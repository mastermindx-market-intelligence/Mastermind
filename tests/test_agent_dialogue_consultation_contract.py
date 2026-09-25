from __future__ import annotations

import copy
from pathlib import Path

import pytest

from common.agent_dialogue_consultation_contract import (
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


# --- IAC-P1-0: the consultation packet wire and its byte budget ---------------

import common.agent_dialogue_consultation_contract as consultation_contract
from common.agent_dialogue_contract import MAX_FRAME_BYTES as INCUMBENT_MAX_FRAME_BYTES
from common.agent_dialogue_contract_v2 import (
    MESSAGE_DISCRIMINATOR_V2,
    PARENT_DISCRIMINATOR_V2,
)

PACKET_LINE_OVERHEAD = len(
    consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1
) + 1


def packet_frame(
    purpose: str = "QUESTION",
    question: str | None = None,
    answer_text: str | None = None,
    **overrides,
) -> dict:
    if purpose == "ANSWER":
        value = raw_consultation(
            purpose="ANSWER",
            question=None,
            answer={"text": answer_text if answer_text is not None else "x", "evidence_refs": []},
            **overrides,
        )
    else:
        value = raw_consultation(
            purpose=purpose,
            question=question if question is not None else "packet?",
            answer=None,
            **overrides,
        )
    if value.get("schema") == CONSULTATION_SCHEMA:
        value.pop("question_message_key", None)
    return value


def worst_case_ceiling_frame() -> dict:
    """A ceiling-fitting frame whose variable content is astral (worst escape expansion)."""
    base = build_consultation(packet_frame())
    base_canonical = len(canonical_consultation_json(base).encode())
    old_question_bytes = len(base["question"].encode())
    emoji = "\U0001F600"
    pad = (
        INCUMBENT_MAX_FRAME_BYTES
        - PACKET_LINE_OVERHEAD
        - base_canonical
        + old_question_bytes
    ) // len(emoji.encode())
    frame = copy.deepcopy(base)
    frame["question"] = emoji * pad
    frame["fingerprint"] = consultation_semantic_fingerprint(frame)
    return frame


def test_packet_discriminator_is_not_a_prefix_of_either_v2_discriminator() -> None:
    packet_discriminator = consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1
    for incumbent_discriminator in (MESSAGE_DISCRIMINATOR_V2, PARENT_DISCRIMINATOR_V2):
        assert not incumbent_discriminator.startswith(packet_discriminator)
        assert not packet_discriminator.startswith(incumbent_discriminator)


def test_render_packet_emits_discriminator_newline_then_canonical_json() -> None:
    frame = build_consultation(packet_frame())
    rendered = consultation_contract.render_consultation_packet(frame)
    first_line, newline, remainder = rendered.partition("\n")
    assert first_line == consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1
    assert newline == "\n"
    assert remainder == canonical_consultation_json(frame)
    # The first line must equal the discriminator EXACTLY: a longer line is refused.
    tampered = consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1 + "X\n"
    assert consultation_contract.parse_consultation_packet(tampered + remainder) is None


def test_parse_packet_rejects_non_prefix_discriminator_in_both_directions() -> None:
    body = canonical_consultation_json(build_consultation(packet_frame()))
    assert consultation_contract.parse_consultation_packet(
        MESSAGE_DISCRIMINATOR_V2 + "\n" + body
    ) is None
    assert consultation_contract.parse_consultation_packet(
        PARENT_DISCRIMINATOR_V2 + "\n" + body
    ) is None
    assert consultation_contract.parse_consultation_packet(
        consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1 + "\n" + body
    ) is not None


def test_packet_purposes_are_question_and_answer_only() -> None:
    assert consultation_contract.CONSULTATION_PACKET_PURPOSES == frozenset(
        {"QUESTION", "ANSWER"}
    )
    question_packet = consultation_contract.render_consultation_packet(
        build_consultation(packet_frame("QUESTION"))
    )
    assert consultation_contract.parse_consultation_packet(question_packet)[
        "purpose"
    ] == "QUESTION"
    answer_packet = consultation_contract.render_consultation_packet(
        build_consultation(packet_frame("ANSWER"))
    )
    assert consultation_contract.parse_consultation_packet(answer_packet)[
        "purpose"
    ] == "ANSWER"
    notice_packet = consultation_contract.render_consultation_packet(
        build_consultation(packet_frame("NOTICE"))
    )
    assert consultation_contract.parse_consultation_packet(notice_packet) is None


def test_parse_packet_error_path_never_echoes_candidate_text() -> None:
    marker = "UNTRUSTED_BODY_MARKER"
    good = consultation_contract.render_consultation_packet(
        build_consultation(packet_frame(question=marker + "?"))
    )
    body = good.partition("\n")[2]
    assert marker in body
    tampered_discriminator = good.replace(
        consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1,
        "MMX/TAMPERED_PACKET_V1",
        1,
    )
    tampered_body = consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1 + "\n" + body[:-1]
    raised_messages: list[str] = []
    for candidate in (
        tampered_discriminator,
        tampered_body,
        "",
        consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1,
        consultation_contract.CONSULTATION_PACKET_DISCRIMINATOR_V1 + "\nnot json",
    ):
        try:
            parsed = consultation_contract.parse_consultation_packet(candidate)
        except Exception as exc:  # noqa: BLE001 - the contract is the absence of echo
            raised_messages.append(str(exc))
            parsed = None
        assert parsed is None
    assert marker not in "\n".join(raised_messages)


def test_packet_ceiling_is_the_imported_incumbent_max_frame_bytes() -> None:
    assert consultation_contract.MAX_FRAME_BYTES is INCUMBENT_MAX_FRAME_BYTES
    assert consultation_contract.MAX_FRAME_BYTES == INCUMBENT_MAX_FRAME_BYTES
    source = Path(consultation_contract.__file__).read_text(encoding="utf-8")
    assert "4500" not in source


def test_question_over_ceiling_is_a_typed_refusal_before_any_effect() -> None:
    oversized_question = "OVERSIZE" * 400
    frame = build_consultation(packet_frame(question=oversized_question))
    budget = consultation_contract.consultation_packet_budget(frame)
    assert budget.fits_wire_ceiling is False
    with pytest.raises(
        consultation_contract.ConsultationPacketOverCeiling
    ) as excinfo:
        consultation_contract.assert_packet_within_ceiling(frame)
    assert excinfo.value.code == "PACKET_OVER_CEILING"
    assert "OVERSIZE" not in str(excinfo.value)
    assert frame["question"] not in str(excinfo.value)


def test_escaped_request_line_bytes_stay_within_the_af_unix_request_limit() -> None:
    frame = worst_case_ceiling_frame()
    budget = consultation_contract.consultation_packet_budget(frame)
    assert budget.rendered_bytes <= INCUMBENT_MAX_FRAME_BYTES
    af_unix_request_limit = RESPONSE_BUDGET_MAXIMA["max_payload_bytes"]
    assert budget.escaped_request_line_bytes > budget.rendered_bytes
    assert budget.escaped_request_line_bytes < af_unix_request_limit


def test_no_truncation_chunking_or_alternate_carrier_symbol_exists() -> None:
    source = Path(consultation_contract.__file__).read_text(encoding="utf-8")
    for token in ("truncat", "chunk", "files_upload", "upload"):
        assert token not in source


def test_response_budget_max_payload_bytes_is_clamped_under_the_wire_ceiling() -> None:
    # A fully loaded ANSWER frame (envelope + its own narrative) is the overhead;
    # only the remainder of the wire ceiling may be declared as payload budget.
    lean_answer = build_consultation(packet_frame("ANSWER"))
    lean_bytes = len(
        consultation_contract.render_consultation_packet(lean_answer).encode()
    )
    filler = INCUMBENT_MAX_FRAME_BYTES - 150 - lean_bytes
    assert filler > 0
    loaded_answer = build_consultation(packet_frame("ANSWER", answer_text="x" * filler))
    overhead = len(
        consultation_contract.render_consultation_packet(loaded_answer).encode()
    )
    clamped = consultation_contract.clamp_response_budget(
        RESPONSE_BUDGET_MAXIMA, answer_frame_overhead_bytes=overhead
    )
    assert clamped is not RESPONSE_BUDGET_MAXIMA
    assert clamped["max_payload_bytes"] < INCUMBENT_MAX_FRAME_BYTES
    assert clamped["max_payload_bytes"] * 100 < RESPONSE_BUDGET_MAXIMA["max_payload_bytes"]
    assert clamped["max_answers"] == RESPONSE_BUDGET_MAXIMA["max_answers"]
    assert clamped["max_evidence_reads"] == RESPONSE_BUDGET_MAXIMA["max_evidence_reads"]
    assert clamped["max_forward_hops"] == RESPONSE_BUDGET_MAXIMA["max_forward_hops"]
    assert RESPONSE_BUDGET_MAXIMA["max_payload_bytes"] == 32768
    never_negative = consultation_contract.clamp_response_budget(
        RESPONSE_BUDGET_MAXIMA,
        answer_frame_overhead_bytes=INCUMBENT_MAX_FRAME_BYTES + 10,
    )
    assert never_negative["max_payload_bytes"] == 0


def test_worst_case_replies_page_plus_candidate_stays_under_max_response_bytes() -> None:
    candidate = worst_case_ceiling_frame()
    charge = consultation_contract.reply_entry_page_bytes(candidate)
    entry = real_page_entry_bytes(candidate)
    assert charge >= entry
    page_ceiling_bytes = 64 * 1024
    capacity = page_ceiling_bytes // charge
    assert capacity >= 1
    # The entries the page law admits, priced as real replies-page entries, still fit.
    assert capacity * entry <= page_ceiling_bytes
    full_page = capacity * charge
    assert full_page <= page_ceiling_bytes
    assert (
        consultation_contract.replies_page_has_room(
            full_page, candidate, page_ceiling_bytes=page_ceiling_bytes
        )
        is False
    )
    assert (
        consultation_contract.replies_page_has_room(
            full_page - charge,
            candidate,
            page_ceiling_bytes=page_ceiling_bytes,
        )
        is True
    )


# --- IAC-P1-B3: page capacity for the entry that carries a packet -------------

import json


def real_page_entry_bytes(frame: dict) -> int:
    """Bytes of the smallest replies-page entry carrying this frame.

    The incumbent parser accepts {"type","user","text","ts"} and nothing smaller;
    the frame reaches the reader escaped a second time, as a JSON string.
    """
    entry = {
        "type": "message",
        "user": "U061F7EUR",
        "text": consultation_contract.render_consultation_packet(frame),
        "ts": "1700000000.000100",
    }
    return len(
        json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def edited_page_entry_bytes(frame: dict) -> int:
    """Bytes of a message_changed entry, whose previous_message stores the text twice."""
    inner = {
        "type": "message",
        "user": "U061F7EUR",
        "text": consultation_contract.render_consultation_packet(frame),
        "ts": "1700000000.000100",
    }
    entry = {
        "type": "message",
        "subtype": "message_changed",
        "message": inner,
        "previous_message": inner,
    }
    return len(
        json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def test_reply_page_charge_is_never_below_a_minimal_real_entry() -> None:
    for frame in (worst_case_ceiling_frame(), build_consultation(packet_frame())):
        entry = real_page_entry_bytes(frame)
        charge = consultation_contract.reply_entry_page_bytes(frame)
        assert charge >= entry


def test_reply_page_charge_covers_an_edited_reply_stored_twice() -> None:
    for frame in (worst_case_ceiling_frame(), build_consultation(packet_frame())):
        entry = edited_page_entry_bytes(frame)
        charge = consultation_contract.reply_entry_page_bytes(frame)
        assert charge >= entry


def test_replies_page_refuses_a_candidate_that_a_real_page_cannot_hold() -> None:
    for frame in (worst_case_ceiling_frame(), build_consultation(packet_frame())):
        entry = real_page_entry_bytes(frame)
        assert (
            consultation_contract.replies_page_has_room(
                0, frame, page_ceiling_bytes=entry - 1
            )
            is False
        )


def test_replies_page_admitted_capacity_fits_the_read_ceiling() -> None:
    read_ceiling = 64 * 1024
    for frame in (worst_case_ceiling_frame(), build_consultation(packet_frame())):
        charge = consultation_contract.reply_entry_page_bytes(frame)
        entry = real_page_entry_bytes(frame)
        capacity = read_ceiling // charge
        assert capacity >= 1
        assert capacity * entry <= read_ceiling


def test_replies_page_still_admits_at_least_one_ceiling_frame() -> None:
    assert (
        consultation_contract.replies_page_has_room(
            0, worst_case_ceiling_frame(), page_ceiling_bytes=64 * 1024
        )
        is True
    )
