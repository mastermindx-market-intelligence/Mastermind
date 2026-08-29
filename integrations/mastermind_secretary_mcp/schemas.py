"""Frozen, SDK-free contract for the six Secretary grounding reads.

This module contains data shapes and validation only. It deliberately imports
neither an MCP SDK nor any canonical owner, transport, provider, browser, host,
or persistence implementation.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

SERVER_NAME = "mastermind-secretary-grounding"
SERVER_IDENTITY = "mastermind-secretary-grounding-mcp"
SERVER_VERSION = "1.0.0"
RESULT_SCHEMA = "mastermind.secretary_grounding_mcp_result.v1"

MAX_REQUEST_BYTES = 8 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RESPONSIBILITY_REF_CHARS = 160
MAX_FACTS = 64
MAX_SOURCES_PER_FACT = 8
MAX_REASON_CODES = 16
MAX_FACT_VALUE_CHARS = 1_024

ERROR_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "STEWARD_UNAVAILABLE",
        "GROUNDING_REFUSED",
        "RESPONSE_REFUSED",
        "INTERNAL_ERROR",
    }
)
GROUNDING_STATES = frozenset({"FACTS", "UNKNOWN", "DEGRADED", "REFUSED"})
FRESHNESS_STATES = frozenset({"FRESH", "STALE", "UNKNOWN"})
SOURCE_OWNERS = frozenset(
    {
        "agent_os",
        "executive_os",
        "runtime_binding",
        "wake",
        "agent_dialogue",
        "surface_binding",
        "provider_control",
        "unknown",
    }
)

_RESPONSIBILITY_REF_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|bearer\s+[A-Za-z0-9._~-]{16,}|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"[\"']?(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)[\"']?"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{12,})"
)


class GatewayError(RuntimeError):
    """One fixed Secretary gateway refusal."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown Secretary gateway error code")
        super().__init__(code)
        self.code = code


def _string(*, max_length: int, pattern: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": max_length}
    if pattern is not None:
        value["pattern"] = pattern
    return value


def _object(properties: Mapping[str, Any], *, required: tuple[str, ...] = ()) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        value["required"] = list(required)
    return value


_RESPONSIBILITY_REF_SCHEMA = _string(
    max_length=MAX_RESPONSIBILITY_REF_CHARS,
    pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$",
)
_SOURCE_SCHEMA = _object(
    {
        "owner": {"type": "string", "enum": sorted(SOURCE_OWNERS)},
        "source_ref": _string(max_length=256),
        "observed_at": {
            "oneOf": [
                {"type": "null"},
                _string(
                    max_length=20,
                    pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
                ),
            ]
        },
    },
    required=("owner", "source_ref", "observed_at"),
)
_FACT_SCHEMA = _object(
    {
        "subject_ref": _RESPONSIBILITY_REF_SCHEMA,
        "predicate": _string(max_length=96, pattern=r"^[a-z][a-z0-9_.-]{0,95}$"),
        "value": {
            "anyOf": [
                {"type": "null"},
                {"type": "boolean"},
                {"type": "integer"},
                {"type": "number"},
                _string(max_length=MAX_FACT_VALUE_CHARS),
            ]
        },
        "freshness": {"type": "string", "enum": sorted(FRESHNESS_STATES)},
        "sources": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_SOURCES_PER_FACT,
            "items": _SOURCE_SCHEMA,
        },
    },
    required=("subject_ref", "predicate", "value", "freshness", "sources"),
)
_RESULT_DATA_SCHEMA = _object(
    {
        "state": {"type": "string", "enum": sorted(GROUNDING_STATES)},
        "facts": {"type": "array", "maxItems": MAX_FACTS, "items": _FACT_SCHEMA},
        "reason_codes": {
            "type": "array",
            "maxItems": MAX_REASON_CODES,
            "uniqueItems": True,
            "items": _string(max_length=64, pattern=r"^[A-Z][A-Z0-9_]{1,63}$"),
        },
    },
    required=("state", "facts", "reason_codes"),
)


def _output_schema(tool_name: str) -> dict[str, Any]:
    return _object(
        {
            "schema": {"const": RESULT_SCHEMA},
            "tool": {"const": tool_name},
            "ok": {"type": "boolean"},
            "server_version": {"const": SERVER_VERSION},
            "data": {"oneOf": [{"type": "null"}, _RESULT_DATA_SCHEMA]},
            "error": {
                "oneOf": [
                    {"type": "null"},
                    _object(
                        {
                            "code": {"type": "string", "enum": sorted(ERROR_CODES)},
                            "message": {"type": "string", "enum": sorted(ERROR_CODES)},
                        },
                        required=("code", "message"),
                    ),
                ]
            },
        },
        required=("schema", "tool", "ok", "server_version", "data", "error"),
    )


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """One immutable reviewed Secretary read tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    read_only: bool = True

    @property
    def annotations(self) -> dict[str, Any]:
        return {
            "title": self.name,
            "readOnlyHint": self.read_only,
            "destructiveHint": False,
            "idempotentHint": self.read_only,
            "openWorldHint": False,
        }


_ZERO_INPUT = _object({})
_RESPONSIBILITY_INPUT = _object(
    {"responsibility_ref": _RESPONSIBILITY_REF_SCHEMA},
    required=("responsibility_ref",),
)
_TOOL_ROWS = (
    (
        "list_responsibilities",
        "List source-attributed responsibility grounding from the injected Steward read port.",
        _ZERO_INPUT,
    ),
    (
        "get_responsibility",
        "Read one exact responsibility reference without heuristic identity resolution.",
        _RESPONSIBILITY_INPUT,
    ),
    (
        "get_attention",
        "Read source-attributed attention facts without selecting a person, role, or transport.",
        _ZERO_INPUT,
    ),
    (
        "get_current_runtime",
        "Read current runtime facts for one exact responsibility reference.",
        _RESPONSIBILITY_INPUT,
    ),
    (
        "explain_blocker",
        "Read source-attributed company, runtime, and surface blocker facts for one responsibility.",
        _RESPONSIBILITY_INPUT,
    ),
    (
        "resolve_surface",
        "Read exact reviewed surface resolution and health without performing any action.",
        _RESPONSIBILITY_INPUT,
    ),
)
TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    ToolSpec(name, description, copy.deepcopy(input_schema), _output_schema(name))
    for name, description, input_schema in _TOOL_ROWS
)
_TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


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


def contains_secret_shape(value: Any) -> bool:
    try:
        rendered = canonical_json(value).decode("utf-8")
    except GatewayError:
        return True
    return _SECRET_SHAPED_RE.search(rendered) is not None


def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
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
    if set(raw) != set(spec.input_schema.get("required", ())) or not set(raw) <= allowed:
        raise GatewayError("INVALID_REQUEST")
    if not raw:
        return {}
    responsibility_ref = raw.get("responsibility_ref")
    if (
        not isinstance(responsibility_ref, str)
        or _RESPONSIBILITY_REF_RE.fullmatch(responsibility_ref) is None
        or contains_secret_shape(responsibility_ref)
    ):
        raise GatewayError("INVALID_REQUEST")
    return {"responsibility_ref": responsibility_ref}


def _validated_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "owner",
        "source_ref",
        "observed_at",
    }:
        raise GatewayError("RESPONSE_REFUSED")
    owner = value["owner"]
    source_ref = value["source_ref"]
    observed_at = value["observed_at"]
    if owner not in SOURCE_OWNERS:
        raise GatewayError("RESPONSE_REFUSED")
    if (
        not isinstance(source_ref, str)
        or not 1 <= len(source_ref) <= 256
        or any(ord(character) < 32 or ord(character) == 127 for character in source_ref)
        or contains_secret_shape(source_ref)
    ):
        raise GatewayError("RESPONSE_REFUSED")
    if observed_at is not None and (
        not isinstance(observed_at, str)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            observed_at,
        )
        is None
    ):
        raise GatewayError("RESPONSE_REFUSED")
    return {
        "owner": owner,
        "source_ref": source_ref,
        "observed_at": observed_at,
    }


def _validated_fact_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GatewayError("RESPONSE_REFUSED")
        return value
    if isinstance(value, str) and (
        1 <= len(value) <= MAX_FACT_VALUE_CHARS
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
        and not contains_secret_shape(value)
    ):
        return value
    raise GatewayError("RESPONSE_REFUSED")


def _validated_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "subject_ref",
        "predicate",
        "value",
        "freshness",
        "sources",
    }:
        raise GatewayError("RESPONSE_REFUSED")
    subject_ref = value["subject_ref"]
    predicate = value["predicate"]
    freshness = value["freshness"]
    sources = value["sources"]
    if (
        not isinstance(subject_ref, str)
        or _RESPONSIBILITY_REF_RE.fullmatch(subject_ref) is None
        or contains_secret_shape(subject_ref)
        or not isinstance(predicate, str)
        or re.fullmatch(r"[a-z][a-z0-9_.-]{0,95}", predicate) is None
        or freshness not in FRESHNESS_STATES
        or not isinstance(sources, (list, tuple))
        or not 1 <= len(sources) <= MAX_SOURCES_PER_FACT
    ):
        raise GatewayError("RESPONSE_REFUSED")
    return {
        "subject_ref": subject_ref,
        "predicate": predicate,
        "value": _validated_fact_value(value["value"]),
        "freshness": freshness,
        "sources": [_validated_source(source) for source in sources],
    }


def validate_result_data(value: Any) -> dict[str, Any]:
    """Validate the complete typed Steward return without inference or repair."""

    if not isinstance(value, Mapping) or set(value) != {
        "state",
        "facts",
        "reason_codes",
    }:
        raise GatewayError("RESPONSE_REFUSED")
    state = value["state"]
    facts = value["facts"]
    reason_codes = value["reason_codes"]
    if (
        state not in GROUNDING_STATES
        or not isinstance(facts, (list, tuple))
        or len(facts) > MAX_FACTS
        or not isinstance(reason_codes, (list, tuple))
        or len(reason_codes) > MAX_REASON_CODES
        or len(reason_codes) != len(set(reason_codes))
        or any(
            not isinstance(code, str) or re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", code) is None
            for code in reason_codes
        )
    ):
        raise GatewayError("RESPONSE_REFUSED")
    normalized_facts = [_validated_fact(fact) for fact in facts]
    if state == "FACTS" and (not normalized_facts or reason_codes):
        raise GatewayError("RESPONSE_REFUSED")
    if state in {"UNKNOWN", "REFUSED"} and (normalized_facts or not reason_codes):
        raise GatewayError("RESPONSE_REFUSED")
    if state == "DEGRADED" and not reason_codes:
        raise GatewayError("RESPONSE_REFUSED")
    normalized = {
        "state": state,
        "facts": normalized_facts,
        "reason_codes": list(reason_codes),
    }
    if contains_secret_shape(normalized):
        raise GatewayError("RESPONSE_REFUSED")
    return normalized


def result_envelope(tool_name: str, *, data: Any) -> dict[str, Any]:
    if tool_name not in _TOOLS_BY_NAME:
        raise GatewayError("RESPONSE_REFUSED")
    normalized = validate_result_data(data)
    envelope = {
        "schema": RESULT_SCHEMA,
        "tool": tool_name,
        "ok": True,
        "server_version": SERVER_VERSION,
        "data": normalized,
        "error": None,
    }
    try:
        if len(canonical_json(envelope)) > MAX_RESPONSE_BYTES:
            raise GatewayError("RESPONSE_REFUSED")
    except GatewayError:
        raise GatewayError("RESPONSE_REFUSED") from None
    return envelope


def error_envelope(tool_name: str, code: str) -> dict[str, Any]:
    if code not in ERROR_CODES:
        code = "INTERNAL_ERROR"
    return {
        "schema": RESULT_SCHEMA,
        "tool": tool_name if tool_name in _TOOLS_BY_NAME else "unknown",
        "ok": False,
        "server_version": SERVER_VERSION,
        "data": None,
        "error": {"code": code, "message": code},
    }


def schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": SERVER_NAME,
        "server_identity": SERVER_IDENTITY,
        "server_version": SERVER_VERSION,
        "result_schema": RESULT_SCHEMA,
        "errors": sorted(ERROR_CODES),
        "limits": {
            "request_bytes": MAX_REQUEST_BYTES,
            "response_bytes": MAX_RESPONSE_BYTES,
            "facts": MAX_FACTS,
            "sources_per_fact": MAX_SOURCES_PER_FACT,
            "reason_codes": MAX_REASON_CODES,
        },
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": copy.deepcopy(spec.input_schema),
                "output_schema": copy.deepcopy(spec.output_schema),
                "annotations": copy.deepcopy(spec.annotations),
                "read_only": spec.read_only,
            }
            for spec in TOOL_SPECS
        ],
    }


def schema_snapshot_sha256() -> str:
    return hashlib.sha256(canonical_json(schema_snapshot())).hexdigest()


def tool_schema_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "annotations": copy.deepcopy(spec.annotations),
            "input_schema": copy.deepcopy(spec.input_schema),
            "name": spec.name,
            "output_schema": copy.deepcopy(spec.output_schema),
        }
        for spec in sorted(TOOL_SPECS, key=lambda item: item.name)
    ]


def tool_schema_digest() -> str:
    return hashlib.sha256(canonical_json(tool_schema_snapshot())).hexdigest()


# Literal review tripwires. Update only when the reviewed contract changes.
SCHEMA_SNAPSHOT_SHA256 = (
    "84344b185a4bc61443d5955a1fd787126eecf7144b237f09eda7f7ba80dfd2f9"
)
TOOL_SCHEMA_DIGEST = (
    "206ee247d84aa3c6301d2010e5bffc797fe8afd03b0f3034016b5c92d7ac3215"
)


__all__ = [
    "ERROR_CODES",
    "FRESHNESS_STATES",
    "GROUNDING_STATES",
    "GatewayError",
    "MAX_FACTS",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "MAX_SOURCES_PER_FACT",
    "RESULT_SCHEMA",
    "SCHEMA_SNAPSHOT_SHA256",
    "SERVER_IDENTITY",
    "SERVER_NAME",
    "SERVER_VERSION",
    "SOURCE_OWNERS",
    "TOOL_SCHEMA_DIGEST",
    "TOOL_SPECS",
    "ToolSpec",
    "canonical_json",
    "contains_secret_shape",
    "error_envelope",
    "result_envelope",
    "schema_snapshot",
    "schema_snapshot_sha256",
    "tool_schema_digest",
    "tool_schema_snapshot",
    "validate_result_data",
    "validate_tool_arguments",
]
