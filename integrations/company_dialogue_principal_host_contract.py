"""Closed Unix framing for the principal Company Dialogue host edge.

This module serializes one tool call and one principal MCP result. It owns no
principal identity, binding resolution, Runtime state, retry, transport,
provider action, or lifecycle.
"""
from __future__ import annotations

import json
import math
from typing import Any

from integrations.mastermind_company_mcp.principal_schemas import (
    ERROR_CODES,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    PRINCIPAL_RESULT_SCHEMA,
    PRINCIPAL_SERVER_VERSION,
    PRINCIPAL_TOOL_SPECS,
)


HOST_REQUEST_SCHEMA = "mastermind.company_dialogue_principal_host_request.v1"
TOOLS = frozenset(spec.name for spec in PRINCIPAL_TOOL_SPECS)


class PrincipalHostFrameError(ValueError):
    def __init__(self) -> None:
        super().__init__("COMPANY_DIALOGUE_PRINCIPAL_HOST_FRAME_INVALID")


def _validate_json(
    value: Any,
    *,
    depth: int = 0,
    budget: list[int] | None = None,
) -> None:
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise PrincipalHostFrameError()
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
    raise PrincipalHostFrameError()


def encode_json_frame(value: dict[str, Any], *, limit: int) -> bytes:
    try:
        if type(value) is not dict:
            raise PrincipalHostFrameError()
        _validate_json(value)
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8") + b"\n"
        if len(encoded) > limit:
            raise PrincipalHostFrameError()
        return encoded
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PrincipalHostFrameError() from None


def decode_json_frame(frame: bytes, *, limit: int) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PrincipalHostFrameError()
            result[key] = value
        return result

    def nonfinite(_):
        raise PrincipalHostFrameError()

    try:
        if (
            type(frame) is not bytes
            or not frame.endswith(b"\n")
            or frame.count(b"\n") != 1
            or len(frame) > limit
        ):
            raise PrincipalHostFrameError()
        value = json.loads(
            frame.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=nonfinite,
        )
        if type(value) is not dict:
            raise PrincipalHostFrameError()
        _validate_json(value)
        return value
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PrincipalHostFrameError() from None


def encode_request(tool: str, arguments: dict[str, Any]) -> bytes:
    if type(tool) is not str or tool not in TOOLS or type(arguments) is not dict:
        raise PrincipalHostFrameError()
    return encode_json_frame(
        {
            "schema": HOST_REQUEST_SCHEMA,
            "tool": tool,
            "arguments": arguments,
        },
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
        raise PrincipalHostFrameError()
    return value["tool"], value["arguments"]


def validate_response(frame: bytes, *, tool: str) -> dict[str, Any]:
    if type(tool) is not str or tool not in TOOLS:
        raise PrincipalHostFrameError()
    value = decode_json_frame(frame, limit=MAX_RESPONSE_BYTES)
    if (
        set(value) != {
            "schema",
            "tool",
            "ok",
            "server_version",
            "data",
            "error",
        }
        or value["schema"] != PRINCIPAL_RESULT_SCHEMA
        or value["tool"] != tool
        or value["server_version"] != PRINCIPAL_SERVER_VERSION
        or type(value["ok"]) is not bool
    ):
        raise PrincipalHostFrameError()
    if value["ok"] is True:
        if value["error"] is not None:
            raise PrincipalHostFrameError()
    else:
        error = value["error"]
        if (
            type(error) is not dict
            or set(error) - {
                "code",
                "message",
                "detail_code",
            }
            or set(error) & {"code", "message"} != {"code", "message"}
            or type(error["code"]) is not str
            or error["code"] not in ERROR_CODES
            or type(error["message"]) is not str
            or not error["message"]
        ):
            raise PrincipalHostFrameError()
        if error.get("detail_code") is not None and (
            type(error["detail_code"]) is not str
            or not error["detail_code"]
            or len(error["detail_code"]) > 64
        ):
            raise PrincipalHostFrameError()
        if value["data"] is not None and (
            type(value["data"]) is not dict
            or set(value["data"]) != {"message_key"}
            or type(value["data"]["message_key"]) is not str
        ):
            raise PrincipalHostFrameError()
    return value


__all__ = [
    "HOST_REQUEST_SCHEMA",
    "TOOLS",
    "PrincipalHostFrameError",
    "decode_json_frame",
    "decode_request",
    "encode_json_frame",
    "encode_request",
    "validate_response",
]
