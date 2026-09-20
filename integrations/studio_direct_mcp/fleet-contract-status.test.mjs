import assert from 'node:assert/strict';
import {test} from 'node:test';
import {
  canonicalDigest,
  contractDigests,
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
