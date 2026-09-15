"""Closed, I/O-free contract for the attended DevBox MCP surface.

The model supplies bounded intent only. Target, workspace, host, cwd, environment,
credentials and executable policy are deployment/owner facts and are deliberately
absent from every input schema.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from typing import Any, Dict, Mapping, Tuple

EFFECT_STATES = ("NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN")
TOOL_NAMES = (
    "devbox_status",
    "start_devbox_command",
    "read_devbox_process",
    "cancel_devbox_process",
)

_OPERATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_PROCESS_RE = re.compile(r"^process:[0-9a-f]{64}$")


class DevBoxContractError(ValueError):
    """Bounded refusal safe to translate at the MCP edge."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    annotations: Mapping[str, bool]


_READ_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
_MODIFY_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": False,
}

_STATUS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
_START_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation_key": {
            "type": "string",
            "minLength": 1,
            "maxLength": 96,
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$",
        },
        "command_text": {"type": "string", "minLength": 1, "maxLength": 16384},
        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 1800},
        "output_limit_bytes": {
            "type": "integer",
            "minimum": 1024,
            "maximum": 262144,
        },
    },
    "required": ["operation_key", "command_text"],
    "additionalProperties": False,
}
_READ_PROCESS_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "process_ref": {
            "type": "string",
            "pattern": r"^process:[0-9a-f]{64}$",
            "minLength": 72,
            "maxLength": 72,
        },
        "stdout_cursor": {"type": "integer", "minimum": 0},
        "stderr_cursor": {"type": "integer", "minimum": 0},
        "max_bytes": {"type": "integer", "minimum": 1024, "maximum": 262144},
    },
    "required": ["process_ref"],
    "additionalProperties": False,
}
_CANCEL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "process_ref": {
            "type": "string",
            "pattern": r"^process:[0-9a-f]{64}$",
            "minLength": 72,
            "maxLength": 72,
        },
        "reason": {"type": "string", "minLength": 1, "maxLength": 256},
    },
    "required": ["process_ref"],
    "additionalProperties": False,
}

TOOL_SPECS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name="devbox_status",
        description="Read opaque identity and working-tree status for the already-bound DevBox target.",
        input_schema=_STATUS_SCHEMA,
        annotations=_READ_ANNOTATIONS,
    ),
    ToolSpec(
        name="start_devbox_command",
        description="Start one bounded attended command in the already-bound DevBox workspace.",
        input_schema=_START_SCHEMA,
        annotations=_MODIFY_ANNOTATIONS,
    ),
    ToolSpec(
        name="read_devbox_process",
        description="Read bounded stdout/stderr and terminal truth for one owned process reference.",
        input_schema=_READ_PROCESS_SCHEMA,
        annotations=_READ_ANNOTATIONS,
    ),
    ToolSpec(
        name="cancel_devbox_process",
        description="Cancel one exact owned DevBox process generation.",
        input_schema=_CANCEL_SCHEMA,
        annotations=_MODIFY_ANNOTATIONS,
    ),
)
_TOOLS = {spec.name: spec for spec in TOOL_SPECS}


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def schema_snapshot() -> Dict[str, Any]:
    return {
        "schema": "mastermind.devbox_mcp_tools.v1",
        "effect_states": list(EFFECT_STATES),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": copy.deepcopy(dict(spec.input_schema)),
                "annotations": dict(spec.annotations),
            }
            for spec in TOOL_SPECS
        ],
    }


# Literal changes only when the reviewed model-facing contract changes.
SCHEMA_SNAPSHOT_SHA256 = "0d54b5cc717235cbc42f88c641df86c2641abaddfd56bcb3283448867d1fa1e2"


def _invalid(message: str) -> None:
    raise DevBoxContractError("INVALID_REQUEST", message)


def _mapping(arguments: object) -> Dict[str, Any]:
    if type(arguments) is not dict:
        _invalid("arguments must be an object")
    return dict(arguments)


def _exact_keys(arguments: Mapping[str, Any], required: set, optional: set) -> None:
    keys = set(arguments)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        _invalid("missing field " + sorted(missing)[0])
    if extra:
        _invalid("unexpected field " + sorted(extra)[0])


def _bounded_int(value: object, field: str, low: int, high: int) -> int:
    if type(value) is not int or value < low or value > high:
        _invalid("%s is out of bounds" % field)
    return value


def _process_ref(value: object) -> str:
    if type(value) is not str or _PROCESS_RE.fullmatch(value) is None:
        _invalid("process_ref is invalid")
    return value


def validate_tool_arguments(name: str, arguments: object) -> Dict[str, Any]:
    spec = _TOOLS.get(name)
    if spec is None:
        raise DevBoxContractError("TOOL_NOT_AVAILABLE", "tool is not available")
    request = _mapping(arguments)

    if name == "devbox_status":
        _exact_keys(request, set(), set())
        return request

    if name == "start_devbox_command":
        _exact_keys(
            request,
            {"operation_key", "command_text"},
            {"timeout_seconds", "output_limit_bytes"},
        )
        operation_key = request["operation_key"]
        command_text = request["command_text"]
        if type(operation_key) is not str or _OPERATION_RE.fullmatch(operation_key) is None:
            _invalid("operation_key is invalid")
        if (
            type(command_text) is not str
            or not command_text
            or len(command_text) > 16384
            or "\x00" in command_text
        ):
            _invalid("command_text is invalid")
        if "timeout_seconds" in request:
            _bounded_int(request["timeout_seconds"], "timeout_seconds", 1, 1800)
        if "output_limit_bytes" in request:
            _bounded_int(request["output_limit_bytes"], "output_limit_bytes", 1024, 262144)
        return request

    if name == "read_devbox_process":
        _exact_keys(
            request,
            {"process_ref"},
            {"stdout_cursor", "stderr_cursor", "max_bytes"},
        )
        _process_ref(request["process_ref"])
        for field in ("stdout_cursor", "stderr_cursor"):
            if field in request:
                _bounded_int(request[field], field, 0, (1 << 63) - 1)
        if "max_bytes" in request:
            _bounded_int(request["max_bytes"], "max_bytes", 1024, 262144)
        return request

    if name == "cancel_devbox_process":
        _exact_keys(request, {"process_ref"}, {"reason"})
        _process_ref(request["process_ref"])
        if "reason" in request:
            reason = request["reason"]
            if type(reason) is not str or not reason or len(reason) > 256 or "\x00" in reason:
                _invalid("reason is invalid")
        return request

    raise AssertionError("unreachable reviewed tool")


def schema_snapshot_sha256() -> str:
    return hashlib.sha256(_canonical_json(schema_snapshot())).hexdigest()


__all__ = [
    "DevBoxContractError",
    "EFFECT_STATES",
    "SCHEMA_SNAPSHOT_SHA256",
    "TOOL_NAMES",
    "TOOL_SPECS",
    "ToolSpec",
    "schema_snapshot",
    "schema_snapshot_sha256",
    "validate_tool_arguments",
]
