/**
 * Local execution interlock, not a lease issuer or durable action owner.
 * Only the trusted native host may supply commands. The existing owner must
 * authorize every call and persist effects before using this actuator.
 */
import { BrowserLinkError, CREATE_COMMANDS, READ_COMMANDS, RESULT_SCHEMA, boundedJSON, httpURL, refuse, validateCommand } from './protocol.mjs';

export class SharedTabController {
  #tabs = new Map();
  #requests = new Map();
  #locks = new Map();
  #uncertain = new Set();
  #connected = true;
  #creations = 0;
  #pendingShares = 0;
  constructor({ adapter, connectionGeneration, now = Date.now, nonce = () => crypto.randomUUID(), maxRequestIds = 4096 }) {
    if (!adapter || typeof adapter.read !== 'function' || typeof adapter.mutate !== 'function' || typeof connectionGeneration !== 'string' || !connectionGeneration || !Number.isSafeInteger(maxRequestIds) || maxRequestIds < 1) throw new TypeError('Invalid Browser Link constructor');
    this.adapter = adapter; this.connectionGeneration = connectionGeneration;
    this.now = now; this.nonce = nonce; this.maxRequestIds = maxRequestIds;
  }
  share(tabId, origin, allowCreate = false) {
    if (!this.#connected) refuse('DISCONNECTED');
    if (!Number.isSafeInteger(tabId) || tabId < 0 || typeof allowCreate !== 'boolean') refuse('INVALID_COMMAND');
    if (!this.#tabs.has(tabId) && this.#tabs.size + this.#pendingShares >= 64) refuse('SHARE_LIMIT');
    const url = httpURL(origin);
    if (url.pathname !== '/' || url.search || url.hash) refuse('INVALID_COMMAND');
    this.adapter.invalidate?.(tabId);
    // Physical in-flight state survives local consent revocation/re-sharing.
    const lock = this.#locks.get(tabId) ?? { readers: 0, busy: false, fence: -1, holder: null };
    this.#locks.set(tabId, lock);
    const tab = { tab_id: tabId, origin: url.origin, consent_id: this.nonce(), document_revision: 0,
      allow_create: allowCreate, navigating: false, lock };
    this.#tabs.set(tabId, tab);
    return this.#view(tab);
  }
  #view(tab) {
    return Object.freeze({ tab_id: tab.tab_id, origin: tab.origin, consent_id: tab.consent_id,
      document_revision: tab.document_revision, allow_create: tab.allow_create,
      state: this.#uncertain.has(tab.tab_id) ? 'effect_unresolved' : tab.lock.busy ? 'busy' : tab.navigating ? 'navigating' : 'shared' });
  }
  inventory() { return [...this.#tabs.values()].map(tab => this.#view(tab)); }
  invalidate(tabId) {
    const tab = this.#tabs.get(tabId);
    if (tab) { if (tab.document_revision === Number.MAX_SAFE_INTEGER) this.revoke(tabId); else tab.document_revision++; }
    this.adapter.invalidate?.(tabId);
  }
  navigation(tabId, navigating) {
    const tab = this.#tabs.get(tabId);
    if (!tab) return;
    tab.navigating = navigating;
    // Completion is a new document boundary even for a same-URL reload.
    this.invalidate(tabId);
  }
  revoke(tabId) { this.#tabs.delete(tabId); this.adapter.invalidate?.(tabId); }
  disconnect() { this.#connected = false; for (const id of [...this.#tabs.keys()]) this.revoke(id); }
  #basic(request) {
    if (!this.#connected) refuse('DISCONNECTED');
    if (request.connection_generation !== this.connectionGeneration) refuse('STALE_CONNECTION');
    const tab = this.#tabs.get(request.tab_id);
    if (!tab) refuse('TAB_NOT_SHARED');
    if (request.consent_id !== tab.consent_id) refuse('CONSENT_MISMATCH');
    if (tab.navigating) refuse('TARGET_NAVIGATING');
    if (this.now() >= request.expires_at_ms) refuse('EXPIRED');
    return tab;
  }
  #receipt(request, status, effect, extra = {}) {
    return { schema: RESULT_SCHEMA, request_id: request?.request_id ?? null, connection_generation: this.connectionGeneration, status, effect, ...extra };
  }
  #creationOutput(entry, code) {
    return { kind: 'browser_creation', created: { ...entry.created }, sharing: { state: 'not_shared', code } };
  }
  async execute(input) {
    let request;
    try {
      request = validateCommand(input, this.now());
      const tab = this.#basic(request);
      const digest = boundedJSON(request);
      const known = this.#requests.get(request.request_id);
      if (known) {
        if (known.digest !== digest) return this.#receipt(request, 'refused', 'NOT_APPLIED', { code: 'REQUEST_ID_CONFLICT', original_effect: known.result?.effect ?? 'EFFECT_UNKNOWN' });
        if (known.result) return { ...structuredClone(known.result), replayed: true };
        return this.#receipt(request, 'pending', known.read ? 'NOT_APPLIED' : 'EFFECT_UNKNOWN', { code: 'IN_FLIGHT', replayed: true });
      }
      const read = READ_COMMANDS.includes(request.command), creation = CREATE_COMMANDS.includes(request.command);
      if (!read && this.#uncertain.has(request.tab_id)) refuse('EFFECT_UNRESOLVED');
      if (tab.document_revision !== request.document_revision) refuse('STALE_DOCUMENT');
      const lock = tab.lock;
      if (lock.busy || (!read && lock.readers > 0)) refuse('TAB_BUSY');
      if (read && lock.readers >= 4) refuse('READ_LIMIT');
      if (!read) {
        if (request.writer.fence < lock.fence) refuse('STALE_WRITER');
        if (request.writer.fence === lock.fence && request.writer.holder_ref !== lock.holder) refuse('WRITER_MISMATCH');
        if (request.command === 'navigate' && httpURL(request.args.url).origin !== tab.origin) refuse('ORIGIN_NOT_SHARED');
        if (creation && !tab.allow_create) refuse('CREATION_NOT_SHARED');
      }
      if (this.#requests.size >= this.maxRequestIds) refuse('REPLAY_GUARD_FULL');
      if (creation && (this.#creations >= 64 || this.#tabs.size + this.#pendingShares >= 64)) refuse('CREATION_LIMIT');
      // Reserve before any await. Every dispatched creation consumes the
      // connection budget, including an uncertain or subsequently unshared one.
      if (creation) { this.#creations++; this.#pendingShares++; }
      const entry = { digest, read, dispatched: false, result: null, tab_id: request.tab_id,
        created: null, pendingShare: creation };
      this.#requests.set(request.request_id, entry);
      if (read) lock.readers++; else { lock.busy = true; lock.fence = request.writer.fence; lock.holder = request.writer.holder_ref; }
      const assertCurrent = () => {
        if (entry.result !== null) refuse('ACTION_CLOSED');
        const current = this.#basic(request);
        if (current !== tab || current.document_revision !== request.document_revision) refuse('STALE_DOCUMENT');
        if (!read && (current.lock.fence !== request.writer.fence || current.lock.holder !== request.writer.holder_ref)) refuse('STALE_WRITER');
      };
      try {
        assertCurrent();
        const guard = {
          assertCurrent, origin: tab.origin,
          beforeEffect: () => { assertCurrent(); entry.dispatched = true; },
          creationConfirmed: created => {
            // Capture exact native evidence before awaiting page readiness.
            if (!creation || !entry.dispatched || entry.result !== null || entry.created !== null || !created || typeof created !== 'object' || Array.isArray(created)) refuse('ACTUATOR_CONTRACT_VIOLATION');
            const keys = Object.keys(created).sort().join(',');
            const expectedKind = request.command === 'create_tab' ? 'tab' : 'window';
            if (created.kind !== expectedKind || !['kind,tab_id,window_id', 'kind,window_id'].includes(keys) ||
                !Number.isSafeInteger(created.window_id) || created.window_id < 0 ||
                (expectedKind === 'tab' && !Object.hasOwn(created, 'tab_id')) ||
                (Object.hasOwn(created, 'tab_id') && (!Number.isSafeInteger(created.tab_id) || created.tab_id < 0 || created.tab_id === request.tab_id))) refuse('ACTUATOR_CONTRACT_VIOLATION');
            entry.created = Object.freeze(JSON.parse(boundedJSON(created, 512)));
          },
          shareCreated: child => {
            assertCurrent();
            if (!creation || !tab.allow_create || !entry.created || !entry.pendingShare ||
                child?.id !== entry.created.tab_id || child.windowId !== entry.created.window_id ||
                child.status !== 'complete' || child.incognito !== false ||
                (typeof child.pendingUrl === 'string' && child.pendingUrl)) refuse('CREATED_TAB_NOT_READY');
            const origin = httpURL(child.url).origin;
            if (origin !== httpURL(request.args.url).origin) refuse('CREATED_TAB_ORIGIN_CHANGED');
            if (this.#tabs.has(child.id)) refuse('CHILD_ALREADY_SHARED');
            // No asynchronous gap between the final authority check and consent.
            this.#pendingShares--; entry.pendingShare = false;
            this.share(child.id, origin, false);
            return { state: 'shared' };
          },
        };
        const output = read ? await this.adapter.read(request, guard) : await this.adapter.mutate(request, guard);
        if (!read && (!entry.dispatched || (creation && !entry.created))) {
          // Missing evidence cannot prove the absence of a dispatched effect.
          entry.dispatched = true;
          refuse('ACTUATOR_CONTRACT_VIOLATION');
        }
        if (read) assertCurrent(); else this.invalidate(request.tab_id);
        // Revocation after a known successful dispatch prevents output disclosure.
        const stillShared = this.#tabs.get(request.tab_id) === tab;
        const extra = stillShared ? { output: JSON.parse(boundedJSON(output)), document_revision: tab.document_revision } : { code: 'REVOKED_AFTER_DISPATCH' };
        const result = this.#receipt(request, 'completed', read ? 'NOT_APPLIED' : 'APPLIED', extra);
        boundedJSON(result);
        entry.result = result;
      } catch (error) {
        const code = error instanceof BrowserLinkError ? error.code : 'ACTUATOR_FAILURE';
        if (entry.created) {
          // Creation evidence is already qualified. A later sharing failure
          // must never turn a known-created tab/window into an unknown effect.
          this.invalidate(request.tab_id);
          const extra = this.#tabs.get(request.tab_id) === tab
            ? { output: this.#creationOutput(entry, code), document_revision: tab.document_revision }
            : { code: 'REVOKED_AFTER_DISPATCH' };
          entry.result = this.#receipt(request, 'completed', 'APPLIED', extra);
        } else {
          if (!read && entry.dispatched) { this.#uncertain.add(request.tab_id); this.invalidate(request.tab_id); }
          entry.result = this.#receipt(request, 'refused', !read && entry.dispatched ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED', { code });
        }
      } finally {
        if (entry.pendingShare) { this.#pendingShares--; entry.pendingShare = false; }
        if (creation && !entry.dispatched) this.#creations--;
        if (read) lock.readers--; else lock.busy = false;
      }
      return structuredClone(entry.result);
    } catch (error) {
      return this.#receipt(request, 'refused', 'NOT_APPLIED', { code: error instanceof BrowserLinkError ? error.code : 'INVALID_COMMAND' });
    }
  }
}
