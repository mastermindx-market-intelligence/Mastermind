import { readFile, lstat } from 'node:fs/promises';
import path from 'node:path';

const DEFAULT_TIMEOUT_MS = 15_000;
const API_ROOT = 'https://managerapi.mosyle.com/v2';
const ALLOWED_OS = new Set(['mac', 'ios', 'tvos']);
const SERIAL_RE = /^[A-Za-z0-9._-]{1,80}$/;
const DEVICE_FIELDS = Object.freeze([
  'deviceudid', 'serial_number', 'device_name', 'tags', 'asset_tag', 'userid',
  'enrollment_type', 'username', 'date_app_info', 'date_last_beat',
  'lostmode_status', 'last_ip_beat', 'last_lan_ip',
]);
const DEVICE_FIELD_SET = new Set(DEVICE_FIELDS);
const RESOLVED_CONFIGS = new WeakSet();

export const MOSYLE_FLEET_STATUS_TOOL = Object.freeze({
  name: 'mosyle_fleet_status',
  title: 'Read Mosyle Fleet Status',
  description: 'Read a bounded page of Mosyle MDM device inventory/status. Read-only: no MDM commands are exposed.',
  inputSchema: {
    type: 'object',
    properties: {
      os: { type: 'string', enum: ['mac', 'ios', 'tvos'], default: 'mac' },
      page: { type: 'integer', minimum: 1, maximum: 1000, default: 1 },
      page_size: { type: 'integer', minimum: 1, maximum: 100, default: 50 },
      serial_numbers: { type: 'array', maxItems: 20, items: { type: 'string', minLength: 1, maxLength: 80 } },
    },
    additionalProperties: false,
  },
  annotations: { title: 'Read Mosyle Fleet Status', readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  _meta: { 'private-studio-mcp/gateway': true, 'mastermind/mosyle': true },
});

export const MOSYLE_DEVICE_STATUS_TOOL = Object.freeze({
  name: 'mosyle_device_status',
  title: 'Read Mosyle Device Status',
  description: 'Read Mosyle MDM status for one exact device serial number. Read-only: no MDM commands are exposed.',
  inputSchema: {
    type: 'object',
    properties: {
      serial_number: { type: 'string', minLength: 1, maxLength: 80 },
      os: { type: 'string', enum: ['mac', 'ios', 'tvos'], default: 'mac' },
    },
    required: ['serial_number'],
    additionalProperties: false,
  },
  annotations: { title: 'Read Mosyle Device Status', readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  _meta: { 'private-studio-mcp/gateway': true, 'mastermind/mosyle': true },
});

export const MOSYLE_TOOLS = Object.freeze([MOSYLE_FLEET_STATUS_TOOL, MOSYLE_DEVICE_STATUS_TOOL]);
export const MOSYLE_TOOL_NAMES = new Set(MOSYLE_TOOLS.map((tool) => tool.name));

function absoluteFile(value, label) {
  if (typeof value !== 'string' || !value || !path.isAbsolute(value) || value.includes('\\0')) {
    throw new TypeError(`${label} must be a non-empty absolute path`);
  }
  return value;
}

export function resolveMosyleConfig(value) {
  if (value === undefined || value === null || value === false) return null;
  if (typeof value === 'object' && value !== null && RESOLVED_CONFIGS.has(value)) return value;
  if (typeof value !== 'object' || Array.isArray(value)) throw new TypeError('config.mosyle must be an object, false, or absent');
  const allowed = new Set(['enabled', 'credentialPath', 'timeoutMs']);
  for (const key of Object.keys(value)) if (!allowed.has(key)) throw new TypeError(`config.mosyle.${key} is not supported`);
  if (value.enabled !== true) throw new TypeError('config.mosyle.enabled must be true when configured');
  const timeoutMs = value.timeoutMs === undefined ? DEFAULT_TIMEOUT_MS : value.timeoutMs;
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 60000) throw new TypeError('config.mosyle.timeoutMs must be 1000..60000');
  const out = Object.freeze({ enabled: true, credentialPath: absoluteFile(value.credentialPath, 'config.mosyle.credentialPath'), timeoutMs });
  RESOLVED_CONFIGS.add(out);
  return out;
}

function validateSerial(value) {
  const serial = String(value ?? '');
  if (!SERIAL_RE.test(serial)) throw new TypeError('invalid serial number');
  return serial;
}

function validateOs(value) {
  const os = String(value ?? 'mac').toLowerCase();
  if (!ALLOWED_OS.has(os)) throw new TypeError('invalid os');
  return os;
}

function sanitizeDevice(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const out = {};
  for (const [key, item] of Object.entries(value)) if (DEVICE_FIELD_SET.has(key)) out[key] = item;
  return out;
}

function extractDevices(payload) {
  const candidate = Array.isArray(payload) ? payload : Array.isArray(payload?.response) ? payload.response : Array.isArray(payload?.response?.devices) ? payload.response.devices : [];
  return candidate.map(sanitizeDevice).filter(Boolean);
}

export function mosyleToolResult(value, isError = false) {
  return { content: [{ type: 'text', text: JSON.stringify(value) }], isError: Boolean(isError) };
}

export function createMosyleClient(config, dependencies = {}) {
  const resolved = resolveMosyleConfig(config);
  if (!resolved) return null;
  const deps = { fetch: dependencies.fetch ?? globalThis.fetch, readFile: dependencies.readFile ?? readFile, lstat: dependencies.lstat ?? lstat };
  let cachedBearer = null;
  let bearerExpiresAt = 0;

  async function credentials() {
    const info = await deps.lstat(resolved.credentialPath);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error('MOSYLE_CREDENTIAL_IDENTITY_REFUSED');
    if (typeof info.uid === 'number' && typeof process.getuid === 'function' && info.uid !== process.getuid()) throw new Error('MOSYLE_CREDENTIAL_OWNER_REFUSED');
    if (typeof info.mode === 'number' && (info.mode & 0o077) !== 0) throw new Error('MOSYLE_CREDENTIAL_MODE_REFUSED');
    const parsed = JSON.parse(await deps.readFile(resolved.credentialPath, 'utf8'));
    const accessToken = String(parsed?.accessToken ?? '');
    const email = String(parsed?.email ?? '');
    const password = String(parsed?.password ?? '');
    if (!accessToken || !email || !password) throw new Error('MOSYLE_CREDENTIAL_INVALID');
    return { accessToken, email, password };
  }

  async function post(url, body, headers = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), resolved.timeoutMs);
    try {
      return await deps.fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(body), signal: controller.signal, redirect: 'error' });
    } finally { clearTimeout(timer); }
  }

  async function bearer(creds) {
    if (cachedBearer && Date.now() < bearerExpiresAt) return cachedBearer;
    const response = await post(`${API_ROOT}/login`, creds);
    if (!response.ok) throw new Error(`MOSYLE_LOGIN_HTTP_${response.status}`);
    const auth = response.headers.get('authorization') ?? '';
    const match = /^Bearer\s+(.+)$/i.exec(auth.trim());
    if (!match) throw new Error('MOSYLE_LOGIN_TOKEN_MISSING');
    cachedBearer = match[1].trim();
    bearerExpiresAt = Date.now() + 45 * 60 * 1000;
    return cachedBearer;
  }

  async function list(input) {
    const creds = await credentials();
    const token = await bearer(creds);
    const os = validateOs(input?.os);
    const page = Number.isInteger(input?.page) ? input.page : 1;
    const pageSize = Number.isInteger(input?.page_size) ? input.page_size : 50;
    if (page < 1 || page > 1000 || pageSize < 1 || pageSize > 100) throw new TypeError('invalid pagination');
    const options = { os, page, page_size: pageSize, specific_columns: [...DEVICE_FIELDS] };
    if (input?.serial_numbers !== undefined) {
      if (!Array.isArray(input.serial_numbers) || input.serial_numbers.length > 20) throw new TypeError('invalid serial_numbers');
      options.serial_numbers = input.serial_numbers.map(validateSerial);
    }
    const response = await post(`${API_ROOT}/listdevices`, { accessToken: creds.accessToken, options }, { Authorization: `Bearer ${token}` });
    if (!response.ok) throw new Error(`MOSYLE_LIST_HTTP_${response.status}`);
    const payload = await response.json();
    return { state: 'OBSERVED', provider: 'mosyle', os, page, page_size: pageSize, devices: extractDevices(payload), provider_status: typeof payload?.status === 'string' ? payload.status : null };
  }

  return Object.freeze({
    async call(name, input = {}) {
      try {
        if (name === MOSYLE_FLEET_STATUS_TOOL.name) return { value: await list(input), isError: false };
        if (name === MOSYLE_DEVICE_STATUS_TOOL.name) {
          const serial = validateSerial(input?.serial_number);
          const value = await list({ os: input?.os, page: 1, page_size: 10, serial_numbers: [serial] });
          return { value: { ...value, serial_number: serial, device: value.devices.find((d) => d.serial_number === serial) ?? value.devices[0] ?? null }, isError: false };
        }
        return { value: { state: 'MOSYLE_TOOL_NOT_FOUND' }, isError: true };
      } catch (err) {
        return { value: { state: 'MOSYLE_READ_FAILED', reason: err?.message || 'Error', retry_allowed: true }, isError: true };
      }
    },
  });
}
