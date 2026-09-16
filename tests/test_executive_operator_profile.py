"""Provider-neutral rich-operator binding resolution (OCR-4A Task 3)."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_operator_profile import (
    OperatorImplementationSupport,
    OperatorProfileResolutionError,
    resolve_operator_execution_binding,
)
from control_plane.executive_runtime import (
    Attempt,
    AttemptStatus,
    Job,
    JobStatus,
    WorkerQuotaClass,
    WorkerStatus,
)
from control_plane.model_router import ModelRouter
from control_plane.operator_harness_contract import (
    AttemptExecutionMode,
    AuthRealmRequirement,
)
from control_plane.remote_codex_operator_adapter import codex_remote_capabilities


def _fixture():
    registry = ExecutionCapabilityRegistry.load()
    route = ModelRouter.load().model_aliases["coo.operator.readonly"]
    profile = registry.resolve(route.execution_profile_id)
    constraints = {
        "model": route.model,
        "effort": route.effort,
        "execution_profile_id": profile.profile_id,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "harness_binary_digest": "a" * 64,
        "harness_version": "0.147.0",
    }
    job = Job(
        job_id="job-operator-1",
        objective="Produce one bounded read-only plan.",
        department="executive-infrastructure",
        priority=9,
        status=JobStatus.RUNNING,
        assigned_worker_id="worker-a",
        assigned_quota_class="codex-coo-operator",
        authority_level="READ",
        branch=None,
        worktree=None,
        checkpoint=None,
        result=None,
        created_at="2026-09-14T00:00:00Z",
        updated_at="2026-09-14T00:00:01Z",
        constraints=constraints,
        current_attempt_id="attempt-1",
        requested_authorities=["READ"],
        authority_policy_hash="f" * 64,
        root_job_id="job-operator-1",
        orchestration_role="plan",
    )
    attempt = Attempt(
        attempt_id="attempt-1",
        job_id=job.job_id,
        attempt_number=1,
        worker_id="worker-a",
        quota_class="codex-coo-operator",
        status=AttemptStatus.CLAIMED,
        fence_generation=1,
        lease_owner="supervisor-1",
        lease_expires_at="2026-09-14T00:10:00Z",
        heartbeat_at="2026-09-14T00:00:01Z",
        checkpoint_sequence=0,
        checkpoint=None,
        result=None,
        error=None,
        started_at="2026-09-14T00:00:01Z",
        finished_at="",
        version=1,
        authority_policy_hash=job.authority_policy_hash,
        pid=None,
        pgid=None,
        process_start_identity=None,
        boot_id=None,
        provider_session_id=None,
        stdout_path=None,
        stderr_path=None,
        result_path=None,
        exit_code=None,
        launch_metadata={},
        execution_mode=AttemptExecutionMode.OPERATOR_HARNESS.value,
    )
    metadata = {
        "execution_profile_id": profile.profile_id,
        "execution_profile_digest": profile.profile_digest,
        "capability_policy_version": registry.policy_version,
        "capability_policy_digest": registry.policy_digest,
        "harness_binary_digest": "a" * 64,
        "harness_version": "0.147.0",
    }
    quota = WorkerQuotaClass(
        worker_id="worker-a",
        quota_class="codex-coo-operator",
        status=WorkerStatus.BUSY,
        provider=route.provider_alias,
        model=route.model,
        effort=route.effort,
        cost_class=route.cost_class,
        capabilities=list(route.capabilities),
        active_attempt_id=attempt.attempt_id,
        active_job_id=job.job_id,
        fence_generation=1,
        last_seen_at="2026-09-14T00:00:01Z",
        metadata=metadata,
    )
    support = OperatorImplementationSupport(
        worker_provider="codex",
        provider="openai-codex",
        execution_surface="codex-app-server",
        harness_kind="codex-app-server",
        capability_auth_realm="dedicated-worker-account",
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
        remote_capabilities=codex_remote_capabilities(),
    )
    return job, attempt, quota, registry, support


def _resolve(job, attempt, quota, registry, support):
    return resolve_operator_execution_binding(
        job=job,
        attempt=attempt,
        quota=quota,
        capability_registry=registry,
        implementation=support,
    )


def test_current_codex_binding_preserves_exact_reviewed_identity():
    job, attempt, quota, registry, support = _fixture()
    binding = _resolve(job, attempt, quota, registry, support)
    assert binding.provider == "openai-codex"
    assert binding.harness_kind == "codex-app-server"
    assert binding.harness_binary_digest == "a" * 64
    assert binding.harness_version == "0.147.0"
    assert binding.model == "gpt-5.6-sol"
    assert binding.effort == "xhigh"
    assert binding.capability_profile_id == job.constraints["execution_profile_id"]
    assert binding.capability_profile_digest == job.constraints["execution_profile_digest"]
    assert binding.auth_realm_requirement is AuthRealmRequirement.SLOT_BOUND_V1
    assert binding.remote_capabilities == codex_remote_capabilities()


def test_hermetic_synthetic_claude_binding_uses_same_pure_contract():
    job, attempt, quota, registry, _support = _fixture()
    current = registry.resolve(job.constraints["execution_profile_id"])
    synthetic = dataclasses.replace(
        current,
        profile_id="operator.synthetic.claude.readonly.v1",
        execution_surface="claude-agent-sdk",
        profile_digest="c" * 64,
    )
    synthetic_registry = dataclasses.replace(
        registry,
        policy_version="synthetic-claude-policy-v1",
        policy_digest="d" * 64,
        profiles={synthetic.profile_id: synthetic},
        source_path=Path("/nonexistent/hermetic-policy.json"),
    )
    synthetic_constraints = dict(job.constraints)
    synthetic_constraints.update(
        {
            "model": "claude-opus-5-20260830",
            "effort": "high",
            "execution_profile_id": synthetic.profile_id,
            "execution_profile_digest": synthetic.profile_digest,
            "capability_policy_version": synthetic_registry.policy_version,
            "capability_policy_digest": synthetic_registry.policy_digest,
            "harness_binary_digest": "e" * 64,
            "harness_version": "1.0.0",
        }
    )
    job = dataclasses.replace(job, constraints=synthetic_constraints)
    metadata = dict(quota.metadata)
    metadata.update(
        {
            "execution_profile_id": synthetic.profile_id,
            "execution_profile_digest": synthetic.profile_digest,
            "capability_policy_version": synthetic_registry.policy_version,
            "capability_policy_digest": synthetic_registry.policy_digest,
            "harness_binary_digest": "e" * 64,
            "harness_version": "1.0.0",
        }
    )
    quota = dataclasses.replace(
        quota,
        provider="claude",
        model="claude-opus-5-20260830",
        effort="high",
        metadata=metadata,
    )
    support = OperatorImplementationSupport(
        worker_provider="claude",
        provider="claude",
        execution_surface="claude-agent-sdk",
        harness_kind="claude-agent-sdk",
        capability_auth_realm="dedicated-worker-account",
        auth_realm_requirement=AuthRealmRequirement.SLOT_BOUND_V1,
        remote_capabilities=dataclasses.replace(
            codex_remote_capabilities(),
            provider_capability_ids=("claude-agent-sdk",),
        ),
    )
    binding = _resolve(job, attempt, quota, synthetic_registry, support)
    assert binding.provider == "claude"
    assert binding.harness_kind == "claude-agent-sdk"
    assert binding.model == "claude-opus-5-20260830"
    assert binding.capability_profile_id == synthetic.profile_id
    assert binding.remote_capabilities.provider_capability_ids == (
        "claude-agent-sdk",
    )


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda j, a, q, r, s: (j, dataclasses.replace(a, worker_id="worker-b"), q, r, s),
            "Job assigned Worker identity drifted",
        ),
        (
            lambda j, a, q, r, s: (j, a, dataclasses.replace(q, provider="claude"), r, s),
            "lacks the supplied operator implementation",
        ),
        (
            lambda j, a, q, r, s: (
                dataclasses.replace(j, constraints={**j.constraints, "execution_profile_digest": "0" * 64}),
                a,
                q,
                r,
                s,
            ),
            "execution-profile identity drifted",
        ),
        (
            lambda j, a, q, r, s: (
                j,
                a,
                q,
                dataclasses.replace(r, policy_digest="0" * 64),
                s,
            ),
            "capability policy identity drifted",
        ),
        (
            lambda j, a, q, r, s: (
                j,
                a,
                q,
                dataclasses.replace(
                    r,
                    profiles={
                        j.constraints["execution_profile_id"]: dataclasses.replace(
                            r.resolve(j.constraints["execution_profile_id"]),
                            write_capable=True,
                        )
                    },
                ),
                s,
            ),
            "widen read-only authority",
        ),
        (
            lambda j, a, q, r, s: (
                j,
                a,
                q,
                r,
                dataclasses.replace(s, execution_surface="claude-agent-sdk"),
            ),
            "no matching implementation support",
        ),
        (
            lambda j, a, q, r, s: (
                j,
                a,
                dataclasses.replace(q, model="other-model"),
                r,
                s,
            ),
            "model or effort drifted",
        ),
    ],
)
def test_identity_authority_and_implementation_drift_refuse(mutator, match):
    values = mutator(*_fixture())
    with pytest.raises(OperatorProfileResolutionError, match=match):
        _resolve(*values)


def test_preclaim_job_snapshot_without_assignment_fields_is_accepted():
    job, attempt, quota, registry, support = _fixture()
    stale_snapshot = dataclasses.replace(
        job,
        current_attempt_id=None,
        assigned_worker_id=None,
        assigned_quota_class=None,
    )
    assert _resolve(stale_snapshot, attempt, quota, registry, support) == _resolve(
        job, attempt, quota, registry, support
    )


def test_provider_identity_does_not_infer_owner_seat_or_role():
    job, attempt, quota, registry, support = _fixture()
    baseline = _resolve(job, attempt, quota, registry, support)
    changed_job = dataclasses.replace(job, owner_seat="cto", orchestration_role="review")
    assert _resolve(changed_job, attempt, quota, registry, support) == baseline


def test_resolution_requires_claimed_operator_attempt_and_exact_harness_pin():
    job, attempt, quota, registry, support = _fixture()
    with pytest.raises(OperatorProfileResolutionError, match="CLAIMED"):
        _resolve(
            job,
            dataclasses.replace(attempt, status=AttemptStatus.RUNNING),
            quota,
            registry,
            support,
        )
    bad_metadata = dict(quota.metadata)
    bad_metadata["harness_version"] = "0.999.0"
    with pytest.raises(OperatorProfileResolutionError, match="harness identity"):
        _resolve(job, attempt, dataclasses.replace(quota, metadata=bad_metadata), registry, support)
