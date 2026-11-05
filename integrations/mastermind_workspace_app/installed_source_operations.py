"""Installed fixed source-action factory over the incumbent Control owners.

Construction is network/effect inert. The actual boot composes this from its
sealed policy/loader, installed collector and independent root-sealed service
Git identity. HTTP/client inputs cannot supply any factory or source path.
"""
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_source_operations import SourceOperationEvents
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.project_git_identity import InstalledProjectGitIdentity
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from integrations.mastermind_workspace_app.knowledge_publisher_events import KnowledgePublisherEvents
from integrations.mastermind_workspace_app.knowledge_recipe_adapter import ProjectKnowledgeRecipeAdapter
from integrations.mastermind_workspace_app.knowledge_source_service import ProjectKnowledgeSourceOwner
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService


class InstalledWorkspaceSourceOperations:
    def __init__(self, *, collector, policy, load_bindings, git_identity, runtime_guard):
        if (type(collector) is not InstalledBootPacketCollector
                or type(git_identity) is not InstalledProjectGitIdentity
                or not callable(load_bindings) or not callable(runtime_guard)):
            raise TypeError('actual installed source owners required')
        from pathlib import Path
        writer = Path(git_identity.binding.worktree).resolve()
        if any(writer == root or writer.is_relative_to(root) or root.is_relative_to(writer)
               for root in (collector._macro_root, collector._source_root, collector._code_root)):
            raise ValueError('source publisher must use its separate qualified clone')
        self._collector, self._git = collector, git_identity
        self._permissions = WorkspaceSourceOperationContextFactory(policy=policy,load_bindings=load_bindings)
        self._runtime_guard = runtime_guard
        self._compiler = collector.project_knowledge_recipe_reader(macro_root=collector._macro_root)
        from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectJourneyRecipes
        self._journey = InstalledProjectJourneyRecipes(collector)

    def __call__(self, runtime, supervisor):
        if type(runtime) is not Runtime:
            raise ValueError('SOURCE_OPERATION_UNAVAILABLE')
        if type(supervisor) is ExecutiveSupervisor:
            primary = supervisor
            host = None
        elif type(supervisor) is MixedExecutionOwnerSupervisor:
            primary,host = supervisor.primary,supervisor
        else:
            raise ValueError('SOURCE_OPERATION_UNAVAILABLE')
        if type(primary) is not ExecutiveSupervisor or primary.runtime is not runtime:
            raise ValueError('SOURCE_OPERATION_UNAVAILABLE')
        if self._runtime_guard(runtime) is not True:
            raise PermissionError('SOURCE_OPERATION_UNAVAILABLE')
        # Current principal/action guards apply to every request. Event-only
        # status does not acquire Git credentials, Macro or private contents;
        # the actual Git identity owner requalifies before each Git/API read
        # or effect when publication/reconciliation invokes it.
        events = SourceOperationEvents(runtime.store)
        private = ProjectSourceOriginalInput(primary)
        contexts = self._permissions
        event_adapter = KnowledgePublisherEvents(events=events,contexts=contexts)
        from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
        data = InstalledCanonicalProjectData(collector=self._collector,policy=contexts.policy,
            load_bindings=contexts._load_bindings,git_identity=self._git,events=events,
            runtime_guard=lambda:self._runtime_guard(runtime))
        owner = ProjectKnowledgeSourceOwner(events=events,private_inputs=private,permission_factory=contexts,
            adapter=ProjectKnowledgeRecipeAdapter(self._compiler),publisher_events=event_adapter,
            publisher_binding=self._git.binding,qualify_publisher=data.qualify_publisher,pr_owner=self._git)
        from integrations.mastermind_workspace_app.project_journey_recipes import (
            InstalledProjectCreationRecipeAdapter, InstalledProjectPlanProposalRecipeAdapter)
        from integrations.mastermind_workspace_app.project_creation_service import ProjectCreationSourceOwner
        from integrations.mastermind_workspace_app.project_plan_proposal_service import ProjectPlanProposalSourceOwner
        from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
        create = ProjectCreationSourceOwner(events=events,private_inputs=private,permission_factory=contexts,
            adapter=InstalledProjectCreationRecipeAdapter(self._journey),publisher_binding=self._git.binding,
            qualify_publisher=data.qualify_publisher,pr_owner=self._git)
        def unavailable(*args):
            raise ValueError('SAME_S19_PREPARATION_REQUIRED')
        def recipe_qualified(principal,prepared,recipe,phase):
            return (phase == 'PUBLICATION' and recipe.get('action') == 'publish_project_plan_proposal'
                and prepared.private_payload()['actor'] == {'principal_id':'workspace:'+source_principal_scope(principal)}
                and self._runtime_guard(runtime) is True)
        proposal = ProjectPlanProposalSourceOwner(events=events,private_inputs=private,permission_factory=contexts,
            adapter=InstalledProjectPlanProposalRecipeAdapter(self._journey),capture_basis=unavailable,
            capture_result=unavailable,actor_for=lambda principal: {'principal_id':'workspace:'+source_principal_scope(principal)},
            qualify_recipe=recipe_qualified,publisher_binding=self._git.binding,
            qualify_publisher=data.qualify_publisher,pr_owner=self._git)
        service = WorkspaceSourceOperationService(create_owner=create,knowledge_owner=owner,
            plan_proposal_owner=proposal,journey_recipes=self._journey,host_supervisor=host,
            runtime_guard=lambda: self._runtime_guard(runtime),canonical_data_source=data)
        if self._runtime_guard(runtime) is not True:
            raise PermissionError('SOURCE_OPERATION_UNAVAILABLE')
        return service.installed_binding()
