"""Real adapter normalization over a local fake App Server; no paid provider.

This file is disjoint from the active rich-worker candidate's tests. The three
normalizer/read methods were AST-identical to #1340 head 3b231e6 before this hook.
"""
from __future__ import annotations

import copy
import json

import pytest

from control_plane.codex_operator_adapter import CodexAdapterError
from control_plane.operator_harness_contract import TurnRef
from test_codex_operator_adapter import _make_harness, _op, _start


@pytest.fixture
def active(tmp_path):
    harness = _make_harness(tmp_path, fault_server=True,
                            extra_env={"OHF_FAKE_DELAY_COMPLETION": "1"})
    try:
        _, _, launch = _start(harness)
        turn = TurnRef("context-turn", harness.epoch.session_epoch_id,
                       harness.generation.process_generation_id, harness.epoch.attempt_id)
        start = harness.adapter.begin_turn(operation_id=_op("context-turn"), turn=turn,
                                          generation=harness.generation, launch=launch)
        assert start.acknowledged
        state = harness.adapter._state(harness.generation)
        yield harness.adapter, state, turn, start.provider_native_turn_id
    finally:
        for state in harness.adapter._generations.values():
            state.client.close()


def usage(state, native_turn):
    return {"method": "thread/tokenUsage/updated", "params": {
        "threadId": state.provider_session_id, "turnId": native_turn,
        "tokenUsage": {"last": {"inputTokens": 600, "outputTokens": 40,
            "cachedInputTokens": 450, "reasoningOutputTokens": 20, "totalTokens": 640},
            "total": {"totalTokens": 9_000_000}, "modelContextWindow": 1000}}}


def ingest(active, event, *, generation_only=False):
    adapter, state, turn, native = active
    adapter._ingest_turn_notifications(state, turn, [event], generation_only=generation_only)
    return state.events[-1]


def test_current_native_usage_reaches_existing_redacted_event(active):
    _, state, turn, native = active
    event = ingest(active, usage(state, native))
    assert event.turn_id == turn.turn_id
    assert event.payload_redacted["context_usage"]["last_request_tokens"] == 640
    assert event.payload_redacted["context_usage"]["context_window_tokens"] == 1000
    assert event.payload_redacted["context_usage"]["authority_effect"] == "NONE"


def test_usage_projection_keeps_provider_extra_text_out_of_retained_events(active):
    _, state, turn, native = active
    raw = usage(state, native)
    raw["params"]["private_prompt"] = "never publish this source"
    raw["params"]["tokenUsage"]["last"]["credential"] = "private credential"
    before = copy.deepcopy(raw)
    event = ingest(active, raw)
    assert "context_usage" in event.payload_redacted
    encoded = json.dumps(event.payload_redacted)
    assert "never publish" not in encoded and "private credential" not in encoded
    assert raw == before


@pytest.mark.parametrize("other_turn", ["other-turn", "", None, [], 123])
def test_foreign_turn_usage_cannot_change_current_context(active, other_turn):
    _, state, _, native = active
    raw = usage(state, native)
    raw["params"]["turnId"] = other_turn
    event = ingest(active, raw)
    assert "context_usage" not in event.payload_redacted


def test_foreign_thread_retains_existing_helper_admission_refusal(active):
    _, state, _, native = active
    raw = usage(state, native)
    raw["params"]["threadId"] = "foreign-thread"
    with pytest.raises(CodexAdapterError):
        ingest(active, raw)


def test_generation_only_observation_does_not_advance_a_closed_turn_context(active):
    _, state, _, native = active
    event = ingest(active, usage(state, native), generation_only=True)
    assert "context_usage" not in event.payload_redacted
    assert event.turn_id is None


def test_usage_after_exact_terminal_cannot_rewrite_that_turns_context(active):
    _, state, turn, native = active
    ingest(active, {"method": "turn/completed", "params": {
        "threadId": state.provider_session_id, "turn": {"id": native, "status": "completed"}}})
    event = ingest(active, usage(state, native))
    assert event.turn_id is None
    assert "context_usage" not in event.payload_redacted


def test_malformed_current_counts_are_unknown_without_failing_the_worker(active):
    _, state, turn, native = active
    raw = usage(state, native)
    raw["params"]["tokenUsage"]["last"]["totalTokens"] = True
    event = ingest(active, raw)
    assert event.turn_id == turn.turn_id
    assert event.payload_redacted["context_usage"]["state"] == "UNKNOWN"
    assert event.payload_redacted["context_usage"]["last_request_tokens"] is None

def compacted(state,native):
    return {"method":"thread/compacted","params":{
        "threadId":state.provider_session_id,"turnId":native,
        "nativeSecrets":"not for ledger"}}


def test_current_async_compaction_signal_stays_with_original_turn(active):
    _, state, turn, native=active
    event=ingest(active,compacted(state,native))
    assert event.turn_id==turn.turn_id
    assert event.payload_redacted["context_compaction"]["requires_remeasurement"] is True
    assert event.payload_redacted["context_compaction"]["checkpoint_committed"] is False
    assert "not for ledger" not in json.dumps(event.payload_redacted)


def test_foreign_compaction_turn_does_not_claim_current_completion(active):
    _,state,turn,native=active
    params=compacted(state,native)
    params["params"]["turnId"]="foreign-turn"
    event=ingest(active,params)
    assert "context_compaction" not in event.payload_redacted


def test_compaction_signal_after_terminal_turn_is_generation_only(active):
    _,state,turn,native=active
    ingest(active,{"method":"turn/completed","params":{
        "threadId":state.provider_session_id,"turn":{"id":native,"status":"completed"}}})
    event=ingest(active,compacted(state,native))
    assert event.turn_id is None
    assert "context_compaction" not in event.payload_redacted
