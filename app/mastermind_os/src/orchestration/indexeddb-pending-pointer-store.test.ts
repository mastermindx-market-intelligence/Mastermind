// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory, IDBDatabase, IDBObjectStore, IDBVersionChangeEvent } from "fake-indexeddb";
import {
  createIndexedDbPendingPointerStore, PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME,
  PENDING_POINTER_OPEN_TIMEOUT_MS, PENDING_POINTER_ERRORS as ERR,
} from "./indexeddb-pending-pointer-store";
import type { OperationPointer } from "./operation-controller";

const scope = "a".repeat(64), otherScope = "b".repeat(64);
const pointer: OperationPointer = { operationKey: "mmos-launch-" + "1".repeat(40), kind: "launch", targetKey: "WS:Original.Work-1" };
const replacement: OperationPointer = { ...pointer, operationKey: "mmos-launch-" + "2".repeat(40) };
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

function database(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(PENDING_POINTER_DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(PENDING_POINTER_STORE_NAME);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}
async function raw(factory: IDBFactory, value?: unknown): Promise<unknown> {
  const db = await database(factory);
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(PENDING_POINTER_STORE_NAME, value === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore(PENDING_POINTER_STORE_NAME);
      let observed: unknown;
      const request = value === undefined ? store.get(scope) : store.put(value, scope);
      request.onsuccess = () => { observed = request.result; };
      tx.oncomplete = () => resolve(observed);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

describe("durable IndexedDB pointer transactions", () => {
  it("reopens the original pointer and stores only the closed lookup record", async () => {
    const factory = new IDBFactory();
    const first = createIndexedDbPendingPointerStore(factory);
    expect(await first.read(scope)).toBeNull();
    expect(await first.reserve(scope, pointer)).toEqual({ reserved: true });
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(pointer);
    expect(await raw(factory)).toEqual({ v: 1, ...pointer });
    expect(await first.read(otherScope)).toBeNull();
  });
  it("serializes two connections so only one reservation succeeds, even for an equal pointer", async () => {
    const factory = new IDBFactory();
    const one = createIndexedDbPendingPointerStore(factory), two = createIndexedDbPendingPointerStore(factory);
    const results = await Promise.all([one.reserve(scope, pointer), two.reserve(scope, pointer)]);
    expect(results.filter((r) => r.reserved)).toHaveLength(1);
    expect(results.filter((r) => !r.reserved)).toEqual([{ reserved: false, pointer }]);
  });
  it("never overwrites an occupied pointer and stale clears cannot remove a replacement", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.reserve(scope, pointer);
    expect(await store.reserve(scope, replacement)).toEqual({ reserved: false, pointer });
    expect(await store.clearIfEqual(scope, replacement)).toBe(false);
    expect(await store.clearIfEqual(scope, pointer)).toBe(true);
    await store.reserve(scope, replacement);
    expect(await store.clearIfEqual(scope, pointer)).toBe(false);
    expect(await store.read(scope)).toEqual(replacement);
  });
  it.each([null, { v: 2, ...pointer }, { v: 1, ...pointer, token: "not-persisted" }, { v: 1, ...pointer, kind: "message" }])(
    "refuses corrupt records on read/reserve/clear instead of treating them as absent", async (record) => {
      const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
      await raw(factory, record);
      await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
      await expect(store.reserve(scope, pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
      await expect(store.clearIfEqual(scope, pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
      expect(await raw(factory)).toEqual(record);
    });
  it("refuses missing storage, invalid namespaces, nonlaunch and extra input fields", async () => {
    await expect(createIndexedDbPendingPointerStore(undefined).read(scope)).rejects.toThrow(ERR.UNAVAILABLE);
    const store = createIndexedDbPendingPointerStore(new IDBFactory());
    await expect(store.read("unverified-subject")).rejects.toThrow(ERR.INVALID_SCOPE);
    for (const invalid of [{ ...pointer, kind: "stop" }, { ...pointer, payload: {} }, { ...pointer, targetKey: "WS:X" }])
      await expect(store.reserve(scope, invalid as OperationPointer)).rejects.toThrow(ERR.INVALID_POINTER);
  });
  it("does not resolve until the durable transaction completes", async () => {
    const completed: boolean[] = [];
    const original = IDBDatabase.prototype.transaction;
    vi.spyOn(IDBDatabase.prototype, "transaction").mockImplementation(function (this: IDBDatabase, ...args) {
      const tx = original.apply(this, args);
      if (args[1] === "readwrite") tx.addEventListener("complete", () => completed.push(true));
      return tx;
    });
    await createIndexedDbPendingPointerStore(new IDBFactory()).reserve(scope, pointer);
    expect(completed).toEqual([true]);
  });
  it("refuses unsupported strict durability before enqueuing a write", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.read(scope);
    const original = IDBDatabase.prototype.transaction;
    vi.spyOn(IDBDatabase.prototype, "transaction").mockImplementation(function (this: IDBDatabase, ...args) {
      if (args[2]?.durability === "strict") throw new TypeError("unsupported");
      return original.apply(this, args);
    });
    await expect(store.reserve(scope, pointer)).rejects.toThrow(ERR.TX_FAILED);
    expect(await raw(factory)).toBeUndefined();
  });
  it("aborts an uncommitted reservation without retaining the write", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const abort = new AbortController(), original = IDBObjectStore.prototype.add;
    vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args);
      request.addEventListener("success", () => abort.abort());
      return request;
    });
    await expect(store.reserve(scope, pointer, abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(await store.read(scope)).toBeNull();
  });
  it("aborts an uncommitted clear and preserves the original pointer", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.reserve(scope, pointer);
    const abort = new AbortController(), original = IDBObjectStore.prototype.delete;
    vi.spyOn(IDBObjectStore.prototype, "delete").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args);
      request.addEventListener("success", () => abort.abort());
      return request;
    });
    await expect(store.clearIfEqual(scope, pointer, abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(await store.read(scope)).toEqual(pointer);
  });
  it("withholds a transaction interrupted by database version change", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const original = IDBObjectStore.prototype.get;
    vi.spyOn(IDBObjectStore.prototype, "get").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args), db = this.transaction.db;
      request.addEventListener("success", () => db.dispatchEvent(new IDBVersionChangeEvent("versionchange")));
      return request;
    });
    await expect(store.read(scope)).rejects.toThrow(ERR.VERSION_CHANGE);
  });
  it("rejects an already cancelled operation without opening storage", async () => {
    const factory = new IDBFactory(), spy = vi.spyOn(factory, "open"), abort = new AbortController();
    abort.abort();
    await expect(createIndexedDbPendingPointerStore(factory).reserve(scope, pointer, abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(spy).not.toHaveBeenCalled();
  });
  it("rejects a blocked open whose result getter is still unavailable", async () => {
    const request = { get result() { throw new Error("InvalidStateError"); }, onblocked: null as (() => void) | null };
    const factory = { open() { queueMicrotask(() => request.onblocked?.()); return request; } } as unknown as IDBFactory;
    await expect(createIndexedDbPendingPointerStore(factory).read(scope)).rejects.toThrow(ERR.BLOCKED);
  });
  it("rejects an open timeout and closes a late success without starting a transaction", async () => {
    vi.useFakeTimers();
    const db = { close: vi.fn() };
    let ready = false;
    const request = { get result() { if (!ready) throw new Error("InvalidStateError"); return db; },
      onsuccess: null as (() => void) | null };
    const factory = { open: () => request } as unknown as IDBFactory;
    const result = createIndexedDbPendingPointerStore(factory).read(scope).catch((error: Error) => error.message);
    await vi.advanceTimersByTimeAsync(PENDING_POINTER_OPEN_TIMEOUT_MS + 1);
    expect(await result).toBe(ERR.TIMEOUT);
    ready = true; request.onsuccess?.();
    expect(db.close).toHaveBeenCalledTimes(1);
  });
});
