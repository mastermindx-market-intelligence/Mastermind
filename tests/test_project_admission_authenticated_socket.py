"""Signed JWT -> fixed HTTP -> incumbent App-peer Unix -> real Runtime owner.

Temporary isolated service/source fixtures only; no installed host/grant effect.
"""
import asyncio
import copy
import json
import time
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
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_result_socket import control, short_socket_root

WORK = 'WS:PLAN-TEST'
PAUSE = 'mmos-project-pause-' + 'a'*40
RESUME = 'mmos-project-resume-' + 'b'*40

@pytest.mark.parametrize('rootless,loss', [(False,None),(True,None),(False,'after_socket'),(False,'owner_after_commit')])
def test_fixed_admission_actual_authenticated_socket_join(tmp_path,monkeypatch,repository,rsa_key,short_socket_root,rootless,loss):
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
        calls=[]
        def runner(argv,**limits):
            calls.append(argv)
            if argv[0]=='git':return _default_packet_runner(argv,**limits)
            child=Path(argv[argv.index('--macro-root')+1])
            body=plan.read_from_macro_owner(macro_root=child,expected_macro_sha=argv[argv.index('--expected-macro-sha')+1],
                work_ref=argv[argv.index('--work-ref')+1],include_continuity=True,timeout=float(argv[-1]))
            return dict(code=0,stdout=json.dumps(body),timed_out=False,limit_exceeded=False,invalid_utf8=False)
        collector._runner=runner;reader=collector.project_plan_reader(macro_root=repo['root'])
        owners,clock,cache=cache_fixture(tmp_path);doc=owners[0].state_cache['doc'];doc['work'][0]['work_ref']=WORK
        row=doc['autonomy']['responsibilities'][0];row['responsibility_ref']=WORK;doc['sources']={'macro_sha':repo['head']}
        if rootless:row.update(root_job_id=None,root_job_candidates=[],root_job_ambiguous=False,runtime_root_state='UNKNOWN')
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
        def provider(runtime):
            return WorkspaceReadService(cache=cache,runtime=runtime,authorize=frame_auth,armed={},runtime_identity={},
                project_plan_reader=reader,project_admission_permissions=project_admission_permissions(policy=auth.policy,load_bindings=lambda:bindings))
        svc=control(tmp_path/'service',short_socket_root,provider);await svc.start()
        runtime=svc._require_runtime();selected={'work_ref':WORK}
        if not rootless:
            root=runtime.jobs.create_job('Actual isolated root',provenance={'workstream':WORK},command_id='fixture-root')
            assert root.job_id=='JOB-001';selected['root_job_id']=root.job_id
        assert not svc._ceo_ingress_armed and not svc._ceo_ingress_app_binding.armed
        if loss=='owner_after_commit':
            original=runtime.jobs.pause_workstream_admission
            def lost(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('private provider detail')
            monkeypatch.setattr(runtime.jobs,'pause_workstream_admission',lost)
        peer=CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path);seen_frames=[]
        class Client:
            async def request(self,frame):
                seen_frames.append(copy.deepcopy(frame));value=await peer.request(frame)
                if loss=='after_socket' and frame['operation']==pause.OPERATION:slot['project_admission_suspend']=None
                return value
        app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=app_auth,
            project_admission_load_bindings=lambda:bindings,client=Client()))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
                calls.clear();read_started=time.monotonic()
                current=await client.get('/workspace/project-admission/current',params=selected)
                current_elapsed=time.monotonic()-read_started
                captures=[argv for argv in calls if argv[0]!='git']
                assert len(captures)==(2 if rootless else 0),len(captures)
                assert current_elapsed<peer.timeout_seconds
                print(json.dumps({'rootless':rootless,'current_read_captures':len(captures),'elapsed_seconds':round(current_elapsed,3),'stricter_checked_bound':peer.timeout_seconds,'existing_read_timeout':peer.acceptance_timeout_seconds}))
                assert current.status_code==200,current.text
                assert current.json()['availability']=='AVAILABLE',current.text
                result=await client.post('/workspace/project-admission/pause',json={'selection':selected,'command_id':PAUSE})
                body=result.json();assert result.headers['cache-control']=='no-store'
                assert body['disposition']==('EFFECT_UNKNOWN' if loss else 'COMMITTED'),result.text
                if loss:
                    assert body['receipt'] is None and 'private' not in result.text
                    slot['project_admission_suspend']={'work_ref':WORK,'permission_digest':'6'*64}
                original=await client.get('/workspace/project-admission/operation',params={**selected,'kind':'project_pause','command_id':PAUSE})
                assert original.json()['state']=='OBSERVED',original.text
                gate=await client.get('/workspace/project-admission/current',params=selected)
                assert gate.json()['state']=='PAUSED',gate.text
                resumed=await client.post('/workspace/project-admission/resume',json={'selection':selected,'command_id':RESUME,'pause_token':gate.json()['pause_token']})
                assert resumed.json()['disposition']=='COMMITTED',resumed.text
                after=await client.get('/workspace/project-admission/current',params=selected)
                assert after.json()['state']=='RESUMED',after.text
                if rootless:assert runtime.jobs.list_jobs()==[] and calls
                assert len([frame for frame in seen_frames if frame['operation']==pause.OPERATION])==1
        finally:await svc.close()
    asyncio.run(run())
