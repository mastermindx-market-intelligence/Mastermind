"""Real Starlette routing + HTTPX ASGI transport; no network listener/TLS claim."""
import asyncio,json
import httpx,pytest

pytest.importorskip('jwt', reason='PyJWT unavailable in this environment')
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.routing import Route
from tests.mastermind_window_reader.test_existing_auth_composition import composition,token
from tests.mastermind_window_reader.test_read_resource import PATH,RAW

@pytest.fixture(scope='module')
def key():return rsa.generate_private_key(public_exponent=65537,key_size=2048)

def through_router(key,*,method='GET',path=PATH,extra_headers=None,body=None,grant=True):
    resource,state,_,_=composition(key,grant=grant)
    app=Starlette(routes=[Route(PATH,resource,methods=['GET'])])
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://workspace.example') as client:
            return await client.request(method,path,headers={'Authorization':'Bearer '+token(key),**(extra_headers or {})},content=body)
    return asyncio.run(go()),state

def test_fixed_resource_composes_under_real_starlette_router(key):
    r,s=through_router(key)
    assert r.status_code==200 and s['reads']==1
    assert r.json()['view']['items'][1]['text']==json.loads(RAW)['items'][1]['text']
    assert r.headers['cache-control']=='no-store' and 'set-cookie' not in r.headers

@pytest.mark.parametrize('kwargs,status',[
 ({'path':PATH+'?source=/etc/passwd'},404),({'path':'/unknown'},404),
 ({'method':'POST'},405),({'extra_headers':{'Origin':'https://evil.example'}},403),
 ({'body':b'not-an-empty-get'},400),({'grant':False},401)
])
def test_unqualified_http_request_reads_no_content(key,kwargs,status):
    r,s=through_router(key,**kwargs)
    assert r.status_code==status and s['reads']==0
    assert 'SHIP LOOP' not in r.text
