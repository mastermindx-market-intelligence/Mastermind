import assert from 'node:assert/strict';
import { execFile as execFileCallback, execFileSync } from 'node:child_process';
import { chmod, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import {
  STUDIO_GIT_PUBLISH_STATUS_TOOL,
  STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL,
  STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL,
  createGitPublisher,
  resolveGitPublishConfig,
} from './git-publish.mjs';

const execFile = promisify(execFileCallback);
const GIT = '/usr/bin/git';

async function run(file, args, options = {}) {
  return execFile(file, args, {
    encoding: 'utf8',
    maxBuffer: 1024 * 1024,
    ...options,
  });
}

async function git(cwd, ...args) {
  return run(GIT, args, { cwd });
}

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'studio-git-publish-'));
  const sourceRepo = path.join(root, 'source');
  const workspace = path.join(root, 'workspace');
  const remote = path.join(root, 'remote.git');
  const operationId = 'typed-git-test-operation';
  const branch = `sol/web-${operationId}`;
  const cli = path.join(root, 'mmx-workspace');
  await run('/bin/mkdir', ['-p', sourceRepo, workspace]);
  await git(root, 'init', '--bare', remote);
  await git(workspace, 'init');
  await git(workspace, 'config', 'user.name', 'Studio Direct Test');
  await git(workspace, 'config', 'user.email', 'studio-direct-test@example.invalid');
  await git(workspace, 'checkout', '-b', branch);
  await writeFile(path.join(workspace, 'proof.txt'), 'v1\n');
  await git(workspace, 'add', 'proof.txt');
  await git(workspace, 'commit', '-m', 'test: initial');
  await git(workspace, 'remote', 'add', 'origin', remote);
  const { stdout: headOut } = await git(workspace, 'rev-parse', 'HEAD');
  const head = headOut.trim();

  const receipt = {
    action: 'status',
    effect: 'NOT_APPLIED',
    receipt: {
      source_repository: sourceRepo,
      workspace_path: workspace,
      branch,
      dirty: false,
      head_sha: head,
      state: 'RELEASABLE',
    },
    schema_version: 'mastermind.workspace_cli/v1',
  };
  await writeFile(cli, `#!/bin/sh\nprintf '%s\\n' '${JSON.stringify(receipt)}'\n`);
  await chmod(cli, 0o700);

  const config = {
    enabled: true,
    workspaceCli: cli,
    gitBinary: GIT,
    sourceRepository: sourceRepo,
    allowedRemoteUrls: [remote],
    commandTimeoutMs: 10_000,
    pushTimeoutMs: 10_000,
  };
  return {
    root, sourceRepo, workspace, remote, operationId, branch, cli, head, config,
    async cleanup() { await rm(root, { recursive: true, force: true }); },
  };
}

test('tool metadata is narrow and truthful', () => {
  assert.equal(STUDIO_GIT_PUBLISH_STATUS_TOOL.annotations.readOnlyHint, true);
  assert.equal(STUDIO_GIT_PUBLISH_STATUS_TOOL.annotations.openWorldHint, true);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.annotations.readOnlyHint, false);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.annotations.destructiveHint, true);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.annotations.idempotentHint, true);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.annotations.openWorldHint, false);
  assert.deepEqual(
    STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.required,
    ['operation_id', 'expected_head_sha', 'message'],
  );
  for (const forbidden of ['branch', 'remote', 'path', 'command', 'force']) {
    assert.equal(forbidden in STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties, false);
  }
  assert.equal(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.annotations.readOnlyHint, false);
  assert.equal(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.annotations.destructiveHint, true);
  assert.equal(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.annotations.idempotentHint, true);
  assert.equal(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.annotations.openWorldHint, true);
  assert.match(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.description, /real index is synchronized to that exact commit/);
  assert.deepEqual(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.inputSchema.required, ['operation_id', 'expected_head_sha']);
  assert.equal('branch' in STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.inputSchema.properties, false);
  assert.equal('remote' in STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.inputSchema.properties, false);
  assert.equal('path' in STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.inputSchema.properties, false);
  assert.equal('command' in STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.inputSchema.properties, false);
  assert.equal('force' in STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.inputSchema.properties, false);
});

test('configuration is closed and disabled unless explicitly enabled', () => {
  assert.equal(resolveGitPublishConfig(undefined), null);
  assert.equal(resolveGitPublishConfig(false), null);
  assert.throws(() => resolveGitPublishConfig({ enabled: false }), /enabled must be true/);
  assert.throws(() => resolveGitPublishConfig({ enabled: true, surprise: true }), /not supported/);
  assert.throws(() => resolveGitPublishConfig({
    enabled: true,
    workspaceCli: 'relative',
    gitBinary: GIT,
    sourceRepository: '/tmp/source',
    allowedRemoteUrls: ['/tmp/remote'],
  }), /absolute path/);
});

test('resolved configuration can be consumed again without opening caller-controlled keys', () => {
  const raw = {
    enabled: true,
    workspaceCli: '/tmp/mmx-workspace',
    gitBinary: GIT,
    sourceRepository: '/tmp/source',
    allowedRemoteUrls: ['/tmp/remote'],
  };
  const resolved = resolveGitPublishConfig(raw);
  assert.equal(resolveGitPublishConfig(resolved), resolved);
  assert.throws(() => resolveGitPublishConfig({ ...resolved, lane: 'other' }), /not supported/);
});

test('status is read-only and push is exact, non-force, and idempotent', async () => {
  const f = await fixture();
  try {
    const publisher = createGitPublisher(f.config);
    const before = await publisher.status({ operation_id: f.operationId });
    assert.equal(before.schema, 'mastermind.studio_git_publish_status.v1');
    assert.equal(before.branch, f.branch);
    assert.equal(before.local_head_sha, f.head);
    assert.equal(before.remote_head_sha, null);
    assert.equal(before.clean, true);
    assert.equal(before.publication_state, 'NOT_APPLIED');
    assert.equal(before.ready_to_push, true);

    const pushed = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(pushed.schema, 'mastermind.studio_git_push_result.v1');
    assert.equal(pushed.status, 'OK');
    assert.equal(pushed.effect_state, 'APPLIED');
    assert.equal(pushed.code, 'APPLIED');
    assert.equal(pushed.push_attempted, true);
    assert.equal(pushed.local_head_sha, f.head);
    assert.equal(pushed.remote_head_sha, f.head);

    const { stdout: remoteOut } = await git(f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(remoteOut.trim().split(/\s+/)[0], f.head);

    const replay = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(replay.effect_state, 'APPLIED');
    assert.equal(replay.code, 'ALREADY_APPLIED');
    assert.equal(replay.push_attempted, false);
  } finally {
    await f.cleanup();
  }
});

test('typed commit includes staged and unstaged changes, syncs the real index, and never pushes', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
    await git(f.workspace, 'add', 'proof.txt');
    await writeFile(path.join(f.workspace, 'new.txt'), 'new\n');

    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: typed commit',
    });
    assert.equal(result.schema, 'mastermind.studio_git_commit_result.v1');
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED');
    assert.equal(result.previous_head_sha, f.head);
    assert.equal(result.index_synced, true);
    assert.match(result.commit_head_sha, /^[0-9a-f]{40}$/);
    assert.notEqual(result.commit_head_sha, f.head);

    const { stdout: localOut } = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(localOut.trim(), result.commit_head_sha);
    const { stdout: subjectOut } = await git(f.workspace, 'log', '-1', '--format=%s');
    assert.equal(subjectOut.trim(), 'test: typed commit');
    const { stdout: statusOut } = await git(f.workspace, 'status', '--porcelain=v1', '--untracked-files=all');
    assert.equal(statusOut, '');
    const { stdout: remoteBefore } = await git(f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(remoteBefore.trim(), '', 'typed commit must never publish remotely');

    const replay = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: typed commit',
    });
    assert.equal(replay.status, 'REFUSED');
    assert.equal(replay.effect_state, 'NOT_APPLIED');
    assert.equal(replay.code, 'EXPECTED_HEAD_MISMATCH');

    const pushed = await publisher.push({
      operation_id: f.operationId,
      expected_head_sha: result.commit_head_sha,
    });
    assert.equal(pushed.effect_state, 'APPLIED');
    assert.equal(pushed.remote_head_sha, result.commit_head_sha);
  } finally {
    await f.cleanup();
  }
});

test('typed commit rejects stale fences, extra selectors, and multiline messages', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
    const publisher = createGitPublisher(f.config);
    const stale = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: '0'.repeat(40),
      message: 'test: stale',
    });
    assert.equal(stale.status, 'REFUSED');
    assert.equal(stale.effect_state, 'NOT_APPLIED');
    assert.equal(stale.code, 'EXPECTED_HEAD_MISMATCH');
    await assert.rejects(
      () => publisher.commit({ operation_id: f.operationId, expected_head_sha: f.head, message: 'x', path: '/tmp' }),
      /arguments are invalid/,
    );
    await assert.rejects(
      () => publisher.commit({ operation_id: f.operationId, expected_head_sha: f.head, message: 'bad\nmessage' }),
      /message is invalid/,
    );
  } finally {
    await f.cleanup();
  }
});

test('lost local ref-update response reconciles typed commit to APPLIED when exact new HEAD is observed', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
    let injected = false;
    const wrappedExec = async (file, args, options) => {
      if (file === GIT && args[0] === 'update-ref' && !injected) {
        injected = true;
        await execFile(file, args, options);
        const error = new Error('simulated lost response after local ref update');
        error.code = 'SIMULATED_LOSS';
        throw error;
      }
      return execFile(file, args, options);
    };
    const publisher = createGitPublisher(f.config, { execFile: wrappedExec });
    const result = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: ambiguous local commit',
    });
    assert.equal(injected, true);
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED_AFTER_AMBIGUOUS_UPDATE_RETURN');
    assert.equal(result.index_synced, true);
    const { stdout } = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(stdout.trim(), result.commit_head_sha);
  } finally {
    await f.cleanup();
  }
});

test('dirty workspace refuses before a remote write', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'uncommitted.txt'), 'dirty\n');
    const publisher = createGitPublisher(f.config);
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'WORKSPACE_DIRTY');
    const { stdout } = await git(f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim(), '');
  } finally {
    await f.cleanup();
  }
});

test('expected-head mismatch refuses before a remote write', async () => {
  const f = await fixture();
  try {
    const publisher = createGitPublisher(f.config);
    const other = '0'.repeat(40);
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: other });
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'EXPECTED_HEAD_MISMATCH');
    const { stdout } = await git(f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim(), '');
  } finally {
    await f.cleanup();
  }
});

test('foreign origin is rejected by host policy', async () => {
  const f = await fixture();
  try {
    const otherRemote = path.join(f.root, 'other.git');
    await git(f.root, 'init', '--bare', otherRemote);
    await git(f.workspace, 'remote', 'set-url', 'origin', otherRemote);
    const publisher = createGitPublisher(f.config);
    await assert.rejects(() => publisher.status({ operation_id: f.operationId }), /origin URL is outside/);
  } finally {
    await f.cleanup();
  }
});

test('operation and argument surface reject injection and extra selectors', async () => {
  const f = await fixture();
  try {
    const publisher = createGitPublisher(f.config);
    await assert.rejects(() => publisher.status({ operation_id: '../oops' }), /operation_id is invalid/);
    await assert.rejects(() => publisher.status({ operation_id: f.operationId, path: '/tmp' }), /arguments are invalid/);
    await assert.rejects(() => publisher.push({ operation_id: f.operationId, expected_head_sha: f.head, force: true }), /arguments are invalid/);
    await assert.rejects(() => publisher.commit({ operation_id: f.operationId, expected_head_sha: f.head, message: 'x', command: 'git status' }), /arguments are invalid/);
  } finally {
    await f.cleanup();
  }
});

test('concurrent local HEAD advance cannot widen the fenced remote effect', async () => {
  const f = await fixture();
  try {
    let advancedHead = null;
    let injected = false;
    const wrappedExec = async (file, args, options) => {
      if (file === GIT && args[0] === 'push' && !injected) {
        injected = true;
        await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
        await git(f.workspace, 'add', 'proof.txt');
        await git(f.workspace, 'commit', '-m', 'test: concurrent local advance');
        const { stdout } = await git(f.workspace, 'rev-parse', 'HEAD');
        advancedHead = stdout.trim();
      }
      return execFile(file, args, options);
    };
    const publisher = createGitPublisher(f.config, { execFile: wrappedExec });
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(injected, true);
    assert.notEqual(advancedHead, f.head);
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED');
    assert.equal(result.remote_head_sha, f.head);
    assert.equal(result.local_head_sha, advancedHead);
    const { stdout: remoteOut } = await git(f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(remoteOut.trim().split(/\s+/)[0], f.head);
  } finally {
    await f.cleanup();
  }
});

test('lost push response reconciles to APPLIED when exact remote head proves the effect', async () => {
  const f = await fixture();
  try {
    let injected = false;
    const wrappedExec = async (file, args, options) => {
      if (file === GIT && args[0] === 'push' && !injected) {
        injected = true;
        await execFile(file, args, options);
        const error = new Error('simulated lost response after remote accepted push');
        error.code = 'SIMULATED_LOSS';
        throw error;
      }
      return execFile(file, args, options);
    };
    const publisher = createGitPublisher(f.config, { execFile: wrappedExec });
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(injected, true);
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED_AFTER_AMBIGUOUS_PUSH_RETURN');
    assert.equal(result.remote_head_sha, f.head);
  } finally {
    await f.cleanup();
  }
});

test('push failure after admission remains EFFECT_UNKNOWN when exact remote effect is not proved', async () => {
  const f = await fixture();
  try {
    let injected = false;
    const wrappedExec = async (file, args, options) => {
      if (file === GIT && args[0] === 'push' && !injected) {
        injected = true;
        const error = new Error('simulated transport failure after push admission');
        error.code = 'SIMULATED_LOSS';
        throw error;
      }
      return execFile(file, args, options);
    };
    const publisher = createGitPublisher(f.config, { execFile: wrappedExec });
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(injected, true);
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'PUSH_RESULT_UNCERTAIN');
    assert.equal(result.push_attempted, true);
  } finally {
    await f.cleanup();
  }
});
