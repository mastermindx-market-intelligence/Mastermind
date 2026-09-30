"""MCP presentation for the stateless Mastermind Session Bridge.

This module is the optional MCP SDK edge only. The bridge owns no session
registry, lifecycle, dialogue, placement, retry, queue, or provider state.
"""
from __future__ import annotations

from typing import Any

from .gateway import SessionBridgeGateway


def build_mcp_server(gateway: SessionBridgeGateway) -> Any:
    # Keep the core package importable in control-plane/runtime environments
    # that intentionally do not install the optional MCP SDK.
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        "mastermind-session-bridge",
        instructions=(
            "Use exact current session targets only. session_send writes one "
            "governed Agent Dialogue CONTINUE before exact native attention; "
            "it is not a raw provider prompt injector. session_summon requests "
            "existing Executive admission and Capacity placement."
        ),
    )

    @server.tool()
    async def session_targets(kind: str | None = None) -> dict[str, Any]:
        """List exact addressable targets from canonical current projections."""
        return await gateway.call(
            "session_targets", {} if kind is None else {"kind": kind}
        )

    @server.tool()
    async def session_send(
        target_ref: str,
        instruction: str,
        stop_condition: str,
        operation_key: str,
    ) -> dict[str, Any]:
        """Reply on the canonical carrier, then wake only the exact bound runtime."""
        return await gateway.call(
            "session_send",
            {
                "target_ref": target_ref,
                "instruction": instruction,
                "stop_condition": stop_condition,
                "operation_key": operation_key,
            },
        )

    @server.tool()
    async def session_summon(
        objective: str,
        execution_profile: str,
        operation_key: str,
    ) -> dict[str, Any]:
        """Request admission; provider/host selection remains with Capacity."""
        return await gateway.call(
            "session_summon",
            {
                "objective": objective,
                "execution_profile": execution_profile,
                "operation_key": operation_key,
            },
        )

    return server


__all__ = ["build_mcp_server"]
