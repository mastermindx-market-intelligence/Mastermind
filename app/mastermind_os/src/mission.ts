export type ReadState = "CURRENT" | "PARTIAL" | "HISTORICAL" | "UNAVAILABLE";
export type SectionState =
  "AVAILABLE" | "EMPTY" | "PARTIAL" | "HISTORICAL" | "UNAVAILABLE";
export type Coverage =
  | "COMPLETE"
  | "INCOMPLETE"
  | "HISTORICAL_ONLY"
  | "NOT_PROJECTED"
  | "NOT_APPLICABLE";
export type DispatchState =
  | "WAITING_CAPACITY"
  | "RECEIVER_SELECTED"
  | "DELIVERY_SENT"
  | "PICKUP_ACKNOWLEDGED"
  | "STARTED"
  | "RETURNED"
  | "CONTINUED"
  | "STOPPED"
  | "DELIVERY_UNCONSUMED"
  | "WATCH_UNPROVEN"
  | "RUNTIME_BINDING_RECONCILIATION_REQUIRED"
  | "EFFECT_UNKNOWN"
  | "UNKNOWN";
export type Role = "plan" | "work" | "review" | "repair" | "aggregation";
export interface EvidenceRef {
  owner:
    | "EXECUTIVE_OS"
    | "EXECUTIVE_INBOX"
    | "AGENT_OS"
    | "GITHUB"
    | "LINEAR"
    | "SLACK"
    | "AUTONOMY_PROJECTION"
    | "CONTROL_ROOM_CACHE"
    | "SOURCE_VALIDITY";
  ref: string;
  field: string;
  source_revision: string | null;
  source_time: string | null;
  observed_at: string | null;
  freshness_state: "CURRENT" | "PARTIAL" | "HISTORICAL" | "UNAVAILABLE";
}
export interface AttemptCard {
  attempt_id: string | null;
  attempt_number: number | null;
  status: (typeof ATTEMPT_STATES)[number] | null;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  has_result: boolean;
  error_present: boolean;
  error_class: "WITHHELD" | null;
}
export interface ChildCard {
  job_id: string;
  status: (typeof JOB_STATES)[number];
  parent_job_id: string;
  depth: number;
  orchestration_role: Role;
  plan_step_id: string | null;
  attempt_count: number;
  attempt_limit: number;
  current_attempt_id: string | null;
  latest_attempt: AttemptCard | null;
  worker_id: string | null;
}
export interface ListSection<T> {
  state: SectionState;
  coverage: Coverage;
  reason_codes: string[];
  total_count: number | null;
  items: T[];
  overflow_count: number | null;
}
export interface SourceReceipt {
  owner: string;
  ref: string;
  observed_at: string;
  freshness: string;
}
export interface OwedTurn {
  seat: "chairman" | "ceo" | "coo" | "worker" | "unknown" | null;
  reason: string | null;
  source_refs: SourceReceipt[];
}
export interface RuntimeCard {
  worker_id: string | null;
  attempt_id: string | null;
  status: (typeof ATTEMPT_STATES)[number] | null;
  runtime_binding_id: string | null;
  binding_generation: string | number | boolean | null;
  continuation_state: "NONE" | "PREPARED" | "ACKNOWLEDGED" | "UNKNOWN" | null;
  effect_state: "none" | "applied" | "effect_unknown" | null;
  capacity_state: "available" | "degraded" | "unknown" | null;
  previous_attempt_id: string | null;
  movement_reason_code: string | null;
}
export interface MissionDocument {
  schema: "mastermind.mission_workspace.v1";
  generated_at: string;
  source: {
    control_room_schema: string | null;
    control_room_generated_at: string | null;
    fabric_view_schema: string | null;
    fabric_view_generated_at: string | null;
    source_generation: Record<string, string | number | boolean | null>;
    source_coverage: string[];
  };
  read_state: {
    state: ReadState;
    reason_codes: string[];
    usable_sections: string[];
  };
  program: {
    work_ref: string;
    title: string | null;
    state: string | null;
    next_action: string | null;
    github_prs: Array<{
      repo: string | null;
      number: number | null;
      url: string | null;
      title: string | null;
      branch: string | null;
      draft: boolean | null;
      merge_state: string | null;
    }>;
    attention_ids: string[];
    disagreements: Array<{
      source: "control_room" | "autonomy_projection";
      field: string | null;
      values: string[];
      reason: string | null;
    }>;
    evidence: EvidenceRef[];
  };
  mission: {
    root_job_id: string | null;
    root_job_candidates: string[];
    root_job_ambiguous: boolean;
    runtime_root_state: "RESOLVED" | "CONFLICT" | "UNKNOWN";
    status: string | null;
    orchestration_role: Role | null;
    plan_step_id: string | null;
    depth: number | null;
    title: string | null;
    armed: {
      ceo_submit_armed: boolean | null;
      coo_autonomy_armed: boolean | null;
      ceo_ingress_app_armed: boolean | null;
      dialogue_bridge_armed: boolean | null;
      terminal_return_armed: boolean | null;
      source: "absent" | "control.json";
    };
    submission_availability:
      "AVAILABLE" | "UNAVAILABLE_NEW_SUBMISSION" | "UNKNOWN";
    capability: {
      state: "PROVEN" | "PARTIAL" | "UNSUPPORTED" | "NOT_INSTALLED";
      installed: boolean;
      version: string | null;
      detail: string;
    };
    evidence: EvidenceRef[];
  };
  principal: {
    accountable_seat: "chairman" | "ceo" | "coo" | "worker" | null;
    current_worker: RuntimeCard | null;
    current_sol_target: RuntimeCard | null;
    owed_turn: OwedTurn | null;
    evidence: EvidenceRef[];
  };
  children: ListSection<ChildCard> & {
    unjoined_job_count: number | null;
    unjoined_job_ids: string[];
  };
  execution: {
    state:
      | "NOT_STARTED"
      | "IN_PROGRESS"
      | "ACCEPTED"
      | "CANCELLED"
      | "FAILED"
      | "LOST"
      | "RATE_LIMITED"
      | null;
    summary_present: boolean;
    artifacts: string[];
    errors_present: boolean;
    next_actions: string[];
    evidence: EvidenceRef[];
  };
  review: {
    required: boolean | null;
    reviews_job_id: string | null;
    verdict: "approve" | "reject" | "NOT_YET";
    evidence: EvidenceRef[];
  };
  transport: {
    dispatch_state: DispatchState;
    reason: string | null;
    actionable: boolean;
    historical: boolean;
    watch_proven: boolean | null;
    carrier: {
      state: "RESOLVED" | "OWNER_HELD" | "UNKNOWN" | null;
      reason: string | null;
      historical: boolean | null;
      actionable: boolean | null;
    } | null;
    w3c: {
      state:
        | "RESOLVED"
        | "ABSENT"
        | "UNAVAILABLE"
        | "CONFLICT"
        | "AMBIGUOUS"
        | "EFFECT_UNKNOWN"
        | null;
      reason: string | null;
      terminal_state: string | null;
      wake_state: string | null;
      terminal_applied: boolean | null;
      source_receipt: {
        observed_at: string | null;
        freshness: "SOURCE_EVIDENCE_TIME" | null;
        snapshot_digest: string | null;
        terminal_source_owner: "executive_terminal_return" | null;
        wake_source_owner: "wake_ledger" | null;
      } | null;
    } | null;
    evidence: EvidenceRef[];
  };
  acceptance: {
    state: "NOT_PROJECTED" | "ACCEPTED";
    reason_codes: string[];
    owner: string | null;
    artifact_revision: string | null;
    ruling: string | null;
    evidence: EvidenceRef[];
  };
  posture: { value: string; rule: string | null; evidence: EvidenceRef[] };
  conversation: ListSection<never>;
  missingness: Array<{
    missingness_class:
      | "MISSING_PRODUCER"
      | "NULL_BY_DESIGN"
      | "EXCLUDED"
      | "OMITTED"
      | "DEGRADED";
    target_field: string;
    producer_owner: string | null;
    reason: string;
  }>;
  degraded: string[];
  budget: Record<string, string | number | boolean | null>;
  feature_gates: {
    conversation: "UNAVAILABLE";
    actions: "READ_ONLY";
    advanced: "AVAILABLE";
  };
}
export interface MissionSelection {
  workRef: string;
  rootJobId: string;
}
export interface UnavailableMission {
  kind: "LOCAL_UNAVAILABLE";
  work_ref: string | null;
  root_job_id: string | null;
  reason: string;
}
export type MissionRead = (
  selection: MissionSelection & { signal: AbortSignal },
) => Promise<unknown>;
export interface ProgramCard {
  workRef: string;
  title: string | null;
  state: string | null;
  nextAction: string | null;
  rootJobId: string | null;
  rootState: "RESOLVED" | "CONFLICT" | "UNKNOWN";
  rootCandidates: string[];
}
export interface Relationship {
  id: string;
  from: string;
  to: string;
  kind: "Execution containment";
}

const TOP = [
  "acceptance",
  "budget",
  "children",
  "conversation",
  "degraded",
  "execution",
  "feature_gates",
  "generated_at",
  "mission",
  "missingness",
  "posture",
  "principal",
  "program",
  "read_state",
  "review",
  "schema",
  "source",
  "transport",
];
const OWNERS = [
  "EXECUTIVE_OS",
  "EXECUTIVE_INBOX",
  "AGENT_OS",
  "GITHUB",
  "LINEAR",
  "SLACK",
  "AUTONOMY_PROJECTION",
  "CONTROL_ROOM_CACHE",
  "SOURCE_VALIDITY",
] as const;
const DISPATCH = [
  "WAITING_CAPACITY",
  "RECEIVER_SELECTED",
  "DELIVERY_SENT",
  "PICKUP_ACKNOWLEDGED",
  "STARTED",
  "RETURNED",
  "CONTINUED",
  "STOPPED",
  "DELIVERY_UNCONSUMED",
  "WATCH_UNPROVEN",
  "RUNTIME_BINDING_RECONCILIATION_REQUIRED",
  "EFFECT_UNKNOWN",
  "UNKNOWN",
] as const;
const ROLES = ["plan", "work", "review", "repair", "aggregation"] as const;
const SECTIONS = [
  "AVAILABLE",
  "EMPTY",
  "PARTIAL",
  "HISTORICAL",
  "UNAVAILABLE",
] as const;
const COVERAGES = [
  "COMPLETE",
  "INCOMPLETE",
  "HISTORICAL_ONLY",
  "NOT_PROJECTED",
  "NOT_APPLICABLE",
] as const;
const READS = ["CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"] as const;
const JOB_STATES = [
  "QUEUED",
  "RUNNING",
  "CHECKPOINTED",
  "RATE_LIMITED",
  "FAILED",
  "LOST",
  "CANCEL_REQUESTED",
  "COMPLETED",
  "CANCELLED",
] as const;
const ATTEMPT_STATES = [
  "CLAIMED",
  "RUNNING",
  "CHECKPOINTED",
  "CANCEL_REQUESTED",
  "RATE_LIMITED",
  "FAILED",
  "LOST",
  "COMPLETED",
  "CANCELLED",
] as const;
const PRIVATE =
  /(?:\b(?:x-ccr-token|authorization|bearer|api[_ -]?key|access[_ -]?token|refresh[_ -]?token)\b|\b(?:token|secret|password|session_id)\s*[:=]|\b(?:gh[pousr]_|sk-|xox[baprs]-)[a-z0-9_-]+|traceback|\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b|\b[a-z0-9.-]+\.(?:local|internal|lan)\b|(?:https?|file|ftp):\/\/|(?:^|[\s"'=(])(?:~\/|\/[A-Za-z0-9._-]+(?:\/[^\s"']*)?|[A-Za-z]:\\|\\\\)|(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[?::1\]?|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(?::\d+)?)/i;
const ISO = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?Z$/;
const obj = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const exact = (v: Record<string, unknown>, ks: readonly string[]) => {
  const a = Object.keys(v).sort(),
    b = [...ks].sort();
  return a.length === b.length && a.every((x, i) => x === b[i]);
};
const oneOf = <T extends readonly string[]>(v: unknown, x: T): v is T[number] =>
  typeof v === "string" && x.includes(v as T[number]);
const text = (v: unknown, n = 1024): v is string =>
  typeof v === "string" &&
  v.length <= n &&
  !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v) &&
  !PRIVATE.test(v);
const ntext = (v: unknown, n = 1024): v is string | null =>
  v === null || text(v, n);
const token = (v: unknown, n = 256): v is string =>
  text(v, n) &&
  !/:\/\//.test(v) &&
  !/\/(?:Users|home|private|Volumes|var|etc)\//i.test(v) &&
  /^[A-Za-z0-9][A-Za-z0-9._:@/-]*$/.test(v);
const time = (v: unknown): v is string => {
  if (typeof v !== "string") return false;
  const match = ISO.exec(v);
  if (!match) return false;
  const [year, month, day, hour, minute, second] = match
    .slice(1, 7)
    .map(Number);
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59)
    return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0),
    days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
};
const ntime = (v: unknown): v is string | null => v === null || time(v);
const int = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): v is number =>
  Number.isInteger(v) && Number(v) >= min && Number(v) <= max;
const nint = (
  v: unknown,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
): v is number | null => v === null || int(v, min, max);
const ws = (v: unknown): v is string =>
  typeof v === "string" && /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(v);
const job = (v: unknown): v is string =>
  typeof v === "string" && /^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$/.test(v);
const strings = (
  v: unknown,
  count = 128,
  len = 512,
  tokens = false,
): v is string[] =>
  Array.isArray(v) &&
  v.length <= count &&
  v.every((x) => (tokens ? token(x, len) : text(x, len)));
function ev(v: unknown): v is EvidenceRef {
  return (
    obj(v) &&
    exact(v, [
      "owner",
      "ref",
      "field",
      "source_revision",
      "source_time",
      "observed_at",
      "freshness_state",
    ]) &&
    oneOf(v.owner, OWNERS) &&
    token(v.ref, 256) &&
    token(v.field, 128) &&
    ntext(v.source_revision, 128) &&
    ntime(v.source_time) &&
    ntime(v.observed_at) &&
    oneOf(v.freshness_state, [
      "CURRENT",
      "PARTIAL",
      "HISTORICAL",
      "UNAVAILABLE",
    ] as const)
  );
}
const evs = (v: unknown): v is EvidenceRef[] =>
  Array.isArray(v) &&
  v.length <= 32 &&
  v.every(ev) &&
  new Set(v.map((x) => JSON.stringify(x))).size === v.length;
function sourceReceipt(v: unknown): v is SourceReceipt {
  return (
    obj(v) &&
    exact(v, ["owner", "ref", "observed_at", "freshness"]) &&
    token(v.owner, 128) &&
    token(v.ref, 256) &&
    time(v.observed_at) &&
    token(v.freshness, 64)
  );
}
function owedTurn(v: unknown): v is OwedTurn {
  return (
    obj(v) &&
    exact(v, ["seat", "reason", "source_refs"]) &&
    (v.seat === null ||
      oneOf(v.seat, [
        "chairman",
        "ceo",
        "coo",
        "worker",
        "unknown",
      ] as const)) &&
    ntext(v.reason, 1024) &&
    Array.isArray(v.source_refs) &&
    v.source_refs.length <= 32 &&
    v.source_refs.every(sourceReceipt)
  );
}
function runtimeCard(v: unknown): v is RuntimeCard {
  return (
    obj(v) &&
    exact(v, [
      "worker_id",
      "attempt_id",
      "status",
      "runtime_binding_id",
      "binding_generation",
      "continuation_state",
      "effect_state",
      "capacity_state",
      "previous_attempt_id",
      "movement_reason_code",
    ]) &&
    ntext(v.worker_id, 128) &&
    ntext(v.attempt_id, 128) &&
    (v.status === null || oneOf(v.status, ATTEMPT_STATES)) &&
    ntext(v.runtime_binding_id, 128) &&
    (v.binding_generation === null ||
      typeof v.binding_generation === "boolean" ||
      (typeof v.binding_generation === "number" &&
        Number.isFinite(v.binding_generation)) ||
      text(v.binding_generation, 256)) &&
    (v.continuation_state === null ||
      oneOf(v.continuation_state, [
        "NONE",
        "PREPARED",
        "ACKNOWLEDGED",
        "UNKNOWN",
      ] as const)) &&
    (v.effect_state === null ||
      oneOf(v.effect_state, ["none", "applied", "effect_unknown"] as const)) &&
    (v.capacity_state === null ||
      oneOf(v.capacity_state, ["available", "degraded", "unknown"] as const)) &&
    ntext(v.previous_attempt_id, 128) &&
    ntext(v.movement_reason_code, 128)
  );
}
function pullRequest(v: unknown) {
  return (
    obj(v) &&
    exact(v, [
      "repo",
      "number",
      "url",
      "title",
      "branch",
      "draft",
      "merge_state",
    ]) &&
    ntext(v.repo, 256) &&
    nint(v.number, 1, 1e9) &&
    (v.url === null ||
      (typeof v.url === "string" &&
        v.url.length <= 512 &&
        /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/pull\/[1-9][0-9]*$/.test(
          v.url,
        ))) &&
    ntext(v.title, 1024) &&
    ntext(v.branch, 512) &&
    (v.draft === null || typeof v.draft === "boolean") &&
    ntext(v.merge_state, 128)
  );
}
function disagreement(v: unknown) {
  return (
    obj(v) &&
    exact(v, ["source", "field", "values", "reason"]) &&
    oneOf(v.source, ["control_room", "autonomy_projection"] as const) &&
    ntext(v.field, 256) &&
    strings(v.values, 50, 4096) &&
    ntext(v.reason, 4096)
  );
}
function carrier(v: unknown) {
  return (
    obj(v) &&
    exact(v, ["state", "reason", "historical", "actionable"]) &&
    (v.state === null ||
      oneOf(v.state, ["RESOLVED", "OWNER_HELD", "UNKNOWN"] as const)) &&
    ntext(v.reason, 4096) &&
    (v.historical === null || typeof v.historical === "boolean") &&
    (v.actionable === null || typeof v.actionable === "boolean")
  );
}
function w3cReceipt(v: unknown) {
  return (
    obj(v) &&
    exact(v, [
      "observed_at",
      "freshness",
      "snapshot_digest",
      "terminal_source_owner",
      "wake_source_owner",
    ]) &&
    ntime(v.observed_at) &&
    (v.freshness === null || v.freshness === "SOURCE_EVIDENCE_TIME") &&
    (v.snapshot_digest === null ||
      (typeof v.snapshot_digest === "string" &&
        /^[0-9a-f]{64}$/.test(v.snapshot_digest))) &&
    (v.terminal_source_owner === null ||
      v.terminal_source_owner === "executive_terminal_return") &&
    (v.wake_source_owner === null || v.wake_source_owner === "wake_ledger")
  );
}
function w3c(v: unknown) {
  return (
    obj(v) &&
    exact(v, [
      "state",
      "reason",
      "terminal_state",
      "wake_state",
      "terminal_applied",
      "source_receipt",
    ]) &&
    (v.state === null ||
      oneOf(v.state, [
        "RESOLVED",
        "ABSENT",
        "UNAVAILABLE",
        "CONFLICT",
        "AMBIGUOUS",
        "EFFECT_UNKNOWN",
      ] as const)) &&
    ntext(v.reason, 4096) &&
    (v.terminal_state === null ||
      oneOf(v.terminal_state, [
        "APPLIED",
        "MISSING",
        "UNAVAILABLE",
        "CONFLICT",
        "EFFECT_UNKNOWN",
      ] as const)) &&
    (v.wake_state === null ||
      oneOf(v.wake_state, [
        "UNAVAILABLE",
        "ABSENT",
        "AMBIGUOUS",
        "OVERFLOW",
        "CONFLICT",
        "NOT_SEEN",
        "PENDING_RETRYABLE",
        "ATTEMPTED",
        "RECONCILIATION_REQUIRED",
        "ACCEPTED",
        "DELIVERED_UNACKNOWLEDGED",
        "TARGET_ACKNOWLEDGED",
        "SOURCE_RESOLVED",
      ] as const)) &&
    (v.terminal_applied === null || typeof v.terminal_applied === "boolean") &&
    (v.source_receipt === null || w3cReceipt(v.source_receipt))
  );
}
function att(v: unknown): v is AttemptCard {
  if (!obj(v)) return false;
  const keys = [
    "attempt_id",
    "attempt_number",
    "status",
    "started_at",
    "finished_at",
    "exit_code",
    "has_result",
    "error_present",
    "error_class",
  ];
  return (
    exact(v, keys) &&
    (v.attempt_id === null || token(v.attempt_id)) &&
    nint(v.attempt_number, 0, 1e6) &&
    (v.status === null || oneOf(v.status, ATTEMPT_STATES)) &&
    ntime(v.started_at) &&
    ntime(v.finished_at) &&
    (v.exit_code === null || int(v.exit_code, -255, 255)) &&
    typeof v.has_result === "boolean" &&
    typeof v.error_present === "boolean" &&
    (v.error_class === null || v.error_class === "WITHHELD") &&
    (v.error_present ? v.error_class === "WITHHELD" : v.error_class === null)
  );
}
function child(v: unknown): v is ChildCard {
  if (!obj(v)) return false;
  const keys = [
    "job_id",
    "status",
    "parent_job_id",
    "depth",
    "orchestration_role",
    "plan_step_id",
    "attempt_count",
    "attempt_limit",
    "current_attempt_id",
    "latest_attempt",
    "worker_id",
  ];
  return (
    exact(v, keys) &&
    job(v.job_id) &&
    oneOf(v.status, JOB_STATES) &&
    job(v.parent_job_id) &&
    int(v.depth, 1, 256) &&
    oneOf(v.orchestration_role, ROLES) &&
    ntext(v.plan_step_id, 128) &&
    int(v.attempt_count, 0, 1e6) &&
    int(v.attempt_limit, 0, 1e6) &&
    (v.current_attempt_id === null || token(v.current_attempt_id)) &&
    (v.latest_attempt === null || att(v.latest_attempt)) &&
    ntext(v.worker_id, 128)
  );
}
function section<T>(
  v: unknown,
  decode: (x: unknown) => x is T,
): v is ListSection<T> {
  if (
    !obj(v) ||
    !exact(v, [
      "state",
      "coverage",
      "reason_codes",
      "total_count",
      "items",
      "overflow_count",
    ]) ||
    !oneOf(v.state, SECTIONS) ||
    !oneOf(v.coverage, COVERAGES) ||
    !strings(v.reason_codes, 64, 128, true) ||
    !Array.isArray(v.items) ||
    v.items.length > 500 ||
    !v.items.every(decode) ||
    !nint(v.total_count, 0, 1e6) ||
    !nint(v.overflow_count, 0, 1e6)
  )
    return false;
  if (v.coverage === "COMPLETE") {
    if (
      v.total_count === null ||
      v.overflow_count === null ||
      v.total_count !== v.items.length + v.overflow_count
    )
      return false;
    if (
      v.state === "EMPTY" &&
      (v.total_count !== 0 || v.items.length || v.overflow_count !== 0)
    )
      return false;
    if (v.total_count === 0 && v.state !== "EMPTY") return false;
  } else if (v.total_count !== null || v.overflow_count !== null) return false;
  return v.state !== "EMPTY" || v.coverage === "COMPLETE";
}

export function decodeMission(
  value: unknown,
  sel: MissionSelection,
): MissionDocument | null {
  if (
    !obj(value) ||
    !exact(value, TOP) ||
    value.schema !== "mastermind.mission_workspace.v1" ||
    !time(value.generated_at)
  )
    return null;
  const s = value.source;
  if (
    !obj(s) ||
    !exact(s, [
      "control_room_schema",
      "control_room_generated_at",
      "fabric_view_schema",
      "fabric_view_generated_at",
      "source_generation",
      "source_coverage",
    ]) ||
    !(
      s.control_room_schema === null ||
      s.control_room_schema === "mastermind.chairman_control_room.v1"
    ) ||
    !ntime(s.control_room_generated_at) ||
    !(
      s.fabric_view_schema === null ||
      s.fabric_view_schema === "mastermind.fabric_job_view.v1"
    ) ||
    !ntime(s.fabric_view_generated_at) ||
    !obj(s.source_generation) ||
    !exact(s.source_generation, ["state", "version", "generation"]) ||
    ![
      s.source_generation.state,
      s.source_generation.version,
      s.source_generation.generation,
    ].every(
      (x) =>
        x === null ||
        typeof x === "boolean" ||
        (typeof x === "number" && Number.isFinite(x)) ||
        text(x, 256),
    ) ||
    !Array.isArray(s.source_coverage) ||
    s.source_coverage.length > 2 ||
    !s.source_coverage.every((x) =>
      oneOf(x, ["control_room", "fabric_view"] as const),
    ) ||
    new Set(s.source_coverage).size !== s.source_coverage.length
  )
    return null;
  const r = value.read_state;
  if (
    !obj(r) ||
    !exact(r, ["state", "reason_codes", "usable_sections"]) ||
    !oneOf(r.state, READS) ||
    !strings(r.reason_codes, 64, 128, true) ||
    !Array.isArray(r.usable_sections) ||
    r.usable_sections.length > 7 ||
    !r.usable_sections.every((x) =>
      oneOf(x, [
        "program",
        "mission",
        "execution",
        "review",
        "principal",
        "transport",
        "children",
      ] as const),
    ) ||
    new Set(r.usable_sections).size !== r.usable_sections.length
  )
    return null;
  const p = value.program;
  if (
    !obj(p) ||
    !exact(p, [
      "work_ref",
      "title",
      "state",
      "next_action",
      "github_prs",
      "attention_ids",
      "disagreements",
      "evidence",
    ]) ||
    p.work_ref !== sel.workRef ||
    !ntext(p.title, 256) ||
    !ntext(p.state, 64) ||
    !ntext(p.next_action, 4096) ||
    !Array.isArray(p.github_prs) ||
    p.github_prs.length > 16 ||
    !p.github_prs.every(pullRequest) ||
    !strings(p.attention_ids, 50, 512, true) ||
    !Array.isArray(p.disagreements) ||
    p.disagreements.length > 50 ||
    !p.disagreements.every(disagreement) ||
    !evs(p.evidence)
  )
    return null;
  const m = value.mission;
  if (
    !obj(m) ||
    !exact(m, [
      "root_job_id",
      "root_job_candidates",
      "root_job_ambiguous",
      "runtime_root_state",
      "status",
      "orchestration_role",
      "plan_step_id",
      "depth",
      "title",
      "armed",
      "submission_availability",
      "capability",
      "evidence",
    ]) ||
    !(m.root_job_id === null || job(m.root_job_id)) ||
    !Array.isArray(m.root_job_candidates) ||
    m.root_job_candidates.length > 50 ||
    !m.root_job_candidates.every(job) ||
    new Set(m.root_job_candidates).size !== m.root_job_candidates.length ||
    typeof m.root_job_ambiguous !== "boolean" ||
    !oneOf(m.runtime_root_state, [
      "RESOLVED",
      "CONFLICT",
      "UNKNOWN",
    ] as const) ||
    !(m.status === null || oneOf(m.status, JOB_STATES)) ||
    !(m.orchestration_role === null || oneOf(m.orchestration_role, ROLES)) ||
    !ntext(m.plan_step_id, 128) ||
    !nint(m.depth, 0, 256) ||
    !ntext(m.title, 256) ||
    !obj(m.armed) ||
    !exact(m.armed, [
      "ceo_submit_armed",
      "coo_autonomy_armed",
      "ceo_ingress_app_armed",
      "dialogue_bridge_armed",
      "terminal_return_armed",
      "source",
    ]) ||
    ![
      m.armed.ceo_submit_armed,
      m.armed.coo_autonomy_armed,
      m.armed.ceo_ingress_app_armed,
      m.armed.dialogue_bridge_armed,
      m.armed.terminal_return_armed,
    ].every((bit) => bit === null || typeof bit === "boolean") ||
    !oneOf(m.armed.source, ["absent", "control.json"] as const) ||
    !oneOf(m.submission_availability, [
      "AVAILABLE",
      "UNAVAILABLE_NEW_SUBMISSION",
      "UNKNOWN",
    ] as const) ||
    !obj(m.capability) ||
    !exact(m.capability, ["state", "installed", "version", "detail"]) ||
    !oneOf(m.capability.state, [
      "PROVEN",
      "PARTIAL",
      "UNSUPPORTED",
      "NOT_INSTALLED",
    ] as const) ||
    typeof m.capability.installed !== "boolean" ||
    !ntext(m.capability.version, 64) ||
    !text(m.capability.detail, 256) ||
    !evs(m.evidence)
  )
    return null;
  const established =
    m.root_job_id === sel.rootJobId &&
    m.runtime_root_state === "RESOLVED" &&
    m.root_job_ambiguous === false &&
    m.root_job_candidates.length === 1 &&
    m.root_job_candidates[0] === sel.rootJobId;
  const unknown =
    m.root_job_id === null &&
    m.runtime_root_state === "UNKNOWN" &&
    m.root_job_ambiguous === false &&
    m.root_job_candidates.length <= 1 &&
    m.root_job_candidates[0] !== sel.rootJobId;
  const conflict =
    m.root_job_id === null &&
    m.runtime_root_state === "CONFLICT" &&
    m.root_job_ambiguous === true;
  if (!established && !unknown && !conflict) return null;
  const pr = value.principal;
  if (
    !obj(pr) ||
    !exact(pr, [
      "accountable_seat",
      "current_worker",
      "current_sol_target",
      "owed_turn",
      "evidence",
    ]) ||
    !(
      pr.accountable_seat === null ||
      oneOf(pr.accountable_seat, ["chairman", "ceo", "coo", "worker"] as const)
    ) ||
    !(pr.current_worker === null || runtimeCard(pr.current_worker)) ||
    !(pr.current_sol_target === null || runtimeCard(pr.current_sol_target)) ||
    !(pr.owed_turn === null || owedTurn(pr.owed_turn)) ||
    !evs(pr.evidence)
  )
    return null;
  if (
    !obj(value.children) ||
    !exact(value.children, [
      "state",
      "coverage",
      "reason_codes",
      "total_count",
      "items",
      "overflow_count",
      "unjoined_job_count",
      "unjoined_job_ids",
    ]) ||
    !section(
      {
        state: value.children.state,
        coverage: value.children.coverage,
        reason_codes: value.children.reason_codes,
        total_count: value.children.total_count,
        items: value.children.items,
        overflow_count: value.children.overflow_count,
      },
      child,
    ) ||
    !nint(value.children.unjoined_job_count, 0, 1e6) ||
    !strings(value.children.unjoined_job_ids, 50, 512, true)
  )
    return null;
  const childItems = value.children.items as ChildCard[],
    childIds = new Set(childItems.map((x) => x.job_id)),
    childById = new Map(childItems.map((x) => [x.job_id, x]));
  const cyclic = childItems.some((start) => {
    const seen = new Set<string>();
    let current: ChildCard | undefined = start;
    while (current && current.parent_job_id !== sel.rootJobId) {
      if (seen.has(current.job_id)) return true;
      seen.add(current.job_id);
      current = childById.get(current.parent_job_id);
    }
    return current === undefined;
  });
  if (
    childIds.size !== childItems.length ||
    cyclic ||
    childItems.some((x) => {
      if (
        x.job_id === sel.rootJobId ||
        x.parent_job_id === x.job_id ||
        (x.parent_job_id !== sel.rootJobId && !childIds.has(x.parent_job_id)) ||
        x.attempt_count > x.attempt_limit
      )
        return true;
      const parentDepth =
        x.parent_job_id === sel.rootJobId
          ? 0
          : childById.get(x.parent_job_id)?.depth;
      return parentDepth === undefined || x.depth !== parentDepth + 1;
    }) ||
    (!established && childItems.length !== 0) ||
    (value.children.coverage === "COMPLETE" &&
      (value.children.unjoined_job_count !== 0 ||
        value.children.unjoined_job_ids.length !== 0)) ||
    (value.children.unjoined_job_count !== null &&
      value.children.unjoined_job_count <
        value.children.unjoined_job_ids.length) ||
    new Set(value.children.unjoined_job_ids).size !==
      value.children.unjoined_job_ids.length ||
    value.children.unjoined_job_ids.some(
      (id) => id === sel.rootJobId || childIds.has(id),
    )
  )
    return null;
  const ex = value.execution;
  if (
    !obj(ex) ||
    !exact(ex, [
      "state",
      "summary_present",
      "artifacts",
      "errors_present",
      "next_actions",
      "evidence",
    ]) ||
    !(
      ex.state === null ||
      oneOf(ex.state, [
        "NOT_STARTED",
        "IN_PROGRESS",
        "ACCEPTED",
        "CANCELLED",
        "FAILED",
        "LOST",
        "RATE_LIMITED",
      ] as const)
    ) ||
    typeof ex.summary_present !== "boolean" ||
    !strings(ex.artifacts, 50, 1024) ||
    typeof ex.errors_present !== "boolean" ||
    !strings(ex.next_actions, 50, 1024) ||
    !evs(ex.evidence)
  )
    return null;
  const rv = value.review;
  if (
    !obj(rv) ||
    !exact(rv, ["required", "reviews_job_id", "verdict", "evidence"]) ||
    !(rv.required === null || typeof rv.required === "boolean") ||
    !(rv.reviews_job_id === null || job(rv.reviews_job_id)) ||
    !oneOf(rv.verdict, ["approve", "reject", "NOT_YET"] as const) ||
    !evs(rv.evidence)
  )
    return null;
  const tr = value.transport;
  if (
    !obj(tr) ||
    !exact(tr, [
      "dispatch_state",
      "reason",
      "actionable",
      "historical",
      "watch_proven",
      "carrier",
      "w3c",
      "evidence",
    ]) ||
    !oneOf(tr.dispatch_state, DISPATCH) ||
    !ntext(tr.reason, 256) ||
    typeof tr.actionable !== "boolean" ||
    typeof tr.historical !== "boolean" ||
    !(tr.watch_proven === null || typeof tr.watch_proven === "boolean") ||
    !(tr.carrier === null || carrier(tr.carrier)) ||
    !(tr.w3c === null || w3c(tr.w3c)) ||
    !evs(tr.evidence)
  )
    return null;
  const ac = value.acceptance;
  if (
    !obj(ac) ||
    !exact(ac, [
      "state",
      "reason_codes",
      "owner",
      "artifact_revision",
      "ruling",
      "evidence",
    ]) ||
    !oneOf(ac.state, ["NOT_PROJECTED", "ACCEPTED"] as const) ||
    !strings(ac.reason_codes, 32, 128, true) ||
    !ntext(ac.owner, 128) ||
    !ntext(ac.artifact_revision, 128) ||
    !ntext(ac.ruling, 512) ||
    !evs(ac.evidence) ||
    (ac.state === "ACCEPTED" &&
      (!ac.owner || !ac.artifact_revision || !ac.ruling)) ||
    (ac.state === "NOT_PROJECTED" &&
      (ac.owner !== null ||
        ac.artifact_revision !== null ||
        ac.ruling !== null ||
        ac.reason_codes.length !== 1 ||
        ac.reason_codes[0] !== "ACCEPTANCE_OWNER_NOT_PROJECTED"))
  )
    return null;
  const po = value.posture;
  if (
    !obj(po) ||
    !exact(po, ["value", "rule", "evidence"]) ||
    !oneOf(po.value, [
      "EFFECT_UNKNOWN",
      "RECONCILIATION_REQUIRED",
      "EXECUTION_FAILED",
      "EXECUTION_CANCELLED",
      "EXECUTION_LOST",
      "EXECUTION_RATE_LIMITED",
      "BLOCKED",
      "DELIVERED_UNCONSUMED",
      "CONSUMPTION_UNKNOWN",
      "RETURN_EXECUTION_MISMATCH",
      "ACCEPTANCE_REVIEW_CONFLICT",
      "ACCEPTED_PRODUCT",
      "REVIEW_REJECTED",
      "RETURNED_UNREVIEWED",
      "REVIEWED_NOT_ACCEPTED",
      "RUNNING",
      "HISTORICAL_OBSERVATION",
      "WAITING",
      "NOT_STARTED",
      "UNKNOWN",
    ] as const) ||
    !(
      po.rule === null ||
      oneOf(po.rule, [
        "A1",
        "B1",
        "B2",
        "C1",
        "C2",
        "C3",
        "C4",
        "D1",
        "E1",
        "E2",
        "E3",
        "F0",
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
        "G1",
        "G1h",
        "G2",
        "G2h",
        "H1",
        "I1",
      ] as const)
    ) ||
    !evs(po.evidence)
  )
    return null;
  if (
    !section(value.conversation, (_x): _x is never => false) ||
    value.conversation.items.length ||
    value.conversation.state !== "UNAVAILABLE" ||
    value.conversation.coverage !== "NOT_PROJECTED" ||
    value.conversation.total_count !== null ||
    value.conversation.overflow_count !== null ||
    value.conversation.reason_codes.length !== 1 ||
    value.conversation.reason_codes[0] !==
      "MISSION_TREE_SUBSLICE_EXCLUDES_CONTENT"
  )
    return null;
  if (
    !Array.isArray(value.missingness) ||
    value.missingness.length > 128 ||
    !value.missingness.every(
      (x) =>
        obj(x) &&
        exact(x, [
          "missingness_class",
          "target_field",
          "producer_owner",
          "reason",
        ]) &&
        oneOf(x.missingness_class, [
          "MISSING_PRODUCER",
          "NULL_BY_DESIGN",
          "EXCLUDED",
          "OMITTED",
          "DEGRADED",
        ] as const) &&
        token(x.target_field, 128) &&
        (x.producer_owner === null || token(x.producer_owner, 128)) &&
        text(x.reason, 512),
    )
  )
    return null;
  if (
    ex.state === null &&
    (r.state === "CURRENT" ||
      !value.missingness.some(
        (x) =>
          obj(x) &&
          x.missingness_class === "DEGRADED" &&
          x.target_field === "execution",
      ))
  )
    return null;
  if (
    !strings(value.degraded, 128, 4096) ||
    !obj(value.budget) ||
    Object.keys(value.budget).length !== 0
  )
    return null;
  const g = value.feature_gates;
  if (
    !obj(g) ||
    !exact(g, ["conversation", "actions", "advanced"]) ||
    g.conversation !== "UNAVAILABLE" ||
    g.actions !== "READ_ONLY" ||
    g.advanced !== "AVAILABLE"
  )
    return null;
  return value as unknown as MissionDocument;
}
export function validateMission(
  v: unknown,
  w: string,
  r?: string | null,
): v is MissionDocument {
  return (
    typeof r === "string" &&
    decodeMission(v, { workRef: w, rootJobId: r }) !== null
  );
}
function part(raw: string) {
  if (!raw || raw.length > 320 || /%(?![0-9A-Fa-f]{2})/.test(raw)) return null;
  try {
    return decodeURIComponent(raw.replace(/\+/g, " "));
  } catch {
    return null;
  }
}
export function selectionFromLocation(
  search = window.location.search,
): MissionSelection | null {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  if (!raw || raw.length > 640) return null;
  const pairs = raw.split("&");
  if (pairs.length !== 2) return null;
  const map = new Map<string, string>();
  for (const pair of pairs) {
    const at = pair.indexOf("=");
    if (at <= 0 || pair.indexOf("=", at + 1) !== -1) return null;
    const k = part(pair.slice(0, at)),
      v = part(pair.slice(at + 1));
    if (
      !k ||
      v === null ||
      map.has(k) ||
      (k !== "work_ref" && k !== "root_job_id")
    )
      return null;
    map.set(k, v);
  }
  const w = map.get("work_ref"),
    r = map.get("root_job_id");
  return ws(w) && job(r) ? { workRef: w, rootJobId: r } : null;
}
export function normalizeSelection(v: unknown): MissionSelection | null {
  return obj(v) &&
    exact(v, ["workRef", "rootJobId"]) &&
    ws(v.workRef) &&
    job(v.rootJobId)
    ? { workRef: v.workRef, rootJobId: v.rootJobId }
    : null;
}
export function unavailableMission(
  sel: MissionSelection | null,
  reason = "NO_HOST_SELECTION",
): UnavailableMission {
  return {
    kind: "LOCAL_UNAVAILABLE",
    work_ref: sel?.workRef ?? null,
    root_job_id: sel?.rootJobId ?? null,
    reason,
  };
}
const CCR = [
  "schema",
  "generated_at",
  "sources",
  "degraded",
  "attention",
  "work",
  "unjoined_open_prs",
  "unbound_surfaces",
  "binding_conflicts",
  "placement_selection",
  "autonomy",
];
const WORK = [
  "work_ref",
  "agent_os",
  "executive",
  "github",
  "attention_ids",
  "bindings",
  "disagreements",
];
const AGENT = [
  "depends_on",
  "next_action",
  "program",
  "reason",
  "reason_code",
  "source",
  "state",
  "status",
  "title",
  "unmet_dependencies",
  "workstream",
];
const AUTONOMY = [
  "chairman_decisions",
  "counts",
  "generated_at",
  "issues",
  "owed_by_seat",
  "responsibilities",
  "schema",
  "source_failures",
  "unmapped_responsibilities",
];
const RESPONSIBILITY = [
  "accountable_seat",
  "actionability_reason",
  "blocker",
  "chairman_decision_reason",
  "chairman_decision_required",
  "current_sol_target",
  "current_worker",
  "declared_blocker",
  "disagreements",
  "dispatch",
  "freshness",
  "is_actionable",
  "owed_turn",
  "placement_state",
  "query_status",
  "responsibility_ref",
  "root_job_ambiguous",
  "root_job_candidates",
  "root_job_id",
  "runtime_root_state",
  "source_receipts",
  "state",
  "title",
  "validity",
  "wake_outcome",
];
export function programsFromControlRoom(value: unknown): {
  programs: ProgramCard[];
  state: "AVAILABLE" | "UNAVAILABLE";
  reason: string;
} {
  if (value === null || value === undefined)
    return {
      programs: [],
      state: "UNAVAILABLE",
      reason: "SOURCE_UNAVAILABLE",
    };
  if (
    !obj(value) ||
    !exact(value, CCR) ||
    value.schema !== "mastermind.chairman_control_room.v1" ||
    !time(value.generated_at) ||
    !Array.isArray(value.work) ||
    value.work.length > 500
  )
    return {
      programs: [],
      state: "UNAVAILABLE",
      reason: "SCHEMA_INVALID",
    };
  const au = value.autonomy;
  if (
    !obj(au) ||
    !exact(au, AUTONOMY) ||
    au.schema !== "mastermind.autonomy_control_room.v1" ||
    !time(au.generated_at) ||
    !Array.isArray(au.responsibilities) ||
    au.responsibilities.length > 500 ||
    !au.responsibilities.every(
      (row) =>
        obj(row) &&
        exact(row, RESPONSIBILITY) &&
        ws(row.responsibility_ref) &&
        (row.root_job_id === null || job(row.root_job_id)) &&
        typeof row.root_job_ambiguous === "boolean" &&
        oneOf(row.runtime_root_state, [
          "RESOLVED",
          "CONFLICT",
          "UNKNOWN",
        ] as const) &&
        Array.isArray(row.root_job_candidates) &&
        row.root_job_candidates.length <= 50 &&
        row.root_job_candidates.every(job),
    )
  )
    return {
      programs: [],
      state: "UNAVAILABLE",
      reason: "SCHEMA_INVALID",
    };
  if (au.generated_at !== value.generated_at)
    return {
      programs: [],
      state: "UNAVAILABLE",
      reason: "GENERATION_MISMATCH",
    };
  const rows = au.responsibilities as Array<Record<string, unknown>>,
    out: ProgramCard[] = [],
    seenWork = new Set<string>();
  for (const card of value.work) {
    if (
      !obj(card) ||
      !exact(card, WORK) ||
      !ws(card.work_ref) ||
      !(card.agent_os === null || obj(card.agent_os))
    )
      return {
        programs: [],
        state: "UNAVAILABLE",
        reason: "WORK_CARD_INVALID",
      };
    if (seenWork.has(card.work_ref))
      return {
        programs: [],
        state: "UNAVAILABLE",
        reason: "DUPLICATE_WORK_REF",
      };
    seenWork.add(card.work_ref);
    const a = card.agent_os;
    if (
      a &&
      (!exact(a, AGENT) ||
        !ntext(a.title, 256) ||
        !ntext(a.state, 64) ||
        !ntext(a.status, 64) ||
        !ntext(a.next_action))
    )
      return {
        programs: [],
        state: "UNAVAILABLE",
        reason: "AGENT_OS_ORIENTATION_INVALID",
      };
    const matches = rows.filter((x) => x.responsibility_ref === card.work_ref),
      base = {
        workRef: card.work_ref,
        title: (a?.title as string | null) ?? null,
        state: (a?.state ?? a?.status ?? null) as string | null,
        nextAction: (a?.next_action as string | null) ?? null,
      };
    if (matches.length !== 1) {
      out.push({
        ...base,
        rootJobId: null,
        rootState: matches.length ? "CONFLICT" : "UNKNOWN",
        rootCandidates: [],
      });
      continue;
    }
    const row = matches[0],
      candidates =
        Array.isArray(row.root_job_candidates) &&
        row.root_job_candidates.length <= 50 &&
        row.root_job_candidates.every(job)
          ? (row.root_job_candidates as string[])
          : [],
      candidatesUnique = new Set(candidates).size === candidates.length,
      state = oneOf(row.runtime_root_state, [
        "RESOLVED",
        "CONFLICT",
        "UNKNOWN",
      ] as const)
        ? row.runtime_root_state
        : "UNKNOWN",
      resolved =
        state === "RESOLVED" &&
        row.root_job_ambiguous === false &&
        job(row.root_job_id) &&
        candidatesUnique &&
        candidates.length === 1 &&
        candidates[0] === row.root_job_id
          ? row.root_job_id
          : null,
      rootState = resolved
        ? "RESOLVED"
        : row.root_job_ambiguous === true ||
            state === "CONFLICT" ||
            !candidatesUnique ||
            (job(row.root_job_id) &&
              candidates.length > 0 &&
              !candidates.includes(row.root_job_id))
          ? "CONFLICT"
          : "UNKNOWN";
    out.push({
      ...base,
      rootJobId: resolved,
      rootState,
      rootCandidates: candidates,
    });
  }
  return {
    programs: out,
    state: "AVAILABLE",
    reason: out.length ? "CONTROL_ROOM_AVAILABLE" : "NO_PROGRAMS_PROJECTED",
  };
}
export function relationshipsForMission(d: MissionDocument): Relationship[] {
  return d.children.items.flatMap((x) =>
    x.parent_job_id && x.job_id
      ? [
          {
            id: `${x.parent_job_id}->${x.job_id}`,
            from: x.parent_job_id,
            to: x.job_id,
            kind: "Execution containment" as const,
          },
        ]
      : [],
  );
}
export function allEvidence(
  d: MissionDocument,
): Array<{ facet: string; evidence: EvidenceRef }> {
  const groups: Array<[string, EvidenceRef[]]> = [
    ["Program", d.program.evidence],
    ["Mission", d.mission.evidence],
    ["Principal", d.principal.evidence],
    ["Execution", d.execution.evidence],
    ["Review", d.review.evidence],
    ["Transport", d.transport.evidence],
    ["Acceptance", d.acceptance.evidence],
    ["Posture", d.posture.evidence],
  ];
  return groups.flatMap(([facet, refs]) =>
    refs.map((evidence) => ({ facet, evidence })),
  );
}
