"""Claude Desktop live-session attention through the incumbent management owner."""
from __future__ import annotations

import asyncio
import socket

import pytest

from integrations.session_bridge.claude_native import (
    ClaudeManagedSession,
    ClaudeManagementSendReceipt,
    ClaudeNativeAttentionClient,
    ClaudeNativeTargetProjector,
    ClaudeSessionManagementAttentionAdapter,
)
from integrations.session_bridge.native_wire import AttentionReference
from integrations.session_bridge.schemas import BridgeError

SESSION = "f71c3451-edd7-4e88-93d8-1fe483eac293"
OTHER = "11111111-2222-4333-8444-555555555555"
REF = AttentionReference(
    operation_key="claude-management-op-001",
    message_key="asd-executive-request-001",
)


def session(
    session_id=SESSION,
    *,
    generation="gen-001",
    addressable=True,
    host_ref="m2studio",
):
    return ClaudeManagedSession(
        session_id=session_id,
        generation=generation,
        addressable=addressable,
        host_ref=host_ref,
    )


class Port:
    def __init__(self, sessions=None):
        self.sessions = list(sessions or [session()])
        self.current = {item.session_id: item for item in self.sessions}
        self.list_calls = 0
        self.get_calls = []
        self.send_calls = []
        self.reconcile_calls = []
        self.send_result = ClaudeManagementSendReceipt(state="accepted")
        self.send_error = None
        self.reconcile_result = None

    def list_sessions(self):
        self.list_calls += 1
        return list(self.sessions)

    def get_session(self, session_id):
        self.get_calls.append(session_id)
        return self.current.get(session_id)

    async def send_message(self, session_id, message):
        self.send_calls.append((session_id, message))
        if self.send_error is not None:
            raise self.send_error
        return self.send_result

    async def reconcile_message(self, session_id, operation_key):
        self.reconcile_calls.append((session_id, operation_key))
        return self.reconcile_result


def projector(port=None):
    return ClaudeNativeTargetProjector(port or Port())


def test_projector_represents_management_owned_session_without_resume_or_title():
    p = projector()
    targets = p.list_targets()
    assert len(targets) == 1
    target = targets[0]
    assert target.session_id == SESSION
    assert target.generation == "gen-001"
    assert target.target_ref.startswith("claude:")
    assert p.resolve(target.target_ref) == target


def test_public_projection_exposes_no_private_session_or_transport_coordinates():
    target = projector().list_targets()[0]
    public = target.public_projection()
    assert public == {
        "target_ref": target.target_ref,
        "kind": "claude",
        "host_ref": "m2studio",
        "generation": "gen-001",
        "addressable": True,
    }
    rendered = repr(public).lower()
    assert SESSION not in rendered
    assert "socket" not in rendered
    assert "token" not in rendered
    assert "title" not in rendered
    assert "path" not in rendered


def test_non_addressable_management_session_is_not_projected():
    assert ClaudeNativeTargetProjector(
        Port([session(addressable=False)])
    ).list_targets() == []


def test_resolve_refuses_management_generation_change():
    port = Port()
    p = ClaudeNativeTargetProjector(port)
    target = p.list_targets()[0]
    port.current[SESSION] = session(generation="gen-002")
    with pytest.raises(BridgeError) as error:
        p.resolve(target.target_ref)
    assert error.value.code == "native_target_stale"


def test_resolve_refuses_detached_or_revoked_target():
    port = Port()
    p = ClaudeNativeTargetProjector(port)
    target = p.list_targets()[0]
    port.current[SESSION] = session(addressable=False)
    with pytest.raises(BridgeError) as error:
        p.resolve(target.target_ref)
    assert error.value.code == "native_target_stale"


def test_exact_target_has_no_title_or_newest_session_fallback():
    port = Port([session(SESSION), session(OTHER, generation="gen-other")])
    p = ClaudeNativeTargetProjector(port)
    first = p.list_targets()[0]
    port.current.pop(first.session_id)
    with pytest.raises(BridgeError):
        p.resolve(first.target_ref)
    assert port.get_calls == [first.session_id]


def test_attention_uses_management_owner_once_and_never_opens_raw_socket(monkeypatch):
    port = Port()
    p = ClaudeNativeTargetProjector(port)
    target = p.list_targets()[0]
    client = ClaudeNativeAttentionClient(p, target=target)

    async def exercise():
        monkeypatch.setattr(
            socket,
            "socket",
            lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("direct Unix socket transport is forbidden")
            ),
        )
        return await client.deliver(REF)

    result = asyncio.run(exercise())
    assert len(port.send_calls) == 1
    session_id, notice = port.send_calls[0]
    assert session_id == SESSION
    assert REF.operation_key in notice and REF.message_key in notice
    assert "grants no permissions" in notice.lower()
    assert result == {
        "state": "ATTENTION_ACCEPTED",
        "target_ref": target.target_ref,
        "target_consumed": False,
        "parent_consumed": False,
        "reconciled": False,
    }
    assert port.reconcile_calls == []


def test_management_refusal_is_definitive_but_not_consumption():
    port = Port()
    port.send_result = ClaudeManagementSendReceipt(state="refused")
    p = ClaudeNativeTargetProjector(port)
    client = ClaudeNativeAttentionClient(p, target=p.list_targets()[0])
    with pytest.raises(BridgeError) as error:
        asyncio.run(client.deliver(REF))
    assert error.value.code == "native_refused"
    assert len(port.send_calls) == 1
    assert port.reconcile_calls == []


def test_lost_send_response_reconciles_same_owner_without_second_send():
    port = Port()
    port.send_error = RuntimeError("response lost")
    p = ClaudeNativeTargetProjector(port)
    client = ClaudeNativeAttentionClient(p, target=p.list_targets()[0])
    with pytest.raises(BridgeError) as error:
        asyncio.run(client.deliver(REF))
    assert error.value.code == "native_effect_unknown"
    assert len(port.send_calls) == 1
    assert port.reconcile_calls == [(SESSION, REF.operation_key)]


def test_lost_response_can_reconcile_accepted_without_resending():
    port = Port()
    port.send_error = RuntimeError("response lost")
    port.reconcile_result = ClaudeManagementSendReceipt(state="accepted")
    p = ClaudeNativeTargetProjector(port)
    target = p.list_targets()[0]
    client = ClaudeNativeAttentionClient(p, target=target)
    result = asyncio.run(client.deliver(REF))
    assert len(port.send_calls) == 1
    assert port.reconcile_calls == [(SESSION, REF.operation_key)]
    assert result == {
        "state": "ATTENTION_ACCEPTED",
        "target_ref": target.target_ref,
        "target_consumed": False,
        "parent_consumed": False,
        "reconciled": True,
    }


def test_reconcile_refusal_after_lost_response_remains_effect_unknown():
    port = Port()
    port.send_error = RuntimeError("response lost")
    port.reconcile_result = ClaudeManagementSendReceipt(state="refused")
    p = ClaudeNativeTargetProjector(port)
    client = ClaudeNativeAttentionClient(p, target=p.list_targets()[0])
    with pytest.raises(BridgeError) as error:
        asyncio.run(client.deliver(REF))
    assert error.value.code == "native_effect_unknown"
    assert len(port.send_calls) == 1
    assert len(port.reconcile_calls) == 1


def test_port_must_supply_full_management_owner_contract():
    class Incomplete:
        def list_sessions(self):
            return []

    with pytest.raises(TypeError):
        ClaudeNativeTargetProjector(Incomplete())


def test_duplicate_or_ambiguous_session_identity_fails_closed():
    duplicate = [
        session(SESSION, generation="gen-001"),
        session(SESSION, generation="gen-002"),
    ]
    with pytest.raises(BridgeError) as error:
        ClaudeNativeTargetProjector(Port(duplicate)).list_targets()
    assert error.value.code == "native_unavailable"


def test_target_ref_changes_with_management_generation():
    p1 = ClaudeNativeTargetProjector(Port([session(generation="gen-001")]))
    p2 = ClaudeNativeTargetProjector(Port([session(generation="gen-002")]))
    assert p1.list_targets()[0].target_ref != p2.list_targets()[0].target_ref


def test_client_has_no_retry_fallback_socket_or_session_store():
    port = Port()
    p = ClaudeNativeTargetProjector(port)
    client = ClaudeNativeAttentionClient(p, target=p.list_targets()[0])
    assert not hasattr(client, "retry")
    assert not hasattr(client, "fallback")
    assert not hasattr(client, "operation_store")
    assert not hasattr(client, "socket_path")


def test_management_attention_adapter_routes_only_exact_target_and_reference():
    port = Port()
    p = ClaudeNativeTargetProjector(port)
    target = p.list_targets()[0]
    adapter = ClaudeSessionManagementAttentionAdapter(p)

    result = asyncio.run(adapter(target.target_ref, REF))

    assert len(port.send_calls) == 1
    assert port.send_calls[0][0] == SESSION
    assert REF.operation_key in port.send_calls[0][1]
    assert REF.message_key in port.send_calls[0][1]
    assert result["state"] == "ATTENTION_ACCEPTED"
    assert result["target_ref"] == target.target_ref
    assert result["target_consumed"] is False
    assert result["parent_consumed"] is False


def test_management_attention_adapter_refuses_implicit_or_stale_target():
    port = Port()
    p = ClaudeNativeTargetProjector(port)
    adapter = ClaudeSessionManagementAttentionAdapter(p)

    with pytest.raises(BridgeError) as error:
        asyncio.run(adapter("claude:newest", REF))

    assert error.value.code == "native_target_stale"
    assert port.send_calls == []
