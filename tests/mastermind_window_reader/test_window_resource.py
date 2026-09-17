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
