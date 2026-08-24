"""Adversarial durability, fencing, and reconciliation tests for Phase 1B."""
from __future__ import annotations

import json
import stat
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

import control_plane.executive_runtime as executive_runtime
from control_plane.executive_authority import AuthorityPolicyError
from control_plane.executive_runtime import (
    AttemptLease,
    AttemptStatus,
    JobPayload,
    JobStatus,
    PersistenceError,
    Runtime,
    StateConflict,
    WorkerStatus,
)


class MutableClock:
    def __init__(self, value: int = 1_800_000_000_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += seconds * 1_000


def _runtime(tmp_path, *, clock=None, lease_seconds: int = 60) -> Runtime:
    return Runtime.at(tmp_path, clock=clock, lease_seconds=lease_seconds)


def _register_default(runtime: Runtime, *, worker_id: str = "worker-01") -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code", "research"],
    )


def _claim_default(runtime: Runtime) -> tuple[str, AttemptLease]:
    job = runtime.jobs.create_job("Durable work")
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    return job.job_id, lease


def test_sqlite_defaults_pragmas_migration_and_five_durable_objects(tmp_path):
    runtime = _runtime(tmp_path)

    assert runtime.store.path == (
        tmp_path / "data" / "control_plane" / "executive.sqlite3"
    )
    assert stat.S_IMODE(runtime.store.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(runtime.store.path.stat().st_mode) == 0o600
    with runtime.store.read() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        migrations = connection.execute(
            "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert {"workers", "worker_quota_classes", "jobs", "attempts", "events"} <= tables
    assert [row[0:2] for row in migrations] == [
        (1, "executive_runtime_core"),
        (2, "durable_parent_child_review_contract"),
        (3, "ohf_session_epochs_and_process_generations"),
        (4, "executive_phase1fc_orchestration_contract"),
    ]
    assert all(len(row[2]) == 64 for row in migrations)


def test_policy_receipt_is_persisted_at_create_and_snapshotted_at_claim(
    tmp_path, monkeypatch
):
    calls: list[str] = []
    original_load = executive_runtime.ExecutiveAuthorityPolicy.load

    def observed_load(path=None):
        calls.append("load")
        return original_load(path)

    monkeypatch.setattr(
        executive_runtime.ExecutiveAuthorityPolicy,
        "load",
        staticmethod(observed_load),
    )
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    worktree = tmp_path / "assigned-worktree"
    job = runtime.jobs.create_job(
        "Authorized work",
        worktree=str(worktree),
        requested_authorities=["read", "write_branch", "run_tests"],
        allowed_write_paths=["control_plane/executive_runtime.py"],
        validation_commands=[["python3", "-m", "pytest", "-q"]],
    )
    lease = runtime.attempts.claim_job(job.job_id)

    assert lease is not None
    assert calls == ["load", "load"]
    assert job.requested_authorities == ["READ", "RUN_TESTS", "WRITE_BRANCH"]
    assert job.worktree == str(worktree.resolve())
    assert job.allowed_write_paths == ["control_plane/executive_runtime.py"]
    assert job.validation_commands == [["python3", "-m", "pytest", "-q"]]
    assert len(job.authority_policy_hash) == 64
    assert lease.attempt.authority_policy_hash == job.authority_policy_hash


def test_claim_reauthorizes_and_fails_closed_without_partial_assignment(
    tmp_path, monkeypatch
):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job = runtime.jobs.create_job("Policy-gated work")

    def unavailable_policy(path=None):
        raise AuthorityPolicyError("simulated missing policy")

    monkeypatch.setattr(
        executive_runtime.ExecutiveAuthorityPolicy,
        "load",
        staticmethod(unavailable_policy),
    )
    with pytest.raises(StateConflict, match="denied at claim time"):
        runtime.attempts.claim_job(job.job_id)

    persisted = runtime.jobs.get_job(job.job_id)
    quota = runtime.workers.get_quota_class("worker-01", "default")
    assert persisted is not None and persisted.status == JobStatus.QUEUED
    assert persisted.current_attempt_id is None
    assert quota is not None and quota.status == WorkerStatus.AVAILABLE
    assert quota.active_attempt_id is None
    assert runtime.attempts.list_attempts(job.job_id) == []


def test_stage2_job_requires_complete_execution_capability_identity(tmp_path):
    runtime = _runtime(tmp_path)
    with pytest.raises(StateConflict, match=r"stage2\+ routed Jobs require"):
        runtime.jobs.create_job(
            "Reject an unbound stage2 route",
            constraints={"routing_policy_version": "2026-08-24.stage2"},
        )

    with pytest.raises(StateConflict, match="complete profile/policy identity"):
        runtime.jobs.create_job(
            "Reject a partial capability grant",
            constraints={
                "execution_profile_id": "sealed.worker.write.no-extensions.v1",
                "execution_profile_digest": "a" * 64,
            },
        )


def test_quota_pool_matches_provider_model_effort_cost_class_and_caps(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "fable-account",
        provider="fable",
        account_label="fable",
        worker_type="mock",
        capabilities=["research"],
        quota_classes={
            "fable-eligible": {
                "provider": "fable",
                "model": "Fable-Research",
                "effort": "Deep",
                "cost_class": "Premium",
            }
        },
    )
    runtime.workers.register_worker(
        "claude-account",
        provider="claude",
        account_label="claude",
        worker_type="mock",
        capabilities=["research", "code"],
        quota_classes={
            "claude-native": {
                "provider": "claude",
                "model": "Opus",
                "effort": "Deep",
                "cost_class": "Premium",
                "caps": ["research", "code"],
            },
        },
    )
    job = runtime.jobs.create_job(
        "Use the exact Claude-native pool",
        constraints={
            "provider": "CLAUDE",
            "model": "OPUS",
            "effort": "DEEP",
            "cost_class": "PREMIUM",
            "required_capabilities": ["CODE"],
            "eligible_quota_classes": ["fable-eligible", "claude-native"],
        },
    )

    selected = runtime.broker.select_worker(job)
    lease = runtime.attempts.claim_job(job.job_id)

    assert selected is not None and selected.worker_id == "claude-account"
    assert lease is not None
    assert lease.attempt.quota_class == "claude-native"
    quota = runtime.workers.get_quota_class("claude-account", "claude-native")
    assert quota is not None
    assert (quota.provider, quota.model, quota.effort, quota.cost_class) == (
        "claude",
        "opus",
        "deep",
        "premium",
    )
    inherited = runtime.workers.get_quota_class("fable-account", "fable-eligible")
    assert inherited is not None and inherited.capabilities == ["research"]


def test_additive_quota_registration_is_exact_idempotent_and_idle_only(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    specification = {
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "cost_class": "small",
        "capabilities": ["code", "planning"],
        "metadata": {"execution_profile_digest": "a" * 64},
    }

    created = runtime.workers.register_quota_class(
        "worker-01", "codex-coo", **specification
    )
    replayed = runtime.workers.register_quota_class(
        "worker-01", "codex-coo", **specification
    )
    assert created == replayed
    assert len(
        [
            event
            for event in runtime.events.list_events()
            if event.event_type == "WORKER_QUOTA_REGISTERED"
        ]
    ) == 1

    with pytest.raises(StateConflict, match="different policy"):
        runtime.workers.register_quota_class(
            "worker-01", "codex-coo", **{**specification, "effort": "high"}
        )

    held_job = runtime.jobs.create_job("Hold the existing worker identity")
    assert runtime.attempts.claim_job(held_job.job_id) is not None
    with pytest.raises(StateConflict, match="active Attempt"):
        runtime.workers.register_quota_class(
            "worker-01",
            "codex-coo-default",
            **{**specification, "cost_class": "default"},
        )
    assert (
        runtime.workers.get_quota_class("worker-01", "codex-coo-default") is None
    )


def test_whole_identity_status_can_recover_an_offline_registered_worker(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.workers.register_worker(
        "offline-worker",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        status=WorkerStatus.OFFLINE,
    )
    job = runtime.jobs.create_job("Wait for worker recovery")
    assert runtime.attempts.claim_job(job.job_id) is None

    recovered = runtime.workers.set_worker_status(
        "offline-worker", WorkerStatus.AVAILABLE
    )
    lease = runtime.attempts.claim_job(job.job_id)

    assert recovered.status == WorkerStatus.AVAILABLE
    assert lease is not None and lease.attempt.worker_id == "offline-worker"


def test_atomic_claim_allows_exactly_one_winner_across_runtime_instances(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job = runtime.jobs.create_job("Contended work")
    barrier = Barrier(2)

    def contend() -> AttemptLease | str | None:
        contender = _runtime(tmp_path)
        barrier.wait()
        try:
            return contender.attempts.claim_job(job.job_id)
        except StateConflict as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: contend(), range(2)))

    winners = [item for item in outcomes if isinstance(item, AttemptLease)]
    assert len(winners) == 1
    assert len(runtime.attempts.list_attempts(job.job_id)) == 1
    persisted = runtime.jobs.get_job(job.job_id)
    assert persisted is not None and persisted.attempt_count == 1


def test_retry_creates_fresh_attempt_and_fences_both_old_credentials(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job_id, first = _claim_default(runtime)
    checkpoint = JobPayload(summary="half done", current_state="restartable")
    runtime.attempts.checkpoint_attempt(
        first.attempt.attempt_id,
        fence_generation=first.attempt.fence_generation,
        lease_token=first.lease_token,
        payload=checkpoint,
    )
    runtime.attempts.fail_attempt(
        first.attempt.attempt_id,
        fence_generation=first.attempt.fence_generation,
        lease_token=first.lease_token,
        payload=JobPayload(summary="retry", errors=["simulated"]),
    )
    runtime.jobs.requeue_job(job_id)
    second = runtime.attempts.claim_job(job_id)
    assert second is not None

    assert second.attempt.attempt_id != first.attempt.attempt_id
    assert second.attempt.attempt_number == 2
    assert second.attempt.fence_generation > first.attempt.fence_generation
    assert second.attempt.checkpoint == checkpoint.to_dict()
    with pytest.raises(StateConflict, match="stale fence"):
        runtime.attempts.heartbeat_attempt(
            second.attempt.attempt_id,
            fence_generation=first.attempt.fence_generation,
            lease_token=second.lease_token,
        )
    with pytest.raises(StateConflict, match="invalid lease token"):
        runtime.attempts.heartbeat_attempt(
            second.attempt.attempt_id,
            fence_generation=second.attempt.fence_generation,
            lease_token=first.lease_token,
        )


def test_mutation_fails_closed_if_quota_fence_diverges_from_active_attempt(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    _, lease = _claim_default(runtime)
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute(
            """
            UPDATE worker_quota_classes SET fence_counter=fence_counter+1
            WHERE worker_id='worker-01' AND quota_class='default'
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceError, match="inconsistent fences"):
        runtime.attempts.heartbeat_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )


def test_expiry_boundary_reconciles_lost_and_preserves_error_hold_until_requeue(
    tmp_path,
):
    clock = MutableClock()
    runtime = _runtime(tmp_path, clock=clock, lease_seconds=2)
    _register_default(runtime)
    job_id, lease = _claim_default(runtime)
    clock.advance(seconds=2)

    with pytest.raises(StateConflict, match="lease has expired"):
        runtime.attempts.heartbeat_attempt(
            lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    lost = runtime.attempts.restart_reconcile()

    assert [item.attempt_id for item in lost] == [lease.attempt.attempt_id]
    assert lost[0].status == AttemptStatus.LOST
    persisted = runtime.jobs.get_job(job_id)
    quota = runtime.workers.get_quota_class("worker-01", "default")
    assert persisted is not None and persisted.status == JobStatus.LOST
    assert quota is not None and quota.status == WorkerStatus.ERROR
    assert quota.active_attempt_id == lease.attempt.attempt_id

    runtime.jobs.requeue_job(job_id)
    quota = runtime.workers.get_quota_class("worker-01", "default")
    assert quota is not None and quota.active_attempt_id is None
    assert quota.status == WorkerStatus.ERROR


def test_targeted_expiry_reconcile_does_not_finalize_an_uninspected_attempt(tmp_path):
    clock = MutableClock()
    runtime = _runtime(tmp_path, clock=clock, lease_seconds=5)
    _register_default(runtime, worker_id="worker-01")
    _register_default(runtime, worker_id="worker-02")
    first = runtime.jobs.create_job("First durable work")
    second = runtime.jobs.create_job("Second durable work")
    first_lease = runtime.attempts.claim_job(first.job_id, worker_id="worker-01")
    second_lease = runtime.attempts.claim_job(second.job_id, worker_id="worker-02")
    assert first_lease is not None and second_lease is not None
    clock.advance(seconds=6)

    expired = runtime.attempts.reconcile_expired(
        attempt_id=first_lease.attempt.attempt_id
    )

    assert [item.attempt_id for item in expired] == [first_lease.attempt.attempt_id]
    persisted_first = runtime.attempts.get_attempt(first_lease.attempt.attempt_id)
    persisted_second = runtime.attempts.get_attempt(second_lease.attempt.attempt_id)
    assert persisted_first is not None and persisted_first.status is AttemptStatus.LOST
    assert persisted_second is not None and persisted_second.status is AttemptStatus.CLAIMED
    assert runtime.jobs.get_job(second.job_id).status is JobStatus.RUNNING  # type: ignore[union-attr]


def test_terminal_cancel_releases_a_held_class_when_retry_limit_is_exhausted(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job = runtime.jobs.create_job("One-shot work", attempt_limit=1)
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    runtime.attempts.rate_limit_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )

    with pytest.raises(StateConflict, match="attempt limit"):
        runtime.jobs.requeue_job(job.job_id)
    held = runtime.workers.get_quota_class("worker-01", "default")
    assert held is not None and held.active_attempt_id == lease.attempt.attempt_id

    cancelled = runtime.jobs.cancel_job(job.job_id)
    released = runtime.workers.get_quota_class("worker-01", "default")
    assert cancelled.status == JobStatus.CANCELLED
    assert released is not None and released.active_attempt_id is None
    assert released.status == WorkerStatus.RATE_LIMITED


def test_cancelled_attempt_lost_during_restart_does_not_leak_capacity_hold(tmp_path):
    clock = MutableClock()
    runtime = _runtime(tmp_path, clock=clock, lease_seconds=3)
    _register_default(runtime)
    job_id, lease = _claim_default(runtime)
    requested = runtime.jobs.cancel_job(job_id)
    assert requested.status == JobStatus.CANCEL_REQUESTED
    clock.advance(seconds=3)

    lost = _runtime(tmp_path, clock=clock, lease_seconds=3).attempts.restart_reconcile()

    assert len(lost) == 1 and lost[0].status == AttemptStatus.LOST
    job = runtime.jobs.get_job(job_id)
    quota = runtime.workers.get_quota_class("worker-01", "default")
    assert job is not None and job.status == JobStatus.CANCELLED
    assert quota is not None and quota.status == WorkerStatus.ERROR
    assert quota.active_attempt_id is None
    runtime.workers.set_worker_status("worker-01", WorkerStatus.AVAILABLE)
    assert runtime.workers.get_quota_class("worker-01", "default").status == WorkerStatus.AVAILABLE  # type: ignore[union-attr]


def test_process_identity_is_durable_and_running_transition_is_fenced(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    _, lease = _claim_default(runtime)
    attempt_id = lease.attempt.attempt_id
    assert lease.attempt.status == AttemptStatus.CLAIMED

    with pytest.raises(StateConflict, match="no durable process"):
        runtime.attempts.mark_running(
            attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )
    recorded = runtime.attempts.record_process(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        pid=4321,
        pgid=4321,
        process_start_identity="start-ticks-99",
        boot_id="boot-a",
        stdout_path="logs/stdout.log",
        stderr_path="logs/stderr.log",
        result_path="results/result.json",
        launch_metadata={"argv": ["worker", "run"]},
    )
    assert recorded.pid == recorded.pgid == 4321
    assert recorded.process_start_identity == "start-ticks-99"
    assert recorded.boot_id == "boot-a"
    assert recorded.launch_metadata == {"argv": ["worker", "run"]}
    with pytest.raises(StateConflict, match="complete launch attestation"):
        runtime.attempts.mark_running(
            attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            required_launch_attestation_schema=(
                "mastermind.executive_launch_attestation/v1"
            ),
        )
    with pytest.raises(StateConflict, match="already has a process identity"):
        runtime.attempts.record_process(
            attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            provider_session_id="replacement-must-not-win",
        )

    running = runtime.attempts.mark_running(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )
    exited = runtime.attempts.record_process_exit(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        exit_code=0,
        result_path="results/final.json",
        provider_session_id="provider-session-a",
    )
    reconstructed = _runtime(tmp_path).attempts.get_attempt(attempt_id)

    assert running.status == AttemptStatus.RUNNING
    assert exited.exit_code == 0
    assert reconstructed is not None
    assert reconstructed.provider_session_id == "provider-session-a"
    assert reconstructed.result_path == "results/final.json"
    assert reconstructed.stdout_path == "logs/stdout.log"


def test_restart_adoption_rotates_fence_and_token_with_one_race_winner(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    _, original = _claim_default(runtime)
    attempt_id = original.attempt.attempt_id
    runtime.attempts.record_process(
        attempt_id,
        fence_generation=original.attempt.fence_generation,
        lease_token=original.lease_token,
        provider_session_id="persisted-provider-session",
    )
    runtime.attempts.mark_running(
        attempt_id,
        fence_generation=original.attempt.fence_generation,
        lease_token=original.lease_token,
    )
    contenders = [_runtime(tmp_path), _runtime(tmp_path)]
    barrier = Barrier(2)

    def adopt(index: int) -> AttemptLease | str:
        barrier.wait()
        try:
            return contenders[index].attempts.adopt_attempt(
                attempt_id,
                expected_fence_generation=original.attempt.fence_generation,
                lease_owner=f"restarted-supervisor-{index}",
            )
        except StateConflict as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(adopt, range(2)))

    winners = [item for item in outcomes if isinstance(item, AttemptLease)]
    assert len(winners) == 1
    adopted = winners[0]
    assert adopted.attempt.status == AttemptStatus.RUNNING
    assert adopted.attempt.result is None
    assert adopted.attempt.fence_generation == original.attempt.fence_generation + 1
    assert adopted.lease_token != original.lease_token
    assert any("stale adoption fence" in item for item in outcomes if isinstance(item, str))

    with pytest.raises(StateConflict, match="stale fence"):
        runtime.attempts.heartbeat_attempt(
            attempt_id,
            fence_generation=original.attempt.fence_generation,
            lease_token=original.lease_token,
        )
    heartbeat = runtime.attempts.heartbeat_attempt(
        attempt_id,
        fence_generation=adopted.attempt.fence_generation,
        lease_token=adopted.lease_token,
    )
    assert heartbeat.lease_owner.startswith("restarted-supervisor-")


def test_explicit_mark_lost_requires_verified_absence_and_current_lease(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job_id, lease = _claim_default(runtime)
    attempt_id = lease.attempt.attempt_id
    runtime.attempts.record_process(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        provider_session_id="provider-session-lost",
    )
    runtime.attempts.mark_running(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
    )

    with pytest.raises(StateConflict, match="verified_process_absent"):
        runtime.attempts.mark_lost(
            attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
            reason="session lookup failed",
        )
    lost_job = runtime.attempts.mark_lost(
        attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        reason="provider confirmed session missing",
        verified_process_absent=True,
    )

    assert lost_job.job_id == job_id and lost_job.status == JobStatus.LOST
    lost_attempt = runtime.attempts.get_attempt(attempt_id)
    quota = runtime.workers.get_quota_class("worker-01", "default")
    assert lost_attempt is not None and lost_attempt.status == AttemptStatus.LOST
    assert lost_attempt.error == {
        "reason": "provider confirmed session missing",
        "verified_process_absent": True,
    }
    assert quota is not None and quota.status == WorkerStatus.ERROR
    with pytest.raises(StateConflict):
        runtime.attempts.heartbeat_attempt(
            attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token,
        )


def test_lease_token_is_absent_from_public_attempts_snapshots_and_events(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    _, lease = _claim_default(runtime)
    public_documents = {
        "attempt": lease.attempt.to_dict(),
        "claim": lease.to_dict(),
        "snapshot": runtime.store.snapshot(),
        "events": [event.to_dict() for event in runtime.events.list_events()],
    }
    serialized = json.dumps(public_documents, sort_keys=True)

    assert "lease_token" not in serialized
    assert lease.lease_token not in serialized


def test_event_and_terminal_attempt_rows_are_database_immutable(tmp_path):
    runtime = _runtime(tmp_path)
    _register_default(runtime)
    job_id, lease = _claim_default(runtime)
    runtime.attempts.complete_attempt(
        lease.attempt.attempt_id,
        fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token,
        payload=JobPayload(summary="done", current_state="complete"),
    )

    connection = sqlite3.connect(runtime.store.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="events are immutable"):
            connection.execute("UPDATE events SET actor='tampered' WHERE event_id=1")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="terminal attempts are immutable"):
            connection.execute(
                "UPDATE attempts SET status='FAILED' WHERE attempt_id=?",
                (lease.attempt.attempt_id,),
            )
        connection.rollback()
    finally:
        connection.close()
    assert runtime.jobs.get_job(job_id).status == JobStatus.COMPLETED  # type: ignore[union-attr]


def test_event_failure_rolls_back_linked_state_changes(tmp_path, monkeypatch):
    runtime = _runtime(tmp_path)

    def fail_event(*args, **kwargs):
        raise StateConflict("simulated event write failure")

    monkeypatch.setattr(runtime.store, "append_event", fail_event)
    with pytest.raises(StateConflict, match="event write failure"):
        _register_default(runtime)

    assert runtime.workers.list_workers() == []
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM worker_quota_classes").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_migration_checksum_tampering_fails_closed(tmp_path):
    runtime = _runtime(tmp_path)
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceError, match="checksum"):
        _runtime(tmp_path)


def test_v4_runtime_normal_open_refuses_existing_v2_without_v3_artifacts(
    tmp_path, monkeypatch
):
    migrations = executive_runtime._MIGRATIONS
    monkeypatch.setattr(executive_runtime, "_MIGRATIONS", migrations[:2])
    v2 = _runtime(tmp_path)
    database = v2.store.path

    monkeypatch.setattr(executive_runtime, "_MIGRATIONS", migrations)
    with pytest.raises(
        executive_runtime.ExecutiveSchemaUpgradeRequired,
        match="explicit offline",
    ):
        _runtime(tmp_path)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0] == 2
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
    finally:
        connection.close()
    assert "harness_session_epochs" not in tables
    assert "process_generations" not in tables
    assert "execution_mode" not in columns
