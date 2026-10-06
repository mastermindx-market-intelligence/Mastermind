"""MCP transports over one injected Browser owner facade.

This module starts no listener, tunnel, browser, grant, provider session, or Auth0
flow. HTTP authentication is supplied by the existing resource owner. Private
stdio must be supplied by an already-admitted supervisor.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
import inspect
import json
from typing import Any, Callable

from .catalog import SERVER_NAME, SERVER_VERSION
from .facade import BrowserFacade
from .ingress import INTERNAL_PATH

MAX_REQUEST_BYTES = 98_304


def create_mcp_server(facade: BrowserFacade):
    if not isinstance(facade, BrowserFacade):
        raise TypeError("owner-bound BrowserFacade is required")

    from mcp.server import Server
    from mcp.types import CallToolResult, TextContent, Tool

    server = Server(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def list_tools():
        return [Tool(**row) for row in facade.catalog()]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict):
        result = await facade.call(name, arguments)
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        result,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            ],
            structuredContent=result,
            isError=result["is_error"],
        )

    return server


async def serve_stdio(facade: BrowserFacade) -> None:
    """Serve only an already-owned private stdin/stdout pair."""
    from mcp.server.stdio import stdio_server

    server = create_mcp_server(facade)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def create_http_app(
    *,
    owner: Any,
    authenticate: Callable,
    auth_challenge: str,
    allowed_hosts: list[str],
    allowed_origins: tuple[str, ...] = (),
):
    """Return an unstarted Browser ASGI app using injected owner authentication."""
    if not callable(authenticate):
        raise TypeError("existing HTTP authentication is required")
    if (
        type(auth_challenge) is not str
        or not auth_challenge.startswith("Bearer")
        or len(auth_challenge) > 2048
        or any(ord(ch) < 32 for ch in auth_challenge)
    ):
        raise TypeError("valid owner-authored challenge required")
    if (
        not isinstance(allowed_hosts, (list, tuple))
        or not allowed_hosts
        or any(
            type(host) is not str
            or not host
            or "*" in host
            or any(ch.isspace() for ch in host)
            for host in allowed_hosts
        )
    ):
        raise TypeError("exact allowed hosts required")
    if any(
        type(origin) is not str
        or not origin.startswith("https://")
        or "*" in origin
        for origin in allowed_origins
    ):
        raise TypeError("exact HTTPS allowed origins required")

    caller = ContextVar("mastermind_browser_authenticated_caller", default=None)
    facade = BrowserFacade(owner=owner, caller_resolver=caller.get)

    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Route

    manager = StreamableHTTPSessionManager(
        app=create_mcp_server(facade),
        stateless=True,
        json_response=True,
        max_request_body_size=MAX_REQUEST_BYTES,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(allowed_hosts),
            allowed_origins=list(allowed_origins),
        ),
    )

    class Endpoint:
        async def __call__(self, scope, receive, send):
            request = Request(scope, receive)
            try:
                verified = authenticate(request)
                if inspect.isawaitable(verified):
                    verified = await verified
            except Exception:
                verified = None
            if verified is None:
                await Response(
                    status_code=401,
                    headers={"WWW-Authenticate": auth_challenge},
                )(scope, receive, send)
                return
            token = caller.set(verified)
            try:
                await manager.handle_request(scope, receive, send)
            finally:
                caller.reset(token)

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    return Starlette(
        routes=[Route(INTERNAL_PATH, Endpoint(), methods=["POST", "GET", "DELETE"])],
        lifespan=lifespan,
    )
