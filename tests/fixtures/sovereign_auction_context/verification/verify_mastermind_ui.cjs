#!/usr/bin/env node
// Actual Chromium browser proof of the existing page, through a loopback-only
// FastAPI fixture harness. No production app, provider jobs, credentials or UI
// substitute. See README for the explicit fixture and proof boundaries.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');
const readline = require('node:readline');

function parseArgs(argv) {
  const values = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!argv[i].startsWith('--') || argv[i + 1] == null) throw new Error('Arguments must be --name value pairs');
    values[argv[i].slice(2)] = argv[i + 1];
  }
  for (const key of ['mastermind-root', 'macro-root', 'capture-data-root', 'playwright-root', 'out-dir']) {
    if (!values[key]) throw new Error(`Missing --${key}; see README_mastermind_ui.md`);
  }
  return values;
}
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const safeName = value => value.replace(/[^a-zA-Z0-9_-]/g, '_');
const labels = {
  en: {title: 'Sovereign auctions — observed context', fresh: 'Freshness unassessed',
    groups: {ANNOUNCED: 'Scheduled auctions', AWAITING_RESULT: 'Awaiting results', TENTATIVE: 'Tentative calendar', RESULT_OBSERVED: 'Observed results'},
    unknownAmount: 'Offering amount: Unknown', unknownDeadline: 'Competitive deadline: Unknown',
    noResult: 'Results not observed', unavailable: 'Unavailable', sourceDetails: 'Source details', degraded: 'Source coverage degraded'},
  zh: {title: '国债拍卖 — 已观察背景', fresh: '新鲜度未评估',
    groups: {ANNOUNCED: '计划拍卖', AWAITING_RESULT: '等待结果', TENTATIVE: '暂定日历', RESULT_OBSERVED: '已观察结果'},
    unknownAmount: '发行金额: 未知', unknownDeadline: '竞争性投标截止时间: 未知',
    noResult: '尚未观察到结果', unavailable: '不可用', sourceDetails: '来源详情', degraded: '来源覆盖降级'},
};
function expectedDollars(value) {
  const parts = String(value).match(/^([+-]?)(\d+)(\.\d*)?$/);
  return (parts ? parts[1] + parts[2].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (parts[3] || '') : String(value)) + ' USD';
}
const expectedDeadline = value => String(value).replace('T', ' ').replace(/(?:Z|\+00:00)$/, ' UTC');

async function startHarness(args, outDir, receipt) {
  const script = path.join(__dirname, 'mastermind_loopback_harness.py');
  const command = [script, '--mastermind-root', path.resolve(args['mastermind-root']),
    '--macro-root', path.resolve(args['macro-root']), '--capture-data-root', path.resolve(args['capture-data-root']),
    '--out-dir', outDir, '--cutoff', args.cutoff || '2026-10-08T23:00:00Z'];
  if (args['fixture-feed']) command.push('--fixture-feed', path.resolve(args['fixture-feed']));
  const child = spawn(args.python || 'python3', command, {
    cwd: path.resolve(args['mastermind-root']), stdio: ['ignore', 'pipe', 'pipe'],
    env: {...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONUNBUFFERED: '1'},
  });
  receipt.harnessProcess = {pid: child.pid, python: args.python || 'python3', args: command};
  const log = fs.createWriteStream(path.join(outDir, 'harness_process.log'), {flags: 'wx'});
  child.stdout.on('data', chunk => log.write(chunk));
  child.stderr.on('data', chunk => log.write(chunk));
  child.once('exit', () => log.end());
  const lines = readline.createInterface({input: child.stdout});
  const ready = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {child.kill('SIGTERM'); reject(new Error('Loopback harness startup exceeded 30 seconds'));}, 30000);
    child.once('error', error => {clearTimeout(timer); reject(error);});
    child.once('exit', code => {clearTimeout(timer); reject(new Error(`Loopback harness exited before ready (${code}); inspect harness_process.log`));});
    lines.on('line', line => {
      if (line.startsWith('HARNESS_READY ')) {
        clearTimeout(timer);
        try {resolve(JSON.parse(line.slice('HARNESS_READY '.length)));}
        catch (error) {child.kill('SIGTERM'); reject(error);}
      }
    });
  });
  lines.close();
  return {child, ready};
}

async function stopChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => {
    const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
    child.once('exit', () => {clearTimeout(timer); resolve();});
    child.kill('SIGTERM');
  });
}

async function geometry(page) {
  return await page.evaluate(() => {
    const panel = document.querySelector('.auction-context');
    const p = panel.getBoundingClientRect();
    const clipping = [];
    const visibleCards = [];
    for (const el of panel.querySelectorAll('*')) {
      if (!el.getClientRects().length) continue;
      const closed = el.closest('details:not([open])');
      if (closed && closed !== el && !closed.querySelector(':scope > summary')?.contains(el)) continue;
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      const tag = `${el.tagName.toLowerCase()}.${String(el.className).replace(/\s+/g, '.')}`;
      if (rect.left < p.left - 1 || rect.right > p.right + 1) clipping.push({tag, reason: 'outside_auction_panel', left: rect.left, right: rect.right});
      if (el.clientWidth && el.scrollWidth > el.clientWidth + 1 && ['hidden', 'clip'].includes(style.overflowX)) {
        clipping.push({tag, reason: 'horizontal_text_clipped', scrollWidth: el.scrollWidth, clientWidth: el.clientWidth});
      }
      if (el.clientHeight && el.scrollHeight > el.clientHeight + 1 && ['hidden', 'clip'].includes(style.overflowY)) {
        clipping.push({tag, reason: 'vertical_text_clipped', scrollHeight: el.scrollHeight, clientHeight: el.clientHeight});
      }
      if (el.classList.contains('pair')) visibleCards.push({width: rect.width, height: rect.height});
    }
    return {
      viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth,
      panel: {left: p.left, right: p.right, width: p.width, height: p.height}, clipping,
      visibleCardCount: visibleCards.length,
      minVisibleCardWidth: visibleCards.length ? Math.min(...visibleCards.map(c => c.width)) : null,
      theme: document.documentElement.getAttribute('data-theme'), lang: document.documentElement.getAttribute('data-lang'),
      bodyFont: getComputedStyle(document.body).fontFamily, bodyBackground: getComputedStyle(document.body).backgroundColor,
      fontStatus: document.fonts.status,
      fonts: [...document.fonts].map(font => ({family: font.family, status: font.status})),
    };
  });
}

function assertGeometry(value) {
  assert.ok(value.documentWidth <= value.viewportWidth + 1,
    `Document overflows horizontally: ${value.documentWidth}px > ${value.viewportWidth}px`);
  assert.ok(value.bodyWidth <= value.viewportWidth + 1,
    `Body overflows horizontally: ${value.bodyWidth}px > ${value.viewportWidth}px`);
  assert.ok(value.panel.left >= -1 && value.panel.right <= value.viewportWidth + 1,
    'Auction panel crosses viewport boundary');
  assert.deepEqual(value.clipping, [], 'Visible auction content extends beyond its panel or is clipped');
}

async function screenshot(page, locator, name, outDir, result) {
  if (locator) await locator.evaluate(el => window.scrollTo({top: el.getBoundingClientRect().top + window.scrollY - 12, behavior: 'instant'}));
  const file = path.join(outDir, 'screenshots', `${safeName(name)}.png`);
  const bytes = await page.screenshot({path: file, fullPage: false, animations: 'disabled'});
  result.screenshots.push({path: path.relative(outDir, file), sha256: sha(bytes), bytes: bytes.length});
}

async function runCase(browser, origin, manifest, cfg, outDir) {
  const result = {...cfg, status: 'running', screenshots: [], errors: [], warnings: [], blockedExternal: [], pageErrors: [], badLocalResponses: []};
  const context = await browser.newContext({viewport: {width: cfg.width, height: cfg.height}, deviceScaleFactor: 1,
    locale: cfg.lang === 'zh' ? 'zh-CN' : 'en-US', colorScheme: cfg.theme, serviceWorkers: 'block',
    extraHTTPHeaders: {'X-Sovereign-UI-Case': cfg.case}});
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin === origin || ['data:', 'blob:'].includes(url.protocol)) return route.continue();
    result.blockedExternal.push({url: url.href, resourceType: route.request().resourceType()});
    return route.abort('blockedbyclient');
  });
  await context.addInitScript(({lang, theme}) => {
    try {localStorage.setItem('lang', lang); localStorage.setItem('theme', theme);} catch (_) {}
  }, {lang: cfg.lang, theme: cfg.theme});
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', error => result.pageErrors.push(error.message));
  page.on('response', response => {
    if (response.url().startsWith(origin + '/') && response.status() >= 400) result.badLocalResponses.push({url: response.url(), status: response.status()});
  });
  const key = `${cfg.width}x${cfg.height}-${cfg.lang}-${cfg.theme}-${cfg.case}`;
  try {
    const apiReady = page.waitForResponse(response => response.url() === origin + '/api/market_view');
    await page.goto(origin + '/market_view', {waitUntil: 'domcontentloaded'});
    const apiResponse = await apiReady;
    assert.equal(apiResponse.status(), 200);
    assert.equal(apiResponse.headers()['cache-control'], 'no-cache');
    const bodyText = await apiResponse.text();
    const body = JSON.parse(bodyText);
    const expected = manifest.cases[cfg.case];
    assert.equal(sha(Buffer.from(bodyText)), expected.actual_api_response_sha256, 'HTTP payload differs from actual-handler preflight');
    const panel = page.locator('.auction-context');
    await panel.waitFor({state: 'visible'});
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('html').getAttribute('data-lang'), cfg.lang);
    assert.equal(await page.locator('html').getAttribute('data-theme'), cfg.theme);
    const text = await panel.innerText();
    const copy = labels[cfg.lang];
    assert.ok(text.includes(copy.title));
    assert.ok(text.includes(copy.fresh));
    if (expected.available) {
      assert.ok(text.includes(expected.source_observed_at), 'Source observation clock remains visible above the cards');
      assert.ok(text.includes(expected.decision_cutoff_utc), 'Producer cutoff remains visible above the cards');
    }
    assert.equal(body.sovereign_auction_context.available, expected.available);
    const headings = await panel.locator('h3').allTextContents();
    const expectedHeadings = ['ANNOUNCED', 'AWAITING_RESULT', 'TENTATIVE', 'RESULT_OBSERVED']
      .filter(state => expected.group_counts[state])
      .map(state => `${copy.groups[state]} (${expected.group_counts[state]})`);
    assert.deepEqual(headings, expectedHeadings, 'Scheduled/awaiting/tentative groups must precede observed past results');
    for (const row of expected.scheduled_rows) {
      const card = panel.locator('.pair').filter({hasText: row.episode_id});
      assert.equal(await card.count(), 1);
      assert.ok(await card.isVisible(), 'Each known upcoming auction must be visible before expansion');
      const cardText = await card.locator(':scope > .auction-row-summary').innerText();
      assert.ok(cardText.includes(expectedDollars(row.offering_amount_usd)), 'Grouped exact offering amount is visible');
      assert.ok(cardText.includes(expectedDeadline(row.competitive_deadline_utc)), 'Readable exact deadline is visible');
      assert.ok(!cardText.includes(row.episode_id) && !cardText.includes(row.known_at), 'Raw row identifiers and evidence clocks belong in Source details');
    }
    if (cfg.case === 'unavailable') {
      assert.ok(text.includes(copy.unavailable));
      assert.ok(text.includes('sovereign_auction_context_not_published'));
      assert.equal(await panel.locator('.pair').count(), 0);
    }
    if (cfg.case === 'source_failure') {
      assert.equal(body.sovereign_auction_context.status, 'degraded');
      assert.ok(text.includes(copy.degraded));
      assert.equal(body.sovereign_auction_context.source_observed_at, manifest.cases.observed.source_observed_at);
    }
    if (cfg.case === 'awaiting_unknown') {
      assert.ok(text.includes(copy.unknownAmount));
      assert.ok(text.includes(copy.unknownDeadline));
      assert.ok(text.includes(copy.noResult));
      assert.ok(!text.includes('Offering amount: 0'));
    }
    result.sourceDetailChecks = [];
    const events = body.sovereign_auction_context.events || [];
    const auditRows = [...new Map([
      ...events.filter(row => expected.scheduled_rows.some(scheduled => scheduled.episode_id === row.episode_id)),
      ...['ANNOUNCED', 'AWAITING_RESULT', 'TENTATIVE', 'RESULT_OBSERVED'].map(state => events.find(row => row.physical_state === state)).filter(Boolean),
    ].map(row => [row.episode_id, row])).values()];
    for (const row of auditRows) {
      const card = panel.locator('.pair').filter({hasText: row.episode_id});
      const source = card.locator(':scope > details.auction-source-details');
      assert.equal(await source.getAttribute('open'), null, 'Row audit disclosure is closed by default');
      assert.equal(await source.locator(':scope > summary').innerText(), copy.sourceDetails);
      const summaryText = await card.locator(':scope > .auction-row-summary').innerText();
      for (const raw of [row.episode_id, row.known_at, row.source_state, row.physical_state, ...(row.null_reasons || [])]) {
        assert.ok(!summaryText.includes(raw), `Raw source field leaked into card summary: ${raw}`);
      }
      await source.locator(':scope > summary').click();
      const auditText = await source.innerText();
      const exactValues = [row.episode_id, row.label, row.normalized_class, row.known_at, row.source_state, row.physical_state, row.issue_calendar_state,
        ...(row.offering_amount_usd == null ? [] : [String(row.offering_amount_usd)]),
        ...(row.competitive_deadline_utc == null ? [] : [row.competitive_deadline_utc]), ...(row.null_reasons || [])];
      for (const value of exactValues) assert.ok(auditText.includes(value), `Source details lost exact evidence: ${value}`);
      for (const [name, value] of Object.entries(row.result || {})) {
        assert.ok(auditText.includes(name));
        if (value != null) assert.ok(auditText.includes(String(value)), `Source result value lost: ${name}`);
      }
      assert.equal(await source.locator('a').getAttribute('href'), row.source_url);
      const sourceGeometry = await geometry(page);
      assertGeometry(sourceGeometry);
      result.sourceDetailChecks.push({episode_id: row.episode_id, source_state: row.source_state, geometry: sourceGeometry});
      if (cfg.case === 'observed' && result.sourceDetailChecks.length === 1) await screenshot(page, source, `${key}-source-details`, outDir, result);
      await source.locator(':scope > summary').click();
    }
    result.initialGeometry = await geometry(page);
    // Capture before asserting geometry so real failures remain inspectable.
    if (cfg.case === 'observed') {await page.evaluate(() => window.scrollTo(0, 0));await screenshot(page, null, `${key}-page`, outDir, result);}
    await screenshot(page, panel, `${key}-auction`, outDir, result);
    assertGeometry(result.initialGeometry);
    if (cfg.case === 'source_failure') {
      const sources = panel.locator(':scope > details.auction-context-sources');
      await sources.locator(':scope > summary').click();
      assert.ok((await sources.innerText()).includes('UI_HARNESS_SYNTHETIC_TIMEOUT'));
      assertGeometry(await geometry(page));
      await screenshot(page, panel.locator('.footnote').filter({hasText: 'UI_HARNESS_SYNTHETIC_TIMEOUT'}), `${key}-failure`, outDir, result);
      await sources.locator(':scope > summary').click();
    }
    if (cfg.case === 'observed') {
      result.expandedGroups = [];
      const groupHeadings = panel.locator('h3');
      for (let i = 0; i < await groupHeadings.count(); i++) {
        const heading = groupHeadings.nth(i);
        const group = heading.locator('..');
        const summary = group.locator(':scope > details.auction-group-expander > summary');
        if (!await summary.count()) continue;
        const initialWidths = await group.locator(':scope > .pairs > .pair').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().width));
        await summary.click();
        const expanded = await geometry(page);
        const newWidths = await group.locator(':scope > details > .pairs > .pair').evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().width));
        result.expandedGroups.push({heading: await heading.innerText(), geometry: expanded, initialCardWidths: initialWidths, expandedCardWidths: newWidths});
        await screenshot(page, summary, `${key}-expanded-${i}`, outDir, result);
        assertGeometry(expanded);
        if (initialWidths.length && newWidths.length && Math.min(...newWidths) < 0.75 * Math.min(...initialWidths)) {
          result.warnings.push(`Expanded cards in '${await heading.innerText()}' shrink below 75% of the same group's initial card width; inspect screenshot before acceptance.`);
        }
        await summary.click();
      }
    }
    assert.deepEqual(result.pageErrors, [], 'Actual page JavaScript error');
    assert.deepEqual(result.badLocalResponses, [], 'Missing or failed local asset/route');
    if (result.blockedExternal.length) result.warnings.push('Off-origin page resources were blocked; external-font/resource equivalence is not established.');
    result.status = result.warnings.length ? 'review_required' : 'passed';
  } catch (error) {
    result.status = 'failed';
    result.errors.push(error.stack || String(error));
    try {await screenshot(page, null, `${key}-failure-evidence`, outDir, result);} catch (captureError) {result.errors.push(`Failure screenshot: ${captureError.message}`);}
  } finally {
    await context.close();
  }
  return result;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const outDir = path.resolve(args['out-dir']);
  if (fs.existsSync(path.join(outDir, 'browser_receipt.json'))) throw new Error('Existing browser receipt would be overwritten; choose a new --out-dir');
  for (const root of [args['mastermind-root'], args['macro-root']]) {
    const rel = path.relative(path.resolve(root), outDir);
    if (!rel || (!rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel))) throw new Error('--out-dir must be outside source repositories');
  }
  fs.mkdirSync(path.join(outDir, 'screenshots'), {recursive: true});
  const receipt = {schema_version: 'mastermind_auction_browser_receipt_v1', started_at: new Date().toISOString(),
    status: 'running', source_files: [__filename, path.join(__dirname, 'mastermind_loopback_harness.py')].map(file => ({path: file, sha256: sha(fs.readFileSync(file))})),
    proof_scope: 'Actual Chromium page, exact existing FastAPI endpoint functions, source-bound real auction observations plus declared synthetic negative cases; no production/auth/lifespan/provider acceptance.',
    results: []};
  let harness, browser;
  try {
    const moduleFile = require.resolve('@playwright/test', {paths: [path.resolve(args['playwright-root']), path.dirname(path.resolve(args['playwright-root']))]});
    const {chromium} = require(moduleFile);
    harness = await startHarness(args, outDir, receipt);
    const origin = harness.ready.origin;
    assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
    const manifest = JSON.parse(fs.readFileSync(harness.ready.manifest, 'utf8'));
    receipt.harness_manifest = {path: 'harness_manifest.json', sha256: sha(fs.readFileSync(harness.ready.manifest))};
    const launch = {headless: true, args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-default-browser-check']};
    if (args['chromium-executable']) launch.executablePath = path.resolve(args['chromium-executable']);
    browser = await chromium.launch(launch);
    receipt.browser_version = browser.version();
    receipt.playwright_module = moduleFile;
    const viewports = [{width: 1440, height: 900}, {width: 820, height: 1180}, {width: 390, height: 844}];
    for (const viewport of viewports) for (const lang of ['en', 'zh']) for (const theme of ['light', 'dark']) {
      for (const caseName of ['observed', 'unavailable', 'source_failure', 'awaiting_unknown']) {
        const result = await runCase(browser, origin, manifest, {...viewport, lang, theme, case: caseName}, outDir);
        receipt.results.push(result);
        fs.writeFileSync(path.join(outDir, 'browser_receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
        process.stdout.write(`${receipt.results.length}/48 ${viewport.width}x${viewport.height} ${lang}/${theme} ${caseName}: ${result.status}\n`);
      }
    }
    const counts = receipt.results.reduce((map, result) => ({...map, [result.status]: (map[result.status] || 0) + 1}), {});
    receipt.counts = counts;
    receipt.status = counts.failed ? 'failed' : counts.review_required ? 'review_required' : 'passed';
  } catch (error) {
    receipt.status = 'blocked'; receipt.error = error.stack || String(error);
    process.stderr.write(String(error.stack || error) + '\n');
  } finally {
    if (browser) await browser.close();
    if (harness) await stopChild(harness.child);
    receipt.completed_at = new Date().toISOString();
    fs.writeFileSync(path.join(outDir, 'browser_receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  }
  process.stdout.write(`Receipt: ${path.join(outDir, 'browser_receipt.json')}\n`);
  process.exitCode = receipt.status === 'passed' ? 0 : receipt.status === 'review_required' ? 2 : 1;
}
main().catch(error => {process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1;});
