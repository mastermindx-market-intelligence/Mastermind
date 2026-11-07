"""DIAGNOSTIC ONLY: eight known failures remain unresolved; not a release test.

Behavioral reproducer for the unchanged installed Codex/Claude hook.

No provider, GitHub, worker, or production action is executed by these tests.
The hook only evaluates representative tool payloads.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "execution_friction_hook",
    ROOT / "fixtures/installed_routing_guard.py",
)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class ExecutionFrictionHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [
            ("POLL_STATE_DIR", self.tmp.name),
            ("is_mastermind_scope", lambda payload: True),
            ("_legacy_macro_root_reason", lambda payload, tool: None),
        ]:
            p = patch.object(guard, target, value)
            p.start()
            self.addCleanup(p.stop)

    def invoke(self, command=None, *, cwd="/repo/a", tool="Bash", extra=None, **ti):
        if command is not None:
            ti["command"] = command
        payload = {"session_id": "fixture-session", "cwd": cwd,
                   "tool_name": tool, "tool_input": ti}
        payload.update(extra or {})
        out = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
            try:
                guard.main()
            except SystemExit as exc:
                self.assertEqual(exc.code, 0)
        text = out.getvalue().strip()
        return json.loads(text).get("hookSpecificOutput", {}) if text else {}

    def assert_not_denied(self, result):
        self.assertNotEqual(result.get("permissionDecision"), "deny", result)

    def test_repeated_status_read_is_advice_not_permission_denial(self):
        self.invoke("gh pr view 42 --json state")
        result = self.invoke("gh pr view 42 --json state")
        self.assert_not_denied(result)
        self.assertIn("REPEATED STATUS READ", result.get("additionalContext", ""))

    def test_different_repositories_do_not_share_poll_identity(self):
        self.invoke("gh pr view 42 --json state", cwd="/repo/a")
        result = self.invoke("gh pr view 42 --json state", cwd="/repo/b")
        self.assert_not_denied(result)
        self.assertNotIn("REPEATED STATUS READ", result.get("additionalContext", ""))

    def test_different_status_questions_are_not_redundant(self):
        self.invoke("gh pr view 42 --json state")
        result = self.invoke("gh pr view 42 --json reviewDecision,mergeStateStatus")
        self.assert_not_denied(result)
        self.assertNotIn("REPEATED STATUS READ", result.get("additionalContext", ""))

    def test_explicit_repository_flags_are_part_of_observation_identity(self):
        self.invoke("gh pr checks 42 --repo owner/first")
        result = self.invoke("gh pr checks 42 --repo owner/second")
        self.assert_not_denied(result)
        self.assertNotIn("REPEATED STATUS READ", result.get("additionalContext", ""))

    def test_pretool_watch_never_claims_started_or_armed(self):
        result = self.invoke("gh run watch 123 --interval 150", run_in_background=True)
        self.assert_not_denied(result)
        context = result.get("additionalContext", "")
        self.assertIn("CI WATCH REQUEST", context)
        self.assertNotIn("ARMED", context)
        self.assertIn("successful tool result", context)
        self.assertIn("return path", context)

    def test_codex_native_watch_requires_result_not_implicit_durable_owner(self):
        result = self.invoke("gh run watch 123 --interval 150", extra={"turn_id": "turn-1"})
        self.assert_not_denied(result)
        context = result.get("additionalContext", "")
        self.assertIn("successful tool result", context)
        self.assertNotIn("task is now", context)

    def test_legacy_checkout_does_not_block_readonly_diagnosis(self):
        with patch.object(guard, "_legacy_macro_root_reason", return_value="Legacy checkout: recover safely."):
            result = self.invoke("git status --short")
        self.assert_not_denied(result)
        self.assertIn("Legacy checkout", result.get("additionalContext", ""))

    def test_legacy_checkout_does_not_block_workspace_acquisition(self):
        with patch.object(guard, "_legacy_macro_root_reason", return_value="Legacy checkout: recover safely."):
            result = self.invoke("mmx-workspace acquire --operation-id fixture --base-sha abc --lane web")
        self.assert_not_denied(result)

    def test_legacy_advice_does_not_bypass_native_model_policy(self):
        with patch.object(guard, "_legacy_macro_root_reason", return_value="Legacy checkout."):
            result = self.invoke(tool="Agent", model="sonnet", prompt="Routine work")
        self.assertEqual(result.get("permissionDecision"), "deny")

    def test_native_implicit_model_still_refused(self):
        result = self.invoke(tool="Agent", prompt="Routine work")
        self.assertEqual(result.get("permissionDecision"), "deny")

    def test_explicit_bounded_readonly_opus_review_still_allowed(self):
        result = self.invoke(tool="Agent", model="opus", prompt=(
            "ROUTE: AUDIT\nWHY OPUS: Independent review of a consequential bounded patch\nMODE: READ_ONLY\n"
        ))
        self.assert_not_denied(result)

    def test_observation_only_watcher_restriction_preserved(self):
        result = self.invoke("gh run watch 123 --interval 150; gh pr merge 42", run_in_background=True)
        self.assertEqual(result.get("permissionDecision"), "deny")
        self.assertIn("OBSERVATION-ONLY", result.get("permissionDecisionReason", ""))

    def test_hot_watcher_restriction_preserved(self):
        result = self.invoke("gh run watch 123 --interval 2", run_in_background=True)
        self.assertEqual(result.get("permissionDecision"), "deny")

    def test_foreground_sleep_poll_loop_remains_refused(self):
        result = self.invoke("while true; do gh pr checks 42; sleep 2; done")
        self.assertEqual(result.get("permissionDecision"), "deny")

    def test_heredoc_documentation_is_not_executed_polling(self):
        result = self.invoke("cat > example.txt <<'EOF'\nwhile true; do gh pr checks 42; sleep 2; done\nEOF")
        self.assert_not_denied(result)

    def test_material_mutation_clears_advisory_observation(self):
        self.invoke("gh pr view 42 --json state")
        self.invoke("gh pr ready 42")
        result = self.invoke("gh pr view 42 --json state")
        self.assert_not_denied(result)
        self.assertNotIn("REPEATED STATUS READ", result.get("additionalContext", ""))


if __name__ == "__main__":
    unittest.main()
