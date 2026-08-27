"""Behavioral proof that execution identity cannot rewrite Sol CEO authority.

This is a conformance-only test. It uses the existing Executive Runtime Job,
Attempt, Worker, quota and requeue semantics and adds no production contract.
"""
from __future__ import annotations

from control_plane.executive_runtime import Runtime, WorkerStatus


_CEO_PROVENANCE = {"schema": "mastermind.ceo_intent.v1", "actor": "sol"}


def test_one_ceo_job_keeps_authority_across_worker_provider_failover(tmp_path):
    runtime = Runtime.at(tmp_path)
    runtime.workers.register_worker(
        "codex-01",
        provider="codex",
        account_label="chatgpt1-codex-capacity",
        worker_type="fixture",
        capabilities=["code"],
        quota_classes={"codex-native": ["code"]},
    )
    runtime.workers.register_worker(
        "claude-01",
        provider="claude",
        account_label="claude5-communication-principal",
        worker_type="fixture",
        capabilities=["code"],
        quota_classes={"claude-native": ["code"]},
    )

    job = runtime.jobs.create_job(
        "Bounded CEO-owned technical continuation",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance=_CEO_PROVENANCE,
        requested_authorities=["READ"],
        constraints={
            "required_capabilities": ["code"],
            "eligible_quota_classes": ["codex-native", "claude-native"],
        },
    )
    authority_snapshot = (
        job.owner_seat,
        job.escalation_target,
        tuple(job.requested_authorities),
        job.authority_policy_hash,
    )
    assert "provider" not in job.constraints
    assert "model" not in job.constraints

    runtime.jobs.assign_job(job.job_id, "codex-01", quota_class="codex-native")
    first = runtime.jobs.get_job(job.job_id)
    assert first is not None
    first_attempt_id = first.current_attempt_id
    assert first_attempt_id is not None
    assert first.assigned_worker_id == "codex-01"
    assert first.assigned_quota_class == "codex-native"
    assert runtime.workers.get_worker("codex-01").provider == "codex"  # type: ignore[union-attr]
    assert (
        first.owner_seat,
        first.escalation_target,
        tuple(first.requested_authorities),
        first.authority_policy_hash,
    ) == authority_snapshot

    runtime.workers.set_worker_status(
        "codex-01",
        WorkerStatus.RATE_LIMITED,
        quota_class="codex-native",
    )
    requeued = runtime.jobs.requeue_job(job.job_id)
    # Detached requeue clears the current Attempt pointer. The historical
    # Codex Attempt remains distinct evidence, and the next dispatch must mint
    # a fresh Attempt without changing the durable CEO authority snapshot.
    assert requeued.current_attempt_id is None
    assert requeued.assigned_worker_id is None
    assert (
        requeued.owner_seat,
        requeued.escalation_target,
        tuple(requeued.requested_authorities),
        requeued.authority_policy_hash,
    ) == authority_snapshot

    replacement = runtime.broker.dispatch(job.job_id)
    assert replacement is not None
    assert replacement.worker_id == "claude-01"

    second = runtime.jobs.get_job(job.job_id)
    assert second is not None
    assert second.job_id == job.job_id
    assert second.assigned_worker_id == "claude-01"
    assert second.assigned_quota_class == "claude-native"
    assert second.current_attempt_id is not None
    assert second.current_attempt_id != first_attempt_id
    assert second.attempt_count == 2
    assert runtime.workers.get_worker("claude-01").provider == "claude"  # type: ignore[union-attr]
    assert (
        second.owner_seat,
        second.escalation_target,
        tuple(second.requested_authorities),
        second.authority_policy_hash,
    ) == authority_snapshot

    # Provider/account labels are execution/communication evidence only. Even
    # deliberately Sol/Slack-looking canonical labels cannot rewrite the Job's
    # durable executive authority.
    assert runtime.workers.get_worker("codex-01").account_label.startswith("chatgpt1")  # type: ignore[union-attr]
    assert runtime.workers.get_worker("claude-01").account_label.startswith("claude5")  # type: ignore[union-attr]
    assert second.owner_seat == "ceo"
    assert second.escalation_target == "ceo"
