from __future__ import annotations

import dataclasses
import importlib

import pytest

from control_plane.executive_orchestration_principal import digest
from control_plane.executive_runtime import Job, JobStatus


def _job(
    *,
    job_id: str = "JOB-123",
    root_job_id: str = "JOB-001",
    parent_job_id: str | None = "JOB-001",
    role: str | None = "work",
) -> Job:
    provenance = {
        "schema_version": "mastermind.executive_orchestration_provenance/v1",
        "creator": "coo_cycle",
        "source_id": "coo-cycle-source-123",
        "source_digest": "a" * 64,
        "command_id": "coo-cycle:JOB-001:create-work:JOB-123",
        "job_id": job_id,
        "parent_job_id": parent_job_id,
        "root_job_id": root_job_id,
        "role": role,
    }
    lineage: dict[str, object] = {}
    if role in {"work", "review", "repair"}:
        lineage.update(
            plan_attempt_id="ATT-001",
            plan_digest="b" * 64,
            plan_step_id="step-1",
            repair_round=0 if role in {"work", "review"} else 1,
        )
    if role == "review":
        lineage["reviews_job_id"] = "JOB-122"
    if role == "repair":
        lineage["supersedes_job_id"] = "JOB-122"

    return Job(
        job_id=job_id,
        objective="Implement the bounded Executive child.",
        department="executive-infrastructure",
        priority=9,
        status=JobStatus.QUEUED,
        assigned_worker_id=None,
        assigned_quota_class=None,
        authority_level="A0",
        branch=None,
        worktree=None,
        checkpoint=None,
        result=None,
        created_at="2026-08-29T00:00:00Z",
        updated_at="2026-08-29T00:00:00Z",
        parent_job_id=parent_job_id,
        root_job_id=root_job_id,
        depth=1,
        orchestration_role=role,
        orchestration_provenance=provenance,
        orchestration_provenance_digest=digest(provenance),
        **lineage,
    )


def _identity_module():
    return importlib.import_module("control_plane.executive_delegation_identity")


def test_canonical_child_projects_to_stable_company_identity() -> None:
    identity = _identity_module().derive_delegation_identity(_job())

    assert dataclasses.asdict(identity) == {
        "job_id": "JOB-123",
        "root_job_id": "JOB-001",
        "operation_key": "exec-job-123",
        "session_ref": "asd-session-exec-job-123",
    }


def test_identity_value_is_immutable() -> None:
    identity = _identity_module().derive_delegation_identity(_job())

    with pytest.raises(dataclasses.FrozenInstanceError):
        identity.operation_key = "exec-job-999"  # type: ignore[misc]


def _replace_provenance(job: Job, **updates: object) -> Job:
    provenance = dict(job.orchestration_provenance or {})
    provenance.update(updates)
    return dataclasses.replace(
        job,
        orchestration_provenance=provenance,
        orchestration_provenance_digest=digest(provenance),
    )


def _remove_provenance_key(job: Job, key: str) -> Job:
    provenance = dict(job.orchestration_provenance or {})
    provenance.pop(key)
    return dataclasses.replace(
        job,
        orchestration_provenance=provenance,
        orchestration_provenance_digest=digest(provenance),
    )


def test_attempt_provider_and_semantic_rollover_cannot_change_identity() -> None:
    module = _identity_module()
    original = _job()
    expected = module.derive_delegation_identity(original)
    rollover = dataclasses.replace(
        original,
        objective="Same Job, revised semantic prose.",
        assigned_worker_id="worker-2",
        assigned_quota_class="provider-b",
        current_attempt_id="ATT-002",
        attempt_count=2,
        constraints={
            "provider": "provider-b",
            "account": "account-b",
            "host": "host-b",
        },
        updated_at="2026-08-29T00:01:00Z",
    )
    changed_commission = _replace_provenance(
        rollover,
        source_id="coo-cycle-source-456",
        source_digest="c" * 64,
        command_id="coo-cycle:JOB-001:create-work:JOB-123:replay",
    )

    assert module.derive_delegation_identity(changed_commission) == expected


def test_distinct_work_review_repair_and_successor_jobs_have_distinct_identity() -> None:
    module = _identity_module()
    jobs = [
        _job(job_id="JOB-123", role="work"),
        _job(job_id="JOB-124", role="review"),
        _job(job_id="JOB-125", role="repair"),
        dataclasses.replace(
            _job(job_id="JOB-126", role="work"),
            supersedes_job_id=None,
        ),
    ]

    identities = [module.derive_delegation_identity(job) for job in jobs]

    assert len({identity.operation_key for identity in identities}) == 4
    assert len({identity.session_ref for identity in identities}) == 4


def test_projected_identifiers_are_valid_dialogue_v2_parent_identity() -> None:
    from integrations.slack_agent_dialogue.contract_v2 import (
        PARENT_SCHEMA_V2,
        build_parent_v2,
    )

    identity = _identity_module().derive_delegation_identity(_job())
    parent = build_parent_v2(
        {
            "schema": PARENT_SCHEMA_V2,
            "work_ref": "WS:AUTONOMY-DIALOGUE",
            "commission_ref": {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "commit": "a" * 40,
                "path": "research/commission.md",
                "content_sha256": "b" * 64,
            },
            "session_ref": identity.session_ref,
            "operation_key": identity.operation_key,
            "watch_mode": None,
            "allowed_sol_user_ids": ["U0BRETDUAS2"],
            "created_at": "2026-08-29T00:00:00Z",
        }
    )

    assert parent["operation_key"] == "exec-job-123"
    assert parent["session_ref"] == "asd-session-exec-job-123"


def test_runtime_round_boundaries_remain_projectable() -> None:
    module = _identity_module()

    review = dataclasses.replace(_job(role="review"), repair_round=2)
    repair = dataclasses.replace(_job(role="repair"), repair_round=2)

    assert module.derive_delegation_identity(review).operation_key == "exec-job-123"
    assert module.derive_delegation_identity(repair).operation_key == "exec-job-123"


@pytest.mark.parametrize(
    "invalid_job",
    [
        pytest.param(lambda: _job(role=None), id="legacy-role-null"),
        pytest.param(lambda: _job(role="aggregation"), id="aggregation-root"),
        pytest.param(lambda: _job(role="foreign"), id="unknown-role"),
        pytest.param(lambda: _job(parent_job_id=None), id="missing-parent"),
        pytest.param(
            lambda: _job(parent_job_id="JOB-002"), id="parent-root-mismatch"
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), depth=2), id="indirect-child"
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), depth=True), id="boolean-depth"
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), depth=1.0), id="floating-depth"
        ),
        pytest.param(lambda: _job(job_id="job-123"), id="malformed-job-id"),
        pytest.param(lambda: _job(root_job_id="ROOT-001"), id="malformed-root-id"),
        pytest.param(
            lambda: _job(parent_job_id="ROOT-001"), id="malformed-parent-id"
        ),
        pytest.param(
            lambda: _job(job_id="JOB-001"), id="child-is-root"
        ),
        pytest.param(
            lambda: _job(job_id="JOB-" + "1" * 200), id="transport-overflow"
        ),
        pytest.param(
            lambda: _remove_provenance_key(_job(), "command_id"),
            id="incomplete-provenance",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), extra="value"),
            id="extra-provenance",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), schema_version="foreign/v1"),
            id="foreign-schema",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), creator="foreign"),
            id="foreign-creator",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), job_id="JOB-999"),
            id="provenance-job-mismatch",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), parent_job_id="JOB-999"),
            id="provenance-parent-mismatch",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), root_job_id="JOB-999"),
            id="provenance-root-mismatch",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), role="review"),
            id="provenance-role-mismatch",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), source_id="bad source"),
            id="malformed-source-id",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), source_digest="A" * 64),
            id="malformed-source-digest",
        ),
        pytest.param(
            lambda: _replace_provenance(_job(), command_id="bad command"),
            id="malformed-command-id",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(), orchestration_provenance_digest=None
            ),
            id="missing-provenance-digest",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(), orchestration_provenance_digest="A" * 64
            ),
            id="malformed-provenance-digest",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(), orchestration_provenance_digest="0" * 64
            ),
            id="provenance-digest-mismatch",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), plan_attempt_id=None),
            id="work-missing-plan-attempt",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), repair_round=1),
            id="work-repair-round",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), repair_round=True),
            id="boolean-repair-round",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), reviews_job_id="JOB-122"),
            id="work-carries-review-target",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(), supersedes_job_id="JOB-122"),
            id="work-carries-superseded-job",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="review"), reviews_job_id=None
            ),
            id="review-missing-reviewed-job",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(role="review"), repair_round=3),
            id="review-round-outside-runtime-contract",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="review"), reviews_job_id="JOB-123"
            ),
            id="review-self-reference",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="review"), reviews_job_id="JOB-001"
            ),
            id="review-root-reference",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="repair"), supersedes_job_id=None
            ),
            id="repair-missing-superseded-job",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(role="repair"), repair_round=3),
            id="repair-round-outside-runtime-contract",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="repair"), supersedes_job_id="JOB-123"
            ),
            id="repair-self-reference",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="repair"), supersedes_job_id="JOB-001"
            ),
            id="repair-root-reference",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="plan"), plan_attempt_id="ATT-001"
            ),
            id="plan-carries-plan-attempt",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(role="plan"), plan_digest="b" * 64),
            id="plan-carries-plan-digest",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(role="plan"), plan_step_id="step-1"),
            id="plan-carries-plan-step",
        ),
        pytest.param(
            lambda: dataclasses.replace(_job(role="plan"), repair_round=0),
            id="plan-carries-repair-round",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="plan"), reviews_job_id="JOB-122"
            ),
            id="plan-carries-review-target",
        ),
        pytest.param(
            lambda: dataclasses.replace(
                _job(role="plan"), supersedes_job_id="JOB-122"
            ),
            id="plan-carries-superseded-job",
        ),
    ],
)
def test_malformed_or_foreign_lineage_is_refused(invalid_job) -> None:
    module = _identity_module()

    with pytest.raises(module.ExecutiveDelegationIdentityError):
        module.derive_delegation_identity(invalid_job())


def test_non_runtime_job_is_refused() -> None:
    module = _identity_module()

    with pytest.raises(module.ExecutiveDelegationIdentityError):
        module.derive_delegation_identity(object())
