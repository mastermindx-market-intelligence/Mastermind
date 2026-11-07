"""Offline Hermes Executive v3 + Paper MCP source/installer contract tests."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness import executive_paper_mcp as plugin
from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_steward.config_guard import _load_unique_yaml


class ExecutivePaperMcpTests(unittest.TestCase):
    def profile(self, home: Path, role: str):
        from dataclasses import replace
        return replace(
            compose_profile(role, state_dir=home / "state",
                            secrets_file=home / "unread.env"),
            tool_allowlist=frozenset({"clarify"}),
        )

    def test_actual_role_render_has_both_disabled_read_only_servers(self):
        for role in ("mmsecretary", "mmmeta"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                result = plugin.render_disarmed_native_exec_paper(
                    self.profile(Path(tmp), role))
                config = _load_unique_yaml(result.encode("utf-8"))
            self.assertEqual(set(config["mcp_servers"]), {
                "mastermind_steward", *plugin.SERVER_NAMES,
            })
            self.assertEqual(config["toolsets"], ["clarify"])
            for entry in config["mcp_servers"].values():
                self.assertIs(entry["enabled"], False)
                self.assertIs(entry["tools"]["resources"], False)
                self.assertIs(entry["tools"]["prompts"], False)
            self.assertEqual(
                config["mcp_servers"]["mastermind_executive_v3"]["tools"]["include"],
                list(plugin.EXECUTIVE_READ_TOOLS),
            )
            self.assertEqual(
                config["mcp_servers"]["mastermind_paper"]["tools"]["include"],
                list(plugin.PAPER_READ_TOOLS),
            )
            for forbidden in ("submit_ceo_intent", "session_send", "paper_edit",
                              "--allow-write", "127.0.0.1:29979"):
                self.assertNotIn(forbidden, result)

    def test_original_native_model_and_steward_are_preserved(self):
        from integrations.hermes_harness.native_byok import render_disarmed_native_byok
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.profile(Path(tmp), "mmmeta")
            old = _load_unique_yaml(render_disarmed_native_byok(profile).encode())
            new = _load_unique_yaml(
                plugin.render_disarmed_native_exec_paper(profile).encode())
        for key in old:
            if key != "mcp_servers":
                self.assertEqual(old[key], new[key], key)
        self.assertEqual(old["mcp_servers"]["mastermind_steward"],
                         new["mcp_servers"]["mastermind_steward"])

    def test_server_addresses_are_only_existing_owner_env_references(self):
        cfg = plugin.disarmed_server_entries()
        self.assertEqual(
            cfg["mastermind_executive_v3"]["headers"]["Authorization"],
            "Bearer ${MASTERMIND_EXECUTIVE_MCP_ACCESS_TOKEN}",
        )
        self.assertEqual(cfg["mastermind_executive_v3"]["url"],
                         "${MASTERMIND_EXECUTIVE_V3_MCP_URL}")
        self.assertEqual(cfg["mastermind_paper"]["command"],
                         "${MASTERMIND_PAPER_MCP_PYTHON}")
        self.assertEqual(cfg["mastermind_paper"]["args"],
                         ["${MASTERMIND_PAPER_MCP_SERVER}"])

    def test_executive_tool_names_really_are_read_only_in_current_v3(self):
        from integrations.executive_mcp.web_ceo_v3 import web_ceo_v3_tool_spec
        for name in plugin.EXECUTIVE_READ_TOOLS:
            with self.subTest(tool=name):
                self.assertIs(web_ceo_v3_tool_spec(name).read_only, True)

    def test_pre_enrollment_source_drift_refuses_and_never_mutates_original(self):
        baseline = {
            "toolsets": ["clarify"],
            "agent": {"disabled_toolsets": [
                "terminal", "file", "browser", "delegation", "computer_use",
            ]},
            "mcp_servers": {"mastermind_steward": {"enabled": False}},
        }
        original = baseline["mcp_servers"].copy()
        result = plugin.augment_disarmed_document(baseline)
        self.assertEqual(baseline["mcp_servers"], original)
        self.assertFalse(result["mcp_servers"]["mastermind_paper"]["enabled"])
        mutants = (
            {**baseline, "toolsets": ["clarify", "terminal"]},
            {**baseline, "mcp_servers": {"mastermind_steward": {"enabled": True}}},
            {**baseline, "mcp_servers": {**original, "unreviewed": {"enabled": True}}},
            {**baseline, "agent": {"disabled_toolsets": ["file"]}},
        )
        for mutant in mutants:
            with self.subTest(mutant=repr(mutant)), self.assertRaises(ValueError):
                plugin.augment_disarmed_document(mutant)

    def test_supervisor_catalog_accepts_only_exact_disabled_bytes(self):
        from integrations.hermes_steward.client import ALLOWED_TOOLS
        for role in ("mmsecretary", "mmmeta"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                profile = self.profile(Path(tmp), role)
                rendered = plugin.render_disarmed_native_exec_paper(profile).encode()
                expected = plugin.exact_disarmed_catalog(profile, rendered)
                self.assertEqual(expected, {
                    "mastermind_steward": tuple(ALLOWED_TOOLS),
                    "mastermind_executive_v3": plugin.EXECUTIVE_READ_TOOLS,
                    "mastermind_paper": plugin.PAPER_READ_TOOLS,
                })
                for modified in (
                    rendered + b"\\n",
                    rendered.replace(b"enabled: false", b"enabled: true", 1),
                    rendered.replace(b"paper_read", b"paper_edit", 1),
                    rendered.replace(b"${MASTERMIND_PAPER_MCP_SERVER}", b"/tmp/unsafe.py", 1),
                    rendered[:100],
                    rendered.decode(),
                    b"x" * (64 * 1024 + 1),
                ):
                    with self.subTest(modified_type=type(modified).__name__,
                                      modified_size=len(modified)):
                        self.assertIsNone(plugin.exact_disarmed_catalog(profile, modified))

    def test_duplicate_yaml_rejected_without_installed_effect(self):
        from integrations.hermes_harness import native_byok
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.profile(Path(tmp), "mmmeta")
            with mock.patch.object(
                native_byok, "render_disarmed_native_byok",
                return_value="mcp_servers: {}\nmcp_servers: {}\n",
            ), self.assertRaises(RuntimeRefusal):
                plugin.render_disarmed_native_exec_paper(profile)


if __name__ == "__main__":
    unittest.main()
