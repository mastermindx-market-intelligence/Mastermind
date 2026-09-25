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

const PUBLIC_ACCOUNTS = new Set([
  'admin-business',
  'chatgpt1',
  'chatgpt2',
  'chatgpt2-personal',
  'chatgpt2-business',
  'chatgpt3',
  'chatgpt3-w570f6f34',
  'chatgpt3-wa2a9e6f9',
  'chatgpt4',
]);
const PUBLIC_TRANSPORT_TTL = '5h';
const TUNNEL_ID = /^tunnel_[0-9a-f]{32}$/;
const ORGANIZATION_ID = /^org-[A-Za-z0-9]+$/;
const MAX_ACCOUNTS = PUBLIC_ACCOUNTS.size;
const MAX_OWNER_ERROR_CHARS = 4096;

function invalidOwner() {
  throw new Error('FLEET_STATUS_OWNER_RESULT_INVALID');
}

function exactKeys(value, required, optional = []) {
  const allowed = new Set([...required, ...optional]);
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalidOwner();
  for (const key of required) {
    if (!Object.hasOwn(value, key)) invalidOwner();
  }
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) invalidOwner();
  }
}

function expectBoolean(value) {
  if (typeof value !== 'boolean') invalidOwner();
  return value;
}

function expectOptionalBoolean(value) {
  if (value !== null && typeof value !== 'boolean') invalidOwner();
  return value;
}

function expectBoundedInteger(value, min, max) {
  if (!Number.isInteger(value) || value < min || value > max) invalidOwner();
  return value;
}

function expectNullableInteger(value, min, max) {
  if (value === null) return null;
  return expectBoundedInteger(value, min, max);
}

function expectNullableBoundedString(value, maxChars, pattern = null) {
  if (value === null) return null;
  if (typeof value !== 'string' || value.length < 1 || value.length > maxChars) invalidOwner();
  if (pattern && !pattern.test(value)) invalidOwner();
  return value;
}

function expectAccount(value) {
  if (typeof value !== 'string' || !PUBLIC_ACCOUNTS.has(value)) invalidOwner();
  return value;
}

function projectErrorRow(row) {
  exactKeys(row, ['account', 'ready', 'error']);
  const account = expectAccount(row.account);
  if (row.ready !== false) invalidOwner();
  if (typeof row.error !== 'string' || row.error.length < 1 || row.error.length > MAX_OWNER_ERROR_CHARS) {
    invalidOwner();
  }
  return {
    account,
    state: 'DEGRADED',
    ready: false,
    gateway: null,
    tunnel: null,
    issues: ['OWNER_STATUS_UNAVAILABLE'],
  };
}

function projectStatusRow(row) {
  exactKeys(row, ['account', 'action', 'steps', 'ready', 'gateway', 'tunnel']);
  const account = expectAccount(row.account);
  if (row.action !== 'status' || !Array.isArray(row.steps) || row.steps.length !== 0) invalidOwner();
  const ready = expectBoolean(row.ready);

  exactKeys(row.gateway, ['account', 'label', 'loaded', 'pid', 'port', 'running']);
  if (row.gateway.account !== account) invalidOwner();
  expectNullableBoundedString(row.gateway.label, 128);
  const gatewayLoaded = expectBoolean(row.gateway.loaded);
  const gatewayRunning = expectBoolean(row.gateway.running);
  expectNullableInteger(row.gateway.pid, 1, 2 ** 31 - 1);
  expectNullableInteger(row.gateway.port, 1024, 65535);

  exactKeys(
    row.tunnel,
    [
      'account',
      'label',
      'loaded',
      'pid',
      'running',
      'healthy',
      'ready',
      'configurationDrift',
      'tunnelReady',
      'controlPlanePollReady',
      'gatewayReady',
      'transportTTL',
      'maxConcurrentRequests',
      'gatewayPort',
      'healthPort',
      'tunnelId',
      'managedAlias',
      'managedAliasRunning',
      'organizationId',
    ],
  );
  if (row.tunnel.account !== account) invalidOwner();
  expectNullableBoundedString(row.tunnel.label, 128);
  expectNullableInteger(row.tunnel.pid, 1, 2 ** 31 - 1);
  expectNullableInteger(row.tunnel.gatewayPort, 1024, 65535);
  expectNullableInteger(row.tunnel.healthPort, 1024, 65535);
  expectNullableBoundedString(row.tunnel.tunnelId, 64, TUNNEL_ID);
  expectNullableBoundedString(row.tunnel.organizationId ?? null, 128, ORGANIZATION_ID);
  expectNullableBoundedString(row.tunnel.managedAlias, 128);
  const tunnelLoaded = expectBoolean(row.tunnel.loaded);
  const tunnelRunning = expectBoolean(row.tunnel.running);
  const tunnelHealthy = expectBoolean(row.tunnel.healthy);
  const tunnelReady = expectBoolean(row.tunnel.ready);
  const configurationDrift = expectBoolean(row.tunnel.configurationDrift);
  const transportReady = expectBoolean(row.tunnel.tunnelReady);
  const gatewayReady = expectBoolean(row.tunnel.gatewayReady);
  const managedAliasRunning = expectBoolean(row.tunnel.managedAliasRunning);
  if (managedAliasRunning) invalidOwner();
  const pollReady = expectBoolean(row.tunnel.controlPlanePollReady);
  const transportTTL = row.tunnel.transportTTL;
  if (transportTTL !== PUBLIC_TRANSPORT_TTL) invalidOwner();
  const maxConcurrentRequests = row.tunnel.maxConcurrentRequests === null
    ? null
    : expectBoundedInteger(row.tunnel.maxConcurrentRequests, 1, 64);

  if (gatewayRunning && !gatewayLoaded) invalidOwner();
  if (tunnelRunning && !tunnelLoaded) invalidOwner();
  if (tunnelReady !== (transportReady && gatewayReady)) invalidOwner();
  const computedReady = (
    gatewayLoaded
    && gatewayRunning
    && tunnelLoaded
    && tunnelRunning
    && tunnelHealthy
    && tunnelReady
    && !configurationDrift
    && transportReady
    && pollReady
    && gatewayReady
  );
  if (ready !== computedReady) invalidOwner();

  const issues = [];
  if (configurationDrift) issues.push('CONFIGURATION_DRIFT');
  if (!gatewayLoaded) issues.push('GATEWAY_NOT_LOADED');
  if (!gatewayRunning) issues.push('GATEWAY_NOT_RUNNING');
  if (!tunnelLoaded) issues.push('TUNNEL_NOT_LOADED');
  if (!tunnelRunning) {
    issues.push('TUNNEL_NOT_RUNNING');
  } else if (!configurationDrift) {
    if (!tunnelHealthy) issues.push('TUNNEL_NOT_HEALTHY');
    if (pollReady === false) issues.push('CONTROL_PLANE_POLL_NOT_READY');
    if (!transportReady) issues.push('TUNNEL_NOT_READY');
    if (!gatewayReady) issues.push('GATEWAY_NOT_READY');
  }

  return {
    account,
    state: ready ? 'READY' : 'DEGRADED',
    ready,
    gateway: {
      loaded: gatewayLoaded,
      running: gatewayRunning,
    },
    tunnel: {
      loaded: tunnelLoaded,
      running: tunnelRunning,
      healthy: tunnelHealthy,
      ready: tunnelReady,
      controlPlanePollReady: pollReady,
      gatewayReady,
      transportTTL,
      maxConcurrentRequests,
    },
    issues,
  };
}

function validateAndProjectOwnerResult(value) {
  exactKeys(value, ['schema', 'action', 'accountCount', 'readyCount', 'allReady', 'accounts']);
  if (value.schema !== OWNER_SCHEMA || value.action !== 'status' || !Array.isArray(value.accounts)) {
    invalidOwner();
  }
  const accountCount = expectBoundedInteger(value.accountCount, 0, MAX_ACCOUNTS);
  const readyCount = expectBoundedInteger(value.readyCount, 0, MAX_ACCOUNTS);
  const allReady = expectBoolean(value.allReady);
  if (value.accounts.length !== accountCount || readyCount > accountCount) invalidOwner();

  const accounts = value.accounts.map((row) =>
    Object.hasOwn(row ?? {}, 'error') ? projectErrorRow(row) : projectStatusRow(row));
  const seen = new Set();
  for (const row of accounts) {
    if (seen.has(row.account)) invalidOwner();
    seen.add(row.account);
  }
  const computedReadyCount = accounts.filter((row) => row.ready).length;
  const computedAllReady = accountCount > 0 && computedReadyCount === accountCount;
  if (readyCount !== computedReadyCount || allReady !== computedAllReady) invalidOwner();

  return {
    accountCount,
    readyCount,
    allReady,
    accounts,
  };
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
      const projection = validateAndProjectOwnerResult(owner);
      return {
        schema: RESULT_SCHEMA,
        state: projection.allReady ? 'READY' : 'DEGRADED',
        ...projection,
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
