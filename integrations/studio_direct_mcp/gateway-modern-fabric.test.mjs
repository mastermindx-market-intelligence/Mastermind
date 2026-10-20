import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { Client as LegacyClient } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport as LegacyTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { PROTOCOL_VERSION_META_KEY, CLIENT_INFO_META_KEY, CLIENT_CAPABILITIES_META_KEY } from '@modelcontextprotocol/server';
import { startGateway, resolveConfig } from './gateway.mjs';
import { startPrivateGateway } from './private-tunnel-gateway.mjs';

const profile = { host: '127.0.0.1', port: 0, accountLabel: 'fabric-test',
  fabricOnly: true, backendMode: 'shared-account', modernFabricProtocol: true,
  command: process.execPath, args: [fileURLToPath(new URL('./fixtures/modern-fabric-backend.mjs', import.meta.url))],
  requestTimeoutMs: 3000 };
const metadata = { [PROTOCOL_VERSION_META_KEY]: '2026-07-28',
  [CLIENT_INFO_META_KEY]: { name: 'disposable-test', version: '0.0.0' },
  [CLIENT_CAPABILITIES_META_KEY]: {} };
const body = (method, params = {}, id = 1) => ({ jsonrpc: '2.0', id, method,
  params: { ...params, _meta: metadata } });
async function raw(gw, message, headers = {}) {
  return fetch(gw.url, { method: 'POST', headers: { 'content-type': 'application/json',
    accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2026-07-28',
    'mcp-method': message.method, ...(message.params?.name ? { 'mcp-name': message.params.name } : {}),
    ...headers }, body: JSON.stringify(message) });
}
function value(result) { return JSON.parse(result.content.find(c => c.type === 'text').text); }
async function connect(gw, headers = {}) {
  const client = new Client({ name: 'modern-integration-test', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: '2026-07-28' }, probe: { timeoutMs: 3000, maxRetries: 0 } } });
  await client.connect(new StreamableHTTPClientTransport(new URL(gw.url), { requestInit: { headers } }));
  return client;
}

test('modern selection is strict, private, restricted and off by default', async () => {
  assert.equal(resolveConfig({}).modernFabricProtocol, undefined);
  for (const delta of [{ modernFabricProtocol: 1 }, { fabricOnly: false },
    { backendMode: 'per-session' }, { host: 'localhost' }, { publicUrl: 'https://example.test' }]) {
    assert.throws(() => resolveConfig({ ...profile, ...delta }), /modern Fabric|modernFabricProtocol/);
  }
  await assert.rejects(startGateway(profile, {}), /installed private tunnel principal/);
});

test('the actual private entry keeps legacy serving when modern mode is absent', async () => {
  const config = { ...profile }; delete config.modernFabricProtocol; delete config.backendMode;
  const gw = await startPrivateGateway(config);
  const client = new LegacyClient({ name: 'legacy-private-entry', version: '0.0.0' });
  try {
    assert.equal(gw.accountLabel, 'fabric-test');
    assert.equal(gw.principal, 'tunnel:fabric-test');
    const ready = await (await fetch(new URL('/readyz', gw.url))).json();
    assert.equal(ready.modernFabricProtocol, undefined);
    await client.connect(new LegacyTransport(new URL(gw.url)));
    assert.equal((await client.listTools()).tools.length, 9);
    assert.equal(value(await client.callTool({ name: 'fabric_status', arguments: {} })).name, 'fabric_status');
  } finally { await client.close(); await gw.close(); }
});

test('pinned modern client lists/calls through real HTTP and retains the existing backend generation', async () => {
  const gw = await startPrivateGateway(profile);
  let first, second, legacy;
  try {
    first = await connect(gw);
    assert.equal(first.getProtocolEra(), 'modern');
    const tools = await first.listTools();
    assert.equal(tools.tools.length, 9);
    const requested = value(await first.callTool({ name: 'fabric_request', arguments: { run_id: 'fixture-only' } }));
    assert.equal(requested.effects, 1);
    assert.ok(requested.backendRequestId && requested.backendRequestId !== 'undefined');
    await first.close();
    assert.equal(gw.stats().sessions.active, 0);
    second = await connect(gw);
    const result = value(await second.callTool({ name: 'fabric_status', arguments: { run_id: 'fixture-only' } }));
    assert.equal(result.pid, requested.pid);
    assert.equal(result.effects, 1);
    assert.equal(gw.stats().backend.spawns, 1);
    const ping = value(await second.callTool({ name: 'studio_ping', arguments: {} }));
    assert.equal(ping.protocolVersion, '2026-07-28');
    assert.equal(ping.sessionId, null);
    assert.equal(ping.requestScoped, true);
    assert.equal(ping.backendGeneration, gw.stats().backend.owners[0].generation);
    legacy = new LegacyClient({ name: 'legacy-still-supported', version: '0.0.0' });
    await legacy.connect(new LegacyTransport(new URL(gw.url)));
    assert.equal(value(await legacy.callTool({ name: 'fabric_status', arguments: {} })).pid, requested.pid);
    assert.equal(gw.stats().backend.spawns, 1);
  } finally { await first?.close(); await second?.close(); await legacy?.close(); await gw.close(); }
});

test('malformed modern claims are rejected before backend acquisition; metadata cannot grant identity', async () => {
  const gw = await startPrivateGateway(profile);
  try {
    const response = await raw(gw, body('tools/call', { name: 'fabric_request', arguments: {} }),
      { 'mcp-protocol-version': '2025-11-25' });
    assert.equal(response.status, 400);
    await response.text();
    assert.equal(gw.stats().backend.spawns, 0);
    assert.equal(gw.stats().sessions.started, 0);
    const invalid = await raw(gw, { jsonrpc: '2.0', id: 2, method: 'tools/call',
      params: { name: 'fabric_request', _meta: { [PROTOCOL_VERSION_META_KEY]: '2026-07-28' } } });
    assert.equal(invalid.status, 400);
    await invalid.text();
    assert.equal(gw.stats().backend.spawns, 0);
    assert.equal(gw.stats().sessions.started, 0);
  } finally { await gw.close(); }
});

test('modern calls cannot reach unrelated tools, and catalog drift fails closed', async () => {
  for (const unrelated of [false, true]) {
    const gw = await startPrivateGateway({ ...profile, childEnv: { FIXTURE_UNRELATED: String(unrelated) } });
    let client;
    try {
      client = await connect(gw);
      await assert.rejects(client.callTool({ name: 'start_process', arguments: {} }), /Fabric-only boundary/);
      assert.equal(gw.stats().backend.spawns, 0);
      if (unrelated) await assert.rejects(client.listTools(), /unrelated tool/);
      else assert.equal((await client.listTools()).tools.length, 9);
      assert.equal(gw.stats().sessions.active, 0);
    } finally { await client?.close(); await gw.close(); }
  }
});

test('an effectful timeout preserves UNKNOWN and the real facade refuses replay on the next exchange', async () => {
  const gw = await startPrivateGateway({ ...profile,
    childEnv: { FIXTURE_FACADE_TIMEOUT: 'true' } });
  let client;
  const args = { run_id: 'fixture-timeout', root_id: 'fixture-root', parent_id: 'fixture-root',
    task_class: 'mechanical', task_complexity: 'C0_MECHANICAL', work_packet: 'Disposable fixture only.' };
  try {
    client = await connect(gw);
    await client.listTools(); // Verify startup before the deliberately pending effect.
    await assert.rejects(client.callTool({ name: 'fabric_request', arguments: args }), error => {
      assert.match(error.message, /EFFECT_UNKNOWN/);
      assert.equal(error.code, -32603);
      assert.equal(error.data['private-studio-mcp/effect'], 'UNKNOWN');
      return true;
    });
    const generation = gw.stats().backend.owners[0].generation;
    const replay = value(await client.callTool({ name: 'fabric_request', arguments: args }));
    assert.equal(replay.error, 'REQUEST_ALREADY_ATTEMPTED');
    assert.equal(replay.retry_allowed, false);
    const observed = value(await client.callTool({ name: 'fabric_status', arguments: {
      run_id: args.run_id, root_id: args.root_id } }));
    assert.equal(observed.status.fixture_effects, 1);
    assert.equal(gw.stats().backend.spawns, 1);
    assert.equal(gw.stats().backend.owners[0].generation, generation);
    assert.equal(gw.stats().sessions.active, 0);
  } finally { await client?.close(); await gw.close(); }
});

test('retained output survives exchanges and cannot be read under another authenticated principal', async () => {
  const auth = { middleware(req, res, next) {
    const principal = req.headers.authorization;
    if (!['alice', 'bob'].includes(principal)) return res.status(401).end();
    req.auth = { principal, clientId: principal, scopes: ['studio.control'] }; next();
  } };
  const gw = await startGateway({ ...profile, testMode: true, childEnv: { FIXTURE_LARGE: 'true' } }, auth);
  let alice, bob;
  try {
    const unauthenticated = await raw(gw, body('tools/call', { name: 'fabric_request', arguments: {} }));
    assert.equal(unauthenticated.status, 401);
    assert.equal(gw.stats().sessions.started, 0);
    alice = await connect(gw, { authorization: 'alice' });
    await alice.listTools(); // Paging requires verified untyped catalog metadata.
    const receipt = value(await alice.callTool({ name: 'fabric_result', arguments: {} }));
    assert.equal(receipt.status, 'OUTPUT_PAGED', JSON.stringify(receipt).slice(0,1200));
    bob = await connect(gw, { authorization: 'bob' });
    const foreign = value(await bob.callTool({ name: 'studio_output_page', arguments: {
      receipt_id: receipt.receipt_id, offset: 0 } }));
    assert.equal(foreign.status, 'OUTPUT_NOT_AVAILABLE');
    const chunks = []; let offset = 0;
    for (let n = 0; n < 100; n++) {
      const page = value(await alice.callTool({ name: 'studio_output_page', arguments: {
        receipt_id: receipt.receipt_id, offset } }));
      chunks.push(page.text);
      if (page.done) break;
      assert.ok(page.next_offset > offset); offset = page.next_offset;
    }
    const exact = chunks.join('');
    assert.equal(Buffer.byteLength(exact), receipt.source_bytes);
    assert.equal(createHash('sha256').update(exact).digest('hex'), receipt.sha256);
    assert.equal(value(JSON.parse(exact)).resultCalls, 1);
    assert.equal(value(await alice.callTool({ name: 'fabric_status', arguments: {} })).resultCalls, 1);
    assert.equal(gw.stats().sessions.active, 0);
  } finally { await alice?.close(); await bob?.close(); await gw.close(); }
});

test('HTTP disconnect after dispatch never closes the shared owner or replays the real facade run', async () => {
  const gw = await startPrivateGateway({ ...profile, childEnv: { FIXTURE_FACADE_TIMEOUT: 'true' } });
  let client;
  const args = { run_id: 'fixture-timeout', root_id: 'fixture-root', parent_id: 'fixture-root',
    task_class: 'mechanical', task_complexity: 'C0_MECHANICAL', work_packet: 'Disposable disconnect fixture.' };
  const abort = new AbortController();
  try {
    client = await connect(gw); await client.listTools();
    const pending = fetch(gw.url, { method: 'POST', signal: abort.signal,
      headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream',
        'mcp-protocol-version': '2026-07-28', 'mcp-method': 'tools/call', 'mcp-name': 'fabric_request' },
      body: JSON.stringify(body('tools/call', { name: 'fabric_request', arguments: args }, 902)) }).then(r => r.text());
    let started = false;
    for (let n = 0; n < 30; n++) {
      const state = value(await client.callTool({ name: 'fabric_status', arguments: {
        run_id: args.run_id, root_id: args.root_id } }));
      if (state.status.fixture_effects === 1) { started = true; break; }
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    assert.equal(started, true, 'abort only after the fixture effect was observed');
    const generation = gw.stats().backend.owners[0].generation;
    abort.abort();
    await assert.rejects(pending, /abort/i);
    const replay = value(await client.callTool({ name: 'fabric_request', arguments: args }));
    assert.equal(replay.error, 'REQUEST_ALREADY_ATTEMPTED');
    const state = value(await client.callTool({ name: 'fabric_status', arguments: {
      run_id: args.run_id, root_id: args.root_id } }));
    assert.equal(state.status.fixture_effects, 1);
    assert.equal(gw.stats().backend.owners[0].generation, generation);
    assert.equal(gw.stats().backend.spawns, 1);
  } finally { abort.abort(); await client?.close(); await gw.close(); }
});
