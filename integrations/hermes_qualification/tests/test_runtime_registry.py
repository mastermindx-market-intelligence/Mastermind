import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_registry import inspect

FIXTURE = (Path(__file__).parent / "fixture-cli-toolsets.txt").read_text(encoding="utf8")


class RuntimeRegistryTests(unittest.TestCase):
    def test_observed_restricted_cli_passes_without_claiming_server_policy(self):
        r = inspect(FIXTURE, "")
        self.assertEqual(r["status"], "PASS_CLI_REGISTRY_OBSERVATION_ONLY")
        self.assertTrue(r["enabled_only_clarify"])
        self.assertFalse(r["receiving_service_policy_verified"])
        self.assertFalse(r["source_or_binary_attested_by_this_report"])
        self.assertFalse(r["remote_or_desktop_tools_qualified"])

    def test_missing_or_nonempty_stderr_blocks_fallback_false_positive(self):
        self.assertIn("STDERR_NOT_OBSERVED", inspect(FIXTURE)["issues"])
        self.assertIn("RUNTIME_CONFIG_OR_TOOL_WARNING_PRESENT", inspect(FIXTURE, "Hermes retained previous settings")["issues"])

    def test_unqualified_baseline_todo_and_connections_are_blocked(self):
        modified = FIXTURE.replace("✗ disabled  todo", "✓ enabled  todo")
        modified = modified.replace("✗ disabled  connections", "✓ enabled  connections")
        r = inspect(modified, "")
        self.assertEqual(r["status"], "BLOCKED")
        self.assertIn("EXTRA_ACTUATING_TOOLSET_ENABLED", r["issues"])

    def test_one_enabled_unauthorized_tool_blocks(self):
        for tool in ("terminal", "computer_use", "a2a", "delegation", "memory", "browser", "file"):
            with self.subTest(tool=tool):
                r = inspect(FIXTURE.replace(f"✗ disabled  {tool}", f"✓ enabled  {tool}"))
                self.assertEqual(r["status"], "BLOCKED")

    def test_unknown_enabled_plugin_or_new_builtin_is_blocked(self):
        for target in ("  ✓ enabled  future_tool  Privileged\n", "  ✗ disabled  future_tool  New\n"):
            r = inspect(FIXTURE.replace("Plugin toolsets (cli):\n", "Plugin toolsets (cli):\n" + target))
            self.assertIn("UPSTREAM_TOOLSET_DRIFT", r["issues"])

    def test_missing_tools_and_missing_headings_block(self):
        for text in (FIXTURE.replace("  ✗ disabled  a2a  A2A\n", ""), FIXTURE.replace("Plugin toolsets (cli):", ""), FIXTURE.replace("  ✓ enabled  clarify  Clarifying Questions\n", "")):
            self.assertEqual(inspect(text, "")["status"], "BLOCKED")

    def test_ambiguous_status_duplicate_and_output_noise_block(self):
        variants = [
            FIXTURE.replace("✓ enabled  clarify", "✗ enabled  clarify"),
            FIXTURE + "  ✓ enabled  clarify  Duplicate\n",
            "unexpected banner\n" + FIXTURE,
            FIXTURE.replace("Built-in toolsets (cli):", "Built-in toolsets (desktop):"),
        ]
        for text in variants:
            with self.subTest(firstline=text.splitlines()[0]):
                self.assertEqual(inspect(text, "")["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
