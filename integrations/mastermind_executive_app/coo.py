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

from common.executive_workspace_contract import _check_job_id, _check_work_ref
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
from integrations.hermes_delegate.executive import (
    ExecutiveSelectedChildTarget, SELECTED_CHILD_FRAME_SCHEMA,
    selected_child_response, validate_selected_child_ingress_envelope,
    validate_selected_child_frame,
)
from integrations.hermes_delegate.schema import SubmissionError
from integrations.mastermind_executive_app.app import AppSettings, _authenticate, _outcome_response, _read_body_arguments
from integrations.mastermind_executive_app.admission import AdmissionOutcome, _classify_send_response
from integrations.mastermind_executive_app.coo_binding import COO_SCOPES, coo_authorizer, principal_frame
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
    # The trusted host's frozen selected-child target. It defaults to unbound:
    # this App never selects, creates or derives a child on its own.
    selected_child_target: ExecutiveSelectedChildTarget | None = None
    # Explicit installed Web-CEO v3 host composition, never a request field.
    public_mcp: bool = False
    # Optional same-owner projections; absence preserves the v1 constructor.
    catalogue_provider: Callable[..., str] | None = None
    agentos_context_provider: Callable[..., Mapping[str, Any]] | None = None
    agentos_current_context_provider: Callable[..., Mapping[str, Any]] | None = None
    agentos_discovery_context_provider: Callable[..., Mapping[str, Any]] | None = None
    agentos_knowledge_context_provider: Callable[..., Mapping[str, Any]] | None = None

    def __post_init__(self):
        policy = validate_resource_policy(self.policy)
        base = self.executive
        if not isinstance(base, AppSettings) or not base.read_from_ceo_ingress or base.read_only:
            raise ValueError("COO requires the existing installed ingress readers")
        if type(self.public_mcp) is not bool:
            raise ValueError("COO public MCP composition must be explicit")
        pair = base.public_policies if self.public_mcp else base.policies
        if pair is None:
            raise ValueError("public COO requires the installed public policy pair")
        if (policy.required_scopes != COO_SCOPES
                or policy.policy_id in {base.policies.read.policy_id, base.policies.submit.policy_id}
                or policy.resource_metadata_url != pair.read.resource_metadata_url
                or _jwks_cache_contract(policy) != _jwks_cache_contract(pair.read)):
            raise ValueError("COO must share the Executive resource and JWKS, with distinct exact scopes")
        if not all(callable(x) for x in (self.load_binding, self.authority_provider, self.mission_provider)):
            raise ValueError("COO requires explicit installed binding and canonical fact providers")
        if any(value is not None and not callable(value) for value in
               (self.catalogue_provider, self.agentos_context_provider, self.agentos_current_context_provider, self.agentos_discovery_context_provider, self.agentos_knowledge_context_provider)):
            raise ValueError("COO context requires explicit installed providers")
        if (self.selected_child_target is not None
                and type(self.selected_child_target) is not ExecutiveSelectedChildTarget):
            raise ValueError("COO requires the exact frozen selected-child target")
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
    def __init__(self, settings: CooAppSettings, audit_sink, *, workspace_app=None):
        if type(settings) is not CooAppSettings or not callable(getattr(audit_sink, "emit", None)):
            raise ValueError("exact COO settings and existing audit sink required")
        self.settings = settings
        self._context_settings = settings
        self._context_callbacks = (settings.load_binding, settings.authority_provider,
                                   settings.catalogue_provider, settings.agentos_context_provider,
                                   settings.agentos_current_context_provider, settings.agentos_discovery_context_provider, settings.agentos_knowledge_context_provider)
        if workspace_app is not None:
            from integrations.executive_mcp.server import AuditedWorkspaceApp
            if type(workspace_app) is not AuditedWorkspaceApp:
                raise TypeError("the original audited Workspace App is required")
        self._context_workspace_app = workspace_app
        self._policy = validate_resource_policy(settings.policy)
        # The injected Executive cache belongs only to its primary resource.
        # Public COO gets the existing public pair's bounded cache factory;
        # sharing keys never widens the exact role scopes or enrolled identity.
        if settings.public_mcp:
            from integrations.mastermind_executive_app.gateway import make_shared_jwks_cache
            cache = make_shared_jwks_cache(settings.executive.public_policies)
            if cache is None:
                raise ValueError("public COO requires one qualified JWKS authority")
        else:
            cache = settings.executive.jwks_cache or _default_jwks_cache(self._policy)
        self.authenticator = JwtAuthenticator(policy=self._policy, jwks_cache=cache)
        self.authorizer = coo_authorizer(policy=self._policy, load_binding=settings.load_binding)
        self._context_auth_owners = (self.authenticator, self.authorizer, settings.executive.clock,
                                    self.authorizer.binding_digest, workspace_app)
        self._audit_sink = audit_sink
        self._client = CeoIngressClient(connect_timeout=settings.executive.connect_timeout,
                                       read_timeout=settings.executive.read_timeout)
        self._read_gateway = WebCeoV2CeoIngressReadGateway(settings.executive.ceo_ingress_socket_path, self._client)
        self._app = Starlette(routes=[Route("/v1/tools/{tool}", self.call, methods=["POST"]),
            Route("/v1/memory/evaluation-assessment", self.assess_memory_evaluator, methods=["POST"])])
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

    async def assess_memory_evaluator(self, request):
        """Actual JWT/binding ingress; no rating text/private results returned.

        The dedicated frame is further gated by the installed gateway process,
        explicit sealed study delegation and current mission on Control.
        """
        from common import memory_evaluation_contract as evaluation
        from control_plane.protected_memory_evaluation_assignment import INGRESS, ASSIGN, purpose_document
        from integrations.mastermind_executive_app.coo_binding import principal_frame
        authenticated = await self._auth(request)
        if isinstance(authenticated, JSONResponse): return authenticated
        sent = False
        decision = None
        try:
            raw = await request.body()
            if not 1 <= len(raw) <= 32768: return refused('invalid_input', 400)
            from common.memory_participant_view import _json
            decision = purpose_document(_json(raw))
            principal, stamp = authenticated
            authority, _ = await self._authority(principal, decision['work_ref'], stamp)
            mandate = await self._mandate(principal, stamp, authority)
            if mandate['new_effect_gate'] != 'OPEN' or not await self._same_auth(request, authenticated): return refused()
            frame = dict(schema=INGRESS, principal=principal_frame(principal), verified_expires_at=principal.expires_at, assessment=decision)
            sent = True
            result = await self._client.send_frame(self.settings.executive.ceo_ingress_socket_path, frame)
            if result.transport == TRANSPORT_NOT_SENT: return refused('ingress_unavailable', 503)
            if result.transport != TRANSPORT_SENT_OK: return unknown(decision['command_id'])
            if not await self._same_auth(request, authenticated): return unknown(decision['command_id'])
            if result.ok is not True:
                return unknown(decision['command_id']) if (result.error or {}).get('code') == 'effect_unknown' else refused()
            receipt = result.result
            assignment=decision['schema']==ASSIGN
            evaluation.w.exact(receipt, 'schema event_id '+('assignment_sha256' if assignment else 'admission_sha256')+' verification scientific_admission')
            if (receipt['schema'] != ('mastermind.memory_evaluation_assignment_receipt.v1' if assignment else 'mastermind.memory_evaluator_admission_receipt.v1')
                    or receipt['verification'] != evaluation.w.FLAGS or receipt['scientific_admission'] is not False): return unknown(decision['command_id'])
            return JSONResponse({'ok':True, 'result':receipt}, headers={'Cache-Control':'no-store'})
        except Exception:
            return unknown(decision['command_id']) if sent else refused()

    def require_context_current(self):
        settings = self._context_settings
        if (self.settings is not settings or any(a is not b for a, b in zip(
                self._context_callbacks, (settings.load_binding, settings.authority_provider,
                                         settings.catalogue_provider, settings.agentos_context_provider,
                                         settings.agentos_current_context_provider, settings.agentos_discovery_context_provider, settings.agentos_knowledge_context_provider)))):
            raise ValueError("authority_refused")

    async def catalogue(self, principal, stamp, *, work_ref=None):
        from common import coo_agentos_context_contract as wire
        self.require_context_current()
        settings = self.settings
        provider = settings.catalogue_provider
        if provider is None:
            return wire.LEGACY_CATALOGUE
        value = await _owner_call(provider, principal, *(() if work_ref is None else (work_ref,)))
        self.require_context_current()
        if (type(value) is not str or value not in {wire.LEGACY_CATALOGUE, wire.CATALOGUE, wire.CURRENT_CATALOGUE, wire.DISCOVERY_CATALOGUE, wire.KNOWLEDGE_CATALOGUE}
                or self.settings is not settings or settings.catalogue_provider is not provider
                or not self._policy_current() or self.authorizer.binding_digest(principal) != stamp):
            raise ValueError("authority_refused")
        return value

    def require_current_context_auth(self, authenticated, workspace_authenticated):
        self.require_context_current()
        held = self._context_auth_owners
        live = (self.authenticator, self.authorizer, self.settings.executive.clock,
                self.authorizer.binding_digest, self._context_workspace_app)
        if any(a is not b for a, b in zip(held, live)) or live[-1] is None or not self._policy_current():
            raise ValueError("authority_refused")
        principal, stamp = authenticated
        now = self.settings.executive.clock()
        if (type(now) is not int or not principal.issued_at <= now < principal.expires_at
                or self.authorizer.binding_digest(principal) != stamp):
            raise ValueError("authority_refused")
        live[-1].require_context_principal(*workspace_authenticated)

    async def current_context_auth(self, request):
        """Authenticate the original pair for a single HTTP/MCP read boundary."""
        from common import coo_agentos_context_contract as wire
        from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame
        from integrations.mastermind_executive_app.fresh_conversation_transport import FreshConversationTransportApp
        token = FreshConversationTransportApp._token(request.scope, b"x-mastermind-workspace-authorization")
        workspace_owner = self._context_workspace_app
        if workspace_owner is None or workspace_owner is not self._context_auth_owners[-1]:
            raise ValueError("authority_refused")
        authenticated = await self._auth(request)
        if isinstance(authenticated, JSONResponse):
            raise ValueError("authority_refused")
        workspace_authenticated = await workspace_owner.agentos_context_principal(token)
        if workspace_authenticated is None:
            raise ValueError("authority_refused")
        wire.workspace_principal(workspace_frame(workspace_authenticated[0]), executive=principal_frame(authenticated[0]))
        self.require_current_context_auth(authenticated, workspace_authenticated)
        return authenticated, workspace_authenticated

    async def _agentos_context(self, request, authenticated, validated, *, current_data=False, discovery=False, knowledge=False):
        from common import coo_agentos_context_contract as wire
        from integrations.mastermind_workspace_app.contract import principal_frame as workspace_frame
        settings = self.settings
        callbacks = (settings.load_binding, settings.authority_provider,
                     settings.catalogue_provider, settings.agentos_context_provider,
                     settings.agentos_current_context_provider, settings.agentos_discovery_context_provider, settings.agentos_knowledge_context_provider)
        principal, stamp = authenticated
        workspace_owner = self._context_workspace_app
        provider = settings.agentos_knowledge_context_provider if knowledge else settings.agentos_discovery_context_provider if discovery else settings.agentos_current_context_provider if current_data else settings.agentos_context_provider
        catalogue = wire.KNOWLEDGE_CATALOGUE if knowledge else wire.DISCOVERY_CATALOGUE if discovery else wire.CURRENT_CATALOGUE if current_data else wire.CATALOGUE
        action = wire.CURRENT_ACTION if current_data else wire.ACTION
        tool = wire.CURRENT_TOOL if current_data else wire.TOOL
        def current():
            self.require_context_current()
            if (self.settings is not settings or any(a is not b for a, b in zip(callbacks,
                    (settings.load_binding, settings.authority_provider,
                     settings.catalogue_provider, settings.agentos_context_provider,
                     settings.agentos_current_context_provider, settings.agentos_discovery_context_provider, settings.agentos_knowledge_context_provider)))):
                raise ValueError("authority_refused")
            if current_data:
                now = settings.executive.clock()
                if (self._context_workspace_app is not workspace_owner or any(a is not b for a, b in zip(
                        self._context_auth_owners, (self.authenticator, self.authorizer, settings.executive.clock,
                            self.authorizer.binding_digest, workspace_owner)))
                        or type(now) is not int or not principal.issued_at <= now < principal.expires_at):
                    raise ValueError("authority_refused")
        try:
            current()
            if provider is None:
                return refused()
            workspace_authenticated = None
            if current_data:
                # One fixed companion bearer; it is never a tool argument or a
                # relabeled COO credential. The original audited owner verifies it.
                pair = await self.current_context_auth(request)
                current()
                if pair[0] != authenticated:
                    return refused()
                workspace_authenticated = pair[1]
                workspace, _ = workspace_authenticated
                workspace_projection = workspace_frame(workspace)
                wire.workspace_principal(workspace_projection, executive=principal_frame(principal))
            selected_catalogue = await self.catalogue(principal, stamp, work_ref=validated["work_ref"])
            current()
            if selected_catalogue != catalogue:
                return refused()
            authority, context = await self._authority(principal, validated["work_ref"], stamp)
            current()
            if action not in authority.principal_actions:
                return refused()
            current()
            if not await self._same_auth(request, authenticated):
                return refused()
            current()
            if current_data:
                if await self.current_context_auth(request) != (authenticated, workspace_authenticated):
                    return refused()
                current()
                data = await _owner_call(provider, principal, workspace, context, authority.capability_profile_digest)
            else:
                data = await _owner_call(provider, principal, context, authority.capability_profile_digest)
            current()
            validator = wire.validate_knowledge_result if knowledge else wire.validate_discovery_result if discovery else wire.validate_current_result if current_data else wire.validate_result
            validator(data, expected_context=dataclasses.asdict(context),
                capability_profile_digest=authority.capability_profile_digest,
                **({"expected_workspace_principal": workspace_projection} if current_data else {}))
            observed_authority = await self._authority(principal, validated["work_ref"], stamp)
            current()
            observed_catalogue = await self.catalogue(principal, stamp, work_ref=validated["work_ref"])
            current()
            same_auth = await self._same_auth(request, authenticated)
            current()
            if (observed_authority != (authority, context)
                    or observed_catalogue != catalogue or not same_auth):
                return refused()
            if current_data and await self.current_context_auth(request) != (authenticated, workspace_authenticated):
                return refused()
            current()
            if current_data:
                self.require_current_context_auth(authenticated, workspace_authenticated)
            response = JSONResponse(self._read_result(tool, data), headers={"Cache-Control": "no-store"})
            if len(response.body) > MAX_RESPONSE_BYTES:
                return refused("output_too_large", 503)
            return response
        except Exception:
            return refused("source_unavailable", 503)

    async def resolve_principal_dialogue_caller(self, request: Request, *,
                                                work_ref: str, reasoning_surface: str):
        """Derive current principal facts for trusted host composition only.

        This is not a new HTTP/MCP action or a send authorization. A host must
        separately bind the exact pending child and revalidate these facts at
        COMMIT. The reasoning-surface label is host metadata, not identity proof.
        The existing authenticated principal and mission owners supply authority.
        """
        from control_plane.coo_principal_mandate import NewEffectGate
        from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
            CooPrincipalDialogueCaller,
        )

        try:
            if (type(work_ref) is not str or not _check_work_ref(work_ref)
                    or type(reasoning_surface) is not str
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", reasoning_surface) is None):
                return refused()
            authenticated = await self._auth(request)
            if isinstance(authenticated, JSONResponse):
                return authenticated
            principal, stamp = authenticated
            authority, context = await self._authority(principal, work_ref, stamp)
            if "governed_orchestration" not in authority.principal_actions:
                return refused()
            mandate = await self._mandate(principal, stamp, authority)
            mission = mandate["mission"]
            if (mandate["new_effect_gate"] != "OPEN"
                    or mandate["decision_posture"] != "DECIDE_CONTINUE"
                    or mission["work_ref"] != work_ref
                    or not _check_job_id(mission["root_job_id"])
                    or mission["accountable_seat"] != "coo"
                    or mission["owed_turn"]["seat"] != "coo"
                    or not await self._same_auth(request, authenticated)):
                return refused()
            # Owner reads can await. Re-read the same authenticated mission;
            # never retarget the caller to a replacement principal or root.
            current_authority, current_context = await self._authority(principal, work_ref, stamp)
            current_mandate = await self._mandate(principal, stamp, current_authority)
            if (current_authority != authority or current_context != context
                    or current_mandate != mandate
                    or not await self._same_auth(request, authenticated)):
                return refused()
            return CooPrincipalDialogueCaller(
                admission_context=context, root_job_id=mission["root_job_id"],
                reasoning_surface=reasoning_surface,
                capability_profile_digest=authority.capability_profile_digest,
                new_effect_gate=NewEffectGate(mandate["new_effect_gate"]),
                accountable_seat=mission["accountable_seat"],
                owed_seat=mission["owed_turn"]["seat"],
            )
        except Exception:
            return refused()

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

    async def _selected_child(self, request, authenticated, validated):
        """Submit or observe exactly one host-frozen child.

        The model names a canonical command the trusted host already froze.
        Every authority field in the private frame comes from this App's own
        authenticated providers; the model supplies none of them. The frame
        is sent once. There is no retry, no resubmit, no cancellation, no
        alternative carrier and no recomputed ordinal.
        """

        principal, stamp = authenticated
        command = validated["command"]
        action = validated["action"]
        is_submit = action == "selected_child_submit"

        def answer(state, reason, *, job_id=None):
            return JSONResponse(selected_child_response(
                state, reason, command_id=command, job_id=job_id,
                live_submit=None if state in {"EFFECT_UNKNOWN", "UNAVAILABLE"} else False,
            ), status_code=200)

        def uncertain(reason):
            # A possible submit stays unknown; a failed status observation is
            # unavailable. Both retain the original command.
            state = "EFFECT_UNKNOWN" if is_submit else "UNAVAILABLE"
            return answer(state, reason)

        target = self.settings.selected_child_target
        if type(target) is not ExecutiveSelectedChildTarget:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_NOT_BOUND")
        try:
            target.require_current()
            child = target.child_for(command)
        except Exception:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_TARGET_UNAVAILABLE")
        if child is None:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_UNKNOWN_COMMAND")
        job_id = child.selection.job_id
        work_ref = target.work_ref
        try:
            authority, context = await self._authority(principal, work_ref, stamp)
        except Exception:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_AUTHORITY_REFUSED", job_id=job_id)
        try:
            target.require_current()
        except Exception:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_TARGET_UNAVAILABLE", job_id=job_id)
        if not await self._same_auth(request, authenticated):
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_AUTHORITY_REFUSED", job_id=job_id)
        target_digest = target.material_digest()
        if self.settings.selected_child_target is not target:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_TARGET_UNAVAILABLE", job_id=job_id)
        frame = {
            "schema": SELECTED_CHILD_FRAME_SCHEMA,
            "request": {"action": action, "command": command},
            "target_digest": target_digest,
            "principal": principal_frame(principal),
            "principal_context": dataclasses.asdict(context),
            "capability_profile_digest": authority.capability_profile_digest,
        }
        try:
            validate_selected_child_frame(frame)
        except SubmissionError:
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_FRAME_INVALID", job_id=job_id)
        try:
            response = await self._client.send_frame(
                self.settings.executive.ceo_ingress_socket_path, frame)
        except Exception:
            # The frame may already have reached the Control. Never prove a
            # no-effect outcome from an unrecognized post-send failure.
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        if type(response) is not CeoIngressResponse:
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        if response.transport == TRANSPORT_NOT_SENT:
            # Provably never delivered: a preflight refusal, not an effect.
            return answer("REFUSED", "EXECUTIVE_SELECTED_CHILD_NOT_SENT", job_id=job_id)
        if response.transport != TRANSPORT_SENT_OK:
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        if response.ok is not True:
            # A generic ingress error does not establish where an effect
            # stopped. Only NOT_SENT or a qualified canonical envelope can
            # establish a negative result after this transport boundary.
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        try:
            envelope = validate_selected_child_ingress_envelope(
                response.result, command_id=command, job_id=job_id,
                target_digest=target_digest)
        except (TypeError, ValueError):
            # A malformed return after a possible submit is not a no-effect
            # receipt. Retain the original command.
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        # Recheck this same principal's source facts and held target after
        # the transport await. A closed fresh mandate alone does not deny
        # observation of an already claimed original command.
        try:
            current_authority, current_context = await self._authority(principal, work_ref, stamp)
            if (current_context != context
                    or current_authority.capability_profile_digest
                    != authority.capability_profile_digest
                    or not await self._same_auth(request, authenticated)):
                raise ValueError("selected child principal changed")
            target.require_current()
            if (self.settings.selected_child_target is not target
                    or target.material_digest() != target_digest):
                raise ValueError("selected child target changed")
        except Exception:
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        try:
            body = canonical_json(envelope)
        except (TypeError, ValueError):
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        if len(body) > MAX_RESPONSE_BYTES:
            return uncertain("EXECUTIVE_SELECTED_CHILD_EFFECT_UNKNOWN")
        return JSONResponse(envelope, status_code=200)

    async def call(self, request: Request):
        name = request.path_params["tool"]
        from common import coo_agentos_context_contract as context_wire
        from integrations.executive_mcp.coo import validate_coo_context_tool_arguments
        from common import coo_project_knowledge_contract as knowledge_wire
        context_tools = (context_wire.TOOL, context_wire.CURRENT_TOOL)
        extended_tools = (*context_tools, *knowledge_wire.TOOLS)
        if name not in (*COO_TOOL_NAMES, *extended_tools):
            return refused("invalid_input", 404)
        authenticated = await self._auth(request)
        if isinstance(authenticated, JSONResponse):
            return authenticated
        principal, stamp = authenticated
        arguments = await _read_body_arguments(request)
        if isinstance(arguments, JSONResponse):
            return arguments
        try:
            validated = (validate_coo_context_tool_arguments(name, arguments) if name in extended_tools
                         else validate_coo_tool_arguments(name, arguments))
        except GatewayError as exc:
            return refused(exc.code, 400)
        if name in knowledge_wire.TOOLS:
            from .coo_discovery import forward_discovery
            return await forward_discovery(self, request, authenticated, name, validated)
        if name in context_tools:
            try:
                catalogue = await self.catalogue(principal, stamp, work_ref=validated["work_ref"])
            except Exception:
                return refused()
            return await self._agentos_context(request, authenticated, validated,
                current_data=name == context_wire.CURRENT_TOOL,
                discovery=name == context_wire.CURRENT_TOOL and catalogue == context_wire.DISCOVERY_CATALOGUE,
                knowledge=name == context_wire.CURRENT_TOOL and catalogue == context_wire.KNOWLEDGE_CATALOGUE)
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
        if name == "mmx_delegate":
            # The closed selected-child branch runs before the generic
            # work_ref/principal-intent logic: it has no work_ref, no
            # request reference and no principal intent.
            return await self._selected_child(request, authenticated, validated)
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
            from common.coo_agentos_context_contract import TOOL as context_tool, CURRENT_TOOL as current_context_tool
            from common.coo_project_knowledge_contract import TOOLS as project_tools
            path = scope.get("path", "")
            if (not path.isascii() or scope.get("raw_path") != path.encode("ascii")
                    or scope.get("query_string") or scope.get("method") != "POST"
                    or path not in ({"/v1/tools/" + name for name in (*COO_TOOL_NAMES, context_tool, current_context_tool, *project_tools)}
                                    | {"/v1/memory/evaluation-assessment"})):
                await refused("invalid_input", 404)(scope, receive, send)
                return
        await self._bounded(scope, receive, send)


def create_coo_app(settings: CooAppSettings, *, audit_sink, workspace_app=None):
    """Build a same-process adapter, not a listener or an installed authority."""
    return CooApp(settings, audit_sink, workspace_app=workspace_app)
