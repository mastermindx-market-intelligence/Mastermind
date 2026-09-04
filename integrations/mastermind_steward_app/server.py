"""MCP projection for the authenticated Mastermind Steward app.

This module is the only Steward-app module that imports the MCP SDK. It exposes
exactly the protected six Secretary tools plus one optional self-contained UI
resource. All organizational reads remain in the injected ``StewardReadPort``;
this module creates no source reader, state store, retry loop, or write path.
"""
from __future__ import annotations

import json
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from integrations.business_mcp_auth.metadata import oauth_security_schemes
from integrations.mastermind_secretary_mcp.adapter import (
    SecretaryGroundingGateway,
    StewardReadPort,
)
from integrations.mastermind_secretary_mcp.server import (
    SecretaryGroundingContractServer,
    build_tools as build_contract_tools,
)
from integrations.mastermind_steward_app.ui import (
    CONTROL_ROOM_HTML,
    UI_MIME_TYPE,
    UI_RESOURCE_URI,
)

SERVER_NAME = "mastermind-steward"
SERVER_VERSION = "2.0.0"
REQUIRED_SCOPE = "mastermind.steward.read"
UI_TOOLS = frozenset({"list_responsibilities"})

__all__ = [
    "REQUIRED_SCOPE",
    "SERVER_NAME",
    "SERVER_VERSION",
    "build_contract_server",
    "build_mcp_server",
    "build_tools",
    "initialization_options",
    "run_stdio",
]


def build_contract_server(port: StewardReadPort) -> SecretaryGroundingContractServer:
    return SecretaryGroundingContractServer(SecretaryGroundingGateway(port))


def _tool_meta(name: str) -> dict[str, object]:
    meta: dict[str, object] = {
        "securitySchemes": oauth_security_schemes((REQUIRED_SCOPE,)),
        "openai/toolInvocation/invoking": "Reading Mastermind company state…",
        "openai/toolInvocation/invoked": "Mastermind company state loaded",
        "openai/widgetAccessible": False,
    }
    if name in UI_TOOLS:
        meta["ui"] = {"resourceUri": UI_RESOURCE_URI}
        meta["openai/outputTemplate"] = UI_RESOURCE_URI
    return meta


def build_tools() -> list[mcp_types.Tool]:
    """Build the immutable six-tool advertisement from the protected contract."""

    security = oauth_security_schemes((REQUIRED_SCOPE,))
    tools: list[mcp_types.Tool] = []
    for row in build_contract_tools():
        tools.append(
            mcp_types.Tool(
                name=row["name"],
                description=row["description"],
                inputSchema=row["inputSchema"],
                outputSchema=row["outputSchema"],
                annotations=mcp_types.ToolAnnotations(**row["annotations"]),
                securitySchemes=security,
                _meta=_tool_meta(row["name"]),
            )
        )
    return tools


def _ui_meta() -> dict[str, object]:
    return {
        "ui": {
            "prefersBorder": False,
            "csp": {
                "connectDomains": [],
                "resourceDomains": [],
            },
        },
        "openai/widgetDescription": (
            "Read-only Mastermind responsibility, attention, runtime, blocker, "
            "and surface facts."
        ),
    }


def build_mcp_server(
    contract: SecretaryGroundingContractServer,
) -> Server:
    if not isinstance(contract, SecretaryGroundingContractServer):
        raise TypeError("contract must be SecretaryGroundingContractServer")

    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> dict[str, Any]:
        # The protected contract performs closed input validation and exactly one
        # injected read-port call. Returning the mapping gives MCP both
        # structuredContent and a JSON text fallback.
        return await contract.call_tool(name, arguments or {})

    @server.list_resources()
    async def list_resources() -> list[mcp_types.Resource]:
        return [
            mcp_types.Resource(
                uri=UI_RESOURCE_URI,
                name="mastermind-steward-control-room",
                title="Mastermind Control Room",
                description=(
                    "Self-contained read-only visualization for Mastermind "
                    "responsibility, attention, runtime, blocker, and surface facts."
                ),
                mimeType=UI_MIME_TYPE,
                _meta=_ui_meta(),
            )
        ]

    @server.read_resource()
    async def read_resource(uri: Any) -> list[ReadResourceContents]:
        if str(uri) != UI_RESOURCE_URI:
            raise ValueError("resource not found")
        return [
            ReadResourceContents(
                content=CONTROL_ROOM_HTML,
                mime_type=UI_MIME_TYPE,
                meta=_ui_meta(),
            )
        ]

    return server


def initialization_options(server: Server) -> InitializationOptions:
    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


async def run_stdio(contract: SecretaryGroundingContractServer) -> None:
    """Run the read-only app over stdio for isolated local development only."""

    server = build_mcp_server(contract)
    options = initialization_options(server)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


def describe() -> str:
    return (
        json.dumps(
            {
                "server_name": SERVER_NAME,
                "server_version": SERVER_VERSION,
                "required_scope": REQUIRED_SCOPE,
                "tools": [tool.name for tool in build_tools()],
                "ui_resource": UI_RESOURCE_URI,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
