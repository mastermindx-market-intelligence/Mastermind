// Fixed original-result operations inside the incumbent authenticated C3 owner.
// Selectors/stdin are correlation, never identity. The gateway authenticates.
import childProcess from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { open, lstat } from 'node:fs/promises';
import path from 'node:path';

export const ORIGINAL_ACCOUNT = 'fabric-c3-570f6f34';
export const ORIGINAL_PRINCIPAL = 'p:tunnel:' + ORIGINAL_ACCOUNT;
export const ORIGINAL_ROOT = 'fabric-application-integration-20261104-sol';
export const ORIGINAL_RUNS = Object.freeze([
  'fabric-app-native-drivers-j-20261105-01',
  'fabric-app-application-process-carrier-20261105-01',
]);
// Exactly one reconciliation selection exists, for the preserved J identity.
export const ORIGINAL_RECONCILE_RUN = 'fabric-app-native-drivers-j-20261105-01';
const ACTIONS = Object.freeze({ fabric_collect_original: 'collect',
  fabric_original_collection_status: 'status', fabric_original_collection_result: 'result',
  fabric_original_collection_reconcile: 'reconcile' });
export const ORIGINAL_TOOL_NAMES = new Set(Object.keys(ACTIONS));
const SHA = /^[0-9a-f]{64}$/;
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const FIELDS = ['enabled', 'schema', 'pythonPath', 'pythonSha256', 'controlPath',
  'controlSha256', 'controlBundleDigest', 'nativeStore', 'nativeGeneration',
  'predecessor'].sort();
const PREDECESSOR_SCHEMA = 'mastermind.fabric_original_predecessor.v1';
const PREDECESSOR_KEYS = ['prior', 'receipt_sha256', 'runs', 'schema', 'seal'];
const PREDECESSOR_PRIOR_KEYS = ['account', 'bundleDigest', 'configHash', 'controlSha256',
  'host', 'nativeGeneration', 'parent', 'principal', 'root'];
const PREDECESSOR_RUN_KEYS = ['destination', 'observation'];
const OBSERVATION_STATUS_KEYS = ['acceptance', 'controller_state', 'destination_reserved',
  'effect_state', 'lease_settlement', 'original_operation_mutated', 'reason', 'run_id', 'state'];
const OBSERVATION_RECEIPT_KEYS = ['acceptance', 'controller_state', 'delivery_verified',
  'destination_reserved', 'lease_settlement', 'original_operation_mutated', 'receipt_sha256',
  'run_id', 'state'];
const RETRY_KEYS = ['retry_authorized', 'retry_allowed'];
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const canonicalPath = value => typeof value === 'string' && !value.includes('\0') &&
  path.isAbsolute(value) && path.normalize(value) === value;

// The machine owner seals the predecessor. This owner only consumes the
// sealed result and recomputes the seal as a tamper check; the seal covers
// the machine owner's own prior commitments, never caller-chosen bytes.
function predecessorBody(document) {
  const pairs = [['schema', document.schema], ['receipt_sha256', document.receipt_sha256]];
  for (const key of Object.keys(document.prior).sort()) pairs.push([`prior.${key}`, String(document.prior[key])]);
  for (const run of Object.keys(document.runs).sort()) {
    const entry = document.runs[run];
    pairs.push([`runs.${run}.destination`, entry.destination]);
    pairs.push([`runs.${run}.observation`, entry.observation === null ? 'null' : entry.observation]);
  }
  pairs.sort((left, right) => (left[0] < right[0] ? -1 : left[0] > right[0] ? 1 : 0));
  for (const [key, value] of pairs) {
    if (!key || key.includes('=') || value.includes('\n')) throw new TypeError('original predecessor body refused');
  }
  return pairs.map(([key, value]) => `${key}=${value}`).join('\n');
}

function observationShape(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const keys = Object.keys(value);
  const retry = keys.filter(key => RETRY_KEYS.includes(key));
  if (retry.length !== 1) return null;
  const rest = keys.filter(key => !RETRY_KEYS.includes(key)).sort();
  if (rest.join(',') === [...OBSERVATION_STATUS_KEYS].sort().join(',')) return 'status';
  if (rest.join(',') === [...OBSERVATION_RECEIPT_KEYS].sort().join(',')) return 'receipt';
  const required = OBSERVATION_STATUS_KEYS.filter(key => !['destination_reserved', 'effect_state'].includes(key));
  if (value.state === 'UNKNOWN' && required.every(key => rest.includes(key)) &&
      rest.every(key => OBSERVATION_STATUS_KEYS.includes(key)) && rest.length < OBSERVATION_STATUS_KEYS.length) return 'held_status';
  return null;
}

function qualifyObservation(observation, runId) {
  const shape = observationShape(observation);
  if (!shape) throw new TypeError('original predecessor observation is not the original contract');
  if (observation.run_id !== runId) throw new TypeError('original predecessor observation names another run');
  const retry = RETRY_KEYS.find(key => key in observation);
  if (observation[retry] !== false) throw new TypeError('original predecessor observation authorizes a retry');
  if (observation.acceptance !== 'NOT_RECORDED') throw new TypeError('original predecessor observation recorded acceptance');
  if (observation.original_operation_mutated !== false) throw new TypeError('original predecessor observation mutated the original operation');
  if (observation.lease_settlement !== 'UNKNOWN' || observation.controller_state !== 'UNKNOWN') {
    throw new TypeError('original predecessor observation settled a lease or controller');
  }
  if (shape === 'status' || shape === 'held_status') {
    if (!['ABSENT', 'UNKNOWN'].includes(observation.state)) throw new TypeError('original predecessor observation is not absent or unknown');
    if ('effect_state' in observation && observation.effect_state !== 'UNKNOWN') throw new TypeError('original predecessor observation effect is not unknown');
    if ('destination_reserved' in observation && typeof observation.destination_reserved !== 'boolean') throw new TypeError('original predecessor observation reservation is not a fact');
    if (observation.state === 'ABSENT' && observation.destination_reserved !== false) {
      throw new TypeError('original predecessor observation claims a reservation it never made');
    }
  } else {
    if (!['PENDING', 'COMPLETE'].includes(observation.state)) throw new TypeError('original predecessor observation is not a retained return');
    if (observation.destination_reserved !== true) throw new TypeError('original predecessor observation lost its reservation');
    if (typeof observation.delivery_verified !== 'boolean') throw new TypeError('original predecessor observation verification is not a fact');
    if (observation.delivery_verified !== (observation.state === 'COMPLETE')) throw new TypeError('original predecessor observation verification differs from state');
    if (!SHA.test(observation.receipt_sha256)) throw new TypeError('original predecessor observation receipt digest is not qualified');
  }
  return shape;
}

function validatePredecessor(document) {
  if (!exact(document, PREDECESSOR_KEYS) || document.schema !== PREDECESSOR_SCHEMA) {
    throw new TypeError('original predecessor binding is not installed');
  }
  if (!SHA.test(document.receipt_sha256)) throw new TypeError('original predecessor digest refused');
  if (!exact(document.prior, PREDECESSOR_PRIOR_KEYS)) throw new TypeError('original predecessor prior commitments refused');
  if (document.prior.account !== ORIGINAL_ACCOUNT || document.prior.principal !== ORIGINAL_PRINCIPAL) {
    throw new TypeError('original predecessor owner refused');
  }
  if (document.prior.root !== ORIGINAL_ROOT || document.prior.parent !== ORIGINAL_ROOT || document.prior.host !== 'ubuntu1') {
    throw new TypeError('original predecessor root refused');
  }
  for (const key of ['bundleDigest', 'configHash', 'controlSha256', 'nativeGeneration']) {
    if (!SHA.test(document.prior[key])) throw new TypeError('original predecessor commitment refused');
  }
  if (!document.runs || typeof document.runs !== 'object' || Array.isArray(document.runs)) {
    throw new TypeError('original predecessor runs refused');
  }
  const runs = Object.keys(document.runs);
  if (runs.sort().join(',') !== [...ORIGINAL_RUNS].sort().join(',')) throw new TypeError('original predecessor runs refused');
  const observations = {};
  for (const run of runs) {
    if (!ORIGINAL_RUNS.includes(run)) throw new TypeError('original predecessor run refused');
    const entry = document.runs[run];
    if (!exact(entry, PREDECESSOR_RUN_KEYS)) throw new TypeError('original predecessor entry refused');
    if (!canonicalPath(entry.destination)) throw new TypeError('original predecessor destination refused');
    if (!entry.destination.split('/').includes(ORIGINAL_ROOT)) throw new TypeError('original predecessor destination refused');
    if (path.basename(entry.destination) !== `${run}-collection-v1`) throw new TypeError('original predecessor destination refused');
    if (entry.observation === null) { observations[run] = null; continue; }
    if (typeof entry.observation !== 'string' || !entry.observation) throw new TypeError('original predecessor observation refused');
    let observation;
    try { observation = JSON.parse(entry.observation); } catch { throw new TypeError('original predecessor observation is not decodable'); }
    // Python's sealed observation is canonical flat JSON. Equality rejects
    // duplicate JSON fields as well as a caller's noncanonical replacement.
    const canonical = JSON.stringify(observation, Object.keys(observation).sort())
      .replace(/[\u007f-\uffff]/g, char => '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0'));
    if (canonical !== entry.observation) {
      throw new TypeError('original predecessor observation is not canonical');
    }
    qualifyObservation(observation, run);
    observations[run] = observation;
  }
  if (digest(Buffer.from(predecessorBody(document), 'utf8')) !== document.seal) {
    throw new TypeError('original predecessor seal refused');
  }
  return { receipt_sha256: document.receipt_sha256, runs: observations };
}

export function originalCollectionConfig(cfg) {
  const value = cfg.originalCollection;
  if (value === undefined || value === false || value === null) return null;
  if (cfg.accountLabel !== ORIGINAL_ACCOUNT || cfg.host !== '127.0.0.1' || cfg.port !== 45280 ||
      cfg.modernFabricProtocol !== true || cfg.fabricOnly !== true || cfg.backendMode !== 'shared-account' ||
      cfg.testMode || cfg.publicUrl || cfg.gitPublish || cfg.repositoryWorkspaces ||
      cfg.commissionPublication || cfg.paperDesign || cfg.fleetStatus || !canonicalPath(cfg.cwd) ||
      !exact(value, FIELDS) || value.enabled !== true || value.schema !== 'mastermind.fabric_original_collection.v2' ||
      ['pythonSha256', 'controlSha256', 'controlBundleDigest', 'nativeGeneration'].some(key => !SHA.test(value[key])) ||
      ['pythonPath', 'controlPath', 'nativeStore'].some(key => !canonicalPath(value[key])) ||
      value.controlPath !== path.join(cfg.cwd, '.local/share/studio-direct-mcp/control/private_service.py') ||
      value.nativeStore !== path.join(cfg.cwd, '.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/' +
        'handoff_kits/meta-ceo-b-2026-09-08/native-code-releases')) {
    throw new TypeError('original collection requires its exact enrolled private C3 configuration');
  }
  // The sealed predecessor is validated before the descriptor is accepted, so
  // an invalid or conflicting import never reaches a running owner.
  if (value.predecessor !== null) validatePredecessor(value.predecessor);
  return Object.freeze({ ...value });
}

export const ORIGINAL_TOOLS = Object.freeze(Object.entries(ACTIONS).map(([name, action]) => ({
  name,
  description: action === 'collect' ? 'Collect one of the two source-qualified original returns once; never launch or retry work.' :
    action === 'status' ? 'Read the fixed original collection destination; absence never authorizes a retry.' :
      action === 'reconcile' ? 'Perform at most one subordinate collection-only observation of the fixed original leaf, bound to the sealed predecessor digest; never launches, retries or settles.' :
        'Read a COMPLETE original return pinned by its exact receipt SHA256; does not accept code or settle a lease.',
  inputSchema: { type: 'object', additionalProperties: false,
    required: action === 'result' ? ['run_id', 'receipt_sha256'] :
      action === 'reconcile' ? ['run_id', 'predecessor_sha256'] : ['run_id'],
    properties: { run_id: { type: 'string', enum: [...ORIGINAL_RUNS] },
      ...(action === 'result' ? { receipt_sha256: { type: 'string', pattern: '^[0-9a-f]{64}$' } } : {}),
      ...(action === 'reconcile' ? { predecessor_sha256: { type: 'string', pattern: '^[0-9a-f]{64}$' } } : {}) } },
  annotations: { readOnlyHint: action === 'status' || action === 'result', destructiveHint: false,
    idempotentHint: action !== 'collect' && action !== 'reconcile', openWorldHint: false },
})));

function argumentsFor(name, args) {
  const action = ACTIONS[name];
  const keys = action === 'result' ? ['run_id', 'receipt_sha256'] :
    action === 'reconcile' ? ['run_id', 'predecessor_sha256'] : ['run_id'];
  if (!action || !exact(args, keys) ||
      !ORIGINAL_RUNS.includes(args.run_id) ||
      (action === 'result' && (typeof args.receipt_sha256 !== 'string' || !SHA.test(args.receipt_sha256))) ||
      (action === 'reconcile' && (typeof args.predecessor_sha256 !== 'string' || !SHA.test(args.predecessor_sha256)))) {
    throw new TypeError('original collection arguments refused');
  }
  return { operation: action, ...args };
}

async function pinnedFile(filename, expected, { executable = false } = {}) {
  const handle = await open(filename, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const initial = await handle.stat({ bigint: true });
    const mode = Number(initial.mode);
    if (!initial.isFile() || initial.nlink !== 1n || (mode & 0o022) ||
        (executable ? !(mode & 0o111) : Number(initial.uid) !== process.getuid()) ||
        initial.size > 256n * 1024n * 1024n) throw new Error('original collection helper file refused');
    const bytes = await handle.readFile();
    const identity = info => [info.dev, info.ino, info.mode, info.uid, info.size,
      info.mtimeNs, info.ctimeNs].map(String).join(':');
    if (identity(initial) !== identity(await handle.stat({ bigint: true })) ||
        identity(initial) !== identity(await lstat(filename, { bigint: true })) ||
        digest(bytes) !== expected) throw new Error('original collection helper changed');
  } finally { await handle.close(); }
}

function unknown(run, reason) {
  return { run_id: run, state: 'UNKNOWN', effect_state: 'EFFECT_UNKNOWN',
    reason, retry_authorized: false, acceptance: 'NOT_RECORDED', lease_settlement: 'UNKNOWN' };
}

async function invoke(configuration, input) {
  // Authenticate the bootstrap and interpreter before executing either. The
  // bootstrap then verifies its whole control and native dependency closure.
  try {
    await pinnedFile(configuration.pythonPath, configuration.pythonSha256, { executable: true });
    await pinnedFile(configuration.controlPath, configuration.controlSha256);
  } catch {
    const error = new Error('original helper preflight refused');
    error.code = 'ORIGINAL_HELPER_PREFLIGHT';
    throw error;
  }
  return new Promise(resolve => {
    let failed = false, started = false, size = 0;
    const chunks = [];
    const child = childProcess.spawn(configuration.pythonPath,
      ['-I', '-S', '-B', configuration.controlPath, '_original-collection-helper'], {
        env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONNOUSERSITE: '1' },
        stdio: ['pipe', 'pipe', 'ignore'], windowsHide: true,
      });
    // Only this new local helper/read transport is ours to terminate. Never
    // receive an HTTP abort signal or signal an original worker/controller.
    const stopOwnedHelper = () => {
      failed = true;
      if (started) { try { child.kill('SIGKILL'); } catch {} }
    };
    const timer = setTimeout(stopOwnedHelper, 90000);
    child.once('spawn', () => { started = true; });
    child.once('error', () => { failed = true; });
    child.stdin.on('error', () => { failed = true; });
    child.stdout.on('data', chunk => {
      size += chunk.length;
      if (size > 16 * 1024 * 1024) return stopOwnedHelper();
      chunks.push(chunk);
    });
    child.once('close', code => {
      clearTimeout(timer);
      if (failed) return resolve(unknown(input.run_id, 'original_helper_outcome_unqualified'));
      try {
        const result = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks)));
        if (code === 75 && exact(result, ['run_id', 'state', 'effect_state', 'reason', 'retry_authorized']) &&
            result.run_id === input.run_id && result.reason === 'original_collection_unconfirmed' &&
            result.retry_authorized === false &&
            ((result.state === 'REFUSED' && result.effect_state === 'NOT_APPLIED') ||
             (result.state === 'UNKNOWN' && result.effect_state === 'EFFECT_UNKNOWN'))) return resolve(result);
        if (code !== 0) return resolve(unknown(input.run_id, 'original_helper_outcome_unqualified'));
        if (!result || typeof result !== 'object' || Array.isArray(result) || result.run_id !== input.run_id ||
            !['COMPLETE', 'PENDING', 'ABSENT', 'UNKNOWN', 'REFUSED'].includes(result.state)) throw new Error();
        resolve(result);
      } catch { resolve(unknown(input.run_id, 'original_helper_output_unqualified')); }
    });
    child.stdin.end(JSON.stringify({ configuration, ...input }));
  });
}

export function createOriginalDelivery(configuration, principalKey) {
  if (principalKey !== ORIGINAL_PRINCIPAL) throw new TypeError('original collection principal refused');
  // These two operation references belong to BackendOwner. The existing
  // destination reservation, not this map, is the durable once-only fence.
  const collections = new Map();
  const pending = new Set();
  // The single subordinate reconciliation attempt per enrolled run.
  const subordinate = new Map();
  let closed = false;
  let predecessor = null;
  let importFailure = null;
  // The preserving migration imports the machine owner's sealed predecessor
  // before any successor call is exposed. An invalid, missing or conflicting
  // import fails closed instead of leaving an empty apparently unused map.
  const sealed = configuration.predecessor;
  if (sealed !== undefined && sealed !== null) {
    try { predecessor = validatePredecessor(sealed); }
    catch { importFailure = 'original_predecessor_import_invalid'; }
  }
  if (importFailure === null) {
    for (const run of ORIGINAL_RUNS) {
      const observation = predecessor?.runs?.[run];
      collections.set(run, Promise.resolve(observation ??
        unknown(run, 'original_predecessor_slot_held')));
    }
  }
  async function execute(input) {
    try { return await invoke(configuration, input); }
    catch (error) {
      if (error?.code !== 'ORIGINAL_HELPER_PREFLIGHT') return unknown(input.run_id, 'original_helper_outcome_unqualified');
      return { run_id: input.run_id, state: 'REFUSED', effect_state: 'NOT_APPLIED',
        reason: 'original_helper_preflight_refused', retry_authorized: false };
    }
  }
  async function reconcile(input) {
    const observation = predecessor?.runs?.[input.run_id];
    if (!observation) throw new TypeError('original reconciliation is not enrolled for this run');
    if (input.run_id !== ORIGINAL_RECONCILE_RUN) {
      throw new TypeError('original reconciliation is not enrolled for this run');
    }
    if (input.predecessor_sha256 !== predecessor.receipt_sha256) {
      throw new TypeError('original predecessor digest refused');
    }
    if (observationShape(observation) !== 'status' || !['ABSENT', 'UNKNOWN'].includes(observation.state)) {
      throw new TypeError('original reconciliation is not eligible');
    }
    // One subordinate promise per run. Concurrent calls and a client
    // disconnect share the same attempt, and changed arguments never create
    // another one.
    let task = subordinate.get(input.run_id);
    if (!task) {
      task = execute(input);
      subordinate.set(input.run_id, task);
      pending.add(task);
      task.finally(() => pending.delete(task));
    }
    const value = await task;
    return { content: [{ type: 'text', text: JSON.stringify(value) }],
      isError: ['UNKNOWN', 'REFUSED'].includes(value.state) };
  }
  return Object.freeze({
    async call(name, args, actualPrincipal) {
      if (closed || actualPrincipal !== principalKey || actualPrincipal !== ORIGINAL_PRINCIPAL) {
        throw new TypeError('original collection principal refused');
      }
      const input = argumentsFor(name, args);
      // An invalid, missing or conflicting import fails closed for every
      // operation. The owner never presents an empty apparently unused map.
      if (importFailure) {
        return { content: [{ type: 'text', text: JSON.stringify({
          run_id: input.run_id, state: 'REFUSED', effect_state: 'NOT_APPLIED',
          reason: importFailure, retry_authorized: false, acceptance: 'NOT_RECORDED',
          original_operation_mutated: false, lease_settlement: 'UNKNOWN',
          controller_state: 'UNKNOWN' }) }], isError: true };
      }
      if (input.operation === 'reconcile') return reconcile(input);
      let task = input.operation === 'collect' ? collections.get(input.run_id) : null;
      if (!task) {
        task = execute(input);
        pending.add(task);
        if (input.operation === 'collect') collections.set(input.run_id, task);
        task.finally(() => pending.delete(task));
      }
      const value = await task;
      if (input.operation !== 'result' || value.state !== 'COMPLETE') {
        return { content: [{ type: 'text', text: JSON.stringify(value) }],
          isError: ['UNKNOWN', 'REFUSED'].includes(value.state) };
      }
      try {
        if (value.receipt_sha256 !== input.receipt_sha256 || typeof value.stdout_base64 !== 'string' ||
            !Number.isSafeInteger(value.stdout_bytes) || value.stdout_bytes < 0 || value.stdout_bytes > 8 * 1024 * 1024 ||
            !SHA.test(value.stdout_sha256)) throw new Error();
        const raw = Buffer.from(value.stdout_base64, 'base64');
        if (raw.toString('base64') !== value.stdout_base64 || raw.length !== value.stdout_bytes ||
            digest(raw) !== value.stdout_sha256) throw new Error();
        const text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
        return { content: [{ type: 'text', text }] };
      } catch {
        return { content: [{ type: 'text', text: 'Original result encoding or receipt refused.' }], isError: true };
      }
    },
    async close() { closed = true; await Promise.allSettled([...pending]); },
  });
}
