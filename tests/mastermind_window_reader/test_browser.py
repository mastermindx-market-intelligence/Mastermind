"""Real Chromium tests of the recorded-data consumer; not a live-provider test."""
import copy, hashlib, json
from pathlib import Path
import pytest
from tests.mastermind_window_reader._browser_support import browser_available, browser_launch_kwargs
from integrations.mastermind_window_reader.recorded_view import render_capture

_AVAILABLE, _REASON = browser_available()

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason=_REASON)
pytest.importorskip('playwright.sync_api', reason=_REASON or 'Playwright unavailable in this environment', exc_type=ImportError)
from playwright.sync_api import sync_playwright, expect


ROOT=Path(__file__).resolve().parents[0]
CAP=json.loads((ROOT/'recorded_lane_capture.json').read_bytes())

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(**browser_launch_kwargs())
        yield b
        b.close()

@pytest.fixture
def app(browser,tmp_path):
    page_file=tmp_path/'view.html'
    page_file.write_text(render_capture(json.dumps(CAP).encode()))
    ctx=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    pg=ctx.new_page(); errors=[]; requests=[]
    pg.on('pageerror',lambda err: errors.append(str(err)))
    pg.on('request',lambda req: requests.append(req.url))
    # The environment blocks URL navigation. Render already-authorized bytes
    # in about:blank without changing policy or fetching a blocked resource.
    pg.set_content(page_file.read_text())
    expect(pg.locator('#workspace')).to_be_visible()
    yield pg, errors, requests
    ctx.close()

def test_initial_real_builder_output(app):
    p,errors,_=app
    expect(p.get_by_role('heading',name='Builder output',exact=True)).to_be_visible()
    assert p.locator('.message-text').inner_text()==CAP['items'][0]['text']
    expect(p.locator('#capture-notice')).to_contain_text('Recorded capture')
    expect(p.locator('#mode-note')).to_contain_text('No live connection')
    assert not errors

def test_select_reviewer_complete_text_and_findings(app):
    p,_,_=app
    p.locator('[data-item-index="1"]').click()
    assert p.locator('.message-text').inner_text()==CAP['items'][1]['text']
    expect(p.locator('#review-warning')).to_contain_text('2 major findings')
    expect(p.locator('#review-warning')).to_contain_text('not company acceptance')

def test_compare_two_outputs(app):
    p,_,_=app
    p.get_by_role('button',name='Compare outputs',exact=True).click()
    expect(p.locator('.message-text')).to_have_count(2)
    assert p.locator('.message-text').all_inner_texts()==[i['text'] for i in CAP['items']]
    p.get_by_role('button',name='Single output',exact=True).click()
    expect(p.locator('.message-text')).to_have_count(1)

def test_search_and_zero_results(app):
    p,_,_=app
    p.get_by_role('searchbox',name='Find in recorded outputs').fill('VERDICT_LINE')
    expect(p.locator('[data-item-index]')).to_have_count(1)
    expect(p.locator('mark')).to_have_count(1)
    expect(p.locator('#search-result')).to_contain_text('1 of 2 outputs')
    p.get_by_role('searchbox').fill('not-a-real-phrase-829291')
    expect(p.locator('#empty-result')).to_be_visible()
    expect(p.locator('.message-text')).to_have_count(0)
    p.get_by_role('button',name='Clear search').click()
    expect(p.locator('[data-item-index]')).to_have_count(2)

def test_evidence_modal_focus_and_escape(app):
    p,_,_=app
    b=p.get_by_role('button',name='Inspect capture evidence')
    b.click()
    expect(p.get_by_role('dialog')).to_be_visible()
    expect(p.get_by_role('dialog')).to_contain_text(CAP['items'][0]['source']['sha256'])
    expect(p.get_by_role('dialog')).to_contain_text('Provider history not established')
    p.keyboard.press('Escape')
    expect(p.get_by_role('dialog')).not_to_be_visible()
    expect(b).to_be_focused()

def test_connections_only_recorded_edges(app):
    p,_,_=app
    p.get_by_role('button',name='Inspect recorded connections').click()
    expect(p.get_by_role('dialog')).to_contain_text('Recorded round')
    expect(p.get_by_role('dialog')).to_contain_text('Review target')
    expect(p.get_by_role('dialog')).to_contain_text('Executive Job not linked')
    assert p.get_by_role('dialog').locator('[data-relation]').count()==len(CAP['relations'])

def test_no_provider_controls_or_external_requests(app):
    p,errors,requests=app
    for title in ['Send','Run','Stop','Approve','Resume','Regenerate']:
        assert p.get_by_role('button',name=title,exact=True).count()==0
    assert p.locator('textarea').count()==0
    assert len([u for u in requests if u.startswith(('http:','https:','ws:','wss:'))])==0
    assert not errors

def test_keyboard_search_and_text_size(app):
    p,_,_=app
    p.keyboard.press('/')
    expect(p.get_by_role('searchbox')).to_be_focused()
    before=p.locator('.message-text').evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)')
    p.get_by_role('button',name='Increase reading size').click()
    after=p.locator('.message-text').evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)')
    assert after>before

def test_mobile_no_horizontal_overflow(app):
    p,_,_=app;p.set_viewport_size({'width':390,'height':844})
    assert p.evaluate('document.documentElement.scrollWidth')<=390
    p.get_by_role('button',name='Compare outputs',exact=True).click()
    assert p.evaluate('document.documentElement.scrollWidth')<=390
    expect(p.locator('.message-text')).to_have_count(2)

def test_200_percent_reading_zoom(app):
    p,_,_=app
    for _ in range(5):p.get_by_role('button',name='Increase reading size').click()
    assert p.evaluate('document.documentElement.scrollWidth')<=1440
    assert p.locator('.message-text').inner_text()==CAP['items'][0]['text']

@pytest.mark.parametrize('attack',[
 '</script><script>window.pwned=1</script>',
 '<img src="https://attacker.invalid" onerror="window.pwned=1">',
 '<svg onload="window.pwned=1"></svg>',
 '[click](javascript:window.pwned=1)',
])
def test_hostile_body_is_inert(browser,tmp_path,attack):
    c=copy.deepcopy(CAP);c['items'][0]['text']=attack
    c['items'][0]['display_sha256']=hashlib.sha256(attack.encode()).hexdigest()
    f=tmp_path/'hostile.html';f.write_text(render_capture(json.dumps(c).encode()))
    pg=browser.new_page();requests=[];pg.on('request',lambda r:requests.append(r.url))
    pg.set_content(f.read_text())
    assert pg.locator('.message-text').inner_text()==attack
    assert pg.evaluate('window.pwned') is None
    assert pg.locator('.message-text img, .message-text svg, .message-text script, .message-text a').count()==0
    assert not any(x.startswith(('http:','https:')) for x in requests)
    pg.close()

def test_empty_capture_not_fake_chat(browser,tmp_path):
    c=copy.deepcopy(CAP);c['items']=[];c['relations']=[];c['review']=None
    f=tmp_path/'empty.html';f.write_text(render_capture(json.dumps(c).encode()))
    pg=browser.new_page();pg.set_content(f.read_text())
    expect(pg.locator('#empty-result')).to_contain_text('No outputs in this capture')
    assert pg.locator('.message-text').count()==0
    pg.close()

def test_unicode_search_preserves_original_text(browser,tmp_path):
    c=copy.deepcopy(CAP);text='İ x: a Unicode search must preserve every source character.'
    c['items'][0]['text']=text;c['items'][0]['display_sha256']=hashlib.sha256(text.encode()).hexdigest()
    pg=browser.new_page();pg.set_content(render_capture(json.dumps(c).encode()))
    pg.get_by_role('searchbox').fill('x')
    assert pg.locator('.message-text').inner_text()==text
    assert pg.locator('mark').first.inner_text()=='x'
    pg.close()

def test_search_regex_symbols_are_literal(app):
    p,_,_=app
    p.get_by_role('searchbox').fill('.*')
    expect(p.locator('#empty-result')).to_be_visible()

def test_inspection_preserves_reading_scroll(app):
    p,_,_=app;p.locator('[data-item-index="1"]').click()
    body=p.locator('.message-text');body.evaluate('(n)=>{n.scrollTop=170;}')
    before=body.evaluate('(n)=>n.scrollTop')
    p.get_by_role('button',name='Inspect capture evidence').click();p.keyboard.press('Escape')
    assert body.evaluate('(n)=>n.scrollTop')==before
