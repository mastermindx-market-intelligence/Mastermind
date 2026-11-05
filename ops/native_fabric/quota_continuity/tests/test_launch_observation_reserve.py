"""No-worker proof of launch-observation reserve under original commission.

The actual reviewed shell policy is extracted from remote_sub.sh and executed
with a disposable deadline reader. No SSH, lease, model or worker is invoked.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / "candidate/remote_sub.sh"


def _policy():
    source = REMOTE.read_text()
    start = source.index("commission_refresh_runtime() {")
    end = source.index("\n}", start) + 2
    return source[start:end]


def _run(remaining, stage="launch", poll=10, active=True):
    with tempfile.TemporaryDirectory(prefix="fabric-observation-reserve-") as td:
        helper = Path(td) / "clock.sh"
        helper.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_REMAINING"\n')
        helper.chmod(0o700)
        script = (
            "log() { :; }; "
            f'COMMISSION_ACTIVE={1 if active else 0}; '
            f'POLL_SECS={poll}; MAX_SECS={remaining}; RC=0; '
            f'REMOTE_SUB_PYTHON="{helper}"; HERE="{td}";\n'
            + _policy() + "\n"
            + f'commission_refresh_runtime {stage}\n'
            + 'code=$?; printf "RC=%s MAX=%s CHILD=%s\\n" '
              '"$code" "$MAX_SECS" "${CHILD_TIMEOUT:-missing}"\n'
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True,
            timeout=4, env={**os.environ, "TEST_REMAINING": str(remaining)},
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()


class OriginalLaunchReserve(unittest.TestCase):
    def test_subfive_second_remaining_commission_refuses_new_launch(self):
        for remaining in (1, 2, 3, 4):
            with self.subTest(remaining=remaining):
                self.assertIn("RC=75", _run(remaining, stage="launch"))
        source = REMOTE.read_text()
        assert source.index('commission_refresh_runtime launch') < source.index('LAUNCH_ATTEMPT attempt=')

    def test_five_second_or_longer_commission_preserves_bounded_child(self):
        for remaining, expected in ((5, 5), (6, 6), (20, 10), (14400, 14380)):
            with self.subTest(remaining=remaining):
                state = _run(remaining, stage="launch")
                self.assertIn("RC=0", state)
                self.assertIn(f"CHILD={expected}", state)

    def test_prior_non_launch_terminal_collection_not_blocked_by_gate(self):
        for stage in ("poll", "broker", "observe"):
            with self.subTest(stage=stage):
                self.assertIn("RC=0", _run(1, stage=stage))

    def test_noncommissioned_tiny_explicit_runtime_keeps_prior_semantics(self):
        self.assertIn("RC=0", _run(1, stage="launch", active=False))

    def test_original_owner_preserves_lease_on_post_launch_effect_unknown(self):
        source = REMOTE.read_text()
        self.assertIn("PRESERVE_LEASE=1", source)
        self.assertIn("EFFECT_UNKNOWN timeout max_secs=$MAX_SECS", source)
        self.assertIn('log "COMMISSION_TIME_EXHAUSTED stage=launch observation_reserve=5"', source)


if __name__ == "__main__":
    unittest.main()
