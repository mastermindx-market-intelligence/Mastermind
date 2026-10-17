/* Browser-only acceptance. All responses are intercepted; no live server,
 * portfolio files, credentials or provider are accessed. Backend behavior is
 * tested independently by test_decision_snapshot_api.py. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '..');
const out = path.resolve(root, '.venv/evidence-browser/results');
fs.mkdirSync(out, { recursive: true });
const ID = 'sha256:' + 'a'.repeat(64);
const SECOND = 'sha256:' + 'b'.repeat(64);
const authority = { write_permitted: false, execution_authority: false, numeric_target_authority: false };
const sourceFiles = {
  '/decision-evidence': ['decision-evidence.html', 'text/html'],
  '/decision-evidence.js': ['decision-evidence.js', 'text/javascript'],
  '/decision-evidence.css': ['decision-evidence.css', 'text/css'],
  '/theme.css': ['theme.css', 'text/css'],
};

function response(scenario, query) {
  const state = scenario === 'complete' ? 'COMPLETE' : scenario === 'corrected' ? 'CORRECTED_GENERATION_AVAILABLE' : 'PARTIAL';
  const id = query.get('snapshot_id') || (scenario === 'corrected' ? SECOND : ID);
  const manifest = { snapshot_id: id, book: 'autonomous', state, coverage_state: scenario === 'complete' ? 'COMPLETE' : 'PARTIAL',
    decision_cutoff: '2026-09-15T20:00:00Z', recorded_at: '2026-09-15T20:01:00Z',
    summary: { sources_available: 1, sources_total: 12, domains_complete: scenario === 'complete' ? 12 : 1, domains_partial: scenario === 'complete' ? 0 : 11, domains_blocked: 0 },
    correction: {status:scenario==='corrected'?'CORRECTED_GENERATION_AVAILABLE':'ORIGINAL',same_cutoff_prior_snapshot_ids:scenario==='corrected'?[ID]:[]}, authority };
  if (scenario === 'absent') return {status:'ABSENT',book:'autonomous',snapshot:null,snapshots:[],section:null,authority};
  const total = scenario === 'paged' ? 45 : 1;
  const offset = Number(query.get('offset') || 0), limit = Number(query.get('limit') || 20);
  const rows = Array.from({length:total}, (_,i)=>({kind:scenario==='xss'?'<img src=x onerror="window.evidenceXss=1">':'SYNTHETIC BROWSER FIXTURE',sequence:i+1,source_id:'fixture.account',note:'Test data, not a real portfolio'}));
  const section = query.get('section') ? {section_id:query.get('section'),snapshot_id:scenario==='wrong_identity'?SECOND:id,
    coverage_state:'PARTIAL',rows_total:total,stored_rows:total,omitted_rows:0,
    rows:rows.slice(offset,offset+limit),rows_returned:rows.slice(offset,offset+limit).length,
    source_ids:['fixture.account'],gaps:[{code:'SYNTHETIC_FIXTURE',source_id:'fixture.account',detail:'Browser response double; no production evidence'}],
    next_offset:offset+limit<total?offset+limit:null} : null;
  return {status:'AVAILABLE',book:'autonomous',snapshot:manifest,snapshots:scenario==='corrected'?[manifest,{...manifest,snapshot_id:ID,state:'PARTIAL'}]:[manifest],section,authority};
}

(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const results=[];
  try {
    for(const width of [1440,768,390]) {
      for(const theme of ['dark','light']) {
        for(const scenario of ['absent','partial','complete','corrected','locked','corrupt','unavailable']) {
          const context=await browser.newContext({viewport:{width,height:1000}});
          const page=await context.newPage(); const errors=[];
          page.on('pageerror',error=>errors.push(String(error)));
          await page.route('**/*',async route=>{
            const u=new URL(route.request().url());
            if(u.origin!=='http://evidence.test')return route.abort();
            if(sourceFiles[u.pathname]) {
              const [file,type]=sourceFiles[u.pathname];
              return route.fulfill({status:200,contentType:type,body:fs.readFileSync(path.join(root,'app/static',file))});
            }
            if(u.pathname==='/api/decision-snapshot') {
              const status={locked:401,corrupt:409,unavailable:503}[scenario]||200;
              return route.fulfill({status,contentType:'application/json',body:JSON.stringify(status===200?response(scenario,u.searchParams):{error:'fixture'})});
            }
            return route.fulfill({status:404,body:''});
          });
          await page.goto('http://evidence.test/decision-evidence');
          const expected={absent:'No snapshot available',partial:'partial evidence',complete:'complete evidence',corrected:'Corrected generation',locked:'Operator authorization required',corrupt:'Evidence integrity check failed',unavailable:'Evidence unavailable'}[scenario];
          await page.locator('#status').filter({hasText:expected}).waitFor();
          if(['partial','complete','corrected'].includes(scenario))await page.locator('.row-card').first().waitFor();
          if(theme==='light')await page.locator('#theme-toggle').click();
          assert.equal(await page.locator('html').getAttribute('data-theme'),theme);
          assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`${scenario} overflow at ${width}`);
          assert.deepEqual(errors,[]);
          assert.equal(await page.locator('#domain-list button').count(),12);
          if(['absent','locked','corrupt','unavailable'].includes(scenario)) assert.equal(await page.locator('#domain-list button:disabled').count(),12);
          if(scenario==='partial'&&['1440','390'].includes(String(width))&&theme==='dark') await page.screenshot({path:path.join(out,`evidence-${width}.png`),fullPage:true});
          results.push({width,theme,scenario,passed:true});await context.close();
        }
      }
    }
    for(const scenario of ['paged','xss','wrong_identity','stale_response']) {
      const context=await browser.newContext();const page=await context.newPage();let requests=[];
      await page.route('**/*',async route=>{
        const u=new URL(route.request().url());
        if(u.origin!=='http://evidence.test')return route.abort();
        if(sourceFiles[u.pathname]) {const [file,type]=sourceFiles[u.pathname];return route.fulfill({status:200,contentType:type,body:fs.readFileSync(path.join(root,'app/static',file))});}
        if(u.pathname!=='/api/decision-snapshot')return route.fulfill({status:404,body:''});
        requests.push(Object.fromEntries(u.searchParams));
        if(scenario==='stale_response' && u.searchParams.get('section')==='risk_truth') await new Promise(r=>setTimeout(r,250));
        const d=response(scenario,u.searchParams);
        if(d.section)d.section.rows[0].note=u.searchParams.get('section');
        try {await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(d)});}catch(e){if(!String(e).match(/closed|cancel|abort/i))throw e;}
      });
      await page.goto('http://evidence.test/decision-evidence');
      if(scenario==='wrong_identity') {
        await page.locator('#status').filter({hasText:'Evidence unavailable'}).waitFor();
        assert.equal(await page.locator('.row-card').count(),0);
      } else {
        await page.locator('.row-card').first().waitFor();
        if(scenario==='paged') {
          assert.match(await page.locator('#page-label').textContent(),/1–20/);
          await page.locator('#next-page').click(); await page.locator('#page-label').filter({hasText:'21–40'}).waitFor();
          await page.locator('#next-page').click(); await page.locator('#page-label').filter({hasText:'41–45'}).waitFor();
          assert.equal(await page.locator('#next-page').isDisabled(),true);
          await page.locator('#previous-page').click();await page.locator('#page-label').filter({hasText:'21–40'}).waitFor();
          assert.ok(requests.filter(r=>r.section).every(r=>r.snapshot_id===ID));
        } else if(scenario==='xss') {
          assert.equal(await page.locator('#rows img').count(),0);
          assert.equal(await page.evaluate(()=>window.evidenceXss),undefined);
          assert.match(await page.locator('#rows').textContent(),/<img src=x/);
        } else {
          await page.locator('[data-domain="risk_truth"]').click();
          await page.locator('[data-domain="event_state"]').click();
          await page.locator('#rows').filter({hasText:'event_state'}).waitFor();
          await page.waitForTimeout(350);
          assert.match(await page.locator('#domain-title').textContent(),/Events/);
          assert.doesNotMatch(await page.locator('#rows').textContent(),/risk_truth/);
        }
      }
      results.push({scenario,passed:true});await context.close();
    }
    fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({scope:'browser rendering and request identity with intercepted responses; not server/production proof',browser:browser.version(),cases:results},null,2));
    console.log(JSON.stringify({passed:results.length,scope:'intercepted browser acceptance',browser:browser.version()}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
