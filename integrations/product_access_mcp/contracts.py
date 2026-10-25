"""Closed public-observation values; no identity, storage or lifecycle owner."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

SCHEMA = "mastermind.product_observation.v1"
MAX_BODY_BYTES = 256 * 1024
MAX_SYMBOLS = 12
ENDPOINTS = MappingProxyType({
    "health": "https://www.mastermind-x.com/api/health",
    "status": "https://www.mastermind-x.com/api/status",
    "market_pulse": "https://www.mastermind-x.com/api/intelligence-hub/market-pulse",
})
SYMBOL_PATTERN = r"[A-Z][A-Z0-9.-]{0,14}"


@dataclass(frozen=True)
class HttpObservation:
    status: int | None
    body: bytes = b""
    content_type: str | None = None
    error: str | None = None


def symbols_checked(value: object) -> tuple[str, ...]:
    if (type(value) not in (list, tuple) or not 1 <= len(value) <= MAX_SYMBOLS
            or any(type(s) is not str or re.fullmatch(SYMBOL_PATTERN, s) is None for s in value)
            or len(set(value)) != len(value)):
        raise ValueError("invalid_symbols")
    return tuple(value)


def finite(value: object, *, nonnegative: bool = False) -> int | float | None:
    if type(value) not in (int, float):
        return None
    try:
        if not math.isfinite(value) or (nonnegative and value < 0):
            return None
    except OverflowError:
        return None
    return value


def count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**53 - 1 else None


def revision(value: object, minimum: int = 7, maximum: int = 40) -> str | None:
    return value if type(value) is str and re.fullmatch(r"[0-9a-f]{%d,%d}" % (minimum, maximum), value) else None


# Match the advertised JSON Schema date-time wire format before parsing.
# datetime.fromisoformat also accepts ISO week/basic dates, arbitrary separators,
# and overflowed offset minutes that would fail the advertised schema.
RFC3339_PATTERN = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def time_observation(value: object, now: datetime) -> dict[str, Any]:
    output = {"value": None, "status": "unknown", "age_seconds": None}
    if value is None:
        return output
    try:
        if (type(value) is not str or len(value) > 64
                or re.fullmatch(RFC3339_PATTERN, value) is None):
            raise ValueError
        # Lowercase t/z are permitted; preserve the original wire spelling.
        parsed_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        stamp = datetime.fromisoformat(parsed_value)
        if stamp.utcoffset() is None:
            raise ValueError
        age = (now - stamp).total_seconds()
        return {"value": value, "status": "future" if age < -30 else "observed", "age_seconds": age}
    except (TypeError, ValueError, OverflowError):
        return {**output, "status": "invalid"}


def utc_now(value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("an explicit timezone-aware observation clock is required")
    return value.astimezone(timezone.utc)


def strict_json(body: bytes) -> dict[str, Any]:
    if type(body) is not bytes or len(body) > MAX_BODY_BYTES:
        raise ValueError("invalid_body")
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite_json")
    def floating(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("nonfinite_json")
        return value
    value = json.loads(body.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)
    if type(value) is not dict:
        raise ValueError("invalid_shape")
    return value
