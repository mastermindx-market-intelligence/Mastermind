"""W3: private retained plain-text input evidence (source-only milestone).

These tests prove one bounded extractor on ``CodexOperatorAdapter``: the
retained ORIGINAL single plain-text input of one acknowledged native turn is
compared against the immutable digest captured at ``begin_turn`` from the
trusted Executive rendering (``turn_input_loader`` plain string plus the
existing attempt-resource ``turn_prompt_suffix``). No model use, capsule ACK,
or authority is claimed or proven here; every refusal is the typed
``CONSUMPTION_EVIDENCE_UNAVAILABLE`` constant and never carries retained text.

Row shapes come from ``tests/fixtures/ohf_retained_input_source.json``, which
records the pinned upstream codex ``rust-v0.159.2`` schemas read read-only;
no native schema generator, binary, RPC, or provider is contacted.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from control_plane import codex_operator_adapter as adapter_module
from control_plane.codex_operator_adapter import (
    CodexAdapterError,
    CodexTurnInputEnvelope,
    RetainedPlainInputEvidence,
)
from control_plane.operator_harness_contract import (
    AdapterFailureClass,
    TurnRef,
)
from scripts.ohf.laboratory import PrivateRawTurnPage
from tests.test_codex_operator_adapter import _make_harness, _op, _start
from tests.test_codex_turn_evidence_scope import _begin, _turn

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOCUMENT = (
    REPO_ROOT / "tests" / "fixtures" / "ohf_retained_input_source.json"
)
PROMPT = "Rendered Executive instruction: retain this exact plain input — W3 中文 marker."
PINNED_VERSION = "codex-cli 0.159.2"
PINNED_BINARY = (
    "16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704"
)
UPSTREAM_COMMIT = "ff6aec96948b70d94983af2641a6b67c94faeff5"


def _source() -> dict:
    return json.loads(SOURCE_DOCUMENT.read_text(encoding="utf-8"))


@contextmanager
def _evidence_fixture(tmp_path, prompt):
    harness = _make_harness(tmp_path.resolve(), turn_input=prompt)
    try:
        _, _, launch = _start(harness)
        yield harness, launch
    finally:
        for state in harness.adapter._generations.values():
            state.client.close()


class _SuffixResource:
    """Minimal attempt-resource double exposing only the closed turn contract."""

    def turn_prompt_suffix(self) -> str:
        return "\n\nW3 RESOURCE SUFFIX CONTRACT (Executive-owned)"


def _pin_fixture_build(monkeypatch, harness) -> None:
    """Aim the production pin gate at the hermetic fixture build identity.

    The shipped constants stay byte-identical (see the provenance test); this
    re-points them at the exact version/digest the fake App Server harness
    actually attests so the full requested/attested/fresh-hash chain runs.
    """
    monkeypatch.setattr(
        adapter_module,
        "CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION",
        harness.requested.harness_version,
    )
    monkeypatch.setattr(
        adapter_module,
        "CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST",
        harness.adapter.binary_digest,
    )


def _text_user_input(text: str) -> dict:
    return {"type": "text", "text": text, "text_elements": []}


def _user_message(content, *, item_id="item-retained-input") -> dict:
    return {"type": "userMessage", "id": item_id, "content": content}


def _source_row(native_turn_id: str, *, items) -> dict:
    return {"id": native_turn_id, "items": items, "status": "completed"}


def _serve_pages(monkeypatch, state, pages):
    """Serve the private raw seam from hermetic pages; record traversal calls."""
    calls = []

    def private(*, thread_id, native_turn_id, cursor=None, timeout=15.0):
        assert thread_id == state.provider_session_id
        assert isinstance(native_turn_id, str) and native_turn_id
        assert native_turn_id in state.turns.values()
        index = 0 if cursor is None else int(cursor)
        assert 0 <= index < len(pages)
        calls.append(cursor)
        return PrivateRawTurnPage(json.loads(json.dumps(pages[index])), 256)

    monkeypatch.setattr(state.client, "request_raw_turn_page", private)
    return calls


def _forbid_ordinary_rpc(monkeypatch, state) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("evidence collection issued an ordinary provider call")

    monkeypatch.setattr(state.client, "request", forbidden)


def _assert_unavailable(failure, *, prompt=None) -> None:
    assert isinstance(failure.value, CodexAdapterError)
    assert str(failure.value) == adapter_module.CONSUMPTION_EVIDENCE_UNAVAILABLE
    if prompt is not None:
        assert prompt not in str(failure.value)
        assert prompt not in repr(failure.value)


# ---------------------------------------------------------------------------
# Provenance: the shipped pin is the exact production generation
# ---------------------------------------------------------------------------


def test_pinned_constants_are_the_documented_production_generation():
    document = _source()
    assert (
        adapter_module.CONSUMPTION_EVIDENCE_PINNED_HARNESS_VERSION
        == PINNED_VERSION
        == document["provenance"]["installed_binary_version"]
    )
    assert (
        adapter_module.CONSUMPTION_EVIDENCE_PINNED_BINARY_DIGEST
        == PINNED_BINARY
        == document["provenance"]["installed_binary_sha256"]
    )
    assert document["provenance"]["commit"] == UPSTREAM_COMMIT
    assert document["provenance"]["repository"] == "openai/codex"
    assert document["provenance"]["release_tag"] == "rust-v0.159.2"


# ---------------------------------------------------------------------------
# Positive: exact source-schema-shaped retained row accepts
# ---------------------------------------------------------------------------


def test_retained_plain_input_row_is_bound_to_the_begin_turn_rendering(
    tmp_path, monkeypatch
):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-plain-evidence")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        document = _source()
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(PROMPT)])],
        )
        assert set(document["turn"]["required"]) <= set(row)
        messages = [
            item for item in row["items"]
            if item["type"] == document["user_message_thread_item"]["type_value"]
        ]
        assert len(messages) == 1
        assert set(document["user_message_thread_item"]["required"]) <= set(
            messages[0]
        )
        pages = [
            {"data": [], "nextCursor": "1"},
            {"data": [row], "nextCursor": None},
        ]
        calls = _serve_pages(monkeypatch, state, pages)
        _forbid_ordinary_rpc(monkeypatch, state)
        evidence = harness.adapter.collect_retained_plain_text_evidence(turn)
        assert calls == [None, "1"], "the complete pagination must run to the end"
        assert isinstance(evidence, RetainedPlainInputEvidence)
        encoded = PROMPT.encode("utf-8")
        assert evidence.retained_input_digest == hashlib.sha256(encoded).hexdigest()
        assert evidence.retained_input_byte_length == len(encoded)
        assert evidence.provider_native_turn_id == started.provider_native_turn_id
        assert evidence.provider_session_id == state.provider_session_id
        assert evidence.turn_id == turn.turn_id
        assert evidence.attempt_id == turn.attempt_id == harness.epoch.attempt_id
        assert evidence.session_epoch_id == turn.session_epoch_id
        assert evidence.process_generation_id == turn.process_generation_id
        assert evidence.harness_version == harness.requested.harness_version
        assert evidence.harness_binary_digest == harness.adapter.binary_digest
        assert evidence.input_shape == adapter_module.CONSUMPTION_EVIDENCE_SHAPE
        assert evidence.scope == adapter_module.CONSUMPTION_EVIDENCE_SCOPE
        assert PROMPT not in repr(evidence) and PROMPT not in str(evidence)


def test_resource_suffix_is_part_of_the_proven_retained_input(
    tmp_path, monkeypatch
):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-suffix-evidence")
        state = harness.adapter._generations[turn.process_generation_id]
        state.resource = _SuffixResource()
        _pin_fixture_build(monkeypatch, harness)
        started = _begin(harness, launch, turn)
        rendered = PROMPT + state.resource.turn_prompt_suffix()
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(rendered)])],
        )
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        evidence = harness.adapter.collect_retained_plain_text_evidence(turn)
        encoded = rendered.encode("utf-8")
        assert evidence.retained_input_digest == hashlib.sha256(encoded).hexdigest()
        assert evidence.retained_input_byte_length == len(encoded)


# ---------------------------------------------------------------------------
# Honest scope: digest-and-binding only, no raw text, no caller attestation
# ---------------------------------------------------------------------------


def test_capture_is_digest_only_and_frozen_after_the_acknowledged_turn(
    tmp_path,
):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-capture-shape")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        capture = state.retained_plain_inputs[turn.turn_id]
        assert capture is not None
        assert capture.turn_id == turn.turn_id
        assert capture.native_turn_id == started.provider_native_turn_id
        assert capture.provider_session_id == state.provider_session_id
        encoded = PROMPT.encode("utf-8")
        assert capture.input_digest == hashlib.sha256(encoded).hexdigest()
        assert capture.input_byte_length == len(encoded)
        names = {field.name for field in dataclasses.fields(capture)}
        assert not names & {"text", "prompt", "body", "content", "input"}
        assert PROMPT not in repr(capture) and PROMPT not in str(capture)
        with pytest.raises(dataclasses.FrozenInstanceError):
            capture.input_digest = "0" * 64  # type: ignore[misc]


def test_extractor_accepts_no_caller_supplied_attestation(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-no-attestation")
        _begin(harness, launch, turn)
        _pin_fixture_build(monkeypatch, harness)
        with pytest.raises(TypeError):
            harness.adapter.collect_retained_plain_text_evidence(
                turn, expected_text=PROMPT  # type: ignore[call-arg]
            )
        with pytest.raises(TypeError):
            harness.adapter.collect_retained_plain_text_evidence(
                turn, build_attestation="attested"  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# Build and binding gates
# ---------------------------------------------------------------------------


def test_unknown_build_stays_unsupported(tmp_path):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-unknown-build")
        _begin(harness, launch, turn)
        # No pin re-pointing: the hermetic fixture build is not the pinned
        # production generation, so the extractor must refuse it outright.
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)


def test_fresh_binary_drift_is_unsupported(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-binary-drift")
        _begin(harness, launch, turn)
        _pin_fixture_build(monkeypatch, harness)
        monkeypatch.setattr(adapter_module, "_sha256_file", lambda _path: "a" * 64)
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("harness_version", "drifted/other"),
        ("harness_binary_digest", "b" * 64),
    ],
)
def test_attested_binding_drift_is_unsupported(tmp_path, monkeypatch, field, value):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, f"turn-binding-drift-{field}")
        _begin(harness, launch, turn)
        _pin_fixture_build(monkeypatch, harness)
        state = harness.adapter._generations[turn.process_generation_id]
        state.attestation = dataclasses.replace(state.attestation, **{field: value})
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)


def test_requested_binding_of_a_different_binary_is_unsupported(
    tmp_path, monkeypatch
):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-file-drift")
        _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        # The requested/attested binding now names a different binary image
        # than the one this adapter actually launched; the fresh hash of the
        # launched file can no longer satisfy that binding.
        other_binary = tmp_path / "codex-binary-other"
        other_binary.write_bytes(b"other harness bytes")
        drifted_digest = adapter_module._sha256_file(other_binary)
        state.requested = dataclasses.replace(
            state.requested, harness_binary_digest=drifted_digest
        )
        state.attestation = dataclasses.replace(
            state.attestation, harness_binary_digest=drifted_digest
        )
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(failure, prompt=PROMPT)


# ---------------------------------------------------------------------------
# Turn, generation, and capture binding
# ---------------------------------------------------------------------------


def test_wrong_attempt_generation_and_turn_are_refused(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-binding")
        _begin(harness, launch, turn)
        _pin_fixture_build(monkeypatch, harness)
        wrong_attempt = TurnRef(
            turn.turn_id, turn.session_epoch_id, turn.process_generation_id,
            "attempt-other",
        )
        with pytest.raises(CodexAdapterError) as attempt_failure:
            harness.adapter.collect_retained_plain_text_evidence(wrong_attempt)
        assert (
            attempt_failure.value.failure_class
            is AdapterFailureClass.VALIDATION_FAILURE
        )
        foreign_generation = TurnRef(
            turn.turn_id, turn.session_epoch_id, "gen-other", turn.attempt_id
        )
        with pytest.raises(CodexAdapterError) as generation_failure:
            harness.adapter.collect_retained_plain_text_evidence(foreign_generation)
        assert (
            generation_failure.value.failure_class
            is AdapterFailureClass.SESSION_MISSING
        )
        absent = TurnRef(
            "turn-absent", turn.session_epoch_id, turn.process_generation_id,
            turn.attempt_id,
        )
        with pytest.raises(CodexAdapterError) as native_failure:
            harness.adapter.collect_retained_plain_text_evidence(absent)
        assert native_failure.value.failure_class is AdapterFailureClass.SESSION_MISSING


def test_wrong_native_turn_or_session_capture_binding_is_unavailable(
    tmp_path, monkeypatch
):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-capture-binding")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(PROMPT)])],
        )
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        state.retained_plain_inputs[turn.turn_id] = dataclasses.replace(
            state.retained_plain_inputs[turn.turn_id], native_turn_id="native-other"
        )
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)
        state.retained_plain_inputs[turn.turn_id] = dataclasses.replace(
            state.retained_plain_inputs[turn.turn_id],
            native_turn_id=started.provider_native_turn_id,
            provider_session_id="thread-other",
        )
        with pytest.raises(CodexAdapterError) as session_failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(session_failure, prompt=PROMPT)


def test_absent_capture_is_unavailable(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-no-capture")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(PROMPT)])],
        )
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        state.retained_plain_inputs.pop(turn.turn_id, None)
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)


def test_non_plain_turn_input_never_captures(tmp_path):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-envelope")
        state = harness.adapter._generations[turn.process_generation_id]
        harness.adapter.turn_input_loader = lambda _turn: CodexTurnInputEnvelope(
            text="skill envelope", skills=()
        )
        with pytest.raises(CodexAdapterError):
            harness.adapter.begin_turn(
                operation_id=_op(turn.turn_id), turn=turn,
                generation=harness.generation, launch=launch,
            )
        assert turn.turn_id not in state.retained_plain_inputs


# ---------------------------------------------------------------------------
# Retained-row shape refusals
# ---------------------------------------------------------------------------


def _final_agent_message() -> dict:
    return {
        "type": "agentMessage",
        "text": "final",
        "content": [{"type": "text", "text": "final"}],
    }


@pytest.mark.parametrize("items", [
    pytest.param([_user_message([_text_user_input(" \n\t ")])], id="whitespace-only"),
    pytest.param([_user_message([_text_user_input("")])], id="empty-text"),
    pytest.param(
        [_user_message([
            _text_user_input(PROMPT),
            _text_user_input("second segment"),
        ])],
        id="multisegment",
    ),
    pytest.param(
        [_user_message([
            {"type": "skill", "name": "probe", "path": "/skills/probe"},
        ])],
        id="skill-segment",
    ),
    pytest.param(
        [_user_message([
            {"type": "text", "text": PROMPT, "text_elements": [{"byteRange": [0, 4]}]},
        ])],
        id="text-elements",
    ),
    pytest.param(
        [_user_message([{"type": "image", "url": "https://example.invalid/image"}])],
        id="non-text-segment",
    ),
    pytest.param([_final_agent_message()], id="missing-user-message"),
    pytest.param(
        [
            _user_message([_text_user_input(PROMPT)]),
            _user_message(
                [_text_user_input(PROMPT)], item_id="item-retained-input-duplicate"
            ),
        ],
        id="duplicate-user-message",
    ),
])
def test_unsupported_retained_rows_stay_unavailable(tmp_path, monkeypatch, items):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-row-shape")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        row = _source_row(started.provider_native_turn_id, items=items)
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)


def test_retained_text_drift_from_the_captured_rendering_is_refused(
    tmp_path, monkeypatch
):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-suffix-drift")
        state = harness.adapter._generations[turn.process_generation_id]
        state.resource = _SuffixResource()
        _pin_fixture_build(monkeypatch, harness)
        started = _begin(harness, launch, turn)
        # The retained row lost the resource suffix that the trusted rendering
        # appended before the acknowledged native turn.
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(PROMPT)])],
        )
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            failure.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        _assert_unavailable(failure, prompt=PROMPT)
        rendered = PROMPT + state.resource.turn_prompt_suffix()
        drifted_row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(rendered + " drift")])],
        )
        _serve_pages(
            monkeypatch, state, [{"data": [drifted_row], "nextCursor": None}]
        )
        with pytest.raises(CodexAdapterError) as drift_failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(drift_failure, prompt=PROMPT)


def test_non_strict_utf8_retained_text_is_unavailable(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-utf8")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        surrogate_text = "broken \ud800 surrogate"
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([{"type": "text", "text": surrogate_text}])],
        )
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(failure, prompt=PROMPT)
        assert surrogate_text not in str(failure.value)


# ---------------------------------------------------------------------------
# Traversal: the complete bounded seam stays typed
# ---------------------------------------------------------------------------


def test_missing_duplicate_and_paging_failures_stay_typed(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-paging")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        row = _source_row(
            started.provider_native_turn_id,
            items=[_user_message([_text_user_input(PROMPT)])],
        )
        calls = _serve_pages(monkeypatch, state, [{"data": [], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as missing:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            missing.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        assert missing.value.effect_unknown is True
        assert calls == [None]
        foreign = {"id": "native-foreign", "items": [], "status": "completed"}
        calls = _serve_pages(
            monkeypatch,
            state,
            [
                {"data": [foreign], "nextCursor": "1"},
                {"data": [json.loads(json.dumps(row))], "nextCursor": "2"},
                {"data": [json.loads(json.dumps(row))], "nextCursor": None},
            ],
        )
        with pytest.raises(CodexAdapterError) as ambiguous:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            ambiguous.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        assert calls == [None, "1", "2"], "every page must be consumed"
        calls = _serve_pages(
            monkeypatch,
            state,
            [
                {"data": [json.loads(json.dumps(row))], "nextCursor": "1"},
                {"data": [], "nextCursor": []},
            ],
        )
        with pytest.raises(CodexAdapterError) as malformed:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert (
            malformed.value.failure_class
            is AdapterFailureClass.MODEL_OR_WORK_RESULT_FAILURE
        )
        assert malformed.value.effect_unknown is True

# Parent integration regressions: evidence must survive later valid turns while
# refusing bindings or the qualified build that change during private readback.
def test_prior_plain_turn_evidence_survives_a_later_plain_turn(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        first = _turn(harness, "turn-first-retained")
        started = _begin(harness, launch, first)
        state = harness.adapter._generations[first.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        later = _turn(harness, "turn-later-retained")
        _begin(harness, launch, later)
        row = _source_row(started.provider_native_turn_id,
                          items=[_user_message([_text_user_input(PROMPT)])])
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        result = harness.adapter.collect_retained_plain_text_evidence(first)
        assert result.provider_native_turn_id == started.provider_native_turn_id
        assert result.turn_id == first.turn_id


def test_binary_drift_during_private_readback_refuses(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-build-read-drift")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        changed = [False]
        original_hash = adapter_module._sha256_file
        monkeypatch.setattr(adapter_module, "_sha256_file",
                            lambda path: "a" * 64 if changed[0] else original_hash(path))
        row = _source_row(started.provider_native_turn_id,
                          items=[_user_message([_text_user_input(PROMPT)])])
        def page(**_kwargs):
            changed[0] = True
            return PrivateRawTurnPage({"data": [row], "nextCursor": None}, 256)
        monkeypatch.setattr(state.client, "request_raw_turn_page", page)
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(failure, prompt=PROMPT)


@pytest.mark.parametrize("drift", ["native_turn", "attempt", "generation_replaced", "generation_number"])
def test_binding_drift_during_private_readback_refuses(tmp_path, monkeypatch, drift):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-state-read-drift")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        row = _source_row(started.provider_native_turn_id,
                          items=[_user_message([_text_user_input(PROMPT)])])
        def page(**_kwargs):
            if drift == "native_turn":
                state.turns[turn.turn_id] = "replacement-native-turn"
            elif drift == "attempt":
                state.epoch = dataclasses.replace(state.epoch, attempt_id="attempt-other")
            elif drift == "generation_number":
                state.generation = dataclasses.replace(
                    state.generation, generation_number=state.generation.generation_number + 1
                )
            else:
                harness.adapter._generations[turn.process_generation_id] = dataclasses.replace(state)
            return PrivateRawTurnPage({"data": [row], "nextCursor": None}, 256)
        monkeypatch.setattr(state.client, "request_raw_turn_page", page)
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        assert PROMPT not in str(failure.value)


@pytest.mark.parametrize("malformed", ["missing_item_id", "summary_view", "malformed_item"])
def test_nonfull_or_malformed_retained_row_refuses(tmp_path, monkeypatch, malformed):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-partial-row")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        message = _user_message([_text_user_input(PROMPT)])
        row = _source_row(started.provider_native_turn_id, items=[message])
        if malformed == "missing_item_id":
            del message["id"]
        elif malformed == "summary_view":
            row["itemsView"] = "summary"
        else:
            row["items"].append(None)
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(failure, prompt=PROMPT)


def test_provider_session_drift_during_start_cannot_rebind_capture(tmp_path, monkeypatch):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        turn = _turn(harness, "turn-start-session-drift")
        state = harness.adapter._generations[turn.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        original_request = state.client.request
        def request(method, *args, **kwargs):
            response = original_request(method, *args, **kwargs)
            if method == "turn/start":
                state.provider_session_id = "replacement-provider-session"
            return response
        monkeypatch.setattr(state.client, "request", request)
        # An acknowledgement may arrive without queued notifications. The
        # input capture must bind the request session in that case too.
        monkeypatch.setattr(state.client, "drain_notifications", lambda: [])
        started = _begin(harness, launch, turn)
        row = _source_row(started.provider_native_turn_id,
                          items=[_user_message([_text_user_input(PROMPT)])])
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(turn)
        _assert_unavailable(failure, prompt=PROMPT)

@pytest.mark.parametrize("identity", ["attempt", "epoch", "generation"])
def test_capture_cannot_be_spliced_into_rebound_generation(tmp_path, monkeypatch, identity):
    with _evidence_fixture(tmp_path, PROMPT) as (harness, launch):
        original = _turn(harness, "turn-rebound-identity")
        started = _begin(harness, launch, original)
        state = harness.adapter._generations[original.process_generation_id]
        _pin_fixture_build(monkeypatch, harness)
        if identity == "attempt":
            state.epoch = dataclasses.replace(state.epoch, attempt_id="attempt-other")
            rebound = dataclasses.replace(original, attempt_id="attempt-other")
        elif identity == "epoch":
            state.epoch = dataclasses.replace(state.epoch, session_epoch_id="epoch-other")
            rebound = dataclasses.replace(original, session_epoch_id="epoch-other")
        else:
            state.generation = dataclasses.replace(state.generation, process_generation_id="gen-other")
            harness.adapter._generations["gen-other"] = state
            rebound = dataclasses.replace(original, process_generation_id="gen-other")
        row = _source_row(started.provider_native_turn_id,
                          items=[_user_message([_text_user_input(PROMPT)])])
        _serve_pages(monkeypatch, state, [{"data": [row], "nextCursor": None}])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_retained_plain_text_evidence(rebound)
        _assert_unavailable(failure, prompt=PROMPT)
