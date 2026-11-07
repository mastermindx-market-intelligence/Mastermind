"""Actual nominal App/HTTP lifetime/service/Runtime; inert provider guards only."""
import asyncio
import copy
import dataclasses
import hashlib
from pathlib import Path
import subprocess
import time
import os
import inspect
from types import SimpleNamespace

import pytest

from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.project_planning_policy import PlanningPolicy,launch_limits,COMMISSION_PATH
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_executive_app.project_planning_factory import ProjectPlanningAppFactory
from control_plane.foreground_operation import _project_planning_foreground_dispatch,ForegroundOperationClosed,ForegroundOperationRefusal
from common import project_planning_private_contract as private_wire
from tests.test_executive_service import _config
from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest, AUTH_POLICY_SCHEMA
from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE
from tests.test_project_planning_admission import fixture as core_fixture


def fixture(tmp_path,monkeypatch):
    kwargs,current,observed,executing=core_fixture(tmp_path,monkeypatch)
    config=_config(tmp_path,ceo_submit_armed=True,coo_autonomy_armed=True,
        coo_operator_harness_armed=True,coo_foreground_only=True)
    root=config.proof_source_repository
    for relative in ('config/authority_map.yml',COMMISSION_PATH):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((Path(__file__).resolve().parents[1]/relative).read_bytes())
    subprocess.run(['git','-C',str(root),'add','config/authority_map.yml',COMMISSION_PATH],check=True)
    subprocess.run(['git','-C',str(root),'commit','-qm','fixed planning policy and commission'],check=True)
    base=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    config=dataclasses.replace(config,proof_base_sha=base,proof_workspace_root=kwargs['workspace_root'])
    armed=[True]
    def guard():
        if not armed[0]:raise ValueError('existing general admission withdrawn')
    class Grounding:
        def observe(self):return dict(mastermind_sha=base,macro_sha='e'*40)
    app=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=Grounding())
    service=ExecutiveControlService(config,autonomy_guard=guard,ceo_submit_admission_guard=guard,
        direct_native_generation_provider=lambda:'e'*64,ceo_ingress_app_binding=app,
        ceo_ingress_socket_path=config.socket_path.with_name('ceo.sock'),ceo_ingress_peer_uid=os.geteuid()+1,
        ceo_ingress_grounding_provider=app.grounding_provider)
    service.runtime=kwargs['runtime'];service._ceo_ingress_ready=True
    service.supervisor=kwargs['source']._input_owner.supervisor
    binding=kwargs['executive_admission'].binding
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    registry=ExecutionCapabilityRegistry.load();profile=registry.resolve('sealed.worker.readonly.no-extensions.v1')
    binding={**binding,'execution_profile_id':profile.profile_id,'execution_profile_digest':profile.profile_digest,
        'capability_policy_version':registry.policy_version,'capability_policy_digest':registry.policy_digest}
    monkeypatch.setattr(service,'_paid_subject_review_registration',lambda router,**kw:('default',{},binding))
    def policy(label,scopes):
        issuer='https://issuer.example.invalid'
        return load_resource_policy(dict(schema=AUTH_POLICY_SCHEMA,policy_id=label,
            resource='https://executive.example.invalid/mcp',resource_metadata_url='https://executive.example.invalid/mcp/.well-known/oauth-protected-resource',
            issuer=issuer,authorization_servers=[issuer],jwks_uri=issuer+'/.well-known/jwks.json',
            required_scopes=scopes,allowed_subject_digests=[subject_digest(issuer=issuer,subject='inert-chairman')],
            allowed_algorithms=['RS256'],clock_skew_seconds=30,max_token_lifetime_seconds=900,
            jwks_cache_ttl_seconds=300,unknown_kid_refresh_cooldown_seconds=30,fetch_failure_backoff_seconds=5))
    policies=AppPolicies(read=policy('planning-test-read',[READ_SCOPE]),submit=policy('planning-test-submit',sorted([READ_SCOPE,SUBMIT_SCOPE])))
    now=int(time.time())
    principal=VerifiedPrincipal(policy_id=policies.submit.policy_id,issuer=policies.submit.issuer,
        issuer_digest=hashlib.sha256(policies.submit.issuer.encode()).hexdigest(),resource=policies.submit.resource,
        subject_digest=policies.submit.allowed_subject_digests[0],client_ref=hashlib.sha256((policies.submit.issuer+'\nclient\ninert-client').encode()).hexdigest(),
        scopes=policies.submit.required_scopes,issued_at=now-5,expires_at=now+600,jti_digest=None)
    from common.executive_workspace_contract import RESOURCE,SCOPE,PRINCIPAL_KEYS
    workspace_policy=policy('planning-workspace-read',[SCOPE])
    workspace_policy=dataclasses.replace(workspace_policy,resource=RESOURCE,resource_metadata_url=RESOURCE+'/.well-known/oauth-protected-resource')
    workspace=dataclasses.replace(principal,policy_id=workspace_policy.policy_id,resource=RESOURCE,scopes=(SCOPE,))
    from integrations.mastermind_workspace_app.contract import principal_frame,MEMBER_BINDINGS_SCHEMA
    from integrations.mastermind_workspace_app.owner_context import workspace_principal_scope
    bindings=[dict(schema=MEMBER_BINDINGS_SCHEMA,primary_profile='member-0',profiles={
        'member-0':dict(enabled=True,binding={**principal_frame(workspace),'permission_digest':'6'*64})})]
    from control_plane.agentos_project_plan import AgentOsProjectPlanReader
    from control_plane.workspace_project_plan import project_workstream_plan
    plan_reader=AgentOsProjectPlanReader(macro_root=tmp_path)
    plan=project_workstream_plan(dict(key=current[0]['work_ref'][3:],title='Canonical project',objective='Canonical private goal.',
        status='proposed',owner='ceo-sol',next_action='Clarify',waves=[]),work_ref=current[0]['work_ref'],
        source={**{k:v for k,v in current[0]['source'].items() if k!='request_sha256'},'repository':'mastermindx-market-intelligence/macro'})
    monkeypatch.setattr(AgentOsProjectPlanReader,'read',lambda self,**kw:copy.deepcopy(plan))
    events=kwargs['source']._events
    lookup=dict(schema='mastermind.workspace_source_operation_lookup.v1',action='publish_project_proposal',
        request_id=current[0]['publication']['request_id'],work_ref=current[0]['work_ref'])
    scope=workspace_principal_scope(workspace)
    ref=dict(schema='mastermind.terminal_original_input_reference.v1',input_ref='terminal-input:'+'4'*64,artifact_sha256='5'*64,payload_sha256='6'*64)
    events.prepare(lookup,scope,request_sha256='8'*64,recipe_fingerprint_sha256='9'*64,original_input=ref,
        permission_binding_digest='0'*64,guard=lambda:True,publication_binding=dict(expected_commit='e'*40,branch=None,
        postimages=[dict(path=current[0]['source']['path'],content_sha256=current[0]['source']['content_sha256'],expected_preimage_sha256=None)]))
    events.claim_phase(lookup,scope,permission_binding_digest='0'*64,preview_witness=dict(original_input=ref,recipe_fingerprint_sha256='9'*64),guard=lambda:True)
    receipt=events.retain_observation(lookup,scope,phase='PUBLICATION',sources=[{k:v for k,v in current[0]['source'].items() if k!='request_sha256'}],
        proposal=None,qualify_observation=lambda _:True,guard=lambda:True)
    current[0]['publication']=dict(request_id=lookup['request_id'],principal_scope=scope,event_id=receipt['event_id'],receipt_sha256=receipt['receipt_sha256'])
    factory=ProjectPlanningAppFactory(service=service,app_binding=app,policies=policies,
        reader=kwargs['source']._reader,plan_reader=plan_reader,events=events,
        workspace_policy=workspace_policy,load_workspace_bindings=lambda:copy.deepcopy(bindings[0]))
    factory._test_workspace_principal=workspace
    factory._test_bindings=bindings
    args=dict(principal=principal,operation_key='explicit-app-planning',stage='clarify',
        work_ref=current[0]['work_ref'],project_source=current[0]['source'],publication=current[0]['publication'],
        private_request=b'Private first request.',grounding=dict(mastermind_sha=base,macro_sha='e'*40))
    return factory,args,armed,observed


async def invocation(factory,args,call,operation='submit'):
    principal=dataclasses.asdict(args['principal']);principal['scopes']=list(principal['scopes'])
    workspace=dataclasses.asdict(factory._test_workspace_principal);workspace['scopes']=list(workspace['scopes'])
    arguments={key:value for key,value in args.items() if key!='principal'} if operation=='submit' else {key:args[key] for key in ('operation_key','work_ref')}
    if operation=='submit':arguments['private_request']=arguments['private_request'].decode()
    frame=dict(schema=private_wire.SCHEMA,operation=operation,principal=principal,workspace_principal=workspace,arguments=arguments)
    async with _project_planning_foreground_dispatch(factory.service._require_runtime(),frame,lambda:None):
        value=call()
        return await value if inspect.isawaitable(value) else value


def test_actual_authenticated_factory_admits_original_once_without_web_branch_lookup(tmp_path,monkeypatch):
    factory,args,_,_=fixture(tmp_path,monkeypatch)
    def run():
        first=factory.submit(**args);again=factory.submit(**args)
        assert first['job_id']==again['job_id'] and not first['duplicate'] and again['duplicate']
        runtime=factory.service._require_runtime()
        material=runtime.jobs.direct_native_provenance(first['job_id'])
        context=material['project_planning']
        assert context['origin_root'].startswith('principal-request:')
        assert context['origin_root']!=first['job_id']
        assert context['return_ref']=='principal-return:'+context['principal_scope']
        assert context['budget_ref'].startswith('project-planning-policy:')
        assert material['source']['commission_ref']['path']==COMMISSION_PATH
        assert runtime.attempts.list_attempts()==[] and first['dispatched'] is False
        return first
    first=asyncio.run(invocation(factory,args,run))
    # A new genuine invocation with the same verified principal may reconcile,
    # without inventing another original operation or retrying a provider.
    again=asyncio.run(invocation(factory,args,lambda:factory.submit(**args)))
    assert again['job_id']==first['job_id'] and again['duplicate']


@pytest.mark.parametrize('change',['unarmed','expired','read-only','wrong-policy','wrong-subject','wrong-resource','wrong-app','source'])
def test_factory_refuses_actual_principal_host_and_source_failures(tmp_path,monkeypatch,change):
    factory,args,armed,observed=fixture(tmp_path,monkeypatch)
    if change=='unarmed':armed[0]=False
    if change=='expired':args['principal']=dataclasses.replace(args['principal'],expires_at=1)
    if change=='read-only':args['principal']=dataclasses.replace(args['principal'],scopes=(factory.policies.read.required_scopes[0],))
    if change=='wrong-policy':args['principal']=dataclasses.replace(args['principal'],policy_id='another-policy')
    if change=='wrong-subject':args['principal']=dataclasses.replace(args['principal'],subject_digest='f'*64)
    if change=='wrong-resource':args['principal']=dataclasses.replace(args['principal'],resource='https://invalid.example/mcp')
    if change=='wrong-app':factory.service._ceo_ingress_app_binding=None
    if change=='source':observed[0]['content_sha256']='f'*64
    with pytest.raises((ValueError,ForegroundOperationRefusal)):
        asyncio.run(invocation(factory,args,lambda:factory.submit(**args)))
    assert factory.service._require_runtime().jobs.list_jobs()==[]


def test_no_actual_http_invocation_can_be_forged_by_request_data(tmp_path,monkeypatch):
    factory,args,_,_=fixture(tmp_path,monkeypatch)
    with pytest.raises(ForegroundOperationClosed):factory.submit(**args)
    assert factory.service._require_runtime().jobs.list_jobs()==[]


def test_fixed_policy_and_physical_launch_bounds_use_original_runtime_rows(tmp_path,monkeypatch):
    factory,args,_,_=fixture(tmp_path,monkeypatch)
    def run():
        receipt=factory.submit(**args)
        runtime=factory.service._require_runtime();job=runtime.jobs.get_job(receipt['job_id'])
        # Prepare the incumbent genuine clone; this is a temporary local Git
        # allocation, never a broker/provider/session operation.
        prep=dict(args)
        source,executive=factory.prepare(**prep)
        from control_plane.project_planning_admission import requalify_original
        access=requalify_original(runtime,job_id=job.job_id,source=source,executive_admission=executive)
        import os
        runtime.jobs.prepare_direct_native_workspace(job.job_id,
            source_repository=factory.service.config.proof_source_repository,shared_gid=os.getegid(),access=access)
        policy=PlanningPolicy.load(job.worktree,job.constraints['base_sha'])
        assert policy.max_jobs_per_original_request==1 and policy.max_attempts_per_job==1
        assert launch_limits(runtime,job)==dict(timeout_seconds=300,max_artifacts=0,cancel_grace_seconds=10)
        # Losing the immutable policy object refuses rather than selecting the
        # incumbent 1800-second launch default.
        monkeypatch.setattr('control_plane.project_planning_policy.read_protected_blob',lambda *a:b'')
        with pytest.raises(ValueError):launch_limits(runtime,job)
    asyncio.run(invocation(factory,args,run))


def test_actual_planning_prompt_finite_launch_terminal_and_retained_result(tmp_path,monkeypatch):
    from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
    from control_plane.project_planning_admission import requalify_original
    from control_plane.executive_runtime import JobStatus,AttemptStatus
    factory,args,_,_=fixture(tmp_path,monkeypatch)
    runtime=factory.service.runtime;old=factory.service.supervisor
    supervisor=make_direct_supervisor(runtime,workspace_root=factory.service.config.proof_workspace_root,
        runs_root=old.runs_root,provider_home=tmp_path/'provider-home')
    factory.service.supervisor=supervisor
    async def run():
        receipt=factory.submit(**args);job=runtime.jobs.get_job(receipt['job_id'])
        source,executive=factory.prepare(**args)
        access=requalify_original(runtime,job_id=job.job_id,source=source,executive_admission=executive)
        binding=executive.binding
        metadata={key:binding[key] for key in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')}
        metadata['adapter_id']='codex-cli'
        runtime.workers.register_worker(binding['worker_id'],provider='codex',account_label='inert-planning',worker_type='codex-cli',
            capabilities=['read','research'],quota_classes={'default':dict(provider='codex',model=binding['model'],effort=binding['effort'],cost_class=binding['cost_class'],capabilities=['read','research'],metadata=metadata)})
        runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=factory.service.config.proof_source_repository,shared_gid=os.getegid(),access=access)
        active=await supervisor.start_direct_native_job(job.job_id,access=access)
        spec=supervisor.adapter.spec
        assert spec.timeout_seconds==300 and spec.max_artifacts==0 and spec.cancel_grace_seconds==10
        assert 'Private first request.' in spec.prompt and 'Canonical private goal.' in spec.prompt
        assert 'project_initial_planning_stage' in spec.prompt and 'clarify' in spec.prompt
        replay=await supervisor.start_direct_native_job(job.job_id,access=access)
        assert supervisor.adapter.start_count==1
        assert replay.attempt.attempt_id==active.lease.attempt.attempt_id
        terminal=await supervisor.finish_job(active)
        assert terminal.job.status is JobStatus.COMPLETED and terminal.attempt.status is AttemptStatus.COMPLETED
        assert len(runtime.attempts.list_attempts())==1
        return job.job_id
    job_id=asyncio.run(invocation(factory,args,run))
    # Actual retained Runtime read uses its existing descriptor-bound owner.
    from tests.test_fabric_result_projection import _bound_reader,_release
    async def result():
        original,access=factory.qualified_original(principal=args['principal'],operation_key=args['operation_key'],work_ref=args['work_ref'])
        keeper,_,binding,reader=_bound_reader(runtime)
        try:
            view=reader.read_direct_native_result_bounded(dict(work_ref=args['work_ref'],job_id=job_id,attempt_id=None),access=access)
            assert original['job_id']==job_id and view['availability']=='AVAILABLE'
            assert view['result']['summary']=='Retained direct research findings'
        finally:_release(keeper,binding)
    asyncio.run(invocation(factory,args,result,operation='result'))


@pytest.mark.parametrize('withdrawal',['grant','disconnect','runtime-replaced'])
def test_postlaunch_entry_failure_cancels_only_original_claim_and_retains_finisher(tmp_path,monkeypatch,withdrawal):
    from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
    from control_plane.project_planning_admission import requalify_original
    from control_plane.foreground_operation import current_foreground_operation
    from control_plane.executive_runtime import JobStatus,AttemptStatus
    factory,args,armed,_=fixture(tmp_path,monkeypatch)
    service=factory.service;runtime=service.runtime
    service.supervisor=make_direct_supervisor(runtime,workspace_root=service.config.proof_workspace_root,
        runs_root=service.supervisor.runs_root,provider_home=tmp_path/'provider-home')
    async def run():
        receipt=factory.submit(**args);job_id=receipt['job_id']
        source,executive=factory.prepare(**args)
        access=requalify_original(runtime,job_id=job_id,source=source,executive_admission=executive)
        binding=executive.binding
        metadata={key:binding[key] for key in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')}
        metadata['adapter_id']='codex-cli'
        runtime.workers.register_worker(binding['worker_id'],provider='codex',account_label='inert-planning',worker_type='codex-cli',
            capabilities=['read','research'],quota_classes={'default':dict(provider='codex',model=binding['model'],effort=binding['effort'],cost_class=binding['cost_class'],capabilities=['read','research'],metadata=metadata)})
        monkeypatch.setattr(service,'_register_worker',lambda **kw:None)
        release=asyncio.Event()
        async def physical_finish(job_id,active,**kw):
            # This discriminating seam delays only physical collection; the
            # real dispatch registry, Runtime rows and cancellation are intact.
            await release.wait()
        monkeypatch.setattr(service,'_finish_dispatched',physical_finish)
        operation=current_foreground_operation()
        original_start=service.supervisor.adapter.start
        async def withdraw_during_start(*args,**kwargs):
            process=await original_start(*args,**kwargs)
            # Physical START has occurred, but its original dispatch has not
            # returned ActiveRun or attached a foreground wait/cancel fence.
            if withdrawal=='grant':armed[0]=False
            elif withdrawal=='disconnect':operation._mark_source_closed()
            else:service.runtime=None
            return process
        monkeypatch.setattr(service.supervisor.adapter,'start',withdraw_during_start)
        active=await service._dispatch_direct_native(job_id,access=access)
        original=active.lease.attempt;finisher=service._dispatch_tasks[job_id]
        assert service.supervisor.adapter.start_count==1 and not finisher.done()
        try:
            with pytest.raises(Exception):
                await service._await_foreground_dispatch(operation,job_id,None,_direct_active=active,_direct_access=access)
            assert runtime.jobs.get_job(job_id).status is JobStatus.CANCEL_REQUESTED
            assert runtime.attempts.get_attempt(original.attempt_id).status is AttemptStatus.CANCEL_REQUESTED
            assert runtime.jobs.get_job(job_id).current_attempt_id==original.attempt_id
            assert service._dispatch_tasks[job_id] is finisher and not finisher.done()
            assert service.supervisor.adapter.start_count==1 and len(runtime.attempts.list_attempts())==1
        finally:
            service.runtime=runtime
            release.set();await finisher
    asyncio.run(invocation(factory,args,run))


@pytest.mark.parametrize('text',[
    b'',b'project_initial_planning_policy:\n  schema_version: 1\n',
    b'project_initial_planning_policy:\n  schema_version: 1\n  max_jobs_per_original_request: 0\n',
])
def test_missing_incomplete_or_exhausted_policy_never_authorizes_requested_one_attempt(tmp_path,monkeypatch,text):
    factory,args,_,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr('control_plane.project_planning_policy.read_protected_blob',lambda *a:text)
    with pytest.raises(ValueError):asyncio.run(invocation(factory,args,lambda:factory.submit(**args)))
    assert factory.service._require_runtime().jobs.list_jobs()==[]
