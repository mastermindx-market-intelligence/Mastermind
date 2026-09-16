#!/usr/bin/env node
// Private Studio Direct tunnel gateway: one loopback `startGateway` per owned
// account, fronting a ChatGPT "No Auth" Secure MCP Tunnel.
//
// This adapter calls the same `startGateway` the OAuth service uses, so every
// engine invariant is inherited unchanged: one SDK HTTP transport plus one
// stdio engine child per MCP session, principal-bound sessions, the 4+4
// account-wide limiter, duplicate-id 409, and timeout/loss answered as
// EFFECT_UNKNOWN with no retry. Nothing here retries a `tools/call`, ever.
//
// Deliberate differences from the OAuth service listener:
//   - auth is `createTunnelAuth({ accountLabel })`, never production
//     `createAuth()`; this module does not import ./auth.mjs
//   - bind is exactly 127.0.0.1, no `publicUrl`, `testMode` stays false
//   - the Funnel listener's port 45017 is refused, so the two can never merge
//
// Configuration (backend command, args, cwd, childEnv, stateDir) is passed in
// by the operator; this module resolves no credentials and reads no key store.

import { fileURLToPath } from 'node:url';
import { dirname, isAbsolute, resolve as resolvePath } from 'node:path';
import { readFile } from 'node:fs/promises';

import { startGateway } from './gateway.mjs';
import { createTunnelAuth, TUNNEL_CLIENT_ID, TUNNEL_SCOPE } from './private-tunnel-auth.mjs';

/** The only host a private tunnel may bind. */
const REQUIRED_HOST = '127.0.0.1';

/** Existing OAuth/Funnel listener; a private tunnel must never take it. */
const RESERVED_FUNNEL_PORT = 45017;

/** Thrown for a private tunnel configuration that would weaken the listener. */
export class PrivateTunnelConfigError extends TypeError {}

function isAbsent(value) {
  return value === undefined || value === null;
}

/**
 * Validate the operator's config for one private tunnel listener.
 *
 * Rejects — rather than normalizes — anything that would silently weaken the
 * listener: `testMode`, a `publicUrl`, a non-127.0.0.1 `host`, a missing or
 * reserved `port`, or an unsafe `accountLabel`.
 *
 * @param {object} partial same shape as `resolveConfig` plus `accountLabel`
 * @returns {{config:object, auth:object}} config ready for `startGateway` and
 *          the auth object to pair with it
 */
export function resolvePrivateTunnelConfig(partial = {}) {
  if (partial === null || typeof partial !== 'object' || Array.isArray(partial)) {
    throw new PrivateTunnelConfigError(
      `private tunnel config must be an object (got ${Array.isArray(partial) ? 'array' : typeof partial})`);
  }
  const config = { ...partial };

  // `testMode` collapses every caller to principal `test-mode`; a private
  // tunnel must present its own principal, so true/'true'/1 are all refused.
  if (!isAbsent(config.testMode) && config.testMode !== false) {
    throw new PrivateTunnelConfigError(
      `private tunnel config.testMode must be false or absent (got ${JSON.stringify(config.testMode)})`);
  }
  config.testMode = false;

  // No publicUrl: the Host/Origin allow-list stays the loopback aliases of the
  // bound port. A public origin would admit Funnel traffic on a listener that
  // has no bearer check.
  if (!isAbsent(config.publicUrl) && config.publicUrl !== '') {
    throw new PrivateTunnelConfigError(
      `private tunnel config.publicUrl must be absent or null (got ${JSON.stringify(config.publicUrl)})`);
  }
  config.publicUrl = null;

  // Bind exactly 127.0.0.1. The gateway itself would also accept '::1' or
  // 'localhost'; the tunnel refuses them so the configured bind and the
  // loopback peer check can never drift apart.
  if (!isAbsent(config.host) && config.host !== '' && config.host !== REQUIRED_HOST) {
    throw new PrivateTunnelConfigError(
      `private tunnel config.host must be ${REQUIRED_HOST} or absent (got ${JSON.stringify(config.host)})`);
  }
  config.host = REQUIRED_HOST;

  // An explicit port is required: defaulting would land on 45017, the live
  // OAuth/Funnel listener. Port 0 (ephemeral) is for tests only.
  if (!Number.isInteger(config.port) || config.port < 0 || config.port > 65535) {
    throw new PrivateTunnelConfigError(
      `private tunnel config.port must be an explicit integer 0..65535 (got ${JSON.stringify(config.port)})`);
  }
  if (config.port === RESERVED_FUNNEL_PORT) {
    throw new PrivateTunnelConfigError(
      `private tunnel config.port must not be ${RESERVED_FUNNEL_PORT}: that is the OAuth/Funnel listener`);
  }

  // The label is the principal; validation and fixing of clientId/scope live
  // in createTunnelAuth and throw on anything unsafe or conflicting.
  const auth = createTunnelAuth({ accountLabel: config.accountLabel });
  delete config.accountLabel;

  // backendMode: only 'shared-account' or 'per-session' are valid; anything
  // else is a config error rather than silently defaulting to per-session.
  if (config.backendMode !== undefined && config.backendMode !== 'shared-account' && config.backendMode !== 'per-session') {
    throw new PrivateTunnelConfigError(
      `private tunnel config.backendMode must be 'shared-account' or 'per-session' (got ${JSON.stringify(config.backendMode)})`);
  }
  config.backendMode ??= 'shared-account';
  config.reclaimIdleCatalogSessions ??= true;
  // Note: resolveConfig inside startGateway will also validate, but we check
  // here so the error is thrown before startGateway is called.

  return { config, auth };
}

/**
 * Start a dedicated private tunnel listener.
 *
 * @param {object} config see `resolvePrivateTunnelConfig`; the backend is
 *        supplied here (`command`, `args`, `cwd`, `childEnv`, `stateDir`)
 * @returns {Promise<{url:string, baseUrl:string, host:string, port:number,
 *                    accountLabel:string, principal:string, auth:object,
 *                    close:Function, stats:Function}>}
 */
export async function startPrivateGateway(config = {}) {
  const { config: resolved, auth } = resolvePrivateTunnelConfig(config);
  const gateway = await startGateway(resolved, auth);
  return Object.assign(gateway, {
    accountLabel: auth.accountLabel,
    principal: auth.principal,
    auth,
  });
}

/**
 * Read a tunnel config file. Mirrors `gateway.mjs`'s CLI: relative `args`
 * starting with '../' and relative `cwd`/`stateDir` resolve against the
 * directory holding the config, so the documented defaults work from anywhere.
 *
 * @param {string} configPath
 * @returns {Promise<object>} parsed, path-resolved config
 */
export async function loadPrivateTunnelConfig(configPath) {
  let raw;
  try {
    raw = JSON.parse(await readFile(configPath, 'utf8'));
  } catch (err) {
    throw new PrivateTunnelConfigError(`cannot read tunnel config ${configPath}: ${err.message}`);
  }
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new PrivateTunnelConfigError(`tunnel config ${configPath} must be a JSON object`);
  }
  const resolved = { ...raw };
  const configDir = dirname(resolvePath(configPath));
  if (Array.isArray(resolved.args)) {
    resolved.args = resolved.args.map((a) =>
      (typeof a === 'string' && a.startsWith('../') ? resolvePath(configDir, a) : a));
  }
  for (const key of ['cwd', 'stateDir']) {
    if (typeof resolved[key] === 'string' && !isAbsolute(resolved[key])) {
      resolved[key] = resolvePath(configDir, resolved[key]);
    }
  }
  return resolved;
}

/**
 * SIGTERM/SIGINT handling for the CLI: close the gateway (which destroys every
 * session and engine child) and exit. Never restarts, never retries work.
 *
 * @param {{close:Function}} gateway
 * @param {{write?:Function}} [out] stderr-like sink
 * @returns {{dispose:Function}} removes the listeners again
 */
export function installSignalHandlers(gateway, out = process.stderr) {
  const write = typeof out?.write === 'function' ? (s) => out.write(s) : () => {};
  let shuttingDown = false;
  const shutdown = async (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    write(`private-tunnel-gateway: ${signal}, closing listener\n`);
    try {
      await gateway.close();
    } finally {
      process.exit(0);
    }
  };
  const onTerm = () => void shutdown('SIGTERM');
  const onInt = () => void shutdown('SIGINT');
  process.on('SIGTERM', onTerm);
  process.on('SIGINT', onInt);
  return {
    dispose() {
      process.off('SIGTERM', onTerm);
      process.off('SIGINT', onInt);
    },
  };
}

/**
 * CLI entry: `node private-tunnel-gateway.mjs <config.json>`.
 * Loads the JSON config, validates it, boots the dedicated loopback listener
 * and stays up until SIGTERM/SIGINT.
 *
 * @param {string[]} argv defaults to `process.argv`
 * @returns {Promise<object>} the running gateway handle (tests close it)
 */
export async function main(argv = process.argv) {
  const configPath = argv[2];
  if (!configPath) {
    process.stderr.write(
      `usage: node private-tunnel-gateway.mjs <config.json>\n` +
      `config keys: accountLabel, port, command, args, cwd, childEnv, stateDir, gitPublish\n`);
    process.exitCode = 1;
    return null;
  }

  const raw = await loadPrivateTunnelConfig(configPath);
  const gateway = await startPrivateGateway(raw);
  // Exposed on the handle so an embedder (and the tests) can detach the
  // handlers again; the CLI itself never needs to.
  gateway.signals = installSignalHandlers(gateway);
  process.stderr.write(
    `private-tunnel-gateway: account ${gateway.accountLabel} ` +
    `listening on ${gateway.url}\n`);
  return gateway;
}

/** True only when executed directly, never when imported by the tests. */
function isMainModule() {
  try {
    return Boolean(process.argv[1]) &&
      resolvePath(process.argv[1]) === fileURLToPath(import.meta.url);
  } catch {
    return false;
  }
}

if (isMainModule()) {
  main().catch((err) => {
    process.stderr.write(`private-tunnel-gateway: fatal: ${err?.stack || err}\n`);
    process.exitCode = 1;
  });
}

export { TUNNEL_CLIENT_ID, TUNNEL_SCOPE };
