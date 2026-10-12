"""Loopback-mountable Product MCP ASGI composition over an existing owner.

The external approved process owner keeps listener, TLS/tunnel, admitted user
sessions, source-port capacity, audit durability and graceful shutdown. No
socket, process, filesystem path, credential, token issuer, scheduler, grant
state or browser worker is acquired by this module.

Liveness and readiness are intentionally distinct. The host MUST supply a
real current readiness check; an SDK constructor or Git merge is not readiness.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route


def create_product_asgi_app(
    *, server: FastMCP, owner_ready: Callable[[], bool],
) -> Starlette:
    """Mount the existing SDK server, without launching or arming a service.

    Production owner supplies all dependencies including a qualified,
    nonblocking *synchronous* readiness probe. A failing probe yields 503 and
    does not leak exception, resource ID or authentication details.
    """
    if not isinstance(server, FastMCP) or not callable(owner_ready):
        raise ValueError("MCP server and owner readiness required")
    app = server.streamable_http_app()

    def ready_now() -> bool:
        try:
            return owner_ready() is True
        except Exception:
            return False

    class ReadinessGate:
        """Admit MCP requests only while the borrowed host is ready.

        This is NOT user authorization. The authenticated Product handler
        separately verifies current OAuth and product-user grants.
        """
        async def __call__(self, scope, receive, send):
            if scope.get("type") in ("http", "websocket") and not ready_now():
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                await PlainTextResponse("NOT_READY\n", status_code=503)(
                    scope, receive, send)
                return
            await app(scope, receive, send)

    async def healthz(_request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK\n", status_code=200)

    async def readyz(_request: Request) -> PlainTextResponse:
        ready = ready_now()
        return PlainTextResponse(
            "READY\n" if ready else "NOT_READY\n",
            status_code=200 if ready else 503,
        )

    @asynccontextmanager
    async def lifespan(_host_app: Starlette):
        # One borrowed SDK transport-session owner; no child app auto-start
        # assumption, no app state registry and no cleanup of foreign assets.
        async with server.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
            Mount("/", app=ReadinessGate()),
        ],
        lifespan=lifespan,
    )
