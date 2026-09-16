// gateway-session-churn.test.mjs
//
// Regression for native ChatGPT session accumulation: ChatGPT opens a new
// MCP session per catalog/ping/file/resource/process probe and does not
// DELETE. Opt-in reclaim may evict only idle catalog/read-only sessions
// when a new initialize arrives at capacity. Default public behavior is
// unchanged. No live runtime, credentials, or replay.
//
// Run: node --test private-studio-mcp/gateway-session-churn.test.mjs

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { setTimeout as delay } from 'node:timers/promises';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

import * as gatewayMod from './gateway.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..');
const FIXTURE_PATH = resolve(HERE, 'fixtures/backend.mjs');

function buildDeterministicAuth() {
  const TOKENS = {
    'tok-alice': { principal: 'alice', clientId: 'cli-alice', scopes: ['studio.control'] },
  };
  return {
    middleware(req, _res, next) {
      const h = req.headers.authorization || '';
      const m = /^Bearer\s+(\S+)$/.exec(h);
      const found = m && TOKENS[m[1]];
      if (!found) {
        const err = new Error('unauthorized');
        err.statusCode = 401;
        throw err;
      }
      req.auth = { ...found };
      next();
    },
    mount() {},
  };
}

const cleanup = { dirs: [], clients: [], gateways: [] };

after(async () => {
  for (const c of cleanup.clients) void c.close().catch(() => {});
  await Promise.all(cleanup.gateways.map((gw) => gw.close().catch(() => {})));
  for (const d of cleanup.dirs) {
    try { rmSync(d, { recursive: true, force: true }); } catch { /* ignore */ }
  }
});

async function bootGateway(extra = {}, childEnvExtra = {}) {
  const stateDir = mkdtempSync(resolve(tmpdir(), 'studio-churn-'));
  cleanup.dirs.push(stateDir);
  const config = {
    host: '127.0.0.1',
    port: 0,
    command: process.execPath,
    args: [FIXTURE_PATH],
    cwd: REPO_ROOT,
    childEnv: {
      ...process.env,
      FIXTURE_DELAY_MS: '60',
      FIXTURE_HANG_MS: '0',
      FIXTURE_MARKER_PATH: resolve(stateDir, 'marker.txt'),
      FIXTURE_EFFECT_LOG: resolve(stateDir, 'effect.jsonl'),
      ...childEnvExtra,
    },
    stateDir,
    maxSessions: 8,
    requestTimeoutMs: 60_000,
    testMode: true,
    ...extra,
  };
  const gw = await gatewayMod.startGateway(config, buildDeterministicAuth());
  cleanup.gateways.push(gw);
  return { gw, stateDir };
}

function newClient() {
  const client = new Client({ name: 'studio-churn-test', version: '0.0.0' }, { capabilities: {} });
  cleanup.clients.push(client);
  return {
    client,
    transportOpts: { requestInit: { headers: { authorization: 'Bearer tok-alice' } } },
  };
}

async function connect(client, url, opts) {
  const transport = new StreamableHTTPClientTransport(new URL(url), opts);
  await client.connect(transport);
  return transport;
}

function initializeBody(id) {
  return JSON.stringify({
    jsonrpc: '2.0',
    id,
    method: 'initialize',
    params: {
      protocolVersion: '2025-03-26',
      capabilities: {},
      clientInfo: { name: 'churn-test', version: '0.0.0' },
    },
  });
}

async function rawInitialize(gw, id = 1) {
  const res = await fetch(new URL('/mcp', gw.url), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      authorization: 'Bearer tok-alice',
    },
    body: initializeBody(id),
  });
  const text = await res.text();
  return { status: res.status, sid: res.headers.get('mcp-session-id'), text };
}

async function postOnSession(gw, sessionId, body) {
  const res = await fetch(new URL('/mcp', gw.url), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      authorization: 'Bearer tok-alice',
      'mcp-session-id': sessionId,
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  return { status: res.status, text };
}

/** Abandoned catalog / ping / cached-read-only session. Caller must not close it. */
async function openAbandonedCatalogSession(gw) {
  const { client, transportOpts } = newClient();
  const transport = await connect(client, gw.url, transportOpts);
  const listed = await client.listTools();
  assert.ok(listed.tools.some((t) => t.name === 'echo'));
  await client.callTool({ name: 'studio_ping', arguments: {} });
  const echo = await client.callTool({ name: 'echo', arguments: { value: 'catalog-idle' } });
  assert.match(echo.content[0].text, /catalog-idle/);
  await client.listResources();
  await delay(300);
  return { client, sessionId: transport.sessionId };
}

test('reclaimIdleCatalogSessions defaults off and is explicit-true only', () => {
  const unset = gatewayMod.resolveConfig({});
  assert.equal(unset.reclaimIdleCatalogSessions, false);
  assert.equal(gatewayMod.resolveConfig({ reclaimIdleCatalogSessions: true }).reclaimIdleCatalogSessions, true);
  assert.equal(gatewayMod.resolveConfig({ reclaimIdleCatalogSessions: 'yes' }).reclaimIdleCatalogSessions, false);
  assert.equal(gatewayMod.resolveConfig({ reclaimIdleCatalogSessions: 1 }).reclaimIdleCatalogSessions, false);
});

test('default public behavior does not evict idle catalog sessions at capacity', async () => {
  const { gw } = await bootGateway({ maxSessions: 1 });
  const abandoned = await openAbandonedCatalogSession(gw);
  const init = await rawInitialize(gw, 200);
  assert.equal(init.status, 503, `default must refuse at cap, got ${init.status}`);
  assert.equal(gw.stats().sessions.active, 1);
  assert.equal(gw.stats().sessions.reclaimed, 0);

  const stillThere = await postOnSession(gw, abandoned.sessionId, {
    jsonrpc: '2.0', id: 9, method: 'tools/list',
  });
  assert.equal(stillThere.status, 200, 'default must keep the idle catalog session');
});

test('opt-in reclaim evicts oldest abandoned catalog session and 404s the old id', async () => {
  const { gw } = await bootGateway({ maxSessions: 2, reclaimIdleCatalogSessions: true });
  const first = await openAbandonedCatalogSession(gw);
  const second = await openAbandonedCatalogSession(gw);
  assert.equal(gw.stats().sessions.active, 2);

  const init = await rawInitialize(gw, 201);
  assert.equal(init.status, 200, `reclaim initialize must succeed, got ${init.status}`);
  assert.ok(init.sid, 'new session id assigned');
  assert.notEqual(init.sid, first.sessionId);
  assert.notEqual(init.sid, second.sessionId);
  assert.equal(gw.stats().sessions.active, 2);
  assert.equal(gw.stats().sessions.reclaimed, 1);

  const evicted = await postOnSession(gw, first.sessionId, {
    jsonrpc: '2.0', id: 10, method: 'tools/list',
  });
  assert.equal(evicted.status, 404, `reclaimed id must be session-not-found, got ${evicted.status}`);
  assert.match(evicted.text, /Session not found|SESSION_NOT_FOUND|-32001/);

  const kept = await postOnSession(gw, second.sessionId, {
    jsonrpc: '2.0', id: 11, method: 'tools/list',
  });
  assert.equal(kept.status, 200, 'newer catalog session must remain');

  const again = await rawInitialize(gw, 202);
  assert.equal(again.status, 200, 'repeated initialize must keep succeeding by evicting the next safe idle');
  assert.equal(gw.stats().sessions.reclaimed, 2);
});

test('in-flight HTTP and queued limiter work are not reclaimed', async () => {
  const { gw } = await bootGateway({
    maxSessions: 1,
    reclaimIdleCatalogSessions: true,
    maxPerSessionConcurrency: 1,
    requestTimeoutMs: 30_000,
  });
  const { client, transportOpts } = newClient();
  const transport = await connect(client, gw.url, transportOpts);
  const sid = transport.sessionId;

  const inflight = client.callTool({
    name: 'delayed_effect',
    arguments: { marker: 'CHURN-INFLIGHT', delayMs: 2500 },
  });
  await delay(80);

  const initWhileActive = await rawInitialize(gw, 301);
  assert.equal(initWhileActive.status, 503, 'must not evict a session with active limiter work');
  assert.equal(gw.stats().sessions.active, 1);
  assert.equal(gw.stats().sessions.reclaimed, 0);

  const queued = client.callTool({
    name: 'delayed_effect',
    arguments: { marker: 'CHURN-QUEUED', delayMs: 100 },
  });
  await delay(40);

  const initWhileQueued = await rawInitialize(gw, 302);
  assert.equal(initWhileQueued.status, 503, 'must not evict a session with queued limiter work');

  const stillBound = await postOnSession(gw, sid, {
    jsonrpc: '2.0', id: 'probe-alive', method: 'tools/call',
    params: { name: 'studio_ping', arguments: {} },
  });
  assert.notEqual(stillBound.status, 404, 'active/queued session id must remain bound');

  await Promise.allSettled([inflight, queued]);
});

test('tainted and interactive/effectful idle sessions are not reclaimed', async () => {
  const { gw } = await bootGateway({ maxSessions: 3, reclaimIdleCatalogSessions: true });

  const effectful = newClient();
  const effectfulT = await connect(effectful.client, gw.url, effectful.transportOpts);
  await effectful.client.callTool({
    name: 'delayed_effect',
    arguments: { marker: 'CHURN-EFFECT', delayMs: 0 },
  });

  const interactive = newClient();
  const interactiveT = await connect(interactive.client, gw.url, interactive.transportOpts);
  try {
    const result = await interactive.client.callTool({
      name: 'start_process', arguments: { command: 'true' },
    });
    assert.equal(result.isError, true, 'unknown interactive tool is a tool error, not a new session');
  } catch (err) {
    assert.match(String(err?.message || err), /error|unknown|not found|MethodNotFound/i);
  }

  const tainted = newClient();
  const taintedT = await connect(tainted.client, gw.url, tainted.transportOpts);
  await assert.rejects(
    tainted.client.callTool({ name: 'drop_after_effect', arguments: { marker: 'CHURN-TAINT' } }),
    /EFFECT_UNKNOWN/,
  );

  assert.equal(gw.stats().sessions.active, 3);

  const init = await rawInitialize(gw, 401);
  assert.equal(init.status, 503, 'no safe victim among tainted/interactive/effectful');
  assert.equal(gw.stats().sessions.reclaimed, 0);
  assert.equal(gw.stats().sessions.active, 3);

  const effectStill = await postOnSession(gw, effectfulT.sessionId, {
    jsonrpc: '2.0', id: 20, method: 'tools/list',
  });
  assert.equal(effectStill.status, 200, 'effectful idle session must stay');

  const interactiveStill = await postOnSession(gw, interactiveT.sessionId, {
    jsonrpc: '2.0', id: 21, method: 'tools/list',
  });
  assert.equal(interactiveStill.status, 200, 'interactive session must stay');

  const taintedStill = await postOnSession(gw, taintedT.sessionId, {
    jsonrpc: '2.0', id: 22, method: 'tools/call',
    params: { name: 'echo', arguments: { value: 'no' } },
  });
  assert.equal(taintedStill.status, 409, 'tainted session must keep the 409, not become 404');
});

test('concurrent initialize at cap stays bounded with and without reclaim', async () => {
  const { gw } = await bootGateway({ maxSessions: 2, reclaimIdleCatalogSessions: true });
  await openAbandonedCatalogSession(gw);
  await openAbandonedCatalogSession(gw);

  const burst = await Promise.all(
    Array.from({ length: 8 }, (_, i) => rawInitialize(gw, 500 + i)),
  );
  const accepted = burst.filter((r) => r.status === 200);
  const refused = burst.filter((r) => r.status === 503);
  assert.equal(accepted.length, 2, `reclaim burst must admit exactly the two evicted catalog slots, got ${accepted.length}`);
  assert.equal(refused.length, 6, `expected 6 capacity refusals, got ${refused.length}`);
  assert.ok(gw.stats().sessions.active <= 2, `active ${gw.stats().sessions.active} exceeded cap`);
  assert.equal(new Set(accepted.map((r) => r.sid).filter(Boolean)).size, accepted.length);

  const { gw: plain } = await bootGateway({ maxSessions: 2 });
  await openAbandonedCatalogSession(plain);
  await openAbandonedCatalogSession(plain);
  const plainBurst = await Promise.all(
    Array.from({ length: 8 }, (_, i) => rawInitialize(plain, 600 + i)),
  );
  assert.equal(plainBurst.filter((r) => r.status === 200).length, 0);
  assert.equal(plain.stats().sessions.active, 2);
  assert.equal(plain.stats().sessions.reclaimed, 0);
});

test('readyz is false when it cannot admit and never exposes ids or principals', async () => {
  const { gw } = await bootGateway({ maxSessions: 1 });
  const abandoned = await openAbandonedCatalogSession(gw);

  const full = await fetch(new URL('/readyz', gw.url));
  assert.equal(full.status, 200);
  const body = await full.json();
  assert.equal(body.ready, false, 'full default gateway cannot admit');
  assert.equal(body.accepting, true);
  assert.equal(body.sessions.full, true);
  assert.equal(body.sessions.active, 1);
  assert.equal(body.sessions.capacity, 1);
  for (const key of Object.keys(body)) {
    assert.ok(!/(token|secret|password|auth|principal|path|sid)/i.test(key), `readyz leaked key: ${key}`);
  }
  const dumped = JSON.stringify(body);
  assert.ok(!dumped.includes(abandoned.sessionId), 'readyz must not include a session id');
  assert.ok(!dumped.includes('alice'), 'readyz must not include a principal');
  assert.ok(!dumped.includes(FIXTURE_PATH), 'readyz must not include a filesystem path');

  const { gw: reclaiming } = await bootGateway({ maxSessions: 1, reclaimIdleCatalogSessions: true });
  await openAbandonedCatalogSession(reclaiming);
  const canReclaim = await (await fetch(new URL('/readyz', reclaiming.url))).json();
  assert.equal(canReclaim.ready, true, 'full but reclaimable catalog capacity is still ready');
  assert.equal(canReclaim.sessions.full, true);

  const { gw: blocked } = await bootGateway({
    maxSessions: 1,
    reclaimIdleCatalogSessions: true,
    requestTimeoutMs: 30_000,
  });
  const busy = newClient();
  await connect(busy.client, blocked.url, busy.transportOpts);
  await busy.client.callTool({
    name: 'delayed_effect',
    arguments: { marker: 'CHURN-READYZ', delayMs: 0 },
  });
  const cannot = await (await fetch(new URL('/readyz', blocked.url))).json();
  assert.equal(cannot.ready, false, 'full of unreclaimable sessions must not claim ready');
});
