// Disposable stdio fixture: no Fabric adapter, credentials or real work.
import { createHash } from 'node:crypto';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { ListToolsRequestSchema, CallToolRequestSchema, McpError, ErrorCode } from '@modelcontextprotocol/sdk/types.js';
import { createFabricFacade } from '../fabric-backend.mjs';
const names = ['fabric_capabilities', 'fabric_request', 'fabric_status', 'fabric_wait',
  'fabric_result', 'fabric_accept', 'fabric_controller_output'];
let effects = 0;
let resultCalls = 0;
const finished = value => {
  const stdout = Buffer.from(JSON.stringify(value), 'utf8');
  const envelope = { exit_code: 0, stdout_base64: stdout.toString('base64'),
    stdout_bytes: stdout.length, stdout_sha256: createHash('sha256').update(stdout).digest('hex') };
  return { content: [{ type: 'text', text:
    `Process started with PID 123 (shell: /bin/zsh)\nInitial output:\n${JSON.stringify(envelope)}\nMMX_FABRIC_EXIT=0\n` }] };
};
// Real incumbent facade, disposable engine. This checks its anti-replay state
// across the new HTTP request lifetime without starting a shell/provider.
const facade = createFabricFacade({ async callTool(request) {
  const command = request.arguments.command;
  if (command.includes("'status' 'fixture-timeout'")) return finished({
    schema: 'mastermind.fabric_task_status.v1', run_id: 'fixture-timeout',
    root_id: effects ? 'fixture-root' : null, state: effects ? 'ACTIVE_OR_WAITING' : 'NOT_FOUND',
    result_available: false, fixture_effects: effects, fixture_pid: process.pid });
  if (command.includes("'request' '--id' 'fixture-timeout'")) {
    effects++;
    // Keep this disposable effect pending until its stdio owner is closed.
    // The real gateway timeout or HTTP abort must occur before any completion.
    await new Promise(() => {});
  }
  throw new Error('Unexpected fixture engine call');
} });
const server = new Server({ name: 'disposable-fabric-fixture', version: '0.0.0' }, { capabilities: { tools: {} } });
server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools:
  [...names, ...(process.env.FIXTURE_UNRELATED === 'true' ? ['start_process'] : [])]
    .map(name => ({ name, inputSchema: { type: 'object' } })) }));
server.setRequestHandler(CallToolRequestSchema, async request => {
  const name = request.params.name;
  if (!names.includes(name)) throw new McpError(ErrorCode.InvalidParams, 'Unknown fixture tool');
  if (process.env.FIXTURE_FACADE_TIMEOUT === 'true') return facade.call(name, request.params.arguments);
  if (name === 'fabric_request') effects++;
  if (name === 'fabric_result') resultCalls++;
  const value = { fixture: true, name, effects, resultCalls, pid: process.pid, args: request.params.arguments,
    backendRequestId: request.params._meta?.mastermind_remote_call_id,
    ...(name === 'fabric_result' && process.env.FIXTURE_LARGE === 'true' ? { payload: 'retained-fixture-'.repeat(5000) } : {}) };
  return { content: [{ type: 'text', text: JSON.stringify(value) }] };
});
await server.connect(new StdioServerTransport());
