import { normalizeWorkspaceSelection } from "../mission";

/** Frozen owner schema for the observational Project -> managed Runtime
 * session association READ. This module only decodes owner-produced
 * documents; it cannot authenticate a caller and derives no admission,
 * session control or send/continue authority. The signed Workspace owner
 * port is the only authority for what a caller may read. */

export const PROJECT_ASSOCIATION_SCHEMA = "mastermind.workspace_project_session_association.v1";

export const PROJECT_ASSOCIATION_BODY_BYTES = 16384;

export type ProjectAssociationAvailability = "AVAILABLE" | "UNAVAILABLE";

export type ProjectAssociationState =
  | "MATERIALIZED_OBSERVATION"
  | "RECORDED_MATERIALIZATION"
  | "PREPARING"
  | "UNAVAILABLE";

export type ProjectAssociationReason =
  | "NOT_MATERIALIZED"
  | "BROKER_RESTARTED"
  | "MATERIALIZATION_CONFLICT"
  | "SOURCE_UNAVAILABLE"
  | "SOURCE_CHANGED"
  | "SOURCE_MISMATCH"
  | "RESPONSE_OVER_BUDGET";

/** Model-level selection (camelCase, host side of the owner port). */
export interface ProjectAssociationSelection {
  readonly workRef: string;
  readonly rootJobId: string;
}

/** Owner-observed publication of the project source for the selection. */
export interface ProjectSourcePublication {
  readonly repository: "macro";
  readonly commit: string;
  readonly path: string;
  readonly content_sha256: string;
  readonly request_sha256: string;
}

/** Owner-observed runtime creation record for the selection. */
export interface RuntimeCreationRecord {
  readonly intent_id: string;
  readonly fingerprint: string;
  readonly creation_event_sha256: string;
}

/** Owner-observed materialization receipt (broker-side, digest-only). */
export interface MaterializationReceipt {
  readonly receipt_sha256: string;
  readonly recorded_at: string;
  readonly operation_kind: "start_session" | "resume_session";
  readonly epoch_sha256: string;
  readonly process_generation_sha256: string;
  readonly provider_session_sha256: string;
  readonly generation_number: 1 | 2;
}

/** Decoded, copied and frozen owner association document. */
export interface ProjectAssociationDocument {
  readonly schema: typeof PROJECT_ASSOCIATION_SCHEMA;
  readonly selection: Readonly<{ work_ref: string; root_job_id: string }>;
  readonly availability: ProjectAssociationAvailability;
  readonly state: ProjectAssociationState;
  readonly reason: ProjectAssociationReason | null;
  readonly observational_only: true;
  readonly can_send: false;
  readonly continuation_target: null;
  readonly project_source: ProjectSourcePublication | null;
  readonly runtime_creation: RuntimeCreationRecord | null;
  readonly materialization: MaterializationReceipt | null;
}

/** Existing signed Workspace owner read port. Exactly one bounded
 * observational read per call; callers supply no principal, session, path,
 * provider or epoch selector. */
export type ProjectAssociationRead = (
  request: ProjectAssociationSelection & { signal: AbortSignal },
) => Promise<unknown>;

const AVAILABILITY_VALUES: readonly ProjectAssociationAvailability[] = ["AVAILABLE", "UNAVAILABLE"];
const STATE_VALUES: readonly ProjectAssociationState[] = [
  "MATERIALIZED_OBSERVATION",
  "RECORDED_MATERIALIZATION",
  "PREPARING",
  "UNAVAILABLE",
];
const REASON_VALUES: readonly ProjectAssociationReason[] = [
  "NOT_MATERIALIZED",
  "BROKER_RESTARTED",
  "MATERIALIZATION_CONFLICT",
  "SOURCE_UNAVAILABLE",
  "SOURCE_CHANGED",
  "SOURCE_MISMATCH",
  "RESPONSE_OVER_BUDGET",
];
/** An unavailable owner response always carries one of these reasons; the
 * remaining reasons belong to specific available states. */
const UNAVAILABLE_REASONS: readonly ProjectAssociationReason[] = [
  "MATERIALIZATION_CONFLICT",
  "SOURCE_UNAVAILABLE",
  "SOURCE_CHANGED",
  "SOURCE_MISMATCH",
  "RESPONSE_OVER_BUDGET",
];
const OPERATION_KINDS: readonly string[] = ["start_session", "resume_session"];

const TOP_KEYS = [
  "schema",
  "selection",
  "availability",
  "state",
  "reason",
  "observational_only",
  "can_send",
  "continuation_target",
  "project_source",
  "runtime_creation",
  "materialization",
] as const;
const SELECTION_KEYS = ["work_ref", "root_job_id"] as const;
const SOURCE_KEYS = [
  "repository",
  "commit",
  "path",
  "content_sha256",
  "request_sha256",
] as const;
const CREATION_KEYS = ["intent_id", "fingerprint", "creation_event_sha256"] as const;
const MATERIALIZATION_KEYS = [
  "receipt_sha256",
  "recorded_at",
  "operation_kind",
  "epoch_sha256",
  "process_generation_sha256",
  "provider_session_sha256",
  "generation_number",
] as const;

const WORK_REF_RE = /^WS:(?=.{2,64}$)[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const HEX40_RE = /^[0-9a-f]{40}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const UTC_INSTANT_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d{1,6})?(?:Z|\+00:00)$/;
const WORK_REF_PREFIX = "WS:";
const SOURCE_PATH_PREFIX = "agentos/workstreams/WS-";
const SOURCE_PATH_SUFFIX = ".md";
const INTENT_ID_MAX = 64;

/** Model-level normalizer over the existing Workspace selection helper: the
 * closed {workRef, rootJobId} pair with the canonical host-side predicates. */
export function normalizeProjectAssociationSelection(
  value: unknown,
): ProjectAssociationSelection | null {
  try {
  if (!isPlainObject(value) || !hasExactClosedKeys(value, ["workRef", "rootJobId"])) return null;
  if (typeof value.workRef !== "string" || !WORK_REF_RE.test(value.workRef)) return null;
  const mission = normalizeWorkspaceSelection(value);
  if (!mission) return null;
  return Object.freeze({ workRef: mission.workRef, rootJobId: mission.rootJobId });
  } catch { return null; }
}

function canonicalWorkKey(workRef: string): string {
  return workRef.slice(WORK_REF_PREFIX.length);
}

/** The owner path is exactly the selected canonical work key; nothing is
 * inferred or joined from other identities. */
function expectedSourcePath(expected: ProjectAssociationSelection): string {
  return SOURCE_PATH_PREFIX + canonicalWorkKey(expected.workRef) + SOURCE_PATH_SUFFIX;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype: unknown = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

/** Closed key set: own string-keyed data properties only, no accessors,
 * no symbol keys, no inherited or extra members. */
function hasExactClosedKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== keys.length) return false;
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) return false;
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor) return false;
    if (typeof descriptor.get === "function" || typeof descriptor.set === "function") return false;
    if (!("value" in descriptor)) return false;
  }
  return true;
}

/** Unicode scalar strings only: no C0/C1 controls, no DEL, no lone
 * surrogates (for..of yields a lone surrogate as its own unit). */
function isScalarText(value: unknown): value is string {
  if (typeof value !== "string") return false;
  for (const character of value) {
    const codePoint = character.codePointAt(0) as number;
    if (codePoint <= 0x1f) return false;
    if (codePoint === 0x7f) return false;
    if (codePoint >= 0x80 && codePoint <= 0x9f) return false;
    if (codePoint >= 0xd800 && codePoint <= 0xdfff) return false;
  }
  return true;
}

function utf8ByteLength(text: string): number {
  let bytes = 0;
  for (let index = 0; index < text.length; index++) {
    const unit = text.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff && index + 1 < text.length) {
      const next = text.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        bytes += 4;
        index++;
        continue;
      }
    }
    if (unit <= 0x7f) bytes += 1;
    else if (unit <= 0x7ff) bytes += 2;
    else bytes += 3;
  }
  return bytes;
}

/** Owner-recorded UTC instant: actual owner Z or +00:00 form, real date. */
function isUtcInstant(value: unknown): value is string {
  if (!isScalarText(value)) return false;
  const match = UTC_INSTANT_RE.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second] = match;
  const epoch = Date.parse(value);
  if (!Number.isFinite(epoch)) return false;
  const parsed = new Date(epoch);
  return (
    Number(year) >= 1 && parsed.getUTCFullYear() === Number(year) &&
    parsed.getUTCMonth() + 1 === Number(month) &&
    parsed.getUTCDate() === Number(day) &&
    parsed.getUTCHours() === Number(hour) &&
    parsed.getUTCMinutes() === Number(minute) &&
    parsed.getUTCSeconds() === Number(second)
  );
}

function isHex(value: unknown, pattern: RegExp): value is string {
  return typeof value === "string" && pattern.test(value);
}

function decodeBodySelection(
  value: unknown,
  expected: ProjectAssociationSelection,
): ProjectAssociationDocument["selection"] | null {
  if (!isPlainObject(value) || !hasExactClosedKeys(value, SELECTION_KEYS)) return null;
  const workRef = value.work_ref;
  const rootJobId = value.root_job_id;
  if (typeof workRef !== "string" || !WORK_REF_RE.test(workRef)) return null;
  if (!isScalarText(rootJobId) || rootJobId.length === 0) return null;
  if (workRef !== expected.workRef || rootJobId !== expected.rootJobId) return null;
  return Object.freeze({ work_ref: workRef, root_job_id: rootJobId });
}

function decodeProjectSource(
  value: unknown,
  expected: ProjectAssociationSelection,
): ProjectSourcePublication | null {
  if (value === null) return null;
  if (!isPlainObject(value) || !hasExactClosedKeys(value, SOURCE_KEYS)) return null;
  if (value.repository !== "macro") return null;
  if (!isHex(value.commit, HEX40_RE)) return null;
  const path = value.path;
  if (typeof path !== "string" || path !== expectedSourcePath(expected)) return null;
  if (!isHex(value.content_sha256, HEX64_RE)) return null;
  if (!isHex(value.request_sha256, HEX64_RE)) return null;
  return Object.freeze({
    repository: "macro",
    commit: value.commit,
    path,
    content_sha256: value.content_sha256,
    request_sha256: value.request_sha256,
  });
}

function decodeRuntimeCreation(value: unknown): RuntimeCreationRecord | null {
  if (value === null) return null;
  if (!isPlainObject(value) || !hasExactClosedKeys(value, CREATION_KEYS)) return null;
  const intentId = value.intent_id;
  if (!isScalarText(intentId) || intentId.length > INTENT_ID_MAX || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/.test(intentId)) return null;
  if (!isHex(value.fingerprint, HEX64_RE)) return null;
  if (!isHex(value.creation_event_sha256, HEX64_RE)) return null;
  return Object.freeze({
    intent_id: intentId,
    fingerprint: value.fingerprint,
    creation_event_sha256: value.creation_event_sha256,
  });
}

function decodeMaterialization(value: unknown): MaterializationReceipt | null {
  if (value === null) return null;
  if (!isPlainObject(value) || !hasExactClosedKeys(value, MATERIALIZATION_KEYS)) return null;
  if (!isHex(value.receipt_sha256, HEX64_RE)) return null;
  if (!isUtcInstant(value.recorded_at)) return null;
  const operationKind = value.operation_kind;
  if (typeof operationKind !== "string" || !OPERATION_KINDS.includes(operationKind)) return null;
  if (!isHex(value.epoch_sha256, HEX64_RE)) return null;
  if (!isHex(value.process_generation_sha256, HEX64_RE)) return null;
  if (!isHex(value.provider_session_sha256, HEX64_RE)) return null;
  const generation = value.generation_number;
  if (!((operationKind === "start_session" && generation === 1) || (operationKind === "resume_session" && generation === 2))) return null;
  return Object.freeze({
    receipt_sha256: value.receipt_sha256,
    recorded_at: value.recorded_at,
    operation_kind: operationKind as MaterializationReceipt["operation_kind"],
    epoch_sha256: value.epoch_sha256,
    process_generation_sha256: value.process_generation_sha256,
    provider_session_sha256: value.provider_session_sha256,
    generation_number: generation,
  });
}

function validateExpectedSelection(
  expected: unknown,
): ProjectAssociationSelection | null {
  return normalizeProjectAssociationSelection(expected);
}

/** State, availability, reason and payload must correspond exactly; the
 * four frozen owner shapes admit no other combination. */
function validateDocument(
  value: Record<string, unknown>,
  expected: ProjectAssociationSelection,
): ProjectAssociationDocument | null {
  if (!hasExactClosedKeys(value, TOP_KEYS)) return null;
  if (value.schema !== PROJECT_ASSOCIATION_SCHEMA) return null;
  const selection = decodeBodySelection(value.selection, expected);
  if (!selection) return null;
  if (value.observational_only !== true) return null;
  if (value.can_send !== false) return null;
  if (value.continuation_target !== null) return null;
  const availability = value.availability;
  const state = value.state;
  const reason = value.reason;
  if (typeof availability !== "string" || !AVAILABILITY_VALUES.includes(availability as ProjectAssociationAvailability)) return null;
  if (typeof state !== "string" || !STATE_VALUES.includes(state as ProjectAssociationState)) return null;
  if (reason !== null && (typeof reason !== "string" || !REASON_VALUES.includes(reason as ProjectAssociationReason))) return null;

  const projectSource = decodeProjectSource(value.project_source, expected);
  const runtimeCreation = decodeRuntimeCreation(value.runtime_creation);
  const materialization = decodeMaterialization(value.materialization);

  let correspondence: boolean;
  switch (state) {
    case "MATERIALIZED_OBSERVATION":
      correspondence =
        availability === "AVAILABLE" &&
        reason === null &&
        projectSource !== null &&
        runtimeCreation !== null &&
        materialization !== null;
      break;
    case "RECORDED_MATERIALIZATION":
      correspondence =
        availability === "AVAILABLE" &&
        reason === "BROKER_RESTARTED" &&
        projectSource !== null &&
        runtimeCreation !== null &&
        materialization !== null;
      break;
    case "PREPARING":
      correspondence =
        availability === "AVAILABLE" &&
        reason === "NOT_MATERIALIZED" &&
        projectSource !== null &&
        runtimeCreation !== null &&
        value.materialization === null;
      break;
    case "UNAVAILABLE":
      correspondence =
        availability === "UNAVAILABLE" &&
        typeof reason === "string" &&
        UNAVAILABLE_REASONS.includes(reason as ProjectAssociationReason) &&
        value.project_source === null &&
        value.runtime_creation === null &&
        value.materialization === null;
      break;
    default:
      return null;
  }
  if (!correspondence) return null;
  return Object.freeze({
    schema: PROJECT_ASSOCIATION_SCHEMA,
    selection,
    availability: availability as ProjectAssociationAvailability,
    state: state as ProjectAssociationState,
    reason: reason as ProjectAssociationReason | null,
    observational_only: true,
    can_send: false,
    continuation_target: null,
    project_source: projectSource,
    runtime_creation: runtimeCreation,
    materialization: materialization,
  });
}

/** Decode one owner association document. `raw` is owner JSON text (bounded
 * by PROJECT_ASSOCIATION_BODY_BYTES UTF-8 bytes) or an already-parsed plain
 * owner object; `expected` is the exact public selection this read was made
 * for. Returns a copied, frozen document, or null when the body is not an
 * owner document for exactly that selection. Verification is shape and
 * equality only: a forged caller or a forged body cannot be authenticated
 * here, and the owner/private port remains the sole authority. */
export function decodeProjectAssociation(
  raw: unknown,
  expected: ProjectAssociationSelection,
): ProjectAssociationDocument | null {
  try {
    const checked = validateExpectedSelection(expected);
    if (!checked) return null;
    let value: unknown = raw;
    if (typeof raw === "string") {
      if (utf8ByteLength(raw) + 1 > PROJECT_ASSOCIATION_BODY_BYTES) return null;
      value = JSON.parse(raw);
    }
    if (!isPlainObject(value)) return null;
    // Validate closed own data properties BEFORE serializing. JSON.stringify
    // on an unvalidated object could invoke an accessor or toJSON callback.
    const document = validateDocument(value, checked);
    if (!document || utf8ByteLength(JSON.stringify(document)) + 1 > PROJECT_ASSOCIATION_BODY_BYTES) return null;
    return document;
  } catch {
    return null;
  }
}
