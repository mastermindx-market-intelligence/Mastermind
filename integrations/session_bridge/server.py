"""Session Bridge MCP presentation boundary.

The standalone unauthenticated FastMCP edge is deliberately disabled. Session
Bridge tools may be exposed only through the existing authenticated Executive
MCP host, which supplies a verified principal and trusted target projection.
"""
from __future__ import annotations

from typing import Any

from .gateway import SessionBridgeGateway


def build_mcp_server(_gateway: SessionBridgeGateway) -> Any:
    raise RuntimeError(
        "standalone Session Bridge MCP is disabled; use the authenticated Executive MCP host"
    )


__all__ = ["build_mcp_server"]
