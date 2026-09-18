// gateway.test.mjs
//
// Integration tests for private-studio-mcp/gateway.mjs.
//
// Contract under test:
//   async startGateway(config, auth) -> { url, baseUrl, host, port, close, stats }
//
// `auth` is dependency-injected: this file supplies a deterministic bearer
// middleware so we can exercise per-principal binding without importing
// auth.mjs. gateway.mjs and auth.mjs are owned by their respective workers;
// this file imports the gateway under test and never imports production auth.
//
// All tests run without real credentials. The fixture backend replaces any
// real Desktop Commander child; no commands are executed.
//
// Run: node --test private-studio-mcp/gateway.test.mjs

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdtempSync, rmSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import http from 'node:http';
import { Readable } from 'node:stream';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

// Hard-import the gateway under test. No auth.mjs import; no skip-on-missing.
import * as gatewayMod from './gateway.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..');
const FIXTURE_PATH = resolve(HERE, 'fixtures/backend.mjs');

// ---- test auth (dependency injection; never reads auth.mjs) ---------------
//
// Bearer tokens used by the test. Each token is bound to exactly one
// {principal, clientId, scopes} triple and rejected if absent or malformed.
// The middleware throws so the gateway turns it into a 401 response — the
// production code path never imports or bypasses this shim.

function buildDeterministicAuth() {
  const TOKENS = {
    'tok-alice': { principal: 'alice', clientId: 'cli-alice', scopes: ['studio.control'] },
    'tok-bob':   { principal: 'bob',   clientId: 'cli-bob',   scopes: ['studio.control'] },
  };
  function lookup(req) {
    const h = req.headers['authorization'] || req.headers['Authorization'];
    if (typeof h !== 'string') return null;
    const m = /^Bearer\s+(\S+)$/.exec(h);
    if (!m) return null;
    return TOKENS[m[1]] || null;
  }
  return {
    TOKENS,
    middleware(req, _res, next) {
      const found = lookup(req);
      if (!found) {
        const err = new Error('unauthorized');
        err.statusCode = 401;
        throw err;
      }
      req.auth = { ...found };
      next();
    },
    mount() { /* no-op for tests; gateway uses middleware directly */ },
  };
}

// ---- cleanup accounting ----------------------------------------------------
//
// Every gateway, every SDK client, and every temp dir is tracked here so a
// failing test cannot leak processes or files into the next run.

const cleanup = { dirs: [], clients: [], gateways: [] };

after(async () => {
  // Close SDK clients first so any in-flight requests unblock before we tear
  // the gateway down underneath them.
  for (const c of cleanup.clients) {
    try { await c.close(); } catch { /* ignore */ }
  }
  for (const gw of cleanup.gateways) {
    try { await gw.close(); } catch { /* ignore */ }
  }
  for (const d of cleanup.dirs) {
    try { rmSync(d, { recursive: true, force: true }); } catch { /* ignore */ }
  }
});

// ---- helpers --------------------------------------------------------------

async function bootGateway(extra = {}, childEnvExtra = {}) {
  const stateDir = mkdtempSync(resolve(tmpdir(), 'studio-gw-'));
  cleanup.dirs.push(stateDir);

  const markerPath = resolve(stateDir, 'marker.txt');
  const effectLog = resolve(stateDir, 'effect.jsonl');

  const config = {
    host: '127.0.0.1',
    port: 0,                       // ephemeral
    command: process.execPath,
    args: [FIXTURE_PATH],
    cwd: REPO_ROOT,
    childEnv: {
      ...process.env,
      FIXTURE_DELAY_MS: '60',
      FIXTURE_HANG_MS: '0',
      FIXTURE_MARKER_PATH: markerPath,
      FIXTURE_EFFECT_LOG: effectLog,
      ...childEnvExtra,
    },
    stateDir,
    maxSessions: 8,
    requestTimeoutMs: 60_000,
    testMode: true,
    ...extra,
  };

  const auth = buildDeterministicAuth();
  const gw = await gatewayMod.startGateway(config, auth);
  cleanup.gateways.push(gw);
  return { gw, auth, stateDir, markerPath, effectLog };
}

function newClient(token) {
  const client = new Client(
    { name: 'studio-test', version: '0.0.0' },
    { capabilities: {} },
  );
  cleanup.clients.push(client);
  const transportOpts = {
    requestInit: { headers: { authorization: `Bearer ${token}` } },
  };
  return { client, transportOpts, token };
}

async function connect(client, url, opts) {
  // `url` already ends in /mcp per the gateway contract.
  const transport = new StreamableHTTPClientTransport(new URL(url), opts);
  await client.connect(transport);
  return transport;
}

/**
 * Raw HTTP POST that lets us set reserved headers (Host, etc.) that the
 * fetch() implementation strips. Required to exercise the gateway's Host /
 * Origin allow-list validation end-to-end.
 */
function rawPost(port, headers, body) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: '127.0.0.1', port, path: '/mcp', method: 'POST', headers },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => resolve({
          status: res.statusCode,
          body: Buffer.concat(chunks).toString(),
        }));
      },
    );
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

// ---- tests ----------------------------------------------------------------

test('startGateway contract: url ends in /mcp, baseUrl, close, stats', async () => {
  const { gw } = await bootGateway();
  try {
    assert.equal(typeof gw.url, 'string');
    assert.ok(gw.url.endsWith('/mcp'), `url must end with /mcp, got ${gw.url}`);
    assert.equal(typeof gw.baseUrl, 'string');
    assert.ok(gw.baseUrl.startsWith('http://127.0.0.1:'), `baseUrl must be loopback, got ${gw.baseUrl}`);
    assert.equal(typeof gw.host, 'string');
    assert.equal(gw.host, '127.0.0.1');
    assert.equal(typeof gw.port, 'number');
    assert.ok(gw.port > 0, `port must be the ephemeral bound port, got ${gw.port}`);
    assert.equal(typeof gw.close, 'function');
    assert.equal(typeof gw.stats, 'function');
    const snap = gw.stats();
    assert.equal(typeof snap.uptimeMs, 'number');
    assert.equal(snap.listening.host, '127.0.0.1');
    assert.equal(snap.listening.port, gw.port);
  } finally { /* cleanup */ }
});

test('gateway boots and /healthz responds unauthenticated', async () => {
  const { gw } = await bootGateway();
  try {
    const healthz = await fetch(new URL('/healthz', gw.url), { method: 'GET' });
    assert.equal(healthz.status, 200, 'healthz 200');
    const body = await healthz.json();
    assert.equal(typeof body, 'object');
    assert.ok('ok' in body);
    assert.ok(!('token' in body) && !('tokens' in body));
    for (const k of Object.keys(body)) {
      assert.ok(/^(ok|version|uptimeMs)$/.test(k), `unexpected healthz key: ${k}`);
    }
  } finally { /* cleanup */ }
});

test('rejects malformed JSON-RPC and unknown session IDs', async () => {
  const { gw } = await bootGateway();
  try {
    const mcp = new URL('/mcp', gw.url);

    // Malformed body: not valid JSON.
    const bad = await fetch(mcp, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: 'Bearer tok-alice' },
      body: '{not-json',
    });
    assert.equal(bad.status, 400, 'malformed JSON must be 400');

    // Unknown session id attached to a well-formed request must yield 404.
    const unknown = await fetch(mcp, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: 'Bearer tok-alice',
        'mcp-session-id': 'does-not-exist-12345',
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    });
    assert.equal(unknown.status, 404,
      `unknown session must be 404, got ${unknown.status}`);
  } finally { /* cleanup */ }
});

test('rejects missing or invalid bearer with 401', async () => {
  const { gw } = await bootGateway();
  try {
    const mcp = new URL('/mcp', gw.url);

    const noAuth = await fetch(mcp, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    });
    assert.equal(noAuth.status, 401,
      `missing authorization must be 401, got ${noAuth.status}`);

    const badToken = await fetch(mcp, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: 'Bearer tok-nope',
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    });
    assert.equal(badToken.status, 401,
      `unknown token must be 401, got ${badToken.status}`);

    const malformed = await fetch(mcp, {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: 'NotBearer foo' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    });
    assert.equal(malformed.status, 401,
      `malformed authorization header must be 401, got ${malformed.status}`);
  } finally { /* cleanup */ }
});

test('rejects bad Host and bad Origin headers', async () => {
  const { gw } = await bootGateway();
  try {
    const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' });

    // Bad Host header. fetch() strips Host overrides, so use raw http.request.
    const badHost = await rawPost(
      gw.port,
      {
        'content-type': 'application/json',
        'content-length': Buffer.byteLength(body),
        authorization: 'Bearer tok-alice',
        host: 'evil.example.com',
      },
      body,
    );
    assert.equal(badHost.status, 403,
      `bad host must be 403, got ${badHost.status}`);

    // Bad Origin header (allowed origins are loopback for this bind).
    const badOrigin = await rawPost(
      gw.port,
      {
        'content-type': 'application/json',
        'content-length': Buffer.byteLength(body),
        authorization: 'Bearer tok-alice',
        origin: 'https://evil.example.com',
      },
      body,
    );
    assert.equal(badOrigin.status, 403,
      `bad origin must be 403, got ${badOrigin.status}`);
  } finally { /* cleanup */ }
});

test('rejects additional initialize when capacity reached', async () => {
  const { gw } = await bootGateway({ maxSessions: 1 });
  try {
    const a = newClient('tok-alice');
    const aT = await connect(a.client, gw.url, a.transportOpts);
    assert.ok(aT.sessionId, 'alice session id assigned');

    // Second initialize must be refused with 503 capacity.
    const init = await fetch(new URL('/mcp', gw.url), {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'accept': 'application/json, text/event-stream',
        authorization: 'Bearer tok-alice',
      },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 100,
        method: 'initialize',
        params: {
          protocolVersion: '2025-03-26',
          capabilities: {},
          clientInfo: { name: 'cap-test', version: '0.0.0' },
        },
      }),
    });
    assert.equal(init.status, 503,
      `capacity exceeded must be 503, got ${init.status}`);
  } finally { /* cleanup */ }
});

test('two independent client sessions do not mix responses', async () => {
  const { gw } = await bootGateway();
  try {
    const a = newClient('tok-alice');
    const b = newClient('tok-bob');
    await connect(a.client, gw.url, a.transportOpts);
    await connect(b.client, gw.url, b.transportOpts);

    // Two parallel requests across sessions. Each client auto-assigns its
    // own JSON-RPC ids; we do not assert anything about which id was used,
    // only that each client receives its own response.
    const [aRes, bRes] = await Promise.all([
      a.client.callTool({ name: 'echo', arguments: { value: 'alice' } }, undefined, { _meta: {} }),
      b.client.callTool({ name: 'echo', arguments: { value: 'bob' } }, undefined, { _meta: {} }),
    ]);

    const aTxt = aRes.content?.[0]?.text ?? '';
    const bTxt = bRes.content?.[0]?.text ?? '';
    assert.ok(aTxt.includes('alice'), `alice got wrong response: ${aTxt}`);
    assert.ok(bTxt.includes('bob'), `bob got wrong response: ${bTxt}`);
    assert.ok(!aTxt.includes('bob'), 'alice response leaked bob');
    assert.ok(!bTxt.includes('alice'), 'bob response leaked alice');
  } finally { /* cleanup */ }
});

test("token for one principal cannot drive another principal's session", async () => {
  const { gw } = await bootGateway();
  try {
    const a = newClient('tok-alice');
    const aTransport = await connect(a.client, gw.url, a.transportOpts);
    const aliceSessionId = aTransport.sessionId;
    assert.ok(aliceSessionId, 'alice session id assigned');

    // Bob attempts to drive Alice's session using his own bearer.
    const mcp = new URL('/mcp', gw.url);
    const cross = await fetch(mcp, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: 'Bearer tok-bob',
        'mcp-session-id': aliceSessionId,
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 99, method: 'tools/list' }),
    });
    assert.equal(cross.status, 403,
      `cross-principal reuse must be 403, got ${cross.status}`);

    // Alice can still use her own session.
    const list = await a.client.listTools();
    assert.ok(Array.isArray(list.tools));
  } finally { /* cleanup */ }
});

test('SDK tool requests progress through a single HTTP connection after initialization', async () => {
  const { gw } = await bootGateway();
  const a = newClient('tok-alice');
  // Model a serial proxy connection. An idle GET/SSE stream would hold the
  // only socket indefinitely, preventing the SDK's next POST from arriving.
  const agent = new http.Agent({ keepAlive: true, maxSockets: 1 });
  const serialFetch = (input, init = {}) => new Promise((resolve, reject) => {
    const req = http.request(new URL(input), {
      method: init.method || 'GET', agent,
      headers: Object.fromEntries(new Headers(init.headers)),
      signal: init.signal,
    }, (res) => resolve(new Response(Readable.toWeb(res), {
      status: res.statusCode,
      headers: Object.fromEntries(Object.entries(res.headers).filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, Array.isArray(v) ? v.join(', ') : v])),
    })));
    req.on('error', reject);
    req.end(init.body);
  });
  try {
    const transport = await connect(a.client, gw.url, { ...a.transportOpts, fetch: serialFetch });
    const sessionId = transport.sessionId;
    const list = await a.client.listTools({}, { timeout: 2000 });
    assert.ok(list.tools.length > 0);
    const ping = await a.client.callTool({ name: 'studio_ping', arguments: {} }, undefined, { timeout: 2000 });
    assert.equal(ping.isError, undefined);
    assert.equal(transport.sessionId, sessionId);
    assert.equal(gw.stats().backend.spawns, 1);
  } finally {
    await a.client.close();
    agent.destroy();
  }
});

test('tools/list publishes gateway-owned neutral backend metadata and privacy-minimal ping', async () => {
  const { gw } = await bootGateway();
  const a = newClient('tok-alice');
  await connect(a.client, gw.url, a.transportOpts);

  const listed = await a.client.listTools();
  const byName = new Map(listed.tools.map((tool) => [tool.name, tool]));
  assert.equal(
    byName.get('read_file')?.description,
    'Reads one allowed local file or supported URL, with bounded paging for supported formats.',
  );
  assert.equal(
    byName.get('echo')?.description,
    'Backend MCP capability. The input schema defines accepted parameters and annotations describe its effect posture.',
  );
  assert.notEqual(
    byName.get('echo')?.description,
    'Returns its argument object verbatim. Read-only, no side effects.',
    'backend-authored prose must not cross the gateway metadata boundary',
  );

  const directivePattern =
    /required workflow|always\b|never\b|only correct tool|must use|do not use|prefer this|critical rule/i;
  for (const tool of listed.tools) {
    assert.doesNotMatch(
      tool.description ?? '',
      directivePattern,
      `tool description contains classifier-directed language: ${tool.name}`,
    );
  }

  const ping = await a.client.callTool(
    { name: 'studio_ping', arguments: {} },
    undefined,
    { timeout: 2000 },
  );
  const payload = ping.structuredContent ??
    JSON.parse(ping.content?.find((item) => item.type === 'text')?.text ?? '{}');
  assert.equal(Object.hasOwn(payload, 'hostname'), false, 'ping must not expose a raw host name');
  assert.equal(Object.hasOwn(payload, 'pid'), false, 'ping must not expose the gateway process id');
  assert.match(payload.generation, /^[a-z0-9-]+$/i);
  assert.equal(payload.gatewayVersion, '0.1.5');
});

test('shared backend reserves one slot for catalog traffic while typed Git remains advertised', { timeout: 15_000 }, async () => {
  const { gw, effectLog } = await bootGateway({
    backendMode: 'shared-account',
    maxSessions: 8,
    maxPerSessionConcurrency: 4,
    requestTimeoutMs: 10_000,
    gitPublish: {
      enabled: true,
      workspaceCli: '/usr/bin/true',
      gitBinary: '/usr/bin/git',
      sourceRepository: REPO_ROOT,
      allowedRemoteUrls: ['https://github.com/mastermindx-market-intelligence/Mastermind.git'],
    },
  }, { FIXTURE_READ_DELAY_MS: '1000' });

  const actors = [];
  for (let i = 0; i < 5; i += 1) {
    const actor = newClient('tok-alice');
    await connect(actor.client, gw.url, actor.transportOpts);
    actors.push(actor);
  }

  const catalog = await actors[4].client.listTools();
  const names = new Set(catalog.tools.map((tool) => tool.name));
  for (const name of [
    'studio_git_publish_status',
    'studio_git_commit_current_changes',
    'studio_git_push_current_branch',
  ]) {
    assert.ok(names.has(name), `typed Git tool missing from combined catalog: ${name}`);
  }

  const resources = await actors[4].client.listResources();
  assert.ok(resources.resources.some((resource) => resource.uri === 'ui://studio-test/priority'));

  const ordinary = actors.slice(0, 4).map((actor, index) => actor.client.callTool({
    name: 'read_file',
    arguments: { path: `/fixture-priority-${index}` },
  }, undefined, { timeout: 5000 }));

  let starts = 0;
  const startDeadline = Date.now() + 1500;
  while (Date.now() < startDeadline) {
    const text = await readFile(effectLog, 'utf8').catch(() => '');
    starts = text.split('\n').filter(Boolean).map((line) => JSON.parse(line))
      .filter((event) => event.tool === 'read_file' && event.phase === 'start').length;
    if (starts >= 3) break;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal(starts, 3, 'ordinary work must consume only three of four shared backend slots');

  const resourceStarted = performance.now();
  const resource = await actors[4].client.readResource({ uri: 'ui://studio-test/priority' });
  const resourceLatencyMs = performance.now() - resourceStarted;
  assert.equal(resource.contents[0].text, 'priority-resource-ok');
  assert.ok(resourceLatencyMs < 500,
    `priority resource should bypass saturated ordinary work; latency=${Math.round(resourceLatencyMs)}ms`);

  await Promise.all(ordinary);

  const events = (await readFile(effectLog, 'utf8')).split('\n').filter(Boolean).map((line) => JSON.parse(line));
  let activeReads = 0;
  let activeTotal = 0;
  let peakReads = 0;
  let peakTotal = 0;
  let readsAtResourceStart = null;
  for (const event of events) {
    if (event.tool !== 'read_file' && event.tool !== 'priority_resource') continue;
    if (event.phase === 'start') {
      if (event.tool === 'read_file') activeReads += 1;
      activeTotal += 1;
      if (event.tool === 'priority_resource') readsAtResourceStart = activeReads;
      peakReads = Math.max(peakReads, activeReads);
      peakTotal = Math.max(peakTotal, activeTotal);
    } else if (event.phase === 'resolved') {
      if (event.tool === 'read_file') activeReads -= 1;
      activeTotal -= 1;
    }
  }
  assert.equal(readsAtResourceStart, 3,
    'catalog resource must start while three ordinary calls occupy the normal slots');
  assert.equal(peakReads, 3, 'ordinary shared-backend concurrency must remain capped at three');
  assert.equal(peakTotal, 4, 'catalog traffic may consume the reserved fourth slot');
  assert.equal(activeReads, 0);
  assert.equal(activeTotal, 0);
});

test('backend timeout marks session EFFECT_UNKNOWN and rejects retry; new session good', async () => {
  const { gw, markerPath, effectLog } = await bootGateway(
    { requestTimeoutMs: 1500 },
    { FIXTURE_NEVER: '1' },
  );
  try {
    const a = newClient('tok-alice');
    const aTransport = await connect(a.client, gw.url, a.transportOpts);
    const sessionId = aTransport.sessionId;
    assert.ok(sessionId, 'alice session id assigned');

    // Send a call that the backend will hang past the timeout. The fixture
    // awaits the marker write before hanging, so the marker file is on disk
    // before the gateway times out.
    let firstErr = null;
    try {
      await a.client.callTool({
        name: 'delayed_effect',
        arguments: { marker: 'TIMEOUT-MARKER-1', delayMs: 5000 },
      });
    } catch (err) {
      firstErr = err;
    }
    assert.ok(firstErr, 'timeout call must surface an error');
    const msg = String(firstErr && (firstErr.message || firstErr));
    assert.match(msg, /EFFECT_UNKNOWN/,
      `expected EFFECT_UNKNOWN marker in error, got: ${msg}`);

    // Same session must refuse further calls (tainted → 409).
    const mcp = new URL('/mcp', gw.url);
    const retry = await fetch(mcp, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: 'Bearer tok-alice',
        'mcp-session-id': sessionId,
      },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 2, method: 'tools/call',
        params: { name: 'echo', arguments: { value: 'should-not-run' } },
      }),
    });
    assert.equal(retry.status, 409,
      `retry on tainted session must be 409, got ${retry.status}`);

    // Tight wait for the fixture's marker write + effect log flush.
    await new Promise((r) => setTimeout(r, 200));

    // Exactly one marker line for TIMEOUT-MARKER-1 — no replay, no double-call.
    const markerText = await readFile(markerPath, 'utf8').catch(() => '');
    const markerCount = markerText.split('\n').filter((l) => l === 'TIMEOUT-MARKER-1').length;
    assert.equal(markerCount, 1,
      `exactly one marker expected, saw ${markerCount}`);

    // Exactly one start entry in the effect log for that marker.
    const effectText = await readFile(effectLog, 'utf8').catch(() => '');
    const starts = effectText
      .split('\n').filter(Boolean)
      .map((l) => JSON.parse(l))
      .filter((e) => e && e.marker === 'TIMEOUT-MARKER-1' && e.phase === 'start');
    assert.equal(starts.length, 1,
      `exactly one effect start expected, saw ${starts.length}`);

    // A brand-new session for the same principal must NOT replay the prior
    // failure: a fresh call must succeed and have its own state.
    const b = newClient('tok-alice');
    await connect(b.client, gw.url, b.transportOpts);
    const fresh = await b.client.callTool({ name: 'echo', arguments: { value: 'fresh-ok' } });
    assert.ok(fresh.content?.[0]?.text.includes('fresh-ok'),
      'new session must not replay tainted state');
  } finally { /* cleanup */ }
});

test('timeout-safe read returns READ_TIMEOUT without taint or replay', async () => {
  const { gw } = await bootGateway(
    { requestTimeoutMs: 1500 },
    { FIXTURE_READ_DELAY_MS: '3500' },
  );
  const a = newClient('tok-alice');
  await connect(a.client, gw.url, a.transportOpts);

  const result = await a.client.callTool({
    name: 'read_file', arguments: { path: '/fixture-only' },
  }, undefined, { timeout: 5000 });
  assert.equal(result.isError, true);
  assert.match(result.content?.[0]?.text || '', /READ_TIMEOUT/);
  assert.equal(gw.stats().sessions.tainted, 0, 'timeout-safe read must not taint the frontend session');
  assert.equal(gw.stats().requests.timeouts, 1);

  await new Promise((resolve) => setTimeout(resolve, 400));
  const fresh = await a.client.callTool({ name: 'echo', arguments: { value: 'same-session-ok' } });
  assert.match(fresh.content?.[0]?.text || '', /same-session-ok/);
  assert.equal(gw.stats().sessions.tainted, 0);
});

test('backend request metadata preserves the exact outer JSON-RPC call id', async () => {
  const { gw } = await bootGateway();
  const a = newClient('tok-alice');
  const transport = await connect(a.client, gw.url, a.transportOpts);
  assert.ok(transport.sessionId);

  const body = JSON.stringify({
    jsonrpc: '2.0',
    id: 'outer-call-correlation-001',
    method: 'tools/call',
    params: {
      name: 'request_meta',
      arguments: {},
      _meta: { caller_tag: 'preserve-me' },
    },
  });
  const response = await rawPost(gw.port, {
    'content-type': 'application/json',
    accept: 'application/json, text/event-stream',
    authorization: 'Bearer tok-alice',
    'mcp-session-id': transport.sessionId,
  }, body);
  assert.equal(response.status, 200, response.body);
  assert.match(response.body, /preserve-me/);
  assert.match(response.body, /mastermind_remote_call_id/);
  assert.match(response.body, /outer-call-correlation-001/);
});

test('readiness reflects accepting MCP traffic', async () => {
  const { gw } = await bootGateway();
  try {
    const r = await fetch(new URL('/readyz', gw.url));
    assert.equal(r.status, 200, 'readyz 200 once gateway accepts');
    const body = await r.json();
    assert.ok(body.ready === true || body.ok === true,
      `expected ready, got ${JSON.stringify(body)}`);
    // Never leak secrets on readiness.
    for (const k of Object.keys(body)) {
      assert.ok(!/(token|secret|password|auth)/i.test(k),
        `readyz leaked key: ${k}`);
    }
  } finally { /* cleanup */ }
});

test("DELETE closes only the caller's session and frees capacity for reuse", async () => {
  const { gw } = await bootGateway({ maxSessions: 2 });
  try {
    const a = newClient('tok-alice');
    const b = newClient('tok-bob');
    const aT = await connect(a.client, gw.url, a.transportOpts);
    const bT = await connect(b.client, gw.url, b.transportOpts);
    const aSid = aT.sessionId;
    const bSid = bT.sessionId;
    assert.ok(aSid && bSid, 'both sessions initialized');

    // Alice issues DELETE on her session — must succeed.
    const del = await fetch(new URL('/mcp', gw.url), {
      method: 'DELETE',
      headers: { authorization: 'Bearer tok-alice', 'mcp-session-id': aSid },
    });
    assert.ok(del.status === 200 || del.status === 204,
      `alice close status ${del.status}`);

    // Bob's session must remain usable.
    const bobList = await b.client.listTools();
    assert.ok(Array.isArray(bobList.tools));

    // Bob cannot close Alice's (now-closed) session.
    const cross = await fetch(new URL('/mcp', gw.url), {
      method: 'DELETE',
      headers: { authorization: 'Bearer tok-bob', 'mcp-session-id': aSid },
    });
    assert.ok(cross.status >= 400,
      `bob closing alice session must fail, got ${cross.status}`);

    // Closed session must 404 on further requests.
    const reuse = await fetch(new URL('/mcp', gw.url), {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: 'Bearer tok-alice',
        'mcp-session-id': aSid,
      },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
    });
    assert.equal(reuse.status, 404,
      `closed session must be 404, got ${reuse.status}`);

    // Capacity was freed: alice can open a new session.
    const a2 = newClient('tok-alice');
    const a2T = await connect(a2.client, gw.url, a2.transportOpts);
    assert.ok(a2T.sessionId && a2T.sessionId !== aSid,
      'new session opened for alice after DELETE');
    const fresh = await a2.client.callTool({ name: 'echo', arguments: { value: 'after-delete' } });
    assert.ok(fresh.content?.[0]?.text.includes('after-delete'),
      'new session must work normally');
  } finally { /* cleanup */ }
});

test('duplicate JSON-RPC id in same session does not re-execute', async () => {
  const { gw, markerPath, effectLog } = await bootGateway(
    { requestTimeoutMs: 3000 },
    {},
  );
  try {
    const a = newClient('tok-alice');
    const aT = await connect(a.client, gw.url, a.transportOpts);
    const sessionId = aT.sessionId;
    assert.ok(sessionId, 'alice session id assigned');

    const mcp = new URL('/mcp', gw.url);

    // First request with id=1.
    const r1 = await fetch(mcp, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'accept': 'application/json, text/event-stream',
        authorization: 'Bearer tok-alice',
        'mcp-session-id': sessionId,
      },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 1, method: 'tools/call',
        params: { name: 'delayed_effect', arguments: { marker: 'DUP-MARKER-1', delayMs: 100 } },
      }),
    });
    // Drain the SSE body so the response stream closes cleanly.
    await r1.text().catch(() => {});

    // Second request with the SAME id=1 must not cause a second execution.
    const r2 = await fetch(mcp, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'accept': 'application/json, text/event-stream',
        authorization: 'Bearer tok-alice',
        'mcp-session-id': sessionId,
      },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 1, method: 'tools/call',
        params: { name: 'delayed_effect', arguments: { marker: 'DUP-MARKER-1', delayMs: 100 } },
      }),
    });
    await r2.text().catch(() => {});

    assert.equal(r2.status, 409,
      `duplicate JSON-RPC id must be 409, got ${r2.status}`);

    // Tight wait for the fixture's marker write to land on disk.
    await new Promise((r) => setTimeout(r, 200));

    // Exactly one marker line: no replay.
    const markerText = await readFile(markerPath, 'utf8').catch(() => '');
    const markerCount = markerText.split('\n').filter((l) => l === 'DUP-MARKER-1').length;
    assert.equal(markerCount, 1,
      `exactly one marker expected after duplicate, saw ${markerCount}`);

    // Exactly one invocation recorded in the effect log.
    const effectText = await readFile(effectLog, 'utf8').catch(() => '');
    const starts = effectText
      .split('\n').filter(Boolean)
      .map((l) => JSON.parse(l))
      .filter((e) => e && e.marker === 'DUP-MARKER-1' && e.phase === 'start');
    assert.equal(starts.length, 1,
      `exactly one invocation expected, saw ${starts.length}`);
  } finally { /* cleanup */ }
});
test('backend exit after an effect taints the session without replacing its child', async () => {
  const {gw, markerPath}=await bootGateway();
  const a=newClient('tok-alice');
  await connect(a.client,gw.url,a.transportOpts);
  await assert.rejects(a.client.callTool({name:'drop_after_effect',arguments:{marker:'DROP_ONCE'}}), /EFFECT_UNKNOWN/);
  assert.equal(await readFile(markerPath,'utf8'),'DROP_ONCE\n');
  assert.equal(gw.stats().backend.spawns,1);
  await assert.rejects(a.client.callTool({name:'echo',arguments:{value:'forbidden'}}), /409|tainted/);
  assert.equal(gw.stats().backend.spawns,1);
  const b=newClient('tok-alice');
  await connect(b.client,gw.url,b.transportOpts);
  const result=await b.client.callTool({name:'echo',arguments:{value:'fresh'}});
  assert.match(result.content[0].text,/fresh/);
  assert.equal(gw.stats().backend.spawns,2);
  assert.equal(await readFile(markerPath,'utf8'),'DROP_ONCE\n');
});
