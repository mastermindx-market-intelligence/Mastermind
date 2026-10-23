"""Shared, backward-compatible Runtime / Executive Job readback contracts.

Only the Runtime may originate a verified process-absence transition. Legacy
persisted envelopes lacked a reason_code and remain readable; new envelopes
carry an explicit semantic code so a diagnostic sentence cannot impersonate a
known reconciliation cause.

Event timestamps represent observed events, not future lease deadlines. The
same skew policy is available to the runtime clock owner and the read gateway.
"""
from __future__ import annotations

from datetime import datetime, timezone

LOST_REASON_MAX_CHARS = 1024
PROCESS_ABSENCE_REASONS = {
    "process identity absent during supervisor restart": "supervisor_restart_absence",
    "provider session disappeared": "provider_session_absence",
    "provider confirmed session missing": "provider_session_absence",
}
OTHER_VERIFIED_ABSENCE = "other_verified_absence"
EXPIRED_REASONS = frozenset({"lease_expired", "ohf_lease_expired_fenced"})

# Producer/reader envelope skew: a future *event* exceeding 5 minutes has no
# trustworthy source-observation provenance. Leases are schedules, not events.
MAX_EVENT_CLOCK_SKEW_MS = 5 * 60 * 1000
MAX_LEASE_LOOKAHEAD_MS = 30 * 24 * 60 * 60 * 1000


def bounded_lost_reason(reason: object) -> bool:
    return (
        type(reason) is str
        and 0 < len(reason) <= LOST_REASON_MAX_CHARS
        and reason == reason.strip()
        and all(char.isprintable() for char in reason)
    )


def process_absence_error(reason: str) -> dict[str, object]:
    """New producer envelope: known semantic cause or typed diagnostic OTHER."""
    if not bounded_lost_reason(reason):
        raise ValueError("unbounded or malformed verified-absence reason")
    return {
        "reason": reason,
        "verified_process_absent": True,
        "reason_code": PROCESS_ABSENCE_REASONS.get(reason, OTHER_VERIFIED_ABSENCE),
    }


def valid_requeued_lost_error(value: object) -> bool:
    """Accept both newly typed and historically persisted exact envelopes."""
    if type(value) is not dict or not bounded_lost_reason(value.get("reason")):
        return False
    reason = value["reason"]
    if set(value) == {"reason", "expired_at_ms"}:
        return (
            reason in EXPIRED_REASONS
            and type(value["expired_at_ms"]) is int
            and 0 <= value["expired_at_ms"] < 2**63
        )
    if set(value) == {"reason", "verified_process_absent"}:
        # Historical Runtime persisted no machine reason code. Preserve exactly
        # this bounded legacy shape; never reinterpret it as a new v2 receipt.
        return value["verified_process_absent"] is True
    if set(value) == {"reason", "verified_process_absent", "reason_code"}:
        return (
            value["verified_process_absent"] is True
            and type(value["reason_code"]) is str
            and value["reason_code"]
            == PROCESS_ABSENCE_REASONS.get(reason, OTHER_VERIFIED_ABSENCE)
        )
    return False


def event_timestamp_within_skew(
    timestamp_ms: object, *, now_ms: int, lease_schedule: bool = False,
) -> bool:
    """Common producer/reader future bound; never compare a lease to event skew."""
    limit = MAX_LEASE_LOOKAHEAD_MS if lease_schedule else MAX_EVENT_CLOCK_SKEW_MS
    return (
        type(timestamp_ms) is int and timestamp_ms >= 0
        and type(now_ms) is int and now_ms >= 0
        and timestamp_ms <= now_ms + limit
    )


def parsed_utc_timestamp_ms(value: object) -> int | None:
    if type(value) is not str or not value or len(value) > 64:
        return None
    try:
        date = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
        if date.tzinfo is None or date.utcoffset() != timezone.utc.utcoffset(date):
            return None
        return int(date.timestamp() * 1000)
    except (OverflowError, ValueError, OSError):
        return None
