"""Pure point measurement of existing Wake owner observations.

Recorded append intervals are conditional samples, not model reasoning time,
queue service guarantees, parent acceptance, or a seven-day installed campaign.
No clock read, persistence, transport, admission or lifecycle mutation occurs.
The input bound limits this composition, not upstream snapshot acquisition.
"""
from __future__ import annotations

import math
from datetime import datetime

from control_plane.wake_events import ISO_UTC_RE, WAKE_ID_RE
from control_plane.wake_ledger import (
    AckMode, LedgerPhase, SourceReadHealth, WakeLedgerError, assert_causal,
    identity_payload, wake_record_from_event,
)
from control_plane.wake_reconcile import WakeLedgerSnapshot, WakeSourceSnapshot

SCHEMA = "mastermind.capacity_campaign_observation.v1"
MAX_INPUT_EVENTS = 10_000
_METRICS = (
    "request_to_first_delivery_ms", "matched_delivery_to_reasoning_ack_ms",
    "request_to_ack_ms", "request_to_source_resolution_ms",
)
_UNAVAILABLE = (
    "model_reasoning_duration_ms", "desktop_occupancy_ms", "job_queue_delay_ms",
    "actual_cash_usd_per_accepted_outcome", "accepted_outcomes_per_avoidable_intervention",
    "original_parent_disposition_consumption", "seven_day_installed_coverage",
)


def _stamp(value: str) -> datetime:
    if not isinstance(value, str) or ISO_UTC_RE.fullmatch(value) is None:
        raise ValueError("APPEND_TIMESTAMP_UNAVAILABLE")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _interval(start, end, *, reason=None):
    if reason:
        return {"state": "UNAVAILABLE", "value": None, "reason": reason}
    if start is None:
        return {"state": "UNAVAILABLE", "value": None, "reason": "START_NOT_RECORDED"}
    if end is None:
        return {"state": "UNFINISHED", "value": None, "reason": "END_NOT_RECORDED"}
    elapsed = end - start
    milliseconds = elapsed.days * 86_400_000 + elapsed.seconds * 1000 + elapsed.microseconds // 1000
    return {"state": "COMPLETED", "value": milliseconds, "reason": None}


def observe_capacity_campaign(
    source: WakeSourceSnapshot, ledger: WakeLedgerSnapshot, *, max_events: int = MAX_INPUT_EVENTS,
) -> dict[str, object]:
    """Compose owner-produced snapshots without promoting observation to acceptance.

    Every stream is revalidated through the existing Wake causal/wire owners.
    Missing or malformed append clocks never become zero-duration observations.
    Human ACK is reported separately and has no matched reasoning-delivery sample.
    """
    if type(max_events) is not int or not 1 <= max_events <= MAX_INPUT_EVENTS:
        raise ValueError("invalid observation input bound")
    contradictions = (["SOURCE_SNAPSHOT_CONTRADICTION"] if source.contradictions else []) + (
        ["LEDGER_SNAPSHOT_CONTRADICTION"] if ledger.contradictions else [])
    reasons = ["SOURCE_SNAPSHOT_DEGRADED"] if source.degraded else []
    health = {
        "runtime": source.runtime_health.value, "inbox_runtime": source.inbox_runtime_health.value,
        "agentos": source.agentos_health.value,
    }
    if any(value != SourceReadHealth.HEALTHY.value for value in health.values()):
        reasons.append("SOURCE_COVERAGE_DEGRADED")
    if source.unsupported_attention:
        reasons.append("UNSUPPORTED_ATTENTION")
    report = {
        "schema": SCHEMA, "mode": "point_observation", "writes_applied": False,
        "campaign_qualified": False, "source_digest": source.digest,
        "clock_basis": "RECORDED_RUNTIME_EVENT_APPEND", "physical_elapsed_accuracy": "NOT_ESTABLISHED",
        "snapshot_consistency": "INDEPENDENT_OWNER_READS_NOT_ATOMIC",
        "acknowledgement_scope": "TARGET_ACK_NOT_ORIGINAL_PARENT_DISPOSITION_ACCEPTANCE",
        "request_to_ack_scope": "INCLUDES_HUMAN_OPERATOR_ACK_SEPARATE_MODE_COUNTS",
        "population_scope": "IDENTIFIED_SNAPSHOT_UNION_NOT_COMPLETE_DEMAND",
        "interpretation": "CONDITIONAL_ON_RECORDED_COMPLETED_INTERVALS_NOT_AN_SLO",
        "source_coverage": {"health": health, "scope": "EXISTING_SNAPSHOTS_ONLY",
                            "unsupported_attention_count": len(source.unsupported_attention),
                            "degraded_entry_count": len(source.degraded),
                            "contradiction_count": len(source.contradictions)},
        "input_coverage": {"events_received": len(ledger.events), "max_events": max_events,
                           "source_obligations_received": len(source.observed),
                           "ledger_contradiction_count": len(ledger.contradictions),
                           "acquisition_bounded_by_this_consumer": False},
        "unavailable_metrics": {name: {"state": "UNAVAILABLE", "value": None,
                                      "reason": "NO_QUALIFIED_PRODUCER_JOIN_IN_THIS_OBSERVATION"}
                                for name in _UNAVAILABLE},
    }
    rows = []
    ack_counts = {"reasoning_session": 0, "human_operator": 0, "not_recorded": 0, "unavailable": 0}
    bounded = len(ledger.events) <= max_events and len(source.observed) <= max_events
    if not bounded:
        reasons.append("OBSERVATION_INPUT_BOUND_EXCEEDED")
    else:
        observed = {}
        for obligation in source.observed:
            if not isinstance(obligation.obligation_id, str) or WAKE_ID_RE.fullmatch(obligation.obligation_id) is None:
                contradictions.append("SOURCE_OBLIGATION_ID_INVALID")
                continue
            if obligation.obligation_id in observed:
                contradictions.append("DUPLICATE_SOURCE_OBLIGATION")
            observed[obligation.obligation_id] = obligation
        groups = {}
        previous_id = 0
        invalid_ids = set()
        for index, item in enumerate(ledger.events):
            oid = item.event.aggregate_id
            if not isinstance(oid, str) or WAKE_ID_RE.fullmatch(oid) is None:
                oid = "UNIDENTIFIED_RECORD_" + str(index)
                contradictions.append("LEDGER_OBLIGATION_ID_INVALID")
                invalid_ids.add(oid)
            groups.setdefault(oid, []).append(item)
            if type(item.event.event_id) is not int or item.event.event_id <= previous_id:
                contradictions.append("EVENT_APPEND_ORDER_INVALID")
                invalid_ids.add(oid)
            if type(item.event.event_id) is int:
                previous_id = item.event.event_id
        backlog = {}
        for obligation in observed.values():
            backlog[obligation.wake_kind.value] = backlog.get(obligation.wake_kind.value, 0) + 1
        report["current_attention_by_kind"] = dict(sorted(backlog.items()))
        for oid in sorted(set(observed) | set(groups)):
            items = groups.get(oid, [])
            obligation = observed.get(oid)
            record_error = "EVENT_APPEND_ORDER_INVALID" if oid in invalid_ids else None
            try:
                for item in items:
                    if wake_record_from_event(item.event) != item.record:
                        raise WakeLedgerError("record differs from persisted wire")
                assert_causal(tuple(item.record for item in items))
                if items:
                    persisted_obligation = items[0].record.obligation
                    if (obligation is not None and persisted_obligation is not None
                            and identity_payload(obligation) != identity_payload(persisted_obligation)):
                        raise WakeLedgerError("source and persisted identity disagree")
                    obligation = persisted_obligation
                    if obligation is None or obligation.obligation_id != oid:
                        raise WakeLedgerError("stream identity disagrees")
            except (WakeLedgerError, ValueError, TypeError, AttributeError):
                record_error = "CAUSAL_STREAM_INVALID"
                contradictions.append(record_error)
            phases = {}
            stamps = {}
            if not record_error:
                try:
                    previous_stamp = None
                    previous_sequence = 0
                    for item in items:
                        stamp = _stamp(item.event.created_at)
                        if (previous_stamp is not None and stamp < previous_stamp
                                or type(item.event.sequence) is not int
                                or item.event.sequence != previous_sequence + 1):
                            raise ValueError("APPEND_CLOCK_OR_SEQUENCE_ORDER_INVALID")
                        previous_stamp, previous_sequence = stamp, item.event.sequence
                        phases.setdefault(item.record.phase, item)
                        stamps[item.record.command_id] = stamp
                except (ValueError, TypeError):
                    record_error = "APPEND_CLOCK_OR_SEQUENCE_UNAVAILABLE"
                    reasons.append(record_error)
            ack_item = phases.get(LedgerPhase.TARGET_ACKNOWLEDGED)
            ack = ack_item.record.ack if ack_item else None
            ack_mode = ack.ack_mode.value if ack and not record_error else None
            ack_counts[ack_mode if ack_mode else "unavailable" if record_error else "not_recorded"] += 1
            def phase_stamp(phase):
                item = phases.get(phase)
                return stamps.get(item.record.command_id) if item else None
            requested = phase_stamp(LedgerPhase.WAKE_REQUESTED)
            acknowledged = phase_stamp(LedgerPhase.TARGET_ACKNOWLEDGED)
            first_delivery = phase_stamp(LedgerPhase.DELIVERED)
            delivery_error = record_error or (
                "ACK_CLOSED_WITHOUT_RECORDED_DELIVERY" if ack and first_delivery is None else None)
            matching = (stamps.get(ack.delivered_command_id) if ack and ack.ack_mode is AckMode.REASONING_SESSION
                        else phase_stamp(LedgerPhase.DELIVERED) if ack is None else None)
            metrics = {
                "request_to_first_delivery_ms": _interval(requested, first_delivery, reason=delivery_error),
                "matched_delivery_to_reasoning_ack_ms": _interval(matching, acknowledged, reason=record_error or (
                    "HUMAN_ACK_IS_NOT_REASONING_CONSUMPTION" if ack and ack.ack_mode is AckMode.HUMAN_OPERATOR else None)),
                "request_to_ack_ms": _interval(requested, acknowledged, reason=record_error),
                "request_to_source_resolution_ms": _interval(requested, phase_stamp(LedgerPhase.SOURCE_RESOLVED), reason=record_error),
            }
            rows.append({"obligation_id": oid if WAKE_ID_RE.fullmatch(oid) else None,
                         "wake_kind": obligation.wake_kind.value if obligation else None,
                         "source_kind": obligation.source_kind.value if obligation else None,
                         "acknowledgement_mode": ack_mode, "metrics": metrics})
    summaries = {}
    for name in _METRICS:
        samples = sorted(row["metrics"][name]["value"] for row in rows
                         if row["metrics"][name]["state"] == "COMPLETED")
        summaries[name] = {
            "population": len(rows) if bounded else None, "completed": len(samples) if bounded else None,
            "unfinished": sum(row["metrics"][name]["state"] == "UNFINISHED" for row in rows) if bounded else None,
            "unavailable": sum(row["metrics"][name]["state"] == "UNAVAILABLE" for row in rows) if bounded else None,
            "p50": samples[math.ceil(len(samples) * .5) - 1] if samples else None,
            "p95": samples[math.ceil(len(samples) * .95) - 1] if samples else None,
            "max": samples[-1] if samples else None, "quantile_method": "NEAREST_RANK",
        }
    report.update(obligations=rows, interval_summaries=summaries,
                  acknowledgement_counts=ack_counts if bounded else None,
                  contradictions=sorted(set(contradictions)), degraded=sorted(set(reasons)),
                  point_status="CONTRADICTORY" if contradictions else "PARTIAL" if reasons else "OBSERVED")
    return report
