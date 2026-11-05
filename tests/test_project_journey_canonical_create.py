"""Actual CREATE→default Event→current DATA→same original S19 admission.

Disposable Git and real Runtime/private source owners. Credential/PR, sealed
host source observation, native execution availability and principal enrollment
are explicit inert fixture seams. No live grant, worker or publication occurs.
"""
import asyncio
import copy
import dataclasses
import base64
import hashlib
import json
from pathlib import Path
import zlib
import sys

import pytest

from tests.test_project_creation_source_owner import owner, env, isolated_git_env, selection
from tests.test_project_planning_factory import fixture as planning_fixture, invocation
from tests.test_installed_source_git_identity import identity
from tests.test_workspace_project_git_publisher import git, rev_parse
from integrations.mastermind_workspace_app.project_creation_operation import ProjectCreationRecipeAdapter
from integrations.mastermind_workspace_app.project_creation_service import ProjectCreationSourceOwner
from integrations.mastermind_workspace_app.source_operation_context import WorkspaceSourceOperationContextFactory
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from integrations.mastermind_workspace_app.contract import principal_frame
from integrations.mastermind_workspace_app.project_authoring_grant import SCHEMA_V5
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.project_planning_compiler_source import capture_project_planning_compilers
from control_plane.workspace_project_git_publisher import PublisherBinding
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
from integrations.mastermind_workspace_app.source_operations import WorkspaceSourceOperationService
from control_plane.project_plan_canonical_basis import capture_current_plan_basis


@pytest.fixture
def joined(owner,identity,tmp_path,monkeypatch):
    o=owner
    # Complete real fixed compiler closure, all loaded from immutable fixture Git.
    for filename in ('agentos-project-plan-owner-contract.json','agentos-plan-proposal-7c54.json'):
        fixture=json.loads((Path(__file__).parent/'fixtures'/filename).read_bytes())
        for item in fixture['files']:
            if item['path']=='scripts/agentos.py':continue
            raw=zlib.decompress(base64.b64decode(item['zlib_base64'],validate=True))
            assert hashlib.sha256(raw).hexdigest()==item['sha256']
            target=o['env'].clone/item['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    git(o['env'].clone,'add','.');git(o['env'].clone,'commit','-m','Full actual fixed compiler closure')
    git(o['env'].clone,'push','origin','main');code=rev_parse(o['env'].clone,'HEAD')
    factory,args,armed,_=planning_fixture(tmp_path/'planning',monkeypatch)
    workspace=factory._test_workspace_principal
    # Existing grant schema, same authenticated Workspace principal as S19.
    document=copy.deepcopy(o['bindings']);document['schema']=SCHEMA_V5
    for slot in document['profiles'].values():
        slot['enabled']=False;slot['binding']=None
        slot['project_plan_proposal_publish']=None;slot['project_canonical_data_read']=None
    slot=document['profiles'][document['primary_profile']]
    slot['enabled']=True;slot['binding']=dict(principal_frame(workspace),permission_digest='a'*64)
    slot['project_canonical_data_read']='b'*64
    runtime=factory.service.runtime;events=factory.events
    source_root=factory.service.config.proof_source_repository
    profile_path=source_root/'config/workspace_project_authoring_profiles.json'
    profile_path.write_bytes((Path(__file__).parents[1]/'config/workspace_project_authoring_profiles.json').read_bytes())
    git(source_root,'add',str(profile_path.relative_to(source_root)));git(source_root,'commit','-m','Actual authored profile catalogue')
    factory.service.config=dataclasses.replace(factory.service.config,proof_base_sha=rev_parse(source_root,'HEAD'))
    # Actual installed factory, separate immutable code clone and writer.
    code_root=tmp_path/'configured-code';git(tmp_path,'clone',str(o['env'].origin),str(code_root));git(code_root,'checkout','--detach',code)
    collector=InstalledBootPacketCollector(source_root=source_root,macro_root=code_root,
        code_root=Path(__file__).parents[1],python_executable=Path(sys.executable),expected_source_sha=factory.service.config.proof_base_sha)
    from integrations.executive_mcp import installed as installed_module
    def actual_macro_snapshot(env,*,deadline=None,snapshot_capture=None):
        observed=installed_module._clean_git_snapshot(code_root,runner=collector._runner,env=env,
            label='Macro source',content_scope='macro_brief',include_seal=True,deadline=deadline,
            snapshot_capture=snapshot_capture,_allow_synthetic_fixture=True)
        return factory.service.config.proof_base_sha,observed[0],'synthetic-test-Root-seal',observed[1]
    monkeypatch.setattr(collector,'_snapshot_pair',actual_macro_snapshot)
    git_owner=identity[0];git_owner.binding=PublisherBinding(worktree=str(o['env'].clone),expected_origin=str(o['env'].origin),default_branch='main',publisher_identity='synthetic-fixed-service-identity')
    monkeypatch.setattr(git_owner,'qualify',lambda binding:binding==git_owner.binding)
    monkeypatch.setattr(git_owner,'find',o['pr'].find);monkeypatch.setattr(git_owner,'create',o['pr'].create)
    from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
    installed=InstalledWorkspaceSourceOperations(collector=collector,policy=factory.workspace_policy,
        load_bindings=lambda:document,git_identity=git_owner,runtime_guard=lambda rt:rt is runtime)
    binding=installed(runtime,factory.service.supervisor)
    create=binding.owner._create;data=binding.owner._canonical_data_source
    def source_call(operation,value):
        from common.workspace_source_operation_wire import FRAME_SCHEMA
        return binding.owner.handle(dict(schema=FRAME_SCHEMA,operation=operation,principal=principal_frame(workspace),
            verified_expires_at=workspace.expires_at,request=value),peer_guard=lambda:True)
    options=source_call('options',{'action':'publish_project_proposal'})
    assert options['expected_macro_sha']==code and options['grounding']['mastermind_sha']==factory.service.config.proof_base_sha
    request=copy.deepcopy(o['request']);request['expected_macro_sha']=code;request['request_id']='mmos-project-create-'+'b'*40
    preview=source_call('prepare',{'action':'publish_project_proposal','request':request})
    lookup=selection(preview)
    pending=source_call('submit',dict(preview['selection'],preview_witness=preview['preview_witness']))
    assert pending['receipt']['kind']=='PROPOSAL_OBSERVED'
    integrator=tmp_path/'landing';git(tmp_path,'clone',str(o['env'].origin),str(integrator))
    git(integrator,'fetch','origin',pending['receipt']['proposal']['head_branch'])
    git(integrator,'merge','--no-ff','--no-edit','FETCH_HEAD');git(integrator,'push','origin','main')
    status=create.reconcile(lookup,workspace)
    assert status['receipt']['kind']=='SOURCE_OBSERVED'
    current=rev_parse(integrator,'HEAD');assert current!=code
    factory.reader=collector.project_creation_source_reader(macro_root=code_root)
    factory.plan_reader=collector.project_plan_reader(macro_root=code_root)
    # Physical isolated-child edge only. The actual installed scope and actual
    # immutable parser remain; existing child-isolation proof is not rerun here.
    from integrations.executive_mcp import installed as installed_module
    def physical_plan(**selected):
        selected_owner,selected_view,selected_work=installed_module._CANONICAL_PROJECT_DATA.get()
        assert selected_owner is collector and selected_work==selected['work_ref']
        return selected_view.read_plan(**selected)
    monkeypatch.setattr(collector,'read_project_plan',physical_plan)
    factory.app_binding=dataclasses.replace(factory.app_binding,source_operation_provider_factory=installed)
    factory.service._ceo_ingress_app_binding=factory.app_binding
    binding=installed(runtime,factory.service.supervisor)
    factory._test_bindings[0]=document
    factory._authorize_workspace,unused=__import__('integrations.mastermind_workspace_app.contract',fromlist=['workspace_authorizers']).workspace_authorizers(
        policy=factory.workspace_policy,load_bindings=lambda:__import__('integrations.mastermind_workspace_app.project_authoring_grant',fromlist=['legacy_workspace_document']).legacy_workspace_document(document,factory.workspace_policy))
    source=status['receipt']['sources'][0]
    args.update(work_ref=lookup['work_ref'],project_source={**source,'request_sha256':status['recipe_fingerprint_sha256']},
        publication=dict(request_id=lookup['request_id'],principal_scope=source_principal_scope(workspace),
            event_id=status['receipt']['event_id'],receipt_sha256=status['receipt']['receipt_sha256']),
        grounding=dict(mastermind_sha=factory.service.config.proof_base_sha,macro_sha=current))
    return locals()


def test_actual_create_default_event_qualifies_initial_plan_and_original_reopen(joined):
    j=joined;factory,args=j['factory'],j['args']
    assert len(j['runtime'].jobs.list_jobs())==0
    view=j['data'].view(j['workspace'],work_ref=args['work_ref'])
    with view.capture_scope():
        source=capture_current_plan_basis(view,work_ref=args['work_ref']).qualify_creation_source(args['project_source'])
    assert source==args['project_source'] and view.code_commit==j['code'] and view.data_commit==j['current']
    from tests.test_workspace_read_service import cache_fixture
    from control_plane.workspace_read_service import WorkspaceReadService
    from common.workspace_project_plan_contract import FRAME_SCHEMA
    from integrations.mastermind_workspace_app.contract import workspace_authorizers
    from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
    owners,clock,cache=cache_fixture(j['tmp_path']/'read-cache')
    doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':j['code']}
    from scripts import chairman_control_room as ccr
    with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
    _,read_frame=workspace_authorizers(policy=factory.workspace_policy,load_bindings=lambda:legacy_workspace_document(j['document'],factory.workspace_policy))
    read=WorkspaceReadService(cache=cache,runtime=j['runtime'],authorize=read_frame,armed={},runtime_identity={},
        canonical_project_data=j['data'].installed_binding(),project_plan_reader=factory.plan_reader)
    request=dict(schema=FRAME_SCHEMA,operation='project_plan',selection={'work_ref':args['work_ref']},principal=principal_frame(j['workspace']))
    plan=asyncio.run(read.handle_frame(request))
    assert plan['ok'] and plan['result']['availability']=='AVAILABLE',plan
    assert plan['result']['source']['commit']==j['current']
    assert not any(row['work_ref']==args['work_ref'] for row in doc['work'])
    first=asyncio.run(invocation(factory,args,lambda:factory.submit(**args)))
    again=asyncio.run(invocation(factory,args,lambda:factory.submit(**args)))
    assert first['job_id']==again['job_id'] and again['duplicate']
    assert len(j['runtime'].jobs.list_jobs())==1 and j['runtime'].attempts.list_attempts()==[]
    assert j['create'].read_status(j['lookup'],j['workspace'])==j['status']
    # Same original Job now traverses the actual native Supervisor/Runtime
    # terminal and explicit original-parent result/consume owners. Only the
    # physical native process observations use the existing inert adapter.
    from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
    from control_plane.project_planning_admission import requalify_original
    from control_plane.executive_runtime import JobStatus
    from tests.test_fabric_result_projection import _bound_reader,_release
    import os
    old=factory.service.supervisor;runtime=j['runtime']
    supervisor=make_direct_supervisor(runtime,workspace_root=factory.service.config.proof_workspace_root,
        runs_root=old.runs_root,provider_home=j['tmp_path']/'native-provider-fixture')
    factory.service.supervisor=supervisor
    async def complete():
        source,executive=factory.prepare(**args)
        job=runtime.jobs.get_job(first['job_id'])
        access=requalify_original(runtime,job_id=job.job_id,source=source,executive_admission=executive)
        bound=executive.binding
        metadata={key:bound[key] for key in ('routing_policy_version','execution_profile_id','execution_profile_digest','capability_policy_version','capability_policy_digest')}
        metadata['adapter_id']='codex-cli'
        runtime.workers.register_worker(bound['worker_id'],provider='codex',account_label='inert-planning',
            worker_type='codex-cli',capabilities=['read','research'],quota_classes={'default':dict(provider='codex',
                model=bound['model'],effort=bound['effort'],cost_class=bound['cost_class'],capabilities=['read','research'],metadata=metadata)})
        runtime.jobs.prepare_direct_native_workspace(job.job_id,source_repository=factory.service.config.proof_source_repository,
            shared_gid=os.getegid(),access=access)
        active=await supervisor.start_direct_native_job(job.job_id,access=access)
        terminal=await supervisor.finish_job(active)
        assert terminal.job.status is JobStatus.COMPLETED
        return dict(work_ref=args['work_ref'],job_id=job.job_id,attempt_id=terminal.attempt.attempt_id)
    selected=asyncio.run(invocation(factory,args,complete))
    def inspect_then_explicit_consume():
        source,executive=factory.prepare(**args)
        access=requalify_original(runtime,job_id=first['job_id'],source=source,executive_admission=executive)
        keeper,_,binding,reader=_bound_reader(runtime)
        try:
            before=len(runtime.store.list_events())
            result=reader.read_direct_native_result_bounded(selected,access=access)
            assert result['availability']=='AVAILABLE' and result['consumption']=={'state':'UNCONSUMED','receipt_digest':None}
            assert len(runtime.store.list_events())==before
            digest=result['result']['result_digest']
            ack=runtime.consume_direct_native_result(dict(selected,result_digest=digest,operation_key='explicit-parent-result-consume'),access=access)
            assert ack['state']=='CONSUMED'
            after=reader.read_direct_native_result_bounded(selected,access=access)
            assert after['result']==result['result'] and after['consumption']==ack
            count=len(runtime.store.list_events())
            assert runtime.consume_direct_native_result(dict(selected,result_digest=digest,operation_key='explicit-parent-result-consume'),access=access)==ack
            assert len(runtime.store.list_events())==count
        finally:_release(keeper,binding)
    asyncio.run(invocation(factory,args,inspect_then_explicit_consume,operation='result'))
    assert len(runtime.jobs.list_jobs())==1 and len(runtime.attempts.list_attempts())==1
    assert j['create'].read_status(j['lookup'],j['workspace'])==j['status']


def test_actual_installed_options_create_and_readonly_original_return(joined):
    j=joined
    assert j['options']['grounding']==dict(mastermind_sha=j['factory'].service.config.proof_base_sha,macro_sha=j['code'])
    before=len(j['runtime'].store.list_events())
    assert j['source_call']('read',j['lookup'])==j['status']
    assert j['create'].read_status(j['lookup'],j['workspace'])==j['status']
    assert len(j['runtime'].store.list_events())==before and j['runtime'].jobs.list_jobs()==[]


def test_current_read_grant_original_event_and_default_drift_refuse_without_job(joined):
    j=joined;factory,args=j['factory'],j['args']
    slot=j['document']['profiles'][j['document']['primary_profile']]
    # Revoke after the genuine pure capture. Nested access checks retain the
    # actual current grant, not just its previously hashed principal label.
    def revoke_after_capture():
        from control_plane.foreground_operation import current_foreground_operation
        invocation_=current_foreground_operation()
        factory._current(args['principal'],invocation_,args['operation_key'],args['work_ref'])
        before=slot['project_canonical_data_read'];slot['project_canonical_data_read']=None
        try:
            with pytest.raises(ValueError):factory._current(args['principal'],invocation_,args['operation_key'],args['work_ref'],current_only=True)
        finally:slot['project_canonical_data_read']=before
    asyncio.run(invocation(factory,args,revoke_after_capture))
    bad=copy.deepcopy(args);bad['publication']['receipt_sha256']='f'*64
    with pytest.raises(ValueError):asyncio.run(invocation(factory,bad,lambda:factory.submit(**bad)))
    assert j['runtime'].jobs.list_jobs()==[]
    # A new default commit is an actual external fixture actor. No refreshed
    # DATA view may silently rebase this original source/goal or publish again.
    def drift_after_capture():
        from control_plane.foreground_operation import current_foreground_operation
        operation=current_foreground_operation()
        factory._current(args['principal'],operation,args['operation_key'],args['work_ref'])
        root=j['integrator'];path=root/args['project_source']['path']
        path.write_bytes(path.read_bytes()+b'\nUnqualified external default drift.\n')
        git(root,'add',str(path.relative_to(root)));git(root,'commit','-m','Unqualified default source drift')
        git(root,'push','origin','main')
        with pytest.raises(ValueError):factory.submit(**args)
    asyncio.run(invocation(factory,args,drift_after_capture))
    assert j['runtime'].jobs.list_jobs()==[]
    assert j['create'].read_status(j['lookup'],j['workspace'])==j['status']
    assert j['o']['pr'].create_calls==1
