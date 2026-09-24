from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as protocol
from tests.test_web_sol_runtime_binding_transport import (
    BOOT_ONE,
    BOOT_TWO,
    navigation_binding,
    lease,
)


WAKE_A = "WAKE-" + "a" * 32
WAKE_B = "WAKE-" + "b" * 32
WAKES = (WAKE_A, WAKE_B)
NUDGE = "NUDGE-" + "c" * 32


def _window() -> tuple[str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return (
        now.isoformat().replace("+00:00", "Z"),
        (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
    )


def _request(*, current_lease=None, nonce: str = "semantic-ack-nonce-00000001") -> dict:
    issued, expires = _window()
    current = current_lease or lease(BOOT_ONE)
    return client._request(
        navigation_binding(),
        action="OBSERVE_CONTINUATION_ACK",
        operation_key=f"web-sol-semantic-ack:{NUDGE}",
        issued_at=issued,
        expires_at=expires,
        nonce=nonce,
        turn_id=NUDGE,
        runtime_binding_lease=current,
        wake_obligation_ids=WAKES,
    )


def _observation() -> dict:
    return {
        "schema": protocol.PROBE_SCHEMA,
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


def _receipt(request: dict) -> dict:
    return {
        "schema": protocol.RECEIPT_SCHEMA,
        "binding_id": request["binding_id"],
        "conversation_fingerprint": request["conversation_fingerprint"],
        "binding_fingerprint": request["binding_fingerprint"],
        "action": request["action"],
        "operation_key": request["operation_key"],
        "nonce": request["nonce"],
        "status": "CONTINUATION_ACKNOWLEDGED",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        "acknowledged_obligation_ids": list(WAKES),
        "terminal_ack_trailer": True,
    }


def test_client_observation_is_read_only_exact_lease_bound(monkeypatch) -> None:
    current = lease(BOOT_ONE)
    sent: list[dict] = []

    def exchange(request, *, path, expected_instance_id, on_handshake=None, before_action=None):
        handshake = {"boot_nonce": BOOT_ONE}
        if on_handshake is not None:
            on_handshake(handshake)
        assert before_action is not None
        before_action(handshake)
        sent.append(request)
        return _receipt(request)

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    issued, expires = _window()
    result = client.observe_continuation_ack_via_extension(
        navigation_binding(),
        current,
        operation_key=f"web-sol-semantic-ack:{NUDGE}",
        nudge_id=NUDGE,
        wake_obligation_ids=WAKES,
        issued_at=issued,
        expires_at=expires,
        nonce="semantic-ack-nonce-00000001",
    )
    assert result["status"] == "CONTINUATION_ACKNOWLEDGED"
    assert len(sent) == 1
    assert sent[0]["action"] == "OBSERVE_CONTINUATION_ACK"
    assert sent[0]["turn_id"] == NUDGE
    assert sent[0]["wake_obligation_ids"] == list(WAKES)
    assert sent[0]["wake_obligation_digest"] == protocol.wake_obligation_digest(WAKES)
    assert sent[0]["runtime_binding_id"] == current.runtime_binding.binding_id
    assert sent[0]["runtime_binding_fingerprint"] == current.runtime_binding_fingerprint


def test_rotated_host_refuses_observation_before_action_frame(monkeypatch) -> None:
    stale = lease(BOOT_ONE)
    sent: list[dict] = []

    def exchange(request, *, path, expected_instance_id, on_handshake=None, before_action=None):
        handshake = {"boot_nonce": BOOT_TWO}
        if before_action is not None:
            before_action(handshake)
        sent.append(request)
        raise AssertionError("rotated host must refuse before write")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    issued, expires = _window()
    with pytest.raises(client.WebSolExtensionError) as excinfo:
        client.observe_continuation_ack_via_extension(
            navigation_binding(), stale,
            operation_key=f"web-sol-semantic-ack:{NUDGE}", nudge_id=NUDGE,
            wake_obligation_ids=WAKES, issued_at=issued, expires_at=expires,
            nonce="semantic-ack-nonce-00000001",
        )
    assert excinfo.value.code == "runtime_binding_stale"
    assert sent == []


def test_native_ack_observation_never_uses_submit_effect_ledger() -> None:
    current = lease(BOOT_ONE)
    native._SUBMIT_CONTINUATION_NONCES.clear()
    native._SUBMIT_CONTINUATION_TURNS.clear()
    writes: list[dict] = []

    for index in range(2):
        request = _request(
            current_lease=current,
            nonce=f"semantic-ack-nonce-0000000{index + 1}",
        )
        result = native.forward_request(
            request,
            write_chrome=writes.append,
            read_chrome=lambda _remaining, request=request: _receipt(request),
            timeout_seconds=1.0,
            expected_instance_id=current.target.adapter_instance_id,
            boot_nonce=BOOT_ONE,
        )
        assert result["status"] == "CONTINUATION_ACKNOWLEDGED"

    assert len(writes) == 2
    assert native._SUBMIT_CONTINUATION_NONCES == set()
    assert native._SUBMIT_CONTINUATION_TURNS == set()
