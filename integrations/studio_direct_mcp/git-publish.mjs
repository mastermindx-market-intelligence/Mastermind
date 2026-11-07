import { createHash, randomUUID } from 'node:crypto';
import { execFile as execFileCallback, spawn as spawnDefault } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { chmod, lstat, mkdir, mkdtemp, open, readFile, readdir, realpath as realpathDefault, rename, rm, stat, utimes, writeFile } from 'node:fs/promises';
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

// Bounded index-lock recovery: one orphaned index.lock, one owner, one local
// filesystem effect. It never rewrites the index, never creates a commit,
// never updates a ref and never contacts a remote. Its historical origin stays
// UNKNOWN by construction: this leaf establishes present exclusive custody, it
// does not reconstruct a past creator.
const INDEX_RECOVERY_SCHEMA = 'mastermind.studio_git_index_recovery_receipt.v1';
const INDEX_RECOVERY_DIR = 'index-recovery';
const INDEX_RECOVERY_MODES = new Set(['PREVIEW', 'APPLY', 'RECONCILE']);
const INDEX_RECOVERY_OUTCOMES = new Set(['APPLIED', 'NOT_APPLIED', 'EFFECT_UNKNOWN']);
const LOCK_IDENTITY_KEYS = Object.freeze([
  'device', 'inode', 'file_type', 'uid', 'gid', 'mode', 'size', 'mtime_ns', 'content_sha256',
]);
// The caller declares the identity it actually observed. Eligibility, not the
// schema, decides that only a regular file can be recovered.
const LOCK_FILE_TYPES = Object.freeze(['REGULAR', 'SYMLINK', 'DIRECTORY', 'OTHER']);
const CUSTODY_KEYS = Object.freeze(['maintenance_window', 'pending_mutators_retired']);
const DECIMAL_STRING_RE = /^(0|[1-9][0-9]*)$/;
const OCTAL_MODE_RE = /^[0-7]{3,4}$/;
const EMPTY_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';

// The recovery phase ladder. A phase is the affirmative proof of how far the
// single lock-path effect could have been reached. PRE_EFFECT and PRE_RENAME
// prove that the rename statement was never entered, so a refusal there is
// truthful. POST_EFFECT proves only that the rename may have happened, so
// every unclassified failure from that point on is an unknown effect, never a
// refusal and never a thrown error a caller could read as "nothing happened".
const INDEX_RECOVERY_PHASE = Object.freeze({
  PRE_EFFECT: 'PRE_EFFECT',
  PRE_RENAME: 'PRE_RENAME',
  POST_EFFECT: 'POST_EFFECT',
  RECONCILING: 'RECONCILING',
});

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
// Recovery inventories may exceed the ordinary command-result buffer. Hash
// their exact NUL-delimited bytes without retaining stdout; this separate hard
// ceiling bounds work, not memory, and never changes other command limits.
const MAX_RECOVERY_INVENTORY_BYTES = 64 * 1024 * 1024;
const RECOVERY_INVENTORY_CLEANUP_MS = 1000;
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

// The exact identity of one orphaned index.lock. Decimal strings keep inode,
// device and nanosecond modification time exact where JSON numbers cannot.
const INDEX_RECOVERY_LOCK_SCHEMA = Object.freeze({
  type: 'object',
  description: 'Exact identity of the one orphaned zero-byte index.lock: device, inode, type, owner, ' +
    'group, permission mode, size, modification nanoseconds and content digest.',
  properties: {
    device: { type: 'string', pattern: '^(0|[1-9][0-9]*)$' },
    inode: { type: 'string', pattern: '^(0|[1-9][0-9]*)$' },
    file_type: { type: 'string', enum: ['REGULAR', 'SYMLINK', 'DIRECTORY', 'OTHER'] },
    uid: { type: 'string', pattern: '^(0|[1-9][0-9]*)$' },
    gid: { type: 'string', pattern: '^(0|[1-9][0-9]*)$' },
    mode: { type: 'string', pattern: '^[0-7]{3,4}$' },
    size: { type: 'string', pattern: '^(0|[1-9][0-9]*)$' },
    mtime_ns: { type: 'string', pattern: '^(0|[1-9][0-9]*)$' },
    content_sha256: { type: 'string', pattern: '^[0-9a-f]{64}$' },
  },
  required: ['device', 'inode', 'file_type', 'uid', 'gid', 'mode', 'size', 'mtime_ns', 'content_sha256'],
  additionalProperties: false,
});

// Present custody is asserted by the caller. It is recorded as declared
// evidence: it is not machine-proven global writer exclusion.
const INDEX_RECOVERY_CUSTODY_SCHEMA = Object.freeze({
  type: 'object',
  description: 'Current custody evidence and the present bounded maintenance condition for this one ' +
    'workspace. Caller-declared, recorded as declared evidence rather than as proven global writer exclusion.',
  properties: {
    maintenance_window: { type: 'string', minLength: 1, maxLength: 128 },
    pending_mutators_retired: { type: 'boolean', enum: [true] },
  },
  required: ['maintenance_window', 'pending_mutators_retired'],
  additionalProperties: false,
});

export const STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL = Object.freeze({
  name: 'studio_git_commit_current_changes',
  title: 'Studio Git Commit or Index Recovery',
  description:
    'Two mutually exclusive local-only variants over one existing Mastermind attended Web workspace. ' +
    'COMMIT: create exactly one local commit from all current committable changes. The caller supplies ' +
    'only the operation id, exact expected current HEAD and a bounded single-line commit message, with an ' +
    'optional exact protected-base and prepared-tree merge fence. Merge mode checks the host-fixed local ' +
    'tracking ref and preserves both ordered parents. Ignored files stay uncommitted. A private temporary ' +
    'index prevents pre-commit staging side effects; after the fenced ref update is known applied, the real ' +
    'index is synchronized to that exact commit. Compare-and-swap ref update prevents stale-head publication. ' +
    'INDEX RECOVERY: recover one orphaned zero-byte Git index.lock in the same owner. The caller supplies ' +
    'the operation id, exact expected current HEAD and a closed index_recovery object holding the expected ' +
    'HEAD tree, the expected real-index digest, the exact lock identity and the current custody and ' +
    'maintenance condition. Recovery preserves the exact lock under a unique owner-private destination on ' +
    'the same filesystem, leaves the real index, the commit graph and the remote untouched, and reports a ' +
    'distinct structured result with the historical origin unknown. ' +
    'The host resolves the workspace, branch, Git directory, index and lock paths from canonical ' +
    'mmx-workspace registration. This operation is local-only; its schema has no capability to contact ' +
    'origin, push, accept paths, change remotes, or accept shell commands.',
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
      index_recovery: {
        type: 'object',
        description: 'Closed index-lock recovery selector. PREVIEW and APPLY carry the exact HEAD tree, ' +
          'real-index digest, lock identity and custody condition. RECONCILE carries only the action_ref ' +
          'of the same action and never moves anything.',
        properties: {
          mode: { type: 'string', enum: ['PREVIEW', 'APPLY', 'RECONCILE'] },
          expected_tree_sha: { type: 'string', pattern: '^[0-9a-f]{40}$' },
          expected_index_sha256: { type: 'string', pattern: '^[0-9a-f]{64}$' },
          lock: INDEX_RECOVERY_LOCK_SCHEMA,
          custody: INDEX_RECOVERY_CUSTODY_SCHEMA,
          action_ref: { type: 'string', pattern: '^[0-9a-f]{64}$' },
        },
        required: ['mode'],
        additionalProperties: false,
      },
    },
    required: ['operation_id', 'expected_head_sha'],
    additionalProperties: false,
    oneOf: [
      { required: ['message'], not: { required: ['index_recovery'] } },
      {
        required: ['index_recovery'],
        not: { anyOf: [{ required: ['message'] }, { required: ['merge'] }] },
      },
    ],
  },
  annotations: {
    title: 'Studio Git Commit or Index Recovery',
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

// ---------------------------------------------------------------------------
// Bounded index-lock recovery: validation, identity and retained records.
//
// One orphaned index.lock, one owner, one local filesystem effect. The leaf
// never rewrites the index, never creates a commit, never updates a ref and
// never contacts a remote. Its historical origin stays UNKNOWN: this leaf
// establishes present exclusive custody, it does not reconstruct a past
// creator. Every durable record lives in the incumbent owner's own private
// Git directory, beside the existing publication receipts, and reuses the
// incumbent integrity wire format and durability primitives. It is not a
// second journal, control plane or lease owner.
// ---------------------------------------------------------------------------

function parseOctalMode(value) {
  if (typeof value !== 'string' || !OCTAL_MODE_RE.test(value)) return null;
  const parsed = parseInt(value, 8);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

// Permission bits only, in octal. The file type is carried separately so a
// declared "0600" and an observed "100600" describe the same regular file.
function permissionMode(stats) {
  return (stats.mode & 0o7777n).toString(8).padStart(4, '0');
}

function digestOf(value) {
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(String(value ?? ''), 'utf8');
  return createHash('sha256').update(bytes).digest('hex');
}

// The action identity is derived only from the caller's own fences, so a
// previewed action, an applied action and a later re-issue of that same action
// all name one record. A different fence set is a different action.
function indexRecoveryActionRef(operationId, branch, expectedHead, expectedTreeSha, expectedIndexSha256, lock) {
  const digest = createHash('sha256')
    .update('mastermind.studio_git_index_recovery.v1\0')
    .update(operationId).update('\0').update(branch).update('\0').update(expectedHead)
    .update('\0').update(expectedTreeSha).update('\0').update(expectedIndexSha256);
  for (const key of LOCK_IDENTITY_KEYS) digest.update('\0').update(String(lock[key]));
  return digest.digest('hex');
}

function validateIndexRecovery(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('index_recovery must be a closed object');
  }
  const mode = value.mode;
  if (typeof mode !== 'string' || !INDEX_RECOVERY_MODES.has(mode)) {
    throw new TypeError('index_recovery.mode must be PREVIEW, APPLY or RECONCILE');
  }
  if (mode === 'RECONCILE') {
    if (Object.keys(value).some((key) => key !== 'mode' && key !== 'action_ref')) {
      throw new TypeError('index_recovery RECONCILE accepts only mode and action_ref');
    }
    if (typeof value.action_ref !== 'string' || !ACTION.test(value.action_ref)) {
      throw new TypeError('index_recovery.action_ref is invalid');
    }
    return Object.freeze({mode, action_ref: value.action_ref});
  }
  const allowed = ['mode', 'expected_tree_sha', 'expected_index_sha256', 'lock', 'custody'];
  if (Object.keys(value).some((key) => !allowed.includes(key))) {
    throw new TypeError('index_recovery accepts only mode, expected_tree_sha, expected_index_sha256, lock and custody');
  }
  if (typeof value.expected_tree_sha !== 'string' || !SHA_RE.test(value.expected_tree_sha)) {
    throw new TypeError('index_recovery.expected_tree_sha is invalid');
  }
  if (typeof value.expected_index_sha256 !== 'string' || !SHA256_RE.test(value.expected_index_sha256)) {
    throw new TypeError('index_recovery.expected_index_sha256 is invalid');
  }
  const lock = value.lock;
  if (!lock || typeof lock !== 'object' || Array.isArray(lock) ||
      Object.keys(lock).length !== LOCK_IDENTITY_KEYS.length ||
      !LOCK_IDENTITY_KEYS.every((key) => Object.hasOwn(lock, key))) {
    throw new TypeError('index_recovery.lock requires the exact device, inode, type, owner, mode, size, mtime and content identity');
  }
  for (const key of ['device', 'inode', 'uid', 'gid', 'size', 'mtime_ns']) {
    if (typeof lock[key] !== 'string' || !DECIMAL_STRING_RE.test(lock[key])) {
      throw new TypeError(`index_recovery.lock.${key} must be an exact decimal string`);
    }
  }
  if (!LOCK_FILE_TYPES.includes(lock.file_type)) {
    throw new TypeError('index_recovery.lock.file_type is invalid');
  }
  if (parseOctalMode(lock.mode) === null) {
    throw new TypeError('index_recovery.lock.mode must be an exact octal string');
  }
  if (typeof lock.content_sha256 !== 'string' || !SHA256_RE.test(lock.content_sha256)) {
    throw new TypeError('index_recovery.lock.content_sha256 is invalid');
  }
  const custody = value.custody;
  if (!custody || typeof custody !== 'object' || Array.isArray(custody) ||
      Object.keys(custody).length !== CUSTODY_KEYS.length ||
      !CUSTODY_KEYS.every((key) => Object.hasOwn(custody, key))) {
    throw new TypeError('index_recovery.custody requires the exact maintenance window and pending-mutator retirement evidence');
  }
  if (typeof custody.maintenance_window !== 'string' || !custody.maintenance_window ||
      custody.maintenance_window.length > 128 || /[\x00-\x1f]/.test(custody.maintenance_window)) {
    throw new TypeError('index_recovery.custody.maintenance_window is invalid');
  }
  if (custody.pending_mutators_retired !== true) {
    throw new TypeError('index_recovery.custody.pending_mutators_retired must be true');
  }
  return Object.freeze({
    mode,
    expected_tree_sha: value.expected_tree_sha,
    expected_index_sha256: value.expected_index_sha256,
    lock: Object.freeze({...lock}),
    custody: Object.freeze({...custody}),
  });
}

// The quarantine destination is derived, never supplied. It is a unique,
// owner-private directory inside the owner's own Git directory, which for both
// a main worktree and a linked worktree is the same directory that holds the
// real index and therefore the same filesystem as the lock.
function indexRecoveryReceiptDir(gitdir, identity) {
  return path.join(gitdir, RECEIPT_DIR, INDEX_RECOVERY_DIR, identity);
}

function indexRecoveryReceiptFile(gitdir, identity, actionRef) {
  return path.join(indexRecoveryReceiptDir(gitdir, identity), actionRef + '.json');
}

function indexRecoveryQuarantineDir(gitdir, identity, actionRef) {
  return path.join(indexRecoveryReceiptDir(gitdir, identity), 'quarantine', actionRef);
}

function indexRecoveryQuarantineFile(gitdir, identity, actionRef) {
  return path.join(indexRecoveryQuarantineDir(gitdir, identity, actionRef), 'index.lock');
}

function indexRecoveryResult({
  status, effect_state, code, disposition, operation_id, branch, mode, action_ref,
  custody = null, unchanged_head, lock, quarantined_lock, receipt_recorded = false, detail = null,
}) {
  return {
    schema: 'mastermind.studio_git_index_recovery_result.v1',
    status,
    effect_state,
    code,
    disposition,
    operation_id,
    branch,
    mode,
    action_ref,
    commit_created: false,
    historical_origin: 'UNKNOWN',
    // This result never conveys retry authority. A caller that wants to try
    // again re-reads the current state and issues a new action with new
    // fences, which is a different action identity.
    retry_allowed: false,
    ...(custody === null ? {} : {custody}),
    unchanged_head,
    lock,
    quarantined_lock,
    receipt_recorded,
    ...(detail === null ? {} : {detail}),
  };
}

// A current state that could not be observed is never reported as unchanged
// and never as changed: it is reported as unavailable.
function unchangedHeadEvidence({expectedHead, expectedTree, expectedIndexSha256, current, entry}) {
  const baseline = entry ?? current;
  const available = Boolean(current) && typeof current.head === 'string' &&
    typeof current.tree === 'string' && typeof current.indexSha256 === 'string';
  return {
    expected_head_sha: expectedHead ?? null,
    observed_head_sha: available ? current.head : null,
    head_unchanged: available ? current.head === expectedHead : null,
    expected_tree_sha: expectedTree ?? null,
    observed_tree_sha: available ? current.tree : null,
    tree_unchanged: available ? current.tree === expectedTree : null,
    expected_index_sha256: expectedIndexSha256 ?? null,
    observed_index_sha256: available ? current.indexSha256 : null,
    index_unchanged: available ? current.indexSha256 === expectedIndexSha256 : null,
    index_matches_head_tree: available ? current.indexMatchesHead : null,
    staged_state_sha256: available ? current.stagedStateSha256 : null,
    sparse_state_sha256: available ? current.sparseStateSha256 : null,
    dirty_state_sha256: available ? current.dirtyStateSha256 : null,
    untracked_state_sha256: available ? current.untrackedStateSha256 : null,
    working_state_unchanged: available ? (
      current.stagedStateSha256 === baseline.stagedStateSha256 &&
      current.sparseStateSha256 === baseline.sparseStateSha256 &&
      current.dirtyStateSha256 === baseline.dirtyStateSha256 &&
      current.untrackedStateSha256 === baseline.untrackedStateSha256) : null,
    clean: available ? (
      current.indexMatchesHead &&
      current.dirtyStateSha256 === EMPTY_SHA256 &&
      current.untrackedStateSha256 === EMPTY_SHA256) : null,
  };
}

// The lock is compared as an exact identity, never as an age or a name. A
// zero-byte regular file owned by the current user is the only eligible
// shape; everything else is refused before any effect.
function lockMatchesExpected(observed, expected) {
  if (!observed || observed.present !== true || observed.file_type !== 'REGULAR') return false;
  const declared = parseOctalMode(expected.mode);
  if (declared === null || declared !== parseOctalMode(observed.mode)) return false;
  for (const key of ['device', 'inode', 'uid', 'gid', 'size', 'mtime_ns', 'content_sha256']) {
    if (String(observed[key]) !== String(expected[key])) return false;
  }
  return true;
}

function lockEligibility(observed, expected) {
  if (!observed || observed.present === null || observed.present === undefined) {
    return {eligible: false, code: 'LOCK_OBSERVATION_UNAVAILABLE'};
  }
  if (!observed.present) return {eligible: false, code: 'LOCK_NOT_PRESENT'};
  if (observed.file_type !== 'REGULAR') return {eligible: false, code: 'LOCK_NOT_REGULAR'};
  const currentUid = typeof process.getuid === 'function' ? String(process.getuid()) : null;
  if (currentUid !== null && observed.uid !== currentUid) {
    return {eligible: false, code: 'LOCK_NOT_OWNED_BY_CURRENT_USER'};
  }
  if (observed.size !== '0' || observed.content_bytes !== 0) {
    return {eligible: false, code: 'LOCK_NOT_EMPTY'};
  }
  if (!lockMatchesExpected(observed, expected)) {
    return {eligible: false, code: 'LOCK_IDENTITY_MISMATCH'};
  }
  return {eligible: true};
}


// A retained record is admitted only as a complete, closed, owner-bound
// record. A valid integrity hash alone proves only that the bytes were not
// changed after they were written: it does not prove that the record belongs
// to this owner, this branch or this action, and it does not prove that its
// fields are complete enough for the helpers that consume them.
function validRecoveryLockIdentity(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  if (Object.keys(value).length !== LOCK_IDENTITY_KEYS.length) return false;
  if (!LOCK_IDENTITY_KEYS.every((key) => Object.hasOwn(value, key))) return false;
  for (const key of ['device', 'inode', 'uid', 'gid', 'size', 'mtime_ns']) {
    if (typeof value[key] !== 'string' || !DECIMAL_STRING_RE.test(value[key])) return false;
  }
  if (!LOCK_FILE_TYPES.includes(value.file_type)) return false;
  if (parseOctalMode(value.mode) === null) return false;
  if (typeof value.content_sha256 !== 'string' || !SHA256_RE.test(value.content_sha256)) return false;
  return true;
}

function validRecoveryCustody(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  if (Object.keys(value).length !== CUSTODY_KEYS.length) return false;
  if (!CUSTODY_KEYS.every((key) => Object.hasOwn(value, key))) return false;
  if (typeof value.maintenance_window !== 'string' || !value.maintenance_window ||
      value.maintenance_window.length > 128 || /[\x00-\x1f]/.test(value.maintenance_window)) return false;
  if (value.pending_mutators_retired !== true) return false;
  return true;
}

function validRecoveryEntryState(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  for (const key of ['head', 'tree', 'indexSha256', 'stagedStateSha256', 'sparseStateSha256',
    'dirtyStateSha256', 'untrackedStateSha256']) {
    if (typeof value[key] !== 'string' || !value[key]) return false;
  }
  if (typeof value.indexMatchesHead !== 'boolean') return false;
  return true;
}

// The retained record must name this owner, this branch and this action, must
// carry every stage field its stage requires, and its own retained fences must
// reproduce its action reference. A copied, renamed or hand-edited record
// fails one of these checks before any mutation is considered.
function validateIndexRecoveryRecord(record, binding) {
  if (!record || typeof record !== 'object' || Array.isArray(record)) {
    return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  }
  if (record.schema !== INDEX_RECOVERY_SCHEMA || record.kind !== 'INDEX_RECOVERY' ||
      !STAGES.has(record.stage)) {
    return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  }
  if (typeof record.operation_id !== 'string' || !record.operation_id ||
      record.operation_id !== binding.operation_id) {
    return {ok: false, error: 'RECEIPT_OWNER_MISMATCH'};
  }
  if (typeof record.branch !== 'string' || !record.branch || record.branch !== binding.branch) {
    return {ok: false, error: 'RECEIPT_OWNER_MISMATCH'};
  }
  if (!ACTION.test(record.action_ref || '') || record.action_ref !== binding.action_ref) {
    return {ok: false, error: 'RECEIPT_ACTION_MISMATCH'};
  }
  if (!SHA_RE.test(record.intended_head_sha || '') || !SHA_RE.test(record.intended_tree_sha || '') ||
      !SHA256_RE.test(record.intended_index_sha256 || '')) {
    return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  }
  if (!validRecoveryLockIdentity(record.lock_identity) || !validRecoveryCustody(record.custody) ||
      !validRecoveryEntryState(record.entry_state)) {
    return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  }
  if (record.historical_origin !== 'UNKNOWN') return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  if (typeof record.generation_id !== 'string' || !record.generation_id ||
      typeof record.created_at !== 'string' || !record.created_at) {
    return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  }
  if (record.stage === 'TERMINAL') {
    if (!INDEX_RECOVERY_OUTCOMES.has(record.terminal_outcome) ||
        (record.terminal_proof !== null && typeof record.terminal_proof !== 'string') ||
        (record.terminal_evidence !== null &&
          (typeof record.terminal_evidence !== 'object' || Array.isArray(record.terminal_evidence))) ||
        typeof record.completed_at !== 'string' || !record.completed_at) {
      return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
    }
  } else if (record.terminal_outcome !== undefined) {
    return {ok: false, error: 'INVALID_RECEIPT_SCHEMA'};
  }
  const derived = indexRecoveryActionRef(record.operation_id, record.branch, record.intended_head_sha,
    record.intended_tree_sha, record.intended_index_sha256, record.lock_identity);
  if (derived !== record.action_ref) return {ok: false, error: 'RECEIPT_DERIVATION_MISMATCH'};
  return {ok: true};
}

// The retained record is bound to the current owner, branch and action before
// it is consumed. Integrity alone is never sufficient: a valid-hash record
// copied or renamed out of a foreign owner would otherwise be adopted as this
// action's terminal outcome.
async function readIndexRecoveryReceipt(file, binding) {
  let bytes;
  try {
    bytes = await readFile(file);
  } catch (error) {
    if (error.code === 'ENOENT') return {missing: true};
    return {corrupt: true, error: String(error.message || error)};
  }
  if (bytes.length > MAX_RECEIPT_BYTES) return {corrupt: true, error: 'OVERSIZE_RECEIPT'};
  let parsed;
  try {
    parsed = JSON.parse(bytes.toString('utf8'));
  } catch {
    return {corrupt: true, error: 'INVALID_RECEIPT'};
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return {corrupt: true, error: 'INVALID_RECEIPT'};
  }
  const {integrity_sha256, ...body} = parsed;
  if (!ACTION.test(integrity_sha256 || '') || hash(JSON.stringify(body)) !== integrity_sha256) {
    return {corrupt: true, error: 'TORN_OR_CHANGED_RECEIPT'};
  }
  const validation = validateIndexRecoveryRecord(body, binding);
  if (!validation.ok) return {corrupt: true, error: validation.error};
  return {record: body};
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
  // One filesystem seam, beside the incumbent realpath and rm seams, so the
  // exact lock ownership check can be exercised without a privileged host.
  const statFile = dependencies.lstat ?? lstat;
  const spawn = dependencies.spawn ?? spawnDefault;

  function commandEnvironment(envExtra = {}) {
    return {
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
    };
  }

  async function run(file, args, { cwd, timeoutMs = cfg.commandTimeoutMs, envExtra = {}, encoding = 'utf8' } = {}) {
    return execFile(file, args, {
      cwd,
      timeout: timeoutMs,
      maxBuffer: MAX_STDIO_BYTES,
      encoding,
      env: commandEnvironment(envExtra),
    });
  }

  async function git(cwd, args, options = {}) {
    return run(cfg.gitBinary, args, { cwd, ...options });
  }

  function gitInventoryDigest(cwd, args) {
    return new Promise((resolve, reject) => {
      // Only the four fixed, read-only recovery inventories call this helper.
      // No shell, optional index refresh, caller command, or output exposure.
      const child = spawn(cfg.gitBinary, args, {
        cwd, env: commandEnvironment({GIT_OPTIONAL_LOCKS: '0'}),
        stdio: ['ignore', 'pipe', 'pipe'], shell: false,
      });
      const digest = createHash('sha256');
      let stdoutBytes = 0;
      let stderrBytes = 0;
      let failure = null;
      let settled = false;
      let timer = null;
      let cleanupTimer = null;
      const finish = (error = null) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        clearTimeout(cleanupTimer);
        if (error) reject(error);
        else resolve(digest.digest('hex'));
      };
      const abort = (code) => {
        if (failure || settled) return;
        failure = Object.assign(new Error(code), {code});
        // These fixed Git readers do not launch hooks or descendants. Require
        // close to confirm reaping; a signal request alone is not that proof.
        cleanupTimer = setTimeout(() => {
          finish(Object.assign(new Error('RECOVERY_INVENTORY_CLEANUP_UNCONFIRMED'),
            {code: 'RECOVERY_INVENTORY_CLEANUP_UNCONFIRMED', cause: failure}));
          // Bound retained pipes even if an OS-level child failure
          // prevents close. This does not claim that the child has exited.
          child.stdout.destroy();
          child.stderr.destroy();
        }, RECOVERY_INVENTORY_CLEANUP_MS);
        try { child.kill('SIGKILL'); } catch { /* Cleanup remains unconfirmed until close. */ }
      };
      timer = setTimeout(() => abort('RECOVERY_INVENTORY_TIMEOUT'), cfg.commandTimeoutMs);
      child.on('error', () => abort('RECOVERY_INVENTORY_PROCESS_ERROR'));
      child.stdout.on('error', () => abort('RECOVERY_INVENTORY_STDOUT_ERROR'));
      child.stderr.on('error', () => abort('RECOVERY_INVENTORY_STDERR_ERROR'));
      child.stdout.on('data', (chunk) => {
        stdoutBytes += chunk.length;
        if (stdoutBytes > MAX_RECOVERY_INVENTORY_BYTES) {
          abort('RECOVERY_INVENTORY_LIMIT');
        } else if (!failure && !settled) {
          digest.update(chunk);
        }
      });
      child.stderr.on('data', (chunk) => {
        stderrBytes += chunk.length;
        if (stderrBytes > MAX_STDIO_BYTES) abort('RECOVERY_INVENTORY_STDERR_LIMIT');
      });
      child.once('close', (code, signal) => {
        if (failure) return finish(failure);
        if (code !== 0 || signal !== null) {
          return finish(new Error('RECOVERY_INVENTORY_COMMAND_FAILED'));
        }
        finish();
      });
    });
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

  // ---- Bounded index-lock recovery ---------------------------------------
  //
  // The workspace, branch, Git directory, real index and lock are resolved
  // entirely through the incumbent registered owner. The caller supplies
  // fences, never a path, branch, remote, command or destination.

  function custodyEvidence(custody) {
    if (!custody) return null;
    return {
      maintenance_window: custody.maintenance_window,
      pending_mutators_retired: custody.pending_mutators_retired,
      // Declared evidence, explicitly not machine-proven global writer
      // exclusion. The publisher cannot see other writers on this host.
      evidence_source: 'CALLER_DECLARED',
      writer_exclusion: 'NOT_MACHINE_PROVEN',
    };
  }

  function recoveryEntryState(state) {
    return {
      head: state.head,
      tree: state.tree,
      indexSha256: state.indexSha256,
      indexMatchesHead: state.indexMatchesHead,
      stagedStateSha256: state.stagedStateSha256,
      sparseStateSha256: state.sparseStateSha256,
      dirtyStateSha256: state.dirtyStateSha256,
      untrackedStateSha256: state.untrackedStateSha256,
    };
  }

  async function captureRecoveryState(workspacePath, resolvedPaths = null) {
    const observationOptions = Object.freeze({envExtra: {GIT_OPTIONAL_LOCKS: '0'}});
    const resolved = resolvedPaths ?? await resolveRecoveryPaths(workspacePath);
    const [{stdout: headOut}, {stdout: treeOut}] = await Promise.all([
      git(workspacePath, ['rev-parse', 'HEAD']),
      git(workspacePath, ['rev-parse', 'HEAD^{tree}']),
    ]);
    const gitdir = resolved.gitdir;
    const indexPath = resolved.indexPath;
    const head = oneLine(headOut, 'workspace HEAD');
    const tree = oneLine(treeOut, 'workspace tree');
    if (!SHA_RE.test(head) || !SHA_RE.test(tree)) throw new Error('workspace identity is invalid');
    // Fingerprint only the state this leaf can affect. This is the incumbent's
    // own bounded observation set, never an unbounded recursive census.
    const [staged, flags, dirty, untracked, indexMatchesHead] = await Promise.all([
      gitInventoryDigest(workspacePath, ['ls-files', '--stage', '-z']),
      gitInventoryDigest(workspacePath, ['ls-files', '-v', '-z']),
      gitInventoryDigest(workspacePath, ['diff-files', '--name-status', '-z']),
      gitInventoryDigest(workspacePath, ['ls-files', '--others', '--exclude-standard', '-z']),
      gitQuiet(workspacePath, ['diff-index', '--cached', '--quiet', 'HEAD', '--'], observationOptions),
    ]);
    const indexStats = await statFile(indexPath, {bigint: true});
    if (!indexStats.isFile()) throw new Error('real index is not a regular file');
    const indexBytes = await readFile(indexPath);
    return {
      workspacePath,
      gitdir,
      indexPath,
      lockPath: indexPath + '.lock',
      head,
      tree,
      indexSha256: createHash('sha256').update(indexBytes).digest('hex'),
      indexSize: indexStats.size.toString(),
      indexMtimeNs: indexStats.mtimeNs.toString(),
      indexInode: indexStats.ino.toString(),
      indexDevice: indexStats.dev.toString(),
      indexMode: permissionMode(indexStats),
      stagedStateSha256: staged,
      sparseStateSha256: flags,
      dirtyStateSha256: dirty,
      untrackedStateSha256: untracked,
      indexMatchesHead,
    };
  }

  async function observeLock(lockPath) {
    let stats;
    try {
      stats = await statFile(lockPath, {bigint: true});
    } catch (error) {
      if (error.code === 'ENOENT') return {present: false};
      throw error;
    }
    const base = {
      present: true,
      device: stats.dev.toString(),
      inode: stats.ino.toString(),
    };
    if (stats.isSymbolicLink()) return {...base, file_type: 'SYMLINK'};
    if (!stats.isFile()) return {...base, file_type: stats.isDirectory() ? 'DIRECTORY' : 'OTHER'};
    const content = await readFile(lockPath);
    return {
      ...base,
      file_type: 'REGULAR',
      uid: stats.uid.toString(),
      gid: stats.gid.toString(),
      mode: permissionMode(stats),
      size: stats.size.toString(),
      mtime_ns: stats.mtimeNs.toString(),
      content_sha256: createHash('sha256').update(content).digest('hex'),
      content_bytes: content.length,
    };
  }

  async function observeQuarantine(quarantineFile, expectedLock) {
    let stats;
    try {
      stats = await statFile(quarantineFile, {bigint: true});
    } catch (error) {
      if (error.code === 'ENOENT') return {present: false, matches: false};
      throw error;
    }
    const observed = {
      present: true,
      file_type: stats.isFile() ? 'REGULAR' : 'OTHER',
      device: stats.dev.toString(),
      inode: stats.ino.toString(),
      uid: stats.uid.toString(),
      gid: stats.gid.toString(),
      mode: permissionMode(stats),
      size: stats.size.toString(),
      mtime_ns: stats.mtimeNs.toString(),
    };
    if (observed.file_type !== 'REGULAR') return {...observed, matches: false};
    const content = await readFile(quarantineFile);
    observed.content_sha256 = createHash('sha256').update(content).digest('hex');
    observed.content_bytes = content.length;
    observed.matches = lockMatchesExpected({...observed, present: true}, expectedLock);
    return observed;
  }

  // A diagnostic observation never throws over a recovery result. An
  // unreadable path is reported as unavailable, which is a different claim
  // from absence: "unavailable" never becomes "absent" and never becomes
  // "retained".
  async function observeQuarantineSafe(quarantineFile, expectedLock) {
    try {
      return await observeQuarantine(quarantineFile, expectedLock);
    } catch (error) {
      return {
        present: null,
        matches: false,
        observation: 'UNAVAILABLE',
        observation_error: String(error?.message ?? error),
      };
    }
  }

  async function observeLockSafe(lockPath) {
    try {
      return await observeLock(lockPath);
    } catch (error) {
      return {
        present: null,
        observation: 'UNAVAILABLE',
        observation_error: String(error?.message ?? error),
      };
    }
  }

  // The quarantined lock is reported as three distinct states: retained,
  // absent, or unavailable. An unavailable observation is never reported as an
  // absence, and a retained lock is never invented.
  function quarantinedLockEvidence(quarantined) {
    if (quarantined.present === true) {
      return {
        present: true, retained: true, device: quarantined.device, inode: quarantined.inode,
        uid: quarantined.uid, gid: quarantined.gid, mode: quarantined.mode, size: quarantined.size,
        mtime_ns: quarantined.mtime_ns, content_sha256: quarantined.content_sha256 ?? null,
      };
    }
    if (quarantined.present === false) return {present: false, retained: false};
    return {
      present: null, retained: null, observation: 'UNAVAILABLE',
      observation_error: quarantined.observation_error ?? null,
    };
  }

  // The recovery receipt, identity and quarantine paths are introduced by this
  // leaf. Every ancestor below the owner's own Git directory is verified as a
  // real, owner-controlled directory with a non-symlink ancestry before any
  // path write, so a pre-existing symlink cannot redirect the quarantine
  // outside the owner. The verification is read-only for every directory that
  // already exists: a directory this leaf creates is the only one whose mode
  // is set, and no chmod ever runs through an unverified ancestor.
  //
  // The check and the later use are not an atomic inode compare-and-swap. A
  // directory can still be replaced between the verification and the write.
  // That limitation is stated, not papered over.
  async function ensureOwnerDirectoryChain(target, ownerRoot, {create = true} = {}) {
    const root = await realpath(ownerRoot);
    const currentUid = typeof process.getuid === 'function' ? process.getuid() : null;
    const rootStats = await statFile(ownerRoot);
    if (rootStats.isSymbolicLink() || !rootStats.isDirectory()) {
      throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
    }
    if (currentUid !== null && rootStats.uid !== currentUid) {
      throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
    }
    if ((rootStats.mode & 0o022) !== 0) {
      throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
    }
    const segments = path.relative(ownerRoot, target).split(path.sep).filter((part) => part.length > 0);
    if (segments.length === 0 || segments.some((segment) => segment === '..' || segment === '.')) {
      throw new Error('INDEX_RECOVERY_PATH_ESCAPES_OWNER');
    }
    let current = ownerRoot;
    for (const segment of segments) {
      current = path.join(current, segment);
      let stats;
      let created = false;
      try {
        stats = await statFile(current);
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
        if (!create) return null;
        try {
          await mkdir(current, {mode: 0o700});
          created = true;
        } catch (mkdirError) {
          if (mkdirError.code !== 'EEXIST') throw mkdirError;
        }
        stats = await statFile(current);
      }
      if (stats.isSymbolicLink() || !stats.isDirectory()) {
        throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
      }
      if (currentUid !== null && stats.uid !== currentUid) {
        throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
      }
      if ((stats.mode & 0o022) !== 0) {
        throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
      }
      const resolved = await realpath(current);
      if (resolved !== root && !resolved.startsWith(root + path.sep)) {
        throw new Error('INDEX_RECOVERY_PATH_ESCAPES_OWNER');
      }
      if (created) await chmod(current, 0o700);
    }
    return current;
  }

  // Reading an existing action never creates its paths. A valid receipt hash
  // cannot authorize following an unowned or symlinked receipt ancestry.
  async function readOwnerIndexRecoveryReceipt(paths, identity, actionRef, binding) {
    const dir = indexRecoveryReceiptDir(paths.gitdir, identity);
    if (await ensureOwnerDirectoryChain(dir, paths.gitdir, {create: false}) === null) {
      return {missing: true};
    }
    const file = indexRecoveryReceiptFile(paths.gitdir, identity, actionRef);
    let stats;
    try {
      stats = await statFile(file);
    } catch (error) {
      if (error.code === 'ENOENT') return {missing: true};
      throw error;
    }
    const uid = typeof process.getuid === 'function' ? process.getuid() : null;
    if (stats.isSymbolicLink() || !stats.isFile() ||
        (uid !== null && stats.uid !== uid) || (stats.mode & 0o022) !== 0) {
      throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
    }
    return await readIndexRecoveryReceipt(file, binding);
  }

  async function observeOwnerQuarantineSafe(state, identity, actionRef, expected) {
    try {
      const dir = indexRecoveryQuarantineDir(state.gitdir, identity, actionRef);
      if (await ensureOwnerDirectoryChain(dir, state.gitdir, {create: false}) === null) {
        return {present: false, matches: false};
      }
      return await observeQuarantineSafe(
        indexRecoveryQuarantineFile(state.gitdir, identity, actionRef), expected);
    } catch (error) {
      return {present: null, matches: false, observation: 'UNAVAILABLE',
        observation_error: String(error?.message ?? error)};
    }
  }

  function recoveryPathFailureCode(error) {
    const message = String(error?.message ?? error);
    if (message.includes('INDEX_RECOVERY_PATH_ESCAPES_OWNER')) return 'INDEX_RECOVERY_PATH_ESCAPES_OWNER';
    if (message.includes('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY')) {
      return 'INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY';
    }
    return 'INDEX_RECOVERY_QUARANTINE_PREPARE_FAILED';
  }

  // A rename becomes durable only when the source and the destination
  // directory are both synced. Syncing the receipt directory alone does not
  // establish a separate rename: the receipt and the lock move are two
  // different directory entries in two different directories.
  async function syncQuarantineDirectories(sourceDir, destinationDir, ownerRoot) {
    const failures = [];
    const directories = new Set([sourceDir]);
    // Every newly created quarantine ancestor must itself be durably reachable.
    // The caller admits this existing chain before any directory is opened.
    if (destinationDir !== ownerRoot && !destinationDir.startsWith(ownerRoot + path.sep)) {
      return {ok: false, failures: [{error: 'INDEX_RECOVERY_PATH_ESCAPES_OWNER'}]};
    }
    for (let dir = destinationDir; ; dir = path.dirname(dir)) {
      directories.add(dir);
      if (dir === ownerRoot) break;
    }
    for (const dir of directories) {
      try {
        await syncDirectory(dir);
      } catch (error) {
        failures.push({directory: path.basename(dir), error: String(error?.message ?? error)});
      }
    }
    return {ok: failures.length === 0, failures};
  }

  // The owner's Git directory and the real index path are resolved with the
  // narrowest possible reads, so that an unreadable real index never erases
  // a retained action.
  async function resolveRecoveryPaths(workspacePath) {
    const [{stdout: gitdirOut}, {stdout: indexPathOut}] = await Promise.all([
      git(workspacePath, ['rev-parse', '--absolute-git-dir']),
      git(workspacePath, ['rev-parse', '--git-path', 'index']),
    ]);
    const gitdir = oneLine(gitdirOut, 'absolute git directory');
    if (!path.isAbsolute(gitdir)) throw new Error('workspace Git directory is not absolute');
    const indexPath = path.resolve(workspacePath, oneLine(indexPathOut, 'real index path'));
    return {workspacePath, gitdir, indexPath, lockPath: indexPath + '.lock'};
  }

  // A state whose observation failed is carried explicitly. It never stands
  // in for a real observation: every comparison against it is "unavailable",
  // not "unchanged" and not "changed".
  function degradedRecoveryState(paths, observed) {
    return {
      workspacePath: paths.workspacePath,
      gitdir: paths.gitdir,
      indexPath: paths.indexPath,
      lockPath: paths.lockPath,
      head: null,
      tree: null,
      indexSha256: null,
      indexMatchesHead: null,
      stagedStateSha256: null,
      sparseStateSha256: null,
      dirtyStateSha256: null,
      untrackedStateSha256: null,
      stateUnavailable: true,
    };
  }

  async function writeIndexRecoveryTerminal(ctx, dispatching, outcome, proof, evidence) {
    if (!dispatching) return false;
    const receiptFile = indexRecoveryReceiptFile(ctx.state.gitdir, ctx.identity, ctx.actionRef);
    const next = {
      ...dispatching,
      stage: 'TERMINAL',
      terminal_outcome: outcome,
      terminal_proof: proof,
      terminal_evidence: evidence ?? null,
      completed_at: new Date().toISOString(),
    };
    try {
      const existing = await readOwnerIndexRecoveryReceipt(
        ctx.state, ctx.identity, ctx.actionRef,
        {operation_id: dispatching.operation_id, branch: dispatching.branch, action_ref: ctx.actionRef});
      if (!existing.record || existing.record.generation_id !== dispatching.generation_id) return false;
      // A stale unknown observation must not overwrite retained applied proof.
      if (existing.record.stage === 'TERMINAL' && existing.record.terminal_outcome === 'APPLIED' &&
          outcome !== 'APPLIED') return false;
      await replaceAtomically(receiptFile, makeWire(next));
      return true;
    } catch {
      // The effect itself stays known to this caller. A later reconcile on the
      // same record completes the terminal write from the retained evidence.
      return false;
    }
  }

  async function refusedIndexRecovery(ctx, code, dispatching) {
    const {base, state, identity, actionRef, recovery, expectedHead, expectedTree, expectedIndexSha256} = ctx;
    const receiptRecorded = await writeIndexRecoveryTerminal(ctx, dispatching, 'NOT_APPLIED', code, null);
    return indexRecoveryResult({
      status: 'REFUSED',
      effect_state: 'NOT_APPLIED',
      code,
      disposition: 'REFUSED',
      ...base,
      action_ref: actionRef,
      custody: custodyEvidence(recovery.custody),
      unchanged_head: unchangedHeadEvidence({expectedHead, expectedTree, expectedIndexSha256, current: state}),
      lock: ctx.lock,
      quarantined_lock: {present: false, retained: false},
      receipt_recorded: receiptRecorded,
    });
  }

  async function unknownIndexRecovery(ctx, code, dispatching) {
    const {base, state, identity, actionRef, recovery, expectedHead, expectedTree, expectedIndexSha256} = ctx;
    const receiptRecorded = await writeIndexRecoveryTerminal(ctx, dispatching, 'EFFECT_UNKNOWN', code, null);
    let current = state;
    try {
      current = await captureRecoveryState(state.workspacePath);
    } catch {
      // Keep the entry capture. An unreadable readback never becomes a
      // fabricated success.
    }
    const quarantined = await observeOwnerQuarantineSafe(state, identity, actionRef, recovery.lock);
    return indexRecoveryResult({
      status: 'UNKNOWN',
      effect_state: 'EFFECT_UNKNOWN',
      code,
      disposition: 'UNKNOWN',
      ...base,
      action_ref: actionRef,
      custody: custodyEvidence(recovery.custody),
      unchanged_head: unchangedHeadEvidence({expectedHead, expectedTree, expectedIndexSha256, current}),
      lock: ctx.lock,
      quarantined_lock: quarantinedLockEvidence(quarantined),
      receipt_recorded: receiptRecorded,
    });
  }

  async function completeIndexRecovery(ctx, dispatching, quarantined) {
    const {base, state, identity, actionRef, recovery, expectedHead, expectedTree, expectedIndexSha256} = ctx;
    if (!quarantined.present || !quarantined.matches) {
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_READBACK_FAILED', dispatching);
    }
    const lockNow = await observeLockSafe(state.lockPath);
    if (lockNow.present === true) {
      // A replacement active lock is not eligible for this action. It is never
      // deleted, restored over or automatically retried.
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_REPLACEMENT_LOCK_PRESENT', dispatching);
    }
    if (lockNow.present === null) {
      // The quarantine is proven, but the absence of a replacement lock on the
      // source path is not, so the effect stays unknown.
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_LOCK_OBSERVATION_UNAVAILABLE', dispatching);
    }
    let current;
    try {
      current = await captureRecoveryState(state.workspacePath);
    } catch {
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_READBACK_FAILED', dispatching);
    }
    const entry = dispatching.entry_state ?? recoveryEntryState(state);
    const head = unchangedHeadEvidence({expectedHead, expectedTree, expectedIndexSha256, current, entry});
    if (!head.head_unchanged || !head.tree_unchanged || !head.index_unchanged ||
        !head.index_matches_head_tree || !head.working_state_unchanged) {
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_STATE_CHANGED_AFTER_QUARANTINE', dispatching);
    }
    const quarantineDir = indexRecoveryQuarantineDir(state.gitdir, identity, actionRef);
    try {
      if (await ensureOwnerDirectoryChain(quarantineDir, state.gitdir, {create: false}) === null) {
        throw new Error('INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
      }
    } catch (error) {
      return await unknownIndexRecovery(ctx, recoveryPathFailureCode(error), dispatching);
    }
    // All routes to a new APPLIED settlement share this durability obligation,
    // including a rename that threw after moving and later reconciliation.
    const durability = await syncQuarantineDirectories(
      path.dirname(state.lockPath), quarantineDir, state.gitdir);
    if (!durability.ok) {
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_DURABILITY_UNCERTAIN', dispatching);
    }
    const evidence = {
      head_sha: current.head,
      tree_sha: current.tree,
      index_sha256: current.indexSha256,
      index_matches_head_tree: current.indexMatchesHead,
      staged_state_sha256: current.stagedStateSha256,
      sparse_state_sha256: current.sparseStateSha256,
      dirty_state_sha256: current.dirtyStateSha256,
      untracked_state_sha256: current.untrackedStateSha256,
      quarantined_lock: {
        device: quarantined.device,
        inode: quarantined.inode,
        uid: quarantined.uid,
        gid: quarantined.gid,
        mode: quarantined.mode,
        size: quarantined.size,
        mtime_ns: quarantined.mtime_ns,
        content_sha256: quarantined.content_sha256,
      },
    };
    const receiptRecorded = await writeIndexRecoveryTerminal(
      ctx, dispatching, 'APPLIED', 'LOCK_QUARANTINED_WITH_UNCHANGED_STATE', evidence);
    return indexRecoveryResult({
      status: 'OK',
      effect_state: 'APPLIED',
      code: 'INDEX_RECOVERY_APPLIED',
      disposition: 'QUARANTINED',
      ...base,
      action_ref: actionRef,
      custody: custodyEvidence(recovery.custody),
      unchanged_head: head,
      lock: ctx.lock,
      quarantined_lock: {present: true, retained: true, ...evidence.quarantined_lock},
      receipt_recorded: receiptRecorded,
    });
  }

  // The single dispatch of the single lock-path effect. There is exactly one
  // rename here and it is never repeated: every other route into this leaf is
  // reconciliation-only.
  async function executeIndexRecovery(ctx, record) {
    const {base, state, identity, actionRef, recovery, expectedHead, expectedTree, expectedIndexSha256} = ctx;
    const receiptFile = indexRecoveryReceiptFile(state.gitdir, identity, actionRef);
    const quarantineDir = indexRecoveryQuarantineDir(state.gitdir, identity, actionRef);
    const quarantineFile = indexRecoveryQuarantineFile(state.gitdir, identity, actionRef);
    let dispatching;
    try {
      dispatching = {...record, stage: 'DISPATCHING', dispatch_started_at: new Date().toISOString()};
      await replaceAtomically(receiptFile, makeWire(dispatching));
      // The dispatch record is durable. The rename is still provably not
      // reached, so a refusal from here is still truthful.
      ctx.phase = INDEX_RECOVERY_PHASE.PRE_RENAME;
    } catch {
      return await refusedIndexRecovery(ctx, 'INDEX_RECOVERY_DISPATCH_RECORD_FAILED', null);
    }
    // Boundary revalidation: operation, HEAD, tree, index bytes and tree, the
    // exact lock identity and the working/staged/sparse fingerprint are all
    // re-read immediately before the effect.
    let current;
    try {
      current = await captureRecoveryState(state.workspacePath);
    } catch {
      return await refusedIndexRecovery(ctx, 'INDEX_RECOVERY_BOUNDARY_READBACK_FAILED', dispatching);
    }
    const lockNow = await observeLockSafe(state.lockPath);
    const boundaryFailures = [];
    if (current.head !== expectedHead) boundaryFailures.push('EXPECTED_HEAD_MISMATCH');
    if (current.tree !== expectedTree) boundaryFailures.push('EXPECTED_TREE_MISMATCH');
    if (current.indexSha256 !== expectedIndexSha256) boundaryFailures.push('INDEX_BYTES_MISMATCH');
    if (!current.indexMatchesHead) boundaryFailures.push('INDEX_TREE_MISMATCH');
    if (current.stagedStateSha256 !== state.stagedStateSha256 ||
        current.sparseStateSha256 !== state.sparseStateSha256 ||
        current.dirtyStateSha256 !== state.dirtyStateSha256 ||
        current.untrackedStateSha256 !== state.untrackedStateSha256) {
      boundaryFailures.push('WORKING_STATE_CHANGED');
    }
    if (lockNow.present === null) boundaryFailures.push('LOCK_OBSERVATION_UNAVAILABLE');
    else if (!lockNow.present) boundaryFailures.push('LOCK_NOT_PRESENT');
    else if (!lockMatchesExpected(lockNow, recovery.lock)) boundaryFailures.push('LOCK_IDENTITY_MISMATCH');
    if (boundaryFailures.length > 0) {
      return await refusedIndexRecovery(ctx, boundaryFailures[0], dispatching);
    }
    // Unique, owner-private, non-overwriting quarantine destination, on the
    // same filesystem as the lock. Every ancestor below the owner's own Git
    // directory is verified as a real owner-controlled directory before any
    // path write, so a pre-existing symlink cannot move the lock outside the
    // owner.
    try {
      await ensureOwnerDirectoryChain(path.dirname(quarantineDir), state.gitdir);
    } catch (error) {
      return await refusedIndexRecovery(ctx, recoveryPathFailureCode(error), dispatching);
    }
    let destinationReady = false;
    try {
      await mkdir(quarantineDir, {mode: 0o700});
      destinationReady = true;
    } catch (error) {
      // The unique destination is never reused and never overwritten.
      if (error.code !== 'EEXIST') {
        return await refusedIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_PREPARE_FAILED', dispatching);
      }
      return await refusedIndexRecovery(ctx, 'QUARANTINE_DESTINATION_OCCUPIED', dispatching);
    }
    if (!destinationReady) {
      return await refusedIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_PREPARE_FAILED', dispatching);
    }
    let destinationOccupied = false;
    try {
      await statFile(quarantineFile, {bigint: true});
      destinationOccupied = true;
    } catch (error) {
      if (error.code !== 'ENOENT') {
        return await refusedIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_PREPARE_FAILED', dispatching);
      }
    }
    if (destinationOccupied) {
      return await refusedIndexRecovery(ctx, 'QUARANTINE_DESTINATION_OCCUPIED', dispatching);
    }
    const destinationStats = await statFile(quarantineDir, {bigint: true});
    if (destinationStats.dev.toString() !== lockNow.device) {
      return await refusedIndexRecovery(ctx, 'QUARANTINE_FILESYSTEM_MISMATCH', dispatching);
    }
    // From this statement the rename may be reached. The phase advances before
    // the call, so an unclassified failure from the rename onward is an
    // unknown effect and never a refusal.
    ctx.phase = INDEX_RECOVERY_PHASE.POST_EFFECT;
    try {
      await rename(state.lockPath, quarantineFile);
    } catch {
      // The rename itself failed. The effect is then established by
      // observation, not inferred from the thrown error.
      const after = await observeOwnerQuarantineSafe(state, identity, actionRef, recovery.lock);
      const lockAfter = await observeLockSafe(state.lockPath);
      if (after.present === true && after.matches) {
        return await completeIndexRecovery(ctx, dispatching, after);
      }
      if (after.present === null || lockAfter.present === null) {
        // Neither the destination nor the source could be read, so the effect
        // is not affirmatively established either way.
        return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_RENAME_UNCERTAIN', dispatching);
      }
      if (lockAfter.present === true && lockMatchesExpected(lockAfter, recovery.lock)) {
        return await refusedIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_RENAME_FAILED', dispatching);
      }
      return await unknownIndexRecovery(ctx, 'INDEX_RECOVERY_QUARANTINE_RENAME_UNCERTAIN', dispatching);
    }
    const quarantined = await observeOwnerQuarantineSafe(state, identity, actionRef, recovery.lock);
    return await completeIndexRecovery(ctx, dispatching, quarantined);
  }

  // An existing non-terminal action is reconciliation-only. It is never a
  // second rename dispatch: the first invocation may still be between its
  // last boundary check and the rename, and a repeated APPLY would open a
  // second rename path for one action. The retained receipt is not retry
  // permission.
  async function resumeIndexRecovery(ctx, record) {
    const {state, identity, actionRef} = ctx;
    const quarantined = await observeOwnerQuarantineSafe(state, identity, actionRef, record.lock_identity);
    if (quarantined.present === true && quarantined.matches) {
      // The move already happened. Finish the same record; never move again.
      return await completeIndexRecovery(ctx, record, quarantined);
    }
    // The original action is not proven terminal: its recorded intent may
    // still reach the lock path. The effect of the original action therefore
    // stays unknown. Reconciliation never claims the effect did not happen and
    // never conveys retry authority.
    const lockNow = await observeLockSafe(state.lockPath);
    const code = lockNow.present === true && lockMatchesExpected(lockNow, record.lock_identity)
      ? 'INDEX_RECOVERY_ORIGINAL_ACTION_MAY_BE_LIVE'
      : 'INDEX_RECOVERY_ORIGINAL_EFFECT_UNRESOLVED';
    return await unknownIndexRecovery(ctx, code, record);
  }

  async function terminalIndexRecoveryResult(ctx, record) {
    const {base, state, identity, actionRef} = ctx;
    const evidence = record.terminal_evidence ?? null;
    const quarantined = await observeOwnerQuarantineSafe(state, identity, actionRef, record.lock_identity);
    const outcome = record.terminal_outcome;
    const applied = outcome === 'APPLIED';
    const uncertain = outcome === 'EFFECT_UNKNOWN';
    const current = evidence
      ? {
        head: evidence.head_sha,
        tree: evidence.tree_sha,
        indexSha256: evidence.index_sha256,
        indexMatchesHead: evidence.index_matches_head_tree,
        stagedStateSha256: evidence.staged_state_sha256,
        sparseStateSha256: evidence.sparse_state_sha256,
        dirtyStateSha256: evidence.dirty_state_sha256,
        untrackedStateSha256: evidence.untracked_state_sha256,
      }
      : {...record.entry_state};
    const lockObserved = await observeLockSafe(state.lockPath);
    return indexRecoveryResult({
      status: applied ? 'OK' : (uncertain ? 'UNKNOWN' : 'REFUSED'),
      effect_state: applied ? 'APPLIED' : (uncertain ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED'),
      code: applied ? 'INDEX_RECOVERY_APPLIED'
        : (uncertain ? 'INDEX_RECOVERY_EFFECT_UNKNOWN' : 'INDEX_RECOVERY_NOT_APPLIED'),
      disposition: applied ? 'QUARANTINED' : (uncertain ? 'UNKNOWN' : 'NOT_OBSERVED'),
      ...base,
      action_ref: actionRef,
      custody: custodyEvidence(record.custody),
      unchanged_head: unchangedHeadEvidence({
        expectedHead: record.intended_head_sha,
        expectedTree: record.intended_tree_sha,
        expectedIndexSha256: record.intended_index_sha256,
        current,
      }),
      lock: {expected: record.lock_identity, observed: lockObserved, eligible: false},
      quarantined_lock: quarantinedLockEvidence(quarantined),
      receipt_recorded: true,
      detail: {terminal_outcome: outcome, terminal_proof: record.terminal_proof ?? null},
    });
  }

  async function reconcileIndexRecovery(ctx) {
    const {base, observed, identity, actionRef, operationId} = ctx;
    let paths = null;
    try {
      paths = await resolveRecoveryPaths(observed.workspacePath);
    } catch (error) {
      // Without the owner's Git directory the retained record cannot be
      // located at all. The action identity is still the caller's, and the
      // effect is unknown.
      return indexRecoveryResult({
        status: 'UNKNOWN',
        effect_state: 'EFFECT_UNKNOWN',
        code: 'INDEX_RECOVERY_OWNER_UNAVAILABLE',
        disposition: 'UNKNOWN',
        ...base,
        action_ref: actionRef,
        unchanged_head: unchangedHeadEvidence({
          expectedHead: null, expectedTree: null, expectedIndexSha256: null, current: null,
        }),
        lock: {expected: null, observed: null, eligible: false},
        quarantined_lock: {present: null, retained: null, observation: 'UNAVAILABLE'},
        detail: {reason: 'THE_OWNER_GIT_DIRECTORY_COULD_NOT_BE_RESOLVED', observation_error: String(error?.message ?? error)},
      });
    }
    // The retained action is read before the current observation is trusted:
    // an unreadable real index can never erase a retained action.
    const binding = {operation_id: operationId, branch: observed.branch, action_ref: actionRef};
    ctx.state = degradedRecoveryState(paths, observed);
    const existing = await readOwnerIndexRecoveryReceipt(paths, identity, actionRef, binding);
    if (existing.missing) {
      // No retained record for this action. The absence of a receipt is not
      // proof that the action never ran, and it is not proof of a terminal
      // absence.
      return indexRecoveryResult({
        status: 'UNKNOWN',
        effect_state: 'EFFECT_UNKNOWN',
        code: 'INDEX_RECOVERY_NO_RETAINED_RECORD',
        disposition: 'UNKNOWN',
        ...base,
        action_ref: actionRef,
        unchanged_head: unchangedHeadEvidence({
          expectedHead: null, expectedTree: null, expectedIndexSha256: null, current: null,
        }),
        lock: {expected: null, observed: null, eligible: false},
        quarantined_lock: {present: null, retained: null, observation: 'UNAVAILABLE'},
        detail: {reason: 'NO_RETAINED_INDEX_RECOVERY_RECEIPT'},
      });
    }
    if (existing.corrupt) {
      return indexRecoveryResult({
        status: 'UNKNOWN',
        effect_state: 'EFFECT_UNKNOWN',
        code: 'INDEX_RECOVERY_RECEIPT_CORRUPT',
        disposition: 'UNKNOWN',
        ...base,
        action_ref: actionRef,
        unchanged_head: unchangedHeadEvidence({
          expectedHead: null, expectedTree: null, expectedIndexSha256: null, current: null,
        }),
        lock: {expected: null, observed: null, eligible: false},
        quarantined_lock: {present: null, retained: null, observation: 'UNAVAILABLE'},
        detail: {receipt_error: existing.error ?? null},
      });
    }
    const record = existing.record;
    // From here the current observation is best-effort. A live owner or index
    // that cannot be read never becomes a claim about the original action.
    let state;
    try {
      state = await captureRecoveryState(observed.workspacePath, paths);
    } catch (error) {
      state = degradedRecoveryState(paths, observed);
      state.observation_error = String(error?.message ?? error);
    }
    const recoveryCtx = {
      base,
      observed,
      state,
      identity,
      actionRef,
      recovery: {
        expected_tree_sha: record.intended_tree_sha,
        expected_index_sha256: record.intended_index_sha256,
        lock: record.lock_identity,
        custody: record.custody,
      },
      expectedHead: record.intended_head_sha,
      expectedTree: record.intended_tree_sha,
      expectedIndexSha256: record.intended_index_sha256,
      lock: {expected: record.lock_identity, observed: null, eligible: false},
      phase: INDEX_RECOVERY_PHASE.RECONCILING,
    };
    const quarantined = await observeOwnerQuarantineSafe(state, identity, actionRef, record.lock_identity);
    if (record.stage === 'TERMINAL') {
      if (record.terminal_outcome === 'EFFECT_UNKNOWN' && quarantined.present === true && quarantined.matches) {
        // The historical terminal outcome is unknown, but the current physical
        // proof for this exact action is exact. The effect is reconciled
        // through the existing owner, without another lock move.
        return await completeIndexRecovery(recoveryCtx, record, quarantined);
      }
      return await terminalIndexRecoveryResult(recoveryCtx, record);
    }
    if (quarantined.present === true && quarantined.matches) {
      // The move happened. Complete the same record and report the truth.
      return await completeIndexRecovery(recoveryCtx, record, quarantined);
    }
    const lockNow = await observeLockSafe(paths.lockPath);
    recoveryCtx.lock = {expected: record.lock_identity, observed: lockNow, eligible: false};
    // The recorded intent never reached the lock path, but it may still be
    // live. The current observation does not prove that the original action
    // never reached the rename and never proves a terminal absence.
    const code = lockNow.present === true && lockMatchesExpected(lockNow, record.lock_identity)
      ? 'INDEX_RECOVERY_ORIGINAL_ACTION_MAY_BE_LIVE'
      : 'INDEX_RECOVERY_ORIGINAL_EFFECT_UNRESOLVED';
    return await unknownIndexRecovery(recoveryCtx, code, record);
  }

  // The recovery-specific, phase-aware exception boundary. Once the rename may
  // have been reached, an unclassified error is a structured unknown effect
  // that keeps the original action reference. Before that point the phase is
  // the affirmative proof that the rename statement was never entered, so the
  // refusal is truthful. Diagnostics never throw over this result.
  async function indexRecoveryBoundary(ctx, error) {
    const phase = ctx.phase ?? INDEX_RECOVERY_PHASE.PRE_EFFECT;
    const uncertain = phase === INDEX_RECOVERY_PHASE.POST_EFFECT ||
      phase === INDEX_RECOVERY_PHASE.RECONCILING;
    const code = uncertain
      ? 'INDEX_RECOVERY_EFFECT_UNQUALIFIED'
      : 'INDEX_RECOVERY_PRE_EFFECT_REFUSED';
    const state = ctx.state ?? null;
    let current = state;
    try {
      if (state && state.workspacePath) current = await captureRecoveryState(state.workspacePath);
    } catch {
      // An unreadable readback never becomes a fabricated success.
    }
    let quarantined = {present: null, matches: false, observation: 'UNAVAILABLE'};
    try {
      if (state && state.gitdir && ctx.identity && ctx.actionRef) {
        quarantined = await observeOwnerQuarantineSafe(
          state, ctx.identity, ctx.actionRef, ctx.recovery?.lock ?? null);
      }
    } catch {
      // The observation stays unavailable.
    }
    return indexRecoveryResult({
      status: uncertain ? 'UNKNOWN' : 'REFUSED',
      effect_state: uncertain ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED',
      code,
      disposition: uncertain ? 'UNKNOWN' : 'REFUSED',
      ...ctx.base,
      action_ref: ctx.actionRef ?? null,
      custody: custodyEvidence(ctx.recovery?.custody ?? null),
      unchanged_head: unchangedHeadEvidence({
        expectedHead: ctx.expectedHead ?? null,
        expectedTree: ctx.expectedTree ?? null,
        expectedIndexSha256: ctx.expectedIndexSha256 ?? null,
        current,
      }),
      lock: ctx.lock ?? {expected: ctx.recovery?.lock ?? null, observed: null, eligible: false},
      quarantined_lock: quarantinedLockEvidence(quarantined),
      receipt_recorded: false,
      detail: {phase, observation_error: String(error?.message ?? error)},
    });
  }

  async function indexRecovery({operationId, expectedHead, recovery}) {
    const reconciling = recovery.mode === 'RECONCILE';
    // The recovery context exists before the owner is resolved, so that a
    // failure to reach the owner is still a structured recovery result that
    // keeps the original action identity instead of an escaping error.
    const ctx = {
      base: {operation_id: operationId, branch: null, mode: recovery.mode},
      observed: null,
      identity: null,
      actionRef: reconciling ? recovery.action_ref : null,
      operationId,
      expectedHead,
      expectedTree: reconciling ? null : recovery.expected_tree_sha,
      expectedIndexSha256: reconciling ? null : recovery.expected_index_sha256,
      recovery,
      // APPLY may name a retained action. Until absence is actually observed,
      // an owner/read failure cannot establish historical nonexecution.
      phase: recovery.mode === 'PREVIEW' ? INDEX_RECOVERY_PHASE.PRE_EFFECT : INDEX_RECOVERY_PHASE.RECONCILING,
      state: null,
      lock: null,
    };
    try {
      const observed = await workspace(operationId, {observeRemote: false});
      ctx.observed = observed;
      ctx.base = {operation_id: operationId, branch: observed.branch, mode: recovery.mode};
      ctx.identity = hash(operationId + '\0' + observed.branch);
      const identity = ctx.identity;
      const base = ctx.base;
      if (reconciling) {
        return await reconcileIndexRecovery(ctx);
      }

      const expectedTree = recovery.expected_tree_sha;
      const expectedIndexSha256 = recovery.expected_index_sha256;
      // The action identity is derived only from the caller's own fences and
      // the resolved branch, so it is known before any lock-path effect and
      // survives an unreadable live state.
      const actionRef = indexRecoveryActionRef(operationId, observed.branch, expectedHead,
        expectedTree, expectedIndexSha256, recovery.lock);
      ctx.actionRef = actionRef;
      ctx.expectedTree = expectedTree;
      ctx.expectedIndexSha256 = expectedIndexSha256;
      let paths;
      try {
        paths = await resolveRecoveryPaths(observed.workspacePath);
      } catch (error) {
        const uncertain = recovery.mode === 'APPLY';
        return indexRecoveryResult({
          status: uncertain ? 'UNKNOWN' : 'REFUSED',
          effect_state: uncertain ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED',
          code: 'INDEX_RECOVERY_OWNER_UNAVAILABLE',
          disposition: uncertain ? 'UNKNOWN' : 'REFUSED',
          ...base,
          action_ref: actionRef,
          custody: custodyEvidence(recovery.custody),
          unchanged_head: unchangedHeadEvidence({
            expectedHead, expectedTree, expectedIndexSha256, current: null,
          }),
          lock: {expected: recovery.lock, observed: null, eligible: false},
          quarantined_lock: {present: null, retained: null, observation: 'UNAVAILABLE'},
          detail: {reason: 'THE_OWNER_GIT_DIRECTORY_COULD_NOT_BE_RESOLVED', observation_error: String(error?.message ?? error)},
        });
      }
      ctx.state = degradedRecoveryState(paths, observed);
      if (recovery.mode === 'APPLY') {
        const binding = {operation_id: operationId, branch: observed.branch, action_ref: actionRef};
        const existing = await readOwnerIndexRecoveryReceipt(paths, identity, actionRef, binding);
        if (existing.corrupt || existing.record) {
          ctx.phase = INDEX_RECOVERY_PHASE.RECONCILING;
          return await reconcileIndexRecovery(ctx);
        }
        if (existing.missing !== true) throw new Error('INDEX_RECOVERY_RECEIPT_OBSERVATION_UNAVAILABLE');
        // Only a positively observed new action enters new-effect preparation.
        ctx.phase = INDEX_RECOVERY_PHASE.PRE_EFFECT;
      }
      let state;
      try {
        state = await captureRecoveryState(observed.workspacePath, paths);
      } catch {
        state = degradedRecoveryState(paths, observed);
      }
      ctx.state = state;
      if (state.stateUnavailable) {
        // The current index could not be read. Nothing was dispatched and the
        // rename was never reached, so this refusal is affirmative.
        return indexRecoveryResult({
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'INDEX_RECOVERY_STATE_UNAVAILABLE',
          disposition: 'REFUSED',
          ...base,
          action_ref: actionRef,
          custody: custodyEvidence(recovery.custody),
          unchanged_head: unchangedHeadEvidence({
            expectedHead, expectedTree, expectedIndexSha256, current: state,
          }),
          lock: {expected: recovery.lock, observed: null, eligible: false},
          quarantined_lock: {present: null, retained: null, observation: 'UNAVAILABLE'},
          detail: {reason: 'THE_CURRENT_OWNER_STATE_COULD_NOT_BE_READ'},
        });
      }
      if (state.head !== observed.localHead) {
        throw new Error('workspace HEAD changed during recovery observation');
      }
      const lockObserved = await observeLockSafe(state.lockPath);
      const eligibility = lockEligibility(lockObserved, recovery.lock);
      const fenceFailures = [];
      if (state.head !== expectedHead) fenceFailures.push('EXPECTED_HEAD_MISMATCH');
      if (state.tree !== expectedTree) fenceFailures.push('EXPECTED_TREE_MISMATCH');
      if (state.indexSha256 !== expectedIndexSha256) fenceFailures.push('INDEX_BYTES_MISMATCH');
      if (!state.indexMatchesHead) fenceFailures.push('INDEX_TREE_MISMATCH');
      if (!eligibility.eligible) fenceFailures.push(eligibility.code);
      const lock = {expected: recovery.lock, observed: lockObserved, eligible: eligibility.eligible};
      ctx.lock = lock;
      const head = unchangedHeadEvidence({expectedHead, expectedTree, expectedIndexSha256, current: state});

      if (recovery.mode === 'PREVIEW') {
        const plan = {
          action_ref: actionRef,
          quarantine_relative_path: path.join(RECEIPT_DIR, INDEX_RECOVERY_DIR, identity,
            'quarantine', actionRef, 'index.lock'),
          expected_head_sha: expectedHead,
          expected_tree_sha: expectedTree,
          expected_index_sha256: expectedIndexSha256,
          effects: ['QUARANTINE_ONE_ORPHANED_INDEX_LOCK'],
          writes_index: false,
          creates_commit: false,
          updates_ref: false,
          contacts_remote: false,
          historical_origin: 'UNKNOWN',
        };
        if (fenceFailures.length > 0) {
          return indexRecoveryResult({
            status: 'REFUSED',
            effect_state: 'NOT_APPLIED',
            code: fenceFailures[0],
            disposition: 'REFUSED',
            ...base,
            action_ref: actionRef,
            custody: custodyEvidence(recovery.custody),
            unchanged_head: head,
            lock,
            quarantined_lock: null,
            detail: {fence_failures: fenceFailures, plan},
          });
        }
        return indexRecoveryResult({
          status: 'OK',
          effect_state: 'NOT_APPLIED',
          code: 'INDEX_RECOVERY_PREVIEW',
          disposition: 'REVIEW_ONLY',
          ...base,
          action_ref: actionRef,
          custody: custodyEvidence(recovery.custody),
          unchanged_head: head,
          lock,
          quarantined_lock: null,
          detail: {plan},
        });
      }

      // APPLY: retained actions were handled before current-index preparation.
      const receiptFile = indexRecoveryReceiptFile(state.gitdir, identity, actionRef);
      if (fenceFailures.length > 0) {
        return indexRecoveryResult({
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: fenceFailures[0],
          disposition: 'REFUSED',
          ...base,
          action_ref: actionRef,
          custody: custodyEvidence(recovery.custody),
          unchanged_head: head,
          lock,
          quarantined_lock: null,
          detail: {fence_failures: fenceFailures},
        });
      }
      // Durable same-owner intent before the first lock-path effect. Its
      // historical origin is UNKNOWN by construction.
      const record = {
        schema: INDEX_RECOVERY_SCHEMA,
        kind: 'INDEX_RECOVERY',
        operation_id: operationId,
        branch: observed.branch,
        action_ref: actionRef,
        intended_head_sha: expectedHead,
        intended_tree_sha: expectedTree,
        intended_index_sha256: expectedIndexSha256,
        lock_identity: recovery.lock,
        custody: recovery.custody,
        historical_origin: 'UNKNOWN',
        entry_state: recoveryEntryState(state),
        stage: 'PREPARED',
        generation_id: String(process.pid) + ':' + randomUUID(),
        created_at: new Date().toISOString(),
      };
      try {
        await ensureOwnerDirectoryChain(indexRecoveryReceiptDir(state.gitdir, identity), state.gitdir);
      } catch (error) {
        return indexRecoveryResult({
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: recoveryPathFailureCode(error),
          disposition: 'REFUSED',
          ...base,
          action_ref: actionRef,
          custody: custodyEvidence(recovery.custody),
          unchanged_head: head,
          lock,
          quarantined_lock: null,
          detail: {reason: String(error?.message ?? error)},
        });
      }
      try {
        await writeExclusive(receiptFile, makeWire(record));
      } catch (error) {
        return indexRecoveryResult({
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'INDEX_RECOVERY_INTENT_RECORD_FAILED',
          disposition: 'REFUSED',
          ...base,
          action_ref: actionRef,
          custody: custodyEvidence(recovery.custody),
          unchanged_head: head,
          lock,
          quarantined_lock: null,
          detail: {reason: String(error.code || error.message || error)},
        });
      }
      return await executeIndexRecovery(ctx, record);
    } catch (error) {
      return await indexRecoveryBoundary(ctx, error);
    }
  }

  async function commit(args) {
    if (!args || typeof args !== 'object' || Array.isArray(args) ||
        Object.keys(args).some((key) =>
          !['operation_id', 'expected_head_sha', 'message', 'merge', 'index_recovery'].includes(key))) {
      throw new TypeError('studio_git_commit_current_changes arguments are invalid');
    }
    const operationId = validateOperationId(args.operation_id);
    const expectedHead = validateExpectedHead(args.expected_head_sha);
    // The recovery branch is taken before any commit-message validation. The
    // two variants are mutually exclusive: a recovery carries no message and
    // no merge fence, and an ordinary commit carries no recovery object.
    if (Object.hasOwn(args, 'index_recovery')) {
      if (Object.hasOwn(args, 'message') || Object.hasOwn(args, 'merge')) {
        throw new TypeError('index_recovery forbids message and merge');
      }
      const recovery = validateIndexRecovery(args.index_recovery);
      return await indexRecovery({operationId, expectedHead, recovery});
    }
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
