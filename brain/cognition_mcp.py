"""Read-only Mastermind cognition plane for the live Advisor chat.

The data contracts and packet builders remain owned by ``brain.portfolio_intelligence`` and
are exposed through the already-reviewed tool objects in ``brain.autonomous_mcp``.  This module
only gives the conversational Advisor a separate MCP namespace containing those READ tools.
It deliberately excludes the standalone raw-book reader, context-upgrade writes, and
``submit_book``. ``get_market_packet`` may carry the incumbent bounded active-book summary, but
connecting more evidence cannot grant queue, sizing, rebalance, or execution authority.
"""
from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server

from brain import autonomous_mcp

SERVER_NAME = "cognition"

# Named aliases make the shared owner explicit and keep handler-level verification available.
# These are the SAME decorated tool objects, not wrappers or second implementations.
get_market_packet = autonomous_mcp.get_market_packet
get_prophet_board = autonomous_mcp.get_prophet_board
get_sector_rotation = autonomous_mcp.get_sector_rotation
get_technical_lab = autonomous_mcp.get_technical_lab
get_context_catalog = autonomous_mcp.get_context_catalog
get_surface_packet = autonomous_mcp.get_surface_packet
get_neural_web_packet = autonomous_mcp.get_neural_web_packet

# Reuse the exact incumbent handlers/schemas. Do not fork their artifact allowlists, freshness
# rules, packet budgets, or Neural Web authority fences into a second implementation.
_READ_TOOLS = [
    get_market_packet,
    get_prophet_board,
    get_sector_rotation,
    get_technical_lab,
    get_context_catalog,
    get_surface_packet,
    get_neural_web_packet,
]

TOOL_NAMES = [f"mcp__{SERVER_NAME}__{tool.name}" for tool in _READ_TOOLS]


def build_server():
    """Build the Advisor's typed, read-only cross-data-plane MCP server."""
    return create_sdk_mcp_server(
        name=SERVER_NAME,
        version="0.1.0",
        tools=_READ_TOOLS,
    )


def allowed_tools() -> list[str]:
    """Return only typed cognition reads; no raw filesystem or mutation tools."""
    return list(TOOL_NAMES)
