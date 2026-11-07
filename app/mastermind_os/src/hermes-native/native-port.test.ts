// @vitest-environment node
import { IDBFactory } from "fake-indexeddb";
import { describe, expect, it, vi } from "vitest";
import { createIndexedDbPendingPointerStore, PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME,
  type DurablePendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { createNativeHermesPort } from "./native-port";
import { nativePendingPointer, readNativePending } from "./pending-pointer";

const scope = "e".repeat(64);
const original = { kind: "send" as const, sessionId: "original-session", requestId: "a".repeat(32) };
const send = { operation: "send" as const, sessionId: original.sessionId, requestId: original.requestId,
  text: "Private original\n 中文\t" };
function session() { return { id: original.sessionId, storedId: original.sessionId, title: "Original",
  requestedModel: "configured", canSend: true, toolAccess: "NONE", running: false, executionGeneration: 1,
  messageCount: 0, messages: [], historyTruncated: false, pending: [], promptsPending: false }; }
function view(extra: Record<string, unknown> = {}) {
  const operation = extra.operation ?? "status";
  const binding = operation === "send" || operation === "recover"
    ? { requestId: original.requestId, requestSessionId: original.sessionId } : {};
  return {
  schema: "mastermind.hermes_native_view.v1", state: "READY", operation: "status", authGeneration: 7,
  capabilities: ["native_chat", "native_history", "admission_recovery"],
  delegation: "NOT_ENABLED", retryAllowed: false,
  runtime: { protocol: 1, instanceId: "native", authorityEpoch: 1, version: "0.23.0",
    sourceRevision: "b".repeat(40), localScope: scope }, ...binding, ...extra }; }
function receipt(status = "terminal", extra: Record<string, unknown> = {}) {
  return view({ state: "ADMITTED", operation: "recover", session: session(), receipt: {
    id: "original-admission", sessionId: original.sessionId, status, sequence: 1,
    outcome: status === "terminal" ? "completed" : null, executionGeneration: 1, ...extra } });
}
type Wire = { operation: string; sessionId?: string; requestId?: string; text?: string };
function noSend(request: Wire, code: string, extra: Record<string, unknown> = {}) {
  return { schema: "mastermind.hermes_native_no_send.v1", operation: request.operation,
    requestId: request.requestId, expectedAuthGeneration: 7, code,
    ...(request.operation === "send" ? { sessionId: request.sessionId } : {}), ...extra };
}
function harness(factory = new IDBFactory(),
    handle: (request: Wire, args: Record<string, unknown>) => Promise<unknown> = async request =>
      view({ operation: request.operation.startsWith("recover_") ? "recover" : request.operation,
        requestId: request.requestId, requestSessionId: request.requestId ? request.sessionId : undefined }),
    storeOverride?: DurablePendingPointerStore) {
  const store = storeOverride ?? createIndexedDbPendingPointerStore(factory);
  const invoke = vi.fn(async (_command: string, args: Record<string, unknown>) => handle(args.request as Wire, args));
  const port = createNativeHermesPort({ invoke, available: () => true, store });
  return { port, store, invoke, factory };
}
async function rawRecord(factory: IDBFactory, replacement?: unknown): Promise<unknown> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const open = factory.open(PENDING_POINTER_DB_NAME, 1);
    open.onsuccess = () => resolve(open.result); open.onerror = () => reject(open.error);
  });
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(PENDING_POINTER_STORE_NAME, replacement === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore(PENDING_POINTER_STORE_NAME);
      const req = replacement === undefined ? store.get(scope) : store.put(replacement, scope);
      let result: unknown;
      req.onsuccess = () => { result = req.result; };
      tx.oncomplete = () => resolve(result); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

describe("native Hermes durable original-request recovery", () => {
  it("commits only the closed lookup before dispatch and restores it in a fresh port/store", async () => {
    const factory = new IDBFactory();
    const h = harness(factory, async request => {
      if (request.operation === "status") return view();
      expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(nativePendingPointer(original));
      expect(await rawRecord(factory)).toEqual({ v: 14, ...nativePendingPointer(original) });
      throw new Error("reply lost after native dispatch");
    });
    expect(h.invoke).not.toHaveBeenCalled();
    await h.port.request({ operation: "status" });
    await expect(h.port.request(send)).rejects.toThrow("reply lost");
    const reopened = harness(factory, async request => request.operation === "recover_send" ? receipt() : view());
    const status = await reopened.port.request({ operation: "status" });
    expect(status.pendingOperation).toEqual(original);
    expect(reopened.invoke).toHaveBeenCalledTimes(1); // reopening does not submit or even recover automatically
    expect((await reopened.port.request({ ...send, requestId: "c".repeat(32) })).state).toBe("EFFECT_UNKNOWN");
    expect(reopened.invoke).toHaveBeenCalledTimes(1);
    const recovered = await reopened.port.request({ operation: "recover" });
    expect(reopened.invoke.mock.calls[1]).toEqual(["hermes_native", {
      request: { operation: "recover_send", sessionId: original.sessionId, requestId: original.requestId },
      expectedAuthGeneration: 7,
    }]);
    expect(recovered.receipt?.status).toBe("terminal");
    expect(recovered.pendingOperation).toBeNull();
    expect(await reopened.store.read(scope)).toBeNull();
    expect(h.invoke.mock.calls.filter(([, args]) => (args.request as Wire).operation === "send")).toHaveLength(1);
  });

  it("holds queued, started, unknown, empty history and missing or pruned recovery", async () => {
    const h = harness();
    await h.store.reserve(scope, nativePendingPointer(original));
    await h.port.request({ operation: "status" });
    for (const answer of [receipt("queued"), receipt("started"), receipt("unknown"),
      view({ operation: "recover", session: session() }), view({ state: "EFFECT_UNKNOWN", operation: "recover", code: "NATIVE_RECOVERY_UNRESOLVED" }),
      view({ operation: "recover", state: "REFUSED" }), view({ operation: "recover", state: "NOT_SENT" }), view({ operation: "recover", state: "UNAVAILABLE" })]) {
      h.invoke.mockResolvedValueOnce(answer);
      const result = await h.port.request({ operation: "recover" });
      expect(result.pendingOperation).toEqual(original);
      expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    }
    h.invoke.mockResolvedValueOnce(view({ operation: "read", session: session() }));
    await h.port.request({ operation: "read", sessionId: original.sessionId });
    expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
  });

  it("keeps the pointer when a reply is withheld on sign-out and recovers under fresh authentication", async () => {
    const h = harness();
    await h.port.request({ operation: "status" });
    h.invoke.mockRejectedValueOnce(new Error("AUTHENTICATION_CHANGED"));
    await expect(h.port.request(send)).rejects.toThrow("AUTHENTICATION_CHANGED");
    expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    await expect(h.port.request({ operation: "recover" })).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    h.invoke.mockResolvedValueOnce(view({ authGeneration: 8 }));
    expect((await h.port.request({ operation: "status" })).pendingOperation).toEqual(original);
    h.invoke.mockResolvedValueOnce({ ...receipt(), authGeneration: 8 });
    await h.port.request({ operation: "recover" });
    expect(h.invoke.mock.calls.at(-1)?.[1]).toEqual({
      request: { operation: "recover_send", requestId: original.requestId, sessionId: original.sessionId },
      expectedAuthGeneration: 8,
    });
    expect(await h.store.read(scope)).toBeNull();
  });

  it("withholds a stale generation or changed native attachment without clearing", async () => {
    for (const answer of [view({ authGeneration: 8 }),
      view({ runtime: { ...view().runtime, localScope: "f".repeat(64) } })]) {
      const h = harness();
      await h.port.request({ operation: "status" });
      h.invoke.mockResolvedValueOnce(answer);
      await expect(h.port.request(send)).rejects.toThrow(/AUTHENTICATION_CHANGED|NATIVE_IDENTITY_CHANGED/);
      expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    }
  });

  it("reserves atomically across two independently mounted ports", async () => {
    const factory = new IDBFactory();
    const owner = vi.fn(async (request: Wire) => request.operation === "send"
      ? view({ state: "EFFECT_UNKNOWN", operation: "send", requestId: request.requestId }) : view());
    const a = harness(factory, owner), b = harness(factory, owner);
    await Promise.all([a.port.request({ operation: "status" }), b.port.request({ operation: "status" })]);
    const results = await Promise.all([a.port.request(send), b.port.request({ ...send, requestId: "b".repeat(32) })]);
    expect(results.every(result => result.state === "EFFECT_UNKNOWN")).toBe(true);
    expect(owner.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(1);
    const held = readNativePending((await a.store.read(scope))!);
    expect(results.map(result => result.pendingOperation)).toEqual([held, held]);
  });

  it("never dispatches without a durable reservation or a qualified local scope", async () => {
    const factory = new IDBFactory();
    const base = createIndexedDbPendingPointerStore(factory);
    const h = harness(factory, async () => view(), { ...base,
      reserve: async () => { throw new Error("PENDING_POINTER_TRANSACTION_FAILED"); } });
    await h.port.request({ operation: "status" });
    await expect(h.port.request(send)).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    expect(h.invoke).toHaveBeenCalledTimes(1);
    const oldHost = harness(factory, async () => view({ runtime: { ...view().runtime, localScope: undefined } }));
    await expect(oldHost.port.request({ operation: "status" })).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    await expect(oldHost.port.request(send)).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    expect(oldHost.invoke).toHaveBeenCalledTimes(1);
  });

  it("does not clear a crossed or malformed terminal response", async () => {
    for (const answer of [receipt("terminal", { sessionId: "another-session" }),
      receipt("terminal", { sequence: 0 }), view({ state: "ADMITTED" }),
      { ...receipt(), operation: "send" }, { ...receipt(), operation: undefined },
      { ...receipt(), requestId: "b".repeat(32) }, { ...receipt(), requestId: undefined },
      { ...receipt(), requestSessionId: "other" },
      { ...receipt(), session: { ...session(), id: "other", storedId: "other" } }]) {
      const h = harness();
      await h.store.reserve(scope, nativePendingPointer(original));
      await h.port.request({ operation: "status" });
      h.invoke.mockResolvedValueOnce(answer);
      await expect(h.port.request({ operation: "recover" })).rejects.toThrow("NATIVE_RESPONSE_INVALID");
      expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    }
  });

  it("retains uncertainty if clearing fails, and never erases a newer record", async () => {
    const factory = new IDBFactory(), base = createIndexedDbPendingPointerStore(factory);
    const h = harness(factory, async request => request.operation === "recover_send" ? receipt() : view(),
      { ...base, clearIfEqual: async () => { throw new Error("PENDING_POINTER_TRANSACTION_FAILED"); } });
    await base.reserve(scope, nativePendingPointer(original));
    await h.port.request({ operation: "status" });
    await expect(h.port.request({ operation: "recover" })).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    expect(await base.read(scope)).toEqual(nativePendingPointer(original));
    await base.clearIfEqual(scope, nativePendingPointer(original));
    const newer = nativePendingPointer({ ...original, requestId: "c".repeat(32) });
    await base.reserve(scope, newer);
    expect(await base.clearIfEqual(scope, nativePendingPointer(original))).toBe(false);
    expect(await base.read(scope)).toEqual(newer);
  });

  it("clears only a positively classified before-spawn failure for this exact reservation", async () => {
    for (const code of ["NATIVE_BUSY", "NATIVE_CLIENT_NOT_STARTED", "REQUEST_INVALID"]) {
      const h = harness();
      await h.port.request({ operation: "status" });
      h.invoke.mockRejectedValueOnce(noSend(send, code));
      await expect(h.port.request(send)).rejects.toThrow(code);
      expect(await h.store.read(scope)).toBeNull();
    }
    const h = harness();
    await h.port.request({ operation: "status" });
    h.invoke.mockResolvedValueOnce(view({ operation: "send", state: "NOT_SENT" }));
    expect((await h.port.request(send)).pendingOperation).toBeNull();
  });

  it("recovers an uncertain create with its original identity without another create", async () => {
    const factory = new IDBFactory(), h = harness(factory);
    await h.port.request({ operation: "status" });
    h.invoke.mockRejectedValueOnce(new Error("lost create response"));
    await expect(h.port.request({ operation: "create", role: "secretary", requestId: "d".repeat(32) })).rejects.toThrow();
    expect(await rawRecord(factory)).toEqual({ v: 13,
      ...nativePendingPointer({ kind: "create", requestId: "d".repeat(32) }) });
    const reopened = harness(factory, async request => request.operation === "recover_create"
      ? view({ state: "OPENED", operation: "recover", requestId: "d".repeat(32), requestSessionId: undefined, session: session() }) : view());
    await reopened.port.request({ operation: "status" });
    expect((await reopened.port.request({ operation: "recover" })).pendingOperation).toBeNull();
    expect(reopened.invoke.mock.calls[1]?.[1].request).toEqual({ operation: "recover_create", requestId: "d".repeat(32) });
    expect(reopened.invoke.mock.calls.some(([, args]) => (args.request as Wire).operation === "create")).toBe(false);
  });

  it("keeps malformed or unknown persisted records fenced and rejects payload-bearing pointers", async () => {
    const h = harness();
    await h.store.read(scope);
    await expect(h.store.reserve(scope, { ...nativePendingPointer(original), text: "never persist" } as never))
      .rejects.toThrow("PENDING_POINTER_INVALID_POINTER");
    for (const bad of [{ v: 99, ...nativePendingPointer(original) },
      { v: 14, ...nativePendingPointer(original), text: "private" },
      { v: 14, ...nativePendingPointer(original), targetKey: "../other" }]) {
      await rawRecord(h.factory, bad);
      await expect(h.port.request({ operation: "status" })).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
      await expect(h.port.request(send)).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
      expect(await rawRecord(h.factory)).toEqual(bad);
    }
    expect(h.invoke.mock.calls.every(([, args]) => (args.request as Wire).operation === "status")).toBe(true);
    expect(() => nativePendingPointer({ ...original, requestId: original.requestId + "\n" })).toThrow("REQUEST_INVALID");
  });

  it("clears a proven before-dispatch auth rejection and requires fresh sign-in before another request", async () => {
    for (const request of [send, { operation: "create" as const, role: "secretary" as const, requestId: "d".repeat(32) }]) {
      const h = harness();
      await h.port.request({ operation: "status" });
      h.invoke.mockRejectedValueOnce(noSend(request, "NATIVE_AUTH_NOT_DISPATCHED"));
      await expect(h.port.request(request)).rejects.toThrow("NATIVE_AUTH_NOT_DISPATCHED");
      expect(await h.store.read(scope)).toBeNull();
      await expect(h.port.request(request)).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
      expect(h.invoke).toHaveBeenCalledTimes(2);
      h.invoke.mockResolvedValueOnce(view({ authGeneration: 8 }));
      expect((await h.port.request({ operation: "status" })).pendingOperation).toBeNull();
      h.invoke.mockResolvedValueOnce(view({ operation: request.operation, state: "NOT_SENT", authGeneration: 8,
        requestId: request.requestId, requestSessionId: "sessionId" in request ? request.sessionId : undefined }));
      expect((await h.port.request(request)).pendingOperation).toBeNull();
      expect(h.invoke).toHaveBeenCalledTimes(4);
    }
  });

  it("does not settle a reservation from a crossed or missing public operation", async () => {
    for (const operation of ["read", undefined]) {
      for (const state of ["REFUSED", "NOT_SENT", "OPENED"]) {
        const h = harness();
        const create = { operation: "create" as const, role: "secretary" as const, requestId: "d".repeat(32) };
        await h.port.request({ operation: "status" });
        h.invoke.mockResolvedValueOnce(view({ operation, state, ...(state === "OPENED" ? { session: session() } : {}) }));
        await expect(h.port.request(create)).rejects.toThrow("NATIVE_RESPONSE_INVALID");
        expect(await h.store.read(scope)).toEqual(nativePendingPointer({ kind: "create", requestId: create.requestId }));
      }
    }
  });

  it("keeps generic or crossed no-send errors held across reopening", async () => {
    const valid = noSend(send, "NATIVE_AUTH_NOT_DISPATCHED");
    for (const error of [new Error("NATIVE_AUTH_NOT_DISPATCHED"), new Error("NATIVE_BUSY"),
      { ...valid, requestId: "b".repeat(32) }, { ...valid, operation: "create" },
      { ...valid, sessionId: "other" }, { ...valid, expectedAuthGeneration: 8 },
      { ...valid, requestId: undefined }, { ...valid, private: "extra" }]) {
      const h = harness(); await h.port.request({ operation: "status" });
      h.invoke.mockRejectedValueOnce(error);
      await expect(h.port.request(send)).rejects.toBeDefined();
      const reopened = harness(h.factory);
      expect((await reopened.port.request({ operation: "status" })).pendingOperation).toEqual(original);
      expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    }
  });

  it("does not clear a direct refusal or terminal receipt for another original request", async () => {
    for (const answer of [view({ operation: "send", state: "NOT_SENT", requestId: "b".repeat(32) }),
      view({ operation: "send", state: "REFUSED", requestId: undefined }),
      { ...receipt(), operation: "send", requestId: "b".repeat(32) }]) {
      const h = harness(); await h.port.request({ operation: "status" });
      h.invoke.mockResolvedValueOnce(answer);
      await expect(h.port.request(send)).rejects.toThrow("NATIVE_RESPONSE_INVALID");
      expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    }
  });

  it("freezes the original arguments before awaiting durable reservation", async () => {
    const factory = new IDBFactory(), base = createIndexedDbPendingPointerStore(factory);
    let release!: () => void;
    const waiting = new Promise<void>(resolve => { release = resolve; });
    const h = harness(factory, async request => request.operation === "send"
      ? view({ operation: "send", state: "NOT_SENT" }) : view(), {
      ...base, reserve: async (key, pointer) => { await waiting; return base.reserve(key, pointer); },
    });
    await h.port.request({ operation: "status" });
    const input = { ...send }; const result = h.port.request(input);
    input.requestId = "b".repeat(32); input.text = "changed after click";
    release(); await result;
    expect(h.invoke.mock.calls.at(-1)?.[1].request).toEqual(send);
  });

  it("cannot qualify an attachment from a crossed status response", async () => {
    const h = harness(undefined, async () => view({ operation: "list" }));
    await expect(h.port.request({ operation: "status" })).rejects.toThrow("NATIVE_RESPONSE_INVALID");
    await expect(h.port.request(send)).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    expect(h.invoke).toHaveBeenCalledTimes(1);
  });
});


describe("native Hermes Stop of the reserved original admission", () => {
  const stop = { operation: "stop" as const, sessionId: original.sessionId, requestId: original.requestId };
  const stopped = { ...original, stopReserved: true as const };
  const stopView = (status = "terminal", extra: Record<string, unknown> = {}) =>
    ({ ...receipt(status), operation: "stop", ...extra });
  async function held(h: ReturnType<typeof harness>) {
    await h.port.request({ operation: "status" });
    await h.store.reserve(scope, nativePendingPointer(original));
  }
  it("cannot cancel a replacement request in the same session from a stale Stop button", async () => {
    const h = harness(); await held(h);
    const first = nativePendingPointer(original);
    await h.store.clearIfEqual(scope, first);
    const replacement = { ...original, requestId: "b".repeat(32) };
    await h.store.reserve(scope, nativePendingPointer(replacement));
    const result = await h.port.request(stop);
    expect(result).toMatchObject({ state: "REFUSED", code: "NATIVE_STOP_TARGET_CHANGED", pendingOperation: replacement });
    expect(await h.store.read(scope)).toEqual(nativePendingPointer(replacement));
    expect(h.invoke.mock.calls.some(([, args]) => (args.request as { operation: string }).operation === "stop_send")).toBe(false);
  });
  it("durably fences the exact original before the single cancel and settles only its terminal receipt", async () => {
    const h = harness(new IDBFactory(), async request => {
      if (request.operation === "status") return view();
      expect(request).toEqual({ operation: "stop_send", sessionId: original.sessionId, requestId: original.requestId });
      expect(await rawRecord(h.factory)).toEqual({ v: 15, ...nativePendingPointer(stopped) });
      return stopView();
    });
    await held(h);
    const result = await h.port.request(stop);
    expect(result.receipt?.status).toBe("terminal");
    expect(result.pendingOperation).toBeNull();
    expect(await h.store.read(scope)).toBeNull();
    expect(h.invoke.mock.calls[1][1].expectedAuthGeneration).toBe(7);
  });
  it("has no cancellation target without an existing original send", async () => {
    const h = harness(); await h.port.request({ operation: "status" });
    expect((await h.port.request(stop)).state).toBe("REFUSED");
    await h.store.reserve(scope, nativePendingPointer({ kind: "create", requestId: original.requestId }));
    expect((await h.port.request(stop)).state).toBe("REFUSED");
    expect(h.invoke).toHaveBeenCalledTimes(1);
  });
  it("retains a nonterminal Stop as the same original and never dispatches it twice", async () => {
    const h = harness(new IDBFactory(), async request => request.operation === "status" ? view() : stopView("started"));
    await held(h);
    expect((await h.port.request(stop)).pendingOperation).toEqual(stopped);
    expect((await h.port.request(stop)).state).toBe("EFFECT_UNKNOWN");
    expect(h.invoke.mock.calls.filter(([, args]) => (args.request as Wire).operation === "stop_send")).toHaveLength(1);
    expect((await h.port.request(send)).pendingOperation).toEqual(stopped);
  });
  it("reopens an interrupted Stop for original receipt recovery without a second cancel or send", async () => {
    const factory = new IDBFactory();
    const first = harness(factory, async request => {
      if (request.operation === "status") return view();
      throw new Error("response lost after cancel");
    });
    await held(first); await expect(first.port.request(stop)).rejects.toThrow("response lost");
    const reopened = harness(factory, async request => request.operation === "recover_send" ? receipt() : view());
    expect((await reopened.port.request({ operation: "status" })).pendingOperation).toEqual(stopped);
    expect((await reopened.port.request(stop)).state).toBe("EFFECT_UNKNOWN");
    expect(reopened.invoke).toHaveBeenCalledTimes(1);
    expect((await reopened.port.request({ operation: "recover" })).pendingOperation).toBeNull();
    expect(reopened.invoke.mock.calls.map(([, args]) => args.request)).toEqual([
      { operation: "status" }, { operation: "recover_send", sessionId: original.sessionId, requestId: original.requestId }]);
  });
  it("allows only one dispatch when two independent ports contend for the original", async () => {
    const factory = new IDBFactory();
    const handle = vi.fn(async (request: Wire) => request.operation === "status" ? view() : stopView("started"));
    const first = harness(factory, handle), second = harness(factory, handle);
    await held(first); await second.port.request({ operation: "status" });
    const results = await Promise.all([first.port.request(stop), second.port.request(stop)]);
    expect(handle.mock.calls.filter(([request]) => request.operation === "stop_send")).toHaveLength(1);
    expect(results.every(result => result.pendingOperation?.kind === "send" && result.pendingOperation.stopReserved)).toBe(true);
    expect(await first.store.read(scope)).toEqual(nativePendingPointer(stopped));
  });
  it("does not erase a newer Stop fence when an older terminal recovery finishes", async () => {
    const factory = new IDBFactory(); let release!: (value: unknown) => void;
    const recovery = harness(factory, async request => request.operation === "status" ? view()
      : new Promise(resolve => { release = resolve; }));
    await held(recovery);
    const pending = recovery.port.request({ operation: "recover" });
    await vi.waitFor(() => expect(release).toBeTypeOf("function"));
    const stopper = harness(factory, async request => request.operation === "status" ? view() : stopView("started"));
    await stopper.port.request({ operation: "status" }); await stopper.port.request(stop);
    release(receipt());
    expect((await pending).pendingOperation).toEqual(stopped);
    expect(await recovery.store.read(scope)).toEqual(nativePendingPointer(stopped));
  });
  it.each([
    { authGeneration: 8 }, { requestId: "b".repeat(32) }, { requestSessionId: "other-session" },
    { receipt: { ...receipt().receipt, sessionId: "other-session" } },
  ])("keeps the fence when response identity crosses: %j", async change => {
    const h = harness(new IDBFactory(), async request => request.operation === "status" ? view() : stopView("terminal", change));
    await held(h); await expect(h.port.request(stop)).rejects.toThrow();
    expect(await h.store.read(scope)).toEqual(nativePendingPointer(stopped));
  });
  it("requires a durable Stop reservation method and never substitutes a new store", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const h = harness(factory, undefined, { read: store.read, reserve: store.reserve, clearIfEqual: store.clearIfEqual });
    await held(h);
    expect((await h.port.request(stop)).state).toBe("EFFECT_UNKNOWN");
    expect(h.invoke).toHaveBeenCalledTimes(1);
    expect(await store.read(scope)).toEqual(nativePendingPointer(original));
  });
  it("never dispatches after an unknown reservation failure and retains any committed marker", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const h = harness(factory, undefined, { ...store, async reserveNativeStop(...args) {
      await store.reserveNativeStop!(...args); throw new Error("PENDING_POINTER_TRANSACTION_FAILED");
    } });
    await held(h); await expect(h.port.request(stop)).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
    expect(h.invoke).toHaveBeenCalledTimes(1);
    expect(await store.read(scope)).toEqual(nativePendingPointer(stopped));
  });
  it("retains the original when cancellation is refused or definitely not dispatched", async () => {
    for (const state of ["REFUSED", "NOT_SENT", "EFFECT_UNKNOWN"]) {
      const h = harness(new IDBFactory(), async request => request.operation === "status" ? view()
        : view({ operation: "stop", state, requestId: original.requestId, requestSessionId: original.sessionId, code: "NATIVE_NOT_SENT" }));
      await held(h); expect((await h.port.request(stop)).pendingOperation).toEqual(stopped);
    }
  });
});
