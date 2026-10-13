// @vitest-environment node
// Focused coverage for the session-exclusive durable pending-pointer namespace.
import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory, IDBObjectStore } from "fake-indexeddb";
import {
  createIndexedDbPendingPointerStore,
  PENDING_POINTER_DB_NAME,
} from "./indexeddb-pending-pointer-store";
import {
  createIndexedDbSessionPendingPointerStore,
  SESSION_POINTER_DB_NAME,
  SESSION_POINTER_ERRORS as ERR,
} from "./indexeddb-session-pending-pointer-store";
import type { OperationPointer } from "./operation-controller";

const scope = "a".repeat(64);
const otherScope = "b".repeat(64);
const pointer: OperationPointer = {
  operationKey: "session-continue-" + "1".repeat(64),
  kind: "message",
  targetKey: "fabric_attempt:" + "2".repeat(64),
};
const replacement: OperationPointer = { ...pointer, operationKey: "session-continue-" + "3".repeat(64) };
// Launch-shaped pointers live in the launch namespace only; this store must
// refuse every one of them instead of adopting a cross-kind hint.
const launchPointer: OperationPointer = {
  operationKey: "mmos-launch-" + "4".repeat(40),
  kind: "launch",
  targetKey: "WS:Original.Work-1",
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("session-exclusive durable namespace", () => {
  it("round-trips a message pointer in its own database, isolated from the launch namespace", async () => {
    const factory = new IDBFactory();
    const launch = createIndexedDbPendingPointerStore(factory);
    const session = createIndexedDbSessionPendingPointerStore(factory);
    await launch.reserve(scope, launchPointer);
    expect(await session.read(scope)).toBeNull();
    expect(await session.reserve(scope, pointer)).toEqual({ reserved: true });
    expect(await createIndexedDbSessionPendingPointerStore(factory).read(scope)).toEqual(pointer);
    // The launch record is untouched: same factory, different database, no
    // migration, no cross-kind read.
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(launchPointer);
    expect(await session.read(otherScope)).toBeNull();
    expect(SESSION_POINTER_DB_NAME).not.toBe(PENDING_POINTER_DB_NAME);
  });

  it("serializes concurrent reservations so exactly one wins, even for an equal pointer", async () => {
    const factory = new IDBFactory();
    const one = createIndexedDbSessionPendingPointerStore(factory);
    const two = createIndexedDbSessionPendingPointerStore(factory);
    const results = await Promise.all([
      one.reserve(scope, pointer),
      two.reserve(scope, pointer),
    ]);
    expect(results.filter((r) => r.reserved)).toHaveLength(1);
    expect(results.filter((r) => !r.reserved)).toEqual([{ reserved: false, pointer }]);
  });

  it("clears only the exact retained pointer and keeps any replacement", async () => {
    const factory = new IDBFactory();
    const store = createIndexedDbSessionPendingPointerStore(factory);
    await store.reserve(scope, pointer);
    expect(await store.clearIfEqual(scope, replacement)).toBe(false);
    expect(await store.read(scope)).toEqual(pointer);
    expect(await store.clearIfEqual(scope, pointer)).toBe(true);
    expect(await store.read(scope)).toBeNull();
    expect(await store.clearIfEqual(scope, pointer)).toBe(false);
  });

  it.each([
    launchPointer,
    { ...pointer, kind: "stop" },
    { ...pointer, kind: "launch" },
    { ...pointer, operationKey: "mmos-launch-" + "4".repeat(40) },
    { ...pointer, targetKey: "WS:Not.An.Attempt" },
    { ...pointer, targetKey: null },
    { ...pointer, extra: true },
  ])("refuses non-session pointer input %#", async (invalid) => {
    const store = createIndexedDbSessionPendingPointerStore(new IDBFactory());
    await expect(store.reserve(scope, invalid as OperationPointer)).rejects.toThrow(ERR.INVALID_POINTER);
    await expect(store.clearIfEqual(scope, invalid as OperationPointer)).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await store.read(scope)).toBeNull();
  });

  it.each([
    null,
    { v: 2, ...pointer },
    { v: 1, ...pointer, kind: "launch" },
    { v: 1, ...launchPointer },
    { v: 1, ...pointer, token: "not-persisted" },
  ])("fails closed on corrupt stored records %# instead of treating them as absent", async (record) => {
    const factory = new IDBFactory();
    const store = createIndexedDbSessionPendingPointerStore(factory);
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = factory.open(SESSION_POINTER_DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("pointers");
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("pointers", "readwrite");
      tx.objectStore("pointers").put(record, scope);
      tx.oncomplete = () => resolve();
      tx.onabort = () => reject(tx.error);
    });
    db.close();
    await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
    await expect(store.reserve(scope, pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
    await expect(store.clearIfEqual(scope, pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
  });

  it("refuses missing storage and invalid scopes", async () => {
    await expect(
      createIndexedDbSessionPendingPointerStore(undefined).read(scope),
    ).rejects.toThrow(ERR.UNAVAILABLE);
    const store = createIndexedDbSessionPendingPointerStore(new IDBFactory());
    await expect(store.read("unverified-subject")).rejects.toThrow(ERR.INVALID_SCOPE);
    await expect(store.reserve("unverified-subject", pointer)).rejects.toThrow(ERR.INVALID_SCOPE);
  });

  it("aborts an uncommitted reservation without retaining the write", async () => {
    const factory = new IDBFactory();
    const store = createIndexedDbSessionPendingPointerStore(factory);
    const abort = new AbortController();
    await expect(store.reserve(scope, pointer, abort.signal)).resolves.toEqual({ reserved: true });
    await store.clearIfEqual(scope, pointer);
    const late = new AbortController();
    const originalAdd = IDBObjectStore.prototype.add;
    const spy = vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = originalAdd.apply(this, args);
      request.addEventListener("success", () => late.abort());
      return request;
    });
    try {
      await expect(store.reserve(scope, pointer, late.signal)).rejects.toThrow(ERR.CANCELLED);
      expect(await store.read(scope)).toBeNull();
    } finally {
      spy.mockRestore();
    }
  });

  it("rejects an already cancelled operation without opening storage", async () => {
    const factory = new IDBFactory();
    const spy = vi.spyOn(factory, "open");
    const abort = new AbortController();
    abort.abort();
    await expect(
      createIndexedDbSessionPendingPointerStore(factory).reserve(scope, pointer, abort.signal),
    ).rejects.toThrow(ERR.CANCELLED);
    expect(spy).not.toHaveBeenCalled();
  });
});
