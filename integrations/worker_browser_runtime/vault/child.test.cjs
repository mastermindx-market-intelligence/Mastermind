'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { PrivateRedaction, PrivateTransport, genericAllowed, secretRepresentations } = require('./child.cjs');

test('shared native redaction map retains prior values and globally orders overlaps', () => {
  const redaction = new PrivateRedaction();
  const shared = redaction.map;
  redaction.add('fixture-short', 'fixture@example.test');
  redaction.add('fixture-short-followed-by-sensitive-suffix', 'fixture@example.test');
  const special = 'fixture-"quote\' &<xml>\\slash\n雪';
  redaction.add(special, 'fixture@example.test');
  assert.equal(shared, redaction.map);
  const values = Object.values(shared);
  assert.deepEqual(values, [...values].sort((a, b) => b.length - a.length));
  for (const original of ['fixture-short', 'fixture-short-followed-by-sensitive-suffix', special]) {
    for (const representation of secretRepresentations(original)) {
      let donorText = representation;
      // Exact pinned upstream Context.redactSecrets iteration semantics.
      for (const [name, value] of Object.entries(shared)) donorText = donorText.split(value).join(`<secret>${name}</secret>`);
      assert(!donorText.includes(original));
      assert(!redaction.text(donorText).includes('MMX_PRIVATE_'));
    }
  }
  assert.equal(redaction.text('fixture-short-followed-by-sensitive-suffix'), '[REDACTED]');
});

test('normal tools cannot reuse secret aliases or credential representations', () => {
  const redaction = new PrivateRedaction();
  redaction.add('canary-password', 'fixture@example.test');
  const call = (name, args) => ({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name, arguments: args } });
  assert(genericAllowed(call('browser_snapshot', {}), redaction));
  for (const text of ['canary-password', 'fixture@example.test', ...Object.keys(redaction.map)])
    assert(!genericAllowed(call('browser_type', { text }), redaction));
  for (const name of ['browser_take_screenshot', 'browser_console_messages', 'browser_network_requests', 'browser_evaluate'])
    assert(!genericAllowed(call(name, {}), redaction));
  for (const key of ['ControlOrMeta+A', 'ControlOrMeta+C', 'ControlOrMeta+V', 'Shift+F10'])
    assert(!genericAllowed(call('browser_press_key', { key }), redaction));
  assert(genericAllowed(call('browser_press_key', { key: 'Tab' }), redaction));
  assert(!genericAllowed(call('browser_click', { button: 'right' }), redaction));
  assert(!genericAllowed(call('browser_click', { modifiers: ['Alt'] }), redaction));
  assert(!genericAllowed(call('browser_snapshot', { filename: 'artifact.txt' }), redaction));
  assert(!genericAllowed(call('browser_navigate', { url: 'file:///tmp/secret' }), redaction));
  assert(!genericAllowed(call('browser_navigate', { url: 'https://user:password@vault.test' }), redaction));
});

test('redaction strips binary payloads and arbitrary metadata, never evicts old values', () => {
  const redaction = new PrivateRedaction();
  redaction.add('initial-canary', 'fixture@example.test');
  for (let i = 1; i < 8; i++) redaction.add(`different-canary-${i}`, 'fixture@example.test');
  redaction.add('initial-canary', 'fixture@example.test');
  assert.throws(() => redaction.add('ninth-canary', 'fixture@example.test'));
  assert.equal(redaction.text('initial-canary'), '[REDACTED]');
  assert.throws(() => redaction.output({ content: [{ type: 'image', data: 'opaque' }] }));
  assert.deepEqual(Object.keys(redaction.output({ _meta: {}, structuredContent: {}, content: [] })), ['content']);
});

test('fixed private effect receipt survives a password equal to FILLED/APPLIED', () => {
  const redaction = new PrivateRedaction();
  redaction.add('FILLED', 'APPLIED');
  const transport = new PrivateTransport({}, redaction);
  const written = [];
  transport.write = message => written.push(message);
  transport.pendingId = 7;
  transport.sendPrivate(7, { schema: 'mastermind.workbench_browser_credential_result.v1', effect_state: 'APPLIED', code: 'FILLED' });
  assert.equal(written[0].result.effect_state, 'APPLIED');
  assert.equal(written[0].result.code, 'FILLED');
  assert.equal(transport.pendingId, undefined);
});

test('private dispatch failure after possible fill is never NOT_APPLIED', async () => {
  const target = { fill: async () => { throw new Error('fixture possible effect'); } };
  const transport = new PrivateTransport(target, new PrivateRedaction());
  const written = [];
  transport.write = message => written.push(message);
  await transport.receive(Buffer.from(JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'mastermind/credential_fill', params: {} })));
  assert.equal(written[0].result.effect_state, 'EFFECT_UNKNOWN');
  assert.equal(written[0].result.code, 'FILL_UNCERTAIN');
});
