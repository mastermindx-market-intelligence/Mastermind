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
function view(extra: Record<string, unknown> = {}) { return {
  schema: "mastermind.hermes_native_view.v1", state: "READY", authGeneration: 7,
  capabilities: ["native_chat", "native_history", "admission_recovery"],
  delegation: "NOT_ENABLED", retryAllowed: false,
  runtime: { protocol: 1, instanceId: "native", authorityEpoch: 1, version: "0.23.0",
    sourceRevision: "b".repeat(40), localScope: scope }, ...extra }; }
function receipt(status = "terminal", extra: Record<string, unknown> = {}) {
  return view({ state: "ADMITTED", operation: "recover", session: session(), receipt: {
    id: "original-admission", sessionId: original.sessionId, status, sequence: 1,
    outcome: status === "terminal" ? "completed" : null, executionGeneration: 1, ...extra } });
}
type Wire = { operation: string; sessionId?: string; requestId?: string; text?: string };
function harness(factory = new IDBFactory(),
    handle: (request: Wire, args: Record<string, unknown>) => Promise<unknown> = async () => view(),
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
      view({ session: session() }), view({ state: "EFFECT_UNKNOWN", operation: "recover", code: "NATIVE_RECOVERY_UNRESOLVED" }),
      view({ state: "REFUSED" }), view({ state: "NOT_SENT" }), view({ state: "UNAVAILABLE" })]) {
      h.invoke.mockResolvedValueOnce(answer);
      const result = await h.port.request({ operation: "recover" });
      expect(result.pendingOperation).toEqual(original);
      expect(await h.store.read(scope)).toEqual(nativePendingPointer(original));
    }
    h.invoke.mockResolvedValueOnce(view({ session: session() }));
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
      ? view({ state: "EFFECT_UNKNOWN", operation: "send" }) : view());
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
      h.invoke.mockRejectedValueOnce(new Error(code));
      await expect(h.port.request(send)).rejects.toThrow(code);
      expect(await h.store.read(scope)).toBeNull();
    }
    const h = harness();
    await h.port.request({ operation: "status" });
    h.invoke.mockResolvedValueOnce(view({ state: "NOT_SENT" }));
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
      ? view({ state: "OPENED", operation: "recover", session: session() }) : view());
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
});
