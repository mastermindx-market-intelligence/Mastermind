import path from 'node:path';
import { execFile as execFileCallback } from 'node:child_process';
import { promisify } from 'node:util';
import { createGitPublisher, resolveGitPublishConfig, STUDIO_GIT_PUBLISH_TOOLS } from './git-publish.mjs';

// A thin consumer of the installed workspace owner. No allocation, Git
// publication, registration, retry or lifecycle implementation lives here.
const execFileDefault = promisify(execFileCallback);
const REPOSITORIES = Object.freeze({ mastermind: ['Mastermind', 'master'], macro: ['macro', 'main'], terminal: ['mastermind-terminal', 'master'] });
const ALIASES = Object.keys(REPOSITORIES);
const OPERATION = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const SHA = /^[0-9a-f]{40}$/;
const RESOLVED = new WeakSet();
const repositoryProperty = { type: 'string', enum: ALIASES };
const operationProperty = { type: 'string', minLength: 1, maxLength: 96, pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$' };

export const STUDIO_WORKSPACE_TOOLS = Object.freeze([
  Object.freeze({
    name: 'studio_workspace_repositories', title: 'Studio Workspace Repositories',
    description: 'Read installed, host-owned Mastermind/Macro/Terminal workspace choices. READY means the local repository binding is verified, not storage or execution admission. No allocation, network fetch, configuration change or credentials.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }),
  Object.freeze({
    name: 'studio_workspace_acquire', title: 'Studio Workspace Acquire',
    description: 'MODIFYING. Ask the installed mmx-workspace owner to acquire or reuse one operation-bound workspace for a closed repository alias and exact base commit. The host owns source paths, storage, branch derivation and remotes. A lost or unqualified return is EFFECT_UNKNOWN and conveys no retry or retargeting authority. Reconciliation concerns the same repository and operation.',
    inputSchema: { type: 'object', properties: { repository: repositoryProperty, operation_id: operationProperty,
      base_sha: { type: 'string', pattern: '^[0-9a-f]{40}$' } },
      required: ['repository', 'operation_id', 'base_sha'], additionalProperties: false },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
  }),
]);

const PUBLICATION_DESCRIPTIONS = [
  'Read publication status for one existing managed workspace. Optional repository is a closed host-enrolled alias; omission preserves the legacy Mastermind route. The installed owner supplies the workspace and source binding. No workspace allocation, commit or push is performed.',
  'MODIFYING. Commit current committable changes in one existing managed workspace through the existing exact-HEAD-fenced publisher. Optional repository is a closed host-enrolled alias; omission preserves Mastermind. No caller path, branch, remote, credential or command. This operation is local-only and has no push capability.',
  'MODIFYING. Push the exact expected HEAD of one existing clean managed workspace through the existing same-branch, canonical-origin publisher. Optional repository is a closed host-enrolled alias; omission preserves Mastermind. No force, tag, arbitrary destination or credential input. Unknown effects convey no retry or retargeting authority.',
];
export const STUDIO_REPOSITORY_GIT_TOOLS = Object.freeze(STUDIO_GIT_PUBLISH_TOOLS.map((tool, i) => Object.freeze({
  ...tool, description: PUBLICATION_DESCRIPTIONS[i],
  inputSchema: { ...tool.inputSchema, properties: { ...tool.inputSchema.properties, repository: repositoryProperty } },
})));

function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function closed(value, keys) {
  if (!object(value) || Object.keys(value).some((key) => !keys.includes(key))) throw new Error('WORKSPACE_ARGUMENTS_INVALID');
}
function absolute(value) { return typeof value === 'string' && value.length > 0 && value.length <= 4096 && !/[\x00-\x1f]/.test(value) && path.isAbsolute(value) && path.resolve(value) === value; }
function remote(alias) { return `https://github.com/mastermindx-market-intelligence/${REPOSITORIES[alias][0]}.git`; }
function parse(text) {
  if (typeof text !== 'string' || Buffer.byteLength(text) > 1024 * 1024) throw new Error('WORKSPACE_OWNER_RESPONSE_INVALID');
  try { return JSON.parse(text); } catch { throw new Error('WORKSPACE_OWNER_RESPONSE_INVALID'); }
}

export function resolveRepositoryWorkspaceConfig(value) {
  if (value === undefined || value === null || value === false) return null;
  if (object(value) && RESOLVED.has(value)) return value;
  closed(value, ['enabled', 'allowedRepositories']);
  if (value.enabled !== true || !Array.isArray(value.allowedRepositories) || !value.allowedRepositories.length ||
      value.allowedRepositories.length > 3 || value.allowedRepositories.some((item) => !ALIASES.includes(item)) ||
      new Set(value.allowedRepositories).size !== value.allowedRepositories.length) throw new Error('WORKSPACE_CONFIGURATION_INVALID');
  const result = Object.freeze({ enabled: true, allowedRepositories: Object.freeze([...value.allowedRepositories]) });
  RESOLVED.add(result);
  return result;
}

function validateRows(value) {
  if (!object(value) || value.action !== 'repositories' || value.effect !== 'NOT_APPLIED' ||
      value.schema_version !== 'mastermind.workspace_cli/v1' ||
      value.receipt?.schema !== 'mastermind.workspace_repositories/v1' ||
      value.receipt.admission_check_only !== true || value.receipt.workspace_created !== false ||
      !Array.isArray(value.receipt.repositories) || value.receipt.repositories.length !== 3) throw new Error('WORKSPACE_OWNER_RESPONSE_INVALID');
  const seen = new Set();
  for (const row of value.receipt.repositories) {
    if (!object(row) || !ALIASES.includes(row.alias) || seen.has(row.alias) ||
        row.repository_full_name !== `mastermindx-market-intelligence/${REPOSITORIES[row.alias][0]}` ||
        row.default_branch !== REPOSITORIES[row.alias][1] || !['READY', 'UNAVAILABLE', 'NOT_ENROLLED'].includes(row.state)) throw new Error('WORKSPACE_OWNER_RESPONSE_INVALID');
    seen.add(row.alias);
    if (row.state === 'READY' && (row.remote_url !== remote(row.alias) ||
        !['source_repository', 'common_git_dir', 'workspace_root'].every((key) => absolute(row[key])))) throw new Error('WORKSPACE_OWNER_RESPONSE_INVALID');
  }
  return value.receipt.repositories;
}

function validateAcquisition(value, row, args) {
  const receipt = value?.receipt;
  const branch = `sol/web-${args.operation_id.toLowerCase()}`;
  const workspace = path.join(row.workspace_root, 'web', args.operation_id.toLowerCase());
  if (value?.schema_version !== 'mastermind.workspace_cli/v2' || value.action !== 'acquire' ||
      value.repository !== row.alias || !['APPLIED', 'NOT_APPLIED'].includes(value.effect) || !object(receipt) ||
      receipt.source_repository !== row.source_repository || receipt.workspace_root !== row.workspace_root ||
      receipt.workspace_path !== workspace || receipt.operation_id !== args.operation_id || receipt.lane !== 'web' ||
      receipt.base_sha !== args.base_sha || typeof receipt.head_sha !== 'string' || !SHA.test(receipt.head_sha) ||
      receipt.branch !== branch || receipt.common_git_dir !== row.common_git_dir ||
      receipt.lock_reason !== `mastermind-linked-worktree:v1 operation=${args.operation_id} lane=web base=${args.base_sha}` ||
      typeof receipt.reused !== 'boolean' || (receipt.reused ? value.effect !== 'NOT_APPLIED' : value.effect !== 'APPLIED' || receipt.head_sha !== args.base_sha)) throw new Error('WORKSPACE_ACQUISITION_UNQUALIFIED');
  return receipt;
}

export function createRepositoryWorkspaceAccess(config, gitConfig, dependencies = {}) {
  const cfg = resolveRepositoryWorkspaceConfig(config);
  const git = resolveGitPublishConfig(gitConfig);
  if (!cfg || !git) throw new Error('WORKSPACE_CONFIGURATION_INVALID');
  const execute = dependencies.execFile ?? execFileDefault;
  const publisherFactory = dependencies.publisherFactory ?? createGitPublisher;
  const legacy = publisherFactory(git);

  async function owner(args) {
    const result = await execute(git.workspaceCli, args, {
      timeout: git.commandTimeoutMs, maxBuffer: 1024 * 1024, encoding: 'utf8',
      env: { PATH: '/usr/bin:/bin:/usr/sbin:/sbin', HOME: process.env.HOME ?? '',
        USER: process.env.USER ?? '', LOGNAME: process.env.LOGNAME ?? '', LANG: 'C', LC_ALL: 'C',
        GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: '/usr/bin/false', SSH_ASKPASS: '/usr/bin/false' },
    });
    return parse(result.stdout);
  }
  async function currentRows() { return validateRows(await owner(['repositories'])); }
  function selectAlias(alias) {
    if (!cfg.allowedRepositories.includes(alias)) throw new Error('REPOSITORY_NOT_PERMITTED');
    return alias;
  }
  async function selected(alias) {
    selectAlias(alias);
    const row = (await currentRows()).find((row) => row.alias === alias);
    if (row?.state !== 'READY') throw new Error('REPOSITORY_NOT_READY');
    if (alias === 'mastermind' && (row.source_repository !== path.resolve(git.sourceRepository) ||
        !git.allowedRemoteUrls.includes(row.remote_url))) throw new Error('WORKSPACE_OWNER_RESPONSE_INVALID');
    return row;
  }
  async function repositories(args) {
    closed(args, []);
    const rows = await currentRows();
    return { schema: 'mastermind.studio_workspace_repositories.v1', effect_state: 'NOT_APPLIED',
      repositories: rows.filter((row) => cfg.allowedRepositories.includes(row.alias)).map((row) => ({
        alias: row.alias, repository_full_name: row.repository_full_name, default_branch: row.default_branch, state: row.state,
      })), admission_evaluated: false };
  }
  async function acquire(args) {
    closed(args, ['repository', 'operation_id', 'base_sha']);
    selectAlias(args.repository);
    if (typeof args.operation_id !== 'string' || !OPERATION.test(args.operation_id) || typeof args.base_sha !== 'string' || !SHA.test(args.base_sha)) throw new Error('WORKSPACE_ARGUMENTS_INVALID');
    const row = await selected(args.repository);
    const identity = { schema: 'mastermind.studio_workspace_acquire.v1', repository: args.repository, operation_id: args.operation_id, base_sha: args.base_sha };
    // This boundary is intentionally one-shot. A missing/malformed response after
    // invoking the owner is uncertainty, not an invitation to create another tree.
    try {
      const value = await owner(['acquire', '--repository', args.repository, '--operation-id', args.operation_id,
        '--base-sha', args.base_sha, '--lane', 'web']);
      const receipt = validateAcquisition(value, row, args);
      return { ...identity, status: 'OK', effect_state: value.effect, receipt };
    } catch (error) {
      // Only documented pre-construction validation failures prove no effect.
      // Never trust the old owner's generic NOT_APPLIED label after arbitrary
      // constructor errors or a transport timeout.
      if (error?.code === 2) {
        try {
          const refused = parse(error.stderr);
          if (refused.schema_version === 'mastermind.workspace_cli/v2' && refused.action === 'acquire' && refused.repository === args.repository && refused.effect === 'NOT_APPLIED' &&
              /^(REPOSITORY_[A-Z_]+|STORAGE_[A-Z_]+):/.test(refused.error ?? '')) {
            return { ...identity, status: 'REFUSED', effect_state: 'NOT_APPLIED', code: refused.error.split(':', 1)[0] };
          }
        } catch { /* absence of qualified evidence preserves uncertainty */ }
      }
      return { ...identity, status: 'PARTIAL', effect_state: 'EFFECT_UNKNOWN', code: 'WORKSPACE_ACQUISITION_UNQUALIFIED' };
    }
  }
  async function publication(method, args) {
    const keys = method === 'status' ? ['operation_id', 'repository'] : method === 'commit'
      ? ['operation_id', 'repository', 'expected_head_sha', 'message'] : ['operation_id', 'repository', 'expected_head_sha'];
    closed(args, keys);
    if (args.repository === undefined) return legacy[method](args);
    selectAlias(args.repository);
    if (typeof args.operation_id !== 'string' || !OPERATION.test(args.operation_id)) throw new Error('WORKSPACE_ARGUMENTS_INVALID');
    const row = await selected(args.repository);
    const publisher = publisherFactory({ enabled: true, workspaceCli: git.workspaceCli, gitBinary: git.gitBinary,
      sourceRepository: row.source_repository, allowedRemoteUrls: [row.remote_url], repository: args.repository,
      commandTimeoutMs: git.commandTimeoutMs, pushTimeoutMs: git.pushTimeoutMs });
    const { repository, ...original } = args;
    const result = await publisher[method](original);
    return { ...result, schema: result.schema.replace(/\.v1$/, '.v2'), repository };
  }
  return Object.freeze({ repositories, acquire,
    status: (args) => publication('status', args), commit: (args) => publication('commit', args), push: (args) => publication('push', args) });
}
