"""Fast same-carrier result observations and bounded broker grant pickup.

No host transport, worker, credential, quota ledger, or production lease is used.
The pure Bash scheduling policy is extracted from the *actual* source to avoid
testing an independently reimplemented expectation.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
sys.path.insert(0, str(CANDIDATE))



def _poll_function():
    s = (CANDIDATE / "remote_sub.sh").read_text()
    a = s.index("fabric_poll_delay() {")
    b = s.index("\n}", a) + 2
    return s[a:b]


def _heartbeat_function():
    s = (CANDIDATE / "remote_sub.sh").read_text()
    a = s.index("fabric_poll_heartbeat_due() {")
    b = s.index("\n}", a) + 2
    return s[a:b]


def schedule(max_secs=14400, interval=30, failures=0):
    """Execute the real shell policy with virtual time, never sleep."""
    script = (
        f'POLL_SECS={interval}\n' + _poll_function() + "\n"
        + f'clock=0; max={max_secs}; failures={failures}\n'
        + 'while [ "$clock" -lt "$max" ]; do\n'
        + '  printf "%s\\n" "$clock"\n'
        + '  left=$((max - clock))\n'
        + '  fabric_poll_delay "$clock" "$left" "$failures"\n'
        + '  [ "$FABRIC_POLL_DELAY_S" -gt 0 ] || exit 97\n'
        + '  clock=$((clock + FABRIC_POLL_DELAY_S))\n'
        + 'done\n'
    )
    result = subprocess.run(
        ["/bin/bash", "-c", script], capture_output=True, text=True,
        check=True, timeout=5,
    )
    return [int(x) for x in result.stdout.splitlines()]


def first_observation(points, ready):
    return next(t for t in points if t >= ready)


class AdaptiveResultPollingTests(unittest.TestCase):
    def test_numeric_preflight_rejects_zero_overflow_and_oversized_poll(self):
        source = (CANDIDATE / "remote_sub.sh").read_text()
        start = source.index('case "$POLL_SECS" in')
        stop = source.index('if [ "$MAX_SECS" -lt "$POLL_SECS" ]; then', start)
        guard = source[start:stop]
        examples = (
            ("10", "14400", True),
            ("10", "7200", True),
            ("00010", "07200", False),
            ("00008", "7200", False),
            ("10", "07200", False),
            ("1", "1", True),
            ("00", "14400", False),
            ("00000", "14400", False),
            ("999999999999999999", "14400", False),
            ("30", "00000", False),
            ("30", "999999999999999999", False),
            ("30", "14401", False),
        )
        for poll, maximum, valid in examples:
            with self.subTest(poll=poll, maximum=maximum):
                script = ('POLL_SECS=' + poll + '; MAX_SECS=' + maximum
                          + '; RC=0; ' + guard + '\nprintf "ACCEPTED\n"')
                p = subprocess.run(['/bin/bash', '-c', script],
                                   text=True, capture_output=True,
                                   check=False, timeout=3)
                if valid:
                    self.assertEqual(p.returncode, 0, p.stderr)
                    self.assertIn("ACCEPTED", p.stdout)
                else:
                    self.assertEqual(p.returncode, 2, p.stderr)
                    self.assertNotIn("ACCEPTED", p.stdout)

    def test_result_ready_early_is_observed_far_faster_than_30s_static_poll(self):
        times = schedule(14400, 30)
        self.assertEqual(times[:15], list(range(0, 30, 2)))
        self.assertEqual(times[15:20], [30, 35, 40, 45, 50])
        observed = [first_observation(times, ready) - ready
                    for ready in range(1, 120)]
        baseline = [((ready + 29) // 30) * 30 - ready
                    for ready in range(1, 120)]
        self.assertLessEqual(max(observed), 4)
        self.assertLess(sum(observed) / len(observed), 0.2 * (sum(baseline) / len(baseline)))
        self.assertLess(first_observation(times, 7) - 7, 2)

    def test_midrange_uses_10s_then_long_run_returns_to_prior_cadence(self):
        times = schedule(14400, 30)
        early = [x for x in times if 120 <= x < 600]
        self.assertGreater(len(early), 20)
        self.assertTrue(all(b - a == 10 for a, b in zip(early, early[1:])))
        after = [x for x in times if x >= 600]
        self.assertTrue(all(b - a == 30 for a, b in zip(after, after[1:])))
        self.assertLessEqual(max(first_observation(times, ready)-ready
                                 for ready in range(120, 600)), 9)

    def test_long_horizon_ssh_probe_overhead_is_finite(self):
        for cap in (10, 30):
            with self.subTest(configured_poll_seconds=cap):
                actual = schedule(14400, cap)
                old = len(range(0, 14400, cap))
                self.assertGreaterEqual(len(actual), old)
                self.assertLessEqual(len(actual), old + 80)
                self.assertTrue(all(0 < b-a <= cap for a, b
                                    in zip(actual, actual[1:])))
                # The controller's previously verified double-poll margin
                # is unchanged, even though early observations are faster.
                self.assertIn("CHILD_TIMEOUT", (CANDIDATE / "remote_sub.sh").read_text())

    def test_large_configured_poll_never_misses_lease_heartbeat_window(self):
        # The poll configuration is a maximum, not permission to sleep for
        # hours while the native broker owner needs regular liveness.
        times = schedule(14400, 120)
        self.assertTrue(all(0 < b-a <= 30 for a, b in zip(times, times[1:])))
        self.assertLessEqual(max(first_observation(times, t)-t
                                 for t in (601, 1201, 3601, 12001)), 29)
        source = (CANDIDATE / 'remote_sub.sh').read_text()
        self.assertIn('[ "$proposed" -le 30 ] || proposed=30', source)

    def test_early_fast_observations_do_not_multiply_broker_heartbeats(self):
        for interval in (10, 30):
            with self.subTest(interval=interval):
                stamps = schedule(14400, interval)
                last = -interval
                heartbeat_times = []
                for stamp in stamps:
                    if stamp - last >= min(interval, 30):
                        heartbeat_times.append(stamp)
                        last = stamp
                self.assertEqual(heartbeat_times[0], 0)
                self.assertLessEqual(len(heartbeat_times),
                                     len(range(0, 14400, interval)) + 1)
                # Execute the actual Bash guard, not just a reimplementation.
                check = ('POLL_SECS=' + str(interval) + '\n'
                         + _heartbeat_function()
                         + '\nfor age in 0 9 10 29 30 31; do '
                         + 'if fabric_poll_heartbeat_due "$age"; '
                         + 'then printf "1"; else printf "0"; fi; done\n')
                run = subprocess.run(['/bin/bash', '-c', check],
                                     capture_output=True, text=True,
                                     check=True, timeout=3)
                expected = '001111' if interval == 10 else '000011'
                self.assertEqual(run.stdout, expected)
        source = (CANDIDATE / 'remote_sub.sh').read_text()
        self.assertIn('LAST_POLL_BROKER_HEARTBEAT=$SECONDS', source)
        self.assertIn('fabric_poll_heartbeat_due "$((SECONDS - LAST_POLL_BROKER_HEARTBEAT))"', source)

    def test_consecutive_failures_can_only_backoff_and_config_limit_wins(self):
        for limit in (1, 10, 30):
            for t in (0, 90, 300, 900):
                # Compute one interval at the exact same synthetic elapsed t.
                body = 'POLL_SECS=' + str(limit) + '\n' + _poll_function() + '\n'
                body += '\n'.join(
                    f'fabric_poll_delay {t} 100 {failed}; echo "$FABRIC_POLL_DELAY_S"'
                    for failed in range(4)) + '\n'
                p = subprocess.run(['/bin/bash','-c',body], text=True,
                                   capture_output=True, timeout=3, check=True)
                delays = [int(x) for x in p.stdout.split()]
                with self.subTest(limit=limit, elapsed=t):
                    self.assertEqual(delays, sorted(delays))
                    self.assertLessEqual(delays[-1], limit)
                    self.assertEqual(delays[-1], limit)
        s = (CANDIDATE / "remote_sub.sh").read_text()
        self.assertIn("POLL_FAILURE_STREAK=0", s)
        self.assertIn("POLL_FAILURE_STREAK=$((POLL_FAILURE_STREAK + 1))", s)
        self.assertIn('fabric_poll_delay "$elapsed" "$remaining" "$POLL_FAILURE_STREAK"', s)
        self.assertIn('EFFECT_UNKNOWN timeout max_secs=$MAX_SECS', s)
        self.assertIn('PRESERVE_LEASE=1', s)
        self.assertIn('commission_run poll "$SSH_CMD"', s)


if __name__ == "__main__":
    unittest.main()
