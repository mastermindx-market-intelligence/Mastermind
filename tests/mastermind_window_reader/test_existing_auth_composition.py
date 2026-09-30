"""Exact incumbent JWT/claims source + ephemeral synthetic key/claims.

These are actual RS256 signature checks, NOT registered-client/OAuth or network
proof. Neither private fixture keys nor signed tokens are written to artifacts.
"""
import asyncio,copy,dataclasses,hashlib,json
from pathlib import Path
import pytest

jwt = pytest.importorskip('jwt', reason='PyJWT unavailable in this environment')
from cryptography.hazmat.primitives.asymmetric import rsa
from integrations.business_mcp_auth.contracts import load_resource_policy,subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_window_reader.owner_read_resource import from_existing_business_owner,CONTENT_SCOPE
from tests.mastermind_window_reader.test_read_resource import request,LANE,RESOURCE,RAW

ROOT=Path(__file__).resolve().parents[2]
NOW=1789550000;ISSUER='https://fixture-issuer.example';SUB='fixture-authorized-person'

@pytest.fixture(scope='module')
def signing_key():return rsa.generate_private_key(public_exponent=65537,key_size=2048)

class KeySource:
    def __init__(self,key):
        self.public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));self.calls=0
    async def key_for(self,kid):
        self.calls+=1
        if kid!='fixture-key':raise ValueError('unknown fixture key')
        return self.public

def composition(key,*,grant=True,after_grant=None,after_read=None,scope=CONTENT_SCOPE):
    policy=load_resource_policy(dict(schema='mastermind.business_mcp_auth_policy.v1',policy_id='workspace-fixture-read',
      resource=RESOURCE,resource_metadata_url='https://workspace.example/.well-known/oauth-protected-resource',
      issuer=ISSUER,authorization_servers=[ISSUER],jwks_uri=ISSUER+'/jwks',required_scopes=[scope],
      allowed_subject_digests=[subject_digest(issuer=ISSUER,subject=SUB)],allowed_algorithms=['RS256'],
      clock_skew_seconds=0,max_token_lifetime_seconds=900,jwks_cache_ttl_seconds=60,
      unknown_kid_refresh_cooldown_seconds=1,fetch_failure_backoff_seconds=1))
    keys=KeySource(key);auth=JwtAuthenticator(policy=policy,jwks_cache=keys)
    state=dict(now=NOW,grant=grant,reads=0,accesses=0,grant_epoch='fixture-grant-v1')
    async def access(principal,ref):
        assert ref==LANE and principal.subject_digest==policy.allowed_subject_digests[0]
        state['accesses']+=1
        if after_grant:after_grant(state,auth)
        return (state['grant_epoch'],) if state['grant'] else None
    async def read():
        state['reads']+=1
        if after_read:after_read(state,auth)
        return RAW
    state['audit']=[]
    class FixtureAudit:
        def emit(self,event):
            if state.get('audit_failed'):raise RuntimeError('fixture audit unavailable')
            state['audit'].append(event)
    app=from_existing_business_owner(authenticator=auth,policy=policy,current_access=access,read_source=read,
          source_ref=LANE,now=lambda:state['now'],allowed_origin='https://workspace.example',audit_sink=FixtureAudit())
    return app,state,auth,keys

def token(key,**overrides):
    claims=dict(iss=ISSUER,sub=SUB,aud=RESOURCE,iat=NOW-5,exp=NOW+600,
                scope=CONTENT_SCOPE,client_id='fixture-client',jti='fixture-request')
    claims.update(overrides)
    return jwt.encode(claims,key,algorithm='RS256',headers={'kid':'fixture-key','typ':'at+jwt'})

def run(app,tok):
    return asyncio.run(request(app,headers=[(b'host',b'workspace.example'),(b'authorization',('Bearer '+tok).encode())]))

def test_exact_three_upstream_files_are_unmodified():
    expected={'contracts.py':'374e55b3f294885d637b1a1fa1e8be47c6aefeab','claims.py':'2f1aaf053a136629834cf66c11491b0a7194aee2','jwt_verifier.py':'32d72cb27d4fbacc6a19614679e4a33c13c205e7'}
    for name,want in expected.items():
        b=(ROOT/'integrations/business_mcp_auth'/name).read_bytes()
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==want

def test_real_signed_fixture_reaches_fixed_source_through_existing_auth(signing_key):
    a,s,_,keys=composition(signing_key);t=token(signing_key);status,h,raw=run(a,t)
    assert status==200 and s['reads']==1 and s['accesses']==2 and keys.calls==2
    assert json.loads(raw)['view']['items'][0]['text']==json.loads(RAW)['items'][0]['text']
    assert t.encode() not in raw and SUB.encode() not in raw

@pytest.mark.parametrize('changes',[
 {'sub':'somebody-else'},{'aud':'https://other.example/resource'}, {'iss':'https://wrong.example'},
 {'scope':'mastermind.steward.read'}, {'scope':CONTENT_SCOPE+' mastermind.executive.write'},
 {'exp':NOW-1,'iat':NOW-100}, {'iat':NOW+10}, {'exp':NOW+2000},
 {'aud':[RESOURCE]},{'iat':True}, {'scope':CONTENT_SCOPE+' '+CONTENT_SCOPE}
])
def test_signature_valid_but_policy_invalid_never_reads(signing_key,changes):
    a,s,_,_=composition(signing_key);status,_,body=run(a,token(signing_key,**changes))
    assert status==401 and s['reads']==0 and b'SHIP LOOP' not in body

def test_wrong_signature_never_reaches_target_grant_or_source(signing_key):
    a,s,_,_=composition(signing_key);wrong=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    status,_,_=run(a,token(wrong));assert status==401 and s['reads']==0 and s['accesses']==0

def test_valid_resource_token_is_not_current_target_permission(signing_key):
    a,s,_,_=composition(signing_key,grant=False)
    assert run(a,token(signing_key))[0]==401 and s['reads']==0

def test_current_grant_revocation_after_source_read_withholds_response(signing_key):
    a,s,_,_=composition(signing_key,after_read=lambda s,a:s.update(grant=False))
    status,_,body=run(a,token(signing_key));assert status==403 and s['reads']==1 and b'SHIP LOOP' not in body

def test_token_expiration_during_source_read_withholds_response(signing_key):
    a,s,_,_=composition(signing_key,after_read=lambda s,a:s.update(now=NOW+601))
    assert run(a,token(signing_key))[0]==403 and s['reads']==1

def test_token_expiration_during_last_grant_await_withholds_response(signing_key):
    def step(s,a):
        if s['accesses']==2:s['now']=NOW+601
    a,s,_,_=composition(signing_key,after_grant=step)
    status,_,body=run(a,token(signing_key));assert status==403 and b'SHIP LOOP' not in body

def test_policy_replacement_during_grant_await_withholds(signing_key):
    def step(s,a):a._policy=dataclasses.replace(a.policy,policy_id='different-policy')
    a,s,_,_=composition(signing_key,after_grant=step)
    assert run(a,token(signing_key))[0]==401 and s['reads']==0

def test_grant_revision_changed_during_source_work_withholds(signing_key):
    a,s,_,_=composition(signing_key,after_read=lambda s,a:s.update(grant_epoch='different-epoch'))
    assert run(a,token(signing_key))[0]==403

def test_non_authorizing_offline_scope_does_not_add_control(signing_key):
    a,s,_,_=composition(signing_key)
    status,_,raw=run(a,token(signing_key,scope=CONTENT_SCOPE+' offline_access'))
    assert status==200 and json.loads(raw)['view']['capabilities']['provider_control'] is False

def test_existing_steward_scope_cannot_be_reused_as_content_enrollment(signing_key):
    with pytest.raises(ValueError,match='separate accepted content scope'):
        composition(signing_key,scope='mastermind.steward.read')

def test_no_audit_owner_cannot_construct_the_production_composition(signing_key):
    # Existing binding data is real fixture data; only the required audit owner
    # is deliberately absent. No new audit store is allowed as a fallback.
    a,s,auth,keys=composition(signing_key)
    with pytest.raises(TypeError):
        from_existing_business_owner(authenticator=auth,policy=auth.policy,current_access=lambda p,r:None,
          read_source=lambda:RAW,source_ref=LANE,now=lambda:NOW,allowed_origin='https://workspace.example')


def test_existing_audit_failure_refuses_before_any_source_read(signing_key):
    a,s,_,_=composition(signing_key);s['audit_failed']=True
    status,_,raw=run(a,token(signing_key));assert status==401 and s['reads']==0 and b'SHIP LOOP' not in raw

def test_audit_records_are_closed_and_contain_no_token_or_content(signing_key):
    a,s,_,_=composition(signing_key);run(a,token(signing_key))
    assert len(s['audit'])==2
    for event in s['audit']:
        d=dataclasses.asdict(event)
        assert set(d)=={'schema','policy_id','code','accepted'}
        assert d['accepted'] is True and d['code']=='accepted'
        assert 'token' not in json.dumps(d) and 'SHIP LOOP' not in json.dumps(d)
