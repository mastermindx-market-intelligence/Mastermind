"""Signed real App/HTTP/private Unix/Runtime join; no physical worker here.

Real signed auth, TS producer, Service, allocator, native Supervisor, Runtime
validators and result/consume owners stay connected. Only Root receipt/current
host grant, source-publication observation and physical process/UID/broker
observations are simulated; no provider process or live host is touched.
"""
import asyncio
import dataclasses
import hashlib
import os
import json
import subprocess
import shutil
import pytest
from pathlib import Path
from control_plane import executive_runtime as er, ceo_request
from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding,CEO_WEB_CEO_V2_READ_SCHEMA
from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_executive_app.os_commission_client import StudioCommissionClient,PreparationResult
from tests import test_paid_authenticated_launch_producer as app
from tests.test_mastermind_os_executive_transport import headers
from tests import test_mastermind_executive_app_asgi as auth
rsa_key=auth.rsa_key
short_socket_root=auth.short_socket_root


def actual_consume_payload(tmp_path,view,principal_scope):
    root=Path(__file__).resolve().parents[1]/'app/mastermind_os/src'
    pins={'direct-native-result.ts':'b181c43301be0ab96fb92056b2c4511b75c4628da1c7a6bbfcf95ff58a58f43d',
        'orchestration/direct-native-command-port.ts':'d505d4cb1a765b49bc7b656f22f5f470e29d10f4998b82b17cdb2d38a43f32b2'}
    for path,sha in pins.items():assert hashlib.sha256((root/path).read_bytes()).hexdigest()==sha
    scratch=tmp_path/'actual-result-consumer';scratch.mkdir()
    script=r'''
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stripTypeScriptTypes} from 'node:module';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
for(const [name,file] of [['operation-key','orchestration/operation-key.ts'],
 ['direct-native-result','direct-native-result.ts'],['direct-native-command-port','orchestration/direct-native-command-port.ts']]) {
 let code=stripTypeScriptTypes(fs.readFileSync(path.join(input.source,file),'utf8'),{mode:'transform'});
 code=code.replaceAll('"./orchestration/operation-key"','"./operation-key.mjs"')
 .replaceAll('"./operation-key"','"./operation-key.mjs"')
 .replaceAll('"../direct-native-result"','"./direct-native-result.mjs"');
 fs.writeFileSync(path.join(input.scratch,name+'.mjs'),code);
}
const result=await import(pathToFileURL(path.join(input.scratch,'direct-native-result.mjs')));
const view=result.decodeDirectNativeResult(result.parseDirectNativeJson(input.raw),input.selection);
if(!view||view.availability!=='AVAILABLE')throw Error('actual App decoder refused actual Runtime result');
const {DirectNativeCommandPort}=await import(pathToFileURL(path.join(input.scratch,'direct-native-command-port.mjs')));
const port=new DirectNativeCommandPort({read(){throw Error('not a transport fixture');},consume(){throw Error('not a transport fixture');}},
 ()=>({principalScope:input.principal_scope,generation:'offline-authenticated-context'}));
const intent=port.makeConsumeIntent(view.selection,view.result.result_digest);
if(!intent)throw Error('actual App consume producer refused result');
port.prepare(intent);
process.stdout.write(JSON.stringify(intent.payload));
'''
    node = os.environ.get('MM_TEST_TYPESCRIPT_NODE') or shutil.which('node')
    assert node, 'Node.js is required for the actual TypeScript consumer proof'
    completed=subprocess.run([node,'--input-type=module','-e',script],
        input=json.dumps(dict(source=str(root),scratch=str(scratch),raw=json.dumps(view),selection=view['selection'],principal_scope=principal_scope)),
        capture_output=True,text=True,timeout=15)
    assert completed.returncode==0,completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize('execution',['closed','publication-loss','admission-loss','full','late-loss'])
def test_actual_native_ts_authenticated_http_unix_admits_one_role_null_job(rsa_key,tmp_path,short_socket_root,monkeypatch,execution):
    mastermind=tmp_path/'mastermind';macro=tmp_path/'macro'
    commit=auth._git_repo(mastermind)
    (macro/'scripts').mkdir(parents=True);(macro/'scripts'/'agentos.py').write_text('')
    (macro/'agentos').mkdir();auth._git_repo(macro)
    source=dict(schema_version=er.EXECUTIVE_DIALOGUE_SOURCE_SCHEMA,work_ref=app.MANIFEST_PROJECTION['workstream'],
        commission_ref=dict(repository='mastermindx-market-intelligence/Mastermind',commit=commit,path='README.md',
            content_sha256=hashlib.sha256((mastermind/'README.md').read_bytes()).hexdigest()),watch_mode=None)
    async def exercise():
        base=auth._real_service(tmp_path,socket_root=short_socket_root,mastermind_root=mastermind,macro_root=macro)
        armed=execution!='closed'
        config=dataclasses.replace(base.config,proof_source_repository=mastermind,proof_base_sha=commit,
            proof_shared_gid=os.getegid(),ceo_submit_armed=True,coo_autonomy_armed=armed,
            coo_operator_harness_armed=armed,coo_foreground_only=armed)
        config.proof_workspace_root.mkdir(parents=True)
        grounding=auth._RealGitGroundingProvider(mastermind_root=mastermind,macro_root=macro)
        readers=WebCeoV2InstalledExecutiveReaders(repo_root=mastermind,macro_root=macro,runtime_root=config.runtime_root)
        from tests.test_direct_native_supervisor_runtime_join import make_direct_supervisor
        def supervisor_factory(runtime):
            from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
            primary=make_direct_supervisor(runtime,workspace_root=config.proof_workspace_root,
                runs_root=tmp_path/'runs',provider_home=tmp_path/'provider-home')
            # Actual normal mixed factory preserves this primary; direct mode
            # must not need an admitted paid/attended owner to invoke it.
            return MixedExecutionOwnerSupervisor(primary,{config.worker_id:primary})
        async def inert_operator_identity():pass
        service=ExecutiveControlService(config,supervisor_factory=supervisor_factory,
            operator_supervisor_factory=lambda *_:auth._NoExecutionSupervisor(),
            operator_identity_verifier=inert_operator_identity,autonomy_guard=(lambda:None) if armed else None,
            ceo_submit_admission_guard=lambda:None,direct_native_generation_provider=lambda:'a'*64,
            ceo_ingress_socket_path=short_socket_root/'native-http.sock',ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_armed=False,ceo_ingress_grounding_provider=grounding,
            ceo_ingress_dialogue_source_provider=lambda _intent,_work:source,
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=grounding,read_provider=readers,read_schema=CEO_WEB_CEO_V2_READ_SCHEMA))
        await service.start()
        try:
            # I1: merely installing the provider/startup creates no quota rows;
            # ordinary registration retains its incumbent view exactly.
            assert service.runtime.workers.list_workers()==[]
            service._register_worker()
            readonly_quota=service.config.coo_default_quota_class+'.review'
            assert service.runtime.workers.get_quota_class(service.config.worker_id,readonly_quota) is None
            def quota_rows():
                with service.runtime.store.read() as connection:
                    return [dict(q) for q in connection.execute('SELECT * FROM worker_quota_classes ORDER BY worker_id,quota_class')]
            before_quotas=quota_rows()
            native=service.supervisor.primary
            if execution=='admission-loss':
                from control_plane import ceo_intent
                original_receipt=ceo_intent.build_receipt
                def lost_after_commit(*args,**kwargs):raise OSError('inert post-admission receipt loss')
                monkeypatch.setattr(ceo_intent,'build_receipt',lost_after_commit)
            if execution=='publication-loss':
                original_create=er.JobRegistry._create_job_in_transaction
                def revoke_before_commit(registry,*args,**kwargs):
                    value=original_create(registry,*args,**kwargs)
                    service.config=dataclasses.replace(service.config,coo_autonomy_armed=False)
                    return value
                monkeypatch.setattr(er.JobRegistry,'_create_job_in_transaction',revoke_before_commit)
            if execution=='late-loss':
                original=native._launch_spec
                def revoke_after_preparation(*args,**kwargs):
                    value=original(*args,**kwargs)
                    service.config=dataclasses.replace(service.config,coo_autonomy_armed=False)
                    return value
                monkeypatch.setattr(native,'_launch_spec',revoke_after_preparation)
            settings=auth._real_app_settings(rsa_key,mastermind_root=mastermind,macro_root=macro,ceo_ingress_socket_path=service.ceo_ingress_socket_path)
            kwargs=dict(resource=app.OS_RESOURCE,resource_metadata_url=app.OS_RESOURCE+'/.well-known/oauth-protected-resource')
            settings=dataclasses.replace(settings,read_from_ceo_ingress=True,policies=AppPolicies(read=auth._read_policy(**kwargs),submit=auth._submit_policy(**kwargs)))
            token=auth._submit_token(rsa_key,aud=app.OS_RESOURCE)
            async def publication(self,*,arguments,bearer,principal_scope):
                assert bearer==token
                return PreparationResult('prepared',arguments['operation_key'],commit,source['commission_ref']['content_sha256'])
            monkeypatch.setattr(StudioCommissionClient,'prepare',publication)
            async with app.launch_http(settings,StudioCommissionClient(port=45025)) as http:
                context=await http.post('/os/executive/context',headers=headers(token),json={})
                assert context.status_code==200,context.text
                manifest=dict(app.MANIFEST_PROJECTION,profiles=[*app.MANIFEST_PROJECTION['profiles'],dict(ref='native_research_only',label='Native research only')])
                payload=app.actual_launch_payload(tmp_path,context.json()['principal_scope'],profile_ref='native_research_only',manifest_projection=manifest)
                response=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':payload})
                if execution=='admission-loss':
                    assert response.status_code==202 and response.json()['status']=='effect_unknown',response.text
                    assert len(service.runtime.jobs.list_jobs())==1 and service.runtime.attempts.list_attempts()==[]
                    assert native.adapter.start_count==0
                    monkeypatch.setattr(ceo_intent,'build_receipt',original_receipt)
                    original_id=ceo_request.automated_intent_id(response.json()['request_ref'])
                    local_receipt=ceo_intent.resolve_intent(service.runtime,original_id)
                    assert local_receipt['schema']=='mastermind.ceo_direct_native_receipt.v1'
                    direct_status=await asyncio.to_thread(readers._read,'ceo_intent_status',{'intent_id':original_id},'2026-10-24T12:00:00+00:00')
                    assert direct_status['ok'],direct_status
                    # Original status lookup learns durable mode/Job from its
                    # actual admitted Event; no submit or launch is repeated.
                    recovered=await http.post('/os/executive/status',headers=headers(token),json={'arguments':{'intent_id':ceo_request.automated_intent_id(response.json()['request_ref'])}})
                    assert recovered.status_code==200,recovered.text
                    assert recovered.json().get('data') is not None,recovered.text
                    assert recovered.json()['data']['schema']=='mastermind.ceo_direct_native_receipt.v1'
                    assert recovered.json()['data']['job_id']==service.runtime.jobs.list_jobs()[0].job_id
                    assert recovered.json()['data']['status']=='QUEUED'
                    assert recovered.json()['data']['dispatched'] is False
                    assert service.runtime.attempts.list_attempts()==[]
                    assert native.adapter.start_count==0
                    return
                if not armed or execution=='publication-loss':
                    assert response.status_code!=200 or response.json()['status']!='accepted',response.text
                    assert service.runtime.jobs.list_jobs()==[] and service.runtime.attempts.list_attempts()==[]
                    assert native.adapter.start_count==0
                    assert quota_rows()==before_quotas
                    # Studio preparation was independently reached; zero native
                    # Job is not a claim that source-publication had no effect.
                    return
                assert response.status_code==200,response.text
                result=response.json();assert result['status']=='accepted',result
                receipt=result['receipt'];assert receipt['schema']=='mastermind.ceo_direct_native_receipt.v1'
                job=service.runtime.jobs.get_job(receipt['job_id'])
                assert job.orchestration_role is None and job.parent_job_id is None and job.root_job_id==job.job_id
                assert job.attempt_limit==1 and job.allowed_write_paths==[] and job.validation_commands==[]
                assert job.constraints['execution_profile_id']=='sealed.worker.readonly.no-extensions.v1'
                assert len(service.runtime.jobs.list_jobs())==1
                if execution=='late-loss':
                    assert len(service.runtime.attempts.list_attempts())==1
                    assert native.adapter.start_count==0
                    assert 'original direct dispatch unavailable' in service._dispatch_errors[job.job_id]
                    return
                tasks=tuple(service._dispatch_tasks.values())
                if tasks:await asyncio.gather(*tasks)
                assert service.runtime.jobs.get_job(job.job_id).status is er.JobStatus.COMPLETED,service._dispatch_errors
                assert len(service.runtime.attempts.list_attempts())==1 and native.adapter.start_count==1
                repeated=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':payload})
                assert repeated.status_code==200,repeated.text
                assert repeated.json()['receipt']['duplicate'] is True
                assert len(service.runtime.jobs.list_jobs())==1
                found=await http.post('/os/executive/direct-native/result',headers=headers(token),json=dict(work_ref=source['work_ref'],job_id=job.job_id,attempt_id=None))
                assert found.status_code==200,found.text
                view=found.json();assert view['availability']=='AVAILABLE',view
                assert view['consumption']['state']=='UNCONSUMED'
                assert view['result']['summary']=='Retained direct research findings'
                request=actual_consume_payload(tmp_path,view,context.json()['principal_scope'])
                # R2: fail the readback AFTER actual existing Event commit.
                owner=service._namespace_custody
                actual_bound=owner.bound_runtime
                def lose_after_commit(_runtime):raise OSError('inert postcommit read loss')
                monkeypatch.setattr(owner,'bound_runtime',lose_after_commit)
                lost=await http.post('/os/executive/direct-native/consume',headers=headers(token),json=request)
                assert lost.status_code==200,lost.text
                assert lost.json()['reason_codes']==['EFFECT_UNKNOWN'] and lost.json()['consumption'] is None,lost.text
                with service.runtime.store.read() as connection:
                    assert connection.execute("SELECT count(*) FROM events WHERE event_type='DIRECT_NATIVE_RESULT_CONSUMED'").fetchone()[0]==1
                monkeypatch.setattr(owner,'bound_runtime',actual_bound)
                # Resolve only by original selection read; no consume resubmit.
                recovered=await http.post('/os/executive/direct-native/result',headers=headers(token),json=view['selection'])
                assert recovered.status_code==200,recovered.text
                acknowledged=recovered.json();assert acknowledged['availability']=='AVAILABLE',acknowledged
                assert acknowledged['consumption']['state']=='CONSUMED'
                assert acknowledged['result']==view['result']
                assert native.adapter.start_count==1 and len(service.runtime.jobs.list_jobs())==1
        finally:await service.close()
    asyncio.run(exercise())


def test_normal_installed_factory_closed_arm_startup_creates_no_native_quota(tmp_path,short_socket_root,monkeypatch):
    """Real normal factory+Service start; only launchd activation is inert.

    No Worker broker call, account read, live path or provider is available.
    The configured direct callable itself must confer no registration effect.
    """
    from tests.test_ceo_submit_armed_composition import _module,_raw,_write
    module=_module()
    raw=_raw(tmp_path,control_socket_path=str(short_socket_root/'closed-factory.sock'),
        shared_run_gid=os.getegid(),ceo_submit_armed=False,coo_autonomy_armed=False,coo_operator_harness_armed=False)
    loaded=module.load_control_config(_write(tmp_path,raw))
    monkeypatch.setattr(module,'activate_launchd_socket',lambda _:None)
    service=module._service_from_config(loaded,direct_native_generation_provider=lambda:'a'*64)
    async def exercise():
        await service.start()
        try:
            assert service.service_state=='AWAITING_CANARY'
            assert service.runtime.workers.list_workers()==[] and service.runtime.jobs.list_jobs()==[]
            service._register_worker()
            assert service.runtime.workers.get_quota_class(service.config.worker_id,
                service.config.coo_default_quota_class+'.review') is None
        finally:await service.close()
    asyncio.run(exercise())


def test_normal_full_arm_factory_retains_native_primary_and_execution_guards(tmp_path,short_socket_root,monkeypatch):
    """Actual installed factory constructor; broker/source/Root facts inert.

    This binds the normal factory to the independently joined native owner. It
    does not claim a physical Worker invocation from this constructor fixture.
    """
    from tests.test_ceo_submit_armed_composition import _module,_raw,_write
    from tests.test_executive_terminal_return import _SEALED_WORKER_SECRET_CANARY
    from control_plane import executive_worker_broker as broker
    from control_plane.executive_supervisor import ExecutiveSupervisor
    module=_module()
    raw=_raw(tmp_path,control_socket_path=str(short_socket_root/'armed-factory.sock'),shared_run_gid=os.getegid(),
        ceo_submit_armed=True,coo_autonomy_armed=True,coo_operator_harness_armed=True,coo_foreground_only=True,
        operator_harness_binary_digest='b'*64,operator_harness_version='inert-qualified')
    loaded=module.load_control_config(_write(tmp_path,raw))
    client=object()
    monkeypatch.setattr(broker,'WorkerBrokerClient',lambda *_,**__:client)
    monkeypatch.setattr(module,'activate_launchd_socket',lambda _:None)
    guards=[]
    def autonomy():guards.append('existing-full-autonomy')
    def admission():guards.append('existing-ceo-coexistence')
    def generation():return 'a'*64
    service=module._service_from_config(loaded,autonomy_guard=autonomy,ceo_submit_admission_guard=admission,
        direct_native_generation_provider=generation,initial_canary=_SEALED_WORKER_SECRET_CANARY)
    runtime=er.Runtime.at(tmp_path/'constructor-runtime')
    native=service._supervisor_factory(runtime)
    assert type(native) is ExecutiveSupervisor and type(native.adapter) is broker.RemoteCodexWorkerAdapter
    assert native.runtime is runtime and native.require_complete_launch_attestation is True
    assert service._direct_native_generation_provider is generation and service._autonomy_guard is autonomy
    assert service.config.coo_foreground_only is True
    assert service.config.coo_operator_model_alias!='coo.operator.native-return'
    from control_plane import direct_native_execution as dn
    base=dn._issue_access('d'*64,'WS:H2','a'*64,generation)
    execution=service._direct_native_execution_access(base)
    execution.check()
    assert guards and set(guards)=={'existing-full-autonomy','existing-ceo-coexistence'}
