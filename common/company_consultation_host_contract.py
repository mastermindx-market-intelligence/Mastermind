"""Closed local Company MCP frames; identity is supplied only by the host.

This module parses data, never authenticates a caller or dispatches a tool.
"""
from __future__ import annotations

import json
import math
from typing import Any

HOST_REQUEST_SCHEMA = "mastermind.company_consultation_host_request.v1"
MAX_REQUEST_BYTES = 32768
MAX_RESPONSE_BYTES = 65536
TOOLS = frozenset({
    "company.peers", "company.consult", "company.reply", "company.consultation",
})


class HostFrameError(ValueError):
    def __init__(self) -> None:
        super().__init__("COMPANY_CONSULTATION_FRAME_INVALID")


def _validate_json(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise HostFrameError()
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _validate_json(item, depth=depth + 1, budget=budget)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _validate_json(item, depth=depth + 1, budget=budget)
        return
    raise HostFrameError()


def encode_json_frame(value: dict[str, Any], *, limit: int) -> bytes:
    try:
        if type(value) is not dict:
            raise HostFrameError()
        _validate_json(value)
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8") + b"\n"
        if len(encoded) > limit:
            raise HostFrameError()
        return encoded
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HostFrameError() from None


def decode_json_frame(frame: bytes, *, limit: int) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise HostFrameError()
            result[key] = value
        return result

    def nonfinite(_):
        raise HostFrameError()

    try:
        if (type(frame) is not bytes or not frame.endswith(b"\n")
                or frame.count(b"\n") != 1 or len(frame) > limit):
            raise HostFrameError()
        value = json.loads(
            frame.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
        if type(value) is not dict:
            raise HostFrameError()
        _validate_json(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise HostFrameError() from None


def encode_request(tool: str, arguments: dict[str, Any]) -> bytes:
    if type(tool) is not str or tool not in TOOLS or type(arguments) is not dict:
        raise HostFrameError()
    return encode_json_frame(
        {"schema": HOST_REQUEST_SCHEMA, "tool": tool, "arguments": arguments},
        limit=MAX_REQUEST_BYTES,
    )


def decode_request(frame: bytes) -> tuple[str, dict[str, Any]]:
    value = decode_json_frame(frame, limit=MAX_REQUEST_BYTES)
    if (
        set(value) != {"schema", "tool", "arguments"}
        or value["schema"] != HOST_REQUEST_SCHEMA
        or type(value["tool"]) is not str
        or value["tool"] not in TOOLS
        or type(value["arguments"]) is not dict
    ):
        raise HostFrameError()
    return value["tool"], value["arguments"]
