// Test-only in-memory persistence; no durable session/resume claim.
import SessionPersistence, {SessionPersistenceRevision} from '@deepseek-ai/dsh-session-persistence'
import {SessionLogOffset} from '@deepseek-ai/dsh-session'
export default class EphemeralPersistence extends SessionPersistence {
  rows = /* @__PURE__ */ new Map();
  async create(header, options = {}) {
    options.signal?.throwIfAborted();
    if (this.rows.has(header.id)) throw new Error("N1_SESSION_ALREADY_EXISTS");
    const stored = {
      header: structuredClone(header),
      inheritedEventCount: options.inheritedEventCount ?? SessionLogOffset(0),
      events: [],
      revision: 0,
      writerOpen: true
    };
    this.rows.set(header.id, stored);
    return this.handle(stored, "write");
  }
  async open(id, access, options = {}) {
    options.signal?.throwIfAborted();
    const stored = this.rows.get(id);
    if (stored === void 0) throw new Error("N1_SESSION_NOT_FOUND");
    if (access === "write") throw new Error("N1_RESUME_DISABLED");
    return this.handle(stored, "read");
  }
  async flush() {
  }
  stat(id, options = {}) {
    options.signal?.throwIfAborted();
    const stored = this.rows.get(id);
    return Promise.resolve(stored === void 0 ? void 0 : this.snapshot(stored));
  }
  list(options = {}) {
    options.signal?.throwIfAborted();
    return Promise.resolve([...this.rows.values()].map((row) => this.snapshot(row)));
  }
  snapshot(stored) {
    return {
      header: structuredClone(stored.header),
      revision: SessionPersistenceRevision("n1:" + stored.header.id + ":" + stored.revision),
      eventCount: stored.events.length
    };
  }
  handle(stored, access) {
    let closed = false;
    let floor = 0;
    const ensure = () => {
      if (closed) throw new Error("N1_SESSION_HANDLE_CLOSED");
    };
    const handle = {
      id: stored.header.id,
      header: stored.header,
      inheritedEventCount: stored.inheritedEventCount,
      access,
      async read(offset = 0, length = Number.MAX_SAFE_INTEGER) {
        ensure();
        const start = Math.max(floor, offset);
        const events = stored.events.slice(start, start + length).map((event) => structuredClone(event));
        floor = Math.max(floor, start + events.length);
        return { eventState: "detached", events };
      },
      async append(events) {
        ensure();
        if (access !== "write" || !stored.writerOpen) throw new Error("N1_SESSION_READ_ONLY");
        for (const [index, event] of events.entries()) {
          if (event.seq !== stored.events.length + index) throw new Error("N1_SESSION_NONCONTIGUOUS");
        }
        stored.events.push(...events.map((event) => structuredClone(event)));
        stored.revision += 1;
      },
      async flush() {
        ensure();
        if (access !== "write") throw new Error("N1_SESSION_READ_ONLY");
      },
      async close() {
        if (closed) return;
        closed = true;
        if (access === "write") stored.writerOpen = false;
      },
      async [Symbol.asyncDispose]() {
        await handle.close();
      }
    };
    return handle;
  }
}
