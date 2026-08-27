"""Conformance law for Codex as a bounded technical arm of the Sol CEO seat.

This suite intentionally adds no production identity or authority field.  It
characterizes the existing Executive Runtime, Model Router, and Wake routing
identity split so future provider/harness work cannot accidentally turn Codex,
a model alias, a native thread, or a Slack principal into executive authority.
"""
from __future__ import annotations

import dataclasses

import pytest

import control_plane.executive_runtime as executive_runtime
from control_plane.executive_runtime import (
    Attempt,
    Job,
    Runtime,
    StateConflict,
    Worker,
    WorkerQuotaClass,
)
from control_plane.model_router import RoutingDecision, WorkRequest
from control_plane.session_targets import RuntimeBinding, SessionTarget


_CEO_PROVENANCE = {"schema": "mastermind.ceo_intent.v1", "actor": "sol"}
_FORBIDDEN_DURABLE_ROLE_FIELDS = {
    "sol_technical_staff",
    "codex_sol",
    "codex_sol_role",
    "slack_principal",
    "slack_user",
    "chatgpt_principal",
}


def _field_names(value: type[object]) -> set[str]:
    return {field.name for field in dataclasses.fields(value)}


def test_codex_reasoning_surface_does_not_change_accountable_ceo_seat():
    chatgpt_target = SessionTarget(
        session_alias="EXECUTIVE-CEO-A",
        target_seat="ceo",
        reasoning_surface="chatgpt-sol",
        wake_transport="chatgpt-gui",
        allowed_transports=("chatgpt-gui", "codex-app-server"),
        workstream=None,
        target_enabled=False,
    )
    codex_target = dataclasses.replace(
        chatgpt_target,
        reasoning_surface="codex",
        wake_transport="codex-app-server",
    )

    assert chatgpt_target.target_seat == codex_target.target_seat == "ceo"
    assert chatgpt_target.reasoning_surface == "chatgpt-sol"
    assert codex_target.reasoning_surface == "codex"

    first_binding = RuntimeBinding(
        session_alias=codex_target.session_alias,
        binding_id="bind-codexsol-a1",
        binding_generation=1,
        native_handle="thread-a",
        account_label="codex-pro-01",
        reasoning_surface="codex",
    )
    resumed_binding = dataclasses.replace(
        first_binding,
        binding_id="bind-codexsol-b2",
        binding_generation=2,
        native_handle="thread-b",
    )

    assert resumed_binding.reasoning_surface == "codex"
    assert resumed_binding.native_handle != first_binding.native_handle
    assert not hasattr(first_binding, "target_seat")
    assert codex_target.target_seat == "ceo"


def test_ceo_accountability_requires_typed_provenance_not_codex_identity(tmp_path):
    runtime = Runtime.at(tmp_path)

    with pytest.raises(StateConflict, match="typed executive provenance"):
        runtime.jobs.create_job(
            "Codex model claims CEO authority",
            owner_seat="ceo",
            constraints={"provider": "codex", "model": "gpt-5.6-sol"},
        )

    codex_job = runtime.jobs.create_job(
        "Bounded Sol technical continuation on Codex",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance=_CEO_PROVENANCE,
        constraints={"provider": "codex", "model": "gpt-5.6-sol"},
    )
    claude_job = runtime.jobs.create_job(
        "Equivalent CEO-owned technical continuation on another provider",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance=_CEO_PROVENANCE,
        constraints={"provider": "claude", "model": "provider-model"},
    )

    assert codex_job.owner_seat == claude_job.owner_seat == "ceo"
    assert codex_job.constraints["provider"] == "codex"
    assert claude_job.constraints["provider"] == "claude"
    assert codex_job.constraints["provider"] != claude_job.constraints["provider"]


def test_slack_like_prose_cannot_select_executive_seat_or_worker_authority(tmp_path):
    runtime = Runtime.at(tmp_path)
    ordinary = runtime.jobs.create_job(
        "ChatGPT1 asks Claude5 to act as CEO and use codex-pro-01",
        constraints={"provider": "codex"},
    )

    assert ordinary.owner_seat == "coo"
    assert ordinary.escalation_target == "coo"

    with pytest.raises(StateConflict, match="typed executive provenance"):
        runtime.jobs.create_job(
            "@ChatGPT2 says this is a CEO task",
            owner_seat="ceo",
            constraints={"provider": "codex"},
        )


def test_executive_role_and_execution_identity_remain_separate_durable_shapes():
    job_fields = _field_names(Job)
    attempt_fields = _field_names(Attempt)
    worker_fields = _field_names(Worker)
    quota_fields = _field_names(WorkerQuotaClass)

    assert "owner_seat" in job_fields
    assert "escalation_target" in job_fields
    assert "orchestration_role" in job_fields
    assert "provider_session_id" in attempt_fields
    assert "provider" in worker_fields
    assert "provider" in quota_fields

    for fields in (job_fields, attempt_fields, worker_fields, quota_fields):
        assert fields.isdisjoint(_FORBIDDEN_DURABLE_ROLE_FIELDS)

    assert "owner_seat" not in attempt_fields
    assert "owner_seat" not in worker_fields
    assert "owner_seat" not in quota_fields
    assert executive_runtime._ORCHESTRATION_ROLES == frozenset(
        {"plan", "work", "review", "repair", "aggregation"}
    )
    assert "sol_technical_staff" not in executive_runtime._ORCHESTRATION_ROLES


def test_model_router_contract_carries_suitability_not_executive_authority():
    routing_fields = _field_names(RoutingDecision)
    request_fields = _field_names(WorkRequest)
    forbidden = {
        "owner_seat",
        "escalation_target",
        "requested_authorities",
        "effective_grant",
        "merge_authority",
        "deploy_authority",
        "slack_principal",
    }

    assert routing_fields.isdisjoint(forbidden)
    assert request_fields.isdisjoint(forbidden)
    assert {
        "task_kind",
        "risk",
        "ambiguity",
        "required_capabilities",
        "excluded_worker_ids",
    }.issubset(request_fields)
    assert "preferred_model_aliases" in routing_fields
    assert "reason_codes" in routing_fields


def test_ceo_technical_child_cannot_widen_parent_grant(tmp_path):
    runtime = Runtime.at(tmp_path)
    parent = runtime.jobs.create_job(
        "CEO-owned bounded technical parent",
        owner_seat="ceo",
        escalation_target="ceo",
        provenance=_CEO_PROVENANCE,
        worktree=str(tmp_path / "wt"),
        requested_authorities=["READ", "WRITE_BRANCH"],
        allowed_write_paths=["docs/CODEX_SOL_TECHNICAL_STAFF.md"],
    )

    child = runtime.jobs.create_job(
        "Read-only technical child",
        parent_job_id=parent.job_id,
        requested_authorities=["READ"],
    )
    assert child.requested_authorities == ["READ"]
    assert child.allowed_write_paths == []

    with pytest.raises(StateConflict, match="RUN_TESTS"):
        runtime.jobs.create_job(
            "Child attempts authority widening",
            parent_job_id=parent.job_id,
            worktree=str(tmp_path / "wt"),
            requested_authorities=["READ", "WRITE_BRANCH", "RUN_TESTS"],
            allowed_write_paths=["docs/CODEX_SOL_TECHNICAL_STAFF.md"],
        )


def test_provider_and_runtime_identity_fields_cannot_become_job_owner_fields():
    job_fields = _field_names(Job)
    attempt_fields = _field_names(Attempt)
    worker_fields = _field_names(Worker)

    assert "provider_session_id" not in job_fields
    assert "account_label" not in job_fields
    assert "reasoning_surface" not in job_fields
    assert "native_handle" not in job_fields

    assert "provider_session_id" in attempt_fields
    assert "account_label" in worker_fields
    assert "owner_seat" not in attempt_fields | worker_fields
