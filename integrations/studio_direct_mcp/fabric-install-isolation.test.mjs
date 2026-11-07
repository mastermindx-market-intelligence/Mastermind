import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveConfig} from './gateway.mjs';
import {resolvePrivateTunnelConfig} from './private-tunnel-gateway.mjs';

const fleet = Object.freeze({
  enabled: true,
  launcherPath: '/usr/local/bin/studio-direct',
  launcherSha256: 'a'.repeat(64),
  timeoutMs: 15000,
});

test('Fabric-only normal configuration has no unrelated gateway capabilities', () => {
  const cfg = resolveConfig({fabricOnly:true, gitPublish:false, paperDesign:false});
  for (const name of ['fleetStatus','gitPublish','paperDesign','repositoryWorkspaces']) {
    assert.ok(!cfg[name], name);
  }
  assert.ok(!cfg.commissionPublication);
});

test('Fabric-only gateway refuses installed fleet telemetry even when it is valid', () => {
  assert.throws(() => resolveConfig({
    fabricOnly:true, gitPublish:false, paperDesign:false, fleetStatus:fleet,
  }), /Fabric-only gateway refuses unrelated host capabilities/);
  const {config} = resolvePrivateTunnelConfig({
    accountLabel:'fabric-qa', port:45280, fabricOnly:true,
    gitPublish:false, paperDesign:false, fleetStatus:fleet,
  });
  assert.throws(() => resolveConfig(config), /Fabric-only gateway refuses unrelated host capabilities/);
});

test('Fabric-only flag cannot be supplied as a truthy string', () => {
  for (const mode of ['true', 1, null, {}, []]) {
    assert.throws(() => resolveConfig({fabricOnly:mode}), /config.fabricOnly must be boolean/);
  }
});

test('existing non-Fabric gateway may still configure the reviewed fleet tool', () => {
  const cfg = resolveConfig({fleetStatus:fleet});
  assert.equal(cfg.fleetStatus.launcherPath, fleet.launcherPath);
});
