"""Private installed constructor identity for one existing Fresh pure phase.

This owns no permission, cached grant, Runtime, reader registry or public DTO.
Ordinary factory calls still construct fresh owners. Only the existing nominal
pure phase may retain ONE actual reader, with current source checks each use.
Installed-type/policy validation and source context capture live behind the
integration helper that issues the nominal source binding from the actual
installed source constructor; this core module imports no integrations module.
"""
from dataclasses import dataclass,field
from types import MethodType,FunctionType,CodeType
from inspect import getattr_static

_KEY=object()
_ATTRIBUTE='_installed_workspace_read_provider'
_SOURCE_ATTRIBUTE='_installed_workspace_read_source'


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
class _SourceBinding:
    """Nominal installed source identity issued by the integration constructor.

    Capturing the qualifier/context callback function/code identities plus the
    actual bound read/canonical-owner methods is recognition data only. It
    carries no read authority: every use rechecks the real current policy,
    configuration and runtime state through the unchanged owners.
    """
    key:object
    source:object
    qualifier:object
    qualifier_code:object
    capture:object
    capture_code:object
    read_function:object
    owner_function:object
    guard_function:object
    lifetime:object=field(default_factory=_Lifetime,repr=False)


def _issue_installed_read_source(source,*,qualifier,capture,read_function,owner_function,guard_function):
    """Private nominal issuer; only the installed source constructor calls it.

    No read, grant or registry is created. A fabricated or already-drifted
    source composition is refused before any binding exists.
    """
    if (type(qualifier) is not FunctionType or type(capture) is not FunctionType
            or type(read_function) is not FunctionType or type(owner_function) is not FunctionType
            or not callable(guard_function) or source is None
            or qualifier(source) is not True):_fail()
    binding=_SourceBinding(_KEY,source,qualifier,qualifier.__code__,capture,capture.__code__,
        read_function,owner_function,guard_function)
    binding.lifetime.issuer=binding
    return binding


def installed_read_source_binding(read_bindings):
    """Recognize ONLY the exact nominal binding on its own bound source.

    Arbitrary attributes, truthiness or callables are never an authority. A
    forged carrier or a drifted binding fails closed instead of degrading the
    caller to the legacy composition.
    """
    if type(read_bindings) is not MethodType:return None
    value=getattr_static(read_bindings.__self__,_SOURCE_ATTRIBUTE,None)
    if value is None:return None
    if (type(value) is not _SourceBinding or value.key is not _KEY
            or value.lifetime.issuer is not value or not value.lifetime.active
            or value.source is not read_bindings.__self__
            or type(value.qualifier) is not FunctionType
            or value.qualifier.__code__ is not value.qualifier_code
            or type(value.capture) is not FunctionType
            or value.capture.__code__ is not value.capture_code
            or type(value.read_function) is not FunctionType
            or value.read_function is not read_bindings.__func__
            or type(value.owner_function) is not FunctionType
            or not callable(value.guard_function)):_fail()
    return value


@dataclass(frozen=True,slots=True)
class _Provider:
    key:object
    factory:object
    source_binding:object
    factory_code:object
    closure:tuple
    lifetime:object=field(default_factory=_Lifetime,repr=False)

    def context(self,runtime,*,expected=None):
        if (type(self) is not _Provider or self.key is not _KEY or self.lifetime.issuer is not self
                or not self.lifetime.active or getattr(self.factory,_ATTRIBUTE,None) is not self
                or type(self.factory) is not FunctionType or self.factory.__code__ is not self.factory_code
                or self.factory_code is not _fixed_factory_code()):_fail()
        binding=self.source_binding
        if (type(binding) is not _SourceBinding or binding.key is not _KEY
                or binding.lifetime.issuer is not binding or not binding.lifetime.active
                or binding.source is None
                or type(binding.qualifier) is not FunctionType
                or binding.qualifier.__code__ is not binding.qualifier_code
                or type(binding.capture) is not FunctionType
                or binding.capture.__code__ is not binding.capture_code
                or type(binding.read_function) is not FunctionType
                or type(binding.owner_function) is not FunctionType
                or not callable(binding.guard_function)):_fail()
        cells=tuple(cell.cell_contents for cell in (self.factory.__closure__ or ()))
        current=tuple(ref for value in cells for ref in _references(value))
        if len(current)!=len(self.closure) or any(a is not b for a,b in zip(current,self.closure)):_fail()
        return binding.capture(binding,self.factory,runtime,expected=expected)

    def acquire(self,phase,runtime):
        before=self.context(runtime)
        reader=self.factory(runtime)
        after=self.context(runtime,expected=before)
        if not _same(before,after):_fail()
        from control_plane.workspace_read_service import WorkspaceReadService
        from control_plane.installed_canonical_project_data_binding import _ProjectDataReadBinding
        binding=reader._canonical_project_data
        source=self.source_binding.source
        if (type(reader) is not WorkspaceReadService or reader.runtime is not runtime
                or type(binding) is not _ProjectDataReadBinding or binding.store is not runtime.store
                or binding.owner.collector is not source._collector
                or binding.owner.policy is not source._permissions.policy
                or binding.owner.loader is not source._permissions._load_bindings
                or binding.owner.identity is not source._git):_fail()
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

    Recognition is the exact nominal source binding issued by the installed
    constructor; no arbitrary attribute or callback truthiness qualifies.
    Legacy/custom factories keep their strict existing behavior. A public frame
    cannot select this composition, and the tag grants no READ or mutation.
    """
    binding=installed_read_source_binding(read_bindings)
    if binding is None:
        return factory
    if type(factory) is not FunctionType or factory.__code__ is not _fixed_factory_code():_fail()
    cells=tuple(cell.cell_contents for cell in (factory.__closure__ or ()))
    provider=_Provider(_KEY,factory,binding,factory.__code__,
        tuple(ref for value in cells for ref in _references(value)))
    provider.lifetime.issuer=provider
    setattr(factory,_ATTRIBUTE,provider)
    return factory


def installed_read_provider(factory):
    value=getattr(factory,_ATTRIBUTE,None)
    if value is None:return None
    if (type(value) is not _Provider or value.key is not _KEY or value.factory is not factory
            or value.lifetime.issuer is not value or not value.lifetime.active):_fail()
    return value
