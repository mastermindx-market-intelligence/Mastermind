"""Dormant VPS service App profile over existing OAuth, CeoIngress and Fabric readers.

Host enrollment supplies the exact service subject/client binding. No credential
acquisition, Runtime construction, provider selection or installation lives here.
"""
import asyncio
import dataclasses
import json
import re
from collections.abc import Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from control_plane import executive_inference_ingress as ingress
from control_plane.executive_inference_contract import (
    PRINCIPAL_ID, TOOLS, intent_id, validate_receipt, validate_submission_receipt, validate_status,
)
from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA, AuthAuditEvent, ResourcePolicy, validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.executive_mcp.e1_http import BoundedE1App, MAX_RESPONSE_BYTES
from integrations.mastermind_executive_app.app import AppSettings, _authenticate, _read_body_arguments, _outcome_response
from integrations.mastermind_executive_app.admission import AdmissionOutcome, _classify_send_response
from integrations.mastermind_executive_app.coo_binding import principal_frame
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, CeoIngressResponse, WebCeoV2CeoIngressReadGateway,
    _default_jwks_cache, _jwks_cache_contract, observe_ingress_grounding,
)

from integrations.executive_mcp.inference import validate_arguments, validate_result

SERVICE_SCOPE = "mastermind.executive.service.inference"


@dataclasses.dataclass(frozen=True)
class InferenceSettings:
    executive: AppSettings
    policy: ResourcePolicy
    load_binding: Callable[[], object]

    def __post_init__(self):
        policy = validate_resource_policy(self.policy)
        base = self.executive
        if (type(base) is not AppSettings or not base.read_from_ceo_ingress or base.read_only
                or policy.required_scopes != (SERVICE_SCOPE,)
                or policy.policy_id in {base.policies.read.policy_id, base.policies.submit.policy_id}
                or policy.resource_metadata_url != base.policies.read.resource_metadata_url
                or _jwks_cache_contract(policy) != _jwks_cache_contract(base.policies.read)
                or set(policy.allowed_subject_digests) & (
                    set(base.policies.read.allowed_subject_digests) | set(base.policies.submit.allowed_subject_digests))
                or not callable(self.load_binding)):
            raise ValueError("distinct enrolled service policy and installed ingress required")
        object.__setattr__(self, 'policy', policy)


def refused(code='authority_refused', status=403):
    return JSONResponse({'ok': False, 'error': {'code': code, 'message': 'Service request unavailable or refused'}}, status_code=status)


def unknown(operation_key):
    return _outcome_response(AdmissionOutcome(status='effect_unknown', request_ref=intent_id(operation_key),
        code='effect_unknown', message='Reconcile this same operation_key; do not resubmit.'))


class InferenceApp:
    def __init__(self, settings, audit_sink):
        if type(settings) is not InferenceSettings or not callable(getattr(audit_sink, 'emit', None)):
            raise ValueError('service settings and audit sink required')
        self.settings = settings
        self._policy = settings.policy
        self._audit_sink = audit_sink
        self.authenticator = JwtAuthenticator(policy=self._policy,
            jwks_cache=settings.executive.jwks_cache or _default_jwks_cache(self._policy))
        self._client = CeoIngressClient(connect_timeout=settings.executive.connect_timeout,
                                       read_timeout=settings.executive.read_timeout)
        self._reader = WebCeoV2CeoIngressReadGateway(settings.executive.ceo_ingress_socket_path, self._client)
        app = Starlette(routes=[Route('/v1/tools/{tool}', self.call, methods=['POST'])])
        app.router.redirect_slashes = False
        self._bounded = BoundedE1App(app)

    def _enrolled(self, principal):
        if (validate_resource_policy(self.settings.policy) != self._policy
                or validate_resource_policy(self.authenticator.policy) != self._policy):
            return False
        expected = dict(principal_frame(principal), principal_id=PRINCIPAL_ID, principal_kind='service')
        return (re.fullmatch(r'[0-9a-f]{64}', principal.client_ref) is not None
                and self.settings.load_binding() == expected)

    async def authorize_token(self, token):
        principal = await self.authenticator.verify_token(token, now=self.settings.executive.clock())
        if not self._enrolled(principal):
            raise ValueError('authority_refused')
        return principal

    async def _auth(self, request):
        try:
            if (validate_resource_policy(self.settings.policy) != self._policy
                    or validate_resource_policy(self.authenticator.policy) != self._policy):
                return refused()
            principal = await _authenticate(request, self.authenticator, clock=self.settings.executive.clock)
            if isinstance(principal, JSONResponse):
                code = json.loads(principal.body)['error']['code']
                self._audit_sink.emit(AuthAuditEvent(AUTH_AUDIT_SCHEMA, self._policy.policy_id, code, False))
                return principal
            # Existing verifier hashes the OAuth client; absent client identity cannot enroll.
            if not self._enrolled(principal):
                self._audit_sink.emit(AuthAuditEvent(AUTH_AUDIT_SCHEMA, self._policy.policy_id, 'token_claims_refused', False))
                return refused()
            self._audit_sink.emit(AuthAuditEvent(AUTH_AUDIT_SCHEMA, self._policy.policy_id, 'accepted', True))
            return principal
        except Exception:
            return refused('internal_error', 500)

    async def _send(self, frame, operation):
        try:
            terminal_ref = None
            response = await self._client.send_frame(self.settings.executive.ceo_ingress_socket_path, frame)
            if type(response) is not CeoIngressResponse:
                return unknown(operation)
            if response.transport not in {'sent_ok', 'not_sent'}:
                return unknown(operation)
            if response.transport == 'sent_ok':
                if response.ok is True:
                    if frame["schema"] == ingress.STATUS_SCHEMA:
                        status = validate_status(response.result, operation)
                        terminal_ref = status["terminal_result_ref"]
                        response = dataclasses.replace(response, result=status["receipt"])
                    validate_receipt(response.result, operation)
                    if frame["schema"] == ingress.SUBMIT_SCHEMA:
                        validate_submission_receipt(response.result, frame["request"])
                elif response.ok is False and (response.error or {}).get('code') in {
                    'invalid_input', 'peer_denied', 'ingress_unavailable', 'not_found',
                    'grounding_mismatch', 'grounding_changed', 'operation_conflict', 'authority_refused',
                }:
                    response = dataclasses.replace(response, error={'code': response.error['code'],
                        'message': 'Canonical service ingress refused the request'})
                else:
                    return unknown(operation)
            result = _outcome_response(_classify_send_response(response, request_ref=intent_id(operation)))
            if frame["schema"] == ingress.STATUS_SCHEMA and response.ok is True:
                result = JSONResponse(dict(json.loads(result.body), terminal_result_ref=terminal_ref),
                                      status_code=result.status_code)
            return result
        except asyncio.CancelledError:
            # A submit cancellation can occur after the Unix ingress send crossed
            # its effect boundary. Convert it to the existing effect-unknown
            # response rather than allowing cancellation to imply safe replay.
            if frame.get("schema") == ingress.SUBMIT_SCHEMA:
                return unknown(operation)
            raise
        except Exception:
            return unknown(operation)

    async def call(self, request: Request):
        name = request.path_params['tool']
        authenticated = await self._auth(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        arguments = await _read_body_arguments(request)
        if isinstance(arguments, JSONResponse):
            return arguments
        try:
            args = validate_arguments(name, arguments)
        except Exception:
            # Validation errors are opaque; never echo caller or dependency content.
            return refused('invalid_input', 400)
        operation = args['operation_key']
        submit = name == 'submit_service_intent'
        frame = dict(schema=ingress.STATUS_SCHEMA, operation_key=operation)
        if submit:
            try:
                grounding = await observe_ingress_grounding(self._client, self.settings.executive.ceo_ingress_socket_path)
            except Exception:
                return refused('grounding_unavailable', 503)
            frame = dict(schema=ingress.SUBMIT_SCHEMA, request=args, observed_grounding=grounding)
        if await self._auth(request) != authenticated:
            return refused()
        result = await self._send(frame, operation)
        if name == 'executive_fabric':
            try:
                status = json.loads(result.body)
                if status.get('ok') is not True:
                    return result
                receipt = validate_receipt(status['receipt'], operation)
                selection = {k: v for k, v in args.items() if k != 'operation_key'}
                ref = validate_status({"receipt": receipt,
                    "terminal_result_ref": status.get("terminal_result_ref")}, operation)["terminal_result_ref"]
                if ref is None:
                    return refused('backend_unavailable', 503)
                if {k: v for k, v in selection.items() if k != 'view'} != {
                        k: ref[k] for k in ('root_job_id', 'job_id', 'attempt_id', 'result_envelope_digest')}:
                    return refused()
                value = await self._reader.call(name, selection)
                validate_result(value, {k: v for k, v in selection.items() if k != 'view'})
                result = JSONResponse(value)
            except Exception:
                return refused('backend_unavailable', 503)
        if await self._auth(request) != authenticated:
            return unknown(operation) if submit else refused()
        return result if len(result.body) <= MAX_RESPONSE_BYTES else (
            unknown(operation) if submit else refused('output_too_large', 503))

    async def aclose(self):
        await self._reader.aclose()

    async def __call__(self, scope, receive, send):
        if scope.get('type') == 'http':
            path = scope.get('path', '')
            if (not path.isascii() or scope.get('raw_path') != path.encode('ascii')
                    or scope.get('query_string') or scope.get('method') != 'POST'
                    or path not in {'/v1/tools/' + name for name in TOOLS}):
                await refused('invalid_input', 404)(scope, receive, send)
                return
        await self._bounded(scope, receive, send)


def create_inference_app(settings, *, audit_sink):
    return InferenceApp(settings, audit_sink)
