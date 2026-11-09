/** `mastermind.t3_thread_projection/v1` — read-only projection of native T3
 * threads for the Code surface. Deep links follow the documented T3 scheme:
 * `https://app.t3.codes/threads/<environment>/<thread>` (T3 user docs,
 * "Share a thread"). The projection never launches, steers or interrupts a
 * thread; it only projects observed state for inspection and deep-linking.
 *
 * Field names: thread id → `threadId`, environment → `environment`,
 * run state → `runState` (running|idle|blocked|unknown), last activity →
 * `lastActivity` (ISO|null), PR link → `prLink` (https URL|null),
 * repository → `repository` (owner/name|null), company managed →
 * `companyManaged` (boolean).
 */
export type T3RunState = "running" | "idle" | "blocked" | "unknown";

export interface T3ThreadProjection {
  schema: "mastermind.t3_thread_projection.v1";
  threadId: string;
  environment: string;
  title: string | null;
  runState: T3RunState;
  lastActivity: string | null;
  prLink: string | null;
  repository: string | null;
  companyManaged: boolean;
}

export interface T3ThreadProjectionList {
  schema: "mastermind.t3_thread_projection_list.v1";
  threads: readonly T3ThreadProjection[];
}

export type T3ProjectionRead =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "AVAILABLE"; list: T3ThreadProjectionList };

const RUN_STATES = new Set(["running", "idle", "blocked", "unknown"]);
const THREAD_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const ENVIRONMENT_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const HTTPS = /^https:\/\/[A-Za-z0-9.-]+(:\d+)?(\/[^\s"<>]*)?$/;

function invalid(): never {
  throw new Error("T3_PROJECTION_INVALID");
}

function record(
  value: unknown,
  allowed: readonly string[],
  required: readonly string[],
): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  const object = value as Record<string, unknown>;
  if (
    Object.keys(object).some((key) => !allowed.includes(key)) ||
    required.some((key) => !(key in object))
  )
    invalid();
  return object;
}

function text(value: unknown, maximum: number): string {
  if (typeof value !== "string" || value.length === 0 || value.length > maximum)
    invalid();
  return value;
}

function optionalText(value: unknown, maximum: number): string | null {
  return value === null ? null : text(value, maximum);
}

function thread(value: unknown): T3ThreadProjection {
  const required = [
    "threadId",
    "environment",
    "title",
    "runState",
    "lastActivity",
    "prLink",
    "repository",
    "companyManaged",
  ];
  const row = record(value, required, required);
  const threadId = text(row.threadId, 128);
  if (THREAD_ID.exec(threadId)?.[0] !== threadId) invalid();
  const environment = text(row.environment, 128);
  if (ENVIRONMENT_ID.exec(environment)?.[0] !== environment) invalid();
  const runState = text(row.runState, 16);
  if (!RUN_STATES.has(runState)) invalid();
  const runStateValue = runState as T3RunState;
  const lastActivity = optionalText(row.lastActivity, 40);
  if (lastActivity !== null && ISO.exec(lastActivity)?.[0] !== lastActivity)
    invalid();
  const prLink = optionalText(row.prLink, 512);
  if (prLink !== null && HTTPS.exec(prLink)?.[0] !== prLink) invalid();
  if (typeof row.companyManaged !== "boolean") invalid();
  return {
    schema: "mastermind.t3_thread_projection.v1",
    threadId,
    environment,
    title: optionalText(row.title, 240),
    runState: runStateValue,
    lastActivity,
    prLink,
    repository: optionalText(row.repository, 240),
    companyManaged: row.companyManaged,
  };
}

/** Fail-closed parser for a projected T3 thread list. Throws on any defect. */
export function parseT3ThreadList(value: unknown): T3ThreadProjectionList {
  const root = record(value, ["schema", "threads"], ["schema", "threads"]);
  if (root.schema !== "mastermind.t3_thread_projection_list.v1") invalid();
  if (!Array.isArray(root.threads) || root.threads.length > 64) invalid();
  const threads = root.threads.map(thread);
  const identity = new Set(
    threads.map((item) => `${item.environment}/${item.threadId}`),
  );
  if (identity.size !== threads.length) invalid();
  return { schema: "mastermind.t3_thread_projection_list.v1", threads };
}

/** The documented T3 thread deep link. Pure function; no launch authority. */
export function t3ThreadUrl(environment: string, threadId: string): string {
  return `https://app.t3.codes/threads/${encodeURIComponent(environment)}/${encodeURIComponent(threadId)}`;
}

/** Read the projection through the existing mission host facade, fail-closed.
 *  NO host implements `MastermindMissionHost.t3ThreadProjection` today — the
 *  read therefore reports UNAVAILABLE on every host and the Code surface
 *  names that missing source honestly instead of implying a pending load.
 *  This module never invents a host or a second transport. The source of
 *  truth for per-attempt T3 facts is the Fleet per-attempt read
 *  (`mastermind.t3_attempt_fleet/v1`,
 *  integrations/mmos/FLEET_ATTEMPT_CONTRACT_PROPOSAL.md §3 — the Workspace
 *  read route `/workspace/resources/t3/attempts/<attempt_id>` pending
 *  Director G2); this thread-list projection is a separate, still-unfed
 *  surface and does not duplicate it. */
export function readT3ThreadProjection(host: unknown): T3ProjectionRead {
  const source = (
    host as { t3ThreadProjection?: { read?: unknown } } | undefined
  )?.t3ThreadProjection;
  if (
    !source ||
    typeof source !== "object" ||
    typeof source.read !== "function"
  ) {
    return {
      kind: "UNAVAILABLE",
      reason: "T3_PROJECTION_SOURCE_NOT_CONNECTED",
    };
  }
  let raw: unknown;
  try {
    raw = (source.read as () => unknown)();
  } catch {
    return { kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_READ_FAILED" };
  }
  if (raw === null || raw === undefined)
    return { kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_EMPTY" };
  try {
    return { kind: "AVAILABLE", list: parseT3ThreadList(raw) };
  } catch {
    return { kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_INVALID" };
  }
}
