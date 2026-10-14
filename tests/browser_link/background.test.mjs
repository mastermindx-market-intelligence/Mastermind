import test from 'node:test';
import assert from 'node:assert/strict';
const event = () => ({ listeners: [], addListener(fn) { this.listeners.push(fn); } });
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

test('native hello includes a persistent unprivileged instance ref and rotates connection generation', async () => {
  const storage = {}, messages = [], ports = [];
  globalThis.chrome = {
    runtime: { id: 'a'.repeat(32), getURL: p => `chrome-extension://${'a'.repeat(32)}/${p}`,
      onMessage: event(), onInstalled: event(), onStartup: event(),
      connectNative(name) { assert.equal(name, 'com.mastermind.browser_link');
        const p = { onDisconnect: event(), onMessage: event(), postMessage(m) { messages.push(m); }, disconnect() {} };
        ports.push(p); return p; } },
    debugger: { sendCommand() {}, onDetach: event(), onEvent: event() },
    tabs: { get() {}, onRemoved: event(), onUpdated: event() },
    action: { async setBadgeText() {} },
    storage: { local: { async get(key) { return {[key]:storage[key]}; }, async set(v) { Object.assign(storage,v); } } },
    alarms: { onAlarm: event(), create() {} },
  };
  for (let i = 0; i < 2; i++) {
    await import(`../../integrations/mastermind_browser_link/extension/background.mjs?boot=${i}`);
    await tick(); await tick();
  }
  assert.equal(ports.length, 2);
  const [a,b] = messages;
  assert.deepEqual(Object.keys(a).sort(), ['schema','protocol_version','extension_id','instance_ref','connection_generation'].sort());
  assert.match(a.instance_ref, /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  assert.equal(a.instance_ref, b.instance_ref);
  assert.notEqual(a.connection_generation, b.connection_generation);
  assert.equal(Object.keys(storage).length, 1); // discovery ref only, never credentials or consent
  delete globalThis.chrome;
});
