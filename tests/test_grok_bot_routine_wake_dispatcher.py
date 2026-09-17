"""RED-first contract for the production-inert Grok routine Wake adapter."""
from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from control_plane.wake_transport import transport_implemented
from integrations.executive_wake.grok_bot_routine import (
    GrokBotRoutineWakeDispatcher,
    GrokRoutineWakeObservation,
)


def _wake(**overrides) -> WakeNudge:
    value = {
        "session_alias": "EXECUTIVE-COO-GROK-A",
        "reasoning_surface": "grok-bot",
        "wake_transport": "grok-computer",
        "binding_id": "bind-grokroutine01",
        "binding_generation": 4,
        "native_handle": "grok-routine-opaque-123",
        "account_label": "must-not-be-sent",
        "destination_digest": "d" * 16,
        "obligation_ids": ("WAKE-" + "a" * 32,),
        "attempt_command_ids": ("WAKE-" + "a" * 32 + ":delivery:1",),
        "nudge_id": "NUDGE-" + "b" * 32,
    }
    value.update(overrides)
    return WakeNudge(**value)


@dataclasses.dataclass
class _FakeClient:
    observation: object
    fail: BaseException | None = None
    calls: list[tuple[str, str, str, int, tuple[str, ...]]] = dataclasses.field(
        default_factory=list
    )

    async def deliver_wake(
        self,
        *,
        native_handle,
        nudge_id,
        binding_id,
        binding_generation,
        opaque_ids,
    ):
        self.calls.append(
            (
                native_handle,
                nudge_id,
                binding_id,
                binding_generation,
                tuple(opaque_ids),
            )
        )
        if self.fail is not None:
            raise self.fail
        return self.observation


@dataclasses.dataclass
class _FakeObservationSource:
    observation: object | None
    fail: BaseException | None = None
    calls: list[tuple[str, str]] = dataclasses.field(default_factory=list)

    async def observe_wake(self, *, native_handle, nudge_id):
        self.calls.append((native_handle, nudge_id))
        if self.fail is not None:
            raise self.fail
        return self.observation


@dataclasses.dataclass
class _BlockingClient:
    started: asyncio.Event
    calls: list[tuple[str, str, str, int, tuple[str, ...]]] = dataclasses.field(
        default_factory=list
    )

    async def deliver_wake(
        self,
        *,
        native_handle,
        nudge_id,
        binding_id,
        binding_generation,
        opaque_ids,
    ):
        self.calls.append(
            (
                native_handle,
                nudge_id,
                binding_id,
                binding_generation,
                tuple(opaque_ids),
            )
        )
        self.started.set()
        await asyncio.Future()


@dataclasses.dataclass
class _BlockingObservationSource:
    started: asyncio.Event
    calls: list[tuple[str, str]] = dataclasses.field(default_factory=list)

    async def observe_wake(self, *, native_handle, nudge_id):
        self.calls.append((native_handle, nudge_id))
        self.started.set()
        await asyncio.Future()


def _observation(
    *,
    accepted=True,
    native_handle="grok-routine-opaque-123",
    nudge_id="NUDGE-" + "b" * 32,
    request_id="request-opaque-1",
):
    return GrokRoutineWakeObservation(
        native_handle=native_handle,
        nudge_id=nudge_id,
        accepted=accepted,
        request_id=request_id,
    )


def _nudge(dispatcher, wake):
    return asyncio.run(dispatcher.nudge(wake))


def _reconcile(dispatcher, wake):
    return asyncio.run(dispatcher.reconcile(wake))


def test_source_presence_does_not_mark_transport_implemented():
    assert transport_implemented("grok-computer") is False


def test_constructor_requires_an_explicit_client():
    with pytest.raises(ValueError, match="client"):
        GrokBotRoutineWakeDispatcher(None)


def test_nudge_requires_the_typed_wake_contract():
    dispatcher = GrokBotRoutineWakeDispatcher(_FakeClient(_observation()))

    with pytest.raises(ValueError, match="WakeNudge"):
        _nudge(dispatcher, object())


def test_missing_native_handle_is_target_unavailable_without_provider_call():
    client = _FakeClient(_observation())
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake(native_handle=None))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"reasoning_surface": "chatgpt-sol"},
        {"reasoning_surface": "codex"},
        {"wake_transport": "codex-app-server"},
        {"wake_transport": "chatgpt-gui"},
    ],
)
def test_surface_or_transport_mismatch_refuses_before_provider_call(overrides):
    client = _FakeClient(_observation())
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake(**overrides))

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert client.calls == []


def test_exact_acceptance_is_accepted_and_can_never_claim_delivery():
    client = _FakeClient(_observation(accepted=True))
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.ACCEPTED
    assert receipt.outcome is not TransportOutcome.DELIVERED
    assert receipt.reason_code == "accepted"
    assert dict(receipt.details) == {"nudge_id": "NUDGE-" + "b" * 32}
    assert len(client.calls) == 1


def test_definite_provider_refusal_is_target_unavailable_not_delivery():
    client = _FakeClient(_observation(accepted=False))
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert receipt.outcome is not TransportOutcome.DELIVERED
    assert len(client.calls) == 1


def test_typed_pre_submit_absence_can_terminalize_without_effect_unknown():
    client = _FakeClient(
        _observation(),
        fail=WakePreSubmitError("routine unavailable before submission"),
    )
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    receipt = _nudge(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.TARGET_UNAVAILABLE
    assert receipt.reason_code == "target_unavailable"
    assert len(client.calls) == 1


def test_post_call_exception_is_effect_unknown_and_never_failed_or_retried():
    client = _FakeClient(_observation(), fail=TimeoutError("response lost"))
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="effect is unknown"):
        _nudge(dispatcher, _wake())
    assert len(client.calls) == 1


def test_post_call_injected_cancellation_is_effect_unknown_and_never_retries():
    secret = "secret-cancellation-detail.not-for-logs"
    client = _FakeClient(_observation(), fail=asyncio.CancelledError(secret))
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="effect is unknown") as captured:
        _nudge(dispatcher, _wake())

    assert secret not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert len(client.calls) == 1


def test_real_post_call_task_cancellation_is_effect_unknown_and_never_retried():
    secret = "secret-task-cancellation-detail.not-for-logs"

    async def exercise() -> None:
        client = _BlockingClient(asyncio.Event())
        dispatcher = GrokBotRoutineWakeDispatcher(client)
        task = asyncio.create_task(dispatcher.nudge(_wake()))
        await client.started.wait()

        task.cancel(secret)
        with pytest.raises(WakeEffectUnknownError, match="effect is unknown") as captured:
            await task

        assert task.cancelled() is False
        assert secret not in repr(captured.value)
        assert captured.value.__cause__ is None
        assert captured.value.__context__ is None
        assert len(client.calls) == 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "observation",
    [
        _observation(native_handle="wrong-handle"),
        _observation(nudge_id="NUDGE-" + "c" * 32),
        object(),
    ],
)
def test_untyped_or_mismatched_provider_observation_is_effect_unknown(observation):
    client = _FakeClient(observation)
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="observation"):
        _nudge(dispatcher, _wake())
    assert len(client.calls) == 1


def test_provider_receives_only_bound_identity_and_opaque_wake_ids():
    client = _FakeClient(_observation())
    dispatcher = GrokBotRoutineWakeDispatcher(client)
    wake = _wake(account_label="must-not-be-sent")

    _nudge(dispatcher, wake)

    assert client.calls == [
        (
            wake.native_handle,
            wake.nudge_id,
            wake.binding_id,
            wake.binding_generation,
            wake.obligation_ids + wake.attempt_command_ids,
        )
    ]
    assert "must-not-be-sent" not in repr(client.calls)


def test_reconcile_requires_an_explicit_observation_source():
    dispatcher = GrokBotRoutineWakeDispatcher(_FakeClient(_observation()))

    with pytest.raises(WakeEffectUnknownError, match="observation source"):
        _reconcile(dispatcher, _wake())


def test_reconcile_observes_same_nudge_without_a_second_submission():
    client = _FakeClient(_observation())
    source = _FakeObservationSource(_observation(accepted=True))
    dispatcher = GrokBotRoutineWakeDispatcher(client, observation_source=source)

    receipt = _reconcile(dispatcher, _wake())

    assert receipt.outcome is TransportOutcome.ACCEPTED
    assert receipt.outcome is not TransportOutcome.DELIVERED
    assert client.calls == []
    assert source.calls == [
        ("grok-routine-opaque-123", "NUDGE-" + "b" * 32)
    ]


def test_reconcile_without_a_provider_observation_remains_effect_unknown():
    source = _FakeObservationSource(None)
    dispatcher = GrokBotRoutineWakeDispatcher(
        _FakeClient(_observation()), observation_source=source
    )

    with pytest.raises(WakeEffectUnknownError, match="remains unknown"):
        _reconcile(dispatcher, _wake())
    assert len(source.calls) == 1


def test_reconcile_source_error_remains_effect_unknown_without_submission():
    client = _FakeClient(_observation())
    source = _FakeObservationSource(None, fail=RuntimeError("history unavailable"))
    dispatcher = GrokBotRoutineWakeDispatcher(client, observation_source=source)

    with pytest.raises(WakeEffectUnknownError, match="remains unknown"):
        _reconcile(dispatcher, _wake())
    assert client.calls == []
    assert len(source.calls) == 1


def test_reconcile_injected_cancellation_remains_effect_unknown_without_submission():
    secret = "secret-reconcile-cancellation-detail.not-for-logs"
    client = _FakeClient(_observation())
    source = _FakeObservationSource(None, fail=asyncio.CancelledError(secret))
    dispatcher = GrokBotRoutineWakeDispatcher(client, observation_source=source)

    with pytest.raises(WakeEffectUnknownError, match="remains unknown") as captured:
        _reconcile(dispatcher, _wake())

    assert secret not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert client.calls == []
    assert len(source.calls) == 1


def test_real_reconcile_task_cancellation_remains_effect_unknown():
    secret = "secret-reconcile-task-cancellation-detail.not-for-logs"

    async def exercise() -> None:
        client = _FakeClient(_observation())
        source = _BlockingObservationSource(asyncio.Event())
        dispatcher = GrokBotRoutineWakeDispatcher(client, observation_source=source)
        task = asyncio.create_task(dispatcher.reconcile(_wake()))
        await source.started.wait()

        task.cancel(secret)
        with pytest.raises(WakeEffectUnknownError, match="remains unknown") as captured:
            await task

        assert task.cancelled() is False
        assert secret not in repr(captured.value)
        assert captured.value.__cause__ is None
        assert captured.value.__context__ is None
        assert client.calls == []
        assert len(source.calls) == 1

    asyncio.run(exercise())


def test_observation_validation_is_closed_and_secret_free():
    with pytest.raises(ValueError, match="native handle"):
        GrokRoutineWakeObservation("", "NUDGE-" + "b" * 32, True)
    with pytest.raises(ValueError, match="nudge"):
        GrokRoutineWakeObservation("routine", "", True)
    with pytest.raises(ValueError, match="boolean"):
        GrokRoutineWakeObservation("routine", "NUDGE-" + "b" * 32, 1)
    with pytest.raises(ValueError, match="request"):
        GrokRoutineWakeObservation(
            "routine", "NUDGE-" + "b" * 32, True, request_id="bad\nrequest"
        )

    observation = _observation(request_id="request-opaque-1")
    assert "bearer" not in repr(observation).lower()
    assert "token" not in repr(observation).lower()


def test_module_has_no_network_or_secret_implementation():
    source = Path("integrations/executive_wake/grok_bot_routine.py").read_text()
    forbidden = (
        "httpx",
        "requests",
        "urllib.request",
        "Authorization",
        "Bearer ",
        "socket",
        "subprocess",
    )
    for token in forbidden:
        assert token not in source


def test_observation_rejects_non_string_opaque_identity_fields():
    with pytest.raises(ValueError, match="native handle"):
        GrokRoutineWakeObservation(7, "NUDGE-" + "b" * 32, True)
    with pytest.raises(ValueError, match="request"):
        GrokRoutineWakeObservation(
            "routine", "NUDGE-" + "b" * 32, True, request_id=7
        )


def test_post_call_exception_does_not_expose_injected_client_details():
    secret = "secret-token-value.not-for-logs"
    client = _FakeClient(_observation(), fail=RuntimeError(secret))
    dispatcher = GrokBotRoutineWakeDispatcher(client)

    with pytest.raises(WakeEffectUnknownError, match="effect is unknown") as captured:
        _nudge(dispatcher, _wake())

    assert secret not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert len(client.calls) == 1


def test_reconcile_error_does_not_expose_observation_source_details():
    secret = "secret-provider-history.not-for-logs"
    client = _FakeClient(_observation())
    source = _FakeObservationSource(None, fail=RuntimeError(secret))
    dispatcher = GrokBotRoutineWakeDispatcher(client, observation_source=source)

    with pytest.raises(WakeEffectUnknownError, match="remains unknown") as captured:
        _reconcile(dispatcher, _wake())

    assert secret not in repr(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert client.calls == []
    assert len(source.calls) == 1
