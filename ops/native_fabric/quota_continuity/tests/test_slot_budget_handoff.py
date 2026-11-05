"""End-to-end source handoff of the existing four-hour outer worker fuse.

Never launches a provider, SSH worker or broker lease. The source-extracted
Grok launch fragment and the actual remote executor contract are tested
against the nested slot.py parser, preserving original shorter budgets.
"""
from pathlib import Path
import ast
import os
import sys
import textwrap
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
sys.path.insert(0, str(CANDIDATE))

import lane_runtime
import slot


def _actual_remote_slot_handoff():
    # Compile precisely the production helper, not a fresh mock implementation.
    source = (CANDIDATE / "remote_sub_exec.py").read_text()
    parsed = ast.parse(source)
    node = next(x for x in parsed.body
                if isinstance(x, ast.FunctionDef)
                and x.name == "_slot_child_timeout_env")
    ns = {"parse_bounded_seconds": lane_runtime.parse_bounded_seconds,
          "LaneRuntimeConfigError": lane_runtime.LaneRuntimeConfigError}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 "<real-remote-slot-handoff>", "exec"), ns)
    return ns["_slot_child_timeout_env"]


remote_slot_handoff = _actual_remote_slot_handoff()


def grok_handoff_fragment() -> str:
    text = (CANDIDATE / "sub.sh").read_text()
    first = text.index("        # Pass the validated existing Grok worker budget")
    end = text.index("        save(folder / \"stdout.txt\", result.stdout.encode())", first)
    return text[first:end]


def grok_launch_with_inert_owner(worker_timeout: float, env: dict) -> dict:
    # Execute the *real* embedded Python launch fragment; the process function
    # is a recording fake, no executable is spawned.
    source = ("def fixture():\n" +
              textwrap.indent(textwrap.dedent(grok_handoff_fragment()), "    ") +
              "    return captured\n")
    ast.parse(source)
    captured = {}
    def record(command, **kwargs):
        captured.update(kwargs)
        return object()
    scope = {
        "worker_timeout": worker_timeout,
        "env": dict(env),
        "parse_bounded_seconds": lane_runtime.parse_bounded_seconds,
        "run_owned_process": record,
        "command": ["/usr/bin/python3", "/fixture/slot.py", "grok"],
        "cwd": Path("/tmp"),
        "config": type("Cfg", (), {"nice": 0})(),
        "key": "fixture-only",
        "folder": Path("/tmp"),
        "captured": captured,
    }
    exec(compile(source, "<source-extracted-grok>", "exec"), scope)
    scope["fixture"]()
    return captured


def grok_budget_from_real_source(complexity: str, env: dict) -> float:
    # Execute the actual complexity/default-resolution fragment, including
    # its explicit shorter-commission rule; no checkout/provider is launched.
    original = (CANDIDATE / "sub.sh").read_text()
    start = original.index('    complexity = str(env.get("POOL_TASK_COMPLEXITY")')
    stop = original.index('    default_turns = 140', start)
    section = textwrap.dedent(original[start:stop])
    namespace = {
        "env": dict(env),
        "parse_bounded_seconds": lane_runtime.parse_bounded_seconds,
    }
    namespace["env"]["POOL_TASK_COMPLEXITY"] = complexity
    exec(compile(section, "<actual-grok-budget-resolution>", "exec"), namespace)
    return namespace["worker_timeout"]


class SlotBudgetHandoffTests(unittest.TestCase):
    def slot_limit(self, forwarded):
        with mock.patch.dict(os.environ, forwarded, clear=True):
            return slot._child_runtime_limit()

    def test_default_slot_without_handoff_is_two_hours(self):
        self.assertEqual(self.slot_limit({}), 7200.0)
        self.assertEqual(slot.MAX_CHILD_TIMEOUT_S, 14400.0)

    def test_remote_c3_four_hour_window_reaches_real_slot_monitor(self):
        env = remote_slot_handoff({}, 14340.0)
        self.assertEqual(self.slot_limit(env), 14340.0)

    def test_remote_inherited_deadline_narrows_inner_slot(self):
        for outer, explicit, expected in (
            (14340, {}, 14340),
            (3600, {}, 3600),
            (14340, {"POOL_CHILD_TIMEOUT_SECONDS": "1200"}, 1200),
            (14340, {"SLOT_CHILD_TIMEOUT_SECONDS": "600"}, 600),
            (500, {"POOL_CHILD_TIMEOUT_SECONDS": "1200"}, 500),
            (14340, {"POOL_CHILD_TIMEOUT_SECONDS": "1800",
                     "SLOT_CHILD_TIMEOUT_SECONDS": "1000"}, 1000),
            (210, {}, 210),
        ):
            with self.subTest(outer=outer, explicit=explicit):
                env = remote_slot_handoff(explicit, outer)
                self.assertEqual(self.slot_limit(env), expected)

    def test_remote_overflow_and_malformed_fails_closed(self):
        for outer, inherited in (
            (14401, {}), (float("inf"), {}), (0.3, {}),
            (14340, {"SLOT_CHILD_TIMEOUT_SECONDS": "14401"}),
            (14340, {"POOL_CHILD_TIMEOUT_SECONDS": "NaN"}),
            (14340, {"SLOT_CHILD_TIMEOUT_SECONDS": "-1"}),
        ):
            with self.subTest(outer=outer, inherited=inherited):
                with self.assertRaises(lane_runtime.LaneRuntimeConfigError):
                    remote_slot_handoff(inherited, outer)

    def test_actual_remote_launcher_calls_handoff_only_for_slot_modes(self):
        text = (CANDIDATE / "remote_sub_exec.py").read_text()
        self.assertIn('if canonical_command is None and mode in ("glm", "minimax", "qwen"):', text)
        self.assertIn("child_env = _slot_child_timeout_env(child_env, timeout)", text)
        self.assertLess(
            text.index("child_env = _slot_child_timeout_env(child_env, timeout)"),
            text.index("state[\"started\"] = True"),
        )
        self.assertIn('REMOTE_SUB_SLOT_TIMEOUT_REFUSED before_worker=1', text)

    def test_standalone_grok_c3_explicit_shorter_commission_is_respected(self):
        for complexity, limits, expected in (
            ("C3_FRONTIER_JUDGMENT", {}, 14400),
            ("C2_COMPLEX_BOUNDED", {}, 7200),
            ("C1_ROUTINE_BOUNDED", {}, 3600),
            ("C3_FRONTIER_JUDGMENT",
             {"POOL_CHILD_TIMEOUT_SECONDS": "1200"}, 1200),
            ("C2_COMPLEX_BOUNDED",
             {"POOL_CHILD_TIMEOUT_SECONDS": "1800"}, 1800),
            ("C3_FRONTIER_JUDGMENT",
             {"POOL_CHILD_TIMEOUT_SECONDS": "14340"}, 14340),
        ):
            with self.subTest(complexity=complexity, inherited=limits):
                actual = grok_budget_from_real_source(complexity, limits)
                self.assertEqual(actual, expected)
                result = grok_launch_with_inert_owner(actual, {})
                self.assertEqual(self.slot_limit(result["env"]), expected)

    def test_standalone_grok_c3_passes_four_hours_to_real_slot(self):
        captured = grok_launch_with_inert_owner(14400.0, {})
        self.assertEqual(captured["timeout"], 14400.0)
        self.assertEqual(self.slot_limit(captured["env"]), 14400.0)

    def test_standalone_grok_stricter_window_is_preserved(self):
        for outer, env, expected in (
            (14400, {"SLOT_CHILD_TIMEOUT_SECONDS": "1200"}, 1200),
            (7200, {}, 7200),
            (3600, {}, 3600),
            (14400, {"SLOT_CHILD_TIMEOUT_SECONDS": "14340"}, 14340),
        ):
            with self.subTest(outer=outer, explicit=env):
                captured = grok_launch_with_inert_owner(outer, env)
                self.assertEqual(self.slot_limit(captured["env"]), expected)
                self.assertEqual(captured["timeout"], outer)

    def test_standalone_grok_bad_child_override_refuses_before_start(self):
        for value in ("nan", "14401", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(lane_runtime.LaneRuntimeConfigError):
                    grok_launch_with_inert_owner(
                        14400, {"SLOT_CHILD_TIMEOUT_SECONDS": value},
                    )


if __name__ == "__main__":
    unittest.main()
