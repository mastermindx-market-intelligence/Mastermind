import assert from 'node:assert/strict';
import {test} from 'node:test';
import {
  buildFleetReleaseStatus,
  classifyFleetRelease,
  publicReleaseProjection,
  releaseBuildIdentity,
} from './fleet-release-status.mjs';
import {contractDigests} from './fleet-contract-status.mjs';

const toolA = {
  name: 'alpha',
  description: 'Alpha',
  inputSchema: {type: 'object', properties: {}},
};
const toolAMetadata = {...toolA, description: 'Alpha changed'};
const toolB = {
  name: 'beta',
  inputSchema: {type: 'object', properties: {x: {type: 'string'}}},
};

function manifest(overrides = {}) {
  return {
    version: 2,
    account: 'chatgpt1',
    port: 45018,
    source: '/Users/example/source-a',
    configHash: '1'.repeat(64),
    plistHash: '2'.repeat(64),
    nodeHash: '3'.repeat(64),
    backendHash: '4'.repeat(64),
    dependencyTreeHash: '5'.repeat(64),
    files: {
      'gateway.mjs': '6'.repeat(64),
      'package.json': '7'.repeat(64),
    },
    ...overrides,
  };
}

function row(account, buildIdentity, tools) {
  return {account, buildIdentity, ...contractDigests(tools)};
}

test('release build identity ignores seat config and private source path', () => {
  const one = releaseBuildIdentity(manifest());
  const two = releaseBuildIdentity(manifest({
    account: 'chatgpt2',
    port: 45022,
    source: '/Users/other/private-source',
    configHash: '8'.repeat(64),
    plistHash: '9'.repeat(64),
  }));
  assert.equal(one, two);
  assert.equal(one.length, 64);
  assert.equal(one.includes('/Users/'), false);
});

test('release build identity changes for staged code or dependency bytes', () => {
  const before = releaseBuildIdentity(manifest());
  const fileChanged = releaseBuildIdentity(manifest({
    files: {'gateway.mjs': 'a'.repeat(64), 'package.json': '7'.repeat(64)},
  }));
  const dependencyChanged = releaseBuildIdentity(manifest({dependencyTreeHash: 'b'.repeat(64)}));
  assert.notEqual(before, fileChanged);
  assert.notEqual(before, dependencyChanged);
});

test('uniform fleet is current at the release-contract layer', () => {
  const build = releaseBuildIdentity(manifest());
  const projection = classifyFleetRelease([
    row('chatgpt1', build, [toolA]),
    row('chatgpt2', build, [toolA]),
  ]);
  assert.equal(projection.classification, 'UNIFORM_RELEASE_CONTRACT');
  assert.equal(projection.buildGroupCount, 1);
  assert.equal(projection.contractGroupCount, 1);
});

test('different builds with identical contract are contract-preserving drift only', () => {
  const projection = classifyFleetRelease([
    row('chatgpt1', '1'.repeat(64), [toolA]),
    row('chatgpt2', '2'.repeat(64), [toolA]),
  ]);
  assert.equal(projection.classification, 'CONTRACT_PRESERVING_BUILD_DRIFT');
  assert.equal(projection.buildGroupCount, 2);
  assert.equal(projection.contractGroupCount, 1);
  assert.equal(projection.invocationGroupCount, 1);
});

test('metadata-only contract drift is distinct from invocation change', () => {
  const projection = classifyFleetRelease([
    row('chatgpt1', '1'.repeat(64), [toolA]),
    row('chatgpt2', '2'.repeat(64), [toolAMetadata]),
  ]);
  assert.equal(projection.classification, 'PUBLISHED_METADATA_CONTRACT_DRIFT');
  assert.equal(projection.invocationGroupCount, 1);
  assert.equal(projection.contractGroupCount, 2);
});

test('tool or input drift is invocation contract migration', () => {
  const projection = classifyFleetRelease([
    row('chatgpt1', '1'.repeat(64), [toolA]),
    row('chatgpt2', '2'.repeat(64), [toolA, toolB]),
  ]);
  assert.equal(projection.classification, 'INVOCATION_CONTRACT_DRIFT');
  assert.equal(projection.invocationGroupCount, 2);
  assert.equal(projection.contractGroupCount, 2);
});

test('public release projection emits opaque identities only', () => {
  const rowWithPrivate = {
    ...row('chatgpt1', '1'.repeat(64), [toolA]),
    source: '/Users/example/private',
    port: 45018,
  };
  const output = publicReleaseProjection([rowWithPrivate], []);
  const encoded = JSON.stringify(output);
  assert.equal(encoded.includes('/Users/'), false);
  assert.equal(encoded.includes('45018'), false);
  assert.equal(output.accounts[0].account, 'chatgpt1');
  assert.equal(output.accounts[0].buildIdentity, '1'.repeat(64));
});

test('any failed seat makes release classification unknown without hiding healthy seats', () => {
  const output = publicReleaseProjection(
    [row('chatgpt1', '1'.repeat(64), [toolA])],
    [{account: 'chatgpt2', code: 'RELEASE_PROBE_FAILED'}],
  );
  assert.equal(output.classification, 'UNKNOWN_INCOMPLETE_FLEET');
  assert.equal(output.allReleasesObserved, false);
  assert.equal(output.accountCount, 2);
  assert.deepEqual(output.failures, [{account: 'chatgpt2', code: 'RELEASE_PROBE_FAILED'}]);
});

test('fleet build preserves probe failure and makes zero mutation calls', async () => {
  let calls = 0;
  const output = await buildFleetReleaseStatus('/unused', {
    discover: async () => ['chatgpt1', 'chatgpt2'],
    probe: async account => {
      calls += 1;
      if (account === 'chatgpt2') throw new Error('/Users/private/secret');
      return row(account, '1'.repeat(64), [toolA]);
    },
  });
  assert.equal(calls, 2);
  assert.equal(output.classification, 'UNKNOWN_INCOMPLETE_FLEET');
  assert.equal(JSON.stringify(output).includes('/Users/'), false);
});
