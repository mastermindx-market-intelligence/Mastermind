"""RED-first contract for Wake PR3 Codex App Server delivery."""
from __future__ import annotations

import dataclasses

import pytest

from control_plane.wake_dispatcher import TransportOutcome, WakeNudge
from integrations.executive_wake.codex_app_server import (
    CODEX_WAKE_INSTRUCTION,
    CodexAppServerWakeDispatcher,
    CodexWakeDeliveryObservation,
)


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


@pytest.mark.asyncio
async def test_missing_native_handle_is_target_unavailable_without_provider_call():
    client = _FakeClient(_observation())
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = await dispatcher.nudge(_wake(native_handle=None))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"reasoning_surface": "chatgpt-sol"},
        {"wake_transport": "claude-code-session"},
    ],
)
async def test_surface_or_transport_mismatch_refuses_before_provider_call(overrides):
    client = _FakeClient(_observation())
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = await dispatcher.nudge(_wake(**overrides))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


@pytest.mark.asyncio
async def test_accepted_but_not_observed_is_accepted_not_delivered():
    client = _FakeClient(_observation(accepted=True, delivered=False))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = await dispatcher.nudge(_wake())

    assert receipt.outcome is TransportOutcome.ACCEPTED
    assert receipt.reason_code == "accepted"
    assert dict(receipt.details)["nudge_id"] == "NUDGE-" + "b" * 32
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_exact_bound_thread_confirmation_is_delivered():
    client = _FakeClient(_observation(accepted=True, delivered=True))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = await dispatcher.nudge(_wake())

    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.reason_code == "delivered"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_provider_echo_mismatch_fails_closed_and_never_retries():
    client = _FakeClient(_observation(native_handle="wrong-thread"))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = await dispatcher.nudge(_wake())

    assert receipt.outcome is TransportOutcome.FAILED
    assert receipt.reason_code == "transport_failed"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_provider_timeout_is_failed_and_never_causes_second_call():
    client = _FakeClient(_observation(), fail=TimeoutError("provider timeout"))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = await dispatcher.nudge(_wake())

    assert receipt.outcome is TransportOutcome.FAILED
    assert receipt.reason_code == "transport_failed"
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_payload_is_fixed_bounded_instruction_plus_opaque_wake_ids_only():
    client = _FakeClient(_observation())
    dispatcher = CodexAppServerWakeDispatcher(client)
    wake = _wake(account_label="must-not-enter-prompt")

    await dispatcher.nudge(wake)

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
