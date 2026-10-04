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


function fabricGate(host, gate, result, detail = '') {
  return { host, gate, result, detail };
}

function fabricRow(host, mode, {
  roles = ['lanes'],
  seat = false,
  eligible = true,
  candidateExcluded = false,
} = {}) {
  return {
    host,
    eligible,
    seat,
    ssh_alias: host === 'm2' ? null : host,
    score: eligible ? 0.75 : null,
    age: 12,
    gates: [
      fabricGate(host, 'roles', roles.includes('lanes') || seat ? 'PASS' : 'FAIL', roles.join(',')),
      fabricGate(host, 'mode', 'PASS', mode),
      fabricGate(host, 'automatic-qualification', 'PASS', 'not-held'),
      fabricGate(host, 'excluded', 'PASS', ''),
      fabricGate(host, 'fresh', 'PASS', 'age=12s'),
      fabricGate(host, 'reachable', 'PASS', ''),
      fabricGate(host, 'window', 'PASS', 'OPEN'),
      fabricGate(host, 'load', 'PASS', '2.5<12'),
      ...(seat ? [fabricGate(host, 'seat-load', 'PASS', '2.5<12')] : []),
      fabricGate(host, 'lane-ceiling', 'PASS', '0<2'),
      fabricGate(host, 'disk', 'PASS', '250.5>=50'),
      fabricGate(host, 'tools', 'PASS', 'all'),
      fabricGate(host, 'cpu', 'PASS', seat ? '24' : '12'),
    ],
    candidate_excluded: candidateExcluded,
    identity_shadowed: false,
    telemetry_source: {
      status: 'VALID',
      source: '/private/owner/path-that-must-never-project',
      observed_at: '2026-10-04T02:15:00Z',
    },
  };
}

function fabricView(mode, rows) {
  return {
    schema: 'placement-view.private-candidate.v1',
    generated_at: '2026-10-04T02:15:00Z',
    mode,
    host_eligibility: {
      status: 'ELIGIBLE',
      selected_by_existing_host_pick: rows[0]?.host ?? null,
      max_age: 600,
      hosts: rows,
    },
  };
}

async function fabricFixture(owner) {
  const dir = await mkdtemp(join(tmpdir(), 'studio-fleet-physical-'));
  const launcher = join(dir, 'studio-direct');
  await writeFile(launcher, `#!/bin/sh\nprintf '%s\\n' '${JSON.stringify(owner)}'\n`);
  await chmod(launcher, 0o700);

  const fabric = join(dir, 'pool');
  const cases = ['go-codex', 'glm', 'minimax', 'grok', 'cursor', 'oc-free']
    .map((mode) => {
      const view = fabricView(mode, [
        fabricRow('m2', mode, {roles:['seat'], seat:true, eligible:mode === 'grok'}),
        fabricRow('mini1', mode, {roles:['lanes'], eligible:mode === 'go-codex'}),
        fabricRow('bm1', mode, {roles:['lanes-shadow'], eligible:false, candidateExcluded:true}),
      ]);
      return `${mode}) printf '%s\\n' '${JSON.stringify(view)}' ;;\n`;
    })
    .join('');
  await writeFile(
    fabric,
    `#!/bin/sh\ncase "$3" in\n${cases}*) exit 9 ;;\nesac\n`,
  );
  await chmod(fabric, 0o700);

  const { readFile } = await import('node:fs/promises');
  const launcherHash = createHash('sha256').update(await readFile(launcher)).digest('hex');
  const fabricHash = createHash('sha256').update(await readFile(fabric)).digest('hex');
  return {
    dir,
    config: {
      enabled:true,
      launcherPath:launcher,
      launcherSha256:launcherHash,
      timeoutMs:5000,
      fabricLauncherPath:fabric,
      fabricLauncherSha256:fabricHash,
      fabricTimeoutMs:5000,
    },
  };
}

test('physical fleet projection is advisory, bounded, and hides owner internals', async t => {
  const owner = ownerFor([statusRow('chatgpt1', true)]);
  const fx = await fabricFixture(owner);
  t.after(() => rm(fx.dir, {recursive:true, force:true}));

  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.state, 'READY');
  assert.deepEqual(result.issues, []);
  assert.equal(result.physicalFleet.schema, 'mastermind.studio_fleet_hosts.v1');
  assert.equal(result.physicalFleet.scope, 'subagent-fabric-registered-hosts');
  assert.equal(result.physicalFleet.hostCount, 2);
  assert.deepEqual(
    result.physicalFleet.hosts.map((row) => row.hostRef),
    ['m2', 'mini1'],
  );

  const m2 = result.physicalFleet.hosts.find((row) => row.hostRef === 'm2');
  assert.equal(m2.title, 'M2 Studio — Lead Computer');
  assert.equal(m2.seat, true);
  assert.equal(m2.online, true);
  assert.equal(m2.environment.logicalCpuCount, 24);
  assert.equal(m2.environment.diskFreeGb, 250.5);
  assert.equal(m2.environment.load1, 2.5);
  assert.equal(m2.environment.activeLanes, 0);
  assert.equal(m2.environment.laneCeiling, 2);
  assert.equal(m2.modes.grok.eligible, true);
  assert.equal(m2.modes['go-codex'].eligible, false);
  assert.equal(m2.advisoryOnly, true);
  assert.equal(m2.placementAuthority, false);
  assert.equal(m2.executionAuthority, false);
  assert.equal(m2.physicalIdentityProven, false);

  const rendered = JSON.stringify(fleetStatusToolResult(result));
  for (const forbidden of [
    '/private/owner/path-that-must-never-project',
    'ssh_alias',
    'telemetry_source',
  ]) {
    assert.equal(rendered.includes(forbidden), false, `leaked fabric owner field: ${forbidden}`);
  }
});

test('fabric launcher drift degrades only the physical projection', async t => {
  const owner = ownerFor([statusRow('chatgpt1', true)]);
  const fx = await fabricFixture(owner);
  t.after(() => rm(fx.dir, {recursive:true, force:true}));

  const config = {...fx.config};
  await writeFile(config.fabricLauncherPath, '#!/bin/sh\nexit 99\n');
  const result = await createFleetStatus(config).status();
  assert.equal(result.state, 'DEGRADED');
  assert.equal(result.physicalFleet, null);
  assert.deepEqual(result.issues, ['FLEET_STATUS_FABRIC_LAUNCHER_DRIFT']);
  assert.equal(result.accountCount, 1);
  assert.equal(result.accounts[0].ready, true);
});

test('fabric config is all-or-nothing and fail closed', () => {
  const base = {
    enabled:true,
    launcherPath:'/tmp/studio-direct',
    launcherSha256:'0'.repeat(64),
    timeoutMs:5000,
  };
  assert.throws(
    () => resolveFleetStatusConfig({...base, fabricLauncherPath:'/tmp/pool'}),
    /fabricLauncherSha256/,
  );
  assert.throws(
    () => resolveFleetStatusConfig({
      ...base,
      fabricLauncherPath:'/tmp/pool',
      fabricLauncherSha256:'0'.repeat(64),
      fabricTimeoutMs:500,
    }),
    /fabricTimeoutMs/,
  );
});
