"""Actual UID458 dispatcher and sealed static/config composition; fixtures only."""
import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import test_executive_mcp_app_composition as existing
from integrations.executive_mcp import server
from ops.executive_os import executive_mcp_entry as entry

rsa_key = existing.rsa_key
settings = existing.settings
short_socket_root = existing.short_socket_root

class Mount:
    def __init__(self): self.calls = []
    async def __call__(self, scope, receive, send):
        self.calls.append((scope['path'], scope.get('query_string', b'')))
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'owned mount'})


def test_actual_outer_dispatch_and_path_fence(settings):
    workspace, content = Mount(), Mount()
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
                                        workspace_app=workspace, content_app=content)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=entry.PUBLIC_ORIGIN) as client:
            assert (await client.get('/workspace/programs/current')).status_code == 200
            assert (await client.get('/workspace/mission/current?work_ref=WS:ONE&root_job_id=JOB-001')).status_code == 200
            assert (await client.get('/workspace/window/current')).status_code == 200
            assert workspace.calls[-1][1] == b'work_ref=WS:ONE&root_job_id=JOB-001'
            calls = len(workspace.calls) + len(content.calls)
            for url, method in [('/workspace/programs/current?x=1','GET'),('/workspace/window/current?x=1','GET'),
                                ('/workspace/programs/current/','GET'),('/workspace%2Fprograms/current','GET'),
                                ('/workspace/programs/current','POST'),('/workspace/window/current','HEAD'),
                                ('/mcp?x=1','POST')]:
                assert (await client.request(method,url)).status_code == 404
            assert (await client.get('/workspace/programs/current',headers=[('Authorization','Bearer a'),('Authorization','Bearer b')])).status_code in (400,401)
            assert len(workspace.calls)+len(content.calls)==calls
            assert (await client.get('/mcp')).status_code == 404
    asyncio.run(check())


def test_absent_mounts_keep_legacy_closed(settings):
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=entry.PUBLIC_ORIGIN) as client:
            for path in ('/workspace/programs/current','/workspace/mission/current','/workspace/window/current','/os/'):
                assert (await client.get(path)).status_code==404
    asyncio.run(check())


@pytest.fixture
def static_source(tmp_path,monkeypatch):
    source=tmp_path/'sealed-release';dist=source/'app/mastermind_os/dist';(dist/'assets').mkdir(parents=True)
    (dist/'index.html').write_text('<link rel="stylesheet" href="/os/assets/index-abc.css"><script src="/os/assets/index-def.js"></script>')
    (dist/'assets/index-abc.css').write_text('body { color: white; }')
    (dist/'assets/index-def.js').write_text('console.log("fixture");')
    monkeypatch.setattr(entry,'require_sealed_path',lambda *a,**k:None)
    return source


def test_asset_manifest_and_callback_headers(static_source,settings):
    manifest=entry.build_os_asset_manifest(static_source)
    dist=static_source/'app/mastermind_os/dist'
    (dist/'asset-manifest.json').write_text(json.dumps(manifest))
    os_app=entry.load_os_app(static_source)
    app=server.build_executive_mcp_app(settings,audit_sink=existing.Sink(),os_app=os_app)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=entry.PUBLIC_ORIGIN) as client:
            index=await client.get('/os/')
            for path in ('/os/auth/callback?code=secret&state=opaque','/os/?work_ref=WS:ONE&root_job_id=JOB-001'):
                reply=await client.get(path);assert reply.status_code==200 and reply.content==index.content
                assert b'secret' not in reply.content
                assert reply.headers['cache-control']=='no-store'
                assert reply.headers['referrer-policy']=='no-referrer'
                assert reply.headers['x-content-type-options']=='nosniff'
                assert 'https://dev-eo0jf8us5mup7wd5.us.auth0.com' in reply.headers['content-security-policy']
            assert (await client.get('/os/assets/index-def.js')).headers['content-type']=='text/javascript; charset=utf-8'
            for path in ('/os/?x=1','/os/?work_ref=WS:ONE','/os/auth/callback?code=a&code=b',
                         '/os/auth/callback?next=https://evil.example','/os/assets/index-def.js?x=1',
                         '/os/assets/missing.js','/os/index.html','/os/auth/callback?code='+('a'*8193)):
                refusal=await client.get(path)
                assert refusal.status_code in (400,404)
                assert refusal.headers['cache-control']=='no-store' and refusal.headers['referrer-policy']=='no-referrer'
            assert (await client.post('/os/')).status_code==404
    asyncio.run(check())


@pytest.mark.parametrize('fault',['bytes','extra','symlink','manifest_path'])
def test_static_manifest_refuses_drift_and_paths(static_source,fault):
    dist=static_source/'app/mastermind_os/dist';manifest=entry.build_os_asset_manifest(static_source)
    (dist/'asset-manifest.json').write_text(json.dumps(manifest))
    if fault=='bytes':(dist/'assets/index-def.js').write_text('changed')
    elif fault=='extra':(dist/'assets/foreign.js').write_text('foreign')
    elif fault=='symlink':
        f=dist/'assets/index-def.js';f.unlink();f.symlink_to(dist/'index.html')
    else:
        manifest['files'][0]['path']='../../secret';(dist/'asset-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):entry.load_os_app(static_source)


def document():
    return {'schema':entry.CONFIG_SCHEMA,'release_sha':'1'*40,'service_uid':458,'port':8443,
            'ceo_ingress_socket_path':'/var/run/mastermind-executive/ceo-ingress.sock',
            'audit_root':'/var/log/mastermind-executive/mcp-auth','policies':{}}


def workspace_block():
    policy=existing.fixture._read_policy(policy_id='workspace',resource='https://mcp.mastermind-x.com/workspace/read',
          resource_metadata_url='https://mcp.mastermind-x.com/.well-known/oauth-protected-resource/workspace',required_scopes=['mastermind.workspace.read'])
    return {'policy':json.loads(json.dumps(dataclasses.asdict(policy))),
            'bindings':{'schema':'mastermind.workspace_acquisition_bindings.v1','profiles':{
                'web':{'enabled':False,'binding':None},'mac':{'enabled':False,'binding':None}}}}


def test_optional_config_closed_and_validated():
    raw=document();raw['workspace']=workspace_block();assert entry.validate_document(raw)==raw
    for change in ('unknown','missing','null','bad_scope'):
        broken=json.loads(json.dumps(raw))
        if change=='unknown':broken['workspace']['other']=True
        elif change=='missing':del broken['workspace']['bindings']
        elif change=='null':broken['workspace']=None
        else:broken['workspace']['policy']['required_scopes']=['mastermind.executive.read']
        with pytest.raises(ValueError):entry.validate_document(broken)


def test_current_projection_rechecks_seal_and_policy(tmp_path,monkeypatch):
    source=tmp_path/('1'*40);source.mkdir();path=tmp_path/'app.json';raw=document();raw['workspace']=workspace_block();path.write_text(json.dumps(raw))
    checks=[];monkeypatch.setattr(entry,'require_sealed_path',lambda p,**k:checks.append(p));monkeypatch.setattr(entry.os,'geteuid',lambda:458)
    loader=entry.current_projection_loader(path,source,raw,'workspace','bindings')
    assert loader()==raw['workspace']['bindings'] and path in checks
    changed=json.loads(json.dumps(raw));changed['workspace']['policy']['policy_id']='rotated';path.write_text(json.dumps(changed))
    with pytest.raises(ValueError):loader()
    path.write_text(json.dumps({k:v for k,v in raw.items() if k!='workspace'}))
    with pytest.raises(ValueError):loader()


def test_workspace_audit_gate_real_jwt_and_failed_sink(rsa_key):
    from integrations.business_mcp_auth.contracts import load_resource_policy
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
    policy=load_resource_policy(workspace_block()['policy'])
    auth=JwtAuthenticator(policy=policy,jwks_cache=existing.fixture._FakeJwksCache(rsa_key))
    sink=existing.Sink();inner=Mount()
    verifier=MastermindTokenVerifier(authenticator=auth,policy=policy,now=lambda:existing.fixture.NOW,audit_sink=sink)
    app=server.AuditedWorkspaceApp(inner,verifier)
    valid=existing.fixture._token(rsa_key,scope='mastermind.workspace.read',resource=policy.resource)
    wrong=existing.fixture._token(rsa_key,scope='mastermind.executive.read',resource=policy.resource)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=entry.PUBLIC_ORIGIN) as client:
            assert (await client.get('/workspace/programs/current',headers={'Authorization':'Bearer '+valid})).status_code==200
            assert len(inner.calls)==1 and sink.events[-1].accepted is True
            assert (await client.get('/workspace/programs/current',headers={'Authorization':'Bearer '+wrong})).status_code==401
            assert len(inner.calls)==1 and sink.events[-1].policy_id==policy.policy_id and not sink.events[-1].accepted
            def fail(event):raise OSError('fixture audit unavailable')
            sink.emit=fail
            assert (await client.get('/workspace/programs/current',headers={'Authorization':'Bearer '+valid})).status_code==401
            assert len(inner.calls)==1
    asyncio.run(check())


@pytest.mark.parametrize('query',[b'code=%ZZ',b'code=%00',b'code=a#fragment',b'code=a&state=x&state=y'])
def test_callback_query_encoding_is_strict(query):
    assert not server.OsStaticApp._query_allowed('/os/auth/callback',query)


def test_manifest_byte_count_rejects_bool(static_source):
    dist=static_source/'app/mastermind_os/dist';(dist/'assets/index-def.js').write_text('x')
    manifest=entry.build_os_asset_manifest(static_source)
    for item in manifest['files']:
        if item['path'].endswith('.js'):item['byte_count']=True
    (dist/'asset-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):entry.load_os_app(static_source)


def test_outer_lifespan_drains_optional_owners(settings):
    events=[]
    class ManagedMount(Mount):
        def __init__(self,name):super().__init__();self.name=name
        async def __call__(self,scope,receive,send):
            if scope['type']!='lifespan':return await super().__call__(scope,receive,send)
            while True:
                message=await receive()
                if message['type']=='lifespan.startup':
                    events.append(self.name+' start');await send({'type':'lifespan.startup.complete'})
                else:
                    events.append(self.name+' stop');await send({'type':'lifespan.shutdown.complete'});return
    app=server.build_executive_mcp_app(settings,audit_sink=existing.Sink(),
          workspace_app=ManagedMount('workspace'),content_app=ManagedMount('content'))
    async def check():
        incoming,outgoing=asyncio.Queue(),asyncio.Queue()
        task=asyncio.create_task(app({'type':'lifespan','asgi':{'version':'3.0'}},incoming.get,outgoing.put))
        try:
            await incoming.put({'type':'lifespan.startup'})
            assert (await asyncio.wait_for(outgoing.get(),5))['type']=='lifespan.startup.complete'
            assert events==['workspace start','content start']
        finally:
            await incoming.put({'type':'lifespan.shutdown'})
            await asyncio.wait_for(outgoing.get(),5)
            await task
        assert events==['workspace start','content start','content stop','workspace stop']
    asyncio.run(check())


def test_os_owner_cannot_register_arbitrary_routes():
    with pytest.raises(ValueError):server.OsStaticApp({'/admin':(b'x','text/html; charset=utf-8')})


def test_asset_manifest_has_no_hidden_second_manifest(static_source):
    dist=static_source/'app/mastermind_os/dist'
    (dist/'assets/asset-manifest.json').write_text('{}')
    with pytest.raises(ValueError):entry.build_os_asset_manifest(static_source)


def test_concrete_optional_factories_and_public_projection(tmp_path,monkeypatch,rsa_key):
    from integrations.mastermind_executive_app import gateway
    from integrations.mastermind_workspace_app.installed import CeoIngressWorkspaceClient
    source=tmp_path/('1'*40);source.mkdir();path=tmp_path/'app.json';raw=document();raw['workspace']=workspace_block()
    steward_policy=existing.fixture._read_policy(policy_id='steward',resource=entry.PUBLIC_ORIGIN+'/steward/mcp',
        resource_metadata_url=entry.PUBLIC_ORIGIN+'/.well-known/oauth-protected-resource/steward',required_scopes=['mastermind.steward.read'])
    content_policy=existing.fixture._read_policy(policy_id='content',resource=entry.PUBLIC_ORIGIN+'/workspace/window/current',
        resource_metadata_url=entry.PUBLIC_ORIGIN+'/.well-known/oauth-protected-resource/content',required_scopes=['mastermind.workspace.content.read'])
    wire=lambda p:json.loads(json.dumps(dataclasses.asdict(p)))
    raw['steward']={'policy':wire(steward_policy),'content_policy':wire(content_policy),'allowed_origin':entry.PUBLIC_ORIGIN,
        'content_profiles':{'schema':'mastermind.executive_content_profiles.v1','profiles':{
            'web':{'enabled':False,'profile':None},'mac':{'enabled':False,'profile':None}}}}
    path.write_text(json.dumps(raw));assert entry.validate_document(raw)==raw
    monkeypatch.setattr(entry,'require_sealed_path',lambda *a,**k:None);monkeypatch.setattr(entry.os,'geteuid',lambda:458)
    monkeypatch.setattr(entry.time,'time',lambda:existing.fixture.NOW)
    monkeypatch.setattr(gateway,'_default_jwks_cache',lambda policy:existing.fixture._FakeJwksCache(rsa_key))
    async def forbidden(*a,**k):pytest.fail('disabled public binding reached socket')
    monkeypatch.setattr(CeoIngressWorkspaceClient,'request',forbidden)
    sink=existing.Sink();mounts=entry.build_optional_apps(raw,source,path,sink)
    assert set(mounts)=={'workspace_app','content_app'}
    async def check():
        for name,route,policy in [('workspace_app','/workspace/programs/current',entry.optional_policies(raw)['workspace']),
                                  ('content_app','/workspace/window/current',content_policy)]:
            token=existing.fixture._token(rsa_key,scope=policy.required_scopes[0],resource=policy.resource)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mounts[name]),base_url=entry.PUBLIC_ORIGIN) as client:
                assert (await client.get(route,headers={'Authorization':'Bearer '+token})).status_code in (401,403)
    asyncio.run(check())
    assert {'workspace','content'}<={event.policy_id for event in sink.events}


def test_public_mount_transport_fence_precedes_dispatch(settings, static_source):
    workspace = Mount()
    dist = static_source/'app/mastermind_os/dist'
    (dist/'asset-manifest.json').write_text(json.dumps(entry.build_os_asset_manifest(static_source)))
    app = server.build_executive_mcp_app(settings, audit_sink=existing.Sink(),
        workspace_app=workspace, os_app=entry.load_os_app(static_source))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=entry.PUBLIC_ORIGIN) as client:
            for path in ('/workspace/programs/current', '/os/', '/os/auth/callback'):
                assert (await client.get(path)).status_code == 200
                assert (await client.get(path,headers={'Origin':entry.PUBLIC_ORIGIN})).status_code == 200
                before = len(workspace.calls)
                for headers in ({'Host':'invalid.example'}, {'Origin':'https://invalid.example'},
                    [('Host','mcp.mastermind-x.com'),('Host','mcp.mastermind-x.com')],
                    [('Origin',entry.PUBLIC_ORIGIN),('Origin',entry.PUBLIC_ORIGIN)]):
                    assert (await client.get(path,headers=headers)).status_code in (400,403)
                assert (await client.get('http://mcp.mastermind-x.com'+path)).status_code == 403
                assert len(workspace.calls) == before
    asyncio.run(check())

def test_repeated_cancellation_does_not_interrupt_shutdown_cleanup():
    async def check():
        entered, shutdown_started, release, cleaned = (asyncio.Event() for _ in range(4))
        async def owner(scope,receive,send):
            assert (await receive())['type']=='lifespan.startup'
            await send({'type':'lifespan.startup.complete'})
            assert (await receive())['type']=='lifespan.shutdown'
            shutdown_started.set()
            await release.wait()
            cleaned.set()
            await send({'type':'lifespan.shutdown.complete'})
        async def parent():
            async with server._mounted_lifespan(owner):
                entered.set()
                await asyncio.Event().wait()
        task=asyncio.create_task(parent())
        try:
            await asyncio.wait_for(entered.wait(),1)
            task.cancel()
            await asyncio.wait_for(shutdown_started.wait(),1)
            task.cancel()
            for _ in range(12):
                await asyncio.sleep(0)
            assert not task.done(), 'mounted lifecycle relinquished incomplete cleanup'
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
        assert cleaned.is_set()
    asyncio.run(check())


def test_shutdown_deadline_retains_owner_until_cleanup_terminal(monkeypatch):
    async def check():
        entered, shutdown_started, release, cleaned = (asyncio.Event() for _ in range(4))
        original_wait = asyncio.wait_for
        calls = 0
        async def bounded_wait(awaitable, timeout):
            nonlocal calls
            if timeout == 10:
                calls += 1
                if calls == 2:
                    awaitable.close()
                    raise TimeoutError('test-owned shutdown deadline')
            return await original_wait(awaitable, timeout)
        monkeypatch.setattr(server.asyncio, 'wait_for', bounded_wait)
        async def owner(scope,receive,send):
            await receive(); await send({'type':'lifespan.startup.complete'})
            await receive(); shutdown_started.set()
            await release.wait(); cleaned.set()
            await send({'type':'lifespan.shutdown.complete'})
        async def parent():
            async with server._mounted_lifespan(owner):
                entered.set()
        task = asyncio.create_task(parent())
        await original_wait(shutdown_started.wait(),1)
        for _ in range(12): await asyncio.sleep(0)
        assert not task.done() and not cleaned.is_set()
        release.set()
        with pytest.raises(TimeoutError): await task
        assert cleaned.is_set()
    asyncio.run(check())


def test_public_mount_trusts_only_loopback_forwarded_scheme(settings):
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    mount = Mount()
    app = ProxyHeadersMiddleware(server.build_executive_mcp_app(settings,
        audit_sink=existing.Sink(),workspace_app=mount),trusted_hosts='127.0.0.1')
    async def check():
        for peer, expected in [('127.0.0.1',200),('192.0.2.1',403)]:
            transport=httpx.ASGITransport(app=app,client=(peer,12345))
            async with httpx.AsyncClient(transport=transport,base_url='http://mcp.mastermind-x.com') as client:
                assert (await client.get('/workspace/programs/current',headers={'X-Forwarded-Proto':'https'})).status_code==expected
        assert len(mount.calls)==1
    asyncio.run(check())
