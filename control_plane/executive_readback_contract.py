"""Single producer/reader contract for LOST reasons and UTC Runtime dates.

Runtime owns timestamps using its injectable authoritative store clock. Formatting
MUST NOT compare that clock with the host wall clock; that would reject valid
simulated clocks and externally authorized long leases. The untrusted Web read
boundary applies one common 24-hour *future event observation* tolerance; lease
expiration deadlines are future-by-design and are checked for UTC shape only.
Existing historical LOST reasons remain valid without a fixed reason allowlist.
"""
from datetime import datetime, timedelta, timezone

MAX_LOST_REASON_LENGTH = 1024
MAX_FUTURE_CLOCK_SKEW = timedelta(days=1)


def valid_lost_reason(value: object) -> bool:
    return (type(value) is str and 0 < len(value) <= MAX_LOST_REASON_LENGTH
            and value == value.strip()
            and all(char.isprintable() for char in value))


def format_runtime_utc_timestamp(timestamp_ms: int | None) -> str:
    """Trusted producer serializer; accepts the Runtime's injected store clock."""
    if timestamp_ms is None:
        return ""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def valid_runtime_instant(
    value: object, *, now: datetime | None = None, deadline: bool = False
) -> bool:
    """Validate a UTC event-time observation or a future-by-design deadline.

    Reader-only wall-clock skew is not a constraint on producer store clocks.
    """
    if type(value) is not str:
        return False
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except (TypeError, ValueError, OverflowError):
        return False
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return False
    if deadline:
        return True
    observed = now if now is not None else datetime.now(timezone.utc)
    return parsed <= observed + MAX_FUTURE_CLOCK_SKEW
