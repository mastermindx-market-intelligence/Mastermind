"""Real browser + ASGI/auth + unchanged upstream window; synthetic source events."""
import asyncio,json
import pytest

pytest.importorskip('jwt', reason='PyJWT unavailable in this environment')
from cryptography.hazmat.primitives.asymmetric import rsa
from tests.mastermind_window_reader._browser_support import browser_available, browser_launch_kwargs
from integrations.mastermind_window_reader.recorded_view import render_connection_shell
from tests.mastermind_window_reader.test_window_resource import signed_window
from tests.mastermind_window_reader.test_read_resource import request
from tests.mastermind_window_reader.test_existing_auth_composition import token
from tests.mastermind_window_reader.test_live_window import REF,KEY

_AVAILABLE, _REASON = browser_available()
pytestmark = pytest.mark.skipif(not _AVAILABLE, reason=_REASON)
pytest.importorskip('playwright.sync_api', reason=_REASON or 'Playwright unavailable in this environment', exc_type=ImportError)
from playwright.sync_api import sync_playwright,expect

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(**browser_launch_kwargs())
        yield b;b.close()

@pytest.fixture
def connected(browser):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    app,state,source=signed_window(key);state['token']=token(key)
    ctx=browser.new_context(viewport={'width':1440,'height':1000});page=ctx.new_page();errors=[];requests=[];calls=[]
    page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
    async def read():
        status,headers,body=await request(app,headers=[(b'host',b'workspace.example'),(b'authorization',('Bearer '+state['token']).encode())])
        calls.append(status);return {'status':status,'body':json.loads(body)}
    page.expose_function('fixtureOwnerRead',read)
    page.set_content(render_connection_shell())
    page.evaluate('''ref=>window.MastermindReadConnection.attach({expectedLane:ref,sourceKind:'live-window',read:async()=>await window.fixtureOwnerRead()})''',REF)
    yield page,state,source,calls,errors,requests
    ctx.close()

def refresh(p):return p.evaluate('window.MastermindReadConnection.refresh()')

def test_partial_visible_before_terminal_in_actual_projection_path(connected):
    p,state,s,calls,errors,requests=connected;s.publish('a','Fixture response while the source turn remains nonterminal.')
    assert refresh(p) is True
    expect(p.locator('.message-text')).to_have_text('Fixture response while the source turn remains nonterminal.')
    expect(p.locator('#window-state')).to_contain_text('nonterminal')
    assert not s.owner.read(KEY,reader_grant=s.grant,cursor=None,max_items=64).terminal
    assert not errors and not requests and calls==[200]

def test_final_replaces_partial_without_second_bubble(connected):
    p,_,s,calls,errors,_=connected;s.publish('a','Draft');refresh(p)
    s.publish('a','Corrected final','completed');assert refresh(p)
    assert p.locator('.output-card').count()==1
    expect(p.locator('.message-text')).to_have_text('Corrected final')
    expect(p.locator('.body-caption')).to_contain_text('COMPLETED')
    assert not errors

def test_paging_update_preserves_other_message(connected):
    p,_,s,_,errors,_=connected;s.publish('a','Draft');refresh(p)
    s.publish('b','Second answer',position=2);s.publish('a','Final answer','completed');refresh(p)
    p.locator('#compare').click()
    assert p.locator('.message-text').all_inner_texts()==['Final answer','Second answer'] and not errors

def test_gap_is_visible_not_complete_history(connected):
    p,_,s,_,errors,_=connected;s.publish('a','Readable')
    s.owner.publish(KEY,method='item/updated',params={'item':{'type':'agentMessage','id':'broken'}},native_turn_id=KEY.native_turn_id)
    assert refresh(p);expect(p.locator('#window-state')).to_contain_text('gap')
    expect(p.locator('#mode-note')).to_contain_text('history')
    assert not errors

def test_terminal_does_not_become_company_acceptance(connected):
    p,_,s,_,errors,_=connected;s.publish('a','PASS','completed');s.terminal();refresh(p)
    expect(p.locator('#window-state')).to_contain_text('ended')
    expect(p.locator('#review-warning')).to_contain_text('Acceptance is not projected')
    assert not errors

def test_actual_grant_revocation_clears_content_and_details(connected):
    p,state,s,calls,errors,_=connected;s.publish('a','Private test phrase');refresh(p)
    p.locator('#evidence').click();s.owner.revoke_grant(s.grant)
    assert refresh(p) is False
    assert p.locator('.message-text').count()==0 and 'Private test phrase' not in p.content()
    assert not p.locator('#details').is_visible() and calls==[200,401] and not errors

def test_empty_observation_not_zero_agents(connected):
    p,_,s,_,errors,_=connected;assert refresh(p)
    expect(p.locator('#empty-result')).to_contain_text('not a fleet count')
    assert '0 agents' not in p.content() and not errors

def test_context_has_no_invented_job_or_org_edges(connected):
    p,_,s,_,errors,_=connected;s.publish('a','Visible');refresh(p);p.locator('#connections').click()
    expect(p.locator('#dialog-body')).to_contain_text('No organizational relationships are inferred')
    assert not errors

def test_refresh_preserves_selection_and_scroll(connected):
    p,_,s,_,errors,_=connected;s.publish('a','\n'.join(f'line {i}' for i in range(150)));s.publish('b','Other',position=2);refresh(p)
    p.locator('.message-text').focus();p.locator('.message-text').evaluate('e=>e.scrollTop=120');before=p.locator('.message-text').evaluate('e=>e.scrollTop')
    s.publish('a','\n'.join(f'line {i}' for i in range(160)),'completed');refresh(p)
    assert p.locator('.message-text').evaluate('e=>e.scrollTop')==before
    expect(p.locator('.message-text')).to_be_focused();assert not errors

def test_source_markup_remains_inert(connected):
    p,_,s,_,errors,requests=connected;text='<img src="https://bad.example/a" onerror="window.pwn=1"><script>window.pwn=1</script>'
    s.publish('a',text);refresh(p)
    expect(p.locator('.message-text')).to_have_text(text)
    assert p.evaluate('window.pwn') is None and not errors and not requests

def test_disconnect_while_source_read_pending_cannot_restore_content(connected):
    p,_,s,_,errors,_=connected;s.publish('a','Earlier');refresh(p)
    p.evaluate('''ref=>{window.MastermindReadConnection.attach({expectedLane:ref,sourceKind:'live-window',read:()=>new Promise(resolve=>window.pendingResolve=resolve)}); window.pendingRead=window.MastermindReadConnection.refresh();}''',REF)
    p.locator('#disconnect-source').click()
    assert p.evaluate('window.pendingRead') is False
    p.evaluate("window.pendingResolve({status:200,body:{}})")
    assert p.locator('.message-text').count()==0 and not errors

def test_signature_fixture_never_enters_browser(connected):
    p,state,s,_,errors,_=connected;s.publish('a','Answer');refresh(p)
    html=p.content();assert state['token'] not in html and s.grant not in html and KEY.native_turn_id not in html
    assert not errors

def test_window_labels_do_not_claim_recorded_file(connected):
    p,_,s,_,_,_=connected;s.publish('a','Visible');refresh(p)
    expect(p.locator('#evidence')).to_have_text('Inspect window evidence')
    expect(p.locator('#connections')).to_have_text('Inspect observation context')
    expect(p.locator('.breadcrumb')).to_contain_text('Conversation window')

def test_window_status_aligns_with_content(connected):
    p,_,s,_,_,_=connected;s.publish('a','Visible');refresh(p)
    status=p.locator('#window-state').bounding_box();content=p.locator('#review-warning').bounding_box()
    assert abs(status['x']-content['x'])<1
