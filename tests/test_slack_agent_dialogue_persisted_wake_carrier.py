from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.dialogue_wake_canary_activation import (
    DialogueWakeCanaryActivationGrant,
    DialogueWakeCanaryProfile,
    SCHEMA as CANARY_SCHEMA,
    effective_dialogue_wake_canary_route,
)
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.session_targets import RuntimeBinding
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import LedgerPhase, requested_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    CanaryWakeHistoryError,
    HistoricalWakeContext,
    PersistedWakeCarrier,
)
from integrations.slack_agent_dialogue.turn_observer import (
    DialogueTurnObserver,
    ObservationOutcome,
    WakeCarrierState,
)
from tests.test_executive_wake_persisted_dispatch import (
    _Dispatcher,
    _POLICY,
    _binding,
    _pair,
)
from tests.test_slack_agent_dialogue_turn_observer import (
    _client_with_result as _dialogue_client_with_result,
    _context as _dialogue_context,
    _parent as _dialogue_parent,
    _policy as _dialogue_policy,
    _registry as _dialogue_registry,
    _routing as _dialogue_routing,
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


def _canary(obligation, route, **overrides):
    values = {
        "schema": CANARY_SCHEMA,
        "installed_release_sha": "a" * 40,
        "operation_key": "runtime-continuity-r2-test",
        "source_root_job_id": "JOB-900",
        "source_job_id": "JOB-901",
        "source_attempt_id": "ATT-" + "6" * 32,
        "source_worker_id": "worker-test",
        "source_semantic_digest": "b" * 64,
        "obligation_id": obligation.obligation_id,
        "target_seat": route.target_seat,
        "target_session_alias": route.session_alias,
        "target_attempt_id": "ATT-" + "7" * 32,
        "binding_id": route.binding_id,
        "binding_generation": route.binding_generation,
        "process_generation_id": "generation-test-1",
        "policy_digest": route.policy_digest,
        "valid_from_epoch_seconds": 1_700_000_000,
        "expires_at_epoch_seconds": 1_700_000_600,
    }
    values.update(overrides)
    grant = DialogueWakeCanaryActivationGrant(**values)
    profile = DialogueWakeCanaryProfile(grant)
    from control_plane.session_targets import route_digest

    base = dataclasses.replace(
        route,
        production_armed=False,
        target_enabled=False,
        policy_digest=grant.policy_digest,
        route_digest=route_digest(
            obligation_id=route.obligation_id,
            destination=route.destination_digest,
            policy_digest=grant.policy_digest,
        ),
    )
    return profile, effective_dialogue_wake_canary_route(profile, base)


@pytest.mark.parametrize("outcome", ["FAILED", "TARGET_UNAVAILABLE"])
def test_canary_known_negative_history_is_recorded_without_retry(tmp_path, outcome) -> None:
    from control_plane.wake_dispatcher import TransportOutcome

    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    profile, effective = _canary(obligation, route)
    dispatcher = _Dispatcher(outcome=TransportOutcome(outcome), repo=repo)
    carrier = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
        canary_profile=profile,
    )

    _run(carrier.submit(obligation, effective))
    before = tuple(_phases(repo, obligation.obligation_id))
    _run(carrier.submit(obligation, effective))
    assert tuple(_phases(repo, obligation.obligation_id)) == before
    assert dispatcher.nudge_calls == 1


def test_null_or_changed_canary_grant_cannot_erase_persisted_effect(tmp_path) -> None:
    from control_plane.wake_dispatcher import TransportOutcome

    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    profile, effective = _canary(obligation, route)
    dispatcher = _Dispatcher(outcome=TransportOutcome.FAILED, repo=repo)
    seeded = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
        canary_profile=profile,
    )
    _run(seeded.submit(obligation, effective))
    before = tuple(_phases(repo, obligation.obligation_id))
    forbidden_calls = 0

    def forbidden(_route):
        nonlocal forbidden_calls
        forbidden_calls += 1
        return binding

    null = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=forbidden,
        retry_policy=_POLICY,
        canary_profile=DialogueWakeCanaryProfile(None),
    )
    with pytest.raises(CanaryWakeHistoryError):
        _run(null.reconcile(obligation, effective))
    changed, _changed_route = _canary(obligation, route, policy_digest="c" * 16)
    drifted = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=forbidden,
        retry_policy=_POLICY,
        canary_profile=changed,
    )
    with pytest.raises(CanaryWakeHistoryError):
        _run(drifted.reconcile(obligation, effective))
    assert tuple(_phases(repo, obligation.obligation_id)) == before
    assert forbidden_calls == 0


def test_canary_accepted_history_resolves_original_context_lazily(tmp_path) -> None:
    from control_plane.wake_dispatcher import TransportOutcome, TransportReceipt
    from control_plane.wake_events import utc_now_iso

    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    profile, effective = _canary(obligation, route)
    first = _Dispatcher(outcome=TransportOutcome.ACCEPTED, repo=repo)
    submitted = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": first}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
        canary_profile=profile,
    )
    _run(submitted.submit(obligation, effective))

    class HistoricalDispatcher:
        transport_id = "codex-app-server"
        calls = 0

        async def reconcile(self, wake):
            self.calls += 1
            return TransportReceipt(
                outcome=TransportOutcome.DELIVERED,
                reason_code="delivered",
                created_at=utc_now_iso(),
                details=(("nudge_id", wake.nudge_id),),
            )

    historical = HistoricalDispatcher()
    resolver_calls = 0

    def resolve(attempt):
        nonlocal resolver_calls
        resolver_calls += 1
        assert attempt.matches_route(effective)
        return HistoricalWakeContext(
            dispatchers=WakeDispatcherRegistry({"codex-app-server": historical}),
            runtime_binding=binding,
        )

    replay = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=lambda _route: (_ for _ in ()).throw(
            AssertionError("historical replay cannot consult current binding")
        ),
        retry_policy=_POLICY,
        canary_profile=profile,
        historical_context_for=resolve,
    )
    assert _run(
        replay.reconcile(
            obligation,
            dataclasses.replace(route, production_armed=False, target_enabled=False),
        )
    ) is WakeCarrierState.RECORDED
    assert resolver_calls == 1
    assert historical.calls == 1
    assert first.nudge_calls == 1
    assert _phases(repo, obligation.obligation_id).count(LedgerPhase.DELIVERY_ATTEMPT) == 1


def _phases(repo, obligation_id):
    return [item.record.phase for item in repo.list_records(obligation_id)]


def _remint(obligation, **overrides):
    fields = {
        "wake_kind": obligation.wake_kind,
        "source_kind": obligation.source_kind,
        "source_ref": obligation.source_ref,
        "declared_target_seat": obligation.declared_target_seat,
        "job_id": obligation.job_id,
        "attempt_id": obligation.attempt_id,
        "root_job_id": obligation.root_job_id,
        "workstream": obligation.workstream,
        "source_workstream": obligation.source_workstream,
        "source_created_at": obligation.source_created_at,
        "emitted_at": obligation.emitted_at,
    }
    fields.update(overrides)
    return mint_obligation(**fields)


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

    with pytest.raises(WakePreSubmitError, match="current RuntimeBinding"):
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


def test_observer_binding_movement_is_reconciliation_incomplete_not_crash(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    parent = _dialogue_parent()
    current = RuntimeBinding(
        session_alias="EXECUTIVE-CEO-A",
        binding_id="bind-observer01",
        binding_generation=1,
        native_handle="thread-observer-current",
        reasoning_surface="chatgpt-sol",
    )
    rotated = RuntimeBinding(
        session_alias="EXECUTIVE-CEO-A",
        binding_id="bind-observer02",
        binding_generation=2,
        native_handle="thread-observer-rotated",
        reasoning_surface="chatgpt-sol",
    )
    carrier = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry(),
        current_binding_for=lambda _route: rotated,
        retry_policy=_POLICY,
    )
    observer = DialogueTurnObserver(
        policy=_dialogue_policy(),
        client=_dialogue_client_with_result(parent),
        registry=_dialogue_registry(),
        wake_carrier=carrier,
        binding_for=lambda seat: current if seat == "ceo" else None,
        emitted_at=lambda: "2026-08-29T02:00:00Z",
    )

    first = _run(
        observer.reconcile_once(
            context=_dialogue_context(parent),
            routing=_dialogue_routing(parent),
        )
    )
    second = _run(
        observer.reconcile_once(
            context=_dialogue_context(parent),
            routing=_dialogue_routing(parent),
        )
    )

    assert first.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert first.reason == "WAKE_TARGET_UNAVAILABLE"
    assert second.outcome is ObservationOutcome.RECONCILIATION_INCOMPLETE
    assert second.reason == "WAKE_TARGET_UNAVAILABLE"
    assert first.obligation is not None
    assert _phases(repo, first.obligation.obligation_id) == [LedgerPhase.WAKE_REQUESTED]


@pytest.mark.parametrize(
    "mutation",
    [
        {"declared_target_seat": "coo"},
        {"job_id": "JOB-777", "root_job_id": "JOB-777"},
        {"attempt_id": "ATT-" + ("cd" * 16)},
        {"workstream": "changed_stream"},
        {"source_workstream": "changed-source-stream"},
    ],
)
def test_requested_only_reconcile_refuses_same_id_frozen_envelope_drift(
    tmp_path, mutation
) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    repo.append_record(requested_record(obligation), obligation=obligation)
    mutated = _remint(obligation, **mutation)
    assert mutated.obligation_id == obligation.obligation_id
    before = repo.get_by_command_id(obligation.obligation_id)
    dispatcher = _Dispatcher()
    carrier = _carrier(repo, dispatcher, binding)

    with pytest.raises(StateConflict, match="payload disagrees|correlation disagrees"):
        _run(carrier.reconcile(mutated, route))

    after = repo.get_by_command_id(obligation.obligation_id)
    assert before is not None and after is not None
    assert before.event.payload == after.event.payload
    assert dispatcher.nudge_calls == 0
    assert _phases(repo, obligation.obligation_id) == [LedgerPhase.WAKE_REQUESTED]


@pytest.mark.parametrize(
    "mutation",
    [
        {"declared_target_seat": "coo"},
        {"job_id": "JOB-777", "root_job_id": "JOB-777"},
        {"attempt_id": "ATT-" + ("ef" * 16)},
        {"workstream": "changed_stream"},
    ],
)
def test_requested_only_submit_refuses_same_id_frozen_envelope_drift_before_dispatch(
    tmp_path, mutation
) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    repo.append_record(requested_record(obligation), obligation=obligation)
    mutated = _remint(obligation, **mutation)
    assert mutated.obligation_id == obligation.obligation_id
    before = repo.get_by_command_id(obligation.obligation_id)
    dispatcher = _Dispatcher()
    carrier = _carrier(repo, dispatcher, binding)

    with pytest.raises(StateConflict, match="payload disagrees|correlation disagrees"):
        _run(carrier.submit(mutated, route))

    after = repo.get_by_command_id(obligation.obligation_id)
    assert before is not None and after is not None
    assert before.event.payload == after.event.payload
    assert dispatcher.nudge_calls == 0
    assert _phases(repo, obligation.obligation_id) == [LedgerPhase.WAKE_REQUESTED]


def test_terminal_reconcile_refuses_same_id_frozen_envelope_drift(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    dispatcher = _Dispatcher(repo=repo)
    carrier = _carrier(repo, dispatcher, binding)
    _run(carrier.submit(obligation, route))
    assert dispatcher.nudge_calls == 1
    mutated = _remint(obligation, declared_target_seat="coo")
    assert mutated.obligation_id == obligation.obligation_id

    with pytest.raises(StateConflict, match="payload disagrees|correlation disagrees"):
        _run(carrier.reconcile(mutated, route))

    assert dispatcher.nudge_calls == 1
    assert _phases(repo, obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]


def test_timestamp_only_semantic_replay_remains_submit_eligible(tmp_path) -> None:
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    repo.append_record(requested_record(obligation), obligation=obligation)
    replay = _remint(
        obligation,
        source_created_at="2026-08-30T04:00:00Z",
        emitted_at="2026-08-30T04:01:00Z",
    )
    assert replay.obligation_id == obligation.obligation_id
    dispatcher = _Dispatcher(repo=repo)
    carrier = _carrier(repo, dispatcher, binding)

    assert _run(carrier.reconcile(replay, route)) is WakeCarrierState.MISSING
    _run(carrier.submit(replay, route))

    assert dispatcher.nudge_calls == 1
    persisted = repo.get_by_command_id(obligation.obligation_id)
    assert persisted is not None
    assert persisted.obligation == obligation
    assert _phases(repo, obligation.obligation_id) == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]
