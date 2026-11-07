/** Tests for the fresh-conversation consume/turn closed wire decoder.
 *
 * The genuine frames below are the captured d4bcad271f1a95dd730b18ea56f9d468
 * bad9658c attended turn fixture, embedded verbatim; the RECORDED result
 * envelope (identical in the turn/turn_status/turn_read/duplicate captures)
 * is factored once and referenced by the rebuilt outer frames — no fixture
 * value is rewritten, trimmed or normalized to fit the decoder. These tests
 * exercise wire syntax and closure only: nothing here consumes, sends,
 * transports or stores anything.
 */
import { describe, expect, it } from "vitest";
import { canonicalJson, sha256Hex } from "../../orchestration/operation-key";
import {
  decodeFreshConversationTurnResult,
  decodeFreshConversationTurnPreviewResult,
  validateFreshConversationReference,
  validateFreshConversationTurnRequest,
} from "./fresh-conversation-turn";
import type {
  FreshConversationReference,
  FreshConversationTurnOperation,
  FreshConversationTurnRequest,
} from "./fresh-conversation-turn";
import { decodeFreshConversationInitialResult } from "./fresh-conversation";

// ---- Genuine captured values (d4bcad271 fixture) ----

const WORK_REF = "WS:ONE";

const REFERENCE:FreshConversationReference = {
  schema: "mastermind.fresh_conversation_reference.v1",
  work_ref: "WS:ONE",
  root_job_id: "JOB-001",
  root_event_id: 2,
  root_event_sha256:
    "88eabd8cca4f01769ca165f5427341102c468e8f446217c9f6dd14795a64bc97",
  principal_scope_sha256:
    "76db24909023ea40db1a58bf5421e37222a4b36c7af79aad19c471b1cc597442",
};

const CONSUMPTION = {
  state: "CONSUMED",
  event_id: 21,
  event_sha256:
    "90b0d496f3b8e198ea9815b65e25a26a162db556881f2f8daefd8f50cb8f0681",
  initial_digest:
    "38b30c3d06cf50fbf009034fc820284cd7d495b02cdcc8c740f83e26b40377bb",
};

const LOCATOR = {
  work_ref: "WS:ONE",
  root_job_id: "JOB-001",
  job_id: "JOB-002",
  attempt_id: "ATT-72d71af1be384701876433e7d90c4553",
};

const RECORDED_ENVELOPE = {
  schema_version: "mastermind.executive_orchestration_result/v1",
  job_id: "JOB-002",
  run_id: "ATT-72d71af1be384701876433e7d90c4553",
  worker_id: "worker-a",
  role: "plan",
  status: "COMPLETED",
  role_result: {
    schema_version: "mastermind.execution_plan/v1",
    plan_attempt_id: "ATT-72d71af1be384701876433e7d90c4553",
    root_job_id: "JOB-001",
    steps: [
      {
        step_id: "step-1",
        ordinal: 0,
        objective: "Perform one bounded read-only follow-up.",
        requested_authorities: ["READ"],
        allowed_write_paths: [],
        validation_ids: [],
        attempt_limit: 1,
        cost_class: "small",
        business_impact: "routine",
        review_required: false,
      },
    ],
  },
  summary: "Inert native follow-up answer.",
  current_state: "complete",
  next_actions: [],
  errors: [],
  validations: [],
};

const RECORDED_RESULT = {
  digest: "d0212153e9a325ad9a380ecc16af7e54224ccad20b493d392021e3e6d126ad86",
  envelope: RECORDED_ENVELOPE,
};

const INITIAL_RESULT = {
  digest: "38b30c3d06cf50fbf009034fc820284cd7d495b02cdcc8c740f83e26b40377bb",
  envelope: {
    schema_version: "mastermind.executive_orchestration_result/v1",
    job_id: "JOB-002",
    run_id: "ATT-72d71af1be384701876433e7d90c4553",
    worker_id: "worker-a",
    role: "plan",
    status: "COMPLETED",
    role_result: {
      schema_version: "mastermind.execution_plan/v1",
      plan_attempt_id: "ATT-72d71af1be384701876433e7d90c4553",
      root_job_id: "JOB-001",
      steps: [
        {
          step_id: "step-1",
          ordinal: 0,
          objective: "Perform one bounded read-only follow-up.",
          requested_authorities: ["READ"],
          allowed_write_paths: [],
          validation_ids: [],
          attempt_limit: 1,
          cost_class: "small",
          business_impact: "routine",
          review_required: false,
        },
      ],
    },
    summary: "Recovered one exact planner session.",
    current_state: "complete",
    next_actions: [],
    errors: [],
    validations: [],
  },
};

const CONSUME_REQUEST: FreshConversationTurnRequest = {
  work_ref: "WS:ONE",
  reference: REFERENCE,
  initial_digest: "38b30c3d06cf50fbf009034fc820284cd7d495b02cdcc8c740f83e26b40377bb",
};

const TURN_REQUEST: FreshConversationTurnRequest = {
  work_ref: "WS:ONE",
  reference: REFERENCE,
  initial_digest: "38b30c3d06cf50fbf009034fc820284cd7d495b02cdcc8c740f83e26b40377bb",
  message: "Explain the next bounded action. 新消息",
  turn_key: "original-followup-001",
};

const STATUS_REQUEST: FreshConversationTurnRequest = {
  work_ref: "WS:ONE",
  reference: REFERENCE,
  turn_key: "original-followup-001",
};

// ---- Genuine captured outer frames (envelope factored once, values verbatim) ----

const CONSUME_FRAME = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "consume",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_turn_data.v1",
    work_ref: "WS:ONE",
    operation_key: null,
    reference: REFERENCE,
    turn_key: null,
    state: "CONSUMED",
    effect: "COMMITTED",
    initial_consumption: CONSUMPTION,
    locator: LOCATOR,
    result: null,
    parent_consumed: false,
    can_send: true,
  },
  error: null,
};

const TURN_FRAME = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "turn",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_turn_data.v1",
    work_ref: "WS:ONE",
    operation_key: null,
    reference: REFERENCE,
    turn_key: "original-followup-001",
    state: "RECORDED",
    effect: "COMMITTED",
    initial_consumption: CONSUMPTION,
    locator: LOCATOR,
    result: RECORDED_RESULT,
    parent_consumed: false,
    can_send: false,
  },
  error: null,
};

const STATUS_FRAME = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "turn_status",
  ok: true,
  data: TURN_FRAME.data,
  error: null,
};

const READ_FRAME = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "turn_read",
  ok: true,
  data: TURN_FRAME.data,
  error: null,
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function asRec(value: unknown): Record<string, unknown> {
  return value as Record<string, unknown>;
}

function sealed(envelope: unknown): { digest: string; envelope: unknown } {
  return { digest: sha256Hex(canonicalJson(envelope)), envelope };
}

describe("genuine captured frames decode", () => {
  it("consume frame decodes CONSUMED with the genuine consumption and locator", () => {
    const result = decodeFreshConversationTurnResult(clone(CONSUME_FRAME), "consume", CONSUME_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(result.ok).toBe(true);
    expect(result.data.state).toBe("CONSUMED");
    expect(result.data.effect).toBe("COMMITTED");
    expect(result.data.can_send).toBe(true);
    expect(result.data.parent_consumed).toBe(false);
    expect(result.data.operation_key).toBe(null);
    expect(result.data.turn_key).toBe(null);
    expect(result.data.result).toBe(null);
    expect(result.data.initial_consumption).toEqual(CONSUMPTION);
    expect(result.data.locator).toEqual(LOCATOR);
    expect(result.data.reference).toEqual(REFERENCE);
  });

  it("turn frame decodes RECORDED with the strictly sealed genuine result", () => {
    const result = decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", TURN_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(result.data.state).toBe("RECORDED");
    expect(result.data.can_send).toBe(false);
    expect(result.data.turn_key).toBe("original-followup-001");
    expect(result.data.result?.digest).toBe(RECORDED_RESULT.digest);
    expect(result.data.result?.envelope).toEqual(RECORDED_ENVELOPE);
  });

  it("turn_status frame decodes against the reference-mode status request", () => {
    const result = decodeFreshConversationTurnResult(clone(STATUS_FRAME), "turn_status", STATUS_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(result.data.state).toBe("RECORDED");
    expect(result.data.can_send).toBe(false);
  });

  it("turn_read frame decodes against the reference-mode read request", () => {
    const result = decodeFreshConversationTurnResult(clone(READ_FRAME), "turn_read", STATUS_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(result.data.state).toBe("RECORDED");
    expect(result.data.reference).toEqual(REFERENCE);
  });

  it("genuine initial_result passes the strict locator-bound sealed reader", () => {
    const payload = decodeFreshConversationInitialResult(INITIAL_RESULT, {
      job_id: LOCATOR.job_id,
      attempt_id: LOCATOR.attempt_id,
      root_job_id: LOCATOR.root_job_id,
    });
    expect(payload === null).toBe(false);
    if (payload === null) throw new Error("expected payload");
    expect(payload.digest).toBe(INITIAL_RESULT.digest);
    expect(payload.digest).toBe(CONSUMPTION.initial_digest);
  });

  it("decoded values are detached from the source frame (envelope deep-copy)", () => {
    const frame = clone(TURN_FRAME);
    const result = decodeFreshConversationTurnResult(frame, "turn", TURN_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    const decodedEnvelope = result.data.result?.envelope;
    const sourceEnvelope = asRec(asRec(frame.data).result).envelope;
    expect(decodedEnvelope === sourceEnvelope).toBe(false);
    const decodedSteps = asRec(asRec(decodedEnvelope).role_result).steps as unknown[];
    const sourceSteps = asRec(asRec(sourceEnvelope).role_result).steps as unknown[];
    expect(decodedSteps === sourceSteps).toBe(false);
    // Mutating the decode output must not touch the source frame.
    asRec(decodedEnvelope).current_state = "mutated";
    expect(asRec(sourceEnvelope).current_state).toBe("complete");
    expect(decodedSteps === sourceSteps).toBe(false);
  });

  it("mutating the input frame after decoding does not change decoded data", () => {
    const frame = clone(TURN_FRAME);
    const result = decodeFreshConversationTurnResult(frame, "turn", TURN_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    const summaryBefore = asRec(result.data.result?.envelope).summary;
    asRec(asRec(frame.data).locator).job_id = "JOB-999";
    const summaryAfter = asRec(result.data.result?.envelope).summary;
    expect(summaryAfter).toBe(summaryBefore);
    expect(summaryAfter).toBe("Inert native follow-up answer.");
    expect(result.data.locator.job_id).toBe("JOB-002");
  });
});

describe("selector modes and request law", () => {
  const keyStatusData = () => {
    const data = clone(TURN_FRAME.data) as Record<string, unknown>;
    data.reference = null;
    data.operation_key = "fresh-original-one";
    const frame = clone(TURN_FRAME) as Record<string, unknown>;
    frame.data = data;
    frame.operation = "turn_status";
    return frame;
  };

  it("operation_key-mode turn_status request decodes a matching frame", () => {
    const request = validateFreshConversationTurnRequest(
      { work_ref: "WS:ONE", operation_key: "fresh-original-one", turn_key: "original-followup-001" },
      "turn_status",
    );
    expect(request === null).toBe(false);
    const result = decodeFreshConversationTurnResult(keyStatusData(), "turn_status", request);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(result.data.reference).toBe(null);
    expect(result.data.operation_key).toBe("fresh-original-one");
    expect(result.data.state).toBe("RECORDED");
  });

  it("operation_key-mode consume request decodes a matching frame", () => {
    const data = clone(CONSUME_FRAME.data) as Record<string, unknown>;
    data.reference = null;
    data.operation_key = "fresh-original-one";
    const frame = { ...clone(CONSUME_FRAME), data };
    const request = validateFreshConversationTurnRequest(
      {
        work_ref: "WS:ONE",
        operation_key: "fresh-original-one",
        initial_digest: CONSUMPTION.initial_digest,
      },
      "consume",
    );
    expect(request === null).toBe(false);
    const result = decodeFreshConversationTurnResult(frame, "consume", request);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(result.data.can_send).toBe(true);
    expect(result.data.initial_consumption).toEqual(CONSUMPTION);
  });

  it("a request carrying both selector forms is rejected", () => {
    expect(
      validateFreshConversationTurnRequest(
        {
          work_ref: "WS:ONE",
          reference: REFERENCE,
          operation_key: "fresh-original-one",
          turn_key: "original-followup-001",
        },
        "turn_status",
      ),
    ).toBeNull();
  });

  it("foreign work reference (reference.work_ref != request.work_ref) is rejected", () => {
    const foreign = { ...REFERENCE, work_ref: "WS:TWO" };
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: foreign, turn_key: "original-followup-001" },
        "turn_status",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: foreign, initial_digest: CONSUMPTION.initial_digest },
        "consume",
      ),
    ).toBeNull();
  });

  it("non-turn operations are refused on both entry points", () => {
    const previewOp = "preview" as unknown as FreshConversationTurnOperation;
    const createOp = "create" as unknown as FreshConversationTurnOperation;
    const readOp = "read" as unknown as FreshConversationTurnOperation;
    expect(
      decodeFreshConversationTurnResult(clone(CONSUME_FRAME), previewOp, CONSUME_REQUEST),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: REFERENCE, initial_digest: CONSUMPTION.initial_digest },
        createOp,
      ),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(clone(CONSUME_FRAME), readOp, CONSUME_REQUEST),
    ).toBeNull();
  });

  it("whole-string selectors reject final newlines and overlong tails", () => {
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE\n", reference: REFERENCE, turn_key: "original-followup-001" },
        "turn_status",
      ),
    ).toBeNull();
    // WS: + 1 + 68 = 72 chars is exactly the law; one more is rejected.
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: `WS:${"b".repeat(68)}`, operation_key: "k", turn_key: "k" },
        "turn_status",
      ),
    ).not.toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: `WS:${"b".repeat(69)}`, operation_key: "k", turn_key: "k" },
        "turn_status",
      ),
    ).not.toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: `WS:${"b".repeat(70)}`, operation_key: "k", turn_key: "k" },
        "turn_status",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: `WS:${"b".repeat(68)}`, operation_key: "k", turn_key: "k" },
        "turn_status",
      ),
    ).not.toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", operation_key: "ok-key\n", turn_key: "k" },
        "turn_status",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", operation_key: "a".repeat(96), turn_key: "k" },
        "turn_status",
      ),
    ).not.toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", operation_key: "a".repeat(97), turn_key: "k" },
        "turn_status",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: REFERENCE, turn_key: "original-followup-001\n" },
        "turn_status",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: REFERENCE, initial_digest: `${CONSUMPTION.initial_digest}\n` },
        "consume",
      ),
    ).toBeNull();
  });

  it("digest hex law: lowercase 64 only", () => {
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: REFERENCE, initial_digest: CONSUMPTION.initial_digest.toUpperCase() },
        "consume",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: REFERENCE, initial_digest: CONSUMPTION.initial_digest.slice(1) },
        "consume",
      ),
    ).toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { work_ref: "WS:ONE", reference: REFERENCE, initial_digest: `0${CONSUMPTION.initial_digest}` },
        "consume",
      ),
    ).toBeNull();
  });
});

describe("turn message law", () => {
  it("preserves whitespace, newlines and non-BMP literally", () => {
    const message = "  新对话\nRead source.  ";
    const request = validateFreshConversationTurnRequest(
      {
        work_ref: "WS:ONE",
        reference: REFERENCE,
        initial_digest: CONSUMPTION.initial_digest,
        message,
        turn_key: "original-followup-001",
      },
      "turn",
    );
    expect(request === null).toBe(false);
    if (request === null || !("message" in request)) throw new Error("expected turn request");
    expect(request.message).toBe(message);
  });

  it("rejects all-whitespace messages under Python strip semantics", () => {
    for (const message of ["   ", "\n\t ", "　", "\u001c\u001f", " "]) {
      expect(
        validateFreshConversationTurnRequest(
          {
            work_ref: "WS:ONE",
            reference: REFERENCE,
            initial_digest: CONSUMPTION.initial_digest,
            message,
            turn_key: "original-followup-001",
          },
          "turn",
        ),
      ).toBeNull();
    }
  });

  it("enforces the 700 code point boundary including astral characters", () => {
    const base = {
      work_ref: "WS:ONE",
      reference: REFERENCE,
      initial_digest: CONSUMPTION.initial_digest,
      turn_key: "original-followup-001",
    };
    const exactly700 = `x${"𝕏".repeat(699)}`; // 700 code points, 2800 UTF-8 bytes
    expect(
      validateFreshConversationTurnRequest({ ...base, message: exactly700 }, "turn"),
    ).not.toBeNull();
    expect(
      validateFreshConversationTurnRequest(
        { ...base, message: `x${"あ".repeat(700)}` },
        "turn",
      ),
    ).toBeNull(); // 701 code points
  });

  it("rejects forbidden controls, DEL, C1 and lone surrogates", () => {
    const base = {
      work_ref: "WS:ONE",
      reference: REFERENCE,
      initial_digest: CONSUMPTION.initial_digest,
      turn_key: "original-followup-001",
    };
    expect(validateFreshConversationTurnRequest({ ...base, message: "a\u0001b" }, "turn")).toBeNull();
    expect(validateFreshConversationTurnRequest({ ...base, message: "a\u007fb" }, "turn")).toBeNull();
    expect(validateFreshConversationTurnRequest({ ...base, message: "a\u009fb" }, "turn")).toBeNull();
    expect(validateFreshConversationTurnRequest({ ...base, message: "a\ud800b" }, "turn")).toBeNull();
    expect(validateFreshConversationTurnRequest({ ...base, message: "a\tb\nc\rd" }, "turn")).not.toBeNull();
    expect(
      validateFreshConversationTurnRequest({ ...base, message: "text" as string }, "turn"),
    ).not.toBeNull();
  });
});

describe("validateFreshConversationReference", () => {
  it("accepts and detaches the genuine reference", () => {
    const source = clone(REFERENCE);
    const reference = validateFreshConversationReference(source);
    expect(reference === null).toBe(false);
    expect(reference).toEqual(REFERENCE);
    expect(reference === source).toBe(false);
    expect(reference?.schema).toBe("mastermind.fresh_conversation_reference.v1");
  });

  it("rejects schema, key and scalar mutations", () => {
    expect(validateFreshConversationReference({ ...REFERENCE, schema: "mastermind.fresh_conversation_reference.v2" })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_event_id: 0 })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_event_id: -1 })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_event_id: true })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_event_id: 1.5 })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_event_sha256: "88EABD8CCA4F01769CA165F5427341102C468E8F446217C9F6DD14795A64BC97" })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, principal_scope_sha256: "76db2490" })).toBeNull();
    const extra:Record<string,unknown> = { ...REFERENCE };
    extra.extra = 1;
    expect(validateFreshConversationReference(extra)).toBeNull();
    const missing:Record<string,unknown> = { ...REFERENCE };
    delete missing.principal_scope_sha256;
    expect(validateFreshConversationReference(missing)).toBeNull();
  });

  it("rejects whole-string violations on work_ref and root_job_id", () => {
    expect(validateFreshConversationReference({ ...REFERENCE, work_ref: "WS:ONE\n" })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, work_ref: "WS:ONE " })).toBeNull();
    expect(
      validateFreshConversationReference({ ...REFERENCE, root_job_id: `${"j".repeat(128)}` }),
    ).not.toBeNull();
    expect(
      validateFreshConversationReference({ ...REFERENCE, root_job_id: `${"j".repeat(129)}` }),
    ).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_job_id: "-JOB-001" })).toBeNull();
    expect(validateFreshConversationReference({ ...REFERENCE, root_job_id: "JOB-001\n" })).toBeNull();
  });
});

describe("turn DATA mutations and state law", () => {
  function withData(mutate: (data: Record<string, unknown>) => void): Record<string, unknown> {
    const frame = clone(TURN_FRAME) as unknown as Record<string, unknown>;
    const data = clone(TURN_FRAME.data) as Record<string, unknown>;
    mutate(data);
    frame.data = data;
    return frame;
  }

  it("rejects a foreign work_ref, operation_key or turn_key echo", () => {
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.work_ref = "WS:TWO"; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.operation_key = "other-key"; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.turn_key = "another-turn"; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.turn_key = null; }), "turn", TURN_REQUEST),
    ).toBeNull();
  });

  it("rejects reference echoes that disagree with the request selector", () => {
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.reference = null; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(
        withData((d) => { d.reference = { ...REFERENCE, root_event_id: 99 }; }),
        "turn",
        TURN_REQUEST,
      ),
    ).toBeNull();
  });

  it("rejects a reference whose root job disagrees with the returned locator", () => {
    const foreignRoot = { ...REFERENCE, root_job_id: "JOB-009" };
    expect(
      decodeFreshConversationTurnResult(
        withData((d) => { d.reference = foreignRoot; }),
        "turn",
        TURN_REQUEST,
      ),
    ).toBeNull();
    const refTurnRequest: FreshConversationTurnRequest = { ...TURN_REQUEST, reference: foreignRoot };
    expect(
      decodeFreshConversationTurnResult(
        withData((d) => { d.reference = foreignRoot; }),
        "turn",
        refTurnRequest,
      ),
    ).toBeNull();
  });

  it("rejects parent_consumed true and non-boolean or misplaced can_send", () => {
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.parent_consumed = true; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.parent_consumed = null; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.can_send = "true"; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.can_send = 1; }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.can_send = true; }), "turn", TURN_REQUEST),
    ).toBeNull();
  });

  it("rejects missing or malformed initial consumption", () => {
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.initial_consumption = null; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const bad = clone(CONSUME_FRAME) as unknown as Record<string, unknown>;
    const data = clone(CONSUME_FRAME.data) as Record<string, unknown>;
    const consumption = clone(CONSUMPTION) as Record<string, unknown>;
    consumption.state = "PENDING";
    data.initial_consumption = consumption;
    bad.data = data;
    expect(decodeFreshConversationTurnResult(bad, "consume", CONSUME_REQUEST)).toBeNull();
    const zero = clone(CONSUMPTION) as Record<string, unknown>;
    zero.event_id = 0;
    const zeroFrame = clone(CONSUME_FRAME) as unknown as Record<string, unknown>;
    zeroFrame.data = { ...clone(CONSUME_FRAME.data), initial_consumption: zero };
    expect(decodeFreshConversationTurnResult(zeroFrame, "consume", CONSUME_REQUEST)).toBeNull();
    const float = clone(CONSUMPTION) as Record<string, unknown>;
    float.event_id = 21.5;
    const floatFrame = clone(CONSUME_FRAME) as unknown as Record<string, unknown>;
    floatFrame.data = { ...clone(CONSUME_FRAME.data), initial_consumption: float };
    expect(decodeFreshConversationTurnResult(floatFrame, "consume", CONSUME_REQUEST)).toBeNull();
    const bool = clone(CONSUMPTION) as Record<string, unknown>;
    bool.event_id = true;
    const boolFrame = clone(CONSUME_FRAME) as unknown as Record<string, unknown>;
    boolFrame.data = { ...clone(CONSUME_FRAME.data), initial_consumption: bool };
    expect(decodeFreshConversationTurnResult(boolFrame, "consume", CONSUME_REQUEST)).toBeNull();
  });

  it("consumption initial_digest must agree with a supplied request digest", () => {
    const drifted = {
      ...CONSUMPTION,
      initial_digest: "1111111111111111111111111111111111111111111111111111111111111111",
    };
    const frame = clone(CONSUME_FRAME) as unknown as Record<string, unknown>;
    frame.data = { ...clone(CONSUME_FRAME.data), initial_consumption: drifted };
    expect(decodeFreshConversationTurnResult(frame, "consume", CONSUME_REQUEST)).toBeNull();
  });

  it("locator law: foreign work_ref, extra keys, and ABSENT null handling", () => {
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.locator = { ...LOCATOR, work_ref: "WS:TWO" }; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const extraLocator = { ...LOCATOR } as Record<string, unknown>;
    extraLocator.session_id = "S1";
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.locator = extraLocator; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const absentOk = withData((d) => {
      d.state = "ABSENT";
      d.effect = "NONE";
      d.locator = { work_ref: "WS:ONE", root_job_id: "JOB-001", job_id: null, attempt_id: null };
      d.initial_consumption = null;
      d.result = null;
    });
    const absentResult = decodeFreshConversationTurnResult(absentOk, "turn", TURN_REQUEST);
    expect(absentResult === null).toBe(false);
    if (absentResult !== null && absentResult.ok) expect(absentResult.data.locator.job_id).toBe(null);
    const absentEmpty = withData((d) => {
      d.state = "ABSENT";
      d.effect = "NONE";
      d.locator = { work_ref: "WS:ONE", root_job_id: "JOB-001", job_id: "", attempt_id: null };
      d.initial_consumption = null;
      d.result = null;
    });
    expect(decodeFreshConversationTurnResult(absentEmpty, "turn", TURN_REQUEST)).toBeNull();
    const absentNullOnLive = withData((d) => {
      d.locator = { work_ref: "WS:ONE", root_job_id: "JOB-001", job_id: null, attempt_id: null };
    });
    expect(decodeFreshConversationTurnResult(absentNullOnLive, "turn", TURN_REQUEST)).toBeNull();
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.locator = null; }), "turn", TURN_REQUEST),
    ).toBeNull();
  });

  it("result/state coupling: RECORDED needs consumption+result; others need none", () => {
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = null; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const consumedWithResult = withData((d) => {
      d.state = "CONSUMED";
      d.can_send = false;
    });
    expect(decodeFreshConversationTurnResult(consumedWithResult, "turn", TURN_REQUEST)).toBeNull();
    const absentWithResult = withData((d) => {
      d.state = "ABSENT";
      d.effect = "UNKNOWN";
      d.initial_consumption = null;
    });
    expect(decodeFreshConversationTurnResult(absentWithResult, "turn", TURN_REQUEST)).toBeNull();
  });

  it("RECORDED result is strictly bound to the actual locator envelope", () => {
    const wrongJob = sealed({ ...RECORDED_ENVELOPE, job_id: "JOB-009" });
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = wrongJob; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const wrongRun = sealed({ ...RECORDED_ENVELOPE, run_id: "ATT-0000" });
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = wrongRun; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const wrongPlanRoot = sealed({
      ...RECORDED_ENVELOPE,
      role_result: { ...RECORDED_ENVELOPE.role_result, root_job_id: "JOB-009" },
    });
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = wrongPlanRoot; }), "turn", TURN_REQUEST),
    ).toBeNull();
    const deepNested: Record<string, unknown> = { ...clone(RECORDED_ENVELOPE) as Record<string, unknown> };
    let cursor: Record<string, unknown> = deepNested;
    for (let i = 0; i < 26; i++) {
      const next: Record<string, unknown> = {};
      cursor.nest = next;
      cursor = next;
    }
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = sealed(deepNested); }), "turn", TURN_REQUEST),
    ).toBeNull();
    const oversized = { ...clone(RECORDED_ENVELOPE) as Record<string, unknown>, filler: "x".repeat(20000) };
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = sealed(oversized); }), "turn", TURN_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(
        withData((d) => { d.result = { digest: RECORDED_RESULT.digest, envelope: RECORDED_ENVELOPE }; }),
        "turn",
        TURN_REQUEST,
      ),
    ).not.toBeNull();
    const digestless = { digest: "0".repeat(64), envelope: RECORDED_ENVELOPE };
    expect(
      decodeFreshConversationTurnResult(withData((d) => { d.result = digestless; }), "turn", TURN_REQUEST),
    ).toBeNull();
  });
});

describe("outer envelope law", () => {
  it("preserves a well-formed ok:false error branch as data", () => {
    const frame = {
      schema: "mastermind.executive.fresh_conversation_result.v1",
      operation: "turn_status",
      ok: false,
      data: null,
      error: { code: "turn_not_recorded", message: "No recorded turn under this key." },
    };
    const result = decodeFreshConversationTurnResult(frame, "turn_status", STATUS_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || result.ok) throw new Error("expected error branch");
    expect(result.ok).toBe(false);
    expect(result.data).toBe(null);
    expect(result.error.code).toBe("turn_not_recorded");
    expect(result.error.message).toBe("No recorded turn under this key.");
  });

  it("rejects malformed error payloads", () => {
    const base = {
      schema: "mastermind.executive.fresh_conversation_result.v1",
      operation: "turn_status",
      ok: false,
      data: null,
    };
    expect(
      decodeFreshConversationTurnResult({ ...base, error: { code: "", message: "m" } }, "turn_status", STATUS_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(
        { ...base, error: { code: "c", message: "m", extra: 1 } },
        "turn_status",
        STATUS_REQUEST,
      ),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult({ ...base, error: { code: "c\u0007", message: "m" } }, "turn_status", STATUS_REQUEST),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult({ ...base, error: null }, "turn_status", STATUS_REQUEST),
    ).toBeNull();
  });

  it("enforces the exact five-field envelope, schema and operation", () => {
    const missing = clone(TURN_FRAME) as unknown as Record<string, unknown>;
    const missingFrame = { ...(missing as Record<string, unknown>) };
    delete missingFrame.error;
    expect(decodeFreshConversationTurnResult(missingFrame, "turn", TURN_REQUEST)).toBeNull();
    const extra = { ...clone(TURN_FRAME), extra: 1 } as Record<string, unknown>;
    expect(decodeFreshConversationTurnResult(extra, "turn", TURN_REQUEST)).toBeNull();
    expect(
      decodeFreshConversationTurnResult(
        { ...clone(TURN_FRAME), schema: "mastermind.executive.fresh_conversation.v1" },
        "turn",
        TURN_REQUEST,
      ),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(
        { ...clone(CONSUME_FRAME), operation: "turn" },
        "turn",
        TURN_REQUEST,
      ),
    ).toBeNull();
    expect(decodeFreshConversationTurnResult(clone(CONSUME_FRAME), "turn", TURN_REQUEST)).toBeNull();
  });

  it("rejects ok-field nullability violations", () => {
    const badOk = { ...clone(TURN_FRAME), ok: null } as unknown;
    expect(decodeFreshConversationTurnResult(badOk, "turn", TURN_REQUEST)).toBeNull();
    const stringOk = { ...clone(TURN_FRAME), ok: "true" } as unknown;
    expect(decodeFreshConversationTurnResult(stringOk, "turn", TURN_REQUEST)).toBeNull();
    const okWithError = { ...clone(TURN_FRAME), error: { code: "c", message: "m" } };
    expect(decodeFreshConversationTurnResult(okWithError, "turn", TURN_REQUEST)).toBeNull();
    const failWithData = {
      schema: "mastermind.executive.fresh_conversation_result.v1",
      operation: "turn",
      ok: false,
      data: clone(TURN_FRAME.data),
      error: { code: "c", message: "m" },
    };
    expect(decodeFreshConversationTurnResult(failWithData, "turn", TURN_REQUEST)).toBeNull();
    const okWithDataNull = { ...clone(TURN_FRAME), data: null } as unknown;
    expect(decodeFreshConversationTurnResult(okWithDataNull, "turn", TURN_REQUEST)).toBeNull();
  });

  it("re-validates the expected request: no surrogate, no foreign selector", () => {
    expect(decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", null)).toBeNull();
    expect(decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", undefined)).toBeNull();
    expect(
      decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", { ...TURN_REQUEST, extra: 1 }),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", {
        work_ref: "WS:TWO",
        reference: REFERENCE,
        initial_digest: CONSUMPTION.initial_digest,
        message: "Explain the next bounded action. 新消息",
        turn_key: "original-followup-001",
      }),
    ).toBeNull();
    expect(
      decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", clone(STATUS_REQUEST)),
    ).toBeNull(); // turn_status request shape under the turn operation
  });
});

describe("closure and hostile input", () => {
  it("rejects non-object and non-plain-object frames", () => {
    expect(decodeFreshConversationTurnResult(null, "turn", TURN_REQUEST)).toBeNull();
    expect(decodeFreshConversationTurnResult(undefined, "turn", TURN_REQUEST)).toBeNull();
    expect(decodeFreshConversationTurnResult(42, "turn", TURN_REQUEST)).toBeNull();
    expect(decodeFreshConversationTurnResult("frame", "turn", TURN_REQUEST)).toBeNull();
    expect(decodeFreshConversationTurnResult([TURN_FRAME], "turn", TURN_REQUEST)).toBeNull();
    expect(decodeFreshConversationTurnResult(new Date(), "turn", TURN_REQUEST)).toBeNull();
    expect(validateFreshConversationTurnRequest(null, "consume")).toBeNull();
    expect(validateFreshConversationTurnRequest("request", "turn_status")).toBeNull();
    expect(validateFreshConversationReference(null)).toBeNull();
    expect(validateFreshConversationReference(undefined)).toBeNull();
    expect(validateFreshConversationReference([REFERENCE])).toBeNull();
  });

  it("rejects accessor stand-ins and inherited fields", () => {
    const getterFrame: Record<string, unknown> = {};
    Object.defineProperty(getterFrame, "schema", {
      enumerable: true,
      get() {
        return "mastermind.executive.fresh_conversation_result.v1";
      },
    });
    Object.assign(getterFrame, {
      operation: "turn",
      ok: true,
      data: clone(TURN_FRAME.data),
      error: null,
    });
    expect(decodeFreshConversationTurnResult(getterFrame, "turn", TURN_REQUEST)).toBeNull();
    const getterRequest: Record<string, unknown> = {};
    Object.defineProperty(getterRequest, "work_ref", {
      enumerable: true,
      get() {
        return "WS:ONE";
      },
    });
    Object.assign(getterRequest, {
      operation_key: "fresh-original-one",
      turn_key: "original-followup-001",
    });
    expect(validateFreshConversationTurnRequest(getterRequest, "turn_status")).toBeNull();
    const inherited: Record<string, unknown> = Object.create({
      operation_key: "inherited-key",
    }) as Record<string, unknown>;
    inherited.work_ref = "WS:ONE";
    inherited.turn_key = "original-followup-001";
    expect(validateFreshConversationTurnRequest(inherited, "turn_status")).toBeNull();
  });

  it("rejects a non-plain JSON stand-in inside the turn data", () => {
    const data = clone(CONSUME_FRAME.data) as unknown as Record<string, unknown>;
    const consumption = new (class Consumption {
      state = "CONSUMED";
      event_id = 21;
    })();
    data.initial_consumption = consumption;
    const frame = { ...clone(CONSUME_FRAME), data };
    expect(decodeFreshConversationTurnResult(frame, "consume", CONSUME_REQUEST)).toBeNull();
  });

  it("accepts proto-null frames but never mutates prototypes", () => {
    const frame = clone(CONSUME_FRAME) as unknown as Record<string, unknown>;
    const nullProtoFrame: Record<string, unknown> = Object.assign(Object.create(null), frame);
    const result = decodeFreshConversationTurnResult(nullProtoFrame, "consume", CONSUME_REQUEST);
    expect(result === null).toBe(false);
    expect(Object.getPrototypeOf({}).prototype).toBeUndefined();
  });

  it("does not leak prototype mutation through an own __proto__ data key", () => {
    const hostile = JSON.parse(
      JSON.stringify(clone(CONSUME_FRAME)),
    ) as unknown as Record<string, unknown>;
    const data = JSON.parse(JSON.stringify(clone(CONSUME_FRAME.data))) as Record<string, unknown>;
    data.extra_proto = { polluted: true };
    hostile.data = data;
    // An extra key breaks the closed key set; the decoder returns null and
    // Object.prototype is untouched.
    expect(decodeFreshConversationTurnResult(hostile, "consume", CONSUME_REQUEST)).toBeNull();
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it("decoded turn data exposes exactly the closed twelve-field shape", () => {
    const result = decodeFreshConversationTurnResult(clone(TURN_FRAME), "turn", TURN_REQUEST);
    expect(result === null).toBe(false);
    if (result === null || !result.ok) throw new Error("expected ok branch");
    expect(Object.keys(result.data).sort()).toEqual([
      "can_send",
      "effect",
      "initial_consumption",
      "locator",
      "operation_key",
      "parent_consumed",
      "reference",
      "result",
      "schema",
      "state",
      "turn_key",
      "work_ref",
    ]);
    expect(Object.keys(result.data.reference ?? {}).sort()).toEqual([
      "principal_scope_sha256",
      "root_event_id",
      "root_event_sha256",
      "root_job_id",
      "schema",
      "work_ref",
    ]);
  });
});


// New f357 branches below use explicit SYNTHETIC schema units, not a replay,
// rewrite, or joined acceptance claim for the future genuine successor run.
const SYNTHETIC_RECOVERY_REQUEST={work_ref:WORK_REF,reference:REFERENCE,initial_digest:CONSUMPTION.initial_digest};
const SYNTHETIC_RECOVERY_FRAME={...CONSUME_FRAME,operation:"consume_status",data:{...CONSUME_FRAME.data,can_send:false}};
const SYNTHETIC_PREVIEW_FRAME={schema:"mastermind.executive.fresh_conversation_result.v1",operation:"turn_preview",ok:true,error:null,
 data:{schema:"mastermind.executive.fresh_conversation_turn_preview.v1",work_ref:WORK_REF,operation_key:null,reference:REFERENCE,
 turn_key:"original-followup-001",state:"TURN_READY",effect:"NONE",initial_consumption:CONSUMPTION,locator:LOCATOR,
 preview_digest:"a".repeat(64),parent_consumed:false,can_send:true}};

describe("f357 interrupted Keep and attended preflight pure schema units",()=>{
 it("validates readonly consume_status without creating a turn selector",()=>{
  expect(validateFreshConversationTurnRequest(SYNTHETIC_RECOVERY_REQUEST,"consume_status")).toEqual(SYNTHETIC_RECOVERY_REQUEST);
  expect(validateFreshConversationTurnRequest({...SYNTHETIC_RECOVERY_REQUEST,turn_key:"invented"},"consume_status")).toBeNull();
  const decoded=decodeFreshConversationTurnResult(SYNTHETIC_RECOVERY_FRAME,"consume_status",SYNTHETIC_RECOVERY_REQUEST);
  expect(decoded?.ok).toBe(true);if(decoded?.ok){expect(decoded.data.can_send).toBe(false);expect(decoded.data.turn_key).toBeNull();}
 });
 it("keeps key-mode recovery exact and ABSENT separate from a receipt",()=>{
  const request={work_ref:WORK_REF,operation_key:"unit-original-key",initial_digest:CONSUMPTION.initial_digest};
  const data={...SYNTHETIC_RECOVERY_FRAME.data,reference:null,operation_key:request.operation_key};
  expect(decodeFreshConversationTurnResult({...SYNTHETIC_RECOVERY_FRAME,data},"consume_status",request)?.ok).toBe(true);
  const absent={...data,state:"ABSENT",effect:"NONE",initial_consumption:null};
  expect(decodeFreshConversationTurnResult({...SYNTHETIC_RECOVERY_FRAME,data:absent},"consume_status",request)?.ok).toBe(true);
  for(const delta of [{can_send:true},{effect:"UNKNOWN"},{state:"RECORDED"},{initial_consumption:null}])
   expect(decodeFreshConversationTurnResult({...SYNTHETIC_RECOVERY_FRAME,data:{...data,...delta}},"consume_status",request)).toBeNull();
 });
 it("preserves legacy turn syntax and only accepts a valid optional Send preview digest",()=>{
  expect(validateFreshConversationTurnRequest(TURN_REQUEST,"turn")).toEqual(TURN_REQUEST);
  const checked={...TURN_REQUEST,preview_digest:"b".repeat(64)};
  expect(validateFreshConversationTurnRequest(checked,"turn")).toEqual(checked);
  expect(validateFreshConversationTurnRequest(TURN_REQUEST,"turn_preview")).toEqual(TURN_REQUEST);
  expect(validateFreshConversationTurnRequest(checked,"turn_preview")).toBeNull();
  for(const preview_digest of [undefined,null,"", "b".repeat(63),"B".repeat(64)])
   expect(validateFreshConversationTurnRequest({...TURN_REQUEST,preview_digest},"turn")).toBeNull();
 });
 it("separates exact preflight DATA from a recorded effect receipt",()=>{
  const decoded=decodeFreshConversationTurnPreviewResult(SYNTHETIC_PREVIEW_FRAME,TURN_REQUEST);
  expect(decoded?.ok).toBe(true);if(decoded?.ok){expect(decoded.data).toEqual(SYNTHETIC_PREVIEW_FRAME.data);expect(decoded.data).not.toBe(SYNTHETIC_PREVIEW_FRAME.data);}
  expect(decodeFreshConversationTurnResult(SYNTHETIC_PREVIEW_FRAME,"turn_preview",TURN_REQUEST)).toBeNull();
  expect(decodeFreshConversationTurnPreviewResult(CONSUME_FRAME,TURN_REQUEST)).toBeNull();
 });
 it("rejects preview literal/schema/digest/root/receipt drift rather than minting readiness",()=>{
  for(const delta of [{schema:"foreign"},{state:"CONSUMED"},{effect:"COMMITTED"},{parent_consumed:true},{can_send:false},
   {preview_digest:"no"},{extra:true},{initial_consumption:null},{locator:{...LOCATOR,root_job_id:"foreign"}},
   {initial_consumption:{...CONSUMPTION,initial_digest:"f".repeat(64)}}])
   expect(decodeFreshConversationTurnPreviewResult({...SYNTHETIC_PREVIEW_FRAME,data:{...SYNTHETIC_PREVIEW_FRAME.data,...delta}},TURN_REQUEST)).toBeNull();
 });
 it("rejects extra response reference fields and accessors without executing them",()=>{
  const extra={...REFERENCE,extra:true};
  expect(decodeFreshConversationTurnResult({...TURN_FRAME,data:{...TURN_FRAME.data,reference:extra}},"turn",TURN_REQUEST)).toBeNull();
  expect(decodeFreshConversationTurnPreviewResult({...SYNTHETIC_PREVIEW_FRAME,data:{...SYNTHETIC_PREVIEW_FRAME.data,reference:extra}},TURN_REQUEST)).toBeNull();
  let called=false;const raw={...SYNTHETIC_PREVIEW_FRAME};Object.defineProperty(raw,"data",{enumerable:true,get(){called=true;return SYNTHETIC_PREVIEW_FRAME.data;}});
  expect(decodeFreshConversationTurnPreviewResult(raw,TURN_REQUEST)).toBeNull();expect(called).toBe(false);
 });
});
