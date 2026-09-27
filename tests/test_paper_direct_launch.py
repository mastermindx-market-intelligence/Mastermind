"""Real launcher/exec tests using a non-networking fake client and fixture key.

HOME, service state and credentials are temporary. No real tunnel or host service
is launched. Every child is joined in this test and has a bounded cleanup path.
"""
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from paper_direct_test_support import PrivatePython, has_pinned_mcp_sdk

SOURCE = Path(__file__).resolve().parents[1] / "integrations/paper_desktop/direct_service.py"


@unittest.skipUnless(has_pinned_mcp_sdk(), "Dedicated mcp==1.30.0 SDK lane required")
class DirectLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._python_fixture = PrivatePython()
        cls.private_python = cls._python_fixture.python

    @classmethod
    def tearDownClass(cls):
        cls._python_fixture.close()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.children = []
        spec = importlib.util.spec_from_file_location("paper_launch_fixture", SOURCE)
        self.svc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.svc)
        self.binary = self.home / "fixture-client"
        self.binary.write_text(
            "#!" + str(self.private_python) + "\n"
            "import json, os, select, sys\n"
            "names=['OPENAI_API_KEY','OPENAI_ADMIN_KEY','CONTROL_PLANE_API_KEY',"
            "'CONTROL_PLANE_TUNNEL_ID','MCP_COMMAND','PYTHONPATH','HTTPS_PROXY']\n"
            "print(json.dumps({'state':'FIXTURE_STARTED','argv':sys.argv[1:],"
            "'inherited_sensitive_names':[k for k in names if k in os.environ],"
            "'home':os.environ.get('HOME')}),flush=True)\n"
            "ready,_,_=select.select([sys.stdin],[],[],12)\n"
            "if ready: sys.stdin.readline()\n"
        )
        self.binary.chmod(0o700)
        self.env = self.svc.clean_env(dict(os.environ))
        self.env["HOME"] = str(self.home)

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                try:
                    child.communicate("stop\n", timeout=3)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.communicate(timeout=3)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None:
                    stream.close()
        self.tmp.cleanup()

    def stage(self, name):
        root = self.home / name
        with patch.dict(os.environ, {"HOME": str(self.home)}):
            self.svc.stage(root, python=self.private_python, tunnel_client=self.binary,
                           source_revision="0" * 40, allow_write=True, allow_prepare=True)
            self.svc.bind(root, "tunnel_" + "b" * 32, "workspace-fixture-business")
        # Deliberately fake and local. The fixture binary never contacts OpenAI.
        key = root / "secrets/runtime-key"
        key.write_text("fixture-only-not-a-real-credential")
        key.chmod(0o600)
        return root

    def start(self, root, extra_env=None, action="run"):
        child = subprocess.Popen([str(self.private_python), "-I", str(root / "runtime/direct_service.py"),
                                  action, "--root", str(root)],
                                 env=dict(self.env, **(extra_env or {})), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        return child

    def started(self, child):
        ready, _, _ = select.select([child.stdout], [], [], 8)
        self.assertTrue(ready, "Fixture launcher did not become observable")
        line = child.stdout.readline()
        if not line:
            self.fail("Launcher exited before fixture startup: " + child.stderr.read())
        value = json.loads(line)
        self.assertEqual(value["state"], "FIXTURE_STARTED")
        return value

    def finish(self, child):
        child.communicate("stop\n", timeout=3)
        self.assertEqual(child.returncode, 0)

    def test_supervised_entrypoint_executes_official_run_shape(self):
        root = self.stage("supervised")
        child = self.start(root, action="launch")
        value = self.started(child)
        self.assertEqual(value["argv"], ["run", "--profile-file", str(root / "connection/profile.yaml")])
        self.finish(child)

    def test_supervised_duplicate_stays_stopped_without_displacing_first(self):
        root = self.stage("supervised")
        first = self.start(root, action="launch")
        self.started(first)
        second = self.start(root, action="launch")
        out, err = second.communicate(timeout=8)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(out, "")
        value = json.loads(err)
        self.assertEqual(value["state"], "ALREADY_RUNNING")
        self.assertEqual(value["execution_state"], "NOT_STARTED")
        self.assertFalse(value["automatic_restart_allowed"])
        self.assertIsNone(first.poll(), "Existing client was displaced")
        self.finish(first)

    def test_exec_strips_other_account_and_tunnel_environment(self):
        root = self.stage("bundle")
        child = self.start(root, {name: "fixture-not-real" for name in (
            "OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "CONTROL_PLANE_API_KEY",
            "CONTROL_PLANE_TUNNEL_ID", "MCP_COMMAND", "PYTHONPATH", "HTTPS_PROXY")})
        value = self.started(child)
        self.assertEqual(value["inherited_sensitive_names"], [])
        self.assertEqual(value["home"], str(self.home))
        self.assertEqual(value["argv"], ["run", "--profile-file", str(root / "connection/profile.yaml")])
        self.finish(child)

    def test_duplicate_client_refused_then_restart_allowed_after_exit(self):
        root = self.stage("bundle")
        first = self.start(root)
        self.started(first)
        second = self.start(root)
        out, err = second.communicate(timeout=8)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err)["state"], "ALREADY_RUNNING")
        self.finish(first)
        replacement = self.start(root)
        self.started(replacement)
        self.finish(replacement)

    def test_two_bundle_versions_still_share_one_service_singleton(self):
        one = self.stage("version-one")
        two = self.stage("version-two")
        first = self.start(one)
        self.started(first)
        second = self.start(two)
        out, err = second.communicate(timeout=8)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err)["state"], "ALREADY_RUNNING")
        self.finish(first)


if __name__ == "__main__":
    unittest.main()
