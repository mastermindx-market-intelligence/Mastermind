"""Source integration only: actual Runtime/adapter/broker and Unix App reader."""
from collections import OrderedDict
import asyncio
import json
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import pytest
from test_executive_operator_supervisor import _seed_expired_g1
from test_executive_content_observer import profile
from control_plane.executive_content_observer import ExecutiveContentObserver, ContentRefused
from control_plane.executive_worker_broker import ExecutiveWorkerBroker, WorkerBrokerClient, PeerCredentials
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.visible_turn_projection import TurnKey
from integrations.executive_content_contract import ACCESS_SCHEMA, PAGE_SCHEMA, canonical
from integrations.mastermind_steward_app.installed import InstalledWindowSource, CeoIngressContentClient


def fixture(tmp_path):
    clock,runtime,root,planner,dispatch,execution_profile,epoch = _seed_expired_g1(tmp_path,observed_dead=False)
    generation=runtime.operator_harness.current_writer_generation(epoch)
    from control_plane.operator_harness_contract import ReconcileObservation, ProcessLiveness, ProcessIdentityObservation, ProviderWriterState
    runtime.operator_harness.record_reconcile_observation(generation=generation,
        observation=ReconcileObservation(ProcessLiveness.ALIVE,ProcessIdentityObservation(2101,2101,'start-2101','boot-test'),True,ProviderWriterState.HELD,'SESSION-G1','d'*64),
        fence_generation=dispatch.attempt.fence_generation,lease_token=dispatch.lease_token)
    with runtime.store.read() as conn:
        row=conn.execute("SELECT payload_json FROM events WHERE event_type='OPERATOR_OPERATION_APPLIED' AND json_extract(payload_json,'$.operation_kind')='begin_turn'").fetchone()
    turn=json.loads(row['payload_json'])
    from integrations.business_mcp_auth.contracts import subject_digest
    issuer='https://content-issuer.example.test'
    p=profile(policy_id='mastermind-workspace-window-fixture',content_resource='https://mcp.example.test/workspace/window/current',
        issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),
        subject_digest=subject_digest(issuer=issuer,subject='fixture-authorized-viewer'),
        client_ref=hashlib.sha256((issuer+'\nclient\nfixture-content-client').encode()).hexdigest(),job_id=planner.job_id,attempt_id=dispatch.attempt.attempt_id,session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,local_turn_id=turn['turn_id'],expires_at='2031-01-01T00:00:00Z')
    adapter=CodexOperatorAdapter.__new__(CodexOperatorAdapter)
    adapter._generations={generation.process_generation_id:SimpleNamespace(epoch=epoch,generation=generation,turns={turn['turn_id']:'NATIVE-G1'})}
    broker=ExecutiveWorkerBroker.__new__(ExecutiveWorkerBroker)
    broker._state_lock=asyncio.Lock()
    broker._operator_terminal=OrderedDict()
    broker._observer_refusals=[]
    broker._operator_run=SimpleNamespace(epoch=epoch,generation=generation,adapter=adapter)
    return clock,runtime,p,adapter,broker


def test_actual_runtime_broker_unix_reader_and_midread_revocation(tmp_path):
    clock,runtime,p,adapter,broker=fixture(tmp_path)
    async def run():
        # Real clients exercise framing. The test server invokes the production
        # broker dispatch; deployment's unchanged control-UID guard is tested
        # separately by the existing broker suite.
        with tempfile.TemporaryDirectory(prefix='mmcontent-',dir='/tmp') as directory:
            broker_path=Path(directory)/'broker.sock'
            ingress_path=Path(directory)/'ingress.sock'
            installed_profile=[p]
            change_permission_during_page=False
            async def serve_broker(reader,writer):
                frame=json.loads(await reader.readline())
                try:
                    result=await broker._dispatch(frame['operation'],frame['payload'])
                    if change_permission_during_page and frame['operation']=='ohf-observe-turn':
                        installed_profile[0]=None
                    reply=dict(schema_version='mastermind.executive_worker_broker_response/v1',request_id=frame['request_id'],operation=frame['operation'],ok=True,result=result)
                except Exception:
                    reply=dict(schema_version='mastermind.executive_worker_broker_response/v1',request_id=frame['request_id'],operation=frame['operation'],ok=False,error={'code':'state_conflict','message':'refused'})
                writer.write(canonical(reply)+b'\n');await writer.drain();writer.close();await writer.wait_closed()
            server=await asyncio.start_unix_server(serve_broker,path=str(broker_path))
            owner=ExecutiveContentObserver(runtime=runtime,broker_client=WorkerBrokerClient(broker_path),profile_loader=lambda:installed_profile[0],now=lambda:clock.value//1000)
            async with server:
                access=await owner.handle_frame(p.frame(ACCESS_SCHEMA))
                assert access['ok'] is False # Read cannot enroll.
                enrollment=await owner.enroll()
                assert enrollment['status']=='ACTIVE'
                assert await owner.enroll()==enrollment
                key=TurnKey(**enrollment['turn_key'])
                for n in range(4):
                    adapter.visible_turn_projection.publish(key,method='item/updated',params={'item':{'type':'agentMessage','id':str(n),'sequence':n,'text':'x'*12000}},native_turn_id='NATIVE-G1')
                revoke_on_page=False
                async def serve_ingress(reader,writer):
                    frame=json.loads(await reader.readline())
                    reply=await owner.handle_frame(frame)
                    if revoke_on_page and frame['schema']==PAGE_SCHEMA:
                        await owner.revoke()
                    writer.write(canonical(reply)+b'\n');await writer.drain();writer.close();await writer.wait_closed()
                ingress=await asyncio.start_unix_server(serve_ingress,path=str(ingress_path))
                async with ingress:
                    source=InstalledWindowSource(profile=p,client=CeoIngressContentClient(ingress_path),now=lambda:clock.value//1000)
                    window=json.loads(await source.read_source())
                    assert [len(i['text']) for i in window['items']]==[12000]*4
                    assert window['terminal'] is False
                    assert 'NATIVE-G1' not in json.dumps(window)
                    assert 'reader_grant' not in json.dumps(window)
                    from test_mastermind_steward_app_live_window import (_key, _cache, _content_policy, _steward_policy, _steward_verifier, _Sink, _content_token, _invoke, _headers, WINDOW_PATH, ORIGIN)
                    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
                    from integrations.mastermind_steward_app.installed import build_installed_steward_app
                    key_material=_key();content_policy=_content_policy();steward_policy=_steward_policy()
                    app=build_installed_steward_app(profile=p,steward_policy=steward_policy,
                        steward_token_verifier=_steward_verifier(steward_policy,key_material),
                        content_authenticator=JwtAuthenticator(policy=content_policy,jwks_cache=_cache(content_policy,key_material)),
                        content_policy=content_policy,audit_sink=_Sink(),ceo_ingress_socket_path=ingress_path,
                        now=lambda:clock.value//1000,allowed_origin=ORIGIN)
                    token=_content_token(key_material,issued_at=clock.value//1000-5,expires_at=clock.value//1000+600)
                    status,headers,raw,_=await _invoke(app,path=WINDOW_PATH,headers=_headers(token=token))
                    assert status==200
                    assert len(json.loads(raw)['view']['items'])==4
                    assert token.encode() not in raw
                    change_permission_during_page=True
                    with pytest.raises(ValueError):
                        await source.read_source()
                    installed_profile[0]=p
                    change_permission_during_page=False
                    revoke_on_page=True
                    with pytest.raises(ValueError):
                        await source.read_source()
                    status,headers,raw,_=await _invoke(app,path=WINDOW_PATH,headers=_headers(token=token))
                    assert status==401 and b'xxxxxxxx' not in raw
                    assert (await owner.status())['status']=='REVOKED'
                    assert (await owner.enroll())['status']=='REVOKED'
                    from control_plane.visible_turn_projection import VisibleTurnProjection
                    adapter.visible_turn_projection=VisibleTurnProjection()
                    assert (await owner.status())['status']=='ABSENT'
                    with pytest.raises(ContentRefused,match='GRANT_INVALIDATED'):
                        await owner.enroll()
    asyncio.run(run())
