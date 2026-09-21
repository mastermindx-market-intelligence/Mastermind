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
from control_plane.wake_ledger import (
    AckMode,
    LedgerPhase,
    TrustedAckContext,
    ack_record,
    acknowledge,
)
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

def _persist_generic_reasoning_ack_group(fixture) -> None:
    claims = tuple(sorted(item.obligation_id for item in fixture.obligations))
    rows = []
    for obligation in fixture.obligations:
        records = tuple(
            item.record
            for item in fixture.repository.list_records(obligation.obligation_id)
        )
        delivered = next(
            record for record in records if record.phase is LedgerPhase.DELIVERED
        )
        ack = acknowledge(
            obligation,
            trusted=TrustedAckContext(
                ack_mode=AckMode.REASONING_SESSION,
                target_seat=obligation.declared_target_seat,
                session_alias=str(delivered.session_alias),
                reasoning_surface=str(delivered.reasoning_surface),
                binding_id=str(delivered.binding_id),
                binding_generation=int(delivered.binding_generation),
            ),
            claimed_obligation_ids=claims,
            delivered_command_id=delivered.command_id,
        )
        rows.append((ack_record(obligation, ack), None))
    fixture.repository.append_records_atomic(tuple(rows))


def test_durable_replay_refuses_generic_reasoning_ack_without_web_sol_provenance(
    tmp_path,
) -> None:
    fixture = _fixture(tmp_path, obligation_count=2)
    _persist_generic_reasoning_ack_group(fixture)
    never = _NeverDispatcher()

    replay = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            _pairs(fixture),
            dispatcher=never,
            binding=fixture.binding,
        )
    )

    assert replay.state is PersistedDeliveredAckState.HOLD
    assert replay.reason == "SEMANTIC_ACK_NOT_PROVEN"
    assert never.calls == 0


def test_first_web_sol_persistence_keeps_privacy_safe_semantic_provenance(tmp_path) -> None:
    fixture = _fixture(tmp_path, obligation_count=2)
    result = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            _pairs(fixture),
            dispatcher=_Dispatcher(fixture.trusted, fixture.lease),
            binding=fixture.binding,
        )
    )
    assert result.state is PersistedDeliveredAckState.RECORDED

    provenances = []
    for obligation in fixture.obligations:
        row = _ack_rows(fixture, obligation.obligation_id)[0].record
        provenance = getattr(row.ack, "semantic_provenance", None)
        assert provenance is not None
        provenances.append(provenance)
        payload = row.ack and row.ack.__dict__
        rendered = repr(payload)
        assert fixture.trusted.native_handle not in rendered
        assert fixture.trusted.provider_native_turn_id not in rendered
    assert provenances[0] == provenances[1]
    assert provenances[0].producer_kind == "web_sol_semantic_ack"
    assert provenances[0].nudge_id == fixture.nudge_id



def _persist_human_ack_group(fixture) -> None:
    claims = tuple(sorted(item.obligation_id for item in fixture.obligations))
    rows = []
    for obligation in fixture.obligations:
        ack = acknowledge(
            obligation,
            trusted=TrustedAckContext(
                ack_mode=AckMode.HUMAN_OPERATOR,
                target_seat=obligation.declared_target_seat,
                session_alias=fixture.binding.session_alias,
                reasoning_surface="human",
                operator_authority_receipt="OP-WEB-SOL-LEGACY-01",
            ),
            claimed_obligation_ids=claims,
        )
        rows.append((ack_record(obligation, ack), None))
    fixture.repository.append_records_atomic(tuple(rows))


def test_durable_replay_refuses_human_ack_as_web_sol_semantic_proof(tmp_path) -> None:
    fixture = _fixture(tmp_path, obligation_count=2)
    _persist_human_ack_group(fixture)
    never = _NeverDispatcher()

    replay = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            _pairs(fixture),
            dispatcher=never,
            binding=fixture.binding,
        )
    )

    assert replay.state is PersistedDeliveredAckState.HOLD
    assert replay.reason == "SEMANTIC_ACK_NOT_PROVEN"
    assert never.calls == 0


def test_persisted_web_sol_ack_event_contains_only_digest_provenance(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    result = asyncio.run(
        reconcile_persisted_delivered_ack(
            fixture.repository,
            _pairs(fixture),
            dispatcher=_Dispatcher(fixture.trusted, fixture.lease),
            binding=fixture.binding,
        )
    )
    assert result.state is PersistedDeliveredAckState.RECORDED

    events = fixture.runtime.events.list_events(
        aggregate_type="wake",
        aggregate_id=fixture.obligations[0].obligation_id,
    )
    event = next(item for item in events if item.event_type == "TARGET_ACKNOWLEDGED")
    rendered = repr(event.payload)
    assert fixture.trusted.native_handle not in rendered
    assert fixture.trusted.provider_native_turn_id not in rendered
    provenance = event.payload["semantic_provenance"]
    assert provenance["producer_kind"] == "web_sol_semantic_ack"
    assert len(provenance["provider_turn_digest"]) == 64
    assert len(provenance["native_host_life_digest"]) == 64
