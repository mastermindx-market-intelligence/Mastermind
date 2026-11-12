import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { setTimeout as delay } from 'node:timers/promises';
import { Realtime } from '../realtime.mjs';
import { NativeSubscription, parseNotice } from '../native-watch.mjs';

const config = { enabled: true, companyId: 'company', environmentId: 'environment', projectIds: ['project'],
  nativeCliPath: '/qualified/bin.mjs', nodePath: '/node', t3Home: '/t3', t3Port: 3773 };
const connectionId = createHash('sha256').update(JSON.stringify([config.environmentId, config.t3Home, config.t3Port])).digest('hex');
const notice = (type, threadId = undefined) => ({ schema: 'mastermind.teamlink.native-watch.v1', type, environmentId: 'environment', ...(threadId ? { threadId } : {}) });
async function until(predicate) {
  for (let i = 0; i < 200; i++) { if (predicate()) return; await delay(5); }
  assert.fail('condition did not settle');
}
function fixture(count = 1, options = {}) {
  const bindings = Array.from({ length: count }, (_, n) => ({ issueId: `issue-${String(n).padStart(4, '0')}`, bindingId: `binding-${n}`,
    companyId: 'company', environmentId: 'environment', projectId: 'project', threadId: `thread-${n}`, connectionId }));
  const calls = [], watchers = [], pages = [];
  const store = { async bindingPage(_company, after, limit) {
    pages.push({ after, limit });
    const values = bindings.filter(x => after === null || x.issueId > after).slice(0, limit);
    return { bindings: structuredClone(values), nextCursor: values.length === limit ? values.at(-1).issueId : null };
  } };
  const service = { async reconcileBinding(issue, binding, args) { calls.push({ issue, binding }); if (options.work) return options.work(issue, args); } };
  const watchFactory = (ids, notify) => {
    const watcher = { ids, notify, stopped: false, ready: false,
      async stop() { this.stopped = true; },
      health() { return { readyThreads: this.ready ? ids.length : 0, requestedThreads: ids.length, error: null }; },
      emit(value) { if (value.type === 'ready') this.ready = true; notify(value); },
    };
    watchers.push(watcher); return watcher;
  };
  const live = new Realtime(config, store, service, { watchFactory, debounceMs: 1, minIntervalMs: 0, retryBaseMs: 5, ...options });
  return { live, bindings, calls, watchers, pages };
}

test('native notice projection rejects unbound roots, body leakage and invalid sequences', () => {
  const parse = x => parseNotice(JSON.stringify(x), 'environment', new Set(['root']));
  assert.equal(parse({ ...notice('changed', 'root'), sequence: 42 }).sequence, 42);
  for (const x of [notice('changed', 'other'), { ...notice('ready'), environmentId: 'other' },
    { ...notice('changed', 'root'), text: 'private body' }, { ...notice('changed', 'root'), sequence: -1 },
    { ...notice('error'), code: 'raw credential or path' }, { ...notice('heartbeat'), arbitrary: true }, notice('changed')]) {
    assert.throws(() => parse(x));
  }
  assert.throws(() => parseNotice(' '.repeat(4097), 'environment', new Set()), /LIMIT/);
});

test('actual native helper codes preserve renewal, transport and refusal semantics', () => {
  const parse = code => parseNotice(JSON.stringify({ ...notice('error'), code }), 'environment', new Set(['root']));
  assert.equal(parse('subscription_closed').code, 'WATCH_CONNECTION_CLOSED');
  assert.equal(parse('connection_lost').code, 'WATCH_CONNECTION_UNAVAILABLE');
  assert.equal(parse('server_unreachable').code, 'WATCH_SERVER_UNREACHABLE');
  assert.equal(parse('authorization_failed').code, 'WATCH_AUTHORIZATION_FAILED');
  assert.equal(parse('qualification_incomplete').code, 'WATCH_QUALIFICATION_INCOMPLETE');
  assert.equal(parse('lifetime_expired').code, 'WATCH_SESSION_ROTATE');
  assert.equal(parse('environment_mismatch').code, 'WATCH_ENVIRONMENT_MISMATCH');
  assert.equal(parse('session_failed').code, 'WATCH_SESSION_FAILED');
  for (const code of ['unknown_native_error', 'constructor', 'toString', 123]) assert.throws(() => parse(code));
});

test('native child holds only allowlisted environment, frames bursts and closes with its owner', async () => {
  let child, launched;
  const spawnProcess = (...args) => {
    launched = args; child = new EventEmitter();
    child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.stdin.on('finish', () => queueMicrotask(() => child.emit('close', 0)));
    child.kill = () => child.emit('close', 0); return child;
  };
  const seen = [];
  const subscription = new NativeSubscription(config, ['root'], x => seen.push(x), { spawnProcess });
  assert.deepEqual(Object.keys(launched[2].env).sort(), ['HOME', 'PATH', 'T3CODE_HOME', 'TMPDIR']);
  assert.equal(launched[2].shell, false);
  child.stdout.write(JSON.stringify(notice('ready', 'root')) + '\n' + JSON.stringify(notice('changed', 'root')) + '\n');
  assert.equal(seen.length, 2); assert.equal(subscription.health().readyThreads, 1);
  await subscription.stop();
  assert.equal(seen.some(x => x.type === 'closed'), false);
});

test('loss of native process immediately invalidates connection health', async () => {
  let child;
  const subscription = new NativeSubscription(config, ['root'], () => {}, { spawnProcess: () => {
    child = new EventEmitter(); child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.kill = () => {}; return child;
  } });
  child.stdout.write(JSON.stringify(notice('ready')) + '\n');
  child.emit('close', 1); await subscription.done;
  assert.equal(subscription.health().readyThreads, 0);
  assert.equal(subscription.health().error, 'WATCH_CONNECTION_CLOSED');
});

test('all sixty-five bindings receive hot subscriptions and initial catch-up beyond the old batch limit', async t => {
  const f = fixture(65); t.after(() => f.live.stop()); await f.live.refresh();
  assert.equal(f.watchers.flatMap(x => x.ids).length, 65);
  await until(() => f.calls.length === 65);
  assert.equal(new Set(f.calls.map(x => x.issue)).size, 65);
  assert.equal(f.live.health().coverageComplete, true);
});

test('bounded inventory pages and native batches cover every included binding', async t => {
  const f = fixture(260); t.after(() => f.live.stop()); await f.live.refresh();
  assert.deepEqual(f.watchers.map(x => x.ids.length), [128, 128, 4]);
  assert.equal(f.pages.length, 3); assert.equal(f.live.health().coveredBindings, 260);
});

test('event bursts coalesce with one in-flight operation per binding and bounded global concurrency', async t => {
  let finish, entered = 0, active = 0, maximum = 0;
  const held = new Promise(resolve => { finish = resolve; });
  const counts = new Map();
  const f = fixture(3, { work: async issue => {
    entered++; active++; maximum = Math.max(maximum, active);
    counts.set(issue, (counts.get(issue) || 0) + 1);
    assert.equal(counts.get(issue), 1);
    await held; counts.set(issue, counts.get(issue) - 1); active--;
  } });
  t.after(async () => { finish(); await f.live.stop(); }); await f.live.refresh();
  await until(() => entered === 2);
  for (let n = 0; n < 10000; n++) f.watchers[0].emit(notice('changed', 'thread-0'));
  assert.ok(f.live.dirty.size <= 3); assert.equal(f.live.inflight.size, 2);
  finish(); await until(() => f.live.inflight.size === 0 && f.live.dirty.size === 0);
  assert.equal(maximum, 2); assert.ok(f.calls.filter(x => x.issue === 'issue-0000').length <= 2);
});

test('a disconnected listener reopens and catches up without any message-send method', async t => {
  const f = fixture(); t.after(() => f.live.stop()); await f.live.refresh();
  await until(() => f.calls.length === 1);
  f.watchers[0].emit({ type: 'closed', code: 'WATCH_CONNECTION_CLOSED' });
  await until(() => f.watchers.length === 2 && f.calls.length >= 2);
  assert.equal(f.watchers[0].stopped, true); assert.equal(f.live.health().reconnects, 1);
});

test('old subscription callbacks cannot schedule work after a binding replacement', async t => {
  const f = fixture(); t.after(() => f.live.stop()); await f.live.refresh();
  await until(() => f.calls.length === 1);
  const old = f.watchers[0]; f.bindings[0].bindingId = 'replacement'; f.bindings[0].threadId = 'new-root';
  await f.live.refresh(); await until(() => f.calls.some(x => x.binding === 'replacement'));
  const before = f.calls.length;
  old.emit(notice('changed', 'thread-0')); await delay(15);
  assert.equal(f.calls.length, before); assert.equal(old.stopped, true);
});

test('overflow coverage is explicit and preserves scheduled recovery without an unbounded dirty set', async t => {
  const f = fixture(10, { maxBindings: 8 }); t.after(() => f.live.stop()); await f.live.refresh();
  assert.equal(f.live.health().coveredBindings, 8); assert.equal(f.live.health().observedBindings, 9);
  assert.equal(f.live.health().coverageComplete, false);
  assert.equal(f.live.health().recovery, 'native_scheduled_reconcile');
  assert.match(f.live.health().error, /COVERAGE/); assert.ok(f.live.dirty.size <= 8);
});

test('source scope mismatch is never subscribed and appears as incomplete coverage', async t => {
  const f = fixture(2); t.after(() => f.live.stop()); f.bindings[1].connectionId = 'another-connection';
  await f.live.refresh(); assert.deepEqual(f.watchers[0].ids, ['thread-0']);
  assert.equal(f.live.health().skippedBindings, 1); assert.equal(f.live.health().coverageComplete, false);
});

test('tool/rebind and event reconciliation share the same issue exclusion boundary', async t => {
  const f = fixture(); t.after(() => f.live.stop());
  let release, entered; const started = new Promise(r => { entered = r; });
  const tool = f.live.exclusive('issue-0000', async () => { entered(); await new Promise(r => { release = r; }); });
  await started; await f.live.refresh(); await delay(15);
  assert.equal(f.calls.length, 0); release(); await tool;
  await until(() => f.calls.length === 1);
});

test('shutdown awaits owned in-flight work and rejects late callbacks', async () => {
  let release;
  const held = new Promise(resolve => { release = resolve; });
  const f = fixture(1, { work: async () => held }); await f.live.refresh();
  await until(() => f.calls.length === 1);
  let stopped = false; const stopping = f.live.stop().then(() => { stopped = true; });
  await delay(10); assert.equal(stopped, false);
  f.watchers[0].emit(notice('changed', 'thread-0')); release(); await stopping;
  assert.equal(f.calls.length, 1); assert.equal(f.live.dirty.size, 0); assert.equal(f.live.watchers.length, 0);
});

test('one native notification drains a paginated backlog without waiting for another event', async t => {
  let pages = 0;
  const f = fixture(1, { work: async () => ({ ok: true, more: ++pages < 4 }) });
  t.after(() => f.live.stop()); await f.live.refresh();
  await until(() => pages === 4); await delay(15);
  assert.equal(f.calls.length, 4); assert.equal(f.live.dirty.size, 0);
});

test('locked issues do not consume slots needed by unrelated ready roots', async t => {
  const f = fixture(3); const releases = [];
  const held = [0, 1].map(n => f.live.exclusive(`issue-000${n}`, () => new Promise(r => releases.push(r))));
  t.after(async () => { releases.forEach(r => r()); await Promise.all(held); await f.live.stop(); });
  await until(() => releases.length === 2); await f.live.refresh();
  await until(() => f.calls.length === 1);
  assert.equal(f.calls[0].issue, 'issue-0002'); assert.equal(f.live.dirty.size, 2);
  releases.forEach(r => r()); await Promise.all(held);
  await until(() => f.calls.length === 3);
});

test('a held receipt error does not suppress another receipt with proven catch-up progress', async t => {
  let pages = 0;
  const f = fixture(1, { work: async () => ({ ok: false, error: 'ORIGINAL_INCOMING_ITEM_UNAVAILABLE', more: ++pages < 3 }) });
  t.after(() => f.live.stop()); await f.live.refresh();
  await until(() => pages === 3 && f.live.inflight.size === 0); await delay(15);
  assert.equal(f.calls.length, 3); assert.equal(f.live.dirty.size, 0);
  assert.equal(f.live.health().errors.observations.count, 1);
  assert.equal(f.live.health().lastReconciledAt, null);
});

test('ready and unrelated success cannot clear an original observation failure', async t => {
  let failing = true;
  const f = fixture(2, { work: async issue => ({ ok: !(failing && issue === 'issue-0000'), more: false, error: 'NATIVE_UNAVAILABLE' }) });
  t.after(() => f.live.stop()); await f.live.refresh();
  await until(() => f.calls.length === 2 && f.live.inflight.size === 0);
  assert.equal(f.live.health().errors.observations.count, 1);
  f.watchers[0].emit(notice('ready')); await until(() => f.calls.length >= 4 && f.live.inflight.size === 0);
  assert.equal(f.live.health().error, 'REALTIME_RECONCILE_UNAVAILABLE');
  assert.deepEqual(f.live.health().errors.observations.examples, [{ issueId: 'issue-0000', code: 'NATIVE_UNAVAILABLE' }]);
  failing = false; f.live.nudge('issue-0000'); await until(() => f.live.health().errors.observations.count === 0);
  assert.equal(f.live.health().error, null);
});

test('permission or protocol refusal does not start a reconnection loop', async t => {
  const f = fixture(); t.after(() => f.live.stop()); await f.live.refresh();
  f.watchers[0].emit({ type: 'unavailable', code: 'WATCH_SCOPE_DENIED' });
  await delay(25); assert.equal(f.watchers.length, 1); assert.equal(f.live.health().errors.watch, 'WATCH_SCOPE_DENIED');
});

test('paused lifecycle retains incoming notices but admits no new source work', async t => {
  const f = fixture(); t.after(() => f.live.stop()); await f.live.refresh(); await until(() => f.calls.length === 1);
  f.live.pause(); f.watchers[0].emit(notice('changed', 'thread-0')); await delay(15);
  assert.equal(f.calls.length, 1); assert.equal(f.live.dirty.size, 1);
  f.live.resume(); await until(() => f.calls.length === 2);
});
