"""Strict bounded JSON transport for local proposal preparation, not admission."""
from __future__ import annotations

import json
from typing import Any
from .adapter import MAX_BYTES, MAX_DEPTH, ProposalError, bounded_plain, prepare_execution_plan

_FIELDS = {"nodes", "policies", "root_job_id", "plan_attempt_id"}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProposalError("INVALID_JSON")
        result[key] = value
    return result


def _no_constant(value):
    raise ProposalError("INVALID_JSON")


def decode_plain_json(raw: bytes) -> Any:
    """Decode bounded plain JSON without IO or caller-value diagnostics."""
    if type(raw) is not bytes or not raw:
        raise ProposalError("INVALID_JSON")
    if len(raw) > MAX_BYTES:
        raise ProposalError("INPUT_OVER_BUDGET")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ProposalError("INVALID_JSON") from None
    # Bound nesting before the recursive stdlib decoder. Braces in strings
    # do not count; JSON syntax itself is still owned by json.loads.
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ProposalError("INPUT_OVER_BUDGET")
        elif char in "]}": depth -= 1
    try:
        request = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
    except (ValueError, RecursionError):
        raise ProposalError("INVALID_JSON") from None
    bounded_plain(request)
    return request


def prepare_json(raw: bytes) -> dict[str, Any]:
    """Parse and prepare one UTF-8 request without IO or user-value diagnostics."""
    request = decode_plain_json(raw)
    if type(request) is not dict or set(request) != _FIELDS:
        raise ProposalError("INVALID_INPUT")
    return prepare_execution_plan(**request)
