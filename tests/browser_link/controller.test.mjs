import test from 'node:test';
import assert from 'node:assert/strict';
import { SharedTabController } from '../../integrations/mastermind_browser_link/extension/controller.mjs';

const START = 1_000_000;
function setup(overrides = {}) {
  let clock = START, serial = 0, reads = 0, writes = 0;
  const port = {
    async read(_request, { assertCurrent }) { assertCurrent(); reads++; return { text: 'fixture only' }; },
    async mutate(_request, { beforeEffect }) { beforeEffect(); writes++; return { returned: true }; },
    invalidate() {},
    ...overrides,
  };
  const control = new SharedTabController({ adapter: port, connectionGeneration: 'connection-1', now: () => clock, nonce: () => `nonce-${++serial}` });
  const tab = control.share(7, 'https://example.test');
  const command = (name = 'snapshot', args = {}, extra = {}) => ({
    schema: 'mastermind.browser_link.command.v1', request_id: `request-${++serial}`,
    connection_generation: 'connection-1', tab_id: 7, consent_id: tab.consent_id,
    document_revision: tab.document_revision, expires_at_ms: START + 20_000,
    command: name, args,
    ...(!['snapshot', 'screenshot'].includes(name) ? { writer: { holder_ref: 'writer-a', fence: 1 } } : {}),
    ...extra,
  });
  return { control, command, port, tab, tick: ms => clock += ms, counts: () => ({ reads, writes }) };
}
function deferred() { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; }

test('explicitly shared tab can be observed', async () => {
  const s = setup(); const result = await s.control.execute(s.command());
  assert.equal(result.status, 'completed'); assert.equal(result.effect, 'NOT_APPLIED');
  assert.equal(result.output.text, 'fixture only'); assert.equal(s.counts().reads, 1);
});

test('unshared tab is rejected before an adapter read', async () => {
  const s = setup(); const result = await s.control.execute(s.command('snapshot', {}, { tab_id: 8 }));
  assert.equal(result.code, 'TAB_NOT_SHARED'); assert.deepEqual(s.counts(), { reads: 0, writes: 0 });
});

test('connection generation and consent are exact', async () => {
  const s = setup();
  assert.equal((await s.control.execute(s.command('snapshot', {}, { connection_generation: 'old' }))).code, 'STALE_CONNECTION');
  assert.equal((await s.control.execute(s.command('snapshot', {}, { consent_id: 'foreign' }))).code, 'CONSENT_MISMATCH');
  assert.equal(s.counts().reads, 0);
});

test('navigation/document change rejects a prepared stale command', async () => {
  const s = setup(); const request = s.command('click', { element_ref: 'element-1' });
  s.control.invalidate(7);
  assert.equal((await s.control.execute(request)).code, 'STALE_DOCUMENT'); assert.equal(s.counts().writes, 0);
});

test('two authorized readers overlap without allocating a writer', async () => {
  const gate = deferred(); let concurrent = 0, maximum = 0;
  const s = setup({ async read(_req, { assertCurrent }) { concurrent++; maximum = Math.max(maximum, concurrent); await gate.promise; assertCurrent(); concurrent--; return {}; } });
  const a = s.control.execute(s.command()), b = s.control.execute(s.command());
  await Promise.resolve(); assert.equal(maximum, 2); gate.resolve();
  assert.equal((await a).status, 'completed'); assert.equal((await b).status, 'completed');
});

test('native writer races are refused rather than silently queued', async () => {
  const gate = deferred(); let effects = 0;
  const s = setup({ async mutate(_req, { beforeEffect }) { await gate.promise; beforeEffect(); effects++; return {}; } });
  const a = s.control.execute(s.command('click', { element_ref: 'element-1' }));
  const b = await s.control.execute(s.command('click', { element_ref: 'element-2' }, { writer: { holder_ref: 'writer-b', fence: 2 } }));
  assert.equal(b.code, 'TAB_BUSY'); assert.equal(b.effect, 'NOT_APPLIED'); gate.resolve();
  assert.equal((await a).effect, 'APPLIED'); assert.equal(effects, 1);
});

test('a read cannot claim a stable snapshot while a native writer is active', async () => {
  const gate = deferred();
  const s = setup({ async mutate(_r, { beforeEffect }) { await gate.promise; beforeEffect(); return {}; } });
  const a = s.control.execute(s.command('click', { element_ref: 'element-1' }));
  assert.equal((await s.control.execute(s.command())).code, 'TAB_BUSY'); gate.resolve(); await a;
});

test('a writer waits at its owner when readers are active, not in an extension queue', async () => {
  const gate = deferred(); const s = setup({ async read(_r, { assertCurrent }) { await gate.promise; assertCurrent(); return {}; } });
  const a = s.control.execute(s.command());
  assert.equal((await s.control.execute(s.command('scroll', { delta_x: 0, delta_y: 50 }))).code, 'TAB_BUSY');
  gate.resolve(); await a;
});

test('different shared tabs do not share one global native-action lock', async () => {
  const gate = deferred(); let started = 0;
  const s = setup({ async mutate(_r, { beforeEffect }) { beforeEffect(); started++; await gate.promise; return {}; } });
  const other = s.control.share(8, 'https://example.test');
  const a = s.control.execute(s.command('scroll', { delta_x: 0, delta_y: 20 }));
  const b = s.control.execute(s.command('scroll', { delta_x: 0, delta_y: 20 }, { tab_id: 8, consent_id: other.consent_id }));
  await Promise.resolve(); assert.equal(started, 2); gate.resolve(); await Promise.all([a, b]);
});

test('revocation during async lookup is checked immediately before effect', async () => {
  const gate = deferred(); let effects = 0;
  const s = setup({ async mutate(_r, { beforeEffect }) { await gate.promise; beforeEffect(); effects++; return {}; } });
  const pending = s.control.execute(s.command('click', { element_ref: 'element-1' }));
  s.control.revoke(7); gate.resolve(); const result = await pending;
  assert.equal(result.effect, 'NOT_APPLIED'); assert.equal(result.code, 'TAB_NOT_SHARED'); assert.equal(effects, 0);
});

test('expiration during async lookup is checked immediately before effect', async () => {
  const gate = deferred(); let effects = 0;
  const s = setup({ async mutate(_r, { beforeEffect }) { await gate.promise; beforeEffect(); effects++; return {}; } });
  const pending = s.control.execute(s.command('click', { element_ref: 'element-1' }));
  s.tick(21_000); gate.resolve(); const result = await pending;
  assert.equal(result.effect, 'NOT_APPLIED'); assert.equal(result.code, 'EXPIRED'); assert.equal(effects, 0);
});

test('document change during a read returns stale rather than reusable output', async () => {
  const gate = deferred(); const s = setup({ async read() { await gate.promise; return { secret: 'not returned' }; } });
  const pending = s.control.execute(s.command()); s.control.invalidate(7); gate.resolve();
  const result = await pending; assert.equal(result.code, 'STALE_DOCUMENT'); assert.equal(result.output, undefined);
});

test('exact duplicate mutation returns original receipt, not another click', async () => {
  const s = setup(); const request = s.command('click', { element_ref: 'element-1' });
  const first = await s.control.execute(request), replay = await s.control.execute(request);
  assert.equal(first.effect, 'APPLIED'); assert.equal(replay.effect, 'APPLIED');
  assert.equal(replay.replayed, true); assert.equal(s.counts().writes, 1);
});

test('changed payload cannot reuse a completed request identity', async () => {
  const s = setup(); const request = s.command('click', { element_ref: 'element-1' });
  await s.control.execute(request);
  const result = await s.control.execute({ ...request, args: { element_ref: 'different-element' } });
  assert.equal(result.code, 'REQUEST_ID_CONFLICT'); assert.equal(s.counts().writes, 1);
});

test('a duplicate while the original is pending never dispatches a second effect', async () => {
  const gate = deferred(); let effects = 0;
  const s = setup({ async mutate(_r, { beforeEffect }) { beforeEffect(); effects++; await gate.promise; return {}; } });
  const request = s.command('click', { element_ref: 'element-1' }); const pending = s.control.execute(request);
  const duplicate = await s.control.execute(request);
  assert.equal(duplicate.status, 'pending'); assert.equal(duplicate.effect, 'EFFECT_UNKNOWN');
  gate.resolve(); await pending; assert.equal(effects, 1);
});

test('revocation prevents disclosure of an old cached read result', async () => {
  const s = setup(); const request = s.command(); await s.control.execute(request); s.control.revoke(7);
  const result = await s.control.execute(request); assert.equal(result.code, 'TAB_NOT_SHARED'); assert.equal(result.output, undefined);
});

test('post-dispatch transport failure is uncertain and fences subsequent writes', async () => {
  const s = setup({ async mutate(_r, { beforeEffect }) { beforeEffect(); throw new Error('transport included secret'); } });
  const result = await s.control.execute(s.command('click', { element_ref: 'element-1' }));
  assert.equal(result.effect, 'EFFECT_UNKNOWN'); assert.equal(result.code, 'ACTUATOR_FAILURE');
  assert.equal(JSON.stringify(result).includes('secret'), false);
  const next = await s.control.execute(s.command('click', { element_ref: 'element-2' }));
  assert.equal(next.code, 'EFFECT_UNRESOLVED');
});

test('re-sharing the same tab does not clear unresolved effects', async () => {
  const s = setup({ async mutate(_r, { beforeEffect }) { beforeEffect(); throw Error(); } });
  await s.control.execute(s.command('click', { element_ref: 'element-1' })); s.control.revoke(7);
  const fresh = s.control.share(7, 'https://example.test');
  const next = await s.control.execute(s.command('click', { element_ref: 'element-2' }, { consent_id: fresh.consent_id }));
  assert.equal(next.code, 'EFFECT_UNRESOLVED');
});

test('read-only reconciliation remains possible while writes are quarantined', async () => {
  const s = setup({ async mutate(_r, { beforeEffect }) { beforeEffect(); throw Error(); } });
  await s.control.execute(s.command('click', { element_ref: 'element-1' }));
  const current = s.control.inventory()[0];
  const read = await s.control.execute(s.command('snapshot', {}, { document_revision: current.document_revision }));
  assert.equal(read.status, 'completed');
});

test('stale writer fences and same-fence holder substitution are refused', async () => {
  const s = setup(); await s.control.execute(s.command('scroll', { delta_x: 0, delta_y: 1 }, { writer: { holder_ref: 'writer-a', fence: 4 } }));
  const revision = s.control.inventory()[0].document_revision;
  const stale = await s.control.execute(s.command('scroll', { delta_x: 0, delta_y: 1 }, { document_revision: revision, writer: { holder_ref: 'writer-a', fence: 3 } }));
  const foreign = await s.control.execute(s.command('scroll', { delta_x: 0, delta_y: 1 }, { document_revision: revision, writer: { holder_ref: 'writer-b', fence: 4 } }));
  assert.equal(stale.code, 'STALE_WRITER'); assert.equal(foreign.code, 'WRITER_MISMATCH');
});

test('cross-origin navigation is refused even with a valid writer envelope', async () => {
  const s = setup(); const result = await s.control.execute(s.command('navigate', { url: 'https://other.test/' }));
  assert.equal(result.code, 'ORIGIN_NOT_SHARED'); assert.equal(s.counts().writes, 0);
});

test('same-origin navigation succeeds and advances document revision', async () => {
  const s = setup(); const result = await s.control.execute(s.command('navigate', { url: 'https://example.test/next' }));
  assert.equal(result.effect, 'APPLIED'); assert.equal(s.control.inventory()[0].document_revision, 1);
});

test('disconnect invalidates all targets and does not silently recreate sharing', async () => {
  const s = setup(); s.control.disconnect();
  assert.equal((await s.control.execute(s.command())).code, 'DISCONNECTED'); assert.equal(s.control.inventory().length, 0);
});

test('adapter claiming a mutation without an effect guard fails closed', async () => {
  const s = setup({ async mutate() { return {}; } });
  const result = await s.control.execute(s.command('click', { element_ref: 'element-1' }));
  assert.equal(result.code, 'ACTUATOR_CONTRACT_VIOLATION'); assert.equal(result.effect, 'EFFECT_UNKNOWN');
});

test('stop-and-re-share cannot reset the native in-flight interlock', async () => {
  const gate = deferred(); let effects = 0;
  const s = setup({ async mutate(_r, { beforeEffect }) { beforeEffect(); effects++; await gate.promise; return {}; } });
  const first = s.control.execute(s.command('click', { element_ref: 'element-1' }));
  s.control.revoke(7); const shared = s.control.share(7, 'https://example.test');
  const second = s.control.execute(s.command('click', { element_ref: 'element-2' }, { consent_id: shared.consent_id, writer: { holder_ref: 'writer-b', fence: 2 } }));
  try { const observed = await Promise.race([second, Promise.resolve({ code: 'WRONGLY_WAITING_FOR_EFFECT' })]); assert.equal(observed.code, 'TAB_BUSY'); }
  finally { gate.resolve(); await Promise.all([first, second]); }
  assert.equal(effects, 1);
});

test('reader concurrency is bounded without allocating a local work queue', async () => {
  const gate = deferred(); const s = setup({ async read(_r, { assertCurrent }) { await gate.promise; assertCurrent(); return {}; } });
  const pending = Array.from({ length: 4 }, () => s.control.execute(s.command()));
  const rejected = s.control.execute(s.command());
  try { const observed = await Promise.race([rejected, Promise.resolve({ code: 'WRONGLY_WAITING_FOR_READ' })]); assert.equal(observed.code, 'READ_LIMIT'); }
  finally { gate.resolve(); await Promise.all([...pending, rejected]); }
});

test('shared inventory cannot exceed native protocol limit', () => {
  const c = new SharedTabController({ adapter:{async read(){},async mutate(){}}, connectionGeneration:'g' });
  for(let i=0;i<64;i++) c.share(i,'https://example.test');
  assert.throws(()=>c.share(64,'https://example.test'),{code:'SHARE_LIMIT'});
  assert.equal(c.inventory().length,64);
  c.share(0,'https://example.test');assert.equal(c.inventory().length,64);
});
