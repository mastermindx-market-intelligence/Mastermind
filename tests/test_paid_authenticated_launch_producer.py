"""Authenticated Launch producer, real temporary HTTP/AF_UNIX/Runtime only.

Manifest selection values below are the principal-accepted projection of the qualified
02649 staged build. The sealed launch-config file refused a filesystem read;
this test never opens it or claims fresh byte-read proof. Choice labels are
fixture presentation text, not asserted sealed-manifest bytes. JWT signing keys and
commission/host observations are disposable fixture DATA, never live credentials,
registration, admission or a provider call. The actual TS request producer,
RS256/auth/audit/HTTP/Unix ingress and Service host-binding code stay in the path.
"""
import asyncio
from contextlib import asynccontextmanager
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil

import pytest
import httpx

from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding
from control_plane.executive_paid_fabric_composition import PaidWorkPlacement
from control_plane.executive_coo_policy import CooCyclePolicy
from control_plane.executive_runtime import OrchestrationDispatchOutcome
from control_plane.model_router import ModelRouter
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.executive_mcp.web_ceo import WebCeoV2InstalledExecutiveReaders
from tests import test_mastermind_executive_app_asgi as auth
from tests.test_mastermind_os_executive_transport import headers,Sink,FixedMdm,_assets
from integrations.executive_mcp import server as transport_server
from integrations.mastermind_executive_app.os_commission_client import StudioCommissionClient,PreparationResult
from tests.test_executive_os_phase1fc import _complete_ohf_role

rsa_key=auth.rsa_key
short_socket_root=auth.short_socket_root
ROOT=Path(__file__).resolve().parents[1]
OS_RESOURCE='https://mcp.mastermind-x.com/os/executive'
MANIFEST_PROJECTION={
    'workstream':'WS:EXECUTIVE-ECOSYSTEM-COMPLETION','priority':0,'attemptLimit':1,
    'projects':[{'ref':'executive-infrastructure','label':'Executive infrastructure'}],
    'profiles':[{'ref':'research_only','label':'Research only'}],
}
OBJECTIVE=('Assess launch-readiness from supplied exact release evidence. Two independent read-only '
    'analyses cover auth/admission/launch and return/recovery/effect preservation. Review only the '
    'auth/admission/launch analysis; the original parent reconciles both and labels the second unreviewed.')
# These pins identify the exact published #1315 Launch source; any source drift refuses.
SOURCE_PINS={
    'app/mastermind_os/src/orchestration/operation-key.ts':
        'de1b4f7bf74030b6c71b956440801760452f17049d13fa423a9fac6aeec2562f',
    'app/mastermind_os/src/orchestration/executive-launch-command-port.ts':
        '5ead9e73c047a50d085208f9e981cdedae54bf23c9304c2a57da7c0cf2bd4321',
    'app/mastermind_os/src/launch-config.ts':
        '692df4fda3a95a5142c3a36b84d4b7a8ca22a2a606518ee2c92e7628ab770d11',
}


def actual_launch_payload(tmp_path,principal_scope):
    """Execute actual frozen TS producer with Node's supported TS transformer."""
    for name,digest in SOURCE_PINS.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
    script=r'''
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stripTypeScriptTypes} from 'node:module';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const folder=input.scratch;
for(const [name,source] of [
 ['operation-key', 'orchestration/operation-key.ts'],
 ['executive-launch-command-port','orchestration/executive-launch-command-port.ts'],
 ['launch-config','launch-config.ts']]) {
 let code=stripTypeScriptTypes(fs.readFileSync(path.join(input.source,source),'utf8'),{mode:'transform'});
 if(name==='executive-launch-command-port') {
   if(!code.includes('"./operation-key"')) throw Error('unexpected dependency source');
   code=code.replace('"./operation-key"','"./operation-key.mjs"');
 }
 fs.writeFileSync(path.join(folder,name+'.mjs'),code);
}
const {decodeLaunchBindingConfig}=await import(pathToFileURL(path.join(folder,'launch-config.mjs')));
const {ExecutiveLaunchCommandPort}=await import(pathToFileURL(path.join(folder,'executive-launch-command-port.mjs')));
const config=decodeLaunchBindingConfig(JSON.stringify({v:1,...input.config}));
if(!config)throw Error('accepted manifest projection refused');
const port=new ExecutiveLaunchCommandPort(config,{callTool(){throw Error('never call an endpoint');}},
 ()=>({principalScope:input.principal_scope,generation:'offline-authenticated-context'}));
const intent=port.makeLaunchIntent({goal:input.objective,projectRef:'executive-infrastructure',profileRef:'research_only'});
if(!intent)throw Error('actual Launch producer refused fixture form');
port.prepare(intent);
process.stdout.write(JSON.stringify(intent.payload));
'''
    scratch=tmp_path/'compiled-consumer';scratch.mkdir()
    data=dict(scratch=str(scratch),source=str(ROOT/'app/mastermind_os/src'),
        config=MANIFEST_PROJECTION,principal_scope=principal_scope,objective=OBJECTIVE)
    node=os.environ.get('MM_TEST_TYPESCRIPT_NODE') or shutil.which('node')
    assert node,'Node with the supported TypeScript transform API is required'
    result=subprocess.run([node,'--input-type=module','-e',script],input=json.dumps(data),
        capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


@asynccontextmanager
async def launch_http(settings,preparer):
    app=transport_server.build_web_ceo_v3_mcp_app(settings,audit_sink=Sink(),mdm_reader=FixedMdm(),
        session_target_projector=lambda *_:[],session_reply_handler=lambda *_:{},
        session_summon_handler=lambda *_:{},os_app=_assets(),enable_os_executive_transport=True,
        os_executive_resource=OS_RESOURCE,os_commission_preparer=preparer)
    async with app._fenced_app._app.router.lifespan_context(app._fenced_app._app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
            base_url='https://mcp.mastermind-x.com') as http:
            yield http


def _register_planner_fixture(runtime,service):
    """Actual registry boundary with disposable external host DATA only."""
    router=ModelRouter.load();alias=router.resolve_model_alias(service.config.coo_model_alias)
    metadata={'adapter_id':alias.adapter_id,'model_alias':alias.model_alias,
        'routing_policy_version':router.policy_version,
        **{k:getattr(alias,k) for k in ('execution_profile_id','execution_profile_digest',
            'capability_policy_version','capability_policy_digest')}}
    runtime.workers.register_worker('offline-codex-plan',provider='codex',account_label='offline-account',
        worker_type='codex-cli',capabilities=list(alias.capabilities),quota_classes={
            service.config.coo_quota_class:{'provider':'codex','model':alias.model,'effort':alias.effort,
                'cost_class':'small','capabilities':list(alias.capabilities),'metadata':metadata}})


def test_authenticated_launch_uses_actual_host_paid_recipe_and_unchanged_reserve(
    rsa_key,tmp_path,short_socket_root,monkeypatch,
):
    mastermind=tmp_path/'mastermind';macro=tmp_path/'macro'
    commit=auth._git_repo(mastermind)
    (macro/'scripts').mkdir(parents=True);(macro/'scripts'/'agentos.py').write_text('')
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
            ceo_ingress_socket_path=short_socket_root/'paid-http.sock',ceo_ingress_peer_uid=os.geteuid()+1000,
            ceo_ingress_armed=False,ceo_ingress_grounding_provider=grounding,
            ceo_ingress_dialogue_source_provider=source_provider,
            ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,
                grounding_provider=grounding,read_provider=readers))
        await service.start()
        try:
            settings=auth._real_app_settings(rsa_key,mastermind_root=mastermind,macro_root=macro,
                ceo_ingress_socket_path=service.ceo_ingress_socket_path)
            policy_kwargs={'resource':OS_RESOURCE,'resource_metadata_url':OS_RESOURCE+'/.well-known/oauth-protected-resource'}
            settings=dataclasses.replace(settings,read_from_ceo_ingress=True,
                policies=AppPolicies(read=auth._read_policy(**policy_kwargs),submit=auth._submit_policy(**policy_kwargs)))
            token=auth._submit_token(rsa_key,aud=OS_RESOURCE)
            preparations=[]
            async def publication_observation(self,*,arguments,bearer,principal_scope):
                # Unavoidable external Studio publication observation only.
                # No Studio network/source write is made; the actual transport
                # still checks prepared state + matching original operation.
                assert bearer==token and len(principal_scope)==64
                preparations.append(dict(arguments))
                return PreparationResult('prepared',arguments['operation_key'],commit,
                    source['commission_ref']['content_sha256'])
            monkeypatch.setattr(StudioCommissionClient,'prepare',publication_observation)
            async with launch_http(settings,StudioCommissionClient(port=45025)) as http:
                context=await http.post('/os/executive/context',headers=headers(token),json={})
                assert context.status_code==200,context.text
                payload=actual_launch_payload(tmp_path,context.json()['principal_scope'])
                assert payload['attempt_limit']==1 and payload['priority']==0
                assert payload['execution_profile']=='research_only'
                assert set(payload)=={'operation_key','objective','department','priority','execution_profile','workstream','attempt_limit'}
                # Public input cannot smuggle host route/profile/review authority.
                hostile=dict(payload,paid_subject_review_binding=service._coo_execution_binding['paid_subject_review_binding'])
                refused=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':hostile})
                assert refused.status_code==400 and service.runtime.jobs.list_jobs()==[] and preparations==[]
                response=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':payload})
                assert response.status_code==200,response.text
                assert response.json()['status']=='accepted',response.text
                receipt=response.json()['receipt'];root=service.runtime.jobs.get_job(receipt['job_id'])
                assert root.orchestration_role=='aggregation' and root.parent_job_id is None
                assert root.constraints['cost_class']=='default' and root.attempt_limit==1 and root.priority==0
                assert root.constraints['paid_subject_review_binding']==service._coo_execution_binding['paid_subject_review_binding']
                assert root.constraints['execution_profile_id']=='sealed.worker.write.no-extensions.v1'
                assert root.requested_authorities==['READ','RESEARCH'] and root.allowed_write_paths==[] and root.validation_commands==[]
                paid=[m for m in root.constraints['work_placement_union'] if 'paid_execution_route' in m]
                assert len(paid)==1 and paid[0]['paid_execution_route']['model_alias']=='glm.paid.sealed-input'
                assert service.runtime.attempts.list_attempts(root.job_id)==[] and service.runtime.workers.list_workers()==[]
                replay=await http.post('/os/executive/submit',headers=headers(token),json={'arguments':payload})
                assert replay.json()['receipt']['job_id']==root.job_id and len(service.runtime.jobs.list_jobs())==1
                assert len(source_calls)==2
                assert preparations==[payload,payload]
            # Continue the HTTP-created root, not a directly minted replacement.
            runtime=service.runtime;_register_planner_fixture(runtime,service)
            planner=runtime.jobs.create_cycle_planner(root.job_id,command_id=f'coo-cycle:{root.job_id}:create-planner:0')
            planning=runtime.attempts.dispatch_cycle_job(planner.job_id,
                command_id=f'coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1',
                worker_id='offline-codex-plan',quota_class=service.config.coo_quota_class)
            assert isinstance(planning,OrchestrationDispatchOutcome)
            plan={'schema_version':'mastermind.execution_plan/v3','root_job_id':root.job_id,
                'plan_attempt_id':planning.attempt.attempt_id,'steps':[
                    {'ordinal':i,'step_id':step,'objective':objective,'business_impact':'routine',
                     'review_required':review,'requested_authorities':['READ'],'allowed_write_paths':[],
                     'validation_ids':[],'attempt_limit':1,'cost_class':'small',
                     'placement':{'provider_realm':'glm','quota_class':'offline-paid-read'},'prerequisite_step_ids':[]}
                    for i,(step,objective,review) in enumerate([
                        ('auth-launch','Analyze supplied auth/admission/launch evidence only.',True),
                        ('return-recovery','Analyze supplied return/recovery/effect evidence; label unreviewed.',False)])]}
            _complete_ohf_role(runtime,planning,plan,identity_seed=9861)
            children=runtime.jobs.admit_cycle_plan(root.job_id,
                command_id=f'coo-cycle:{root.job_id}:admit-plan:{planning.attempt.attempt_id}')
            assert len(children)==2
            assert all(c.constraints['execution_profile_id']=='fabric.paid.glm.sealed-input.v1' and
                c.constraints['cost_class']=='small' and c.attempt_limit==1 and c.requested_authorities==['READ'] for c in children)
            admission=[e for e in runtime.events.list_events(job_id=root.job_id) if e.event_type=='COO_PLAN_ADMITTED']
            assert len(admission)==1 and admission[0].payload['reserved_children_total']==11
            policy=CooCyclePolicy.load();assert policy.reserved_children_total((True,False))==11<=policy.max_children_total==16
            assert policy.max_repair_rounds==2 and policy.max_review_attempts_per_job==2
            assert len(runtime.jobs.list_jobs())==4  # root+planner+two analyses, not eleven actual children.
        finally:
            await service.close()
    asyncio.run(exercise())
