import assert from 'node:assert/strict';
import { execFile as execFileCallback, execFileSync, spawn } from 'node:child_process';
import { renameSync, symlinkSync } from 'node:fs';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { createHash } from 'node:crypto';
import { chmod, lstat, mkdir, mkdtemp, readFile, readdir, realpath, rename, rm, stat, symlink, utimes, writeFile } from 'node:fs/promises';
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
const GIT = process.env.STUDIO_DIRECT_TEST_GIT_BINARY || '/usr/bin/git';

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

async function fixture(options = {}) {
  const root = await realpath(await mkdtemp(path.join(os.tmpdir(), 'studio-git-publish-')));
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
  if (options.largeIndex) {
    const blob = (await git(workspace, 'rev-parse', 'HEAD:proof.txt')).stdout.trim();
    const entries = Array.from({length: 7000}, (_,i) =>
      `100644 ${blob}\ttracked/${String(i).padStart(5, '0')}-${'x'.repeat(170)}\n`).join('');
    // A real Git index/tree, without thousands of unnecessary working files.
    execFileSync(GIT, ['update-index', '--index-info'], {cwd: workspace, input: entries});
    await git(workspace, 'commit', '--quiet', '-m', 'test: large recovery inventory');
  }
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
    ['operation_id', 'expected_head_sha'],
  );
  // The commit variant requires a message and forbids index_recovery; the
  // recovery variant requires index_recovery and forbids message and merge.
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.oneOf.length, 2);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.oneOf[0].required, ['message']);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.oneOf[0].not.required, ['index_recovery']);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.oneOf[1].required, ['index_recovery']);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.oneOf[1].not.anyOf,
    [{required: ['message']}, {required: ['merge']}]);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.additionalProperties, false);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.required, ['mode']);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties.mode.enum,
    ['PREVIEW', 'APPLY', 'RECONCILE']);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties.lock.additionalProperties, false);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties.lock.required,
    ['device', 'inode', 'file_type', 'uid', 'gid', 'mode', 'size', 'mtime_ns', 'content_sha256']);
  assert.equal(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties.custody.additionalProperties, false);
  assert.deepEqual(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties.custody.required,
    ['maintenance_window', 'pending_mutators_retired']);
  assert.equal('branch' in STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties, false);
  assert.equal('path' in STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties, false);
  assert.equal('command' in STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties, false);
  assert.equal('force' in STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema.properties.index_recovery.properties, false);
  assert.match(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.description, /index_recovery/);
  assert.match(STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.description, /historical origin unknown/);
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

test('typed commit stays closed-world and does not require remote observation', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
    let remoteObservationAttempted = false;
    const wrappedExec = async (file, args, options) => {
      if (file === GIT && gitCommand(args) === 'ls-remote') {
        remoteObservationAttempted = true;
        throw new Error('simulated remote observation outage');
      }
      return execFile(file, args, options);
    };
    const publisher = createGitPublisher(f.config, { execFile: wrappedExec });
    const result = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: local-only typed commit',
    });
    assert.equal(remoteObservationAttempted, false);
    assert.equal(result.status, 'OK', JSON.stringify(result));
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED');
    assert.equal('remote_head_sha' in result, false);
    assert.equal('publication_state' in result, false);
    const { stdout } = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(stdout.trim(), result.commit_head_sha);

    await assert.rejects(
      () => publisher.status({ operation_id: f.operationId }),
      /simulated remote observation outage/,
    );
    assert.equal(remoteObservationAttempted, true);
  } finally {
    await f.cleanup();
  }
});

test('scratch cleanup failure after ref admission cannot downgrade an applied commit', async () => {
  const f = await fixture();
  let leakedScratch = null;
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
    const publisher = createGitPublisher(f.config, {
      rm: async (target) => {
        leakedScratch = target;
        throw new Error('simulated scratch cleanup failure');
      },
    });
    const result = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: cleanup failure preserves effect truth',
    });
    assert.ok(leakedScratch);
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED');
    const { stdout } = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(stdout.trim(), result.commit_head_sha);
  } finally {
    if (leakedScratch) await rm(leakedScratch, { recursive: true, force: true });
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
      if (file === GIT && gitCommand(args) === 'push' && !injected) {
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
      if (file === GIT && gitCommand(args) === 'push' && !injected) {
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

test('explicit server-side one-ref rejection is diagnosed without treating its ref as unknown', async () => {
  const f = await fixture();
  try {
    const hook = path.join(f.remote, 'hooks', 'pre-receive');
    await writeFile(hook, '#!/bin/sh\nprintf "test-only remote rejection\\n" >&2\nexit 1\n');
    await chmod(hook, 0o700);
    let pushCount = 0;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        if (file === GIT && gitCommand(args) === 'push') pushCount += 1;
        return execFile(file, args, options);
      },
    });
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(pushCount, 1, 'a rejection must never initiate another write');
    assert.equal(result.status, 'REFUSED', JSON.stringify(result));
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'REMOTE_REF_REJECTED_UNCHANGED');
    assert.equal(result.push_attempted, true);
    assert.equal(result.retry_allowed, false);
    assert.equal(result.ready_to_push, false);
    assert.equal(result.diagnostic_scope, 'SAME_CARRIER_READ_ONLY');
    assert.equal(result.rejection_reason, 'UNDETERMINED');
    assert.equal(result.local_head_sha, f.head);
    assert.equal(result.remote_head_sha, null);
    assert.equal((await git(f.workspace, 'ls-remote', '--heads', 'origin',
      `refs/heads/${f.branch}`)).stdout.trim(), '');
  } finally {
    await f.cleanup();
  }
});

test('an unrelated porcelain ref cannot clear an ambiguous admitted push', async () => {
  const f = await fixture();
  try {
    let pushCount = 0;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        if (file === GIT && gitCommand(args) === 'push') {
          pushCount += 1;
          const error = new Error('test-only wrong-ref remote rejection');
          error.code = 1;
          error.stdout = ['!', `${f.head}:refs/heads/unrelated`, '[remote rejected] (failed)'].join(String.fromCharCode(9)) + String.fromCharCode(10);
          error.stderr = '';
          throw error;
        }
        return execFile(file, args, options);
      },
    });
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(pushCount, 1);
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'PUSH_RESULT_UNCERTAIN');
  } finally {
    await f.cleanup();
  }
});

test('push failure after admission remains EFFECT_UNKNOWN when exact remote effect is not proved', async () => {
  const f = await fixture();
  try {
    let injected = false;
    const wrappedExec = async (file, args, options) => {
      if (file === GIT && gitCommand(args) === 'push' && !injected) {
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

// Destination/ref regressions use only the incumbent disposable local Git fixture.
function gitCommand(args) {
  let i = 0;
  while (args[i] === '-c') i += 2;
  return args[i];
}
async function otherRemote(f, name = 'other.git') {
  const location = path.join(f.root, name);
  await git(f.root, 'init', '--bare', location);
  return location;
}
async function refsAt(location) {
  return (await git(location, 'for-each-ref', '--format=%(refname) %(objectname)')).stdout.trim();
}
for (const variant of ['pushurl', 'multiple-pushurls', 'pushInsteadOf', 'insteadOf']) {
  test(`destination fence refuses ${variant} before any network command`, async () => {
    const f = await fixture();
    try {
      const foreign = await otherRemote(f);
      if (variant === 'pushurl') await git(f.workspace, 'config', 'remote.origin.pushurl', foreign);
      if (variant === 'multiple-pushurls') {
        await git(f.workspace, 'config', '--add', 'remote.origin.pushurl', f.remote);
        await git(f.workspace, 'config', '--add', 'remote.origin.pushurl', foreign);
      }
      if (variant === 'pushInsteadOf') await git(f.workspace, 'config', `url.${foreign}.pushInsteadOf`, f.remote);
      if (variant === 'insteadOf') await git(f.workspace, 'config', `url.${foreign}.insteadOf`, f.remote);
      let networkCommands = 0;
      const publisher = createGitPublisher(f.config, {execFile: async (file, args, options) => {
        if (file === GIT && ['push', 'ls-remote'].includes(gitCommand(args))) networkCommands++;
        return execFile(file, args, options);
      }});
      let refusal;
      try { await publisher.push({operation_id:f.operationId, expected_head_sha:f.head}); }
      catch (error) { refusal = error; }
      assert.equal(await refsAt(foreign), '', 'forbidden destination must remain untouched');
      assert.equal(await refsAt(f.remote), '', 'no partial multi-destination push');
      assert.equal(networkCommands, 0, 'qualification must precede all network commands');
      assert.ok(refusal, 'invalid destination must be refused');
    } finally { await f.cleanup(); }
  });
}
for (const setting of ['push.followTags', 'remote.origin.mirror']) {
  test(`one-ref push is not widened by ${setting}`, async () => {
    const f = await fixture();
    try {
      await git(f.workspace, 'tag', '-a', 'unrequested-tag', '-m', 'not authorized');
      await git(f.workspace, 'branch', 'unrequested-branch');
      await git(f.workspace, 'config', setting, 'true');
      const out = await createGitPublisher(f.config).push({operation_id:f.operationId, expected_head_sha:f.head});
      assert.equal(out.effect_state, 'APPLIED');
      assert.equal(await refsAt(f.remote), `refs/heads/${f.branch} ${f.head}`);
    } finally { await f.cleanup(); }
  });
}
test('allowlisted distinct push destination is also the reconciliation destination', async () => {
  const f = await fixture();
  try {
    const destination = await otherRemote(f, 'allowed-push.git');
    await git(f.workspace, 'config', 'remote.origin.pushurl', destination);
    const publisher = createGitPublisher({...f.config, allowedRemoteUrls:[f.remote,destination]});
    const out = await publisher.push({operation_id:f.operationId, expected_head_sha:f.head});
    assert.equal(out.effect_state, 'APPLIED');
    assert.equal(out.remote_head_sha, f.head);
    assert.equal((await publisher.status({operation_id:f.operationId})).remote_head_sha, f.head);
    assert.equal(await refsAt(f.remote), '');
    assert.equal(await refsAt(destination), `refs/heads/${f.branch} ${f.head}`);
  } finally { await f.cleanup(); }
});
for (const loseReply of [false, true]) {
  test(`captured destination survives origin change at admission, lost reply=${loseReply}`, async () => {
    const f = await fixture();
    try {
      const foreign = await otherRemote(f);
      let injected = false;
      const publisher = createGitPublisher(f.config, {execFile:async(file,args,options)=>{
        if(file===GIT && gitCommand(args)==='push' && !injected){
          injected=true;
          await git(f.workspace,'remote','set-url','origin',foreign);
          await git(f.workspace,'config','remote.origin.pushurl',foreign);
          const out=await execFile(file,args,options);
          if(loseReply) throw new Error('simulated lost reply after exact destination write');
          return out;
        }
        return execFile(file,args,options);
      }});
      const out=await publisher.push({operation_id:f.operationId,expected_head_sha:f.head});
      assert.equal(injected,true);assert.equal(await refsAt(foreign),'');
      assert.equal(await refsAt(f.remote),`refs/heads/${f.branch} ${f.head}`);
      assert.equal(out.effect_state,'APPLIED');assert.equal(out.remote_head_sha,f.head);
    } finally { await f.cleanup(); }
  });
}
test('mandatory pre-push hook is not bypassed by destination pinning',async()=>{
  const f=await fixture();
  try{
    const hook=path.join(f.workspace,'.git','hooks','pre-push');
    const marker=path.join(f.root,'hook-ran');
    await writeFile(hook,`#!/bin/sh\nprintf '%s' "$1" > '${marker}'\nexit 1\n`);await chmod(hook,0o700);
    const out=await createGitPublisher(f.config).push({operation_id:f.operationId,expected_head_sha:f.head});
    assert.equal(await readFile(marker,'utf8'),'origin');
    assert.equal(await refsAt(f.remote),'');assert.notEqual(out.effect_state,'APPLIED');
  }finally{await f.cleanup();}
});
test('submodule-pushing policy is refused, not silently disabled',async()=>{
  const f=await fixture();
  try{
    await git(f.workspace,'config','push.recurseSubmodules','on-demand');let calls=0;
    const publisher=createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT&&gitCommand(args)==='push')calls++;return execFile(file,args,options);
    }});
    let refusal;try{await publisher.push({operation_id:f.operationId,expected_head_sha:f.head});}catch(e){refusal=e;}
    assert.equal(calls,0);assert.equal(await refsAt(f.remote),'');assert.ok(refusal);
  }finally{await f.cleanup();}
});

test('second-hop rewrite of captured destination refuses before network',async()=>{
  const f=await fixture();
  try{
    const allowed=await otherRemote(f,'allowed.git'),foreign=await otherRemote(f,'forbidden.git');
    await git(f.workspace,'config',`url.${allowed}.insteadOf`,f.remote);
    await git(f.workspace,'config',`url.${foreign}.insteadOf`,allowed);
    let network=0;
    const publisher=createGitPublisher({...f.config,allowedRemoteUrls:[f.remote,allowed]},{execFile:async(file,args,options)=>{
      if(file===GIT&&['push','ls-remote'].includes(gitCommand(args)))network++;return execFile(file,args,options);
    }});
    await assert.rejects(()=>publisher.push({operation_id:f.operationId,expected_head_sha:f.head}),/pinned origin/);
    assert.equal(network,0);assert.equal(await refsAt(allowed),'');assert.equal(await refsAt(foreign),'');
  }finally{await f.cleanup();}
});
test('mandatory submodule check remains enabled on the exact push',async()=>{
  const f=await fixture();
  try{
    await git(f.workspace,'config','push.recurseSubmodules','check');let sawCheck=false;
    const publisher=createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT&&gitCommand(args)==='push')sawCheck=args.includes('--recurse-submodules=check');
      return execFile(file,args,options);
    }});
    const out=await publisher.push({operation_id:f.operationId,expected_head_sha:f.head});
    assert.equal(out.effect_state,'APPLIED');assert.equal(sawCheck,true);
  }finally{await f.cleanup();}
});

test('non-fast-forward remains refused without rewinding the remote',async()=>{
  const f=await fixture();
  try{
    await git(f.workspace,'push','origin',`${f.head}:refs/heads/${f.branch}`);
    await writeFile(path.join(f.workspace,'proof.txt'),'remote ahead\n');
    await git(f.workspace,'add','proof.txt');await git(f.workspace,'commit','-m','ahead');
    const ahead=(await git(f.workspace,'rev-parse','HEAD')).stdout.trim();
    await git(f.workspace,'push','origin',`${ahead}:refs/heads/${f.branch}`);
    await git(f.workspace,'reset','--hard',f.head);
    const out=await createGitPublisher(f.config).push({operation_id:f.operationId,expected_head_sha:f.head});
    assert.notEqual(out.effect_state,'APPLIED');
    assert.equal(await refsAt(f.remote),`refs/heads/${f.branch} ${ahead}`);
  }finally{await f.cleanup();}
});


test('selected repository publisher uses the exact v2 owner binding', async () => {
  const f = await fixture();
  try {
    const calls = [];
    const selectedExec = async (file, args, options) => {
      if (file === f.cli) {
        calls.push(args);
        return { stdout: JSON.stringify({
          schema_version: 'mastermind.workspace_cli/v2', action: 'status',
          effect: 'NOT_APPLIED', repository: 'macro',
          receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace,
            branch: f.branch, head_sha: f.head, dirty: false },
        }), stderr: '' };
      }
      return execFile(file, args, options);
    };
    const publisher = createGitPublisher({ ...f.config, repository: 'macro' }, { execFile: selectedExec });
    const status = await publisher.status({ operation_id: f.operationId });
    assert.equal(status.local_head_sha, f.head);
    assert.deepEqual(calls, [['status', '--operation-id', f.operationId, '--lane', 'web', '--repository', 'macro']]);
    await writeFile(path.join(f.workspace, 'proof.txt'), 'macro selected\n');
    const committed = await publisher.commit({ operation_id: f.operationId, expected_head_sha: f.head, message: 'test: selected owner' });
    assert.equal(committed.effect_state, 'APPLIED');
    const pushed = await publisher.push({ operation_id: f.operationId, expected_head_sha: committed.commit_head_sha });
    assert.equal(pushed.remote_head_sha, committed.commit_head_sha);
    assert.ok(calls.every((args) => args.at(-1) === 'macro'));
  } finally { await f.cleanup(); }
});

test('selected publisher refuses a foreign or unversioned owner receipt before Git', async () => {
  const f = await fixture();
  try {
    for (const bad of [{ repository: 'terminal', schema_version: 'mastermind.workspace_cli/v2' },
                       { repository: 'macro', schema_version: 'mastermind.workspace_cli/v1' }]) {
      let gitCalls = 0;
      const publisher = createGitPublisher({ ...f.config, repository: 'macro' }, {
        execFile: async (file) => {
          if (file !== f.cli) { gitCalls++; throw new Error('must not reach Git'); }
          return { stdout: JSON.stringify({ ...bad, action: 'status', effect: 'NOT_APPLIED',
            receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace, branch: f.branch } }) };
        },
      });
      await assert.rejects(publisher.status({ operation_id: f.operationId }), /repository binding/);
      assert.equal(gitCalls, 0);
    }
  } finally { await f.cleanup(); }
});

test('read-only cleanliness probes preserve config semantics and confine optional locks', async () => {
  const f = await fixture();
  try {
    const calls = [];
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        calls.push({file, args, env: options?.env ?? {}});
        return execFile(file, args, options);
      },
    });
    const status = await publisher.status({ operation_id: f.operationId });
    assert.equal(status.clean, true);
    const cleanliness = new Set(['diff-files', 'diff-index', 'ls-files']);
    const observed = calls.filter(({file, args}) => file === GIT && cleanliness.has(gitCommand(args)));
    assert.deepEqual(observed.map(({args}) => gitCommand(args)).sort(), ['diff-files', 'diff-index', 'ls-files']);
    for (const {env} of observed) {
      assert.equal(env.GIT_OPTIONAL_LOCKS, '0');
      assert.equal('GIT_CONFIG_GLOBAL' in env, false);
      assert.equal('GIT_CONFIG_NOSYSTEM' in env, false);
    }
    for (const {file, args, env} of calls.filter(({file, args}) =>
      file === GIT && !cleanliness.has(gitCommand(args)))) {
      assert.equal('GIT_OPTIONAL_LOCKS' in env, false, `${gitCommand(args)} inherited observation fence`);
      assert.equal('GIT_CONFIG_GLOBAL' in env, false);
      assert.equal('GIT_CONFIG_NOSYSTEM' in env, false);
    }
  } finally {
    await f.cleanup();
  }
});

test('global exclude semantics cannot create false-clean push readiness', async () => {
  const f = await fixture();
  const previousHome = process.env.HOME;
  try {
    const home = path.join(f.root, 'home');
    const ignoreDir = path.join(home, '.config', 'git');
    await run('/bin/mkdir', ['-p', ignoreDir]);
    await writeFile(path.join(home, '.gitconfig'), '[core]\n\texcludesFile = /dev/null\n');
    await writeFile(path.join(ignoreDir, 'ignore'), 'pending.txt\n');
    await writeFile(path.join(f.workspace, 'pending.txt'), 'must remain visible to publication admission\n');
    process.env.HOME = home;

    const publisher = createGitPublisher(f.config);
    const status = await publisher.status({operation_id: f.operationId});
    assert.equal(status.clean, false);
    assert.equal(status.ready_to_push, false);

    const out = await publisher.push({operation_id: f.operationId, expected_head_sha: f.head});
    assert.equal(out.effect_state, 'NOT_APPLIED');
    assert.equal(out.code, 'WORKSPACE_DIRTY');
    const {stdout: remoteOut} = await git(
      f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(remoteOut.trim(), '');
  } finally {
    if (previousHome === undefined) delete process.env.HOME;
    else process.env.HOME = previousHome;
    await f.cleanup();
  }
});

test('tracked and staged changes both refuse push under split cleanliness probes', async () => {
  for (const staged of [false, true]) {
    const f = await fixture();
    try {
      await writeFile(path.join(f.workspace, 'proof.txt'), staged ? 'staged\n' : 'unstaged\n');
      if (staged) await git(f.workspace, 'add', 'proof.txt');
      const publisher = createGitPublisher(f.config);
      const out = await publisher.push({operation_id: f.operationId, expected_head_sha: f.head});
      assert.equal(out.effect_state, 'NOT_APPLIED');
      assert.equal(out.code, 'WORKSPACE_DIRTY');
      const {stdout: remoteOut} = await git(
        f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
      assert.equal(remoteOut.trim(), '');
    } finally {
      await f.cleanup();
    }
  }
});


function closedProfileFor(f) {
  return {
    enabled: true, workspaceCli: f.cli, gitBinary: GIT,
    commandTimeoutMs: 10_000, pushTimeoutMs: 10_000,
    repositories: [
      { repository: 'mastermind', sourceRepository: path.join(f.root, 'mastermind-source'),
        allowedRemoteUrls: [path.join(f.root, 'mastermind-remote.git')] },
      { repository: 'macro', sourceRepository: path.join(f.root, 'macro-source'),
        allowedRemoteUrls: [path.join(f.root, 'macro-remote.git')] },
      { repository: 'terminal', sourceRepository: f.sourceRepo, allowedRemoteUrls: [f.remote] },
    ],
  };
}

test('closed three-repository publication profile is explicit, immutable and rejects aliases/remotes', async () => {
  const f = await fixture();
  try {
    const profile = closedProfileFor(f);
    const frozen = resolveGitPublishConfig(profile);
    assert.equal(resolveGitPublishConfig(frozen), frozen);
    assert.deepEqual(frozen.repositories.map((p) => p.repository), ['mastermind', 'macro', 'terminal']);
    assert.equal(frozen.repositories[2].sourceRepository, f.sourceRepo);
    assert.throws(() => resolveGitPublishConfig({ ...profile, repository: 'terminal' }), /not supported/);
    assert.throws(() => resolveGitPublishConfig({ ...profile, repositories: profile.repositories.slice(0, 2) }), /exact closed/);
    assert.throws(() => resolveGitPublishConfig({ ...profile,
      repositories: [profile.repositories[0], profile.repositories[1], profile.repositories[1]] }), /unique/);
    assert.throws(() => resolveGitPublishConfig({ ...profile,
      repositories: [profile.repositories[0], profile.repositories[1],
        { ...profile.repositories[2], sourceRepository: profile.repositories[0].sourceRepository }] }), /distinct/);
    assert.throws(() => resolveGitPublishConfig({ ...profile,
      repositories: [profile.repositories[0], profile.repositories[1],
        { ...profile.repositories[2], allowedRemoteUrls: profile.repositories[0].allowedRemoteUrls }] }), /distinct/);
    assert.throws(() => resolveGitPublishConfig({ ...profile,
      repositories: [profile.repositories[0], profile.repositories[1],
        { ...profile.repositories[2], allowedRemoteUrls: [f.remote, 'another'] }] }), /distinct/);
  } finally { await f.cleanup(); }
});

test('closed publisher routes only the uniquely registered Terminal operation and retains exact commit/push fencing', async () => {
  const f = await fixture();
  try {
    const seen = [];
    const exec = async (file, args, options) => {
      if (file !== f.cli) return execFile(file, args, options);
      const alias = args.at(-1);
      assert.deepEqual(args, ['status', '--operation-id', f.operationId,
        '--lane', 'web', '--repository', alias]);
      seen.push(alias);
      if (alias !== 'terminal') {
        const error = new Error('workspace registration absent');
        error.code = 2;
        error.stdout = '';
        error.stderr = JSON.stringify({
          schema_version: 'mastermind.workspace_cli/v2',
          action: 'status', effect: 'NOT_APPLIED', repository: alias,
          error: 'workspace is not registered to the source repository',
        });
        throw error;
      }
      return { stdout: JSON.stringify({
        schema_version: 'mastermind.workspace_cli/v2',
        action: 'status', effect: 'NOT_APPLIED', repository: alias,
        receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace,
          branch: f.branch, dirty: false, head_sha: f.head },
      }), stderr: '' };
    };
    const publisher = createGitPublisher(closedProfileFor(f), { execFile: exec });
    const before = await publisher.status({ operation_id: f.operationId });
    assert.equal(before.local_head_sha, f.head);
    assert.equal(before.remote_head_sha, null);
    await writeFile(path.join(f.workspace, 'proof.txt'), 'terminal repair\n');
    const committed = await publisher.commit({
      operation_id: f.operationId, expected_head_sha: f.head, message: 'fix: closed publisher routing',
    });
    assert.equal(committed.effect_state, 'APPLIED');
    const pushed = await publisher.push({
      operation_id: f.operationId, expected_head_sha: committed.commit_head_sha,
    });
    assert.equal(pushed.effect_state, 'APPLIED');
    assert.equal(pushed.remote_head_sha, committed.commit_head_sha);
    // The delegated publisher independently rereads its exact Terminal binding
    // during commit/push, so its extra Terminal observations are intentional.
    assert.equal(seen.filter((alias) => alias === 'mastermind').length, 3);
    assert.equal(seen.filter((alias) => alias === 'macro').length, 3);
    assert.ok(seen.filter((alias) => alias === 'terminal').length >= 3);
    assert.ok(seen.every((alias) => ['mastermind', 'macro', 'terminal'].includes(alias)));
    const {stdout} = await git(f.workspace, 'ls-remote', '--heads', 'origin', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim().split(/\s+/)[0], committed.commit_head_sha);
  } finally { await f.cleanup(); }
});

test('closed publisher refuses duplicate operation ownership or bad registry receipts before Git', async () => {
  const f = await fixture();
  try {
    for (const caseName of ['ambiguous', 'unversioned', 'foreign', 'unregistered']) {
      let gitCalls = 0;
      const exec = async (file, args) => {
        if (file !== f.cli) { gitCalls++; throw new Error('Git must remain untouched'); }
        const alias = args.at(-1);
        const registered = alias === 'terminal' || (caseName === 'ambiguous' && alias === 'macro');
        const result = registered ? {
          schema_version: 'mastermind.workspace_cli/v2', action: 'status',
          effect: 'NOT_APPLIED', repository: alias,
          receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace,
            branch: f.branch, dirty: false, head_sha: f.head },
        } : {
          schema_version: 'mastermind.workspace_cli/v2', action: 'status',
          effect: 'NOT_APPLIED', repository: alias,
          error: 'workspace is not registered to the source repository',
        };
        if (caseName === 'unregistered') {
          // A stdout success can never claim registration absence; this is
          // malformed evidence, not the canonical exit-code-2 refusal.
          delete result.receipt;
          result.error = 'workspace is not registered to the source repository';
        }
        if (caseName === 'unversioned' && alias === 'macro') result.schema_version = 'mastermind.workspace_cli/v1';
        if (caseName === 'foreign' && alias === 'macro') result.repository = 'terminal';
        return { stdout: JSON.stringify(result), stderr: '' };
      };
      const publisher = createGitPublisher(closedProfileFor(f), { execFile: exec });
      await assert.rejects(publisher.commit({
        operation_id: f.operationId, expected_head_sha: f.head, message: 'test: no effects',
      }), /more than one repository|invalid repository receipt|unexpected result/);
      assert.equal(gitCalls, 0, caseName);
    }
  } finally { await f.cleanup(); }
});

test('closed publisher fails closed on stdout absence even when another repository is registered', async () => {
  const f = await fixture();
  try {
    for (const caseName of ['malformed stdout absence', 'stdout absence beside a clean registration']) {
      let gitCalls = 0;
      const exec = async (file, args) => {
        if (file !== f.cli) { gitCalls++; throw new Error('Git must remain untouched'); }
        const alias = args.at(-1);
        if (caseName === 'stdout absence beside a clean registration' && alias === 'macro') {
          const error = new Error('workspace registration absent');
          error.code = 2;
          error.stdout = '';
          error.stderr = JSON.stringify({
            schema_version: 'mastermind.workspace_cli/v2', action: 'status',
            effect: 'NOT_APPLIED', repository: alias,
            error: 'workspace is not registered to the source repository',
          });
          throw error;
        }
        if (caseName === 'stdout absence beside a clean registration' && alias === 'terminal') {
          return { stdout: JSON.stringify({
            schema_version: 'mastermind.workspace_cli/v2', action: 'status',
            effect: 'NOT_APPLIED', repository: alias,
            receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace,
              branch: f.branch, dirty: false, head_sha: f.head },
          }), stderr: '' };
        }
        return { stdout: JSON.stringify({
          schema_version: 'mastermind.workspace_cli/v2', action: 'status',
          effect: 'NOT_APPLIED', repository: alias,
          error: 'workspace is not registered to the source repository',
        }), stderr: '' };
      };
      const publisher = createGitPublisher(closedProfileFor(f), { execFile: exec });
      await assert.rejects(publisher.commit({
        operation_id: f.operationId, expected_head_sha: 'b'.repeat(40), message: 'test: no effects',
      }), /unexpected result/, caseName);
      assert.equal(gitCalls, 0, caseName);
    }
  } finally { await f.cleanup(); }
});

test('closed publisher keeps canonical exit-code-2 absence as the only non-registration evidence', async () => {
  const f = await fixture();
  try {
    const canonicalAbsence = (alias) => {
      const error = new Error('workspace registration absent');
      error.code = 2;
      error.stdout = '';
      error.stderr = JSON.stringify({
        schema_version: 'mastermind.workspace_cli/v2', action: 'status',
        effect: 'NOT_APPLIED', repository: alias,
        error: 'workspace is not registered to the source repository',
      });
      return error;
    };
    let gitCalls = 0;
    const exec = async (file, args, options) => {
      if (file !== f.cli) return execFile(file, args, options);
      const alias = args.at(-1);
      if (alias === 'terminal') {
        return { stdout: JSON.stringify({
          schema_version: 'mastermind.workspace_cli/v2', action: 'status',
          effect: 'NOT_APPLIED', repository: alias,
          receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace,
            branch: f.branch, dirty: false, head_sha: f.head },
        }), stderr: '' };
      }
      throw canonicalAbsence(alias);
    };

    const absent = createGitPublisher(closedProfileFor(f), {
      execFile: (file, args) => {
        if (file !== f.cli) { gitCalls++; throw new Error('Git must remain untouched'); }
        throw canonicalAbsence(args.at(-1));
      },
    });
    await assert.rejects(absent.commit({
      operation_id: f.operationId, expected_head_sha: f.head, message: 'test: no effects',
    }), /not registered in the closed repository profile/);
    assert.equal(gitCalls, 0);

    const routed = createGitPublisher(closedProfileFor(f), { execFile: exec });
    const refused = await routed.commit({
      operation_id: f.operationId, expected_head_sha: 'b'.repeat(40), message: 'test: no effects',
    });
    assert.equal(refused.status, 'REFUSED');
    assert.equal(refused.effect_state, 'NOT_APPLIED');
    assert.equal(refused.code, 'EXPECTED_HEAD_MISMATCH');
  } finally { await f.cleanup(); }
});


test('sparse typed commit seeds its private index from the linked worktree index', async () => {
  const f = await fixture();
  try {
    await run('/bin/mkdir', ['-p', path.join(f.workspace, 'visible'), path.join(f.workspace, 'hidden')]);
    await writeFile(path.join(f.workspace, 'visible', 'shown.txt'), 'original\n');
    await writeFile(path.join(f.workspace, 'hidden', 'preserve.txt'), 'hidden tracked\n');
    await git(f.workspace, 'add', '-A');
    await git(f.workspace, 'commit', '-m', 'test: complete source before sparse checkout');
    const { stdout: baseOut } = await git(f.workspace, 'rev-parse', 'HEAD');
    const base = baseOut.trim();
    const receipt = {
      schema_version: 'mastermind.workspace_cli/v1', action: 'status', effect: 'NOT_APPLIED',
      receipt: { source_repository: f.sourceRepo, workspace_path: f.workspace, branch: f.branch,
        dirty: false, head_sha: base, state: 'RELEASABLE' },
    };
    const shell = '#!/bin/sh\n' + 'printf "%s\\n" ' + "'" + JSON.stringify(receipt) + "'" + '\n';
    await writeFile(f.cli, shell);
    await chmod(f.cli, 0o700);
    await git(f.workspace, 'sparse-checkout', 'init', '--cone');
    await git(f.workspace, 'sparse-checkout', 'set', 'visible');
    await assert.rejects(readFile(path.join(f.workspace, 'hidden', 'preserve.txt')), /ENOENT/);
    await writeFile(path.join(f.workspace, 'visible', 'shown.txt'), 'changed\n');
    await writeFile(path.join(f.workspace, 'visible', 'new.txt'), 'new file\n');

    const { stdout: indexOut } = await git(f.workspace, 'rev-parse', '--git-path', 'index');
    const realIndexPath = path.resolve(f.workspace, indexOut.trim());
    const realIndex = await readFile(realIndexPath);
    let privateIndexVerified = false;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        if (file === GIT && args[0] === 'add' && options?.env?.GIT_INDEX_FILE) {
          assert.deepEqual(await readFile(options.env.GIT_INDEX_FILE), realIndex,
            'private staging index must retain sparse skip-worktree flags');
          privateIndexVerified = true;
        }
        return execFile(file, args, options);
      },
    });
    const result = await publisher.commit({
      operation_id: f.operationId, expected_head_sha: base,
      message: 'test: sparse typed commit',
    });
    assert.equal(privateIndexVerified, true);
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.status, 'OK');
    assert.equal(result.index_synced, true);
    const { stdout: hiddenOut } = await git(f.workspace, 'show', 'HEAD:hidden/preserve.txt');
    assert.equal(hiddenOut, 'hidden tracked\n');
    const { stdout: shownOut } = await git(f.workspace, 'show', 'HEAD:visible/shown.txt');
    assert.equal(shownOut, 'changed\n');
    const { stdout: newOut } = await git(f.workspace, 'show', 'HEAD:visible/new.txt');
    assert.equal(newOut, 'new file\n');
    const { stdout: statusOut } = await git(f.workspace, 'status', '--porcelain=v1', '--untracked-files=all');
    assert.equal(statusOut, '');
    assert.equal((await publisher.status({operation_id:f.operationId})).clean, true);
  } finally { await f.cleanup(); }
});

test('typed commit captures a same-size unstaged edit after copying a racily clean index', async () => {
  const f = await fixture();
  try {
    await git(f.workspace, 'config', 'core.checkStat', 'minimal');
    await git(f.workspace, 'config', 'core.trustctime', 'false');
    await git(f.workspace, 'config', 'core.fsmonitor', 'false');

    const proofPath = path.join(f.workspace, 'proof.txt');
    const timestamp = 1_700_000_000;
    await utimes(proofPath, timestamp, timestamp);
    await git(f.workspace, 'add', '--', 'proof.txt');
    const { stdout: indexOut } = await git(f.workspace, 'rev-parse', '--git-path', 'index');
    const realIndexPath = path.resolve(f.workspace, indexOut.trim());
    await utimes(realIndexPath, timestamp, timestamp);

    const originalIndex = await readFile(realIndexPath);
    const originalIndexMtime = (await stat(realIndexPath, { bigint: true })).mtimeNs;
    const assertRealIndexUnchanged = async () => {
      assert.deepEqual(await readFile(realIndexPath), originalIndex,
        'pre-commit preparation must not rewrite the real index');
      assert.equal((await stat(realIndexPath, { bigint: true })).mtimeNs, originalIndexMtime,
        'pre-commit preparation must not retimestamp the real index');
    };

    // Keep v2 entirely unstaged with the same size and compared timestamp.
    await writeFile(proofPath, 'v2\n');
    await utimes(proofPath, timestamp, timestamp);
    assert.equal((await stat(proofPath)).size, 3);
    const diffNames = async (indexPath) => {
      const { stdout } = await run(GIT, ['diff-files', '--name-only', '--', 'proof.txt'], {
        cwd: f.workspace,
        env: { ...process.env, GIT_INDEX_FILE: indexPath, GIT_OPTIONAL_LOCKS: '0' },
      });
      return stdout;
    };

    // Identical index bytes lose Git's racy-clean guard if the copy is newer.
    const newerCopy = path.join(f.root, 'newer-index-control');
    await writeFile(newerCopy, originalIndex);
    await utimes(newerCopy, timestamp + 60, timestamp + 60);
    assert.deepEqual(await readFile(newerCopy), originalIndex);
    assert.equal(await diffNames(realIndexPath), 'proof.txt\n');
    assert.equal(await diffNames(newerCopy), '');
    await assertRealIndexUnchanged();

    let candidateChecks = 0;
    let refChecks = 0;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        if (file === GIT && args[0] === 'commit-tree') {
          await assertRealIndexUnchanged();
          const { stdout } = await git(f.workspace, 'show', args[1] + ':proof.txt');
          assert.equal(stdout, 'v2\n',
            'the actual candidate tree must contain the unstaged edit');
          candidateChecks++;
        }
        if (file === GIT && args[0] === 'update-ref') {
          await assertRealIndexUnchanged();
          const { stdout: oldHead } = await git(f.workspace, 'rev-parse', 'HEAD');
          assert.equal(oldHead.trim(), f.head,
            'the branch must remain unchanged before its fenced update');
          const { stdout: candidateContent } = await git(
            f.workspace, 'show', args[2] + ':proof.txt');
          assert.equal(candidateContent, 'v2\n',
            'the commit admitted to update-ref must contain the edit');
          refChecks++;
        }
        return execFile(file, args, options);
      },
    });
    const result = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: preserve racily clean index semantics',
    });
    assert.equal(result.code, 'APPLIED', JSON.stringify(result));
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.index_synced, true);
    assert.equal(candidateChecks, 1);
    assert.equal(refChecks, 1);
    assert.notEqual(result.commit_head_sha, f.head);
    const { stdout: committed } = await git(
      f.workspace, 'show', result.commit_head_sha + ':proof.txt');
    assert.equal(committed, 'v2\n');
    const { stdout: staged } = await git(f.workspace, 'show', ':proof.txt');
    assert.equal(staged, 'v2\n',
      'post-commit synchronization must install the committed content');
  } finally {
    await f.cleanup();
  }
});

test('private-index preparation refuses concurrent real-index mutation before ref update', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'changed\n');
    let injected = false;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        const out = await execFile(file, args, options);
        if (!injected && file === GIT && args[0] === 'write-tree' && options?.env?.GIT_INDEX_FILE) {
          await writeFile(path.join(f.workspace, 'competitor.txt'), 'concurrent\n');
          await git(f.workspace, 'add', 'competitor.txt');
          injected = true;
        }
        return out;
      },
    });
    const result = await publisher.commit({
      operation_id: f.operationId, expected_head_sha: f.head,
      message: 'test: concurrent index refusal',
    });
    assert.equal(injected, true);
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'REAL_INDEX_CHANGED_DURING_PREPARATION');
    const { stdout: headOut } = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(headOut.trim(), f.head);
    const { stdout: remoteOut } = await git(
      f.workspace, 'ls-remote', '--heads', 'origin', 'refs/heads/' + f.branch);
    assert.equal(remoteOut.trim(), '');
  } finally { await f.cleanup(); }
});


test('foreign index lock is preserved after the fenced ref update', async () => {
  const f = await fixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'v2\n');
    const {stdout: indexOut} = await git(f.workspace, 'rev-parse', '--git-path', 'index');
    const lockPath = path.resolve(f.workspace, indexOut.trim()) + '.lock';
    let injected = false;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        const out = await execFile(file, args, options);
        if (!injected && file === GIT && args[0] === 'commit-tree') {
          // Disposable synthetic workspace only. Git index lock belongs to
          // another writer and must never be deleted by the publisher.
          await writeFile(lockPath, 'foreign index lock\n', {flag:'wx'});
          injected = true;
        }
        return out;
      },
    });
    const result = await publisher.commit({
      operation_id:f.operationId, expected_head_sha:f.head,
      message:'test: preserve foreign index lock',
    });
    assert.equal(injected, true);
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.index_synced, false);
    assert.equal(result.status, 'PARTIAL');
    assert.equal(result.code, 'APPLIED_INDEX_SYNC_FAILED');
    assert.equal(await readFile(lockPath, 'utf8'), 'foreign index lock\n');
    const {stdout: headOut} = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(headOut.trim(), result.commit_head_sha);
  } finally {await f.cleanup();}
});


async function preparedMergeFixture() {
  const f = await fixture();
  await git(f.workspace, 'checkout', '-b', 'fixture-protected', f.head);
  await writeFile(path.join(f.workspace, 'proof.txt'), 'protected runtime\n');
  await git(f.workspace, 'add', 'proof.txt');
  await git(f.workspace, 'commit', '-m', 'test: protected successor');
  f.protectedBase = (await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim();
  await git(f.workspace, 'update-ref', 'refs/remotes/origin/master', f.protectedBase);
  await git(f.workspace, 'checkout', f.branch);
  await writeFile(path.join(f.workspace, 'proof.txt'), 'requested CEO selection\n');
  await git(f.workspace, 'add', 'proof.txt');
  await git(f.workspace, 'commit', '-m', 'test: original source');
  f.head = (await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim();
  await assert.rejects(git(f.workspace, 'merge-tree', '--write-tree', f.head, f.protectedBase),
    (error) => error.code === 1 && error.stdout.includes('CONFLICT'));
  await writeFile(path.join(f.workspace, 'proof.txt'), 'protected runtime\nrequested CEO selection\n');
  await git(f.workspace, 'add', 'proof.txt');
  f.tree = (await git(f.workspace, 'write-tree')).stdout.trim();
  f.args = { operation_id: f.operationId, expected_head_sha: f.head,
    message: 'test: preserve reviewed integration ancestry',
    merge: { expected_protected_base_sha: f.protectedBase, expected_tree_sha: f.tree } };
  return f;
}

test('merge schema accepts only optional exact parent and tree fences', () => {
  const schema = STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL.inputSchema;
  assert.equal(schema.required.includes('merge'), false);
  assert.equal(schema.properties.merge.additionalProperties, false);
  assert.deepEqual(schema.properties.merge.required, ['expected_protected_base_sha', 'expected_tree_sha']);
  assert.deepEqual(Object.keys(schema.properties.merge.properties), schema.properties.merge.required);
});

test('typed merge preserves reviewed conflict resolution and actual protected ancestry without network', async () => {
  const f = await preparedMergeFixture();
  try {
    const commands = [];
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT) {
        const command = gitCommand(args);
        commands.push(command);
        assert.ok(!['fetch', 'push', 'ls-remote', 'clone'].includes(command), 'commit must remain local-only');
      }
      return execFile(file, args, options);
    } });
    const result = await publisher.commit(f.args);
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.status, 'OK');
    const record = (await git(f.workspace, 'show', '-s', '--format=%T%n%P', result.commit_head_sha)).stdout.trim().split('\n');
    assert.deepEqual(record, [f.tree, `${f.head} ${f.protectedBase}`]);
    assert.equal((await git(f.workspace, 'status', '--porcelain')).stdout, '');
    await git(f.workspace, 'merge-base', '--is-ancestor', f.protectedBase, result.commit_head_sha);
    await git(f.workspace, 'merge-tree', '--write-tree', result.commit_head_sha, f.protectedBase);
    assert.equal((await readFile(path.join(f.workspace, 'proof.txt'), 'utf8')), 'protected runtime\nrequested CEO selection\n');
    assert.equal(commands.filter((command) => command === 'commit-tree').length, 1);
    assert.equal((await git(f.workspace, 'ls-remote', '--heads', 'origin')).stdout, '');
  } finally { await f.cleanup(); }
});

test('merge can record missing ancestry with an unchanged reviewed tree and binds its second parent in the action reference', async () => {
  const f = await fixture();
  try {
    const tree = (await git(f.workspace, 'rev-parse', 'HEAD^{tree}')).stdout.trim();
    const refs = [];
    for (const message of ['protected one', 'protected two']) {
      const base = (await git(f.workspace, 'commit-tree', tree, '-p', f.head, '-m', message)).stdout.trim();
      await git(f.workspace, 'update-ref', 'refs/remotes/origin/master', base);
      const result = await createGitPublisher(f.config).commit({ operation_id: f.operationId,
        expected_head_sha: f.head, message: 'test: same reviewed tree',
        merge: { expected_protected_base_sha: base, expected_tree_sha: tree } });
      assert.equal(result.effect_state, 'APPLIED');
      assert.equal((await git(f.workspace, 'show', '-s', '--format=%P', result.commit_head_sha)).stdout.trim(), `${f.head} ${base}`);
      refs.push(result.action_ref);
      await git(f.workspace, 'reset', '--hard', f.head);
    }
    assert.notEqual(refs[0], refs[1]);
    const ordinary = await createGitPublisher(f.config).commit({ operation_id: f.operationId,
      expected_head_sha: f.head, message: 'test: unchanged ordinary commit' });
    assert.equal(ordinary.code, 'NO_COMMITTABLE_CHANGES');
  } finally { await f.cleanup(); }
});

for (const merge of [null, [], {}, { expected_protected_base_sha: 'a'.repeat(40) },
  { expected_protected_base_sha: 'A'.repeat(40), expected_tree_sha: 'b'.repeat(40) },
  { expected_protected_base_sha: 'a'.repeat(40), expected_tree_sha: 'b'.repeat(40), ref: 'refs/heads/foreign' }]) {
  test(`malformed merge object is rejected before owner or Git effects: ${JSON.stringify(merge)}`, async () => {
    const f = await fixture();
    try {
      let calls = 0;
      const publisher = createGitPublisher(f.config, { execFile: async () => { calls++; throw new Error('unexpected effect'); } });
      await assert.rejects(publisher.commit({ operation_id: f.operationId,
        expected_head_sha: f.head, message: 'test: invalid merge', merge }), /merge requires/);
      assert.equal(calls, 0);
      assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    } finally { await f.cleanup(); }
  });
}

for (const mismatch of ['protected', 'missing_protected', 'tree', 'head', 'duplicate', 'already_contained']) {
  test(`merge ${mismatch} fence refuses without moving the owned ref or real index`, async () => {
    const f = await preparedMergeFixture();
    try {
      const args = structuredClone(f.args);
      const codes = { protected: 'PROTECTED_BASE_MISMATCH_OR_UNAVAILABLE', missing_protected: 'PROTECTED_BASE_MISMATCH_OR_UNAVAILABLE',
        tree: 'EXPECTED_TREE_MISMATCH', head: 'EXPECTED_HEAD_MISMATCH', duplicate: 'DUPLICATE_MERGE_PARENT',
        already_contained: 'PROTECTED_BASE_ALREADY_CONTAINED' };
      if (mismatch === 'protected') args.merge.expected_protected_base_sha = 'b'.repeat(40);
      if (mismatch === 'missing_protected') await git(f.workspace, 'update-ref', '-d', 'refs/remotes/origin/master');
      if (mismatch === 'tree') args.merge.expected_tree_sha = 'c'.repeat(40);
      if (mismatch === 'head') args.expected_head_sha = 'd'.repeat(40);
      if (mismatch === 'duplicate' || mismatch === 'already_contained') {
        const base = mismatch === 'duplicate' ? f.head : (await git(f.workspace, 'rev-parse', `${f.head}^`)).stdout.trim();
        await git(f.workspace, 'update-ref', 'refs/remotes/origin/master', base);
        args.merge.expected_protected_base_sha = base;
      }
      const indexPath = (await git(f.workspace, 'rev-parse', '--git-path', 'index')).stdout.trim();
      const index = await readFile(path.resolve(f.workspace, indexPath));
      const result = await createGitPublisher(f.config).commit(args);
      assert.equal(result.effect_state, 'NOT_APPLIED');
      assert.equal(result.code, codes[mismatch]);
      assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
      assert.deepEqual(await readFile(path.resolve(f.workspace, indexPath)), index);
    } finally { await f.cleanup(); }
  });
}

test('changed protected snapshot during preparation is refused before branch mutation', async () => {
  const f = await preparedMergeFixture();
  try {
    let changed = false;
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      const result = await execFile(file, args, options);
      if (file === GIT && gitCommand(args) === 'commit-tree' && !changed) {
        changed = true;
        await git(f.workspace, 'update-ref', 'refs/remotes/origin/master', f.head);
      }
      return result;
    } });
    const result = await publisher.commit(f.args);
    assert.equal(result.code, 'PROTECTED_BASE_CHANGED_DURING_PREPARATION');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});

test('merge readback rejects a commit with the wrong parent before updating the owned branch', async () => {
  const f = await preparedMergeFixture();
  try {
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      const result = await execFile(file, args, options);
      if (file === GIT && gitCommand(args) === 'show' && args.includes('--format=%T%n%P')) {
        return { ...result, stdout: `${f.tree}\n${f.head}\n` };
      }
      return result;
    } });
    const result = await publisher.commit(f.args);
    assert.equal(result.code, 'MERGE_COMMIT_IDENTITY_MISMATCH');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});


test('publication recovery: pre-existing unjournaled action remains UNKNOWN and never becomes retry authority', async () => {
  const f = await fixture();
  try {
    const sha = (await import('node:crypto')).createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(f.operationId).update('\0').update(f.branch).update('\0').update(f.head)
      .digest('hex');
    const publisher = createGitPublisher(f.config);
    const observed = await publisher.status({operation_id:f.operationId, action_ref:sha});
    assert.equal(observed.publication_recovery.outcome, 'UNKNOWN');
    assert.equal(observed.publication_recovery.reason, 'NO_MATCHING_OR_LEGACY_RECEIPT');
    assert.equal(observed.publication_recovery.retry_allowed, false);
    assert.equal(await refsAt(f.remote), '');
  } finally { await f.cleanup(); }
});

test('publication recovery: successful exact ref is journaled, survives a new publisher instance, and never republishes', async () => {
  const f = await fixture();
  try {
    const writer = createGitPublisher(f.config);
    const out = await writer.push({operation_id:f.operationId, expected_head_sha:f.head});
    assert.equal(out.effect_state, 'APPLIED');
    assert.equal(out.receipt_recorded, true);
    const restart = createGitPublisher(f.config);
    const status = await restart.status({operation_id:f.operationId, action_ref:out.action_ref});
    assert.equal(status.publication_recovery.outcome, 'APPLIED');
    assert.equal(status.publication_recovery.stage, 'TERMINAL');
    assert.equal(status.publication_recovery.reason, 'REMOTE_EXACT_AFTER_PUSH');
    let pushes = 0;
    const replay = createGitPublisher(f.config, {execFile:async (file,args,options)=>{
      if (file===GIT && gitCommand(args)==='push') pushes++;
      return execFile(file,args,options);
    }});
    const result = await replay.push({operation_id:f.operationId, expected_head_sha:f.head});
    assert.equal(result.code, 'ALREADY_APPLIED');
    assert.equal(pushes, 0);
  } finally { await f.cleanup(); }
});

test('publication recovery: lost reply after remote update is proven APPLIED on the original destination', async () => {
  const f = await fixture();
  try {
    let injected = false;
    const writer = createGitPublisher(f.config, {execFile:async (file,args,options)=>{
      if (file===GIT && gitCommand(args)==='push' && !injected) {
        injected = true;
        await execFile(file,args,options);
        const err = new Error('simulated lost response after external effect');
        err.code = 'SIMULATED_LOSS';
        throw err;
      }
      return execFile(file,args,options);
    }});
    const out = await writer.push({operation_id:f.operationId, expected_head_sha:f.head});
    assert.equal(injected,true);
    assert.equal(out.code, 'APPLIED_AFTER_AMBIGUOUS_PUSH_RETURN');
    assert.equal(out.receipt_recorded,true);
    const restart = createGitPublisher(f.config);
    assert.equal((await restart.status({operation_id:f.operationId,action_ref:out.action_ref}))
      .publication_recovery.outcome,'APPLIED');
    assert.equal(await refsAt(f.remote), 'refs/heads/' + f.branch + ' ' + f.head);
  } finally { await f.cleanup(); }
});

test('publication recovery: ambiguous dispatch is retained and blocks unchanged retry after restart', async () => {
  const f = await fixture();
  try {
    let originalPushes = 0;
    const writer = createGitPublisher(f.config, {execFile:async (file,args,options)=>{
      if (file===GIT && gitCommand(args)==='push') {
        originalPushes++;
        throw Object.assign(new Error('lost dispatch'), {code:'SIMULATED_LOSS'});
      }
      return execFile(file,args,options);
    }});
    const out = await writer.push({operation_id:f.operationId, expected_head_sha:f.head});
    assert.equal(out.effect_state,'EFFECT_UNKNOWN');
    assert.equal(originalPushes,1);
    const recovery = await createGitPublisher(f.config).status({operation_id:f.operationId,action_ref:out.action_ref});
    assert.equal(recovery.publication_recovery.outcome,'UNKNOWN');
    assert.equal(recovery.publication_recovery.stage,'DISPATCHING');
    let replayCount = 0;
    const newProcess = createGitPublisher(f.config, {execFile:async (file,args,options)=>{
      if (file===GIT && gitCommand(args)==='push') replayCount++;
      return execFile(file,args,options);
    }});
    const second = await newProcess.push({operation_id:f.operationId, expected_head_sha:f.head});
    assert.equal(second.status,'REFUSED');
    assert.equal(second.retry_allowed,false);
    assert.equal(second.code,'UNRECONCILED_OR_DENIED_PUBLICATION');
    assert.equal(replayCount,0);
    assert.equal(await refsAt(f.remote),'');
  } finally { await f.cleanup(); }
});

test('publication recovery: prepared-before-dispatch evidence stays held while an original writer could continue', async () => {
  const f = await fixture();
  try {
    const digest = (await import('node:crypto')).createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(f.operationId).update('\0').update(f.branch).update('\0').update(f.head)
      .digest('hex');
    const {createPublicationRecovery} = await import('./git-publish.mjs');
    const recovery = await createPublicationRecovery({
      git:(cwd,args)=>git(cwd,...args), workspacePath:f.workspace,
      operationId:f.operationId, branch:f.branch, ref:'refs/heads/'+f.branch,
      remoteUrl:f.remote,
    });
    const before = await recovery.begin({actionRef:digest,intendedHead:f.head,expectedRemote:null});
    assert.equal(before.record.stage,'PREPARED');
    const read = await createGitPublisher(f.config).status({operation_id:f.operationId,action_ref:digest});
    assert.equal(read.publication_recovery.outcome,'UNKNOWN');
    assert.equal(read.publication_recovery.reason,'WRITER_MAY_STILL_DISPATCH');
    const refusal = await createGitPublisher(f.config).push({operation_id:f.operationId,expected_head_sha:f.head});
    assert.equal(refusal.status,'REFUSED');
    assert.equal(await refsAt(f.remote),'');
  } finally { await f.cleanup(); }
});

test('publication recovery: incomplete or torn terminal receipt never creates success or retry clearance', async () => {
  const f = await fixture();
  try {
    const out = await createGitPublisher(f.config).push({operation_id:f.operationId,expected_head_sha:f.head});
    assert.equal(out.effect_state,'APPLIED');
    const digest = (await import('node:crypto')).createHash('sha256')
      .update(f.operationId+'\0'+f.branch).digest('hex');
    const file = path.join(f.workspace,'.git','mastermind-studio-publication-receipts',digest,out.action_ref+'.json');
    await writeFile(file,'{"schema":"torn"}\n');
    const read = await createGitPublisher(f.config).status({operation_id:f.operationId,action_ref:out.action_ref});
    assert.equal(read.publication_recovery.outcome,'UNKNOWN');
    assert.equal(read.publication_recovery.reason,'INVALID_OR_TORN_RECEIPT');
    assert.equal(read.publication_recovery.retry_allowed,false);
  } finally { await f.cleanup(); }
});


test('publication recovery: PREPARED does not attribute an identical remote push by another writer', async () => {
  const f = await fixture();
  try {
    const {createPublicationRecovery} = await import('./git-publish.mjs');
    const actionRef = (await import('node:crypto')).createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(f.operationId).update('\0').update(f.branch).update('\0').update(f.head)
      .digest('hex');
    const journal = await createPublicationRecovery({
      git:(cwd,args)=>git(cwd,...args), workspacePath:f.workspace,
      operationId:f.operationId, branch:f.branch, ref:'refs/heads/'+f.branch,
      remoteUrl:f.remote,
    });
    const held = await journal.begin({actionRef,intendedHead:f.head,expectedRemote:null});
    assert.equal(held.record.stage,'PREPARED');
    // Separate fixture-side publisher creates precisely the intended remote tip.
    // This is NOT the operation with the held PREPARED receipt.
    await git(f.workspace,'push','origin',f.head+':refs/heads/'+f.branch);
    const status = await createGitPublisher(f.config).status({operation_id:f.operationId,action_ref:actionRef});
    assert.equal(status.remote_head_sha,f.head);
    assert.equal(status.publication_recovery.outcome,'UNKNOWN');
    assert.equal(status.publication_recovery.reason,'WRITER_MAY_STILL_DISPATCH');
    assert.equal(status.publication_recovery.retry_allowed,false);
  } finally {await f.cleanup();}
});

test('publication recovery: DISPATCHING action can be reconciled after a later valid descendant tip', async () => {
  const f = await fixture();
  try {
    const {createPublicationRecovery} = await import('./git-publish.mjs');
    const actionRef = (await import('node:crypto')).createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(f.operationId).update('\0').update(f.branch).update('\0').update(f.head)
      .digest('hex');
    const journal = await createPublicationRecovery({
      git:(cwd,args)=>git(cwd,...args), workspacePath:f.workspace,
      operationId:f.operationId, branch:f.branch, ref:'refs/heads/'+f.branch,
      remoteUrl:f.remote,
    });
    const prepared = await journal.begin({actionRef,intendedHead:f.head,expectedRemote:null});
    await journal.markDispatching(prepared.record);
    await git(f.workspace,'push','origin',f.head+':refs/heads/'+f.branch);
    await writeFile(path.join(f.workspace,'proof.txt'),'subsequent valid change\n');
    await git(f.workspace,'add','proof.txt');
    await git(f.workspace,'commit','-m','test: newer publisher');
    const newer=(await git(f.workspace,'rev-parse','HEAD')).stdout.trim();
    await git(f.workspace,'push','origin',newer+':refs/heads/'+f.branch);
    const status=await createGitPublisher(f.config).status({operation_id:f.operationId,action_ref:actionRef});
    assert.equal(status.remote_head_sha,newer);
    assert.equal(status.publication_recovery.outcome,'APPLIED');
    assert.equal(status.publication_recovery.reason,'INTENDED_HEAD_IS_REMOTE_ANCESTOR');
    assert.equal(status.publication_recovery.retry_allowed,false);
  } finally {await f.cleanup();}
});

test('publication recovery: unrelated remote branch advance is CONFLICT, not proven absence or retry clearance', async () => {
  const f = await fixture();
  try {
    const {createPublicationRecovery} = await import('./git-publish.mjs');
    const actionRef = (await import('node:crypto')).createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(f.operationId).update('\0').update(f.branch).update('\0').update(f.head)
      .digest('hex');
    const journal = await createPublicationRecovery({
      git:(cwd,args)=>git(cwd,...args), workspacePath:f.workspace,
      operationId:f.operationId, branch:f.branch, ref:'refs/heads/'+f.branch,
      remoteUrl:f.remote,
    });
    await journal.markDispatching((await journal.begin({
      actionRef,intendedHead:f.head,expectedRemote:null,
    })).record);
    // An unparented commit models a different legitimate writer's branch tip.
    const tree=(await git(f.workspace,'rev-parse','HEAD^{tree}')).stdout.trim();
    const unparented=(await git(f.workspace,'commit-tree',tree,'-m','test: separate writer')).stdout.trim();
    await git(f.workspace,'push','origin',unparented+':refs/heads/'+f.branch);
    const status=await createGitPublisher(f.config).status({operation_id:f.operationId,action_ref:actionRef});
    assert.equal(status.publication_recovery.outcome,'CONFLICT');
    assert.equal(status.publication_recovery.reason,'REMOTE_DIVERGED_TARGET_NOT_ANCESTOR');
    assert.equal(status.publication_recovery.retry_allowed,false);
    let pushes=0;
    const attempted=createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT&&gitCommand(args)==='push')pushes++;
      return execFile(file,args,options);
    }});
    const held=await attempted.push({operation_id:f.operationId,expected_head_sha:f.head});
    assert.equal(held.code,'UNRECONCILED_OR_DENIED_PUBLICATION');
    assert.equal(pushes,0);
  } finally {await f.cleanup();}
});

test('publication recovery: wrong operation and wrong origin never match a retained action', async () => {
  const f = await fixture();
  try {
    const {createPublicationRecovery} = await import('./git-publish.mjs');
    const actionRef = (await import('node:crypto')).createHash('sha256')
      .update('mastermind.studio_git_push_current_branch.v1\0')
      .update(f.operationId).update('\0').update(f.branch).update('\0').update(f.head)
      .digest('hex');
    const args={
      git:(cwd,args)=>git(cwd,...args), workspacePath:f.workspace,
      operationId:f.operationId, branch:f.branch, ref:'refs/heads/'+f.branch,
      remoteUrl:f.remote,
    };
    const journal=await createPublicationRecovery(args);
    const prepared=await journal.begin({actionRef,intendedHead:f.head,expectedRemote:null});
    assert.equal(prepared.record.stage,'PREPARED');
    const wrongOperation=await createPublicationRecovery({...args,operationId:'other-operation'});
    assert.equal((await wrongOperation.status(actionRef,null)).outcome,'UNKNOWN');
    assert.equal((await wrongOperation.status(actionRef,null)).reason,'NO_MATCHING_OR_LEGACY_RECEIPT');
    const wrongOrigin=await createPublicationRecovery({...args,remoteUrl:path.join(f.root,'forbidden.git')});
    const state=await wrongOrigin.status(actionRef,null);
    assert.equal(state.outcome,'UNKNOWN');
    assert.equal(state.reason,'INVALID_OR_TORN_RECEIPT');
    assert.equal(state.retry_allowed,false);
    const wrongBranch=await createPublicationRecovery({...args,branch:'sol/web-foreign'});
    assert.equal((await wrongBranch.status(actionRef,null)).reason,'NO_MATCHING_OR_LEGACY_RECEIPT');
  } finally {await f.cleanup();}
});


function originalPushRef(f, head) {
  return (awaitedCrypto()).createHash('sha256')
    .update('mastermind.studio_git_push_current_branch.v1\0')
    .update(f.operationId).update('\0').update(f.branch).update('\0').update(head)
    .digest('hex');
}

function awaitedCrypto() {
  return cryptoForForward;
}

const cryptoForForward = await import('node:crypto');

async function legacyForwardFixture() {
  const f = await fixture();
  await git(f.workspace, 'push', 'origin', f.head + ':refs/heads/' + f.branch);
  await writeFile(path.join(f.workspace, 'proof.txt'), 'original uncertain candidate\n');
  await git(f.workspace, 'add', 'proof.txt');
  await git(f.workspace, 'commit', '-m', 'test: old unpublished candidate');
  const originalHead = (await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim();
  await writeFile(path.join(f.workspace, 'proof.txt'), 'prepared forward candidate\n');
  await git(f.workspace, 'add', 'proof.txt');
  await git(f.workspace, 'commit', '-m', 'test: new guarded candidate');
  const candidate = (await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim();
  const recovery = {
    prior_action_ref: originalPushRef(f, originalHead),
    prior_intended_head_sha: originalHead,
    expected_remote_head_sha: f.head,
  };
  return {...f, originalHead, candidate, recovery};
}

test('forward recovery: legacy unknown publication admits one new nonforced descendant action', async () => {
  const f = await legacyForwardFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const result = await publisher.push({
      operation_id:f.operationId, expected_head_sha:f.candidate,
      recovery:f.recovery,
    });
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.receipt_recorded, true);
    assert.notEqual(result.action_ref, f.recovery.prior_action_ref);
    assert.equal(await refsAt(f.remote), 'refs/heads/' + f.branch + ' ' + f.candidate);
    const old = await publisher.status({operation_id:f.operationId,
      action_ref:f.recovery.prior_action_ref});
    assert.equal(old.publication_recovery.outcome, 'UNKNOWN');
    assert.equal(old.publication_recovery.reason, 'NO_MATCHING_OR_LEGACY_RECEIPT');
    const fresh = await publisher.status({operation_id:f.operationId,
      action_ref:result.action_ref});
    assert.equal(fresh.publication_recovery.outcome, 'APPLIED');
    assert.equal(fresh.publication_recovery.stage, 'TERMINAL');
    assert.equal(fresh.publication_recovery.retry_allowed, false);
    let pushes = 0;
    const restarted = createGitPublisher(f.config, {execFile:async(file,args,options)=>{
      if (file===GIT && gitCommand(args)==='push') pushes++;
      return execFile(file,args,options);
    }});
    const repeat = await restarted.push({operation_id:f.operationId,
      expected_head_sha:f.candidate,recovery:f.recovery});
    assert.equal(repeat.code,'ALREADY_APPLIED');
    assert.equal(pushes,0);
  } finally {await f.cleanup();}
});

test('forward recovery: malformed/wrong prior identity and widened input refuse before push', async () => {
  const f = await legacyForwardFixture();
  try {
    const publisher = createGitPublisher(f.config);
    await assert.rejects(()=>publisher.push({
      operation_id:f.operationId, expected_head_sha:f.candidate,
      recovery:{...f.recovery, force:true},
    }),/recovery arguments are invalid/);
    await assert.rejects(()=>publisher.push({
      operation_id:f.operationId, expected_head_sha:f.candidate,
      recovery:{...f.recovery, prior_action_ref:'bad'},
    }),/recovery identities are invalid/);
    const bad = await publisher.push({
      operation_id:f.operationId, expected_head_sha:f.candidate,
      recovery:{...f.recovery, prior_action_ref:'a'.repeat(64)},
    });
    assert.equal(bad.code,'RECOVERY_PRIOR_IDENTITY_MISMATCH');
    assert.equal(bad.push_attempted,false);
    assert.equal(await refsAt(f.remote), 'refs/heads/' + f.branch + ' ' + f.head);
  } finally {await f.cleanup();}
});

test('forward recovery: stale expected remote and missing ancestry are nonmutating', async () => {
  const f = await legacyForwardFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const stale = await publisher.push({
      operation_id:f.operationId, expected_head_sha:f.candidate,
      recovery:{...f.recovery, expected_remote_head_sha:f.originalHead},
    });
    assert.equal(stale.code,'RECOVERY_REMOTE_HEAD_MISMATCH');
    assert.equal(stale.push_attempted,false);
    const tree=(await git(f.workspace,'rev-parse','HEAD^{tree}')).stdout.trim();
    const alien=(await git(f.workspace,'commit-tree',tree,'-m','test: unparented prior')).stdout.trim();
    const unrelated = await publisher.push({
      operation_id:f.operationId, expected_head_sha:f.candidate,
      recovery:{...f.recovery, prior_intended_head_sha:alien,
        prior_action_ref:originalPushRef(f,alien)},
    });
    assert.equal(unrelated.code,'RECOVERY_ANCESTRY_UNVERIFIED');
    assert.equal(unrelated.push_attempted,false);
    assert.equal(await refsAt(f.remote),'refs/heads/'+f.branch+' '+f.head);
  } finally {await f.cleanup();}
});

test('forward recovery: outstanding journalled prior is not bypassed by legacy exception', async () => {
  const f = await legacyForwardFixture();
  try {
    const {createPublicationRecovery} = await import('./git-publish.mjs');
    const journal = await createPublicationRecovery({
      git:(cwd,args)=>git(cwd,...args), workspacePath:f.workspace,
      operationId:f.operationId, branch:f.branch,
      ref:'refs/heads/'+f.branch, remoteUrl:f.remote,
    });
    const held = await journal.begin({
      actionRef:f.recovery.prior_action_ref,
      intendedHead:f.originalHead, expectedRemote:f.head,
    });
    assert.equal(held.record.stage,'PREPARED');
    const result = await createGitPublisher(f.config).push({
      operation_id:f.operationId, expected_head_sha:f.candidate,recovery:f.recovery,
    });
    assert.equal(result.status,'REFUSED');
    assert.equal(result.code,'PRIOR_ACTION_HAS_DURABLE_RECEIPT');
    assert.equal(result.push_attempted,false);
    assert.equal(await refsAt(f.remote),'refs/heads/'+f.branch+' '+f.head);
  } finally {await f.cleanup();}
});

test('forward recovery: lost reply after actual update is reconciled by exact new action', async () => {
  const f = await legacyForwardFixture();
  try {
    let attempts=0;
    const publisher = createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT&&gitCommand(args)==='push') {
        attempts++;
        const settled=await execFile(file,args,options);
        assert.ok(settled);
        throw Object.assign(new Error('simulated response loss'),{code:'SIMULATED_LOSS'});
      }
      return execFile(file,args,options);
    }});
    const result = await publisher.push({
      operation_id:f.operationId,expected_head_sha:f.candidate,recovery:f.recovery,
    });
    assert.equal(attempts,1);
    assert.equal(result.code,'APPLIED_AFTER_AMBIGUOUS_PUSH_RETURN');
    assert.equal(result.effect_state,'APPLIED');
    assert.equal(await refsAt(f.remote),'refs/heads/'+f.branch+' '+f.candidate);
    const read=await createGitPublisher(f.config).status({
      operation_id:f.operationId,action_ref:result.action_ref,
    });
    assert.equal(read.publication_recovery.outcome,'APPLIED');
  } finally {await f.cleanup();}
});

test('forward recovery: competing remote update after preflight cannot overwrite history', async () => {
  const f = await legacyForwardFixture();
  try {
    let writes=0, remoteCompetitor=null;
    const publisher = createGitPublisher(f.config,{execFile:async(file,args,options)=>{
      if(file===GIT&&gitCommand(args)==='push'&&writes===0) {
        writes++;
        const tree=(await git(f.workspace,'rev-parse','HEAD^{tree}')).stdout.trim();
        remoteCompetitor=(await git(f.workspace,'commit-tree',tree,'-p',f.head,
          '-m','test: competing sibling')).stdout.trim();
        await git(f.workspace,'push','origin',
          remoteCompetitor+':refs/heads/'+f.branch);
      }
      return execFile(file,args,options);
    }});
    const result = await publisher.push({
      operation_id:f.operationId,expected_head_sha:f.candidate,recovery:f.recovery,
    });
    assert.equal(writes,1);
    assert.ok(['EFFECT_UNKNOWN','NOT_APPLIED'].includes(result.effect_state));
    assert.equal(await refsAt(f.remote),'refs/heads/'+f.branch+' '+remoteCompetitor);
  } finally {await f.cleanup();}
});

// ---------------------------------------------------------------------------
// Bounded index-lock recovery.
//
// The publisher under test is the shipped one. Every fixture is an inert
// temporary Git workspace with a local bare remote: no real Macro workspace,
// index or lock is touched, and no network, push, credential or protected
// ref is involved.
// ---------------------------------------------------------------------------

const EMPTY_CONTENT_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
const RECOVERY_RECEIPT_ROOT = 'mastermind-studio-publication-receipts';
const RECOVERY_IDENTITY_DIR = 'index-recovery';

function recoveryIdentity(operationId, branch) {
  return createHash('sha256').update(operationId + '\0' + branch).digest('hex');
}

async function sha256OfFile(file) {
  return createHash('sha256').update(await readFile(file)).digest('hex');
}

async function lockIdentityOf(lockPath) {
  const stats = await lstat(lockPath, { bigint: true });
  if (!stats.isFile()) {
    return {
      device: stats.dev.toString(),
      inode: stats.ino.toString(),
      file_type: stats.isSymbolicLink() ? 'SYMLINK' : (stats.isDirectory() ? 'DIRECTORY' : 'OTHER'),
      uid: stats.uid.toString(),
      gid: stats.gid.toString(),
      mode: (stats.mode & 0o7777n).toString(8).padStart(4, '0'),
      size: stats.size.toString(),
      mtime_ns: stats.mtimeNs.toString(),
      content_sha256: EMPTY_CONTENT_SHA256,
    };
  }
  const content = await readFile(lockPath);
  return {
    device: stats.dev.toString(),
    inode: stats.ino.toString(),
    file_type: 'REGULAR',
    uid: stats.uid.toString(),
    gid: stats.gid.toString(),
    mode: (stats.mode & 0o7777n).toString(8).padStart(4, '0'),
    size: stats.size.toString(),
    mtime_ns: stats.mtimeNs.toString(),
    content_sha256: createHash('sha256').update(content).digest('hex'),
  };
}

async function recoveryFixture(options = {}) {
  const f = await fixture(options);
  const indexPath = path.join(f.workspace, '.git', 'index');
  const lockPath = indexPath + '.lock';
  if (options.lockKind === 'symlink') {
    await writeFile(path.join(f.root, 'target'), 'x');
    await symlink(path.join(f.root, 'target'), lockPath);
  } else if (options.lockKind === 'directory') {
    await mkdir(lockPath, { recursive: true });
  } else {
    await writeFile(lockPath, options.lockBytes ?? Buffer.alloc(0), { mode: options.lockMode ?? 0o600 });
  }
  const { stdout: treeOut } = await git(f.workspace, 'rev-parse', 'HEAD^{tree}');
  const tree = treeOut.trim();
  const indexSha256 = await sha256OfFile(indexPath);
  const identity = recoveryIdentity(f.operationId, f.branch);
  const receiptDir = path.join(f.workspace, '.git', RECOVERY_RECEIPT_ROOT, RECOVERY_IDENTITY_DIR, identity);
  const quarantineDir = path.join(receiptDir, 'quarantine');
  let lock = null;
  try { lock = await lockIdentityOf(lockPath); } catch { lock = null; }
  return {
    ...f,
    indexPath,
    lockPath,
    tree,
    indexSha256,
    identity,
    lock,
    receiptDir,
    quarantineDir,
    async lockIdentity() {
      try { return await lockIdentityOf(lockPath); } catch (error) {
        if (error.code === 'ENOENT') return null;
        throw error;
      }
    },
    async fences(overrides = {}) {
      const currentIndexSha256 = await sha256OfFile(indexPath);
      const { stdout: currentTreeOut } = await git(f.workspace, 'rev-parse', 'HEAD^{tree}');
      const recovery = {
        mode: overrides.mode ?? 'APPLY',
        expected_tree_sha: overrides.expected_tree_sha ?? currentTreeOut.trim(),
        expected_index_sha256: overrides.expected_index_sha256 ?? currentIndexSha256,
        lock: overrides.lock === null ? null : { ...lock, ...(overrides.lock ?? {}) },
        custody: overrides.custody ?? {
          maintenance_window: 'psl-c4-maintenance-window-1',
          pending_mutators_retired: true,
        },
      };
      if (overrides.action_ref !== undefined) recovery.action_ref = overrides.action_ref;
      const args = {
        operation_id: overrides.operation_id ?? f.operationId,
        expected_head_sha: overrides.expected_head_sha ?? f.head,
        index_recovery: recovery,
      };
      if (overrides.with_message) args.message = 'test: mixed variant must refuse';
      if (overrides.with_merge) {
        args.merge = { expected_protected_base_sha: 'b'.repeat(40), expected_tree_sha: 'c'.repeat(40) };
      }
      return args;
    },
    async cleanup() {
      await chmod(receiptDir, 0o700).catch(() => {});
      await rm(f.root, { recursive: true, force: true });
    },
    quarantineFile(actionRef) {
      return path.join(quarantineDir, actionRef, 'index.lock');
    },
  };
}

test('index recovery preview reads the current state back and writes nothing', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit(await f.fences({ mode: 'PREVIEW' }));
    assert.equal(result.schema, 'mastermind.studio_git_index_recovery_result.v1');
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'INDEX_RECOVERY_PREVIEW');
    assert.equal(result.disposition, 'REVIEW_ONLY');
    assert.equal(result.commit_created, false);
    assert.equal(result.historical_origin, 'UNKNOWN');
    assert.equal(result.unchanged_head.head_unchanged, true);
    assert.equal(result.unchanged_head.index_unchanged, true);
    assert.equal(result.unchanged_head.index_matches_head_tree, true);
    assert.equal(result.unchanged_head.working_state_unchanged, true);
    assert.equal(result.detail.plan.action_ref, result.action_ref);
    assert.equal(result.detail.plan.writes_index, false);
    assert.equal(result.detail.plan.creates_commit, false);
    assert.equal(result.detail.plan.updates_ref, false);
    assert.equal(result.detail.plan.contacts_remote, false);
    assert.equal(result.custody.evidence_source, 'CALLER_DECLARED');
    assert.equal(result.custody.writer_exclusion, 'NOT_MACHINE_PROVEN');
    // The lock is untouched and no receipt, quarantine or commit exists.
    assert.equal((await f.lockIdentity()).inode, (await lockIdentityOf(f.lockPath)).inode);
    await assert.rejects(lstat(f.receiptDir), (error) => error.code === 'ENOENT');
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    assert.equal((await git(f.workspace, 'status', '--porcelain')).stdout, '');
  } finally { await f.cleanup(); }
});

test('recovery inventory streaming preserves every byte beyond the ordinary 1 MiB buffer', async () => {
  const f = await recoveryFixture();
  try {
    const inventories = [
      ['ls-files', '--stage', '-z'], ['ls-files', '-v', '-z'],
      ['diff-files', '--name-status', '-z'],
      ['ls-files', '--others', '--exclude-standard', '-z'],
    ];
    const fields = ['staged_state_sha256', 'sparse_state_sha256',
      'dirty_state_sha256', 'untracked_state_sha256'];
    const count = 2 * 1024 * 1024 + 17;
    const program = `const {writeSync}=require('node:fs');
      const n=Number(process.argv[1]), salt=Number(process.argv[2]);
      const block=Buffer.from(Array.from({length:65536},(_,i)=>(i+salt)%256));
      for(let done=0;done<n;) done+=writeSync(1,block,0,Math.min(block.length,n-done));`;
    // The old capture rejects these same bytes, including NUL/non-UTF8 data.
    await assert.rejects(execFile(process.execPath, ['-e', program, String(count), '0'],
      {maxBuffer: 1024 * 1024, encoding: 'buffer'}),
    error => error.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER');
    const seen = new Set();
    const publisher = createGitPublisher(f.config, {spawn: (file, args, options) => {
      const index = inventories.findIndex(value => JSON.stringify(value) === JSON.stringify(args));
      assert.equal(file, GIT);
      assert.ok(index >= 0, 'only the four fixed inventories may use streaming');
      assert.equal(options.env.GIT_OPTIONAL_LOCKS, '0');
      assert.equal(options.env.GIT_TERMINAL_PROMPT, '0');
      assert.equal(options.shell, false);
      assert.deepEqual(options.stdio, ['ignore', 'pipe', 'pipe']);
      seen.add(index);
      return spawn(process.execPath, ['-e', program, String(count), String(index)], options);
    }});
    const result = await publisher.commit(await f.fences({mode: 'PREVIEW'}));
    assert.equal(result.code, 'INDEX_RECOVERY_PREVIEW');
    assert.equal(seen.size, 4);
    for (let i = 0; i < 4; i++) {
      const complete = Buffer.from(Array.from({length: count}, (_,j) => (j+i)%256));
      assert.equal(result.unchanged_head[fields[i]],
        createHash('sha256').update(complete).digest('hex'));
      assert.notEqual(result.unchanged_head[fields[i]],
        createHash('sha256').update(complete.subarray(0, 1024 * 1024)).digest('hex'));
    }
    assert.equal(await sha256OfFile(f.indexPath), f.indexSha256);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.receiptDir), false);
  } finally { await f.cleanup(); }
});

test('recovery inventory streaming handles a real Git index exceeding both ordinary inventory buffers', async () => {
  const f = await recoveryFixture({largeIndex: true});
  try {
    const expected = {};
    for (const [flag, field] of [['--stage', 'staged_state_sha256'], ['-v', 'sparse_state_sha256']]) {
      await assert.rejects(run(GIT, ['ls-files', flag, '-z'],
        {cwd: f.workspace, encoding: 'buffer'}),
      error => error.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER');
      const complete = (await run(GIT, ['ls-files', flag, '-z'],
        {cwd: f.workspace, encoding: 'buffer', maxBuffer: 8 * 1024 * 1024})).stdout;
      assert.ok(complete.length > 1024 * 1024);
      expected[field] = createHash('sha256').update(complete).digest('hex');
    }
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit(await f.fences({mode: 'PREVIEW'}));
    assert.equal(result.code, 'INDEX_RECOVERY_PREVIEW');
    for (const [key, digest] of Object.entries(expected)) assert.equal(result.unchanged_head[key], digest);
    assert.equal(await sha256OfFile(f.indexPath), f.indexSha256);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD^{tree}')).stdout.trim(), f.tree);
    assert.equal(await pathExists(f.receiptDir), false);
  } finally { await f.cleanup(); }
});

test('recovery inventory streaming accepts exactly the byte ceiling and remains tail-sensitive', async () => {
  const f = await recoveryFixture();
  try {
    const block = Buffer.alloc(65536, 37);
    const expected = createHash('sha256');
    for (let i = 0; i < 1024; i++) expected.update(block);
    const publisher = createGitPublisher(f.config, {spawn: (file, args, options) => {
      if (!args.includes('--stage')) return spawn(file, args, options);
      return spawn(process.execPath, ['-e',
        `const {writeSync}=require('node:fs'); const b=Buffer.alloc(65536,37);
         for(let n=0;n<1024;n++) writeSync(1,b);`], options);
    }});
    const result = await publisher.commit(await f.fences({mode: 'PREVIEW'}));
    assert.equal(result.code, 'INDEX_RECOVERY_PREVIEW');
    assert.equal(result.unchanged_head.staged_state_sha256, expected.digest('hex'));
    const changed = createGitPublisher(f.config, {spawn: (file, args, options) => {
      if (!args.includes('--stage')) return spawn(file, args, options);
      return spawn(process.execPath, ['-e',
        `const {writeSync}=require('node:fs'); const b=Buffer.alloc(65536,37);
         for(let n=0;n<1023;n++) writeSync(1,b); b[b.length-1]=38; writeSync(1,b);`], options);
    }});
    const tail = await changed.commit(await f.fences({mode: 'PREVIEW'}));
    assert.equal(tail.code, 'INDEX_RECOVERY_PREVIEW');
    assert.notEqual(tail.unchanged_head.staged_state_sha256, result.unchanged_head.staged_state_sha256);
  } finally { await f.cleanup(); }
});

for (const kind of ['stdout-limit', 'stderr-limit', 'timeout', 'nonzero', 'spawn-error']) {
  test(`recovery inventory streaming refuses ${kind} without a partial fingerprint or effect`, async () => {
    const f = await recoveryFixture();
    try {
      let closed;
      let child;
      const programs = {
        'stdout-limit': `const {writeSync}=require('node:fs'); const b=Buffer.alloc(65536);
          for(let n=0;n<1024;n++) writeSync(1,b); writeSync(1,Buffer.from([0])); setInterval(()=>{},1000);`,
        'stderr-limit': `const {writeSync}=require('node:fs'); const b=Buffer.alloc(65536);
          for(let n=0;n<17;n++) writeSync(2,b); setInterval(()=>{},1000);`,
        timeout: `process.stdout.write('partial\\0'); setInterval(()=>{},1000);`,
        nonzero: `process.stdout.write('partial\\0',()=>process.exit(7));`,
      };
      const publisher = createGitPublisher({...f.config, commandTimeoutMs: 1000}, {
        spawn: (file, args, options) => {
          if (!args.includes('--stage')) return spawn(file, args, options);
          child = kind === 'spawn-error'
            ? spawn(path.join(f.root, 'missing-executable'), [], options)
            : spawn(process.execPath, ['-e', programs[kind]], options);
          closed = new Promise(resolve => child.once('close', (code, signal) => resolve({code, signal})));
          return child;
        },
      });
      const result = await publisher.commit(await f.fences({mode: 'PREVIEW'}));
      assert.equal(result.effect_state, 'NOT_APPLIED');
      assert.equal(result.code, 'INDEX_RECOVERY_STATE_UNAVAILABLE');
      assert.equal(result.receipt_recorded, false);
      assert.equal(result.unchanged_head.staged_state_sha256, null);
      const terminal = await closed;
      if (['stdout-limit', 'stderr-limit', 'timeout'].includes(kind)) {
        assert.equal(terminal.signal, 'SIGKILL');
        assert.equal(child.killed, true);
      }
      if (kind === 'nonzero') assert.equal(terminal.code, 7);
      assert.equal(await sha256OfFile(f.indexPath), f.indexSha256);
      assert.equal((await f.lockIdentity()).inode, f.lock.inode);
      assert.equal(await pathExists(f.receiptDir), false);
    } finally { await f.cleanup(); }
  });
}

for (const killFailure of ['returns-false', 'throws']) {
  test(`recovery inventory streaming settles cleanup uncertainty when kill ${killFailure} and close never arrives`,
    {timeout: 6000}, async () => {
      const f = await recoveryFixture();
      try {
        let reader;
        let attempted = 0;
        const publisher = createGitPublisher({...f.config, commandTimeoutMs: 1000}, {
          spawn: (file, args, options) => {
            if (!args.includes('--stage')) return spawn(file, args, options);
            // Inert event source: deliberately no real child and no close.
            reader = new EventEmitter();
            reader.stdout = new PassThrough();
            reader.stderr = new PassThrough();
            reader.kill = signal => {
              attempted += 1;
              assert.equal(signal, 'SIGKILL');
              if (killFailure === 'throws') throw new Error('kill unavailable');
              return false;
            };
            queueMicrotask(() => reader.stdout.write(Buffer.from('partial\0')));
            return reader;
          },
        });
        const result = await publisher.commit(await f.fences({mode: 'PREVIEW'}));
        assert.equal(attempted, 1);
        assert.equal(result.code, 'INDEX_RECOVERY_STATE_UNAVAILABLE');
        assert.equal(result.effect_state, 'NOT_APPLIED');
        assert.equal(result.receipt_recorded, false);
        assert.equal(result.unchanged_head.staged_state_sha256, null);
        assert.equal(reader.stdout.destroyed, true);
        assert.equal(reader.stderr.destroyed, true);
        assert.equal((await f.lockIdentity()).inode, f.lock.inode);
        assert.equal(await pathExists(f.receiptDir), false);
      } finally { await f.cleanup(); }
    });
}

test('index recovery quarantines exactly the fenced orphan lock and leaves the index and source unchanged', async () => {
  const f = await recoveryFixture();
  try {
    const commands = [];
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT) commands.push(gitCommand(args));
      return execFile(file, args, options);
    } });
    const before = await readFile(f.indexPath);
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'INDEX_RECOVERY_APPLIED');
    assert.equal(result.disposition, 'QUARANTINED');
    assert.equal(result.commit_created, false);
    assert.equal(result.historical_origin, 'UNKNOWN');
    assert.equal(result.retry_allowed, false);
    assert.equal(result.unchanged_head.head_unchanged, true);
    assert.equal(result.unchanged_head.tree_unchanged, true);
    assert.equal(result.unchanged_head.index_unchanged, true);
    assert.equal(result.unchanged_head.index_matches_head_tree, true);
    assert.equal(result.unchanged_head.working_state_unchanged, true);
    assert.equal(result.unchanged_head.clean, true);
    // The exact lock is preserved: same inode, same metadata, still empty.
    const quarantineFile = f.quarantineFile(result.action_ref);
    const quarantined = await lstat(quarantineFile, { bigint: true });
    assert.equal(quarantined.ino.toString(), f.lock.inode);
    assert.equal(quarantined.dev.toString(), f.lock.device);
    assert.equal(quarantined.size, 0n);
    assert.equal(result.quarantined_lock.inode, f.lock.inode);
    assert.equal(result.quarantined_lock.content_sha256, EMPTY_CONTENT_SHA256);
    assert.equal(result.quarantined_lock.retained, true);
    // The lock path is released and the real index bytes are untouched.
    await assert.rejects(lstat(f.lockPath), (error) => error.code === 'ENOENT');
    assert.deepEqual(await readFile(f.indexPath), before);
    assert.equal(await sha256OfFile(f.indexPath), f.indexSha256);
    // No commit, no ref update, no push, no index rewrite.
    for (const forbidden of ['commit', 'commit-tree', 'update-ref', 'push', 'fetch', 'ls-remote',
      'write-tree', 'read-tree', 'reset', 'checkout', 'add', 'rm']) {
      assert.equal(commands.includes(forbidden), false, `recovery must not run ${forbidden}`);
    }
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    assert.equal((await git(f.workspace, 'status', '--porcelain')).stdout, '');
    assert.equal((await git(f.workspace, 'rev-list', '--count', 'HEAD')).stdout.trim(), '1');
    // The retained receipt records the action and keeps the origin UNKNOWN.
    const receiptDir = path.join(f.receiptDir);
    const entries = await readdir(receiptDir);
    assert.deepEqual(entries.filter((name) => name.endsWith('.json')), [result.action_ref + '.json']);
    const receipt = JSON.parse(await readFile(path.join(receiptDir, result.action_ref + '.json'), 'utf8'));
    assert.equal(receipt.stage, 'TERMINAL');
    assert.equal(receipt.terminal_outcome, 'APPLIED');
    assert.equal(receipt.historical_origin, 'UNKNOWN');
    assert.equal(receipt.intended_head_sha, f.head);
    assert.equal(receipt.intended_tree_sha, f.tree);
    assert.equal(receipt.intended_index_sha256, f.indexSha256);
  } finally { await f.cleanup(); }
});

test('index recovery preserves the dirty working state exactly and refuses a staged index', async () => {
  const f = await recoveryFixture();
  try {
    await writeFile(path.join(f.workspace, 'proof.txt'), 'dirty\n');
    const publisher = createGitPublisher(f.config);
    const before = (await git(f.workspace, 'status', '--porcelain')).stdout;
    const result = await publisher.commit(await f.fences());
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.unchanged_head.working_state_unchanged, true);
    assert.equal(result.unchanged_head.clean, false);
    assert.equal((await git(f.workspace, 'status', '--porcelain')).stdout, before);
    assert.equal((await readFile(path.join(f.workspace, 'proof.txt'), 'utf8')), 'dirty\n');
  } finally { await f.cleanup(); }
});

test('index recovery refuses a staged index that no longer equals the admitted HEAD tree', async () => {
  const f = await recoveryFixture();
  try {
    // The orphan lock is exactly what stops Git from writing the index, so the
    // staged state is produced first and the orphan lock is then reproduced.
    await rm(f.lockPath);
    await writeFile(path.join(f.workspace, 'proof.txt'), 'staged\n');
    await git(f.workspace, 'add', 'proof.txt');
    await writeFile(f.lockPath, Buffer.alloc(0), { mode: 0o600 });
    const before = (await git(f.workspace, 'status', '--porcelain')).stdout;
    const result = await publisher_commit(f, await f.fences({ lock: await lockIdentityOf(f.lockPath) }));
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'INDEX_TREE_MISMATCH');
    assert.equal(result.commit_created, false);
    assert.equal((await git(f.workspace, 'status', '--porcelain')).stdout, before);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    // The staged state is preserved and the lock is left exactly where it was.
    assert.equal((await lstat(f.lockPath)).size, 0);
    assert.equal((await git(f.workspace, 'diff', '--cached', '--name-only')).stdout.trim(), 'proof.txt');
  } finally { await f.cleanup(); }
});

async function publisher_commit(f, args) {
  return await createGitPublisher(f.config).commit(args);
}

for (const [label, overrides, code] of [
  ['a stale HEAD fence', { expected_head_sha: 'a'.repeat(40) }, 'EXPECTED_HEAD_MISMATCH'],
  ['a stale tree fence', { expected_tree_sha: 'b'.repeat(40) }, 'EXPECTED_TREE_MISMATCH'],
  ['a stale index digest fence', { expected_index_sha256: 'c'.repeat(64) }, 'INDEX_BYTES_MISMATCH'],
  ['a stale lock identity fence', { lock: { inode: '999999' } }, 'LOCK_IDENTITY_MISMATCH'],
]) {
  test(`index recovery refuses ${label} before any effect`, async () => {
    const f = await recoveryFixture();
    try {
      const result = await publisher_commit(f, await f.fences(overrides));
      assert.equal(result.status, 'REFUSED');
      assert.equal(result.effect_state, 'NOT_APPLIED');
      assert.equal(result.code, code);
      assert.equal(result.commit_created, false);
      assert.equal(result.disposition, 'REFUSED');
      // The lock, the index and the ref are all untouched.
      assert.equal((await f.lockIdentity()).inode, f.lock.inode);
      assert.equal(await sha256OfFile(f.indexPath), f.indexSha256);
      assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
      await assert.rejects(lstat(f.receiptDir), (error) => error.code === 'ENOENT');
    } finally { await f.cleanup(); }
  });
}

for (const [label, options, code] of [
  ['a symlinked lock', { lockKind: 'symlink' }, 'LOCK_NOT_REGULAR'],
  ['a non-regular lock', { lockKind: 'directory' }, 'LOCK_NOT_REGULAR'],
  ['a non-empty lock', { lockBytes: Buffer.from('held') }, 'LOCK_NOT_EMPTY'],
  ['a lock with a different permission mode', { lockMode: 0o644 }, 'LOCK_IDENTITY_MISMATCH'],
]) {
  test(`index recovery refuses ${label} before any effect`, async () => {
    const f = await recoveryFixture(options);
    try {
      const overrides = label.includes('permission mode')
        ? { lock: { mode: f.lock.mode === '0600' ? '0644' : '0600' } }
        : {};
      const result = await publisher_commit(f, await f.fences(overrides));
      assert.equal(result.status, 'REFUSED');
      assert.equal(result.effect_state, 'NOT_APPLIED');
      assert.equal(result.code, code);
      assert.equal(result.commit_created, false);
      assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
      await assert.rejects(lstat(f.receiptDir), (error) => error.code === 'ENOENT');
    } finally { await f.cleanup(); }
  });
}

test('index recovery refuses a lock owned by another user before any effect', async () => {
  const f = await recoveryFixture();
  try {
    const foreignUid = String(Number(f.lock.uid) + 1);
    let injected = 0;
    const publisher = createGitPublisher(f.config, { lstat: async (target, options) => {
      const stats = await lstat(target, options);
      if (target !== f.lockPath || !options?.bigint) return stats;
      injected += 1;
      return new Proxy(stats, { get: (target, property) =>
        property === 'uid' ? BigInt(foreignUid) : Reflect.get(target, property) });
    } });
    const result = await publisher.commit(await f.fences());
    assert.ok(injected > 0, 'the intended exact-path fault hook must execute');
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'LOCK_NOT_OWNED_BY_CURRENT_USER');
    assert.equal(result.commit_created, false);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});

test('index recovery refuses an occupied quarantine destination without touching the lock', async () => {
  const f = await recoveryFixture();
  try {
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    assert.equal(preview.status, 'OK');
    await mkdir(f.quarantineFile(preview.action_ref).replace(/\/index\.lock$/, ''), { recursive: true });
    const result = await publisher_commit(f, await f.fences());
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'QUARANTINE_DESTINATION_OCCUPIED');
    assert.equal(result.commit_created, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});

test('index recovery reconciles the same action without a second move', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const args = await f.fences();
    const applied = await publisher.commit(args);
    assert.equal(applied.effect_state, 'APPLIED');
    const quarantineFile = f.quarantineFile(applied.action_ref);
    const quarantined = await lstat(quarantineFile, { bigint: true });
    // The same action, re-issued, returns the recorded disposition.
    const again = await publisher.commit(await f.fences());
    assert.equal(again.action_ref, applied.action_ref);
    assert.equal(again.effect_state, 'APPLIED');
    assert.equal(again.code, 'INDEX_RECOVERY_APPLIED');
    assert.equal(again.commit_created, false);
    // Exactly one preserved lock, same inode, and no second quarantine.
    const entries = await readdir(path.join(f.quarantineDir, applied.action_ref));
    assert.deepEqual(entries, ['index.lock']);
    assert.equal((await lstat(quarantineFile, { bigint: true })).ino, quarantined.ino);
    await assert.rejects(lstat(f.lockPath), (error) => error.code === 'ENOENT');
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});

test('index recovery reconcile reports the recorded action and never moves a lock', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const applied = await publisher.commit(await f.fences());
    const reconciled = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: applied.action_ref },
    });
    assert.equal(reconciled.action_ref, applied.action_ref);
    assert.equal(reconciled.effect_state, 'APPLIED');
    assert.equal(reconciled.code, 'INDEX_RECOVERY_APPLIED');
    assert.equal(reconciled.commit_created, false);
    const entries = await readdir(path.join(f.quarantineDir, applied.action_ref));
    assert.deepEqual(entries, ['index.lock']);
  } finally { await f.cleanup(); }
});

test('index recovery reconcile never claims an effect for an action with no retained record', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: 'd'.repeat(64) },
    });
    // The absence of a retained record is not proof that the action never ran
    // and not proof of a terminal absence. The original uncertainty is kept.
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'INDEX_RECOVERY_NO_RETAINED_RECORD');
    assert.equal(result.action_ref, 'd'.repeat(64));
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    assert.equal(result.historical_origin, 'UNKNOWN');
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
  } finally { await f.cleanup(); }
});

test('a lost callback after the quarantine reconciles to the proven quarantine without a second move', async () => {
  const f = await recoveryFixture();
  try {
    // The retained receipt directory is made read-only during the boundary
    // revalidation, so the terminal record write cannot land. The published
    // effect is proven and the caller loses the result publication.
    let trees = 0;
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      const result = await execFile(file, args, options);
      if (file === GIT && args.includes('HEAD^{tree}')) {
        trees += 1;
        if (trees === 3) await chmod(f.receiptDir, 0o500).catch(() => {});
      }
      return result;
    } });
    const applied = await publisher.commit(await f.fences());
    assert.equal(applied.effect_state, 'APPLIED');
    assert.equal(applied.receipt_recorded, false);
    const quarantineFile = f.quarantineFile(applied.action_ref);
    const quarantined = await lstat(quarantineFile, { bigint: true });
    // The same action reconciles to the proven quarantine.
    await chmod(f.receiptDir, 0o700);
    const reconciled = await createGitPublisher(f.config).commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: applied.action_ref },
    });
    assert.equal(reconciled.effect_state, 'APPLIED');
    assert.equal(reconciled.code, 'INDEX_RECOVERY_APPLIED');
    assert.equal(reconciled.quarantined_lock.inode, quarantined.ino.toString());
    const entries = await readdir(path.join(f.quarantineDir, applied.action_ref));
    assert.deepEqual(entries, ['index.lock'], 'reconcile must never move the lock a second time');
  } finally { await f.cleanup(); }
});

test('a lost callback before the quarantine reconciles to an unknown effect and moves nothing', async () => {
  const f = await recoveryFixture();
  try {
    // The boundary revalidation fails after the intent was durably recorded.
    // The terminal record cannot land, so the record stays non-terminal and
    // the lock is still exactly where it was.
    let trees = 0;
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT && args.includes('HEAD^{tree}')) {
        trees += 1;
        if (trees === 2) {
          await chmod(f.receiptDir, 0o500).catch(() => {});
          throw new Error('simulated boundary readback failure');
        }
      }
      return execFile(file, args, options);
    } });
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'INDEX_RECOVERY_BOUNDARY_READBACK_FAILED');
    assert.equal(result.receipt_recorded, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    await chmod(f.receiptDir, 0o700);
    // Reconciling the same action reports that the original effect is
    // unresolved. The recorded intent may still be live, so the current
    // observation never proves that the effect did not happen.
    const reconciled = await createGitPublisher(f.config).commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: result.action_ref },
    });
    assert.equal(reconciled.status, 'UNKNOWN');
    assert.equal(reconciled.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(reconciled.code, 'INDEX_RECOVERY_ORIGINAL_ACTION_MAY_BE_LIVE');
    assert.equal(reconciled.action_ref, result.action_ref);
    assert.equal(reconciled.commit_created, false);
    assert.equal(reconciled.retry_allowed, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
  } finally { await f.cleanup(); }
});

test('a post-effect readback failure is a structured unknown, never a thrown or NOT_APPLIED result', async () => {
  const f = await recoveryFixture();
  try {
    let trees = 0;
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT && args.includes('HEAD^{tree}')) {
        trees += 1;
        // The readback after the quarantine fails.
        if (trees === 3) throw new Error('simulated post-effect readback failure');
      }
      return execFile(file, args, options);
    } });
    const result = await publisher.commit(await f.fences());
    assert.equal(result.schema, 'mastermind.studio_git_index_recovery_result.v1');
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    assert.equal(result.quarantined_lock.present, true);
    assert.equal(result.quarantined_lock.inode, f.lock.inode);
  } finally { await f.cleanup(); }
});

test('a replacement active lock after the quarantine is never deleted and stays unknown', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config, {
      lstat: async (target, options) => {
        const stats = await lstat(target, options);
        // A different writer takes the index lock path the moment the
        // quarantine is observed, that is, after the move already happened.
        if (target.includes('/quarantine/') && target.endsWith('/index.lock')) {
          await writeFile(f.lockPath, Buffer.alloc(0), { mode: 0o600 });
        }
        return stats;
      },
    });
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'INDEX_RECOVERY_REPLACEMENT_LOCK_PRESENT');
    assert.equal(result.commit_created, false);
    // The replacement lock is preserved, not removed, and never restored over.
    assert.ok(await lstat(f.lockPath));
    assert.equal((await lstat(f.lockPath)).size, 0);
    assert.notEqual((await lockIdentityOf(f.lockPath)).inode, f.lock.inode);
    // The original lock is still preserved at the quarantine.
    assert.equal((await lstat(f.quarantineFile(result.action_ref), { bigint: true })).ino.toString(), f.lock.inode);
  } finally { await f.cleanup(); }
});

test('index recovery refuses null, incomplete and mixed variants before any effect', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    for (const args of [
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: null },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: {} },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'APPLY' } },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'PREVIEW', unexpected: true } },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'RECONCILE' } },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'RECONCILE', action_ref: 'x' } },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'RECONCILE', action_ref: 'a'.repeat(64), lock: {} } },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'APPLY', ...(await f.fences()).index_recovery, message: 'x' } },
      { operation_id: f.operationId, expected_head_sha: f.head, index_recovery: { mode: 'APPLY', ...(await f.fences()).index_recovery, merge: {} } },
    ]) {
      await assert.rejects(publisher.commit(args), TypeError);
    }
    // A mixed ordinary commit and recovery variant refuses as well.
    await assert.rejects(publisher.commit(await f.fences({ with_message: true })), /index_recovery forbids message and merge/);
    await assert.rejects(publisher.commit(await f.fences({ with_merge: true })), /index_recovery forbids message and merge/);
    // Nothing ran.
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    await assert.rejects(lstat(f.receiptDir), (error) => error.code === 'ENOENT');
  } finally { await f.cleanup(); }
});

test('an ordinary commit still refuses to carry an index recovery object', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    await assert.rejects(publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      message: 'test: ordinary commit',
      index_recovery: { mode: 'PREVIEW' },
    }), /index_recovery forbids message and merge/);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});

// ---------------------------------------------------------------------------
// Corrective regressions for the bounded index-recovery effect truth.
//
// Every fixture is an inert temporary Git workspace with a local bare remote:
// no real Macro workspace, index or lock is touched, and no network, push,
// credential or protected ref is involved. The retained receipts are written
// only inside the fixture's own private Git directory.
// ---------------------------------------------------------------------------

async function pathExists(target) {
  try { await lstat(target); return true; } catch { return false; }
}

// The retained receipt wire format, re-derived by the test so that a
// deliberately foreign or tampered record still carries a valid integrity
// hash. A valid hash alone must never admit a record.
function recoveryWire(value) {
  const body = {...value};
  const integrity = createHash('sha256').update(JSON.stringify(body)).digest('hex');
  return JSON.stringify({...body, integrity_sha256: integrity}) + '\n';
}

// A complete, owner-bound record for the current action. It is the base of
// the foreign and tampered variants below.
function recoveryRecordFor(f, actionRef, overrides = {}) {
  return {
    schema: 'mastermind.studio_git_index_recovery_receipt.v1',
    kind: 'INDEX_RECOVERY',
    operation_id: f.operationId,
    branch: f.branch,
    action_ref: actionRef,
    intended_head_sha: f.head,
    intended_tree_sha: f.tree,
    intended_index_sha256: f.indexSha256,
    lock_identity: f.lock,
    custody: {
      maintenance_window: 'psl-c4-maintenance-window-1',
      pending_mutators_retired: true,
    },
    historical_origin: 'UNKNOWN',
    entry_state: {
      head: f.head,
      tree: f.tree,
      indexSha256: f.indexSha256,
      indexMatchesHead: true,
      stagedStateSha256: 'a'.repeat(64),
      sparseStateSha256: 'b'.repeat(64),
      dirtyStateSha256: 'c'.repeat(64),
      untrackedStateSha256: 'd'.repeat(64),
    },
    stage: 'DISPATCHING',
    generation_id: 'test:retained',
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

// ---- defect 1: post-effect errors never escape as a refusal ----------------

test('a post-effect quarantine read failure is a structured unknown, never a thrown or false refusal', async () => {
  const f = await recoveryFixture();
  try {
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    const quarantineFile = f.quarantineFile(preview.action_ref);
    // The quarantine read fails only once the move really happened: the
    // destination exists only after the rename.
    let injected = 0;
    const publisher = createGitPublisher(f.config, { lstat: async (target, options) => {
      if (target === quarantineFile && await pathExists(quarantineFile)) {
        injected += 1;
        throw Object.assign(new Error('simulated quarantine lstat failure'), {code: 'EIO'});
      }
      return lstat(target, options);
    } });
    const result = await publisher.commit(await f.fences());
    assert.ok(injected > 0, 'the intended exact-path fault hook must execute');
    assert.equal(result.schema, 'mastermind.studio_git_index_recovery_result.v1');
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.action_ref, preview.action_ref);
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    assert.equal(result.historical_origin, 'UNKNOWN');
    // The diagnostic read could not be made. That is reported as
    // unavailable, never as an absence and never as a retained lock.
    assert.equal(result.quarantined_lock.present, null);
    assert.equal(result.quarantined_lock.retained, null);
    assert.equal(result.quarantined_lock.observation, 'UNAVAILABLE');
    // The lock really moved: it is at the quarantine and not at the lock path.
    assert.equal(await pathExists(f.lockPath), false);
    assert.equal(await pathExists(quarantineFile), true);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
  } finally { await f.cleanup(); }
});

test('a post-effect original lock read failure is a structured unknown, never a false refusal', async () => {
  const f = await recoveryFixture();
  try {
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    const quarantineFile = f.quarantineFile(preview.action_ref);
    // The source lock read fails only once the move really happened: the
    // lock path is free only after the rename.
    let injected = 0;
    const publisher = createGitPublisher(f.config, { lstat: async (target, options) => {
      if (target === f.lockPath && !(await pathExists(f.lockPath)) && await pathExists(quarantineFile)) {
        injected += 1;
        throw Object.assign(new Error('simulated lock lstat failure'), {code: 'EACCES'});
      }
      return lstat(target, options);
    } });
    const result = await publisher.commit(await f.fences());
    assert.ok(injected > 0, 'the intended exact-path fault hook must execute');
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.action_ref, preview.action_ref);
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    assert.equal(await pathExists(f.lockPath), false);
    assert.equal(await pathExists(quarantineFile), true);
  } finally { await f.cleanup(); }
});

test('a post-effect readback failure with an unreadable diagnostic stays a structured unknown', async () => {
  const f = await recoveryFixture();
  try {
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    const quarantineFile = f.quarantineFile(preview.action_ref);
    let injected = 0;
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        if (file === GIT && args.includes('HEAD^{tree}') && await pathExists(quarantineFile)) {
          throw new Error('simulated post-effect readback failure');
        }
        return execFile(file, args, options);
      },
      lstat: async (target, options) => {
        if (target === quarantineFile && await pathExists(quarantineFile)) {
          injected += 1;
          throw Object.assign(new Error('simulated quarantine lstat failure'), {code: 'EIO'});
        }
        return lstat(target, options);
      },
    });
    const result = await publisher.commit(await f.fences());
    assert.ok(injected > 0, 'the intended exact-path fault hook must execute');
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.action_ref, preview.action_ref);
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    assert.equal(result.quarantined_lock.observation, 'UNAVAILABLE');
  } finally { await f.cleanup(); }
});

test('a retained-action entry that cannot be read stays an unknown effect with the same action ref', async () => {
  const f = await recoveryFixture();
  let receiptFile = null;
  try {
    const publisher = createGitPublisher(f.config);
    const applied = await publisher.commit(await f.fences());
    assert.equal(applied.effect_state, 'APPLIED');
    receiptFile = path.join(f.receiptDir, applied.action_ref + '.json');
    await chmod(receiptFile, 0o000);
    const reconciled = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: applied.action_ref },
    });
    // The retained action could not be observed. The action identity is kept
    // and the effect stays unknown; it is never a refusal.
    assert.equal(reconciled.status, 'UNKNOWN');
    assert.equal(reconciled.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(reconciled.code, 'INDEX_RECOVERY_RECEIPT_CORRUPT');
    assert.equal(reconciled.action_ref, applied.action_ref);
    assert.equal(reconciled.commit_created, false);
    assert.equal(reconciled.retry_allowed, false);
    // A reconcile never moves a lock.
    assert.deepEqual(await readdir(path.join(f.quarantineDir, applied.action_ref)), ['index.lock']);
  } finally {
    if (receiptFile) await chmod(receiptFile, 0o600).catch(() => {});
    await f.cleanup();
  }
});

test('a reconcile whose owner read is unavailable keeps the action identity and stays unknown', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const applied = await publisher.commit(await f.fences());
    assert.equal(applied.effect_state, 'APPLIED');
    const unavailable = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT && args.includes('--absolute-git-dir')) {
        throw new Error('simulated owner read failure');
      }
      return execFile(file, args, options);
    } });
    const reconciled = await unavailable.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: applied.action_ref },
    });
    assert.equal(reconciled.status, 'UNKNOWN');
    assert.equal(reconciled.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(reconciled.code, 'INDEX_RECOVERY_OWNER_UNAVAILABLE');
    assert.equal(reconciled.action_ref, applied.action_ref);
    assert.equal(reconciled.commit_created, false);
    assert.equal(reconciled.retry_allowed, false);
  } finally { await f.cleanup(); }
});

test('a reconcile whose owner cannot be reached at all keeps the action identity and stays unknown', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const applied = await publisher.commit(await f.fences());
    assert.equal(applied.effect_state, 'APPLIED');
    const unavailable = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT) throw new Error('simulated owner read failure');
      return execFile(file, args, options);
    } });
    const reconciled = await unavailable.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: applied.action_ref },
    });
    // The owner could not be reached at all. The action identity survives
    // and the effect stays unknown: it is never a refusal.
    assert.equal(reconciled.status, 'UNKNOWN');
    assert.equal(reconciled.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(reconciled.action_ref, applied.action_ref);
    assert.equal(reconciled.commit_created, false);
    assert.equal(reconciled.retry_allowed, false);
  } finally { await f.cleanup(); }
});

test('a reconcile whose live state cannot be read still reports the retained terminal action', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const applied = await publisher.commit(await f.fences());
    assert.equal(applied.effect_state, 'APPLIED');
    // The live state read fails while the owner itself still resolves, so
    // the retained record is read before the current observation is trusted.
    const degraded = createGitPublisher(f.config, { spawn: (file, args, options) => {
      if (file === GIT && args.includes('--stage')) {
        throw new Error('simulated live state read failure');
      }
      return spawn(file, args, options);
    } });
    const reconciled = await degraded.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: applied.action_ref },
    });
    // The live index cannot be read, but the retained terminal record is
    // owner-bound and validated, so the historical outcome is preserved and
    // the action identity is unchanged.
    assert.equal(reconciled.action_ref, applied.action_ref);
    assert.equal(reconciled.effect_state, 'APPLIED');
    assert.equal(reconciled.code, 'INDEX_RECOVERY_APPLIED');
    assert.equal(reconciled.commit_created, false);
    assert.equal(reconciled.retry_allowed, false);
  } finally {
    await chmod(f.indexPath, 0o600).catch(() => {});
    await f.cleanup();
  }
});

// ---- defect 2: a retained record is bound to its owner and its action -----

test('a valid-integrity foreign receipt is refused before any mutation', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    await mkdir(f.receiptDir, { recursive: true, mode: 0o700 });
    const foreign = recoveryRecordFor(f, preview.action_ref, {
      operation_id: 'a-foreign-operation-id',
    });
    await writeFile(path.join(f.receiptDir, preview.action_ref + '.json'), recoveryWire(foreign));
    const result = await publisher.commit(await f.fences());
    // The integrity hash is valid, so only the owner binding can refuse it.
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'INDEX_RECOVERY_RECEIPT_CORRUPT');
    assert.equal(result.detail.receipt_error, 'RECEIPT_OWNER_MISMATCH');
    assert.equal(result.action_ref, preview.action_ref);
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    // No foreign adoption and no mutation at all.
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.quarantineDir), false);
    assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    assert.equal((await git(f.workspace, 'status', '--porcelain')).stdout, '');
  } finally { await f.cleanup(); }
});

for (const [label, mutate, error] of [
  ['a broken fence derivation', (r) => ({...r, lock_identity: {...r.lock_identity, inode: '999999'}}),
    'RECEIPT_DERIVATION_MISMATCH'],
  ['tampered custody', (r) => ({...r, custody: {...r.custody, pending_mutators_retired: false}}),
    'INVALID_RECEIPT_SCHEMA'],
  ['custody with an extra field', (r) => ({...r, custody: {...r.custody, extra: true}}),
    'INVALID_RECEIPT_SCHEMA'],
  ['an incomplete lock identity', (r) => {
    const identity = {...r.lock_identity};
    delete identity.mtime_ns;
    return {...r, lock_identity: identity};
  }, 'INVALID_RECEIPT_SCHEMA'],
  ['a foreign branch', (r) => ({...r, branch: 'sol/web-a-foreign-branch'}),
    'RECEIPT_OWNER_MISMATCH'],
  ['a foreign action ref', (r) => ({...r, action_ref: 'e'.repeat(64)}),
    'RECEIPT_ACTION_MISMATCH'],
  ['a missing entry state', (r) => {
    const record = {...r};
    delete record.entry_state;
    return record;
  }, 'INVALID_RECEIPT_SCHEMA'],
  ['a terminal stage without an outcome', (r) => ({...r, stage: 'TERMINAL'}),
    'INVALID_RECEIPT_SCHEMA'],
  ['a rewritten historical origin', (r) => ({...r, historical_origin: 'SOME_WRITER'}),
    'INVALID_RECEIPT_SCHEMA'],
]) {
  test(`a retained receipt with ${label} is refused before any mutation`, async () => {
    const f = await recoveryFixture();
    try {
      const publisher = createGitPublisher(f.config);
      const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
      await mkdir(f.receiptDir, { recursive: true, mode: 0o700 });
      const record = mutate(recoveryRecordFor(f, preview.action_ref));
      await writeFile(path.join(f.receiptDir, preview.action_ref + '.json'), recoveryWire(record));
      const result = await publisher.commit(await f.fences());
      assert.equal(result.status, 'UNKNOWN');
      assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
      assert.equal(result.code, 'INDEX_RECOVERY_RECEIPT_CORRUPT');
      assert.equal(result.detail.receipt_error, error);
      assert.equal(result.action_ref, preview.action_ref);
      assert.equal(result.commit_created, false);
      assert.equal(result.retry_allowed, false);
      // No adoption and no mutation.
      assert.equal((await f.lockIdentity()).inode, f.lock.inode);
      assert.equal(await pathExists(f.quarantineDir), false);
      assert.equal((await git(f.workspace, 'rev-parse', 'HEAD')).stdout.trim(), f.head);
    } finally { await f.cleanup(); }
  });
}

// ---- defect 3: an existing non-terminal action is reconciliation-only ------

test('a repeated apply while the original action is paused before the rename never dispatches a second move', async () => {
  const f = await recoveryFixture();
  try {
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    let trees = 0;
    let releaseBoundary;
    const boundaryGate = new Promise((resolve) => { releaseBoundary = resolve; });
    let reachedBoundary;
    const boundaryReached = new Promise((resolve) => { reachedBoundary = resolve; });
    const publisher = createGitPublisher(f.config, { execFile: async (file, args, options) => {
      if (file === GIT && args.includes('HEAD^{tree}')) {
        trees += 1;
        // The original action pauses after its boundary checks and before
        // the rename.
        if (trees === 2) { reachedBoundary(); await boundaryGate; }
      }
      return execFile(file, args, options);
    } });
    const first = publisher.commit(await f.fences());
    first.catch(() => {});
    await boundaryReached;
    const second = await publisher.commit(await f.fences());
    // The repeated apply is reconciliation-only: it is unknown, it never
    // moves the lock and it never conveys retry authority.
    assert.equal(second.status, 'UNKNOWN');
    assert.equal(second.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(second.code, 'INDEX_RECOVERY_ORIGINAL_ACTION_MAY_BE_LIVE');
    assert.equal(second.action_ref, preview.action_ref);
    assert.equal(second.commit_created, false);
    assert.equal(second.retry_allowed, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.quarantineFile(preview.action_ref)), false);
    // The original action then completes its own single move.
    releaseBoundary();
    const applied = await first;
    assert.equal(applied.effect_state, 'APPLIED');
    assert.equal(applied.action_ref, preview.action_ref);
    assert.deepEqual(await readdir(path.join(f.quarantineDir, preview.action_ref)), ['index.lock']);
    assert.equal(await pathExists(f.lockPath), false);
  } finally { await f.cleanup(); }
});

test('a prepared action with the original lock still present is reconciled, never dispatched again', async () => {
  const f = await recoveryFixture();
  try {
    const publisher = createGitPublisher(f.config);
    const preview = await publisher_commit(f, await f.fences({ mode: 'PREVIEW' }));
    const receiptFile = path.join(f.receiptDir, preview.action_ref + '.json');
    await mkdir(f.receiptDir, { recursive: true, mode: 0o700 });
    await writeFile(receiptFile, recoveryWire(
      recoveryRecordFor(f, preview.action_ref, {stage: 'PREPARED'})));
    // A repeated apply finds the prepared record. The original invocation may
    // still be about to dispatch, so this one only reconciles.
    const applied = await publisher.commit(await f.fences());
    assert.equal(applied.status, 'UNKNOWN');
    assert.equal(applied.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(applied.code, 'INDEX_RECOVERY_ORIGINAL_ACTION_MAY_BE_LIVE');
    assert.equal(applied.action_ref, preview.action_ref);
    assert.equal(applied.commit_created, false);
    assert.equal(applied.retry_allowed, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.quarantineFile(preview.action_ref)), false);
    // The same prepared record reconciled directly is equally unresolved.
    await writeFile(receiptFile, recoveryWire(
      recoveryRecordFor(f, preview.action_ref, {stage: 'PREPARED'})));
    const reconciled = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: f.head,
      index_recovery: { mode: 'RECONCILE', action_ref: preview.action_ref },
    });
    assert.equal(reconciled.status, 'UNKNOWN');
    assert.equal(reconciled.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(reconciled.action_ref, preview.action_ref);
    assert.equal(reconciled.commit_created, false);
    assert.equal(reconciled.retry_allowed, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.quarantineFile(preview.action_ref)), false);
  } finally { await f.cleanup(); }
});

// ---- defect 4: the quarantine ancestry never escapes the owner ------------

test('a symlinked quarantine ancestor on the same filesystem refuses before any outside write', async () => {
  const f = await recoveryFixture();
  try {
    const outside = path.join(f.root, 'outside');
    await mkdir(outside, { recursive: true, mode: 0o700 });
    await mkdir(path.join(f.workspace, '.git', RECOVERY_RECEIPT_ROOT, RECOVERY_IDENTITY_DIR),
      { recursive: true, mode: 0o700 });
    await mkdir(f.receiptDir, { recursive: true, mode: 0o700 });
    // The quarantine ancestor is a symlink to an external directory on the
    // same filesystem. A device check alone cannot see it.
    await symlink(outside, f.quarantineDir);
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    // Nothing was written outside the owner and the lock never moved.
    assert.deepEqual(await readdir(outside), []);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.lockPath), true);
  } finally { await f.cleanup(); }
});

test('an unobservable symlinked identity ancestor stays unknown without any outside write', async () => {
  const f = await recoveryFixture();
  try {
    const outside = path.join(f.root, 'outside');
    await mkdir(outside, { recursive: true, mode: 0o700 });
    await mkdir(path.join(f.workspace, '.git', RECOVERY_RECEIPT_ROOT, RECOVERY_IDENTITY_DIR),
      { recursive: true, mode: 0o700 });
    await symlink(outside, f.receiptDir);
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'INDEX_RECOVERY_EFFECT_UNQUALIFIED');
    assert.match(result.detail.observation_error, /INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY/);
    assert.equal(result.commit_created, false);
    assert.deepEqual(await readdir(outside), []);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.lockPath), true);
  } finally { await f.cleanup(); }
});

test('a quarantine ancestor with a world writable mode refuses before any write', async () => {
  const f = await recoveryFixture();
  try {
    await mkdir(f.quarantineDir, { recursive: true, mode: 0o700 });
    await chmod(f.quarantineDir, 0o777);
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'INDEX_RECOVERY_PATH_NOT_OWNER_DIRECTORY');
    assert.equal(result.commit_created, false);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
    assert.equal(await pathExists(f.lockPath), true);
    assert.deepEqual(await readdir(f.quarantineDir), []);
  } finally { await f.cleanup(); }
});

// ---- defect 5: the rename is durable only when both directories are synced

test('a source directory durability failure after the move is unknown, never a false refusal', async () => {
  const f = await recoveryFixture();
  const gitDir = path.join(f.workspace, '.git');
  try {
    // The owner's Git directory keeps write and search permission but loses
    // read permission, so the source directory cannot be synced while every
    // Git read still works. The rename is really reached.
    await chmod(gitDir, 0o300);
    const publisher = createGitPublisher(f.config);
    const result = await publisher.commit(await f.fences());
    assert.equal(result.status, 'UNKNOWN');
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.code, 'INDEX_RECOVERY_QUARANTINE_DURABILITY_UNCERTAIN');
    assert.equal(result.commit_created, false);
    assert.equal(result.retry_allowed, false);
    // The lock really moved and is truthfully reported at the quarantine.
    assert.equal(await pathExists(f.lockPath), false);
    assert.equal(result.quarantined_lock.present, true);
    assert.equal(result.quarantined_lock.retained, true);
    assert.equal(result.quarantined_lock.inode, f.lock.inode);
    // No destructive cleanup, no rollback and no second move.
    assert.deepEqual(await readdir(path.join(f.quarantineDir, result.action_ref)), ['index.lock']);
  } finally {
    await chmod(gitDir, 0o700).catch(() => {});
    await f.cleanup();
  }
});


// Parent settlement regressions: original same-action effects remain truthful.
test('settlement keeps reconciliation unknown until rename directories are durable', async () => {
  const f = await recoveryFixture();
  const gitDir = path.join(f.workspace, '.git');
  try {
    const args = await f.fences();
    await chmod(gitDir, 0o300);
    const publisher = createGitPublisher(f.config);
    const first = await publisher.commit(args);
    assert.equal(first.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(first.quarantined_lock.inode, f.lock.inode);
    const request = {operation_id: f.operationId, expected_head_sha: f.head,
      index_recovery: {mode: 'RECONCILE', action_ref: first.action_ref}};
    const unresolved = await publisher.commit(request);
    assert.equal(unresolved.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(unresolved.action_ref, first.action_ref);
    assert.equal(unresolved.quarantined_lock.inode, f.lock.inode);
    await chmod(gitDir, 0o700);
    const settled = await publisher.commit(request);
    assert.equal(settled.effect_state, 'APPLIED');
    assert.equal(settled.action_ref, first.action_ref);
    assert.equal(settled.quarantined_lock.inode, f.lock.inode);
    assert.equal(await pathExists(f.lockPath), false);
    assert.deepEqual(await readdir(path.join(f.quarantineDir, first.action_ref)), ['index.lock']);
  } finally { await chmod(gitDir, 0o700).catch(() => {}); await f.cleanup(); }
});

test('settlement establishes durable reachability of the quarantine ancestors', async () => {
  const f = await recoveryFixture();
  try {
    const args = await f.fences();
    const preview = await publisher_commit(f, await f.fences({mode: 'PREVIEW'}));
    const canonicalActionDir = path.join(await realpath(f.workspace), '.git',
      RECOVERY_RECEIPT_ROOT, RECOVERY_IDENTITY_DIR, f.identity, 'quarantine', preview.action_ref);
    let injected = 0;
    const publisher = createGitPublisher(f.config, {lstat: async (target, options) => {
      const stats = await lstat(target, options);
      if (target === canonicalActionDir && options?.bigint && injected === 0) {
        injected += 1;
        await chmod(f.quarantineDir, 0o300);
      }
      return stats;
    }});
    const result = await publisher.commit(args);
    assert.equal(injected, 1);
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.quarantined_lock.inode, f.lock.inode);
    await chmod(f.quarantineDir, 0o700);
    const settled = await publisher.commit({operation_id: f.operationId, expected_head_sha: f.head,
      index_recovery: {mode: 'RECONCILE', action_ref: result.action_ref}});
    assert.equal(settled.effect_state, 'APPLIED');
    assert.equal(settled.quarantined_lock.inode, f.lock.inode);
    assert.equal(await pathExists(f.lockPath), false);
  } finally { await chmod(f.quarantineDir, 0o700).catch(() => {}); await f.cleanup(); }
});

for (const mode of ['APPLY', 'RECONCILE']) {
  test(`settlement ${mode} never consumes or rewrites a retained receipt through symlink ancestry`, async () => {
    const f = await recoveryFixture();
    try {
      const args = await f.fences();
      const preview = await publisher_commit(f, await f.fences({mode: 'PREVIEW'}));
      const outside = path.join(f.root, 'external-receipts');
      await mkdir(outside, {mode: 0o700});
      await mkdir(path.dirname(f.receiptDir), {recursive: true, mode: 0o700});
      const file = path.join(outside, preview.action_ref + '.json');
      const wire = recoveryWire(recoveryRecordFor(f, preview.action_ref));
      await writeFile(file, wire, {mode: 0o600});
      await symlink(outside, f.receiptDir);
      const request = mode === 'APPLY' ? args : {
        operation_id: f.operationId, expected_head_sha: f.head,
        index_recovery: {mode, action_ref: preview.action_ref}};
      const result = await createGitPublisher(f.config).commit(request);
      assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
      assert.equal(result.action_ref, preview.action_ref);
      assert.equal(await readFile(file, 'utf8'), wire);
      assert.deepEqual(await readdir(outside), [preview.action_ref + '.json']);
      assert.equal((await f.lockIdentity()).inode, f.lock.inode);
      assert.equal(result.receipt_recorded, false);
    } finally { await f.cleanup(); }
  });
}

for (const retained of ['applied', 'unresolved']) {
  test(`settlement repeated APPLY preserves ${retained} action when the current index is unreadable`, async () => {
    const f = await recoveryFixture();
    try {
      const args = await f.fences();
      const preview = await publisher_commit(f, await f.fences({mode: 'PREVIEW'}));
      if (retained === 'applied') {
        const first = await createGitPublisher(f.config).commit(args);
        assert.equal(first.effect_state, 'APPLIED');
      } else {
        await mkdir(f.receiptDir, {recursive: true, mode: 0o700});
        await writeFile(path.join(f.receiptDir, preview.action_ref + '.json'),
          recoveryWire(recoveryRecordFor(f, preview.action_ref)), {mode: 0o600});
      }
      let injected = 0;
      const publisher = createGitPublisher(f.config, {spawn: (file, argv, options) => {
        if (file === GIT && argv.includes('--stage')) {
          injected += 1;
          throw new Error('settlement current index observation unavailable');
        }
        return spawn(file, argv, options);
      }});
      const result = await publisher.commit(args);
      assert.ok(injected > 0);
      assert.equal(result.action_ref, preview.action_ref);
      assert.equal(result.effect_state, retained === 'applied' ? 'APPLIED' : 'EFFECT_UNKNOWN');
      assert.equal(result.commit_created, false);
      assert.equal(result.retry_allowed, false);
      if (retained === 'applied') {
        assert.equal(result.quarantined_lock.inode, f.lock.inode);
        assert.equal(await pathExists(f.lockPath), false);
      } else {
        assert.equal((await f.lockIdentity()).inode, f.lock.inode);
        assert.equal(await pathExists(f.quarantineDir), false);
      }
    } finally { await f.cleanup(); }
  });
}

test('settlement rechecks retained receipt ancestry before a terminal replacement', async () => {
  const f = await recoveryFixture();
  try {
    const args = await f.fences();
    const preview = await publisher_commit(f, await f.fences({mode: 'PREVIEW'}));
    await mkdir(f.receiptDir, {recursive: true, mode: 0o700});
    const wire = recoveryWire(recoveryRecordFor(f, preview.action_ref));
    await writeFile(path.join(f.receiptDir, preview.action_ref + '.json'), wire, {mode: 0o600});
    const outside = path.join(f.root, 'external-receipts');
    await mkdir(outside, {mode: 0o700});
    const externalFile = path.join(outside, preview.action_ref + '.json');
    await writeFile(externalFile, wire, {mode: 0o600});
    let injected = 0;
    const publisher = createGitPublisher(f.config, {spawn: (file, argv, options) => {
      if (file === GIT && argv.includes('--stage') && injected === 0) {
        injected += 1;
        renameSync(f.receiptDir, f.receiptDir + '.retained-test');
        symlinkSync(outside, f.receiptDir);
      }
      return spawn(file, argv, options);
    }});
    const result = await publisher.commit(args);
    assert.equal(injected, 1);
    assert.equal(result.effect_state, 'EFFECT_UNKNOWN');
    assert.equal(result.action_ref, preview.action_ref);
    assert.equal(result.receipt_recorded, false);
    assert.equal(await readFile(externalFile, 'utf8'), wire);
    assert.deepEqual(await readdir(outside), [preview.action_ref + '.json']);
    assert.equal((await f.lockIdentity()).inode, f.lock.inode);
  } finally { await f.cleanup(); }
});
