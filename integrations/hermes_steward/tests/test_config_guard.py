"""Offline guard tests for the Hermes Steward MCP config."""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_steward.client import ALLOWED_TOOLS  # noqa: E402
from integrations.hermes_steward.config_guard import (  # noqa: E402
    HERMES_PIN,
    inspect,
    inspect_file,
    main,
)
from integrations.hermes_steward import config_guard  # noqa: E402

EXAMPLE = ROOT / "integrations" / "hermes_steward" / "hermes.mcp.yaml"
SENTINEL = "fixture-config-secret-sentinel-do-not-print"


def _base_config() -> dict:
    loaded = inspect_file(EXAMPLE)
    if loaded["status"] != "PASS_OFFLINE_STEWARD_READ_CONFIG":
        raise AssertionError(loaded["issues"])
    text = EXAMPLE.read_text(encoding="utf-8")
    parsed = config_guard._load_unique_yaml(text.encode("utf-8"))
    return parsed


class ConfigGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _base_config()

    def check(self, config=None):
        return inspect(self.config if config is None else config, sha256="b" * 64)

    def test_example_config_passes_offline_and_lists_six_tools(self) -> None:
        result = inspect_file(EXAMPLE)
        self.assertEqual(result["status"], "PASS_OFFLINE_STEWARD_READ_CONFIG")
        self.assertEqual(result["observations"]["allowlist"], list(ALLOWED_TOOLS))
        self.assertEqual(result["observations"]["allowlist_count"], 6)
        self.assertEqual(result["observations"]["extra_tool_count"], 0)
        self.assertEqual(result["observations"]["missing_tools"], [])
        self.assertFalse(result["observations"]["write_tool_configured"])
        self.assertFalse(result["write_path_admitted"])
        self.assertFalse(result["hermes_started"])
        self.assertFalse(result["model_or_provider_called"])
        self.assertFalse(result["network_contacted"])
        self.assertFalse(result["identity_or_authority_granted"])
        self.assertEqual(result["observations"]["hermes_pin"], HERMES_PIN)
        self.assertEqual(HERMES_PIN, "1c0cd667746d3395fe9e1b6c74f8f85952486f18")

    def test_allowlist_mutation_is_blocked(self) -> None:
        short = copy.deepcopy(self.config)
        short["mcp_servers"]["mastermind_steward"]["tools"]["include"] = list(ALLOWED_TOOLS[:-1])
        short_result = self.check(short)
        self.assertEqual(short_result["status"], "BLOCKED")
        self.assertIn("TOOL_ALLOWLIST_MISMATCH", short_result["issues"])
        self.assertEqual(short_result["observations"]["missing_tools"], ["resolve_surface"])

        extra = copy.deepcopy(self.config)
        extra["mcp_servers"]["mastermind_steward"]["tools"]["include"] = list(ALLOWED_TOOLS) + [
            "submit_executive_intent"
        ]
        extra_result = self.check(extra)
        self.assertIn("TOOL_ALLOWLIST_MISMATCH", extra_result["issues"])
        self.assertIn("WRITE_TOOL_CONFIGURED", extra_result["issues"])
        self.assertTrue(extra_result["observations"]["write_tool_configured"])
        self.assertNotIn("submit_executive_intent", json.dumps(extra_result))

    def test_exclude_only_filter_is_not_an_allowlist(self) -> None:
        config = copy.deepcopy(self.config)
        config["mcp_servers"]["mastermind_steward"]["tools"] = {
            "exclude": ["delete_customer"],
            "resources": False,
            "prompts": False,
        }
        result = self.check(config)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("MCP_TOOL_FILTER_INVALID", result["issues"])

    def test_resources_and_prompts_must_stay_off(self) -> None:
        for key in ("resources", "prompts"):
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config["mcp_servers"]["mastermind_steward"]["tools"][key] = True
                self.assertIn("MCP_RESOURCES_OR_PROMPTS_ENABLED", self.check(config)["issues"])

    def test_literal_bearer_is_blocked_and_not_echoed(self) -> None:
        config = copy.deepcopy(self.config)
        config["mcp_servers"]["mastermind_steward"]["headers"]["Authorization"] = (
            f"Bearer {SENTINEL}"
        )
        result = self.check(config)
        encoded = json.dumps(result)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("LITERAL_SECRET_VALUE", result["issues"])
        self.assertIn("AUTHORIZATION_MUST_BE_BEARER_ENV_REFERENCE", result["issues"])
        self.assertNotIn(SENTINEL, encoded)

    def test_inline_secret_field_is_counted_not_printed(self) -> None:
        config = copy.deepcopy(self.config)
        config["mcp_servers"]["mastermind_steward"]["access_token"] = SENTINEL
        result = self.check(config)
        self.assertGreaterEqual(result["observations"]["inline_secret_field_count"], 1)
        self.assertIn("INLINE_SECRET_FIELD", result["issues"])
        self.assertNotIn(SENTINEL, json.dumps(result))

    def test_stdio_command_and_shell_are_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["mcp_servers"]["mastermind_steward"]["command"] = "bash"
        config["mcp_servers"]["mastermind_steward"]["args"] = ["-c", "curl https://example.invalid"]
        result = self.check(config)
        self.assertIn("UNQUALIFIED_MCP_SERVER_KEY", result["issues"])

    def test_second_server_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["mcp_servers"]["other"] = {"url": "${OTHER_URL}"}
        result = self.check(config)
        self.assertIn("MCP_SERVER_NAME_REFUSED", result["issues"])
        self.assertNotIn("other", json.dumps(result["observations"]))

    def test_public_url_literal_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["mcp_servers"]["mastermind_steward"]["url"] = "https://mcp.example.invalid/mcp"
        self.assertIn("MCP_URL_MUST_BE_ENV_REFERENCE", self.check(config)["issues"])

    def test_duplicate_yaml_key_is_refused(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8") + "\ntoolsets:\n  - terminal\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dup.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                inspect_file(path)

    def test_yaml_anchor_is_refused(self) -> None:
        text = "model: &m {provider: zai, default: glm-5.3}\nauxiliary: *m\n"
        with self.assertRaises(ValueError):
            config_guard._load_unique_yaml(text.encode("utf-8"))

    def test_dropped_dangerous_toolset_is_blocked(self) -> None:
        config = copy.deepcopy(self.config)
        config["agent"]["disabled_toolsets"].remove("terminal")
        result = self.check(config)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("DANGEROUS_TOOLSET_NOT_GLOBALLY_DISABLED", result["issues"])

    def test_cli_prints_structural_result_only(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--config", str(EXAMPLE)])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "PASS_OFFLINE_STEWARD_READ_CONFIG")
        self.assertNotIn("MASTERMIND_STEWARD_ACCESS_TOKEN", json.dumps(payload["issues"]))

    def test_qualification_profiles_do_not_gain_mcp(self) -> None:
        profiles = ROOT / "integrations" / "hermes_qualification" / "profiles"
        for path in profiles.glob("*/config.yaml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("mcp_servers", text)
            self.assertNotIn(SENTINEL, text)


if __name__ == "__main__":
    unittest.main()
