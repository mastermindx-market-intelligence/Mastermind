/**
 * Closed compound Mission/Result body. Nested Mission v3 and Workspace Result
 * documents stay with their existing decoders. This module does not acquire,
 * authorize, or invent a nested Result from a compound refusal.
 */
import {
  decodeMissionv3,
  type Missionv3Document,
  type MissionSelection,
} from "./mission";
import {
  decodeResultEnvelope,
  normalizeResultSelection,
  RESULT_SOCKET_ENVELOPE_BYTES,
  type ResultEnvelopeDigestShape,
  type ResultSelection,
} from "./result";

export const MISSION_RESULT_SCHEMA = "mastermind.workspace_mission_result.v1";
/** Streamed compound HTTP body and the canonical outer socket envelope plus LF. */
export const MISSION_RESULT_HTTP_BODY_BYTES = 2_000_000;
export const MISSION_RESULT_SOCKET_ENVELOPE_BYTES = 2_000_000;
export const COMPOUND_REFUSAL_REASONS = [
  "SOURCE_UNAVAILABLE",
  "SOURCE_CHANGED",
  "OVER_BUDGET",
  "RESPONSE_OVER_BUDGET",
] as const;
export type CompoundRefusalReason = (typeof COMPOUND_REFUSAL_REASONS)[number];

const BODY_KEYS = [
  "schema",
  "selection",
  "availability",
  "reason_codes",
  "mission",
  "role_result",
] as const;
const WIRE_SELECTION_KEYS = [
  "work_ref",
  "root_job_id",
  "job_id",
  "attempt_id",
  "result_envelope_digest",
] as const;

export interface MissionResultAvailable {
  schema: typeof MISSION_RESULT_SCHEMA;
  availability: "AVAILABLE";
  selection: ResultSelection;
  reasonCodes: readonly [];
  mission: Missionv3Document;
  roleResult: ResultEnvelopeDigestShape;
}
export interface MissionResultUnavailable {
  schema: typeof MISSION_RESULT_SCHEMA;
  availability: "UNAVAILABLE";
  selection: ResultSelection;
  reasonCodes: readonly CompoundRefusalReason[];
  mission: null;
  roleResult: null;
}
export type MissionResultDocument = MissionResultAvailable | MissionResultUnavailable;
export type MissionResultDecode =
  | { ok: true; document: MissionResultDocument }
  | { ok: false; reason: "RECEIVED_OVER_BUDGET" | "RESPONSE_OVER_BUDGET" | "INVALID" };

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));

function canonicalJson(value: unknown): string | null {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : null;
  if (Array.isArray(value)) {
    const parts: string[] = [];
    for (const item of value) {
      const encoded = canonicalJson(item);
      if (encoded === null) return null;
      parts.push(encoded);
    }
    return `[${parts.join(",")}]`;
  }
  if (!record(value)) return null;
  const parts: string[] = [];
  for (const key of Object.keys(value).sort()) {
    const encoded = canonicalJson(value[key]);
    if (encoded === null) return null;
    parts.push(`${JSON.stringify(key)}:${encoded}`);
  }
  return `{${parts.join(",")}}`;
}

/** Canonical `{ok:true,result:BODY}` UTF-8 length. The caller adds the socket LF. */
export function canonicalSocketEnvelopeBytes(body: unknown): number | null {
  const encoded = canonicalJson({ ok: true, result: body });
  if (encoded === null) return null;
  return new TextEncoder().encode(encoded).byteLength;
}

function selectionFromWire(value: unknown): ResultSelection | null {
  if (!record(value) || !exact(value, WIRE_SELECTION_KEYS)) return null;
  return normalizeResultSelection({
    workRef: value.work_ref,
    rootJobId: value.root_job_id,
    jobId: value.job_id,
    attemptId: value.attempt_id,
    resultEnvelopeDigest: value.result_envelope_digest,
  });
}

function sameSelection(expected: ResultSelection, actual: ResultSelection): boolean {
  return expected.workRef === actual.workRef
    && expected.rootJobId === actual.rootJobId
    && expected.jobId === actual.jobId
    && expected.attemptId === actual.attemptId
    && expected.resultEnvelopeDigest === actual.resultEnvelopeDigest;
}

function refusalReasons(value: unknown): readonly CompoundRefusalReason[] | null {
  if (!Array.isArray(value) || value.length === 0 || value.length > COMPOUND_REFUSAL_REASONS.length)
    return null;
  const seen = new Set<string>();
  const reasons: CompoundRefusalReason[] = [];
  for (const item of value) {
    if (typeof item !== "string" || seen.has(item) || !COMPOUND_REFUSAL_REASONS.includes(item as CompoundRefusalReason))
      return null;
    seen.add(item);
    reasons.push(item as CompoundRefusalReason);
  }
  return reasons;
}

function missionSelection(selection: ResultSelection): MissionSelection {
  return { workRef: selection.workRef, rootJobId: selection.rootJobId };
}

/**
 * Decode one compound BODY. Received-byte accounting is `decodeMissionResultBytes`;
 * reserializing this object never replaces that ceiling. The nested Result
 * ceiling remains the existing decoder's 16384-byte socket envelope plus LF.
 */
export function decodeMissionResult(value: unknown, expected: ResultSelection): MissionResultDecode {
  if (!normalizeResultSelection(expected)) return { ok: false, reason: "INVALID" };
  const envelope = canonicalSocketEnvelopeBytes(value);
  if (envelope === null) return { ok: false, reason: "INVALID" };
  if (envelope + 1 > MISSION_RESULT_SOCKET_ENVELOPE_BYTES)
    return { ok: false, reason: "RESPONSE_OVER_BUDGET" };
  if (!record(value) || !exact(value, BODY_KEYS) || value.schema !== MISSION_RESULT_SCHEMA)
    return { ok: false, reason: "INVALID" };
  const selection = selectionFromWire(value.selection);
  if (!selection || !sameSelection(expected, selection)) return { ok: false, reason: "INVALID" };
  if (value.availability === "AVAILABLE") {
    if (!Array.isArray(value.reason_codes) || value.reason_codes.length !== 0)
      return { ok: false, reason: "INVALID" };
    if (!record(value.mission) || !record(value.role_result)) return { ok: false, reason: "INVALID" };
    // The existing Result decoder owns the nested 16384 socket-envelope ceiling.
    const roleResult = decodeResultEnvelope(value.role_result, selection);
    if (!roleResult || roleResult.availability === "UNAVAILABLE") return { ok: false, reason: "INVALID" };
    const nested = canonicalSocketEnvelopeBytes(value.role_result);
    if (nested === null || nested + 1 > RESULT_SOCKET_ENVELOPE_BYTES)
      return { ok: false, reason: "INVALID" };
    const mission = decodeMissionv3(value.mission, missionSelection(selection));
    if (!mission) return { ok: false, reason: "INVALID" };
    return {
      ok: true,
      document: {
        schema: MISSION_RESULT_SCHEMA,
        availability: "AVAILABLE",
        selection,
        reasonCodes: [],
        mission,
        roleResult,
      },
    };
  }
  if (value.availability !== "UNAVAILABLE") return { ok: false, reason: "INVALID" };
  const reasonCodes = refusalReasons(value.reason_codes);
  if (!reasonCodes || value.mission !== null || value.role_result !== null)
    return { ok: false, reason: "INVALID" };
  return {
    ok: true,
    document: {
      schema: MISSION_RESULT_SCHEMA,
      availability: "UNAVAILABLE",
      selection,
      reasonCodes,
      mission: null,
      roleResult: null,
    },
  };
}

/** Count the bytes actually received, then decode. A smaller reserialization cannot admit them. */
export function decodeMissionResultBytes(bytes: Uint8Array, expected: ResultSelection): MissionResultDecode {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength > MISSION_RESULT_HTTP_BODY_BYTES)
    return { ok: false, reason: "RECEIVED_OVER_BUDGET" };
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return { ok: false, reason: "INVALID" };
  }
  try {
    return decodeMissionResult(JSON.parse(text) as unknown, expected);
  } catch {
    return { ok: false, reason: "INVALID" };
  }
}
