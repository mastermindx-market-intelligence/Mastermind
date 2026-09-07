"""RED-first contract for Wake PR3 Codex App Server delivery."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeTransportCompletion,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
    normalize_transport_completion,
)
from control_plane.wake_ack_ingress import TrustedWorkerWakeAckProjection
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
    late_observation: CodexWakeDeliveryObservation | None = None
    calls: list[tuple[str, str, tuple[str, ...], str]] = dataclasses.field(default_factory=list)
    reconcile_calls: list[tuple[str, str, tuple[str, ...]]] = dataclasses.field(
        default_factory=list
    )
    fail: Exception | None = None

    async def deliver_wake(self, *, native_handle, nudge_id, opaque_ids, instruction):
        self.calls.append((native_handle, nudge_id, tuple(opaque_ids), instruction))
        if self.fail is not None:
            raise self.fail
        return self.observation

    async def reconcile_wake(self, *, native_handle, nudge_id, opaque_ids):
        self.reconcile_calls.append((native_handle, nudge_id, tuple(opaque_ids)))
        if self.fail is not None:
            raise self.fail
        if self.late_observation is None:
            raise RuntimeError("late completion is not available")
        return self.late_observation


def _projection() -> TrustedWorkerWakeAckProjection:
    return TrustedWorkerWakeAckProjection(
        target_attempt_id="ATT-" + "1" * 32,
        process_generation_id="generation-ack-1",
        binding_id="bind-ack12345",
        binding_generation=3,
        provider_session_id="thread-opaque-123",
        provider_native_turn_id="turn-ack-1",
        nudge_id="NUDGE-" + "b" * 32,
        obligation_ids=("WAKE-" + "a" * 32,),
        terminal_ack_trailer=True,
    )


def _observation(
    *,
    accepted=True,
    delivered=False,
    native_handle="thread-opaque-123",
    target_ack_projection=None,
):
    return CodexWakeDeliveryObservation(
        native_handle=native_handle,
        nudge_id="NUDGE-" + "b" * 32,
        accepted=accepted,
        delivered=delivered,
        target_ack_projection=target_ack_projection,
    )


def _nudge(dispatcher, wake):
    return asyncio.run(dispatcher.nudge(wake))


def _reconcile(dispatcher, wake):
    return asyncio.run(dispatcher.reconcile(wake))


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


def test_known_terminal_failed_or_interrupted_is_accepted_not_delivered():
    """Both recognized terminal failure statuses collapse to this closed observation."""

    client = _FakeClient(_observation(accepted=True, delivered=False))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.ACCEPTED
    assert receipt.outcome is not TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "accepted"
    assert dict(receipt.details)["nudge_id"] == "NUDGE-" + "b" * 32
    assert len(client.calls) == 1


def test_completed_without_ack_projection_is_delivered_not_target_unavailable():
    """Completed no/invalid ACK content remains delivery with no projection."""

    client = _FakeClient(_observation(accepted=True, delivered=True))
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.DELIVERED
    assert receipt.outcome is not TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "delivered"
    assert len(client.calls) == 1


def test_exact_bound_ack_projection_is_transient_completion_not_receipt_detail():
    projection = _projection()
    client = _FakeClient(
        _observation(
            accepted=True,
            delivered=True,
            target_ack_projection=projection,
        )
    )
    dispatcher = CodexAppServerWakeDispatcher(client)

    completion = _nudge(dispatcher, _wake())

    assert isinstance(completion, WakeTransportCompletion)
    receipt, normalized = normalize_transport_completion(completion)
    assert receipt.outcome is TransportOutcome.DELIVERED
    assert dict(receipt.details) == {"nudge_id": "NUDGE-" + "b" * 32}
    assert normalized is projection
    assert "target_ack_projection" not in repr(completion)


def test_late_reconcile_returns_delivery_and_projection_without_provider_submission():
    """Catches late reconciliation calling deliver_wake or discarding its projection."""

    projection = _projection()
    client = _FakeClient(
        _observation(),
        late_observation=_observation(
            accepted=True,
            delivered=True,
            target_ack_projection=projection,
        ),
    )
    dispatcher = CodexAppServerWakeDispatcher(client)

    completion = _reconcile(dispatcher, _wake())

    receipt, normalized = normalize_transport_completion(completion)
    assert receipt.outcome is TransportOutcome.DELIVERED
    assert normalized is projection
    assert client.calls == []
    assert client.reconcile_calls == [
        (
            "thread-opaque-123",
            "NUDGE-" + "b" * 32,
            _wake().obligation_ids + _wake().attempt_command_ids,
        )
    ]


def test_late_terminal_failure_remains_accepted_without_provider_submission():
    client = _FakeClient(
        _observation(),
        late_observation=_observation(accepted=True, delivered=False),
    )
    dispatcher = CodexAppServerWakeDispatcher(client)

    receipt = _reconcile(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.ACCEPTED
    assert client.calls == []
    assert len(client.reconcile_calls) == 1


def test_transport_completion_normalizer_rejects_untyped_projection_or_value():
    receipt = CodexAppServerWakeDispatcher._receipt(
        TransportOutcome.DELIVERED,
        "delivered",
        nudge_id="NUDGE-" + "b" * 32,
    )

    assert normalize_transport_completion(receipt) == (receipt, None)
    with pytest.raises(Exception, match="completion"):
        normalize_transport_completion(object())


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
