import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync, chmodSync } from 'node:fs';
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
  return { middleware(req, _res, next) { req.auth = { principal: 'mosyle-test', clientId: 'mosyle-test', scopes: ['studio.control'] }; next(); }, mount() {} };
}

async function connect(client, url) {
  const transport = new StreamableHTTPClientTransport(new URL(url), { requestInit: { headers: { Authorization: 'Bearer fixture' } } });
  await client.connect(transport);
  return transport;
}

test('gateway advertises only read-only Mosyle status tools when host credential is configured', async (t) => {
  const root = mkdtempSync(resolve(tmpdir(), 'studio-mosyle-gateway-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const credentialPath = resolve(root, 'mosyle.json');
  writeFileSync(credentialPath, JSON.stringify({ accessToken: 'fixture', email: 'fixture@example.com', password: 'fixture' }));
  chmodSync(credentialPath, 0o600);
  const gw = await startGateway({
    host: '127.0.0.1', port: 0, command: process.execPath, args: [FIXTURE_PATH], cwd: REPO_ROOT,
    childEnv: { ...process.env }, stateDir: root, maxSessions: 4, requestTimeoutMs: 10_000, testMode: true,
    mosyle: { enabled: true, credentialPath, timeoutMs: 5000 },
  }, auth());
  t.after(async () => { await gw.close(); });
  const client = new Client({ name: 'mosyle-gateway-test', version: '1.0.0' }, { capabilities: {} });
  t.after(async () => { await client.close(); });
  await connect(client, gw.url);
  const listed = await client.listTools();
  const byName = new Map(listed.tools.map((tool) => [tool.name, tool]));
  for (const name of ['mosyle_fleet_status', 'mosyle_device_status']) {
    assert.ok(byName.has(name), `missing ${name}`);
    assert.equal(byName.get(name).annotations.readOnlyHint, true);
    assert.equal(byName.get(name).annotations.destructiveHint, false);
    assert.equal(byName.get(name).annotations.idempotentHint, true);
  }
  assert.equal([...byName].some(([name]) => /^mosyle_.*(wipe|lock|erase|lost|command|install)/i.test(name)), false);
});
