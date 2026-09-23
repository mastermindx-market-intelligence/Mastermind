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
  assert.equal(result.schema, 'mastermind.studio_fleet_status_tool.v1');
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
