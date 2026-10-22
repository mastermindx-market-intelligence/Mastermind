import test from 'node:test';
import assert from 'node:assert/strict';
import { startBrowserLink } from '../../integrations/mastermind_browser_link/extension/background-core.mjs';
const event = () => ({ listeners: [], addListener(fn) { this.listeners.push(fn); },
  emit(...args) { for (const fn of this.listeners) fn(...args); } });
const tick = () => new Promise(resolve => setImmediate(resolve));
const ALARM = 'browser-link-reconnect';

function fixture(storage = {}) {
  const messages = [], ports = [], alarmRows = new Map(), created = [], badges = [], detached = [];
  const chrome = {
    runtime: { id: 'a'.repeat(32), getURL: p => `chrome-extension://${'a'.repeat(32)}/${p}`,
      onMessage: event(), onInstalled: event(), onStartup: event(),
      connectNative(name) {
        assert.equal(name, 'com.mastermind.browser_link');
        const port = { onDisconnect: event(), onMessage: event(), closed: 0,
          postMessage(m) { if (port.failSend) throw new Error('host lost'); messages.push(m); },
          // Deliberately no local onDisconnect: exercises Chrome's local-close path.
          disconnect() { port.closed++; } };
        ports.push(port); return port;
      } },
    debugger: { sendCommand() {}, async detach({tabId}) { detached.push(tabId); }, onDetach: event(), onEvent: event() },
    tabs: { async get() { return {id:7,url:'https://example.test/path'}; },
      async query() { return [{id:7,url:'https://example.test/path'}]; }, onRemoved: event(), onUpdated: event() },
    action: { async setBadgeText(value) { badges.push(value); } },
    storage: { local: { async get(key) { return {[key]:storage[key]}; },
      async set(value) { Object.assign(storage,value); } } },
    alarms: { onAlarm: event(), async get(name) { return alarmRows.get(name); },
      async create(name, value) { alarmRows.set(name, value); created.push(name); } },
  };
  return { chrome, messages, ports, created, alarmRows, badges, detached, storage,
    hello() { return messages.filter(row => row.schema === 'mastermind.browser_link.hello.v1').at(-1); },
    ready() { ports.at(-1).onMessage.emit({schema:'mastermind.browser_link.ready.v1',connection_generation:this.hello().connection_generation}); },
    async request(message, path='popup.html') {
      return await new Promise(resolve => {
        assert.equal(chrome.runtime.onMessage.listeners[0](message,
          {id:chrome.runtime.id,url:chrome.runtime.getURL(path)}, resolve), true);
      });
    },
    async drop() { ports.at(-1)?.onDisconnect.emit(); await tick(); },
    async reconnect() { chrome.alarms.onAlarm.emit({name:ALARM}); await tick(); },
  };
}

test('native hello preserves discovery identity across boots but rotates connection generation', async () => {
  const storage = {}, first=fixture(storage), second=fixture(storage);
  startBrowserLink({chrome:first.chrome}); await tick();
  await first.drop();
  startBrowserLink({chrome:second.chrome}); await tick();
  const a=first.hello(), b=second.hello();
  assert.deepEqual(Object.keys(a).sort(), ['schema','protocol_version','extension_id','instance_ref','connection_generation'].sort());
  assert.match(a.instance_ref, /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  assert.equal(a.instance_ref,b.instance_ref);
  assert.notEqual(a.connection_generation,b.connection_generation);
  assert.deepEqual(Object.keys(storage),['browserLinkInstanceRef']);
  await second.drop();
});

test('worker startup repairs a missing reconnect alarm without rescheduling an existing one', async () => {
  const f=fixture(); startBrowserLink({chrome:f.chrome}); await tick();
  assert.deepEqual(f.created,[ALARM]);
  f.chrome.runtime.onStartup.emit(); await tick();
  assert.deepEqual(f.created,[ALARM]);
  assert.equal(f.ports.length,1);
  f.alarmRows.delete(ALARM);
  f.chrome.runtime.onStartup.emit(); await tick();
  assert.deepEqual(f.created,[ALARM,ALARM]);
  await f.drop();
});

test('stalled handshake closes locally and a later alarm reconnects', async context => {
  context.mock.timers.enable({apis:['setTimeout']});
  const f=fixture(); startBrowserLink({chrome:f.chrome}); await tick();
  const generation=f.hello().connection_generation;
  context.mock.timers.tick(5000); await tick();
  assert.equal(f.ports[0].closed,1);
  assert.equal((await f.request({kind:'status'})).connected,false);
  await f.reconnect();
  assert.equal(f.ports.length,2);
  assert.notEqual(f.hello().connection_generation,generation);
  await f.drop();
});

test('ready cancels the handshake timer; reconnect never restores tab consent', async context => {
  context.mock.timers.enable({apis:['setTimeout']});
  const f=fixture(); startBrowserLink({chrome:f.chrome}); await tick(); f.ready();
  context.mock.timers.tick(5001); await tick();
  assert.equal(f.ports[0].closed,0);
  assert.equal((await f.request({kind:'share_current'})).shared,true);
  assert.equal((await f.request({kind:'status'})).shared_tabs.length,1);
  await f.drop();
  assert.deepEqual(f.detached,[7]);
  assert.deepEqual((await f.request({kind:'status'})).shared_tabs,[]);
  await f.reconnect(); f.ready();
  assert.equal((await f.request({kind:'status'})).connected,true);
  assert.deepEqual((await f.request({kind:'status'})).shared_tabs,[]);
  await f.drop();
});

for (const bad of [{schema:'unknown'}, {schema:'mastermind.browser_link.ready.v1',connection_generation:'stale'}]) {
  test('invalid native handshake cleans up without a local disconnect event: '+bad.schema, async () => {
    const f=fixture(); startBrowserLink({chrome:f.chrome}); await tick();
    f.ports[0].onMessage.emit(bad); await tick();
    assert.equal(f.ports[0].closed,1);
    await f.reconnect(); assert.equal(f.ports.length,2);
    await f.drop();
  });
}

test('composed worker leaves Web Sol messages and toolbar badge to Web Sol', async () => {
  const f=fixture(); startBrowserLink({chrome:f.chrome,popupPath:'browser-link/popup.html',showBadge:false}); await tick();
  const listener=f.chrome.runtime.onMessage.listeners[0];
  let responded=false;
  assert.equal(listener({type:'MMX_WEB_SOL_CENSUS_REFRESH'},
    {id:f.chrome.runtime.id,url:f.chrome.runtime.getURL('census.html')},()=>{responded=true;}),false);
  assert.equal(listener({kind:'status'},
    {id:f.chrome.runtime.id,url:'https://chatgpt.com/'},()=>{responded=true;}),false);
  assert.equal(responded,false);
  assert.equal((await f.request({kind:'status'},'browser-link/popup.html')).connected,false);
  assert.deepEqual(f.badges,[]);
  await f.drop();
});

test('inventory send failure clears readiness and leaves reconnect possible', async () => {
  const f=fixture(); startBrowserLink({chrome:f.chrome}); await tick(); f.ready();
  f.ports[0].failSend=true;
  await f.request({kind:'share_current'}); await tick();
  assert.equal(f.ports[0].closed,1);
  assert.equal((await f.request({kind:'status'})).connected,false);
  assert.deepEqual(f.detached,[7]);
  await f.reconnect(); assert.equal(f.ports.length,2);
  await f.drop();
});

for (const replacementReady of [false, true]) {
  test('an old share request cannot grant consent to a replacement connection; ready='+replacementReady, async () => {
    const f=fixture(); startBrowserLink({chrome:f.chrome}); await tick(); f.ready();
    let finishQuery;
    f.chrome.tabs.query=()=>new Promise(resolve=>{finishQuery=resolve;});
    const pending=f.request({kind:'share_current'}); await tick();
    await f.drop(); await f.reconnect();
    if (replacementReady) f.ready();
    finishQuery([{id:7,url:'https://example.test/path'}]);
    assert.deepEqual(await pending,{error:'LINK_NOT_READY'});
    assert.deepEqual((await f.request({kind:'status'})).shared_tabs,[]);
    await f.drop();
  });
}
