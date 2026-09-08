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
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
import mcp.types as mcp_types
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import protected_resource_metadata
from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig
from integrations.executive_mcp.e1_http import (
    MAX_RESPONSE_BYTES,
    BoundedRequestApp,
    E1_READ_PATHS,
    build_e1_app,
)
from integrations.executive_mcp.schemas import (
    ERROR_CODES,
    RESULT_SCHEMA,
    SERVER_NAME,
    SERVER_VERSION,
    GatewayError,
    ServerMode,
    TOOL_SPECS,
    canonical_json,
    error_envelope,
    validate_tool_arguments,
)

__all__ = ["build_e1_mcp_app", "build_e1_tools", "build_mcp_server", "build_tools", "run_stdio"]

_E1_READ_NAMES = tuple(path.rsplit("/", 1)[-1] for path in sorted(E1_READ_PATHS))
_E1_ENVELOPE_FIELDS = frozenset(
    {
        "schema", "tool", "ok", "server_version", "mode", "generated_at",
        "grounding", "data", "degraded", "bounded", "error",
    }
)


def _e1_generated_at(settings: Any) -> str:
    """Translate the integer auth clock to the result contract's UTC timestamp."""

    value = settings.clock()
    if type(value) is int:
        return (
            datetime.fromtimestamp(value, timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _e1_error(settings: Any, tool: str, code: str, message: str) -> dict[str, Any]:
    """Return the one canonical E1 failure envelope for the outer bridge."""

    return error_envelope(
        tool,
        mode=ServerMode.READONLY,
        generated_at=_e1_generated_at(settings),
        code=code,
        message=message,
    )


def _is_e1_envelope(payload: Any, tool: str) -> bool:
    """Recognize only the fixed read-profile result shape from the inner app."""

    if not isinstance(payload, dict) or set(payload) != _E1_ENVELOPE_FIELDS:
        return False
    try:
        canonical_json(payload)
    except (TypeError, ValueError):
        return False
    if (
        payload["schema"] != RESULT_SCHEMA
        or payload["tool"] != tool
        or type(payload["ok"]) is not bool
        or payload["server_version"] != SERVER_VERSION
        or payload["mode"] != ServerMode.READONLY.value
        or not isinstance(payload["generated_at"], str)
        or not isinstance(payload["grounding"], dict)
        or not isinstance(payload["degraded"], list)
        or not all(isinstance(item, str) for item in payload["degraded"])
        or not isinstance(payload["bounded"], list)
        or not all(isinstance(item, dict) for item in payload["bounded"])
    ):
        return False
    if payload["ok"]:
        return payload["error"] is None
    error = payload["error"]
    return (
        payload["data"] is None
        and isinstance(error, dict)
        and set(error).issubset({"code", "message", "intent_id"})
        and {"code", "message"}.issubset(error)
        and isinstance(error["code"], str)
        and error["code"] in ERROR_CODES
        and isinstance(error["message"], str)
        and ("intent_id" not in error or isinstance(error["intent_id"], str))
    )


class _DuplicateAuthorizationGuard:
    """Reject raw duplicate credentials before SDK header coalescing."""

    def __init__(self, app: Any, *, fenced_app: Any | None = None) -> None:
        self._app = app
        self._fenced_app = fenced_app or app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            values = [value for key, value in scope.get("headers", []) if key.lower() == b"authorization"]
            if len(values) > 1:
                response = JSONResponse(
                    {"ok": False, "error": {"code": "authority_refused", "message": "duplicate Authorization headers are refused"}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self._fenced_app(scope, receive, send)


def build_e1_tools() -> list[mcp_types.Tool]:
    """The temporary MCP profile is a literal four-reader subset."""

    by_name = {spec.name: spec for spec in TOOL_SPECS}
    return [
        mcp_types.Tool(
            name=name,
            description=by_name[name].description,
            inputSchema=by_name[name].input_schema,
            annotations=mcp_types.ToolAnnotations(**by_name[name].annotations),
        )
        for name in ("executive_state", "executive_inbox", "executive_job", "ceo_intent_status")
    ]


def build_e1_mcp_app(settings: Any, *, audit_sink: Any) -> Any:
    """Compose one stateless, authenticated MCP HTTP edge around E1 ASGI."""

    from integrations.mastermind_executive_app.gateway import make_jwt_authenticators

    if not getattr(settings, "read_only", False):
        raise ValueError("E1 MCP requires read-only app settings")
    inner_app = build_e1_app(settings)
    read_authenticator, _submit_authenticator = make_jwt_authenticators(
        settings.policies, jwks_cache=settings.jwks_cache
    )
    verifier = MastermindTokenVerifier(
        authenticator=read_authenticator,
        policy=settings.policies.read,
        now=settings.clock,
        audit_sink=audit_sink,
    )
    server: Server = Server(f"{SERVER_NAME}-e1", version=SERVER_VERSION)
    tools = build_e1_tools()

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        try:
            request = server.request_context.request
        except LookupError as exc:
            raise ValueError("current MCP request is unavailable") from exc
        if not isinstance(request, Request):
            raise ValueError("current MCP request is unavailable")
        headers = request.headers.getlist("authorization")
        if len(headers) != 1 or name not in _E1_READ_NAMES:
            raise ValueError("ambiguous or unsupported E1 tool request")
        try:
            validated_arguments = validate_tool_arguments(name, arguments)
        except GatewayError as exc:
            payload = _e1_error(settings, name, exc.code, exc.message)
        else:
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=inner_app, raise_app_exceptions=True),
                    base_url="http://e1.internal",
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    response = await client.post(
                        f"/v1/tools/{name}",
                        headers=[("authorization", headers[0])],
                        json={"arguments": validated_arguments},
                    )
                if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
                    raise ValueError("inner response is unavailable")
                payload = response.json()
                if not _is_e1_envelope(payload, name):
                    raise ValueError("inner response has no E1 envelope")
            except (httpx.HTTPError, ValueError):
                payload = _e1_error(
                    settings, name, "backend_unavailable", "E1 response is unavailable"
                )
        return [
            mcp_types.TextContent(
                type="text", text=canonical_json(payload).decode("utf-8")
            )
        ]

    manager = StreamableHTTPSessionManager(
        server,
        stateless=True,
        json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=[
                "127.0.0.1",
                "127.0.0.1:*",
                "localhost",
                "localhost:*",
                "e1.local",
                "e1.local:*",
                "::1",
                "[::1]",
                "[::1]:*",
            ],
            allowed_origins=[],
        ),
    )
    protected = RequireAuthMiddleware(
        BoundedRequestApp(manager.handle_request),
        required_scopes=list(settings.policies.read.required_scopes),
        resource_metadata_url=settings.policies.read.resource_metadata_url,
    )
    authenticated = AuthenticationMiddleware(protected, backend=BearerAuthBackend(verifier))

    @asynccontextmanager
    async def lifespan(_app: Any):
        try:
            async with manager.run():
                yield
        finally:
            await inner_app.aclose()

    metadata_path = urlsplit(settings.policies.read.resource_metadata_url).path or "/"

    async def metadata(_request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(settings.policies.read))

    outer_app = Starlette(
        routes=[
            Route(metadata_path, metadata, methods=["GET"]),
            Route("/mcp", authenticated, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    outer_app.router.redirect_slashes = False
    from integrations.mastermind_executive_app.app import _RawPathFence

    return _DuplicateAuthorizationGuard(
        outer_app,
        fenced_app=_RawPathFence(
            outer_app, metadata_path=metadata_path, read_gateway=inner_app
        ),
    )


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
