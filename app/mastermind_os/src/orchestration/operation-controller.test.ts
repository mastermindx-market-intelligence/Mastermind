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
  _storeReserveShouldFail: boolean;
  _storeReadShouldFail: boolean;
  _storeClearShouldFail: boolean;
  _data: Map<string, OperationPointer>;
  /** Every pointer the store was asked to reserve, for privacy assertions. */
  _reservations: Array<OperationPointer>;
  /** Every read the store was asked, in order. */
  _reads: Array<string>;
  /** Every clear the store was asked. */
  _clears: Array<OperationPointer>;
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
    _storeReserveShouldFail: false,
    _storeReadShouldFail: false,
    _storeClearShouldFail: false,
    _data: new Map(),
    _reservations: [],
    _reads: [],
    _clears: [],
  };
  const store: PendingPointerStore = {
    read: (scope) => {
      state._reads.push(scope);
      if (state._storeReadShouldFail) throw new Error("store read failed");
      return state._data.get(scope) ?? null;
    },
    reserve: (scope, pointer) => {
      if (state._storeReserveShouldFail) throw new Error("store reserve failed");
      // Reserve never overwrites — even when the existing pointer exactly
      // equals the incoming one. The caller joins the observation, never
      // submits a second effect.
      const existing = state._data.get(scope);
      if (existing) return { reserved: false, pointer: existing };
      state._data.set(scope, pointer);
      state._reservations.push(pointer);
      return { reserved: true };
    },
    clearIfEqual: (scope, pointer) => {
      state._clears.push(pointer);
      if (state._storeClearShouldFail) throw new Error("store clear failed");
      const existing = state._data.get(scope);
      if (existing && samePointer(existing, pointer)) {
        state._data.delete(scope);
        return true;
      }
      return false;
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

      expect(state._reservations).toHaveLength(0);
      expect(state._data.size).toBe(0);
    });

    it("store-reserve failure refuses without submit", async () => {
      const { store, state } = makeStoreWithState();
      state._storeReserveShouldFail = true;
      const submitSpy = vi.fn();
      const portState = makePort({ _submit: submitSpy });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("STORE_WRITE_FAILED");
      expect(submitSpy).not.toHaveBeenCalled();
    });

    it("reserves the pointer before submit", async () => {
      const { store, state } = makeStoreWithState();
      const order: string[] = [];
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => {
          order.push("submit");
          return echoReceipt(pointer, "accepted");
        }),
      });
      const originalReserve = store.reserve.bind(store);
      store.reserve = ((scope: string, pointer: OperationPointer, signal?: AbortSignal) => {
        order.push("reserve");
        return originalReserve(scope, pointer, signal);
      }) as PendingPointerStore["reserve"];
      const ctrl = new OperationController(buildPort(portState), store);

      await ctrl.begin(LAUNCH_INTENT);

      expect(order).toEqual(["reserve", "submit"]);
      expect(state._reservations).toHaveLength(1);
    });

    it("same-intent duplicate begin is local OPERATION_BUSY; original continues", async () => {
      const { store } = makeStoreWithState();
      const { submitFn, resolve } = deferredSubmit();
      const portState = makePort({ _submit: submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const p1 = ctrl.begin(LAUNCH_INTENT);
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      // Seed via the test fixture's underlying map: the public API is now
      // read/reserve/clearIfEqual, and reserve refuses to overwrite, so
      // corrupt pointers can be set up only through the underlying state.
      store.read = ((scope: string) => {
        if (scope === "scope-A") return { operationKey: "junk" } as unknown as OperationPointer;
        return null;
      }) as PendingPointerStore["read"];
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      const p2 = ctrl.recover();
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      const recovered = ctrl.recover();
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      // Recover only reads; no reservation, no clear.
      expect(state._reservations).toHaveLength(0);
      expect(state._clears).toHaveLength(0);
    });
  });

  describe("invalidate", () => {
    it("invalidate during in-flight retains the hint; a second begin does not submit", async () => {
      const { store } = makeStoreWithState();
      const first = deferredSubmit();
      const portState = makePort({ _submit: first.submitFn });
      const ctrl = new OperationController(buildPort(portState), store);

      const pending = ctrl.begin(LAUNCH_INTENT);
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      expect(first.submitFn).toHaveBeenCalledTimes(1);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);

      ctrl.invalidate();
      expect(ctrl.getState().status).toBe("idle");
      expect(ctrl.getState().reason).toBe("CLEARED");
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);

      const again = await ctrl.begin(LAUNCH_INTENT);
      expectLocalBusy(again);
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
      store.reserve("scope-A", newPointer);
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      // A newer operation's hint lands in the store while the first is in flight.
      state._data.set("scope-A", newer);
      resolve(acceptedEcho(SUBMITTED_POINTER));
      await pending;

      expect(ctrl.getState().status).toBe("unknown");
      expect(store.read("scope-A")).toEqual(newer);
    });

    it("signing out before invalidate leaves the hint in its original scope", async () => {
      const { store, state } = makeStoreWithState();
      const pointer: OperationPointer = {
        operationKey: "op-kept",
        kind: "launch",
        targetKey: null,
      };
      state._data.set("scope-A", pointer);
      const portState = makePort({ _ctx: null });
      const ctrl = new OperationController(buildPort(portState), store);

      ctrl.invalidate();

      expect(state._data.get("scope-A")).toEqual(pointer);
      // Only the seeded pointer is in the store; the controller reserved
      // nothing and cleared nothing.
      expect(state._reservations).toHaveLength(0);
      expect(state._clears).toHaveLength(0);
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

      expect(again).toMatchObject({ status: "checking", reason: "PENDING_POINTER", pointer: SUBMITTED_POINTER });
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

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("EPOCH_CHANGED");
      expect(result.pointer).toBeNull();
      expect(store.read("scope-A")).not.toBeNull();
      expect(ctrl.getState().status).toBe("idle");
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      state._data.set("scope-A", pointer);
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
      expect(first.submitFn).toHaveBeenCalledTimes(1);

      ctrl.invalidate();
      generation = "gen-B";
      generation = "gen-C";

      const again = await ctrl.begin(LAUNCH_INTENT);
      expectLocalBusy(again);
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
      await new Promise<void>((resolve) => setTimeout(resolve, 0));
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
      for (const reserved of state._reservations) {
        expect(JSON.stringify(reserved)).not.toContain("sk-secret-value");
      }
      expect(JSON.stringify(state._reservations)).not.toContain("payload");
    });
  });

  // ── Async durability boundary ─────────────────────────────────────────────
  //
  // The store is now a three-operation durability boundary (read / reserve /
  // clearIfEqual) instead of a sync read/write/clear. These tests cover what
  // each operation must and must not let the controller do, and the order in
  // which the controller must fence, fence, and commit.
  describe("async durability boundary", () => {
    it("read throwing is LOCAL_UNAVAILABLE: zero prepare, zero submit, no clear", async () => {
      const { store, state } = makeStoreWithState();
      state._storeReadShouldFail = true;
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("LOCAL_UNAVAILABLE");
      expect(portState._prepare).not.toHaveBeenCalled();
      expect(portState._submit).not.toHaveBeenCalled();
      expect(state._reservations).toHaveLength(0);
      expect(state._clears).toHaveLength(0);
    });

    it("read returning a corrupt pointer is MALFORMED_POINTER: zero prepare, zero submit", async () => {
      const { store, state } = makeStoreWithState();
      store.read = (() => ({ operationKey: "junk" }) as unknown as OperationPointer) as PendingPointerStore["read"];
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("MALFORMED_POINTER");
      expect(portState._prepare).not.toHaveBeenCalled();
      expect(portState._submit).not.toHaveBeenCalled();
      expect(state._reservations).toHaveLength(0);
    });

    it("deferred reserve keeps submit at zero until the reserve commits", async () => {
      const { store } = makeStoreWithState();
      let commitReserve!: () => void;
      const pending = new Promise<void>((res) => {
        commitReserve = res;
      });
      const originalReserve = store.reserve.bind(store);
      store.reserve = ((scope: string, pointer: OperationPointer, signal?: AbortSignal) => {
        return pending.then(() => originalReserve(scope, pointer, signal));
      }) as PendingPointerStore["reserve"];

      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const begin = ctrl.begin(LAUNCH_INTENT);
      // Yield to let begin run to the await on reserve.
      await Promise.resolve();
      await Promise.resolve();
      expect(portState._submit).not.toHaveBeenCalled();

      commitReserve();
      // Allow the now-pending reserve to settle through the original fixture.
      await new Promise<void>((res) => {
        queueMicrotask(res);
      });
      await begin;

      expect(portState._submit).toHaveBeenCalledTimes(1);
    });

    it("competing controllers — reserve is atomic, at most one submit", async () => {
      // Two controllers share an in-memory store. Each tries to begin at the
      // same time with a different intent: only the reservation winner
      // reaches port.submit. The loser must report PENDING_POINTER and never
      // hit submit.
      const sharedData = new Map<string, OperationPointer>();
      const sharedStore: PendingPointerStore = {
        read: (scope) => sharedData.get(scope) ?? null,
        reserve: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing) return { reserved: false, pointer: existing };
          sharedData.set(scope, pointer);
          return { reserved: true };
        },
        clearIfEqual: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing && samePointer(existing, pointer)) {
            sharedData.delete(scope);
            return true;
          }
          return false;
        },
      };

      const portA = makePort({
        _prepare: vi.fn(() => ({ operationKey: "op-A", kind: "launch" as OperationKind, targetKey: null })),
      });
      const portB = makePort({
        _prepare: vi.fn(() => ({ operationKey: "op-B", kind: "launch" as OperationKind, targetKey: null })),
      });
      const ctrlA = new OperationController(buildPort(portA), sharedStore);
      const ctrlB = new OperationController(buildPort(portB), sharedStore);

      // Both begin simultaneously. Only one reserve commits.
      const [resA, resB] = await Promise.all([
        ctrlA.begin(LAUNCH_INTENT),
        ctrlB.begin(LAUNCH_INTENT),
      ]);

      const submissions = [vi.mocked(portA._submit).mock.calls.length, vi.mocked(portB._submit).mock.calls.length];
      const totalSubmits = submissions[0] + submissions[1];
      expect(totalSubmits).toBe(1);

      const winner = totalSubmits === 1 ? (submissions[0] === 1 ? resA : resB) : null;
      const loser = totalSubmits === 1 ? (submissions[0] === 0 ? resA : resB) : null;

      // Whichever controller won reports accepted (or its own terminal state);
      // the loser reports checking/PENDING_POINTER with the winner's pointer.
      expect(winner).not.toBeNull();
      expect(loser).not.toBeNull();
      expect(loser!.status).toBe("checking");
      expect(loser!.reason).toBe("PENDING_POINTER");
      expect(loser!.pointer).toMatchObject({
        operationKey: winner!.status === "accepted" ? (vi.mocked(portA._submit).mock.calls.length ? "op-A" : "op-B") : (loser!.pointer?.operationKey ?? null),
      });
      // The accepted winner has atomically cleared its own pointer.
      expect(sharedData.size).toBe(0);
    });

    it("occupied equal pointer in store -> checking, zero new submit", async () => {
      const { store } = makeStoreWithInitial([["scope-A", SUBMITTED_POINTER]]);
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("checking");
      expect(result.reason).toBe("PENDING_POINTER");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      expect(portState._prepare).not.toHaveBeenCalled();
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("occupied different pointer in store -> checking, zero new submit", async () => {
      const foreign: OperationPointer = {
        operationKey: "op-other",
        kind: "launch",
        targetKey: null,
      };
      const { store } = makeStoreWithInitial([["scope-A", foreign]]);
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("checking");
      expect(result.reason).toBe("PENDING_POINTER");
      expect(result.pointer).toEqual(foreign);
      expect(portState._prepare).not.toHaveBeenCalled();
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("reserve returning a different pointer -> checking, zero new submit", async () => {
      // Reserve loses the race to a different pointer (e.g., another
      // controller's reserve committed between our read and our reserve).
      const foreign: OperationPointer = {
        operationKey: "op-other",
        kind: "launch",
        targetKey: null,
      };
      const { store } = makeStoreWithState();
      store.reserve = ((scope: string, _pointer: OperationPointer, _signal?: AbortSignal) => {
        return { reserved: false as const, pointer: foreign };
      }) as PendingPointerStore["reserve"];
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("checking");
      expect(result.reason).toBe("PENDING_POINTER");
      expect(result.pointer).toEqual(foreign);
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("late invalidation during read suppresses every later publish", async () => {
      const { store } = makeStoreWithState();
      const readStart = deferredSubmit();
      store.read = ((scope: string) => {
        // Synchronously invalidate while the read is "in flight" by calling
        // ctrl.invalidate() from the host store callback.
        ctrl.invalidate();
        return null;
      }) as PendingPointerStore["read"];
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("CLEARED");
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("late invalidation during reserve suppresses submit", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);
      // Override reserve to invalidate before returning.
      const originalReserve = store.reserve.bind(store);
      store.reserve = ((scope: string, p: OperationPointer, signal?: AbortSignal) => {
        ctrl.invalidate();
        return originalReserve(scope, p, signal);
      }) as PendingPointerStore["reserve"];

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("CLEARED");
      expect(portState._submit).not.toHaveBeenCalled();
    });

    it("late invalidation during submit suppresses publish; hint is durable", async () => {
      const { store } = makeStoreWithState();
      let invalidateFromSubmit!: () => void;
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => {
          invalidateFromSubmit();
          return echoReceipt(pointer, "accepted");
        }),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const begin = ctrl.begin(LAUNCH_INTENT);
      // Submit hasn't been invoked yet; install the invalidator and let it
      // run synchronously when submit is called below.
      invalidateFromSubmit = () => ctrl.invalidate();
      const result = await begin;

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("CLEARED");
      // The reservation is durable, so the hint remains in the store even
      // though the receipt was suppressed.
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("late invalidation during clear suppresses terminal publish", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);
      const originalClear = store.clearIfEqual.bind(store);
      store.clearIfEqual = ((scope: string, pointer: OperationPointer, signal?: AbortSignal) => {
        // Invalidate from inside the host store callback for the clear.
        ctrl.invalidate();
        return originalClear(scope, pointer, signal);
      }) as PendingPointerStore["clearIfEqual"];

      const result = await ctrl.begin(LAUNCH_INTENT);

      // The receipt was accepted and clearIfEqual returned true, but the
      // controller was invalidated during clear — so the UI sees CLEARED,
      // not ACCEPTED. The hint may have been cleared by the store already
      // (durable effect), and the in-flight slot joins through the await.
      expect(result.status).toBe("idle");
      expect(result.reason).toBe("CLEARED");
      expect(store.read("scope-A")).toBeNull();
    });

    it("clearIfEqual returning false on an accepted receipt holds unknown", async () => {
      const { store } = makeStoreWithState();
      // Make clearIfEqual return false even though the receipt is accepted.
      store.clearIfEqual = (() => false) as PendingPointerStore["clearIfEqual"];
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      // Terminal receipt, but the clear said false: we don't know the state.
      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("UNKNOWN_RECEIPT");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      // The hint remains — the next recover() can resolve it.
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("clearIfEqual rejecting on a refused receipt holds unknown", async () => {
      const { store } = makeStoreWithState();
      store.clearIfEqual = (() => {
        throw new Error("store write conflict");
      }) as PendingPointerStore["clearIfEqual"];
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "refused")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("UNKNOWN_RECEIPT");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("clearIfEqual returning false on a refused receipt holds unknown", async () => {
      const { store } = makeStoreWithState();
      store.clearIfEqual = (() => false) as PendingPointerStore["clearIfEqual"];
      const portState = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "refused")),
      });
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.begin(LAUNCH_INTENT);

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("UNKNOWN_RECEIPT");
      expect(result.pointer).toEqual(SUBMITTED_POINTER);
      expect(store.read("scope-A")).toEqual(SUBMITTED_POINTER);
    });

    it("lost reply + new controller recover is status-only, no second submit", async () => {
      // First controller submits, gets an unknown receipt, holds the pointer.
      // A brand-new controller (different instance, same store) recovers
      // through readOperation only — never submits.
      const sharedData = new Map<string, OperationPointer>();
      const sharedStore: PendingPointerStore = {
        read: (scope) => sharedData.get(scope) ?? null,
        reserve: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing) return { reserved: false, pointer: existing };
          sharedData.set(scope, pointer);
          return { reserved: true };
        },
        clearIfEqual: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing && samePointer(existing, pointer)) {
            sharedData.delete(scope);
            return true;
          }
          return false;
        },
      };
      const portA = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "unknown")),
        _readOp: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "unknown")),
      });
      const portB = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => echoReceipt(pointer, "unknown")),
        _readOp: vi.fn(async (pointer: OperationPointer) =>
          echoReceipt(pointer, "accepted", { missionSelection: VALID_SELECTION }),
        ),
      });

      const ctrlA = new OperationController(buildPort(portA), sharedStore);
      const beginA = await ctrlA.begin(LAUNCH_INTENT);
      expect(beginA.status).toBe("unknown");
      expect(beginA.reason).toBe("UNKNOWN_RECEIPT");
      expect(portA._submit).toHaveBeenCalledTimes(1);

      // New controller, same store: recover must use readOperation only.
      const ctrlB = new OperationController(buildPort(portB), sharedStore);
      const recovered = await ctrlB.recover();

      expect(recovered.status).toBe("accepted");
      expect(recovered).toHaveProperty("missionSelection", VALID_SELECTION);
      expect(portB._submit).not.toHaveBeenCalled();
      expect(portB._readOp).toHaveBeenCalledTimes(1);
      // Only one submit ever happened (from the first controller).
      expect(portA._submit).toHaveBeenCalledTimes(1);
      // And the hint is cleared by the recovering readOperation's success.
      expect(sharedStore.read("scope-A")).toBeNull();
    });

    it("clearIfEqual does not erase a pointer that was overwritten by a newer reservation", async () => {
      // The first controller's submit returned accepted. Before its
      // clearIfEqual ran, a new controller reserved a different pointer in
      // the same scope. The exact-pointer check must return false; the UI
      // holds unknown; the newer pointer survives.
      const sharedData = new Map<string, OperationPointer>();
      const sharedStore: PendingPointerStore = {
        read: (scope) => sharedData.get(scope) ?? null,
        reserve: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing) return { reserved: false, pointer: existing };
          sharedData.set(scope, pointer);
          return { reserved: true };
        },
        clearIfEqual: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing && samePointer(existing, pointer)) {
            sharedData.delete(scope);
            return true;
          }
          return false;
        },
      };
      let overwrite!: () => void;
      const portA = makePort({
        _submit: vi.fn(async (pointer: OperationPointer) => {
          // Before A's clearIfEqual runs, a newer reservation lands in the
          // store. A's clear must see the new one and return false.
          overwrite();
          return echoReceipt(pointer, "accepted", { missionSelection: VALID_SELECTION });
        }),
      });
      const ctrlA = new OperationController(buildPort(portA), sharedStore);

      const beginPromise = ctrlA.begin(LAUNCH_INTENT);
      overwrite = () => {
        sharedData.set("scope-A", {
          operationKey: "op-newer",
          kind: "launch",
          targetKey: null,
        });
      };
      const result = await beginPromise;

      expect(result.status).toBe("unknown");
      expect(result.reason).toBe("UNKNOWN_RECEIPT");
      expect(sharedStore.read("scope-A")).toEqual({
        operationKey: "op-newer",
        kind: "launch",
        targetKey: null,
      });
    });

    it("reserve never overwrites — even when the new pointer is exactly equal to the existing", async () => {
      // Two concurrent begins with the SAME prepared pointer. The second
      // reserve must lose with reserved:false, even though the pointers are
      // structurally equal. The second controller sees checking/PENDING_POINTER.
      const sharedData = new Map<string, OperationPointer>();
      const sharedStore: PendingPointerStore = {
        read: (scope) => sharedData.get(scope) ?? null,
        reserve: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing) return { reserved: false, pointer: existing };
          sharedData.set(scope, pointer);
          return { reserved: true };
        },
        clearIfEqual: (scope, pointer) => {
          const existing = sharedData.get(scope);
          if (existing && samePointer(existing, pointer)) {
            sharedData.delete(scope);
            return true;
          }
          return false;
        },
      };
      const equalPointer: OperationPointer = {
        operationKey: "op-shared",
        kind: "launch",
        targetKey: null,
      };
      const portState = makePort({
        _prepare: vi.fn(() => equalPointer),
        _submit: vi.fn(async (p: OperationPointer) =>
          echoReceipt(p, "accepted", { missionSelection: VALID_SELECTION }),
        ),
      });
      const ctrl1 = new OperationController(buildPort(portState), sharedStore);
      const ctrl2 = new OperationController(buildPort(portState), sharedStore);

      const [r1, r2] = await Promise.all([
        ctrl1.begin(LAUNCH_INTENT),
        ctrl2.begin(LAUNCH_INTENT),
      ]);

      const results = [r1, r2];
      const accepted = results.filter((r) => r.status === "accepted");
      const checking = results.filter((r) => r.status === "checking");

      expect(accepted).toHaveLength(1);
      expect(checking).toHaveLength(1);
      expect(checking[0]!.reason).toBe("PENDING_POINTER");
      // Only one submit was issued.
      expect(portState._submit).toHaveBeenCalledTimes(1);
    });

    it("recover that finds no pointer returns RECOVER_NO_POINTER without calling clearIfEqual", async () => {
      const { store, state } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      const result = await ctrl.recover();

      expect(result.status).toBe("idle");
      expect(result.reason).toBe("RECOVER_NO_POINTER");
      expect(portState._readOp).not.toHaveBeenCalled();
      expect(state._clears).toHaveLength(0);
    });

    it("sign-out during reserve bails before submit; the uncommitted reservation leaves no hint", async () => {
      const { store } = makeStoreWithState();
      const portState = makePort();
      const ctrl = new OperationController(buildPort(portState), store);

      // Make reserve observe the system signal and pretend it was aborted
      // before any commit happened. We model this by throwing from reserve,
      // which the controller maps to STORE_WRITE_FAILED. The store stays
      // empty: no reservation was committed.
      store.reserve = ((_scope: string, _pointer: OperationPointer, _signal?: AbortSignal) => {
        portState._ctx = null;
        throw new Error("aborted before commit");
      }) as PendingPointerStore["reserve"];

      const result = await ctrl.begin(LAUNCH_INTENT);

      // sign-out happens after reserve was rejected; the controller returns
      // idle/OWNER_ABSENT (the context gate). The hint was not committed.
      expect(result.status).toBe("idle");
      expect(store.read("scope-A")).toBeNull();
      expect(portState._submit).not.toHaveBeenCalled();
    });
  });
});