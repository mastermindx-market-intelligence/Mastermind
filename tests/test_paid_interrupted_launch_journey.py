"""Real Launch controller -> authenticated HTTP -> durable Runtime interruption.

Synthetic RSA/host/publication observations are fixture edges. No provider or
worker is invoked. This recovers the actual queued Job, not a completed result.
The accepted manifest projection is fixture DATA; no sealed asset is opened.
"""
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil

from control_plane.executive_service import ExecutiveControlService, CeoIngressAppBinding, CEO_WEB_CEO_V2_READ_SCHEMA
from control_plane.executive_paid_fabric_composition import PaidWorkPlacement
from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.mastermind_executive_app.os_commission_client import StudioCommissionClient, PreparationResult
from tests import test_mastermind_executive_app_asgi as auth
from tests.test_mastermind_os_executive_transport import headers
from tests.test_paid_authenticated_launch_producer import (
    ROOT, OS_RESOURCE, MANIFEST_PROJECTION, OBJECTIVE, actual_launch_payload, launch_http,
)

rsa_key=auth.rsa_key
short_socket_root=auth.short_socket_root
EXTRA_PINS={
 'orchestration/operation-controller.ts':'9f21d8b2231be09048b38c5c696e14d9c2a53d0a47d75387e4cd8f544fb444fd',
 'mission.ts':'20bf1a35c5be760c8418930972ad9adaab23bbde36a3e8b88a2caa72b42b67bb',
 'workspace-contract.ts':'14992cfc81dbc577cf50ba7198285b21652bb25eb5cc6c0efc53954e33ef11b1',
}


def _compile_controller(tmp_path,scope):
    actual_launch_payload(tmp_path,scope)  # Actual manifest decoder/producer and its source pins.
    for name,digest in EXTRA_PINS.items():
        assert hashlib.sha256((ROOT/'app/mastermind_os/src'/name).read_bytes()).hexdigest()==digest
    script=r'''
import fs from 'node:fs';import path from 'node:path';import {stripTypeScriptTypes} from 'node:module';
const i=JSON.parse(fs.readFileSync(0,'utf8'));
for(const [name,file,oldPath,newPath] of [
 ['operation-controller','orchestration/operation-controller.ts','"../mission"','"./mission.mjs"'],
 ['mission','mission.ts','"./workspace-contract"','"./workspace-contract.mjs"'],
 ['workspace-contract','workspace-contract.ts',null,null]]){
 let code=stripTypeScriptTypes(fs.readFileSync(path.join(i.source,file),'utf8'),{mode:'transform'});
 if(oldPath){if(!code.includes(oldPath))throw Error('dependency drift');code=code.replace(oldPath,newPath);}
 fs.writeFileSync(path.join(i.scratch,name+'.mjs'),code);
}
'''
    node=os.environ.get('MM_TEST_TYPESCRIPT_NODE') or shutil.which('node')
    assert node,'Node with the supported TypeScript transform API is required'
    result=subprocess.run([node,'--input-type=module','-e',script],input=json.dumps({
        'source':str(ROOT/'app/mastermind_os/src'),'scratch':str(tmp_path/'compiled-consumer')}),
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    return node,tmp_path/'compiled-consumer'


async def _driver(node,compiled,phase,input_path,hint_path,http,token,*,on_commit=None):
    process=await asyncio.create_subprocess_exec(node,str(ROOT/'tests/fixtures/paid_interrupted_launch_consumer.mjs'),
        phase,str(compiled/'executive-launch-command-port.mjs'),str(compiled/'operation-controller.mjs'),
        str(input_path),str(hint_path),stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    calls=[];last_response=None
    try:
        while True:
            line=await asyncio.wait_for(process.stdout.readline(),20)
            assert line,'driver exited without result: '+(await process.stderr.read()).decode()+' last HTTP reply: '+json.dumps(last_response)
            frame=json.loads(line)
            if frame['type']=='result':
                await asyncio.wait_for(process.wait(),5)
                assert process.returncode==0,(await process.stderr.read()).decode()
                return frame,calls
            assert frame['type']=='call'
            name=frame['name'];args=frame['arguments'];calls.append((name,args))
            endpoint={'submit_ceo_intent':'submit','ceo_intent_status':'status'}[name]
            response=await http.post('/os/executive/'+endpoint,headers=headers(token),json={'arguments':args})
            assert response.status_code==200,response.text
            last_response=response.json()
            if phase=='begin':
                assert name=='submit_ceo_intent' and response.json()['status']=='accepted'
                assert on_commit is not None
                on_commit(response.json(),args)
                # Actual accepted HTTP reply is lost only at the browser edge.
                answer={'throw':'fixture response lost'}
            else:
                assert name=='ceo_intent_status'
                answer={'envelope':response.json()}
            process.stdin.write((json.dumps(answer)+'\n').encode());await process.stdin.drain()
    finally:
        if process.returncode is None:
            process.kill();await process.wait()  # Only this test-owned local IPC process.


def test_paid_authenticated_launch_lost_reply_reopens_original_job(
    rsa_key,tmp_path,short_socket_root,monkeypatch,
):
    mastermind=tmp_path/'mastermind';macro=tmp_path/'macro'
    commit=auth._git_repo(mastermind)
    (macro/'scripts').mkdir(parents=True);(macro/'scripts/agentos.py').write_text('')
    (macro/'agentos').mkdir();auth._git_repo(macro)
    source={'schema_version':'mastermind.executive_dialogue_source/v1',
        'work_ref':MANIFEST_PROJECTION['workstream'],'commission_ref':{
            'repository':'mastermindx-market-intelligence/Mastermind','commit':commit,'path':'README.md',
            'content_sha256':hashlib.sha256((mastermind/'README.md').read_bytes()).hexdigest()},'watch_mode':None}
    source_calls=[]
    def source_provider(intent_id,work_ref):
        assert work_ref==source['work_ref'];source_calls.append((intent_id,work_ref));return source
    async def exercise():
        base=auth._real_service(tmp_path,socket_root=short_socket_root,mastermind_root=mastermind,macro_root=macro)
        config=dataclasses.replace(base.config,proof_source_repository=mastermind,proof_base_sha=commit,
            coo_paid_work_placements=(PaidWorkPlacement('glm.paid.sealed-input','offline-paid-read'),))
        grounding=auth._RealGitGroundingProvider(mastermind_root=mastermind,macro_root=macro)
        readers=WebCeoV2InstalledExecutiveReaders(repo_root=mastermind,macro_root=macro,runtime_root=config.runtime_root)
        service=ExecutiveControlService(config,supervisor_factory=lambda _:auth._NoExecutionSupervisor(),
            ceo_ingress_socket_path=short_socket_root/'h4.sock',ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_armed=False,ceo_ingress_grounding_provider=grounding,
            ceo_ingress_dialogue_source_provider=source_provider,
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,
                grounding_provider=grounding,read_provider=readers,read_schema=CEO_WEB_CEO_V2_READ_SCHEMA))
        await service.start()
        try:
            settings=auth._real_app_settings(rsa_key,mastermind_root=mastermind,macro_root=macro,
                ceo_ingress_socket_path=service.ceo_ingress_socket_path)
            policies={'resource':OS_RESOURCE,'resource_metadata_url':OS_RESOURCE+'/.well-known/oauth-protected-resource'}
            settings=dataclasses.replace(settings,read_from_ceo_ingress=True,
                policies=AppPolicies(read=auth._read_policy(**policies),submit=auth._submit_policy(**policies)))
            token=auth._submit_token(rsa_key,aud=OS_RESOURCE);preparations=[]
            async def publication_observation(self,*,arguments,bearer,principal_scope):
                assert bearer==token and len(principal_scope)==64;preparations.append(dict(arguments))
                return PreparationResult('prepared',arguments['operation_key'],commit,
                    source['commission_ref']['content_sha256'])
            monkeypatch.setattr(StudioCommissionClient,'prepare',publication_observation)
            committed=[]
            def observe_commit(envelope,payload):
                root=service.runtime.jobs.get_job(envelope['receipt']['job_id'])
                assert envelope['receipt']['status']=='QUEUED' and envelope['receipt']['dispatched'] is False
                assert root.constraints['cost_class']=='default'
                assert root.constraints['paid_subject_review_binding']==service._coo_execution_binding['paid_subject_review_binding']
                assert len(service.runtime.jobs.list_jobs())==1
                committed.append((root,payload))
            hint=tmp_path/'pending-pointer.json';input_path=tmp_path/'consumer-input.json'
            async with launch_http(settings,StudioCommissionClient(port=45025)) as http:
                context=await http.post('/os/executive/context',headers=headers(token),json={})
                assert context.status_code==200,context.text
                scope=context.json()['principal_scope'];node,compiled=_compile_controller(tmp_path,scope)
                input_data={'config':MANIFEST_PROJECTION,'form':{'goal':OBJECTIVE,
                    'projectRef':'executive-infrastructure','profileRef':'research_only'},
                    'principalScope':scope,'generation':'authenticated-epoch-1'}
                input_path.write_text(json.dumps(input_data))
                begun,begin_calls=await _driver(node,compiled,'begin',input_path,hint,http,token,on_commit=observe_commit)
                assert begun['state']['status']=='unknown' and len(begin_calls)==1 and len(committed)==1
                persisted=json.loads(hint.read_text());original_pointer=persisted['pointer']
                assert set(persisted)=={'scope','pointer'} and persisted['scope']==scope
                assert set(original_pointer)=={'operationKey','kind','targetKey'}
                assert original_pointer['operationKey']==committed[0][1]['operation_key']
            # New HTTP app and separate Node controller process, same durable hint.
            input_data['generation']='authenticated-epoch-2'
            input_data['config']={**MANIFEST_PROJECTION,'workstream':'WS:CHANGED-DRAFT'}
            input_data['form']={**input_data['form'],'goal':'Different draft must not submit.'}
            input_path.write_text(json.dumps(input_data))
            async with launch_http(settings,StudioCommissionClient(port=45025)) as reopened_http:
                recovered,recovery_calls=await _driver(node,compiled,'reopen',input_path,hint,reopened_http,token)
            assert recovered['state']['status']=='accepted',recovered
            assert len(recovery_calls)==1 and recovery_calls[0][0]=='ceo_intent_status'
            selection=recovered['state']['missionSelection'];root,payload=committed[0]
            assert selection['rootJobId']==root.job_id and selection['workRef']==source['work_ref']
            assert not hint.exists() and len(preparations)==1
            assert source_calls and len(set(source_calls))==1
            assert recovery_calls[0][1]['intent_id']==source_calls[0][0]
            assert len(service.runtime.jobs.list_jobs())==1
            assert service.runtime.attempts.list_attempts(root.job_id)==[] and service.runtime.workers.list_workers()==[]
            created=[e for e in service.runtime.events.list_events(job_id=root.job_id) if e.event_type=='JOB_CREATED']
            assert len(created)==1
        finally:
            await service.close()
    asyncio.run(exercise())
