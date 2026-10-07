import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';

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
  const owner = options.owner ?? (async (argv) => {
    if (argv[0] === 'repositories') return discovery();
    return acquisition(argv[argv.indexOf('--repository') + 1]);
  });
  const gateway = api.createRepositoryWorkspaceAccess(config, gitConfig, {
    execFile: async (file, args, execution) => {
      calls.push({ file, args, execution });
      return { stdout: JSON.stringify(await owner(args)), stderr: '' };
    },
    publisherFactory: (selected) => {
      publications.push(selected);
      return Object.fromEntries(['status', 'commit', 'push'].map((method) => [method, async (args) => ({
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
