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

test('status returns the existing owner projection without mutation', async t => {
  const owner = {
    schema:'mastermind.studio_direct_fleet_status.v1',
    action:'status',
    accountCount:1,
    readyCount:1,
    allReady:true,
    accounts:[],
  };
  const fx = await fixture(JSON.stringify(owner));
  t.after(() => rm(fx.dir, {recursive:true, force:true}));
  const result = await createFleetStatus(fx.config).status();
  assert.equal(result.schema, 'mastermind.studio_fleet_status_tool.v1');
  assert.equal(result.state, 'READY');
  assert.deepEqual(result.owner, owner);
});
test('launcher drift refuses before owner execution', async t => {
  const owner = {
    schema:'mastermind.studio_direct_fleet_status.v1',
    action:'status',
    accountCount:0,
    readyCount:0,
    allReady:false,
    accounts:[],
  };
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
