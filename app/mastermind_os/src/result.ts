/**
 * Strict shared/Workspace result decoder for the D parent-ratified contract.
 *
 * The Missionv3 result reference index identifies a single tuple
 * (work_ref, root_job_id, job_id, attempt_id, result_envelope_digest). This
 * module validates the frozen outer body `mastermind.workspace_role_result.v1`,
 * its typed `source_observation`, and the embedded shared
 * `mastermind.fabric_role_result_view.v1` projection as inert display data.
 *
 * Budget enforcement is byte-precise for both the HTTP body (<=16KiB) and the
 * canonical compact `{ok:true,result:BODY}` plus LF wrapper (<=16KiB). The
 * decoder never widens either cap. Consumer callers should pass already-bounded
 * bytes; `decodeResultBytes` and `decodeResultSocketEnvelope` will measure and
 * refuse anything larger.
 */

export interface ResultSelection {
  workRef: string;
  rootJobId: string;
  jobId: string;
  attemptId: string;
  resultEnvelopeDigest: string;
}

export interface ResultEnvelopeDigestShape {
  schema: "mastermind.workspace_role_result.v1";
  selection: {
    work_ref: string;
    root_job_id: string;
    job_id: string;
    attempt_id: string;
    result_envelope_digest: string;
  };
  availability: "AVAILABLE" | "CONTENT_OVER_BUDGET" | "UNAVAILABLE";
  reason_codes: string[];
  source_observation: ResultSourceObservation;
  result: ResultRoleView | null;
}

export interface ResultSourceObservation {
  schema: "mastermind.workspace_result_observation.v1";
  state: "SAME" | "UNKNOWN" | "CONFLICT";
  selection: {
    work_ref: string;
    root_job_id: string;
    job_id: string;
    attempt_id: string;
    result_envelope_digest: string;
  };
  control_room: null | {
    instance_before: string | null;
    instance_after: string | null;
    publication_before: number | null;
    publication_after: number | null;
    document_digest: string | null;
    source_validity_digest: string | null;
    cache_currentness_digest: string | null;
  };
  runtime: null | {
    schema: "mastermind.runtime_read_observation.v1";
    state: "SAME" | "UNKNOWN" | "CONFLICT";
    source_identity: string | null;
    before: number | null;
    after: number | null;
  };
}

export interface ResultRoleView {
  schema: "mastermind.fabric_role_result_view.v1";
  selection: {
    root_job_id: string;
    job_id: string;
    attempt_id: string;
    result_envelope_digest: string;
  };
  role: "aggregation" | "plan" | "work" | "review" | "repair";
  execution_status: "COMPLETED";
  acceptance: "NOT_PROJECTED";
  role_result_digest: string;
  generation: {
    schema: "mastermind.runtime_read_observation.v1";
    state: "SAME";
    source_identity: string;
    before: number;
    after: number;
  };
  availability: "AVAILABLE" | "CONTENT_OVER_BUDGET";
  content_complete: boolean;
  review: null | {
    verdict: "approve" | "reject";
    reviewed_job_id: string;
    reviewed_attempt_id: string;
    reviewed_result_digest: string;
    latest_revision_currentness: "UNPROVEN";
  };
  counts: {
    findings: null | {
      total: number;
      blocking: number;
      warning: number;
      info: number;
    };
    next_actions: number;
  };
  content: null | {
    role_result: unknown;
    summary: string;
    next_actions: string[];
  };
  omitted: string[];
}

export interface UnavailableResult {
  kind: "LOCAL_UNAVAILABLE";
  reason:
    | "OVER_BUDGET"
    | "SOURCE_UNAVAILABLE"
    | "SOURCE_CHANGED"
    | "RESPONSE_OVER_BUDGET";
  selection: ResultSelection;
}

const WS_REF = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const JOB_REF = /^JOB-[0-9]{1,9}$/;
const ATTEMPT_REF = /^ATT-[0-9a-f]{32}$/;
const DIGEST_REF = /^[0-9a-f]{64}$/;

const REASON_CODES = [
  "CONTENT_OVER_BUDGET",
  "OVER_BUDGET",
  "SOURCE_UNAVAILABLE",
  "SOURCE_CHANGED",
  "RESPONSE_OVER_BUDGET",
] as const;

export const RESULT_HTTP_BODY_BYTES = 16_384;
export const RESULT_SOCKET_ENVELOPE_BYTES = 16_384;

const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k));
const oneOf = <T extends string>(v: unknown, xs: readonly T[]): v is T =>
  typeof v === "string" && (xs as readonly string[]).includes(v);
const int = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): v is number =>
  Number.isInteger(v) && (v as number) >= min && (v as number) <= max;
const hash = (v: unknown): v is string =>
  typeof v === "string" && DIGEST_REF.test(v);

// C0 controls except TAB (0x09), LF (0x0A) and CR (0x0D): 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F and DEL 0x7F.
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;
// Escaped source notation only; semantics identical to the previous raw-byte character class.
const PRIVATE_LEAK = new RegExp(
  "(?:\\b(?:x-ccr-token|authorization|bearer|api[_ -]?key|access[_ -]?token|refresh[_ -]?token)\\b|\\b(?:token|secret|password|session_id)\\s*[:=]|\\b(?:gh[pousr_]|sk-|xox[baprs]-)[a-z0-9_-]+|\\b[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}\\b|\\b[a-z0-9.-]+\\.(?:local|internal|lan)\\b|(?:https?|file|ftp):\\/\\/|~\\/|(?:localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|\\[?::1\\]?|10\\.\\d+\\.\\d+\\.\\d+|192\\.168\\.\\d+\\.\\d+|172\\.(?:1[6-9]|2\\d|3[01])\\.\\d+\\.\\d+)(?::\\d+)?)",
  "i",
);
const text = (v: unknown, max = 4096): v is string =>
  typeof v === "string" &&
  v.length > 0 &&
  v.length <= max &&
  !CONTROL.test(v) &&
  !PRIVATE_LEAK.test(v);

// Matches the canonical result owner's _text(maximum=8192, nonempty=False).
// Count Unicode scalar values as Python does; lone UTF-16 surrogates cannot
// encode as canonical UTF-8. Content remains inert text at the React boundary.
function canonicalNextAction(value: unknown): value is string {
  if (typeof value !== "string" || value.includes("\u0000")) return false;
  let characters = 0;
  for (const character of value) {
    const point = character.codePointAt(0)!;
    if ((point >= 0xd800 && point <= 0xdfff) || ++characters > 8192)
      return false;
  }
  return true;
}

export function normalizeResultSelection(v: unknown): ResultSelection | null {
  if (
    !record(v) ||
    !exact(v, [
      "workRef",
      "rootJobId",
      "jobId",
      "attemptId",
      "resultEnvelopeDigest",
    ])
  )
    return null;
  const w = v.workRef as string,
    r = v.rootJobId as string,
    j = v.jobId as string,
    a = v.attemptId as string,
    d = v.resultEnvelopeDigest as string;
  if (
    ![w, r, j, a, d].every((x) => typeof x === "string") ||
    !WS_REF.test(w) ||
    !JOB_REF.test(r) ||
    !JOB_REF.test(j) ||
    !ATTEMPT_REF.test(a) ||
    !DIGEST_REF.test(d)
  )
    return null;
  return {
    workRef: w,
    rootJobId: r,
    jobId: j,
    attemptId: a,
    resultEnvelopeDigest: d,
  };
}

export function selectionsEqual(
  expected: ResultSelection,
  actual: ResultSelection,
): boolean {
  return (
    expected.workRef === actual.workRef &&
    expected.rootJobId === actual.rootJobId &&
    expected.jobId === actual.jobId &&
    expected.attemptId === actual.attemptId &&
    expected.resultEnvelopeDigest === actual.resultEnvelopeDigest
  );
}

function selectionWire(
  s: ResultSelection,
): ResultSourceObservation["selection"] {
  return {
    work_ref: s.workRef,
    root_job_id: s.rootJobId,
    job_id: s.jobId,
    attempt_id: s.attemptId,
    result_envelope_digest: s.resultEnvelopeDigest,
  };
}

function isUtf8(bytes: Uint8Array): boolean {
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return true;
  } catch {
    return false;
  }
}

export function decodeResultBytes(
  bytes: Uint8Array,
  cap: number,
  expected: ResultSelection,
): ResultEnvelopeDigestShape | null {
  if (bytes.byteLength > Math.min(cap, RESULT_HTTP_BODY_BYTES)) return null;
  if (!isUtf8(bytes)) return null;
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  return decodeResultEnvelope(raw, expected);
}

export function decodeResultEnvelope(
  value: unknown,
  expected: ResultSelection,
): ResultEnvelopeDigestShape | null {
  try {
    if (
      new TextEncoder().encode(
        JSON.stringify({ ok: true, result: value }) + "\n",
      ).byteLength > RESULT_SOCKET_ENVELOPE_BYTES
    )
      return null;
  } catch {
    return null;
  }
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "selection",
      "availability",
      "reason_codes",
      "source_observation",
      "result",
    ]) ||
    value.schema !== "mastermind.workspace_role_result.v1"
  )
    return null;

  const selectionWireValue = value.selection;
  if (
    !record(selectionWireValue) ||
    !exact(selectionWireValue, [
      "work_ref",
      "root_job_id",
      "job_id",
      "attempt_id",
      "result_envelope_digest",
    ]) ||
    selectionWireValue.work_ref !== expected.workRef ||
    selectionWireValue.root_job_id !== expected.rootJobId ||
    selectionWireValue.job_id !== expected.jobId ||
    selectionWireValue.attempt_id !== expected.attemptId ||
    selectionWireValue.result_envelope_digest !== expected.resultEnvelopeDigest
  )
    return null;

  if (
    !oneOf(value.availability, [
      "AVAILABLE",
      "CONTENT_OVER_BUDGET",
      "UNAVAILABLE",
    ] as const)
  )
    return null;

  if (
    !Array.isArray(value.reason_codes) ||
    value.reason_codes.length > 4 ||
    !value.reason_codes.every((c) => oneOf(c, REASON_CODES))
  )
    return null;

  const observation = decodeSourceObservation(
    value.source_observation,
    expected,
    value.availability,
    value.reason_codes,
  );
  if (!observation) return null;

  let roleView: ResultRoleView | null = null;
  if (value.result !== null) {
    roleView = decodeRoleResultView(value.result, expected);
    if (!roleView) return null;
    if (
      value.availability === "AVAILABLE" &&
      roleView.availability !== "AVAILABLE"
    )
      return null;
    if (
      value.availability === "CONTENT_OVER_BUDGET" &&
      roleView.availability !== "CONTENT_OVER_BUDGET"
    )
      return null;
    if (value.availability === "UNAVAILABLE") return null;
  } else if (value.availability !== "UNAVAILABLE") return null;

  // Availability <-> reason_codes <-> result consistency
  if (value.availability === "AVAILABLE") {
    if (
      value.reason_codes.length !== 0 ||
      roleView === null ||
      roleView.content_complete !== true ||
      roleView.omitted.length !== 0
    )
      return null;
  } else if (value.availability === "CONTENT_OVER_BUDGET") {
    if (
      value.reason_codes.length !== 1 ||
      value.reason_codes[0] !== "CONTENT_OVER_BUDGET" ||
      roleView === null ||
      roleView.content !== null ||
      roleView.content_complete !== false
    )
      return null;
  } else {
    // UNAVAILABLE
    if (
      value.reason_codes.length !== 1 ||
      roleView !== null ||
      !oneOf(value.reason_codes[0], [
        "OVER_BUDGET",
        "SOURCE_UNAVAILABLE",
        "SOURCE_CHANGED",
        "RESPONSE_OVER_BUDGET",
      ] as const)
    )
      return null;
  }

  if (
    value.availability === "UNAVAILABLE" &&
    observation.state !==
      (value.reason_codes[0] === "SOURCE_CHANGED" ? "CONFLICT" : "UNKNOWN")
  )
    return null;

  // Receipt binding: for SAME observation, result.generation must match
  // source_observation.runtime exactly. UNPROVEN scoping is preserved
  // (review verdict never implies fresh currentness).
  if (
    value.availability !== "UNAVAILABLE" &&
    roleView !== null &&
    observation.state === "SAME" &&
    observation.runtime !== null
  ) {
    const g = roleView.generation;
    const r = observation.runtime;
    if (
      g.schema !== r.schema ||
      g.state !== "SAME" ||
      g.state !== r.state ||
      g.source_identity !== r.source_identity ||
      g.before !== r.before ||
      g.after !== r.after
    )
      return null;
  }

  return value as unknown as ResultEnvelopeDigestShape;
}

function decodeSourceObservation(
  value: unknown,
  expected: ResultSelection,
  availability: "AVAILABLE" | "CONTENT_OVER_BUDGET" | "UNAVAILABLE",
  reasons: string[],
): ResultSourceObservation | null {
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "state",
      "selection",
      "control_room",
      "runtime",
    ]) ||
    value.schema !== "mastermind.workspace_result_observation.v1" ||
    !oneOf(value.state, ["SAME", "UNKNOWN", "CONFLICT"] as const)
  )
    return null;
  const sel = value.selection;
  const expectedWire = selectionWire(expected);
  if (
    !record(sel) ||
    !exact(sel, [
      "work_ref",
      "root_job_id",
      "job_id",
      "attempt_id",
      "result_envelope_digest",
    ]) ||
    sel.work_ref !== expectedWire.work_ref ||
    sel.root_job_id !== expectedWire.root_job_id ||
    sel.job_id !== expectedWire.job_id ||
    sel.attempt_id !== expectedWire.attempt_id ||
    sel.result_envelope_digest !== expectedWire.result_envelope_digest
  )
    return null;

  const cr = value.control_room;
  if (cr !== null) {
    if (
      !record(cr) ||
      !exact(cr, [
        "instance_before",
        "instance_after",
        "publication_before",
        "publication_after",
        "document_digest",
        "source_validity_digest",
        "cache_currentness_digest",
      ]) ||
      !(cr.instance_before === null || text(cr.instance_before, 64)) ||
      !(cr.instance_after === null || text(cr.instance_after, 64)) ||
      !(cr.publication_before === null || int(cr.publication_before, 1)) ||
      !(cr.publication_after === null || int(cr.publication_after, 1)) ||
      !(cr.document_digest === null || hash(cr.document_digest)) ||
      !(
        cr.source_validity_digest === null || hash(cr.source_validity_digest)
      ) ||
      !(
        cr.cache_currentness_digest === null ||
        hash(cr.cache_currentness_digest)
      )
    )
      return null;
  }

  const rt = value.runtime;
  if (rt !== null) {
    if (
      !record(rt) ||
      !exact(rt, ["schema", "state", "source_identity", "before", "after"]) ||
      rt.schema !== "mastermind.runtime_read_observation.v1" ||
      !oneOf(rt.state, ["SAME", "UNKNOWN", "CONFLICT"] as const) ||
      !(
        rt.source_identity === null ||
        /^[0-9a-f]{32}$/.test(asString(rt, "source_identity"))
      ) ||
      !(
        rt.before === null ||
        (int(rt.before, 0) && typeof rt.before === "number")
      ) ||
      !(rt.after === null || (int(rt.after, 0) && typeof rt.after === "number"))
    )
      return null;
  }

  if (availability === "AVAILABLE" || availability === "CONTENT_OVER_BUDGET") {
    if (
      value.state !== "SAME" ||
      cr === null ||
      rt === null ||
      rt.state !== "SAME"
    )
      return null;
    if (
      cr.instance_before === null ||
      cr.instance_after === null ||
      cr.instance_before !== cr.instance_after ||
      cr.publication_before === null ||
      cr.publication_after === null ||
      cr.publication_before !== cr.publication_after ||
      cr.document_digest === null ||
      cr.source_validity_digest === null ||
      cr.cache_currentness_digest === null
    )
      return null;
    if (
      rt.source_identity === null ||
      asString(rt, "source_identity").length !== 32 ||
      rt.before === null ||
      rt.after === null ||
      rt.before !== rt.after ||
      typeof rt.before !== "number" ||
      typeof rt.after !== "number"
    )
      return null;
  } else {
    // UNAVAILABLE: both sub-objects must be null and state must NOT be SAME.
    if (cr !== null || rt !== null) return null;
    if (value.state === "SAME") return null;
    // Frozen observation-state pinning: SOURCE_CHANGED means the observed
    // source changed under the reader (CONFLICT); every other unavailable
    // reason never established an observation (UNKNOWN).
    if (reasons.length !== 1) return null;
    if (reasons[0] === "SOURCE_CHANGED") {
      if (value.state !== "CONFLICT") return null;
    } else if (value.state !== "UNKNOWN") return null;
  }

  return value as unknown as ResultSourceObservation;
}

function decodeRoleResultView(
  value: unknown,
  expected: ResultSelection,
): ResultRoleView | null {
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "selection",
      "role",
      "execution_status",
      "acceptance",
      "role_result_digest",
      "generation",
      "availability",
      "content_complete",
      "review",
      "counts",
      "content",
      "omitted",
    ]) ||
    value.schema !== "mastermind.fabric_role_result_view.v1"
  )
    return null;

  const sel = value.selection;
  if (
    !record(sel) ||
    !exact(sel, [
      "root_job_id",
      "job_id",
      "attempt_id",
      "result_envelope_digest",
    ]) ||
    sel.root_job_id !== expected.rootJobId ||
    sel.job_id !== expected.jobId ||
    sel.attempt_id !== expected.attemptId ||
    sel.result_envelope_digest !== expected.resultEnvelopeDigest
  )
    return null;

  if (
    !oneOf(value.role, [
      "aggregation",
      "plan",
      "work",
      "review",
      "repair",
    ] as const) ||
    value.execution_status !== "COMPLETED" ||
    value.acceptance !== "NOT_PROJECTED" ||
    !hash(value.role_result_digest) ||
    !oneOf(value.availability, ["AVAILABLE", "CONTENT_OVER_BUDGET"] as const)
  )
    return null;

  if (typeof value.content_complete !== "boolean") return null;

  const gen = value.generation;
  if (
    !record(gen) ||
    !exact(gen, ["schema", "state", "source_identity", "before", "after"]) ||
    gen.schema !== "mastermind.runtime_read_observation.v1" ||
    gen.state !== "SAME" ||
    !/^[0-9a-f]{32}$/.test(asString(gen, "source_identity")) ||
    typeof gen.before !== "number" ||
    typeof gen.after !== "number" ||
    !Number.isInteger(gen.before) ||
    !Number.isInteger(gen.after) ||
    gen.before !== gen.after ||
    gen.before < 0
  )
    return null;

  // Role <-> review/findings nullability: the projection review block exists
  // for exactly the review role, and findings counts exist with exactly that
  // block. No other role may carry a review projection or finding counts.
  if (value.role === "review" && value.review === null) return null;
  if (value.role !== "review" && value.review !== null) return null;

  const rv = value.review;
  let review: ResultRoleView["review"] = null;
  if (rv !== null) {
    if (
      !record(rv) ||
      !exact(rv, [
        "verdict",
        "reviewed_job_id",
        "reviewed_attempt_id",
        "reviewed_result_digest",
        "latest_revision_currentness",
      ]) ||
      !oneOf(rv.verdict, ["approve", "reject"] as const) ||
      !JOB_REF.test(asString(rv, "reviewed_job_id")) ||
      !ATTEMPT_REF.test(asString(rv, "reviewed_attempt_id")) ||
      !hash(asString(rv, "reviewed_result_digest")) ||
      rv.latest_revision_currentness !== "UNPROVEN"
    )
      return null;
    review = rv as unknown as ResultRoleView["review"];
  }

  const counts = value.counts;
  if (!record(counts) || !exact(counts, ["findings", "next_actions"]))
    return null;
  const fc = counts.findings;
  let findings: ResultRoleView["counts"]["findings"] = null;
  if (fc !== null) {
    if (
      !record(fc) ||
      !exact(fc, ["total", "blocking", "warning", "info"]) ||
      !int(fc.total, 0) ||
      !int(fc.blocking, 0) ||
      !int(fc.warning, 0) ||
      !int(fc.info, 0) ||
      fc.blocking + fc.warning + fc.info !== fc.total
    )
      return null;
    findings = fc as unknown as ResultRoleView["counts"]["findings"];
  } else if (rv !== null) return null;
  if (review === null && counts.findings !== null) return null;
  if (!int(counts.next_actions, 0)) return null;

  const content = value.content;
  const omitted = value.omitted;
  if (
    !Array.isArray(omitted) ||
    omitted.length > 3 ||
    !omitted.every(
      (s) => s === "role_result" || s === "summary" || s === "next_actions",
    ) ||
    new Set(omitted).size !== omitted.length
  )
    return null;

  if (value.availability === "AVAILABLE") {
    if (value.content_complete !== true) return null;
    if (
      content === null ||
      !record(content) ||
      !exact(content, ["role_result", "summary", "next_actions"]) ||
      typeof content.summary !== "string" ||
      content.summary.length > 16_384 ||
      !Array.isArray(content.next_actions) ||
      content.next_actions.length > 16 ||
      !content.next_actions.every(canonicalNextAction) ||
      new Set(content.next_actions).size !== content.next_actions.length
    )
      return null;
    if (!roleResultRef(content.role_result)) return null;
    if (omitted.length !== 0) return null;
    // next_actions count/content join: the retained exact count must equal
    // the delivered full list.
    if (counts.next_actions !== content.next_actions.length) return null;
    if (review !== null) {
      // Selected role-result verdict/target consistency with the projection
      // review: the inert canonical role_result document is authoritative for
      // the review family, so the projection must agree with it exactly. The
      // reviewed digest is only ever compared here, never used as a pull
      // selector.
      const rr = content.role_result;
      if (
        !record(rr) ||
        rr.verdict !== review.verdict ||
        rr.reviewed_job_id !== review.reviewed_job_id ||
        rr.reviewed_attempt_id !== review.reviewed_attempt_id ||
        rr.reviewed_result_digest !== review.reviewed_result_digest
      )
        return null;
      // Full findings count/content join: tally the delivered findings by
      // severity and require the retained counts to match exactly. Unknown
      // severities cannot be tallied, so they fail closed.
      const fs = rr.findings;
      if (!Array.isArray(fs)) return null;
      let tallyBlocking = 0;
      let tallyWarning = 0;
      let tallyInfo = 0;
      for (const f of fs) {
        if (!record(f)) return null;
        if (f.severity === "blocking") tallyBlocking += 1;
        else if (f.severity === "warning") tallyWarning += 1;
        else if (f.severity === "info") tallyInfo += 1;
        else return null;
      }
      if (
        findings === null ||
        findings.total !== fs.length ||
        findings.blocking !== tallyBlocking ||
        findings.warning !== tallyWarning ||
        findings.info !== tallyInfo
      )
        return null;
    }
  } else {
    // CONTENT_OVER_BUDGET
    if (value.content_complete !== false) return null;
    if (content !== null) return null;
    // omitted is exactly the contract's closed triple, in contract order.
    if (
      omitted.length !== 3 ||
      omitted[0] !== "role_result" ||
      omitted[1] !== "summary" ||
      omitted[2] !== "next_actions"
    )
      return null;
  }

  return value as unknown as ResultRoleView;
}

function roleResultRef(v: unknown): boolean {
  return record(v as Record<string, unknown>);
}

function asString(v: Record<string, unknown>, key: string): string {
  return v[key] as string;
}

export function unavailableResult(
  selection: ResultSelection,
  reason: UnavailableResult["reason"],
): UnavailableResult {
  return { kind: "LOCAL_UNAVAILABLE", selection, reason };
}

/**
 * Decode the canonical compact socket envelope `{ok:true,result:BODY}` plus LF.
 * Measures the exact UTF-8 length and refuses anything larger than
 * RESULT_SOCKET_ENVELOPE_BYTES. Returns the parsed BODY on success.
 */
export function decodeResultSocketEnvelope(
  bytes: Uint8Array,
  expected: ResultSelection,
  cap: number = RESULT_SOCKET_ENVELOPE_BYTES,
):
  | { ok: true; result: ResultEnvelopeDigestShape }
  | {
      ok: false;
      reason: "OVER_BUDGET" | "INVALID_JSON" | "INVALID_SHAPE" | "MALFORMED";
    }
  | null {
  if (bytes.byteLength > Math.min(cap, RESULT_HTTP_BODY_BYTES)) return null;
  if (!isUtf8(bytes)) return null;
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  if (!text.endsWith("\n")) return { ok: false, reason: "INVALID_SHAPE" };
  const stripped = text.slice(0, -1);
  let value: unknown;
  try {
    value = JSON.parse(stripped);
  } catch {
    return { ok: false, reason: "INVALID_JSON" };
  }
  if (!record(value) || !exact(value, ["ok", "result"]) || value.ok !== true)
    return { ok: false, reason: "INVALID_SHAPE" };
  const decoded = decodeResultEnvelope(value.result, expected);
  if (!decoded) return { ok: false, reason: "INVALID_SHAPE" };
  return { ok: true, result: decoded };
}

/**
 * The legacy v1 selection query parser is intentionally separate from the
 * exact result path: the v2 frame takes 5 fields, the legacy one takes 2.
 * Exposed for fixture loading and decoders that need to read v1 byte-only
 * fixtures verbatim.
 */
export const LEGACY_V1_SELECTION_KEYS = ["work_ref", "root_job_id"] as const;
