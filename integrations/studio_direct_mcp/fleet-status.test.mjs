import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { chmod, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import {
  STUDIO_FLEET_STATUS_TOOL,
  createFleetStatus,
  fleetStatusErrorResult,
  fleetStatusToolResult,
  resolveFleetStatusConfig,
} from './fleet-status.mjs';

async function fixture(body) {
  const dir = await mkdtemp(join(tmpdir(), 'studio-fleet-status-'));
  const launcher = join(dir, 'studio-direct');
  await writeFile(launcher, `#!/bin/sh\nprintf '%s\\n' '${body}'\n`);
  await chmod(launcher, 0o700);
  const bytes = await import('node:fs/promises').then(({readFile}) => readFile(launcher));
  const hash = createHash('sha256').update(bytes).digest('hex');
  return {
    dir,
    launcher,
    config: {enabled:true, launcherPath:launcher, launcherSha256:hash, timeoutMs:5000},
  };
}

function statusRow(account, ready = true) {
  return {
    account,
    action: 'status',
    steps: [],
    ready,
    gateway: {
      account,
      label: `com.mastermind.studio-direct-private.${account}`,
      loaded: true,
      pid: 987654321,
      port: 45018,
      running: true,
    },
    tunnel: {
      account,
      label: `com.mastermind.studio-direct-tunnel.${account}`,
      loaded: ready,
      pid: ready ? 123456789 : null,
      running: ready,
      healthy: ready,
      ready,
      configurationDrift: false,
      tunnelReady: ready,
      controlPlanePollReady: ready,
      gatewayReady: true,
      transportTTL: '5h',
      maxConcurrentRequests: 4,
      gatewayPort: 45018,
      healthPort: 45019,
      tunnelId: 'tunnel_0123456789abcdef0123456789abcdef',
      organizationId: 'org-SensitiveInternal123',
      managedAlias: `studio-direct-private-${account}`,
      managedAliasRunning: false,
    },
  };
}

function ownerFor(accounts) {
  const readyCount = accounts.filter((row) => row.ready === true).length;
  return {
    schema:'mastermind.studio_direct_fleet_status.v1',
    action:'status',
    accountCount:accounts.length,
    readyCount,
    allReady:accounts.length > 0 && readyCount === accounts.length,
    accounts,
  };
}

test('tool metadata is closed read-only status', () => {
  const a = STUDIO_FLEET_STATUS_TOOL.annotations;
  assert.equal(STUDIO_FLEET_STATUS_TOOL.name, 'studio_fleet_status');
  assert.deepEqual(
    [a.readOnlyHint, a.destructiveHint, a.idempotentHint, a.openWorldHint],
    [true, false, true, false],
  );
  assert.deepEqual(STUDIO_FLEET_STATUS_TOOL.inputSchema.required, []);
});

test('config is opt-in and closed', () => {
  assert.equal(resolveFleetStatusConfig(null), null);
  assert.equal(resolveFleetStatusConfig({enabled:false}), null);
  assert.throws(() => resolveFleetStatusConfig({
    enabled:true, launcherPath:'relative', launcherSha256:'0'.repeat(64), timeoutMs:5000,
  }), /must be absolute/);
  assert.throws(() => resolveFleetStatusConfig({
    enabled:true, launcherPath:'/tmp/x', launcherSha256:'0'.repeat(64), timeoutMs:5000, extra:true,
  }), /unknown key/);
});

test('status returns only the bounded public fleet projection', async t => {
  const owner = ownerFor([statusRow('chatgpt1', true)]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.schema, 'mastermind.studio_fleet_status_tool.v2');
  assert.equal(result.state, 'READY');
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 1);
  assert.equal(result.allReady, true);
  assert.deepEqual(result.accounts, [{
    account: 'chatgpt1',
    state: 'READY',
    ready: true,
    gateway: { loaded: true, running: true },
    tunnel: {
      loaded: true,
      running: true,
      healthy: true,
      ready: true,
      controlPlanePollReady: true,
      gatewayReady: true,
      transportTTL: '5h',
      maxConcurrentRequests: 4,
    },
    issues: [],
  }]);
  assert.equal(Object.hasOwn(result, 'owner'), false);
});

test('raw owner internals never appear in structured or text output', async t => {
  const rawError = '/Users/chriswong/private sk-proj-secret-shape raw stderr 987654321 45018';
  const owner = ownerFor([
    statusRow('chatgpt1', true),
    { account:'admin-business', ready:false, error:rawError },
  ]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'DEGRADED');
  assert.deepEqual(result.accounts[1], {
    account: 'admin-business',
    state: 'DEGRADED',
    ready: false,
    gateway: null,
    tunnel: null,
    issues: ['OWNER_STATUS_UNAVAILABLE'],
  });

  const toolResult = fleetStatusToolResult(result);
  const surfaces = [
    JSON.stringify(toolResult.structuredContent),
    toolResult.content[0].text,
  ];
  for (const surface of surfaces) {
    for (const forbidden of [
      '/Users/chriswong',
      'sk-proj-secret-shape',
      'raw stderr',
      '987654321',
      '45018',
      '45019',
      'tunnel_0123456789abcdef0123456789abcdef',
      'org-SensitiveInternal123',
      'managedAlias',
      'com.mastermind.studio-direct',
    ]) {
      assert.equal(surface.includes(forbidden), false, `leaked raw owner field: ${forbidden}`);
    }
  }
});

test('closed issue codes explain degraded known status without raw internals', async t => {
  const row = statusRow('admin-business', false);
  row.gateway.running = false;
  row.tunnel.gatewayReady = false;
  const owner = ownerFor([row]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.accounts[0].state, 'DEGRADED');
  assert.deepEqual(result.accounts[0].issues, [
    'GATEWAY_NOT_RUNNING',
    'TUNNEL_NOT_LOADED',
    'TUNNEL_NOT_RUNNING',
  ]);
});

test('running tunnel exposes closed poll and readiness issue codes', async t => {
  const row = statusRow('admin-business', false);
  row.tunnel.loaded = true;
  row.tunnel.running = true;
  row.tunnel.gatewayReady = false;
  const owner = ownerFor([row]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.deepEqual(result.accounts[0].issues, [
    'TUNNEL_NOT_HEALTHY',
    'CONTROL_PLANE_POLL_NOT_READY',
    'TUNNEL_NOT_READY',
    'GATEWAY_NOT_READY',
  ]);
});

test('configuration drift is projected as one closed issue without raw internals', async t => {
  const row = statusRow('admin-business', true);
  row.ready = false;
  row.tunnel.configurationDrift = true;
  row.tunnel.healthy = false;
  row.tunnel.ready = false;
  row.tunnel.tunnelReady = false;
  row.tunnel.controlPlanePollReady = false;
  row.tunnel.gatewayReady = false;
  const owner = ownerFor([row]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'DEGRADED');
  assert.deepEqual(result.accounts[0].issues, ['CONFIGURATION_DRIFT']);
  const rendered = JSON.stringify(fleetStatusToolResult(result));
  assert.equal(rendered.includes('configurationDrift'), false);
  assert.equal(rendered.includes('tunnel_0123456789abcdef0123456789abcdef'), false);
});

test('owner counts, readiness, duplicates, types, and future fields fail closed', async t => {
  const cases = [];
  const valid = ownerFor([statusRow('chatgpt1', true)]);
  cases.push({...valid, accountCount:2});
  cases.push({...valid, readyCount:0});
  cases.push({...valid, allReady:false});
  cases.push({...valid, futureField:true});
  cases.push(ownerFor([statusRow('chatgpt1', true), statusRow('chatgpt1', true)]));
  {
    const row = statusRow('chatgpt1', true);
    row.gateway.futureField = 'must-refuse';
    cases.push(ownerFor([row]));
  }
  {
    const row = statusRow('chatgpt1', true);
    row.tunnel.ready = 'yes';
    cases.push(ownerFor([row]));
  }
  {
    const row = statusRow('sk-proj-secret-shaped', true);
    cases.push(ownerFor([row]));
  }
  {
    const row = statusRow('chatgpt1', true);
    row.tunnel.transportTTL = '/Users/chriswong/private-secret';
    cases.push(ownerFor([row]));
  }
  for (const field of ['controlPlanePollReady', 'healthy', 'running']) {
    const row = statusRow('chatgpt1', true);
    row.tunnel[field] = false;
    cases.push(ownerFor([row]));
  }
  {
    const row = statusRow('chatgpt1', true);
    row.tunnel.gatewayReady = false;
    cases.push(ownerFor([row]));
  }
  {
    const row = statusRow('chatgpt1', true);
    delete row.tunnel.controlPlanePollReady;
    cases.push(ownerFor([row]));
  }

  for (const [index, value] of cases.entries()) {
    const fx = await fixture(JSON.stringify(value));
    t.after(() => rm(fx.dir, {recursive:true, force:true}));
    await assert.rejects(
      () => createFleetStatus(fx.config).status(),
      /FLEET_STATUS_OWNER_RESULT_INVALID/,
      `case ${index} must fail closed`,
    );
  }
});

test('launcher drift refuses before owner execution', async t => {
  const owner = ownerFor([]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  await writeFile(fx.launcher, '#!/bin/sh\nexit 99\n');
  await assert.rejects(() => createFleetStatus(fx.config).status(), /FLEET_STATUS_LAUNCHER_DRIFT/);
});

test('malformed owner output is a bounded refusal', async t => {
  const fx = await fixture('not-json');
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  let caught;
  try {
    await createFleetStatus(fx.config).status();
  } catch (error) {
    caught = error;
  }
  const result = fleetStatusErrorResult(caught);
  assert.equal(result.isError, true);
  assert.equal(result.structuredContent.state, 'REFUSED');
  assert.equal(result.structuredContent.code, 'FLEET_STATUS_OWNER_RESULT_INVALID');
});


function privateFabricStatus(account, ready = false) {
  const row = statusRow(account, ready);
  if (!ready) {
    // This is the genuine stopped-tunnel shape reported by the Studio owner.
    row.tunnel.transportTTL = null;
    row.tunnel.maxConcurrentRequests = null;
    row.tunnel.gatewayPort = null;
    row.tunnel.healthPort = null;
    row.tunnel.tunnelId = null;
    row.tunnel.organizationId = null;
  }
  return row;
}

test('private Fabric seats are verified but never exposed in the 13-seat owner result', async t => {
  const publicSeats = [
    'admin-business', 'chatgpt1', 'chatgpt2-business', 'chatgpt2-personal',
    'chatgpt3', 'chatgpt3-w570f6f34', 'chatgpt3-wa2a9e6f9', 'chatgpt4',
  ];
  const privateSeats = [
    'fabric-c3-570f6f34', 'fabric-chatgpt3-w570f6f34',
    'fabric-design', 'fabric-read', 'subagent-fabric-c3',
  ];
  const owner = ownerFor([
    ...publicSeats.map((account) => ({ account, ready: false, error: 'owner status unavailable' })),
    privateFabricStatus(privateSeats[0]),
    privateFabricStatus(privateSeats[1]),
    { account: privateSeats[2], ready: false, error: '/private/root/key/shaped diagnostic' },
    { account: privateSeats[3], ready: false, error: 'private daemon unavailable' },
    privateFabricStatus(privateSeats[4]),
  ]);
  assert.equal(owner.accountCount, 13);
  assert.equal(owner.readyCount, 0);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, { recursive:true, force:true }));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'DEGRADED');
  assert.equal(result.accountCount, publicSeats.length);
  assert.equal(result.readyCount, 0);
  assert.equal(result.allReady, false);
  assert.deepEqual(result.accounts.map((row) => row.account), publicSeats);
  const rendered = JSON.stringify(fleetStatusToolResult(result));
  for (const secret of [...privateSeats, '/private/root/key', 'tunnel_0123456789abcdef', 'org-SensitiveInternal']) {
    assert.equal(rendered.includes(secret), false, `private owner field leaked: ${secret}`);
  }
});

test('private seats are included in original owner readiness consistency checks', async t => {
  const owner = ownerFor([
    { account:'chatgpt1', ready:false, error:'public unavailable' },
    privateFabricStatus('fabric-c3-570f6f34', true),
  ]);
  assert.equal(owner.readyCount, 1);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, { recursive:true, force:true }));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 0);
  assert.equal(result.allReady, false);
  assert.equal(result.accounts[0].account, 'chatgpt1');
  const forged = { ...owner, readyCount:0 };
  const invalid = await fixture(JSON.stringify(forged));
  t.after(() => rm(invalid.dir, { recursive:true, force:true }));
  await assert.rejects(() => createFleetStatus(invalid.config).status(), /FLEET_STATUS_OWNER_RESULT_INVALID/);
});

test('malformed or unknown private seat rows still fail closed', async t => {
  const cases = [
    ownerFor([privateFabricStatus('sk-proj-secret-shaped')]),
    ownerFor([privateFabricStatus('fabric-c3-570f6f34'), privateFabricStatus('fabric-c3-570f6f34')]),
    ownerFor([{ ...privateFabricStatus('fabric-design'), extra:'refuse' }]),
  ];
  const badScope = privateFabricStatus('fabric-c3-570f6f34');
  badScope.tunnel.account = 'chatgpt1';
  cases.push(ownerFor([badScope]));
  const badTTL = statusRow('chatgpt1', true);
  badTTL.tunnel.transportTTL = null;
  cases.push(ownerFor([badTTL]));
  const badPrivateReady = privateFabricStatus('fabric-read', true);
  badPrivateReady.tunnel.transportTTL = null;
  cases.push(ownerFor([badPrivateReady]));
  for (const [n, owner] of cases.entries()) {
    const fx = await fixture(JSON.stringify(owner));
    t.after(() => rm(fx.dir, { recursive:true, force:true }));
    await assert.rejects(
      () => createFleetStatus(fx.config).status(),
      /FLEET_STATUS_OWNER_RESULT_INVALID/,
      `invalid private seat case ${n}`,
    );
  }
});

test('new owner-enumerated private Fabric seats remain bounded and undisclosed', async t => {
  const owner = ownerFor([
    statusRow('chatgpt1', true),
    privateFabricStatus('fabric-new-worker-catalog-2027'),
  ]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.schema, 'mastermind.studio_fleet_status_tool.v2');
  assert.equal(result.scope, 'public_accounts');
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 1);
  assert.equal(result.publicAllReady, true);
  assert.equal(result.allReady, false);
  assert.equal(result.state, 'DEGRADED');
  assert.deepEqual(result.issues, ['OWNER_FLEET_DEGRADED']);
  assert.deepEqual(result.accounts.map(x => x.account), ['chatgpt1']);
  assert.equal(JSON.stringify(result).includes('fabric-new-worker-catalog-2027'), false);
});

test('stopped public tunnel may omit TTL without concealing degraded owner readiness', async t => {
  const row = statusRow('chatgpt1', false);
  row.tunnel.transportTTL = null;
  const fx = await fixture(JSON.stringify(ownerFor([row])));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'DEGRADED');
  assert.equal(result.allReady, false);
  assert.equal(result.publicAllReady, false);
  assert.deepEqual(result.accounts.map(x => x.account), ['chatgpt1']);
});

test('a healthy public projection cannot report owner fleet READY when private is degraded', async t => {
  const fx = await fixture(JSON.stringify(ownerFor([
    statusRow('chatgpt1', true),
    {account:'subagent-fabric-future', ready:false, error:'private unavailable'},
  ])));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.publicAllReady, true);
  assert.equal(result.allReady, false);
  assert.equal(result.state, 'DEGRADED');
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 1);
  const text = JSON.stringify(fleetStatusToolResult(result));
  assert.equal(text.includes('subagent-fabric-future'), false);
  assert.equal(text.includes('private unavailable'), false);
});
