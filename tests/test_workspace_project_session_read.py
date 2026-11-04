"""Actual temp Runtime/Git/issued collector → signed HTTP/socket association READ.

The managed broker status transport is an explicit READ fixture, not a provider
or installed service. No continuation target, write or fabricated chat is tested.
"""
import asyncio
import json
from pathlib import Path
import httpx
import pytest

from common import workspace_project_session_contract as wire
from control_plane import agentos_project_creation_source as creation
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.executive_mcp.installed import _default_packet_runner
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, principal_frame, workspace_authorizers
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from tests.test_workspace_managed_project_session_source import owner, source, git
from tests.test_installed_product_acceptance_context import fixture
from tests.test_workspace_read_service import cache_fixture
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_workspace_result_socket import control, short_socket_root

ORIGINAL_READ = creation.AgentOsProjectCreationReader.read


@pytest.mark.parametrize('case',['available','after_source_revoke','after_socket_revoke','stale_catalogue_source','foreign_root'])
def test_real_source_and_current_broker_receipt_cross_actual_fixed_read(tmp_path,monkeypatch,owner,rsa_key,short_socket_root,case):
    async def run():
        managed, original_service, selected, broker, _native = owner
        macro=managed._source_reader._macro_root
        monkeypatch.setattr(creation.AgentOsProjectCreationReader,'read',ORIGINAL_READ)
        area=tmp_path/'issued-source';area.mkdir()
        collector,_,seen=fixture(area)
        collector._macro_root=macro.resolve()
        monkeypatch.setattr(creation,'_SOURCE_ROOT',seen['code'])
        auth=_authenticator(rsa_key);token=_workspace_token(rsa_key)
        who=await auth.verify_authorization_header('Bearer '+token,now=NOW)
        bindings={'schema':BINDINGS_SCHEMA,'profiles':{'web':{'enabled':True,'binding':dict(principal_frame(who),permission_digest='a'*64)},'mac':{'enabled':False,'binding':None}}}
        app_gate,frame_gate=workspace_authorizers(policy=auth.policy,load_bindings=lambda:bindings)
        def revoke():bindings['profiles']['web']['enabled']=False
        calls=[]
        def runner(argv,**limits):
            if argv[0]=='git':return _default_packet_runner(argv,**limits)
            calls.append(argv)
            assert limits['max_bytes']==4096
            child=Path(argv[argv.index('--macro-root')+1])
            assert child != macro
            value=creation.read_from_macro_owner(macro_root=child,
                expected_macro_sha=argv[argv.index('--expected-macro-sha')+1],
                record_commit=argv[argv.index('--record-commit')+1],work_ref=argv[argv.index('--work-ref')+1],timeout=float(argv[-1]))
            if case=='after_source_revoke':revoke()
            observation={'schema':'mastermind.agentos_project_creation_source.v1','work_ref':selected['work_ref'],'availability':'AVAILABLE','source':value,'reason':None}
            return dict(code=0,stdout=json.dumps(observation),timed_out=False,limit_exceeded=False,invalid_utf8=False)
        collector._runner=runner
        managed._source_reader=collector.project_creation_source_reader(macro_root=macro)
        owners,clock,cache=cache_fixture(tmp_path)
        doc=owners[0].state_cache['doc'];doc['work'][0]['work_ref']=selected['work_ref']
        row=doc['autonomy']['responsibilities'][0]
        row.update(responsibility_ref=selected['work_ref'],root_job_id=selected['root_job_id'],root_job_candidates=[selected['root_job_id']])
        doc['sources']={'macro_sha':'f'*40 if case=='stale_catalogue_source' else git(macro,'rev-parse','HEAD')}
        from scripts import chairman_control_room as ccr
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
        provider=WorkspaceReadService(cache=cache,runtime=original_service.runtime,authorize=frame_gate,armed={},runtime_identity={},project_session_source=managed)
        socket_service=control(tmp_path/'socket-service',short_socket_root,lambda _:provider)
        await socket_service.start()
        peer=CeoIngressWorkspaceClient(socket_service.ceo_ingress_socket_path)
        class Client:
            async def request(self,frame):
                value=await peer.request(frame)
                if case=='after_socket_revoke':revoke()
                return value
        app=create_workspace_app(WorkspaceAppConfig(authenticator=auth,now=lambda:NOW,authorize_principal=app_gate,client=Client()))
        query=dict(selected)
        if case=='foreign_root':query['root_job_id']='JOB-999999'
        before=original_service.runtime.events.list_events()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://mcp.mastermind-x.com') as client:
                result=await client.get('/workspace/project-session/current',params=query,headers={'Authorization':'Bearer '+token})
            if 'revoke' in case:
                assert result.status_code==403,result.text
                assert 'provider_session_sha256' not in result.text
            elif case=='foreign_root':
                assert result.status_code==404,result.text
                assert calls==[] and broker.calls==[]
            elif case=='stale_catalogue_source':
                assert result.status_code==503,result.text
                assert result.json()['state']=='UNAVAILABLE' and broker.calls==[]
            else:
                assert result.status_code==200,result.text
                body=wire.validate_body(result.json())
                assert body['state']=='MATERIALIZED_OBSERVATION' and body['can_send'] is False and body['continuation_target'] is None
                assert calls and broker.calls
                assert result.headers['cache-control']=='no-store'
            assert original_service.runtime.events.list_events()==before
        finally:await socket_service.close()
    asyncio.run(run())


def test_session_permission_refusal_keeps_plain_integer_http_status_before_source_read():
    from tests.test_workspace_member_bindings import fixture as bindings_fixture, principal
    from integrations.mastermind_workspace_app.app import _envelope_response
    _, bindings = bindings_fixture()
    frame = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
             "principal": principal(bindings),
             "selection": {"work_ref": "WS:SYNTHETIC-PROJECT", "root_job_id": "JOB-001"}}
    provider = object.__new__(WorkspaceReadService)
    provider.authorize = lambda _: False
    # This refusal occurs before any cache/source/Runtime owner is accessed.
    result = asyncio.run(provider._handle_project_session_frame(frame))
    assert type(result["status"]) is int and result["status"] == 403
    assert _envelope_response(result).status_code == 403
