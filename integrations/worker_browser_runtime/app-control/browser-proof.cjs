'use strict';
// Compiled-source proof only. The test owns this isolated browser and local
// fixture server; neither carries a real account, provider, or installed grant.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { chromium } = require('playwright');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { InMemoryTransport } = require('@modelcontextprotocol/sdk/inMemory.js');
const { createAppControlConnection } = require('./connection.cjs');

const root = path.resolve(__dirname, '../../..');
const fixtureRoot = path.join(root, 'app/mastermind_os/dist-browser-proof');
const output = process.env.MM_APP_CONTROL_PROOF_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), 'mmos-app-control-proof-'));
const mime = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.woff2':'font/woff2', '.ttf':'font/ttf', '.jpg':'image/jpeg', '.png':'image/png', '.svg':'image/svg+xml' };

async function main() {
  fs.mkdirSync(output, { recursive: true });
  assert(fs.existsSync(path.join(fixtureRoot, 'agent-control-proof.html')), 'Build the isolated Vite source fixture first');
  const local = http.createServer((request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      const file = path.resolve(fixtureRoot, '.' + decodeURIComponent(url.pathname.slice(3)));
      if (!url.pathname.startsWith('/os/') || !file.startsWith(fixtureRoot + path.sep) || !fs.statSync(file).isFile()) throw new Error();
      response.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
      response.end(fs.readFileSync(file));
    } catch { response.writeHead(404); response.end('Source fixture asset not found'); }
  });
  await new Promise(resolve => local.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${local.address().port}`;
  let browser, server, client;
  const trace = [], errors = [];
  try {
    browser = await chromium.launch({ executablePath: process.env.MM_APP_CONTROL_CHROMIUM || undefined,
      headless: true, args: ['--enable-features=WebMCP'] });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.on('pageerror', error => { errors.push(error.message); });
    await page.goto(origin + '/os/agent-control-proof.html');
    await page.waitForFunction(() => Boolean(window.MastermindAppControl && document.querySelector('[data-active-route]')));
    server = await createAppControlConnection({ getContext: async () => context, origin, outputDir: output });
    client = new Client({ name: 'mastermind-app-control-source-proof', version: '1.0.0' });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport); await client.connect(clientTransport);
    const tools = await client.listTools();
    assert.equal(tools.tools.length, 18);
    assert(!tools.tools.some(tool => /evaluate|run_code/.test(tool.name)));
    const call = async (name, args = {}) => {
      const response = await client.callTool({ name, arguments: args });
      const value = response.structuredContent;
      assert(value && value.schema === 'mastermind.os.app-control.v1', JSON.stringify(response));
      trace.push({ tool: name, status: value.status ?? value.access, code: value.code, route: value.route ?? value.observation?.route });
      return value;
    };
    const inspect = () => call('mastermind_os_inspect');
    const act = async (name, action, args = {}) => {
      const observed = await inspect();
      const matches = observed.controls.filter(row => row.name === name);
      assert.equal(matches.length, 1, `Expected one ${name}; observed: ${observed.controls.map(row => row.name).join(', ')}`);
      const response = await call('mastermind_os_act', { observation: observed.observation, target: matches[0].ref, action, ...args });
      assert(['DISPATCHED','NO_CHANGE'].includes(response.status), JSON.stringify(response));
      return response;
    };
    const navigate = async route => {
      const observed = await inspect();
      assert(observed.routes.includes(route), `Unavailable route: ${route}`);
      const response = await call('mastermind_os_navigate', { observation: observed.observation, route });
      assert.equal(response.status, 'DISPATCHED', JSON.stringify(response));
      assert.equal((await call('mastermind_os_check', { route })).status, 'PASS');
    };
    let observed = await inspect();
    assert.equal(observed.access, 'AVAILABLE');
    assert.equal(observed.capabilities.content, false, 'Prove Executive navigation without Workspace Content');
    const routes = observed.routes;
    for (const route of ['Projects','Inbox','Conversations','Knowledge','Search','Fleet & Capacity']) await navigate(route);
    await navigate('Projects');
    assert.equal((await call('mastermind_os_check', { textIncludes: 'Alpha program' })).status, 'PASS');
    await act('Open project Alpha program', 'activate');
    await navigate('Search');
    await act('Search available sources', 'fill', { value: 'Alpha' });
    assert.equal((await inspect()).controls.find(row => row.name === 'Search available sources').value, 'Alpha');
    await act('Display settings', 'activate');
    await act('Theme', 'select', { value: 'light' });
    assert.equal((await inspect()).theme, 'light');
    await act('Language', 'select', { value: 'zh-CN' });
    assert.equal((await inspect()).locale, 'zh-CN');
    await act('语言', 'select', { value: 'en' });
    await act('Theme', 'select', { value: 'dark' });
    await act('Display settings', 'activate');
    assert.equal((await inspect()).controls.find(row => row.name === 'Search available sources').value, 'Alpha', 'React state survives rerender');
    await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });

    observed = await inspect();
    await inspect();
    assert.equal((await call('mastermind_os_navigate', { observation: observed.observation, route: 'Today' })).code, 'STALE_OBSERVATION');
    assert.equal((await call('mastermind_os_check', { route: 'Search' })).status, 'PASS');
    observed = await inspect();
    const request = { observation: observed.observation, route: 'Today' };
    assert.equal((await call('mastermind_os_navigate', request)).status, 'DISPATCHED');
    assert.equal((await call('mastermind_os_navigate', request)).code, 'STALE_OBSERVATION');
    await page.setViewportSize({ width: 390, height: 844 });
    await navigate('Projects');
    assert.equal((await call('mastermind_os_check', { route: 'Projects', horizontalOverflowAtMost: 2 })).status, 'PASS');
    await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });

    // An ambiguous second app page is refused without choosing another session.
    const second = await context.newPage(); await second.goto(origin + '/os/agent-control-proof.html');
    assert.equal((await inspect()).code, 'APP_PAGE_AMBIGUOUS'); await second.close();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await act('Sign out', 'activate');
    observed = await inspect();
    assert.equal(observed.access, 'AUTH_REQUIRED'); assert.deepEqual(observed.controls, []); assert.equal(observed.text, '');
    assert.deepEqual(errors, []);
    const registration = await page.evaluate(() => ({ transport: window.MastermindAppControl.transport(), documentModelContext: typeof document.modelContext?.registerTool === 'function' }));
    const receipt = { schema: 'mastermind.os.app_control_source_proof.v1', passed: true, live_acceptance: false,
      source_revision: process.env.GITHUB_SHA || null, run_id: process.env.GITHUB_RUN_ID || null, run_attempt: process.env.GITHUB_RUN_ATTEMPT || null,
      synthetic_auth: true, synthetic_owners: true, transport: 'MCP_SDK_TO_OWNED_PLAYWRIGHT_CONTEXT',
      routes, calls: trace.length, checks: ['source catalogue','primary and advanced navigation','Executive without Content','project selection','React search field','theme and locale','stale observation','duplicate refusal','mobile layout','ambiguous app page','sign-out privacy'], registration, trace };
    fs.writeFileSync(path.join(output, 'proof.json'), JSON.stringify(receipt, null, 2) + '\n');
    console.log(JSON.stringify({ passed: true, live_acceptance: false, calls: trace.length, registration, output }));
  } finally {
    await client?.close().catch(() => {}); await server?.close().catch(() => {});
    await browser?.close().catch(() => {}); await new Promise(resolve => local.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
