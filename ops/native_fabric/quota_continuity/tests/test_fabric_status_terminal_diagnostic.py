"""Read-only status projection of existing, validated Fabric terminal evidence.

No live worker, provider credentials, admissions or retry behavior.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "source"), str(ROOT / "candidate")]
import fabric_task
import provider_outcome


class TerminalDiagnostic(unittest.TestCase):
    RID = "fixture-glm-turn-ceiling"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dir = self.root / "state" / "remote_sub"
        self.dir.mkdir(parents=True)
        self.log = (f"2026-10-30T22:16Z [remote_sub id={self.RID} host=ubuntu3] "
                    f"PROVIDER_OUTCOME_RECORDED file={self.RID}.provider.json\n").encode()
        (self.dir / f"{self.RID}.log").write_bytes(self.log)
        self.outcome = {"command_rc": 1, "kind": "turn_limit",
                        "cli_subtype": "error_max_turns",
                        "cli_terminal_reason": "max_turns"}
        self.provider_file = self.dir / f"{self.RID}.provider.json"
        self.process_file = self.dir / f"{self.RID}.process.jsonl"
        self.save()
        self.status = {"state": "TERMINAL", "rc": 1, "signal": "other"}
        self.here = mock.patch.object(fabric_task, "HERE", self.root)
        self.here.start()
        self.addCleanup(self.here.stop)

    def save(self):
        self.provider_file.write_text(json.dumps(self.outcome))
        self.process_file.write_text(json.dumps({"schema": "fixture"}))
        self.provider_file.chmod(0o600)
        self.process_file.chmod(0o600)

    def project(self, **status):
        with mock.patch.object(provider_outcome, "validate_receipt") as verify:
            value = fabric_task._terminal_provider_projection(
                self.RID, status or self.status, self.log)
            if value:
                verify.assert_called_once()
            return value

    def test_bound_terminal_enriches_only_with_diagnostic_not_authority(self):
        out = self.project()
        self.assertEqual(out, {"terminal_provider_diagnostic": {
            "kind": "turn_limit", "cli_subtype": "error_max_turns",
            "source": "validated_original_provider_process_receipt",
            "replay_authorized": False,
        }})

    def test_success_settling_other_rc_and_effect_unknown_never_project(self):
        for status in (
            {"state": "TERMINAL", "rc": 0, "signal": "ok"},
            {"state": "ACTIVE_OR_WAITING", "rc": None, "signal": None},
            {"state": "SETTLING", "rc": 1, "signal": "other"},
            {"state": "EFFECT_UNKNOWN", "rc": 1, "signal": "effect_unknown"},
            {"state": "TERMINAL", "rc": 2, "signal": "other"},
        ):
            with self.subTest(status=status):
                self.assertFalse(self.project(**status))

    def test_provider_mismatch_or_broken_proof_withholds_diagnostic(self):
        for key, value in (("kind", "invalid_request"),
                           ("cli_subtype", "error_during_execution"),
                           ("cli_terminal_reason", "unknown"),
                           ("command_rc", 0)):
            with self.subTest(key=key):
                original = dict(self.outcome)
                self.outcome[key] = value
                self.save()
                self.assertFalse(self.project())
                self.outcome = original
        self.save()
        with mock.patch.object(provider_outcome, "validate_receipt",
                               side_effect=ValueError("unbound")):
            self.assertFalse(fabric_task._terminal_provider_projection(
                self.RID, self.status, self.log))
        self.provider_file.chmod(0o622)
        self.assertFalse(self.project())

    def test_missing_controller_proof_is_never_inferred_from_result_text(self):
        self.log = b"2026-10-30T22:16Z unrecognized_model\n"
        (self.dir / f"{self.RID}.log").write_bytes(self.log)
        self.assertFalse(self.project())


if __name__ == "__main__":
    unittest.main()
