import { createHash, randomUUID } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { constants as fsConstants } from 'node:fs';
import { mkdir, mkdtemp, open, realpath as realpathDefault, rename, rm, unlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';

const execFileDefault = promisify(execFileCallback);

const OPERATION_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const SHA_RE = /^[0-9a-f]{40}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
const BRANCH_RE = /^sol\/web-[A-Za-z0-9._-]+$/;
const ALLOWED_LANE = 'web';
const MAX_STDIO_BYTES = 1024 * 1024;
const DEFAULT_COMMAND_TIMEOUT_MS = 15_000;
const DEFAULT_PUSH_TIMEOUT_MS = 60_000;
const RESOLVED_CONFIGS = new WeakSet();

// Canonical commission convention expected by the trusted resolver. These are
// fixed host constants: no caller ever selects a repository, branch or path.
const COMMISSION_DIR_SEGMENTS = Object.freeze(['research', 'executive_commissions']);
const COMMISSION_FILE_NAME = 'COMMISSION.md';
const COMMISSION_RELATIVE_PATH = [...COMMISSION_DIR_SEGMENTS, COMMISSION_FILE_NAME].join('/');

// Frozen contract consumed from the incumbent Mastermind Craft brief compiler
// (`research/worker_craft/mastermind-craft/scripts/brief.py`). That compiler
// remains the sole owner of compact-request validation and commission
// rendering; this adapter only feeds it and fences where its bytes land.
const COMMISSION_REQUEST_SCHEMA = 'mastermind.craft_commission_request.v1';
const COMMISSION_COMPILATION_SCHEMA = 'mastermind.craft_commission_compilation.v1';
const COMMISSION_REQUEST_FIELDS = Object.freeze([
  'schema_version', 'role', 'authority_ref', 'source', 'outcome', 'scope', 'inputs',
  'data', 'method', 'deliverables', 'acceptance', 'failure', 'constraints', 'continuation',
]);
// Mirrors the compiler's own MAX_COMMISSION_INPUT_BYTES so an oversized compact
// request is refused before anything is written to disk.
const MAX_COMMISSION_INPUT_BYTES = 16_384;
const MAX_COMMISSION_OUTPUT_BYTES = 2 * 1024 * 1024;
const DEFAULT_COMMISSION_TIMEOUT_MS = 30_000;
// The compiler's refusal tokens are a closed `field.reason` vocabulary that by
// construction carries no caller values or filesystem paths.
const REFUSAL_TOKEN_RE = /^[A-Za-z][A-Za-z0-9_.]{0,127}$/;
const SELECTION_ASSERTIONS = Object.freeze([
  ['execution_authority', false],
  ['provider_selection', 'NOT_PERFORMED'],
  ['model_selection', 'NOT_PERFORMED'],
  ['account_selection', 'NOT_PERFORMED'],
]);

export const STUDIO_GIT_PUBLISH_STATUS_TOOL = Object.freeze({
  name: 'studio_git_publish_status',
  title: 'Studio Git Publish Status',
  description:
    'Read-only publication status for one existing Mastermind attended Web workspace. ' +
    'The host resolves the workspace, repository, branch and origin from the canonical mmx-workspace ' +
    'registration. The caller supplies only the operation id. Reports the current local HEAD, remote ' +
    'branch HEAD and whether the workspace is clean. It never creates a workspace, commits, pushes, ' +
    'changes a ref, or accepts a repository, path, branch, remote, credential, shell command or force option.',
  inputSchema: {
    type: 'object',
    properties: {
      operation_id: {
        type: 'string',
        minLength: 1,
        maxLength: 256,
        pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$',
      },
    },
    required: ['operation_id'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Studio Git Publish Status',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: true,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'private-studio-mcp/typed-git': true },
});

export const STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL = Object.freeze({
  name: 'studio_git_commit_current_changes',
  title: 'Studio Git Commit Current Changes',
  description:
    'Create exactly one local commit from all current committable changes in one existing Mastermind ' +
    'attended Web workspace. The host resolves the workspace and branch from canonical mmx-workspace ' +
    'registration. The caller supplies only the operation id, exact expected current HEAD and a bounded ' +
    'single-line commit message. Ignored files stay uncommitted. A private temporary index prevents ' +
    'pre-commit staging side effects; after the fenced ref update is known applied, the real index is ' +
    'synchronized to that exact commit. Compare-and-swap ref update prevents stale-head publication. ' +
    'It never contacts origin, pushes, accepts paths, changes remotes, or accepts shell commands.',
  inputSchema: {
    type: 'object',
    properties: {
      operation_id: {
        type: 'string',
        minLength: 1,
        maxLength: 256,
        pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$',
      },
      expected_head_sha: {
        type: 'string',
        pattern: '^[0-9a-f]{40}$',
      },
      message: {
        type: 'string',
        minLength: 1,
        maxLength: 240,
      },
    },
    required: ['operation_id', 'expected_head_sha', 'message'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Studio Git Commit Current Changes',
    readOnlyHint: false,
    destructiveHint: true,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'private-studio-mcp/typed-git': true },
});

export const STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL = Object.freeze({
  name: 'studio_git_push_current_branch',
  title: 'Studio Git Push Current Branch',
  description:
    'Push exactly the current HEAD of one existing clean Mastermind attended Web workspace to its ' +
    'same host-resolved sol/web-* origin branch without force, tags, branch selection or credential input. ' +
    'Requires the caller to fence the action with the exact expected local HEAD. If the remote already ' +
    'equals that HEAD, no push is issued. A failure after push starts is EFFECT_UNKNOWN unless remote ' +
    'readback proves the exact HEAD is applied; never blindly retry an EFFECT_UNKNOWN result. Use ' +
    'studio_git_publish_status to reconcile before any later action.',
  inputSchema: {
    type: 'object',
    properties: {
      operation_id: {
        type: 'string',
        minLength: 1,
        maxLength: 256,
        pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$',
      },
      expected_head_sha: {
        type: 'string',
        pattern: '^[0-9a-f]{40}$',
      },
    },
    required: ['operation_id', 'expected_head_sha'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Studio Git Push Current Branch',
    readOnlyHint: false,
    destructiveHint: true,
    idempotentHint: true,
    openWorldHint: true,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'private-studio-mcp/typed-git': true },
});

export const STUDIO_WEB_COMMISSION_MATERIALIZE_TOOL = Object.freeze({
  name: 'studio_web_commission_materialize',
  title: 'Studio Web Commission Materialize',
  description:
    'Materialize the canonical commission artifact research/executive_commissions/COMMISSION.md inside one ' +
    'existing Mastermind attended Web workspace from a compact commission request. The host resolves the ' +
    'workspace and sol/web-* branch from canonical mmx-workspace registration, and the host-side Mastermind ' +
    'Craft compiler expands the compact request into the complete commission from repository-owned method ' +
    'files. The caller supplies only the operation id and the bounded compact request: the worker transcript, ' +
    'the rendered commission body, shell commands, heredocs, repository, remote, branch, path and force ' +
    'options are all refused. It performs no provider, model, account, credential or host selection, creates ' +
    'no commit and contacts no remote. Identical existing bytes report ALREADY_APPLIED without rewriting, so ' +
    'repeating the call after an uncertain result reconciles by exact digest readback rather than blind retry.',
  inputSchema: {
    type: 'object',
    properties: {
      operation_id: {
        type: 'string',
        minLength: 1,
        maxLength: 256,
        pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$',
      },
      commission: {
        type: 'object',
        description:
          'One compact mastermind.craft_commission_request.v1 object, at most 16384 serialized bytes. ' +
          'The Mastermind Craft compiler owns this schema and refuses unknown, incomplete or ' +
          'routing-bearing fields; this tool never re-interprets or rewrites it.',
        properties: { schema_version: { const: COMMISSION_REQUEST_SCHEMA } },
        required: [...COMMISSION_REQUEST_FIELDS],
      },
    },
    required: ['operation_id', 'commission'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Studio Web Commission Materialize',
    readOnlyHint: false,
    destructiveHint: true,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'private-studio-mcp/typed-git': true },
});

export const STUDIO_GIT_PUBLISH_TOOLS = Object.freeze([
  STUDIO_GIT_PUBLISH_STATUS_TOOL,
  STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL,
  STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL,
]);

function assertExactKeys(value, allowed, label) {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw new TypeError(`${label}.${key} is not supported`);
  }
}

function requireAbsoluteString(value, label) {
  if (typeof value !== 'string' || !value || !path.isAbsolute(value) || value.includes('\0')) {
    throw new TypeError(`${label} must be a non-empty absolute path`);
  }
  return value;
}

function clampTimeout(value, fallback, label) {
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || value < 1 || value > 300_000) {
    throw new TypeError(`${label} must be an integer between 1 and 300000 milliseconds`);
  }
  return value;
}

export function resolveGitPublishConfig(value) {
  if (value === undefined || value === null || value === false) return null;
  if (typeof value === 'object' && value !== null && RESOLVED_CONFIGS.has(value)) return value;
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('config.gitPublish must be an object, false, or absent');
  }
  assertExactKeys(
    value,
    new Set([
      'enabled', 'workspaceCli', 'gitBinary', 'sourceRepository', 'allowedRemoteUrls',
      'commandTimeoutMs', 'pushTimeoutMs',
      'commissionCompiler', 'commissionCompilerInterpreter', 'commissionTimeoutMs',
    ]),
    'config.gitPublish',
  );
  if (value.enabled !== true) {
    throw new TypeError('config.gitPublish.enabled must be true when gitPublish is configured');
  }
  const allowedRemoteUrls = value.allowedRemoteUrls;
  if (!Array.isArray(allowedRemoteUrls) || allowedRemoteUrls.length < 1 || allowedRemoteUrls.length > 8) {
    throw new TypeError('config.gitPublish.allowedRemoteUrls must be a non-empty array of at most 8 URLs');
  }
  const normalizedRemotes = [];
  for (const remote of allowedRemoteUrls) {
    if (typeof remote !== 'string' || !remote || remote.length > 2048 || remote.includes('\0')) {
      throw new TypeError('config.gitPublish.allowedRemoteUrls contains an invalid URL');
    }
    if (normalizedRemotes.includes(remote)) {
      throw new TypeError('config.gitPublish.allowedRemoteUrls contains a duplicate URL');
    }
    normalizedRemotes.push(remote);
  }
  // The Craft commission compiler is an optional host dependency. While it is
  // unprotected, an installation that omits it keeps the typed Git plane fully
  // usable and simply does not advertise commission materialization; nothing
  // here vendors or re-implements that compiler.
  const wantsCommission = value.commissionCompiler !== undefined || value.commissionCompilerInterpreter !== undefined;
  if (!wantsCommission && value.commissionTimeoutMs !== undefined) {
    throw new TypeError(
      'config.gitPublish.commissionTimeoutMs requires commissionCompiler and commissionCompilerInterpreter');
  }
  const commission = wantsCommission
    ? Object.freeze({
      compiler: requireAbsoluteString(value.commissionCompiler, 'config.gitPublish.commissionCompiler'),
      interpreter: requireAbsoluteString(value.commissionCompilerInterpreter, 'config.gitPublish.commissionCompilerInterpreter'),
      timeoutMs: clampTimeout(value.commissionTimeoutMs, DEFAULT_COMMISSION_TIMEOUT_MS, 'config.gitPublish.commissionTimeoutMs'),
    })
    : null;

  const resolved = Object.freeze({
    enabled: true,
    workspaceCli: requireAbsoluteString(value.workspaceCli, 'config.gitPublish.workspaceCli'),
    gitBinary: requireAbsoluteString(value.gitBinary, 'config.gitPublish.gitBinary'),
    sourceRepository: requireAbsoluteString(value.sourceRepository, 'config.gitPublish.sourceRepository'),
    allowedRemoteUrls: Object.freeze(normalizedRemotes),
    lane: ALLOWED_LANE,
    commandTimeoutMs: clampTimeout(value.commandTimeoutMs, DEFAULT_COMMAND_TIMEOUT_MS, 'config.gitPublish.commandTimeoutMs'),
    pushTimeoutMs: clampTimeout(value.pushTimeoutMs, DEFAULT_PUSH_TIMEOUT_MS, 'config.gitPublish.pushTimeoutMs'),
    commission,
  });
  RESOLVED_CONFIGS.add(resolved);
  return resolved;
}

function validateOperationId(value) {
  if (typeof value !== 'string' || !OPERATION_RE.test(value)) {
    throw new TypeError('operation_id is invalid');
  }
  return value;
}

function validateExpectedHead(value) {
  if (typeof value !== 'string' || !SHA_RE.test(value)) {
    throw new TypeError('expected_head_sha is invalid');
  }
  return value;
}

function validateCommitMessage(value) {
  if (typeof value !== 'string') throw new TypeError('message is invalid');
  const text = value.trim();
  if (!text || text.length > 240 || text.includes('\0') || text.includes('\n') || text.includes('\r')) {
    throw new TypeError('message is invalid');
  }
  return text;
}

/**
 * Bound the compact request and pin the exact compiler entry contract. The
 * Craft compiler owns every field-level rule; duplicating them here would
 * create a second compiler, which this adapter must not do.
 */
function serializeCompactCommission(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('commission must be a compact commission request object');
  }
  if (value.schema_version !== COMMISSION_REQUEST_SCHEMA) {
    throw new TypeError('commission.schema_version is not the supported compact commission request schema');
  }
  let serialized;
  try {
    serialized = JSON.stringify(value);
  } catch {
    throw new TypeError('commission is not serializable');
  }
  if (typeof serialized !== 'string') throw new TypeError('commission is not serializable');
  const bytes = Buffer.byteLength(serialized, 'utf8');
  if (bytes < 2 || bytes > MAX_COMMISSION_INPUT_BYTES) {
    throw new TypeError('commission is outside the compact commission request size boundary');
  }
  return serialized;
}

function compilerRefusalToken(error) {
  const stderr = typeof error?.stderr === 'string' ? error.stderr : '';
  const match = stderr.match(/^BRIEF_REFUSED (\S+)/m);
  const token = match?.[1];
  return token && REFUSAL_TOKEN_RE.test(token) ? token : null;
}

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

/**
 * Read an existing commission artifact without following a symlink, so a
 * planted link inside the workspace can never redirect the readback proof.
 */
async function readRegularFile(filePath) {
  const handle = await open(filePath, fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW);
  try {
    const stats = await handle.stat();
    if (!stats.isFile()) throw new Error('commission path is not a regular file');
    if (stats.size > MAX_COMMISSION_OUTPUT_BYTES) throw new Error('commission file exceeds the supported size');
    return await handle.readFile();
  } finally {
    await handle.close();
  }
}

async function writeNewFile(filePath, bytes) {
  const handle = await open(
    filePath,
    fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | fsConstants.O_NOFOLLOW,
    0o644,
  );
  try {
    await handle.writeFile(bytes);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

function parseJson(text, label) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${label} returned invalid JSON`);
  }
  return parsed;
}

function oneLine(value, label) {
  const text = String(value ?? '').trim();
  if (!text || text.includes('\n') || text.includes('\r')) throw new Error(`${label} is invalid`);
  return text;
}

function actionRef(operationId, branch, head) {
  return createHash('sha256')
    .update('mastermind.studio_git_push_current_branch.v1\0')
    .update(operationId).update('\0').update(branch).update('\0').update(head)
    .digest('hex');
}

function commissionActionRef(operationId, branch, commissionSha) {
  return createHash('sha256')
    .update('mastermind.studio_web_commission_materialize.v1\0')
    .update(operationId).update('\0').update(branch).update('\0').update(commissionSha)
    .digest('hex');
}

function commitActionRef(operationId, branch, oldHead, tree, message) {
  return createHash('sha256')
    .update('mastermind.studio_git_commit_current_changes.v1\0')
    .update(operationId).update('\0').update(branch).update('\0').update(oldHead)
    .update('\0').update(tree).update('\0').update(message)
    .digest('hex');
}

function publicStatus(state) {
  return {
    operation_id: state.operationId,
    branch: state.branch,
    local_head_sha: state.localHead,
    remote_head_sha: state.remoteHead,
    clean: state.clean,
    publication_state: state.remoteHead === state.localHead ? 'APPLIED' : (state.remoteHead === null ? 'NOT_APPLIED' : 'DIFFERENT_REMOTE_HEAD'),
    ready_to_push: state.clean && state.remoteHead !== state.localHead,
  };
}

export function createGitPublisher(config, dependencies = {}) {
  const cfg = resolveGitPublishConfig(config);
  if (!cfg) throw new TypeError('git publish is not configured');
  const execFile = dependencies.execFile ?? execFileDefault;
  const realpath = dependencies.realpath ?? realpathDefault;
  const remove = dependencies.rm ?? rm;

  async function run(file, args, { cwd, timeoutMs = cfg.commandTimeoutMs, envExtra = {}, maxBuffer = MAX_STDIO_BYTES } = {}) {
    return execFile(file, args, {
      cwd,
      timeout: timeoutMs,
      maxBuffer,
      encoding: 'utf8',
      env: {
        PATH: '/usr/bin:/bin:/usr/sbin:/sbin',
        HOME: process.env.HOME ?? '',
        USER: process.env.USER ?? '',
        LOGNAME: process.env.LOGNAME ?? '',
        LANG: 'C',
        LC_ALL: 'C',
        GIT_TERMINAL_PROMPT: '0',
        GIT_ASKPASS: '/usr/bin/false',
        SSH_ASKPASS: '/usr/bin/false',
        ...envExtra,
      },
    });
  }

  async function git(cwd, args, options = {}) {
    return run(cfg.gitBinary, args, { cwd, ...options });
  }

  async function gitWithIndex(cwd, args, indexPath, options = {}) {
    return git(cwd, args, { ...options, envExtra: { GIT_INDEX_FILE: indexPath } });
  }

  async function workspace(operationId, { observeRemote = true } = {}) {
    const operation = validateOperationId(operationId);
    const { stdout } = await run(
      cfg.workspaceCli,
      ['status', '--operation-id', operation, '--lane', cfg.lane],
      { timeoutMs: cfg.commandTimeoutMs },
    );
    const result = parseJson(stdout, 'mmx-workspace status');
    const receipt = result?.receipt;
    if (result?.action !== 'status' || !receipt || typeof receipt !== 'object') {
      throw new Error('mmx-workspace status receipt is invalid');
    }
    const receiptSource = requireAbsoluteString(receipt.source_repository, 'workspace source repository');
    const [resolvedReceiptSource, resolvedConfiguredSource] = await Promise.all([
      realpath(receiptSource),
      realpath(cfg.sourceRepository),
    ]);
    if (resolvedReceiptSource !== resolvedConfiguredSource) {
      throw new Error('workspace source repository does not match the configured Mastermind repository');
    }
    const rawWorkspacePath = requireAbsoluteString(receipt.workspace_path, 'workspace receipt path');
    const workspacePath = await realpath(rawWorkspacePath);
    const branch = oneLine(receipt.branch, 'workspace branch');
    if (!BRANCH_RE.test(branch)) throw new Error('workspace branch is outside the sol/web-* publication boundary');

    const [{ stdout: topOut }, { stdout: branchOut }, { stdout: headOut }, { stdout: statusOut }, { stdout: remoteOut }] = await Promise.all([
      git(workspacePath, ['rev-parse', '--show-toplevel']),
      git(workspacePath, ['symbolic-ref', '--quiet', '--short', 'HEAD']),
      git(workspacePath, ['rev-parse', 'HEAD']),
      git(workspacePath, ['status', '--porcelain=v1', '--untracked-files=all']),
      git(workspacePath, ['remote', 'get-url', 'origin']),
    ]);
    const top = await realpath(oneLine(topOut, 'workspace top level'));
    const currentBranch = oneLine(branchOut, 'current branch');
    const localHead = oneLine(headOut, 'local HEAD');
    const remoteUrl = oneLine(remoteOut, 'origin URL');
    if (top !== workspacePath) throw new Error('workspace path is not the Git top level');
    if (currentBranch !== branch) throw new Error('current Git branch does not match mmx-workspace ownership');
    if (!SHA_RE.test(localHead)) throw new Error('local HEAD is invalid');
    if (!cfg.allowedRemoteUrls.includes(remoteUrl)) throw new Error('origin URL is outside the configured Mastermind remote boundary');

    const ref = `refs/heads/${branch}`;
    let remoteHead;
    if (observeRemote) {
      remoteHead = null;
      const { stdout: lsOut } = await git(workspacePath, ['ls-remote', '--heads', 'origin', ref]);
      const lines = String(lsOut ?? '').trim() ? String(lsOut).trim().split(/\r?\n/) : [];
      if (lines.length > 1) throw new Error('origin returned multiple exact branch refs');
      if (lines.length === 1) {
        const match = lines[0].match(/^([0-9a-f]{40})\s+refs\/heads\/(.+)$/);
        if (!match || match[2] !== branch) throw new Error('origin returned an invalid exact branch ref');
        remoteHead = match[1];
      }
    }

    return {
      operationId: operation,
      workspacePath,
      branch,
      localHead,
      ...(observeRemote ? { remoteHead } : {}),
      clean: String(statusOut ?? '') === '',
      remoteUrl,
      ref,
    };
  }

  async function status(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).some((key) => key !== 'operation_id')) {
      throw new TypeError('studio_git_publish_status arguments are invalid');
    }
    return {
      schema: 'mastermind.studio_git_publish_status.v1',
      ...publicStatus(await workspace(args.operation_id)),
    };
  }

  /**
   * Compile one compact commission request through the incumbent host-side
   * Mastermind Craft compiler and place the exact compiled bytes at the
   * canonical commission path inside the already-fenced attended Web
   * workspace. This is an adapter, not a second compiler and not a commission
   * truth store: Craft owns the compact schema and the rendered bytes, the
   * mmx-workspace registration owns repository/branch/workspace identity, and
   * the caller selects none of it.
   */
  async function materializeCommission(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => !['operation_id', 'commission'].includes(key))) {
      throw new TypeError('studio_web_commission_materialize arguments are invalid');
    }
    if (!cfg.commission) throw new TypeError('commission materialization is not configured');
    const operationId = validateOperationId(args.operation_id);
    const compact = serializeCompactCommission(args.commission);
    const before = await workspace(operationId, { observeRemote: false });

    const scratch = await mkdtemp(path.join(tmpdir(), 'studio-commission-'));
    let compiled;
    try {
      const requestPath = path.join(scratch, 'commission-request.json');
      await writeFile(requestPath, compact, { encoding: 'utf8', mode: 0o600 });
      let stdout;
      try {
        // argv only. The compact request travels as a private bounded file, so
        // no commission content ever passes through a shell or a heredoc.
        ({ stdout } = await run(
          cfg.commission.interpreter,
          [cfg.commission.compiler, 'compile-commission', requestPath, '--format', 'json'],
          {
            cwd: scratch,
            timeoutMs: cfg.commission.timeoutMs,
            maxBuffer: MAX_COMMISSION_OUTPUT_BYTES,
            envExtra: { PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1' },
          },
        ));
      } catch (error) {
        const token = compilerRefusalToken(error);
        return {
          schema: 'mastermind.studio_web_commission_result.v1',
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'COMMISSION_COMPILER_REFUSED',
          operation_id: operationId,
          branch: before.branch,
          commission_path: COMMISSION_RELATIVE_PATH,
          ...(token ? { compiler_refusal: token } : {}),
        };
      }
      compiled = parseJson(stdout, 'craft commission compiler');
    } finally {
      // No effect has been admitted yet, so a scratch cleanup failure may still
      // fail this call normally.
      await remove(scratch, { recursive: true, force: true });
    }

    if (!compiled || typeof compiled !== 'object' || Array.isArray(compiled) ||
        compiled.schema_version !== COMMISSION_COMPILATION_SCHEMA) {
      throw new Error('craft commission compiler returned an unsupported result schema');
    }
    for (const [field, expected] of SELECTION_ASSERTIONS) {
      if (compiled[field] !== expected) {
        throw new Error('craft commission compiler reported a selection outside the publication boundary');
      }
    }
    const markdown = compiled.instructions_markdown;
    if (typeof markdown !== 'string' || markdown.length === 0) {
      throw new Error('craft commission compiler returned no commission bytes');
    }
    const declared = compiled.commission_sha256;
    if (typeof declared !== 'string' || !SHA256_RE.test(declared)) {
      throw new Error('craft commission compiler returned an invalid commission digest');
    }
    const bytes = Buffer.from(markdown, 'utf8');
    if (bytes.byteLength > MAX_COMMISSION_OUTPUT_BYTES) {
      throw new Error('compiled commission exceeds the supported artifact size');
    }
    // The digest the compiler publishes must describe the exact bytes it
    // returned, or its receipt cannot be used as publication proof.
    if (sha256(bytes) !== declared) {
      throw new Error('craft commission digest does not match the compiled commission bytes');
    }

    const ref = commissionActionRef(operationId, before.branch, declared);
    // before.workspacePath is already fully resolved, so a symlinked segment on
    // the canonical commission path shows up as a mismatch here. Each segment is
    // checked as it is created, so a redirected ancestor is caught before the
    // next segment is created through it.
    let directory = before.workspacePath;
    for (const segment of COMMISSION_DIR_SEGMENTS) {
      directory = path.join(directory, segment);
      try {
        await mkdir(directory);
      } catch (error) {
        if (error?.code !== 'EEXIST') throw error;
      }
      if (await realpath(directory) !== directory) {
        throw new Error('commission directory escapes the attended Web workspace');
      }
    }
    const target = path.join(directory, COMMISSION_FILE_NAME);

    async function observe(state) {
      let observed = null;
      try {
        observed = await workspace(operationId, { observeRemote: false });
      } catch {
        // A failed workspace readback cannot retract an already-proved effect.
      }
      return {
        schema: 'mastermind.studio_web_commission_result.v1',
        ...state,
        action_ref: ref,
        operation_id: operationId,
        branch: before.branch,
        commission_path: COMMISSION_RELATIVE_PATH,
        commission_sha256: declared,
        commission_bytes: bytes.byteLength,
        ...(observed ? { local_head_sha: observed.localHead, clean: observed.clean } : {}),
      };
    }

    let existing = null;
    try {
      existing = await readRegularFile(target);
    } catch {
      // Absent, unreadable or symlinked: treat as not yet materialized. The
      // fenced rename below replaces whatever entry is currently there.
    }
    if (existing && sha256(existing) === declared) {
      return observe({ status: 'OK', effect_state: 'APPLIED', code: 'ALREADY_APPLIED', written: false });
    }

    const staged = path.join(directory, `.studio-commission-${randomUUID()}.tmp`);
    let renameAttempted = false;
    try {
      await writeNewFile(staged, bytes);
      renameAttempted = true;
      // rename(2) replaces the destination entry atomically and never follows a
      // symlink at the destination, so the artifact is all-or-nothing.
      await rename(staged, target);
    } catch {
      let stray = true;
      try {
        await unlink(staged);
        stray = false;
      } catch {
        // The staged file may never have been created, or may be unremovable.
        try {
          await readRegularFile(staged);
        } catch {
          stray = false;
        }
      }
      let observedBytes = null;
      let readbackFailed = false;
      try {
        observedBytes = await readRegularFile(target);
      } catch {
        readbackFailed = true;
      }
      if (observedBytes && sha256(observedBytes) === declared) {
        // Either the rename landed and only its response was lost, or the exact
        // artifact was already present. Both are a proved applied effect.
        return observe({
          status: 'OK',
          effect_state: 'APPLIED',
          code: renameAttempted ? 'APPLIED_AFTER_AMBIGUOUS_WRITE_RETURN' : 'ALREADY_APPLIED',
          written: false,
        });
      }
      if (readbackFailed && renameAttempted) {
        // The rename may have run and the destination cannot be observed, so the
        // effect stays unknown. Reconcile with a repeat call; never blind-retry.
        return observe({ status: 'UNKNOWN', effect_state: 'EFFECT_UNKNOWN', code: 'COMMISSION_WRITE_UNCERTAIN', written: false });
      }
      // Either staging failed before any rename, or the observed artifact is not
      // this one. The canonical artifact is provably not this commission. Only a
      // staged remnant, if any, still needs a human.
      return observe({
        status: 'REFUSED',
        effect_state: 'NOT_APPLIED',
        code: stray ? 'COMMISSION_WRITE_FAILED_STRAY_STAGED_FILE' : 'COMMISSION_WRITE_FAILED',
        written: false,
        ...(stray ? { stray_staged_path: path.posix.join(...COMMISSION_DIR_SEGMENTS, path.basename(staged)) } : {}),
      });
    }

    let observedBytes;
    try {
      observedBytes = await readRegularFile(target);
    } catch {
      return observe({ status: 'PARTIAL', effect_state: 'APPLIED', code: 'APPLIED_READBACK_FAILED', written: true });
    }
    if (sha256(observedBytes) !== declared) {
      return observe({ status: 'PARTIAL', effect_state: 'APPLIED', code: 'APPLIED_BUT_SUPERSEDED', written: true });
    }
    return observe({ status: 'OK', effect_state: 'APPLIED', code: 'APPLIED', written: true });
  }

  async function commit(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => !['operation_id', 'expected_head_sha', 'message'].includes(key))) {
      throw new TypeError('studio_git_commit_current_changes arguments are invalid');
    }
    const operationId = validateOperationId(args.operation_id);
    const expectedHead = validateExpectedHead(args.expected_head_sha);
    const message = validateCommitMessage(args.message);
    const before = await workspace(operationId, { observeRemote: false });
    if (before.localHead !== expectedHead) {
      return {
        schema: 'mastermind.studio_git_commit_result.v1',
        status: 'REFUSED',
        effect_state: 'NOT_APPLIED',
        code: 'EXPECTED_HEAD_MISMATCH',
        operation_id: operationId,
        branch: before.branch,
        expected_head_sha: expectedHead,
        local_head_sha: before.localHead,
      };
    }

    const scratch = await mkdtemp(path.join(tmpdir(), 'studio-git-commit-'));
    const indexPath = path.join(scratch, 'index');
    let refUpdateAttempted = false;
    try {
      await gitWithIndex(before.workspacePath, ['read-tree', expectedHead], indexPath);
      await gitWithIndex(before.workspacePath, ['add', '-A', '--', '.'], indexPath);
      const { stdout: treeOut } = await gitWithIndex(before.workspacePath, ['write-tree'], indexPath);
      const tree = oneLine(treeOut, 'candidate tree');
      if (!SHA_RE.test(tree)) throw new Error('candidate tree is invalid');
      const { stdout: baseTreeOut } = await git(before.workspacePath, ['rev-parse', `${expectedHead}^{tree}`]);
      const baseTree = oneLine(baseTreeOut, 'base tree');
      const ref = commitActionRef(operationId, before.branch, expectedHead, tree, message);
      if (tree === baseTree) {
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'NO_COMMITTABLE_CHANGES',
          action_ref: ref,
          operation_id: operationId,
          branch: before.branch,
          local_head_sha: expectedHead,
        };
      }

      const { stdout: commitOut } = await gitWithIndex(
        before.workspacePath,
        ['commit-tree', tree, '-p', expectedHead, '-m', message],
        indexPath,
      );
      const commitHead = oneLine(commitOut, 'commit HEAD');
      if (!SHA_RE.test(commitHead)) throw new Error('commit HEAD is invalid');

      async function finishKnownApplied(successCode) {
        let indexSynced = true;
        try {
          // The private index protects the caller from pre-commit staging side
          // effects. Once the fenced ref update is known applied, align the
          // real index with that exact commit without touching the worktree.
          await git(before.workspacePath, ['read-tree', commitHead]);
        } catch {
          indexSynced = false;
        }

        let observed = null;
        try {
          observed = await workspace(operationId, { observeRemote: false });
        } catch {
          // The ref update itself is already known applied. A failed readback
          // cannot turn that known effect into EFFECT_UNKNOWN.
        }
        if (!observed) {
          return {
            schema: 'mastermind.studio_git_commit_result.v1',
            status: 'PARTIAL',
            effect_state: 'APPLIED',
            code: indexSynced ? 'APPLIED_READBACK_FAILED' : 'APPLIED_INDEX_SYNC_AND_READBACK_FAILED',
            action_ref: ref,
            operation_id: operationId,
            branch: before.branch,
            previous_head_sha: expectedHead,
            commit_head_sha: commitHead,
            index_synced: indexSynced,
          };
        }
        const current = observed.localHead === commitHead;
        const complete = current && indexSynced;
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: complete ? 'OK' : 'PARTIAL',
          effect_state: 'APPLIED',
          code: complete ? successCode : (current ? 'APPLIED_INDEX_SYNC_FAILED' : 'APPLIED_BUT_SUPERSEDED'),
          action_ref: ref,
          operation_id: observed.operationId,
          branch: observed.branch,
          previous_head_sha: expectedHead,
          commit_head_sha: commitHead,
          local_head_sha: observed.localHead,
          clean: observed.clean,
          index_synced: indexSynced,
        };
      }

      refUpdateAttempted = true;
      try {
        await git(before.workspacePath, ['update-ref', before.ref, commitHead, expectedHead]);
      } catch {
        try {
          const observed = await workspace(operationId, { observeRemote: false });
          if (observed.localHead === commitHead) {
            return finishKnownApplied('APPLIED_AFTER_AMBIGUOUS_UPDATE_RETURN');
          }
        } catch {
          // Preserve uncertainty from a lost ref-update response.
        }
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'UNKNOWN',
          effect_state: 'EFFECT_UNKNOWN',
          code: 'LOCAL_REF_UPDATE_UNCERTAIN',
          action_ref: ref,
          operation_id: operationId,
          branch: before.branch,
          previous_head_sha: expectedHead,
          commit_head_sha: commitHead,
        };
      }

      return finishKnownApplied('APPLIED');
    } finally {
      try {
        await remove(scratch, { recursive: true, force: true });
      } catch (error) {
        // Before the ref update is admitted, cleanup failure can still fail the
        // operation normally. Once the ref update may have run, however, a
        // scratch cleanup error must never overwrite APPLIED/EFFECT_UNKNOWN
        // source truth with a synthetic NOT_APPLIED gateway precheck result.
        if (!refUpdateAttempted) throw error;
      }
    }
  }

  async function push(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) || Object.keys(args).some((key) => !['operation_id', 'expected_head_sha'].includes(key))) {
      throw new TypeError('studio_git_push_current_branch arguments are invalid');
    }
    const operationId = validateOperationId(args.operation_id);
    const expectedHead = validateExpectedHead(args.expected_head_sha);
    const before = await workspace(operationId);
    const ref = actionRef(operationId, before.branch, expectedHead);

    if (before.localHead !== expectedHead) {
      return {
        schema: 'mastermind.studio_git_push_result.v1',
        status: 'REFUSED',
        effect_state: 'NOT_APPLIED',
        code: 'EXPECTED_HEAD_MISMATCH',
        action_ref: ref,
        ...publicStatus(before),
      };
    }
    if (before.remoteHead === expectedHead) {
      return {
        schema: 'mastermind.studio_git_push_result.v1',
        status: 'OK',
        effect_state: 'APPLIED',
        code: 'ALREADY_APPLIED',
        action_ref: ref,
        push_attempted: false,
        ...publicStatus(before),
      };
    }
    if (!before.clean) {
      return {
        schema: 'mastermind.studio_git_push_result.v1',
        status: 'REFUSED',
        effect_state: 'NOT_APPLIED',
        code: 'WORKSPACE_DIRTY',
        action_ref: ref,
        ...publicStatus(before),
      };
    }

    try {
      await git(
        before.workspacePath,
        // Push the fenced commit object, never mutable HEAD. A concurrent local
        // branch advance after precheck must not widen the authorized remote effect.
        ['push', '--porcelain', 'origin', `${expectedHead}:${before.ref}`],
        { timeoutMs: cfg.pushTimeoutMs },
      );
    } catch (error) {
      try {
        const afterFailure = await workspace(operationId);
        if (afterFailure.remoteHead === expectedHead) {
          return {
            schema: 'mastermind.studio_git_push_result.v1',
            status: 'OK',
            effect_state: 'APPLIED',
            code: 'APPLIED_AFTER_AMBIGUOUS_PUSH_RETURN',
            action_ref: ref,
            push_attempted: true,
            ...publicStatus(afterFailure),
          };
        }
      } catch {
        // The attempted remote write remains ambiguous. Do not replace the
        // original effect uncertainty with a readback failure.
      }
      return {
        schema: 'mastermind.studio_git_push_result.v1',
        status: 'UNKNOWN',
        effect_state: 'EFFECT_UNKNOWN',
        code: 'PUSH_RESULT_UNCERTAIN',
        action_ref: ref,
        push_attempted: true,
        operation_id: operationId,
        branch: before.branch,
        local_head_sha: expectedHead,
      };
    }

    try {
      const after = await workspace(operationId);
      if (after.remoteHead === expectedHead) {
        return {
          schema: 'mastermind.studio_git_push_result.v1',
          status: 'OK',
          effect_state: 'APPLIED',
          code: 'APPLIED',
          action_ref: ref,
          push_attempted: true,
          ...publicStatus(after),
        };
      }
    } catch {
      // A successful push command followed by failed readback is still
      // ambiguous to the caller. Never call it success without exact ref proof.
    }
    return {
      schema: 'mastermind.studio_git_push_result.v1',
      status: 'UNKNOWN',
      effect_state: 'EFFECT_UNKNOWN',
      code: 'POST_PUSH_READBACK_UNCERTAIN',
      action_ref: ref,
      push_attempted: true,
      operation_id: operationId,
      branch: before.branch,
      local_head_sha: expectedHead,
    };
  }

  return Object.freeze({
    status,
    commit,
    push,
    materializeCommission,
    commissionEnabled: Boolean(cfg.commission),
  });
}

export function toolResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
    ...(isError ? { isError: true } : {}),
  };
}
