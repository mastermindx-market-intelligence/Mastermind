/**
 * Bounded saved-conversation search composition.
 *
 * This leaf composes READS ONLY over two existing, already authorized owner
 * surfaces: the Session Bridge saved-reference reader (`readReferences`) and
 * the executive session command port's qualified-answer reader
 * (`readAnswer`). It never authenticates anything itself: the signed Session
 * Bridge owner stays the authority for references, and the existing
 * cryptographic answer validator inside the port stays the only qualifier of
 * a reply body. This module neither replaces nor bypasses that validator and
 * never calls a raw read.
 *
 * Scope boundaries, deliberately enforced in code:
 * - One explicit query performs exactly ONE pageSize=4 saved-reference page
 *   read and at most FOUR sequential qualified-answer body reads. There is
 *   no hidden full-history loop, no polling, no bulk index build.
 * - No current-window conversation text exists in this module: only answers
 *   reached through saved references of the requested project (rootless
 *   within that project is intentional).
 * - No writes: no operation send/retry/consume, no pending-pointer mutation,
 *   no host/backend/auth/store/UI reach-through, no network, no filesystem.
 * - Search is a literal Unicode case-insensitive substring match over the
 *   qualified answer text. Results carry an exact bounded excerpt plus the
 *   SHA-256 (WebCrypto) of the exact full source text. No generated summary,
 *   no full answer text, no nextStep, no private envelope fields.
 *
 * Failure policy is fail-closed. Malformed owner responses, watermark
 * movement, work_ref drift, owner/context/method replacement, stale auth
 * generations, aborts and missing owner context discard all content and
 * return an UNAVAILABLE result with empty items and null cursor/high water.
 * Owner exception text is never surfaced. Per-answer body reads stay inside
 * the existing qualified text limit (16384 UTF-8 bytes), the composed result
 * stays inside a 64KiB ceiling, and an oversize or malformed answer counts
 * as one unavailable row instead of an owner denial.
 *
 * Integration, UI and actual host wiring of this seam belong to the parent
 * workstream; this file only ships the bounded composer and its decoder.
 */

import type { OperationPointer } from "../orchestration/operation-controller";
import type { QualifiedSessionAnswerRead } from "../orchestration/executive-session-command-port";

/** Canonical bounded project reference: `WS:` plus 2..64 work characters. */
const WORK_REF_PATTERN = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const READ_REF_PATTERN = /^session-reply-[0-9a-f]{64}$/;
const OPERATION_KEY_PATTERN = /^session-continue-[0-9a-f]{64}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
/** The closed canonical target-prefix union: a mixed page stays readable. */
const TARGET_REF_PATTERN = /^(?:fabric_attempt|hermes_secretary|hermes_meta):[0-9a-f]{64}$/;
const CURSOR_PATTERN = /^[A-Za-z0-9_=-]{1,2048}$/;
const ROOT_JOB_PATTERN = /^JOB-[0-9]{1,9}$/;
/** Real-calendar UTC stamp: ISO 8601 extended, offset strictly Z or +00:00. */
const UTC_STAMP_PATTERN =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:Z|\+00:00)$/;

const ENVELOPE_KEYS: readonly string[] = [
  "schema",
  "operation",
  "ok",
  "effect",
  "operation_key",
  "error",
  "data",
];
const DATA_KEYS: readonly string[] = [
  "schema",
  "status",
  "references",
  "next_cursor",
  "high_water",
];
const ROW_KEYS: readonly string[] = [
  "read_ref",
  "operation_key",
  "request_ref",
  "request_event_id",
  "request_revision",
  "requested_at",
  "work_ref",
  "root_job_id",
  "target_ref",
  "reference_only",
];

const ENVELOPE_SCHEMA = "mastermind.os.executive.session_result.v1";
const DATA_SCHEMA = "mastermind.session_reply_references.v1";

/** The owner page request is fixed at 4 rows; the decoder accepts at most 4. */
const MAX_REFERENCES_PER_PAGE = 4;
const PAGE_SIZE = 4 as const;
const MIN_QUERY_SCALAR_CHARS = 2;
const MAX_QUERY_SCALAR_CHARS = 128;
const MAX_REQUEST_REF_CHARS = 256;
const MAX_REQUESTED_AT_CHARS = 64;
/** Existing qualified-answer text limit for one body read. */
const MAX_ANSWER_UTF8_BYTES = 16384;
/** Exact excerpt bound: never split a grapheme or a surrogate pair. */
const MAX_EXCERPT_UTF8_BYTES = 480;
/** Composed result ceiling. */
const MAX_RESULT_UTF8_BYTES = 65536;

/** One saved-conversation reference row exactly as the owner projects it. */
export interface SavedConversationReference {
  readonly read_ref: string;
  readonly operation_key: string;
  readonly request_ref: string;
  readonly request_event_id: number;
  readonly request_revision: string;
  readonly requested_at: string;
  readonly work_ref: string;
  readonly root_job_id: string;
  readonly target_ref: string;
  readonly reference_only: true;
}

/** Decoded, frozen reference page. Shape and selection only, never auth. */
export interface SavedConversationPage {
  readonly references: readonly SavedConversationReference[];
  readonly nextCursor: string | null;
  readonly highWater: number;
}

export interface SavedConversationMatch {
  readonly reference: SavedConversationReference;
  /** Exact bounded substring of the source text around the first match. */
  readonly excerpt: string;
  /** SHA-256 (WebCrypto) of the exact full source text, 64 lowercase hex. */
  readonly sourceTextSha256: string;
}

export interface SavedConversationCoverage {
  readonly status: "COMPLETE" | "PARTIAL";
  /** Owner rows actually scanned by this one explicit query. */
  readonly scanned: number;
  /** Qualified answers whose text actually matched the query. */
  readonly matched: number;
  /** Answers unknown, refused, mismatched, missing or malformed/oversize. */
  readonly unavailable: number;
  readonly nextCursor: string | null;
  readonly highWater: number | null;
}

export type SavedConversationSearchState = "AVAILABLE" | "UNAVAILABLE";

export type SavedConversationSearchFailure =
  | "INVALID_INPUT"
  | "OWNER_UNAVAILABLE"
  | "SOURCE_CHANGED"
  | "INVALID_SOURCE"
  | "OVER_BUDGET";

export interface SavedConversationSearchResult {
  readonly state: SavedConversationSearchState;
  readonly reason: SavedConversationSearchFailure | null;
  readonly workRef: string;
  readonly query: string;
  readonly scope: "SAVED_CONVERSATIONS_IN_PROJECT";
  readonly items: readonly SavedConversationMatch[];
  readonly coverage: SavedConversationCoverage;
}

export interface SavedConversationSearchRequest {
  readonly workRef: string;
  readonly query: string;
  readonly cursor?: string;
  readonly expectedHighWater?: number;
  readonly signal: AbortSignal;
}

/**
 * The actual owner ports this composer consumes. Both reads are existing,
 * separately authorized owner methods; this interface only names them.
 */
export interface SavedConversationSearchOwner {
  context(): { principalScope: string; generation: string } | null;
  authGeneration(): number;
  readReferences(request: {
    workRef: string;
    pageSize: 4;
    cursor?: string;
    signal: AbortSignal;
  }): Promise<unknown>;
  readAnswer(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<QualifiedSessionAnswerRead>;
}

/* ------------------------------------------------------------------ *
 * Scalar and plain-data validation helpers.
 * ------------------------------------------------------------------ */

function fullMatch(pattern: RegExp, value: string): boolean {
  return pattern.exec(value)?.[0] === value;
}

function isWorkRef(value: unknown): value is string {
  return typeof value === "string" && fullMatch(WORK_REF_PATTERN, value);
}

function isCursor(value: unknown): value is string {
  return typeof value === "string" && fullMatch(CURSOR_PATTERN, value);
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isAbortSignalLike(value: unknown): value is AbortSignal {
  try {
    return value instanceof AbortSignal && typeof value.aborted === "boolean" &&
      typeof value.addEventListener === "function";
  } catch { return false; }
}

/** UTF-8 byte length of well-formed scalar text (lone surrogates: defensive). */
function utf8ByteLength(value: string): number {
  let bytes = 0;
  let index = 0;
  while (index < value.length) {
    const code = value.charCodeAt(index);
    if (code < 0x80) {
      bytes += 1;
      index += 1;
    } else if (code < 0x800) {
      bytes += 2;
      index += 1;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      const low = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (low >= 0xdc00 && low <= 0xdfff) {
        bytes += 4;
        index += 2;
      } else {
        bytes += 3;
        index += 1;
      }
    } else {
      bytes += 3;
      index += 1;
    }
  }
  return bytes;
}

function hasLoneSurrogate(value: string): boolean {
  let index = 0;
  while (index < value.length) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const low = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (low >= 0xdc00 && low <= 0xdfff) {
        index += 2;
        continue;
      }
      return true;
    }
    if (code >= 0xdc00 && code <= 0xdfff) return true;
    index += 1;
  }
  return false;
}

/** Exact UTF-8 encoding of well-formed scalar text, without TextEncoder. */
function utf8Encode(value: string): Uint8Array {
  const out = new Uint8Array(value.length * 4);
  let at = 0;
  let index = 0;
  while (index < value.length) {
    const code = value.charCodeAt(index);
    if (code < 0x80) {
      out[at] = code;
      at += 1;
      index += 1;
    } else if (code < 0x800) {
      out[at] = 0xc0 | (code >> 6);
      out[at + 1] = 0x80 | (code & 0x3f);
      at += 2;
      index += 1;
    } else if (code >= 0xd800 && code <= 0xdbff) {
      const low = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (low >= 0xdc00 && low <= 0xdfff) {
        const point = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00);
        out[at] = 0xf0 | (point >> 18);
        out[at + 1] = 0x80 | ((point >> 12) & 0x3f);
        out[at + 2] = 0x80 | ((point >> 6) & 0x3f);
        out[at + 3] = 0x80 | (point & 0x3f);
        at += 4;
        index += 2;
      } else {
        out[at] = 0xef;
        out[at + 1] = 0xbf;
        out[at + 2] = 0xbd;
        at += 3;
        index += 1;
      }
    } else {
      out[at] = 0xe0 | (code >> 12);
      out[at + 1] = 0x80 | ((code >> 6) & 0x3f);
      out[at + 2] = 0x80 | (code & 0x3f);
      at += 3;
      index += 1;
    }
  }
  return out.subarray(0, at);
}

/** Query must be 2..128 Unicode scalar chars with no control characters. */
function isBoundedQuery(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0) return false;
  let scalarChars = 0;
  let index = 0;
  while (index < value.length) {
    const code = value.charCodeAt(index);
    let width = 1;
    if (code >= 0xd800 && code <= 0xdbff) {
      const low = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (low >= 0xdc00 && low <= 0xdfff) {
        width = 2;
        if (isForbiddenQueryCode(code) || isForbiddenQueryCode(low)) return false;
      } else {
        return false; // lone high surrogate
      }
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false; // orphan low surrogate
    }
    scalarChars += 1;
    if (scalarChars > MAX_QUERY_SCALAR_CHARS) return false;
    if (width === 1 && isForbiddenQueryCode(code)) return false;
    index += width;
  }
  return scalarChars >= MIN_QUERY_SCALAR_CHARS;
}

/** C0, DEL, C1, BOM and Unicode noncharacters are rejected in queries. */
function isForbiddenQueryCode(code: number): boolean {
  if (code <= 0x1f) return true;
  if (code === 0x7f) return true;
  if (code >= 0x80 && code <= 0x9f) return true;
  if (code === 0xfeff) return true;
  if (code >= 0xfdd0 && code <= 0xfdef) return true;
  return (code & 0xfffe) === 0xfffe;
}

/** Real-calendar UTC ISO 8601 stamp with offset strictly Z or +00:00. */
function isRealUtcStamp(value: string): boolean {
  if (value.length > MAX_REQUESTED_AT_CHARS) return false;
  const match = UTC_STAMP_PATTERN.exec(value);
  if (match === null) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (month < 1 || month > 12) return false;
  const leapYear = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const monthDays = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const monthLength = monthDays[month - 1];
  if (monthLength === undefined || day < 1 || day > monthLength) return false;
  return hour <= 23 && minute <= 59 && second <= 59;
}

/* ------------------------------------------------------------------ *
 * Plain own-data object checks. Raw transport frames are untrusted: no
 * accessor (getter/setter) may exist on any own property, no symbols, no
 * extra keys, no exotic prototype. Validators inspect descriptors BEFORE
 * any field read, so no raw getter and no toJSON is ever invoked during
 * validation. Depth is fixed and flat, so validated rows cannot cycle.
 * ------------------------------------------------------------------ */

function plainOwnData(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  if (Object.getPrototypeOf(value) !== Object.prototype) return null;
  if (Object.getOwnPropertySymbols(value).length !== 0) return null;
  const names = Object.getOwnPropertyNames(value);
  for (let i = 0; i < names.length; i += 1) {
    const name = names[i];
    if (name === undefined) return null;
    const descriptor = Object.getOwnPropertyDescriptor(value, name);
    if (descriptor === undefined) return null;
    if (descriptor.get !== undefined || descriptor.set !== undefined) return null;
    if (!("value" in descriptor)) return null;
  }
  return value as Record<string, unknown>;
}

function plainArray(value: unknown): unknown[] | null {
  if (!Array.isArray(value)) return null;
  if (Object.getPrototypeOf(value) !== Array.prototype) return null;
  if (Object.getOwnPropertySymbols(value).length !== 0) return null;
  const names = Object.getOwnPropertyNames(value);
  for (let i = 0; i < names.length; i += 1) {
    const name = names[i];
    if (name === undefined) return null;
    if (name === "length") continue;
    const index = Number(name);
    if (
      !Number.isSafeInteger(index) ||
      index < 0 ||
      index >= value.length ||
      String(index) !== name
    ) {
      return null;
    }
  }
  return value;
}

function ownKeysExactly(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== keys.length) return false;
  for (let i = 0; i < keys.length; i += 1) {
    const key = keys[i];
    if (key === undefined) return false;
    if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  }
  return true;
}

/* ------------------------------------------------------------------ *
 * Page decoding: shape and selection only, never authentication.
 * ------------------------------------------------------------------ */

type PageFailure = "MALFORMED" | "WORK_REF_CHANGED" | "HIGH_WATER_CHANGED";

type DecodedPage =
  | { readonly page: SavedConversationPage }
  | { readonly failure: PageFailure };

const MALFORMED = Object.freeze({ failure: "MALFORMED" as const });

interface SeenIdentity {
  readonly readRefs: Set<string>;
  readonly operations: Set<string>;
  readonly events: Set<number>;
}

type DecodedRow =
  | { readonly reference: SavedConversationReference }
  | { readonly failure: PageFailure };

function decodeRow(
  value: unknown,
  expectedWorkRef: string,
  highWater: number,
  seen: SeenIdentity,
): DecodedRow {
  const row = plainOwnData(value);
  if (row === null || !ownKeysExactly(row, ROW_KEYS)) return MALFORMED;
  const readRef = row.read_ref;
  if (typeof readRef !== "string" || !fullMatch(READ_REF_PATTERN, readRef)) return MALFORMED;
  const operationKey = row.operation_key;
  if (typeof operationKey !== "string" || !fullMatch(OPERATION_KEY_PATTERN, operationKey)) {
    return MALFORMED;
  }
  const requestRef = row.request_ref;
  if (
    typeof requestRef !== "string" ||
    requestRef.length === 0 ||
    requestRef.length > MAX_REQUEST_REF_CHARS || hasLoneSurrogate(requestRef) ||
    /[\u0000-\u001f\u007f-\u009f]/.test(requestRef)
  ) {
    return MALFORMED;
  }
  const eventId = row.request_event_id;
  if (typeof eventId !== "number" || !Number.isSafeInteger(eventId) || eventId < 1) {
    return MALFORMED;
  }
  if (eventId > highWater) return MALFORMED;
  // Actual owner revision form: the Runtime row carries a 64 lowercase hex
  // event digest (verified against the supplied Runtime producer source).
  const revision = row.request_revision;
  if (typeof revision !== "string" || !fullMatch(SHA256_PATTERN, revision)) return MALFORMED;
  const requestedAt = row.requested_at;
  if (typeof requestedAt !== "string" || !isRealUtcStamp(requestedAt)) return MALFORMED;
  const workRef = row.work_ref;
  if (typeof workRef !== "string") return MALFORMED;
  if (workRef !== expectedWorkRef) return { failure: "WORK_REF_CHANGED" };
  // Rootless within the requested project is intentional: root_job_id is
  // format-checked but never compared to a requested root.
  const rootJobId = row.root_job_id;
  if (typeof rootJobId !== "string" || !fullMatch(ROOT_JOB_PATTERN, rootJobId)) return MALFORMED;
  const targetRef = row.target_ref;
  if (typeof targetRef !== "string" || !fullMatch(TARGET_REF_PATTERN, targetRef)) return MALFORMED;
  if (row.reference_only !== true) return MALFORMED;
  if (
    seen.readRefs.has(readRef) ||
    seen.operations.has(operationKey) ||
    seen.events.has(eventId)
  ) {
    return MALFORMED;
  }
  seen.readRefs.add(readRef);
  seen.operations.add(operationKey);
  seen.events.add(eventId);
  // Copy the exact closed projection and freeze it before any await, so a
  // transport retaining and mutating its raw JSON frame afterwards cannot
  // retarget a later read.
  const reference: SavedConversationReference = Object.freeze({
    read_ref: readRef,
    operation_key: operationKey,
    request_ref: requestRef,
    request_event_id: eventId,
    request_revision: revision,
    requested_at: requestedAt,
    work_ref: workRef,
    root_job_id: rootJobId,
    target_ref: targetRef,
    reference_only: true as const,
  });
  return { reference };
}

/**
 * Decode one saved-reference page. Returns null for any malformed envelope,
 * any row whose work_ref differs from the requested project, any watermark
 * mismatch, duplicate identity, broken status/cursor pairing, or a page with
 * more than four rows. There is no partial private prefix on a null return.
 * The 64KiB UTF-8 envelope body bound stays with the owner transport seam
 * that parses the frame; this decoder validates the parsed projection only.
 */
function decodePageDetailed(
  raw: unknown,
  expectedWorkRef: string,
  expectedHighWater?: number,
): DecodedPage {
  if (!isWorkRef(expectedWorkRef)) return MALFORMED;
  if (
    expectedHighWater !== undefined &&
    !isNonNegativeSafeInteger(expectedHighWater)
  ) {
    return MALFORMED;
  }
  try {
    const envelope = plainOwnData(raw);
    if (envelope === null || !ownKeysExactly(envelope, ENVELOPE_KEYS)) return MALFORMED;
    if (
      envelope.schema !== ENVELOPE_SCHEMA ||
      envelope.operation !== "references" ||
      envelope.ok !== true ||
      envelope.effect !== "NONE" ||
      envelope.operation_key !== null ||
      envelope.error !== null
    ) {
      return MALFORMED;
    }
    const data = plainOwnData(envelope.data);
    if (data === null || !ownKeysExactly(data, DATA_KEYS)) return MALFORMED;
    if (data.schema !== DATA_SCHEMA) return MALFORMED;
    const status = data.status;
    if (status !== "COMPLETE" && status !== "PARTIAL") return MALFORMED;
    const highWaterValue = data.high_water;
    if (
      typeof highWaterValue !== "number" ||
      !Number.isSafeInteger(highWaterValue) ||
      highWaterValue < 0
    ) {
      return MALFORMED;
    }
    const nextCursorValue = data.next_cursor;
    let nextCursor: string | null;
    if (nextCursorValue === null) {
      if (status === "PARTIAL") return MALFORMED; // PARTIAL iff cursor non-null
      nextCursor = null;
    } else if (typeof nextCursorValue === "string" && fullMatch(CURSOR_PATTERN, nextCursorValue)) {
      if (status === "COMPLETE") return MALFORMED;
      nextCursor = nextCursorValue;
    } else {
      return MALFORMED;
    }
    const rows = plainArray(data.references);
    if (rows === null || rows.length > MAX_REFERENCES_PER_PAGE) return MALFORMED;
    const seen: SeenIdentity = {
      readRefs: new Set<string>(),
      operations: new Set<string>(),
      events: new Set<number>(),
    };
    const references: SavedConversationReference[] = [];
    for (let i = 0; i < rows.length; i += 1) {
      const decodedRow = decodeRow(rows[i], expectedWorkRef, highWaterValue, seen);
      if (!("reference" in decodedRow)) return decodedRow;
      references.push(decodedRow.reference);
    }
    if (
      expectedHighWater !== undefined &&
      highWaterValue !== expectedHighWater
    ) {
      return { failure: "HIGH_WATER_CHANGED" };
    }
    // All values below are detached validated scalars. Bound the actual
    // decoded source content without ever serializing the caller's getters.
    if (utf8ByteLength(JSON.stringify({schema: ENVELOPE_SCHEMA, operation: "references", ok: true,
      effect: "NONE", operation_key: null, error: null, data: {schema: DATA_SCHEMA,
        status, references, next_cursor: nextCursor, high_water: highWaterValue}})) > 65536) return MALFORMED;
    return {
      page: Object.freeze({
        references: Object.freeze(references),
        nextCursor,
        highWater: highWaterValue,
      }),
    };
  } catch {
    return MALFORMED;
  }
}

/** Strict public decoder: any failure collapses to null, never partial data. */
export function decodeSavedConversationPage(
  raw: unknown,
  expectedWorkRef: string,
  expectedHighWater?: number,
): SavedConversationPage | null {
  const decoded = decodePageDetailed(raw, expectedWorkRef, expectedHighWater);
  return "page" in decoded ? decoded.page : null;
}

/* ------------------------------------------------------------------ *
 * Literal matching and bounded excerpt extraction.
 * ------------------------------------------------------------------ */

/** Escape the query so it can only ever match literally, never as a regex. */
function escapeLiteral(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function findLiteralMatch(
  text: string,
  query: string,
): { readonly start: number; readonly end: number } | null {
  let pattern: RegExp;
  try {
    pattern = new RegExp(escapeLiteral(query), "iu");
  } catch {
    return null;
  }
  const match = pattern.exec(text);
  if (match === null) return null;
  const matched = match[0];
  if (matched === undefined || matched.length === 0) return null;
  return { start: match.index, end: match.index + matched.length };
}

interface TextUnit {
  readonly text: string;
  /** Code-unit offset of this unit inside the source text. */
  readonly start: number;
  readonly bytes: number;
}

interface SegmenterConstructor {
  new (
    locale?: string,
    options?: { granularity?: string },
  ): { segment(text: string): Iterable<{ segment: string; index: number }> };
}

/** Grapheme segmentation when Intl.Segmenter exists, else null. */
function segmentGraphemes(text: string): TextUnit[] | null {
  const holder = globalThis as unknown as {
    Intl?: { Segmenter?: SegmenterConstructor };
  };
  const ctor = holder.Intl?.Segmenter;
  if (typeof ctor !== "function") return null;
  try {
    const segmenter = new ctor("und", { granularity: "grapheme" });
    const parts = Array.from(segmenter.segment(text));
    const units: TextUnit[] = [];
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i];
      if (part === undefined || part.segment.length === 0) return null;
      units.push({
        text: text.slice(part.index, part.index + part.segment.length),
        start: part.index,
        bytes: utf8ByteLength(part.segment),
      });
    }
    return units.length > 0 ? units : null;
  } catch {
    return null;
  }
}

/** Fallback units: single Unicode code points, surrogate pairs kept intact. */
function codePointUnits(text: string): TextUnit[] {
  const units: TextUnit[] = [];
  let index = 0;
  while (index < text.length) {
    const code = text.charCodeAt(index);
    let width = 1;
    if (code >= 0xd800 && code <= 0xdbff && index + 1 < text.length) {
      const low = text.charCodeAt(index + 1);
      if (low >= 0xdc00 && low <= 0xdfff) width = 2;
    }
    const part = text.slice(index, index + width);
    units.push({ text: part, start: index, bytes: utf8ByteLength(part) });
    index += width;
  }
  return units;
}

function excerptUnits(text: string): TextUnit[] {
  return segmentGraphemes(text) ?? codePointUnits(text);
}

function joinUnits(units: TextUnit[], lo: number, hi: number): string {
  let out = "";
  for (let i = lo; i <= hi; i += 1) {
    const unit = units[i];
    if (unit === undefined) break;
    out += unit.text;
  }
  return out;
}

/**
 * Exact bounded substring around the first match: at most 480 UTF-8 bytes,
 * never splitting a grapheme (or, without Intl.Segmenter, a code point).
 * Emits no ellipsis or any other generated decoration, so the excerpt is
 * always a literal substring of the source text.
 */
function buildExcerpt(text: string, matchStart: number, matchEnd: number): string {
  const units = excerptUnits(text);
  if (units.length === 0) return "";
  let first = 0;
  while (first + 1 < units.length && (units[first + 1]?.start ?? Infinity) <= matchStart) {
    first += 1;
  }
  let last = first;
  while (last + 1 < units.length && (units[last + 1]?.start ?? Infinity) < matchEnd) {
    last += 1;
  }
  let lo = first;
  let hi = first - 1;
  let bytes = 0;
  for (let i = first; i <= last; i += 1) {
    const unit = units[i];
    if (unit === undefined) break;
    if (bytes + unit.bytes > MAX_EXCERPT_UTF8_BYTES) break;
    hi = i;
    bytes += unit.bytes;
  }
  if (hi < last) {
    // The matched span alone exceeds the budget: emit its bounded prefix.
    return joinUnits(units, lo, hi);
  }
  let preferBefore = true;
  for (;;) {
    const before = lo > 0 ? units[lo - 1] : undefined;
    const after = hi + 1 < units.length ? units[hi + 1] : undefined;
    const canBefore = before !== undefined && bytes + before.bytes <= MAX_EXCERPT_UTF8_BYTES;
    const canAfter = after !== undefined && bytes + after.bytes <= MAX_EXCERPT_UTF8_BYTES;
    if (!canBefore && !canAfter) break;
    if (preferBefore && canBefore && before !== undefined) {
      lo -= 1;
      bytes += before.bytes;
    } else if (canAfter && after !== undefined) {
      hi += 1;
      bytes += after.bytes;
    } else if (canBefore && before !== undefined) {
      lo -= 1;
      bytes += before.bytes;
    } else {
      break;
    }
    preferBefore = !preferBefore;
  }
  return joinUnits(units, lo, hi);
}

/* ------------------------------------------------------------------ *
 * Digest binding over WebCrypto.
 * ------------------------------------------------------------------ */

interface DigestSubtle {
  digest(algorithm: string, data: Uint8Array): Promise<ArrayBuffer | Uint8Array>;
}

function webCryptoSubtle(): DigestSubtle | null {
  const holder = globalThis as unknown as {
    crypto?: { subtle?: DigestSubtle };
  };
  const subtle = holder.crypto?.subtle;
  return typeof subtle === "object" && subtle !== null && typeof subtle.digest === "function"
    ? subtle
    : null;
}

async function sha256Hex(text: string): Promise<string | null> {
  const subtle = webCryptoSubtle();
  if (subtle === null) return null;
  let digest: ArrayBuffer | Uint8Array;
  try {
    digest = await subtle.digest("SHA-256", utf8Encode(text));
  } catch {
    return null;
  }
  const bytes = digest instanceof Uint8Array ? digest : new Uint8Array(digest);
  let hex = "";
  for (let i = 0; i < bytes.length; i += 1) {
    const byte = bytes[i];
    hex += (byte === undefined ? 0 : byte).toString(16).padStart(2, "0");
  }
  return fullMatch(SHA256_PATTERN, hex) ? hex : null;
}

/* ------------------------------------------------------------------ *
 * Owner capture and lifetime fencing.
 *
 * This is lifetime fencing only and never mints new permission: the owner
 * keeps its existing signed authority and the port keeps its existing
 * cryptographic answer validation. Actual principalScope/generation values
 * and actual bound method identities are captured before the first read and
 * re-read and compared exactly after every await, before any next read or
 * any return.
 * ------------------------------------------------------------------ */

interface OwnerContext {
  readonly principalScope: string;
  readonly generation: string;
}

interface OwnerSnapshot {
  readonly principalScope: string;
  readonly generation: string;
  readonly authGeneration: number;
  readonly context: () => OwnerContext | null;
  readonly readAuthGeneration: () => number;
  readonly readReferences: SavedConversationSearchOwner["readReferences"];
  readonly readAnswer: SavedConversationSearchOwner["readAnswer"];
}

function isSearchOwner(value: unknown): value is SavedConversationSearchOwner {
  const row = plainOwnData(value);
  return row !== null && ["context", "authGeneration", "readReferences", "readAnswer"]
    .every(key => typeof row[key] === "function");
}

function isOwnerContext(value: unknown): value is OwnerContext {
  const row = plainOwnData(value);
  return row !== null && ownKeysExactly(row, ["principalScope", "generation"]) &&
    typeof row.principalScope === "string" && row.principalScope.length > 0 &&
    typeof row.generation === "string" && row.generation.length > 0;
}

function captureOwnerSnapshot(owner: SavedConversationSearchOwner): OwnerSnapshot | null {
  let context: unknown;
  let authGeneration: unknown;
  try {
    context = owner.context();
    authGeneration = owner.authGeneration();
  } catch {
    return null;
  }
  if (!isOwnerContext(context)) return null;
  if (typeof authGeneration !== "number" || !Number.isFinite(authGeneration)) return null;
  return {
    principalScope: context.principalScope,
    generation: context.generation,
    authGeneration,
    context: owner.context,
    readAuthGeneration: owner.authGeneration,
    readReferences: owner.readReferences,
    readAnswer: owner.readAnswer,
  };
}

function ownerFence(
  owner: SavedConversationSearchOwner,
  snapshot: OwnerSnapshot,
  signal: AbortSignal,
): boolean {
  if (signal.aborted) return false;
  try {
    if (
      owner.context !== snapshot.context ||
      owner.authGeneration !== snapshot.readAuthGeneration ||
      owner.readReferences !== snapshot.readReferences ||
      owner.readAnswer !== snapshot.readAnswer
    ) {
      return false;
    }
    const context = snapshot.context.call(owner);
    if (!isOwnerContext(context)) return false;
    if (
      context.principalScope !== snapshot.principalScope ||
      context.generation !== snapshot.generation
    ) {
      return false;
    }
    return snapshot.readAuthGeneration.call(owner) === snapshot.authGeneration;
  } catch {
    return false;
  }
}

/**
 * Accept a qualified answer only when the existing port's receipt is accepted
 * and binds exactly the original row identity, the answer exists, was never
 * consumed by a parent, and its read ref matches the saved reference. The
 * port's cryptographic validator remains the authority; this is selection
 * over its already-qualified output, plus bounded-length scalar text checks.
 */
function qualifiedAnswerText(
  reference: SavedConversationReference,
  read: unknown,
): string | null {
  try {
  if (typeof read !== "object" || read === null) return null;
  const holder = plainOwnData(read);
  if (!holder) return null;
  const receipt = holder.receipt;
  const answer = holder.answer;
  if (typeof receipt !== "object" || receipt === null) return null;
  const receiptFields = plainOwnData(receipt);
  if (!receiptFields) return null;
  if (receiptFields.disposition !== "accepted") return null;
  if (receiptFields.operationKey !== reference.operation_key) return null;
  if (receiptFields.kind !== "message") return null;
  if (receiptFields.targetKey !== reference.target_ref) return null;
  if (typeof answer !== "object" || answer === null) return null;
  const answerFields = plainOwnData(answer);
  if (!answerFields) return null;
  if (answerFields.parentConsumed !== false) return null;
  if (typeof answerFields.readRef !== "string") return null;
  if (answerFields.readRef !== reference.read_ref) return null;
  const text = answerFields.text;
  if (typeof text !== "string" || text.length === 0) return null;
  if (hasLoneSurrogate(text)) return null;
  if (utf8ByteLength(text) > MAX_ANSWER_UTF8_BYTES) return null;
  return text;
  } catch { return null; }
}

function referenceContentBytes(reference: SavedConversationReference): number {
  return (
    utf8ByteLength(reference.read_ref) +
    utf8ByteLength(reference.operation_key) +
    utf8ByteLength(reference.request_ref) +
    utf8ByteLength(reference.request_revision) +
    utf8ByteLength(reference.requested_at) +
    utf8ByteLength(reference.work_ref) +
    utf8ByteLength(reference.root_job_id) +
    utf8ByteLength(reference.target_ref) +
    8
  );
}

function resultContentBytes(result: SavedConversationSearchResult): number {
  let total =
    utf8ByteLength(result.workRef) +
    utf8ByteLength(result.query) +
    32;
  for (let i = 0; i < result.items.length; i += 1) {
    const item = result.items[i];
    if (item === undefined) continue;
    total +=
      utf8ByteLength(item.excerpt) +
      utf8ByteLength(item.sourceTextSha256) +
      referenceContentBytes(item.reference);
  }
  return total;
}

function failedResult(
  reason: SavedConversationSearchFailure,
  workRef: string,
  query: string,
): SavedConversationSearchResult {
  return Object.freeze({
    state: "UNAVAILABLE" as const,
    reason,
    workRef,
    query,
    scope: "SAVED_CONVERSATIONS_IN_PROJECT" as const,
    items: Object.freeze([]) as readonly SavedConversationMatch[],
    coverage: Object.freeze({
      status: "PARTIAL" as const,
      scanned: 0,
      matched: 0,
      unavailable: 0,
      nextCursor: null,
      highWater: null,
    }),
  });
}

function echoScalar(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/* ------------------------------------------------------------------ *
 * The bounded search composer.
 * ------------------------------------------------------------------ */

/**
 * Run one explicit saved-conversation search.
 *
 * Budget: exactly one pageSize=4 saved-reference page read plus at most four
 * sequential qualified-answer body reads. No polling, no history scan, no
 * bulk index, no writes, and no retries beyond what the owner read itself
 * already performs.
 *
 * Fencing: actual owner principalScope/generation/authGeneration values and
 * actual bound read-method identities are captured before the first read and
 * re-read and compared exactly after every await, before any next read or
 * return. Any drift, any abort, any malformed source, any watermark or
 * work_ref movement, any non-advancing cursor, and any over-budget result
 * fails closed with empty items and no partial content prefix. Owner
 * exception text is never surfaced.
 */
export async function searchSavedConversations(
  request: SavedConversationSearchRequest,
  owner: SavedConversationSearchOwner,
): Promise<SavedConversationSearchResult> {
  const input = plainOwnData(request);
  const allowed = ["workRef", "query", "signal", "cursor", "expectedHighWater"];
  if (!input || !["workRef", "query", "signal"].every(key => Object.hasOwn(input, key)) ||
      Object.keys(input).some(key => !allowed.includes(key))) {
    return failedResult("INVALID_INPUT", "", "");
  }
  const requestFields = input as unknown as SavedConversationSearchRequest;
  if (
    !isWorkRef(requestFields.workRef) ||
    !isBoundedQuery(requestFields.query) ||
    !isAbortSignalLike(requestFields.signal) ||
    (requestFields.cursor !== undefined && !isCursor(requestFields.cursor)) ||
    (requestFields.expectedHighWater !== undefined &&
      !isNonNegativeSafeInteger(requestFields.expectedHighWater))
  ) {
    return failedResult(
      "INVALID_INPUT",
      isWorkRef(requestFields.workRef) ? requestFields.workRef : "",
      isBoundedQuery(requestFields.query) ? requestFields.query : "",
    );
  }
  // An owner that cannot serve reads at all is an unavailable owner, not a
  // caller-input problem; no read has happened either way.
  if (!isSearchOwner(owner)) {
    return failedResult(
      "OWNER_UNAVAILABLE",
      isWorkRef(requestFields.workRef) ? requestFields.workRef : "",
      isBoundedQuery(requestFields.query) ? requestFields.query : "",
    );
  }
  const workRef: string = requestFields.workRef;
  const query: string = requestFields.query;
  const cursor: string | undefined =
    requestFields.cursor === undefined ? undefined : requestFields.cursor;
  const expectedHighWater: number | undefined =
    requestFields.expectedHighWater === undefined
      ? undefined
      : requestFields.expectedHighWater;
  const signal: AbortSignal = requestFields.signal;

  // The result must bind digests through WebCrypto; without it no bound
  // match can honestly be produced, so fail closed before any read.
  if (webCryptoSubtle() === null) {
    return failedResult("OWNER_UNAVAILABLE", workRef, query);
  }
  const snapshot = captureOwnerSnapshot(owner);
  if (snapshot === null) {
    return failedResult("OWNER_UNAVAILABLE", workRef, query);
  }
  if (!ownerFence(owner, snapshot, signal)) {
    return failedResult("SOURCE_CHANGED", workRef, query);
  }

  // ONE pageSize=4 reference page read for this explicit query.
  let rawPage: unknown;
  let pageReadFailed = false;
  const pageRequest:
    | { workRef: string; pageSize: 4; signal: AbortSignal }
    | { workRef: string; pageSize: 4; cursor: string; signal: AbortSignal } =
    cursor === undefined
      ? { workRef, pageSize: PAGE_SIZE, signal }
      : { workRef, pageSize: PAGE_SIZE, cursor, signal };
  try {
    rawPage = await snapshot.readReferences.call(owner, pageRequest);
  } catch {
    pageReadFailed = true;
  }
  if (!ownerFence(owner, snapshot, signal)) {
    return failedResult("SOURCE_CHANGED", workRef, query);
  }
  if (pageReadFailed) {
    return failedResult("OWNER_UNAVAILABLE", workRef, query);
  }

  const decoded = decodePageDetailed(rawPage, workRef, expectedHighWater);
  if (!("page" in decoded)) {
    return failedResult(
      decoded.failure === "MALFORMED" ? "INVALID_SOURCE" : "SOURCE_CHANGED",
      workRef,
      query,
    );
  }
  const page = decoded.page;
  if (page.nextCursor !== null && page.nextCursor === cursor) {
    // A cursor that does not advance would loop forever; reject it closed.
    return failedResult("INVALID_SOURCE", workRef, query);
  }

  const items: SavedConversationMatch[] = [];
  let unavailable = 0;
  for (let i = 0; i < page.references.length; i += 1) {
    const reference = page.references[i];
    if (reference === undefined) break;
    if (!ownerFence(owner, snapshot, signal)) {
      return failedResult("SOURCE_CHANGED", workRef, query);
    }
    // Exactly the original pointer identity of the saved row.
    const pointer: OperationPointer = {
      operationKey: reference.operation_key,
      targetKey: reference.target_ref,
      kind: "message",
    };
    let read: unknown;
    let answerReadFailed = false;
    try {
      read = await snapshot.readAnswer.call(owner, pointer, signal);
    } catch {
      answerReadFailed = true;
    }
    if (!ownerFence(owner, snapshot, signal)) {
      return failedResult("SOURCE_CHANGED", workRef, query);
    }
    const text = answerReadFailed ? null : qualifiedAnswerText(reference, read);
    if (text === null) {
      // Unknown, refused, mismatched, missing, malformed or oversize
      // bodies are one unavailable row, never an owner denial.
      unavailable += 1;
      continue;
    }
    const hit = findLiteralMatch(text, query);
    if (hit === null) continue;
    const digest = await sha256Hex(text);
    if (!ownerFence(owner, snapshot, signal)) {
      return failedResult("SOURCE_CHANGED", workRef, query);
    }
    if (digest === null) {
      unavailable += 1;
      continue;
    }
    items.push(
      Object.freeze({
        reference,
        excerpt: buildExcerpt(text, hit.start, hit.end),
        sourceTextSha256: digest,
      }),
    );
  }

  const result: SavedConversationSearchResult = {
    state: "AVAILABLE",
    reason: null,
    workRef,
    query,
    scope: "SAVED_CONVERSATIONS_IN_PROJECT",
    items: Object.freeze(items),
    coverage: Object.freeze({
      status:
        unavailable > 0 || page.nextCursor !== null
          ? ("PARTIAL" as const)
          : ("COMPLETE" as const),
      scanned: page.references.length,
      matched: items.length,
      unavailable,
      nextCursor: page.nextCursor,
      highWater: page.highWater,
    }),
  };
  if (resultContentBytes(result) > MAX_RESULT_UTF8_BYTES) {
    return failedResult("OVER_BUDGET", workRef, query);
  }
  return Object.freeze(result);
}

/** Explicit Open over one actual search result. The original page cursor and
 * watermark retain the exact owner-issued reference scope; neither a match
 * object nor its digest grants an original-answer read on its own. */
export interface SavedConversationOpenRequest {
  readonly workRef: string;
  readonly match: SavedConversationMatch;
  readonly pageCursor?: string;
  readonly expectedHighWater: number;
  readonly signal: AbortSignal;
}
export interface SavedConversationSourceRead {
  readonly state: "AVAILABLE" | "UNAVAILABLE";
  readonly reason: SavedConversationSearchFailure | null;
  readonly reference: SavedConversationReference | null;
  readonly text: string | null;
  readonly sourceTextSha256: string | null;
}
export async function readSavedConversationSource(
  request: SavedConversationOpenRequest, owner: SavedConversationSearchOwner,
): Promise<SavedConversationSourceRead> {
  const unavailable = (reason: SavedConversationSearchFailure): SavedConversationSourceRead =>
    Object.freeze({state:"UNAVAILABLE",reason,reference:null,text:null,sourceTextSha256:null});
  const input = plainOwnData(request);
  if (!input || !["workRef","match","expectedHighWater","signal"].every(key => Object.hasOwn(input,key)) ||
      Object.keys(input).some(key => !["workRef","match","pageCursor","expectedHighWater","signal"].includes(key)) ||
      !isWorkRef(input.workRef) || !isNonNegativeSafeInteger(input.expectedHighWater) ||
      !isAbortSignalLike(input.signal) || (input.pageCursor !== undefined && !isCursor(input.pageCursor)))
    return unavailable("INVALID_INPUT");
  const match = plainOwnData(input.match);
  if (!match || !ownKeysExactly(match,["reference","excerpt","sourceTextSha256"]) ||
      typeof match.excerpt !== "string" || hasLoneSurrogate(match.excerpt) ||
      utf8ByteLength(match.excerpt) > MAX_EXCERPT_UTF8_BYTES ||
      typeof match.sourceTextSha256 !== "string" || !fullMatch(SHA256_PATTERN,match.sourceTextSha256))
    return unavailable("INVALID_INPUT");
  const row = decodeRow(match.reference,input.workRef,input.expectedHighWater,
    {readRefs:new Set(),operations:new Set(),events:new Set()});
  if (!("reference" in row)) return unavailable("INVALID_INPUT");
  const reference=row.reference, expectedDigest=match.sourceTextSha256, excerpt=match.excerpt;
  const signal=input.signal, workRef=input.workRef, highWater=input.expectedHighWater;
  const cursor=input.pageCursor as string|undefined;
  if (!isSearchOwner(owner) || webCryptoSubtle() === null) return unavailable("OWNER_UNAVAILABLE");
  const snapshot=captureOwnerSnapshot(owner);
  if (!snapshot) return unavailable("OWNER_UNAVAILABLE");
  if (!ownerFence(owner,snapshot,signal)) return unavailable("SOURCE_CHANGED");
  let pageRaw:unknown;
  try { pageRaw=await snapshot.readReferences.call(owner,{workRef,pageSize:4,signal,
    ...(cursor !== undefined ? {cursor} : {})}); }
  catch { return unavailable(ownerFence(owner,snapshot,signal) ? "OWNER_UNAVAILABLE" : "SOURCE_CHANGED"); }
  if (!ownerFence(owner,snapshot,signal)) return unavailable("SOURCE_CHANGED");
  const page=decodeSavedConversationPage(pageRaw,workRef,highWater);
  if (!page || !page.references.some(candidate => ROW_KEYS.every(key =>
      candidate[key as keyof SavedConversationReference] === reference[key as keyof SavedConversationReference])))
    return unavailable("SOURCE_CHANGED");
  let answer:unknown;
  try { answer=await snapshot.readAnswer.call(owner,{operationKey:reference.operation_key,
    targetKey:reference.target_ref,kind:"message"},signal); }
  catch { return unavailable(ownerFence(owner,snapshot,signal) ? "OWNER_UNAVAILABLE" : "SOURCE_CHANGED"); }
  if (!ownerFence(owner,snapshot,signal)) return unavailable("SOURCE_CHANGED");
  const text=qualifiedAnswerText(reference,answer);
  if (text === null) return unavailable("INVALID_SOURCE");
  const digest=await sha256Hex(text);
  if (!ownerFence(owner,snapshot,signal)) return unavailable("SOURCE_CHANGED");
  if (digest !== expectedDigest || !text.includes(excerpt)) return unavailable("SOURCE_CHANGED");
  return Object.freeze({state:"AVAILABLE",reason:null,reference,text,sourceTextSha256:digest});
}
