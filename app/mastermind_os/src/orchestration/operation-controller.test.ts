/**
 * OperationController — acceptance tests
 *
 * Tests actual behavior, not implementation snapshots. Every test drives an
 * explicit fake port and an in-memory store and asserts on the observable
 * state, on which port methods ran, and on what the store was told.
 */

import { describe, expect, it, vi } from "vitest";
import type { MissionSelection } from "../mission";
import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationKind,
  OperationPointer,
  OperationState,
  OwnerContext,
  PendingPointerStore,
} from "./operation-controller";
import { OperationController } from "./operation-controller";

// ── Shared store state ─────────────────────────────────────────────────────────

interface StoreState {
  _storeWriteShouldFail: boolean;
  _data: Map<string, OperationPointer>;
  /** Every pointer the store was asked to persist, for privacy assertions. */
  _writes: Array<OperationPointer>;
}

/** Exact match on all three fields, as the real host store is specified to do. */
function samePointer(a: OperationPointer, b: OperationPointer): boolean {
  return (
    a.operationKey === b.operationKey &&
    a.kind === b.kind &&
    a.targetKey === b.targetKey
  );
}

function makeStoreWithState(): { store: PendingPointerStore; state: StoreState } {
  const state: StoreState = {
    _storeWriteShouldFail: false,
    _data: new Map(),
    _writes: [],
  };
  const store: PendingPointerStore = {
    read: (scope) => state._data.get(scope) ?? null,
    write: (scope, pointer) => {
      if (state._storeWriteShouldFail) throw new Error("store write failed");
      state._writes.push(pointer);
      state._data.set(scope, pointer);
    },
    clear: (scope, pointer) => {
      const existing = state._data.get(scope);
      if (existing && samePointer(existing, pointer)) state._data.delete(scope);
    },
  };
  return { store, state };
}

function makeStoreWithInitial(
  initial: Array<[string, OperationPointer]>,
): { store: PendingPointerStore; state: StoreState } {
  const { store, state } = makeStoreWithState();
  for (const [scope, pointer] of initial) state._data.set(scope, pointer);
  return { store, state };
}

// ── Fake port builder ──────────────────────────────────────────────────────────

interface FakePortState {
  _ctx: OwnerContext | null;
  _prepare: (intent: CommandIntent) => OperationPointer;
  _submit: (
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ) => Promise<EffectReceipt>;
  _readOp: (
    pointer: OperationPointer,
    signal: AbortSignal,
  ) => Promise<EffectReceipt>;
}

/**
 * The default fakes model a contract-conformant producer: an accepted launch
 * receipt carries a decodable selection; an accepted message or stop carries
 * none (a selection there is a protocol violation covered separately).
 */
function acceptedEcho(pointer: OperationPointer): EffectReceipt {
  return echoReceipt(pointer, "accepted", {
    ...(pointer.kind === "launch" ? { missionSelection: VALID_SELECTION } : {}),
  });
}

function makePort(overrides: Partial<FakePortState> = {}): FakePortState {
  return {
    _ctx: { principalScope: "scope-A", generation: "gen-1" },
    _prepare: vi.fn((intent: CommandIntent): OperationPointer => ({
      operationKey: `op-${intent.kind}-1`,
      kind: intent.kind,
      targetKey: intent.targetKey,
    })),
    _submit: vi.fn(
      async (
        pointer: OperationPointer,
        _intent: CommandIntent,
        _signal: AbortSignal,
      ): Promise<EffectReceipt> => acceptedEcho(pointer),
    ),
    _readOp: vi.fn(
      async (
        pointer: OperationPointer,
        _signal: AbortSignal,
      ): Promise<EffectReceipt> => acceptedEcho(pointer),
    ),
    ...overrides,
  } as FakePortState;
}

function buildPort(state: FakePortState): FiniteCommandPort {
  return {
    context: () => state._ctx,
    prepare: state._prepare,
    submit: state._submit,
    readOperation: state._readOp,
  };
}

/** A receipt that echoes the pointer it was asked about. */
function echoReceipt(
  pointer: OperationPointer,
  disposition: EffectReceipt["disposition"],
  extra: Partial<EffectReceipt> = {},
): EffectReceipt {
  return {
    operationKey: pointer.operationKey,
    kind: pointer.kind,
    targetKey: pointer.targetKey,
    disposition,
    ...extra,
  };
}

/** A selection that passes `normalizeSelection` strictly. */
const VALID_SELECTION: MissionSelection = {
  workRef: "WS:alpha",
  rootJobId: "JOB-123",
};

/**
 * Deferred submit so a test controls exactly when the receipt arrives. The
 * resolver is reached through a holder because the submit function only runs
 * once `begin()` has started the operation.
 */
function deferredSubmit(): {
  submitFn: (
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ) => Promise<EffectReceipt>;
  resolve: (r: EffectReceipt) => void;
  reject: (e: unknown) => void;
} {
  const holder: {
    resolve?: (r: EffectReceipt) => void;
    reject?: (e: unknown) => void;
  } = {};
  const submitFn = vi.fn(
    (_p: OperationPointer, _i: CommandIntent, _s: AbortSignal) =>
      new Promise<EffectReceipt>((res, rej) => {
        holder.resolve = res;
        holder.reject = rej;
      }),
  );
  return {
    submitFn: submitFn as unknown as (
      pointer: OperationPointer,
      intent: CommandIntent,
      signal: AbortSignal,
    ) => Promise<EffectReceipt>,
    resolve: (r: EffectReceipt) => holder.resolve?.(r),
    reject: (e: unknown) => holder.reject?.(e),
  };
}

/** Watch whether a promise has settled without awaiting it. */
function watchSettled(p: Promise<unknown>): { readonly settled: () => boolean } {
  let settled = false;
  void p.then(
    () => {
      settled = true;
    },
    () => {
      settled = true;
    },
  );
  return { settled: () => settled };
}

function expectLocalBusy(result: OperationState): void {
  expect(result.status).toBe("refused");
  expect(result.reason).toBe("OPERATION_BUSY");
  expect(result.pointer).toBeNull();
  expect(result).not.toHaveProperty("missionSelection");
}

// ── Test intents ───────────────────────────────────────────────────────────────

const LAUNCH_INTENT: CommandIntent = {
  kind: "launch",
  payload: { key: "value" },
  targetKey: null,
};

const MESSAGE_INTENT: CommandIntent = {
  kind: "message",
  payload: { text: "hi" },
  targetKey: "t-1",
};

const STOP_INTENT: CommandIntent = {
  kind: "stop",
  payload: {},
  targetKey: "t-1",
};

const BASE_POINTER: OperationPointer = {
  operationKey: "op-base",
  kind: "launch",
  targetKey: null,
};

/** What the default `prepare` mints for `LAUNCH_INTENT`. */
const SUBMITTED_POINTER: OperationPointer = {
  operationKey: "op-launch-1",
  kind: "launch",
  targetKey: null,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("OperationController", () => {
  describe("begin", () => {
    it("submits intent and transitions to accepted", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("accepted");
      expect(portState._submit).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledWith(LAUNCH_INTENT);
    });

    it("refuses when owner context is absent", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("OWNER_ABSENT");
      expect(portState._submit).not.toHaveBeenCalled();
      expect(portState._prepare).not.toHaveBeenCalled();
    });

    it("auth absent means no mutation: nothing written to the store", async () => {
      const { store, state } = makeStoreWithState();
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.begin(LAUNCH_INTENT);

      expect(state._writes).toHaveLength(0);
      expect(state._data.size).toBe(0);
    });

    it("store-write failure refuses without submit", async () => {
      const { store, state } = makeStoreWithState();
      state._storeWriteShouldFail = true;
      const submitSpy = vi.fn();
      const portState = makePort({ _submit: submitSpy });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("STORE_WRITE_FAILED");
      expect(submitSpy).not.toHaveBeenCalled();
    });

    it("writes the pointer before submit", async () => {
      const { store, state } = makeStoreWithState();
      const order: string[] = [];
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => {
          order.push("submit");
          return echoReceipt(pointer, "accepted");
        }),
      });
      const originalWrite = store.write.bind(store);
      store.write = (scope, pointer) => {
        order.push("write");
        originalWrite(scope, pointer);
      };
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.begin(LAUNCH_INTENT);

      expect(order).toEqual(["write", "submit"]);
    });

    it("same-intent duplicate begin is local OPERATION_BUSY; original continues", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const watch = watchSettled(p1);
      const p2 = await ctrl.begin(LAUNCH_INTENT);
      await Promise.resolve();

      expectLocalBusy(p2);
      expect(watch.settled()).toBe(false);
      expect(ctrl.getState().status).toBe("submitting");
      expect(ctrl.getState().pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledTimes(1);

      resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(r1.reason).toBe("ACCEPTED");
      expect(ctrl.getState().status).toBe("accepted");
      expect(submitFn).toHaveBeenCalledTimes(1);
    });

    it("mixed-kind/target begin is local OPERATION_BUSY (launch vs stop)", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const watch = watchSettled(p1);
      const p2 = await ctrl.begin(STOP_INTENT);
      const p3 = await ctrl.begin(MESSAGE_INTENT);
      await Promise.resolve();

      expectLocalBusy(p2);
      expectLocalBusy(p3);
      expect(watch.settled()).toBe(false);
      expect(ctrl.getState().status).toBe("submitting");
      expect(ctrl.getState().pointer).toEqual(SUBMITTED_POINTER);
      expect(ctrl.getState().reason).toBe("SUBMITTING");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledTimes(1);

      resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(r1.reason).toBe("ACCEPTED");
      expect(ctrl.getState().status).toBe("accepted");
      expect(submitFn).toHaveBeenCalledTimes(1);
    });

    it("different-payload begin is local OPERATION_BUSY; original continues", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const watch = watchSettled(p1);
      const p2 = await ctrl.begin({
        kind: "launch",
        payload: { different: true },
        targetKey: null,
      });
      await Promise.resolve();

      expectLocalBusy(p2);
      expect(watch.settled()).toBe(false);
      expect(ctrl.getState().status).toBe("submitting");
      expect(ctrl.getState().pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(submitFn).toHaveBeenCalledTimes(1);

      resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(ctrl.getState().status).toBe("accepted");
      expect(submitFn).toHaveBeenCalledTimes(1);
    });

    it("if store has pointer, begin returns checking requiring recover", async () => {
      const { store } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("checking");
      expect(result.pointer).toEqual(BASE_POINTER);
      expect(result.reason).toBe("PENDING_POINTER");
      expect(portState._submit).not.toHaveBeenCalled();
      expect(portState._prepare).not.toHaveBeenCalled();
    });

    it("a malformed stored hint never reaches the port", async () => {
      const { store } = makeStoreWithState();
      store.write("scope-A", { operationKey: "junk" } as OperationPointer);
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const began = await ctrl.begin(LAUNCH_INTENT);
      const recovered = await ctrl.recover();

      expect(began.status).toBe("idle");
      expect(began.reason).toBe("MALFORMED_POINTER");
      expect(recovered.status).toBe("idle");
      expect(portState._submit).not.toHaveBeenCalled();
      expect(portState._readOp).not.toHaveBeenCalled();
    });

    it("malformed pointer from prepare is refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: () => ({ operationKey: "", kind: "launch", targetKey: null }) as OperationPointer,
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("MALFORMED_POINTER");
    });

    it("prepare throwing is refused and never submitted", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: () => {
          throw new Error("prepare exploded");
        },
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("unsupported extra fields on a prepared pointer are refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: () =>
          ({ operationKey: "op-1", kind: "launch", targetKey: null, runtime: "x" }) as OperationPointer,
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("MALFORMED_POINTER");
    });

    it("wrong kind mismatch from prepare is refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: () => ({ operationKey: "op-1", kind: "stop", targetKey: null }),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("KIND_MISMATCH");
    });

    it("wrong target mismatch from prepare is refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: () => ({ operationKey: "op-1", kind: "launch", targetKey: "wrong-target" }),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("TARGET_MISMATCH");
    });

    it("empty targetKey is refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({ kind: "launch", payload: {}, targetKey: "" });

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("INVALID_TARGET");
    });

    it("unsupported intent kind is refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({
        kind: "restart" as OperationKind,
        payload: {},
        targetKey: null,
      });

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("INVALID_KIND");
    });

    it("non-object payload is refused", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({
        kind: "launch",
        payload: ["not", "an", "object"] as unknown as CommandIntent["payload"],
        targetKey: null,
      });

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("INVALID_PAYLOAD");
    });

    it("racing begin is local OPERATION_BUSY; original submit count stays 1", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      const portState = makePort({ _submit: first.submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const watch = watchSettled(p1);
      const p2 = await ctrl.begin(LAUNCH_INTENT);
      await Promise.resolve();

      expectLocalBusy(p2);
      expect(watch.settled()).toBe(false);
      expect(ctrl.getState().status).toBe("submitting");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);

      first.resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(ctrl.getState().status).toBe("accepted");
      expect(first.submitFn).toHaveBeenCalledTimes(1);
    });

    const KIND_PAIRS: ReadonlyArray<{ first: OperationKind; second: OperationKind }> = (
      ["launch", "message", "stop"] as const
    ).flatMap((first) =>
      (["launch", "message", "stop"] as const).map((second) => ({ first, second })),
    );

    it.each(KIND_PAIRS)(
      "in-flight $first begin refuses a concurrent $second begin",
      async ({ first, second }) => {
        const { store } = makeStoreWithState();
        const held = deferredSubmit();
        const portState = makePort({ _submit: held.submitFn });
        const ctrl = new OperationController(buildPort(portState), store);
        const firstIntent: CommandIntent = {
          kind: first,
          payload: { n: 1 },
          targetKey: first === "launch" ? null : "t-first",
        };
        const secondIntent: CommandIntent = {
          kind: second,
          payload: { n: 2 },
          targetKey: second === "launch" ? null : "t-second",
        };
        const submitted: OperationPointer = {
          operationKey: `op-${first}-1`,
          kind: first,
          targetKey: firstIntent.targetKey,
        };

        const p1 = ctrl.begin(firstIntent);
        const watch = watchSettled(p1);
        const p2 = await ctrl.begin(secondIntent);
        await Promise.resolve();

        expectLocalBusy(p2);
        expect(watch.settled()).toBe(false);
        expect(ctrl.getState().status).toBe("submitting");
        expect(ctrl.getState().pointer).toEqual(submitted);
        expect(store.read("scope-A")).toEqual(submitted);
        expect(held.submitFn).toHaveBeenCalledTimes(1);
        expect(portState._prepare).toHaveBeenCalledTimes(1);

        held.resolve(acceptedEcho(submitted));
        const r1 = await p1;
        expect(r1.status).toBe("accepted");
        expect(held.submitFn).toHaveBeenCalledTimes(1);
      },
    );

    it("changed-principal begin is local OPERATION_BUSY without leaking or submitting", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const watch = watchSettled(p1);
      portState._ctx = { principalScope: "scope-B", generation: "gen-1" };
      const p2 = await ctrl.begin(LAUNCH_INTENT);
      await Promise.resolve();

      expectLocalBusy(p2);
      expect(JSON.stringify(p2)).not.toContain("op-launch-1");
      expect(watch.settled()).toBe(false);
      expect(ctrl.getState().status).toBe("submitting");
      expect(ctrl.getState().pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-B")).toBeNull();
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledTimes(1);

      portState._ctx = { principalScope: "scope-A", generation: "gen-1" };
      resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(store.read("scope-A")).toBeNull();
      expect(store.read("scope-B")).toBeNull();
      expect(submitFn).toHaveBeenCalledTimes(1);
    });

    it("changed-generation begin is local OPERATION_BUSY without joining", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      portState._ctx = { principalScope: "scope-A", generation: "gen-2" };
      const p2 = await ctrl.begin(LAUNCH_INTENT);

      expectLocalBusy(p2);
      expect(ctrl.getState().status).toBe("submitting");
      expect(ctrl.getState().pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(submitFn).toHaveBeenCalledTimes(1);

      portState._ctx = { principalScope: "scope-A", generation: "gen-1" };
      resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(submitFn).toHaveBeenCalledTimes(1);
    });

    it("invalid intent still precedes the in-flight busy gate", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const bad = await ctrl.begin({
        kind: "restart" as OperationKind,
        payload: {},
        targetKey: null,
      });

      expect(bad.status).toBe("idle");
      expect(bad.reason).toBe("INVALID_KIND");
      expect(submitFn).toHaveBeenCalledTimes(1);

      resolve(acceptedEcho(SUBMITTED_POINTER));
      await p1;
    });

    it("owner absence still precedes the in-flight busy gate", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      portState._ctx = null;
      const absent = await ctrl.begin(LAUNCH_INTENT);

      expect(absent.status).toBe("idle");
      expect(absent.reason).toBe("OWNER_ABSENT");
      expect(submitFn).toHaveBeenCalledTimes(1);

      resolve(acceptedEcho(SUBMITTED_POINTER));
      await p1;
    });
  });

  describe("recover", () => {
    it("uses readOperation only, not submit", async () => {
      const { store } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      const readFn = vi.fn(async (pointer: OperationPointer) => acceptedEcho(pointer));
      const submitSpy = vi.fn();
      const portState = makePort({ _submit: submitSpy, _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("accepted");
      expect(readFn).toHaveBeenCalledTimes(1);
      expect(submitSpy).not.toHaveBeenCalled();
    });

    it("returns accepted when readOperation returns accepted", async () => {
      const { store } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      const portState = makePort({
        _readOp: vi.fn(async (pointer: OperationPointer) => acceptedEcho(pointer)),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("accepted");
      expect(result.pointer).toBeNull(); // accepted clears pointer
    });

    it("refuses when no pointer in store", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("RECOVER_NO_POINTER");
    });

    it("refuses when auth absent", async () => {
      const { store } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("OWNER_ABSENT");
      expect(portState._readOp).not.toHaveBeenCalled();
    });

    it("readOperation transport exception becomes unknown", async () => {
      const { store } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      const readFn = vi.fn(async () => {
        throw new Error("transport error");
      });
      const portState = makePort({ _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("unknown");
      expect(result.pointer).toEqual(BASE_POINTER);
      expect(result.reason).toBe("RECOVER_FAILED");
    });

    it("racing recover joins the in-flight read instead of reading twice", async () => {
      const { store } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      let resolveRead!: () => void;
      const readFn = vi.fn(
        (pointer: OperationPointer) =>
          new Promise<EffectReceipt>((res) => {
            resolveRead = () => res(echoReceipt(pointer, "unknown"));
          }),
      );
      const portState = makePort({ _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.recover();
      const p2 = ctrl.recover();
      resolveRead();
      const [r1, r2] = await Promise.all([p1, p2]);

      expect(readFn).toHaveBeenCalledTimes(1);
      expect(r1).toBe(r2);
    });

    it("same-owner recover still joins the in-flight begin", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const readFn = vi.fn();
      const portState = makePort({ _submit: submitFn, _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const recovered = ctrl.recover();
      resolve(acceptedEcho(SUBMITTED_POINTER));
      const [r1, r2] = await Promise.all([p1, recovered]);

      expect(r1).toBe(r2);
      expect(r1.status).toBe("accepted");
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(readFn).not.toHaveBeenCalled();
    });

    it("foreign-principal recover during in-flight is local OPERATION_BUSY without leaking", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const readFn = vi.fn();
      const portState = makePort({ _submit: submitFn, _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      const watch = watchSettled(p1);
      portState._ctx = { principalScope: "scope-B", generation: "gen-1" };
      const recovered = await ctrl.recover();
      await Promise.resolve();

      expectLocalBusy(recovered);
      expect(JSON.stringify(recovered)).not.toContain("op-launch-1");
      expect(recovered).not.toHaveProperty("missionSelection");
      expect(watch.settled()).toBe(false);
      expect(ctrl.getState().status).toBe("submitting");
      expect(ctrl.getState().pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-B")).toBeNull();
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(readFn).not.toHaveBeenCalled();

      resolve(acceptedEcho(SUBMITTED_POINTER));
      await p1;
    });

    it("changed-generation recover during in-flight is local OPERATION_BUSY without leaking", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const readFn = vi.fn();
      const portState = makePort({ _submit: submitFn, _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      portState._ctx = { principalScope: "scope-A", generation: "gen-2" };
      const recovered = await ctrl.recover();

      expectLocalBusy(recovered);
      expect(JSON.stringify(recovered)).not.toContain("op-launch-1");
      expect(ctrl.getState().status).toBe("submitting");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(readFn).not.toHaveBeenCalled();

      portState._ctx = { principalScope: "scope-A", generation: "gen-1" };
      resolve(acceptedEcho(SUBMITTED_POINTER));
      const r1 = await p1;
      expect(r1.status).toBe("accepted");
      expect(submitFn).toHaveBeenCalledTimes(1);
      expect(readFn).not.toHaveBeenCalled();
    });

    it("lost response then NEW controller recover uses readOperation only", async () => {
      const { store } = makeStoreWithInitial([
        ["scope-A", { operationKey: "op-lost", kind: "launch", targetKey: null }],
      ]);
      const readFn = vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "unknown"));
      const submitSpy = vi.fn();
      const portState = makePort({ _submit: submitSpy, _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("unknown");
      expect(result.pointer).toEqual({
        operationKey: "op-lost",
        kind: "launch",
        targetKey: null,
      });
      expect(readFn).toHaveBeenCalledTimes(1);
      expect(submitSpy).not.toHaveBeenCalled();
    });

    it("recover after sign-out keeps the pointer in the original scope", async () => {
      const { store, state } = makeStoreWithInitial([["scope-A", BASE_POINTER]]);
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.recover();

      expect(state._data.get("scope-A")).toEqual(BASE_POINTER);
      expect(state._writes).toHaveLength(0);
    });
  });

  describe("invalidate", () => {
    it("invalidate during in-flight retains the hint; a second begin does not submit", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      const portState = makePort({ _submit: first.submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);

      ctrl.invalidate();
      expect(ctrl.getState().status).toBe("idle");
      expect(ctrl.getState().reason).toBe("CLEARED");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);

      const again = await ctrl.begin(LAUNCH_INTENT);
      expect(again.status).toBe("checking");
      expect(again.reason).toBe("PENDING_POINTER");
      expect(again.pointer).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledTimes(1);

      first.resolve(acceptedEcho(SUBMITTED_POINTER));
      await pending;
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("clear with wrong pointer does not erase newer operation", async () => {
      const { store } = makeStoreWithState();
      const newPointer = { operationKey: "op-new", kind: "launch" as OperationKind, targetKey: null };
      store.write("scope-A", newPointer);
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      ctrl.invalidate();

      expect(store.read("scope-A")).toEqual(newPointer);
    });

    it("invalidate without pointer does nothing", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      ctrl.invalidate();

      expect(ctrl.getState().status).toBe("idle");
    });

    it("a terminal receipt cannot erase a pointer written after it started", async () => {
      const { store, state } = makeStoreWithState();
      const newer: OperationPointer = {
        operationKey: "op-newer",
        kind: "launch",
        targetKey: null,
      };
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      // A newer operation's hint lands in the store while the first is in flight.
      state._data.set("scope-A", newer);
      resolve(acceptedEcho(SUBMITTED_POINTER));
      await pending;

      expect(ctrl.getState().status).toBe("accepted");
      expect(store.read("scope-A")).toEqual(newer);
    });

    it("signing out before invalidate leaves the hint in its original scope", async () => {
      const { store, state } = makeStoreWithState();
      const pointer: OperationPointer = {
        operationKey: "op-kept",
        kind: "launch",
        targetKey: null,
      };
      store.write("scope-A", pointer);
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      ctrl.invalidate();

      expect(state._data.get("scope-A")).toEqual(pointer);
      // Only the seeded write: the controller added and removed nothing.
      expect(state._writes).toEqual([pointer]);
    });
  });

  describe("receipt validation", () => {
    it("malformed receipt becomes unknown with original pointer", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async () => ({ invalid: "receipt" }) as unknown as EffectReceipt),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.pointer).not.toBeNull();
    });

    it("unsupported extra fields on a receipt hold the pointer", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          ({ ...echoReceipt(pointer, "accepted"), runtime: "spawn-7" }) as EffectReceipt,
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("MALFORMED_RECEIPT");
      expect(result.pointer).not.toBeNull();
    });

    it("wrong operation-kind receipt remains unknown", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { kind: "stop" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("KIND_MISMATCH");
    });

    it("wrong target receipt remains unknown", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { targetKey: "wrong-target" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("TARGET_MISMATCH");
    });

    it("receipt mismatch remains unknown with original pointer", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async () =>
          echoReceipt({ operationKey: "op-wrong-key", kind: "launch", targetKey: null }, "accepted"),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("RECEIPT_MISMATCH");
      expect(result.pointer?.operationKey).toBe("op-launch-1");
    });

    it("arbitrary producer reason text is withheld from state", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "refused", { reason: "token expired for user chris@example.com" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("refused");
      expect(result.reason).toBe("REFUSED");
      expect(JSON.stringify(result)).not.toContain("chris@example.com");
      expect(JSON.stringify(result)).not.toContain("token expired");
    });

    it("allow-listed producer reason is never forwarded as the UI reason", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "refused", { reason: "OWNER_ABSENT" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("refused");
      expect(result.reason).toBe("REFUSED");
    });

    it("allow-listed producer reason on accepted message stays ACCEPTED", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: vi.fn((intent: CommandIntent): OperationPointer => ({
          operationKey: "op-message-1",
          kind: "message",
          targetKey: intent.targetKey,
        })),
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { reason: "OWNER_ABSENT" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({ kind: "message", payload: {}, targetKey: null });

      expect(result.status).toBe("accepted");
      expect(result.reason).toBe("ACCEPTED");
    });

    it("allow-listed producer reason on unknown disposition stays UNKNOWN_RECEIPT", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "unknown", { reason: "ACCEPTED" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("UNKNOWN_RECEIPT");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("unknown disposition retains pointer", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "unknown", { reason: "something went wrong" }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.pointer).not.toBeNull();
      expect(result.reason).not.toBe("something went wrong");
    });

    it("accepted disposition clears pointer via store", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("accepted");
      expect(store.read("scope-A")).toBeNull();
    });

    it("refused disposition clears pointer via store", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "refused")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("refused");
      expect(store.read("scope-A")).toBeNull();
    });

    it("transport exception becomes unknown and retains original pointer", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async () => {
          throw new Error("EXPLOIT: steal info");
        }),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.pointer).not.toBeNull();
      expect(result.reason).toBe("TRANSPORT_ERROR");
    });
  });

  describe("mission selection", () => {
    it("accepts a legitimate launch selection", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { missionSelection: VALID_SELECTION }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("accepted");
      expect(result).toHaveProperty("missionSelection", VALID_SELECTION);
      expect(store.read("scope-A")).toBeNull();
    });

    it("an accepted launch receipt with no selection is unknown, not accepted", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "accepted")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      // The launch is the selection-changing effect: with no selection to
      // publish, the outcome is unknown and the exact pointer is held.
      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_INVALID");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      expect(result).not.toHaveProperty("missionSelection");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("rejects a syntactically valid selection on a message receipt", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _prepare: vi.fn((intent: CommandIntent) => ({
          operationKey: "op-msg-1",
          kind: "message" as OperationKind,
          targetKey: intent.targetKey,
        })),
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { missionSelection: VALID_SELECTION }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({ kind: "message", payload: {}, targetKey: "ws:alpha" });

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_NOT_ALLOWED");
      // The selection must not be adopted, and the pointer must survive.
      expect(result.pointer?.kind).toBe("message");
      expect(store.read("scope-A")).not.toBeNull();
    });

    it("rejects a syntactically valid foreign root on a stop receipt", async () => {
      const { store } = makeStoreWithState();
      const foreign: MissionSelection = { workRef: "WS:other", rootJobId: "JOB-999" };
      const portState = makePort({
        _prepare: vi.fn((intent: CommandIntent) => ({
          operationKey: "op-stop-1",
          kind: "stop" as OperationKind,
          targetKey: intent.targetKey,
        })),
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { missionSelection: foreign }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({ kind: "stop", payload: {}, targetKey: "t-stop" });

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_NOT_ALLOWED");
      expect(store.read("scope-A")).not.toBeNull();
    });

    it("rejects a selection on a refused receipt", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "refused", { missionSelection: VALID_SELECTION }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_NOT_ALLOWED");
      expect(result.pointer).not.toBeNull();
    });

    it("rejects a selection on an unknown receipt", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "unknown", { missionSelection: VALID_SELECTION }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_NOT_ALLOWED");
    });

    it("wrong root selection is unknown and held, never a fabricated refusal", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", {
            // Lowercase workspace prefix fails `normalizeSelection`.
            missionSelection: { workRef: "ws:foo", rootJobId: "JOB-123" } as MissionSelection,
          }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      // The producer reported acceptance; the client cannot decode the root.
      // The effect may have happened, so this is not a refusal and the exact
      // hint survives for recover().
      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_INVALID");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("a selection with an extra field is unknown and held, not adopted", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", {
            missionSelection: { ...VALID_SELECTION, rootJobId2: "JOB-1" } as MissionSelection,
          }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("SELECTION_INVALID");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("a selection that is not even an object is malformed data, not a selection", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", {
            missionSelection: "WS:alpha/JOB-123" as unknown as MissionSelection,
          }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      // Structurally malformed: hold the pointer rather than invent a terminal
      // state from it.
      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("MALFORMED_RECEIPT");
      expect(result.pointer).not.toBeNull();
      expect(result).not.toHaveProperty("missionSelection");
    });

    it("an unknown receipt holding a selection can be recovered and resolved", async () => {
      const { store, state } = makeStoreWithState();
      const pointer: OperationPointer = {
        operationKey: "op-sel",
        kind: "launch",
        targetKey: null,
      };
      state._data.set("scope-A", pointer);
      let carrySelection = true;
      const readFn = vi.fn(async (p: OperationPointer) =>
        echoReceipt(p, carrySelection ? "unknown" : "accepted", {
          missionSelection: VALID_SELECTION,
        }),
      );
      const portState = makePort({ _submit: vi.fn(), _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const held = await ctrl.recover();
      carrySelection = false;
      const resolved = await ctrl.recover();

      expect(held.reason).toBe("SELECTION_NOT_ALLOWED");
      expect(resolved.status).toBe("accepted");
      expect(store.read("scope-A")).toBeNull();
    });
  });

  // ── Effect-uncertainty regression ──────────────────────────────────────────
  //
  // An accepted launch may only be published as accepted when it carries a
  // selection that `normalizeSelection` decodes. Absent or malformed, the
  // outcome is unknown and the exact pointer is held — the producer's launch
  // may have happened even though this client cannot decode the root, so a
  // refusal must never be fabricated from a decoder failure.
  describe("accepted launch requires a decodable selection", () => {
    interface Row {
      readonly name: string;
      readonly kind: OperationKind;
      readonly disposition: EffectReceipt["disposition"];
      readonly selection: unknown;
      readonly wantStatus: OperationState["status"];
      readonly wantReason: string;
      readonly wantHintRetained: boolean;
    }

    const rows: readonly Row[] = [
      {
        name: "accepted launch / selection absent",
        kind: "launch",
        disposition: "accepted",
        selection: undefined,
        wantStatus: "unknown",
        wantReason: "SELECTION_INVALID",
        wantHintRetained: true,
      },
      {
        name: "accepted launch / selection not decodable (lowercase prefix)",
        kind: "launch",
        disposition: "accepted",
        selection: { workRef: "ws:foo", rootJobId: "JOB-123" },
        wantStatus: "unknown",
        wantReason: "SELECTION_INVALID",
        wantHintRetained: true,
      },
      {
        name: "accepted launch / selection fields empty",
        kind: "launch",
        disposition: "accepted",
        selection: { workRef: "", rootJobId: "" },
        wantStatus: "unknown",
        wantReason: "SELECTION_INVALID",
        wantHintRetained: true,
      },
      {
        name: "accepted launch / valid selection",
        kind: "launch",
        disposition: "accepted",
        selection: VALID_SELECTION,
        wantStatus: "accepted",
        wantReason: "ACCEPTED",
        wantHintRetained: false,
      },
      {
        name: "accepted message / selection present",
        kind: "message",
        disposition: "accepted",
        selection: VALID_SELECTION,
        wantStatus: "unknown",
        wantReason: "SELECTION_NOT_ALLOWED",
        wantHintRetained: true,
      },
      {
        name: "accepted stop / selection present",
        kind: "stop",
        disposition: "accepted",
        selection: VALID_SELECTION,
        wantStatus: "unknown",
        wantReason: "SELECTION_NOT_ALLOWED",
        wantHintRetained: true,
      },
      {
        name: "refused launch / selection present",
        kind: "launch",
        disposition: "refused",
        selection: VALID_SELECTION,
        wantStatus: "unknown",
        wantReason: "SELECTION_NOT_ALLOWED",
        wantHintRetained: true,
      },
      {
        name: "unknown launch / selection present",
        kind: "launch",
        disposition: "unknown",
        selection: VALID_SELECTION,
        wantStatus: "unknown",
        wantReason: "SELECTION_NOT_ALLOWED",
        wantHintRetained: true,
      },
      {
        name: "refused launch / selection absent stays a refusal",
        kind: "launch",
        disposition: "refused",
        selection: undefined,
        wantStatus: "refused",
        wantReason: "REFUSED",
        wantHintRetained: false,
      },
      {
        name: "accepted message / selection absent stays accepted",
        kind: "message",
        disposition: "accepted",
        selection: undefined,
        wantStatus: "accepted",
        wantReason: "ACCEPTED",
        wantHintRetained: false,
      },
    ];

    it.each(rows)("$name -> $wantStatus/$wantReason", async (row) => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(
          async (pointer: OperationPointer): Promise<EffectReceipt> =>
            echoReceipt(pointer, row.disposition, {
              ...(row.selection === undefined
                ? {}
                : { missionSelection: row.selection as MissionSelection }),
            }),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin({
        kind: row.kind,
        payload: {},
        targetKey: null,
      });

      expect(result.status).toBe(row.wantStatus);
      expect(result.reason).toBe(row.wantReason);
      expect(portState._submit).toHaveBeenCalledTimes(1);
      if (row.wantHintRetained) {
        // The exact pending pointer is held, both in state and in the store.
        expect(result.pointer).toEqual({
          operationKey: `op-${row.kind}-1`,
          kind: row.kind,
          targetKey: null,
        });
        expect(store.read("scope-A")).toEqual(result.pointer);
      } else {
        expect(store.read("scope-A")).toBeNull();
      }
    });

    it("begin again after a held launch never submits a second operation", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "accepted")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const held = await ctrl.begin(LAUNCH_INTENT);
      expect(held.status).toBe("unknown");

      const again = await ctrl.begin(LAUNCH_INTENT);

      expect(again.status).toBe("checking");
      expect(again.reason).toBe("PENDING_POINTER");
      expect(again.pointer).toEqual(SUBMITTED_POINTER);
      expect(portState._submit).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledTimes(1);
    });

    it("recover uses readOperation only and accepts a corrected matching receipt", async () => {
      const { store } = makeStoreWithState();
      let corrected = false;
      const portState = makePort({
        _submit: vi.fn(
          async (pointer: OperationPointer): Promise<EffectReceipt> =>
            echoReceipt(pointer, "accepted", corrected ? { missionSelection: VALID_SELECTION } : {}),
        ),
        _readOp: vi.fn(
          async (pointer: OperationPointer): Promise<EffectReceipt> =>
            echoReceipt(pointer, "accepted", corrected ? { missionSelection: VALID_SELECTION } : {}),
        ),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const held = await ctrl.begin(LAUNCH_INTENT);
      expect(held.reason).toBe("SELECTION_INVALID");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);

      corrected = true;
      const resolved = await ctrl.recover();

      expect(resolved.status).toBe("accepted");
      expect(resolved).toHaveProperty("missionSelection", VALID_SELECTION);
      expect(portState._submit).toHaveBeenCalledTimes(1);
      expect(portState._readOp).toHaveBeenCalledTimes(1);
      // The exact hint is cleared only by the accepting resolution.
      expect(store.read("scope-A")).toBeNull();
    });

    it("recover that still sees no selection stays unknown and held", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "accepted")),
        _readOp: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "accepted")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.begin(LAUNCH_INTENT);
      const still = await ctrl.recover();

      expect(still.status).toBe("unknown");
      expect(still.reason).toBe("SELECTION_INVALID");
      expect(still.pointer).toEqual(SUBMITTED_POINTER);
      expect(portState._submit).toHaveBeenCalledTimes(1);
      expect(portState._readOp).toHaveBeenCalledTimes(1);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });
  });

  describe("auth/target epoch races", () => {
    it("A-B-A: generation change mid-flight suppresses the receipt and keeps the hint", async () => {
      const { store } = makeStoreWithState();
      let generation = "gen-A";
      const portState = makePort({
        _ctx: {
          principalScope: "scope-A",
          get generation() {
            return generation;
          },
        },
        _submit: vi.fn(async (pointer: OperationPointer) => {
          // The authentication epoch rolls over while the operation is in flight.
          generation = "gen-B";
          return echoReceipt(pointer, "accepted");
        }),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("EPOCH_CHANGED");
      expect(result.pointer?.operationKey).toBe("op-launch-1");
      expect(store.read("scope-A")).not.toBeNull();
      expect(ctrl.getState().status).toBe("unknown");
    });

    it("A-B-A: the retained hint is still recoverable under the new epoch", async () => {
      const { store } = makeStoreWithState();
      let generation = "gen-A";
      const ctxObject: OwnerContext = {
        principalScope: "scope-A",
        get generation() {
          return generation;
        },
      };
      const portState = makePort({
        _ctx: ctxObject,
        _submit: vi.fn(async (pointer: OperationPointer) => {
          generation = "gen-B";
          return echoReceipt(pointer, "accepted");
        }),
        _readOp: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "refused")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.begin(LAUNCH_INTENT);
      const recovered = await ctrl.recover();

      expect(recovered.status).toBe("refused");
      expect(store.read("scope-A")).toBeNull();
    });

    it("a submit aborted by invalidate does not publish and retains the hint", async () => {
      const { store } = makeStoreWithState();
      let rejectSubmit!: (e: Error) => void;
      const submitFn = vi.fn(
        (_p: OperationPointer, _i: CommandIntent, signal: AbortSignal) =>
          new Promise<EffectReceipt>((_res, rej) => {
            rejectSubmit = rej;
            signal.addEventListener("abort", () =>
              rej(new Error(`aborted: ${signal.reason}`)),
            );
          }),
      );
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      ctrl.invalidate();
      // The port surfaces the abort as a rejection after invalidate() ran.
      rejectSubmit(new Error("The operation was aborted"));

      await pending;

      expect(ctrl.getState().status).toBe("idle");
      expect(ctrl.getState().reason).toBe("CLEARED");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(submitFn).toHaveBeenCalledTimes(1);

      const again = await ctrl.begin(LAUNCH_INTENT);
      expect(again.status).toBe("checking");
      expect(again.reason).toBe("PENDING_POINTER");
      expect(submitFn).toHaveBeenCalledTimes(1);
    });

    it("a recover aborted by invalidate does not publish and retains the hint", async () => {
      const { store, state } = makeStoreWithState();
      const pointer: OperationPointer = {
        operationKey: "op-old",
        kind: "launch",
        targetKey: null,
      };
      store.write("scope-A", pointer);
      let rejectRead!: (e: Error) => void;
      const readFn = vi.fn(
        (_p: OperationPointer, signal: AbortSignal) =>
          new Promise<EffectReceipt>((_res, rej) => {
            rejectRead = rej;
            signal.addEventListener("abort", () => rej(new Error("aborted")));
          }),
      );
      const portState = makePort({ _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.recover();
      ctrl.invalidate();
      rejectRead(new Error("The operation was aborted"));

      await pending;

      expect(ctrl.getState().status).toBe("idle");
      expect(ctrl.getState().reason).toBe("CLEARED");
      expect(state._data.get("scope-A")).toEqual(pointer);
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("principal change mid-flight keeps the original scope's pointer", async () => {
      const { store, state } = makeStoreWithState();
      const portState = makePort({
        _ctx: { principalScope: "scope-A", generation: "gen-1" },
        _submit: vi.fn(async (pointer: OperationPointer) => {
          portState._ctx = { principalScope: "scope-B", generation: "gen-1" };
          return echoReceipt(pointer, "accepted");
        }),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.reason).toBe("EPOCH_CHANGED");
      expect(state._data.get("scope-A")).not.toBeNull();
    });

    it("signout refusal: signed-out state refuses mutation", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("OWNER_ABSENT");
    });

    it("in-flight target change plus stale success keeps the original-scope hint", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      const portState = makePort({ _submit: first.submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      ctrl.invalidate();
      first.resolve(acceptedEcho(SUBMITTED_POINTER));
      await pending;

      expect(ctrl.getState().status).toBe("idle");
      expect(ctrl.getState().reason).toBe("CLEARED");
      expect(ctrl.getState()).not.toHaveProperty("missionSelection");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);
    });

    it("in-flight target change plus stale failure keeps the original-scope hint", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      const portState = makePort({ _submit: first.submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      ctrl.invalidate();
      first.reject(new Error("producer failed after abort"));
      await pending;

      expect(ctrl.getState().status).toBe("idle");
      expect(ctrl.getState().reason).toBe("CLEARED");
      expect(JSON.stringify(ctrl.getState())).not.toContain("producer failed");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);

      const again = await ctrl.begin(LAUNCH_INTENT);
      expect(again.status).toBe("checking");
      expect(again.reason).toBe("PENDING_POINTER");
      expect(first.submitFn).toHaveBeenCalledTimes(1);
    });

    it("same-principal begin after invalidate plus ABA generation still does not submit", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      let generation = "gen-A";
      const ctxObject: OwnerContext = {
        principalScope: "scope-A",
        get generation() {
          return generation;
        },
      };
      const portState = makePort({ _ctx: ctxObject, _submit: first.submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      expect(first.submitFn).toHaveBeenCalledTimes(1);

      ctrl.invalidate();
      generation = "gen-B";
      generation = "gen-C";

      const again = await ctrl.begin(LAUNCH_INTENT);
      expect(again.status).toBe("checking");
      expect(again.reason).toBe("PENDING_POINTER");
      expect(again.pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(portState._prepare).toHaveBeenCalledTimes(1);

      first.resolve(acceptedEcho(SUBMITTED_POINTER));
      await pending;
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);
    });

    it("only readOperation recovery clears the exact terminal hint after invalidate", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      const readFn = vi.fn(async (pointer: OperationPointer) => acceptedEcho(pointer));
      const portState = makePort({ _submit: first.submitFn, _readOp: readFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      ctrl.invalidate();
      first.reject(new Error("aborted"));
      await pending;

      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(readFn).not.toHaveBeenCalled();

      const recovered = await ctrl.recover();

      expect(recovered.status).toBe("accepted");
      expect(recovered.reason).toBe("ACCEPTED");
      expect(store.read("scope-A")).toBeNull();
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(readFn).toHaveBeenCalledTimes(1);
      expect(readFn).toHaveBeenCalledWith(SUBMITTED_POINTER, expect.any(AbortSignal));
    });
  });

  describe("scope isolation", () => {
    it("different principal scope has isolated pointer", async () => {
      const { store } = makeStoreWithInitial([
        ["scope-A", { operationKey: "op-A", kind: "launch", targetKey: null }],
      ]);
      const portState = makePort({
        _ctx: { principalScope: "scope-B", generation: "gen-1" },
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("accepted");
      expect(store.read("scope-A")).not.toBeNull();
    });

    it("recovering under a different scope does not read the original scope", async () => {
      const { store } = makeStoreWithInitial([
        ["scope-A", { operationKey: "op-A", kind: "launch", targetKey: null }],
      ]);
      const portState = makePort({
        _ctx: { principalScope: "scope-B", generation: "gen-1" },
        _readOp: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "accepted")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("RECOVER_NO_POINTER");
      expect(portState._readOp).not.toHaveBeenCalled();
      expect(store.read("scope-A")).not.toBeNull();
    });
  });

  describe("getState", () => {
    it("returns current state", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      expect(ctrl.getState().status).toBe("idle");
      const before: OperationState = ctrl.getState();
      await ctrl.begin(LAUNCH_INTENT);

      expect(ctrl.getState().status).toBe("accepted");
      expect(before.status).toBe("idle");
    });

    it("never exposes the intent payload", async () => {
      const { store, state } = makeStoreWithState();
      const secret = { apiKey: "sk-secret-value" };
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.begin({ kind: "launch", payload: secret, targetKey: null });

      expect(JSON.stringify(ctrl.getState())).not.toContain("sk-secret-value");
      for (const written of state._writes) {
        expect(JSON.stringify(written)).not.toContain("sk-secret-value");
      }
      expect(JSON.stringify(state._writes)).not.toContain("payload");
    });
  });
});
