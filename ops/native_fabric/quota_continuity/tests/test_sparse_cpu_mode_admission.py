"""Prospective request capabilities through the real router, without effects.

Only host/account observations, economic ranking and the final shell transport
are inert. The real request, mode vocabulary, host-mode enumeration, operator
intersection and reviewer-independence predicate remain under test.
"""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_adapter_continuity as fixture
import glm_host_account_source
import host_pick
import lease_broker
import placement_view


api = fixture.api
QUALIFIED = {"glm", "glm-codex", "minimax", "qwen"}


class SparseCpuModeAdmission(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.available = {"grok", "glm"}
        self.views = []
        self.options = []
        self.transports = []
        self.ranked = []
        registry = {"ubuntu3": {"platform": "linux", "local": False}}
        account = {"name": "synthetic", "_eff_cap": 1}
        broker = SimpleNamespace(
            hosts_path=self.root / "unused-hosts.json",
            _conn=lambda: SimpleNamespace(close=lambda: None),
            grantable_accounts=lambda _provider: [account],
            account_model_cap=lambda *_: None,
            _account_held=lambda *_: 0,
            _account_model_held=lambda *_: 0,
        )

        def observation(_registry, _state, mode, **kwargs):
            self.views.append(mode)
            usable = mode in self.available and "ubuntu3" not in kwargs["excluded"]
            return {"host_choice": "ubuntu3" if usable else None}

        def ranking(task_class, **kwargs):
            modes = kwargs.get("host_modes") or {}
            # Unsupported Grok genuinely outranks the qualified alternative.
            for pool in ("grok", "glm", "minimax", "bailian"):
                if pool not in modes or kwargs.get("pool") not in (None, pool):
                    continue
                if not api.pick._subject_ok(pool, task_class, kwargs.get("subject_pool"), {})[0]:
                    continue
                self.ranked.append(pool)
                return f"POOL={pool} MODEL=synthetic-model"
            return "NONE reason=synthetic eligible ranking exhausted"

        real_router = api.pick.format_pick

        def route(task_class, **kwargs):
            self.options.append(dict(kwargs))
            return real_router(task_class, **kwargs)

        def transport(argv, env):
            self.transports.append((list(argv), dict(env)))
            return SimpleNamespace(returncode=0)

        for target, name, value in (
            (api, "HERE", self.root),
            (host_pick, "load_registry", lambda: registry),
            (lease_broker, "default_broker", lambda: broker),
            (glm_host_account_source, "filter_observed_accounts", lambda accounts, **_: (accounts, [])),
            (placement_view, "build_placement_view", observation),
            (api.pick, "load_pools", lambda: {}),
            (api.pick, "_selection_model", lambda *_args, **_kwargs: ("synthetic-model", "")),
            (api.pick, "_format_pick", ranking),
            (api.pick, "_grok_exhausted", lambda: False),
            (api.pick, "format_pick", route),
            (api.pick, "launch_policy", lambda *_args, **_kwargs: {"allowed": True}),
            (api.subprocess, "run", transport),
        ):
            self.stack.enter_context(patch.object(target, name, value))

    def invoke(self, *, task_class="mechanical", **kwargs):
        return api.request(
            "synthetic-request", task_class, cwd="~/lanes/repos/macro",
            packet=None, stdin_bytes=b"synthetic prospective assignment\n",
            root_id="synthetic-root", parent_run_id="synthetic-parent",
            task_complexity="C1_ROUTINE_BOUNDED", **kwargs,
        )

    def assert_no_launch(self):
        self.assertEqual(self.transports, [])
        state = self.root / "state/remote_sub"
        self.assertFalse((state / "synthetic-request.request-launch.json").exists())
        refused = json.loads((state / "synthetic-request.request-refused.json").read_text())
        self.assertFalse(refused["launch_attempted"])

    def test_sparse_skips_higher_ranked_unqualified_mode(self):
        self.assertEqual(self.invoke(new_macro_worktree="a" * 40), 0)
        self.assertEqual(self.ranked, ["glm"])
        self.assertEqual(self.transports[0][0][2:4], ["ubuntu3", "glm"])
        self.assertEqual(set(self.options[0]["required_modes"]), QUALIFIED)
        self.assertEqual(self.options[0]["required_platforms"], ["linux"])
        self.assertNotIn("grok", self.views)

    def test_cpu_scope_uses_the_same_existing_mode_capability(self):
        self.assertEqual(self.invoke(cpu_scope_percent=100), 0)
        self.assertEqual(self.ranked, ["glm"])
        self.assertEqual(set(self.options[0]["required_modes"]), QUALIFIED)
        self.assertIn("--cpu-scope-quota", self.transports[0][0])

    def test_combined_request_keeps_both_transport_options(self):
        self.assertEqual(self.invoke(new_macro_worktree="b" * 40, cpu_scope_percent=200), 0)
        self.assertEqual(self.ranked, ["glm"])
        self.assertIn("--new-macro-worktree", self.transports[0][0])
        self.assertIn("--cpu-scope-quota", self.transports[0][0])

    def test_legacy_request_keeps_unconstrained_ranking(self):
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.ranked, ["grok"])
        self.assertNotIn("required_modes", self.options[0])
        self.assertNotIn("required_platforms", self.options[0])

    def test_only_unqualified_capacity_remains_no_eligible(self):
        self.available = {"grok"}
        with self.assertRaisesRegex(api.FabricTaskError, "no eligible remote mode"):
            self.invoke(new_macro_worktree="c" * 40)
        self.assert_no_launch()

    def test_glm_codex_is_in_the_incumbent_router_vocabulary(self):
        self.available = {"grok", "glm-codex"}
        self.assertEqual(self.invoke(new_macro_worktree="d" * 40), 0)
        self.assertEqual(self.transports[0][0][3], "glm-codex")

    def test_turn_ceiling_intersects_instead_of_broadening_modes(self):
        self.assertEqual(self.invoke(new_macro_worktree="e" * 40, max_turns=7), 0)
        self.assertEqual(set(self.options[0]["required_modes"]), {"glm", "minimax"})
        self.assertEqual(self.transports[0][1]["POOL_REQUEST_MAX_TURNS"], "7")

    def test_operator_child_intersection_remains_glm_only(self):
        with patch.dict(os.environ, {"POOL_OPERATOR_CHILD_BUDGET": "1"}):
            self.assertEqual(self.invoke(new_macro_worktree="f" * 40), 0)
        self.assertEqual(self.views, ["glm"])
        self.assertEqual(self.ranked, ["glm"])

    def test_author_independence_cannot_be_bypassed_by_capability(self):
        with self.assertRaises(api.FabricTaskError):
            self.invoke(task_class="review", subject_pool="glm", new_macro_worktree="1" * 40)
        self.assertEqual(self.options[0]["subject_pool"], "glm")
        self.assert_no_launch()

    def test_economic_refusal_still_precedes_transport(self):
        with patch.object(api.pick, "launch_policy", return_value={"allowed": False, "reason": "synthetic refusal"}):
            with self.assertRaisesRegex(api.FabricTaskError, "ECONOMIC_POLICY_REFUSED"):
                self.invoke(new_macro_worktree="2" * 40)
        self.assert_no_launch()

    def test_unqualified_mode_from_a_faulty_router_still_refuses(self):
        with patch.object(api.pick, "format_pick", return_value="POOL=grok MODEL=synthetic-model HOST=ubuntu3 MODE=grok"):
            with self.assertRaisesRegex(api.FabricTaskError, "SPARSE_MODE_NOT_YET_QUALIFIED"):
                self.invoke(new_macro_worktree="3" * 40)
        self.assert_no_launch()

    def test_unqualified_cpu_host_from_a_faulty_router_still_refuses(self):
        with patch.object(api.pick, "format_pick", return_value="POOL=glm MODEL=synthetic-model HOST=ubuntu0 MODE=glm"):
            with self.assertRaisesRegex(api.FabricTaskError, "CPU_SCOPE_HOST_NOT_QUALIFIED"):
                self.invoke(cpu_scope_percent=100)
        self.assert_no_launch()

    def test_root_parent_and_task_identity_reach_existing_transport(self):
        self.assertEqual(self.invoke(new_macro_worktree="4" * 40), 0)
        env = self.transports[0][1]
        self.assertEqual(env["POOL_ORCHESTRATOR_ID"], "synthetic-root")
        self.assertEqual(env["POOL_PARENT_RUN_ID"], "synthetic-parent")
        self.assertEqual(env["POOL_TASK_CLASS"], "mechanical")
        self.assertEqual(env["POOL_TASK_COMPLEXITY"], "C1_ROUTINE_BOUNDED")


if __name__ == "__main__":
    unittest.main()
