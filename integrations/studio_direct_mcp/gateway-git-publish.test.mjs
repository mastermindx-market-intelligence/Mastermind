import assert from 'node:assert/strict';
import { execFile as execFileCallback } from 'node:child_process';
import { chmod, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { startGateway } from './gateway.mjs';

const execFile = promisify(execFileCallback);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(HERE, 'fixtures', 'backend.mjs');
const GIT = '/usr/bin/git';

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
    const directivePattern =
      /required workflow|always\b|never\b|only correct tool|must use|do not use|prefer this|critical rule/i;
    for (const tool of [status, commit, push]) {
      assert.doesNotMatch(
        tool.description ?? '',
        directivePattern,
        `typed Git description contains classifier-directed language: ${tool.name}`,
      );
    }
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
