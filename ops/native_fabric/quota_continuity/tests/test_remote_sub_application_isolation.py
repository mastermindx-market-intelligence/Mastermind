"""APPLICATION carrier isolation: capacity, concurrency and custody.

The application purpose shares the incumbent physical lane, admission lock and
owned process groups with the worker fixtures, adds no parallel capacity
counter and no worker provider acquire/heartbeat/release/ledger write.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
SOURCE = ROOT / "source"
sys.path[:0] = [str(ROOT / "tests"), str(CANDIDATE), str(SOURCE)]
import lane_runtime
from test_remote_sub_application_carrier import ApplicationFixture

SLEEPY_CHILD = ("import sys,time;sys.stdin.read();time.sleep(4);"
                "sys.stdout.write('APPLICATION-OK')")
AUDIT_WRAPPER = '''import json, os, sys
sys.path.insert(0, {ext!r})
recorded = []
def audit(event, args):
    if event == "subprocess.Popen":
        recorded.append(" ".join(str(a) for a in args[1] if a))
    elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        recorded.append(os.fsdecode(args[0]))
sys.addaudithook(audit)
import remote_sub_exec as remote
code = remote.main(sys.argv[1:])
open({report!r}, "w").write(json.dumps(recorded))
raise SystemExit(code)
'''


class ApplicationIsolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = ApplicationFixture(self.root, child=SLEEPY_CHILD)

    def test_two_unrelated_invocations_own_independent_processes_and_captures(self):
        slow = self.fixture.envelope("app-iso-slow", remaining_seconds=1)
        fast = self.fixture.envelope("app-iso-fast")
        paths = {}
        for run, envelope in (("app-iso-slow", slow), ("app-iso-fast", fast)):
            paths[run] = self.root / (run + ".dispatch.json")
            paths[run].write_text(json.dumps(envelope))
        env = self.fixture.env()
        first = subprocess.Popen(
            [sys.executable, str(self.fixture.ext / "remote_sub_exec.py"),
             "app-iso-slow", "application", str(paths["app-iso-slow"]), "~",
             "model-fixture"], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        second = subprocess.Popen(
            [sys.executable, str(self.fixture.ext / "remote_sub_exec.py"),
             "app-iso-fast", "application", str(paths["app-iso-fast"]), "~",
             "model-fixture"], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        first_rc, second_rc = first.wait(timeout=120), second.wait(timeout=120)
        self.assertEqual(second_rc, 0, second.stderr.read().decode())
        self.assertNotEqual(first_rc, 0)
        slow = self.fixture.terminal("app-iso-slow")
        fast = self.fixture.terminal("app-iso-fast")
        self.assertIsNotNone(slow)
        self.assertIsNotNone(fast)
        self.assertEqual(fast["status"], "completed")
        self.assertNotEqual(slow["process"]["pid"], fast["process"]["pid"])
        self.assertNotEqual(slow["process"]["pgid"], fast["process"]["pgid"])
        self.assertNotEqual(slow["process"]["label"], fast["process"]["label"])
        self.assertNotEqual(slow["capture"]["stdout_bytes"],
                            fast["capture"]["stdout_bytes"])
        for run in ("app-iso-slow", "app-iso-fast"):
            receipt = self.fixture.ext / "lanes" / (run + ".process.jsonl")
            self.assertTrue(receipt.is_file())
            self.assertEqual(len(receipt.read_text().splitlines()), 1)
            self.assertTrue((self.fixture.ext / "lanes" /
                             (run + ".application-prepare.json")).is_file())

    def test_the_application_shares_the_physical_lane_and_a_full_lane_refuses(self):
        env = self.fixture.env()
        env["LANE_MAX_ACTIVE"] = "1"
        lease = lane_runtime.LaneLease.acquire(
            self.fixture.ext / "active", key="occupied-lane", label="occupied-lane",
            env=env, reconcile_unreleased=True)
        self.addCleanup(lease.release)
        result = self.fixture.run("app-full-1", self.fixture.envelope("app-full-1"),
                                  extra_env={"LANE_MAX_ACTIVE": "1"})
        self.assertEqual(result.returncode, 75)
        self.assertIn(b"APPLICATION_ADMISSION_REFUSED", result.stderr)
        lanes = self.fixture.ext / "lanes"
        self.assertFalse((lanes / "app-full-1.process.jsonl").exists())
        self.assertFalse((lanes / "app-full-1.application-prepare.json").exists())

    def test_the_application_branch_touches_no_worker_provider_or_ledger_owner(self):
        path = self.root / "app-audit-1.dispatch.json"
        path.write_text(json.dumps(self.fixture.envelope("app-audit-1")))
        report = self.root / "audit.json"
        script = AUDIT_WRAPPER.format(ext=str(self.fixture.ext), report=str(report))
        result = subprocess.run([sys.executable, "-c", script,
                                 str(self.fixture.ext / "remote_sub_exec.py"),
                                 "app-audit-1", "application", str(path), "~",
                                 "model-fixture"],
                                env=self.fixture.env(), capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for value in json.loads(report.read_text()):
            self.assertNotIn("lease_broker", value)
            self.assertNotIn("pool_ledger", value)
        lanes = self.fixture.ext / "lanes"
        self.assertFalse((lanes / "app-audit-1.usage.json").exists())
        self.assertFalse((lanes / "app-audit-1.provider.json").exists())

    def test_the_next_intentional_step_keeps_the_original_lease_and_model(self):
        first = self.fixture.envelope("app-turn-1", turn_id="turn-shared",
                                      lease_id="lease-shared")
        second = self.fixture.envelope("app-turn-2", turn_id="turn-shared",
                                       lease_id="lease-shared")
        self.assertNotEqual(first["dispatch_id"], second["dispatch_id"])
        self.assertEqual(first["lease_id"], second["lease_id"])
        for run, envelope in (("app-turn-1", first), ("app-turn-2", second)):
            result = self.fixture.run(run, envelope)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            terminal = self.fixture.terminal(run)
            self.assertEqual(terminal["lease_id"], envelope["lease_id"])
            self.assertEqual(terminal["account"], envelope["account"])
            self.assertEqual(terminal["model"], envelope["model"])
            self.assertEqual(terminal["turn_id"], "turn-shared")
            self.assertEqual(terminal["process"]["label"], run)
        lanes = self.fixture.ext / "lanes"
        self.assertFalse((lanes / "app-turn-1.usage.json").exists())
        self.assertFalse((lanes / "app-turn-2.provider.json").exists())


if __name__ == "__main__":
    unittest.main()
