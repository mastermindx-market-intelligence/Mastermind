"""Qualify only the existing H3 outer-invalidation rejection delta.

The upstream fixture and the joined quota/Broker bytes are exact inputs.
All Broker, application and SQLite state is created by the original disposable
fixture. The existing offline boundary denies network, subprocess and credentials.
This script does not build, select, install, enroll or invoke a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

FIXTURE_SHA256 = "63dda830a38f941323a9e37a3d2a40f3dad2b4a3c8bf41bfff4997e96822b87e"
QUOTA_SHA256 = "00e8614b35696607fed0455de1b617d70ab70ce822486efe44f742844b5d8c4e"
BROKER_SHA256 = "760a4432373c5785d107096af410dbcae77cdd3c77cb8dc0cab54a2ca8fe0815"
OFFLINE_SHA256 = "a89278e46aff2c71bffb2b8112eb55a09f6607c9c34812bd42f7fbebf146c9eb"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--native-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    fixture_path = args.fixture.resolve(strict=True)
    native = args.native_source.resolve(strict=True)
    for path, expected in (
        (fixture_path, FIXTURE_SHA256),
        (fixture_path.parent / "_offline_boundary.py", OFFLINE_SHA256),
        (native / "quota_remote.py", QUOTA_SHA256),
        (native / "lease_broker.py", BROKER_SHA256),
    ):
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("EXACT_QUALIFICATION_INPUT_REQUIRED")
    os.environ["H3_NATIVE_SOURCE"] = str(native)
    sys.path.insert(0, str(fixture_path.parent))
    spec = importlib.util.spec_from_file_location("_h6_original_h3_fixture", fixture_path)
    if spec is None or spec.loader is None:
        raise ValueError("ORIGINAL_FIXTURE_UNAVAILABLE")
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    observations = []

    class OuterInvalidationTests(original.ExpiryAdmissionTests):
        def snapshot(self):
            return {name: self.rows(name) for name in
                    ("leases", "application_turns", "application_requests")}

        def invalidated(self, field, value):
            self.only_near()
            retained = self.claim(root="retained-liability", account="zeta-near")
            self.assertTrue(retained.ok, retained)
            before = self.snapshot()
            self.cache["go"]["accounts"]["zeta-near"][field] = value
            self.save()
            with self.assertRaisesRegex(ValueError, "^capacity_refresh_unreconciled$"):
                original.quota_remote.account_admission_observation(
                    self.cache, provider="go", account="zeta-near",
                    generation="fixture-generation-1", quota_scope="go:zeta-near",
                    required_windows=self.windows, now_ts=self.clock[0])
            claim = self.claim(root="refused-new-claim", account="zeta-near")
            self.assertFalse(claim.ok, claim)
            application = self.begin(turn="refused-new-application")
            self.assertFalse(application["ok"], application)
            after = self.snapshot()
            self.assertEqual(after, before)
            observations.append({
                "outer_field": field, "claim_refused": True,
                "application_turn_refused": True,
                "original_liability_unchanged": True,
                "rows_before": {key: len(rows) for key, rows in before.items()},
                "rows_after": {key: len(rows) for key, rows in after.items()},
                "claim_reason": claim.reason,
            })

        def test_pending_refresh_refuses(self):
            self.invalidated("refresh_pending", {"operation_id": "fixture-pending"})

        def test_failed_refresh_refuses(self):
            self.invalidated("refresh_error", "fixture-refresh-failed")

        def test_terminal_refusal_refuses(self):
            self.invalidated("terminal_refusal", {"code": "fixture-refused"})

        def test_clean_synthetic_observation_preserves_prior_behavior(self):
            self.only_near()
            result = self.claim(root="clean-observation", account="zeta-near")
            self.assertTrue(result.ok, result)
            self.assertEqual(result.account, "zeta-near")
            self.assertEqual(len(self.rows()), 1)
            self.assertEqual(self.rows("application_turns"), [])
            self.assertEqual(self.rows("application_requests"), [])
            observations.append({"clean_observation": True, "claim_granted": True,
                                 "synthetic_only": True})

    suite = unittest.TestSuite(OuterInvalidationTests(name) for name in (
        "test_pending_refresh_refuses", "test_failed_refresh_refuses",
        "test_terminal_refusal_refuses",
        "test_clean_synthetic_observation_preserves_prior_behavior",
    ))
    original.setUpModule()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        original.tearDownModule()
    receipt = {
        "schema": "mastermind.h6.h3_outer_invalidation_proof.v1",
        "tests": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skips": len(result.skipped),
        "observations": observations,
        "fixture_sha256": FIXTURE_SHA256, "quota_sha256": QUOTA_SHA256,
        "broker_sha256": BROKER_SHA256,
        "provider_calls": False, "live_state_mutated": False,
        "native_selection": False, "strict_scope_qualified": False,
        "open_contracts": ["outer physical/configuration binding",
                           "whole-operation meter enforcement",
                           "publication and claim serialization",
                           "actual quantities and settlement coverage"],
    }
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "tests": result.testsRun,
                      "success": result.wasSuccessful()}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
