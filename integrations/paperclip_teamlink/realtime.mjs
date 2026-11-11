import { createHash } from 'node:crypto';
import { NativeSubscription } from './native-watch.mjs';

const connection = c => createHash('sha256').update(JSON.stringify([c.environmentId, c.t3Home ?? null, c.t3Port ?? null])).digest('hex');
const reconnectable = new Set(['WATCH_CONNECTION_CLOSED', 'WATCH_HEARTBEAT_TIMEOUT', 'WATCH_READY_TIMEOUT', 'WATCH_CONNECTION_UNAVAILABLE', 'WATCH_STREAM_INTERRUPTED', 'WATCH_SESSION_ROTATE']);

// Ephemeral event coalescing only. Paperclip's SQL receipts and scheduled
// reconciler remain the sole durable effect/recovery owners.
export class Realtime {
  constructor(config, store, service, { watchFactory, concurrency = 2, maxBindings = 512,
    debounceMs = 30, minIntervalMs = 500, retryBaseMs = 250, retryMaxMs = 30000 } = {}) {
    this.config = config; this.store = store; this.service = service;
    this.watchFactory = watchFactory || ((ids, notify) => new NativeSubscription(config, ids, notify));
    this.concurrency = concurrency; this.maxBindings = maxBindings;
    this.debounceMs = debounceMs; this.minIntervalMs = minIntervalMs;
    this.retryBaseMs = retryBaseMs; this.retryMaxMs = retryMaxMs;
    this.bindings = new Map(); this.dirty = new Map(); this.inflight = new Map(); this.locks = new Map();
    this.lastAttempt = new Map(); this.watchers = []; this.closed = false; this.generation = 0;
    this.coverageComplete = false; this.observedBindings = 0; this.skippedBindings = 0;
    this.lastEventAt = null; this.lastReconciledAt = null;
    this.errors = { inventory: null, watch: null }; this.reconcileErrors = new Map();
    this.paused = false; this.needsReconnect = false;
    this.lastDispatchLagMs = null; this.lastReconcileDurationMs = null;
    this.reconnects = 0; this.retryCount = 0; this.signature = null;
  }
  async exclusive(issueId, work) {
    const previous = this.locks.get(issueId) || Promise.resolve();
    let release;
    const tail = new Promise(resolve => { release = resolve; });
    this.locks.set(issueId, tail);
    await previous;
    try { return await work(); }
    finally {
      release(); if (this.locks.get(issueId) === tail) this.locks.delete(issueId);
      this.schedule();
    }
  }
  async refresh() {
    if (this.closed) return;
    if (this.refreshing) return this.refreshing;
    const task = this.refreshNow(); this.refreshing = task;
    try { await task; this.errors.inventory = null; }
    catch (error) { this.errors.inventory = 'REALTIME_INVENTORY_UNAVAILABLE'; throw error; }
    finally { if (this.refreshing === task) this.refreshing = null; }
  }
  async refreshNow() {
    const links = new Map(); let cursor = null, seen = 0, skipped = 0;
    do {
      const page = await this.store.bindingPage(this.config.companyId, cursor, Math.min(128, this.maxBindings + 1 - seen));
      if (this.closed) return;
      for (const b of page.bindings) {
        seen++;
        if (seen > this.maxBindings) break;
        if (b.companyId !== this.config.companyId || b.environmentId !== this.config.environmentId ||
            b.connectionId !== connection(this.config) || !this.config.projectIds.includes(b.projectId)) { skipped++; continue; }
        links.set(b.issueId, b);
      }
      if (page.nextCursor === cursor && page.nextCursor !== null) throw new Error('BINDING_CURSOR_STALLED');
      cursor = page.nextCursor;
    } while (cursor !== null && seen <= this.maxBindings);
    this.coverageComplete = cursor === null && seen <= this.maxBindings && skipped === 0;
    this.observedBindings = seen; this.skippedBindings = skipped;
    const signature = JSON.stringify([...links.values()].map(b => [b.issueId, b.bindingId, b.threadId]));
    this.bindings = links;
    for (const [issue, queued] of this.dirty) if (links.get(issue)?.bindingId !== queued.bindingId) this.dirty.delete(issue);
    for (const issue of this.lastAttempt.keys()) if (!links.has(issue)) this.lastAttempt.delete(issue);
    for (const issue of this.reconcileErrors.keys()) if (!links.has(issue)) this.reconcileErrors.delete(issue);
    if (signature !== this.signature) {
      this.signature = signature;
      clearTimeout(this.retryTimer); this.retryTimer = null;
      await this.connect();
    }
  }
  async connect() {
    const generation = ++this.generation;
    const old = this.watchers; this.watchers = [];
    await Promise.allSettled(old.map(w => w.stop()));
    if (this.closed || this.paused || generation !== this.generation) return;
    const ids = [...new Set([...this.bindings.values()].map(b => b.threadId))].sort();
    for (let offset = 0; offset < ids.length; offset += 128) {
      const group = ids.slice(offset, offset + 128);
      let stableSince = null;
      try {
        const watcher = this.watchFactory(group, notice => {
          if (this.closed || generation !== this.generation) return;
          if (notice.type === 'closed' || notice.type === 'unavailable') {
            this.errors.watch = notice.code;
            // Only connection/liveness failures reconnect. Scope, authorization,
            // protocol and configuration refusals remain held for a real change.
            if (reconnectable.has(notice.code)) this.retry();
            return;
          }
          if (notice.type === 'ready') {
            stableSince ??= Date.now();
            if (this.watchers.length && this.watchers.every(w => { const h = w.health(); return !h.error && h.readyThreads === h.requestedThreads; })) this.errors.watch = null;
          }
          if (stableSince !== null && Date.now() - stableSince >= 30000) this.retryCount = 0;
          if (notice.type === 'changed' || notice.type === 'ready') {
            this.lastEventAt = new Date().toISOString();
            for (const b of this.bindings.values()) {
              if ((notice.threadId ? b.threadId === notice.threadId : group.includes(b.threadId))) this.nudge(b.issueId);
            }
          }
        });
        this.watchers.push(watcher);
      } catch { this.errors.watch = 'WATCH_START_UNAVAILABLE'; }
    }
    // Catch-up follows subscription establishment; the ready notice schedules
    // another pass if an event raced this first read. No event cursor is saved.
    for (const issue of this.bindings.keys()) this.nudge(issue);
  }
  retry() {
    if (this.closed || this.retryTimer) return;
    if (this.paused) { this.needsReconnect = true; return; }
    const delay = Math.min(this.retryMaxMs, this.retryBaseMs * 2 ** Math.min(10, this.retryCount++));
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null; if (this.closed) return;
      this.reconnects++;
      const task = this.connect().catch(() => { this.errors.watch = 'WATCH_RECONNECT_UNAVAILABLE'; this.retry(); });
      this.connecting = task;
      task.finally(() => { if (this.connecting === task) this.connecting = null; });
    }, delay);
    this.retryTimer.unref?.();
  }
  nudge(issueId) {
    const b = this.bindings.get(issueId);
    if (this.closed || !b) return;
    if (!this.dirty.has(issueId)) this.dirty.set(issueId, { bindingId: b.bindingId, queuedAt: Date.now() });
    this.schedule();
  }
  schedule(delay = this.debounceMs) {
    if (this.closed || this.paused || this.pumpTimer || !this.dirty.size) return;
    this.pumpTimer = setTimeout(() => { this.pumpTimer = null; this.pump(); }, delay);
    this.pumpTimer.unref?.();
  }
  pump() {
    if (this.closed || this.paused) return;
    let nextDelay = Infinity;
    for (const [issue, entry] of this.dirty) {
      if (this.inflight.size >= this.concurrency) break;
      if (this.inflight.has(issue) || this.locks.has(issue)) continue;
      const delay = this.minIntervalMs - (Date.now() - (this.lastAttempt.get(issue) || 0));
      if (delay > 0) { nextDelay = Math.min(nextDelay, delay); continue; }
      this.dirty.delete(issue); this.lastAttempt.set(issue, Date.now());
      const isCurrent = () => !this.closed && this.bindings.get(issue)?.bindingId === entry.bindingId;
      const task = this.exclusive(issue, async () => {
        if (!isCurrent()) return;
        const start = Date.now(); this.lastDispatchLagMs = start - entry.queuedAt;
        try {
          const result = await this.service.reconcileBinding(issue, entry.bindingId, { isCurrent });
          if (result?.ok === false) this.reconcileErrors.set(issue, /^[A-Z0-9_]+$/.test(result.error) ? result.error : 'REALTIME_RECONCILE_UNAVAILABLE');
          else { this.reconcileErrors.delete(issue); this.lastReconciledAt = new Date().toISOString(); }
          // Proven cursor/page progress can continue independently of a held
          // receipt's error. Keep that error visible until its own recovery.
          if (result?.more && isCurrent()) this.nudge(issue);
        } catch { this.reconcileErrors.set(issue, 'REALTIME_RECONCILE_UNAVAILABLE'); }
        finally { this.lastReconcileDurationMs = Date.now() - start; }
      }).finally(() => { this.inflight.delete(issue); this.schedule(); });
      this.inflight.set(issue, task);
    }
    if (Number.isFinite(nextDelay)) this.schedule(Math.max(this.debounceMs, nextDelay));
  }
  health() {
    const listeners = this.watchers.map(w => w.health());
    return { enabled: !this.closed, coveredBindings: this.bindings.size, observedBindings: this.observedBindings,
      coverageComplete: this.coverageComplete, skippedBindings: this.skippedBindings, bindingLimit: this.maxBindings,
      readyThreads: listeners.reduce((n, x) => n + x.readyThreads, 0),
      requestedThreads: listeners.reduce((n, x) => n + x.requestedThreads, 0),
      connected: this.bindings.size === 0 || listeners.length > 0 && listeners.every(x => !x.error && x.readyThreads === x.requestedThreads),
      queuedBindings: this.dirty.size, activeBindings: this.inflight.size, reconnects: this.reconnects,
      lastEventAt: this.lastEventAt, lastReconciledAt: this.lastReconciledAt,
      lastDispatchLagMs: this.lastDispatchLagMs, lastReconcileDurationMs: this.lastReconcileDurationMs,
      error: !this.coverageComplete ? 'REALTIME_COVERAGE_LIMIT_OR_SCOPE' : this.errors.inventory || this.errors.watch || (this.reconcileErrors.size ? 'REALTIME_RECONCILE_UNAVAILABLE' : null),
      errors: { ...this.errors, observations: { count: this.reconcileErrors.size, examples: [...this.reconcileErrors].slice(0, 5).map(([issueId, code]) => ({ issueId, code })) } },
      recovery: 'native_scheduled_reconcile', deliveryIsConsumption: false };
  }
  pause() {
    this.paused = true; clearTimeout(this.pumpTimer); this.pumpTimer = null;
    if (this.retryTimer) { clearTimeout(this.retryTimer); this.retryTimer = null; this.needsReconnect = true; }
  }
  resume() {
    if (this.closed) return;
    this.paused = false; this.schedule();
    if (this.needsReconnect) { this.needsReconnect = false; this.retry(); }
  }
  async stop() {
    if (!this.closed) {
      this.closed = true; ++this.generation;
      clearTimeout(this.pumpTimer); clearTimeout(this.retryTimer); this.dirty.clear();
    }
    await Promise.allSettled([this.refreshing, this.connecting, ...this.watchers.map(w => w.stop()), ...this.inflight.values()]);
    this.watchers = [];
  }
}
