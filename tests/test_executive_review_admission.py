"""Fresh reviewer selection without changing retained dispatch or result authority."""
from __future__ import annotations

import pytest

import control_plane.executive_runtime as runtime_module
from tests.test_executive_os_phase1fc import _cycle_through_completed_work


def _pending_review(tmp_path):
    runtime, cycle, _dispatches, root, _planner, work, _seal = _cycle_through_completed_work(
        tmp_path, intent_id="CEO-REVIEW-ADMISSION", review_workers=[],
    )
    created = cycle.run_once(root.job_id)
    assert created.action == "REVIEW_CREATED"
    review = runtime.jobs.get_job(created.selected_job_id)
    command = f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1"
    return runtime, review, work.attempt, command


def _register_shared_account(runtime, account):
    runtime.workers.register_worker(
        "worker-aa", provider="codex", account_label=account, worker_type="mock",
        capabilities=["read", "research"],
        quota_classes={"default": {
            "provider": "codex", "cost_class": "small", "capabilities": ["read", "research"],
        }},
    )


def _quota_state(runtime):
    with runtime.store.read() as connection:
        return [tuple(row) for row in connection.execute(
            "SELECT worker_id,quota_class,status,held_attempt_id FROM worker_quota_classes ORDER BY worker_id,quota_class"
        )]


def test_automatic_review_excludes_worker_and_sealed_account(tmp_path):
    runtime, review, work_attempt, command = _pending_review(tmp_path)
    _register_shared_account(runtime, "worker-a@company")
    # A different worker ID with the same sealed account is also excluded.
    outcome = runtime.attempts.dispatch_cycle_job(review.job_id, command_id=command)
    assert outcome.attempt.worker_id == "worker-b"
    assert runtime.jobs.get_job(review.job_id).attempt_count == 1
    assert outcome.attempt.worker_id != work_attempt.worker_id


@pytest.mark.parametrize("explicit", [False, True])
def test_no_independent_capacity_consumes_no_attempt_or_quota(tmp_path, explicit):
    runtime, review, _work, command = _pending_review(tmp_path)
    if not explicit:
        _register_shared_account(runtime, "worker-a@company")
        runtime.workers.set_worker_status("worker-b", "RATE_LIMITED")
    before = _quota_state(runtime)
    outcome = runtime.attempts.dispatch_cycle_job(
        review.job_id, command_id=command,
        **({"worker_id": "worker-a", "quota_class": "default"} if explicit else {}),
    )
    assert outcome is None
    assert _quota_state(runtime) == before
    retained = runtime.jobs.get_job(review.job_id)
    assert retained.attempt_count == 0 and retained.current_attempt_id is None
    if explicit:
        # The explicit refusal did not create a command or silently choose b.
        automatic = runtime.attempts.dispatch_cycle_job(review.job_id, command_id=command)
        assert automatic.attempt.worker_id == "worker-b"


def test_existing_review_command_replays_before_fresh_candidate_selection(tmp_path, monkeypatch):
    runtime, review, _work, command = _pending_review(tmp_path)
    first = runtime.attempts.dispatch_cycle_job(review.job_id, command_id=command)

    def no_reselection(*_args, **_kwargs):
        pytest.fail("retained review dispatch must not perform fresh selection")

    monkeypatch.setattr(runtime_module, "_review_candidate_exclusions", no_reselection)
    replay = runtime.attempts.dispatch_cycle_job(review.job_id, command_id=command)
    assert replay.attempt.attempt_id == first.attempt.attempt_id
    assert replay.attempt.worker_id == first.attempt.worker_id == "worker-b"
    assert runtime.jobs.get_job(review.job_id).attempt_count == 1


def test_review_of_repair_excludes_the_repair_principal_not_the_first_worker(tmp_path):
    from control_plane.executive_coo_cycle import CooCycle
    from tests.test_executive_os_phase1fc import _complete_ohf_role, _review_body

    runtime, review, _work, command = _pending_review(tmp_path)
    first = runtime.attempts.dispatch_cycle_job(review.job_id, command_id=command)
    target = runtime.validated_role_completion(
        review.reviews_job_id, expected_attempt_id=_work.attempt_id,
    )
    body = _review_body(
        root_id=review.root_job_id, plan_attempt_id=review.plan_attempt_id,
        plan_digest=review.plan_digest, plan_step_id=review.plan_step_id,
        target_job_id=review.reviews_job_id,
        target_attempt_id=target.attempt.attempt_id,
        target_result_digest=target.role_result_digest,
        repair_round=0, verdict="reject",
    )
    rejection, _ = _complete_ohf_role(runtime, first, body, identity_seed=4801)
    cycle = CooCycle(runtime)
    created = cycle.run_once(review.root_job_id)
    assert created.action == "REPAIR_CREATED"
    repair = runtime.jobs.get_job(created.selected_job_id)
    repaired = runtime.attempts.dispatch_cycle_job(
        repair.job_id,
        command_id=f"coo-cycle:{review.root_job_id}:dispatch:{repair.job_id}:attempt:1",
        worker_id="worker-b",
    )
    _complete_ohf_role(runtime, repaired, {
        "schema_version": "mastermind.repair_result/v1",
        "root_job_id": review.root_job_id, "plan_attempt_id": repair.plan_attempt_id,
        "plan_digest": repair.plan_digest, "plan_step_id": repair.plan_step_id,
        "repair_round": 1, "supersedes_job_id": repair.supersedes_job_id,
        "rejected_review_job_id": review.job_id,
        "rejected_review_result_digest": rejection["role_result_digest"],
        "artifacts": [], "evidence_digests": [],
    }, identity_seed=4802)
    next_review = cycle.run_once(review.root_job_id)
    assert next_review.action == "REVIEW_CREATED"
    selected = runtime.attempts.dispatch_cycle_job(
        next_review.selected_job_id,
        command_id=f"coo-cycle:{review.root_job_id}:dispatch:{next_review.selected_job_id}:attempt:1",
    )
    assert selected.attempt.worker_id == "worker-a"
    assert selected.attempt.worker_id != repaired.attempt.worker_id
