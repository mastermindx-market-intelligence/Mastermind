"""Closed tool contracts for the private Mastermind Context MCP surface.

These are transport schemas only. They do not select roots, owners, workstreams,
repositories, runtime identities, or permissions. The authenticated deployment port
must resolve all caller-visible references through existing Context Fabric owners.
"""

from __future__ import annotations

from typing import Any

TOOL_NAMES = (
    "resolve_context",
    "expand_context",
    "diff_context",
    "atlas_search",
    "workspace_overlay",
)

_PROJECT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 128,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
}
_REF = {
    "type": "string",
    "minLength": 1,
    "maxLength": 512,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/@#-]*$",
}
_SHA = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
_DIGEST = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_ID_LIST = {
    "type": "array",
    "maxItems": 16,
    "uniqueItems": True,
    "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": 256,
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/#-]*$",
    },
}


INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "resolve_context": {
        "type": "object",
        "properties": {
            "project_ref": _PROJECT,
            "task": {"type": "string", "minLength": 1, "maxLength": 8192},
            "workstreams": _ID_LIST,
            "linear": _ID_LIST,
            "repositories": _ID_LIST,
            "operation_key": {
                "type": ["string", "null"],
                "minLength": 1,
                "maxLength": 256,
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
            },
            "requires_executive": {"type": "boolean"},
            "prior_context_ref": {"oneOf": [_REF, {"type": "null"}]},
            "max_items": {"type": "integer", "minimum": 1, "maximum": 64},
        },
        "required": ["project_ref", "task"],
        "additionalProperties": False,
    },
    "expand_context": {
        "type": "object",
        "properties": {
            "project_ref": _PROJECT,
            "context_ref": _REF,
            "line_start": {"type": "integer", "minimum": 0, "maximum": 1048576},
            "line_count": {"type": "integer", "minimum": 1, "maximum": 256},
        },
        "required": ["project_ref", "context_ref"],
        "additionalProperties": False,
    },
    "diff_context": {
        "type": "object",
        "properties": {
            "project_ref": _PROJECT,
            "before_context_ref": _REF,
            "task": {"type": "string", "minLength": 1, "maxLength": 8192},
            "workstreams": _ID_LIST,
            "linear": _ID_LIST,
            "repositories": _ID_LIST,
            "operation_key": {
                "type": ["string", "null"],
                "minLength": 1,
                "maxLength": 256,
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
            },
            "requires_executive": {"type": "boolean"},
        },
        "required": ["project_ref", "before_context_ref", "task"],
        "additionalProperties": False,
    },
    "atlas_search": {
        "type": "object",
        "properties": {
            "project_ref": _PROJECT,
            "repository": {
                "type": "string",
                "minLength": 3,
                "maxLength": 256,
                "pattern": "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
            },
            "revision": {"oneOf": [_SHA, {"type": "null"}]},
            "term": {"type": "string", "minLength": 1, "maxLength": 1024},
            "kind": {
                "type": "string",
                "enum": ["any", "symbol", "heading", "reference", "import"],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["project_ref", "repository", "term"],
        "additionalProperties": False,
    },
    "workspace_overlay": {
        "type": "object",
        "properties": {
            "project_ref": _PROJECT,
            "operation_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 96,
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
        },
        "required": ["project_ref", "operation_id"],
        "additionalProperties": False,
    },
}


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["OK", "PARTIAL", "REFUSED"]},
        "schema": {"type": "string", "minLength": 1, "maxLength": 128},
        "project_ref": _PROJECT,
        "context_ref": {"oneOf": [_REF, {"type": "null"}]},
        "source_digest": {"oneOf": [_DIGEST, {"type": "null"}]},
        "data": {
            "type": "object",
            "maxProperties": 64,
            "additionalProperties": True,
        },
        "degraded": {
            "type": "array",
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 256},
        },
    },
    "required": ["status", "schema", "project_ref", "data", "degraded"],
    "additionalProperties": False,
}


TOOL_DESCRIPTIONS = {
    "resolve_context": (
        "Resolve bounded current Mastermind context for one authorized project/task. "
        "Read-only navigation; does not grant source or runtime authority."
    ),
    "expand_context": (
        "Expand one exact context reference into a bounded source-attributed slice."
    ),
    "diff_context": (
        "Compare a prior context reference with current exact selected dependencies "
        "and return material invalidators only."
    ),
    "atlas_search": (
        "Search the derived Project Atlas. Exact structural matches remain distinct "
        "from any future semantic ranking."
    ),
    "workspace_overlay": (
        "Read the derived overlay for one exact existing managed workspace operation. "
        "Does not grant workspace custody or write permission."
    ),
}
