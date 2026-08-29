"""Frozen, SDK-free schema surface for bounded company dialogue.

This module is deliberately data and validation only.  It imports neither the
MCP SDK nor a transport implementation.  Identity, thread, operation, and
runtime binding fields are structurally absent from every model-visible input.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    MAX_EVIDENCE_REFS,
    validate_body,
    validate_evidence_ref,
)

SERVER_NAME = "mastermind-company-dialogue"
SERVER_IDENTITY = "mastermind-company-dialogue-mcp"
SERVER_VERSION = "1.0.0"
RESULT_SCHEMA = "mastermind.company_dialogue_mcp_result.v1"

MAX_REQUEST_BYTES = 32 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_ERROR_MESSAGE_CHARS = 240

ERROR_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "BINDING_UNAVAILABLE",
        "DIALOGUE_REFUSED",
        "SERVICE_UNAVAILABLE",
        "INTERNAL_ERROR",
    }
)

_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|bearer\s+[A-Za-z0-9._~-]{16,})"
)
_MESSAGE_KEY_RE = re.compile(r"\Aasd-[a-z0-9][a-z0-9-]{7,95}\Z")


class GatewayError(RuntimeError):
    """One fixed MCP-facade refusal."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown company-dialogue gateway error code")
        super().__init__(message or code)
        self.code = code


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """One immutable reviewed tool row."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_description: str
    read_only: bool

    @property
    def annotations(self) -> dict[str, Any]:
        return {
            "title": self.name,
            "readOnlyHint": self.read_only,
            "destructiveHint": False,
            "idempotentHint": self.read_only,
            "openWorldHint": False,
        }


def _string(*, max_length: int, min_length: int = 1, pattern: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "string",
        "minLength": min_length,
        "maxLength": max_length,
    }
    if pattern is not None:
        value["pattern"] = pattern
    return value


_EVIDENCE_REFS = {
    "type": "array",
    "maxItems": MAX_EVIDENCE_REFS,
    "uniqueItems": True,
    "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": 500,
        "pattern": r"^https://(?:github\.com|linear\.app)/",
    },
}

_OPTION = {
    "type": "object",
    "properties": {
        "id": _string(max_length=32, pattern=r"^opt-[a-z0-9][a-z0-9-]{1,31}$"),
        "summary": _string(max_length=400),
        "consequence": _string(max_length=600),
        "disposition": {"type": "string", "enum": ["CONTINUE", "STOP"]},
        "authority_effect": {
            "type": "string",
            "enum": ["NONE", "CANONICAL_REF_REQUIRED", "CHAIRMAN_REQUIRED"],
        },
    },
    "required": ["id", "summary", "consequence", "disposition", "authority_effect"],
    "additionalProperties": False,
}


def _object(properties: Mapping[str, Any], *, required: tuple[str, ...] = ()) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        result["required"] = list(required)
    return result


_OUTPUT_DESCRIPTION = (
    "mastermind.company_dialogue_mcp_result.v1 fixed bounded envelope. Dialogue "
    "transport evidence is not Executive lifecycle or production authority."
)

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="read_thread",
        description=(
            "Read only the already-bound company-dialogue thread through the existing "
            "Agent Relay service. The caller cannot select identity, channel, thread, or context."
        ),
        input_schema=_object({}),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=True,
    ),
    ToolSpec(
        name="ack",
        description=(
            "Acknowledge the already-bound commissioned context. This emits dialogue "
            "transport only and creates no Job, Attempt, Worker, grant, retry, or Wake authority."
        ),
        input_schema=_object({"evidence_refs": _EVIDENCE_REFS}),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
    ToolSpec(
        name="progress",
        description=(
            "Emit bounded descriptive progress in the already-bound company dialogue. "
            "It cannot mutate Executive lifecycle or select a transport target."
        ),
        input_schema=_object(
            {
                "stage": _string(max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$"),
                "completed": _string(max_length=700),
                "next": _string(max_length=700),
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=("stage", "completed", "next"),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
    ToolSpec(
        name="blocked",
        description=(
            "Report one bounded blocker in the already-bound dialogue. This requests "
            "attention only; it cannot reassign, retry, stop, or widen the underlying work."
        ),
        input_schema=_object(
            {
                "blocker_code": _string(max_length=64, pattern=r"^[A-Z][A-Z0-9_]{1,63}$"),
                "reason": _string(max_length=700),
                "needed_from": {"type": "string", "enum": ["sol", "chairman", "external"]},
                "work_paused": {"type": "boolean"},
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=("blocker_code", "reason", "needed_from", "work_paused"),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
    ToolSpec(
        name="request_decision",
        description=(
            "Request one bounded decision within the already-bound commission. It "
            "cannot author a ruling, continue/stop edge, or canonical authority record."
        ),
        input_schema=_object(
            {
                "question": _string(max_length=700),
                "outcome_impact": _string(max_length=700),
                "options": {"type": "array", "minItems": 1, "maxItems": 3, "items": _OPTION},
                "recommendation": _string(
                    max_length=32, pattern=r"^opt-[a-z0-9][a-z0-9-]{1,31}$"
                ),
                "work_paused": {"type": "boolean"},
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=(
                "question",
                "outcome_impact",
                "options",
                "recommendation",
                "work_paused",
            ),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
    ToolSpec(
        name="result",
        description=(
            "Return one bounded result in the already-bound company dialogue. This is "
            "transport evidence only and does not complete a Job or accept production."
        ),
        input_schema=_object(
            {
                "status": {"type": "string", "enum": ["PASS", "PARTIAL", "BLOCKED", "FAIL"]},
                "result": _string(max_length=900),
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=("status", "result"),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
)

_TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}
_MESSAGE_TYPES = {
    "ack": "ACK",
    "progress": "PROGRESS",
    "blocked": "BLOCKED",
    "request_decision": "DECISION_REQUEST",
    "result": "RESULT",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise GatewayError("INVALID_REQUEST")


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise GatewayError("INVALID_REQUEST") from None


def _validated_evidence_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_REFS:
        raise GatewayError("INVALID_REQUEST")
    try:
        refs = [validate_evidence_ref(item) for item in value]
    except DialogueContractError:
        raise GatewayError("INVALID_REQUEST") from None
    if len(refs) != len(set(refs)):
        raise GatewayError("INVALID_REQUEST")
    return refs


def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    """Strictly normalize one model-visible call without accepting binding fields."""

    spec = _TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        raise GatewayError("INVALID_REQUEST")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise GatewayError("INVALID_REQUEST")
    raw = dict(arguments)
    if len(canonical_json({"arguments": raw})) > MAX_REQUEST_BYTES:
        raise GatewayError("INVALID_REQUEST")
    allowed = set(spec.input_schema["properties"])
    if not set(raw) <= allowed:
        raise GatewayError("INVALID_REQUEST")
    required = set(spec.input_schema.get("required", ()))
    if not required <= set(raw):
        raise GatewayError("INVALID_REQUEST")
    if tool_name == "read_thread":
        if raw:
            raise GatewayError("INVALID_REQUEST")
        return {}

    evidence_refs = _validated_evidence_refs(raw.pop("evidence_refs", None))
    message_type = _MESSAGE_TYPES[tool_name]
    body = {"acknowledged": True} if tool_name == "ack" else raw
    try:
        normalized = validate_body(message_type, body)
    except DialogueContractError:
        raise GatewayError("INVALID_REQUEST") from None
    if tool_name == "ack":
        return {"evidence_refs": evidence_refs}
    return {**normalized, "evidence_refs": evidence_refs}


def _safe_message(code: str, message: Any) -> str:
    if not isinstance(message, str) or _SECRET_SHAPED_RE.search(message):
        return code
    if any(ord(character) < 32 or ord(character) == 127 for character in message):
        return code
    cleaned = message.strip()
    if not cleaned:
        return code
    return cleaned[:MAX_ERROR_MESSAGE_CHARS]


def result_envelope(tool: str, *, data: Any) -> dict[str, Any]:
    envelope = {
        "schema": RESULT_SCHEMA,
        "tool": tool if tool in _TOOLS_BY_NAME else "unknown",
        "ok": True,
        "server_version": SERVER_VERSION,
        "data": _jsonable(data),
        "error": None,
    }
    if len(canonical_json(envelope)) > MAX_RESPONSE_BYTES:
        raise GatewayError("INTERNAL_ERROR")
    return envelope


def error_envelope(
    tool: str,
    *,
    code: str,
    message: Any,
    detail_code: str | None = None,
    reconciliation_message_key: str | None = None,
) -> dict[str, Any]:
    if code not in ERROR_CODES:
        code = "INTERNAL_ERROR"
    error: dict[str, Any] = {"code": code, "message": _safe_message(code, message)}
    if detail_code is not None and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", detail_code):
        error["detail_code"] = detail_code
    data = None
    if (
        isinstance(reconciliation_message_key, str)
        and _MESSAGE_KEY_RE.fullmatch(reconciliation_message_key) is not None
    ):
        data = {"message_key": reconciliation_message_key}
    return {
        "schema": RESULT_SCHEMA,
        "tool": tool if tool in _TOOLS_BY_NAME else "unknown",
        "ok": False,
        "server_version": SERVER_VERSION,
        "data": data,
        "error": error,
    }


def schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": SERVER_NAME,
        "server_version": SERVER_VERSION,
        "result_schema": RESULT_SCHEMA,
        "errors": sorted(ERROR_CODES),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": copy.deepcopy(spec.input_schema),
                "output_description": spec.output_description,
                "annotations": copy.deepcopy(spec.annotations),
                "read_only": spec.read_only,
            }
            for spec in TOOL_SPECS
        ],
    }


def schema_snapshot_sha256() -> str:
    return hashlib.sha256(canonical_json(schema_snapshot())).hexdigest()


def tool_schema_snapshot() -> list[dict[str, Any]]:
    """Project the exact shape used by Executive OS MCP observation."""

    return [
        {
            "annotations": copy.deepcopy(spec.annotations),
            "input_schema": copy.deepcopy(spec.input_schema),
            "name": spec.name,
            "output_schema": None,
        }
        for spec in sorted(TOOL_SPECS, key=lambda item: item.name)
    ]


def tool_schema_digest() -> str:
    return hashlib.sha256(canonical_json(tool_schema_snapshot())).hexdigest()


# Deliberately literal: any reviewed schema/description/annotation change must
# update this value explicitly and is therefore visible in review.
SCHEMA_SNAPSHOT_SHA256 = (
    "7de48b158725f04a37bfb54379d29c9a2c4e41d0880ac6c04aaa150dde42322d"
)
TOOL_SCHEMA_DIGEST = (
    "792f03d4a17fe258df62600a79f165cede13d1fb0712a8835b857b027b51f79c"
)


__all__ = [
    "ERROR_CODES",
    "GatewayError",
    "RESULT_SCHEMA",
    "SCHEMA_SNAPSHOT_SHA256",
    "SERVER_IDENTITY",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_SCHEMA_DIGEST",
    "TOOL_SPECS",
    "ToolSpec",
    "canonical_json",
    "error_envelope",
    "result_envelope",
    "schema_snapshot",
    "schema_snapshot_sha256",
    "tool_schema_digest",
    "tool_schema_snapshot",
    "validate_tool_arguments",
]
