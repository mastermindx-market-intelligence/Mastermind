"""Starlette host for one fixed authenticated workspace-content resource.

The app is inert until an owning deployment supplies a resource already bound to
accepted Business authentication and source callbacks.  It starts no listener,
provider process, projection, grant registry, history store, or background task.
"""
from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from integrations.business_mcp_auth.contracts import ResourcePolicy, validate_resource_policy
from integrations.business_mcp_auth.metadata import protected_resource_metadata
from integrations.mastermind_workspace_content.business import CONTENT_SCOPE
from integrations.mastermind_workspace_content.resource import WorkspaceContentResource
from integrations.mastermind_workspace_content.ui import UI_PATH, WORKSPACE_HTML


class _ContentEndpoint:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._app(scope, receive, send)


class _KnownPathGuard:
    """Reject query/path ambiguity before route or source access."""

    def __init__(self, app: ASGIApp, *, known_paths: Sequence[str]) -> None:
        self._app = app
        self._known = frozenset(path.encode("ascii") for path in known_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        raw_path = scope.get("raw_path")
        path = scope.get("path")
        if (
            not isinstance(raw_path, bytes)
            or not isinstance(path, str)
            or scope.get("root_path")
            or scope.get("query_string")
        ):
            await JSONResponse({"error": "not_found"}, status_code=404)(scope, receive, send)
            return
        try:
            decoded = path.encode("ascii")
        except UnicodeEncodeError:
            decoded = b""
        if raw_path != decoded or raw_path not in self._known:
            await JSONResponse({"error": "not_found"}, status_code=404)(scope, receive, send)
            return
        await self._app(scope, receive, send)


def _path(url: str, label: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"{label} must be one exact HTTPS URL")
    return parsed.path or "/"


def build_workspace_content_app(
    *,
    resource: WorkspaceContentResource,
    policy: ResourcePolicy,
) -> Starlette:
    """Build one stateless, read-only content resource server."""

    if not isinstance(resource, WorkspaceContentResource):
        raise TypeError("resource must be WorkspaceContentResource")
    policy = validate_resource_policy(policy)
    if policy.required_scopes != (CONTENT_SCOPE,):
        raise ValueError("workspace content policy must require exactly its content scope")
    if resource.resource_url != policy.resource:
        raise ValueError("resource must be bound to the same accepted policy resource")

    content_path = _path(policy.resource, "resource")
    metadata_path = _path(policy.resource_metadata_url, "resource_metadata_url")
    if content_path != resource.resource_path:
        raise ValueError("resource path does not match accepted resource URL")

    async def metadata(_request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(policy))

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "mastermind-workspace-content",
                "mode": "authenticated-readonly",
            }
        )

    async def ready(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ready",
                "service": "mastermind-workspace-content",
                "mode": "authenticated-readonly",
                "source_health": "not_asserted",
            }
        )

    async def workspace_ui(_request: Request) -> Response:
        return Response(
            WORKSPACE_HTML,
            media_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "script-src 'unsafe-inline'; connect-src 'self'; "
                    "img-src 'none'; font-src 'none'; object-src 'none'; "
                    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
                ),
            },
        )

    routes = [
        Route("/healthz", health, methods=["GET"]),
        Route("/readyz", ready, methods=["GET"]),
        Route(UI_PATH, workspace_ui, methods=["GET"]),
        Route(metadata_path, metadata, methods=["GET"]),
        Route(content_path, endpoint=_ContentEndpoint(resource), methods=["GET"]),
    ]
    known_paths = ("/healthz", "/readyz", UI_PATH, metadata_path, content_path)
    app = Starlette(
        debug=False,
        routes=routes,
        middleware=[Middleware(_KnownPathGuard, known_paths=known_paths)],
    )
    app.state.resource_policy = policy
    app.state.workspace_content_resource = resource
    return app


__all__ = ["build_workspace_content_app"]
