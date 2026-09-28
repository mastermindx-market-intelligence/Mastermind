const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(v).length === keys.length && keys.every((key) => Object.hasOwn(v, key));
const integer = (v: unknown, min = 0): v is number =>
  Number.isSafeInteger(v) && Number(v) >= min;
const text = (v: unknown, max = 512): v is string =>
  typeof v === "string" &&
  v.length > 0 &&
  v.length <= max &&
  !/[\u0000-\u001f\u007f]/.test(v);
const hash = (v: unknown): v is string =>
  typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
const timestamp = (v: unknown): v is string =>
  typeof v === "string" &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) &&
  Number.isFinite(Date.parse(v));
const nullable = (v: unknown, check: (value: unknown) => boolean) =>
  v === null || check(v);

export const WORK_GROUP_ORDER = [
  "EFFECT_EXCEPTION",
  "NEEDS_SOL",
  "NEEDS_WORKER",
  "WAITING_CAPACITY",
  "RUNNING",
  "QUEUED",
  "COMPLETED_NOT_ACCEPTED",
  "TERMINAL",
  "UNKNOWN",
] as const;
export type WorkGroup = (typeof WORK_GROUP_ORDER)[number];

export const WORK_LIFECYCLE_STATUSES = [
  "QUEUED",
  "RUNNING",
  "CHECKPOINTED",
  "RATE_LIMITED",
  "CANCEL_REQUESTED",
  "COMPLETED",
  "FAILED",
  "LOST",
  "CANCELLED",
] as const;
export type WorkLifecycleStatus = (typeof WORK_LIFECYCLE_STATUSES)[number];

const GROUPS = new Set<string>(WORK_GROUP_ORDER);
const STATUSES = new Set<string>(WORK_LIFECYCLE_STATUSES);
const LIFECYCLE_GROUP: Record<WorkLifecycleStatus, WorkGroup> = {
  QUEUED: "QUEUED",
  RUNNING: "RUNNING",
  CHECKPOINTED: "RUNNING",
  RATE_LIMITED: "RUNNING",
  CANCEL_REQUESTED: "RUNNING",
  COMPLETED: "COMPLETED_NOT_ACCEPTED",
  FAILED: "TERMINAL",
  LOST: "TERMINAL",
  CANCELLED: "TERMINAL",
};
const REASON_CODES = new Set([
  "source_unavailable",
  "runtime_observation_not_same",
  "projection_refused",
  "source_integrity_unverified",
  "LIFECYCLE_UNAVAILABLE",
  "effect_not_row_attributed",
  "lifecycle_degraded",
]);
const REFUSAL_CODES = new Set([
  "source_unavailable",
  "runtime_observation_not_same",
  "projection_refused",
  "source_integrity_unverified",
]);
const EFFECT_REASONS = new Set([
  "control_room_missing",
  "autonomy_missing",
  "no_exception_observed",
  "exception_observed",
  "read_refused",
]);

export interface WorkColumn {
  value: string;
  source: string | null;
  reason: string;
  evidence_ref: string | null;
  observed_at: string | null;
}
export interface WorkRow {
  root_job_id: string;
  lifecycle: {
    status: WorkLifecycleStatus;
    source: "EXECUTIVE_RUNTIME";
    orchestration_role: string | null;
    depth: number;
  };
  next_actor: WorkColumn;
  capacity: WorkColumn;
  effect: WorkColumn;
  acceptance: {
    state: "NOT_PROJECTED";
    producer_owner: null;
    reason: "product acceptance has no producer in this projection";
  };
  group: WorkGroup;
}
export interface WorkRuntimeObservation {
  schema: "mastermind.runtime_read_observation.v1";
  state: "SAME" | "UNKNOWN" | "CONFLICT";
  source_identity: string | null;
  before: number | null;
  after: number | null;
  snapshot_digest: string | null;
}
export interface WorkSourceObservation {
  schema: "mastermind.workspace_source_observation.v1";
  state: "SAME" | "UNKNOWN" | "CONFLICT";
  selection: null;
  control_room: null | {
    instance_before: string | null;
    instance_after: string | null;
    publication_before: number | null;
    publication_after: number | null;
    document_digest: string | null;
    source_validity_digest: string | null;
    cache_currentness_digest: string | null;
  };
  runtime: WorkRuntimeObservation | null;
}
export interface WorkLifecycleSource {
  schema: "mastermind.fabric_job_root_list.v2";
  runtime: {
    root: string;
    db_present: boolean;
    identity: string | null;
    acquisition: {
      schema: "mastermind.fabric_runtime_acquisition.v1";
      query: Record<string, unknown>;
      owner: string;
      snapshot_digest: string | null;
      budgets: Record<string, unknown>;
      truncation: Record<string, unknown>;
      provenance: Record<string, unknown>;
      generation: {
        schema: "mastermind.runtime_read_observation.v1";
        state: "SAME" | "UNKNOWN" | "CONFLICT";
        source_identity: string | null;
        before: number | null;
        after: number | null;
      };
    };
  };
  degraded: string[];
}
export interface WorkDocument {
  schema: "mastermind.workspace_work_queue.v1";
  generated_at: string;
  availability: "AVAILABLE" | "UNAVAILABLE";
  lifecycle_source: WorkLifecycleSource | null;
  effect_exception: {
    value: "UNKNOWN" | "NONE" | "EFFECT_UNKNOWN";
    scope: "RUNTIME_CURRENT_WORKER";
    observable: boolean;
    reason:
      | "control_room_missing"
      | "autonomy_missing"
      | "no_exception_observed"
      | "exception_observed"
      | "read_refused";
  };
  coverage: {
    count: number;
    total: number | null;
    truncated: boolean;
    completeness: "COMPLETE" | "PARTIAL";
  };
  groups: Record<WorkGroup, WorkRow[]>;
  source_observation: WorkSourceObservation;
  reason_codes: string[];
}

function observation(value: unknown): WorkSourceObservation | null {
  if (
    !record(value) ||
    !exact(value, ["schema", "state", "selection", "control_room", "runtime"]) ||
    value.schema !== "mastermind.workspace_source_observation.v1" ||
    !["SAME", "UNKNOWN", "CONFLICT"].includes(String(value.state)) ||
    value.selection !== null
  )
    return null;
  const control = value.control_room;
  if (
    control !== null &&
    (!record(control) ||
      !exact(control, [
        "instance_before",
        "instance_after",
        "publication_before",
        "publication_after",
        "document_digest",
        "source_validity_digest",
        "cache_currentness_digest",
      ]) ||
      !nullable(control.instance_before, text) ||
      !nullable(control.instance_after, text) ||
      !nullable(control.publication_before, (v) => integer(v, 1)) ||
      !nullable(control.publication_after, (v) => integer(v, 1)) ||
      !nullable(control.document_digest, hash) ||
      !nullable(control.source_validity_digest, hash) ||
      !nullable(control.cache_currentness_digest, hash))
  )
    return null;
  const runtime = value.runtime;
  if (
    runtime !== null &&
    (!record(runtime) ||
      !exact(runtime, [
        "schema",
        "state",
        "source_identity",
        "before",
        "after",
        "snapshot_digest",
      ]) ||
      runtime.schema !== "mastermind.runtime_read_observation.v1" ||
      !["SAME", "UNKNOWN", "CONFLICT"].includes(String(runtime.state)) ||
      !nullable(runtime.source_identity, text) ||
      !nullable(runtime.before, integer) ||
      !nullable(runtime.after, integer) ||
      !nullable(runtime.snapshot_digest, hash))
  )
    return null;
  if (value.state === "SAME") {
    if (!record(control) || !record(runtime) || runtime.state !== "SAME") return null;
    if (
      !text(control.instance_before) ||
      control.instance_before !== control.instance_after ||
      !integer(control.publication_before, 1) ||
      control.publication_before !== control.publication_after ||
      !hash(control.document_digest) ||
      !hash(control.source_validity_digest) ||
      !hash(control.cache_currentness_digest) ||
      !text(runtime.source_identity) ||
      !integer(runtime.before) ||
      runtime.before !== runtime.after ||
      !hash(runtime.snapshot_digest)
    )
      return null;
  }
  return value as unknown as WorkSourceObservation;
}

function lifecycleSource(value: unknown): WorkLifecycleSource | null {
  if (
    !record(value) ||
    !exact(value, ["schema", "runtime", "degraded"]) ||
    value.schema !== "mastermind.fabric_job_root_list.v2" ||
    !Array.isArray(value.degraded) ||
    !value.degraded.every((item) => typeof item === "string") ||
    !record(value.runtime) ||
    !exact(value.runtime, ["root", "db_present", "identity", "acquisition"]) ||
    !text(value.runtime.root, 4096) ||
    typeof value.runtime.db_present !== "boolean" ||
    !nullable(value.runtime.identity, text) ||
    !record(value.runtime.acquisition)
  )
    return null;
  const acquisition = value.runtime.acquisition;
  if (
    !exact(acquisition, [
      "schema",
      "query",
      "owner",
      "snapshot_digest",
      "budgets",
      "truncation",
      "provenance",
      "generation",
    ]) ||
    acquisition.schema !== "mastermind.fabric_runtime_acquisition.v1" ||
    acquisition.owner !== "executive_runtime" ||
    !record(acquisition.query) ||
    acquisition.query.kind !== "root_discovery" ||
    !nullable(acquisition.snapshot_digest, hash) ||
    !record(acquisition.budgets) ||
    !record(acquisition.truncation) ||
    !record(acquisition.provenance) ||
    !record(acquisition.generation)
  )
    return null;
  const generation = acquisition.generation;
  if (
    !exact(generation, ["schema", "state", "source_identity", "before", "after"]) ||
    generation.schema !== "mastermind.runtime_read_observation.v1" ||
    !["SAME", "UNKNOWN", "CONFLICT"].includes(String(generation.state)) ||
    !nullable(generation.source_identity, text) ||
    !nullable(generation.before, integer) ||
    !nullable(generation.after, integer)
  )
    return null;
  return value as unknown as WorkLifecycleSource;
}

function evidenceFields(value: Record<string, unknown>) {
  return (
    nullable(value.evidence_ref, text) &&
    nullable(value.observed_at, timestamp) &&
    ((value.evidence_ref === null && value.observed_at === null) ||
      (value.evidence_ref !== null && value.observed_at !== null))
  );
}

function nextActor(value: unknown): value is WorkColumn {
  if (
    !record(value) ||
    !exact(value, ["value", "source", "reason", "evidence_ref", "observed_at"]) ||
    !evidenceFields(value)
  )
    return false;
  if (value.value === "UNKNOWN")
    return (
      value.source === null &&
      ["no_producer", "evidence_stale"].includes(String(value.reason))
    );
  return (
    ["NEEDS_SOL", "NEEDS_WORKER"].includes(String(value.value)) &&
    value.source === "AGENT_OS" &&
    value.reason === "evidence_supplied" &&
    value.evidence_ref !== null
  );
}

function capacity(value: unknown): value is WorkColumn {
  if (
    !record(value) ||
    !exact(value, ["value", "source", "reason", "evidence_ref", "observed_at"]) ||
    !evidenceFields(value)
  )
    return false;
  if (value.value === "UNKNOWN")
    return (
      value.source === null &&
      ["no_producer", "evidence_stale"].includes(String(value.reason))
    );
  if (value.value === "NOT_APPLICABLE")
    return (
      value.source === "EXECUTIVE_RUNTIME" &&
      value.reason === "post_start_lifecycle" &&
      value.evidence_ref === null
    );
  return (
    value.value === "WAITING_CAPACITY" &&
    value.source === "AUTONOMY" &&
    value.reason === "pre_start_placement_evidence" &&
    value.evidence_ref !== null
  );
}

function effect(value: unknown): value is WorkColumn {
  if (
    !record(value) ||
    !exact(value, ["value", "source", "reason", "evidence_ref", "observed_at"]) ||
    !evidenceFields(value)
  )
    return false;
  if (value.value === "UNKNOWN")
    return (
      value.source === null &&
      ["no_producer", "evidence_stale"].includes(String(value.reason))
    );
  return (
    ["NONE", "EFFECT_UNKNOWN"].includes(String(value.value)) &&
    value.source === "EFFECT_PRODUCER" &&
    ["evidence_supplied", "evidence_supplied_stale"].includes(String(value.reason)) &&
    value.evidence_ref !== null
  );
}

function expectedGroup(value: WorkRow): WorkGroup {
  if (value.effect.value === "EFFECT_UNKNOWN") return "EFFECT_EXCEPTION";
  const lifecycle = LIFECYCLE_GROUP[value.lifecycle.status];
  if (
    (lifecycle === "QUEUED" || lifecycle === "RUNNING") &&
    (value.next_actor.value === "NEEDS_SOL" ||
      value.next_actor.value === "NEEDS_WORKER")
  )
    return value.next_actor.value;
  if (value.capacity.value === "WAITING_CAPACITY") return "WAITING_CAPACITY";
  return lifecycle;
}

function lifecycleCapacityConsistent(value: WorkRow): boolean {
  if (value.lifecycle.status === "QUEUED")
    return value.capacity.value !== "NOT_APPLICABLE";
  return (
    value.capacity.value === "NOT_APPLICABLE" &&
    value.capacity.source === "EXECUTIVE_RUNTIME" &&
    value.capacity.reason === "post_start_lifecycle" &&
    value.capacity.evidence_ref === null &&
    value.capacity.observed_at === null
  );
}

function row(value: unknown, group: WorkGroup): WorkRow | null {
  if (
    !record(value) ||
    !exact(value, [
      "root_job_id",
      "lifecycle",
      "next_actor",
      "capacity",
      "effect",
      "acceptance",
      "group",
    ]) ||
    typeof value.root_job_id !== "string" ||
    !/^JOB-[0-9]{1,9}$/.test(value.root_job_id) ||
    value.group !== group ||
    !record(value.lifecycle) ||
    !exact(value.lifecycle, ["status", "source", "orchestration_role", "depth"]) ||
    !STATUSES.has(String(value.lifecycle.status)) ||
    value.lifecycle.source !== "EXECUTIVE_RUNTIME" ||
    !nullable(value.lifecycle.orchestration_role, text) ||
    !integer(value.lifecycle.depth) ||
    !nextActor(value.next_actor) ||
    !capacity(value.capacity) ||
    !effect(value.effect) ||
    !record(value.acceptance) ||
    !exact(value.acceptance, ["state", "producer_owner", "reason"]) ||
    value.acceptance.state !== "NOT_PROJECTED" ||
    value.acceptance.producer_owner !== null ||
    value.acceptance.reason !==
      "product acceptance has no producer in this projection"
  )
    return null;
  const decoded = value as unknown as WorkRow;
  if (!lifecycleCapacityConsistent(decoded) || expectedGroup(decoded) !== group)
    return null;
  return decoded;
}

export function decodeWorkDocument(input: unknown): WorkDocument | null {
  let value: unknown;
  try {
    value = structuredClone(input);
  } catch {
    return null;
  }
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "generated_at",
      "availability",
      "lifecycle_source",
      "effect_exception",
      "coverage",
      "groups",
      "source_observation",
      "reason_codes",
    ]) ||
    value.schema !== "mastermind.workspace_work_queue.v1" ||
    !timestamp(value.generated_at) ||
    !["AVAILABLE", "UNAVAILABLE"].includes(String(value.availability)) ||
    !record(value.effect_exception) ||
    !exact(value.effect_exception, ["value", "scope", "observable", "reason"]) ||
    !["UNKNOWN", "NONE", "EFFECT_UNKNOWN"].includes(String(value.effect_exception.value)) ||
    value.effect_exception.scope !== "RUNTIME_CURRENT_WORKER" ||
    typeof value.effect_exception.observable !== "boolean" ||
    !EFFECT_REASONS.has(String(value.effect_exception.reason)) ||
    !record(value.coverage) ||
    !exact(value.coverage, ["count", "total", "truncated", "completeness"]) ||
    !integer(value.coverage.count) ||
    !nullable(value.coverage.total, integer) ||
    typeof value.coverage.truncated !== "boolean" ||
    !["COMPLETE", "PARTIAL"].includes(String(value.coverage.completeness)) ||
    !record(value.groups) ||
    !exact(value.groups, WORK_GROUP_ORDER) ||
    !Array.isArray(value.reason_codes) ||
    value.reason_codes.length > 64 ||
    !value.reason_codes.every((code) => typeof code === "string" && REASON_CODES.has(code)) ||
    new Set(value.reason_codes).size !== value.reason_codes.length
  )
    return null;

  const observed = observation(value.source_observation);
  if (!observed) return null;
  const source =
    value.lifecycle_source === null ? null : lifecycleSource(value.lifecycle_source);
  if (value.lifecycle_source !== null && !source) return null;

  const groups = value.groups as Record<string, unknown>;
  const decoded = {} as Record<WorkGroup, WorkRow[]>;
  const roots = new Set<string>();
  let count = 0;
  for (const group of WORK_GROUP_ORDER) {
    const rows = groups[group];
    if (!Array.isArray(rows)) return null;
    const out: WorkRow[] = [];
    for (const raw of rows) {
      const item = row(raw, group);
      if (!item || roots.has(item.root_job_id)) return null;
      roots.add(item.root_job_id);
      out.push(item);
      count++;
    }
    decoded[group] = out;
  }
  if (value.coverage.count !== count) return null;
  if (value.coverage.total !== null && Number(value.coverage.total) < count) return null;

  const isAvailable = value.availability === "AVAILABLE";
  if (isAvailable) {
    if (!source || observed.state !== "SAME" || !observed.runtime) return null;
    const acquisition = source.runtime.acquisition;
    const generation = acquisition.generation;
    if (
      source.runtime.db_present !== true ||
      generation.state !== "SAME" ||
      !hash(acquisition.snapshot_digest) ||
      generation.source_identity !== observed.runtime.source_identity ||
      generation.before !== observed.runtime.before ||
      generation.after !== observed.runtime.after ||
      acquisition.snapshot_digest !== observed.runtime.snapshot_digest ||
      value.reason_codes.some((code) => REFUSAL_CODES.has(code) || code === "LIFECYCLE_UNAVAILABLE")
    )
      return null;
  } else {
    if (
      count !== 0 ||
      value.coverage.count !== 0 ||
      value.coverage.completeness !== "PARTIAL" ||
      value.reason_codes.length === 0
    )
      return null;
    const typedRefusals = value.reason_codes.filter((code) => REFUSAL_CODES.has(code));
    if (
      typedRefusals.length > 0 &&
      (typedRefusals.length !== value.reason_codes.length ||
        value.effect_exception.reason !== "read_refused" ||
        observed.state === "SAME")
    )
      return null;
  }

  if (
    value.effect_exception.value === "EFFECT_UNKNOWN" &&
    (value.effect_exception.observable !== true ||
      value.effect_exception.reason !== "exception_observed")
  )
    return null;
  if (
    value.effect_exception.value === "NONE" &&
    (value.effect_exception.observable !== false ||
      value.effect_exception.reason !== "no_exception_observed")
  )
    return null;
  if (
    value.effect_exception.value === "UNKNOWN" &&
    value.effect_exception.observable !== false
  )
    return null;

  return {
    ...(value as unknown as WorkDocument),
    lifecycle_source: source,
    source_observation: observed,
    groups: decoded,
  };
}
