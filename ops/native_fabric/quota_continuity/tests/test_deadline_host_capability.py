"""Deadline capability narrows only the unsupported local m2 transport."""
from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_adapter_continuity as adapter_fixture
import host_pick
import pick
import placement_view

ROOT = Path(__file__).resolve().parents[1]


class DeadlineHostCapability(unittest.TestCase):
    def setUp(self):
        self.registry = {
            "m2": {"platform": "darwin", "local": True},
            "remote-mac": {"platform": "darwin", "local": False},
            "ubuntu-fixture": {"platform": "linux", "local": False},
        }
        self.views = []
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(host_pick, "load_registry", return_value=self.registry))
        # Only the telemetry boundary is inert. Existing picker exclusion
        # composition and host ranking execute their actual source.
        def observed_view(registry, _state, _mode, **options):
            excluded = set(options["excluded"])
            self.views.append(excluded)
            rows = [{"host": name, "eligible": name not in excluded,
                "seat": entry["local"], "score": 100 - index}
                for index, (name, entry) in enumerate(registry.items())]
            choice = host_pick.choose_host(rows)
            return {"host_choice": choice["host"] if choice else None}
        self.stack.enter_context(patch.object(placement_view, "build_placement_view", side_effect=observed_view))

    def routes(self, host="auto", **extra):
        return pick._eligible_host_routes(host, required_modes=["minimax"], **extra)

    def test_only_m2_is_excluded_and_remote_darwin_stays_eligible(self):
        self.assertEqual(self.routes(excluded_hosts=["m2"])["minimax"], ("remote-mac", "minimax"))
        self.assertEqual(self.views, [{"m2"}])

    def test_capability_is_unioned_with_existing_host_and_platform_exclusions(self):
        self.assertEqual(self.routes("remote-mac", excluded_hosts=["m2"])["minimax"],
                         ("remote-mac", "minimax"))
        self.assertEqual(self.views[-1], {"m2", "ubuntu-fixture"})
        self.assertEqual(self.routes(required_platforms=["linux"], excluded_hosts=["m2"])["minimax"],
                         ("ubuntu-fixture", "minimax"))
        self.assertEqual(self.views[-1], {"m2", "remote-mac"})

    def test_ordinary_explicit_local_selection_keeps_original_behavior(self):
        self.assertEqual(self.routes("m2")["minimax"], ("m2", "minimax"))
        self.assertEqual(self.views[-1], {"remote-mac", "ubuntu-fixture"})

    def test_format_pick_forwards_capability_without_changing_economic_selection(self):
        with patch.object(pick, "load_pools", return_value={}), \
             patch.object(pick, "_selection_model", return_value=("fixture-model", "")), \
             patch.object(pick, "_format_pick", return_value="POOL=minimax MODEL=fixture-model") as economic:
            value = pick.format_pick("mechanical", host="auto", required_modes=["minimax"],
                                     excluded_hosts=["m2"])
        self.assertIn("HOST=remote-mac MODE=minimax", value)
        self.assertEqual(economic.call_args.kwargs["host_modes"], {"minimax": "minimax"})

    def test_malformed_exclusions_fail_before_host_reads_or_route_effects(self):
        with patch.object(pick, "_eligible_host_routes", side_effect=AssertionError("must not select")):
            for value in ("m2", ["m2", "m2"], ["../m2"], [None], ["host"] * 65):
                with self.subTest(value=value):
                    self.assertTrue(pick.format_pick("mechanical", host="auto",
                        excluded_hosts=value).startswith("NONE reason=invalid excluded_hosts"))


class DeadlineRequestCapability(unittest.TestCase):
    def test_only_deadline_requests_pass_exact_m2_capability(self):
        case = adapter_fixture.Adapter(methodName="runTest")
        case.setUp()
        self.addCleanup(case.doCleanups)
        api = adapter_fixture.api
        seen = []
        def route(_task, **options):
            seen.append(options)
            return "POOL=minimax MODEL=fixture-model HOST=fixture MODE=minimax"
        with patch.object(api.pick, "format_pick", side_effect=route), \
             patch.object(api, "_route_with_deadline", side_effect=lambda task, options, *rest: route(task, **options)):
            for run, deadline in (("ordinary-capability", None),
                                  ("deadline-capability", time.monotonic_ns() + 300_000_000_000)):
                result = api.request(run, "mechanical", cwd="~", packet=None,
                    stdin_bytes=b"inert fixture\n", root_id="root", parent_run_id="parent",
                    task_complexity="C0_MECHANICAL", request_deadline_ns=deadline)
                self.assertEqual(result, 0)
        self.assertNotIn("excluded_hosts", seen[0])
        self.assertEqual(seen[1]["excluded_hosts"], ["m2"])
        self.assertNotIn("required_platforms", seen[1])

    def test_direct_m2_deadline_refuses_before_local_slot_but_ordinary_call_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="fabric-local-deadline-") as raw:
            root = Path(raw)
            for name in ("remote_sub.sh", "remote_sub_helpers.py", "commission_deadline.py"):
                shutil.copyfile(ROOT / "candidate" / name, root / name)
            packet = root / "packet.txt"
            packet.write_text("inert local fixture\n")
            local = root / "local-fixture"
            local.write_text('#!/bin/sh\nprintf "local fixture invoked\\n" > "$LOCAL_FIXTURE_RECORD"\n')
            local.chmod(0o700)
            for run, active in (("deadline-local", True), ("ordinary-local", False)):
                marker = root / (run + ".invoked")
                env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": os.environ["HOME"],
                    "REMOTE_SUB_PYTHON": sys.executable, "REMOTE_SUB_LOCAL_CMD": str(local),
                    "LOCAL_FIXTURE_RECORD": str(marker), "PYTHONDONTWRITEBYTECODE": "1"}
                if active:
                    env["POOL_COMMISSION_DEADLINE_NS"] = str(time.monotonic_ns() + 5_000_000_000)
                result = subprocess.run(["/bin/bash", str(root / "remote_sub.sh"), "m2", "minimax",
                    str(packet), "~", "fixture-model", "--run-id", run], env=env,
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 78 if active else 0, result.stderr)
                self.assertEqual(marker.exists(), not active)
                if active:
                    self.assertIn("COMMISSION_LOCAL_TRANSPORT_REFUSED rc=78", result.stderr)
                    self.assertNotIn("LEASE_WAIT", result.stderr)
                    self.assertNotIn("LAUNCH stdout=", result.stderr)


if __name__ == "__main__":
    unittest.main()
