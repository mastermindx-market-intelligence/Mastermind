// Fixed original-result operations inside the incumbent authenticated C3 owner.
// Selectors/stdin are correlation, never identity. The gateway authenticates.
import childProcess from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { open, lstat } from 'node:fs/promises';
import path from 'node:path';

export const ORIGINAL_ACCOUNT = 'fabric-c3-570f6f34';
export const ORIGINAL_PRINCIPAL = 'p:tunnel:' + ORIGINAL_ACCOUNT;
export const ORIGINAL_RUNS = Object.freeze([
  'fabric-app-native-drivers-j-20261105-01',
  'fabric-app-application-process-carrier-20261105-01',
]);
const ACTIONS = Object.freeze({ fabric_collect_original: 'collect',
  fabric_original_collection_status: 'status', fabric_original_collection_result: 'result' });
export const ORIGINAL_TOOL_NAMES = new Set(Object.keys(ACTIONS));
const SHA = /^[0-9a-f]{64}$/;
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const FIELDS = ['enabled', 'schema', 'pythonPath', 'pythonSha256', 'controlPath',
  'controlSha256', 'controlBundleDigest', 'nativeStore', 'nativeGeneration'].sort();
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const canonicalPath = value => typeof value === 'string' && !value.includes('\0') &&
  path.isAbsolute(value) && path.normalize(value) === value;

export function originalCollectionConfig(cfg) {
  const value = cfg.originalCollection;
  if (value === undefined || value === false || value === null) return null;
  if (cfg.accountLabel !== ORIGINAL_ACCOUNT || cfg.host !== '127.0.0.1' || cfg.port !== 45280 ||
      cfg.modernFabricProtocol !== true || cfg.fabricOnly !== true || cfg.backendMode !== 'shared-account' ||
      cfg.testMode || cfg.publicUrl || cfg.gitPublish || cfg.repositoryWorkspaces ||
      cfg.commissionPublication || cfg.paperDesign || cfg.fleetStatus || !canonicalPath(cfg.cwd) ||
      !exact(value, FIELDS) || value.enabled !== true || value.schema !== 'mastermind.fabric_original_collection.v1' ||
      ['pythonSha256', 'controlSha256', 'controlBundleDigest', 'nativeGeneration'].some(key => !SHA.test(value[key])) ||
      ['pythonPath', 'controlPath', 'nativeStore'].some(key => !canonicalPath(value[key])) ||
      value.controlPath !== path.join(cfg.cwd, '.local/share/studio-direct-mcp/control/private_service.py') ||
      value.nativeStore !== path.join(cfg.cwd, '.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/' +
        'handoff_kits/meta-ceo-b-2026-09-08/native-code-releases')) {
    throw new TypeError('original collection requires its exact enrolled private C3 configuration');
  }
  return Object.freeze({ ...value });
}

export const ORIGINAL_TOOLS = Object.freeze(Object.entries(ACTIONS).map(([name, action]) => ({
  name,
  description: action === 'collect' ? 'Collect one of the two source-qualified original returns once; never launch or retry work.' :
    action === 'status' ? 'Read the fixed original collection destination; absence never authorizes a retry.' :
      'Read a COMPLETE original return pinned by its exact receipt SHA256; does not accept code or settle a lease.',
  inputSchema: { type: 'object', additionalProperties: false,
    required: action === 'result' ? ['run_id', 'receipt_sha256'] : ['run_id'],
    properties: { run_id: { type: 'string', enum: [...ORIGINAL_RUNS] },
      ...(action === 'result' ? { receipt_sha256: { type: 'string', pattern: '^[0-9a-f]{64}$' } } : {}) } },
  annotations: { readOnlyHint: action !== 'collect', destructiveHint: false,
    idempotentHint: action !== 'collect', openWorldHint: false },
})));

function argumentsFor(name, args) {
  const action = ACTIONS[name];
  if (!action || !exact(args, action === 'result' ? ['run_id', 'receipt_sha256'] : ['run_id']) ||
      !ORIGINAL_RUNS.includes(args.run_id) ||
      (action === 'result' && (typeof args.receipt_sha256 !== 'string' || !SHA.test(args.receipt_sha256)))) {
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
  let closed = false;
  async function execute(input) {
    try { return await invoke(configuration, input); }
    catch (error) {
      if (error?.code !== 'ORIGINAL_HELPER_PREFLIGHT') return unknown(input.run_id, 'original_helper_outcome_unqualified');
      return { run_id: input.run_id, state: 'REFUSED', effect_state: 'NOT_APPLIED',
        reason: 'original_helper_preflight_refused', retry_authorized: false };
    }
  }
  return Object.freeze({
    async call(name, args, actualPrincipal) {
      if (closed || actualPrincipal !== principalKey || actualPrincipal !== ORIGINAL_PRINCIPAL) {
        throw new TypeError('original collection principal refused');
      }
      const input = argumentsFor(name, args);
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
