'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createAppControlAdapter, validateOrigin, SCHEMA } = require('./adapter.cjs');
const { options } = require('./child.cjs');

function fixture({ urls = ['https://mcp.mastermind-x.com/os/'], output, throws = false } = {}) {
  const calls = [];
  const pages = urls.map(url => ({ url: () => url, isClosed: () => false, evaluate: async (fn, args) => {
    calls.push({ fn, args });
    if (throws) throw new Error('private transport detail');
    return output ?? { schema: SCHEMA, status: 'DISPATCHED', code: 'UI_EVENT_DISPATCHED' };
  } }));
  const adapter = createAppControlAdapter({ getContext: async () => ({ pages: () => pages }), origin: 'https://mcp.mastermind-x.com' });
  return { adapter, calls, pages };
}
test('catalogue is closed, data-only, and normalized for standard MCP', async () => {
  const { adapter, calls } = fixture();
  assert.deepEqual(adapter.tools().map(tool => tool.name), ['mastermind_os_inspect','mastermind_os_navigate','mastermind_os_act','mastermind_os_check']);
  assert(adapter.tools().every(tool => Object.keys(tool.annotations).join() === 'readOnlyHint'));
  const input = { observation: 'opaque', target: 'control-1', action: 'fill', value: 'literal ${not_code}' };
  await adapter.call('mastermind_os_act', input);
  assert.equal(calls.length, 1);
  assert.equal(typeof calls[0].fn, 'function');
  assert.deepEqual(calls[0].args.input, input);
  assert.equal((await adapter.call('browser_evaluate', { function: 'secret()' })).structuredContent.code, 'TOOL_UNAVAILABLE');
  assert.equal(calls.length, 1);
});
test('origin configuration refuses remote cleartext, paths, credentials, query and fragments', () => {
  for (const value of ['http://example.com', 'https://example.com/', 'https://user@example.com', 'https://example.com?x=1', 'https://example.com#x', 'javascript:x', undefined]) assert.throws(() => validateOrigin(value));
  for (const value of ['https://mcp.mastermind-x.com', 'http://127.0.0.1:5179', 'http://localhost:5179']) assert.equal(validateOrigin(value), value);
});
test('missing, foreign and ambiguous app pages never evaluate', async () => {
  for (const urls of [[], ['https://foreign.example/os/'], ['https://mcp.mastermind-x.com/other'], ['https://mcp.mastermind-x.com/os/','https://mcp.mastermind-x.com/os/other']]) {
    const { adapter, calls } = fixture({ urls });
    assert.equal((await adapter.call('mastermind_os_inspect')).structuredContent.status, 'REFUSED');
    assert.equal(calls.length, 0);
  }
});
test('pre-dispatch cancellation and invalid arguments do not evaluate', async () => {
  const { adapter, calls } = fixture();
  const signal = AbortSignal.abort();
  assert.equal((await adapter.call('mastermind_os_act', {}, { signal })).structuredContent.code, 'CANCELLED_BEFORE_DISPATCH');
  for (const input of [[], null, 'code', { value: 'x'.repeat(40000) }]) assert.equal((await adapter.call('mastermind_os_act', input)).structuredContent.code, 'INVALID_ARGUMENT');
  assert.equal(calls.length, 0);
});
test('lost action responses are unknown and are never automatically retried', async () => {
  const { adapter, calls } = fixture({ throws: true });
  assert.equal((await adapter.call('mastermind_os_act', {})).structuredContent.status, 'EFFECT_UNKNOWN');
  assert.equal(calls.length, 1);
  assert.equal((await adapter.call('mastermind_os_inspect')).structuredContent.code, 'APP_READ_UNAVAILABLE');
  assert.equal(calls.length, 2);
});
test('origin drift after dispatch and oversized results retain uncertainty', async () => {
  const { adapter, pages } = fixture();
  pages[0].evaluate = async () => { pages[0].url = () => 'https://foreign.example/'; return { schema: SCHEMA, status: 'DISPATCHED' }; };
  assert.equal((await adapter.call('mastermind_os_navigate', {})).structuredContent.status, 'EFFECT_UNKNOWN');
  const large = fixture({ output: { schema: SCHEMA, status: 'DISPATCHED', value: 'x'.repeat(100000) } });
  assert.equal((await large.adapter.call('mastermind_os_act', {})).structuredContent.status, 'EFFECT_UNKNOWN');
});
test('child accepts only the owner-projected local launch options', () => {
  const input = ['--app-origin','https://mcp.mastermind-x.com','--browser','chrome','--executable-path','/owned/chrome','--output-dir','/owned/output','--headless','--isolated'];
  assert.equal(options(input)['--isolated'], true);
  for (const extra of [['--cdp-endpoint','ws://localhost:9222'], ['--extension'], ['--app-origin','https://foreign.example'], ['--user-data-dir','/owned/profile']]) assert.throws(() => options([...input,...extra]));
});
