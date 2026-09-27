"""Audit regressions for local setup failures; no network or real credentials."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "integrations/paper_desktop/direct_service.py"


class DirectPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        spec = importlib.util.spec_from_file_location("direct_preflight_fixture", SOURCE)
        self.svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.svc)
        self.binary = self.home / "client"
        self.binary.write_text("#!/bin/sh\necho CLIENT_MUST_NOT_START\nexit 93\n")
        self.binary.chmod(0o700)
        self.root = self.home / "bundle"
        self.env = self.svc.clean_env(dict(os.environ))
        self.env["HOME"] = str(self.home)
        with patch.dict(os.environ, {"HOME": str(self.home)}):
            self.svc.stage(self.root, python=Path(sys.executable).resolve(),
                           tunnel_client=self.binary, source_revision="0" * 40)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, action):
        return subprocess.run([sys.executable, "-I", str(self.root / "runtime/direct_service.py"),
                               action, "--root", str(self.root)],
                              capture_output=True, text=True, env=self.env, timeout=8)

    def bind_fixture(self):
        with patch.dict(os.environ, {"HOME": str(self.home)}):
            self.svc.bind(self.root, "tunnel_" + "b" * 32, "business-fixture")

    def assert_held(self, expected):
        result = self.cli("launch")
        self.assertEqual(result.returncode, 0, "launchd would keep relaunching a refused preflight")
        self.assertEqual(result.stdout, "")
        value = json.loads(result.stderr)
        self.assertEqual(value["state"], expected)
        self.assertEqual(value["execution_state"], "NOT_STARTED")
        self.assertFalse(value["retry_allowed"])
        self.assertFalse(value["automatic_restart_allowed"])

    def test_launch_agent_uses_non_restarting_preflight_entrypoint(self):
        plist = plistlib.loads((self.root / ("service/" + self.svc.LABEL + ".plist")).read_bytes())
        self.assertIn("launch", plist["ProgramArguments"])
        self.assertEqual(plist["KeepAlive"], {"SuccessfulExit": False})

    def test_unbound_service_does_not_auto_restart(self):
        self.assert_held("BINDING_REQUIRED")

    def test_missing_runtime_key_does_not_auto_restart(self):
        self.bind_fixture()
        self.assert_held("RUNTIME_KEY_MISSING")

    def test_changed_source_does_not_auto_restart(self):
        target = self.root / "runtime/bridge.py"
        target.write_text(target.read_text() + "\n# fixture drift\n")
        self.assert_held("HASH_MISMATCH")

    def test_runtime_key_fifo_stops_supervised_start_without_hanging(self):
        self.bind_fixture()
        os.mkfifo(self.root / "secrets/runtime-key", mode=0o600)
        self.assert_held("PRIVATE_FILE_REQUIRED")

    def test_manual_run_still_signals_failure(self):
        result = self.cli("run")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["state"], "BINDING_REQUIRED")

    def test_launch_agent_creates_private_logs(self):
        plist = plistlib.loads((self.root / ("service/" + self.svc.LABEL + ".plist")).read_bytes())
        self.assertEqual(plist.get("Umask"), 0o077)

    def test_supervised_start_rejects_a_different_running_python(self):
        self.bind_fixture()
        error = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(sys, "executable", str(self.home / "different-python")), \
             patch.object(sys, "argv", ["direct_service.py", "launch", "--root", str(self.root)]), \
             contextlib.redirect_stderr(error):
            status = self.svc.main()
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(error.getvalue())["state"], "RUNTIME_INTERPRETER_MISMATCH")

    def test_serve_checks_running_python_before_loading_sdk(self):
        with patch.dict(os.environ, self.env, clear=True), \
             patch.object(sys, "executable", str(self.home / "different-python")), \
             patch.object(self.svc, "_sdk", side_effect=self.svc.Refusal("SDK_REACHED_BEFORE_IDENTITY")):
            with self.assertRaisesRegex(self.svc.Refusal, "RUNTIME_INTERPRETER_MISMATCH"):
                self.svc.serve(self.root)

    def test_private_read_rejects_fifo_without_waiting_for_a_writer(self):
        self.check_fifo("_read", "PRIVATE_FILE_REQUIRED")

    def test_executable_probe_rejects_fifo_without_waiting_for_a_writer(self):
        self.check_fifo("_binary", "EXECUTABLE_REQUIRED")

    def check_fifo(self, function, expected):
        fifo = self.home / function
        os.mkfifo(fifo, mode=0o600)
        code = (
            "import importlib.util,pathlib,sys; "
            "s=importlib.util.spec_from_file_location('fixture',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
            "\ntry: getattr(m,sys.argv[2])(pathlib.Path(sys.argv[3]))"
            "\nexcept m.Refusal as e: print(str(e))"
        )
        try:
            result = subprocess.run([sys.executable, "-I", "-c", code, str(SOURCE), function, str(fifo)],
                                    capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            self.fail("Special file blocked before regular-file validation")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)

    def test_directory_is_a_typed_file_refusal(self):
        with self.assertRaisesRegex(self.svc.Refusal, "PRIVATE_FILE_REQUIRED"):
            self.svc._read(self.home)


if __name__ == "__main__":
    unittest.main()
