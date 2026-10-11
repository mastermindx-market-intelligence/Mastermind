from __future__ import annotations

import dataclasses

import pytest

from control_plane.coo_principal_envelope import (
    ACTOR,
    INTENT_SCHEMA,
    SEAT,
    CooPrincipalEnvelopeError,
    PrincipalAdmissionContext,
    derive_principal_envelope,
)


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
