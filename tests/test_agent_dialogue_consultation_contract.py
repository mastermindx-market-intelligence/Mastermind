from __future__ import annotations

import copy
import json

import pytest

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_PACKET_DISCRIMINATOR,
    CONSULTATION_PACKET_MAX_BYTES,
    _BINDING_ID_RE,
    _PRODUCER_SCHEMA_BY_REASONING_SURFACE,
    CONSULTATION_PURPOSES,
    CONSULTATION_SCHEMA,
    CONSULTATION_SCHEMA_REASONING_SURFACES,
    CONSULTATION_V2_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
    RECEIPT_KEYS,
    RESPONSE_BUDGET_MAXIMA,
    DuplicateClassification,
    build_consultation,
    canonical_consultation_json,
    classify_duplicate,
    parse_consultation_packet,
    render_consultation_packet,
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
    if value["purpose"] == "QUESTION":
        value.pop("question_message_key", None)
    return value


def _valid_answer_frame() -> dict:
    question = build_consultation(raw_consultation())
    answer = copy.deepcopy(question)
    answer["schema"] = CONSULTATION_V2_SCHEMA
    answer["message_key"] = "asd-consultation-answer-0001"
    answer["purpose"] = "ANSWER"
    answer["question"] = None
    answer["answer"] = {"text": "closed answer", "evidence_refs": []}
    answer["question_message_key"] = question["message_key"]
    answer["correlation"]["request_message_key"] = question["message_key"]
    answer["fingerprint"] = ""
    return build_consultation(answer)


def _wire(document: dict) -> str:
    return (
        CONSULTATION_PACKET_DISCRIMINATOR
        + "\n"
        + json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def test_consultation_packet_round_trip_is_canonical_and_bounded() -> None:
    for frame in (
        build_consultation(raw_consultation()),
        _valid_answer_frame(),
    ):
        rendered = render_consultation_packet(frame)

        assert rendered.split("\n", 1)[0] == CONSULTATION_PACKET_DISCRIMINATOR
        assert len(rendered.encode("utf-8")) <= CONSULTATION_PACKET_MAX_BYTES
        assert parse_consultation_packet(rendered) == validate_consultation(frame)
        assert render_consultation_packet(parse_consultation_packet(rendered)) == rendered


def test_consultation_packet_discriminator_is_disjoint_from_lifecycle_frames() -> None:
    from common.agent_dialogue_contract_v2 import (
        MESSAGE_DISCRIMINATOR_V2,
        PARENT_DISCRIMINATOR_V2,
    )

    for incumbent in (MESSAGE_DISCRIMINATOR_V2, PARENT_DISCRIMINATOR_V2):
        assert not CONSULTATION_PACKET_DISCRIMINATOR.startswith(incumbent)
        assert not incumbent.startswith(CONSULTATION_PACKET_DISCRIMINATOR)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda text: text.replace(":", ": ", 1), id="whitespace"),
        pytest.param(lambda text: text + "\nextra", id="third-line"),
        pytest.param(
            lambda text: text.replace(
                CONSULTATION_PACKET_DISCRIMINATOR,
                "MMX/AGENT_DIALOGUE_CONSULTATION_PACKET_V0",
                1,
            ),
            id="wrong-discriminator",
        ),
    ],
)
def test_consultation_packet_parser_rejects_noncanonical_text(mutate) -> None:
    rendered = render_consultation_packet(build_consultation(raw_consultation()))

    with pytest.raises(DialogueContractError):
        parse_consultation_packet(mutate(rendered))


def test_consultation_packet_parser_rejects_invalid_utf8_and_nonfinite_json() -> None:
    with pytest.raises(DialogueContractError):
        parse_consultation_packet(b"\xff")

    with pytest.raises(DialogueContractError):
        parse_consultation_packet(
            CONSULTATION_PACKET_DISCRIMINATOR + "\n{\"value\":NaN}"
        )


def test_consultation_packet_parser_rejects_unknown_key_and_fingerprint_drift() -> None:
    frame = build_consultation(raw_consultation())
    unknown = copy.deepcopy(frame)
    unknown["unknown"] = 1
    with pytest.raises(DialogueContractError):
        parse_consultation_packet(_wire(unknown))

    drifted = copy.deepcopy(frame)
    drifted["fingerprint"] = "0" * 64
    with pytest.raises(DialogueContractError):
        parse_consultation_packet(_wire(drifted))


@pytest.mark.parametrize("purpose", ["NOTICE", "CORRECTION"])
def test_consultation_packet_wire_refuses_non_question_answer_purposes(
    purpose: str,
) -> None:
    frame = _valid_answer_frame() if purpose == "CORRECTION" else raw_consultation()
    frame = copy.deepcopy(frame)
    frame["purpose"] = purpose
    if purpose == "NOTICE":
        frame["schema"] = CONSULTATION_SCHEMA
        frame.pop("question_message_key", None)
        frame["question"] = "notice"
        frame["answer"] = None
        frame["supersedes_message_key"] = None
    else:
        frame["supersedes_message_key"] = "asd-consultation-answer-0000"
    frame["fingerprint"] = ""
    valid_non_wire_frame = build_consultation(frame)

    with pytest.raises(DialogueContractError):
        render_consultation_packet(valid_non_wire_frame)


@pytest.mark.parametrize(
    "question",
    [
        "token xoxb-not-a-real-token-shaped-value",
        "notify <@U12345678>",
    ],
    ids=["secret", "mention"],
)
def test_consultation_packet_wire_delegates_secret_and_mention_refusal(
    question: str,
) -> None:
    with pytest.raises(DialogueContractError):
        render_consultation_packet(raw_consultation(question=question))


def test_consultation_packet_wire_refuses_limit_plus_one_rendered_bytes() -> None:
    oversized = build_consultation(raw_consultation(question="x" * 8000))

    with pytest.raises(DialogueContractError) as exc_info:
        render_consultation_packet(oversized)

    assert exc_info.value.code == "FRAME_TOO_LARGE"


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


@pytest.mark.parametrize(
    "schema",
    [
        "mastermind.agent_dialogue_consultation.v99",
        "",
        None,
        1,
        ["mastermind.agent_dialogue_consultation.v1"],
    ],
    ids=["unreserved", "empty", "none", "int", "list"],
)
def test_validate_consultation_refuses_unreserved_or_non_string_schema(schema) -> None:
    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(raw_consultation(schema=schema))

    assert exc_info.value.code == "MESSAGE_INVALID"


def test_consultation_enforces_purpose_and_frozen_budget_bounds() -> None:
    answer = {"text": "The closed field list and refusal list.", "evidence_refs": []}
    correction = raw_consultation(
        message_key="asd-consultation-correction-0001",
        purpose="CORRECTION",
        question=None,
        answer=answer,
        supersedes_message_key="asd-consultation-answer-0001",
    )
    correction["schema"] = "mastermind.agent_dialogue_consultation.v2"
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
    answer["schema"] = "mastermind.agent_dialogue_consultation.v2"
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


def test_protected_v1_frame_and_fingerprint_remain_admitted_unchanged() -> None:
    protected = raw_consultation()
    built = build_consultation(protected)

    assert "question_message_key" not in built
    assert validate_consultation(built) is not built
    assert built["fingerprint"] == (
        "f63e2e0e2e64939b47e03fc4008115064bca4a51ef6cb02b8ab7025c2cdd19b1"
    )
    assert built["fingerprint"] == consultation_semantic_fingerprint(built)

    replay = copy.deepcopy(built)
    assert classify_duplicate(built, replay) is DuplicateClassification.IDEMPOTENT

    historical_answer = copy.deepcopy(protected)
    historical_answer.update(
        {
            "message_key": "asd-consultation-original-answer",
            "purpose": "ANSWER",
            "question": None,
            "answer": {"text": "closed answer", "evidence_refs": []},
            "fingerprint": "",
        }
    )
    historical_answer["correlation"]["request_message_key"] = historical_answer[
        "message_key"
    ]
    built_answer = build_consultation(historical_answer)
    assert "question_message_key" not in built_answer
    assert built_answer["fingerprint"] == (
        "b410fc5189d244c7b94ef74affff676a0c74703a76e9d87cf4efe4cc0b451afc"
    )

    foreign_request_link = copy.deepcopy(historical_answer)
    foreign_request_link["correlation"]["request_message_key"] = protected[
        "message_key"
    ]
    with pytest.raises(DialogueContractError):
        validate_consultation(foreign_request_link)

    legacy_correction = copy.deepcopy(protected)
    legacy_correction.update(
        {
            "purpose": "CORRECTION",
            "question": None,
            "answer": {"text": "legacy correction", "evidence_refs": []},
            "supersedes_message_key": protected["message_key"],
            "fingerprint": "",
        }
    )
    built_legacy_correction = build_consultation(legacy_correction)
    assert built_legacy_correction["schema"] == CONSULTATION_SCHEMA
    assert built_legacy_correction["supersedes_message_key"] == protected[
        "message_key"
    ]
    assert built_legacy_correction["fingerprint"] == (
        "e659d12d195ad987aebdff5eaf62dc6e68abf3d851490ddde46ae0e5695221a8"
    )

def test_v2_correction_message_identity_is_closed() -> None:
    request = build_consultation(raw_consultation())
    answer = copy.deepcopy(request)
    answer.update(
        {
            "schema": CONSULTATION_V2_SCHEMA,
            "message_key": "asd-consultation-answer-0001",
            "purpose": "ANSWER",
            "question": None,
            "answer": {"text": "closed answer", "evidence_refs": []},
            "question_message_key": request["message_key"],
            "fingerprint": "",
        }
    )
    answer["correlation"]["request_message_key"] = request["message_key"]
    answer = build_consultation(answer)

    correction = copy.deepcopy(answer)
    correction.update(
        {
            "message_key": "asd-consultation-correction-0001",
            "purpose": "CORRECTION",
            "supersedes_message_key": answer["message_key"],
            "answer": {"text": "corrected answer", "evidence_refs": []},
            "fingerprint": "",
        }
    )
    assert validate_consultation(correction)["purpose"] == "CORRECTION"

    reused_request_key = copy.deepcopy(correction)
    reused_request_key["message_key"] = request["message_key"]
    with pytest.raises(DialogueContractError):
        validate_consultation(reused_request_key)

    self_superseding = copy.deepcopy(correction)
    self_superseding["supersedes_message_key"] = correction["message_key"]
    with pytest.raises(DialogueContractError):
        validate_consultation(self_superseding)

    supersedes_request = copy.deepcopy(correction)
    supersedes_request["supersedes_message_key"] = request["message_key"]
    with pytest.raises(DialogueContractError):
        validate_consultation(supersedes_request)


def _grok_question() -> dict:
    frame = raw_consultation(schema=GROK_CONSULTATION_SCHEMA)
    frame["recipient_binding"]["reasoning_surface"] = "grok-bot"
    return frame


def test_v3_accepts_only_closed_grok_question_shape() -> None:
    built = build_consultation(_grok_question())

    assert built["schema"] == GROK_CONSULTATION_SCHEMA
    assert built["purpose"] == "QUESTION"
    assert built["question"]
    assert built["answer"] is None
    assert "question_message_key" not in built
    assert built["correlation"]["request_message_key"] == built["message_key"]
    assert built["recipient_binding"]["reasoning_surface"] == "grok-bot"
    assert CONSULTATION_SCHEMA_REASONING_SURFACES[GROK_CONSULTATION_SCHEMA] == frozenset(
        {"grok-bot"}
    )


@pytest.mark.parametrize("surface", ["codex", "claude", "gemini", "grok", ""])
def test_v3_refuses_every_non_grok_reasoning_surface(surface: str) -> None:
    frame = _grok_question()
    frame["recipient_binding"]["reasoning_surface"] = surface

    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(frame)

    assert exc_info.value.code == "MESSAGE_INVALID"


@pytest.mark.parametrize("purpose", ["ANSWER", "CORRECTION", "NOTICE"])
def test_v3_refuses_non_question_purposes(purpose: str) -> None:
    frame = _grok_question()
    frame["purpose"] = purpose
    if purpose in {"ANSWER", "CORRECTION"}:
        frame["question"] = None
        frame["answer"] = {"text": "{}", "evidence_refs": []}
    if purpose == "CORRECTION":
        frame["supersedes_message_key"] = "asd-consultation-answer-0001"

    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(frame)

    assert exc_info.value.code == "MESSAGE_INVALID"


def test_v3_refuses_v2_request_reference_shape() -> None:
    frame = _grok_question()
    frame["question_message_key"] = frame["message_key"]

    with pytest.raises(DialogueContractError) as exc_info:
        validate_consultation(frame)

    assert exc_info.value.code == "MESSAGE_INVALID"


def test_v1_and_v2_do_not_gain_grok_surface_authority() -> None:
    v1 = raw_consultation()
    v1["recipient_binding"]["reasoning_surface"] = "grok-bot"
    with pytest.raises(DialogueContractError):
        validate_consultation(v1)

    request = build_consultation(raw_consultation())
    v2 = copy.deepcopy(request)
    v2.update(
        {
            "schema": CONSULTATION_V2_SCHEMA,
            "message_key": "asd-consultation-answer-v2-surface",
            "purpose": "ANSWER",
            "question": None,
            "answer": {"text": "{}", "evidence_refs": []},
            "question_message_key": request["message_key"],
            "fingerprint": "",
        }
    )
    v2["recipient_binding"]["reasoning_surface"] = "grok-bot"
    with pytest.raises(DialogueContractError):
        validate_consultation(v2)


def test_surface_selector_reserves_v3_for_grok_without_widening_v2() -> None:
    assert dict(CONSULTATION_SCHEMA_REASONING_SURFACES) == {
        CONSULTATION_SCHEMA: frozenset({"codex", "claude"}),
        CONSULTATION_V2_SCHEMA: frozenset({"codex", "claude"}),
        GROK_CONSULTATION_SCHEMA: frozenset({"grok-bot"}),
    }
    assert set(_PRODUCER_SCHEMA_BY_REASONING_SURFACE) == {
        "codex",
        "claude",
        "grok-bot",
    }
    assert consultation_schema_for_reasoning_surface("codex") == CONSULTATION_SCHEMA
    assert consultation_schema_for_reasoning_surface("claude") == CONSULTATION_SCHEMA
    assert consultation_schema_for_reasoning_surface("grok-bot") == GROK_CONSULTATION_SCHEMA

    for unsupported in ("gemini", "grok", "", None, 1):
        with pytest.raises(DialogueContractError) as exc_info:
            consultation_schema_for_reasoning_surface(unsupported)
        assert exc_info.value.code == "MESSAGE_INVALID"


def test_v3_schema_identity_is_not_a_v1_fingerprint_alias() -> None:
    v1 = build_consultation(raw_consultation())
    v3 = build_consultation(_grok_question())

    assert v3["fingerprint"] == (
        "6ba1d8cf6e5e254dd54862a4199d3285dfdd5afd0fe61012a0128a2daa754695"
    )
    assert v3["fingerprint"] != v1["fingerprint"]
    assert classify_duplicate(v1, v3) is DuplicateClassification.CONFLICT
