"""Real installer-level tests for the disabled native Hermes Steward configuration.

No network connection, model key, MCP bearer token, systemd start, or Slack.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness import native_mcp
from integrations.hermes_harness.cli import _install
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.tests._support import write_secrets
from integrations.hermes_steward.client import ALLOWED_TOOLS
from integrations.hermes_steward.config_guard import _load_unique_yaml

ROOT = Path(__file__).resolve().parents[3]
STUB = ROOT / "integrations" / "hermes_runtime" / "tests" / "fixtures" / "hermes_stub.py"


class NativeStewardConfigTests(unittest.TestCase):
    def _profile(self, root: Path):
        return compose_profile(
            "mmsecretary",
            state_dir=root / "state",
            secrets_file=root / "secrets.env",
        )

    def test_native_steward_present_but_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as path:
            text = native_mcp.render_disarmed_native_config(self._profile(Path(path)))
        parsed = _load_unique_yaml(text.encode("utf-8"))
        self.assertEqual(parsed["toolsets"], ["clarify"])
        self.assertIn("delegation", parsed["agent"]["disabled_toolsets"])
        self.assertEqual(set(parsed["mcp_servers"]), {"mastermind_steward"})
        entry = parsed["mcp_servers"]["mastermind_steward"]
        self.assertIs(entry["enabled"], False)
        self.assertEqual(entry["url"], "${MASTERMIND_STEWARD_MCP_URL}")
        self.assertEqual(
            entry["headers"],
            {"Authorization": "Bearer ${MASTERMIND_STEWARD_ACCESS_TOKEN}"},
        )
        self.assertEqual(entry["tools"]["include"], list(ALLOWED_TOOLS))
        self.assertIs(entry["tools"]["resources"], False)
        self.assertIs(entry["tools"]["prompts"], False)
        self.assertEqual(text.count("mcp_servers:"), 1)
        self.assertNotIn("xoxb-", text)
        self.assertNotIn("sk-", text)

    def test_meta_ceo_has_same_six_reads_and_no_write_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            p = compose_profile("mmmeta", state_dir=root / "state", secrets_file=root / "secrets.env")
            text = native_mcp.render_disarmed_native_config(p)
        parsed = _load_unique_yaml(text.encode("utf-8"))
        self.assertEqual(parsed["mcp_servers"]["mastermind_steward"]["tools"]["include"], list(ALLOWED_TOOLS))
        self.assertIs(parsed["mcp_servers"]["mastermind_steward"]["enabled"], False)
        self.assertEqual(set(parsed["mcp_servers"]), {"mastermind_steward"})
        self.assertNotIn("mmx_delegate", text)
        self.assertIn("delegation", parsed["agent"]["disabled_toolsets"])

    def test_source_drift_extra_tool_or_missing_source_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = native_mcp._SOURCE.read_text(encoding="utf-8")
            forged = root / "unsafe.yaml"
            self.assertIn("        - resolve_surface", source)
            forged.write_text(
                source.replace(
                    "        - resolve_surface",
                    "        - resolve_surface\n        - write_company_state",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(native_mcp, "_SOURCE", forged):
                with self.assertRaises(RuntimeRefusal) as exc:
                    native_mcp.render_disarmed_native_config(self._profile(root))
                self.assertEqual(exc.exception.code, "NATIVE_MCP_SOURCE_UNQUALIFIED")
            with mock.patch.object(native_mcp, "_SOURCE", root / "missing.yaml"):
                with self.assertRaises(RuntimeRefusal) as exc:
                    native_mcp.render_disarmed_native_config(self._profile(root))
                self.assertEqual(exc.exception.code, "NATIVE_MCP_SOURCE_UNAVAILABLE")

    def test_harness_install_writes_actual_disarmed_native_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            unit_dir = root / "config" / "systemd" / "user"
            upstream = root / "upstream"
            upstream.mkdir()
            (upstream / "PINNED_FIXTURE_ONLY").write_text("fixture\n", encoding="utf-8")
            secrets = root / "secrets.env"
            write_secrets(secrets)
            payload = _install(
                argparse.Namespace(
                    role="mmsecretary",
                    state=state,
                    systemd_user_dir=unit_dir,
                    secrets_file=secrets,
                    hermes_bin=STUB,
                    upstream_source=upstream,
                    fetch=False,
                )
            )
            self.assertEqual(payload["status"], "INSTALLED")
            self.assertEqual(payload["native_steward_mcp"], "CONFIGURED_DISABLED")
            self.assertIs(payload["extensions_registered"], False)
            from integrations.hermes_runtime.profile import load_profile
            real_profile = load_profile(state / "current" / "profile.yaml")
            self.assertEqual(real_profile.tool_allowlist, frozenset({"clarify"}))
            self.assertEqual(real_profile.extension_allowlist, frozenset())
            self.assertIs(payload["native_steward_connected"], False)
            self.assertIs(payload["upstream_attested"], False)
            native = state / "current" / "hermes-home" / "profiles" / "mmsecretary" / "config.yaml"
            self.assertTrue(native.is_file())
            self.assertEqual(stat.S_IMODE(native.stat().st_mode), 0o600)
            parsed = _load_unique_yaml(native.read_bytes())
            self.assertIs(parsed["mcp_servers"]["mastermind_steward"]["enabled"], False)
            self.assertEqual(
                parsed["mcp_servers"]["mastermind_steward"]["tools"]["include"],
                list(ALLOWED_TOOLS),
            )
            manifest = json.loads((state / "install-manifest.json").read_text(encoding="utf-8"))
            unit = Path(manifest["unit_path"])
            self.assertEqual(stat.S_IMODE(unit.stat().st_mode), 0o600)
            policy = state / "current" / "hermes-home" / "profiles" / "mmsecretary" / "SOUL.md"
            self.assertEqual(stat.S_IMODE(policy.stat().st_mode), 0o600)
            receipt = json.loads((state / "current" / "install-receipt.json").read_text(encoding="utf-8"))
            import hashlib
            self.assertEqual(receipt["hermes_config_sha256"], hashlib.sha256(native.read_bytes()).hexdigest())
            self.assertFalse(manifest.get("production_armed", False))
            self.assertTrue(secrets.is_file())
            self.assertEqual(stat.S_IMODE(secrets.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
