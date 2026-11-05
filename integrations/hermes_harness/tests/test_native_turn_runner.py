"""Deterministic no-network execution and confinement tests for native canary."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.native_turn_runner import (
    _capture_bounded_child, _private_child_environment,
    assert_role_service_cgroup, run_native_canary,
)
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal


def _fake_script(mode="good"):
    return '''#!/usr/bin/env python3
import json
import re
import sys
import time
mode = MODE_TOKEN
if mode == "sleep":
    time.sleep(3)
    sys.exit(0)
if mode == "oversize":
    sys.stdout.write("x" * 70000)
    sys.stdout.flush()
    sys.exit(0)
if mode == "malformed":
    sys.stdout.write("not-json\\n")
    sys.stderr.write("\\nsession_id: session-source-test\\n")
    sys.exit(0)
role = sys.argv[sys.argv.index("-p") + 1]
marker = re.search(r"MMX-CANARY-[A-F0-9]{32}", sys.stdin.read()).group(0)
# Protocol-source fixture: gateway emitter initializes before session binding.
events = [
    {"type": "system", "subtype": "init", "model": "", "session_id": ""},
    {"type": "text", "text": marker},
    {"type": "result", "exit_code": 0, "text": marker, "session_id": "session-source-test",
     "tokens": {"input": 19, "output": 14, "total": 33}},
]
for event in events:
    sys.stdout.write(json.dumps(event) + "\\n")
sys.stdout.flush()
sys.stderr.write("Session: session-source-test\\n\\nsession_id: session-source-test\\n")
if mode == "private_stderr":
    sys.stderr.write("Authorization: PRIVATE_SECRET_SENTINEL\\n")
'''.replace("MODE_TOKEN", repr(mode))


class CgroupAndEnvironmentTests(unittest.TestCase):
    def test_exact_service_cgroup_matches(self):
        assert_role_service_cgroup(
            "mmsecretary",
            raw="0::/system.slice/hermes-runtime-mmsecretary.service\n",
        )
        assert_role_service_cgroup(
            "mmmeta",
            raw="0::/system.slice/hermes-runtime-mmmeta.service/child.slice\n",
        )

    def test_wrong_or_forged_cgroup_refuses(self):
        bad = [
            "0::/user.slice/user-1000.slice/user@1000.service/app.slice/hermes-runtime-mmsecretary.service\n",
            "0::/user.slice/hermes-runtime-mmsecretary.service/child.slice\n",
            "0::/system.slice/unrelated.service/hermes-runtime-mmsecretary.service\n",
            "1:name=systemd:/system.slice/hermes-runtime-mmsecretary.service\n",
            "0::/user.slice/hermes-runtime-mmmeta.service\n",
            "0::/user.slice/hermes-runtime-mmsecretary.service-fake\n",
            "0::/unrelated/sol-shell.scope\n",
            "0::/user.slice/hermes-runtime-mmsecretary.service.extra\n",
            "",
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(RuntimeRefusal) as cm:
                    assert_role_service_cgroup("mmsecretary", raw=raw)
                self.assertEqual(cm.exception.code, "NATIVE_CANARY_CGROUP_UNQUALIFIED")

    def test_external_proxy_and_extraneous_bearers_refuse(self):
        with tempfile.TemporaryDirectory() as raw:
            profile = compose_profile(
                "mmsecretary", state_dir=Path(raw) / "state",
                secrets_file=Path(raw) / "secret.env", hermes_home=Path(raw) / "home",
            )
            env = {
                "HERMES_HOME": str(profile.hermes_home),
                "BYTEPLUS_MODELARK_API_KEY": "synthetic-not-live",
                "HTTPS_PROXY": "http://127.0.0.2:18651",
                "NO_PROXY": "127.0.0.1,localhost,127.0.0.2",
            }
            self.assertEqual(_private_child_environment(profile, env), env)
            for key, value in [
                ("HTTPS_PROXY", "http://evil.example:18651"),
                ("HTTPS_PROXY", "http://127.0.0.1:18651"),
                ("HTTPS_PROXY", "http://127.0.0.3:18651"),
                ("HTTPS_PROXY", "http://127.0.0.1:99999"),
                ("NO_PROXY", "*"),
                ("NO_PROXY", "127.0.0.1,localhost"),
                ("HERMES_GATEWAY_TOKEN", "PRIVATE-NOT-LIVE"),
                ("HERMES_SLACK_BOT_TOKEN", "PRIVATE-NOT-LIVE"),
                ("HTTP_PROXY", "http://127.0.0.1:1234"),
                ("ZAI_API_KEY", "SYNTHETIC_WRONG_ROLE_KEY"),
                ("HERMES_STUB_TOOLS", "/private/rogue-file"),
                ("EXTRA_SECRET_AUTH", "PRIVATE_AUTH_SENTINEL"),
            ]:
                bad = {**env, key: value}
                with self.subTest(key=key, value=value):
                    with self.assertRaises(RuntimeRefusal):
                        _private_child_environment(profile, bad)


class SyntheticRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hermes-native-canary-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "hermeshome"
        self.home.mkdir()
        self.bin = self.root / "fake-hermes"
        self.profile = compose_profile(
            "mmsecretary", state_dir=self.root / "state",
            secrets_file=self.root / "role.secrets.env", hermes_home=self.home,
        )
        self.child_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C",
            "HOME": str(self.home),
            "HERMES_HOME": str(self.home),
            "BYTEPLUS_MODELARK_API_KEY": "SOURCE_ONLY_PRIVATE_FIXTURE_KEY",
            "HTTPS_PROXY": "http://127.0.0.2:18651",
            "NO_PROXY": "127.0.0.1,localhost,127.0.0.2",
        }

    def _write(self, mode="good"):
        self.bin.write_text(_fake_script(mode), encoding="utf-8")
        self.bin.chmod(0o700)

    def _run(self, **kwargs):
        with mock.patch(
            "integrations.hermes_harness.native_turn_runner.assert_role_service_cgroup",
            return_value=None,
        ):
            return run_native_canary(
                self.profile, hermes_bin=self.bin, model_child_env=self.child_env,
                timeout_seconds=kwargs.get("timeout_seconds", 5.0),
            )

    def test_valid_fake_child_observed_without_live_claim(self):
        self._write()
        receipt = self._run()
        self.assertEqual(receipt["status"], "PASS_CHILD_OUTPUT_OBSERVATION_ONLY")
        self.assertEqual(receipt["issue_codes"], [])
        self.assertTrue(receipt["host_service_cgroup_membership_observed"])
        self.assertFalse(receipt["provider_authentication_verified"])
        self.assertFalse(receipt["provider_tls_verified"])
        self.assertFalse(receipt["bpf_network_deny_verified"])
        self.assertFalse(receipt["live_slack_delivery_verified"])
        self.assertNotIn("role_bot_slack_delivery_verified", receipt)
        self.assertNotIn("SOURCE_ONLY_PRIVATE_FIXTURE_KEY", str(receipt))

    def test_meta_role_uses_its_selected_model_and_only_zai_key(self):
        self.profile = compose_profile(
            "mmmeta", state_dir=self.root / "meta-state",
            secrets_file=self.root / "meta.secrets.env", hermes_home=self.home,
        )
        self.child_env.pop("BYTEPLUS_MODELARK_API_KEY")
        self.child_env["ZAI_API_KEY"] = "SOURCE_ONLY_META_PROVIDER_FIXTURE"
        self.child_env["HTTPS_PROXY"] = "http://127.0.0.3:18652"
        self.child_env["NO_PROXY"] = "127.0.0.1,localhost,127.0.0.3"
        self._write()
        receipt = self._run()
        self.assertEqual(receipt["status"], "PASS_CHILD_OUTPUT_OBSERVATION_ONLY")
        self.assertEqual(receipt["role"], "mmmeta")
        self.assertEqual(receipt["expected_model"], "glm-5.3")
        self.assertIsNone(receipt["observed_model"])
        self.assertFalse(receipt["model_identity_verified"])
        self.assertNotIn("SOURCE_ONLY_META_PROVIDER_FIXTURE", str(receipt))

    def test_cross_role_key_refused_before_child_spawn(self):
        self._write()
        self.child_env["ZAI_API_KEY"] = "SYNTHETIC_WRONG_ROLE"
        with mock.patch(
            "integrations.hermes_harness.native_turn_runner._capture_bounded_child",
            side_effect=AssertionError("unapproved mixed account credentials reached child"),
        ) as spawn:
            with self.assertRaises(RuntimeRefusal) as cm:
                self._run()
            self.assertEqual(cm.exception.code, "NATIVE_CANARY_ENV_UNQUALIFIED")
            spawn.assert_not_called()

    def test_malformed_json_is_blocked_not_a_canary(self):
        self._write("malformed")
        receipt = self._run()
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("STREAM_INVALID", receipt["issue_codes"])

    def test_stderr_secret_is_not_returned(self):
        self._write("private_stderr")
        receipt = self._run()
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertNotIn("PRIVATE_SECRET_SENTINEL", str(receipt))
        self.assertIn("SESSION_STDERR_MISMATCH", receipt["issue_codes"])

    def test_large_output_kills_child_without_unbounded_capture(self):
        self._write("oversize")
        with self.assertRaises(RuntimeRefusal) as cm:
            self._run()
        self.assertEqual(cm.exception.code, "NATIVE_CANARY_OUTPUT_TOO_LARGE")

    def test_timeout_kills_child_without_implicit_retry(self):
        self._write("sleep")
        with self.assertRaises(RuntimeRefusal) as cm:
            self._run(timeout_seconds=1.1)
        self.assertEqual(cm.exception.code, "NATIVE_CANARY_TIMEOUT")

    def test_cgroup_refuses_before_child_spawn(self):
        self._write()
        with mock.patch(
            "integrations.hermes_harness.native_turn_runner.assert_role_service_cgroup",
            side_effect=RuntimeRefusal("NATIVE_CANARY_CGROUP_UNQUALIFIED"),
        ):
            with mock.patch(
                "integrations.hermes_harness.native_turn_runner._capture_bounded_child",
                side_effect=AssertionError("child must not be spawned"),
            ) as proc:
                with self.assertRaises(RuntimeRefusal) as cm:
                    run_native_canary(
                        self.profile, hermes_bin=self.bin,
                        model_child_env=self.child_env,
                    )
                self.assertEqual(cm.exception.code, "NATIVE_CANARY_CGROUP_UNQUALIFIED")
                proc.assert_not_called()

    def test_without_hermes_binary_refuses(self):
        with self.assertRaises(RuntimeRefusal) as cm:
            self._run()
        self.assertEqual(cm.exception.code, "NATIVE_CANARY_PROFILE_UNQUALIFIED")




class ExitedLeaderCleanupTests(unittest.TestCase):
    def test_exited_leader_group_is_signalled_before_reaping(self):
        from integrations.hermes_harness.native_turn_runner import _terminate_group
        import signal
        proc = mock.Mock()
        proc.pid = 123456
        proc.returncode = None
        proc.poll.return_value = 0
        with mock.patch("integrations.hermes_harness.native_turn_runner.os.killpg") as kill:
            _terminate_group(proc)
        kill.assert_called_once_with(proc.pid, signal.SIGKILL)
        proc.poll.assert_not_called()
        proc.wait.assert_called_once_with(timeout=3)

    def test_timeout_and_overflow_terminate_group_after_leader_exit(self):
        import json
        import signal
        import subprocess
        import sys
        import time
        for mode, expected in (("timeout", "NATIVE_CANARY_TIMEOUT"),
                               ("overflow", "NATIVE_CANARY_OUTPUT_TOO_LARGE")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="hermes-owned-group-") as td:
                root = Path(td)
                pidfile = root / "child.json"
                script = root / "fixture.py"
                script.write_text(
                    "import os,json,time,sys\np=os.fork()\n"
                    "if p==0:\n"
                    " open(sys.argv[1], 'w').write(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp()}))\n"
                    " time.sleep(0.25)\n"
                    " if sys.argv[2]=='overflow':\n  os.write(1,b'x'*70000)\n"
                    " time.sleep(8)\n os._exit(0)\n"
                    "time.sleep(0.1)\nos._exit(0)\n", encoding="utf-8")
                try:
                    with self.assertRaises(RuntimeRefusal) as cm:
                        _capture_bounded_child(
                            [sys.executable, str(script), str(pidfile), mode], b"fixture",
                            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                            cwd=root, timeout_seconds=1.1)
                    self.assertEqual(cm.exception.code, expected)
                    owned = json.loads(pidfile.read_text())
                    deadline = time.monotonic() + 2
                    live = True
                    while time.monotonic() < deadline:
                        result = subprocess.run(
                            ["ps", "-p", str(owned["pid"]), "-o", "stat="],
                            capture_output=True, text=True, timeout=2)
                        state = result.stdout.strip()
                        live = bool(state) and not state.startswith("Z")
                        if not live:
                            break
                        time.sleep(0.02)
                    self.assertFalse(live, "owned descendant survived bounded capture cleanup")
                finally:
                    # Only this test's exact child is cleaned; no host/service PID.
                    if pidfile.exists():
                        owned = json.loads(pidfile.read_text())
                        try:
                            if os.getpgid(owned["pid"]) == owned["pgid"]:
                                os.kill(owned["pid"], signal.SIGKILL)
                        except ProcessLookupError:
                            pass


if __name__ == "__main__":
    unittest.main()
