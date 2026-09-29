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
from functools import partial
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
from integrations.executive_mcp.schemas import GatewayError, refuse_production_path
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
    CeoIngressReadGateway,
    WebCeoCeoIngressReadGateway,
    WebCeoV2CeoIngressReadGateway,
    make_jwt_authenticator_variants,
)
from integrations.executive_mcp.web_ceo import (
    build_web_ceo_read_gateway,
    build_web_ceo_v2_read_gateway,
    web_ceo_tool_names,
    web_ceo_v2_tool_names,
)
from integrations.executive_mcp.web_ceo_v3 import web_ceo_v3_tool_names
from integrations.mosyle_mdm.executive import WebCeoV3CeoIngressReadGateway

__all__ = [
    "AppSettings",
    "create_app",
    "create_web_ceo_app",
    "create_web_ceo_v2_app",
    "create_web_ceo_v3_app",
    "create_release_control_app",
]

_MAX_BODY_BYTES = 65536


def _refuse_read_only_production_path(value: "Path | str", field: str) -> None:
    """Keep direct E1 app construction out of installed Executive OS trees."""

    try:
        normalized = refuse_production_path(str(value), field)
        refuse_production_path(str(Path(normalized).resolve()), field)
    except GatewayError as exc:
        raise ValueError("read_only app refuses production configuration path") from exc


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
    path = urlsplit(read_policy.resource_metadata_url).path or "/"
    if (
        "%" in path
        or "//" in path
        or any(segment in {".", ".."} for segment in path.split("/"))
    ):
        raise ValueError("metadata policy route is not safely serveable")
    if path == "/v1/tools" or path.startswith("/v1/tools/"):
        raise ValueError("metadata policy route collides with reserved tool namespace")
    return read_policy, path


@dataclasses.dataclass(frozen=True)
class AppSettings:
    """Everything one running app process needs.  No caller input reaches
    any field here — every one is host/operator configuration."""

    policies: AppPolicies
    mastermind_root: "Path | str"
    macro_root_flag: str | None
    environ: Mapping[str, str]
    ceo_ingress_socket_path: "Path | str | None"
    #: E1 sets this immutable capability flag.  Legacy direct callers retain
    #: the existing writer-capable route surface by default.
    read_only: bool = False
    #: Native five-tool MCP can receive a token upgraded to the exact submit
    #: policy. This opt-in verifies that policy in full on reader routes;
    #: legacy HTTP and temporary E1 retain their exact read-only policy.
    allow_submit_authorized_reads: bool = False
    #: Installed composition reads only through the existing CeoIngress.
    read_from_ceo_ingress: bool = False
    #: Additional exact OAuth resource variants for the same Executive app.
    #: Each variant must be identical to ``policies`` except for ``resource``.
    #: The tuple is host/operator configuration; request data never reaches it.
    additional_policies: tuple[AppPolicies, ...] = ()
    #: E1's temporary runtime projection root.  It is required only for the
    #: read-only capability and never comes from a request body.
    runtime_root: "Path | str | None" = None
    #: ``None`` lets :func:`create_app` build bounded production JWKS cache
    #: state, sharing one generation when read and submit have the same JWKS
    #: authority/refresh contract. Native MCP may inject that same cache here
    #: so its outer and inner auth layers reuse one generation. Tests can also
    #: inject a stateless fake.
    jwks_cache: JwksKeySource | None = None
    clock: Callable[[], int] = lambda: int(time.time())
    connect_timeout: float = 5.0
    read_timeout: float = 10.0

    def __post_init__(self) -> None:
        if type(self.additional_policies) is not tuple or any(
            type(item) is not AppPolicies for item in self.additional_policies
        ):
            raise ValueError("additional_policies must be a tuple of AppPolicies")
        resources = {self.policies.read.resource}
        for alternate in self.additional_policies:
            _metadata_policy_and_path(alternate)
            if alternate.read.resource in resources:
                raise ValueError("Executive OAuth resources must be unique")
            resources.add(alternate.read.resource)
            for name in ("read", "submit"):
                primary_policy = getattr(self.policies, name)
                alternate_policy = getattr(alternate, name)
                if dataclasses.replace(
                    alternate_policy, resource=primary_policy.resource
                ) != primary_policy:
                    raise ValueError(
                        "additional Executive policies may differ only by resource"
                    )
        if type(self.read_only) is not bool:
            raise ValueError("read_only must be a bool")
        if type(self.allow_submit_authorized_reads) is not bool:
            raise ValueError("allow_submit_authorized_reads must be a bool")
        if self.read_only and self.allow_submit_authorized_reads:
            raise ValueError("read_only app refuses submit-authorized reads")
        if type(self.read_from_ceo_ingress) is not bool:
            raise ValueError("read_from_ceo_ingress must be a bool")
        if self.read_from_ceo_ingress and (self.read_only or self.runtime_root is not None):
            raise ValueError("installed reads refuse temporary E1/runtime configuration")
        if self.read_only:
            if self.ceo_ingress_socket_path is not None:
                raise ValueError("read_only app refuses an ingress socket path")
            if self.runtime_root is None:
                raise ValueError("read_only app requires runtime_root")
            if self.macro_root_flag is None:
                raise ValueError("read_only app requires macro_root_flag")
            for field, value in (
                ("mastermind_root", self.mastermind_root),
                ("macro_root_flag", self.macro_root_flag),
                ("runtime_root", self.runtime_root),
            ):
                _refuse_read_only_production_path(value, field)
        elif self.ceo_ingress_socket_path is None:
            raise ValueError("legacy app requires an ingress socket path")


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


def _authenticator_tuple(
    value: JwtAuthenticator | tuple[JwtAuthenticator, ...],
) -> tuple[JwtAuthenticator, ...]:
    if isinstance(value, JwtAuthenticator):
        return (value,)
    if type(value) is not tuple or not value or any(
        not isinstance(item, JwtAuthenticator) for item in value
    ):
        raise TypeError("authenticator set must contain JwtAuthenticator values")
    return value


async def _verify_exact_resource_set(
    authenticators: JwtAuthenticator | tuple[JwtAuthenticator, ...],
    header: object,
    *,
    now: int,
) -> VerifiedPrincipal:
    """Verify one token against a closed set of exact resource policies.

    Only ``resource_refused`` advances to the next resource variant. Any
    signature, issuer, lifetime, subject, scope, key, or internal refusal is
    terminal because those contracts are identical across admitted variants.
    """

    values = _authenticator_tuple(authenticators)
    last_resource_error: AuthError | None = None
    for value in values:
        try:
            return await value.verify_authorization_header(header, now=now)
        except AuthError as exc:
            if exc.code.value != "resource_refused" or len(values) == 1:
                raise
            last_resource_error = exc
    if last_resource_error is None:
        raise RuntimeError("resource authenticator set produced no result")
    raise last_resource_error


async def _authenticate(
    request: Request,
    authenticator: JwtAuthenticator | tuple[JwtAuthenticator, ...],
    *,
    clock: Callable[[], int],
    submit_fallback: JwtAuthenticator | tuple[JwtAuthenticator, ...] | None = None,
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
    active = authenticator
    try:
        try:
            return await _verify_exact_resource_set(active, header, now=now)
        except AuthError as exc:
            if submit_fallback is None or exc.code.value != "scope_refused":
                raise
            active = submit_fallback
            return await _verify_exact_resource_set(active, header, now=now)
    except AuthError as exc:
        challenge_policy = _authenticator_tuple(active)[0].policy
        challenge = mcp_auth_error_result(challenge_policy, exc)
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

    def __init__(self, app: Any, *, metadata_path: str, read_gateway: Any) -> None:
        self._app = app
        self._metadata_path = metadata_path
        self._read_gateway = read_gateway

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

    async def aclose(self) -> None:
        """Close the one read gateway owned by this direct app instance."""

        await self._read_gateway.aclose()


def _create_profile_app(
    settings: AppSettings,
    *,
    read_tool_names: tuple[str, ...],
    ingress_gateway_type: type[CeoIngressReadGateway],
    read_gateway_builder: Callable[..., Any],
    prereply_reverify: bool = False,
    release_control_profile: bool = False,
) -> Any:
    """Build one stateless ASGI app from one compile-time selected profile.

    A fresh instance is cheap and holds no state beyond ``settings`` itself
    (plus the two verified-at-construction :class:`JwtAuthenticator`s), so a
    restart never loses anything (§ Data/time/null: no app-local IDs, no
    session rows, no token cache, no job mirror, no result store).

    ``prereply_reverify`` selects the static Web-CEO v2 law only: the same
    company-read authenticator runs again after the read and before the reply,
    and must verify the request to the exact same immutable
    :class:`VerifiedPrincipal`.  Legacy profiles keep the historical single
    before-invoke verifier call, byte for byte.
    """

    if release_control_profile and (settings.read_only or not settings.read_from_ceo_ingress):
        raise ValueError("release controls require the installed authenticated ingress")
    metadata_policy, metadata_path = _metadata_policy_and_path(settings.policies)
    authenticator_variants = make_jwt_authenticator_variants(
        settings.policies,
        settings.additional_policies,
        primary_jwks_cache=settings.jwks_cache,
    )
    if len(authenticator_variants) == 1:
        read_authenticator, submit_authenticator = authenticator_variants[0]
    else:
        read_authenticator = tuple(pair[0] for pair in authenticator_variants)
        submit_authenticator = tuple(pair[1] for pair in authenticator_variants)
    ceo_ingress_client = None
    if not settings.read_only:
        ceo_ingress_client = CeoIngressClient(
            connect_timeout=settings.connect_timeout, read_timeout=settings.read_timeout
        )
    if settings.read_from_ceo_ingress:
        read_gateway = ingress_gateway_type(
            settings.ceo_ingress_socket_path, ceo_ingress_client
        )
    else:
        read_gateway = read_gateway_builder(
            settings.mastermind_root,
            macro_root_flag=settings.macro_root_flag,
            runtime_root=settings.runtime_root,
        )

    async def call_read_tool(request: Request) -> JSONResponse:
        tool_name = request.path_params["tool_name"]
        if tool_name not in read_tool_names:
            return JSONResponse(
                {"ok": False, "error": {"code": "not_found", "message": f"unknown tool {tool_name!r}"}},
                status_code=404,
            )
        principal_or_response = await _authenticate(
            request, read_authenticator, clock=settings.clock,
            submit_fallback=(submit_authenticator if settings.allow_submit_authorized_reads else None),
        )
        if isinstance(principal_or_response, JSONResponse):
            return principal_or_response
        principal = principal_or_response
        arguments = await _read_body_arguments(request)
        if isinstance(arguments, JSONResponse):
            return arguments
        envelope = await read_gateway.call(tool_name, arguments)
        if prereply_reverify:
            # Pre-reply reverify (static Web-CEO v2 only): the SAME
            # company-read authenticator must still verify this request to
            # the SAME immutable principal.  A real owner expiry, refusal, or
            # changed principal discards the already-read data and denies
            # closed; no synthetic root-ACL or revocation-policy claim is
            # made here, and legacy profiles never enter this branch.
            recheck_or_response = await _authenticate(
                request, read_authenticator, clock=settings.clock,
                submit_fallback=(submit_authenticator if settings.allow_submit_authorized_reads else None),
            )
            if isinstance(recheck_or_response, JSONResponse):
                return recheck_or_response
            if recheck_or_response != principal:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": {
                            "code": "identity_unverified",
                            "message": "read authorization did not re-verify to the "
                            "same principal; response withheld",
                        },
                    },
                    status_code=401,
                )
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
            read_grounding_from_ingress=settings.read_from_ceo_ingress,
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

    async def call_release_tool(request: Request) -> JSONResponse:
        from control_plane.executive_release_ingress import ReleaseIngressError
        from integrations.business_mcp_auth.principal_projection import PrincipalProjectionError
        from integrations.mastermind_executive_app.release_admission import compose_release_admission
        principal = await _authenticate(request, submit_authenticator, clock=settings.clock)
        if isinstance(principal, JSONResponse):
            return principal
        raw = await request.body()
        if len(raw) > _MAX_BODY_BYTES:
            return JSONResponse({"ok": False, "error": {"code": "RELEASE_FRAME_TOO_LARGE"}}, status_code=413)
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result
        def reject_number(_):
            raise ValueError("unsupported number")
        try:
            body = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                              parse_float=reject_number, parse_constant=reject_number)
            if type(body) is not dict or set(body) != {"arguments"}:
                raise ValueError("invalid envelope")
        except (ValueError, UnicodeError, RecursionError):
            return JSONResponse({"ok": False, "error": {"code": "RELEASE_ARGUMENTS_INVALID"}}, status_code=400)
        # The route owns the operation. A model cannot choose a principal or
        # replace it with a projection in its tool arguments.
        operation = request.url.path.rsplit("/", 1)[-1]
        try:
            result = await compose_release_admission(
                operation=operation, arguments=body["arguments"], principal=principal,
                client=ceo_ingress_client, socket_path=settings.ceo_ingress_socket_path,
            )
        except (ReleaseIngressError, PrincipalProjectionError):
            return JSONResponse({"ok": False, "error": {"code": "RELEASE_ARGUMENTS_INVALID"}}, status_code=400)
        return JSONResponse(result, status_code=202 if result.get("effect") == "EFFECT_UNKNOWN" else 200)

    async def protected_resource_document(request: Request) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(metadata_policy), status_code=200)

    routes = [
        Route(metadata_path, protected_resource_document, methods=["GET"]),
        Route("/v1/tools/{tool_name}", call_read_tool, methods=["POST"]),
    ]
    if not settings.read_only:
        routes[1:1] = [
            Route("/v1/tools/submit_ceo_intent/reconcile", reconcile_submit_tool, methods=["POST"]),
            Route("/v1/tools/submit_ceo_intent", call_submit_tool, methods=["POST"]),
        ]
    if release_control_profile:
        from control_plane.executive_release_ingress import OPERATIONS as RELEASE_OPERATIONS
        routes[1:1] = [Route("/v1/tools/" + name, call_release_tool, methods=["POST"])
                       for name in sorted(RELEASE_OPERATIONS)]
    application = Starlette(routes=routes)
    # Never implicitly rewrite a trailing-slash alias onto a different route:
    # an encoded/trailing-slash/raw-path ambiguity must refuse as a plain
    # 404, never be silently redirected before auth has even run.
    application.router.redirect_slashes = False
    return _RawPathFence(
        application,
        metadata_path=metadata_path,
        read_gateway=read_gateway,
    )

def create_app(settings: AppSettings) -> Any:
    """Legacy BSC-E1 app; exact v1 read/tool surface remains frozen."""

    return _create_profile_app(
        settings,
        read_tool_names=READ_TOOL_NAMES,
        ingress_gateway_type=CeoIngressReadGateway,
        read_gateway_builder=build_read_gateway,
    )


def create_web_ceo_app(settings: AppSettings) -> Any:
    """Separately versioned Web-CEO app over the same auth/admission owners."""

    read_names = tuple(
        name for name in web_ceo_tool_names() if name != "submit_ceo_intent"
    )
    return _create_profile_app(
        settings,
        read_tool_names=read_names,
        ingress_gateway_type=WebCeoCeoIngressReadGateway,
        read_gateway_builder=build_web_ceo_read_gateway,
    )


def create_web_ceo_v2_app(settings: AppSettings) -> Any:
    """Static Web-CEO v2 app (App-read v3, server 1.2.0, pre-reply reverify)."""

    read_names = tuple(
        name for name in web_ceo_v2_tool_names() if name != "submit_ceo_intent"
    )
    return _create_profile_app(
        settings,
        read_tool_names=read_names,
        ingress_gateway_type=WebCeoV2CeoIngressReadGateway,
        read_gateway_builder=build_web_ceo_v2_read_gateway,
        prereply_reverify=True,
    )


def create_web_ceo_v3_app(settings: AppSettings, *, mdm_reader: Any) -> Any:
    """Installed Web-CEO v3: v2 Executive reads plus local MDM observation."""

    if not settings.read_from_ceo_ingress:
        raise ValueError("Web CEO v3 is installed-only")
    read_names = tuple(
        name for name in web_ceo_v3_tool_names() if name != "submit_ceo_intent"
    )
    gateway = partial(WebCeoV3CeoIngressReadGateway, mdm_reader=mdm_reader)
    return _create_profile_app(
        settings,
        read_tool_names=read_names,
        ingress_gateway_type=gateway,
        read_gateway_builder=build_web_ceo_v2_read_gateway,
        prereply_reverify=True,
    )


def create_release_control_app(settings: AppSettings) -> Any:
    """Separate installed release profile; old tool profiles remain frozen.

    Route visibility does not enable owner approval or preparation. Installed
    same-process qualification and root-owner policy remain Control's gates;
    release commit is unconditionally disarmed in the C1 consumer.
    """
    read_names = tuple(name for name in web_ceo_v2_tool_names() if name != "submit_ceo_intent")
    return _create_profile_app(
        settings, read_tool_names=read_names,
        ingress_gateway_type=WebCeoV2CeoIngressReadGateway,
        read_gateway_builder=build_web_ceo_v2_read_gateway,
        prereply_reverify=True, release_control_profile=True,
    )
