from __future__ import annotations

import asyncio
import dataclasses

from control_plane.session_targets import (
    SCHEMA as TARGET_SCHEMA,
    SessionTargetRegistry,
    route_obligation,
)
from control_plane.wake_dispatcher import (
    PersistedDeliveredAckState,
    TransportOutcome,
    TransportReceipt,
    WakeTransportCompletion,
    WebSolWakeAckCompletion,
    reconcile_persisted_delivered_ack,
)
from control_plane.wake_events import utc_now_iso
from tests.test_web_sol_wake_ack_ingress import (
    _ack_rows,
    _fixture,
    _lease,
    _logical_target,
    _ROTATED_BOOT_NONCE,
)


def _registry() -> SessionTargetRegistry:
    target = _logical_target()
    return SessionTargetRegistry(
        schema=TARGET_SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=True,
        policy_version="web-sol-wake-ack-test",
        default_alias_by_seat={"ceo": target.session_alias},
        workstream_alias_by_seat={},
        root_job_bindings={},
        targets={target.session_alias: target},
    )


def _pairs(fixture):
    registry = _registry()
    return tuple(
        (
            obligation,
            route_obligation(obligation, registry, binding=fixture.binding),
        )
        for obligation in fixture.obligations
    )


@dataclasses.dataclass
class _Dispatcher:
    projection: object
    lease: object
    calls: int = 0

    transport_id = "chatgpt-gui"

    async def reconcile_delivered_ack(self, wake):
        self.calls += 1
        return WakeTransportCompletion(
            receipt=TransportReceipt(
                outcome=TransportOutcome.DELIVERED,
                reason_code="delivered",
                created_at=utc_now_iso(),
                details=(("nudge_id", wake.nudge_id),),
            ),
            target_ack_projection=WebSolWakeAckCompletion(
                projection=self.projection,
                runtime_binding_lease=self.lease,
            ),
        )


class _NeverDispatcher:
    transport_id = "chatgpt-gui"
    calls = 0

    async def reconcile_delivered_ack(self, _wake):
        self.calls += 1
        raise AssertionError("durable ACK replay must not touch the provider")


def test_complete_coalesced_web_sol_ack_records_once_and_replays_without_provider(
    tmp_path,
) -> None:
    fixture = _fixture(tmp_path, obligation_count=2)
    pairs = _pairs(fixture)
    dispatcher = _Dispatcher(fixture.trusted, fixture.lease)
    result = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            pairs,
            dispatcher=dispatcher,
            binding=fixture.binding,
        )
    )
    assert result.state is PersistedDeliveredAckState.RECORDED
    assert result.reason == "ACK_RECORDED"
    assert dispatcher.calls == 1
    assert all(
        len(_ack_rows(fixture, obligation.obligation_id)) == 1
        for obligation in fixture.obligations
    )

    never = _NeverDispatcher()
    replay = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            pairs,
            dispatcher=never,
            binding=dataclasses.replace(
                fixture.binding,
                binding_generation=fixture.binding.binding_generation + 1,
            ),
        )
    )
    assert replay.state is PersistedDeliveredAckState.RECORDED
    assert replay.reason == "ACK_ALREADY_RECORDED"
    assert never.calls == 0


def test_wrong_nudge_or_obligation_projection_holds_without_partial_ack(tmp_path) -> None:
    fixture = _fixture(tmp_path, obligation_count=2)
    pairs = _pairs(fixture)
    wrong = dataclasses.replace(
        fixture.trusted,
        nudge_id="NUDGE-" + "f" * 32,
    )
    result = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            pairs,
            dispatcher=_Dispatcher(wrong, fixture.lease),
            binding=fixture.binding,
        )
    )
    assert result.state is PersistedDeliveredAckState.HOLD
    assert result.reason == "ACK_PROJECTION_REFUSED"
    assert all(
        _ack_rows(fixture, obligation.obligation_id) == ()
        for obligation in fixture.obligations
    )


def test_rotated_live_lease_holds_before_first_ack_persistence(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    rotated = _lease(boot_nonce=_ROTATED_BOOT_NONCE)
    result = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            _pairs(fixture),
            dispatcher=_Dispatcher(fixture.trusted, rotated),
            binding=fixture.binding,
        )
    )
    assert result.state is PersistedDeliveredAckState.HOLD
    assert result.reason == "ACK_PROJECTION_REFUSED"
    assert _ack_rows(fixture, fixture.obligations[0].obligation_id) == ()
