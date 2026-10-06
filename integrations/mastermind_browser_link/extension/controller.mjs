/**
 * Local execution interlock, not a lease issuer or durable action owner.
 * Only the trusted native host may supply commands. The existing owner must
 * authorize every call and persist effects before using this actuator.
 */
import { BrowserLinkError, READ_COMMANDS, RESULT_SCHEMA, boundedJSON, httpURL, refuse, validateCommand } from './protocol.mjs';

export class SharedTabController {
  #tabs = new Map();
  #requests = new Map();
  #locks = new Map();
  #uncertain = new Set();
  #connected = true;
  constructor({ adapter, connectionGeneration, now = Date.now, nonce = () => crypto.randomUUID(), maxRequestIds = 4096 }) {
    if (!adapter || typeof adapter.read !== 'function' || typeof adapter.mutate !== 'function' || typeof connectionGeneration !== 'string' || !connectionGeneration || !Number.isSafeInteger(maxRequestIds) || maxRequestIds < 1) throw new TypeError('Invalid Browser Link constructor');
    this.adapter = adapter; this.connectionGeneration = connectionGeneration;
    this.now = now; this.nonce = nonce; this.maxRequestIds = maxRequestIds;
  }
  share(tabId, origin) {
    if (!this.#connected) refuse('DISCONNECTED');
    if (!Number.isSafeInteger(tabId) || tabId < 0) refuse('INVALID_COMMAND');
    if (!this.#tabs.has(tabId) && this.#tabs.size >= 64) refuse('SHARE_LIMIT');
    const url = httpURL(origin);
    if (url.pathname !== '/' || url.search || url.hash) refuse('INVALID_COMMAND');
    this.adapter.invalidate?.(tabId);
    // Physical in-flight state survives local consent revocation/re-sharing.
    const lock = this.#locks.get(tabId) ?? { readers: 0, busy: false, fence: -1, holder: null };
    this.#locks.set(tabId, lock);
    const tab = { tab_id: tabId, origin: url.origin, consent_id: this.nonce(), document_revision: 0, lock };
    this.#tabs.set(tabId, tab);
    return this.#view(tab);
  }
  #view(tab) {
    return Object.freeze({ tab_id: tab.tab_id, origin: tab.origin, consent_id: tab.consent_id, document_revision: tab.document_revision,
      state: this.#uncertain.has(tab.tab_id) ? 'effect_unresolved' : tab.lock.busy ? 'busy' : 'shared' });
  }
  inventory() { return [...this.#tabs.values()].map(tab => this.#view(tab)); }
  invalidate(tabId) {
    const tab = this.#tabs.get(tabId);
    if (tab) { if (tab.document_revision === Number.MAX_SAFE_INTEGER) this.revoke(tabId); else tab.document_revision++; }
    this.adapter.invalidate?.(tabId);
  }
  revoke(tabId) { this.#tabs.delete(tabId); this.adapter.invalidate?.(tabId); }
  disconnect() { this.#connected = false; for (const id of [...this.#tabs.keys()]) this.revoke(id); }
  #basic(request) {
    if (!this.#connected) refuse('DISCONNECTED');
    if (request.connection_generation !== this.connectionGeneration) refuse('STALE_CONNECTION');
    const tab = this.#tabs.get(request.tab_id);
    if (!tab) refuse('TAB_NOT_SHARED');
    if (request.consent_id !== tab.consent_id) refuse('CONSENT_MISMATCH');
    if (this.now() >= request.expires_at_ms) refuse('EXPIRED');
    return tab;
  }
  #receipt(request, status, effect, extra = {}) {
    return { schema: RESULT_SCHEMA, request_id: request?.request_id ?? null, connection_generation: this.connectionGeneration, status, effect, ...extra };
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
      const read = READ_COMMANDS.includes(request.command);
      if (!read && this.#uncertain.has(request.tab_id)) refuse('EFFECT_UNRESOLVED');
      if (tab.document_revision !== request.document_revision) refuse('STALE_DOCUMENT');
      const lock = tab.lock;
      if (lock.busy || (!read && lock.readers > 0)) refuse('TAB_BUSY');
      if (read && lock.readers >= 4) refuse('READ_LIMIT');
      if (!read) {
        if (request.writer.fence < lock.fence) refuse('STALE_WRITER');
        if (request.writer.fence === lock.fence && request.writer.holder_ref !== lock.holder) refuse('WRITER_MISMATCH');
        if (request.command === 'navigate' && httpURL(request.args.url).origin !== tab.origin) refuse('ORIGIN_NOT_SHARED');
      }
      if (this.#requests.size >= this.maxRequestIds) refuse('REPLAY_GUARD_FULL');
      const entry = { digest, read, dispatched: false, result: null, tab_id: request.tab_id };
      this.#requests.set(request.request_id, entry);
      if (read) lock.readers++; else { lock.busy = true; lock.fence = request.writer.fence; lock.holder = request.writer.holder_ref; }
      const assertCurrent = () => {
        const current = this.#basic(request);
        if (current !== tab || current.document_revision !== request.document_revision) refuse('STALE_DOCUMENT');
        if (!read && (current.lock.fence !== request.writer.fence || current.lock.holder !== request.writer.holder_ref)) refuse('STALE_WRITER');
      };
      try {
        assertCurrent();
        const guard = { assertCurrent, origin: tab.origin, beforeEffect: () => { assertCurrent(); entry.dispatched = true; } };
        const output = read ? await this.adapter.read(request, guard) : await this.adapter.mutate(request, guard);
        if (!read && !entry.dispatched) {
          // A faulty native adapter may already have acted: absence of a guard
          // receipt cannot honestly prove NOT_APPLIED.
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
        if (!read && entry.dispatched) { this.#uncertain.add(request.tab_id); this.invalidate(request.tab_id); }
        const code = error instanceof BrowserLinkError ? error.code : 'ACTUATOR_FAILURE';
        entry.result = this.#receipt(request, 'refused', !read && entry.dispatched ? 'EFFECT_UNKNOWN' : 'NOT_APPLIED', { code });
      } finally { if (read) lock.readers--; else lock.busy = false; }
      return structuredClone(entry.result);
    } catch (error) {
      return this.#receipt(request, 'refused', 'NOT_APPLIED', { code: error instanceof BrowserLinkError ? error.code : 'INVALID_COMMAND' });
    }
  }
}
