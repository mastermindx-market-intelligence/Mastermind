/** Focused pure vitest coverage for the fresh conversation wire decoder.
 *
 * Every fixture here is an explicit synthetic unit fixture: these tests prove
 * decoder shape/branch behavior only. They are NOT genuine runtime proof, not
 * admission evidence, and never exercise transport, auth, dispatch or the
 * producer's live settlement path (parent owns that compatibility).
 */
import { describe, expect, it } from "vitest";
import { canonicalJson, sha256Hex } from "../../orchestration/operation-key";
import {
  decodeFreshConversationResult,
  validateFreshConversationRequest,
  type FreshConversationData,
  type FreshConversationRequest,
} from "./fresh-conversation";

const WORK = "WS:fresh-demo";
const KEY = "fresh-op-key.1";
const MESSAGE = "  Investigate the fresh conversation queue.  ";
const EXPECTED = { work_ref: WORK, operation_key: KEY };
const DATA_SCHEMA = "mastermind.executive.fresh_conversation_data.v1";

const hex = (seed: string) => sha256Hex(seed);
const previewRequest = () => ({ work_ref: WORK, operation_key: KEY, message: MESSAGE });
const createRequest = () => ({ ...previewRequest(), preview_digest: hex("preview") });
const keyRequest = () => ({ work_ref: WORK, operation_key: KEY });

const previewBody = () => ({
  digest: hex("p"),
  profile_digest: hex("pf"),
  source_digest: hex("src"),
  grounding: { topic: "queue", notes: [1, 2] },
  attempt_limit: 1,
  worker_account: "REGISTERED_NOT_SESSION_ATTESTED",
});
const locatorBody = (job: string | null = "job-1", attempt: string | null = "att-1") => ({
  work_ref: WORK,
  root_job_id: "root-1",
  job_id: job,
  attempt_id: attempt,
});
const sessionBody = (attempt = "att-1") => ({
  attempt_id: attempt,
  generation: "gen-1",
  binding_digest: hex("binding"),
});
const envelope = () => ({ marker: "sealed", nested: { n: 1, tags: ["a"] } });
const envelopeDigest = () => sha256Hex(canonicalJson(envelope()));
const resultBody = () => ({ digest: envelopeDigest(), envelope: envelope() });

type Body = Record<string, unknown>;
const dataBody = (over: Body = {}): Body => ({
  schema: DATA_SCHEMA,
  operation_key: KEY,
  work_ref: WORK,
  state: "ABSENT",
  effect: "NONE",
  parent_consumed: false,
  can_send: false,
  preview: null,
  locator: null,
  session: null,
  result: null,
  ...over,
});
const RESULT_SCHEMA="mastermind.executive.fresh_conversation_result.v1";
const okFrame = (data: unknown,operation="status") => ({schema:RESULT_SCHEMA,operation,ok:true,data,error:null});
/** Bind the operation in explicitly synthetic DATA tests. Actual envelope
 * identity/missing-field checks use the separate genuine owner suite. */
function unitFrame(value:unknown,operation:string):unknown {
 if(value && typeof value==="object" && (value as Body).schema===RESULT_SCHEMA)
  return Object.create(Object.getPrototypeOf(value),{...Object.getOwnPropertyDescriptors(value),operation:{value:operation,enumerable:true,configurable:true,writable:true}});
 return value;
}
const errorFrame = (over: Body = {}): Body => ({
  schema: RESULT_SCHEMA,
  operation: "read",
  ok: false,
  data: null,
  error: { code: "PRE_EFFECT_REFUSED", message: "admission refused" },
  ...over,
});

const nest = (levels: number): Record<string, unknown> => {
  let out: unknown = 1;
  for (let i = 0; i < levels; i += 1) out = { v: out };
  return out as Record<string, unknown>;
};
const throwingProp = (target: object, key: string) =>
  Object.defineProperty(target, key, {
    enumerable: true,
    get() {
      throw new Error("hostile getter");
    },
  });

function okData(value: unknown, operation: Parameters<typeof decodeFreshConversationResult>[1]): FreshConversationData {
  const decoded = decodeFreshConversationResult(unitFrame(value,operation), operation, EXPECTED);
  expect(decoded).not.toBeNull();
  const frame = decoded as { ok: boolean; data?: FreshConversationData };
  expect(frame.ok).toBe(true);
  return frame.data as FreshConversationData;
}
function refused(value: unknown, operation: Parameters<typeof decodeFreshConversationResult>[1]) {
  expect(decodeFreshConversationResult(unitFrame(value,operation), operation, EXPECTED)).toBeNull();
}

describe("validateFreshConversationRequest", () => {
  it("accepts the exact key set of every operation", () => {
    expect(validateFreshConversationRequest(previewRequest(), "preview")).toEqual(previewRequest());
    expect(validateFreshConversationRequest(createRequest(), "create")).toEqual(createRequest());
    const bare: FreshConversationRequest | null = validateFreshConversationRequest(keyRequest(), "status");
    expect(bare).toEqual(keyRequest());
    expect(validateFreshConversationRequest(keyRequest(), "read")).toEqual(keyRequest());
  });

  it("preserves the literal message and returns a detached copy", () => {
    const literal = "  keep  spaces 　 exact ﻿? no \n";
    const input = { work_ref: WORK, operation_key: KEY, message: literal };
    const decoded = validateFreshConversationRequest(input, "preview");
    expect(decoded).not.toBeNull();
    expect((decoded as { message: string }).message).toBe(literal);
    expect(decoded).not.toBe(input);
    input.message = "mutated";
    expect((decoded as { message: string }).message).toBe(literal);
  });

  it("rejects whitespace-only messages under Python strip semantics", () => {
    for (const blank of ["", " ", " \n\t ", "  ", "\u001C", "  ", "　"]) {
      expect(validateFreshConversationRequest({ ...previewRequest(), message: blank }, "preview")).toBeNull();
    }
    // U+FEFF is not Python strip whitespace, so a BOM-padded message survives.
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "﻿" }, "preview")).not.toBeNull();
  });

  it("rejects C0 controls except TAB/LF/CR, DEL and C1", () => {
    for (const bad of ["a\u0000b", "\u0007", "\u001Ba", "a\u007F", "\u0085", "\u009F"]) {
      expect(validateFreshConversationRequest({ ...previewRequest(), message: bad }, "preview")).toBeNull();
    }
    for (const good of ["a\tb", "a\nb", "a\rb"]) {
      expect(validateFreshConversationRequest({ ...previewRequest(), message: good }, "preview")).not.toBeNull();
    }
  });

  it("rejects unpaired surrogates and honors code point bounds", () => {
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "\uD800" }, "preview")).toBeNull();
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "ok\uDFFF" }, "preview")).toBeNull();
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "\u{1F600}" }, "preview")).not.toBeNull();
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "a".repeat(700) }, "preview")).not.toBeNull();
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "a".repeat(701) }, "preview")).toBeNull();
    // 700 astral code points = exactly 2800 UTF-8 bytes: the byte ceiling holds.
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "\u{1F600}".repeat(700) }, "preview")).not.toBeNull();
    expect(validateFreshConversationRequest({ ...previewRequest(), message: "\u{1F600}".repeat(701) }, "preview")).toBeNull();
  });

  it("enforces server-exact selector syntax without newline anchors", () => {
    for (const good of ["WS:a", `WS:${"a".repeat(68)}`, `WS:${"a".repeat(69)}`, "WS:Ws.9-_x"]) {
      expect(validateFreshConversationRequest({ ...keyRequest(), work_ref: good }, "status")).not.toBeNull();
    }
    for (const bad of ["ws:a", "WS:", "WS: a", `WS:${"a".repeat(70)}`, "WS:a\n", "WS:a/b", "WS:a b", "WS:é"]) {
      expect(validateFreshConversationRequest({ ...keyRequest(), work_ref: bad }, "status")).toBeNull();
    }
    for (const good of ["k", "k".padEnd(96, "-"), "k:1.a-b_c"]) {
      expect(validateFreshConversationRequest({ ...keyRequest(), operation_key: good }, "status")).not.toBeNull();
    }
    for (const bad of ["", ".lead", "-lead", "k/1", "k\n", "a".repeat(97)]) {
      expect(validateFreshConversationRequest({ ...keyRequest(), operation_key: bad }, "status")).toBeNull();
    }
  });

  it("rejects key set drift and malformed preview digests", () => {
    expect(validateFreshConversationRequest({ ...keyRequest(), message: "hi" }, "status")).toBeNull();
    expect(validateFreshConversationRequest({ work_ref: WORK, operation_key: KEY }, "preview")).toBeNull();
    const noDigest = previewRequest();
    expect(validateFreshConversationRequest(noDigest, "create")).toBeNull();
    expect(
      validateFreshConversationRequest({ ...createRequest(), preview_digest: hex("x").toUpperCase() }, "create"),
    ).toBeNull();
    expect(
      validateFreshConversationRequest({ ...createRequest(), preview_digest: `${hex("x").slice(1)}0` }, "create"),
    ).not.toBeNull();
    expect(
      validateFreshConversationRequest({ ...previewRequest(), preview_digest: hex("extra") }, "preview"),
    ).toBeNull();
    expect(
      validateFreshConversationRequest({ ...createRequest(), surprise: 1 }, "create"),
    ).toBeNull();
  });

  it("rejects non-plain and hostile request values without leaking errors", () => {
    for (const junk of [null, 42, "x", [], true, new Map(), new Date(), () => {}, Object.create(new Date())]) {
      expect(validateFreshConversationRequest(junk, "preview")).toBeNull();
    }
    const hostile: Body = { work_ref: WORK, operation_key: KEY };
    throwingProp(hostile, "message");
    expect(validateFreshConversationRequest(hostile, "preview")).toBeNull();
  });

  it("refuses an operation outside the closed set", () => {
    expect(validateFreshConversationRequest(previewRequest(), "bogus" as never)).toBeNull();
  });
});

describe("decodeFreshConversationResult", () => {
  it("decodes the preview branch end to end", () => {
    const data = okData(okFrame(dataBody({ state: "PREVIEW_READY", preview: previewBody() })), "preview");
    expect(data).toEqual({
      schema: DATA_SCHEMA,
      operation_key: KEY,
      work_ref: WORK,
      state: "PREVIEW_READY",
      effect: "NONE",
      parent_consumed: false,
      can_send: false,
      preview: previewBody(),
      locator: null,
      session: null,
      result: null,
    });
  });

  it("decodes create branches: admitted pending pointer and genuine created", () => {
    const admitted = okData(
      okFrame(dataBody({ state: "ADMITTED", effect: "ADMITTED", locator: locatorBody(null, null) })),
      "create",
    );
    expect(admitted.locator).toEqual(locatorBody(null, null));
    expect(admitted.session).toBeNull();
    const created = okData(
      okFrame(
        dataBody({
          state: "CREATED",
          effect: "COMMITTED",
          locator: locatorBody(),
          session: sessionBody(),
        }),
      ),
      "create",
    );
    expect(created.session).toEqual(sessionBody());
  });

  it("decodes status, read, settled, absent and reconciliation branches", () => {
    expect(okData(okFrame(dataBody({ state: "ADMITTED", locator: locatorBody() })), "status").state).toBe("ADMITTED");
    expect(okData(okFrame(dataBody({ state: "ABSENT" })), "status").state).toBe("ABSENT");
    const settled = okData(
      okFrame(dataBody({ state: "SETTLED", locator: locatorBody() })),
      "status",
    );
    expect(settled.result).toBeNull();
    const read = okData(
      okFrame(dataBody({ state: "SETTLED", locator: locatorBody(), result: resultBody() })),
      "read",
    );
    expect(read.result).toEqual(resultBody());
    expect(okData(okFrame(dataBody({ state: "RECONCILIATION_REQUIRED", locator: locatorBody("j2", null) })), "status").state).toBe(
      "RECONCILIATION_REQUIRED",
    );
    const readCreated = decodeFreshConversationResult(
      okFrame(dataBody({ state: "CREATED", locator: locatorBody(), session: sessionBody() }),"read"),
      "read",
      EXPECTED,
    );
    expect(readCreated).not.toBeNull();
  });

  it("detaches opaque JSON: mutating the decode never aliases the producer object", () => {
    const frame = okFrame(
      dataBody({ state: "PREVIEW_READY", preview: previewBody(), result: null }),
    );
    const data = okData(frame, "preview");
    (data.preview!.grounding as Body).topic = "mutated";
    expect((frame.data as Body).preview).toEqual(previewBody());
    const readFrame = okFrame(
      dataBody({ state: "SETTLED", locator: locatorBody(), result: resultBody() }),
    );
    const read = okData(readFrame, "read");
    (read.result!.envelope as Body).marker = "forged";
    ((read.result!.envelope as Body).nested as Body).n = 99;
    expect(envelope()).toEqual({ marker: "sealed", nested: { n: 1, tags: ["a"] } });
    expect(read.result!.digest).toBe(envelopeDigest());
  });

  it("matches the exact expected selector pair", () => {
    const frame = okFrame(dataBody({ state: "ABSENT" }));
    expect(decodeFreshConversationResult(frame, "status", { work_ref: "WS:other", operation_key: KEY })).toBeNull();
    expect(
      decodeFreshConversationResult(frame, "status", { work_ref: WORK, operation_key: "other-key" }),
    ).toBeNull();
    refused(okFrame(dataBody({ ...dataBody(), work_ref: "WS:other" })), "status");
    refused(okFrame(dataBody({ ...dataBody(), operation_key: "other-key" })), "status");
  });

  it("rejects frame shape drift in both branches", () => {
    refused({ ...okFrame(dataBody({ state: "ABSENT" })), extra: 1 }, "status");
    refused({ ok: true }, "status");
    refused({ ok: "yes", data: dataBody({ state: "ABSENT" }) }, "status");
    refused(okFrame(dataBody({ state: "ABSENT" })), "bogus" as never);
    refused({ ...errorFrame(), extra: 1 }, "read");
    refused({ ...errorFrame(), data: dataBody({ state: "ABSENT" }) }, "read");
    refused({ ok: false, data: null }, "read");
    refused({ ok: true, data: null }, "read");
    for (const junk of [null, 7, "frame", [], () => {}, new Date()]) {
      expect(decodeFreshConversationResult(junk, "read", EXPECTED)).toBeNull();
    }
  });

  it("keeps PREVIEW_READY exclusive to the preview operation", () => {
    const previewState = dataBody({ state: "PREVIEW_READY", preview: previewBody() });
    refused(okFrame(previewState), "create");
    refused(okFrame(previewState), "status");
    refused(okFrame(previewState), "read");
    refused(okFrame(dataBody({ state: "ADMITTED", effect: "ADMITTED", locator: locatorBody(), preview: previewBody() })), "create");
    refused(okFrame(dataBody({ state: "ADMITTED", effect: "ADMITTED", locator: locatorBody() })), "preview");
    refused(okFrame(dataBody({ state: "PREVIEW_READY", effect: "ADMITTED", preview: previewBody() })), "preview");
  });

  it("enforces effect discipline per operation", () => {
    refused(okFrame(dataBody({ state: "ADMITTED", effect: "COMMITTED", locator: locatorBody() })), "status");
    refused(okFrame(dataBody({ state: "SETTLED", effect: "ADMITTED", locator: locatorBody() })), "read");
    expect(
      okData(okFrame(dataBody({ state: "ADMITTED", effect: "COMMITTED", locator: locatorBody() })), "create").effect,
    ).toBe("COMMITTED");
  });

  it("rejects nullability and state contradictions", () => {
    refused(okFrame(dataBody({ state: "ABSENT", locator: locatorBody() })), "status");
    refused(okFrame(dataBody({ state: "ABSENT", session: sessionBody() })), "status");
    refused(okFrame(dataBody({ state: "ABSENT", result: resultBody() })), "read");
    refused(okFrame(dataBody({ state: "PREVIEW_READY", preview: previewBody(), locator: locatorBody() })), "preview");
    refused(okFrame(dataBody({ state: "PREVIEW_READY", preview: previewBody(), result: resultBody() })), "read");
    refused(okFrame(dataBody({ state: "ADMITTED" })), "create");
    refused(okFrame(dataBody({ state: "RECONCILIATION_REQUIRED" })), "status");
    refused(okFrame(dataBody({ state: "SETTLED" })), "read");
    refused(okFrame(dataBody({ state: "ADMITTED", locator: locatorBody(), session: sessionBody() })), "create");
    refused(okFrame(dataBody({ state: "SETTLED", locator: locatorBody(), session: sessionBody("att-1") })), "read");
  });

  it("requires a genuine created session bound to the actual locator attempt", () => {
    const created = (over: Body): Body =>
      dataBody({ state: "CREATED", effect: "COMMITTED", locator: locatorBody(), ...over });
    refused(okFrame(created({ session: null })), "create");
    refused(okFrame(dataBody({ state: "CREATED", effect: "COMMITTED", locator: locatorBody(null, null), session: sessionBody() })), "create");
    refused(okFrame(dataBody({ state: "CREATED", effect: "COMMITTED", locator: locatorBody("j", null), session: sessionBody() })), "create");
    refused(okFrame(created({ session: sessionBody("att-2") })), "create");
    refused(okFrame(created({ session: { ...sessionBody(), binding_digest: hex("x").toUpperCase() } })), "create");
    refused(okFrame(created({ session: { ...sessionBody(), generation: "" } })), "create");
    refused(okFrame(created({ session: { ...sessionBody(), extra: 1 } })), "create");
  });

  it("bounds the locator exactly", () => {
    const settled = (over: Body): Body => dataBody({ state: "SETTLED", locator: { ...locatorBody(), ...over } });
    expect(okData(okFrame(settled({ job_id: null, attempt_id: null })), "read").locator!.root_job_id).toBe("root-1");
    expect(okData(okFrame(settled({ root_job_id: "r".repeat(256) })), "read").locator!.root_job_id).toHaveLength(256);
    refused(okFrame(settled({ work_ref: "WS:other" })), "read");
    refused(okFrame(settled({ root_job_id: "" })), "read");
    refused(okFrame(settled({ root_job_id: "root\n1" })), "read");
    refused(okFrame(settled({ root_job_id: "r".repeat(257) })), "read");
    refused(okFrame(settled({ job_id: 7 })), "read");
    refused(okFrame(settled({ attempt_id: {} })), "read");
    refused(okFrame(settled({ extra: 1 })), "read");
  });

  it("bounds the preview object and its opaque grounding", () => {
    const badPreview = (over: Body): Body =>
      dataBody({ state: "PREVIEW_READY", preview: { ...previewBody(), ...over } });
    refused(okFrame(badPreview({ digest: hex("p").toUpperCase() })), "preview");
    refused(okFrame(badPreview({ profile_digest: hex("p").slice(1) })), "preview");
    refused(okFrame(badPreview({ source_digest: "nothex" })), "preview");
    refused(okFrame(badPreview({ attempt_limit: 2 })), "preview");
    refused(okFrame(badPreview({ attempt_limit: "1" })), "preview");
    refused(okFrame(badPreview({ worker_account: "SESSION_ATTESTED" })), "preview");
    refused(okFrame(badPreview({ extra: 1 })), "preview");
    refused(okFrame(badPreview({ grounding: [1] })), "preview");
    refused(okFrame(badPreview({ grounding: nest(17) })), "preview");
    expect(okData(okFrame(badPreview({ grounding: nest(16) })), "preview").preview).not.toBeNull();
    refused(okFrame(badPreview({ grounding: { pad: "x".repeat(8200) } })), "preview");
    expect(
      okData(okFrame(badPreview({ grounding: { pad: "x".repeat(8000) } })), "preview").preview!.grounding,
    ).toEqual({ pad: "x".repeat(8000) });
  });

  it("re-verifies the result digest against the exact envelope and bounds it", () => {
    const settled = (over: Body): Body => dataBody({ state: "SETTLED", locator: locatorBody(), result: { ...resultBody(), ...over } });
    // Override the envelope with its own correct digest (mutation failures above
    // already cover the mismatch path).
    const settledEnvelope = (value: unknown): Body =>
      dataBody({
        state: "SETTLED",
        locator: locatorBody(),
        result: { digest: sha256Hex(canonicalJson(value)), envelope: value },
      });
    refused(okFrame(settled({ digest: hex("forged") })), "read");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: { ...envelope(), extra: true } } }), "read");
    refused(okFrame(settled({ envelope: [1, 2] })), "read");
    refused(okFrame(settled({ envelope: null })), "read");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: { n: Number.NaN } } }), "read");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: { n: Infinity } } }), "read");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: { gone: undefined } } }), "read");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: { fn: () => 1 } } }), "read");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: { at: new Date() } } }), "read");
    refused(okFrame(settled({ envelope: nest(25) })), "read");
    expect(okData(okFrame(settledEnvelope(nest(24))), "read").result!.envelope).toEqual(nest(24));
    refused(okFrame(settled({ envelope: { pad: "y".repeat(16400) } })), "read");
    expect(okData(okFrame(settledEnvelope({ pad: "y".repeat(16000) })), "read").result!.digest).toBe(
      sha256Hex(canonicalJson({ pad: "y".repeat(16000) })),
    );
    const cyclic: Body = { a: 1 };
    cyclic.self = cyclic;
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: cyclic } }), "read");
    const hostileEnvelope: Body = { fine: 1 };
    throwingProp(hostileEnvelope, "boom");
    refused(okFrame({ ...settled({}), result: { digest: envelopeDigest(), envelope: hostileEnvelope } }), "read");
  });

  it("carries a result envelope only for a read of CREATED/SETTLED", () => {
    const withResult = (state: string, effect = "NONE"): Body =>
      dataBody({ state, effect, locator: locatorBody(), session: sessionBody(), result: resultBody() });
    refused(okFrame(withResult("ADMITTED", "ADMITTED")), "create");
    refused(okFrame(withResult("ADMITTED")), "status");
    refused(okFrame(withResult("ABSENT")), "read");
    refused(okFrame(withResult("RECONCILIATION_REQUIRED")), "status");
    // A read frame is NONE-effect even when the state is CREATED.
    expect(okData(okFrame(withResult("CREATED")), "read").result!.digest).toBe(
      envelopeDigest(),
    );
    // A read of SETTLED without a sealed envelope is still decodable data.
    expect(
      okData(okFrame(dataBody({ state: "SETTLED", locator: locatorBody(), result: null })), "read").result,
    ).toBeNull();
  });

  it("preserves the closed error branch as data only", () => {
    const decoded = decodeFreshConversationResult(errorFrame(), "read", EXPECTED);
    expect(decoded).not.toBeNull();
    expect((decoded as { ok: boolean }).ok).toBe(false);
    const branch = decoded as { ok: false; data: null; error: { code: string; message: string } };
    expect(branch.data).toBeNull();
    expect(branch.error).toEqual({ code: "PRE_EFFECT_REFUSED", message: "admission refused" });
    const long = decodeFreshConversationResult(
      errorFrame({ error: { code: "c".repeat(96), message: "m".repeat(512) } }),
      "read",
      EXPECTED,
    );
    expect(long).not.toBeNull();
    for (const bad of [
      { code: "", message: "m" },
      { code: "c".repeat(97), message: "m" },
      { code: "has\nnewline", message: "m" },
      { code: "c", message: "" },
      { code: "c", message: "m".repeat(513) },
      { code: "c", message: "tab\tinside" },
      { code: 7, message: "m" },
      { code: "c", message: null },
      { code: "c" },
    ]) {
      expect(
        decodeFreshConversationResult(errorFrame({ error: bad }), "read", EXPECTED),
      ).toBeNull();
    }
    refused(errorFrame({ error: [1] }), "read");
  });

  it("survives hostile frames without propagating raw errors", () => {
    const hostile: Body = { ok: true, data: 1 };
    throwingProp(hostile, "data");
    expect(decodeFreshConversationResult(hostile, "read", EXPECTED)).toBeNull();
    const hostileError: Body = errorFrame();
    throwingProp(hostileError, "error");
    expect(decodeFreshConversationResult(hostileError, "read", EXPECTED)).toBeNull();
    expect(decodeFreshConversationResult(okFrame(dataBody({ state: "ABSENT" })), "status", null as never)).toBeNull();
    expect(
      decodeFreshConversationResult(okFrame(dataBody({ state: "ABSENT" })), "status", {
        work_ref: 5 as unknown as string,
        operation_key: KEY,
      }),
    ).toBeNull();
  });

  it("rejects data-record key drift, schema drift and literal drift", () => {
    const bad = (over: Body): Body => dataBody(over);
    refused(okFrame({ ...bad({ state: "ABSENT" }), extra: 1 }), "status");
    refused(okFrame({ ...bad({ state: "ABSENT" }), can_send: undefined }), "status");
    const missing = bad({ state: "ABSENT" }) as Body;
    delete missing.can_send;
    refused(okFrame(missing), "status");
    refused(okFrame(bad({ schema: "mastermind.executive.fresh_conversation.v1" })), "status");
    refused(okFrame(bad({ state: "SETTLED_NOW" })), "status");
    refused(okFrame(bad({ state: "settled" })), "status");
    refused(okFrame(bad({ effect: "COMMITTED_NOW" })), "status");
    refused(okFrame(bad({ parent_consumed: true })), "status");
    refused(okFrame(bad({ can_send: true })), "status");
    refused(okFrame(bad({ parent_consumed: false, can_send: false, schema: 7 })), "status");
  });
});
