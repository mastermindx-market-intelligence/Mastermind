"""Real Chromium + controlled host read-port; NOT installed OAuth/provider proof."""
import copy,hashlib,json,sys
from pathlib import Path
import pytest
from tests.mastermind_window_reader._browser_support import browser_available, browser_launch_kwargs
from integrations.mastermind_window_reader.recorded_view import render_capture,project_capture

_AVAILABLE, _REASON = browser_available()
pytestmark = pytest.mark.skipif(not _AVAILABLE, reason=_REASON)
pytest.importorskip('playwright.sync_api', reason=_REASON or 'Playwright unavailable in this environment', exc_type=ImportError)
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[0]
CAP=json.loads((ROOT/'recorded_lane_capture.json').read_bytes())
LANE=CAP['lane']['ref']

def wire(capture=None):
    c=capture or CAP;v=project_capture(c)
    v['capture_sha256']=hashlib.sha256(json.dumps(c).encode()).hexdigest()
    return dict(schema='mastermind.workspace.recorded_read_candidate.v1',selection_ref=LANE,mode='recorded-source-read',view=v)

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(**browser_launch_kwargs())
        yield b;b.close()

@pytest.fixture
def page(browser):
    ctx=browser.new_context(viewport={'width':1440,'height':1000});p=ctx.new_page();errs=[];requests=[]
    p.on('pageerror',lambda e:errs.append(str(e)));p.on('request',lambda r:requests.append(r.url))
    p.set_content(render_capture(json.dumps(CAP).encode()))
    yield p,errs,requests
    ctx.close()

def attach(p,responses):
    assert p.evaluate("typeof window.MastermindReadConnection==='object'"),'read-source attachment not implemented'
    p.evaluate('''args=>{
      window.fixtureResponses=args.responses;window.fixtureCalls=0;
      window.MastermindReadConnection.attach({expectedLane:args.lane,read:async ({signal})=>{
        window.fixtureCalls++;return window.fixtureResponses.shift();
      }});
    }''',{'responses':responses,'lane':LANE})

def refresh(p):return p.evaluate('window.MastermindReadConnection.refresh()')

def test_first_attached_read_uses_existing_view_and_exact_text(page):
    p,errs,reqs=page;attach(p,[{'status':200,'body':wire()}])
    expect(p.locator('.message-text')).to_have_count(0)
    assert refresh(p) is True
    assert p.locator('.message-text').inner_text()==CAP['items'][0]['text']
    expect(p.locator('#source-status')).to_contain_text('Read succeeded')
    expect(p.locator('#mode-note')).to_contain_text('not live chat')
    assert not errs and not reqs

def test_refresh_replaces_not_appends_and_keeps_selected_reader_and_size(page):
    p,_,_=page;c=copy.deepcopy(CAP);text='Updated recorded review.\n'+c['items'][1]['text']
    c['items'][1].update(text=text,display_sha256=hashlib.sha256(text.encode()).hexdigest())
    attach(p,[{'status':200,'body':wire()},{'status':200,'body':wire(c)}]);refresh(p)
    p.locator('[data-item-index="1"]').click();p.locator('#larger').click()
    p.locator('.message-text').evaluate('(e)=>e.scrollTop=130')
    old=p.locator('.message-text').evaluate('(e)=>e.scrollTop')
    assert old>0
    refresh(p)
    assert p.locator('.message-text').inner_text()==text
    assert p.locator('.message-text').evaluate('(e)=>e.scrollTop')==old
    assert 'size-1' in p.locator('#reading-grid').get_attribute('class')
    assert p.locator('#output-nav [aria-pressed=true]').get_attribute('data-item-index')=='1'

@pytest.mark.parametrize('status',[401,403])
def test_access_loss_clears_text_modal_search_and_bootstrap_data(page,status):
    p,_,_=page;attach(p,[{'status':200,'body':wire()},{'status':status,'body':{'error':'PRIVATE_DETAIL'}}]);refresh(p)
    p.locator('#search').fill('VERDICT_LINE');p.locator('#evidence').click()
    refresh(p)
    expect(p.get_by_role('dialog')).not_to_be_visible()
    expect(p.locator('.message-text')).to_have_count(0)
    assert p.locator('#search').input_value()==''
    assert 'SHIP LOOP BLOCKED' not in p.locator('body').text_content()
    assert 'PRIVATE_DETAIL' not in p.locator('body').inner_text()
    expect(p.locator('#source-status')).to_contain_text('Access unavailable')
    assert p.evaluate('window.fixtureCalls')==2

def test_source_failure_retains_qualified_previous_read_but_labels_it(page):
    p,_,_=page;attach(p,[{'status':200,'body':wire()},{'status':502,'body':{'error':'/Users/private'}}]);refresh(p)
    before=p.locator('.message-text').inner_text();refresh(p)
    assert p.locator('.message-text').inner_text()==before
    expect(p.locator('#source-status')).to_contain_text('Last successful read')
    assert '/Users/private' not in p.locator('body').inner_text()
    p.locator('#evidence').click();expect(p.get_by_role('dialog')).to_contain_text(CAP['captured_at'][:10])

def test_changed_selection_is_refused_not_merged(page):
    p,_,_=page;bad=wire();bad['selection_ref']='native-lane:other'
    attach(p,[{'status':200,'body':wire()},{'status':200,'body':bad}]);refresh(p);refresh(p)
    assert p.locator('.message-text').inner_text()==CAP['items'][0]['text']
    expect(p.locator('#source-status')).to_contain_text('response refused')

def test_old_response_cannot_repopulate_after_detach(page):
    p,_,_=page;attach(p,[])
    p.evaluate('''lane=>{window.MastermindReadConnection.attach({expectedLane:lane,read:({signal})=>new Promise(r=>{window.finishRead=r;window.readSignal=signal})});window.pendingRead=window.MastermindReadConnection.refresh();}''',LANE)
    p.wait_for_function('window.finishRead!==undefined')
    p.evaluate('window.MastermindReadConnection.detach()')
    p.evaluate('w=>window.finishRead({status:200,body:w})',wire())
    assert p.evaluate('window.pendingRead') is False
    assert p.evaluate('window.readSignal.aborted') is True
    expect(p.locator('.message-text')).to_have_count(0)

def test_old_response_cannot_override_new_attachment(page):
    p,_,_=page;attach(p,[])
    p.evaluate('''lane=>{window.MastermindReadConnection.attach({expectedLane:lane,read:()=>new Promise(r=>window.oldRead=r)});window.pendingOld=window.MastermindReadConnection.refresh();}''',LANE)
    p.wait_for_function('window.oldRead!==undefined')
    changed=copy.deepcopy(CAP);changed['items'][0]['text']='New authorized source response';changed['items'][0]['display_sha256']=hashlib.sha256(changed['items'][0]['text'].encode()).hexdigest()
    attach(p,[{'status':200,'body':wire(changed)}]);refresh(p)
    p.evaluate('w=>window.oldRead({status:200,body:w})',wire());assert p.evaluate('window.pendingOld') is False
    assert p.locator('.message-text').inner_text()=='New authorized source response'

def test_no_duplicate_request_from_double_refresh(page):
    p,_,_=page;attach(p,[])
    p.evaluate('''lane=>{window.calls=0;window.MastermindReadConnection.attach({expectedLane:lane,read:()=>{window.calls++;return new Promise(r=>window.pendingResolve=r)}});window.pendingOne=window.MastermindReadConnection.refresh();}''',LANE)
    p.wait_for_function('window.pendingResolve!==undefined')
    assert refresh(p) is False and p.evaluate('window.calls')==1
    p.evaluate('window.MastermindReadConnection.detach()')
    p.evaluate('w=>window.pendingResolve({status:200,body:w})',wire())

@pytest.mark.parametrize('mutate', ['capabilities','script','schema','items','review'])
def test_malformed_or_authority_inflated_view_is_rejected(page,mutate):
    p,_,_=page;bad=wire()
    if mutate=='capabilities':bad['view']['capabilities']['send']=True
    if mutate=='script':bad['view']['lane']['repository']='evil.example/<script>'
    if mutate=='schema':bad['schema']='unknown.v999'
    if mutate=='items':bad['view']['items'][1]['id']=bad['view']['items'][0]['id']
    if mutate=='review':bad['view']['review']['company_acceptance']='ACCEPTED'
    attach(p,[{'status':200,'body':bad}]);assert refresh(p) is False
    expect(p.locator('.message-text')).to_have_count(0)
    expect(p.locator('#source-status')).to_contain_text('response refused')

def test_source_change_does_not_refresh_capture_time(page):
    p,_,_=page;attach(p,[{'status':200,'body':wire()}]);refresh(p)
    assert p.locator('#captured-time').inner_text().startswith('Capture from 16 Sept 2026, 05:01:37')
    assert CAP['captured_at'].startswith('2026-09-16T05:01:37')

def test_removed_selected_item_is_not_silently_replaced(page):
    p,_,_=page;d=copy.deepcopy(CAP);d['items']=d['items'][:1];removed=CAP['items'][1]['id']
    d['relations']=[e for e in d['relations'] if e['from']!=removed and e['to']!=removed]
    attach(p,[{'status':200,'body':wire()},{'status':200,'body':wire(d)}]);refresh(p)
    p.locator('[data-item-index="1"]').click();refresh(p)
    expect(p.locator('.message-text')).to_have_count(0)
    expect(p.locator('#empty-result')).to_contain_text('selected output is no longer available')
    p.locator('[data-item-index="0"]').click();expect(p.locator('.message-text')).to_have_count(1)

def test_repeated_equal_snapshot_does_not_drop_focus_or_scroll(page):
    p,_,_=page;attach(p,[{'status':200,'body':wire()},{'status':200,'body':wire()}]);refresh(p)
    p.locator('.message-text').focus();p.locator('.message-text').evaluate('e=>e.scrollTop=70');before=p.locator('.message-text').evaluate('e=>e.scrollTop')
    refresh(p)
    expect(p.locator('.message-text')).to_be_focused()
    assert p.locator('.message-text').evaluate('e=>e.scrollTop')==before

def test_connection_shell_contains_no_captured_output_before_owner_read(browser):
    import integrations.mastermind_window_reader.recorded_view as recorded_view
    assert hasattr(recorded_view,'render_connection_shell'),'unconnected zero-content shell not implemented'
    ctx=browser.new_context(viewport={'width':1440,'height':1000});p=ctx.new_page();errs=[];reqs=[]
    p.on('pageerror',lambda e:errs.append(str(e)));p.on('request',lambda r:reqs.append(r.url))
    p.set_content(recorded_view.render_connection_shell())
    assert 'SHIP LOOP BLOCKED' not in p.content() and 'VERDICT_LINE' not in p.content()
    assert LANE not in p.content() and '7054' not in p.content()
    expect(p.locator('.message-text')).to_have_count(0)
    attach(p,[{'status':200,'body':wire()}]);refresh(p)
    assert p.locator('.message-text').inner_text()==CAP['items'][0]['text']
    assert not errs and not reqs
    ctx.close()

def test_unresponsive_port_expires_without_replay_or_stuck_busy_state(page):
    p,_,_=page;attach(p,[]);p.clock.install()
    p.evaluate('''lane=>{window.calls=0;window.MastermindReadConnection.attach({expectedLane:lane,read:({signal})=>{window.calls++;window.readSignal=signal;return new Promise(()=>{})}});window.result=null;window.MastermindReadConnection.refresh().then(r=>window.result=r);}''',LANE)
    p.clock.run_for(16000)
    assert p.evaluate('window.result') is False
    assert p.evaluate('window.calls')==1 and p.evaluate('window.readSignal.aborted') is True
    expect(p.locator('#source-status')).to_contain_text('timed out')
    expect(p.locator('#refresh-source')).to_be_enabled()

def test_detach_completes_pending_read_even_when_owner_ignores_abort(page):
    p,_,_=page;attach(p,[])
    p.evaluate('''lane=>{window.MastermindReadConnection.attach({expectedLane:lane,read:()=>new Promise(()=>{})});window.result=null;window.MastermindReadConnection.refresh().then(r=>window.result=r);}''',LANE)
    p.evaluate('window.MastermindReadConnection.detach()')
    assert p.evaluate('window.result') is False
    expect(p.locator('.message-text')).to_have_count(0)

def test_unavailable_source_does_not_claim_an_empty_inventory(page):
    p,_,_=page;attach(p,[{'status':200,'body':wire()},{'status':403}])
    expect(p.locator('#search-result')).not_to_contain_text('0 recorded outputs')
    refresh(p);refresh(p)
    expect(p.locator('#search-result')).to_contain_text('No source currently displayed')
    expect(p.locator('#empty-result')).to_contain_text('Source content is not currently displayed')
    expect(p.locator('#empty-result')).not_to_contain_text('No outputs in this capture')
