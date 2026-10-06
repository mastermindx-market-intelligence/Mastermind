"""Closed model-facing catalog for the separate Mastermind Browser service."""
from __future__ import annotations

import copy
import hashlib
import json

SERVER_NAME = "mastermind-browser"
SERVER_VERSION = "0.1.0"
CATALOG_GENERATION = "mastermind.browser.mcp.v1"


def _object(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else list(required),
        "additionalProperties": False,
    }


def _text(maximum=16384):
    return {"type": "string", "minLength": 1, "maxLength": maximum}


_ACTIONS = [
    _object({"action": {"const": "click"}, "args": _object({"element_ref": _text(128)})}),
    _object({
        "action": {"const": "type"},
        "args": _object({"element_ref": _text(128), "text": {"type": "string", "maxLength": 16384}}),
    }),
    _object({
        "action": {"const": "scroll"},
        "args": _object({
            "delta_x": {"type": "integer", "minimum": -2000, "maximum": 2000},
            "delta_y": {"type": "integer", "minimum": -2000, "maximum": 2000},
        }),
    }),
    _object({
        "action": {"const": "navigate"},
        "args": _object({"url": {"type": "string", "maxLength": 2048, "pattern": "^https?://"}}),
    }),
]
_PREPARE = {
    "type": "object",
    "properties": {
        "tab_ref": _text(),
        "operation_key": _text(128),
        "action": {"enum": ["click", "type", "scroll", "navigate"]},
        "args": {"type": "object"},
    },
    "required": ["tab_ref", "operation_key", "action", "args"],
    "additionalProperties": False,
    "oneOf": [],
}
for branch in _ACTIONS:
    selected = copy.deepcopy(branch)
    selected["properties"].update({"tab_ref": _text(), "operation_key": _text(128)})
    selected["required"] += ["tab_ref", "operation_key"]
    _PREPARE["oneOf"].append(selected)


def _tool(name, description, schema, *, read_only):
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": not read_only,
            "idempotentHint": read_only,
            "openWorldHint": True,
        },
    }


_TOOLS = [
    _tool(
        "browser_fleet",
        "Read browser capacity already permitted by the existing owner; never allocates a host.",
        _object({"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, []),
        read_only=True,
    ),
    _tool(
        "browser_tabs",
        "Read only tabs authorized by the existing owner for an opaque browser reference.",
        _object({"browser_ref": _text()}),
        read_only=True,
    ),
    _tool(
        "browser_snapshot",
        "Read a bounded accessibility observation for an exact authorized tab.",
        _object({"tab_ref": _text()}),
        read_only=True,
    ),
    _tool(
        "browser_screenshot",
        "Read a bounded viewport image for an exact authorized tab.",
        _object({"tab_ref": _text()}),
        read_only=True,
    ),
    _tool(
        "prepare_browser_action",
        "Prepare one closed action through the existing owner; does not execute it.",
        _PREPARE,
        read_only=True,
    ),
    _tool(
        "run_browser_action",
        "Commit one prepared action through its original owner. Unknown effects are never retried.",
        _object({"action_ref": _text()}),
        read_only=False,
    ),
    _tool(
        "reconcile_browser_action",
        "Read the original action outcome from its owner; never re-dispatches it.",
        _object({"action_ref": _text()}),
        read_only=True,
    ),
]

SCHEMA_DIGEST = hashlib.sha256(
    json.dumps(_TOOLS, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
).hexdigest()


def catalog():
    return copy.deepcopy(_TOOLS)
