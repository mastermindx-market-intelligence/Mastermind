import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdir, mkdtemp, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {
  buildFleetContractStatus,
  canonicalDigest,
  contractDigests,
  discoverAccounts,
  groupContracts,
  publicFleetProjection,
  validateManifest,
} from './fleet-contract-status.mjs';

const toolA = {
  name: 'alpha',
  description: 'Alpha tool',
  inputSchema: {type: 'object', properties: {x: {type: 'string'}}},
  annotations: {readOnlyHint: true},
};
const toolB = {
  name: 'beta',
  description: 'Beta tool',
  inputSchema: {type: 'object', properties: {}},
};

test('canonical digest ignores object-key and tool ordering', () => {
  const left = contractDigests([toolB, toolA]);
  const right = contractDigests([
    {
      annotations: {readOnlyHint: true},
      inputSchema: {properties: {x: {type: 'string'}}, type: 'object'},
      description: 'Alpha tool',
      name: 'alpha',
    },
    {
      inputSchema: {properties: {}, type: 'object'},
      description: 'Beta tool',
      name: 'beta',
    },
  ]);
  assert.deepEqual(left, right);
});

test('metadata change preserves invocation digest but changes published digest', () => {
  const before = contractDigests([toolA]);
  const after = contractDigests([{...toolA, description: 'Changed description'}]);
  assert.equal(before.invocationDigest, after.invocationDigest);
  assert.notEqual(before.publishedDigest, after.publishedDigest);
});

test('input schema change changes both contract digests', () => {
  const before = contractDigests([toolA]);
  const after = contractDigests([
    {...toolA, inputSchema: {type: 'object', properties: {x: {type: 'number'}}}},
  ]);
  assert.notEqual(before.invocationDigest, after.invocationDigest);
  assert.notEqual(before.publishedDigest, after.publishedDigest);
});

test('contract groups are deterministic and preserve account membership', () => {
  const old = contractDigests([toolA]);
  const newer = contractDigests([toolA, toolB]);
  const rows = [
    {account: 'chatgpt4', toolCount: 2, toolNames: ['alpha','beta'], ...newer},
    {account: 'chatgpt2', toolCount: 1, toolNames: ['alpha'], ...old},
    {account: 'chatgpt3', toolCount: 2, toolNames: ['alpha','beta'], ...newer},
    {account: 'chatgpt1', toolCount: 1, toolNames: ['alpha'], ...old},
  ];
  const groups = groupContracts(rows);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups.map(group => group.accounts), [
    ['chatgpt1','chatgpt2'],
    ['chatgpt3','chatgpt4'],
  ]);
});

test('public projection contains no runtime paths or ports', () => {
  const digests = contractDigests([toolA]);
  const projected = publicFleetProjection([
    {
      account: 'chatgpt1',
      toolCount: 1,
      toolNames: ['alpha'],
      ...digests,
      privatePath: '/Users/example/private',
      port: 45018,
    },
  ]);
  const raw = JSON.stringify(projected);
  assert.equal(raw.includes('/Users/'), false);
  assert.equal(raw.includes('45018'), false);
  assert.equal(projected.schema, 'mastermind.studio_direct_contract_fleet.v1');
});

test('manifest validator accepts exact closed seat identity and port only', () => {
  assert.deepEqual(
    validateManifest({account: 'chatgpt1', port: 45018}, 'chatgpt1'),
    {account: 'chatgpt1', port: 45018},
  );
  assert.throws(
    () => validateManifest({account: 'chatgpt2', port: 45018}, 'chatgpt1'),
    /account mismatch/,
  );
  assert.throws(
    () => validateManifest({account: 'chatgpt1', port: '45018'}, 'chatgpt1'),
    /port/,
  );
});

test('canonicalDigest rejects non-json values rather than stringifying ambiguity', () => {
  assert.throws(() => canonicalDigest({bad: undefined}), /unsupported JSON value/);
});


test('installed account discovery does not hide a malformed manifest', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'studio-contract-discovery-'));
  try {
    await mkdir(path.join(root, 'chatgpt1'));
    await writeFile(path.join(root, 'chatgpt1', 'manifest.json'), '{malformed');
    assert.deepEqual(await discoverAccounts(root), ['chatgpt1']);
  } finally {
    await rm(root, {recursive: true, force: true});
  }
});

test('fleet build preserves probe failure as explicit non-green row', async () => {
  const good = {account: 'chatgpt1', ...contractDigests([toolA])};
  const output = await buildFleetContractStatus('/unused', {
    discover: async () => ['chatgpt1', 'chatgpt2'],
    probe: async account => {
      if (account === 'chatgpt2') throw new Error('/Users/private/secret-path');
      return good;
    },
  });
  assert.equal(output.accountCount, 2);
  assert.equal(output.observedContractCount, 1);
  assert.equal(output.allContractsObserved, false);
  assert.deepEqual(output.failures, [
    {account: 'chatgpt2', code: 'CONTRACT_PROBE_FAILED'},
  ]);
  assert.equal(JSON.stringify(output).includes('/Users/'), false);
});

test('public projection refuses duplicate identity across success and failure', () => {
  const row = {account: 'chatgpt1', ...contractDigests([toolA])};
  assert.throws(
    () => publicFleetProjection(
      [row],
      [{account: 'chatgpt1', code: 'CONTRACT_PROBE_FAILED'}],
    ),
    /duplicate account/,
  );
});
