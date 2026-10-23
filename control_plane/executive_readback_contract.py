"""Shared LOST-reason and UTC Runtime timestamp validators.

Runtime formats timestamps from its injectable authoritative store clock
without comparing them to the producer host wall clock. The untrusted Web
reader separately compares observed Runtime event timestamps to its own UTC
wall clock, allowing at most 24 hours of future event skew. A producer with a
far-future injected clock may therefore serialize a legitimate test timestamp
that the reader intentionally rejects at its independent trust boundary.

A lease expiration is a future-by-design deadline, so the reader checks its
UTC shape without applying event-time skew. Envelope, inbox and Fabric
generated_at fields retain their separate shape-only validation; they do not
establish freshness or replay authority. Historical bounded verified-process-
absence LOST reasons have no closed reason allowlist; expiry/fence LOST
envelopes still require their exact pre-existing reason values.
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
    """Validate a UTC event observation or future-by-design deadline.

    The Web reader's independent clock bound applies to event observations,
    not to producer serialization or lawful future lease deadlines.
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
