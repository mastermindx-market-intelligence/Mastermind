/**
 * Frontend consumer decoder for the closed selected-root autonomy policy read.
 *
 * Body schema `mastermind.workspace_autonomy_read_result.v1` is a fixed,
 * read-only producer shape for one exact selected root. This decoder checks
 * the released shape only: exact keys, exact selection equality, SAME source
 * receipts and digest/limit formats. It implements no crypto — actual digest
 * validation stays with the source owner binding — and it derives no grant,
 * remaining budget, pause or supervision permission from the admitted
 * ceilings. Unknown or malformed input fails closed with the single fixed
 * error `AUTONOMY_READ_INVALID`; raw exceptions never escape.
 */

export interface AutonomySelection {
  work_ref: string;
  root_job_id: string;
}

export const AUTONOMY_READ_BODY_SCHEMA = "mastermind.workspace_autonomy_read_result.v1";
export const AUTONOMY_SOURCE_OBSERVATION_SCHEMA = "mastermind.workspace_plan_observation.v1";
export const AUTONOMY_RUNTIME_RECEIPT_SCHEMA = "mastermind.runtime_read_observation.v1";
export const AUTONOMY_READ_INVALID = "AUTONOMY_READ_INVALID";
export const AUTONOMY_MAX_LIMIT = 1_000_000;
export const AUTONOMY_MAX_COST_CLASSES = 16;

export const AUTONOMY_UNAVAILABLE_REASONS = [
  "SOURCE_UNAVAILABLE",
  "SOURCE_CHANGED",
  "POLICY_MISMATCH",
  "OVER_BUDGET",
] as const;
export type AutonomyUnavailableReason = (typeof AUTONOMY_UNAVAILABLE_REASONS)[number];

export const AUTONOMY_WORK_REF_PATTERN = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
export const AUTONOMY_ROOT_JOB_ID_PATTERN = /^JOB-[0-9]{1,9}$/;
export const AUTONOMY_SOURCE_IDENTITY_PATTERN = /^[0-9a-f]{32}$/;
export const AUTONOMY_DIGEST_PATTERN = /^[0-9a-f]{64}$/;
export const AUTONOMY_COST_CLASS_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;

export interface AutonomyRuntimeReceipt {
  schema: typeof AUTONOMY_RUNTIME_RECEIPT_SCHEMA;
  state: "SAME";
  source_identity: string;
  before: number;
  after: number;
}

export interface AutonomyControlRoomReceipt {
  instance_before: string;
  instance_after: string;
  publication_before: number;
  publication_after: number;
  document_digest: string;
  source_validity_digest: string;
  cache_currentness_digest: string;
}

export interface AutonomySourceObservation {
  schema: typeof AUTONOMY_SOURCE_OBSERVATION_SCHEMA;
  state: "SAME";
  selection: AutonomySelection;
  runtime: AutonomyRuntimeReceipt;
  control_room: AutonomyControlRoomReceipt;
}

export interface AutonomyPolicyLimits {
  schema_version: 1 | 2;
  max_children_total: number;
  max_fan_out_per_parent: number;
  max_depth: number;
  max_attempts_per_orchestration_job: number;
  max_repair_rounds: number;
  max_review_attempts_per_job: number;
  review_job_attempt_limit: number;
  allowed_child_cost_classes: readonly string[];
}

export interface AutonomyPolicy {
  scope: "ADMITTED_ROOT";
  policy_sha: string;
  source_sha256: string;
  plan_digest: string;
  reservation_digest: string;
  limits: AutonomyPolicyLimits;
}

/** Exact read body union: one admitted-root policy, or one closed unavailable reason. */
export type AutonomyRead = {
  schema: typeof AUTONOMY_READ_BODY_SCHEMA;
  selection: AutonomySelection;
  availability: "AVAILABLE";
  reason_codes: readonly [];
  source_observation: AutonomySourceObservation;
  policy: AutonomyPolicy;
} | {
  schema: typeof AUTONOMY_READ_BODY_SCHEMA;
  selection: AutonomySelection;
  availability: "UNAVAILABLE";
  reason_codes: readonly [AutonomyUnavailableReason];
  source_observation: null;
  policy: null;
};

type Recordish = { [key: string]: unknown };

const SELECTION_KEYS: readonly string[] = ["work_ref", "root_job_id"];
const BODY_KEYS: readonly string[] = [
  "schema", "selection", "availability", "reason_codes", "source_observation", "policy",
];
const OBSERVATION_KEYS: readonly string[] = ["schema", "state", "selection", "runtime", "control_room"];
const RUNTIME_KEYS: readonly string[] = ["schema", "state", "source_identity", "before", "after"];
const CONTROL_ROOM_KEYS: readonly string[] = [
  "instance_before", "instance_after", "publication_before", "publication_after",
  "document_digest", "source_validity_digest", "cache_currentness_digest",
];
const POLICY_KEYS: readonly string[] = [
  "scope", "policy_sha", "source_sha256", "plan_digest", "reservation_digest", "limits",
];
const LIMIT_KEYS: readonly string[] = [
  "schema_version", "max_children_total", "max_fan_out_per_parent", "max_depth",
  "max_attempts_per_orchestration_job", "max_repair_rounds", "max_review_attempts_per_job",
  "review_job_attempt_limit", "allowed_child_cost_classes",
];

function isRecord(value: unknown): value is Recordish {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
}

function hasExactKeys(value: Recordish, keys: readonly string[]): boolean {
  const owned = Reflect.ownKeys(value);
  if (owned.length !== keys.length) return false;
  const expected = new Set(keys);
  return owned.every((key) => {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return typeof key === "string" && expected.has(key)
      && descriptor !== undefined && "value" in descriptor && descriptor.enumerable;
  });
}

function isPatternMatch(value: unknown, pattern: RegExp): value is string {
  return typeof value === "string" && pattern.exec(value)?.[0] === value;
}

function boundedLimit(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= AUTONOMY_MAX_LIMIT
    ? value
    : null;
}

/** Exact selected-root selection: strict key set plus the released formats. */
export function isAutonomySelection(value: unknown): value is AutonomySelection {
  if (!isRecord(value) || !hasExactKeys(value, SELECTION_KEYS)) return false;
  return isPatternMatch(value.work_ref, AUTONOMY_WORK_REF_PATTERN)
    && isPatternMatch(value.root_job_id, AUTONOMY_ROOT_JOB_ID_PATTERN);
}

function parseSourceObservation(
  value: unknown,
  selected: AutonomySelection,
): AutonomySourceObservation | null {
  if (!isRecord(value) || !hasExactKeys(value, OBSERVATION_KEYS)) return null;
  if (value.schema !== AUTONOMY_SOURCE_OBSERVATION_SCHEMA || value.state !== "SAME") return null;
  if (!isAutonomySelection(value.selection)) return null;
  if (value.selection.work_ref !== selected.work_ref
    || value.selection.root_job_id !== selected.root_job_id) return null;
  const runtime = value.runtime;
  if (!isRecord(runtime) || !hasExactKeys(runtime, RUNTIME_KEYS)) return null;
  if (runtime.schema !== AUTONOMY_RUNTIME_RECEIPT_SCHEMA || runtime.state !== "SAME") return null;
  if (!isPatternMatch(runtime.source_identity, AUTONOMY_SOURCE_IDENTITY_PATTERN)) return null;
  if (typeof runtime.before !== "number" || !Number.isInteger(runtime.before) || runtime.before < 0) return null;
  if (runtime.after !== runtime.before) return null;
  const room = value.control_room;
  if (!isRecord(room) || !hasExactKeys(room, CONTROL_ROOM_KEYS)) return null;
  if (typeof room.instance_before !== "string" || room.instance_before.length === 0) return null;
  if (room.instance_after !== room.instance_before) return null;
  if (typeof room.publication_before !== "number" || !Number.isInteger(room.publication_before)
    || room.publication_before <= 0) return null;
  if (room.publication_after !== room.publication_before) return null;
  if (!isPatternMatch(room.document_digest, AUTONOMY_DIGEST_PATTERN)) return null;
  if (!isPatternMatch(room.source_validity_digest, AUTONOMY_DIGEST_PATTERN)) return null;
  if (!isPatternMatch(room.cache_currentness_digest, AUTONOMY_DIGEST_PATTERN)) return null;
  return {
    schema: AUTONOMY_SOURCE_OBSERVATION_SCHEMA,
    state: "SAME",
    selection: { work_ref: selected.work_ref, root_job_id: selected.root_job_id },
    runtime: {
      schema: AUTONOMY_RUNTIME_RECEIPT_SCHEMA,
      state: "SAME",
      source_identity: runtime.source_identity,
      before: runtime.before,
      after: runtime.before,
    },
    control_room: {
      instance_before: room.instance_before,
      instance_after: room.instance_before,
      publication_before: room.publication_before,
      publication_after: room.publication_before,
      document_digest: room.document_digest,
      source_validity_digest: room.source_validity_digest,
      cache_currentness_digest: room.cache_currentness_digest,
    },
  };
}

function parseLimits(value: unknown): AutonomyPolicyLimits | null {
  if (!isRecord(value) || !hasExactKeys(value, LIMIT_KEYS)) return null;
  let schemaVersion: 1 | 2;
  if (value.schema_version === 1) schemaVersion = 1;
  else if (value.schema_version === 2) schemaVersion = 2;
  else return null;
  const maxChildrenTotal = boundedLimit(value.max_children_total);
  const maxFanOutPerParent = boundedLimit(value.max_fan_out_per_parent);
  const maxDepth = boundedLimit(value.max_depth);
  const maxAttemptsPerOrchestrationJob = boundedLimit(value.max_attempts_per_orchestration_job);
  const maxRepairRounds = boundedLimit(value.max_repair_rounds);
  const maxReviewAttemptsPerJob = boundedLimit(value.max_review_attempts_per_job);
  const reviewJobAttemptLimit = boundedLimit(value.review_job_attempt_limit);
  if (maxChildrenTotal === null || maxFanOutPerParent === null || maxDepth === null
    || maxAttemptsPerOrchestrationJob === null || maxRepairRounds === null
    || maxReviewAttemptsPerJob === null || reviewJobAttemptLimit === null) return null;
  const classes = value.allowed_child_cost_classes;
  if (!Array.isArray(classes) || classes.length < 1 || classes.length > AUTONOMY_MAX_COST_CLASSES) return null;
  const seen = new Set<string>();
  for (const item of classes) {
    if (!isPatternMatch(item, AUTONOMY_COST_CLASS_PATTERN) || seen.has(item)) return null;
    seen.add(item);
  }
  return {
    schema_version: schemaVersion,
    max_children_total: maxChildrenTotal,
    max_fan_out_per_parent: maxFanOutPerParent,
    max_depth: maxDepth,
    max_attempts_per_orchestration_job: maxAttemptsPerOrchestrationJob,
    max_repair_rounds: maxRepairRounds,
    max_review_attempts_per_job: maxReviewAttemptsPerJob,
    review_job_attempt_limit: reviewJobAttemptLimit,
    allowed_child_cost_classes: [...classes],
  };
}

function parsePolicy(value: unknown): AutonomyPolicy | null {
  if (!isRecord(value) || !hasExactKeys(value, POLICY_KEYS)) return null;
  if (value.scope !== "ADMITTED_ROOT") return null;
  if (!isPatternMatch(value.policy_sha, AUTONOMY_DIGEST_PATTERN)) return null;
  if (!isPatternMatch(value.source_sha256, AUTONOMY_DIGEST_PATTERN)) return null;
  if (!isPatternMatch(value.plan_digest, AUTONOMY_DIGEST_PATTERN)) return null;
  if (!isPatternMatch(value.reservation_digest, AUTONOMY_DIGEST_PATTERN)) return null;
  const limits = parseLimits(value.limits);
  if (limits === null) return null;
  return {
    scope: "ADMITTED_ROOT",
    policy_sha: value.policy_sha,
    source_sha256: value.source_sha256,
    plan_digest: value.plan_digest,
    reservation_digest: value.reservation_digest,
    limits,
  };
}

function parseRead(value: unknown, expected: AutonomySelection): AutonomyRead | null {
  if (!isAutonomySelection(expected)) return null;
  if (!isRecord(value) || !hasExactKeys(value, BODY_KEYS)) return null;
  if (value.schema !== AUTONOMY_READ_BODY_SCHEMA) return null;
  if (!isAutonomySelection(value.selection)) return null;
  if (value.selection.work_ref !== expected.work_ref
    || value.selection.root_job_id !== expected.root_job_id) return null;
  const selection: AutonomySelection = { work_ref: expected.work_ref, root_job_id: expected.root_job_id };
  if (value.availability === "UNAVAILABLE") {
    const codes = value.reason_codes;
    if (!Array.isArray(codes) || codes.length !== 1) return null;
    const reason = codes[0];
    if (typeof reason !== "string"
      || !(AUTONOMY_UNAVAILABLE_REASONS as readonly string[]).includes(reason)) return null;
    if (value.source_observation !== null || value.policy !== null) return null;
    const decoded: AutonomyRead = {
      schema: AUTONOMY_READ_BODY_SCHEMA,
      selection,
      availability: "UNAVAILABLE",
      reason_codes: [reason as AutonomyUnavailableReason],
      source_observation: null,
      policy: null,
    };
    return decoded;
  }
  if (value.availability !== "AVAILABLE") return null;
  if (!Array.isArray(value.reason_codes) || value.reason_codes.length !== 0) return null;
  const source_observation = parseSourceObservation(value.source_observation, selection);
  if (source_observation === null) return null;
  const policy = parsePolicy(value.policy);
  if (policy === null) return null;
  const decoded: AutonomyRead = {
    schema: AUTONOMY_READ_BODY_SCHEMA,
    selection,
    availability: "AVAILABLE",
    reason_codes: [],
    source_observation,
    policy,
  };
  return decoded;
}

function detachedFrozen<T>(value: T): T {
  if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value as Recordish)) detachedFrozen((value as Recordish)[key]);
  }
  return Object.freeze(value);
}

/**
 * Decode one autonomy read body against the exact expected selected root.
 * Malformed, foreign-root, proof-drifted or unknown input throws the fixed
 * `AUTONOMY_READ_INVALID` error — never a raw exception. The returned value is
 * a detached, deeply frozen copy holding only the released fields.
 */
export function decodeAutonomyPolicy(value: unknown, expected: AutonomySelection): AutonomyRead {
  let decoded: AutonomyRead | null = null;
  try {
    decoded = parseRead(value, expected);
  } catch {
    decoded = null;
  }
  if (decoded === null || new TextEncoder().encode(JSON.stringify(decoded)).byteLength >= 32768)
    throw new Error(AUTONOMY_READ_INVALID);
  return detachedFrozen(decoded);
}
