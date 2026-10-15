"""Actual Wake producers in isolated Runtime fixtures; no installed campaign."""
from dataclasses import replace

import pytest

from control_plane.capacity_campaign_observation import observe_capacity_campaign
from control_plane.executive_runtime import Runtime
from control_plane.wake_ledger import (
    AckMode, LedgerPhase, SourceReadHealth, TrustedAckContext, ack_record,
    acknowledge, attempt_record, expected_resolution_code, make_delivery_attempt,
    requested_record, resolve_source, resolved_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_reconcile import WakeLedgerSnapshot, WakeSourceSnapshot, collect_ledger_snapshot
from tests.test_executive_wake_fabric import (
    _ack_row, _binding, _obligation_from_inbox, _route_for,
)


def snapshot(obligations=(), *, degraded=False, unsupported=()):
    health = SourceReadHealth.DEGRADED if degraded else SourceReadHealth.HEALTHY
    return WakeSourceSnapshot(tuple(obligations), health, health, health, (), {}, "a" * 64,
                              unsupported_attention=unsupported)


def owner_stream(root, *, human=False, human_delivery=False, finish=True, retry=False, pending=False):
    tick = [1_780_000_000_000]
    runtime = Runtime.at(root, clock=lambda: tick[0])
    runtime.jobs.create_job("Isolated observation fixture")
    obligation = _obligation_from_inbox()
    repo = WakeLedgerRepository(runtime)
    def append(record, offset):
        tick[0] = 1_780_000_000_000 + offset
        return repo.append_record(record, obligation=obligation)
    append(requested_record(obligation), 0)
    if not human or human_delivery:
        route = _route_for(obligation, binding=_binding())
        attempt = make_delivery_attempt(obligation, route, attempt_n=1)
        append(attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), 1000)
        if retry:
            append(attempt_record(attempt, LedgerPhase.FAILED), 1500)
            attempt = make_delivery_attempt(obligation, route, attempt_n=2)
            append(attempt_record(attempt, LedgerPhase.DELIVERY_ATTEMPT), 1800)
        delivered = append(attempt_record(attempt, LedgerPhase.DELIVERED), 2000)
        # Replaying the owner's same command does not append a second delivery.
        assert append(attempt_record(attempt, LedgerPhase.DELIVERED), 3000).event.event_id == delivered.event.event_id
        ack = _ack_row(obligation, route=route, attempt_n=attempt.attempt_n)
    if human:
        ack = ack_record(obligation, acknowledge(obligation,
            trusted=TrustedAckContext(ack_mode=AckMode.HUMAN_OPERATOR,
                target_seat=obligation.declared_target_seat, session_alias="EXECUTIVE-HUMAN-OPERATOR",
                reasoning_surface="human", acknowledged_at="2026-08-16T16:00:00Z",
                operator_authority_receipt="OP-OBSERVATION-TEST"),
            claimed_obligation_ids=(obligation.obligation_id,)))
    if not pending:
        append(ack, 5000)
        if finish:
            resolution = resolve_source(obligation, code=expected_resolution_code(obligation),
                health=SourceReadHealth.HEALTHY, source_present=False, snapshot_digest="a" * 64,
                resolved_at="2026-08-16T16:00:00Z")
            append(resolved_record(obligation, resolution), 8000)
    return runtime, obligation, collect_ledger_snapshot(runtime)


def test_owner_causal_intervals_and_replayed_delivery(tmp_path):
    runtime, obligation, ledger = owner_stream(tmp_path, retry=True)
    before = runtime.events.list_events()
    report = observe_capacity_campaign(snapshot(), ledger)
    row = report["obligations"][0]
    assert row["obligation_id"] == obligation.obligation_id
    assert report["point_status"] == "OBSERVED"
    assert row["acknowledgement_mode"] == "reasoning_session"
    assert {key: value["value"] for key, value in row["metrics"].items()} == {
        "request_to_first_delivery_ms": 2000, "matched_delivery_to_reasoning_ack_ms": 3000,
        "request_to_ack_ms": 5000, "request_to_source_resolution_ms": 8000}
    assert report["interval_summaries"]["request_to_ack_ms"]["completed"] == 1
    assert report["campaign_qualified"] is False
    assert "NOT_ORIGINAL_PARENT" in report["acknowledgement_scope"]
    assert report["unavailable_metrics"]["actual_cash_usd_per_accepted_outcome"]["value"] is None
    assert runtime.events.list_events() == before


def test_unfinished_and_unrecorded_obligations_keep_denominators(tmp_path):
    _, obligation, ledger = owner_stream(tmp_path, pending=True)
    other = replace(obligation, source_ref="eia-abcdef123456")
    # Mint identity through its owner rather than changing a frozen identifier.
    from control_plane.wake_events import mint_obligation
    other = mint_obligation(wake_kind=other.wake_kind, source_kind=other.source_kind,
        source_ref=other.source_ref, declared_target_seat=other.declared_target_seat)
    report = observe_capacity_campaign(snapshot((obligation, other)), ledger)
    summary = report["interval_summaries"]["request_to_ack_ms"]
    assert (summary["population"], summary["completed"], summary["unfinished"], summary["unavailable"]) == (2, 0, 1, 1)
    assert summary["p95"] is None
    assert report["interval_summaries"]["matched_delivery_to_reasoning_ack_ms"]["unfinished"] == 1


@pytest.mark.parametrize("finish", [False, True])
def test_human_ack_never_becomes_reasoning_consumption_or_unfinished_delivery(tmp_path, finish):
    _, _, ledger = owner_stream(tmp_path, human=True, finish=finish)
    report = observe_capacity_campaign(snapshot(), ledger)
    assert report["acknowledgement_counts"]["human_operator"] == 1
    metrics = report["obligations"][0]["metrics"]
    assert metrics["request_to_ack_ms"]["value"] == 5000
    assert metrics["matched_delivery_to_reasoning_ack_ms"] == {
        "state": "UNAVAILABLE", "value": None, "reason": "HUMAN_ACK_IS_NOT_REASONING_CONSUMPTION"}
    assert metrics["request_to_first_delivery_ms"] == {
        "state": "UNAVAILABLE", "value": None, "reason": "ACK_CLOSED_WITHOUT_RECORDED_DELIVERY"}
    summary = report["interval_summaries"]["request_to_first_delivery_ms"]
    assert summary["unfinished"] == 0 and summary["unavailable"] == 1
    assert summary["completed"] == 0 and summary["p95"] is None


def test_human_ack_preserves_a_previously_recorded_delivery_sample(tmp_path):
    _, _, ledger = owner_stream(tmp_path, human=True, human_delivery=True)
    report = observe_capacity_campaign(snapshot(), ledger)
    metric = report["obligations"][0]["metrics"]["request_to_first_delivery_ms"]
    assert metric == {"state": "COMPLETED", "value": 2000, "reason": None}
    summary = report["interval_summaries"]["request_to_first_delivery_ms"]
    assert summary["completed"] == 1 and summary["unfinished"] == summary["unavailable"] == 0


@pytest.mark.parametrize("change", ["clock_missing", "clock_backwards", "sequence_gap", "binding", "order", "wire"])
def test_invalid_owner_observation_cannot_yield_healthy_timing(tmp_path, change):
    _, _, ledger = owner_stream(tmp_path)
    items = list(ledger.events)
    item = items[2]
    if change == "clock_missing":
        items[2] = replace(item, event=replace(item.event, created_at=None))
    elif change == "clock_backwards":
        items[2] = replace(item, event=replace(item.event, created_at="2000-01-01T00:00:00Z"))
    elif change == "sequence_gap":
        items[2] = replace(item, event=replace(item.event, sequence=20))
    elif change == "binding":
        items[2] = replace(item, record=replace(item.record, binding_generation=2))
    elif change == "order":
        items[1], items[2] = items[2], items[1]
    else:
        items[2] = replace(item, event=replace(item.event, aggregate_id="WAKE-" + "f" * 32))
    report = observe_capacity_campaign(snapshot(), replace(ledger, events=tuple(items)))
    assert report["point_status"] in ("PARTIAL", "CONTRADICTORY")
    assert report["interval_summaries"]["request_to_ack_ms"]["completed"] == 0
    assert report["interval_summaries"]["request_to_ack_ms"]["p50"] is None


def test_partial_source_coverage_does_not_erase_conditional_samples(tmp_path):
    _, obligation, ledger = owner_stream(tmp_path)
    report = observe_capacity_campaign(snapshot((obligation,), degraded=True, unsupported=("unsupported",)), ledger)
    assert report["point_status"] == "PARTIAL"
    assert report["current_attention_by_kind"] == {"job_failed": 1}
    assert report["interval_summaries"]["request_to_ack_ms"]["completed"] == 1
    assert report["source_coverage"]["health"]["agentos"] == "degraded"


def test_input_bound_refuses_instead_of_silently_truncating(tmp_path):
    _, _, ledger = owner_stream(tmp_path)
    report = observe_capacity_campaign(snapshot(), ledger, max_events=1)
    assert report["point_status"] == "PARTIAL" and report["obligations"] == []
    assert report["interval_summaries"]["request_to_ack_ms"]["population"] is None
    assert report["acknowledgement_counts"] is None
    assert report["input_coverage"]["acquisition_bounded_by_this_consumer"] is False


def test_empty_observation_has_no_fabricated_zero_latency_or_campaign():
    report = observe_capacity_campaign(snapshot(), WakeLedgerSnapshot((), {}))
    assert report["interval_summaries"]["request_to_ack_ms"]["population"] == 0
    assert report["interval_summaries"]["request_to_ack_ms"]["p95"] is None
    assert report["campaign_qualified"] is False
    assert all(row["state"] == "UNAVAILABLE" for row in report["unavailable_metrics"].values())


def test_source_identity_disagreement_and_private_diagnostics_are_not_copied(tmp_path):
    import json
    _, obligation, ledger = owner_stream(tmp_path)
    source = replace(snapshot((replace(obligation, root_job_id="JOB-999"),)),
                     degraded=("private body marker",), contradictions=("private source marker",),
                     unsupported_attention=("private account marker",))
    report = observe_capacity_campaign(source, ledger)
    assert report["point_status"] == "CONTRADICTORY"
    assert report["interval_summaries"]["request_to_ack_ms"]["completed"] == 0
    assert "private" not in json.dumps(report)
    assert report["source_coverage"]["unsupported_attention_count"] == 1


def test_invalid_event_identifier_does_not_echo_payload_or_count_a_valid_sample(tmp_path):
    import json
    _, _, ledger = owner_stream(tmp_path)
    item = ledger.events[0]
    items = (replace(item, event=replace(item.event, aggregate_id="private prompt marker")),) + ledger.events[1:]
    report = observe_capacity_campaign(snapshot(), replace(ledger, events=items))
    assert report["point_status"] == "CONTRADICTORY"
    assert "private prompt" not in json.dumps(report)
    assert report["interval_summaries"]["request_to_ack_ms"]["completed"] == 0
