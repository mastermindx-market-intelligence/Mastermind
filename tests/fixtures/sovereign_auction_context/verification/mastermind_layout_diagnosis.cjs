// Read-only source diagnosis. Serves exact Git/current/candidate HTML from memory
// through intercepted loopback page requests; creates no remote source/proof file.
// This is browser CSS evidence, not the final actual FastAPI harness acceptance.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const crypto = require('node:crypto');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const proofDir = process.argv[2] || '/tmp/sovereign-auction-mastermind-ui-proof-01';
const receipt = JSON.parse(fs.readFileSync(path.join(proofDir, 'browser_receipt.json'), 'utf8'));
const arg = name => receipt.harnessProcess.args[receipt.harnessProcess.args.indexOf(name) + 1];
const root = arg('--mastermind-root');
const prior = cp.execFileSync('git', ['-C', root, 'show', 'c7e47c859eb2925c5626931fd511800773ba09ac:app/static/market_view.html'], {encoding: 'utf8'});
const current = fs.readFileSync(path.join(root, 'app/static/market_view.html'), 'utf8');
if (sha(current) !== 'ea065f214c49c053fa584eb1143631f9b09bee5f7a3563b9c5e7237178d70daa') throw new Error('Unpatched source preimage differs; do not diagnose a different revision');
const patched = current.replace('.auction-context h3 { font-size: 13px; margin: 16px 0 8px; }\n',
    '.auction-context h3 { font-size: 13px; margin: 16px 0 8px; }\nbody.page-mv .auction-context .brief-row > details { grid-column: 1 / -1; }\n')
  .replace('body.page-mv .panel {\n  margin: 0;', 'body.page-mv .panel {\n  min-width: 0;\n  margin: 0;');
if (sha(patched) !== 'b8d84a7313bdd7c9f4bbcc3ddfeadaaeddd85b9976ca143a64acaf5146c8a043') throw new Error('In-memory candidate does not match the local two-line patch');
const theme = fs.readFileSync(path.join(root, 'app/static/theme.css'));
const python = [
  'import ast,importlib.util,json,sys',
  'from pathlib import Path',
  'sys.dont_write_bytecode=True',
  'root,macro,data,cutoff=map(str,sys.argv[1:])',
  'def load(name,path):',
  ' spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module',
  'producer=load("ui_w1",Path(macro)/"engine/treasury_auction_lifecycle.py")',
  'reader=load("ui_reader",Path(root)/"brain/sovereign_auction_context.py")',
  'tree=ast.parse((Path(root)/"tests/test_sovereign_auction_api.py").read_text())',
  'fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="frozen_view")',
  'base=ast.literal_eval(fn.body[0].value)',
  'context=reader.validate_context(producer.snapshot(data_dir=Path(data),as_of=cutoff,horizon_days=30),now=cutoff)',
  'print(json.dumps({"base":base,"observed":{**base,"sovereign_auction_context":context},"unavailable":{**base,"sovereign_auction_context":reader.unavailable("sovereign_auction_context_not_published")}}))',
].join('\n');
const payload = JSON.parse(cp.execFileSync(receipt.harnessProcess.python, ['-c', python, root, arg('--macro-root'), arg('--capture-data-root'), arg('--cutoff')],
  {encoding: 'utf8', maxBuffer: 4 * 1024 * 1024, env: {...process.env, PYTHONDONTWRITEBYTECODE: '1'}}));
const {chromium} = require(receipt.playwright_module);

async function measure(page) {
  return await page.evaluate(() => {
    const panel = document.querySelector('.auction-context');
    const table = document.querySelector('.mv-table-scroll');
    const cards = panel ? [...panel.querySelectorAll('.pair')].filter(e => !e.closest('details:not([open])')) : [];
    return {viewport: innerWidth, document: document.documentElement.scrollWidth,
      rootWidth: document.querySelector('#mv-root').getBoundingClientRect().width,
      auctionWidth: panel?.getBoundingClientRect().width ?? null,
      table: {client: table.clientWidth, scroll: table.scrollWidth, overflow: getComputedStyle(table).overflowX,
        containingPanelWidth: table.closest('.panel').getBoundingClientRect().width,
        containingPanelMinWidth: getComputedStyle(table.closest('.panel')).minWidth},
      visibleCards: cards.length, minCardWidth: cards.length ? Math.min(...cards.map(e => e.getBoundingClientRect().width)) : null};
  });
}

(async () => {
  const browser = await chromium.launch({headless: true, args: ['--disable-background-networking', '--disable-component-update', '--disable-sync']});
  const output = {scope: 'Read-only in-memory browser diagnosis; exact Git baseline and exact candidate bytes; intercepted loopback requests; no source file write or FastAPI acceptance claim.',
    source: {incumbentHtml: sha(prior), currentHtml: sha(current), candidateHtml: sha(patched), theme: sha(theme)}, browser: browser.version(), results: []};
  try {
    const cases = [];
    for (const width of [1440, 820, 390]) {
      cases.push({width, lang: 'en', theme: 'light', source: 'incumbent_before_auction', html: prior, view: payload.base});
      cases.push({width, lang: 'en', theme: 'light', source: 'current_unavailable', html: current, view: payload.unavailable});
      cases.push({width, lang: 'en', theme: 'light', source: 'patched_unavailable', html: patched, view: payload.unavailable});
      for (const lang of ['en', 'zh']) for (const themeName of ['light', 'dark']) cases.push({width, lang, theme: themeName, source: 'patched_observed', html: patched, view: payload.observed});
    }
    for (const item of cases) {
      const ctx = await browser.newContext({viewport: {width: item.width, height: item.width === 820 ? 1180 : item.width === 1440 ? 900 : 844}, colorScheme: item.theme, serviceWorkers: 'block'});
      const errors = [], blocked = [];
      await ctx.addInitScript(({lang, theme}) => {try {localStorage.setItem('lang', lang);localStorage.setItem('theme', theme);} catch (_) {}}, {lang: item.lang, theme: item.theme});
      await ctx.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== 'http://127.0.0.1:49197') {blocked.push(url.href);return route.abort();}
        if (url.pathname === '/market_view') return route.fulfill({status: 200, contentType: 'text/html', body: item.html});
        if (url.pathname === '/theme.css') return route.fulfill({status: 200, contentType: 'text/css', body: theme});
        if (url.pathname === '/api/market_view') return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(item.view)});
        return route.fulfill({status: 204, body: ''});
      });
      const page = await ctx.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto('http://127.0.0.1:49197/market_view', {waitUntil: 'domcontentloaded'});
      await page.locator('.mv-table-scroll').waitFor();
      await page.evaluate(() => document.fonts.ready);
      const result = {width: item.width, lang: item.lang, theme: item.theme, source: item.source, initial: await measure(page), expanded: [], errors, blocked};
      if (item.source === 'patched_observed') {
        const headings = page.locator('.auction-context h3');
        for (let i = 0; i < await headings.count(); i++) {
          const summary = headings.nth(i).locator('..').locator(':scope > details > summary');
          if (!await summary.count()) continue;
          await summary.click();
          result.expanded.push({heading: await headings.nth(i).innerText(), geometry: await measure(page)});
          await summary.click();
        }
      }
      output.results.push(result);
      await ctx.close();
    }
    console.log('DIAGNOSIS_JSON ' + JSON.stringify(output));
  } finally {await browser.close();}
})().catch(error => {console.error(error.stack || error);process.exitCode=1;});
