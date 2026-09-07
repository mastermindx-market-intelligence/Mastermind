'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const file = path.resolve(__dirname, '../integrations/chairman_surfaces/web_sol_extension/census_core.js');
const core = fs.existsSync(file) ? require(file) : null;
const INSTANCE = 'a'.repeat(64);
const hash = (s) => crypto.createHash('sha256').update(s).digest('hex');
function tab(id, extra = {}) {
  return {id, windowId: 1, url: `https://chatgpt.com/c/fixture-${id}`, status: 'complete',
    discarded: false, frozen: false, incognito: false, active: false, ...extra};
}
function probe(t, changes = {}) {
  const u = new URL(t.url); const p = u.pathname.replace(/\/$/, '');
  return {kind: 'MMX_WEB_SOL_PROBE', conversation_fingerprint: hash(`https://chatgpt.com${p}`),
    observation: {schema: 'mastermind.web_sol_surface_probe.v1', target_present: true,
      exact_conversation_loaded: true, page_responsive: true, document_ready_state: 'complete',
      visibility: 'hidden', composer_available: true, generation_state: 'idle',
      auth_required: false, provider_error_present: false, ...changes}};
}
function api(rows, options = {}) {
  let q = 0; const calls = [];
  const boundary = {
    async query(args) { calls.push(['query', args]); return options.query ? options.query(++q) : structuredClone(rows); },
    async get(id) { calls.push(['get', id]); if (options.get) return options.get(id); const t = rows.find(x => x.id === id);
      if (!t) throw Error('PRIVATE EXCEPTION MUST NOT LEAK'); return structuredClone(t); },
    async sendMessage(id, request, target) { calls.push(['probe', id, request, target]);
      return options.send ? options.send(id, request, target) : probe(rows.find(x => x.id === id)); }
  };
  for (const key of ['update', 'reload', 'create', 'remove', 'discard', 'executeScript']) {
    boundary[key] = () => { throw Error(`FORBIDDEN EFFECT: ${key}`); };
  }
  return {boundary, calls};
}
async function collect(rows, options = {}) {
  assert.ok(core, 'census_core.js must implement the read-only census');
  const fake = api(rows, options); const result = await core.collect(fake.boundary, INSTANCE);
  return {result, calls: fake.calls};
}

test('the census source exists and exports a real collector', () => {
  assert.ok(core, 'census_core.js must implement the read-only census');
  assert.equal(typeof core.collect, 'function');
});
test('zero tabs is a complete scoped inventory, not an all-account claim', async () => {
  const {result} = await collect([]);
  assert.equal(result.scope, 'CURRENT_PROFILE_NORMAL_CHATGPT_TABS');
  assert.equal(result.inventory_coverage, 'COMPLETE_IN_SCOPE');
  assert.equal(result.initial_tab_count, 0); assert.equal(result.final_tab_count, 0);
  assert.deepEqual(result.rows, []); assert.equal(result.consistency, 'STABLE_AT_BOUNDARIES');
});
test('generation cue and next-turn model uncertainty remain separate', async () => {
  const t = tab(1, {active: true});
  const {result, calls} = await collect([t], {send: () => probe(t, {generation_state: 'active'})});
  assert.equal(result.rows[0].generation_cue, 'PRESENT');
  assert.equal(result.rows[0].selected_in_window, true);
  assert.equal(result.rows[0].selected_model, null); assert.equal(result.rows[0].selected_effort, null);
  assert.equal(result.rows[0].served_model, null); assert.equal(result.rows[0].model_evidence, 'UNVERIFIED');
  const call = calls.find(x => x[0] === 'probe');
  assert.deepEqual(call[3], {frameId: 0});
  assert.equal(call[2].kind, 'MMX_WEB_SOL_REPROBE');
  assert.equal(call[2].expected_conversation_fingerprint, hash(t.url));
});
test('composer without stop is no cue observed, not proven idle or free capacity', async () => {
  const {result} = await collect([tab(1)]);
  assert.equal(result.rows[0].generation_cue, 'NOT_OBSERVED');
  assert.equal(result.rows[0].status, 'OBSERVED');
  assert.ok(!JSON.stringify(result).includes('idle'));
  assert.ok(!('available_capacity' in result));
});
test('two tabs for one canonical conversation remain two rows and one conversation', async () => {
  const one = tab(1), two = tab(2, {url: 'https://chat.openai.com/c/fixture-1/'});
  const {result} = await collect([one, two]);
  assert.equal(result.rows.length, 2); assert.equal(result.unique_conversation_count, 1);
  assert.equal(result.duplicate_tab_count, 1);
  assert.deepEqual(result.rows.map(r => r.duplicate_count), [2, 2]);
});
for (const field of ['discarded', 'frozen']) test(`${field} tab remains in census and is not probed or labelled idle`, async () => {
  const {result, calls} = await collect([tab(1, {[field]: true})]);
  assert.equal(result.rows.length, 1); assert.equal(result.rows[0].status, field.toUpperCase());
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
  assert.equal(calls.filter(x => x[0] === 'probe').length, 0);
});
test('a new-chat or unsupported conversation route remains an unbound row', async () => {
  const {result, calls} = await collect([tab(1, {url: 'https://chatgpt.com/'})]);
  assert.equal(result.rows[0].status, 'NOT_A_CONVERSATION');
  assert.equal(result.rows[0].conversation_fingerprint, null);
  assert.equal(result.initial_tab_count, 1); assert.equal(calls.filter(x => x[0] === 'probe').length, 0);
});
test('incognito tabs are excluded explicitly, never silently claimed as coverage', async () => {
  const {result, calls} = await collect([tab(1), tab(2, {incognito: true})]);
  assert.equal(result.rows.length, 1); assert.equal(result.excluded_private_count, 1);
  assert.equal(result.initial_tab_count, 1);
  assert.equal(calls.filter(x => x[0] === 'probe').length, 1);
});
test('missing content script preserves the tab with an unknown observation', async () => {
  const {result} = await collect([tab(1)], {send: () => Promise.reject(Error('secret=PRIVATE_SENTINEL'))});
  assert.equal(result.rows[0].status, 'PROBE_UNAVAILABLE');
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
  assert.equal(result.inventory_coverage, 'COMPLETE_IN_SCOPE');
  assert.equal(result.probe_coverage, 'NONE');
  assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'));
});
test('a mismatched conversation probe cannot provide generation or model evidence', async () => {
  const {result} = await collect([tab(1)], {send: () => probe(tab(2), {generation_state: 'active'})});
  assert.equal(result.rows[0].status, 'TARGET_CHANGED');
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
});
test('unknown fields in a probe are refused rather than copied to the view', async () => {
  const t = tab(1); const p = probe(t); p.observation.raw_dom = 'PRIVATE_SENTINEL';
  const {result} = await collect([t], {send: () => p});
  assert.equal(result.rows[0].status, 'INVALID_PROBE');
  assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'));
});
test('malformed probe booleans and readiness cannot be laundered into an observation', async () => {
  const {result} = await collect([tab(1)], {send: () => probe(tab(1), {page_responsive: 'true'})});
  assert.equal(result.rows[0].status, 'INVALID_PROBE');
});
test('pending navigation refuses the probe without selecting or reloading the tab', async () => {
  const {result, calls} = await collect([tab(1, {pendingUrl: 'https://chatgpt.com/c/other'})]);
  assert.equal(result.rows[0].status, 'NAVIGATING');
  assert.equal(calls.filter(x => x[0] === 'probe').length, 0);
});
test('loading tabs remain explicit unknowns', async () => {
  const {result} = await collect([tab(1, {status: 'loading'})]);
  assert.equal(result.rows[0].status, 'LOADING');
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
});
test('navigation after probe invalidates its cue before publication', async () => {
  const t = tab(1); let calls = 0;
  const {result} = await collect([t], {get: () => ++calls === 1 ? t : tab(1, {url: 'https://chatgpt.com/c/replaced'}),
    send: () => probe(t, {generation_state: 'active'})});
  assert.equal(result.rows[0].status, 'TARGET_CHANGED');
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
});
test('tab disappearance is preserved as lookup failure without exposing exception text', async () => {
  const {result} = await collect([tab(1)], {get: () => Promise.reject(Error('PRIVATE_SENTINEL'))});
  assert.equal(result.rows[0].status, 'LOOKUP_UNAVAILABLE');
  assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'));
});
test('changed final inventory cannot be labelled complete', async () => {
  const {result} = await collect([tab(1)], {query: n => n === 1 ? [tab(1)] : [tab(1), tab(2)]});
  assert.equal(result.inventory_coverage, 'PARTIAL');
  assert.equal(result.consistency, 'CHANGED');
  assert.equal(result.initial_tab_count, 1); assert.equal(result.final_tab_count, 2);
  assert.equal(result.unobserved_added_count, 1);
});
test('final inventory failure preserves observations but loses completeness', async () => {
  const {result} = await collect([tab(1)], {query: n => n === 1 ? [tab(1)] : Promise.reject(Error('PRIVATE_SENTINEL'))});
  assert.equal(result.inventory_coverage, 'PARTIAL');
  assert.equal(result.final_tab_count, null); assert.equal(result.consistency, 'UNKNOWN');
  assert.equal(result.rows.length, 1);
});
test('initial query failure is unavailable, never an empty complete inventory', async () => {
  const {result} = await collect([], {query: () => Promise.reject(Error('PRIVATE_SENTINEL'))});
  assert.equal(result.inventory_coverage, 'UNAVAILABLE');
  assert.equal(result.initial_tab_count, null); assert.equal(result.reason, 'QUERY_UNAVAILABLE');
});
test('invalid query shape fails closed with a fixed reason', async () => {
  const {result} = await collect([], {query: () => ({secret: 'PRIVATE_SENTINEL'})});
  assert.equal(result.inventory_coverage, 'UNAVAILABLE'); assert.equal(result.reason, 'INVALID_INVENTORY');
  assert.ok(!JSON.stringify(result).includes('PRIVATE_SENTINEL'));
});
test('overflow reports the real returned count and a partial bounded view', async () => {
  assert.ok(core); const rows = Array.from({length: core.MAX_TABS + 1}, (_, i) => tab(i + 1));
  const {result} = await collect(rows);
  assert.equal(result.inventory_coverage, 'PARTIAL'); assert.equal(result.reason, 'TAB_LIMIT');
  assert.equal(result.rows.length, core.MAX_TABS);
  assert.equal(result.omitted_tab_count, 1); assert.equal(result.initial_tab_count, core.MAX_TABS + 1);
});
test('invalid tab identity is represented without guessing a target', async () => {
  const {result, calls} = await collect([tab(1, {id: -1})]);
  assert.equal(result.rows[0].status, 'INVALID_TAB');
  assert.equal(result.inventory_coverage, 'PARTIAL');
  assert.equal(calls.filter(x => x[0] === 'probe').length, 0);
});
test('raw title, account-shaped query and private URL never enter the normalized snapshot', async () => {
  const t = tab(1, {title: 'PRIVATE_SENTINEL', url: 'https://chatgpt.com/c/fixture-1?account=PRIVATE_SENTINEL#private'});
  const {result} = await collect([t]);
  const serialized = JSON.stringify(result);
  assert.ok(!serialized.includes('PRIVATE_SENTINEL')); assert.ok(!serialized.includes('https://'));
  assert.ok(!serialized.includes('windowId')); assert.ok(!serialized.includes('tabId'));
});
test('unconfigured adapter refuses before tab access', async () => {
  assert.ok(core); const fake = api([tab(1)]);
  const result = await core.collect(fake.boundary, 'not-an-instance');
  assert.equal(result.reason, 'ADAPTER_UNCONFIGURED'); assert.equal(fake.calls.length, 0);
});
test('probe timeout is bounded and does not cause a second request', async () => {
  const {result, calls} = await collect([tab(1)], {send: () => new Promise(() => {})});
  assert.equal(result.rows[0].status, 'PROBE_TIMEOUT');
  assert.equal(calls.filter(x => x[0] === 'probe').length, 1);
});
test('concurrent fan-out stays bounded and all rows survive', async () => {
  assert.ok(core); let running = 0, high = 0;
  const rows = Array.from({length: 40}, (_, i) => tab(i + 1));
  const {result} = await collect(rows, {send: async id => { running++; high = Math.max(high, running);
    await new Promise(r => setTimeout(r, 2)); running--; return probe(tab(id)); }});
  assert.equal(result.rows.length, 40); assert.ok(high <= core.CONCURRENCY); assert.ok(high > 0);
});
test('a timed-out worker retires its slot instead of accumulating outstanding Chrome messages', async () => {
  assert.ok(core);
  const rows = Array.from({length: core.CONCURRENCY * 2}, (_, i) => tab(i + 1));
  const {result, calls} = await collect(rows, {send: () => new Promise(() => {})});
  assert.equal(calls.filter(x => x[0] === 'probe').length, core.CONCURRENCY);
  assert.equal(result.rows.filter(r => r.status === 'PROBE_SLOTS_EXHAUSTED').length, core.CONCURRENCY);
});
test('late replies after the deadline cannot mutate an already returned snapshot', async () => {
  let deliver; const t = tab(1);
  const {result} = await collect([t], {send: () => new Promise(resolve => { deliver = resolve; })});
  const before = JSON.stringify(result); deliver(probe(t, {generation_state: 'active'}));
  await new Promise(r => setTimeout(r, 5));
  assert.equal(JSON.stringify(result), before);
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
});
test('a replaced tab in the final sweep loses stale conversation and cue evidence', async () => {
  const t = tab(1);
  const {result} = await collect([t], {query: n => n === 1 ? [t] : [tab(1, {url: 'https://chatgpt.com/c/new'})],
    send: () => probe(t, {generation_state: 'active'})});
  assert.equal(result.rows[0].conversation_fingerprint, null);
  assert.equal(result.rows[0].generation_cue, 'UNKNOWN');
  assert.equal(result.inventory_coverage, 'PARTIAL');
});
test('top-level provider-shaped fields cannot enter a probe receipt', async () => {
  const p = probe(tab(1)); p.model = 'PRIVATE_SENTINEL';
  const {result} = await collect([tab(1)], {send: () => p});
  assert.equal(result.rows[0].status, 'INVALID_PROBE');
  assert.equal(result.rows[0].selected_model, null);
});
test('duplicate tabs with contradictory cues are flagged without electing a winner', async () => {
  const a = tab(1), b = tab(2, {url: a.url});
  const {result} = await collect([a, b], {send: id => probe(id === 1 ? a : b,
    {generation_state: id === 1 ? 'active' : 'idle'})});
  assert.deepEqual(result.rows.map(r => r.duplicate_cue_disagreement), [true, true]);
  assert.deepEqual(result.rows.map(r => r.generation_cue), ['PRESENT', 'NOT_OBSERVED']);
  assert.equal(result.unique_conversation_count, 1);
});
test('manual refresh cannot add probes while prior messages on that same API remain unresolved', async () => {
  assert.ok(core);
  const rows = Array.from({length: core.CONCURRENCY}, (_, i) => tab(i + 1));
  const fake = api(rows, {send: () => new Promise(() => {})});
  await core.collect(fake.boundary, INSTANCE);
  const again = await core.collect(fake.boundary, INSTANCE);
  assert.equal(fake.calls.filter(x => x[0] === 'probe').length, core.CONCURRENCY);
  assert.ok(again.rows.every(r => r.status === 'PROBE_SLOTS_EXHAUSTED'));
});
const vm = require('node:vm');
class TestElement {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; this.events = {}; this.disabled = false; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, callback) { this.events[name] = callback; }
}
const flattened = node => node.textContent + node.children.map(flattened).join(' ');
async function popupFixture(reader, tabs) {
  const elements = Object.fromEntries(['refresh', 'rows', 'summary', 'scope', 'status', 'timestamp'].map(id => [id, new TestElement(id)]));
  const context = {document: {getElementById: id => elements[id], createElement: tag => new TestElement(tag)},
    chrome: {tabs}, MMX_WEB_SOL_INSTANCE: {instanceId: INSTANCE}, MMXWebSolCensus: reader};
  vm.runInNewContext(fs.readFileSync(path.join(path.dirname(file), 'census.js'), 'utf8'), context);
  const done = async () => {
    for (let i = 0; i < 100 && elements.refresh.disabled; i++) await new Promise(r => setTimeout(r, 2));
    assert.equal(elements.refresh.disabled, false, 'popup refresh must settle');
  };
  await done(); return {elements, done};
}
test('the actual popup controller consumes real census output and refreshes its rows', async () => {
  assert.ok(core);
  const t = tab(1, {title: 'PRIVATE_SENTINEL'}), duplicate = tab(2, {url: t.url}); let active = true;
  const fake = api([t, duplicate], {send: id => probe(id === 1 ? t : duplicate,
    {generation_state: id === 1 && active ? 'active' : 'idle'})});
  const {elements, done} = await popupFixture(core, fake.boundary);
  assert.equal(elements.rows.children.length, 2);
  assert.ok(flattened(elements.rows).includes('Cue observations differ'));
  assert.ok(flattened(elements.rows).includes('Served model: unknown'));
  assert.ok(!flattened(elements.rows).includes('PRIVATE_SENTINEL'));
  active = false; elements.refresh.events.click(); await done();
  assert.ok(!flattened(elements.rows).includes('Cue observations differ'));
  assert.ok(flattened(elements.rows).includes('No cue observed'));
});
test('popup failure publishes a fixed safe message and re-enables refresh', async () => {
  const {elements} = await popupFixture({collect: () => Promise.reject(Error('PRIVATE_SENTINEL'))}, {});
  assert.equal(elements.status.textContent, 'Snapshot unavailable. No browser-control action was attempted.');
  assert.ok(!flattened(elements.status).includes('PRIVATE_SENTINEL'));
});

// Read-budget regression coverage. Existing tests above remain unchanged.
{
'use strict';
// Exercise the real collector in an isolated JS realm. Only browser APIs and
// time are controlled: the module's source, limits and control flow are intact.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const SOURCE = process.env.CORE_PATH || path.resolve(__dirname,
  '../integrations/chairman_surfaces/web_sol_extension/census_core.js');
const INSTANCE = 'a'.repeat(64);
const HANG = Symbol('controlled-pending-browser-read');
const PRIVATE = 'SYNTHETIC_PRIVATE_ERROR_MUST_NOT_LEAK';
const plain = value => JSON.parse(JSON.stringify(value));
const turn = () => new Promise(resolve => setImmediate(resolve));
function row(id) {
  return {id, windowId: 1, url: `https://chatgpt.com/c/budget-${id}`,
    status: 'complete', discarded: false, frozen: false, active: false, incognito: false};
}
function observation(t) {
  return {kind: 'MMX_WEB_SOL_PROBE',
    conversation_fingerprint: crypto.createHash('sha256').update(t.url).digest('hex'),
    observation: {schema: 'mastermind.web_sol_surface_probe.v1',
      target_present: true, exact_conversation_loaded: true, page_responsive: true,
      document_ready_state: 'complete', visibility: 'hidden', composer_available: true,
      generation_state: 'active', auth_required: false, provider_error_present: false}};
}
function load() {
  let now = 0, sequence = 0;
  const timers = new Map();
  const NativeDate = Date;
  const epoch = NativeDate.parse('2026-09-06T21:00:00.000Z');
  class ControlledDate extends NativeDate {
    constructor(...args) { super(...(args.length ? args : [epoch + now])); }
    static now() { return epoch + now; }
  }
  const context = vm.createContext({module: {exports: {}}, URL, TextEncoder, Promise,
    Date: ControlledDate, performance: {now: () => now},
    crypto: {subtle: {digest: async (_name, bytes) => {
      const b = crypto.createHash('sha256').update(bytes).digest();
      return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
    }}},
    setTimeout: (fn, delay) => { const id = ++sequence; timers.set(id, {fn, due: now + delay}); return id; },
    clearTimeout: id => timers.delete(id)});
  vm.runInContext(fs.readFileSync(SOURCE, 'utf8'), context, {filename: SOURCE});
  const core = context.module.exports;
  async function complete(promise) {
    let finished = false, result, failure;
    promise.then(value => { finished = true; result = value; }, error => { finished = true; failure = error; });
    for (let step = 0; step < 10000; step++) {
      // Drain the entire promise/microtask turn before advancing fake time.
      await turn();
      if (finished) { if (failure) throw failure; return result; }
      assert.ok(timers.size, 'collector must have a finite deadline or have settled');
      now = Math.min(...[...timers.values()].map(t => t.due));
      for (const [id, timer] of [...timers]) if (timer.due <= now) {
        timers.delete(id); timer.fn();
      }
    }
    assert.fail('controlled-clock execution did not terminate');
  }
  return {core, complete, timers};
}
function api(count = 8) {
  const rows = Array.from({length: count}, (_, i) => row(i + 1));
  const state = {query: null, get: null, send: null};
  const stats = {calls: {query: 0, get: 0, send: 0}, active: 0, high: 0,
    pending: {query: 0, get: 0, send: 0}, highByKind: {query: 0, get: 0, send: 0}, mutations: 0};
  const deferred = [];
  const byId = new Map();
  function invoke(kind, choose, expected) {
    const n = ++stats.calls[kind];
    stats.active++; stats.pending[kind]++;
    stats.high = Math.max(stats.high, stats.active);
    stats.highByKind[kind] = Math.max(stats.highByKind[kind], stats.pending[kind]);
    const release = () => { stats.active--; stats.pending[kind]--; };
    let value;
    try { value = choose ? choose(n) : expected; } catch (error) { release(); throw error; }
    let result;
    if (value === HANG) {
      result = new Promise((resolve, reject) => deferred.push({kind, resolve, reject, expected, settled: false}));
    } else if (value instanceof Error) result = Promise.reject(value);
    else result = Promise.resolve(structuredClone(value));
    return result.finally(release);
  }
  const tabs = {
    query(args) {
      assert.deepEqual(plain(args), {url: ['https://chatgpt.com/*', 'https://chat.openai.com/*']});
      return invoke('query', state.query, rows);
    },
    get(id) {
      const n = (byId.get(id) || 0) + 1; byId.set(id, n);
      const t = rows.find(t => t.id === id);
      return invoke('get', state.get ? () => state.get(id, n) : null, t);
    },
    sendMessage(id, request, target) {
      assert.deepEqual(plain(target), {frameId: 0});
      assert.equal(request.kind, 'MMX_WEB_SOL_REPROBE');
      const p = observation(rows.find(t => t.id === id));
      assert.equal(request.expected_conversation_fingerprint, p.conversation_fingerprint);
      return invoke('send', state.send ? () => state.send(id) : null, p);
    },
  };
  for (const name of ['update', 'reload', 'create', 'remove', 'discard', 'executeScript']) {
    tabs[name] = () => { stats.mutations++; throw Error('FORBIDDEN_BROWSER_EFFECT'); };
  }
  function settle(kind, rejection = false) {
    for (const item of deferred) if (!item.settled && (!kind || item.kind === kind)) {
      item.settled = true;
      rejection ? item.reject(Error(PRIVATE)) : item.resolve(structuredClone(item.expected));
    }
  }
  return {tabs, stats, state, rows, settle};
}
async function sweep(h, fixture) { return h.complete(h.core.collect(fixture.tabs, INSTANCE)); }
function noLeak(snapshot) {
  const text = JSON.stringify(snapshot);
  assert.ok(!text.includes(PRIVATE)); assert.ok(!text.includes('https://'));
  assert.ok(!text.includes('windowId')); assert.ok(!text.includes('tabId'));
  for (const r of snapshot.rows) {
    assert.equal(r.selected_model, null); assert.equal(r.selected_effort, null);
    assert.equal(r.served_model, null); assert.equal(r.model_evidence, 'UNVERIFIED');
  }
}

test('three refreshes cannot triple pending pre-probe tab lookups', async () => {
  const h = load(), f = api(); f.state.get = () => HANG;
  for (let i = 0; i < 3; i++) { const s = await sweep(h, f); noLeak(s); }
  assert.ok(f.stats.high <= h.core.CONCURRENCY, `pending high=${f.stats.high}, bound=${h.core.CONCURRENCY}`);
  assert.equal(f.stats.calls.get, h.core.CONCURRENCY);
  assert.equal(f.stats.calls.send, 0);
});
test('overlapping refreshes share pending lookup admission', async () => {
  const h = load(), f = api(16); f.state.get = () => HANG;
  const result = await h.complete(Promise.all([h.core.collect(f.tabs, INSTANCE), h.core.collect(f.tabs, INSTANCE)]));
  assert.equal(result.length, 2);
  assert.ok(f.stats.high <= h.core.CONCURRENCY, `pending high=${f.stats.high}`);
});
test('unresolved initial inventory queries cannot grow across forty refreshes', async () => {
  const h = load(), f = api(); f.state.query = () => HANG;
  for (let i = 0; i < 40; i++) {
    const s = await sweep(h, f);
    assert.equal(s.inventory_coverage, 'UNAVAILABLE'); assert.equal(s.initial_tab_count, null);
    noLeak(s);
  }
  assert.ok(f.stats.high <= h.core.CONCURRENCY, `pending inventory high=${f.stats.high}`);
  assert.equal(f.stats.calls.query, h.core.CONCURRENCY);
});
test('unresolved final inventory queries retain slots between refreshes', async () => {
  const h = load(), f = api(0); f.state.query = n => n % 2 ? [] : HANG;
  for (let i = 0; i < 20; i++) await sweep(h, f);
  assert.ok(f.stats.high <= h.core.CONCURRENCY, `pending final-inventory high=${f.stats.high}`);
});
test('pending post-probe lookups are budgeted, not just pre-probe lookups', async () => {
  const h = load(), f = api(); f.state.get = (id, n) => n % 2 ? row(id) : HANG;
  for (let i = 0; i < 3; i++) await sweep(h, f);
  assert.ok(f.stats.high <= h.core.CONCURRENCY, `post-probe high=${f.stats.high}`);
});
test('query, lookup and message operations cannot each claim an independent full pool', async () => {
  const h = load(), f = api(3); f.state.send = () => HANG;
  await sweep(h, f); assert.equal(f.stats.pending.send, 3);
  f.state.query = () => HANG;
  for (let i = 0; i < 10; i++) await sweep(h, f);
  assert.ok(f.stats.high <= h.core.CONCURRENCY, `mixed pending high=${f.stats.high}`);
});
test('saturation returns unknown inventory rather than inventing zero sessions', async () => {
  const h = load(), f = api(); f.state.get = () => HANG;
  const first = await sweep(h, f), again = await sweep(h, f);
  assert.equal(first.rows.length, 8);
  assert.equal(first.inventory_coverage, 'PARTIAL');
  assert.equal(first.reason, 'FINAL_QUERY_UNAVAILABLE');
  assert.equal(again.inventory_coverage, 'UNAVAILABLE'); assert.equal(again.initial_tab_count, null);
  assert.equal(again.final_tab_count, null); assert.equal(again.reason, 'QUERY_UNAVAILABLE');
  assert.equal(again.probe_coverage, 'NONE');
});
test('settling late lookups restores admission without mutating the prior result', async () => {
  const h = load(), f = api(); f.state.get = () => HANG;
  const first = await sweep(h, f), before = JSON.stringify(first);
  f.state.get = null; f.settle('get'); await turn();
  assert.equal(JSON.stringify(first), before); assert.equal(f.stats.active, 0);
  const recovered = await sweep(h, f);
  assert.equal(recovered.inventory_coverage, 'COMPLETE_IN_SCOPE'); assert.equal(recovered.probed_tab_count, 8);
  assert.equal(f.stats.active, 0); assert.equal(f.stats.mutations, 0);
});
test('late query rejections free held slots without error-text leakage', async () => {
  const h = load(), f = api(0); f.state.query = () => HANG;
  const completed = [];
  for (let i = 0; i < 8; i++) completed.push(await sweep(h, f));
  const before = completed.map(JSON.stringify);
  f.state.query = null; f.settle('query', true); await turn();
  assert.equal(f.stats.active, 0);
  const recovered = await sweep(h, f);
  assert.equal(recovered.inventory_coverage, 'COMPLETE_IN_SCOPE'); assert.equal(recovered.initial_tab_count, 0);
  completed.forEach((s, i) => { assert.equal(JSON.stringify(s), before[i]); noLeak(s); });
});
test('synchronous browser errors release slots exactly once', async () => {
  const h = load(), f = api(1); f.state.query = () => { throw Error(PRIVATE); };
  for (let i = 0; i < 40; i++) { noLeak(await sweep(h, f)); assert.equal(f.stats.active, 0); }
  f.state.query = null;
  const recovered = await sweep(h, f); assert.equal(recovered.probed_tab_count, 1);
  assert.equal(f.stats.active, 0); assert.equal(f.stats.mutations, 0);
});
test('immediate promise rejection does not permanently consume a slot', async () => {
  const h = load(), f = api(1); f.state.get = () => Error(PRIVATE);
  for (let i = 0; i < 20; i++) { noLeak(await sweep(h, f)); assert.equal(f.stats.active, 0); }
  f.state.get = null;
  assert.equal((await sweep(h, f)).probed_tab_count, 1);
});
test('late message resolution changes neither completed cues nor subsequent identity', async () => {
  const h = load(), f = api(); f.state.send = () => HANG;
  const first = await sweep(h, f), before = JSON.stringify(first);
  f.state.send = null; f.settle('send'); await turn();
  assert.equal(JSON.stringify(first), before);
  assert.equal((await sweep(h, f)).generation_cue_count, 8); assert.equal(f.stats.active, 0);
});
test('a saturated API object does not consume a different profile API object budget', async () => {
  const h = load(), stalled = api(), healthy = api(2); stalled.state.get = () => HANG;
  await sweep(h, stalled);
  const other = await sweep(h, healthy);
  assert.equal(other.probed_tab_count, 2); assert.equal(other.inventory_coverage, 'COMPLETE_IN_SCOPE');
  assert.equal(stalled.stats.calls.get, 8); assert.equal(healthy.stats.mutations, 0);
});
test('the healthy 128-tab capability survives the stronger read budget', async () => {
  const h = load(), f = api(128); const s = await sweep(h, f);
  assert.equal(s.rows.length, 128); assert.equal(s.probed_tab_count, 128);
  assert.equal(s.inventory_coverage, 'COMPLETE_IN_SCOPE'); assert.equal(s.consistency, 'STABLE_AT_BOUNDARIES');
  assert.equal(f.stats.calls.query, 2); assert.equal(f.stats.calls.get, 256); assert.equal(f.stats.calls.send, 128);
  assert.ok(f.stats.high <= h.core.CONCURRENCY); assert.equal(f.stats.active, 0); assert.equal(f.stats.mutations, 0);
  noLeak(s);
});
test('sleeping rows stay present, unprobed and unknown', async () => {
  const h = load(), f = api(128);
  for (const t of f.rows) t.discarded = true;
  const s = await sweep(h, f);
  assert.equal(s.rows.length, 128); assert.equal(s.unknown_cue_count, 128);
  assert.equal(f.stats.calls.get, 0); assert.equal(f.stats.calls.send, 0); assert.equal(f.stats.mutations, 0);
});
test('unconfigured collectors never enter the browser at all', async () => {
  const h = load(), f = api();
  const s = await h.complete(h.core.collect(f.tabs, null));
  assert.equal(s.reason, 'ADAPTER_UNCONFIGURED'); assert.equal(s.inventory_coverage, 'UNAVAILABLE');
  assert.deepEqual(f.stats.calls, {query: 0, get: 0, send: 0});
});

}
