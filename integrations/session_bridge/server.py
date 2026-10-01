"""Authenticated-host MCP presentation for the stateless Session Bridge.

The Session Bridge must be composed into an existing authenticated Executive
MCP host. A standalone network listener is deliberately refused because send
and summon are modifying tools and the bridge owns no independent auth plane.
"""
from __future__ import annotations

from typing import Any

from .gateway import SessionBridgeGateway


def build_tools() -> list[Any]:
    """Return the three static MCP tool definitions for host composition."""
    import mcp.types as mcp_types

    common = mcp_types.ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )
    read_only = mcp_types.ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )
    return [
        mcp_types.Tool(
            name="session_targets",
            description="List exact addressable Fabric/Codex/Claude targets from canonical current projections.",
            inputSchema={
                "type": "object",
                "properties": {"kind": {"type": "string", "enum": ["fabric_attempt", "codex", "claude"]}},
                "additionalProperties": False,
            },
            annotations=read_only,
        ),
        mcp_types.Tool(
            name="session_send",
            description="Commit one governed continuation to one exact current target, then request native attention.",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_ref": {"type": "string", "minLength": 1, "maxLength": 256},
                    "instruction": {"type": "string", "minLength": 1, "maxLength": 700},
                    "stop_condition": {"type": "string", "minLength": 1, "maxLength": 700},
                    "operation_key": {"type": "string", "minLength": 1, "maxLength": 96},
                },
                "required": ["target_ref", "instruction", "stop_condition", "operation_key"],
                "additionalProperties": False,
            },
            annotations=common,
        ),
        mcp_types.Tool(
            name="session_summon",
            description="Request one admitted worker/session through canonical Executive admission and Capacity placement.",
            inputSchema={
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "execution_profile": {"type": "string", "enum": ["bounded_code_change", "research_only"]},
                    "operation_key": {"type": "string", "minLength": 1, "maxLength": 96},
                },
                "required": ["objective", "execution_profile", "operation_key"],
                "additionalProperties": False,
            },
            annotations=common,
        ),
    ]


def build_handlers(gateway: SessionBridgeGateway) -> dict[str, Any]:
    """Return exact tool handlers for an already-authenticated host."""
    if not isinstance(gateway, SessionBridgeGateway):
        raise TypeError("SessionBridgeGateway required")
    return {
        name: (lambda arguments, _name=name: gateway.call(_name, arguments))
        for name in ("session_targets", "session_send", "session_summon")
    }


def build_mcp_server(_gateway: SessionBridgeGateway) -> Any:
    """Standalone unauthenticated Session Bridge networking is forbidden."""
    raise RuntimeError(
        "standalone Session Bridge MCP is refused; compose build_tools/build_handlers into the authenticated Executive MCP host"
    )


__all__ = ["build_handlers", "build_mcp_server", "build_tools"]
