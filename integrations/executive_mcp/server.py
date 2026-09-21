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

__all__ = ["build_executive_mcp_app", "build_e1_mcp_app", "build_e1_tools", "build_mcp_server", "build_tools", "run_stdio"]

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


class _ExecutivePolicyVerifiers:
    """Compose the two existing A1 adapters without changing either policy.

    Each adapter independently verifies and audits an exact scope set. A read
    token is never projected into a submit principal, and vice versa.
    """

    def __init__(self, read: MastermindTokenVerifier, submit: MastermindTokenVerifier):
        self._read = read
        self._submit = submit

    async def verify_token(self, token: str) -> Any:
        access = await self._read.verify_token(token)
        if access is not None:
            return access
        return await self._submit.verify_token(token)


class _ExecutivePathFence:
    """Literal, query-free routes for the private stateless HTTP transport."""

    def __init__(self, app: Any, metadata_path: str, *, workspace_app=None, content_app=None, os_app=None):
        self._app = app
        self._routes = {metadata_path: "GET", "/mcp": "POST",
                        "/v1/tools/submit_ceo_intent/reconcile": "POST"}
        self._query_routes = set()
        self._workspace_routes = set()
        self._public_routes = set()
        if workspace_app is not None:
            self._workspace_routes.update(("/workspace/programs/current", "/workspace/mission/current"))
            self._query_routes.add("/workspace/mission/current")
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


def build_executive_mcp_app(settings: Any, *, audit_sink: Any,
                            workspace_app=None, content_app=None, os_app=None) -> Any:
    """Expose the frozen five tools through the existing authenticated App.

    This is a stateless transport composition, not a new admission service.
    Submit and status use only the App's dedicated CeoIngress client. Every
    tool call forwards its current raw bearer for independent App verification.
    No installed configuration, public listener, or fixture write is implied.
    """
    from control_plane.ceo_request import app_request_ref
    from integrations.mastermind_executive_app.app import (
        _metadata_policy_and_path, _outcome_response, create_app,
    )
    from integrations.mastermind_executive_app.admission import (
        AdmissionOutcome, STATUS_EFFECT_UNKNOWN,
    )
    from integrations.mastermind_executive_app.gateway import (
        make_jwt_authenticators, make_shared_jwks_cache,
    )

    if settings.read_only:
        raise ValueError("five-tool MCP refuses read-only app settings")
    _, metadata_path = _metadata_policy_and_path(settings.policies)
    if metadata_path == "/mcp":
        raise ValueError("metadata route collides with MCP transport")
    configured = dataclasses.replace(settings, allow_submit_authorized_reads=True)
    if configured.jwks_cache is None:
        shared_cache = make_shared_jwks_cache(configured.policies)
        if shared_cache is not None:
            configured = dataclasses.replace(configured, jwks_cache=shared_cache)
    authenticators = make_jwt_authenticators(configured.policies, jwks_cache=configured.jwks_cache)
    verifier = _ExecutivePolicyVerifiers(*(
        MastermindTokenVerifier(authenticator=authenticator, policy=policy,
            now=configured.clock, audit_sink=audit_sink)
        for authenticator, policy in zip(authenticators, (configured.policies.read, configured.policies.submit))
    ))
    # Reuse the bounded ASGI seam. Its generic failure body is never evidence
    # of no effect: all unrecognized submit replies become same-request UNKNOWN.
    inner_app = BoundedE1App(create_app(configured))
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION)
    def authenticated_tool(tool: mcp_types.Tool) -> mcp_types.Tool:
        policy = (
            configured.policies.submit
            if tool.name == "submit_ceo_intent"
            else configured.policies.read
        )
        schemes = oauth_security_schemes(policy.required_scopes)
        return tool.model_copy(update={
            "securitySchemes": schemes,
            "meta": {"securitySchemes": schemes},
        })

    tools = tuple(authenticated_tool(tool) for tool in build_tools())

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return list(tools)

    def unknown(request_ref: str) -> dict[str, Any]:
        response = _outcome_response(AdmissionOutcome(
            status=STATUS_EFFECT_UNKNOWN, request_ref=request_ref, code="effect_unknown",
            message="the Executive response is unavailable; reconcile the same request_ref before any further submission",
        ))
        return json.loads(response.body)

    def result(payload: dict[str, Any], *, challenge: str | None = None) -> mcp_types.CallToolResult:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=canonical_json(payload).decode("utf-8"))],
            isError=payload.get("ok") is not True,
            _meta={"mcp/www_authenticate": [challenge]} if challenge else None,
        )

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> mcp_types.CallToolResult:
        request = server.request_context.request
        if not isinstance(request, Request) or len(request.headers.getlist("authorization")) != 1:
            raise ValueError("current unambiguous MCP authorization is unavailable")
        try:
            validated = validate_tool_arguments(name, arguments)
        except GatewayError as exc:
            return result(_e1_error(configured, name, exc.code, exc.message))
        is_submit = name == "submit_ceo_intent"
        request_ref = app_request_ref(validated["operation_key"]) if is_submit else None
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
                if is_submit and payload.get("error", {}).get("code") == "scope_refused":
                    # The direct App's challenge intentionally omits requested
                    # scopes. Use its existing A1 helper for the MCP upgrade.
                    challenge = mcp_auth_error_result(configured.policies.submit,
                        AuthError(AuthErrorCode.SCOPE_REFUSED),
                        required_scopes=configured.policies.submit.required_scopes,
                    )["_meta"]["mcp/www_authenticate"][0]
                return result(payload, challenge=challenge)
            if is_submit:
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
                    payload = unknown(request_ref)
            elif response.status_code != 200 or not _is_e1_envelope(payload, name):
                payload = _e1_error(configured, name, "backend_unavailable", "Executive response is unavailable")
        except Exception:
            payload = unknown(request_ref) if is_submit else _e1_error(
                configured, name, "backend_unavailable", "Executive response is unavailable")
        reply = result(payload)
        # Bound the actual escaped MCP result, reserving room for the maximum
        # admitted request id and JSON-RPC envelope, not only the inner JSON.
        if len(reply.model_dump_json(by_alias=True).encode("utf-8")) > MAX_RESPONSE_BYTES - MAX_REQUEST_BYTES - 4096:
            reply = result(unknown(request_ref) if is_submit else _e1_error(
                configured, name, "output_too_large", "Executive response exceeds the transport budget"))
        return reply

    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "::1", "[::1]", "[::1]:*"],
            allowed_origins=[],
        ))
    authenticated = PreAuthMcpBodyApp(
        AuthenticationMiddleware(
            RequireAuthMiddleware(BoundedRequestApp(manager.handle_request),
                required_scopes=list(configured.policies.read.required_scopes),
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
        Route("/v1/tools/submit_ceo_intent/reconcile", inner_app, methods=["POST"]),
    ]
    if workspace_app is not None:
        outer_routes.extend(Route(path, workspace_app, methods=["GET"]) for path in
                            ("/workspace/programs/current", "/workspace/mission/current"))
    if content_app is not None:
        outer_routes.append(Route("/workspace/window/current", content_app, methods=["GET"]))
    if os_app is not None:
        if type(os_app) is not OsStaticApp:
            raise ValueError("fixed OS static owner required")
        outer_routes.extend(Route(path, os_app, methods=["GET"]) for path in sorted(os_app.paths))
    outer_app = Starlette(routes=outer_routes, lifespan=lifespan)
    outer_app.router.redirect_slashes = False
    return _DuplicateAuthorizationGuard(outer_app,
        fenced_app=_ExecutivePathFence(outer_app, metadata_path, workspace_app=workspace_app,
                                      content_app=content_app, os_app=os_app))

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
