"""Authenticated stateless Streamable HTTP host for Mastermind Steward."""
from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials, AuthenticationBackend
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from integrations.business_mcp_auth.contracts import (
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import (
    mcp_auth_error_result,
    protected_resource_metadata,
    www_authenticate,
)
from integrations.mastermind_secretary_mcp.server import SecretaryGroundingContractServer
from integrations.mastermind_steward_app.server import REQUIRED_SCOPE, build_mcp_server

__all__ = ["build_authenticated_app"]
MAX_REQUEST_BODY_BYTES = 1024 * 1024


async def _reply(
    scope: Scope,
    receive: Receive,
    send: Send,
    status: int,
    code: str,
    *,
    challenge: str | None = None,
) -> None:
    headers = {"WWW-Authenticate": challenge} if challenge else None
    await JSONResponse({"error": code}, status_code=status, headers=headers)(
        scope, receive, send
    )


def _headers(scope: Scope, name: bytes) -> list[bytes]:
    return [value for key, value in scope.get("headers", ()) if key.lower() == name]


def _ascii(value: bytes) -> str | None:
    try:
        token = value.decode("ascii")
    except UnicodeDecodeError:
        return None
    if (
        not token
        or token != token.strip()
        or "," in token
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in token)
    ):
        return None
    return token


def _accepts_json(value: bytes) -> bool:
    try:
        token = value.decode("ascii")
    except UnicodeDecodeError:
        return False
    if (
        not token
        or token != token.strip()
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in token)
    ):
        return False
    return any(
        media_type.partition(";")[0].strip().lower() == "application/json"
        for media_type in token.split(",")
    )


def _canonical_raw_path(scope: Scope) -> bytes:
    """Return exact raw bytes only when decoded and raw ASGI paths agree."""

    raw_path = scope.get("raw_path")
    path = scope.get("path")
    if not isinstance(raw_path, bytes) or not isinstance(path, str):
        return b""
    try:
        decoded_path = path.encode("ascii")
    except UnicodeEncodeError:
        return b""
    return raw_path if decoded_path == raw_path else b""


def _host_matches(candidate: str, allowed_hosts: Sequence[str]) -> bool:
    candidate = candidate.lower()
    for raw in allowed_hosts:
        allowed = raw.lower()
        if candidate == allowed:
            return True
        if not allowed.endswith(":*"):
            continue
        base = allowed[:-2]
        if candidate == base:
            return True
        prefix = base + ":"
        if candidate.startswith(prefix):
            port = candidate[len(prefix) :]
            if port.isdigit() and 1 <= int(port) <= 65535:
                return True
    return False


class _McpEndpoint:
    """Expose exactly one reviewed MCP ASGI request handler."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._app(scope, receive, send)


class _A1BearerAuthBackend(AuthenticationBackend):
    """Project A1's single verified decision into Starlette request auth."""

    def __init__(self, token_verifier: MastermindTokenVerifier) -> None:
        self._token_verifier = token_verifier

    async def authenticate(self, conn: HTTPConnection):
        auth_header = next(
            (
                conn.headers.get(key)
                for key in conn.headers
                if key.lower() == "authorization"
            ),
            None,
        )
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return None

        auth_info = await self._token_verifier.verify_token(auth_header[7:])
        if auth_info is None:
            return None
        return AuthCredentials(auth_info.scopes), AuthenticatedUser(auth_info)


class _StewardTransportGuard:
    """Refuse non-canonical HTTP before verifier, manager, or source access."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        resource_path: str,
        metadata_path: str,
        allowed_hosts: Sequence[str],
        allowed_origins: Sequence[str],
    ) -> None:
        self.app = app
        self.resource = resource_path.encode("ascii")
        self.public = {
            b"/healthz",
            b"/readyz",
            metadata_path.encode("ascii"),
        }
        self.allowed_hosts = tuple(allowed_hosts)
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        raw_path = _canonical_raw_path(scope)
        if scope.get("root_path") or scope.get("query_string"):
            await _reply(scope, receive, send, 404, "not_found")
            return
        if raw_path != self.resource and raw_path not in self.public:
            await _reply(scope, receive, send, 404, "not_found")
            return

        expected_method = "POST" if raw_path == self.resource else "GET"
        if str(scope.get("method") or "").upper() != expected_method:
            await _reply(scope, receive, send, 405, "method_not_allowed")
            return

        hosts = _headers(scope, b"host")
        origins = _headers(scope, b"origin")
        authorizations = _headers(scope, b"authorization")
        if len(hosts) != 1 or len(origins) > 1 or len(authorizations) > 1:
            await _reply(scope, receive, send, 400, "invalid_request")
            return
        host = _ascii(hosts[0])
        if host is None:
            await _reply(scope, receive, send, 400, "invalid_request")
            return
        if not _host_matches(host, self.allowed_hosts):
            await _reply(scope, receive, send, 421, "misdirected_request")
            return
        if origins:
            origin = _ascii(origins[0])
            if origin is None:
                await _reply(scope, receive, send, 400, "invalid_request")
                return
            if origin not in self.allowed_origins:
                await _reply(scope, receive, send, 403, "origin_refused")
                return
        if raw_path != self.resource:
            await self.app(scope, receive, send)
            return

        content_types = _headers(scope, b"content-type")
        if len(content_types) != 1:
            status = 400 if content_types else 415
            await _reply(
                scope,
                receive,
                send,
                status,
                "invalid_request" if status == 400 else "unsupported_media_type",
            )
            return
        content_type = _ascii(content_types[0])
        if content_type is None or content_type.lower() != "application/json":
            await _reply(scope, receive, send, 415, "unsupported_media_type")
            return

        accepts = _headers(scope, b"accept")
        if len(accepts) != 1:
            status = 400 if accepts else 406
            await _reply(
                scope,
                receive,
                send,
                status,
                "invalid_request" if status == 400 else "not_acceptable",
            )
            return
        if not _accepts_json(accepts[0]):
            await _reply(scope, receive, send, 406, "not_acceptable")
            return

        lengths = _headers(scope, b"content-length")
        if len(lengths) > 1:
            await _reply(scope, receive, send, 400, "invalid_request")
            return
        if lengths:
            length = _ascii(lengths[0])
            if length is None or not length.isdigit():
                await _reply(scope, receive, send, 400, "invalid_request")
                return
            if int(length) > MAX_REQUEST_BODY_BYTES:
                await _reply(scope, receive, send, 413, "request_too_large")
                return

        body = bytearray()
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                await _reply(scope, receive, send, 400, "invalid_request")
                return
            chunk = message.get("body", b"")
            if not isinstance(chunk, bytes):
                await _reply(scope, receive, send, 400, "invalid_request")
                return
            body.extend(chunk)
            if len(body) > MAX_REQUEST_BODY_BYTES:
                await _reply(scope, receive, send, 413, "request_too_large")
                return
            if not message.get("more_body", False):
                break
        try:
            json.loads(bytes(body))
        except (RecursionError, UnicodeDecodeError, ValueError):
            await _reply(scope, receive, send, 400, "invalid_request")
            return
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


def _challenge(policy: ResourcePolicy, error: AuthError) -> str:
    result = mcp_auth_error_result(
        policy, error, required_scopes=(REQUIRED_SCOPE,)
    )
    challenge = result["_meta"]["mcp/www_authenticate"][0]
    if not isinstance(challenge, str) or not challenge.startswith(
        www_authenticate(policy, (REQUIRED_SCOPE,))
    ):
        raise RuntimeError("A1 challenge projection is inconsistent")
    return challenge


class _A1AuthGate:
    """A1 remains the sole public invalid-token/insufficient-scope owner."""

    def __init__(self, app: ASGIApp, *, policy: ResourcePolicy, resource_path: str):
        self.app = app
        self.policy = policy
        self.resource = resource_path.encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or _canonical_raw_path(scope) != self.resource:
            await self.app(scope, receive, send)
            return
        user = scope.get("user")
        if not isinstance(user, AuthenticatedUser):
            code = (
                AuthErrorCode.AUTHORIZATION_MISSING
                if not _headers(scope, b"authorization")
                else AuthErrorCode.TOKEN_SIGNATURE_REFUSED
            )
            await _reply(
                scope,
                receive,
                send,
                401,
                "invalid_token",
                challenge=_challenge(self.policy, AuthError(code)),
            )
            return
        if REQUIRED_SCOPE not in getattr(scope.get("auth"), "scopes", ()):
            await _reply(
                scope,
                receive,
                send,
                403,
                "insufficient_scope",
                challenge=_challenge(
                    self.policy, AuthError(AuthErrorCode.SCOPE_REFUSED)
                ),
            )
            return
        await self.app(scope, receive, send)


def _url_path(url: str, label: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an HTTPS URL")
    return (parsed.path or "/").rstrip("/") or "/"


def _allowed_hosts(policy: ResourcePolicy) -> list[str]:
    values = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    resource_host = urlsplit(policy.resource).netloc
    if resource_host and resource_host not in values:
        values.append(resource_host)
    return values


def build_authenticated_app(
    contract: SecretaryGroundingContractServer,
    *,
    policy: ResourcePolicy,
    token_verifier: MastermindTokenVerifier,
    allowed_origins: Sequence[str] = ("https://chatgpt.com",),
) -> Starlette:
    """Build one stateless A1-authenticated, read-only Steward MCP app."""

    if not isinstance(contract, SecretaryGroundingContractServer):
        raise TypeError("contract must be SecretaryGroundingContractServer")
    policy = validate_resource_policy(policy)
    if tuple(policy.required_scopes) != (REQUIRED_SCOPE,):
        raise ValueError("Steward policy must require exactly mastermind.steward.read")
    if type(token_verifier) is not MastermindTokenVerifier:
        raise TypeError("token_verifier must be MastermindTokenVerifier")
    verifier_policy = MastermindTokenVerifier._validated_composition(token_verifier)
    if verifier_policy != policy:
        raise ValueError("token_verifier policy must match Steward policy")

    mcp_server = build_mcp_server(contract)
    hosts = _allowed_hosts(policy)
    origins = tuple(str(value) for value in allowed_origins)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=list(origins),
    )
    manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=None,
        json_response=True,
        stateless=True,
        security_settings=security,
    )
    metadata_path = _url_path(policy.resource_metadata_url, "resource_metadata_url")
    resource_path = _url_path(policy.resource, "resource")

    async def metadata(_request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(policy))

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {"status": "ok", "service": "mastermind-steward", "mode": "authenticated-readonly"}
        )

    async def ready(request: Request) -> JSONResponse:
        active = bool(getattr(request.app.state, "mcp_manager_ready", False))
        return JSONResponse(
            {
                "status": "ready" if active else "not_ready",
                "service": "mastermind-steward",
                "mode": "authenticated-readonly",
            },
            status_code=200 if active else 503,
        )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.mcp_manager_ready = False
        async with manager.run():
            app.state.mcp_manager_ready = True
            try:
                yield
            finally:
                app.state.mcp_manager_ready = False

    routes = [
        Route("/healthz", health, methods=["GET"]),
        Route("/readyz", ready, methods=["GET"]),
        Route(metadata_path, metadata, methods=["GET"]),
        Route(
            resource_path,
            endpoint=_McpEndpoint(manager.handle_request),
            methods=["POST"],
        ),
    ]
    middleware = [
        Middleware(_StewardTransportGuard,
            resource_path=resource_path,
            metadata_path=metadata_path,
            allowed_hosts=hosts,
            allowed_origins=origins,
        ),
        Middleware(
            AuthenticationMiddleware,
            backend=_A1BearerAuthBackend(token_verifier),
        ),
        Middleware(_A1AuthGate, policy=policy, resource_path=resource_path),
        Middleware(AuthContextMiddleware),
    ]
    application = Starlette(
        debug=False, routes=routes, middleware=middleware, lifespan=lifespan
    )
    application.state.mcp_manager_ready = False
    application.state.mcp_session_manager = manager
    application.state.resource_policy = policy
    return application
