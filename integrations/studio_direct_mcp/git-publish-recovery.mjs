import {createHash, randomUUID} from 'node:crypto';
import path from 'node:path';
import {mkdir, open, readFile, readdir, rename, rm} from 'node:fs/promises';

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
