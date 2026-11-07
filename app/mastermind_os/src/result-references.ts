/**
 * Strict retained-result reference list decoder for the frozen Workspace
 * `result_references` operation (schema `mastermind.workspace_result_references.v1`).
 *
 * Existing HTTP/Web/Tauri reads return the closed BODY directly; the
 * `{ok:true,result:BODY}` socket framing is validated by the backend, so this
 * decoder accepts exactly the BODY and never an alternative outer shape. The
 * frozen byte budget is still measured on the whole canonical framed UTF-8
 * form, mirroring the existing exact-result decoder; the cap is never widened
 * and an over-budget body is refused outright (the owner emits a typed
 * OVER_BUDGET unavailable document instead of an oversized one).
 *
 * The embedded index is the unchanged original
 * `mastermind.fabric_result_reference_index.v1` document exactly as the
 * existing owner emits it, validated against the established nine-key index
 * law (closed keys, partitions, sortedness, disjointness, at most 17 included
 * Job slots). This decoder never truncates, re-sorts, fills or fabricates
 * index partitions to make a body fit, and it never requires the index
 * runtime generation to match any later exact-result read.
 */

import type { ResultSelection } from "./result";

export interface ResultReferencesSelection {
  workRef: string;
  rootJobId: string;
}

export interface ResultReferenceGeneration {
  schema: "mastermind.runtime_read_observation.v1";
  state: "SAME" | "UNKNOWN" | "CONFLICT";
  source_identity: string | null;
  before: number | null;
  after: number | null;
}

export interface ResultReferenceRef {
  root_job_id: string;
  job_id: string;
  attempt_id: string;
  result_envelope_digest: string;
  orchestration_role: "aggregation" | "plan" | "work" | "review" | "repair";
  validation: "UNVALIDATED";
}

export interface ResultReferenceIndex {
  schema: "mastermind.fabric_result_reference_index.v1";
  root_job_id: string;
  snapshot_digest: string | null;
  generation: ResultReferenceGeneration;
  availability: "AVAILABLE" | "PARTIAL";
  refs: ResultReferenceRef[];
  absent_job_ids: string[];
  omitted_job_ids: string[];
  truncated: boolean;
}

export interface ResultReferencesControlRoom {
  instance_before: string | null;
  instance_after: string | null;
  publication_before: number | null;
  publication_after: number | null;
  document_digest: string | null;
  source_validity_digest: string | null;
  cache_currentness_digest: string | null;
}

export interface ResultReferencesRuntime {
  schema: "mastermind.runtime_read_observation.v1";
  state: "SAME";
  source_identity: string;
  before: number;
  after: number;
}

export interface ResultReferencesSourceObservation {
  schema: "mastermind.workspace_source_observation.v1";
  state: "SAME" | "UNKNOWN" | "CONFLICT";
  selection: { work_ref: string; root_job_id: string };
  control_room: ResultReferencesControlRoom | null;
  runtime: ResultReferencesRuntime | null;
}

export interface ResultReferencesCatalogue {
  generated_at: string | null;
  freshness: "CURRENT" | "STALE" | "UNKNOWN";
}

export interface ResultReferencesDocument {
  schema: "mastermind.workspace_result_references.v1";
  selection: { work_ref: string; root_job_id: string };
  availability: "AVAILABLE" | "UNAVAILABLE";
  reason_codes: string[];
  index: ResultReferenceIndex | null;
  source_observation: ResultReferencesSourceObservation;
  catalogue: ResultReferencesCatalogue;
}

export const RESULT_REFERENCES_HTTP_BODY_BYTES = 16_384;
export const RESULT_REFERENCES_SOCKET_ENVELOPE_BYTES = 16_384;

const REFERENCES_SCHEMA = "mastermind.workspace_result_references.v1";
const INDEX_SCHEMA = "mastermind.fabric_result_reference_index.v1";
const RUNTIME_OBSERVATION_SCHEMA = "mastermind.runtime_read_observation.v1";
const SOURCE_OBSERVATION_SCHEMA = "mastermind.workspace_source_observation.v1";

const WS_REF = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const JOB_REF = /^JOB-[0-9]{1,9}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const HEX32 = /^[0-9a-f]{32}$/;
// The established index identifier law: an exact, bounded, opaque string.
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

export const REFERENCE_REASON_CODES = [
  "SOURCE_UNAVAILABLE",
  "SOURCE_CHANGED",
  "OVER_BUDGET",
  "REFERENCE_INDEX_UNAVAILABLE",
] as const;

const INDEX_AVAILABILITY = ["AVAILABLE", "PARTIAL"] as const;
const GENERATION_STATES = ["SAME", "UNKNOWN", "CONFLICT"] as const;
const OBSERVATION_STATES = ["SAME", "UNKNOWN", "CONFLICT"] as const;
const ORCHESTRATION_ROLES = [
  "aggregation",
  "plan",
  "work",
  "review",
  "repair",
] as const;
const FRESHNESS_STATES = ["CURRENT", "STALE", "UNKNOWN"] as const;
const MAX_INCLUDED_SLOTS = 17;

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
  typeof v === "string" && HEX64.test(v);

// C0 controls except TAB (0x09), LF (0x0A) and CR (0x0D), plus DEL 0x7F.
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;
// Escaped source notation only, identical to the exact-result decoder's class.
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

export function normalizeResultReferencesSelection(
  v: unknown,
): ResultReferencesSelection | null {
  if (!record(v) || !exact(v, ["workRef", "rootJobId"])) return null;
  const w = v.workRef as unknown,
    r = v.rootJobId as unknown;
  if (
    typeof w !== "string" ||
    typeof r !== "string" ||
    !WS_REF.test(w) ||
    !JOB_REF.test(r)
  )
    return null;
  return { workRef: w, rootJobId: r };
}

/** Build the exact 5-field result selector for a returned reference row. The
 * caller still qualifies it through normalizeResultSelection before reading. */
export function referenceSelection(
  ref: ResultReferenceRef,
  selection: ResultReferencesSelection,
): ResultSelection {
  return {
    workRef: selection.workRef,
    rootJobId: ref.root_job_id,
    jobId: ref.job_id,
    attemptId: ref.attempt_id,
    resultEnvelopeDigest: ref.result_envelope_digest,
  };
}

function decodeGeneration(value: unknown): ResultReferenceGeneration | null {
  if (
    !record(value) ||
    !exact(value, ["schema", "state", "source_identity", "before", "after"]) ||
    value.schema !== RUNTIME_OBSERVATION_SCHEMA ||
    !oneOf(value.state, GENERATION_STATES)
  )
    return null;
  const identity = value.source_identity;
  if (
    identity !== null &&
    (typeof identity !== "string" || !IDENTIFIER.test(identity))
  )
    return null;
  const before = value.before,
    after = value.after;
  for (const sample of [before, after]) {
    if (
      sample !== null &&
      (typeof sample !== "number" || !Number.isInteger(sample) || sample < 0)
    )
      return null;
  }
  if (value.state === "SAME" || value.state === "CONFLICT") {
    if (typeof before !== "number" || typeof after !== "number") return null;
    if (typeof identity !== "string" || identity.length === 0) return null;
    if (value.state === "SAME" && before !== after) return null;
    if (value.state === "CONFLICT" && before === after) return null;
  }
  return value as unknown as ResultReferenceGeneration;
}

function decodeReferenceRef(
  value: unknown,
  rootJobId: string,
): ResultReferenceRef | null {
  if (
    !record(value) ||
    !exact(value, [
      "root_job_id",
      "job_id",
      "attempt_id",
      "result_envelope_digest",
      "orchestration_role",
      "validation",
    ]) ||
    value.root_job_id !== rootJobId ||
    typeof value.job_id !== "string" ||
    !IDENTIFIER.test(value.job_id) ||
    typeof value.attempt_id !== "string" ||
    !IDENTIFIER.test(value.attempt_id) ||
    typeof value.result_envelope_digest !== "string" ||
    !HEX64.test(value.result_envelope_digest) ||
    !oneOf(value.orchestration_role, ORCHESTRATION_ROLES) ||
    value.validation !== "UNVALIDATED"
  )
    return null;
  return value as unknown as ResultReferenceRef;
}

/** Closed nine-key index validation preserving the established owner law:
 * exact partitions, already-sorted rows, pairwise disjoint Job slots and at
 * most 17 included slots. Nothing is sorted, filled or truncated here. */
function decodeReferenceIndex(
  value: unknown,
  expected: ResultReferencesSelection,
): ResultReferenceIndex | null {
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "root_job_id",
      "snapshot_digest",
      "generation",
      "availability",
      "refs",
      "absent_job_ids",
      "omitted_job_ids",
      "truncated",
    ]) ||
    value.schema !== INDEX_SCHEMA ||
    typeof value.root_job_id !== "string" ||
    !IDENTIFIER.test(value.root_job_id) ||
    value.root_job_id !== expected.rootJobId ||
    !oneOf(value.availability, INDEX_AVAILABILITY) ||
    typeof value.truncated !== "boolean"
  )
    return null;
  const digest = value.snapshot_digest;
  if (digest !== null && (typeof digest !== "string" || !HEX64.test(digest)))
    return null;
  // An AVAILABLE references body carries a finalized SAME generation.
  const generation = decodeGeneration(value.generation);
  if (!generation || generation.state !== "SAME") return null;

  if (
    !Array.isArray(value.refs) ||
    !Array.isArray(value.absent_job_ids) ||
    !Array.isArray(value.omitted_job_ids)
  )
    return null;
  const refs: ResultReferenceRef[] = [];
  for (const row of value.refs) {
    const ref = decodeReferenceRef(row, value.root_job_id);
    if (!ref) return null;
    refs.push(ref);
  }
  for (const group of [value.absent_job_ids, value.omitted_job_ids]) {
    for (const item of group) {
      if (typeof item !== "string" || !IDENTIFIER.test(item)) return null;
    }
  }
  // Already sorted, strictly increasing per group (the owner emits sorted
  // partitions; a consumer never re-sorts).
  for (let i = 1; i < refs.length; i++)
    if (!(refs[i - 1].job_id < refs[i].job_id)) return null;
  for (const group of [value.absent_job_ids, value.omitted_job_ids])
    for (let i = 1; i < group.length; i++)
      if (!(group[i - 1] < group[i])) return null;
  const ids = [
    ...refs.map((ref) => ref.job_id),
    ...(value.absent_job_ids as string[]),
    ...(value.omitted_job_ids as string[]),
  ];
  if (ids.length > MAX_INCLUDED_SLOTS) return null;
  if (new Set(ids).size !== ids.length) return null;
  return value as unknown as ResultReferenceIndex;
}

function decodeReferencesSourceObservation(
  value: unknown,
  expected: ResultReferencesSelection,
  availability: "AVAILABLE" | "UNAVAILABLE",
  reasons: string[],
): ResultReferencesSourceObservation | null {
  if (
    !record(value) ||
    !exact(value, ["schema", "state", "selection", "control_room", "runtime"]) ||
    value.schema !== SOURCE_OBSERVATION_SCHEMA ||
    !oneOf(value.state, OBSERVATION_STATES)
  )
    return null;
  const sel = value.selection;
  if (
    !record(sel) ||
    !exact(sel, ["work_ref", "root_job_id"]) ||
    sel.work_ref !== expected.workRef ||
    sel.root_job_id !== expected.rootJobId
  )
    return null;
  const cr = value.control_room;
  const rt = value.runtime;
  if (availability === "AVAILABLE") {
    if (value.state !== "SAME") return null;
    // The existing seven-key control-room pair receipt.
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
      !text(cr.instance_before, 64) ||
      !text(cr.instance_after, 64) ||
      !int(cr.publication_before, 1) ||
      !int(cr.publication_after, 1) ||
      cr.instance_before !== cr.instance_after ||
      cr.publication_before !== cr.publication_after ||
      !hash(cr.document_digest) ||
      !hash(cr.source_validity_digest) ||
      !hash(cr.cache_currentness_digest)
    )
      return null;
    // The existing five-key runtime read observation, SAME and settled.
    if (
      !record(rt) ||
      !exact(rt, ["schema", "state", "source_identity", "before", "after"]) ||
      rt.schema !== RUNTIME_OBSERVATION_SCHEMA ||
      rt.state !== "SAME" ||
      typeof rt.source_identity !== "string" ||
      !HEX32.test(rt.source_identity) ||
      !int(rt.before, 0) ||
      !int(rt.after, 0) ||
      rt.before !== rt.after
    )
      return null;
  } else {
    // An unavailable read never established an observation (UNKNOWN), except
    // SOURCE_CHANGED which observed the source moving under the reader
    // (CONFLICT). No receipt may be carried.
    if (cr !== null || rt !== null) return null;
    const expectedState = reasons[0] === "SOURCE_CHANGED" ? "CONFLICT" : "UNKNOWN";
    if (value.state !== expectedState) return null;
  }
  return value as unknown as ResultReferencesSourceObservation;
}

function decodeReferencesCatalogue(
  value: unknown,
  availability: "AVAILABLE" | "UNAVAILABLE",
): ResultReferencesCatalogue | null {
  if (!record(value) || !exact(value, ["generated_at", "freshness"])) return null;
  if (!oneOf(value.freshness, FRESHNESS_STATES)) return null;
  if (availability === "UNAVAILABLE") {
    if (value.generated_at !== null || value.freshness !== "UNKNOWN") return null;
    return value as unknown as ResultReferencesCatalogue;
  }
  // Orientation only: no mission-currentness or acceptance field exists here.
  // Timestamp and mapper freshness are independent source facts.
  if (value.generated_at !== null && !text(value.generated_at, 128)) return null;
  return value as unknown as ResultReferencesCatalogue;
}

/**
 * Decode the closed `mastermind.workspace_result_references.v1` BODY returned
 * by the existing transport. The whole canonical framed UTF-8 form
 * `{ok:true,result:BODY}` plus LF must fit within the frozen 16 KiB budget;
 * an over-budget body is refused, never truncated. Returns null for anything
 * that is not exactly the contract, including the typed unavailable shapes
 * it must match.
 */
export function decodeResultReferencesEnvelope(
  value: unknown,
  expected: ResultReferencesSelection,
): ResultReferencesDocument | null {
  try {
    if (
      new TextEncoder().encode(
        JSON.stringify({ ok: true, result: value }) + "\n",
      ).byteLength > RESULT_REFERENCES_SOCKET_ENVELOPE_BYTES
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
      "index",
      "source_observation",
      "catalogue",
    ]) ||
    value.schema !== REFERENCES_SCHEMA
  )
    return null;
  const selection = value.selection;
  if (
    !record(selection) ||
    !exact(selection, ["work_ref", "root_job_id"]) ||
    selection.work_ref !== expected.workRef ||
    selection.root_job_id !== expected.rootJobId
  )
    return null;
  if (!oneOf(value.availability, ["AVAILABLE", "UNAVAILABLE"] as const))
    return null;
  if (!Array.isArray(value.reason_codes)) return null;
  if (value.availability === "AVAILABLE") {
    if (value.reason_codes.length !== 0) return null;
  } else if (
    value.reason_codes.length !== 1 ||
    !oneOf(value.reason_codes[0], REFERENCE_REASON_CODES)
  )
    return null;

  let index: ResultReferenceIndex | null = null;
  if (value.availability === "AVAILABLE") {
    if (value.index === null) return null;
    index = decodeReferenceIndex(value.index, expected);
    if (!index) return null;
  } else if (value.index !== null) return null;

  const observation = decodeReferencesSourceObservation(
    value.source_observation,
    expected,
    value.availability,
    value.reason_codes,
  );
  if (!observation) return null;
  const catalogue = decodeReferencesCatalogue(value.catalogue, value.availability);
  if (!catalogue) return null;

  // Receipt binding: the index generation must equal the actual wrapper
  // runtime receipt exactly. This binds one list read only; it never demands
  // the same generation at a later exact-result click.
  if (index !== null) {
    const g = index.generation;
    const r = observation.runtime;
    if (
      r === null ||
      g.state !== "SAME" ||
      g.source_identity !== r.source_identity ||
      g.before !== r.before ||
      g.after !== r.after ||
      g.before === null ||
      g.before !== g.after
    )
      return null;
  }
  return value as unknown as ResultReferencesDocument;
}
