#!/usr/bin/env python3
"""Qualify the H3 observation-origin slice in a disposable source stage.

All capacity observations and binding lookups in these Broker fixtures are
synthetic. The real existing cache writer is exercised only against temporary
files. The original offline boundary denies network, subprocess and credentials.
No integer producer, actual Go binding, transport bound, installation, or
publication/claim serialization is qualified by this harness.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

FIXTURE_SHA256 = "63dda830a38f941323a9e37a3d2a40f3dad2b4a3c8bf41bfff4997e96822b87e"
OFFLINE_SHA256 = "a89278e46aff2c71bffb2b8112eb55a09f6607c9c34812bd42f7fbebf146c9eb"
QUOTA_SHA256 = "a1a9ab24d502aad6a3a6edd38f2cb8a781be1175e9715eb36c2ddcea475c88c1"
BROKER_SHA256 = "52295146ad13854adcf68a81d14e8a328b5b034e7c974b2b779387e2f32a0097"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = args.fixture.resolve(strict=True)
    native = args.native_source.resolve(strict=True)
    for path, expected in (
        (fixture, FIXTURE_SHA256),
        (fixture.parent / "_offline_boundary.py", OFFLINE_SHA256),
        (native / "quota_remote.py", QUOTA_SHA256),
        (native / "lease_broker.py", BROKER_SHA256),
    ):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("EXACT_QUALIFICATION_INPUT_REQUIRED")
    os.environ["H3_NATIVE_SOURCE"] = str(native)
    sys.path.insert(0, str(fixture.parent))
    spec = importlib.util.spec_from_file_location("_h6_h3_origin_original", fixture)
    if spec is None or spec.loader is None:
        raise ValueError("ORIGINAL_FIXTURE_UNAVAILABLE")
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    quota = original.quota_remote
    broker = original.lease_broker
    real_binding = quota._config_binding
    observations = []

    class OriginTests(original.ExpiryAdmissionTests):
        def setUp(self):
            self.owner_binding = {"config_generation": "fixture-config-1",
                                  "endpoint": "https://fixture.invalid/v1"}
            self.origin_sequence = 1
            self.binding_patch = patch.object(
                quota, "_config_binding", side_effect=lambda provider: copy.deepcopy(self.owner_binding))
            self.binding_patch.start()
            self.addCleanup(self.binding_patch.stop)
            super().setUp()
            for group in self.cache.values():
                for row in group["accounts"].values():
                    row.update(binding=copy.deepcopy(self.owner_binding),
                               observation_id=row["admission"]["origin"]["observation_id"],
                               refreshed_at=self.clock[0])
            self.save()

        def observation(self, name, reset):
            row = super().observation(name, reset)
            row.update(schema="mastermind.account_capacity_observation.v2",
                       origin={"binding": copy.deepcopy(self.owner_binding),
                               "observation_id": f"{self.origin_sequence:032x}"})
            return row

        def refresh_time(self, seconds=1):
            super().refresh_time(seconds)
            self.origin_sequence += 1
            for group in self.cache.values():
                for row in group["accounts"].values():
                    row.update(binding=copy.deepcopy(self.owner_binding),
                               observation_id=f"{self.origin_sequence:032x}",
                               refreshed_at=self.clock[0])
                    row["admission"]["origin"] = {
                        "binding": copy.deepcopy(self.owner_binding),
                        "observation_id": row["observation_id"]}

        def outer(self):
            return self.cache["go"]["accounts"]["zeta-near"]

        def snapshot(self):
            return {name: self.rows(name) for name in
                    ("leases", "application_turns", "application_requests")}

        def read_near(self):
            return quota.account_admission_observation(
                self.cache, provider="go", account="zeta-near",
                generation="fixture-generation-1", quota_scope="go:zeta-near",
                required_windows=self.windows, now_ts=self.clock[0])

        def request(self, request_id="new-request", request_digest="d"*64):
            return self.br.prepare_application_request(
                principal_id="macro", turn_id="original-turn",
                request_id=request_id, request_digest=request_digest)

        def assert_new_request_refused_unchanged(self):
            before = self.snapshot()
            with self.assertRaisesRegex(broker.ApplicationAdmissionError, "account_origin_unqualified"):
                self.request()
            self.assertEqual(self.snapshot(), before)

        def retained_then_refuse(self, mutation, reason):
            self.only_near()
            retained = self.claim(root="retained-origin", account="zeta-near")
            self.assertTrue(retained.ok, retained)
            before = self.snapshot()
            mutation()
            self.save()
            with self.assertRaises((KeyError, ValueError)):
                self.read_near()
            self.assertFalse(self.claim(root="rebound-claim", account="zeta-near").ok)
            self.assertFalse(self.begin(turn="rebound-turn")["ok"])
            self.assertEqual(self.snapshot(), before)
            observations.append({"case": reason, "new_claim_refused": True,
                                 "new_turn_refused": True, "retained_liability_unchanged": True})

        def test_origin_outer_binding_rebound(self):
            self.retained_then_refuse(
                lambda: self.outer()["binding"].update(config_generation="fixture-config-2"),
                "outer_rebind")

        def test_origin_current_owner_rebound(self):
            self.retained_then_refuse(
                lambda: self.owner_binding.update(config_generation="fixture-config-2"),
                "current_owner_rebind")

        def test_origin_old_inner_spliced_into_new_outer(self):
            self.retained_then_refuse(
                lambda: self.outer().update(observation_id="f"*32, refreshed_at=self.clock[0]+1),
                "old_inner_new_outer")

        def test_origin_missing_old_schema_invalid_origin_refused(self):
            self.only_near()
            good = copy.deepcopy(self.outer())
            cases = [
                lambda row: row["admission"].update(schema="mastermind.account_capacity_observation.v1"),
                lambda row: row["admission"].pop("origin"),
                lambda row: row["admission"]["origin"].update(observation_id="bad"),
                lambda row: row.pop("observation_id"),
                lambda row: row["binding"].update(endpoint="http://fixture.invalid"),
                lambda row: row["admission"]["origin"].update(extra=True),
            ]
            for index, change in enumerate(cases):
                with self.subTest(index=index):
                    self.cache["go"]["accounts"]["zeta-near"] = copy.deepcopy(good)
                    change(self.outer())
                    self.save()
                    with self.assertRaises((KeyError, ValueError)):
                        self.read_near()
                    self.assertFalse(self.claim(root=f"invalid-origin-{index}").ok)
                    self.assertEqual(self.rows(), [])

        def test_origin_clock_normalized_and_original(self):
            self.only_near()
            self.near()["observed_at"] = datetime.fromtimestamp(
                self.clock[0], timezone(timedelta(hours=1))).isoformat()
            self.assertEqual(self.read_near()["observed_at"], self.clock[0])
            self.outer()["refreshed_at"] += .001
            with self.assertRaisesRegex(ValueError, "capacity_origin_clock_changed"):
                self.read_near()

        def test_origin_coherent_rebind_cannot_fund_old_turn(self):
            self.only_near()
            self.assertTrue(self.begin()["ok"])
            self.owner_binding["config_generation"] = "fixture-config-2"
            self.refresh_time()
            self.save()
            self.assertEqual(self.read_near()["origin"]["binding"], self.owner_binding)
            self.assert_new_request_refused_unchanged()

        def test_origin_scope_membership_document_cannot_change(self):
            self.only_near()
            self.assertTrue(self.begin()["ok"])
            self.doc["providers"]["go"]["accounts"].append({
                "name": "new-alias", "per_account_cap": 1,
                "capacity_generation": "fixture-generation-1", "quota_scope": "go:zeta-near"})
            self.save()
            self.assert_new_request_refused_unchanged()

        def test_origin_same_id_cannot_change_content(self):
            self.only_near()
            self.assertTrue(self.begin()["ok"])
            self.clock[0] += 1
            self.near()["observed_at"] = original.iso(self.clock[0])
            self.outer()["refreshed_at"] = self.clock[0]
            self.near()["windows"][0]["remaining"] -= 1
            self.save()
            self.assert_new_request_refused_unchanged()

        def test_origin_same_clock_cannot_change_observation(self):
            self.only_near()
            self.assertTrue(self.begin()["ok"])
            self.near()["origin"]["observation_id"] = "f"*32
            self.outer()["observation_id"] = "f"*32
            self.near()["windows"][0]["remaining"] -= 1
            self.save()
            self.assert_new_request_refused_unchanged()

        def test_origin_window_definition_cannot_change(self):
            self.only_near()
            self.assertTrue(self.begin()["ok"])
            good = copy.deepcopy(self.cache)
            cases = [
                lambda w: w.update(epoch="different-epoch"),
                lambda w: w.update(unit="tokens"),
                lambda w: w.update(limit=101),
                lambda w: w.update(starts_at=original.iso(self.clock[0]-3601)),
                lambda w: w.update(reset_at=original.iso(self.clock[0]+3601)),
                lambda w: w.update(kind="different-kind"),
            ]
            for index, change in enumerate(cases):
                with self.subTest(index=index):
                    self.cache = copy.deepcopy(good)
                    self.refresh_time()
                    change(self.near()["windows"][1])
                    self.save()
                    self.assert_new_request_refused_unchanged()

        def test_origin_new_coherent_observation_preserves_admitted_reservation(self):
            self.only_near()
            binding = self.begin()
            before = self.rows()[0]
            self.refresh_time()
            self.near()["windows"][0]["remaining"] -= 1
            self.save()
            request = self.request()
            self.assertTrue(request["dispatch_permitted"])
            self.assertEqual(request["lease_id"], binding["lease_id"])
            self.assertEqual(self.rows()[0], before)
            self.assertEqual(len(self.rows("application_requests")), 1)
            observations.append({"case": "coherent_new_observation", "new_request_permitted": True,
                                 "same_original_lease": True, "reservation_unchanged": True})

        def test_origin_unknown_recovery_and_settlement_after_rebind(self):
            self.only_near()
            binding, request = self.prepared()
            self.br.mark_application_request_unknown(dispatch_id=request["dispatch_id"], reason="response_lost")
            before = self.snapshot()
            self.owner_binding["config_generation"] = "fixture-config-2"
            recovered = self.request("original-request", "b"*64)
            self.assertEqual(recovered["dispatch_id"], request["dispatch_id"])
            self.assertFalse(recovered["dispatch_permitted"])
            self.assertEqual(self.snapshot(), before)
            unsettled = self.request()
            self.assertEqual(unsettled["disposition"], "effect_unknown")
            self.assertEqual(self.snapshot(), before)
            settled = self.br.complete_application_request(
                dispatch_id=request["dispatch_id"], terminal_receipt=self.receipt(request))
            self.assertEqual(settled["terminal_receipt"]["account"], binding["account"])
            self.assert_new_request_refused_unchanged()
            self.br.close_application_turn(principal_id="macro", turn_id="original-turn")
            self.assertEqual(self.rows()[0]["state"], "released")
            self.assertEqual(len(self.rows("application_requests")), 1)

        def test_origin_terminal_recovery_after_rebind(self):
            self.only_near()
            _, request = self.prepared()
            self.br.complete_application_request(
                dispatch_id=request["dispatch_id"], terminal_receipt=self.receipt(request))
            before = self.snapshot()
            self.owner_binding["config_generation"] = "fixture-config-2"
            recovered = self.request("original-request", "b"*64)
            self.assertEqual(recovered["dispatch_id"], request["dispatch_id"])
            self.assertFalse(recovered["dispatch_permitted"])
            self.assertEqual(self.snapshot(), before)

        def test_origin_cross_epoch_refuses_new_request_preserves_recovery(self):
            self.only_near()
            _, request = self.prepared()
            self.br.complete_application_request(
                dispatch_id=request["dispatch_id"], terminal_receipt=self.receipt(request))
            self.refresh_time()
            for window in self.near()["windows"]:
                window.update(epoch="next-"+window["kind"], starts_at=original.iso(self.clock[0]-1),
                              reset_at=original.iso(self.clock[0]+3600))
            self.save()
            self.assert_new_request_refused_unchanged()
            recovered = self.request("original-request", "b"*64)
            self.assertEqual(recovered["dispatch_id"], request["dispatch_id"])
            self.assertFalse(recovered["dispatch_permitted"])

        def test_origin_pending_error_refusal_remain_closed(self):
            for field, value in (("refresh_pending", {"attempt_id": "fixture"}),
                                 ("refresh_error", "fixture-failure"),
                                 ("terminal_refusal", {"code": "fixture-refusal"})):
                with self.subTest(field=field):
                    self.outer()[field] = value
                    with self.assertRaisesRegex(ValueError, "capacity_refresh_unreconciled"):
                        self.read_near()
                    self.outer().pop(field)

        def test_origin_actual_go_owner_remains_unsupported(self):
            self.only_near()
            with patch.object(quota, "_config_binding", side_effect=real_binding):
                self.assertIsNone(quota._config_binding("go"))
                with self.assertRaisesRegex(ValueError, "capacity_origin_unqualified"):
                    self.read_near()
                self.assertFalse(self.claim().ok)
                self.assertEqual(self.rows(), [])

        def test_origin_minimax_uses_canonical_provider_row(self):
            row = copy.deepcopy(self.outer())
            row["admission"].update(provider="minimax", quota_scope="minimax:zeta-near")
            row["accounts"] = {"zeta-near": {"admission": {"schema": "invalid-copy"}}}
            kwargs = dict(provider="minimax", account="zeta-near",
                          generation="fixture-generation-1", quota_scope="minimax:zeta-near",
                          required_windows=self.windows, now_ts=self.clock[0])
            result = quota.account_admission_observation({"minimax": row}, **kwargs)
            self.assertEqual(result["provider"], "minimax")
            with self.assertRaises((KeyError, ValueError)):
                quota.account_admission_observation(
                    {"minimax": {"accounts": {"zeta-near": copy.deepcopy(self.outer())}}}, **kwargs)

        def publication(self):
            path = self.root / "publication.json"
            path.write_text("{}")
            binding = copy.deepcopy(self.owner_binding)
            attempt = quota._begin_refresh(
                str(path), "glm", "fixture-account", binding, self.clock[0])
            self.assertRegex(attempt, r"^[0-9a-f]{32}$")
            return path, binding, attempt

        def test_origin_publisher_retains_original_matched_attempt(self):
            path, binding, attempt = self.publication()
            row = quota._publish_observation(
                str(path), "glm", "fixture-account", [], binding, self.clock[0], attempt_id=attempt)
            self.assertEqual(row["observation_id"], attempt)
            self.assertEqual(row["binding"], binding)
            self.assertEqual(row["refreshed_at"], self.clock[0])
            self.assertNotIn("refresh_pending", row)
            self.assertNotIn("admission", row)
            self.assertEqual(json.loads(path.read_text())["glm"]["accounts"]["fixture-account"], row)

        def test_origin_publisher_removed_marker_never_recreates_row(self):
            path, binding, attempt = self.publication()
            path.write_text("{}")
            before = path.read_bytes()
            result = quota._publish_observation(
                str(path), "glm", "fixture-account", [], binding, self.clock[0], attempt_id=attempt)
            self.assertIsNone(result)
            self.assertEqual(path.read_bytes(), before)

        def test_origin_publisher_wrong_original_identity_preserves_marker(self):
            path, binding, attempt = self.publication()
            before = path.read_bytes()
            cases = [
                ("glm", "fixture-account", binding, self.clock[0], "f"*32),
                ("glm", "different-account", binding, self.clock[0], attempt),
                ("other", "fixture-account", binding, self.clock[0], attempt),
                ("glm", "fixture-account", dict(binding, config_generation="changed"), self.clock[0], attempt),
                ("glm", "fixture-account", binding, self.clock[0]+1, attempt),
            ]
            for values in cases:
                with self.subTest(identity=values):
                    provider, account, candidate, stamp, original_attempt = values
                    quota._publish_observation(
                        str(path), provider, account, [], candidate, stamp, attempt_id=original_attempt)
                    self.assertEqual(path.read_bytes(), before)

        def test_origin_publisher_owner_rebind_preserves_pending(self):
            path, binding, attempt = self.publication()
            before = path.read_bytes()
            self.owner_binding["config_generation"] = "fixture-config-2"
            result = quota._publish_observation(
                str(path), "glm", "fixture-account", [], binding, self.clock[0], attempt_id=attempt)
            self.assertEqual(result["refresh_pending"]["attempt_id"], attempt)
            self.assertEqual(path.read_bytes(), before)

        def test_origin_legacy_percentage_publish_never_mints_strict_origin(self):
            path = self.root / "legacy-publication.json"
            path.write_text("{}")
            row = quota._publish_observation(
                str(path), "glm", "fixture-account", [], None, self.clock[0])
            self.assertNotIn("observation_id", row)
            self.assertNotIn("admission", row)

    names = unittest.defaultTestLoader.getTestCaseNames(OriginTests)
    inherited = unittest.defaultTestLoader.getTestCaseNames(original.ExpiryAdmissionTests)
    suite = unittest.TestSuite(OriginTests(name) for name in names)
    original.setUpModule()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        original.tearDownModule()
    receipt = {
        "schema": "mastermind.h6.h3_origin_proof.v1",
        "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skips": len(result.skipped),
        "inherited_tests_with_explicit_v2_synthetic_fixture": len(inherited),
        "new_origin_tests": len(names)-len(inherited), "test_names": names,
        "observations": observations,
        "fixture_sha256": FIXTURE_SHA256, "offline_boundary_sha256": OFFLINE_SHA256,
        "quota_sha256": QUOTA_SHA256, "broker_sha256": BROKER_SHA256,
        "fixture_binding_lookup": True, "real_go_binding_supported": False,
        "provider_calls": False, "live_state_mutated": False,
        "native_selection": False, "strict_scope_qualified": False,
        "open_contracts": [
            "actual integer quantity and settlement-coverage producer",
            "physical subscription and entitlement qualification",
            "whole-operation billable meter enforcement",
            "publication/claim participating-writer serialization",
            "execution-owner binding through actual provider send",
        ],
    }
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "tests": result.testsRun,
                      "success": result.wasSuccessful()}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
