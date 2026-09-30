"""MCP presentation for the stateless Mastermind Session Bridge.

The server is only a presentation adapter over SessionBridgeGateway. It owns no
session registry, lifecycle, placement, retry, queue, or provider state.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .gateway import SessionBridgeGateway


def build_mcp_server(gateway: SessionBridgeGateway) -> FastMCP:
    server = FastMCP(
        "mastermind-session-bridge",
        instructions=(
            "Use exact session targets only. session_send never selects a fallback. "
            "session_summon requests admission through existing Executive owners; "
            "accepted is not dispatched or started."
        ),
    )

    @server.tool()
    async def session_targets(kind: str | None = None) -> dict[str, Any]:
        """List addressable current targets from canonical Runtime/Agent projections."""
        return await gateway.call("session_targets", {} if kind is None else {"kind": kind})

    @server.tool()
    async def session_send(target_ref: str, message: str, operation_key: str) -> dict[str, Any]:
        """Send one bounded message to one exact already-bound session target."""
        return await gateway.call(
            "session_send",
            {
                "target_ref": target_ref,
                "message": message,
                "operation_key": operation_key,
            },
        )

    @server.tool()
    async def session_summon(
        objective: str,
        execution_profile: str,
        operation_key: str,
        preferred_surface: str | None = None,
    ) -> dict[str, Any]:
        """Request one new admitted session via existing Executive placement/lifecycle."""
        arguments: dict[str, Any] = {
            "objective": objective,
            "execution_profile": execution_profile,
            "operation_key": operation_key,
        }
        if preferred_surface is not None:
            arguments["preferred_surface"] = preferred_surface
        return await gateway.call("session_summon", arguments)

    return server


__all__ = ["build_mcp_server"]
