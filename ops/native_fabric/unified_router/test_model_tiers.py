"""Deterministic local-only regression tests against the installed-source candidate."""
import asyncio
import hashlib
import json
import math
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from ops.native_fabric.unified_router.routes import Route, RouteState, RateWindow
from ops.native_fabric.unified_router.model_policy import ModelPolicyState, normalized_usage, session_key
from ops.native_fabric.unified_router.gateway import Settings, create_app

TOKEN = 'fixture-token-not-a-secret-123456789'


def route(rid='r1', model='kimi', wire='openai', priority=5):
    return Route(rid, 'gateway', 'https://api.morphllm.com/v1', wire, (model,),
                 gateway_token_env='FABRIC_TEST_UPSTREAM', priority=priority,
                 rate_limit={'input': 100, 'output': 100})


def test_out_of_order_settlement_preserves_sibling():
    w=RateWindow();w.reserve('r1',80,10,request_id='slow',now=0)
    w.reserve('r1',5,50,request_id='fast',now=1)
    w.settle('r1',2,3,7,request_id='fast')
    assert w.totals('r1',2)==(83,17)
    assert 'slow' in w._pending and 'fast' not in w._pending
    w.settle('r1',3,90,20,request_id='slow')
    assert w.totals('r1',3)==(93,27)


def test_active_reservations_do_not_expire_at_sixty_seconds():
    w=RateWindow();w.reserve('r1',90,90,request_id='long',now=0)
    assert w.totals('r1',999)==(90,90)
    assert w.wait_for(route(),999,20,20)>0
    assert w.release('long') and not w.release('long')
    assert w.totals('r1',1000)==(0,0)


def test_shared_resource_and_independent_subscriptions():
    w=RateWindow();w.reserve('alias1',90,1,request_id='a',resource_id='subscription1',now=0)
    assert w.wait_for(route('alias2'),1,20,1,resource_id='subscription1')>0
    assert w.wait_for(route('alias2'),1,20,1,resource_id='subscription2')==0
    w.settle('alias1',2,75,3,request_id='a')
    assert w.totals('subscription1',2)==(75,3)


def test_oversized_probe_is_not_an_unlimited_parallel_bypass():
    w=RateWindow();r=route()
    assert math.isinf(w.wait_for(r,0,1000,1))
    assert w.wait_for(r,0,1000,1,allow_oversize=True)==0
    w.reserve('r1',1000,1,request_id='probe',now=0)
    assert w.wait_for(r,0,1000,1,allow_oversize=True)>0
    w.settle('r1',5,1000,1,request_id='probe')
    assert w.wait_for(r,64,1000,1,allow_oversize=True)>0
    assert w.wait_for(r,65,1000,1,allow_oversize=True)==0


def test_duplicate_and_ambiguous_settlement_refuse():
    w=RateWindow();w.reserve('r1',1,2,request_id='a',now=0)
    with pytest.raises(ValueError):w.reserve('r1',1,2,request_id='a',now=0)
    w.reserve('r1',3,4,request_id='b',now=0)
    with pytest.raises(ValueError):w.settle('r1',1,1,1)
    assert len(w._pending)==2


@pytest.mark.parametrize('value',[True,-1,float('inf'),float('nan')])
def test_invalid_estimates_refuse(value):
    with pytest.raises(ValueError):RateWindow().reserve('r1',value,1)


def test_output_and_input_limits_are_independent():
    w=RateWindow();w.reserve('r1',1,95,request_id='a',now=0)
    assert w.wait_for(route(),0,1,10)>0
    assert w.wait_for(route(),0,95,1)==0


def test_cache_normalization_and_malformed_usage():
    usage={'prompt_tokens':90000,'completion_tokens':500,'prompt_tokens_details':{'cached_tokens':88000}}
    assert normalized_usage(usage,'openai')=={'input':90000,'uncached_input':2000,'cached_input':88000,'output':500}
    assert normalized_usage({'input_tokens':30,'cache_read_input_tokens':70,'cache_creation_input_tokens':10,'output_tokens':4},'anthropic')=={'input':110,'uncached_input':40,'cached_input':70,'output':4}
    assert normalized_usage({'prompt_tokens':10,'completion_tokens':1,'prompt_tokens_details':{'cached_tokens':11}},'openai') is None
    assert normalized_usage({'prompt_tokens':True,'completion_tokens':1},'openai') is None


def test_stable_session_headers_and_no_anonymous_affinity():
    assert session_key({}, {}) is None
    assert session_key({'x-session-id':'thread-1'}, {})==hashlib.sha256(b'thread-1').hexdigest()
    assert session_key({}, {'metadata':{'session_id':'thread-1'}})==session_key({'x-session-id':'thread-1'}, {})
    assert session_key({'x-session-id':'thread-2'}, {})!=session_key({'x-session-id':'thread-1'}, {})


def settings(tmp_path, *, wait=0.02, metered=False):
    rs=(replace(route('morph','kimi'),rate_limit=()),
        replace(route('glm','glm','anthropic'),rate_limit=()),
        replace(route('paid','kimi',priority=40),rate_limit=()))
    return Settings(TOKEN,tmp_path, routes=rs, aliases=(('fabric/balanced',('kimi','glm')),),
        capacity_wait_s=wait,free_hold_s=0,model_routing={
            'groups':{'fabric/balanced':{'weights':{'kimi':1000,'glm':1},
                'routes':{'kimi':['morph'],'glm':['glm']}}},
            'resources':{'morph':{'key':'sub-1-kimi','input_tpm':24290,'output_tpm':6162,
                'input_basis':'uncached','max_inflight':2,'allow_one_oversize':True}},
            'metered_routes':['paid'],'allow_metered_fallback':metered,'affinity_wait_s':0})


def response_for(req, *, streaming=False, cached=0, inp=10, out=5):
    payload=json.loads(req.content)
    if req.url.path.endswith('/v1/messages'):
        data={'id':'msg-native','type':'message','role':'assistant','model':'glm','content':[{'type':'text','text':'OK'}],
            'stop_reason':'end_turn','usage':{'input_tokens':inp,'output_tokens':out}}
        return httpx.Response(200,json=data)
    usage={'prompt_tokens':inp,'completion_tokens':out,'prompt_tokens_details':{'cached_tokens':cached}}
    if not streaming:
        return httpx.Response(200,json={'id':'chat-fixture','model':payload['model'],
            'choices':[{'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}],'usage':usage})
    rows=[{'model':payload['model'],'choices':[{'delta':{'content':'OK'},'finish_reason':None}]},
          {'model':payload['model'],'choices':[{'delta':{},'finish_reason':'stop'}]},
          {'model':payload['model'],'choices':[],'usage':usage}]
    text=''.join('data: '+json.dumps(r)+'\n\n' for r in rows)+'data: [DONE]\n\n'
    return httpx.Response(200,content=text,headers={'content-type':'text/event-stream'})


async def run_request(cfg, handler, *, model='fabric/balanced', stream=False, setup=None, payload_extra=None):
    app=create_app(cfg,transport=httpx.MockTransport(handler))
    if setup:setup(app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1111)),base_url='http://router') as client:
            payload={'model':model,'messages':[{'role':'user','content':'test'}],'max_tokens':20,'stream':stream}
            payload.update(payload_extra or {})
            response=await client.post('/v1/messages',headers={'authorization':'Bearer '+TOKEN,'x-session-id':'test-thread'},json=payload)
            return response, app


def prefer_kimi(app):
    key=hashlib.sha256(b'test-thread').hexdigest()
    app.state.model_policy.sticky[('fabric/balanced',key)]=('kimi','morph',time.monotonic())


def test_throttled_kimi_spills_to_glm_without_paid_route(tmp_path, monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only')
    calls=[]
    def handler(req):
        model=json.loads(req.content)['model'];calls.append(model)
        if model=='kimi':return httpx.Response(429,json={'error':{'message':'uncached input limit is 20000 tokens per minute'}},headers={'retry-after':'60'})
        return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=prefer_kimi))
    assert response.status_code==200 and calls==['kimi','glm']
    assert response.headers['x-fabric-resolved-model']=='glm'
    assert not app.state.model_policy.active and not app.state.router_state.rate_window._pending
    assert app.state.model_policy.resources['morph']['input_tpm']==20000


def test_known_cooling_kimi_is_not_sent_or_waited_on(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def setup(app):
        prefer_kimi(app);app.state.router_state.routes.cooldown_until['morph']=time.monotonic()+3600
    def handler(req):calls.append(json.loads(req.content)['model']);return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=setup))
    assert response.status_code==200 and calls==['glm']


def test_exact_model_never_silently_changes_or_uses_paid_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def setup(app):app.state.router_state.routes.cooldown_until['morph']=time.monotonic()+3600
    def handler(req):calls.append(req);return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path,wait=0.01),handler,model='kimi',setup=setup))
    assert response.status_code==503 and calls==[]
    assert not app.state.model_policy.waiters


@pytest.mark.parametrize('status',[401,403,500])
def test_upstream_denial_or_ambiguous_failure_is_not_replayed(tmp_path,monkeypatch,status):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def handler(req):calls.append(req);return httpx.Response(status,json={'error':{'message':'fixture'}})
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=prefer_kimi))
    assert response.status_code==(502 if status==500 else status) and len(calls)==1
    assert app.state.router_state.served==0


@pytest.mark.parametrize('status',[502,503,504,529])
def test_provider_capacity_failure_before_output_uses_bounded_safe_fallback(tmp_path,monkeypatch,status):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(status,json={'error':{'message':'fixture'}}) if len(calls)==1 else response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=prefer_kimi))
    assert response.status_code==200 and len(calls)==2
    assert response.headers['x-fabric-resolved-model']=='glm'


@pytest.mark.parametrize('status',[502,503,504,529])
def test_provider_side_effect_tools_never_replay_on_capacity_error(tmp_path,monkeypatch,status):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def handler(req):calls.append(req);return httpx.Response(status,json={'error':{'message':'fixture'}})
    response,app=asyncio.run(run_request(settings(tmp_path),handler,setup=prefer_kimi,
        payload_extra={'mcp_servers':[{'type':'url','name':'fixture','url':'https://fixture.example/mcp'}]}))
    assert response.status_code==status and len(calls)==1


def test_stream_cache_usage_is_metered_as_uncached(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');seen=[]
    def handler(req):
        seen.append(json.loads(req.content))
        return response_for(req,streaming=True,cached=88000,inp=90000,out=500)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,stream=True,model='kimi'))
    assert response.status_code==200 and 'message_stop' in response.text
    assert seen[0]['stream_options']=={'include_usage':True}
    assert app.state.router_state.usage['morph']['uncached_input']==2000
    assert app.state.router_state.rate_window.totals('sub-1-kimi',time.monotonic())==(2000,500)
    assert app.state.router_state.served==1


def test_partial_stream_is_not_success_or_replayed(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(200,content='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',headers={'content-type':'text/event-stream'})
    response,app=asyncio.run(run_request(settings(tmp_path),handler,stream=True,setup=prefer_kimi))
    assert 'FABRIC_STREAM_INCOMPLETE' in response.text and 'message_stop' not in response.text
    assert len(calls)==1 and app.state.router_state.served==0
    assert not app.state.model_policy.active and not app.state.router_state.rate_window._pending


def test_rich_input_not_silently_degraded_to_text_tier(tmp_path,monkeypatch):
    monkeypatch.setenv('FABRIC_TEST_UPSTREAM','test-only');calls=[]
    def handler(req):calls.append(req);return response_for(req)
    response,app=asyncio.run(run_request(settings(tmp_path),handler,payload_extra={
        'messages':[{'role':'user','content':[{'type':'image','source':{'type':'base64','data':'fixture'}}]}]}))
    assert response.status_code==503 and calls==[]


def test_long_retry_after_not_capped_to_five_minutes():
    s=RouteState();now=time.monotonic();s.record_failure('r','quota',now=now,cooldown_s=7200,escalate=False)
    assert s.cooldown_until['r']==now+7200
    s.record_success('r')
    assert s.cooldown_until['r']==now+7200
