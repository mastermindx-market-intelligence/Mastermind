import asyncio,json
import pytest

pytest.importorskip('jwt', reason='PyJWT unavailable in this environment')
from tests.mastermind_window_reader.test_read_resource import request,RESOURCE
from tests.mastermind_window_reader.test_existing_auth_composition import composition,token,NOW
from tests.mastermind_window_reader.test_live_window import Source,KEY,REF,build
from integrations.mastermind_window_reader.owner_read_resource import NativeOutputReadResource,from_existing_business_owner

class Owner:
    def __init__(self,s):self.s=s;self.reads=0;self.allowed=True
    async def authorize(self,*args):return ('fixture-scope',) if self.allowed else None
    async def read(self,ref):self.reads+=1;return await build(self.s).read()

def make(owner,**extra):
    return NativeOutputReadResource(owner=owner,resource=RESOURCE,source_ref=REF,
      allowed_origin='https://workspace.example',source_kind='live-window',**extra)

@pytest.mark.parametrize('state',['partial','completed'])
def test_resource_consumes_window_not_native_record(state):
    s=Source();s.publish('a','Current response',state);o=Owner(s);app=make(o)
    status,headers,body=asyncio.run(request(app))
    assert status==200 and o.reads==1
    d=json.loads(body);assert d['mode']=='observed-turn-window' and d['view']['items'][0]['text']=='Current response'
    assert 'no-store' in str(headers)

def test_scope_cannot_be_inferred_from_prefix():
    with pytest.raises(ValueError):NativeOutputReadResource(owner=Owner(Source()),resource=RESOURCE,source_ref=REF,allowed_origin='https://workspace.example')

def signed_window(key):
    _,state,auth,keys=composition(key);s=Source();r=build(s)
    async def access(principal,ref):
        state['accesses']+=1
        assert ref==REF
        return ('fixture-scope-epoch',) if state['grant'] and s.owner.check_grant(s.grant)==KEY else None
    async def read():state['reads']+=1;return await r.read()
    class Audit:
        def emit(self,event):state['audit'].append(event)
    app=from_existing_business_owner(authenticator=auth,policy=auth.policy,current_access=access,
      read_source=read,source_ref=REF,now=lambda:state['now'],allowed_origin='https://workspace.example',audit_sink=Audit(),source_kind='live-window')
    return app,state,s

def test_real_signature_and_actual_source_composed():
    from cryptography.hazmat.primitives.asymmetric import rsa
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    app,state,s=signed_window(key);s.publish('a','Nonterminal text')
    async def call():return await request(app,headers=[(b'host',b'workspace.example'),(b'authorization',('Bearer '+token(key)).encode())])
    status,_,body=asyncio.run(call());assert status==200 and not json.loads(body)['view']['terminal']
    s.owner.revoke_grant(s.grant)
    status,_,body=asyncio.run(call());assert status==401 and b'Nonterminal text' not in body and state['reads']==1


JOB='JOB-12'
ATT='ATT-'+'ab'*16
V1='mastermind.workspace.window_read_candidate.v1'
V2='mastermind.workspace.window_read_candidate.v2'


def test_default_live_window_remains_exact_v1():
    s=Source();s.publish('a','Current response');o=Owner(s);app=make(o)
    status,_,body=asyncio.run(request(app))
    d=json.loads(body)
    assert status==200 and set(d)=={'schema','selection_ref','mode','view'}
    assert d['schema']==V1 and 'observation_binding' not in d


def test_qualified_binding_emits_closed_v2_tuple_before_final_authorize():
    from integrations.mastermind_window_reader.owner_read_resource import ObservationBinding
    s=Source();s.publish('a','Bound response');o=Owner(s)
    app=make(o,observation_binding=ObservationBinding(job_id=JOB,attempt_id=ATT))
    status,_,body=asyncio.run(request(app))
    d=json.loads(body)
    assert status==200
    assert set(d)=={'schema','selection_ref','mode','view','observation_binding'}
    assert d['schema']==V2
    assert d['observation_binding']=={'job_id':JOB,'attempt_id':ATT}
    assert set(d['observation_binding'])=={'job_id','attempt_id'}
    assert d['view']['items'][0]['text']=='Bound response'
    assert o.reads==1


@pytest.mark.parametrize('kwargs', [
    {'job_id':'job','attempt_id':ATT},
    {'job_id':'JOB-','attempt_id':ATT},
    {'job_id':'JOB-1234567890','attempt_id':ATT},
    {'job_id':JOB,'attempt_id':'attempt'},
    {'job_id':JOB,'attempt_id':'ATT-'+'AB'*16},
    {'job_id':JOB,'attempt_id':'ATT-'+'a'*31},
    {'job_id':' JOB-12','attempt_id':ATT},
    {'job_id':JOB+' ','attempt_id':ATT},
])
def test_malformed_binding_fails_closed_never_v1(kwargs):
    from integrations.mastermind_window_reader.owner_read_resource import ObservationBinding
    s=Source();s.publish('a','secret-visible')
    with pytest.raises((TypeError,ValueError)):
        ObservationBinding(**kwargs)
    with pytest.raises((TypeError,ValueError)):
        make(Owner(s),observation_binding=kwargs)
    with pytest.raises((TypeError,ValueError)):
        make(Owner(s),observation_binding=object())


def test_dict_or_extra_binding_never_falls_back_to_v1():
    s=Source();s.publish('a','secret-visible')
    with pytest.raises((TypeError,ValueError)):
        make(Owner(s),observation_binding={'job_id':JOB,'attempt_id':ATT,'root':'JOB-1'})
    with pytest.raises((TypeError,ValueError)):
        make(Owner(s),observation_binding={'job_id':JOB})


def test_revocation_before_final_release_does_not_leak_tuple_or_content():
    from integrations.mastermind_window_reader.owner_read_resource import ObservationBinding
    s=Source();s.publish('a','Nonterminal secret');o=Owner(s)
    original=o.authorize
    async def authorize(*args):
        ticket=await original(*args)
        o.allowed=False
        return ticket
    o.authorize=authorize
    app=make(o,observation_binding=ObservationBinding(job_id=JOB,attempt_id=ATT))
    status,_,body=asyncio.run(request(app))
    assert status==403
    assert JOB.encode() not in body and ATT.encode() not in body
    assert b'Nonterminal secret' not in body
    assert b'observation_binding' not in body
