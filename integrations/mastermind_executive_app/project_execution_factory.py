"""Project-qualified launch using the existing authenticated App, Runtime and COO."""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import hashlib
import json
from pathlib import Path

from common import project_execution_private_contract as wire
from common.executive_principal_namespace import principal_scope_from_identity
from control_plane import ceo_intent, ceo_request, executive_ceo_ingress as ingress
from control_plane import project_execution_admission as source_owner
from control_plane.foreground_operation import current_foreground_operation
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app.project_planning_factory import ProjectPlanningAppFactory


class ProjectExecutionRefusal(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__("Project execution refused")


class ProjectExecutionAppFactory:
    """Compose existing independently qualified Executive and Workspace owners."""
    def __init__(self, planning):
        if type(planning) is not ProjectPlanningAppFactory:
            raise ValueError("actual project source owner required")
        self.planning = planning
        self.service = planning.service
        self.app_binding = planning.app_binding
        self._source_issuer = source_owner.bind_issuer(self.service)

    def _authorize(self, principal, args, *, fresh=False):
        operation = current_foreground_operation()
        operation.require_arguments(args)
        workspace, workspace_scope, stamp = self.planning._authorize_project_request(
            principal, operation, args["operation_key"], args["work_ref"], require_execution=fresh)
        scope = principal_scope_from_identity(issuer_digest=principal.issuer_digest,
            subject_digest=principal.subject_digest, client_ref=principal.client_ref, resource=principal.resource)
        return operation, workspace, scope, stamp

    def _supervisor(self):
        from control_plane.executive_supervisor import ExecutiveSupervisor
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        owner = self.service._require_supervisor()
        owner = owner.primary if type(owner) is MixedExecutionOwnerSupervisor else owner
        if type(owner) is not ExecutiveSupervisor or owner.runtime is not self.service._require_runtime():
            raise ProjectExecutionRefusal("execution_unavailable")
        return owner

    def _capture(self, principal, args):
        operation, workspace, scope, stamp = self._authorize(principal, args)
        plan = self.planning._canonical_plan(workspace, args["work_ref"])
        context = wire.context_from_plan(plan)
        if context != args["expected_context"]:
            raise ProjectExecutionRefusal("context_changed")
        view = self.planning._canonical_view(workspace, args["work_ref"])
        if view is None:
            raise ProjectExecutionRefusal("source_unavailable")
        from control_plane.project_plan_canonical_basis import capture_current_plan_basis, capture_current_project_files
        with view.capture_scope():
            basis = capture_current_plan_basis(view, work_ref=args["work_ref"])
            exact = basis.execution_material()
            files = capture_current_project_files(view, work_ref=args["work_ref"]).material()
        if exact["authored_record"]["source"] != context["record_source"]:
            raise ProjectExecutionRefusal("context_changed")
        # A declared but unreadable adopted plan must not become "no plan".
        current = exact["adoption"]
        adoption = context["adoption"]
        if current is not None:
            if (adoption is None or adoption["state"] != "AVAILABLE"
                    or current["decision_ref"] != adoption["decision_ref"]
                    or exact["adopted_plan"]["source"] != adoption["adopted_source"]):
                raise ProjectExecutionRefusal("source_unavailable")
        elif adoption is not None and (adoption["state"] != "UNAVAILABLE" or adoption["reason"] != "NOT_DECLARED"):
            raise ProjectExecutionRefusal("source_unavailable")
        data = dict(expected_context=context, plan=exact, files=files)
        if len(wire.canonical(data)) > 256 * 1024:
            raise ProjectExecutionRefusal("input_too_large")
        return dict(data=data, context_sha256=wire.digest(data), workspace_permission=stamp,
                    principal_scope=scope, view=view)

    def _binding(self, execution_profile="research_only", previous=None):
        binding = self.service._require_project_execution_binding(execution_profile)
        if type(previous) is dict and "workspace_revision" in previous:
            binding = dict(binding, base_sha=previous["workspace_revision"]["commit"])
        return binding

    def _fixed_source(self, work_ref):
        from control_plane.project_planning_policy import read_protected_blob
        from control_plane.executive_runtime import EXECUTIVE_DIALOGUE_SOURCE_SCHEMA
        raw = read_protected_blob(self.service.config.proof_source_repository,
                                  self.service.config.proof_base_sha, source_owner.COMMISSION_PATH)
        if not raw or len(raw) > 16384:
            raise ProjectExecutionRefusal("source_unavailable")
        return dict(schema_version=EXECUTIVE_DIALOGUE_SOURCE_SCHEMA, work_ref=work_ref, watch_mode=None,
            commission_ref=dict(repository="mastermindx-market-intelligence/Mastermind",
                commit=self.service.config.proof_base_sha, path=source_owner.COMMISSION_PATH,
                content_sha256=hashlib.sha256(raw).hexdigest()))

    def _previous(self, args, principal_scope, *, unused=True):
        witness = args.get("previous_run")
        if witness is None:
            return None
        previous = source_owner.completed_run(self._supervisor(), witness["root_job_id"],
            args["work_ref"], principal_scope)
        if previous["witness"] != witness:
            raise ProjectExecutionRefusal("context_changed")
        if unused:
            source_owner.require_unused_parent(self.service._require_runtime(), witness)
        root = self.service._require_runtime().jobs.get_job(witness["root_job_id"])
        if source_owner.requires_workspace_continuity(self._supervisor(), root):
            previous["workspace_revision"] = source_owner.completed_workspace_revision(self._supervisor(), previous)
        return previous

    async def preview(self, principal, args):
        capture = await asyncio.to_thread(self._capture, principal, args)
        previous = await asyncio.to_thread(self._previous, args, capture["principal_scope"])
        state, binding = "EXECUTION_UNAVAILABLE", None
        if not self.service.config.coo_autonomy_armed:
            state = "AUTONOMY_OFF"
        else:
            try:
                self._authorize(principal, args, fresh=True)
                binding = self._binding("research_only", previous)
                self._fixed_source(args["work_ref"])
                state = "WORK_CAPABLE"
            except Exception:
                # Eligibility failure is observable; no root or artifact is prepared.
                state = "EXECUTION_UNAVAILABLE"
        profiles = [{"ref": "research_only", "label": "Research team"}] if binding is not None else []
        profile_bindings = {"research_only": wire.digest(binding)} if binding is not None else {}
        if binding is not None:
            try:
                code_binding = self._binding("bounded_code_change", previous)
                profile_bindings["bounded_code_change"] = wire.digest(code_binding)
                profiles.append({"ref": "bounded_code_change", "label": "Build in declared paths"})
            except Exception:
                pass  # Offer only a freshly qualified native write capability.
        self._authorize(principal, args)
        capture["view"].check()
        return dict(schema=wire.PREVIEW_SCHEMA, work_ref=args["work_ref"],
            context_sha256=capture["context_sha256"], execution_state=state,
            execution_binding_sha256=wire.digest(binding) if binding is not None else None,
            execution_profile_bindings=profile_bindings,
            continuation_mode=self.service._project_execution_mode() if binding is not None else None,
            coordinator={k:binding[k] for k in ("provider", "model", "effort")} if binding is not None else None,
            execution_scope=dict(repository="mastermindx-market-intelligence/Mastermind",
                commit=binding["base_sha"]) if binding is not None else None,
            previous_run=previous["witness"] if previous is not None else None,
            binding=dict(workstream=args["work_ref"], priority=0, attemptLimit=1,
                projects=[{"ref": "executive-infrastructure", "label": "Project team"}], profiles=profiles))

    def _original(self, principal, args, *, submit):
        operation, workspace, scope, stamp = self._authorize(principal, args, fresh=False)

        def require_current_read():
            current, current_workspace, current_scope, current_stamp = self._authorize(
                principal, args, fresh=False)
            if (current is not operation or current_workspace != workspace
                    or current_scope != scope or current_stamp != stamp):
                raise ProjectExecutionRefusal("context_changed")

        runtime = self.service._require_runtime()
        event = runtime.store.find_event_by_command_id(operation._command)
        if event is None:
            require_current_read()
            return None
        root = runtime.jobs.get_job(event["job_id"])
        material = source_owner.read_source(runtime, root)
        if (material is None or material["principal_scope_sha256"] != scope
                or material["operation_key"] != args["operation_key"] or material["work_ref"] != args["work_ref"]
                or (submit and material["arguments_sha256"] != wire.digest(args))):
            raise ProjectExecutionRefusal("operation_conflict")
        source_owner.read_original_input(self._supervisor(), material)
        receipt = ceo_intent.resolve_intent(runtime, material["intent_id"])
        # Retained reads may block. Qualify the same live reader and permission
        # after the last read, without requiring a new plan or execution arm.
        require_current_read()
        return receipt

    def _request(self, args):
        return ceo_request.normalize_automated_request(dict(objective=wire.objective_for_intent(args["objective"]),
            department="executive-infrastructure", priority=0, execution_profile=args["execution_profile"],
            workstream=args["work_ref"], attempt_limit=1,
            **{k: args[k] for k in ("allowed_write_paths", "validation") if k in args}))

    async def _prepare_workspace(self, root, operation):
        operation.require_root(root.job_id)
        await self.service._prepare_project_root_workspace(root)
        operation.require_root(root.job_id)

    async def submit(self, principal, args):
        # Original effects are resolved before current source, policy, routing or input preparation.
        original = await asyncio.to_thread(self._original, principal, args, submit=True)
        if original is not None:
            return dict(operation_key=args["operation_key"], work_ref=args["work_ref"], state="ACCEPTED", receipt=original)
        operation, workspace, scope, stamp = self._authorize(principal, args, fresh=True)
        if args["operation_key"] != wire.operation_key(scope, args):
            raise ProjectExecutionRefusal("operation_conflict")
        capture = await asyncio.to_thread(self._capture, principal, args)
        previous = await asyncio.to_thread(self._previous, args, scope)
        binding = self._binding(args["execution_profile"], previous)
        if (self.service._project_execution_mode() != args["continuation_mode"]
                or capture["context_sha256"] != args["context_sha256"]
                or wire.digest(binding) != args["execution_binding_sha256"]):
            raise ProjectExecutionRefusal("context_changed")
        source = self._fixed_source(args["work_ref"])
        request = self._request(args)
        grounding = await ingress._observe_trusted_grounding(self.app_binding.grounding_provider)
        intent_id = ceo_request.automated_intent_id(ceo_request.app_request_ref(args["operation_key"]))
        intent = ingress._build_envelope(request, intent_id=intent_id,
            workspace_root=self.service.config.proof_workspace_root, grounding=grounding, strict_v2=True)
        from control_plane.executive_authority import ExecutiveAuthorityPolicy
        contract = intent["execution_contract"]
        ExecutiveAuthorityPolicy.load().authorize(contract["requested_authorities"], worktree=contract["worktree"],
            allowed_write_paths=contract.get("allowed_write_paths"), validation_commands=contract.get("validation_commands"))
        private = dict(schema="mastermind.project_execution_input.v1", work_ref=args["work_ref"],
            request=copy.deepcopy(args), grounding=grounding, dialogue_source=source,
            intent=copy.deepcopy(intent), execution_binding=copy.deepcopy(binding), project=capture["data"],
            previous_run=previous)
        payload = wire.canonical(private)
        if len(payload) > 256 * 1024:
            raise ProjectExecutionRefusal("input_too_large")
        supervisor = self._supervisor()
        existing_input = supervisor.lookup_terminal_original_input(command_id=operation._command, issuer_scope_sha256=scope)
        if existing_input is not None and existing_input.payload != payload:
            raise ProjectExecutionRefusal("operation_conflict")
        input_fingerprint = wire.digest(dict(schema="mastermind.project_execution_input_identity.v1",
            command_id=operation._command, principal_scope=scope, intent_fingerprint=ceo_intent.intent_fingerprint(intent),
            context_sha256=capture["context_sha256"], input_sha256=hashlib.sha256(payload).hexdigest()))

        def current():
            now_operation, _, now_scope, now_stamp = self._authorize(principal, args, fresh=True)
            if (type(self._source_issuer) is not source_owner.ProjectExecutionIssuer
                    or self._source_issuer.service is not self.service
                    or now_operation is not operation or now_scope != scope or now_stamp != stamp
                    or self._binding(args["execution_profile"], previous) != binding
                    or self._fixed_source(args["work_ref"]) != source
                    or self.service._project_execution_mode() != args["continuation_mode"]):
                raise ProjectExecutionRefusal("context_changed")
            # Re-observe canonical CODE/default/Event/permission fences immediately before commit.
            current_view = self.planning._canonical_view(workspace, args["work_ref"])
            if (current_view is None or current_view.code_commit != capture["view"].code_commit
                    or current_view.data_commit != capture["view"].data_commit):
                raise ProjectExecutionRefusal("context_changed")
            current_view.check()
            if self._previous(args, scope, unused=False) != previous:
                raise ProjectExecutionRefusal("context_changed")
            self.planning._require_effect_outside_read(operation)

        current()
        reference = supervisor.prepare_terminal_original_input(command_id=operation._command,
            issuer_scope_sha256=scope, fingerprint_sha256=input_fingerprint, payload=payload)
        if reference is None:
            original = await asyncio.to_thread(self._original, principal, args, submit=True)
            if original is None:
                raise ProjectExecutionRefusal("effect_unknown")
            return dict(operation_key=args["operation_key"], work_ref=args["work_ref"], state="ACCEPTED", receipt=original)
        material = dict(schema=source_owner.SCHEMA, operation_key=args["operation_key"], command_id=operation._command,
            intent_id=intent_id, work_ref=args["work_ref"], intent_fingerprint=ceo_intent.intent_fingerprint(intent),
            arguments_sha256=wire.digest(args), principal_scope_sha256=scope, workspace_permission_sha256=stamp,
            context_sha256=capture["context_sha256"], execution_binding_sha256=wire.digest(binding),
            dialogue_source_sha256=wire.digest(source), input_fingerprint_sha256=input_fingerprint,
            input_reference=reference.to_dict(), continuation_mode=args["continuation_mode"],
            previous_run=args.get("previous_run"))
        def authorize_original():
            self._authorize(principal, args)
        operation._project_execution_authorize = authorize_original
        admitted = source_owner.issue_source(self._source_issuer, operation, material, current)
        def execution_binding():
            current()
            return copy.deepcopy(binding)
        def dialogue_source(_intent, _work):
            if _intent != intent_id or _work != args["work_ref"]:
                raise ProjectExecutionRefusal("context_changed")
            current()
            return copy.deepcopy(source)
        async with self.service._foreground_cycle_scope(operation):
            receipt = await ingress.handle_frame(dict(schema=ingress.SUBMIT_SCHEMA_V2,
                request_ref=ceo_request.app_request_ref(args["operation_key"]),
                observed_grounding=grounding, request=request), runtime=self.service._require_runtime(),
                grounding_provider=self.app_binding.grounding_provider,
                workspace_root=self.service.config.proof_workspace_root, strict_v2_admission=True,
                service_state=self.service._service_state, ceo_ingress_armed=self.app_binding.armed,
                execution_binding_provider=execution_binding, dialogue_source_provider=dialogue_source,
                frontier_selection_provider=self.service._resolve_ceo_frontier_selection,
                project_execution_source=admitted, fresh_admission_observer=operation._bind_admitted_root)
            if operation._root is not None:
                root = self.service._require_runtime().jobs.get_job(operation._root)
                await self._prepare_workspace(root, operation)
                if args["continuation_mode"] == "ATTENDED":
                    await self.service._drive_foreground_cycle(operation, root.job_id)
                # Durable projects are driven by the incumbent service tick
                # after this serial admission reservation is released.
        return dict(operation_key=args["operation_key"], work_ref=args["work_ref"], state="ACCEPTED", receipt=receipt)

    async def handle_frame(self, value):
        value = wire.frame(value)
        principal = VerifiedPrincipal(**{**value["principal"], "scopes": tuple(value["principal"]["scopes"])})
        operation, args = value["operation"], value["arguments"]
        try:
            if operation == "preview":
                data = await self.preview(principal, args)
            elif operation == "submit":
                data = await self.submit(principal, args)
            else:
                receipt = await asyncio.to_thread(self._original, principal, args, submit=False)
                data = dict(operation_key=args["operation_key"], work_ref=args["work_ref"],
                    state="ACCEPTED" if receipt is not None else "NOT_FOUND", receipt=receipt)
            return dict(schema=wire.RESULT_SCHEMA, operation=operation, ok=True, data=data, error=None)
        except Exception as exc:
            if operation == "status":
                # This read cannot resolve a retained submission when authority
                # or storage is unavailable. Do not probe historical effects
                # again, or let their existence change the read's refusal.
                code = exc.code if isinstance(exc, ProjectExecutionRefusal) else "refused"
                return dict(schema=wire.RESULT_SCHEMA, operation=operation, ok=False, data=None,
                            error=dict(code=code, message="Project execution is unavailable for this request"))
            current = current_foreground_operation()
            existing = self.service._require_runtime().store.find_event_by_command_id(current._command)
            code = ("previous_workspace_unavailable" if isinstance(exc, source_owner.PreviousWorkspaceUnavailable) and existing is None
                    else "previous_run_already_continued" if isinstance(exc, source_owner.PreviousRunConflict) and existing is None
                    else "operation_conflict" if isinstance(exc, ProjectExecutionRefusal) and exc.code == "operation_conflict"
                    else "effect_unknown" if existing is not None else
                    exc.code if isinstance(exc, ProjectExecutionRefusal) else "refused")
            return dict(schema=wire.RESULT_SCHEMA, operation=operation, ok=False, data=None,
                        error=dict(code=code, message="Reconcile the original operation" if existing is not None
                                   else "Project execution is unavailable for this request"))


def build_ingress_owner(planning):
    factory = ProjectExecutionAppFactory(planning)
    return wire.ProjectExecutionIngressOwner(factory.handle_frame)
