"""Signed JWT -> fixed HTTP -> App peer -> issued source -> Runtime Event."""
import asyncio
import copy
import subprocess
import httpx
import pytest
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.project_admission_permissions import instruction_admission_permissions
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_installed_project_instructions_context import bound
from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
from tests.test_workspace_read_app import rsa_key,_authenticator,_workspace_token,NOW
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_result_socket import control,short_socket_root
from tests.test_executive_workspace_mount import settings,existing


@pytest.mark.parametrize('loss',[None,'after_socket','owner_after_commit','no_grant','wrong_identity','outer_removed'])
def test_actual_signed_instruction_control_join(tmp_path,monkeypatch,rsa_key,short_socket_root,settings,loss):
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        who=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        _,bindings=grant_fixture();bindings['profiles']={'member-0':bindings['profiles']['member-0']}
        slot=bindings['profiles']['member-0'];slot['binding'].update(principal_frame(who))
        grant={'work_ref':'WS:ONE','instruction_ref':'INS:DAILY-ONE','permission_digest':'f'*64}
        slot['instruction_admission_suspend']=None if loss=='no_grant' else copy.deepcopy(grant)
        app_auth,frame_auth=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(bindings,auth.policy))
        area=tmp_path/'source';area.mkdir();collector,seen=bound(area,monkeypatch)
        reader=collector.project_instructions_reader(macro_root=seen['macro'])
        owners,clock,cache=cache_fixture(tmp_path);doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':seen['sha']}
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
        def provider(runtime):return WorkspaceReadService(cache=cache,runtime=runtime,authorize=frame_auth,armed={},runtime_identity={},project_instructions_reader=reader,
            instruction_admission_permissions=instruction_admission_permissions(policy=auth.policy,load_bindings=lambda:bindings))
        svc=control(tmp_path/'runtime',short_socket_root,provider);await svc.start();runtime=svc._require_runtime()
        if loss=='owner_after_commit':
            original=runtime.jobs.pause_instruction_admission
            def lost(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('private owner detail')
            monkeypatch.setattr(runtime.jobs,'pause_instruction_admission',lost)
        peer=CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path);frames=[]
        class Client:
            async def request(self,frame):
                frames.append(copy.deepcopy(frame));value=await peer.request(frame)
                if loss=='after_socket' and frame['operation']=='pause_instruction_admission':slot['instruction_admission_suspend']=None
                if loss=='wrong_identity' and frame['operation']=='instruction_admission_control':value['result']['owner_context']={'principal_scope':'f'*64}
                return value
        app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=app_auth,
            project_admission_load_bindings=lambda:bindings,client=Client()))
        if loss=='outer_removed':
            from integrations.executive_mcp import server
            app=server.build_executive_mcp_app(settings,audit_sink=existing.Sink(),workspace_app=app)
        selected={'work_ref':'WS:ONE','instruction_ref':'INS:DAILY-ONE'};command='mmos-instruction-pause-'+'1'*40
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
                for params in [{**selected,'actor':'forged'},{**selected,'instruction_ref':'INS:../foreign'}]:
                    assert (await client.get('/workspace/instruction-admission/current',params=params)).status_code==400
                head=await client.head('/workspace/instruction-admission/current',params=selected);assert head.status_code in (400,404) and frames==[]
                current=await client.get('/workspace/instruction-admission/current',params=selected)
                if loss=='no_grant':
                    assert current.status_code==403 and frames==[] and runtime.jobs.list_jobs()==[];return
                if loss=='wrong_identity':
                    assert current.json()['availability']=='UNAVAILABLE' and current.json()['owner_context'] is None,current.text
                    assert not any(frame['operation']=='pause_instruction_admission' for frame in frames) and runtime.jobs.list_jobs()==[];return
                assert current.status_code==200 and current.json()['state']=='NOT_SUSPENDED',current.text
                content=current.json()
                result=await client.post('/workspace/instruction-admission/pause',json={'selection':selected,'command_id':command,'expected_revision':content['instruction_revision'],'expected_source':content['source']})
                assert result.headers['cache-control']=='no-store'
                assert result.json()['disposition']==('COMMITTED' if loss in (None,'outer_removed') else 'EFFECT_UNKNOWN'),result.text
                assert 'private' not in result.text
                slot['instruction_admission_suspend']=copy.deepcopy(grant)
                status=await client.get('/workspace/instruction-admission/operation',params={**selected,'command_id':command})
                assert status.json()['state']=='OBSERVED',status.text
                gate=await client.get('/workspace/instruction-admission/current',params=selected)
                assert gate.json()['state']=='PAUSED' and gate.json()['current_receipt']==status.json()['receipt'],gate.text
                if loss=='outer_removed':
                    path=seen['record'];path.write_text(path.read_text().replace("standing_instructions:\n  - instruction_ref: INS:DAILY-ONE\n    text: 'Review the project carefully.'\n",'standing_instructions: []\n'))
                    subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True);subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','ordinary project reopen after instruction removal'],check=True,capture_output=True)
                    doc['sources']['macro_sha']=subprocess.check_output(['git','-C',str(seen['macro']),'rev-parse','HEAD'],text=True).strip()
                    with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
                    project_only=await client.get('/workspace/project-instructions/current',params={'work_ref':'WS:ONE'})
                    content=project_only.json();assert project_only.status_code==200 and content['instructions']==[],project_only.text
                    assert content['recovery_identity']==gate.json()['owner_context']
                    removed=await client.get('/workspace/instruction-admission/current',params=selected)
                    assert removed.json()['availability']=='UNAVAILABLE' and removed.json()['permission'] is None and removed.json()['owner_context']==content['recovery_identity'],removed.text
                    observed=await client.get('/workspace/instruction-admission/operation',params={**selected,'command_id':command})
                    assert observed.json()==status.json(),observed.text
                assert runtime.jobs.list_jobs()==[]
                assert len([frame for frame in frames if frame['operation']=='pause_instruction_admission'])==1
                with runtime.store.read() as connection:assert connection.execute("SELECT count(*) FROM events WHERE event_type='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED'").fetchone()[0]==1
        finally:await svc.close()
    asyncio.run(run())
