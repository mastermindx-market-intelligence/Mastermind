"""No-worker regression for transport-vs-remote-child timeout observation margin.

The original run identity, broker lease and terminal-status owner remain unchanged.
The tests extract and execute only the pure local runtime-budget shell function.
No network, provider, worker, lease or credential is used.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
PATHS = (
    ROOT / 'candidate/remote_sub.sh',
    REPO / 'ops/native_fabric/grok47/overlay/remote_sub.sh',
)


def shell_function(path):
    source = path.read_text()
    start = source.index('commission_refresh_runtime() {')
    end = source.index('\n}', start)
    return source[start:end + 2]


def budget(path, maximum, poll):
    assert isinstance(maximum, int) and 1 <= maximum <= 7200
    assert isinstance(poll, int) and 1 <= poll <= maximum
    script = (
        f'COMMISSION_ACTIVE=0; MAX_SECS={maximum}; POLL_SECS={poll}; '
        + shell_function(path)
        + '\ncommission_refresh_runtime regression\n'
        + 'printf "%s:%s" "$MAX_SECS" "$CHILD_TIMEOUT"\n'
    )
    result = subprocess.run(['bash', '-c', script], text=True,
                            capture_output=True, timeout=4, check=True)
    a, b = result.stdout.strip().split(':')
    return int(a), int(b)


class TerminalPollBudgetTests(unittest.TestCase):
    def test_max_fuse_unchanged_and_two_interval_reserve(self):
        for file in PATHS:
            for maximum, poll, expected_child in (
                (7200, 30, 7140),
                (3600, 30, 3540),
                (3600, 10, 3580),
                (210, 10, 190),
                (60, 30, 30),
            ):
                with self.subTest(path=file.name, maximum=maximum, poll=poll):
                    fuse, child = budget(file, maximum, poll)
                    self.assertEqual(fuse, maximum)
                    self.assertEqual(child, expected_child)
                    self.assertGreater(child, 0)
                    self.assertLessEqual(child, fuse)

    def test_edge_cases_do_not_make_negative_timeout(self):
        for file in PATHS:
            for maximum, poll, child_expected in ((45, 30, 15), (30, 30, 30), (2, 1, 1)):
                with self.subTest(path=file.name, maximum=maximum, poll=poll):
                    self.assertEqual(budget(file, maximum, poll), (maximum, child_expected))

    def test_commission_deadline_still_narrows_total_runtime(self):
        # Commission-owned workers retain the original deadline-command owner.
        # Exercise the existing deadline-seconds invocation with a safe stub.
        with tempfile.TemporaryDirectory(prefix='poll-margin-deadline-') as tmp:
            stub = Path(tmp) / 'deadline-seconds.sh'
            stub.write_text('#!/bin/sh\nprintf \"3600\\n\"\n')
            stub.chmod(0o700)
            for file in PATHS:
                script = (
                    f'COMMISSION_ACTIVE=1; MAX_SECS=7200; POLL_SECS=30; '
                    f'REMOTE_SUB_PYTHON={stub}; HERE={tmp}; '
                    + shell_function(file)
                    + '\ncommission_refresh_runtime regression\n'
                    + 'printf "%s:%s" "$MAX_SECS" "$CHILD_TIMEOUT"\n'
                )
                result = subprocess.run(['bash', '-c', script], text=True,
                                        capture_output=True, timeout=4, check=True)
                self.assertEqual(result.stdout.strip(), '3600:3540')

    def test_late_remote_rc_can_be_observed_with_new_margin(self):
        # 2026-10-22 intl-gs transport observed only 30-sec polls, with
        # remote timeout .rc files appearing after the last in-fuse poll.
        # A deterministic 14s start+settle tail demonstrates the regression:
        # the old single-poll margin misses, the new double-poll margin catches.
        maximum, poll, start_and_settle = 7200, 30, 14
        last_poll_before_fuse = ((maximum - 1) // poll) * poll
        old_child = maximum - poll
        self.assertGreater(old_child + start_and_settle, last_poll_before_fuse)
        for file in PATHS:
            _, new_child = budget(file, maximum, poll)
            self.assertLessEqual(new_child + start_and_settle, last_poll_before_fuse)

    def test_uncertain_effect_and_existing_controller_fuse_not_modified(self):
        for file in PATHS:
            body = file.read_text()
            self.assertIn('while [ $((SECONDS - WAIT_STARTED_SECONDS)) -lt "$MAX_SECS" ]; do', body)
            self.assertIn('EFFECT_UNKNOWN timeout max_secs=$MAX_SECS rc_file_missing=1; preserve broker lease until TTL', body)
            self.assertIn('PRESERVE_LEASE=1', body)
            self.assertIn('MAX_SECS must not exceed 7200', body)

    def test_native_inventory_closure_and_original_preimage(self):
        manifest = json.loads((ROOT / 'rollout/native-manifest.json').read_text())
        inventory = json.loads((ROOT / 'rollout/native-source-inventory.json').read_text())
        preimages = json.loads((ROOT / 'rollout/native-preimages.json').read_text())['files']
        candidate = ROOT / 'candidate/remote_sub.sh'
        original = ROOT / 'source/remote_sub.sh'
        # The closed, hash-pinned forward candidate preserves both reviewed
        # Grok behavior and caller UTC narrowing. Both distinct launchers keep
        # their real runtime-margin checks above; this asserts the actual source.
        selected = candidate
        self.assertEqual(hashlib.sha256(selected.read_bytes()).hexdigest(),
                         'eb7ae5e3288a9f3a49eb5eab14a5481501cced21f72b646f9891fc5b83981bc0')
        self.assertEqual(inventory['files']['ext/remote_sub.sh']['source'],
                         'candidate/remote_sub.sh')
        self.assertEqual(hashlib.sha256(selected.read_bytes()).hexdigest(),
                         manifest['ext/remote_sub.sh'])
        self.assertEqual(inventory['files']['ext/remote_sub.sh']['sha256'],
                         manifest['ext/remote_sub.sh'])
        self.assertTrue(candidate.is_file())
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),
                         preimages['remote_sub.sh'])


if __name__ == '__main__':
    unittest.main()
