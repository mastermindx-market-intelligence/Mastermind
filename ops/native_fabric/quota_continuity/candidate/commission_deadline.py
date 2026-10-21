"""The original commission's deadline in its controller's monotonic domain.

This is a duration/validation helper, not an execution or settlement owner.
Never send DEADLINE_ENV to another host: only a freshly narrowed duration may
cross the existing transport, where a separate local clock must be anchored.
"""
from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Mapping


DEADLINE_ENV = "POOL_COMMISSION_DEADLINE_NS"
NANOSECONDS = 1_000_000_000
MAX_DEADLINE_NS = 2**63 - 1


class CommissionDeadlineInvalid(ValueError):
    pass


class CommissionDeadlineExpired(TimeoutError):
    pass


def validate_deadline_ns(value: object) -> int:
    if type(value) is str:
        if not re.fullmatch(r"[1-9][0-9]{0,18}", value):
            raise CommissionDeadlineInvalid("commission_deadline_invalid")
        value = int(value)
    if type(value) is not int or not 0 < value <= MAX_DEADLINE_NS:
        raise CommissionDeadlineInvalid("commission_deadline_invalid")
    return value


def read_deadline_ns(env: Mapping[str, str] | None = None) -> int | None:
    values = os.environ if env is None else env
    if DEADLINE_ENV not in values:
        return None
    return validate_deadline_ns(values[DEADLINE_ENV])


def _seconds(value: object) -> float:
    if type(value) not in (int, float):
        raise CommissionDeadlineInvalid("commission_duration_invalid")
    try:
        result = float(value)
    except OverflowError as exc:
        raise CommissionDeadlineInvalid("commission_duration_invalid") from exc
    if not math.isfinite(result) or not 0 <= result <= 7200:
        raise CommissionDeadlineInvalid("commission_duration_invalid")
    return result


def _now(now_ns: int | None) -> int:
    value = time.monotonic_ns() if now_ns is None else now_ns
    if type(value) is not int or not 0 <= value <= MAX_DEADLINE_NS:
        raise CommissionDeadlineInvalid("commission_clock_invalid")
    return value


def remaining_seconds(deadline_ns: int, *, now_ns: int | None = None) -> float:
    remaining = validate_deadline_ns(deadline_ns) - _now(now_ns)
    return max(0, remaining) / NANOSECONDS


def narrow_deadline_ns(deadline_ns: int | None, seconds: float,
                       *, now_ns: int | None = None) -> int:
    """Anchor once or narrow an existing local deadline; never refresh it."""
    candidate = _now(now_ns) + int(_seconds(seconds) * NANOSECONDS)
    candidate = validate_deadline_ns(candidate)
    if deadline_ns is None:
        return candidate
    return min(validate_deadline_ns(deadline_ns), candidate)


def require_remaining(deadline_ns: int, *, minimum_seconds: float = 0,
                      now_ns: int | None = None) -> float:
    remaining = remaining_seconds(deadline_ns, now_ns=now_ns)
    minimum = _seconds(minimum_seconds)
    if remaining <= 0 or remaining < minimum:
        raise CommissionDeadlineExpired("commission_time_exhausted")
    return remaining
