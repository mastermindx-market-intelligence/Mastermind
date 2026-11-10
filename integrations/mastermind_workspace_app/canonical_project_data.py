"""Installed READ+latest-DATA acquisition, separate from every source action.

No callback or caller SourceRef is publication authority. The nominal fixed
publisher qualifies the actual default/Events, while this integration binds the
same verified Workspace owner, configured collector and Runtime namespace.
"""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
import base64
import hashlib
import json
import time

from control_plane.workspace_source_operations import SourceOperationEvents
from control_plane.workspace_project_git_publisher import FixedProjectGitPublisher
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.project_git_identity import InstalledProjectGitIdentity
from integrations.mastermind_workspace_app.contract import workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document, workspace_project_authorizers
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_frame, source_principal_scope


_ACTIVE_COMPILATION_VIEW=ContextVar("installed_source_compilation_data",default=None)

@dataclass(frozen=True,slots=True)
class _ReadPrincipal:
    owner: object
    frame_bytes: bytes


class InstalledCanonicalProjectData:
    def __init__(self, *, collector, policy, load_bindings, git_identity, events, runtime_guard):
        if (type(collector) is not InstalledBootPacketCollector or type(git_identity) is not InstalledProjectGitIdentity
                or type(events) is not SourceOperationEvents or not callable(load_bindings) or not callable(runtime_guard)):
            raise TypeError('actual installed canonical data owners required')
        self.collector,self.policy,self.loader,self.identity,self.events=collector,policy,load_bindings,git_identity,events
        self.runtime_guard=runtime_guard
        _,self.read=workspace_authorizers(policy=policy,load_bindings=lambda:legacy_workspace_document(load_bindings(),policy))
        _,self.latest=workspace_project_authorizers(policy=policy,load_bindings=load_bindings,action='read_latest_project_data')

    def context_binding(self):
        collector=self.collector
        return (collector, self.policy, self.loader, self.identity, self.events, self.events.store,
            self.runtime_guard, self.read, self.latest,
            self.identity.binding,self.identity._path,self.identity._expected,
            json.dumps(self.identity._selection,sort_keys=True,separators=(',',':')),
            collector.read_project_knowledge_catalogue,collector.read_project_knowledge_memory,
            collector.read_project_knowledge_source,collector.read_project_discovery_source,collector.read_project_plan,collector.canonical_project_data_scope,collector._collect_packet,
            collector.read_current_agentos_context,
            collector.canonical_project_compilation_scope,
            collector._source_root,collector._macro_root,collector._code_root,collector._python,
            collector._expected_source_sha,collector._allow_synthetic_fixture)

    def installed_binding(self):
        from control_plane.installed_canonical_project_data_binding import _issue_project_data_read
        return _issue_project_data_read(self,qualifier=lambda owner:type(owner) is InstalledCanonicalProjectData)

    def _frame(self,principal):
        if self.runtime_guard() is not True:raise PermissionError('CANONICAL_DATA_UNAVAILABLE')
        if type(principal) is _ReadPrincipal:
            if principal.owner is not self:raise PermissionError('CANONICAL_DATA_UNAVAILABLE')
            frame=json.loads(principal.frame_bytes)
        else:
            if not 0<=int(time.time())<principal.expires_at:raise PermissionError('CANONICAL_DATA_UNAVAILABLE')
            frame=source_principal_frame(principal)
        # Actual frame gates own the closed six-field identity and current
        # sealed enrollment. Hashing a browser label is never a fallback.
        if self.read(frame) is not True:raise PermissionError('CANONICAL_DATA_UNAVAILABLE')
        return frame

    def _scope(self,principal):
        frame=self._frame(principal)
        if type(principal) is not _ReadPrincipal:return source_principal_scope(principal)
        return hashlib.sha256(json.dumps(frame,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

    def _read_stamp(self,principal):return self.read.binding_digest(self._frame(principal))
    def _latest_stamp(self,principal):return self.latest.binding_digest(self._frame(principal))
    def _can_read(self,principal):
        # _frame already checks the actual current Runtime/principal/READ gate.
        # Do not immediately reload that identical gate a second time; each
        # callback still obtains its own fresh check and retains no grant truth.
        try:self._frame(principal);return True
        except (ValueError,PermissionError,TypeError):return False
    def _can_latest(self,principal):
        try:return self.latest(self._frame(principal)) is True
        except (ValueError,PermissionError,TypeError):return False

    def view(self,principal,*,work_ref):
        frame=self._frame(principal)
        if self.latest(frame) is not True:return None
        # Acquire the actual configured CODE pin lazily. Original operation GET
        # and reconciliation never call this method or refresh Macro source.
        capture=self.collector._capture_canonical_code()
        code=capture.observations[1]
        def no_compile(*args):raise ValueError('SOURCE_WRITE_NOT_AVAILABLE')
        publisher=FixedProjectGitPublisher(self.identity.binding,no_compile,lambda _:False,lambda _:'',
            self.identity.qualify,self.identity,principal_scope=self._scope,
            canonical_data_macro_root=str(self.collector._macro_root),canonical_data_code_commit=code,
            authorize_workspace_read=self._can_read,workspace_read_permission_stamp=self._read_stamp,
            authorize_latest_project_data=self._can_latest,latest_project_data_permission_stamp=self._latest_stamp,
            canonical_data_events=self.events)
        view=publisher.observe_canonical_project_data(principal,work_ref=work_ref)
        self.collector._bind_canonical_code_capture(capture,view)
        return view

    @contextmanager
    def compilation_scope(self,principal,*,work_ref):
        view=self.view(principal,work_ref=work_ref)
        token=_ACTIVE_COMPILATION_VIEW.set((self,view))
        try:
            if view is None:
                yield None
            else:
                with self.collector.canonical_project_compilation_scope(view,work_ref=work_ref):yield view
        finally:
            if view is not None:self.collector._discard_canonical_code_capture(view)
            _ACTIVE_COMPILATION_VIEW.reset(token)

    def qualify_publisher(self,binding):
        active=_ACTIVE_COMPILATION_VIEW.get()
        try:
            if active is not None:
                if active[0] is not self:return False
                if active[1] is not None:
                    view=active[1]
                    # Publication is fenced by its own distinct action, live
                    # claim and exact original-N CAS in the fixed publisher.
                    # A spent READ view is never renewed as write authority.
                    # Recheck only its actual current READ/latest grants here;
                    # compiler captures retain the full bounded DATA bracket.
                    operation=view._operation
                    if (view._owner.permission(operation.principal,operation)!=operation.stamp
                            or view._owner.publisher._principal_scope(operation.principal)!=operation.scope):
                        return False
            return self.identity.qualify(binding)
        except (ValueError,PermissionError):return False

    def read_plan(self,principal_frame,*,operation,selection):
        # This fixed READ entry shares the existing opaque installed DATA owner.
        # Newly created projects are qualified by their actual publication Event,
        # never by a browser WorkRef or an unchanged-DATA fallback.
        if operation != 'project_plan':raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        from common.workspace_project_plan_contract import validate_selection, validate_body
        selected=validate_selection(selection)
        encoded=json.dumps(principal_frame,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        principal=_ReadPrincipal(self,encoded)
        view=self.view(principal,work_ref=selected['work_ref'])
        if view is None:return None
        try:
            with view.capture_scope():
                with self.collector.canonical_project_data_scope(view,work_ref=selected['work_ref']):
                    body=validate_body(self.collector.read_project_plan(**selected))
                witness=view.witness()
        finally:self.collector._discard_canonical_code_capture(view)
        generation=hashlib.sha256(json.dumps({'code':view.code_commit,'data':view.data_commit,
            'witness':witness},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return body,view,generation

    def read_context(self,principal_frame,*,operation,selection):
        """Full context under the same independently authorized DATA owner.

        The caller must already have authenticated the Workspace principal.
        Neither this nominal method nor a COO identity converts a credential.
        """
        if operation != 'agentos_current_context':raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        from common.workspace_project_plan_contract import validate_selection
        from control_plane.agentos_context_bundle import validate_current_context_read
        selected=validate_selection(selection)
        encoded=json.dumps(principal_frame,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        principal=_ReadPrincipal(self,encoded)
        view=self.view(principal,work_ref=selected['work_ref'])
        if view is None:return None
        try:
            with view.capture_scope():
                with self.collector.canonical_project_data_scope(view,work_ref=selected['work_ref']):
                    raw,receipt=self.collector.read_current_agentos_context(work_ref=selected['work_ref'])
                validate_current_context_read(raw,receipt,work_ref=selected['work_ref'])
                witness=view.witness()
                if receipt['data_observation']!=witness:raise ValueError('CANONICAL_DATA_UNAVAILABLE')
        finally:self.collector._discard_canonical_code_capture(view)
        body={'bundle_encoding':'base64','bundle_base64':base64.b64encode(raw).decode('ascii'),'receipt':receipt}
        generation=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),
            ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        return body,view,generation

    def read_knowledge(self,principal_frame,*,operation,selection):
        # This method is reached only through the installed lower binding and
        # the existing authenticated Workspace read service, never public JSON.
        encoded=json.dumps(principal_frame,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        principal=_ReadPrincipal(self,encoded)
        view=self.view(principal,work_ref=selection['work_ref'])
        if view is None:return None
        readers={'project_knowledge_catalogue':self.collector.read_project_knowledge_catalogue,
                 'project_knowledge_memory':self.collector.read_project_knowledge_memory,
                 'project_knowledge_source':self.collector.read_project_knowledge_source,
                 'project_discovery_source':self.collector.read_project_discovery_source}
        # One pure installed READ capture, inside this view's original budget.
        # Nested collector/source checks retain live permissions while reusing
        # immutable C/N facts; full default/config/Event fences bracket capture.
        try:
            with view.capture_scope():
                with self.collector.canonical_project_data_scope(view,work_ref=selection['work_ref']):
                    body=readers[operation](**selection)
                witness=view.witness()
        finally:self.collector._discard_canonical_code_capture(view)
        generation=hashlib.sha256(json.dumps({'code':view.code_commit,'data':view.data_commit,
            'closure':witness['reader_closure_sha256'],'scope':view._operation.scope,
            'permission':view._operation.stamp,'event':witness['source_operation']},
            sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        return body,view,generation
