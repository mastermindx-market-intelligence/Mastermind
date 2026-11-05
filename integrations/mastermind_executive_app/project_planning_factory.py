"""Authenticated first-request factory over the existing native Executive owner.

No route, provider, receipt or store is installed here. The existing App edge
verifies its submit policy and binds its actual HTTP foreground invocation;
its sealed Workspace owner independently supplies publication READ custody.
Only this typed project namespace uses the fixed protected commission.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from pathlib import Path
import dataclasses
import hashlib
import json
import time

from control_plane import direct_native_execution as native
from control_plane import project_planning_admission as planning
from control_plane.project_planning_policy import PlanningPolicy, read_protected_blob, COMMISSION_PATH
from control_plane.executive_runtime import EXECUTIVE_DIALOGUE_SOURCE_SCHEMA
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app.admission import principal_authorizes_submit
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_executive_app.principal_namespace import principal_scope_from_identity
from control_plane.foreground_operation import current_foreground_operation

_ROOT_REPOSITORY = "mastermindx-market-intelligence/Mastermind"


class ProjectPlanningAppFactory:
    """Actual App principal + general Submit/autonomy + protected request budget.

    The saved source DTO is never an Executive grant. The policy authorizes one
    Job per original request; the incumbent command uniqueness and Attempt limit
    enforce that allowance. Reusing/changing a key never resets its budget.
    """
    def __init__(self, *, service, app_binding, policies, reader, plan_reader, events,
                 workspace_policy,load_workspace_bindings,policy_loader=None,clock=time.time):
        from control_plane.executive_service import ExecutiveControlService
        from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader
        from control_plane.agentos_project_plan import AgentOsProjectPlanReader
        from control_plane.workspace_source_operations import SourceOperationEvents
        if (type(service) is not ExecutiveControlService or app_binding is not service._ceo_ingress_app_binding
                or type(policies) is not AppPolicies or type(reader) is not AgentOsProjectCreationReader
                or type(plan_reader) is not AgentOsProjectPlanReader
                or type(events) is not SourceOperationEvents or events.store is not service._require_runtime().store
                or not callable(load_workspace_bindings) or not callable(clock)):
            raise ValueError("project planning actual installed owners unavailable")
        self.service,self.app_binding,self.policies=service,app_binding,policies
        self.reader,self.events=reader,events
        self.plan_reader=plan_reader
        self.workspace_policy=workspace_policy
        from integrations.mastermind_workspace_app.contract import workspace_authorizers
        self._authorize_workspace,_=workspace_authorizers(policy=workspace_policy,load_bindings=load_workspace_bindings)
        self.policy_loader=policy_loader
        self.clock=clock

    def _canonical_data(self):
        provider=self.app_binding.source_operation_provider_factory
        if not callable(provider):return None
        runtime=self.service._require_runtime();mounted=self.service._require_supervisor()
        invocation=current_foreground_operation()
        invocation._require_live()
        identity=(self,provider,runtime,mounted,self.app_binding)
        saved=getattr(invocation,'_planning_data_binding',None)
        if saved is None:
            binding=provider(runtime,mounted)
            invocation._planning_data_binding=(identity,binding)
        else:
            if saved[0]!=identity:raise ValueError('canonical planning owner changed')
            binding=saved[1]
        from control_plane.workspace_source_operation_binding import _current_source_operation
        def current():
            current_foreground_operation()._require_live()
            return self.app_binding is self.service._ceo_ingress_app_binding
        _current_source_operation(binding,runtime=runtime,supervisor=mounted,host_guard=current)
        data=binding.owner._canonical_data_source
        if data is not None and (self.reader._installed_context_owner is not data.collector
                or self.plan_reader._installed_context_owner is not data.collector):
            raise ValueError('canonical planning installed source owners differ')
        return data

    def _accept_new_canonical_view(self,data,view,*,workspace,work_ref):
        """Consume only the immediate installed producer's genuine issued proof.

        Mode.observe has just completed its full current postcheck. This is not
        a reusable grant or a new deadline: even this immediate handoff refuses
        an expired view, and the consumer's capture retains full pre/post checks.
        """
        from integrations.executive_mcp import installed
        from control_plane.project_canonical_data import CanonicalProjectDataView
        if type(view) is not CanonicalProjectDataView:raise ValueError('canonical planning issued view unavailable')
        collector=data.collector
        proof=view._verified_facts.pop(installed._CANONICAL_CODE_CAPTURE,None)
        if (type(proof) is not installed._CanonicalCodeCapture
                or proof.seal is not installed._CANONICAL_CODE_CAPTURE or proof.owner is not collector
                or proof.binding!=collector._canonical_code_capture_binding()
                or proof.view is not view or proof.view_identity!=view._owner._view_identity(view)
                or type(proof.observations) is not tuple or len(proof.observations)!=4
                or type(proof.macro_snapshot) is not installed._VerifiedRepositorySnapshot
                or proof.observations[0]!=self.service.config.proof_base_sha
                or proof.observations[1]!=view.code_commit
                or proof.macro_snapshot.root!=collector._macro_root
                or proof.macro_snapshot.head!=view.code_commit
                or collector._source_root!=self.service.config.proof_source_repository
                or view._code_root!=collector._macro_root
                or view._root!=Path(data.identity.binding.worktree)
                or view._operation.selected_work_ref!=work_ref
                or dataclasses.asdict(view._operation.principal)!=dataclasses.asdict(workspace)
                or view._owner.events is not data.events
                or view._owner.publisher._binding!=data.identity.binding):
            raise ValueError('canonical planning issued CODE proof differs')
        view._owner._validate_view(view)
        view._owner._permission_guard(view._operation)
        return view

    def _canonical_view(self,workspace,work_ref,*,verify_source=True):
        data=self._canonical_data()
        if data is None:return None
        invocation=current_foreground_operation()
        identity=(data,dataclasses.asdict(workspace),work_ref,data.context_binding())
        saved=getattr(invocation,'_planning_data_view',None)
        issued=False
        if saved is None:
            view=data.view(workspace,work_ref=work_ref)
            if view is None:raise ValueError('canonical planning DATA permission unavailable')
            view=self._accept_new_canonical_view(data,view,workspace=workspace,work_ref=work_ref)
            issued=True
            invocation._planning_data_view=(identity,view)
        else:
            if saved[0]!=identity:raise ValueError('canonical planning source owner changed')
            view=saved[1]
            view._owner._validate_view(view)
            from control_plane.project_canonical_data import _CAPTURE
            capture=_CAPTURE.get()
            if capture is not None:
                active=capture.view
                if active is not view:
                    # A genuine basis may retain its earlier issued view while
                    # an intervening strict guard reobserved the same C/N.
                    # Only that installed owner's nominal live capture rejoins;
                    # a DTO, foreign issuer/principal/work/source cannot do so.
                    mode=active._owner
                    seams=dict(authorize_read=data._can_read,read_stamp=data._read_stamp,
                        authorize_data=data._can_latest,data_stamp=data._latest_stamp)
                    if (mode.events is not data.events or mode.seams!=seams
                            or mode.publisher._binding!=data.identity.binding
                            or active._code_root!=data.collector._macro_root
                            or dataclasses.asdict(active._operation.principal)!=dataclasses.asdict(workspace)
                            or active._operation.selected_work_ref!=work_ref
                            or (active.code_commit,active.data_commit)!=(view.code_commit,view.data_commit)):
                        raise ValueError('canonical planning capture owner differs')
                    active._check_capture(capture)
                    view=active
                view.check()
            if capture is None and (verify_source or time.monotonic()>=view._operation.read_deadline):
                renewed=data.view(workspace,work_ref=work_ref)
                if renewed is not None:renewed=self._accept_new_canonical_view(data,renewed,workspace=workspace,work_ref=work_ref)
                if renewed is None or (renewed.code_commit,renewed.data_commit)!=(view.code_commit,view.data_commit):
                    raise ValueError('original planning source changed; no rebase')
                view=renewed;issued=True;invocation._planning_data_view=(identity,view)
        if issued:return view
        # Nested access/Event fences recheck current grants; the separate
        # Source.check observation performs the full current Git/seal check.
        # A later independent read may recapture only the SAME immutable C/N.
        # It never extends principal expiry, request identity or Job allowance.
        if not verify_source:
            view._owner._validate_view(view)
            view._owner._permission_guard(view._operation)
            return view
        from integrations.executive_mcp.installed import _installed_child_env
        collector=data.collector
        view._owner._permission_guard(view._operation)
        observed=collector._snapshot_pair(_installed_child_env(code_root=collector._code_root,
            macro_root=collector._macro_root),deadline=min(time.monotonic()+15,view._operation.read_deadline))
        if observed[0]!=self.service.config.proof_base_sha or observed[1]!=view.code_commit:
            raise ValueError('canonical planning CODE changed')
        view.check()
        return view

    @contextmanager
    def canonical_read_scope(self,*,principal,operation_key,work_ref):
        """Pure original-record reads only; never enclose a write/effect.

        The incumbent nominal capture brackets DATA/default/Event/config and
        permission observations. Nested checks keep current grants and CODE;
        an expired or changed capture refuses without returning partial DATA.
        """
        invocation=current_foreground_operation()
        if not callable(self.app_binding.source_operation_provider_factory):
            # Incumbent supplier without canonical DATA retains all of its
            # original strict checks; no capture or fallback authority is added.
            yield None
            return
        if invocation._project_planning_operation not in {'status','result','consume','prepare_proposal'}:
            raise ValueError('original planning read scope requires a read phase')
        self._current(principal,invocation,operation_key,work_ref)
        workspace=VerifiedPrincipal(**dataclasses.asdict(invocation._project_workspace_principal))
        view=self._canonical_view(workspace,work_ref)
        if view is None:raise ValueError('canonical planning read unavailable')
        with view.capture_scope():
            yield view
        # This executes before the caller receives captured DATA or may effect
        # anything else. A nested same-view scope keeps its outer full bracket.
        self._current(principal,invocation,operation_key,work_ref)

    def _canonical_plan(self,workspace,work_ref,*,current_only=False):
        view=self._canonical_view(workspace,work_ref,verify_source=not current_only)
        if view is None:
            from control_plane.agentos_project_plan import AgentOsProjectPlanReader
            return AgentOsProjectPlanReader.read(self.plan_reader,work_ref=work_ref)
        invocation=current_foreground_operation()
        saved=getattr(invocation,'_planning_plan_body',None)
        if saved is None:
            with view.capture_scope():body=view.read_plan(work_ref=work_ref)
            invocation._planning_plan_body=((view.code_commit,view.data_commit),copy.deepcopy(body))
        else:
            if saved[0]!=(view.code_commit,view.data_commit):raise ValueError('canonical planning source changed')
            body=copy.deepcopy(saved[1])
        return body

    def _canonical_creation(self,principal,invocation,operation_key,work_ref,source):
        invocation._require_live()
        workspace=VerifiedPrincipal(**dataclasses.asdict(invocation._project_workspace_principal))
        view=self._canonical_view(workspace,work_ref)
        if view is None:raise ValueError('canonical planning source unavailable')
        from control_plane.project_plan_canonical_basis import capture_current_plan_basis
        saved=getattr(invocation,'_planning_creation_source',None)
        if saved is None:
            with view.capture_scope():
                value=capture_current_plan_basis(view,work_ref=work_ref).qualify_creation_source(source)
            invocation._planning_creation_source=((view.code_commit,view.data_commit),copy.deepcopy(source),copy.deepcopy(value))
        else:
            if saved[0]!=(view.code_commit,view.data_commit) or saved[1]!=source:raise ValueError('original CREATE source changed')
            value=copy.deepcopy(saved[2])
        invocation._require_live()
        return value

    def _fixed_planning_code(self,invocation):
        """Commit-addressed policy/commission bytes, never live permission truth.

        The same foreground invocation cannot rebase its configured source.
        Current CODE/default/Event/config and grants retain their independent
        checks; repeated nested SQL guards need not rerun git-show for the same
        immutable objects. No value survives into another request/invocation.
        """
        invocation._require_live()
        key=(self,self.service.config.proof_source_repository,self.service.config.proof_base_sha)
        saved=getattr(invocation,'_planning_fixed_code',None)
        if saved is None:
            policy=PlanningPolicy.load(key[1],key[2])
            commission=read_protected_blob(key[1],key[2],COMMISSION_PATH)
            if not commission or len(commission)>16384:
                raise ValueError('project planning fixed commission unavailable')
            saved=(key,policy,commission)
            invocation._planning_fixed_code=saved
        elif saved[0]!=key:
            raise ValueError('project planning configured CODE changed; no rebase')
        return saved[1],saved[2]

    def _current(self,principal,invocation,operation_key,work_ref,*,current_only=False):
        service=self.service
        now=self.clock()
        if self.policy_loader is not None and self.policy_loader()!=self.policies:
            raise ValueError('project planning installed Executive policies changed')
        if (type(principal) is not VerifiedPrincipal or not principal_authorizes_submit(principal)
                or principal.policy_id != self.policies.submit.policy_id
                or principal.resource != self.policies.submit.resource
                or principal.issuer != self.policies.submit.issuer
                or principal.issuer_digest != hashlib.sha256(principal.issuer.encode()).hexdigest()
                or principal.subject_digest not in self.policies.submit.allowed_subject_digests
                or type(principal.issued_at) is not int or type(principal.expires_at) is not int
                or type(now) not in (int,float) or not principal.issued_at <= now < principal.expires_at):
            raise ValueError("project planning verified Executive principal refused")
        if (current_foreground_operation() is not invocation
                or invocation._project_planning_operation not in {'submit','status','result','consume','prepare_proposal'}
                or invocation._operation_key!=operation_key or invocation._project_planning_work_ref!=work_ref
                or dataclasses.asdict(invocation._principal)!=dataclasses.asdict(principal)
                or self.app_binding is not service._ceo_ingress_app_binding
                or not self.app_binding.armed or service._closing or not service._ceo_ingress_ready
                or service._service_state != "READY"):
            raise ValueError("project planning original App invocation unavailable")
        workspace=VerifiedPrincipal(**dataclasses.asdict(invocation._project_workspace_principal))
        if (workspace.policy_id!=self.workspace_policy.policy_id or workspace.resource!=self.workspace_policy.resource
                or workspace.issuer!=self.workspace_policy.issuer
                or not workspace.issued_at<=now<workspace.expires_at
                or (workspace.issuer_digest,workspace.subject_digest,workspace.client_ref)!=(principal.issuer_digest,principal.subject_digest,principal.client_ref)
                or self._authorize_workspace(workspace) is not True):
            raise ValueError('project planning distinct Workspace READ principal refused')
        stamp=self._authorize_workspace.binding_digest(workspace)
        native.require_digest(stamp)
        from integrations.mastermind_workspace_app.owner_context import workspace_principal_scope
        workspace_scope=workspace_principal_scope(workspace)
        try:
            service._require_ceo_submit_admission()
            service._require_current_autonomy()
        except Exception:
            raise ValueError("project planning existing Executive admission refused") from None
        invocation._require_live()
        policy,commission=self._fixed_planning_code(invocation)
        from control_plane.agentos_project_plan import AgentOsProjectPlanReader
        from common.workspace_project_plan_contract import validate_body
        plan=validate_body(self._canonical_plan(workspace,work_ref,current_only=current_only))
        if plan['availability']!='AVAILABLE' or plan['selection']!={'work_ref':work_ref}:
            raise ValueError('project planning current canonical goal unavailable')
        from control_plane.model_router import ModelRouter
        _quota,_registration,recipe=service._paid_subject_review_registration(ModelRouter.load(),direct_native=True)
        binding=native.normalize_binding({key:(service.config.proof_base_sha if key=="base_sha"
            else service.config.worker_id if key=="worker_id" else recipe[key]) for key in native._BINDING_KEYS})
        generation=native.require_digest(service._direct_native_generation_provider())
        scope=principal_scope_from_identity(issuer_digest=principal.issuer_digest,subject_digest=principal.subject_digest,
            client_ref=principal.client_ref,resource=principal.resource)
        identity=native.digest(dict(principal_scope=scope,operation_key=operation_key))
        limits=dict(principal_scope=scope,origin_root="principal-request:"+identity,
            return_ref="principal-return:"+scope,budget_ref="project-planning-policy:"+policy.source_sha256)
        source=dict(schema_version=EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,work_ref=work_ref,watch_mode=None,
            commission_ref=dict(repository=_ROOT_REPOSITORY,commit=service.config.proof_base_sha,
                path=COMMISSION_PATH,content_sha256=hashlib.sha256(commission).hexdigest()))
        try: service._require_ceo_submit_admission()
        except Exception:
            raise ValueError("project planning current Executive admission refused") from None
        invocation._require_live()
        return dict(limits=limits,binding=binding,source=source,host_generation=generation,
            policy_source_sha256=policy.source_sha256,
            principal_policy_sha256=native.digest(dataclasses.asdict(self.policies.submit)),
            project_plan=dict(source=plan['source'],plan=plan['plan']),
            workspace_scope=workspace_scope,workspace_permission_digest=stamp)

    def prepare(self, *, principal, operation_key, stage, work_ref, project_source,
                publication, private_request, grounding):
        """Source preparation only; the caller still explicitly submits once."""
        if type(private_request) is not bytes or not private_request or len(private_request)>256*1024:
            raise ValueError("project planning explicit private request is absent or too large")
        private_request.decode('utf-8',errors='strict')
        invocation=current_foreground_operation()
        if invocation._project_planning_operation=='submit':
            invocation.require_arguments(dict(operation_key=operation_key,stage=stage,work_ref=work_ref,
                project_source=project_source,publication=publication,private_request=private_request.decode('utf-8'),grounding=grounding))
        else:
            invocation._require_live()
        initial=self._current(principal,invocation,operation_key,work_ref)
        if publication['principal_scope']!=initial['workspace_scope']:
            raise ValueError('project planning publication belongs to another Workspace principal')
        if initial['project_plan']['source']!={**{key:value for key,value in project_source.items() if key!='request_sha256'},
                'repository':'mastermindx-market-intelligence/macro'}:
            raise ValueError('project planning goal and canonical source differ')
        generation=native.digest(initial)
        def current_generation():
            return native.digest(self._current(principal,invocation,operation_key,work_ref,current_only=True))
        access=native._issue_access(initial["limits"]["principal_scope"],work_ref,generation,current_generation)
        execution=self.service._direct_native_execution_access(access)
        executive=native._issue_admission(access,initial["source"],initial["binding"],execution_access=execution)
        runtime=self.service._require_runtime()
        from control_plane.executive_supervisor import ExecutiveSupervisor
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        mounted=self.service._require_supervisor()
        supervisor=mounted.primary if type(mounted) is MixedExecutionOwnerSupervisor else mounted
        if type(supervisor) is not ExecutiveSupervisor or supervisor.runtime is not runtime:
            raise ValueError("project planning original native Supervisor unavailable")
        input_owner=planning.ProjectPlanningInput(supervisor)
        if type(private_request) is not bytes or not private_request:
            raise ValueError("project planning explicit private request is absent")
        payload=native.canonical(dict(schema='mastermind.project_initial_planning_input.v1',
            request_text=private_request.decode('utf-8'),project_plan=initial['project_plan']))
        context=dict(schema=planning.SCHEMA,work_ref=work_ref,source=copy.deepcopy(project_source),
            publication=copy.deepcopy(publication),operation_key=operation_key,stage=stage,
            request_sha256=hashlib.sha256(payload).hexdigest(),executive_authority_sha256=generation,
            **initial["limits"])
        command=planning.operation_intent_id(context)
        from control_plane import ceo_intent
        prior=runtime.store.find_event_by_command_id(ceo_intent.command_id_for(command))
        if prior is None:
            context["input_artifact_sha256"]=input_owner.prepare(context,payload)
        else:
            original=runtime.jobs.direct_native_provenance(prior["job_id"])["project_planning"]
            if {key:value for key,value in original.items() if key!="input_artifact_sha256"} != context:
                raise ValueError("project planning original operation differs; no replacement")
            context["input_artifact_sha256"]=original["input_artifact_sha256"]
        def authority():
            if self._current(principal,invocation,operation_key,work_ref,current_only=True) != initial:
                raise ValueError("project planning current source/policy/authority changed")
            return copy.deepcopy(context)
        def publication_guard():
            authority()
            return True
        owner=planning._issue_source(reader=self.reader,executive=execution,context=context,
            authority_guard=authority,input_owner=input_owner,events=self.events,publication_guard=publication_guard,
            canonical_source_reader=(None if not callable(self.app_binding.source_operation_provider_factory) else
                lambda:self._canonical_creation(principal,invocation,operation_key,work_ref,project_source)),
            read_scope=(None if not callable(self.app_binding.source_operation_provider_factory) else
                lambda:self.canonical_read_scope(principal=principal,operation_key=operation_key,work_ref=work_ref)))
        return owner,executive

    def submit(self, *, principal, operation_key, stage, work_ref, project_source,
               publication, private_request, grounding):
        """Authenticated explicit producer -> canonical sink, zero dispatches."""
        source,executive=self.prepare(principal=principal,operation_key=operation_key,stage=stage,work_ref=work_ref,
            project_source=project_source,publication=publication,private_request=private_request,grounding=grounding)
        invocation=current_foreground_operation()
        if invocation._project_planning_operation!='submit':raise ValueError('project planning status cannot submit')
        return planning.submit_initial_request(self.service._require_runtime(),source=source,executive_admission=executive,
            request={key:source.material()[key] for key in ("operation_key","stage","request_sha256")},
            grounding=grounding,workspace_root=self.service.config.proof_workspace_root,
            fresh_admission_observer=invocation._bind_admitted_root)

    def qualified_original_source(self,*,principal,operation_key,work_ref):
        """Same-carrier read only. No private input rewrite or new root."""
        invocation=current_foreground_operation()
        if invocation._project_planning_operation=='submit':raise ValueError('original read requires its distinct operation')
        current=self._current(principal,invocation,operation_key,work_ref)
        from control_plane import ceo_intent
        runtime=self.service._require_runtime()
        intent=planning.operation_intent_id(dict(operation_key=operation_key,principal_scope=current['limits']['principal_scope']))
        receipt=ceo_intent.resolve_intent(runtime,intent)
        material=runtime.jobs.direct_native_provenance(receipt['job_id'])
        context=material['project_planning']
        if context['principal_scope']!=current['limits']['principal_scope'] or context['work_ref']!=work_ref:
            raise ValueError('project planning original owner differs')
        from control_plane.executive_supervisor import ExecutiveSupervisor
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        mounted=self.service._require_supervisor()
        supervisor=mounted.primary if type(mounted) is MixedExecutionOwnerSupervisor else mounted
        if type(supervisor) is not ExecutiveSupervisor:raise ValueError('project planning original Supervisor unavailable')
        payload=planning.ProjectPlanningInput(supervisor).read(context)
        value=json.loads(payload)
        if type(value) is not dict or set(value)!={'schema','request_text','project_plan'} or value['schema']!='mastermind.project_initial_planning_input.v1':
            raise ValueError('project planning original private envelope differs')
        source,executive=self.prepare(principal=principal,operation_key=operation_key,stage=context['stage'],work_ref=work_ref,
            project_source=context['source'],publication=context['publication'],private_request=value['request_text'].encode('utf-8'),
            grounding=receipt['grounding'])
        access=planning.requalify_original(runtime,job_id=receipt['job_id'],source=source,executive_admission=executive)
        return receipt,access,source,executive

    def qualified_original(self,**arguments):
        return self.qualified_original_source(**arguments)[:2]

    def original(self,**arguments):
        return self.qualified_original(**arguments)[0]


def build_ingress_owner(factory):
    """Installed upper composition; only the real private-peer handler enters."""
    from common.project_planning_private_contract import ProjectPlanningIngressOwner,RESULT_SCHEMA
    if type(factory) is not ProjectPlanningAppFactory:raise ValueError('project planning nominal factory required')
    async def handle(frame):
        operation=current_foreground_operation()
        # The actual private-peer source validated this neutral projection.
        # This conversion does not verify a wire token or create a capability.
        principal=VerifiedPrincipal(**dataclasses.asdict(operation._principal))
        args=frame['arguments']
        operation.require_arguments(args)
        if frame['operation']=='prepare_proposal':
            original,access,source,executive=factory.qualified_original_source(principal=principal,
                operation_key=args['operation_key'],work_ref=args['work_ref'])
            request=args['proposal_request']
            if request['selection']['job_id']!=original['job_id']:
                raise ValueError('proposal belongs to another original planning Job')
            runtime=factory.service._require_runtime()
            mounted=factory.service._require_supervisor()
            workspace=VerifiedPrincipal(**dataclasses.asdict(operation._project_workspace_principal))
            from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
            if source.material()['publication']['principal_scope']!=source_principal_scope(workspace):
                raise ValueError('proposal Workspace principal differs')
            provider=factory.app_binding.source_operation_provider_factory
            if not callable(provider):raise ValueError('proposal source owner unavailable')
            binding=provider(runtime,mounted)
            from control_plane.workspace_source_operation_binding import _current_source_operation,prepare_project_plan_proposal
            def host_current():
                operation._require_live()
                factory._current(principal,operation,args['operation_key'],args['work_ref'])
                return True
            current=_current_source_operation(binding,runtime=runtime,supervisor=mounted,host_guard=host_current)
            data=binding.owner._canonical_data_source
            if data is None:raise ValueError('canonical plan basis unavailable')
            from control_plane.project_plan_canonical_basis import capture_current_plan_basis
            from control_plane.project_plan_result_source import capture_completed_planning_result
            view=data.view(workspace,work_ref=args['work_ref'])
            if view is None:raise ValueError('canonical plan basis unavailable')
            with view.capture_scope():
                basis=capture_current_plan_basis(view,work_ref=args['work_ref'])
                bound=factory.service._namespace_custody.bound_runtime(runtime)
                result=capture_completed_planning_result(runtime,result_reader=bound,selection=request['selection'],
                    source=source,executive_admission=executive)
                if result.check()['result_digest']!=request['result_digest']:raise ValueError('proposal result differs')
                current();host_current()
            # Captures are read/compiler-only. The distinct original source
            # retention below uses fresh full checks outside that scope.
            receipt=prepare_project_plan_proposal(binding,request,runtime=runtime,supervisor=mounted,
                host_guard=host_current,principal=workspace,basis=basis,result=result)
            current();host_current()
        elif frame['operation']=='status':
            with factory.canonical_read_scope(principal=principal,**args):
                receipt=factory.original(principal=principal,**args)
        elif frame['operation'] in {'result','consume'}:
            with factory.canonical_read_scope(principal=principal,operation_key=args['operation_key'],work_ref=args['work_ref']):
                original,access=factory.qualified_original(principal=principal,operation_key=args['operation_key'],work_ref=args['work_ref'])
            runtime=factory.service._require_runtime()
            from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
            custody=factory.service._namespace_custody
            if type(custody) is not ServiceRuntimeNamespaceCustody:raise ValueError('original Runtime result custody unavailable')
            bound=custody.bound_runtime(runtime)
            selection=dict(work_ref=args['work_ref'],job_id=original['job_id'],attempt_id=args.get('attempt_id'))
            if frame['operation']=='consume':
                selection.update(result_digest=args['result_digest'],operation_key=args['consumption_operation_key'])
                acknowledged=runtime.consume_direct_native_result(selection,access=access)
            read_selection={key:selection[key] for key in ('work_ref','job_id','attempt_id')}
            with factory.canonical_read_scope(principal=principal,operation_key=args['operation_key'],work_ref=args['work_ref']):
                receipt=bound.read_direct_native_result_bounded(read_selection,access=access)
                bound.store.read_binding.validate_before_core_return()
            if frame['operation']=='consume' and (receipt['availability']!='AVAILABLE' or receipt['consumption']!=acknowledged):
                raise ValueError('original Runtime consumption return is uncertain')
        else:
            request={**args,'private_request':args['private_request'].encode('utf-8')}
            receipt=factory.submit(principal=principal,**request)
            if receipt['duplicate'] is False:
                operation.require_root(receipt['job_id'])
                source,executive=factory.prepare(principal=principal,**request)
                access=planning.requalify_original(factory.service._require_runtime(),job_id=receipt['job_id'],
                    source=source,executive_admission=executive)
                # This is the incumbent actual owner. Unknown/reserved effects
                # remain on its original Runtime/worker carrier, never replayed.
                active=await factory.service._dispatch_direct_native(receipt['job_id'],access=access)
                if active is not None:
                    await factory.service._await_foreground_dispatch(operation,receipt['job_id'],None,
                        _direct_active=active,_direct_access=access)
        return dict(schema=RESULT_SCHEMA,operation=frame['operation'],ok=True,data=receipt,error=None)
    return ProjectPlanningIngressOwner(handle)
