// Focused Vitest coverage for the executive session command port.
// The module under test is integrated as ./executive-session-command-port;
// every fixture below is an in-memory fake: no backend, route, credential,
// store or producer is instantiated by these tests.
import { afterEach, describe, expect, it, vi } from "vitest";
import { OperationController } from "./operation-controller";
import { messageIntentFromBinding } from "./host-command-bindings";
import type {
  CommandIntent,
  OperationPointer,
  PendingPointerStore,
} from "./operation-controller";
import {
  codePointLength,
  createExecutiveSessionBinding,
  decodeSessionContext,
  type ExecutiveSessionTransport,
  type SessionSendArguments,
} from "./executive-session-command-port";

// ── Frozen fixture vocabulary ─────────────────────────────────────────────────

const WS = "WS:ALPHA";
const ROOT = "JOB-1";
const selection = { workRef: WS, rootJobId: ROOT };
const REF = `fabric_attempt:${"a".repeat(64)}`;
const GEN = "a".repeat(24);
const CONT = "b".repeat(64);
const OPKEY = `session-continue-${CONT}`;
const FP = "f".repeat(64);
const TS = "1728620000.000001";
const SCOPE = "c".repeat(64);

const POINTER: OperationPointer = {
  operationKey: OPKEY,
  kind: "message",
  targetKey: REF,
};

const messageIntent = (instruction = "Continue the slice", stop = "CI green"): CommandIntent => ({
  kind: "message",
  targetKey: REF,
  payload: {
    instruction,
    stop_condition: stop,
    work_ref: WS,
    root_job_id: ROOT,
  },
});

/** Canonical owner formula, used only to build faithful fixture receipts. */
const continueKey = (_operationKey: string): string => "asd-dot-continue-c81bfcc7ccadd7372a1b0d05bb610f9d147b43b9";
const nativeReplyKey = "asd-native-reply-4310b611582e4d2fa8f7053ea19490441b3e3db1";

const row = {
  target_ref: REF,
  generation: GEN,
  addressable: true,
  kind: "fabric_attempt",
  continuation_operation_key: OPKEY,
  work_ref: WS,
  root_job_id: ROOT,
};

const result = (operation: string, patch: Record<string, unknown>) => ({
  schema: "mastermind.os.executive.session_result.v1",
  operation,
  ok: true,
  effect: "NONE",
  operation_key: null,
  data: null,
  error: null,
  ...patch,
});

const contextData = (
  state: "RESOLVED" | "UNAVAILABLE" | "AMBIGUOUS" = "RESOLVED",
  targetRow: unknown = row,
  patch: Record<string, unknown> = {},
) => ({
  schema: "mastermind.os.executive.session_context.v1",
  principal_scope: SCOPE,
  verified_expiry: 4102444800,
  selection: { work_ref: WS, root_job_id: ROOT },
  selection_state: state,
  target: state === "RESOLVED" ? targetRow : null,
  capabilities: { send: state === "RESOLVED", reply_read: true, stop: false },
  ...patch,
});

const contextEnvelope = (state?: Parameters<typeof contextData>[0]) =>
  result("context", { data: contextData(state) });

const sendData = (attention: string = "UNAVAILABLE") => ({
  target_ref: REF,
  reply_committed: true,
  carrier: {
    reply_committed: true,
    action: "POSTED",
    message_key: continueKey(OPKEY),
    fingerprint: FP,
    thread_ts: TS,
  },
  attention: { state: attention },
  read_ref: "read-ref-1",
});

const sendEnvelope = (patch: Record<string, unknown> = {}) =>
  result("send", {
    ok: true,
    effect: "CONTINUATION_COMMITTED",
    operation_key: OPKEY,
    data: sendData(),
    ...patch,
  });

const replyData = (patch: Record<string, unknown> = {}) => ({
  schema: "mastermind.native_reply_read.v1",
  read_ref: "read-ref-1",
  request_ref: "request-ref-1",
  in_reply_to: continueKey(OPKEY),
  message_key: nativeReplyKey,
  fingerprint: FP,
  text: "slice accepted",
  next_step: "none",
  primary_ts: TS,
  reply_committed: true,
  parent_consumed: false,
  operation_key: OPKEY,
  ...patch,
});

const replyEnvelope = (patch: Record<string, unknown> = {}) =>
  result("reply", {
    ok: true,
    effect: "CONTINUATION_COMMITTED",
    operation_key: OPKEY,
    data: replyData(),
    ...patch,
  });

// ── Fixtures ──────────────────────────────────────────────────────────────────

function samePointer(a: OperationPointer, b: OperationPointer): boolean {
  return (
    a.operationKey === b.operationKey &&
    a.kind === b.kind &&
    a.targetKey === b.targetKey
  );
}

function memStore(): {
  store: PendingPointerStore;
  hints: Map<string, OperationPointer>;
} {
  const hints = new Map<string, OperationPointer>();
  const store: PendingPointerStore = {
    read: (scope) => hints.get(scope) ?? null,
    reserve: (scope, pointer) => {
      const existing = hints.get(scope);
      if (existing) return { reserved: false, pointer: existing };
      hints.set(scope, pointer);
      return { reserved: true };
    },
    clearIfEqual: (scope, pointer) => {
      const existing = hints.get(scope);
      if (existing && samePointer(existing, pointer)) {
        hints.delete(scope);
        return true;
      }
      return false;
    },
  };
  return { store, hints };
}

function fixture() {
  let authGen = 1;
  let available = true;
  let contextResponse: unknown = contextEnvelope();
  let sendImpl: (args: SessionSendArguments, signal: AbortSignal) => Promise<unknown> =
    async () => sendEnvelope();
  let replyImpl: (args: { operation_key: string }) => Promise<unknown> =
    async () => replyEnvelope();
  const listeners = new Set<() => void>();
  const f = {
    contextSelections: [] as Array<{ workRef: string; rootJobId: string }>,
    calls: { context: 0, send: 0, reply: 0 },
    sendArgs: [] as SessionSendArguments[],
    replyArgs: [] as Array<{ operation_key: string }>,
    transport: null as unknown as ExecutiveSessionTransport,
    setContext(value: unknown) {
      contextResponse = value;
    },
    setSend(impl: typeof sendImpl) {
      sendImpl = impl;
    },
    setReply(impl: typeof replyImpl) {
      replyImpl = impl;
    },
    bumpAuth() {
      authGen++;
      for (const listener of listeners) listener();
    },
  };
  const transport: ExecutiveSessionTransport = {
    authGeneration: () => authGen,
    available: () => available,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    context: vi.fn(async (selected) => {
      f.contextSelections.push(selected);
      f.calls.context++;
      return contextResponse;
    }),
    send: vi.fn(async (args: SessionSendArguments, signal: AbortSignal) => {
      f.calls.send++;
      f.sendArgs.push(args);
      return sendImpl(args, signal);
    }),
    reply: vi.fn(async (args: { operation_key: string }) => {
      f.calls.reply++;
      f.replyArgs.push(args);
      return replyImpl(args);
    }),
  };
  f.transport = transport;
  return f;
}

const disposables: Array<() => void> = [];
afterEach(() => {
  for (const dispose of disposables.splice(0)) dispose();
});

function mount(
  f: ReturnType<typeof fixture>,
  options: {
    selection?: () => { workRef: string; rootJobId: string } | null;
    store?: PendingPointerStore;
    stopCondition?: () => unknown;
  } = {},
) {
  const handle = createExecutiveSessionBinding({
    transport: f.transport,
    store: options.store ?? memStore().store,
    selection: options.selection ?? (() => selection),
    clock: () => 1_000_000,
    stopCondition: options.stopCondition ?? (() => undefined),
  });
  disposables.push(handle.dispose);
  return handle;
}

async function beginSession(f: ReturnType<typeof fixture>, store: PendingPointerStore) {
  const handle = mount(f, { store });
  await handle.ready;
  const controller = new OperationController(handle.binding.port, store);
  return { handle, controller };
}

// ── Canonical selection join ──────────────────────────────────────────────────

describe("decodeSessionContext — canonical fabric_attempt join", () => {
  it("resolves exactly one intact row for the exact requested work/root pair", () => {
    const decoded = decodeSessionContext(contextEnvelope(), selection);
    expect(decoded?.selectionState).toBe("RESOLVED");
    expect(decoded?.target?.target_ref).toBe(REF);
    expect(decoded?.capabilities).toEqual({ send: true, reply_read: true, stop: false });
  });

  it("fails closed on wrong selection echo, foreign rows and broken grammars", () => {
    expect(
      decodeSessionContext(
        result("context", { data: contextData("RESOLVED", { ...row, work_ref: "WS:OTHER" }) }),
        selection,
      ),
    ).toBeNull();
    expect(
      decodeSessionContext(
        result("context", { data: contextData("RESOLVED", { ...row, kind: "codex_attempt" }) }),
        selection,
      ),
    ).toBeNull();
    expect(
      decodeSessionContext(
        result("context", { data: contextData("RESOLVED", { ...row, addressable: false }) }),
        selection,
      ),
    ).toBeNull();
    expect(
      decodeSessionContext(
        result("context", { data: contextData("RESOLVED", { ...row, generation: "abc" }) }),
        selection,
      ),
    ).toBeNull();
    expect(
      decodeSessionContext(
        result("context", {
          data: contextData("RESOLVED", { ...row, continuation_operation_key: "zz".repeat(32) }),
        }),
        selection,
      ),
    ).toBeNull();
    expect(decodeSessionContext({ nope: true }, selection)).toBeNull();
  });

  it("treats ambiguous and empty projections as no target, never a first pick", () => {
    for (const state of ["UNAVAILABLE", "AMBIGUOUS"] as const) {
      const decoded = decodeSessionContext(contextEnvelope(state), selection);
      expect(decoded?.selectionState).toBe(state);
      expect(decoded?.target).toBeNull();
      expect(decoded?.capabilities.send).toBe(false);
      // A stateful projection that still smuggles a target fails closed.
      expect(
        decodeSessionContext(
          result("context", { data: contextData(state, row, { target: row }) }),
          selection,
        ),
      ).toBeNull();
    }
  });
});

describe("exact and wrong selection through the binding host", () => {
  it("resolves the exact selected Mission and re-reads under a new epoch", async () => {
    const f = fixture();
    const handle = mount(f);
    await handle.ready;
    expect(f.calls.context).toBe(1);
    expect(f.contextSelections[0]).toEqual(selection);
    expect(handle.sessionState()?.target?.target_ref).toBe(REF);
    expect(handle.binding.port.context()?.principalScope).toBe(SCOPE);
    expect(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green"),
    ).not.toBeNull();
    const generationBefore = handle.binding.port.context()?.generation;
    f.bumpAuth();
    await Promise.resolve();
    await Promise.resolve();
    expect(handle.sessionState()?.target?.target_ref).toBe(REF);
    // A new auth epoch is a new owner generation: A→B→A can never repeat it.
    expect(handle.binding.port.context()?.generation).not.toBe(generationBefore);
  });

  it("withholds the session when the selected Mission moved away", async () => {
    const f = fixture();
    let current: { workRef: string; rootJobId: string } | null = selection;
    const handle = mount(f, { selection: () => current });
    await handle.ready;
    expect(handle.sessionState()).not.toBeNull();
    current = { workRef: "WS:OTHER", rootJobId: ROOT };
    await handle.refresh();
    expect(handle.sessionState()).toBeNull();
    expect(handle.binding.port.context()).toBeNull();
    expect(handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")).toBeNull();
  });
});

describe("ambiguous and empty targets never mint or guess", () => {
  it("exposes no target and refuses message intents", async () => {
    const f = fixture();
    f.setContext(contextEnvelope("AMBIGUOUS"));
    const { store, hints } = memStore();
    const handle = mount(f, { store });
    await handle.ready;
    expect(handle.sessionState()?.selectionState).toBe("AMBIGUOUS");
    expect(handle.sessionState()?.target).toBeNull();
    expect(handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")).toBeNull();
    expect(() => handle.binding.port.prepare(messageIntent())).toThrow();
    expect(hints.size).toBe(0);
    expect(f.calls.send).toBe(0);
  });
});

describe("intent boundaries", () => {
  it("never invents a stop condition and never offers launch or stop", async () => {
    const f = fixture();
    const handle = mount(f);
    await handle.ready;
    // Two-argument form: no default stop condition, so no intent.
    expect(handle.binding.makeMessageIntent(REF, "Continue")).toBeNull();
    expect(
      handle.binding.makeLaunchIntent({ goal: "g", projectRef: "p", profileRef: "r" }),
    ).toBeNull();
    expect(handle.binding.makeStopIntent(REF)).toBeNull();
    const explicit = handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green");
    expect(explicit?.payload).toEqual({
      instruction: "Continue",
      stop_condition: "CI green",
      work_ref: WS,
      root_job_id: ROOT,
    });
    expect(explicit?.targetKey).toBe(REF);
  });

  it("counts Unicode code points like Python len (700 passes, 701 fails)", async () => {
    const f = fixture();
    const handle = mount(f);
    await handle.ready;
    const astral = "\u{1D11E}";
    expect(codePointLength(astral)).toBe(1);
    expect(astral.length).toBe(2);
    // 700 astral code points = 1400 UTF-16 units: valid by code points alone.
    expect(handle.binding.makeSessionMessageIntent(REF, astral.repeat(700), "stop")).not.toBeNull();
    // 701 astral code points: invalid even though no UTF-16 counting applies.
    expect(handle.binding.makeSessionMessageIntent(REF, astral.repeat(701), "stop")).toBeNull();
    expect(handle.binding.makeSessionMessageIntent(REF, "ok", astral.repeat(700))).not.toBeNull();
    expect(handle.binding.makeSessionMessageIntent(REF, "ok", astral.repeat(701))).toBeNull();
    // Plain BMP text at the same bounds behaves identically.
    expect(handle.binding.makeSessionMessageIntent(REF, "x".repeat(700), "s")).not.toBeNull();
    expect(handle.binding.makeSessionMessageIntent(REF, "x".repeat(701), "s")).toBeNull();
  });
});

describe("send through a real OperationController", () => {
  it("commits only on the validated canonical receipt and clears the pointer", async () => {
    const f = fixture();
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    const state = await controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    expect(state.status).toBe("accepted");
    expect(state.reason).toBe("ACCEPTED");
    expect(f.calls.send).toBe(1);
    // Exactly the four validated arguments, strings preserved verbatim.
    expect(f.sendArgs[0]).toEqual({
      target_ref: REF,
      instruction: "Continue",
      stop_condition: "CI green",
      operation_key: OPKEY,
    });
    expect(hints.size).toBe(0);
  });

  it("retains the pointer on a wrong operation key receipt or wrong key pointer", async () => {
    const otherKey = `session-continue-${"9".repeat(64)}`;
    // Foreign key on the receipt: unknown, pointer retained.
    const f = fixture();
    f.setSend(async () => sendEnvelope({ operation_key: otherKey }));
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    const state = await controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    expect(state.status).toBe("unknown");
    expect(state.reason).toBe("UNKNOWN_RECEIPT");
    expect(hints.get(SCOPE)?.operationKey).toBe(OPKEY);
    // Pointer whose key does not bind to the current host-projected
    // continuation key: refused before any send.
    const stale = await handle.binding.port.submit(
      { operationKey: otherKey, kind: "message", targetKey: REF },
      handle.binding.makeSessionMessageIntent(REF, "Continue", "done")!,
      new AbortController().signal,
    );
    expect(stale.disposition).toBe("refused");
    expect(f.calls.send).toBe(1);
  });

  it("publishes commit with unavailable attention and never conflates the two", async () => {
    for (const attention of ["UNAVAILABLE", "EFFECT_UNKNOWN"] as const) {
      const f = fixture();
      f.setSend(async () => sendEnvelope({ data: sendData(attention) }));
      const { store, hints } = memStore();
      const { handle, controller } = await beginSession(f, store);
      const state = await controller.begin(
        handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
      );
      expect(state.status).toBe("accepted");
      expect(state.reason).toBe("ACCEPTED");
      expect(hints.size).toBe(0);
      expect(f.sendArgs[0]?.target_ref).toBe(REF);
    }
  });

  it("maps a pre-send NONE refusal to refused and an UNKNOWN effect to retained", async () => {
    const refused = fixture();
    refused.setSend(
      async () =>
        sendEnvelope({
          ok: false,
          effect: "NONE",
          data: null,
          operation_key: null,
          error: { code: "invalid_input", message: "invalid input" },
        }),
    );
    const refusedStore = memStore();
    const refusedRun = await beginSession(refused, refusedStore.store);
    const refusedState = await refusedRun.controller.begin(
      refusedRun.handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    expect(refusedState.status).toBe("refused");
    expect(refusedStore.hints.size).toBe(0);

    const unknownEffect = fixture();
    unknownEffect.setSend(
      async () =>
        sendEnvelope({
          ok: false,
          effect: "UNKNOWN",
          data: null,
          operation_key: null,
          error: { code: "effect_unknown", message: "effect unknown" },
        }),
    );
    const unknownStore = memStore();
    const unknownRun = await beginSession(unknownEffect, unknownStore.store);
    const unknownState = await unknownRun.controller.begin(
      unknownRun.handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    expect(unknownState.status).toBe("unknown");
    expect(unknownStore.hints.size).toBe(1);
  });

  it("refuses before sending when the payload selection disagrees with the owner", async () => {
    const f = fixture();
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    const state = await controller.begin({
      kind: "message",
      targetKey: REF,
      payload: {
        instruction: "Continue",
        stop_condition: "CI green",
        work_ref: "WS:OTHER",
        root_job_id: ROOT,
      },
    });
    expect(state.status).toBe("idle");
    expect(hints.size).toBe(0);
    expect(f.calls.send).toBe(0);
    void handle;
  });
});

describe("auth and selection fencing around the send", () => {
  it("retains the pointer across auth-generation drift and recovers by the original key", async () => {
    const f = fixture();
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    let release: (value: unknown) => void = () => {};
    f.setSend(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const pending = controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    await vi.waitFor(() => expect(f.calls.send).toBe(1));
    f.bumpAuth(); // A -> B while the send is in flight
    release(sendEnvelope());
    const drifted = await pending;
    expect(["idle", "unknown"]).toContain(drifted.status);
    expect(f.calls.send).toBe(1);
    expect(hints.size).toBe(1);
    // Recovery under the new epoch still uses the exact original key.
    const recovered = await controller.recover();
    expect(recovered.status).toBe("accepted");
    expect(f.replyArgs[0]?.operation_key).toBe(OPKEY);
    expect(f.calls.send).toBe(1); // recovery never sent
    expect(hints.size).toBe(0);
  });

  it("retains the pointer when the selection changes while the send is in flight", async () => {
    const f = fixture();
    let current: { workRef: string; rootJobId: string } | null = selection;
    const { store, hints } = memStore();
    const handle = mount(f, { selection: () => current, store });
    await handle.ready;
    const controller = new OperationController(handle.binding.port, store);
    let release: (value: unknown) => void = () => {};
    f.setSend(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const pending = controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    await vi.waitFor(() => expect(f.calls.send).toBe(1));
    current = { workRef: "WS:OTHER", rootJobId: ROOT };
    await handle.refresh(); // bumps the owner epoch, drops the verified session
    release(sendEnvelope());
    const drifted = await pending;
    expect(["idle", "unknown"]).toContain(drifted.status);
    expect(hints.size).toBe(1);
  });

  it("returns unknown on a lost response and keeps the exact pointer", async () => {
    const f = fixture();
    f.setSend(async () => {
      throw new Error("lost response");
    });
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    const state = await controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    expect(state.status).toBe("unknown");
    expect(state.reason).toBe("UNKNOWN_RECEIPT");
    expect([...hints.values()][0]).toEqual(POINTER);
    expect(handle.sessionState()?.target?.target_ref).toBe(REF);
  });
});

describe("recovery after the target disappears", () => {
  it("recovers by the exact original key with no send and no target lookup", async () => {
    const f = fixture();
    f.setSend(async () => {
      throw new Error("lost response");
    });
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    await controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    // The writer cleaned up: the projection no longer resolves a target.
    f.setContext(contextEnvelope("UNAVAILABLE"));
    await handle.refresh();
    expect(handle.sessionState()?.target).toBeNull();
    const contextCalls = f.calls.context;
    const state = await controller.recover();
    expect(state.status).toBe("accepted");
    expect(f.replyArgs[0]?.operation_key).toBe(OPKEY);
    expect(f.calls.send).toBe(1); // recovery never sent
    expect(f.calls.context).toBe(contextCalls); // and never looked up targets
    expect(hints.size).toBe(0);
  });

  it("never clears the pointer on reply failures, including malformed replies", async () => {
    const cases: Array<[string, () => unknown]> = [
      [
        "reply unavailable",
        () =>
          replyEnvelope({
            ok: false,
            effect: "UNKNOWN",
            data: null,
            operation_key: null,
            error: { code: "effect_unknown", message: "reply unavailable" },
          }),
      ],
      ["parent consumed", () => replyEnvelope({ data: replyData({ parent_consumed: true }) })],
      [
        "foreign schema",
        () => replyEnvelope({ data: { ...replyData(), schema: "someone.else.v9", extra: 1 } }),
      ],
      [
        "wrong operation key",
        () => replyEnvelope({ operation_key: `session-continue-${"9".repeat(64)}` }),
      ],
    ];
    for (const [name, impl] of cases) {
      const f = fixture();
      f.setReply(async () => impl());
      const { store, hints } = memStore();
      hints.set(SCOPE, POINTER);
      const handle = mount(f, { store });
      await handle.ready;
      const controller = new OperationController(handle.binding.port, store);
      const state = await controller.recover();
      expect(state.status, name).toBe("unknown");
      expect(hints.size, name).toBe(1);
      expect(hints.get(SCOPE)?.operationKey, name).toBe(OPKEY);
      expect(f.calls.send, name).toBe(0);
      handle.dispose();
    }
  });

  it("reads nothing when there is no pending pointer", async () => {
    const f = fixture();
    const { store } = memStore();
    const handle = mount(f, { store });
    await handle.ready;
    const controller = new OperationController(handle.binding.port, store);
    expect((await controller.recover()).reason).toBe("RECOVER_NO_POINTER");
    expect(f.calls.send).toBe(0);
    expect(f.calls.reply).toBe(0);
  });
});

describe("stop is unavailable and never a cancellation", () => {
  it("invalidation mid-flight suppresses rendering but retains the effect pointer", async () => {
    const f = fixture();
    const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    expect(handle.binding.makeStopIntent(REF)).toBeNull();
    let release: (value: unknown) => void = () => {};
    f.setSend(
      (_args, signal) =>
        new Promise((resolve) => {
          release = resolve;
          signal.addEventListener("abort", () => release(sendEnvelope()), { once: true });
        }),
    );
    const pending = controller.begin(
      handle.binding.makeSessionMessageIntent(REF, "Continue", "CI green")!,
    );
    await vi.waitFor(() => expect(f.calls.send).toBe(1));
    controller.invalidate(); // aborts the render, not the durable effect
    const after = await pending;
    expect(after.status).toBe("idle");
    expect(f.calls.send).toBe(1); // exactly one send, no retry
    expect(hints.size).toBe(1); // pointer kept its original scope
    const recovered = await controller.recover();
    expect(recovered.status).toBe("accepted");
    expect(hints.size).toBe(0);
  });

  it("does not send on a pre-aborted signal", async () => {
    const f = fixture();
    const { store, hints } = memStore();
    const handle = mount(f, { store });
    await handle.ready;
    const abort = new AbortController();
    abort.abort();
    const receipt = await handle.binding.port.submit(
      POINTER,
      handle.binding.makeSessionMessageIntent(REF, "Continue", "done")!,
      abort.signal,
    );
    expect(receipt.disposition).toBe("unknown");
    expect(f.calls.send).toBe(0);
    expect(hints.size).toBe(0);
  });
});

// Parent contract falsifiers against the retained worker postimage.
describe("owner-bound stop condition and exact backend receipt", () => {
  it("captures the explicit owner condition once for the existing two-argument UI", async () => {
    const f = fixture(); let condition = "Exact owner stop"; const provider = vi.fn(() => condition);
    const h = mount(f, { stopCondition: provider }); await h.ready;
    const intent = h.binding.makeMessageIntent(REF, "Useful continuation");
    expect(intent).not.toBeNull(); condition = "Later changed condition";
    const pointer = h.binding.port.prepare(intent!);
    await h.binding.port.submit(pointer, intent!, new AbortController().signal);
    expect(provider).toHaveBeenCalledTimes(1); expect(f.sendArgs[0].stop_condition).toBe("Exact owner stop");
    expect(Object.isFrozen(intent)).toBe(true); expect(Object.isFrozen(intent!.payload)).toBe(true);
  });
  it.each([undefined, null, 1, "", "   ", "😀".repeat(701)])("refuses unusable owner condition %s", async (value) => {
    const f = fixture(); const h = mount(f, { stopCondition: () => value }); await h.ready;
    expect(h.binding.makeMessageIntent(REF, "Continue")).toBeNull(); expect(f.calls.send).toBe(0);
  });
  it("refuses a throwing condition provider", async () => {
    const f = fixture(); const h = mount(f, { stopCondition: () => { throw new Error("private"); } }); await h.ready;
    expect(h.binding.makeMessageIntent(REF, "Continue")).toBeNull();
  });
  it("rejects valid-looking generation that disagrees with the canonical target", () => {
    expect(decodeSessionContext(result("context", { data: contextData("RESOLVED", {...row, generation: "0".repeat(24)}) }), selection)).toBeNull();
  });
  it("does not accept a forged native reply with merely grammatical correlation", async () => {
    const f = fixture(); f.setReply(async () => replyEnvelope({data: replyData({ in_reply_to: "asd-dot-continue-" + "0".repeat(40) })}));
    const h = mount(f); await h.ready; expect((await h.binding.port.readOperation(POINTER,new AbortController().signal)).disposition).toBe("unknown");
  });
});


describe("final boundary falsifiers", () => {
  it("refuses receipt validation when WebCrypto is unavailable", async () => {
    const f = fixture(); const { store, hints } = memStore();
    const { handle, controller } = await beginSession(f, store);
    const intent = handle.binding.makeSessionMessageIntent(REF, "Continue", "done")!;
    vi.stubGlobal("crypto", undefined);
    try {
      expect((await controller.begin(intent)).status).toBe("unknown");
      expect(hints.get(SCOPE)).toEqual(POINTER);
      expect(f.calls.send).toBe(1);
    } finally { vi.unstubAllGlobals(); }
  });
  it.each(["send", "reply"] as const)("fences auth changes during %s hash validation", async (operation) => {
    const f = fixture(); const h = mount(f); await h.ready;
    const intent = h.binding.makeSessionMessageIntent(REF, "Continue", "done")!;
    const pointer = h.binding.port.prepare(intent);
    const digest = crypto.subtle.digest.bind(crypto.subtle);
    let release: (() => void) | undefined;
    const spy = vi.spyOn(crypto.subtle, "digest").mockImplementation(async (algorithm, data) => {
      const result = await digest(algorithm, data);
      await new Promise<void>(resolve => { release = resolve; });
      return result;
    });
    try {
      const pending = operation === "send"
        ? h.binding.port.submit(pointer, intent, new AbortController().signal)
        : h.binding.port.readOperation(pointer, new AbortController().signal);
      await vi.waitFor(() => expect(release).toBeDefined());
      f.bumpAuth();
      spy.mockRestore(); release!();
      expect((await pending).disposition).toBe("unknown");
    } finally { spy.mockRestore(); }
  });
  it("rejects an intent captured before an auth epoch change before any SEND", async () => {
    const f = fixture(); const h = mount(f, { stopCondition: () => "done" }); await h.ready;
    const intent = h.binding.makeMessageIntent(REF, "Continue")!;
    f.bumpAuth(); await h.refresh();
    expect(() => h.binding.port.prepare(intent)).toThrow("EPOCH_CHANGED");
    expect(f.calls.send).toBe(0);
  });
  it("rejects current selection drift even before host refresh", async () => {
    const f = fixture(); let selected = selection;
    const h = mount(f, { selection: () => selected }); await h.ready;
    const intent = h.binding.makeSessionMessageIntent(REF, "Continue", "done")!;
    selected = { workRef: "WS:OTHER", rootJobId: ROOT };
    expect(h.sessionState()).toBeNull();
    expect(() => h.binding.port.prepare(intent)).toThrow();
    expect(f.calls.send).toBe(0);
  });
  it("freezes the authenticated projection against caller mutation", async () => {
    const f = fixture(); const h = mount(f); await h.ready;
    expect(Object.isFrozen(h.sessionState())).toBe(true);
    expect(Object.isFrozen(h.sessionState()?.target)).toBe(true);
    expect(Object.isFrozen(h.sessionState()?.selection)).toBe(true);
    expect(Object.isFrozen(h.sessionState()?.capabilities)).toBe(true);
  });
  it.each([
    { text: "x".repeat(8193) }, { next_step: "x".repeat(8193) },
    { next_step: "" }, { text: "😀".repeat(2000) },
    { message_key: "asd-native-reply-" + "0".repeat(40) },
  ])("retains the original pointer for out-of-bound or foreign native data %#", async (patch) => {
    const f = fixture(); f.setReply(async () => replyEnvelope({ data: replyData(patch) }));
    const { store, hints } = memStore(); hints.set(SCOPE, POINTER);
    const h = mount(f, { store }); await h.ready;
    const controller = new OperationController(h.binding.port, store);
    expect((await controller.recover()).status).toBe("unknown");
    expect(hints.get(SCOPE)).toEqual(POINTER); expect(f.calls.send).toBe(0);
  });
  it("preserves canonical nonempty whitespace reply text", async () => {
    const f = fixture(); f.setReply(async () => replyEnvelope({ data: replyData({ text: " ", next_step: " " }) }));
    const h = mount(f); await h.ready;
    expect((await h.binding.port.readOperation(POINTER, new AbortController().signal)).disposition).toBe("accepted");
  });
  it("reserves the immutable original pointer before entering SEND", async () => {
    const f = fixture(); const { store, hints } = memStore();
    f.setSend(async () => { expect(hints.get(SCOPE)).toEqual(POINTER); return sendEnvelope(); });
    const { handle, controller } = await beginSession(f, store);
    expect((await controller.begin(handle.binding.makeSessionMessageIntent(REF, "Continue", "done")!)).status).toBe("accepted");
    expect(f.calls.send).toBe(1);
  });
  it("does not SEND when atomic reservation loses to an existing pointer", async () => {
    const f = fixture(); const { store, hints } = memStore();
    const existing = { ...POINTER, operationKey: "session-continue-" + "d".repeat(64) };
    const read = store.read; store.read = () => null;
    store.reserve = () => ({ reserved: false, pointer: existing });
    hints.set(SCOPE, existing);
    const { handle, controller } = await beginSession(f, store);
    await controller.begin(handle.binding.makeSessionMessageIntent(REF, "Continue", "done")!);
    expect(f.calls.send).toBe(0); expect(hints.get(SCOPE)).toEqual(existing);
    store.read = read;
  });
});


describe("original independent review regressions", () => {
  it.each([null, OPKEY, "session-continue-" + "9".repeat(64)])("maps NONE against exact retained key %#", async operationKey => {
    const f = fixture(); f.setSend(async () => sendEnvelope({ ok: false, effect: "NONE", data: null,
      operation_key: operationKey, error: { code: "invalid_input", message: "invalid input" } }));
    const { store, hints } = memStore(); const { handle, controller } = await beginSession(f, store);
    const state = await controller.begin(handle.binding.makeSessionMessageIntent(REF, "Continue", "done")!);
    expect(state.status).toBe(operationKey === null || operationKey === OPKEY ? "refused" : "unknown");
    expect(hints.size).toBe(operationKey === null || operationKey === OPKEY ? 0 : 1);
  });
  it("preserves captured epoch through the real UI intent helper", async () => {
    const f = fixture(); const h = mount(f, { stopCondition: () => "done" }); await h.ready;
    const wrapped = messageIntentFromBinding(h.binding, REF, "Continue")!;
    await h.refresh();
    expect(() => h.binding.port.prepare(wrapped)).toThrow("EPOCH_CHANGED");
    expect(f.calls.send).toBe(0);
  });
  it("allows the same-epoch real UI wrapper and freezes it before reservation", async () => {
    const f = fixture(); const { store } = memStore();
    const h = mount(f, { store, stopCondition: () => "done" }); await h.ready;
    const wrapped = messageIntentFromBinding(h.binding, REF, "Continue")!;
    h.binding.port.prepare(wrapped);
    expect(Object.isFrozen(wrapped)).toBe(true);
    expect(Object.isFrozen(wrapped.payload)).toBe(true);
    const controller = new OperationController(h.binding.port, store);
    expect((await controller.begin(wrapped)).status).toBe("accepted"); expect(f.calls.send).toBe(1);
  });
  it("refuses unregistered copied payloads rather than bypassing capture", async () => {
    const f = fixture(); const h = mount(f); await h.ready;
    const original = h.binding.makeSessionMessageIntent(REF, "Continue", "done")!;
    const copied = { ...original, payload: { ...original.payload } };
    expect(() => h.binding.port.prepare(copied)).toThrow("EPOCH_CHANGED");
    expect((await h.binding.port.submit(POINTER, copied, new AbortController().signal)).disposition).toBe("refused");
    expect(f.calls.send).toBe(0);
  });
  it("pins the context namespace to protected os_transport.principal_scope SHA256 hexdigest", () => {
    expect(decodeSessionContext(result("context", { data: contextData("RESOLVED", row, { principal_scope: "opaque arbitrary" }) }), selection)).toBeNull();
    expect(decodeSessionContext(contextEnvelope(), selection)?.principalScope).toBe(SCOPE);
  });
});
