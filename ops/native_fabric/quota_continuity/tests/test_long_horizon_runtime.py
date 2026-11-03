"""No-worker regression for finite long-horizon Fabric execution and original custody.

The test never launches a provider, authenticates a host, allocates a broker lease,
or alters an existing run. The selected native candidate and original deadline
owners are the only subjects.
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
sys.path.insert(0, str(CANDIDATE))

import commission_deadline
import remote_sub_helpers
import slot


class LongHorizonRuntimeTests(unittest.TestCase):
    @staticmethod
    def _runtime_floor(complexity: str, initial: int, *, mode: str = "glm",
                       original_remaining: str = "") -> tuple[int, str, int]:
        body = (CANDIDATE / "remote_sub.sh").read_text()
        first = body.index("RUNTIME_FLOOR_SECS=0")
        last = body.index("\nADMISSION_WAIT_SECS=", first)
        fragment = body[first:last]
        # This is the real pre-acquire shell validation; no shell sourcing,
        # broker, network, provider or worker is reachable.
        script = (
            'log() { :; }; RC=0; POLL_SECS=30; '
            + 'MODE=' + mode + '; MAX_SECS=' + str(initial) + '; '
            + 'POOL_TASK_COMPLEXITY=' + complexity + '; '
            + 'POOL_COMMISSION_REMAINING_SECONDS=' + original_remaining + '; '
            + fragment + '\n'
            + 'printf "%s|%s|%s" "$MAX_SECS" "$RUNTIME_FLOOR_SECS" "$RC"\n'
        )
        result = subprocess.run(["bash", "-c", script], capture_output=True,
                                text=True, timeout=3, check=False)
        return result.returncode, result.stdout.strip(), result.stderr

    def test_classified_runtime_floors_and_legacy_short_path(self):
        for complexity, mode, initial, expected in (
            ("C0_MECHANICAL", "glm", 210, "210|0|0"),
            ("C1_ROUTINE_BOUNDED", "glm", 210, "210|0|0"),
            ("C2_COMPLEX_BOUNDED", "glm", 210, "7200|7200|0"),
            ("C3_FRONTIER_JUDGMENT", "glm", 210, "14400|14400|0"),
            ("C3_FRONTIER_JUDGMENT", "go-codex", 210, "210|0|0"),
        ):
            with self.subTest(complexity=complexity, mode=mode):
                rc, output, error = self._runtime_floor(complexity, initial, mode=mode)
                self.assertEqual(rc, 0, error)
                self.assertEqual(output, expected)

    def test_original_commission_remaining_narrows_c3_after_floor(self):
        rc, output, error = self._runtime_floor("C3_FRONTIER_JUDGMENT",
                                                7200, original_remaining="1800")
        self.assertEqual(rc, 0, error)
        self.assertEqual(output, "1800|14400|0")
        rc, output, error = self._runtime_floor("C3_FRONTIER_JUDGMENT",
                                                7200, original_remaining="14401")
        self.assertEqual(rc, 2, error)
        self.assertEqual(output, "")

    def test_five_digit_duration_is_accepted_but_oversize_is_refused(self):
        with mock.patch.dict(os.environ, {"POOL_COMMISSION_REMAINING_SECONDS": "14400"},
                             clear=True):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                remote_sub_helpers.deadline_init()
            self.assertGreater(int(output.getvalue()), time.monotonic_ns())
        with mock.patch.dict(os.environ, {"POOL_COMMISSION_REMAINING_SECONDS": "14401"},
                             clear=True):
            with self.assertRaises(ValueError):
                remote_sub_helpers.deadline_init()
        executor = (CANDIDATE / "remote_sub_exec.py").read_text()
        self.assertIn("not re.fullmatch(r'[1-9][0-9]{0,4}', commission_budget)", executor)
        self.assertIn("int(commission_budget) > 14400", executor)

    def test_monotonic_deadline_is_finite_and_never_extended(self):
        initial = 9_000_000_000
        until = commission_deadline.narrow_deadline_ns(None, 14400, now_ns=initial)
        self.assertEqual(until, initial + 14400 * 1_000_000_000)
        self.assertEqual(commission_deadline.narrow_deadline_ns(
            until, 14400, now_ns=initial + 200 * 1_000_000_000), until)
        self.assertEqual(commission_deadline.narrow_deadline_ns(
            until, 150, now_ns=initial + 200 * 1_000_000_000),
            initial + 350 * 1_000_000_000)
        with self.assertRaises(commission_deadline.CommissionDeadlineInvalid):
            commission_deadline.narrow_deadline_ns(None, 14401, now_ns=initial)
        with self.assertRaises(commission_deadline.CommissionDeadlineInvalid):
            commission_deadline.narrow_deadline_ns(None, float("inf"),
                                                    now_ns=initial)

    def test_slot_hard_fuse_and_lease_ttl_do_not_expand_infinitely(self):
        with mock.patch.dict(os.environ, {"SLOT_CHILD_TIMEOUT_SECONDS": "14400"}):
            self.assertEqual(slot._child_runtime_limit(), 14400.0)
        with mock.patch.dict(os.environ, {"SLOT_CHILD_TIMEOUT_SECONDS": "14401"}):
            with self.assertRaises(slot.LaneRuntimeConfigError):
                slot._child_runtime_limit()

    def test_native_lease_window_requires_original_sufficient_ttl(self):
        def observe(ttl: int):
            now = int(time.time())
            lease = dict(id="test-lease", orchestrator_id="test-root",
                         pool="glm", account="test-account", host="test-host",
                         state="held", granted_at=now - 10, ttl=ttl)
            broker = types.ModuleType("lease_broker")
            class FakeBroker:
                def heartbeat(self, lease_id):
                    return lease_id == lease["id"]
                def snapshot(self):
                    return {"leases": [lease]}
            broker.default_broker = FakeBroker
            with mock.patch.dict(sys.modules, {"lease_broker": broker}):
                with mock.patch.object(sys, "argv", [
                    "remote_sub_helpers.py", str(CANDIDATE), "test-lease",
                    "test-root", "test-account", "test-host", "14340", "glm"
                ]):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        remote_sub_helpers.native_window()
                    return output.getvalue()
        window = observe(14700).strip().split()
        self.assertEqual(len(window), 2)
        self.assertEqual(int(window[1]) - int(window[0]), 14340)
        with self.assertRaises(AssertionError):
            observe(7200)

    def test_selected_owners_retained_and_special_no_slot_limited(self):
        remote = (CANDIDATE / "remote_sub.sh").read_text()
        self.assertIn("MAX_SECS must not exceed 14400", remote)
        self.assertIn("PROVIDER_LEASE_TTL=15000", remote)
        self.assertIn("PRESERVE_LEASE=1", remote)
        self.assertIn("EFFECT_UNKNOWN timeout max_secs=$MAX_SECS", remote)
        child = (CANDIDATE / "remote_sub_exec.py").read_text()
        self.assertIn("maximum=14400.0", child)
        nocap = (CANDIDATE / "oc_free_exec.sh").read_text()
        self.assertIn("C3_FRONTIER_JUDGMENT) _OC_FREE_TIMEOUT_DEFAULT=14400", nocap)
        self.assertIn("OC_FREE_TIMEOUT must be between 60 and 14400 seconds", nocap)
        self.assertIn("go-codex", remote)


if __name__ == "__main__":
    unittest.main()
