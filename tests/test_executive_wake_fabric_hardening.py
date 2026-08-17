"""Wake Fabric final-hardening adversarial matrix (PR #82).

Contracts only.  No live transport, no SQLite wake writes, no MCP ACK tool.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
from pathlib import Path

import pytest

from control_plane.executive_inbox import project_needs_ceo
from control_plane.executive_runtime import Event, Job, JobStatus
from control_plane.session_targets import (
    RouteRefusalError,
    RuntimeBinding,
    SessionTargetError,
    evaluate_delivery_allowed,
    load_session_targets,
    route_obligation,
)
from control_plane.wake_dispatcher import (
    DISPATCHER_INTERFACE_VERSION,
    RECEIPT_SCHEMA,
    TransportOutcome,
    TransportReceipt,
    WakeDispatchError,
    WakeNudge,
    WakeOutcome,
    WakeReceipt,
    authenticate_receipt,
    coalesce_nudge,
    dispatch_nudge,
    make_receipt,
    plan_eligible_nudge,
    wake_transport_descriptor,
)
from control_plane.wake_events import (
    SourceKind,
    WakeKind,
    WakeObligationError,
    mint_obligation,
    runtime_source_ref,
)
from control_plane.wake_ledger import (
    AckMode,
    LedgerPhase,
    ObligationStatus,
    SourceReadHealth,
    TrustedAckContext,
    UNARMED_RETRY_POLICY,
    WAKE_AGGREGATE_TYPE,
    WakeLedgerError,
    WakeLedgerRecord,
    acknowledge,
    assert_causal,
    eligible_for_nudge,
    ledger_command_id,
    make_delivery_attempt,
    next_attempt_n,
    parse_ledger_record,
    reconstruct_status,
    requested_record,
    resolve_source,
    resolved_record,
    unfinished_attempt_n,
)
from control_plane.wake_router import (
    WakeAction,
    WakeRouter,
    admit_inbox_projection,
    admit_runtime_review_source,
    obligation_from_inbox,
    obligation_from_runtime,
)
from control_plane.wake_transport import WAKE_TRANSPORT_DESCRIPTORS
from integrations.executive_mcp.schemas import TOOL_SPECS, tool_names
from tests.test_executive_wake_fabric import (
    _BIND,
    _FROZEN,
    _JOB,
    _ack_row,
    _binding,
    _bound_registry,
    _ceo_pending,
    _inbox,
    _router,
)


def _arm(route):
    return dataclasses.replace(
        route,
        production_armed=True,
        target_enabled=True,
        transport_implemented=True,
        binding_ready=True,
        human_required=False,
    )


def _armed_descriptor(transport: str):
    return dataclasses.replace(
        wake_transport_descriptor(transport),
        transport_implemented=True,
    )


def _job(**overrides) -> Job:
    fields = dict(
        job_id=_JOB,
        objective="complete the reviewed builder",
        department="research",
        priority=0,
        status=JobStatus.COMPLETED,
        assigned_worker_id=None,
        assigned_quota_class=None,
        authority_level="worker",
        branch=None,
        worktree=None,
        checkpoint=None,
        result=None,
        created_at=_FROZEN,
        updated_at=_FROZEN,
        root_job_id=_JOB,
        owner_seat="coo",
        review_required=True,
        reviews_job_id=None,
    )
    fields.update(overrides)
    return Job(**fields)


def _event(job: Job, **overrides) -> Event:
    fields = dict(
        event_id=1,
        aggregate_type="job",
        aggregate_id=job.job_id,
        sequence=4,
        event_type="JOB_COMPLETED",
        command_id="CMD-1",
        actor="test",
        job_id=job.job_id,
        attempt_id=None,
        worker_id=None,
        quota_class=None,
        payload={"objective": job.objective, "next_actions": ["wake the CEO"]},
        created_at=_FROZEN,
    )
    fields.update(overrides)
    return Event(**fields)


def _receipt_kwargs(obligation, route, **overrides):
    fields = dict(
        schema=RECEIPT_SCHEMA,
        outcome=WakeOutcome.DELIVERED,
        obligation_id=obligation.obligation_id,
        attempt_n=1,
        attempt_command_id=ledger_command_id(
            obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=1
        ),
        session_alias=route.session_alias,
        reasoning_surface=route.reasoning_surface,
        wake_transport=route.wake_transport,
        route_digest=route.route_digest,
        destination_digest=route.destination_digest,
        binding_id=route.binding_id,
        binding_generation=route.binding_generation,
        transport_implemented=route.transport_implemented,
        target_enabled=route.target_enabled,
        production_armed=route.production_armed,
        interface_version=route.interface_version,
        reason_code="delivered",
        created_at=_FROZEN,
        details=(),
    )
    fields.update(overrides)
    return fields


def test_source_admission_succeeds_with_no_route():
    unbound = load_session_targets()
    item = _inbox(root_job_id="JOB-009", job_id="JOB-009")
    obligation = obligation_from_inbox(item)
    assert obligation.obligation_id.startswith("WAKE-")
    with pytest.raises(RouteRefusalError, match="no binding for seat"):
        route_obligation(obligation, unbound)
    decision = WakeRouter(unbound).from_inbox(item)
    assert decision.action is WakeAction.UNROUTABLE
    assert decision.obligation is not None
    assert decision.obligation.obligation_id == obligation.obligation_id
    assert decision.route is None


def test_same_obligation_routes_after_binding_is_registered():
    unbound = load_session_targets()
    item = _inbox(root_job_id="JOB-009", job_id="JOB-009")
    first = obligation_from_inbox(item)
    with pytest.raises(RouteRefusalError):
        route_obligation(first, unbound)
    bound = unbound.with_root_job_bindings(
        {"JOB-009": {"coo": "PROPHET-COO-B", "ceo": "EXECUTIVE-CEO-A"}}
    )
    later = obligation_from_inbox(item)
    assert later.obligation_id == first.obligation_id
    route = route_obligation(later, bound)
    assert route.session_alias == "PROPHET-COO-B"
    assert route.obligation_id == first.obligation_id


def test_runtime_unroutable_source_still_mints_then_routes_same_id():
    job = _job(job_id="JOB-009", root_job_id="JOB-009")
    fact = admit_runtime_review_source(event=_event(job), job=job, sibling_jobs=())
    obligation = obligation_from_runtime(fact)
    assert obligation is not None
    unbound = load_session_targets()
    with pytest.raises(RouteRefusalError):
        route_obligation(obligation, unbound)
    bound = unbound.with_root_job_bindings({"JOB-009": {"coo": "PROPHET-COO-B"}})
    again = obligation_from_runtime(fact)
    assert again is not None
    assert again.obligation_id == obligation.obligation_id
    assert route_obligation(again, bound).session_alias == "PROPHET-COO-B"


def test_same_root_has_distinct_coo_ceo_chairman_bindings():
    registry = load_session_targets().with_root_job_bindings(
        {
            "JOB-001": {
                "coo": "PROPHET-COO-B",
                "ceo": "EXECUTIVE-CEO-A",
                "chairman": "EXECUTIVE-CHAIRMAN-A",
            }
        }
    )
    coo = obligation_from_inbox(_inbox(root_job_id=_JOB))
    ceo_item = dict(_ceo_pending())
    ceo_item["root_job_id"] = _JOB
    ceo = obligation_from_inbox(ceo_item)
    chairman = obligation_from_inbox(
        _inbox(target="chairman", root_job_id=_JOB, reason="chairman decision")
    )
    coo_route = route_obligation(coo, registry)
    ceo_route = route_obligation(ceo, registry)
    chair_route = route_obligation(chairman, registry)
    assert coo_route.session_alias == "PROPHET-COO-B"
    assert ceo_route.session_alias == "EXECUTIVE-CEO-A"
    assert chair_route.session_alias == "EXECUTIVE-CHAIRMAN-A"
    assert chair_route.human_required is True
    assert chair_route.delivery_allowed is False
    assert chair_route.binding_generation == 0


def test_public_route_api_cannot_override_seat_root_or_workstream():
    sig = inspect.signature(route_obligation)
    assert list(sig.parameters) == ["obligation", "registry", "binding"]
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    route = route_obligation(obligation, _bound_registry())
    assert route.target_seat == "coo"
    assert route.root_job_id == _JOB


def test_mismatched_runtime_binding_alias_and_surface_refuse():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    registry = _bound_registry()
    with pytest.raises(SessionTargetError, match="session_alias"):
        route_obligation(
            obligation,
            registry,
            binding=_binding(alias="EXECUTIVE-CEO-A", binding_id="bind-test000000aa"),
        )
    with pytest.raises(SessionTargetError, match="reasoning_surface"):
        route_obligation(
            obligation,
            registry,
            binding=_binding(surface="codex"),
        )


def test_bool_float_and_zero_binding_generation_refuse():
    with pytest.raises(SessionTargetError, match="actual integer"):
        RuntimeBinding(session_alias="PROPHET-COO-A", binding_id=_BIND, binding_generation=True)
    with pytest.raises(SessionTargetError, match="actual integer"):
        RuntimeBinding(session_alias="PROPHET-COO-A", binding_id=_BIND, binding_generation=1.5)
    with pytest.raises(SessionTargetError, match=">= 1"):
        RuntimeBinding(session_alias="PROPHET-COO-A", binding_id=_BIND, binding_generation=0)


def test_binding_aba_identity_does_not_match_a_later_replacement():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    registry = _bound_registry()
    first_life = route_obligation(
        obligation, registry, binding=_binding(generation=1, binding_id="bind-life00000001")
    )
    second_life = route_obligation(
        obligation, registry, binding=_binding(generation=1, binding_id="bind-life00000002")
    )
    assert first_life.binding_generation == second_life.binding_generation == 1
    assert first_life.destination_digest != second_life.destination_digest
    assert first_life.route_digest != second_life.route_digest


def test_production_armed_is_a_global_kill_switch():
    assert evaluate_delivery_allowed(
        production_armed=False,
        target_enabled=True,
        transport_implemented=True,
        binding_ready=True,
        human_required=False,
        requires_runtime_binding=True,
    ) is False
    assert evaluate_delivery_allowed(
        production_armed=True,
        target_enabled=True,
        transport_implemented=False,
        binding_ready=True,
        human_required=False,
        requires_runtime_binding=True,
    ) is False
    assert evaluate_delivery_allowed(
        production_armed=True,
        target_enabled=False,
        transport_implemented=True,
        binding_ready=True,
        human_required=False,
        requires_runtime_binding=True,
    ) is False
    assert evaluate_delivery_allowed(
        production_armed=True,
        target_enabled=True,
        transport_implemented=True,
        binding_ready=False,
        human_required=False,
        requires_runtime_binding=True,
    ) is False
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    assert route.production_armed is False
    assert route.delivery_allowed is False
    assert load_session_targets().production_armed is False
    assert all(not target.target_enabled for target in load_session_targets().targets.values())
    assert all(not item.transport_implemented for item in WAKE_TRANSPORT_DESCRIPTORS.values())


def test_a1_receipt_cannot_close_a2_or_a_different_route():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    registry = _bound_registry()
    r1 = route_obligation(obligation, registry, binding=_binding(generation=1))
    r2 = route_obligation(
        obligation, registry, binding=_binding(generation=2, binding_id="bind-test00000002")
    )
    a1 = make_delivery_attempt(obligation, r1, attempt_n=1)
    a2 = make_delivery_attempt(obligation, r1, attempt_n=2)
    a1_r2 = make_delivery_attempt(obligation, r2, attempt_n=1)
    receipt = make_receipt(
        outcome=WakeOutcome.FAILED,
        obligation=obligation,
        route=r1,
        reason_code="transport_failed",
        created_at=_FROZEN,
        attempt=a1,
    )
    with pytest.raises(WakeDispatchError, match="attempt_n"):
        authenticate_receipt(
            receipt, obligation=obligation, route=r1, descriptor=wake_transport_descriptor(r1.wake_transport), attempt=a2
        )
    with pytest.raises(WakeDispatchError, match="route|destination|binding"):
        authenticate_receipt(
            receipt, obligation=obligation, route=r2, descriptor=wake_transport_descriptor(r2.wake_transport), attempt=a1_r2
        )


def test_dispatcher_receives_validated_runtime_address_without_source_prose():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    binding = _binding()
    object.__setattr__(binding, "native_handle", "native-tab-a")
    object.__setattr__(binding, "account_label", "sol-account")
    route = _arm(route_obligation(obligation, _bound_registry(), binding=binding))
    seen: list[WakeNudge] = []

    class Probe:
        async def nudge(self, wake: WakeNudge) -> TransportReceipt:
            seen.append(wake)
            return TransportReceipt(
                outcome=TransportOutcome.FAILED,
                reason_code="transport_failed",
                created_at=_FROZEN,
            )

    asyncio.run(
        dispatch_nudge(
            [(obligation, route)],
            dispatcher=Probe(),
            binding=binding,
            descriptor=_armed_descriptor(route.wake_transport),
        )
    )
    assert len(seen) == 1
    wake = seen[0]
    assert wake.native_handle == "native-tab-a"
    assert wake.session_alias == "PROPHET-COO-A"
    assert obligation.obligation_id in wake.obligation_ids
    payload = dataclasses.asdict(wake)
    joined = " ".join(str(value) for value in payload.values())
    assert "complete the reviewed" not in joined
    assert "wake the CEO" not in joined
    assert "next_actions" not in payload
    assert "objective" not in payload
    names = {field.name for field in dataclasses.fields(WakeNudge)}
    assert names.isdisjoint({"objective", "result", "worker_prose", "next_actions", "authority_level"})


def test_five_obligations_one_mock_adapter_invocation():
    router = _router()
    pairs = []
    for index in range(5):
        decision = router.from_inbox(_inbox(reason=f"attempt failed {index}", ordinal=index, root_job_id=_JOB))
        assert decision.obligation is not None and decision.route is not None
        pairs.append(
            (
                decision.obligation,
                _arm(route_obligation(decision.obligation, _bound_registry(), binding=_binding())),
            )
        )

    class Counter:
        calls = 0

        async def nudge(self, wake: WakeNudge) -> TransportReceipt:
            Counter.calls += 1
            assert len(wake.obligation_ids) == 5
            return TransportReceipt(
                outcome=TransportOutcome.FAILED,
                reason_code="transport_failed",
                created_at=_FROZEN,
            )

    nudge, transport, receipts = asyncio.run(
        dispatch_nudge(
            pairs,
            dispatcher=Counter(),
            binding=_binding(),
            descriptor=_armed_descriptor(pairs[0][1].wake_transport),
        )
    )
    assert Counter.calls == 1
    assert transport is not None
    assert len(nudge.attempts) == 5
    assert len(receipts) == 5


def test_mixed_destinations_cannot_coalesce_and_closed_obligations_are_excluded():
    registry = _bound_registry()
    w1 = obligation_from_inbox(_inbox(reason="one", ordinal=0, root_job_id=_JOB))
    w2 = obligation_from_inbox(_inbox(reason="two", ordinal=1, root_job_id=_JOB))
    w3 = obligation_from_inbox(_inbox(reason="three", ordinal=2, root_job_id=_JOB))
    w4 = obligation_from_inbox(_inbox(reason="four", ordinal=3, root_job_id=_JOB))
    w5 = obligation_from_inbox(_inbox(reason="five", ordinal=4, root_job_id=_JOB))
    r1 = route_obligation(w1, registry, binding=_binding())
    r2 = route_obligation(w2, registry, binding=_binding())
    r3 = route_obligation(w3, registry, binding=_binding())
    r4 = route_obligation(w4, registry, binding=_binding())
    r5 = route_obligation(w5, registry, binding=_binding())
    other = route_obligation(
        w1, registry, binding=_binding(generation=8, binding_id="bind-test00000008")
    )
    with pytest.raises(WakeDispatchError, match="destination"):
        coalesce_nudge([r1, other])
    requested = {
        w1.obligation_id: [requested_record(w1)],
        w2.obligation_id: [requested_record(w2)],
        w3.obligation_id: [
            requested_record(w3),
            resolved_record(
                w3,
                resolve_source(
                    w3,
                    health=SourceReadHealth.HEALTHY,
                    source_present=False,
                    reason="sibling review job exists",
                    resolved_at=_FROZEN,
                ),
            ),
        ],
        w4.obligation_id: [requested_record(w4)],
        w5.obligation_id: [requested_record(w5), _ack_row(w5)],
    }
    plan = plan_eligible_nudge([r1, r2, r3, r4, r5], requested)
    assert list(plan.obligation_ids) == [w1.obligation_id, w2.obligation_id, w4.obligation_id]
    assert w3.obligation_id not in plan.obligation_ids
    assert w5.obligation_id not in plan.obligation_ids
    assert eligible_for_nudge(w3.obligation_id, requested[w3.obligation_id]) is False
    assert eligible_for_nudge(w5.obligation_id, requested[w5.obligation_id]) is False


def test_adapter_authored_already_delivered_and_contradictory_receipts_refuse():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    descriptor = wake_transport_descriptor(route.wake_transport)
    forged = WakeReceipt(**_receipt_kwargs(obligation, route, outcome=WakeOutcome.ALREADY_DELIVERED, reason_code="command_id_replay"))
    with pytest.raises(WakeDispatchError, match="fabric outcome"):
        authenticate_receipt(forged, obligation=obligation, route=route, descriptor=descriptor)
    contradictory = WakeReceipt(**_receipt_kwargs(obligation, route, reason_code="target_unavailable"))
    with pytest.raises(WakeDispatchError, match="pairing"):
        authenticate_receipt(contradictory, obligation=obligation, route=route, descriptor=descriptor)
    accepted_wrong = WakeReceipt(**_receipt_kwargs(obligation, route, outcome=WakeOutcome.ACCEPTED, reason_code="delivered"))
    with pytest.raises(WakeDispatchError, match="pairing"):
        authenticate_receipt(accepted_wrong, obligation=obligation, route=route, descriptor=descriptor)


def test_direct_dataclass_receipt_adversarial_matrix():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    other = obligation_from_inbox(_ceo_pending())
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    other_route = route_obligation(other, _bound_registry())
    descriptor = wake_transport_descriptor(route.wake_transport)
    cases = [
        ("obligation_id", {"obligation_id": other.obligation_id}),
        ("session_alias", {"session_alias": "EXECUTIVE-CEO-A"}),
        ("reasoning_surface", {"reasoning_surface": "codex"}),
        ("wake_transport", {"wake_transport": "chatgpt-gui"}),
        ("route_digest", {"route_digest": other_route.route_digest}),
        ("destination_digest", {"destination_digest": other_route.destination_digest}),
        ("binding_generation", {"binding_generation": 9}),
        ("binding_id", {"binding_id": "bind-test00000009"}),
        ("target_enabled", {"target_enabled": True}),
        ("interface version", {"interface_version": "mastermind.wake_dispatcher/v0"}),
        ("created_at", {"created_at": "yesterday"}),
        ("attempt_n", {"attempt_n": 2, "attempt_command_id": ledger_command_id(obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=2)}),
    ]
    for label, overrides in cases:
        receipt = WakeReceipt(**_receipt_kwargs(obligation, route, **overrides))
        with pytest.raises(WakeDispatchError):
            authenticate_receipt(
                receipt,
                obligation=obligation,
                route=route,
                descriptor=descriptor,
                attempt=make_delivery_attempt(obligation, route, attempt_n=1),
            )
        _ = label
    unknown_detail = WakeReceipt(
        **_receipt_kwargs(
            obligation,
            route,
            outcome=WakeOutcome.FAILED,
            reason_code="transport_failed",
            details=(("error_url", "https://provider.example/secret"),),
        )
    )
    with pytest.raises(WakeDispatchError, match="closed typed set"):
        authenticate_receipt(unknown_detail, obligation=obligation, route=route, descriptor=descriptor)
    assert DISPATCHER_INTERFACE_VERSION == "mastermind.wake_dispatcher/v1"


def test_command_id_phase_and_route_snapshot_invariants():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    with pytest.raises(WakeLedgerError, match="command_id"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(obligation.obligation_id, LedgerPhase.TARGET_ACKNOWLEDGED),
                phase=LedgerPhase.DELIVERED,
                attempt_n=1,
                route_digest=route.route_digest,
                destination_digest=route.destination_digest,
                session_alias=route.session_alias,
                reasoning_surface=route.reasoning_surface,
                wake_transport=route.wake_transport,
            )
        )
    with pytest.raises(WakeLedgerError, match="route snapshot"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    obligation.obligation_id, LedgerPhase.DELIVERED, attempt_n=1
                ),
                phase=LedgerPhase.DELIVERED,
                attempt_n=1,
            )
        )
    with pytest.raises(WakeLedgerError, match="attempt_n|route/native"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=obligation.obligation_id,
                phase=LedgerPhase.WAKE_REQUESTED,
                attempt_n=1,
                binding_id="bind-test00000001",
            )
        )
    with pytest.raises(WakeLedgerError, match="acknowledgement evidence"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    obligation.obligation_id, LedgerPhase.TARGET_ACKNOWLEDGED
                ),
                phase=LedgerPhase.TARGET_ACKNOWLEDGED,
            )
        )
    with pytest.raises(WakeLedgerError, match="native"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=1
                ),
                phase=LedgerPhase.DELIVERY_ATTEMPT,
                attempt_n=1,
                route_digest=route.route_digest,
                destination_digest=route.destination_digest,
                session_alias=route.session_alias,
                reasoning_surface=route.reasoning_surface,
                wake_transport=route.wake_transport,
                native_handle="thread-secret",
            )
        )


def test_ack_requires_trusted_context_not_model_identity_claim():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    with pytest.raises(WakeLedgerError, match="binding context"):
        acknowledge(
            obligation,
            trusted=TrustedAckContext(
                ack_mode=AckMode.REASONING_SESSION,
                target_seat="coo",
                session_alias="PROPHET-COO-A",
                reasoning_surface="chatgpt-sol",
                acknowledged_at=_FROZEN,
            ),
            claimed_obligation_ids=[obligation.obligation_id],
        )
    human = acknowledge(
        obligation,
        trusted=TrustedAckContext(
            ack_mode=AckMode.HUMAN_OPERATOR,
            target_seat="chairman",
            session_alias="EXECUTIVE-CHAIRMAN-A",
            reasoning_surface="human",
            acknowledged_at=_FROZEN,
        ),
        claimed_obligation_ids=[obligation.obligation_id],
    )
    assert human.ack_mode is AckMode.HUMAN_OPERATOR
    rotated = acknowledge(
        obligation,
        trusted=TrustedAckContext(
            ack_mode=AckMode.REASONING_SESSION,
            target_seat="coo",
            session_alias="PROPHET-COO-A",
            reasoning_surface="chatgpt-sol",
            binding_id="bind-rotated00008",
            acknowledged_at=_FROZEN,
        ),
        claimed_obligation_ids=[obligation.obligation_id],
    )
    assert rotated.binding_id == "bind-rotated00008"


def test_review_wake_source_resolved_after_sibling_review_appears():
    builder = _job(job_id="JOB-010", root_job_id="JOB-010")
    fact = admit_runtime_review_source(event=_event(builder), job=builder, sibling_jobs=())
    obligation = obligation_from_runtime(fact)
    assert obligation is not None
    review = _job(
        job_id="JOB-011",
        root_job_id="JOB-010",
        owner_seat="coo",
        review_required=False,
        reviews_job_id=builder.job_id,
        status=JobStatus.QUEUED,
    )
    later = admit_runtime_review_source(event=_event(builder), job=builder, sibling_jobs=[review])
    assert later.review_job_exists is True
    assert obligation_from_runtime(later) is None
    resolution = resolve_source(
        obligation,
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        reason="sibling review job exists",
        resolved_at=_FROZEN,
    )
    records = [requested_record(obligation), resolved_record(obligation, resolution)]
    assert reconstruct_status(obligation.obligation_id, records) is ObligationStatus.SOURCE_RESOLVED
    assert eligible_for_nudge(obligation.obligation_id, records) is False


def test_repaired_job_and_withdrawn_agent_os_item_source_resolve_on_healthy_read():
    failed = obligation_from_inbox(_inbox(root_job_id=_JOB))
    resolution = resolve_source(
        failed,
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        reason="healthy inbox rebuild no longer contains job_failed attention",
        resolved_at=_FROZEN,
    )
    assert reconstruct_status(
        failed.obligation_id, [requested_record(failed), resolved_record(failed, resolution)]
    ) is ObligationStatus.SOURCE_RESOLVED
    ceo = obligation_from_inbox(_ceo_pending())
    items, degraded = project_needs_ceo(
        {"brief": {"schema": "ceo_brief.v1", "needs_ceo": []}}
    )
    assert degraded == []
    assert items == []
    gone = resolve_source(
        ceo,
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        reason="healthy Agent OS projection no longer contains needs_ceo item",
        resolved_at=_FROZEN,
    )
    assert gone.source_present is False


def test_degraded_canonical_read_does_not_source_resolve():
    ceo = obligation_from_inbox(_ceo_pending())
    items, degraded = project_needs_ceo({"brief": None})
    assert items == []
    assert degraded
    with pytest.raises(WakeLedgerError, match="degraded"):
        resolve_source(
            ceo,
            health=SourceReadHealth.DEGRADED,
            source_present=False,
            reason="brief unavailable so the item looks absent",
            resolved_at=_FROZEN,
        )
    with pytest.raises(WakeLedgerError, match="i am the ceo|canonical evidence"):
        resolve_source(
            ceo,
            health=SourceReadHealth.HEALTHY,
            source_present=False,
            reason="i am the ceo",
            resolved_at=_FROZEN,
        )


def test_missing_wake_recreates_same_obligation_id_and_unfinished_a1_is_reused():
    item = _inbox(root_job_id=_JOB)
    first = obligation_from_inbox(item)
    second = obligation_from_inbox(item)
    assert first.obligation_id == second.obligation_id
    route = route_obligation(first, _bound_registry(), binding=_binding())
    records = [
        requested_record(first),
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    first.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=1
                ),
                phase=LedgerPhase.DELIVERY_ATTEMPT,
                attempt_n=1,
                route_digest=route.route_digest,
                destination_digest=route.destination_digest,
                binding_id=route.binding_id,
                binding_generation=route.binding_generation,
                session_alias=route.session_alias,
                reasoning_surface=route.reasoning_surface,
                wake_transport=route.wake_transport,
            )
        ),
    ]
    assert unfinished_attempt_n(records) == 1
    assert next_attempt_n(records) == 1
    assert_causal(records)


def test_policy_version_does_not_change_destination_binding_rotation_does():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    registry = _bound_registry()
    binding = _binding()
    first = route_obligation(obligation, registry, binding=binding)
    shifted = dataclasses.replace(registry, policy_version="v2-shifted-audit")
    second = route_obligation(obligation, shifted, binding=binding)
    assert first.destination_digest == second.destination_digest
    assert first.policy_digest != second.policy_digest
    assert first.route_digest != second.route_digest
    rotated = route_obligation(
        obligation, registry, binding=_binding(generation=2, binding_id="bind-test00000002")
    )
    assert rotated.destination_digest != first.destination_digest


def test_source_workstream_is_inert_and_malformed_runtime_workstream_does_not_seat_default():
    items, degraded = project_needs_ceo(
        {"brief": {"schema": "ceo_brief.v1", "needs_ceo": [{"workstream": "WS:PROPHET-FUSION", "question": "rule?"}]}}
    )
    assert degraded == []
    admitted = admit_inbox_projection(items[0])
    assert admitted.source_workstream == "WS:PROPHET-FUSION"
    assert admitted.workstream is None
    decision = _router().from_inbox(items[0])
    assert decision.obligation is not None
    assert decision.obligation.source_workstream == "WS:PROPHET-FUSION"
    assert decision.obligation.routing_workstream is None
    assert decision.route is not None
    assert decision.route.session_alias == "EXECUTIVE-CEO-A"
    job = _job(job_id="JOB-099", root_job_id="JOB-099")
    fact = admit_runtime_review_source(event=_event(job), job=job)
    fact = dataclasses.replace(fact, source_workstream="WS:PROPHET-FUSION")
    obligation = obligation_from_runtime(fact)
    assert obligation is not None
    with pytest.raises(RouteRefusalError, match="no binding for seat"):
        route_obligation(obligation, load_session_targets())


def test_runtime_review_source_ref_must_be_matching_job_not_worker_or_attempt():
    with pytest.raises(WakeObligationError, match="runtime:job"):
        mint_obligation(
            wake_kind=WakeKind.REVIEW_REQUIRED,
            source_kind=SourceKind.EXECUTIVE_RUNTIME_EVENT,
            source_ref="runtime:worker:foo:1",
            declared_target_seat="coo",
            job_id=_JOB,
            root_job_id=_JOB,
        )
    with pytest.raises(WakeObligationError, match="runtime:job"):
        mint_obligation(
            wake_kind=WakeKind.REVIEW_REQUIRED,
            source_kind=SourceKind.EXECUTIVE_RUNTIME_EVENT,
            source_ref="runtime:attempt:ATT-1:1",
            declared_target_seat="coo",
            job_id=_JOB,
            root_job_id=_JOB,
        )
    with pytest.raises(WakeObligationError, match="job_id must match"):
        mint_obligation(
            wake_kind=WakeKind.REVIEW_REQUIRED,
            source_kind=SourceKind.EXECUTIVE_RUNTIME_EVENT,
            source_ref=runtime_source_ref(aggregate_type="job", aggregate_id=_JOB, sequence=4),
            declared_target_seat="coo",
            job_id="JOB-002",
            root_job_id=_JOB,
        )


def test_real_phase1f_typed_admission_derives_owner_and_review_from_jobs():
    builder = _job()
    event = _event(builder)
    fact = admit_runtime_review_source(event=event, job=builder, sibling_jobs=())
    assert fact.owner_seat == "coo"
    assert fact.review_job_exists is False
    assert fact.root_job_id == _JOB
    hijack = dataclasses.replace(builder, owner_seat="ceo", escalation_target="chairman")
    derived = admit_runtime_review_source(event=_event(hijack), job=hijack, sibling_jobs=())
    assert derived.owner_seat == "ceo"
    review = _job(job_id="JOB-012", reviews_job_id=builder.job_id, review_required=False)
    exists = admit_runtime_review_source(event=event, job=builder, sibling_jobs=[review])
    assert exists.review_job_exists is True
    with pytest.raises(Exception):
        admit_runtime_review_source(
            event=dataclasses.replace(event, aggregate_type="attempt"),
            job=builder,
        )


def test_retry_policy_remains_unarmed_and_ledger_aggregate_is_wake():
    assert UNARMED_RETRY_POLICY.armed is False
    assert UNARMED_RETRY_POLICY.max_delivery_attempts is None
    assert WAKE_AGGREGATE_TYPE == "wake"
    assert len(TOOL_SPECS) == 5
    assert "acknowledge_ceo_wake" not in tool_names()


def test_causal_rules_refuse_delivery_before_requested():
    obligation = obligation_from_inbox(_inbox(root_job_id=_JOB))
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    attempt = make_delivery_attempt(obligation, route, attempt_n=1)
    with pytest.raises(WakeLedgerError, match="REQUESTED must precede"):
        assert_causal(
            [
                parse_ledger_record(
                    WakeLedgerRecord(
                        command_id=attempt.attempt_command_id,
                        phase=LedgerPhase.DELIVERY_ATTEMPT,
                        attempt_n=1,
                        route_digest=route.route_digest,
                        destination_digest=route.destination_digest,
                        binding_id=route.binding_id,
                        binding_generation=route.binding_generation,
                        session_alias=route.session_alias,
                        reasoning_surface=route.reasoning_surface,
                        wake_transport=route.wake_transport,
                    )
                )
            ]
        )
