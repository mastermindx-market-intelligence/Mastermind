/** Fail-closed mirror of the Python `mastermind.t3_attempt_fleet/v1` read.
 *
 * This parser grants no launch, interrupt, send or thread-read authority; it
 * only decodes the signed per-attempt Workspace observation. Unknown stays
 * unknown: an unobserved harness or thread is a real value with its reason,
 * never zero and never healthy. A typed refusal is an honest document, not a
 * transport failure; only malformed bodies decode to INVALID_RESPONSE.
 */
export const T3_ATTEMPT_FLEET_SCHEMA = "mastermind.t3_attempt_fleet/v1";
export const T3_ATTEMPT_FLEET_MAX_BYTES = 16_384;

export type InvariantVerdict = "PROVEN" | "VIOLATED" | "UNKNOWN";
export type FreshnessState = "fresh" | "stale" | "absent" | "unknown";
export type DuplicateKind = "dsh_direct" | "codex_cli" | "second_t3_thread" | "other";

export type T3AttemptThread = { thread_id: string | null; run_id: string | null; state: string | null; unknown_reason: string | null };
export type T3HarnessProcess = { pid: number | null; provider: string | null; model: string | null; start_time: string | null; unknown_reason: string | null };
export type T3DuplicateLauncher = { observed: boolean | null; kinds: DuplicateKind[]; evidence_refs: string[]; unknown_reason: string | null };

export type T3Attempt = {
  attempt_id: string;
  idempotency: { key: string | null; namespace: string | null };
  t3_thread: T3AttemptThread;
  harness_process: T3HarnessProcess;
  thread_count_for_key: number | null;
  thread_count_reason: string | null;
  harness_count_for_thread: number | null;
  harness_count_reason: string | null;
  duplicate_launcher: T3DuplicateLauncher;
  invariant: { exactly_one_thread: InvariantVerdict; exactly_one_harness: InvariantVerdict };
  freshness: { adapter_state: FreshnessState; census: FreshnessState; thread_read: FreshnessState };
  evidence_refs: string[];
};

/** The closed refusal vocabulary of the wire contract (mirror of the Python set). */
export const T3_ATTEMPT_FLEET_REFUSALS = [
  "ADAPTER_ROW_MALFORMED", "ADAPTER_STATE_UNREADABLE", "ADAPTER_STATE_SCHEMA_UNKNOWN",
  "ATTEMPT_FIELDS_INVALID", "ATTEMPT_ID_INVALID", "CENSUS_INVALID", "CLOCK_INVALID",
  "DUPLICATE_FIELDS_INVALID", "EVIDENCE_FIELDS_INVALID", "FRESHNESS_FIELDS_INVALID",
  "FRESHNESS_WINDOW_INVALID", "HARNESS_FIELDS_INVALID", "IDEMPOTENCY_FIELDS_INVALID",
  "INVARIANT_FIELDS_INVALID", "THREAD_FIELDS_INVALID", "THREAD_READ_INVALID",
  "TOO_MANY_ATTEMPTS", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED",
] as const;
export type T3AttemptFleetRefusal = (typeof T3_ATTEMPT_FLEET_REFUSALS)[number];

export type T3AttemptFleetDocument =
  | { kind: "attempt"; evaluated_at_utc: string; attempt: T3Attempt; notes: string[] }
  | { kind: "refusal"; refusal: T3AttemptFleetRefusal };
export type T3AttemptFleetRead =
  | { state: "AVAILABLE"; document: T3AttemptFleetDocument }
  | { state: "UNAVAILABLE"; reason: string };

type Obj = Record<string, unknown>;
const object = (x: unknown): x is Obj => !!x && typeof x === "object" && !Array.isArray(x);
const exact = (x: Obj, keys: string) => Object.keys(x).length === keys.split(" ").length && keys.split(" ").every(k => Object.hasOwn(x, k));
const SECRET = /xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,}|bearer/i;
/** Run ids CONTAIN `/` — the ordinary token grammar would refuse every attempt id. */
const attemptId = (x: unknown): x is string => typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}$/.test(x) && !SECRET.test(x);
const id = (x: unknown): x is string => typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:=/%-]{0,255}$/.test(x) && !SECRET.test(x);
const keyToken = (x: unknown): x is string => typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:=/-]{0,255}$/.test(x) && !SECRET.test(x);
const status = (x: unknown): x is string => typeof x === "string" && /^[A-Za-z0-9_ -]{1,32}$/.test(x);
const providerModel = (x: unknown): x is string => typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:/+ -]{0,63}$/.test(x) && !SECRET.test(x);
const time = (x: unknown): x is string => typeof x === "string" && x.length <= 40 && /(Z|\+00:00)$/.test(x) && Number.isFinite(Date.parse(x));
const note = (x: unknown): x is string => typeof x === "string" && /^[A-Z][A-Z0-9_]{0,63}$/.test(x);
const evidenceRef = (x: unknown): x is string => typeof x === "string" && x.length <= 160 && !x.includes("\n") && !SECRET.test(x);
const VERDICTS: InvariantVerdict[] = ["PROVEN", "VIOLATED", "UNKNOWN"];
const FRESH: FreshnessState[] = ["fresh", "stale", "absent", "unknown"];
const KINDS: DuplicateKind[] = ["dsh_direct", "codex_cli", "second_t3_thread", "other"];
const count = (x: unknown) => x === null || (Number.isSafeInteger(x) && (x as number) >= 0 && (x as number) <= 1_000_000);
const invalid = (): T3AttemptFleetRead => ({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });

/** The wire attempt-id grammar (run ids contain `/`); mirrors the Python `ATTEMPT_ID_RE`. */
export const validT3AttemptId = (x: unknown): x is string =>
  typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}$/.test(x) && !SECRET.test(x);

export function decodeT3AttemptFleet(value: unknown): T3AttemptFleetRead {
  try {
    const encoded = JSON.stringify(value);
    if (!encoded || new TextEncoder().encode(encoded).length >= T3_ATTEMPT_FLEET_MAX_BYTES || !object(value)) return invalid();
    const envelope = exact(value, "schema refusal attempts")
      || exact(value, "schema evaluated_at_utc attempts notes");
    if (!envelope
      || value.schema !== T3_ATTEMPT_FLEET_SCHEMA
      || !Array.isArray(value.attempts) || value.attempts.length > 1) return invalid();
    if ("refusal" in value) {
      if (!exact(value, "schema refusal attempts") || value.attempts.length !== 0
        || !(T3_ATTEMPT_FLEET_REFUSALS as readonly string[]).includes(value.refusal as string)) return invalid();
      return { state: "AVAILABLE", document: { kind: "refusal", refusal: value.refusal as T3AttemptFleetRefusal } };
    }
    if (!exact(value, "schema evaluated_at_utc attempts notes")
      || !time(value.evaluated_at_utc)
      || !Array.isArray(value.notes) || value.notes.length > 8 || !value.notes.every(note)
      || value.attempts.length !== 1) return invalid();
    const attempt = decodeAttempt(value.attempts[0]);
    if (!attempt) return invalid();
    // Detach the validated observation from a mutable transport object.
    return { state: "AVAILABLE", document: { kind: "attempt", evaluated_at_utc: (value as { evaluated_at_utc: string }).evaluated_at_utc, attempt, notes: value.notes as string[] } };
  } catch { return invalid(); }
}

function decodeAttempt(value: unknown): T3Attempt | null {
  if (!object(value) || !exact(value, "attempt_id idempotency t3_thread harness_process thread_count_for_key thread_count_reason harness_count_for_thread harness_count_reason duplicate_launcher invariant freshness evidence_refs")
    || !attemptId(value.attempt_id)) return null;
  const idempotency = value.idempotency;
  if (!object(idempotency) || !exact(idempotency, "key namespace")
    || !(idempotency.key === null || keyToken(idempotency.key))
    || !(idempotency.namespace === null || keyToken(idempotency.namespace))) return null;
  const thread = value.t3_thread;
  if (!object(thread) || !exact(thread, "thread_id run_id state unknown_reason")
    || !(thread.thread_id === null || id(thread.thread_id))
    || !(thread.run_id === null || id(thread.run_id))
    || !(thread.state === null || status(thread.state))
    || !(thread.unknown_reason === null || status(thread.unknown_reason))
    // thread_id is null exactly when unknown_reason carries the reason.
    || (thread.thread_id === null) !== (thread.unknown_reason !== null)) return null;
  const harness = value.harness_process;
  if (!object(harness) || !exact(harness, "pid provider model start_time unknown_reason")
    || !(harness.pid === null || (Number.isSafeInteger(harness.pid) && (harness.pid as number) >= 1))
    || !(harness.provider === null || providerModel(harness.provider))
    || !(harness.model === null || providerModel(harness.model))
    || !(harness.start_time === null || time(harness.start_time))
    // pid is null exactly when unknown_reason carries the reason.
    || (harness.pid === null) !== (harness.unknown_reason !== null)) return null;
  if (!count(value.thread_count_for_key) || !count(value.harness_count_for_thread)
    || !(value.thread_count_reason === null || status(value.thread_count_reason))
    || !(value.harness_count_reason === null || status(value.harness_count_reason))) return null;
  const duplicate = value.duplicate_launcher;
  if (!object(duplicate) || !exact(duplicate, "observed kinds evidence_refs unknown_reason")
    || !(duplicate.observed === null || typeof duplicate.observed === "boolean")
    || !Array.isArray(duplicate.kinds) || !duplicate.kinds.every((k): k is DuplicateKind => KINDS.includes(k as DuplicateKind))
    || !Array.isArray(duplicate.evidence_refs) || duplicate.evidence_refs.length > 24 || !duplicate.evidence_refs.every(evidenceRef)
    // observed is null exactly when unknown_reason carries the reason.
    || (duplicate.observed === null) !== (duplicate.unknown_reason !== null)
    // a proven duplicate always names its kinds.
    || (duplicate.observed === true && duplicate.kinds.length === 0)
    || !(duplicate.unknown_reason === null || status(duplicate.unknown_reason))) return null;
  const invariant = value.invariant;
  if (!object(invariant) || !exact(invariant, "exactly_one_thread exactly_one_harness")
    || !VERDICTS.includes(invariant.exactly_one_thread as InvariantVerdict)
    || !VERDICTS.includes(invariant.exactly_one_harness as InvariantVerdict)) return null;
  const freshness = value.freshness;
  if (!object(freshness) || !exact(freshness, "adapter_state census thread_read")
    || !FRESH.includes(freshness.adapter_state as FreshnessState)
    || !FRESH.includes(freshness.census as FreshnessState)
    || !FRESH.includes(freshness.thread_read as FreshnessState)) return null;
  if (!Array.isArray(value.evidence_refs) || value.evidence_refs.length > 24 || !value.evidence_refs.every(evidenceRef)) return null;
  return JSON.parse(JSON.stringify(value)) as T3Attempt;
}
