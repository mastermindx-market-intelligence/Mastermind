"""Prelease thermal host reselection: no provider lease or worker side effects."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
import fabric_task as task
import host_pick


class ThermalHostPreleaseTests(unittest.TestCase):
    def setUp(self):
        self.route = {
            "POOL": "glm", "MODE": "glm", "MODEL": "glm-5.3", "HOST": "ubuntu0",
        }
        self.other = {
            **self.route, "HOST": "ubuntu1",
        }
        self.registry = {
            "ubuntu0": {"ssh_alias": "ubuntu0", "platform": "linux",
                        "require_thermal": True, "cpu_tctl_limit_c": 84},
            "ubuntu1": {"ssh_alias": "ubuntu1", "platform": "linux",
                        "require_thermal": True, "cpu_tctl_limit_c": 84},
        }
        self.options = {"host": "auto", "pool": None,
                        "requested_model": None, "route_key": "review-one"}

    def test_hot_host_reselected_with_same_pool_model_mode(self):
        calls = []
        def selector(options, ordinal):
            calls.append((options.copy(), ordinal))
            return "POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm"
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            route = task._prelease_select_cool_host(
                self.route, self.options, selector,
                observe=lambda host, _: 90.0 if host == "ubuntu0" else 57.0)
        self.assertEqual(route, self.other)
        self.assertEqual(len(calls), 1)
        selected, ordinal = calls[0]
        self.assertEqual(ordinal, 1)
        self.assertEqual(selected["pool"], "glm")
        self.assertIsNone(selected["requested_model"])
        self.assertEqual(selected["excluded_hosts"], ["ubuntu0"])
        self.assertEqual(selected["route_key"], "review-one")

    def test_existing_caller_exact_model_pin_survives_selection(self):
        options = dict(self.options, requested_model="glm-5.3")
        chosen = []
        def selector(updated, ordinal):
            chosen.append(updated)
            return "POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm"
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            result = task._prelease_select_cool_host(
                self.route, options, selector,
                observe=lambda host, _: 90.0 if host == "ubuntu0" else 57.0)
        self.assertEqual(result["MODEL"], "glm-5.3")
        self.assertEqual(chosen[0]["requested_model"], "glm-5.3")

    def test_unreadable_physical_sensor_excludes_only_that_host(self):
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            route = task._prelease_select_cool_host(
                self.route, self.options,
                lambda *_: "POOL=glm MODEL=glm-5.3 HOST=ubuntu1 MODE=glm",
                observe=lambda host, _: None if host == "ubuntu0" else 55.0)
        self.assertEqual(route["HOST"], "ubuntu1")

    def test_cool_host_keeps_original_route(self):
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            route = task._prelease_select_cool_host(
                self.route, self.options,
                lambda *_: self.fail("unexpected reselect"),
                observe=lambda *_: 60.0)
        self.assertEqual(route, self.route)

    def test_transport_or_permission_failure_is_not_host_retry(self):
        def fail_probe(*_):
            raise task.FabricTaskError("THERMAL_PREFLIGHT_UNAVAILABLE")
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(task.FabricTaskError, "THERMAL_PREFLIGHT_UNAVAILABLE"):
                task._prelease_select_cool_host(
                    self.route, self.options,
                    lambda *_: self.fail("must not try alternative after unknown SSH"),
                    observe=fail_probe)

    def test_no_eligible_host_refuses_before_any_launch(self):
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(task.FabricTaskError, "NO_ELIGIBLE_THERMAL_HOST"):
                task._prelease_select_cool_host(
                    self.route, self.options,
                    lambda *_: "NONE reason=no eligible remote mode",
                    observe=lambda *_: 90.0)

    def test_different_pool_or_model_never_substituted(self):
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            for substitute in (
                "POOL=cursor MODEL=cursor-grok-4.6-high HOST=ubuntu1 MODE=cursor",
                "POOL=glm MODEL=glm-5.3-flash HOST=ubuntu1 MODE=glm",
            ):
                with self.subTest(substitute=substitute):
                    with self.assertRaisesRegex(task.FabricTaskError,
                                                "THERMAL_PREFLIGHT_ROUTE_CHANGED"):
                        task._prelease_select_cool_host(
                            self.route, self.options,
                            lambda *_: substitute,
                            observe=lambda *_: 100.0)

    def test_malformed_thermal_policy_never_downgrades_to_unenrolled(self):
        self.registry["ubuntu0"]["require_thermal"] = "false"
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(task.FabricTaskError,
                                        "THERMAL_PREFLIGHT_POLICY_INVALID"):
                task._prelease_select_cool_host(
                    self.route, self.options,
                    lambda *_: self.fail("no route authorized"),
                    observe=lambda *_: self.fail("invalid host must not probe"))

    def test_linux_thermal_enrollment_missing_or_disabled_refuses(self):
        for value in (None, False):
            entry = self.registry["ubuntu0"]
            if value is None:
                entry.pop("require_thermal", None)
            else:
                entry["require_thermal"] = value
            with self.subTest(thermal_enrollment=value):
                with patch.object(host_pick, "load_registry", return_value=self.registry):
                    with self.assertRaisesRegex(
                            task.FabricTaskError, "THERMAL_PREFLIGHT_POLICY_INVALID"):
                        task._prelease_select_cool_host(
                            self.route, self.options,
                            lambda *_: self.fail("must not reselect malformed host"),
                            observe=lambda *_: self.fail("must not probe malformed host"))

    def test_missing_platform_cannot_skip_thermal_policy(self):
        self.registry["ubuntu0"].pop("platform")
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(task.FabricTaskError,
                                        "THERMAL_PREFLIGHT_POLICY_INVALID"):
                task._prelease_select_cool_host(
                    self.route, self.options,
                    lambda *_: self.fail("must not route malformed host"),
                    observe=lambda *_: self.fail("must not probe malformed host"))

    def test_non_capacity_refusal_remains_explicit(self):
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(task.FabricTaskError,
                                        "THERMAL_PREFLIGHT_RESELECT_REFUSED"):
                task._prelease_select_cool_host(
                    self.route, self.options,
                    lambda *_: "NONE reason=invalid excluded_hosts or host",
                    observe=lambda *_: 99.0)

    def test_unenrolled_host_does_not_gain_extra_admission(self):
        # macOS registry entries intentionally use another admission path.
        self.registry["ubuntu0"]["platform"] = "darwin"
        self.registry["ubuntu0"]["require_thermal"] = False
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            self.assertEqual(task._prelease_select_cool_host(
                self.route, self.options,
                lambda *_: self.fail("unexpected route"),
                observe=lambda *_: self.fail("unexpected temperature call")), self.route)

    def test_reselect_cannot_choose_excluded_host(self):
        with patch.object(host_pick, "load_registry", return_value=self.registry):
            with self.assertRaisesRegex(task.FabricTaskError,
                                        "THERMAL_PREFLIGHT_ROUTE_CHANGED"):
                task._prelease_select_cool_host(
                    self.route, self.options,
                    lambda *_: "POOL=glm MODEL=glm-5.3 HOST=ubuntu0 MODE=glm",
                    observe=lambda *_: 90.0)

    def test_live_probe_executes_physical_sensor_source_readonly(self):
        observed = []
        def fake_process(args, **kwargs):
            observed.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, "65.500\n", "")
        with patch.object(task.subprocess, "run", side_effect=fake_process):
            value = task._live_host_tctl_c("ubuntu0", self.registry)
        self.assertEqual(value, 65.5)
        self.assertEqual(len(observed), 1)
        args, kwargs = observed[0]
        self.assertEqual(args[0], "ssh")
        self.assertEqual(args[6], "ubuntu0")
        self.assertIn("_linux_cpu_tctl_c", args[7])
        self.assertIn("k10temp", args[7])
        self.assertEqual(kwargs["timeout"], 12)

    def test_malformed_remote_stdout_fails_closed(self):
        def fake_process(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "65.0\nREADY\n", "")
        with patch.object(task.subprocess, "run", side_effect=fake_process):
            with self.assertRaisesRegex(task.FabricTaskError,
                                        "THERMAL_PREFLIGHT_UNQUALIFIED"):
                task._live_host_tctl_c("ubuntu0", self.registry)


if __name__ == "__main__":
    unittest.main()
