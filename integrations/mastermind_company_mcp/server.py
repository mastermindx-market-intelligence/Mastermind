"""The only company-dialogue module that imports the MCP SDK.

WP-2 advertises tools only. It has no launcher, listener, resource, prompt,
sampling, roots, elicitation, dynamic registration, or production binding.
"""
from __future__ import annotations

import json
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from integrations.mastermind_company_mcp.adapter import CompanyDialogueGateway
from integrations.mastermind_company_mcp.schemas import (
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_SPECS,
)


def build_tools() -> list[mcp_types.Tool]:
    """Build the static six-tool advertisement from the reviewed table."""

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in TOOL_SPECS
    ]


def build_mcp_server(gateway: CompanyDialogueGateway) -> Server:
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
                text=json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2),
            )
        ]

    return server


def initialization_options(server: Server) -> InitializationOptions:
    """Build tools-only MCP initialization options."""

    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


__all__ = ["build_mcp_server", "build_tools", "initialization_options"]
