"""Fixed private ingress composition of actual source action owners.

The host's installed factory supplies each concrete owner and qualifies its
source/Git coordinates. This service supplies neither enrollment nor a caller
selected handler. Unimplemented action owners remain unavailable; they cannot
borrow CREATE's grant or publisher mode.
"""
from __future__ import annotations
from contextlib import nullcontext

from common.workspace_source_operation_wire import validate_frame, MAX_RESPONSE_BYTES, operation_response_limit
from common.workspace_source_operation_contract import validate_status
from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.project_creation_service import ProjectCreationSourceOwner
from integrations.mastermind_workspace_app.knowledge_source_service import ProjectKnowledgeSourceOwner
from integrations.mastermind_workspace_app.source_operation_principal import bind_private_source_principal


class WorkspaceSourceOperationService:
    def __init__(self, *, create_owner=None, knowledge_owner=None, plan_proposal_owner=None, adoption_owner=None, journey_recipes=None, host_supervisor=None, runtime_guard=None, canonical_data_source=None):
        from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
        from integrations.mastermind_workspace_app.project_plan_adoption_service import ProjectPlanAdoptionSourceOwner
        from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectJourneyRecipes
        if ((plan_proposal_owner is not None and type(plan_proposal_owner) is not ProjectPlanProposalSourceOwner)
                or (adoption_owner is not None and type(adoption_owner) is not ProjectPlanAdoptionSourceOwner)
                or (journey_recipes is not None and type(journey_recipes) is not InstalledProjectJourneyRecipes)):
            raise ValueError("actual project journey owner required")
        if ((create_owner is not None and type(create_owner) is not ProjectCreationSourceOwner)
                or (knowledge_owner is not None and type(knowledge_owner) is not ProjectKnowledgeSourceOwner)
                or (create_owner is None and knowledge_owner is None and plan_proposal_owner is None and adoption_owner is None)):
            raise ValueError("actual source action owner required")
        if runtime_guard is not None and not callable(runtime_guard):
            raise ValueError("actual installed Runtime guard required")
        self._runtime_guard = runtime_guard
        if canonical_data_source is not None:
            from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
            if type(canonical_data_source) is not InstalledCanonicalProjectData:
                raise ValueError("actual canonical DATA source owner required")
        self._canonical_data_source = canonical_data_source
        self._create, self._knowledge = create_owner, knowledge_owner
        self._proposal, self._journey_recipes = plan_proposal_owner, journey_recipes
        self._adoption = adoption_owner
        owners = [owner for owner in (create_owner, knowledge_owner, plan_proposal_owner, adoption_owner) if owner is not None]
        self._store, self._supervisor = owners[0]._events.store, owners[0]._private.supervisor
        if any(owner._events.store is not self._store or owner._private.supervisor is not self._supervisor
               for owner in owners):
            raise ValueError("source action owners must share the actual Runtime/private owner")
        if canonical_data_source is not None and canonical_data_source.events.store is not self._store:
            raise ValueError("canonical DATA must use the same actual Runtime owner")
        if host_supervisor is not None:
            from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
            if (type(host_supervisor) is not MixedExecutionOwnerSupervisor
                    or host_supervisor.primary is not self._supervisor
                    or host_supervisor.runtime.store is not self._store):
                raise ValueError("source private custody must be the actual host primary")
            self._supervisor = host_supervisor


    def handle(self, frame, *, peer_guard):
        """Called only inside the existing App-peer host capability bracket."""
        request = validate_frame(frame)
        def guarded_peer():
            return peer_guard() is True and (self._runtime_guard is None or self._runtime_guard() is True)
        principal = bind_private_source_principal(request["principal"],
            verified_expires_at=request["verified_expires_at"], peer_guard=guarded_peer)
        value, operation = request["request"], request["operation"]
        if operation == "options":
            if self._create is None or self._journey_recipes is None:raise ValueError("SOURCE_OPERATION_OWNER_UNAVAILABLE")
            permission=self._create._permission(principal)
            result=self._journey_recipes.options()
            if not permission.check() or not guarded_peer():raise PermissionError("SOURCE_OPERATION_UNAVAILABLE")
            result['owner_context']={'principal_scope':permission.principal_scope}
            if len(canonical(result))+1>MAX_RESPONSE_BYTES or not guarded_peer():
                raise PermissionError('SOURCE_OPERATION_UNAVAILABLE')
            return result
        if value["action"] == "publish_project_proposal":
            owner = self._create
        elif value["action"] == "publish_project_plan_proposal":
            owner = self._proposal
            if operation == "prepare":
                raise ValueError("SAME_S19_PREPARATION_REQUIRED")
        elif value["action"] == "ADOPT_PLAN":
            owner = self._adoption
        elif value["action"] in {"add_project_file", "set_project_communication_preference", "correct_project_discovery"}:
            owner = self._knowledge
        else:
            owner = None
        if owner is None or (operation == "advance" and owner is not self._adoption):
            raise ValueError("SOURCE_OPERATION_OWNER_UNAVAILABLE")
        needs_data = operation == "prepare"
        if operation == "submit" and type(owner) is ProjectKnowledgeSourceOwner:
            basic = {"schema": "mastermind.workspace_source_operation_lookup.v1",
                     **{key:value[key] for key in ("action", "request_id", "work_ref")}}
            permission = owner._permission(principal,basic)
            status = owner._events.read_status(basic,permission.principal_scope,guard=permission.check)
            needs_data = (status["disposition"] == "unknown" and status["receipt"] is not None
                          and status["receipt"]["kind"] == "INTENT")
        scope = nullcontext()
        if needs_data and type(owner) is ProjectKnowledgeSourceOwner and self._canonical_data_source is not None:
            work_ref = value["request"]["work_ref"] if operation == "prepare" else value["work_ref"]
            scope = self._canonical_data_source.compilation_scope(principal,work_ref=work_ref)
        with scope:
            if operation == "prepare":
                result = owner.prepare(value["request"], principal)
            elif operation == "read":
                result = owner.read_status(value, principal)
            elif operation == "read_original" and type(owner) is ProjectKnowledgeSourceOwner:
                result = owner.read_original(value, principal)
            elif operation == "reconcile":
                result = owner.reconcile(value, principal)
            elif operation == "submit":
                lookup = {"schema": "mastermind.workspace_source_operation_lookup.v1",
                          **{k: value[k] for k in ("action", "request_id", "work_ref")}}
                result = owner.submit(lookup=lookup, preview_witness=value["preview_witness"], principal=principal)
            elif operation == "advance":
                result = owner.advance(value, principal)
            else:
                raise ValueError("SOURCE_OPERATION_OWNER_UNAVAILABLE")
        if operation not in {"prepare", "read_original"}:
            result = validate_status(result)
        if len(canonical(result)) + 1 > operation_response_limit(operation) or guarded_peer() is not True:
            raise PermissionError("SOURCE_OPERATION_UNAVAILABLE")
        return result

    def _context_binding(self):
        # Stable identities only. Actual permission/expiry and publisher/source
        # qualification still recheck through their original action owner.
        def context(owner):
            if owner is None:
                return None
            common = (owner, owner._events, owner._private, owner._permissions, owner._adapter,
                      owner._binding, owner._qualifier, owner._pr_owner,
                      owner._permissions.policy, owner._permissions._load_bindings, owner._permissions._now,
                      owner.prepare, owner.submit, owner.read_status, owner.reconcile)
            if type(owner) is ProjectCreationSourceOwner:
                from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectCreationRecipeAdapter
                return common + ((owner._adapter._recipes.context,) if type(owner._adapter) is InstalledProjectCreationRecipeAdapter else (owner._adapter._compile_proposal,))
            if owner is self._proposal:
                return common + (owner._basis,owner._result,owner._actor,owner._qualify_recipe)
            if owner is self._adoption:
                from integrations.mastermind_workspace_app.installed_plan_adoption import InstalledPlanAdoptionRecipeAdapter
                if type(owner._adapter) is not InstalledPlanAdoptionRecipeAdapter:
                    raise ValueError("actual installed plan adoption adapter required")
                return common + (owner._capture,owner._actor,owner._qualify_recipe,
                                 owner.advance,owner._adapter._recipes.context)
            return common + (owner.read_original, owner._private.read, owner._publisher_events, owner._adapter._compiler,
                             owner._adapter._compiler._installed_reader_binding,
                             owner._adapter._compiler._installed_context_owner,
                             owner._adapter._compiler._installed_context_binding)
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        host = None if type(self._supervisor) is not MixedExecutionOwnerSupervisor else (
            self._supervisor.primary, tuple(self._supervisor.owners.items()), self._supervisor.runtime)
        return (self._store, self._supervisor, self._runtime_guard,
                None if self._canonical_data_source is None else self._canonical_data_source.context_binding(), host, context(self._create), context(self._knowledge), context(self._proposal), context(self._adoption), self._journey_recipes)

    def prepare_project_plan_proposal(self, request, principal, *, basis, result):
        from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
        if (type(self) is not WorkspaceSourceOperationService
                or type(self._proposal) is not ProjectPlanProposalSourceOwner):
            raise ValueError("SOURCE_OPERATION_UNAVAILABLE")
        return self._proposal.prepare_qualified(request, principal, basis=basis, result=result)

    def installed_binding(self):
        """Private installed factory composition; construction grants nothing."""
        from control_plane.workspace_source_operation_binding import _issue_source_operation_binding
        return _issue_source_operation_binding(self,
            qualified_owner=lambda owner: type(owner) is WorkspaceSourceOperationService,
            proposal_callback=self.prepare_project_plan_proposal)
