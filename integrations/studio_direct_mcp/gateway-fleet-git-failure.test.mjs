// C1 fleet-gateway typed-Git failure compatibility.
//
// The installed C1 fleet gateway (chatgpt1) is an old module whose typed-Git
// error path is wrong: its opaque `catch { ... }` reports
// REFUSED/NOT_APPLIED/TYPED_GIT_PRECHECK_REFUSED for EVERY thrown status,
// commit and push, discarding the exception. A thrown mutation is not proof
// of a refusal, so the effect is unknown.
//
// This test qualifies the deterministic source compile that fixes it:
//
//   * the predecessor is the pinned public Git object f87ac012...;
//   * `fleet_git_failure_compat.py` compiles the exact pinned successor;
//   * the successor is imported as a REAL module and driven through a REAL
//     MCP `tools/call` against a REAL loopback gateway.
//
// Nothing here touches a live host, a credential, a real repository or the
// network. The pinned Git objects are read through an offline object store so
// a missing input fails the qualification instead of triggering a runtime
// network fetch, and the test never skips.

import assert from 'node:assert/strict';
import { execFile as execFileCallback } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmod, copyFile, mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import https from 'node:https';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';

const execFile = promisify(execFileCallback);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const GIT = '/usr/bin/git';
const PYTHON = 'python3';
const COMPILER = path.join(HERE, 'fleet_git_failure_compat.py');

// Pinned byte identities (see fleet_git_failure_compat.py).
const PREIMAGE_BLOB = 'f87ac012339e82fe46bce5ddc70d1d04183d1b6e';
const PREIMAGE_SHA256 = '17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30';
const PREIMAGE_SIZE = 101068;
const SUCCESSOR_SHA256 = '336de8ed10e7da483d46e93bd98439fd00c3e277111b39b5baa9cf0e68074674';
const SUCCESSOR_SIZE = 102141;
const SUCCESSOR_BLOB = 'c02bcdada5217bbc987099e90ebdce236f023b86';
const ROUTING_BLOB = '63c47d73ae7b73a61c95cee1803c549ecd6df9c8';

// The five sibling modules that exist in the tree at this pin, plus the one
// that only exists as a Git object.
const BUNDLE_MODULES = Object.freeze([
  'output-budget.mjs',
  'git-publish.mjs',
  'workspace-access.mjs',
  'paper-design.mjs',
  'fleet-status.mjs',
]);

// Byte-for-byte copies of the compiler's pinned regions. They are repeated
// here so the test can prove the generated file still carries them.
const GUARD_BLOCK = `    if (this.gitPublisher && this.selectedHostRef &&
        (name === STUDIO_GIT_PUBLISH_STATUS_TOOL.name ||
         name === STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.name ||
         name === STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.name)) {
      return gitToolResult({
        schema: 'mastermind.studio_git_tool_error.v1',
        status: 'REFUSED',
        effect_state: 'NOT_APPLIED',
        code: 'TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION',
      }, true);
    }
`;
const DISPATCH_MARKER = '      const data = name === STUDIO_GIT_PUBLISH_STATUS_TOOL.name\n';

// A secret planted in the exception the publisher throws. It must never reach
// the tool result.
const SECRET = 'c1-planted-secret-4f9b2d7a-not-for-the-caller';
const FAILURE_EXIT_CODE = 42;

const FLEET_HOST = 'c1-fleet-host.ts.net';
const FLEET_HOST_REF = 'c1-fleet-host';

// The synthetic local backend. It exposes exactly one fleet-backend tool name
// so the fleet routing contract has a local side to compare against.
const FLEET_BACKEND_TOOL = Object.freeze({
  name: 'read_file',
  title: 'Read file',
  description: 'Synthetic read-only fleet backend probe.',
  inputSchema: {
    type: 'object',
    properties: { path: { type: 'string' } },
    required: ['path'],
    additionalProperties: false,
  },
});

const BACKEND_FIXTURE_SOURCE = `#!/usr/bin/env node
// Synthetic stdio MCP backend used by the C1 fleet-gateway failure tests.
// It performs no work and touches no real system.
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const server = new Server(
  { name: 'c1-fleet-backend-fixture', version: '0.0.0' },
  { capabilities: { tools: {} } },
);
server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [${JSON.stringify(FLEET_BACKEND_TOOL)}],
}));
server.setRequestHandler(CallToolRequestSchema, async () => ({
  content: [{ type: 'text', text: 'fixture' }],
}));
await server.connect(new StdioServerTransport());
`;

async function run(file, args, options = {}) {
  return execFile(file, args, { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, ...options });
}

async function git(cwd, ...args) {
  return run(GIT, args, { cwd });
}

function sha256(data) {
  return createHash('sha256').update(data).digest('hex');
}

function gitBlobId(data) {
  return createHash('sha1')
    .update(`blob ${data.length}\0`)
    .update(data)
    .digest('hex');
}

// ---------------------------------------------------------------------------
// Offline resolution of the pinned public Git objects.
//
// The checkout is a partial clone. Resolving a missing blob through the
// ordinary repository would spawn a promisor fetch, i.e. a runtime network
// access. The pinned objects are therefore read through an offline object
// store: a bare repository with no remote at all, borrowing the canonical
// object directory as an alternate. A missing input then fails here, loudly,
// instead of skipping the test or reaching the network.
// ---------------------------------------------------------------------------

let offlineStorePromise = null;

function offlineStore() {
  if (!offlineStorePromise) {
    offlineStorePromise = (async () => {
      const root = await mkdtemp(path.join(os.tmpdir(), 'c1-offline-objects-'));
      const dir = path.join(root, 'store.git');
      await run(GIT, ['init', '--bare', '-q', dir]);
      const { stdout } = await run(GIT, ['-C', REPO, 'rev-parse', '--path-format=absolute', '--git-common-dir']);
      return { dir, objects: path.join(stdout.trim(), 'objects') };
    })();
  }
  return offlineStorePromise;
}

async function pinnedBlob(blob) {
  const store = await offlineStore();
  const { stdout } = await run(GIT, ['cat-file', 'blob', blob], {
    cwd: store.dir,
    encoding: 'buffer',
    env: {
      ...process.env,
      GIT_DIR: store.dir,
      GIT_ALTERNATE_OBJECT_DIRECTORIES: store.objects,
      GIT_TERMINAL_PROMPT: '0',
    },
  });
  return stdout;
}

// ---------------------------------------------------------------------------
// The compiled fleet bundle.
//
// The successor is imported as the real module. `gateway.predecessor.mjs` is
// the untouched predecessor in the same bundle so both can be booted and
// compared. The fleet-routing sibling is the pinned Git object; the other
// five siblings are the files that exist in the tree at this pin.
// ---------------------------------------------------------------------------

const artifacts = (async () => {
  const preimage = await pinnedBlob(PREIMAGE_BLOB);
  const routing = await pinnedBlob(ROUTING_BLOB);
  const root = await mkdtemp(path.join(os.tmpdir(), 'c1-fleet-git-'));
  const preimagePath = path.join(root, 'preimage-gateway.mjs');
  const successorPath = path.join(root, 'successor-gateway.mjs');
  await writeFile(preimagePath, preimage);
  const { stdout: reportText } = await run(PYTHON, [COMPILER, preimagePath, '--out', successorPath], { cwd: HERE });
  const report = JSON.parse(reportText);
  const successor = await readFile(successorPath);

  const bundle = path.join(root, 'bundle');
  await mkdir(path.join(bundle, 'fixtures'), { recursive: true });
  await writeFile(path.join(bundle, 'gateway.mjs'), successor);
  await writeFile(path.join(bundle, 'gateway.predecessor.mjs'), preimage);
  await writeFile(path.join(bundle, 'fleet-routing.mjs'), routing);
  for (const name of BUNDLE_MODULES) {
    await copyFile(path.join(HERE, name), path.join(bundle, name));
  }
  await symlink(path.join(HERE, 'node_modules'), path.join(bundle, 'node_modules'), 'dir');
  await writeFile(path.join(bundle, 'fixtures', 'backend.mjs'), BACKEND_FIXTURE_SOURCE);
  return { root, preimage, successor, report, bundle };
})();

// ---------------------------------------------------------------------------
// Gateway harness.
// ---------------------------------------------------------------------------

function auth() {
  return {
    middleware(req, _res, next) {
      if (req.headers.authorization !== 'Bearer c1-fleet-git-failure') {
        const error = new Error('unauthorized');
        error.statusCode = 401;
        throw error;
      }
      req.auth = {
        principal: 'c1-fleet-git-failure',
        clientId: 'c1-fleet-client',
        scopes: ['studio.control'],
      };
      next();
    },
    mount() {},
  };
}

async function boot(modulePath, extra = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'c1-fleet-gateway-'));
  const stateDir = path.join(root, 'state');
  await mkdir(stateDir, { recursive: true });
  const mod = await import(pathToFileURL(modulePath).href);
  const gw = await mod.startGateway({
    host: '127.0.0.1',
    port: 0,
    command: process.execPath,
    args: [path.join(path.dirname(modulePath), 'fixtures', 'backend.mjs')],
    cwd: path.dirname(modulePath),
    childEnv: { ...process.env },
    stateDir,
    maxSessions: 8,
    requestTimeoutMs: 30_000,
    testMode: true,
    ...extra,
  }, auth());
  return { root, gw, mod };
}

async function connect(gw) {
  const client = new Client({ name: 'c1-fleet-git-failure-test', version: '0.0.0' }, { capabilities: {} });
  const transport = new StreamableHTTPClientTransport(new URL(gw.url), {
    requestInit: { headers: { authorization: 'Bearer c1-fleet-git-failure' } },
  });
  await client.connect(transport);
  return { client, transport };
}

async function closeAll(items) {
  for (const item of items.reverse()) {
    try {
      if (item?.client) await item.client.close();
      else if (item?.close) await item.close();
      else if (typeof item === 'string') await rm(item, { recursive: true, force: true });
    } catch {}
  }
}

// ---------------------------------------------------------------------------
// Publisher fixtures.
//
// The publisher is the real one from git-publish.mjs. It reaches the installed
// workspace owner through `cfg.workspaceCli`, so the fixture is a synthetic
// owner script: it counts its own invocations and either answers with a valid
// workspace receipt or fails with a planted secret.
// ---------------------------------------------------------------------------

async function makeWorkspaceFixture({ mode = 'healthy' } = {}) {
  const root = await realpath(await mkdtemp(path.join(os.tmpdir(), 'c1-fleet-git-workspace-')));
  const sourceRepository = path.join(root, 'source');
  const workspacePath = path.join(root, 'workspace');
  const remote = path.join(root, 'remote.git');
  const stateDir = path.join(root, 'state');
  const operationId = 'c1-fleet-git-failure';
  const branch = `sol/web-${operationId}`;
  const workspaceCli = path.join(root, 'mmx-workspace');
  const callLog = path.join(root, 'publisher-calls.log');
  const receiptFile = path.join(root, 'workspace-receipt.json');
  await run('/bin/mkdir', ['-p', sourceRepository, workspacePath, stateDir]);
  await git(root, 'init', '--bare', remote);
  await git(workspacePath, 'init');
  await git(workspacePath, 'config', 'user.name', 'C1 Fleet Gateway Test');
  await git(workspacePath, 'config', 'user.email', 'c1-fleet@example.invalid');
  await git(workspacePath, 'checkout', '-b', branch);
  await writeFile(path.join(workspacePath, 'proof.txt'), 'typed git failure\n');
  await git(workspacePath, 'add', 'proof.txt');
  await git(workspacePath, 'commit', '-m', 'test: fixture');
  await git(workspacePath, 'remote', 'add', 'origin', remote);
  const head = (await git(workspacePath, 'rev-parse', 'HEAD')).stdout.trim();

  const receipt = {
    action: 'status',
    effect: 'NOT_APPLIED',
    receipt: {
      source_repository: sourceRepository,
      workspace_path: workspacePath,
      branch,
      dirty: false,
      head_sha: head,
      state: 'RELEASABLE',
    },
    schema_version: 'mastermind.workspace_cli/v1',
  };
  await writeFile(receiptFile, JSON.stringify(receipt));
  if (mode === 'throwing') {
    // The owner fails after printing a planted secret. The publisher therefore
    // throws; the gateway must classify the failure without serializing it.
    await writeFile(workspaceCli, `#!/bin/sh
printf 'call\\n' >> '${callLog}'
printf '%s\\n' '${SECRET}'
printf '%s\\n' '${SECRET}' >&2
exit ${FAILURE_EXIT_CODE}
`);
  } else {
    await writeFile(workspaceCli, `#!/bin/sh
printf 'call\\n' >> '${callLog}'
cat '${receiptFile}'
`);
  }
  await chmod(workspaceCli, 0o700);

  return {
    root,
    sourceRepository,
    workspacePath,
    remote,
    stateDir,
    operationId,
    branch,
    workspaceCli,
    callLog,
    head,
    gitPublish: {
      enabled: true,
      workspaceCli,
      gitBinary: GIT,
      sourceRepository,
      allowedRemoteUrls: [remote],
      commandTimeoutMs: 10_000,
      pushTimeoutMs: 10_000,
    },
  };
}

async function publisherCalls(fixture) {
  const text = await readFile(fixture.callLog, 'utf8').catch(() => '');
  return text.split('\n').filter((line) => line.trim() === 'call').length;
}

// ---------------------------------------------------------------------------
// Synthetic fleet host.
//
// `fleet-routing.mjs` only accepts an exact https tailnet MCP URL, so the
// route under test is a policy-valid tailnet URL whose transport is answered
// by a local synthetic MCP server. The transport is the only substituted part;
// the router, the gateway session binding and the guard are the real ones.
// ---------------------------------------------------------------------------

async function startSyntheticFleetHost() {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'c1-fleet-host-'));
  const keyPath = path.join(dir, 'key.pem');
  const certPath = path.join(dir, 'cert.pem');
  await run('openssl', [
    'req', '-x509', '-newkey', 'rsa:2048',
    '-keyout', keyPath, '-out', certPath,
    '-days', '2', '-nodes',
    '-subj', `/CN=${FLEET_HOST}`,
    '-addext', `subjectAltName=DNS:${FLEET_HOST}`,
  ]);
  const keyPem = await readFile(keyPath);
  const certPem = await readFile(certPath);

  const server = https.createServer({ key: keyPem, cert: certPem }, async (req, res) => {
    if (req.method !== 'POST') {
      res.writeHead(405, { allow: 'POST' });
      res.end();
      return;
    }
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let body;
    try {
      body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } catch {
      res.writeHead(400);
      res.end();
      return;
    }
    const respond = (payload, status = 200) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(payload));
    };
    if (body.method === 'initialize') {
      respond({
        jsonrpc: '2.0',
        id: body.id,
        result: {
          protocolVersion: body.params?.protocolVersion,
          capabilities: { tools: {} },
          serverInfo: { name: 'c1-synthetic-fleet-host', version: '0.0.0' },
        },
      });
      return;
    }
    if (body.method === 'tools/list') {
      respond({ jsonrpc: '2.0', id: body.id, result: { tools: [FLEET_BACKEND_TOOL] } });
      return;
    }
    if (body.method === 'ping') {
      respond({ jsonrpc: '2.0', id: body.id, result: {} });
      return;
    }
    if (body.id === undefined) {
      res.writeHead(202);
      res.end();
      return;
    }
    respond({ jsonrpc: '2.0', id: body.id, error: { code: -32601, message: 'Method not found' } });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, port: server.address().port, certPem };
}

// Routes the one synthetic tailnet URL to the local synthetic host over TLS,
// verified against the synthetic certificate. Every other URL keeps the
// original global fetch.
function installSyntheticHostFetch(host, port, certPem) {
  const original = globalThis.fetch;
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : (input?.url ?? String(input)));
    if (url.hostname !== host) return original(input, init);
    return new Promise((resolve, reject) => {
      const headers = {};
      if (init.headers) {
        for (const [key, value] of new Headers(init.headers).entries()) headers[key] = value;
      }
      const request = https.request({
        host: '127.0.0.1',
        port,
        path: `${url.pathname}${url.search}`,
        method: init.method ?? 'GET',
        servername: host,
        ca: certPem,
        headers,
      }, (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk));
        response.on('end', () => {
          const payload = Buffer.concat(chunks);
          const empty = payload.length === 0 || [204, 205, 304].includes(response.statusCode);
          resolve(new Response(empty ? null : payload, {
            status: response.statusCode,
            statusText: response.statusMessage,
            headers: { 'content-type': response.headers['content-type'] ?? 'application/json' },
          }));
        });
      });
      request.on('error', reject);
      if (init.signal) init.signal.addEventListener('abort', () => request.destroy(new Error('aborted')));
      if (init.body) request.write(init.body);
      request.end();
    });
  };
  return () => { globalThis.fetch = original; };
}

// ---------------------------------------------------------------------------
// Tests.
// ---------------------------------------------------------------------------

test('the compiled successor carries exactly the pinned generated identity', async () => {
  const art = await artifacts;

  assert.equal(art.preimage.length, PREIMAGE_SIZE);
  assert.equal(sha256(art.preimage), PREIMAGE_SHA256);
  assert.equal(gitBlobId(art.preimage), PREIMAGE_BLOB);

  assert.equal(art.successor.length, SUCCESSOR_SIZE);
  assert.equal(sha256(art.successor), SUCCESSOR_SHA256);
  assert.equal(gitBlobId(art.successor), SUCCESSOR_BLOB);

  // The compiler's own report.
  assert.equal(art.report.hunks, 2, 'the compile must be exactly two diff hunks');
  assert.equal(art.report.preimageSha256, PREIMAGE_SHA256);
  assert.equal(art.report.preimageGitBlob, PREIMAGE_BLOB);
  assert.equal(art.report.preimageSize, PREIMAGE_SIZE);
  assert.equal(art.report.successorSha256, SUCCESSOR_SHA256);
  assert.equal(art.report.successorGitBlob, SUCCESSOR_BLOB);
  assert.equal(art.report.successorSize, SUCCESSOR_SIZE);
  assert.equal(art.report.guard.guardPreserved, true);
  assert.equal(art.report.guard.guardPrecedesDispatch, true);
  assert.ok(art.report.guard.guardOffset < art.report.guard.dispatchOffset);

  const text = art.successor.toString('utf8');
  assert.equal(text.includes('TYPED_GIT_PRECHECK_REFUSED'), false, 'the legacy precheck code must be gone');
  assert.equal(text.includes('TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION'), true);
  assert.equal(text.includes('TYPED_GIT_READONLY_INSPECTION_REFUSED'), true);
  assert.equal(text.includes('TYPED_GIT_EFFECT_UNQUALIFIED'), true);

  // The local-session guard is byte-preserved, still ahead of the typed-Git
  // dispatch, and still contains no publisher call.
  assert.equal(text.split(GUARD_BLOCK).length - 1, 1, 'the guard must appear exactly once, byte-for-byte');
  assert.ok(text.indexOf(GUARD_BLOCK) < text.indexOf(DISPATCH_MARKER), 'the guard must precede the dispatch');
  assert.equal(/gitPublisher\.(status|commit|push)\s*\(/.test(GUARD_BLOCK), false, 'the guard must not dispatch');

  // The successor parses: importing the generated module is the parse proof.
  const mod = await import(pathToFileURL(path.join(art.bundle, 'gateway.mjs')).href);
  assert.equal(typeof mod.startGateway, 'function');
  assert.equal(typeof mod.resolveConfig, 'function');
});

test('a thrown typed-Git status is a read-only refusal, not a mutation verdict', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'throwing' });
  const { gw } = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_publish_status',
      arguments: { operation_id: fixture.operationId },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.schema, 'mastermind.studio_git_tool_error.v1');
    assert.equal(result.structuredContent.status, 'REFUSED');
    assert.equal(result.structuredContent.effect_state, 'NOT_APPLIED');
    assert.equal(result.structuredContent.code, 'TYPED_GIT_READONLY_INSPECTION_REFUSED');
    // Exactly one publisher dispatch: no retry, no duplicate.
    assert.equal(await publisherCalls(fixture), 1);
    assert.equal(gw.stats().requests.byTool.studio_git_publish_status, 1);
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('the predecessor still reports the legacy precheck refusal for the same failure', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'throwing' });
  const { gw } = await boot(path.join(art.bundle, 'gateway.predecessor.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_publish_status',
      arguments: { operation_id: fixture.operationId },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.status, 'REFUSED');
    assert.equal(result.structuredContent.effect_state, 'NOT_APPLIED');
    assert.equal(result.structuredContent.code, 'TYPED_GIT_PRECHECK_REFUSED');
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('a thrown typed-Git commit is an unqualified effect and taints the session', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'throwing' });
  const { gw } = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: fixture.operationId,
        expected_head_sha: fixture.head,
        message: 'test: uncertain commit',
      },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.schema, 'mastermind.studio_git_tool_error.v1');
    assert.equal(result.structuredContent.status, 'UNKNOWN');
    assert.equal(result.structuredContent.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.structuredContent.code, 'TYPED_GIT_EFFECT_UNQUALIFIED');
    // Exactly one publisher dispatch: no retry, no duplicate.
    assert.equal(await publisherCalls(fixture), 1);
    assert.equal(gw.stats().requests.byTool.studio_git_commit_current_changes, 1);

    // The session is tainted: a further mutation on it is refused.
    await assert.rejects(
      () => c.client.callTool({
        name: 'studio_git_push_current_branch',
        arguments: { operation_id: fixture.operationId, expected_head_sha: fixture.head },
      }),
      (error) => {
        assert.equal(error.code, 409, 'a tainted session is refused at the HTTP layer');
        assert.match(error.message, /Session tainted/);
        assert.match(error.message, /-32003/);
        return true;
      },
    );
    // The refused mutation never reached the publisher either.
    assert.equal(await publisherCalls(fixture), 1);
    assert.equal(gw.stats().requests.byTool.studio_git_push_current_branch, undefined);
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('a thrown typed-Git push is an unqualified effect and taints the session', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'throwing' });
  const { gw } = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_push_current_branch',
      arguments: { operation_id: fixture.operationId, expected_head_sha: fixture.head },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.status, 'UNKNOWN');
    assert.equal(result.structuredContent.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.structuredContent.code, 'TYPED_GIT_EFFECT_UNQUALIFIED');
    assert.equal(await publisherCalls(fixture), 1);
    assert.equal(gw.stats().requests.byTool.studio_git_push_current_branch, 1);

    await assert.rejects(
      () => c.client.callTool({
        name: 'studio_git_commit_current_changes',
        arguments: {
          operation_id: fixture.operationId,
          expected_head_sha: fixture.head,
          message: 'test: tainted session',
        },
      }),
      (error) => {
        assert.equal(error.code, 409);
        assert.match(error.message, /Session tainted/);
        return true;
      },
    );
    assert.equal(await publisherCalls(fixture), 1);
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('a real typed result is passed through with its original fields unchanged', async () => {
  // Run the complete status/commit/push path against the actual publisher.
  // The existing destination binding stays mandatory on every host; an
  // incompatible Git executable fails qualification instead of skipping it.
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'healthy' });
  const successor = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: path.join(fixture.stateDir, 'successor'),
    gitPublish: fixture.gitPublish,
  });
  const predecessor = await boot(path.join(art.bundle, 'gateway.predecessor.mjs'), {
    stateDir: path.join(fixture.stateDir, 'predecessor'),
    gitPublish: fixture.gitPublish,
  });
  const successorClient = await connect(successor.gw);
  const predecessorClient = await connect(predecessor.gw);
  try {
    // A returned refusal keeps its own receipt; it is not reclassified, and
    // the successor passes it through exactly like the predecessor.
    const refusalArgs = {
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: fixture.operationId,
        expected_head_sha: 'b'.repeat(40),
        message: 'test: expected head mismatch',
      },
    };
    const refused = await successorClient.client.callTool(refusalArgs);
    const predecessorRefused = await predecessorClient.client.callTool(refusalArgs);
    assert.equal(refused.isError, true);
    assert.equal(refused.structuredContent.schema, 'mastermind.studio_git_commit_result.v1');
    assert.equal(refused.structuredContent.status, 'REFUSED');
    assert.equal(refused.structuredContent.effect_state, 'NOT_APPLIED');
    assert.equal(refused.structuredContent.code, 'EXPECTED_HEAD_MISMATCH');
    assert.equal(refused.structuredContent.expected_head_sha, 'b'.repeat(40));
    assert.equal(refused.structuredContent.local_head_sha, fixture.head);
    assert.equal(refused.structuredContent.operation_id, fixture.operationId);
    assert.deepEqual(
      refused.structuredContent,
      predecessorRefused.structuredContent,
      'the returned receipt must reach the caller unchanged',
    );

    // A real applied commit keeps its own receipt.
    await writeFile(path.join(fixture.workspacePath, 'published.txt'), 'typed fleet publication\n');
    const dispatchesBefore = successor.gw.stats().requests.byTool.studio_git_commit_current_changes;
    const committed = await successorClient.client.callTool({
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: fixture.operationId,
        expected_head_sha: fixture.head,
        message: 'test: applied commit',
      },
    });
    assert.equal(committed.isError, undefined);
    assert.equal(committed.structuredContent.schema, 'mastermind.studio_git_commit_result.v1');
    assert.equal(committed.structuredContent.status, 'OK');
    assert.equal(committed.structuredContent.effect_state, 'APPLIED');
    assert.equal(committed.structuredContent.code, 'APPLIED');
    assert.equal(committed.structuredContent.index_synced, true);
    assert.equal(committed.structuredContent.operation_id, fixture.operationId);
    assert.equal(committed.structuredContent.branch, fixture.branch);
    assert.equal(committed.structuredContent.previous_head_sha, fixture.head);
    const commitHead = committed.structuredContent.commit_head_sha;
    assert.match(commitHead, /^[0-9a-f]{40}$/);
    assert.equal((await git(fixture.workspacePath, 'rev-parse', 'HEAD')).stdout.trim(), commitHead);
    // One dispatch, one commit object: no retry and no duplicate dispatch.
    assert.equal(
      successor.gw.stats().requests.byTool.studio_git_commit_current_changes - dispatchesBefore,
      1,
    );
    assert.equal(
      (await git(fixture.workspacePath, 'rev-list', '--count', 'HEAD')).stdout.trim(),
      '2',
    );
    const status = await successorClient.client.callTool({
      name: 'studio_git_publish_status',
      arguments: { operation_id: fixture.operationId },
    });
    assert.equal(status.isError, undefined);
    assert.equal(status.structuredContent.local_head_sha, commitHead);
    assert.equal(status.structuredContent.remote_head_sha, null);
    const pushed = await successorClient.client.callTool({
      name: 'studio_git_push_current_branch',
      arguments: { operation_id: fixture.operationId, expected_head_sha: commitHead },
    });
    assert.equal(pushed.isError, undefined);
    assert.equal(pushed.structuredContent.effect_state, 'APPLIED');
    assert.equal(pushed.structuredContent.remote_head_sha, commitHead);
    const remote = await git(fixture.workspacePath, 'ls-remote', '--heads', 'origin',
      `refs/heads/${fixture.branch}`);
    assert.equal(remote.stdout.trim().split(/\s+/)[0], commitHead);
  } finally {
    await closeAll([successorClient, predecessorClient, successor.gw, predecessor.gw, fixture.root]);
  }
});

test('a returned UNKNOWN receipt keeps its own fields and taints the session', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'healthy' });
  // The real publisher prepares the commit but cannot update the source ref:
  // the update-ref lock is already held. The publisher answers with a typed
  // UNKNOWN receipt instead of throwing.
  await mkdir(path.join(fixture.workspacePath, '.git', 'refs', 'heads', 'sol'), { recursive: true });
  await writeFile(path.join(fixture.workspacePath, '.git', 'refs', 'heads', `${fixture.branch}.lock`), 'held\n');
  await writeFile(path.join(fixture.workspacePath, 'published.txt'), 'typed fleet publication\n');

  const { gw } = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: fixture.operationId,
        expected_head_sha: fixture.head,
        message: 'test: uncertain ref update',
      },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.schema, 'mastermind.studio_git_commit_result.v1');
    assert.equal(result.structuredContent.status, 'UNKNOWN');
    assert.equal(result.structuredContent.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.structuredContent.code, 'LOCAL_REF_UPDATE_UNCERTAIN');
    assert.equal(result.structuredContent.operation_id, fixture.operationId);
    assert.equal(result.structuredContent.branch, fixture.branch);
    assert.equal(result.structuredContent.previous_head_sha, fixture.head);

    // An unqualified effect taints the session even when it was returned.
    await assert.rejects(
      () => c.client.callTool({
        name: 'studio_git_push_current_branch',
        arguments: { operation_id: fixture.operationId, expected_head_sha: fixture.head },
      }),
      (error) => {
        assert.equal(error.code, 409);
        assert.match(error.message, /Session tainted/);
        return true;
      },
    );
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('a returned PARTIAL receipt keeps its own fields unchanged', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'healthy' });
  // The commit is applied but the real index cannot be synchronized: the
  // index lock is already held. The publisher answers with a typed PARTIAL
  // receipt whose applied effect must survive unchanged.
  await writeFile(path.join(fixture.workspacePath, '.git', 'index.lock'), 'held\n');
  await writeFile(path.join(fixture.workspacePath, 'published.txt'), 'typed fleet publication\n');

  const { gw } = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: fixture.operationId,
        expected_head_sha: fixture.head,
        message: 'test: partially applied commit',
      },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.schema, 'mastermind.studio_git_commit_result.v1');
    assert.equal(result.structuredContent.status, 'PARTIAL');
    assert.equal(result.structuredContent.effect_state, 'APPLIED');
    assert.equal(result.structuredContent.code, 'APPLIED_INDEX_SYNC_FAILED');
    assert.equal(result.structuredContent.index_synced, false);
    assert.match(result.structuredContent.commit_head_sha, /^[0-9a-f]{40}$/);
    // The applied ref is real: a partial receipt is not a denial.
    assert.equal(
      (await git(fixture.workspacePath, 'rev-parse', 'HEAD')).stdout.trim(),
      result.structuredContent.commit_head_sha,
    );
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('the error payload leaks no part of the thrown exception', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'throwing' });
  const { gw } = await boot(path.join(art.bundle, 'gateway.mjs'), {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
  });
  const c = await connect(gw);
  try {
    const result = await c.client.callTool({
      name: 'studio_git_publish_status',
      arguments: { operation_id: fixture.operationId },
    });
    assert.equal(result.isError, true);
    const serialized = JSON.stringify(result);

    // Reproduce the very exception the publisher threw, so the leak check is
    // made against the real object and not against a guess.
    let thrown = null;
    try {
      await run(fixture.workspaceCli, ['status', '--operation-id', fixture.operationId, '--lane', 'web']);
    } catch (error) {
      thrown = error;
    }
    assert.ok(thrown, 'the fixture owner must fail');

    const forbidden = [
      SECRET,
      thrown.message,
      thrown.stack,
      thrown.stdout,
      thrown.stderr,
      thrown.cmd,
      thrown.path,
      thrown.syscall,
      JSON.stringify(thrown.spawnargs ?? null),
      String(thrown.code),
      'Command failed',
    ].filter((value) => typeof value === 'string' && value.length > 0);
    for (const value of forbidden) {
      assert.equal(serialized.includes(value), false, `the tool result leaked ${JSON.stringify(value.slice(0, 40))}`);
    }
    assert.equal(serialized.includes('TYPED_GIT_READONLY_INSPECTION_REFUSED'), true);
  } finally {
    await closeAll([fixture.root, gw, c]);
  }
});

test('the local-session guard refuses typed Git before any publisher dispatch', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'healthy' });
  const host = await startSyntheticFleetHost();
  const restoreFetch = installSyntheticHostFetch(FLEET_HOST, host.port, host.certPem);
  let gw = null;
  let c = null;
  try {
    const booted = await boot(path.join(art.bundle, 'gateway.mjs'), {
      stateDir: fixture.stateDir,
      gitPublish: fixture.gitPublish,
      fleetRouting: {
        enabled: true,
        routes: [{ hostRef: FLEET_HOST_REF, url: `https://${FLEET_HOST}/mcp` }],
        requestTimeoutMs: 5_000,
      },
    });
    gw = booted.gw;
    c = await connect(gw);

    // Bind the session to the synthetic fleet host through the gateway's own
    // fleet-routing select-host mechanism.
    const selected = await c.client.callTool({
      name: 'studio_select_host',
      arguments: { hostRef: FLEET_HOST_REF },
    });
    assert.equal(selected.isError, undefined, JSON.stringify(selected.structuredContent));
    assert.equal(selected.structuredContent.status, 'BOUND');
    assert.equal(selected.structuredContent.hostRef, FLEET_HOST_REF);

    const result = await c.client.callTool({
      name: 'studio_git_publish_status',
      arguments: { operation_id: fixture.operationId },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.schema, 'mastermind.studio_git_tool_error.v1');
    assert.equal(result.structuredContent.status, 'REFUSED');
    assert.equal(result.structuredContent.effect_state, 'NOT_APPLIED');
    assert.equal(result.structuredContent.code, 'TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION');
    // The publisher was never called.
    assert.equal(await publisherCalls(fixture), 0, 'the publisher must not be dispatched');
    assert.equal(gw.stats().requests.byTool.studio_git_publish_status, undefined);
  } finally {
    restoreFetch();
    await closeAll([c, gw, fixture.root]);
    await new Promise((resolve) => host.server.close(resolve));
  }
});

test('the generated gateway keeps the predecessor tool surface and fleet configuration', async () => {
  const art = await artifacts;
  const fixture = await makeWorkspaceFixture({ mode: 'healthy' });
  const config = {
    stateDir: fixture.stateDir,
    gitPublish: fixture.gitPublish,
    paperDesign: {
      enabled: true,
      pythonPath: '/usr/bin/python3',
      bridgePath: path.join(fixture.root, 'paper-bridge.py'),
      bridgeSha256: 'a'.repeat(64),
      appPath: path.join(fixture.root, 'paper-app'),
      commandTimeoutMs: 5_000,
    },
    fleetStatus: {
      enabled: true,
      launcherPath: path.join(fixture.root, 'fleet-launcher.sh'),
      launcherSha256: 'b'.repeat(64),
      timeoutMs: 5_000,
    },
    fleetRouting: {
      enabled: true,
      routes: [{ hostRef: FLEET_HOST_REF, url: `https://${FLEET_HOST}/mcp` }],
      requestTimeoutMs: 5_000,
    },
  };
  const successor = await boot(path.join(art.bundle, 'gateway.mjs'), config);
  const predecessor = await boot(path.join(art.bundle, 'gateway.predecessor.mjs'), config);
  const successorClient = await connect(successor.gw);
  const predecessorClient = await connect(predecessor.gw);
  try {
    const successorTools = (await successorClient.client.listTools()).tools.map((tool) => tool.name).sort();
    const predecessorTools = (await predecessorClient.client.listTools()).tools.map((tool) => tool.name).sort();
    assert.deepEqual(successorTools, predecessorTools, 'the local tool surface must be unchanged');
    for (const name of [
      'studio_ping',
      'studio_output_page',
      'studio_fleet_status',
      'studio_select_host',
      'studio_git_publish_status',
      'studio_git_commit_current_changes',
      'studio_git_push_current_branch',
      'paper_inspect',
      'paper_catalog',
      'paper_read',
      'paper_prepare',
      'paper_edit',
    ]) {
      assert.ok(successorTools.includes(name), `the generated gateway must still expose ${name}`);
    }

    // The fleet routing, scheduler and allowlist configuration is identical.
    const successorConfig = successor.mod.resolveConfig(config);
    const predecessorConfig = predecessor.mod.resolveConfig(config);
    assert.deepEqual(successorConfig.fleetRouting, predecessorConfig.fleetRouting);
    assert.deepEqual(successorConfig.fleetStatus, predecessorConfig.fleetStatus);
    assert.deepEqual(successorConfig.toolAllowlist, predecessorConfig.toolAllowlist);
    assert.deepEqual(
      successorConfig.fleetRouting.routes.map((route) => route.hostRef),
      [FLEET_HOST_REF],
    );

    // The fleet routing refusal is identical on both modules.
    const successorRefusal = await successorClient.client.callTool({
      name: 'studio_select_host',
      arguments: { hostRef: 'not-a-configured-host' },
    });
    const predecessorRefusal = await predecessorClient.client.callTool({
      name: 'studio_select_host',
      arguments: { hostRef: 'not-a-configured-host' },
    });
    assert.equal(successorRefusal.isError, true);
    assert.equal(successorRefusal.structuredContent.code, 'FLEET_ROUTE_PREFLIGHT_REFUSED');
    assert.deepEqual(successorRefusal.structuredContent, predecessorRefusal.structuredContent);
  } finally {
    await closeAll([successorClient, predecessorClient, successor.gw, predecessor.gw, fixture.root]);
  }
});
