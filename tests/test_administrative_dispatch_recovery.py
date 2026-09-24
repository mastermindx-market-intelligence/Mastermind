"""Hermetic #917 acceptance cases; expected failures are unresolved runtime defects.

Run with --runxfail to expose pending recovery. V3 cases require V3 source.
Legacy READ/placement does not establish independent dependency readiness.
These exercise temporary SQLite state and fixture workers, never live providers.
"""
from unittest.mock import patch

import pytest
import control_plane.executive_orchestration_result as role_result
import test_executive_os_phase1fc as phase1fc

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import Runtime, StateConflict
from test_executive_os_phase1fc import _admit_v2_plan, _register_placement_union


_pending_recovery = pytest.mark.xfail(
    getattr(role_result, "PLAN_SCHEMA_V3", None) != "mastermind.execution_plan/v3",
    strict=True, raises=AssertionError,
    reason="#917: baseline recovery absent; V3 source must satisfy this requirement",
)


_requires_dependency_plan = pytest.mark.skipif(
    getattr(role_result, "PLAN_SCHEMA_V3", None) != "mastermind.execution_plan/v3",
    reason="V3 source absent: run on actual #870 carrier; this skip is not acceptance",
)


def _admitted_children(tmp_path, prerequisites=None):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    complete = phase1fc._complete_ohf_role

    def seal_declared_plan(runtime, dispatch, body, **kwargs):
        # Adapt only the existing fixture's plan input, never Runtime validation.
        assert body["schema_version"] == "mastermind.execution_plan/v2"
        if prerequisites is not None:
            body["schema_version"] = role_result.PLAN_SCHEMA_V3
            assert set(prerequisites) == {s["step_id"] for s in body["steps"]}
            for step in body["steps"]:
                step["prerequisite_step_ids"] = list(prerequisites[step["step_id"]])
        return complete(runtime, dispatch, body, **kwargs)

    with patch.object(phase1fc, "_complete_ohf_role", seal_declared_plan):
        _, root, plan, children = _admit_v2_plan(runtime, placements=[
            {"provider_realm": "codex", "quota_class": "codex-hf1q-step"},
            {"provider_realm": "claude-compatible-subscription", "quota_class": "claude-hf1q-step"},
        ])
    return runtime, root, plan, children


def _children(tmp_path, explicit_dependencies=False):
    prerequisites = {"step-0": [], "step-1": []} if explicit_dependencies else None
    runtime, root, plan, children = _admitted_children(tmp_path, prerequisites)
    if explicit_dependencies:
        assert plan["schema_version"] == role_result.PLAN_SCHEMA_V3
        assert all(step["prerequisite_step_ids"] == [] for step in plan["steps"])
    else:
        assert plan["schema_version"] == role_result.PLAN_SCHEMA_V2
        assert all("prerequisite_step_ids" not in step for step in plan["steps"])
    first, second = sorted(children, key=lambda job: job.plan_step_id)
    return runtime, root, first, second


@_requires_dependency_plan
def test_preclaim_unavailability_does_not_starve_explicit_v3_ready_sibling(tmp_path):
    runtime, root, first, second = _children(tmp_path, explicit_dependencies=True)
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


@pytest.mark.parametrize("explicit_dependencies", [
    pytest.param(False, id="legacy-v2"),
    pytest.param(True, marks=_requires_dependency_plan, id="explicit-v3"),
])
@pytest.mark.parametrize("response_mode", ["none", "raise"])
def test_ambiguous_claim_never_launches_sibling_or_duplicates_attempt(
    tmp_path, explicit_dependencies, response_mode,
):
    runtime, root, first, second = _children(tmp_path, explicit_dependencies)
    calls = []

    def lost_return(job_id, command_id):
        calls.append((job_id, command_id))
        runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-a",
        )
        if response_mode == "raise":
            raise RuntimeError("fixture lost dispatch response")
        return None

    error = RuntimeError if response_mode == "raise" else StateConflict
    message = "fixture lost dispatch response" if response_mode == "raise" else "ambiguous after durable Job transition"
    with pytest.raises(error, match=message):
        CooCycle(runtime, dispatcher=lost_return).run_once(root.job_id)
    assert len(runtime.attempts.list_attempts(first.job_id)) == 1
    assert runtime.attempts.list_attempts(second.job_id) == []
    assert runtime.jobs.validated_cycle_block(root.job_id) is None
    original_command = calls[0]

    def reconcile(job_id, command_id):
        calls.append((job_id, command_id))
        worker_id = "worker-a" if job_id == first.job_id else "worker-b"
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id=worker_id,
        )

    CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)
    assert runtime.attempts.list_attempts(second.job_id) == []
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


def test_legacy_read_only_placement_does_not_authorize_skipping_a_predecessor(tmp_path):
    runtime, root, first, second = _children(tmp_path)
    calls = []

    def unavailable(job_id, command_id):
        calls.append(job_id)
        if job_id == first.job_id:
            return None
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id="worker-b",
        )

    CooCycle(runtime, dispatcher=unavailable).run_once(root.job_id)
    assert runtime.attempts.list_attempts(second.job_id) == []
    assert calls == [first.job_id]
    assert runtime.attempts.list_attempts(first.job_id) == []


@_requires_dependency_plan
def test_v3_declared_dependency_is_not_bypassed_by_preclaim_unavailability(tmp_path):
    runtime, root, plan, children = _admitted_children(
        tmp_path, {"step-0": [], "step-1": ["step-0"]},
    )
    assert plan["steps"][1]["prerequisite_step_ids"] == ["step-0"]
    first = next(job for job in children if job.plan_step_id == "step-0")
    calls = []

    def unavailable(job_id, command_id):
        calls.append(job_id)
        return None

    CooCycle(runtime, dispatcher=unavailable).run_once(root.job_id)
    assert calls == [first.job_id]
    assert all(
        runtime.attempts.list_attempts(job.job_id) == []
        for job in runtime.jobs.list_jobs()
        if job.root_job_id == root.job_id and job.orchestration_role == "work"
    )


def test_legacy_live_predecessor_is_reconciled_before_sibling(tmp_path):
    runtime, root, first, second = _children(tmp_path)
    command = f"coo-cycle:{root.job_id}:dispatch:{first.job_id}:attempt:1"
    runtime.attempts.dispatch_cycle_job(
        first.job_id, command_id=command, worker_id="worker-a",
    )
    calls = []

    def dispatch(job_id, command_id):
        calls.append((job_id, command_id))
        worker = "worker-a" if job_id == first.job_id else "worker-b"
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command_id, worker_id=worker,
        )

    CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert runtime.attempts.list_attempts(second.job_id) == []
    assert calls == [(first.job_id, command)]
