"""Allowlist equality and empty-stderr registry gate."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from integrations.hermes_runtime.constants import (  # noqa: E402
    ADMITTED_HERMES_TOOLSETS,
    REFUSED_HERMES_TOOLSETS,
)
from integrations.hermes_runtime.errors import RuntimeRefusal  # noqa: E402
from integrations.hermes_runtime.registry import (  # noqa: E402
    assert_registered_tools_exact,
    clear_extension_tools,
    extension_tools_for,
    inspect_tool_registry,
    register_extension_tools,
)
from integrations.hermes_runtime.secrets import (  # noqa: E402
    Secrets,
    child_env,
    clear_child_secret_env,
    register_child_secret_env,
)
from integrations.hermes_runtime.tests._support import CENSUS, load_preflight  # noqa: E402

CENSUS_TEXT = CENSUS.read_text(encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_extension_tools()
        clear_child_secret_env()

    def test_allowlist_equals_registered_tools_with_empty_stderr(self) -> None:
        result = assert_registered_tools_exact(CENSUS_TEXT, "", {"clarify"}, ())
        self.assertEqual(result["status"], "PASS_REGISTRY_EXACT")
        self.assertEqual(result["registered"], ["clarify"])
        self.assertEqual(result["allowlist"], ["clarify"])
        self.assertTrue(result["stderr_empty"])
        self.assertFalse(result["upstream_attested"])
        self.assertEqual(set(result["registered"]), set(result["allowlist"]))

    def test_empty_stderr_bytes_pass_and_any_stderr_bytes_block(self) -> None:
        self.assertTrue(inspect_tool_registry(CENSUS_TEXT, b"", {"clarify"})["stderr_empty"])
        for stderr in (None, b"\n", b" ", "warning\n", "Hermes retained previous settings"):
            with self.subTest(stderr=stderr):
                result = inspect_tool_registry(CENSUS_TEXT, stderr, {"clarify"})
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse(result["stderr_empty"])
                self.assertTrue(
                    {"STDERR_NOT_EMPTY", "STDERR_NOT_OBSERVED"} & set(result["issues"])
                )

    def test_enabled_tool_outside_the_allowlist_is_refused(self) -> None:
        for tool in ("terminal", "todo", "connections", "delegation", "memory", "a2a"):
            with self.subTest(tool=tool):
                modified = CENSUS_TEXT.replace(f"✗ disabled  {tool}", f"✓ enabled  {tool}")
                result = inspect_tool_registry(modified, "", {"clarify"})
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn("ALLOWLIST_REGISTERED_MISMATCH", result["issues"])
                self.assertIn("REFUSED_TOOLSET_ENABLED", result["issues"])
                with self.assertRaises(RuntimeRefusal):
                    assert_registered_tools_exact(modified, "", {"clarify"})

    def test_allowlist_tool_missing_from_the_registry_is_refused(self) -> None:
        modified = CENSUS_TEXT.replace("✓ enabled  clarify", "✗ disabled  clarify")
        result = inspect_tool_registry(modified, "", {"clarify"})
        self.assertIn("ALLOWLIST_REGISTERED_MISMATCH", result["issues"])

    def test_unknown_toolset_and_truncated_census_are_refused(self) -> None:
        extra = CENSUS_TEXT.replace(
            "Plugin toolsets (cli):\n",
            "Plugin toolsets (cli):\n  ✓ enabled  future_tool  New\n",
        )
        self.assertIn("UPSTREAM_TOOLSET_DRIFT", inspect_tool_registry(extra, "", {"clarify"})["issues"])
        truncated = CENSUS_TEXT.replace("  ✗ disabled  a2a  A2A\n", "")
        self.assertIn(
            "INCOMPLETE_TOOLSET_REGISTRY",
            inspect_tool_registry(truncated, "", {"clarify"})["issues"],
        )

    def test_extension_tools_must_equal_the_non_hermes_allowlist(self) -> None:
        def provider(profile):
            del profile
            return frozenset({"list_responsibilities"})

        register_extension_tools("steward", provider)
        blocked = inspect_tool_registry(
            CENSUS_TEXT, "", {"clarify", "list_responsibilities"}, (),
        )
        self.assertIn("EXTENSION_ALLOWLIST_MISMATCH", blocked["issues"])
        passed = assert_registered_tools_exact(
            CENSUS_TEXT, "", {"clarify", "list_responsibilities"}, {"list_responsibilities"},
        )
        self.assertEqual(
            set(passed["registered"]),
            {"clarify", "list_responsibilities"},
        )

    def test_every_refused_toolset_collides_as_an_extension(self) -> None:
        for name in sorted(REFUSED_HERMES_TOOLSETS):
            clear_extension_tools()
            register_extension_tools("probe", lambda profile, name=name: frozenset({name}))
            with self.assertRaises(RuntimeRefusal) as ctx:
                extension_tools_for(object())
            self.assertEqual(ctx.exception.code, "EXTENSION_TOOL_COLLIDES_WITH_HERMES")
        clear_extension_tools()

        def batch(profile: object) -> frozenset[str]:
            del profile
            return frozenset({"delegation", "skills", "terminal"})

        register_extension_tools("probe", batch)
        with self.assertRaises(RuntimeRefusal) as ctx:
            extension_tools_for(object())
        self.assertEqual(ctx.exception.code, "EXTENSION_TOOL_COLLIDES_WITH_HERMES")

    def test_exact_disabled_mcp_summary_is_not_a_registered_tool(self) -> None:
        names = (
            "list_responsibilities", "get_responsibility", "get_attention",
            "get_current_runtime", "explain_blocker", "resolve_surface",
        )
        expected = {"mastermind_steward": names}
        summary = (
            CENSUS_TEXT.rstrip() + "\n\nMCP servers:\n"
            + f"  mastermind_steward  [include only: {', '.join(names)}]\n"
        )
        result = inspect_tool_registry(summary, b"", {"clarify"},
                                       expected_disabled_mcp=expected)
        self.assertEqual(result["status"], "PASS_REGISTRY_EXACT", result["issues"])
        self.assertEqual(result["registered"], ["clarify"])
        for changed, culprit in (
            (summary.replace("resolve_surface]", "write_company_state]"), "MCP_SERVER_SUMMARY_MISMATCH"),
            (summary.replace("mastermind_steward  [", "evil_server  ["), "MCP_SERVER_SUMMARY_MISMATCH"),
            (summary + "  mastermind_steward  [include only: list_responsibilities]\n", "DUPLICATE_MCP_SERVER"),
            (summary.replace("MCP servers:", "Other servers:"), "UNRECOGNIZED_TOOL_ROW_OR_SECTION"),
        ):
            self.assertIn(culprit, inspect_tool_registry(
                changed, b"", {"clarify"}, expected_disabled_mcp=expected,
            )["issues"])
        self.assertIn("UNEXPECTED_MCP_SECTION",
                      inspect_tool_registry(summary, b"", {"clarify"})["issues"])
        self.assertIn("INCOMPLETE_MCP_SUMMARY",
                      inspect_tool_registry(CENSUS_TEXT, b"", {"clarify"},
                                            expected_disabled_mcp=expected)["issues"])

    def test_registered_child_secret_names_are_forwarded_and_the_gateway_token_is_not(self) -> None:
        register_child_secret_env(["ZAI_API_KEY"])
        with self.assertRaises(RuntimeRefusal) as ctx:
            register_child_secret_env(["HERMES_GATEWAY_TOKEN"])
        self.assertEqual(ctx.exception.code, "GATEWAY_TOKEN_STAYS_ON_THE_FRONT_DOOR")
        token = "local-test-gateway-token"
        secrets = Secrets(token, "hermes", token, {"ZAI_API_KEY": "distinct-provider-value", "HERMES_GATEWAY_TOKEN": token})
        env = child_env(secrets, home=Path("/tmp/hermes-home-test"))
        self.assertEqual(env["ZAI_API_KEY"], "distinct-provider-value")
        self.assertNotIn("HERMES_GATEWAY_TOKEN", env)
        self.assertNotIn("distinct-provider-value", repr(secrets))
        os.environ["HERMES_SLACK_BOT_TOKEN"] = "parent-token-should-not-leak"
        os.environ["HERMES_SLACK_BOT_USER_ID"] = "UPARENTSHOULDNOTWIN"
        self.addCleanup(os.environ.pop, "HERMES_SLACK_BOT_TOKEN", None)
        self.addCleanup(os.environ.pop, "HERMES_SLACK_BOT_USER_ID", None)
        identified = Secrets(
            token,
            "hermes",
            token,
            {
                "HERMES_GATEWAY_TOKEN": token,
                "HERMES_SLACK_BOT_TOKEN": "file-bot-token-value1",
                "HERMES_SLACK_BOT_USER_ID": "UHERMESSELF1",
            },
        )
        child = child_env(identified, home=Path("/tmp/hermes-home-test"))
        self.assertEqual(child["HERMES_SLACK_BOT_USER_ID"], "UHERMESSELF1")
        self.assertNotIn("HERMES_SLACK_BOT_TOKEN", child)
        self.assertNotIn("HERMES_GATEWAY_TOKEN", child)
        self.assertNotIn("file-bot-token-value1", child.values())
        self.assertNotIn("parent-token-should-not-leak", child.values())

    def test_refused_set_matches_the_qualification_census(self) -> None:
        preflight = load_preflight()
        self.assertEqual(REFUSED_HERMES_TOOLSETS, preflight.REQUIRED_DISABLED)
        self.assertEqual(ADMITTED_HERMES_TOOLSETS, preflight.ALLOWED_ENABLED)


if __name__ == "__main__":
    unittest.main()
