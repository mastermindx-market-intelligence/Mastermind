"""Verify only real, disabled native MCP is observed by the fresh supervisor.

No credentialed MCP, Slack, model, real host or network effect is exercised.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import shutil
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.native_mcp import render_disarmed_native_config
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.secrets import load_secrets
from integrations.hermes_runtime.supervisor import ServiceRuntime
from integrations.hermes_runtime.tests._support import CENSUS, STUB, write_secrets
from integrations.hermes_steward.client import ALLOWED_TOOLS


class NativeSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="mmx-hermes-native-supervisor-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.profile = replace(
            compose_profile("mmsecretary", state_dir=self.root / "state",
                            secrets_file=self.root / "gateway.secrets.env",
                            hermes_home=self.home, gateway_port=0, backend_port=0),
            tool_allowlist=frozenset({"clarify"}),
        )
        self.native = self.home / "profiles" / self.profile.role / "config.yaml"
        self.native.parent.mkdir(parents=True)
        self.native.write_text(render_disarmed_native_config(self.profile), encoding="utf-8")
        self.native.chmod(0o600)
        write_secrets(self.profile.secrets_file)
        self.stub = self.root / "stub-hermes"
        shutil.copyfile(STUB, self.stub)
        self.stub.chmod(0o700)
        self.census = self.root / "actual-cli-census.txt"
        self.census.write_text(
            CENSUS.read_text(encoding="utf-8").rstrip() +
            "\n\nMCP servers:\n  mastermind_steward  [include only: " +
            ", ".join(ALLOWED_TOOLS) + "]\n",
            encoding="utf-8",
        )

    def _runtime(self, profile=None) -> ServiceRuntime:
        return ServiceRuntime(
            profile or self.profile, load_secrets(self.profile.secrets_file),
            self.stub, extra_child_env={"HERMES_STUB_TOOLS":str(self.census)},
        )

    def test_disarmed_native_cli_registry_passes_without_fake_extension(self) -> None:
        runtime = self._runtime()
        self.assertEqual(runtime._expected_disabled_mcp(),
                         {"mastermind_steward": tuple(ALLOWED_TOOLS)})
        runtime._check_registry()
        self.assertEqual(runtime.profile.tool_allowlist, frozenset({"clarify"}))

    def test_named_byok_model_config_is_accepted_but_mcp_stays_disabled(self) -> None:
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok

        self.native.write_text(
            render_disarmed_native_byok(self.profile), encoding="utf-8"
        )
        self.assertEqual(
            self._runtime()._expected_disabled_mcp(),
            {"mastermind_steward": tuple(ALLOWED_TOOLS)},
        )
        changed = self.native.read_text().replace(
            "key_env: BYTEPLUS_MODELARK_API_KEY", "key_env: UNAPPROVED_KEY"
        )
        self.native.write_text(changed, encoding="utf-8")
        with self.assertRaises(RuntimeRefusal) as caught:
            self._runtime()._expected_disabled_mcp()
        self.assertEqual(caught.exception.code, "RUNTIME_NATIVE_CONFIG_DRIFT")

    def test_native_config_with_enabled_server_refuses_before_tool_execution(self) -> None:
        self.native.write_text(self.native.read_text().replace(
            "enabled: false", "enabled: true"), encoding="utf-8")
        with self.assertRaises(RuntimeRefusal) as caught:
            self._runtime()._expected_disabled_mcp()
        self.assertEqual(caught.exception.code, "RUNTIME_NATIVE_CONFIG_DRIFT")

    def test_missing_duplicate_and_world_readable_config_refuse(self) -> None:
        original = self.native.read_bytes()
        self.native.chmod(0o644)
        with self.assertRaises(RuntimeRefusal) as caught:
            self._runtime()._expected_disabled_mcp()
        self.assertEqual(caught.exception.code, "RUNTIME_NATIVE_CONFIG_UNSAFE")
        self.native.chmod(0o600)
        self.native.write_bytes(original + b"mcp_servers: {}\n")
        with self.assertRaises(RuntimeRefusal) as caught:
            self._runtime()._expected_disabled_mcp()
        self.assertEqual(caught.exception.code, "RUNTIME_NATIVE_CONFIG_DRIFT")

    def test_declared_but_uninstalled_python_extension_cannot_start(self) -> None:
        with self.assertRaises(RuntimeRefusal) as caught:
            self._runtime(compose_profile(
                "mmsecretary", state_dir=self.profile.state_dir,
                secrets_file=self.profile.secrets_file,
                hermes_home=self.profile.hermes_home,
                gateway_port=0, backend_port=0,
            ))._expected_disabled_mcp()
        self.assertEqual(caught.exception.code, "NATIVE_EXTENSION_NOT_INSTALLED")

    def test_extra_configured_mcp_cli_summary_refused(self) -> None:
        self.census.write_text(self.census.read_text() +
                               "  evil_server  [include only: unknown_tool]\n", encoding="utf-8")
        with self.assertRaises(RuntimeRefusal) as caught:
            self._runtime()._check_registry()
        self.assertIn("MCP_SERVER_SUMMARY_MISMATCH", caught.exception.code)

    def test_the_default_runtime_stays_disarmed(self) -> None:
        """No qualified consumer means no extension and no serving proof."""
        runtime = self._runtime()
        self.assertIsNone(runtime._consumer_publication())
        self.assertEqual(runtime._expected_disabled_mcp(),
                         {"mastermind_steward": tuple(ALLOWED_TOOLS)})
        self.assertFalse(runtime._extension_proved)
        status, payload = runtime.health_snapshot()
        self.assertEqual(status, 503)
        self.assertFalse(payload["native_extension_proved"])

    def _consumer_runtime(self):
        import types
        from integrations.hermes_harness.tests.test_native_executive_consumer import (
            OWNER, publication_document, publication_from_document, schema_digest)
        from integrations.hermes_harness.native_tool_registration import NATIVE_TOOL_SCHEMA
        from integrations.hermes_runtime import native_session_control
        document = publication_document()
        publication = publication_from_document(document)
        class Launch:
            recipe = {"vendor_root": "/nonexistent", "executive_consumer": document}
            owner = types.SimpleNamespace(root=Path("/qualified") / OWNER)
            def __init__(self):
                self.observed = []
            def observe_child(self, pid):
                self.observed.append(pid)
            def check(self):
                return None
        launch = Launch()
        runtime = self._runtime(replace(self.profile, gateway_backend="native-session-authority"))
        runtime._native_launch = launch
        runtime._native_home = self.home
        runtime._child = types.SimpleNamespace(pid=4242, poll=lambda: None)
        runtime.child_pid = 4242
        runtime._backend_ready = True
        target = {
            "profile_id": str(self.home), "principal_id": publication.session.principal_id,
            "session_id": "session-1", "instance_id": "instance-1", "authority_epoch": 1,
            "revision": 0, "execution_generation": 0,
        }
        extension = {
            "tool": "mmx_delegate", "present": True, "toolset": "mmx_delegate",
            "scope": str(self.home), "profile_id": str(self.home),
            "schema_sha256": schema_digest(NATIVE_TOOL_SCHEMA),
            "implementation_sha": OWNER, "instance_id": target["instance_id"],
            "authority_epoch": target["authority_epoch"],
            "enrollment_request_id": publication.session.request_id,
            "principal_id": publication.session.principal_id, "session_id": target["session_id"],
            "command_id": publication.command, "job_id": publication.job_id,
            "target_digest": publication.target_digest,
            "principal_binding_digest": publication.principal_binding_digest,
            "authority_generation_digest": publication.authority_generation_digest,
            "capability_profile_digest": publication.capability_profile_digest,
            "plugin_sha256": publication.plugin.digest,
            "mcp_tools_schema_sha256": publication.tools_schema_digest,
        }
        enrollment = native_session_control.enrollment_result(
            OWNER, publication.session.request_id, "ENROLLED", target)
        class Client:
            def __init__(self, home, expected_pid=None, role="mmsecretary"):
                assert home == runtime._native_home and expected_pid == runtime._child.pid
                assert role == runtime.profile.role
            def consumer_extension(self):
                return {"schema": native_session_control.SCHEMA,
                        "status": "OBSERVED", "extension": dict(extension)}
            def inspect_enrollment(self, implementation, request_id):
                assert implementation == OWNER and request_id == publication.session.request_id
                return enrollment
        return runtime, launch, extension, Client

    def test_the_extension_proof_needs_the_original_actual_child(self) -> None:
        from integrations.hermes_runtime import native_session_control
        runtime, launch, _extension, _client = self._consumer_runtime()
        runtime._child = None
        runtime._consume_consumer_extension(4242)
        self.assertEqual(launch.observed, [])
        runtime._child = type("Child", (), {"pid": 4242, "poll": lambda _self: None})()
        with mock.patch.object(native_session_control, "NativeSecretaryClient",
                               side_effect=RuntimeRefusal("NO_SERVING_PROCESS")):
            runtime._consume_consumer_extension(4242)
        self.assertEqual(launch.observed, [4242])
        self.assertIsNone(runtime._extension_observed)
        self.assertFalse(runtime._extension_proved)

    def test_a_proved_scoped_entry_is_recorded(self) -> None:
        from integrations.hermes_runtime import native_session_control
        runtime, launch, _extension, client = self._consumer_runtime()
        with mock.patch.object(native_session_control, "NativeSecretaryClient", client):
            status, payload = runtime.health_snapshot()
        self.assertEqual(status, 200)
        self.assertTrue(payload["native_extension_proved"])
        self.assertEqual(launch.observed, [4242, 4242])

    def test_health_clears_the_proof_after_same_schema_binding_or_scope_replacement(self):
        from integrations.hermes_runtime import native_session_control
        for key, value in (("scope", "/foreign"), ("session_id", "foreign-session"),
                           ("target_digest", "f" * 64), ("implementation_sha", "b" * 40)):
            with self.subTest(key=key):
                runtime, _launch, extension, client = self._consumer_runtime()
                with mock.patch.object(native_session_control, "NativeSecretaryClient", client):
                    self.assertTrue(runtime.health_snapshot()[1]["native_extension_proved"])
                    extension[key] = value
                    self.assertFalse(runtime.health_snapshot()[1]["native_extension_proved"])
                self.assertFalse(runtime._extension_proved)

    def test_no_backend_readiness_means_no_serving_proof(self):
        runtime, _launch, _extension, _client = self._consumer_runtime()
        runtime._extension_proved = True
        runtime._backend_ready = False
        self.assertFalse(runtime.health_snapshot()[1]["native_extension_proved"])


if __name__ == "__main__":
    unittest.main()
