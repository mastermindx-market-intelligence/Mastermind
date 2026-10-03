"""MCP app generation that layers search/fetch over protected Steward reads.

The installed Steward v2 builder remains unchanged and continues to advertise
exactly the protected six Secretary tools. This module is an explicit later app
generation: it reuses those six tools verbatim and adds only the two standard
read-only research tools from the research module.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from integrations.business_mcp_auth.contracts import ResourcePolicy
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import oauth_security_schemes
from integrations.mastermind_secretary_mcp.server import (
    SecretaryGroundingContractServer,
)
from integrations.mastermind_steward_app.app import build_authenticated_app
from integrations.mastermind_steward_app.research import (
    FETCH_TOOL,
    MAX_RESULT_BYTES,
    RESEARCH_SCHEMA_SNAPSHOT_SHA256,
    RESEARCH_SERVER_VERSION,
    RESEARCH_TOOL_SCHEMA_DIGEST,
    RESEARCH_TOOL_SPECS,
    SEARCH_TOOL,
    ResearchError,
    StewardResearchGateway,
    assert_research_contract_integrity,
)
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    SERVER_NAME,
    build_tools as build_secretary_tools,
)

_RESEARCH_TOOL_NAMES = frozenset({SEARCH_TOOL, FETCH_TOOL})


def _meta(name: str) -> dict[str, object]:
    if name == SEARCH_TOOL:
        invoking = "Searching Mastermind company evidence…"
        invoked = "Mastermind company evidence searched"
    else:
        invoking = "Fetching Mastermind company evidence…"
        invoked = "Mastermind company evidence loaded"
    return {
        "securitySchemes": oauth_security_schemes((REQUIRED_SCOPE,)),
        "openai/toolInvocation/invoking": invoking,
        "openai/toolInvocation/invoked": invoked,
        "openai/widgetAccessible": False,
    }


def build_research_tools() -> list[mcp_types.Tool]:
    """Return the six protected tools plus search/fetch for research generation."""

    assert_research_contract_integrity()
    tools = list(build_secretary_tools())
    security = oauth_security_schemes((REQUIRED_SCOPE,))
    for spec in RESEARCH_TOOL_SPECS:
        tools.append(
            mcp_types.Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
                outputSchema=spec.output_schema,
                annotations=mcp_types.ToolAnnotations(**spec.annotations),
                securitySchemes=security,
                _meta=_meta(spec.name),
            )
        )
    return tools


def _success(payload: dict[str, Any]) -> mcp_types.CallToolResult:
    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        encoded = text.encode("utf-8", errors="strict")
        if len(encoded) > MAX_RESULT_BYTES:
            raise ValueError
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return _error("RESPONSE_REFUSED")
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        structuredContent=payload,
        isError=False,
    )


def _error(code: str) -> mcp_types.CallToolResult:
    safe = code if code in ResearchError.CODES else "INTERNAL_ERROR"
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=safe)],
        isError=True,
    )


def build_research_mcp_server(
    contract: SecretaryGroundingContractServer,
) -> Server:
    """Build explicit Steward research generation without changing v2."""

    if not isinstance(contract, SecretaryGroundingContractServer):
        raise TypeError("contract must be SecretaryGroundingContractServer")
    assert_research_contract_integrity()
    research = StewardResearchGateway(contract)
    server: Server = Server(SERVER_NAME, version=RESEARCH_SERVER_VERSION)
    tools = tuple(build_research_tools())
    secretary_names = frozenset(
        tool.name for tool in tools if tool.name not in _RESEARCH_TOOL_NAMES
    )

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool(validate_input=False)
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> Any:
        if name in secretary_names:
            # Preserve the exact Secretary contract response path in this
            # generation; only the application tool census is larger.
            return await contract.call_tool(name, arguments or {})
        if name not in _RESEARCH_TOOL_NAMES:
            return _error("INVALID_REQUEST")
        try:
            payload = await research.call(name, arguments)
        except ResearchError as exc:
            return _error(exc.code)
        except Exception:
            return _error("INTERNAL_ERROR")
        return _success(payload)

    return server


def research_initialization_options(server: Server) -> InitializationOptions:
    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


async def run_research_stdio(contract: SecretaryGroundingContractServer) -> None:
    """Run the explicit research generation over stdio for local inspection."""

    server = build_research_mcp_server(contract)
    options = research_initialization_options(server)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


def build_authenticated_research_app(
    contract: SecretaryGroundingContractServer,
    *,
    policy: ResourcePolicy,
    token_verifier: MastermindTokenVerifier,
    allowed_origins: Sequence[str] = ("https://chatgpt.com",),
):
    """Build the new research app generation on the existing A1 auth stack."""

    return build_authenticated_app(
        contract,
        policy=policy,
        token_verifier=token_verifier,
        allowed_origins=allowed_origins,
        app_generation="research-v3",
    )


def describe_research() -> str:
    return (
        json.dumps(
            {
                "server_name": SERVER_NAME,
                "server_version": RESEARCH_SERVER_VERSION,
                "required_scope": REQUIRED_SCOPE,
                "tools": [tool.name for tool in build_research_tools()],
                "research_schema_sha256": RESEARCH_SCHEMA_SNAPSHOT_SHA256,
                "research_tool_schema_digest": RESEARCH_TOOL_SCHEMA_DIGEST,
                "citation_status": "CITATION_URL_SURFACE_MISSING",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


__all__ = [
    "build_authenticated_research_app",
    "build_research_mcp_server",
    "build_research_tools",
    "describe_research",
    "research_initialization_options",
    "run_research_stdio",
]
