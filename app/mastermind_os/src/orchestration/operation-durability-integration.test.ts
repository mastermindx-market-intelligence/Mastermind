import { describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { createIndexedDbPendingPointerStore } from "./indexeddb-pending-pointer-store";
import { OperationController, type CommandIntent, type EffectReceipt, type FiniteCommandPort, type OperationPointer, type PendingPointerStore } from "./operation-controller";

const scope = "a".repeat(64);
const intent: CommandIntent = { kind: "launch", targetKey: "WS:DURABLE-TEST", payload: { goal: "Private goal must not persist" } };
const pointer: OperationPointer = { operationKey: "mmos-launch-" + "1".repeat(40), kind: "launch", targetKey: intent.targetKey };
const accepted = (p: OperationPointer): EffectReceipt => ({ ...p, disposition: "accepted",
  missionSelection: { workRef: p.targetKey!, rootJobId: "JOB-DURABLE-TEST" } });
function fixture() {
  let generation = "1";
  const port: FiniteCommandPort = {
    context: () => ({ principalScope: scope, generation }),
    prepare: vi.fn(() => pointer),
    submit: vi.fn(async () => { throw new Error("Lost response after acceptance"); }),
    readOperation: vi.fn(async (p) => accepted(p)),
  };
  return { port, drift: () => { generation = "2"; } };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

describe("controller with durable IndexedDB", () => {
  it("two independent connections reserve one effect; a reopened controller recovers the original without resubmit", async () => {
    const factory = new IDBFactory(), f = fixture();
    const a = createIndexedDbPendingPointerStore(factory), b = createIndexedDbPendingPointerStore(factory);
    const ca = new OperationController(f.port, a), cb = new OperationController(f.port, b);
    const results = await Promise.all([ca.begin(intent), cb.begin(intent)]);
    expect(results.map((r) => r.status).sort()).toEqual(["checking", "unknown"]);
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(await a.read(scope)).toEqual(pointer);
    expect(JSON.stringify(await a.read(scope))).not.toContain("Private goal");
    ca.invalidate(); cb.invalidate();
    const reopenedStore = createIndexedDbPendingPointerStore(factory);
    const reopened = new OperationController(f.port, reopenedStore);
    expect(await reopened.recover()).toMatchObject({ status: "accepted", pointer: null,
      missionSelection: { workRef: "WS:DURABLE-TEST", rootJobId: "JOB-DURABLE-TEST" } });
    expect(f.port.readOperation).toHaveBeenCalledExactlyOnceWith(pointer, expect.any(AbortSignal));
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(await reopenedStore.read(scope)).toBeNull();
  });
  it("auth drift after the effect hides the prior pointer and retains it for original-scope recovery", async () => {
    const store = createIndexedDbPendingPointerStore(new IDBFactory()), f = fixture();
    vi.mocked(f.port.submit).mockImplementation(async (p) => { f.drift(); return accepted(p); });
    const controller = new OperationController(f.port, store);
    expect(await controller.begin(intent)).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(await store.read(scope)).toEqual(pointer);
    expect(await controller.recover()).toMatchObject({ status: "accepted" });
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  });
  it.each(["read", "reserve"] as const)("invalidate during deferred %s aborts it and releases the settled slot", async (stage) => {
    const real = createIndexedDbPendingPointerStore(new IDBFactory()), gate = deferred<void>(), entered = deferred<AbortSignal>();
    const store: PendingPointerStore = { ...real };
    if (stage === "read") store.read = async (s, signal) => {
      entered.resolve(signal!); await gate.promise;
      if (signal!.aborted) throw new Error("aborted"); return real.read(s, signal);
    };
    else store.reserve = async (s, p, signal) => {
      entered.resolve(signal!); await gate.promise;
      if (signal!.aborted) throw new Error("aborted"); return real.reserve(s, p, signal);
    };
    const f = fixture(), controller = new OperationController(f.port, store), running = controller.begin(intent);
    const signal = await entered.promise;
    controller.invalidate(); expect(signal.aborted).toBe(true);
    gate.resolve(); expect(await running).toMatchObject({ status: "idle", pointer: null });
    expect(f.port.submit).not.toHaveBeenCalled(); expect(await real.read(scope)).toBeNull();
    // Settled invalidation must release the busy slot; restoring the live adapter can execute.
    store.read = real.read; store.reserve = real.reserve;
    expect(await controller.begin(intent)).toMatchObject({ status: "unknown" });
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  });
  it.each([null, {}, { reserved: 1 }, { reserved: true, extra: true },
    { reserved: false }, { reserved: false, pointer: { operationKey: "bad" } }])(
    "malformed reservation reply causes zero submit", async (reply) => {
      const f = fixture(), store = createIndexedDbPendingPointerStore(new IDBFactory());
      const unsafe = { ...store, reserve: async () => reply } as unknown as PendingPointerStore;
      expect(await new OperationController(f.port, unsafe).begin(intent)).toMatchObject({ reason: "STORE_WRITE_FAILED" });
      expect(f.port.submit).not.toHaveBeenCalled();
    });
  it("a truthy non-boolean clear result cannot publish a terminal receipt", async () => {
    const f = fixture(), store = createIndexedDbPendingPointerStore(new IDBFactory());
    vi.mocked(f.port.submit).mockImplementation(async (p) => accepted(p));
    const unsafe = { ...store, clearIfEqual: async () => "true" } as unknown as PendingPointerStore;
    expect(await new OperationController(f.port, unsafe).begin(intent)).toMatchObject({ status: "unknown", pointer });
    expect(await store.read(scope)).toEqual(pointer);
  });
});
