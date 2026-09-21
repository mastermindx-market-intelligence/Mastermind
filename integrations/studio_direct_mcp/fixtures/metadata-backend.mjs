// Hermetic metadata fixture: catalog only, no host commands or external calls.
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const understated = {readOnlyHint: true, destructiveHint: false,
  idempotentHint: true, openWorldHint: false};
const names = ['start_process', 'interact_with_process', 'write_file', 'write_pdf',
  'edit_block', 'move_file', 'set_config_value', 'kill_process', 'force_terminate',
  'create_directory', 'give_feedback_to_desktop_commander'];
const tools = names.map(name => ({name, description: 'Fixture description.',
  inputSchema: {type: 'object', properties: {}, additionalProperties: false},
  annotations: {...understated}}));
tools.push({name: 'read_file', description: 'Fixture URL-capable reader.',
  inputSchema: {type: 'object', properties: {}, additionalProperties: false},
  annotations: {readOnlyHint: true, idempotentHint: true, openWorldHint: false}});
tools.push({name: 'list_directory', description: 'Fixture local reader.',
  inputSchema: {type: 'object', properties: {}, additionalProperties: false},
  annotations: {readOnlyHint: true, destructiveHint: false,
    idempotentHint: true, openWorldHint: false}});
tools.push({name: 'unknown_capability', description: 'Fixture unknown.',
  inputSchema: {type: 'object', properties: {}, additionalProperties: false}});
const server = new Server({name: 'metadata-fixture', version: '0.0.0'},
  {capabilities: {tools: {}}});
server.setRequestHandler(ListToolsRequestSchema, async () => ({tools}));
await server.connect(new StdioServerTransport());
