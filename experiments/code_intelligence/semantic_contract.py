"""Frozen, closed contract for the six Mastermind semantic tools.

This module is the entire model-facing surface of the C0 experiment. It is
deliberately hostile to widening:

* the tool census is fixed at exactly six tools;
* every schema is closed (``additionalProperties: false``);
* no argument may select a location outside the sealed worktree, and no
  argument may name a root, project, executable, command, environment or
  session — the host owns all of those;
* argument sizes and result limits are bounded.

A backend never sees a caller-supplied root. It is handed one already-sealed
workspace by the host runner.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

__all__ = [
    "MAX_ARGUMENT_BYTES",
    "MAX_LIMIT",
    "DEFAULT_LIMIT",
    "SEMANTIC_TOOL_NAMES",
    "SEMANTIC_TOOL_SCHEMAS",
    "SemanticContractError",
    "SemanticRequest",
    "SemanticResponse",
    "canonical_json",
    "semantic_tool_schema_digest",
    "validate_semantic_request",
]

MAX_ARGUMENT_BYTES = 4096
MAX_LIMIT = 100
DEFAULT_LIMIT = 50

SEMANTIC_TOOL_NAMES = (
    "workspace_status",
    "symbol_overview",
    "find_symbol",
    "find_references",
    "find_implementations",
    "diagnostics",
)


class SemanticContractError(Exception):
    """A request violated the frozen contract. Always fail closed."""


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact, ASCII-only, no NaN."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _relative_file_schema() -> dict[str, Any]:
    return {
        "type": ["string", "null"],
        "maxLength": MAX_ARGUMENT_BYTES,
        "description": (
            "Repository-relative file inside the already-sealed workspace. "
            "Never selects or changes the workspace."
        ),
    }


def _limit_schema() -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": MAX_LIMIT,
        "description": "Maximum rows returned.",
    }


def _name_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_ARGUMENT_BYTES,
        "description": "Symbol name to resolve.",
    }


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


SEMANTIC_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "workspace_status": _object({}, []),
    "symbol_overview": _object(
        {
            "relative_file": _relative_file_schema(),
            "query": {
                "type": ["string", "null"],
                "maxLength": MAX_ARGUMENT_BYTES,
                "description": "Optional substring filter over symbol names.",
            },
            "limit": _limit_schema(),
        },
        [],
    ),
    "find_symbol": _object(
        {
            "name": _name_schema(),
            "relative_file": _relative_file_schema(),
            "limit": _limit_schema(),
        },
        ["name"],
    ),
    "find_references": _object(
        {
            "name": _name_schema(),
            "relative_file": _relative_file_schema(),
            "limit": _limit_schema(),
        },
        ["name"],
    ),
    "find_implementations": _object(
        {
            "name": _name_schema(),
            "relative_file": _relative_file_schema(),
            "limit": _limit_schema(),
        },
        ["name"],
    ),
    "diagnostics": _object(
        {
            "relative_file": _relative_file_schema(),
            "limit": _limit_schema(),
        },
        [],
    ),
}


@dataclass(frozen=True, slots=True)
class SemanticRequest:
    """A validated, bounded call against the closed contract."""

    tool: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SemanticResponse:
    """A bounded result, bound to the workspace seal and backend identity."""

    tool: str
    workspace_binding_digest: str
    backend_digest: str
    payload: Mapping[str, Any]


def _reject(reason: str) -> None:
    raise SemanticContractError(reason)


def _validate_relative_file(value: str) -> str:
    if "\x00" in value:
        _reject("relative_file contains NUL")
    if len(value.encode("utf-8")) > MAX_ARGUMENT_BYTES:
        _reject("relative_file exceeds argument ceiling")
    if not value or value.strip() != value:
        _reject("relative_file is empty or padded")
    if "\\" in value:
        _reject("relative_file contains a backslash")
    if value.startswith("/"):
        _reject("relative_file is absolute")
    if value.startswith("~"):
        _reject("relative_file references a home directory")
    # Windows drive or UNC style.
    if len(value) >= 2 and value[1] == ":":
        _reject("relative_file names a drive")
    parts = value.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            _reject("relative_file contains an empty or traversing component")
    return value


def _validate_string(tool: str, field: str, value: Any) -> str:
    if not isinstance(value, str):
        _reject(f"{tool}.{field} must be a string")
    if "\x00" in value:
        _reject(f"{tool}.{field} contains NUL")
    if len(value.encode("utf-8")) > MAX_ARGUMENT_BYTES:
        _reject(f"{tool}.{field} exceeds {MAX_ARGUMENT_BYTES} bytes")
    return value


def _validate_limit(tool: str, value: Any) -> int:
    # bool is an int subclass; a closed contract must not read True as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        _reject(f"{tool}.limit must be an integer")
    if value < 1 or value > MAX_LIMIT:
        _reject(f"{tool}.limit must be within 1..{MAX_LIMIT}")
    return value


def validate_semantic_request(
    tool: str, arguments: Mapping[str, Any]
) -> SemanticRequest:
    """Validate a call against the frozen contract, or refuse it."""
    if not isinstance(tool, str) or tool not in SEMANTIC_TOOL_SCHEMAS:
        _reject(f"unknown tool {tool!r}")
    if not isinstance(arguments, Mapping):
        _reject("arguments must be a mapping")

    schema = SEMANTIC_TOOL_SCHEMAS[tool]
    allowed = set(schema["properties"])
    supplied = set(arguments)

    unknown = supplied - allowed
    if unknown:
        _reject(f"{tool} rejects unknown argument(s): {sorted(unknown)}")

    missing = set(schema["required"]) - supplied
    if missing:
        _reject(f"{tool} is missing required argument(s): {sorted(missing)}")

    cleaned: dict[str, Any] = {}
    for field, value in arguments.items():
        if value is None:
            if field in schema["required"]:
                _reject(f"{tool}.{field} may not be null")
            cleaned[field] = None
            continue
        if field == "limit":
            cleaned[field] = _validate_limit(tool, value)
        elif field == "relative_file":
            cleaned[field] = _validate_relative_file(
                _validate_string(tool, field, value)
            )
        else:
            cleaned[field] = _validate_string(tool, field, value)

    if "limit" in allowed and "limit" not in cleaned:
        cleaned["limit"] = DEFAULT_LIMIT

    return SemanticRequest(tool=tool, arguments=MappingProxyType(cleaned))


def semantic_tool_schema_digest() -> str:
    """SHA-256 over the canonical frozen schema bytes."""
    return hashlib.sha256(
        canonical_json(SEMANTIC_TOOL_SCHEMAS).encode("utf-8")
    ).hexdigest()
