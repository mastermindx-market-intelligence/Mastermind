import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { lstat, readFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const SHA256 = /^[0-9a-f]{64}$/;
const OWNER_SCHEMA = 'mastermind.studio_direct_fleet_status.v1';
const RESULT_SCHEMA = 'mastermind.studio_fleet_status_tool.v1';
const MAX_OUTPUT_BYTES = 256 * 1024;

export const STUDIO_FLEET_STATUS_TOOL = Object.freeze({
  name: 'studio_fleet_status',
  title: 'Studio Fleet Status',
  description:
    'Reads aggregate Studio Direct gateway and tunnel status through the installed Studio Direct owner. ' +
    'This action is read-only: it does not start, stop, restart, create, delete, or rebind any service, tunnel, app, or credential.',
  inputSchema: {
    type: 'object',
    properties: {},
    required: [],
    additionalProperties: false,
  },
  annotations: {
    title: 'Studio Fleet Status',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true },
});

export function resolveFleetStatusConfig(raw) {
  if (raw == null || raw === false || raw?.enabled === false) return null;
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    throw new TypeError('config.fleetStatus must be an object when enabled');
  }
  const allowed = new Set(['enabled', 'launcherPath', 'launcherSha256', 'timeoutMs']);
  for (const key of Object.keys(raw)) {
    if (!allowed.has(key)) throw new TypeError(`config.fleetStatus contains unknown key: ${key}`);
  }
  if (raw.enabled !== true) throw new TypeError('config.fleetStatus.enabled must be true');
  if (typeof raw.launcherPath !== 'string' || !path.isAbsolute(raw.launcherPath)) {
    throw new TypeError('config.fleetStatus.launcherPath must be absolute');
  }
  if (typeof raw.launcherSha256 !== 'string' || !SHA256.test(raw.launcherSha256)) {
    throw new TypeError('config.fleetStatus.launcherSha256 must be lowercase sha256');
  }
  const timeoutMs = Number(raw.timeoutMs);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 30000) {
    throw new TypeError('config.fleetStatus.timeoutMs must be an integer from 1000 to 30000');
  }
  return Object.freeze({
    launcherPath: raw.launcherPath,
    launcherSha256: raw.launcherSha256,
    timeoutMs,
  });
}

async function verifyLauncher(cfg) {
  const info = await lstat(cfg.launcherPath);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('FLEET_STATUS_LAUNCHER_UNSAFE');
  if (typeof process.getuid === 'function' && info.uid !== process.getuid()) {
    throw new Error('FLEET_STATUS_LAUNCHER_OWNER_MISMATCH');
  }
  const bytes = await readFile(cfg.launcherPath);
  const digest = createHash('sha256').update(bytes).digest('hex');
  if (digest !== cfg.launcherSha256) throw new Error('FLEET_STATUS_LAUNCHER_DRIFT');
}

function validateOwnerResult(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('FLEET_STATUS_OWNER_RESULT_INVALID');
  }
  if (value.schema !== OWNER_SCHEMA || value.action !== 'status' || !Array.isArray(value.accounts)) {
    throw new Error('FLEET_STATUS_OWNER_RESULT_INVALID');
  }
  return value;
}

export function createFleetStatus(rawConfig) {
  const cfg = resolveFleetStatusConfig(rawConfig);
  if (!cfg) return null;
  return Object.freeze({
    async status() {
      await verifyLauncher(cfg);
      const { stdout } = await execFileAsync(
        cfg.launcherPath,
        ['status', '--all'],
        {
          timeout: cfg.timeoutMs,
          maxBuffer: MAX_OUTPUT_BYTES,
          windowsHide: true,
          env: {
            HOME: process.env.HOME ?? '',
            PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
          },
        },
      );
      let owner;
      try {
        owner = JSON.parse(stdout);
      } catch {
        throw new Error('FLEET_STATUS_OWNER_RESULT_INVALID');
      }
      validateOwnerResult(owner);
      return {
        schema: RESULT_SCHEMA,
        state: owner.allReady === true ? 'READY' : 'DEGRADED',
        owner,
      };
    },
  });
}

export function fleetStatusToolResult(value, isError = false) {
  const text = JSON.stringify(value, null, 2);
  return {
    content: [{ type: 'text', text }],
    structuredContent: value,
    ...(isError ? { isError: true } : {}),
  };
}

export function fleetStatusErrorResult(error) {
  const code = typeof error?.message === 'string' && /^FLEET_STATUS_[A-Z0-9_]+$/.test(error.message)
    ? error.message
    : 'FLEET_STATUS_UNAVAILABLE';
  return fleetStatusToolResult({
    schema: RESULT_SCHEMA,
    state: 'REFUSED',
    code,
  }, true);
}
