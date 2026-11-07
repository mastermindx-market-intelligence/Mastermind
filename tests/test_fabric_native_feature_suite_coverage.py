"""Fail-closed CI discovery for opt-in native Fabric feature test suites.

Canonical CI discovers tests/**/test_*.py, not ops/native_fabric/.../tests.
Before the feature PRs merge these checks preserve the incumbent; once any
feature marker arrives they require its complete implementation and run its
real native unittest suite. No credential, provider, lease or remote host call.
"""
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
GROK_OVERLAY = ROOT / "ops/native_fabric/grok47/overlay/remote_sub.sh"
NATIVE_TESTS = NATIVE / "tests"


def _suite(name: str, *, minimum_cases: int) -> None:
    suite = NATIVE_TESTS / (name + ".py")
    assert suite.is_file(), f"native feature suite missing: {suite.relative_to(ROOT)}"
    run = subprocess.run(
        [sys.executable, "-m", "unittest", "-q", name],
        cwd=NATIVE_TESTS,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert run.returncode == 0, (
        f"native feature suite failed ({name}): "
        + (run.stdout + run.stderr)[-3000:]
    )
    # unittest can exit 0 for a module that imports but discovers zero tests.
    # Require the existing 9-case / 6-case minimum without preventing additions.
    count = re.search(r"Ran (\d+) tests?", run.stdout + run.stderr)
    assert count and int(count.group(1)) >= minimum_cases, (
        f"native feature suite discovered too few cases: {name}; "
        + (run.stdout + run.stderr)[-1000:]
    )


def test_minimax_first_worker_suite_runs_whenever_qualified_lane_is_present() -> None:
    task = (NATIVE / "candidate/fabric_task.py").read_text(encoding="utf-8")
    # The two feature hunks must land together; one hunk alone is a hard failure.
    # The central GLM-Codex route extends, rather than replaces, MiniMax qualification.
    allows = any(
        clause in task
        for clause in (
            'if pool not in ("grok", "minimax")',
            'if pool not in ("grok", "minimax", "glm")',
        )
    )
    forwards = (
        "qualification_host, pool=pool, task_class=task_class" in task
    )
    assert allows == forwards, (
        "MiniMax held-host qualification has a partial request-route integration"
    )
    if allows:
        _suite("test_minimax_first_worker_qualification", minimum_cases=9)


def test_terminal_poll_margin_suite_runs_for_both_distinct_launchers() -> None:
    candidate = (NATIVE / "candidate/remote_sub.sh").read_text(encoding="utf-8")
    grok = GROK_OVERLAY.read_text(encoding="utf-8")
    old_margin = 'if [ "$MAX_SECS" -gt $((2 * POLL_SECS)) ]; then'
    observed_margin = (
        'actual_observation_poll="$POLL_SECS"' in candidate
        and '[ "$actual_observation_poll" -le 30 ] || actual_observation_poll=30' in candidate
        and 'if [ "$MAX_SECS" -gt $((2 * actual_observation_poll)) ]; then' in candidate
    )
    # Different launchers intentionally keep different *observation*
    # policies, but BOTH must retain the finite two-observation cleanup
    # margin. The newer adaptive controller uses its ACTUAL <=30s cadence;
    # the Grok overlay still uses its old configured interval unchanged.
    assert (old_margin in grok), "Grok launcher lost its finite cleanup margin"
    assert (old_margin in candidate or observed_margin), (
        "native controller lost its finite cleanup margin"
    )
    _suite("test_terminal_poll_margin", minimum_cases=6)
