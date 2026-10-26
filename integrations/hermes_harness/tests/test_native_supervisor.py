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


if __name__ == "__main__":
    unittest.main()
