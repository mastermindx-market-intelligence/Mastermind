import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const url = new URL(process.argv[2]);
assert.equal(url.protocol, 'http:');
assert.equal(url.hostname, '127.0.0.1');
assert.equal(url.pathname, '/mcp');
const preflight = process.argv.includes('--preflight');
const client = new Client({ name: 'studio-preview-verification', version: '1' });
const transport = new StreamableHTTPClientTransport(url);
const receipt = { at: new Date().toISOString(), endpoint: url.href, nativeChatGPT: false,
  scope: preflight ? 'private restart process preflight' : 'installed UI-origin file read' };
try {
  await client.connect(transport);
  if (preflight) {
    const result = await client.callTool({ name: 'list_sessions', arguments: {} });
    assert.ok(!result.isError);
    receipt.noActiveProcesses = result.content.some(c => c.type === 'text' && c.text === 'No active sessions');
    assert.equal(receipt.noActiveProcesses, true, 'active process handles must be preserved; do not restart');
  } else {
    await client.listTools();
    const start = performance.now();
    const result = await client.callTool({ name: 'read_file', arguments: {
      path: '/System/Library/CoreServices/SystemVersion.plist', offset: 0, length: 8, origin: 'ui' } });
    receipt.durationMs = Math.round((performance.now() - start) * 10) / 10;
    assert.ok(!result.isError);
    assert.equal(result.structuredContent?.filePath, '/System/Library/CoreServices/SystemVersion.plist');
    assert.ok(result.content.some(c => c.type === 'text' && c.text.includes('<plist')),
      'UI must receive actual file contents in the MCP content array');
    receipt.structuredContentReturned = true;
    // Measures file handling plus the optional metadata budget after startup.
    assert.ok(receipt.durationMs < 3000, `UI read took ${receipt.durationMs} ms`);
  }
  receipt.status = 'PASS';
} catch (error) {
  receipt.status = 'FAIL'; receipt.error = error.message; process.exitCode = 1;
} finally {
  try { await transport.terminateSession(); } catch {}
  await client.close();
  console.log(JSON.stringify(receipt, null, 2));
}
