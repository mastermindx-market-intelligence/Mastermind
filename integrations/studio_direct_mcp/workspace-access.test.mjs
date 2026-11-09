import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import { execFile as execFileCallback } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmod, mkdir, mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const api = await import('./workspace-access.mjs').catch((error) => {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  return {};
});
const HEAD = 'a'.repeat(40);
const OP = 'workspace-test';
const repoNames = { mastermind: 'Mastermind', macro: 'macro', terminal: 'mastermind-terminal' };
const config = { enabled: true, allowedRepositories: ['mastermind', 'macro', 'terminal'] };
const gitConfig = { enabled: true, workspaceCli: '/owned/bin/mmx-workspace', gitBinary: '/usr/bin/git',
  sourceRepository: '/owned/source/mastermind',
  allowedRemoteUrls: ['https://github.com/mastermindx-market-intelligence/Mastermind.git'] };

const closedGitConfig = { enabled: true, workspaceCli: '/owned/bin/mmx-workspace', gitBinary: '/usr/bin/git',
  repositories: [
    { repository: 'mastermind', sourceRepository: '/owned/source/mastermind',
      allowedRemoteUrls: ['https://github.com/mastermindx-market-intelligence/Mastermind.git'] },
    { repository: 'macro', sourceRepository: '/owned/source/macro',
      allowedRemoteUrls: ['https://github.com/mastermindx-market-intelligence/macro.git'] },
    { repository: 'terminal', sourceRepository: '/owned/source/terminal',
      allowedRemoteUrls: ['https://github.com/mastermindx-market-intelligence/mastermind-terminal.git'] },
  ] };

function rows() {
  return Object.entries(repoNames).map(([alias, name]) => ({ alias,
    repository_full_name: `mastermindx-market-intelligence/${name}`,
    default_branch: alias === 'macro' ? 'main' : 'master', state: 'READY',
    remote_url: `https://github.com/mastermindx-market-intelligence/${name}.git`,
    source_repository: `/owned/source/${alias}`, common_git_dir: `/owned/source/${alias}/.git`,
    workspace_root: alias === 'mastermind' ? '/owned/workspaces' : `/owned/workspaces/${alias}`,
  }));
}
function discovery() { return { schema_version: 'mastermind.workspace_cli/v1', action: 'repositories',
  effect: 'NOT_APPLIED', receipt: { schema: 'mastermind.workspace_repositories/v1',
    repositories: rows(), admission_check_only: true, workspace_created: false } }; }
function acquisition(alias) {
  const row = rows().find((row) => row.alias === alias);
  return { schema_version: 'mastermind.workspace_cli/v2', action: 'acquire', repository: alias,
    effect: 'APPLIED', receipt: { source_repository: row.source_repository,
      workspace_root: row.workspace_root, workspace_path: path.join(row.workspace_root, 'web', OP),
      operation_id: OP, lane: 'web', base_sha: HEAD, head_sha: HEAD, branch: `sol/web-${OP}`,
      common_git_dir: row.common_git_dir,
      lock_reason: `mastermind-linked-worktree:v1 operation=${OP} lane=web base=${HEAD}`, reused: false } };
}
function setup(options = {}) {
  assert.equal(typeof api.createRepositoryWorkspaceAccess, 'function', 'workspace consumer must be implemented');
  const calls = [], publications = [];
  const gitCfg = options.gitConfig ?? gitConfig;
  const owner = options.owner ?? (async (argv) => {
    if (argv[0] === 'repositories') return discovery();
    return acquisition(argv[argv.indexOf('--repository') + 1]);
  });
  const gateway = api.createRepositoryWorkspaceAccess(config, gitCfg, {
    execFile: async (file, args, execution) => {
      calls.push({ file, args, execution });
      return { stdout: JSON.stringify(await owner(args)), stderr: '' };
    },
    publisherFactory: (selected) => {
      publications.push(selected);
      return Object.fromEntries(['status', 'commit', 'push', 'commissionStatus', 'commitCommission'].map((method) => [method, async (args) => ({
        schema: `mastermind.studio_git_${method}.v1`, effect_state: method === 'status' ? undefined : 'APPLIED',
        status: 'OK', local_head_sha: HEAD, args,
      })]));
    },
  });
  return { gateway, calls, publications };
}

test('new tools have closed truthful schemas and no path, remote or shell selector', () => {
  assert.ok(Array.isArray(api.STUDIO_WORKSPACE_TOOLS));
  assert.deepEqual(api.STUDIO_WORKSPACE_TOOLS.map((tool) => tool.name), ['studio_workspace_repositories', 'studio_workspace_acquire']);
  const [read, acquire] = api.STUDIO_WORKSPACE_TOOLS;
  assert.equal(read.annotations.readOnlyHint, true);
  assert.equal(acquire.annotations.readOnlyHint, false);
  assert.equal(acquire.annotations.idempotentHint, false, 'unknown effects never authorize blind automatic retry');
  assert.deepEqual(acquire.inputSchema.required, ['repository', 'operation_id', 'base_sha']);
  assert.equal(acquire.inputSchema.additionalProperties, false);
  for (const forbidden of ['path', 'source', 'remote', 'branch', 'command', 'force', 'env', 'executable']) {
    assert.equal(forbidden in acquire.inputSchema.properties, false);
  }
});

test('consumer configuration is explicitly enabled and cannot configure arbitrary repositories', () => {
  assert.equal(typeof api.resolveRepositoryWorkspaceConfig, 'function');
  assert.equal(api.resolveRepositoryWorkspaceConfig(undefined), null);
  assert.equal(api.resolveRepositoryWorkspaceConfig(false), null);
  assert.throws(() => api.resolveRepositoryWorkspaceConfig({ ...config, allowedRepositories: ['foreign'] }));
  assert.throws(() => api.resolveRepositoryWorkspaceConfig({ ...config, source: '/another' }));
  assert.throws(() => api.resolveRepositoryWorkspaceConfig({ ...config, allowedRepositories: ['macro', 'macro'] }));
});

test('repository discovery projects available aliases without exposing private paths', async () => {
  const { gateway, calls } = setup();
  const result = await gateway.repositories({});
  assert.equal(result.effect_state, 'NOT_APPLIED');
  assert.deepEqual(result.repositories.map((row) => row.alias), Object.keys(repoNames));
  assert.equal(JSON.stringify(result).includes('/owned/'), false);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].args, ['repositories']);
});

for (const alias of Object.keys(repoNames)) {
  test(`acquisition delegates one exact ${alias} operation to the installed owner`, async () => {
    const { gateway, calls } = setup();
    const result = await gateway.acquire({ repository: alias, operation_id: OP, base_sha: HEAD });
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.repository, alias);
    assert.equal(result.receipt.base_sha, HEAD);
    assert.equal(calls.length, 2);
    assert.deepEqual(calls[1].args, ['acquire', '--repository', alias, '--operation-id', OP,
      '--base-sha', HEAD, '--lane', 'web']);
    assert.equal(calls[1].file, gitConfig.workspaceCli);
  });
}

test('explicit repository publication composes existing publisher with the owner-selected binding', async () => {
  const { gateway, calls, publications } = setup();
  for (const method of ['status', 'commit', 'push']) {
    const args = { repository: 'macro', operation_id: OP };
    if (method !== 'status') args.expected_head_sha = HEAD;
    if (method === 'commit') args.message = 'test: scoped commit';
    const result = await gateway[method](args);
    assert.equal(result.repository, 'macro');
    assert.match(result.schema, /\.v2$/);
    assert.equal(result.args.repository, undefined, 'repository is consumed by the host router, not arbitrary publisher args');
    const selected = publications.at(-1);
    assert.equal(selected.repository, 'macro');
    assert.equal(selected.sourceRepository, '/owned/source/macro');
    assert.deepEqual(selected.allowedRemoteUrls, ['https://github.com/mastermindx-market-intelligence/macro.git']);
  }
  assert.ok(calls.every((call) => call.args[0] === 'repositories'));
});

for (const alias of Object.keys(repoNames)) {
  test(`closed three-repository profile resolves the exact ${alias} binding for explicit publication`, async () => {
    const { gateway, publications } = setup({ gitConfig: closedGitConfig });
    const result = await gateway.status({ repository: alias, operation_id: OP });
    assert.match(result.schema, /\.v2$/);
    assert.equal(result.repository, alias);
    const selected = publications.at(-1);
    assert.equal(selected.repository, alias);
    assert.equal(selected.sourceRepository, `/owned/source/${alias}`);
    assert.deepEqual(selected.allowedRemoteUrls,
      [`https://github.com/mastermindx-market-intelligence/${repoNames[alias]}.git`]);
  });
}


test('legacy publication keeps its original configuration and never reads an unrequested target', async () => {
  const { gateway, calls, publications } = setup();
  const result = await gateway.status({ operation_id: OP });
  assert.match(result.schema, /\.v1$/);
  assert.equal(result.repository, undefined);
  assert.equal(calls.length, 0);
  assert.equal(publications[0].sourceRepository, gitConfig.sourceRepository);
  assert.equal(publications[0].repository, undefined);
});

for (const malformed of [
  { repository: 'foreign', operation_id: OP, base_sha: HEAD },
  { repository: 'macro', operation_id: '../escape', base_sha: HEAD },
  { repository: 'macro', operation_id: OP, base_sha: 'HEAD' },
  { repository: 'macro', operation_id: OP, base_sha: HEAD, path: '/evil' },
]) {
  test(`invalid acquisition arguments refuse before any owner call: ${JSON.stringify(malformed)}`, async () => {
    const { gateway, calls } = setup();
    await assert.rejects(gateway.acquire(malformed));
    assert.equal(calls.length, 0);
  });
}

test('unavailable repository never falls back and produces no modifying call', async () => {
  const { gateway, calls, publications } = setup({ owner: async () => {
    const data = discovery();
    data.receipt.repositories[1] = { alias: 'macro', repository_full_name: 'mastermindx-market-intelligence/macro', default_branch: 'main', state: 'NOT_ENROLLED' };
    return data;
  } });
  await assert.rejects(gateway.acquire({ repository: 'macro', operation_id: OP, base_sha: HEAD }), /REPOSITORY_NOT_READY/);
  assert.equal(calls.length, 1);
  assert.equal(publications.length, 1, 'only the unchanged legacy publisher is constructed');
});

test('closed three-repository profile keeps the exact Mastermind source check', async () => {
  const { gateway } = setup({ gitConfig: closedGitConfig, owner: async () => {
    const data = discovery();
    data.receipt.repositories.find((row) => row.alias === 'mastermind').source_repository = '/elsewhere/mastermind';
    return data;
  } });
  await assert.rejects(gateway.status({ repository: 'mastermind', operation_id: OP }),
    /WORKSPACE_OWNER_RESPONSE_INVALID/);
});

test('closed three-repository profile keeps the exact Mastermind remote check', async () => {
  const misbound = { ...closedGitConfig, repositories: closedGitConfig.repositories.map((profile) =>
    profile.repository === 'mastermind'
      ? { ...profile, allowedRemoteUrls: ['https://example.invalid/Mastermind.git'] } : profile) };
  const { gateway } = setup({ gitConfig: misbound });
  await assert.rejects(gateway.status({ repository: 'mastermind', operation_id: OP }),
    /WORKSPACE_OWNER_RESPONSE_INVALID/);
});

test('legacy single-source profile still enforces its own Mastermind binding', async () => {
  const { gateway } = setup({ owner: async () => {
    const data = discovery();
    data.receipt.repositories.find((row) => row.alias === 'mastermind').source_repository = '/elsewhere/mastermind';
    return data;
  } });
  await assert.rejects(gateway.status({ repository: 'mastermind', operation_id: OP }),
    /WORKSPACE_OWNER_RESPONSE_INVALID/);
});

for (const kind of ['wrong_origin', 'duplicate_alias', 'wrong_default', 'outside_source']) {
  test(`malformed owner discovery fails closed: ${kind}`, async () => {
    const { gateway, calls } = setup({ owner: async () => {
      const data = discovery(); const row = data.receipt.repositories[1];
      if (kind === 'wrong_origin') row.remote_url = 'https://example.invalid/foreign';
      if (kind === 'duplicate_alias') data.receipt.repositories.push({ ...row });
      if (kind === 'wrong_default') row.default_branch = 'master';
      if (kind === 'outside_source') row.source_repository = 'relative/source';
      return data;
    } });
    await assert.rejects(gateway.acquire({ repository: 'macro', operation_id: OP, base_sha: HEAD }));
    assert.equal(calls.length, 1);
  });
}

test('lost acquisition return remains effect unknown and never automatically retries', async () => {
  const { gateway, calls } = setup({ owner: async (argv) => {
    if (argv[0] === 'repositories') return discovery();
    throw Object.assign(new Error('timeout after possible allocation'), { code: 'ETIMEDOUT' });
  } });
  const result = await gateway.acquire({ repository: 'macro', operation_id: OP, base_sha: HEAD });
  assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
  assert.equal(result.operation_id, OP);
  assert.equal(result.repository, 'macro');
  assert.equal(calls.length, 2);
});

for (const field of ['base_sha', 'operation_id', 'source_repository', 'workspace_path', 'common_git_dir', 'lock_reason']) {
  test(`foreign acquisition postcondition is effect unknown, not a retryable refusal: ${field}`, async () => {
    const { gateway, calls } = setup({ owner: async (argv) => {
      if (argv[0] === 'repositories') return discovery();
      const data = acquisition('macro'); data.receipt[field] = 'foreign'; return data;
    } });
    const result = await gateway.acquire({ repository: 'macro', operation_id: OP, base_sha: HEAD });
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(calls.length, 2);
  });
}


test('all new and extended tool descriptions state capabilities without classifier instructions', () => {
  const directives = /required workflow|always\b|never\b|only correct tool|must use|do not use|prefer this|critical rule/i;
  for (const tool of [...api.STUDIO_WORKSPACE_TOOLS, ...api.STUDIO_REPOSITORY_GIT_TOOLS]) {
    assert.doesNotMatch(tool.description, directives, tool.name);
  }
});

test('known pre-construction owner refusal is not promoted to effect unknown', async () => {
  const { gateway, calls } = setup({ owner: async (argv) => {
    if (argv[0] === 'repositories') return discovery();
    throw Object.assign(new Error('owner refused'), { code: 2, stderr: JSON.stringify({
      schema_version: 'mastermind.workspace_cli/v2', action: 'acquire', repository: 'macro',
      effect: 'NOT_APPLIED', error: 'STORAGE_LOW_SPACE: fixture reserve',
    }) });
  } });
  const result = await gateway.acquire({ repository: 'macro', operation_id: OP, base_sha: HEAD });
  assert.equal(result.status, 'REFUSED');
  assert.equal(result.effect_state, 'NOT_APPLIED');
  assert.equal(result.code, 'STORAGE_LOW_SPACE');
  assert.equal(calls.length, 2);
});

test('unversioned refusal after invocation cannot claim a known no-effect result', async () => {
  const { gateway } = setup({ owner: async (argv) => {
    if (argv[0] === 'repositories') return discovery();
    throw Object.assign(new Error('unqualified response'), { code: 2, stderr: JSON.stringify({
      action: 'acquire', repository: 'macro', effect: 'NOT_APPLIED', error: 'STORAGE_LOW_SPACE: unversioned',
    }) });
  } });
  const result = await gateway.acquire({ repository: 'macro', operation_id: OP, base_sha: HEAD });
  assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
});


test('workspace acquisition honestly allows canonical Git promisor materialization', () => {
  const acquire = api.STUDIO_WORKSPACE_TOOLS.find((tool) => tool.name === 'studio_workspace_acquire');
  assert.equal(acquire.annotations.openWorldHint, true,
    'the underlying Git owner can retrieve missing objects from its fixed canonical origin');
});


function statusReceipt() {
  const row = rows()[0];
  return { schema_version: 'mastermind.workspace_cli/v2', action: 'status',
    repository: 'mastermind', effect: 'NOT_APPLIED', receipt: {
      source_repository: row.source_repository, workspace_path: path.join(row.workspace_root, 'web', OP),
      branch: 'sol/web-' + OP, head_sha: HEAD, dirty: false, removed: false,
    } };
}
test('internal inspection qualifies exact existing owner custody without acquiring', async () => {
  const { gateway, calls } = setup({ owner: async (args) => args[0] === 'repositories' ? discovery() : statusReceipt() });
  assert.equal((await gateway.inspect({ repository: 'mastermind', operation_id: OP })).status, 'PRESENT');
  assert.deepEqual(calls.map((c) => c.args[0]), ['repositories', 'status']);
  assert.equal(api.STUDIO_WORKSPACE_TOOLS.some((t) => /inspect|commission/.test(t.name)), false);
});
for (const mutation of [{ removed: true }, { workspace_path: '/foreign' }, { branch: 'master' }, { head_sha: 'HEAD' }]) {
  test('internal inspection refuses unqualified existing custody: ' + JSON.stringify(mutation), async () => {
    const response = statusReceipt();
    Object.assign(response.receipt, mutation);
    const { gateway, calls } = setup({ owner: async (args) => args[0] === 'repositories' ? discovery() : response });
    await assert.rejects(gateway.inspect({ repository: 'mastermind', operation_id: OP }));
    assert.ok(calls.every((c) => c.args[0] !== 'acquire'));
  });
}
test('only exact known owner absence plus absent path permits fresh publication', async () => {
  const { gateway } = setup({ owner: async (args) => {
    if (args[0] === 'repositories') return discovery();
    throw Object.assign(Error('known absence'), { code: 2, stderr: JSON.stringify({
      schema_version: 'mastermind.workspace_cli/v2', action: 'status', effect: 'NOT_APPLIED',
      repository: 'mastermind', error: 'workspace is not registered to the source repository',
    }) });
  } });
  assert.equal((await gateway.inspect({ repository: 'mastermind', operation_id: OP })).status, 'ABSENT');
});
test('unknown status transport failure never becomes fresh allocation permission', async () => {
  const { gateway } = setup({ owner: async (args) => {
    if (args[0] === 'repositories') return discovery();
    throw Object.assign(Error('lost'), { code: 75, stderr: '' });
  } });
  await assert.rejects(gateway.inspect({ repository: 'mastermind', operation_id: OP }));
});


for (const repository of [undefined, 'mastermind', 'macro', 'terminal']) {
  test(`repository wrapper retains closed merge fences for ${repository ?? 'legacy'}`, async () => {
    const { gateway, publications } = setup();
    const args = { operation_id: OP, expected_head_sha: HEAD, message: 'test: reviewed merge',
      merge: { expected_protected_base_sha: 'b'.repeat(40), expected_tree_sha: 'c'.repeat(40) },
      ...(repository === undefined ? {} : { repository }) };
    const result = await gateway.commit(args);
    assert.deepEqual(result.args.merge, args.merge);
    assert.equal(result.args.repository, undefined);
    assert.equal(publications.at(-1).repository, repository);
    const schema = api.STUDIO_REPOSITORY_GIT_TOOLS.find((tool) => tool.name === 'studio_git_commit_current_changes').inputSchema;
    assert.equal(schema.properties.merge.additionalProperties, false);
    assert.deepEqual(Object.keys(schema.properties.merge.properties), ['expected_protected_base_sha', 'expected_tree_sha']);
  });
}


// ---------------------------------------------------------------------------
// Recovery-contract forwarding.
//
// The incumbent publisher owns action_ref and guarded recovery: its shape,
// hex, head and ancestry checks, its retained receipt journal and its effect
// classification. The adapter is a router, so it must admit exactly the
// publisher's own fields and forward the supplied values unchanged. It must
// not interpret, normalize, replace or retry them.
// ---------------------------------------------------------------------------

const ACTION_REF = 'a'.repeat(64);
const RECOVERY = Object.freeze({
  prior_action_ref: 'b'.repeat(64),
  prior_intended_head_sha: 'c'.repeat(40),
  expected_remote_head_sha: 'd'.repeat(40),
});
const ROUTES = [undefined, 'mastermind', 'macro', 'terminal'];

const CATALOG_METHODS = [
  ['studio_git_publish_status', 'status'],
  ['studio_git_commit_current_changes', 'commit'],
  ['studio_git_push_current_branch', 'push'],
];
const INDEX_RECOVERY = Object.freeze({
  mode: 'APPLY',
  expected_tree_sha: 'e'.repeat(40),
  expected_index_sha256: 'f'.repeat(64),
  lock: {
    device: '66306', inode: '56040019', file_type: 'REGULAR', uid: '1000', gid: '1000',
    mode: '0600', size: '0', mtime_ns: '1793987509342378895',
    content_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  },
  custody: { maintenance_window: 'psl-c4-maintenance-window-1', pending_mutators_retired: true },
});
const CATALOG_SAMPLE = {
  operation_id: OP,
  action_ref: ACTION_REF,
  expected_head_sha: HEAD,
  message: 'test: catalog agreement',
  merge: { expected_protected_base_sha: 'b'.repeat(40), expected_tree_sha: 'c'.repeat(40) },
  recovery: RECOVERY,
  index_recovery: INDEX_RECOVERY,
};

test('the published catalog and the dispatch handlers admit exactly the same keys', async () => {
  const { gateway, publications } = setup();
  for (const [toolName, method] of CATALOG_METHODS) {
    const tool = api.STUDIO_REPOSITORY_GIT_TOOLS.find((entry) => entry.name === toolName);
    assert.ok(tool, toolName);
    assert.equal(tool.inputSchema.additionalProperties, false, toolName);
    const catalogKeys = Object.keys(tool.inputSchema.properties).filter((key) => key !== 'repository');
    for (const key of catalogKeys) {
      const args = { operation_id: OP };
      if (key !== 'operation_id') args[key] = CATALOG_SAMPLE[key];
      const result = await gateway[method](args);
      assert.equal(result.args[key], CATALOG_SAMPLE[key], `${method} must forward ${key} unchanged`);
    }
    await assert.rejects(gateway[method]({ operation_id: OP, not_a_catalog_key: true }),
      /WORKSPACE_ARGUMENTS_INVALID/, method);
  }
  assert.equal(publications.length, 1, 'only the unchanged legacy publisher is constructed');
});

test('the repository catalog publishes the incumbent publisher own recovery fields', () => {
  const status = api.STUDIO_REPOSITORY_GIT_TOOLS.find((tool) => tool.name === 'studio_git_publish_status');
  const push = api.STUDIO_REPOSITORY_GIT_TOOLS.find((tool) => tool.name === 'studio_git_push_current_branch');
  assert.equal(status.inputSchema.properties.action_ref.pattern, '^[0-9a-f]{64}$');
  assert.equal(status.inputSchema.properties.action_ref.type, 'string');
  assert.equal(status.inputSchema.additionalProperties, false);
  assert.equal(push.inputSchema.properties.recovery.additionalProperties, false);
  assert.deepEqual(push.inputSchema.properties.recovery.required,
    ['prior_action_ref', 'prior_intended_head_sha', 'expected_remote_head_sha']);
  assert.equal(push.inputSchema.required.includes('recovery'), false,
    'recovery stays optional: an ordinary push never becomes a recovery');
  assert.equal(push.inputSchema.properties.repository.enum.length, 3);
});

test('the repository catalog publishes the closed index recovery object', () => {
  const commit = api.STUDIO_REPOSITORY_GIT_TOOLS.find((tool) => tool.name === 'studio_git_commit_current_changes');
  const recovery = commit.inputSchema.properties.index_recovery;
  assert.equal(recovery.additionalProperties, false);
  assert.deepEqual(recovery.required, ['mode']);
  assert.deepEqual(recovery.properties.mode.enum, ['PREVIEW', 'APPLY', 'RECONCILE']);
  assert.equal(recovery.properties.lock.additionalProperties, false);
  assert.deepEqual(recovery.properties.lock.required,
    ['device', 'inode', 'file_type', 'uid', 'gid', 'mode', 'size', 'mtime_ns', 'content_sha256']);
  assert.equal(recovery.properties.custody.additionalProperties, false);
  assert.deepEqual(recovery.properties.custody.required,
    ['maintenance_window', 'pending_mutators_retired']);
  assert.equal(commit.inputSchema.required.includes('message'), false,
    'the message is optional in the catalog because the recovery variant carries no message');
  assert.equal(commit.inputSchema.oneOf.length, 2);
  assert.equal(commit.inputSchema.properties.repository.enum.length, 3);
  assert.match(commit.description, /index_recovery/);
});

for (const repository of ROUTES) {
  test(`the index recovery object reaches the incumbent publisher unchanged for ${repository ?? 'legacy'}`, async () => {
    const { gateway, publications } = setup();
    const args = { operation_id: OP, expected_head_sha: HEAD, index_recovery: INDEX_RECOVERY,
      ...(repository === undefined ? {} : { repository }) };
    const result = await gateway.commit(args);
    assert.equal(result.args.index_recovery, INDEX_RECOVERY,
      'the supplied index recovery object is forwarded verbatim, not normalized or replaced');
    assert.equal(result.args.index_recovery.mode, 'APPLY');
    assert.equal(result.args.index_recovery.expected_tree_sha, INDEX_RECOVERY.expected_tree_sha);
    assert.equal(result.args.index_recovery.expected_index_sha256, INDEX_RECOVERY.expected_index_sha256);
    assert.equal(result.args.index_recovery.lock.inode, INDEX_RECOVERY.lock.inode);
    assert.equal(result.args.index_recovery.lock.mtime_ns, INDEX_RECOVERY.lock.mtime_ns);
    assert.equal(result.args.index_recovery.lock.mode, '0600');
    assert.equal(result.args.index_recovery.custody.pending_mutators_retired, true);
    assert.equal(result.args.repository, undefined,
      'the repository is consumed by the host router, not forwarded to the publisher');
    assert.equal(publications.at(-1).repository, repository);
  });
}

test('only commit admits the index recovery selector', async () => {
  const { gateway, publications } = setup();
  await assert.rejects(gateway.status({ operation_id: OP, index_recovery: INDEX_RECOVERY }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.push({ operation_id: OP, expected_head_sha: HEAD, index_recovery: INDEX_RECOVERY }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commissionStatus({ operation_id: OP, index_recovery: INDEX_RECOVERY }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commitCommission({ operation_id: OP, expected_head_sha: HEAD,
    expected_content_sha256: 'a'.repeat(64), index_recovery: INDEX_RECOVERY }), /WORKSPACE_ARGUMENTS_INVALID/);
  assert.equal(publications.length, 1, 'no refusal reached a publisher');
});

test('the adapter owns no index recovery interpretation and forwards the nested object verbatim', async () => {
  const { gateway } = setup();
  const recovery = { ...INDEX_RECOVERY, unknown_nested: 'x' };
  const result = await gateway.commit({ operation_id: OP, expected_head_sha: HEAD, index_recovery: recovery });
  assert.equal(result.args.index_recovery, recovery);
  assert.equal(result.args.index_recovery.unknown_nested, 'x',
    'nested closedness stays with the incumbent publisher, never with the router');
});

for (const repository of ROUTES) {
  test(`status action_ref reaches the existing publisher unchanged for ${repository ?? 'legacy'}`, async () => {
    const { gateway } = setup();
    const args = { operation_id: OP, action_ref: ACTION_REF, ...(repository === undefined ? {} : { repository }) };
    const result = await gateway.status(args);
    assert.equal(result.args.action_ref, ACTION_REF);
    assert.equal(result.args.repository, undefined,
      'repository is consumed by the host router, not forwarded to the publisher');
    assert.equal(result.schema.endsWith(repository === undefined ? '.v1' : '.v2'), true);
  });

  test(`push recovery reaches the existing publisher unchanged for ${repository ?? 'legacy'}`, async () => {
    const { gateway } = setup();
    const args = { operation_id: OP, expected_head_sha: HEAD, recovery: RECOVERY,
      ...(repository === undefined ? {} : { repository }) };
    const result = await gateway.push(args);
    assert.equal(result.args.recovery, RECOVERY,
      'the supplied recovery object is forwarded verbatim, not normalized or replaced');
    assert.equal(result.args.recovery.prior_action_ref, RECOVERY.prior_action_ref);
    assert.equal(result.args.recovery.prior_intended_head_sha, RECOVERY.prior_intended_head_sha);
    assert.equal(result.args.recovery.expected_remote_head_sha, RECOVERY.expected_remote_head_sha);
    assert.equal(result.args.repository, undefined);
  });
}

test('an unknown repository alias cannot reach the publisher with a recovery selector', async () => {
  const { gateway, publications } = setup();
  await assert.rejects(gateway.status({ repository: 'foreign', operation_id: OP, action_ref: ACTION_REF }),
    /REPOSITORY_NOT_PERMITTED/);
  await assert.rejects(gateway.push({ repository: 'foreign', operation_id: OP, expected_head_sha: HEAD, recovery: RECOVERY }),
    /REPOSITORY_NOT_PERMITTED/);
  assert.equal(publications.length, 1, 'only the unchanged legacy publisher is constructed');
});

test('commission status, commit and commission commit refuse unrelated recovery fields', async () => {
  const { gateway, publications } = setup();
  await assert.rejects(gateway.commissionStatus({ operation_id: OP, recovery: RECOVERY }), /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commissionStatus({ operation_id: OP, action_ref: ACTION_REF }), /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commit({ operation_id: OP, expected_head_sha: HEAD, message: 'test: refused', recovery: RECOVERY }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commit({ operation_id: OP, expected_head_sha: HEAD, message: 'test: refused', action_ref: ACTION_REF }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commitCommission({ operation_id: OP, expected_head_sha: HEAD,
    expected_content_sha256: 'e'.repeat(64), recovery: RECOVERY }), /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.commitCommission({ operation_id: OP, expected_head_sha: HEAD,
    expected_content_sha256: 'e'.repeat(64), action_ref: ACTION_REF }), /WORKSPACE_ARGUMENTS_INVALID/);
  assert.equal(publications.length, 1, 'no refusal reached a publisher');
});

test('extra unknown fields remain refused on the widened methods', async () => {
  const { gateway } = setup();
  await assert.rejects(gateway.status({ operation_id: OP, action_ref: ACTION_REF, extra: true }), /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.push({ operation_id: OP, expected_head_sha: HEAD, recovery: RECOVERY, extra: true }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.status({ repository: 'macro', operation_id: OP, action_ref: ACTION_REF, extra: true }),
    /WORKSPACE_ARGUMENTS_INVALID/);
  await assert.rejects(gateway.push({ repository: 'macro', operation_id: OP, expected_head_sha: HEAD, recovery: RECOVERY, extra: true }),
    /WORKSPACE_ARGUMENTS_INVALID/);
});

test('the adapter owns no recovery interpretation and forwards the nested object verbatim', async () => {
  const { gateway } = setup();
  const recovery = { ...RECOVERY, unknown_nested: 'x' };
  const result = await gateway.push({ operation_id: OP, expected_head_sha: HEAD, recovery });
  assert.equal(result.args.recovery, recovery);
  assert.equal(result.args.recovery.unknown_nested, 'x',
    'nested closedness stays with the incumbent publisher, never with the router');
});

test('an ordinary legacy call without any recovery selector still works', async () => {
  const { gateway, calls, publications } = setup();
  const result = await gateway.status({ operation_id: OP });
  assert.match(result.schema, /\.v1$/);
  assert.equal(result.args.action_ref, undefined);
  assert.equal(result.args.recovery, undefined);
  assert.equal(calls.length, 0);
  assert.equal(publications[0].sourceRepository, gitConfig.sourceRepository);
});


// ---------------------------------------------------------------------------
// Actual-target-publisher fixture.
//
// The cases above use an inert publisher seam. These use the installed
// incumbent publisher itself over an isolated real Git workspace and a local
// bare remote, so the closed validator, the retained-receipt lookup and the
// effect classification under test are the shipped ones. No listener, network
// request, live repository write, push or credential is involved: the remote
// is a local bare repository and the canonical remote URL is present only to
// satisfy the adapter's own Mastermind source/remote binding check.
// ---------------------------------------------------------------------------

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
// The admitted worker workspace lives on the external SSD. Keep the throwaway
// publisher fixture beside it instead of on the internal disk.
const FIXTURE_PARENT = path.join(path.dirname(REPO_ROOT), 'psl-publisher-adapter-fixtures');
const GIT = '/usr/bin/git';
const execFile = promisify(execFileCallback);
const shQuote = (value) => "'" + value.replaceAll("'", "'\\''") + "'";

async function run(file, args, options = {}) {
  return execFile(file, args, { encoding: 'utf8', maxBuffer: 1024 * 1024, ...options });
}
async function git(cwd, ...args) { return run(GIT, args, { cwd }); }

// The incumbent publisher pins its push destination with repeated -c
// overrides and requires `git remote get-url --all origin` to return exactly
// one URL. Git builds that append repeated -c values instead of replacing
// the list cannot satisfy that contract. Resolve a binary that can, so this
// fixture exercises the shipped publisher rather than a weakened stand-in.
const GIT_CANDIDATES = [...new Set([...(process.env.PATH ?? '').split(':').filter(Boolean)
  .map((dir) => path.join(dir, 'git')), '/usr/bin/git'])];

async function resolvesPinnedDestination(gitBinary, workspacePath, remote) {
  try {
    const { stdout } = await execFile(gitBinary, ['-c', 'remote.origin.url=', '-c', `remote.origin.url=${remote}`,
      '-c', 'remote.origin.pushurl=', '-c', `remote.origin.pushurl=${remote}`, '-c', 'remote.origin.mirror=false',
      'remote', 'get-url', '--all', 'origin'],
    { cwd: workspacePath, encoding: 'utf8', maxBuffer: 1024 * 1024 });
    const lines = stdout.trim().split('\n');
    return lines.length === 1 && lines[0] === remote;
  } catch {
    return false;
  }
}

async function resolvePublisherGitBinary(workspacePath, remote) {
  for (const candidate of GIT_CANDIDATES) {
    try { await stat(candidate); } catch { continue; }
    if (await resolvesPinnedDestination(candidate, workspacePath, remote)) return candidate;
  }
  throw new Error('no installed Git build satisfies the incumbent publisher pinned-destination contract');
}

async function makePublisherFixture() {
  await mkdir(FIXTURE_PARENT, { recursive: true });
  const root = await realpath(await mkdtemp(path.join(FIXTURE_PARENT, 'fixture-')));
  const sourceRepository = path.join(root, 'source');
  const workspacePath = path.join(root, 'workspace');
  const remote = path.join(root, 'remote.git');
  const operationId = 'psl-publisher-adapter-fixture';
  const branch = `sol/web-${operationId}`;
  const ownerLog = path.join(root, 'owner.log');
  const gitLog = path.join(root, 'git.log');
  await mkdir(sourceRepository, { recursive: true });
  await mkdir(workspacePath, { recursive: true });
  await git(root, 'init', '--bare', remote);
  await git(sourceRepository, 'init', '-b', 'master');
  await git(sourceRepository, 'config', 'user.name', 'Publisher Fixture');
  await git(sourceRepository, 'config', 'user.email', 'publisher-fixture@example.invalid');
  await git(sourceRepository, 'commit', '--allow-empty', '-m', 'test: source fixture');
  await git(workspacePath, 'init', '-b', 'master');
  await git(workspacePath, 'config', 'user.name', 'Publisher Fixture');
  await git(workspacePath, 'config', 'user.email', 'publisher-fixture@example.invalid');
  await git(workspacePath, 'checkout', '-b', branch);
  await writeFile(path.join(workspacePath, 'proof.txt'), 'psl publisher fixture\n');
  await git(workspacePath, 'add', 'proof.txt');
  await git(workspacePath, 'commit', '-m', 'test: publisher fixture');
  await git(workspacePath, 'remote', 'add', 'origin', remote);
  const head = (await git(workspacePath, 'rev-parse', 'HEAD')).stdout.trim();

  const responses = {
    repositories: { schema_version: 'mastermind.workspace_cli/v1', action: 'repositories',
      effect: 'NOT_APPLIED', receipt: { schema: 'mastermind.workspace_repositories/v1',
        repositories: Object.entries(repoNames).map(([alias, name]) => ({ alias,
          repository_full_name: `mastermindx-market-intelligence/${name}`,
          default_branch: alias === 'macro' ? 'main' : 'master', state: 'READY',
          remote_url: `https://github.com/mastermindx-market-intelligence/${name}.git`,
          source_repository: sourceRepository, common_git_dir: path.join(sourceRepository, '.git'),
          workspace_root: root })),
        admission_check_only: true, workspace_created: false } },
    status: { schema_version: 'mastermind.workspace_cli/v2', action: 'status', repository: 'mastermind',
      effect: 'NOT_APPLIED', receipt: { source_repository: sourceRepository, workspace_path: workspacePath,
        branch, head_sha: head, dirty: false, removed: false } },
  };
  const ownerScript = path.join(root, 'owner.mjs');
  await writeFile(ownerScript, [
    "import { appendFileSync } from 'node:fs';",
    `const responses = ${JSON.stringify(responses)};`,
    `const logPath = ${JSON.stringify(ownerLog)};`,
    'const argv = process.argv.slice(2);',
    "appendFileSync(logPath, JSON.stringify(argv) + '\\n');",
    "if (argv[0] !== 'repositories' && argv[0] !== 'status') {",
    "  process.stderr.write('unsupported fixture owner request\\n'); process.exit(2);",
    '}',
    "const response = argv[0] === 'status' && argv.includes('--repository')",
    "  ? { ...responses.status, repository: argv[argv.indexOf('--repository') + 1] } : responses[argv[0]];",
    "process.stdout.write(JSON.stringify(response) + '\\n');",
    '',
  ].join('\n'));
  const workspaceCli = path.join(root, 'mmx-workspace');
  await writeFile(workspaceCli, `#!/bin/sh\nexec ${shQuote(process.execPath)} ${shQuote(ownerScript)} "$@"\n`);
  await chmod(workspaceCli, 0o700);

  // A recording Git binary proves that no Git command at all runs before the
  // incumbent closed validator refuses a malformed recovery.
  const publisherGit = await resolvePublisherGitBinary(workspacePath, remote);
  const gitScript = path.join(root, 'git-wrap.mjs');
  await writeFile(gitScript, [
    "import { appendFileSync } from 'node:fs';",
    "import { spawnSync } from 'node:child_process';",
    `const logPath = ${JSON.stringify(gitLog)};`,
    'const args = process.argv.slice(2);',
    "appendFileSync(logPath, JSON.stringify(args) + '\\n');",
    `const result = spawnSync(${JSON.stringify(publisherGit)}, args, { stdio: 'inherit' });`,
    'process.exit(typeof result.status === "number" ? result.status : 1);',
    '',
  ].join('\n'));
  const gitBinary = path.join(root, 'git');
  await writeFile(gitBinary, `#!/bin/sh\nexec ${shQuote(process.execPath)} ${shQuote(gitScript)} "$@"\n`);
  await chmod(gitBinary, 0o700);

  const canonicalRemote = 'https://github.com/mastermindx-market-intelligence/Mastermind.git';
  async function logged(file) {
    try {
      return (await readFile(file, 'utf8')).split('\n').filter(Boolean).map((line) => JSON.parse(line));
    } catch (error) {
      if (error.code === 'ENOENT') return [];
      throw error;
    }
  }
  return { root, sourceRepository, workspacePath, remote, operationId, branch, head, workspaceCli, gitBinary,
    publisherGit,
    gitConfig: { enabled: true, workspaceCli, gitBinary, sourceRepository,
      allowedRemoteUrls: [remote, canonicalRemote], commandTimeoutMs: 10_000, pushTimeoutMs: 10_000 },
    gitInvocations: () => logged(gitLog),
    ownerInvocations: () => logged(ownerLog),
    remoteRefs: async () => (await git(remote, 'for-each-ref', '--format=%(refname)')).stdout.trim(),
    workspaceHead: async () => (await git(workspacePath, 'rev-parse', 'HEAD')).stdout.trim(),
    workspaceStatus: async () => (await git(workspacePath, 'status', '--porcelain')).stdout,
    // The incumbent publisher's own deterministic action identity.
    actionRefFor: (headSha) => createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(operationId).update('\0').update(branch).update('\0').update(headSha).digest('hex'),
  };
}

test('the actual incumbent publisher consumes a supplied action_ref itself', async () => {
  const fixture = await makePublisherFixture();
  try {
    const gateway = api.createRepositoryWorkspaceAccess(config, fixture.gitConfig);
    const result = await gateway.status({ operation_id: fixture.operationId, action_ref: ACTION_REF });
    assert.equal(result.schema, 'mastermind.studio_git_publish_status.v1');
    assert.equal(result.publication_recovery.action_ref, ACTION_REF,
      'the retained-receipt lookup ran for this exact action');
    assert.equal(result.publication_recovery.outcome, 'UNKNOWN');
    assert.equal(result.publication_recovery.reason, 'NO_MATCHING_OR_LEGACY_RECEIPT');
    assert.equal(result.publication_recovery.retry_allowed, false);
    assert.equal(result.local_head_sha, fixture.head);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

for (const [label, recovery, expected] of [
  ['a non-hex prior identity', { ...RECOVERY, prior_action_ref: 'not-hex' }, /recovery identities are invalid/],
  ['an unknown nested key', { ...RECOVERY, unknown_nested: 'x' }, /recovery arguments are invalid/],
]) {
  test(`malformed nested recovery reaches the incumbent closed validator without a Git mutation: ${label}`, async () => {
    const fixture = await makePublisherFixture();
    try {
      const gateway = api.createRepositoryWorkspaceAccess(config, fixture.gitConfig);
      await assert.rejects(
        gateway.push({ operation_id: fixture.operationId, expected_head_sha: fixture.head, recovery }),
        (error) => {
          assert.equal(error instanceof TypeError, true,
            'the refusal belongs to the incumbent publisher, not to the router');
          assert.match(error.message, expected);
          return true;
        });
      assert.deepEqual(await fixture.gitInvocations(), [],
        'no Git command may run before the incumbent closed validator refuses');
      assert.deepEqual(await fixture.ownerInvocations(), [],
        'the publisher never even resolved the registered workspace');
      assert.equal(await fixture.remoteRefs(), '', 'no remote ref was created');
      assert.equal(await fixture.workspaceHead(), fixture.head);
      assert.equal(await fixture.workspaceStatus(), '');
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });
}

test('a well-formed recovery is classified by the incumbent publisher, never by the router', async () => {
  const fixture = await makePublisherFixture();
  try {
    const gateway = api.createRepositoryWorkspaceAccess(config, fixture.gitConfig);
    const recovery = { prior_action_ref: fixture.actionRefFor(fixture.head),
      prior_intended_head_sha: fixture.head, expected_remote_head_sha: 'e'.repeat(40) };
    const result = await gateway.push({ operation_id: fixture.operationId,
      expected_head_sha: fixture.head, recovery });
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'RECOVERY_REMOTE_HEAD_MISMATCH');
    assert.equal(result.push_attempted, false);
    assert.equal(result.retry_allowed, false);
    assert.equal(result.prior_action_ref, recovery.prior_action_ref);
    const invocations = await fixture.gitInvocations();
    assert.equal(invocations.some((args) => args.includes('push')), false, 'no push was issued');
    assert.equal(await fixture.remoteRefs(), '');
    assert.equal(await fixture.workspaceHead(), fixture.head);
    assert.equal(await fixture.workspaceStatus(), '');
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

for (const alias of Object.keys(repoNames)) {
  test(`malformed nested recovery cannot execute a Git mutation for the explicit ${alias} route`, async () => {
    const fixture = await makePublisherFixture();
    try {
      const gateway = api.createRepositoryWorkspaceAccess(config, fixture.gitConfig);
      await assert.rejects(
        gateway.push({ repository: alias, operation_id: fixture.operationId, expected_head_sha: fixture.head,
          recovery: { ...RECOVERY, prior_action_ref: 'not-hex' } }),
        /recovery identities are invalid/);
      assert.deepEqual(await fixture.gitInvocations(), [], 'no Git command ran');
      assert.equal(await fixture.remoteRefs(), '');
      assert.equal(await fixture.workspaceHead(), fixture.head);
      assert.deepEqual(await fixture.ownerInvocations(), [['repositories']],
        'only the read-only repository discovery precedes the incumbent refusal');
    } finally {
      await rm(fixture.root, { recursive: true, force: true });
    }
  });
}
