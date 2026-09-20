"""Bounded ready-frontier behavior for the existing Executive COO cycle."""
from __future__ import annotations

import dataclasses
import json

from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_orchestration_result import canonical_digest as result_digest
from control_plane.executive_runtime import OrchestrationDispatchOutcome, Runtime
from test_executive_os_phase1fc import (
    _admit_v2_plan,
    _complete_ohf_role,
    _register_placement_union,
    _v2_intent,
)

_CODEX = {"provider_realm": "codex", "quota_class": "codex-hf1q-step"}
_CLAUDE = {
    "provider_realm": "claude-compatible-subscription",
    "quota_class": "claude-hf1q-step",
}


def _admitted_pair(runtime: Runtime):
    _register_placement_union(runtime)
    runtime, root, _plan, admitted = _admit_v2_plan(
        runtime,
        placements=[_CODEX, _CLAUDE],
    )
    by_step = {job.plan_step_id: job for job in admitted}
    return root, by_step["step-0"], by_step["step-1"]


def _admitted_three_with_required_review(runtime: Runtime):
    _register_placement_union(runtime)
    _register_codex_peer(runtime, "worker-c")
    receipt = submit_intent(
        runtime,
        _v2_intent(
            intent_id="CEO-READY-FRONTIER-BARRIER-001",
            business_impact="routine",
        ),
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET constraints_json=? WHERE job_id=?",
            (
                json.dumps(
                    {
                        **root.constraints,
                        "provider": "codex",
                        "eligible_quota_classes": ["codex-hf1q-step"],
                        "work_placement_union": [_CODEX, _CLAUDE],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                root.job_id,
            ),
        )
    root = runtime.jobs.get_job(root.job_id)
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    planner_dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a",
    )
    assert isinstance(planner_dispatch, OrchestrationDispatchOutcome)
    plan_body = {
        "schema_version": "mastermind.execution_plan/v2",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner_dispatch.attempt.attempt_id,
        "steps": [
            {
                "ordinal": 0,
                "step_id": "step-0",
                "objective": "Keep one exact read-only work item live.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
                "placement": _CODEX,
            },
            {
                "ordinal": 1,
                "step_id": "step-1",
                "objective": "Complete one item that requires independent review.",
                "business_impact": "routine",
                "review_required": True,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
                "placement": _CLAUDE,
            },
            {
                "ordinal": 2,
                "step_id": "step-2",
                "objective": "Remain queued behind the coupled review barrier.",
                "business_impact": "routine",
                "review_required": False,
                "requested_authorities": ["READ"],
                "allowed_write_paths": [],
                "validation_ids": [],
                "attempt_limit": 1,
                "cost_class": "small",
                "placement": _CODEX,
            },
        ],
    }
    _complete_ohf_role(runtime, planner_dispatch, plan_body, identity_seed=7401)
    admitted = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:"
            f"{planner_dispatch.attempt.attempt_id}"
        ),
    )
    return root, planner_dispatch, plan_body, admitted


def _start_first(runtime: Runtime, root_id: str, job_id: str):
    outcome = runtime.attempts.dispatch_cycle_job(
        job_id,
        command_id=f"coo-cycle:{root_id}:dispatch:{job_id}:attempt:1",
        worker_id="worker-a",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(outcome, OrchestrationDispatchOutcome)
    return outcome


def test_live_read_only_work_does_not_starve_ready_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    first_dispatch = _start_first(runtime, root.job_id, first.job_id)
    calls: list[str] = []

    def dispatch(job_id: str, command_id: str):
        calls.append(job_id)
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        worker = "worker-a" if job.plan_step_id == "step-0" else "worker-b"
        quota = "codex-hf1q-step" if worker == "worker-a" else "claude-hf1q-step"
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker,
            quota_class=quota,
        )
        assert outcome is not None
        return outcome

    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)

    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == second.job_id
    assert calls == [second.job_id]
    assert runtime.jobs.get_job(first.job_id).current_attempt_id == (
        first_dispatch.attempt.attempt_id
    )
    assert runtime.jobs.get_job(first.job_id).attempt_count == 1
    assert runtime.jobs.get_job(second.job_id).attempt_count == 1


def test_queued_review_closes_ready_frontier_until_coupled_work_resolves(
    tmp_path,
):
    runtime = Runtime.at(tmp_path)
    root, planner, plan_body, admitted = _admitted_three_with_required_review(
        runtime
    )
    by_step = {job.plan_step_id: job for job in admitted}
    active_dispatch = _start_first(
        runtime, root.job_id, by_step["step-0"].job_id
    )
    reviewed_dispatch = runtime.attempts.dispatch_cycle_job(
        by_step["step-1"].job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:dispatch:"
            f"{by_step['step-1'].job_id}:attempt:1"
        ),
        worker_id="worker-b",
        quota_class="claude-hf1q-step",
    )
    assert isinstance(reviewed_dispatch, OrchestrationDispatchOutcome)
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": planner.attempt.attempt_id,
        "plan_digest": result_digest(plan_body),
        "plan_step_id": "step-1",
        "repair_round": 0,
        "artifacts": [],
        "evidence_digests": [],
    }
    _complete_ohf_role(runtime, reviewed_dispatch, work_body, identity_seed=7402)
    review = runtime.jobs.create_cycle_review(
        root.job_id,
        by_step["step-1"].job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:create-review:"
            f"{by_step['step-1'].job_id}:1"
        ),
    )
    assert review.attempt_count == 0

    calls: list[str] = []

    def reconcile(job_id: str, _command_id: str):
        calls.append(job_id)
        assert job_id == by_step["step-0"].job_id
        return active_dispatch

    outcome = CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)

    assert outcome.selected_job_id == by_step["step-0"].job_id
    assert calls == [by_step["step-0"].job_id]
    assert runtime.jobs.get_job(by_step["step-2"].job_id).attempt_count == 0
    assert runtime.jobs.get_job(review.job_id).attempt_count == 0


def test_expired_active_attempt_keeps_reconciliation_priority(tmp_path):
    now_ms = [1_800_000_000_000]
    runtime = Runtime.at(
        tmp_path,
        clock=lambda: now_ms[0],
        lease_seconds=30,
    )
    root, first, second = _admitted_pair(runtime)
    first_dispatch = _start_first(runtime, root.job_id, first.job_id)
    now_ms[0] += 31_000
    calls: list[str] = []

    def reconcile(job_id: str, command_id: str):
        calls.append(job_id)
        return first_dispatch

    outcome = CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)

    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == first.job_id
    assert calls == [first.job_id]
    assert runtime.jobs.get_job(second.job_id).attempt_count == 0


def _register_codex_peer(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}@company",
        worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={
            "codex-hf1q-step": {
                "provider": "codex",
                "capabilities": ["read", "research"],
                "cost_class": "small",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "metadata": {
                    "routing_policy_version": "fph0-routing",
                    "execution_profile_id": "fph0-execution",
                    "execution_profile_digest": "b" * 64,
                    "capability_policy_version": "fph0-capability",
                    "capability_policy_digest": "c" * 64,
                },
            }
        },
    )


def test_two_live_read_only_children_do_not_starve_third_ready_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    _register_codex_peer(runtime, "worker-c")
    runtime, root, _plan, admitted = _admit_v2_plan(
        runtime,
        placements=[_CODEX, _CLAUDE, _CODEX],
    )
    by_step = {job.plan_step_id: job for job in admitted}
    first = by_step["step-0"]
    _start_first(runtime, root.job_id, first.job_id)

    workers = {
        "step-0": ("worker-a", "codex-hf1q-step"),
        "step-1": ("worker-b", "claude-hf1q-step"),
        "step-2": ("worker-c", "codex-hf1q-step"),
    }
    calls: list[str] = []

    def dispatch(job_id: str, command_id: str):
        job = runtime.jobs.get_job(job_id)
        assert job is not None
        calls.append(str(job.plan_step_id))
        worker, quota = workers[str(job.plan_step_id)]
        outcome = runtime.attempts.dispatch_cycle_job(
            job_id,
            command_id=command_id,
            worker_id=worker,
            quota_class=quota,
        )
        assert outcome is not None
        return outcome

    cycle = CooCycle(runtime, dispatcher=dispatch)
    second = cycle.run_once(root.job_id)
    third = cycle.run_once(root.job_id)
    reconcile = cycle.run_once(root.job_id)

    assert second.selected_job_id == by_step["step-1"].job_id
    assert third.selected_job_id == by_step["step-2"].job_id
    assert reconcile.selected_job_id == by_step["step-0"].job_id
    assert calls == ["step-1", "step-2", "step-0"]
    assert all(runtime.jobs.get_job(job.job_id).attempt_count == 1 for job in admitted)


def test_ready_frontier_refuses_write_capable_sibling(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    write_candidate = dataclasses.replace(
        candidate,
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/example.py"],
    )
    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)

    assert cycle._is_read_only_frontier_work(candidate)
    assert not cycle._is_read_only_frontier_work(write_candidate)
    assert not cycle._ready_frontier_candidate(write_candidate, [active])


def test_ready_frontier_refuses_if_any_active_child_is_write_capable(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    write_active = dataclasses.replace(
        active,
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["control_plane/example.py"],
    )
    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)

    assert not cycle._ready_frontier_candidate(candidate, [write_active])


def test_ready_frontier_refuses_cross_plan_identity(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    mismatched = dataclasses.replace(active, plan_digest="0" * 64)
    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)

    assert not cycle._ready_frontier_candidate(candidate, [mismatched])


def test_ready_frontier_refuses_if_active_quota_no_longer_holds_attempt(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    started = _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET status='AVAILABLE', held_attempt_id=NULL "
            "WHERE worker_id=? AND quota_class=?",
            (started.attempt.worker_id, started.attempt.quota_class),
        )

    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)
    assert not cycle._active_attempt_is_current_and_live(active)
    assert not cycle._ready_frontier_candidate(candidate, [active])


def test_ready_frontier_refuses_non_read_authority_without_write_paths(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    authority_only = dataclasses.replace(
        candidate,
        requested_authorities=["READ", "WRITE_BRANCH"],
    )
    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)

    assert authority_only.allowed_write_paths == []
    assert not cycle._is_read_only_frontier_work(authority_only)
    assert not cycle._ready_frontier_candidate(authority_only, [active])


def test_ready_frontier_refuses_write_paths_even_with_read_only_authority(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    path_only = dataclasses.replace(
        candidate,
        allowed_write_paths=["control_plane/example.py"],
    )
    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)

    assert path_only.requested_authorities == ["READ"]
    assert not cycle._is_read_only_frontier_work(path_only)
    assert not cycle._ready_frontier_candidate(path_only, [active])


def test_ready_frontier_open_requires_current_lineage(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, first, second = _admitted_pair(runtime)
    _start_first(runtime, root.job_id, first.job_id)
    active = runtime.jobs.get_job(first.job_id)
    candidate = runtime.jobs.get_job(second.job_id)
    assert active is not None and candidate is not None

    cycle = CooCycle(runtime, dispatcher=lambda _job, _command: None)
    current_by_step = {
        str(active.plan_step_id): {"current_job_id": active.job_id},
        str(candidate.plan_step_id): {"current_job_id": "JOB-NOT-CURRENT"},
    }

    assert not cycle._ready_frontier_open(
        [active], [candidate], current_by_step
    )
