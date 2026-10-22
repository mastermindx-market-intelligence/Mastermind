"""Closed model-facing catalog for the separate Mastermind Browser service."""
from __future__ import annotations

import copy
import hashlib
import json
from .tab_ref import MAX_TAB_REF_WIRE_BYTES, MAX_BROWSER_SESSION_REF_WIRE_BYTES, MAX_BROKER_ACTION_REF_WIRE_BYTES

SERVER_NAME = "mastermind-browser"
SERVER_VERSION = "0.3.0"
CATALOG_GENERATION = "mastermind.browser.mcp.v3"


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
    *[_object({
        "action": {"const": action},
        "args": _object({"url": {"type": "string", "maxLength": 2048, "pattern": "^https?://"}}),
    }) for action in ("navigate", "create_tab", "create_window")],
]
_PREPARE = {
    "type": "object",
    "properties": {
        "tab_ref": _text(MAX_TAB_REF_WIRE_BYTES),
        "action": {"enum": ["click", "type", "scroll", "navigate", "create_tab", "create_window"]},
        "args": {"type": "object"},
    },
    "required": ["tab_ref", "action", "args"],
    "additionalProperties": False,
    "oneOf": [],
}
for branch in _ACTIONS:
    selected = copy.deepcopy(branch)
    selected["properties"].update({"tab_ref": _text(MAX_TAB_REF_WIRE_BYTES)})
    selected["required"] += ["tab_ref"]
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
        "Read a live bounded page of permitted browsers. If truncated, pass next_after_browser_ref as after_browser_ref. observation_status describes this call only. Any restart_required page makes the entire walk incomplete: continue to reach healthy browsers, then restart from the first page to establish completeness. No atomic snapshot or host allocation.",
        _object({"limit": {"type": "integer", "minimum": 1, "maximum": 50},
                 "after_browser_ref": _text(MAX_BROWSER_SESSION_REF_WIRE_BYTES)}, []),
        read_only=True,
    ),
    _tool(
        "browser_tabs",
        "Read a bounded page of authorized tabs. If truncated, pass next_after_tab_id as after_tab_id with the same browser_ref.",
        _object({"browser_ref": _text(MAX_BROWSER_SESSION_REF_WIRE_BYTES), "after_tab_id": {"type": "integer", "minimum": 0, "maximum": 9007199254740991}}, ["browser_ref"]),
        read_only=True,
    ),
    _tool(
        "browser_snapshot",
        "Read a bounded accessibility observation for an exact authorized tab.",
        _object({"tab_ref": _text(MAX_TAB_REF_WIRE_BYTES)}),
        read_only=True,
    ),
    _tool(
        "browser_screenshot",
        "Read a bounded viewport image for an exact authorized tab.",
        _object({"tab_ref": _text(MAX_TAB_REF_WIRE_BYTES)}),
        read_only=True,
    ),
    _tool(
        "prepare_browser_action",
        "Prepare one action for an authorized tab. Creating a tab or window needs local creation permission; args contains one HTTP(S) URL. Does not execute it.",
        _PREPARE,
        read_only=True,
    ),
    _tool(
        "run_browser_action",
        "Commit one prepared action through its original owner. Unknown effects are never retried.",
        _object({"tab_ref": _text(MAX_TAB_REF_WIRE_BYTES), "action_ref": _text(MAX_BROKER_ACTION_REF_WIRE_BYTES)}),
        read_only=False,
    ),
    _tool(
        "reconcile_browser_action",
        "Read the original action outcome from its owner; never re-dispatches it.",
        _object({"tab_ref": _text(MAX_TAB_REF_WIRE_BYTES), "action_ref": _text(MAX_BROKER_ACTION_REF_WIRE_BYTES)}),
        read_only=True,
    ),
]

SCHEMA_DIGEST = hashlib.sha256(
    json.dumps(_TOOLS, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
).hexdigest()


def catalog():
    return copy.deepcopy(_TOOLS)
