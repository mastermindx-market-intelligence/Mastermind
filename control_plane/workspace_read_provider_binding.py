"""Private installed constructor identity for one existing Fresh pure phase.

This owns no permission, cached grant, Runtime, reader registry or public DTO.
Ordinary factory calls still construct fresh owners. Only the existing nominal
pure phase may retain ONE actual reader, with current source checks each use.
"""
from dataclasses import dataclass,field,astuple
from types import MethodType,FunctionType,CodeType
import json

_KEY=object()
_ATTRIBUTE='_installed_workspace_read_provider'


def _fail():raise ValueError('CONVERSATION_PROJECT_CHANGED')


def _fixed_factory_code():
    from control_plane.workspace_read_service import workspace_provider_factory
    rows=[value for value in workspace_provider_factory.__code__.co_consts
        if type(value) is CodeType and value.co_name=='provide']
    if len(rows)!=1:_fail()
    return rows[0]


def _references(value):
    if type(value) is MethodType:return (value.__self__,value.__func__,value.__func__.__code__)
    if type(value) is FunctionType:return (value,value.__code__)
    return (value,)


def _same(first,second):
    return (len(first[0])==len(second[0]) and all(a is b for a,b in zip(first[0],second[0]))
        and first[1]==second[1])


@dataclass(slots=True)
class _Lifetime:
    issuer:object=None
    active:bool=True


@dataclass(frozen=True,slots=True)
class _Provider:
    key:object
    factory:object
    source:object
    read_function:object
    owner_function:object
    factory_code:object
    closure:tuple
    lifetime:object=field(default_factory=_Lifetime,repr=False)

    def context(self,runtime,*,expected=None):
        from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
        from integrations.business_mcp_auth.contracts import validate_resource_policy
        from integrations.mastermind_workspace_app.project_git_identity import InstalledProjectGitIdentity
        from integrations.executive_mcp.installed import InstalledBootPacketCollector
        from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
        if (type(self) is not _Provider or self.key is not _KEY or self.lifetime.issuer is not self
                or not self.lifetime.active or getattr(self.factory,_ATTRIBUTE,None) is not self
                or type(self.factory) is not FunctionType or self.factory.__code__ is not self.factory_code
                or self.factory_code is not _fixed_factory_code()
                or type(self.source) is not InstalledWorkspaceSourceOperations
                or type(self.source.read_bindings) is not MethodType
                or self.source.read_bindings.__func__ is not self.read_function
                or type(self.source).__dict__.get('read_bindings') is not self.read_function
                or type(self.source.canonical_data_owner) is not MethodType
                or self.source.canonical_data_owner.__func__ is not self.owner_function
                or type(self.source).__dict__.get('canonical_data_owner') is not self.owner_function):_fail()
        cells=tuple(cell.cell_contents for cell in (self.factory.__closure__ or ()))
        current=tuple(ref for value in cells for ref in _references(value))
        if len(current)!=len(self.closure) or any(a is not b for a,b in zip(current,self.closure)):_fail()
        source=self.source;permissions=source._permissions;collector=source._collector;identity=source._git
        if (type(permissions) is not WorkspaceSourceOperationContextFactory
                or type(collector) is not InstalledBootPacketCollector or type(identity) is not InstalledProjectGitIdentity):_fail()
        # These remain actual CURRENT checks. No policy parser or config/grant
        # loader is bypassed, and this never calls a provider/GitHub account.
        policy=validate_resource_policy(permissions.policy)
        values=(source,permissions,permissions.policy,permissions._load_bindings,source._runtime_guard,
            collector,identity,identity.binding,identity._path,runtime,runtime.store,
            collector._source_root,collector._macro_root,collector._code_root,collector._python,
            collector._runner,permissions._now,self.read_function,self.owner_function,
            identity._configuration,identity.qualify,collector.read_project_plan,collector.read_project_discovery,
            collector.read_project_knowledge_catalogue,collector.read_project_knowledge_memory,
            collector.read_project_knowledge_source,collector.canonical_project_data_scope,
            collector.canonical_project_compilation_scope,collector._collect_packet,
            collector._capture_canonical_code,collector._bind_canonical_code_capture)
        source_fields=tuple(sorted(vars(source).items()))
        refs=tuple(ref for value in (*values,*(value for _,value in source_fields)) for ref in _references(value))
        # Mutable constructor metadata is compared, not retained as current.
        constructor=dict(zip(self.factory.__code__.co_freevars,cells))
        literals=(tuple(name for name,_ in source_fields),astuple(policy),identity.binding.fingerprint,identity._expected,
            json.dumps(identity._selection,sort_keys=True,separators=(',',':')),
            collector._expected_source_sha,collector._allow_synthetic_fixture,
            json.dumps(constructor.get('armed'),sort_keys=True,separators=(',',':')),
            json.dumps(constructor.get('runtime_identity'),sort_keys=True,separators=(',',':')))
        context=refs,literals
        if expected is not None and not _same(expected,context):_fail()
        # Reject descriptor drift before invoking any changed current callback.
        if source._runtime_guard(runtime) is not True:_fail()
        identity._configuration()
        return context

    def acquire(self,phase,runtime):
        before=self.context(runtime)
        reader=self.factory(runtime)
        after=self.context(runtime,expected=before)
        if not _same(before,after):_fail()
        from control_plane.workspace_read_service import WorkspaceReadService
        from control_plane.installed_canonical_project_data_binding import _ProjectDataReadBinding
        binding=reader._canonical_project_data
        if (type(reader) is not WorkspaceReadService or reader.runtime is not runtime
                or type(binding) is not _ProjectDataReadBinding or binding.store is not runtime.store
                or binding.owner.collector is not self.source._collector
                or binding.owner.policy is not self.source._permissions.policy
                or binding.owner.loader is not self.source._permissions._load_bindings
                or binding.owner.identity is not self.source._git):_fail()
        lease=_ReaderLease(_KEY,self,phase,runtime,reader,binding,before,
            (phase.owner,phase.principal,phase.workspace,phase.work_ref))
        lease.lifetime.issuer=lease
        return lease


@dataclass(frozen=True,slots=True)
class _ReaderLease:
    key:object
    provider:object
    phase:object
    runtime:object
    reader:object
    binding:object
    context:tuple
    phase_identity:tuple
    lifetime:object=field(default_factory=_Lifetime,repr=False)

    def current(self,phase,factory,runtime):
        from control_plane.fresh_conversation_membership import _binding_current
        from control_plane.project_canonical_data import _CAPTURE
        if (type(self) is not _ReaderLease or self.key is not _KEY or self.lifetime.issuer is not self
                or not self.lifetime.active or phase is not self.phase or factory is not self.provider.factory
                or runtime is not self.runtime or phase.owner._app.workspace_read_provider_factory is not factory
                or getattr(phase.owner,"_project_validation_phase",None) is not phase
                or not phase.active or phase.view is None
                or phase.capture is None or _CAPTURE.get() is not phase.capture
                or phase.capture.view is not phase.view or phase.reader is not self.reader
                or phase.binding is not self.binding
                or any(a is not b for a,b in zip((phase.owner,phase.principal,phase.workspace),self.phase_identity[:3]))
                or phase.work_ref!=self.phase_identity[3]
                or self.reader._canonical_project_data is not self.binding
                or not _same(self.context,self.provider.context(runtime,expected=self.context))
                or not _binding_current(self.binding)):_fail()
        phase.view.check()
        return self.reader

    def finish(self,phase,factory,runtime):
        """Current constructor/binding check AFTER the blocking full DATA post.

        The read scope is already closed. This cannot authorize another read
        with that view or extend its deadline; caller follows with liveness.
        """
        from control_plane.fresh_conversation_membership import _binding_current
        if (type(self) is not _ReaderLease or self.key is not _KEY or self.lifetime.issuer is not self
                or not self.lifetime.active or phase is not self.phase or factory is not self.provider.factory
                or runtime is not self.runtime or phase.owner._app.workspace_read_provider_factory is not factory
                or getattr(phase.owner,"_project_validation_phase",None) is not phase
                or phase.active or phase.capture is None or phase.capture.active
                or phase.reader is not self.reader or phase.binding is not self.binding
                or any(a is not b for a,b in zip((phase.owner,phase.principal,phase.workspace),self.phase_identity[:3]))
                or phase.work_ref!=self.phase_identity[3]
                or self.reader._canonical_project_data is not self.binding
                or not _binding_current(self.binding)
                or not _same(self.context,self.provider.context(runtime,expected=self.context))):_fail()

    def close(self):
        self.lifetime.active=False;self.lifetime.issuer=None


def bind_installed_read_provider(factory,read_bindings):
    """Only the actual installed source factory receives this private tag.

    Legacy/custom factories keep their strict existing behavior. A public frame
    cannot select this composition, and the tag grants no READ or mutation.
    """
    from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
    if type(read_bindings) is not MethodType or type(read_bindings.__self__) is not InstalledWorkspaceSourceOperations:
        return factory
    if type(factory) is not FunctionType or factory.__code__ is not _fixed_factory_code():_fail()
    source=read_bindings.__self__
    if read_bindings.__func__ is not type(source).__dict__.get('read_bindings'):_fail()
    cells=tuple(cell.cell_contents for cell in (factory.__closure__ or ()))
    provider=_Provider(_KEY,factory,source,read_bindings.__func__,source.canonical_data_owner.__func__,
        factory.__code__,tuple(ref for value in cells for ref in _references(value)))
    provider.lifetime.issuer=provider
    setattr(factory,_ATTRIBUTE,provider)
    return factory


def installed_read_provider(factory):
    value=getattr(factory,_ATTRIBUTE,None)
    if value is None:return None
    if (type(value) is not _Provider or value.key is not _KEY or value.factory is not factory
            or value.lifetime.issuer is not value or not value.lifetime.active):_fail()
    return value
