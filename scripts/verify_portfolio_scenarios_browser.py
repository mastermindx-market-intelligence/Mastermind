"""Local synthetic HTTP/browser proof of the shipped dashboard scenario panel.

Loads the actual FastAPI application without lifespan or scheduler startup.
Only the external vendor bootstrap path and instrument-identity observations are
synthetic. The real auth middleware, native valuation, scenario engine, API,
HTML, CSS and JS execute. No customer account, token, market feed or production
service is read. Not deployment or authenticated production acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect

from app import auth, portfolio_scenarios as api
from portfolio import instrument_policy, paper_account
from tests.test_portfolio_scenarios_api import HEADERS, NOW, TOKEN, payload


def forbidden(*args, **kwargs):
    raise AssertionError('Browser verification must not load, write or transact accounts')


def verify(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    deps = types.ModuleType('app.deps')
    deps.data_dir = lambda: '/unused-synthetic-data-root'
    with patch.dict('os.environ', {
            'MASTERMIND_AUTH_TOKEN': TOKEN, 'MASTERMIND_VPS_AUTHORITATIVE': '1',
            'MASTERMIND_SERVE_ONLY': '0'}), patch.dict(sys.modules, {'app.deps': deps}), \
         patch.object(api, '_now', lambda: NOW), \
         patch.object(instrument_policy, 'classify_instrument', lambda pid, key: {
             'ticker':key,'kind':'common_stock','verified':True,'market':pid,
             'status':'synthetic-browser-fixture-only'}), \
         patch.object(paper_account, '_load_account', forbidden), \
         patch.object(paper_account, '_save_account', forbidden), \
         patch.object(paper_account, 'mark', forbidden), \
         patch.object(paper_account, 'rebalance', forbidden):
        from app import main, scheduler
        with patch.object(scheduler, 'start', forbidden):
            client = TestClient(main.app)  # no lifespan; never starts app runtime jobs
            state = {'posts':0,'delay':False,'last_status':None}
            seen, release = threading.Event(), threading.Event()
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_):
                    pass
                def do_GET(self):
                    if self.path.split('?',1)[0] not in {
                        '/', '/portfolio-scenarios.js', '/portfolio-scenarios.css',
                        '/theme.css', '/theme.js', '/account.js', '/chat.js'}:
                        self.send_response(503);self.send_header('Content-Type','application/json')
                        self.end_headers();self.wfile.write(b'{"status":"unavailable","fixture_only":true}')
                        return
                    response = client.get(self.path)
                    self.send_response(response.status_code)
                    for k,v in response.headers.items():
                        if k.lower() not in {'content-length','transfer-encoding','content-encoding'}:
                            self.send_header(k,v)
                    self.end_headers();self.wfile.write(response.content)
                def do_POST(self):
                    if self.path != api.PATH:
                        self.send_response(404);self.end_headers();return
                    body = self.rfile.read(min(int(self.headers.get('Content-Length','0')),api.MAX_BODY_BYTES+1))
                    response = client.post(api.PATH, content=body, headers={
                        'Authorization':self.headers.get('Authorization',''),
                        'Content-Type':self.headers.get('Content-Type','')})
                    state['posts'] += 1;state['last_status'] = response.status_code
                    if state['delay']:
                        seen.set();release.wait(8);state['delay'] = False
                    self.send_response(response.status_code)
                    for k,v in response.headers.items():
                        if k.lower() not in {'content-length','transfer-encoding','content-encoding'}:
                            self.send_header(k,v)
                    self.end_headers()
                    try:self.wfile.write(response.content)
                    except (BrokenPipeError,ConnectionResetError):pass
            server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            worker = threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            origin = 'http://127.0.0.1:' + str(server.server_address[1])
            results = []
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    for width,height in [(1440,1000),(820,1180),(390,844)]:
                        for lang,theme in [('en','light'),('zh','dark')]:
                            auth._operator_limiter.reset()
                            context = browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1)
                            page = context.new_page();errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.add_init_script('localStorage.setItem("lang",'+json.dumps(lang)+');localStorage.setItem("theme",'+json.dumps(theme)+');')
                            # No third-party resources or real API work may occur in this proof.
                            page.route('**/*',lambda route: route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
                            page.goto(origin+'/#/autonomous/opportunities',wait_until='domcontentloaded')
                            lab = page.locator('#portfolio-scenario-lab')
                            expect(lab.locator('summary')).to_be_visible(timeout=15000)
                            lab.locator('summary').focus();page.keyboard.press('Enter')
                            expect(lab.locator('details')).to_have_attribute('open','')
                            start_posts=state['posts']
                            expect(page.locator('#scenario-run')).to_be_disabled()
                            page.locator('#scenario-file').set_input_files({
                                'name':'synthetic-scenarios.json','mimeType':'application/json',
                                'buffer':json.dumps(payload()).encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled()
                            assert state['posts']==start_posts
                            page.locator('#scenario-token').fill(TOKEN)
                            page.locator('#scenario-run').click()
                            expect(page.locator('#scenario-results table')).to_be_visible()
                            expect(page.locator('#scenario-token')).to_have_value('')
                            expect(page.locator('#scenario-results')).to_contain_text('+6.024')
                            expect(page.locator('#scenario-results')).to_contain_text('-5.960%')
                            assert state['last_status']==200 and state['posts']==start_posts+1
                            assert page.evaluate('(needle)=>!JSON.stringify([localStorage,sessionStorage,location.href]).includes(needle)',TOKEN)
                            assert not page.locator('#scenario-results').get_by_role('button').count()
                            assert lab.evaluate('(e)=>e.scrollWidth-e.clientWidth')<=1
                            label=f'{width}-{lang}-{theme}'
                            lab.screenshot(path=str(output/(label+'-qualified.png')))
                            cases=['real_http_native_comparison','no_automatic_submission','credential_cleared','keyboard','viewport','storage_absence']

                            # A positive stress delta cannot conceal native policy ineligibility.
                            bad=payload();bad['mandate']['constraints']['max_turnover_fraction']=.1
                            page.locator('#scenario-file').set_input_files({'name':'constraint.json','mimeType':'application/json','buffer':json.dumps(bad).encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled();page.locator('#scenario-token').fill(TOKEN);page.locator('#scenario-run').click()
                            expect(page.locator('.scenario-ineligible')).to_have_count(2)
                            expect(page.locator('#scenario-results')).to_contain_text('Turnover limit exceeded' if lang=='en' else '\u6362\u624b\u7387\u8d85\u51fa\u9650\u5236')
                            expect(page.locator('#scenario-results')).to_contain_text('+6.024')
                            lab.screenshot(path=str(output/(label+'-constraints.png')));cases.append('positive_delta_still_ineligible')

                            # A language toggle is presentation-only, not another private POST.
                            before_language = state['posts']
                            other = 'zh' if lang == 'en' else 'en'
                            page.evaluate('(v)=>document.documentElement.setAttribute("data-lang",v)', other)
                            expect(page.locator('#scenario-results')).to_contain_text('Outside mandate' if other=='en' else '\u8d85\u51fa\u7ec4\u5408\u9650\u5236')
                            page.evaluate('(v)=>document.documentElement.setAttribute("data-lang",v)', lang)
                            assert state['posts'] == before_language
                            if width == 390:
                                warning=page.locator('.scenario-ineligible td:last-child').first
                                assert warning.evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth')
                                assert lab.locator('tbody th').first.evaluate('(e)=>e.getBoundingClientRect().width') > 200
                            cases.extend(['language_change_no_post','constraint_visible_on_phone'])

                            # Reset aborts the actual pending HTTP request; its late response cannot repaint.
                            state['delay']=True;seen.clear();release.clear()
                            page.locator('#scenario-token').fill(TOKEN);page.locator('#scenario-run').click()
                            assert seen.wait(5)
                            page.locator('#scenario-clear').click();release.set()
                            expect(page.locator('#scenario-results table')).to_have_count(0)
                            expect(page.locator('#scenario-run')).to_be_disabled()
                            page.wait_for_timeout(150)
                            expect(page.locator('#scenario-results table')).to_have_count(0);cases.append('late_result_withdrawn')

                            # An original duplicate-key packet must reach the server unchanged.
                            raw=json.dumps(payload()).replace('"schema":','"schema":"invalid","schema":',1)
                            page.locator('#scenario-file').set_input_files({'name':'duplicate.json','mimeType':'application/json','buffer':raw.encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled();page.locator('#scenario-token').fill(TOKEN);page.locator('#scenario-run').click()
                            expect(page.locator('#scenario-status')).to_contain_text('No zero-return' if lang=='en' else '\u4e0d\u4f1a\u7528\u96f6\u6536\u76ca')
                            assert state['last_status']==400;cases.append('duplicate_keys_not_laundered')

                            # The real operator boundary denies a wrong key without reusing the old result.
                            page.locator('#scenario-file').set_input_files({'name':'authorized-input.json','mimeType':'application/json','buffer':json.dumps(payload()).encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled();page.locator('#scenario-token').fill('synthetic-wrong-key');page.locator('#scenario-run').click()
                            expect(page.locator('#scenario-status')).to_contain_text('refused' if lang=='en' else '\u62d2\u7edd')
                            expect(page.locator('#scenario-results table')).to_have_count(0)
                            expect(page.locator('#scenario-token')).to_have_value('');assert state['last_status']==401;cases.append('real_operator_denial')

                            # Missing evidence remains unavailable, never a zero-return row.
                            incomplete=payload();incomplete['prices']={}
                            page.locator('#scenario-file').set_input_files({'name':'missing-price.json','mimeType':'application/json','buffer':json.dumps(incomplete).encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled();page.locator('#scenario-token').fill(TOKEN);page.locator('#scenario-run').click()
                            expect(page.locator('#scenario-results')).to_contain_text('No qualified comparison' if lang=='en' else '\u6ca1\u6709\u5408\u683c\u7684\u6bd4\u8f83')
                            expect(page.locator('#scenario-results table')).to_have_count(0);cases.append('missing_prices_not_zero')
                            # Returned action authority is never accepted, even from an HTTP 200.
                            unsafe=client.post(api.PATH,json=payload(),headers=HEADERS).json()
                            unsafe['authority']['can_trade']=True
                            page.route('**'+api.PATH,lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(unsafe)))
                            page.locator('#scenario-file').set_input_files({'name':'safe-input.json','mimeType':'application/json','buffer':json.dumps(payload()).encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled();page.locator('#scenario-token').fill(TOKEN);page.locator('#scenario-run').click()
                            expect(page.locator('#scenario-status')).to_contain_text('read-only contract' if lang=='en' else '\u53ea\u8bfb\u5408\u540c')
                            expect(page.locator('#scenario-results table')).to_have_count(0)
                            page.unroute('**'+api.PATH);cases.append('unsafe_authority_response_withdrawn')

                            # Untrusted alternative labels remain text, not executable markup.
                            hostile=payload();hostile['alternatives'][0]['alternative_id']='<img src=x onerror="window.scenarioInjected=true">'
                            page.locator('#scenario-file').set_input_files({'name':'hostile-label.json','mimeType':'application/json','buffer':json.dumps(hostile).encode()})
                            expect(page.locator('#scenario-run')).to_be_enabled();page.locator('#scenario-token').fill(TOKEN);page.locator('#scenario-run').click()
                            expect(page.locator('#scenario-results table')).to_be_visible()
                            expect(page.locator('#scenario-results')).to_contain_text('<img src=x')
                            assert page.locator('#scenario-results img').count()==0
                            assert page.evaluate('window.scenarioInjected===undefined')
                            cases.append('source_labels_not_html')
                            page.locator('#scenario-clear').click()
                            assert lab.evaluate('(e)=>e.scrollWidth-e.clientWidth')<=1
                            results.append({'viewport':[width,height],'language':lang,'theme':theme,'cases':cases,
                                            'posts':state['posts']-start_posts,'page_errors':errors})
                            context.close()
                    browser.close()
            finally:
                release.set();server.shutdown();server.server_close();client.close();worker.join(timeout=3)
            auth._operator_limiter.reset()
            hashes={}
            for relative in ['app/static/index.html','app/static/portfolio_scenarios.js','app/static/portfolio_scenarios.css',
                             'app/portfolio_scenarios.py','portfolio/global_scenario_account.py','portfolio/global_scenario_context.py',
                             'portfolio/global_scenario_summary.py','app/auth.py','app/main.py',
                             'scripts/verify_portfolio_scenarios_browser.py']:
                hashes[relative]=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
            captures=[{'file':f.name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
                      for f in sorted(output.glob('*.png'))]
            receipt={'schema':'mastermind.scenario_browser_receipt/v1','scope':'local_synthetic_http_not_production',
                     'source_hashes':hashes,'matrices':results,'captures':captures,
                     'account_io':False,'production':False,'scheduler_started':False,
                     'bootstrap_stub':'app.deps.data_dir only','instrument_identity':'synthetic-only',
                     'total_matrices':len(results),'total_behavior_assertions':sum(len(x['cases']) for x in results)}
            (output/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
            return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    r=verify(args.output)
    print(json.dumps({'matrices':r['total_matrices'],'behavior_assertions':r['total_behavior_assertions'],
                      'captures':len(r['captures']),'page_errors':[x['page_errors'] for x in r['matrices']],
                      'scope':r['scope']},sort_keys=True))
