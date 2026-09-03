"""RED-first contract tests for the bounded Executive terminal-return reducer."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.executive_orchestration_result import canonical_digest
from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime
from control_plane.executive_terminal_return import (
    TerminalReturnError,
    reduce_terminal_return,
)
from tests.test_executive_os_phase1fc import (
    _complete_ohf_role,
    _cycle_through_completed_work,
    _review_body,
)


def _completed_planner(tmp_path):
    runtime, _cycle, _dispatches, _root, planner, _work, _seal = (
        _cycle_through_completed_work(
            tmp_path / "runtime",
            intent_id="CEO-TERMINAL-RETURN-PLANNER",
            review_workers=["worker-b"],
        )
    )
    job = runtime.jobs.get_job(planner.job_id)
    attempt = runtime.attempts.get_attempt(planner.attempt.attempt_id)
    worker = runtime.workers.get_worker(planner.attempt.worker_id)
    assert job is not None and attempt is not None and worker is not None
    return job, attempt, worker


def test_reducer_projects_one_exact_sealed_completed_child(tmp_path) -> None:
    job, attempt, worker = _completed_planner(tmp_path)
    assert job.result == attempt.result

    candidate = reduce_terminal_return(job=job, attempt=attempt, worker=worker)

    assert candidate.job_id == job.job_id
    assert candidate.attempt_id == attempt.attempt_id
    assert candidate.worker_id == worker.worker_id
    assert candidate.root_job_id == job.root_job_id
    assert candidate.role == "plan"
    assert candidate.runtime_status == "COMPLETED"
    assert candidate.result_status == "RESULT"
    assert candidate.operation_key == f"exec-{job.job_id.lower()}"
    assert candidate.session_ref == f"asd-session-exec-{job.job_id.lower()}"
    assert candidate.result_digest == job.result["result_envelope_digest"]
    assert candidate.terminal_digest == job.result["terminal_evidence_digest"]
    assert candidate.message_key == f"asd-exec-result-{candidate.terminal_digest}"
    assert candidate.summary == "bounded typed fixture result"
    assert candidate.review_verdict is None


def _completed_review(tmp_path, verdict: str):
    runtime, cycle, dispatches, root, planner, work, work_seal = _cycle_through_completed_work(
        tmp_path / verdict,
        intent_id=f"CEO-TERMINAL-RETURN-{verdict.upper()}",
        review_workers=["worker-b"],
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    work_job = runtime.jobs.get_job(work.attempt.job_id)
    assert work_job is not None
    _complete_ohf_role(
        runtime,
        review,
        _review_body(
            root_id=root.job_id,
            plan_attempt_id=planner.attempt.attempt_id,
            plan_digest=str(work_job.plan_digest),
            target_job_id=work.attempt.job_id,
            target_attempt_id=work.attempt.attempt_id,
            target_result_digest=work_seal["role_result_digest"],
            repair_round=0,
            verdict=verdict,
        ),
        identity_seed=744 if verdict == "approve" else 745,
    )
    job = runtime.jobs.get_job(review.attempt.job_id)
    attempt = runtime.attempts.get_attempt(review.attempt.attempt_id)
    worker = runtime.workers.get_worker(review.attempt.worker_id)
    assert job is not None and attempt is not None and worker is not None
    return job, attempt, worker


@pytest.mark.parametrize("verdict", ["approve", "reject"])
def test_reducer_is_deterministic_and_preserves_review_verdict_shape(
    tmp_path, verdict
) -> None:
    job, attempt, worker = _completed_review(tmp_path, verdict)

    first = reduce_terminal_return(job=job, attempt=attempt, worker=worker)
    second = reduce_terminal_return(job=job, attempt=attempt, worker=worker)

    assert first == second
    assert first.review_verdict == verdict


@pytest.mark.parametrize(
    "job_change,attempt_change,worker_change",
    [
        ({"parent_job_id": "JOB-999"}, {}, {}),
        ({"current_attempt_id": "ATT-stale"}, {}, {}),
        ({}, {"worker_id": "worker-other"}, {}),
        ({}, {}, {"worker_id": "worker-other"}),
    ],
)
def test_reducer_refuses_parent_attempt_or_worker_identity_drift(
    tmp_path, job_change, attempt_change, worker_change
) -> None:
    job, attempt, worker = _completed_planner(tmp_path)

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=dataclasses.replace(job, **job_change),
            attempt=dataclasses.replace(attempt, **attempt_change),
            worker=dataclasses.replace(worker, **worker_change),
        )

    assert raised.value.code in {"IDENTITY_REFUSED", "BINDING_REFUSED"}


def test_reducer_refuses_mutated_noncanonical_or_unsealed_receipt(tmp_path) -> None:
    job, attempt, worker = _completed_planner(tmp_path)
    changed = dict(attempt.result)
    changed["terminal_evidence_digest"] = "0" * 64

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=dataclasses.replace(job, result=changed),
            attempt=dataclasses.replace(attempt, result=changed),
            worker=worker,
        )

    assert raised.value.code == "EVIDENCE_REFUSED"


def test_reducer_refuses_nan_nested_in_the_terminal_receipt(tmp_path) -> None:
    job, attempt, worker = _completed_planner(tmp_path)
    changed = dict(attempt.result)
    changed["result_evidence"] = {"unserializable": float("nan")}

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=dataclasses.replace(job, result=changed),
            attempt=dataclasses.replace(attempt, result=changed),
            worker=worker,
        )

    assert raised.value.code == "EVIDENCE_REFUSED"


def test_reducer_refuses_missing_execution_mode_binding(tmp_path) -> None:
    job, attempt, worker = _completed_planner(tmp_path)

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=job,
            attempt=dataclasses.replace(attempt, execution_mode=None),
            worker=worker,
        )

    assert raised.value.code == "BINDING_REFUSED"


def test_reducer_refuses_unvalidated_sealed_worker_evidence(tmp_path) -> None:
    job, attempt, worker = _completed_planner(tmp_path)
    changed = dict(attempt.result)
    changed["execution_mode"] = "SEALED_WORKER"
    changed["result_seal_command_id"] = f"sealed-worker-result:{attempt.attempt_id}"
    changed["result_evidence"] = {
        "schema_version": "fixture",
        "secret": "must-not-project",
    }
    unsigned = dict(changed)
    unsigned.pop("terminal_evidence_digest")
    changed["terminal_evidence_digest"] = canonical_digest(unsigned)

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=dataclasses.replace(job, result=changed),
            attempt=dataclasses.replace(
                attempt,
                execution_mode="SEALED_WORKER",
                result=changed,
            ),
            worker=worker,
        )

    assert raised.value.code == "EVIDENCE_REFUSED"


@pytest.mark.parametrize("side", ["job", "attempt"])
def test_reducer_refuses_divergent_job_and_attempt_result(tmp_path, side) -> None:
    job, attempt, worker = _completed_planner(tmp_path)
    changed = dict(job.result)
    changed["terminal_evidence_digest"] = "f" * 64
    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=dataclasses.replace(job, result=changed) if side == "job" else job,
            attempt=(
                dataclasses.replace(attempt, result=changed)
                if side == "attempt"
                else attempt
            ),
            worker=worker,
        )

    assert raised.value.code == "EVIDENCE_REFUSED"


@pytest.mark.parametrize("status", [AttemptStatus.FAILED, AttemptStatus.LOST, AttemptStatus.CANCELLED, AttemptStatus.RATE_LIMITED])
def test_reducer_gates_noncompleted_terminal_families(tmp_path, status) -> None:
    job, attempt, worker = _completed_planner(tmp_path)

    with pytest.raises(TerminalReturnError) as raised:
        reduce_terminal_return(
            job=dataclasses.replace(job, status=JobStatus(status.value)),
            attempt=dataclasses.replace(attempt, status=status),
            worker=worker,
        )

    assert raised.value.code == "NOT_APPLICABLE"
