/**
 * Recovery-distinction tests for OperationController.
 *
 * These drive the real controller with in-memory port and store fakes:
 *
 *  - a default `recover()` is read-only: it calls `readOperation` only and
 *    keeps the old terminal-refused semantics, even when the port exposes the
 *    optional observer;
 *
 *  - an explicit `recover({ reconcileSource: true })` calls the optional
 *    `reconcileOperation` exactly once with the exact stored original pointer
 *    — and only for the closed source kinds. No prepare, no reserve, no
 *    submit, no new key, no advance;
 *
 *  - a reconcile refusal / throw / unknown / partial READY_FOR_ADVANCE holds
 *    the exact original pointer as `unknown` (never cleared): the observational
 *    POST does not prove the original source action had no effect. Only a
 *    verified overall terminal accepted receipt clears, and only through the
 *    existing exact compare-clear;
 *
 *  - context rotation between the store read and the pending response masks
 *    the state and preserves the old-scope hint, and concurrent recovery is
 *    singleflight — never two observational calls.
 */

import { describe, expect, it, vi } from "vitest";
import { OperationController } from "./operation-controller";
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationKind,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "./operation-controller";

const SOURCE_KINDS = [
  "project_create",
  "project_adopt",
  "direction_accept",
  "project_source_write",
] as const;

const NON_SOURCE_KINDS = [
  "launch",
  "message",
  "stop",
  "consume",
  "project_pause",
  "project_resume",
] as const;

const SCOPE = "scope-A";
const GENERATION = "gen-1";
const TARGET = "target-1";
const ADOPT_KEY = `mmos-project-adopt-${"c".repeat(40)}`;
const DIGEST = "b".repeat(64);
/** Producer text that must never surface as a UI reason. */
const PRODUCER_REFUSAL_TEXT = "SOURCE_RECONCILE_POST_REFUSED_BY_PRODUCER";

function pointerFor(kind: OperationKind, overrides?: Partial<OperationPointer>): OperationPointer {
  return {
    operationKey: kind === "project_adopt" ? ADOPT_KEY : `op-${kind}-1`,
    kind,
    targetKey: TARGET,
    ...overrides,
  };
}

function receiptFor(pointer: OperationPointer, overrides?: Partial<EffectReceipt>): EffectReceipt {
  return {
    operationKey: pointer.operationKey,
    kind: pointer.kind,
    targetKey: pointer.targetKey,
    disposition: "refused",
    ...overrides,
  };
}

/** Exact match on all three fields, as the real host store is specified to do. */
function samePointer(a: OperationPointer, b: OperationPointer): boolean {
  return (
    a.operationKey === b.operationKey &&
    a.kind === b.kind &&
    a.targetKey === b.targetKey
  );
}

interface HarnessOptions {
  /** Build the port WITHOUT the optional reconcileOperation method. */
  omitReconcile?: boolean;
  /** Make reading the optional reconcileOperation property throw. */
  throwOnReconcileAccess?: boolean;
}

function makeHarness(initial: OperationPointer | null, options: HarnessOptions = {}) {
  const context = vi.fn((): OwnerContext | null => ({ principalScope: SCOPE, generation: GENERATION }));
  const prepare = vi.fn((intent: CommandIntent): OperationPointer => ({
    operationKey: `minted-${intent.kind}-1`,
    kind: intent.kind,
    targetKey: intent.targetKey,
  }));
  const submit = vi.fn(async (pointer: OperationPointer, _intent: CommandIntent, _signal: AbortSignal): Promise<EffectReceipt> => receiptFor(pointer));
  const readOperation = vi.fn(async (pointer: OperationPointer, _signal: AbortSignal): Promise<EffectReceipt> => receiptFor(pointer));
  const reconcileOperation = vi.fn(async (pointer: OperationPointer, _signal: AbortSignal): Promise<EffectReceipt> => receiptFor(pointer, { reason: PRODUCER_REFUSAL_TEXT }));
  const advanceOperation = vi.fn(async (pointer: OperationPointer, _digest: string, _signal: AbortSignal): Promise<EffectReceipt> => receiptFor(pointer));

  let stored: OperationPointer | null = initial;
  const storeRead = vi.fn(async (_scope: string, _signal?: AbortSignal): Promise<OperationPointer | null> => stored);
  const reserve = vi.fn(async (_scope: string, pointer: OperationPointer, _signal?: AbortSignal) => {
    if (stored === null) {
      stored = pointer;
      return { reserved: true } as const;
    }
    return { reserved: false, pointer: stored } as const;
  });
  const clearIfEqual = vi.fn(async (_scope: string, pointer: OperationPointer, _signal?: AbortSignal): Promise<boolean> => {
    if (stored !== null && samePointer(stored, pointer)) {
      stored = null;
      return true;
    }
    return false;
  });

  const port: FiniteCommandPort = options.omitReconcile
    ? { context, prepare, submit, readOperation, advanceOperation }
    : { context, prepare, submit, readOperation, reconcileOperation, advanceOperation };
  if (options.throwOnReconcileAccess) {
    Object.defineProperty(port, "reconcileOperation", {
      get() {
        throw new Error("reconcile observer unavailable");
      },
      enumerable: true,
      configurable: true,
    });
  }
  const store: PendingPointerStore = { read: storeRead, reserve, clearIfEqual };
  const controller = new OperationController(port, store);

  return {
    controller,
    port,
    stored: () => stored,
    context,
    prepare,
    submit,
    readOperation,
    reconcileOperation,
    advanceOperation,
    storeRead,
    reserve,
    clearIfEqual,
  };
}

type Harness = ReturnType<typeof makeHarness>;

/** Assert the recovery path stayed pure observation: no effects, no reservations. */
async function expectObservationOnly(h: Harness): Promise<void> {
  expect(h.prepare).not.toHaveBeenCalled();
  expect(h.submit).not.toHaveBeenCalled();
  expect(h.advanceOperation).not.toHaveBeenCalled();
  expect(h.reserve).not.toHaveBeenCalled();
}

function tick(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe("default recover() stays read-only", () => {
  it("uses readOperation only on a stored source pointer and keeps terminal-refused semantics", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer);
    const state = await h.controller.recover();

    expect(h.readOperation).toHaveBeenCalledTimes(1);
    expect(h.readOperation.mock.calls[0]![0]).toBe(pointer);
    expect(h.reconcileOperation).not.toHaveBeenCalled();
    await expectObservationOnly(h);
    expect(h.storeRead).toHaveBeenCalledTimes(1);
    expect(h.storeRead.mock.calls[0]![0]).toBe(SCOPE);
    // Old default semantics: a refused read receipt is terminal and clears.
    expect(state).toEqual({ status: "refused", pointer: null, reason: "REFUSED" });
    expect(h.clearIfEqual).toHaveBeenCalledTimes(1);
    expect(h.clearIfEqual.mock.calls[0]!.slice(0, 2)).toEqual([SCOPE, pointer]);
    expect(h.stored()).toBeNull();
  });

  it("keeps a non-source default recovery terminal on refusal too", async () => {
    const pointer = pointerFor("launch");
    const h = makeHarness(pointer);
    const state = await h.controller.recover();
    expect(h.reconcileOperation).not.toHaveBeenCalled();
    expect(state).toEqual({ status: "refused", pointer: null, reason: "REFUSED" });
    expect(h.stored()).toBeNull();
  });

  for (const kind of SOURCE_KINDS) {
    it(`never invokes the optional observer for ${kind} without the explicit flag`, async () => {
      const pointer = pointerFor(kind);
      const h = makeHarness(pointer);
      const state = await h.controller.recover();

      expect(h.reconcileOperation).not.toHaveBeenCalled();
      expect(h.readOperation).toHaveBeenCalledTimes(1);
      expect(state.status).toBe("refused");
    });
  }
});

describe("explicit recover({ reconcileSource: true }) uses the optional observer", () => {
  for (const kind of SOURCE_KINDS) {
    it(`observes ${kind} exactly once with the exact stored pointer and holds its refusal`, async () => {
      const pointer = pointerFor(kind);
      const h = makeHarness(pointer);
      const state = await h.controller.recover({ reconcileSource: true });

      expect(h.reconcileOperation).toHaveBeenCalledTimes(1);
      const [observed, signal] = h.reconcileOperation.mock.calls[0]!;
      expect(observed).toBe(pointer);
      expect(signal).toBeInstanceOf(AbortSignal);
      expect(h.readOperation).not.toHaveBeenCalled();
      await expectObservationOnly(h);
      expect(h.storeRead).toHaveBeenCalledTimes(1);
      expect(h.storeRead.mock.calls[0]![0]).toBe(SCOPE);
      // The observational POST was refused: that is NOT evidence the original
      // source action had no effect, so the exact original pointer is retained.
      expect(state).toEqual({ status: "unknown", pointer, reason: "UNKNOWN_RECEIPT" });
      expect(h.clearIfEqual).not.toHaveBeenCalled();
      expect(h.stored()).toBe(pointer);
    });
  }

  for (const kind of NON_SOURCE_KINDS) {
    it(`keeps ${kind} recovery read-only even under the explicit flag`, async () => {
      const pointer = pointerFor(kind);
      const h = makeHarness(pointer);
      const state = await h.controller.recover({ reconcileSource: true });

      expect(h.reconcileOperation).not.toHaveBeenCalled();
      expect(h.readOperation).toHaveBeenCalledTimes(1);
      expect(state).toEqual({ status: "refused", pointer: null, reason: "REFUSED" });
      expect(h.stored()).toBeNull();
    });
  }

  it("falls back to read-only recovery when the optional method is absent", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer, { omitReconcile: true });
    const state = await h.controller.recover({ reconcileSource: true });

    expect(h.readOperation).toHaveBeenCalledTimes(1);
    expect(state).toEqual({ status: "refused", pointer: null, reason: "REFUSED" });
    expect(h.stored()).toBeNull();
  });

  it("falls back to read-only recovery when reading the optional method throws", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer, { throwOnReconcileAccess: true });
    const state = await h.controller.recover({ reconcileSource: true });

    expect(h.readOperation).toHaveBeenCalledTimes(1);
    expect(state).toEqual({ status: "refused", pointer: null, reason: "REFUSED" });
    expect(h.stored()).toBeNull();
  });

  it("stays read-only when reconcileSource is explicitly false", async () => {
    const pointer = pointerFor("project_source_write");
    const h = makeHarness(pointer);
    const state = await h.controller.recover({ reconcileSource: false });

    expect(h.reconcileOperation).not.toHaveBeenCalled();
    expect(h.readOperation).toHaveBeenCalledTimes(1);
    expect(state.status).toBe("refused");
  });

  it("never observes when there is no stored pointer to reconcile", async () => {
    const h = makeHarness(null);
    const state = await h.controller.recover({ reconcileSource: true });

    expect(h.reconcileOperation).not.toHaveBeenCalled();
    expect(h.readOperation).not.toHaveBeenCalled();
    expect(state).toEqual({ status: "idle", pointer: null, reason: "RECOVER_NO_POINTER" });
    expect(h.stored()).toBeNull();
  });
});

describe("observational reconcile outcomes hold the original pointer", () => {
  it("the same refused receipt is terminal read-only but held unknown on reconcile", async () => {
    const pointer = pointerFor("project_create");

    const readonlyH = makeHarness(pointer);
    const readonlyState = await readonlyH.controller.recover();
    expect(readonlyState).toEqual({ status: "refused", pointer: null, reason: "REFUSED" });
    expect(readonlyH.stored()).toBeNull();

    const reconcileH = makeHarness(pointer);
    const reconcileState = await reconcileH.controller.recover({ reconcileSource: true });
    expect(reconcileState).toEqual({ status: "unknown", pointer, reason: "UNKNOWN_RECEIPT" });
    expect(reconcileH.clearIfEqual).not.toHaveBeenCalled();
    expect(reconcileH.stored()).toBe(pointer);
  });

  it("a thrown reconcile holds the pointer as RECOVER_FAILED without clearing", async () => {
    const pointer = pointerFor("direction_accept");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockRejectedValueOnce(new Error("observational POST refused"));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "RECOVER_FAILED" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });

  it("an unknown reconcile receipt holds the pointer without clearing", async () => {
    const pointer = pointerFor("project_source_write");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { disposition: "unknown" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "UNKNOWN_RECEIPT" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });

  it("a partial READY_FOR_ADVANCE witness holds the pointer and never advances", async () => {
    const pointer = pointerFor("project_adopt");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, {
      disposition: "unknown",
      reason: "READY_FOR_ADVANCE",
      advance: { phase_receipt_digest: DIGEST },
    }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({
      status: "unknown",
      pointer,
      reason: "READY_FOR_ADVANCE",
      advance: { phase_receipt_digest: DIGEST },
    });
    expect(h.advanceOperation).not.toHaveBeenCalled();
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });

  it("a verified terminal accepted receipt clears through exact compare-clear", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { disposition: "accepted" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "accepted", pointer: null, reason: "ACCEPTED" });
    expect(h.clearIfEqual).toHaveBeenCalledTimes(1);
    expect(h.clearIfEqual.mock.calls[0]!.slice(0, 2)).toEqual([SCOPE, pointer]);
    expect(h.stored()).toBeNull();
  });

  it("a false compare-clear holds an accepted receipt as unknown", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer);
    h.clearIfEqual.mockResolvedValueOnce(false);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { disposition: "accepted" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "UNKNOWN_RECEIPT" });
    expect(h.stored()).toBe(pointer);
  });

  it("a rejected compare-clear holds an accepted receipt as unknown", async () => {
    const pointer = pointerFor("project_adopt");
    const h = makeHarness(pointer);
    h.clearIfEqual.mockRejectedValueOnce(new Error("store busy"));
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { disposition: "accepted" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "UNKNOWN_RECEIPT" });
    expect(h.stored()).toBe(pointer);
  });
});

describe("receipt identity fencing on the observational call", () => {
  it("a receipt with a foreign operationKey cannot publish or clear", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { operationKey: "foreign-key" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "RECEIPT_MISMATCH" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });

  it("a receipt with a foreign kind cannot publish or clear", async () => {
    const pointer = pointerFor("direction_accept");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { kind: "project_create" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "KIND_MISMATCH" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });

  it("a receipt with a foreign targetKey cannot publish or clear", async () => {
    const pointer = pointerFor("project_source_write");
    const h = makeHarness(pointer);
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { targetKey: "foreign-target" }));
    const state = await h.controller.recover({ reconcileSource: true });

    expect(state).toEqual({ status: "unknown", pointer, reason: "TARGET_MISMATCH" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });
});

describe("context rotation around the observational call", () => {
  it("a generation rotation while the reconcile is pending masks the state, preserves the hint, and a later recover still resolves it", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer);
    let release!: (receipt: EffectReceipt) => void;
    const gate = new Promise<EffectReceipt>((done) => {
      release = done;
    });
    h.reconcileOperation.mockImplementationOnce(() => gate);

    const pending = h.controller.recover({ reconcileSource: true });
    await tick();
    h.context.mockImplementation(() => ({ principalScope: SCOPE, generation: "gen-2" }));
    // An accepted receipt arriving after the rotation is dropped entirely.
    release(receiptFor(pointer, { disposition: "accepted" }));
    const state = await pending;

    expect(state).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(h.reconcileOperation).toHaveBeenCalledTimes(1);
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);

    // The hint survived in its original scope and resolves under the new epoch.
    h.reconcileOperation.mockResolvedValueOnce(receiptFor(pointer, { disposition: "accepted" }));
    const recovered = await h.controller.recover({ reconcileSource: true });
    expect(recovered).toEqual({ status: "accepted", pointer: null, reason: "ACCEPTED" });
    expect(h.stored()).toBeNull();
  });

  it("a principal scope rotation while the reconcile is pending masks the state and preserves the old scope hint", async () => {
    const pointer = pointerFor("direction_accept");
    const h = makeHarness(pointer);
    let release!: (receipt: EffectReceipt) => void;
    const gate = new Promise<EffectReceipt>((done) => {
      release = done;
    });
    h.reconcileOperation.mockImplementationOnce(() => gate);

    const pending = h.controller.recover({ reconcileSource: true });
    await tick();
    h.context.mockImplementation(() => ({ principalScope: "scope-B", generation: GENERATION }));
    release(receiptFor(pointer));
    const state = await pending;

    expect(state).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.storeRead.mock.calls[0]![0]).toBe(SCOPE);
    expect(h.stored()).toBe(pointer);
  });

  it("a sign-out (null context) while the reconcile is pending masks the state and preserves the hint", async () => {
    const pointer = pointerFor("project_source_write");
    const h = makeHarness(pointer);
    let release!: (receipt: EffectReceipt) => void;
    const gate = new Promise<EffectReceipt>((done) => {
      release = done;
    });
    h.reconcileOperation.mockImplementationOnce(() => gate);

    const pending = h.controller.recover({ reconcileSource: true });
    await tick();
    h.context.mockImplementation(() => null);
    release(receiptFor(pointer));
    const state = await pending;

    expect(state).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });

  it("a rotation while a read-only recovery is pending masks the state the same way", async () => {
    const pointer = pointerFor("launch");
    const h = makeHarness(pointer);
    let release!: (receipt: EffectReceipt) => void;
    const gate = new Promise<EffectReceipt>((done) => {
      release = done;
    });
    h.readOperation.mockImplementationOnce(() => gate);

    const pending = h.controller.recover();
    await tick();
    h.context.mockImplementation(() => ({ principalScope: SCOPE, generation: "gen-2" }));
    release(receiptFor(pointer));
    const state = await pending;

    expect(state).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(h.reconcileOperation).not.toHaveBeenCalled();
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });
});

describe("recovery singleflight", () => {
  it("a concurrent same-context recover joins the in-flight observation instead of issuing a second one", async () => {
    const pointer = pointerFor("project_create");
    const h = makeHarness(pointer);
    let release!: (receipt: EffectReceipt) => void;
    const gate = new Promise<EffectReceipt>((done) => {
      release = done;
    });
    h.reconcileOperation.mockImplementationOnce(() => gate);

    const first = h.controller.recover({ reconcileSource: true });
    await tick();
    // The async method wraps the joined in-flight run in its own promise, so
    // the join itself is proven below: one observational call, and both
    // callers resolve to the very same state object.
    const second = h.controller.recover({ reconcileSource: true });
    release(receiptFor(pointer, { reason: PRODUCER_REFUSAL_TEXT }));

    const [a, b] = await Promise.all([first, second]);
    expect(h.reconcileOperation).toHaveBeenCalledTimes(1);
    expect(h.readOperation).not.toHaveBeenCalled();
    await expectObservationOnly(h);
    expect(a).toBe(b);
    expect(a).toEqual({ status: "unknown", pointer, reason: "UNKNOWN_RECEIPT" });
    expect(h.stored()).toBe(pointer);
  });

  it("a foreign-context recover during flight is refused busy without a second observation or a pointer leak", async () => {
    const pointer = pointerFor("direction_accept");
    const h = makeHarness(pointer);
    let release!: (receipt: EffectReceipt) => void;
    const gate = new Promise<EffectReceipt>((done) => {
      release = done;
    });
    h.reconcileOperation.mockImplementationOnce(() => gate);

    const first = h.controller.recover({ reconcileSource: true });
    await tick();
    h.context.mockImplementation(() => ({ principalScope: "scope-B", generation: GENERATION }));
    const busy = await h.controller.recover({ reconcileSource: true });

    expect(busy).toEqual({ status: "refused", pointer: null, reason: "OPERATION_BUSY" });
    expect(h.reconcileOperation).toHaveBeenCalledTimes(1);

    release(receiptFor(pointer, { disposition: "accepted" }));
    const settled = await first;
    expect(settled).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(h.clearIfEqual).not.toHaveBeenCalled();
    expect(h.stored()).toBe(pointer);
  });
});

describe("no automatic reconcile from begin or advance", () => {
  it("begin never calls the optional observer", async () => {
    const h = makeHarness(null);
    const intent: CommandIntent = { kind: "project_create", payload: {}, targetKey: TARGET };
    const state = await h.controller.begin(intent);

    expect(h.reconcileOperation).not.toHaveBeenCalled();
    expect(h.prepare).toHaveBeenCalledTimes(1);
    expect(h.submit).toHaveBeenCalledTimes(1);
    expect(state.status).toBe("refused");
    expect(h.stored()).toBeNull();
  });

  it("advance never calls the optional observer", async () => {
    const pointer = pointerFor("project_adopt");
    const h = makeHarness(pointer);
    h.readOperation.mockResolvedValueOnce(receiptFor(pointer, {
      disposition: "unknown",
      reason: "READY_FOR_ADVANCE",
      advance: { phase_receipt_digest: DIGEST },
    }));
    h.advanceOperation.mockResolvedValueOnce(receiptFor(pointer));
    const state = await h.controller.advance();

    expect(h.reconcileOperation).not.toHaveBeenCalled();
    expect(h.readOperation).toHaveBeenCalledTimes(1);
    expect(h.advanceOperation).toHaveBeenCalledTimes(1);
    expect(state.status).toBe("unknown");
    expect(h.stored()).toBe(pointer);
  });
});

it.each(['options','method'])('fences reentrant %s resolution before any original scoped request',async(which)=>{
 const pointer=pointerFor('project_adopt'),h=makeHarness(pointer);
 const rotate=()=>h.context.mockImplementation(()=>({principalScope:'foreign-scope',generation:'gen-2'}));
 const options:{readonly reconcileSource?:boolean}={reconcileSource:true};
 if(which==='options')Object.defineProperty(options,'reconcileSource',{get(){rotate();return true;}});
 else Object.defineProperty(h.port,'reconcileOperation',{get(){rotate();return h.reconcileOperation;}});
 const state=await h.controller.recover(options);
 expect(state).toEqual({status:'idle',pointer:null,reason:'EPOCH_CHANGED'});
 expect(h.reconcileOperation).not.toHaveBeenCalled();expect(h.readOperation).not.toHaveBeenCalled();
 expect(h.clearIfEqual).not.toHaveBeenCalled();expect(h.stored()).toEqual(pointer);
});
