#!/usr/bin/env node
/**
 * Local Claude Desktop stdio projection for the guarded Studio/Paper MCP.
 *
 * This process owns no Paper, fleet, placement, authentication, or tool
 * authority. It mirrors one already-running tailnet Studio route into stdio
 * for Claude Desktop's local-MCP mechanism and refuses catalog drift.
 */
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
    path: '/studio-fabric',
    tools: Object.freeze([
      'paper_catalog',
      'paper_inspect',
      'paper_read',
      'studio_fleet_status',
      'studio_ping',
    ]),
  }),
  design: Object.freeze({
    path: '/studio-design',
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

export function routeUrl(originValue, routeValue) {
  const route = String(routeValue || '').trim().toLowerCase();
  const spec = ROUTES[route];
  if (!spec) throw new Error('STUDIO_ROUTE_REFUSED');

  let origin;
  try {
    origin = new URL(String(originValue || ''));
  } catch {
    throw new Error('STUDIO_ORIGIN_REFUSED');
  }
  if (
    origin.protocol !== 'https:' ||
    !origin.hostname.endsWith('.ts.net') ||
    origin.hostname === '.ts.net' ||
    origin.username ||
    origin.password ||
    origin.port ||
    origin.search ||
    origin.hash ||
    (origin.pathname !== '' && origin.pathname !== '/')
  ) {
    throw new Error('STUDIO_ORIGIN_REFUSED');
  }
  return `https://${origin.hostname}${spec.path}`;
}

export function assertCatalog(routeValue, toolsValue) {
  const route = String(routeValue || '').trim().toLowerCase();
  const spec = ROUTES[route];
  if (!spec) throw new Error('STUDIO_ROUTE_REFUSED');
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
  origin,
  route,
  remoteClient = null,
  remoteTransport = null,
} = {}) {
  const normalizedRoute = String(route || '').trim().toLowerCase();
  const url = routeUrl(origin, normalizedRoute);
  const client = remoteClient ?? new Client(
    { name: 'mastermind-claude-desktop-studio-bridge', version: '1.0.0' },
    { capabilities: {} },
  );
  const transport = remoteTransport ?? new StreamableHTTPClientTransport(new URL(url));
  if (!remoteClient) {
    await client.connect(transport);
  }

  const initial = await client.listTools();
  assertCatalog(normalizedRoute, initial?.tools);

  const allowed = new Set(ROUTES[normalizedRoute].tools);
  const server = new Server(
    { name: 'mastermindStudio', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const listed = await client.listTools();
    assertCatalog(normalizedRoute, listed?.tools);
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

  return { server, client, transport, url, route: normalizedRoute };
}

function parseArgs(argv) {
  let route = 'design';
  let origin = process.env.MASTERMIND_STUDIO_MCP_ORIGIN || '';
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--route') {
      route = argv[++index] || '';
      continue;
    }
    if (token === '--origin') {
      origin = argv[++index] || '';
      continue;
    }
    throw new Error('STUDIO_ARGUMENT_REFUSED');
  }
  return { route, origin };
}

export async function main(argv = process.argv.slice(2)) {
  const { route, origin } = parseArgs(argv);
  const bridge = await createBridge({ origin, route });
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
