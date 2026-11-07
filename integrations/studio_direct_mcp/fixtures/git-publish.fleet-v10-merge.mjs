import { createHash, randomUUID } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { mkdir, mkdtemp, open, readFile, readdir, realpath as realpathDefault, rename, rm, stat, utimes, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';

// Integrated retained publisher journal: no second staged module or store.

// A durable receipt inside the incumbent, registered Git worktree's private gitdir.
// This is publisher evidence, NOT a new retry service, workspace registry, or lease.
// Never expose disk paths, URLs, command output, or credentials through the status tool.
const SCHEMA = 'mastermind.studio_git_publication_receipt.v1';
const RECEIPT_DIR = 'mastermind-studio-publication-receipts';
const SHA = /^[0-9a-f]{40}$/;
const ACTION = /^[0-9a-f]{64}$/;
const MAX_RECEIPTS = 256;
const MAX_RECEIPT_BYTES = 8192;
const STAGES = new Set(['PREPARED', 'DISPATCHING', 'TERMINAL']);
const OUTCOMES = new Set(['APPLIED', 'NOT_APPLIED']);

function hash(value) {
  return createHash('sha256').update(value).digest('hex');
}

function makeWire(value) {
  const body = {...value};
  return JSON.stringify({...body, integrity_sha256: hash(JSON.stringify(body))}) + '\n';
}

function decodeWire(bytes) {
  if (bytes.length > MAX_RECEIPT_BYTES) throw new Error('OVERSIZE_RECEIPT');
  const parsed = JSON.parse(bytes.toString('utf8'));
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('INVALID_RECEIPT');
  const {integrity_sha256, ...body} = parsed;
  if (!ACTION.test(integrity_sha256 || '') || hash(JSON.stringify(body)) !== integrity_sha256) {
    throw new Error('TORN_OR_CHANGED_RECEIPT');
  }
  if (body.schema !== SCHEMA || !STAGES.has(body.stage) ||
      !ACTION.test(body.action_ref || '') || !SHA.test(body.intended_head_sha || '') ||
      (body.expected_remote_head_sha !== null && !SHA.test(body.expected_remote_head_sha || '')) ||
      (body.stage === 'TERMINAL' && !OUTCOMES.has(body.terminal_outcome))) {
    throw new Error('INVALID_RECEIPT_SCHEMA');
  }
  return body;
}

async function syncDirectory(dir) {
  const fd = await open(dir, 'r');
  try { await fd.sync(); } finally { await fd.close(); }
}

async function writeExclusive(file, wire) {
  const fd = await open(file, 'wx', 0o600);
  try { await fd.writeFile(wire, 'utf8'); await fd.sync(); }
  finally { await fd.close(); }
  await syncDirectory(path.dirname(file));
}

async function replaceAtomically(file, wire) {
  const tmp = file + '.' + randomUUID() + '.tmp';
  let own = false;
  try {
    await writeExclusive(tmp, wire);
    own = true;
    await rename(tmp, file);
    own = false;
    await syncDirectory(path.dirname(file));
  } finally {
    if (own) await rm(tmp, {force:true}).catch(() => {});
  }
}

// This implementation deliberately has NO mutating reconciliation endpoint.
// Pre-existing attempts which lack a retained original intent stay UNKNOWN.
export async function createPublicationRecovery({git, workspacePath, operationId, branch, ref, remoteUrl}) {
  const {stdout} = await git(workspacePath, ['rev-parse', '--absolute-git-dir']);
  const gitdir = String(stdout || '').trim();
  if (!path.isAbsolute(gitdir)) throw new Error('INVALID_GITDIR');
  const identity = hash(operationId + '\0' + branch);
  const dir = path.join(gitdir, RECEIPT_DIR, identity);
  const remoteFingerprint = hash(remoteUrl);
  const filename = (actionRef) => {
    if (!ACTION.test(actionRef || '')) throw new TypeError('invalid publication action_ref');
    return path.join(dir, actionRef + '.json');
  };

  async function read(actionRef) {
    try {
      const record = decodeWire(await readFile(filename(actionRef)));
      if (record.operation_id !== operationId || record.branch !== branch ||
          record.target_ref !== ref || record.remote_fingerprint !== remoteFingerprint ||
          record.action_ref !== actionRef) {
        throw new Error('RECEIPT_BINDING_CONFLICT');
      }
      return {record};
    } catch (error) {
      if (error.code === 'ENOENT') return {missing: true};
      return {corrupt: true, error: String(error.message || error)};
    }
  }

  async function allActionRefs() {
    try {
      const names = await readdir(dir);
      if (names.length > MAX_RECEIPTS) throw new Error('RECEIPT_LIMIT_EXCEEDED');
      if (names.some((name) => !ACTION.test(name.replace(/\.json$/, '')) || !name.endsWith('.json'))) {
        throw new Error('UNEXPECTED_RECEIPT_ENTRY');
      }
      return names.map((name) => name.slice(0, -5));
    } catch (error) {
      if (error.code === 'ENOENT') return [];
      throw error;
    }
  }

  async function disposition(actionRef, remoteHead, checkAncestor = true) {
    const found = await read(actionRef);
    if (found.missing) return {action_ref: actionRef, outcome:'UNKNOWN', reason:'NO_MATCHING_OR_LEGACY_RECEIPT', retry_allowed:false};
    if (found.corrupt) return {action_ref: actionRef, outcome:'UNKNOWN', reason:'INVALID_OR_TORN_RECEIPT', retry_allowed:false};
    const r = found.record;
    const base = {
      action_ref: actionRef,
      intended_head_sha: r.intended_head_sha,
      expected_remote_head_sha: r.expected_remote_head_sha,
      stage: r.stage,
      generation_id: r.generation_id,
      retry_allowed: false,
    };
    if (r.stage === 'TERMINAL') {
      return {...base, outcome:r.terminal_outcome, reason:r.terminal_proof,
        current_remote_head_sha:remoteHead};
    }
    // A PREPARED record is explicitly before dispatch. Another valid writer
    // may have published identical bytes; target equality must not falsely
    // attribute that effect to this never-proven publisher invocation.
    if (r.stage === 'PREPARED') {
      return {...base, outcome:'UNKNOWN', reason:'WRITER_MAY_STILL_DISPATCH',
        current_remote_head_sha:remoteHead};
    }
    if (remoteHead === r.intended_head_sha) {
      return {...base, outcome:'APPLIED', reason:'INTENDED_REMOTE_REF_OBSERVED'};
    }
    // A later tip equal to neither preimage nor intended head is NOT proof
    // that a prior attempted push did not happen. Use ancestry only when all
    // needed commit objects are locally present; never fetch or change refs.
    if (remoteHead !== null && remoteHead !== r.expected_remote_head_sha && checkAncestor) {
      try {
        await git(workspacePath, ['merge-base', '--is-ancestor', r.intended_head_sha, remoteHead]);
        return {...base, outcome:'APPLIED', reason:'INTENDED_HEAD_IS_REMOTE_ANCESTOR'};
      } catch (error) {
        if (error.code === 1) {
          return {...base, outcome:'CONFLICT', reason:'REMOTE_DIVERGED_TARGET_NOT_ANCESTOR',
            current_remote_head_sha:remoteHead};
        }
      }
    }
    return {...base, outcome:'UNKNOWN',
      reason:r.stage === 'PREPARED' ? 'WRITER_MAY_STILL_DISPATCH' : 'DISPATCH_OUTCOME_UNPROVEN',
      current_remote_head_sha:remoteHead};
  }

  async function status(actionRef, remoteHead) {
    if (actionRef) return disposition(actionRef, remoteHead);
    const refs = await allActionRefs();
    if (refs.length === 0) return {outcome:'UNKNOWN', reason:'NO_RETAINED_PUBLICATION_RECEIPT', retry_allowed:false};
    const states = await Promise.all(refs.map((id) => disposition(id, remoteHead)));
    const unsafe = states.filter((s) => s.outcome !== 'APPLIED');
    // The status without an action selector prioritizes unresolved effects,
    // not whichever branch tip happens to be newest.
    return unsafe[0] || states.at(-1);
  }

  async function begin({actionRef, intendedHead, expectedRemote}) {
    if (!SHA.test(intendedHead || '') || (expectedRemote !== null && !SHA.test(expectedRemote || ''))) {
      throw new TypeError('invalid publication commit identity');
    }
    const refs = await allActionRefs();
    for (const oldRef of refs) {
      const item = await disposition(oldRef, expectedRemote);
      if (item.outcome !== 'APPLIED') {
        return {blocked:true, reason:'UNRECONCILED_OR_DENIED_PUBLICATION', prior:item};
      }
    }
    if (refs.includes(actionRef)) {
      return {blocked:true, reason:'ALREADY_RECORDED_PUBLICATION', prior:await disposition(actionRef, expectedRemote)};
    }
    const record = {
      schema:SCHEMA, operation_id:operationId, branch, target_ref:ref,
      remote_fingerprint:remoteFingerprint, action_ref:actionRef,
      intended_head_sha:intendedHead, expected_remote_head_sha:expectedRemote,
      stage:'PREPARED', generation_id:String(process.pid) + ':' + randomUUID(),
      created_at:new Date().toISOString(),
    };
    await mkdir(dir, {recursive:true, mode:0o700});
    await writeExclusive(filename(actionRef), makeWire(record));
    return {record};
  }

  // Distinct legacy-only forward progress. This does not claim a missing old
  // action succeeded or failed, and never reuses its action ID. It is valid
  // only when caller has separately qualified source custody and quiescence.
  async function beginForward({actionRef, intendedHead, expectedRemote,
      priorActionRef, priorIntendedHead}) {
    if (!ACTION.test(actionRef || '') || !ACTION.test(priorActionRef || '') ||
        actionRef === priorActionRef || !SHA.test(intendedHead || '') ||
        !SHA.test(expectedRemote || '') || !SHA.test(priorIntendedHead || '')) {
      throw new TypeError('invalid guarded publication recovery identity');
    }
    const refs = await allActionRefs();
    if (refs.includes(actionRef)) {
      return {blocked:true, reason:'ALREADY_RECORDED_PUBLICATION',
        prior:await disposition(actionRef, expectedRemote)};
    }
    // This path is for a pre-journal old action only. A known prior journal
    // with DISPATCHING/PREPARED still demands its exact result/owner fence;
    // an already-terminal prior can use the ordinary current-state path.
    if (refs.includes(priorActionRef)) {
      return {blocked:true, reason:'PRIOR_ACTION_HAS_DURABLE_RECEIPT',
        prior:await disposition(priorActionRef, expectedRemote)};
    }
    for (const oldRef of refs) {
      const item = await disposition(oldRef, expectedRemote);
      if (item.outcome !== 'APPLIED') {
        return {blocked:true, reason:'OTHER_UNRECONCILED_PUBLICATION',
          prior:item};
      }
    }
    const record = {
      schema:SCHEMA, operation_id:operationId, branch, target_ref:ref,
      remote_fingerprint:remoteFingerprint, action_ref:actionRef,
      intended_head_sha:intendedHead, expected_remote_head_sha:expectedRemote,
      prior_action_ref:priorActionRef,
      prior_intended_head_sha:priorIntendedHead,
      recovery_mode:'LEGACY_FORWARD_ONLY',
      stage:'PREPARED', generation_id:String(process.pid) + ':' + randomUUID(),
      created_at:new Date().toISOString(),
    };
    await mkdir(dir, {recursive:true, mode:0o700});
    await writeExclusive(filename(actionRef), makeWire(record));
    return {record};
  }

  async function markDispatching(record) {
    const found = await read(record.action_ref);
    if (!found.record || found.record.stage !== 'PREPARED' ||
        found.record.generation_id !== record.generation_id) {
      throw new Error('PRE_DISPATCH_RECEIPT_CHANGED');
    }
    const next = {...record, stage:'DISPATCHING'};
    await replaceAtomically(filename(record.action_ref), makeWire(next));
    return next;
  }

  async function terminal(record, outcome, proof, observedRemoteHead) {
    if (!OUTCOMES.has(outcome)) throw new TypeError('invalid terminal outcome');
    const found = await read(record.action_ref);
    if (!found.record || found.record.stage !== 'DISPATCHING' ||
        found.record.generation_id !== record.generation_id) throw new Error('DISPATCH_RECEIPT_CHANGED');
    const next = {...record, stage:'TERMINAL', terminal_outcome:outcome,
      terminal_proof:proof, observed_remote_head_sha:observedRemoteHead,
      completed_at:new Date().toISOString()};
    await replaceAtomically(filename(record.action_ref), makeWire(next));
    return next;
  }

  return Object.freeze({status, begin, beginForward, markDispatching, terminal});
}

const execFileDefault = promisify(execFileCallback);

const OPERATION_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
const SHA_RE = /^[0-9a-f]{40}$/;
const SHA256_RE = /^[0-9a-f]{64}$/;
const COMMISSION_PATH = 'research/executive_commissions/COMMISSION.md';
const COMMISSION_COMMIT_MESSAGE = 'chore: prepare Executive commission';
const MAX_COMMISSION_BYTES = 512 * 1024;
const BRANCH_RE = /^sol\/web-[A-Za-z0-9._-]+$/;
const ALLOWED_LANE = 'web';
const CLOSED_REPOSITORY_ALIASES = Object.freeze(['mastermind', 'macro', 'terminal']);
// The installed repository owner fixes these branches; callers select no ref.
const PROTECTED_TRACKING_REFS = Object.freeze({
  mastermind: 'refs/remotes/origin/master', macro: 'refs/remotes/origin/main',
  terminal: 'refs/remotes/origin/master',
});
const NOT_REGISTERED = 'workspace is not registered to the source repository';
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
    'branch HEAD, clean state, and an exact retained publication-action recovery outcome when available. ' +
    'A missing or ambiguous historical receipt remains UNKNOWN and never grants retry. ' +
    'This read-only schema has no capability to create ' +
    'a workspace, commit, push, change a ref, or accept a repository, path, branch, remote, credential, shell command or force option.',
  inputSchema: {
    type: 'object',
    properties: {
      operation_id: {
        type: 'string',
        minLength: 1,
        maxLength: 256,
        pattern: '^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$',
      },
      action_ref: {
        type: 'string',
        pattern: '^[0-9a-f]{64}$',
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
    'single-line commit message, with an optional exact protected-base and prepared-tree merge fence. ' +
    'Merge mode checks the host-fixed local tracking ref and preserves both ordered parents. ' +
    'Ignored files stay uncommitted. A private temporary index prevents ' +
    'pre-commit staging side effects; after the fenced ref update is known applied, the real index is ' +
    'synchronized to that exact commit. Compare-and-swap ref update prevents stale-head publication. ' +
    'This operation is local-only; its schema has no capability to contact origin, push, accept paths, change remotes, or accept shell commands.',
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
      merge: {
        type: 'object',
        properties: {
          expected_protected_base_sha: { type: 'string', pattern: '^[0-9a-f]{40}$' },
          expected_tree_sha: { type: 'string', pattern: '^[0-9a-f]{40}$' },
        },
        required: ['expected_protected_base_sha', 'expected_tree_sha'],
        additionalProperties: false,
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
    'equals that HEAD, no push is issued. Readback of the exact pinned ref proves successful publication. ' +
    'A Git porcelain one-ref rejection with the remote ref unchanged returns NOT_APPLIED for that ref, ' +
    'but never grants retry or alternative-carrier permission; diagnose its unknown cause read-only on ' +
    'the original carrier. All other unresolved push failures remain EFFECT_UNKNOWN and fenced. ' +
    'studio_git_publish_status provides read-only reconciliation.',
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
      recovery: {
        type: 'object',
        description: 'Legacy lost-response recovery only: new forward-only source ref update on the SAME registered workspace/branch after external source-writer and original-process qualification. This cannot replay or settle the old action.',
        properties: {
          prior_action_ref: {type: 'string', pattern: '^[0-9a-f]{64}$'},
          prior_intended_head_sha: {type: 'string', pattern: '^[0-9a-f]{40}$'},
          expected_remote_head_sha: {type: 'string', pattern: '^[0-9a-f]{40}$'},
        },
        required: ['prior_action_ref', 'prior_intended_head_sha', 'expected_remote_head_sha'],
        additionalProperties: false,
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
  if (Object.hasOwn(value, 'repositories')) {
    assertExactKeys(value, new Set([
      'enabled', 'workspaceCli', 'gitBinary', 'repositories',
      'commandTimeoutMs', 'pushTimeoutMs',
    ]), 'config.gitPublish');
    if (value.enabled !== true || !Array.isArray(value.repositories) ||
        value.repositories.length !== CLOSED_REPOSITORY_ALIASES.length) {
      throw new TypeError('config.gitPublish requires the exact closed repository profile');
    }
    const names = new Set();
    const sources = new Set();
    const remotes = new Set();
    const profiles = value.repositories.map((profile) => {
      if (!profile || typeof profile !== 'object' || Array.isArray(profile)) {
        throw new TypeError('repository profile must be an object');
      }
      assertExactKeys(profile, new Set(['repository', 'sourceRepository', 'allowedRemoteUrls']),
        'config.gitPublish.repositories[]');
      if (!CLOSED_REPOSITORY_ALIASES.includes(profile.repository) || names.has(profile.repository)) {
        throw new TypeError('repository profile alias must be unique and closed');
      }
      if (profile.allowedRemoteUrls?.length !== 1 ||
          sources.has(profile.sourceRepository) || remotes.has(profile.allowedRemoteUrls[0])) {
        throw new TypeError('closed repository profile requires distinct source and remote bindings');
      }
      names.add(profile.repository);
      sources.add(profile.sourceRepository);
      remotes.add(profile.allowedRemoteUrls[0]);
      return resolveGitPublishConfig({
        enabled: true,
        workspaceCli: value.workspaceCli,
        gitBinary: value.gitBinary,
        repository: profile.repository,
        sourceRepository: profile.sourceRepository,
        allowedRemoteUrls: profile.allowedRemoteUrls,
        commandTimeoutMs: value.commandTimeoutMs,
        pushTimeoutMs: value.pushTimeoutMs,
      });
    });
    if (!CLOSED_REPOSITORY_ALIASES.every((alias) => names.has(alias))) {
      throw new TypeError('repository profile missing a closed alias');
    }
    const resolved = Object.freeze({
      enabled: true,
      workspaceCli: requireAbsoluteString(value.workspaceCli, 'config.gitPublish.workspaceCli'),
      gitBinary: requireAbsoluteString(value.gitBinary, 'config.gitPublish.gitBinary'),
      commandTimeoutMs: clampTimeout(value.commandTimeoutMs, DEFAULT_COMMAND_TIMEOUT_MS, 'config.gitPublish.commandTimeoutMs'),
      pushTimeoutMs: clampTimeout(value.pushTimeoutMs, DEFAULT_PUSH_TIMEOUT_MS, 'config.gitPublish.pushTimeoutMs'),
      repositories: Object.freeze(CLOSED_REPOSITORY_ALIASES.map((name) =>
        profiles.find((profile) => profile.repository === name))),
    });
    RESOLVED_CONFIGS.add(resolved);
    return resolved;
  }
  assertExactKeys(
    value,
    new Set([
      'enabled', 'workspaceCli', 'gitBinary', 'sourceRepository', 'allowedRemoteUrls',
      'commandTimeoutMs', 'pushTimeoutMs', 'repository',
    ]),
    'config.gitPublish',
  );
  if (value.enabled !== true) {
    throw new TypeError('config.gitPublish.enabled must be true when gitPublish is configured');
  }
  if (value.repository !== undefined && !['mastermind', 'macro', 'terminal'].includes(value.repository)) {
    throw new TypeError('config.gitPublish.repository is not a closed repository alias');
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
    ...(value.repository !== undefined ? { repository: value.repository } : {}),
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

function validateExpectedContentSha256(value) {
  if (typeof value !== 'string' || !SHA256_RE.test(value)) {
    throw new TypeError('expected_content_sha256 is invalid');
  }
  return value;
}

function validateExpectedHead(value) {
  if (typeof value !== 'string' || !SHA_RE.test(value)) {
    throw new TypeError('expected_head_sha is invalid');
  }
  return value;
}

function validateMerge(args) {
  if (!Object.hasOwn(args, 'merge')) return null;
  const value = args.merge;
  const keys = ['expected_protected_base_sha', 'expected_tree_sha'];
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).length !== keys.length ||
      !keys.every((key) => Object.hasOwn(value, key) && typeof value[key] === 'string' && SHA_RE.test(value[key]))) {
    throw new TypeError('merge requires only exact protected-base and tree SHA fences');
  }
  return Object.freeze(Object.fromEntries(keys.map((key) => [key, value[key]])));
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

function forwardRecoveryActionRef(operationId, branch, head, priorActionRef, expectedRemoteHead) {
  return createHash('sha256')
    .update('mastermind.studio_git_forward_recovery.v1\0')
    .update(operationId).update('\0').update(branch).update('\0')
    .update(head).update('\0').update(priorActionRef).update('\0').update(expectedRemoteHead)
    .digest('hex');
}

function commitActionRef(operationId, branch, oldHead, tree, message, protectedBase = null) {
  const hash = createHash('sha256')
    .update(protectedBase === null ? 'mastermind.studio_git_commit_current_changes.v1\0'
      : 'mastermind.studio_git_commit_current_changes.merge.v1\0')
    .update(operationId).update('\0').update(branch).update('\0').update(oldHead);
  if (protectedBase !== null) hash.update('\0').update(protectedBase);
  return hash.update('\0').update(tree).update('\0').update(message).digest('hex');
}

// A rejected *one-ref* push and a lost push response are different effects.
// Inspect only Git's machine-readable porcelain status for this exact pinned
// destination, never untrusted remote prose or a generic exit code.
function explicitlyRejectedExactRef(error, ref) {
  if (error?.code !== 1 || error?.killed === true || error?.signal) return false;
  const output = [error?.stdout, error?.stderr]
    .filter((value) => typeof value === 'string').join('\n');
  return output.split(/\r?\n/).some((line) => {
    const match = line.match(/^!\t([^\t\r\n]+)\t\[remote rejected\](?:\s*\([^\r\n]*\))?\s*$/);
    return match !== null && match[1].endsWith(`:${ref}`);
  });
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

function createClosedRepositoryPublisher(cfg, dependencies) {
  const execFile = dependencies.execFile ?? execFileDefault;
  const publishers = new Map(cfg.repositories.map((profile) =>
    [profile.repository, createGitPublisher(profile, dependencies)]));
  async function select(operationId) {
    const operation = validateOperationId(operationId);
    let selected = null;
    for (const profile of cfg.repositories) {
      let stdout;
      try {
        ({stdout} = await execFile(cfg.workspaceCli,
          ['status', '--operation-id', operation, '--lane', ALLOWED_LANE,
            '--repository', profile.repository],
          {
            timeout: cfg.commandTimeoutMs, maxBuffer: MAX_STDIO_BYTES, encoding: 'utf8',
            env: {
              PATH: '/usr/bin:/bin:/usr/sbin:/sbin',
              HOME: process.env.HOME ?? '',
              USER: process.env.USER ?? '',
              LOGNAME: process.env.LOGNAME ?? '',
              LANG: 'C', LC_ALL: 'C', GIT_TERMINAL_PROMPT: '0',
              GIT_ASKPASS: '/usr/bin/false', SSH_ASKPASS: '/usr/bin/false',
            },
          }));
      } catch (error) {
        // The installed mmx-workspace CLI emits its exact NOT_REGISTERED
        // read-only refusal as JSON on stderr and exits 2. Only this one
        // typed absence is a non-match; every other error remains a refusal.
        if (error?.code !== 2 || String(error.stdout ?? '').trim() ||
            typeof error.stderr !== 'string') throw error;
        const result = parseJson(error.stderr, 'closed mmx-workspace refusal');
        const exactKeys = ['action', 'effect', 'error', 'repository', 'schema_version'];
        if (result?.action === 'status' && result.effect === 'NOT_APPLIED' &&
            result.error === NOT_REGISTERED && result.repository === profile.repository &&
            result.schema_version === 'mastermind.workspace_cli/v2' &&
            Object.keys(result).length === exactKeys.length &&
            exactKeys.every((key) => Object.hasOwn(result, key))) continue;
        throw error;
      }
      const result = parseJson(stdout, 'closed mmx-workspace status');
      if (result?.action !== 'status' ||
          result.schema_version !== 'mastermind.workspace_cli/v2' ||
          result.effect !== 'NOT_APPLIED' || result.repository !== profile.repository) {
        throw new Error('closed workspace registry returned an invalid repository receipt');
      }
      // A successful stdout response can never report absence: only the exit
      // code 2 typed stderr refusal above is canonical non-registration. Any
      // error field here is malformed evidence and fails closed.
      if (result.error !== undefined || !result.receipt || typeof result.receipt !== 'object') {
        throw new Error('closed workspace registry returned an unexpected result');
      }
      if (selected !== null) throw new Error('operation ID is registered in more than one repository');
      selected = publishers.get(profile.repository);
    }
    if (!selected) throw new Error('operation is not registered in the closed repository profile');
    return selected;
  }
  const dispatch = (method) => async (args) => {
    const publisher = await select(args?.operation_id);
    return publisher[method](args);
  };
  return Object.freeze({
    status: dispatch('status'),
    commit: dispatch('commit'),
    push: dispatch('push'),
  });
}

export function createGitPublisher(config, dependencies = {}) {
  const cfg = resolveGitPublishConfig(config);
  if (!cfg) throw new TypeError('git publish is not configured');
  if (cfg.repositories) return createClosedRepositoryPublisher(cfg, dependencies);
  const execFile = dependencies.execFile ?? execFileDefault;
  const realpath = dependencies.realpath ?? realpathDefault;
  const remove = dependencies.rm ?? rm;

  async function run(file, args, { cwd, timeoutMs = cfg.commandTimeoutMs, envExtra = {}, encoding = 'utf8' } = {}) {
    return execFile(file, args, {
      cwd,
      timeout: timeoutMs,
      maxBuffer: MAX_STDIO_BYTES,
      encoding,
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

  async function gitQuiet(cwd, args, options = {}) {
    try {
      await git(cwd, args, options);
      return true;
    } catch (error) {
      if (error?.code === 1) return false;
      throw error;
    }
  }

  async function seedPrivateIndex(workspacePath, indexPath) {
    const {stdout} = await git(workspacePath, ['rev-parse', '--git-path', 'index']);
    const realIndexPath = path.resolve(workspacePath, oneLine(stdout, 'real index path'));
    // Bind bytes and metadata to one inode even if Git replaces the pathname.
    // The existing real-index byte comparisons still fence concurrent writers.
    const source = await open(realIndexPath, 'r');
    let originalIndex;
    let originalMtimeNs;
    try {
      originalMtimeNs = (await source.stat({bigint: true})).mtimeNs;
      originalIndex = await source.readFile();
    } finally {
      await source.close();
    }

    // A newer copy can hide a same-size edit in a racily clean cached entry.
    // Floor integer nanoseconds before conversion so floating-point rounding
    // cannot advance the private index into the following second.
    const nsPerSecond = 1_000_000_000n;
    let seconds = originalMtimeNs / nsPerSecond;
    if (originalMtimeNs < 0n && originalMtimeNs % nsPerSecond !== 0n) seconds -= 1n;
    const timestamp = Number(seconds);
    if (!Number.isSafeInteger(timestamp)) {
      throw new Error('real index timestamp is outside the supported range');
    }
    await writeFile(indexPath, originalIndex);
    await utimes(indexPath, timestamp, timestamp);
    if ((await stat(indexPath, {bigint: true})).mtimeNs > originalMtimeNs) {
      throw new Error('private index timestamp advanced during preparation');
    }
    return {realIndexPath, originalIndex};
  }

  async function syncRealIndex(realIndexPath, originalIndex, stagedIndexPath) {
    // read-tree after a successful commit also destroys sparse skip-worktree
    // metadata. The private staged index already encodes the exact committed
    // tree; install those bytes with Git's normal exclusive index.lock protocol.
    // Never clobber a concurrent index writer. A sync failure after update-ref
    // is APPLIED/PARTIAL, never a denial or replay of the committed ref.
    const lockPath = realIndexPath + '.lock';
    let handle = null;
    let ownsLock = false;
    try {
      handle = await open(lockPath, 'wx', 0o600);
      ownsLock = true;
      if (!(await readFile(realIndexPath)).equals(originalIndex)) {
        throw new Error('real index changed before post-commit synchronization');
      }
      const stagedIndex = await readFile(stagedIndexPath);
      await handle.writeFile(stagedIndex);
      await handle.sync();
      await handle.close();
      handle = null;
      await rename(lockPath, realIndexPath);
      ownsLock = false;
    } finally {
      if (handle !== null) await handle.close().catch(() => {});
      // A failed exclusive open never grants ownership of someone else's lock.
      if (ownsLock) await rm(lockPath, {force: true}).catch(() => {});
    }
  }

  async function verifyDestinationBinding(binding) {
    const {workspacePath, remoteUrl, gitArgs} = binding;
    for (const mode of [[], ['--push']]) {
      const {stdout} = await git(workspacePath, [...gitArgs, 'remote', 'get-url', ...mode, '--all', 'origin']);
      if (oneLine(stdout, 'pinned origin destination') !== remoteUrl) {
        throw new Error('pinned origin destination changed or was rewritten');
      }
    }
  }

  async function captureDestination(workspacePath, branch) {
    const {stdout} = await git(workspacePath, ['remote', 'get-url', '--push', '--all', 'origin']);
    const remoteUrl = oneLine(stdout, 'complete effective push destination');
    if (!cfg.allowedRemoteUrls.includes(remoteUrl)) {
      throw new Error('effective push destination is outside the configured Mastermind remote boundary');
    }
    // Empty values clear inherited URL lists, then bind one destination for
    // both push and readback. Keep origin identity, hooks, credentials and all
    // unrelated repository controls; never persist a config change.
    const gitArgs = Object.freeze([
      '-c', 'remote.origin.url=', '-c', `remote.origin.url=${remoteUrl}`,
      '-c', 'remote.origin.pushurl=', '-c', `remote.origin.pushurl=${remoteUrl}`,
      // Git applies remote.mirror after parsing --no-mirror; constrain both.
      '-c', 'remote.origin.mirror=false',
    ]);
    const binding = Object.freeze({workspacePath, branch, remoteUrl, gitArgs});
    await verifyDestinationBinding(binding);
    return binding;
  }

  async function boundedSubmodulePolicy(workspacePath) {
    async function value(key, boolean = false) {
      try {
        const {stdout} = await git(workspacePath, ['config', ...(boolean ? ['--bool'] : []), '--get', key]);
        return String(stdout).trim();
      } catch (error) {
        if (error.code === 1) return null;
        throw error;
      }
    }
    const pushPolicy = await value('push.recurseSubmodules');
    if (pushPolicy === 'check') return 'check';
    if (pushPolicy === 'no' || pushPolicy === 'false') return 'no';
    if (pushPolicy !== null) {
      throw new Error('submodule-pushing policy is outside the one-repository publication boundary');
    }
    if (await value('submodule.recurse', true) === 'true') {
      throw new Error('recursive submodule policy requires explicit non-pushing publication policy');
    }
    return 'no';
  }

  async function workspace(operationId, { observeRemote = true, remoteBinding = null } = {}) {
    const operation = validateOperationId(operationId);
    const { stdout } = await run(
      cfg.workspaceCli,
      ['status', '--operation-id', operation, '--lane', cfg.lane,
        ...(cfg.repository === undefined ? [] : ['--repository', cfg.repository])],
      { timeoutMs: cfg.commandTimeoutMs },
    );
    const result = parseJson(stdout, 'mmx-workspace status');
    if (cfg.repository !== undefined && (result?.schema_version !== 'mastermind.workspace_cli/v2' ||
        result?.repository !== cfg.repository || result?.effect !== 'NOT_APPLIED')) {
      throw new Error('workspace repository binding does not match the selected repository');
    }
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
    if (cfg.repository !== undefined && branch !== `sol/web-${operation.toLowerCase()}`) {
      throw new Error('workspace repository binding has a foreign operation branch');
    }

    // Avoid the high-level status refresh on very large linked worktrees.
    // These three read-only probes preserve the same repository/global ignore,
    // attribute and filter semantics as commit while optional locks prevent
    // observation from rewriting the shared index.
    const observationOptions = Object.freeze({envExtra: {GIT_OPTIONAL_LOCKS: '0'}});
    const [
      { stdout: topOut }, { stdout: branchOut }, { stdout: headOut },
      worktreeClean, indexClean, { stdout: untrackedOut }, { stdout: remoteOut },
    ] = await Promise.all([
      git(workspacePath, ['rev-parse', '--show-toplevel']),
      git(workspacePath, ['symbolic-ref', '--quiet', '--short', 'HEAD']),
      git(workspacePath, ['rev-parse', 'HEAD']),
      gitQuiet(workspacePath, ['diff-files', '--quiet', '--'], observationOptions),
      gitQuiet(workspacePath, ['diff-index', '--cached', '--quiet', 'HEAD', '--'], observationOptions),
      git(workspacePath, ['ls-files', '--others', '--exclude-standard', '-z'], observationOptions),
      remoteBinding ? Promise.resolve({stdout: remoteBinding.remoteUrl}) : git(workspacePath, ['remote', 'get-url', 'origin']),
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
    let binding;
    if (observeRemote) {
      binding = remoteBinding ?? await captureDestination(workspacePath, branch);
      if (binding.workspacePath !== workspacePath || binding.branch !== branch) {
        throw new Error('original publication destination lost its workspace or branch binding');
      }
      await verifyDestinationBinding(binding);
      remoteHead = null;
      const { stdout: lsOut } = await git(workspacePath, [...binding.gitArgs, 'ls-remote', '--heads', 'origin', ref]);
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
      ...(observeRemote ? { remoteHead, remoteBinding: binding } : {}),
      clean: worktreeClean && indexClean && String(untrackedOut ?? '') === '',
      remoteUrl,
      ref,
    };
  }


  async function committedCommissionDigest(workspacePath, revision) {
    const {stdout: entryOut} = await git(workspacePath, ['ls-tree', revision, '--', COMMISSION_PATH]);
    const entry = String(entryOut ?? '').trim();
    const match = entry.match(/^100644 blob ([0-9a-f]{40})\tresearch\/executive_commissions\/COMMISSION\.md$/);
    if (!match) return null;
    const blob = match[1];
    const {stdout: sizeOut} = await git(workspacePath, ['cat-file', '-s', blob]);
    const size = Number(oneLine(sizeOut, 'commission blob size'));
    if (!Number.isSafeInteger(size) || size < 0 || size > MAX_COMMISSION_BYTES) return null;
    const {stdout: blobBytes} = await run(cfg.gitBinary, ['cat-file', 'blob', blob], {
      cwd: workspacePath, encoding: 'buffer',
    });
    if (!Buffer.isBuffer(blobBytes) || blobBytes.length !== size) throw new Error('commission blob read is invalid');
    return createHash('sha256').update(blobBytes).digest('hex');
  }

  // Internal-only, read-only reconciliation record. It is deliberately absent
  // from STUDIO_GIT_PUBLISH_TOOLS and does not disclose document bytes or paths.
  async function commissionStatus(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => key !== 'operation_id')) {
      throw new TypeError('internal commission status arguments are invalid');
    }
    const observed = await workspace(args.operation_id);
    const contentSha256 = await committedCommissionDigest(observed.workspacePath, observed.localHead);
    return {
      schema: 'mastermind.studio_git_commission_status.v1',
      operation_id: observed.operationId,
      branch: observed.branch,
      local_head_sha: observed.localHead,
      remote_head_sha: observed.remoteHead,
      clean: observed.clean,
      ...(contentSha256 === null ? {} : {commission_content_sha256: contentSha256}),
    };
  }

  async function status(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => !['operation_id', 'action_ref'].includes(key)) ||
        (args.action_ref !== undefined && !SHA256_RE.test(args.action_ref))) {
      throw new TypeError('studio_git_publish_status arguments are invalid');
    }
    const observed = await workspace(args.operation_id);
    const recovery = await createPublicationRecovery({
      git, workspacePath:observed.workspacePath, operationId:observed.operationId,
      branch:observed.branch, ref:observed.ref, remoteUrl:observed.remoteUrl,
    });
    return {
      schema:'mastermind.studio_git_publish_status.v1',
      ...publicStatus(observed),
      publication_recovery:await recovery.status(args.action_ref, observed.remoteHead),
    };
  }

  async function commit(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => !['operation_id', 'expected_head_sha', 'message', 'merge'].includes(key))) {
      throw new TypeError('studio_git_commit_current_changes arguments are invalid');
    }
    const operationId = validateOperationId(args.operation_id);
    const expectedHead = validateExpectedHead(args.expected_head_sha);
    const message = validateCommitMessage(args.message);
    const merge = validateMerge(args);
    const before = await workspace(operationId, { observeRemote: false });
    const refuseMerge = (code) => ({
      schema: 'mastermind.studio_git_commit_result.v1', status: 'REFUSED', effect_state: 'NOT_APPLIED',
      code, operation_id: operationId, branch: before.branch, local_head_sha: before.localHead,
    });
    const protectedRef = PROTECTED_TRACKING_REFS[cfg.repository ?? 'mastermind'];
    async function protectedBaseMatches() {
      try {
        const { stdout } = await git(before.workspacePath, ['rev-parse', '--verify', `${protectedRef}^{commit}`]);
        return oneLine(stdout, 'protected tracking commit') === merge.expected_protected_base_sha;
      } catch { return false; }
    }
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

    if (merge !== null) {
      if (!(await protectedBaseMatches())) return refuseMerge('PROTECTED_BASE_MISMATCH_OR_UNAVAILABLE');
      if (merge.expected_protected_base_sha === expectedHead) return refuseMerge('DUPLICATE_MERGE_PARENT');
      try {
        await git(before.workspacePath, ['merge-base', '--is-ancestor', merge.expected_protected_base_sha, expectedHead]);
        return refuseMerge('PROTECTED_BASE_ALREADY_CONTAINED');
      } catch (error) {
        if (error.code !== 1) throw error;
      }
      try {
        const { stdout } = await git(before.workspacePath, ['merge-base', expectedHead, merge.expected_protected_base_sha]);
        if (!SHA_RE.test(oneLine(stdout, 'shared merge base'))) return refuseMerge('PROTECTED_BASE_NOT_RELATED');
      } catch { return refuseMerge('PROTECTED_BASE_NOT_RELATED'); }
    }

    const scratch = await mkdtemp(path.join(tmpdir(), 'studio-git-commit-'));
    const indexPath = path.join(scratch, 'index');
    let refUpdateAttempted = false;
    try {
      // read-tree into a fresh GIT_INDEX_FILE loses linked-worktree sparse
      // skip-worktree metadata. On a large sparse checkout that produces
      // phantom deletions and makes git add -A exceed its bounded timeout.
      // Snapshot the actual index into the private staging index instead.
      // Neither the real index nor the source ref is modified at this step.
      const {realIndexPath, originalIndex} = await seedPrivateIndex(before.workspacePath, indexPath);
      await gitWithIndex(before.workspacePath, ['add', '-A', '--', '.'], indexPath);
      const { stdout: treeOut } = await gitWithIndex(before.workspacePath, ['write-tree'], indexPath);
      const tree = oneLine(treeOut, 'candidate tree');
      if (!SHA_RE.test(tree)) throw new Error('candidate tree is invalid');
      // A competing index writer must not be silently overwritten. The
      // original source ref is still untouched, so this refusal is NOT_APPLIED.
      if (!(await readFile(realIndexPath)).equals(originalIndex)) {
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'REAL_INDEX_CHANGED_DURING_PREPARATION',
          operation_id: operationId,
          branch: before.branch,
          local_head_sha: expectedHead,
        };
      }
      const { stdout: baseTreeOut } = await git(before.workspacePath, ['rev-parse', `${expectedHead}^{tree}`]);
      const baseTree = oneLine(baseTreeOut, 'base tree');
      if (merge !== null && tree !== merge.expected_tree_sha) return refuseMerge('EXPECTED_TREE_MISMATCH');
      const ref = commitActionRef(operationId, before.branch, expectedHead, tree, message,
        merge?.expected_protected_base_sha ?? null);
      if (tree === baseTree && merge === null) {
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
        ['commit-tree', tree, '-p', expectedHead,
          ...(merge === null ? [] : ['-p', merge.expected_protected_base_sha]), '-m', message],
        indexPath,
      );
      const commitHead = oneLine(commitOut, 'commit HEAD');
      if (!SHA_RE.test(commitHead)) throw new Error('commit HEAD is invalid');
      if (merge !== null) {
        const { stdout } = await git(before.workspacePath, ['show', '-s', '--format=%T%n%P', commitHead]);
        const identity = stdout.trim().split('\n');
        if (identity.length !== 2 || identity[0] !== tree ||
            identity[1] !== `${expectedHead} ${merge.expected_protected_base_sha}`) {
          return refuseMerge('MERGE_COMMIT_IDENTITY_MISMATCH');
        }
        // A concurrent source refresh requires a new explicit reviewed fence.
        if (!(await protectedBaseMatches())) return refuseMerge('PROTECTED_BASE_CHANGED_DURING_PREPARATION');
      }

      async function finishKnownApplied(successCode) {
        let indexSynced = true;
        try {
          // The private index protects the caller from pre-commit staging side
          // effects. Once the fenced ref update is known applied, align the
          // real index with that exact commit without touching the worktree.
          await syncRealIndex(realIndexPath, originalIndex, indexPath);
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
            return await finishKnownApplied('APPLIED_AFTER_AMBIGUOUS_UPDATE_RETURN');
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

      return await finishKnownApplied('APPLIED');
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


  // Internal-only fixed-path primitive for the commissioned preparation endpoint.
  // It is deliberately absent from STUDIO_GIT_PUBLISH_TOOLS and accepts no path,
  // branch, remote, repository, or command selector.
  async function commitCommission(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => !['operation_id', 'expected_head_sha', 'expected_content_sha256'].includes(key))) {
      throw new TypeError('internal commission commit arguments are invalid');
    }
    const operationId = validateOperationId(args.operation_id);
    const expectedHead = validateExpectedHead(args.expected_head_sha);
    const expectedContentSha256 = validateExpectedContentSha256(args.expected_content_sha256);
    const message = COMMISSION_COMMIT_MESSAGE;
    const before = await workspace(operationId, { observeRemote: false });
    if (before.localHead !== expectedHead) {
      return {
        schema: 'mastermind.studio_git_commit_result.v1',
        status: 'REFUSED', effect_state: 'NOT_APPLIED', code: 'EXPECTED_HEAD_MISMATCH',
        operation_id: operationId, branch: before.branch,
        expected_head_sha: expectedHead, local_head_sha: before.localHead,
      };
    }

    const {stdout: statusOut} = await git(before.workspacePath,
      ['status', '--porcelain=v1', '--untracked-files=all']);
    const statusLines = String(statusOut ?? '').split(/\r?\n/).filter(Boolean);
    if (statusLines.length !== 1 || statusLines[0].slice(3) !== COMMISSION_PATH) {
      return {
        schema: 'mastermind.studio_git_commit_result.v1',
        status: 'REFUSED', effect_state: 'NOT_APPLIED', code: 'FOREIGN_WORKTREE_CHANGES',
        operation_id: operationId, branch: before.branch, local_head_sha: expectedHead,
      };
    }

    const scratch = await mkdtemp(path.join(tmpdir(), 'studio-git-commission-'));
    const indexPath = path.join(scratch, 'index');
    let refUpdateAttempted = false;
    let commitHead = null;
    let ref = null;
    try {
      const {realIndexPath, originalIndex} = await seedPrivateIndex(before.workspacePath, indexPath);
      await gitWithIndex(before.workspacePath, ['add', '--', COMMISSION_PATH], indexPath);
      const {stdout: treeOut} = await gitWithIndex(before.workspacePath, ['write-tree'], indexPath);
      const tree = oneLine(treeOut, 'commission candidate tree');
      if (!SHA_RE.test(tree)) throw new Error('commission candidate tree is invalid');
      ref = commitActionRef(operationId, before.branch, expectedHead, tree, message);

      const {stdout: pathsOut} = await git(before.workspacePath,
        ['diff-tree', '--no-commit-id', '--name-only', '-r', expectedHead, tree]);
      if (String(pathsOut ?? '').trim() !== COMMISSION_PATH) {
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'REFUSED', effect_state: 'NOT_APPLIED', code: 'COMMISSION_PATHSET_MISMATCH',
          action_ref: ref, operation_id: operationId, branch: before.branch,
          local_head_sha: expectedHead,
        };
      }
      const actualContentSha256 = await committedCommissionDigest(before.workspacePath, tree);
      if (actualContentSha256 === null) {
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'REFUSED', effect_state: 'NOT_APPLIED', code: 'COMMISSION_ENTRY_NOT_REGULAR_BLOB',
          action_ref: ref, operation_id: operationId, branch: before.branch,
          local_head_sha: expectedHead,
        };
      }
      if (actualContentSha256 !== expectedContentSha256) {
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'REFUSED', effect_state: 'NOT_APPLIED', code: 'COMMISSION_CONTENT_SHA256_MISMATCH',
          action_ref: ref, operation_id: operationId, branch: before.branch,
          local_head_sha: expectedHead,
        };
      }

      if (!(await readFile(realIndexPath)).equals(originalIndex)) {
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'REFUSED', effect_state: 'NOT_APPLIED',
          code: 'REAL_INDEX_CHANGED_DURING_PREPARATION',
          operation_id: operationId, branch: before.branch, local_head_sha: expectedHead,
        };
      }
      const {stdout: commitOut} = await gitWithIndex(before.workspacePath,
        ['commit-tree', tree, '-p', expectedHead, '-m', message], indexPath);
      commitHead = oneLine(commitOut, 'commission commit HEAD');
      if (!SHA_RE.test(commitHead)) throw new Error('commission commit HEAD is invalid');

      refUpdateAttempted = true;
      try {
        await git(before.workspacePath, ['update-ref', before.ref, commitHead, expectedHead]);
      } catch {
        try {
          if ((await workspace(operationId, {observeRemote: false})).localHead === commitHead) {
            return await finishCommissionApplied('APPLIED_AFTER_AMBIGUOUS_UPDATE_RETURN');
          }
        } catch { /* retain uncertainty */ }
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: 'UNKNOWN', effect_state: 'EFFECT_UNKNOWN', code: 'LOCAL_REF_UPDATE_UNCERTAIN',
          action_ref: ref, operation_id: operationId, branch: before.branch,
          previous_head_sha: expectedHead, commit_head_sha: commitHead,
        };
      }
      return await finishCommissionApplied('APPLIED');

      async function finishCommissionApplied(successCode) {
        let indexSynced = true;
        try { await syncRealIndex(realIndexPath, originalIndex, indexPath); } catch { indexSynced = false; }
        let observed = null;
        try { observed = await workspace(operationId, {observeRemote: false}); } catch { /* known applied */ }
        if (!observed) {
          return {
            schema: 'mastermind.studio_git_commit_result.v1',
            status: 'PARTIAL', effect_state: 'APPLIED',
            code: indexSynced ? 'APPLIED_READBACK_FAILED' : 'APPLIED_INDEX_SYNC_AND_READBACK_FAILED',
            action_ref: ref, operation_id: operationId, branch: before.branch,
            previous_head_sha: expectedHead, commit_head_sha: commitHead, index_synced: indexSynced,
          };
        }
        const current = observed.localHead === commitHead;
        return {
          schema: 'mastermind.studio_git_commit_result.v1',
          status: current && indexSynced ? 'OK' : 'PARTIAL', effect_state: 'APPLIED',
          code: current && indexSynced ? successCode : (current ? 'APPLIED_INDEX_SYNC_FAILED' : 'APPLIED_BUT_SUPERSEDED'),
          action_ref: ref, operation_id: observed.operationId, branch: observed.branch,
          previous_head_sha: expectedHead, commit_head_sha: commitHead,
          local_head_sha: observed.localHead, clean: observed.clean, index_synced: indexSynced,
        };
      }
    } finally {
      try { await remove(scratch, {recursive: true, force: true}); }
      catch (error) { if (!refUpdateAttempted) throw error; }
    }
  }

  async function push(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) => !['operation_id', 'expected_head_sha', 'recovery'].includes(key))) {
      throw new TypeError('studio_git_push_current_branch arguments are invalid');
    }
    const operationId = validateOperationId(args.operation_id);
    const expectedHead = validateExpectedHead(args.expected_head_sha);
    const forward = args.recovery !== undefined;
    if (forward && (!args.recovery || typeof args.recovery !== 'object' ||
        Array.isArray(args.recovery) || Object.keys(args.recovery).some((key) =>
          !['prior_action_ref', 'prior_intended_head_sha', 'expected_remote_head_sha'].includes(key)))) {
      throw new TypeError('studio_git_push_current_branch recovery arguments are invalid');
    }
    if (forward && (!SHA256_RE.test(args.recovery.prior_action_ref || '') ||
        !SHA_RE.test(args.recovery.prior_intended_head_sha || '') ||
        !SHA_RE.test(args.recovery.expected_remote_head_sha || ''))) {
      throw new TypeError('studio_git_push_current_branch recovery identities are invalid');
    }
    const before = await workspace(operationId);
    const ref = forward
      ? forwardRecoveryActionRef(operationId, before.branch, expectedHead,
          args.recovery.prior_action_ref, args.recovery.expected_remote_head_sha)
      : actionRef(operationId, before.branch, expectedHead);
    if (before.localHead !== expectedHead) {
      return {
        schema:'mastermind.studio_git_push_result.v1', status:'REFUSED',
        effect_state:'NOT_APPLIED', code:'EXPECTED_HEAD_MISMATCH',
        action_ref:ref, ...publicStatus(before),
      };
    }
    if (before.remoteHead === expectedHead) {
      return {
        schema:'mastermind.studio_git_push_result.v1', status:'OK',
        effect_state:'APPLIED', code:'ALREADY_APPLIED',
        action_ref:ref, push_attempted:false, ...publicStatus(before),
      };
    }
    if (!before.clean) {
      return {
        schema:'mastermind.studio_git_push_result.v1', status:'REFUSED',
        effect_state:'NOT_APPLIED', code:'WORKSPACE_DIRTY',
        action_ref:ref, ...publicStatus(before),
      };
    }

    if (forward) {
      // No attempt to infer a legacy action's outcome from a missing journal.
      // The explicit prior identity must be the original tool's deterministic
      // action ID for the same operation/ref and immutable intended commit.
      const prior = args.recovery;
      const fail = (code) => ({
        schema:'mastermind.studio_git_push_result.v1', status:'REFUSED',
        effect_state:'NOT_APPLIED', code, action_ref:ref, push_attempted:false,
        retry_allowed:false, prior_action_ref:prior.prior_action_ref,
        ...publicStatus(before), ready_to_push:false,
      });
      if (prior.prior_action_ref !== actionRef(operationId, before.branch, prior.prior_intended_head_sha)) {
        return fail('RECOVERY_PRIOR_IDENTITY_MISMATCH');
      }
      if (before.remoteHead === null ||
          before.remoteHead !== prior.expected_remote_head_sha) {
        return fail('RECOVERY_REMOTE_HEAD_MISMATCH');
      }
      // Both ancestors must be locally present. No implicit fetch, history
      // rewrite, branch creation, or non-fast-forward fallback is authorized.
      if (!await gitQuiet(before.workspacePath,
          ['merge-base', '--is-ancestor', prior.prior_intended_head_sha, expectedHead]) ||
          !await gitQuiet(before.workspacePath,
            ['merge-base', '--is-ancestor', before.remoteHead, expectedHead])) {
        return fail('RECOVERY_ANCESTRY_UNVERIFIED');
      }
      // Reobserve the same owner/remote immediately before journaling. A race
      // after this snapshot remains bounded by Git's non-forced ref update.
      const fresh = await workspace(operationId, {remoteBinding:before.remoteBinding});
      if (fresh.remoteHead !== before.remoteHead || fresh.localHead !== expectedHead ||
          !fresh.clean) return fail('RECOVERY_STALE_PREFLIGHT');
    }

    const submodulePolicy = await boundedSubmodulePolicy(before.workspacePath);
    await verifyDestinationBinding(before.remoteBinding);
    let journal;
    let dispatch;
    try {
      journal = await createPublicationRecovery({
        git, workspacePath:before.workspacePath, operationId, branch:before.branch,
        ref:before.ref, remoteUrl:before.remoteUrl,
      });
      // All prior actions for this exact workspace are checked before any push.
      // A changed remote is not evidence of nonapplication of an old effect.
      const opening = forward
        ? await journal.beginForward({
            actionRef:ref, intendedHead:expectedHead, expectedRemote:before.remoteHead,
            priorActionRef:args.recovery.prior_action_ref,
            priorIntendedHead:args.recovery.prior_intended_head_sha,
          })
        : await journal.begin({
            actionRef:ref, intendedHead:expectedHead, expectedRemote:before.remoteHead,
          });
      if (opening.blocked) {
        return {
          schema:'mastermind.studio_git_push_result.v1', status:'REFUSED',
          effect_state:'EFFECT_UNKNOWN', code:opening.reason,
          action_ref:ref, retry_allowed:false, push_attempted:false,
          prior_recovery:opening.prior, ...publicStatus(before),
          ready_to_push:false,
        };
      }
      // The durable DISPATCHING receipt MUST predate any external Git command.
      // If this transition fails, the push never begins on this invocation.
      dispatch = await journal.markDispatching(opening.record);
    } catch {
      return {
        schema:'mastermind.studio_git_push_result.v1', status:'REFUSED',
        effect_state:'NOT_APPLIED', code:'RECOVERY_RECEIPT_PRE_DISPATCH_FAILED',
        action_ref:ref, push_attempted:false, retry_allowed:false,
        ...publicStatus(before), ready_to_push:false,
      };
    }

    async function saveTerminal(outcome, proof, remoteHead) {
      try {
        await journal.terminal(dispatch, outcome, proof, remoteHead);
        return true;
      } catch {
        // A known ref disposition remains known to this caller. The durable
        // DISPATCHING record remains fail-closed after an incomplete terminal write.
        return false;
      }
    }

    try {
      await git(before.workspacePath,
        // Never push mutable HEAD: the original fenced commit and exact ref only.
        [...before.remoteBinding.gitArgs, 'push', '--porcelain', '--no-follow-tags',
          '--no-force', '--no-mirror', '--recurse-submodules=' + submodulePolicy,
          'origin', expectedHead + ':' + before.ref],
        {timeoutMs:cfg.pushTimeoutMs});
    } catch (error) {
      try {
        const afterFailure = await workspace(operationId, {remoteBinding:before.remoteBinding});
        if (afterFailure.remoteHead === expectedHead) {
          const saved = await saveTerminal('APPLIED', 'REMOTE_EXACT_AFTER_LOST_RETURN', afterFailure.remoteHead);
          return {
            schema:'mastermind.studio_git_push_result.v1', status:'OK',
            effect_state:'APPLIED', code:'APPLIED_AFTER_AMBIGUOUS_PUSH_RETURN',
            action_ref:ref, push_attempted:true, receipt_recorded:saved,
            ...publicStatus(afterFailure),
          };
        }
        if (explicitlyRejectedExactRef(error, before.ref) &&
            afterFailure.remoteHead === before.remoteHead) {
          const saved = await saveTerminal('NOT_APPLIED', 'EXACT_REF_REJECTED_UNCHANGED', afterFailure.remoteHead);
          return {
            schema:'mastermind.studio_git_push_result.v1', status:'REFUSED',
            effect_state:'NOT_APPLIED', code:'REMOTE_REF_REJECTED_UNCHANGED',
            action_ref:ref, push_attempted:true, receipt_recorded:saved,
            retry_allowed:false, diagnostic_scope:'SAME_CARRIER_READ_ONLY',
            rejection_reason:'UNDETERMINED', ...publicStatus(afterFailure),
            ready_to_push:false,
          };
        }
      } catch {
        // Both the original effect and terminal readback remain unproven.
      }
      return {
        schema:'mastermind.studio_git_push_result.v1', status:'UNKNOWN',
        effect_state:'EFFECT_UNKNOWN', code:'PUSH_RESULT_UNCERTAIN',
        action_ref:ref, push_attempted:true, retry_allowed:false,
        operation_id:operationId, branch:before.branch,
        local_head_sha:expectedHead,
      };
    }
    try {
      const after = await workspace(operationId, {remoteBinding:before.remoteBinding});
      if (after.remoteHead === expectedHead) {
        const saved = await saveTerminal('APPLIED', 'REMOTE_EXACT_AFTER_PUSH', after.remoteHead);
        return {
          schema:'mastermind.studio_git_push_result.v1', status:'OK',
          effect_state:'APPLIED', code:'APPLIED', action_ref:ref,
          push_attempted:true, receipt_recorded:saved, ...publicStatus(after),
        };
      }
    } catch {
      // A process response and no exact ref receipt are NOT sufficient for success.
    }
    return {
      schema:'mastermind.studio_git_push_result.v1', status:'UNKNOWN',
      effect_state:'EFFECT_UNKNOWN', code:'POST_PUSH_READBACK_UNCERTAIN',
      action_ref:ref, push_attempted:true, retry_allowed:false,
      operation_id:operationId, branch:before.branch, local_head_sha:expectedHead,
    };
  }

  return Object.freeze({ status, commit, push, commitCommission, commissionStatus });
}

export function toolResult(value, isError = false) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
    ...(isError ? { isError: true } : {}),
  };
}
