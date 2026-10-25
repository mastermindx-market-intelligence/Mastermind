"""Typed wire association is data; a forged association is not issuance."""

import copy
import pytest

from common.agent_dialogue_contract import DialogueContractError
from common.agent_dialogue_contract_v2 import validate_decision_request_body_v2


def source_ref():
    return {
        "repository": "mastermindx-market-intelligence/macro",
        "commit": "a" * 40,
        "path": "agentos/workstreams/WS-EXAMPLE.md",
        "content_sha256": "b" * 64,
    }


def association():
    return {
        "schema": "mastermind.product_acceptance_association.v1",
        "issuance_ref": "runtime-product-acceptance:" + "c" * 32,
        "root_job_id": "JOB-root",
        "issuer_job_id": "JOB-live-operator",
        "issuer_attempt_id": "ATT-live",
        "subject_job_id": "JOB-completed",
        "subject_attempt_id": "ATT-completed",
        "subject_result_envelope_digest": "d" * 64,
        "subject_role_result_digest": "e" * 64,
        "reviewer_job_id": "JOB-review",
        "reviewer_attempt_id": "ATT-review",
        "reviewer_result_envelope_digest": "f" * 64,
        "original_intent_ref": source_ref(),
        "current_intent_ref": source_ref(),
        "proof_contract_ref": source_ref(),
        "current_intent_revision": "r2-initial-v1",
        "acceptance_basis_digest": "1" * 64,
        "criteria_objective_sha256": "2" * 64,
    }


def generic_body():
    return {
        "question": "Should the scoped result be accepted?",
        "outcome_impact": "One exact revision is selected.",
        "options": [
            {
                "id": "opt-accept",
                "summary": "Accept this revision",
                "consequence": "Complete this outcome",
                "disposition": "CONTINUE",
                "authority_effect": "NONE",
            }
        ],
        "recommendation": "opt-accept",
        "work_paused": True,
    }


def test_generic_body_keeps_exact_legacy_meaning():
    body = generic_body()
    assert validate_decision_request_body_v2(body) == body


def test_association_is_detached_and_has_no_accepted_flag():
    body = {**generic_body(), "acceptance_request": association()}
    result = validate_decision_request_body_v2(body)
    assert result == body
    result["acceptance_request"]["current_intent_ref"]["path"] = "changed.md"
    assert body["acceptance_request"]["current_intent_ref"]["path"] != "changed.md"
    assert "accepted" not in result["acceptance_request"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("accepted", True),
        ("issuer_job_id", "../forged"),
        ("subject_result_envelope_digest", "public-digest"),
        ("issuance_ref", "runtime-event:1"),
        ("current_intent_revision", True),
        ("proof_contract_ref", {"role": "ceo"}),
    ],
)
def test_malformed_or_verdict_bearing_association_is_rejected(field, value):
    value_body = {**generic_body(), "acceptance_request": copy.deepcopy(association())}
    value_body["acceptance_request"][field] = value
    with pytest.raises(DialogueContractError):
        validate_decision_request_body_v2(value_body)


def test_missing_issuance_reference_cannot_be_inferred_from_accept_option():
    body = {**generic_body(), "acceptance_request": association()}
    del body["acceptance_request"]["issuance_ref"]
    with pytest.raises(DialogueContractError):
        validate_decision_request_body_v2(body)


def typed_message():
    from common.agent_dialogue_contract_v2 import build_message_v2

    return build_message_v2(
        {
            "schema": "mastermind.agent_dialogue.v2",
            "message_key": "asd-acceptance-12345678",
            "message_type": "DECISION_REQUEST",
            "work_ref": "WS:EXAMPLE",
            "commission_ref": source_ref(),
            "session_ref": "asd-session-example1234",
            "actor_ref": {
                "kind": "worker_attempt",
                "job_id": "JOB-live-operator",
                "attempt_id": "ATT-live",
                "worker_id": "WORKER-live",
            },
            "reply_to_message_key": None,
            "applies_to": {
                "kind": "executive_attempt",
                "job_id": "JOB-live-operator",
                "attempt_id": "ATT-live",
                "worker_id": "WORKER-live",
            },
            "summary": "Decision on this scoped result.",
            "body": {**generic_body(), "acceptance_request": association()},
            "evidence_refs": [],
            "requires_response": True,
            "created_at": "2026-10-13T08:00:00Z",
        }
    )


def test_actual_v2_frame_roundtrip_retains_the_typed_association():
    from common.agent_dialogue_contract_v2 import (
        parse_message_frame_v2,
        render_message_v2,
    )

    message = typed_message()
    assert parse_message_frame_v2(render_message_v2(message)) == message


@pytest.mark.parametrize(
    "field",
    [
        "current_intent_revision",
        "subject_result_envelope_digest",
        "reviewer_result_envelope_digest",
    ],
)
def test_association_revision_is_part_of_exact_message_semantics(field):
    from common.agent_dialogue_contract_v2 import validate_message_v2

    message = typed_message()
    message["body"]["acceptance_request"][field] = "9" * 64
    with pytest.raises(DialogueContractError, match="FINGERPRINT_MISMATCH"):
        validate_message_v2(message)
