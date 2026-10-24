"""Attested internal tools for the exact-tab Browser Link backend.

These tools are the Workbench owner-to-actuator seam. They are not the public
agent catalog and confer no resource/profile authority.
"""
from __future__ import annotations

import copy
from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest

INVENTORY_TOOL = "browser_link_inventory"
READ_TOOL = "browser_link_read"
ACTION_TOOL = "browser_link_action"
LINK_TOOLS = frozenset({INVENTORY_TOOL, READ_TOOL, ACTION_TOOL})
LINK_READ_TOOLS = frozenset({INVENTORY_TOOL, READ_TOOL})
OWNER_CONNECTION_SCHEMA = "mastermind.browser_link.owner_connection.v1"
OWNER_INVENTORY_SCHEMA = "mastermind.browser_link.owner_inventory.v2"
OWNER_RESULT_SCHEMA = "mastermind.browser_link.owner_result.v1"


def _object(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


_REF = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", "maxLength": 128}
_INT = {"type": "integer", "minimum": 0, "maximum": 2**53 - 1}
_TARGET = _object({"connection_generation": _REF, "tab_id": _INT,
                   "consent_id": _REF, "document_revision": _INT})
_COMMON = {"target": _TARGET, "expires_at_ms": _INT}
_READ = _object({**_COMMON, "command": {"enum": ["snapshot", "screenshot"]}, "args": _object({})})
_ACTION = _object({**_COMMON, "command": {"enum": ["click", "type", "scroll", "navigate", "create_tab", "create_window"]},
                   "args": {"type": "object"}})
_ACTION["oneOf"] = [
    {"properties": {"command": {"const": "click"}, "args": _object({"element_ref": _REF})}},
    {"properties": {"command": {"const": "type"}, "args": _object({
        "element_ref": _REF, "text": {"type": "string", "maxLength": 16384}})}},
    {"properties": {"command": {"const": "scroll"}, "args": _object({
        "delta_x": {"type": "integer", "minimum": -2000, "maximum": 2000},
        "delta_y": {"type": "integer", "minimum": -2000, "maximum": 2000}})}},
    *[{"properties": {"command": {"const": command}, "args": _object({
        "url": {"type": "string", "maxLength": 2048, "pattern": "^https?://"}})}}
      for command in ("navigate", "create_tab", "create_window")],
]


def _tool(name, schema, read):
    return {"name": name, "inputSchema": schema, "annotations": {
        "readOnlyHint": read, "destructiveHint": not read,
        "idempotentHint": read, "openWorldHint": True}}


_ROWS = [
    _tool(INVENTORY_TOOL, _object({}), True),
    _tool(READ_TOOL, _READ, True),
    _tool(ACTION_TOOL, _ACTION, False),
]
LINK_TOOL_SCHEMA_DIGEST = observed_mcp_tool_schema_digest(
    {"tools": {row["name"]: row for row in _ROWS}}
)


def tool_catalog():
    return {"tools": copy.deepcopy(_ROWS)}


def backend_tool_policy(schema_digest: str):
    """Select an explicit Link policy without widening the legacy attestation."""
    if schema_digest == LINK_TOOL_SCHEMA_DIGEST:
        return LINK_TOOLS, LINK_READ_TOOLS
    from control_plane.browser_resource_contract import ALLOWED_BROWSER_TOOLS, READ_ONLY_BROWSER_TOOLS
    return ALLOWED_BROWSER_TOOLS, READ_ONLY_BROWSER_TOOLS
