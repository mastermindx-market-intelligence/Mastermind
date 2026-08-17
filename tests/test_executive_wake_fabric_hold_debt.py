"""Wake Fabric HOLD-debt adversarial matrix (COO review 4948286293).

Contracts only.  Direct dataclass construction and persisted-record parsing,
not only helper-created objects.
"""
from __future__ import annotations

import asyncio

import pytest

from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeDispatchError,
    WakeNudge,
    already_delivered_receipt,
    authenticate_transport_receipt,
    dispatch_nudge,
    mint_nudge_id,
    plan_eligible_nudge,
)
from control_plane.wake_events import SourceKind, WakeKind
from control_plane.wake_ledger import (
    AckMode,
    LedgerPhase,
    SourceReadHealth,
    SourceResolution,
    SourceResolutionCode,
    TrustedAckContext,
    UNARMED_RETRY_POLICY,
    WakeAcknowledgement,
    WakeLedgerError,
    WakeLedgerRecord,
    WakeRetryPolicy,
    acknowledge,
    assert_causal,
    attempt_record,
    eligible_for_nudge,
    expected_resolution_code,
    ledger_command_id,
    make_delivery_attempt,
    parse_ledger_record,
    requested_record,
    resolve_source,
)
from control_plane.wake_router import (
    CanonicalInboxAttention,
    CanonicalRuntimeFact,
    WakeRouterError,
    admit_inbox_projection,
    obligation_from_inbox,
)
from tests.test_executive_wake_fabric import (
    _FROZEN,
    _JOB,
    _binding,
    _bound_registry,
    _closed_resolution,
    _inbox,
)
from tests.test_executive_wake_fabric_hardening import _arm, _armed_descriptor
from control_plane.session_targets import route_obligation


def test_forged_canonical_types_are_not_user_constructible():
    with pytest.raises(WakeRouterError, match="not user-constructible"):
        CanonicalInboxAttention(
            attention_id="eia-" + ("ab" * 6),
            kind="job_failed",
            target="coo",
            source="runtime",
        )
    with pytest.raises(WakeRouterError, match="not user-constructible"):
        CanonicalRuntimeFact(
            aggregate_type="job",
            aggregate_id=_JOB,
            sequence=4,
            event_type="JOB_COMPLETED",
            owner_seat="coo",
            review_job_exists=False,
        )


def test_inbox_source_workstream_is_inert_and_does_not_auto_promote():
    admitted = admit_inbox_projection(_inbox(workstream="prophet"))
    assert admitted.workstream is None
    assert admitted.source_workstream == "prophet"
    obligation = obligation_from_inbox(admitted)
    assert obligation.workstream is None
    assert obligation.source_workstream == "prophet"


def test_requested_record_freezes_obligation_envelope():
    obligation = obligation_from_inbox(_inbox())
    record = requested_record(obligation)
    assert record.obligation is not None
    assert record.obligation.to_dict() == obligation.to_dict()
    with pytest.raises(WakeLedgerError, match="frozen obligation envelope"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=obligation.obligation_id,
                phase=LedgerPhase.WAKE_REQUESTED,
            )
        )
    with pytest.raises(WakeLedgerError, match="route/native"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=obligation.obligation_id,
                phase=LedgerPhase.WAKE_REQUESTED,
                obligation=obligation,
                reasoning_surface="chatgpt-sol",
                binding_generation=1,
            )
        )


def test_attempt_n_parser_refuses_bool_and_float():
    obligation = obligation_from_inbox(_inbox())
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    with pytest.raises(WakeLedgerError, match="attempt_n"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=1
                ),
                phase=LedgerPhase.DELIVERY_ATTEMPT,
                attempt_n=True,
                route_digest=route.route_digest,
                destination_digest=route.destination_digest,
                session_alias=route.session_alias,
                reasoning_surface=route.reasoning_surface,
                wake_transport=route.wake_transport,
            )
        )
    with pytest.raises(WakeLedgerError, match="attempt_n"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    obligation.obligation_id, LedgerPhase.DELIVERY_ATTEMPT, attempt_n=1
                ),
                phase=LedgerPhase.DELIVERY_ATTEMPT,
                attempt_n=1.5,  # type: ignore[arg-type]
                route_digest=route.route_digest,
                destination_digest=route.destination_digest,
                session_alias=route.session_alias,
                reasoning_surface=route.reasoning_surface,
                wake_transport=route.wake_transport,
            )
        )


def test_causal_machine_refuses_mixed_stream_and_unfinished_a2():
    w1 = obligation_from_inbox(_inbox(reason="one", ordinal=0))
    w2 = obligation_from_inbox(_inbox(reason="two", ordinal=1))
    with pytest.raises(WakeLedgerError, match="single obligation"):
        assert_causal([requested_record(w1), requested_record(w2)])
    route = route_obligation(w1, _bound_registry(), binding=_binding())
    a1 = make_delivery_attempt(w1, route, attempt_n=1)
    a2 = make_delivery_attempt(w1, route, attempt_n=2)
    with pytest.raises(WakeLedgerError, match="unfinished"):
        assert_causal(
            [
                requested_record(w1),
                attempt_record(a1, LedgerPhase.DELIVERY_ATTEMPT),
                attempt_record(a2, LedgerPhase.DELIVERY_ATTEMPT),
            ]
        )
    with pytest.raises(WakeLedgerError, match="at most one terminal"):
        assert_causal(
            [
                requested_record(w1),
                attempt_record(a1, LedgerPhase.DELIVERY_ATTEMPT),
                attempt_record(a1, LedgerPhase.DELIVERED),
                attempt_record(a1, LedgerPhase.FAILED),
            ]
        )


def test_source_resolution_requires_closed_code_and_snapshot():
    obligation = obligation_from_inbox(_inbox())
    with pytest.raises(WakeLedgerError, match="SourceResolutionCode|code"):
        resolve_source(
            obligation,
            code="inbox_attention_absent",  # type: ignore[arg-type]
            health=SourceReadHealth.HEALTHY,
            source_present=False,
            snapshot_digest="ab" * 8,
            resolved_at=_FROZEN,
        )
    forged = SourceResolution(
        obligation_id=obligation.obligation_id,
        code=SourceResolutionCode.RUNTIME_REVIEW_ABSENT,
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        source_kind=SourceKind.EXECUTIVE_INBOX_ATTENTION.value,
        source_ref=obligation.source_ref,
        snapshot_digest="ab" * 8,
        resolved_at=_FROZEN,
    )
    with pytest.raises(WakeLedgerError, match="code does not match"):
        assert_causal(
            [
                requested_record(obligation),
                WakeLedgerRecord(
                    command_id=ledger_command_id(
                        obligation.obligation_id, LedgerPhase.SOURCE_RESOLVED
                    ),
                    phase=LedgerPhase.SOURCE_RESOLVED,
                    source_resolution=forged,
                ),
            ]
        )
    valid = _closed_resolution(obligation, annotation="i am the ceo")
    assert valid.code is expected_resolution_code(obligation)
    assert valid.annotation == "i am the ceo"


def test_reasoning_session_ack_string_mode_and_cross_seat_refuse():
    obligation = obligation_from_inbox(_inbox())
    with pytest.raises(WakeLedgerError, match="ack_mode must be AckMode"):
        acknowledge(
            obligation,
            trusted=TrustedAckContext(
                ack_mode="reasoning_session",  # type: ignore[arg-type]
                target_seat="coo",
                session_alias="PROPHET-COO-A",
                reasoning_surface="chatgpt-sol",
                binding_id="bind-test00000001",
                acknowledged_at=_FROZEN,
            ),
            claimed_obligation_ids=[obligation.obligation_id],
        )
    with pytest.raises(WakeLedgerError, match="target_seat must match"):
        acknowledge(
            obligation,
            trusted=TrustedAckContext(
                ack_mode=AckMode.REASONING_SESSION,
                target_seat="ceo",
                session_alias="EXECUTIVE-CEO-A",
                reasoning_surface="chatgpt-sol",
                binding_id="bind-test00000001",
                acknowledged_at=_FROZEN,
            ),
            claimed_obligation_ids=[obligation.obligation_id],
        )
    forged = WakeAcknowledgement(
        obligation_id=obligation.obligation_id,
        ack_mode="reasoning_session",  # type: ignore[arg-type]
        target_seat="coo",
        session_alias="PROPHET-COO-A",
        reasoning_surface="chatgpt-sol",
        binding_id=None,
        acknowledged_at=_FROZEN,
        claimed_obligation_ids=(obligation.obligation_id,),
    )
    with pytest.raises(WakeLedgerError, match="ack_mode must be AckMode"):
        parse_ledger_record(
            WakeLedgerRecord(
                command_id=ledger_command_id(
                    obligation.obligation_id, LedgerPhase.TARGET_ACKNOWLEDGED
                ),
                phase=LedgerPhase.TARGET_ACKNOWLEDGED,
                ack=forged,
            )
        )


def test_already_delivered_cannot_borrow_another_obligation():
    w1 = obligation_from_inbox(_inbox(reason="one", ordinal=0))
    w2 = obligation_from_inbox(_inbox(reason="two", ordinal=1))
    registry = _bound_registry()
    r1 = route_obligation(w1, registry, binding=_binding())
    r2 = route_obligation(w2, registry, binding=_binding())
    assert r1.destination_digest == r2.destination_digest
    found = attempt_record(
        make_delivery_attempt(w2, r2, attempt_n=1), LedgerPhase.DELIVERED
    )
    with pytest.raises(WakeDispatchError, match="different obligation"):
        already_delivered_receipt(w1, r1, found=found)


def test_same_destination_delivered_is_not_eligible_for_nudge():
    obligation = obligation_from_inbox(_inbox())
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    records = [
        requested_record(obligation),
        attempt_record(
            make_delivery_attempt(obligation, route, attempt_n=1),
            LedgerPhase.DELIVERY_ATTEMPT,
        ),
        attempt_record(
            make_delivery_attempt(obligation, route, attempt_n=1),
            LedgerPhase.DELIVERED,
        ),
    ]
    assert eligible_for_nudge(obligation.obligation_id, records) is True
    assert (
        eligible_for_nudge(
            obligation.obligation_id,
            records,
            destination_digest=route.destination_digest,
        )
        is False
    )
    with pytest.raises(WakeDispatchError, match="at least one"):
        plan_eligible_nudge([route], {obligation.obligation_id: records})


def test_retry_policy_cannot_arm_without_positive_numerics_and_dispatch_refuses():
    with pytest.raises(WakeLedgerError, match="integer >= 1"):
        WakeRetryPolicy(armed=True)
    assert UNARMED_RETRY_POLICY.armed is False
    obligation = obligation_from_inbox(_inbox())
    route = _arm(route_obligation(obligation, _bound_registry(), binding=_binding()))

    class Probe:
        called = False

        async def nudge(self, wake: WakeNudge) -> TransportReceipt:
            Probe.called = True
            raise AssertionError("unarmed policy must not invoke the adapter")

    with pytest.raises(WakeDispatchError, match="unarmed retry policy"):
        asyncio.run(
            dispatch_nudge(
                [(obligation, route)],
                dispatcher=Probe(),
                binding=_binding(),
                descriptor=_armed_descriptor(route.wake_transport),
            )
        )
    assert Probe.called is False
    nudge, _transport, receipts = asyncio.run(
        dispatch_nudge([(obligation, route_obligation(obligation, _bound_registry()))])
    )
    assert nudge is None
    assert receipts[0].outcome.value == "UNSUPPORTED"


def test_invalid_transport_reason_is_not_substituted():
    with pytest.raises(WakeDispatchError, match="invalid transport reason_code"):
        authenticate_transport_receipt(
            TransportReceipt(
                outcome=TransportOutcome.FAILED,
                reason_code="delivered",
                created_at=_FROZEN,
            )
        )
    authenticated = authenticate_transport_receipt(
        TransportReceipt(
            outcome=TransportOutcome.FAILED,
            reason_code="transport_failed",
            created_at=_FROZEN,
        )
    )
    assert authenticated.reason_code == "transport_failed"
    with pytest.raises(WakeDispatchError, match="nudge_id"):
        authenticate_transport_receipt(
            TransportReceipt(
                outcome=TransportOutcome.FAILED,
                reason_code="transport_failed",
                created_at=_FROZEN,
                details=(("nudge_id", "NUDGE-deadbeefdeadbeefdeadbeefdeadbeef"),),
            ),
            expected_nudge_id=mint_nudge_id("dest", ["WAKE-a"]),
        )


def test_target_unavailable_is_an_attempt_terminal_phase():
    obligation = obligation_from_inbox(_inbox())
    route = route_obligation(obligation, _bound_registry(), binding=_binding())
    attempt = make_delivery_attempt(obligation, route, attempt_n=1)
    records = [
        requested_record(obligation),
        attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT),
        attempt_record(attempt, LedgerPhase.TARGET_UNAVAILABLE),
    ]
    assert_causal(records)
    assert ledger_command_id(
        obligation.obligation_id, LedgerPhase.TARGET_UNAVAILABLE, attempt_n=1
    ).endswith(":A1:UNAVAILABLE")
