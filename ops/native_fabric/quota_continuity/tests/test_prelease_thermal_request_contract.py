"""Exercise the actual request boundary with an inert provider transport.

No real credentials, provider lease, host SSH, worker, or source checkout is used.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
import fabric_task as task
import host_pick


class ThermalRequestContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.launched = []
        self.routed = []
        self.readings = {"ubuntu0": 92.0, "ubuntu1": 58.0}
        self.registry = {
            "ubuntu0": {"ssh_alias": "ubuntu0", "platform": "linux",
                        "require_thermal": True, "cpu_tctl_limit_c": 84},
            "ubuntu1": {"ssh_alias": "ubuntu1", "platform": "linux",
                        "require_thermal": True, "cpu_tctl_limit_c": 84},
        }
        self.source = task._prelease_select_cool_host
        def select(task_class, **options):
            self.routed.append((task_class, options))
            if "ubuntu0" in options.get("excluded_hosts", []):
                if "ubuntu1" in options["excluded_hosts"]:
                    return "NONE reason=no eligible remote mode satisfying required_modes"
                return "POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm"
            return "POOL=glm MODEL=glm-5.3 HOST=ubuntu0 MODE=glm"
        def launch(argv, env):
            self.launched.append((argv, env.copy()))
            return SimpleNamespace(returncode=0)
        self.apply(task, "HERE", self.root)
        self.apply(task.pick, "format_pick", select)
        self.apply(task.pick, "launch_policy", lambda *a, **k: {"allowed": True})
        self.apply(host_pick, "load_registry", lambda path=None: self.registry)
        self.apply(task.subprocess, "run", launch)
        self.apply(task, "_prelease_select_cool_host", self.choose)

    def apply(self, obj, name, replacement):
        ctx = patch.object(obj, name, replacement)
        ctx.start()
        self.addCleanup(ctx.stop)

    def choose(self, original, options, select_route):
        def observe(host, registry):
            result = self.readings[host]
            if isinstance(result, Exception):
                raise result
            return result
        return self.source(original, options, select_route, observe=observe)

    def invoke(self, run="thermal-review", *, enabled=True, **kwargs):
        return task.request(
            run, "review", cwd="~", packet=None,
            stdin_bytes=b"read only independent review\n",
            root_id="root-review", parent_run_id="parent-review",
            task_complexity="C2_COMPLEX_BOUNDED",
            prelease_live_thermal=enabled, **kwargs)

    def artifact(self, suffix, run="thermal-review"):
        return self.root / "state" / "remote_sub" / (run + suffix)

    def test_hot_first_host_reselects_once_before_only_worker_launch(self):
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(len(self.launched), 1)
        argv, env = self.launched[0]
        self.assertEqual(argv[2:4], ["ubuntu1", "glm"])
        self.assertEqual(argv[6], "glm-5.3")
        self.assertEqual(argv[-2:], ["--run-id", "thermal-review"])
        self.assertEqual(env["POOL_ORCHESTRATOR_ID"], "root-review")
        self.assertEqual(env["POOL_PARENT_RUN_ID"], "parent-review")
        self.assertEqual(len(self.routed), 2)
        self.assertEqual(self.routed[1][1]["excluded_hosts"], ["ubuntu0"])
        self.assertIsNone(self.routed[1][1]["requested_model"])
        self.assertEqual(self.routed[1][1]["pool"], "glm")
        self.assertEqual(self.artifact(".request.packet").read_bytes(),
                         b"read only independent review\n")
        launch = json.loads(self.artifact(".request-launch.json").read_text())
        self.assertEqual(launch["state"], "LAUNCH_ATTEMPT_RESERVED")

    def test_no_healthy_host_retains_task_and_proves_no_launch(self):
        self.readings["ubuntu1"] = 96.0
        with self.assertRaisesRegex(task.FabricTaskError, "NO_ELIGIBLE_THERMAL_HOST"):
            self.invoke()
        self.assertEqual(self.launched, [])
        self.assertFalse(self.artifact(".request-launch.json").exists())
        self.assertEqual(task.inspect_run("thermal-review")["state"],
                         "REQUEST_REFUSED_BEFORE_LAUNCH")
        refusal = json.loads(self.artifact(".request-refused.json").read_text())
        self.assertIs(refusal["launch_attempted"], False)
        self.assertEqual(self.artifact(".request.packet").read_bytes(),
                         b"read only independent review\n")

    def test_remote_transport_refusal_blocks_alternative_and_execution(self):
        self.readings["ubuntu0"] = task.FabricTaskError("THERMAL_PREFLIGHT_UNAVAILABLE")
        with self.assertRaisesRegex(task.FabricTaskError, "THERMAL_PREFLIGHT_UNAVAILABLE"):
            self.invoke()
        self.assertEqual(self.launched, [])
        self.assertEqual(len(self.routed), 1)
        self.assertFalse(self.artifact(".request-launch.json").exists())

    def test_missing_linux_thermal_enrollment_cannot_launch(self):
        self.registry["ubuntu0"].pop("require_thermal")
        with self.assertRaisesRegex(task.FabricTaskError,
                                    "THERMAL_PREFLIGHT_POLICY_INVALID"):
            self.invoke()
        self.assertEqual(self.launched, [])
        self.assertFalse(self.artifact(".request-launch.json").exists())
        self.assertEqual(task.inspect_run("thermal-review")["state"],
                         "REQUEST_REFUSED_BEFORE_LAUNCH")

    def test_opt_in_is_required_and_legacy_request_unchanged(self):
        self.assertEqual(self.invoke(enabled=False), 0)
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(self.launched[0][0][2], "ubuntu0")
        self.assertEqual(len(self.routed), 1)

    def test_manual_pool_scope_refused_before_task_artifact(self):
        with self.assertRaisesRegex(task.FabricTaskError, "PRELEASE_LIVE_THERMAL_SCOPE_REFUSED"):
            self.invoke(pool="glm")
        self.assertFalse(self.artifact(".request.json").exists())
        self.assertEqual(self.launched, [])

    def test_sealed_mode_cannot_silently_skip_opted_in_check(self):
        with patch.dict("os.environ", {"FABRIC_CANONICAL_PAID_MODE": "sealed-model-only-v1"}):
            with self.assertRaisesRegex(task.FabricTaskError,
                                        "PRELEASE_LIVE_THERMAL_SEALED_MODE_REFUSED"):
                self.invoke()
        self.assertFalse(self.artifact(".request.json").exists())
        self.assertEqual(self.launched, [])

    def test_completed_run_identity_must_not_be_replayed(self):
        self.assertEqual(self.invoke(), 0)
        with self.assertRaisesRegex(task.FabricTaskError, "REQUEST_RUN_ALREADY_EXISTS"):
            self.invoke()
        self.assertEqual(len(self.launched), 1)

    def test_missing_sensor_may_select_another_qualified_host(self):
        self.readings["ubuntu0"] = None
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.launched[0][0][2], "ubuntu1")

    def test_invalid_alias_is_not_interpreted_as_ssh_option(self):
        registry = {"ubuntu0": {"ssh_alias": "--ProxyCommand=evil",
                                "require_thermal": True, "cpu_tctl_limit_c": 84}}
        with self.assertRaisesRegex(task.FabricTaskError,
                                    "THERMAL_PREFLIGHT_ROUTE_UNQUALIFIED"):
            task._live_host_tctl_c("ubuntu0", registry)
        self.assertEqual(self.launched, [])

    def test_unchanged_cool_host_preserves_original_placement(self):
        self.readings["ubuntu0"] = 55.0
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.launched[0][0][2], "ubuntu0")
        self.assertEqual(len(self.routed), 1)


if __name__ == "__main__":
    unittest.main()
