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
import pytest
from pathlib import Path
from control_plane import executive_runtime as er
from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding
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
    completed=subprocess.run([os.environ['MM_TEST_TYPESCRIPT_NODE'],'--input-type=module','-e',script],
        input=json.dumps(dict(source=str(root),scratch=str(scratch),raw=json.dumps(view),selection=view['selection'],principal_scope=principal_scope)),
        capture_output=True,text=True,timeout=15)
    assert completed.returncode==0,completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.parametrize('execution',['closed','publication-loss','full','late-loss'])
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
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=grounding,read_provider=readers))
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
