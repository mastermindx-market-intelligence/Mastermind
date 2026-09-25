import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { startGateway } from './gateway.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..');
const FIXTURE_PATH = resolve(HERE, 'fixtures/backend.mjs');

function auth() {
  return {
    middleware(req, _res, next) {
      req.auth = { principal: 'paper-test', clientId: 'paper-test', scopes: ['studio.control'] };
      next();
    },
    mount() {},
  };
}

async function connect(client, url) {
  const transport = new StreamableHTTPClientTransport(new URL(url), {
    requestInit: { headers: { Authorization: 'Bearer fixture' } },
  });
  await client.connect(transport);
  return transport;
}

test('gateway advertises and dispatches guarded Paper design tools locally', async (t) => {
  const root = mkdtempSync(resolve(tmpdir(), 'studio-paper-gateway-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));

  const bridgePath = resolve(root, 'fake-paper-bridge.mjs');
  const snapshotA = 'a'.repeat(64);
  const snapshotB = 'b'.repeat(64);
  const snapshotC = 'c'.repeat(64);
  const fakeBridge = [
    "const action = process.argv[2];",
    "const argv = process.argv.slice(3);",
    "const arg = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : undefined; };",
    `if (action === 'status') console.log(JSON.stringify({state:'CONNECTED', document:{fileId:'FILE', snapshot_sha256:'${snapshotA}'}}));`,
    `else if (action === 'catalog') console.log(JSON.stringify({server:{name:'paper-desktop',version:'0.5.11'}, schema_sha256:'${snapshotB}', tools:[]}));`,
    "else if (action === 'read') console.log(JSON.stringify({state:'OBSERVED', tool:arg('--tool'), result:{content:[{type:'text',text:'read-ok'}]}}));",
    "else if (action === 'edit') console.log(JSON.stringify({state:'APPLIED_RESPONSE_OBSERVED', operation_id:arg('--operation-id'), result:{content:[{type:'text',text:'edit-ok'}]}}));",
    "else { process.exitCode = 2; console.log(JSON.stringify({state:'REFUSED', retry_allowed:false})); }",
    "",
  ].join('\n');
  writeFileSync(bridgePath, fakeBridge, { encoding: 'utf8', mode: 0o600 });
  const bridgeSha256 = createHash('sha256').update(fakeBridge).digest('hex');

  const gw = await startGateway({
    host: '127.0.0.1',
    port: 0,
    command: process.execPath,
    args: [FIXTURE_PATH],
    cwd: REPO_ROOT,
    childEnv: { ...process.env },
    stateDir: root,
    maxSessions: 4,
    requestTimeoutMs: 10_000,
    testMode: true,
    paperDesign: {
      enabled: true,
      pythonPath: process.execPath,
      bridgePath,
      bridgeSha256,
      appPath: '/Applications/Paper.app',
      commandTimeoutMs: 5000,
    },
  }, auth());
  t.after(async () => { await gw.close(); });

  const client = new Client({ name: 'paper-gateway-test', version: '1.0.0' }, { capabilities: {} });
  t.after(async () => { await client.close(); });
  await connect(client, gw.url);

  const listed = await client.listTools();
  const byName = new Map(listed.tools.map((tool) => [tool.name, tool]));
  for (const name of ['paper_inspect', 'paper_catalog', 'paper_read', 'paper_prepare', 'paper_edit']) {
    assert.ok(byName.has(name), `missing ${name}`);
  }
  assert.equal(byName.get('paper_inspect').annotations.readOnlyHint, true);
  assert.equal(byName.get('paper_read').annotations.readOnlyHint, true);
  assert.equal(byName.get('paper_prepare').annotations.readOnlyHint, false);
  assert.equal(byName.get('paper_prepare').annotations.destructiveHint, false);
  assert.equal(byName.get('paper_edit').annotations.readOnlyHint, false);
  assert.equal(byName.get('paper_edit').annotations.idempotentHint, false);

  const inspect = await client.callTool({ name: 'paper_inspect', arguments: {} });
  const inspectPayload = JSON.parse(inspect.content.find((item) => item.type === 'text').text);
  assert.equal(inspectPayload.state, 'CONNECTED');
  assert.equal(inspectPayload.document.fileId, 'FILE');

  const read = await client.callTool({
    name: 'paper_read',
    arguments: { tool: 'get_jsx', arguments: { fileId: 'FILE', nodeId: '1-0' } },
  });
  const readPayload = JSON.parse(read.content.find((item) => item.type === 'text').text);
  assert.equal(readPayload.state, 'OBSERVED');
  assert.equal(readPayload.tool, 'get_jsx');

  const edit = await client.callTool({
    name: 'paper_edit',
    arguments: {
      tool: 'write_html',
      arguments: { fileId: 'FILE', html: '<div />' },
      expected_snapshot: snapshotC,
      operation_id: 'paper-web-canary-1',
    },
  });
  const editPayload = JSON.parse(edit.content.find((item) => item.type === 'text').text);
  assert.equal(editPayload.state, 'APPLIED_RESPONSE_OBSERVED');
  assert.equal(editPayload.operation_id, 'paper-web-canary-1');
});
