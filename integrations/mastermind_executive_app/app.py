"""integrations.mastermind_executive_app.app — the stateless ASGI edge.

Exposes the existing five-tool Executive MCP contract over plain
bearer-authenticated HTTP:

* ``POST /v1/tools/{name}`` for the four read tools
  (:data:`gateway.READ_TOOL_NAMES`) — reused verbatim through
  ``integrations.executive_mcp.adapter.ExecutiveMcpGateway``.
* ``POST /v1/tools/submit_ceo_intent`` — the ONE modifying tool, admitted
  ONLY through :mod:`integrations.mastermind_executive_app.admission`
  (dedicated CeoIngress socket, never in-process, never the general
  Executive control socket).
* ``POST /v1/tools/submit_ceo_intent/reconcile`` — the ONLY legal follow-up
  to an ``effect_unknown`` outcome: a v2 status read keyed by the same
  ``request_ref``, never a resubmission.

This module holds NO durable state, NO in-memory session/job table, and NO
token cache: every request is verified from scratch (restart-safe by
construction — there is nothing to lose on restart). It never imports the MCP
SDK, ``control_plane.executive_service``, or
``control_plane.ceo_intent.submit_intent``.
"""
from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from control_plane.ceo_request import AUTOMATED_REQUEST_REF_RE
from integrations.business_mcp_auth.contracts import (
    AuthError,
    ResourcePolicy,
    VerifiedPrincipal,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwksKeySource, JwtAuthenticator
from integrations.business_mcp_auth.metadata import mcp_auth_error_result, protected_resource_metadata
from integrations.mastermind_executive_app.admission import (
    STATUS_ACCEPTED,
    STATUS_CONFLICT,
    STATUS_EFFECT_UNKNOWN,
    STATUS_REFUSED,
    STATUS_TRANSPORT_UNAVAILABLE,
    AdmissionError,
    AdmissionOutcome,
    AdmissionRequest,
    compose_admission,
    reconcile_by_request_ref,
)
from integrations.mastermind_executive_app.gateway import (
    READ_TOOL_NAMES,
    AppPolicies,
    CeoIngressClient,
    build_read_gateway,
    make_jwt_authenticators,
)

__all__ = ["AppSettings", "create_app"]

_MAX_BODY_BYTES = 65536


def _metadata_policy_and_path(policies: AppPolicies) -> tuple[ResourcePolicy, str]:
    """Return the one public metadata policy and its exact validated path.

    The app has separate read and submit scopes, but one OAuth resource-server
    identity.  Revalidate both immutable-looking policy objects because a
    frozen dataclass can still be manually forged before process construction.
    """

    try:
        read_policy = validate_resource_policy(policies.read)
        submit_policy = validate_resource_policy(policies.submit)
    except AuthError as exc:
        raise ValueError("metadata policy refused") from exc
    identity = (
        "resource",
        "resource_metadata_url",
        "issuer",
        "authorization_servers",
    )
    if any(getattr(read_policy, name) != getattr(submit_policy, name) for name in identity):
        raise ValueError("read and submit policies must name the same resource identity")
    path = urlsplit(read_policy.resource_metadata_url).path
    if not path:
        raise ValueError("metadata policy must include an exact route path")
    return read_policy, path


@dataclasses.dataclass(frozen=True)
class AppSettings:
    """Everything one running app process needs.  No caller input reaches
    any field here — every one is host/operator configuration."""

    policies: AppPolicies
    mastermind_root: "Path | str"
    macro_root_flag: str | None
    environ: Mapping[str, str]
    ceo_ingress_socket_path: "Path | str"
    #: ``None`` (the production default) builds one independent
    #: ``BoundedJwksCache`` per policy inside :func:`create_app`; tests inject
    #: a single stateless fake here instead.
    jwks_cache: JwksKeySource | None = None
    clock: Callable[[], int] = lambda: int(time.time())
    connect_timeout: float = 5.0
    read_timeout: float = 10.0


class _AmbiguousAuthorizationHeader(Exception):
    """Raised when a request carries more than one Authorization header.

    Never silently picks the first (or last) value: an ambiguous request is
    refused outright, before any bearer token is even looked at, so no
    header-smuggling ambiguity can ever reach the JWT verifier.
    """


def _auth_header(request: Request) -> str | None:
    values = request.headers.getlist("authorization")
    if len(values) > 1:
        raise _AmbiguousAuthorizationHeader
    return values[0] if values else None


async def _authenticate(
    request: Request, authenticator: JwtAuthenticator, *, clock: Callable[[], int]
) -> VerifiedPrincipal | JSONResponse:
    now = clock()
    if type(now) is not int:
        return JSONResponse(
            {"ok": False, "error": {"code": "internal_error", "message": "authentication clock is unavailable"}},
            status_code=500,
        )
    try:
        header = _auth_header(request)
    except _AmbiguousAuthorizationHeader:
        return JSONResponse(
            {"ok": False, "error": {"code": "authorization_malformed", "message": "authentication required"}},
            status_code=401,
        )
    try:
        return await authenticator.verify_authorization_header(header, now=now)
    except AuthError as exc:
        challenge = mcp_auth_error_result(authenticator.policy, exc)
        header_value = challenge["_meta"]["mcp/www_authenticate"][0]
        status_code = 403 if exc.code.value == "scope_refused" else 401
        return JSONResponse(
            {"ok": False, "error": {"code": exc.code.value, "message": exc.public_message}},
            status_code=status_code,
            headers={"WWW-Authenticate": header_value},
        )


async def _read_body_arguments(request: Request) -> dict[str, Any] | JSONResponse:
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return JSONResponse(
            {"ok": False, "error": {"code": "invalid_input", "message": "request body too large"}},
            status_code=413,
        )
    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return JSONResponse(
            {"ok": False, "error": {"code": "invalid_input", "message": "request body must be JSON"}},
            status_code=400,
        )
    if not isinstance(parsed, dict) or set(parsed) - {"arguments"}:
        return JSONResponse(
            {"ok": False, "error": {"code": "invalid_input", "message": "body must contain exactly {\"arguments\": {...}}"}},
            status_code=400,
        )
    arguments = parsed.get("arguments", {})
    if not isinstance(arguments, dict):
        return JSONResponse(
            {"ok": False, "error": {"code": "invalid_input", "message": "arguments must be an object"}},
            status_code=400,
        )
    return arguments


def _outcome_response(outcome: AdmissionOutcome) -> JSONResponse:
    body: dict[str, Any] = {
        "ok": outcome.status == STATUS_ACCEPTED,
        "status": outcome.status,
        "request_ref": outcome.request_ref,
    }
    if outcome.receipt is not None:
        body["receipt"] = outcome.receipt
    if outcome.code is not None:
        body["error"] = {"code": outcome.code, "message": outcome.message}
    status_code = {
        STATUS_ACCEPTED: 200,
        STATUS_CONFLICT: 409,
        STATUS_REFUSED: 200,
        STATUS_TRANSPORT_UNAVAILABLE: 503,
        STATUS_EFFECT_UNKNOWN: 202,
    }.get(outcome.status, 500)
    return JSONResponse(body, status_code=status_code)


#: Percent-encoded (or alternate) path separators that must never be
#: silently decoded into a route-altering "/" by the router underneath this
#: fence.  Checked against the RAW (undecoded) ASGI path bytes, before
#: Starlette's router ever sees a decoded path -- this is what keeps
#: ``/v1/tools/submit_ceo_intent%2Freconcile`` from aliasing onto the
#: literal ``/v1/tools/submit_ceo_intent/reconcile`` route.
_SUSPICIOUS_RAW_PATH_MARKERS = (b"%2f", b"%5c", b"//")


class _RawPathFence:
    """ASGI wrapper refusing any HTTP request whose raw path bytes contain an
    encoded/alternate separator, before routing or authentication ever runs.
    """

    def __init__(self, app: Any, *, metadata_path: str) -> None:
        self._app = app
        self._metadata_path = metadata_path

    async def __call__(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            raw_path = scope.get("raw_path") or b""
            lowered = bytes(raw_path).lower()
            if any(marker in lowered for marker in _SUSPICIOUS_RAW_PATH_MARKERS):
                response = JSONResponse(
                    {
                        "ok": False,
                        "error": {
                            "code": "invalid_input",
                            "message": "path contains an unsupported encoded separator",
                        },
                    },
                    status_code=400,
                )
                await response(scope, receive, send)
                return
            if (
                scope.get("path") == self._metadata_path
                and (scope.get("method") != "GET" or scope.get("query_string"))
            ):
                response = JSONResponse(
                    {"ok": False, "error": {"code": "not_found", "message": "not found"}},
                    status_code=404,
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def create_app(settings: AppSettings) -> Any:
    """Build one stateless ASGI app instance from ``settings``.

    A fresh instance is cheap and holds no state beyond ``settings`` itself
    (plus the two verified-at-construction :class:`JwtAuthenticator`s), so a
    restart never loses anything (§ Data/time/null: no app-local IDs, no
    session rows, no token cache, no job mirror, no result store).
    """

    metadata_policy, metadata_path = _metadata_policy_and_path(settings.policies)
    read_authenticator, submit_authenticator = make_jwt_authenticators(
        settings.policies, jwks_cache=settings.jwks_cache
    )
    read_gateway = build_read_gateway(settings.mastermind_root)
    ceo_ingress_client = CeoIngressClient(
        connect_timeout=settings.connect_timeout, read_timeout=settings.read_timeout
    )

    async def call_read_tool(request: Request) -> JSONResponse:
        tool_name = request.path_params["tool_name"]
        if tool_name not in READ_TOOL_NAMES:
            return JSONResponse(
                {"ok": False, "error": {"code": "not_found", "message": f"unknown tool {tool_name!r}"}},
                status_code=404,
            )
        principal_or_response = await _authenticate(
            request, read_authenticator, clock=settings.clock
        )
        if isinstance(principal_or_response, JSONResponse):
            return principal_or_response
        arguments = await _read_body_arguments(request)
        if isinstance(arguments, JSONResponse):
            return arguments
        envelope = await read_gateway.call(tool_name, arguments)
        return JSONResponse(envelope, status_code=200)

    async def call_submit_tool(request: Request) -> JSONResponse:
        principal_or_response = await _authenticate(
            request, submit_authenticator, clock=settings.clock
        )
        if isinstance(principal_or_response, JSONResponse):
            return principal_or_response
        principal = principal_or_response
        arguments = await _read_body_arguments(request)
        if isinstance(arguments, JSONResponse):
            return arguments
        admission_request = AdmissionRequest(
            payload=arguments,
            principal=principal,
            ceo_ingress_socket_path=settings.ceo_ingress_socket_path,
            mastermind_root=settings.mastermind_root,
            macro_root_flag=settings.macro_root_flag,
            environ=settings.environ,
            client=ceo_ingress_client,
        )
        try:
            outcome = await compose_admission(admission_request)
        except AdmissionError as exc:
            status_code = 403 if exc.code == "authority_refused" else 400
            return JSONResponse(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                status_code=status_code,
            )
        return _outcome_response(outcome)

    async def reconcile_submit_tool(request: Request) -> JSONResponse:
        principal_or_response = await _authenticate(
            request, submit_authenticator, clock=settings.clock
        )
        if isinstance(principal_or_response, JSONResponse):
            return principal_or_response
        body = await request.body()
        try:
            parsed = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, ValueError):
            parsed = None
        request_ref = parsed.get("request_ref") if isinstance(parsed, dict) else None
        if not isinstance(request_ref, str) or AUTOMATED_REQUEST_REF_RE.fullmatch(request_ref) is None:
            return JSONResponse(
                {"ok": False, "error": {"code": "invalid_input", "message": "request_ref must be a valid AD-ID1 reference"}},
                status_code=400,
            )
        try:
            outcome = await reconcile_by_request_ref(
                ceo_ingress_client,
                socket_path=settings.ceo_ingress_socket_path,
                request_ref=request_ref,
            )
        except AdmissionError as exc:
            return JSONResponse(
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                status_code=400,
            )
        return _outcome_response(outcome)

    async def protected_resource_document(request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(metadata_policy), status_code=200)

    routes = [
        Route(metadata_path, protected_resource_document, methods=["GET"]),
        Route("/v1/tools/submit_ceo_intent/reconcile", reconcile_submit_tool, methods=["POST"]),
        Route("/v1/tools/submit_ceo_intent", call_submit_tool, methods=["POST"]),
        Route("/v1/tools/{tool_name}", call_read_tool, methods=["POST"]),
    ]
    application = Starlette(routes=routes)
    # Never implicitly rewrite a trailing-slash alias onto a different route:
    # an encoded/trailing-slash/raw-path ambiguity must refuse as a plain
    # 404, never be silently redirected before auth has even run.
    application.router.redirect_slashes = False
    return _RawPathFence(application, metadata_path=metadata_path)
