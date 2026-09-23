"""Hermetic #917 acceptance cases; expected failures are unresolved runtime defects.

Run with --runxfail to expose the two pending #870 recovery requirements.
These exercise temporary SQLite state and fixture workers, never live providers.
"""
import pytest

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import Runtime, StateConflict
from test_executive_os_phase1fc import _admit_v2_plan, _register_placement_union


_pending_recovery = pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason="#917: persistent PRE_START block; incumbent #870 integration required",
)


def _children(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    _, root, _, children = _admit_v2_plan(runtime, placements=[
        {"provider_realm": "codex", "quota_class": "codex-hf1q-step"},
        {"provider_realm": "claude-compatible-subscription", "quota_class": "claude-hf1q-step"},
    ])
    first, second = sorted(children, key=lambda job: job.plan_step_id)
    return runtime, root, first, second


@_pending_recovery
def test_preclaim_unavailability_does_not_starve_ready_read_only_sibling(tmp_path):
    runtime, root, first, second = _children(tmp_path)
    calls = []

    def dispatch(job_id, command_id):
        calls.append(job_id)
        if job_id == first.job_id:
            return None
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-b",
        )

    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert runtime.attempts.list_attempts(first.job_id) == []
    assert len(runtime.attempts.list_attempts(second.job_id)) == 1
    assert calls == [first.job_id, second.job_id]
    assert outcome.selected_job_id == second.job_id
    assert runtime.jobs.validated_cycle_block(root.job_id) is None


@_pending_recovery
def test_capacity_restoration_can_resume_same_unstarted_operation(tmp_path):
    runtime, root, first, _second = _children(tmp_path)
    CooCycle(runtime, dispatcher=lambda *_: None).run_once(root.job_id)
    assert runtime.attempts.list_attempts(first.job_id) == []
    calls = []

    def restored(job_id, command_id):
        calls.append(job_id)
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a",
        )

    outcome = CooCycle(runtime, dispatcher=restored).run_once(root.job_id)
    assert outcome.action == "DISPATCHED"
    assert calls == [first.job_id]
    assert len(runtime.attempts.list_attempts(first.job_id)) == 1
    assert runtime.jobs.validated_cycle_block(root.job_id) is None


def test_none_after_claim_never_launches_sibling_or_duplicates_attempt(tmp_path):
    runtime, root, first, second = _children(tmp_path)
    calls = []

    def lost_return(job_id, command_id):
        calls.append((job_id, command_id))
        runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a",
        )
        return None

    with pytest.raises(StateConflict, match="ambiguous after durable Job transition"):
        CooCycle(runtime, dispatcher=lost_return).run_once(root.job_id)
    assert len(runtime.attempts.list_attempts(first.job_id)) == 1
    assert runtime.attempts.list_attempts(second.job_id) == []
    assert runtime.jobs.validated_cycle_block(root.job_id) is None
    original_command = calls[0]

    def reconcile(job_id, command_id):
        calls.append((job_id, command_id))
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a",
        )

    CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)
    assert calls == [original_command, original_command]
    assert len(runtime.attempts.list_attempts(first.job_id)) == 1
    assert runtime.attempts.list_attempts(second.job_id) == []


def test_invalid_root_still_stops_dispatch_without_touching_unrelated_work(tmp_path):
    runtime = Runtime.at(tmp_path)
    invalid = runtime.jobs.create_job("not an admitted COO root")
    sentinel = runtime.jobs.create_job("unrelated protected work")
    calls = []

    def unexpected_dispatch(*args):
        calls.append(args)
        raise AssertionError("invalid root reached dispatch")

    outcome = CooCycle(runtime, dispatcher=unexpected_dispatch).run_once(invalid.job_id)
    assert outcome.action == "BLOCKED"
    assert outcome.receipt["reason"] == "invalid_root"
    assert calls == []
    assert runtime.jobs.get_job(sentinel.job_id) == sentinel
    assert runtime.attempts.list_attempts() == []
