import { createHash, timingSafeEqual } from 'node:crypto';
import { spawn } from 'node:child_process';
import { readFileSync, constants } from 'node:fs';
import { open } from 'node:fs/promises';
import path from 'node:path';

// Generated from the same release's Python contract; parity is regression-tested.
const catalog = JSON.parse(readFileSync(new URL('./t3-dot-tools.json', import.meta.url), 'utf8'));
export const T3_CONTROL_TOOLS = Object.freeze(catalog.tools.map(tool => Object.freeze(tool)));
export const T3_CONTROL_NAMES = new Set(T3_CONTROL_TOOLS.map(tool => tool.name));
const BY_NAME = new Map(T3_CONTROL_TOOLS.map(tool => [tool.name, tool]));
const MAX_BYTES = 256 * 1024;
const SHA = /^[0-9a-f]{64}$/;
const PRINCIPAL = /^p:tunnel:[a-z0-9][a-z0-9_-]{0,63}$/;
const RESOLVED = new WeakSet();
const STATUSES = new Set(['OBSERVED', 'EFFECT_UNKNOWN', 'REJECTED', 'CONFLICT', 'UNAVAILABLE', 'INVALID_ARGUMENT']);

function absolute(value) {
  return typeof value === 'string' && value.length > 0 && value.length <= 4096 &&
    path.isAbsolute(value) && !value.split(path.sep).includes('..') && !/[\x00-\x1f\x7f]/.test(value);
}

export function resolveT3ControlConfig(value) {
  if (value === undefined || value === false) return null;
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join(',') !== 'enabled,profilePath,profileSha256,pythonPath,sourceRoot' ||
      value.enabled !== true || !absolute(value.pythonPath) || !absolute(value.sourceRoot) ||
      !absolute(value.profilePath) || typeof value.profileSha256 !== 'string' || !SHA.test(value.profileSha256)) {
    throw new TypeError('T3 control requires an explicitly enabled, exact installed profile');
  }
  const resolved = Object.freeze({ ...value });
  RESOLVED.add(resolved);
  return resolved;
}

async function currentProfile(config, principalKey) {
  if (typeof principalKey !== 'string' || !PRINCIPAL.test(principalKey)) throw new Error('T3_ACCOUNT_UNBOUND');
  const handle = await open(config.profilePath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.uid !== process.getuid() || (stat.mode & 0o022) !== 0 ||
        stat.size < 1 || stat.size > 65536) throw new Error('T3_PROFILE_CUSTODY');
    // A bounded read rather than readFile avoids a growing file escaping the cap.
    const bytes = Buffer.alloc(65537);
    const { bytesRead } = await handle.read(bytes, 0, bytes.length, 0);
    if (bytesRead > 65536) throw new Error('T3_PROFILE_LIMIT');
    const raw = bytes.subarray(0, bytesRead);
    const digest = createHash('sha256').update(raw).digest();
    if (!timingSafeEqual(digest, Buffer.from(config.profileSha256, 'hex'))) throw new Error('T3_PROFILE_CHANGED');
    const profile = JSON.parse(raw.toString('utf8'));
    if (profile.schema !== 'mastermind.t3_dot_native_profile.v1' || profile.principal_key !== principalKey ||
        !Array.isArray(profile.operations) || profile.operations.length === 0 ||
        profile.operations.some(name => typeof name !== 'string' || !T3_CONTROL_NAMES.has(name)) ||
        new Set(profile.operations).size !== profile.operations.length ||
        !Number.isInteger(profile.timeout_seconds) || profile.timeout_seconds < 5 || profile.timeout_seconds > 90) {
      throw new Error('T3_PROFILE_OR_ACCOUNT_UNQUALIFIED');
    }
    return profile;
  } finally { await handle.close(); }
}

function failure(status, code, original = {}) {
  return { schema: 'mastermind.t3_dot_result.v1', status, code, original,
    retry_allowed: false, parent_accepted: false };
}

export function t3ToolResult(value) {
  return { content: [{ type: 'text', text: JSON.stringify(value) }], structuredContent: value,
    isError: value.status !== 'OBSERVED' };
}

/** One fixed port invocation; the existing gateway owns its lifecycle and timeout.
 * No shell, auth flow, retry, service, scheduler, alternate host or fallback exists.
 * Cancellation after spawning is conservatively an uncertain native mutation.
 */
export function createT3Controller(config, principalKey, { spawnProcess = spawn } = {}) {
  if (!RESOLVED.has(config)) throw new TypeError('Resolved T3 configuration required');
  return {
    async tools() {
      const profile = await currentProfile(config, principalKey);
      return T3_CONTROL_TOOLS.filter(tool => profile.operations.includes(tool.name)).map(tool => structuredClone(tool));
    },
    async call(name, args, { signal } = {}) {
      const tool = BY_NAME.get(name);
      if (!tool) return failure('UNAVAILABLE', 'T3_TOOL_NOT_EXPOSED');
      const modifying = tool.annotations.readOnlyHint !== true;
      const original = { operation: name, operation_id: args?.operation_id,
        environment_id: args?.environment_id, project_id: args?.project_id, thread_id: args?.thread_id };
      let profile, input;
      try {
        profile = await currentProfile(config, principalKey);
        if (!profile.operations.includes(name)) return failure('REJECTED', 'T3_OPERATION_NOT_GRANTED', original);
        if (!args || typeof args !== 'object' || Array.isArray(args)) return failure('INVALID_ARGUMENT', 'T3_ARGUMENTS_REQUIRED');
        input = JSON.stringify({ schema: 'mastermind.t3_dot_call.v1', principal_key: principalKey, tool: name, arguments: args });
        if (Buffer.byteLength(input) > MAX_BYTES) return failure('INVALID_ARGUMENT', 'T3_ARGUMENT_LIMIT');
      } catch { return failure('REJECTED', 'T3_ACCOUNT_PROFILE_UNAVAILABLE', original); }
      if (signal?.aborted) return failure('UNAVAILABLE', 'T3_CANCELLED_BEFORE_DISPATCH', original);
      return new Promise(resolve => {
        let child, spawned = false, settled = false, timedOut = false, output = [], bytes = 0, stderrBytes = 0;
        let deadline, killTimer;
        const finish = async (value) => {
          if (settled) return;
          settled = true;
          clearTimeout(deadline); clearTimeout(killTimer);
          signal?.removeEventListener('abort', cancel);
          if (value.status === 'OBSERVED') {
            try { await currentProfile(config, principalKey); }
            catch { value = failure(modifying ? 'EFFECT_UNKNOWN' : 'REJECTED', 'T3_POST_EFFECT_PROFILE_CHANGED', original); }
          }
          if (value.status === 'EFFECT_UNKNOWN') {
            value = { ...value, original: { ...original, ...(value.original ?? {}) },
              port_helper: { pid: child?.pid ?? null, observed_spawn: spawned, timed_out: timedOut } };
          }
          resolve(value);
        };
        const uncertain = code => failure(modifying && spawned ? 'EFFECT_UNKNOWN' : 'UNAVAILABLE', code, original);
        const terminateOwned = () => {
          if (!child || child.exitCode !== null || child.signalCode !== null) return;
          child.stdin.end();
          child.kill('SIGTERM');
          killTimer = setTimeout(() => child.kill('SIGKILL'), 2500);
          killTimer.unref?.();
        };
        const cancel = () => { timedOut = true; terminateOwned(); };
        try {
          child = spawnProcess(config.pythonPath, ['-B', '-m', 'integrations.session_bridge.t3_dot_port',
            '--profile', config.profilePath, '--profile-sha256', config.profileSha256], {
            cwd: config.sourceRoot, shell: false, stdio: ['pipe', 'pipe', 'pipe'],
            env: { HOME: process.env.HOME, PATH: '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin',
              TMPDIR: process.env.TMPDIR || '/tmp', PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1',
              PYTHONPATH: config.sourceRoot, NO_COLOR: '1' },
          });
        } catch { finish(uncertain('T3_PORT_START_UNAVAILABLE')); return; }
        child.once('spawn', () => { spawned = true; });
        child.once('error', () => finish(uncertain('T3_PORT_START_UNAVAILABLE')));
        child.stdout.on('data', chunk => {
          bytes += chunk.length;
          if (bytes > MAX_BYTES) { timedOut = true; terminateOwned(); return; }
          output.push(Buffer.from(chunk));
        });
        child.stderr.on('data', chunk => {
          stderrBytes += chunk.length;
          if (stderrBytes > 65536) { timedOut = true; terminateOwned(); }
        });
        child.stdin.on('error', () => { timedOut = true; terminateOwned(); });
        child.once('close', code => {
          if (settled) return;
          if (timedOut || code !== 0 || bytes > MAX_BYTES) { finish(uncertain('T3_PORT_RETURN_UNQUALIFIED')); return; }
          try {
            const value = JSON.parse(Buffer.concat(output).toString('utf8'));
            if (!value || value.schema !== 'mastermind.t3_dot_result.v1' || !STATUSES.has(value.status) ||
                value.retry_allowed !== false || value.parent_accepted !== false ||
                value.status === 'OBSERVED' && value.operation !== name) throw new Error();
            finish(value);
          } catch { finish(uncertain('T3_PORT_RETURN_UNQUALIFIED')); }
        });
        deadline = setTimeout(() => { timedOut = true; terminateOwned(); }, (profile.timeout_seconds + 5) * 1000);
        deadline.unref?.();
        signal?.addEventListener('abort', cancel, { once: true });
        child.stdin.end(input);
      });
    },
  };
}
