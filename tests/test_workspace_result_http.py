"""Signed actual UID458 → Unix service → closed fixture Runtime owner.

These tests do not qualify installed namespace custody or an Auth0 registration.
"""
import asyncio
import json
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import urlencode

import httpx
import pytest

from control_plane import executive_runtime as er
from control_plane import fabric_result_projection as frp
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig, create_workspace_app
from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
from integrations.mastermind_workspace_app.contract import BINDINGS_SCHEMA, canonical, principal_frame, workspace_authorizers
from integrations.executive_mcp.server import AuditedWorkspaceApp, build_executive_mcp_app, _mounted_lifespan
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from tests.test_workspace_read_app import rsa_key, _authenticator, _workspace_token, NOW
from tests.test_workspace_read_socket import control, short_socket_root
from tests.test_workspace_result_service import result_owner, request
from tests.test_mastermind_executive_app_asgi import _read_policy, _submit_policy, _FakeJwksCache
from integrations.mastermind_executive_app.app import AppSettings
from integrations.mastermind_executive_app.gateway import AppPolicies


@asynccontextmanager
async def transport(o, rsa_key, tmp_path, socket_root, *, after_control=None, after_app=None):
    auth = _authenticator(rsa_key); token = _workspace_token(rsa_key)
    principal = await auth.verify_authorization_header('Bearer ' + token, now=NOW)
    slots = {'schema': BINDINGS_SCHEMA, 'profiles': {
        'web': {'enabled': True, 'binding': dict(principal_frame(principal), permission_digest='a' * 64)},
        'mac': {'enabled': False, 'binding': None}}}
    app_auth, control_auth = workspace_authorizers(policy=auth.policy, load_bindings=lambda: slots)
    seen = {'factory': 0, 'projected': []}
    def factory(actual):
        assert actual is o['writer']; seen['factory'] += 1
        def project(snapshot, receipt):
            value = frp.project_fabric_role_result(snapshot, receipt)
            seen['projected'].append(value)
            if after_control: after_control(slots)
            return value
        return WorkspaceReadService(cache=o['cache'], runtime=actual, authorize=control_auth,
            armed={}, runtime_identity={'db_present': True}, result_project=project,
            bounded_runtime=lambda owner: o['reader'] if owner is o['writer'] else pytest.fail('wrong owner'))
    svc = control(tmp_path, socket_root, factory); svc._runtime_factory = lambda path: o['writer']
    await svc.start()
    client = CeoIngressWorkspaceClient(svc.ceo_ingress_socket_path)
    class AppClient:
        async def request(self, frame):
            response = await client.request(frame)
            if after_app: after_app(slots)
            return response
    workspace = create_workspace_app(WorkspaceAppConfig(authenticator=auth, now=lambda: NOW,
        authorize_principal=app_auth, client=AppClient()))
    class Sink:
        def __init__(self): self.events = []
        def emit(self, event): self.events.append(event)
    sink = Sink(); verifier = MastermindTokenVerifier(authenticator=auth, policy=auth.policy, now=lambda: NOW, audit_sink=sink)
    mounted = build_executive_mcp_app(AppSettings(policies=AppPolicies(read=_read_policy(), submit=_submit_policy()),
        mastermind_root=tmp_path, macro_root_flag=None, environ={}, ceo_ingress_socket_path=svc.ceo_ingress_socket_path,
        read_from_ceo_ingress=True, jwks_cache=_FakeJwksCache(rsa_key), clock=lambda: NOW),
        audit_sink=sink, workspace_app=AuditedWorkspaceApp(workspace, verifier))
    try:
        async with _mounted_lifespan(mounted):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounted), base_url='https://mcp.mastermind-x.com') as http:
                yield http, token, slots, seen, client, principal, mounted, sink
    finally:
        await svc.close()


def test_signed_result_and_mission_join_real_owners(result_owner, rsa_key, tmp_path, short_socket_root, monkeypatch):
    o = result_owner
    # Every success forbids broad registry acquisition.
    for registry, method in [(o['reader'].jobs, 'list_jobs'), (o['reader'].attempts, 'list_attempts'), (o['reader'].events, 'list_events')]:
        monkeypatch.setattr(registry, method, lambda *a, **k: pytest.fail('unbounded acquisition'))
    async def run():
        async with transport(o, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, client, principal, mounted, sink):
            headers = {'Authorization': 'Bearer ' + token}
            before = o['namespace'].entries
            traces=[]
            original_connect=er.sqlite3.connect
            def connect(*a,**k):
                connection=original_connect(*a,**k); connection.set_trace_callback(traces.append); return connection
            monkeypatch.setattr(er.sqlite3,'connect',connect)
            response = await http.get('/workspace/result/current', params=o['selection'], headers=headers)
            assert response.status_code == 200, response.text
            body = response.json()
            statements=[sql.strip().upper() for sql in traces]
            assert statements.count('PRAGMA DATA_VERSION') == 2
            assert len(statements) <= er.BOUNDED_ROLE_RESULT_MAX_STATEMENTS + 40
            assert not any(sql.startswith(('INSERT','UPDATE','DELETE')) for sql in statements)
            (tmp_path/'actual-result.json').write_bytes(response.content)
            assert body['availability'] == 'AVAILABLE' and body['result'] == seen['projected'][-1].complete
            assert body['source_observation']['runtime'] == body['result']['generation']
            assert body['result']['review']['verdict'] == 'reject'
            assert body['selection']['result_envelope_digest'] != body['result']['review']['reviewed_result_digest']
            assert response.headers['cache-control'] == 'no-store' and len(response.content) <= 16384
            assert o['namespace'].entries == before + 1 == o['namespace'].exits
            frame = request(o); frame['principal'] = principal_frame(principal)
            socket = await client.request(frame)
            assert socket['result']['result'] == seen['projected'][-1].complete
            assert len(canonical(socket)) + 1 <= 16384
            # Separate fresh observation identities are deliberately not equated.
            mission = await http.get('/workspace/mission/v3/current', params={k:o['selection'][k] for k in ('work_ref','root_job_id')}, headers=headers)
            assert mission.status_code == 200, mission.text
            doc = mission.json()
            (tmp_path/'actual-mission-v3.json').write_bytes(mission.content)
            (tmp_path/'fixture-provenance.json').write_text(json.dumps({'proof':'real signed HTTP and Unix socket; closed test-owned namespace only','selection':o['selection'],'result_http_bytes':len(response.content),'result_socket_bytes':len(canonical(socket))+1,'result_sql_statements':len(statements)},indent=2)+'\n')
            assert doc['read_state']['state'] == 'CURRENT', doc['source']
            assert any(row['result_envelope_digest'] == o['selection']['result_envelope_digest'] for row in doc['result_refs']['refs'])
            assert any(event.accepted and event.policy_id == _authenticator(rsa_key).policy.policy_id for event in sink.events)
    asyncio.run(run())


def test_signed_deny_before_cache_and_runtime(result_owner, rsa_key, tmp_path, short_socket_root):
    o=result_owner
    async def run():
        async with transport(o, rsa_key, tmp_path, short_socket_root) as (http, token, slots, seen, *_):
            o['cache'].snapshot = lambda: pytest.fail('cache before permission')
            before=o['namespace'].entries
            for path,selection in [('/workspace/result/current',o['selection']),('/workspace/mission/v3/current',{k:o['selection'][k] for k in ('work_ref','root_job_id')})]:
                for bad in (None,_workspace_token(rsa_key,client_id='foreign'),_workspace_token(rsa_key,scope='mastermind.executive.read'),_workspace_token(rsa_key,sub='foreign'),_workspace_token(rsa_key,resource='https://wrong.example.test')):
                    response=await http.get(path,params=selection,headers={} if bad is None else {'Authorization':'Bearer '+bad})
                    assert response.status_code in (401,403)
                    assert seen['factory']==0 and o['namespace'].entries==before
            slots['profiles']['web']['enabled']=False
            response=await http.get('/workspace/result/current',params=o['selection'],headers={'Authorization':'Bearer '+token})
            assert response.status_code==403 and seen['factory']==0
    asyncio.run(run())


@pytest.mark.parametrize('gate',['control','app'])
@pytest.mark.parametrize('mutation',['disabled','missing','digest'])
def test_real_binding_reload_discards_material(result_owner,rsa_key,tmp_path,short_socket_root,gate,mutation):
    def mutate(slots):
        profile=slots['profiles']['web']
        if mutation=='disabled':profile['enabled']=False
        elif mutation=='missing':profile['binding']=None
        else:profile['binding']['permission_digest']='b'*64
    async def run():
        async with transport(result_owner,rsa_key,tmp_path,short_socket_root,**{'after_'+gate:mutate}) as (http,token,slots,seen,*_):
            response=await http.get('/workspace/result/current',params=result_owner['selection'],headers={'Authorization':'Bearer '+token})
            assert response.status_code==403 and seen['projected']
            assert 'role_result' not in response.text and 'reject' not in response.text
    asyncio.run(run())


def test_raw_asgi_query_rejection_before_acquisition(result_owner,rsa_key,tmp_path,short_socket_root):
    async def run():
        async with transport(result_owner,rsa_key,tmp_path,short_socket_root) as (http,token,slots,seen,client,principal,mounted,sink):
            base=urlencode(result_owner['selection']).encode()
            queries=[base+b'&extra=x',base+b'&work_ref=WS:OTHER',base+b'#frag',base.replace(b'work_ref=',b'%77ork_ref='),base.replace(b'work_ref=',b'work_ref=%GG'),base.replace(b'work_ref=',b'work_ref=+'),base.replace(b'&',b';',1),base+b'&bad',b'work_ref=WS:ONE']
            for query in queries:
                sent=[]
                async def receive():return {'type':'http.request','body':b'','more_body':False}
                async def send(event):sent.append(event)
                await mounted({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'https','method':'GET',
                    'path':'/workspace/result/current','raw_path':b'/workspace/result/current','root_path':'','query_string':query,
                    'headers':[(b'host',b'mcp.mastermind-x.com'),(b'authorization',('Bearer '+token).encode())],
                    'client':('127.0.0.1',1),'server':('mcp.mastermind-x.com',443)},receive,send)
                assert next(e['status'] for e in sent if e['type']=='http.response.start')==400
                assert seen['factory']==0
    asyncio.run(run())
