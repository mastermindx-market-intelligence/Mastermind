"""Offline consumer proof: real JWT verifier/grant owner, synthetic item resolver.

No actual F10 context, producer descriptor table, current receipt or deployment
is qualified here. Ephemeral RSA is test-only, never a provider credential.
"""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from integrations.business_mcp_auth.contracts import load_resource_policy, subject_digest
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.research_read_mcp.runtime import CurrentGrantOwner, Deployment
from integrations.research_read_mcp.contracts import ContractViolation
from integrations.research_read_mcp.evidence_http import EvidenceHttpApp, ORIGIN, PREFIX

ISSUER = 'https://issuer.example.invalid'
RESOURCE = 'https://research.example.invalid/mcp/research/v1'
ITEM = 'rvitem.v1.' + 'a' * 64
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key()))
JWK.update(kid='offline', alg='RS256', use='sig')

class Audit:
    def __init__(self):self.events=[];self.fail_on=None
    def emit(self,event):
        self.events.append(event)
        if len(self.events)==self.fail_on:raise RuntimeError('PRIVATE_AUDIT_FAILURE')

class Keys:
    async def key_for(self, kid):
        assert kid == 'offline'
        return JWK

@pytest.fixture
def rig(tmp_path):
    clock = [1700000000]
    digest = subject_digest(issuer=ISSUER, subject='reader')
    policy = load_resource_policy(dict(schema='mastermind.business_mcp_auth_policy.v1',
        policy_id='fixture.research.read', resource=RESOURCE,
        resource_metadata_url='https://research.example.invalid/.well-known/oauth-protected-resource/mcp/research/v1',
        issuer=ISSUER, authorization_servers=[ISSUER], jwks_uri=ISSUER+'/jwks.json',
        required_scopes=['mastermind.research.read'], allowed_subject_digests=[digest],
        allowed_algorithms=['RS256'], clock_skew_seconds=0, max_token_lifetime_seconds=3600,
        jwks_cache_ttl_seconds=60, unknown_kid_refresh_cooldown_seconds=1, fetch_failure_backoff_seconds=1))
    path = tmp_path/'grant.json'
    def write(classes=None, quote=1000, expires=None, grant_id='fixture.grant'):
        path.write_text(json.dumps(dict(schema='mastermind.research_read_mcp.grant.v1',
            grant_id=grant_id, policy_id=policy.policy_id, entries=[dict(subject_digest=digest,
            content_classes=classes if classes is not None else ['catalog_metadata','evidence_passage'],
            quote_limit_chars=quote, expires_at=expires or clock[0]+1000)])))
        path.chmod(0o600)
    write()
    deployment=Deployment('a','a'*40,'b'*40,'b','c'*40,'d'*40,'127.0.0.1',9999,
        '/not-used/policy',str(path),policy.policy_id,('mcp.mastermind-x.com',),())
    owner=CurrentGrantOwner(deployment,clock=lambda:clock[0],owner_uid=os.getuid())
    calls=[]
    value=dict(id=ITEM,title='Source passage',text='  文本 <script>alert(1)</script>\n',
               url=ORIGIN+PREFIX+ITEM,metadata={'coverage':'COMPLETE_BOUNDED_ITEM'})
    hook=[None]
    async def resolve(**kwargs):
        calls.append(kwargs)
        if hook[0]: hook[0]()
        return value
    def token(**changes):
        claims=dict(iss=ISSUER,sub='reader',aud=RESOURCE,iat=clock[0]-10,exp=clock[0]+600,
                    scope='mastermind.research.read',client_id='fixture-client')
        claims.update(changes)
        return jwt.encode(claims,KEY,algorithm='RS256',headers={'kid':'offline'})
    audit=Audit()
    app=EvidenceHttpApp(policy=policy,authenticator=JwtAuthenticator(policy=policy,jwks_cache=Keys()),
        grant_owner=owner,context_builder=lambda e:SimpleNamespace(principal_id=e.subject_digest),
        item_resolver=resolve,clock=lambda:clock[0],audit_sink=audit)
    def request(*, changes=None, headers=None, auth=True, body=b'', token_value=None):
        scope=dict(type='http',method='GET',scheme='https',path=PREFIX+ITEM,
                   raw_path=(PREFIX+ITEM).encode(),query_string=b'',
                   headers=[(b'host',b'mcp.mastermind-x.com'),(b'accept',b'application/json')])
        if auth: scope['headers'].append((b'authorization',('Bearer '+(token_value or token())).encode()))
        if changes: scope.update(changes)
        if headers: scope['headers']+=headers
        sent=[]
        async def receive():return dict(type='http.request',body=body,more_body=False)
        async def send(message):sent.append(message)
        asyncio.run(app(scope,receive,send))
        return sent[0]['status'],json.loads(sent[1]['body']),dict(sent[0]['headers'])
    return SimpleNamespace(**locals())

def test_whole_literal_success_and_headers(rig):
    status,body,headers=rig.request()
    assert status==200 and body==rig.value
    assert rig.calls[0]['item_id']==ITEM and rig.calls[0]['caller_context'].principal_id==rig.digest
    assert headers[b'cache-control']==b'no-store' and headers[b'vary']==b'Accept'
    assert headers[b'x-robots-tag']==b'noindex, nofollow'

@pytest.mark.parametrize('changes',[
    {'method':'POST'}, {'scheme':'http'}, {'query_string':b'x=1'},
    {'path':PREFIX+ITEM+'/'}, {'raw_path':(PREFIX+ITEM).replace('rvitem','%72vitem').encode()},
    {'path':'/mcp/research/v1'}, {'path':'/.well-known/oauth-protected-resource'},
    {'raw_path':b'/os'}, {'path':PREFIX+ITEM.upper()},
])
def test_route_refusal_before_resolver(rig,changes):
    assert rig.request(changes=changes)[0]==404
    assert not rig.calls

@pytest.mark.parametrize('headers',[
    [(b'host',b'elsewhere.invalid')], [(b'accept',b'text/html')],
    [(b'origin',b'https://elsewhere.invalid')], [(b'authorization',b'Bearer ignored')],
    [(b'transfer-encoding',b'chunked')], [(b'content-length',b'1')],
])
def test_header_refusal(rig,headers):
    assert rig.request(headers=headers)[0]==404 and not rig.calls

def test_missing_token_no_lookup(rig):
    assert rig.request(auth=False)[0]==401 and not rig.calls

def test_body_no_lookup(rig):
    assert rig.request(body=b'private')[0]==400 and not rig.calls

@pytest.mark.parametrize('classes',[['catalog_metadata'],['catalog_metadata','report_text']])
def test_catalog_rights_not_passage_rights(rig,classes):
    rig.write(classes=classes)
    assert rig.request()[0]==403 and not rig.calls

@pytest.mark.parametrize('action',['revoke','expire_token','change_grant','shrink_quote'])
def test_change_during_resolution_suppresses_body(rig,action):
    def change():
        if action=='revoke':rig.path.unlink()
        elif action=='expire_token':rig.clock[0]+=601
        elif action=='change_grant':rig.write(grant_id='fixture.replacement')
        else:rig.write(quote=1)
    rig.hook[0]=change
    status,body,_=rig.request()
    assert status in (401,403) and 'text' not in body
    assert len(rig.calls)==1

def test_expired_grant_no_lookup(rig):
    rig.write(expires=rig.clock[0]-1)
    assert rig.request()[0]==403 and not rig.calls

def test_grant_below_complete_item_never_truncates(rig):
    rig.write(quote=1)
    status,body,_=rig.request()
    assert status==403 and 'text' not in body

@pytest.mark.parametrize('mutate',[
    lambda v:v.update(text='文'*334),lambda v:v.update(text='\ud800'),
    lambda v:v.update(id='rvitem.v1.'+'b'*64),lambda v:v.update(url='https://elsewhere.invalid'),
    lambda v:v.update(secret='private'),lambda v:v['metadata'].update(source_url='r2://private'),
    lambda v:v.update(text=''),lambda v:v.update(title='  '),
])
def test_unreviewed_or_overlong_dto_no_leak(rig,mutate):
    mutate(rig.value)
    status,body,_=rig.request()
    assert status==503 and body=={'error':'SERVICE_UNAVAILABLE'}

def test_stale_or_replayed_reference_fixed_unavailable(rig):
    async def unavailable(**kwargs):raise ContractViolation('SOURCE_UNAVAILABLE')
    rig.app.item_resolver=unavailable
    assert rig.request()[0]==404

def test_private_exception_is_not_returned(rig):
    async def fail(**kwargs):raise RuntimeError('r2://private secret body')
    rig.app.item_resolver=fail
    assert rig.request()[1]=={'error':'SERVICE_UNAVAILABLE'}

def test_wrong_trusted_context_never_resolves(rig):
    rig.app.context_builder=lambda e:SimpleNamespace(principal_id='b'*64)
    assert rig.request()[0]==503 and not rig.calls

@pytest.mark.parametrize("changes", [{"aud":"https://executive.example.invalid"}, {"exp":1699999999}, {"scope":"other"}, {"sub":"outsider"}])
def test_wrong_token_no_lookup(rig, changes):
    assert rig.request(token_value=rig.token(**changes))[0] == 401
    assert not rig.calls

def test_grant_revoked_in_final_token_await(rig):
    class RevokeKeys:
        calls=0
        async def key_for(self, kid):
            self.calls+=1
            if self.calls==2:rig.path.unlink()
            return JWK
    rig.app.authenticator=JwtAuthenticator(policy=rig.policy,jwks_cache=RevokeKeys())
    status,body,_=rig.request()
    assert status==403 and 'text' not in body and len(rig.calls)==1

def test_audit_failure_before_lookup_withholds_everything(rig):
    rig.audit.fail_on=1
    status,body,_=rig.request()
    assert status==503 and body=={'error':'SERVICE_UNAVAILABLE'} and not rig.calls

def test_final_audit_failure_withholds_resolved_body(rig):
    rig.audit.fail_on=2
    status,body,_=rig.request()
    assert status==503 and body=={'error':'SERVICE_UNAVAILABLE'} and len(rig.calls)==1

def test_audit_contains_only_public_closed_auth_facts(rig):
    from dataclasses import asdict
    rig.request()
    assert len(rig.audit.events)==2
    for event in rig.audit.events:
        row=asdict(event)
        assert row==dict(schema='mastermind.business_mcp_auth_audit.v1',policy_id=rig.policy.policy_id,code='accepted',accepted=True)
        assert set(row)=={'schema','policy_id','code','accepted'}

def test_auth_denial_is_audited_without_private_inputs(rig):
    assert rig.request(auth=False)[0]==401 and not rig.calls
    assert len(rig.audit.events)==1 and rig.audit.events[0].accepted is False

def test_auth_denial_audit_failure_is_fixed_unavailable(rig):
    rig.audit.fail_on=1
    assert rig.request(auth=False)[0]==503 and not rig.calls

@pytest.mark.parametrize("entitled", [True,False])
def test_same_public_durable_sink_accepts_events_and_contains_no_private_body(rig,tmp_path,entitled):
    from integrations.business_mcp_auth.audit import DurableAuthAuditSink
    directory=tmp_path/'audit';directory.mkdir(mode=0o700)
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:sink=DurableAuthAuditSink.open(fd,policy_id=rig.policy.policy_id)
    finally:os.close(fd)
    rig.app.audit_sink=sink
    if not entitled:rig.write(classes=['catalog_metadata'])
    try:assert rig.request()[0]==(200 if entitled else 403)
    finally:sink.close()
    rows=[json.loads(line) for line in (directory/'auth-audit.jsonl').read_text().splitlines()]
    assert rows and all(set(row)=={'schema','policy_id','code','accepted'} for row in rows)
    assert all(rig.value['text'] not in json.dumps(row) and ITEM not in json.dumps(row) for row in rows)

def test_async_audit_is_not_a_durable_acknowledgment(rig):
    class AsyncAudit:
        async def emit(self,event):pass
    rig.app.audit_sink=AsyncAudit()
    assert rig.request()[0]==503 and not rig.calls

def test_expiry_during_last_synchronous_owner_read_suppresses_body(rig):
    def quote(_principal):
        rig.clock[0]+=601
        return 1000
    rig.owner.quote_limit=quote
    status,body,_=rig.request()
    assert status==401 and 'text' not in body
