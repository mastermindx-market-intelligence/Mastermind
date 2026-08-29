"""RED-first contract for explicit Wake PR3 provider dispatcher composition."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    UnsupportedWakeDispatcher,
    WakeDispatcher,
    WakeDispatchError,
)
from control_plane.wake_transport import (
    WAKE_TRANSPORT_DESCRIPTORS,
    WakeTransportDescriptor,
)
from integrations.executive_wake.registry import WakeDispatcherRegistry


@dataclasses.dataclass
class _FakeDispatcher:
    transport_id: str = "codex-app-server"
    calls: int = 0

    async def nudge(self, wake):
        self.calls += 1
        return TransportReceipt(
            outcome=TransportOutcome.ACCEPTED,
            reason_code="accepted",
            created_at="2026-08-27T09:00:00Z",
            details=(("nudge_id", wake.nudge_id),),
        )


@dataclasses.dataclass
class _IdentitylessDispatcher:
    calls: int = 0

    async def nudge(self, wake):
        self.calls += 1
        return TransportReceipt(
            outcome=TransportOutcome.ACCEPTED,
            reason_code="accepted",
            created_at="2026-08-27T09:00:00Z",
            details=(("nudge_id", wake.nudge_id),),
        )


def _mark_implemented(monkeypatch, transport_id: str) -> None:
    existing = WAKE_TRANSPORT_DESCRIPTORS[transport_id]
    monkeypatch.setitem(
        WAKE_TRANSPORT_DESCRIPTORS,
        transport_id,
        WakeTransportDescriptor(
            transport_id=existing.transport_id,
            interface_version=existing.interface_version,
            transport_implemented=True,
            requires_runtime_binding=existing.requires_runtime_binding,
        ),
    )


def test_registry_unknown_transport_refuses():
    with pytest.raises(WakeDispatchError, match="unknown wake transport"):
        WakeDispatcherRegistry({}).resolve("not-a-reviewed-transport")


def test_registry_unimplemented_transport_returns_existing_fail_closed_dispatcher():
    registry = WakeDispatcherRegistry({})

    dispatcher = registry.resolve("claude-code-session")

    assert isinstance(dispatcher, UnsupportedWakeDispatcher)
    assert dispatcher.descriptor.transport_id == "claude-code-session"
    assert dispatcher.descriptor.transport_implemented is False


def test_wake_dispatcher_protocol_requires_canonical_transport_identity():
    assert isinstance(_FakeDispatcher(), WakeDispatcher)
    assert not isinstance(_IdentitylessDispatcher(), WakeDispatcher)


def test_unsupported_dispatcher_exposes_canonical_transport_identity():
    dispatcher = WakeDispatcherRegistry({}).resolve("claude-code-session")

    assert getattr(dispatcher, "transport_id", None) == "claude-code-session"


def test_registry_implemented_transport_requires_explicit_registered_dispatcher(monkeypatch):
    _mark_implemented(monkeypatch, "codex-app-server")
    registry = WakeDispatcherRegistry({})

    with pytest.raises(WakeDispatchError, match="implemented.*no registered dispatcher"):
        registry.resolve("codex-app-server")


def test_registry_returns_exact_explicit_dispatcher_for_implemented_transport(monkeypatch):
    _mark_implemented(monkeypatch, "codex-app-server")
    fake = _FakeDispatcher()
    registry = WakeDispatcherRegistry({"codex-app-server": fake})

    assert registry.resolve("codex-app-server") is fake


def test_registry_refuses_concrete_dispatcher_identity_mismatch(monkeypatch):
    _mark_implemented(monkeypatch, "codex-app-server")
    _mark_implemented(monkeypatch, "claude-code-session")
    fake = _FakeDispatcher(transport_id="claude-code-session")

    with pytest.raises(WakeDispatchError, match="dispatcher transport identity"):
        WakeDispatcherRegistry({"codex-app-server": fake})

    assert fake.calls == 0


def test_registry_refuses_missing_dispatcher_identity(monkeypatch):
    _mark_implemented(monkeypatch, "codex-app-server")
    fake = _IdentitylessDispatcher()

    with pytest.raises(WakeDispatchError, match="dispatcher transport identity"):
        WakeDispatcherRegistry({"codex-app-server": fake})

    assert fake.calls == 0


def test_registry_refuses_registration_for_unknown_transport():
    with pytest.raises(WakeDispatchError, match="unknown wake transport"):
        WakeDispatcherRegistry({"invented-provider-transport": _FakeDispatcher()})


def test_registry_refuses_registration_before_descriptor_is_implemented():
    with pytest.raises(WakeDispatchError, match="not marked implemented"):
        WakeDispatcherRegistry({"claude-code-session": _FakeDispatcher()})


def test_registry_keeps_mapping_private_and_has_no_persistence_api(monkeypatch):
    _mark_implemented(monkeypatch, "codex-app-server")
    registry = WakeDispatcherRegistry({"codex-app-server": _FakeDispatcher()})

    assert not hasattr(registry, "save")
    assert not hasattr(registry, "load")
    assert not hasattr(registry, "discover")
    assert not hasattr(registry, "refresh")
    assert not hasattr(registry, "retry")
