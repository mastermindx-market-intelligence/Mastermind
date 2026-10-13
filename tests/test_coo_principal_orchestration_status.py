from __future__ import annotations

import dataclasses

import pytest

from control_plane import ceo_intent
from control_plane.coo_principal_envelope import (
    PrincipalAdmissionContext,
    derive_principal_orchestration_envelope,
)
from control_plane.coo_principal_orchestration_status import (
    STATUS_SCHEMA,
    PrincipalOrchestrationNotFound,
    PrincipalOrchestrationStatusError,
    resolve_principal_orchestration,
)
from control_plane.executive_runtime import Runtime


WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"


def bundle(*, operation_key: str = "h4-status", objective: str = "Coordinate one governed episode."):
    return derive_principal_orchestration_envelope(
        {
            "operation_key": operation_key,
            "objective": objective,
            "department": "executive-infrastructure",
            "priority": 5,
            "workstream": WORK_REF,
            "business_impact": "routine",
        },
        context=PrincipalAdmissionContext(
            work_ref=WORK_REF,
            principal_binding_digest="1" * 64,
            mission_authority_ref="authority:coo-principal-v2",
            authority_generation_digest="2" * 64,
        ),
        grounding={
            "mastermind_sha": "a" * 40,
            "macro_sha": "b" * 40,
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
        },
    )


def test_resolve_principal_orchestration_reads_existing_root_without_effect(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle()
    root = runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
    )
    before_jobs = runtime.jobs.list_jobs()
    before_events = runtime.events.list_events()
    before_attempts = runtime.attempts.list_attempts()

    result = resolve_principal_orchestration(
        runtime,
        request_ref=source["request_ref"],
        work_ref=WORK_REF,
    )

    assert result["schema"] == STATUS_SCHEMA
    assert result["request_ref"] == source["request_ref"]
    assert result["intent_id"] == source["intent_id"]
    assert result["action_kind"] == "governed_orchestration"
    assert result["work_ref"] == WORK_REF
    assert result["job_id"] == root.job_id
    assert result["job_status"] == "QUEUED"
    assert result["accepted"] is True
    assert result["request_fingerprint"] == source["request_fingerprint"]
    assert result["principal_binding_digest"] == "1" * 64
    assert result["authority_generation_digest"] == "2" * 64
    assert result["has_dialogue_source"] is False
    assert len(result["bundle_digest"]) == 64
    assert len(result["orchestration_provenance_digest"]) == 64
    assert runtime.jobs.list_jobs() == before_jobs
    assert runtime.events.list_events() == before_events
    assert runtime.attempts.list_attempts() == before_attempts


def test_resolver_reports_host_dialogue_evidence_without_exposing_route(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    source = bundle(operation_key="h4-status-dialogue")
    dialogue = {
        "schema_version": "mastermind.executive_dialogue_source/v1",
        "work_ref": WORK_REF,
        "commission_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "7" * 40,
            "path": "docs/commissions/h4.md",
            "content_sha256": "8" * 64,
        },
        "watch_mode": "turn_watch_v1",
    }
    binding = {
        "eligible_quota_classes": ["codex-h4-work"],
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "cost_class": "small",
        "base_sha": "a" * 40,
        "routing_policy_version": "h4-routing-v1",
        "execution_profile_id": "sealed.worker.write.no-extensions.v1",
        "execution_profile_digest": "3" * 64,
        "capability_policy_version": "h4-capability-v1",
        "capability_policy_digest": "4" * 64,
        "operator_eligible_quota_classes": ["codex-h4-operator"],
        "operator_provider": "codex",
        "operator_model": "gpt-5.6-sol",
        "operator_effort": "xhigh",
        "operator_cost_class": "small",
        "operator_routing_policy_version": "h4-routing-v1",
        "operator_execution_profile_id": "operator.appserver.readonly.docs-mcp.native-helper.v1",
        "operator_execution_profile_digest": "5" * 64,
        "operator_capability_policy_version": "h4-capability-v1",
        "operator_capability_policy_digest": "4" * 64,
        "operator_harness_binary_digest": "6" * 64,
        "operator_harness_version": "h4-harness-v1",
        "operator_harness_armed": True,
        "host_execution_binding_version": "mastermind.host_execution_binding/v3",
        "work_placement_union": [
            {"provider_realm": "codex", "quota_class": "codex-h4-work"}
        ],
    }
    runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
        workspace_root=tmp_path / "workspaces",
        execution_binding=binding,
        dialogue_source=dialogue,
        require_dialogue_source=True,
    )

    result = resolve_principal_orchestration(
        runtime,
        request_ref=source["request_ref"],
        work_ref=WORK_REF,
    )

    assert result["has_dialogue_source"] is True
    assert "dialogue_source" not in result
    assert "provider" not in result
    assert "worktree" not in result
    assert "branch" not in result


def test_unknown_request_is_not_reinterpreted_as_permission_to_create(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle(operation_key="h4-missing")

    with pytest.raises(PrincipalOrchestrationNotFound, match="no durable root"):
        resolve_principal_orchestration(
            runtime,
            request_ref=source["request_ref"],
            work_ref=WORK_REF,
        )

    assert runtime.jobs.list_jobs() == []
    assert runtime.events.list_events() == []


def test_cross_kind_command_owner_is_not_reported_as_principal_orchestration(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle(operation_key="h4-cross-kind")
    runtime.jobs.create_job(
        "Existing bounded COO action.",
        command_id=ceo_intent.command_id_for(source["intent_id"]),
        requested_authorities=["READ"],
        attempt_limit=1,
    )

    with pytest.raises(PrincipalOrchestrationStatusError, match="Runtime lineage"):
        resolve_principal_orchestration(
            runtime,
            request_ref=source["request_ref"],
            work_ref=WORK_REF,
        )


@pytest.mark.parametrize(
    ("request_ref", "work_ref"),
    [
        ("bad", WORK_REF),
        ("req-coo-" + "a" * 32, "not-a-work-ref"),
    ],
)
def test_status_selector_is_closed(request_ref, work_ref, tmp_path):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(PrincipalOrchestrationStatusError):
        resolve_principal_orchestration(
            runtime,
            request_ref=request_ref,
            work_ref=work_ref,
        )


def test_workstream_mismatch_refuses_existing_root(tmp_path):
    runtime = Runtime.at(tmp_path)
    source = bundle(operation_key="h4-wrong-workstream")
    runtime.jobs.create_principal_orchestration_root(
        source,
        principal_admission_guard=lambda _value: None,
    )

    with pytest.raises(PrincipalOrchestrationStatusError, match="identity differs"):
        resolve_principal_orchestration(
            runtime,
            request_ref=source["request_ref"],
            work_ref="WS:OTHER",
        )


def test_status_module_has_no_write_or_retry_surface():
    import control_plane.coo_principal_orchestration_status as status

    names = set(status.__all__)
    assert names == {
        "STATUS_SCHEMA",
        "PrincipalOrchestrationNotFound",
        "PrincipalOrchestrationStatusError",
        "resolve_principal_orchestration",
    }
    source = open(status.__file__, encoding="utf-8").read()
    for forbidden in (
        "create_job(",
        "create_principal_orchestration_root(",
        "append_event(",
        "submit_intent(",
        "sleep(",
        "requests",
        "httpx",
        "subprocess",
    ):
        assert forbidden not in source
