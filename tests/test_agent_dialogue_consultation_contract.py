from __future__ import annotations

import copy

import pytest

from common.agent_dialogue_consultation_contract import (
    _BINDING_ID_RE,
    CONSULTATION_PURPOSES,
    CONSULTATION_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    RECEIPT_KEYS,
    RESPONSE_BUDGET_MAXIMA,
    DuplicateClassification,
    build_consultation,
    canonical_consultation_json,
    classify_duplicate,
    consultation_schema_for_reasoning_surface,
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


_FROZEN_V1_FINGERPRINT = (
    "59f67fe58a9fca4ad427eea1a6f4ae0201afa392b98313e0bc720f3249e2fdd4"
)
_FROZEN_V1_CANONICAL_JSON = (
    '{"answer":null,"artifact_revisions":[{"commit":"1111111111111111111111111111111111'
    '111111","content_sha256":"2222222222222222222222222222222222222222222222222222222222'
    '222222","path":"integrations/mastermind_company_mcp/schemas.py","repository":'
    '"mastermindx-market-intelligence/Mastermind"}],"consultation_id":'
    '"consult-6bdf4a6f9a664bbcf1a93d67a41ba51d","correlation":{"consultation_id":'
    '"consult-6bdf4a6f9a664bbcf1a93d67a41ba51d","parent_fingerprint":'
    '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","recipient_actor_digest":'
    '"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","request_message_key":'
    '"asd-consultation-0000000000000001","requester_actor_digest":'
    '"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"deadline_ms":60000,'
    '"evidence_refs":["https://github.com/mastermindx-market-intelligence/Mastermind/blob/'
    '1111111111111111111111111111111111111111/common/x.py"],"fingerprint":'
    f'"{_FROZEN_V1_FINGERPRINT}","message_key":"asd-consultation-0000000000000001",'
    '"purpose":"QUESTION","question":"Which consultation fields are forbidden?",'
    '"question_message_key":"asd-consultation-0000000000000001","receipts":'
    '{"accepted_for_processing":null,"answer_available":null,"consumed_by_requester":null,'
    '"consumed_in_recipient_turn":null,"native_input_accepted":null,"recorded_on_carrier":null,'
    '"work_accepted":null},"recipient_actor_ref":{"attempt_id":"ATT-200","job_id":"JOB-200",'
    '"kind":"worker_attempt","worker_id":"codex-att-200"},"recipient_binding":'
    '{"binding_generation":1,"binding_id":"bind-92895df88c06f80da03073d5f201b0e740900aec",'
    '"reasoning_surface":"codex"},"recipient_peer_ref":"peer-6bdf4a6f9a664bbcf1a93d67a41ba51d",'
    '"requester_actor_ref":{"attempt_id":"ATT-100","job_id":"JOB-200","kind":"worker_attempt",'
    '"worker_id":"codex-att-100"},"response_budget":{"max_answers":1,"max_evidence_reads":2,'
    '"max_forward_hops":0,"max_payload_bytes":32768},"schema":'
    '"mastermind.agent_dialogue_consultation.v1","supersedes_message_key":null,"valid_until":'
    '"2026-09-14T00:00:00Z"}'
)


def test_v1_canonical_json_and_fingerprint_are_literally_frozen() -> None:
    frame = build_consultation(raw_consultation())

    assert canonical_consultation_json(frame) == _FROZEN_V1_CANONICAL_JSON
    assert frame["fingerprint"] == _FROZEN_V1_FINGERPRINT

    revalidated = validate_consultation(frame)
    assert canonical_consultation_json(revalidated) == _FROZEN_V1_CANONICAL_JSON
    assert revalidated["fingerprint"] == _FROZEN_V1_FINGERPRINT


def test_v1_accepts_codex_and_claude_but_rejects_grok_bot() -> None:
    for surface in ("codex", "claude"):
        frame = raw_consultation()
        frame["recipient_binding"]["reasoning_surface"] = surface
        assert validate_consultation(frame)["recipient_binding"]["reasoning_surface"] == surface

    grok = raw_consultation()
    grok["recipient_binding"]["reasoning_surface"] = "grok-bot"
    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(grok)
    assert exc_info.value.code == "MESSAGE_INVALID"


def test_v2_accepts_codex_claude_and_grok_bot() -> None:
    for surface in ("codex", "claude", "grok-bot"):
        frame = raw_consultation(schema=GROK_CONSULTATION_SCHEMA)
        frame["recipient_binding"]["reasoning_surface"] = surface
        assert validate_consultation(frame)["schema"] == GROK_CONSULTATION_SCHEMA


def test_v2_rejects_unknown_surface_and_both_versions_reject_unknown_schema() -> None:
    unknown_surface = raw_consultation(schema=GROK_CONSULTATION_SCHEMA)
    unknown_surface["recipient_binding"]["reasoning_surface"] = "gemini"
    with pytest.raises(DialogueContractError) as unknown_surface_info:
        validate_consultation(unknown_surface)
    assert unknown_surface_info.value.code == "MESSAGE_INVALID"

    for schema in (CONSULTATION_SCHEMA, GROK_CONSULTATION_SCHEMA):
        unknown_schema = raw_consultation(schema="mastermind.agent_dialogue_consultation.v3")
        with pytest.raises(DialogueContractError) as unknown_schema_info:
            validate_consultation(unknown_schema)
        assert unknown_schema_info.value.code == "MESSAGE_INVALID"
        assert schema


def test_trusted_surface_to_schema_selector_is_closed_and_literal() -> None:
    assert consultation_schema_for_reasoning_surface("codex") == CONSULTATION_SCHEMA
    assert consultation_schema_for_reasoning_surface("claude") == CONSULTATION_SCHEMA
    assert consultation_schema_for_reasoning_surface("grok-bot") == GROK_CONSULTATION_SCHEMA
    with pytest.raises(DialogueContractError) as exc_info:
        consultation_schema_for_reasoning_surface("gemini")
    assert exc_info.value.code == "MESSAGE_INVALID"
