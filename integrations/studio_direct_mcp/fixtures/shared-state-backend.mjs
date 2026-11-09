#!/usr/bin/env node
// Test fixture: shared-state MCP backend used by gateway-shared-backend.test.mjs.
//
// Tracks process handles in a shared in-memory Map (keyed by PID) so that
// multiple MCP sessions on the same backend child can read/interact with a
// process started by a sibling session.
//
// Implements:
//   - start_process:  registers a fake process, returns its PID
//   - read_process_output: reads from the shared process Map by PID
//   - interact_with_process: sends input to a shared process Map entry
//   - drop_after_effect: writes marker then exits (simulates process death)
//   - echo: read-only echo for basic connectivity checks
//
// No real commands are executed. No credentials are read.

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { randomUUID } from 'node:crypto';

const PID = process.pid;
const MARKER_PATH = `${tmpdir()}/private-studio-mcp-shared-marker-${PID}.txt`;

// Shared process Map: pid -> { cmd, startedAt, output: [] }
const processes = new Map();
let processCounter = 0;

const server = new McpServer(
  { name: 'shared-state-fixture', version: '0.0.0' },
  { capabilities: { tools: {} } },
);

server.registerTool(
  'start_process',
  {
    title: 'Start process',
    description: 'Registers a fake process and returns its PID. Shared across MCP sessions.',
    inputSchema: {
      cmd: z.string().optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  async ({ cmd = 'sleep 999' }) => {
    const id = ++processCounter;
    const pid = 10000 + id;
    processes.set(pid, { cmd, startedAt: Date.now(), output: [] });
    return {
      content: [{ type: 'text', text: JSON.stringify({ pid, cmd, registered: processes.has(pid) }) }],
    };
  },
);

server.registerTool(
  'read_process_output',
  {
    title: 'Read process output',
    description: 'Reads from the shared process Map by PID.',
    inputSchema: {
      pid: z.number().int(),
    },
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  },
  async ({ pid }) => {
    const proc = processes.get(pid);
    if (!proc) {
      return { content: [{ type: 'text', text: `No session found for PID ${pid}` }], isError: true };
    }
    return {
      content: [{ type: 'text', text: JSON.stringify({ pid, cmd: proc.cmd, output: proc.output }) }],
    };
  },
);

server.registerTool(
  'interact_with_process',
  {
    title: 'Interact with process',
    description: 'Sends input to a shared process Map entry by PID.',
    inputSchema: {
      pid: z.number().int(),
      input: z.string().optional(),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  async ({ pid, input = '' }) => {
    const proc = processes.get(pid);
    if (!proc) {
      return { content: [{ type: 'text', text: `Failed to send input to process ${pid}. The process may have exited or doesn't accept input.` }], isError: true };
    }
    proc.output.push(`[${input}]`);
    return {
      content: [{ type: 'text', text: JSON.stringify({ pid, sent: input.length }) }],
    };
  },
);

server.registerTool(
  'drop_after_effect',
  {
    title: 'Drop after effect',
    description: 'Writes marker then exits. Simulates process death.',
    inputSchema: {
      marker: z.string(),
    },
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: false },
  },
  async ({ marker }) => {
    await writeFile(MARKER_PATH, `${marker}\n${randomUUID()}\n`, { flag: 'a' });
    // Exit immediately — simulates the backend child dying mid-session.
    process.exit(0);
  },
);

server.registerTool(
  'echo',
  {
    title: 'Echo',
    description: 'Returns its argument verbatim. Read-only.',
    inputSchema: { value: z.any() },
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  },
  async ({ value }) => {
    return { content: [{ type: 'text', text: JSON.stringify({ echoed: value }) }] };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);

// Clean shutdown on parent SIGTERM/SIGINT.
for (const sig of ['SIGTERM', 'SIGINT']) {
  process.on(sig, async () => {
    try { await server.close(); } catch { /* ignore */ }
    process.exit(0);
  });
}
