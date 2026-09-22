#!/usr/bin/env node
/**
 * private-studio-mcp gateway — Node ESM HTTP Streamable MCP proxy.
 *
 * Exposes the local Desktop Commander stdio MCP server over the MCP
 * "Streamable HTTP" transport so a remote client can reach a user-owned
 * Mac Studio without a raw stdio channel.
 *
 * Design invariants (do not weaken these):
 *
 *  - One distinct SDK `Server` + `StreamableHTTPServerTransport` + SDK
 *    `Client`/`StdioClientTransport` triple per MCP session. The SDK owns
 *    protocol framing, notifications and SSE; the gateway only routes.
 *  - Every request re-reads `req.auth` and re-checks the session/principal
 *    binding. Nothing is trusted from a previous request.
 *  - No unauthenticated path can list tools or call tools. Only /healthz and
 *    /readyz are unauthenticated, and neither returns anything but booleans,
 *    a version string and coarse counters.
 *  - No retries, no replay. A tools/call is sent to the backend exactly once.
 *    Nothing is persisted, so a reconnect cannot replay anything. No event
 *    store is configured, so SSE resume deliberately carries no backlog.
 *  - A timed-out mutation or ambiguous backend loss may or may not have taken
 *    effect: the gateway answers EFFECT_UNKNOWN, taints that frontend session,
 *    and refuses further work on it. A small closed allowlist of audited,
 *    side-effect-free reads instead returns READ_TIMEOUT without taint. Neither
 *    path ever retries or replays the call.
 *  - Session capacity is reserved under a single admit lock so concurrent
 *    `initialize` calls cannot exceed `maxSessions`. When
 *    `reclaimIdleCatalogSessions` is explicitly true, a full map may evict a
 *    fully quiescent capacity victim to admit one new initialize. Default
 *    public gateways never evict this way. Per-session mode retains the
 *    conservative historical rule: tainted/effectful/interactive sessions are
 *    never victims because the frontend owns its backend child. Shared-account
 *    mode may reclaim a quiescent tainted/effectful frontend shell because its
 *    BackendOwner and live process/search handles survive independently.
 *  - Backend child processes are only ever closed through their own
 *    `StdioClientTransport.close()`. The gateway never scans processes and
 *    never signals a process it does not own.
 *  - Logs carry request method, tool name, duration and a result
 *    classification. Never tokens, never tool arguments, never file contents.
 *
 *  Shared-account backend mode (backendMode: 'shared-account'):
 *  - One BackendOwner per principal, living for the gateway process lifetime.
 *    Session DELETE/destroy/capacity reclaim NEVER closes it; only
 *    gateway.close closes its owned transport.
 *  - The owner holds one lazy stdio Client+Transport, one generation counter,
 *    one bounded limiter, and a shared backend state machine.
 *  - A timeout taints only its originating session and preserves the child.
 *    Backend loss marks the owner broken and taints all attached sessions. A new
 *    session for the same principal can obtain a fresh owner generation.
 *    Old sessions never silently rebind to a new generation.
 *
 * Security posture:
 *  - Binds to loopback by default. An explicitly supplied `publicUrl` must be
 *    `https://` unless `testMode` is set.
 *  - Host and Origin headers are validated against the public URL and the
 *    loopback aliases, defending against DNS rebinding and cross-site POSTs.
 *    The SDK transport validates the same lists as a second layer.
 *  - Auth (`req.auth`) is supplied by ./auth.mjs and mounted by this module;
 *    this file implements no authentication itself.
 *
 * Exports:
 *  - `startGateway(config, auth)` ->
 *      `{ url, baseUrl, host, port, close, stats }`
 *    `stats` is a function returning a fresh snapshot object; `stats.live`
 *    exposes the same numbers as nested getters for property-style access.
 *  - `resolveConfig(partial)` -> fully validated config. Used by the CLI and by
 *    a test worker that wants `port: 0` for an ephemeral loopback port.
 */

import { TextOutputPager, OUTPUT_PAGE_TOOL, projectOutputSafely } from './output-budget.mjs';
import { randomUUID } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import express from 'express';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema,
  ReadResourceRequestSchema,
  ListPromptsRequestSchema,
  McpError,
  isInitializeRequest,
} from '@modelcontextprotocol/sdk/types.js';
import {
  STUDIO_GIT_PUBLISH_STATUS_TOOL,
  STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL,
  STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL,
  STUDIO_GIT_PUBLISH_TOOLS,
  createGitPublisher,
  resolveGitPublishConfig,
  toolResult as gitToolResult,
} from './git-publish.mjs';
import {
  PAPER_DESIGN_TOOLS,
  PAPER_DESIGN_TOOL_NAMES,
  createPaperDesigner,
  paperToolResult,
  resolvePaperDesignConfig,
} from './paper-design.mjs';

/** Gateway version. Kept independent of the backend's version. */
export const GATEWAY_VERSION = '0.1.6';

const BOOT_MS = Date.now();
const BOOT_NS = process.hrtime.bigint();
const HOSTNAME = os.hostname();
/** Unique for the lifetime of this gateway process. */
const GATEWAY_GENERATION = randomUUID();

/** Body cap: write_file/write_pdf payloads, still bounded. */
const MAX_BODY_BYTES = 10 * 1024 * 1024;
const MAX_SESSIONS_DEFAULT = 8;
const MAX_PER_SESSION_CONCURRENCY = 4;
const MAX_QUEUED_PER_SESSION = 4;
/** Reserve one shared-backend slot for MCP catalog/template traffic. */
const CATALOG_RESERVED_BACKEND_SLOTS = 1;
const REQUEST_TIMEOUT_MS_DEFAULT = 60_000;
const IDLE_TIMEOUT_MS_DEFAULT = 30 * 60 * 1000;
const SESSION_SWEEP_INTERVAL_MS = 60_000;
/** Shared-account frontend shells must be idle this long before capacity reclaim. */
const RECLAIM_IDLE_GRACE_MS_DEFAULT = 30_000;

/**
 * Closed vocabulary used in logs and in stats.byClassification, so log
 * analysis never has to guess what a string meant.
 */
const CLASSIFICATION = Object.freeze({
  OK: 'ok',
  TOOL_ERROR: 'tool_error',
  BUSY: 'busy',
  TAINTED: 'tainted',
  UNKNOWN_SESSION: 'unknown_session',
  CROSS_PRINCIPAL: 'cross_principal',
  PARSE_ERROR: 'parse_error',
  UNSUPPORTED_MEDIA: 'unsupported_media',
  CAPACITY: 'capacity',
  NOT_FOUND: 'not_found',
  BAD_HOST: 'bad_host',
  BAD_ORIGIN: 'bad_origin',
});

/** JSON-RPC error codes in the server-defined range (-32000..-32099). */
const CODE = Object.freeze({
  GENERIC: -32000,
  SESSION_NOT_FOUND: -32001,
  TAINTED: -32003,
  BUSY: -32004,
  CAPACITY: -32005,
  PARSE: -32700,
});

/** Magic key in stats.byTool for tools/list calls (which have no tool name). */
const LIST_TOOLS_KEY = '__tools_list';

/**
 * MCP methods that cannot create subprocess or search handles. A session
 * that has only ever admitted these (plus reclaim-safe tools/call names)
 * may be evicted under the opt-in capacity reclaim path.
 */
const RECLAIM_SAFE_METHODS = new Set([
  'initialize',
  'notifications/initialized',
  'notifications/cancelled',
  'ping',
  'tools/list',
  'resources/list',
  'resources/templates/list',
  'resources/read',
  'prompts/list',
  'prompts/get',
]);

/**
 * Well-known read-only tools that cannot hold live process/search handles.
 * Used when this session never listed tools (native ChatGPT file-read
 * sessions). Cached `readOnlyHint: true` from this session's tools/list
 * can add more names. Interactive names always win and stay unsafe.
 */
const KNOWN_READONLY_TOOL_NAMES = new Set([
  'studio_ping',
  'read_file',
  'read_multiple_files',
  'list_directory',
  'get_file_info',
  'list_allowed_directories',
  'paper_inspect',
  'paper_catalog',
  'paper_read',
]);

/**
 * Read calls whose timeout cannot create an external effect. This is
 * deliberately narrower than backend readOnlyHint: e.g. start_search is
 * metadata-read-only but creates a live search handle, so it stays ambiguous
 * if the response is lost. These calls may return READ_TIMEOUT without
 * poisoning the frontend session; the gateway still never retries them.
 */
const TIMEOUT_SAFE_READ_TOOL_NAMES = new Set([
  'read_file',
  'read_multiple_files',
  'list_directory',
  'get_file_info',
  'list_allowed_directories',
  'read_process_output',
  'list_sessions',
  'list_processes',
  'list_searches',
  'get_more_search_results',
  'get_config',
  'get_recent_tool_calls',
  'get_usage_stats',
  'get_prompts',
]);

/** Names that imply live subprocess, search, or session-handle state. */
function isInteractiveToolName(name) {
  return typeof name === 'string' &&
    /(process|search|session|interact|kill|terminat|feedback)/i.test(name);
}

/** Host header forms a client may legitimately use for a loopback bind. */
const LOOPBACK_HOSTS = ['127.0.0.1', 'localhost', '[::1]'];
const LOOPBACK_ADDRESSES = new Set(['127.0.0.1', '::1', 'localhost']);

/* ------------------------------------------------------------------ *
 * Config
 * ------------------------------------------------------------------ */

function isLoopbackHost(host) {
  return typeof host === 'string' && LOOPBACK_ADDRESSES.has(host.toLowerCase());
}

function isExplicit(source, key) {
  return Object.prototype.hasOwnProperty.call(source, key) && source[key] !== undefined;
}

function clampInt(value, min, max, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(n)));
}

function mapStrings(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      out[k] = String(v);
    }
  }
  return out;
}

/**
 * Validate and normalise a partial config into the shape the gateway uses.
 * Throws a descriptive Error on anything that would silently weaken security.
 *
 * Defaults: host 127.0.0.1, port 45017, command process.execPath,
 * args ['../dist/index.js'], maxSessions 8, requestTimeoutMs 60000,
 * backendMode 'per-session'.
 * `reclaimIdleCatalogSessions` is false unless the caller passes true;
 * it defaults true when backendMode is 'shared-account'.
 */
export function resolveConfig(partial = {}) {
  const cfg = { ...partial };
  const hostExplicit = isExplicit(partial, 'host');

  cfg.host = typeof cfg.host === 'string' && cfg.host ? cfg.host : '127.0.0.1';
  cfg.port = Number.isInteger(cfg.port) && cfg.port >= 0 ? cfg.port : 45017;
  cfg.testMode = cfg.testMode === true;

  // backendMode: strict validated string, no coercion
  if (isExplicit(partial, 'backendMode')) {
    if (partial.backendMode !== 'per-session' && partial.backendMode !== 'shared-account') {
      throw new TypeError(
        `config.backendMode must be 'per-session' or 'shared-account' (got ${JSON.stringify(partial.backendMode)})`);
    }
    cfg.backendMode = partial.backendMode;
  } else {
    cfg.backendMode = 'per-session';
  }

  // reclaimIdleCatalogSessions: shared-account defaults true; per-session stays false
  if (partial.backendMode === 'shared-account') {
    cfg.reclaimIdleCatalogSessions = partial.reclaimIdleCatalogSessions !== false;
  } else {
    cfg.reclaimIdleCatalogSessions = partial.reclaimIdleCatalogSessions === true;
  }

  cfg.maxSessions = clampInt(cfg.maxSessions, 1, 1024, MAX_SESSIONS_DEFAULT);
  cfg.reclaimIdleGraceMs = clampInt(
    cfg.reclaimIdleGraceMs, 250, 10 * 60 * 1000, RECLAIM_IDLE_GRACE_MS_DEFAULT);
  cfg.maxPerSessionConcurrency = clampInt(
    cfg.maxPerSessionConcurrency, 1, 64, MAX_PER_SESSION_CONCURRENCY);
  cfg.requestTimeoutMs = clampInt(
    cfg.requestTimeoutMs, 1, 24 * 60 * 60 * 1000, REQUEST_TIMEOUT_MS_DEFAULT);
  cfg.idleTimeoutMs = clampInt(
    cfg.idleTimeoutMs, 1_000, 30 * 24 * 60 * 60 * 1000, IDLE_TIMEOUT_MS_DEFAULT);

  cfg.command = typeof cfg.command === 'string' && cfg.command
    ? cfg.command
    : process.execPath;
  cfg.args = Array.isArray(cfg.args) ? cfg.args.map(String) : ['../dist/index.js'];
  if (cfg.cwd !== undefined && cfg.cwd !== null && typeof cfg.cwd !== 'string') {
    throw new TypeError('config.cwd must be a string when provided');
  }
  if (cfg.childEnv !== undefined &&
      (typeof cfg.childEnv !== 'object' || cfg.childEnv === null)) {
    throw new TypeError('config.childEnv must be an object when provided');
  }
  // `childEnv` is an overlay the caller controls. StdioClientTransport merges
  // it over the SDK's safe inherited environment (HOME/PATH/SHELL/USER/TERM/
  // LOGNAME), so an empty overlay still yields a working backend while a
  // caller who explicitly passes process.env gets exactly what it asked for.
  cfg.childEnv = cfg.childEnv ? mapStrings(cfg.childEnv) : {};

  if (cfg.publicUrl !== undefined && cfg.publicUrl !== null && cfg.publicUrl !== '') {
    let parsed;
    try {
      parsed = new URL(String(cfg.publicUrl));
    } catch {
      throw new TypeError(`config.publicUrl is not a valid URL: ${cfg.publicUrl}`);
    }
    if (!cfg.testMode && parsed.protocol !== 'https:') {
      throw new TypeError(
        `config.publicUrl must use https:// outside testMode (got ${parsed.protocol})`);
    }
    if (parsed.pathname !== '/' && parsed.pathname !== '') {
      throw new TypeError('config.publicUrl must not include a path');
    }
    if (parsed.username || parsed.password) {
      throw new TypeError('config.publicUrl must not embed credentials');
    }
    cfg.publicUrl = parsed;
  } else {
    cfg.publicUrl = null;
  }

  // Loopback is the default bind regardless of publicUrl. A caller who wants a
  // raw non-loopback bind has to say so explicitly, and must then also supply
  // a publicUrl so Host/Origin validation has something meaningful to pin to.
  if (!hostExplicit && !isLoopbackHost(cfg.host)) {
    cfg.host = '127.0.0.1';
  }
  if (!isLoopbackHost(cfg.host) && (!cfg.publicUrl || !hostExplicit)) {
    throw new TypeError(
      `config.host ${cfg.host} is not a loopback address; bind to 127.0.0.1 and expose via a https publicUrl`);
  }

  if (cfg.stateDir !== undefined && cfg.stateDir !== null && typeof cfg.stateDir !== 'string') {
    throw new TypeError('config.stateDir must be a string when provided');
  }

  cfg.gitPublish = resolveGitPublishConfig(cfg.gitPublish);
  cfg.paperDesign = resolvePaperDesignConfig(cfg.paperDesign);

  return cfg;
}

/**
 * Host and Origin allow-lists derived from the public URL plus the loopback
 * aliases of the bound address. Both the gateway middleware and the SDK
 * transport validate against these exact sets, so the two layers cannot
 * disagree about what is allowed.
 */
function buildAllowlists(cfg) {
  const hosts = new Set();
  const origins = new Set();

  if (cfg.publicUrl) {
    hosts.add(cfg.publicUrl.host.toLowerCase()); // includes a non-default port
    hosts.add(cfg.publicUrl.hostname.toLowerCase());
    origins.add(cfg.publicUrl.origin.toLowerCase());
  }
  for (const h of LOOPBACK_HOSTS) {
    hosts.add(h);
  }
  return { hosts, origins, loopback: isLoopbackHost(cfg.host) };
}

/** Called once the real bound port is known, to admit loopback aliases. */
function addLoopbackAliases(lists, port) {
  if (!lists.loopback) return;
  for (const h of LOOPBACK_HOSTS) {
    lists.hosts.add(`${h}:${port}`);
    lists.origins.add(`http://${h}:${port}`);
    lists.origins.add(`https://${h}:${port}`);
  }
}

function hostHeaderMatches(header, allowlist) {
  if (typeof header !== 'string' || header.length === 0) return false;
  const lower = header.toLowerCase();
  if (allowlist.has(lower)) return true;
  // Admit an explicit default-port spelling of an allowed bare host, but never
  // a non-default port: that would be a different endpoint.
  const colon = lower.lastIndexOf(':');
  if (colon > lower.lastIndexOf(']')) {
    const bare = lower.slice(0, colon);
    const port = lower.slice(colon + 1);
    if ((port === '80' || port === '443') && allowlist.has(bare)) return true;
  }
  return false;
}

/* ------------------------------------------------------------------ *
 * Logging
 * ------------------------------------------------------------------ */

let logSink = (line) => process.stderr.write(line + '\n');

/** Overridable for tests; not part of the frozen config surface. */
export function setLogSink(fn) {
  logSink = typeof fn === 'function' ? fn : logSink;
}

function log(level, event, fields = {}) {
  try {
    logSink(JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields }));
  } catch {
    /* logging must never break the request path */
  }
}

/**
 * Short, non-reversible tag for a secret-ish value. Never logs the token,
 * the full client id or the raw principal.
 */
function shortTag(value) {
  if (typeof value !== 'string' || value.length === 0) return 'none';
  let h = 0;
  for (let i = 0; i < value.length; i++) {
    h = (h * 31 + value.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(36).slice(0, 8);
}

/** Host/Origin values are sanitised before they ever reach the log. */
function safeHost(value) {
  if (typeof value !== 'string') return 'none';
  return value.replace(/[^A-Za-z0-9.[\]:-]/g, '').slice(0, 64) || 'invalid';
}

/* ------------------------------------------------------------------ *
 * Identity binding
 * ------------------------------------------------------------------ */

/**
 * Canonical string for the principal a session is bound to.
 * Recomputed from `req.auth` on EVERY request — never cached on the socket,
 * never taken from a header or cookie this module owns.
 */
export function principalKeyOf(auth) {
  if (auth == null || typeof auth !== 'object') return 'anon';
  const p = auth.principal;
  if (typeof p === 'string' && p.length > 0) return 'p:' + p;
  const c = auth.clientId;
  if (typeof c === 'string' && c.length > 0) return 'c:' + c;
  if (p != null) return 'p:' + stableStringify(p);
  if (c != null) return 'c:' + stableStringify(c);
  return 'anon';
}

function stableStringify(value) {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value) ?? 'null';
  }
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']';
  const keys = Object.keys(value).sort();
  return '{' +
    keys.map((k) => JSON.stringify(k) + ':' + stableStringify(value[k])).join(',') +
    '}';
}

/* ------------------------------------------------------------------ *
 * Concurrency primitive
 * ------------------------------------------------------------------ */

/**
 * FIFO limiter with explicit slot hand-off, so a released slot is handed
 * directly to the next waiter instead of being decremented and immediately
 * re-contested. That keeps the cap exact under contention.
 */
function createLimiter(max, maxQueued, { reservePriority = 0 } = {}) {
  let active = 0;
  let activeNormal = 0;
  let queue = [];
  const reserved = Math.min(Math.max(0, reservePriority), Math.max(0, max - 1));
  const normalCap = Math.max(1, max - reserved);
  // Preserve the historical normal-work outstanding bound (max + maxQueued)
  // even though one active slot is held for catalog traffic.
  const normalQueueCap = maxQueued + reserved;
  const priorityQueueCap = reserved > 0 ? reserved : maxQueued;

  function canRun(priority) {
    if (active >= max) return false;
    return priority || activeNormal < normalCap;
  }

  function admit(waiter) {
    active += 1;
    if (!waiter.priority) activeNormal += 1;
    waiter.resolve(waiter.priority ? 'priority' : 'normal');
  }

  return {
    get active() { return active; },
    get queued() { return queue.length; },
    acquire({ priority = false } = {}) {
      const waiter = { priority: priority === true };
      if (canRun(waiter.priority)) {
        active += 1;
        if (!waiter.priority) activeNormal += 1;
        return Promise.resolve(waiter.priority ? 'priority' : 'normal');
      }
      const normalQueued = queue.reduce((n, w) => n + (w.priority ? 0 : 1), 0);
      const priorityQueued = queue.length - normalQueued;
      if ((!waiter.priority && normalQueued >= normalQueueCap) ||
          (waiter.priority && priorityQueued >= priorityQueueCap)) {
        const err = new Error('Server busy: per-session concurrency cap reached');
        err.code = 'STUDIO_BUSY';
        return Promise.reject(err);
      }
      return new Promise((resolve, reject) => {
        queue.push({ ...waiter, resolve, reject });
      });
    },
    release(kind = 'normal') {
      if (active > 0) active -= 1;
      if (kind === 'normal' && activeNormal > 0) activeNormal -= 1;

      // Preserve one bounded priority lane for MCP catalog/template traffic.
      // Within each class, FIFO order remains stable.
      while (active < max) {
        let index = queue.findIndex((w) => w.priority && canRun(true));
        if (index < 0) index = queue.findIndex((w) => !w.priority && canRun(false));
        if (index < 0) break;
        const [next] = queue.splice(index, 1);
        admit(next);
      }
    },
    drain(reason) {
      const waiting = queue;
      queue = [];
      for (const w of waiting) {
        const err = new Error(reason || 'Session closed');
        err.code = 'STUDIO_CLOSED';
        w.reject(err);
      }
    },
  };
}

/* ------------------------------------------------------------------ *
 * studio_ping
 * ------------------------------------------------------------------ */

/** Monotonic milliseconds since gateway module load. */
function monotonicMs() {
  return Number(process.hrtime.bigint() - BOOT_NS) / 1e6;
}

const STUDIO_PING_TOOL = Object.freeze({
  name: 'studio_ping',
  title: 'Studio Gateway Ping',
  description:
    'Reports private Studio gateway liveness with an ephemeral process-generation nonce, per-call ' +
    'nonce, wall-clock timestamp, monotonic age, call duration, gateway version, and MCP session ' +
    'reference. The generation nonce is random and process-scoped; it carries no host or hardware ' +
    'data. The gateway answers this probe without invoking ' +
    'the Desktop Commander backend or filesystem.',
  inputSchema: {
    type: 'object',
    properties: {},
    required: [],
    additionalProperties: false,
  },
  annotations: {
    title: 'Studio Gateway Ping',
    readOnlyHint: true,
    destructiveHint: false,
    idempotentHint: true,
    openWorldHint: false,
  },
  _meta: { 'private-studio-mcp/gateway': true },
});

let pingCounter = 0;

function handleStudioPing(session) {
  const startNs = process.hrtime.bigint();
  const structured = {
    timestamp: new Date().toISOString(),
    generation: GATEWAY_GENERATION,
    pingId: `ping-${(++pingCounter).toString(36)}-${randomUUID().slice(0, 8)}`,
    monotonicMs: monotonicMs(),
    monotonicDurationMs: 0,
    gatewayVersion: GATEWAY_VERSION,
    sessionId: session ? session.id : null,
  };
  structured.monotonicDurationMs = Number(process.hrtime.bigint() - startNs) / 1e6;
  return {
    content: [{ type: 'text', text: JSON.stringify(structured, null, 2) }],
    structuredContent: structured,
  };
}

/* ------------------------------------------------------------------ *
 * Tool metadata proxying
 * ------------------------------------------------------------------ */

/** Reviewed effect floors for existing backend capabilities, not permissions.
 * Missing hints are explicit and conservative. Upstream labels cannot turn a
 * known write, arbitrary shell command, or external request into a harmless read.
 * Authorization and actual execution remain with their existing owners.
 */
const MUTATING_BACKEND_TOOL_NAMES = new Set([
  'set_config_value', 'write_file', 'write_pdf', 'create_directory', 'move_file',
  'edit_block', 'start_process', 'interact_with_process', 'force_terminate',
  'kill_process', 'give_feedback_to_desktop_commander', 'stop_search',
]);
const DESTRUCTIVE_BACKEND_TOOL_NAMES = new Set([
  'set_config_value', 'write_file', 'write_pdf', 'move_file', 'edit_block',
  'start_process', 'interact_with_process', 'force_terminate', 'kill_process',
]);
// Known 0.2.50 capabilities: [openWorldHint, idempotentHint]. These are
// reviewed metadata defaults, not grants or assertions about future versions.
// Local readers are closed-world even when the upstream hint is omitted.
// Handle creation/consumption, arbitrary commands, moves, overwrites and process
// termination stay non-idempotent. Read idempotence does not promise stable data
// or authorize retry after an unknown effect. Ordinary logging is not the job.
const REVIEWED_BACKEND_EFFECT_PROFILES = Object.freeze(Object.fromEntries(
  Object.entries({
    get_config: [false, true],
    set_config_value: [false, true],
    read_file: [true, true],
    read_multiple_files: [false, true],
    write_file: [false, false],
    write_pdf: [false, false],
    create_directory: [false, true],
    list_directory: [false, true],
    move_file: [false, false],
    start_search: [false, false],
    get_more_search_results: [false, false],
    stop_search: [false, true],
    list_searches: [false, true],
    get_file_info: [false, true],
    edit_block: [false, false],
    start_process: [true, false],
    read_process_output: [false, false],
    interact_with_process: [true, false],
    force_terminate: [false, false],
    list_sessions: [false, true],
    list_processes: [false, true],
    kill_process: [false, false],
    get_usage_stats: [false, true],
    get_recent_tool_calls: [false, true],
    give_feedback_to_desktop_commander: [true, false],
    get_prompts: [false, true],
  }).map(([name, [openWorldHint, idempotentHint]]) =>
    [name, Object.freeze({openWorldHint, idempotentHint})]),
));

function conservativeAnnotations(tool) {
  const raw = tool?.annotations;
  const existing = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const booleanOr = (key, fallback) =>
    typeof existing[key] === 'boolean' ? existing[key] : fallback;
  const profile = Object.hasOwn(REVIEWED_BACKEND_EFFECT_PROFILES, tool?.name)
    ? REVIEWED_BACKEND_EFFECT_PROFILES[tool.name] : undefined;
  const readOnlyHint = !MUTATING_BACKEND_TOOL_NAMES.has(tool?.name)
    && booleanOr('readOnlyHint', false);
  return {
    ...existing,
    ...(Object.keys(existing).length === 0
      ? {title: typeof tool?.title === 'string' ? tool.title : tool?.name} : {}),
    readOnlyHint,
    destructiveHint: typeof existing.readOnlyHint !== 'boolean'
      || DESTRUCTIVE_BACKEND_TOOL_NAMES.has(tool?.name)
      || booleanOr('destructiveHint', !readOnlyHint),
    idempotentHint: profile?.idempotentHint !== false
      && booleanOr('idempotentHint', profile?.idempotentHint ?? false),
    openWorldHint: profile?.openWorldHint === true
      || booleanOr('openWorldHint', profile?.openWorldHint ?? true),
  };
}

const NEUTRAL_BACKEND_TOOL_DESCRIPTIONS = Object.freeze({
  get_config: 'Returns Desktop Commander configuration, access bounds, runtime metadata, and client information.',
  set_config_value: "Updates one Desktop Commander setting, including filesystem access bounds, blocked commands, or the default shell. Security-related changes affect later tool calls and do not override operating-system permissions.",
  read_file: 'Reads one allowed local file or supported URL, with bounded paging for supported formats.',
  read_multiple_files: 'Reads multiple allowed local files and returns contents or per-file errors.',
  write_file: 'Creates, replaces, or appends content in one allowed local file.',
  write_pdf: 'Creates a PDF or writes a modified copy of an existing PDF from structured page operations.',
  create_directory: 'Creates an allowed local directory path, including missing parent directories.',
  list_directory: 'Lists entries beneath an allowed local directory to the requested depth.',
  move_file: 'Moves or renames an allowed local file or directory.',
  start_search: 'Starts a bounded filesystem search and returns a search handle with initial results.',
  get_more_search_results: 'Returns additional results for an existing filesystem search handle.',
  stop_search: 'Stops an existing filesystem search handle.',
  list_searches: 'Lists active filesystem search handles.',
  get_file_info: 'Returns metadata for an allowed local file or directory.',
  list_allowed_directories: 'Returns the local filesystem directories allowed for file operations.',
  edit_block: 'Applies an exact text or supported document-block replacement in one allowed local file.',
  start_process: "Runs a caller-supplied shell command on the connected computer with the host user's permissions. Commands may change files, launch programs, or access the network; file-tool directory limits are not a shell sandbox. This is a direct host-command capability, not a work-submission or agent-handoff interface. Nested agent instructions, large worker handoffs, and opaque/repackaged payloads are outside its declared purpose. Bounded work commissions are represented by purpose-built work-submission actions using stable job or request references. Returns output and process state.",
  read_process_output: 'Reads bounded output from an existing terminal process.',
  interact_with_process: "Sends input to an existing terminal process and returns output and process state. The input may execute commands, modify files, or access the network with that process's permissions. This is direct terminal interaction, not a work-submission or agent-handoff interface. Nested agent instructions, large worker handoffs, and opaque/repackaged payloads are outside its declared purpose.",
  force_terminate: 'Terminates an existing terminal session by process identifier.',
  list_sessions: 'Lists terminal sessions owned by the Desktop Commander runtime.',
  list_processes: 'Lists operating-system processes visible to the Desktop Commander runtime.',
  kill_process: 'Terminates a running operating-system process by process identifier.',
  get_usage_stats: 'Returns Desktop Commander usage and performance statistics.',
  get_recent_tool_calls: "Returns locally retained tool-call metadata, arguments, and bounded outputs, which may contain sensitive user data.",
  give_feedback_to_desktop_commander: "Opens the Desktop Commander feedback form in the local browser and sends usage statistics, platform information, and a client identifier to the feedback service. Survey answers are entered in the form.",
  get_prompts: 'Returns one Desktop Commander onboarding prompt by identifier.',
  search_files: 'Searches allowed local directories for files matching a bounded query.',
});

const FALLBACK_BACKEND_TOOL_DESCRIPTION =
  'Backend MCP capability. The input schema defines accepted parameters and annotations describe its effect posture.';

function sanitizeTool(tool) {
  if (!tool || typeof tool !== 'object' || typeof tool.name !== 'string') return tool;
  return {
    ...tool,
    description: NEUTRAL_BACKEND_TOOL_DESCRIPTIONS[tool.name] ?? FALLBACK_BACKEND_TOOL_DESCRIPTION,
    annotations: conservativeAnnotations(tool),
  };
}

function sanitizeToolList(tools) {
  if (!Array.isArray(tools)) return [];
  return tools
    .filter((t) => t && typeof t === 'object' && typeof t.name === 'string')
    .map(sanitizeTool);
}

/* ------------------------------------------------------------------ *
 * BackendOwner — shared-account backend lifetime manager
 * ------------------------------------------------------------------ */

/** One immutable backend generation per principal. Healthy owners survive
 * frontend session closure; broken owners are closed before replacement. */
class BackendOwner {
  constructor({ principalKey, principalTag, cfg, stats }) {
    Object.assign(this, { principalKey, principalTag, cfg, stats });
    this.generation = randomUUID();
    this.outputPager = new TextOutputPager();
    this.outputToolSchemas = new Map();
    this.state = 'idle';
    this.client = null;
    this.transport = null;
    this.connectPromise = null;
    this.closePromise = null;
    this.closing = false;
    this.sessions = new Set();
    this.limiter = createLimiter(cfg.maxPerSessionConcurrency, MAX_QUEUED_PER_SESSION, {
      reservePriority: CATALOG_RESERVED_BACKEND_SLOTS,
    });
  }

  async getClient() {
    if (this.state === 'broken' || this.closing) {
      const error = new Error('Backend generation lost; initialize a new session');
      error.code = 'STUDIO_OWNER_BROKEN';
      throw error;
    }
    if (this.state === 'ready') return {client:this.client, generation:this.generation};
    if (!this.connectPromise) {
      this.state = 'connecting';
      this.stats.backend.spawns += 1;
      this.connectPromise = this.connect();
    }
    await this.connectPromise;
    return {client:this.client, generation:this.generation};
  }

  async connect() {
    const transport = new StdioClientTransport({command:this.cfg.command,
      args:this.cfg.args, cwd:this.cfg.cwd, env:this.cfg.childEnv, stderr:'ignore'});
    const client = new Client({name:'private-studio-mcp-gateway-backend',version:GATEWAY_VERSION}, {capabilities:{}});
    this.transport = transport;
    this.client = client;
    client.onclose = () => {
      if (!this.closing) this.markBroken('backend disconnected');
    };
    try {
      await client.connect(transport, {timeout:this.cfg.requestTimeoutMs});
      if (this.closing || this.state === 'broken') throw new Error('Backend closed during initialization');
      this.state = 'ready';
    } catch (error) {
      if (!this.closing) this.markBroken('backend initialization failed');
      try { await transport.close(); } catch {}
      throw error;
    }
  }

  markBroken(reason) {
    if (this.state === 'broken') return;
    this.state = 'broken';
    this.stats.backend.lost += 1;
    for (const session of this.sessions) session.taint(reason);
    this.limiter.drain('Backend generation lost');
    log('warn', 'backend_owner_broken', {owner:this.principalTag, generation:this.generation, reason});
  }

  close() {
    if (this.closePromise) return this.closePromise;
    this.closing = true;
    this.outputPager.clear();
    this.outputToolSchemas.clear();
    this.state = 'broken';
    this.limiter.drain('Backend closed');
    this.closePromise = (async () => {
      try { await this.client?.close(); } catch {}
      try { await this.transport?.close(); } catch {}
      // A connecting child must finish cleanup before its owner is released.
      try { await this.connectPromise; } catch {}
      this.client = null;
      this.transport = null;
    })();
    return this.closePromise;
  }
}

/* ------------------------------------------------------------------ *
 * Session
 * ------------------------------------------------------------------ */

class GatewaySession {
  constructor({ id, principalKey, principalTag, cfg, lists, stats, onDestroyed, owner }) {
    this.id = id;
    this.principalKey = principalKey;
    this.tag = id.slice(0, 8); // log-safe session tag
    this.principalTag = principalTag;
    this.cfg = cfg;
    this.lists = lists;
    this.stats = stats;
    this.onDestroyed = onDestroyed;

    // In shared-account mode, this session's assigned BackendOwner.
    // Undefined when backendMode is 'per-session' (session uses its own backend).
    this.owner = owner;
    this.outputPager = owner?.outputPager ?? new TextOutputPager();
    this.outputToolSchemas = owner?.outputToolSchemas ?? new Map();
    this.backendOpsInFlight = 0;

    this.createdAt = Date.now();
    this.lastActive = this.createdAt;
    this.initialized = false;
    this.tainted = false;
    this.taintedReason = null;
    this.destroyed = false;
    this.destroyReason = null;

    // HTTP requests in flight, including a long-lived GET SSE stream. Drives
    // idle expiry only. Separate from `limiter`, which counts backend
    // operations, so an idle SSE listener can never starve tool calls.
    this.httpRequestsInFlight = 0;
    this.limiter = createLimiter(cfg.maxPerSessionConcurrency, MAX_QUEUED_PER_SESSION);

    this.backendState = 'idle'; // idle | connecting | ready | broken
    this.backendClient = null;
    this.backendTransport = null;
    this.backendPromise = null;
    this.closingBackend = false;
    this.toolRequestIds = new Set();
    // Starts reclaim-safe. Any effectful or interactive admission flips this
    // permanently; catalog/read-only work does not.
    this.reclaimUnsafe = false;
    this.readonlyToolNames = new Set([STUDIO_PING_TOOL.name, OUTPUT_PAGE_TOOL.name]);

    this.transport = null;
    this.server = null;
    this.gitPublisher = cfg.gitPublish ? createGitPublisher(cfg.gitPublish) : null;
    this.paperDesigner = cfg.paperDesign ? createPaperDesigner(cfg.paperDesign) : null;
    this.owner?.sessions.add(this);
  }

  rememberToolAnnotations(tool) {
    if (!tool || typeof tool.name !== 'string') return;
    this.outputToolSchemas.set(tool.name, Boolean(tool.outputSchema));
    if (tool.annotations?.readOnlyHint === true) {
      this.readonlyToolNames.add(tool.name);
    } else {
      this.readonlyToolNames.delete(tool.name);
    }
  }

  isReclaimSafeTool(name) {
    if (typeof name !== 'string' || name.length === 0) return false;
    if (isInteractiveToolName(name)) return false;
    return this.readonlyToolNames.has(name) || KNOWN_READONLY_TOOL_NAMES.has(name);
  }

  isTimeoutSafeReadTool(name) {
    // Timeout safety is deliberately stricter than readOnlyHint. Only names
    // audited into this closed set can avoid EFFECT_UNKNOWN on timeout.
    return typeof name === 'string' && TIMEOUT_SAFE_READ_TOOL_NAMES.has(name);
  }

  noteAdmittedWork(body) {
    if (this.reclaimUnsafe) return;
    const method = typeof body?.method === 'string' ? body.method : '';
    if (RECLAIM_SAFE_METHODS.has(method)) return;
    if (method === 'tools/call' && this.isReclaimSafeTool(body?.params?.name)) return;
    this.reclaimUnsafe = true;
  }

  isQuiescentCapacityVictim() {
    if (this.destroyed) return false;
    if (!this.initialized) return false;
    if (this.httpRequestsInFlight > 0) return false;
    if (this.backendOpsInFlight > 0) return false;
    if (this.limiter.active > 0 || this.limiter.queued > 0) return false;
    if (this.backendState === 'connecting') return false;
    // Reclaim only after a real idle grace measured from the most recent
    // admitted request. Native ChatGPT can initialize, then send its initialized
    // notification and UI-template resources/read on the same session seconds
    // later. Creation age alone races that bootstrap sequence under churn.
    if (Date.now() - this.lastActive < this.cfg.reclaimIdleGraceMs) return false;

    // Per-session mode preserves the conservative historical rule: effectful
    // or tainted sessions are never capacity victims because destroying the
    // frontend also owns/tears down its backend child. In shared-account mode
    // the frontend is only a disposable routing shell; the BackendOwner and
    // all process/search handles survive. A tainted frontend therefore becomes
    // the *preferred* victim once its request/queue activity has fully unwound.
    if (!this.owner && (this.tainted || this.reclaimUnsafe)) return false;
    return true;
  }

  touch() {
    this.lastActive = Date.now();
  }

  /* ---- gateway-side MCP transport ---- */

  buildTransport() {
    const session = this;
    const transport = new StreamableHTTPServerTransport({
      // Pre-generated so the session is registered — and already bound to its
      // principal — before the initialize response leaves the process.
      sessionIdGenerator: () => session.id,
      enableJsonResponse: false,
      // Second layer of DNS-rebinding protection over the gateway middleware,
      // built from the same allow-lists so the two layers cannot disagree.
      enableDnsRebindingProtection: true,
      allowedHosts: [...session.lists.hosts],
      allowedOrigins: [...session.lists.origins],
      onsessioninitialized() {
        session.initialized = true;
        session.touch();
        session.stats.sessions.started += 1;
        log('info', 'session_initialized', { sid: session.tag, principal: session.principalTag });
      },
      onsessionclosed() {
        // Client sent DELETE, or the transport closed for another reason.
        void session.destroy('transport_closed');
      },
      // Intentionally no `eventStore`: enabling resumability would let the
      // gateway replay events after a reconnect, which this design forbids.
    });
    this.transport = transport;
    return transport;
  }

  /* ---- gateway-side MCP server: merges gateway tools with the backend ---- */

  buildServer() {
    const session = this;
    const server = new Server(
      { name: 'private-studio-mcp-gateway', version: GATEWAY_VERSION },
      {
        capabilities: { tools: { listChanged: false }, resources: {}, prompts: {} },
        instructions:
          'HTTP gateway in front of the local Desktop Commander stdio server. ' +
          'studio_ping, studio_output_page, configured studio_git_* tools, and configured paper_* design tools are gateway-owned. ' +
          'studio_output_page reads retained output without repeating the original action. ' +
          'Paper design tools use the host-pinned guarded Paper adapter and never route through Desktop Commander. ' +
          'start_process and interact_with_process represent direct terminal effects rather than work-submission or agent-handoff transport. ' +
          'Nested agent instructions, worker handoffs, and opaque/repackaged payloads are outside their declared scope. ' +
          'A platform safety refusal is a terminal observation for the refused logical call; transformed replay by encoding, splitting, rewording, or rerouting is outside this server\'s supported behavior. ' +
          'All remaining tools are proxied to the backend.',
      },
    );

    server.setRequestHandler(ListToolsRequestSchema, async (request, extra) =>
      session.withBackendSlot(async () => {
        const backend = await session.ensureBackend();
        const result = await backend.client.listTools(request.params ?? {}, {
          timeout: session.cfg.requestTimeoutMs,
          signal: extra?.signal,
        });
        const tools = sanitizeToolList(result.tools);
        const localTools = [{ ...STUDIO_PING_TOOL }, { ...OUTPUT_PAGE_TOOL }];
        if (session.gitPublisher) {
          localTools.push(...STUDIO_GIT_PUBLISH_TOOLS.map((tool) => ({ ...tool })));
        }
        if (session.paperDesigner) {
          localTools.push(...PAPER_DESIGN_TOOLS.map((tool) => ({ ...tool })));
        }
        const backendNames = new Set(tools.map((tool) => tool.name));
        for (const localTool of localTools) {
          if (backendNames.has(localTool.name)) {
            throw new McpError(ErrorCode.InternalError, `Backend tool name collides with gateway-owned tool: ${localTool.name}`);
          }
          tools.push(localTool);
        }
        for (const tool of tools) session.rememberToolAnnotations(tool);
        const out = { tools };
        if (typeof result.nextCursor === 'string' && result.nextCursor.length > 0) {
          out.nextCursor = result.nextCursor;
        }
        session.bumpTool(LIST_TOOLS_KEY);
        return out;
      }, { kind: 'tools/list', catalogPriority: true }));

    server.setRequestHandler(CallToolRequestSchema, async (request, extra) =>
      session.callTool(request, extra));

    // Tool metadata can reference backend UI resources. ChatGPT fetches these
    // during installation, so the advertised references must remain readable
    // through the same authenticated session and bounded backend queue.
    const proxyCatalog = (schema, capability, method, emptyResult) => {
      server.setRequestHandler(schema, async (request, extra) =>
        session.withBackendSlot(async () => {
          const backend = await session.ensureBackend();
          if (!backend.client.getServerCapabilities()?.[capability]) {
            if (emptyResult) return { ...emptyResult };
            throw new McpError(ErrorCode.InvalidParams, 'Backend does not expose resources');
          }
          return backend.client[method](request.params ?? {}, {
            timeout: session.cfg.requestTimeoutMs,
            signal: extra?.signal,
          });
        }, { kind: request.method, catalogPriority: true }));
    };
    proxyCatalog(ListResourcesRequestSchema, 'resources', 'listResources', { resources: [] });
    proxyCatalog(ListResourceTemplatesRequestSchema, 'resources', 'listResourceTemplates', { resourceTemplates: [] });
    proxyCatalog(ReadResourceRequestSchema, 'resources', 'readResource');
    proxyCatalog(ListPromptsRequestSchema, 'prompts', 'listPrompts', { prompts: [] });

    this.server = server;
    return server;
  }

  bumpTool(name) {
    const key = typeof name === 'string' && name.length > 0 ? name : 'unknown';
    const byTool = this.stats.requests.byTool;
    byTool[key] = (byTool[key] || 0) + 1;
  }

  async callTool(request, extra) {
    const name = request?.params?.name;
    const started = Date.now();

    if (name === OUTPUT_PAGE_TOOL.name) {
      this.touch();
      this.bumpTool(name);
      return this.outputPager.read(request?.params?.arguments ?? {});
    }

    if (name === STUDIO_PING_TOOL.name) {
      // Answered locally: no backend, no limiter slot, cannot taint anything.
      this.bumpTool(name);
      const result = handleStudioPing(this);
      log('info', 'tool_call', {
        sid: this.tag, tool: name, durationMs: Date.now() - started,
        classification: CLASSIFICATION.OK,
      });
      return result;
    }

    if (this.paperDesigner && PAPER_DESIGN_TOOL_NAMES.has(name)) {
      return this.withBackendSlot(async () => {
        this.bumpTool(name);
        const result = await this.paperDesigner.call(name, request?.params?.arguments ?? {});
        if (result.effectUnknown) {
          this.taint('Paper design mutation effect unknown');
        }
        log(result.isError ? 'warn' : 'info', 'tool_call', {
          sid: this.tag,
          tool: name,
          durationMs: Date.now() - started,
          classification: result.isError ? CLASSIFICATION.TOOL_ERROR : CLASSIFICATION.OK,
          effect: result.effectUnknown ? 'EFFECT_UNKNOWN' : undefined,
        });
        return paperToolResult(result.value, result.isError);
      }, { kind: 'tools/call', tool: name, started });
    }

    if (this.gitPublisher &&
        (name === STUDIO_GIT_PUBLISH_STATUS_TOOL.name ||
         name === STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.name ||
         name === STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.name)) {
      this.bumpTool(name);
      try {
        const args = request?.params?.arguments ?? {};
        const data = name === STUDIO_GIT_PUBLISH_STATUS_TOOL.name
          ? await this.gitPublisher.status(args)
          : name === STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.name
            ? await this.gitPublisher.commit(args)
            : await this.gitPublisher.push(args);
        const isError = data?.status === 'REFUSED' || data?.status === 'PARTIAL' || data?.effect_state === 'EFFECT_UNKNOWN';
        if (data?.effect_state === 'EFFECT_UNKNOWN') this.taint('typed git mutation effect unknown');
        log(isError ? 'warn' : 'info', 'tool_call', {
          sid: this.tag, tool: name, durationMs: Date.now() - started,
          classification: isError ? CLASSIFICATION.TOOL_ERROR : CLASSIFICATION.OK,
          effect: typeof data?.effect_state === 'string' ? data.effect_state : undefined,
        });
        return gitToolResult(data, isError);
      } catch {
        log('info', 'tool_call', {
          sid: this.tag, tool: name, durationMs: Date.now() - started,
          classification: CLASSIFICATION.TOOL_ERROR,
        });
        return gitToolResult({
          schema: 'mastermind.studio_git_tool_error.v1',
          status: 'REFUSED',
          effect_state: 'NOT_APPLIED',
          code: 'TYPED_GIT_PRECHECK_REFUSED',
        }, true);
      }
    }

    return this.withBackendSlot(async () => {
      this.bumpTool(name);
      const backend = await this.ensureBackend();

      try {
        // Exactly one attempt. There is no retry loop anywhere in this file.
        // Preserve the caller's existing JSON-RPC identity across the gateway
        // boundary. Desktop Commander's TerminalManager can retain this value
        // on spawned sessions so a lost start_process result can be reconciled
        // by request identity instead of replaying the command or inventing a
        // second lifecycle/state plane.
        const backendMeta = {
          ...(request?.params?._meta && typeof request.params._meta === 'object'
            ? request.params._meta
            : {}),
          mastermind_remote_call_id: String(extra?.requestId),
        };
        const result = await backend.client.callTool(
          { name, arguments: request?.params?.arguments ?? {}, _meta: backendMeta },
          undefined,
          { timeout: this.cfg.requestTimeoutMs, signal: extra?.signal },
        );
        this.touch();
        const classification = result && result.isError === true
          ? CLASSIFICATION.TOOL_ERROR
          : CLASSIFICATION.OK;
        log('info', 'tool_call', {
          sid: this.tag, tool: name, durationMs: Date.now() - started, classification,
        });
        // Retain only catalogued, untyped text results under the existing owner.
        // Paging never dispatches the backend or changes the original effect.
        return projectOutputSafely(this.outputPager, result, {
          toolName: name,
          hasOutputSchema: this.outputToolSchemas.get(name) !== false,
        });
      } catch (err) {
        return this.handleToolFailure(err, name, started);
      }
    }, { kind: 'tools/call', tool: name, started });
  }

  /**
   * A timed-out or disconnected backend call is ambiguous unless the tool is
   * one of the explicitly audited, side-effect-free timeout-safe reads. Those
   * reads return READ_TIMEOUT without taint and are never retried. Every other
   * timeout/backend-loss path preserves EFFECT_UNKNOWN, taints the frontend,
   * and refuses further work on that session. EFFECT_UNKNOWN is surfaced as a
   * JSON-RPC error rather than an `isError` tool result so it cannot be mistaken
   * for a tool verdict.
   *
   * A clean JSON-RPC error from a still-live backend (unknown tool, invalid
   * arguments) is deterministic — the tool provably did not run — so it is
   * forwarded as an `isError` result without tainting the session.
   */
  handleToolFailure(err, toolName, started) {
    const durationMs = Date.now() - started;
    const message = String(err?.message ?? '');
    const timedOut = err?.code === ErrorCode.RequestTimeout || err?.code === 'RequestTimeout' || /timed?\s*out/i.test(message);
    const backendGone = this.backendState === 'broken' ||
      this.tainted ||
      err?.code === 'ConnectionClosed' ||
      err?.code === 'STUDIO_CLOSED' ||
      /not connected|connection closed|transport closed/i.test(message);

    // Only protocol validation/method errors prove a non-executed call.
    const deterministic = [ErrorCode.InvalidParams, ErrorCode.MethodNotFound, ErrorCode.InvalidRequest].includes(err?.code);
    if (timedOut && !backendGone && this.isTimeoutSafeReadTool(toolName)) {
      this.stats.requests.timeouts += 1;
      log('warn', 'tool_call_read_timeout', {
        sid: this.tag, tool: toolName, durationMs, classification: CLASSIFICATION.TOOL_ERROR,
      });
      return {
        content: [{ type: 'text', text: 'READ_TIMEOUT: backend read exceeded the gateway deadline; no retry was performed.' }],
        isError: true,
      };
    }

    if (timedOut || backendGone || !deterministic) {
      const reason = timedOut ? 'backend timeout' : 'backend disconnected';
      this.taint(reason);
      if (timedOut) this.stats.requests.timeouts += 1;
      log('warn', 'tool_call_effect_unknown', {
        sid: this.tag, tool: toolName, durationMs,
        reason: timedOut ? 'timeout' : 'backend_lost',
      });
      throw new McpError(
        ErrorCode.InternalError,
        'EFFECT_UNKNOWN: ' +
          `${reason}. The tool call may or may not have taken effect. ` +
          'This session is tainted and will refuse further work; re-initialize to open a new ' +
          'session. The gateway will not replay this call.',
        { 'private-studio-mcp/effect': 'UNKNOWN' },
      );
    }

    // Deterministic failure from a live backend: no taint, no retry.
    log('info', 'tool_call', {
      sid: this.tag, tool: toolName, durationMs, classification: CLASSIFICATION.TOOL_ERROR,
    });
    return {
      content: [{ type: 'text', text: `Error: ${message || 'backend tool call failed'}` }],
      isError: true,
    };
  }

  /* ---- backend child (per-session mode) ---- */

  /**
   * Spawns the backend at most once per session. The child is owned by this
   * session's StdioClientTransport and is only ever closed through it.
   * In shared-account mode, this delegates to the session's assigned owner.
   */
  ensureBackend() {
    // Shared-account mode: delegate to the assigned owner
    if (this.owner) {
      return this._ensureBackendShared();
    }
    // Per-session mode: original per-session logic
    return this._ensureBackendPerSession();
  }

  _ensureBackendShared() {
    // Refuse if session is already tainted or destroyed
    if (this.tainted || this.destroyed) {
      const err = new Error(`Session tainted: ${this.taintedReason ?? 'backend failure'}`);
      err.code = 'STUDIO_TAINTED';
      return Promise.reject(err);
    }
    if (this.owner.state === 'broken' || this.owner.closing) {
      this.taint('backend generation lost');
      return Promise.reject(new Error('Session tainted: backend generation lost'));
    }
    if (this.backendState === 'ready' && this.backendClient) {
      return Promise.resolve({ client: this.backendClient });
    }
    if (this.backendPromise) return this.backendPromise;

    this.backendState = 'connecting';

    this.backendPromise = (async () => {
      const { client, generation } = await this.owner.getClient();
      // Double-check: session may have been tainted while waiting
      if (this.tainted || this.destroyed) {
        throw new Error(`Session tainted: ${this.taintedReason ?? 'backend failure'}`);
      }
      this.backendClient = client;
      this.backendGeneration = generation;
      this.backendState = 'ready';
      return { client };
    })();

    this.backendPromise = this.backendPromise.finally(() => { this.backendPromise = null; });
    return this.backendPromise;
  }

  _ensureBackendPerSession() {
    if (this.tainted || this.destroyed || this.backendState === 'broken') {
      const err = new Error(`Session tainted: ${this.taintedReason ?? 'backend failure'}`);
      err.code = 'STUDIO_TAINTED';
      return Promise.reject(err);
    }
    if (this.backendState === 'ready' && this.backendClient) {
      return Promise.resolve({ client: this.backendClient });
    }
    if (this.backendPromise) return this.backendPromise;

    this.backendState = 'connecting';
    this.stats.backend.spawns += 1;

    const promise = (async () => {
      const transport = new StdioClientTransport({
        command: this.cfg.command,
        args: this.cfg.args,
        cwd: this.cfg.cwd,
        env: this.cfg.childEnv,
        // Backend stderr is discarded rather than piped into the gateway log:
        // it can carry file contents and paths, which this module must not log.
        stderr: 'ignore',
      });
      const client = new Client(
        { name: 'private-studio-mcp-gateway-backend', version: GATEWAY_VERSION },
        { capabilities: {} },
      );
      client.onclose = () => {
        if (this.closingBackend) return; // our own close is not a "loss"
        if (!this.destroyed && this.backendState !== 'broken') {
          this.backendState = 'broken';
          this.stats.backend.lost += 1;
          this.taint('backend disconnected');
        }
      };

      this.backendClient = client;
      this.backendTransport = transport;
      try {
        await client.connect(transport, { timeout: this.cfg.requestTimeoutMs });
        if (this.destroyed || this.tainted) {
          await client.close();
          throw new Error('Session closed during backend initialization');
        }
      } catch (err) {
        this.backendState = 'broken';
        this.stats.backend.lost += 1;
        this.taint('backend initialization failed');
        this.closingBackend = true;
        try { await transport.close(); } catch { /* ignore */ }
        this.closingBackend = false;
        throw err;
      }

      this.backendClient = client;
      this.backendTransport = transport;
      this.backendState = 'ready';
      return { client };
    })();

    this.backendPromise = promise.finally(() => { this.backendPromise = null; });
    return this.backendPromise;
  }

  /**
   * Closes the backend child through its own transport. Never inspects or
   * signals any process the gateway did not spawn.
   *
   * In shared-account mode: this session detaches from the owner; it does NOT
   * close the owner's transport (the owner lives for gateway lifetime).
   */
  async closeBackend() {
    if (this.closingBackend) return;

    if (this.owner) {
      // Shared mode: just clear this session's reference to the backend.
      // The owner is not closed — it may serve other sessions.
      this.backendClient = null;
      this.backendTransport = null;
      this.backendPromise = null;
      this.backendState = 'idle';
      this.backendGeneration = null;
      return;
    }

    // Per-session mode: output retention shares this backend lifetime.
    this.outputPager.clear();
    this.outputToolSchemas.clear();
    this.closingBackend = true;
    const transport = this.backendTransport;
    const client = this.backendClient;
    this.backendClient = null;
    this.backendTransport = null;
    this.backendPromise = null;
    this.backendState = 'broken';
    try {
      if (client) {
        try { await client.close(); } catch { /* ignore */ }
      }
      if (transport) {
        // StdioClientTransport.close() ends stdin, waits up to 2s for the
        // child to exit, then SIGTERM and finally SIGKILL — scoped strictly to
        // the child it spawned.
        try { await transport.close(); } catch { /* ignore */ }
      }
    } finally {
      this.closingBackend = false;
    }
  }

  /* ---- limiter wrapper: per-session cap plus busy accounting ---- */

  async withBackendSlot(fn, meta = {}) {
    this.touch();
    this.stats.requests.backendOps += 1;
    this.backendOpsInFlight += 1;
    const limiter = this.owner?.limiter ?? this.limiter;
    let acquired = null;
    try {
      try {
        acquired = await limiter.acquire({ priority: meta.catalogPriority === true });
      } catch (err) {
        this.stats.requests.busy += 1;
        log('warn', 'backend_slot_rejected', {sid:this.tag, kind:meta.kind,
          tool:meta.tool, classification:CLASSIFICATION.BUSY});
        throw err;
      }
      if (this.destroyed || this.tainted) throw new Error('Session closed or tainted before dispatch');
      return await fn();
    } finally {
      if (acquired) limiter.release(acquired);
      this.backendOpsInFlight -= 1;
      this.touch();
    }
  }

  /**
   * Poisons the session: the backend is torn down immediately and every later
   * request on this session is refused at the HTTP layer. The session record
   * itself is kept so the client gets an explicit "tainted" answer rather than
   * a bare 404 — except for DELETE, which still works so the client can clean
   * up.
   *
   * In shared-account mode: taint marks this session but does NOT close the
   * shared backend (other sessions remain unaffected). The owner is NOT
   * marked broken — only a backend onclose event breaks the owner.
   */
  taint(reason) {
    if (this.tainted) return;
    this.tainted = true;
    this.taintedReason = reason;
    this.stats.sessions.tainted += 1;
    log('warn', 'session_tainted', { sid: this.tag, reason });

    if (this.owner) {
      // Shared mode: drain only this session's limiter (not the shared one),
      // and do NOT close the shared backend. The owner remains available to
      // other untainted sessions.
      this.limiter.drain('Session tainted');
    } else {
      // Per-session mode: drain and close the backend.
      this.limiter.drain('Session tainted');
      void this.closeBackend();
    }
  }

  async destroy(reason) {
    if (this.destroyed) return;
    this.destroyed = true;
    this.destroyReason = reason;
    if (typeof this.onDestroyed === 'function') this.onDestroyed(this);
    this.limiter.drain('Session closed');

    // In shared mode, session detach from owner (but owner survives).
    this.owner?.sessions.delete(this);
    await this.closeBackend();

    try { await this.transport?.close(); } catch { /* ignore */ }
    try { await this.server?.close(); } catch { /* ignore */ }
    this.stats.sessions.ended += 1;
    log('info', 'session_destroyed', { sid: this.tag, reason });
  }
}

/* ------------------------------------------------------------------ *
 * startGateway
 * ------------------------------------------------------------------ */

/**
 * Start the HTTP gateway.
 *
 * @param {object} partialConfig see resolveConfig(); `port: 0` yields an
 *        ephemeral loopback port, reported back on the resolved object.
 * @param {{middleware?: Function, mount?: Function}} auth supplied by
 *        ./auth.mjs. `middleware(req,res,next)` must set `req.auth`;
 *        `mount(app)` installs the unauthenticated OAuth routes.
 * @returns {Promise<{url:string, baseUrl:string, host:string, port:number,
 *                    close:Function, stats:Function}>}
 */
export async function startGateway(partialConfig = {}, auth = {}) {
  const cfg = resolveConfig(partialConfig);
  const lists = buildAllowlists(cfg);

  /** Every live session, keyed by MCP session id. */
  const sessions = new Map();

  /** In shared-account mode: one BackendOwner per principalKey. */
  const owners = new Map();
  let shuttingDown = false;

  const stats = {
    get version() { return GATEWAY_VERSION; },
    get generation() { return GATEWAY_GENERATION; },
    get uptimeMs() { return Date.now() - BOOT_MS; },
    get hostname() { return HOSTNAME; },
    sessions: {
      started: 0,
      ended: 0,
      tainted: 0,
      rejectedCapacity: 0,
      reclaimed: 0,
    },
    requests: {
      backendOps: 0,
      timeouts: 0,
      busy: 0,
      crossPrincipal: 0,
      byTool: Object.create(null),
      byClassification: Object.create(null),
    },
    backend: { spawns: 0, lost: 0 },
  };
  let mcpRequestTotal = 0;
  let listeningAddress = null;

  function note(classification) {
    const byClassification = stats.requests.byClassification;
    byClassification[classification] = (byClassification[classification] || 0) + 1;
  }

  // Serializes capacity reservation so concurrent initializes cannot race
  // past maxSessions. Failures must not stall later admits.
  let admitTail = Promise.resolve();
  function withAdmitLock(fn) {
    const run = admitTail.then(() => fn(), () => fn());
    admitTail = run.then(() => undefined, () => undefined);
    return run;
  }

  function findCapacityVictim() {
    let oldestTainted = null;
    let oldestNormal = null;
    for (const session of sessions.values()) {
      if (!session.isQuiescentCapacityVictim()) continue;
      if (session.tainted) {
        if (!oldestTainted || session.createdAt < oldestTainted.createdAt) oldestTainted = session;
      } else if (!oldestNormal || session.createdAt < oldestNormal.createdAt) {
        oldestNormal = session;
      }
    }
    return oldestTainted || oldestNormal;
  }

  function capacityCounts() {
    let tainted = 0;
    let reclaimable = 0;
    let busy = 0;
    for (const session of sessions.values()) {
      if (session.tainted) tainted += 1;
      if (session.isQuiescentCapacityVictim()) reclaimable += 1;
      if (session.httpRequestsInFlight > 0 || session.backendOpsInFlight > 0 ||
          session.limiter.active > 0 || session.limiter.queued > 0 ||
          session.backendState === 'connecting') busy += 1;
    }
    return { tainted, reclaimable, busy };
  }

  function canAdmitNewSession() {
    if (sessions.size < cfg.maxSessions) return true;
    return cfg.reclaimIdleCatalogSessions && findCapacityVictim() !== null;
  }

  function reclaimCapacityVictim(victim) {
    sessions.delete(victim.id);
    stats.sessions.reclaimed += 1;
    const reason = victim.tainted ? 'tainted_capacity' : 'capacity';
    log('info', 'session_reclaimed', { sid: victim.tag, reason });
    void victim.destroy(reason);
  }

  /** Only a NEW frontend session can acquire a replacement generation. */
  async function ownerForPrincipal(principalKey, principalTag) {
    if (cfg.backendMode !== 'shared-account') return null;
    let owner = owners.get(principalKey);
    if (owner && owner.state !== 'broken') return owner;
    if (owner) {
      await owner.close();
      owners.delete(principalKey);
    }
    if (owners.size >= cfg.maxSessions) {
      for (const [key, candidate] of owners) {
        if (candidate.state === 'broken') {
          await candidate.close();
          owners.delete(key);
          break;
        }
      }
      if (owners.size >= cfg.maxSessions) return null;
    }
    owner = new BackendOwner({principalKey, principalTag, cfg, stats});
    owners.set(principalKey, owner);
    return owner;
  }

  /* ---- the express app ---- */

  const app = express();
  app.disable('x-powered-by');
  app.set('etag', false);

  // Trace transport stages without recording query strings, headers, tokens,
  // arguments, or returned file contents. This separates ingress/auth/body
  // delays from backend execution when a remote client stalls.
  app.use((req, res, next) => {
    const route = ['/mcp', '/.well-known/oauth-protected-resource',
      '/.well-known/oauth-protected-resource/mcp', '/.well-known/oauth-authorization-server'].includes(req.path)
      ? req.path : null;
    if (!route) return next();
    const trace = { id: randomUUID().slice(0, 8), route, method: req.method };
    const started = Date.now();
    req.__httpTrace = trace;
    log('info', 'http_received', trace);
    res.once('close', () => log('info', 'http_closed', {
      ...trace, status: res.statusCode, durationMs: Date.now() - started,
      complete: res.writableFinished,
    }));
    next();
  });

  /* 1. Host + Origin validation, before anything else. */
  app.use((req, res, next) => {
    if (!hostHeaderMatches(req.headers.host, lists.hosts)) {
      note(CLASSIFICATION.BAD_HOST);
      log('warn', 'reject_host', { host: safeHost(req.headers.host) });
      return sendJsonError(res, 403, CODE.GENERIC, 'Invalid Host header');
    }
    const origin = req.headers.origin;
    if (origin && !lists.origins.has(String(origin).toLowerCase())) {
      note(CLASSIFICATION.BAD_ORIGIN);
      log('warn', 'reject_origin', { origin: safeHost(origin) });
      return sendJsonError(res, 403, CODE.GENERIC, 'Invalid Origin header');
    }
    return next();
  });

  /* 2. Unauthenticated health endpoints. No paths, no principals, no tokens. */
  app.get('/healthz', (_req, res) => {
    res.status(200).json({ ok: true, version: GATEWAY_VERSION });
  });

  // Proves the process is bound and whether it can admit a new session.
  // Deliberately says nothing else: no ids, paths, or principals.
  app.get('/readyz', (_req, res) => {
    const accepting = Boolean(listeningAddress);
    const counts = capacityCounts();
    res.status(200).json({
      ok: true,
      ready: accepting && canAdmitNewSession(),
      accepting,
      version: GATEWAY_VERSION,
      uptimeMs: stats.uptimeMs,
      sessions: {
        active: sessions.size,
        capacity: cfg.maxSessions,
        full: sessions.size >= cfg.maxSessions,
        tainted: counts.tainted,
        reclaimable: counts.reclaimable,
        busy: counts.busy,
      },
    });
  });

  /* 3. OAuth routes: unauthenticated by design, so they must precede the
   *    global auth middleware. Supplied by ./auth.mjs, not implemented here. */
  if (typeof auth.mount === 'function') {
    auth.mount(app);
  }

  /* 4. Everything below this point requires auth. */
  app.use((req, res, next) => {
    if (typeof auth.middleware === 'function') {
      try {
        return auth.middleware(req, res, next);
      } catch (err) {
        return next(err);
      }
    }
    if (!cfg.testMode) {
      log('error', 'no_auth_middleware', {});
      return sendJsonError(res, 503, CODE.GENERIC,
        'Gateway misconfigured: no auth middleware available');
    }
    // testMode only: the principal binding still exists, it just collapses to
    // a single well-known value so cross-principal logic stays exercised.
    req.auth = { clientId: 'test-mode', principal: 'test-mode', scopes: [] };
    return next();
  });

  /* 5. The MCP endpoint. */
  const mcp = express.Router();

  mcp.use('/mcp', (_req, res, next) => {
    if (shuttingDown) return sendJsonError(res, 503, CODE.GENERIC, 'Gateway is shutting down');
    mcpRequestTotal += 1;
    next();
  });

  mcp.post('/mcp', (req, _res, next) => {
    log('info', 'http_authenticated', req.__httpTrace);
    next();
  }, express.json({ limit: MAX_BODY_BYTES }), (req, res, next) => {
    log('info', 'http_body_parsed', req.__httpTrace);
    handlePost(req, res).catch(next).finally(() => releaseInFlight(req));
  });
  mcp.get('/mcp', (req, res, next) => {
    handleGet(req, res).catch(next).finally(() => releaseInFlight(req));
  });
  mcp.delete('/mcp', (req, res, next) => {
    handleDelete(req, res).catch(next).finally(() => releaseInFlight(req));
  });

  app.use(mcp);

  /* 6. Any other path is already past auth; answer JSON, not an HTML page. */
  app.use((_req, res) => {
    note(CLASSIFICATION.NOT_FOUND);
    sendJsonError(res, 404, CODE.GENERIC, 'Not found');
  });

  /* 7. Body-parser and handler errors as machine-readable JSON. */
  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    const type = typeof err?.type === 'string' ? err.type : '';
    if (type === 'entity.parse.failed' || err instanceof SyntaxError) {
      note(CLASSIFICATION.PARSE_ERROR);
      return sendJsonError(res, 400, CODE.PARSE, 'Parse error: Invalid JSON');
    }
    if (type === 'entity.too.large') {
      note(CLASSIFICATION.PARSE_ERROR);
      return sendJsonError(res, 413, CODE.GENERIC, 'Request body too large');
    }
    if (type === 'charset.unsupported' || type === 'encoding.unsupported' ||
        type === 'entity.parse.failed') {
      note(CLASSIFICATION.UNSUPPORTED_MEDIA);
      return sendJsonError(res, 415, CODE.GENERIC, 'Unsupported media type');
    }
    const status = Number(err?.status || err?.statusCode || 500);
    log('error', 'request_error', { type: type || err?.name || 'Error' });
    return sendJsonError(res, status >= 400 && status < 600 ? status : 500,
      CODE.GENERIC, 'Internal gateway error');
  });

  /* ---- per-request bookkeeping ---- */

  /**
   * Drops the request's in-flight count when its socket closes. Reads
   * `req.__session` lazily because the session is attached inside the
   * handler, after this closure is created. Covers completed responses and
   * abandoned sockets alike.
   */
  function releaseInFlight(req) {
    const session = req.__session;
    if (session && !session.destroyed && session.httpRequestsInFlight > 0) {
      session.httpRequestsInFlight -= 1;
    }
  }

  function identityOf(req) {
    return principalKeyOf(req.auth);
  }

  function lookupSession(req, res, bodyId) {
    const sid = req.headers['mcp-session-id'];
    if (typeof sid !== 'string' || sid.length === 0) {
      note(CLASSIFICATION.PARSE_ERROR);
      sendJsonError(res, 400, CODE.GENERIC,
        'Bad Request: Mcp-Session-Id header is required', bodyId);
      return null;
    }
    const session = sessions.get(sid);
    if (!session || session.destroyed) {
      note(CLASSIFICATION.UNKNOWN_SESSION);
      sendJsonError(res, 404, CODE.SESSION_NOT_FOUND, 'Session not found', bodyId);
      return null;
    }
    // Re-derived from req.auth on this very request, never from stored state.
    const principal = identityOf(req);
    if (session.principalKey !== principal) {
      stats.requests.crossPrincipal += 1;
      note(CLASSIFICATION.CROSS_PRINCIPAL);
      log('warn', 'reject_cross_principal', {
        sid: session.tag, principal: shortTag(principal),
      });
      sendJsonError(res, 403, CODE.GENERIC,
        'Session belongs to a different principal', bodyId);
      return null;
    }
    if (session.tainted && req.method !== 'DELETE') {
      note(CLASSIFICATION.TAINTED);
      sendJsonError(res, 409, CODE.TAINTED,
        `Session tainted: ${session.taintedReason ?? 'backend failure'}. ` +
        'Re-initialize to create a new session.', bodyId);
      return null;
    }
    return session;
  }

  /** Admits a request against a session and arranges for the release. */
  function admit(req, session) {
    session.httpRequestsInFlight += 1;
    req.__session = session;
    session.touch();
  }

  /* ---- POST: initialize creates a session; everything else re-binds ---- */

  async function handlePost(req, res) {
    const body = req.body;

    const contentType = req.headers['content-type'];
    if (typeof contentType !== 'string' || !contentType.toLowerCase().includes('json')) {
      note(CLASSIFICATION.UNSUPPORTED_MEDIA);
      return sendJsonError(res, 415, CODE.GENERIC,
        'Unsupported Media Type: expected application/json', bodyId(body));
    }
    if (Array.isArray(body)) {
      note(CLASSIFICATION.PARSE_ERROR);
      return sendJsonError(res, 400, CODE.PARSE, 'JSON-RPC batching is not supported');
    }
    if (!isJsonObject(body) || typeof body.method !== 'string') {
      note(CLASSIFICATION.PARSE_ERROR);
      return sendJsonError(res, 400, CODE.PARSE,
        'Parse error: Invalid JSON-RPC message', bodyId(body));
    }

    if (isInitializeRequest(body)) {
      return handleInitialize(req, res, body);
    }

    const session = lookupSession(req, res, bodyId(body));
    if (!session) return;
    if (body.method === 'tools/call') {
      if (!['string', 'number'].includes(typeof body.id)) {
        return sendJsonError(res, 400, CODE.PARSE, 'tools/call requires a request id', bodyId(body));
      }
      const idKey = JSON.stringify(body.id);
      if (session.toolRequestIds.has(idKey)) {
        return sendJsonError(res, 409, CODE.GENERIC,
          'Duplicate request id: this call will not execute again. Inspect the original outcome.', body.id);
      }
      if (session.toolRequestIds.size >= 4096) {
        return sendJsonError(res, 409, CODE.CAPACITY,
          'Session call budget exhausted. Initialize a new session for future work.', body.id);
      }
      // Retain IDs for the whole session, including failures and lost responses.
      session.toolRequestIds.add(idKey);
    }
    session.noteAdmittedWork(body);
    admit(req, session);
    note(CLASSIFICATION.OK);
    try {
      await session.transport.handleRequest(req, res, body);
    } catch (err) {
      log('error', 'mcp_post_failed', { sid: session.tag, error: err?.name || 'Error' });
      if (!res.headersSent) {
        sendJsonError(res, 500, CODE.GENERIC, 'Internal gateway error', bodyId(body));
      }
    }
  }

  async function handleInitialize(req, res, body) {
    const principal = identityOf(req);
    if (req.headers['mcp-session-id']) {
      return sendJsonError(res, 409, CODE.GENERIC, 'Initialize requires a new connection without a prior session id', body.id);
    }

    if (typeof body.id === 'undefined') {
      note(CLASSIFICATION.PARSE_ERROR);
      return sendJsonError(res, 400, CODE.PARSE, 'initialize must carry a request id');
    }

    const reserved = await withAdmitLock(async () => {
      if (sessions.size >= cfg.maxSessions && cfg.reclaimIdleCatalogSessions) {
        const victim = findCapacityVictim();
        if (victim) reclaimCapacityVictim(victim);
      }
      if (sessions.size >= cfg.maxSessions) {
        return { status: 'capacity' };
      }
      const id = randomUUID();

      // In shared-account mode, get or create the owner for this principal.
      // A broken owner is replaced here; old sessions keep their old owner.
      const owner = await ownerForPrincipal(principal, shortTag(principal));
      if (!owner && cfg.backendMode === 'shared-account') {
        // ownerForPrincipal returned null because all owner slots are taken by
        // non-broken owners. In practice this means maxSessions is exhausted.
        return { status: 'capacity' };
      }

      const session = new GatewaySession({
        id,
        principalKey: principal,
        principalTag: shortTag(principal),
        cfg,
        lists,
        stats,
        onDestroyed(destroyed) { sessions.delete(destroyed.id); },
        owner, // null in per-session mode
      });
      const transport = session.buildTransport();
      session.buildServer();
      try {
        await session.server.connect(transport);
      } catch (err) {
        log('error', 'session_bootstrap_failed', { error: err?.name || 'Error' });
        await session.destroy('bootstrap_failed');
        return { status: 'bootstrap_failed' };
      }
      // Slot reserved before the admit lock drops, so a concurrent
      // initialize cannot oversubscribe the cap.
      sessions.set(id, session);
      return { status: 'ready', session };
    });

    if (reserved.status === 'capacity') {
      stats.sessions.rejectedCapacity += 1;
      note(CLASSIFICATION.CAPACITY);
      log('warn', 'reject_capacity', { active: sessions.size, cap: cfg.maxSessions });
      return sendJsonError(res, 503, CODE.CAPACITY,
        'Too many active sessions; close one and retry', body.id);
    }
    if (reserved.status !== 'ready') {
      return sendJsonError(res, 500, CODE.GENERIC, 'Failed to start session', body.id);
    }

    const session = reserved.session;
    const id = session.id;
    const transport = session.transport;
    admit(req, session);
    note(CLASSIFICATION.OK);

    try {
      await transport.handleRequest(req, res, body);
    } catch (err) {
      log('error', 'initialize_failed', { sid: session.tag, error: err?.name || 'Error' });
      sessions.delete(id);
      await session.destroy('initialize_failed');
      if (!res.headersSent) {
        sendJsonError(res, 500, CODE.GENERIC, 'Failed to initialize session', body.id);
      }
    }
  }

  /* ---- GET: this connector does not send unsolicited server events ---- */

  async function handleGet(req, res) {
    const session = lookupSession(req, res);
    if (!session) return;
    // MCP permits 405 here. Keeping an idle SSE connection open can occupy
    // a serial proxy connection and prevent later POSTs reaching the server.
    // Request-scoped POST streaming remains available for tool responses.
    res.set('Allow', 'POST, DELETE').status(405).json({
      error: 'Standalone event streams are not supported; use MCP POST requests.',
    });
  }

  /* ---- DELETE: closes this principal's own session, and no other ---- */

  async function handleDelete(req, res) {
    const session = lookupSession(req, res);
    if (!session) return;
    admit(req, session);
    note(CLASSIFICATION.OK);
    // Delegates to the transport, whose close() fires onsessionclosed ->
    // session.destroy() -> closeBackend(). Ownership was verified in
    // lookupSession immediately above, so only the caller's own session is
    // ever torn down.
    await session.transport.handleRequest(req, res);
  }

  /* ---- idle expiry ---- */

  const sweeper = setInterval(() => {
    const now = Date.now();
    for (const session of [...sessions.values()]) {
      if (session.destroyed) {
        sessions.delete(session.id);
        continue;
      }
      const idleFor = now - session.lastActive;
      if (idleFor < cfg.idleTimeoutMs) continue;
      // Expire only when nothing is in flight: no HTTP request (including an
      // open SSE stream) and no running or queued backend operation.
      if (session.httpRequestsInFlight > 0) continue;
      if (session.limiter.active > 0 || session.limiter.queued > 0) continue;
      log('info', 'session_expired_idle', { sid: session.tag, idleMs: idleFor });
      sessions.delete(session.id);
      void session.destroy('idle_expiry');
    }
  }, SESSION_SWEEP_INTERVAL_MS);
  sweeper.unref();

  /* ---- listen ---- */

  const server = await new Promise((resolve, reject) => {
    const httpServer = app.listen(cfg.port, cfg.host, () => resolve(httpServer));
    httpServer.once('error', reject);
  });
  const addr = server.address();
  listeningAddress = addr;
  const boundPort = addr && typeof addr === 'object' ? addr.port : cfg.port;
  addLoopbackAliases(lists, boundPort);

  const baseUrl = cfg.publicUrl
    ? cfg.publicUrl.origin
    : `http://${cfg.host}:${boundPort}`;
  const url = `${baseUrl}/mcp`;

  log('info', 'gateway_started', {
    host: cfg.host,
    port: boundPort,
    testMode: cfg.testMode,
    public: Boolean(cfg.publicUrl),
    generation: GATEWAY_GENERATION,
    backendMode: cfg.backendMode,
  });

  let closePromise;
  function close() {
    if (closePromise) return closePromise;
    shuttingDown = true;
    closePromise = (async () => {
      clearInterval(sweeper);
      listeningAddress = null;
      await admitTail;

      // Close all remaining owned backends. Broken predecessors were already
      // closed before replacement.
      const ownerClose = [...owners.values()].map((o) => o.close());
      await Promise.allSettled(ownerClose);
      owners.clear();

      // Destroy all sessions.
      const teardown = [...sessions.values()].map((s) => s.destroy('gateway_shutdown'));
      sessions.clear();
      await Promise.allSettled(teardown);

      await new Promise((resolve) => {
        server.close(() => resolve());
        // Session transports are closed above; release any leftover HTTP sockets
        // owned by this gateway, including abandoned SSE/partial requests.
        server.closeAllConnections();
      });
      log('info', 'gateway_stopped', {});
    })();
    return closePromise;
  }

  /** Fresh snapshot of gateway counters. No secrets, no tool arguments. */
  function statsSnapshot() {
    return {
      version: GATEWAY_VERSION,
      generation: GATEWAY_GENERATION,
      hostname: HOSTNAME,
      uptimeMs: stats.uptimeMs,
      listening: {
        host: cfg.host,
        port: boundPort,
        accepting: Boolean(listeningAddress),
      },
      sessions: {
        active: sessions.size,
        capacity: cfg.maxSessions,
        started: stats.sessions.started,
        ended: stats.sessions.ended,
        tainted: stats.sessions.tainted,
        rejectedCapacity: stats.sessions.rejectedCapacity,
        reclaimed: stats.sessions.reclaimed,
      },
      requests: {
        mcpTotal: mcpRequestTotal,
        backendOps: stats.requests.backendOps,
        timeouts: stats.requests.timeouts,
        busy: stats.requests.busy,
        crossPrincipal: stats.requests.crossPrincipal,
        byTool: { ...stats.requests.byTool },
        byClassification: { ...stats.requests.byClassification },
      },
      backend: {
        spawns: stats.backend.spawns,
        lost: stats.backend.lost,
        // Expose backend generation per owner (shared mode only).
        // Useful for tests that verify different principals got different generations.
        ...(cfg.backendMode === 'shared-account' && {
          owners: [...owners.entries()].map(([key, o]) => ({
            principal: o.principalTag,
            generation: o.generation,
            state: o.state,
          })),
        }),
      },
    };
  }

  // `stats` is callable, and also exposes the same numbers as live getters for
  // property-style access (`gw.stats.live.sessions.active`).
  statsSnapshot.live = {
    get version() { return GATEWAY_VERSION; },
    get generation() { return GATEWAY_GENERATION; },
    get uptimeMs() { return stats.uptimeMs; },
    get url() { return url; },
    get sessions() {
      return {
        get active() { return sessions.size; },
        get capacity() { return cfg.maxSessions; },
        get started() { return stats.sessions.started; },
        get ended() { return stats.sessions.ended; },
        get tainted() { return stats.sessions.tainted; },
      };
    },
    get requests() {
      return {
        get mcpTotal() { return mcpRequestTotal; },
        get backendOps() { return stats.requests.backendOps; },
        get timeouts() { return stats.requests.timeouts; },
        get busy() { return stats.requests.busy; },
        get crossPrincipal() { return stats.requests.crossPrincipal; },
        get byTool() { return { ...stats.requests.byTool }; },
        get byClassification() { return { ...stats.requests.byClassification }; },
      };
    },
    get backend() {
      return {
        get spawns() { return stats.backend.spawns; },
        get lost() { return stats.backend.lost; },
      };
    },
  };

  return { url, baseUrl, host: cfg.host, port: boundPort, close, stats: statsSnapshot };
}

/* ------------------------------------------------------------------ *
 * helpers
 * ------------------------------------------------------------------ */

function isJsonObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function bodyId(body) {
  if (isJsonObject(body) &&
      (typeof body.id === 'string' || typeof body.id === 'number' || body.id === null)) {
    return body.id;
  }
  return null;
}

/** Same JSON-RPC error envelope the SDK transport emits. */
function sendJsonError(res, status, code, message, id = null) {
  if (res.headersSent) {
    try { res.end(); } catch { /* ignore */ }
    return;
  }
  res.status(status);
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify({ jsonrpc: '2.0', error: { code, message }, id: id ?? null }));
}

/* ------------------------------------------------------------------ *
 * CLI
 * ------------------------------------------------------------------ */

function isMainModule() {
  try {
    return Boolean(process.argv[1]) &&
      path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
  } catch {
    return false;
  }
}

/**
 * CLI entry: `node gateway.mjs <config.json>`.
 * Relative backend paths in the config are resolved against the config file's
 * own directory, so the documented `../dist/index.js` default works from any
 * working directory.
 */
async function main() {
  const configPath = process.argv[2];
  if (!configPath) {
    process.stderr.write('usage: node gateway.mjs <config.json>\n');
    process.exitCode = 1;
    return;
  }

  const fs = await import('node:fs/promises');
  let raw;
  try {
    raw = JSON.parse(await fs.readFile(configPath, 'utf8'));
  } catch (err) {
    process.stderr.write(`gateway: cannot read config ${configPath}: ${err.message}\n`);
    process.exitCode = 1;
    return;
  }

  const configDir = path.dirname(path.resolve(configPath));
  if (Array.isArray(raw.args)) {
    raw.args = raw.args.map((a) =>
      (typeof a === 'string' && a.startsWith('../') ? path.resolve(configDir, a) : a));
  }
  for (const key of ['cwd', 'stateDir']) {
    if (typeof raw[key] === 'string' && !path.isAbsolute(raw[key])) {
      raw[key] = path.resolve(configDir, raw[key]);
    }
  }

  const cfg = resolveConfig(raw);
  const { createAuth } = await import('./auth.mjs');
  const auth = await createAuth({
    publicUrl: cfg.publicUrl ? cfg.publicUrl.toString() : undefined,
    stateDir: cfg.stateDir,
    host: cfg.host,
    port: cfg.port,
    testMode: cfg.testMode,
  });

  const gateway = await startGateway(cfg, auth);
  process.stderr.write(`gateway: listening on ${gateway.url}\n`);

  let shuttingDown = false;
  const shutdown = async (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    log('info', 'signal', { signal });
    try {
      await gateway.close();
    } finally {
      process.exit(0);
    }
  };
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
  process.on('SIGINT', () => void shutdown('SIGINT'));
}

if (isMainModule()) {
  main().catch((err) => {
    process.stderr.write(`gateway: fatal: ${err?.stack || err}\n`);
    process.exitCode = 1;
  });
}

export default startGateway;
