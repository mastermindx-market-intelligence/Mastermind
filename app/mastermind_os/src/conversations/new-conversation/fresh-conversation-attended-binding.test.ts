/**
 * Real Vitest tests for the attended fresh-conversation binding over the
 * actual incumbent OperationController core and an atomic memory
 * PendingPointerStore, driven entirely by the genuine A4E6 same-run raw
 * consume_status / turn_preview / turn / turn_read / turn_status / duplicate
 * five-field frames and the strict sealed-body initial_read window of the
 * provided SAME-run fixture. Deterministic public 20-byte CSPRNG draws:
 * first draw 21..40 (consume Keep), second draw 41..60 (fixture turn key).
 * Synthetic frames are used only for explicit negative cases. No App,
 * native, browser-IDB or live-backend proof is claimed here.
 */
import ownerFixture from "./fixtures/fresh-conversation-recovery-owner.json";
import { describe, it, beforeEach, afterEach, expect } from "vitest";
import type {
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "../../orchestration/operation-controller";
import type { FreshConversationOriginalSelector } from "../../orchestration/fresh-conversation-target";
import {
  createFreshConversationAttendedBinding,
  FRESH_CONVERSATION_ATTENDED_CLOSED,
  type FreshConversationAttendedBinding,
  type FreshConversationAttendedTransport,
  type FreshConversationOriginalRead,
} from "./fresh-conversation-attended-binding";
import { decodeFreshConversationWindow } from "../../conversations/fresh-conversation-reference";
import type { FreshConversationTurnRequest } from "./fresh-conversation-turn";

// ── Genuine A4E6 same-run fixture bodies (verbatim; never rewritten) ─────────

const RESULT_SCHEMA = "mastermind.executive.fresh_conversation_result.v1";
const TURN_DATA_SCHEMA = "mastermind.executive.fresh_conversation_turn_data.v1";
const TURN_PREVIEW_SCHEMA = "mastermind.executive.fresh_conversation_turn_preview.v1";
const WORK_REF = "WS:PROJECT-1A8ACA991A56C22F1E86C2F7FCB79412";
const CREATE_KEY = "mmos-conversation-create-0102030405060708090a0b0c0d0e0f1011121314";
const TURN_KEY = "mmos-conversation-turn-292a2b2c2d2e2f303132333435363738393a3b3c";
const TURN_MESSAGE = "Explain this project’s next bounded action. 下一步";
const INITIAL_DIGEST = "a7665e3e393dd1937c877113274cbbeeaec348bf19670b23b730027b478fffcc";
const TURN_RESULT_DIGEST = "a3f37e7e8d238d69e450c48ee3ca41827c7cd8f7e4f44d4521f4ca4a0c4c0f9b";
const PREVIEW_DIGEST = "891b0b4d8786d628a9e951091ebc185c6bb44b7236eabe524828d32ce7885069";

const REFERENCE = {
  schema: "mastermind.fresh_conversation_reference.v1",
  work_ref: WORK_REF,
  root_job_id: "JOB-001",
  root_event_id: 12,
  root_event_sha256: "904f731dae8fd9e4379fc2825565008a8245148c409737149bd7c16dda0726e7",
  principal_scope_sha256: "8f17765b3c75f8426560f03b76f9cf0da5f14b60680ab6628911aa0ea1007210",
} as const;

const LOCATOR = {
  work_ref: WORK_REF,
  root_job_id: "JOB-001",
  job_id: "JOB-002",
  attempt_id: "ATT-b4b9c6d4f11f4103bb8a54c3a8f7fc07",
} as const;

const CONSUMPTION = {
  state: "CONSUMED",
  event_id: 31,
  event_sha256: "48b6f5a243a12dfdd1dcb9857d2bc1400bfa40badbc3f30309ac7c5389c98d20",
  initial_digest: INITIAL_DIGEST,
} as const;

const ENVELOPE_INITIAL = {
  current_state: "complete",
  errors: [],
  job_id: "JOB-002",
  next_actions: [],
  role: "plan",
  role_result: {
    plan_attempt_id: "ATT-b4b9c6d4f11f4103bb8a54c3a8f7fc07",
    root_job_id: "JOB-001",
    schema_version: "mastermind.execution_plan/v1",
    steps: [
      {
        allowed_write_paths: [],
        attempt_limit: 1,
        business_impact: "routine",
        cost_class: "small",
        objective: "Perform one bounded read-only follow-up.",
        ordinal: 0,
        requested_authorities: ["READ"],
        review_required: false,
        step_id: "step-1",
        validation_ids: [],
      },
    ],
  },
  run_id: "ATT-b4b9c6d4f11f4103bb8a54c3a8f7fc07",
  schema_version: "mastermind.executive_orchestration_result/v1",
  status: "COMPLETED",
  summary: "Recovered one exact planner session.",
  validations: [],
  worker_id: "worker-a",
} as const;

const ENVELOPE_TURN = {
  ...ENVELOPE_INITIAL,
  summary: "Inert native follow-up answer.",
} as const;

/** Genuine strict sealed-body initial_read window (RETAINED epoch). */
const INITIAL_READ = {
  schema: "mastermind.fresh_conversation_window.v1",
  kind: "fresh_native",
  reference: REFERENCE,
  state: "RETAINED",
  locator: LOCATOR,
  epoch: {
    attempt_id: "ATT-b4b9c6d4f11f4103bb8a54c3a8f7fc07",
    binding_digest: "34b13ef7ddd62f705990060f49afacd520f27019e6e71f4f1d5fc9788ed42972",
    generation_digest: "27b85547ac8545a13abc6425dfbd42e3b691206ae09fad67cbcb23599a0773e5",
  },
  initial_message: "  新对话\nRead source.  ",
  initial_result: { digest: INITIAL_DIGEST, envelope: ENVELOPE_INITIAL },
  initial_consumption: null,
  turns: [],
  can_send: false,
  parent_consumed: false,
} as const;

const CONSUME_REQUEST = {
  work_ref: WORK_REF,
  reference: REFERENCE,
  initial_digest: INITIAL_DIGEST,
} as const;

const TURN_REQUEST_BASE = {
  work_ref: WORK_REF,
  reference: REFERENCE,
  initial_digest: INITIAL_DIGEST,
  message: TURN_MESSAGE,
  turn_key: TURN_KEY,
} as const;

const TURN_REQUEST_FULL = { ...TURN_REQUEST_BASE, preview_digest: PREVIEW_DIGEST } as const;

const LOST_CONSUME = {
  schema: RESULT_SCHEMA,
  operation: "consume",
  ok: false,
  data: null,
  error: { code: "effect_unknown", message: "Reconcile the original conversation operation" },
} as const;

/** Genuine consume_status receipt of the same run. */
const CONSUME_STATUS_FRAME = {
  schema: RESULT_SCHEMA,
  operation: "consume_status",
  ok: true,
  data: {
    schema: TURN_DATA_SCHEMA,
    work_ref: WORK_REF,
    operation_key: null,
    reference: REFERENCE,
    turn_key: null,
    state: "CONSUMED",
    effect: "COMMITTED",
    initial_consumption: CONSUMPTION,
    locator: LOCATOR,
    result: null,
    parent_consumed: false,
    can_send: false,
  },
  error: null,
} as const;

/** Genuine pure turn_preview of the same run. */
const TURN_PREVIEW_FRAME = {
  schema: RESULT_SCHEMA,
  operation: "turn_preview",
  ok: true,
  data: {
    schema: TURN_PREVIEW_SCHEMA,
    work_ref: WORK_REF,
    operation_key: null,
    reference: REFERENCE,
    turn_key: TURN_KEY,
    state: "TURN_READY",
    effect: "NONE",
    initial_consumption: CONSUMPTION,
    locator: LOCATOR,
    preview_digest: PREVIEW_DIGEST,
    parent_consumed: false,
    can_send: true,
  },
  error: null,
} as const;

const RECORDED_DATA = {
  schema: TURN_DATA_SCHEMA,
  work_ref: WORK_REF,
  operation_key: null,
  reference: REFERENCE,
  turn_key: TURN_KEY,
  state: "RECORDED",
  effect: "COMMITTED",
  initial_consumption: CONSUMPTION,
  locator: LOCATOR,
  result: { digest: TURN_RESULT_DIGEST, envelope: ENVELOPE_TURN },
  parent_consumed: false,
  can_send: false,
} as const;

/** Genuine turn receipt. */
const TURN_OK_FRAME = { schema: RESULT_SCHEMA, operation: "turn", ok: true, data: RECORDED_DATA, error: null };
/** The fixture's separate `duplicate` frame is byte-identical recorded output. */
const TURN_DUPLICATE_FRAME = { schema: RESULT_SCHEMA, operation: "turn", ok: true, data: RECORDED_DATA, error: null };
/** Genuine turn_status receipt. */
const TURN_STATUS_FRAME = { schema: RESULT_SCHEMA, operation: "turn_status", ok: true, data: RECORDED_DATA, error: null };
/** Genuine turn_read receipt. */
const TURN_READ_FRAME = { schema: RESULT_SCHEMA, operation: "turn_read", ok: true, data: RECORDED_DATA, error: null };

// ── Explicit synthetic negative fixtures ────────────────────────────────────

const CONSUME_STATUS_ABSENT = {
  schema: RESULT_SCHEMA,
  operation: "consume_status",
  ok: true,
  data: {
    schema: TURN_DATA_SCHEMA,
    work_ref: WORK_REF,
    operation_key: null,
    reference: REFERENCE,
    turn_key: null,
    state: "ABSENT",
    effect: "NONE",
    initial_consumption: null,
    locator: { work_ref: WORK_REF, root_job_id: "JOB-001", job_id: null, attempt_id: null },
    result: null,
    parent_consumed: false,
    can_send: false,
  },
  error: null,
} as const;

const REFUSED_CONSUME = {
  schema: RESULT_SCHEMA,
  operation: "consume",
  ok: false,
  data: null,
  error: { code: "refused", message: "closed locally by the producer" },
} as const;

const FUTURE_CODE_CONSUME = {
  schema: RESULT_SCHEMA,
  operation: "consume",
  ok: false,
  data: null,
  error: { code: "quantum_deferred", message: "a future producer code" },
} as const;

// ── Harness ──────────────────────────────────────────────────────────────────

type Method =
  | "consume"
  | "consumeStatus"
  | "turnPreview"
  | "turn"
  | "turnStatus"
  | "turnRead";

interface RecordedCall {
  readonly method: Method;
  readonly request: unknown;
}

type Handler = (
  request: FreshConversationTurnRequest,
  signal: AbortSignal,
) => Promise<unknown>;

/** Atomic in-memory PendingPointerStore over the incumbent contract. */
function memoryStore(): PendingPointerStore & { peek(): OperationPointer | null } {
  let pointer: OperationPointer | null = null;
  return {
    async read(_principalScope: string): Promise<OperationPointer | null> {
      return pointer;
    },
    async reserve(
      _principalScope: string,
      incoming: OperationPointer,
    ): Promise<
      | { readonly reserved: true }
      | { readonly reserved: false; readonly pointer: OperationPointer }
    > {
      if (pointer === null) {
        pointer = incoming;
        return { reserved: true };
      }
      return { reserved: false, pointer };
    },
    async clearIfEqual(
      _principalScope: string,
      target: OperationPointer,
    ): Promise<boolean> {
      if (
        pointer !== null &&
        pointer.operationKey === target.operationKey &&
        pointer.kind === target.kind &&
        pointer.targetKey === target.targetKey
      ) {
        pointer = null;
        return true;
      }
      return false;
    },
    peek(): OperationPointer | null {
      return pointer;
    },
  };
}

interface Harness {
  readonly calls: RecordedCall[];
  readonly store: ReturnType<typeof memoryStore>;
  readonly witness: { current: boolean };
  owner: OwnerContext | null;
  canModify: boolean;
  returnedSelection?: FreshConversationOriginalSelector;
  binding: FreshConversationAttendedBinding;
  script(method: Method, handler: Handler): void;
  setOwner(owner: OwnerContext | null): void;
  setCanModify(value: boolean): void;
  setWitnessCurrent(value: boolean): void;
  rebind(): FreshConversationAttendedBinding;
  currentRead(): Promise<FreshConversationOriginalRead | null>;
}

function buildHarness(): Harness {
  const harness: Harness = {
    calls: [],
    store: memoryStore(),
    witness: { current: true },
    owner: { principalScope: "principal-scope-a", generation: "generation-1" },
    canModify: true,
    binding: null as unknown as FreshConversationAttendedBinding,
    script(method: Method, handler: Handler): void {
      handlers.set(method, handler);
    },
    setOwner(owner: OwnerContext | null): void {
      harness.owner = owner;
    },
    setCanModify(value: boolean): void {
      harness.canModify = value;
    },
    setWitnessCurrent(value: boolean): void {
      harness.witness.current = value;
    },
    rebind(): FreshConversationAttendedBinding {
      return createFreshConversationAttendedBinding({
        owner: () => harness.owner,
        canModify: () => harness.canModify,
        transport,
        store: harness.store,
        readInitial,
      });
    },
    async currentRead(): Promise<FreshConversationOriginalRead | null> {
      return readInitial(
        { work_ref: WORK_REF, reference: REFERENCE } as FreshConversationOriginalSelector,
        new AbortController().signal,
      );
    },
  };

  const handlers = new Map<Method, Handler>();

  async function invoke(method: Method, request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown> {
    harness.calls.push({ method, request });
    const handler = handlers.get(method);
    if (handler === undefined) throw new Error(`unexpected ${method} transport call`);
    return handler(request, signal);
  }

  const transport: FreshConversationAttendedTransport = {
    consume: (request, signal) => invoke("consume", request, signal),
    consumeStatus: (request, signal) => invoke("consumeStatus", request, signal),
    turnPreview: (request, signal) => invoke("turnPreview", request, signal),
    turn: (request, signal) => invoke("turn", request, signal),
    turnStatus: (request, signal) => invoke("turnStatus", request, signal),
    turnRead: (request, signal) => invoke("turnRead", request, signal),
  };

  // Existing original-initial reader over the genuine strict sealed body.
  async function readInitial(
    selection: FreshConversationOriginalSelector,
    _signal: AbortSignal,
  ): Promise<FreshConversationOriginalRead | null> {
    if (!("reference" in selection)) return null;
    let window: ReturnType<typeof decodeFreshConversationWindow>;
    try {
      window = decodeFreshConversationWindow(INITIAL_READ, selection.reference);
    } catch {
      return null;
    }
    if (window.initial_result === null) return null;
    return {
      selection: harness.returnedSelection ?? selection,
      result: window.initial_result,
      locator: window.locator,
      current: () => harness.witness.current,
    };
  }

  harness.binding = harness.rebind();
  return harness;
}

/** Deterministic public 20-byte draws: 21..40 then 41..60 (never the fixture rewrite). */
const realCrypto = globalThis.crypto;
let draw = 0;
beforeEach(() => {
  draw = 0;
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: {
      getRandomValues(bytes: Uint8Array): Uint8Array {
        const start = draw === 0 ? 21 : 41;
        draw += 1;
        for (let i = 0; i < bytes.length; i += 1) bytes[i] = (start + i) & 0xff;
        return bytes;
      },
    },
  });
});
afterEach(() => {
  Object.defineProperty(globalThis, "crypto", { configurable: true, value: realCrypto });
});

async function drain(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function expectClosedError(thrown: unknown): void {
  expect(thrown instanceof Error).toBeTruthy();
  expect((thrown as Error).message).toBe(FRESH_CONVERSATION_ATTENDED_CLOSED);
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("fresh-conversation-attended-binding", () => {
  it("retains the exact actual same-run owner frames as test operands", () => {
    expect(INITIAL_READ).toEqual(ownerFixture.initial_read);
    expect(CONSUME_REQUEST).toEqual(ownerFixture.consume_request);
    expect(TURN_REQUEST_FULL).toEqual(ownerFixture.turn_request);
    expect(LOST_CONSUME).toEqual(ownerFixture.lost_consume);
    expect(CONSUME_STATUS_FRAME).toEqual(ownerFixture.consume_status);
    expect(TURN_PREVIEW_FRAME).toEqual(ownerFixture.turn_preview);
    expect(TURN_OK_FRAME).toEqual(ownerFixture.turn);
    expect(TURN_DUPLICATE_FRAME).toEqual(ownerFixture.duplicate);
    expect(TURN_STATUS_FRAME).toEqual(ownerFixture.status);
    expect(TURN_READ_FRAME).toEqual(ownerFixture.turn_read);
  });
  it("refuses a foreign reacquired initial-read selector before any original status request", async () => {
    const harness = buildHarness();
    harness.returnedSelection = {work_ref: WORK_REF, operation_key: CREATE_KEY};
    harness.script("consumeStatus", async () => CONSUME_STATUS_FRAME);
    await expect(harness.binding.readOriginalConsume(
      {work_ref: WORK_REF, reference: REFERENCE}, new AbortController().signal,
    )).rejects.toThrow();
    expect(harness.calls).toEqual([]);
  });

  it("retains the pending Keep when its reacquired initial-read selector differs", async () => {
    const harness = buildHarness();
    harness.script("consume", async () => LOST_CONSUME);
    harness.script("consumeStatus", async () => CONSUME_STATUS_FRAME);
    const read = await harness.currentRead();
    const intent = harness.binding.makeConsumeIntent(read!);
    await harness.binding.controller.begin(intent!);
    const original = harness.store.peek();
    harness.returnedSelection = {work_ref: WORK_REF, operation_key: CREATE_KEY};
    const outcome = await harness.rebind().controller.recover();
    expect(outcome.status).toBe("unknown");
    expect(harness.store.peek()).toEqual(original);
    expect(harness.calls.map(c => c.method)).toEqual(["consume"]);
  });
  it("never settles or clears another operation kind from the shared store", async () => {
    const harness = buildHarness();
    const original: OperationPointer = {kind: "conversation_create", operationKey: CREATE_KEY, targetKey: WORK_REF};
    await harness.store.reserve("principal-scope-a", original);
    const result = await harness.binding.controller.recover();
    expect(result.status).toBe("unknown");
    expect(harness.store.peek()).toEqual(original);
    expect(harness.calls).toEqual([]);
  });
  it("exposes exactly the fixed finite factory surface", () => {
    const harness = buildHarness();
    expect(Object.keys(harness.binding).sort()).toEqual([
      "context",
      "controller",
      "makeConsumeIntent",
      "makeTurnIntent",
      "makeTurnRequest",
      "previewTurn",
      "readOriginalConsume",
      "readOriginalTurn",
      "store",
    ]);
    expect(harness.binding.context()).toEqual({
      principalScope: "principal-scope-a",
      generation: "generation-1",
    });
  });

  it("a lost consume retains the pointer; a same-store successor recovers through consume_status only and clears on the actual receipt", async () => {
    const harness = buildHarness();
    harness.script("consume", async () => LOST_CONSUME);
    harness.script("consumeStatus", async () => CONSUME_STATUS_FRAME);
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const intent = harness.binding.makeConsumeIntent(read!);
    expect(intent).toBeTruthy();
    const first = await harness.binding.controller.begin(intent!);
    expect(first.status).toBe("unknown");
    expect(first.reason).toBe("UNKNOWN_RECEIPT");
    const kept = harness.store.peek();
    expect(kept === null).toBeFalsy();
    expect(kept!.kind).toBe("conversation_consume");
    // The local Keep is correlation only: exactly the closed wire on the transport.
    expect(harness.calls.length).toBe(1);
    expect(harness.calls[0]!.method).toBe("consume");
    expect(harness.calls[0]!.request).toEqual(CONSUME_REQUEST);
    expect(Object.keys(harness.calls[0]!.request as object).length).toBe(3);

    // A same-store successor never resubmits over the retained pointer.
    const successor = harness.rebind();
    const nextRead = await harness.currentRead();
    const nextIntent = successor.makeConsumeIntent(nextRead!);
    expect(nextIntent).toBeTruthy();
    const joined = await successor.controller.begin(nextIntent!);
    expect(joined.status).toBe("checking");
    expect(joined.reason).toBe("PENDING_POINTER");
    expect(harness.calls.length).toBe(1);

    // Recovery is consume_status only (even when reconcileSource is requested:
    // source reconcile never applies to these kinds) and clears on the receipt.
    const recovered = await successor.controller.recover({ reconcileSource: true });
    expect(recovered.status).toBe("accepted");
    expect(recovered.reason).toBe("ACCEPTED");
    expect(harness.store.peek()).toBeNull();
    expect(harness.calls.map((call) => call.method)).toEqual(["consume", "consumeStatus"]);
    expect(harness.calls[1]!.request).toEqual(CONSUME_REQUEST);
    expect(Object.keys(harness.calls[1]!.request as object).length).toBe(3);
  });

  it("an ABSENT consume_status stays conservatively unknown and pending", async () => {
    const harness = buildHarness();
    harness.script("consume", async () => LOST_CONSUME);
    harness.script("consumeStatus", async () => CONSUME_STATUS_ABSENT);
    const intent = harness.binding.makeConsumeIntent((await harness.currentRead())!);
    const first = await harness.binding.controller.begin(intent!);
    expect(first.status).toBe("unknown");
    const recovered = await harness.binding.controller.recover();
    expect(recovered.status).toBe("unknown");
    expect(recovered.reason).toBe("UNKNOWN_RECEIPT");
    const kept = harness.store.peek();
    expect(kept === null).toBeFalsy();
    expect(kept!.operationKey).toBe(recovered.pointer!.operationKey);
    expect(harness.calls.map((call) => call.method)).toEqual(["consume", "consumeStatus"]);
  });

  it("the attended turn is pure in preview, minted once, submitted once, accepted and cleared", async () => {
    const harness = buildHarness();
    harness.script("turnPreview", async () => TURN_PREVIEW_FRAME);
    harness.script("turn", async () => TURN_OK_FRAME);
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const request = harness.binding.makeTurnRequest(read!, TURN_MESSAGE);
    expect(request).toEqual(TURN_REQUEST_BASE);
    const signal = new AbortController().signal;
    const prepared = await harness.binding.previewTurn(read!, request!, signal);
    expect(prepared === null).toBeFalsy();
    expect(prepared!.preview.state).toBe("TURN_READY");
    expect(prepared!.preview.preview_digest).toBe(PREVIEW_DIGEST);
    expect(prepared!.request).toEqual(TURN_REQUEST_BASE);
    // Zero store writes and zero turn calls in the pure preflight.
    expect(harness.calls.map((call) => call.method)).toEqual(["turnPreview"]);
    expect(harness.store.peek()).toBeNull();

    const intent = harness.binding.makeTurnIntent(prepared!);
    expect(intent).toBeTruthy();
    const state = await harness.binding.controller.begin(intent!);
    expect(state.status).toBe("accepted");
    expect(state.reason).toBe("ACCEPTED");
    expect(harness.store.peek()).toBeNull();
    expect(harness.calls.map((call) => call.method)).toEqual(["turnPreview", "turn"]);
    expect(harness.calls[1]!.request).toEqual(TURN_REQUEST_FULL);
    expect(Object.keys(harness.calls[1]!.request as object).length).toBe(6);
  });

  it("a rapid duplicate begin of one minted turn submits exactly one effect", async () => {
    const harness = buildHarness();
    harness.script("turnPreview", async () => TURN_PREVIEW_FRAME);
    harness.script("turn", async () => TURN_DUPLICATE_FRAME);
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const request = harness.binding.makeTurnRequest(read!, TURN_MESSAGE);
    const prepared = await harness.binding.previewTurn(read!, request!, new AbortController().signal);
    const intent = harness.binding.makeTurnIntent(prepared!);
    const first = harness.binding.controller.begin(intent!);
    const second = harness.binding.controller.begin(intent!);
    const busy = await second;
    expect(busy.status).toBe("refused");
    expect(busy.reason).toBe("OPERATION_BUSY");
    expect(busy.pointer).toBeNull();
    const done = await first;
    expect(done.status).toBe("accepted");
    expect(harness.store.peek()).toBeNull();
    expect(harness.calls.filter((call) => call.method === "turn").length).toBe(1);
  });

  it("an unknown turn recovers by turn_status only; a withdrawn Workspace still reads the original; turn_read stays readonly", async () => {
    const harness = buildHarness();
    harness.script("turnPreview", async () => TURN_PREVIEW_FRAME);
    harness.script("turn", async () => {
      throw new Error("transport socket died");
    });
    harness.script("turnStatus", async () => TURN_STATUS_FRAME);
    harness.script("turnRead", async () => TURN_READ_FRAME);
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const request = harness.binding.makeTurnRequest(read!, TURN_MESSAGE);
    const prepared = await harness.binding.previewTurn(read!, request!, new AbortController().signal);
    const intent = harness.binding.makeTurnIntent(prepared!);
    const state = await harness.binding.controller.begin(intent!);
    expect(state.status).toBe("unknown");
    expect(state.reason).toBe("UNKNOWN_RECEIPT");
    const kept = harness.store.peek();
    expect(kept === null).toBeFalsy();
    expect(kept!.kind).toBe("conversation_turn");
    expect(kept!.operationKey).toBe(TURN_KEY);

    // Workspace withdrawn: the original status is still read, never a resend.
    harness.setCanModify(false);
    const recovered = await harness.binding.controller.recover();
    expect(recovered.status).toBe("accepted");
    expect(recovered.reason).toBe("ACCEPTED");
    expect(harness.store.peek()).toBeNull();
    expect(harness.calls.map((call) => call.method)).toEqual(["turnPreview", "turn", "turnStatus"]);
    expect(harness.calls[2]!.request).toEqual({
      work_ref: WORK_REF,
      reference: REFERENCE,
      turn_key: TURN_KEY,
    });

    // Explicit readback is turn_read only and returns the raw envelope verbatim.
    const raw = await harness.binding.readOriginalTurn(
      { work_ref: WORK_REF, reference: REFERENCE } as FreshConversationOriginalSelector,
      TURN_KEY,
      new AbortController().signal,
    );
    expect(raw).toBe(TURN_READ_FRAME);
    expect(harness.calls.map((call) => call.method)).toEqual(["turnPreview", "turn", "turnStatus", "turnRead"]);
  });

  it("an owner change across the effect await withholds publication and retains the original pointer", async () => {
    const harness = buildHarness();
    let release!: () => void;
    const gate = new Promise<void>((done) => {
      release = done;
    });
    harness.script("consume", async () => {
      await gate;
      return LOST_CONSUME;
    });
    const intent = harness.binding.makeConsumeIntent((await harness.currentRead())!);
    const pending = harness.binding.controller.begin(intent!);
    await drain();
    expect(harness.calls.length).toBe(1);
    harness.setOwner({ principalScope: "principal-scope-a", generation: "generation-2" });
    release();
    const state = await pending;
    // Not a private-view publication: the epoch is voided and the hint stays.
    expect(state.status).toBe("idle");
    expect(state.reason).toBe("EPOCH_CHANGED");
    expect(harness.store.peek()!.kind).toBe("conversation_consume");
    expect(harness.calls.length).toBe(1);
  });

  it("a lost read witness after the reservation stays conservatively unknown", async () => {
    const harness = buildHarness();
    let release!: () => void;
    const gate = new Promise<void>((done) => {
      release = done;
    });
    harness.script("consume", async () => {
      await gate;
      return CONSUME_STATUS_FRAME;
    });
    const intent = harness.binding.makeConsumeIntent((await harness.currentRead())!);
    const pending = harness.binding.controller.begin(intent!);
    await drain();
    harness.setWitnessCurrent(false);
    release();
    const state = await pending;
    expect(state.status).toBe("unknown");
    expect(state.reason).toBe("UNKNOWN_RECEIPT");
    expect(harness.store.peek()!.kind).toBe("conversation_consume");
    // Even a genuinely CONSUMED receipt is withheld once the witness is lost.
    expect(harness.calls.length).toBe(1);
  });

  it("known pre-effect refusal codes close the submit; future codes stay unknown", async () => {
    const refused = buildHarness();
    refused.script("consume", async () => REFUSED_CONSUME);
    const refusedIntent = refused.binding.makeConsumeIntent((await refused.currentRead())!);
    const refusedState = await refused.binding.controller.begin(refusedIntent!);
    expect(refusedState.status).toBe("refused");
    expect(refusedState.reason).toBe("REFUSED");
    expect(refused.store.peek()).toBeNull();

    const future = buildHarness();
    future.script("consume", async () => FUTURE_CODE_CONSUME);
    const futureIntent = future.binding.makeConsumeIntent((await future.currentRead())!);
    const futureState = await future.binding.controller.begin(futureIntent!);
    expect(futureState.status).toBe("unknown");
    expect(futureState.reason).toBe("UNKNOWN_RECEIPT");
    expect(future.store.peek()!.kind).toBe("conversation_consume");
  });

  it("malformed foreign selectors, keys and extra target fields cause zero effects", async () => {
    const harness = buildHarness();
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const polluted = {
      work_ref: WORK_REF,
      reference: REFERENCE,
      extra: 1,
    } as unknown as FreshConversationOriginalSelector;
    const badRead: FreshConversationOriginalRead = {
      selection: polluted,
      result: read!.result,
      locator: read!.locator,
      current: () => true,
    };
    expect(harness.binding.makeConsumeIntent(badRead)).toBeNull();
    expect(harness.binding.makeTurnRequest(badRead, TURN_MESSAGE)).toBeNull();

    let foreign: unknown = null;
    try {
      await harness.binding.readOriginalConsume(
        { work_ref: "WS:OTHER", reference: { ...REFERENCE, work_ref: "WS:OTHER" } } as FreshConversationOriginalSelector,
        new AbortController().signal,
      );
    } catch (err) {
      foreign = err;
    }
    expectClosedError(foreign);

    let badKey: unknown = null;
    try {
      await harness.binding.readOriginalTurn(
        { work_ref: WORK_REF, reference: REFERENCE } as FreshConversationOriginalSelector,
        "mmos-conversation-turn-not-a-key",
        new AbortController().signal,
      );
    } catch (err) {
      badKey = err;
    }
    expectClosedError(badKey);

    // A reader that reacquires nothing never manufactures a context or digest.
    let absent: unknown = null;
    try {
      await harness.binding.readOriginalConsume(
        { work_ref: WORK_REF, operation_key: CREATE_KEY } as FreshConversationOriginalSelector,
        new AbortController().signal,
      );
    } catch (err) {
      absent = err;
    }
    expectClosedError(absent);
    expect(harness.calls.length).toBe(0);
  });

  it("readbacks return the original raw envelopes verbatim with no normalized surrogate", async () => {
    const harness = buildHarness();
    harness.script("consumeStatus", async () => CONSUME_STATUS_FRAME);
    harness.script("turnRead", async () => TURN_READ_FRAME);
    const consumeRaw = await harness.binding.readOriginalConsume(
      { work_ref: WORK_REF, reference: REFERENCE } as FreshConversationOriginalSelector,
      new AbortController().signal,
    );
    expect(consumeRaw).toBe(CONSUME_STATUS_FRAME);
    expect(harness.calls[0]!.request).toEqual(CONSUME_REQUEST);
    const turnRaw = await harness.binding.readOriginalTurn(
      { work_ref: WORK_REF, reference: REFERENCE } as FreshConversationOriginalSelector,
      TURN_KEY,
      new AbortController().signal,
    );
    expect(turnRaw).toBe(TURN_READ_FRAME);
    expect(harness.calls[1]!.request).toEqual({
      work_ref: WORK_REF,
      reference: REFERENCE,
      turn_key: TURN_KEY,
    });
    expect(harness.calls.map((call) => call.method)).toEqual(["consumeStatus", "turnRead"]);
  });

  it("new actions require the current witness, the live owner and Workspace availability", async () => {
    const harness = buildHarness();
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    expect(harness.binding.makeTurnRequest(read!, TURN_MESSAGE)).toBeTruthy();

    harness.setOwner(null);
    expect(harness.binding.makeConsumeIntent(read!)).toBeNull();
    expect(harness.binding.makeTurnRequest(read!, TURN_MESSAGE)).toBeNull();
    harness.setOwner({ principalScope: "principal-scope-a", generation: "generation-1" });

    harness.setCanModify(false);
    expect(harness.binding.makeConsumeIntent(read!)).toBeNull();
    expect(harness.binding.makeTurnRequest(read!, TURN_MESSAGE)).toBeNull();
    harness.setCanModify(true);

    harness.setWitnessCurrent(false);
    expect(harness.binding.makeConsumeIntent(read!)).toBeNull();
    expect(harness.binding.makeTurnRequest(read!, TURN_MESSAGE)).toBeNull();
    expect(harness.calls.length).toBe(0);
    expect(harness.store.peek()).toBeNull();
  });

  it("a stale prepared turn cannot be minted into an intent after the owner moved", async () => {
    const harness = buildHarness();
    harness.script("turnPreview", async () => TURN_PREVIEW_FRAME);
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const request = harness.binding.makeTurnRequest(read!, TURN_MESSAGE);
    const prepared = await harness.binding.previewTurn(read!, request!, new AbortController().signal);
    expect(prepared === null).toBeFalsy();
    harness.setOwner({ principalScope: "principal-scope-a", generation: "generation-9" });
    expect(harness.binding.makeTurnIntent(prepared!)).toBeNull();
    expect(harness.calls.map((call) => call.method)).toEqual(["turnPreview"]);
    expect(harness.store.peek()).toBeNull();
  });

  it("a hardened witness whose sealed proof does not bind the selector is refused locally", async () => {
    const harness = buildHarness();
    const read = await harness.currentRead();
    expect(harness.binding.makeConsumeIntent(read!)).toBeTruthy();
    const wrongLocator: FreshConversationOriginalRead = {
      selection: read!.selection,
      result: read!.result,
      locator: { ...read!.locator, root_job_id: "JOB-009" },
      current: () => true,
    };
    expect(harness.binding.makeConsumeIntent(wrongLocator)).toBeNull();
    expect(harness.binding.makeTurnRequest(wrongLocator, TURN_MESSAGE)).toBeNull();

    const tampered: FreshConversationOriginalRead = {
      selection: read!.selection,
      result: { ...read!.result, digest: "f".repeat(64) },
      locator: read!.locator,
      current: () => true,
    };
    expect(harness.binding.makeConsumeIntent(tampered)).toBeNull();
    expect(harness.calls.length).toBe(0);
    expect(harness.store.peek()).toBeNull();
  });
});
