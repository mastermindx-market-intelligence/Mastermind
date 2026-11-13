import asyncio
import dataclasses
import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest

from ops.native_fabric.unified_router import gateway
from ops.native_fabric.unified_router.config_refresh import ConfigRefresh, read_document
from ops.native_fabric.unified_router.model_policy import ModelPolicyState, prefix_signature
from ops.native_fabric.unified_router.routes import RateWindow, RouteState
from ops.native_fabric.unified_router.test_model_tiers import (
    TOKEN, settings, route, response_for, run_request, prefer_kimi,
)


def document_from(cfg):
    rows=[]
    for r in cfg.routes:
        row=dataclasses.asdict(r);row['rate_limit']=dict(row['rate_limit']);row['upstream_model']=dict(row['upstream_model'])
        rows.append(row)
    return {'routes':rows,'aliases':dict(cfg.aliases),'model_routing':cfg.model_routing}


def test_hot_alias_update_preserves_pending_reservation_and_cache(tmp_path):
    cfg=settings(tmp_path);p=tmp_path/'routes.json';doc=document_from(cfg);p.write_text(json.dumps(doc));p.chmod(0o600)
    _,digest=read_document(p);cfg=dataclasses.replace(cfg,routes_path=p,routes_digest=digest)
    app=gateway.create_app(cfg);state=app.state.model_policy
    payload={'messages':[{'role':'user','content':'test'}],'max_tokens':100}
    admission=state.begin(cfg.routes[0],'kimi',payload,'session','fabric/balanced',time.monotonic())
    state.sticky[('fabric/balanced','session')]=('kimi','morph',time.monotonic())
    doc['model_routing']['groups']['fabric/balanced']['weights']['glm']=10
    p.write_text(json.dumps(doc));p.chmod(0o600)
    assert app.state.config_refresh.refresh(app,gateway._routes_from_document,force=True)
    assert app.state.model_policy is state
    assert admission.token in state.active and admission.token in state.window._pending
    assert state.sticky[('fabric/balanced','session')][0]=='kimi'
    assert state.groups['fabric/balanced']['weights']['glm']==10
    state.finish(admission,no_send=True)


def test_invalid_config_and_active_identity_change_fail_closed(tmp_path):
    cfg=settings(tmp_path);p=tmp_path/'routes.json';doc=document_from(cfg);p.write_text(json.dumps(doc));p.chmod(0o600)
    _,digest=read_document(p);app=gateway.create_app(dataclasses.replace(cfg,routes_path=p,routes_digest=digest))
    state=app.state.model_policy;admission=state.begin(cfg.routes[0],'kimi',{},None,'model:kimi',time.monotonic())
    doc['routes'][0]['base_url']='https://other.example'
    p.write_text(json.dumps(doc));assert not app.state.config_refresh.refresh(app,gateway._routes_from_document,force=True)
    assert app.state.settings.routes[0].base_url==cfg.routes[0].base_url
    assert admission.token in state.active
    p.write_text('{"routes": []');assert not app.state.config_refresh.refresh(app,gateway._routes_from_document,force=True)
    state.finish(admission,no_send=True)


def test_duplicate_config_keys_and_symlink_refused(tmp_path):
    p=tmp_path/'r.json';p.write_text('{"routes":[],"routes":[]}');p.chmod(0o600)
    with pytest.raises(ValueError):read_document(p)
    q=tmp_path/'link';q.symlink_to(p)
    with pytest.raises(OSError):read_document(q)


def test_nested_rich_input_refuses_without_send(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','fixture');calls=[]
    def handler(req):calls.append(req);return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,payload_extra={
        'messages':[{'role':'user','content':[{'type':'tool_result','content':[{'type':'image','source':{'type':'base64','data':'abc'}}]}]}]}))
    assert response.status_code==503 and not calls


def test_successful_session_affinity_then_spillover(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','fixture')
    async def run():
        app=gateway.create_app(settings(tmp_path),transport=httpx.MockTransport(response_for));prefer_kimi(app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://router') as client:
                body={'model':'fabric/balanced','messages':[{'role':'user','content':'test'}],'max_tokens':20}
                headers={'authorization':'Bearer '+TOKEN,'x-session-id':'test-thread'}
                first=await client.post('/v1/messages',json=body,headers=headers)
                second=await client.post('/v1/messages',json=body,headers=headers)
                assert first.headers['x-fabric-resolved-model']==second.headers['x-fabric-resolved-model']=='kimi'
                app.state.router_state.routes.cooldown_until['morph']=time.monotonic()+60
                third=await client.post('/v1/messages',json=body,headers=headers)
                assert third.headers['x-fabric-resolved-model']=='glm'
                assert app.state.model_policy.counters['model_spillovers']==1
                assert not app.state.model_policy.active
    asyncio.run(run())


def test_original_observer_still_consumes_actual_stream(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','fixture')
    from ops.native_fabric.unified_router.capacity_fabric_observer import instrument_app
    async def run():
        app=gateway.create_app(settings(tmp_path),transport=httpx.MockTransport(lambda req:response_for(req,streaming=True,cached=80,inp=100,out=5)))
        instrument_app(app,gateway)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://router') as client:
                response=await client.post('/v1/messages',json={'model':'kimi','messages':[{'role':'user','content':'test'}],'stream':True,'max_tokens':20},headers={'authorization':'Bearer '+TOKEN})
                assert response.status_code==200 and 'message_stop' in response.text
                snapshot=app.state.capacity_observer.snapshot(app)
                assert snapshot['totals']['completed']==1 and snapshot['totals']['observer_errors']==0
                assert app.state.router_state.usage['morph']['uncached_input']==20
    asyncio.run(run())


def test_queue_bound_and_cleanup(tmp_path):
    cfg=settings(tmp_path);state=ModelPolicyState(cfg.routes,cfg.aliases,cfg.model_routing,RateWindow(),RouteState())
    for i in range(8):assert state.join_wait(str(i),'same-session')
    assert not state.join_wait('overflow','same-session')
    assert state.join_wait('other','other-session')
    assert state.counters['queue_refused']==1


def test_cancellation_releases_exact_admission(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','fixture')
    async def run():
        entered=asyncio.Event()
        async def handler(req):entered.set();await asyncio.sleep(100);return response_for(req)
        app=gateway.create_app(settings(tmp_path),transport=httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://router') as client:
                task=asyncio.create_task(client.post('/v1/messages',json={'model':'kimi','messages':[],'max_tokens':20},headers={'authorization':'Bearer '+TOKEN}))
                await entered.wait();assert len(app.state.model_policy.active)==1
                task.cancel()
                with pytest.raises(asyncio.CancelledError):await task
                assert not app.state.model_policy.active and not app.state.router_state.rate_window._pending
                assert app.state.model_policy.counters['completed']==0
    asyncio.run(run())


def test_warm_prefix_is_only_same_model_route_and_session(tmp_path):
    cfg=settings(tmp_path);state=ModelPolicyState(cfg.routes,cfg.aliases,cfg.model_routing,RateWindow(),RouteState())
    body={'system':'shared instructions '*1000,'messages':[{'role':'user','content':'one'}],'max_tokens':20}
    now=time.monotonic();cold=state.estimate(cfg.routes[0],'kimi',body,'s',now)[0]
    admission=state.begin(cfg.routes[0],'kimi',body,'s','model:kimi',now)
    state.observe_usage(admission,{'prompt_tokens':1000,'completion_tokens':5},'openai')
    state.finish(admission,success=True)
    assert state.estimate(cfg.routes[0],'kimi',body,'s',time.monotonic())[0] < cold
    assert state.estimate(cfg.routes[0],'kimi',body,'different',time.monotonic())[0] == cold
    assert state.estimate(cfg.routes[0],'different-model',body,'s',time.monotonic())[0] == cold


@pytest.mark.parametrize('value',[True,0,-1,0.5,1000])
def test_invalid_inflight_cap_refuses(tmp_path,value):
    cfg=settings(tmp_path);cfg.model_routing['resources']['morph']['max_inflight']=value
    with pytest.raises(ValueError):gateway.create_app(cfg)


def test_actual_sdk_and_fabric_session_identity_conventions():
    from ops.native_fabric.unified_router.model_policy import session_key
    sid='abcdef01-2345-6789-abcd-0123456789ab'
    expected=session_key({'x-fabric-session-id':sid},{})
    assert session_key({}, {'metadata':{'fabric':{'session_id':sid}}})==expected
    assert session_key({}, {'metadata':{'user_id':json.dumps({'session_id':sid,'user_id':'ignored'})}})==expected
    assert session_key({}, {'metadata':{'user_id':'user_ignored_session_'+sid}})==expected
    assert session_key({}, {'metadata':{'user_id':'shared-user-not-a-conversation'}}) is None


def test_auto_respects_declared_complexity_without_inventing_frontier_spend():
    aliases=(('auto',('deepseek',)),('fabric/balanced',('glm','kimi')))
    assert gateway._model_candidates({'model':'auto','metadata':{'task_complexity':'C2_COMPLEX_BOUNDED'}},aliases)==[('glm','fabric/balanced'),('kimi','fabric/balanced')]
    assert gateway._model_candidates({'model':'auto'},aliases)==[('deepseek','auto')]
    with pytest.raises(gateway.WireTranslationError,match='FABRIC_EXPLICIT_FRONTIER_REQUIRED'):
        gateway._model_candidates({'model':'auto','metadata':{'task_complexity':'C3_FRONTIER_JUDGMENT'}},aliases)


def test_model_policy_cannot_disappear_during_hot_reload(tmp_path):
    cfg=settings(tmp_path);cfg.model_routing['version']='model-tier-v1-20261111'
    p=tmp_path/'routes.json';doc=document_from(cfg);p.write_text(json.dumps(doc));p.chmod(0o600)
    _,digest=read_document(p);app=gateway.create_app(dataclasses.replace(cfg,routes_path=p,routes_digest=digest))
    del doc['model_routing'];p.write_text(json.dumps(doc))
    assert not app.state.config_refresh.refresh(app,gateway._routes_from_document,force=True)
    assert app.state.model_policy.policy['version']=='model-tier-v1-20261111'


def test_known_included_exact_pin_never_uses_unknown_funding_route(tmp_path):
    cfg=settings(tmp_path);cfg.model_routing['exact_route_allowlists']={'kimi':['morph']}
    cfg=dataclasses.replace(cfg,routes=(*cfg.routes,dataclasses.replace(route('unknown','kimi'),rate_limit=())))
    state=ModelPolicyState(cfg.routes,cfg.aliases,cfg.model_routing,RateWindow(),RouteState())
    state.route_state.cooldown_until['morph']=time.monotonic()+60
    ladder,_,_,_=state.plan([('kimi','')],{},None,'fixture',time.monotonic())
    assert ladder==[]


def test_local_credential_permission_denial_is_not_rerouted(tmp_path,monkeypatch):
    def denied(*args):raise PermissionError('fixture')
    monkeypatch.setattr(gateway,'_route_authorization',denied)
    calls=[]
    def handler(req):calls.append(req);return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=prefer_kimi))
    assert response.status_code==403 and not calls
    assert not app.state.model_policy.active and not app.state.router_state.rate_window._pending


def test_internal_routing_metadata_is_not_forwarded_as_provider_metadata(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','fixture');seen=[]
    def setup(app):app.state.router_state.routes.cooldown_until['morph']=time.monotonic()+100
    def handler(req):seen.append(json.loads(req.content));return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=setup,payload_extra={
        'metadata':{'fabric':{'session_id':'local-session'},'task_complexity':'C2_COMPLEX_BOUNDED','user_id':'valid-provider-user'}}))
    assert response.status_code==200
    assert seen[0]['metadata']=={'user_id':'valid-provider-user'}
