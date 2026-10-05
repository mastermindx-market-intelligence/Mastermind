#!/usr/bin/env node
// Tailnet Studio Direct gateway: one loopback startGateway for the Mastermind
// subagent-fabric channel, reverse-proxied by Tailscale Serve.
//
// This is NOT a public Paper gateway. The process still binds exactly
// 127.0.0.1, uses the same guarded Studio/Paper gateway, and reuses
// createTunnelAuth's exact loopback-peer principal binding. The only transport
// difference from private-tunnel-gateway.mjs is that Host/Origin validation
// also admits one exact tailnet HTTPS origin so Tailscale Serve may preserve
// the external Host header.
//
// Tailscale identity/app-capability headers are deliberately ignored here.
// Tailnet ACL/Serve controls transport reachability; Studio Direct binds each
// request to one of the two closed fabric principals below. No header can
// widen a route, select a host/Paper target, or create another authority plane.

import { fileURLToPath } from 'node:url';
import { resolve as resolvePath } from 'node:path';

import { startGateway } from './gateway.mjs';
import { createTunnelAuth, TUNNEL_CLIENT_ID, TUNNEL_SCOPE } from './private-tunnel-auth.mjs';
import { installSignalHandlers, loadPrivateTunnelConfig } from './private-tunnel-gateway.mjs';
import { FLEET_BACKEND_TOOL_NAMES } from './fleet-routing.mjs';

export const TAILNET_PROFILES = Object.freeze({
  'fabric-read': Object.freeze([
    'studio_ping',
    'studio_fleet_status',
    'paper_inspect',
    'paper_catalog',
    'paper_read',
  ]),
  'fabric-design': Object.freeze([
    'studio_ping',
    'studio_fleet_status',
    'paper_inspect',
    'paper_catalog',
    'paper_read',
    'paper_prepare',
    'paper_edit',
  ]),
  'fleet-host': Object.freeze([
    'studio_ping',
    'studio_output_page',
    ...FLEET_BACKEND_TOOL_NAMES,
  ]),
});
export const REQUIRED_HOST = '127.0.0.1';
export const RESERVED_FUNNEL_PORT = 45017;
const TAILNET_SUFFIX = '.ts.net';

export class TailnetGatewayConfigError extends TypeError {}

function absent(value) {
  return value === undefined || value === null || value === '';
}

function parseTailnetOrigin(value) {
  if (typeof value !== 'string' || value.length < 1 || value.length > 2048) {
    throw new TailnetGatewayConfigError('tailnet gateway publicUrl must be an https tailnet origin');
  }
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new TailnetGatewayConfigError('tailnet gateway publicUrl must be an https tailnet origin');
  }
  if (
    url.protocol !== 'https:' ||
    !url.hostname.endsWith(TAILNET_SUFFIX) ||
    url.hostname.length <= TAILNET_SUFFIX.length ||
    (url.pathname !== '/' && url.pathname !== '') ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new TailnetGatewayConfigError('tailnet gateway publicUrl must be an https tailnet origin');
  }
  return url.origin;
}

export function resolveTailnetGatewayConfig(partial = {}) {
  if (partial === null || typeof partial !== 'object' || Array.isArray(partial)) {
    throw new TailnetGatewayConfigError('tailnet gateway config must be an object');
  }
  const config = { ...partial };

  const accountLabel = config.accountLabel;
  if (
    typeof accountLabel !== 'string' ||
    !Object.prototype.hasOwnProperty.call(TAILNET_PROFILES, accountLabel)
  ) {
    throw new TailnetGatewayConfigError(
      'tailnet gateway accountLabel must be fabric-read, fabric-design, or fleet-host');
  }
  if (config.toolAllowlist !== undefined && config.toolAllowlist !== null) {
    throw new TailnetGatewayConfigError(
      'tailnet gateway toolAllowlist is profile-owned and cannot be supplied');
  }
  config.toolAllowlist = TAILNET_PROFILES[accountLabel];

  if (!absent(config.host) && config.host !== REQUIRED_HOST) {
    throw new TailnetGatewayConfigError(
      `tailnet gateway host is fixed to ${REQUIRED_HOST}`);
  }
  config.host = REQUIRED_HOST;

  if (!absent(config.testMode) && config.testMode !== false) {
    throw new TailnetGatewayConfigError('tailnet gateway testMode must be false or absent');
  }
  config.testMode = false;

  if (!Number.isInteger(config.port) || config.port < 0 || config.port > 65535) {
    throw new TailnetGatewayConfigError(
      'tailnet gateway port must be an explicit integer 0..65535');
  }
  if (config.port === RESERVED_FUNNEL_PORT) {
    throw new TailnetGatewayConfigError(
      `tailnet gateway port must not be ${RESERVED_FUNNEL_PORT}`);
  }

  config.publicUrl = parseTailnetOrigin(config.publicUrl);

  if (config.backendMode !== undefined && config.backendMode !== 'shared-account') {
    throw new TailnetGatewayConfigError(
      'tailnet gateway backendMode is fixed to shared-account');
  }
  config.backendMode = 'shared-account';
  config.reclaimIdleCatalogSessions = true;

  const auth = createTunnelAuth({ accountLabel });
  delete config.accountLabel;
  return { config, auth, accountLabel };
}

export async function startTailnetGateway(config = {}) {
  const { config: resolved, auth, accountLabel } = resolveTailnetGatewayConfig(config);
  const gateway = await startGateway(resolved, auth);
  return Object.assign(gateway, {
    accountLabel,
    principal: auth.principal,
    auth,
  });
}

export async function main(argv = process.argv) {
  const configPath = argv[2];
  if (!configPath) {
    process.stderr.write(
      'usage: node tailnet-gateway.mjs <config.json>\n' +
      'requires accountLabel=fabric-read|fabric-design|fleet-host, loopback bind, and https://*.ts.net publicUrl\n');
    process.exitCode = 1;
    return null;
  }
  const raw = await loadPrivateTunnelConfig(configPath);
  const gateway = await startTailnetGateway(raw);
  gateway.signals = installSignalHandlers(gateway);
  process.stderr.write(
    `tailnet-gateway: account ${gateway.accountLabel} listening on ${gateway.url}\n`);
  return gateway;
}

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
    process.stderr.write(`tailnet-gateway: fatal: ${err?.stack || err}\n`);
    process.exitCode = 1;
  });
}

export { TUNNEL_CLIENT_ID, TUNNEL_SCOPE };
