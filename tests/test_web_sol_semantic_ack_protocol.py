from __future__ import annotations

import copy

import pytest

from integrations.chairman_surfaces import web_sol_protocol as wsp


WAKE_A = "WAKE-" + "a" * 32
WAKE_B = "WAKE-" + "b" * 32
NUDGE = "NUDGE-" + "c" * 32


def _request(**overrides) -> dict:
    ids = [WAKE_A, WAKE_B]
    value = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": "a" * 64,
        "binding_fingerprint": "b" * 64,
        "action": "OBSERVE_CONTINUATION_ACK",
        "operation_key": "web-sol-semantic-ack-observe-001",
        "issued_at": "2026-09-19T12:00:00Z",
        "expires_at": "2026-09-19T12:00:30Z",
        "nonce": "semantic-ack-nonce-00000001",
        "turn_id": NUDGE,
        "directive_digest": wsp.CONTINUATION_DIRECTIVE_DIGEST,
        "session_alias": "SOL-WEB-3",
        "runtime_binding_id": "bind-wsx-" + "d" * 48,
        "runtime_binding_generation": 4,
        "runtime_binding_fingerprint": "e" * 64,
        "wake_obligation_ids": ids,
        "wake_obligation_digest": wsp.wake_obligation_digest(ids),
    }
    value.update(overrides)
    return value


def _observation(**overrides) -> dict:
    value = {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }
    value.update(overrides)
    return value


def _receipt(**overrides) -> dict:
    request = _request()
    value = {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": request["binding_id"],
        "conversation_fingerprint": request["conversation_fingerprint"],
        "binding_fingerprint": request["binding_fingerprint"],
        "action": request["action"],
        "operation_key": request["operation_key"],
        "nonce": request["nonce"],
        "status": "CONTINUATION_ACKNOWLEDGED",
        "observed_at": "2026-09-19T12:00:10Z",
        "observation": _observation(),
        "turn_id": request["turn_id"],
        "directive_digest": request["directive_digest"],
        "session_alias": request["session_alias"],
        "runtime_binding_id": request["runtime_binding_id"],
        "runtime_binding_generation": request["runtime_binding_generation"],
        "runtime_binding_fingerprint": request["runtime_binding_fingerprint"],
        "wake_obligation_ids": request["wake_obligation_ids"],
        "wake_obligation_digest": request["wake_obligation_digest"],
        "provider_native_turn_id": "assistant-turn-current-001",
        "acknowledged_obligation_ids": request["wake_obligation_ids"],
        "terminal_ack_trailer": True,
    }
    value.update(overrides)
    return value


def test_semantic_ack_action_and_package_generation_are_explicit() -> None:
    assert wsp.WEB_SOL_PACKAGE_VERSION == "0.5.0"
    assert "OBSERVE_CONTINUATION_ACK" in {item.value for item in wsp.SurfaceAction}
    assert {
        "CONTINUATION_ACKNOWLEDGED",
        "CONTINUATION_ACK_PENDING",
        "CONTINUATION_ACK_REFUSED",
    }.issubset({item.value for item in wsp.ReceiptStatus})


def test_obligation_digest_is_deterministic_and_order_is_canonical() -> None:
    ids = [WAKE_A, WAKE_B]
    digest = wsp.wake_obligation_digest(ids)
    assert len(digest) == 64
    assert digest == wsp.wake_obligation_digest(tuple(ids))
    with pytest.raises(wsp.WebSolProtocolError, match="canonical"):
        wsp.wake_obligation_digest([WAKE_B, WAKE_A])
    with pytest.raises(wsp.WebSolProtocolError, match="canonical"):
        wsp.wake_obligation_digest([WAKE_A, WAKE_A])


def test_observe_request_round_trips_as_detached_closed_copy() -> None:
    request = _request()
    accepted = wsp.validate_request(request)
    assert accepted == request
    assert accepted is not request
    assert accepted["wake_obligation_ids"] is not request["wake_obligation_ids"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("wake_obligation_ids", [WAKE_B, WAKE_A]),
        ("wake_obligation_ids", [WAKE_A, WAKE_A]),
        ("wake_obligation_ids", ["WAKE-not-canonical"]),
        ("wake_obligation_digest", "f" * 64),
        ("turn_id", "not-a-nudge"),
    ],
)
def test_observe_request_refuses_wrong_or_noncanonical_semantic_identity(
    field: str,
    value: object,
) -> None:
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request(_request(**{field: value}))


def test_acknowledged_receipt_is_closed_and_never_carries_raw_content() -> None:
    receipt = _receipt()
    accepted = wsp.validate_receipt(receipt)
    assert accepted == receipt
    assert accepted is not receipt
    assert accepted["acknowledged_obligation_ids"] == [WAKE_A, WAKE_B]
    assert accepted["provider_native_turn_id"] == "assistant-turn-current-001"
    rendered = repr(accepted).lower()
    for forbidden in ("transcript", "output", "message_text", "raw_dom"):
        assert forbidden not in rendered


def test_acknowledged_receipt_does_not_derive_semantics_from_page_idle_state() -> None:
    receipt = _receipt(observation=_observation(generation_state="active"))
    assert wsp.validate_receipt(receipt) == receipt


def test_pending_receipt_carries_no_turn_or_ack_set() -> None:
    receipt = _receipt(
        status="CONTINUATION_ACK_PENDING",
        provider_native_turn_id=None,
        acknowledged_obligation_ids=[],
        terminal_ack_trailer=False,
        observation=_observation(generation_state="active"),
    )
    assert wsp.validate_receipt(receipt) == receipt


def test_refused_receipt_carries_no_turn_or_ack_set() -> None:
    receipt = _receipt(
        status="CONTINUATION_ACK_REFUSED",
        provider_native_turn_id=None,
        acknowledged_obligation_ids=[],
        terminal_ack_trailer=False,
    )
    assert wsp.validate_receipt(receipt) == receipt


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_native_turn_id": None},
        {"acknowledged_obligation_ids": [WAKE_A]},
        {"acknowledged_obligation_ids": [WAKE_B, WAKE_A]},
        {"terminal_ack_trailer": False},
        {"observation": _observation(provider_error_present=True)},
    ],
)
def test_acknowledged_receipt_refuses_missing_or_contradictory_semantics(
    overrides: dict,
) -> None:
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(_receipt(**copy.deepcopy(overrides)))
