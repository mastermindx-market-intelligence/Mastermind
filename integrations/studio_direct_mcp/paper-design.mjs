import { createHash } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import path from 'node:path';
import { lstat, readFile } from 'node:fs/promises';
import { promisify } from 'node:util';

const execFileDefault = promisify(execFileCallback);
const SHA256_RE = /^[0-9a-f]{64}$/;
const OPERATION_RE = /^[A-Za-z0-9_.:-]{1,120}$/;
const SNAPSHOT_RE = /^[0-9a-f]{64}$/;
const MAX_ARGUMENT_BYTES = 1 << 19;
const MAX_STDIO_BYTES = 12 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 70_000;
const RESOLVED_CONFIGS = new WeakSet();

export const PAPER_INSPECT_TOOL = Object.freeze({
  name: 'paper_inspect',
  title: 'Inspect Paper Design',
  description:
    'Read Paper Desktop availability and the active design identity through the guarded Mastermind adapter. ' +
    'Returns a fresh snapshot guard for later edits. This tool does not modify the design.',
  inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  annotations: {
    title: 'Inspect Paper Design',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'mastermind/paper-design': true },
});

export const PAPER_CATALOG_TOOL = Object.freeze({
  name: 'paper_catalog',
  title: 'Inspect Paper Tool Catalog',
  description:
    'Read the exact Paper Desktop tool schemas and the adapter write-schema receipt. ' +
    'The receipt exposes whether the pinned upstream write schema is currently compatible.',
  inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  annotations: {
    title: 'Inspect Paper Tool Catalog',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'mastermind/paper-design': true },
});

export const PAPER_READ_TOOL = Object.freeze({
  name: 'paper_read',
  title: 'Read Paper Design',
  description:
    'Run one allowed read-only Paper operation against the active design using the guarded adapter. ' +
    'Examples include node inspection, screenshots and JSX extraction. Unknown or modifying upstream tools are refused.',
  inputSchema: {
    type: 'object',
    properties: {
      tool: { type: 'string', minLength: 1, maxLength: 80 },
      arguments: { type: 'object' },
      expected_snapshot: {
        type: 'string',
        pattern: '^[0-9a-f]{64}$',
        description: 'Optional observed Paper snapshot used only as a drift guard.',
      },
    },
    required: ['tool', 'arguments'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Read Paper Design',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'mastermind/paper-design': true },
});

export const PAPER_EDIT_TOOL = Object.freeze({
  name: 'paper_edit',
  title: 'Edit Paper Design',
  description:
    'Apply one explicitly requested Paper design edit through the guarded adapter. ' +
    'Requires the exact inspected snapshot and a stable operation id. The adapter refuses destructive node deletion, ' +
    'native host export, file-open transitions and token deletion. A lost or ambiguous response is reported as EFFECT_UNKNOWN with retry_allowed=false; the gateway provides no replay path.',
  inputSchema: {
    type: 'object',
    properties: {
      tool: { type: 'string', minLength: 1, maxLength: 80 },
      arguments: { type: 'object' },
      expected_snapshot: { type: 'string', pattern: '^[0-9a-f]{64}$' },
      operation_id: { type: 'string', minLength: 1, maxLength: 120, pattern: '^[A-Za-z0-9_.:-]{1,120}$' },
    },
    required: ['tool', 'arguments', 'expected_snapshot', 'operation_id'],
    additionalProperties: false,
  },
  annotations: {
    title: 'Edit Paper Design',
    readOnlyHint: false,
    destructiveHint: true,
    idempotentHint: false,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true, 'mastermind/paper-design': true },
});

export const PAPER_DESIGN_TOOLS = Object.freeze([
  PAPER_INSPECT_TOOL,
  PAPER_CATALOG_TOOL,
  PAPER_READ_TOOL,
  PAPER_EDIT_TOOL,
]);

export const PAPER_DESIGN_TOOL_NAMES = new Set(PAPER_DESIGN_TOOLS.map((tool) => tool.name));

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

export function resolvePaperDesignConfig(value) {
  if (value === undefined || value === null || value === false) return null;
  if (typeof value === 'object' && value !== null && RESOLVED_CONFIGS.has(value)) return value;
  if (typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('config.paperDesign must be an object, false, or absent');
  }
  assertExactKeys(
    value,
    new Set(['enabled', 'pythonPath', 'bridgePath', 'bridgeSha256', 'commandTimeoutMs']),
    'config.paperDesign',
  );
  if (value.enabled !== true) {
    throw new TypeError('config.paperDesign.enabled must be true when paperDesign is configured');
  }
  if (!SHA256_RE.test(String(value.bridgeSha256 ?? ''))) {
    throw new TypeError('config.paperDesign.bridgeSha256 must be a lowercase SHA-256 digest');
  }
  const commandTimeoutMs = value.commandTimeoutMs === undefined
    ? DEFAULT_TIMEOUT_MS
    : value.commandTimeoutMs;
  if (!Number.isInteger(commandTimeoutMs) || commandTimeoutMs < 1_000 || commandTimeoutMs > 120_000) {
    throw new TypeError('config.paperDesign.commandTimeoutMs must be an integer between 1000 and 120000');
  }
  const out = Object.freeze({
    enabled: true,
    pythonPath: requireAbsoluteString(value.pythonPath, 'config.paperDesign.pythonPath'),
    bridgePath: requireAbsoluteString(value.bridgePath, 'config.paperDesign.bridgePath'),
    bridgeSha256: value.bridgeSha256,
    commandTimeoutMs,
  });
  RESOLVED_CONFIGS.add(out);
  return out;
}

function stableJson(value) {
  const text = JSON.stringify(value);
  if (typeof text !== 'string' || Buffer.byteLength(text, 'utf8') > MAX_ARGUMENT_BYTES) {
    throw new TypeError('Paper tool arguments exceed the bounded request size');
  }
  return text;
}

function minimalEnv() {
  const out = {};
  for (const key of ['HOME', 'PATH', 'USER', 'LOGNAME', 'TMPDIR']) {
    if (typeof process.env[key] === 'string') out[key] = process.env[key];
  }
  return out;
}

async function verifyBridge(config, deps) {
  const info = await deps.lstat(config.bridgePath);
  if (!info.isFile() || info.isSymbolicLink()) {
    throw new Error('PAPER_BRIDGE_IDENTITY_REFUSED');
  }
  const bytes = await deps.readFile(config.bridgePath);
  const actual = createHash('sha256').update(bytes).digest('hex');
  if (actual !== config.bridgeSha256) {
    throw new Error('PAPER_BRIDGE_HASH_MISMATCH');
  }
}

function parseResult(stdout) {
  if (typeof stdout !== 'string' || stdout.length === 0) return null;
  try {
    const parsed = JSON.parse(stdout);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function resultState(value) {
  return typeof value?.state === 'string' ? value.state : null;
}

function definitelySuccessful(value) {
  const state = resultState(value);
  return state === null || ['CONNECTED', 'OBSERVED', 'APPLIED_RESPONSE_OBSERVED'].includes(state);
}

function sanitizeMcpContent(value) {
  const copied = JSON.parse(JSON.stringify(value));
  const images = [];
  const content = copied?.result?.content;
  if (Array.isArray(content)) {
    for (const block of content) {
      if (!block || block.type !== 'image') continue;
      if ((block.mimeType === 'image/png' || block.mimeType === 'image/jpeg') &&
          typeof block.data === 'string' && block.data.length > 0) {
        images.push({
          type: 'image',
          data: block.data,
          mimeType: block.mimeType,
        });
        delete block.data;
        block.rendered_as_mcp_image = true;
      }
    }
  }
  return { copied, images };
}

export function paperToolResult(value, isError = false) {
  const { copied, images } = sanitizeMcpContent(value);
  return {
    content: [
      { type: 'text', text: JSON.stringify(copied) },
      ...images,
    ],
    isError: Boolean(isError),
  };
}

function localFailure(editing, code) {
  if (editing) {
    return {
      value: {
        state: 'EFFECT_UNKNOWN',
        retry_allowed: false,
        reason: code,
      },
      isError: true,
      effectUnknown: true,
    };
  }
  return {
    value: {
      state: code,
      retry_allowed: false,
    },
    isError: true,
    effectUnknown: false,
  };
}

export function createPaperDesigner(config, dependencies = {}) {
  const resolved = resolvePaperDesignConfig(config);
  if (!resolved) return null;
  const deps = {
    execFile: dependencies.execFile ?? execFileDefault,
    readFile: dependencies.readFile ?? readFile,
    lstat: dependencies.lstat ?? lstat,
  };

  async function dispatch(action, args, { editing = false } = {}) {
    try {
      await verifyBridge(resolved, deps);
    } catch {
      // Bridge identity is checked before any subprocess or Paper call begins.
      // A mismatch is a definite refusal, never an ambiguous modifying effect.
      return localFailure(false, 'PAPER_BRIDGE_IDENTITY_REFUSED');
    }

    let stdout = '';
    try {
      const out = await deps.execFile(
        resolved.pythonPath,
        [resolved.bridgePath, ...args],
        {
          timeout: resolved.commandTimeoutMs,
          maxBuffer: MAX_STDIO_BYTES,
          env: minimalEnv(),
          windowsHide: true,
        },
      );
      stdout = out?.stdout ?? '';
    } catch (err) {
      stdout = typeof err?.stdout === 'string' ? err.stdout : '';
      const parsed = parseResult(stdout);
      if (parsed) {
        const state = resultState(parsed);
        return {
          value: parsed,
          isError: !definitelySuccessful(parsed),
          effectUnknown: state === 'EFFECT_UNKNOWN',
        };
      }
      return localFailure(editing, err?.killed ? 'PAPER_LOCAL_TIMEOUT' : 'PAPER_LOCAL_FAILURE');
    }

    const parsed = parseResult(stdout);
    if (!parsed) return localFailure(editing, 'PAPER_INVALID_LOCAL_RESPONSE');
    const state = resultState(parsed);
    return {
      value: parsed,
      isError: !definitelySuccessful(parsed),
      effectUnknown: state === 'EFFECT_UNKNOWN',
    };
  }

  return Object.freeze({
    async call(name, input = {}) {
      if (name === PAPER_INSPECT_TOOL.name) {
        return dispatch('status', ['status']);
      }
      if (name === PAPER_CATALOG_TOOL.name) {
        return dispatch('catalog', ['catalog']);
      }
      if (name === PAPER_READ_TOOL.name) {
        if (typeof input?.tool !== 'string' || !input.tool ||
            typeof input?.arguments !== 'object' || input.arguments === null || Array.isArray(input.arguments)) {
          return localFailure(false, 'PAPER_INVALID_ARGUMENTS');
        }
        let encodedArguments;
        try {
          encodedArguments = stableJson(input.arguments);
        } catch {
          return localFailure(false, 'PAPER_INVALID_ARGUMENTS');
        }
        const args = ['read', '--tool', input.tool, '--arguments', encodedArguments];
        if (input.expected_snapshot !== undefined) {
          if (!SNAPSHOT_RE.test(String(input.expected_snapshot))) {
            return localFailure(false, 'PAPER_INVALID_SNAPSHOT');
          }
          args.push('--expected-snapshot', input.expected_snapshot);
        }
        return dispatch('read', args);
      }
      if (name === PAPER_EDIT_TOOL.name) {
        if (typeof input?.tool !== 'string' || !input.tool ||
            typeof input?.arguments !== 'object' || input.arguments === null || Array.isArray(input.arguments) ||
            !SNAPSHOT_RE.test(String(input.expected_snapshot ?? '')) ||
            !OPERATION_RE.test(String(input.operation_id ?? ''))) {
          return localFailure(false, 'PAPER_INVALID_ARGUMENTS');
        }
        let encodedArguments;
        try {
          encodedArguments = stableJson(input.arguments);
        } catch {
          return localFailure(false, 'PAPER_INVALID_ARGUMENTS');
        }
        return dispatch(
          'edit',
          [
            'edit',
            '--allow-write',
            '--tool', input.tool,
            '--arguments', encodedArguments,
            '--expected-snapshot', input.expected_snapshot,
            '--operation-id', input.operation_id,
          ],
          { editing: true },
        );
      }
      return localFailure(false, 'PAPER_TOOL_NOT_FOUND');
    },
  });
}
