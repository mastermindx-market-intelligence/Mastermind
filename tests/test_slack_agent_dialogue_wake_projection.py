"""RED-first end-to-end proof of the composed persisted turn-observation vertical.

This exercises the real machine journey through
:func:`compose_persisted_turn_observer` only.  It owns no watcher, loop,
store, transport, retry, binding, or lifecycle state of its own; every
fixture below composes the same accepted W3C owners already proven in
``tests/test_slack_agent_dialogue_turn_observer.py`` and
``tests/test_slack_agent_dialogue_persisted_wake_carrier.py``.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json

from control_plane.executive_runtime import Runtime
from control_plane.session_targets import RuntimeBinding, load_session_targets
from control_plane.wake_ledger import LedgerPhase
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
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
    """Overlay production_armed + an implemented, enabled CEO transport.

    Mirrors the same override ``tests/test_executive_wake_persisted_dispatch.py``
    (``_pair``) applies -- this test file does not arm anything in the real
    registry file, it only overrides an in-memory copy for the fixture.
    """

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
    observer = _compose(
        repo, dispatcher, parent, emitted_at=lambda: "2026-08-30T04:00:00Z"
    )

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


def test_restart_recomputes_from_ledger_not_memory(tmp_path) -> None:
    # Each life mints a DIFFERENT emitted_at.  emitted_at is outside
    # IDENTITY_PAYLOAD_KEYS (control_plane/wake_ledger.py) so this still
    # dedups by identity -- and it makes the assertion a real regression
    # guard against an envelope-equivalence check that (wrongly) folds
    # emitted_at into identity, rather than a test that would pass even if
    # both lives happened to mint identical second-truncated timestamps.
    first_repo = _repo(tmp_path)
    first_dispatcher = _Dispatcher(repo=first_repo)
    parent = _parent()
    first_observer = _compose(
        first_repo,
        first_dispatcher,
        parent,
        emitted_at=lambda: "2026-08-30T04:00:00Z",
    )
    first = _run(
        first_observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )
    assert first.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert first_dispatcher.nudge_calls == 1

    second_repo = _repo(tmp_path)
    second_dispatcher = _Dispatcher(repo=second_repo)
    second_observer = _compose(
        second_repo,
        second_dispatcher,
        parent,
        emitted_at=lambda: "2026-08-30T09:59:59Z",
    )

    second = _run(
        second_observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert second.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
    assert second.reason == "WAKE_OBLIGATION_ALREADY_RECORDED"
    assert second.obligation is not None
    assert first.obligation is not None
    assert second.obligation.obligation_id == first.obligation.obligation_id
    assert second_dispatcher.nudge_calls == 0


def test_same_process_duplicate_suppressed_after_submit(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher(repo=repo)
    observer = _compose(repo, dispatcher, parent)

    first = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )
    second = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert first.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert second.outcome is ObservationOutcome.DUPLICATE_SUPPRESSED
    assert second.reason == "ATTENTION_IDENTITY_ALREADY_SUBMITTED"
    assert dispatcher.nudge_calls == 1


def test_transport_outage_holds_effect_unknown_across_restart(tmp_path) -> None:
    # Distinct emitted_at per life, same rationale as
    # test_restart_recomputes_from_ledger_not_memory above: emitted_at is
    # outside IDENTITY_PAYLOAD_KEYS, so dedup still holds, and this makes the
    # hold a real regression guard rather than one that would also pass with
    # both lives minting identical second-truncated timestamps.
    parent = _parent()
    first_repo = _repo(tmp_path)
    failing_dispatcher = _Dispatcher(failure=TimeoutError("provider response lost"))
    first_observer = _compose(
        first_repo,
        failing_dispatcher,
        parent,
        emitted_at=lambda: "2026-08-30T04:00:00Z",
    )

    first = _run(
        first_observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert first.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
    assert first.reason == "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD"
    assert failing_dispatcher.nudge_calls == 1
    assert first.obligation is not None
    assert _phases(first_repo, first.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]

    second_repo = _repo(tmp_path)
    clean_dispatcher = _Dispatcher(repo=second_repo)
    second_observer = _compose(
        second_repo,
        clean_dispatcher,
        parent,
        emitted_at=lambda: "2026-08-30T09:59:59Z",
    )

    second = _run(
        second_observer.reconcile_once(
            context=_context(parent), routing=_routing(parent)
        )
    )

    assert second.outcome is ObservationOutcome.EFFECT_UNKNOWN_HOLD
    assert second.reason == "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD"
    assert clean_dispatcher.nudge_calls == 0
    assert second.obligation is not None
    assert second.obligation.obligation_id == first.obligation.obligation_id
    # The reconcile READ path must never append a ledger row of its own --
    # phases stay exactly what the first life's failed delivery attempt left
    # behind.
    assert _phases(second_repo, second.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]


def test_target_drift_fails_closed_pre_submit(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    rotated = _binding(generation=2, binding_id="bind-codexwake02")
    observer = _compose(repo, dispatcher, parent, current_binding=rotated)

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "WAKE_TARGET_UNAVAILABLE"
    assert receipt.obligation is not None
    assert _phases(repo, receipt.obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
    ]
    assert dispatcher.nudge_calls == 0


def test_unbound_target_refused_without_persistence(tmp_path) -> None:
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


def test_slack_outage_is_reconciliation_incomplete_without_persistence(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    client = InMemorySlackClient(relay_bot_user_id="U0RELAY001")
    from integrations.slack_agent_dialogue.contract_v2 import render_parent_v2
    from integrations.slack_agent_dialogue.engine import SlackMessage

    client.add_parent(
        SlackMessage(
            ts="1787961600.000001",
            author_user_id="U0PARENT001",
            text=render_parent_v2(parent),
        )
    )
    client.thread_history_complete = False
    observer = compose_persisted_turn_observer(
        policy=_policy(),
        client=client,
        registry=_armed_ceo_registry(),
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: _binding(),
        retry_policy=_POLICY,
        binding_for=_ceo_binding_for,
    )

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert receipt.reason == "BOUNDED_HISTORY_INCOMPLETE"
    assert receipt.obligation is None
    assert dispatcher.nudge_calls == 0


def test_active_waiter_suppressed_before_any_persistence(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher()
    observer = compose_persisted_turn_observer(
        policy=_policy(),
        client=_client_with_result(parent),
        registry=_armed_ceo_registry(),
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: _binding(),
        retry_policy=_POLICY,
        binding_for=_ceo_binding_for,
        has_active_waiter=lambda *_: True,
    )

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.ACTIVE_WAITER_SUPPRESSED
    assert receipt.obligation is not None
    assert repo.list_records(receipt.obligation.obligation_id) == ()
    assert dispatcher.nudge_calls == 0


def test_no_provider_native_handle_leaks_into_receipt_or_ledger(tmp_path) -> None:
    parent = _parent()
    repo = _repo(tmp_path)
    dispatcher = _Dispatcher(repo=repo)
    binding = _binding()
    observer = _compose(repo, dispatcher, parent, current_binding=binding)

    receipt = _run(
        observer.reconcile_once(context=_context(parent), routing=_routing(parent))
    )

    assert receipt.outcome is ObservationOutcome.WAKE_SUBMITTED
    assert receipt.obligation is not None
    native_handle = binding.native_handle
    assert native_handle  # sanity: the fixture binding actually carries one

    # One strong, future-proof assertion instead of two narrower ones that
    # were each tautological today: repr(receipt) covers obligation + route
    # + reason + decision together, and would fail if ObservationReceipt or
    # WakeRoute (control_plane/session_targets.py) ever grew a field that
    # carries native_handle -- unlike asserting today's known-absent field
    # by name, or asserting against a reason string that is a fixed
    # constant and could never have contained it.
    assert native_handle not in repr(receipt)

    # WakeRoute (control_plane/session_targets.py) carries no native_handle
    # field at all -- session_alias/binding_id/binding_generation are the
    # only identity on the route.  WakeNudge is what carries native_handle
    # onward to the transport dispatcher by design; that hop is out of this
    # test's scope.
    route_dict = dataclasses.asdict(receipt.route)
    serialized_route = json.dumps(route_dict, default=str)
    assert native_handle not in serialized_route

    records = repo.list_records(receipt.obligation.obligation_id)
    assert records
    for item in records:
        serialized_payload = json.dumps(item.event.payload, default=str)
        assert native_handle not in serialized_payload
