#!/usr/bin/env node
// Tests for the private Studio Direct tunnel adapter.
//
// Runs the fixture stdio backend (fixtures/backend.mjs) in production mode:
// testMode is false everywhere, no publicUrl is ever set, and the listener is
// always 127.0.0.1 on an ephemeral port. No real engine, no credentials, no
// tunnel-client, no network beyond loopback.
//
// The existing suite (gateway.test.mjs / auth.test.mjs) is imported nowhere
// and left untouched; these tests follow its patterns.

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import http from 'node:http';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

import {
  createTunnelAuth,
  TunnelAuthConfigError,
  TUNNEL_CLIENT_ID,
  TUNNEL_SCOPE,
} from './private-tunnel-auth.mjs';
import {
  startPrivateGateway,
  resolvePrivateTunnelConfig,
  loadPrivateTunnelConfig,
  installSignalHandlers,
  main,
  PrivateTunnelConfigError,
} from './private-tunnel-gateway.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..');
const FIXTURE_PATH = resolve(HERE, 'fixtures/backend.mjs');
const AUTH_SOURCE = await readFile(resolve(HERE, 'private-tunnel-auth.mjs'), 'utf8');
const GATEWAY_SOURCE = await readFile(resolve(HERE, 'private-tunnel-gateway.mjs'), 'utf8');

// ---- cleanup accounting -----------------------------------------------------

const cleanup = { dirs: [], clients: [], gateways: [] };

after(async () => {
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

// ---- helpers ----------------------------------------------------------------

/** Polls until `fn()` stops throwing, so marker-file waits stay bounded. */
async function waitFor(fn, timeoutMs = 4000, stepMs = 50) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      return await fn();
    } catch (err) {
      if (Date.now() > deadline) throw err;
      await new Promise((r) => setTimeout(r, stepMs));
    }
  }
}

/**
 * Boots a private tunnel gateway on an ephemeral loopback port against the
 * fixture backend. `testMode` is always false; `publicUrl` is never set.
 */
async function bootTunnel(accountLabel = 'acct-a', extra = {}, childEnvExtra = {}) {
  const stateDir = mkdtempSync(resolve(tmpdir(), 'studio-tunnel-'));
  cleanup.dirs.push(stateDir);
  const markerPath = resolve(stateDir, 'marker.txt');
  const effectLog = resolve(stateDir, 'effect.jsonl');

  const gw = await startPrivateGateway({
    port: 0,
    command: process.execPath,
    args: [FIXTURE_PATH],
    cwd: REPO_ROOT,
    childEnv: {
      FIXTURE_DELAY_MS: '60',
      FIXTURE_HANG_MS: '0',
      FIXTURE_MARKER_PATH: markerPath,
      FIXTURE_EFFECT_LOG: effectLog,
      ...childEnvExtra,
    },
    stateDir,
    maxSessions: 8,
    requestTimeoutMs: 60_000,
    testMode: false,
    accountLabel,
    ...extra,
  });
  cleanup.gateways.push(gw);
  return { gw, stateDir, markerPath, effectLog };
}

/** SDK client with NO Authorization header at all — the No Auth contract. */
function newClient() {
  const client = new Client(
    { name: 'studio-private-tunnel-test', version: '0.0.0' },
    { capabilities: {} },
  );
  cleanup.clients.push(client);
  return client;
}

async function connect(client, url) {
  const transport = new StreamableHTTPClientTransport(new URL(url));
  await client.connect(transport);
  return transport;
}

/** Raw POST that can set a forbidden Host header fetch() would strip. */
function rawPost(port, headers, body) {
  return new Promise((resolveP, rejectP) => {
    const req = http.request(
      { hostname: '127.0.0.1', port, path: '/mcp', method: 'POST', headers },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => resolveP({
          status: res.statusCode,
          body: Buffer.concat(chunks).toString(),
        }));
      },
    );
    req.on('error', rejectP);
    if (body) req.write(body);
    req.end();
  });
}

/** Minimal req/res stubs for unit-level middleware checks. */
function fakeReq(remoteAddress, headers = {}) {
  return { socket: { remoteAddress }, headers };
}
function fakeRes() {
  return {
    statusCode: 0,
    body: null,
    headers: {},
    status(code) { this.statusCode = code; return this; },
    setHeader(k, v) { this.headers[k] = v; return this; },
    end(b) { this.body = b; return this; },
  };
}

async function readCounters(path) {
  const text = await readFile(path, 'utf8').catch(() => '');
  return text.split('\n').filter(Boolean).map((l) => JSON.parse(l));
}

// ---- unit: createTunnelAuth -------------------------------------------------

test('createTunnelAuth fixes principal, clientId and scope; trims the label', () => {
  const auth = createTunnelAuth({ accountLabel: '  acct-a  ' });
  assert.equal(auth.accountLabel, 'acct-a');
  assert.equal(auth.principal, 'tunnel:acct-a');
  assert.equal(auth.clientId, TUNNEL_CLIENT_ID, 'studio-private-tunnel');
  assert.deepEqual(auth.scopes, [TUNNEL_SCOPE]);
  assert.deepEqual(auth.scopes, ['studio.control']);
  assert.equal(typeof auth.mount, 'function');
  assert.equal(typeof auth.middleware, 'function');
  // mount() installs nothing: calling it must be a no-op, not a route producer.
  assert.equal(auth.mount.length, 0);
  assert.equal(auth.mount(), undefined);
});

test('createTunnelAuth rejects missing, empty or unsafe accountLabel', () => {
  for (const bad of [
    undefined, null, '', '   ', 7, {}, ['acct-a'], 'p:alice',
    'tunnel:spoof', '../etc/passwd', 'acct a', 'acct\n-a', 'acct;a',
    'acct"b', '-lead', '.lead', '_lead', 'a'.repeat(65), 'ünïcode',
  ]) {
    assert.throws(() => createTunnelAuth({ accountLabel: bad }),
      TunnelAuthConfigError,
      `expected rejection of ${JSON.stringify(bad)}`);
  }
  // 64 characters is the documented maximum and must still be accepted.
  assert.equal(createTunnelAuth({ accountLabel: 'a'.repeat(64) }).accountLabel.length, 64);
});

test('createTunnelAuth refuses conflicting clientId/scope overrides', () => {
  assert.throws(() => createTunnelAuth({ accountLabel: 'a', clientId: 'other' }),
    TunnelAuthConfigError);
  assert.throws(() => createTunnelAuth({ accountLabel: 'a', scopes: ['studio.read'] }),
    TunnelAuthConfigError);
  assert.throws(() => createTunnelAuth({ accountLabel: 'a', scopes: [] }),
    TunnelAuthConfigError);
  // The documented values may be stated explicitly without changing anything.
  const explicit = createTunnelAuth({
    accountLabel: 'a', clientId: TUNNEL_CLIENT_ID, scopes: [TUNNEL_SCOPE],
  });
  assert.equal(explicit.principal, 'tunnel:a');
});

test('middleware fails closed on missing or non-loopback peer address', () => {
  const { middleware } = createTunnelAuth({ accountLabel: 'acct-a' });
  for (const bad of [
    undefined, null, '', '::', '0.0.0.0', '10.1.2.3', '192.168.8.194',
    'fe80::1', '127.0.0.2', 'localhost', '::ffff:7f00:1', ' 127.0.0.1',
  ]) {
    const req = fakeReq(bad);
    const res = fakeRes();
    let nextCalled = false;
    middleware(req, res, () => { nextCalled = true; });
    assert.equal(nextCalled, false, `expected refusal for ${JSON.stringify(bad)}`);
    assert.equal(res.statusCode, 403, `expected 403 for ${JSON.stringify(bad)}`);
    const parsed = JSON.parse(res.body);
    assert.equal(parsed.jsonrpc, '2.0');
    assert.equal(parsed.id, null);
    assert.ok(parsed.error, `expected a JSON-RPC error for ${JSON.stringify(bad)}`);
    assert.equal(req.auth, undefined, `no identity may be set for ${JSON.stringify(bad)}`);
  }
  // A request with no socket object at all is refused too.
  const socketless = fakeRes();
  middleware({ headers: {} }, socketless, () => { throw new Error('must not be called'); });
  assert.equal(socketless.statusCode, 403);
});

test('middleware admits exactly the loopback address set and binds the principal', () => {
  const { middleware } = createTunnelAuth({ accountLabel: 'acct-a' });
  for (const good of ['127.0.0.1', '::1', '::ffff:127.0.0.1']) {
    const req = fakeReq(good);
    const res = fakeRes();
    let nextCalled = false;
    middleware(req, res, () => { nextCalled = true; });
    assert.equal(nextCalled, true, `expected admission for ${good}`);
    assert.equal(res.statusCode, 0, `no error response expected for ${good}`);
    assert.equal(req.auth.principal, 'tunnel:acct-a');
    assert.equal(req.auth.clientId, 'studio-private-tunnel');
    assert.deepEqual(req.auth.scopes, ['studio.control']);
  }
});

test('middleware never trusts forwarded headers in either direction', () => {
  const { middleware } = createTunnelAuth({ accountLabel: 'acct-a' });
  // A loopback peer spoofing a proxy chain is still just the loopback peer:
  // identity comes from the socket, so the forged header changes nothing.
  const spoof = fakeReq('127.0.0.1', {
    'x-forwarded-for': '203.0.113.9',
    'x-real-ip': '203.0.113.9',
    forwarded: 'for=203.0.113.9',
  });
  let next = 0;
  middleware(spoof, fakeRes(), () => { next += 1; });
  assert.equal(next, 1);
  assert.equal(spoof.auth.principal, 'tunnel:acct-a');
  // And a remote peer cannot talk its way in by claiming a loopback origin.
  const liar = fakeReq('203.0.113.9', { 'x-forwarded-for': '127.0.0.1' });
  const res = fakeRes();
  middleware(liar, res, () => { throw new Error('forwarded header must not authenticate'); });
  assert.equal(res.statusCode, 403);
});

// ---- unit: resolvePrivateTunnelConfig ---------------------------------------

test('resolvePrivateTunnelConfig pins loopback bind and strips accountLabel', () => {
  const { config, auth } = resolvePrivateTunnelConfig({ port: 45018, accountLabel: 'acct-a' });
  assert.equal(config.host, '127.0.0.1');
  assert.equal(config.testMode, false);
  assert.equal(config.publicUrl, null);
  assert.equal(config.port, 45018);
  assert.equal('accountLabel' in config, false);
  assert.equal(auth.principal, 'tunnel:acct-a');
});

test('resolvePrivateTunnelConfig preserves the closed typed-Git host policy for gateway validation', () => {
  const gitPublish = {
    enabled: true,
    workspaceCli: '/Users/test/.local/bin/mmx-workspace',
    gitBinary: '/usr/bin/git',
    sourceRepository: '/Users/test/Documents/GitHub/Mastermind',
    allowedRemoteUrls: ['https://github.com/mastermindx-market-intelligence/Mastermind.git'],
  };
  const { config } = resolvePrivateTunnelConfig({
    port: 45018,
    accountLabel: 'acct-a',
    gitPublish,
  });
  assert.equal(config.gitPublish, gitPublish);
});

test('resolvePrivateTunnelConfig rejects testMode, publicUrl and non-loopback bind', () => {
  for (const [name, bad] of [
    ['testMode true', { port: 45018, accountLabel: 'a', testMode: true }],
    ['testMode string', { port: 45018, accountLabel: 'a', testMode: 'true' }],
    ['testMode 1', { port: 45018, accountLabel: 'a', testMode: 1 }],
    ['publicUrl https', { port: 45018, accountLabel: 'a', publicUrl: 'https://studio.example.invalid' }],
    ['publicUrl empty-ish url', { port: 45018, accountLabel: 'a', publicUrl: 'http://127.0.0.1:45018' }],
    ['host ::1', { port: 45018, accountLabel: 'a', host: '::1' }],
    ['host localhost', { port: 45018, accountLabel: 'a', host: 'localhost' }],
    ['host 0.0.0.0', { port: 45018, accountLabel: 'a', host: '0.0.0.0' }],
    ['host LAN ip', { port: 45018, accountLabel: 'a', host: '192.168.8.194' }],
    ['missing port', { accountLabel: 'a' }],
    ['port 45017 Funnel', { port: 45017, accountLabel: 'a' }],
    ['port string', { port: '45018', accountLabel: 'a' }],
    ['port negative', { port: -1, accountLabel: 'a' }],
    ['port out of range', { port: 65536, accountLabel: 'a' }],
    ['missing accountLabel', { port: 45018 }],
    ['unsafe accountLabel', { port: 45018, accountLabel: 'bad label' }],
    ['non-object config', undefined],
  ]) {
    assert.throws(() => resolvePrivateTunnelConfig(bad),
      TypeError, `expected rejection: ${name}`);
  }
});

// ---- unit: CLI config loading ----------------------------------------------

test('loadPrivateTunnelConfig resolves relative paths against the config file', async () => {
  const dir = mkdtempSync(resolve(tmpdir(), 'studio-tunnel-cfg-'));
  cleanup.dirs.push(dir);
  const cfgPath = resolve(dir, 'tunnel.json');
  writeFileSync(cfgPath, JSON.stringify({
    accountLabel: 'acct-a',
    port: 45018,
    args: ['../dist/index.js', '--no-onboarding'],
    cwd: '..',
    stateDir: './state',
  }), 'utf8');
  const cfg = await loadPrivateTunnelConfig(cfgPath);
  assert.equal(cfg.accountLabel, 'acct-a');
  assert.equal(cfg.args[0], resolve(dir, '../dist/index.js'));
  assert.equal(cfg.cwd, resolve(dir, '..'));
  assert.equal(cfg.stateDir, resolve(dir, 'state'));
  const missing = await loadPrivateTunnelConfig(resolve(dir, 'nope.json')).catch((e) => e);
  assert.ok(missing instanceof PrivateTunnelConfigError, 'missing file must fail closed');
});

// ---- CLI: main() boots the same listener and is closable --------------------

test('main() loads JSON config and starts a loopback private gateway', async () => {
  const dir = mkdtempSync(resolve(tmpdir(), 'studio-tunnel-cli-'));
  cleanup.dirs.push(dir);
  const markerPath = resolve(dir, 'marker.txt');
  const cfgPath = resolve(dir, 'tunnel.json');
  writeFileSync(cfgPath, JSON.stringify({
    accountLabel: 'acct-cli',
    port: 0,
    command: process.execPath,
    args: [FIXTURE_PATH],
    cwd: REPO_ROOT,
    childEnv: { FIXTURE_MARKER_PATH: markerPath, FIXTURE_DELAY_MS: '60' },
    stateDir: dir,
    testMode: false,
  }), 'utf8');

  const handlersBefore = process.listenerCount('SIGTERM') + process.listenerCount('SIGINT');
  const gw = await main([process.execPath, resolve(HERE, 'private-tunnel-gateway.mjs'), cfgPath]);
  cleanup.gateways.push(gw);
  assert.equal(gw.accountLabel, 'acct-cli');
  assert.equal(gw.principal, 'tunnel:acct-cli');
  assert.equal(gw.host, '127.0.0.1');
  assert.ok(gw.baseUrl.startsWith('http://127.0.0.1:'), gw.baseUrl);
  assert.ok(gw.url.endsWith('/mcp'), gw.url);
  // SIGTERM/SIGINT are wired for graceful shutdown.
  assert.equal(process.listenerCount('SIGTERM') + process.listenerCount('SIGINT'),
    handlersBefore + 2);

  const healthz = await fetch(new URL('/healthz', gw.url));
  assert.equal(healthz.status, 200);
  const client = newClient();
  await connect(client, gw.url);
  const ping = await client.callTool({ name: 'studio_ping', arguments: {} });
  assert.ok(ping.content?.[0]?.text.includes('hostname'), ping.content?.[0]?.text);

  // Detach them again so this test process keeps no CLI shutdown path.
  gw.signals.dispose();
  assert.equal(process.listenerCount('SIGTERM') + process.listenerCount('SIGINT'),
    handlersBefore);
});

test('main() without a config path fails closed with a usage line', async () => {
  const exitCode = process.exitCode;
  try {
    const gw = await main([process.execPath, resolve(HERE, 'private-tunnel-gateway.mjs')]);
    assert.equal(gw, null, 'no gateway without a config path');
    assert.equal(process.exitCode, 1);
  } finally {
    process.exitCode = exitCode;
  }
});

// ---- integration: the dedicated listener ------------------------------------

test('private gateway boots loopback without OAuth metadata and without testMode', async () => {
  const { gw } = await bootTunnel('acct-a');
  assert.equal(gw.host, '127.0.0.1');
  assert.ok(gw.baseUrl.startsWith('http://127.0.0.1:'), gw.baseUrl);
  assert.ok(gw.port > 0 && gw.port !== 45017, `unexpected port ${gw.port}`);
  assert.equal(gw.principal, 'tunnel:acct-a');

  const healthz = await fetch(new URL('/healthz', gw.url));
  assert.equal(healthz.status, 200);
  const health = await healthz.json();
  for (const k of Object.keys(health)) {
    assert.ok(/^(ok|version)$/.test(k), `unexpected healthz key: ${k}`);
  }

  // No Auth means no RFC 9728/8414 documents at all.
  for (const path of [
    '/.well-known/oauth-protected-resource',
    '/.well-known/oauth-protected-resource/mcp',
    '/.well-known/oauth-authorization-server',
  ]) {
    const r = await fetch(new URL(path, gw.url));
    assert.equal(r.status, 404, `${path} must be 404 on a No Auth listener`);
  }

  // Standalone event streams stay disabled, exactly as on the OAuth listener.
  const client = newClient();
  const transport = await connect(client, gw.url);
  const get = await fetch(new URL('/mcp', gw.url), {
    method: 'GET',
    headers: { 'mcp-session-id': transport.sessionId },
  });
  assert.equal(get.status, 405, `GET /mcp must stay 405, got ${get.status}`);

  // A forged Host header is refused by the gateway's own allow-list.
  const evil = await rawPost(gw.port, {
    host: 'evil.example.com',
    'content-type': 'application/json',
    accept: 'application/json, text/event-stream',
  }, JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} }));
  assert.equal(evil.status, 403, `forged Host must be 403, got ${evil.status}`);
});

test('No Auth SDK client initializes, lists tools and pings without any bearer', async () => {
  const { gw } = await bootTunnel('acct-a');
  const client = newClient();
  const transport = await connect(client, gw.url);
  assert.ok(transport.sessionId, 'session id assigned without auth');

  const listed = await client.listTools();
  assert.ok(Array.isArray(listed.tools) && listed.tools.length > 0, 'tools/list worked');
  assert.ok(listed.tools.some((t) => t.name === 'echo'), 'fixture echo tool exposed');

  const ping = await client.callTool({ name: 'studio_ping', arguments: {} });
  assert.ok(ping.content?.[0]?.text.includes('hostname'), ping.content?.[0]?.text);

  const echoed = await client.callTool({ name: 'echo', arguments: { value: 'no-auth-ok' } });
  assert.ok(echoed.content?.[0]?.text.includes('no-auth-ok'), echoed.content?.[0]?.text);
});

test('two sessions on one listener do not mix responses', async () => {
  const { gw } = await bootTunnel('acct-a');
  const a = newClient();
  const b = newClient();
  await connect(a, gw.url);
  await connect(b, gw.url);
  const [aRes, bRes] = await Promise.all([
    a.callTool({ name: 'echo', arguments: { value: 'one' } }),
    b.callTool({ name: 'echo', arguments: { value: 'two' } }),
  ]);
  const aTxt = aRes.content?.[0]?.text ?? '';
  const bTxt = bRes.content?.[0]?.text ?? '';
  assert.ok(aTxt.includes('"one"') && !aTxt.includes('"two"'), aTxt);
  assert.ok(bTxt.includes('"two"') && !bTxt.includes('"one"'), bTxt);
});

test('a session id from one account listener is unknown on another account listener', async () => {
  const a = await bootTunnel('acct-a');
  const b = await bootTunnel('acct-b');
  assert.notEqual(a.gw.port, b.gw.port);
  assert.notEqual(a.gw.principal, b.gw.principal);

  const client = newClient();
  const transport = await connect(client, a.gw.url);
  const sid = transport.sessionId;
  assert.ok(sid, 'acct-a session initialized');

  // Replaying that session id against the second listener must not proxy a
  // tool call anywhere: the session simply does not exist there.
  const replay = await fetch(new URL('/mcp', b.gw.url), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      'mcp-session-id': sid,
    },
    body: JSON.stringify({ jsonrpc: '2.0', id: 7, method: 'tools/list' }),
  });
  assert.equal(replay.status, 404, `cross-listener session must be 404, got ${replay.status}`);
  await replay.text().catch(() => {});

  // The original session is untouched by the attempt.
  const still = await client.listTools();
  assert.ok(Array.isArray(still.tools) && still.tools.length > 0);
});

test('timeout answers EFFECT_UNKNOWN once, refuses the retry, and never replays', async () => {
  const { gw, markerPath, effectLog } = await bootTunnel(
    'acct-a', { requestTimeoutMs: 300 }, { FIXTURE_NEVER: '1' });
  const client = newClient();
  const transport = await connect(client, gw.url);
  const sid = transport.sessionId;

  let firstErr = null;
  try {
    await client.callTool({ name: 'delayed_effect', arguments: { marker: 'TUNNEL-TIMEOUT-1' } });
  } catch (err) {
    firstErr = err;
  }
  assert.ok(firstErr, 'timeout must surface an error');
  assert.match(String(firstErr?.message || firstErr), /EFFECT_UNKNOWN/,
    `expected EFFECT_UNKNOWN, got: ${firstErr?.message || firstErr}`);

  // The same session must refuse further work rather than run it again.
  const retry = await fetch(new URL('/mcp', gw.url), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      'mcp-session-id': sid,
    },
    body: JSON.stringify({
      jsonrpc: '2.0', id: 2, method: 'tools/call',
      params: { name: 'echo', arguments: { value: 'must-not-run' } },
    }),
  });
  assert.equal(retry.status, 409, `tainted retry must be 409, got ${retry.status}`);
  await retry.text().catch(() => {});

  // Exactly one backend effect for the timed-out call: no replay anywhere.
  const markerText = await waitFor(() => readFile(markerPath, 'utf8'));
  assert.equal(markerText.split('\n').filter((l) => l === 'TUNNEL-TIMEOUT-1').length, 1,
    `marker file must hold exactly one effect line, got: ${JSON.stringify(markerText)}`);
  const starts = (await readCounters(effectLog))
    .filter((e) => e.marker === 'TUNNEL-TIMEOUT-1' && e.phase === 'start');
  assert.equal(starts.length, 1, 'exactly one effect start expected');
  assert.equal(gw.stats().requests.timeouts, 1);

  // A fresh session works again — the failure did not poison the listener.
  const fresh = newClient();
  await connect(fresh, gw.url);
  const ok = await fresh.callTool({ name: 'echo', arguments: { value: 'fresh-ok' } });
  assert.ok(ok.content?.[0]?.text.includes('fresh-ok'));
});

test('duplicate tools/call id in one session is refused and runs once', async () => {
  const { gw, markerPath, effectLog } = await bootTunnel('acct-a');
  const client = newClient();
  const transport = await connect(client, gw.url);
  const sid = transport.sessionId;
  const mcp = new URL('/mcp', gw.url);
  const call = (id) => fetch(mcp, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      'mcp-session-id': sid,
    },
    body: JSON.stringify({
      jsonrpc: '2.0', id, method: 'tools/call',
      params: { name: 'delayed_effect', arguments: { marker: 'TUNNEL-DUP-1', delayMs: 120 } },
    }),
  }).then((r) => r.text().then(() => r.status));

  const [first, second] = await Promise.all([call(1), call(1)]);
  // Whichever arrives first runs; the other must be refused outright.
  const statuses = [first, second].sort((x, y) => x - y);
  assert.equal(statuses[0], 200, `one call must succeed, got ${statuses}`);
  assert.equal(statuses[1], 409, `duplicate id must be 409, got ${statuses}`);

  const markerText = await waitFor(async () => {
    const text = await readFile(markerPath, 'utf8');
    assert.equal(text.split('\n').filter((l) => l === 'TUNNEL-DUP-1').length, 1,
      `exactly one marker expected, got ${JSON.stringify(text)}`);
    return text;
  });
  assert.ok(markerText.includes('TUNNEL-DUP-1'));
  const starts = (await readCounters(effectLog))
    .filter((e) => e.marker === 'TUNNEL-DUP-1' && e.phase === 'start');
  assert.equal(starts.length, 1, 'duplicate id must not start a second effect');
});

test('fifth concurrent backend op on one session is refused as busy', async () => {
  const { gw, markerPath, effectLog } = await bootTunnel(
    'acct-a', {}, { FIXTURE_HANG_MS: '1500' });
  const client = newClient();
  const transport = await connect(client, gw.url);
  const sid = transport.sessionId;
  const mcp = new URL('/mcp', gw.url);

  const call = (id, marker) => fetch(mcp, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json, text/event-stream',
      'mcp-session-id': sid,
    },
    body: JSON.stringify({
      jsonrpc: '2.0', id, method: 'tools/call',
      params: { name: 'delayed_effect', arguments: { marker } },
    }),
  }).then((r) => r.text().then((body) => ({ status: r.status, body })));

  // Four slots in flight, four queued; the ninth concurrent call on the same
  // session is over both caps. The tunnel-client profile pins its own
  // concurrency to 4 so it never reaches this, but the gateway must still hold.
  const results = await Promise.all(
    Array.from({ length: 9 }, (_, i) => call(i + 1, `TUNNEL-BUSY-${i + 1}`)));

  const busy = results.filter((r) => /Server busy|STUDIO_BUSY|-32004/i.test(r.body));
  assert.equal(busy.length, 1, `exactly one busy refusal expected, got ${busy.length}`);
  assert.equal(results.length - busy.length, 8, 'the other eight calls are accepted');

  // The eight accepted calls really ran, each exactly once.
  await waitFor(async () => {
    const lines = (await readFile(markerPath, 'utf8').catch(() => ''))
      .split('\n').filter((l) => l.startsWith('TUNNEL-BUSY-'));
    assert.equal(lines.length, 8, `eight effects expected, got ${lines.length}`);
    return lines;
  }, 8000);
  const starts = (await readCounters(effectLog))
    .filter((e) => e.marker?.startsWith('TUNNEL-BUSY-') && e.phase === 'start');
  assert.equal(starts.length, 8);
  assert.ok(gw.stats().requests.busy >= 1, 'busy counter recorded');
});

test('a real non-loopback peer is refused (or cannot connect at all)', async () => {
  const { gw } = await bootTunnel('acct-a');
  // Pick a real IPv4 address of this machine that is not loopback and that a
  // source bind can actually use. A Tailscale address cannot (ETIMEDOUT), and
  // that outcome proves the same thing, so both branches are accepted.
  const os = await import('node:os');
  const interfaces = os.networkInterfaces();
  const source = Object.values(interfaces).flat()
    .find((i) => i?.family === 'IPv4' && !i.internal && !i.address.startsWith('100.'))?.address;

  if (!source) {
    // No usable non-loopback address on this host: the middleware unit tests
    // above are the proof, and this check has nothing to add.
    return;
  }

  const outcome = await new Promise((resolveP) => {
    const req = http.request({
      host: '127.0.0.1', port: gw.port, path: '/mcp', method: 'POST',
      localAddress: source,
      headers: {
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
      },
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolveP({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
    });
    req.setTimeout(1500, () => { req.destroy(); resolveP({ error: 'timeout' }); });
    req.on('error', (err) => resolveP({ error: err.code || err.message }));
    req.end(JSON.stringify({
      jsonrpc: '2.0', id: 1, method: 'initialize',
      params: { protocolVersion: '2025-03-26', capabilities: {}, clientInfo: { name: 'lan', version: '0' } },
    }));
  });

  if (outcome.error) {
    // The OS refused or could not route the non-loopback source: no request
    // reached the listener, so nothing was admitted.
    return;
  }
  assert.equal(outcome.status, 403,
    `non-loopback peer must be refused, got ${outcome.status} ${outcome.body}`);
});

test('adapter module surface is the bounded one', async () => {
  const authMod = await import('./private-tunnel-auth.mjs');
  assert.deepEqual(Object.keys(authMod).sort(),
    ['TUNNEL_CLIENT_ID', 'TUNNEL_SCOPE', 'TunnelAuthConfigError', 'createTunnelAuth'].sort());
  const gwMod = await import('./private-tunnel-gateway.mjs');
  for (const name of [
    'PrivateTunnelConfigError', 'installSignalHandlers', 'loadPrivateTunnelConfig',
    'main', 'resolvePrivateTunnelConfig', 'startPrivateGateway',
  ]) {
    assert.equal(typeof gwMod[name], 'function', `missing export: ${name}`);
  }
});
