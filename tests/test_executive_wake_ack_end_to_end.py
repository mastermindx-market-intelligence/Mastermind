"""Hermetic exact-session Wake ACK1 vertical over the real Executive owners."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane import wake_ack_ingress
from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import StateConflict
from control_plane.runtime_binding_projection import project_runtime_binding
from control_plane.session_targets import (
    SCHEMA as TARGET_SCHEMA,
    SessionTargetRegistry,
    route_obligation,
)
from control_plane.wake_ack_ingress import (
    TrustedWorkerWakeAckProjection,
    WakeAckClaim,
    WakeAckIngressError,
    acknowledge_consumed_wakes,
)
from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeNudge,
    WakeTransportCompletion,
    dispatch_persisted_nudge,
)
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import (
    LedgerPhase,
    ObligationStatus,
    SourceReadHealth,
    WakeLedgerError,
    WakeRetryPolicy,
    expected_resolution_code,
    reconstruct_status,
    requested_record,
    resolve_source,
    resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from tests.test_runtime_binding_projection import (
    _admitted_runtime,
    _intent,
    _resume_admitted_runtime,
    _target,
)


_POLICY = WakeRetryPolicy(
    max_delivery_attempts=1,
    retry_cooldown_s=1,
    accepted_ttl_s=60,
    target_unavailable_backoff_s=1,
    reenable_on_binding_rotation=False,
    armed=True,
)


def _source_attempt(runtime) -> tuple[str, str, str]:
    runtime.workers.register_worker(
        "worker-source",
        provider="openai-codex",
        account_label="account-source",
        worker_type="fixture",
        capabilities=["read"],
        quota_classes={
            "default": {
                "provider": "openai-codex",
                "capabilities": ["read"],
                "cost_class": "small",
            }
        },
    )
    intent = _intent()
    intent["intent_id"] = "CEO-WAKE-ACK-SOURCE-001"
    intent["objective"] = "Create a distinct source Attempt for Wake ACK proof."
    receipt = submit_intent(runtime, intent)
    root = runtime.jobs.get_job(receipt["job_id"])
    assert root is not None
    planner = runtime.jobs.create_cycle_planner(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-planner:0",
    )
    dispatched = runtime.attempts.dispatch_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1",
        worker_id="worker-source",
    )
    assert dispatched is not None
    return dispatched.attempt.attempt_id, planner.job_id, root.job_id


@dataclasses.dataclass
class _ExactProjectionDispatcher:
    target_attempt_id: str
    process_generation_id: str
    provider_session_id: str
    calls: int = 0
    projection: TrustedWorkerWakeAckProjection | None = None
    transport_id: str = "codex-app-server"

    async def nudge(self, wake: WakeNudge) -> WakeTransportCompletion:
        self.calls += 1
        self.projection = TrustedWorkerWakeAckProjection(
            target_attempt_id=self.target_attempt_id,
            process_generation_id=self.process_generation_id,
            binding_id=wake.binding_id,
            binding_generation=wake.binding_generation,
            provider_session_id=self.provider_session_id,
            provider_native_turn_id="turn-e2e-ack-1",
            nudge_id=wake.nudge_id,
            obligation_ids=tuple(sorted(wake.obligation_ids)),
            terminal_ack_trailer=True,
        )
        return WakeTransportCompletion(
            receipt=TransportReceipt(
                outcome=TransportOutcome.DELIVERED,
                reason_code="delivered",
                created_at="2026-09-01T00:00:00Z",
                details=(("nudge_id", wake.nudge_id),),
            ),
            target_ack_projection=self.projection,
        )


def test_real_vertical_orders_delivery_exact_session_ack_and_source_resolution(
    tmp_path,
    monkeypatch,
) -> None:
    admitted = _admitted_runtime(tmp_path)
    runtime, _dispatch, sealed, _epoch, generation, _process, _profile = admitted
    source_attempt_id, source_job_id, source_root_job_id = _source_attempt(runtime)
    assert source_attempt_id != sealed.attempt_id

    target = dataclasses.replace(
        _target(),
        wake_transport="codex-app-server",
        allowed_transports=("codex-app-server",),
        target_enabled=True,
    )
    registry = SessionTargetRegistry(
        schema=TARGET_SCHEMA,
        lifecycle_authority="executive_os",
        production_armed=True,
        policy_version="wake-ack-e2e",
        default_alias_by_seat={"coo": target.session_alias},
        workstream_alias_by_seat={},
        root_job_bindings={source_root_job_id: {"coo": target.session_alias}},
        targets={target.session_alias: target},
    )
    binding = project_runtime_binding(runtime, sealed.attempt_id, target)
    obligation = mint_obligation(
        wake_kind="job_failed",
        source_kind="executive_inbox_attention",
        source_ref="eia-00000000e2e1",
        declared_target_seat="coo",
        job_id=source_job_id,
        attempt_id=source_attempt_id,
        root_job_id=source_root_job_id,
    )
    route = route_obligation(obligation, registry, binding=binding)
    repo = WakeLedgerRepository(runtime)
    repo.append_record(requested_record(obligation), obligation=obligation)

    resolution = resolve_source(
        obligation,
        code=expected_resolution_code(obligation),
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        snapshot_digest="ab" * 16,
        resolved_at="2026-09-01T00:00:01Z",
    )
    with pytest.raises((WakeLedgerError, StateConflict), match="TARGET_ACKNOWLEDGED"):
        repo.append_record(
            resolved_record(obligation, resolution),
            obligation=obligation,
        )

    connection_evidence: dict[str, object] = {}
    original_project = wake_ack_ingress.project_runtime_binding
    original_append = WakeLedgerRepository.append_records_on_connection

    def observed_project(*args, connection=None, **kwargs):
        assert connection is not None and connection.in_transaction is True
        connection_evidence["project"] = connection
        return original_project(*args, connection=connection, **kwargs)

    def observed_append(self, connection, items, *, actor="wake_fabric"):
        rows = tuple(items)
        if any(record.phase is LedgerPhase.TARGET_ACKNOWLEDGED for record, _ in rows):
            assert connection.in_transaction is True
            connection_evidence["append"] = connection
        return original_append(self, connection, rows, actor=actor)

    monkeypatch.setattr(wake_ack_ingress, "project_runtime_binding", observed_project)
    monkeypatch.setattr(
        WakeLedgerRepository,
        "append_records_on_connection",
        observed_append,
    )

    dispatcher = _ExactProjectionDispatcher(
        target_attempt_id=sealed.attempt_id,
        process_generation_id=generation.process_generation_id,
        provider_session_id=str(binding.native_handle),
    )
    result = asyncio.run(
        dispatch_persisted_nudge(
            repo,
            [(obligation, route)],
            dispatcher=dispatcher,
            binding=binding,
            retry_policy=_POLICY,
            target_registry=registry,
        )
    )

    assert result.state.value == "DELIVERED"
    assert dispatcher.calls == 1
    assert connection_evidence["project"] is connection_evidence["append"]
    records = tuple(item.record for item in repo.list_records(obligation.obligation_id))
    assert [record.phase for record in records] == [
        LedgerPhase.WAKE_REQUESTED,
        LedgerPhase.DELIVERY_ATTEMPT,
        LedgerPhase.DELIVERED,
        LedgerPhase.TARGET_ACKNOWLEDGED,
    ]
    assert reconstruct_status(
        obligation.obligation_id,
        records,
        route=route,
    ) is ObligationStatus.TARGET_ACKNOWLEDGED
    assert dispatcher.projection is not None

    ack_before = records[-1]
    replay = acknowledge_consumed_wakes(
        runtime,
        registry,
        claim=WakeAckClaim(dispatcher.projection.obligation_ids),
        trusted=dispatcher.projection,
    )
    assert replay[0].inserted is False
    records_after_replay = tuple(
        item.record for item in repo.list_records(obligation.obligation_id)
    )
    assert records_after_replay[-1] == ack_before
    assert sum(
        record.phase is LedgerPhase.TARGET_ACKNOWLEDGED
        for record in records_after_replay
    ) == 1

    repo.append_record(
        resolved_record(obligation, resolution),
        obligation=obligation,
    )
    resolved_records = tuple(
        item.record for item in repo.list_records(obligation.obligation_id)
    )
    assert [record.phase for record in resolved_records][-2:] == [
        LedgerPhase.TARGET_ACKNOWLEDGED,
        LedgerPhase.SOURCE_RESOLVED,
    ]
    assert reconstruct_status(
        obligation.obligation_id,
        resolved_records,
        route=route,
    ) is ObligationStatus.SOURCE_RESOLVED

    _runtime, _dispatch2, _sealed2, _epoch2, _g1, generation2, _process2, _profile2 = (
        _resume_admitted_runtime(admitted)
    )
    assert generation2.generation_number == generation.generation_number + 1
    with pytest.raises(WakeAckIngressError, match="binding|process generation"):
        acknowledge_consumed_wakes(
            runtime,
            registry,
            claim=WakeAckClaim(dispatcher.projection.obligation_ids),
            trusted=dispatcher.projection,
        )
    with pytest.raises(WakeAckIngressError, match="target Attempt|RuntimeBinding"):
        acknowledge_consumed_wakes(
            runtime,
            registry,
            claim=WakeAckClaim(dispatcher.projection.obligation_ids),
            trusted=dataclasses.replace(
                dispatcher.projection,
                target_attempt_id=source_attempt_id,
            ),
        )
