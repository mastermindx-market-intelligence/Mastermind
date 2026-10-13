"""Current Runtime review demand drains before discretionary cycle work."""
from __future__ import annotations

import pytest

from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import Runtime, OrchestrationDispatchOutcome, StateConflict
from test_executive_coo_ready_frontier import (
    _admitted_v3_chain, _complete_v3_prerequisite,
)


def _pending_review(tmp_path):
    runtime = Runtime.at(tmp_path)
    root, planner, plan, jobs = _admitted_v3_chain(
        runtime, prerequisite_review_required=True,
    )
    # The shared placement fixture omits the V3 exact host binding on its
    # Claude peer. Qualify this synthetic peer rather than bypass that guard.
    runtime.workers.register_worker(
        "worker-qualified-b", provider="claude-compatible-subscription",
        account_label="worker-qualified-b@company", worker_type="mock",
        capabilities=["read", "research"], quota_classes={
            "claude-hf1q-step": {
                "provider": "claude-compatible-subscription", "cost_class": "small",
                "capabilities": ["read", "research"], "model": "gpt-5.6-sol", "effort": "xhigh",
                "metadata": {
                    "routing_policy_version": "fph0-routing", "execution_profile_id": "fph0-execution",
                    "execution_profile_digest": "b" * 64, "capability_policy_version": "fph0-capability",
                    "capability_policy_digest": "c" * 64,
                },
            },
        },
    )
    dispatch, seal = _complete_v3_prerequisite(
        runtime, root, planner, plan, jobs["step-0"],
    )
    return runtime, root, jobs, dispatch, seal


def _create_review(runtime, root, target):
    return runtime.jobs.create_cycle_review(
        root.job_id, target.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-review:{target.job_id}:1",
    )


def _dispatch(runtime, job_id, command):
    outcome = runtime.attempts.dispatch_cycle_job(
        job_id, command_id=command, worker_id=("worker-c" if runtime.jobs.get_job(job_id).orchestration_role == "review" else "worker-qualified-b"),
        quota_class=("codex-hf1q-step" if runtime.jobs.get_job(job_id).orchestration_role == "review" else "claude-hf1q-step"),
    )
    assert isinstance(outcome, OrchestrationDispatchOutcome)
    return outcome


def test_missing_required_review_created_before_queued_work(tmp_path):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    calls = []
    outcome = CooCycle(runtime, dispatcher=lambda j, c: calls.append(j)).run_once(root.job_id)
    assert outcome.action == "REVIEW_CREATED"
    review = runtime.jobs.get_job(outcome.selected_job_id)
    assert review.reviews_job_id == jobs["step-0"].job_id
    assert outcome.command_id == f"coo-cycle:{root.job_id}:create-review:{jobs['step-0'].job_id}:1"
    assert calls == []
    assert runtime.jobs.get_job(jobs["step-1"].job_id).attempt_count == 0


def test_queued_review_dispatched_before_discretionary_work(tmp_path):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    calls = []
    def dispatch(job_id, command):
        calls.append(job_id)
        return _dispatch(runtime, job_id, command)
    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert outcome.selected_job_id == review.job_id
    assert calls == [review.job_id]
    assert runtime.jobs.get_job(jobs["step-1"].job_id).attempt_count == 0


def test_preclaim_review_capacity_miss_allows_disjoint_read_once(tmp_path):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    calls = []
    def dispatch(job_id, command):
        calls.append(job_id)
        return None if job_id == review.job_id else _dispatch(runtime, job_id, command)
    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert outcome.selected_job_id == jobs["step-1"].job_id
    assert calls == [review.job_id, jobs["step-1"].job_id]
    assert runtime.jobs.get_job(review.job_id).attempt_count == 0
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id) is None
    assert runtime.jobs.validated_cycle_block(root.job_id) is None


def test_preclaim_misses_are_resumable_and_do_not_create_events(tmp_path):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    events = runtime.events.list_events()
    calls = []
    cycle = CooCycle(runtime, dispatcher=lambda j, c: calls.append(j))
    outcome = cycle.run_once(root.job_id)
    assert outcome.action == "NO_ACTION"
    assert calls == [review.job_id, jobs["step-1"].job_id]
    assert runtime.events.list_events() == events
    calls.clear()
    cycle.run_once(root.job_id)
    assert calls == [review.job_id, jobs["step-1"].job_id]


@pytest.mark.parametrize("raises", [False, True])
def test_claimed_review_uncertainty_settles_original_command_before_work(tmp_path, raises):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    claimed = []
    def lost(job_id, command):
        assert job_id == review.job_id
        claimed.append(_dispatch(runtime, job_id, command))
        if raises:
            raise RuntimeError("synthetic lost response")
        return None
    with pytest.raises((StateConflict, RuntimeError)):
        CooCycle(runtime, dispatcher=lost).run_once(root.job_id)
    pending = runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id)
    assert pending["selected_job_id"] == review.job_id
    assert runtime.jobs.get_job(jobs["step-1"].job_id).attempt_count == 0
    calls = []
    def reconcile(job_id, command):
        calls.append((job_id, command))
        return claimed[0]
    outcome = CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)
    assert calls == [(review.job_id, pending["dispatch_command_id"])]
    assert outcome.selected_job_id == review.job_id
    assert runtime.jobs.get_job(review.job_id).attempt_count == 1
    assert runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id) is None


def test_active_review_reconciles_before_further_work(tmp_path):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    active = _dispatch(runtime, review.job_id,
                       f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1")
    calls = []
    def reconcile(job_id, command):
        calls.append(job_id)
        return active
    outcome = CooCycle(runtime, dispatcher=reconcile).run_once(root.job_id)
    assert outcome.selected_job_id == review.job_id
    assert calls == [review.job_id]
    assert runtime.jobs.get_job(jobs["step-1"].job_id).attempt_count == 0
    assert len([j for j in runtime.jobs.list_jobs() if j.orchestration_role == "review"]) == 1


def _finish_review(runtime, root, review, target_dispatch, seal, verdict, *, same_worker=False):
    from test_executive_os_phase1fc import _complete_ohf_role, _review_body
    outcome = runtime.attempts.dispatch_cycle_job(
        review.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1",
        worker_id="worker-a" if same_worker else "worker-c",
        quota_class="codex-hf1q-step",
    )
    assert isinstance(outcome, OrchestrationDispatchOutcome)
    target = runtime.jobs.get_job(target_dispatch.attempt.job_id)
    body = _review_body(
        root_id=root.job_id, plan_attempt_id=target.plan_attempt_id,
        plan_digest=target.plan_digest, target_job_id=target.job_id,
        target_attempt_id=target_dispatch.attempt.attempt_id,
        target_result_digest=seal["role_result_digest"],
        repair_round=target.repair_round, verdict=verdict, plan_step_id=target.plan_step_id,
    )
    _complete_ohf_role(runtime, outcome, body, identity_seed=7803)


def test_independent_approval_releases_dependency_work(tmp_path):
    runtime, root, jobs, target, seal = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    _finish_review(runtime, root, review, target, seal, "approve")
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "WORK_CREATED"
    assert runtime.jobs.get_job(outcome.selected_job_id).plan_step_id == "step-2"


def test_same_worker_approval_does_not_clear_current_review_demand(tmp_path):
    runtime, root, jobs, target, seal = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    _finish_review(runtime, root, review, target, seal, "approve", same_worker=True)
    outcome = CooCycle(runtime).run_once(root.job_id)
    assert outcome.action == "REVIEW_CREATED"
    assert outcome.command_id.endswith(":2")
    assert runtime.jobs.get_job(outcome.selected_job_id).reviews_job_id == jobs["step-0"].job_id
    assert runtime.jobs.get_job(jobs["step-1"].job_id).attempt_count == 0


def test_reject_repair_dispatch_precedes_discretionary_work(tmp_path):
    runtime, root, jobs, target, seal = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    _finish_review(runtime, root, review, target, seal, "reject")
    created = CooCycle(runtime).run_once(root.job_id)
    assert created.action == "REPAIR_CREATED"
    calls = []
    def dispatch(job_id, command):
        calls.append(job_id)
        return runtime.attempts.dispatch_cycle_job(
            job_id, command_id=command, worker_id="worker-a", quota_class="codex-hf1q-step",
        )
    outcome = CooCycle(runtime, dispatcher=dispatch).run_once(root.job_id)
    assert outcome.selected_job_id == created.selected_job_id
    assert calls == [created.selected_job_id]
    assert runtime.jobs.get_job(jobs["step-1"].job_id).attempt_count == 0


def test_stale_completion_cannot_create_a_new_review_after_repair(tmp_path):
    runtime, root, jobs, target, seal = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    _finish_review(runtime, root, review, target, seal, "reject")
    repair = CooCycle(runtime).run_once(root.job_id)
    assert repair.action == "REPAIR_CREATED"
    calls = []
    outcome = CooCycle(runtime, dispatcher=lambda j, c: calls.append(j)).run_once(root.job_id)
    assert outcome.action == "NO_ACTION"
    assert calls == [repair.selected_job_id]
    assert len([j for j in runtime.jobs.list_jobs() if j.orchestration_role == "review"]) == 1


@pytest.mark.parametrize("drift", [
    {"requested_authorities": ["READ", "WRITE"]},
    {"allowed_write_paths": ["control_plane/example.py"]},
    {"validation_commands": ["pytest"]},
    {"plan_digest": "f" * 64},
    {"supersedes_job_id": "JOB-OLD"},
    {"plan_step_id": "step-0"},
])
def test_review_capacity_fallback_refuses_coupled_or_unqualified_revision(tmp_path, drift):
    import dataclasses
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    target = runtime.jobs.get_job(jobs["step-0"].job_id)
    candidate = dataclasses.replace(jobs["step-1"], **drift)
    current = {
        "step-0": {"current_job_id": target.job_id, "review_required": True},
        "step-1": {"current_job_id": candidate.job_id, "review_required": False},
    }
    calls = []
    outcome = CooCycle(runtime, dispatcher=lambda j, c: calls.append(j))._drain_current_reviews(
        root.job_id, [target, review, candidate], current, {"step-0": 0, "step-1": 1},
        {"schema_version": "mastermind.execution_plan/v3"}, "pinned-test-policy",
    )
    assert outcome.action == "NO_ACTION"
    assert calls == [review.job_id]
    assert outcome.receipt["unavailable_job_ids"] == [review.job_id]
    assert runtime.jobs.get_job(candidate.job_id).attempt_count == 0


def test_review_capacity_fallback_refuses_noncurrent_candidate(tmp_path):
    runtime, root, jobs, _, _ = _pending_review(tmp_path)
    review = _create_review(runtime, root, jobs["step-0"])
    target = runtime.jobs.get_job(jobs["step-0"].job_id)
    calls = []
    outcome = CooCycle(runtime, dispatcher=lambda j, c: calls.append(j))._drain_current_reviews(
        root.job_id, [target, review, jobs["step-1"]],
        {"step-0": {"current_job_id": target.job_id, "review_required": True},
         "step-1": {"current_job_id": "JOB-OTHER", "review_required": False}},
        {}, {"schema_version": "mastermind.execution_plan/v3"}, "pinned-test-policy",
    )
    assert outcome.action == "NO_ACTION"
    assert calls == [review.job_id]


def test_raced_snapshot_replays_existing_review_without_new_revision_mutation(tmp_path):
    runtime, root, jobs, dispatch, seal = _pending_review(tmp_path)
    old_target = runtime.jobs.get_job(jobs["step-0"].job_id)
    review = _create_review(runtime, root, old_target)
    _finish_review(runtime, root, review, dispatch, seal, "reject")
    assert CooCycle(runtime).run_once(root.job_id).action == "REPAIR_CREATED"
    # The exact old command may replay its receipt; it cannot create a review
    # of the superseded revision or mutate the newer canonical repair.
    events = runtime.events.list_events()
    outcome = CooCycle(runtime)._drain_current_reviews(
        root.job_id, [old_target],
        {"step-0": {"current_job_id": old_target.job_id, "review_required": True}},
        {}, {"schema_version": "mastermind.execution_plan/v3"}, "pinned-test-policy",
    )
    assert outcome.action == "REVIEW_CREATED"
    assert outcome.selected_job_id == review.job_id
    assert runtime.events.list_events() == events
    assert len([j for j in runtime.jobs.list_jobs() if j.orchestration_role == "review"]) == 1
