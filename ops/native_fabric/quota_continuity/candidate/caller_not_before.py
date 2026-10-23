"""A caller's UTC lower bound, never capacity, retry or dispatch authority."""
from __future__ import annotations

import calendar
from datetime import datetime
import os
import re
import sys
import time

ENV = "POOL_CALLER_NOT_BEFORE"
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")


class CallerNotBeforeInvalid(ValueError):
    pass


class CallerNotBeforePending(ValueError):
    def __init__(self, eligible_at: str):
        self.eligible_at = eligible_at
        super().__init__("caller_not_before eligible_at=" + eligible_at)


def validate_not_before(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not _UTC.fullmatch(value):
        raise CallerNotBeforeInvalid("caller_not_before_invalid")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CallerNotBeforeInvalid("caller_not_before_invalid") from exc
    return value  # retain the exact request witness, including its precision


def require_not_before(value: object, *, now_ns: int | None = None) -> str | None:
    value = validate_not_before(value)
    if value is None:
        return None  # old callers do not acquire a clock or a new obligation
    instant = datetime.fromisoformat(value[:-1] + "+00:00")
    cutoff = calendar.timegm(instant.utctimetuple()) * 1_000_000_000 + instant.microsecond * 1000
    observed = time.time_ns() if now_ns is None else now_ns
    if type(observed) is not int or observed < 0:
        raise CallerNotBeforeInvalid("caller_not_before_clock_invalid")
    if observed < cutoff:
        raise CallerNotBeforePending(value)
    return value


def main() -> int:
    try:
        require_not_before(os.environ[ENV] if ENV in os.environ else None)
    except CallerNotBeforePending as exc:
        print(str(exc), file=sys.stderr)
        return 75
    except CallerNotBeforeInvalid as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
