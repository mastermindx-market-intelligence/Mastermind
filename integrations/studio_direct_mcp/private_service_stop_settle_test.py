"""Bounded launchd stop-settle tests; never operate a real host service."""
import inspect
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import private_service as svc


class StopSettleTests(unittest.TestCase):
    """Probe the original stop body behind unchanged lifecycle decorators."""

    def setUp(self):
        self.account = svc.C2_PAPER_ACCOUNT
        self.plist = Path("/private/virtual/launch/owned.plist")
        self.roots = {"plist": self.plist}
        self.loaded = {"path": str(self.plist), "state": "running", "pid": 77}
        self.bootout_calls = []
        self.calls = []
        self.patches = [
            mock.patch.object(svc, "_build_runtime_roots", return_value=self.roots),
            mock.patch.object(svc, "_verify_native_pin_install", return_value={}),
            mock.patch.object(svc.time, "sleep", return_value=None),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.stop = inspect.unwrap(svc.cmd_stop)

    def execute(self, observations, *, account=None, bootout_ok=True):
        seq = iter(observations)

        def inspect_state(*_args, **_kwargs):
            self.calls.append("observe")
            observation = next(seq)
            if isinstance(observation, BaseException):
                raise observation
            return observation

        def run(cmd, **_kwargs):
            self.bootout_calls.append(tuple(cmd))
            return svc.CmdResult(0 if bootout_ok else 1, "", "" if bootout_ok else "failed")

        output = io.StringIO()
        with mock.patch.object(svc, "_lifecycle_inspect", inspect_state), \
             mock.patch.object(svc, "_run", run), \
             redirect_stdout(output):
            result = self.stop(SimpleNamespace(account=account or self.account))
        return result, json.loads(output.getvalue())

    def test_transient_indeterminate_then_exact_absence_succeeds(self):
        result, body = self.execute(
            [self.loaded, SystemExit("transient"), None]
        )
        self.assertEqual(result, 0)
        self.assertTrue(body["stopped"])
        self.assertEqual(len(self.bootout_calls), 1)
        self.assertEqual(self.calls, ["observe", "observe", "observe"])

    def test_live_then_absent_without_uncertainty_succeeds(self):
        result, body = self.execute([self.loaded, self.loaded, None])
        self.assertEqual(result, 0)
        self.assertTrue(body["stopped"])
        self.assertEqual(len(self.bootout_calls), 1)

    def test_persistent_indeterminate_remains_effect_unknown(self):
        with mock.patch.object(svc.time, "monotonic", side_effect=[100.0, 111.0]):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.execute([self.loaded, SystemExit("indeterminate")])
        self.assertEqual(len(self.bootout_calls), 1)
        self.assertEqual(len(self.calls), 2)

    def test_still_loaded_timeout_not_falsely_stopped(self):
        with mock.patch.object(svc.time, "monotonic", side_effect=[100.0, 111.0]):
            result, body = self.execute([self.loaded, self.loaded])
        self.assertEqual(result, 1)
        self.assertFalse(body["stopped"])
        self.assertEqual(body["reason"], "still loaded")
        self.assertEqual(len(self.bootout_calls), 1)

    def test_non_enrolled_state_error_preserves_original_behavior(self):
        with self.assertRaisesRegex(SystemExit, "indeterminate"):
            self.execute([self.loaded, SystemExit("indeterminate")],
                         account="test-account")
        self.assertEqual(len(self.bootout_calls), 1)

    def test_failed_bootout_is_not_retried_or_reported_stopped(self):
        result, body = self.execute([self.loaded], bootout_ok=False)
        self.assertEqual(result, 1)
        self.assertFalse(body["stopped"])
        self.assertEqual(body["reason"], "bootout failed")
        self.assertEqual(len(self.bootout_calls), 1)
        self.assertEqual(self.calls, ["observe"])

    def test_initial_exact_absence_never_calls_bootout(self):
        result, body = self.execute([None])
        self.assertEqual(result, 0)
        self.assertTrue(body["stopped"])
        self.assertTrue(body["already"])
        self.assertEqual(self.bootout_calls, [])

    def test_strict_account_set_cannot_widen_to_unknown(self):
        for account in (
            svc.C2_PAPER_ACCOUNT, svc.C4_PAPER_ACCOUNT,
        ):
            with self.subTest(account=account):
                self.bootout_calls.clear()
                self.calls.clear()
                result, body = self.execute([self.loaded, SystemExit("transient"), None],
                                            account=account)
                self.assertEqual(result, 0)
                self.assertTrue(body["stopped"])
                self.assertEqual(len(self.bootout_calls), 1)


if __name__ == "__main__":
    unittest.main()
