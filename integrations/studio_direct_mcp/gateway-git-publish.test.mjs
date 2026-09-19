import assert from 'node:assert/strict';
import { execFile as execFileCallback } from 'node:child_process';
import { createHash } from 'node:crypto';
import { chmod, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { startGateway } from './gateway.mjs';

const execFile = promisify(execFileCallback);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(HERE, 'fixtures', 'backend.mjs');
const COMPILER_FIXTURE = path.join(HERE, 'fixtures', 'commission-compiler.mjs');
const GIT = '/usr/bin/git';
const COMMISSION_PATH = 'research/executive_commissions/COMMISSION.md';

async function run(file, args, options = {}) {
  return execFile(file, args, { encoding: 'utf8', maxBuffer: 1024 * 1024, ...options });
}
async function git(cwd, ...args) { return run(GIT, args, { cwd }); }

function auth() {
  return {
    middleware(req, _res, next) {
      if (req.headers.authorization !== 'Bearer typed-git-test') {
        const error = new Error('unauthorized');
        error.statusCode = 401;
        throw error;
      }
      req.auth = { principal: 'typed-git-test', clientId: 'typed-git-client', scopes: ['studio.control'] };
      next();
    },
    mount() {},
  };
}

async function makePublisherFixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'studio-gateway-git-'));
  const sourceRepository = path.join(root, 'source');
  const workspacePath = path.join(root, 'workspace');
  const remote = path.join(root, 'remote.git');
  const stateDir = path.join(root, 'state');
  const operationId = 'gateway-typed-git-test';
  const branch = `sol/web-${operationId}`;
  const workspaceCli = path.join(root, 'mmx-workspace');
  await run('/bin/mkdir', ['-p', sourceRepository, workspacePath, stateDir]);
  await git(root, 'init', '--bare', remote);
  await git(workspacePath, 'init');
  await git(workspacePath, 'config', 'user.name', 'Studio Gateway Test');
  await git(workspacePath, 'config', 'user.email', 'studio-gateway@example.invalid');
  await git(workspacePath, 'checkout', '-b', branch);
  await writeFile(path.join(workspacePath, 'proof.txt'), 'typed gateway\n');
  await git(workspacePath, 'add', 'proof.txt');
  await git(workspacePath, 'commit', '-m', 'test: typed gateway');
  await git(workspacePath, 'remote', 'add', 'origin', remote);
  const { stdout } = await git(workspacePath, 'rev-parse', 'HEAD');
  const head = stdout.trim();
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
  await writeFile(workspaceCli, `#!/bin/sh\nprintf '%s\\n' '${JSON.stringify(receipt)}'\n`);
  await chmod(workspaceCli, 0o700);
  return {
    root, sourceRepository, workspacePath, remote, stateDir, operationId, branch, workspaceCli, head,
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

async function boot(extra = {}, childEnv = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'studio-gateway-basic-'));
  const stateDir = path.join(root, 'state');
  await run('/bin/mkdir', ['-p', stateDir]);
  const gw = await startGateway({
    host: '127.0.0.1',
    port: 0,
    command: process.execPath,
    args: [FIXTURE],
    cwd: HERE,
    childEnv: { ...process.env, ...childEnv },
    stateDir,
    maxSessions: 8,
    requestTimeoutMs: 30_000,
    testMode: true,
    ...extra,
  }, auth());
  return { root, gw };
}

async function connect(gw) {
  const client = new Client({ name: 'typed-git-test', version: '0.0.0' }, { capabilities: {} });
  const transport = new StreamableHTTPClientTransport(new URL(gw.url), {
    requestInit: { headers: { authorization: 'Bearer typed-git-test' } },
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

test('legacy gateway catalog remains unchanged when typed Git is not configured', async () => {
  const { root, gw } = await boot();
  const c = await connect(gw);
  try {
    const list = await c.client.listTools();
    const names = list.tools.map((tool) => tool.name);
    assert.ok(names.includes('studio_ping'));
    assert.equal(names.includes('studio_git_publish_status'), false);
    assert.equal(names.includes('studio_git_commit_current_changes'), false);
    assert.equal(names.includes('studio_git_push_current_branch'), false);
  } finally {
    await closeAll([root, gw, c]);
  }
});

test('configured gateway exposes typed Git tools with exact truthful annotations', async () => {
  const f = await makePublisherFixture();
  const { gw } = await boot({ stateDir: f.stateDir, gitPublish: f.gitPublish });
  const c = await connect(gw);
  try {
    const list = await c.client.listTools();
    const byName = new Map(list.tools.map((tool) => [tool.name, tool]));
    const status = byName.get('studio_git_publish_status');
    const commit = byName.get('studio_git_commit_current_changes');
    const push = byName.get('studio_git_push_current_branch');
    assert.ok(status);
    assert.ok(commit);
    assert.ok(push);
    assert.equal(status.annotations.readOnlyHint, true);
    assert.equal(status.annotations.destructiveHint, false);
    assert.equal(status.annotations.openWorldHint, true);
    assert.equal(commit.annotations.readOnlyHint, false);
    assert.equal(commit.annotations.destructiveHint, true);
    assert.equal(commit.annotations.idempotentHint, true);
    assert.equal(commit.annotations.openWorldHint, false);
    assert.deepEqual(Object.keys(commit.inputSchema.properties).sort(), ['expected_head_sha', 'message', 'operation_id']);
    assert.equal(push.annotations.readOnlyHint, false);
    assert.equal(push.annotations.destructiveHint, true);
    assert.equal(push.annotations.idempotentHint, true);
    assert.equal(push.annotations.openWorldHint, true);
    assert.deepEqual(Object.keys(push.inputSchema.properties).sort(), ['expected_head_sha', 'operation_id']);
  } finally {
    await closeAll([f.root, gw, c]);
  }
});

test('typed status, commit, and push are handled locally and exact remote ref proves application', async () => {
  const f = await makePublisherFixture();
  const { gw } = await boot({ stateDir: f.stateDir, gitPublish: f.gitPublish });
  const c = await connect(gw);
  try {
    await c.client.listTools();
    const backendBefore = gw.stats().requests.backendOps;

    const statusResult = await c.client.callTool({
      name: 'studio_git_publish_status',
      arguments: { operation_id: f.operationId },
    });
    assert.equal(statusResult.isError, undefined);
    assert.equal(statusResult.structuredContent.local_head_sha, f.head);
    assert.equal(statusResult.structuredContent.remote_head_sha, null);
    assert.equal(gw.stats().requests.backendOps, backendBefore, 'typed status must not hit Desktop Commander backend');

    await writeFile(path.join(f.workspacePath, 'published.txt'), 'typed publication\n');
    const commitResult = await c.client.callTool({
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: f.operationId,
        expected_head_sha: f.head,
        message: 'test: typed gateway publication',
      },
    });
    assert.equal(commitResult.isError, undefined);
    assert.equal(commitResult.structuredContent.effect_state, 'APPLIED');
    assert.equal(commitResult.structuredContent.index_synced, true);
    const commitHead = commitResult.structuredContent.commit_head_sha;
    assert.match(commitHead, /^[0-9a-f]{40}$/);
    assert.notEqual(commitHead, f.head);
    assert.equal(gw.stats().requests.backendOps, backendBefore, 'typed commit must not hit Desktop Commander backend');

    const pushResult = await c.client.callTool({
      name: 'studio_git_push_current_branch',
      arguments: { operation_id: f.operationId, expected_head_sha: commitHead },
    });
    assert.equal(pushResult.isError, undefined);
    assert.equal(pushResult.structuredContent.effect_state, 'APPLIED');
    assert.equal(pushResult.structuredContent.remote_head_sha, commitHead);
    assert.equal(gw.stats().requests.backendOps, backendBefore, 'typed push must not hit Desktop Commander backend');

    const { stdout } = await git(f.workspacePath, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim().split(/\s+/)[0], commitHead);
  } finally {
    await closeAll([f.root, gw, c]);
  }
});

test('backend tool-name collision fails closed rather than shadowing either tool', async () => {
  const f = await makePublisherFixture();
  const { gw } = await boot(
    { stateDir: f.stateDir, gitPublish: f.gitPublish },
    { FIXTURE_TYPED_GIT_COLLISION: '1' },
  );
  const c = await connect(gw);
  try {
    await assert.rejects(
      () => c.client.listTools(),
      /collides with gateway-owned tool|Internal error|MCP error/i,
    );
  } finally {
    await closeAll([f.root, gw, c]);
  }
});

async function withCommissionCompiler(f, mode = 'ok') {
  const compiler = path.join(f.root, `compiler-${mode}.mjs`);
  await writeFile(
    compiler,
    `process.env.STUB_COMMISSION_MODE = ${JSON.stringify(mode)};\n` +
    `await import(${JSON.stringify(pathToFileURL(COMPILER_FIXTURE).href)});\n`,
  );
  return {
    ...f.gitPublish,
    commissionCompiler: compiler,
    commissionCompilerInterpreter: process.execPath,
    commissionTimeoutMs: 20_000,
  };
}

function compactCommission() {
  return {
    schema_version: 'mastermind.craft_commission_request.v1',
    role: 'backend',
    authority_ref: 'gateway.session2.typed-web-publication',
    source: {
      base: { repository: 'mastermindx-market-intelligence/Mastermind', commit: 'b'.repeat(40) },
      governing: [{
        repository: 'mastermindx-market-intelligence/Mastermind',
        commit: 'b'.repeat(40),
        path: 'docs/sol_skills/INDEX.md',
      }],
    },
    outcome: {
      objective: 'Publish one bounded commission artifact through the typed Web publication plane.',
      why: 'The Web CEO must publish without a generic shell command.',
      user_journey: 'Compact intent in, canonical commission artifact out.',
      machine_outcome: 'Deterministic commission bytes with a proved digest.',
    },
    scope: { write_paths: ['research/executive_commissions'], non_goals: ['Do not add a second compiler.'] },
    inputs: ['This compact request and the repository-owned Craft method files.'],
    data: {
      time: 'Exact commit identities.',
      missing: 'Unknown admission stays unknown.',
      corrections: 'A changed request produces a new digest.',
      rights: 'Repository-owned method text only.',
    },
    method: {
      deterministic: ['Validate and render.'],
      model: ['Model judgment stays inside the bounded worker method.'],
      implementation_order: ['Validate, compile, publish.'],
    },
    deliverables: ['One canonical COMMISSION.md.'],
    acceptance: ['Published bytes hash to the declared digest.'],
    failure: {
      refusals: ['Refuse caller-selected repository, remote, branch or path.'],
      stop_conditions: ['Stop on EFFECT_UNKNOWN until the carrier is reconciled.'],
    },
    constraints: ['No execution authority.'],
    continuation: {
      record_owner: 'GitHub owns implementation and evidence.',
      next_action: 'Typed commit and typed exact-ref push.',
    },
  };
}

test('commission materialization is advertised only where the host compiler is installed', async () => {
  const bare = await makePublisherFixture();
  const bareGw = await boot({ stateDir: bare.stateDir, gitPublish: bare.gitPublish });
  const bareClient = await connect(bareGw.gw);
  try {
    const names = (await bareClient.client.listTools()).tools.map((tool) => tool.name);
    assert.ok(names.includes('studio_git_publish_status'), 'the typed Git plane stays fully usable');
    assert.equal(names.includes('studio_web_commission_materialize'), false);

    // A call to the unadvertised name must not be answered locally; it falls
    // through to the backend, which does not implement it.
    const proxied = await bareClient.client.callTool({
      name: 'studio_web_commission_materialize',
      arguments: { operation_id: bare.operationId, commission: compactCommission() },
    });
    assert.equal(proxied.isError, true);
    assert.equal(proxied.structuredContent?.schema, undefined);
  } finally {
    await closeAll([bare.root, bareGw.gw, bareClient]);
  }

  const f = await makePublisherFixture();
  const gitPublish = await withCommissionCompiler(f);
  const { gw } = await boot({ stateDir: f.stateDir, gitPublish });
  const c = await connect(gw);
  try {
    const tool = (await c.client.listTools()).tools.find((item) => item.name === 'studio_web_commission_materialize');
    assert.ok(tool);
    assert.equal(tool.annotations.readOnlyHint, false);
    assert.equal(tool.annotations.destructiveHint, true);
    assert.equal(tool.annotations.idempotentHint, true);
    assert.equal(tool.annotations.openWorldHint, false);
    assert.deepEqual(Object.keys(tool.inputSchema.properties).sort(), ['commission', 'operation_id']);
  } finally {
    await closeAll([f.root, gw, c]);
  }
});

test('gateway publishes the canonical commission locally and never reaches the backend', async () => {
  const f = await makePublisherFixture();
  const gitPublish = await withCommissionCompiler(f);
  const { gw } = await boot({ stateDir: f.stateDir, gitPublish });
  const c = await connect(gw);
  try {
    await c.client.listTools();
    const backendBefore = gw.stats().requests.backendOps;

    const materialized = await c.client.callTool({
      name: 'studio_web_commission_materialize',
      arguments: { operation_id: f.operationId, commission: compactCommission() },
    });
    assert.equal(materialized.isError, undefined);
    const data = materialized.structuredContent;
    assert.equal(data.schema, 'mastermind.studio_web_commission_result.v1');
    assert.equal(data.effect_state, 'APPLIED');
    assert.equal(data.commission_path, COMMISSION_PATH);
    assert.equal(data.local_head_sha, f.head);
    assert.equal(gw.stats().requests.backendOps, backendBefore,
      'commission materialization must not hit Desktop Commander backend');

    const published = await readFile(path.join(f.workspacePath, COMMISSION_PATH));
    assert.equal(createHash('sha256').update(published).digest('hex'), data.commission_sha256);

    const committed = await c.client.callTool({
      name: 'studio_git_commit_current_changes',
      arguments: {
        operation_id: f.operationId,
        expected_head_sha: data.local_head_sha,
        message: 'chore(web): publish commission artifact',
      },
    });
    assert.equal(committed.isError, undefined);
    const commitHead = committed.structuredContent.commit_head_sha;

    const pushed = await c.client.callTool({
      name: 'studio_git_push_current_branch',
      arguments: { operation_id: f.operationId, expected_head_sha: commitHead },
    });
    assert.equal(pushed.isError, undefined);
    assert.equal(pushed.structuredContent.remote_head_sha, commitHead);
    assert.equal(gw.stats().requests.backendOps, backendBefore);

    const { stdout } = await run(GIT, ['show', `${commitHead}:${COMMISSION_PATH}`], { cwd: f.remote });
    assert.equal(createHash('sha256').update(Buffer.from(stdout, 'utf8')).digest('hex'), data.commission_sha256);
  } finally {
    await closeAll([f.root, gw, c]);
  }
});

test('a commission tool failure is reported as a typed error without tainting reclaim on a refusal', async () => {
  const f = await makePublisherFixture();
  const gitPublish = await withCommissionCompiler(f, 'refuse');
  const { gw } = await boot({ stateDir: f.stateDir, gitPublish });
  const c = await connect(gw);
  try {
    await c.client.listTools();
    const result = await c.client.callTool({
      name: 'studio_web_commission_materialize',
      arguments: { operation_id: f.operationId, commission: compactCommission() },
    });
    assert.equal(result.isError, true);
    assert.equal(result.structuredContent.code, 'COMMISSION_COMPILER_REFUSED');
    assert.equal(result.structuredContent.effect_state, 'NOT_APPLIED');
    assert.equal(result.structuredContent.compiler_refusal, 'commission.fields');

    const invalid = await c.client.callTool({
      name: 'studio_web_commission_materialize',
      arguments: { operation_id: f.operationId, commission: { schema_version: 'wrong' } },
    });
    assert.equal(invalid.isError, true);
    assert.equal(invalid.structuredContent.code, 'TYPED_GIT_PRECHECK_REFUSED');
    assert.equal(invalid.structuredContent.effect_state, 'NOT_APPLIED');
  } finally {
    await closeAll([f.root, gw, c]);
  }
});
