#!/usr/bin/env node
/**
 * Local Claude Desktop stdio projection for the guarded Studio/Paper MCP.
 *
 * This process owns no Paper, fleet, placement, authentication, or tool
 * authority. It mirrors one already-installed loopback Studio route into
 * stdio for Claude Desktop's local-MCP mechanism and refuses catalog drift.
 */
import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

export const ROUTES = Object.freeze({
  read: Object.freeze({
    account: 'fabric-read',
    tools: Object.freeze([
      'paper_catalog',
      'paper_inspect',
      'paper_read',
      'studio_fleet_status',
      'studio_ping',
    ]),
  }),
  design: Object.freeze({
    account: 'fabric-design',
    tools: Object.freeze([
      'paper_catalog',
      'paper_edit',
      'paper_inspect',
      'paper_prepare',
      'paper_read',
      'studio_fleet_status',
      'studio_ping',
    ]),
  }),
});

function routeSpec(routeValue) {
  const route = String(routeValue || '').trim().toLowerCase();
  const spec = ROUTES[route];
  if (!spec) throw new Error('STUDIO_ROUTE_REFUSED');
  return { route, spec };
}

export async function routeUrl(
  routeValue,
  {
    home = process.env.HOME || homedir(),
    readManifest = async (path) => JSON.parse(await readFile(path, 'utf8')),
  } = {},
) {
  const { route, spec } = routeSpec(routeValue);
  const manifestPath = join(
    String(home || ''),
    '.local',
    'share',
    'studio-direct-mcp',
    'private',
    spec.account,
    'manifest.json',
  );
  let manifest;
  try {
    manifest = await readManifest(manifestPath);
  } catch {
    throw new Error('STUDIO_RUNTIME_UNAVAILABLE');
  }
  if (
    !manifest ||
    typeof manifest !== 'object' ||
    manifest.account !== spec.account ||
    !Number.isInteger(manifest.port) ||
    manifest.port < 1 ||
    manifest.port > 65535
  ) {
    throw new Error('STUDIO_RUNTIME_REFUSED');
  }
  return {
    route,
    account: spec.account,
    manifestPath,
    url: `http://127.0.0.1:${manifest.port}/mcp`,
  };
}

export function assertCatalog(routeValue, toolsValue) {
  const { spec } = routeSpec(routeValue);
  if (!Array.isArray(toolsValue)) throw new Error('STUDIO_CATALOG_REFUSED');

  const actual = [];
  for (const row of toolsValue) {
    if (!row || typeof row !== 'object' || typeof row.name !== 'string') {
      throw new Error('STUDIO_CATALOG_REFUSED');
    }
    actual.push(row.name);
  }
  if (new Set(actual).size !== actual.length) {
    throw new Error('STUDIO_CATALOG_REFUSED');
  }
  const expected = [...spec.tools].sort();
  actual.sort();
  if (
    expected.length !== actual.length ||
    expected.some((name, index) => name !== actual[index])
  ) {
    throw new Error('STUDIO_CATALOG_REFUSED');
  }
  return true;
}

export async function createBridge({
  route,
  home = process.env.HOME || homedir(),
  readManifest,
  remoteClient = null,
  remoteTransport = null,
} = {}) {
  const resolved = await routeUrl(route, { home, readManifest });
  const client = remoteClient ?? new Client(
    { name: 'mastermind-claude-desktop-studio-bridge', version: '1.0.0' },
    { capabilities: {} },
  );
  const transport = remoteTransport ?? new StreamableHTTPClientTransport(
    new URL(resolved.url),
  );
  if (!remoteClient) {
    await client.connect(transport);
  }

  const initial = await client.listTools();
  assertCatalog(resolved.route, initial?.tools);

  const allowed = new Set(ROUTES[resolved.route].tools);
  const server = new Server(
    { name: 'mastermindStudio', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const listed = await client.listTools();
    assertCatalog(resolved.route, listed?.tools);
    return listed;
  });
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const name = request?.params?.name;
    if (typeof name !== 'string' || !allowed.has(name)) {
      throw new Error('STUDIO_TOOL_REFUSED');
    }
    return await client.callTool({
      name,
      arguments: request?.params?.arguments ?? {},
    });
  });

  return { server, client, transport, ...resolved };
}

function parseArgs(argv) {
  let route = 'design';
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--route') {
      route = argv[++index] || '';
      continue;
    }
    throw new Error('STUDIO_ARGUMENT_REFUSED');
  }
  return { route };
}

export async function main(argv = process.argv.slice(2)) {
  const { route } = parseArgs(argv);
  const bridge = await createBridge({ route });
  const stdio = new StdioServerTransport();
  await bridge.server.connect(stdio);

  const close = async () => {
    try { await bridge.server.close(); } catch {}
    try { await bridge.client.close(); } catch {}
  };
  process.once('SIGTERM', () => { void close().finally(() => process.exit(0)); });
  process.once('SIGINT', () => { void close().finally(() => process.exit(0)); });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    process.stderr.write(
      `mastermindStudio local bridge refused: ${error?.message || 'internal_error'}\n`,
    );
    process.exitCode = 1;
  });
}
