import test from 'node:test';
import assert from 'node:assert/strict';
import { ChromePort } from '../../integrations/mastermind_browser_link/extension/chrome-port.mjs';

function setup() {
  const state = { url: 'https://example.test/path?token=not-returned', name: 'Increment', type: 'text', tag: 'BUTTON', disabled: false, effects: [], attachments: 0, screenshot: '/9j/AA==' };
  const node = () => ({ nodeId: 'ax-17', backendDOMNodeId: 17, role: { value: state.tag === 'INPUT' ? 'textbox' : 'button' }, name: { value: state.name }, value: { value: 'DO_NOT_DISCLOSE_FORM_VALUE' }, properties: [] });
  const api = {
    tabs: { async get() { return { url: state.url }; } },
    debugger: {
      async attach() { state.attachments++; }, async detach() {},
      async sendCommand(_target, method, args) {
        if (method === 'Page.getFrameTree') return { frameTree: { frame: { id: 'main' } } };
        if (method === 'Accessibility.getFullAXTree' || method === 'Accessibility.getPartialAXTree') return { nodes: [node()] };
        if (method === 'DOM.describeNode') return { node: { nodeName: state.tag, attributes: ['type', state.type, ...(state.disabled ? ['disabled', ''] : [])] } };
        if (method === 'DOM.resolveNode') return { object: { objectId: 'object-17' } };
        if (method === 'DOM.getDocument') return { root: { backendNodeId: 1 } };
        if (method === 'Runtime.callFunctionOn' || method === 'Page.navigate') { state.effects.push({ method, args }); return { result: { value: true } }; }
        if (method === 'Page.getLayoutMetrics') return { cssVisualViewport: { pageX: 0, pageY: 0, clientWidth: 1400, clientHeight: 900 } };
        if (method === 'Page.captureScreenshot') return { data: state.screenshot };
        return {};
      },
    },
  };
  let serial = 0, effects = 0;
  const port = new ChromePort({ chrome: api, now: () => 1000, nonce: () => `ref-${++serial}` });
  const guard = { origin: 'https://example.test', assertCurrent() {}, beforeEffect() { effects++; } };
  const request = (command, args = {}) => ({ command, args, tab_id: 7, consent_id: 'consent-1', document_revision: 0, expires_at_ms: 20_000 });
  return { state, port, guard, request, effects: () => effects };
}

test('snapshot produces scoped refs but no form values or URL query secrets', async () => {
  const s = setup(); const out = await s.port.read(s.request('snapshot'), s.guard);
  assert.equal(out.nodes[0].role, 'button'); assert.ok(out.nodes[0].element_ref);
  assert.equal(JSON.stringify(out).includes('DO_NOT_DISCLOSE'), false); assert.equal(JSON.stringify(out).includes('not-returned'), false);
});
test('two reads reuse one real Chrome debugger attachment', async () => {
  const s = setup(); await Promise.all([s.port.read(s.request('snapshot'), s.guard), s.port.read(s.request('snapshot'), s.guard)]);
  assert.equal(s.state.attachments, 1);
});
test('click consumes a snapshot ref and a fixed function, not model code', async () => {
  const s = setup(); const out = await s.port.read(s.request('snapshot'), s.guard);
  await s.port.mutate(s.request('click', { element_ref: out.nodes[0].element_ref }), s.guard);
  assert.equal(s.effects(), 1); assert.equal(s.state.effects.length, 1);
  assert.equal(s.state.effects[0].method, 'Runtime.callFunctionOn');
});
test('document invalidation rejects old element references before a native effect', async () => {
  const s = setup(); const out = await s.port.read(s.request('snapshot'), s.guard); s.port.invalidate(7);
  await assert.rejects(s.port.mutate(s.request('click', { element_ref: out.nodes[0].element_ref }), s.guard), { code: 'STALE_ELEMENT' });
  assert.equal(s.effects(), 0);
});
test('a changed accessible identity rejects a reused backend node', async () => {
  const s = setup(); const out = await s.port.read(s.request('snapshot'), s.guard); s.state.name = 'Delete everything';
  await assert.rejects(s.port.mutate(s.request('click', { element_ref: out.nodes[0].element_ref }), s.guard), { code: 'STALE_ELEMENT' });
  assert.equal(s.effects(), 0);
});
test('restricted input fields refuse typing before the native effect boundary', async () => {
  const s = setup(); s.state.tag = 'INPUT'; s.state.name = 'Sign in'; s.state.type = 'password';
  const out = await s.port.read(s.request('snapshot'), s.guard);
  await assert.rejects(s.port.mutate(s.request('type', { element_ref: out.nodes[0].element_ref, text: 'not a real password' }), s.guard), { code: 'SENSITIVE_TARGET' });
  assert.equal(s.effects(), 0);
});
test('typing passes text as a CDP value, never interpolates it into JavaScript', async () => {
  const s = setup(); s.state.tag = 'INPUT'; const out = await s.port.read(s.request('snapshot'), s.guard);
  const text = '");globalThis.injected=true;//';
  await s.port.mutate(s.request('type', { element_ref: out.nodes[0].element_ref, text }), s.guard);
  assert.equal(s.state.effects[0].args.functionDeclaration.includes(text), false);
  assert.equal(s.state.effects[0].args.arguments[0].value, text);
});
test('live origin mismatch refuses a page read before attachment', async () => {
  const s = setup(); s.state.url = 'https://private.test/';
  await assert.rejects(s.port.read(s.request('snapshot'), s.guard), { code: 'ORIGIN_NOT_SHARED' });
  assert.equal(s.state.attachments, 0);
});
test('screenshots are viewport-bounded and reject oversize native output', async () => {
  const s = setup(); const small = await s.port.read(s.request('screenshot'), s.guard); assert.equal(small.mime_type, 'image/jpeg');
  s.state.screenshot = '/9j/' + 'A'.repeat(50_000);
  await assert.rejects(s.port.read(s.request('screenshot'), s.guard), { code: 'OUTPUT_TOO_LARGE' });
});
test('guard runs again after async target lookup and before native mutation', async () => {
  const s = setup(); const out = await s.port.read(s.request('snapshot'), s.guard);
  const guard = { ...s.guard, beforeEffect() { throw Object.assign(new Error(), { code: 'REVOKED' }); } };
  await assert.rejects(s.port.mutate(s.request('click', { element_ref: out.nodes[0].element_ref }), guard), { code: 'REVOKED' });
  assert.equal(s.state.effects.length, 0);
});

test('fixed typing function rechecks field sensitivity after focus handlers run', async () => {
  const { runInNewContext } = await import('node:vm');
  const s = setup(); s.state.tag = 'INPUT';
  const out = await s.port.read(s.request('snapshot'), s.guard);
  await s.port.mutate(s.request('type', { element_ref: out.nodes[0].element_ref, text: 'synthetic-only' }), s.guard);
  const declaration = s.state.effects[0].args.functionDeclaration;
  const behavior = runInNewContext(`
    class HTMLInputElement {};
    class HTMLTextAreaElement {};
    let writes=0,events=0;
    Object.defineProperty(HTMLInputElement.prototype,'value',{set(value){writes++;}});
    const node=Object.assign(new HTMLInputElement(),{tagName:'INPUT',type:'text',isConnected:true,disabled:false,readOnly:false,
      getAttribute(name){return name==='type'?this.type:name==='autocomplete'?'':null;},
      focus(){this.type='password';},dispatchEvent(){events++;}});
    let refused=false;
    try { (${declaration}).call(node,'synthetic-only'); } catch { refused=true; }
    ({refused,writes,events});
  `, { InputEvent: class {}, Event: class {} });
  assert.equal(behavior.refused, true); assert.equal(behavior.writes, 0); assert.equal(behavior.events, 0);
});
