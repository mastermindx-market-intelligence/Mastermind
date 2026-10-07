"""Tools-only MCP facade for bounded Workspace Agent candidate return.

This is the only Workspace-return module that imports the MCP SDK. It opens no
listener, installs no app, owns no OAuth client, and registers no resources,
prompts, sampling, roots, elicitation, dynamic tools, or lifecycle operations.
"""
from __future__ import annotations

from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from integrations.workspace_agent_return import (
    SERVER_NAME,
    SERVER_VERSION,
    WorkspaceCandidateReturnGateway,
    canonical_return_json,
    tool_spec,
)


def build_tools() -> list[mcp_types.Tool]:
    """Build exactly one immutable model-visible tool."""

    spec = tool_spec()
    return [
        mcp_types.Tool(
            name=spec["name"],
            description=spec["description"],
            inputSchema=spec["input_schema"],
            annotations=mcp_types.ToolAnnotations(**spec["annotations"]),
        )
    ]


def build_mcp_server(gateway: WorkspaceCandidateReturnGateway) -> Server:
    """Register only tools/list and tools/call over the injected gateway."""

    if not isinstance(gateway, WorkspaceCandidateReturnGateway):
        raise TypeError("gateway must be WorkspaceCandidateReturnGateway")
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = tuple(build_tools())

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        envelope = await gateway.call_tool(name, arguments or {})
        return [
            mcp_types.TextContent(
                type="text",
                text=canonical_return_json(envelope).decode("ascii"),
            )
        ]

    return server


def initialization_options(server: Server) -> InitializationOptions:
    """Build tools-only MCP initialization options."""

    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


__all__ = [
    "build_mcp_server",
    "build_tools",
    "initialization_options",
]
