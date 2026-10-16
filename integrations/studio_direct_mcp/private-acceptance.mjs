import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { performance } from 'node:perf_hooks';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

// Real-engine acceptance for the dedicated, private loopback listener. No keys,
// grants, metadata impersonation, retries, or public DNS overrides are involved.
const url = new URL(process.argv[2] || 'http://127.0.0.1:45018/mcp');
assert.equal(url.protocol, 'http:');
assert.equal(url.hostname, '127.0.0.1');
assert.equal(url.pathname, '/mcp');
const client = new Client({ name: 'studio-private-acceptance', version: '1.0.0' });
const transport = new StreamableHTTPClientTransport(url);
const receipt = { kind: 'installed-loopback-real-engine', nativeChatGPT: false,
  at: new Date().toISOString(), endpoint: url.href, measurements: [] };
let initialized = false;
let fixtureDir = null;
const measure = async (name, fn) => {
  const start = performance.now();
  const result = await fn();
  assert.ok(!result?.isError, `${name} returned an MCP error`);
  receipt.measurements.push({ name, ms: Math.round((performance.now() - start) * 10) / 10 });
  return result;
};
try {
  for (const path of ['/.well-known/oauth-protected-resource',
    '/.well-known/oauth-protected-resource/mcp', '/.well-known/oauth-authorization-server']) {
    const response = await fetch(new URL(path, url), { signal: AbortSignal.timeout(5000) });
    assert.equal(response.status, 404, `No Auth discovery ${path}`);
  }
  await measure('initialize', () => client.connect(transport));
  initialized = true;
  const { tools } = await measure('tools/list', () => client.listTools());
  receipt.toolCount = tools.length;
  const resources = await measure('resources/list', () => client.listResources());
  receipt.resourceCount = resources.resources.length;
  for (const uri of new Set(tools.map(t => t._meta?.['openai/outputTemplate']).filter(Boolean))) {
    const result = await measure('resources/read', () => client.readResource({ uri }));
    assert.ok(result.contents.some(c => c.uri === uri && (c.text?.length > 0 || c.blob?.length > 0)),
      'advertised UI resource must be readable');
  }
  for (const required of ['studio_ping', 'read_file', 'start_process'])
    assert.ok(tools.some(t => t.name === required), `${required} exposed`);
  const ping = await measure('studio_ping', () => client.callTool({ name: 'studio_ping', arguments: {} }));
  receipt.ping = ping;
  fixtureDir = await mkdtemp('/private/tmp/studio-private-acceptance-');
  const fixturePath = join(fixtureDir, 'read-marker.txt');
  const fixtureMarker = `STUDIO_PRIVATE_READ_${Date.now()}`;
  await writeFile(fixturePath, `${fixtureMarker}\n`, { encoding: 'utf8', mode: 0o600 });
  for (let i = 0; i < 3; i++) {
    const read = await measure('read_file', () => client.callTool({ name: 'read_file', arguments: {
      path: fixturePath, offset: 0, length: 8 } }));
    assert.ok(read.content.some(c => c.type === 'text' && c.text.includes(fixtureMarker)),
      'bounded acceptance marker read');
  }
  const marker = `STUDIO_PRIVATE_ACCEPTANCE_${Date.now()}`;
  const command = await measure('start_process', () => client.callTool({ name: 'start_process', arguments: {
    command: `printf '%s\\n' '${marker}'; /usr/bin/true`, timeout_ms: 1000, verbose_timing: true } }));
  assert.ok(command.content.some(c => c.type === 'text' && c.text.includes(marker)), 'unique command output');
  receipt.marker = marker;
  receipt.status = 'PASS';
} catch (error) {
  receipt.status = 'FAIL';
  receipt.error = error.message;
  process.exitCode = 1;
} finally {
  if (initialized) {
    try { await transport.terminateSession(); receipt.sessionDeleted = true; }
    catch (error) { receipt.cleanupError = error.message; process.exitCode = 1; }
  }
  await client.close();
  if (fixtureDir) {
    try { await rm(fixtureDir, { recursive: true, force: true }); receipt.fixtureDeleted = true; }
    catch (error) { receipt.fixtureCleanupError = error.message; process.exitCode = 1; }
  }
  console.log(JSON.stringify(receipt, null, 2));
}
