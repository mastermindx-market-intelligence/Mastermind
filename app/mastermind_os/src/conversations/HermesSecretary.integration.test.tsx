// @vitest-environment jsdom
// Focused Vitest coverage for the Secretary session consumer.
//
// The producer contract is closed and owned elsewhere: these cases only prove
// that the consumer carries the closed target kind through every hop, never
// falls back to Fabric, keeps the original pointer until the exact answer
// renders, and refuses every wrong identity, malformed field and oversize
// frame.  No backend, provider, credential, socket or browser is contacted.
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useQualifiedOriginalAnswer } from "./useQualifiedOriginalAnswer";
import { createAwaitingAnswerPort } from "./awaiting-answer-port";
import { OperationController } from "../orchestration/operation-controller";
import type {
  CommandIntent,
  OperationPointer,
  PendingPointerStore,
} from "../orchestration/operation-controller";
import {
  canonicalAsciiLength,
  createExecutiveSessionBinding,
  decodeHermesPublicResult,
  decodeSessionContext,
  MAX_PUBLIC_RESULT_BYTES,
  sessionSelectionWire,
  sessionTargetKind,
  type ExecutiveSessionSelection,
  type ExecutiveSessionTransport,
  type SessionSendArguments,
} from "../orchestration/executive-session-command-port";
import { sessionNativePhase } from "../orchestration/ui/SelectedSessionContinuation";
import metaFixture from "../fixtures/native-hermes-meta-session-send-producer.json";

// ── Frozen fixture vocabulary ─────────────────────────────────────────────────

const WS = "WS:ALPHA";
const ROOT = "JOB-1";
const SCOPE = "c".repeat(64);
const FABRIC_REF = `fabric_attempt:${"a".repeat(64)}`;
const HERMES_REF = `hermes_secretary:${"a".repeat(64)}`;
const HERMES_GEN = "a".repeat(24);
const FABRIC_OPKEY = `session-continue-${"b".repeat(64)}`;
// Verified against the producer's own derivation:
//   "session-continue-" + SHA256({"schema":"…hermes_secretary_operation.v1","target_ref":…})
const HERMES_OPKEY =
  "session-continue-416b8fb98b2d93a068cd6dbd4ff5516c0a75961314334810df3f5b86cf754137";
// Verified against control_plane.native_continuation._request_key(HERMES_OPKEY).
const HERMES_REQUEST_DIGEST =
  "c79537e8b84ffb4c83a3273e5b7a20372a268350f4b8a34de1dbfe0414de6ec9";
const HERMES_READ_REF = "session-reply-" + HERMES_REQUEST_DIGEST;
const HERMES_REQUEST_REF = "session-bridge-continue:" + HERMES_REQUEST_DIGEST;

const fabricSelection = { workRef: WS, rootJobId: ROOT };
const hermesSelection: ExecutiveSessionSelection = {
  workRef: WS, rootJobId: ROOT, targetKind: "hermes_secretary",
};

const fabricRow = {
  target_ref: FABRIC_REF,
  generation: "a".repeat(24),
  addressable: true,
  kind: "fabric_attempt",
  continuation_operation_key: FABRIC_OPKEY,
  work_ref: WS,
  root_job_id: ROOT,
};

const hermesRow = {
  target_ref: HERMES_REF,
  generation: HERMES_GEN,
  addressable: true,
  kind: "hermes_secretary",
  continuation_operation_key: HERMES_OPKEY,
  work_ref: WS,
  root_job_id: ROOT,
};

const envelope = (operation: string, patch: Record<string, unknown>) => ({
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
  selection: Record<string, unknown>,
  state: "RESOLVED" | "UNAVAILABLE" | "AMBIGUOUS" = "RESOLVED",
  targetRow: unknown = hermesRow,
) => ({
  schema: "mastermind.os.executive.session_context.v1",
  principal_scope: SCOPE,
  verified_expiry: 4102444800,
  selection,
  selection_state: state,
  target: state === "RESOLVED" ? targetRow : null,
  capabilities: { send: state === "RESOLVED", reply_read: true, stop: false },
});

const admission = (patch: Record<string, unknown> = {}) => ({
  admission_id: "admission-1",
  sequence: 1,
  status: "queued",
  outcome: null,
  authority_epoch: 1,
  execution_generation: 0,
  ...patch,
});

const nativeResult = (patch: Record<string, unknown> = {}) => ({
  schema: "mastermind.session_bridge.hermes_secretary_result.v1",
  target_ref: HERMES_REF,
  operation_key: HERMES_OPKEY,
  read_ref: HERMES_READ_REF,
  request_ref: HERMES_REQUEST_REF,
  request_revision: "d".repeat(64),
  native_input_sha256: "e".repeat(64),
  commit_started: true,
  native_status: "ADMITTED",
  admission: admission(),
  answer: null,
  successful: null,
  parent_consumed: false,
  ...patch,
});

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
  // The backend echoes the exact requested selection variant and projects the
  // target row of that same kind.
  let contextResponse: unknown = null;
  let sendResponse: unknown = envelope("send", {
    ok: true,
    effect: "CONTINUATION_COMMITTED",
    operation_key: HERMES_OPKEY,
    data: nativeResult(),
  });
  let replyResponse: unknown = envelope("reply", {
    ok: true,
    effect: "CONTINUATION_COMMITTED",
    operation_key: HERMES_OPKEY,
    data: nativeResult(),
  });
  const f = {
    calls: { context: 0, send: 0, reply: 0 },
    contextSelections: [] as ExecutiveSessionSelection[],
    sendArgs: [] as SessionSendArguments[],
    replyArgs: [] as Array<{ operation_key: string }>,
    transport: null as unknown as ExecutiveSessionTransport,
    setContext(value: unknown) { contextResponse = value; },
    setSend(value: unknown) { sendResponse = value; },
    setReply(value: unknown) { replyResponse = value; },
    bumpAuth() { authGen++; },
  };
  f.transport = {
    authGeneration: () => authGen,
    available: () => true,
    subscribe: () => () => undefined,
    context: vi.fn(async (selected: ExecutiveSessionSelection) => {
      f.calls.context++;
      f.contextSelections.push(selected);
      if (contextResponse !== null) return contextResponse;
      const kind = sessionTargetKind(selected);
      return envelope("context", {
        data: contextData(
          kind === "hermes_secretary"
            ? { work_ref: WS, root_job_id: ROOT, target_kind: "hermes_secretary" }
            : { work_ref: WS, root_job_id: ROOT },
          "RESOLVED",
          kind === "hermes_secretary" ? hermesRow : fabricRow,
        ),
      });
    }),
    send: vi.fn(async (args: SessionSendArguments) => {
      f.calls.send++;
      f.sendArgs.push(args);
      return sendResponse;
    }),
    reply: vi.fn(async (args: { operation_key: string }) => {
      f.calls.reply++;
      f.replyArgs.push(args);
      return replyResponse;
    }),
  };
  return f;
}

const disposables: Array<() => void> = [];
afterEach(() => {
  for (const dispose of disposables.splice(0)) dispose();
});

function mount(f: ReturnType<typeof fixture>, options: {
  selection?: () => ExecutiveSessionSelection | null;
  store?: PendingPointerStore;
} = {}) {
  const handle = createExecutiveSessionBinding({
    transport: f.transport,
    store: options.store ?? memStore().store,
    selection: options.selection ?? (() => hermesSelection),
    clock: () => 1_000_000,
    stopCondition: () => undefined,
  });
  disposables.push(handle.dispose);
  return handle;
}

const hermesIntent: CommandIntent = {
  kind: "message",
  targetKey: HERMES_REF,
  payload: {
    instruction: "Summarise the retained thread.",
    stop_condition: "Stop after the summary.",
    work_ref: WS,
    root_job_id: ROOT,
  },
};

// ── The closed selection ──────────────────────────────────────────────────────

describe("the closed session selection", () => {
  it("keeps the incumbent fabric wire byte-identical and names an explicit Secretary target", () => {
    expect(sessionSelectionWire(fabricSelection)).toEqual({
      work_ref: WS, root_job_id: ROOT,
    });
    expect(sessionSelectionWire(hermesSelection)).toEqual({
      work_ref: WS, root_job_id: ROOT, target_kind: "hermes_secretary",
    });
  });

  it("normalizes an omitted kind to fabric and refuses a null or unsupported one", () => {
    expect(sessionTargetKind(fabricSelection)).toBe("fabric_attempt");
    expect(sessionTargetKind(hermesSelection)).toBe("hermes_secretary");
    expect(sessionTargetKind({ workRef: WS, rootJobId: ROOT, targetKind: null })).toBeNull();
    expect(sessionTargetKind({ workRef: WS, rootJobId: ROOT, targetKind: "codex" })).toBeNull();
    expect(sessionTargetKind({ workRef: WS, rootJobId: ROOT, targetKind: 7 })).toBeNull();
  });

  it("joins a context only under the same normalized kind", () => {
    const hermesEcho = envelope("context", {
      data: contextData({ work_ref: WS, root_job_id: ROOT, target_kind: "hermes_secretary" }),
    });
    expect(decodeSessionContext(hermesEcho, hermesSelection)?.selectionState).toBe("RESOLVED");
    // A fabric request never accepts a Secretary echo, and the reverse holds.
    expect(decodeSessionContext(hermesEcho, fabricSelection)).toBeNull();
    const fabricEcho = envelope("context", {
      data: contextData({ work_ref: WS, root_job_id: ROOT }),
    });
    expect(decodeSessionContext(fabricEcho, hermesSelection)).toBeNull();
  });

  it("refuses a target row whose kind, prefix, generation or key disagree", () => {
    const echo = envelope("context", {
      data: contextData({ work_ref: WS, root_job_id: ROOT, target_kind: "hermes_secretary" }),
    });
    for (const row of [
      { ...hermesRow, kind: "fabric_attempt" },
      { ...hermesRow, generation: "b".repeat(24) },
      { ...hermesRow, addressable: false },
      { ...hermesRow, target_ref: "hermes_secretary:" + "f".repeat(64) },
    ]) {
      expect(decodeSessionContext(
        envelope("context", {
          data: contextData(
            { work_ref: WS, root_job_id: ROOT, target_kind: "hermes_secretary" }, "RESOLVED", row,
          ),
        }),
        hermesSelection,
      )).toBeNull();
    }
  });
});

// ── The native public result ─────────────────────────────────────────────────

describe("the closed native public result", () => {
  it("accepts exactly thirteen keys joined to the original request", async () => {
    const decoded = await decodeHermesPublicResult(nativeResult());
    expect(decoded?.operation_key).toBe(HERMES_OPKEY);
    expect(decoded?.read_ref).toBe(HERMES_READ_REF);
    expect(decoded?.parent_consumed).toBe(false);
  });

  it("refuses an extra field, a wrong identity join and an unsafe integer", async () => {
    expect(await decodeHermesPublicResult({ ...nativeResult(), extra: "private" })).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ operation_key: "session-continue-" + "f".repeat(64) }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ target_ref: "hermes_secretary:" + "f".repeat(64) }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ admission: admission({ sequence: Number.MAX_SAFE_INTEGER + 2 }) }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ admission: admission({ sequence: 0 }) }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ admission: admission({ execution_generation: -1 }) }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ admission: admission({ admission_id: "badid" }) }),
    )).toBeNull();
  });

  it("refuses the malformed null rules of an uncommitted request", async () => {
    const committed = nativeResult({ commit_started: false, native_status: null, admission: null });
    expect(await decodeHermesPublicResult(committed)).not.toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ commit_started: false, native_status: "ADMITTED" }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ commit_started: false, admission: admission() }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ native_status: "REFUSED", admission: admission() }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ native_status: "OBSERVED", answer: "text", successful: true }),
    )).toBeNull();
    expect(await decodeHermesPublicResult(
      nativeResult({ native_status: "OBSERVED", successful: true }),
    )).toBeNull();
  });

  it("measures the installed budget in canonical ASCII JSON, not UTF-8 bytes", async () => {
    // 5 000 astral characters are 10 000 UTF-8 bytes but 60 000 canonical
    // ASCII characters: the escaped form exceeds the 23 KiB budget.
    const answer = "\u{1f9ea}".repeat(5000);
    expect(new TextEncoder().encode(answer).length).toBeLessThan(MAX_PUBLIC_RESULT_BYTES);
    const oversize = nativeResult({
      native_status: "OBSERVED",
      admission: admission({ status: "terminal" }),
      answer,
      successful: true,
    });
    expect(canonicalAsciiLength(oversize)).toBeGreaterThan(MAX_PUBLIC_RESULT_BYTES);
    expect(await decodeHermesPublicResult(oversize)).toBeNull();
  });
});

// ── The native phases ─────────────────────────────────────────────────────────

describe("the native phase vocabulary", () => {
  it("shows only the evidence the producer actually returned", async () => {
    const cases: Array<[Record<string, unknown>, string]> = [
      [nativeResult({ commit_started: false, native_status: null, admission: null }),
        "REQUEST_RECORDED"],
      [nativeResult({ native_status: "ADMITTED", admission: admission({ status: "queued" }) }),
        "QUEUED"],
      [nativeResult({ native_status: "ADMITTED", admission: admission({ status: "started" }) }),
        "RUNNING"],
      [nativeResult({ native_status: "ADMITTED", admission: admission({ status: "unknown" }) }),
        "OUTCOME_UNKNOWN"],
      [nativeResult({ native_status: "EFFECT_UNKNOWN", admission: null }),
        "OUTCOME_UNKNOWN"],
      [nativeResult({ native_status: "OBSERVED", admission: admission({ status: "terminal" }) }),
        "TURN_ENDED"],
      [nativeResult({
        native_status: "OBSERVED", admission: admission({ status: "terminal" }),
        answer: "The retained answer.", successful: true,
      }), "REPLY_AVAILABLE"],
      [nativeResult({
        native_status: "OBSERVED", admission: admission({ status: "terminal" }),
        answer: "The retained answer.", successful: false,
      }), "UNSUCCESSFUL_RESULT"],
      [nativeResult({ native_status: "REFUSED", admission: null }), "REFUSED"],
      [nativeResult({ native_status: "NOT_SUBMITTED", admission: null }), "NOT_SUBMITTED"],
      [nativeResult({ native_status: "UNAVAILABLE", admission: null }), "UNAVAILABLE"],
    ];
    for (const [frame, phase] of cases) {
      const decoded = await decodeHermesPublicResult(frame);
      expect(decoded).not.toBeNull();
      expect(sessionNativePhase(decoded)).toBe(phase);
    }
    expect(sessionNativePhase(null)).toBeNull();
  });
});

// ── The qualified SEND and answer ─────────────────────────────────────────────

describe("the qualified Secretary send and answer", () => {
  it("sends once and reports a recorded request without claiming a native effect", async () => {
    const f = fixture();
    f.setSend(envelope("send", {
      ok: true, effect: "NONE", operation_key: HERMES_OPKEY,
      data: nativeResult({ commit_started: false, native_status: null, admission: null }),
    }));
    const handle = mount(f);
    await handle.ready;
    const intent = handle.binding.makeSessionMessageIntent(
      HERMES_REF, "Summarise the retained thread.", "Stop after the summary.",
    );
    expect(intent).not.toBeNull();
    const pointer = handle.binding.port.prepare(intent!);
    const dispatch = await handle.binding.port.submitQualified(pointer, intent!, new AbortController().signal);
    expect(dispatch.receipt.disposition).toBe("accepted");
    expect(dispatch.nativeResult?.commit_started).toBe(false);
    expect(f.calls.send).toBe(1);
  });

  it("keeps a committed refusal unresolved on the original pointer", async () => {
    const f = fixture();
    f.setSend(envelope("send", {
      ok: false, effect: "UNKNOWN", operation_key: HERMES_OPKEY,
      data: null, error: { code: "effect_unknown", message: "unknown" },
    }));
    const { store, hints } = memStore();
    const handle = mount(f, { store });
    await handle.ready;
    const intent = handle.binding.makeSessionMessageIntent(
      HERMES_REF, "Summarise the retained thread.", "Stop after the summary.",
    )!;
    const pointer = handle.binding.port.prepare(intent);
    const controller = new OperationController(
      createAwaitingAnswerPort({
        port: handle.binding.port,
        readAnswer: (p, signal) => handle.binding.port.readQualifiedAnswer(p, signal),
        isCurrent: () => true,
        onAnswer: () => true,
      }),
      store,
    );
    const state = await controller.begin(intent);
    expect(state.status).not.toBe("accepted");
    // The original pointer stays retained: nothing proved a terminal answer.
    expect(hints.size).toBe(1);
  });

  it("publishes the native answer variant and keeps the fabric answer unchanged", async () => {
    const f = fixture();
    f.setReply(envelope("reply", {
      ok: true, effect: "CONTINUATION_COMMITTED", operation_key: HERMES_OPKEY,
      data: nativeResult({
        native_status: "OBSERVED",
        admission: admission({ status: "terminal" }),
        answer: "The retained answer.",
        successful: true,
      }),
    }));
    const handle = mount(f);
    await handle.ready;
    const pointer: OperationPointer = {
      operationKey: HERMES_OPKEY, kind: "message", targetKey: HERMES_REF,
    };
    const read = await handle.binding.port.readQualifiedAnswer(pointer, new AbortController().signal);
    expect(read.receipt.disposition).toBe("accepted");
    expect(read.answer).toEqual({
      kind: "hermes_secretary",
      text: "The retained answer.",
      successful: true,
      readRef: HERMES_READ_REF,
      parentConsumed: false,
      nextStep: null,
    });
    expect(read.nativeResult?.native_status).toBe("OBSERVED");
  });

  it("never publishes a foreign or malformed native frame", async () => {
    const f = fixture();
    f.setReply(envelope("reply", {
      ok: true, effect: "CONTINUATION_COMMITTED", operation_key: HERMES_OPKEY,
      data: nativeResult({ operation_key: "session-continue-" + "f".repeat(64) }),
    }));
    const handle = mount(f);
    await handle.ready;
    const pointer: OperationPointer = {
      operationKey: HERMES_OPKEY, kind: "message", targetKey: HERMES_REF,
    };
    const read = await handle.binding.port.readQualifiedAnswer(pointer, new AbortController().signal);
    expect(read.receipt.disposition).toBe("unknown");
    expect(read.answer).toBeNull();
    expect(read.nativeResult).toBeNull();
  });

  it("refuses a frame mutated during validation", async () => {
    const f = fixture();
    const data = nativeResult({
      native_status: "OBSERVED",
      admission: admission({ status: "terminal" }),
      answer: "The retained answer.",
      successful: true,
    });
    f.setReply(envelope("reply", {
      ok: true, effect: "CONTINUATION_COMMITTED", operation_key: HERMES_OPKEY, data,
    }));
    const handle = mount(f);
    await handle.ready;
    const pointer: OperationPointer = {
      operationKey: HERMES_OPKEY, kind: "message", targetKey: HERMES_REF,
    };
    // The frame mutates while the immutable correlation is awaited: the
    // published answer must not follow the late mutation.
    const nativeDigest = crypto.subtle.digest.bind(crypto.subtle);
    let finish!: () => void;
    const hashSpy = vi.spyOn(crypto.subtle, "digest").mockImplementation(async (algo, bytes) => {
      const result = await nativeDigest(algo, bytes);
      await new Promise<void>((resolve) => { finish = resolve; });
      return result;
    });
    try {
      const pending = handle.binding.port.readQualifiedAnswer(
        pointer, new AbortController().signal,
      );
      await vi.waitFor(() => expect(finish).toBeDefined());
      (data as Record<string, unknown>).answer = "unreviewed late content";
      hashSpy.mockRestore(); finish();
      const observed = await pending;
      expect(observed.receipt.disposition).toBe("unknown");
      expect(observed.answer).toBeNull();
      expect(f.calls.send).toBe(0);
    } finally {
      hashSpy.mockRestore();
      if (finish) finish();
    }
  });

  it("recovers the original operation without a new send target", async () => {
    const f = fixture();
    f.setReply(envelope("reply", {
      ok: true, effect: "CONTINUATION_COMMITTED", operation_key: HERMES_OPKEY,
      data: nativeResult({
        native_status: "OBSERVED",
        admission: admission({ status: "terminal" }),
        answer: "The retained answer.",
        successful: true,
      }),
    }));
    const handle = mount(f);
    await handle.ready;
    const pointer: OperationPointer = {
      operationKey: HERMES_OPKEY, kind: "message", targetKey: HERMES_REF,
    };
    const read = await handle.binding.port.readQualifiedAnswer(pointer, new AbortController().signal);
    expect(f.calls.reply).toBe(1);
    expect(f.calls.send).toBe(0);
    // Recovery never looks up current targets, never creates another
    // operation and never consults another backend.
    expect(f.calls.context).toBe(1);
    expect(f.replyArgs).toEqual([{ operation_key: HERMES_OPKEY }]);
    expect(read.receipt.disposition).toBe("accepted");
    expect(read.answer?.text).toBe("The retained answer.");
  });
});

// ── Kind transitions ──────────────────────────────────────────────────────────

describe("kind transitions", () => {
  it("invalidates the qualified session when the kind changes and back", async () => {
    const f = fixture();
    let current: ExecutiveSessionSelection = hermesSelection;
    const handle = mount(f, { selection: () => current });
    await handle.ready;
    expect(handle.sessionState()?.target?.kind).toBe("hermes_secretary");

    current = fabricSelection;
    await handle.refresh();
    // The kind change re-qualifies the host: the previous Secretary target
    // is gone and the incumbent fabric target is projected instead.
    expect(handle.sessionState()?.target?.kind).toBe("fabric_attempt");
    expect(f.contextSelections.at(-1)?.targetKind).toBeUndefined();

    current = hermesSelection;
    await handle.refresh();
    expect(handle.sessionState()?.target?.kind).toBe("hermes_secretary");
    expect(f.contextSelections.at(-1)?.targetKind).toBe("hermes_secretary");
    expect(f.calls.context).toBe(3);
  });

  it("never answers a fabric selection with a Secretary target", async () => {
    const f = fixture();
    f.setContext(envelope("context", {
      data: contextData({ work_ref: WS, root_job_id: ROOT }, "RESOLVED", hermesRow),
    }));
    const handle = mount(f, { selection: () => fabricSelection });
    await handle.ready;
    expect(handle.sessionState()).toBeNull();
  });
});


describe("native consumer validation repairs", () => {
  it("detaches the admission before asynchronous hashing", async () => {
    const raw = nativeResult();
    const pending = decodeHermesPublicResult(raw);
    const borrowed = raw.admission as Record<string, unknown>;
    borrowed.status = "terminal";
    borrowed.extra = "late";
    const decoded = await pending;
    expect(decoded?.admission?.status).toBe("queued");
    expect(decoded?.admission).not.toHaveProperty("extra");
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.admission)).toBe(true);
  });

  it("cannot shrink the measured frame while retaining an oversized captured answer", async () => {
    const raw = nativeResult({
      native_status: "OBSERVED", admission: admission({ status: "terminal" }),
      answer: "\u{1f9ea}".repeat(5000), successful: true,
    });
    const pending = decodeHermesPublicResult(raw);
    raw.answer = "short";
    expect(await pending).toBeNull();
  });

  it("rejects invalid UTF-8 admission strings and accepts the permitted empty outcome", async () => {
    for (const field of ["admission_id", "outcome"]) {
      expect(await decodeHermesPublicResult(
        nativeResult({ admission: admission({ [field]: "\ud800" }) }),
      )).toBeNull();
    }
    expect(await decodeHermesPublicResult(
      nativeResult({ admission: admission({ outcome: "" }) }),
    )).not.toBeNull();
  });

  it.each(["send", "reply"] as const)("withholds a %s frame with a contradictory effect", async (operation) => {
    const f = fixture();
    const frame = nativeResult({
      native_status: "OBSERVED", admission: admission({ status: "terminal" }),
      answer: "Actual terminal answer.", successful: true,
    });
    const wrong = envelope(operation, { effect: "NONE", operation_key: HERMES_OPKEY, data: frame });
    if (operation === "send") f.setSend(wrong); else f.setReply(wrong);
    const handle = mount(f);
    await handle.ready;
    const pointer: OperationPointer = {
      operationKey: HERMES_OPKEY, kind: "message", targetKey: HERMES_REF,
    };
    if (operation === "send") {
      const intent = handle.binding.makeSessionMessageIntent(HERMES_REF, "Summarise.", "Stop after summary.")!;
      const result = await handle.binding.port.submitQualified(pointer, intent, new AbortController().signal);
      expect(result.receipt.disposition).toBe("unknown");
      expect(result.nativeResult).toBeNull();
      expect(f.calls.send).toBe(1);
    } else {
      const result = await handle.binding.port.readQualifiedAnswer(pointer, new AbortController().signal);
      expect(result.receipt.disposition).toBe("unknown");
      expect(result.nativeResult).toBeNull();
      expect(result.answer).toBeNull();
      expect(f.calls.send).toBe(0);
    }
  });

  it("retains the actual native refusal phase after one SEND", async () => {
    const f = fixture();
    f.setSend(envelope("send", {
      effect: "UNKNOWN", operation_key: HERMES_OPKEY,
      data: nativeResult({ native_status: "REFUSED", admission: null }),
    }));
    const handle = mount(f);
    await handle.ready;
    const intent = handle.binding.makeSessionMessageIntent(HERMES_REF, "Summarise.", "Stop after summary.")!;
    const pointer = handle.binding.port.prepare(intent);
    const result = await handle.binding.port.submitQualified(pointer, intent, new AbortController().signal);
    expect(result.receipt.disposition).toBe("unknown");
    expect(result.nativeResult?.native_status).toBe("REFUSED");
    expect(f.calls.send).toBe(1);
  });
});

describe("rendered original answer custody", () => {
  it("never acknowledges equal text for a different unrendered pointer", async () => {
    const hook = renderHook(useQualifiedOriginalAnswer);
    disposables.push(hook.unmount);
    const owner = { binding: {}, principalScope: SCOPE, generation: HERMES_GEN,
      selectionSeq: 1, authRevision: 1 };
    const pointer: OperationPointer = { kind: "message",
      operationKey: HERMES_OPKEY, targetKey: HERMES_REF };
    const answer = { kind: "hermes_secretary" as const, text: "",
      successful: false, readRef: HERMES_READ_REF, parentConsumed: false as const,
      nextStep: null };
    act(() => hook.result.current.setCurrent({ ...owner, active: true }));
    let pending!: Promise<boolean>;
    act(() => { pending = hook.result.current.stage(owner, pointer, answer); });
    const rendered = hook.result.current.visible(owner);
    expect(rendered).not.toBeNull();
    act(() => hook.result.current.acknowledgeRender(rendered!));
    await expect(pending).resolves.toBe(true);
    await expect(hook.result.current.stage(owner, { ...pointer }, { ...answer }))
      .resolves.toBe(true);
    for (const foreign of [
      { ...pointer, operationKey: FABRIC_OPKEY },
      { ...pointer, targetKey: FABRIC_REF },
      { ...pointer, kind: "launch" as const },
    ]) {
      await expect(hook.result.current.stage(owner, foreign, { ...answer }))
        .resolves.toBe(false);
    }
    expect(hook.result.current.visible(owner)?.pointer).toEqual(pointer);
  });
});

describe("Meta shares the native owner with exact family joins", () => {
  const selection: ExecutiveSessionSelection = {
    workRef: metaFixture.selection.work_ref,
    rootJobId: metaFixture.selection.root_job_id,
    targetKind: "hermes_meta",
  };
  const pointer: OperationPointer = {
    kind: "message", operationKey: metaFixture.arguments.operation_key,
    targetKey: metaFixture.arguments.target_ref,
  };
  function meta() {
    const f = fixture();
    f.setContext(metaFixture.context);
    f.setSend(metaFixture.sent);
    f.setReply(metaFixture.reply);
    return f;
  }

  it("decodes the real Meta producer and preserves its exact selection and original references", async () => {
    expect(sessionSelectionWire(selection)).toEqual(metaFixture.selection);
    expect(decodeSessionContext(metaFixture.context, selection)?.target?.kind).toBe("hermes_meta");
    expect(decodeSessionContext(metaFixture.context, {...selection, targetKind: "hermes_secretary"})).toBeNull();
    const result = await decodeHermesPublicResult(metaFixture.reply.data);
    expect(result).toEqual(metaFixture.reply.data);
    expect(sessionNativePhase(result)).toBe("REPLY_AVAILABLE");
    const f = meta(), handle = mount(f, {selection: () => selection});
    await handle.ready;
    const read = await handle.binding.port.readQualifiedAnswer(pointer, new AbortController().signal);
    expect(read.answer).toEqual({
      kind: "hermes_meta", text: metaFixture.reply.data.answer, successful: true,
      readRef: metaFixture.reply.data.read_ref, parentConsumed: false, nextStep: null,
    });
    expect(f.replyArgs).toEqual([{operation_key: pointer.operationKey}]);
    expect(f.calls.send).toBe(0);
  });

  it("refuses cross-family schemas, targets and operation domains", async () => {
    for (const patch of [
      {schema: "mastermind.session_bridge.hermes_secretary_result.v1"},
      {target_ref: HERMES_REF}, {operation_key: HERMES_OPKEY},
      {schema: []}, {schema: "mastermind.session_bridge.hermes_meta_result.v2"},
    ]) {
      expect(await decodeHermesPublicResult({...metaFixture.reply.data, ...patch})).toBeNull();
    }
    expect(await decodeHermesPublicResult({
      ...nativeResult(), schema: "mastermind.session_bridge.hermes_meta_result.v1",
    })).toBeNull();
  });

  it("will not promote a valid other-family result returned for the original Meta operation", async () => {
    const f = meta();
    const foreign = nativeResult({
      native_status: "OBSERVED", admission: admission({status: "terminal"}),
      answer: "Valid Secretary answer.", successful: true,
    });
    expect(await decodeHermesPublicResult(foreign)).not.toBeNull();
    f.setReply(envelope("reply", {effect: "CONTINUATION_COMMITTED",
      operation_key: pointer.operationKey, data: foreign}));
    const handle = mount(f, {selection: () => selection});
    await handle.ready;
    const read = await handle.binding.port.readQualifiedAnswer(pointer, new AbortController().signal);
    expect(read.receipt.disposition).toBe("unknown");
    expect(read.answer).toBeNull();
    expect(f.calls.send).toBe(0);
  });

  it("captures the Meta family and admission before asynchronous validation", async () => {
    const raw = structuredClone(metaFixture.reply.data);
    const pending = decodeHermesPublicResult(raw);
    raw.schema = "mastermind.session_bridge.hermes_secretary_result.v1";
    raw.admission.status = "queued";
    const result = await pending;
    expect(result?.schema).toBe("mastermind.session_bridge.hermes_meta_result.v1");
    expect(result?.admission?.status).toBe("terminal");
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result?.admission)).toBe(true);
  });

  it("does not accept equal Meta text when its success outcome or family differs", async () => {
    const hook = renderHook(useQualifiedOriginalAnswer);
    disposables.push(hook.unmount);
    const owner = {binding: {}, principalScope: SCOPE, generation: HERMES_GEN,
      selectionSeq: 1, authRevision: 1};
    const answer = {kind: "hermes_meta" as const, text: metaFixture.reply.data.answer,
      successful: true, readRef: metaFixture.reply.data.read_ref,
      parentConsumed: false as const, nextStep: null};
    act(() => hook.result.current.setCurrent({...owner, active: true}));
    let pending!: Promise<boolean>;
    act(() => {pending = hook.result.current.stage(owner, pointer, answer);});
    const rendered = hook.result.current.visible(owner)!;
    act(() => hook.result.current.acknowledgeRender(rendered));
    await expect(pending).resolves.toBe(true);
    await expect(hook.result.current.stage(owner, pointer, {...answer})).resolves.toBe(true);
    await expect(hook.result.current.stage(owner, pointer, {...answer, successful: false})).resolves.toBe(false);
    await expect(hook.result.current.stage(owner, pointer,
      {...answer, kind: "hermes_secretary"})).resolves.toBe(false);
    expect(hook.result.current.visible(owner)?.answer).toEqual(answer);
  });
});
