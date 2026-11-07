'use strict';

// Fixed private entry for one original Workbench relay resource. Normal calls
// still use the pinned upstream Playwright MCP Server and owned BrowserContext.
// No vault discovery, unlock, persistent profile, CDP attachment, or retry.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const Module = require('node:module');

const USE_SCHEMA = 'mastermind.workbench_browser_credential_use.v1';
const GRANT_SCHEMA = 'mastermind.workbench_browser_credential_grant.v1';
const RESULT_SCHEMA = 'mastermind.workbench_browser_credential_result.v1';
const TARGET_SCHEMA = 'mastermind.workbench_browser_credential_target.v1';
const MCP_VERSION = '0.0.79';
const PLAYWRIGHT_VERSION = '1.63.0-alpha-2026-08-05';
const MAX_INPUT = 2 * 1024 * 1024;
const MAX_OUTPUT = 4 * 1024 * 1024;
const BLOCKED_TOOLS = new Set(['browser_take_screenshot', 'browser_console_messages', 'browser_network_requests']);
const ALLOWED_TOOLS = new Set(['browser_click', 'browser_close', 'browser_console_messages',
  'browser_fill_form', 'browser_hover', 'browser_navigate', 'browser_network_requests',
  'browser_press_key', 'browser_select_option', 'browser_snapshot', 'browser_tabs',
  'browser_take_screenshot', 'browser_type', 'browser_wait_for']);
const FILENAME_KEYS = new Set(['filename', 'fileName', 'path', 'outputDir', 'outputFile', 'filePath']);

function closed(value, keys) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).sort().join('\0') === [...keys].sort().join('\0');
}
function refuse() { throw new Error('CREDENTIAL_REFUSED'); }
function result(effect_state, code) { return { schema: RESULT_SCHEMA, effect_state, code }; }
function validOrigin(origin) {
  if (typeof origin !== 'string' || origin.length > 512 || /[^\x21-\x7e]/.test(origin)) return false;
  try { const u = new URL(origin); return u.protocol === 'https:' && !u.username && !u.password && u.origin === origin; }
  catch { return false; }
}
function validateUse(use, resourceId, now = Date.now()) {
  if (!closed(use, ['schema', 'grant', 'resource_id', 'expires_at_ms', 'binding_sha256'])
      || use.schema !== USE_SCHEMA || use.resource_id !== resourceId
      || !Number.isSafeInteger(use.expires_at_ms) || use.expires_at_ms <= now
      || !/^[a-f0-9]{64}$/.test(use.binding_sha256)) refuse();
  const g = use.grant;
  if (!closed(g, ['schema', 'grant_ref', 'backend', 'vault_directory', 'vault_device',
      'vault_inode', 'item_ref', 'account_identifier', 'origin', 'expires_at_ms'])
      || g.schema !== GRANT_SCHEMA || g.backend !== 'hermes-fernet-v1'
      || typeof g.grant_ref !== 'string' || !/^credential:[a-f0-9]{32}$/.test(g.grant_ref)
      || typeof g.item_ref !== 'string' || !/^vault_[a-f0-9]{12}$/.test(g.item_ref)
      || typeof g.account_identifier !== 'string' || !g.account_identifier
      || Buffer.byteLength(g.account_identifier) > 320 || g.account_identifier.trim() !== g.account_identifier
      || /[\x00-\x1f]/.test(g.account_identifier) || !validOrigin(g.origin)
      || !Number.isSafeInteger(g.expires_at_ms) || g.expires_at_ms < use.expires_at_ms
      || typeof g.vault_directory !== 'string' || !path.isAbsolute(g.vault_directory)
      || path.normalize(g.vault_directory) !== g.vault_directory || g.vault_directory.includes('\0')
      || !Number.isSafeInteger(g.vault_device) || g.vault_device < 0
      || !Number.isSafeInteger(g.vault_inode) || g.vault_inode < 1) refuse();
  return use;
}

function constrainModules(runtimeRoot) {
  const root = fs.realpathSync(path.join(runtimeRoot, 'node_modules')) + path.sep;
  const original = Module._resolveFilename;
  const builtins = new Set(Module.builtinModules.flatMap(n => [n, 'node:' + n]));
  Module._resolveFilename = function(request, parent, isMain, options) {
    const resolved = original.call(this, request, parent, isMain, options);
    if (!builtins.has(resolved) && !builtins.has(request)) {
      const actual = fs.realpathSync(resolved);
      if (!actual.startsWith(root)) refuse();
    }
    return resolved;
  };
  function pinned(name, version) {
    const base = path.join(root, name);
    const metadata = JSON.parse(fs.readFileSync(path.join(base, 'package.json'), 'utf8'));
    if (metadata.name !== name || metadata.version !== version) refuse();
    return require(base);
  }
  return {
    mcp: pinned('@playwright/mcp', MCP_VERSION),
    playwright: pinned('playwright', PLAYWRIGHT_VERSION),
    fernet: pinned('fernet', '0.3.3'),
  };
}

function secretRepresentations(value) {
  const variants = new Set([value]);
  // Exact normal serializer representations exercised in the pinned canary.
  variants.add(JSON.stringify(value).slice(1, -1));
  variants.add(value.replaceAll("'", "''"));
  variants.add(encodeURIComponent(value));
  variants.add(new URLSearchParams({ v: value }).toString().slice(2));
  variants.add(value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;'));
  for (const v of [...variants]) variants.add(JSON.stringify(v).slice(1, -1));
  return [...variants].filter(Boolean).sort((a, b) => b.length - a.length);
}

class PrivateRedaction {
  constructor() {
    this.map = Object.create(null);
    this.values = new Set();
    this.credentials = new Set();
    this.bytes = 0;
  }
  add(password, identifier) {
    // These same values already live in the private redaction map. Keep only
    // their bounded membership here; no password-derived verifier is needed.
    if (!this.credentials.has(password) && this.credentials.size >= 8) refuse();
    const additions = [...new Set([...secretRepresentations(password), ...secretRepresentations(identifier)])]
      .filter(v => !this.values.has(v));
    const addedBytes = additions.reduce((n, v) => n + Buffer.byteLength(v), 0);
    if (this.values.size + additions.length > 256 || this.bytes + addedBytes > 128 * 1024) refuse();
    // Append-only: upstream asynchronous console/snapshot writers share this
    // exact object and may still need an earlier value after a later fill.
    for (const value of additions.sort((a, b) => b.length - a.length)) {
      this.map['MMX_PRIVATE_' + crypto.randomBytes(16).toString('hex')] = value;
      this.values.add(value);
    }
    this.credentials.add(password);
    this.bytes += addedBytes;
    // The logical set is monotonic. Reorder the SAME object synchronously so
    // the donor's insertion-order redactor always matches the longest value
    // first, including a new password prefixed by an older identifier.
    const entries = Object.entries(this.map).sort((a, b) => b[1].length - a[1].length);
    for (const key of Object.keys(this.map)) delete this.map[key];
    for (const [key, value] of entries) this.map[key] = value;
  }
  contains(value, depth = 0) {
    if (depth > 20) return true;
    if (typeof value === 'string') return [...this.values, ...Object.keys(this.map)].some(s => value.includes(s));
    if (Array.isArray(value)) return value.some(v => this.contains(v, depth + 1));
    if (value && typeof value === 'object') return Object.entries(value).some(([k, v]) => this.contains(k, depth + 1) || this.contains(v, depth + 1));
    return false;
  }
  text(value) {
    let text = value;
    for (const secret of [...this.values, ...Object.keys(this.map)].sort((a, b) => b.length - a.length))
      text = text.split(secret).join('[REDACTED]');
    return text;
  }
  output(value, depth = 0) {
    if (depth > 20) refuse();
    if (typeof value === 'string') return this.text(value);
    if (Array.isArray(value)) return value.map(v => this.output(v, depth + 1));
    if (value && typeof value === 'object') {
      if ('type' in value && ['image', 'audio', 'resource', 'resource_link'].includes(value.type)) refuse();
      const out = Object.create(null);
      for (const [key, val] of Object.entries(value)) {
        if (this.contains(key)) refuse();
        if (key === '_meta' || key === 'structuredContent') continue;
        out[key] = this.output(val, depth + 1);
      }
      return out;
    }
    return value;
  }
}

function decodeLogin(fernet, material, grant) {
  if (!closed(material, ['key', 'ciphertext']) || typeof material.key !== 'string'
      || typeof material.ciphertext !== 'string' || material.ciphertext.length > 1024 * 1024
      || !/^[A-Za-z0-9_-]{43}=$/.test(material.key)
      || !/^[A-Za-z0-9_-]+={0,2}$/.test(material.ciphertext)) refuse();
  const key = Buffer.from(material.key, 'base64url');
  const token = Buffer.from(material.ciphertext, 'base64url');
  // The donor decoder assumes full fields. Reject truncated/noncanonical input
  // before handing it to the unchanged, pinned Fernet implementation.
  if (key.length !== 32 || key.toString('base64url') + '=' !== material.key
      || token.length < 73 || token[0] !== 0x80 || (token.length - 57) % 16 !== 0
      || token.toString('base64url') !== material.ciphertext.replace(/=+$/, '')) refuse();
  let plaintext;
  try {
    plaintext = new fernet.Token({ secret: new fernet.Secret(material.key), token: material.ciphertext, ttl: 0 }).decode();
  } finally { key.fill(0); token.fill(0); }
  if (typeof plaintext !== 'string' || Buffer.byteLength(plaintext) > 1024 * 1024) refuse();
  const document = JSON.parse(plaintext);
  if (!closed(document, ['version', 'items']) || document.version !== 1 || !Array.isArray(document.items)
      || document.items.length > 4096) refuse();
  const matches = document.items.filter(r => r && r.id === grant.item_ref);
  if (matches.length !== 1) refuse();
  const row = matches[0];
  if (row.kind !== 'login' || row.origin !== grant.origin || row.identifier !== grant.account_identifier
      || !['username', 'email', 'phone'].includes(row.identifier_type)
      || !row.secret || typeof row.secret !== 'object' || Array.isArray(row.secret)
      || typeof row.secret.password !== 'string' || !row.secret.password
      || Buffer.byteLength(row.secret.password) > 4096 || /[\x00\r\n]/.test(row.secret.password)) refuse();
  return { password: row.secret.password, identifier: row.identifier };
}

// These functions execute only in the held main-frame document. They are not
// a generic evaluate tool and no caller supplies JavaScript or selectors.
function operateTarget(value, data) {
  const inspect = (doc, origin) => {
    if (doc !== document || location.origin !== origin) return null;
    const visible = el => el instanceof HTMLInputElement && el.isConnected && !el.disabled
      && !el.readOnly && [...el.getClientRects()].some(r => r.width > 0 && r.height > 0)
      && !['hidden', 'collapse'].includes(getComputedStyle(el).visibility);
    const passwords = [...doc.querySelectorAll('input[type="password"]')].filter(visible);
    if (passwords.length !== 1 || passwords[0].autocomplete.toLowerCase().split(/\s+/).includes('new-password')) return null;
    const password = passwords[0];
    if (!password.form || new URL(password.form.action || location.href).origin !== origin) return null;
    const candidates = [...password.form.querySelectorAll('input')].filter(el => visible(el)
      && ['text', 'email', 'tel'].includes(el.type)
      && (['username', 'email', 'tel'].includes(el.autocomplete.toLowerCase())
          || /^(user(name)?|email|login|identifier)$/i.test(el.name || el.id)));
    if (candidates.length !== 1) return null;
    return { doc, password, identifier: candidates[0], form: password.form, origin };
  };
  if (data.mode === 'inspect') return inspect(value, data.origin);
  const t = value;
  const current = () => {
    if (!t || Date.now() >= data.expires) return false;
    const observed = inspect(t.doc, t.origin);
    return !!observed && observed.password === t.password && observed.identifier === t.identifier
      && observed.form === t.form;
  };
  if (data.mode === 'check') return current();
  if (data.mode !== 'fill' || !current()) return 'TARGET_REFUSED';
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(t.identifier, data.identifier);
  t.identifier.dispatchEvent(new Event('input', { bubbles: true }));
  t.identifier.dispatchEvent(new Event('change', { bubbles: true }));
  if (!current() || t.identifier.value !== data.identifier) return 'FILL_UNCERTAIN';
  setter.call(t.password, data.password);
  t.password.dispatchEvent(new Event('input', { bubbles: true }));
  t.password.dispatchEvent(new Event('change', { bubbles: true }));
  return current() ? 'WRITE_RETURNED' : 'FILL_UNCERTAIN';
}

class CredentialTarget {
  constructor(context, fernet, resourceId, resourceExpiry, redaction) {
    this.context = context; this.fernet = fernet; this.resourceId = resourceId;
    this.resourceExpiry = resourceExpiry; this.redaction = redaction; this.pending = null;
  }
  async prepare(params) {
    if (this.pending || !closed(params, ['use', 'action_id']) || !/^[a-f0-9]{32}$/.test(params.action_id)) refuse();
    const use = validateUse(params.use, this.resourceId);
    if (use.expires_at_ms > this.resourceExpiry) refuse();
    const pages = this.context.pages().filter(p => !p.isClosed());
    if (pages.length !== 1) return result('NOT_APPLIED', 'TARGET_REFUSED');
    const page = pages[0];
    let doc, target;
    try {
      doc = await page.evaluateHandle(() => document);
      target = await doc.evaluateHandle(operateTarget, { mode: 'inspect', origin: use.grant.origin });
      if (!await target.evaluate(operateTarget, { mode: 'check', expires: use.expires_at_ms })) {
        await target.dispose(); return result('NOT_APPLIED', 'TARGET_REFUSED');
      }
      const targetRef = crypto.randomBytes(16).toString('hex');
      this.pending = { target, page, use, targetRef };
      return { schema: TARGET_SCHEMA, target_ref: targetRef, status: 'READY' };
    } catch {
      if (target) await target.dispose().catch(() => {});
      return result('NOT_APPLIED', 'TARGET_REFUSED');
    } finally { if (doc) await doc.dispose().catch(() => {}); }
  }
  async abort(params) {
    if (!closed(params, ['target_ref']) || !this.pending || params.target_ref !== this.pending.targetRef) refuse();
    const pending = this.pending; this.pending = null;
    await pending.target.dispose().catch(() => {});
    return result('NOT_APPLIED', 'VAULT_UNAVAILABLE');
  }
  async fill(params) {
    if (!closed(params, ['target_ref', 'material']) || !this.pending
        || params.target_ref !== this.pending.targetRef) refuse();
    const pending = this.pending; this.pending = null; // consume before any possible effect
    let attempted = false;
    try {
      validateUse(pending.use, this.resourceId);
      const pages = this.context.pages().filter(p => !p.isClosed());
      if (pages.length !== 1 || pages[0] !== pending.page
          || !await pending.target.evaluate(operateTarget, { mode: 'check', expires: pending.use.expires_at_ms }))
        return result('NOT_APPLIED', 'TARGET_REFUSED');
      validateUse(pending.use, this.resourceId); // trusted Node clock after awaited target check
      let login;
      try { login = decodeLogin(this.fernet, params.material, pending.use.grant); }
      catch { return result('NOT_APPLIED', 'ITEM_REFUSED'); }
      try { this.redaction.add(login.password, login.identifier); }
      catch { return result('NOT_APPLIED', 'CREDENTIAL_LIMIT'); }
      // The native shared redaction map is populated before page input/change
      // handlers can log. It remains alive for this original child lifetime.
      validateUse(pending.use, this.resourceId); // final trusted admission boundary
      const currentPages = this.context.pages().filter(p => !p.isClosed());
      if (currentPages.length !== 1 || currentPages[0] !== pending.page)
        return result('NOT_APPLIED', 'TARGET_REFUSED');
      attempted = true;
      const code = await pending.target.evaluate(operateTarget, { mode: 'fill', ...login, expires: pending.use.expires_at_ms });
      if (code === 'TARGET_REFUSED') return result('NOT_APPLIED', code);
      if (code !== 'WRITE_RETURNED') return result('EFFECT_UNKNOWN', 'FILL_UNCERTAIN');
      // Read the native form values through Playwright's injected utility world,
      // independently of any page-overridden main-world getter/setter.
      const password = (await pending.target.getProperty('password')).asElement();
      const identifier = (await pending.target.getProperty('identifier')).asElement();
      try {
        const verified = password && identifier && await password.inputValue() === login.password
          && await identifier.inputValue() === login.identifier
          && await pending.target.evaluate(operateTarget, { mode: 'check', expires: pending.use.expires_at_ms });
        return verified ? result('APPLIED', 'FILLED') : result('EFFECT_UNKNOWN', 'FILL_UNCERTAIN');
      } finally { await password?.dispose().catch(() => {}); await identifier?.dispose().catch(() => {}); }
    } catch { return result(attempted ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED', attempted ? 'FILL_UNCERTAIN' : 'PERMISSION_EXPIRED'); }
    finally { await pending.target.dispose().catch(() => {}); }
  }
}

function genericAllowed(message, redaction) {
  if (redaction.contains(message)) return false;
  if (message.method !== 'tools/call') return ['initialize', 'notifications/initialized', 'tools/list', 'ping'].includes(message.method);
  const p = message.params;
  if (!closed(p, ['name', 'arguments']) || !ALLOWED_TOOLS.has(p.name) || BLOCKED_TOOLS.has(p.name)
      || !p.arguments || typeof p.arguments !== 'object' || Array.isArray(p.arguments)) return false;
  const visit = value => {
    if (!value || typeof value !== 'object') return true;
    return Object.entries(value).every(([key, v]) => !FILENAME_KEYS.has(key) && visit(v));
  };
  if (!visit(p.arguments)) return false;
  if (p.name === 'browser_press_key' && !['Enter', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(p.arguments.key)) return false;
  if (p.name === 'browser_click' && ((p.arguments.button && p.arguments.button !== 'left') || (p.arguments.modifiers && p.arguments.modifiers.length))) return false;
  if (p.name === 'browser_navigate') {
    try { const url = new URL(p.arguments.url); if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return false; }
    catch { return false; }
  }
  return true;
}

class PrivateTransport {
  constructor(target, redaction, ownerClose = () => {}) { this.target = target; this.redaction = redaction; this.ownerClose = ownerClose; this.closed = false; this.pendingId = undefined; this.buffer = Buffer.alloc(0); }
  async start() {
    process.stdout.on('error', () => { void this.close(); });
    process.stdin.on('data', chunk => {
      this.buffer = Buffer.concat([this.buffer, chunk]);
      if (this.buffer.length > MAX_INPUT) return this.close();
      let offset;
      while ((offset = this.buffer.indexOf(10)) >= 0) {
        const line = this.buffer.subarray(0, offset); this.buffer = this.buffer.subarray(offset + 1);
        void this.receive(line);
      }
    });
    process.stdin.on('end', () => { void this.close(); });
    process.stdin.on('error', () => { void this.close(); });
  }
  async receive(raw) {
    let message;
    try { message = JSON.parse(raw.toString('utf8')); } catch { return this.close(); }
    if (!message || message.jsonrpc !== '2.0' || typeof message.method !== 'string') return this.close();
    const id = message.id;
    if (id !== undefined && (!Number.isSafeInteger(id) || id < 1)) return this.close();
    if (id !== undefined && this.pendingId !== undefined)
      return this.write({ jsonrpc: '2.0', id, error: { code: -32000, message: 'ORIGINAL_OPERATION_INFLIGHT' } });
    if (id !== undefined) this.pendingId = id;
    if (message.method.startsWith('mastermind/credential_')) {
      if (id === undefined) return this.close();
      try {
        const method = message.method.slice('mastermind/credential_'.length);
        if (!['prepare', 'fill', 'abort'].includes(method)) refuse();
        const observed = await this.target[method](message.params);
        return this.sendPrivate(id, observed);
      } catch {
        const mayHaveWritten = message.method === 'mastermind/credential_fill';
        return this.sendPrivate(id, result(mayHaveWritten ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED',
          mayHaveWritten ? 'FILL_UNCERTAIN' : 'PROTOCOL_REFUSED'));
      }
    }
    if (this.target.pending || !genericAllowed(message, this.redaction))
      return this.send({ jsonrpc: '2.0', id, error: { code: -32602, message: 'BROWSER_REQUEST_REFUSED' } });
    this.onmessage?.(message);
  }
  write(message) {
    const raw = JSON.stringify(message);
    if (Buffer.byteLength(raw) > MAX_OUTPUT) return this.close();
    process.stdout.write(raw + '\n');
  }
  sendPrivate(id, value) {
    // Closed protocol constants are not page text. A password coinciding with
    // FILLED/APPLIED must not corrupt the original effect receipt.
    const ready = closed(value, ['schema', 'status', 'target_ref']) && value.schema === TARGET_SCHEMA
      && value.status === 'READY' && /^[a-f0-9]{32}$/.test(value.target_ref);
    const completed = closed(value, ['schema', 'effect_state', 'code']) && value.schema === RESULT_SCHEMA
      && ['APPLIED', 'NOT_APPLIED', 'EFFECT_UNKNOWN'].includes(value.effect_state)
      && ['FILLED', 'TARGET_REFUSED', 'VAULT_UNAVAILABLE', 'ITEM_REFUSED', 'PERMISSION_EXPIRED',
          'CREDENTIAL_LIMIT', 'FILL_UNCERTAIN', 'PROTOCOL_REFUSED'].includes(value.code)
      && ((value.effect_state === 'APPLIED') === (value.code === 'FILLED'));
    if (completed && ((value.effect_state === 'EFFECT_UNKNOWN') !== (value.code === 'FILL_UNCERTAIN')))
      return this.close();
    if (!ready && !completed) return this.close();
    this.write({ jsonrpc: '2.0', id, result: value });
    if (id === this.pendingId) this.pendingId = undefined;
  }
  async send(message) {
    const id = message.id;
    try { this.write(this.redaction.output(message)); }
    catch { this.write({ jsonrpc: '2.0', id, error: { code: -32000, message: 'BROWSER_RESULT_UNVERIFIED' } }); }
    if (id === this.pendingId) this.pendingId = undefined;
  }
  async close() { if (this.closed) return; this.closed = true; process.stdin.destroy(); this.onclose?.(); void this.ownerClose(); }
}

async function main(argv) {
  if (argv.length !== 5) refuse();
  const [runtimeSelector, chromeSelector, outputDir, resourceId, expiry] = argv;
  const anchored = runtimeSelector === 'runtime';
  if (anchored && (!chromeSelector.startsWith('runtime/browsers/') || chromeSelector.includes('..'))) refuse();
  const runtimeRoot = anchored ? fs.realpathSync('runtime') : runtimeSelector;
  const chromeExecutable = anchored ? fs.realpathSync(chromeSelector) : chromeSelector;
  if (!/^[a-f0-9]{32}$/.test(resourceId) || !Number.isSafeInteger(Number(expiry)) || Number(expiry) <= Date.now()
      || ![runtimeRoot, chromeExecutable, outputDir].every(p => path.isAbsolute(p) && path.normalize(p) === p)) refuse();
  if (fs.realpathSync(__filename) !== path.join(runtimeRoot, 'node_modules/@mastermind/workbench-vault/child.cjs')) refuse();
  const owned = await createOwnedSession({ runtimeRoot, chromeExecutable, outputDir, resourceId, resourceExpiry: Number(expiry) });
  process.on('SIGTERM', () => { void owned.close(); });
  process.on('SIGINT', () => { void owned.close(); });
  try { await owned.server.connect(owned.transport); }
  catch { await owned.close(); throw new Error('CREDENTIAL_CHILD_REFUSED'); }
}

async function createOwnedSession({ runtimeRoot, chromeExecutable, outputDir, resourceId, resourceExpiry }) {
  const { mcp, playwright, fernet } = constrainModules(runtimeRoot);
  let browser, server, closing = false, closingPromise;
  const close = () => {
    if (closing) return closingPromise || Promise.resolve();
    closing = true;
    closingPromise = (async () => {
      if (server) await server.close().catch(() => {});
      if (browser) await browser.close().catch(() => {});
    })();
    return closingPromise;
  };
  try {
    browser = await playwright.chromium.launch({ executablePath: chromeExecutable, headless: true });
    // API isolated:false adopts only this genuinely fresh owned context.
    const context = await browser.newContext({ acceptDownloads: false, serviceWorkers: 'block' });
    context.on('page', page => page.on('download', download => { void download.cancel(); }));
    const redaction = new PrivateRedaction();
    const target = new CredentialTarget(context, fernet, resourceId, resourceExpiry, redaction);
    server = await mcp.createConnection({ browser: { isolated: false }, secrets: redaction.map,
      imageResponses: 'omit', saveSession: false, outputDir, snapshot: { mode: 'full' },
      codegen: 'none', timeouts: { action: 5000, navigation: 10000 } }, async () => context);
    const transport = new PrivateTransport(target, redaction, close);
    return { context, target, redaction, server, transport, close };
  } catch { await close(); throw new Error('CREDENTIAL_CHILD_REFUSED'); }
}

module.exports = { PrivateRedaction, CredentialTarget, PrivateTransport, decodeLogin,
  validateUse, genericAllowed, secretRepresentations, constrainModules, createOwnedSession, main };
if (require.main === module) main(process.argv.slice(2)).catch(() => { process.exitCode = 70; process.stderr.write('CREDENTIAL_CHILD_REFUSED\n'); });
