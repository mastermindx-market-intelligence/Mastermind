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

# M2 is deliberately absent from the production migration vector. Only this
# synthetic fixture changes the three coupled expectations, with real verifiers.
_M2_V4_VECTOR = executive_runtime._MIGRATIONS
_M2_V4_DIGEST = executive_runtime._NORMALIZED_V4_SCHEMA_DIGEST
_M2_CANDIDATE_DIGEST = 'cd6fe8982e5b8ca8ea40ffff1dee089b5ab0d395916e7384a1ff14b5748f0caf'
_M2_CANDIDATE_CHECKSUM = '9bee01a6ee1f129a9c6b6fb24f52012d2cb790c39057722c5a6867163055b3d8'


def _m2_inputs():
    from test_executive_physical_resources import _request, _policy, _observations
    return _request(), {'policy': _policy(), 'observations': _observations(),
                        'binding': {'origin': 'SYNTHETIC_TEST_ONLY', 'runtime': 'runtime-test'}}


@pytest.fixture
def m2_store(tmp_path, monkeypatch):
    import copy
    candidate = executive_runtime._PHYSICAL_RESOURCE_SCHEMA_CANDIDATE
    assert executive_runtime._migration_checksum(candidate) == _M2_CANDIDATE_CHECKSUM
    monkeypatch.setattr(executive_runtime, '_MIGRATIONS', _M2_V4_VECTOR + (
        (5, 'synthetic_m2_physical_resources', candidate),))
    monkeypatch.setattr(executive_runtime, 'SCHEMA_VERSION', 5)
    monkeypatch.setattr(executive_runtime, '_NORMALIZED_V4_SCHEMA_DIGEST', _M2_CANDIDATE_DIGEST)
    contexts = {}
    def admission(self, request, caller_context, *, connection=None, stage='entry'):
        context = contexts[str(self.store.path)]
        if callable(context.get('at_stage')):
            context['at_stage'](self, connection, stage)
        return copy.deepcopy({key: context[key] for key in ('policy', 'observations', 'binding')})
    monkeypatch.setattr(executive_runtime.ResourceBroker, '_physical_admission', admission)
    def create(name='one'):
        runtime = Runtime.at(tmp_path / name, clock=MutableClock(100), busy_timeout_ms=1000)
        with runtime.store.read() as connection:
            assert executive_runtime._normalized_schema_digest(connection) == _M2_CANDIDATE_DIGEST
        request, context = _m2_inputs()
        # Synthetic timing allowances include real filesystem/schema validation.
        context['policy']['waits'] = {'service_request_max_ms': 2000, 'database_lock_max_ms': 1000}
        context['policy']['freshness']['decision_to_effect_max_ms'] = 1000
        contexts[str(runtime.store.path)] = context
        # Existing-store opening must exercise the genuine version/name/checksum/digest checks.
        second = Runtime.at(tmp_path / name, clock=MutableClock(100), busy_timeout_ms=1000)
        return runtime, second, request, context
    return create


def _m2_rows(runtime):
    with runtime.store.read() as connection:
        return {table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('physical_resource_commitments', 'physical_resource_demands', 'events')}


def _m2_envelope(request, result, command, *, evidence=None):
    import copy
    reservation = copy.deepcopy(request); reservation['command_id'] = 'physical:' + command
    value = {'reservation': reservation, 'commitments': [
        {'commitment_id': row['commitment_id'], 'allocation_generation': row['allocation_generation'],
         'expected_revision': row['revision']}
        for row in result['receipt']['commitments']]}
    if evidence is not None:
        value['evidence'] = evidence
    return value


def _m2_reserve(runtime, request):
    return runtime.broker.reserve_physical(request, caller_context=None)


def test_m2_default_runtime_keeps_exact_v4_vector_and_has_no_candidate_tables(tmp_path):
    runtime = Runtime.at(tmp_path)
    assert executive_runtime.SCHEMA_VERSION == 4
    assert executive_runtime._MIGRATIONS == _M2_V4_VECTOR
    assert executive_runtime._NORMALIZED_V4_SCHEMA_DIGEST == _M2_V4_DIGEST
    with runtime.store.read() as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'physical_resource_%'").fetchall() == []
        assert connection.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 4


def test_m2_default_resource_entry_refuses_before_database_open(tmp_path):
    # Construction has already opened its temporary store. Resource entry must
    # still deny before touching its now-unavailable resource database path.
    runtime = Runtime.at(tmp_path)
    runtime.store.path = tmp_path / 'unavailable.sqlite3'
    runtime.store.create = False
    for method in ('reserve_physical', 'begin_physical', 'observe_physical', 'settle_physical', 'physical_status'):
        result = getattr(runtime.broker, method)({}, caller_context={'verified': True})
        assert result == {'admitted': False, 'code': 'CALLER_BINDING_UNAVAILABLE', 'fresh_begin': False}
        assert not runtime.store.path.exists()


def test_m2_candidate_schema_uses_same_store_and_existing_events_without_jobs(m2_store):
    runtime, _, request, _ = m2_store()
    result = _m2_reserve(runtime, request)
    assert result['admitted'] and not result['fresh_begin'], result
    with runtime.store.read() as connection:
        assert connection.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM attempts').fetchone()[0] == 0
        events = connection.execute('SELECT aggregate_type,job_id,attempt_id,worker_id FROM events').fetchall()
        assert [tuple(r) for r in events] == [('physical_resource_operation', None, None, None)]
        assert connection.execute('SELECT count(*) FROM physical_resource_demands').fetchone()[0] == 6
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert executive_runtime._normalized_schema_digest(connection) == _M2_CANDIDATE_DIGEST
    with runtime.store.transaction() as connection:
        connection.execute("UPDATE schema_migrations SET checksum='bad' WHERE version=5")
    with pytest.raises(PersistenceError):
        Runtime.at(runtime.store.root, clock=MutableClock(100))


def test_m2_same_operation_phase_new_command_reconciles_without_second_debit(m2_store):
    runtime, second, request, _ = m2_store()
    first = _m2_reserve(runtime, request)
    request['command_id'] = 'physical:reserve-again'
    second_result = _m2_reserve(second, request)
    assert second_result['admitted'], second_result
    assert second_result['receipt'] == first['receipt']
    assert second_result['fresh_begin'] is False
    rows = _m2_rows(runtime)
    assert len(rows['physical_resource_commitments']) == 1
    assert len(rows['physical_resource_demands']) == 6
    assert len(rows['events']) == 2
    assert _m2_reserve(second, request) == second_result


def test_m2_changed_owner_carrier_or_source_conflicts_with_existing_phase(m2_store):
    import copy
    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request); before = _m2_rows(runtime)
    for key in ('owner_id', 'carrier_id', 'source_binding'):
        changed = copy.deepcopy(request); changed['command_id'] = 'physical:changed-' + key
        if key == 'source_binding': changed[key]['commit_sha'] = 'd' * 40
        else: changed[key] += '-changed'
        assert _m2_reserve(runtime, changed)['code'] == 'PHASE_IDENTITY_CONFLICT'
        assert _m2_rows(runtime) == before


def test_m2_partial_existing_bundle_refuses_all_new_rows(m2_store):
    import copy
    runtime, _, request, _ = m2_store()
    _m2_reserve(runtime, request); before = _m2_rows(runtime)
    request['command_id'] = 'physical:partial'
    phase = copy.deepcopy(request['phases'][0]); phase['phase_key'] = 'second'
    request['phases'].append(phase)
    assert _m2_reserve(runtime, request)['code'] == 'PHASE_IDENTITY_CONFLICT'
    assert _m2_rows(runtime) == before


def test_m2_linked_reserve_is_atomic_at_every_header_demand_event_fault(m2_store):
    import copy
    stages = ['after_event'] + ['after_header:' + p for p in ('create', 'linked')]
    stages += [f'after_demand:{p}:{i}' for p in ('create', 'linked') for i in range(6)]
    for i, fault in enumerate(stages):
        runtime, _, request, context = m2_store(str(i))
        phase = copy.deepcopy(request['phases'][0]); phase['phase_key'] = 'linked'
        request['phases'].append(phase)
        before = _m2_rows(runtime)
        def fail(_broker, _connection, stage):
            if stage == fault: raise sqlite3.OperationalError('injected resource transaction fault')
        context['at_stage'] = fail
        with pytest.raises(PersistenceError): _m2_reserve(runtime, request)
        assert _m2_rows(runtime) == before


def test_m2_linked_begin_cas_is_atomic_at_every_phase_fault(m2_store):
    import copy
    for fault in ('after_event', 'after_header:create', 'after_header:linked'):
        runtime, _, request, context = m2_store(fault.replace(':', '-'))
        phase = copy.deepcopy(request['phases'][0]); phase['phase_key'] = 'linked'; request['phases'].append(phase)
        reserved = _m2_reserve(runtime, request); before = _m2_rows(runtime)
        def fail(_broker, _connection, stage):
            if stage == fault: raise sqlite3.OperationalError('injected linked CAS failure')
        context['at_stage'] = fail
        with pytest.raises(PersistenceError):
            runtime.broker.begin_physical(_m2_envelope(request, reserved, 'begin'), caller_context=None)
        assert _m2_rows(runtime) == before


def test_m2_stale_generation_revision_and_terminal_reopen_are_refused(m2_store):
    import copy
    runtime, _, request, _ = m2_store(); reserved = _m2_reserve(runtime, request)
    # A valid-schema but incomplete own reservation cannot borrow a foreign
    # operation's matching pool rows to pass BEGIN completeness.
    for corruption in ('missing', 'inflated', 'attributed', 'revision', 'peak', 'window', 'attribution'):
        damaged, _, _, _ = m2_store('own-' + corruption)
        with runtime.store.read() as source, damaged.store.transaction() as target:
            for table in ('events', 'physical_resource_commitments', 'physical_resource_demands'):
                columns = [row[1] for row in source.execute(f'PRAGMA table_info({table})')]
                for row in source.execute(f'SELECT * FROM {table}'):
                    values = list(row)
                    if table == 'physical_resource_demands' and row['capacity_pool_id'] == 'memory':
                        if corruption == 'missing': continue
                        field, value = {'inflated': ('remaining_charge', 21),
                                        'attributed': ('attributed_materialized_or_active', 1),
                                        'revision': ('observed_revision', 2),
                                        'peak': ('qualified_incremental_peak', 21),
                                        'window': ('window_binding_json', json.dumps({**json.loads(row['window_binding_json']), 'baseline_id': 'foreign-baseline'})),
                                        'attribution': ('attribution_json', '{"attribution_id":"foreign"}')}[corruption]
                        values[columns.index(field)] = value
                    placeholders = ','.join('?' for _ in columns)
                    target.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})", tuple(values))
        foreign = copy.deepcopy(request); foreign['operation_key'] = 'foreign'; foreign['command_id'] = 'physical:foreign'
        assert _m2_reserve(damaged, foreign)['admitted']
        before = _m2_rows(damaged)
        refused = damaged.broker.begin_physical(_m2_envelope(request, reserved, 'bad-own'), caller_context=None)
        assert refused['code'] == 'OWN_DEMAND_MISMATCH' and refused['fresh_begin'] is False
        assert _m2_rows(damaged) == before
    for field in ('allocation_generation', 'expected_revision'):
        stale = _m2_envelope(request, reserved, 'stale-' + field); stale['commitments'][0][field] += 1
        assert runtime.broker.begin_physical(stale, caller_context=None)['code'] == 'STALE_COMMITMENT'
    no_effect = {'terminal_effect_state': 'NO_EFFECT', 'positive_no_effect': True, 'pools': {}}
    settled = runtime.broker.settle_physical(_m2_envelope(request, reserved, 'abandon', evidence=no_effect), caller_context=None)
    assert settled['receipt']['commitments'][0]['state'] == 'ABANDONED_NO_EFFECT'
    before = _m2_rows(runtime)
    assert runtime.broker.begin_physical(_m2_envelope(request, settled, 'reopen'), caller_context=None)['code'] == 'TERMINAL_COMMITMENT'
    assert _m2_rows(runtime) == before
    with pytest.raises(StateConflict):
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE physical_resource_commitments SET state='RESERVED',revision=revision+1")


def test_m2_two_runtime_instances_contend_for_one_shared_pool(m2_store):
    import copy
    runtime, second, request, context = m2_store()
    context['observations']['pools']['external']['available'] = 60
    other = copy.deepcopy(request); other['operation_key'] = 'other'; other['command_id'] = 'physical:other'
    barrier = Barrier(2)
    def reserve(pair):
        barrier.wait(); return _m2_reserve(*pair)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, [(runtime, request), (second, other)]))
    assert sorted(r['code'] for r in results) == ['INSUFFICIENT_CAPACITY', 'RESERVED']
    assert len(_m2_rows(runtime)['physical_resource_commitments']) == 1
    # A later larger sample cannot convert the recorded refusal into a grant.
    context['observations']['pools']['external']['available'] = 100
    loser_index = next(i for i, value in enumerate(results) if not value['admitted'])
    loser_runtime, loser_request = [(runtime, request), (second, other)][loser_index]
    assert _m2_reserve(loser_runtime, loser_request)['code'] == 'INSUFFICIENT_CAPACITY'
    loser_request['command_id'] = 'physical:new-command-same-refusal'
    assert _m2_reserve(loser_runtime, loser_request)['code'] == 'INSUFFICIENT_CAPACITY'
    assert loser_runtime.broker.physical_status({'reservation': loser_request}, caller_context=None)['code'] == 'INSUFFICIENT_CAPACITY'


def test_m2_begin_rechecks_freshness_and_policy_after_write_lock(m2_store):
    for mutation in ('age', 'policy', 'deadline', 'commit_clock'):
        runtime, _, request, context = m2_store(mutation); reserved = _m2_reserve(runtime, request)
        runtime.store.clock = WriteLockRequiredClock(runtime.store.path, 100)
        if mutation == 'commit_clock':
            samples = []
            locked_clock = runtime.store.clock
            def crossing_clock():
                samples.append(True)
                return locked_clock() if len(samples) <= 2 else 1101
            runtime.store.clock = crossing_clock
        def move(_broker, _connection, stage):
            if stage == 'locked':
                if mutation == 'age': context['observations']['observed_at_ms'] = 0
                elif mutation == 'policy': context['policy']['policy_revision'] = 'moved'
            if stage == 'before_commit' and mutation == 'deadline': runtime.store.clock.value = 1101
        context['at_stage'] = move
        result = runtime.broker.begin_physical(_m2_envelope(request, reserved, 'begin'), caller_context=None)
        assert result['fresh_begin'] is False, result
        assert result['admitted'] is (mutation == 'commit_clock')
        status = runtime.broker.physical_status({'reservation': request}, caller_context=None)
        assert status['receipt']['commitments'][0]['state'] == ('EFFECT_MAY_HAVE_BEGUN' if mutation == 'commit_clock' else 'RESERVED')


def _m2_timed_call(monkeypatch, samples, call, *args, **kwargs):
    """Inject only this synchronous broker call's explicit monotonic samples.

    SQLite/transaction/schema work stays real; unrelated clock callers retain
    real time, and the process clock function is restored after every call.
    """
    import sys
    import time
    actual_monotonic = time.monotonic
    broker_code = executive_runtime.ResourceBroker._physical_command.__code__
    consumed = []

    def monotonic():
        if sys._getframe(1).f_code is not broker_code:
            return actual_monotonic()
        assert len(consumed) < len(samples), "extra broker monotonic sample"
        value = samples[len(consumed)]
        consumed.append(value)
        return value

    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(time, "monotonic", monotonic)
            return call(*args, **kwargs)
    finally:
        assert time.monotonic is actual_monotonic
        assert consumed == list(samples), "missing broker monotonic sample"


@pytest.mark.parametrize("samples,message", [
    ((), "extra broker monotonic sample"),
    ((0.0, 0.1), "missing broker monotonic sample"),
])
def test_m2_timing_input_rejects_extra_or_missing_samples(m2_store, monkeypatch, samples, message):
    runtime, _, request, _ = m2_store()
    # Status is a real read transaction with exactly its started sample.
    with pytest.raises(AssertionError, match=message):
        _m2_timed_call(monkeypatch, samples, runtime.broker.physical_status,
                       {'reservation': request}, caller_context=None)


@pytest.mark.parametrize("samples,code,admitted,fresh", [
    ((0.0, 0.1, 1.001), "DECISION_DEADLINE_EXPIRED", False, False),
    ((0.0, 0.1, 0.5, 1.001), "BEGIN_COMMITTED_DEADLINE_EXPIRED", True, False),
    ((0.0, 0.1, 1.0, 1.0), "BEGUN", True, True),
], ids=["precommit-1001ms", "postcommit-1001ms", "exact-1000ms"])
def test_m2_monotonic_deadline_real_transaction_boundaries(m2_store, monkeypatch, samples, code, admitted, fresh):
    runtime, second, request, context = m2_store()
    assert context['policy']['freshness']['decision_to_effect_max_ms'] == 1000
    reserved = _m2_timed_call(monkeypatch, (0.0, 0.1), _m2_reserve, runtime, request)
    assert reserved['admitted']
    before = _m2_rows(runtime)
    envelope = _m2_envelope(request, reserved, 'deadline-boundary')
    result = _m2_timed_call(monkeypatch, samples, runtime.broker.begin_physical,
                            envelope, caller_context=None)
    assert result['code'] == code and result['admitted'] is admitted
    assert result['fresh_begin'] is fresh
    if not admitted:
        assert _m2_rows(runtime) == before  # event/header/demands all rolled back
    else:
        after = _m2_rows(runtime)
        assert after != before
        with runtime.store.read() as connection:
            states = [row[0] for row in connection.execute('SELECT state FROM physical_resource_commitments')]
            events = [json.loads(row[0]) for row in connection.execute(
                "SELECT payload_json FROM events WHERE event_type='PHYSICAL_RESOURCE_BEGIN'")]
        assert states == ['EFFECT_MAY_HAVE_BEGUN']
        assert len(events) == 1 and events[0]['receipt'] == result['receipt']
        assert 'fresh_begin' not in events[0]
        assert ('start_deadline_ms' in result) is fresh
        if fresh:
            assert result['start_deadline_ms'] == 1100
        replay = _m2_timed_call(monkeypatch, (0.0, 0.1), second.broker.begin_physical,
                               envelope, caller_context=None)
        assert replay['admitted'] and replay['fresh_begin'] is False
        assert replay['receipt'] == result['receipt']
        assert _m2_rows(runtime) == after  # same-command replay adds no BEGIN


def test_m2_begin_replay_and_new_command_never_return_fresh_grant(m2_store, monkeypatch):
    import copy
    # Exercise real SQLite query order independently of insertion/phase order.
    # A20 + B10 uses exactly the available40 minus protected10 memory boundary.
    for co_start in (False, True):
        for reverse_insertion in (False, True):
            for reverse_rows in (False, True):
                name = f'{co_start}-{reverse_insertion}-{reverse_rows}'
                runtime, second, request, context = m2_store(name)
                small = copy.deepcopy(request)
                small['operation_key'] = 'smaller'; small['command_id'] = 'physical:smaller'
                small_phase = small['phases'][0]
                small_phase['phase_key'] = 'smaller'
                small_phase['profile'] = 'SYNTHETIC_SMALL_CREATE'
                small_phase['demands'][0]['qualified_incremental_peak'] = 10
                profile = copy.deepcopy(context['policy']['profiles'][0])
                profile['profile'] = small_phase['profile']
                profile['qualified_demands'] = copy.deepcopy(small_phase['demands'])
                context['policy']['profiles'].append(profile)
                context['observations']['pools']['memory']['available'] = 40
                def row_order(_broker, connection, stage):
                    if stage == 'locked':
                        connection.execute(f'PRAGMA reverse_unordered_selects={int(reverse_rows)}')
                context['at_stage'] = row_order
                if co_start:
                    request['phases'].append(small_phase)
                    if reverse_insertion: request['phases'].reverse()
                    reserved = _m2_timed_call(monkeypatch, (0.0, 0.1), _m2_reserve, runtime, request)
                else:
                    pairs = [(runtime, request), (second, small)]
                    if reverse_insertion: pairs.reverse()
                    results = {value['operation_key']: _m2_timed_call(monkeypatch, (0.0, 0.1), _m2_reserve, instance, value) for instance, value in pairs}
                    assert all(result['admitted'] for result in results.values()), results
                    reserved = results[request['operation_key']]
                assert reserved['admitted'], reserved
                envelope = _m2_envelope(request, reserved, 'begin')
                # started, locked, precommit, postcommit: all inside 1000ms.
                first = _m2_timed_call(monkeypatch, (0.0, 0.1, 0.2, 0.3), runtime.broker.begin_physical, envelope, caller_context=None)
                assert first['fresh_begin'] is True, (name, first)
                assert first['start_deadline_ms'] == 1100
                with runtime.store.read() as connection:
                    for row in connection.execute('SELECT payload_json FROM events'):
                        payload = json.loads(row[0])
                        assert 'fresh_begin' not in payload and 'fresh_begin' not in payload['receipt']
                replay = _m2_timed_call(monkeypatch, (0.0, 0.1), second.broker.begin_physical, envelope, caller_context=None)
                assert replay['receipt'] == first['receipt'] and replay['fresh_begin'] is False
                envelope['reservation']['command_id'] = 'physical:new-begin-command'
                reconciled = _m2_timed_call(monkeypatch, (0.0, 0.1), second.broker.begin_physical, envelope, caller_context=None)
                assert reconciled['receipt'] == first['receipt'] and reconciled['fresh_begin'] is False

                # A different store starts with the same pristine reservations,
                # then its current observation crosses the protected boundary.
                limited, _, limited_request, limited_context = m2_store(name + '-limited')
                limited_context['policy'] = copy.deepcopy(context['policy'])
                limited_context['at_stage'] = row_order
                limited_request = copy.deepcopy(request)
                limit_reserved = _m2_timed_call(monkeypatch, (0.0, 0.1), _m2_reserve, limited, limited_request)
                assert limit_reserved['admitted'], limit_reserved
                if not co_start: assert _m2_timed_call(monkeypatch, (0.0, 0.1), _m2_reserve, limited, small)['admitted']
                limited_context['observations']['pools']['memory']['available'] = 39
                before = _m2_rows(limited)
                refused = _m2_timed_call(monkeypatch, (0.0, 0.1), limited.broker.begin_physical, _m2_envelope(limited_request, limit_reserved, 'capacity'), caller_context=None)
                assert refused['code'] == 'INSUFFICIENT_CAPACITY' and refused['fresh_begin'] is False, refused
                assert _m2_rows(limited) == before


def test_m2_lost_begin_reply_reconciles_with_zero_effect_stub_calls(m2_store):
    runtime, second, request, _ = m2_store(); reserved = _m2_reserve(runtime, request)
    envelope = _m2_envelope(request, reserved, 'lost-reply')
    runtime.broker.begin_physical(envelope, caller_context=None)  # transport discards first reply
    effects = []
    recovered = second.broker.begin_physical(envelope, caller_context=None)
    if recovered['fresh_begin']: effects.append('launch')
    status = second.broker.physical_status({'reservation': request}, caller_context=None)
    if status['fresh_begin']: effects.append('launch')
    assert effects == [] and status['receipt']['commitments'][0]['state'] == 'EFFECT_MAY_HAVE_BEGUN'


def test_m2_overrun_and_unknown_settlement_retain_required_charge(m2_store):
    runtime, _, request, _ = m2_store(); reserved = _m2_reserve(runtime, request)
    begun = runtime.broker.begin_physical(_m2_envelope(request, reserved, 'begin'), caller_context=None)
    observed = runtime.broker.observe_physical(_m2_envelope(request, begun, 'observe', evidence={
        'usage': {'memory': 150}, 'attribution_id': 'observed-memory', 'baseline_id': 'base-1'}), caller_context=None)
    row = observed['receipt']['commitments'][0]
    assert row['state'] == 'RECONCILIATION_REQUIRED'
    assert next(d for d in row['demands'] if d['capacity_pool_id'] == 'memory')['remaining_charge'] == 150
    unknown = runtime.broker.settle_physical(_m2_envelope(request, observed, 'unknown', evidence={
        'terminal_effect_state': 'UNKNOWN', 'pools': {}}), caller_context=None)
    assert unknown['receipt']['commitments'][0]['demands'] == row['demands']
    assert unknown['fresh_begin'] is False
    with pytest.raises(StateConflict):
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE physical_resource_demands SET remaining_charge=0,attributed_materialized_or_active=0,attribution_json='{}'")
    with pytest.raises(StateConflict):
        with runtime.store.transaction() as connection:
            connection.execute('UPDATE physical_resource_commitments SET last_observation_event_id=decision_event_id,revision=revision+1')


def test_m2_creator_settlement_does_not_release_linked_build(m2_store):
    import copy
    runtime, _, request, _ = m2_store(); creator = _m2_reserve(runtime, request)
    linked = copy.deepcopy(request); linked['command_id'] = 'physical:linked'; linked['phases'][0]['phase_key'] = 'later-build'
    build = _m2_reserve(runtime, linked)
    abandoned = runtime.broker.settle_physical(_m2_envelope(request, creator, 'creator-no-effect', evidence={
        'terminal_effect_state': 'NO_EFFECT', 'positive_no_effect': True, 'pools': {}}), caller_context=None)
    assert abandoned['receipt']['commitments'][0]['state'] == 'ABANDONED_NO_EFFECT'
    status = runtime.broker.physical_status({'reservation': linked}, caller_context=None)
    assert status['receipt']['commitments'] == build['receipt']['commitments']
    assert sum(d['remaining_charge'] for d in status['receipt']['commitments'][0]['demands']) == 116


def test_m2_each_resource_read_and_write_requires_connection_verifier(m2_store):
    # Record SQLite authorization calls, not a mocked verifier. A semantic
    # resource read before PRAGMA database_list is an observable guard omission.
    for method in ('reserve_physical', 'begin_physical', 'observe_physical', 'settle_physical', 'physical_status'):
        runtime, _, request, context = m2_store(method); reserved = _m2_reserve(runtime, request)
        events = []; connections = set()
        def trace(_broker, connection, _stage):
            if connection is not None:
                connections.add(id(connection))
                def authorize(action, arg1, arg2, _db, _trigger):
                    if action == sqlite3.SQLITE_PRAGMA and arg1 == 'database_list': events.append('guard')
                    if action == sqlite3.SQLITE_READ and str(arg1).startswith('physical_resource_'):
                        assert 'guard' in events, 'semantic resource query preceded canonical identity guard'
                    return sqlite3.SQLITE_OK
                connection.set_authorizer(authorize)
        context['at_stage'] = trace
        evidence = {'usage': {}, 'attribution_id': None, 'baseline_id': 'base-1'} if method == 'observe_physical' else {'terminal_effect_state': 'UNKNOWN', 'pools': {}}
        value = request if method == 'reserve_physical' else (
            {'reservation': request} if method == 'physical_status' else _m2_envelope(request, reserved, 'verify-' + method,
                evidence=evidence if method in ('observe_physical', 'settle_physical') else None))
        result = getattr(runtime.broker, method)(value, caller_context=None)
        assert result['admitted'] and events.count('guard') >= 2
        foreign, _, _, _ = m2_store(method + '-foreign')
        # An admission resolver must never receive a foreign, unverified handle.
        queried = []
        def admission_query(_broker, connection, _stage):
            if connection is not None:
                queried.append(connection.execute('SELECT count(*) FROM physical_resource_commitments').fetchone()[0])
        context['at_stage'] = admission_query
        with foreign.store.read() as other:
            with pytest.raises(StateConflict): runtime.broker._physical_guard(value, None, other, 'probe')
        assert queried == []
        original_store = runtime.broker.store
        def swap(broker, connection, stage):
            if connection is not None and stage == 'locked': broker.store = foreign.store
        context['at_stage'] = swap
        try:
            with pytest.raises(StateConflict): getattr(runtime.broker, method)(value, caller_context=None)
        finally:
            runtime.broker.store = original_store


def test_m2_policy_or_connection_change_rolls_back_before_commit(m2_store):
    for mutation in ('policy', 'connection'):
        runtime, _, request, context = m2_store(mutation); before = _m2_rows(runtime)
        def moved(broker, connection, stage):
            if stage == 'before_commit':
                if mutation == 'policy': context['binding']['runtime'] = 'moved'
                else:
                    connection.execute('ROLLBACK')
                    broker.store._assert_owned_snapshot_connection(connection)
        context['at_stage'] = moved
        if mutation == 'connection':
            with pytest.raises(StateConflict): _m2_reserve(runtime, request)
        else:
            assert _m2_reserve(runtime, request)['code'] == 'ADMISSION_MOVED'
        assert _m2_rows(runtime) == before


def test_m2_no_test_configuration_or_schema_flag_arms_production(m2_store, monkeypatch):
    runtime, _, request, _ = m2_store()
    # Undo only the admission replacement; installed synthetic tables are still present.
    monkeypatch.setattr(executive_runtime.ResourceBroker, '_physical_admission', _M2_PRODUCTION_ADMISSION)
    assert _m2_reserve(runtime, request)['code'] == 'CALLER_BINDING_UNAVAILABLE'
    assert _m2_rows(runtime)['physical_resource_commitments'] == []


_M2_PRODUCTION_ADMISSION = getattr(executive_runtime.ResourceBroker, '_physical_admission', None)


def _bound_exclusive_witness(path):
    witness = sqlite3.connect(str(path), timeout=0, isolation_level=None)
    try:
        try:
            witness.execute("BEGIN EXCLUSIVE").close()
        except sqlite3.OperationalError as exc:
            assert exc.sqlite_errorcode == sqlite3.SQLITE_BUSY
            return False
        witness.rollback()
        return True
    finally:
        witness.close()


@pytest.mark.parametrize("route", ["shortcut", "cursor"])
@pytest.mark.parametrize("finish", ["retained", "exhausted", "closed"])
def test_bound_managed_cursors_drain_before_namespace_release(tmp_path, route, finish):
    writer, provider, binding = _bound_fixture(tmp_path)
    writer.jobs.create_job("SECOND A")
    writer.jobs.create_job("THIRD A")
    setup = sqlite3.connect(writer.store.path, isolation_level=None)
    try:
        setup.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        assert setup.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    finally:
        setup.close()
    assert _bound_exclusive_witness(writer.store.path)
    at_release, held = [], []
    provider.after_close = lambda: at_release.append(_bound_exclusive_witness(writer.store.path))

    def reader(runtime):
        with runtime.store.read() as connection:
            for _ in range(2):
                cursor = connection.execute("SELECT objective FROM jobs ORDER BY rowid") if route == "shortcut" else connection.cursor().execute("SELECT objective FROM jobs ORDER BY rowid")
                held.append(cursor)
                assert cursor.fetchmany(1)[0][0] == "APPROVED DATABASE A"
                assert not _bound_exclusive_witness(writer.store.path)
                if finish == "exhausted":
                    assert len(cursor.fetchall()) == 2
                elif finish == "closed":
                    cursor.close()
        # Cursors remain referenced in this callback and outside it, but the
        # returned value is ordinary data. Physical drain must already be true.
        assert _bound_exclusive_witness(writer.store.path)
        return ["APPROVED DATABASE A"]

    assert Runtime.read_bound(tmp_path, binding=binding, reader=reader) == ["APPROVED DATABASE A"]
    assert at_release == [True]
    for cursor in held:
        with pytest.raises((PersistenceError, sqlite3.ProgrammingError)):
            cursor.fetchone()


# Bound reads exercise the real store. This cooperating namespace is ONLY a
# synthetic contract witness; it is not an installed namespace capability.
def _bound_fixture(tmp_path):
    from contextlib import contextmanager
    import threading

    assert hasattr(executive_runtime, "RuntimeNamespaceCapability"), "bound-read API missing"

    class Namespace(executive_runtime.RuntimeNamespaceCapability):
        def __init__(self):
            self.lock = threading.Lock()
            self.valid = True
            self.entries = 0
            self.exits = 0
            self.after_close = None

        @contextmanager
        def namespace(self, database_path):
            assert self.lock.acquire(timeout=1)
            self.entries += 1
            try:
                yield
            finally:
                self.exits += 1
                self.lock.release()
                if self.after_close:
                    self.after_close()

        def validate(self, database_path):
            if not self.valid:
                raise ValueError("namespace revoked")

    writer = _runtime(tmp_path)
    writer.jobs.create_job("APPROVED DATABASE A")
    provider = Namespace()
    binding = executive_runtime.RuntimeReadBinding(provider)
    return writer, provider, binding


def _bound_titles(root, binding):
    return Runtime.read_bound(
        root, binding=binding,
        reader=lambda runtime: [job.objective for job in runtime.jobs.list_jobs()],
    )


def test_bound_read_real_a_and_namespace_excludes_same_schema_b(tmp_path, monkeypatch):
    writer, provider, binding = _bound_fixture(tmp_path / "a")
    other = _runtime(tmp_path / "b")
    other.jobs.create_job("UNAPPROVED DATABASE B")
    original = sqlite3.connect
    attempts = []

    def connect(*args, **kwargs):
        # Independent competing namespace participant cannot replace A while
        # SQLite resolves/opens it. It would swap B if exclusion were absent.
        def substitute():
            acquired = provider.lock.acquire(blocking=False)
            attempts.append(acquired)
            if acquired:
                try:
                    writer.store.path.write_bytes(other.store.path.read_bytes())
                finally:
                    provider.lock.release()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(substitute).result(timeout=2)
        return original(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    assert _bound_titles(tmp_path / "a", binding) == ["APPROVED DATABASE A"]
    assert attempts == [False]
    assert provider.entries == provider.exits == 1


def test_bound_read_missing_capability_refuses_before_sqlite(tmp_path, monkeypatch):
    assert hasattr(executive_runtime, "RuntimeReadBinding"), "bound-read API missing"
    calls = []
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: calls.append(a))
    with pytest.raises(PersistenceError):
        Runtime.read_bound(tmp_path, binding=None, reader=lambda runtime: [])
    with pytest.raises(PersistenceError):
        executive_runtime.RuntimeReadBinding(None)
    assert calls == []
    assert not (tmp_path / "data").exists()


def test_bound_read_exact_schema_on_every_actual_connection(tmp_path):
    writer, provider, binding = _bound_fixture(tmp_path)
    assert _bound_titles(tmp_path, binding) == ["APPROVED DATABASE A"]
    with sqlite3.connect(writer.store.path) as connection:
        connection.execute("CREATE INDEX unapproved_shape ON jobs(objective)")
    with pytest.raises(PersistenceError, match="exact reviewed DDL"):
        _bound_titles(tmp_path, binding)
    assert provider.entries == provider.exits == 2


def test_bound_read_foreign_same_schema_connection_is_refused(tmp_path, monkeypatch):
    writer, provider, binding = _bound_fixture(tmp_path / "a")
    other = _runtime(tmp_path / "b")
    other.jobs.create_job("UNAPPROVED DATABASE B")
    original = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original(f"{other.store.path.as_uri()}?mode=ro", uri=True,
                              isolation_level=None)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(PersistenceError):
        _bound_titles(tmp_path / "a", binding)
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


def test_bound_read_invalid_then_valid_is_irreversibly_latched(tmp_path):
    _, provider, binding = _bound_fixture(tmp_path)
    provider.valid = False
    with pytest.raises(PersistenceError):
        _bound_titles(tmp_path, binding)
    provider.valid = True
    with pytest.raises(PersistenceError):
        _bound_titles(tmp_path, binding)
    assert provider.entries == provider.exits


@pytest.mark.parametrize("stage", ["query", "closed", "materialized"])
def test_bound_read_revoke_during_read_or_before_core_release(tmp_path, stage):
    _, provider, binding = _bound_fixture(tmp_path)
    if stage == "closed":
        provider.after_close = binding.invalidate

    def reader(runtime):
        if stage == "query":
            with runtime.store.read() as connection:
                rows = connection.execute("SELECT objective FROM jobs").fetchall()
                binding.invalidate()
                return [row[0] for row in rows]
        rows = [job.objective for job in runtime.jobs.list_jobs()]
        if stage == "materialized":
            binding.invalidate()
        return rows

    with pytest.raises(PersistenceError):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)
    assert provider.entries == provider.exits == 1


def test_bound_read_closes_rolls_back_and_does_not_retry(tmp_path, monkeypatch):
    _, provider, binding = _bound_fixture(tmp_path)
    original = sqlite3.connect
    calls, traces = [], []

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        calls.append(connection)
        connection.set_trace_callback(traces.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)

    def reader(runtime):
        with runtime.store.read() as connection:
            connection.execute("SELECT objective FROM jobs").fetchall()
            raise RuntimeError("application failure")

    with pytest.raises(RuntimeError, match="application failure"):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)
    assert len(calls) == 1
    assert "ROLLBACK" in traces
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        calls[0].execute("SELECT 1")
    assert provider.entries == provider.exits == 1


@pytest.mark.parametrize("journal", ["delete", "wal"])
def test_bound_read_database_bytes_and_bounded_sidecar_effects(tmp_path, journal):
    import hashlib
    writer, provider, binding = _bound_fixture(tmp_path)
    with sqlite3.connect(writer.store.path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        assert connection.execute(f"PRAGMA journal_mode={journal}").fetchone()[0] == journal
    before = hashlib.sha256(writer.store.path.read_bytes()).hexdigest()
    names_before = {p.name for p in writer.store.path.parent.iterdir()}
    seen = []
    provider.after_close = lambda: seen.append({p.name for p in writer.store.path.parent.iterdir()})
    assert _bound_titles(tmp_path, binding) == ["APPROVED DATABASE A"]
    assert hashlib.sha256(writer.store.path.read_bytes()).hexdigest() == before
    changes = set().union(*seen) - names_before
    assert changes <= {"executive.sqlite3-wal", "executive.sqlite3-shm"}
    if journal == "delete":
        assert changes == set()


def test_unprotected_path_aba_is_not_a_connection_identity_detector(tmp_path):
    # Explicit excluded counterexample: without namespace exclusion, restoring A
    # makes post-open path stats look unchanged while the open handle reads B.
    import os
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    for path, value in [(a, "A"), (b, "B")]:
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE example(value TEXT)")
            connection.execute("INSERT INTO example VALUES (?)", (value,))
    identity = a.stat().st_ino
    saved = tmp_path / "saved-a.db"
    os.rename(a, saved)
    os.rename(b, a)
    connection = sqlite3.connect(a)
    try:
        os.rename(a, b)
        os.rename(saved, a)
        assert a.stat().st_ino == identity
        assert connection.execute("SELECT value FROM example").fetchone()[0] == "B"
    finally:
        connection.close()


def test_bound_read_provider_cannot_suppress_application_error(tmp_path):
    from contextlib import contextmanager
    _, provider, binding = _bound_fixture(tmp_path)
    original_scope = provider.namespace

    @contextmanager
    def suppress(path):
        with original_scope(path):
            try:
                yield
            except RuntimeError:
                pass

    provider.namespace = suppress

    def reader(runtime):
        with runtime.store.read():
            raise RuntimeError("must survive namespace exit")
        return ["FALSE SUCCESS"]

    with pytest.raises(RuntimeError, match="must survive namespace exit"):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)


def test_bound_read_midquery_provider_refusal_is_typed_and_sticky(tmp_path):
    _, provider, binding = _bound_fixture(tmp_path)

    def reader(runtime):
        with runtime.store.read() as connection:
            connection.execute("SELECT objective FROM jobs").fetchall()
            provider.valid = False
        return []

    with pytest.raises(executive_runtime.RuntimeReadUnavailable):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)
    provider.valid = True
    with pytest.raises(executive_runtime.RuntimeReadUnavailable):
        _bound_titles(tmp_path, binding)


def test_bound_read_rejects_nested_unmaterialized_result(tmp_path):
    _, _, binding = _bound_fixture(tmp_path)

    def reader(runtime):
        with runtime.store.read() as connection:
            hidden = {connection}
        return {"hidden": hidden}

    with pytest.raises(PersistenceError, match="materialized"):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)


def test_bound_read_close_uncertainty_retains_namespace_without_retry(tmp_path, monkeypatch):
    _, provider, binding = _bound_fixture(tmp_path)
    original = sqlite3.connect
    calls = []

    class UncertainClose(sqlite3.Connection):
        def close(self):
            calls.append("close")
            raise OSError("close outcome unavailable")

    connections = []
    def connect(*args, **kwargs):
        connection = original(*args, factory=UncertainClose, **kwargs)
        connections.append(connection)
        return connection
    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        with pytest.raises((PersistenceError, OSError)):
            _bound_titles(tmp_path, binding)
        assert provider.lock.locked(), "namespace must outlive uncertain physical close"
        assert provider.exits == 0
        assert calls == ["close"]
        with pytest.raises(PersistenceError):
            _bound_titles(tmp_path, binding)
        assert calls == ["close"]
    finally:
        # Test-owned physical resources only. No production retry/recovery API.
        for connection in connections:
            sqlite3.Connection.close(connection)
        retained = getattr(binding, "_retained_namespace", None)
        if retained is not None:
            retained.close()


def test_bound_read_sqlite_query_error_is_unavailable(tmp_path):
    _, provider, binding = _bound_fixture(tmp_path)
    def reader(runtime):
        with runtime.store.read() as connection:
            connection.execute("SELECT * FROM definitely_absent_table")
        return []
    with pytest.raises(PersistenceError):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)
    assert provider.entries == provider.exits == 1


def test_bound_read_setup_close_failure_retains_actual_connection(tmp_path, monkeypatch):
    _, provider, binding = _bound_fixture(tmp_path)
    original = sqlite3.connect
    connections = []
    class SetupCursor(sqlite3.Cursor):
        def execute(self, sql, *args):
            if sql.startswith("PRAGMA foreign_keys"):
                raise sqlite3.OperationalError("setup failed")
            return super().execute(sql, *args)
    class SetupFailure(sqlite3.Connection):
        def cursor(self):
            return super().cursor(factory=SetupCursor)
        def close(self):
            raise OSError("close unknown")
    def connect(*args, **kwargs):
        connection = original(*args, factory=SetupFailure, **kwargs)
        connections.append(connection)
        return connection
    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        with pytest.raises((PersistenceError, OSError)):
            _bound_titles(tmp_path, binding)
        assert provider.lock.locked()
        assert provider.exits == 0
        assert len(connections) == 1
    finally:
        for connection in connections:
            sqlite3.Connection.close(connection)
        retained = getattr(binding, "_retained_namespace", None)
        if retained is not None:
            retained.close()


@pytest.mark.parametrize("uncertain_close", [False, True])
def test_bound_read_setup_interrupt_closes_or_retains_namespace(tmp_path, monkeypatch, uncertain_close):
    _, provider, binding = _bound_fixture(tmp_path)
    original = sqlite3.connect
    connections, events = [], []
    provider.after_close = lambda: events.append("namespace_exit")

    class InterruptedCursor(sqlite3.Cursor):
        def execute(self, sql, *args):
            if sql.startswith("PRAGMA foreign_keys"):
                events.append("interrupt")
                raise KeyboardInterrupt("post-connect setup interrupted")
            return super().execute(sql, *args)

    class InterruptedSetup(sqlite3.Connection):
        def cursor(self):
            return super().cursor(factory=InterruptedCursor)

        def close(self):
            assert provider.lock.locked(), "close escaped namespace custody"
            events.append("close_attempt")
            if uncertain_close:
                raise OSError("close outcome unavailable")
            super().close()
            events.append("physically_closed")

    def connect(*args, **kwargs):
        connection = original(*args, factory=InterruptedSetup, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        with pytest.raises((KeyboardInterrupt, OSError)):
            _bound_titles(tmp_path, binding)
        assert len(connections) == 1
        if uncertain_close:
            assert events == ["interrupt", "close_attempt"]
            assert binding._unclosed_connection is connections[0]
            assert provider.lock.locked() and provider.exits == 0
        else:
            assert events == ["interrupt", "close_attempt", "physically_closed", "namespace_exit"]
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connections[0].execute("SELECT 1")
            assert not provider.lock.locked() and provider.exits == 1
        with pytest.raises(PersistenceError):
            _bound_titles(tmp_path, binding)
        assert len(connections) == 1  # failed request cannot reconnect
    finally:
        # Reconcile only the synthetic test-owned handle/exclusion for teardown.
        for connection in connections:
            sqlite3.Connection.close(connection)
        retained = getattr(binding, "_retained_namespace", None)
        if retained is not None:
            retained.close()


def test_bound_read_resolution_and_schema_share_actual_handle(tmp_path, monkeypatch):
    from pathlib import Path
    _, provider, binding = _bound_fixture(tmp_path)
    original_resolve, original_connect = Path.resolve, sqlite3.connect
    connections, traces = [], []
    def resolve(path, *args, **kwargs):
        assert provider.lock.locked(), "runtime path resolution escaped custody"
        return original_resolve(path, *args, **kwargs)
    def connect(*args, **kwargs):
        assert provider.lock.locked()
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        connection.set_trace_callback(traces.append)
        return connection
    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(sqlite3, "connect", connect)
    assert _bound_titles(tmp_path, binding) == ["APPROVED DATABASE A"]
    assert len(connections) == 1  # no constructor/probe connection
    begin = traces.index("BEGIN")
    schema = next(i for i, sql in enumerate(traces) if "version, name, checksum FROM schema_migrations" in sql)
    jobs = next(i for i, sql in enumerate(traces) if "FROM jobs ORDER BY" in sql)
    assert begin < schema < jobs
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


def test_bound_read_supplied_foreign_snapshot_is_not_admitted(tmp_path):
    writer, _, binding = _bound_fixture(tmp_path)
    outside = sqlite3.connect(writer.store.path)
    outside.row_factory = sqlite3.Row
    outside.execute("BEGIN")
    try:
        def reader(runtime):
            with runtime.store.read() as owned:
                runtime.store._assert_owned_snapshot_connection(owned)
                with pytest.raises(StateConflict):
                    runtime.store._assert_owned_snapshot_connection(outside)
                return owned.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert Runtime.read_bound(tmp_path, binding=binding, reader=reader) == 1
    finally:
        outside.close()


def test_bound_managed_surface_has_no_native_or_factory_escape(tmp_path):
    writer, _, binding = _bound_fixture(tmp_path)
    runtime = Runtime.at(tmp_path, create=False, read_binding=binding)
    with runtime.store.read() as connection:
        cursor = connection.execute("SELECT objective FROM jobs")
        assert not isinstance(connection, sqlite3.Connection)
        assert not isinstance(cursor, sqlite3.Cursor)
        assert cursor.connection is connection and iter(cursor) is cursor
        assert isinstance(next(cursor), sqlite3.Row)
        assert cursor.row_factory is connection.row_factory is sqlite3.Row
        assert cursor.description[0][0] == "objective"
        for view, names in [(connection, ["commit", "rollback", "close", "executemany", "executescript", "blobopen", "backup", "serialize", "deserialize", "set_authorizer"]), (cursor, ["executemany", "executescript"])]:
            for name in names:
                with pytest.raises(AttributeError):
                    getattr(view, name)
        for view, name, value in [(connection, "row_factory", lambda *args: args), (cursor, "row_factory", lambda *args: args), (connection, "isolation_level", None), (connection, "in_transaction", False), (cursor, "connection", writer.store), (cursor, "arraysize", 200)]:
            with pytest.raises(AttributeError):
                setattr(view, name, value)
        with pytest.raises(TypeError):
            connection.cursor(factory=sqlite3.Cursor)
        with pytest.raises(TypeError):
            sqlite3.Cursor(connection)
        with pytest.raises(TypeError):
            sqlite3.Connection.execute(connection, "SELECT 1")
        with pytest.raises(TypeError):
            sqlite3.Cursor.execute(cursor, "SELECT 1")
        with pytest.raises(TypeError):
            with connection:
                pass
        cursor.close()
        cursor.close()  # successful close is idempotent


@pytest.mark.parametrize("sql", ["COMMIT", "-- owned transaction\nROLLBACK", "SAVEPOINT sneak", "ATTACH ':memory:' AS other", "PRAGMA foreign_keys=OFF", "PRAGMA writable_schema=ON", "CREATE TEMP TABLE unwanted(value)"])
def test_bound_managed_query_cannot_change_connection_or_transaction(tmp_path, sql):
    _, _, binding = _bound_fixture(tmp_path)
    runtime = Runtime.at(tmp_path, create=False, read_binding=binding)
    with runtime.store.read() as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(sql)
        assert connection.in_transaction
        assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_bound_managed_snapshot_requires_exact_active_view(tmp_path):
    import copy
    writer, _, binding = _bound_fixture(tmp_path)
    first = Runtime.at(tmp_path, create=False, read_binding=binding)
    other = Runtime.at(tmp_path, create=False, read_binding=binding)
    raw = sqlite3.connect(writer.store.path)
    try:
        with first.store.read() as active:
            first.store._assert_owned_snapshot_connection(active)
            for foreign in [raw, copy.copy(active)]:
                with pytest.raises(StateConflict):
                    first.store._assert_owned_snapshot_connection(foreign)
            with pytest.raises(StateConflict):
                other.store._assert_owned_snapshot_connection(active)
        with first.store.read() as newer:
            first.store._assert_owned_snapshot_connection(newer)
            with pytest.raises(StateConflict):
                first.store._assert_owned_snapshot_connection(active)
    finally:
        raw.close()


@pytest.mark.parametrize("kind", ["connection", "cursor"])
def test_bound_managed_return_rejects_nested_views(tmp_path, kind):
    _, _, binding = _bound_fixture(tmp_path)
    def reader(runtime):
        with runtime.store.read() as connection:
            cursor = connection.execute("SELECT objective FROM jobs")
        return {"nested": [connection if kind == "connection" else cursor]}
    with pytest.raises(PersistenceError, match="materialized"):
        Runtime.read_bound(tmp_path, binding=binding, reader=reader)


@pytest.mark.parametrize("trigger", ["public_close", "context_exit"])
def test_bound_managed_cursor_close_failure_retains_all_resources(tmp_path, monkeypatch, trigger):
    _, provider, binding = _bound_fixture(tmp_path)
    original = sqlite3.connect
    connections, events, bad = [], [], []
    class FaultCursor(sqlite3.Cursor):
        fail = False
        def execute(self, sql, *args):
            result = super().execute(sql, *args)
            if "SELECT objective" in sql:
                self.fail = True
                bad.append(self)
            return result
        def close(self):
            assert provider.lock.locked()
            events.append(("cursor_close", self.fail))
            if self.fail:
                raise KeyboardInterrupt("cursor finalization unknown")
            return super().close()
    class FaultConnection(sqlite3.Connection):
        def cursor(self):
            return super().cursor(factory=FaultCursor)
        def close(self):
            events.append(("native_close", None))
            return super().close()
    def connect(*args, **kwargs):
        native = original(*args, factory=FaultConnection, **kwargs)
        connections.append(native)
        return native
    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        runtime = Runtime.at(tmp_path, create=False, read_binding=binding)
        with pytest.raises((KeyboardInterrupt, PersistenceError)):
            with runtime.store.read() as connection:
                connection.execute("SELECT 1").close()  # mixed closed/pending
                cursor = connection.cursor().execute("SELECT objective FROM jobs")
                if trigger == "public_close":
                    cursor.close()
        assert events.count(("cursor_close", True)) == 1
        assert ("native_close", None) not in events
        assert provider.lock.locked() and provider.exits == 0
        assert binding._unclosed_connection is connections[0]
        assert binding._unclosed_resources is connection
        assert bad[0] in [item._cursor for item in connection._cursors]
        with pytest.raises(PersistenceError):
            _bound_titles(tmp_path, binding)
        assert len(connections) == 1
    finally:
        # Only disposable fault-injected test resources, not production recovery.
        for native in connections:
            view = binding._unclosed_resources
            if view is not None:
                for item in view._cursors:
                    sqlite3.Cursor.close(item._cursor)
            sqlite3.Connection.close(native)
        if binding._retained_namespace is not None:
            binding._retained_namespace.close()


def test_bound_managed_execute_interrupt_finalizes_registered_cursor(tmp_path, monkeypatch):
    _, provider, binding = _bound_fixture(tmp_path)
    original = sqlite3.connect
    cursors, events = [], []
    provider.after_close = lambda: events.append("namespace_exit")
    class InterruptCursor(sqlite3.Cursor):
        def execute(self, sql, *args):
            if "FROM jobs" in sql:
                events.append("interrupt")
                raise KeyboardInterrupt("execute interrupted")
            return super().execute(sql, *args)
        def close(self):
            assert provider.lock.locked()
            events.append("cursor_close")
            return super().close()
    class InterruptConnection(sqlite3.Connection):
        def cursor(self):
            cursor = super().cursor(factory=InterruptCursor)
            cursors.append(cursor)
            return cursor
        def close(self):
            assert provider.lock.locked()
            super().close()
            events.append("native_close")
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: original(*args, factory=InterruptConnection, **kwargs))
    with pytest.raises(KeyboardInterrupt):
        _bound_titles(tmp_path, binding)
    assert events.index("interrupt") < events.index("cursor_close") < events.index("native_close") < events.index("namespace_exit")
    assert events.count("cursor_close") == len(cursors)
    assert provider.exits == 1 and not provider.lock.locked()


def test_bound_managed_change_preserves_unbound_native_api(tmp_path):
    writer, _, _ = _bound_fixture(tmp_path)
    with writer.store.read() as connection:
        assert isinstance(connection, sqlite3.Connection)
        cursor = connection.cursor()
        assert isinstance(cursor, sqlite3.Cursor)
        cursor.execute("SELECT objective FROM jobs")
        assert cursor.fetchone()[0] == "APPROVED DATABASE A"
        cursor.close()


def test_bound_managed_schema_cancellation_drains_acquired_connection(tmp_path, monkeypatch):
    writer, provider, binding = _bound_fixture(tmp_path)
    runtime = Runtime.at(tmp_path, create=False, read_binding=binding)
    def interrupted_schema(connection):
        cursor = connection.execute("SELECT objective FROM jobs")
        assert cursor.fetchone()[0] == "APPROVED DATABASE A"
        raise KeyboardInterrupt("schema phase interrupted")
    monkeypatch.setattr(runtime.store, "_verify_current_schema", interrupted_schema)
    with pytest.raises(KeyboardInterrupt):
        with runtime.store.read():
            pytest.fail("schema interruption must precede caller access")
    assert provider.exits == 1 and not provider.lock.locked()
    assert binding._unclosed_connection is None
    assert _bound_exclusive_witness(writer.store.path)
    with pytest.raises(PersistenceError):
        with runtime.store.read():
            pytest.fail("invalid request cannot reconnect")
