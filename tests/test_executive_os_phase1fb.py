from __future__ import annotations

import sqlite3

import pytest

from control_plane.executive_runtime import JobPayload, JobStatus, Runtime, StateConflict


def _register(runtime: Runtime, worker_id: str) -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}-account",
        worker_type="fixture",
        capabilities=["code", "research", "review"],
    )


def _complete(
    runtime: Runtime,
    job_id: str,
    worker_id: str,
    *,
    verdict: str = "",
) -> None:
    lease = runtime.attempts.claim_job(job_id, worker_id=worker_id)
    assert lease is not None
    runtime.jobs.complete_job(
        job_id,
        JobPayload(summary="fixture complete", current_state="complete", verdict=verdict),
    )


def test_parent_child_fields_migrate_preserve_and_derive_root_depth(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job("Bounded child", parent_job_id=parent.job_id)

    assert parent.root_job_id == parent.job_id
    assert parent.parent_job_id is None
    assert parent.depth == 0
    assert child.parent_job_id == parent.job_id
    assert child.root_job_id == parent.job_id
    assert child.depth == 1
    assert child.owner_seat == "coo"
    assert child.escalation_target == "coo"
    assert child.business_impact == "routine"
    assert child.review_required is False
    assert child.reviews_job_id is None
    assert Runtime.at(tmp_path).jobs.get_job(child.job_id) == child
    with Runtime.at(tmp_path).store.read() as connection:
        assert connection.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()[0] == 2


def test_parent_with_living_child_is_not_claimable_or_selectable(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    parent = runtime.jobs.create_job("Parent container")
    runtime.jobs.create_job("Living child", parent_job_id=parent.job_id)

    assert runtime.broker.select_worker(parent) is None
    with pytest.raises(StateConflict, match=r"child job\(s\) are living"):
        runtime.attempts.claim_job(parent.job_id)


def test_review_verdict_is_fail_closed(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    job = runtime.jobs.create_job("Review payload")
    lease = runtime.attempts.claim_job(job.job_id, worker_id="worker-a")
    assert lease is not None

    with pytest.raises(StateConflict, match="verdict"):
        runtime.jobs.complete_job(job.job_id, {"summary": "bad", "verdict": "defer"})


def test_same_worker_review_is_void_and_cannot_aggregate_parent(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job(
        "Review-required child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Independent review slot", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )

    _complete(runtime, child.job_id, "worker-a")
    _complete(runtime, review.job_id, "worker-a", verdict="approve")
    review_event = runtime.events.list_events(job_id=review.job_id)[-1]
    assert review_event.payload["review"] == {
        "reviews_job_id": child.job_id,
        "status": "VOID",
        "reason": "review_not_independent",
        "voids": runtime.jobs.get_job(child.job_id).current_attempt_id,  # type: ignore[union-attr]
    }

    parent_lease = runtime.attempts.claim_job(parent.job_id, worker_id="worker-b")
    assert parent_lease is not None
    with pytest.raises(StateConflict, match="independent completed review"):
        runtime.jobs.complete_job(parent.job_id, JobPayload(summary="aggregate"))


def test_independent_approved_review_allows_parent_completion(tmp_path):
    runtime = Runtime.at(tmp_path)
    _register(runtime, "worker-a")
    _register(runtime, "worker-b")
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job(
        "Review-required child", parent_job_id=parent.job_id, review_required=True
    )
    review = runtime.jobs.create_job(
        "Independent review slot", parent_job_id=parent.job_id, reviews_job_id=child.job_id
    )

    _complete(runtime, child.job_id, "worker-a")
    _complete(runtime, review.job_id, "worker-b", verdict="approve")
    parent_lease = runtime.attempts.claim_job(parent.job_id, worker_id="worker-a")
    assert parent_lease is not None
    completed = runtime.jobs.complete_job(parent.job_id, JobPayload(summary="aggregate"))
    assert completed.status is JobStatus.COMPLETED


def test_review_pointer_and_parent_are_immutable(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job("Parent")
    child = runtime.jobs.create_job("Child", parent_job_id=parent.job_id)

    with runtime.store.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE jobs SET parent_job_id=NULL WHERE job_id=?", (child.job_id,)
            )


def test_owner_and_escalation_require_typed_provenance_and_shrink_only(tmp_path):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="typed executive provenance"):
        runtime.jobs.create_job("Unproven CEO job", owner_seat="ceo")

    root = runtime.jobs.create_job(
        "CEO-rooted job",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance={"schema": "mastermind.ceo_intent.v1", "actor": "sol"},
    )
    with pytest.raises(StateConflict, match="shrink"):
        runtime.jobs.create_job(
            "Child tries to elevate",
            parent_job_id=root.job_id,
            escalation_target="chairman",
            provenance={
                "schema": "mastermind.chairman_decision.v1",
                "actor": "chairman",
            },
        )
    child = runtime.jobs.create_job(
        "Child shrinks to COO",
        parent_job_id=root.job_id,
        escalation_target="coo",
    )
    assert child.escalation_target == "coo"
