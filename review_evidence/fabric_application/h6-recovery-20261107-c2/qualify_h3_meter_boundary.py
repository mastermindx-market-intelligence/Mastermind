#!/usr/bin/env python3
"""Qualify missing-meter refusal without creating a billable-capacity authority.

Preexisting prepared effects are created by the exact pre-guard Broker against
the same disposable SQLite owner, then recovered/settled by the new Broker.
No guard is bypassed to seed these originals. All observations, binding lookups
and terminal receipts are synthetic under the original offline boundary.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

FIXTURE = "63dda830a38f941323a9e37a3d2a40f3dad2b4a3c8bf41bfff4997e96822b87e"
OFFLINE = "a89278e46aff2c71bffb2b8112eb55a09f6607c9c34812bd42f7fbebf146c9eb"
QUOTA = "a1a9ab24d502aad6a3a6edd38f2cb8a781be1175e9715eb36c2ddcea475c88c1"
BEFORE = "52295146ad13854adcf68a81d14e8a328b5b034e7c974b2b779387e2f32a0097"
AFTER = "93531372cf343cd92e47fd430acf949b141759ca8cf2b4a5c86b1be4c56246c2"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("EXACT_SOURCE_REQUIRED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--predecessor-native-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = args.fixture.resolve(strict=True)
    native = args.native_source.resolve(strict=True)
    previous = args.predecessor_native_source.resolve(strict=True)
    for path, expected in (
        (fixture, FIXTURE), (fixture.parent/"_offline_boundary.py", OFFLINE),
        (native/"quota_remote.py", QUOTA), (native/"lease_broker.py", AFTER),
        (previous/"quota_remote.py", QUOTA), (previous/"lease_broker.py", BEFORE),
    ):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("EXACT_QUALIFICATION_INPUT_REQUIRED")
    os.environ["H3_NATIVE_SOURCE"] = str(native)
    sys.path.insert(0, str(fixture.parent))
    original = load("_h6_h3_meter_original", fixture)
    predecessor = load("_h6_h3_before_meter_broker", previous/"lease_broker.py")
    quota, broker = original.quota_remote, original.lease_broker
    observations = []

    class MeterBoundaryTests(original.ExpiryAdmissionTests):
        def setUp(self):
            self.owner_binding = {"config_generation": "fixture-config-1",
                                  "endpoint": "https://fixture.invalid/v1"}
            binding = patch.object(quota, "_config_binding",
                                   side_effect=lambda provider: copy.deepcopy(self.owner_binding))
            binding.start()
            self.addCleanup(binding.stop)
            super().setUp()
            for group in self.cache.values():
                for row in group["accounts"].values():
                    row.update(binding=copy.deepcopy(self.owner_binding),
                               observation_id="1"*32, refreshed_at=self.clock[0])
            self.save()
            policy = patch.object(predecessor.Broker, "_expiry_source_policy",
                return_value=({"promote": True, "hours_before_reset": 36.0,
                               "min_remaining_pct": 15.0}, "a"*64))
            policy.start()
            self.addCleanup(policy.stop)

        def observation(self, name, reset):
            result = super().observation(name, reset)
            result.update(schema="mastermind.account_capacity_observation.v2",
                          origin={"binding": copy.deepcopy(self.owner_binding),
                                  "observation_id": "1"*32})
            return result

        def snapshot(self):
            return {table: self.rows(table) for table in
                    ("leases", "application_turns", "application_requests")}

        def prepare(self, request_id="new-request", digest="d"*64):
            return self.br.prepare_application_request(
                principal_id="macro", turn_id="original-turn",
                request_id=request_id, request_digest=digest)

        def refuse_new_unchanged(self):
            before = self.snapshot()
            with self.assertRaisesRegex(broker.ApplicationAdmissionError,
                                        "^application admission refused: account_dispatch_meter_unqualified$"):
                self.prepare()
            self.assertEqual(self.snapshot(), before)

        def prepare_preexisting(self):
            self.only_near()
            prior = predecessor.Broker(
                db_path=str(self.root/"leases.sqlite"), lock_path=str(self.root/"leases.lock"),
                accounts_path=str(self.accounts), now_fn=lambda: self.clock[0],
                check_pid=False, external_gates=False, this_host="fixture-host",
                status_json=str(self.root/"status.json"))
            binding = self.begin(broker=prior)
            request = prior.prepare_application_request(
                principal_id="macro", turn_id="original-turn",
                request_id="original-request", request_digest="b"*64)
            self.assertTrue(request["dispatch_permitted"])
            self.assertEqual(len(self.rows("application_requests")), 1)
            return binding, request

        def test_meter_missing_bound_refuses_before_first_dispatch(self):
            self.only_near(remaining=1)
            binding = self.begin()
            self.assertTrue(binding["ok"])
            admission = json.loads(self.rows()[0]["account_admission_json"])
            self.assertEqual({w["reserved_units"] for w in admission["windows"]}, {1})
            self.assertEqual(self.grant["max_steps"], 2)
            self.refuse_new_unchanged()
            self.assertEqual(self.rows("application_requests"), [])
            observations.append({"case": "one_request_reservation_two_step_grant",
                                 "first_dispatch_refused": True,
                                 "new_request_records": 0, "reservation_unchanged": True})

        def test_meter_one_harness_step_is_still_not_a_billable_bound(self):
            self.only_near()
            self.grant["max_steps"] = 1
            self.save()
            self.assertTrue(self.begin()["ok"])
            self.refuse_new_unchanged()

        def test_meter_new_coherent_observation_cannot_create_dispatch_authority(self):
            self.only_near()
            self.assertTrue(self.begin()["ok"])
            self.clock[0] += 1
            for row in self.cache["go"]["accounts"].values():
                row.update(refreshed_at=self.clock[0], observation_id="2"*32)
                row["admission"].update(observed_at=original.iso(self.clock[0]))
                row["admission"]["origin"]["observation_id"] = "2"*32
            self.save()
            self.refuse_new_unchanged()

        def test_meter_original_pending_recovers_without_new_request(self):
            _, request = self.prepare_preexisting()
            before = self.snapshot()
            result = self.prepare("original-request", "b"*64)
            self.assertEqual(result["dispatch_id"], request["dispatch_id"])
            self.assertFalse(result["dispatch_permitted"])
            self.assertEqual(self.snapshot(), before)

        def test_meter_original_unknown_settles_and_keeps_original_liability(self):
            binding, request = self.prepare_preexisting()
            self.br.mark_application_request_unknown(
                dispatch_id=request["dispatch_id"], reason="response_lost")
            before = self.snapshot()
            recovered = self.prepare("original-request", "b"*64)
            self.assertEqual(recovered["dispatch_id"], request["dispatch_id"])
            self.assertFalse(recovered["dispatch_permitted"])
            self.assertEqual(self.prepare()["disposition"], "effect_unknown")
            self.assertEqual(self.snapshot(), before)
            result = self.br.complete_application_request(
                dispatch_id=request["dispatch_id"], terminal_receipt=self.receipt(request))
            self.assertEqual(result["terminal_receipt"]["account"], binding["account"])
            self.refuse_new_unchanged()
            retained = self.rows()[0]["account_admission_json"]
            self.br.close_application_turn(principal_id="macro", turn_id="original-turn")
            self.assertEqual(self.rows()[0]["state"], "released")
            self.assertEqual(self.rows()[0]["account_admission_json"], retained)
            self.assertEqual(len(self.rows("application_requests")), 1)

        def test_meter_original_terminal_recovers_after_binding_change(self):
            _, request = self.prepare_preexisting()
            self.br.complete_application_request(
                dispatch_id=request["dispatch_id"], terminal_receipt=self.receipt(request))
            self.owner_binding["config_generation"] = "fixture-config-2"
            before = self.snapshot()
            result = self.prepare("original-request", "b"*64)
            self.assertEqual(result["dispatch_id"], request["dispatch_id"])
            self.assertFalse(result["dispatch_permitted"])
            self.assertEqual(self.snapshot(), before)

        def test_meter_changed_original_digest_never_becomes_another_effect(self):
            self.prepare_preexisting()
            before = self.snapshot()
            with self.assertRaisesRegex(broker.ApplicationAdmissionError, "request_conflict"):
                self.prepare("original-request", "f"*64)
            self.assertEqual(self.snapshot(), before)

        def test_meter_original_turn_recovers_after_binding_change(self):
            binding, _ = self.prepare_preexisting()
            self.owner_binding["config_generation"] = "fixture-config-2"
            before = self.snapshot()
            recovered = self.begin()
            self.assertEqual(recovered["lease_id"], binding["lease_id"])
            self.assertEqual(self.snapshot(), before)

        def test_meter_ordinary_application_keeps_existing_two_step_contract(self):
            self.doc["providers"]["go"].pop("expiry_admission")
            self.save()
            self.assertTrue(self.begin()["ok"])
            self.assertIsNone(self.rows()[0]["account_admission_json"])
            first = self.prepare("original-request", "b"*64)
            self.assertTrue(first["dispatch_permitted"])
            self.br.complete_application_request(
                dispatch_id=first["dispatch_id"], terminal_receipt=self.receipt(first))
            second = self.prepare()
            self.assertTrue(second["dispatch_permitted"])
            self.assertEqual(len(self.rows("application_requests")), 2)
            observations.append({"case": "ordinary_application_no_strict_h3_envelope",
                                 "existing_two_steps_preserved": True,
                                 "billable_meter_qualification_claimed": False})

    names = [n for n in unittest.defaultTestLoader.getTestCaseNames(MeterBoundaryTests)
             if n.startswith("test_meter_")]
    suite = unittest.TestSuite(MeterBoundaryTests(name) for name in names)
    original.setUpModule()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        original.tearDownModule()
    receipt = {
        "schema": "mastermind.h6.h3_meter_boundary_proof.v1",
        "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skips": len(result.skipped),
        "test_names": names, "observations": observations,
        "fixture_sha256": FIXTURE, "offline_boundary_sha256": OFFLINE,
        "quota_sha256": QUOTA, "broker_predecessor_sha256": BEFORE, "broker_sha256": AFTER,
        "preexisting_dispatches_created_by_exact_predecessor": True,
        "new_strict_dispatch": "REFUSED_MISSING_EXECUTION_OWNER_BILLABLE_CONTRACT",
        "whole_operation_vector_enforced": False, "strict_scope_qualified": False,
        "provider_calls": False, "live_state_mutated": False, "native_selection": False,
        "limits": [
            "No production Go origin or integer-capacity producer is established",
            "One HTTP POST is not asserted to equal one billable request unit",
            "Native internal attempts and quota-epoch attribution remain unqualified",
            "All retained original effects and settlement stay with their original owner",
        ],
    }
    with args.output.open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"tests": result.testsRun, "success": result.wasSuccessful(),
                      "output": str(args.output)}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
