"""Tools-only MCP surface for the bounded Mastermind GitHub patch owner."""
from __future__ import annotations

from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from integrations.mastermind_github_app.adapter import GithubPatchGateway
from integrations.mastermind_github_app.prepared_token import canonical_json
from integrations.mastermind_github_app.schemas import (
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_SPECS,
)


def build_tools() -> list[mcp_types.Tool]:
    """Build the immutable exact three-tool advertisement."""

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=dict(spec.input_schema),
            annotations=mcp_types.ToolAnnotations(**dict(spec.annotations)),
        )
        for spec in TOOL_SPECS
    ]


def build_mcp_server(gateway: GithubPatchGateway) -> Server:
    """Register only list/call handlers over one injected bounded gateway."""

    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        envelope = await gateway.call(name, arguments or {})
        return [
            mcp_types.TextContent(
                type="text",
                text=canonical_json(envelope).decode("utf-8"),
            )
        ]

    return server


def initialization_options(server: Server) -> InitializationOptions:
    """Return tools-only initialization options with no dynamic capabilities."""

    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


__all__ = ["build_mcp_server", "build_tools", "initialization_options"]
