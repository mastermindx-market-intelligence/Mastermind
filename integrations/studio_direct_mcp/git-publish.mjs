import { createHash } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { mkdtemp, realpath as realpathDefault, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';

const execFileDefault = promisify(execFileCallback);

const OPERATION_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const SHA_RE = /^[0-9a-f]{40}$/;
const BRANCH_RE = /^sol\/web-[A-Za-z0-9._-]+$/;
const ALLOWED_LANE = 'web';
const MAX_STDIO_BYTES = 1024 * 1024;
const DEFAULT_COMMAND_TIMEOUT_MS = 15_000;
const DEFAULT_PUSH_TIMEOUT_MS = 60_000;
const RESOLVED_CONFIGS = new WeakSet();

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
  const resolved = Object.freeze({
    enabled: true,
    workspaceCli: requireAbsoluteString(value.workspaceCli, 'config.gitPublish.workspaceCli'),
    gitBinary: requireAbsoluteString(value.gitBinary, 'config.gitPublish.gitBinary'),
    sourceRepository: requireAbsoluteString(value.sourceRepository, 'config.gitPublish.sourceRepository'),
    allowedRemoteUrls: Object.freeze(normalizedRemotes),
    lane: ALLOWED_LANE,
    commandTimeoutMs: clampTimeout(value.commandTimeoutMs, DEFAULT_COMMAND_TIMEOUT_MS, 'config.gitPublish.commandTimeoutMs'),
    pushTimeoutMs: clampTimeout(value.pushTimeoutMs, DEFAULT_PUSH_TIMEOUT_MS, 'config.gitPublish.pushTimeoutMs'),
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

  async function run(file, args, { cwd, timeoutMs = cfg.commandTimeoutMs, envExtra = {} } = {}) {
    return execFile(file, args, {
      cwd,
      timeout: timeoutMs,
      maxBuffer: MAX_STDIO_BYTES,
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

  return Object.freeze({ status, commit, push });
}

export function toolResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
    ...(isError ? { isError: true } : {}),
  };
}
