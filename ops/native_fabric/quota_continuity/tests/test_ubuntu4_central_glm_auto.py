"""Ubuntu4 central GLM-Codex: ordinary automatic-routing acceptance.

Everything below is synthetic and private to this module:

  * the host registry entries and the host telemetry are fabricated data;
  * the broker, the provider quota/cooldown observation, the GLM broker room
    and the GLM meter are provider-availability facts replaced by inert
    stand-ins. They are never a routing, role, class or economic decision;
  * the transport is an inert sink. No host, provider, credential, registry,
    lease, service or network effect is produced by this module.

What is exercised unmodified is the CURRENT candidate code: the request
adapter, the pick routing law (declared task-class policy and economic guard
included), the pool -> mode enumeration, the placement view and the host gate
evaluation. Nothing here asserts a source text.

Ubuntu4 is physically HELD; its live glm-codex mode is registered and
qualification-held. These synthetic fixtures prove the routing path only. They prove no
live Ubuntu4 worker, no lease, no provider result, no hardware recovery and
no release.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_adapter_continuity as fixture
import glm_host_account_source
import host_pick
import lease_broker
import placement_view
import quota_remote

api = fixture.api
pick = api.pick

GLM_CODEX = "glm-codex"
GLM_EXECUTOR_MODEL = "glm-5.3-flash"
GLM_FULL_MODEL = "glm-5.3"
C1 = "C1_ROUTINE_BOUNDED"
C2 = "C2_COMPLEX_BOUNDED"
# A synthetic economic witness: the existing guard only needs a non-empty
# bounded-complexity reason. It is not an approval, a receipt or a grant.
WITNESS = "synthetic bounded complexity escalation witness for the C2 build route"


def _policy(task_classes=None):
    """Synthetic runtime policy shape (orch/fabric/pools.yaml is host state)."""
    spec = {
        "enabled": True,
        "models": {
            "executor": GLM_EXECUTOR_MODEL,
            "reviewer": GLM_FULL_MODEL,
            "operator": GLM_FULL_MODEL,
        },
    }
    if task_classes is not None:
        spec["task_classes"] = list(task_classes)
    return {"pools": {"glm": spec}}


def _host_entry(host, modes, qualification_only_modes=()):
    return {
        "roles": ["lanes"],
        "platform": "linux",
        "ssh_alias": "synthetic-" + host,
        "allowed_modes": list(modes),
        "qualification_only_modes": list(qualification_only_modes),
        "lane_ceiling": 4,
        "max_active": 4,
        "load_gate": 8.0,
        "min_free_gb": 60,
        "checkout_reserve_gb": 15,
        "min_free_mem_gb": 2,
        "require_thermal": False,
        "cpu_tctl_limit_c": 85,
        "nvme_min_crit_headroom_c": 10,
        "require_pressure": False,
        "max_io_psi_some10_pct": 50,
        "max_memory_psi_some10_pct": 50,
    }


def _host_state(host, tools, ts=None, **overrides):
    value = {
        "host": host,
        "ts": time.time() if ts is None else ts,
        "reachable": True,
        "active_lanes": 0,
        "load1": 0.5,
        "mem_free_gb": 16.0,
        "disk_free_gb": 800.0,
        "ncpu": 32,
        "tools": list(tools),
    }
    value.update(overrides)
    return value


class Ubuntu4CentralGlmAuto(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.state_dir = self.root / "host-state"
        self.state_dir.mkdir(parents=True)
        self.registry = {}
        self.policy = _policy()
        self.transports = []
        self.selection_lines = []
        self.sequence = 0

        account = {"name": "synthetic", "_eff_cap": 1}
        broker = SimpleNamespace(
            hosts_path=str(self.root / "unused-hosts.json"),
            _conn=lambda: SimpleNamespace(close=lambda: None),
            grantable_accounts=lambda _provider: [account],
            account_model_cap=lambda *_: None,
            _account_held=lambda *_: 0,
            _account_model_held=lambda *_: 0,
            provider=lambda _pool: {"enabled": True, "accounts": []},
            pool_cap=lambda _pool: 8,
            snapshot=lambda: {"pools": {}, "leases": []},
            now=lambda: 1000,
        )

        def transport(argv, env):
            self.transports.append((list(argv), dict(env)))
            return SimpleNamespace(returncode=0)

        real_format_pick = pick.format_pick

        def selection(task_class, **options):
            line = real_format_pick(task_class, **options)
            self.selection_lines.append(line)
            return line

        for target, name, value in (
            (api, "HERE", self.root),
            (host_pick, "load_registry", lambda: dict(self.registry)),
            (host_pick, "HOSTS_STATE_DIR", str(self.state_dir)),
            (lease_broker, "default_broker", lambda: broker),
            (glm_host_account_source, "filter_observed_accounts",
             lambda accounts, **_: (accounts, [])),
            (pick, "load_pools", lambda *a, **k: dict(self.policy)),
            (pick, "_glm_broker_model_remaining", lambda _model: 2),
            (pick, "_glm_meter_state", lambda: ""),
            # The real router reads the provider quota cache. Keep that
            # runtime file out of the source tree.
            (quota_remote, "CACHE_PATH", str(self.root / "quota_cache.json")),
            (pick, "format_pick", selection),
            (api.subprocess, "run", transport),
        ):
            self.stack.enter_context(patch.object(target, name, value))

    # ── synthetic topologies ────────────────────────────────────────────────

    def _publish(self, host, state):
        (self.state_dir / (host + ".json")).write_text(json.dumps(state))

    def _install_ubuntu4(self, qualification_only_modes=(), state_overrides=None):
        self.registry["ubuntu4"] = _host_entry("ubuntu4", [GLM_CODEX],
                                               qualification_only_modes)
        state = _host_state("ubuntu4", ["codex"], **(state_overrides or {}))
        self._publish("ubuntu4", state)
        return state

    def _install_ubuntu3_minimax(self):
        self.registry["ubuntu3"] = _host_entry("ubuntu3", ["minimax"])
        self._publish("ubuntu3", _host_state("ubuntu3", ["claude"]))

    def request(self, *, task_class="census", complexity=C1, **overrides):
        self.sequence += 1
        options = dict(
            cwd="~/lanes/repos/macro",
            packet=None,
            stdin_bytes=b"synthetic ubuntu4 central glm-codex assignment\n",
            root_id="synthetic-root",
            parent_run_id="synthetic-parent",
            task_complexity=complexity,
        )
        options.update(overrides)
        return api.request("central-glm-%d" % self.sequence, task_class, **options)

    def assert_no_transport(self):
        """No transport ran and no launch was reserved; a refusal was kept."""
        self.assertEqual(self.transports, [])
        state = self.root / "state" / "remote_sub"
        self.assertEqual(list(state.glob("*.request-launch.json")), [])
        refused = list(state.glob("*.request-refused.json"))
        self.assertTrue(refused)
        for path in refused:
            self.assertFalse(json.loads(path.read_text())["launch_attempted"])

    # ── 1. the retained qualification hold keeps Ubuntu4 out of ordinary routing

    def test_retained_glm_codex_hold_excludes_ubuntu4_from_ordinary_routing(self):
        self._install_ubuntu4(qualification_only_modes=[GLM_CODEX])
        rows = host_pick.evaluate_hosts(
            self.registry, str(self.state_dir), GLM_CODEX,
            now=datetime.now(timezone.utc),
        )
        row = next(item for item in rows if item["host"] == "ubuntu4")
        gates = {item["gate"]: item for item in row["gates"]}
        # The mode itself is authorized; the qualification hold is what refuses.
        self.assertEqual(gates["mode"]["result"], "PASS")
        self.assertEqual(gates["automatic-qualification"]["result"], "FAIL")
        self.assertIn("explicit-canary-only", gates["automatic-qualification"]["detail"])
        self.assertFalse(row["eligible"])
        # The placement view refuses the same host for the same reason, so the
        # hold is not carried by one layer alone.
        view = placement_view.build_placement_view(
            self.registry, str(self.state_dir), GLM_CODEX,
            now=datetime.now(timezone.utc),
        )
        exclusions = {item["host"]: item["reasons"]
                      for item in view["candidate_exclusions"]}
        self.assertIn("ubuntu4", exclusions)
        self.assertIn("explicit-canary-only", exclusions["ubuntu4"])
        self.assertIsNone(view["host_choice"])
        # Ordinary AUTO routing cannot reach it, with no override and no
        # transport effect.
        with self.assertRaises(api.FabricTaskError):
            self.request()
        self.assert_no_transport()
        # The refusal names the qualification hold itself, and no route line
        # selects the host.
        self.assertNotIn("HOST=ubuntu4", " ".join(self.selection_lines))
        self.assertIn("ubuntu4:automatic-qualification",
                      " ".join(self.selection_lines))

    # ── 2. an admitted Ubuntu4 is selectable by ordinary provider policy

    def test_admitted_ubuntu4_routes_c1_census_to_glm_codex(self):
        self._install_ubuntu4()
        self.assertEqual(self.request(task_class="census", complexity=C1), 0)
        argv, _env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu4")
        self.assertEqual(argv[3], GLM_CODEX)
        self.assertEqual(argv[6], GLM_EXECUTOR_MODEL)
        self.assertIn("POOL=glm", self.selection_lines[-1])
        self.assertIn("MODE=" + GLM_CODEX, self.selection_lines[-1])

    def test_admitted_ubuntu4_routes_c1_mechanical_to_glm_codex(self):
        self._install_ubuntu4()
        self.assertEqual(self.request(task_class="mechanical", complexity=C1), 0)
        argv, _env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu4")
        self.assertEqual(argv[3], GLM_CODEX)

    def test_glm_pool_takes_the_glm_codex_mode_first_on_a_dual_mode_host(self):
        # A host that could serve both GLM modes must still be routed through
        # the pool's first adapter.
        self.registry["ubuntu4"] = _host_entry("ubuntu4", [GLM_CODEX, "glm"])
        self._publish("ubuntu4", _host_state("ubuntu4", ["codex", "claude"]))
        self.assertEqual(self.request(task_class="census", complexity=C1), 0)
        argv, _env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu4")
        self.assertEqual(argv[3], GLM_CODEX)

    # ── 2b. the real C1 / C2 task-class policy, checked separately

    def test_c2_build_is_not_routed_into_glm_without_a_witness(self):
        self._install_ubuntu4()
        with self.assertRaisesRegex(api.FabricTaskError,
                                    "bounded_complexity_requires_escalation"):
            self.request(task_class="build", complexity=C2,
                         requested_model=GLM_FULL_MODEL)
        self.assert_no_transport()

    def test_c2_build_escalation_reaches_ubuntu4_glm_codex_with_the_full_model(self):
        self._install_ubuntu4()
        self.assertEqual(self.request(task_class="build", complexity=C2,
                                      requested_model=GLM_FULL_MODEL,
                                      escalation_reason=WITNESS), 0)
        argv, _env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu4")
        self.assertEqual(argv[3], GLM_CODEX)
        self.assertEqual(argv[6], GLM_FULL_MODEL)

    def test_c2_fix_build_uses_the_leaf_labor_executor_route(self):
        self._install_ubuntu4()
        self.assertEqual(self.request(task_class="fix_build", complexity=C2), 0)
        argv, _env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu4")
        self.assertEqual(argv[3], GLM_CODEX)
        self.assertEqual(argv[6], GLM_EXECUTOR_MODEL)

    def test_declared_glm_class_policy_refuses_the_c2_build_class(self):
        self._install_ubuntu4()
        self.policy = _policy(task_classes=["census", "mechanical", "extract",
                                             "execute", "verify"])
        with self.assertRaisesRegex(api.FabricTaskError,
                                    "role does not allow class=build"):
            self.request(task_class="build", complexity=C2,
                         requested_model=GLM_FULL_MODEL,
                         escalation_reason=WITNESS)
        self.assert_no_transport()
        # The same declared policy still admits the C1 labor class.
        self.assertEqual(self.request(task_class="census", complexity=C1), 0)
        self.assertEqual(self.transports[-1][0][2], "ubuntu4")

    # ── 3. stale metrics, full capacity and the retained hold block Ubuntu4

    def test_stale_ubuntu4_metrics_block_the_route(self):
        self._install_ubuntu4(state_overrides={"ts": time.time() - 3600})
        with self.assertRaises(api.FabricTaskError):
            self.request()
        self.assert_no_transport()

    def test_full_ubuntu4_capacity_blocks_the_route(self):
        self._install_ubuntu4(state_overrides={"active_lanes": 4})
        with self.assertRaises(api.FabricTaskError):
            self.request()
        self.assert_no_transport()

    def test_ineligible_ubuntu4_preserves_the_other_host_and_provider_choice(self):
        self._install_ubuntu4(state_overrides={"ts": time.time() - 3600})
        self._install_ubuntu3_minimax()
        self.assertEqual(self.request(), 0)
        argv, _env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu3")
        self.assertEqual(argv[3], "minimax")
        self.assertNotIn("ubuntu4", " ".join(self.selection_lines))

    # ── 4. original lineage, task metadata and the mode reach the transport

    def test_original_root_parent_and_task_metadata_reach_the_transport(self):
        self._install_ubuntu4()
        self.assertEqual(self.request(task_class="census", complexity=C1), 0)
        argv, env = self.transports[0]
        self.assertEqual(env["POOL_ORCHESTRATOR_ID"], "synthetic-root")
        self.assertEqual(env["POOL_PARENT_RUN_ID"], "synthetic-parent")
        self.assertEqual(env["POOL_TASK_CLASS"], "census")
        self.assertEqual(env["POOL_TASK_COMPLEXITY"], C1)
        self.assertEqual(argv[argv.index("--run-id") + 1], "central-glm-1")

    def test_sparse_request_reaches_ubuntu4_glm_codex_with_the_same_lineage(self):
        self._install_ubuntu4()
        commit = "a" * 40
        self.assertEqual(self.request(task_class="census", complexity=C1,
                                      new_macro_worktree=commit), 0)
        argv, env = self.transports[0]
        self.assertEqual(argv[2], "ubuntu4")
        self.assertEqual(argv[3], GLM_CODEX)
        self.assertEqual(argv[argv.index("--new-macro-worktree") + 1], commit)
        self.assertEqual(env["POOL_ORCHESTRATOR_ID"], "synthetic-root")
        self.assertEqual(env["POOL_PARENT_RUN_ID"], "synthetic-parent")
        self.assertEqual(env["POOL_TASK_CLASS"], "census")


if __name__ == "__main__":
    unittest.main()
