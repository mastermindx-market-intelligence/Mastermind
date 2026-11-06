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
            + 'MODE=' + mode + '; CANONICAL_PAID_ACTIVE=0; MAX_SECS=' + str(initial) + '; '
            + 'POOL_TASK_COMPLEXITY=' + complexity + '; '
            + 'POOL_COMMISSION_REMAINING_SECONDS=' + original_remaining + '; '
            + fragment + '\n'
            + 'printf "%s|%s|%s" "$MAX_SECS" "$RUNTIME_FLOOR_SECS" "$RC"\n'
        )
        result = subprocess.run(["bash", "-c", script], capture_output=True,
                                text=True, timeout=3, check=False)
        return result.returncode, result.stdout.strip(), result.stderr

    def test_inherited_broker_wait_reserves_cleanup_without_changing_worker_poll(self):
        from commission_deadline import CommissionDeadlineExpired
        source = (CANDIDATE / 'remote_sub.sh').read_text()
        self.assertIn('deadline-seconds "$LEASE_WAIT_SECS" broker', source)
        for arguments, remaining, expected in (
            (['helper','3600'],30.8,30),
            (['helper','3600','broker'],30.8,28),
            (['helper','3600','broker'],14000.9,3600),
            (['helper','3600','broker'],2.4,0),
            (['helper','5','broker'],30.8,5),
        ):
            with self.subTest(args=arguments), mock.patch.object(sys, 'argv', arguments), \
                 mock.patch('commission_deadline.read_deadline_ns', return_value=4000), \
                 mock.patch('commission_deadline.require_remaining', return_value=remaining):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    remote_sub_helpers.deadline_seconds()
                self.assertEqual(out.getvalue().strip(), str(expected))
        for args in (['helper','30','-1'], ['helper','30','unbounded'],
                     ['helper','30','broker','ignored']):
            with self.subTest(args=args), mock.patch.object(sys,'argv',args), \
                 mock.patch('commission_deadline.read_deadline_ns', return_value=4000):
                with self.assertRaises(ValueError):
                    remote_sub_helpers.deadline_seconds()
        with mock.patch.object(sys,'argv',['helper','3600','broker']), \
             mock.patch('commission_deadline.read_deadline_ns', return_value=4000), \
             mock.patch('commission_deadline.require_remaining',
                        side_effect=CommissionDeadlineExpired('commission_time_exhausted')):
            with self.assertRaises(CommissionDeadlineExpired):
                remote_sub_helpers.deadline_seconds()

    def test_classified_runtime_floors_and_legacy_short_path(self):
        for complexity, mode, initial, expected in (
            ("C0_MECHANICAL", "glm", 210, "210|0|0"),
            ("C1_ROUTINE_BOUNDED", "glm", 210, "210|0|0"),
            ("C2_COMPLEX_BOUNDED", "glm", 210, "7200|7200|0"),
            ("C3_FRONTIER_JUDGMENT", "glm", 210, "14400|14400|0"),
            ("C3_FRONTIER_JUDGMENT", "glm-codex", 210, "7200|14400|0"),
            ("C3_FRONTIER_JUDGMENT", "go-codex", 210, "210|0|0"),
        ):
            with self.subTest(complexity=complexity, mode=mode):
                rc, output, error = self._runtime_floor(complexity, initial, mode=mode)
                self.assertEqual(rc, 0, error)
                self.assertEqual(output, expected)

    def test_c3_controller_poll_stays_live_after_7200_seconds(self):
        """Exercise the installed controller's real poll guard at the 2h boundary.

        The real guard is verified in source, then its SECONDS clock token is
        replaced with an inert scalar to avoid wall-clock tick flakiness.
        The test never waits two hours, spawns a worker, polls SSH, or
        acquires a provider/broker lease. This
        protects the 4h C3 control fuse without claiming real-worker survival.
        """
        source = (CANDIDATE / "remote_sub.sh").read_text()
        loop_guard = (
            'while [ $((SECONDS - WAIT_STARTED_SECONDS)) -lt "$MAX_SECS" ]; do'
        )
        self.assertEqual(source.count(loop_guard), 1)
        predicate = loop_guard[len("while "):-len("; do")]
        clock_expression = "SECONDS - WAIT_STARTED_SECONDS"
        self.assertEqual(predicate.count(clock_expression), 1)
        predicate = predicate.replace(
            clock_expression, "CLOCK_SECONDS - WAIT_STARTED_SECONDS")
        for elapsed, deadline, should_continue in (
            (7199, 14400, True),
            (7200, 14400, True),
            (7201, 14400, True),
            (14339, 14400, True),
            (14399, 14400, True),
            (14400, 14400, False),
            # A separate inherited 2h cap must still terminate at its limit.
            (7201, 7200, False),
        ):
            with self.subTest(elapsed=elapsed, deadline=deadline):
                shell = (
                    f"WAIT_STARTED_SECONDS=0; MAX_SECS={deadline}; "
                    f"CLOCK_SECONDS={elapsed}; "
                    f"if {predicate}; then printf CONTINUE; else printf STOP; fi"
                )
                result = subprocess.run(
                    ["bash", "-c", shell], text=True, capture_output=True,
                    timeout=3, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                                 "CONTINUE" if should_continue else "STOP")

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

    def test_operator_child_start_window_preserved_as_duration(self):
        from fabric_operator_owner import OPERATOR_MIN_START_WINDOW_SECONDS
        self.assertEqual(OPERATOR_MIN_START_WINDOW_SECONDS, 660)
        source = (CANDIDATE / "fabric_operator_owner.py").read_text()
        self.assertIn("OPERATOR_MIN_START_WINDOW_SECONDS = 11 * 60", source)
        self.assertEqual(source.count("< OPERATOR_MIN_START_WINDOW_SECONDS"), 2)

    def test_operator_root_may_opt_into_four_hours_only(self):
        import tempfile
        from fabric_operator_owner import OperatorOwner
        from fabric_operator_contract import DelegationRefused, MAX_GRANT_SECONDS
        self.assertEqual(MAX_GRANT_SECONDS, 14400)
        with tempfile.TemporaryDirectory(prefix="fabric-op-long-window-") as tmp:
            home = Path(tmp)
            (home / "broker").mkdir(mode=0o700)
            import sqlite3
            db = home / "broker/leases.sqlite"
            sqlite3.connect(db).close()
            db.chmod(0o600)
            lock = home / "broker/leases.lock"
            lock.touch(mode=0o600)
            owner = OperatorOwner(here=home, clock=lambda: 10000.0)
            granted = owner.authorize_root("original-root", 1, 24400.0)
            self.assertEqual(granted["expires_at"], 24400.0)
            with self.assertRaises(DelegationRefused):
                owner.authorize_root("other-root", 1, 24401.0)
            with self.assertRaises(DelegationRefused):
                owner.authorize_root("original-root", 1, 18000.0)

    def test_glm_capability_route_remains_bounded_to_qualified_window(self):
        # The upstream GLM signed-capability issuer is still <=7500s.
        for complexity, initial in (("C2_COMPLEX_BOUNDED", 7200),
                                    ("C3_FRONTIER_JUDGMENT", 14400)):
            with self.subTest(complexity=complexity):
                rc, output, error = self._runtime_floor(complexity, initial,
                                                       mode="glm-codex")
                self.assertEqual(rc, 0, error)
                self.assertEqual(output.split("|")[0], "7200")
        issuer = ROOT / "source/glm_remote_capability.py"
        self.assertIn("not 1 <= ttl <= 7500", issuer.read_text())
        remote = (CANDIDATE / "remote_sub.sh").read_text()
        self.assertIn("GLM_CAPABILITY_WINDOW_NARROWED", remote)
        self.assertIn('[ "$CAP_TTL" -gt 7500 ] && CAP_TTL=7500', remote)

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
