"""Keyless native BYOK role configuration contract tests.

No provider transport, real credential, Hermes subprocess, host service or
Steward MCP connection is used. Shadow decision behavior stays unchanged.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness import native_byok
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_models.contract import PROVIDERS
from integrations.hermes_models.profile_config import render_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_steward.client import ALLOWED_TOOLS
from integrations.hermes_steward.config_guard import _load_unique_yaml


class NativeByokTests(unittest.TestCase):
    def _profile(self, root: Path, role: str):
        return replace(
            compose_profile(role, state_dir=root / "state",
                            secrets_file=root / "uncreated-provider-secret.env"),
            tool_allowlist=frozenset({"clarify"}),
        )

    def test_real_native_secretary_modelark_and_meta_zai_primary(self) -> None:
        for role, provider_name, model, keyenv in (
            ("mmsecretary", "byteplus-modelark", "glm-5-3-flash-260828",
             "BYTEPLUS_MODELARK_API_KEY"),
            ("mmmeta", "zai-glm", "glm-5.3", "ZAI_API_KEY"),
        ):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as raw:
                content = native_byok.render_disarmed_native_byok(self._profile(Path(raw), role))
                cfg = _load_unique_yaml(content.encode("utf-8"))
                self.assertEqual(
                    cfg["model"],
                    {
                        "provider": provider_name,
                        "default": model,
                        "base_url": PROVIDERS[
                            "byteplus-modelark.glm-5.3-flash" if role == "mmsecretary"
                            else "zai.glm-5.3"
                        ].base_url,
                        "key_env": keyenv,
                        "api_mode": "chat_completions",
                    },
                )
                self.assertEqual(cfg["toolsets"], ["clarify"])
                self.assertEqual(set(cfg["mcp_servers"]), {"mastermind_steward"})
                self.assertIs(cfg["mcp_servers"]["mastermind_steward"]["enabled"], False)
                self.assertEqual(
                    cfg["mcp_servers"]["mastermind_steward"]["tools"]["include"],
                    list(ALLOWED_TOOLS),
                )
                self.assertEqual(cfg["mcp_servers"]["mastermind_steward"]["tools"]["resources"], False)
                self.assertNotIn("auxiliary", cfg)
                self.assertNotIn("fallback_model", cfg)
                self.assertEqual(cfg["providers"]["cursor-pool"]["enabled"], False)
                self.assertNotIn("api_key:", content.lower())
                self.assertNotIn("api/coding", content.lower())
                self.assertEqual(len(content.split("mcp_servers:")), 2)

    def test_model_or_provider_source_mutation_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            profile = self._profile(Path(raw), "mmsecretary")
            original = render_profile(profile.role)
            for bad in (
                original.replace(
                    "key_env: BYTEPLUS_MODELARK_API_KEY",
                    "key_env: UNREVIEWED_REALM_KEY",
                ),
                original.replace(
                    "    enabled: false",
                    "    enabled: true",
                ),
                original.replace("  - clarify", "  - terminal"),
                original.replace("    - computer_use", "    - future_actuator"),
                original + "mcp_servers: {}\n",
            ):
                with self.subTest(bad_hash=hash(bad)):
                    with mock.patch.object(native_byok, "render_profile", return_value=bad):
                        with self.assertRaises(RuntimeRefusal):
                            native_byok.render_disarmed_native_byok(profile)

    def test_uninstalled_shadow_extension_names_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            profile = compose_profile(
                "mmmeta", state_dir=Path(raw) / "state",
                secrets_file=Path(raw) / "never-read.env",
            )
            self.assertIn("mmx_delegate", profile.extension_allowlist)
            with self.assertRaises(RuntimeRefusal) as exc:
                native_byok.render_disarmed_native_byok(profile)
            self.assertEqual(exc.exception.code, "NATIVE_BYOK_EXTENSION_NOT_INSTALLED")

    def test_no_keys_read_and_model_name_only_in_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            profile = self._profile(Path(raw), "mmsecretary")
            secret_path = profile.secrets_file
            self.assertFalse(secret_path.exists())
            doc = native_byok.render_disarmed_native_byok(profile)
            self.assertFalse(secret_path.exists())
            self.assertIn("key_env: BYTEPLUS_MODELARK_API_KEY", doc)
            self.assertNotIn("NATIVE_HAS_CREDENTIALS", doc)
            self.assertNotIn("fallback_model:", doc)


if __name__ == "__main__":
    unittest.main()
