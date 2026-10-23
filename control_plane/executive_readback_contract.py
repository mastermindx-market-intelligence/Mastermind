"""Shared Runtime/Web readback bounds, preserving historical LOST reasons.

No allowlist of human recovery reasons: old persisted records must remain readable.
The future allowance covers legitimate cross-host clock drift and short leases.
"""
from datetime import datetime, timedelta, timezone

MAX_LOST_REASON_LENGTH = 1024
MAX_FUTURE_CLOCK_SKEW = timedelta(days=1)


def valid_lost_reason(value: object) -> bool:
    return (type(value) is str and 0 < len(value) <= MAX_LOST_REASON_LENGTH
            and value == value.strip()
            and all(char.isprintable() for char in value))


def valid_runtime_instant(value: str, *, now: datetime | None = None) -> bool:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return False
    observed = now if now is not None else datetime.now(timezone.utc)
    return parsed <= observed + MAX_FUTURE_CLOCK_SKEW
