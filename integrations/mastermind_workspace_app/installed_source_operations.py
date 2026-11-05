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
        # Private nominal read-source recognition only; issued once, by the
        # actual installed constructor, through the integration helper.
        from integrations.mastermind_workspace_app.installed_read_provider_binding import install_installed_read_source
        install_installed_read_source(self)

    def canonical_data_owner(self, runtime):
        """Same installed owner construction for READ and source operations.

        READ needs no writable Supervisor/private-input owner. No owner cache,
        config copy, registry or grant is created here.
        """
        if type(runtime) is not Runtime or self._runtime_guard(runtime) is not True:
            raise PermissionError('SOURCE_OPERATION_UNAVAILABLE')
        from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
        return InstalledCanonicalProjectData(collector=self._collector, policy=self._permissions.policy,
            load_bindings=self._permissions._load_bindings, git_identity=self._git,
            events=SourceOperationEvents(runtime.store), runtime_guard=lambda:self._runtime_guard(runtime))

    def read_bindings(self, runtime):
        """One actual DATA owner issues the two fixed READ bindings together."""
        from integrations.mastermind_workspace_app.project_discovery import InstalledProjectDiscovery
        data = self.canonical_data_owner(runtime)
        return data.installed_binding(), InstalledProjectDiscovery(data).installed_binding()

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
        data = self.canonical_data_owner(runtime)
        events = data.events
        private = ProjectSourceOriginalInput(primary)
        contexts = self._permissions
        event_adapter = KnowledgePublisherEvents(events=events,contexts=contexts)
        owner = ProjectKnowledgeSourceOwner(events=events,private_inputs=private,permission_factory=contexts,
            adapter=ProjectKnowledgeRecipeAdapter(self._compiler),publisher_events=event_adapter,
            publisher_binding=self._git.binding,qualify_publisher=data.qualify_publisher,pr_owner=self._git)
        from integrations.mastermind_workspace_app.project_journey_recipes import InstalledProjectCreationRecipeAdapter
        from integrations.mastermind_workspace_app.project_creation_service import ProjectCreationSourceOwner
        create = ProjectCreationSourceOwner(events=events,private_inputs=private,permission_factory=contexts,
            adapter=InstalledProjectCreationRecipeAdapter(self._journey),publisher_binding=self._git.binding,
            qualify_publisher=data.qualify_publisher,pr_owner=self._git)
        from integrations.mastermind_workspace_app.installed_project_plan_proposal import build_installed_project_plan_proposal
        proposal = build_installed_project_plan_proposal(events=events,private_inputs=private,
            contexts=contexts,journey=self._journey,data=data,git_identity=self._git)
        from integrations.mastermind_workspace_app.installed_plan_adoption import build_plan_adoption_owner
        adoption = build_plan_adoption_owner(collector=self._collector,data=data,
            events=events,private_inputs=private,contexts=contexts,git_identity=self._git)
        service = WorkspaceSourceOperationService(create_owner=create,knowledge_owner=owner,
            plan_proposal_owner=proposal,adoption_owner=adoption,
            journey_recipes=self._journey,host_supervisor=host,
            runtime_guard=lambda: self._runtime_guard(runtime),canonical_data_source=data)
        if self._runtime_guard(runtime) is not True:
            raise PermissionError('SOURCE_OPERATION_UNAVAILABLE')
        return service.installed_binding()
