"""Read-only isolated regression for sealed native generation 22's AUTO sentinel.

Never calls a provider, reserves a worker, writes a worktree, or changes the
selected native release. The candidate and sealed baseline are supplied by
the source-only verifier.
"""
from __future__ import annotations

import ast
import inspect
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

CANDIDATE = Path(os.environ["MMX_NATIVE_AUTO_SENTINEL_CANDIDATE"])
BASELINE = Path(os.environ["MMX_NATIVE_AUTO_SENTINEL_BASELINE"])
sys.path.insert(0, str(BASELINE / "ext"))
sys.path.insert(0, str(CANDIDATE / "ext"))
import fabric_task as task


class NativeAutoSentinelTest(unittest.TestCase):
    def test_auto_sentinel_normalizes_case_insensitively(self):
        for value in ("auto", "AUTO", " Auto "):
            with self.subTest(value=value):
                self.assertIsNone(task._manual_token(value))

    def test_literal_exact_model_is_not_renamed(self):
        self.assertEqual(task._manual_token("MiniMax-M3"), "MiniMax-M3")

    def test_explicit_strict_pin_rejects_auto_pool_before_packet(self):
        with self.assertRaisesRegex(task.FabricTaskError, "MANUAL_POOL_REQUIRED"):
            task.request(
                "native-auto-sentinel-strict-001", "review", cwd=".", packet=None, stdin_bytes=None,
                pool="auto", requested_model="auto", strict_manual_pin=True,
            )

    def test_exact_strict_pin_preserves_packet_validation(self):
        with self.assertRaisesRegex(ValueError, "provide exactly one"):
            task.request(
                "native-auto-sentinel-strict-002", "review", cwd=".", packet=None, stdin_bytes=None,
                pool="minimax", requested_model="MiniMax-M3",
                strict_manual_pin=True,
            )

    def test_pool_only_auto_is_normalized_before_packet(self):
        with patch.object(task, "_manual_token", wraps=task._manual_token) as normalize:
            with self.assertRaisesRegex(ValueError, "provide exactly one"):
                task.request(
                    "native-auto-sentinel-pool-only", "review", cwd=".", packet=None, stdin_bytes=None,
                    pool="minimax", requested_model="auto", prefer="auto",
                )
            self.assertGreaterEqual(normalize.call_count, 3)
            normalize.assert_any_call("minimax")
            normalize.assert_any_call("auto")

    def test_malformed_pin_fails_before_packet(self):
        with self.assertRaisesRegex(task.FabricTaskError, "MANUAL_SELECTOR_INVALID"):
            task.request("native-auto-sentinel-invalid", "review", cwd=".", packet=None, stdin_bytes=None, pool="../bad")

    def test_request_normalizes_before_durable_or_provider_paths(self):
        tree = ast.parse(inspect.getsource(task.request))
        fn = tree.body[0]
        self.assertIsInstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        body = fn.body
        fields = {}
        for index, stmt in enumerate(body[:12]):
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
                if isinstance(target, ast.Name):
                    fields[target.id] = (index, stmt.value)
        for name in ("pool", "requested_model", "prefer"):
            self.assertIn(name, fields)
            self.assertIsInstance(fields[name][1], ast.Call)
            self.assertEqual(fields[name][1].func.id, "_manual_token")
        self.assertLess(max(fields[x][0] for x in ("pool", "requested_model", "prefer")), 7)

    def test_preview_pool_only_matches_default_without_reservation(self):
        selected = "POOL=minimax MODEL=MiniMax-M3 HOST=m1 MODE=minimax REASON=fixture"
        with patch.object(task.pick, "format_pick", return_value=selected) as pick:
            with patch.object(task.pick, "launch_policy", return_value={"allowed": True}):
                result = task.preview_route(
                    "native-auto-sentinel-preview-001", "review",
                    pool="minimax", model="auto",
                    task_complexity="C2_COMPLEX_BOUNDED",
                )
        self.assertEqual(result["state"], "PREVIEW_ONLY")
        self.assertIs(result["reserved"], False)
        self.assertEqual((result["pool"], result["model"]), ("minimax", "MiniMax-M3"))
        self.assertTrue(result["strict_pin_enforced_at_request"])
        self.assertIsNone(pick.call_args.kwargs["requested_model"])


if __name__ == "__main__":
    unittest.main()
