"""integrations.executive_mcp.server — the ONLY module that imports the MCP SDK.

Commission R5: the network-facing dependency stack is isolated from the sealed
Executive runtime.  ``control_plane`` never imports this package,
:mod:`integrations.executive_mcp.schemas` and
:mod:`integrations.executive_mcp.adapter` never import ``mcp``, and an AST gate
in ``tests/test_executive_mcp.py`` keeps all three true.  Importing this module
without the SDK installed raises ``ImportError`` — deliberately, and only here.

Commission R13: the capability surface is tools-only.  No resources, no prompts,
no sampling callback, no roots, no dynamic registration.  The tool list is the
static :data:`~integrations.executive_mcp.schemas.TOOL_SPECS` table and is built
once; there is no code path anywhere in this package that adds, removes, or
rewrites a tool at runtime.
"""
from __future__ import annotations

import json
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig
from integrations.executive_mcp.schemas import (
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_SPECS,
    canonical_json,
)

__all__ = ["build_mcp_server", "build_tools", "run_stdio"]


def build_tools() -> list[mcp_types.Tool]:
    """The static five-tool advertisement, built from the reviewed table.

    Read-only annotations are declared here because the SDK's scan surface is
    where a client looks for them.  They are UX metadata: server-side
    enforcement in the adapter stays authoritative if a client ignores them.
    """

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in TOOL_SPECS
    ]


def build_mcp_server(gateway: ExecutiveMcpGateway) -> Server:
    """Wire the five tools onto one low-level MCP server.

    The low-level server is used rather than a higher-level convenience wrapper
    precisely because the surface must stay auditable: exactly two request
    handlers are registered (``tools/list`` and ``tools/call``), and the
    advertised capabilities therefore carry ``tools`` and nothing else.
    """

    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        # Returns the SAME static list on every scan.  Nothing recomputes it
        # from runtime state, and no returned Executive OS text is ever spliced
        # into a description (R7 — tool-poisoning boundary).
        return list(tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        envelope = await gateway.call(name, arguments or {})
        # One tool call does one thing.  There is no branch here that reads the
        # result and calls another tool (§14).
        return [
            mcp_types.TextContent(
                type="text",
                text=json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2),
            )
        ]

    return server


def initialization_options(server: Server) -> InitializationOptions:
    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


async def run_stdio(gateway: ExecutiveMcpGateway) -> None:
    """Serve over stdio, the transport the Secure MCP Tunnel path terminates on.

    No TCP/HTTP listener is created here.  If an HTTP transport is ever wired,
    :func:`~integrations.executive_mcp.schemas.loopback_bind_host` already
    refuses a non-loopback bind at config parse (R11), and
    ``GatewayConfig.__post_init__`` calls it unconditionally so the refusal
    cannot be skipped by simply not using HTTP.
    """

    server = build_mcp_server(gateway)
    options = initialization_options(server)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options)
    finally:
        await gateway.aclose()


def describe(config: GatewayConfig) -> str:
    """A one-shot, machine-readable description of the frozen surface."""

    return canonical_json(
        {
            "server_name": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "mode": config.mode.value,
            "tools": [tool.name for tool in build_tools()],
        }
    ).decode("utf-8")
