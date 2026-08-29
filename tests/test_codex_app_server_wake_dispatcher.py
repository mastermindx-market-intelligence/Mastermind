"""RED-first contract for Wake PR3 Codex App Server delivery."""
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
from integrations.executive_wake.codex_app_server import (
    CODEX_WAKE_INSTRUCTION,
    CodexAppServerWakeDispatcher,
    CodexWakeDeliveryObservation,
)
from integrations.executive_wake.registry import WakeDispatcherRegistry


def _wake(**overrides) -> WakeNudge:
    value = {
        "session_alias": "EXECUTIVE-CEO-A",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "binding_id": "bind-codexwake01",
        "binding_generation": 3,
        "native_handle": "thread-opaque-123",
        "account_label": "codex-pro-a",
        "destination_digest": "d" * 16,
        "obligation_ids": ("WAKE-" + "a" * 32,),
        "attempt_command_ids": ("WAKE-" + "a" * 32 + ":delivery:1",),
        "nudge_id": "NUDGE-" + "b" * 32,
    }
    value.update(overrides)
    return WakeNudge(**value)


@dataclasses.dataclass
class _FakeClient:
    observation: CodexWakeDeliveryObservation
    calls: list[tuple[str, str, tuple[str, ...], str]] = dataclasses.field(default_factory=list)
    fail: Exception | None = None

    async def deliver_wake(self, *, native_handle, nudge_id, opaque_ids, instruction):
        self.calls.append((native_handle, nudge_id, tuple(opaque_ids), instruction))
        if self.fail is not None:
            raise self.fail
        return self.observation


def _observation(*, accepted=True, delivered=False, native_handle="thread-opaque-123"):
    return CodexWakeDeliveryObservation(
        native_handle=native_handle,
        nudge_id="NUDGE-" + "b" * 32,
        accepted=accepted,
        delivered=delivered,
    )


def _nudge(dispatcher, wake):
    return asyncio.run(dispatcher.nudge(wake))


def test_codex_descriptor_is_implemented_but_registry_requires_explicit_composition():
    dispatcher = CodexAppServerWakeDispatcher(_FakeClient(_observation()))
    registry = WakeDispatcherRegistry({"codex-app-server": dispatcher})

    assert transport_implemented("codex-app-server") is True
    assert registry.resolve("codex-app-server") is dispatcher
    assert transport_implemented("claude-code-session") is False


def test_missing_native_handle_is_target_unavailable_without_provider_call():
    client = _FakeClient(_observation())
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake(native_handle=None))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"reasoning_surface": "chatgpt-sol"},
        {"wake_transport": "claude-code-session"},
    ],
)
def test_surface_or_transport_mismatch_refuses_before_provider_call(overrides):
    client = _FakeClient(_observation())
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake(**overrides))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


def test_accepted_but_not_observed_is_accepted_not_delivered():
    client = _FakeClient(_observation(accepted=True, delivered=False))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.ACCEPTED
    assert receipt.reason_code == "accepted"
    assert dict(receipt.details)["nudge_id"] == "NUDGE-" + "b" * 32
    assert len(client.calls) == 1


def test_exact_bound_thread_confirmation_is_delivered():
    client = _FakeClient(_observation(accepted=True, delivered=True))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.reason_code == "delivered"
    assert len(client.calls) == 1


def test_provider_echo_mismatch_is_effect_unknown_after_possible_write():
    client = _FakeClient(_observation(native_handle="wrong-thread"))
    dispatcher = CodexAppServerWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="identity"):
        _nudge(dispatcher, _wake())
    assert len(client.calls) == 1


def test_provider_timeout_is_effect_unknown_and_never_terminal_failed():
    client = _FakeClient(_observation(), fail=TimeoutError("provider timeout"))
    dispatcher = CodexAppServerWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="effect is unknown"):
        _nudge(dispatcher, _wake())
    assert len(client.calls) == 1


def test_typed_pre_submit_absence_can_terminalize_target_unavailable():
    client = _FakeClient(
        _observation(),
        fail=WakePreSubmitError("thread absent before turn/start"),
    )
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert len(client.calls) == 1


def test_payload_is_fixed_bounded_instruction_plus_opaque_wake_ids_only():
    client = _FakeClient(_observation())
    dispatcher = CodexAppServerWakeDispatcher(client)
    wake = _wake(account_label="must-not-enter-prompt")

    _nudge(dispatcher, wake)

    assert len(client.calls) == 1
    native_handle, nudge_id, opaque_ids, instruction = client.calls[0]
    assert native_handle == wake.native_handle
    assert nudge_id == wake.nudge_id
    assert opaque_ids == wake.obligation_ids + wake.attempt_command_ids
    assert instruction == CODEX_WAKE_INSTRUCTION
    assert "must-not-enter-prompt" not in instruction
    assert "objective" not in instruction.lower()
    assert "result" not in instruction.lower()
    assert len(instruction) <= 512
