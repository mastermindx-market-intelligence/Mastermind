"""Phase 1A proof: persisted workers/jobs, checkpointed failover, and release."""
from __future__ import annotations

import json
import sqlite3

import pytest

from control_plane.worker_runtime import (
    JobPayload,
    JobStatus,
    PersistenceError,
    Runtime,
    StateConflict,
    WorkerStatus,
)


def _runtime(tmp_path) -> Runtime:
    return Runtime.at(tmp_path)


def _register_pair(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="claude-a",
        worker_type="mock",
        capabilities=["research", "code"],
        quota_classes={
            "fable-eligible": ["research", "code"],
            "claude-native": ["research", "code"],
        },
    )
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="codex-a",
        worker_type="mock",
        capabilities=["research", "code"],
        quota_classes={"codex-native": ["research", "code"]},
    )


def _checkpoint() -> JobPayload:
    return JobPayload(
        summary="Research packet collected",
        completed_steps=["read inputs", "record evidence"],
        current_state="ready for synthesis",
        artifacts=["jobs/JOB-001/evidence.json"],
        next_actions=["write conclusion"],
        errors=[],
    )


def test_worker_registration_persists_across_registry_instances(tmp_path):
    runtime = _runtime(tmp_path)
    worker = runtime.workers.register_worker(
        "claude-01",
        provider="Claude",
        account_label="primary",
        worker_type="mock",
        capabilities=["Research", "research", "Code"],
        quota_classes={
            "Fable-Eligible": ["Research"],
            "Claude-Native": ["Code"],
        },
    )

    reloaded = _runtime(tmp_path).workers.get_worker("claude-01")
    assert reloaded == worker
    assert reloaded.status == WorkerStatus.AVAILABLE
    assert reloaded.capabilities == ["code", "research"]
    assert reloaded.quota_classes == {
        "claude-native": {
            "active_job_id": None,
            "capabilities": ["code"],
            "status": "AVAILABLE",
        },
        "fable-eligible": {
            "active_job_id": None,
            "capabilities": ["research"],
            "status": "AVAILABLE",
        },
    }
    with pytest.raises(StateConflict):
        runtime.workers.register_worker(
            "claude-01",
            provider="claude",
            account_label="duplicate",
            worker_type="mock",
        )


def test_singular_capability_is_one_value_not_character_classes(tmp_path):
    runtime = _runtime(tmp_path)
    worker = runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="primary",
        worker_type="mock",
        capabilities="Research",
    )
    job = runtime.jobs.create_job(
        "Research job",
        constraints={"required_capabilities": "Research"},
    )

    assigned = runtime.broker.dispatch(job.job_id)
    assert worker.capabilities == ["research"]
    assert job.constraints["required_capabilities"] == ["research"]
    assert assigned is not None and assigned.worker_id == "claude-01"


def test_job_creation_persists_required_shape_and_monotonic_id(tmp_path):
    runtime = _runtime(tmp_path)
    first = runtime.jobs.create_job(
        "Investigate foo",
        department="research",
        priority=7,
        authority_level="A0",
        branch="codex/foo",
        worktree="/tmp/foo",
        constraints={
            "provider": "claude",
            "required_capabilities": ["research"],
            "eligible_quota_classes": ["fable-eligible", "codex-native"],
        },
    )
    second = runtime.jobs.create_job("Investigate bar")

    assert (first.job_id, second.job_id) == ("JOB-001", "JOB-002")
    assert first.status == JobStatus.QUEUED
    assert first.assigned_worker_id is None
    assert first.assigned_quota_class is None
    assert first.constraints["eligible_quota_classes"] == ["codex-native", "fable-eligible"]
    assert second.constraints["eligible_quota_classes"] == ["default"]
    assert first.checkpoint is None and first.result is None
    assert _runtime(tmp_path).jobs.get_job("JOB-001") == first


def test_dispatch_assigns_worker_and_job_in_one_snapshot(tmp_path):
    runtime = _runtime(tmp_path)
    _register_pair(runtime)
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={
            "provider": "claude",
            "required_capabilities": ["research"],
            "eligible_quota_classes": ["fable-eligible"],
        },
    )

    selected = runtime.broker.dispatch(job.job_id)

    assert selected is not None and selected.worker_id == "claude-01"
    persisted = _runtime(tmp_path)
    assert persisted.jobs.get_job(job.job_id).status == JobStatus.RUNNING  # type: ignore[union-attr]
    assert persisted.jobs.get_job(job.job_id).assigned_worker_id == "claude-01"  # type: ignore[union-attr]
    assert persisted.jobs.get_job(job.job_id).assigned_quota_class == "fable-eligible"  # type: ignore[union-attr]
    # The identity summary advertises remaining capacity: another independent
    # class is still available even though fable-eligible is busy.
    assert persisted.workers.get_worker("claude-01").status == WorkerStatus.AVAILABLE  # type: ignore[union-attr]
    assert persisted.workers.get_worker("claude-01").active_job_id == job.job_id  # type: ignore[union-attr]
    assert (
        persisted.workers.get_worker("claude-01").quota_classes["fable-eligible"]  # type: ignore[union-attr]
        ["active_job_id"]
        == job.job_id
    )


def test_checkpoint_payload_persists_with_all_structured_fields(tmp_path):
    runtime = _runtime(tmp_path)
    _register_pair(runtime)
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={"eligible_quota_classes": ["claude-native"]},
    )
    runtime.jobs.assign_job(job.job_id, "claude-01")

    checkpointed = runtime.jobs.checkpoint_job(job.job_id, _checkpoint())
    reloaded = _runtime(tmp_path).jobs.get_job(job.job_id)

    assert checkpointed.status == JobStatus.CHECKPOINTED
    assert reloaded is not None and reloaded.checkpoint == _checkpoint().to_dict()
    assert set(reloaded.checkpoint) == {
        "summary",
        "completed_steps",
        "current_state",
        "artifacts",
        "next_actions",
        "errors",
    }


def test_rate_limit_marks_capacity_and_job_without_losing_checkpoint(tmp_path):
    runtime = _runtime(tmp_path)
    _register_pair(runtime)
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={"eligible_quota_classes": ["claude-native"]},
    )
    runtime.jobs.assign_job(job.job_id, "claude-01")
    runtime.jobs.checkpoint_job(job.job_id, _checkpoint())

    assigned = runtime.jobs.get_job(job.job_id)
    limited = runtime.workers.set_worker_status(
        "claude-01",
        WorkerStatus.RATE_LIMITED,
        quota_class=assigned.assigned_quota_class,  # type: ignore[union-attr]
    )
    persisted_job = runtime.jobs.get_job(job.job_id)

    assert limited.status == WorkerStatus.AVAILABLE
    assert limited.active_job_id == job.job_id
    assert limited.quota_classes["claude-native"]["status"] == "RATE_LIMITED"
    assert limited.quota_classes["fable-eligible"]["status"] == "AVAILABLE"
    assert persisted_job is not None and persisted_job.status == JobStatus.RATE_LIMITED
    assert persisted_job.checkpoint == _checkpoint().to_dict()


def test_requeue_preserves_checkpoint_and_rate_limited_worker_state(tmp_path):
    runtime = _runtime(tmp_path)
    _register_pair(runtime)
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={"eligible_quota_classes": ["claude-native"]},
    )
    runtime.jobs.assign_job(job.job_id, "claude-01")
    runtime.jobs.checkpoint_job(job.job_id, _checkpoint())
    assigned = runtime.jobs.get_job(job.job_id)
    runtime.workers.set_worker_status(
        "claude-01",
        WorkerStatus.RATE_LIMITED,
        quota_class=assigned.assigned_quota_class,  # type: ignore[union-attr]
    )

    requeued = runtime.jobs.requeue_job(job.job_id)
    claude = runtime.workers.get_worker("claude-01")

    assert requeued.status == JobStatus.QUEUED
    assert requeued.assigned_worker_id is None
    assert requeued.assigned_quota_class is None
    assert requeued.checkpoint == _checkpoint().to_dict()
    assert claude is not None and claude.status == WorkerStatus.AVAILABLE
    assert claude.active_job_id is None
    assert claude.quota_classes["claude-native"]["status"] == "RATE_LIMITED"
    assert claude.quota_classes["fable-eligible"]["status"] == "AVAILABLE"


def test_reassignment_selects_another_eligible_worker_and_keeps_checkpoint(tmp_path):
    runtime = _runtime(tmp_path)
    _register_pair(runtime)
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={
            "required_capabilities": ["research"],
            "eligible_quota_classes": ["fable-eligible", "codex-native"],
        },
    )
    runtime.jobs.assign_job(job.job_id, "claude-01", quota_class="fable-eligible")
    runtime.jobs.checkpoint_job(job.job_id, _checkpoint())
    runtime.workers.set_worker_status(
        "claude-01",
        WorkerStatus.RATE_LIMITED,
        quota_class="fable-eligible",
    )
    runtime.jobs.requeue_job(job.job_id)

    replacement = runtime.broker.dispatch(job.job_id)
    reassigned = _runtime(tmp_path).jobs.get_job(job.job_id)

    assert replacement is not None and replacement.worker_id == "codex-01"
    assert reassigned is not None and reassigned.assigned_worker_id == "codex-01"
    assert reassigned.assigned_quota_class == "codex-native"
    assert reassigned.status == JobStatus.RUNNING
    assert reassigned.checkpoint == _checkpoint().to_dict()

    result = JobPayload(summary="Failover complete", current_state="done")
    completed = runtime.jobs.complete_job(job.job_id, result)
    claude = _runtime(tmp_path).workers.get_worker("claude-01")
    codex = _runtime(tmp_path).workers.get_worker("codex-01")
    assert completed.status == JobStatus.COMPLETED
    assert completed.checkpoint == _checkpoint().to_dict()
    assert completed.result == result.to_dict()
    assert claude is not None
    assert claude.quota_classes["fable-eligible"]["status"] == "RATE_LIMITED"
    assert codex is not None
    assert codex.quota_classes["codex-native"]["status"] == "AVAILABLE"
    assert codex.quota_classes["codex-native"]["active_job_id"] is None


def test_completed_job_persists_result_and_releases_worker(tmp_path):
    runtime = _runtime(tmp_path)
    _register_pair(runtime)
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={"eligible_quota_classes": ["codex-native"]},
    )
    runtime.jobs.assign_job(job.job_id, "codex-01")
    runtime.jobs.checkpoint_job(job.job_id, _checkpoint())
    result = JobPayload(
        summary="Investigation complete",
        completed_steps=["write conclusion"],
        current_state="done",
        artifacts=["jobs/JOB-001/result.json"],
        next_actions=[],
        errors=[],
    )

    completed = runtime.jobs.complete_job(job.job_id, result)
    worker = _runtime(tmp_path).workers.get_worker("codex-01")

    assert completed.status == JobStatus.COMPLETED
    assert completed.assigned_worker_id == "codex-01"
    assert completed.checkpoint == _checkpoint().to_dict()
    assert completed.result == result.to_dict()
    assert worker is not None and worker.status == WorkerStatus.AVAILABLE
    assert worker.active_job_id is None


def test_one_worker_runs_independent_jobs_on_two_quota_classes(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="shared-account",
        worker_type="mock",
        quota_classes={
            "fable-eligible": ["research"],
            "claude-native": ["code"],
        },
    )
    fable_job = runtime.jobs.create_job(
        "Research with Fable capacity",
        constraints={
            "required_capabilities": ["research"],
            "eligible_quota_classes": ["fable-eligible"],
        },
    )
    native_job = runtime.jobs.create_job(
        "Implement with native capacity",
        constraints={
            "required_capabilities": ["code"],
            "eligible_quota_classes": ["claude-native"],
        },
    )

    assert runtime.broker.dispatch(fable_job.job_id).worker_id == "claude-01"  # type: ignore[union-attr]
    assert runtime.broker.dispatch(native_job.job_id).worker_id == "claude-01"  # type: ignore[union-attr]
    worker = runtime.workers.get_worker("claude-01")

    assert worker is not None
    assert worker.quota_classes["fable-eligible"]["active_job_id"] == fable_job.job_id
    assert worker.quota_classes["claude-native"]["active_job_id"] == native_job.job_id
    assert runtime.jobs.get_job(fable_job.job_id).assigned_quota_class == "fable-eligible"  # type: ignore[union-attr]
    assert runtime.jobs.get_job(native_job.job_id).assigned_quota_class == "claude-native"  # type: ignore[union-attr]

    runtime.workers.set_worker_status(
        "claude-01",
        WorkerStatus.RATE_LIMITED,
        quota_class="fable-eligible",
    )
    worker = runtime.workers.get_worker("claude-01")
    assert worker is not None and worker.status == WorkerStatus.BUSY
    assert worker.quota_classes["fable-eligible"]["status"] == "RATE_LIMITED"
    assert worker.quota_classes["claude-native"]["status"] == "BUSY"
    assert runtime.jobs.get_job(fable_job.job_id).status == JobStatus.RATE_LIMITED  # type: ignore[union-attr]
    assert runtime.jobs.get_job(native_job.job_id).status == JobStatus.RUNNING  # type: ignore[union-attr]

    runtime.jobs.requeue_job(fable_job.job_id)
    runtime.jobs.complete_job(
        native_job.job_id,
        JobPayload(summary="Native work complete", current_state="done"),
    )
    worker = _runtime(tmp_path).workers.get_worker("claude-01")
    assert worker is not None and worker.status == WorkerStatus.AVAILABLE
    assert worker.quota_classes["fable-eligible"] == {
        "active_job_id": None,
        "capabilities": ["research"],
        "status": "RATE_LIMITED",
    }
    assert worker.quota_classes["claude-native"] == {
        "active_job_id": None,
        "capabilities": ["code"],
        "status": "AVAILABLE",
    }


def test_failed_job_releases_only_its_quota_class_and_can_requeue(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="shared-account",
        worker_type="mock",
        quota_classes={"class-a": ["research"], "class-b": ["research"]},
    )
    first = runtime.jobs.create_job(
        "First job",
        constraints={"eligible_quota_classes": ["class-a"]},
    )
    second = runtime.jobs.create_job(
        "Second job",
        constraints={"eligible_quota_classes": ["class-b"]},
    )
    runtime.broker.dispatch(first.job_id)
    runtime.broker.dispatch(second.job_id)

    failed = runtime.jobs.fail_job(
        first.job_id,
        JobPayload(summary="Mock failure", errors=["simulated"]),
    )
    worker = runtime.workers.get_worker("claude-01")

    assert failed.status == JobStatus.FAILED
    assert worker is not None and worker.status == WorkerStatus.AVAILABLE
    assert worker.quota_classes["class-a"]["status"] == "AVAILABLE"
    assert worker.quota_classes["class-a"]["active_job_id"] is None
    assert worker.quota_classes["class-b"]["active_job_id"] == second.job_id

    with pytest.raises(StateConflict, match="cannot fail from FAILED"):
        runtime.jobs.fail_job(
            failed.job_id,
            JobPayload(summary="Duplicate failure", errors=["must reject"]),
        )

    requeued = runtime.jobs.requeue_job(first.job_id)
    assert requeued.status == JobStatus.QUEUED
    assert requeued.assigned_worker_id is None
    assert requeued.assigned_quota_class is None


def test_operator_release_and_busy_status_are_quota_class_safe(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="shared-account",
        worker_type="mock",
        quota_classes={"fable-eligible": [], "claude-native": []},
    )
    runtime.workers.set_worker_status(
        "claude-01",
        WorkerStatus.RATE_LIMITED,
        quota_class="fable-eligible",
    )
    runtime.workers.set_worker_status(
        "claude-01",
        WorkerStatus.OFFLINE,
        quota_class="claude-native",
    )

    with pytest.raises(StateConflict, match="quota_class is required"):
        runtime.workers.release_worker("claude-01")
    with pytest.raises(StateConflict, match="assign a job"):
        runtime.workers.set_worker_status(
            "claude-01",
            WorkerStatus.BUSY,
            quota_class="claude-native",
        )

    released = runtime.workers.release_worker(
        "claude-01",
        quota_class="claude-native",
    )
    assert released.quota_classes["claude-native"]["status"] == "AVAILABLE"
    assert released.quota_classes["fable-eligible"]["status"] == "RATE_LIMITED"


def test_broker_returns_none_when_no_worker_matches_constraints(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code"],
        quota_classes=["codex-native"],
    )
    job = runtime.jobs.create_job(
        "Investigate foo",
        constraints={
            "provider": "claude",
            "required_capabilities": ["research"],
            "eligible_quota_classes": ["fable-eligible"],
        },
    )

    assert runtime.broker.select_worker(job) is None
    assert runtime.broker.dispatch(job.job_id) is None
    assert runtime.jobs.get_job(job.job_id).status == JobStatus.QUEUED  # type: ignore[union-attr]


def test_omitted_quota_eligibility_defaults_without_wildcard_routing(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="primary",
        worker_type="mock",
        quota_classes=["claude-native"],
    )
    job = runtime.jobs.create_job("Default-class job")

    assert job.constraints["eligible_quota_classes"] == ["default"]
    assert runtime.broker.dispatch(job.job_id) is None
    assert runtime.jobs.get_job(job.job_id).status == JobStatus.QUEUED  # type: ignore[union-attr]


def test_corrupt_snapshot_fails_closed_instead_of_resetting_state(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.store.path.write_bytes(b"{not-sqlite")

    with pytest.raises(PersistenceError):
        runtime.jobs.create_job("must not overwrite corruption")
    assert runtime.store.path.read_bytes() == b"{not-sqlite"


def test_unavailable_sqlite_writer_prevents_unlocked_write(tmp_path):
    runtime = Runtime.at(tmp_path, busy_timeout_ms=0)
    blocker = sqlite3.connect(runtime.store.path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(PersistenceError, match="locked"):
            runtime.jobs.create_job("must remain unpersisted")
    finally:
        blocker.rollback()
        blocker.close()
    assert runtime.jobs.list_jobs() == []


def test_cli_round_trip_uses_the_same_persisted_state(tmp_path, capsys):
    from scripts.executive_os_phase1a import main

    root = str(tmp_path)
    assert main(["--root", root, "register-worker", "codex-01", "--provider", "codex",
                 "--account-label", "primary", "--capability", "research",
                 "--quota-class", "codex-native"]) == 0
    capsys.readouterr()
    assert main(["--root", root, "create-job", "Investigate foo", "--capability", "research",
                 "--quota-class", "codex-native"]) == 0
    capsys.readouterr()
    assert main(["--root", root, "dispatch", "JOB-001"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["assigned_worker_id"] == "codex-01"
    assert output["assigned_quota_class"] == "codex-native"
    assert output["job"]["status"] == "RUNNING"
