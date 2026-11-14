import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { chmod, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import os from 'node:os';
import test from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { startGateway } from './gateway.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(HERE, 'fixtures/backend.mjs');
const shellQuote = value => "'" + value.replaceAll("'", "'\"'\"'") + "'";
async function boot(t, { enabled = true, account = 'account-a', portStatus = 'OBSERVED', t3Only = false } = {}) {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'gateway-t3-proof-'));
  const profilePath = path.join(dir, 'profile.json');
  const port = path.join(dir, 'fixed-python-port');
  const portScript = path.join(dir, 'fixed-port-source.mjs');
  const raw = JSON.stringify({ schema: 'mastermind.t3_dot_native_profile.v1',
    principal_key: 'p:tunnel:account-a', operations: ['t3_fleet_environments', 't3_thread_send'], timeout_seconds: 5 });
  await writeFile(profilePath, raw, { mode: 0o600 });
  // Hermetic fake for the fixed port only. No native client, profile, credential,
  // provider, inference, callback or external runtime is accessed by these tests.
  // The gateway intentionally drops host-toolchain PATH entries. A fake
  // port must use this test's exact interpreter, not an ambient /usr/bin node.
  await writeFile(portScript, `let text='';process.stdin.on('data',x=>text+=x);process.stdin.on('end',()=>{
 const x=JSON.parse(text);if(x.principal_key!=='p:tunnel:account-a')process.exit(7);
 console.log(JSON.stringify({schema:'mastermind.t3_dot_result.v1',status:${JSON.stringify(portStatus)},operation:x.tool,
 data:{environment_id:'fixture-env',original_arguments:x.arguments},original:{operation_id:x.arguments.operation_id},
 retry_allowed:false,parent_accepted:false}));});\n`, { mode: 0o700 });
  await writeFile(port, '#!/bin/sh\nexec ' + shellQuote(process.execPath) + ' '
    + shellQuote(portScript) + ' "$@"\n', { mode: 0o700 });
  await chmod(port, 0o700);
  const config = { host: '127.0.0.1', port: 0, command: process.execPath,
    args: [FIXTURE], cwd: HERE, stateDir: path.join(dir, 'state'), testMode: true,
    requestTimeoutMs: 10000, maxSessions: 4, t3Only,
    ...(enabled ? { t3Control: { enabled: true, pythonPath: port, sourceRoot: dir, profilePath,
      profileSha256: createHash('sha256').update(raw).digest('hex') } } : {}) };
  const gw = await startGateway(config, { middleware(req, _res, next) {
    if (req.headers.authorization !== 'Bearer fixture-auth') throw new Error('unavailable');
    req.auth = { principal: `tunnel:${account}`, clientId: 'fixed-test-client', scopes: ['studio.control'] };
    next();
  }, mount() {} });
  const client = new Client({ name: 't3-gateway-fixture', version: '1.0.0' }, { capabilities: {} });
  t.after(async () => { await client.close(); await gw.close(); await rm(dir, { recursive: true, force: true }); });
  await client.connect(new StreamableHTTPClientTransport(new URL(gw.url), {
    requestInit: { headers: { authorization: 'Bearer fixture-auth' } },
  }));
  return { client, gw, profilePath, port };
}

test('real MCP catalog exposes only the current authenticated account T3 grant', async t => {
  const { client } = await boot(t);
  const list = await client.listTools();
  const tools = list.tools.filter(x => x.name.startsWith('t3_'));
  assert.deepEqual(tools.map(x => x.name).sort(), ['t3_fleet_environments', 't3_thread_send']);
  assert.equal(tools.find(x => x.name === 't3_fleet_environments').annotations.readOnlyHint, true);
  assert.equal(tools.find(x => x.name === 't3_thread_send').annotations.readOnlyHint, false);
  assert.equal(tools.find(x => x.name === 't3_thread_send').inputSchema.additionalProperties, false);
  const result = await client.callTool({ name: 't3_fleet_environments', arguments: {} });
  assert.equal(result.isError, false);
  assert.equal(result.structuredContent.status, 'OBSERVED');
  assert.equal(result.structuredContent.data.environment_id, 'fixture-env');
});
test('disabled reserved T3 control is not forwarded to the generic backend', async t => {
  const { client } = await boot(t, { enabled: false });
  assert.equal((await client.listTools()).tools.some(x => x.name.startsWith('t3_')), false);
  await assert.rejects(() => client.callTool({ name: 't3_thread_send', arguments: {} }), /not enabled/);
});
test('another account cannot discover or call the enrolled account T3 controls', async t => {
  const { client } = await boot(t, { account: 'other-account' });
  assert.equal((await client.listTools()).tools.some(x => x.name.startsWith('t3_')), false);
  const value = await client.callTool({ name: 't3_fleet_environments', arguments: {} });
  assert.equal(value.isError, true);
  assert.equal(value.structuredContent.status, 'REJECTED');
});
test('native effect uncertainty reaches the MCP consumer with original operation and no acceptance', async t => {
  const { client } = await boot(t, { portStatus: 'EFFECT_UNKNOWN' });
  const value = await client.callTool({ name: 't3_thread_send', arguments: { operation_id: 'original-op' } });
  assert.equal(value.isError, true);
  assert.equal(value.structuredContent.status, 'EFFECT_UNKNOWN');
  assert.equal(value.structuredContent.original.operation_id, 'original-op');
  assert.equal(value.structuredContent.retry_allowed, false);
  assert.equal(value.structuredContent.parent_accepted, false);
});
test('revoked profile removes only T3 tools, not ordinary gateway liveness', async t => {
  const { client, profilePath } = await boot(t);
  await writeFile(profilePath, '{}');
  const list = await client.listTools();
  assert.equal(list.tools.some(x => x.name.startsWith('t3_')), false);
  assert.equal(list.tools.some(x => x.name === 'studio_ping'), true);
});


test('T3-only Dot view exposes no shell/files/resources or generic backend', async t => {
  const { client } = await boot(t, { t3Only: true });
  assert.deepEqual((await client.listTools()).tools.map(x => x.name).sort(),
    ['studio_output_page', 'studio_ping', 't3_fleet_environments', 't3_thread_send']);
  for (const name of ['start_process', 'read_file', 'studio_select_host', 'echo', 'paper_edit']) {
    await assert.rejects(() => client.callTool({ name, arguments: {} }), /T3-only view refuses/);
  }
  assert.deepEqual(await client.listResources(), { resources: [] });
  assert.deepEqual(await client.listPrompts(), { prompts: [] });
  await assert.rejects(() => client.readResource({ uri: 'file:///private/host' }), /no backend resources/);
  const result = await client.callTool({ name: 't3_fleet_environments', arguments: {} });
  assert.equal(result.structuredContent.status, 'OBSERVED');
  assert.match(client.getInstructions(), /No shell, SSH/);
});


test('T3-only retained output cannot outlive the installed account grant', async t => {
  const { client, profilePath } = await boot(t, { t3Only: true });
  await client.callTool({ name: 't3_fleet_environments', arguments: {} });
  await writeFile(profilePath, '{}');
  await assert.rejects(() => client.callTool({ name: 'studio_output_page',
    arguments: { receipt_id: 'prior-receipt', offset: 0 } }), /profile is no longer current/);
});


test('fixed fake port uses the exact test interpreter even without a toolchain PATH', async t => {
  const { port } = await boot(t, { t3Only: true });
  const result = spawnSync(port, ['-B', '-m', 'fixture-only'], {
    input: JSON.stringify({ principal_key: 'p:tunnel:account-a', tool: 't3_fleet_environments', arguments: {} }),
    encoding: 'utf8', timeout: 5000, env: { PATH: '/no-test-interpreter-here' },
  });
  assert.equal(result.status, 0, result.stderr);
  const value = JSON.parse(result.stdout);
  assert.equal(value.status, 'OBSERVED');
  assert.equal(value.operation, 't3_fleet_environments');
});
