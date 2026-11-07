"""Signed JWT -> fixed HTTP -> incumbent App-peer Unix -> real Runtime owner.

Temporary isolated service/source fixtures only; no installed host/grant effect.
"""
import asyncio
import copy
import json
import subprocess
from integrations.mastermind_workspace_app.project_admission_permissions import project_admission_permissions
from pathlib import Path
import httpx
import pytest

from common import workspace_project_admission_contract as pause
from control_plane import agentos_project_plan as plan
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.executive_mcp.installed import _default_packet_runner
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_agentos_plan_continuity_capture import repository
from tests.test_installed_product_acceptance_context import fixture
from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_workspace_result_socket import control, short_socket_root

WORK = 'WS:PLAN-TEST'
PAUSE = 'mmos-project-pause-' + 'a'*40
RESUME = 'mmos-project-resume-' + 'b'*40

def test_canonical_project_signed_pause_status_resume_cycle(tmp_path,monkeypatch,repository,rsa_key,short_socket_root):
    from tests.fresh_conversation_full_cache import CanonicalFixtureCache
    from control_plane import executive_runtime as runtime_owner
    from tests.test_workstream_admission_runtime import mutable_rows
    import os
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        who=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        _,bindings=grant_fixture();bindings['profiles']={'member-0':bindings['profiles']['member-0']}
        slot=bindings['profiles']['member-0'];slot['binding'].update(principal_frame(who))
        slot['project_admission_suspend']={'work_ref':WORK,'permission_digest':'6'*64}
        slot['project_admission_resume']={'work_ref':WORK,'permission_digest':'4'*64}
        app_auth,frame_auth=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(bindings,auth.policy))
        repo=repository;area=tmp_path/'source';area.mkdir();collector,_,seen=fixture(area)
        collector._macro_root=repo['root'].resolve();monkeypatch.setattr(plan,'_SOURCE_ROOT',seen['code'])
        def runner(argv,**limits):
            if argv[0]=='git':return _default_packet_runner(argv,**limits)
            child=Path(argv[argv.index('--macro-root')+1])
            body=plan.read_from_macro_owner(macro_root=child,expected_macro_sha=argv[argv.index('--expected-macro-sha')+1],
                work_ref=argv[argv.index('--work-ref')+1],include_continuity=True,timeout=float(argv[-1]))
            return dict(code=0,stdout=json.dumps(body),timed_out=False,limit_exceeded=False,invalid_utf8=False)
        collector._runner=runner;reader=collector.project_plan_reader(macro_root=repo['root'])
        canonical=CanonicalFixtureCache(repo['root'],tmp_path/'full-canonical',mastermind_revision=subprocess.check_output(['git','-C',str(seen['repo']),'rev-parse','HEAD'],text=True).strip())
        def provider(runtime):
            return WorkspaceReadService(cache=canonical.cache,runtime=runtime,authorize=frame_auth,armed={},runtime_identity={},
                project_plan_reader=reader,project_admission_permissions=project_admission_permissions(policy=auth.policy,load_bindings=lambda:bindings))
        svc=control(tmp_path/'service',short_socket_root,provider);await svc.start()
        runtime=svc._require_runtime();selected={'work_ref':WORK}
        runtime.workers.register_worker('worker-01',provider='codex',account_label='inert',worker_type='test')
        original_job=runtime.jobs.create_job('Already claimed fixture work',provenance={'workstream':WORK},command_id='claimed-before-pause')
        lease=runtime.attempts.claim_job(original_job.job_id);assert lease is not None
        before=mutable_rows(runtime)
        peer=CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path);seen_frames=[]
        class Client:
            async def request(self,frame):
                seen_frames.append(copy.deepcopy(frame));return await peer.request(frame)
        app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=app_auth,
            project_admission_load_bindings=lambda:bindings,client=Client()))
        outputs={}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
                programs=await client.get('/workspace/programs/current');assert programs.status_code==200,programs.text
                outputs['programs']=programs.json()
                assert any(row['work_ref']==WORK for row in outputs['programs']['control_room']['work'])
                async def get_current(name):
                    r=await client.get('/workspace/project-admission/current',params=selected)
                    assert r.status_code==200 and r.json()['availability']=='AVAILABLE',r.text
                    outputs[name]=r.json();return r.json()
                await get_current('open')
                pause_response=await client.post('/workspace/project-admission/pause',json={'selection':selected,'command_id':PAUSE})
                outputs['pause_result']=pause_response.json();assert outputs['pause_result']['disposition']=='COMMITTED',pause_response.text
                assert mutable_rows(runtime)==before
                # A known committed pause blocks NEW work; it does not rewrite
                # the already claimed lease. No provider/start/cancel is invoked.
                with pytest.raises(runtime_owner.StateConflict,match='WORKSTREAM_ADMISSION_SUSPENDED'):
                    runtime.jobs.create_job('Must not be admitted',provenance={'workstream':WORK},command_id='new-during-pause')
                assert mutable_rows(runtime)==before
                events_before=runtime.events.list_events()
                status=await client.get('/workspace/project-admission/operation',params={**selected,'kind':'project_pause','command_id':PAUSE})
                outputs['pause_status']=status.json();assert outputs['pause_status']['state']=='OBSERVED',status.text
                assert runtime.events.list_events()==events_before
                gate=await get_current('paused')
                resume_grant=slot['project_admission_resume'];slot['project_admission_resume']=None
                await get_current('paused_resume_denied')
                slot['project_admission_resume']=resume_grant
                r=await client.post('/workspace/project-admission/resume',json={'selection':selected,'command_id':RESUME,'pause_token':gate['pause_token']})
                outputs['resume_result']=r.json();assert outputs['resume_result']['disposition']=='COMMITTED',r.text
                receipt=outputs['resume_result']['receipt'];assert receipt['pause_event_id']==gate['pause_token']['event_id']
                assert receipt['pause_receipt_digest']==gate['pause_token']['receipt_digest']
                status=await client.get('/workspace/project-admission/operation',params={**selected,'kind':'project_resume','command_id':RESUME})
                outputs['resume_status']=status.json();assert outputs['resume_status']['state']=='OBSERVED',status.text
                await get_current('resumed');assert outputs['resumed']['state']=='RESUMED'
                assert mutable_rows(runtime)==before
                assert len([f for f in seen_frames if f['operation']==pause.OPERATION])==1
                outputs.update(selection=selected,source=canonical.provenance(),
                    retained_claim={'job_id':original_job.job_id,'attempt_id':lease.attempt.attempt_id,'mutable_rows_unchanged':True},
                    native_auth={'synthetic':True,'no_Executive_to_Workspace_scope_mapping':True})
                destination=os.environ.get('MMOS_ADMISSION_CYCLE_FIXTURE')
                if destination:Path(destination).write_text(json.dumps(outputs,sort_keys=True,ensure_ascii=False))
        finally:await svc.close()
    asyncio.run(run())
