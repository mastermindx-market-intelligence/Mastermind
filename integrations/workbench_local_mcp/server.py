"""MCP SDK edge for the local Workbench tunnel profile.

The official Secure MCP Tunnel launches this server over stdio. This module is
the only package module that imports the MCP SDK; authority and project access
remain in the adapter and existing Workbench observer.
"""
from __future__ import annotations

import json
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from .adapter import LocalWorkbenchGateway
from .schemas import SERVER_NAME, SERVER_VERSION, TOOL_SPECS


def build_tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in TOOL_SPECS
    ]


def build_server(gateway: LocalWorkbenchGateway) -> Server:
    if not isinstance(gateway, LocalWorkbenchGateway):
        raise TypeError("gateway must be LocalWorkbenchGateway")
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        payload = gateway.call(name, arguments or {})
        return [
            mcp_types.TextContent(
                type="text",
                text=json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            )
        ]

    return server


def initialization_options(server: Server) -> InitializationOptions:
    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


async def run_stdio(gateway: LocalWorkbenchGateway) -> None:
    server = build_server(gateway)
    options = initialization_options(server)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
    finally:
        gateway.close()
