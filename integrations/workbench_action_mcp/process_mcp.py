"""MCP schema/dispatch projection for bounded attended validation processes.

Authentication stays in the parent Workbench Action server. This module only
owns closed tool contracts and dispatch into the already-composed process owner.
It does not launch processes itself, issue authority, or persist state.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator
from mcp.types import Tool, ToolAnnotations

from .contracts import ActionCaller
from .process_contracts import (
    MAX_COMMAND_REF_BYTES,
    MAX_RECIPE_OUTPUT_BYTES,
    MAX_RECIPE_TIMEOUT_SECONDS,
)
from .process_port import AttendedProcessPorts

LIST_RECIPES_TOOL = "list_validation_recipes"
PREPARE_COMMAND_TOOL = "prepare_attended_command"
START_COMMAND_TOOL = "start_attended_command"
RECONCILE_COMMAND_TOOL = "reconcile_attended_command_start"
READ_PROCESS_TOOL = "read_process"
PROCESS_TOOL_NAMES = frozenset(
    {
        LIST_RECIPES_TOOL,
        PREPARE_COMMAND_TOOL,
        START_COMMAND_TOOL,
        RECONCILE_COMMAND_TOOL,
        READ_PROCESS_TOOL,
    }
)
PROCESS_STATES = (
    "NOT_STARTED",
    "STARTING",
    "RUNNING",
    "START_FAILED",
    "EXITED",
    "TIMED_OUT",
    "CANCELLED",
    "OUTPUT_LIMIT",
    "RUNNER_FAILED",
    "OWNER_LOST",
)

_PROJECT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 256,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
}
_REF = {
    "type": "string",
    "minLength": 1,
    "maxLength": 256,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
}
_DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_LIST_INPUT = {
    "type": "object",
    "properties": {"project_ref": dict(_PROJECT)},
    "required": ["project_ref"],
    "additionalProperties": False,
}
_PREPARE_INPUT = {
    "type": "object",
    "properties": {
        "project_ref": dict(_PROJECT),
        "recipe_id": {
            "type": "string",
            "minLength": 3,
            "maxLength": 64,
            "pattern": "^[a-z][a-z0-9._-]{2,63}$",
        },
        "timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_RECIPE_TIMEOUT_SECONDS,
        },
        "max_output_bytes": {
            "type": "integer",
            "minimum": 1024,
            "maximum": MAX_RECIPE_OUTPUT_BYTES,
        },
    },
    "required": ["project_ref", "recipe_id"],
    "additionalProperties": False,
}
_COMMAND_REF_INPUT = {
    "type": "object",
    "properties": {
        "command_ref": {
            "type": "string",
            "minLength": 16,
            "maxLength": MAX_COMMAND_REF_BYTES,
        }
    },
    "required": ["command_ref"],
    "additionalProperties": False,
}
_READ_INPUT = {
    "type": "object",
    "properties": {
        **_COMMAND_REF_INPUT["properties"],
        "stdout_offset": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1},
        "stderr_offset": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1},
        "max_bytes": {"type": "integer", "minimum": 1, "maximum": 65536},
    },
    "required": ["command_ref"],
    "additionalProperties": False,
}
_RECIPE_ROW = {
    "type": "object",
    "properties": {
        "recipe_id": {
            "type": "string",
            "minLength": 3,
            "maxLength": 64,
            "pattern": "^[a-z][a-z0-9._-]{2,63}$",
        },
        "description": {"type": "string", "minLength": 1, "maxLength": 512},
        "timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_RECIPE_TIMEOUT_SECONDS,
        },
        "max_output_bytes": {
            "type": "integer",
            "minimum": 1024,
            "maximum": MAX_RECIPE_OUTPUT_BYTES,
        },
        "recipe_digest": dict(_DIGEST),
    },
    "required": [
        "recipe_id",
        "description",
        "timeout_seconds",
        "max_output_bytes",
        "recipe_digest",
    ],
    "additionalProperties": False,
}
_LIST_OUTPUT = {
    "type": "object",
    "properties": {
        "status": {"const": "OK"},
        "project_ref": dict(_PROJECT),
        "generation": dict(_REF),
        "observed_at_ms": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1},
        "recipes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "items": _RECIPE_ROW,
        },
    },
    "required": ["status", "project_ref", "generation", "observed_at_ms", "recipes"],
    "additionalProperties": False,
}
_PREPARE_OUTPUT = {
    "type": "object",
    "properties": {
        "status": {"const": "PREPARED"},
        "command_ref": {
            "type": "string",
            "minLength": 16,
            "maxLength": MAX_COMMAND_REF_BYTES,
        },
        "process_ref": dict(_REF),
        "project_ref": dict(_PROJECT),
        "responsibility_ref": dict(_REF),
        "operation_ref": dict(_REF),
        "generation": dict(_REF),
        "recipe_id": _RECIPE_ROW["properties"]["recipe_id"],
        "recipe_digest": dict(_DIGEST),
        "runner_digest": dict(_DIGEST),
        "timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_RECIPE_TIMEOUT_SECONDS,
        },
        "max_output_bytes": {
            "type": "integer",
            "minimum": 1024,
            "maximum": MAX_RECIPE_OUTPUT_BYTES,
        },
        "expires_at_ms": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1},
    },
    "required": [
        "status",
        "command_ref",
        "process_ref",
        "project_ref",
        "responsibility_ref",
        "operation_ref",
        "generation",
        "recipe_id",
        "recipe_digest",
        "runner_digest",
        "timeout_seconds",
        "max_output_bytes",
        "expires_at_ms",
    ],
    "additionalProperties": False,
}
_STATE_PROPERTIES = {
    "status": {"const": "OK"},
    "effect_state": {
        "type": "string",
        "enum": ["NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"],
    },
    "process_state": {"type": "string", "enum": list(PROCESS_STATES)},
    "process_ref": dict(_REF),
    "project_ref": dict(_PROJECT),
    "responsibility_ref": dict(_REF),
    "operation_ref": dict(_REF),
    "generation": dict(_REF),
    "recipe_id": _RECIPE_ROW["properties"]["recipe_id"],
    "recipe_digest": dict(_DIGEST),
    "runner_digest": dict(_DIGEST),
    "observed_at_ms": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1},
    "exit_code": {
        "anyOf": [
            {"type": "null"},
            {"type": "integer", "minimum": -2**31, "maximum": 2**31 - 1},
        ]
    },
    "stdout_bytes": {"type": "integer", "minimum": 0, "maximum": MAX_RECIPE_OUTPUT_BYTES},
    "stderr_bytes": {"type": "integer", "minimum": 0, "maximum": MAX_RECIPE_OUTPUT_BYTES},
}
_STATE_REQUIRED = list(_STATE_PROPERTIES)
_STATE_OUTPUT = {
    "type": "object",
    "properties": _STATE_PROPERTIES,
    "required": _STATE_REQUIRED,
    "additionalProperties": False,
}
_PAGE = {
    "type": "object",
    "properties": {
        "offset_start": {"type": "integer", "minimum": 0, "maximum": MAX_RECIPE_OUTPUT_BYTES},
        "offset_end": {"type": "integer", "minimum": 0, "maximum": MAX_RECIPE_OUTPUT_BYTES},
        "retained_start": {"const": 0},
        "retained_end": {"type": "integer", "minimum": 0, "maximum": MAX_RECIPE_OUTPUT_BYTES},
        "gap_ranges": {"type": "array", "maxItems": 0},
        "content": {"type": "string", "maxLength": 65536},
        "truncated": {"type": "boolean"},
        "next_offset": {
            "anyOf": [
                {"type": "null"},
                {"type": "integer", "minimum": 0, "maximum": MAX_RECIPE_OUTPUT_BYTES},
            ]
        },
    },
    "required": [
        "offset_start",
        "offset_end",
        "retained_start",
        "retained_end",
        "gap_ranges",
        "content",
        "truncated",
        "next_offset",
    ],
    "additionalProperties": False,
}
_READ_OUTPUT = {
    "type": "object",
    "properties": {**_STATE_PROPERTIES, "stdout": _PAGE, "stderr": _PAGE},
    "required": [*_STATE_REQUIRED, "stdout", "stderr"],
    "additionalProperties": False,
}


class ProcessMcpSurface:
    def __init__(self, ports: AttendedProcessPorts) -> None:
        if not isinstance(ports, AttendedProcessPorts):
            raise TypeError("AttendedProcessPorts required")
        self._ports = ports
        self._input = {
            LIST_RECIPES_TOOL: Draft202012Validator(_LIST_INPUT),
            PREPARE_COMMAND_TOOL: Draft202012Validator(_PREPARE_INPUT),
            START_COMMAND_TOOL: Draft202012Validator(_COMMAND_REF_INPUT),
            RECONCILE_COMMAND_TOOL: Draft202012Validator(_COMMAND_REF_INPUT),
            READ_PROCESS_TOOL: Draft202012Validator(_READ_INPUT),
        }
        self._output = {
            LIST_RECIPES_TOOL: Draft202012Validator(_LIST_OUTPUT),
            PREPARE_COMMAND_TOOL: Draft202012Validator(_PREPARE_OUTPUT),
            START_COMMAND_TOOL: Draft202012Validator(_STATE_OUTPUT),
            RECONCILE_COMMAND_TOOL: Draft202012Validator(_STATE_OUTPUT),
            READ_PROCESS_TOOL: Draft202012Validator(_READ_OUTPUT),
        }
        for schema in (
            _LIST_INPUT,
            _PREPARE_INPUT,
            _COMMAND_REF_INPUT,
            _READ_INPUT,
            _LIST_OUTPUT,
            _PREPARE_OUTPUT,
            _STATE_OUTPUT,
            _READ_OUTPUT,
        ):
            Draft202012Validator.check_schema(schema)

    @property
    def names(self) -> frozenset[str]:
        return PROCESS_TOOL_NAMES

    @staticmethod
    def effect_unknown_on_post_auth(name: str) -> bool:
        return name == START_COMMAND_TOOL

    def validate_input(self, name: str, request: object) -> Mapping[str, Any]:
        validator = self._input.get(name)
        if validator is None:
            raise ValueError("process tool unavailable")
        validator.validate(request)
        if type(request) is not dict:
            raise ValueError("process request must be object")
        return request

    def validate_output(self, name: str, result: object) -> Mapping[str, Any]:
        validator = self._output.get(name)
        if validator is None:
            raise ValueError("process tool unavailable")
        validator.validate(result)
        if type(result) is not dict:
            raise ValueError("process result must be object")
        return result

    async def call(
        self, name: str, caller: ActionCaller, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if name == LIST_RECIPES_TOOL:
            return await self._ports.list_recipes(caller, request["project_ref"])
        if name == PREPARE_COMMAND_TOOL:
            return await self._ports.prepare(caller, request)
        if name == START_COMMAND_TOOL:
            return await self._ports.start(caller, request["command_ref"])
        if name == RECONCILE_COMMAND_TOOL:
            return await self._ports.reconcile_start(caller, request["command_ref"])
        if name == READ_PROCESS_TOOL:
            return await self._ports.read(caller, request)
        raise ValueError("process tool unavailable")

    def tools(self) -> list[Tool]:
        common_read = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
        return [
            Tool(
                name=LIST_RECIPES_TOOL,
                description=(
                    "List owner-approved bounded validation recipes for the already-selected "
                    "project. No executable, shell or environment is model-selectable."
                ),
                inputSchema=_LIST_INPUT,
                outputSchema=_LIST_OUTPUT,
                annotations=common_read,
            ),
            Tool(
                name=PREPARE_COMMAND_TOOL,
                description=(
                    "Prepare one owner-approved validation recipe with optional lower timeout/output "
                    "ceilings. Preparation starts no process."
                ),
                inputSchema=_PREPARE_INPUT,
                outputSchema=_PREPARE_OUTPUT,
                annotations=common_read,
            ),
            Tool(
                name=START_COMMAND_TOOL,
                description=(
                    "Start exactly one previously prepared attended validation process. The only "
                    "authority input is its signed command reference; never blindly retry after an "
                    "ambiguous response."
                ),
                inputSchema=_COMMAND_REF_INPUT,
                outputSchema=_STATE_OUTPUT,
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=RECONCILE_COMMAND_TOOL,
                description=(
                    "Reconcile the original prepared process start without launching another process."
                ),
                inputSchema=_COMMAND_REF_INPUT,
                outputSchema=_STATE_OUTPUT,
                annotations=common_read,
            ),
            Tool(
                name=READ_PROCESS_TOOL,
                description=(
                    "Read bounded stdout/stderr pages plus non-truncatable terminal/effect truth for "
                    "the original prepared process."
                ),
                inputSchema=_READ_INPUT,
                outputSchema=_READ_OUTPUT,
                annotations=common_read,
            ),
        ]


__all__ = [
    "LIST_RECIPES_TOOL",
    "PREPARE_COMMAND_TOOL",
    "PROCESS_TOOL_NAMES",
    "READ_PROCESS_TOOL",
    "RECONCILE_COMMAND_TOOL",
    "START_COMMAND_TOOL",
    "ProcessMcpSurface",
]
