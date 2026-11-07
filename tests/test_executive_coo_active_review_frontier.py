"""Busy READ frontier and the real Supervisor pre-claim capacity boundary."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import Runtime, OrchestrationDispatchOutcome, StateConflict
from control_plane.executive_supervisor import ExecutiveSupervisor, NoEligibleWorkerCapacity, SupervisorError
from test_executive_coo_ready_frontier import _register_codex_peer
from test_executive_coo_review_drain import _create_review
from test_executive_os_phase1fc import (
    _register_placement_union, _v2_intent, _v3_execution_binding, _complete_ohf_role,
)


def _busy(tmp_path, *, reviewer=True, independent_ready=False):
    runtime = Runtime.at(tmp_path)
    _register_placement_union(runtime)
    if reviewer:
        _register_codex_peer(runtime, "worker-c")
    binding = _v3_execution_binding()
    metadata = {k: binding[k] for k in (
        "routing_policy_version", "execution_profile_id", "execution_profile_digest",
        "capability_policy_version", "capability_policy_digest",
    )}
    runtime.workers.register_worker(
        "reader-b", provider="claude-compatible-subscription", account_label="reader-b@company",
        worker_type="mock", capabilities=["read", "research"], quota_classes={
            "claude-hf1q-step": {"provider": "claude-compatible-subscription", "model": binding["model"],
                "effort": binding["effort"], "cost_class": "small", "capabilities": ["read", "research"],
                "metadata": metadata},
        },
    )
    root = runtime.jobs.get_job(submit_intent(
        runtime, _v2_intent(intent_id="CEO-ACTIVE-REVIEW-001", business_impact="routine"),
        execution_binding=binding,
    )["job_id"])
    planner = runtime.jobs.create_cycle_planner(root.job_id, command_id=f"coo-cycle:{root.job_id}:create-planner:0")
    planned = runtime.attempts.dispatch_cycle_job(
        planner.job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-a", quota_class="codex-hf1q-step",
    )
    plan = {"schema_version": "mastermind.execution_plan/v3", "root_job_id": root.job_id,
        "plan_attempt_id": planned.attempt.attempt_id, "steps": [{
            "ordinal": i, "step_id": f"step-{i}", "objective": "Independent bounded READ" if i != 3 else "Consume approved target",
            "business_impact": "routine", "review_required": i == 0, "requested_authorities": ["READ"],
            "allowed_write_paths": [], "validation_ids": [], "attempt_limit": 1, "cost_class": "small",
            "placement": {"provider_realm": "claude-compatible-subscription" if i == 2 else "codex",
                          "quota_class": "claude-hf1q-step" if i == 2 else "codex-hf1q-step"},
            "prerequisite_step_ids": (["step-3"] if i == 4 else []) if independent_ready else (["step-0"] if i == 3 else []),
        } for i in range(5 if independent_ready else 4)]}
    _complete_ohf_role(runtime, planned, plan, identity_seed=8601)
    admitted = runtime.jobs.admit_cycle_plan(root.job_id, command_id=f"coo-cycle:{root.job_id}:admit-plan:{planned.attempt.attempt_id}")
    jobs = {j.plan_step_id: j for j in admitted}
    target = runtime.attempts.dispatch_cycle_job(
        jobs["step-0"].job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{jobs['step-0'].job_id}:attempt:1",
        worker_id="worker-a", quota_class="codex-hf1q-step",
    )
    _complete_ohf_role(runtime, target, {"schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id, "plan_attempt_id": planned.attempt.attempt_id, "plan_digest": canonical_digest(plan),
        "plan_step_id": "step-0", "repair_round": 0, "artifacts": [], "evidence_digests": []}, identity_seed=8602)
    if independent_ready:
        prerequisite = runtime.attempts.dispatch_cycle_job(
            jobs["step-3"].job_id,
            command_id=f"coo-cycle:{root.job_id}:dispatch:{jobs['step-3'].job_id}:attempt:1",
            worker_id="worker-a", quota_class="codex-hf1q-step",
        )
        _complete_ohf_role(runtime, prerequisite, {"schema_version": "mastermind.work_result/v1",
            "root_job_id": root.job_id, "plan_attempt_id": planned.attempt.attempt_id,
            "plan_digest": canonical_digest(plan), "plan_step_id": "step-3", "repair_round": 0,
            "artifacts": [], "evidence_digests": []}, identity_seed=8603)
    active = runtime.attempts.dispatch_cycle_job(
        jobs["step-1"].job_id, command_id=f"coo-cycle:{root.job_id}:dispatch:{jobs['step-1'].job_id}:attempt:1",
        worker_id="worker-a", quota_class="codex-hf1q-step",
    )
    return runtime, root, jobs, active


def _claim(runtime, root, active, job_id, command):
    if job_id == active.job_id:
        return active
    review = runtime.jobs.get_job(job_id).orchestration_role == "review"
    outcome = runtime.attempts.dispatch_cycle_job(job_id, command_id=command,
        worker_id="worker-c" if review else "reader-b",
        quota_class="codex-hf1q-step" if review else "claude-hf1q-step")
    assert isinstance(outcome, OrchestrationDispatchOutcome)
    return outcome


def test_busy_read_creates_then_dispatches_review_before_fresh_work(tmp_path):
    runtime, root, jobs, active = _busy(tmp_path)
    calls = []
    def dispatch(j, c):
        calls.append(j)
        return _claim(runtime, root, active, j, c)
    cycle = CooCycle(runtime, dispatcher=dispatch)
    created = cycle.run_once(root.job_id)
    assert created.action == "REVIEW_CREATED"
    assert calls == []
    review = runtime.jobs.get_job(created.selected_job_id)
    assert review.reviews_job_id == jobs["step-0"].job_id
    outcome = cycle.run_once(root.job_id)
    assert outcome.selected_job_id == review.job_id
    assert calls == [review.job_id]
    assert runtime.jobs.get_job(review.job_id).assigned_worker_id != runtime.jobs.get_job(jobs["step-0"].job_id).assigned_worker_id
    assert runtime.jobs.get_job(jobs["step-2"].job_id).attempt_count == 0
    assert runtime.jobs.get_job(jobs["step-1"].job_id).current_attempt_id == active.attempt.attempt_id
    assert len(runtime.jobs.list_jobs()) == 6 <= 17


def test_real_supervisor_no_capacity_preserves_disjoint_busy_read_progress(tmp_path):
    runtime, root, jobs, active = _busy(tmp_path, reviewer=False)
    review = _create_review(runtime, root, jobs["step-0"])
    # Only the real claim-None path executes; no launch/provider is reachable.
    supervisor = object.__new__(ExecutiveSupervisor)
    supervisor.runtime, supervisor.instance_id, supervisor._exact_target_provider = runtime, "fixture-supervisor", None
    calls = []
    def dispatch(j, c):
        calls.append(j)
        if j == review.job_id:
            return asyncio.run(supervisor.start_cycle_job(j, command_id=c))
        return _claim(runtime, root, active, j, c)
    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert outcome.selected_job_id == jobs["step-2"].job_id
    assert calls == [review.job_id, jobs["step-2"].job_id]
    assert runtime.attempts.list_attempts(review.job_id) == []
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id) is None
    assert runtime.jobs.get_job(jobs["step-1"].job_id).current_attempt_id == active.attempt.attempt_id


def test_unavailable_review_and_fresh_work_reconcile_original_active_once(tmp_path):
    runtime, root, jobs, active = _busy(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    calls = []
    def dispatch(j, c):
        calls.append((j, c))
        return active if j == active.job_id else None
    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert outcome.selected_job_id == active.job_id
    assert [j for j, _ in calls] == [review.job_id, jobs["step-2"].job_id, active.job_id]
    assert calls[-1][1] == f"coo-cycle:{root.job_id}:dispatch:{active.job_id}:attempt:1"
    assert runtime.jobs.get_job(active.job_id).attempt_count == 1


@pytest.mark.parametrize("signal", ["none", "raise", "typed-after-claim"])
def test_busy_review_unknown_settles_same_command_before_another_claim(tmp_path, signal):
    runtime, root, jobs, active = _busy(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    claimed = []
    def lost(j, c):
        assert j == review.job_id
        claimed.append(_claim(runtime, root, active, j, c))
        if signal == "raise":
            raise SupervisorError("synthetic lost reply")
        if signal == "typed-after-claim":
            raise NoEligibleWorkerCapacity(j)
        return None
    with pytest.raises((StateConflict, SupervisorError)):
        CooCycle(runtime, dispatcher=lost).run_once(root.job_id)
    pending = runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id)
    assert pending["selected_job_id"] == review.job_id
    calls = []
    def reconcile(j, c):
        calls.append((j, c))
        return claimed[0]
    CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)
    assert calls == [(review.job_id, pending["dispatch_command_id"])]
    assert runtime.jobs.get_job(jobs["step-2"].job_id).attempt_count == 0


@pytest.mark.parametrize("error", [SupervisorError("no eligible worker capacity for unrelated"), NoEligibleWorkerCapacity("JOB-OTHER")])
def test_only_exact_owner_capacity_signal_is_treated_as_unavailable(tmp_path, error):
    runtime, root, jobs, active = _busy(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    calls = []
    def fail(j, c):
        calls.append(j)
        raise error
    with pytest.raises(SupervisorError):
        CooCycle(runtime, dispatcher=fail).run_once(root.job_id)
    assert calls == [review.job_id]
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id) is None
    assert runtime.jobs.get_job(jobs["step-2"].job_id).attempt_count == 0


@pytest.mark.parametrize("drift", [
    {"requested_authorities": ["READ", "WRITE"]}, {"allowed_write_paths": ["control_plane/example.py"]},
    {"validation_commands": [["pytest"]]}, {"plan_digest": "f" * 64},
    {"root_job_id": "JOB-FOREIGN"}, {"parent_job_id": "JOB-FOREIGN"},
    {"orchestration_role": "repair"},
])
def test_active_review_frontier_denies_write_coupling_and_foreign_identity(tmp_path, drift):
    runtime, root, jobs, active = _busy(tmp_path)
    target = runtime.jobs.get_job(jobs["step-0"].job_id)
    incumbent = dataclasses.replace(runtime.jobs.get_job(active.job_id), **drift)
    current = {j.plan_step_id: {"current_job_id": j.job_id, "review_required": j.plan_step_id == "step-0"} for j in jobs.values()}
    assert not CooCycle(runtime)._read_review_frontier_open(root.job_id, [incumbent], [jobs["step-2"]], {target.job_id: target}, current, {"schema_version": "mastermind.execution_plan/v3"})


@pytest.mark.parametrize("stale", ["revision", "lease", "quota", "v2"])
def test_active_review_frontier_requires_current_live_bound_custody(tmp_path, stale):
    runtime, root, jobs, active = _busy(tmp_path)
    target = runtime.jobs.get_job(jobs["step-0"].job_id)
    incumbent = runtime.jobs.get_job(active.job_id)
    current = {j.plan_step_id: {"current_job_id": j.job_id, "review_required": j.plan_step_id == "step-0"} for j in jobs.values()}
    if stale == "revision":
        current["step-1"]["current_job_id"] = "JOB-OTHER"
    if stale in {"lease", "quota"}:
        with runtime.store.transaction() as c:
            if stale == "lease":
                c.execute("UPDATE attempts SET lease_expires_at_ms=0 WHERE attempt_id=?", (active.attempt.attempt_id,))
            else:
                c.execute("UPDATE worker_quota_classes SET fence_counter=fence_counter+1 WHERE worker_id='worker-a'")
    schema = "mastermind.execution_plan/v2" if stale == "v2" else "mastermind.execution_plan/v3"
    assert not CooCycle(runtime)._read_review_frontier_open(root.job_id, [incumbent], [jobs["step-2"]], {target.job_id: target}, current, {"schema_version": schema})


@pytest.mark.parametrize("which,drift", [
    ("target", {"requested_authorities": ["READ", "WRITE"]}),
    ("target", {"root_job_id": "JOB-FOREIGN"}),
    ("target", {"plan_digest": "f" * 64}),
    ("target", {"orchestration_role": "aggregation"}),
    ("work", {"allowed_write_paths": ["control_plane/example.py"]}),
    ("work", {"orchestration_role": "repair"}),
    ("review", {"requested_authorities": ["READ", "RUN_TESTS"]}),
    ("review", {"reviews_job_id": "JOB-OLD"}),
])
def test_review_target_and_queued_frontier_require_closed_read_scope(tmp_path, which, drift):
    runtime, root, jobs, active = _busy(tmp_path)
    target = runtime.jobs.get_job(jobs["step-0"].job_id)
    review = _create_review(runtime, root, target)
    work = jobs["step-2"]
    if which == "target":
        target = dataclasses.replace(target, **drift)
    elif which == "work":
        work = dataclasses.replace(work, **drift)
    else:
        review = dataclasses.replace(review, **drift)
    current = {j.plan_step_id: {"current_job_id": j.job_id, "review_required": j.plan_step_id == "step-0"} for j in jobs.values()}
    assert not CooCycle(runtime)._read_review_frontier_open(
        root.job_id, [runtime.jobs.get_job(active.job_id)], [review, work],
        {target.job_id: target}, current, {"schema_version": "mastermind.execution_plan/v3"},
    )


def test_capacity_pressure_reconciles_before_independent_dependency_materialization(tmp_path):
    runtime, root, jobs, active = _busy(tmp_path, reviewer=False, independent_ready=True)
    review = _create_review(runtime, root, jobs["step-0"])
    supervisor = object.__new__(ExecutiveSupervisor)
    supervisor.runtime, supervisor.instance_id, supervisor._exact_target_provider = runtime, "fixture-supervisor", None
    manifest = runtime.jobs.project_cycle_work_dependency_manifest(root.job_id, "step-4")
    assert manifest["plan_step_id"] == "step-4"
    before_jobs = runtime.jobs.list_jobs()
    before_events = runtime.events.list_events()
    calls = []
    def dispatch(j, c):
        calls.append((j, c))
        if j == review.job_id:
            return asyncio.run(supervisor.start_cycle_job(j, command_id=c))
        if j == active.job_id:
            return active
        assert j == jobs["step-2"].job_id
        return None
    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert outcome.action == "DISPATCHED"
    assert outcome.selected_job_id == active.job_id
    assert [j for j, _ in calls] == [review.job_id, jobs["step-2"].job_id, active.job_id]
    assert calls[-1][1] == f"coo-cycle:{root.job_id}:dispatch:{active.job_id}:attempt:1"
    assert runtime.jobs.list_jobs() == before_jobs
    assert runtime.events.list_events() == before_events
    assert not any(j.plan_step_id == "step-4" for j in runtime.jobs.list_jobs())
