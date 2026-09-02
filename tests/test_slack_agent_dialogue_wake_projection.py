"""End-to-end proof of the production-disarmed persisted turn-observation composition."""
from __future__ import annotations

import asyncio
import dataclasses
import json

from control_plane.executive_runtime import Runtime
from control_plane.session_targets import RuntimeBinding, load_session_targets
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.turn_observer import ObservationOutcome
from integrations.slack_agent_dialogue.wake_projection import (
    compose_persisted_turn_observer,
)
from tests.test_executive_wake_persisted_dispatch import _Dispatcher, _POLICY, _binding
from tests.test_slack_agent_dialogue_turn_observer import (
    _client_with_result,
    _context,
    _parent,
    _policy,
    _registry,
    _routing,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _armed_ceo_registry():
    registry = _registry()
    ceo = dataclasses.replace(
        registry.targets["EXECUTIVE-CEO-A"],
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        target_enabled=True,
    )
    return dataclasses.replace(
        registry,
        production_armed=True,
        targets={**registry.targets, "EXECUTIVE-CEO-A": ceo},
    )


def _ceo_binding_for(seat: str) -> RuntimeBinding | None:
    return _binding() if seat == "ceo" else None


def _repo(tmp_path) -> WakeLedgerRepository:
    return WakeLedgerRepository(Runtime.at(tmp_path))


def _compose(
    repo: WakeLedgerRepository,
    dispatcher,
    parent,
    *,
    registry=None,
    binding_for=_ceo_binding_for,
    current_binding=None,
    emitted_at=lambda: "2026-08-30T04:00:00Z",
):
    binding = current_binding if current_binding is not None else _binding()
    return compose_persisted_turn_observer(
        policy=_policy(),
        client=_client_with_result(parent),
        registry=registry if registry is not None else _armed_ceo_registry(),
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
        binding_for=binding_for,
        emitted_at=emitted_at,
    )


def _phases(repo, obligation_id):
    return [item.record.phase for item in repo.list_records(obligation_id)]


def test_composed_journey_delivers_once_with_closed_ledger_receipt(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher(repo=repo)
    observer = _compose(repo, dispatcher, parent)

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert receipt.obligation is not None
    assert receipt.route is not None
    assert receipt.route.target_seat == "ceo"
    assert dispatcher.nudge_calls == 1
    assert _phases(repo, receipt.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]


def test_restart_recomputes_from_canonical_ledger_and_does_not_resend(tmp_path) -> None:
    parent = _parent()
    first_repo = _repo(tmp_path)
    first_dispatcher = _Dispatcher(repo=first_repo)
    first = _run(
        _compose(
            first_repo,
            first_dispatcher,
            parent,
            emitted_at=lambda: "2026-08-30T04:00:00Z",
        ).reconcile_once(context=_context(parent), routing=_routing(parent))
    )
    assert first.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert first_dispatcher.nudge_calls == 1

    second_repo = _repo(tmp_path)
    second_dispatcher = _Dispatcher(repo=second_repo)
    second = _run(
        _compose(
            second_repo,
            second_dispatcher,
            parent,
            emitted_at=lambda: "2026-08-30T09:59:59Z",
        ).reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert second.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
    assert second.reason == "WAKE_OBLIGATION_ALREADY_RECORDED"
    assert second.obligation is not None
    assert first.obligation is not None
    assert second.obligation.obligation_id == first.obligation.obligation_id
    assert second_dispatcher.nudge_calls == 0


def test_unfinished_delivery_attempt_holds_effect_unknown_across_restart(tmp_path) -> None:
    parent = _parent()
    first_repo = _repo(tmp_path)
    failing = _Dispatcher(failure=TimeoutError("provider response lost"))
    first = _run(
        _compose(first_repo, failing, parent).reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )
    assert first.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
    assert first.obligation is not None
    assert _phases(first_repo, first.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]

    second_repo = _repo(tmp_path)
    clean = _Dispatcher(repo=second_repo)
    second = _run(
        _compose(
            second_repo,
            clean,
            parent,
            emitted_at=lambda: "2026-08-30T09:59:59Z",
        ).reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert second.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
    assert second.reason == "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD"
    assert clean.nudge_calls == 0
    assert second.obligation is not None
    assert _phases(second_repo, second.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]


def test_target_drift_fails_closed_before_provider_write(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    rotated = _binding(generation=2, binding_id="bind-codexwake02")
    receipt = _run(
        _compose(repo, dispatcher, parent, current_binding=rotated).reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert receipt.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "WAKE_TARGET_UNAVAILABLE"
    assert receipt.obligation is not None
    assert _phases(repo, receipt.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED
    ]
    assert dispatcher.nudge_calls == 0


def test_unbound_target_refuses_without_persistence(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    observer = compose_persisted_turn_observer(
        policy=_policy(),
        client=_client_with_result(parent),
        registry=load_session_targets(),
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: _binding(),
        retry_policy=_POLICY,
    )

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.REFUSED
    assert receipt.reason.startswith("DIALOGUE_WAKE_TARGET_UNBOUND")
    assert receipt.obligation is not None
    assert repo.list_records(receipt.obligation.obligation_id) == ()
    assert dispatcher.nudge_calls == 0


def test_no_provider_native_handle_leaks_into_receipt_or_ledger(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher(repo=repo)
    binding = _binding()
    receipt = _run(
        _compose(repo, dispatcher, parent, current_binding=binding).reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert receipt.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert receipt.obligation is not None
    assert receipt.route is not None
    native_handle = binding.native_handle
    assert native_handle
    assert native_handle not in repr(receipt)
    assert native_handle not in json.dumps(dataclasses.asdict(receipt.route), default=str)
    for item in repo.list_records(receipt.obligation.obligation_id):
        assert native_handle not in json.dumps(item.event.payload, default=str)
