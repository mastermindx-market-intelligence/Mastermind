"""The only HC0 module that imports MCP and HTTP transport libraries."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any

import mcp.types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from integrations.mastermind_surface_probe.probe import SurfaceContextProbe
from integrations.mastermind_surface_probe.schemas import (
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_NAME,
    TOOL_SPEC,
    ProbeError,
    canonical_json,
)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def build_tools() -> list[mcp_types.Tool]:
    """Build the exact one-tool HC0 advertisement."""

    return [
        mcp_types.Tool(
            name=TOOL_SPEC.name,
            title=TOOL_SPEC.title,
            description=TOOL_SPEC.description,
            inputSchema=TOOL_SPEC.input_schema,
            outputSchema=TOOL_SPEC.output_schema,
            annotations=mcp_types.ToolAnnotations(**TOOL_SPEC.annotations),
            _meta=TOOL_SPEC.meta,
        )
    ]


def request_meta_mapping(meta: Any) -> dict[str, Any]:
    """Project request metadata without accepting model-visible identity fields.

    The MCP progress token and task metadata are transport mechanics, not host
    correlation evidence. Unknown ``openai/*`` keys are preserved only long
    enough for the pure core to report one opaque degradation; their names and
    values are never returned.
    """

    if meta is None:
        return {}
    if isinstance(meta, Mapping):
        raw = dict(meta)
    else:
        model_dump = getattr(meta, "model_dump", None)
        if not callable(model_dump):
            raise ProbeError(
                "HOST_CONTEXT_REFUSED",
                "host context metadata was refused",
            )
        try:
            raw = dict(model_dump(by_alias=True, exclude_none=True))
        except Exception:
            raise ProbeError(
                "HOST_CONTEXT_REFUSED",
                "host context metadata was refused",
            ) from None
    return {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and key.startswith("openai/")
    }


def _tool_result(envelope: dict[str, Any], *, is_error: bool = False):
    text = canonical_json(envelope).decode("utf-8")
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        structuredContent=envelope,
        isError=is_error,
    )


def _error_envelope(code: str) -> dict[str, Any]:
    return {
        "schema": "mastermind.host_context_probe_error.v1",
        "server_identity": "mastermind-surface-probe-mcp",
        "server_version": SERVER_VERSION,
        "ok": False,
        "error": {
            "code": code,
            "message": code,
        },
    }


def build_mcp_server(probe: SurfaceContextProbe) -> Server:
    """Register only list-tools and call-tool handlers over one pure probe."""

    if not isinstance(probe, SurfaceContextProbe):
        raise TypeError("probe must be a SurfaceContextProbe")
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    tools = build_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None):
        if name != TOOL_NAME:
            return _tool_result(_error_envelope("INVALID_REQUEST"), is_error=True)
        try:
            meta = server.request_context.meta
            envelope = probe.inspect(
                arguments or {},
                request_meta=request_meta_mapping(meta),
            )
        except ProbeError as exc:
            return _tool_result(_error_envelope(exc.code), is_error=True)
        except Exception:
            return _tool_result(_error_envelope("INTERNAL_ERROR"), is_error=True)
        return _tool_result(envelope)

    return server


def initialization_options(server: Server) -> InitializationOptions:
    """Build an initialization advertisement from the registered handlers only."""

    return server.create_initialization_options(
        notification_options=NotificationOptions(),
        experimental_capabilities={},
    )


class _StreamableHTTPApp:
    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._manager.handle_request(scope, receive, send)


def build_streamable_http_app(
    server: Server,
    *,
    host: str = "127.0.0.1",
    path: str = "/mcp",
) -> Starlette:
    """Build a production-inert, stateless, JSON streamable-HTTP ASGI app.

    HC0 deliberately binds loopback only. Secure MCP Tunnel or another approved
    private transport remains a separately configured outer transport and does
    not grant application authority.
    """

    normalized_host = str(host or "").strip()
    if normalized_host not in _LOOPBACK_HOSTS:
        raise ValueError("surface probe requires a loopback host")
    normalized_path = str(path or "").strip()
    if (
        not normalized_path.startswith("/")
        or normalized_path == "/"
        or normalized_path.endswith("/")
        or "?" in normalized_path
        or "#" in normalized_path
    ):
        raise ValueError("surface probe MCP path is invalid")

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*",
            "localhost:*",
            "[::1]:*",
        ],
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
        ],
    )
    manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        retry_interval=None,
        json_response=True,
        stateless=True,
        security_settings=security,
    )
    endpoint = _StreamableHTTPApp(manager)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with manager.run():
            yield

    app = Starlette(
        routes=[Route(normalized_path, endpoint=endpoint)],
        lifespan=lifespan,
    )
    app.state.mastermind_surface_probe = {
        "host": normalized_host,
        "path": normalized_path,
        "stateless": True,
        "json_response": True,
    }
    return app


__all__ = [
    "build_mcp_server",
    "build_streamable_http_app",
    "build_tools",
    "initialization_options",
    "request_meta_mapping",
]
