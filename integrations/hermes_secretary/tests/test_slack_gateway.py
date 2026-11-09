"""Source qualification for the existing M2 Slack gateway.

No Slack token, Socket Mode connection, Hermes process, model call or host
mutation is required. The user-visible stdout and native stderr receipt remain
separate; fresh session IDs are necessary for per-thread continuation.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "slack_gateway.py"
SPEC = importlib.util.spec_from_file_location("mmx_slack_gateway_candidate", PATH)
assert SPEC and SPEC.loader
gateway = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gateway
SPEC.loader.exec_module(gateway)


class HermesSessionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conf_patcher = patch.object(gateway, "CONF_DIR", Path(self.tmp.name))
        self.conf_patcher.start()
        self.addCleanup(self.conf_patcher.stop)

    def fake_subprocess(self, *, output, diagnostics="", returncode=0):
        def invoke(cmd, **kwargs):
            self.assertEqual(cmd[:2], ["hermes", "chat"])
            self.assertIn("--query-file", cmd)
            self.assertIn("--oneshot", cmd)
            self.assertIn("-Q", cmd)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(Path(cmd[cmd.index("--query-file")+1]).is_file())
            self.assertEqual(
                Path(cmd[cmd.index("--query-file")+1]).read_text(),
                "Answer my question",
            )
            return subprocess.CompletedProcess(cmd, returncode, output, diagnostics)
        return invoke

    def test_quiet_mode_session_from_stderr_is_saved(self):
        session = "abcd1234-1234-1234-1234-123456789012"
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="My response", diagnostics="\nsession_id: " + session + "\n"
        )):
            ok, result, sid = gateway.dispatch("secretary", "Answer my question", None, 10)
        self.assertEqual((ok, result, sid), (True, "My response", session))
        self.assertEqual(list(Path(self.tmp.name).glob(".prompt-*")), [])

    def test_resumed_id_forwarded_to_original_cli(self):
        sid = "abcd1234-1234-1234-1234-123456789012"
        def invoke(cmd, **kwargs):
            self.assertEqual(cmd[cmd.index("--resume")+1], sid)
            self.assertEqual(cmd[cmd.index("-m")+1], "code-flash")
            return subprocess.CompletedProcess(cmd, 0, "Continued", "session_id: " + sid + "\n")
        with patch.object(gateway.subprocess, "run", side_effect=invoke):
            self.assertEqual(gateway.dispatch("secretary", "Answer my question", sid, 10, "code-flash"),
                             (True, "Continued", sid))

    def test_stdout_receipt_compatibility_without_user_visible_leak(self):
        sid = "abcd1234-1234-1234-1234-123456789012"
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="Text\nsession_id: " + sid + "\n",
        )):
            self.assertEqual(gateway.dispatch("secretary", "Answer my question", None, 10),
                             (True, "Text", sid))

    def test_nonzero_exit_never_claims_success_with_partial_stdout(self):
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="partial text", diagnostics="process crashed", returncode=42,
        )):
            result = gateway.dispatch("secretary", "Answer my question", None, 10)
        self.assertEqual(result, (False, "process crashed", None))

    def test_timeout_never_leaks_or_keeps_prompt_file(self):
        with patch.object(gateway.subprocess, "run", side_effect=subprocess.TimeoutExpired(
            "hermes", timeout=10
        )):
            result = gateway.dispatch("secretary", "Answer my question", None, 10)
        self.assertEqual(result[0], False)
        self.assertIsNone(result[2])
        self.assertEqual(list(Path(self.tmp.name).glob(".prompt-*")), [])

    def test_unrecognized_session_metadata_does_not_enter_native_resume(self):
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="Ordinary text", diagnostics="session_id: !unexpected\n"
        )):
            self.assertEqual(gateway.dispatch("secretary", "Answer my question", None, 10),
                             (True, "Ordinary text", None))


class InstalledGatewayRoutingTests(unittest.TestCase):
    def setUp(self):
        self.conf = gateway.DEFAULT_CONF

    def test_explicit_unbound_role_alias(self):
        self.assertEqual(
            gateway.route(self.conf, text="engineering: Please inspect this",
                          channel="C0CBC6AEAQZ", user="U0BRET6191C", is_dm=False),
            ("engineering", "alias:engineering"),
        )

    def test_bound_thread_prioritizes_existing_role_even_if_alias_changes(self):
        # A cross-role migration cannot silently steal an existing thread.
        self.assertEqual(
            gateway.route(self.conf, text="engineering: one more question",
                          channel="C0CBC6AEAQZ", user="U0BRET6191C",
                          is_dm=False, binding="secretary"),
            ("secretary", "thread-binding"),
        )

    def test_nine_routable_profiles_with_one_app(self):
        self.assertEqual(len(gateway.routable(self.conf)), 9)
        self.assertEqual(len(self.conf["apps"]), 1)


if __name__ == "__main__":
    unittest.main()
