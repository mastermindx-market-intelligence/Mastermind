"""RED-first persisted-dispatch contract for Wake PR3 Task 3.

The provider is a narrow fake boundary.  Executive ``events`` persistence,
route/attempt identity, restart behaviour, and the production coordinator are
real.  No provider, credential, host, Slack, or production target is touched.
"""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane import wake_dispatcher
from control_plane.executive_runtime import Runtime
from control_plane.session_targets import RuntimeBinding, route_obligation
from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeNudge,
)
from control_plane.wake_ledger import (
    LedgerPhase,
    WakeRetryPolicy,
    requested_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_router import obligation_from_inbox
from integrations.executive_wake.codex_app_server import (
    CodexAppServerWakeDispatcher,
    CodexWakeDeliveryObservation,
)
from tests.test_executive_wake_fabric import _bound_registry, _projected_ceo_items


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
    registry = _bound_registry()
    target = dataclasses.replace(
        registry.targets["EXECUTIVE-CEO-A"],
        reasoning_surface="codex",
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        target_enabled=True,
    )
    registry = dataclasses.replace(
        registry,
        production_armed=True,
        targets={**registry.targets, target.session_alias: target},
    )
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


@dataclasses.dataclass
class _Dispatcher:
    transport_id: str = "codex-app-server"
    outcome: TransportOutcome = TransportOutcome.DELIVERED
    failure: BaseException | None = None
    repo: WakeLedgerRepository | None = None
    nudge_calls: int = 0

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
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
        return TransportReceipt(
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
