import test from 'node:test';
import assert from 'node:assert/strict';
import { ChromePort } from '../../integrations/mastermind_browser_link/extension/chrome-port.mjs';
import { SharedTabController } from '../../integrations/mastermind_browser_link/extension/controller.mjs';
import { COMMAND_SCHEMA } from '../../integrations/mastermind_browser_link/extension/protocol.mjs';

function event() {
  const listeners = new Set();
  return { addListener: f => listeners.add(f), removeListener: f => listeners.delete(f),
    emit: (...args) => { for (const f of [...listeners]) f(...args); }, size: () => listeners.size };
}
function deferred() { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; }
function setup(options = {}) {
  let serial = 0, nextTab = 100, nextWindow = 20, attachments = 0;
  const tabs = new Map([[7, { id: 7, windowId: 12, incognito: false, status: 'complete', url: 'https://anchor.test/' }]]);
  const calls = [], gets = [];
  const api = {
    tabs: {
      onUpdated: event(), onRemoved: event(), onReplaced: event(),
      async get(id) {
        gets.push(id);
        if (options.get) return options.get(id, tabs);
        if (!tabs.has(id)) throw new Error('closed');
        return structuredClone(tabs.get(id));
      },
      async create(args) {
        calls.push({ kind: 'tab', args });
        if (options.failCreate) throw new Error('response lost');
        const result = { id: nextTab++, windowId: args.windowId, incognito: false, status: options.status ?? 'complete',
          url: options.url ?? args.url, ...(options.pendingUrl ? { pendingUrl: options.pendingUrl } : {}) };
        tabs.set(result.id, result);
        return structuredClone(result);
      },
    },
    windows: {
      async create(args) {
        calls.push({ kind: 'window', args });
        const windowId = nextWindow++;
        const child = { id: nextTab++, windowId, incognito: false, status: 'complete', url: args.url };
        tabs.set(child.id, child);
        return { id: windowId, type: 'normal', incognito: false, ...(options.noWindowTabs ? {} : { tabs: [structuredClone(child)] }) };
      },
    },
    debugger: { async attach() { attachments++; }, async sendCommand() { throw new Error('unexpected debugger command'); } },
  };
  const adapter = new ChromePort({ chrome: api });
  const control = new SharedTabController({ adapter, connectionGeneration: 'connection', nonce: () => 'nonce-' + ++serial });
  control.share(7, 'https://anchor.test', options.allowCreate ?? true);
  const command = (name = 'create_tab', extra = {}) => {
    const id = extra.tab_id ?? 7, shared = control.inventory().find(t => t.tab_id === id);
    return { schema: COMMAND_SCHEMA, request_id: 'request-' + ++serial,
      connection_generation: 'connection', tab_id: id, consent_id: shared.consent_id,
      document_revision: shared.document_revision, expires_at_ms: Date.now() + 20_000,
      command: name, args: { url: 'https://child.test/page' }, writer: { holder_ref: 'owner', fence: serial }, ...extra };
  };
  return { api, adapter, control, command, calls, gets, tabs, attachments: () => attachments };
}
function noWaiters(s) {
  for (const name of ['onUpdated', 'onRemoved', 'onReplaced']) assert.equal(s.api.tabs[name].size(), 0);
}

test('creation requires explicit permission and uses no implicit current window or debugger', async () => {
  const denied = setup({ allowCreate: false });
  const result = await denied.control.execute(denied.command());
  assert.equal(result.code, 'CREATION_NOT_SHARED'); assert.equal(result.effect, 'NOT_APPLIED');
  assert.equal(denied.calls.length, 0);
  const s = setup(), request = s.command();
  const out = await s.control.execute(request);
  assert.equal(out.effect, 'APPLIED'); assert.equal(out.output.sharing.state, 'shared');
  assert.deepEqual(s.calls, [{ kind: 'tab', args: { windowId: 12, url: 'https://child.test/page', active: false } }]);
  assert.equal(s.attachments(), 0);
  const child = s.control.inventory().find(t => t.tab_id === out.output.created.tab_id);
  assert.equal(child.origin, 'https://child.test'); assert.equal(child.allow_create, false);
  assert.notEqual(child.consent_id, request.consent_id);
  const duplicate = await s.control.execute(request);
  assert.equal(duplicate.effect, 'APPLIED'); assert.equal(duplicate.replayed, true); assert.equal(s.calls.length, 1);
  noWaiters(s);
});

test('a fresh window has a fixed non-incognito normal context and exact returned child', async () => {
  const s = setup();
  const result = await s.control.execute(s.command('create_window'));
  assert.equal(result.effect, 'APPLIED'); assert.equal(result.output.sharing.state, 'shared');
  assert.deepEqual(result.output.created, { kind: 'window', window_id: 20, tab_id: 100 });
  assert.deepEqual(s.calls[0].args, { url: 'https://child.test/page', type: 'normal', focused: false, incognito: false });
  assert.equal(s.attachments(), 0); noWaiters(s);
});

test('a known-created window without initial tab data remains applied and unshared', async () => {
  const s = setup({ noWindowTabs: true });
  const result = await s.control.execute(s.command('create_window'));
  assert.equal(result.effect, 'APPLIED');
  assert.deepEqual(result.output.created, { kind: 'window', window_id: 20 });
  assert.equal(result.output.sharing.state, 'not_shared');
  assert.deepEqual(s.gets, [7]); assert.equal(s.control.inventory().length, 1); noWaiters(s);
});

test('redirected or still-pending children do not revoke evidence of creation', async () => {
  for (const options of [{ url: 'https://redirect.test/' }, { pendingUrl: 'https://child.test/next' }, { status: 'loading' }]) {
    const s = setup(options);
    const result = await s.control.execute(s.command('create_tab', { expires_at_ms: Date.now() + 35 }));
    assert.equal(result.effect, 'APPLIED'); assert.equal(result.status, 'completed');
    assert.equal(result.output.sharing.state, 'not_shared'); assert.equal(s.control.inventory().length, 1);
    assert.equal(s.control.inventory()[0].state, 'shared'); noWaiters(s);
  }
});

test('a lost create reply remains unknown and forbids another mutation', async () => {
  const s = setup({ failCreate: true });
  const out = await s.control.execute(s.command());
  assert.equal(out.effect, 'EFFECT_UNKNOWN');
  assert.equal((await s.control.execute(s.command())).code, 'EFFECT_UNRESOLVED');
  assert.equal(s.calls.length, 1);
});

test('event during child readback invalidates its old origin and forces a fresh observation', async () => {
  const entered = deferred(), gate = deferred(); let held = false;
  const s = setup({ async get(id, tabs) {
    const snapshot = structuredClone(tabs.get(id));
    if (id >= 100 && !held) { held = true; entered.resolve(); await gate.promise; }
    return snapshot;
  } });
  const pending = s.control.execute(s.command());
  await entered.promise;
  s.tabs.get(100).url = 'https://redirect.test/';
  s.api.tabs.onUpdated.emit(100, { status: 'complete', url: 'https://redirect.test/' });
  gate.resolve();
  const result = await pending;
  assert.equal(result.effect, 'APPLIED'); assert.equal(result.output.sharing.code, 'CREATED_TAB_ORIGIN_CHANGED');
  assert.equal(s.gets.filter(id => id === 100).length, 2);
  assert.equal(s.control.inventory().length, 1); noWaiters(s);
});

for (const change of ['removed', 'replaced', 'revoke', 'reshare', 'disconnect', 'human_share']) {
  test('known creation stays applied without late consent after ' + change, async () => {
    const entered = deferred(), gate = deferred();
    const s = setup({ async get(id, tabs) {
      const snapshot = structuredClone(tabs.get(id));
      if (id >= 100) { entered.resolve(); await gate.promise; }
      return snapshot;
    } });
    const pending = s.control.execute(s.command());
    await entered.promise;
    let human;
    if (change === 'removed') s.api.tabs.onRemoved.emit(100);
    if (change === 'replaced') s.api.tabs.onReplaced.emit(101, 100);
    if (change === 'revoke') s.control.revoke(7);
    if (change === 'reshare') s.control.share(7, 'https://anchor.test', true);
    if (change === 'disconnect') s.control.disconnect();
    if (change === 'human_share') human = s.control.share(100, 'https://child.test', true);
    gate.resolve();
    const result = await pending;
    assert.equal(result.effect, 'APPLIED'); assert.equal(result.status, 'completed');
    const child = s.control.inventory().find(t => t.tab_id === 100);
    if (human) assert.deepEqual(child, human); else assert.equal(child, undefined);
    noWaiters(s);
  });
}

test('two permitted anchors create concurrently, with reservations preventing overcommit', async () => {
  const entered = deferred(), gate = deferred(); let arrivals = 0;
  const s = setup({ async get(id, tabs) {
    if (id >= 100) { if (++arrivals === 2) entered.resolve(); await gate.promise; }
    return structuredClone(tabs.get(id));
  } });
  s.tabs.set(8, { ...s.tabs.get(7), id: 8 });
  s.control.share(8, 'https://anchor.test', true);
  const first = s.control.execute(s.command()), second = s.control.execute(s.command('create_tab', { tab_id: 8 }));
  await entered.promise; assert.equal(s.calls.length, 2); gate.resolve();
  assert.deepEqual((await Promise.all([first, second])).map(r => r.effect), ['APPLIED', 'APPLIED']);
  noWaiters(s);
  const entered2 = deferred(), gate2 = deferred();
  const full = setup({ async get(id, tabs) {
    if (id >= 100) { entered2.resolve(); await gate2.promise; }
    return structuredClone(tabs.get(id));
  } });
  full.tabs.set(8, { ...full.tabs.get(7), id: 8 });
  for (let id = 8; id < 70; id++) full.control.share(id, 'https://anchor.test', true);
  const reserved = full.control.execute(full.command());
  await entered2.promise;
  const refused = await full.control.execute(full.command('create_tab', { tab_id: 8 }));
  assert.equal(refused.code, 'CREATION_LIMIT'); assert.equal(refused.effect, 'NOT_APPLIED');
  gate2.resolve(); assert.equal((await reserved).effect, 'APPLIED');
  assert.equal(full.control.inventory().length, 64); assert.equal(full.calls.length, 1); noWaiters(full);
});

test('unshared dispatched creations still consume the bounded connection creation budget', async () => {
  const s = setup({ url: 'https://redirect.test/' });
  for (let i = 0; i < 64; i++) assert.equal((await s.control.execute(s.command())).effect, 'APPLIED');
  assert.equal(s.control.inventory().length, 1);
  assert.equal((await s.control.execute(s.command())).code, 'CREATION_LIMIT');
  assert.equal(s.calls.length, 64); noWaiters(s);
});

test('a retained actuator guard cannot grant late consent after a completed unshared creation', async () => {
  let saved, serial = 0;
  const adapter = { invalidate() {}, async read() {}, async mutate(_request, guard) {
    saved = guard; guard.beforeEffect(); guard.creationConfirmed({ kind: 'tab', tab_id: 100, window_id: 12 });
    return { kind: 'browser_creation', created: { kind: 'tab', tab_id: 100, window_id: 12 }, sharing: { state: 'not_shared' } };
  } };
  const control = new SharedTabController({ adapter, connectionGeneration: 'connection', nonce: () => 'n-' + ++serial });
  const tab = control.share(7, 'https://anchor.test', true);
  const result = await control.execute({ schema: COMMAND_SCHEMA, request_id: 'one', connection_generation: 'connection',
    tab_id: 7, consent_id: tab.consent_id, document_revision: 0, expires_at_ms: Date.now() + 20_000,
    command: 'create_tab', args: { url: 'https://child.test/' }, writer: { holder_ref: 'owner', fence: 1 } });
  assert.equal(result.effect, 'APPLIED');
  assert.throws(() => saved.shareCreated({ id: 100, windowId: 12, status: 'complete', incognito: false, url: 'https://child.test/' }), { code: 'ACTION_CLOSED' });
  assert.throws(() => saved.beforeEffect(), { code: 'ACTION_CLOSED' });
  assert.equal(control.inventory().length, 1);
});

test('a slow creation response does not receive a second child-sharing time budget', async () => {
  const s = setup({ status: 'loading' });
  let clock = Date.now();
  const originalCreate = s.api.tabs.create;
  s.adapter.now = () => clock;
  s.api.tabs.create = async args => { const result = await originalCreate(args); clock += 11_000; return result; };
  const result = await s.control.execute(s.command());
  assert.equal(result.effect, 'APPLIED'); assert.equal(result.output.sharing.code, 'CREATED_TAB_TIMEOUT');
  assert.deepEqual(s.gets, [7]); noWaiters(s);
});
