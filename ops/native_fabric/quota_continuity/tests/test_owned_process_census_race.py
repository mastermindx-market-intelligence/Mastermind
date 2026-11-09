"""Bounded original-Popen observations at the owned-process exit/census seam."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "candidate" / "lane_runtime.py"
_SPEC = importlib.util.spec_from_file_location("owned_process_census_race_runtime", SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
runtime = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = runtime
_SPEC.loader.exec_module(runtime)


class OwnedProcessCensusRace(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.process = Mock(spec=["wait", "poll"])
        self.process.poll.return_value = None
        self.process.wait.side_effect = self.wait
        self.reap = lambda timeout: 0
        self.census_elapsed = 0.0
        self.census = ((), True)

    def wait(self, *, timeout):
        if self.process.wait.call_count == 1:
            self.now += timeout
            raise subprocess.TimeoutExpired("original-owned-fixture", timeout)
        return self.reap(timeout)

    def observe(self, expected_pgid):
        self.assertEqual(expected_pgid, 1234)
        self.now += self.census_elapsed
        return self.census

    def run_wait(self, *, timeout=5.0):
        with patch.object(runtime.time, "monotonic", side_effect=lambda: self.now), \
             patch.object(runtime, "_verified_group_members", side_effect=self.observe), \
             patch.object(runtime.subprocess, "Popen") as start:
            try:
                return runtime._wait_owned_process_with_fuse(self.process, 1234, timeout)
            finally:
                start.assert_not_called()

    def test_empty_census_can_reap_the_same_held_process_once(self):
        self.assertEqual(self.run_wait(), "completed")
        self.assertEqual(self.process.wait.call_count, 2)
        self.assertEqual(self.process.poll.call_count, 1)
        self.assertAlmostEqual(self.process.wait.call_args.kwargs["timeout"], 0.05)

    def test_already_reaped_exit_needs_no_additional_wait(self):
        self.process.poll.return_value = 0
        self.assertEqual(self.run_wait(), "completed")
        self.assertEqual(self.process.wait.call_count, 1)

    def test_still_live_leader_preserves_the_original_refusal_without_retry(self):
        def still_live(timeout):
            self.now += timeout
            raise subprocess.TimeoutExpired("original-owned-fixture", timeout)
        self.reap = still_live
        with self.assertRaisesRegex(
            runtime.ProcessCensusError, "^process_group_census_empty_while_leader_live$"
        ):
            self.run_wait()
        self.assertEqual(self.process.wait.call_count, 2)
        self.assertEqual(self.process.poll.call_count, 1)

    def test_exit_observation_uses_only_remaining_original_deadline(self):
        self.census_elapsed = 3.98
        self.assertEqual(self.run_wait(), "completed")
        self.assertAlmostEqual(self.process.wait.call_args.kwargs["timeout"], 0.02)
        self.assertEqual(self.process.wait.call_count, 2)

    def test_deadline_elapsed_during_census_does_not_start_another_wait(self):
        self.census_elapsed = 4.01
        self.assertEqual(self.run_wait(), "timeout")
        self.assertEqual(self.process.wait.call_count, 1)

    def test_final_bounded_wait_expiry_is_timeout_at_original_deadline(self):
        self.census_elapsed = 3.98
        def expiry(timeout):
            self.now += timeout
            raise subprocess.TimeoutExpired("original-owned-fixture", timeout)
        self.reap = expiry
        self.assertEqual(self.run_wait(), "timeout")
        self.assertEqual(self.process.wait.call_count, 2)

    def test_session_identity_mismatch_is_not_reinterpreted_as_exit(self):
        self.census = ((), False)
        with self.assertRaisesRegex(
            runtime.ProcessCensusError, "^process_group_session_identity_mismatch$"
        ):
            self.run_wait()
        self.assertEqual(self.process.wait.call_count, 1)
        self.process.poll.assert_not_called()

    def test_group_growth_fuse_is_unchanged(self):
        self.census = (tuple(range(runtime.MAX_OWNED_PROCESS_GROUP_MEMBERS + 1)), True)
        self.assertEqual(self.run_wait(), "process_limit")
        self.assertEqual(self.process.wait.call_count, 1)
        self.process.poll.assert_not_called()

    def test_census_permission_failure_is_preserved(self):
        def refused(_):
            raise runtime.ProcessCensusError("process_session_identity_permission_denied")
        self.observe = refused
        with self.assertRaisesRegex(
            runtime.ProcessCensusError, "^process_session_identity_permission_denied$"
        ):
            self.run_wait()
        self.assertEqual(self.process.wait.call_count, 1)
        self.process.poll.assert_not_called()

    def test_original_wait_errors_are_not_suppressed(self):
        for error in (PermissionError("fixture-denied"), ChildProcessError("fixture-unowned")):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                def refused(timeout):
                    raise error
                self.reap = refused
                with self.assertRaises(type(error)):
                    self.run_wait()
                self.assertEqual(self.process.wait.call_count, 2)

    def test_real_owned_child_retains_full_session_and_capture_proof(self):
        result = runtime.run_owned_process(
            [sys.executable, "-B", "-c",
             "import sys; print('owned-out'); print('owned-err', file=sys.stderr)"],
            timeout=5.0,
            label="exit-observation-real-fixture",
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "owned-out\n")
        self.assertEqual(result.stderr, "owned-err\n")
        self.assertFalse(result.timed_out)
        self.assertTrue(runtime.cleanup_receipt_is_proven(result.cleanup))
        self.assertTrue(result.cleanup["stdout_capture_complete"])
        self.assertTrue(result.cleanup["stderr_capture_complete"])
        self.assertTrue(result.cleanup["stdin_delivery_complete"])


if __name__ == "__main__":
    unittest.main()
