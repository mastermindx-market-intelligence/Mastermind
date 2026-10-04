from __future__ import annotations

import dataclasses

import pytest

from control_plane import ceo_intent
from control_plane.coo_principal_envelope import (
    ACTOR,
    INTENT_SCHEMA,
    ORCHESTRATION_INTENT_SCHEMA,
    SEAT,
    CooPrincipalEnvelopeError,
    PrincipalAdmissionContext,
    derive_principal_envelope,
    derive_principal_orchestration_envelope,
)
from control_plane.coo_principal_request import ORCHESTRATION_ACTION_KIND


WORK_REF = "WS:EXECUTIVE-CAPACITY-FABRIC"
D0 = "0" * 64
D1 = "1" * 64


def context(**changes):
    value = PrincipalAdmissionContext(
        work_ref=WORK_REF,
        principal_binding_digest=D0,
        mission_authority_ref="authority:coo-principal-v1",
        authority_generation_digest=D1,
    )
    return dataclasses.replace(value, **changes) if changes else value


def grounding(**changes):
    value = {
        "mastermind_sha": "1" * 40,
        "macro_sha": "2" * 40,
        "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
    }
    value.update(changes)
    return value


def research_request(**changes):
    value = {
        "operation_key": "claude-exec-integration",
        "objective": "Inspect current Executive integration and return grounded findings.",
        "department": "executive-infrastructure",
        "priority": 7,
        "execution_profile": "research_only",
        "workstream": WORK_REF,
    }
    value.update(changes)
    return value


def code_request(**changes):
    value = {
        "operation_key": "claude-exec-code",
        "objective": "Implement one bounded Executive integration slice.",
        "department": "executive-infrastructure",
        "priority": 8,
        "execution_profile": "bounded_code_change",
        "workstream": WORK_REF,
        "allowed_write_paths": ["control_plane/example.py"],
        "validation": {
            "pytest_targets": ["tests/test_example.py"],
            "git_diff_check": True,
        },
    }
    value.update(changes)
    return value


def derive(request=None, *, ctx=None, ground=None):
    return derive_principal_envelope(
        request or research_request(),
        context=ctx or context(),
        workspace_root="/tmp/mastermind-jobs",
        grounding=ground or grounding(),
    )


def orchestration_request(**changes):
    value = {
        "operation_key": "claude-exec-integration",
        "objective": "Coordinate one governed Executive orchestration episode.",
        "department": "executive-infrastructure",
        "priority": 7,
        "workstream": WORK_REF,
        "business_impact": "routine",
    }
    value.update(changes)
    return value


def derive_orchestration(request=None, *, ctx=None, ground=None):
    return derive_principal_orchestration_envelope(
        request or orchestration_request(),
        context=ctx or context(),
        grounding=ground or grounding(),
    )


def test_orchestration_envelope_is_role_correct_and_current_sink_inert():
    result = derive_orchestration()
    envelope = result["envelope"]
    assert envelope["schema"] == ORCHESTRATION_INTENT_SCHEMA
    assert envelope["action_kind"] == ORCHESTRATION_ACTION_KIND
    assert envelope["actor"] == ACTOR == "coo-principal"
    assert envelope["seat"] == SEAT == "coo"
    assert envelope["workstream"] == WORK_REF
    assert envelope["business_impact"] == "routine"
    assert envelope["principal_binding_digest"] == D0
    assert envelope["mission_authority_ref"] == "authority:coo-principal-v1"
    assert envelope["authority_generation_digest"] == D1
    assert "execution_contract" not in envelope
    assert "execution_profile" not in envelope
    assert "root_job_id" not in envelope
    assert "provider" not in envelope
    assert "account" not in envelope
    assert "host" not in envelope

    # H4-A cannot create a root through today's sink. The later reviewed
    # issuer/sink unit must add an explicit accepted discriminator.
    with pytest.raises(ceo_intent.CeoIntentError):
        ceo_intent.validate_intent(envelope)


def test_cross_kind_same_logical_operation_reuses_request_and_intent_identity():
    bounded = derive()
    orchestration = derive_orchestration()
    assert orchestration["request_ref"] == bounded["request_ref"]
    assert orchestration["intent_id"] == bounded["intent_id"]
    assert orchestration["envelope"]["schema"] != bounded["envelope"]["schema"]
    assert orchestration["action_kind"] == ORCHESTRATION_ACTION_KIND
    assert len(orchestration["request_fingerprint"]) == 64
    assert orchestration["request_fingerprint"] == orchestration["envelope"][
        "request_fingerprint"
    ]


def test_orchestration_semantic_change_keeps_identity_but_moves_action_fingerprint():
    first = derive_orchestration()
    changed = derive_orchestration(
        orchestration_request(
            objective="Changed orchestration semantics under the same operation.",
            priority=10,
            business_impact="material",
        )
    )
    assert changed["request_ref"] == first["request_ref"]
    assert changed["intent_id"] == first["intent_id"]
    assert changed["request_fingerprint"] != first["request_fingerprint"]
    assert changed["envelope"] != first["envelope"]


def test_orchestration_principal_generation_moves_envelope_not_business_fingerprint():
    first = derive_orchestration()
    moved = derive_orchestration(
        ctx=context(
            principal_binding_digest="a" * 64,
            mission_authority_ref="authority:coo-principal-v2",
            authority_generation_digest="b" * 64,
        )
    )
    assert moved["request_ref"] == first["request_ref"]
    assert moved["intent_id"] == first["intent_id"]
    assert moved["request_fingerprint"] == first["request_fingerprint"]
    assert moved["envelope"] != first["envelope"]


@pytest.mark.parametrize(
    "field",
    [
        "execution_profile",
        "attempt_limit",
        "allowed_write_paths",
        "validation",
        "root_job_id",
        "children",
        "plan",
        "budget",
        "branch",
        "worktree",
        "provider",
        "model",
        "account",
        "host",
        "realm",
        "release_class",
        "requested_authorities",
        "dispatch",
        "service",
        "session_id",
    ],
)
def test_orchestration_public_request_cannot_supply_execution_or_placement(field):
    request = orchestration_request()
    request[field] = "caller-value"
    with pytest.raises(CooPrincipalEnvelopeError, match="unexpected field"):
        derive_orchestration(request)


def test_orchestration_grounding_is_closed_and_exact():
    result = derive_orchestration()
    assert result["envelope"]["grounding"] == {
        "macro_sha": "2" * 40,
        "mastermind_sha": "1" * 40,
        "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
    }
    with pytest.raises(CooPrincipalEnvelopeError, match="unexpected field"):
        derive_orchestration(
            ground={**grounding(), "provider_session_id": "forbidden"}
        )


def test_orchestration_bundle_has_no_runtime_effect_or_acceptance_claim():
    result = derive_orchestration()
    assert set(result) == {
        "request_ref",
        "intent_id",
        "action_kind",
        "request_fingerprint",
        "normalized_request",
        "envelope",
    }
    forbidden = {
        "job_id",
        "status",
        "accepted",
        "duplicate",
        "dispatched",
        "created_at_ms",
        "worker_id",
        "attempt_id",
        "quota_class",
        "lease_token",
        "provider_session_id",
    }
    assert forbidden.isdisjoint(result)
    assert forbidden.isdisjoint(result["envelope"])


def test_envelope_is_distinct_from_ceo_identity_and_server_derives_coo_provenance():
    result = derive()
    envelope = result["envelope"]
    assert envelope["schema"] == INTENT_SCHEMA == "mastermind.executive_principal_intent.v1"
    assert envelope["actor"] == ACTOR == "coo-principal"
    assert envelope["seat"] == SEAT == "coo"
    assert not envelope["schema"].startswith("mastermind.ceo_intent.")
    assert envelope["workstream"] == WORK_REF
    assert envelope["principal_binding_digest"] == D0
    assert envelope["mission_authority_ref"] == "authority:coo-principal-v1"
    assert envelope["authority_generation_digest"] == D1


def test_research_root_reuses_existing_worker_profile_without_write_or_test_authority():
    envelope = derive()["envelope"]
    contract = envelope["execution_contract"]
    assert contract["requested_authorities"] == ["READ", "RESEARCH"]
    assert contract["authority_level"] == "A0"
    assert contract["attempt_limit"] == 2
    assert "allowed_write_paths" not in contract
    assert "validation_commands" not in contract
    assert contract["branch"].startswith("codex/coo-")
    assert contract["worktree"].startswith("/tmp/mastermind-jobs/coo-")


def test_bounded_code_root_reuses_existing_worker_profile_and_validation_derivation():
    envelope = derive(code_request())["envelope"]
    contract = envelope["execution_contract"]
    assert contract["requested_authorities"] == ["READ", "RUN_TESTS", "WRITE_BRANCH"]
    assert contract["allowed_write_paths"] == ["control_plane/example.py"]
    assert ["python3", "-m", "pytest", "-q", "tests/test_example.py"] in contract[
        "validation_commands"
    ]
    assert ["git", "diff", "--check"] in contract["validation_commands"]


@pytest.mark.parametrize(
    "field",
    [
        "actor",
        "seat",
        "schema",
        "principal_binding_digest",
        "mission_authority_ref",
        "authority_generation_digest",
        "requested_authorities",
        "authority_level",
        "branch",
        "worktree",
        "provider",
        "model",
        "account",
        "host",
        "realm",
        "release_class",
        "credential",
        "service",
        "dispatch",
        "session_id",
    ],
)
def test_public_request_cannot_supply_principal_or_placement_authority(field):
    request = research_request()
    request[field] = "caller-value"
    with pytest.raises(CooPrincipalEnvelopeError, match="unexpected field"):
        derive(request)


def test_durable_envelope_excludes_raw_oauth_provider_session_and_release_identity():
    envelope = derive()["envelope"]
    forbidden = {
        "subject_digest",
        "client_ref",
        "oauth",
        "jti",
        "expires_at",
        "provider",
        "model",
        "account",
        "host",
        "realm",
        "session_id",
        "provider_session_id",
        "release_class",
    }
    assert forbidden.isdisjoint(envelope)
    assert forbidden.isdisjoint(envelope["execution_contract"])


def test_same_logical_operation_keeps_identity_while_semantic_change_moves_envelope():
    first = derive()
    changed = derive(
        research_request(
            objective="Changed semantic objective under the same logical operation.",
            priority=9,
        )
    )
    assert first["request_ref"] == changed["request_ref"]
    assert first["intent_id"] == changed["intent_id"]
    assert first["envelope"] != changed["envelope"]


def test_immutable_principal_or_mission_identity_moves_envelope_not_operation_id():
    first = derive()
    changed_binding = derive(ctx=context(principal_binding_digest="a" * 64))
    changed_authority = derive(
        ctx=context(
            mission_authority_ref="authority:coo-principal-v2",
            authority_generation_digest="b" * 64,
        )
    )
    for changed in (changed_binding, changed_authority):
        assert changed["request_ref"] == first["request_ref"]
        assert changed["intent_id"] == first["intent_id"]
        assert changed["envelope"] != first["envelope"]


def test_different_workstream_is_a_different_operation_namespace():
    other_ref = "WS:OTHER"
    other = derive(
        research_request(workstream=other_ref),
        ctx=context(work_ref=other_ref),
    )
    first = derive()
    assert other["request_ref"] != first["request_ref"]
    assert other["intent_id"] != first["intent_id"]


def test_request_workstream_must_match_server_context_before_envelope_exists():
    with pytest.raises(CooPrincipalEnvelopeError, match="selected Mission Workspace"):
        derive(
            research_request(workstream="WS:OTHER"),
            ctx=context(),
        )


def test_grounding_is_closed_and_preserves_exact_source_claim():
    result = derive()
    assert result["envelope"]["grounding"] == {
        "macro_sha": "2" * 40,
        "mastermind_sha": "1" * 40,
        "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
    }

    with pytest.raises(CooPrincipalEnvelopeError, match="unexpected field"):
        derive(ground={**grounding(), "oauth_subject": "forbidden"})

    with pytest.raises(CooPrincipalEnvelopeError, match="40-character"):
        derive(ground=grounding(mastermind_sha="bad"))


def test_context_requires_only_immutable_secret_free_admission_identity():
    assert {field.name for field in dataclasses.fields(PrincipalAdmissionContext)} == {
        "work_ref",
        "principal_binding_digest",
        "mission_authority_ref",
        "authority_generation_digest",
    }
    with pytest.raises(CooPrincipalEnvelopeError, match="SHA-256"):
        context(principal_binding_digest="bad")
    with pytest.raises(CooPrincipalEnvelopeError, match="SHA-256"):
        context(authority_generation_digest="bad")


def test_envelope_bundle_has_no_effect_or_receipt_claim():
    result = derive()
    assert set(result) == {
        "request_ref",
        "intent_id",
        "normalized_request",
        "envelope",
    }
    for forbidden in ("job_id", "status", "accepted", "duplicate", "dispatched", "created_at_ms"):
        assert forbidden not in result
        assert forbidden not in result["envelope"]
