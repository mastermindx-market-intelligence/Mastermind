"""Exact Web-Sol Wake delivery over the existing Executive Wake fabric."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from control_plane.wake_transport import transport_implemented
from integrations.executive_wake.chatgpt_gui import (
    ChatGPTGuiWakeDeliveryObservation,
    ChatGPTGuiWakeDispatcher,
)
from integrations.executive_wake.registry import WakeDispatcherRegistry


def _wake(**overrides) -> WakeNudge:
    value = {
        "session_alias": "EXECUTIVE-CEO-A",
        "reasoning_surface": "chatgpt-sol",
        "wake_transport": "chatgpt-gui",
        "binding_id": "bind-wsx-" + "a" * 48,
        "binding_generation": 1,
        "native_handle": "wsx-runtime-" + "b" * 16,
        "account_label": "seat-label",
        "destination_digest": "c" * 16,
        "obligation_ids": ("WAKE-" + "d" * 32,),
        "attempt_command_ids": ("WAKE-" + "d" * 32 + ":A1",),
        "nudge_id": "NUDGE-" + "e" * 32,
    }
    value.update(overrides)
    return WakeNudge(**value)


def _observation(**overrides) -> ChatGPTGuiWakeDeliveryObservation:
    value = {
        "native_handle": "wsx-runtime-" + "b" * 16,
        "binding_id": "bind-wsx-" + "a" * 48,
        "binding_generation": 1,
        "session_alias": "EXECUTIVE-CEO-A",
        "nudge_id": "NUDGE-" + "e" * 32,
        "generation_started": True,
    }
    value.update(overrides)
    return ChatGPTGuiWakeDeliveryObservation(**value)


@dataclasses.dataclass
class _Client:
    observation: ChatGPTGuiWakeDeliveryObservation = dataclasses.field(default_factory=_observation)
    fail: BaseException | None = None
    calls: list[tuple[object, ...]] = dataclasses.field(default_factory=list)

    async def deliver_wake(
        self, *, native_handle, binding_id, binding_generation, session_alias, nudge_id, opaque_ids
    ):
        self.calls.append(
            (native_handle, binding_id, binding_generation, session_alias, nudge_id, tuple(opaque_ids))
        )
        if self.fail is not None:
            raise self.fail
        return self.observation


def _run(dispatcher, wake=None):
    return asyncio.run(dispatcher.nudge(wake or _wake()))


def test_descriptor_is_implemented_but_composition_is_explicit():
    dispatcher = ChatGPTGuiWakeDispatcher(_Client())
    registry = WakeDispatcherRegistry({"chatgpt-gui": dispatcher})
    assert transport_implemented("chatgpt-gui") is True
    assert registry.resolve("chatgpt-gui") is dispatcher


@pytest.mark.parametrize(
    "overrides",
    [
        {"native_handle": None},
        {"reasoning_surface": "codex"},
        {"wake_transport": "codex-app-server"},
    ],
)
def test_wrong_surface_or_missing_exact_binding_refuses_before_client_call(overrides):
    client = _Client()
    receipt = _run(ChatGPTGuiWakeDispatcher(client), _wake(**overrides))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


def test_started_exact_generation_is_delivery_not_consumption_ack():
    receipt = _run(ChatGPTGuiWakeDispatcher(_Client()))
    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.reason_code == "delivered"
    assert dict(receipt.details) == {"nudge_id": _wake().nudge_id}


def test_client_receives_only_exact_binding_and_opaque_wake_ids():
    client = _Client()
    wake = _wake()
    _run(ChatGPTGuiWakeDispatcher(client), wake)
    assert client.calls == [(
        wake.native_handle, wake.binding_id, wake.binding_generation, wake.session_alias,
        wake.nudge_id, wake.obligation_ids + wake.attempt_command_ids,
    )]


def test_known_pre_submit_refusal_is_target_unavailable():
    client = _Client(fail=WakePreSubmitError("exact web target absent"))
    receipt = _run(ChatGPTGuiWakeDispatcher(client))
    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE


def test_unknown_provider_effect_stays_effect_unknown():
    client = _Client(fail=TimeoutError("receipt lost after possible submit"))
    with pytest.raises(WakeEffectUnknownError, match="effect is unknown"):
        _run(ChatGPTGuiWakeDispatcher(client))
    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"native_handle": "wsx-runtime-" + "f" * 16},
        {"binding_id": "bind-wsx-" + "f" * 48},
        {"binding_generation": 2},
        {"session_alias": "EXECUTIVE-CEO-B"},
        {"nudge_id": "NUDGE-" + "f" * 32},
    ],
)
def test_untrusted_observation_identity_after_possible_write_is_effect_unknown(changes):
    client = _Client(observation=_observation(**changes))
    with pytest.raises(WakeEffectUnknownError, match="identity"):
        _run(ChatGPTGuiWakeDispatcher(client))


def test_dispatcher_has_no_retry_or_ack_or_persistence_surface():
    dispatcher = ChatGPTGuiWakeDispatcher(_Client())
    for forbidden in ("retry", "acknowledge", "save", "load", "discover"):
        assert not hasattr(dispatcher, forbidden)
