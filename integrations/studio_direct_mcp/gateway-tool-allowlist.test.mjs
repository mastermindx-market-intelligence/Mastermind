import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';

import {resolveConfig, startGateway} from './gateway.mjs';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const FIXTURE = resolve(HERE, 'fixtures/backend.mjs');

function auth() {
  return {
    middleware(req, _res, next) {
      req.auth = {principal:'tool-allowlist-test', clientId:'test', scopes:[]};
      next();
    },
    mount() {},
  };
}

async function connect(gw) {
  const client = new Client({name:'tool-allowlist-test', version:'1'}, {capabilities:{}});
  const transport = new StreamableHTTPClientTransport(new URL(gw.url));
  await client.connect(transport);
  return {client, transport};
}

test('toolAllowlist config is closed, normalized, and duplicate-free', () => {
  assert.equal(resolveConfig({testMode:true}).toolAllowlist, null);
  assert.deepEqual(
    [...resolveConfig({testMode:true, toolAllowlist:['studio_ping','paper_read']}).toolAllowlist],
    ['paper_read','studio_ping'],
  );
  for (const value of [
    [],
    'studio_ping',
    [''],
    ['1bad'],
    ['studio/ping'],
    ['studio_ping','studio_ping'],
    Array.from({length:129}, (_, i) => `tool${i}`),
  ]) {
    assert.throws(() => resolveConfig({testMode:true, toolAllowlist:value}), /toolAllowlist/);
  }
});

test('local-only allowlist lists no backend tools and never spawns backend', async () => {
  const stateDir = await mkdtemp(resolve(tmpdir(), 'studio-allowlist-'));
  const gw = await startGateway({
    host:'127.0.0.1',
    port:0,
    command:process.execPath,
    args:[FIXTURE],
    cwd:HERE,
    childEnv:{...process.env},
    stateDir,
    testMode:true,
    toolAllowlist:['studio_ping'],
  }, auth());
  const {client} = await connect(gw);
  try {
    const listed = await client.listTools();
    assert.deepEqual(listed.tools.map((tool) => tool.name), ['studio_ping']);
    assert.equal(gw.stats().backend.spawns, 0);

    const ping = await client.callTool({name:'studio_ping', arguments:{}});
    assert.equal(ping.structuredContent.gatewayVersion, '0.1.9');
    assert.equal(gw.stats().backend.spawns, 0);

    await assert.rejects(
      () => client.callTool({name:'echo', arguments:{text:'must-not-dispatch'}}),
      /not exposed/i,
    );
    assert.equal(gw.stats().backend.spawns, 0);
    assert.equal(gw.stats().requests.byTool.echo, undefined);

    const resources = await client.listResources();
    assert.deepEqual(resources.resources, []);
    assert.equal(gw.stats().backend.spawns, 0);
  } finally {
    await client.close().catch(() => {});
    await gw.close();
    await rm(stateDir, {recursive:true, force:true});
  }
});

test('unrestricted gateway preserves backend catalog behavior', async () => {
  const stateDir = await mkdtemp(resolve(tmpdir(), 'studio-unrestricted-'));
  const gw = await startGateway({
    host:'127.0.0.1',
    port:0,
    command:process.execPath,
    args:[FIXTURE],
    cwd:HERE,
    childEnv:{...process.env},
    stateDir,
    testMode:true,
  }, auth());
  const {client} = await connect(gw);
  try {
    const listed = await client.listTools();
    assert.ok(listed.tools.some((tool) => tool.name === 'echo'));
    assert.ok(listed.tools.some((tool) => tool.name === 'studio_ping'));
    assert.ok(gw.stats().backend.spawns >= 1);
  } finally {
    await client.close().catch(() => {});
    await gw.close();
    await rm(stateDir, {recursive:true, force:true});
  }
});
