// Run after npm ci in this package. This uses the actual pinned SDK harness,
// an empty fake database and inert local paths; no live agent or T3 call occurs.
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setImmediate as turn } from 'node:timers/promises';
import { createTestHarness } from '@paperclipai/plugin-sdk/testing';
import manifest from '../manifest.mjs';
import plugin from '../worker.mjs';
import { Realtime } from '../realtime.mjs';

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const harness = createTestHarness({ manifest });
harness.ctx.db.namespace = 'plugin_mastermind_teamlink_ddd6e53475';
const definition = plugin.definition;
const directory = await mkdtemp(join(tmpdir(), 'teamlink-sdk-test-'));
const inert = join(directory, 'inert.mjs');
await writeFile(inert, 'throw new Error("NO_NATIVE_PROCESS_EXPECTED");\n');
let skillGate = null, skillEntered = null, issueGate = null, issueEntered = null, skillReconciles = 0, issueReads = 0;
harness.ctx.skills.managed.reconcile = async (_key, companyId) => {
  assert.equal(companyId, 'company'); skillReconciles++; skillEntered?.resolve();
  if (skillGate) await skillGate.promise;
  return { skill: { key: 'teamlink-skill', id: 'managed-skill' }, status: 'current' };
};
harness.ctx.issues.get = async (issueId, companyId) => {
  issueReads++; issueEntered?.resolve(); if (issueGate) await issueGate.promise;
  return { id: issueId, companyId, title: 'Test', status: 'in_progress', assigneeAgentId: 'agent' };
};
const config = { companyId: 'company', environmentId: 'environment', projectIds: ['project'],
  nativeCliPath: inert, nodePath: process.execPath, pythonPath: process.execPath,
  portPath: inert, t3Home: directory, t3Port: 3773, enabled: true };
const scope = { companyId: 'company' }, run = { ...scope, agentId: 'agent', runId: 'run' };
try {
  await definition.setup(harness.ctx);
  assert.equal((await definition.onHealth()).status, 'degraded');
  assert.equal((await definition.onValidateConfig(config)).ok, true);
  await definition.onConfigChanged(config, scope);
  let health = await definition.onHealth();
  assert.equal(health.status, 'ok'); assert.equal(health.details.realtime.coverageComplete, true);
  assert.equal(health.details.realtime.coveredBindings, 0);
  assert.equal(await definition.onIdleDrain(new AbortController().signal), 'present');
  await assert.rejects(definition.onConfigChanged({ ...config, companyId: 'other' }, scope), /COMPANY_SCOPE_MISMATCH/);

  // A slow managed-skill RPC fences both configuration and ordinary handler
  // admission; the second configuration cannot create another listener.
  skillGate = deferred(); skillEntered = deferred();
  const changed = definition.onConfigChanged({ ...config, realtime: false }, scope);
  await skillEntered.promise;
  health = await definition.onHealth();
  assert.equal(health.details.transitioning, true); assert.equal(health.status, 'degraded');
  let toolReturned = false;
  const waiting = harness.executeTool('teamlink_context', { issueId: 'issue' }, run).then(r => { toolReturned = true; return r; });
  await turn(); assert.equal(toolReturned, false); assert.equal(issueReads, 0);
  await assert.rejects(definition.onConfigChanged(config, scope), /TEAMLINK_OPERATION_IN_PROGRESS/);
  skillGate.resolve(); await changed;
  assert.ok((await waiting).data); assert.equal((await definition.onHealth()).details.realtime, null);
  skillGate = null; skillEntered = null;

  // Once admitted, a handler retains its generation and blocks replacement
  // until its in-flight issue read completes.
  issueGate = deferred(); issueEntered = deferred();
  const active = harness.executeTool('teamlink_context', { issueId: 'issue' }, run);
  await issueEntered.promise;
  await assert.rejects(definition.onConfigChanged(config, scope), /TEAMLINK_OPERATION_IN_PROGRESS/);
  issueGate.resolve(); assert.ok((await active).data); issueGate = null; issueEntered = null;
  await definition.onConfigChanged(config, scope);

  // Shutdown during preparation prevents publication of the new generation,
  // releases waiting handlers with a typed refusal, and drains the old owner.
  skillGate = deferred(); skillEntered = deferred();
  const preparing = definition.onConfigChanged({ ...config, realtime: false }, scope);
  const rejected = assert.rejects(preparing, /TEAMLINK_SHUTTING_DOWN/);
  await skillEntered.promise;
  const blocked = harness.executeTool('teamlink_context', { issueId: 'issue' }, run);
  let stopped = false;
  const stopping = definition.onShutdown().then(() => { stopped = true; });
  await turn(); assert.equal(stopped, false); assert.equal((await definition.onHealth()).status, 'degraded');
  skillGate.resolve(); await rejected; await stopping;
  assert.equal((await blocked).error, 'TEAMLINK_SHUTTING_DOWN');
  assert.equal(await definition.onIdleDrain(new AbortController().signal), 'none');
  assert.equal((await definition.onHealth()).details.realtime, null);
  await assert.rejects(definition.onConfigChanged(config, scope), /TEAMLINK_SHUTTING_DOWN/);
  assert.equal((await harness.executeTool('teamlink_context', { issueId: 'issue' }, run)).error, 'TEAMLINK_SHUTTING_DOWN');

  // A second real worker instance covers shutdown arriving after skill
  // reconciliation, while the old listener generation is still draining.
  const second = (await import('../worker.mjs?shutdown_during_drain')).default.definition;
  const secondHarness = createTestHarness({ manifest });
  secondHarness.ctx.db.namespace = harness.ctx.db.namespace;
  secondHarness.ctx.skills.managed.reconcile = async () => ({ skill: { key: 'teamlink-skill' }, status: 'current' });
  await second.setup(secondHarness.ctx); await second.onConfigChanged(config, scope);
  const stopEntered = deferred(), stopGate = deferred(), originalStop = Realtime.prototype.stop;
  Realtime.prototype.stop = async function () { stopEntered.resolve(); await stopGate.promise; return originalStop.call(this); };
  try {
    const changing = second.onConfigChanged({ ...config, environmentId: 'new-environment' }, scope);
    const refused = assert.rejects(changing, /TEAMLINK_SHUTTING_DOWN/);
    await stopEntered.promise; const shutdown = second.onShutdown(); stopGate.resolve();
    await refused; await shutdown;
    const after = await second.onHealth();
    assert.equal(after.details.environmentId, 'environment'); assert.equal(after.details.realtime, null);
  } finally { stopGate.resolve(); Realtime.prototype.stop = originalStop; await second.onShutdown(); }
  console.log(JSON.stringify({ sdkVersion: '2026.1106.0', lifecycle: 'pass', companyFence: 'pass',
    concurrentConfig: 'pass', admissionBarrier: 'pass', shutdownDuringTransition: 'pass', shutdownDuringDrain: 'pass',
    subscriptionInventory: 'empty_without_spawn', skillReconciles, issueReads,
    declaredTools: manifest.tools.length, declaredJobs: manifest.jobs.length }));
} finally {
  skillGate?.resolve(); issueGate?.resolve();
  await definition.onShutdown(); await rm(directory, { recursive: true, force: true });
}
