import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm, chmod, symlink } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import os from 'node:os';
import path from 'node:path';
import { createT3Controller, resolveT3ControlConfig, T3_CONTROL_TOOLS, t3ToolResult } from './t3-control.mjs';

const principal = 'p:tunnel:account-a';
const observed = name => ({ schema: 'mastermind.t3_dot_result.v1', status: 'OBSERVED',
  operation: name, data: { observed: true }, retry_allowed: false, parent_accepted: false });
async function fixture(t, operations = ['t3_fleet_environments', 't3_thread_launch']) {
  const dir = await mkdtemp(path.join(os.tmpdir(), 't3-dot-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const profile = { schema: 'mastermind.t3_dot_native_profile.v1', principal_key: principal,
    operations, timeout_seconds: 5 };
  const raw = JSON.stringify(profile);
  const profilePath = path.join(dir, 'profile.json');
  await writeFile(profilePath, raw, { mode: 0o600 });
  const partial = { enabled: true, pythonPath: '/qualified/python3', sourceRoot: dir, profilePath,
    profileSha256: createHash('sha256').update(raw).digest('hex') };
  return { dir, profile, partial, config: resolveT3ControlConfig(partial) };
}
function fakeSpawn(answer, { error, code = 0, onInput, hold = false } = {}) {
  const calls = [];
  const spawn = (exe, args, options) => {
    const child = new EventEmitter();
    Object.assign(child, { stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
      pid: 12345, exitCode: null, signalCode: null });
    calls.push({ exe, args, options, child });
    let input = '';
    child.stdin.on('data', data => { input += data.toString(); });
    child.kill = signal => { child.signalCode = signal; setImmediate(() => child.emit('close', null)); return true; };
    child.stdin.on('finish', () => setImmediate(async () => {
      if (onInput) await onInput(input);
      if (hold) return;
      if (error) { child.emit('error', error); return; }
      child.stdout.write(typeof answer === 'string' ? answer : JSON.stringify(answer));
      child.exitCode = code;
      child.emit('close', code);
    }));
    setImmediate(() => child.emit('spawn'));
    return child;
  };
  return { spawn, calls };
}

test('T3 gateway defaults off; only closed explicit installed configuration', () => {
  assert.equal(resolveT3ControlConfig(undefined), null);
  assert.equal(resolveT3ControlConfig(false), null);
  for (const bad of [null, true, {}, { enabled: false }, { enabled: true, command: 'sh' }]) {
    assert.throws(() => resolveT3ControlConfig(bad));
  }
  assert.throws(() => createT3Controller({}, principal));
  assert.equal(T3_CONTROL_TOOLS.length, 20);
});
test('native tools require exact authenticated account and current profile', async t => {
  const f = await fixture(t);
  const s = fakeSpawn(observed('t3_fleet_environments'));
  const controller = createT3Controller(f.config, 'p:tunnel:other-account', { spawnProcess: s.spawn });
  await assert.rejects(() => controller.tools());
  assert.equal((await controller.call('t3_fleet_environments', {})).status, 'REJECTED');
  assert.equal(s.calls.length, 0);
});
test('catalog hides ungranted tools; callers cannot escape profile by name', async t => {
  const f = await fixture(t, ['t3_fleet_environments']);
  const s = fakeSpawn(observed('t3_fleet_environments'));
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  assert.deepEqual((await c.tools()).map(x => x.name), ['t3_fleet_environments']);
  assert.equal((await c.call('t3_thread_launch', {})).status, 'REJECTED');
  assert.equal((await c.call('start_process', { command: 'echo unsafe' })).status, 'UNAVAILABLE');
  assert.equal(s.calls.length, 0);
});
test('profile hash, ownership mode and symlink changes fail closed before process', async t => {
  const f = await fixture(t);
  const s = fakeSpawn(observed('t3_fleet_environments'));
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  await writeFile(f.partial.profilePath, JSON.stringify(f.profile) + ' ');
  assert.equal((await c.call('t3_fleet_environments', {})).status, 'REJECTED');
  await writeFile(f.partial.profilePath, JSON.stringify(f.profile));
  await chmod(f.partial.profilePath, 0o666);
  assert.equal((await c.call('t3_fleet_environments', {})).status, 'REJECTED');
  await chmod(f.partial.profilePath, 0o600);
  const alias = path.join(f.dir, 'alias.json');
  await symlink(f.partial.profilePath, alias);
  const d = createT3Controller(resolveT3ControlConfig({ ...f.partial, profilePath: alias }), principal, { spawnProcess: s.spawn });
  assert.equal((await d.call('t3_fleet_environments', {})).status, 'REJECTED');
  assert.equal(s.calls.length, 0);
});
test('port is fixed, shell disabled, principal injected by gateway and data only on stdin', async t => {
  const f = await fixture(t);
  let frame;
  const s = fakeSpawn(observed('t3_fleet_environments'), { onInput: input => { frame = JSON.parse(input); } });
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  const result = await c.call('t3_fleet_environments', {});
  assert.equal(result.status, 'OBSERVED');
  assert.deepEqual(frame, { schema: 'mastermind.t3_dot_call.v1', principal_key: principal,
    tool: 't3_fleet_environments', arguments: {} });
  assert.equal(s.calls.length, 1);
  assert.equal(s.calls[0].exe, '/qualified/python3');
  assert.equal(s.calls[0].options.shell, false);
  assert.equal(s.calls[0].args[2], 'integrations.session_bridge.t3_dot_port');
  assert.equal(s.calls[0].args.some(arg => arg.includes(principal)), false);
  assert.equal(Object.hasOwn(s.calls[0].options.env, 'OPENAI_API_KEY'), false);
});
test('unqualified modifying return stays unknown with original identity; never retries', async t => {
  const f = await fixture(t);
  for (const answer of ['broken json', '{"status":"OBSERVED"}', JSON.stringify(observed('another-tool'))]) {
    const s = fakeSpawn(answer);
    const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
    const value = await c.call('t3_thread_launch', { operation_id: 'op-original', environment_id: 'env-original' });
    assert.equal(value.status, 'EFFECT_UNKNOWN');
    assert.equal(value.original.operation_id, 'op-original');
    assert.equal(value.original.environment_id, 'env-original');
    assert.equal(value.port_helper.pid, 12345);
    assert.equal(value.retry_allowed, false);
    assert.equal(s.calls.length, 1);
  }
});
test('unqualified read return is unavailable, not an inferred mutation or empty result', async t => {
  const f = await fixture(t);
  const s = fakeSpawn('bad');
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  assert.equal((await c.call('t3_fleet_environments', {})).status, 'UNAVAILABLE');
});
test('known native refusal is retained without retry or fallback', async t => {
  const f = await fixture(t);
  const denied = { schema: 'mastermind.t3_dot_result.v1', status: 'REJECTED', code: 'CAPACITY_NOT_READY',
    original: {}, retry_allowed: false, parent_accepted: false };
  const s = fakeSpawn(denied);
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  assert.deepEqual(await c.call('t3_thread_launch', {}), denied);
  assert.equal(s.calls.length, 1);
});
test('profile revocation after native effect suppresses result and retains uncertainty', async t => {
  const f = await fixture(t);
  const s = fakeSpawn(observed('t3_thread_launch'), { onInput: () => writeFile(f.partial.profilePath, '{}') });
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  assert.equal((await c.call('t3_thread_launch', { operation_id: 'op' })).status, 'EFFECT_UNKNOWN');
});
test('abort before dispatch creates no process; after dispatch interrupts only owned port', async t => {
  const f = await fixture(t);
  const before = new AbortController(); before.abort();
  const s = fakeSpawn(observed('t3_thread_launch'), { hold: true });
  const c = createT3Controller(f.config, principal, { spawnProcess: s.spawn });
  assert.equal((await c.call('t3_thread_launch', {}, { signal: before.signal })).code, 'T3_CANCELLED_BEFORE_DISPATCH');
  assert.equal(s.calls.length, 0);
  const after = new AbortController();
  const result = c.call('t3_thread_launch', {}, { signal: after.signal });
  while (!s.calls.length) await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  after.abort();
  const value = await result;
  assert.equal(value.status, 'EFFECT_UNKNOWN');
  assert.equal(s.calls.length, 1);
  assert.equal(s.calls[0].child.signalCode, 'SIGTERM');
});
test('MCP envelope keeps structured status and errors', () => {
  assert.equal(t3ToolResult(observed('t3_fleet_environments')).isError, false);
  assert.equal(t3ToolResult({ status: 'UNAVAILABLE' }).isError, true);
});
