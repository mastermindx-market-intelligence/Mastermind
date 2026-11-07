"""Boundary regressions for the existing ref codec; synthetic, no external services."""
import pytest
from control_plane.workbench_attended_context import (
    AttendedContextError, MAX_REF_BYTES, OPTION_PURPOSE, _b64, _canonical,
)
from test_review_boundaries import setup, option, prepare
from test_workbench_attended_context import _caller

@pytest.mark.parametrize("raw_size", [12288, 12289], ids=["at-existing-limit", "over-existing-limit"])
def test_sign_respects_existing_encoded_component_limit(raw_size):
    _, _, broker = setup()
    payload = {"x": "a" * (raw_size - 8)}
    assert len(_canonical(payload)) == raw_size
    encoded_size = len(_b64(_canonical(payload)))
    assert MAX_REF_BYTES == 16384
    if encoded_size > MAX_REF_BYTES:
        with pytest.raises(AttendedContextError, match="reference is invalid"):
            broker._sign(OPTION_PURPOSE, payload)
    else:
        assert encoded_size == MAX_REF_BYTES
        ref = broker._sign(OPTION_PURPOSE, payload)
        assert broker._decode(OPTION_PURPOSE, ref) == payload

def test_surrogate_signature_has_closed_refusal():
    _, _, broker = setup()
    with pytest.raises(AttendedContextError, match="reference is invalid"):
        broker.resolve_context(_caller(), "AA.\ud800")

def test_supported_unicode_caller_identity_is_preserved():
    _, _, broker = setup()
    caller = _caller(resource="https://example.invalid/研究")
    prepared = prepare(broker, caller, option(broker, caller))
    assert broker.resolve_context(caller, prepared["workbench_context_ref"]).resource == caller.resource
