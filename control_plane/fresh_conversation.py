"""Fresh conversation composition over the incumbent Executive/Runtime owners.

The authenticated private host supplies a neutral principal and, for create,
the SAME Session Bridge ForegroundOperation on the originating connection.
Neither a principal DTO nor a preview digest authenticates its caller. This
module opens no Runtime/listener/provider, stores no sessions or previews, and
does not alter generic summon, fixed-alias capacity placement, or return law.
"""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

from common import fresh_conversation_contract as wire
from control_plane import ceo_intent, ceo_request, executive_ceo_ingress as ingress
from control_plane.executive_runtime import (
    JobStatus, NATIVE_RETURN_TX5_EXECUTION_PROFILE,
)
from control_plane.foreground_operation import current_foreground_operation
from control_plane.principal_projection import NeutralPrincipalProjection, neutral_principal_projection

_SCOPES = frozenset({"mastermind.executive.read", "mastermind.executive.intent.submit"})
_IDENTITY = ("policy_id", "issuer_digest", "resource", "subject_digest", "client_ref")
_RESULT_LIMIT = 16384


class ConversationRefusal(ValueError):
    def __init__(self, code="conversation_unavailable", *, effect="NONE"):
        super().__init__(code)
        self.code, self.effect = code, effect


def scoped_operation_key(principal, operation_key):
    """Stable original-parent namespace, never a token or admission capability."""
    if type(principal) is not NeutralPrincipalProjection:
        raise ConversationRefusal("principal_refused")
    return "conversation-" + wire.canonical_digest({
        "principal": {key: getattr(principal, key) for key in _IDENTITY},
        "operation_key": operation_key,
    })


def admission_arguments(principal, request, *, schema=wire.SCHEMA):
    request = wire.validate_request({key: request[key] for key in
        ("work_ref", "operation_key", "message")}, operation="preview", schema=schema)
    args = wire.admission_arguments(request, scoped_operation_key(principal, request["operation_key"]), schema=schema)
    # V2 keeps exact native text in the original immutable creation material.
    # Its short objective binds that text by UTF-8 identity; it is not a prompt.
    if schema == wire.SCHEMA:
        args["objective"] = json.dumps({"mode": "fresh_conversation", "message": request["message"],
            "response": "Answer this user's message in the sealed result summary within the existing read-only grant. "
                "Retain the native session for separately authenticated continuation; do not dispatch child work."},
            ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return ceo_request.normalize_app_request(args)


class FreshConversationOwner:
    """Host-owned adapter; all effects remain existing admission/cycle effects."""
    def __init__(self, service, *, expected_policy, authorized_policies=None):
        from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
        if type(service) is not ExecutiveControlService:
            raise ConversationRefusal()
        app = service._ceo_ingress_app_binding
        if type(app) is not CeoIngressAppBinding:
            raise ConversationRefusal()
        if (type(expected_policy) is not tuple or len(expected_policy) != 3
                or any(type(value) is not str or not value for value in expected_policy)):
            raise ConversationRefusal()
        self._service, self._runtime, self._app = service, service._require_runtime(), app
        # Trusted composition from the incumbent installed submit policy,
        # never a frame field and never a new policy/enrollment registry.
        self._expected_policy = expected_policy
        from control_plane.installed_principal_read_binding import trusted_read_pair as _trusted_read_pair
        self._trusted_read_pair = _trusted_read_pair(authorized_policies)
        if self._trusted_read_pair is not None:
            import hashlib
            policy = self._trusted_read_pair[1]
            if (policy.policy_id, hashlib.sha256(policy.issuer.encode()).hexdigest(), policy.resource) != expected_policy:
                raise ConversationRefusal("principal_refused")

    def _current(self, principal, *, read_only=False):
        service = self._service
        now = time.time()
        if (type(principal) is not NeutralPrincipalProjection
                or type(principal.issued_at) is not int or type(principal.expires_at) is not int
                or not principal.issued_at <= now < principal.expires_at
                or not _SCOPES <= set(principal.scopes)
                or tuple(getattr(principal, key) for key in ("policy_id", "issuer_digest", "resource")) != self._expected_policy):
            raise ConversationRefusal("principal_refused")
        self._require_host_current(read_only=read_only)

    def _require_host_current(self, *, read_only=False):
        service = self._service
        states = {"READY", "QUARANTINED"} if read_only else {"READY"}
        if (service._closing or service._service_state not in states
                or service._require_runtime() is not self._runtime
                or service._ceo_ingress_app_binding is not self._app
                or self._app.armed is not True or not service.ceo_ingress_ready):
            raise ConversationRefusal()

    def project_references(self, principal, selection):
        from control_plane.fresh_conversation_reference import project_references
        return project_references(self, principal, selection)

    def read_reference(self, principal, reference, *, guard=None):
        from control_plane.fresh_conversation_reference import read_reference
        return read_reference(self, principal, reference, guard=guard)

    def _fresh(self, principal, *, schema=wire.SCHEMA):
        """Current company admission and registered worker are separate facts.

        The actual provider account/process/capability attestation is still owed
        by Runtime/OHF at materialization. Preview never claims that attestation.
        """
        if schema == wire.NATIVE_SCHEMA:
            return self._fresh_native(principal)
        if schema != wire.SCHEMA:
            raise ConversationRefusal("invalid_input")
        self._current(principal)
        service = self._service
        service._require_ceo_submit_admission()
        service._require_current_autonomy()
        service._require_coo_worker_composed()
        binding = service._require_coo_admission_binding()
        host = service._company_consultation_host
        if (not service.config.coo_autonomy_armed
                or binding["operator_harness_armed"] is not True
                or binding["operator_execution_profile_id"] != NATIVE_RETURN_TX5_EXECUTION_PROFILE
                or binding["operator_provider"] != "codex"
                or host is None or host.runtime is not self._runtime
                or host.native_return_armed is not True
                or not callable(self._app.session_bridge_provider_factory)
                or not callable(service._ceo_ingress_dialogue_source_provider)):
            raise ConversationRefusal()
        service._require_company_answer_attention()
        from control_plane.native_continuation import NativeContinuationSource
        source = host.native_continuation_source()
        if not isinstance(source, NativeContinuationSource) or source.runtime is not self._runtime:
            raise ConversationRefusal()
        self._current(principal)
        return binding

    def _fresh_native(self, principal):
        """Select the original installed native binding; browser input grants nothing."""
        self._current(principal)
        service = self._service
        service._require_ceo_submit_admission()
        service._require_current_autonomy()
        service._require_coo_worker_composed()
        binding = service._require_native_conversation_admission_binding()
        from control_plane.executive_agent_capabilities import DSH_NATIVE_CONVERSATION_PROFILE_ID
        if (not service.config.coo_autonomy_armed
                or binding["operator_harness_armed"] is not True
                or binding["operator_execution_profile_id"] != DSH_NATIVE_CONVERSATION_PROFILE_ID
                or binding["operator_provider"] != "acp"
                or not callable(self._app.session_bridge_provider_factory)
                or not callable(service._ceo_ingress_dialogue_source_provider)):
            raise ConversationRefusal()
        service._require_company_answer_attention()
        self._current(principal)
        return binding

    def _project(self, principal, workspace_principal, work_ref):
        """Actual current catalogue + independently authorized Workspace READ.

        Executive admission is not Workspace permission. The host verifies both
        resource-specific bearers before entering here; this repeats the exact
        enrolled Workspace authorizer and producer's current validity predicate.
        No root, global alias or synthetic project is substituted for selection.
        """
        from common.executive_workspace_contract import RESOURCE, SCOPE, PRINCIPAL_KEYS
        from control_plane.workspace_read_service import WorkspaceReadService, _qualified, permission_stamp
        self._current(principal)
        p = workspace_principal
        if (type(p) is not NeutralPrincipalProjection or p.resource != RESOURCE
                or p.policy_id == principal.policy_id or SCOPE not in p.scopes
                or type(p.issued_at) is not int or type(p.expires_at) is not int
                or not p.issued_at <= time.time() < p.expires_at
                or any(getattr(p, key) != getattr(principal, key)
                       for key in ("issuer_digest", "subject_digest", "client_ref"))):
            raise ConversationRefusal("project_read_refused")
        factory = self._app.workspace_read_provider_factory
        if not callable(factory):
            raise ConversationRefusal("project_read_refused")
        from control_plane.fresh_conversation_membership import _reader_for_project_phase
        reader = _reader_for_project_phase(self,principal,workspace_principal,work_ref,factory)
        if type(reader) is not WorkspaceReadService or reader.runtime is not self._runtime:
            raise ConversationRefusal("project_read_refused")
        raw = {key: sorted(p.scopes) if key == "scopes" else getattr(p, key) for key in PRINCIPAL_KEYS}
        if reader.authorize(raw) is not True:
            raise ConversationRefusal("project_read_refused")
        stamp = permission_stamp(reader.authorize, raw)
        if type(stamp) is not str or len(stamp) != 64 or any(c not in "0123456789abcdef" for c in stamp):
            raise ConversationRefusal("project_read_refused")
        snapshot = reader.cache.snapshot()
        if not _qualified(snapshot):
            raise ConversationRefusal("project_read_refused")
        rows = [row for row in snapshot.document["work"]
                if type(row) is dict and row.get("work_ref") == work_ref]
        canonical = None
        if len(rows) != 1:
            if rows:
                raise ConversationRefusal("project_selection_refused")
            from control_plane.fresh_conversation_membership import read_canonical_membership
            canonical = read_canonical_membership(reader, raw, work_ref=work_ref, snapshot=snapshot, owner=self,
                executive_principal=principal, workspace_principal=workspace_principal)
        if (reader.authorize(raw) is not True or permission_stamp(reader.authorize, raw) != stamp
                or not p.issued_at <= time.time() < p.expires_at):
            raise ConversationRefusal("project_read_refused")
        self._current(principal)
        result = {"publication": snapshot.publication, "instance": snapshot.instance,
            "document_digest": wire.canonical_digest(snapshot.document),
            "permission_stamp": stamp, "work_ref": work_ref}
        if canonical is not None:
            result["canonical_membership"] = canonical
        return result

    async def _preview(self, principal, request, workspace_principal, *, schema=wire.SCHEMA):
        args = admission_arguments(principal, request, schema=schema)
        binding = self._fresh(principal, schema=schema)
        project = self._project(principal, workspace_principal, request["work_ref"])
        grounding = await ingress._observe_trusted_grounding(self._app.grounding_provider)
        intent_id = ceo_request.automated_intent_id(ceo_request.app_request_ref(args["operation_key"]))
        provider = self._service._ceo_ingress_dialogue_source_provider
        source = await ingress._observe_dialogue_source(provider, intent_id=intent_id, work_ref=request["work_ref"])
        if (await ingress._observe_trusted_grounding(self._app.grounding_provider) != grounding
                or await ingress._observe_dialogue_source(provider, intent_id=intent_id,
                    work_ref=request["work_ref"]) != source
                or self._fresh(principal, schema=schema) != binding
                or self._project(principal, workspace_principal, request["work_ref"]) != project):
            raise ConversationRefusal("context_changed")
        material = {"arguments": args, "binding": binding,
            "grounding": grounding, "source": source.to_dict(), "project": project}
        return {"digest": wire.canonical_digest(material),
            "profile_digest": binding["operator_execution_profile_digest"],
            "source_digest": wire.canonical_digest(source.to_dict()),
            "grounding": grounding, "attempt_limit": 1,
            "worker_account": "REGISTERED_NOT_SESSION_ATTESTED"}, material

    def _response(self, request, state, *, effect="NONE", _schema=wire.SCHEMA, **extra):
        if _schema == wire.NATIVE_SCHEMA:
            value = dict(schema=wire.NATIVE_DATA_SCHEMA, operation_key=request.get("operation_key"),
                reference=request.get("reference"), work_ref=request["work_ref"], state=state, effect=effect,
                parent_consumed=False, preview=None, locator=None, session=None, active_turn=None,
                result=None, head_result=None, can_send=False, can_resume=False, can_stop=False)
            value.update(extra)
            return wire.validate_native_data(value, request)
        value = dict(schema=wire.DATA_SCHEMA, operation_key=request["operation_key"],
            work_ref=request["work_ref"], state=state, effect=effect,
            parent_consumed=False, preview=None, locator=None, session=None, result=None, can_send=False)
        value.update(extra)
        return wire.validate_data(value, request)

    async def preview(self, principal, request, *, workspace_principal, _schema=wire.SCHEMA):
        request = wire.validate_request(request, operation="preview", schema=_schema)
        preview, _ = await self._preview(principal, request, workspace_principal, schema=_schema)
        self._current(principal)
        return self._response(request, "PREVIEW_READY", preview=preview, _schema=_schema)

    async def _prepare_workspace(self, root, current):
        """One fresh root's existing credentialless allocator; no adoption/retry."""
        from control_plane.executive_workspace import prepare_credentialless_clone
        service = self._service
        async with service._workspace_lock:
            current()
            if (service._native_operator_dispatch is not None
                    or any(not task.done() for task in service._dispatch_tasks.values())):
                raise ConversationRefusal("conversation_busy", effect="UNKNOWN")
            workspace = Path(root.worktree)
            if (workspace.parent != service.config.proof_workspace_root
                    or root.branch != ceo_request.derive_branch(workspace.name)
                    or root.allowed_write_paths):
                raise ConversationRefusal("original_operation_mismatch", effect="UNKNOWN")
            receipt = await service._run_physical(prepare_credentialless_clone,
                service.config.proof_source_repository, service.config.proof_workspace_root,
                job_id=workspace.name, base_sha=root.constraints["base_sha"], branch=root.branch,
                shared_gid=service.config.proof_shared_gid, shared_write_paths=())
            current()
            if (receipt.workspace_path != str(workspace) or receipt.branch != root.branch
                    or receipt.base_sha != root.constraints["base_sha"] or receipt.remote_count != 0):
                raise ConversationRefusal("effect_unknown", effect="UNKNOWN")
            service._require_initial_coo_workspace(root)
            current()

    def _require_fresh_original(self, root, principal, request, command, *, schema=wire.SCHEMA):
        from control_plane.fresh_conversation_admission import read_creation_restriction
        if root is None:
            raise ConversationRefusal("original_operation_mismatch")
        try:
            material = read_creation_restriction(self._runtime, root)
        except Exception:
            raise ConversationRefusal("original_operation_mismatch") from None
        from control_plane.fresh_conversation_admission import SCHEMA, NATIVE_SCHEMA
        expected = NATIVE_SCHEMA if schema == wire.NATIVE_SCHEMA else SCHEMA
        if (schema not in {wire.SCHEMA, wire.NATIVE_SCHEMA}
                or material is None or material["schema"] != expected or material["command_id"] != command
                or material["work_ref"] != request["work_ref"]
                or material["principal_scope_sha256"] != wire.canonical_digest(
                    {key: getattr(principal, key) for key in _IDENTITY})):
            raise ConversationRefusal("original_operation_mismatch")
        return material

    async def create(self, principal, request, *, workspace_principal, _schema=wire.SCHEMA):
        request = wire.validate_request(request, operation="create", schema=_schema)
        self._current(principal)
        args = admission_arguments(principal, request, schema=_schema)
        operation = current_foreground_operation()
        operation.require_arguments(args)
        if (operation._runtime is not self._runtime
                or any(getattr(operation._principal, key) != getattr(principal, key)
                       for key in _IDENTITY)):
            raise ConversationRefusal("principal_refused")
        request_ref = ceo_request.app_request_ref(args["operation_key"])
        command = ceo_intent.command_id_for(ceo_request.automated_intent_id(request_ref))
        existing = self._runtime.store.find_event_by_command_id(command)
        # Durable duplicate comparison is owned by the incumbent sink. A later
        # worker/profile arm cannot dispatch an old operation from this route.
        material = None
        if existing is not None:
            self._require_fresh_original(self._runtime.jobs.get_job(existing["job_id"]),
                principal, request, command, schema=_schema)
        if existing is None:
            preview, material = await self._preview(principal, request, workspace_principal, schema=_schema)
            if preview["digest"] != request["preview_digest"]:
                raise ConversationRefusal("context_changed")

        def current(_envelope=None):
            from contextlib import nullcontext
            from control_plane.fresh_conversation_membership import _project_validation_phase
            # Only this synchronous pure validation callback shares a nominal
            # observation. Its scope exits before the caller inserts/claims,
            # allocates a workspace, advances a cycle or invokes native I/O.
            scope = (_project_validation_phase(self, principal, workspace_principal, request["work_ref"])
                if material is not None and "canonical_membership" in material["project"] else nullcontext())
            with scope:
                operation.require_arguments(args)
                self._current(principal)
                if material is not None and self._fresh(principal, schema=_schema) != material["binding"]:
                    raise ConversationRefusal("context_changed")
                if material is not None and self._project(principal, workspace_principal,
                        request["work_ref"]) != material["project"]:
                    raise ConversationRefusal("context_changed")

        def admitted(root_id, command_id):
            current()
            operation._bind_admitted_root(root_id, command_id)

        creation_source = None
        if material is not None:
            from control_plane.fresh_conversation_admission import _issue_creation_source, SCHEMA
            intent_id = ceo_request.automated_intent_id(request_ref)
            envelope = ingress._build_envelope({key: value for key, value in args.items() if key != "operation_key"},
                intent_id=intent_id, workspace_root=self._service.config.proof_workspace_root,
                grounding=material["grounding"], strict_v2=True)
            creation_material = dict(schema=SCHEMA,
                intent_id=intent_id, command_id=command, work_ref=request["work_ref"],
                intent_fingerprint=ceo_intent.intent_fingerprint(envelope),
                arguments_sha256=operation._arguments_sha256,
                principal_scope_sha256=wire.canonical_digest({key: getattr(principal, key) for key in _IDENTITY}),
                workspace_permission_sha256=material["project"]["permission_stamp"],
                project_sha256=wire.canonical_digest(material["project"]),
                dialogue_source_sha256=wire.canonical_digest(material["source"]),
                host_binding_sha256=wire.canonical_digest(material["binding"]),
                principal_expires_at=principal.expires_at)
            if _schema == wire.NATIVE_SCHEMA:
                from control_plane.fresh_conversation_admission import native_input_material
                creation_material.update(native_input_material(request["message"]))
            creation_source = _issue_creation_source(self, operation, creation_material, current,
                public_operation_key=request["operation_key"],
                project_principal=principal if "canonical_membership" in material["project"] else None,
                workspace_principal=workspace_principal if "canonical_membership" in material["project"] else None)

        entered = False
        try:
            async with self._service._foreground_cycle_scope(operation):
                current()
                observed = (material["grounding"] if material is not None else
                    ceo_intent.resolve_intent(self._runtime,
                        ceo_request.automated_intent_id(request_ref))["grounding"])
                entered = True
                receipt = await ingress.handle_frame({"schema": ingress.SUBMIT_SCHEMA_V2,
                    "request_ref": request_ref, "observed_grounding": observed,
                    "request": {key: value for key, value in args.items() if key != "operation_key"}},
                    runtime=self._runtime, grounding_provider=self._app.grounding_provider,
                    workspace_root=self._service.config.proof_workspace_root,
                    service_state=self._service._service_state, ceo_ingress_armed=self._app.armed,
                    strict_v2_admission=True,
                    execution_binding_provider=lambda: (current(), self._fresh(principal, schema=_schema))[1],
                    dialogue_source_provider=self._service._ceo_ingress_dialogue_source_provider,
                    admission_guard=current, fresh_admission_observer=admitted,
                    fresh_conversation_source=creation_source)
                self._require_fresh_original(self._runtime.jobs.get_job(receipt["job_id"]),
                    principal, request, command, schema=_schema)
                if receipt.get("duplicate") is False:
                    root_id = receipt["job_id"]
                    operation.require_root(root_id)
                    current()
                    root = self._runtime.jobs.get_job(root_id)
                    if _schema == wire.SCHEMA:
                        self._service._native_return_source(root)
                    else:
                        from control_plane.fresh_conversation_admission import require_original_creation_request
                        require_original_creation_request(self._runtime, root, operation)
                    await self._prepare_workspace(root, current)
                    # Exactly two existing transitions, never the paid-work
                    # foreground loop and never a retry/continuation scheduler.
                    for expected in ("PLANNER_CREATED", "DISPATCHED"):
                        current()
                        outcome = await self._service._run_coo_cycle(root_id)
                        if outcome.root_job_id != root_id or outcome.action != expected:
                            raise ConversationRefusal("effect_unknown", effect="UNKNOWN")
                    current()
            return await self.status(principal,
                {key: request[key] for key in ("work_ref", "operation_key")},
                _effect="ADMITTED" if receipt.get("duplicate") is False else "NONE", _schema=_schema)
        except ingress.CeoIngressError as exc:
            # Only the existing canonical owner may establish its pre-effect
            # classification; an entered sink/dispatch uncertainty stays unknown.
            if exc.code in {"operation_conflict", "invalid_input", "grounding_changed",
                            "backend_unavailable", "backend_refused"} and self._runtime.store.find_event_by_command_id(command) is None:
                raise ConversationRefusal(exc.code) from None
            raise ConversationRefusal("effect_unknown", effect="UNKNOWN") from None
        except Exception:
            raise ConversationRefusal("effect_unknown" if entered else "conversation_unavailable",
                effect="UNKNOWN" if entered else "NONE") from None

    async def status(self, principal, request, *, _effect="NONE", include_result=False, _schema=wire.SCHEMA):
        request = wire.validate_request(request, operation="read" if include_result else "status", schema=_schema)
        if _schema == wire.NATIVE_SCHEMA:
            from control_plane.fresh_conversation_native import read_native_status
            return await read_native_status(self, principal, request, effect=_effect)
        self._current(principal, read_only=True)
        key = scoped_operation_key(principal, request["operation_key"])
        intent_id = ceo_request.automated_intent_id(ceo_request.app_request_ref(key))
        command = ceo_intent.command_id_for(intent_id)
        event = self._runtime.store.find_event_by_command_id(command)
        if event is None:
            self._current(principal, read_only=True)
            return self._response(request, "ABSENT")
        receipt = ceo_intent.resolve_intent(self._runtime, intent_id)
        root = self._runtime.jobs.get_job(receipt["job_id"])
        if (receipt.get("work_ref") != request["work_ref"] or root is None
                or root.orchestration_provenance.get("command_id") != command
                or root.parent_job_id is not None or root.root_job_id != root.job_id):
            raise ConversationRefusal("original_operation_mismatch")
        self._require_fresh_original(root, principal, request, command)
        child_command = f"coo-cycle:{root.job_id}:create-interactive:0"
        child_event = self._runtime.store.find_event_by_command_id(child_command)
        child = self._runtime.jobs.get_job(child_event["job_id"]) if child_event is not None else None
        locator = dict(work_ref=request["work_ref"], root_job_id=root.job_id,
            job_id=child.job_id if child else None, attempt_id=child.current_attempt_id if child else None)
        state, result, session = "ADMITTED", None, None
        if child is not None:
            if (child.parent_job_id != root.job_id or child.root_job_id != root.job_id
                    or child.constraints.get("execution_profile_id") != NATIVE_RETURN_TX5_EXECUTION_PROFILE):
                raise ConversationRefusal("original_operation_mismatch")
            dispatch = self._service._native_operator_dispatch
            retained = getattr(dispatch, "retained", None)
            supervisor = self._service.operator_supervisor
            from control_plane.executive_operator_supervisor import (
                ExecutiveOperatorSupervisor, RetainedNativeOperatorSession,
            )
            if (self._service._service_state == "READY" and type(supervisor) is ExecutiveOperatorSupervisor
                    and type(retained) is RetainedNativeOperatorSession
                    and retained.owner is supervisor and supervisor.runtime is self._runtime
                    and dispatch.job_id == child.job_id and retained.job.job_id == child.job_id
                    and retained.session.attempt_id == child.current_attempt_id):
                facts = supervisor._require_retained_native(retained)
                if facts.job_id != child.job_id or not facts.provider_session_id:
                    raise ConversationRefusal()
                state = "CREATED"
                session = {"attempt_id": facts.attempt_id,
                    "generation": facts.process_generation_id,
                    "binding_digest": wire.canonical_digest(dataclasses.asdict(facts))}
                if include_result:
                    raw = supervisor._sealed_role_result_json(child, retained.lease)
                    if raw is not None and len(raw.encode("utf-8")) <= _RESULT_LIMIT:
                        result = {"digest": wire.canonical_digest(json.loads(raw)), "envelope": json.loads(raw)}
                if supervisor._require_retained_native(retained) != facts:
                    raise ConversationRefusal("context_changed")
            elif child.status is JobStatus.COMPLETED:
                completed = self._runtime.validated_role_completion(child.job_id,
                    expected_attempt_id=child.current_attempt_id)
                envelope = completed.result_envelope
                if include_result and len(json.dumps(envelope, ensure_ascii=False).encode("utf-8")) <= _RESULT_LIMIT:
                    result = {"digest": completed.result_digest, "envelope": envelope}
                state = "SETTLED"
            elif child.current_attempt_id:
                state = "RECONCILIATION_REQUIRED"
        self._current(principal, read_only=True)
        return self._response(request, state, effect=_effect, locator=locator,
            session=session, result=result, can_send=False)

    async def read(self, principal, request, *, _schema=wire.SCHEMA):
        return await self.status(principal, request, include_result=True, _schema=_schema)

    async def handle_frame(self, frame, *, host_current, reader=None):
        """Fixed installed App-peer entry on the incumbent private listener.

        The control service verifies its existing kernel peer/App binding and
        supplies this live connection guard and reader. They are not frame
        fields. Create uses the same originating duplex lifetime/expiry source
        as existing foreground admission; a one-shot/EOF caller cannot create.
        """
        operation, entered = None, False
        schema = wire.NATIVE_SCHEMA if type(frame) is dict and frame.get("schema") == wire.NATIVE_SCHEMA else wire.SCHEMA
        result_schema = wire.NATIVE_RESULT_SCHEMA if schema == wire.NATIVE_SCHEMA else wire.RESULT_SCHEMA
        passive = wire.NATIVE_PASSIVE if schema == wire.NATIVE_SCHEMA else {"status", "read", "turn_status", "turn_read", "consume_status"}
        try:
            frame = wire.validate_private_frame(frame)
            operation = frame["operation"]
            def projection(raw):
                return neutral_principal_projection(**{**raw, "scopes": tuple(raw["scopes"])})
            principal = projection(frame["principal"])
            workspace = projection(frame["workspace_principal"]) if frame["workspace_principal"] is not None else None
            if not callable(host_current) or host_current() is not None:
                raise ConversationRefusal()
            self._current(principal, read_only=operation in passive)
            if operation == "create":
                if reader is None:
                    raise ConversationRefusal()
                from common.session_bridge_private_contract import PRIVATE_SCHEMA
                from control_plane.foreground_operation import (
                    _session_bridge_foreground_dispatch, _observe_private_request_end,
                )
                original = dict(schema=PRIVATE_SCHEMA, tool="session_summon",
                    principal=frame["principal"], arguments=admission_arguments(principal, frame["arguments"], schema=schema))
                command = ceo_intent.command_id_for(ceo_request.automated_intent_id(
                    ceo_request.app_request_ref(original["arguments"]["operation_key"])))
                fresh = self._runtime.store.find_event_by_command_id(command) is None
                binding = self._fresh(principal, schema=schema) if fresh else None
                project = self._project(principal, workspace, frame["arguments"]["work_ref"]) if fresh else None
                def creation_current():
                    if host_current() is not None:
                        raise ConversationRefusal()
                    self._current(principal)
                    if fresh and (self._fresh(principal, schema=schema) != binding
                            or self._project(principal, workspace, frame["arguments"]["work_ref"]) != project):
                        raise ConversationRefusal("context_changed")
                async with _session_bridge_foreground_dispatch(self._runtime, original, creation_current) as live:
                    async with _observe_private_request_end(live, reader):
                        entered = True
                        value = await self.create(principal, frame["arguments"], workspace_principal=workspace, _schema=schema)
            elif schema == wire.NATIVE_SCHEMA and operation not in {"preview", "status", "read"}:
                from control_plane.fresh_conversation_native import handle_native_followup
                entered = operation in wire.NATIVE_MODIFYING
                value = await handle_native_followup(self, principal, workspace, frame["arguments"],
                    operation=operation, host_current=host_current, reader=reader)
            elif operation == "consume_status":
                from control_plane.fresh_conversation_consumption import read_consumption
                value = read_consumption(self, principal, frame["arguments"])
            elif operation in {"consume", "turn", "turn_status", "turn_read", "turn_preview"}:
                from control_plane.fresh_conversation_turn import consume_initial, submit_turn, read_turn, preview_turn
                arguments = frame["arguments"]
                reference = arguments.get("reference")
                if reference is not None:
                    from control_plane.fresh_conversation_reference import resolve_action_reference
                    original = resolve_action_reference(self, principal, reference,
                        for_write=operation in {"consume", "turn", "turn_preview"})
                    arguments = {**arguments, **original}
                    arguments.pop("reference")
                if operation in {"consume", "turn"}:
                    def live_turn_request():
                        if reader is None or reader.at_eof() or host_current() is not None:
                            raise ConversationRefusal("request_closed")
                        self._current(principal)
                    live_turn_request()
                    entered = True
                    value = await (consume_initial if operation == "consume" else submit_turn)(
                        self, principal, workspace, arguments, host_current=live_turn_request)
                elif operation == "turn_preview":
                    value = await preview_turn(self, principal, workspace, arguments, host_current=host_current)
                else:
                    value = await read_turn(self, principal, arguments)
                if reference is not None:
                    value = {**value, "operation_key": None, "reference": reference}
                value = wire.validate_data(value, frame["arguments"])
            elif operation == "preview":
                value = await self.preview(principal, frame["arguments"], workspace_principal=workspace, _schema=schema)
            elif operation == "status":
                value = await self.status(principal, frame["arguments"], _schema=schema)
            else:
                value = await self.read(principal, frame["arguments"], _schema=schema)
            try:
                if host_current() is not None:
                    raise ConversationRefusal()
                self._current(principal, read_only=operation in passive)
            except Exception:
                raise ConversationRefusal("effect_unknown" if entered else "conversation_unavailable",
                    effect="UNKNOWN" if entered else "NONE") from None
            result = dict(schema=result_schema, operation=operation, ok=True, data=value, error=None)
            if schema == wire.NATIVE_SCHEMA:
                wire.validate_native_response(result, frame["arguments"], operation=operation)
            return result
        except ConversationRefusal as exc:
            code = "effect_unknown" if exc.effect == "UNKNOWN" else exc.code
        except (ValueError, TypeError):
            code = "effect_unknown" if entered else "invalid_input"
        except Exception:
            code = "effect_unknown" if entered else "conversation_unavailable"
        return dict(schema=result_schema, operation=operation, ok=False, data=None,
            error=dict(code=code, message="Reconcile the original conversation operation" if code == "effect_unknown"
                else "Conversation authority or source unavailable"))
