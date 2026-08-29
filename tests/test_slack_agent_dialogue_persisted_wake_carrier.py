from __future__ import annotations

import asyncio

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.session_targets import RuntimeBinding
from control_plane.wake_dispatcher import WakeEffectUnknownError
from control_plane.wake_ledger import LedgerPhase, requested_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.persisted_wake_carrier import PersistedWakeCarrier
from integrations.slack_agent_dialogue.turn_observer import WakeCarrierState
from tests.test_executive_wake_persisted_dispatch import (
    _Dispatcher,
    _POLICY,
    _binding,
    _pair,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _carrier(repo, dispatcher, binding: RuntimeBinding):
    return PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
    )


def _phases(repo, obligation_id):
    return [item.record.phase for item in repo.list_records(obligation_id)]


def test_reconcile_no_records_and_requested_only_are_submit_eligible(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    dispatcher = _Dispatcher()
    carrier = _carrier(repo, dispatcher, binding)

    assert _run(carrier.reconcile(obligation, route)) is WakeCarrierState.MISSING

    repo.append_record(requested_record(obligation), obligation=obligation)

    assert _run(carrier.reconcile(obligation, route)) is WakeCarrierState.MISSING


def test_submit_persists_request_then_uses_existing_persisted_dispatch(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    dispatcher = _Dispatcher(repo=repo)
    carrier = _carrier(repo, dispatcher, binding)

    _run(carrier.submit(obligation, route))

    assert dispatcher.nudge_calls == 1
    assert _phases(repo, obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]
    assert _run(carrier.reconcile(obligation, route)) is WakeCarrierState.RECORDED


def test_effect_unknown_attempt_reconciles_hold_and_never_resubmits(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    dispatcher = _Dispatcher(failure=TimeoutError("provider response lost"))
    carrier = _carrier(repo, dispatcher, binding)

    with pytest.raises(WakeEffectUnknownError):
        _run(carrier.submit(obligation, route))

    assert dispatcher.nudge_calls == 1
    assert _phases(repo, obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]
    assert _run(carrier.reconcile(obligation, route)) is WakeCarrierState.EFFECT_UNKNOWN

    with pytest.raises(WakeEffectUnknownError):
        _run(carrier.submit(obligation, route))
    assert dispatcher.nudge_calls == 1


def test_current_binding_is_revalidated_before_provider_submission(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    dispatcher = _Dispatcher()
    rotated = _binding(generation=2, binding_id="bind-codexwake02")
    carrier = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: rotated,
        retry_policy=_POLICY,
    )

    with pytest.raises(ValueError, match="current RuntimeBinding"):
        _run(carrier.submit(obligation, route))

    assert dispatcher.nudge_calls == 0
    assert _phases(repo, obligation.obligation_id) == [LedgerPhase.WAKE_REQUESTED]


def test_requested_only_survives_restart_and_dispatches_once(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    repo.append_record(requested_record(obligation), obligation=obligation)

    restarted = Runtime.at(tmp_path)
    restarted_repo = WakeLedgerRepository(restarted)
    dispatcher = _Dispatcher(repo=restarted_repo)
    carrier = _carrier(restarted_repo, dispatcher, binding)

    assert _run(carrier.reconcile(obligation, route)) is WakeCarrierState.MISSING
    _run(carrier.submit(obligation, route))

    assert dispatcher.nudge_calls == 1
    assert _phases(restarted_repo, obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]
