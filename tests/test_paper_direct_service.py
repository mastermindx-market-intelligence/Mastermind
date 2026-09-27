"""Offline Paper tunnel installation tests. These do not prove ChatGPT enrollment."""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "integrations/paper_desktop/direct_service.py"


class DirectServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.target = self.home / "paper-business"
        self.binary = self.home / "tunnel-client"
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        self._service = None

    def tearDown(self):
        self.tmp.cleanup()

    def service(self):
        self.assertTrue(MODULE.is_file(), "Paper direct infrastructure is not implemented")
        if self._service is None:
            spec = importlib.util.spec_from_file_location("paper_direct_under_test", MODULE)
            self._service = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._service)
        return self._service

    def stage(self, **kw):
        params = dict(python=Path(sys.executable).resolve(), tunnel_client=self.binary,
                      source_revision="a" * 40, allow_write=True)
        params.update(kw)
        return self.service().stage(self.target, **params)

    def test_stage_is_inert_business_only(self):
        receipt = self.stage()
        self.assertEqual(receipt["state"], "STAGED_NOT_ENROLLED")
        self.assertEqual(receipt["target_plan"], "Business")
        self.assertFalse(receipt["production_acceptance"])
        self.assertFalse(receipt["service_loaded"])
        self.assertFalse((self.target / "connection").exists())
        self.assertFalse((self.target / "secrets/runtime-key").exists())
        self.assertFalse((self.home / "Library/LaunchAgents").exists())

    def test_bridge_is_reused_byte_for_byte(self):
        self.stage()
        self.assertEqual((self.target / "runtime/bridge.py").read_bytes(),
                         (ROOT / "integrations/paper_desktop/bridge.py").read_bytes())

    def test_read_only_is_default(self):
        receipt = self.stage(allow_write=False)
        self.assertEqual(receipt["tools"], ["paper_catalog", "paper_inspect", "paper_read"])
        self.assertFalse(receipt["allow_write"])

    def test_write_tool_is_explicit(self):
        receipt = self.stage()
        self.assertEqual(receipt["tools"], ["paper_catalog", "paper_edit", "paper_inspect", "paper_read"])

    def test_existing_install_is_not_overwritten(self):
        self.stage()
        original = (self.target / "INSTALLATION.json").read_bytes()
        with self.assertRaisesRegex(self.service().Refusal, "DESTINATION_EXISTS"):
            self.stage()
        self.assertEqual(original, (self.target / "INSTALLATION.json").read_bytes())

    def test_symlink_destination_refused(self):
        self.target.symlink_to(self.home / "elsewhere")
        with self.assertRaises(self.service().Refusal):
            self.stage()
        self.assertFalse((self.home / "elsewhere").exists())

    def test_symlink_parent_refused(self):
        actual = self.home / "actual"
        actual.mkdir()
        link = self.home / "link"
        link.symlink_to(actual, target_is_directory=True)
        self.target = link / "bundle"
        with self.assertRaisesRegex(self.service().Refusal, "SYMLINK"):
            self.stage()
        self.assertFalse((actual / "bundle").exists())

    def test_source_tamper_is_rejected(self):
        self.stage()
        p = self.target / "runtime/bridge.py"
        p.write_text(p.read_text() + "\n# drift\n")
        with self.assertRaisesRegex(self.service().Refusal, "HASH_MISMATCH"):
            self.service().verify(self.target)

    def test_manifest_file_set_cannot_shrink(self):
        self.stage()
        p = self.target / "INSTALLATION.json"
        value = json.loads(p.read_text())
        value["files"].pop("runtime/bridge.py")
        p.write_text(json.dumps(value))
        with self.assertRaisesRegex(self.service().Refusal, "MANIFEST"):
            self.service().verify(self.target)

    def test_private_modes_are_enforced(self):
        self.stage()
        p = self.target / "runtime/mcp_server.py"
        p.chmod(0o644)
        with self.assertRaisesRegex(self.service().Refusal, "PRIVATE_FILE"):
            self.service().verify(self.target)

    def test_binary_replacement_is_rejected(self):
        self.stage()
        self.binary.write_text("#!/bin/sh\nexit 1\n")
        with self.assertRaisesRegex(self.service().Refusal, "BINARY_CHANGED"):
            self.service().verify(self.target)

    def test_profile_is_stdio_and_loopback_without_inline_secret(self):
        self.stage()
        text = self.service().profile_text(self.target, "tunnel_" + "b" * 32)
        self.assertIn('listen_addr: "127.0.0.1:0"', text)
        self.assertIn("stdio_send_initialized_notification: true", text)
        self.assertIn("max_concurrent_requests: 1", text)
        self.assertIn("file:", text)
        self.assertIn("secrets/runtime-key", text)
        self.assertNotIn("server_url", text)
        self.assertNotIn("harpoon", text)
        self.assertNotIn("sk-", text)
        self.assertNotIn("29979", text)

    def test_unsafe_tunnel_id_is_refused_before_write(self):
        self.stage()
        with self.assertRaisesRegex(self.service().Refusal, "TUNNEL_ID"):
            self.service().bind(self.target, "tunnel_bad\ncontrol_plane: evil", "workspace-business")
        self.assertFalse((self.target / "connection").exists())

    def test_workspace_binding_is_required(self):
        self.stage()
        with self.assertRaisesRegex(self.service().Refusal, "WORKSPACE_ID"):
            self.service().bind(self.target, "tunnel_" + "b" * 32, "")
        self.assertFalse((self.target / "connection").exists())

    def test_binding_is_secretless_and_never_replaces_existing(self):
        self.stage()
        svc = self.service()
        value = svc.bind(self.target, "tunnel_" + "b" * 32, "workspace-business")
        self.assertEqual(value["state"], "BOUND_NOT_ACTIVATED")
        self.assertFalse((self.target / "secrets/runtime-key").exists())
        with self.assertRaisesRegex(svc.Refusal, "BINDING_EXISTS"):
            svc.bind(self.target, "tunnel_" + "c" * 32, "workspace-other")
        self.assertEqual(svc.verify_binding(self.target)["workspace_id"], "workspace-business")

    def test_binding_profile_tamper_is_refused(self):
        self.stage()
        svc = self.service()
        svc.bind(self.target, "tunnel_" + "b" * 32, "workspace-business")
        path = self.target / "connection/profile.yaml"
        path.write_text(path.read_text().replace("127.0.0.1:0", "0.0.0.0:8080"))
        with self.assertRaisesRegex(svc.Refusal, "PROFILE_CHANGED"):
            svc.verify_binding(self.target)

    def test_launch_agent_uses_existing_supervisor_not_a_daemon_plane(self):
        self.stage()
        value = plistlib.loads((self.target / "service/com.mastermind.paper-direct.business.plist").read_bytes())
        self.assertEqual(value["Label"], "com.mastermind.paper-direct.business")
        self.assertEqual(value["KeepAlive"], {"SuccessfulExit": False})
        self.assertIn("run", value["ProgramArguments"])
        self.assertEqual(set(value["EnvironmentVariables"]), {"HOME", "PATH"})
        self.assertNotIn("OPENAI_ADMIN_KEY", str(value))
        self.assertNotIn("CONTROL_PLANE_API_KEY", str(value))

    def test_ambient_tunnel_and_provider_credentials_are_not_inherited(self):
        env = self.service().clean_env({"HOME": str(self.home), "PATH": "/malicious", "USER": "test",
              "CONTROL_PLANE_API_KEY": "secret", "OPENAI_API_KEY": "secret", "OPENAI_ADMIN_KEY": "secret",
              "CONTROL_PLANE_TUNNEL_ID": "wrong", "MCP_COMMAND": "evil", "PYTHONPATH": "/evil", "HTTPS_PROXY": "http://evil"})
        self.assertEqual(env["HOME"], str(self.home))
        self.assertNotEqual(env["PATH"], "/malicious")
        for key in ("CONTROL_PLANE_API_KEY", "OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "CONTROL_PLANE_TUNNEL_ID", "MCP_COMMAND", "PYTHONPATH", "HTTPS_PROXY"):
            self.assertNotIn(key, env)

    def test_runtime_key_is_a_separate_final_gate(self):
        self.stage()
        with self.assertRaisesRegex(self.service().Refusal, "RUNTIME_KEY_MISSING"):
            self.service().verify_runtime_key(self.target)

    def test_admin_key_is_never_accepted_for_daemon(self):
        self.stage()
        key = self.target / "secrets/runtime-key"
        key.write_text("sk-admin-example-not-real")
        key.chmod(0o600)
        with self.assertRaisesRegex(self.service().Refusal, "ADMIN_KEY_NOT_RUNTIME"):
            self.service().verify_runtime_key(self.target)

    def test_unsafe_secret_permissions_refused_without_echoing_key(self):
        self.stage()
        key = self.target / "secrets/runtime-key"
        key.write_text("sk-example-not-real")
        key.chmod(0o644)
        try:
            self.service().verify_runtime_key(self.target)
        except self.service().Refusal as exc:
            self.assertNotIn("sk-example", str(exc))
            self.assertIn("PRIVATE_FILE", str(exc))
        else:
            self.fail("World-readable runtime key was accepted")

    def test_process_guard_refuses_second_client(self):
        guard = self.home / "state"
        with self.service().service_lock(guard):
            with self.assertRaisesRegex(self.service().Refusal, "ALREADY_RUNNING"):
                with self.service().service_lock(guard):
                    self.fail("second service acquired the lock")

    def test_binding_symlink_is_never_followed(self):
        self.stage()
        (self.target / "connection").symlink_to(self.home / "other")
        with self.assertRaises(self.service().Refusal):
            self.service().bind(self.target, "tunnel_" + "b" * 32, "workspace-business")
        self.assertFalse((self.home / "other").exists())

    def test_manifest_symlink_is_refused(self):
        self.stage()
        path = self.target / "INSTALLATION.json"
        other = self.home / "manifest"
        path.rename(other)
        path.symlink_to(other)
        with self.assertRaisesRegex(self.service().Refusal, "SYMLINK"):
            self.service().verify(self.target)

    def test_duplicate_manifest_keys_are_refused(self):
        self.stage()
        path = self.target / "INSTALLATION.json"
        path.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(self.service().Refusal, "DUPLICATE_JSON_KEY"):
            self.service().verify(self.target)

    def test_hardlinked_runtime_key_is_refused(self):
        self.stage()
        path = self.target / "secrets/runtime-key"
        path.write_text("sk-test-only")
        path.chmod(0o600)
        os.link(path, self.home / "second-key-link")
        with self.assertRaisesRegex(self.service().Refusal, "PRIVATE_FILE"):
            self.service().verify_runtime_key(self.target)

    def test_runtime_key_symlink_is_refused(self):
        self.stage()
        (self.target / "secrets/runtime-key").symlink_to(self.home / "missing-key")
        with self.assertRaises(self.service().Refusal):
            self.service().verify_runtime_key(self.target)

    def test_source_receipt_cannot_claim_live_acceptance(self):
        self.stage()
        path = self.target / "INSTALLATION.json"
        value = json.loads(path.read_text())
        value["production_acceptance"] = True
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(self.service().Refusal, "MANIFEST"):
            self.service().verify(self.target)

    def test_runtime_sdk_dependency_set_is_captured(self):
        value = self.stage()
        self.assertIn("sdk_distributions", value)
        self.assertIsInstance(value["sdk_distributions"], dict)
        self.assertEqual(value["sdk_distributions"], self.service().sdk_distributions())

    def test_dependency_drift_is_rejected(self):
        self.stage()
        path = self.target / "INSTALLATION.json"
        value = json.loads(path.read_text())
        value["sdk_distributions"] = {"mcp": "unexpected-version"}
        path.write_text(json.dumps(value))
        self.assertTrue(callable(getattr(self.service(), "verify_sdk", None)), "SDK drift verification is missing")
        with self.assertRaisesRegex(self.service().Refusal, "SDK_DEPENDENCIES_CHANGED"):
            self.service().verify_sdk(self.target)

    def test_invalid_source_revision_refused_before_install(self):
        with self.assertRaisesRegex(self.service().Refusal, "SOURCE_REVISION"):
            self.stage(source_revision="moving-master")
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
