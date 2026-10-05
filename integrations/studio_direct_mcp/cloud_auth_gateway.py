"""Authenticated public edge for the guarded Studio/Paper design route.

This module is transport/auth composition only. It owns no Paper operation,
Studio tool catalog, fleet registry, placement, provider client, credential,
retry queue, or lifecycle. The existing Studio design gateway remains the tool
authority. The public edge verifies one exact Business-MCP OAuth resource and
forwards admitted Streamable-HTTP requests to one exact tailnet design URL.
"""
from __future__ import annotations

import dataclasses
import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink,
    AuthErrorCode,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwks import BoundedJwksCache, HttpxJwksFetcher
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import (
    protected_resource_metadata,
    www_authenticate,
)

STUDIO_DESIGN_SCOPE = "mastermind.studio.design"
STUDIO_DESIGN_PATH = "/studio-design"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 70.0
_BEARER_RE = re.compile(r"^[Bb][Ee][Aa][Rr][Ee][Rr] ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$")
_REQUEST_HEADER_ALLOWLIST = frozenset(
    {"accept", "content-type", "mcp-protocol-version", "mcp-session-id", "last-event-id"}
)
_RESPONSE_HEADER_ALLOWLIST = frozenset(
    {"content-type", "mcp-session-id", "cache-control", "retry-after"}
)


class StudioCloudGatewayError(ValueError):
    """Closed construction/configuration refusal."""


@dataclasses.dataclass(frozen=True, slots=True)
class UpstreamResult:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class StudioForwarder(Protocol):
    async def call(
        self,
        *,
        method: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> UpstreamResult: ...


def _configuration(message: str) -> StudioCloudGatewayError:
    return StudioCloudGatewayError(message)


def _exact_tailnet_design_url(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _configuration("upstream URL refused")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise _configuration("upstream URL refused") from error
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or type(host) is not str
        or not host.endswith(".ts.net")
        or host == ".ts.net"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path != STUDIO_DESIGN_PATH
        or parsed.query
        or parsed.fragment
    ):
        raise _configuration("upstream URL refused")
    return f"https://{host}{STUDIO_DESIGN_PATH}"


def _validate_public_policy(policy: object) -> tuple[ResourcePolicy, str, str]:
    if not isinstance(policy, ResourcePolicy):
        raise _configuration("resource policy required")
    try:
        selected = validate_resource_policy(policy)
    except Exception as error:
        raise _configuration("resource policy refused") from error
    if selected.required_scopes != (STUDIO_DESIGN_SCOPE,):
        raise _configuration("Studio cloud policy must require the exact design scope")
    if selected.authorization_servers != (selected.issuer,):
        raise _configuration("Studio cloud policy must use one canonical issuer")
    resource = urlsplit(selected.resource)
    metadata = urlsplit(selected.resource_metadata_url)
    if (
        resource.path != "/mcp"
        or resource.query
        or resource.fragment
        or metadata.query
        or metadata.fragment
        or not metadata.path.startswith("/.well-known/oauth-protected-resource")
        or resource.netloc != metadata.netloc
    ):
        raise _configuration("Studio cloud resource paths are invalid")
    return selected, resource.netloc.lower(), resource.path


def build_business_auth_verifier(
    *,
    policy: ResourcePolicy,
    now: Callable[[], int],
    monotonic: Callable[[], float],
    audit_sink: AuthAuditSink,
) -> MastermindTokenVerifier:
    """Compose only the existing Business-MCP auth owners."""

    selected, _host, _path = _validate_public_policy(policy)
    if not callable(now) or not callable(monotonic) or not callable(
        getattr(audit_sink, "emit", None)
    ):
        raise _configuration("authentication services are invalid")
    cache = BoundedJwksCache(
        policy=selected,
        fetcher=HttpxJwksFetcher(selected),
        monotonic=monotonic,
    )
    authenticator = JwtAuthenticator(policy=selected, jwks_cache=cache)
    return MastermindTokenVerifier(
        authenticator=authenticator,
        policy=selected,
        now=now,
        audit_sink=audit_sink,
    )


class HttpxStudioForwarder:
    """Bounded HTTPS forwarding to one exact tailnet Studio route."""

    def __init__(self, upstream_url: object) -> None:
        self._url = _exact_tailnet_design_url(upstream_url)

    @property
    def upstream_url(self) -> str:
        return self._url

    async def call(
        self,
        *,
        method: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> UpstreamResult:
        if method not in {"POST", "DELETE"}:
            raise RuntimeError("upstream method refused")
        if not isinstance(body, bytes) or len(body) > MAX_REQUEST_BYTES:
            raise RuntimeError("upstream request refused")
        forwarded: dict[str, str] = {}
        for name, value in headers.items():
            lowered = str(name).lower()
            if lowered in _REQUEST_HEADER_ALLOWLIST and isinstance(value, str):
                forwarded[lowered] = value
        try:
            timeout = httpx.Timeout(UPSTREAM_TIMEOUT_SECONDS)
            async with httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=timeout,
            ) as client:
                async with client.stream(
                    method,
                    self._url,
                    content=body if method == "POST" else None,
                    headers=forwarded,
                ) as response:
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise RuntimeError("upstream response exceeded budget")
                        chunks.append(chunk)
                    result_headers = tuple(
                        (name.lower(), value)
                        for name, value in response.headers.items()
                        if name.lower() in _RESPONSE_HEADER_ALLOWLIST
                    )
                    return UpstreamResult(
                        status_code=response.status_code,
                        headers=result_headers,
                        body=b"".join(chunks),
                    )
        except RuntimeError:
            raise
        except Exception as error:
            raise RuntimeError("upstream unavailable") from error


def _header_values(request: Request, selected_name: str) -> list[str]:
    target = selected_name.lower().encode("ascii")
    values: list[str] = []
    for name, value in request.scope.get("headers", ()):
        if bytes(name).lower() != target:
            continue
        try:
            values.append(bytes(value).decode("ascii", errors="strict"))
        except UnicodeDecodeError:
            values.append("")
    return values


def _bearer_token(request: Request) -> str | None:
    values = _header_values(request, "authorization")
    if len(values) != 1:
        return None
    match = _BEARER_RE.fullmatch(values[0])
    return match.group(1) if match is not None else None


def _auth_challenge(policy: ResourcePolicy) -> str:
    return www_authenticate(policy, policy.required_scopes)


def create_studio_cloud_app(
    *,
    policy: ResourcePolicy,
    verifier: MastermindTokenVerifier,
    forwarder: StudioForwarder,
) -> Starlette:
    """Create an inert authenticated proxy over the existing Studio gateway."""

    selected, expected_host, resource_path = _validate_public_policy(policy)
    if not isinstance(verifier, MastermindTokenVerifier):
        raise _configuration("MastermindTokenVerifier is required")
    if validate_resource_policy(verifier._expected_policy) != selected:  # type: ignore[attr-defined]
        raise _configuration("auth verifier policy mismatch")
    if not callable(getattr(forwarder, "call", None)):
        raise _configuration("Studio forwarder is required")
    metadata_path = urlsplit(selected.resource_metadata_url).path

    async def metadata(request: Request) -> Response:
        raw_path = request.scope.get("raw_path", b"")
        if (
            request.method != "GET"
            or bytes(raw_path) != metadata_path.encode("ascii")
            or request.scope.get("query_string", b"")
        ):
            return Response(status_code=404)
        return JSONResponse(
            protected_resource_metadata(selected),
            headers={"cache-control": "no-store"},
        )

    async def mcp(request: Request) -> Response:
        raw_path = request.scope.get("raw_path", b"")
        if (
            bytes(raw_path) != resource_path.encode("ascii")
            or request.scope.get("query_string", b"")
            or request.method not in {"POST", "DELETE"}
        ):
            return Response(status_code=404)

        hosts = _header_values(request, "host")
        if len(hosts) != 1 or hosts[0].lower() != expected_host:
            return Response(status_code=421)

        token = _bearer_token(request)
        if token is None:
            return JSONResponse(
                {"error": "authentication_required"},
                status_code=401,
                headers={
                    "www-authenticate": _auth_challenge(selected),
                    "cache-control": "no-store",
                },
            )
        access, code = await verifier.verify_token_with_code(token)
        if access is None:
            status = 403 if code is AuthErrorCode.SCOPE_REFUSED else 401
            return JSONResponse(
                {"error": "authentication_refused"},
                status_code=status,
                headers={
                    "www-authenticate": _auth_challenge(selected),
                    "cache-control": "no-store",
                },
            )

        if request.method == "POST":
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > MAX_REQUEST_BYTES:
                        return Response(status_code=413)
                except ValueError:
                    return Response(status_code=400)
            body = await request.body()
            if len(body) > MAX_REQUEST_BYTES:
                return Response(status_code=413)
        else:
            body = b""

        request_headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() in _REQUEST_HEADER_ALLOWLIST
        }
        try:
            result = await forwarder.call(
                method=request.method,
                body=body,
                headers=request_headers,
            )
        except Exception:
            return JSONResponse(
                {"error": "studio_unavailable"},
                status_code=502,
                headers={"cache-control": "no-store"},
            )

        response_headers = {
            name: value
            for name, value in result.headers
            if name.lower() in _RESPONSE_HEADER_ALLOWLIST
        }
        return Response(
            result.body,
            status_code=result.status_code,
            headers=response_headers,
        )

    return Starlette(
        debug=False,
        routes=[
            Route(metadata_path, metadata, methods=["GET"]),
            Route(resource_path, mcp, methods=["POST", "DELETE"]),
        ],
    )


__all__ = [
    "HttpxStudioForwarder",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "STUDIO_DESIGN_SCOPE",
    "StudioCloudGatewayError",
    "UpstreamResult",
    "build_business_auth_verifier",
    "create_studio_cloud_app",
]
