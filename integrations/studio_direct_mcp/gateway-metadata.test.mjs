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
    'force_terminate', 'create_directory', 'give_feedback_to_desktop_commander']) {
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
