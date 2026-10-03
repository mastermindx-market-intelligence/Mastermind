"""Exact Web-Sol Wake delivery over the existing Executive Wake fabric."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.wake_ack_ingress import TrustedWebSolWakeAckProjection
from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
    WakeTransportCompletion,
    WebSolWakeAckCompletion,
)
from control_plane.wake_transport import transport_implemented
from integrations.executive_wake.chatgpt_gui import (
    ChatGPTGuiWakeAckObservation,
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


def _ack_observation(**overrides) -> ChatGPTGuiWakeAckObservation:
    projection_value = {
        "session_alias": "EXECUTIVE-CEO-A",
        "reasoning_surface": "chatgpt-sol",
        "binding_id": "bind-wsx-" + "a" * 48,
        "binding_generation": 1,
        "native_handle": "wsx-runtime-" + "b" * 16,
        "runtime_binding_fingerprint": "f" * 64,
        "conversation_fingerprint": "1" * 64,
        "provider_native_turn_id": "assistant-turn-current-001",
        "nudge_id": "NUDGE-" + "e" * 32,
        "obligation_ids": ("WAKE-" + "d" * 32,),
        "terminal_ack_trailer": True,
    }
    projection_value.update(overrides)
    return ChatGPTGuiWakeAckObservation(
        projection=TrustedWebSolWakeAckProjection(**projection_value),
        runtime_binding_lease=object(),
    )


@dataclasses.dataclass
class _Client:
    observation: ChatGPTGuiWakeDeliveryObservation = dataclasses.field(default_factory=_observation)
    ack_observation: ChatGPTGuiWakeAckObservation = dataclasses.field(default_factory=_ack_observation)
    fail: BaseException | None = None
    ack_fail: BaseException | None = None
    calls: list[tuple[object, ...]] = dataclasses.field(default_factory=list)
    ack_calls: list[tuple[object, ...]] = dataclasses.field(default_factory=list)

    async def deliver_wake(
        self, *, native_handle, binding_id, binding_generation, session_alias, nudge_id, obligation_ids
    ):
        self.calls.append(
            (native_handle, binding_id, binding_generation, session_alias, nudge_id, tuple(obligation_ids))
        )
        if self.fail is not None:
            raise self.fail
        return self.observation

    async def observe_wake_ack(
        self, *, native_handle, binding_id, binding_generation, session_alias, nudge_id, obligation_ids
    ):
        self.ack_calls.append(
            (native_handle, binding_id, binding_generation, session_alias, nudge_id, tuple(obligation_ids))
        )
        if self.ack_fail is not None:
            raise self.ack_fail
        return self.ack_observation


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
        wake.nudge_id, wake.obligation_ids,
    )]


def test_web_sol_canonicalizes_coalesced_wake_ids_before_provider_use():
    wake_d = "WAKE-" + "d" * 32
    wake_f = "WAKE-" + "f" * 32
    client = _Client(
        ack_observation=_ack_observation(obligation_ids=(wake_d, wake_f))
    )
    wake = _wake(
        obligation_ids=(wake_f, wake_d),
        attempt_command_ids=(wake_f + ":A1", wake_d + ":A1"),
    )
    dispatcher = ChatGPTGuiWakeDispatcher(client)
    _run(dispatcher, wake)
    completion = asyncio.run(dispatcher.reconcile_delivered_ack(wake))
    assert client.calls[0][-1] == (wake_d, wake_f)
    assert client.ack_calls[0][-1] == (wake_d, wake_f)
    assert isinstance(completion, WakeTransportCompletion)


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


def test_delivered_ack_returns_transient_web_sol_completion():
    client = _Client()
    wake = _wake()
    completion = asyncio.run(
        ChatGPTGuiWakeDispatcher(client).reconcile_delivered_ack(wake)
    )
    assert isinstance(completion, WakeTransportCompletion)
    assert completion.receipt.outcome is TransportOutcome.DELIVERED
    assert isinstance(completion.target_ack_projection, WebSolWakeAckCompletion)
    assert completion.target_ack_projection.projection.provider_native_turn_id == (
        "assistant-turn-current-001"
    )
    assert client.ack_calls == [(
        wake.native_handle,
        wake.binding_id,
        wake.binding_generation,
        wake.session_alias,
        wake.nudge_id,
        wake.obligation_ids,
    )]


def test_wrong_semantic_projection_identity_refuses_without_effect_unknown():
    client = _Client(
        ack_observation=_ack_observation(nudge_id="NUDGE-" + "f" * 32)
    )
    with pytest.raises(WakePreSubmitError, match="identity"):
        asyncio.run(
            ChatGPTGuiWakeDispatcher(client).reconcile_delivered_ack(_wake())
        )


def test_dispatcher_has_no_retry_or_ack_or_persistence_surface():
    dispatcher = ChatGPTGuiWakeDispatcher(_Client())
    for forbidden in ("retry", "acknowledge", "save", "load", "discover"):
        assert not hasattr(dispatcher, forbidden)
