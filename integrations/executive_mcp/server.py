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

import asyncio
import dataclasses
import json
import re
from contextlib import asynccontextmanager, AsyncExitStack
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, parse_qsl

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
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from control_plane.workspace_owned_task import await_owned
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import (
    mcp_auth_error_result, oauth_security_schemes, protected_resource_metadata,
)
from integrations.business_mcp_auth.contracts import AuthError, AuthErrorCode
from integrations.executive_mcp.adapter import ExecutiveMcpGateway, GatewayConfig
from integrations.executive_mcp.e1_http import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    BoundedE1App,
    BoundedRequestApp,
    E1_READ_PATHS,
    PreAuthMcpBodyApp,
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

#: Three fixed POST routes served by the OS Executive transport.  These are
#: exactly the routes enumerated in the integration continuation; nothing
#: else is added by the opt-in OS transport.
_OS_EXECUTIVE_ROUTES: tuple[str, ...] = (
    "/os/executive/context",
    "/os/executive/submit",
    "/os/executive/status",
)

__all__ = ["build_executive_mcp_app", "build_web_ceo_mcp_app", "build_web_ceo_sessions_mcp_app", "build_web_ceo_v3_mcp_app", "build_e1_mcp_app", "build_e1_tools", "build_personal_read_mcp_app", "build_personal_read_tools", "build_mcp_server", "build_tools", "build_web_ceo_tools", "build_web_ceo_sessions_tools", "run_stdio"]

_E1_READ_NAMES = tuple(path.rsplit("/", 1)[-1] for path in sorted(E1_READ_PATHS))
_E1_ENVELOPE_FIELDS = frozenset(
    {
        "schema", "tool", "ok", "server_version", "mode", "generated_at",
        "grounding", "data", "degraded", "bounded", "error",
    }
)
_MAX_EXECUTIVE_OAUTH_RESOURCES = 17


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


def _is_e1_envelope(
    payload: Any, tool: str, server_version: str = SERVER_VERSION
) -> bool:
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
        or payload["server_version"] != server_version
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

    def __init__(self, app: Any, *, fenced_app: Any | None = None, mcp_path: str = "/mcp") -> None:
        if mcp_path not in {"/mcp", "/mcp/coo"}:
            raise ValueError("unknown static Executive transport")
        self._app = app
        self._fenced_app = fenced_app or app
        self._mcp_path = mcp_path

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == self._mcp_path:
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
    authenticated = PreAuthMcpBodyApp(
        AuthenticationMiddleware(protected, backend=BearerAuthBackend(verifier))
    )

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


def build_personal_read_tools() -> list[mcp_types.Tool]:
    """Installed Personal profile: exactly four read-only Executive tools."""

    from integrations.executive_mcp.personal_read import PERSONAL_READ_TOOL_SPECS

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in PERSONAL_READ_TOOL_SPECS
    ]


def build_personal_read_mcp_app(settings: Any, *, audit_sink: Any) -> Any:
    """Publish only installed CeoIngress-v1 readers over authenticated MCP HTTP.

    This edge is intentionally smaller than the Business/Web-CEO composition:
    it has no submit or reconcile route, no optional workspace/Steward/OS
    mounts, and no direct Runtime/filesystem reader.  The existing Executive
    Control process remains the sole owner of canonical read projection.
    """

    from integrations.executive_mcp.personal_read import (
        PERSONAL_READ_SERVER_NAME,
        PERSONAL_READ_SERVER_VERSION,
        PERSONAL_READ_TOOL_NAMES,
        validate_personal_read_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import (
        _RawPathFence,
        _metadata_policy_and_path,
    )
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.mastermind_executive_app.gateway import (
        CeoIngressClient,
        CeoIngressReadGateway,
        _default_jwks_cache,
    )

    if getattr(settings, "read_only", False) or not getattr(
        settings, "read_from_ceo_ingress", False
    ):
        raise ValueError("Personal read MCP requires installed CeoIngress settings")
    _, metadata_path = _metadata_policy_and_path(settings.policies)
    if metadata_path == "/mcp":
        raise ValueError("metadata route collides with MCP transport")

    read_authenticator = JwtAuthenticator(
        policy=settings.policies.read,
        jwks_cache=(settings.jwks_cache or _default_jwks_cache(settings.policies.read)),
    )
    verifier = MastermindTokenVerifier(
        authenticator=read_authenticator,
        policy=settings.policies.read,
        now=settings.clock,
        audit_sink=audit_sink,
    )
    client = CeoIngressClient(
        connect_timeout=settings.connect_timeout,
        read_timeout=settings.read_timeout,
    )
    gateway = CeoIngressReadGateway(settings.ceo_ingress_socket_path, client)
    server: Server = Server(PERSONAL_READ_SERVER_NAME, version=PERSONAL_READ_SERVER_VERSION)
    schemes = oauth_security_schemes(settings.policies.read.required_scopes)
    tools = tuple(
        tool.model_copy(
            update={
                "securitySchemes": schemes,
                "meta": {"securitySchemes": schemes},
            }
        )
        for tool in build_personal_read_tools()
    )

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    def profile_error(tool: str, code: str, message: str) -> dict[str, Any]:
        payload = _e1_error(settings, tool, code, message)
        payload["server_version"] = PERSONAL_READ_SERVER_VERSION
        return payload

    @server.call_tool(validate_input=False)
    async def call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[mcp_types.TextContent]:
        try:
            request = server.request_context.request
        except LookupError as exc:
            raise ValueError("current MCP request is unavailable") from exc
        if not isinstance(request, Request) or len(request.headers.getlist("authorization")) != 1:
            raise ValueError("current unambiguous MCP authorization is unavailable")
        if name not in PERSONAL_READ_TOOL_NAMES:
            payload = profile_error(name, "not_found", "Personal read tool is unavailable")
        else:
            try:
                validated = validate_personal_read_tool_arguments(name, arguments)
                payload = await gateway.call(name, validated)
                if not _is_e1_envelope(payload, name, SERVER_VERSION):
                    raise ValueError("installed Executive response has no legacy read envelope")
                payload = dict(payload)
                payload["server_version"] = PERSONAL_READ_SERVER_VERSION
            except GatewayError as exc:
                payload = profile_error(name, exc.code, exc.message)
            except Exception:
                payload = profile_error(
                    name,
                    "backend_unavailable",
                    "installed Executive response is unavailable",
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
    authenticated = PreAuthMcpBodyApp(
        AuthenticationMiddleware(protected, backend=BearerAuthBackend(verifier))
    )

    @asynccontextmanager
    async def lifespan(_app: Any):
        try:
            async with manager.run():
                yield
        finally:
            await gateway.aclose()

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
    return _DuplicateAuthorizationGuard(
        outer_app,
        fenced_app=_RawPathFence(
            outer_app, metadata_path=metadata_path, read_gateway=gateway
        ),
    )


class _ExecutivePolicyVerifiers:
    """Compose exact-resource A1 adapters without widening any policy.

    Every contained verifier still owns one immutable ResourcePolicy. The
    composition only permits several explicitly configured resource variants
    to reach the same Executive service; each verifier independently performs
    full signature, issuer, audience, scope, subject and lifetime checks.
    """

    def __init__(
        self,
        *verifier_pairs: tuple[MastermindTokenVerifier, MastermindTokenVerifier],
    ):
        if len(verifier_pairs) > _MAX_EXECUTIVE_OAUTH_RESOURCES:
            raise TypeError("Executive OAuth resource composition exceeds 17 resources")
        if not verifier_pairs or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or any(not isinstance(item, MastermindTokenVerifier) for item in pair)
            for pair in verifier_pairs
        ):
            raise TypeError(
                "Executive verifier set requires read/submit verifier pairs"
            )
        self._verifier_pairs = tuple(verifier_pairs)

    async def verify_token(self, token: str) -> Any:
        for read_verifier, submit_verifier in self._verifier_pairs:
            access, code = await read_verifier.verify_token_with_code(token)
            if access is not None:
                return access
            if code == AuthErrorCode.SCOPE_REFUSED:
                access, code = await submit_verifier.verify_token_with_code(token)
                if access is not None:
                    return access
            if code != AuthErrorCode.RESOURCE_REFUSED:
                return None
        return None


class _ExecutivePathFence:
    """Literal, query-free routes for the private stateless HTTP transport."""

    def __init__(self, app: Any, metadata_path: str, *, workspace_app=None, content_app=None, os_app=None,
                 os_executive_transport=None):
        self._app = app
        self._routes = {metadata_path: "GET", "/mcp": "POST",
                        "/v1/tools/submit_ceo_intent/reconcile": "POST"}
        self._query_routes = set()
        self._workspace_routes = set()
        self._public_routes = set()
        if workspace_app is not None:
            self._workspace_routes.update((
                "/workspace/programs/current",
                "/workspace/work/current",
                "/workspace/mission/current",
                "/workspace/mission/v3/current",
                "/workspace/result/current",
            ))
            # v2 routes carry a query string; the legacy v1 mission route does too.
            self._query_routes.update((
                "/workspace/mission/current",
                "/workspace/mission/v3/current",
                "/workspace/result/current",
            ))
        if content_app is not None:
            self._workspace_routes.add("/workspace/window/current")
        self._routes.update({path: "GET" for path in self._workspace_routes})
        self._public_routes.update(self._workspace_routes)
        if os_app is not None:
            if type(os_app) is not OsStaticApp:
                raise ValueError("fixed OS static owner required")
            self._routes.update({path: "GET" for path in os_app.paths})
            self._public_routes.update(os_app.paths)
            self._query_routes.update(("/os/", "/os/auth/callback"))
        if os_executive_transport is not None:
            # The three fixed OS Executive routes are POST and require the
            # exact single bearer plus the closed host/origin set.  They are
            # never query-bearing and never alias onto static GET routes.
            self._routes.update({path: "POST" for path in _OS_EXECUTIVE_ROUTES})

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if (self._routes.get(path) != scope.get("method") or not path.isascii()
                    or scope.get("raw_path") != path.encode("ascii")
                    or (scope.get("query_string") and path not in self._query_routes)):
                await JSONResponse({"ok": False, "error": {
                    "code": "not_found", "message": "unknown Executive transport route",
                }}, status_code=404, headers=_OS_RESPONSE_HEADERS if path.startswith("/os/") else None)(scope, receive, send)
                return
            if path in self._public_routes:
                headers = scope.get("headers", ())
                hosts = [v for k, v in headers if k.lower() == b"host"]
                origins = [v for k, v in headers if k.lower() == b"origin"]
                if (scope.get("scheme") != "https" or hosts != [b"mcp.mastermind-x.com"]
                        or len(origins) > 1 or (origins and origins != [b"https://mcp.mastermind-x.com"])):
                    await JSONResponse({"error": "transport_refused"}, status_code=403,
                        headers=_OS_RESPONSE_HEADERS if path.startswith("/os/")
                        else {"Cache-Control": "no-store"})(scope, receive, send)
                    return
            if path in _OS_EXECUTIVE_ROUTES:
                headers = scope.get("headers", ())
                hosts = [v for k, v in headers if k.lower() == b"host"]
                origins = [v for k, v in headers if k.lower() == b"origin"]
                authorizations = [v for k, v in headers if k.lower() == b"authorization"]
                if (scope.get("scheme") != "https" or hosts != [b"mcp.mastermind-x.com"]
                        or len(origins) > 1 or (origins and origins != [b"https://mcp.mastermind-x.com"])
                        or len(authorizations) != 1):
                    await JSONResponse({"ok": False, "error": {"code": "transport_refused", "message": "fixed OS transport refused"}},
                        status_code=403, headers=_OS_RESPONSE_HEADERS)(scope, receive, send)
                    return
            if path in self._workspace_routes and sum(
                    key.lower() == b"authorization" for key, _ in scope.get("headers", ())) > 1:
                await JSONResponse({"error": "authentication_required"}, status_code=401,
                                   headers={"Cache-Control": "no-store"})(scope, receive, send)
                return
        await self._app(scope, receive, send)


class AuditedWorkspaceApp:
    """Incumbent A1 audit gate; the sibling independently verifies the bearer.

    No principal is injected into ASGI state. A sink failure in the existing
    verifier refuses admission before the sibling can acquire its source.
    """
    def __init__(self, app, verifier):
        if not isinstance(verifier, MastermindTokenVerifier):
            raise TypeError("incumbent A1 verifier required")
        self._app, self._verifier = app, verifier

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        headers = [value for key, value in scope.get("headers", ()) if key.lower() == b"authorization"]
        token = None
        if len(headers) == 1:
            try:
                scheme, value = headers[0].decode("ascii").split(" ", 1)
                if scheme.lower() == "bearer" and value and not any(c.isspace() for c in value):
                    token = value
            except (UnicodeError, ValueError):
                pass
        if token is not None and await self._verifier.verify_token(token) is not None:
            await self._app(scope, receive, send)
            return
        await JSONResponse({"error": "authentication_required"}, status_code=401,
            headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"})(scope, receive, send)


@asynccontextmanager
async def _mounted_lifespan(app):
    """Join an optional owner's ASGI lifecycle under the existing listener."""
    incoming, outgoing = asyncio.Queue(), asyncio.Queue()
    task = asyncio.create_task(app({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}},
                                   incoming.get, outgoing.put))
    started = False
    try:
        await incoming.put({"type": "lifespan.startup"})
        response = await asyncio.wait_for(outgoing.get(), 10)
        if response.get("type") != "lifespan.startup.complete":
            raise RuntimeError("optional App startup failed")
        started = True
        yield
    finally:
        async def finish_owner():
            try:
                if started and not task.done():
                    await incoming.put({"type": "lifespan.shutdown"})
                    response = await asyncio.wait_for(outgoing.get(), 10)
                    if response.get("type") != "lifespan.shutdown.complete":
                        raise RuntimeError("optional App shutdown failed")
            finally:
                # A shutdown deadline is a failure, never permission to abandon
                # or cancel cleanup. Retain custody until the owner terminates.
                if not started and not task.done():
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    if started:
                        raise
        await await_owned(asyncio.create_task(finish_owner()))


_OS_RESPONSE_HEADERS = {
    "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self' https://dev-eo0jf8us5mup7wd5.us.auth0.com; "
        "img-src 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'; form-action 'none'",
}


class OsStaticApp:
    """Three verified release assets, never a pathname supplied by a request."""
    def __init__(self, assets):
        # The sealed launcher supplies already-hashed immutable bytes. The
        # static owner itself also closes the route set before outer routing.
        if type(assets) is not dict or len(assets) != 3 or "/os/" not in assets:
            raise ValueError("fixed OS asset set required")
        expected = {"/os/": "text/html; charset=utf-8"}
        for suffix, mime in (("css", "text/css; charset=utf-8"), ("js", "text/javascript; charset=utf-8")):
            paths = [path for path in assets if isinstance(path, str)
                     and re.fullmatch(r"/os/assets/index-[A-Za-z0-9_-]+\." + suffix, path)]
            if len(paths) != 1:
                raise ValueError("fixed OS asset set required")
            expected[paths[0]] = mime
        for path, value in assets.items():
            if (type(value) is not tuple or len(value) != 2 or type(value[0]) is not bytes
                    or not 0 < len(value[0]) <= 4 * 1024 * 1024 or value[1] != expected.get(path)):
                raise ValueError("fixed OS asset bytes and MIME required")
        self._assets = dict(assets)
        self.paths = frozenset((*self._assets, "/os/", "/os/auth/callback"))

    @staticmethod
    def _query_allowed(path, raw):
        if not raw:
            return True
        if len(raw) > 8192 or b"#" in raw or re.search(rb"%(?![0-9A-Fa-f]{2})", raw) or path not in ("/os/", "/os/auth/callback"):
            return False
        try:
            pairs = parse_qsl(raw.decode("ascii"), keep_blank_values=True,
                              strict_parsing=True, encoding="utf-8", errors="strict", max_num_fields=5)
            fields = dict(pairs)
            if any(any(ord(c) < 32 or ord(c) == 127 for c in key + value) for key, value in pairs):
                return False
            if len(fields) != len(pairs):
                return False
            if path == "/os/":
                from integrations.mastermind_workspace_app.contract import selection
                selection(fields)
            elif not fields or not set(fields) <= {"code", "state", "error", "error_description", "iss"}:
                return False
            return True
        except (ValueError, UnicodeError):
            return False

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if (scope.get("method") != "GET" or path not in self.paths
                or scope.get("raw_path") != path.encode("ascii")
                or not self._query_allowed(path, scope.get("query_string", b""))):
            await Response(status_code=404, headers=_OS_RESPONSE_HEADERS)(scope, receive, send)
            return
        # Bound empty chunks as well; GET never accepts a request body.
        for _ in range(32):
            message = await receive()
            if message.get("type") != "http.request" or message.get("body"):
                await Response(status_code=400, headers=_OS_RESPONSE_HEADERS)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        else:
            await Response(status_code=400, headers=_OS_RESPONSE_HEADERS)(scope, receive, send)
            return
        key = "/os/" if path == "/os/auth/callback" else path
        body, mime = self._assets[key]
        headers = {**_OS_RESPONSE_HEADERS, "Content-Type": mime}
        await Response(body, headers=headers)(scope, receive, send)


def _executive_outcome(payload: Any, request_ref: str, status_code: int) -> bool:
    """Require the existing App outcome and the original deterministic identity."""
    if not isinstance(payload, dict):
        return False
    expected_status = {
        "accepted": 200, "operation_conflict": 409, "refused": 200,
        "ingress_unavailable": 503, "effect_unknown": 202,
    }
    status = payload.get("status")
    if (
        not isinstance(status, str)
        or expected_status.get(status) != status_code
        or payload.get("request_ref") != request_ref
        or payload.get("ok") is not (status == "accepted")
        or set(payload) - {"ok", "status", "request_ref", "receipt", "error"}
    ):
        return False
    if status == "accepted":
        receipt = payload.get("receipt")
        return isinstance(receipt, dict) and receipt.get("dispatched") is False
    error = payload.get("error")
    return (
        isinstance(error, dict) and set(error) == {"code", "message"}
        and isinstance(error["code"], str) and isinstance(error["message"], str)
    )


def _build_profile_mcp_app(
    settings: Any,
    *,
    audit_sink: Any,
    profile_server_name: str,
    profile_server_version: str,
    profile_tools: tuple[mcp_types.Tool, ...],
    profile_validator: Any,
    profile_create_app: Any,
    workspace_app=None,
    content_app=None,
    os_app=None,
    release_profile: bool = False,
    release_tool_names: tuple[str, ...] = (),
    direct_tool_names: tuple[str, ...] = (),
    direct_submit_names: tuple[str, ...] = (),
    direct_handler: Any = None,
    direct_error_factory: Any = None,
    inner_server_version: str | None = None,
    enable_os_executive_transport: bool = False,
) -> Any:
    """Compose one compile-time selected MCP profile over the existing App.

    This is a stateless transport composition, not a new admission service.
    Submit and status use only the App's dedicated CeoIngress client. Every
    tool call forwards its current raw bearer for independent App verification.
    No installed configuration, public listener, or fixture write is implied.

    The OS Executive transport is opt-in via ``enable_os_executive_transport``;
    when enabled it requires the exact installed v3 composition (server 1.4.0,
    ``OsStaticApp``, ``read_from_ceo_ingress=True``) and exposes exactly three
    POST routes around the existing :class:`BoundedE1App`.
    """
    from control_plane.ceo_request import app_request_ref, automated_intent_id
    from integrations.mastermind_executive_app.app import (
        _authenticate, _metadata_policy_and_path, _outcome_response,
    )
    from integrations.mastermind_executive_app.admission import (
        AdmissionOutcome, STATUS_EFFECT_UNKNOWN,
    )
    from integrations.mastermind_executive_app.gateway import (
        make_jwt_authenticator_variants, make_shared_jwks_cache,
    )

    if settings.read_only:
        raise ValueError("authenticated Executive MCP refuses read-only app settings")
    if type(enable_os_executive_transport) is not bool:
        raise ValueError("OS Executive transport toggle must be boolean")
    if release_profile and any(app is not None for app in (workspace_app, content_app, os_app)):
        raise ValueError("release control profile refuses optional mounts")
    # This tuple is fixed by the builder, never selected by an MCP argument.
    # The historical four-tool release profile keeps its existing behavior.
    if type(release_tool_names) is not tuple or any(
        type(name) is not str for name in release_tool_names
    ):
        raise ValueError("release tool names must be a static tuple")
    if release_tool_names:
        from control_plane.executive_release_ingress import OPERATIONS
        names = tuple(tool.name for tool in profile_tools)
        if (len(release_tool_names) != len(set(release_tool_names))
                or set(release_tool_names) != set(OPERATIONS)
                or len(names) != len(set(names))
                or not set(release_tool_names) <= set(names)):
            raise ValueError("release tool names must match the fixed operation inventory")
    names = tuple(tool.name for tool in profile_tools)
    if (type(direct_tool_names) is not tuple or type(direct_submit_names) is not tuple
            or any(type(name) is not str for name in direct_tool_names + direct_submit_names)
            or len(direct_tool_names) != len(set(direct_tool_names))
            or len(direct_submit_names) != len(set(direct_submit_names))
            or not set(direct_submit_names) <= set(direct_tool_names)
            or not set(direct_tool_names) <= set(names)
            or (bool(direct_tool_names) != callable(direct_handler))
            or (bool(direct_tool_names) != callable(direct_error_factory))):
        raise ValueError("direct MCP tool composition is invalid")
    _, metadata_path = _metadata_policy_and_path(settings.policies)
    if metadata_path == "/mcp":
        raise ValueError("metadata route collides with MCP transport")
    if type(settings.additional_policies) is not tuple or len(
        settings.additional_policies
    ) >= _MAX_EXECUTIVE_OAUTH_RESOURCES:
        raise ValueError("Executive OAuth resource composition must contain 1 to 17 resources")
    configured = dataclasses.replace(settings, allow_submit_authorized_reads=True)
    if configured.jwks_cache is None:
        shared_cache = make_shared_jwks_cache(configured.policies)
        if shared_cache is not None:
            configured = dataclasses.replace(configured, jwks_cache=shared_cache)
    policy_variants = (configured.policies, *configured.additional_policies)
    authenticator_variants = make_jwt_authenticator_variants(
        configured.policies,
        configured.additional_policies,
        primary_jwks_cache=configured.jwks_cache,
    )
    verifier = _ExecutivePolicyVerifiers(*(
        tuple(
            MastermindTokenVerifier(
                authenticator=authenticator,
                policy=policy,
                now=configured.clock,
                audit_sink=audit_sink,
            )
            for authenticator, policy in zip(
                authenticator_pair, (policy_pair.read, policy_pair.submit)
            )
        )
        for authenticator_pair, policy_pair in zip(
            authenticator_variants, policy_variants
        )
    ))
    read_authenticators = tuple(pair[0] for pair in authenticator_variants)
    submit_authenticators = tuple(pair[1] for pair in authenticator_variants)
    # Reuse the bounded ASGI seam. Its generic failure body is never evidence
    # of no effect: all unrecognized submit replies become same-request UNKNOWN.
    inner_app = BoundedE1App(profile_create_app(configured))

    # Construct the OS Executive transport with the EXACT submit
    # MastermindTokenVerifier and matching submit JwtAuthenticator(s) — never a
    # read or workspace verifier.  No resource widening, no fallback.
    os_transport_handler = None
    if enable_os_executive_transport:
        from integrations.mastermind_executive_app.os_transport import OsExecutiveTransportApp

        if (
            profile_server_name != "mastermind-executive"
            or profile_server_version != "1.4.0"
            or os_app is None
            or type(os_app) is not OsStaticApp
            or not getattr(configured, "read_from_ceo_ingress", False)
        ):
            raise ValueError("OS Executive transport requires exact installed v3 composition")

        os_transport_handler = OsExecutiveTransportApp(
            inner_app,
            submit_verifier=tuple(
                MastermindTokenVerifier(authenticator=authenticator, policy=policy.submit,
                                        now=configured.clock, audit_sink=audit_sink)
                for authenticator, policy in zip(submit_authenticators, policy_variants)
            ),
            submit_authenticator=submit_authenticators,
            clock=configured.clock,
        )
    server: Server = Server(profile_server_name, version=profile_server_version)
    def authenticated_tool(tool: mcp_types.Tool) -> mcp_types.Tool:
        policy = (
            configured.policies.submit
            if (release_profile or tool.name in release_tool_names
                or tool.name in direct_submit_names or tool.name == "submit_ceo_intent")
            else configured.policies.read
        )
        schemes = oauth_security_schemes(policy.required_scopes)
        return tool.model_copy(update={
            "securitySchemes": schemes,
            "meta": {"securitySchemes": schemes},
        })

    tools = tuple(authenticated_tool(tool) for tool in profile_tools)

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    def unknown(request_ref: str | None, *, is_release: bool) -> dict[str, Any]:
        if is_release:
            from integrations.executive_mcp.release_control import unknown_release_result
            return unknown_release_result()
        if request_ref is None:
            raise ValueError("CEO recovery requires the original request reference")
        # The exposed reader accepts an intent id, not an outer request ref.
        # Reuse the canonical identity owner; never copy its hash derivation.
        intent_id = automated_intent_id(request_ref)
        response = _outcome_response(AdmissionOutcome(
            status=STATUS_EFFECT_UNKNOWN, request_ref=request_ref, code="effect_unknown",
            message=("the Executive response is unavailable; read ceo_intent_status "
                     f"with intent_id={intent_id} for this original request. "
                     "A not_found response does not authorize resubmission. "
                     "Preserve request_ref and require canonical reconciliation "
                     "before any further submission."),
        ))
        return json.loads(response.body)

    def result(payload: dict[str, Any], *, challenge: str | None = None) -> mcp_types.CallToolResult:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=canonical_json(payload).decode("utf-8"))],
            isError=payload.get("ok") is not True,
            _meta={"mcp/www_authenticate": [challenge]} if challenge else None,
        )

    def profile_error(tool: str, code: str, message: str) -> dict[str, Any]:
        payload = _e1_error(configured, tool, code, message)
        payload["server_version"] = profile_server_version
        return payload

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> mcp_types.CallToolResult:
        request = server.request_context.request
        if not isinstance(request, Request) or len(request.headers.getlist("authorization")) != 1:
            raise ValueError("current unambiguous MCP authorization is unavailable")
        try:
            validated = profile_validator(name, arguments)
        except GatewayError as exc:
            return result(profile_error(name, exc.code, exc.message))
        is_submit = name == "submit_ceo_intent"
        is_release = release_profile or name in release_tool_names
        is_direct = name in direct_tool_names
        request_ref = app_request_ref(validated["operation_key"]) if is_submit else None
        if is_direct:
            active = submit_authenticators if name in direct_submit_names else read_authenticators
            principal_or_response = await _authenticate(
                request, active, clock=configured.clock
            )
            if isinstance(principal_or_response, JSONResponse):
                payload = json.loads(principal_or_response.body)
                challenge = principal_or_response.headers.get("www-authenticate")
                if (name in direct_submit_names
                        and payload.get("error", {}).get("code") == "scope_refused"):
                    challenge = mcp_auth_error_result(
                        configured.policies.submit, AuthError(AuthErrorCode.SCOPE_REFUSED),
                        required_scopes=configured.policies.submit.required_scopes,
                    )["_meta"]["mcp/www_authenticate"][0]
                return result(payload, challenge=challenge)
            direct_submit = name in direct_submit_names
            try:
                payload = await direct_handler(principal_or_response, name, validated)
                canonical_json(payload)
            except Exception:
                payload = direct_error_factory(
                    name,
                    "effect_unknown" if direct_submit else "backend_unavailable",
                    (
                        "direct modifying tool outcome is unknown; reconcile the original operation"
                        if direct_submit
                        else "direct tool response is unavailable"
                    ),
                )
            reply = result(payload)
            if len(reply.model_dump_json(by_alias=True).encode("utf-8")) > MAX_RESPONSE_BYTES - MAX_REQUEST_BYTES - 4096:
                reply = result(direct_error_factory(
                    name,
                    "effect_unknown" if direct_submit else "output_too_large",
                    (
                        "direct modifying tool outcome is unknown; reconcile the original operation"
                        if direct_submit
                        else "direct tool response exceeds the transport budget"
                    ),
                ))
            return reply
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=inner_app, raise_app_exceptions=True),
                base_url="http://127.0.0.1", trust_env=False, follow_redirects=False,
            ) as client:
                response = await client.post(f"/v1/tools/{name}",
                    headers={"authorization": request.headers["authorization"]},
                    json={"arguments": validated})
            payload = response.json()
            canonical_json(payload)
            challenge = response.headers.get("www-authenticate")
            if response.status_code in (401, 403) and challenge:
                if is_release:
                    # Only the existing fixed auth refusal may cross this
                    # boundary. Rebuild the challenge; never relay arbitrary
                    # inner diagnostic text or a header carrying private data.
                    auth_error = AuthError(AuthErrorCode(payload["error"]["code"]))
                    expected = {"ok": False, "error": {"code": auth_error.code.value,
                                                      "message": auth_error.public_message}}
                    expected_status = 403 if auth_error.code == AuthErrorCode.SCOPE_REFUSED else 401
                    if payload != expected or response.status_code != expected_status:
                        return result(unknown(request_ref, is_release=is_release))
                    challenge = mcp_auth_error_result(configured.policies.submit,
                        auth_error)["_meta"]["mcp/www_authenticate"][0]
                if (is_submit or is_release) and payload.get("error", {}).get("code") == "scope_refused":
                    # The direct App's challenge intentionally omits requested
                    # scopes. Use its existing A1 helper for the MCP upgrade.
                    challenge = mcp_auth_error_result(configured.policies.submit,
                        AuthError(AuthErrorCode.SCOPE_REFUSED),
                        required_scopes=configured.policies.submit.required_scopes,
                    )["_meta"]["mcp/www_authenticate"][0]
                return result(payload, challenge=challenge)
            if is_release:
                from integrations.executive_mcp.release_control import valid_release_result
                if not valid_release_result(payload, name, validated, response.status_code):
                    payload = unknown(request_ref, is_release=is_release)
            elif is_submit:
                # These closed errors are raised before the App's socket send.
                preflight_error = (
                    response.status_code in (400, 403)
                    and isinstance(payload, dict) and payload.get("ok") is False
                    and isinstance(payload.get("error"), dict)
                    and payload["error"].get("code") in {
                        "invalid_input", "authority_refused", "grounding_unavailable", "internal_error",
                    }
                )
                if not preflight_error and not _executive_outcome(payload, request_ref, response.status_code):
                    payload = unknown(request_ref, is_release=is_release)
                elif payload.get("status") == STATUS_EFFECT_UNKNOWN:
                    # Same closed outcome, now usable through existing MCP tools.
                    payload = unknown(request_ref, is_release=False)
            elif response.status_code != 200 or not _is_e1_envelope(
                payload, name, inner_server_version or profile_server_version
            ):
                payload = profile_error(name, "backend_unavailable", "Executive response is unavailable")
        except Exception:
            payload = unknown(request_ref, is_release=is_release) if is_submit or is_release else profile_error(
                name, "backend_unavailable", "Executive response is unavailable")
        reply = result(payload)
        # Bound the actual escaped MCP result, reserving room for the maximum
        # admitted request id and JSON-RPC envelope, not only the inner JSON.
        if len(reply.model_dump_json(by_alias=True).encode("utf-8")) > MAX_RESPONSE_BYTES - MAX_REQUEST_BYTES - 4096:
            reply = result(unknown(request_ref, is_release=is_release) if is_submit or is_release else profile_error(
                name, "output_too_large", "Executive response exceeds the transport budget"))
        return reply

    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "::1", "[::1]", "[::1]:*"],
            allowed_origins=[],
        ))
    authenticated = PreAuthMcpBodyApp(
        AuthenticationMiddleware(
            RequireAuthMiddleware(BoundedRequestApp(manager.handle_request),
                required_scopes=list((configured.policies.submit if release_profile else configured.policies.read).required_scopes),
                resource_metadata_url=configured.policies.read.resource_metadata_url),
            backend=BearerAuthBackend(verifier),
        )
    )

    @asynccontextmanager
    async def lifespan(_app: Any):
        try:
            async with AsyncExitStack() as owners:
                if workspace_app is not None:
                    await owners.enter_async_context(_mounted_lifespan(workspace_app))
                if content_app is not None:
                    await owners.enter_async_context(_mounted_lifespan(content_app))
                async with manager.run():
                    yield
        finally:
            await inner_app.aclose()

    async def metadata(_request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(configured.policies.submit))

    outer_routes = [
        Route(metadata_path, metadata, methods=["GET"]),
        Route("/mcp", authenticated, methods=["POST"]),
    ]
    if not release_profile:
        outer_routes.append(Route("/v1/tools/submit_ceo_intent/reconcile", inner_app, methods=["POST"]))
    if workspace_app is not None:
        outer_routes.extend(Route(path, workspace_app, methods=["GET"]) for path in
                            ("/workspace/programs/current",
                             "/workspace/work/current",
                             "/workspace/mission/current",
                             "/workspace/mission/v3/current",
                             "/workspace/result/current"))
    if content_app is not None:
        outer_routes.append(Route("/workspace/window/current", content_app, methods=["GET"]))
    if os_app is not None:
        if type(os_app) is not OsStaticApp:
            raise ValueError("fixed OS static owner required")
        outer_routes.extend(Route(path, os_app, methods=["GET"]) for path in sorted(os_app.paths))
    if os_transport_handler is not None:
        for route_path in _OS_EXECUTIVE_ROUTES:
            outer_routes.append(Route(route_path, os_transport_handler, methods=["POST"]))
    outer_app = Starlette(routes=outer_routes, lifespan=lifespan)
    outer_app.router.redirect_slashes = False
    #: Public, read-only view of the OS Executive transport handler (or None
    #: if disabled). Tests use this to wrap a recording verifier without
    #: reaching into private route tables.
    outer_app.os_transport = os_transport_handler
    guard = _DuplicateAuthorizationGuard(outer_app,
        fenced_app=_ExecutivePathFence(outer_app, metadata_path, workspace_app=workspace_app,
                                      content_app=content_app, os_app=os_app,
                                      os_executive_transport=os_transport_handler))
    guard.os_transport = os_transport_handler
    return guard


def build_release_control_mcp_app(settings: Any, *, audit_sink: Any) -> Any:
    """Four explicit release tools; existing App and root owner retain authority."""
    from integrations.executive_mcp.release_control import (
        RELEASE_CONTROL_SERVER_VERSION, RELEASE_CONTROL_TOOL_SPECS,
        validate_release_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import create_release_control_app
    tools = tuple(mcp_types.Tool(name=spec.name, description=spec.description,
        inputSchema=spec.input_schema, annotations=mcp_types.ToolAnnotations(**spec.annotations))
        for spec in RELEASE_CONTROL_TOOL_SPECS)
    return _build_profile_mcp_app(settings, audit_sink=audit_sink,
        profile_server_name=SERVER_NAME, profile_server_version=RELEASE_CONTROL_SERVER_VERSION,
        profile_tools=tools, profile_validator=validate_release_tool_arguments,
        profile_create_app=create_release_control_app, release_profile=True)


def build_executive_mcp_app(settings: Any, *, audit_sink: Any,
                            workspace_app=None, content_app=None, os_app=None) -> Any:
    """Legacy BSC-E1 five-tool composition; public contract remains frozen."""

    from integrations.mastermind_executive_app.app import create_app

    return _build_profile_mcp_app(
        settings,
        audit_sink=audit_sink,
        profile_server_name=SERVER_NAME,
        profile_server_version=SERVER_VERSION,
        profile_tools=tuple(build_tools()),
        profile_validator=validate_tool_arguments,
        profile_create_app=create_app,
        workspace_app=workspace_app,
        content_app=content_app,
        os_app=os_app,
    )


def build_web_ceo_mcp_app(settings: Any, *, audit_sink: Any) -> Any:
    """Versioned six-tool Web-CEO composition over the same App/CeoIngress owners."""

    from integrations.executive_mcp.web_ceo import (
        WEB_CEO_SERVER_NAME,
        WEB_CEO_SERVER_VERSION,
        validate_web_ceo_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import create_web_ceo_app

    return _build_profile_mcp_app(
        settings,
        audit_sink=audit_sink,
        profile_server_name=WEB_CEO_SERVER_NAME,
        profile_server_version=WEB_CEO_SERVER_VERSION,
        profile_tools=tuple(build_web_ceo_tools()),
        profile_validator=validate_web_ceo_tool_arguments,
        profile_create_app=create_web_ceo_app,
    )


def build_web_ceo_release_mcp_app(
    settings: Any,
    *,
    audit_sink: Any,
    workspace_app=None,
    content_app=None,
    os_app=None,
) -> Any:
    """One v2 listener with the existing four separately authorized release tools."""
    from integrations.executive_mcp.release_control import RELEASE_CONTROL_TOOL_SPECS
    from integrations.executive_mcp.web_ceo_release import (
        WEB_CEO_RELEASE_SERVER_NAME, WEB_CEO_RELEASE_SERVER_VERSION,
        WEB_CEO_RELEASE_TOOL_SPECS, validate_web_ceo_release_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import create_release_control_app

    tools = tuple(mcp_types.Tool(
        name=spec.name, description=spec.description, inputSchema=spec.input_schema,
        annotations=mcp_types.ToolAnnotations(**spec.annotations),
    ) for spec in WEB_CEO_RELEASE_TOOL_SPECS)
    return _build_profile_mcp_app(
        settings, audit_sink=audit_sink,
        profile_server_name=WEB_CEO_RELEASE_SERVER_NAME,
        profile_server_version=WEB_CEO_RELEASE_SERVER_VERSION,
        profile_tools=tools, profile_validator=validate_web_ceo_release_tool_arguments,
        profile_create_app=create_release_control_app,
        workspace_app=workspace_app, content_app=content_app, os_app=os_app,
        release_tool_names=tuple(spec.name for spec in RELEASE_CONTROL_TOOL_SPECS),
    )


def build_web_ceo_v2_mcp_app(
    settings: Any,
    *,
    audit_sink: Any,
    workspace_app=None,
    content_app=None,
    os_app=None,
) -> Any:
    """Static Web-CEO v2 composition (server 1.2.0) over the same owners.

    The optional mounted apps and their behavior are the parent composition's
    existing surface, passed through unchanged; this profile adds none of its
    own and alters none of theirs.
    """

    from integrations.executive_mcp.web_ceo import (
        WEB_CEO_V2_SERVER_NAME,
        WEB_CEO_V2_SERVER_VERSION,
        validate_web_ceo_v2_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import create_web_ceo_v2_app

    return _build_profile_mcp_app(
        settings,
        audit_sink=audit_sink,
        profile_server_name=WEB_CEO_V2_SERVER_NAME,
        profile_server_version=WEB_CEO_V2_SERVER_VERSION,
        profile_tools=tuple(build_web_ceo_v2_tools()),
        profile_validator=validate_web_ceo_v2_tool_arguments,
        profile_create_app=create_web_ceo_v2_app,
        workspace_app=workspace_app,
        content_app=content_app,
        os_app=os_app,
    )


def _session_bridge_direct_contract(
    session_target_projector: Any,
    session_reply_handler: Any,
    session_summon_handler: Any,
) -> dict[str, Any]:
    """Reuse one authenticated Session Bridge policy in every host profile."""

    import inspect
    from collections.abc import Mapping
    from integrations.executive_mcp.web_ceo_sessions import (
        SESSION_TOOL_NAMES,
        SESSION_SUBMIT_TOOL_NAMES,
    )
    from integrations.session_bridge import schemas as bridge_schemas

    for name, value in (
        ("session_target_projector", session_target_projector),
        ("session_reply_handler", session_reply_handler),
        ("session_summon_handler", session_summon_handler),
    ):
        if not callable(value):
            raise TypeError(f"{name} must be callable")

    async def maybe(value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    def envelope(
        tool: str,
        *,
        data: Any = None,
        code: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": bridge_schemas.RESULT_SCHEMA,
            "server_version": bridge_schemas.SERVER_VERSION,
            "tool": tool,
            "ok": code is None,
            "data": data if code is None else None,
            "error": None if code is None else {"code": code, "message": message},
        }

    def refs(value: Any) -> set[str]:
        if not isinstance(value, (list, tuple)) or len(value) > 256:
            raise bridge_schemas.BridgeError(
                "backend_unavailable", "authorized target projection is unavailable"
            )
        found: set[str] = set()
        for row in value:
            if not isinstance(row, Mapping):
                raise bridge_schemas.BridgeError(
                    "backend_unavailable", "authorized target projection is unavailable"
                )
            target_ref = bridge_schemas.validate_target_ref(row.get("target_ref"))
            if target_ref in found:
                raise bridge_schemas.BridgeError(
                    "backend_unavailable", "authorized target projection is ambiguous"
                )
            found.add(target_ref)
        return found

    async def direct(
        principal: Any, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        modifying = name in SESSION_SUBMIT_TOOL_NAMES
        try:
            if name == "session_targets":
                projected = await maybe(
                    session_target_projector(principal, arguments.get("kind"))
                )
                refs(projected)
                return envelope(name, data=projected)
            if name == "session_send":
                target_ref = arguments["target_ref"]
                kind = target_ref.partition(":")[0]
                projected = await maybe(session_target_projector(principal, kind))
                if target_ref not in refs(projected):
                    return envelope(
                        name,
                        code="authority_refused",
                        message="target is not in the authenticated caller projection",
                    )
                data = await maybe(session_reply_handler(principal, dict(arguments)))
                if not isinstance(data, Mapping):
                    return envelope(
                        name,
                        code="effect_unknown",
                        message=(
                            "session reply outcome is unknown; reconcile the original operation"
                        ),
                    )
                return envelope(name, data=dict(data))
            data = await maybe(session_summon_handler(principal, dict(arguments)))
            if not isinstance(data, Mapping):
                return envelope(
                    name,
                    code="effect_unknown",
                    message=(
                        "session admission outcome is unknown; reconcile the original operation"
                    ),
                )
            return envelope(name, data=dict(data))
        except bridge_schemas.BridgeError as exc:
            return envelope(name, code=exc.code, message=exc.message)
        except Exception:
            return envelope(
                name,
                code="effect_unknown" if modifying else "backend_unavailable",
                message=(
                    "authenticated Session Bridge outcome is unknown; reconcile the original operation"
                    if modifying
                    else "authenticated Session Bridge owner is unavailable"
                ),
            )

    return {
        "direct_tool_names": SESSION_TOOL_NAMES,
        "direct_submit_names": SESSION_SUBMIT_TOOL_NAMES,
        "direct_handler": direct,
        "direct_error_factory": lambda tool, code, message: envelope(
            tool, code=code, message=message
        ),
    }


def build_web_ceo_v3_mcp_app(
    settings: Any,
    *,
    audit_sink: Any,
    mdm_reader: Any,
    session_target_projector: Any,
    session_reply_handler: Any,
    session_summon_handler: Any,
    session_reply_read_tool=None,
    workspace_app=None,
    content_app=None,
    os_app=None,
    enable_os_executive_transport: bool = False,
) -> Any:
    """Web-CEO v3 composition: v2 owners plus one read-only MDM sensor.

    ``enable_os_executive_transport`` is the default-off v3 opt-in for the
    three fixed POST OS Executive routes.  When enabled, it requires the
    exact installed v3 composition (server 1.4.0, ``OsStaticApp``,
    ``read_from_ceo_ingress=True``).
    """

    from integrations.executive_mcp.web_ceo_v3 import (
        WEB_CEO_V3_SERVER_NAME,
        WEB_CEO_V3_SERVER_VERSION,
        validate_web_ceo_v3_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import create_web_ceo_v3_app

    direct = _session_bridge_direct_contract(
        session_target_projector,
        session_reply_handler,
        session_summon_handler,
    )
    configuration = dict(
        audit_sink=audit_sink,
        profile_server_name=WEB_CEO_V3_SERVER_NAME,
        profile_server_version=WEB_CEO_V3_SERVER_VERSION,
        profile_tools=tuple(build_web_ceo_v3_tools()),
        profile_validator=validate_web_ceo_v3_tool_arguments,
        profile_create_app=lambda configured: create_web_ceo_v3_app(
            configured, mdm_reader=mdm_reader
        ),
        workspace_app=workspace_app,
        content_app=content_app,
        os_app=os_app,
        enable_os_executive_transport=enable_os_executive_transport,
        **direct,
    )
    if session_reply_read_tool is not None:
        from integrations.session_bridge.return_tools import NativeReplyReadTool
        if type(session_reply_read_tool) is not NativeReplyReadTool:
            raise TypeError("the canonical reply-read tool is required")
        configuration = session_reply_read_tool.extend_host_configuration(configuration)
    return _build_profile_mcp_app(settings, **configuration)


def build_web_ceo_sessions_mcp_app(
    settings: Any,
    *,
    audit_sink: Any,
    session_target_projector: Any,
    session_reply_handler: Any,
    session_summon_handler: Any,
    session_reply_read_tool=None,
    workspace_app=None,
    content_app=None,
    os_app=None,
) -> Any:
    """Authenticated Session Bridge profile over the existing Executive OAuth host."""

    from integrations.executive_mcp.web_ceo_sessions import (
        WEB_CEO_SESSIONS_SERVER_NAME,
        WEB_CEO_SESSIONS_SERVER_VERSION,
        WEB_CEO_SESSIONS_TOOL_SPECS,
        validate_web_ceo_sessions_tool_arguments,
    )
    from integrations.mastermind_executive_app.app import create_web_ceo_v2_app

    direct = _session_bridge_direct_contract(
        session_target_projector,
        session_reply_handler,
        session_summon_handler,
    )
    configuration = dict(
        audit_sink=audit_sink,
        profile_server_name=WEB_CEO_SESSIONS_SERVER_NAME,
        profile_server_version=WEB_CEO_SESSIONS_SERVER_VERSION,
        profile_tools=tuple(build_web_ceo_sessions_tools()),
        profile_validator=validate_web_ceo_sessions_tool_arguments,
        profile_create_app=create_web_ceo_v2_app,
        workspace_app=workspace_app,
        content_app=content_app,
        os_app=os_app,
        inner_server_version="1.2.0",
        **direct,
    )
    if session_reply_read_tool is not None:
        from integrations.session_bridge.return_tools import NativeReplyReadTool
        if type(session_reply_read_tool) is not NativeReplyReadTool:
            raise TypeError("the canonical reply-read tool is required")
        configuration = session_reply_read_tool.extend_host_configuration(configuration)
    return _build_profile_mcp_app(settings, **configuration)


def build_web_ceo_sessions_tools() -> list[mcp_types.Tool]:
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_TOOL_SPECS
    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        ) for spec in WEB_CEO_SESSIONS_TOOL_SPECS
    ]

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


def build_web_ceo_tools() -> list[mcp_types.Tool]:
    """Static Web-CEO v1 advertisement; legacy build_tools stays five-tool."""

    from integrations.executive_mcp.web_ceo import WEB_CEO_TOOL_SPECS

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in WEB_CEO_TOOL_SPECS
    ]


def build_web_ceo_v2_tools() -> list[mcp_types.Tool]:
    """Static Web-CEO v2 advertisement; earlier advertisements stay frozen."""

    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_TOOL_SPECS

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in WEB_CEO_V2_TOOL_SPECS
    ]


def build_web_ceo_v3_tools() -> list[mcp_types.Tool]:
    """Static Web-CEO v3 advertisement; prior profiles remain frozen."""

    from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_TOOL_SPECS

    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in WEB_CEO_V3_TOOL_SPECS
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


def build_coo_mcp_app(settings: Any, *, audit_sink: Any) -> Any:
    """Static COO route for composition in the existing listener; never a daemon."""
    from control_plane.coo_principal_request import principal_request_ref, principal_intent_id
    from control_plane import ceo_intent
    from integrations.executive_mcp.coo import (
        COO_MCP_PATH, COO_SERVER_NAME, COO_SERVER_VERSION, COO_TOOL_SPECS,
        validate_coo_tool_arguments,
    )
    from integrations.mastermind_executive_app.coo import create_coo_app, unknown

    core = create_coo_app(settings, audit_sink=audit_sink)
    inner = BoundedE1App(core)
    oauth = MastermindTokenVerifier(authenticator=core.authenticator, policy=settings.policy,
        now=settings.executive.clock, audit_sink=audit_sink)

    class BoundVerifier:
        async def verify_token(self, token):
            access = await oauth.verify_token(token)
            if access is None:
                return None
            try:
                principal, _ = await core.authorize_token(token)
                if (access.client_id != principal.client_ref or access.subject != principal.subject_digest
                        or access.resource != principal.resource or access.scopes != list(principal.scopes)):
                    return None
            except Exception:
                return None
            return access

    server = Server(COO_SERVER_NAME, version=COO_SERVER_VERSION)
    schemes = oauth_security_schemes(settings.policy.required_scopes)
    tools = tuple(mcp_types.Tool(name=spec.name, description=spec.description,
        inputSchema=spec.input_schema, annotations=mcp_types.ToolAnnotations(**spec.annotations),
        securitySchemes=schemes, _meta={"securitySchemes": schemes}) for spec in COO_TOOL_SPECS)

    @server.list_tools()
    async def list_tools():
        return list(tools)

    def error(name, code="backend_unavailable"):
        value = _e1_error(settings.executive, name, code, "COO response is unavailable")
        value["server_version"] = COO_SERVER_VERSION
        return value

    def result(payload, challenge=None):
        return mcp_types.CallToolResult(content=[mcp_types.TextContent(type="text",
            text=canonical_json(payload).decode("utf-8"))], isError=payload.get("ok") is not True,
            _meta={"mcp/www_authenticate": [challenge]} if challenge else None)

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        request = server.request_context.request
        if not isinstance(request, Request) or len(request.headers.getlist("authorization")) != 1:
            raise ValueError("unambiguous current authorization required")
        try:
            validated = validate_coo_tool_arguments(name, arguments)
        except GatewayError as exc:
            return result(error(name, exc.code))
        is_submit = name == "submit_principal_intent"
        has_receipt = is_submit or name == "principal_intent_status"
        request_ref = principal_request_ref(validated) if is_submit else validated.get("request_ref")
        def failed():
            return json.loads(unknown(request_ref).body) if has_receipt else error(name)
        challenge = None
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=inner),
                    base_url="http://127.0.0.1", trust_env=False, follow_redirects=False) as client:
                response = await client.post("/v1/tools/" + name,
                    headers={"authorization": request.headers["authorization"]}, json={"arguments": validated})
            payload = response.json()
            canonical_json(payload)
            challenge = response.headers.get("www-authenticate")
            preflight = (response.status_code in (400, 401, 403, 413, 503)
                and isinstance(payload, dict) and set(payload) == {"ok", "error"}
                and payload["ok"] is False and isinstance(payload["error"], dict)
                and payload["error"].get("code") in {"invalid_input", "authority_refused", "scope_refused",
                    "authorization_missing", "authorization_malformed", "identity_unverified", "grounding_unavailable"})
            if not preflight and has_receipt:
                if not _executive_outcome(payload, request_ref, response.status_code):
                    payload = failed()
                elif payload.get("ok") is True:
                    receipt = payload.get("receipt", {})
                    if (receipt.get("schema") != ceo_intent.RECEIPT_SCHEMA_PRINCIPAL
                            or receipt.get("request_ref") != request_ref
                            or receipt.get("intent_id") != principal_intent_id(request_ref)):
                        payload = failed()
            elif not preflight and (response.status_code != 200 or not _is_e1_envelope(payload, name, COO_SERVER_VERSION)):
                payload = failed()
        except Exception:
            payload = failed()
        reply = result(payload, challenge)
        if len(reply.model_dump_json(by_alias=True).encode("utf-8")) > MAX_RESPONSE_BYTES - MAX_REQUEST_BYTES - 4096:
            reply = result(failed() if has_receipt else error(name, "output_too_large"))
        return reply

    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "::1", "[::1]", "[::1]:*"],
            allowed_origins=[]))
    authenticated = PreAuthMcpBodyApp(AuthenticationMiddleware(
        RequireAuthMiddleware(BoundedRequestApp(manager.handle_request), required_scopes=list(settings.policy.required_scopes),
                              resource_metadata_url=settings.policy.resource_metadata_url),
        backend=BearerAuthBackend(BoundVerifier())))

    @asynccontextmanager
    async def lifespan(_app):
        try:
            async with manager.run():
                yield
        finally:
            await inner.aclose()

    app = Starlette(routes=[Route(COO_MCP_PATH, authenticated, methods=["POST"])], lifespan=lifespan)
    app.router.redirect_slashes = False
    return _LiteralCooRoute(app)


class _LiteralCooRoute:
    def __init__(self, app):
        self._app = app
        self._guard = _DuplicateAuthorizationGuard(app, mcp_path="/mcp/coo")

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and (
                scope.get("path") != "/mcp/coo" or scope.get("raw_path") != b"/mcp/coo"
                or scope.get("method") != "POST" or scope.get("query_string")):
            await JSONResponse({"error": "not_found"}, status_code=404)(scope, receive, send)
            return
        await self._guard(scope, receive, send)


class _ExecutiveWithCoo:
    """Two fixed role routes, one host process and one shared resource document."""
    def __init__(self, ceo, coo, metadata_path, metadata):
        self._ceo, self._coo = ceo, coo
        self._metadata_path, self._metadata = metadata_path, metadata

        @asynccontextmanager
        async def lifespan(_app):
            async with AsyncExitStack() as owners:
                await owners.enter_async_context(ceo._app.router.lifespan_context(ceo._app))
                await owners.enter_async_context(coo._app.router.lifespan_context(coo._app))
                yield
        self._app = Starlette(lifespan=lifespan)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
        elif scope.get("path", "").startswith("/mcp/coo"):
            await self._coo(scope, receive, send)
        elif (scope.get("path") == self._metadata_path and scope.get("method") == "GET"
                and scope.get("raw_path") == self._metadata_path.encode("ascii") and not scope.get("query_string")):
            await JSONResponse(self._metadata, headers={"Cache-Control": "no-store"})(scope, receive, send)
        else:
            await self._ceo(scope, receive, send)


def build_web_ceo_v2_with_coo_mcp_app(settings: Any, *, coo_settings: Any, audit_sink: Any,
                                    workspace_app=None, content_app=None, os_app=None) -> Any:
    """Opt-in host composition only. Existing CEO-only builders stay unchanged."""
    from integrations.mastermind_executive_app.coo import CooAppSettings
    from integrations.mastermind_executive_app.app import _metadata_policy_and_path
    from integrations.mastermind_executive_app.gateway import make_shared_jwks_cache
    if type(coo_settings) is not CooAppSettings or coo_settings.executive != settings:
        raise ValueError("COO and CEO must use the exact same installed Executive settings")
    cache = settings.jwks_cache or make_shared_jwks_cache(settings.policies)
    if cache is None:
        raise ValueError("a shared Executive JWKS authority is required")
    configured = dataclasses.replace(settings, jwks_cache=cache)
    coo_configured = dataclasses.replace(coo_settings, executive=configured)
    _, metadata_path = _metadata_policy_and_path(configured.policies)
    if metadata_path.startswith("/mcp/coo"):
        raise ValueError("metadata route collides with the static COO transport")
    metadata = protected_resource_metadata(configured.policies.submit)
    metadata["scopes_supported"] = sorted(set(metadata["scopes_supported"]) | set(coo_configured.policy.required_scopes))
    ceo = build_web_ceo_v2_mcp_app(configured, audit_sink=audit_sink,
        workspace_app=workspace_app, content_app=content_app, os_app=os_app)
    coo = build_coo_mcp_app(coo_configured, audit_sink=audit_sink)
    return _ExecutiveWithCoo(ceo, coo, metadata_path, metadata)