"""Real signed JWT -> fixed HTTP -> App-peer Unix -> issued canonical reader."""
import asyncio
import json
import httpx
import pytest
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig,create_workspace_app
from integrations.mastermind_workspace_app.contract import principal_frame,workspace_authorizers
from integrations.mastermind_workspace_app.project_authoring_grant import legacy_workspace_document
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_installed_project_instructions_context import bound
from tests.test_workspace_project_suspend_grant import fixture as grant_fixture
from tests.test_workspace_read_app import rsa_key,_authenticator,_workspace_token,NOW
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_result_socket import control,short_socket_root


@pytest.mark.parametrize('loss',[None,'permission','source','expired','wrong_identity'])
def test_actual_content_read_uses_existing_auth_and_sealed_source_without_runtime_effect(tmp_path,monkeypatch,rsa_key,short_socket_root,loss):
    async def run():
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        principal=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        _,bindings=grant_fixture();bindings['profiles']={'member-0':bindings['profiles']['member-0']}
        slot=bindings['profiles']['member-0'];slot['binding'].update(principal_frame(principal))
        app_auth,frame_auth=workspace_authorizers(policy=auth.policy,load_bindings=lambda:legacy_workspace_document(bindings,auth.policy))
        area=tmp_path/'source';area.mkdir()
        def change(value,child,seen):
            if loss=='source':
                raw=seen['record'].read_bytes();seen['record'].write_bytes(b'changed');seen['record'].write_bytes(raw)
        collector,seen=bound(area,monkeypatch,mutation=change)
        reader=collector.project_instructions_reader(macro_root=seen['macro'])
        owners,clock,cache=cache_fixture(tmp_path);doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':seen['sha']}
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
        def provider(runtime):return WorkspaceReadService(cache=cache,runtime=runtime,authorize=frame_auth,armed={},runtime_identity={},project_instructions_reader=reader)
        svc=control(tmp_path/'runtime',short_socket_root,provider);await svc.start()
        peer=CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path);frames=[];instant=[NOW]
        class Client:
            async def request(self,frame):
                frames.append(frame);value=await peer.request(frame)
                if loss=='permission':slot['enabled']=False
                if loss=='expired':instant[0]=principal.expires_at
                if loss=='wrong_identity':value['result']['recovery_identity']={'principal_scope':'f'*64}
                return value
        app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:instant[0],authorize_principal=app_auth,client=Client()))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
                denied=await client.get('/workspace/project-instructions/current',params={'work_ref':'WS:ONE'});assert denied.status_code==401 and frames==[]
                response=await client.get('/workspace/project-instructions/current',params={'work_ref':'WS:ONE'},headers={'Authorization':'Bearer '+token})
                if loss in {'permission','expired'}:assert response.status_code==403 and 'Review the project' not in response.text and 'recovery_identity' not in response.text
                elif loss=='source':assert response.status_code==503 and response.json()['instructions'] is None
                elif loss=='wrong_identity':assert response.status_code==503 and 'recovery_identity' not in response.text
                else:
                    assert response.status_code==200,response.text
                    body=response.json();assert body['instructions'][0]['text']=='Review the project carefully.'
                    assert body['source']['commit']==seen['sha'] and body['declaration']=='SUPPLIED'
                    assert not {'state','permissions','owner_context'}&set(body)
                    from integrations.mastermind_workspace_app.owner_context import workspace_owner_context
                    assert body['schema']=='mastermind.workspace_project_instructions.v2' and body['recovery_identity']==workspace_owner_context(principal)
                assert response.headers['cache-control']=='no-store'
                assert len(frames)==1 and frames[0]['operation']=='project_instructions'
                assert svc._require_runtime().jobs.list_jobs()==[]
                rejected=await client.get('/workspace/project-instructions/current',params={'work_ref':'WS:ONE','source_commit':'a'*40},headers={'Authorization':'Bearer '+token})
                assert rejected.status_code in (400,401,403) and len(frames)==1
        finally:await svc.close()
    asyncio.run(run())
