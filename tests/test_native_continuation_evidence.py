"""Durable continuation reply is closed, redacted and stable across hydration."""
import dataclasses

import pytest

from control_plane.wake_ledger import NativeContinuationResponseEvidence, WakeLedgerError


def evidence(**changes):
    value = dict(
        target_attempt_id="ATT-"+"a"*32, process_generation_id="gen-one",
        binding_id="bind-abcdefgh", binding_generation=1, nudge_id="NUDGE-"+"b"*32,
        obligation_id="WAKE-"+"c"*32, operation_key="continue-one", request_message_key="asd-request-one",
        physical_source_sha256="1"*64, immutable_input_sha256="2"*64,
        provider_session_sha256="3"*64, provider_native_turn_sha256="4"*64,
        text="The bounded finding is confirmed.", next_step="Continue the original parent.")
    value.update(changes)
    return NativeContinuationResponseEvidence(**value)


def test_closed_round_trip_hides_text_and_raw_provider_fields():
    value = evidence()
    assert NativeContinuationResponseEvidence.from_dict(value.to_dict()) == value
    assert value.text not in repr(value)
    for key in ("provider_session_id", "provider_native_turn_id", "unknown"):
        raw = value.to_dict() | {key: "must refuse"}
        with pytest.raises(ValueError):
            NativeContinuationResponseEvidence.from_dict(raw)


@pytest.mark.parametrize("field,bad", [
    ("binding_generation", True), ("binding_generation", 0),
    ("obligation_id", "WAKE-bad"), ("target_attempt_id", "ATT-bad"),
    ("immutable_input_sha256", "A"*64), ("physical_source_sha256", "a"*63),
    ("text", ""), ("next_step", "x"*701), ("text", "bad\u0001"),
    ("text", "/Users/private/source.txt"),
    ("text", "019cafe0-1111-7222-8333-abcdefabcdef"),
    ("text", "sk-proj-"+"A"*70),
])
def test_durable_bad_values_refuse(field, bad):
    with pytest.raises(ValueError):
        evidence(**{field: bad})


def test_durable_history_does_not_change_when_environment_secrets_rotate(monkeypatch):
    value = evidence()
    raw = value.to_dict()
    monkeypatch.setenv("NEW_PROVIDER_API_KEY", value.text)
    assert NativeContinuationResponseEvidence.from_dict(raw) == value
