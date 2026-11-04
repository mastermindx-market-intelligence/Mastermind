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

test('installed Fabric-launcher configuration is retained and fenced', () => {
  const root = '/private/qualified-launcher';
  const hash = 'a'.repeat(64);
  const base = {enabled:true, launcherPath:root, launcherSha256:hash, timeoutMs:15000};
  const value = resolveFleetStatusConfig({
    ...base,
    fabricLauncherPath:'/private/qualified-pool', fabricLauncherSha256:'b'.repeat(64), fabricTimeoutMs:8000,
  });
  assert.equal(value.fabricLauncherPath, '/private/qualified-pool');
  assert.equal(value.fabricLauncherSha256, 'b'.repeat(64));
  assert.equal(value.fabricTimeoutMs, 8000);
  assert.throws(() => resolveFleetStatusConfig({...base, fabricLauncherPath:'/private/missing-pool'}),
    /fabricLauncherSha256/);
  assert.throws(() => resolveFleetStatusConfig({...base, fabricLauncherPath:'/private/pool',
    fabricLauncherSha256:'b'.repeat(64), fabricTimeoutMs:8000, extraCapability:'surprise'}),
  /unknown key/);
});

test('signed Fabric placement view retains v2 physical fleet fields without exposing owner internals', async t => {
  const owner = ownerFor([statusRow('chatgpt1', true)]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const fabricLauncher = join(fx.dir, 'fabric-launcher');
  const script = `#!/bin/sh
printf '{"schema":"placement-view.private-candidate.v1","mode":"%s","host_eligibility":{"hosts":[]}}\n' "$3"
`;
  await writeFile(fabricLauncher, script);
  await chmod(fabricLauncher, 0o700);
  const sha = createHash('sha256').update(script).digest('hex');
  const cfg = {...fx.config, fabricLauncherPath:fabricLauncher,
    fabricLauncherSha256:sha, fabricTimeoutMs:5000};
  const result = await createFleetStatus(cfg).status();
  assert.equal(result.schema, 'mastermind.studio_fleet_status_tool.v2');
  assert.equal(result.state, 'READY');
  assert.equal(result.accountCount, 1);
  assert.deepEqual(result.issues, []);
  assert.deepEqual(result.physicalFleet, {
    schema:'mastermind.studio_fleet_hosts.v1',
    scope:'subagent-fabric-registered-hosts',hostCount:0,hosts:[],
    advisoryOnly:true,placementAuthority:false,executionAuthority:false,
  });
  const surface = JSON.stringify(fleetStatusToolResult(result));
  assert.equal(surface.includes('fabric-launcher'), false);
  assert.equal(surface.includes(fabricLauncher), false);
});

test('Fabric launcher drift degrades physical view but preserves validated public seats', async t => {
  const owner = ownerFor([statusRow('chatgpt1', true)]);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus({...fx.config,
    fabricLauncherPath:fx.launcher, fabricLauncherSha256:'f'.repeat(64),
    fabricTimeoutMs:5000}).status();
  assert.equal(result.schema, 'mastermind.studio_fleet_status_tool.v2');
  assert.equal(result.state, 'DEGRADED');
  assert.equal(result.allReady, true);
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 1);
  assert.equal(result.physicalFleet, null);
  assert.deepEqual(result.issues, ['FLEET_STATUS_FABRIC_LAUNCHER_DRIFT']);
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

test('extra closed internal service rows do not invalidate eight public ChatGPT seats', async t => {
  const publicSeats = [
    'admin-business', 'chatgpt1', 'chatgpt2-business', 'chatgpt2-personal',
    'chatgpt3', 'chatgpt3-w570f6f34', 'chatgpt3-wa2a9e6f9', 'chatgpt4',
  ];
  const internal = [
    'fabric-c3-570f6f34', 'fabric-chatgpt3-w570f6f34', 'fabric-design',
    'fabric-read', 'mastermind-os-publication', 'subagent-fabric-c3',
  ];
  const raw = ownerFor([
    ...publicSeats.map(name => statusRow(name, true)),
    ...internal.map(name => ({...statusRow(name, false), tunnel: {
      ...statusRow(name, false).tunnel, gatewayReady: false, transportTTL: null,
    }})),
  ]);
  assert.equal(raw.accountCount, 14);
  assert.equal(raw.readyCount, 8);
  const fx = await fixture(JSON.stringify(raw));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'READY');
  assert.equal(result.accountCount, 8);
  assert.equal(result.readyCount, 8);
  assert.equal(result.allReady, true);
  assert.deepEqual(result.accounts.map(a => a.account), publicSeats);
  const out = JSON.stringify(fleetStatusToolResult(result));
  for (const name of internal) assert.equal(out.includes(name), false);
});

test('healthy internal services do not hide or change public ChatGPT readiness', async t => {
  const publicReady = statusRow('chatgpt1', true);
  const internalReady = statusRow('fabric-read', true);
  const internalDown = statusRow('fabric-design', false);
  internalDown.tunnel.gatewayReady = false;
  internalDown.tunnel.transportTTL = null;
  const owner = ownerFor([publicReady, internalReady, internalDown]);
  assert.equal(owner.accountCount, 3);
  assert.equal(owner.readyCount, 2);
  assert.equal(owner.allReady, false);
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 1);
  assert.equal(result.allReady, true);
  assert.equal(result.state, 'READY');
  assert.deepEqual(result.accounts.map(row => row.account), ['chatgpt1']);
  const surfaced = JSON.stringify(fleetStatusToolResult(result));
  assert.equal(surfaced.includes('fabric-read'), false);
  assert.equal(surfaced.includes('fabric-design'), false);
});

test('internal fleet status rows cannot hide malformed or duplicated owner evidence', async t => {
  const internal = statusRow('fabric-design', false);
  internal.tunnel.gatewayReady = false;
  internal.tunnel.transportTTL = null;
  const cases = [
    ownerFor([statusRow('chatgpt1'), internal, {...internal}]),
    ownerFor([statusRow('chatgpt1'), {...internal, extraField: true}]),
    ownerFor([statusRow('chatgpt1'), {...internal, ready: true}]),
    ownerFor([statusRow('chatgpt1'), {...internal, gateway: {...internal.gateway, account: 'chatgpt1'}}]),
    ownerFor([statusRow('chatgpt1'), statusRow('unknown-fabric-service', false)]),
  ];
  for (const [index, raw] of cases.entries()) {
    const fx = await fixture(JSON.stringify(raw));
    t.after(() => rm(fx.dir, {recursive:true, force:true}));
    await assert.rejects(() => createFleetStatus(fx.config).status(),
      /FLEET_STATUS_OWNER_RESULT_INVALID/, 'invalid internal case ' + index);
  }
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


test('fully absent tunnel with null TTL is a bounded DEGRADED seat', async t => {
  const row = statusRow('chatgpt1', false);
  row.tunnel.gatewayReady = false;
  row.tunnel.transportTTL = null;
  const fx = await fixture(JSON.stringify(ownerFor([row])));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'DEGRADED');
  assert.equal(result.accountCount, 1);
  assert.equal(result.readyCount, 0);
  assert.deepEqual(result.accounts[0].issues, ['TUNNEL_NOT_LOADED', 'TUNNEL_NOT_RUNNING']);
  assert.equal(result.accounts[0].tunnel.transportTTL, null);
  assert.equal(JSON.stringify(fleetStatusToolResult(result)).includes(row.tunnel.tunnelId), false);
});

test('null TTL still refuses loaded, active, anomalous, or claimed-ready tunnels', async t => {
  const variants = [
    ['loaded', row => { row.tunnel.loaded = true; }],
    ['running', row => { row.tunnel.loaded = true; row.tunnel.running = true; }],
    ['healthy', row => { row.tunnel.healthy = true; }],
    ['poll-ready', row => { row.tunnel.controlPlanePollReady = true; }],
    ['transport-ready', row => { row.tunnel.tunnelReady = true; }],
    ['gateway-ready', row => { row.tunnel.gatewayReady = true; }],
    ['owner-claims-ready', row => { row.ready = true; }],
    ['unauthorized-ttl', row => { row.tunnel.transportTTL = '4h'; }],
    ['missing-ttl-field', row => { delete row.tunnel.transportTTL; }],
  ];
  for (const [name, mutate] of variants) {
    const row = statusRow('chatgpt1', false);
    row.tunnel.gatewayReady = false;
    row.tunnel.transportTTL = null;
    mutate(row);
    const fx = await fixture(JSON.stringify(ownerFor([row])));
    t.after(() => rm(fx.dir, {recursive:true, force:true}));
    await assert.rejects(() => createFleetStatus(fx.config).status(),
      /FLEET_STATUS_OWNER_RESULT_INVALID/, name);
  }
});
