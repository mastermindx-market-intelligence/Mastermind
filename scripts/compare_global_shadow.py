"""Bounded stdin/stdout machine interface for global research scenarios.

Usage: python3 -m scripts.compare_global_shadow < private_request.json

No storage, no market/provider/account fetch, no auth mechanism, no background
worker, no financial execution. The request must explicitly be hypothetical.
This is a local research interface, NOT an internet-exposed service.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

from portfolio.global_scenario_context import ContractError
from portfolio.global_shadow_research import AUTHORITY, compare_global_shadow

REQUEST_SCHEMA = "mastermind.global_shadow_request/v1"
MAX_REQUEST_BYTES = 256 * 1024
_FIELDS = frozenset(("schema", "context", "book", "alternatives", "scenarios", "as_of"))


class InvalidRequest(ValueError):
    """Malformed request, never a published or executable portfolio verdict."""


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InvalidRequest("duplicate_json_key")
        out[key] = value
    return out


def _reject_constant(_value: str) -> None:
    raise InvalidRequest("nonfinite_json_constant")


def parse_request(body: bytes) -> dict[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > MAX_REQUEST_BYTES:
        raise InvalidRequest("request_size_invalid")
    try:
        obj = json.loads(body.decode("utf-8"),
                         object_pairs_hook=_object_pairs,
                         parse_constant=_reject_constant)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise InvalidRequest("malformed_json") from exc
    if not isinstance(obj, dict) or set(obj) != _FIELDS or obj["schema"] != REQUEST_SCHEMA:
        raise InvalidRequest("request_schema_invalid")
    if not isinstance(obj["context"], dict) or not isinstance(obj["book"], dict) or (
            not isinstance(obj["alternatives"], list) or not isinstance(obj["scenarios"], list) or
            not isinstance(obj["as_of"], str)):
        raise InvalidRequest("request_types_invalid")
    return obj


def execute_request(obj: Mapping[str, Any]) -> dict[str, Any]:
    """No data I/O; calculation and source qualification owned by the core."""
    return compare_global_shadow(
        context=obj["context"], book=obj["book"],
        alternatives=obj["alternatives"], scenarios=obj["scenarios"],
        as_of=obj["as_of"],
    )


def main() -> int:
    try:
        data = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        request = parse_request(data)
        result = execute_request(request)
        payload = json.dumps(result, allow_nan=False, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":"))
    except (InvalidRequest, ContractError, TypeError, ValueError, OverflowError, RecursionError):
        # Never reflect raw JSON, holdings, credentials or exception messages.
        payload = json.dumps({
            "schema": "mastermind.global_shadow_response_error/v1",
            "status": "UNAVAILABLE", "reason": "request_unqualified",
            "authority": dict(AUTHORITY), "display_only": True,
            "no_predictive_claim": True,
        }, sort_keys=True)
        sys.stdout.write(payload + "\n")
        return 2
    sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
