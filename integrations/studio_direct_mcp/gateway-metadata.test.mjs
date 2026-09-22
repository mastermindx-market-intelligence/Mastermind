// Real MCP catalog path with a credential-free, no-execution backend.
import {before, after, test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StreamableHTTPClientTransport} from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import {startGateway} from './gateway.mjs';

let gateway, client, stateDir, tools;
before(async () => {
  const here = dirname(fileURLToPath(import.meta.url));
  stateDir = await mkdtemp(join(tmpdir(), 'studio-metadata-test-'));
  const auth = {mount() {}, middleware(req, _res, next) {
    if (req.headers.authorization !== 'Bearer fixture-only') {
      const err = new Error('unauthorized'); err.statusCode = 401; return next(err);
    }
    req.auth = {principal: 'metadata-fixture', clientId: 'metadata-test', scopes: ['studio.control']};
    next();
  }};
  gateway = await startGateway({host: '127.0.0.1', port: 0, testMode: true,
    command: process.execPath, args: [join(here, 'fixtures/metadata-backend.mjs')],
    cwd: here, stateDir, requestTimeoutMs: 10000}, auth);
  client = new Client({name: 'metadata-test', version: '0.0.0'}, {capabilities: {}});
  await client.connect(new StreamableHTTPClientTransport(new URL(gateway.url), {
    requestInit: {headers: {authorization: 'Bearer fixture-only'}},
  }));
  tools = new Map((await client.listTools()).tools.map(tool => [tool.name, tool]));
});
after(async () => {
  try { await client?.close(); } finally {
    try { await gateway?.close(); } finally {
      if (stateDir) await rm(stateDir, {recursive: true, force: true});
    }
  }
});

test('every exposed tool declares all four effect hints as booleans', () => {
  for (const [name, tool] of tools) for (const key of
    ['readOnlyHint', 'destructiveHint', 'idempotentHint', 'openWorldHint']) {
    assert.equal(typeof tool.annotations[key], 'boolean', `${name}.${key}`);
  }
});
test('known mutations cannot inherit an understated read-only claim', () => {
  for (const name of ['start_process', 'interact_with_process', 'write_file',
    'write_pdf', 'edit_block', 'move_file', 'set_config_value', 'kill_process',
    'force_terminate', 'create_directory', 'give_feedback_to_desktop_commander', 'stop_search']) {
    assert.equal(tools.get(name).annotations.readOnlyHint, false, name);
  }
});
test('overwrite, configuration and termination risks remain explicit', () => {
  for (const name of ['start_process', 'interact_with_process', 'write_file',
    'write_pdf', 'edit_block', 'move_file', 'set_config_value', 'kill_process', 'force_terminate']) {
    assert.equal(tools.get(name).annotations.destructiveHint, true, name);
  }
});
test('arbitrary process input cannot be advertised as closed-world or idempotent', () => {
  for (const name of ['start_process', 'interact_with_process']) {
    assert.equal(tools.get(name).annotations.openWorldHint, true, name);
    assert.equal(tools.get(name).annotations.idempotentHint, false, name);
  }
});
test('URL reads and external feedback disclose open-world access', () => {
  for (const name of ['read_file', 'give_feedback_to_desktop_commander']) {
    assert.equal(tools.get(name).annotations.openWorldHint, true, name);
  }
});
test('accurate bounded local reader annotations remain unchanged', () => {
  assert.deepEqual(tools.get('list_directory').annotations,
    {readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false});
});
test('unknown capabilities retain conservative defaults', () => {
  const a = tools.get('unknown_capability').annotations;
  assert.equal(a.readOnlyHint, false); assert.equal(a.destructiveHint, true);
  assert.equal(a.idempotentHint, false); assert.equal(a.openWorldHint, true);
});
test('descriptions disclose command, access-policy and external-data effects', () => {
  assert.match(tools.get('start_process').description, /filesystem|files/i);
  assert.match(tools.get('start_process').description, /network/i);
  assert.match(tools.get('start_process').description, /permissions/i);
  assert.match(tools.get('set_config_value').description, /access|security/i);
  assert.match(tools.get('give_feedback_to_desktop_commander').description, /usage|statistics/i);
  assert.match(tools.get('give_feedback_to_desktop_commander').description, /identifier/i);
});
test('server instructions remain descriptive rather than policy-prescriptive', () => {
  const instructions = client.getInstructions();
  assert.equal(typeof instructions, 'string');
  assert.match(instructions, /direct terminal effects/i);
  assert.match(instructions, /terminal observation/i);
  assert.doesNotMatch(instructions, /\b(?:always|never|must|mandatory|only correct|prefer|choose)\b/i);
});

test('generic terminal tools declare a bounded direct-terminal purpose', () => {
  for (const name of ['start_process', 'interact_with_process']) {
    const description = tools.get(name).description;
    assert.match(description, /not a work-submission or agent-handoff interface/i, name);
    assert.match(description, /nested agent instructions|worker handoffs/i, name);
    assert.match(description, /outside (?:its|their) declared (?:purpose|scope)/i, name);
    assert.doesNotMatch(description, /\b(?:always|never|must|mandatory|only correct|prefer)\b/i, name);
  }
});

test('catalog hardening preserves caller schemas and the existing page reader', () => {
  assert.deepEqual(tools.get('start_process').inputSchema,
    {type: 'object', properties: {}, additionalProperties: false});
  assert.equal(tools.has('studio_output_page'), true);
  assert.equal(tools.get('studio_output_page').annotations.readOnlyHint, true);
});

test('missing read-only evidence preserves the prior destructive default', () => {
  const a = tools.get('partial_unknown').annotations;
  assert.equal(a.readOnlyHint, false);
  assert.equal(a.destructiveHint, true);
});


async function sparseCatalog(t, mode = 'installed-sparse') {
  const here = dirname(fileURLToPath(import.meta.url));
  const dir = await mkdtemp(join(tmpdir(), 'studio-sparse-metadata-'));
  let gw, reader;
  t.after(async () => {
    try { await reader?.close(); } finally {
      try { await gw?.close(); } finally { await rm(dir, {recursive: true, force: true}); }
    }
  });
  const auth = {mount() {}, middleware(req, _res, next) {
    if (req.headers.authorization !== 'Bearer fixture-only') {
      const error = new Error('unauthorized'); error.statusCode = 401; return next(error);
    }
    req.auth = {principal: 'sparse-fixture', clientId: 'sparse-test', scopes: ['studio.control']};
    next();
  }};
  gw = await startGateway({host: '127.0.0.1', port: 0, testMode: true,
    command: process.execPath, args: [join(here, 'fixtures/metadata-backend.mjs')],
    childEnv: {METADATA_FIXTURE_MODE: mode}, cwd: here, stateDir: dir,
    requestTimeoutMs: 10000}, auth);
  reader = new Client({name: 'sparse-metadata-test', version: '0.0.0'}, {capabilities: {}});
  await reader.connect(new StreamableHTTPClientTransport(new URL(gw.url), {
    requestInit: {headers: {authorization: 'Bearer fixture-only'}},
  }));
  return new Map((await reader.listTools()).tools.map(tool => [tool.name, tool]));
}

test('sparse installed catalog resolves all 26 backend tools and both gateway tools', async t => {
  // Independent expected values: read-only, destructive, repeat-effect-free, open-world.
  // Creating/consuming process or search handles is not a repeat-effect-free lookup.
  const expected = {
    get_config: [true, false, true, false],
    set_config_value: [false, true, true, false],
    read_file: [true, false, true, true],
    read_multiple_files: [true, false, true, false],
    write_file: [false, true, false, false],
    write_pdf: [false, true, false, false],
    create_directory: [false, false, true, false],
    list_directory: [true, false, true, false],
    move_file: [false, true, false, false],
    start_search: [true, false, false, false],
    get_more_search_results: [true, false, false, false],
    stop_search: [false, false, true, false],
    list_searches: [true, false, true, false],
    get_file_info: [true, false, true, false],
    edit_block: [false, true, false, false],
    start_process: [false, true, false, true],
    read_process_output: [true, false, false, false],
    interact_with_process: [false, true, false, true],
    force_terminate: [false, true, false, false],
    list_sessions: [true, false, true, false],
    list_processes: [true, false, true, false],
    kill_process: [false, true, false, false],
    get_usage_stats: [true, false, true, false],
    get_recent_tool_calls: [true, false, true, false],
    give_feedback_to_desktop_commander: [false, true, false, true],
    get_prompts: [true, false, true, false],
    studio_ping: [true, false, true, false],
    studio_output_page: [true, false, true, false],
  };
  const catalog = await sparseCatalog(t);
  assert.deepEqual([...catalog.keys()].sort(), Object.keys(expected).sort());
  for (const [name, values] of Object.entries(expected)) await t.test(name, () => {
    const a = catalog.get(name).annotations;
    assert.deepEqual([a.readOnlyHint, a.destructiveHint, a.idempotentHint, a.openWorldHint], values);
  });
});

test('known local profiles do not suppress explicitly higher upstream risk', async t => {
  const catalog = await sparseCatalog(t, 'explicit-risk');
  for (const [name, tool] of catalog) {
    if (name.startsWith('studio_')) continue;
    const a = tool.annotations;
    assert.deepEqual([a.readOnlyHint, a.destructiveHint, a.idempotentHint, a.openWorldHint],
      [false, true, false, true], name);
  }
});


test('stateful reads cannot inherit an understated repeat-effect-free claim', () => {
  for (const name of ['start_search', 'get_more_search_results', 'read_process_output']) {
    assert.equal(tools.get(name).annotations.idempotentHint, false, name);
  }
});
