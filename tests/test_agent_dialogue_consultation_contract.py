from __future__ import annotations

import copy

import pytest

from common.agent_dialogue_consultation_contract import (
    _BINDING_ID_RE,
    CONSULTATION_PURPOSES,
    RECEIPT_KEYS,
    RESPONSE_BUDGET_MAXIMA,
    DuplicateClassification,
    build_consultation,
    canonical_consultation_json,
    classify_duplicate,
    consultation_semantic_fingerprint,
    validate_consultation,
)
from control_plane.operator_harness_contract import runtime_binding_id_for
from integrations.slack_agent_dialogue.contract import DialogueContractError


def worker(job: str = "JOB-200", attempt: str = "ATT-100") -> dict:
    return {
        "kind": "worker_attempt",
        "job_id": job,
        "attempt_id": attempt,
        "worker_id": f"codex-{attempt.lower()}",
    }


def raw_consultation(**overrides) -> dict:
    value = {
        "schema": "mastermind.agent_dialogue_consultation.v1",
        "message_key": "asd-consultation-0000000000000001",
        "consultation_id": "consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        "purpose": "QUESTION",
        "requester_actor_ref": worker(),
        "recipient_actor_ref": worker(job="JOB-200", attempt="ATT-200"),
        "recipient_peer_ref": "peer-6bdf4a6f9a664bbcf1a93d67a41ba51d",
        "recipient_binding": {
            "binding_id": runtime_binding_id_for("ATT-100", "EPOCH-0001"),
            "binding_generation": 1,
            "reasoning_surface": "codex",
        },
        "correlation": {
            "parent_fingerprint": "a" * 64,
            "request_message_key": "asd-consultation-0000000000000001",
            "consultation_id": "consult-6bdf4a6f9a664bbcf1a93d67a41ba51d",
            "requester_actor_digest": "b" * 64,
            "recipient_actor_digest": "c" * 64,
        },
        "question": "Which consultation fields are forbidden?",
        "answer": None,
        "evidence_refs": [
            "https://github.com/mastermindx-market-intelligence/Mastermind/blob/"
            "1111111111111111111111111111111111111111/common/x.py"
        ],
        "artifact_revisions": [
            {
                "repository": "mastermindx-market-intelligence/Mastermind",
                "path": "integrations/mastermind_company_mcp/schemas.py",
                "commit": "1" * 40,
                "content_sha256": "2" * 64,
            }
        ],
        "valid_until": "2026-09-14T00:00:00Z",
        "deadline_ms": 60000,
        "response_budget": {
            "max_answers": 1,
            "max_evidence_reads": 2,
            "max_forward_hops": 0,
            "max_payload_bytes": 32768,
        },
        "supersedes_message_key": None,
        "question_message_key": "asd-consultation-0000000000000001",
        "receipts": {key: None for key in RECEIPT_KEYS},
        "fingerprint": "",
    }
    value.update(overrides)
    return value


def test_consultation_contract_freezes_exact_closed_shape_and_semantics() -> None:
    frame = build_consultation(raw_consultation())

    assert frame["fingerprint"] == consultation_semantic_fingerprint(frame)
    assert canonical_consultation_json(frame)

    changed = copy.deepcopy(frame)
    changed["receipts"]["accepted_for_processing"] = {
        "evidence_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/pull/1",
        "observed_at": "2026-09-14T00:01:00Z",
    }
    frame["receipts"]["accepted_for_processing"] = {
        "evidence_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/pull/1",
        "observed_at": "2026-09-14T00:00:00Z",
    }
    expected = consultation_semantic_fingerprint(frame)
    assert consultation_semantic_fingerprint(changed) == expected


def test_binding_id_shape_matches_real_runtime_binding_producer() -> None:
    binding_id = runtime_binding_id_for("ATT-0001", "EPOCH-0001")

    assert binding_id.startswith("bind-")
    assert len(binding_id.removeprefix("bind-")) == 40
    assert _BINDING_ID_RE.fullmatch(binding_id) is not None
    assert _BINDING_ID_RE.fullmatch("bind-" + "a" * 32) is None
    assert _BINDING_ID_RE.fullmatch(binding_id + "0") is None


def test_consultation_refuses_32_hex_binding_alias() -> None:
    alias = raw_consultation()
    alias["recipient_binding"]["binding_id"] = "bind-" + "a" * 32

    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(alias)

    assert exc_info.value.code == "MESSAGE_INVALID"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"purpose": "RULING"}, "purpose"),
        ({"unknown": 1}, "unknown"),
        ({"requester_actor_ref": {"kind": "executive_surface"}}, "actor"),
        ({"recipient_binding": {**raw_consultation()["recipient_binding"], "host": "x"}}, "host"),
        ({"correlation": {**raw_consultation()["correlation"], "session_id": "x"}}, "session"),
        ({"question": "token xoxb-not-a-real-token-shaped-value"}, "secret"),
        ({"question": "x", "answer": {"text": "answer"}}, "answer"),
    ],
)
def test_consultation_rejects_unknown_privileged_or_secret_shapes(
    overrides: dict, field: str
) -> None:
    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(raw_consultation(**overrides))

    assert exc_info.value.code == "MESSAGE_INVALID"
    assert field


def test_consultation_enforces_purpose_and_frozen_budget_bounds() -> None:
    answer = {"text": "The closed field list and refusal list.", "evidence_refs": []}
    correction = raw_consultation(
        purpose="CORRECTION",
        question=None,
        answer=answer,
        supersedes_message_key="asd-consultation-0000000000000000",
    )
    assert validate_consultation(correction)["purpose"] == "CORRECTION"

    with pytest.raises(DialogueContractError):
        validate_consultation(
            raw_consultation(
                purpose="CORRECTION",
                question=None,
                answer=answer,
            )
        )
    for key, maximum in RESPONSE_BUDGET_MAXIMA.items():
        too_large = raw_consultation()
        too_large["response_budget"][key] = maximum + 1
        with pytest.raises(DialogueContractError):
            validate_consultation(too_large)


def test_consultation_refuses_budget_zero_answers_and_lying_fingerprint() -> None:
    zero_answers = raw_consultation()
    zero_answers["response_budget"]["max_answers"] = 0
    with pytest.raises(DialogueContractError) as budget_info:
        validate_consultation(zero_answers)
    assert budget_info.value.code == "MESSAGE_INVALID"

    lying = raw_consultation(fingerprint="a" * 64)
    with pytest.raises(DialogueContractError) as fingerprint_info:
        validate_consultation(lying)
    assert fingerprint_info.value.code == "MESSAGE_INVALID"
    built = build_consultation(raw_consultation())
    assert validate_consultation(built)["fingerprint"] == built["fingerprint"]


def test_duplicate_key_classifier_is_idempotent_only_for_equivalent_semantics() -> None:
    original = build_consultation(raw_consultation())
    replay = copy.deepcopy(original)
    replay["receipts"]["answer_available"] = {
        "evidence_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/pull/2",
        "observed_at": "2026-09-14T00:02:00Z",
    }
    original["receipts"]["answer_available"] = {
        "evidence_ref": "https://github.com/mastermindx-market-intelligence/Mastermind/pull/2",
        "observed_at": "2026-09-14T00:01:00Z",
    }
    conflict = copy.deepcopy(original)
    conflict["correlation"]["request_message_key"] = "asd-consultation-0000000000000002"
    conflict["message_key"] = "asd-consultation-0000000000000002"
    original["fingerprint"] = ""
    replay["fingerprint"] = ""
    conflict["fingerprint"] = ""

    assert classify_duplicate(original, replay) is DuplicateClassification.IDEMPOTENT
    assert classify_duplicate(original, conflict) is DuplicateClassification.CONFLICT
    assert set(CONSULTATION_PURPOSES) == {"QUESTION", "ANSWER", "NOTICE", "CORRECTION"}


def test_question_and_answer_have_explicit_request_reference_invariants() -> None:
    request = build_consultation(raw_consultation())
    assert request["correlation"]["request_message_key"] == request["message_key"]

    mismatched_question = copy.deepcopy(request)
    mismatched_question["correlation"]["request_message_key"] = "asd-consultation-foreignKey"
    with pytest.raises(DialogueContractError):
        validate_consultation(mismatched_question)

    answer = copy.deepcopy(request)
    answer["message_key"] = "asd-consultation-answer-0001"
    answer["purpose"] = "ANSWER"
    answer["question"] = None
    answer["answer"] = {"text": "closed answer", "evidence_refs": []}
    answer["question_message_key"] = request["message_key"]
    answer["correlation"]["request_message_key"] = request["message_key"]
    answer["fingerprint"] = ""
    assert validate_consultation(answer)["question_message_key"] == request["message_key"]

    foreign_reference = copy.deepcopy(answer)
    foreign_reference["question_message_key"] = "asd-consultation-foreignKey"
    with pytest.raises(DialogueContractError):
        validate_consultation(foreign_reference)

    reused_request_key = copy.deepcopy(answer)
    reused_request_key["message_key"] = request["message_key"]
    reused_request_key["question_message_key"] = request["message_key"]
    with pytest.raises(DialogueContractError):
        validate_consultation(reused_request_key)
