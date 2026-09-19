"""Chromium -> test host binding -> ASGI -> exact existing JWT -> source -> UI.

The bridge, issuer/key source and current target permission are controlled test
inputs. No network listener, registered OAuth flow, native provider or deployment.
"""
import asyncio,copy,hashlib,json
import pytest

pytest.importorskip('jwt', reason='PyJWT unavailable in this environment')
from cryptography.hazmat.primitives.asymmetric import rsa
from tests.mastermind_window_reader._browser_support import browser_available, browser_launch_kwargs
from integrations.mastermind_window_reader.recorded_view import render_connection_shell
from tests.mastermind_window_reader.test_existing_auth_composition import composition,token,NOW
from tests.mastermind_window_reader.test_read_resource import request,RAW,LANE
CAP=json.loads(RAW)

_AVAILABLE, _REASON = browser_available()
pytestmark = pytest.mark.skipif(not _AVAILABLE, reason=_REASON)
pytest.importorskip('playwright.sync_api', reason=_REASON or 'Playwright unavailable in this environment', exc_type=ImportError)
from playwright.sync_api import sync_playwright,expect

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as pw:
        b=pw.chromium.launch(**browser_launch_kwargs())
        yield b;b.close()

@pytest.fixture
def connected(browser):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    resource,state,auth,keys=composition(key)
    state['token']=token(key)
    calls=[]
    async def existing_host_read():
        status,headers,raw=await request(resource,headers=[(b'host',b'workspace.example'),(b'authorization',('Bearer '+state['token']).encode())])
        calls.append({'status':status,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        return {'status':status,'body':json.loads(raw)}
    ctx=browser.new_context(viewport={'width':1440,'height':1000});page=ctx.new_page();errors=[];requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
    # Test bridge invokes the actual ASGI resource; it does not return hardcoded
    # content or skip signature validation. No real token enters the browser.
    page.expose_function('testOnlyReadThroughHost',existing_host_read)
    page.set_content(render_connection_shell())
    page.evaluate('''lane=>window.MastermindReadConnection.attach({expectedLane:lane,
       read:async({signal})=>{if(signal.aborted)throw new Error('aborted');return await window.testOnlyReadThroughHost();}})''',LANE)
    yield page,state,calls,errors,requests,key
    ctx.close()

def test_real_capture_crosses_existing_signed_resource_and_browser(connected):
    p,state,calls,errors,requests,key=connected
    assert p.locator('.message-text').count()==0 and state['reads']==0
    assert p.evaluate('window.MastermindReadConnection.refresh()') is True
    assert p.locator('.message-text').inner_text()==CAP['items'][0]['text']
    p.locator('#compare').click()
    assert p.locator('.message-text').all_inner_texts()==[i['text'] for i in CAP['items']]
    assert state['reads']==1 and state['accesses']==2 and [c['status'] for c in calls]==[200]
    assert state['token'] not in p.content() and not errors and not requests

def test_resource_revocation_actually_clears_both_panes(connected):
    p,state,calls,errors,requests,key=connected
    p.evaluate('window.MastermindReadConnection.refresh()');p.locator('#compare').click()
    state['grant']=False
    assert p.evaluate('window.MastermindReadConnection.refresh()') is False
    assert p.locator('.message-text').count()==0
    assert [c['status'] for c in calls]==[200,401] and state['reads']==1
    expect(p.locator('#source-status')).to_contain_text('Access unavailable')
    assert not errors and not requests

def test_expired_signature_verified_input_is_not_displayed(connected):
    p,state,calls,errors,requests,key=connected
    state['now']=NOW+601
    assert p.evaluate('window.MastermindReadConnection.refresh()') is False
    assert state['reads']==0 and [c['status'] for c in calls]==[401]
    assert p.locator('.message-text').count()==0 and not errors

def test_wrong_signature_is_refused_on_full_reader_path(connected):
    p,state,calls,errors,requests,key=connected
    state['token']=token(rsa.generate_private_key(public_exponent=65537,key_size=2048))
    assert p.evaluate('window.MastermindReadConnection.refresh()') is False
    assert state['reads']==0 and state['accesses']==0 and calls[0]['status']==401
    assert 'SHIP LOOP' not in p.content() and not errors

def test_unchanged_signed_read_preserves_focus_and_reported_findings(connected):
    p,state,calls,errors,requests,key=connected
    p.evaluate('window.MastermindReadConnection.refresh()');p.locator('[data-item-index="1"]').click()
    p.locator('.message-text').focus();p.locator('.message-text').evaluate('e=>e.scrollTop=150')
    before=p.locator('.message-text').evaluate('e=>e.scrollTop')
    p.evaluate('window.MastermindReadConnection.refresh()')
    expect(p.locator('.message-text')).to_be_focused()
    assert p.locator('.message-text').evaluate('e=>e.scrollTop')==before
    expect(p.locator('#review-warning')).to_contain_text('2 major findings')
    assert state['reads']==2 and len(calls)==2 and not errors

def test_disconnect_never_invokes_source_or_provider(connected):
    p,state,calls,errors,requests,key=connected
    p.evaluate('window.MastermindReadConnection.refresh()');before=state['reads']
    p.locator('#disconnect-source').click()
    assert p.locator('.message-text').count()==0 and state['reads']==before
    assert p.evaluate('window.MastermindReadConnection.refresh()') is False
    assert len(calls)==1 and not errors and not requests
