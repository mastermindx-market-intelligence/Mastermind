"""Opt-in SAME-run public operands from actual installed S24 + signed S19.

Only synthetic principal/JWKS/enrollment, Root seal, physical native observations,
Git credential qualification and PR/default-merge actor are inherited seams.
Workspace action ingress uses its actual fixed private wire with an already
verified fixture principal; Executive operations use real JWT/HTTP/Unix ingress.
No response DTO is translated into another schema or product authority.
"""
import asyncio
import copy
import dataclasses
import hashlib
import json
import os
import time
import traceback
import tempfile
import fcntl
import httpx
from tests.test_project_planning_transport import OsExecutiveTransportApp,DirectNativeResultClient,CeoIngressClient
from pathlib import Path
import pytest
from tests.project_plan_proposal_consumer_supplier import completed,joined,owner,env,isolated_git_env,identity
from tests.test_mastermind_executive_app_asgi import rsa_key
from tests.test_workspace_project_git_publisher import git,rev_parse
from integrations.mastermind_workspace_app.contract import principal_frame
from common.workspace_source_operation_wire import FRAME_SCHEMA


# Exact accepted8cd custody-aware test helper. No production/namespace guard is removed.
async def _exercise_existing_custody(parts,action,*,existing_custody=None):
    factory,args,clock,audit,calls,auth,verifier,workspace,bearer,*_=parts
    with tempfile.TemporaryDirectory(prefix='mm-plan-',dir='/tmp') as short:
        from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
        runtime=factory.service.runtime;directory=runtime.store.path.parent
        fd=None
        if existing_custody is None:
            lock=directory/'executive-service.lock';fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            marker=directory/'executive-service.running'
            marker.write_text(json.dumps(dict(instance_id='planning-test',pid=os.getpid())));marker.chmod(0o600)
            custody=ServiceRuntimeNamespaceCustody(runtime=runtime,service_lock_fd=fd,lock_path=lock,marker_path=marker,instance_id='planning-test')
            custody.start();factory.service._namespace_custody=custody
        else:
            assert type(existing_custody) is ServiceRuntimeNamespaceCustody
            assert factory.service._namespace_custody is existing_custody
            assert existing_custody.bound_runtime(runtime).store.path.samefile(runtime.store.path)
            custody=existing_custody
        sock=Path(short)/'ceo.sock'
        server=await asyncio.start_unix_server(factory.service._handle_ceo_ingress_connection,path=str(sock),limit=73728)
        edge=OsExecutiveTransportApp(lambda *args:None,submit_authenticator=auth,submit_verifier=verifier,
            clock=lambda:clock[0],workspace_app=workspace,
            direct_result_client=DirectNativeResultClient(sock,CeoIngressClient(read_timeout=5)))
        token=bearer(factory.policies.submit);second=bearer(factory.workspace_policy)
        headers=[('authorization','Bearer '+token),('x-mastermind-workspace-authorization','Bearer '+second)]
        arguments={k:v for k,v in args.items() if k!='principal'}
        arguments['private_request']=arguments['private_request'].decode()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=edge),base_url='https://mcp.mastermind-x.com') as client:
                await action(client,headers,arguments,token,second)
        finally:
            server.close();await server.wait_closed()
            tasks=list(factory.service._ceo_ingress_tasks)
            if tasks:await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),5)
            if fd is not None:
                custody.close();os.close(fd)


def _observed_ingress_owner(builder,factory,emit):
    from common.project_planning_private_contract import ProjectPlanningIngressOwner
    actual=builder(factory)
    async def handle(frame):
        try:emit(dict(operation=frame.get('operation'),edge='ENTRY'))
        except Exception:pass
        try:
            result=await actual.handler(frame)
            try:emit(dict(operation=frame.get('operation'),edge='RETURN',
                ok=result.get('ok') if type(result) is dict and type(result.get('ok')) is bool else None))
            except Exception:pass
            return result
        except Exception as error:
            try:
                chain=[];seen=set();current=error
                reasons={'SOURCE_OPERATION_UNAVAILABLE','SOURCE_OPERATION_UNAUTHORIZED',
                    'SOURCE_OPERATION_RECIPE_UNQUALIFIED','SOURCE_OPERATION_SOURCE_UNAVAILABLE',
                    'SOURCE_OPERATION_ACTOR_UNAVAILABLE','CANONICAL_DATA_UNAVAILABLE',
                    'RESULT_UNAVAILABLE','ORIGINAL_RESULT_NOT_CONSUMED','PLAN_BASIS_UNAVAILABLE'}
                while current is not None and id(current) not in seen and len(chain)<4:
                    seen.add(id(current));reason=getattr(current,'code',None)
                    if reason not in reasons:
                        reason=current.args[0] if current.args and type(current.args[0]) is str and current.args[0] in reasons else None
                    chain.append(dict(kind=type(current).__name__,reason=reason,
                        frames=[dict(file=Path(x.filename).name,function=x.name,line=x.lineno)
                            for x in traceback.extract_tb(current.__traceback__)[-12:]]))
                    current=current.__cause__ if current.__cause__ is not None else current.__context__
                emit(dict(operation=frame.get('operation'),edge='RAISED',chain=chain))
            except Exception:pass
            raise
    # The same nominal owner validates the wire ONCE before this handler;
    # delegate the original handler ONCE, with no new source acquisition.
    return ProjectPlanningIngressOwner(handle)


def test_private_recorder_observer_preserves_one_call_and_outcome():
    from common.project_planning_private_contract import ProjectPlanningIngressOwner
    result=object();error=ValueError('private sentinel is never logged');calls=[];notes=[]
    async def callback(frame):
        calls.append(frame)
        if frame.get('fail'):raise error
        return result
    owner=_observed_ingress_owner(lambda unused:ProjectPlanningIngressOwner(callback),None,notes.append)
    assert asyncio.run(owner.handler({'operation':'status'})) is result and len(calls)==1
    with pytest.raises(ValueError) as caught:asyncio.run(owner.handler({'operation':'prepare_proposal','fail':True}))
    assert caught.value is error and len(calls)==2
    assert [note['edge'] for note in notes]==['ENTRY','RETURN','ENTRY','RAISED']
    assert 'private sentinel' not in json.dumps(notes)


def test_same_run_installed_s24_complete_consumer_fixture(completed,monkeypatch,rsa_key):
    output=os.environ.get('MM_PROJECT_CONSUMER_FIXTURE_OUTPUT')
    if not output:pytest.skip('opt-in source-issued consumer operand capture')
    f=completed;j=f['j'];factory=f['factory'];runtime=f['runtime'];workspace=j['workspace']
    assert factory.app_binding.source_operation_provider_factory is j['installed']
    binding=j['installed'](runtime,factory.service.supervisor)
    assert binding.owner._proposal is not None
    samples=[]
    def record(edge,operation,request,response,**metadata):
        samples.append(dict(sequence=len(samples)+1,edge=edge,operation=operation,
            request=copy.deepcopy(request),response=copy.deepcopy(response),**metadata))
        if 'packet' in locals_for_record:
            # Failed captures are retained as one-run PARTIAL evidence; they
            # can never be merged into a later successful fixture.
            partial=Path(output).with_name(Path(output).stem+'.'+j['tmp_path'].parent.name+'.partial.json')
            temporary=partial.with_suffix('.atomic.tmp');temporary.write_text(json.dumps(dict(locals_for_record['packet'],capture_state='PARTIAL_UNQUALIFIED'),ensure_ascii=False,indent=2)+'\n');os.replace(temporary,partial)
    locals_for_record={}
    contexts=j['installed']._permissions
    events_before=len(runtime.store.list_events())
    with pytest.raises(ValueError):
        binding.owner._proposal.prepare(f['proposal_request'],workspace)
    assert len(runtime.store.list_events())==events_before
    creation_context=contexts.bind(workspace,action='publish_project_proposal',work_ref=None).public_context()
    record('FIXED_WORKSPACE_CONTEXT','context',creation_context['selection'],creation_context)
    plan_context=contexts.bind(workspace,action='publish_project_plan_proposal',work_ref=f['args']['work_ref']).public_context()
    record('FIXED_WORKSPACE_CONTEXT','context',plan_context['selection'],plan_context)
    initial_plan,unused_view,initial_generation=binding.owner._canonical_data_source.read_plan(
        principal_frame(workspace),operation='project_plan',selection={'work_ref':f['args']['work_ref']})
    assert initial_plan['availability']=='AVAILABLE'
    assert initial_plan['source']['commit']==f['proposal_request']['expected_commit']
    record('ACTUAL_CANONICAL_PLAN_READER','project_plan',{'work_ref':f['args']['work_ref']},initial_plan,generation=initial_generation)
    record('INSTALLED_WORKSPACE_OWNER','options',{'action':'publish_project_proposal'},j['options'])
    record('INSTALLED_WORKSPACE_OWNER','prepare',{'action':'publish_project_proposal','request':j['request']},j['preview'])
    record('INSTALLED_WORKSPACE_OWNER','submit',dict(j['preview']['selection'],preview_witness=j['preview']['preview_witness']),j['pending'])
    record('ACTUAL_DEFAULT_GIT_AND_EVENT','reconcile',j['lookup'],j['status'])

    def source_call(operation,request):
        current=j['installed'](runtime,factory.service.supervisor)
        value=current.owner.handle(dict(schema=FRAME_SCHEMA,operation=operation,
            principal=principal_frame(workspace),verified_expires_at=workspace.expires_at,
            request=request),peer_guard=lambda:True)
        record('FIXED_WORKSPACE_PRIVATE_WIRE',operation,request,value)
        return value

    from tests import test_project_planning_transport as transport
    monkeypatch.setattr(transport,'fixture',lambda *_:(factory,f['args'],j['armed'],None))
    parts=transport.composition(j['tmp_path'],monkeypatch,rsa_key)
    actual_builder=transport.build_ingress_owner
    monkeypatch.setattr(transport,'build_ingress_owner',lambda actual_factory:
        _observed_ingress_owner(actual_builder,actual_factory,
            lambda note:print('CONSUMER_PRIVATE_FAILURE '+json.dumps(note,sort_keys=True),flush=True)))
    packet=dict(scope='DISPOSABLE_SOURCE_ISSUED_CONSUMER_FIXTURE_ONLY',
        recorded_at_ms=int(time.time()*1000),samples=samples,
        limitations=['Synthetic principals/JWKS, enrollment, Root seal, physical native process and Git/PR identity observations.',
            'Workspace source action wire uses verified in-process principal/peer fixture seam; not a signed Workspace HTTP proof.',
            'Executive S19/prepare_proposal use actual JWT→HTTP→AF_UNIX→fixed installed owner; no live credentials/service/provider.',
            'Replay/render may freeze this fixture timestamp. Original expiry/scopes/response schemas are never rewritten.',
            'No DEFAULT_COMMIT_WRITTEN schema is invented; actual SOURCE_OBSERVED Event and default Git postimages retained.'])
    locals_for_record['packet']=packet
    # Preserve the genuine initial operands even if HTTP setup fails. Export
    # only after all source scopes have closed; no captured payload escapes early.
    partial=Path(output).with_name(Path(output).stem+'.'+j['tmp_path'].parent.name+'.partial.json')
    temporary=partial.with_suffix('.atomic.tmp')
    temporary.write_text(json.dumps(dict(packet,capture_state='PARTIAL_UNQUALIFIED'),ensure_ascii=False,indent=2)+'\n')
    os.replace(temporary,partial)
    async def action(client,headers,arguments,*tokens):
        async def post(operation,arguments):
            path='/os/executive/project-planning/'+operation
            response=await client.post(path,headers=headers,json={'arguments':arguments})
            record('SIGNED_EXECUTIVE_HTTP',operation,{'arguments':arguments},response.json(),
                status_code=response.status_code,route=path)
            return response
        # The reserved Workspace bearer belongs ONLY on planning routes. The
        # independent Executive context uses its own single intended bearer.
        context_headers=[(k,v) for k,v in headers if k.lower()=='authorization']
        context=await client.post('/os/executive/context',headers=context_headers,json={})
        assert context.status_code==200,context.text
        record('SIGNED_EXECUTIVE_HTTP','context',{},context.json(),status_code=context.status_code,route='/os/executive/context')
        packet['identities']=dict(workspace_scope=creation_context['owner_context']['principal_scope'],
            executive_context=context.json(),work_ref=f['args']['work_ref'],
            creation_request_id=j['lookup']['request_id'],planning_operation_key=f['args']['operation_key'],
            plan_request_id=f['proposal_request']['request_id'])
        packet['consumer_inputs']=dict(create_goal=j['request']['goal'],profile_id=j['request']['profile_id'],
            create_random_byte_hex='bb',planning_stage=f['args']['stage'],
            initial_request=f['args']['private_request'].decode(),
            planning_input={k:(f['args'][k].decode() if k=='private_request' else f['args'][k]) for k in
                ('work_ref','stage','project_source','publication','grounding','private_request')},
            identity_rule='Inputs fixed BEFORE Job; actual TS planningOperationKey/directConsumeIdentity must verify, no response rewriting')
        assert packet['identities']['workspace_scope']!=context.json()['principal_scope']
        lookup={k:f['args'][k] for k in ('operation_key','work_ref')}
        # Retain the ACTUAL admission envelope the mounted App producer needs.
        # This is the same already-completed original request: a status DTO is
        # never relabelled as submit, and no second Job/Attempt may be created.
        jobs_before=len(runtime.jobs.list_jobs());attempts_before=len(runtime.attempts.list_attempts())
        submit_args={k:(f['args'][k].decode() if k=='private_request' else f['args'][k])
            for k in ('operation_key','work_ref','stage','project_source','publication','grounding','private_request')}
        admitted=await post('submit',submit_args)
        assert admitted.status_code==200
        assert admitted.json()['data']['job_id']==f['proposal_request']['selection']['job_id']
        assert admitted.json()['data']['duplicate'] is True
        assert len(runtime.jobs.list_jobs())==jobs_before==1
        assert len(runtime.attempts.list_attempts())==attempts_before==1
        status=await post('status',lookup);assert status.status_code==200,status.text
        result=await post('result',lookup);assert result.status_code==200,result.text
        data=result.json()['data'];assert data['availability']=='AVAILABLE'
        assert data['consumption']=={'state':'UNCONSUMED','receipt_digest':None}
        proposal_arguments=dict(lookup,proposal_request=f['proposal_request'])
        events=len(runtime.store.list_events())
        refused=await post('prepare_proposal',proposal_arguments)
        assert refused.status_code!=200 and len(runtime.store.list_events())==events
        identity=dict(schema='mastermind.direct_native_consume_pointer.v1',
            principal_scope=context.json()['principal_scope'],**data['selection'],result_digest=data['result']['result_digest'])
        consume_key='mmos-consume-'+hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:40]
        consume=dict(lookup,attempt_id=data['selection']['attempt_id'],result_digest=data['result']['result_digest'],
            consumption_operation_key=consume_key)
        kept=await post('consume',consume);assert kept.status_code==200,kept.text
        assert kept.json()['data']['consumption']['state']=='CONSUMED'
        # Current source WRITE grant is independent of the S19 result READ.
        grant=f['slot']['project_plan_proposal_publish']
        f['slot']['project_plan_proposal_publish']=None
        events=len(runtime.store.list_events())
        try:
            refused=await post('prepare_proposal',proposal_arguments)
            assert refused.status_code!=200 and len(runtime.store.list_events())==events
        finally:f['slot']['project_plan_proposal_publish']=grant
        prepared=await post('prepare_proposal',proposal_arguments)
        assert prepared.status_code==200,prepared.text
        preview=prepared.json()['data'];assert preview['preview']['status']=='DRAFT_ONLY'
        reopened=await post('prepare_proposal',proposal_arguments)
        assert reopened.status_code==200 and reopened.json()['data']==preview
        selected=dict(schema='mastermind.workspace_source_operation_lookup.v1',**preview['selection'])
        pending=source_call('submit',dict(preview['selection'],preview_witness=preview['preview_witness']))
        assert pending['receipt']['kind']=='PROPOSAL_OBSERVED'
        root=j['tmp_path']/'consumer-fixture-default-actor'
        git(j['tmp_path'],'clone',str(j['o']['env'].origin),str(root))
        git(root,'fetch','origin',pending['receipt']['proposal']['head_branch'])
        git(root,'merge','--no-ff','--no-edit','FETCH_HEAD');git(root,'push','origin','main')
        accepted=source_call('reconcile',selected)
        assert accepted['disposition']=='accepted' and accepted['receipt']['kind']=='SOURCE_OBSERVED'
        current=j['installed'](runtime,factory.service.supervisor).owner._canonical_data_source
        compared,unused_view,generation=current.read_plan(principal_frame(workspace),operation='project_plan',selection={'work_ref':f['args']['work_ref']})
        assert compared['availability']=='AVAILABLE'
        assert compared['source']['commit']==rev_parse(root,'HEAD')
        assert any(x['proposal_id']==preview['preview']['proposal_id'] for x in compared['continuity']['proposals']['items'])
        record('ACTUAL_CANONICAL_PLAN_READER','project_plan',{'work_ref':f['args']['work_ref']},compared,generation=generation)
        assert source_call('read',selected)==accepted
        assert source_call('submit',dict(preview['selection'],preview_witness=preview['preview_witness']))==accepted
        stale=await post('result',lookup);assert stale.status_code!=200
        packet['source_events']=[dataclasses.asdict(event) for event in runtime.store.list_events(aggregate_type='project_source_operation')]
        packet['assertions']=dict(jobs=len(runtime.jobs.list_jobs()),attempts=len(runtime.attempts.list_attempts()),
            inert_pr_observations=j['o']['pr'].create_calls,plan_default_commit=rev_parse(root,'HEAD'),
            original_source_stale=True,original_workspace_status_readable=True)
        assert packet['assertions']['jobs']==packet['assertions']['attempts']==1
        assert packet['assertions']['inert_pr_observations']==2
        packet['capture_state']='COMPLETE'
        raw=json.dumps(packet,ensure_ascii=False,sort_keys=True,indent=2)
        for token in tokens:assert token not in raw
        temporary=Path(output).with_suffix('.atomic.tmp');temporary.write_text(raw+'\n');os.replace(temporary,Path(output))
    asyncio.run(_exercise_existing_custody(parts,action,existing_custody=factory.service._namespace_custody))
