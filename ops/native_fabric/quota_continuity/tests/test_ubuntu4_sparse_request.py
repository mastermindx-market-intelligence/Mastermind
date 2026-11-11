"""Ubuntu4 sparse jobs use the existing owners without enrolling a provider.

Only the request routing/transport seams are inert. The current adapter validates
the real sparse contract; the host chooser reads synthetic state without I/O.
"""
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_adapter_continuity as fixture
import host_pick

api = fixture.api
COMMIT = "a" * 40


class Ubuntu4SparseRequest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.calls = []
        self.routes = []
        self.host = "ubuntu4"
        self.mode = "minimax"
        self.sequence = 0
        clear = patch.dict(os.environ, {}, clear=True)
        clear.start()
        self.addCleanup(clear.stop)

        def route(task_class, **options):
            self.routes.append(options)
            return f"POOL={self.mode} MODEL=fixture-model HOST={self.host} MODE={self.mode}"

        def transport(argv, env):
            self.calls.append((argv, dict(env)))
            return SimpleNamespace(returncode=0)

        for target, name, value in (
            (api, "HERE", self.root),
            (api.pick, "format_pick", route),
            (api.pick, "launch_policy", lambda *a, **k: {"allowed": True}),
            (api.subprocess, "run", transport),
        ):
            item = patch.object(target, name, value)
            item.start()
            self.addCleanup(item.stop)

    def request(self, **overrides):
        self.sequence += 1
        options = dict(cwd="~/lanes/repos/macro", packet=None,
                       stdin_bytes=b"bounded offline sparse fixture\n",
                       root_id="original-root", parent_run_id="assigning-parent",
                       task_complexity="C0_MECHANICAL", new_macro_worktree=COMMIT)
        options.update(overrides)
        return api.request(f"sparse-fixture-{self.sequence}", "mechanical", **options)

    def test_ubuntu4_preserves_original_sparse_lineage_and_linux_routing(self):
        self.assertEqual(self.request(), 0)
        argv, env = self.calls[0]
        self.assertEqual(argv[2:4], ["ubuntu4", "minimax"])
        self.assertIn("~/lanes/repos/macro", argv)
        self.assertEqual(argv[argv.index("--new-macro-worktree") + 1], COMMIT)
        self.assertEqual(env["POOL_ORCHESTRATOR_ID"], "original-root")
        self.assertEqual(env["POOL_PARENT_RUN_ID"], "assigning-parent")
        self.assertEqual(self.routes[0]["required_platforms"], ["linux"])

    def test_prior_linux_hosts_remain_supported(self):
        for host in ("ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3"):
            with self.subTest(host=host):
                self.host = host
                self.assertEqual(self.request(), 0)
                self.assertEqual(self.calls[-1][0][2], host)

    def test_unknown_and_mac_hosts_fail_before_transport(self):
        for host in ("ubuntu5", "m1", "m2", "fixture"):
            with self.subTest(host=host):
                self.host = host
                with self.assertRaisesRegex(api.FabricTaskError, "FABRIC_SPARSE_HOST_REFUSED"):
                    self.request()
        self.assertEqual(self.calls, [])

    def test_unsupported_provider_mode_still_fails_before_transport(self):
        self.mode = "grok"
        with self.assertRaisesRegex(api.FabricTaskError, "FABRIC_SPARSE_MODE_NOT_YET_QUALIFIED"):
            self.request()
        self.assertEqual(self.calls, [])

    def test_qualification_cannot_be_combined_with_a_sparse_job(self):
        with self.assertRaisesRegex(api.FabricTaskError, "FABRIC_NEW_MACRO_WORKTREE_SCOPE_REFUSED"):
            self.request(qualification_host="ubuntu4", pool="minimax")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.routes, [])

    def test_ubuntu4_does_not_gain_the_separate_cpu_scope_capability(self):
        with self.assertRaisesRegex(api.FabricTaskError, "CPU_SCOPE_HOST_NOT_QUALIFIED"):
            self.request(cpu_scope_percent=100)
        self.assertEqual(self.calls, [])

    def test_missing_lineage_bad_commit_and_foreign_cwd_are_refused(self):
        for change in ({"root_id": None}, {"parent_run_id": None},
                       {"new_macro_worktree": "HEAD"}, {"cwd": "~"}):
            with self.subTest(change=change):
                with self.assertRaises(api.FabricTaskError):
                    self.request(**change)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.routes, [])

    def test_sparse_support_does_not_remove_automatic_qualification_hold(self):
        registry = {"ubuntu4": {
            "roles": ["lanes"], "allowed_modes": ["minimax"],
            "qualification_only_modes": ["minimax"], "cores": 32,
            "max_active": 2, "lane_ceiling": 2, "load_gate": 8,
            "min_free_gb": 60, "checkout_reserve_gb": 15,
            "min_free_mem_gb": 2, "require_thermal": False,
            "require_pressure": False,
        }}
        states = {"ubuntu4": {
            "host": "ubuntu4", "ts": 1000, "reachable": True,
            "active_lanes": 0, "load1": 0, "mem_free_gb": 11,
            "disk_free_gb": 867, "ncpu": 32, "tools": ["claude"],
        }}
        row = host_pick.evaluate_hosts(registry, "unused", "minimax",
            now=datetime.fromtimestamp(1000, timezone.utc), states=states)[0]
        self.assertFalse(row["eligible"])
        gate = next(g for g in row["gates"] if g["gate"] == "automatic-qualification")
        self.assertEqual(gate["result"], "FAIL")
        self.assertIn("explicit-canary-only", gate["detail"])
        self.assertEqual(registry["ubuntu4"]["qualification_only_modes"], ["minimax"])


if __name__ == "__main__":
    unittest.main()
