"""Actual outer -> signed HTTP -> Unix -> canonical source READ, no mutation."""
import asyncio
import httpx
import pytest
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_installed_project_instructions_context import bound
from tests.test_workspace_project_access import configured
from tests.test_workspace_read_app import rsa_key,_authenticator,_workspace_token,NOW
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_result_socket import control,short_socket_root
from tests.test_executive_workspace_mount import settings,existing


@pytest.mark.parametrize('loss',[None,'source','revoke','wrong_identity','v5'])
def test_real_outer_current_project_access(tmp_path,monkeypatch,rsa_key,short_socket_root,settings,loss):
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        principal=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        bindings,slot,authorize=configured(auth,principal)
        if loss=='v5':
            from integrations.mastermind_workspace_app import project_authoring_grant as grants
            bindings['schema']=grants.SCHEMA_V5
            slot.update(project_canonical_data_read='d'*64,project_plan_proposal_publish={'work_ref':'WS:ONE','permission_digest':'e'*64})
        _,frame_authorize=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(bindings,auth.policy))
        area=tmp_path/'source';area.mkdir()
        def change(value,child,seen):
            if loss=='source':
                raw=seen['record'].read_bytes();seen['record'].write_bytes(b'changed');seen['record'].write_bytes(raw)
        collector,seen=bound(area,monkeypatch,mutation=change)
        reader=collector.project_instructions_reader(macro_root=seen['macro'])
        owners,clock,cache=cache_fixture(tmp_path);doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':seen['sha']}
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
        def provider(runtime):return WorkspaceReadService(cache=cache,runtime=runtime,authorize=frame_authorize,armed={},runtime_identity={},project_instructions_reader=reader)
        svc=control(tmp_path/'runtime',short_socket_root,provider);await svc.start()
        peer=CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path);frames=[]
        class Client:
            async def request(self,frame):
                frames.append(frame);result=await peer.request(frame)
                if loss=='revoke':slot['enabled']=False
                if loss=='wrong_identity':result['result']['selection']={'work_ref':'WS:OTHER'}
                return result
        loader=lambda:bindings
        inner=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=authorize,client=Client(),project_admission_load_bindings=loader))
        from integrations.executive_mcp import server
        app=server.build_executive_mcp_app(settings,audit_sink=existing.Sink(),workspace_app=inner)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com',headers={'Authorization':'Bearer '+token}) as client:
                for path in ['/workspace/project-access/current/','/workspace/project-access/%63urrent']:
                    assert (await client.get(path,params={'work_ref':'WS:ONE'})).status_code in (400,404) and not frames
                assert (await client.head('/workspace/project-access/current',params={'work_ref':'WS:ONE'})).status_code in (400,404) and not frames
                assert (await client.post('/workspace/project-access/current',json={'work_ref':'WS:ONE'})).status_code in (400,404) and not frames
                result=await client.get('/workspace/project-access/current',params={'work_ref':'WS:ONE'})
                assert result.headers['cache-control']=='no-store' and len(frames)==1 and frames[0]['operation']=='project_instructions'
                if loss=='revoke':assert result.status_code==403
                elif loss in {'source','wrong_identity'}:assert result.status_code==503 and result.json()['grants'] is None
                else:
                    assert result.status_code==200,result.text
                    body=result.json();assert body['source']['commit']==seen['sha'] and body['membership']=={'workspace_read':'QUALIFIED'}
                    grant=next(row for row in body['grants'] if row['action']=='pause_instruction_admission')
                    assert grant['instruction_ref']=='INS:DAILY-ONE' and grant['supply']=='SUPPLIED'
                    if loss=='v5':
                        assert body['schema']=='mastermind.workspace_project_access.v2' and len(body['grants'])==10
                        data=next(row for row in body['grants'] if row['action']=='read_latest_project_data')
                        assert data=={'action':'read_latest_project_data','scope':'WORKSPACE','work_ref':None,'instruction_ref':None,'supply':'SUPPLIED'}
                    assert 'permission_digest' not in result.text
                assert svc._require_runtime().jobs.list_jobs()==[]
                with svc._require_runtime().store.read() as connection:
                    assert connection.execute('SELECT count(*) FROM events').fetchone()[0]==0
        finally:await svc.close()
    asyncio.run(run())
