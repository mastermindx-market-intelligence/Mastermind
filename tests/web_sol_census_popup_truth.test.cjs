'use strict';
// Actual checkout source; synthetic DOM and Chrome read boundary only.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createHash} = require('node:crypto');
const EXT = path.resolve(__dirname, '../integrations/chairman_surfaces/web_sol_extension');
const controller = fs.readFileSync(path.join(EXT, 'census.js'), 'utf8');
const html = fs.readFileSync(path.join(EXT, 'census.html'), 'utf8');
const core = require(path.join(EXT, 'census_core.js'));
const INSTANCE = 'a'.repeat(64);
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.text = ''; this.className = ''; this.events = {}; this.disabled = false; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = []; this.text = ''; this.append(...nodes); }
  addEventListener(name, callback) { this.events[name] = callback; }
  set innerHTML(_) { throw Error('HTML_WRITE_FORBIDDEN'); }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function mount(next, options = {}) {
  const ids = ['summary', 'status', 'scope', 'timestamp', 'rows', 'refresh'];
  const nodes = Object.fromEntries(ids.map(id => [id, new Element('div')]));
  for (const id of ids) assert.ok(html.includes(`id="${id}"`), `actual HTML missing ${id}`);
  const tabs = options.tabs || Object.freeze({});
  const config = options.configured === false ? undefined : Object.freeze({instanceId: options.instanceId || INSTANCE});
  let calls = 0, schedulingCalls = 0; const lifecycle = {};
  const received = [];
  const context = {document: {getElementById(id) { assert.ok(nodes[id]); return nodes[id]; },
    createElement: tag => new Element(tag)}, chrome: {runtime: {sendMessage(message) {
      assert.equal(JSON.stringify(message), JSON.stringify({kind:'MMX_WEB_SOL_CENSUS_REFRESH'}));
      calls++; received.push([tabs, config?.instanceId]); return next(tabs, config?.instanceId);
    }}},
    addEventListener(name, callback) { lifecycle[name] = callback; },
    setTimeout() { schedulingCalls++; throw Error('CONTROLLER_RETRY_TIMER_FORBIDDEN'); },
    setInterval() { schedulingCalls++; throw Error('CONTROLLER_RETRY_TIMER_FORBIDDEN'); }};
  context.self = {}; context.top = options.iframe ? {} : context.self;
  vm.runInNewContext(controller, context, {timeout: 1000, filename: path.join(EXT, 'census.js')});
  return {nodes, received, pagehide() { lifecycle.pagehide(); }, get calls() { return calls; }, get schedulingCalls() { return schedulingCalls; },
    refresh() { return nodes.refresh.events.click(); }};
}
async function settled(ui) {
  for (let n = 0; n < 100 && ui.nodes.refresh.disabled; n++)
    await new Promise(resolve => setTimeout(resolve, 2));
  assert.equal(ui.nodes.refresh.disabled, false, 'refresh failed to settle');
  return ui;
}
const metrics = ui => ui.nodes.summary.children.map(node => node.children[0].textContent);
const tab = (id, suffix = '11111111-1111-4111-8111-111111111111') => Object.freeze({
  id, windowId: 1, url: `https://chatgpt.com/c/${suffix}`, status: 'complete',
  discarded: true, frozen: false, incognito: false, active: false});
async function snapshot(rows, options = {}) {
  let queries = 0;
  return core.collect({query: async () => { queries++;
    if (options.fail || (options.finalFail && queries === 2)) throw Error('PRIVATE_ERROR');
    return rows; }, get() { throw Error('UNEXPECTED_LOOKUP'); },
    sendMessage() { throw Error('UNEXPECTED_PROBE'); }}, options.unconfigured ? null : INSTANCE);
}

// Preserve all fifteen original support scenarios, now loading actual checkout paths.
test('healthy discarded duplicate rows retain measured counts and unknown model', async () => {
  const ui = await settled(mount(() => snapshot([tab(1), tab(2)])));
  assert.deepEqual(metrics(ui), ['2', '0', '2', '1']);
  assert.match(ui.nodes.scope.textContent, /1 distinct observed conversation locators/);
  assert.equal(ui.nodes.rows.children.length, 2);
  assert.match(ui.nodes.rows.textContent, /Served model: unknown/);
  assert.match(ui.nodes.timestamp.textContent, /^Captured /);
});
test('successful empty inventory remains distinguishable as measured zero', async () => {
  const ui = await settled(mount(() => snapshot([])));
  assert.deepEqual(metrics(ui), ['0', '0', '0', '0']);
  assert.match(ui.nodes.scope.textContent, /0 sampled/);
  assert.match(ui.nodes.rows.textContent, /No normal ChatGPT tabs were sampled/);
  assert.doesNotMatch(ui.nodes.status.className, /error|warning/);
});
for (const [label, input, options] of [
  ['unconfigured', [], {unconfigured: true}], ['query failure', [], {fail: true}],
  ['invalid inventory', {}, {}], ['inventory overflow', Array(4097).fill(tab(1)), {}],
]) test(`${label} never renders unmeasured counts as zero`, async () => {
  const ui = await settled(mount(() => snapshot(input, options)));
  assert.deepEqual(metrics(ui), ['—', '—', '—', '—']);
  assert.doesNotMatch(ui.nodes.scope.textContent, /0 sampled|0 distinct/);
  assert.match(ui.nodes.rows.textContent, /not evidence that no sessions exist/);
  assert.match(ui.nodes.timestamp.textContent, /^Attempted /);
});
test('refresh clears the previous scope while a new result is pending', async () => {
  const prior = await snapshot([tab(1), tab(2)]); let resolve; let call = 0;
  const ui = await settled(mount(() => ++call === 1 ? prior : new Promise(done => { resolve = done; })));
  const refresh = ui.refresh();
  try {
    assert.equal(ui.nodes.scope.textContent, '');
    assert.equal(ui.nodes.rows.children.length, 0);
    assert.equal(ui.nodes.summary.children.length, 0);
    assert.equal(ui.nodes.timestamp.textContent, '');
    assert.equal(ui.nodes.refresh.disabled, true);
  } finally { resolve(prior); await refresh; }
});
test('failed refresh cannot retain a prior successful scope', async () => {
  const prior = await snapshot([tab(1)]); let call = 0;
  const ui = await settled(mount(() => ++call === 1 ? prior : Promise.reject(Error('PRIVATE_FAILURE'))));
  await ui.refresh();
  assert.equal(ui.nodes.scope.textContent, '');
  assert.equal(ui.nodes.summary.children.length, 0);
  assert.equal(ui.nodes.rows.children.length, 0);
  assert.equal(ui.nodes.timestamp.textContent, '');
  assert.match(ui.nodes.status.textContent, /Snapshot unavailable/);
  assert.doesNotMatch(ui.nodes.status.textContent, /PRIVATE_FAILURE/);
  assert.equal(ui.nodes.refresh.disabled, false);
  let release;
  const closing=mount(()=>new Promise(r=>{release=r;}));closing.pagehide();release(prior);
  await tick();await tick();assert.equal(closing.nodes.rows.children.length,0);
  assert.equal(closing.nodes.summary.children.length,0);assert.equal(closing.nodes.scope.textContent,'');
});
test('partial render failure clears all partially rendered snapshot data', async () => {
  const valid = await snapshot([tab(1)]);
  const ui = await settled(mount(() => ({...valid, rows: null})));
  assert.equal(ui.nodes.summary.children.length, 0);
  assert.equal(ui.nodes.scope.textContent, '');
  assert.equal(ui.nodes.timestamp.textContent, '');
  assert.equal(ui.nodes.rows.children.length, 0);
  assert.match(ui.nodes.status.textContent, /Snapshot unavailable/);
});
test('partial inventory retains observed rows and explicit coverage warning', async () => {
  const ui = await settled(mount(() => snapshot([tab(1), tab(2)], {finalFail: true})));
  assert.deepEqual(metrics(ui), ['2', '0', '2', '1']);
  assert.match(ui.nodes.status.className, /warning/);
  assert.match(ui.nodes.status.textContent, /completeness is unknown/);
  assert.equal(ui.nodes.rows.children.length, 2);
});
test('overflow is unknown but still reports its explicit omission count', async () => {
  const ui = await settled(mount(() => snapshot(Array(4097).fill(tab(1)))));
  assert.match(ui.nodes.scope.textContent, /4097 returned entries omitted/);
  assert.match(ui.nodes.status.className, /warning/);
});
test('a synchronous collection error remains payload-free and re-enables refresh', async () => {
  const ui = await settled(mount(() => { throw Error('PRIVATE_THROW'); }));
  assert.match(ui.nodes.status.textContent, /Snapshot unavailable/);
  assert.doesNotMatch(ui.nodes.status.textContent, /PRIVATE_THROW/);
});
test('busy refresh does not dispatch additional collection work', async () => {
  const prior = await snapshot([]); let resolve;
  const ui = mount(() => new Promise(done => { resolve = done; }));
  await ui.refresh(); await ui.refresh();
  assert.equal(ui.calls, 1);
  const frame=mount(()=>{throw Error('IFRAME_ACQUISITION');},{iframe:true});
  await tick();assert.equal(frame.calls,0);assert.equal(frame.nodes.rows.children.length,0);
  resolve(prior); await settled(ui);
  assert.deepEqual(metrics(ui), ['0', '0', '0', '0']);
});
test('manual refresh recovers after failure without automatic retries', async () => {
  const prior = await snapshot([tab(1)]); let call = 0;
  const ui = await settled(mount(() => ++call === 1 ? Promise.reject(Error('FAIL')) : prior));
  assert.equal(ui.calls, 1); await tick(); assert.equal(ui.calls, 1);
  await ui.refresh();
  assert.equal(ui.calls, 2);
  assert.deepEqual(metrics(ui), ['1', '0', '1', '0']);
  assert.equal(ui.nodes.rows.children.length, 1);
  assert.doesNotMatch(ui.nodes.status.className, /error|warning/);
});
test('successful snapshot data is not mutated by rendering', async () => {
  const prior = await snapshot([tab(1)]); const before = JSON.stringify(prior);
  Object.freeze(prior); for (const row of prior.rows) Object.freeze(row);
  Object.freeze(prior.rows);
  await settled(mount(() => prior));
  assert.equal(JSON.stringify(prior), before);
});

// Additional assertions required by the current source coordinator.
test('controller requests the same worker broker on initial and manual reads', async () => {
  const boundary = Object.freeze({query: async () => [], get() { throw Error('UNEXPECTED_LOOKUP'); },
    sendMessage() { throw Error('UNEXPECTED_PROBE'); }});
  const exactInstance = 'b'.repeat(64);
  const ui = await settled(mount((api, instanceId) => core.collect(api, instanceId),
    {tabs: boundary, instanceId: exactInstance}));
  await ui.refresh();
  assert.equal(ui.received.length, 2);
  for (const [api, instanceId] of ui.received) { assert.equal(api, boundary); assert.equal(instanceId, exactInstance); }
  assert.deepEqual(metrics(ui), ['0', '0', '0', '0']);
});
test('selected model and effort remain explicitly unverified in each actual rendered row', async () => {
  const ui = await settled(mount(() => snapshot([tab(1), tab(2)])));
  for (const row of ui.nodes.rows.children) {
    assert.match(row.textContent, /Unverified \/ Unverified/);
    assert.match(row.textContent, /Served model: unknown/);
  }
});
test('positive generation and disagreeing duplicate cues reach the real controller from the real collector', async () => {
  const rows = [1, 2].map(id => ({...tab(id), discarded: false}));
  const boundary = {
    query: async () => structuredClone(rows),
    get: async id => structuredClone(rows.find(row => row.id === id)),
    sendMessage: async (id, request, target) => {
      assert.deepEqual(target, {frameId: 0});
      const fingerprint = createHash('sha256').update(rows[0].url).digest('hex');
      assert.equal(request.expected_conversation_fingerprint, fingerprint);
      return {kind: 'MMX_WEB_SOL_PROBE', conversation_fingerprint: fingerprint,
        observation: {schema: 'mastermind.web_sol_surface_probe.v1', target_present: true,
          exact_conversation_loaded: true, page_responsive: true, document_ready_state: 'complete',
          visibility: 'visible', composer_available: true, generation_state: id === 1 ? 'active' : 'idle',
          auth_required: false, provider_error_present: false}};
    }};
  const ui = await settled(mount((api, instanceId) => core.collect(api, instanceId), {tabs: boundary}));
  assert.deepEqual(metrics(ui), ['2', '1', '0', '1']);
  assert.match(ui.nodes.rows.children[0].textContent, /Cue present/);
  assert.match(ui.nodes.rows.children[1].textContent, /No cue observed/);
  for (const row of ui.nodes.rows.children) assert.match(row.textContent, /Cue observations differ/);
});
test('controller schedules no retry timer on failure, settlement, or manual recovery', async () => {
  let fail = true;
  const ui = await settled(mount(() => fail ? Promise.reject(Error('SYNTHETIC_FAILURE')) : snapshot([])));
  await tick(); await tick();
  assert.equal(ui.calls, 1); assert.equal(ui.schedulingCalls, 0);
  fail = false; await ui.refresh(); await tick();
  assert.equal(ui.calls, 2); assert.equal(ui.schedulingCalls, 0);
  assert.deepEqual(metrics(ui), ['0', '0', '0', '0']);
});
test('missing instance configuration is forwarded as missing and never touches browser APIs', async () => {
  let browserCalls = 0;
  const boundary = Object.freeze({query() { browserCalls++; return []; }, get() { browserCalls++; },
    sendMessage() { browserCalls++; }});
  const ui = await settled(mount((api, instanceId) => core.collect(api, instanceId), {tabs: boundary, configured: false}));
  assert.equal(ui.received[0][0], boundary); assert.equal(ui.received[0][1], undefined);
  assert.equal(browserCalls, 0); assert.deepEqual(metrics(ui), ['—', '—', '—', '—']);
});
