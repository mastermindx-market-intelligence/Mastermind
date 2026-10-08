"""COO App composition over existing JWT, binding, readers and CeoIngress.

No credential acquisition, Runtime, grant defaults, or installation lives here.
Required authority/mission providers are trusted host inputs, never request data.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from common.executive_workspace_contract import _check_job_id
from control_plane.executive_runtime import JobStatus
from control_plane import executive_ceo_ingress as ingress
from control_plane.coo_principal_envelope import PrincipalAdmissionContext
from control_plane.coo_principal_mandate import AuthorityFact, PrincipalFact, project_coo_principal_mandate
from control_plane.coo_principal_request import principal_request_ref, principal_intent_id
from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA, AuthAuditEvent, AuthErrorCode, ResourcePolicy, VerifiedPrincipal, validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_mcp.coo import COO_READ_NAMES, COO_SERVER_VERSION, COO_TOOL_NAMES, validate_coo_tool_arguments
from integrations.executive_mcp.schemas import RESULT_SCHEMA, GatewayError, canonical_json
from integrations.executive_mcp.e1_http import BoundedE1App, MAX_RESPONSE_BYTES
from integrations.mastermind_executive_app.app import AppSettings, _authenticate, _outcome_response, _read_body_arguments
from integrations.mastermind_executive_app.admission import AdmissionOutcome, _classify_send_response
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES, coo_authorizer
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, CeoIngressResponse, WebCeoV2CeoIngressReadGateway,
    TRANSPORT_SENT_OK, TRANSPORT_NOT_SENT, _default_jwks_cache, _jwks_cache_contract,
    observe_ingress_grounding,
)


@dataclasses.dataclass(frozen=True)
class CooAppSettings:
    executive: AppSettings
    policy: ResourcePolicy
    load_binding: Callable[[], object]
    authority_provider: Callable[[VerifiedPrincipal, str], AuthorityFact]
    mission_provider: Callable[[VerifiedPrincipal, str], Mapping[str, Any]]

    def __post_init__(self):
        policy = validate_resource_policy(self.policy)
        base = self.executive
        if not isinstance(base, AppSettings) or not base.read_from_ceo_ingress or base.read_only:
            raise ValueError("COO requires the existing installed ingress readers")
        if (policy.required_scopes != COO_SCOPES
                or policy.policy_id in {base.policies.read.policy_id, base.policies.submit.policy_id}
                or policy.resource_metadata_url != base.policies.read.resource_metadata_url
                or _jwks_cache_contract(policy) != _jwks_cache_contract(base.policies.read)):
            raise ValueError("COO must share the Executive resource and JWKS, with distinct exact scopes")
        if not all(callable(x) for x in (self.load_binding, self.authority_provider, self.mission_provider)):
            raise ValueError("COO requires explicit installed binding and canonical fact providers")
        object.__setattr__(self, "policy", policy)


def refused(code="authority_refused", status=403):
    return JSONResponse({"ok": False, "error": {"code": code,
        "message": "COO authorization or canonical input is unavailable"}}, status_code=status)


def unknown(request_ref):
    return _outcome_response(AdmissionOutcome(status="effect_unknown", request_ref=request_ref,
        code="effect_unknown", message="Reconcile the original request reference before any further submission."))


def _receipt_shape(receipt):
    """Reassert network result shape; durable identity remains the sink's law."""
    def digest(value):
        return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None
    authority = receipt.get("authority")
    return (
        set(receipt) == {"schema", "intent_id", "request_ref", "fingerprint", "job_id", "status",
                         "accepted", "duplicate", "dispatched", "authority", "grounding", "created_at_ms", "principal"}
        and _check_job_id(receipt.get("job_id"))
        and receipt.get("status") in {item.value for item in JobStatus}
        and digest(receipt.get("fingerprint"))
        and type(receipt.get("created_at_ms")) is int and receipt["created_at_ms"] >= 0
        and ingress._coerce_grounding_shape(receipt.get("grounding")) is not None
        and isinstance(authority, dict)
        and set(authority) == {"requested", "policy_sha256", "authority_level"}
        and digest(authority.get("policy_sha256")) and authority.get("authority_level") == "A0"
        and authority.get("requested") in (["READ", "RESEARCH"], ["READ", "RUN_TESTS", "WRITE_BRANCH"])
    )


async def _owner_call(provider, *args):
    value = await asyncio.to_thread(provider, *args)
    return await value if inspect.isawaitable(value) else value


class CooApp:
    def __init__(self, settings: CooAppSettings, audit_sink):
        if type(settings) is not CooAppSettings or not callable(getattr(audit_sink, "emit", None)):
            raise ValueError("exact COO settings and existing audit sink required")
        self.settings = settings
        self._policy = validate_resource_policy(settings.policy)
        self.authenticator = JwtAuthenticator(policy=self._policy,
            jwks_cache=settings.executive.jwks_cache or _default_jwks_cache(self._policy))
        self.authorizer = coo_authorizer(policy=self._policy, load_binding=settings.load_binding)
        self._audit_sink = audit_sink
        self._client = CeoIngressClient(connect_timeout=settings.executive.connect_timeout,
                                       read_timeout=settings.executive.read_timeout)
        self._read_gateway = WebCeoV2CeoIngressReadGateway(settings.executive.ceo_ingress_socket_path, self._client)
        self._app = Starlette(routes=[Route("/v1/tools/{tool}", self.call, methods=["POST"])])
        self._app.router.redirect_slashes = False
        self._bounded = BoundedE1App(self._app)

    def _policy_current(self):
        return (validate_resource_policy(self.settings.policy) == self._policy
                and validate_resource_policy(self.authenticator.policy) == self._policy)

    async def authorize_token(self, token):
        """Additional exact binding check for the existing audited MCP verifier."""
        if not self._policy_current():
            raise ValueError("authority_refused")
        principal = await self.authenticator.verify_token(token, now=self.settings.executive.clock())
        stamp = self.authorizer.binding_digest(principal)
        if stamp is None or not self._policy_current():
            raise ValueError("authority_refused")
        return principal, stamp

    async def _auth(self, request):
        try:
            if not self._policy_current():
                return refused("internal_error", 500)
            principal = await _authenticate(request, self.authenticator, clock=self.settings.executive.clock)
            if isinstance(principal, JSONResponse):
                code = json.loads(principal.body).get("error", {}).get("code", "internal_error")
                code = AuthErrorCode(code).value
                self._audit_sink.emit(AuthAuditEvent(schema=AUTH_AUDIT_SCHEMA,
                    policy_id=self._policy.policy_id, code=code, accepted=False))
                return principal
            self._audit_sink.emit(AuthAuditEvent(schema=AUTH_AUDIT_SCHEMA,
                policy_id=self._policy.policy_id, code="accepted", accepted=True))
            stamp = self.authorizer.binding_digest(principal)
            return (principal, stamp) if stamp is not None and self._policy_current() else refused()
        except Exception:
            return refused("internal_error", 500)

    async def _authority(self, principal, work_ref, stamp):
        authority = await _owner_call(self.settings.authority_provider, principal, work_ref)
        if type(authority) is not AuthorityFact or authority.work_ref != work_ref:
            raise ValueError("authority_refused")
        authority = dataclasses.replace(authority)  # revalidate and detach provider-owned facts
        context = PrincipalAdmissionContext(work_ref=work_ref, principal_binding_digest=stamp,
            mission_authority_ref=authority.mission_authority_ref,
            authority_generation_digest=authority.authority_generation_digest)
        return authority, context

    async def _mandate(self, principal, stamp, authority):
        document = await _owner_call(self.settings.mission_provider, principal, authority.work_ref)
        fact = PrincipalFact(policy_id=principal.policy_id, issuer_digest=principal.issuer_digest,
            subject_digest=principal.subject_digest, client_ref=principal.client_ref,
            resource_ref=principal.resource, scopes=principal.scopes, principal_binding_digest=stamp)
        return project_coo_principal_mandate(principal=fact, authority=authority, mission_workspace=document)

    def _read_result(self, name, data):
        now = self.settings.executive.clock()
        if type(now) is not int:
            raise ValueError("clock unavailable")
        return {"schema": RESULT_SCHEMA, "tool": name, "ok": True,
            "server_version": COO_SERVER_VERSION, "mode": "readonly",
            "generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z"),
            "grounding": {}, "data": data, "degraded": [], "bounded": [], "error": None}

    async def _same_auth(self, request, expected):
        observed = await self._auth(request)
        return not isinstance(observed, JSONResponse) and observed == expected

    async def _send(self, frame, context, request_ref):
        try:
            response = await self._client.send_frame(self.settings.executive.ceo_ingress_socket_path, frame)
            if type(response) is not CeoIngressResponse:
                return unknown(request_ref)
            if response.transport == TRANSPORT_NOT_SENT:
                return _outcome_response(_classify_send_response(response, request_ref=request_ref))
            if response.transport != TRANSPORT_SENT_OK:
                return unknown(request_ref)
            if response.ok is False:
                error = response.error or {}
                if (error.get("code") not in ingress.ERROR_CODES or error.get("code") in {
                        "backend_unavailable", "backend_refused", "internal_error", "response_too_large"}):
                    # A backend failure may follow a committed effect; it is not
                    # proof of no Job, even when the error envelope is well formed.
                    return unknown(request_ref)
                response = dataclasses.replace(response, error={"code": error["code"],
                    "message": "The canonical Executive ingress refused this request."})
            elif response.ok is True:
                receipt = ingress._principal_receipt(response.result, context=context,
                    request_ref=request_ref, intent_id=principal_intent_id(request_ref))
                if (receipt.get("accepted") is not True or type(receipt.get("duplicate")) is not bool
                        or not _receipt_shape(receipt)):
                    return unknown(request_ref)
                canonical_json(receipt)
                response = dataclasses.replace(response, result=receipt)
            else:
                return unknown(request_ref)
            return _outcome_response(_classify_send_response(response, request_ref=request_ref))
        except Exception:
            # An unrecognized post-send failure never proves no effect.
            return unknown(request_ref)

    async def call(self, request: Request):
        name = request.path_params["tool"]
        if name not in COO_TOOL_NAMES:
            return refused("invalid_input", 404)
        authenticated = await self._auth(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        principal, stamp = authenticated
        arguments = await _read_body_arguments(request)
        if isinstance(arguments, JSONResponse):
            return arguments
        try:
            validated = validate_coo_tool_arguments(name, arguments)
        except GatewayError as exc:
            return refused(exc.code, 400)
        if name in COO_READ_NAMES:
            try:
                result = await self._read_gateway.call(name, validated)
                if not await self._same_auth(request, authenticated):
                    return refused()
                result = dict(result)
                result["server_version"] = COO_SERVER_VERSION
                return JSONResponse(result)
            except Exception:
                return refused("backend_unavailable", 503)
        work_ref = validated.get("work_ref", validated.get("workstream"))
        try:
            authority, context = await self._authority(principal, work_ref, stamp)
        except Exception:
            return refused("authority_refused", 403)
        if name == "submit_principal_intent" and "bounded_intent" not in authority.principal_actions:
            return refused("authority_refused", 403)
        if name == "executive_mandate":
            try:
                data = await self._mandate(principal, stamp, authority)
                if not await self._same_auth(request, authenticated):
                    return refused()
                return JSONResponse(self._read_result(name, data))
            except Exception:
                return refused("backend_unavailable", 503)
        is_submit = name == "submit_principal_intent"
        request_ref = principal_request_ref(validated) if is_submit else validated["request_ref"]
        frame = {"schema": ingress.PRINCIPAL_SUBMIT_SCHEMA if is_submit else ingress.PRINCIPAL_STATUS_SCHEMA,
                 "request_ref": request_ref, "principal_context": dataclasses.asdict(context)}
        if is_submit:
            try:
                frame["observed_grounding"] = await observe_ingress_grounding(
                    self._client, self.settings.executive.ceo_ingress_socket_path)
            except Exception:
                return refused("grounding_unavailable", 503)
            frame["request"] = validated
        # Dynamic mission/effect safety remains the mandatory final host guard.
        # A status read never calls a current-mission provider or new-effect gate.
        if not await self._same_auth(request, authenticated):
            return refused()
        result = await self._send(frame, context, request_ref)
        if not await self._same_auth(request, authenticated):
            return unknown(request_ref) if is_submit else refused()
        return result if len(result.body) <= MAX_RESPONSE_BYTES else unknown(request_ref)

    async def aclose(self):
        await self._read_gateway.aclose()

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if (not path.isascii() or scope.get("raw_path") != path.encode("ascii")
                    or scope.get("query_string") or scope.get("method") != "POST"
                    or path not in {"/v1/tools/" + name for name in COO_TOOL_NAMES}):
                await refused("invalid_input", 404)(scope, receive, send)
                return
        await self._bounded(scope, receive, send)


def create_coo_app(settings: CooAppSettings, *, audit_sink):
    """Build a same-process adapter, not a listener or an installed authority."""
    return CooApp(settings, audit_sink)
