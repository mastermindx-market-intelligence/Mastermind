// Hermetic metadata fixture: catalog only, no host commands or external calls.
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const understated = {readOnlyHint: true, destructiveHint: false,
  idempotentHint: true, openWorldHint: false};
const names = ['start_process', 'interact_with_process', 'write_file', 'write_pdf',
  'edit_block', 'move_file', 'set_config_value', 'kill_process', 'force_terminate',
  'create_directory', 'give_feedback_to_desktop_commander', 'stop_search'];
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
tools.push({name: 'partial_unknown', description: 'Fixture incomplete safety labels.',
  inputSchema: {type: 'object', properties: {}, additionalProperties: false},
  annotations: {destructiveHint: false, idempotentHint: true, openWorldHint: false}});
// Cursor/handle operations cannot gain repeat-effect-free semantics from a label.
for (const name of ['start_search', 'get_more_search_results', 'read_process_output']) {
  tools.push({name, description: 'Fixture stateful read.',
    inputSchema: {type: 'object', properties: {}, additionalProperties: false},
    annotations: {...understated}});
}
const server = new Server({name: 'metadata-fixture', version: '0.0.0'},
  {capabilities: {tools: {}}});
// Reproduce the sparse 0.2.50 annotation shape reported by independent review.
// Schemas are intentionally inert fixture schemas, not production API snapshots.
const sparseAnnotations = {
  get_config: {readOnlyHint: true},
  set_config_value: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  read_file: {readOnlyHint: true, openWorldHint: true},
  read_multiple_files: {readOnlyHint: true},
  write_file: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  write_pdf: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  create_directory: {readOnlyHint: false, destructiveHint: false},
  list_directory: {readOnlyHint: true},
  move_file: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  start_search: {readOnlyHint: true},
  get_more_search_results: {readOnlyHint: true},
  stop_search: {readOnlyHint: false, destructiveHint: false},
  list_searches: {readOnlyHint: true},
  get_file_info: {readOnlyHint: true},
  edit_block: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  start_process: {readOnlyHint: false, destructiveHint: true, openWorldHint: true},
  read_process_output: {readOnlyHint: true},
  interact_with_process: {readOnlyHint: false, destructiveHint: true, openWorldHint: true},
  force_terminate: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  list_sessions: {readOnlyHint: true},
  list_processes: {readOnlyHint: true},
  kill_process: {readOnlyHint: false, destructiveHint: true, openWorldHint: false},
  get_usage_stats: {readOnlyHint: true},
  get_recent_tool_calls: {readOnlyHint: true},
  give_feedback_to_desktop_commander: {readOnlyHint: false, openWorldHint: true},
  get_prompts: {readOnlyHint: true},
};
const mode = process.env.METADATA_FIXTURE_MODE;
const selectedTools = mode === 'installed-sparse' || mode === 'explicit-risk'
  ? Object.entries(sparseAnnotations).map(([name, annotations]) => ({
      name, description: 'Inert sparse-catalog fixture.',
      inputSchema: {type: 'object', properties: {}, additionalProperties: false},
      annotations: mode === 'explicit-risk'
        ? {readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true}
        : {...annotations},
    }))
  : tools;
server.setRequestHandler(ListToolsRequestSchema, async () => ({tools: selectedTools}));
await server.connect(new StdioServerTransport());
