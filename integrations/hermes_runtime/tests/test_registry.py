"""Allowlist equality and empty-stderr registry gate."""
from __future__ import annotations

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
    inspect_tool_registry,
    register_extension_tools,
)
from integrations.hermes_runtime.tests._support import CENSUS, load_preflight  # noqa: E402

CENSUS_TEXT = CENSUS.read_text(encoding="utf-8")


class RegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_extension_tools()

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

    def test_refused_set_matches_the_qualification_census(self) -> None:
        preflight = load_preflight()
        self.assertEqual(REFUSED_HERMES_TOOLSETS, preflight.REQUIRED_DISABLED)
        self.assertEqual(ADMITTED_HERMES_TOOLSETS, preflight.ALLOWED_ENABLED)


if __name__ == "__main__":
    unittest.main()
