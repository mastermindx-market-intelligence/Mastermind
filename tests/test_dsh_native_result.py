"""Closed native result evidence cannot become planner or completion authority."""
from dataclasses import replace
import copy

import pytest

from control_plane.native_conversation_result import (
    NativeConversationResultError, NativeConversationResultObservation,
    ROLE_RESULT_CONTRACT,
)
from control_plane.executive_orchestration_result import RESULT_SCHEMA
from control_plane.operator_harness_contract import TurnRef
from integrations.deepseek_harness.native_protocol import (
    NativeClaim, NativeResult, NativeTerminal,
)

TURN = TurnRef("turn-original", "epoch-original", "generation-original", "attempt-original")


def observed():
    claim = NativeClaim("ohf-op:native-turn", 2, "session-native", "message-native", 1, 5)
    terminal = NativeTerminal(claim.operation_id, claim.request_id, claim, 18, 3, 3)
    return NativeConversationResultObservation.from_native(
        TURN, claim.session_id, NativeResult("end_turn", terminal))


def test_native_result_roundtrip_preserves_actual_first_and_later_native_turns():
    value = observed()
    assert NativeConversationResultObservation.from_wire(value.to_wire()) == value
    assert value.provider_native_turn_id == "1"
    assert value.native_terminal.observed_last_turn == 3
    assert value.native_terminal.observed_turn_count == 3
    assert value.provider_turn_artifact_digest == NativeResult(
        value.stop_reason, value.native_terminal).artifact_digest
    value.require_turn(TURN)
    assert ROLE_RESULT_CONTRACT == RESULT_SCHEMA
    assert "transcript" not in value.to_wire()
    assert "complete_job_permitted" not in value.to_wire()


@pytest.mark.parametrize("key,value", [
    ("schema_version", ROLE_RESULT_CONTRACT),
    ("provider_session_id", "another-session"),
    ("provider_native_turn_id", "01"),
    ("provider_native_turn_id", 1),
    ("provider_turn_artifact_digest", "0" * 64),
    ("stop_reason", "completed"),
    ("attempt_id", ""),
    ("turn_id", True),
])
def test_substituted_native_result_refuses(key, value):
    raw = observed().to_wire()
    raw[key] = value
    with pytest.raises(NativeConversationResultError):
        NativeConversationResultObservation.from_wire(raw)


@pytest.mark.parametrize("edit", [
    lambda row: row.update(extra=True),
    lambda row: row.pop("native_terminal"),
    lambda row: row["native_claim"].update(nativeTurn=True),
    lambda row: row["native_claim"].update(requestId="2"),
    lambda row: row["native_terminal"].update(throughSeq=4),
    lambda row: row["native_terminal"].update(observedLastTurn=0),
    lambda row: row["native_terminal"].update(observedTurnCount=0),
    lambda row: row["native_terminal"].update(claim=None),
    lambda row: row["native_terminal"]["claim"].update(messageId="other-message"),
])
def test_closed_native_nested_observation_refuses_drift(edit):
    raw = copy.deepcopy(observed().to_wire())
    edit(raw)
    with pytest.raises(NativeConversationResultError):
        NativeConversationResultObservation.from_wire(raw)


def test_cancelled_turn_is_observed_without_releasing_or_completing_owners():
    value = observed()
    result = NativeResult("cancelled", value.native_terminal)
    cancelled = NativeConversationResultObservation.from_native(TURN, value.provider_session_id, result)
    assert cancelled.stop_reason == "cancelled"
    assert cancelled.provider_turn_artifact_digest != value.provider_turn_artifact_digest
    assert set(cancelled.to_wire()) == set(value.to_wire())


def test_unclaimed_terminal_cannot_become_acknowledged_native_result():
    result = NativeResult("end_turn", NativeTerminal("ohf-op:empty", 2, None, -1, None, 0))
    with pytest.raises(NativeConversationResultError):
        NativeConversationResultObservation.from_native(TURN, "session-native", result)


@pytest.mark.parametrize("field", ("turn_id", "attempt_id", "session_epoch_id", "process_generation_id"))
def test_original_ohf_identity_required(field):
    with pytest.raises(NativeConversationResultError):
        observed().require_turn(replace(TURN, **{field: "other-original-owner"}))


def test_native_runtime_event_reference_is_closed_and_confers_no_authority():
    from control_plane.native_conversation_result import NativeConversationResultRef
    ref = NativeConversationResultRef("ohf-native-result:turn-original", 12, "a"*64, "b"*64)
    assert NativeConversationResultRef.from_wire(ref.to_wire()) == ref
    for key, value in (("event_id", True), ("event_id", 0), ("event_id", 2**53),
                       ("command_id", "ohf-candidate:turn-original"),
                       ("command_id", "ohf-native-result:"),
                       ("seal_digest", "A"*64), ("observation_digest", 12),
                       ("schema_version", ROLE_RESULT_CONTRACT), ("authority", True)):
        raw = ref.to_wire()
        raw[key] = value
        with pytest.raises(NativeConversationResultError):
            NativeConversationResultRef.from_wire(raw)
