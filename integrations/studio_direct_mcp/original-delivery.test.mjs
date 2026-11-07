// Real private HTTP exchanges and owned, inert Python children; no Fabric work.
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, writeFile, realpath, rm, access } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import { Client as LegacyClient } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport as LegacyTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { PROTOCOL_VERSION_META_KEY, CLIENT_INFO_META_KEY, CLIENT_CAPABILITIES_META_KEY } from '@modelcontextprotocol/server';
import { startGateway, resolveConfig } from './gateway.mjs';
import { startPrivateGateway } from './private-tunnel-gateway.mjs';
import { originalCollectionConfig, createOriginalDelivery, ORIGINAL_ACCOUNT,
  ORIGINAL_PRINCIPAL, ORIGINAL_ROOT, ORIGINAL_RUNS, ORIGINAL_TOOL_NAMES } from './original-delivery.mjs';

const hash = raw => createHash('sha256').update(raw).digest('hex');
const receipt = 'a'.repeat(64);
const resultOf = result => JSON.parse(result.content.find(item => item.type === 'text').text);
const canonical = value => JSON.stringify(value, Object.keys(value).sort());
// The sealed predecessor body is the documented flat canonical form. The test
// rebuilds it independently so the module's own seal is checked, not reused.
function predecessorBody(document) {
  const pairs = [['schema', document.schema], ['receipt_sha256', document.receipt_sha256]];
  for (const key of Object.keys(document.prior).sort()) pairs.push([`prior.${key}`, String(document.prior[key])]);
  for (const run of Object.keys(document.runs).sort()) {
    const entry = document.runs[run];
    pairs.push([`runs.${run}.destination`, entry.destination]);
    pairs.push([`runs.${run}.observation`, entry.observation]);
  }
  pairs.sort((left, right) => (left[0] < right[0] ? -1 : left[0] > right[0] ? 1 : 0));
  return pairs.map(([key, value]) => `${key}=${value}`).join('\n');
}
const absentObservation = run => ({
  acceptance: 'NOT_RECORDED', controller_state: 'UNKNOWN', destination_reserved: false,
  effect_state: 'UNKNOWN', lease_settlement: 'UNKNOWN', original_operation_mutated: false,
  reason: 'destination_absence_is_not_execution_absence', retry_authorized: false,
  run_id: run, state: 'ABSENT',
});
function sealedPredecessor(observations, receiptSha256 = 'b'.repeat(64)) {
  const document = {
    schema: 'mastermind.fabric_original_predecessor.v1',
    receipt_sha256: receiptSha256,
    prior: { account: ORIGINAL_ACCOUNT, principal: ORIGINAL_PRINCIPAL,
      root: ORIGINAL_ROOT, parent: ORIGINAL_ROOT, host: 'ubuntu1',
      controlSha256: '1'.repeat(64), nativeGeneration: '2'.repeat(64),
      configHash: '3'.repeat(64), bundleDigest: '4'.repeat(64) },
    runs: Object.fromEntries(ORIGINAL_RUNS.map(run => [run, {
      destination: `/Volumes/Mastermind/evidence/${ORIGINAL_ROOT}/original-collections/${run}-collection-v1`,
      observation: observations[run] ? canonical(observations[run]) : null }])),
  };
  document.seal = hash(Buffer.from(predecessorBody(document), 'utf8'));
  return document;
}
const metadata = { [PROTOCOL_VERSION_META_KEY]: '2026-07-28',
  [CLIENT_INFO_META_KEY]: { name: 'inert-original-proof', version: '0.0.0' },
  [CLIENT_CAPABILITIES_META_KEY]: {} };
const body = (name, args, id = 1) => ({ jsonrpc: '2.0', id, method: 'tools/call',
  params: { name, arguments: args, _meta: metadata } });
const helper = String.raw`
import base64,hashlib,json,sys,time
from pathlib import Path
assert sys.argv[1:]==['_original-collection-helper']
root=Path(__file__).parent
value=json.load(sys.stdin)
with (root/'calls.jsonl').open('a') as out:
 out.write(json.dumps({'operation':value['operation'],'run_id':value['run_id']})+'\n')
mode=json.loads((root/'mode.json').read_text())
if mode.get('wait'):
 (root/'entered').write_text('ready')
 deadline=time.monotonic()+10
 while not (root/'release').exists():
  if time.monotonic()>deadline: raise SystemExit(91)
  time.sleep(.01)
kind=mode.get('kind')
if kind=='malformed': print('{broken');raise SystemExit(0)
if kind in ('refused','wrong-run','extra-field','unknown','unrelated-exit'):
 result={'run_id':value['run_id'],'state':'REFUSED','effect_state':'NOT_APPLIED',
  'reason':'original_collection_unconfirmed','retry_authorized':False}
 if kind=='wrong-run': result['run_id']='not-the-request'
 if kind=='extra-field': result['caller_approved']=True
 if kind=='unknown': result.update(state='UNKNOWN',effect_state='EFFECT_UNKNOWN')
 print(json.dumps(result));raise SystemExit(1 if kind=='unrelated-exit' else 75)
result={'run_id':value['run_id'],'state':'COMPLETE','receipt_sha256':'a'*64,
 'acceptance':'NOT_RECORDED','lease_settlement':'UNKNOWN','retry_authorized':False}
if value['operation']=='result':
 raw=bytes.fromhex(mode['hex']) if 'hex' in mode else mode.get('text','inert original result').encode()
 result.update(stdout_base64=base64.b64encode(raw).decode(),stdout_bytes=len(raw),
  stdout_sha256=hashlib.sha256(raw).hexdigest())
 result.update(mode.get('override',{}))
print(json.dumps(result))
`;

async function fixture(t) {
  const home = await mkdtemp(path.join(os.tmpdir(), 'mmx-original-http-'));
  t.after(() => rm(home, { recursive: true, force: true }));
  const control = path.join(home, '.local/share/studio-direct-mcp/control/private_service.py');
  await mkdir(path.dirname(control), { recursive: true, mode: 0o700 });
  await writeFile(control, helper, { mode: 0o600 });
  const python = await realpath(execFileSync('python3', ['-I', '-S', '-B', '-c',
    'import sys;print(sys.executable)'], { encoding: 'utf8' }).trim());
  const configuration = { enabled: true, schema: 'mastermind.fabric_original_collection.v2',
    pythonPath: python, pythonSha256: hash(await readFile(python)),
    controlPath: control, controlSha256: hash(await readFile(control)),
    controlBundleDigest: 'b'.repeat(64), nativeGeneration: 'c'.repeat(64),
    nativeStore: path.join(home, '.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/' +
      'handoff_kits/meta-ceo-b-2026-09-08/native-code-releases'),
    predecessor: sealedPredecessor({ [ORIGINAL_RUNS[0]]: absentObservation(ORIGINAL_RUNS[0]) }) };
  const profile = { host: '127.0.0.1', port: 45280, cwd: home, accountLabel: ORIGINAL_ACCOUNT,
    modernFabricProtocol: true, fabricOnly: true, backendMode: 'shared-account',
    gitPublish: false, paperDesign: false, originalCollection: configuration,
    command: process.execPath,
    args: [fileURLToPath(new URL('./fixtures/modern-fabric-backend.mjs', import.meta.url))],
    requestTimeoutMs: 5000 };
  const dir = path.dirname(control);
  const mode = value => writeFile(path.join(dir, 'mode.json'), JSON.stringify(value));
  await mode({});
  const calls = async () => {
    try { return (await readFile(path.join(dir, 'calls.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse); }
    catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  };
  const awaitEntered = async () => {
    for (let n = 0; n < 500; n++) {
      try { await access(path.join(dir, 'entered')); return; } catch { await delay(10); }
    }
    assert.fail('inert helper never reached the owned barrier');
  };
  const release = () => writeFile(path.join(dir, 'release'), 'release');
  return { home, configuration, profile, dir, mode, calls, awaitEntered, release };
}

function ephemeralC3(t) {
  // Keep the exact production tuple; redirect only this test process's bind.
  const listen = net.Server.prototype.listen;
  const patched = mock.method(net.Server.prototype, 'listen', function (...args) {
    if (args[0] === 45280) args[0] = 0;
    else if (args[0] && typeof args[0] === 'object' && args[0].port === 45280) args[0] = { ...args[0], port: 0 };
    return listen.apply(this, args);
  });
  t.after(() => patched.mock.restore());
}
async function modern(gw) {
  const client = new Client({ name: 'original-http-proof', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: '2026-07-28' }, probe: { timeoutMs: 3000, maxRetries: 0 } } });
  await client.connect(new StreamableHTTPClientTransport(new URL(gw.url)));
  return client;
}
async function raw(gw, message, options = {}) {
  return fetch(gw.url, { method: 'POST', headers: { 'content-type': 'application/json',
    accept: 'application/json, text/event-stream', 'mcp-protocol-version': '2026-07-28',
    'mcp-method': message.method, 'mcp-name': message.params.name },
    body: JSON.stringify(message), ...options });
}

test('original collection is absent by default and strictly bound to the enrolled C3 profile', async t => {
  const f = await fixture(t);
  assert.equal(resolveConfig({}).originalCollection, null);
  assert.deepEqual(originalCollectionConfig(f.profile), f.configuration);
  for (const delta of [{ accountLabel: 'another-seat' }, { port: 0 }, { host: 'localhost' },
    { testMode: true }, { modernFabricProtocol: false }, { fabricOnly: false },
    { backendMode: 'per-session' }, { gitPublish: true }, { repositoryWorkspaces: {} },
    { originalCollection: { ...f.configuration, caller_approved: true } },
    { originalCollection: { ...f.configuration, controlPath: '/foreign/control.py' } }]) {
    assert.throws(() => originalCollectionConfig({ ...f.profile, ...delta }), /exact enrolled private C3/);
  }
  assert.throws(() => createOriginalDelivery(f.configuration, 'p:tunnel:other'), /principal refused/);
  await assert.rejects(startGateway(f.profile, { accountLabel: 'another-seat', principal: 'tunnel:another-seat' }),
    /original collection|Original collection/);
  assert.deepEqual(await f.calls(), []);
});

test('reserved names cannot be forwarded or advertised while disabled', async t => {
  const f = await fixture(t); ephemeralC3(t);
  for (const collision of [false, true]) {
    const profile = { ...f.profile, originalCollection: undefined,
      childEnv: { FIXTURE_ORIGINAL_COLLISION: String(collision) } };
    const gw = await startPrivateGateway(profile); let client;
    try {
      client = await modern(gw);
      if (collision) await assert.rejects(client.listTools(), /reserved original collection/);
      else assert.equal((await client.listTools()).tools.some(tool => ORIGINAL_TOOL_NAMES.has(tool.name)), false);
      await assert.rejects(client.callTool({ name: 'fabric_collect_original', arguments: { run_id: ORIGINAL_RUNS[0] } }),
        /Fabric-only boundary|not enabled/);
      assert.deepEqual(await f.calls(), []);
    } finally { await client?.close(); await gw.close(); }
  }
});

test('modern and legacy HTTP clients use the same authenticated owner and closed run selectors', async t => {
  const f = await fixture(t); ephemeralC3(t);
  const gw = await startPrivateGateway(f.profile); let client, legacy;
  try {
    client = await modern(gw);
    assert.deepEqual((await client.listTools()).tools.filter(tool => ORIGINAL_TOOL_NAMES.has(tool.name))
      .map(tool => tool.name).sort(), [...ORIGINAL_TOOL_NAMES].sort());
    for (const argumentsValue of [{ run_id: 'another-run' }, { run_id: ORIGINAL_RUNS[0], root: 'forged-root' },
      { run_id: ORIGINAL_RUNS[0], pythonPath: '/foreign/python' }]) {
      await assert.rejects(client.callTool({ name: 'fabric_collect_original', arguments: argumentsValue }));
    }
    assert.deepEqual(await f.calls(), []);
    const first = resultOf(await client.callTool({ name: 'fabric_collect_original', arguments: { run_id: ORIGINAL_RUNS[0] } }));
    assert.equal(first.state, 'ABSENT');
    legacy = new LegacyClient({ name: 'original-legacy-proof', version: '0.0.0' });
    await legacy.connect(new LegacyTransport(new URL(gw.url)));
    assert.equal(resultOf(await legacy.callTool({ name: 'fabric_collect_original', arguments: { run_id: ORIGINAL_RUNS[0] } })).state, 'ABSENT');
    assert.equal((await f.calls()).length, 0);
    assert.equal(gw.stats().backend.spawns, 1);
    const second = resultOf(await legacy.callTool({ name: 'fabric_collect_original', arguments: { run_id: ORIGINAL_RUNS[1] } }));
    assert.equal(second.state, 'UNKNOWN');
    assert.equal((await f.calls()).length, 0);
    const args = { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 };
    assert.equal(resultOf(await client.callTool({ name: 'fabric_original_collection_reconcile', arguments: args })).state, 'COMPLETE');
    assert.equal(resultOf(await legacy.callTool({ name: 'fabric_original_collection_reconcile', arguments: args })).state, 'COMPLETE');
    assert.equal((await f.calls()).length, 1);
  } finally { await client?.close(); await legacy?.close(); await gw.close(); }
});

test('concurrent HTTP exchanges and client disconnect retain exactly one owned helper', async t => {
  const f = await fixture(t); ephemeralC3(t); await f.mode({ wait: true });
  const gw = await startPrivateGateway(f.profile); let client;
  const aborted = new AbortController();
  try {
    client = await modern(gw); await client.listTools();
    const generation = gw.stats().backend.owners[0].generation;
    const first = raw(gw, body('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, 101),
      { signal: aborted.signal }).then(async response => ({ response: await response.text() }), error => ({ error }));
    await f.awaitEntered();
    const second = raw(gw, body('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, 102));
    aborted.abort(); await first;
    await f.release();
    const response = await second;
    const answer = await response.json();
    assert.equal(resultOf(answer.result).state, 'COMPLETE');
    assert.equal((await f.calls()).length, 1);
    assert.equal(gw.stats().backend.owners[0].generation, generation);
    assert.equal(resultOf(await client.callTool({ name: 'fabric_original_collection_reconcile', arguments: { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 } })).state, 'COMPLETE');
    assert.equal((await f.calls()).length, 1);
  } finally { aborted.abort(); await f.release(); await client?.close(); await gw.close(); }
});

test('owner close waits for its helper without cancelling the original observation', async t => {
  const f = await fixture(t); await f.mode({ wait: true });
  const owner = createOriginalDelivery(f.configuration, ORIGINAL_PRINCIPAL);
  const call = owner.call('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, ORIGINAL_PRINCIPAL);
  await f.awaitEntered();
  let closed = false; const closing = owner.close().then(() => { closed = true; });
  await delay(20); assert.equal(closed, false);
  await f.release(); assert.equal(resultOf(await call).state, 'COMPLETE'); await closing;
  await assert.rejects(owner.call('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, ORIGINAL_PRINCIPAL));
  assert.equal((await f.calls()).length, 1);
});

test('preflight corruption refuses without a child and cannot be retried by the same owner', async t => {
  const f = await fixture(t);
  const owner = createOriginalDelivery({ ...f.configuration, controlSha256: '0'.repeat(64) }, ORIGINAL_PRINCIPAL);
  try {
    for (let n = 0; n < 2; n++) {
      const value = resultOf(await owner.call('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, ORIGINAL_PRINCIPAL));
      assert.equal(value.state, 'REFUSED'); assert.equal(value.effect_state, 'NOT_APPLIED');
    }
    assert.deepEqual(await f.calls(), []);
  } finally { await owner.close(); }
});

test('only a strict correlated rc75 envelope preserves a refusal; uncertain outcomes stay retained', async t => {
  for (const kind of ['refused', 'wrong-run', 'extra-field', 'unknown', 'unrelated-exit', 'malformed']) {
    await t.test(kind, async t => {
      const f = await fixture(t); await f.mode({ kind });
      const owner = createOriginalDelivery(f.configuration, ORIGINAL_PRINCIPAL);
      try {
        const value = resultOf(await owner.call('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, ORIGINAL_PRINCIPAL));
        assert.equal(value.state, kind === 'refused' ? 'REFUSED' : 'UNKNOWN');
        assert.equal(value.retry_authorized, false);
        await owner.call('fabric_original_collection_reconcile', { run_id: ORIGINAL_RUNS[0], predecessor_sha256: f.configuration.predecessor.receipt_sha256 }, ORIGINAL_PRINCIPAL);
        assert.equal((await f.calls()).length, 1);
      } finally { await owner.close(); }
    });
  }
});

test('result bytes require the receipt, exact length, digest, canonical encoding and strict UTF8', async t => {
  const f = await fixture(t);
  const owner = createOriginalDelivery(f.configuration, ORIGINAL_PRINCIPAL);
  try {
    for (const mode of [{ override: { receipt_sha256: 'd'.repeat(64) } },
      { override: { stdout_bytes: 1 } }, { override: { stdout_sha256: '0'.repeat(64) } },
      { override: { stdout_base64: 'aW5lcnQ=\n' } }, { hex: 'ff' }]) {
      await f.mode(mode);
      assert.equal((await owner.call('fabric_original_collection_result',
        { run_id: ORIGINAL_RUNS[0], receipt_sha256: receipt }, ORIGINAL_PRINCIPAL)).isError, true);
    }
    await f.mode({ text: 'exact inert result' });
    assert.equal((await owner.call('fabric_original_collection_result',
      { run_id: ORIGINAL_RUNS[0], receipt_sha256: receipt }, ORIGINAL_PRINCIPAL)).content[0].text, 'exact inert result');
  } finally { await owner.close(); }
});

test('the sealed predecessor import replays the original collect without any helper', async t => {
  const f = await fixture(t);
  const predecessor = sealedPredecessor({ [ORIGINAL_RUNS[0]]: absentObservation(ORIGINAL_RUNS[0]) });
  const owner = createOriginalDelivery({ ...f.configuration, predecessor }, ORIGINAL_PRINCIPAL);
  try {
    const replayed = resultOf(await owner.call('fabric_collect_original',
      { run_id: ORIGINAL_RUNS[0] }, ORIGINAL_PRINCIPAL));
    assert.equal(replayed.state, 'ABSENT');
    assert.equal(replayed.destination_reserved, false);
    assert.equal(replayed.effect_state, 'UNKNOWN');
    assert.equal(replayed.acceptance, 'NOT_RECORDED');
    assert.equal(replayed.original_operation_mutated, false);
    assert.equal(replayed.retry_authorized, false);
    assert.equal(replayed.lease_settlement, 'UNKNOWN');
    assert.equal(replayed.controller_state, 'UNKNOWN');
    assert.equal(replayed.reason, 'destination_absence_is_not_execution_absence');
    // The retained response is returned unchanged and no helper is spawned.
    assert.deepEqual(await f.calls(), []);
    assert.deepEqual(resultOf(await owner.call('fabric_collect_original',
      { run_id: ORIGINAL_RUNS[0] }, ORIGINAL_PRINCIPAL)), replayed);
    assert.deepEqual(await f.calls(), []);
  } finally { await owner.close(); }
});

test('an invalid or conflicting predecessor import refuses every call without a helper', async t => {
  const f = await fixture(t);
  const sealed = sealedPredecessor({ [ORIGINAL_RUNS[0]]: absentObservation(ORIGINAL_RUNS[0]) });
  const tampered = structuredClone(sealed); tampered.seal = '0'.repeat(64);
  const forged = structuredClone(sealed);
  forged.runs[ORIGINAL_RUNS[0]].observation = canonical({ state: 'ABSENT' });
  const foreign = structuredClone(sealed);
  foreign.prior.account = 'another-seat';
  for (const document of [tampered, forged, foreign]) {
    const owner = createOriginalDelivery({ ...f.configuration, predecessor: document }, ORIGINAL_PRINCIPAL);
    try {
      const value = resultOf(await owner.call('fabric_collect_original',
        { run_id: ORIGINAL_RUNS[0] }, ORIGINAL_PRINCIPAL));
      assert.equal(value.state, 'REFUSED');
      assert.equal(value.effect_state, 'NOT_APPLIED');
      assert.equal(value.reason, 'original_predecessor_import_invalid');
      const reconciled = resultOf(await owner.call('fabric_original_collection_reconcile',
        { run_id: ORIGINAL_RUNS[0], predecessor_sha256: sealed.receipt_sha256 }, ORIGINAL_PRINCIPAL));
      assert.equal(reconciled.state, 'REFUSED');
      assert.deepEqual(await f.calls(), []);
    } finally { await owner.close(); }
  }
});

test('the reconciliation selection keeps one subordinate attempt bound to the predecessor', async t => {
  const f = await fixture(t); await f.mode({ wait: true });
  const sealed = sealedPredecessor({ [ORIGINAL_RUNS[0]]: absentObservation(ORIGINAL_RUNS[0]) });
  const owner = createOriginalDelivery({ ...f.configuration, predecessor: sealed }, ORIGINAL_PRINCIPAL);
  try {
    // A changed argument never creates another attempt.
    await assert.rejects(owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[0], predecessor_sha256: 'c'.repeat(64) }, ORIGINAL_PRINCIPAL));
    await assert.rejects(owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[1], predecessor_sha256: sealed.receipt_sha256 }, ORIGINAL_PRINCIPAL));
    await assert.rejects(owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[0] }, ORIGINAL_PRINCIPAL));
    assert.deepEqual(await f.calls(), []);
    const first = owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[0], predecessor_sha256: sealed.receipt_sha256 }, ORIGINAL_PRINCIPAL);
    await f.awaitEntered();
    const second = owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[0], predecessor_sha256: sealed.receipt_sha256 }, ORIGINAL_PRINCIPAL);
    await f.release();
    assert.equal(resultOf(await first).state, 'COMPLETE');
    assert.equal(resultOf(await second).state, 'COMPLETE');
    const calls = await f.calls();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].operation, 'reconcile');
    assert.equal(calls[0].run_id, ORIGINAL_RUNS[0]);
    // A later call reuses the same retained attempt.
    assert.equal(resultOf(await owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[0], predecessor_sha256: sealed.receipt_sha256 }, ORIGINAL_PRINCIPAL)).state, 'COMPLETE');
    assert.equal((await f.calls()).length, 1);
    // The ordinary collect still replays the imported predecessor unchanged.
    assert.equal(resultOf(await owner.call('fabric_collect_original',
      { run_id: ORIGINAL_RUNS[0] }, ORIGINAL_PRINCIPAL)).state, 'ABSENT');
    assert.equal((await f.calls()).length, 1);
  } finally { await f.release(); await owner.close(); }
});

test('a completed or held predecessor slot is never reconciled again', async t => {
  const f = await fixture(t);
  const complete = { acceptance: 'NOT_RECORDED', controller_state: 'UNKNOWN',
    delivery_verified: true, destination_reserved: true, lease_settlement: 'UNKNOWN',
    original_operation_mutated: false, receipt_sha256: 'd'.repeat(64), retry_authorized: false,
    run_id: ORIGINAL_RUNS[1], state: 'COMPLETE' };
  const sealed = sealedPredecessor({ [ORIGINAL_RUNS[1]]: complete });
  const owner = createOriginalDelivery({ ...f.configuration, predecessor: sealed }, ORIGINAL_PRINCIPAL);
  try {
    assert.equal(resultOf(await owner.call('fabric_collect_original',
      { run_id: ORIGINAL_RUNS[1] }, ORIGINAL_PRINCIPAL)).state, 'COMPLETE');
    await assert.rejects(owner.call('fabric_original_collection_reconcile',
      { run_id: ORIGINAL_RUNS[1], predecessor_sha256: sealed.receipt_sha256 }, ORIGINAL_PRINCIPAL));
    assert.deepEqual(await f.calls(), []);
  } finally { await owner.close(); }
});

test('the predecessor descriptor is closed so an interrupted transition never starts a clean owner', async t => {
  const f = await fixture(t);
  // The v1 descriptor predates the predecessor binding. A stopped-service
  // transition that installs the new source before the new configuration must
  // refuse rather than construct an empty owner over a preserved predecessor.
  const legacy = { ...f.configuration };
  delete legacy.predecessor;
  legacy.schema = 'mastermind.fabric_original_collection.v1';
  assert.throws(() => originalCollectionConfig({ ...f.profile, originalCollection: legacy }),
    /exact enrolled private C3/);
  // The current descriptor without its predecessor field is refused as well.
  const unsealed = { ...f.configuration };
  delete unsealed.predecessor;
  assert.throws(() => originalCollectionConfig({ ...f.profile, originalCollection: unsealed }),
    /exact enrolled private C3/);
  assert.deepEqual(await f.calls(), []);
});

test('null and explicitly held predecessor slots never create a fresh collection', async t => {
  const f = await fixture(t);
  for (const predecessor of [null, sealedPredecessor({})]) {
    const owner = createOriginalDelivery({ ...f.configuration, predecessor }, ORIGINAL_PRINCIPAL);
    try {
      for (const run of ORIGINAL_RUNS) {
        const value = resultOf(await owner.call('fabric_collect_original', { run_id: run }, ORIGINAL_PRINCIPAL));
        assert.equal(value.state, 'UNKNOWN');
        assert.equal(value.reason, 'original_predecessor_slot_held');
        await assert.rejects(owner.call('fabric_original_collection_reconcile',
          { run_id: run, predecessor_sha256: 'b'.repeat(64) }, ORIGINAL_PRINCIPAL));
      }
    } finally { await owner.close(); }
  }
  assert.deepEqual(await f.calls(), []);
});

test('a resealed missing slot and duplicate observation fields are refused', async t => {
  const f = await fixture(t);
  const missing = sealedPredecessor({ [ORIGINAL_RUNS[0]]: absentObservation(ORIGINAL_RUNS[0]) });
  delete missing.runs[ORIGINAL_RUNS[1]];
  missing.seal = hash(Buffer.from(predecessorBody(missing)));
  const duplicate = sealedPredecessor({ [ORIGINAL_RUNS[0]]: absentObservation(ORIGINAL_RUNS[0]) });
  duplicate.runs[ORIGINAL_RUNS[0]].observation = duplicate.runs[ORIGINAL_RUNS[0]].observation.slice(0, -1) + ',"state":"ABSENT"}';
  duplicate.seal = hash(Buffer.from(predecessorBody(duplicate)));
  for (const predecessor of [missing, duplicate]) {
    const owner = createOriginalDelivery({ ...f.configuration, predecessor }, ORIGINAL_PRINCIPAL);
    try {
      const value = resultOf(await owner.call('fabric_collect_original', { run_id: ORIGINAL_RUNS[0] }, ORIGINAL_PRINCIPAL));
      assert.equal(value.state, 'REFUSED');
      assert.equal(value.reason, 'original_predecessor_import_invalid');
    } finally { await owner.close(); }
  }
  assert.deepEqual(await f.calls(), []);
});

test('large original results use the incumbent retained pager without invoking the helper again', async t => {
  const f = await fixture(t); ephemeralC3(t);
  const expected = 'inert-original-result-'.repeat(6000); await f.mode({ text: expected });
  const gw = await startPrivateGateway(f.profile); let client;
  try {
    client = await modern(gw); await client.listTools();
    const paged = resultOf(await client.callTool({ name: 'fabric_original_collection_result',
      arguments: { run_id: ORIGINAL_RUNS[0], receipt_sha256: receipt } }));
    assert.equal(paged.status, 'OUTPUT_PAGED');
    const parts = []; let offset = 0;
    for (let n = 0; n < 200; n++) {
      const page = resultOf(await client.callTool({ name: 'studio_output_page', arguments: { receipt_id: paged.receipt_id, offset } }));
      parts.push(page.text); if (page.done) break;
      assert.ok(page.next_offset > offset); offset = page.next_offset;
    }
    const retained = parts.join('');
    assert.equal(Buffer.byteLength(retained), paged.source_bytes);
    assert.equal(hash(retained), paged.sha256);
    assert.equal(JSON.parse(retained).content[0].text, expected);
    assert.equal((await f.calls()).length, 1);
  } finally { await client?.close(); await gw.close(); }
});
