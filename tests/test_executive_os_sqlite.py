"""Adversarial durability, fencing, and reconciliation tests for Phase 1B."""

from __future__ import annotations

import dataclasses
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


class WriteLockRequiredClock:
    """Refuse a time sample unless another connection owns the write lock."""

    def __init__(self, database_path, value: int) -> None:
        self.database_path = database_path
        self.value = value

    def __call__(self) -> int:
        probe = sqlite3.connect(self.database_path, timeout=0, isolation_level=None)
        try:
            probe.execute("PRAGMA busy_timeout=0")
            try:
                probe.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                return self.value
            probe.rollback()
        finally:
            probe.close()
        raise AssertionError("C2 sampled its clock before acquiring BEGIN IMMEDIATE")


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
    assert (
        len(
            [
                event
                for event in runtime.events.list_events()
                if event.event_type == "WORKER_QUOTA_REGISTERED"
            ]
        )
        == 1
    )

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
    assert runtime.workers.get_quota_class("worker-01", "codex-coo-default") is None


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
        connection.execute("""
            UPDATE worker_quota_classes SET fence_counter=fence_counter+1
            WHERE worker_id='worker-01' AND quota_class='default'
            """)
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
    assert (
        persisted_second is not None
        and persisted_second.status is AttemptStatus.CLAIMED
    )
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
    assert any(
        "stale adoption fence" in item for item in outcomes if isinstance(item, str)
    )

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
        with pytest.raises(
            sqlite3.IntegrityError, match="terminal attempts are immutable"
        ):
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
        assert (
            connection.execute("SELECT COUNT(*) FROM worker_quota_classes").fetchone()[
                0
            ]
            == 0
        )
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_migration_checksum_tampering_fails_closed(tmp_path):
    runtime = _runtime(tmp_path)
    connection = sqlite3.connect(runtime.store.path)
    try:
        connection.execute(
            "UPDATE schema_migrations SET checksum='tampered' WHERE version=1"
        )
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
        assert (
            connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[
                0
            ]
            == 2
        )
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


def _c2_r1a_ready_source(tmp_path, monkeypatch):
    """Build one genuine, reviewed COO root at the aggregation handoff edge."""

    import tests.test_executive_os_phase1fc as phase1fc

    original_v2_intent = phase1fc._v2_intent

    def c2_v2_intent(**overrides):
        return original_v2_intent(workstream="WS:C2_R1A", **overrides)

    monkeypatch.setattr(phase1fc, "_v2_intent", c2_v2_intent)

    runtime, cycle, dispatches, root, planner, work, work_seal = (
        phase1fc._cycle_through_completed_work(
            tmp_path,
            intent_id="CEO-C2-R1A-HAPPY",
            review_workers=["worker-b"],
        )
    )
    assert cycle.run_once(root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    work_job = runtime.jobs.get_job(work.attempt.job_id)
    assert work_job is not None and work_job.plan_digest is not None
    review_body = phase1fc._review_body(
        root_id=root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=work_job.plan_digest,
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    phase1fc._complete_ohf_role(runtime, review, review_body, identity_seed=3901)
    assert cycle.run_once(root.job_id).action == "HANDOFF_CREATED"
    runtime.jobs.get_cycle_handoff(root.job_id)

    # Completed COO fixture workers are deliberately ineligible for the new
    # alias carrier.  C1 sees exactly one current Codex READ candidate.
    runtime.workers.set_worker_status("worker-a", WorkerStatus.OFFLINE)
    runtime.workers.set_worker_status("worker-b", WorkerStatus.OFFLINE)
    runtime.workers.register_worker(
        "c2-codex-read",
        provider="codex",
        account_label="c2-primary",
        worker_type="codex",
        capabilities=["read"],
        quota_classes={
            "default": {
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "cost_class": "small",
                "capabilities": ["read"],
            }
        },
    )
    with runtime.store.read() as connection:
        source_revision = int(
            connection.execute(
                "SELECT version FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()[0]
        )
    return runtime, root, source_revision


def test_c2_r1a_commits_one_separate_role_null_carrier_atomically(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    before_event_ids = {event.event_id for event in runtime.events.list_events()}

    outcome = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )

    assert outcome.carrier_disposition == "created"
    assert outcome.mutation_disposition == "CREATED_THIS_CALL"
    assert outcome.fresh_attempt_lease is not None
    carrier = runtime.jobs.get_job(outcome.carrier_job_id)
    assert carrier is not None
    assert carrier.job_id != source_root.job_id
    assert carrier.parent_job_id is None
    assert carrier.root_job_id == carrier.job_id
    assert carrier.depth == 0
    assert carrier.owner_seat == "ceo"
    assert carrier.escalation_target == "ceo"
    assert carrier.orchestration_role is None
    assert carrier.orchestration_provenance is None
    assert carrier.orchestration_provenance_digest is None
    assert carrier.plan_attempt_id is None
    assert carrier.plan_digest is None
    assert carrier.plan_step_id is None
    assert carrier.repair_round is None
    assert carrier.supersedes_job_id is None
    assert carrier.requested_authorities == ["READ"]
    assert carrier.allowed_write_paths == []
    assert carrier.validation_commands == []
    assert carrier.attempt_limit == 1
    assert carrier.current_attempt_id == outcome.carrier_attempt_id
    assert carrier.assigned_worker_id == "c2-codex-read"
    assert carrier.assigned_quota_class == "default"

    attempt = outcome.fresh_attempt_lease.attempt
    assert attempt.attempt_id == outcome.carrier_attempt_id
    assert attempt.effective_grant is None
    assert attempt.effective_grant_digest is None
    assert attempt.placement_snapshot is None
    assert attempt.placement_snapshot_digest is None
    assert attempt.execution_principal_snapshot is None
    assert attempt.execution_principal_snapshot_digest is None

    carrier_events = runtime.events.list_events(job_id=carrier.job_id)
    created_events = [
        event for event in carrier_events if event.event_type == "JOB_CREATED"
    ]
    claim_events = [
        event for event in carrier_events if event.event_type == "JOB_CLAIMED"
    ]
    assert len(created_events) == 1
    assert len(claim_events) == 1
    creation_provenance = created_events[0].payload["provenance"]
    assert creation_provenance == {
        "schema_version": "mastermind.sol_session_carrier/v1",
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": outcome.commitment_event.payload[
            "target_definition_fingerprint"
        ],
        "carrier_generation": 1,
        "carrier_job_created_command_id": created_events[0].command_id,
    }
    claim = claim_events[0].payload["carrier_claim"]
    assert set(claim) == {
        "schema_version",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
        "carrier_job_created_command_id",
        "carrier_job_id",
        "carrier_attempt_id",
        "carrier_disposition",
        "effective_grant",
        "effective_grant_digest",
        "placement_snapshot",
        "placement_snapshot_digest",
        "carrier_authority_fingerprint",
    }
    assert claim["schema_version"] == "mastermind.sol_session_carrier_claim/v1"
    assert claim["carrier_job_id"] == carrier.job_id
    assert claim["carrier_attempt_id"] == attempt.attempt_id
    assert claim["carrier_disposition"] == "created"
    assert claim["effective_grant"] == {
        "schema_version": "mastermind.executive_effective_grant/v1",
        "authorities": ["READ"],
        "write_paths": [],
        "validation_argv": [],
        "policy_sha": carrier.authority_policy_hash,
        "job_id": carrier.job_id,
        "role": None,
    }
    assert claim["placement_snapshot"] == {
        "schema_version": "mastermind.executive_placement_snapshot/v1",
        "worker_id": "c2-codex-read",
        "quota_class": "default",
        "provider": "codex",
        "account_label": "c2-primary",
        "observed_at_ms": claim["placement_snapshot"]["observed_at_ms"],
    }
    assert (
        claim["placement_snapshot_digest"]
        == outcome.commitment_event.payload["committed_placement_snapshot_digest"]
    )

    source_after = runtime.jobs.get_job(source_root.job_id)
    assert source_after is not None
    assert source_after.current_attempt_id is None
    assert source_after.assigned_worker_id is None
    assert source_after.assigned_quota_class is None
    assert source_after.status == JobStatus.QUEUED

    root_events = [
        event
        for event in runtime.events.list_events(job_id=source_root.job_id)
        if event.event_type == "CAPACITY_PLACEMENT_COMMITTED"
    ]
    assert root_events == [outcome.commitment_event]
    event_delta = [
        event
        for event in runtime.events.list_events()
        if event.event_id not in before_event_ids
    ]
    assert [
        (
            event.event_type,
            event.actor,
            event.job_id,
            event.attempt_id,
            event.worker_id,
            event.quota_class,
        )
        for event in event_delta
    ] == [
        ("JOB_CREATED", "operator", carrier.job_id, None, None, None),
        (
            "JOB_CLAIMED",
            "operator",
            carrier.job_id,
            attempt.attempt_id,
            attempt.worker_id,
            attempt.quota_class,
        ),
        (
            "CAPACITY_PLACEMENT_COMMITTED",
            "operator",
            source_root.job_id,
            None,
            None,
            None,
        ),
    ]
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM harness_session_epochs WHERE attempt_id=?",
                (attempt.attempt_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                """
                SELECT COUNT(*) FROM process_generations
                WHERE session_epoch_id IN (
                  SELECT session_epoch_id FROM harness_session_epochs
                  WHERE attempt_id=?
                )
                """,
                (attempt.attempt_id,),
            ).fetchone()[0]
            == 0
        )
    lease_token = outcome.fresh_attempt_lease.lease_token
    assert lease_token not in repr(outcome)
    assert lease_token not in json.dumps(outcome.to_dict(), sort_keys=True)
    assert lease_token not in json.dumps(
        outcome.fresh_attempt_lease.to_dict(), sort_keys=True
    )


def test_c2_r1a_private_carrier_admission_does_not_widen_public_apis(tmp_path):
    runtime = _runtime(tmp_path)
    carrier_provenance = {
        "schema_version": "mastermind.sol_session_carrier/v1",
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": "a" * 64,
        "carrier_generation": 1,
        "carrier_job_created_command_id": "SOL-CARRIER-" + "b" * 32,
    }

    with pytest.raises(StateConflict, match="typed executive provenance"):
        runtime.jobs.create_job(
            "Public callers cannot mint an alias carrier",
            owner_seat="ceo",
            escalation_target="ceo",
            attempt_limit=1,
            requested_authorities=["READ"],
            provenance=carrier_provenance,
            command_id=carrier_provenance["carrier_job_created_command_id"],
        )

    ordinary = runtime.jobs.create_job("Ordinary role-null work")
    with pytest.raises(StateConflict, match="command-bound claim requires"):
        runtime.attempts.claim_job(
            ordinary.job_id,
            command_id="SOL-CARRIER-CLAIM-" + "c" * 32,
        )
    assert runtime.jobs.get_job(ordinary.job_id).status == JobStatus.QUEUED
    assert runtime.attempts.list_attempts(ordinary.job_id) == []


def _c2_durable_state(runtime):
    with runtime.store.read() as connection:
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in (
                "workers",
                "worker_quota_classes",
                "jobs",
                "attempts",
                "events",
            )
        }


def test_c2_r1a_replay_and_current_read_validate_causal_postconditions_without_c1(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    assert runtime.current_capacity_commitment(source_root.job_id) is None
    fresh = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    runtime.workers.register_worker(
        "c2-unrelated-candidate",
        provider="codex",
        account_label="c2-secondary",
        worker_type="codex",
        capabilities=["read"],
    )
    before_replay = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("causal replay/read must not rerun pre-effect C1")

    def claim_must_not_run(*_args, **_kwargs):
        raise AssertionError("causal replay/read must not reacquire a lease")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    monkeypatch.setattr(
        executive_runtime.AttemptRegistry,
        "_claim_job_in_transaction",
        claim_must_not_run,
    )
    replay = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )

    assert replay.commitment_event == fresh.commitment_event
    assert replay.carrier_job_id == fresh.carrier_job_id
    assert replay.carrier_attempt_id == fresh.carrier_attempt_id
    assert replay.carrier_disposition == "created"
    assert replay.mutation_disposition == "REPLAYED_EXISTING"
    assert replay.fresh_attempt_lease is None
    assert _c2_durable_state(runtime) == before_replay

    restarted_runtime = Runtime.at(tmp_path)
    restarted_replay = restarted_runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    assert restarted_replay.commitment_event == fresh.commitment_event
    assert restarted_replay.carrier_job_id == fresh.carrier_job_id
    assert restarted_replay.carrier_attempt_id == fresh.carrier_attempt_id
    assert restarted_replay.mutation_disposition == "REPLAYED_EXISTING"
    assert restarted_replay.fresh_attempt_lease is None
    assert _c2_durable_state(restarted_runtime) == before_replay

    standalone = runtime.current_capacity_commitment(source_root.job_id)
    with runtime.store.read() as connection:
        passed_connection = runtime.current_capacity_commitment(
            source_root.job_id,
            connection=connection,
        )
    assert standalone == passed_connection
    assert standalone is not None
    assert standalone.to_dict() == {
        "source_root_job_id": source_root.job_id,
        "source_job_created_command_id": fresh.commitment_event.payload[
            "source_job_created_command_id"
        ],
        "source_authority_fingerprint": fresh.commitment_event.payload[
            "source_authority_fingerprint"
        ],
        "commitment_command_id": fresh.commitment_event.command_id,
        "command_fingerprint": fresh.commitment_event.payload["command_fingerprint"],
        "commitment_evidence_digest": fresh.commitment_event.payload[
            "commitment_evidence_digest"
        ],
        "responsibility_ref": "WS:C2_R1A",
        "placement_mode": "new_session_materialization",
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": fresh.commitment_event.payload[
            "target_definition_fingerprint"
        ],
        "carrier_generation": 1,
        "carrier_job_id": fresh.carrier_job_id,
        "carrier_job_created_command_id": fresh.commitment_event.payload[
            "carrier_job_created_command_id"
        ],
        "carrier_authority_fingerprint": fresh.commitment_event.payload[
            "carrier_authority_fingerprint"
        ],
        "carrier_disposition": "created",
        "committed_carrier_attempt_id": fresh.carrier_attempt_id,
        "selected_worker_id": "c2-codex-read",
        "selected_quota_class": "default",
        "committed_placement_snapshot_digest": fresh.commitment_event.payload[
            "committed_placement_snapshot_digest"
        ],
    }
    assert fresh.fresh_attempt_lease.lease_token not in json.dumps(
        standalone.to_dict(), sort_keys=True
    )
    assert _c2_durable_state(runtime) == before_replay


@pytest.mark.parametrize(
    "phase",
    [
        "after_carrier_job_created",
        "after_quota_cas_and_fence",
        "after_carrier_attempt_insert",
        "after_carrier_job_transition",
        "after_carrier_job_claimed",
        "before_capacity_placement_committed",
    ],
)
def test_c2_r1a_every_intermediate_failure_rolls_back_the_complete_vertical(
    tmp_path, monkeypatch, phase
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    before = _c2_durable_state(runtime)

    def fail_at_checkpoint(observed):
        if observed == phase:
            raise RuntimeError(f"injected C2 failure at {phase}")

    monkeypatch.setattr(executive_runtime, "_C2_R1A_TEST_HOOK", fail_at_checkpoint)
    with pytest.raises(RuntimeError, match="injected C2 failure"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )

    assert _c2_durable_state(runtime) == before
    assert runtime.current_capacity_commitment(source_root.job_id) is None
    quota = runtime.workers.get_quota_class("c2-codex-read", "default")
    assert quota is not None
    assert quota.status == WorkerStatus.AVAILABLE
    assert quota.active_attempt_id is None
    assert quota.fence_generation == 0


def test_c2_r1a_refuses_pre_handoff_before_selection_or_mutation(tmp_path, monkeypatch):
    import tests.test_executive_os_phase1fc as phase1fc

    runtime = _runtime(tmp_path)
    receipt = phase1fc.submit_intent(
        runtime,
        phase1fc._v2_intent(
            intent_id="CEO-C2-R1A-PRE-HANDOFF",
            workstream="WS:C2_PREHANDOFF",
        ),
    )
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    with runtime.store.read() as connection:
        revision = int(
            connection.execute(
                "SELECT version FROM jobs WHERE job_id=?", (root.job_id,)
            ).fetchone()[0]
        )
    before = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("pre-handoff refusal must precede C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="handoff"):
        runtime.commit_initial_capacity_placement(
            root.job_id,
            expected_source_root_revision=revision,
        )
    assert _c2_durable_state(runtime) == before
    assert runtime.current_capacity_commitment(root.job_id) is None


def test_c2_r1a_refuses_stale_source_revision_before_selection_or_mutation(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    before = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("stale-revision refusal must precede C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="EXPECTED_SOURCE_ROOT_REVISION_MISMATCH"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision + 1,
        )
    assert _c2_durable_state(runtime) == before


def test_c2_r1a_refuses_non_selected_and_reuse_results_with_zero_effect(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    runtime.workers.set_worker_status("c2-codex-read", WorkerStatus.OFFLINE)
    before_non_selected = _c2_durable_state(runtime)
    with pytest.raises(StateConflict, match="C2_PLACEMENT_NO_ELIGIBLE_CANDIDATE"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == before_non_selected

    runtime.workers.set_worker_status("c2-codex-read", WorkerStatus.AVAILABLE)
    original_select = executive_runtime.select_placement
    placement_mode = executive_runtime._capacity_selection_contract().PlacementMode

    def force_reuse(*, responsibility, demand, candidates, accepted_tie_breaker=None):
        reuse_demand = dataclasses.replace(
            demand,
            allowed_modes=frozenset({placement_mode.EXISTING_SESSION_REUSE}),
        )
        reuse_candidates = tuple(
            dataclasses.replace(
                candidate,
                mode=placement_mode.EXISTING_SESSION_REUSE,
                creation_surface_accessible=None,
                session_creation_allowed=None,
            )
            for candidate in candidates
        )
        return original_select(
            responsibility=responsibility,
            demand=reuse_demand,
            candidates=reuse_candidates,
            accepted_tie_breaker=accepted_tie_breaker,
        )

    monkeypatch.setattr(executive_runtime, "select_placement", force_reuse)
    before_reuse = _c2_durable_state(runtime)
    with pytest.raises(StateConflict, match="HELD_MAT_S1_CURRENT_WRITER_OWNER"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == before_reuse


def test_c2_r1a_revision_motion_preserves_stable_replay_but_stale_call_refuses(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    fresh = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET version=version+1,updated_at_ms=updated_at_ms+1 "
            "WHERE job_id=?",
            (source_root.job_id,),
        )
        current_revision = int(
            connection.execute(
                "SELECT version FROM jobs WHERE job_id=?", (source_root.job_id,)
            ).fetchone()[0]
        )
    assert current_revision == source_revision + 1
    after_revision_motion = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("revision-only causal replay must not rerun C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="EXPECTED_SOURCE_ROOT_REVISION_MISMATCH"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == after_revision_motion

    replay = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=current_revision,
    )
    assert replay.commitment_event == fresh.commitment_event
    assert replay.mutation_disposition == "REPLAYED_EXISTING"
    assert replay.fresh_attempt_lease is None
    assert runtime.current_capacity_commitment(source_root.job_id) is not None
    assert _c2_durable_state(runtime) == after_revision_motion


def test_c2_r1a_replay_refuses_current_quota_and_target_drift_without_mutation(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    runtime.workers.set_worker_status("c2-codex-read", WorkerStatus.OFFLINE)
    quota_drift = _c2_durable_state(runtime)
    with pytest.raises(StateConflict, match="C2_CARRIER_QUOTA_NOT_CURRENT"):
        runtime.current_capacity_commitment(source_root.job_id)
    with pytest.raises(StateConflict, match="C2_CARRIER_QUOTA_NOT_CURRENT"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == quota_drift

    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE worker_quota_classes SET status='BUSY' "
            "WHERE worker_id='c2-codex-read' AND quota_class='default'"
        )
        connection.execute(
            "UPDATE workers SET identity_status='ONLINE' "
            "WHERE worker_id='c2-codex-read'"
        )
    original_target = executive_runtime._capacity_target_definition

    def drifted_target():
        value = original_target()
        value["wake_transport"] = "changed-transport"
        return value

    monkeypatch.setattr(
        executive_runtime, "_capacity_target_definition", drifted_target
    )
    target_drift = _c2_durable_state(runtime)
    with pytest.raises(StateConflict, match="C2_COMMITMENT_EVENT_REPLAY_CONFLICT"):
        runtime.current_capacity_commitment(source_root.job_id)
    assert _c2_durable_state(runtime) == target_drift


def test_c2_r1a_expired_carrier_lease_is_not_current_or_replayable(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    fresh = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    with runtime.store.read() as connection:
        lease_expiry_ms = int(
            connection.execute(
                "SELECT lease_expires_at_ms FROM attempts WHERE attempt_id=?",
                (fresh.carrier_attempt_id,),
            ).fetchone()[0]
        )
    expired_runtime = Runtime.at(tmp_path, clock=MutableClock(lease_expiry_ms))
    expired_state = _c2_durable_state(expired_runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("expired commitment validation must precede C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="C2_CARRIER_LEASE_NOT_CURRENT"):
        expired_runtime.current_capacity_commitment(source_root.job_id)
    with pytest.raises(StateConflict, match="C2_CARRIER_LEASE_NOT_CURRENT"):
        expired_runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(expired_runtime) == expired_state


def test_c2_r1a_create_and_replay_sample_time_only_under_the_write_lock(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    locked_clock = WriteLockRequiredClock(
        runtime.store.path,
        runtime.store.now_ms(),
    )
    locked_runtime = Runtime.at(tmp_path, clock=locked_clock, lease_seconds=1)

    fresh = locked_runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    replay = locked_runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )

    assert fresh.mutation_disposition == "CREATED_THIS_CALL"
    assert fresh.fresh_attempt_lease is not None
    assert replay.commitment_event == fresh.commitment_event
    assert replay.mutation_disposition == "REPLAYED_EXISTING"
    assert replay.fresh_attempt_lease is None
    with locked_runtime.store.read() as connection:
        expiry = int(
            connection.execute(
                "SELECT lease_expires_at_ms FROM attempts WHERE attempt_id=?",
                (fresh.carrier_attempt_id,),
            ).fetchone()[0]
        )
    assert expiry > locked_clock.value


@pytest.mark.parametrize(
    "lease_mutation",
    [
        "lease_token=''",
        "lease_owner='not-capacity-c2-r1a'",
        "lease_expires_at_ms=lease_expires_at_ms+1000",
    ],
)
def test_c2_r1a_carrier_lease_identity_and_receipt_drift_fail_closed(
    tmp_path, monkeypatch, lease_mutation
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    fresh = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    with runtime.store.transaction() as connection:
        connection.execute(
            f"UPDATE attempts SET {lease_mutation} WHERE attempt_id=?",
            (fresh.carrier_attempt_id,),
        )
    drifted_state = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("invalid commitment validation must precede C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="C2_CARRIER_LEASE_NOT_CURRENT"):
        runtime.current_capacity_commitment(source_root.job_id)
    with pytest.raises(StateConflict, match="C2_CARRIER_LEASE_NOT_CURRENT"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == drifted_state


def test_c2_r1a_duplicate_root_commitment_is_conflict_never_latest_selection(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    fresh = runtime.commit_initial_capacity_placement(
        source_root.job_id,
        expected_source_root_revision=source_revision,
    )
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="job",
            aggregate_id=source_root.job_id,
            event_type="CAPACITY_PLACEMENT_COMMITTED",
            actor="operator",
            job_id=source_root.job_id,
            payload=fresh.commitment_event.payload,
            command_id="CAP-C2-DUPLICATE-ROOT-CANDIDATE",
        )
    conflicted = _c2_durable_state(runtime)
    with pytest.raises(StateConflict, match="C2_COMMITMENT_CARDINALITY_CONFLICT"):
        runtime.current_capacity_commitment(source_root.job_id)
    with pytest.raises(StateConflict, match="C2_COMMITMENT_CARDINALITY_CONFLICT"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == conflicted


def test_c2_r1a_misaddressed_prior_commitment_refuses_before_c1_or_carrier_effect(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="job",
            aggregate_id="JOB-WRONG-C2-AGGREGATE",
            event_type="CAPACITY_PLACEMENT_COMMITTED",
            actor="operator",
            job_id=source_root.job_id,
            payload={"source_root_job_id": source_root.job_id},
            command_id="CAP-C2-MISADDRESSED-CANDIDATE",
        )
    before = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("malformed prior commitment must precede C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="C2_COMMITMENT_EVENT_INVALID"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == before


@pytest.mark.parametrize(
    ("payload_kind", "expected_code"),
    [
        ("noncanonical", "C2_COMMITMENT_EVENT_INVALID"),
        ("missing_required_field", "C2_COMMITMENT_EVENT_INVALID"),
    ],
)
def test_c2_r1a_addressed_malformed_commitment_refuses_before_c1_or_claim(
    tmp_path, monkeypatch, payload_kind, expected_code
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    command_id = f"CAP-C2-ADDRESSED-MALFORMED-{payload_kind}"
    partial_payload = {
        "commitment_command_id": command_id,
        "source_root_job_id": source_root.job_id,
    }
    if payload_kind == "noncanonical":
        payload_json = json.dumps(partial_payload, indent=2, sort_keys=True)
    else:
        payload_json = json.dumps(
            partial_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
    with runtime.store.transaction() as connection:
        sequence = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) + 1
                FROM events WHERE aggregate_type='job' AND aggregate_id=?
                """,
                (source_root.job_id,),
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO events(
              aggregate_type,aggregate_id,sequence,event_type,command_id,actor,
              job_id,attempt_id,worker_id,quota_class,payload_json,created_at_ms
            ) VALUES('job',?,?,'CAPACITY_PLACEMENT_COMMITTED',?,'operator',
                     ?,NULL,NULL,NULL,?,1)
            """,
            (
                source_root.job_id,
                sequence,
                command_id,
                source_root.job_id,
                payload_json,
            ),
        )
    before = _c2_durable_state(runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("addressed malformed commitment must precede C1")

    def claim_must_not_run(*_args, **_kwargs):
        raise AssertionError("addressed malformed commitment must precede claim")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    monkeypatch.setattr(
        executive_runtime.AttemptRegistry,
        "_claim_job_in_transaction",
        claim_must_not_run,
    )
    with pytest.raises(StateConflict, match=expected_code):
        runtime.current_capacity_commitment(source_root.job_id)
    assert _c2_durable_state(runtime) == before
    with pytest.raises(StateConflict, match=expected_code):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == before


def test_c2_r1a_unavailable_lazy_contract_refuses_before_any_effect(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    before = _c2_durable_state(runtime)
    original_import_module = executive_runtime.importlib.import_module

    def missing_commitment_contract(name, *args, **kwargs):
        if name == "control_plane.executive_placement_commitment":
            raise ModuleNotFoundError("C2 contract is absent", name=name)
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr(
        executive_runtime.importlib,
        "import_module",
        missing_commitment_contract,
    )
    with pytest.raises(StateConflict, match="C2_COMMITMENT_CONTRACT_UNAVAILABLE"):
        runtime.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )
    assert _c2_durable_state(runtime) == before


def test_c2_r1a_same_root_contention_commits_one_effect_and_one_fresh_lease(
    tmp_path, monkeypatch
):
    runtime, source_root, source_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    peer = Runtime.at(tmp_path, busy_timeout_ms=15_000)
    barrier = Barrier(2)
    calls = []
    original_select = executive_runtime.select_placement

    def counted_select(**kwargs):
        calls.append(kwargs["responsibility"].root_job_id)
        return original_select(**kwargs)

    monkeypatch.setattr(executive_runtime, "select_placement", counted_select)

    def invoke(owner):
        barrier.wait()
        return owner.commit_initial_capacity_placement(
            source_root.job_id,
            expected_source_root_revision=source_revision,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, (runtime, peer)))

    assert sorted(item.mutation_disposition.value for item in outcomes) == [
        "CREATED_THIS_CALL",
        "REPLAYED_EXISTING",
    ]
    assert sum(item.fresh_attempt_lease is not None for item in outcomes) == 1
    assert len({item.commitment_event.event_id for item in outcomes}) == 1
    assert len({item.carrier_job_id for item in outcomes}) == 1
    assert len({item.carrier_attempt_id for item in outcomes}) == 1
    assert calls == [source_root.job_id]
    with runtime.store.read() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='CAPACITY_PLACEMENT_COMMITTED' "
                "AND job_id=?",
                (source_root.job_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='JOB_CREATED' "
                "AND json_extract(payload_json, '$.provenance.schema_version')="
                "'mastermind.sol_session_carrier/v1'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type='JOB_CLAIMED' "
                "AND json_extract(payload_json, '$.carrier_claim.schema_version')="
                "'mastermind.sol_session_carrier_claim/v1'"
            ).fetchone()[0]
            == 1
        )


def test_c2_r1a_second_root_refuses_existing_generation_one_carrier_before_c1(
    tmp_path, monkeypatch
):
    import tests.test_executive_os_phase1fc as phase1fc

    runtime, first_root, first_revision = _c2_r1a_ready_source(tmp_path, monkeypatch)
    first = runtime.commit_initial_capacity_placement(
        first_root.job_id,
        expected_source_root_revision=first_revision,
    )
    runtime.workers.set_worker_status("worker-a", WorkerStatus.AVAILABLE)
    runtime.workers.set_worker_status("worker-b", WorkerStatus.AVAILABLE)

    original_complete = phase1fc._complete_ohf_role

    def complete_with_distinct_commands(
        runtime_arg, dispatch, role_result, *, identity_seed
    ):
        return original_complete(
            runtime_arg,
            dispatch,
            role_result,
            identity_seed=identity_seed + 10_000,
        )

    monkeypatch.setattr(phase1fc, "_register", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(phase1fc, "_complete_ohf_role", complete_with_distinct_commands)
    second_runtime, cycle, dispatches, second_root, planner, work, work_seal = (
        phase1fc._cycle_through_completed_work(
            tmp_path,
            intent_id="CEO-C2-R1A-SECOND-ROOT",
            review_workers=["worker-b"],
        )
    )
    assert cycle.run_once(second_root.job_id).action == "REVIEW_CREATED"
    assert cycle.run_once(second_root.job_id).action == "DISPATCHED"
    review = dispatches[-1]
    work_job = second_runtime.jobs.get_job(work.attempt.job_id)
    assert work_job is not None and work_job.plan_digest is not None
    review_body = phase1fc._review_body(
        root_id=second_root.job_id,
        plan_attempt_id=planner.attempt.attempt_id,
        plan_digest=work_job.plan_digest,
        target_job_id=work.attempt.job_id,
        target_attempt_id=work.attempt.attempt_id,
        target_result_digest=work_seal["role_result_digest"],
        repair_round=0,
        verdict="approve",
    )
    phase1fc._complete_ohf_role(second_runtime, review, review_body, identity_seed=4901)
    assert cycle.run_once(second_root.job_id).action == "HANDOFF_CREATED"
    second_runtime.workers.set_worker_status("worker-a", WorkerStatus.OFFLINE)
    second_runtime.workers.set_worker_status("worker-b", WorkerStatus.OFFLINE)
    with second_runtime.store.read() as connection:
        second_revision = int(
            connection.execute(
                "SELECT version FROM jobs WHERE job_id=?", (second_root.job_id,)
            ).fetchone()[0]
        )
    before = _c2_durable_state(second_runtime)

    def selector_must_not_run(**_kwargs):
        raise AssertionError("an existing generation-one carrier precedes C1")

    monkeypatch.setattr(executive_runtime, "select_placement", selector_must_not_run)
    with pytest.raises(StateConflict, match="HELD_MAT_S1_CURRENT_WRITER_OWNER"):
        second_runtime.commit_initial_capacity_placement(
            second_root.job_id,
            expected_source_root_revision=second_revision,
        )
    assert _c2_durable_state(second_runtime) == before
    assert second_runtime.current_capacity_commitment(
        first_root.job_id
    ).carrier_job_id == (first.carrier_job_id)
    assert second_runtime.current_capacity_commitment(second_root.job_id) is None
