/**
 * Closed typed codec for the Terminal sharing-request feed and the distinct
 * native Terminal session status.
 *
 * Pure module: no imports, no I/O, no globals, no URLs, no auth, timers,
 * retry or fallback. Every failure is the single closed code
 * `TERMINAL_SHARING_UNAVAILABLE`; input text and exception contents never leak.
 *
 * Inspection never invokes a getter: records are accepted only as plain
 * objects whose own string keys are enumerable data properties (accessors,
 * symbols, unknown or missing keys, arrays, exotic prototypes and hostile
 * proxies are refused before any value is read, via own descriptors).
 *
 * The feed carries only opaque scope hashes and explicit issued requests. It
 * never carries raw tokens, codes, URLs, user or session UUIDs, private body,
 * subscription ids, actor ids or a static artifact version. `revision` is the
 * immutable request revision, exactly integer 1, never an artifact version.
 */

export const TERMINAL_SHARING_UNAVAILABLE = "TERMINAL_SHARING_UNAVAILABLE";

/** Fresh closed error; the message is the whole observable outcome. */
export function terminalSharingUnavailable(): Error {
  return new Error(TERMINAL_SHARING_UNAVAILABLE);
}

export type TerminalSessionState =
  | "UNCONFIGURED"
  | "SIGNED_OUT"
  | "SIGNING_IN"
  | "SIGNED_IN"
  | "ERROR";

/**
 * Finite public reason allowlist aligned with the distinct native owner.
 */
const SESSION_REASON_CODES = [
  "NOT_CONFIGURED", "INVALID_CONFIG", "SERVICE_KEY_REFUSED", "SIGN_IN_STARTED",
  "SIGN_IN_OVERLAP", "SIGN_IN_OPEN_FAILED", "USER_CANCELLED", "CALLBACK_REJECTED",
  "STATE_MISMATCH", "PENDING_EXPIRED", "PENDING_MISSING", "NO_PENDING",
  "TOKEN_EXCHANGE_REJECTED", "SERVER_VERIFICATION_FAILED", "LATE_COMPLETION_REJECTED",
  "SIGNED_OUT_LOCAL", "SESSION_EXPIRED", "SESSION_CHANGED", "GENERATION_CHANGED",
  "FEED_UNAVAILABLE", "FEED_SCHEMA_REJECTED", "RESPONSE_TOO_LARGE", "REDIRECT_REFUSED",
] as const;

export interface TerminalSessionStatus {
  readonly state: TerminalSessionState;
  /** Distinct Terminal epoch, never an Auth0 generation. */
  readonly generation: number;
  readonly reason: string | null;
  readonly available: boolean;
  /** Opaque domain-separated hashes only; never a user or session UUID. */
  readonly principal_scope: string | null;
  readonly session_scope: string | null;
}

export type TerminalSharingCoverageState = "COMPLETE_WITHIN_SCOPE" | "PARTIAL";

const COVERAGE_REASON_CODES = [
  "LIMIT_REACHED",
  "REQUEST_SOURCE_CHANGED",
  "REQUEST_AUTHORITY_CHANGED",
] as const;

export interface TerminalSharingCoverage {
  readonly state: TerminalSharingCoverageState;
  readonly reason_codes: readonly string[];
}

export interface TerminalSharingViewer {
  readonly principal_scope: string;
  readonly session_scope: string;
}

export interface TerminalSharingSource {
  readonly owner: "TERMINAL_BRIEF_DELIVERY";
  readonly scope: "OWNED_EXPLICIT_SHARING_REQUESTS";
  readonly observed_at: string;
}

export interface TerminalSharingReviewTuple {
  readonly request_ref: string;
  readonly revision: 1;
  readonly delivery_id: string;
}

export interface TerminalSharingDelivery {
  readonly delivery_id: string;
  readonly content_sha256: string;
  readonly title: string;
  readonly slot_asof: string;
  readonly artifact_asof: string | null;
}

export interface TerminalSharingAudience {
  readonly team_id: string;
  readonly name: string;
  readonly member_count: number;
  readonly membership_policy: "DYNAMIC_TEAM_MEMBERSHIP";
}

export interface TerminalSharingRequest {
  readonly request_ref: string;
  /** Exactly integer 1 for this immutable single record; not artifact version. */
  readonly revision: 1;
  readonly issued_at: string;
  readonly delivery: TerminalSharingDelivery;
  readonly audience: TerminalSharingAudience;
  readonly review: TerminalSharingReviewTuple;
}

export interface TerminalSharingFeed {
  readonly schema: "mastermind.terminal_sharing_request_feed.v1";
  readonly viewer: TerminalSharingViewer;
  readonly source: TerminalSharingSource;
  readonly coverage: TerminalSharingCoverage;
  readonly requests: readonly TerminalSharingRequest[];
}

export const FEED_REQUEST_LIMIT = 20;
export const FEED_BYTE_BUDGET = 65536;
const FIELD_MAX_CHARS = 240;

const FEED_KEYS = ["schema", "viewer", "source", "coverage", "requests"] as const;
const VIEWER_KEYS = ["principal_scope", "session_scope"] as const;
const SOURCE_KEYS = ["owner", "scope", "observed_at"] as const;
const COVERAGE_KEYS = ["state", "reason_codes"] as const;
const REQUEST_KEYS = [
  "request_ref",
  "revision",
  "issued_at",
  "delivery",
  "audience",
  "review",
] as const;
const DELIVERY_KEYS = [
  "delivery_id",
  "content_sha256",
  "title",
  "slot_asof",
  "artifact_asof",
] as const;
const AUDIENCE_KEYS = [
  "team_id",
  "name",
  "member_count",
  "membership_policy",
] as const;
const REVIEW_KEYS = ["request_ref", "revision", "delivery_id"] as const;

const STATUS_KEYS = [
  "state",
  "generation",
  "reason",
  "available",
  "principal_scope",
  "session_scope",
] as const;

const SESSION_STATES: readonly TerminalSessionState[] = [
  "UNCONFIGURED",
  "SIGNED_OUT",
  "SIGNING_IN",
  "SIGNED_IN",
  "ERROR",
];

const CANONICAL_UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DIGEST_64 = /^[0-9a-f]{64}$/;
const C0_CONTROL = /[\u0000-\u001f\u007f]/;
const INSTANT =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{6})Z$/;
const CALENDAR_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const TEXT_ENCODER = new TextEncoder();

function unavailable(): never {
  throw terminalSharingUnavailable();
}

/**
 * Returns the value only as a plain record with exactly `keys` own enumerable
 * data properties. No property value is ever read here, so getters are never
 * invoked and hostile inspection cannot throw past this boundary.
 */
export function dataRecord(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> | null {
  try {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return null;
    }
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const own = Reflect.ownKeys(value);
    if (own.length !== keys.length) return null;
    for (const key of keys) {
      if (!Object.prototype.hasOwnProperty.call(value, key)) return null;
    }
    const snapshot: Record<string, unknown> = Object.create(null);
    for (const key of own) {
      if (typeof key !== "string") return null;
      const descriptor = Object.getOwnPropertyDescriptor(value, key);
      if (descriptor === undefined || descriptor === null) return null;
      if (typeof descriptor.get === "function") return null;
      if (typeof descriptor.set === "function") return null;
      if (descriptor.enumerable !== true) return null;
      if (!("value" in descriptor) || !("writable" in descriptor)) return null;
      snapshot[key] = descriptor.value;
    }
    return snapshot;
  } catch {
    return null; // Inspection failures (revoked proxies) refuse, never throw.
  }
}

/** Copy only dense own array data properties; never call an input iterator/getter. */
function dataArray(value: unknown, maxLength: number): readonly unknown[] {
  try {
    if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) unavailable();
    const length = Object.getOwnPropertyDescriptor(value, "length");
    if (!length || !("value" in length) || !Number.isSafeInteger(length.value) ||
        length.value < 0 || length.value > maxLength) unavailable();
    const keys = Reflect.ownKeys(value);
    if (keys.length !== length.value + 1) unavailable();
    const snapshot: unknown[] = [];
    for (let index = 0; index < length.value; index++) {
      const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
      if (!descriptor || !("value" in descriptor) || descriptor.enumerable !== true) unavailable();
      snapshot.push(descriptor.value);
    }
    return snapshot;
  } catch {
    return unavailable();
  }
}

function readString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") unavailable();
  return value;
}

/** Display-only text: nonblank, bounded, no C0. Never used as a navigation target. */
function fieldString(value: unknown): string {
  if (typeof value !== "string") unavailable();
  if (value.length === 0 || value.length > FIELD_MAX_CHARS) unavailable();
  if (value.trim().length === 0) unavailable();
  if (C0_CONTROL.test(value)) unavailable();
  return value;
}

function canonicalUuid(value: unknown): string {
  const text = fieldString(value);
  if (!CANONICAL_UUID.test(text)) unavailable();
  return text;
}

function digest64(value: unknown): string {
  const text = fieldString(value);
  if (!DIGEST_64.test(text)) unavailable();
  return text;
}

function digest64OrNull(value: unknown): string | null {
  if (value === null) return null;
  return digest64(value);
}

function instant(value: unknown): string {
  const text = fieldString(value);
  const match = INSTANT.exec(text);
  if (match === null) unavailable();
  const [, year, month, day, hour, minute, second] = match as RegExpExecArray;
  if (Number(hour) > 23 || Number(minute) > 59 || Number(second) > 59) {
    unavailable();
  }
  calendarDay(Number(year), Number(month), Number(day));
  return text;
}

function instantOrNull(value: unknown): string | null {
  if (value === null) return null;
  return instant(value);
}

function calendarSlot(value: unknown): string {
  const text = fieldString(value);
  const match = CALENDAR_DAY.exec(text);
  if (match === null) unavailable();
  calendarDay(Number(match[1]), Number(match[2]), Number(match[3]));
  return text;
}

function calendarDay(year: number, month: number, day: number): void {
  if (year < 1 || month < 1 || month > 12 || day < 1) unavailable();
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const lengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day > lengths[month - 1]) unavailable();
}

function nonnegSafeInt(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    unavailable();
  }
  return value;
}

function countOrNull(value: unknown): number {
  const count = nonnegSafeInt(value);
  if (count < 1) unavailable();
  return count;
}

function exactRevision(value: unknown): 1 {
  if (typeof value !== "number" || !Number.isInteger(value) || value !== 1) {
    unavailable();
  }
  return 1;
}

function frozen<T>(value: T): T {
  return Object.isFrozen(value) ? value : Object.freeze(value);
}

function frozenArray<T>(values: readonly T[]): readonly T[] {
  return frozen([...values]);
}

export function decodeTerminalSessionStatus(value: unknown): TerminalSessionStatus {
  const record = dataRecord(value, STATUS_KEYS);
  if (record === null) unavailable();
  const state = readString(record, "state");
  if (!SESSION_STATES.includes(state as TerminalSessionState)) unavailable();
  const generation = nonnegSafeInt(record["generation"]);
  const rawReason = record["reason"];
  const reason =
    rawReason === null
      ? null
      : SESSION_REASON_CODES.includes(rawReason as (typeof SESSION_REASON_CODES)[number])
        ? (rawReason as string)
        : unavailable();
  const available = record["available"];
  if (typeof available !== "boolean") unavailable();
  const principal = digest64OrNull(record["principal_scope"]);
  const session = digest64OrNull(record["session_scope"]);
  const granted = state === "SIGNED_IN" && principal !== null && session !== null;
  // SIGNED_IN with both scopes is the only available shape; every other shape
  // reports unavailable with both scopes withheld.
  if (available !== granted) unavailable();
  if (!granted && (principal !== null || session !== null)) unavailable();
  return frozen({
    state: state as TerminalSessionState,
    generation,
    reason,
    available,
    principal_scope: principal,
    session_scope: session,
  });
}

export interface TerminalSharingFeedExpectation {
  readonly principalScope: string;
  readonly sessionScope: string;
}

/**
 * Decodes the native feed body against the caller's current own snapshot.
 * The decoded viewer scopes must equal the expected ones exactly, so a feed
 * captured for another viewer or session is refused, never partially used.
 */
export function decodeTerminalSharingFeed(
  value: unknown,
  expected: TerminalSharingFeedExpectation,
): TerminalSharingFeed {
  const expectedPrincipal = digest64(expected.principalScope);
  const expectedSession = digest64(expected.sessionScope);
  const record = dataRecord(value, FEED_KEYS);
  if (record === null || record.schema !== "mastermind.terminal_sharing_request_feed.v1") unavailable();

  const viewerRecord = dataRecord(record["viewer"], VIEWER_KEYS);
  if (viewerRecord === null) unavailable();
  const principalScope = digest64(viewerRecord["principal_scope"]);
  const sessionScope = digest64(viewerRecord["session_scope"]);
  if (principalScope !== expectedPrincipal || sessionScope !== expectedSession) {
    unavailable();
  }
  const viewer: TerminalSharingViewer = frozen({
    principal_scope: principalScope,
    session_scope: sessionScope,
  });

  const sourceRecord = dataRecord(record["source"], SOURCE_KEYS);
  if (sourceRecord === null) unavailable();
  if (readString(sourceRecord, "owner") !== "TERMINAL_BRIEF_DELIVERY") unavailable();
  if (readString(sourceRecord, "scope") !== "OWNED_EXPLICIT_SHARING_REQUESTS") {
    unavailable();
  }
  const source: TerminalSharingSource = frozen({
    owner: "TERMINAL_BRIEF_DELIVERY",
    scope: "OWNED_EXPLICIT_SHARING_REQUESTS",
    observed_at: instant(sourceRecord["observed_at"]),
  });

  const coverageRecord = dataRecord(record["coverage"], COVERAGE_KEYS);
  if (coverageRecord === null) unavailable();
  const coverageState = readString(coverageRecord, "state");
  if (coverageState !== "COMPLETE_WITHIN_SCOPE" && coverageState !== "PARTIAL") {
    unavailable();
  }
  const rawReasons = dataArray(coverageRecord["reason_codes"], COVERAGE_REASON_CODES.length);
  const reasons: string[] = [];
  for (const entry of rawReasons) {
    const code = fieldString(entry);
    if (!(COVERAGE_REASON_CODES as readonly string[]).includes(code)) unavailable();
    if (reasons.includes(code)) unavailable();
    reasons.push(code);
  }
  // COMPLETE_WITHIN_SCOPE carries no reasons; PARTIAL requires at least one
  // unique known reason, so suppression is never a false empty complete.
  if (coverageState === "COMPLETE_WITHIN_SCOPE" && reasons.length !== 0) unavailable();
  if (coverageState === "PARTIAL" && reasons.length === 0) unavailable();
  const coverage: TerminalSharingCoverage = frozen({
    state: coverageState,
    reason_codes: frozenArray(reasons),
  });

  const rawRequests = dataArray(record["requests"], FEED_REQUEST_LIMIT);
  const seenRequests = new Set<string>();
  const seenDeliveries = new Set<string>();
  const requests = rawRequests.map((entry): TerminalSharingRequest => {
    const requestRecord = dataRecord(entry, REQUEST_KEYS);
    if (requestRecord === null) unavailable();
    const requestRef = canonicalUuid(requestRecord["request_ref"]);
    const revision = exactRevision(requestRecord["revision"]);
    const issuedAt = instant(requestRecord["issued_at"]);
    if (seenRequests.has(requestRef)) unavailable();
    seenRequests.add(requestRef);

    const deliveryRecord = dataRecord(requestRecord["delivery"], DELIVERY_KEYS);
    if (deliveryRecord === null) unavailable();
    const deliveryId = canonicalUuid(deliveryRecord["delivery_id"]);
    if (seenDeliveries.has(deliveryId)) unavailable();
    seenDeliveries.add(deliveryId);
    const delivery: TerminalSharingDelivery = frozen({
      delivery_id: deliveryId,
      content_sha256: digest64(deliveryRecord["content_sha256"]),
      title: fieldString(deliveryRecord["title"]),
      slot_asof: calendarSlot(deliveryRecord["slot_asof"]),
      artifact_asof: instantOrNull(deliveryRecord["artifact_asof"]),
    });

    const audienceRecord = dataRecord(requestRecord["audience"], AUDIENCE_KEYS);
    if (audienceRecord === null) unavailable();
    const audience: TerminalSharingAudience = frozen({
      team_id: canonicalUuid(audienceRecord["team_id"]),
      name: fieldString(audienceRecord["name"]),
      member_count: countOrNull(audienceRecord["member_count"]),
      membership_policy:
        readString(audienceRecord, "membership_policy") === "DYNAMIC_TEAM_MEMBERSHIP"
          ? "DYNAMIC_TEAM_MEMBERSHIP"
          : unavailable(),
    });

    const reviewRecord = dataRecord(requestRecord["review"], REVIEW_KEYS);
    if (reviewRecord === null) unavailable();
    const review: TerminalSharingReviewTuple = frozen({
      request_ref: canonicalUuid(reviewRecord["request_ref"]),
      revision: exactRevision(reviewRecord["revision"]),
      delivery_id: canonicalUuid(reviewRecord["delivery_id"]),
    });
    if (
      review.request_ref !== requestRef ||
      review.delivery_id !== deliveryId ||
      review.revision !== revision
    ) {
      unavailable();
    }
    return frozen({ request_ref: requestRef, revision, issued_at: issuedAt, delivery, audience, review });
  });

  const feed: TerminalSharingFeed = frozen({
    schema: "mastermind.terminal_sharing_request_feed.v1",
    viewer,
    source,
    coverage,
    requests: frozenArray(requests),
  });
  // Total response budget, measured on the compact UTF-8 serialization of the
  // accepted plain data (never on the raw input, whose getters must not run).
  try {
    if (TEXT_ENCODER.encode(JSON.stringify(feed)).length > FEED_BYTE_BUDGET) {
      unavailable();
    }
  } catch {
    unavailable();
  }
  return feed;
}
