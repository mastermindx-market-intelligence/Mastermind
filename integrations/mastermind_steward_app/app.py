"""Authenticated stateless Streamable HTTP host for Mastermind Steward."""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.auth.provider import TokenVerifier
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from integrations.business_mcp_auth.contracts import (
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.metadata import protected_resource_metadata
from integrations.mastermind_secretary_mcp.server import (
    SecretaryGroundingContractServer,
)
from integrations.mastermind_steward_app.server import (
    REQUIRED_SCOPE,
    build_mcp_server,
)

__all__ = ["build_authenticated_app"]


class _ExactResourceApp:
    """Expose the MCP ASGI target at exactly one path, with optional trailing slash."""

    def __init__(self, app, resource_path: str) -> None:
        self._app = app
        self._resource_path = resource_path.rstrip("/") or "/"

    async def __call__(self, scope, receive, send) -> None:
        root_path = str(scope.get("root_path") or "").rstrip("/")
        path = str(scope.get("path") or "")
        full_path = (root_path + "/" + path.lstrip("/")) or "/"
        if (full_path.rstrip("/") or "/") != self._resource_path:
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await self._app(scope, receive, send)


def _path_from_https_url(url: str, *, label: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an HTTPS URL")
    path = parsed.path or "/"
    if not path.startswith("/"):
        raise ValueError(f"{label} path must be absolute")
    return path.rstrip("/") or "/"


def _allowed_hosts(
    policy: ResourcePolicy, extra_allowed_hosts: Sequence[str]
) -> list[str]:
    resource_host = urlsplit(policy.resource).netloc
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    if resource_host:
        hosts.append(resource_host)
    for value in extra_allowed_hosts:
        token = str(value).strip()
        if token and token not in hosts:
            hosts.append(token)
    return hosts


def build_authenticated_app(
    contract: SecretaryGroundingContractServer,
    *,
    policy: ResourcePolicy,
    token_verifier: TokenVerifier,
    extra_allowed_hosts: Sequence[str] = (),
    allowed_origins: Sequence[str] = ("https://chatgpt.com",),
) -> Starlette:
    """Build one stateless OAuth-protected Starlette MCP application.

    OAuth authenticates the caller and enforces the Steward resource scope.  It
    grants no Executive or organizational authority.  The app has no session,
    token, user, response, or company-state store.
    """

    if not isinstance(contract, SecretaryGroundingContractServer):
        raise TypeError("contract must be SecretaryGroundingContractServer")
    policy = validate_resource_policy(policy)
    if tuple(policy.required_scopes) != (REQUIRED_SCOPE,):
        raise ValueError("Steward policy must require exactly mastermind.steward.read")
    if not callable(getattr(token_verifier, "verify_token", None)):
        raise TypeError("token_verifier must provide verify_token")

    mcp_server = build_mcp_server(contract)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts(policy, extra_allowed_hosts),
        allowed_origins=[str(value) for value in allowed_origins],
    )
    manager = StreamableHTTPSessionManager(
        app=mcp_server,
        event_store=None,
        json_response=True,
        stateless=True,
        security_settings=security,
    )

    protected = RequireAuthMiddleware(
        AuthContextMiddleware(manager.handle_request),
        required_scopes=[REQUIRED_SCOPE],
        resource_metadata_url=policy.resource_metadata_url,
    )

    metadata_path = _path_from_https_url(
        policy.resource_metadata_url, label="resource_metadata_url"
    )
    resource_path = _path_from_https_url(policy.resource, label="resource")

    async def resource_metadata(_request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(policy))

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "mastermind-steward",
                "mode": "authenticated-readonly",
            }
        )

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with manager.run():
            yield

    parent_path = resource_path.rsplit("/", 1)[0] or "/"
    routes = [
        Route("/healthz", health, methods=["GET"]),
        Route("/readyz", health, methods=["GET"]),
        Route(metadata_path, resource_metadata, methods=["GET"]),
        Mount(parent_path, app=_ExactResourceApp(protected, resource_path)),
    ]
    middleware = [
        Middleware(
            AuthenticationMiddleware,
            backend=BearerAuthBackend(token_verifier),
        )
    ]
    application = Starlette(
        debug=False,
        routes=routes,
        middleware=middleware,
        lifespan=lifespan,
    )
    application.state.mcp_session_manager = manager
    application.state.resource_policy = policy
    return application
