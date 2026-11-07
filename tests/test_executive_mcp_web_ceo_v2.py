"""Independent probes of immutable GLM partial; no production source edits."""
import asyncio, copy, dataclasses, json, tempfile
from contextlib import asynccontextmanager
from pathlib import Path
import pytest
import jsonschema
from control_plane import executive_runtime as er
from control_plane import executive_service as es
from control_plane import fabric_result_projection as projection
from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp import web_ceo as web
from integrations.executive_mcp.adapter import GatewayConfig
from tests import test_executive_service as service_fixture
from tests.test_executive_runtime_bounded_role_result import complete_maximum_chain

NOW='2026-09-21T17:00:00Z'

def gateway(tmp_path):
    repo=tmp_path/'repo';repo.mkdir(exist_ok=True)
    rt=tmp_path/'runtime';rt.mkdir(exist_ok=True)
    def forbidden(*args,**kwargs):raise AssertionError('legacy factory must not run')
    return web.WebCeoV2ExecutiveMcpGateway(GatewayConfig(mode=legacy.ServerMode.READONLY,repo_root=repo,read_runtime_root=rt),clock=lambda:NOW,runtime_factory=forbidden)

@asynccontextmanager
async def owner(tmp_path):
    _,root,nodes=complete_maximum_chain(tmp_path/'runtime')
    sock=tempfile.TemporaryDirectory(prefix='c-review-')
    service=es.ExecutiveControlService(service_fixture._config(tmp_path,socket_root=Path(sock.name)),supervisor_factory=service_fixture._FakeSupervisor)
    g=gateway(tmp_path);getter_calls=[]
    def get():
        getter_calls.append(1)
        return service._namespace_custody.bound_runtime(service._require_runtime())
    g.bind_fabric_source(bounded_runtime=get,armed={},runtime_identity={'root':'readonly:review-runtime','db_present':True,'identity':None})
    try:
        await service.start()
        yield service,g,root,nodes,getter_calls
    finally:
        await g.aclose();await service.close();sock.cleanup()

def selection(service,root,node):
    job,attempt,_=node
    expected=service._require_runtime().validated_role_completion(job,expected_attempt_id=attempt)
    return dict(view='result',root_job_id=root.job_id,job_id=job,attempt_id=attempt,result_envelope_digest=expected.result_digest),expected


def test_actual_retained_owner_six_node_positive(tmp_path):
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            records=[]
            for node in nodes:
                args,expected=selection(s,root,node)
                out=await g.call('executive_fabric',args)
                assert out['ok'] is True,out
                data=out['data']
                assert data['generation']['state']=='SAME'
                assert data['generation']['source_identity'] is not None
                assert data['content']=={k:expected.result_envelope[k] for k in ('role_result','summary','next_actions')}
                assert data['selection']=={k:v for k,v in args.items() if k!='view'}
                assert data['availability']=='AVAILABLE' and data['acceptance']=='NOT_PROJECTED'
                assert not out['bounded']
                assert len(es._canonical_json({'ok':True,'result':out}))<=16384
                if data['role']=='review':assert data['review']['latest_revision_currentness']=='UNPROVEN'
                records.append({'role':data['role'],'tuple':data['selection'],'wire_bytes':len(es._canonical_json({'ok':True,'result':out}))})
            assert len(calls)==len(nodes)
    asyncio.run(run())


def test_one_fresh_getter_per_physical_result_read(tmp_path):
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            args,_=selection(s,root,nodes[-1]);out=await g.call('executive_fabric',args)
            assert out['ok'] is True,out
            assert len(calls)==1
    asyncio.run(run())


@pytest.mark.parametrize('bad',[
    {'view':'roots','root_job_id':'JOB-1'},
    {'view':'roots','job_id':'JOB-1'},
    {'view':'root','root_job_id':'JOB-1','limit':1},
    {'view':'root','root_job_id':'JOB-1','job_id':'JOB-2'},
    {'view':'root','root_job_id':'JOB-1','attempt_id':'ATT-'+'a'*32},
])
def test_advertised_schema_matches_closed_validator(bad):
    with pytest.raises(legacy.GatewayError):web.validate_web_ceo_v2_tool_arguments('executive_fabric',bad)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,web.FABRIC_V2_TOOL_SPEC.input_schema)


def test_profile_hashes_and_versions():
    assert legacy.schema_snapshot_sha256()=='546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232'
    assert web.web_ceo_schema_snapshot_sha256()=='17e052ed734c2c4606094c49b0e9c057382a193fc181d595fc084da10809a5cd'
    assert web.web_ceo_v2_schema_snapshot_sha256()==web.WEB_CEO_V2_SCHEMA_SNAPSHOT_SHA256
    assert web.WEB_CEO_V2_SERVER_VERSION=='1.2.0'


@pytest.mark.parametrize('mutation',['digest','root','attempt','acquisition_budget'])
def test_actual_owner_refusal_has_no_content_or_counts(tmp_path,monkeypatch,mutation):
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            args,_=selection(s,root,nodes[-1])
            if mutation=='digest':args['result_envelope_digest']='0'*64
            elif mutation=='root':args['root_job_id']='JOB-999999999'
            elif mutation=='attempt':args['attempt_id']='ATT-'+'0'*32
            else:monkeypatch.setattr(er,'BOUNDED_ROLE_RESULT_MAX_STATEMENTS',1)
            out=await g.call('executive_fabric',args)
            assert out['ok'] is False and out['data'] is None,out
            assert 'counts' not in out and 'content' not in out
            assert out['error']['code']==('output_too_large' if mutation=='acquisition_budget' else 'backend_unavailable')
            assert str(tmp_path) not in json.dumps(out)
    asyncio.run(run())


def test_binding_is_inert_copied_and_immutable(tmp_path):
    g=gateway(tmp_path);calls=[];facts={'nested':{'values':[1]}}
    g.bind_fabric_source(bounded_runtime=lambda:calls.append(1),armed=facts,runtime_identity={})
    assert not calls
    facts['nested']['values'].append(2)
    assert g._fabric_source_binding[1]['nested']['values']==(1,)
    with pytest.raises(TypeError):g._fabric_source_binding[1]['nested']['new']=1
    with pytest.raises(legacy.GatewayError):g.bind_fabric_source(bounded_runtime=lambda:None,armed={},runtime_identity={})
    asyncio.run(g.aclose())


@pytest.mark.parametrize('state',['invalid_first_call','closed','noncallable'])
def test_binding_refuses_late_and_invalid(tmp_path,state):
    async def run():
        g=gateway(tmp_path)
        if state=='invalid_first_call':await g.call('not-a-tool',{})
        elif state=='closed':await g.aclose()
        with pytest.raises(legacy.GatewayError):g.bind_fabric_source(bounded_runtime=(None if state=='noncallable' else lambda:None),armed={},runtime_identity={})
        await g.aclose()
    asyncio.run(run())


def test_unbound_refuses_without_legacy_factory(tmp_path):
    async def run():
        g=gateway(tmp_path)
        try:
            out=await g.call('executive_fabric',dict(view='result',root_job_id='JOB-1',job_id='JOB-2',attempt_id='ATT-'+'a'*32,result_envelope_digest='b'*64))
            assert out['ok'] is False and out['error']['code']=='backend_unavailable'
        finally:await g.aclose()
    asyncio.run(run())


def test_exact_utf8_outer_budget_and_fallback_remeasurement(tmp_path,monkeypatch):
    """Formatting unit isolates budget with an actual canonical projection seed."""
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            args,_=selection(s,root,nodes[-1])
            p,ground,degraded=g._executive_fabric(args)
            def envelope(doc):
                e=legacy.result_envelope('executive_fabric',mode=g.config.mode,generated_at=NOW,data=doc,grounding=ground,degraded=degraded)
                e['server_version']='1.2.0';return e
            base=copy.deepcopy(p.complete);base['content']['summary']='漢🙂'
            pad=16384-len(es._canonical_json({'ok':True,'result':envelope(base)}))
            assert pad>0
            base['content']['summary']+='a'*pad
            monkeypatch.setattr(g,'_executive_fabric',lambda a:(projection.FabricRoleResultProjection(base,p.content_over_budget),ground,degraded))
            exact=g._read_fabric_result('executive_fabric',args,NOW)
            assert len(es._canonical_json({'ok':True,'result':exact}))==16384
            assert exact['data']['availability']=='AVAILABLE'
            base['content']['summary']+='a'
            out=g._read_fabric_result('executive_fabric',args,NOW)
            assert out['data']['availability']=='CONTENT_OVER_BUDGET'
            assert out['data']['content'] is None
            assert out['data']['counts']==p.complete['counts']
            assert len(es._canonical_json({'ok':True,'result':out}))<=16384
            monkeypatch.setattr(g,'_executive_fabric',lambda a:(p,{'source':'x'*20000},degraded))
            with pytest.raises(legacy.GatewayError) as error:g._read_fabric_result('executive_fabric',args,NOW)
            assert error.value.code=='output_too_large'
    asyncio.run(run())


"""Independent actual JWT + CeoIngress v3 + retained Runtime composition."""
import asyncio, dataclasses, json, os
from pathlib import Path
import httpx
import pytest
from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding,CEO_WEB_CEO_V2_READ_SCHEMA
from tests.test_executive_runtime_bounded_role_result import complete_maximum_chain
from tests import test_executive_mcp_web_ceo_app as old
from integrations.executive_mcp import web_ceo as web, server as transport
from integrations.mastermind_executive_app import app as appmod
from integrations.executive_mcp import schemas as legacy

rsa_key=old.rsa_key
short_socket_root=old.short_socket_root
settings=old.settings

@pytest.mark.parametrize('case',['authorized','expiry_after_read','invalid_before_read','changed_principal'])
def test_real_jwt_and_v3_socket_with_actual_retained_owner(settings,rsa_key,tmp_path,short_socket_root,case,monkeypatch):
    async def run():
        base=old.fixture._real_service(tmp_path,socket_root=short_socket_root,mastermind_root=Path(settings.mastermind_root),macro_root=Path(settings.macro_root_flag))
        rt,root,nodes=complete_maximum_chain(base.config.runtime_root)
        job,attempt,_=nodes[-1];expected=rt.validated_role_completion(job,expected_attempt_id=attempt)
        readers=web.WebCeoV2InstalledExecutiveReaders(repo_root=Path(settings.mastermind_root),macro_root=Path(settings.macro_root_flag),runtime_root=base.config.runtime_root)
        service=ExecutiveControlService(base.config,supervisor_factory=lambda runtime:old.fixture._NoExecutionSupervisor(),ceo_ingress_socket_path=settings.ceo_ingress_socket_path,ceo_ingress_peer_uid=os.geteuid()+1000,ceo_ingress_grounding_provider=readers,ceo_ingress_armed=False,ceo_ingress_app_binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=readers,read_provider=readers,read_schema=CEO_WEB_CEO_V2_READ_SCHEMA))
        getter_calls=[]
        def get():
            getter_calls.append(1)
            return service._namespace_custody.bound_runtime(service._require_runtime())
        readers.bind_fabric_source(bounded_runtime=get,armed={},runtime_identity={'root':'readonly:installed-executive-runtime','db_present':True,'identity':None})
        now=[old.fixture.NOW];original_call=readers.call
        async def observed_call(name,args):
            response=await original_call(name,args)
            if case=='expiry_after_read':now[0]+=10000
            return response
        readers.call=observed_call
        bound=dataclasses.replace(settings,read_from_ceo_ingress=True,mastermind_root=tmp_path/'no-network-checkout',macro_root_flag=None,clock=lambda:now[0])
        if case=='changed_principal':
            original_verify=appmod.JwtAuthenticator.verify_authorization_header
            verifications=[]
            async def changed_identity(auth,*args,**kwargs):
                principal=await original_verify(auth,*args,**kwargs)
                verifications.append(1)
                # Fault the verified owner's second identity projection only;
                # token verification remains real and no ACL is synthesized.
                if len(verifications)==2:
                    return dataclasses.replace(principal,subject_digest='f'*64)
                return principal
            monkeypatch.setattr(appmod.JwtAuthenticator,'verify_authorization_header',changed_identity)
        app=appmod.create_web_ceo_v2_app(bound)
        await service.start()
        try:
            async with app._app.router.lifespan_context(app._app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
                    token=old.fixture._read_token(rsa_key)
                    if case=='invalid_before_read':token='invalid'
                    response=await client.post('/v1/tools/executive_fabric',headers={'authorization':'Bearer '+token},json={'arguments':dict(view='result',root_job_id=root.job_id,job_id=job,attempt_id=attempt,result_envelope_digest=expected.result_digest)})
                    out=response.json()
                    if case=='authorized':
                        assert response.status_code==200,out
                        assert out['ok'] is True,out
                        assert out['server_version']=='1.2.0'
                        assert out['data']['content_complete'] is True
                        assert out['data']['generation']['state']=='SAME'
                        assert out['data']['content']['role_result']==expected.result_envelope['role_result']
                    else:
                        assert response.status_code==401,out
                        assert 'data' not in out and 'counts' not in out and 'content' not in out
                        if case in ('expiry_after_read','changed_principal'):assert getter_calls
                        else:assert not getter_calls
                    assert str(base.config.runtime_root) not in response.text
        finally:
            await readers.aclose();await service.close()
    asyncio.run(run())

@pytest.mark.parametrize('overflow',[False,True])
def test_actual_nested_mcp_transport_budget(settings,rsa_key,monkeypatch,overflow):
    """Transport-only discriminator preserves actual escaping and request ID."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    # The real MCP host performs its JWT verification; a fixed inner response
    # isolates the existing final escaping cap rather than acquiring fake data.
    text=('\\"\n漢'* (16000 if overflow else 1000))
    envelope=legacy.result_envelope('executive_fabric',mode=legacy.ServerMode.READONLY,generated_at='2026-09-21T17:00:00Z',data={'payload':text})
    envelope['server_version']='1.2.0'
    async def fixed_response(request):return JSONResponse(envelope)
    monkeypatch.setattr(appmod,'create_web_ceo_v2_app',lambda _:Starlette(routes=[Route('/v1/tools/executive_fabric',fixed_response,methods=['POST'])]))
    async def run():
        app=transport.build_web_ceo_v2_mcp_app(settings,audit_sink=old.Sink())
        async with app._app.router.lifespan_context(app._app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
                request_id='r'*60000
                response=await client.post('/mcp',headers=old.headers(old.fixture._read_token(rsa_key)),json={'jsonrpc':'2.0','id':request_id,'method':'tools/call','params':{'name':'executive_fabric','arguments':{'view':'roots'}}})
                assert response.status_code==200,response.text
                body=response.json();assert body['id']==request_id
                out=json.loads(body['result']['content'][0]['text'])
                assert len(response.content)<=legacy.MAX_RESPONSE_BYTES
                if overflow:assert out['ok'] is False and out['error']['code']=='output_too_large',out
                else:assert out==envelope
    asyncio.run(run())


def test_roots_use_accepted_bounded_discovery_without_creation_reads(tmp_path,monkeypatch):
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            def forbidden(*a,**kw):raise AssertionError('roots must not acquire creation events or result details')
            monkeypatch.setattr(er.BoundedRuntimeReadObservation,'get_creation_event_by_command_id',forbidden)
            monkeypatch.setattr(er.BoundedRuntimeReadObservation,'read_role_result_bounded',forbidden)
            monkeypatch.setattr(er.BoundedRuntimeReadObservation,'read_job_root_bounded',forbidden)
            out=await g.call('executive_fabric',{'view':'roots','limit':1})
            assert out['ok'] is True,out
            doc=out['data'];acquisition=doc['runtime']['acquisition']
            assert doc['schema']=='mastermind.fabric_job_root_list.v2'
            assert [row['job_id'] for row in doc['roots']]==[root.job_id]
            assert acquisition['generation']['state']=='SAME'
            assert acquisition['generation']['source_identity'] is not None
            assert acquisition['provenance']['state']=='PARTIAL'
            assert acquisition['snapshot_digest'] is not None
            assert len(calls)==1
            assert str(tmp_path) not in json.dumps(out)
    asyncio.run(run())


def test_result_cancellation_drains_same_executor_before_custody_close(tmp_path,monkeypatch):
    import threading
    from integrations.executive_mcp import adapter
    from tests.test_runtime_namespace_custody import writer_result
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            args,_=selection(s,root,nodes[-1]);entered=threading.Event();release=threading.Event()
            original=er.BoundedRuntimeReadObservation.read_role_result_bounded
            def blocked(observation,*a,**kw):
                value=original(observation,*a,**kw);entered.set();assert release.wait(10);return value
            monkeypatch.setattr(er.BoundedRuntimeReadObservation,'read_role_result_bounded',blocked)
            monkeypatch.setattr(adapter,'_CLOSE_TIMEOUT_SECONDS',.03)
            task=asyncio.create_task(g.call('executive_fabric',args))
            try:
                for _ in range(1000):
                    if entered.is_set():break
                    await asyncio.sleep(.001)
                assert entered.is_set()
                task.cancel();await asyncio.sleep(0);task.cancel()
                with pytest.raises(asyncio.CancelledError):await task
                assert writer_result(s._require_runtime())=='BLOCKED'
                with pytest.raises(legacy.GatewayError) as failure:await g.aclose()
                assert failure.value.code=='timeout'
                assert writer_result(s._require_runtime())=='BLOCKED'
            finally:
                release.set()
                for _ in range(1000):
                    if not g._read_attempts:break
                    await asyncio.sleep(.001)
                await g.aclose()
            assert writer_result(s._require_runtime())=='RESERVED'
    asyncio.run(run())


def test_foreign_finalized_receipt_refuses_at_consumer_boundary(tmp_path):
    async def run():
        async with owner(tmp_path) as (s,g,root,nodes,calls):
            args,_=selection(s,root,nodes[-1]);rt=s._namespace_custody.bound_runtime(s._require_runtime())
            with rt.observe_bounded_read() as first:
                first.read_role_result_bounded(root.job_id,args['job_id'],expected_attempt_id=args['attempt_id'],expected_result_envelope_digest=args['result_envelope_digest'])
            foreign=first.receipt
            class MixedObservation:
                def __init__(self):self.real=rt.observe_bounded_read()
                def __enter__(self):self.real.__enter__();return self
                def __exit__(self,*exc):return self.real.__exit__(*exc)
                def read_role_result_bounded(self,*a,**kw):return self.real.read_role_result_bounded(*a,**kw)
                @property
                def receipt(self):
                    assert self.real.receipt.source_identity!=foreign.source_identity
                    return foreign
            class MixedFacade:
                def observe_bounded_read(self):return MixedObservation()
            altered=gateway(tmp_path)
            altered.bind_fabric_source(bounded_runtime=MixedFacade,armed={},runtime_identity={})
            try:
                out=await altered.call('executive_fabric',args)
                assert out['ok'] is False and out['error']['code']=='backend_unavailable',out
                assert out['data'] is None
            finally:await altered.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('first_call',[('submit_ceo_intent',{}),('executive_fabric',{})])
def test_installed_v2_early_refusal_closes_binding_window(settings,tmp_path,first_call):
    async def run():
        runtime_root=tmp_path/'binding-runtime';runtime_root.mkdir()
        readers=web.WebCeoV2InstalledExecutiveReaders(repo_root=Path(settings.mastermind_root),macro_root=Path(settings.macro_root_flag),runtime_root=runtime_root)
        try:
            with pytest.raises(legacy.GatewayError):await readers.call(*first_call)
            with pytest.raises(legacy.GatewayError):readers.bind_fabric_source(bounded_runtime=lambda:None,armed={},runtime_identity={})
        finally:await readers.aclose()
    asyncio.run(run())
