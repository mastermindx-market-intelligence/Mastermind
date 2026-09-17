"""Contract/consumer tests. OwnerFixture is NOT production authentication."""
import asyncio
import copy
import hashlib
import json
from http import HTTPStatus
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[0]
import integrations.mastermind_window_reader.owner_read_resource as rr
from integrations.mastermind_window_reader.recorded_view import load_capture

RAW=(ROOT/'recorded_lane_capture.json').read_bytes()
LANE='native-lane:a15_7054_p0b_r2'
PATH='/workspace/native-output'
RESOURCE='https://workspace.example'+PATH

class OwnerFixture:
    """In-memory authority contract double. Does not validate real JWTs."""
    def __init__(self):
        self.calls=[];self.ticket=('fixture-subject','fixture-permission-revision-1')
        self.after_read=None;self.data=RAW
    async def authorize(self,header,resource,source_ref):
        self.calls.append(('authorize',resource,source_ref))
        return self.ticket if header=='Bearer fixture-only' else None
    async def read(self,source_ref):
        self.calls.append(('read',source_ref))
        if self.after_read:self.after_read(self)
        return self.data

def app(owner=None,**kwargs):
    return rr.NativeOutputReadResource(owner=owner or OwnerFixture(),resource=RESOURCE,
        source_ref=LANE,allowed_origin='https://workspace.example',**kwargs)

async def request(application,*,path=PATH,raw_path=None,method='GET',headers=None,query=b'',body=b'',scheme='https'):
    events=[]
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':scheme,
        'method':method,'path':path,'raw_path':raw_path if raw_path is not None else path.encode(),
        'root_path':'','query_string':query,'headers':headers if headers is not None else
        [(b'host',b'workspace.example'),(b'authorization',b'Bearer fixture-only')],
        'server':('workspace.example',443),'client':('127.0.0.1',1234)}
    async def receive():return {'type':'http.request','body':body,'more_body':False}
    async def send(message):events.append(message)
    await application(scope,receive,send)
    start=next(e for e in events if e['type']=='http.response.start')
    data=b''.join(e.get('body',b'') for e in events if e['type']=='http.response.body')
    return start['status'],dict(start['headers']),data

def call(application,**kwargs):return asyncio.run(request(application,**kwargs))

def test_real_recorded_capture_has_exact_text_and_no_source_or_action_leak():
    owner=OwnerFixture();status,headers,body=call(app(owner));d=json.loads(body)
    assert status==200
    assert headers[b'cache-control']==b'no-store'
    assert d['selection_ref']==LANE and d['mode']=='recorded-source-read'
    assert d['view']['capture_sha256']==hashlib.sha256(RAW).hexdigest()
    assert d['view']['items'][0]['text']==load_capture(RAW)['items'][0]['text']
    assert d['view']['capabilities']==dict(send=False,live_stream=False,provider_control=False)
    assert [c[0] for c in owner.calls]==['authorize','read','authorize']
    assert b'fixture-only' not in body and b'/Users/' not in body

@pytest.mark.parametrize('headers,status',[
 ([(b'host',b'workspace.example')],401),
 ([(b'host',b'workspace.example'),(b'authorization',b'Bearer wrong')],401),
 ([(b'host',b'workspace.example'),(b'authorization',b'Bearer fixture-only'),(b'Authorization',b'Bearer fixture-only')],400),
 ([(b'host',b'evil.example'),(b'authorization',b'Bearer fixture-only')],403),
 ([(b'host',b'workspace.example'),(b'origin',b'https://evil.example'),(b'authorization',b'Bearer fixture-only')],403),
 ([(b'host',b'workspace.example'),(b'origin',b'null'),(b'authorization',b'Bearer fixture-only')],403),
 ([(b'host',b'workspace.example'),(b'authorization',b'Bearer fixture-only'),(b'content-length',b'1')],400),
 ([(b'host',b'workspace.example'),(b'authorization',b'Bearer fixture-only'),(b'transfer-encoding',b'chunked')],400),
])
def test_transport_or_auth_denial_never_reads_source(headers,status):
    owner=OwnerFixture();got=call(app(owner),headers=headers)
    assert got[0]==status
    assert not any(c[0]=='read' for c in owner.calls)
    assert b'Builder output' not in got[2]

@pytest.mark.parametrize('kwargs,status',[
 ({'method':'POST'},405),({'method':'HEAD'},405),({'method':'OPTIONS'},405),
 ({'query':b'path=/etc/passwd'},404),({'path':'/workspace/native-output/../secret'},404),
 ({'raw_path':b'/workspace/native%2doutput'},404),({'body':b'x'},400),({'scheme':'http'},403),
])
def test_exact_read_only_surface(kwargs,status):
    owner=OwnerFixture();got=call(app(owner),**kwargs)
    assert got[0]==status and not any(c[0]=='read' for c in owner.calls)

def test_http_status_values_are_plain_asgi_integers():
    assert int(HTTPStatus.NOT_FOUND)==404
    owner=OwnerFixture();got=call(app(owner),query=b'path=/etc/passwd')
    assert got[0]==404
    assert type(got[0]) is int

@pytest.mark.parametrize('change',[
 lambda o:setattr(o,'ticket',None),
 lambda o:setattr(o,'ticket',('different-subject','fixture-permission-revision-1')),
 lambda o:setattr(o,'ticket',('fixture-subject','permission-revision-2')),
])
def test_revoked_or_changed_authority_after_read_releases_no_text(change):
    owner=OwnerFixture();owner.after_read=change
    status,headers,body=call(app(owner))
    assert status==403 and b'SHIP LOOP' not in body
    assert headers[b'cache-control']==b'no-store'

@pytest.mark.parametrize('field,value', [('label','other-lane'),('ref','native-lane:other-lane')])
def test_source_substitution_never_returns_body(field,value):
    owner=OwnerFixture();d=load_capture(RAW);d['lane'][field]=value
    owner.data=json.dumps(d).encode()
    assert call(app(owner))[0]==502

@pytest.mark.parametrize('bad', [b'',b'{',b'{"a":1,"a":2}',b'[]',b'null',b'x'*2_000_001,'not-bytes'])
def test_invalid_source_bytes_are_typed_and_do_not_leak(bad):
    o=OwnerFixture();o.data=bad
    status,_,body=call(app(o))
    assert status==502 and json.loads(body)['error']=='source_unavailable'

@pytest.mark.parametrize('stage', ['authorize','read'])
def test_private_dependency_exceptions_are_not_serialized(stage):
    class Broken(OwnerFixture):
        async def authorize(self,*a):
            if stage=='authorize':raise RuntimeError('secret /Users/private token-value')
            return await super().authorize(*a)
        async def read(self,*a):raise RuntimeError('secret /Users/private token-value')
    status,_,body=call(app(Broken()))
    assert status in (401,502) and b'private' not in body and b'token-value' not in body

def test_withheld_content_is_removed_before_serialization():
    o=OwnerFixture();d=load_capture(RAW);d['items'][0].update(state='WITHHELD',text='MUST_NOT_EXPORT')
    o.data=json.dumps(d).encode();status,_,body=call(app(o))
    assert status==200 and b'MUST_NOT_EXPORT' not in body

def test_no_implicit_conditional_304_without_fresh_access():
    o=OwnerFixture();status,h,b=call(app(o),headers=[(b'host',b'workspace.example'),(b'authorization',b'Bearer fixture-only'),(b'if-none-match',b'*')])
    assert status==200 and [x[0] for x in o.calls]==['authorize','read','authorize']
    assert b'last-modified' not in h

def test_final_encoded_byte_limit_not_only_source_size():
    o=OwnerFixture()
    # The source is valid but the response envelope exceeds this reviewed fixture limit.
    status,_,body=call(app(o,max_response_bytes=1000))
    assert status==502 and b'SHIP LOOP' not in body

def test_same_reader_has_no_cross_request_data_cache():
    o=OwnerFixture();a=app(o);assert call(a)[0]==200
    o.ticket=None;status,_,b=call(a)
    assert status==401 and b'SHIP LOOP' not in b

def test_owner_is_mandatory_and_never_default_allow():
    with pytest.raises((TypeError,ValueError)):
        rr.NativeOutputReadResource(owner=None,resource=RESOURCE,source_ref=LANE,allowed_origin='https://workspace.example')

def test_read_failure_does_not_hide_concurrent_access_revocation():
    class FailingRevoked(OwnerFixture):
        async def read(self,*a):
            self.ticket=None
            raise RuntimeError('private upstream went away')
    status,_,body=call(app(FailingRevoked()))
    assert status==403 and json.loads(body)['error']=='access_changed'

@pytest.mark.parametrize('frames,expected',[
 ([{'type':'http.request','body':b'','more_body':True},{'type':'http.request','body':b'','more_body':False}],200),
 ([{'type':'http.request','body':b'','more_body':True},{'type':'http.request','body':b'x','more_body':False}],400),
 ([{'type':'http.request','body':b'','more_body':True}]*10,400),
])
def test_empty_body_frames_follow_asgi_protocol_with_finite_bound(frames,expected):
    owner=OwnerFixture();events=[];queue=list(frames)
    async def run():
        scope={'type':'http','scheme':'https','method':'GET','path':PATH,'raw_path':PATH.encode(),
          'root_path':'','query_string':b'','headers':[(b'host',b'workspace.example'),(b'authorization',b'Bearer fixture-only')]}
        async def receive():return queue.pop(0)
        async def send(message):events.append(message)
        await app(owner)(scope,receive,send)
    asyncio.run(run())
    assert events[0]['status']==expected
    assert sum(c[0]=='read' for c in owner.calls)==(1 if expected==200 else 0)
