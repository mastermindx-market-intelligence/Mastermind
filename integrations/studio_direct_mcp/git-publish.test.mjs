import assert from 'node:assert/strict';
import { execFile as execFileCallback, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { chmod, mkdir, mkdtemp, readdir, readFile, rm, stat, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

import {
  STUDIO_GIT_PUBLISH_STATUS_TOOL,
  STUDIO_GIT_COMMIT_CURRENT_CHANGES_TOOL,
  STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL,
  STUDIO_WEB_COMMISSION_MATERIALIZE_TOOL,
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
  assert.match(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.description, /complete effective push destination/);
  assert.match(STUDIO_GIT_PUSH_CURRENT_BRANCH_TOOL.description, /regardless of ambient follow-tags, submodule or mirror push configuration/);
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
      if (file === GIT && args[0] === 'ls-remote') {
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
    assert.equal(result.status, 'OK');
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
      if (file === GIT && args.includes('push') && !injected) {
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
      if (file === GIT && args.includes('push') && !injected) {
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
      if (file === GIT && args.includes('push') && !injected) {
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

// --- Typed Web commission publication -------------------------------------
//
// The Craft commission compiler (PR #587,
// research/worker_craft/mastermind-craft/scripts/brief.py) is not protected
// yet, so these tests pin the adapter against that compiler's frozen process
// contract through fixtures/commission-compiler.mjs. The final test below runs
// the real compiler instead, and skips while it is still absent from this
// branch, leaving the integration reconciliation explicit rather than vendored.

const COMMISSION_PATH = 'research/executive_commissions/COMMISSION.md';
const COMPILER_FIXTURE = path.join(
  path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'commission-compiler.mjs');

function compactCommission(overrides = {}) {
  return {
    schema_version: 'mastermind.craft_commission_request.v1',
    role: 'backend',
    authority_ref: 'fixture.session2.typed-web-publication',
    source: {
      base: { repository: 'mastermindx-market-intelligence/Mastermind', commit: 'a'.repeat(40) },
      governing: [{
        repository: 'mastermindx-market-intelligence/Mastermind',
        commit: 'a'.repeat(40),
        path: 'docs/sol_skills/INDEX.md',
      }],
    },
    outcome: {
      objective: 'Publish one bounded commission artifact through the typed Web publication plane.',
      why: 'A Web CEO should not have to push a rendered commission through a generic shell tool.',
      user_journey: 'Compact intent in, canonical commission artifact on the attended Web branch out.',
      machine_outcome: 'Deterministic commission bytes land at the canonical path with a proved digest.',
    },
    scope: { write_paths: ['research/executive_commissions'], non_goals: ['Do not add a second compiler.'] },
    inputs: ['This compact request and the repository-owned Craft method files.'],
    data: {
      time: 'Source references are exact commit identities.',
      missing: 'Unknown runtime admission stays unknown.',
      corrections: 'A changed request produces a new digest.',
      rights: 'Repository-owned method text only.',
    },
    method: {
      deterministic: ['Validate the compact request and render the commission.'],
      model: ['Model judgment stays inside the bounded worker method.'],
      implementation_order: ['Validate, compile, publish.'],
    },
    deliverables: ['One canonical COMMISSION.md at the fixed publication path.'],
    acceptance: ['The published bytes hash to the compiler-declared commission digest.'],
    failure: {
      refusals: ['Refuse caller-selected repository, remote, branch or path.'],
      stop_conditions: ['Stop dependent work on EFFECT_UNKNOWN until the carrier is reconciled.'],
    },
    constraints: ['This authoring path grants no execution authority.'],
    continuation: {
      record_owner: 'GitHub owns implementation and evidence.',
      next_action: 'Typed commit and typed exact-ref push on the same attended Web operation.',
    },
    ...overrides,
  };
}

async function withCommission(f, mode = 'ok') {
  const compiler = path.join(f.root, `compiler-${mode}.mjs`);
  await writeFile(
    compiler,
    `process.env.STUB_COMMISSION_MODE = ${JSON.stringify(mode)};\n` +
    `await import(${JSON.stringify(pathToFileURL(COMPILER_FIXTURE).href)});\n`,
  );
  return {
    ...f.config,
    commissionCompiler: compiler,
    commissionCompilerInterpreter: process.execPath,
    commissionTimeoutMs: 20_000,
  };
}

test('commission materialization stays closed unless the host compiler is configured', async () => {
  const f = await fixture();
  try {
    const plain = createGitPublisher(f.config);
    assert.equal(plain.commissionEnabled, false);
    await assert.rejects(
      () => plain.materializeCommission({ operation_id: f.operationId, commission: compactCommission() }),
      /commission materialization is not configured/,
    );

    for (const partial of [
      { commissionCompiler: '/usr/bin/true' },
      { commissionCompilerInterpreter: '/usr/bin/true' },
      { commissionTimeoutMs: 1000 },
      { commissionCompiler: 'brief.py', commissionCompilerInterpreter: '/usr/bin/python3' },
      { commissionCompiler: '/usr/bin/brief.py', commissionCompilerInterpreter: 'python3' },
    ]) {
      assert.throws(() => resolveGitPublishConfig({ ...f.config, ...partial }), TypeError);
    }

    const enabled = createGitPublisher(await withCommission(f));
    assert.equal(enabled.commissionEnabled, true);
  } finally {
    await f.cleanup();
  }
});

test('commission tool metadata refuses every destination and routing selector', () => {
  const tool = STUDIO_WEB_COMMISSION_MATERIALIZE_TOOL;
  assert.equal(tool.annotations.readOnlyHint, false);
  assert.equal(tool.annotations.destructiveHint, true);
  assert.equal(tool.annotations.idempotentHint, true);
  assert.equal(tool.annotations.openWorldHint, false, 'materialization must not contact a remote');
  assert.deepEqual(tool.inputSchema.required, ['operation_id', 'commission']);
  assert.equal(tool.inputSchema.additionalProperties, false);
  assert.deepEqual(Object.keys(tool.inputSchema.properties).sort(), ['commission', 'operation_id']);
  for (const forbidden of [
    'branch', 'remote', 'repository', 'path', 'command', 'force', 'content',
    'commission_markdown', 'provider', 'model', 'account', 'credential', 'host',
  ]) {
    assert.equal(forbidden in tool.inputSchema.properties, false, `${forbidden} must not be selectable`);
  }
  // Pins the compact contract owned by the Craft compiler so a drift in either
  // side shows up here instead of at publication time.
  assert.equal(tool.inputSchema.properties.commission.properties.schema_version.const,
    'mastermind.craft_commission_request.v1');
  assert.deepEqual(tool.inputSchema.properties.commission.required.slice().sort(), [
    'acceptance', 'authority_ref', 'constraints', 'continuation', 'data', 'deliverables',
    'failure', 'inputs', 'method', 'outcome', 'role', 'schema_version', 'scope', 'source',
  ]);
  assert.match(tool.description, /research\/executive_commissions\/COMMISSION\.md/);
});

test('compact request materializes the canonical commission without any shell or commission payload in argv', async () => {
  const f = await fixture();
  try {
    const calls = [];
    const publisher = createGitPublisher(await withCommission(f), {
      execFile: async (file, args, options) => {
        calls.push({ file, args, options });
        return execFile(file, args, options);
      },
    });
    const commission = compactCommission();
    const compactBytes = Buffer.byteLength(JSON.stringify(commission), 'utf8');

    const result = await publisher.materializeCommission({
      operation_id: f.operationId,
      commission,
    });

    assert.equal(result.schema, 'mastermind.studio_web_commission_result.v1');
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.code, 'APPLIED');
    assert.equal(result.written, true);
    assert.equal(result.commission_path, COMMISSION_PATH);
    assert.equal(result.branch, f.branch);
    assert.equal(result.local_head_sha, f.head, 'materialization must not create a commit');
    assert.equal(result.clean, false, 'the new artifact is the pending committable change');
    assert.match(result.action_ref, /^[0-9a-f]{64}$/);

    const published = await readFile(path.join(f.workspace, COMMISSION_PATH));
    assert.equal(createHash('sha256').update(published).digest('hex'), result.commission_sha256);
    assert.equal(published.byteLength, result.commission_bytes);
    assert.ok(published.byteLength > compactBytes * 2,
      'the host must expand compact intent, not echo what the caller sent');
    assert.match(published.toString('utf8'), /^# Worker commission\n/);

    const compilerCalls = calls.filter((call) => call.file === process.execPath);
    assert.equal(compilerCalls.length, 1);
    assert.deepEqual(compilerCalls[0].args.slice(1, 2), ['compile-commission']);
    assert.deepEqual(compilerCalls[0].args.slice(3), ['--format', 'json']);
    assert.equal(path.isAbsolute(compilerCalls[0].args[2]), true);
    assert.equal(compilerCalls[0].args[2].startsWith(f.workspace), false,
      'the compact request must never be staged inside the published workspace');
    for (const call of calls) {
      assert.equal(call.options.shell, undefined, 'no command may be interpreted by a shell');
      for (const arg of call.args) {
        assert.equal(arg.includes('\n'), false, 'no multi-line payload may travel through argv');
        assert.equal(arg.includes('Worker commission'), false, 'commission bytes must not travel through argv');
        assert.equal(arg.includes(commission.outcome.objective), false, 'request bytes must not travel through argv');
      }
    }
  } finally {
    await f.cleanup();
  }
});

test('republishing identical commission bytes reports ALREADY_APPLIED and rewrites nothing', async () => {
  const f = await fixture();
  try {
    const publisher = createGitPublisher(await withCommission(f));
    const commission = compactCommission();
    const first = await publisher.materializeCommission({ operation_id: f.operationId, commission });
    assert.equal(first.code, 'APPLIED');
    const target = path.join(f.workspace, COMMISSION_PATH);
    const { mtimeMs, ino } = await stat(target);

    const second = await publisher.materializeCommission({ operation_id: f.operationId, commission });
    assert.equal(second.status, 'OK');
    assert.equal(second.effect_state, 'APPLIED');
    assert.equal(second.code, 'ALREADY_APPLIED');
    assert.equal(second.written, false);
    assert.equal(second.commission_sha256, first.commission_sha256);
    assert.equal(second.action_ref, first.action_ref);
    const after = await stat(target);
    assert.equal(after.ino, ino);
    assert.equal(after.mtimeMs, mtimeMs, 'a converged republish must not touch the artifact');

    // A compact request that renders different bytes is a different artifact
    // and does replace it. Convergence is on the exact bytes, not on the input.
    const changed = await publisher.materializeCommission({
      operation_id: f.operationId,
      commission: compactCommission({ authority_ref: 'fixture.session2.typed-web-publication-b' }),
    });
    assert.equal(changed.code, 'APPLIED');
    assert.notEqual(changed.commission_sha256, first.commission_sha256);
    assert.notEqual(changed.action_ref, first.action_ref);
  } finally {
    await f.cleanup();
  }
});

test('compiler refusal is surfaced as a closed token and publishes nothing', async () => {
  const f = await fixture();
  try {
    const publisher = createGitPublisher(await withCommission(f, 'refuse'));
    const result = await publisher.materializeCommission({
      operation_id: f.operationId,
      commission: compactCommission(),
    });
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED');
    assert.equal(result.code, 'COMMISSION_COMPILER_REFUSED');
    assert.equal(result.compiler_refusal, 'commission.fields');
    assert.equal('commission_sha256' in result, false);
    await assert.rejects(() => readFile(path.join(f.workspace, COMMISSION_PATH)), /ENOENT/);

    const unbounded = createGitPublisher(await withCommission(f, 'refuse_unbounded'));
    const wide = await unbounded.materializeCommission({
      operation_id: f.operationId,
      commission: compactCommission(),
    });
    assert.equal(wide.code, 'COMMISSION_COMPILER_REFUSED');
    assert.equal('compiler_refusal' in wide, false, 'an out-of-vocabulary token must be dropped, not relayed');
  } finally {
    await f.cleanup();
  }
});

test('an untrustworthy compiler result is refused before anything reaches the workspace', async () => {
  for (const mode of ['digest_mismatch', 'selected_provider', 'granted_authority', 'wrong_schema', 'no_markdown', 'invalid_json']) {
    const f = await fixture();
    try {
      const publisher = createGitPublisher(await withCommission(f, mode));
      await assert.rejects(
        () => publisher.materializeCommission({ operation_id: f.operationId, commission: compactCommission() }),
        (error) => error instanceof Error,
        `${mode} must not publish`,
      );
      await assert.rejects(() => readFile(path.join(f.workspace, COMMISSION_PATH)), /ENOENT/, mode);
      const { stdout } = await git(f.workspace, 'status', '--porcelain=v1', '--untracked-files=all');
      assert.equal(stdout, '', `${mode} must leave the workspace clean`);
    } finally {
      await f.cleanup();
    }
  }
});

test('malformed compact requests are refused before the compiler is ever started', async () => {
  const f = await fixture();
  try {
    const calls = [];
    const publisher = createGitPublisher(await withCommission(f), {
      execFile: async (file, args, options) => {
        calls.push(file);
        return execFile(file, args, options);
      },
    });
    const bad = [
      { operation_id: f.operationId },
      { operation_id: f.operationId, commission: null },
      { operation_id: f.operationId, commission: [compactCommission()] },
      { operation_id: f.operationId, commission: 'a rendered commission body' },
      { operation_id: f.operationId, commission: compactCommission({ schema_version: 'mastermind.craft_brief.v1' }) },
      { operation_id: f.operationId, commission: compactCommission({ authority_ref: 'x'.repeat(20_000) }) },
      { operation_id: f.operationId, commission: compactCommission(), branch: 'sol/web-other' },
      { operation_id: f.operationId, commission: compactCommission(), path: COMMISSION_PATH },
      { operation_id: f.operationId, commission: compactCommission(), force: true },
      { operation_id: '../escape', commission: compactCommission() },
    ];
    for (const args of bad) {
      await assert.rejects(() => publisher.materializeCommission(args), TypeError, JSON.stringify(Object.keys(args)));
    }
    assert.equal(calls.includes(process.execPath), false, 'no compiler process may start for a refused request');
    await assert.rejects(() => readFile(path.join(f.workspace, COMMISSION_PATH)), /ENOENT/);
  } finally {
    await f.cleanup();
  }
});

test('a symlinked commission directory cannot redirect the published artifact', async () => {
  const f = await fixture();
  try {
    const outside = path.join(f.root, 'outside');
    await mkdir(outside, { recursive: true });
    await mkdir(path.join(f.workspace, 'research'), { recursive: true });
    await symlink(outside, path.join(f.workspace, 'research', 'executive_commissions'));

    const publisher = createGitPublisher(await withCommission(f));
    await assert.rejects(
      () => publisher.materializeCommission({ operation_id: f.operationId, commission: compactCommission() }),
      /escapes the attended Web workspace/,
    );
    await assert.rejects(() => readFile(path.join(outside, 'COMMISSION.md')), /ENOENT/);
  } finally {
    await f.cleanup();
  }
});

test('typed publication journey: compact request, typed commit, exact-ref push, exact remote readback', async () => {
  const f = await fixture();
  try {
    const publisher = createGitPublisher(await withCommission(f));
    const materialized = await publisher.materializeCommission({
      operation_id: f.operationId,
      commission: compactCommission(),
    });
    assert.equal(materialized.effect_state, 'APPLIED');

    const committed = await publisher.commit({
      operation_id: f.operationId,
      expected_head_sha: materialized.local_head_sha,
      message: 'chore(web): publish commission artifact',
    });
    assert.equal(committed.status, 'OK');
    assert.equal(committed.effect_state, 'APPLIED');

    const pushed = await publisher.push({
      operation_id: f.operationId,
      expected_head_sha: committed.commit_head_sha,
    });
    assert.equal(pushed.status, 'OK');
    assert.equal(pushed.effect_state, 'APPLIED');
    assert.equal(pushed.remote_head_sha, committed.commit_head_sha);
    assert.equal(pushed.branch, `sol/web-${f.operationId}`);

    // Exact remote readback of the published artifact, straight out of the bare remote.
    const { stdout: refOut } = await git(f.remote, 'rev-parse', `refs/heads/${f.branch}`);
    assert.equal(refOut.trim(), committed.commit_head_sha);
    const { stdout: blobOut } = await run(GIT, ['show', `${committed.commit_head_sha}:${COMMISSION_PATH}`], { cwd: f.remote });
    assert.equal(
      createHash('sha256').update(Buffer.from(blobOut, 'utf8')).digest('hex'),
      materialized.commission_sha256,
      'the exact compiled bytes must be the bytes on the remote branch',
    );
  } finally {
    await f.cleanup();
  }
});

test('the real Craft commission compiler satisfies the adapter contract when it is present', async (t) => {
  // Reconciliation seam for PR #587. Skips while the compiler is unprotected.
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
  const compiler = path.join(repoRoot, 'research/worker_craft/mastermind-craft/scripts/brief.py');
  if (!existsSync(compiler)) {
    t.skip('research/worker_craft/mastermind-craft/scripts/brief.py is not present on this base');
    return;
  }
  const interpreter = ['/usr/bin/python3', '/usr/local/bin/python3', '/opt/homebrew/bin/python3'].find(existsSync);
  if (!interpreter) {
    t.skip('no absolute python3 interpreter is available');
    return;
  }
  const f = await fixture();
  try {
    const publisher = createGitPublisher({
      ...f.config,
      commissionCompiler: compiler,
      commissionCompilerInterpreter: interpreter,
      commissionTimeoutMs: 30_000,
    });
    const result = await publisher.materializeCommission({
      operation_id: f.operationId,
      commission: compactCommission(),
    });
    assert.equal(result.status, 'OK', JSON.stringify(result));
    assert.equal(result.effect_state, 'APPLIED');
    const published = await readFile(path.join(f.workspace, COMMISSION_PATH));
    assert.equal(createHash('sha256').update(published).digest('hex'), result.commission_sha256);
    assert.match(published.toString('utf8'), /^# Worker commission\n/);
  } finally {
    await f.cleanup();
  }
});

test('a staging failure with no prior artifact is NOT_APPLIED, never EFFECT_UNKNOWN', async (t) => {
  if (process.getuid?.() === 0) {
    t.skip('directory permissions do not constrain root');
    return;
  }
  const f = await fixture();
  const directory = path.join(f.workspace, 'research', 'executive_commissions');
  try {
    await mkdir(directory, { recursive: true });
    await chmod(directory, 0o500);
    const publisher = createGitPublisher(await withCommission(f));
    const result = await publisher.materializeCommission({
      operation_id: f.operationId,
      commission: compactCommission(),
    });
    assert.equal(result.status, 'REFUSED');
    assert.equal(result.effect_state, 'NOT_APPLIED',
      'an unwritable destination proves nothing was applied; it is not an unknown effect');
    assert.equal(result.code, 'COMMISSION_WRITE_FAILED');
    assert.equal(result.written, false);
    assert.equal('stray_staged_path' in result, false);
    await assert.rejects(() => readFile(path.join(f.workspace, COMMISSION_PATH)), /ENOENT/);
  } finally {
    await chmod(directory, 0o700).catch(() => {});
    await f.cleanup();
  }
});

test('a staging failure over an existing identical artifact still reports the proved applied state', async (t) => {
  if (process.getuid?.() === 0) {
    t.skip('directory permissions do not constrain root');
    return;
  }
  const f = await fixture();
  const directory = path.join(f.workspace, 'research', 'executive_commissions');
  try {
    const publisher = createGitPublisher(await withCommission(f));
    const commission = compactCommission();
    const first = await publisher.materializeCommission({ operation_id: f.operationId, commission });
    assert.equal(first.code, 'APPLIED');
    // Force the staged-write path by defeating the fast converged pre-check.
    await chmod(path.join(f.workspace, COMMISSION_PATH), 0o000);
    await chmod(directory, 0o500);
    const second = await publisher.materializeCommission({ operation_id: f.operationId, commission });
    assert.equal(second.effect_state, 'NOT_APPLIED', 'unreadable existing bytes cannot be claimed as this artifact');
    assert.equal(second.code, 'COMMISSION_WRITE_FAILED');
  } finally {
    await chmod(directory, 0o700).catch(() => {});
    await chmod(path.join(f.workspace, COMMISSION_PATH), 0o600).catch(() => {});
    await f.cleanup();
  }
});

test('a symlinked ancestor on the commission path creates nothing outside the workspace', async () => {
  const f = await fixture();
  try {
    const outside = path.join(f.root, 'outside-research');
    await mkdir(outside, { recursive: true });
    await symlink(outside, path.join(f.workspace, 'research'));

    const publisher = createGitPublisher(await withCommission(f));
    await assert.rejects(
      () => publisher.materializeCommission({ operation_id: f.operationId, commission: compactCommission() }),
      /escapes the attended Web workspace/,
    );
    assert.deepEqual(await readdir(outside), [],
      'a redirected ancestor must be refused before anything is created through it');
  } finally {
    await f.cleanup();
  }
});

// --- Effective push destination and ref-effect ceiling ----------------------
// Regressions for the two blockers found by independent exact-head review of
// 42d50bf6: the validated fetch origin was not the effective push destination,
// and ambient push configuration could widen the authorized ref set.

test('an effective push URL outside the allowlist is refused before any remote effect', async () => {
  const f = await fixture();
  try {
    const outside = path.join(f.root, 'outside-policy.git');
    await git(f.root, 'init', '--bare', outside);
    await git(f.workspace, 'config', 'remote.origin.pushurl', outside);
    const publisher = createGitPublisher(f.config);
    await assert.rejects(
      () => publisher.push({ operation_id: f.operationId, expected_head_sha: f.head }),
      /origin push URL is outside/,
    );
    const { stdout } = await git(outside, 'for-each-ref', '--format=%(objectname)', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim(), '', 'an out-of-policy repository must never be written');
    const { stdout: allowed } = await git(f.remote, 'for-each-ref', '--format=%(objectname)', `refs/heads/${f.branch}`);
    assert.equal(allowed.trim(), '', 'a refused push must not reach the allowed remote either');
  } finally {
    await f.cleanup();
  }
});

test('a pushInsteadOf rewrite cannot redirect the push away from the allowed remote', async () => {
  const f = await fixture();
  try {
    const rewritten = path.join(f.root, 'rewritten.git');
    await git(f.root, 'init', '--bare', rewritten);
    await git(f.workspace, 'config', `url.${rewritten}.pushInsteadOf`, f.remote);
    const publisher = createGitPublisher(f.config);
    await assert.rejects(
      () => publisher.push({ operation_id: f.operationId, expected_head_sha: f.head }),
      /origin push URL is outside/,
    );
    const { stdout } = await git(rewritten, 'for-each-ref', '--format=%(objectname)', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim(), '', 'a rewritten destination must never be written');
  } finally {
    await f.cleanup();
  }
});

test('an allowed push URL that is not the readback origin is refused', async () => {
  const f = await fixture();
  try {
    const second = path.join(f.root, 'second-allowed.git');
    await git(f.root, 'init', '--bare', second);
    await git(f.workspace, 'config', 'remote.origin.pushurl', second);
    // Both destinations are host-allowed, but the operation must write to and
    // reconcile against one repository, or the readback proves nothing.
    const publisher = createGitPublisher({ ...f.config, allowedRemoteUrls: [f.remote, second] });
    await assert.rejects(
      () => publisher.push({ operation_id: f.operationId, expected_head_sha: f.head }),
      /not the fetch URL this operation reconciles against/,
    );
    const { stdout } = await git(second, 'for-each-ref', '--format=%(objectname)', `refs/heads/${f.branch}`);
    assert.equal(stdout.trim(), '');
  } finally {
    await f.cleanup();
  }
});

test('a remote with several fetch or push URLs is refused rather than chosen between', async () => {
  for (const key of ['remote.origin.url', 'remote.origin.pushurl']) {
    const f = await fixture();
    try {
      const second = path.join(f.root, 'second-allowed.git');
      await git(f.root, 'init', '--bare', second);
      if (key === 'remote.origin.pushurl') await git(f.workspace, 'config', key, f.remote);
      await git(f.workspace, 'config', '--add', key, second);
      const publisher = createGitPublisher({ ...f.config, allowedRemoteUrls: [f.remote, second] });
      await assert.rejects(
        () => publisher.push({ operation_id: f.operationId, expected_head_sha: f.head }),
        /must resolve to exactly one destination/,
        key,
      );
      const { stdout } = await git(second, 'for-each-ref', '--format=%(objectname)', `refs/heads/${f.branch}`);
      assert.equal(stdout.trim(), '', key);
    } finally {
      await f.cleanup();
    }
  }
});

test('ambient push configuration cannot widen the authorized ref set', async () => {
  const f = await fixture();
  try {
    await git(f.workspace, 'tag', '-a', 'unrequested-regression-tag', '-m', 'fixture only');
    await git(f.workspace, 'tag', 'unrequested-lightweight-tag');
    await git(f.workspace, 'config', 'push.followTags', 'true');
    await git(f.workspace, 'config', 'remote.origin.mirror', 'true');
    await git(f.workspace, 'config', 'remote.origin.push', 'refs/heads/*:refs/heads/*');

    const calls = [];
    const publisher = createGitPublisher(f.config, {
      execFile: async (file, args, options) => {
        calls.push(args);
        return execFile(file, args, options);
      },
    });
    const result = await publisher.push({ operation_id: f.operationId, expected_head_sha: f.head });
    assert.equal(result.status, 'OK');
    assert.equal(result.effect_state, 'APPLIED');
    assert.equal(result.remote_head_sha, f.head);

    const { stdout: tags } = await git(f.remote, 'for-each-ref', '--format=%(refname)', 'refs/tags/');
    assert.equal(tags.trim(), '', 'a one-branch tool must never publish a tag');
    const { stdout: refs } = await git(f.remote, 'for-each-ref', '--format=%(refname)');
    assert.deepEqual(refs.trim().split('\n'), [`refs/heads/${f.branch}`],
      'exactly one branch ref may exist on the remote');

    const pushArgs = calls.find((args) => args.includes('push'));
    assert.ok(pushArgs);
    for (const required of ['--no-follow-tags', '--recurse-submodules=no', 'remote.origin.mirror=false']) {
      assert.ok(pushArgs.includes(required), `${required} must bound the push`);
    }
    for (const forbidden of ['--force', '-f', '--mirror', '--tags', '--all', '--force-with-lease', '--delete']) {
      assert.equal(pushArgs.includes(forbidden), false, `${forbidden} must never be issued`);
    }
    assert.equal(pushArgs.some((arg) => arg.startsWith('+')), false, 'no refspec may request a force update');
    assert.equal(pushArgs.at(-1), `${f.head}:refs/heads/${f.branch}`);
  } finally {
    await f.cleanup();
  }
});

test('an unpublishable destination is refused identically through the typed status and commit paths', async () => {
  const f = await fixture();
  try {
    const outside = path.join(f.root, 'outside-policy.git');
    await git(f.root, 'init', '--bare', outside);
    await git(f.workspace, 'config', 'remote.origin.pushurl', outside);
    const publisher = createGitPublisher(f.config);
    await assert.rejects(() => publisher.status({ operation_id: f.operationId }), /origin push URL is outside/);
    await writeFile(path.join(f.workspace, 'pending.txt'), 'pending\n');
    await assert.rejects(
      () => publisher.commit({ operation_id: f.operationId, expected_head_sha: f.head, message: 'test: blocked' }),
      /origin push URL is outside/,
    );
    const { stdout } = await git(f.workspace, 'rev-parse', 'HEAD');
    assert.equal(stdout.trim(), f.head, 'a refused destination must not leave a local commit behind');
  } finally {
    await f.cleanup();
  }
});
