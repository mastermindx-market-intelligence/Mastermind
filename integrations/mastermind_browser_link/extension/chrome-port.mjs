/** Narrow Chrome actuator: no caller-supplied code, CDP methods or selectors. */
import { boundedJSON, httpURL, refuse } from './protocol.mjs';

const ACTIONABLE = new Set(['button', 'link', 'textbox', 'searchbox', 'checkbox', 'radio', 'combobox', 'switch', 'menuitem', 'tab']);
const CLICK = 'function(){ if (!(this instanceof HTMLElement) || !this.isConnected) throw new Error("TARGET_UNAVAILABLE"); HTMLElement.prototype.click.call(this); return true; }';
const TYPE = String.raw`function(value){
  const assertTarget = () => {
    if (!this.isConnected || this.disabled || this.readOnly) throw new Error("TARGET_UNAVAILABLE");
    const tag = this.tagName, type = (this.getAttribute("type") || "").toLowerCase();
    const autocomplete = (this.getAttribute("autocomplete") || "").toLowerCase();
    if (type === "password" || type === "file" || /(?:^|\s)(?:current-password|new-password|one-time-code|cc-[a-z-]+)(?:\s|$)/u.test(autocomplete)) throw new Error("SENSITIVE_TARGET");
    if (tag !== "TEXTAREA" && (tag !== "INPUT" || !["", "text", "search", "url", "tel", "email"].includes(type))) throw new Error("TARGET_UNSUPPORTED");
  };
  assertTarget();
  this.focus();
  assertTarget();
  const proto = this.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto,"value").set.call(this,value);
  this.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertText",data:null}));
  this.dispatchEvent(new Event("change",{bubbles:true}));
  return true;
}`;
const SCROLL = 'function(dx,dy){ if (!this.defaultView) throw new Error("TARGET_UNAVAILABLE"); this.defaultView.scrollBy(dx,dy); return true; }';
const MAX_NODES = 150, MAX_REFS = 2048, MAX_IMAGE_CHARS = 48_000;
const value = item => typeof item?.value === 'string' ? item.value : '';

export class ChromePort {
  #attached = new Map();
  #refs = new Map();
  constructor({ chrome, now = Date.now, nonce = () => crypto.randomUUID() }) {
    if (!chrome?.debugger?.sendCommand || !chrome?.tabs?.get) throw new TypeError('Chrome API required');
    this.chrome = chrome; this.now = now; this.nonce = nonce;
  }
  #send(tabId, method, params = {}) { return this.chrome.debugger.sendCommand({ tabId }, method, params); }
  invalidate(tabId) { for (const [key, ref] of this.#refs) if (ref.tab_id === tabId) this.#refs.delete(key); }
  detached(tabId) { this.#attached.delete(tabId); this.invalidate(tabId); }
  async detach(tabId) {
    this.detached(tabId);
    try { await this.chrome.debugger.detach({ tabId }); } catch { /* already detached; no page command is retried */ }
  }
  async #origin(request, guard) {
    const tab = await this.chrome.tabs.get(request.tab_id);
    if (httpURL(tab.url).origin !== guard.origin) refuse('ORIGIN_NOT_SHARED');
    guard.assertCurrent(); return tab;
  }
  async #ensure(request, guard) {
    await this.#origin(request, guard);
    let attached = this.#attached.get(request.tab_id);
    if (!attached) {
      attached = (async () => {
        guard.assertCurrent();
        await this.chrome.debugger.attach({ tabId: request.tab_id }, '1.3');
        guard.assertCurrent();
        await this.#send(request.tab_id, 'Page.enable');
        await this.#send(request.tab_id, 'DOM.enable');
      })();
      this.#attached.set(request.tab_id, attached);
    }
    try { await attached; } catch (error) { this.#attached.delete(request.tab_id); throw error; }
    guard.assertCurrent();
  }
  async read(request, guard) {
    await this.#ensure(request, guard);
    if (request.command === 'snapshot') return this.#snapshot(request, guard);
    if (request.command === 'screenshot') return this.#screenshot(request, guard);
    refuse('INVALID_COMMAND');
  }
  async #snapshot(request, guard) {
    const { frameTree } = await this.#send(request.tab_id, 'Page.getFrameTree');
    const frameId = frameTree?.frame?.id;
    if (typeof frameId !== 'string') refuse('TARGET_UNAVAILABLE');
    const tree = await this.#send(request.tab_id, 'Accessibility.getFullAXTree', { frameId });
    if (!Array.isArray(tree.nodes)) refuse('TARGET_UNAVAILABLE');
    const nodes = [];
    for (const [key, ref] of this.#refs) if (ref.expires_at_ms <= this.now()) this.#refs.delete(key);
    for (const node of tree.nodes.slice(0, 5000)) {
      if (node.ignored) continue;
      const role = value(node.role), name = value(node.name);
      if (!name && !ACTIONABLE.has(role)) continue;
      if (role === 'InlineTextBox' || role === 'none') continue;
      const output = { role: role.slice(0, 64), name: name.slice(0, 512) };
      const disabled = node.properties?.some(p => p.name === 'disabled' && p.value?.value === true);
      if (disabled) output.disabled = true;
      if (ACTIONABLE.has(role) && !disabled && name.length <= 512 && Number.isSafeInteger(node.backendDOMNodeId)) {
        while (this.#refs.size >= MAX_REFS) this.#refs.delete(this.#refs.keys().next().value);
        const elementRef = this.nonce();
        this.#refs.set(elementRef, { tab_id: request.tab_id, consent_id: request.consent_id, document_revision: request.document_revision,
          expires_at_ms: Math.min(request.expires_at_ms, this.now() + 30_000), backend_node_id: node.backendDOMNodeId, role, name, frame_id: frameId });
        output.element_ref = elementRef;
      }
      nodes.push(output);
      try { boundedJSON(nodes, 44_000); } catch { nodes.pop(); break; }
      if (nodes.length >= MAX_NODES) break;
    }
    const tab = await this.#origin(request, guard);
    const url = httpURL(tab.url);
    return { kind: 'accessibility_snapshot', untrusted_content: true, url: url.origin + url.pathname,
      document_revision: request.document_revision, nodes, truncated: tree.nodes.length > nodes.length,
      coverage: 'main_frame_only; form_values_omitted; not_a_network_sandbox' };
  }
  async #screenshot(request, guard) {
    const metrics = await this.#send(request.tab_id, 'Page.getLayoutMetrics');
    const viewport = metrics.cssVisualViewport ?? metrics.visualViewport;
    if (!viewport || !Number.isFinite(viewport.clientWidth) || !Number.isFinite(viewport.clientHeight) || viewport.clientWidth <= 0 || viewport.clientHeight <= 0) refuse('TARGET_UNAVAILABLE');
    const width = Math.min(viewport.clientWidth, 1024), height = Math.min(viewport.clientHeight, 768);
    const image = await this.#send(request.tab_id, 'Page.captureScreenshot', { format: 'jpeg', quality: 35, captureBeyondViewport: false,
      clip: { x: viewport.pageX ?? 0, y: viewport.pageY ?? 0, width, height, scale: 0.7 } });
    if (typeof image.data !== 'string' || image.data.length > MAX_IMAGE_CHARS) refuse('OUTPUT_TOO_LARGE');
    if (!image.data.startsWith('/9j/') || !/^[A-Za-z0-9+/]*={0,2}$/u.test(image.data)) refuse('TARGET_UNAVAILABLE');
    await this.#origin(request, guard);
    return { kind: 'viewport_screenshot', untrusted_content: true, mime_type: 'image/jpeg', data: image.data,
      width_css: width, height_css: height, scale: 0.7, clipped_to_limit: width < viewport.clientWidth || height < viewport.clientHeight };
  }
  async #element(request, guard) {
    const ref = this.#refs.get(request.args.element_ref);
    if (!ref || ref.tab_id !== request.tab_id || ref.consent_id !== request.consent_id || ref.document_revision !== request.document_revision || ref.expires_at_ms <= this.now()) refuse('STALE_ELEMENT');
    const current = await this.#send(request.tab_id, 'Accessibility.getPartialAXTree', { backendNodeId: ref.backend_node_id, fetchRelatives: false });
    const identity = current.nodes?.find(node => node.backendDOMNodeId === ref.backend_node_id);
    if (!identity || identity.ignored || value(identity.role) !== ref.role || value(identity.name) !== ref.name) refuse('STALE_ELEMENT');
    const { node } = await this.#send(request.tab_id, 'DOM.describeNode', { backendNodeId: ref.backend_node_id, depth: 0 });
    if (!node) refuse('STALE_ELEMENT');
    const attrs = Object.create(null);
    for (let i = 0; i < (node.attributes?.length ?? 0); i += 2) attrs[String(node.attributes[i]).toLowerCase()] = String(node.attributes[i + 1] ?? '');
    const type = (attrs.type ?? '').toLowerCase(), autocomplete = (attrs.autocomplete ?? '').toLowerCase();
    if (type === 'password' || type === 'file' || /(?:^|\s)(?:current-password|new-password|one-time-code|cc-[a-z-]+)(?:\s|$)/u.test(autocomplete)) refuse('SENSITIVE_TARGET');
    if (Object.hasOwn(attrs, 'disabled') || (request.command === 'type' && Object.hasOwn(attrs, 'readonly'))) refuse('TARGET_UNAVAILABLE');
    if (request.command === 'type' && (!['INPUT', 'TEXTAREA'].includes(node.nodeName) || (node.nodeName === 'INPUT' && !['', 'text', 'search', 'url', 'tel', 'email'].includes(type)))) refuse('TARGET_UNSUPPORTED');
    const { object } = await this.#send(request.tab_id, 'DOM.resolveNode', { backendNodeId: ref.backend_node_id });
    if (typeof object?.objectId !== 'string') refuse('STALE_ELEMENT');
    guard.assertCurrent(); return object.objectId;
  }
  async mutate(request, guard) {
    await this.#ensure(request, guard);
    if (request.command === 'navigate') {
      if (httpURL(request.args.url).origin !== guard.origin) refuse('ORIGIN_NOT_SHARED');
      await this.#origin(request, guard); guard.beforeEffect();
      const result = await this.#send(request.tab_id, 'Page.navigate', { url: request.args.url });
      if (result.errorText) refuse('NAVIGATION_FAILED');
      return { native_command_returned: true, business_effect_verified: false };
    }
    let objectId;
    try {
      let functionDeclaration, args;
      if (request.command === 'click' || request.command === 'type') {
        objectId = await this.#element(request, guard);
        functionDeclaration = request.command === 'click' ? CLICK : TYPE;
        args = request.command === 'click' ? [] : [{ value: request.args.text }];
      } else if (request.command === 'scroll') {
        const { root } = await this.#send(request.tab_id, 'DOM.getDocument', { depth: 0, pierce: false });
        const { object } = await this.#send(request.tab_id, 'DOM.resolveNode', { backendNodeId: root.backendNodeId });
        objectId = object?.objectId; functionDeclaration = SCROLL;
        args = [{ value: request.args.delta_x }, { value: request.args.delta_y }];
      } else refuse('INVALID_COMMAND');
      if (typeof objectId !== 'string') refuse('TARGET_UNAVAILABLE');
      await this.#origin(request, guard); guard.beforeEffect();
      const result = await this.#send(request.tab_id, 'Runtime.callFunctionOn', { objectId, functionDeclaration, arguments: args, returnByValue: true });
      if (result.exceptionDetails) refuse('NATIVE_ACTION_EXCEPTION');
      return { native_command_returned: true, business_effect_verified: false };
    } finally {
      if (objectId) { try { await this.#send(request.tab_id, 'Runtime.releaseObject', { objectId }); } catch { /* release is not a page action or action retry */ } }
    }
  }
}
