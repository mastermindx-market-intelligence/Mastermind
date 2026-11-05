// Focused adverse-control-flow proof for the private acceptance harness.
//
// The harness is executed as the real candidate body in a child Node process; only its
// boundary dependencies are substituted — the MCP SDK client and transport, the
// `node:fs/promises` module, the global `fetch` and the reported platform. No live MCP
// session, no network call, no real fixture directory and no installed service is involved.
//
// Set PA_CANDIDATE to run the same expectations against another copy of the harness,
// for example the pre-repair source, without editing a single expectation. The marker-root
// expectations are written against a Linux boundary; PA_PLATFORM pins the platform the
// candidate observes and defaults to `linux`.

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { after, before, describe, it } from 'node:test';

const candidatePath = process.env.PA_CANDIDATE
  ? pathToFileURL(process.env.PA_CANDIDATE).href
  : new URL('./private-acceptance.mjs', import.meta.url).href;

const FAKE_SETUP = `import { register } from 'node:module';
import { writeFileSync } from 'node:fs';
register('./loader.mjs', import.meta.url);
globalThis.__paScenario = process.env.PA_SCENARIO || 'happy';
globalThis.__paFiles = new Map();
globalThis.__paCalls = { mkdtemp: 0, rm: 0, writeFile: 0, close: 0, terminateSession: 0,
  mkdtempPrefixes: [], fixtureDirs: [], writeFilePaths: [], writeFileModes: [], reads: [], rmTargets: [] };
globalThis.fetch = async () => ({
  status: 404, ok: false, headers: new Headers(), text: async () => '', json: async () => ({})
});
if (process.env.PA_PLATFORM)
  Object.defineProperty(process, 'platform', { value: process.env.PA_PLATFORM, configurable: true, writable: true });
const callLog = process.env.PA_CALL_LOG;
if (callLog)
  process.on('exit', () => { try { writeFileSync(callLog, JSON.stringify(globalThis.__paCalls)); } catch {} });
`;

const FAKE_LOADER = `export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'node:fs/promises')
    return { url: new URL('./fake-fs.mjs', import.meta.url).href, shortCircuit: true };
  if (specifier === '@modelcontextprotocol/sdk/client/index.js')
    return { url: new URL('./fake-client.mjs', import.meta.url).href, shortCircuit: true };
  if (specifier === '@modelcontextprotocol/sdk/client/streamableHttp.js')
    return { url: new URL('./fake-transport.mjs', import.meta.url).href, shortCircuit: true };
  return nextResolve(specifier, context);
}
`;

const FAKE_FS = `export async function mkdtemp(prefix) {
  globalThis.__paCalls.mkdtemp += 1;
  globalThis.__paCalls.mkdtempPrefixes.push(prefix);
  const dir = prefix + 'synthetic';
  globalThis.__paCalls.fixtureDirs.push(dir);
  return dir;
}
export async function writeFile(path, data, options) {
  globalThis.__paCalls.writeFile += 1;
  globalThis.__paCalls.writeFilePaths.push(path);
  globalThis.__paCalls.writeFileModes.push(options ? options.mode : null);
  globalThis.__paFiles.set(path, { data, options });
}
export async function rm(target, options) {
  globalThis.__paCalls.rm += 1;
  globalThis.__paCalls.rmTargets.push(target);
  if (globalThis.__paScenario === 'fixture-cleanup-throws'
    || globalThis.__paScenario === 'read-error-and-cleanup-throws')
    throw new Error('synthetic fixture removal failure');
}
export default { mkdtemp, writeFile, rm };
`;

const FAKE_CLIENT = `export class Client {
  constructor(info) { this.info = info; }
  async connect(transport) { this.transport = transport; return {}; }
  async listTools() {
    return { tools: [
      { name: 'studio_ping' },
      { name: 'read_file' },
      { name: 'start_process' },
      { name: 'render_panel', _meta: { 'openai/outputTemplate': 'ui://studio/panel' } }
    ] };
  }
  async listResources() { return { resources: [{ uri: 'ui://studio/panel' }] }; }
  async readResource({ uri }) { return { contents: [{ uri, text: 'synthetic panel body' }] }; }
  async callTool({ name, arguments: args = {} }) {
    if (name === 'studio_ping') return { content: [{ type: 'text', text: 'pong' }] };
    if (name === 'read_file') {
      globalThis.__paCalls.reads.push(args.path);
      if (globalThis.__paScenario === 'read-mcp-error'
        || globalThis.__paScenario === 'read-error-and-cleanup-throws')
        return { isError: true, content: [{ type: 'text', text: 'synthetic MCP read failure' }] };
      const entry = globalThis.__paFiles.get(args.path);
      const lines = String(entry?.data ?? '').split('\\n');
      const offset = Number(args.offset ?? 0);
      const length = Number(args.length ?? lines.length);
      return { content: [{ type: 'text', text: lines.slice(offset, offset + length).join('\\n') }] };
    }
    if (name === 'start_process') {
      const marker = /STUDIO_PRIVATE_ACCEPTANCE_\\d+/.exec(String(args.command ?? ''));
      return { content: [{ type: 'text', text: marker ? marker[0] : 'synthetic' }] };
    }
    return { content: [] };
  }
  async close() {
    globalThis.__paCalls.close += 1;
    if (globalThis.__paScenario === 'client-close-throws')
      throw new Error('synthetic client close failure');
  }
}
export default { Client };
`;

const FAKE_TRANSPORT = `export class StreamableHTTPClientTransport {
  constructor(url) { this.url = url; }
  async terminateSession() {
    globalThis.__paCalls.terminateSession += 1;
    if (globalThis.__paScenario === 'terminate-session-throws')
      throw new Error('synthetic terminateSession failure');
  }
}
export default { StreamableHTTPClientTransport };
`;

let harnessDir = null;

before(async () => {
  harnessDir = await mkdtemp(join(tmpdir(), 'studio-private-acceptance-proof-'));
  await Promise.all([
    writeFile(join(harnessDir, 'setup.mjs'), FAKE_SETUP, 'utf8'),
    writeFile(join(harnessDir, 'loader.mjs'), FAKE_LOADER, 'utf8'),
    writeFile(join(harnessDir, 'fake-fs.mjs'), FAKE_FS, 'utf8'),
    writeFile(join(harnessDir, 'fake-client.mjs'), FAKE_CLIENT, 'utf8'),
    writeFile(join(harnessDir, 'fake-transport.mjs'), FAKE_TRANSPORT, 'utf8')
  ]);
});

after(async () => {
  if (harnessDir) await rm(harnessDir, { recursive: true, force: true });
});

function parseReceipt(stdout) {
  const trimmed = stdout.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf('{');
    const end = trimmed.lastIndexOf('}');
    if (start < 0 || end <= start) return null;
    try {
      return JSON.parse(trimmed.slice(start, end + 1));
    } catch {
      return null;
    }
  }
}

let callLogSeq = 0;

function runScenario(scenario, platform = 'linux') {
  const callLog = join(harnessDir, `calls-${process.pid}-${callLogSeq++}.json`);
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [
      '--import', join(harnessDir, 'setup.mjs'),
      fileURLToPath(candidatePath),
      'http://127.0.0.1:45018/mcp'
    ], { env: { ...process.env, PA_SCENARIO: scenario, PA_PLATFORM: platform, PA_CALL_LOG: callLog },
      stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('close', (code) => {
      let calls = null;
      try { calls = JSON.parse(readFileSync(callLog, 'utf8')); } catch { calls = null; }
      resolve({ code, stdout, stderr, receipt: parseReceipt(stdout), calls });
    });
  });
}

describe('private acceptance finalization', () => {
  it('reports PASS and cleans up on the happy path', async () => {
    const result = await runScenario('happy');
    assert.equal(result.code, 0);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'PASS');
    assert.equal(result.receipt.sessionDeleted, true);
    assert.equal(result.receipt.fixtureDeleted, true);
    assert.equal(result.receipt.error, undefined);
  });

  it('reports FAIL and still removes the fixture when the read tool returns an MCP error', async () => {
    const result = await runScenario('read-mcp-error');
    assert.equal(result.code, 1);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'FAIL');
    assert.match(result.receipt.error, /returned an MCP error/);
    assert.equal(result.receipt.fixtureDeleted, true);
  });

  it('reports FAIL when fixture removal fails instead of leaving PASS', async () => {
    const result = await runScenario('fixture-cleanup-throws');
    assert.equal(result.code, 1);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'FAIL');
    assert.match(result.receipt.fixtureCleanupError, /synthetic fixture removal failure/);
    assert.equal(result.receipt.fixtureDeleted, undefined);
    assert.equal(result.receipt.error, undefined, 'the acceptance itself did not fail');
  });

  it('emits a receipt and still removes the fixture when client close fails', async () => {
    const result = await runScenario('client-close-throws');
    assert.equal(result.code, 1);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'FAIL');
    assert.match(result.receipt.clientCloseError, /synthetic client close failure/);
    assert.equal(result.receipt.sessionDeleted, true);
    assert.equal(result.receipt.fixtureDeleted, true, 'fixture cleanup is attempted independently');
  });

  it('reports FAIL when the session cannot be terminated instead of leaving PASS', async () => {
    const result = await runScenario('terminate-session-throws');
    assert.equal(result.code, 1);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'FAIL');
    assert.match(result.receipt.cleanupError, /synthetic terminateSession failure/);
    assert.equal(result.receipt.fixtureDeleted, true);
  });

  it('keeps the original acceptance failure when fixture removal also fails', async () => {
    const result = await runScenario('read-error-and-cleanup-throws');
    assert.equal(result.code, 1);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'FAIL');
    assert.match(result.receipt.error, /returned an MCP error/, 'the original acceptance error is retained');
    assert.match(result.receipt.fixtureCleanupError, /synthetic fixture removal failure/);
  });
});

describe('private acceptance owned marker root', () => {
  it('creates the owned marker under the Linux root and removes only its own directory', async () => {
    const result = await runScenario('happy', 'linux');
    assert.equal(result.code, 0);
    assert.equal(result.receipt.status, 'PASS');
    assert.deepEqual(result.calls.mkdtempPrefixes, ['/tmp/studio-private-acceptance-'],
      'the owned marker is created under the Linux root');
    assert.equal(result.receipt.markerRoot, '/tmp');
    assert.deepEqual(result.calls.writeFileModes, [0o600], 'the owned marker is mode 0600');
    assert.equal(result.calls.writeFilePaths.length, 1);
    const markerPath = result.calls.writeFilePaths[0];
    assert.ok(markerPath.startsWith(result.calls.fixtureDirs[0]),
      'the marker lives inside the created fixture directory');
    assert.deepEqual(result.calls.reads, [markerPath, markerPath, markerPath],
      'all three bounded reads target the owned marker');
    assert.deepEqual(result.calls.rmTargets, [result.calls.fixtureDirs[0]],
      'cleanup removes the harness-owned directory only');
  });

  it('uses the Darwin root when the platform reports Darwin', async () => {
    const result = await runScenario('happy', 'darwin');
    assert.equal(result.code, 0);
    assert.equal(result.receipt.status, 'PASS');
    assert.deepEqual(result.calls.mkdtempPrefixes, ['/private/tmp/studio-private-acceptance-'],
      'the owned marker is created under the Darwin root');
    assert.equal(result.receipt.markerRoot, '/private/tmp');
  });

  it('refuses an unsupported platform with a bounded FAIL receipt and no system-file fallback', async () => {
    const result = await runScenario('happy', 'win32');
    assert.equal(result.code, 1);
    assert.ok(result.receipt, 'a bounded receipt is emitted');
    assert.equal(result.receipt.status, 'FAIL');
    assert.match(result.receipt.error, /unsupported acceptance platform: win32/);
    assert.deepEqual(result.calls.reads, [], 'no system file was read');
    assert.deepEqual(result.calls.mkdtempPrefixes, [], 'no marker directory was created');
    assert.equal(result.calls.close, 1, 'finalization still runs before the receipt is emitted');
  });
});
