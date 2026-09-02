"""RED-first persisted-dispatch contract for Wake PR3 Task 3.

The provider is a narrow fake boundary.  Executive ``events`` persistence,
route/attempt identity, restart behaviour, and the production coordinator are
real.  No provider, credential, host, Slack, or production target is touched.
"""
from __future__ import annotations

import asyncio
import dataclasses
import sqlite3

import pytest

from control_plane import wake_dispatcher
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import RuntimeBinding, route_obligation
from control_plane.wake_ack_ingress import TrustedWorkerWakeAckProjection
from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeDispatchError,
    WakeNudge,
    WakeTransportCompletion,
)
from control_plane.wake_ledger import (
    LedgerPhase,
    WakeRetryPolicy,
    requested_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_router import obligation_from_inbox
from control_plane.wake_events import mint_obligation
from integrations.executive_wake.codex_app_server import (
    CodexAppServerWakeDispatcher,
    CodexWakeDeliveryObservation,
)
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.persisted_wake_carrier import PersistedWakeCarrier
from integrations.slack_agent_dialogue.turn_observer import WakeCarrierState
from tests.test_executive_wake_fabric import _bound_registry, _projected_ceo_items
from tests.test_wake_ack_ingress import _admitted_runtime


_FROZEN = "2026-08-28T09:00:00Z"
_POLICY = WakeRetryPolicy(
    max_delivery_attempts=1,
    retry_cooldown_s=1,
    accepted_ttl_s=60,
    target_unavailable_backoff_s=1,
    reenable_on_binding_rotation=False,
    armed=True,
)


def _dispatch_persisted(*args, **kwargs):
    function = getattr(wake_dispatcher, "dispatch_persisted_nudge")
    return asyncio.run(function(*args, **kwargs))


def _binding(
    *, generation: int = 1, binding_id: str = "bind-codexwake01"
) -> RuntimeBinding:
    return RuntimeBinding(
        session_alias="EXECUTIVE-CEO-A",
        binding_id=binding_id,
        binding_generation=generation,
        native_handle="thread-runtime-only",
        account_label="codex-runtime-only",
        reasoning_surface="codex",
    )


def _codex_registry(alias: str = "EXECUTIVE-CEO-A"):
    registry = _bound_registry()
    target = dataclasses.replace(
        registry.targets[alias],
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        target_enabled=True,
    )
    return dataclasses.replace(
        registry,
        production_armed=True,
        targets={**registry.targets, target.session_alias: target},
    )


def _pair(*, ordinal: int = 0, binding: RuntimeBinding | None = None):
    item = _projected_ceo_items(
        [
            {
                "workstream": f"persisted-wake-{ordinal}",
                "question": f"persisted Wake fixture {ordinal}",
            }
        ]
    )[0]
    obligation = obligation_from_inbox(item)
    registry = _codex_registry()
    resolved_binding = binding or _binding()
    return obligation, route_obligation(
        obligation,
        registry,
        binding=resolved_binding,
    ), resolved_binding


def _seed_requested(repo: WakeLedgerRepository, *pairs) -> None:
    repo.append_records_atomic(
        tuple((requested_record(obligation), obligation) for obligation, _route in pairs)
    )


def test_connection_scoped_wake_access_requires_executive_transaction(tmp_path):
    """Catches a caller bypassing the existing Executive transaction owner."""

    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, _binding_value = _pair()
    record = requested_record(obligation)
    with sqlite3.connect(runtime.store.path) as connection:
        assert connection.in_transaction is False
        with pytest.raises(StateConflict, match="active transaction"):
            repo.list_ledger_records_on_connection(
                connection, obligation.obligation_id
            )
        with pytest.raises(StateConflict, match="active transaction"):
            repo.append_records_on_connection(
                connection,
                ((record, obligation),),
            )


def test_connection_scoped_wake_append_reuses_causal_and_replay_law(tmp_path):
    """Catches a transaction-scoped append skipping causal or replay checks."""

    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, _route, _binding_value = _pair()
    record = requested_record(obligation)
    with runtime.store.transaction() as connection:
        first = repo.append_records_on_connection(
            connection,
            ((record, obligation),),
        )
        replay = repo.append_records_on_connection(
            connection,
            ((record, obligation),),
        )
        listed = repo.list_ledger_records_on_connection(
            connection, obligation.obligation_id
        )
    assert first[0].inserted is True
    assert replay[0].inserted is False
    assert [item.phase for item in listed] == [LedgerPhase.WAKE_REQUESTED]


@dataclasses.dataclass
class _Dispatcher:
    transport_id: str = "codex-app-server"
    outcome: TransportOutcome = TransportOutcome.DELIVERED
    failure: BaseException | None = None
    repo: WakeLedgerRepository | None = None
    emit_projection: bool = False
    nudge_calls: int = 0

    async def nudge(
        self,
        wake: WakeNudge,
    ) -> TransportReceipt | WakeTransportCompletion:
        self.nudge_calls += 1
        if self.repo is not None:
            for obligation_id in wake.obligation_ids:
                phases = [
                    item.record.phase
                    for item in self.repo.list_records(obligation_id)
                ]
                assert LedgerPhase.DELIVERY_ATTEMPT in phases
        if self.failure is not None:
            raise self.failure
        receipt = TransportReceipt(
            outcome=self.outcome,
            reason_code={
                TransportOutcome.ACCEPTED: "accepted",
                TransportOutcome.DELIVERED: "delivered",
                TransportOutcome.FAILED: "transport_failed",
                TransportOutcome.TARGET_UNAVAILABLE: "target_unavailable",
            }[self.outcome],
            created_at=_FROZEN,
            details=(("nudge_id", wake.nudge_id),),
        )
        if not self.emit_projection:
            return receipt
        projection = TrustedWorkerWakeAckProjection(
            target_attempt_id="ATT-" + "1" * 32,
            process_generation_id="generation-persisted-ack-1",
            binding_id=wake.binding_id,
            binding_generation=wake.binding_generation,
            provider_session_id=str(wake.native_handle),
            provider_native_turn_id="turn-persisted-ack-1",
            nudge_id=wake.nudge_id,
            obligation_ids=tuple(sorted(wake.obligation_ids)),
            terminal_ack_trailer=True,
        )
        return WakeTransportCompletion(
            receipt=receipt,
            target_ack_projection=projection,
        )


@dataclasses.dataclass
class _CrashBeforeProvider:
    transport_id: str = "codex-app-server"
    nudge_calls: int = 0

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        raise SystemExit("crash before provider submission")


def test_persisted_dispatch_records_attempt_before_provider_and_terminal_after(tmp_path):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    _seed_requested(repo, (obligation, route))
    dispatcher = _Dispatcher(repo=repo)

    result = _dispatch_persisted(
        repo,
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
    )
    assert result.state == "DELIVERED"
    assert dispatcher.nudge_calls == 1
    assert [item.record.phase for item in repo.list_records(obligation.obligation_id)] == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]


def test_persisted_ack_projection_runs_once_only_after_exact_delivered_append(
    tmp_path,
    monkeypatch,
):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    _seed_requested(repo, (obligation, route))
    dispatcher = _Dispatcher(repo=repo, emit_projection=True)
    registry = _bound_registry()
    calls = []

    def fake_ack(runtime_arg, registry_arg, *, claim, trusted):
        calls.append((runtime_arg, registry_arg, claim, trusted))
        assert [
            item.record.phase for item in repo.list_records(obligation.obligation_id)
        ] == [
            LedgerPhase.WAKE_REQUESTED,
            LedgerPhase.DELIVERY_ATTEMPT,
            LedgerPhase.DELIVERED,
        ]
        return ()

    monkeypatch.setattr(wake_dispatcher, "acknowledge_consumed_wakes", fake_ack)

    first = _dispatch_persisted(
        repo,
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
        target_registry=registry,
    )
    replay = _dispatch_persisted(
        repo,
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
        target_registry=registry,
    )

    assert first.state == replay.state == "DELIVERED"
    assert dispatcher.nudge_calls == 1
    assert len(calls) == 1
    assert calls[0][0] is runtime
    assert calls[0][1] is registry
    assert calls[0][2].obligation_ids == (obligation.obligation_id,)
    assert calls[0][3].obligation_ids == (obligation.obligation_id,)


def test_persisted_ack_projection_without_registry_refuses_after_truthful_delivery(
    tmp_path,
    monkeypatch,
):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    _seed_requested(repo, (obligation, route))
    dispatcher = _Dispatcher(repo=repo, emit_projection=True)
    ack_calls = []
    monkeypatch.setattr(
        wake_dispatcher,
        "acknowledge_consumed_wakes",
        lambda *args, **kwargs: ack_calls.append((args, kwargs)),
    )

    with pytest.raises(WakeDispatchError, match="SessionTargetRegistry"):
        _dispatch_persisted(
            repo,
            [(obligation, route)],
            dispatcher=dispatcher,
            binding=binding,
            retry_policy=_POLICY,
        )

    assert ack_calls == []
    assert [item.record.phase for item in repo.list_records(obligation.obligation_id)] == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
    ]


def test_nonpersisted_generic_path_discards_projection_without_ack_mutation(
    monkeypatch,
):
    obligation, route, binding = _pair()
    dispatcher = _Dispatcher(emit_projection=True)
    ack_calls = []
    monkeypatch.setattr(
        wake_dispatcher,
        "acknowledge_consumed_wakes",
        lambda *args, **kwargs: ack_calls.append((args, kwargs)),
    )

    _nudge, transport, receipts = asyncio.run(
        wake_dispatcher.dispatch_nudge(
            [(obligation, route)],
            dispatcher=dispatcher,
            binding=binding,
            retry_policy=_POLICY,
        )
    )

    assert transport is not None and transport.outcome is TransportOutcome.DELIVERED
    assert receipts[0].outcome.value == "DELIVERED"
    assert ack_calls == []


def test_lost_provider_response_two_outer_invocations_write_provider_once(tmp_path):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    _seed_requested(repo, (obligation, route))
    dispatcher = _Dispatcher(failure=TimeoutError("response lost after write"))

    first = _dispatch_persisted(
        repo,
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
    )
    second = _dispatch_persisted(
        repo,
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
    )

    assert first.state == second.state == "RECONCILIATION_REQUIRED"
    assert first.nudge_id == second.nudge_id
    assert dispatcher.nudge_calls == 1
    assert [item.record.phase for item in repo.list_records(obligation.obligation_id)] == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
    ]


def test_restart_after_attempt_persisted_never_reissues_provider_write(tmp_path):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    _seed_requested(repo, (obligation, route))
    crash = _CrashBeforeProvider()

    with pytest.raises(SystemExit, match="crash before provider submission"):
        _dispatch_persisted(
            repo,
            [(obligation, route)],
            dispatcher=crash,
            binding=binding,
            retry_policy=_POLICY,
        )

    restarted = Runtime.at(tmp_path)
    restarted_repo = WakeLedgerRepository(restarted)
    probe = _Dispatcher()
    result = _dispatch_persisted(
        restarted_repo,
        [(obligation, route)],
        dispatcher=probe,
        binding=binding,
        retry_policy=_POLICY,
    )

    assert result.state == "RECONCILIATION_REQUIRED"
    assert crash.nudge_calls == 0
    assert probe.nudge_calls == 0


def test_unfinished_a1_refuses_rotated_binding_and_destination(tmp_path):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    obligation, route, binding = _pair()
    _seed_requested(repo, (obligation, route))
    dispatcher = _Dispatcher(failure=TimeoutError("effect unknown"))
    first = _dispatch_persisted(
        repo,
        [(obligation, route)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
    )
    rotated = _binding(generation=2, binding_id="bind-codexwake02")
    same_obligation, rotated_route, _ = _pair(binding=rotated)
    assert same_obligation.obligation_id == obligation.obligation_id

    second = _dispatch_persisted(
        repo,
        [(obligation, rotated_route)],
        dispatcher=dispatcher,
        binding=rotated,
        retry_policy=_POLICY,
    )

    assert first.state == second.state == "RECONCILIATION_REQUIRED"
    assert second.nudge_id == first.nudge_id
    assert dispatcher.nudge_calls == 1
    assert all(item.record.attempt_n in (None, 1) for item in repo.list_records(obligation.obligation_id))


def test_unfinished_coalesced_nudge_cannot_split_into_a_new_nudge(tmp_path):
    runtime = Runtime.at(tmp_path)
    repo = WakeLedgerRepository(runtime)
    one, route_one, binding = _pair(ordinal=1)
    two, route_two, _ = _pair(ordinal=2, binding=binding)
    _seed_requested(repo, (one, route_one), (two, route_two))
    dispatcher = _Dispatcher(failure=TimeoutError("coalesced effect unknown"))

    first = _dispatch_persisted(
        repo,
        [(one, route_one), (two, route_two)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
    )
    split = _dispatch_persisted(
        repo,
        [(one, route_one)],
        dispatcher=dispatcher,
        binding=binding,
        retry_policy=_POLICY,
    )

    assert first.state == split.state == "RECONCILIATION_REQUIRED"
    assert split.nudge_id == first.nudge_id
    assert dispatcher.nudge_calls == 1


@dataclasses.dataclass
class _CodexClient:
    calls: int = 0

    async def deliver_wake(self, *, native_handle, nudge_id, opaque_ids, instruction):
        self.calls += 1
        return CodexWakeDeliveryObservation(
            native_handle=native_handle,
            nudge_id=nudge_id,
            accepted=True,
            delivered=True,
        )


@dataclasses.dataclass
class _LateCodexClient:
    target_attempt_id: str
    process_generation_id: str
    binding_id: str
    binding_generation: int
    mode: str = "canonical"
    deliver_calls: int = 0
    reconcile_calls: int = 0

    async def deliver_wake(self, *, native_handle, nudge_id, opaque_ids, instruction):
        self.deliver_calls += 1
        return CodexWakeDeliveryObservation(
            native_handle=native_handle,
            nudge_id=nudge_id,
            accepted=True,
            delivered=False,
        )

    async def reconcile_wake(self, *, native_handle, nudge_id, opaque_ids):
        self.reconcile_calls += 1
        if self.mode == "unknown":
            raise RuntimeError("late status is not recognized")
        if self.mode == "stale":
            return CodexWakeDeliveryObservation(
                native_handle=native_handle,
                nudge_id="NUDGE-" + "f" * 32,
                accepted=True,
                delivered=True,
            )
        if self.mode == "failed":
            return CodexWakeDeliveryObservation(
                native_handle=native_handle,
                nudge_id=nudge_id,
                accepted=True,
                delivered=False,
            )
        projection = None
        if self.mode == "canonical":
            projection = TrustedWorkerWakeAckProjection(
                target_attempt_id=self.target_attempt_id,
                process_generation_id=self.process_generation_id,
                binding_id=self.binding_id,
                binding_generation=self.binding_generation,
                provider_session_id=native_handle,
                provider_native_turn_id="turn-late-ack-1",
                nudge_id=nudge_id,
                obligation_ids=tuple(
                    sorted(item for item in opaque_ids if ":" not in item)
                ),
                terminal_ack_trailer=True,
            )
        return CodexWakeDeliveryObservation(
            native_handle=native_handle,
            nudge_id=nudge_id,
            accepted=True,
            delivered=True,
            target_ack_projection=projection,
        )


def _late_carrier_fixture(tmp_path, *, mode: str = "canonical"):
    runtime, sealed, generation = _admitted_runtime(tmp_path)
    repo = WakeLedgerRepository(runtime)
    registry = _codex_registry("PROPHET-COO-A")
    binding = project_runtime_binding(
        runtime,
        sealed.attempt_id,
        registry.targets["PROPHET-COO-A"],
    )
    obligation = mint_obligation(
        wake_kind="job_failed",
        source_kind="executive_inbox_attention",
        source_ref="eia-0000000000aa",
        declared_target_seat="coo",
        root_job_id="JOB-001",
    )
    route = route_obligation(obligation, registry, binding=binding)
    client = _LateCodexClient(
        target_attempt_id=sealed.attempt_id,
        process_generation_id=generation.process_generation_id,
        binding_id=binding.binding_id,
        binding_generation=binding.binding_generation,
        mode=mode,
    )
    dispatcher = CodexAppServerWakeDispatcher(client)
    carrier = PersistedWakeCarrier(
        repository=repo,
        dispatchers=WakeDispatcherRegistry({"codex-app-server": dispatcher}),
        current_binding_for=lambda _route: binding,
        retry_policy=_POLICY,
        target_registry=registry,
    )
    return repo, obligation, route, binding, client, carrier


def test_timeout_then_late_canonical_completion_persists_one_delivery_and_ack(
    tmp_path,
):
    """Catches ACCEPTED swallowing a late exact completion and its canonical ACK."""

    repo, obligation, route, binding, client, carrier = _late_carrier_fixture(tmp_path)

    asyncio.run(carrier.submit(obligation, route))
    assert [item.record.phase for item in repo.list_records(obligation.obligation_id)] == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.ACCEPTED,
    ]

    assert asyncio.run(carrier.reconcile(obligation, route)) is WakeCarrierState.RECORDED
    assert [item.record.phase for item in repo.list_records(obligation.obligation_id)] == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.ACCEPTED,
        LedgerPhase.DELIVERED,
        LedgerPhase.TARGET_ACKNOWLEDGED,
    ]

    assert asyncio.run(carrier.reconcile(obligation, route)) is WakeCarrierState.RECORDED
    assert client.deliver_calls == 1
    assert client.reconcile_calls == 1
    assert binding.native_handle is not None


@pytest.mark.parametrize(
    ("mode", "expected_state", "expected_tail"),
    [
        ("malformed", WakeCarrierState.RECORDED, (LedgerPhase.ACCEPTED, LedgerPhase.DELIVERED)),
        ("failed", WakeCarrierState.EFFECT_UNKNOWN, (LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED)),
        ("stale", WakeCarrierState.EFFECT_UNKNOWN, (LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED)),
        ("unknown", WakeCarrierState.EFFECT_UNKNOWN, (LedgerPhase.DELIVERY_ATTEMPT, LedgerPhase.ACCEPTED)),
    ],
)
def test_late_controls_never_resubmit_or_manufacture_ack(
    tmp_path,
    mode,
    expected_state,
    expected_tail,
):
    repo, obligation, route, _binding_value, client, carrier = _late_carrier_fixture(
        tmp_path,
        mode=mode,
    )

    asyncio.run(carrier.submit(obligation, route))
    state = asyncio.run(carrier.reconcile(obligation, route))
    phases = tuple(
        item.record.phase for item in repo.list_records(obligation.obligation_id)
    )

    assert state is expected_state
    assert phases[-2:] == expected_tail
    assert LedgerPhase.TARGET_ACKNOWLEDGED not in phases
    assert client.deliver_calls == 1
    assert client.reconcile_calls == 1


def test_concrete_codex_dispatcher_composes_through_generic_fabric():
    obligation, route, binding = _pair()
    client = _CodexClient()
    dispatcher = CodexAppServerWakeDispatcher(client)

    nudge, transport, receipts = asyncio.run(
        wake_dispatcher.dispatch_nudge(
            [(obligation, route)],
            dispatcher=dispatcher,
            binding=binding,
            retry_policy=_POLICY,
        )
    )

    assert nudge is not None
    assert transport is not None and transport.outcome is TransportOutcome.DELIVERED
    assert receipts[0].outcome.value == "DELIVERED"
    assert client.calls == 1
