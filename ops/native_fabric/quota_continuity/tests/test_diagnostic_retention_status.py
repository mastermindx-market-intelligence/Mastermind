"""Regression for diagnostic predicate false versus owned-process uncertainty.

The CLI and deadline wrapper run as actual local subprocesses against absent
synthetic diagnostics. No broker, provider, account or installed state is used.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
sys.path[:0] = [str(CANDIDATE), str(ROOT / "source")]
import remote_sub_helpers as helpers


class DiagnosticRetentionExitTests(unittest.TestCase):
    def command(self, lane_root):
        return [
            sys.executable, "-B", str(CANDIDATE / "provider_outcome.py"),
            "retained-diagnostic-ready", str(lane_root),
            "fixture-diagnostic-run", "fixture-diagnostic-root",
        ]

    def environment(self, home):
        return {
            "PATH": os.defpath,
            "HOME": str(home),
            "PYTHONPATH": os.pathsep.join((str(CANDIDATE), str(ROOT / "source"))),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def test_false_predicate_is_not_reserved_cleanup_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                self.command(Path(temp)), env=self.environment(temp),
                capture_output=True, timeout=5,
            )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, b"", b""))

    def test_actual_owned_wrapper_preserves_false_with_proved_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            receipt = home / "owned-process.jsonl"
            env = self.environment(home)
            env.update(
                POOL_COMMISSION_DEADLINE_NS=str(time.monotonic_ns() + 5_000_000_000),
                REMOTE_SUB_DEADLINE_PROCESS_RECEIPT=str(receipt),
            )
            result = subprocess.run(
                [sys.executable, "-B", str(CANDIDATE / "remote_sub_helpers.py"),
                 "deadline-command", "diagnostic-retention", "-", *self.command(home)],
                env=env, capture_output=True, timeout=8,
            )
            rows = [json.loads(line) for line in receipt.read_bytes().splitlines()]
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, b"", b""))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["returncode"], 1)
        self.assertEqual(row["label"], "commission-diagnostic-retention")
        self.assertFalse(row["stdout_truncated"])
        self.assertFalse(row["stderr_truncated"])
        self.assertTrue(row["cleanup"]["identity_verified"])
        self.assertTrue(row["cleanup"]["census_proven"])
        self.assertEqual(row["cleanup"]["residual_count"], 0)
        self.assertTrue(row["cleanup"]["stdout_capture_complete"])
        self.assertTrue(row["cleanup"]["stderr_capture_complete"])

    def test_unproved_cleanup_still_uses_reserved_exit(self):
        observed = SimpleNamespace(stdout="", stderr="", cleanup_proven=False)
        with mock.patch.dict(os.environ, {
            "POOL_COMMISSION_DEADLINE_NS": str(time.monotonic_ns() + 5_000_000_000),
        }), mock.patch.object(sys, "argv", [
            "helper", "diagnostic-retention", "-", "/synthetic-not-executed",
        ]), mock.patch("lane_runtime.install_signal_cleanup"), mock.patch(
            "lane_runtime.run_owned_process", return_value=observed,
        ), mock.patch("sys.stderr"), self.assertRaises(SystemExit) as refused:
            helpers.deadline_command()
        self.assertEqual(refused.exception.code, 76)


if __name__ == "__main__":
    unittest.main()
