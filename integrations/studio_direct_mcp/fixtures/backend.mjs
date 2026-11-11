#!/usr/bin/env node
// Test fixture: stdio MCP backend used by gateway.test.mjs and smoke.mjs.
//
// Implements only:
//   - echo:     returns its arguments verbatim (read-only, side-effect-free).
//   - delayed_effect: writes a unique marker to MARKER_PATH after delayMs,
//                     regardless of whether the caller is still waiting.
//   - fixture_paths: returns the marker file path and effect log path used.
//
// No real commands are executed. No credentials are read.
//
// Environment variables (all optional):
//   FIXTURE_DELAY_MS   default 200 (ms) before delayed_effect writes the marker.
//   FIXTURE_THROW      if "1", delayed_effect throws immediately (no marker).
//   FIXTURE_HANG_MS    if >0, delayed_effect resolves only after this many ms
//                      (useful for forcing a gateway-side timeout).
//   FIXTURE_NEVER      if "1", delayed_effect awaits the marker write first,
//                      then intentionally never resolves (truly hangs).
//   FIXTURE_MARKER_PATH  override marker file path (default
//                        $TMPDIR/private-studio-mcp-marker-<pid>.txt).
//   FIXTURE_EFFECT_LOG   override effect log path (default
//                        $TMPDIR/private-studio-mcp-effect-<pid>.jsonl).
//
// Stdout is exclusively JSON-RPC; logging goes to stderr so the gateway
// sees a clean stream.

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { appendFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';

const PID = process.pid;
const DEFAULT_DELAY_MS = Number.parseInt(process.env.FIXTURE_DELAY_MS || '200', 10);
const THROW = process.env.FIXTURE_THROW === '1';
const HANG_MS = Number.parseInt(process.env.FIXTURE_HANG_MS || '0', 10);
const NEVER = process.env.FIXTURE_NEVER === '1';
const READ_DELAY_MS = Number.parseInt(process.env.FIXTURE_READ_DELAY_MS || '0', 10);
const MARKER_PATH = process.env.FIXTURE_MARKER_PATH
  || `${tmpdir()}/private-studio-mcp-marker-${PID}.txt`;
const EFFECT_LOG = process.env.FIXTURE_EFFECT_LOG
  || `${tmpdir()}/private-studio-mcp-effect-${PID}.jsonl`;

const server = new McpServer(
  { name: 'studio-test-fixture', version: '0.0.0' },
  { capabilities: { tools: {}, resources: {} } },
);

// Track every effect call, including those that hang or time out.
async function recordEffect(entry) {
  try {
    await mkdir(dirname(EFFECT_LOG), { recursive: true });
    await appendFile(EFFECT_LOG, JSON.stringify({ ts: Date.now(), pid: PID, ...entry }) + '\n', 'utf8');
  } catch (err) {
    // Effect logging must never throw to the caller.
    process.stderr.write(`[fixture] effect log failed: ${err && err.message}\n`);
  }
}

if (process.env.FIXTURE_TYPED_GIT_COLLISION === '1') {
  server.registerTool(
    'studio_git_publish_status',
    {
      title: 'Fixture collision',
      description: 'Test-only backend name collision with the gateway-owned typed Git status tool.',
      inputSchema: {},
      annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    },
    async () => ({ content: [{ type: 'text', text: 'collision' }] }),
  );
}

server.registerTool(
  'echo',
  {
    title: 'Echo',
    description: 'Returns its argument object verbatim. Read-only, no side effects.',
    inputSchema: { value: z.any() },
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  },
  async ({ value }) => {
    return { content: [{ type: 'text', text: JSON.stringify({ echoed: value }) }] };
  },
);

server.registerTool(
  'read_file',
  {
    title: 'Read file fixture',
    description: 'Test-only timeout-safe read. It performs no filesystem read or write.',
    inputSchema: { path: z.string().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: requestedPath }) => {
    const id = randomUUID();
    await recordEffect({ tool: 'read_file', id, phase: 'start' });
    if (READ_DELAY_MS > 0) {
      await new Promise((resolve) => setTimeout(resolve, READ_DELAY_MS));
    }
    await recordEffect({ tool: 'read_file', id, phase: 'resolved' });
    return {
      content: [{ type: 'text', text: JSON.stringify({ requestedPath: requestedPath ?? null, pid: PID }) }],
    };
  },
);

const PRIORITY_RESOURCE_URI = 'ui://studio-test/priority';
server.registerResource(
  'priority',
  PRIORITY_RESOURCE_URI,
  { mimeType: 'text/plain' },
  async () => {
    const id = randomUUID();
    await recordEffect({ tool: 'priority_resource', id, phase: 'start' });
    await recordEffect({ tool: 'priority_resource', id, phase: 'resolved' });
    return {
      contents: [{ uri: PRIORITY_RESOURCE_URI, mimeType: 'text/plain', text: 'priority-resource-ok' }],
    };
  },
);

server.registerTool(
  'request_meta',
  {
    title: 'Request metadata fixture',
    description: 'Returns request metadata received by the fixture backend.',
    inputSchema: {},
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async (_args, extra) => ({
    content: [{ type: 'text', text: JSON.stringify(extra?._meta ?? {}) }],
  }),
);

server.registerTool(
  'delayed_effect',
  {
    title: 'Delayed effect',
    description:
      'Sleeps for delayMs, then writes a unique marker file. ' +
      'If FIXTURE_HANG_MS>0 or FIXTURE_NEVER=1, never resolves (used to force ' +
      'a caller-side timeout). FIXTURE_THROW=1 fails fast with no marker.',
    inputSchema: {
      marker: z.string().min(1).max(256),
      delayMs: z.number().int().min(0).max(60_000).optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
  },
  async ({ marker, delayMs }) => {
    const id = randomUUID();
    const effectiveDelay = Number.isFinite(delayMs) ? delayMs : DEFAULT_DELAY_MS;
    await recordEffect({
      tool: 'delayed_effect', id, marker, phase: 'start',
      effectiveDelay, throw: THROW, hangMs: HANG_MS, never: NEVER,
    });

    if (THROW) {
      await recordEffect({ tool: 'delayed_effect', id, phase: 'throw' });
      throw new Error('fixture: forced failure before marker write');
    }

    const doEffect = async () => {
      try {
        await mkdir(dirname(MARKER_PATH), { recursive: true });
        // Write-then-append so the file exists with the marker as soon as possible
        // even if the gateway is gone by the time we get here.
        await writeFile(MARKER_PATH, `${marker}\n${id}\n`, { flag: 'a' });
        await recordEffect({
          tool: 'delayed_effect', id, marker, phase: 'marker_written', markerPath: MARKER_PATH,
        });
      } catch (err) {
        await recordEffect({ tool: 'delayed_effect', id, phase: 'marker_error', error: String(err && err.message) });
      }
    };

    if (NEVER) {
      // Await the marker write first so callers can rely on its presence
      // even when the response is then intentionally never produced.
      await doEffect();
      await new Promise(() => {});
    }

    setTimeout(doEffect, HANG_MS > 0 ? HANG_MS : effectiveDelay);
    await new Promise((resolve) => setTimeout(resolve, HANG_MS > 0 ? HANG_MS : effectiveDelay));
    await recordEffect({ tool: 'delayed_effect', id, phase: 'resolved' });
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({ id, marker, markerPath: MARKER_PATH, phase: 'resolved' }),
      }],
    };
  },
);

// Optional: a tool that exposes where the fixture writes its files so tests
// can read them back without trusting environment variables.
server.registerTool(
  'fixture_paths',
  {
    title: 'Fixture paths',
    description: 'Returns the marker file path and effect log path used by this fixture.',
    inputSchema: {},
    annotations: { readOnlyHint: true },
  },
  async () => {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({ markerPath: MARKER_PATH, effectLog: EFFECT_LOG, pid: PID }),
      }],
    };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);

// Clean shutdown on parent SIGTERM/SIGINT (parent may forward when closing our stdio).
for (const sig of ['SIGTERM', 'SIGINT']) {
  process.on(sig, async () => {
    try { await server.close(); } catch { /* ignore */ }
    process.exit(0);
  });
}
server.registerTool('drop_after_effect', {
  inputSchema: {marker: z.string()},
  annotations: {readOnlyHint:false, destructiveHint:true, idempotentHint:false, openWorldHint:false},
}, async ({marker}) => {
  await writeFile(MARKER_PATH, marker+'\n', {flag:'a'});
  await recordEffect({tool:'drop_after_effect', marker, phase:'marker_written'});
  process.exit(0); // Intentional death of this isolated fixture child only.
});
