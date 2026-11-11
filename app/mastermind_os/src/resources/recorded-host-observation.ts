/** A historical physical-host capture. This is not the Linux HostCapacityRead
 * wire, current worker telemetry, a fleet total or placement authority. */
import { validResourceCapacitySelection, type ResourceCapacityReadSelection } from "./resource-capacity-read";
export type HostObservationSelection = ResourceCapacityReadSelection;
export const validHostObservationSelection = validResourceCapacitySelection;
const metrics = ["physical_memory_bytes", "vm_page_size_bytes", "vm_free_pages", "vm_inactive_pages", "vm_speculative_pages", "vm_compressed_pages", "swap_total_bytes", "swap_used_bytes", "pool_total_bytes", "pool_free_bytes"] as const;
type Metric = typeof metrics[number];
export type RecordedHostSnapshot = Record<Metric, number | null> & {
  schema: "mastermind.host_capacity_snapshot/v1"; host_ref: string; boot_ref: string; capacity_pool_ref: string;
  observed_at_ms: number; sample_window_ms: number; total_observation_window_ms: number; hp0_sha256: string;
  hp0_observed_at_ms: number; hp0_sample_window_ms: number; logical_cpu_count: number; load1_milli: number; load_ratio_milli: number;
  hp0_telemetry_status: "COMPLETE" | "PARTIAL"; telemetry_status: "COMPLETE" | "PARTIAL"; unknown_fields: readonly string[];
};
export interface RecordedHostObservation {
  schema: "mastermind.retained_host_observation.v1"; platform: "darwin"; observed_host_role: "PHYSICAL_RESOURCE_HOST";
  observation_kind: "RETAINED_PHYSICAL_BEGIN"; root_job_id: string; job_id: string; attempt_id: string;
  claim_event_id: number; begin_event_id: number; claim_recorded_at_ms: number; begin_recorded_at_ms: number;
  capture_decision_at_ms: number; read_at_ms: number; age_ms: number; oldest_observation_age_ms: number; snapshot_sha256: string;
  source: { commit_sha: string; helper_sha256: string; policy_revision: string; host_qualification_revision: string };
  snapshot: RecordedHostSnapshot; capability: "OBSERVATION_ONLY"; admission_state: "NOT_EVALUATED"; can_place_work: false;
}
export type RecordedHostObservationState = { state: "PENDING" } | { state: "UNAVAILABLE" } | { state: "AVAILABLE"; document: RecordedHostObservation };
export type HostObservationRead = Exclude<RecordedHostObservationState, { state: "PENDING" }>;
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: readonly string[]) => Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const safe = (v: unknown, min = 0): v is number => Number.isSafeInteger(v) && Number(v) >= min;
const match = (v: unknown, pattern: RegExp): v is string => typeof v === "string" && pattern.exec(v)?.[0] === v;
const hash = (v: unknown) => match(v, /^[0-9a-f]{64}$/);
const same = (v: unknown, selected: HostObservationSelection) => object(v) && exact(v, ["work_ref", "root_job_id", "job_id", "attempt_id"]) && Object.entries(selected).every(([k, value]) => v[k] === value);
function invalid(): never { throw Error("HOST_OBSERVATION_INVALID"); }

/** Detached JSON data only: getters/proxies, foreign prototypes, sparse arrays
 * and inherited serialization hooks cannot introduce display fields. */
function data(input: unknown, depth = 0): unknown {
  if (depth > 16) return invalid();
  if (input === null || typeof input === "string" || typeof input === "boolean" || typeof input === "number" && Number.isFinite(input)) return input;
  if (typeof input !== "object") return invalid();
  const array = Array.isArray(input), proto = Object.getPrototypeOf(input);
  if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) return invalid();
  const descriptors = Object.getOwnPropertyDescriptors(input);
  if (array) {
    const length = descriptors.length?.value;
    if (!safe(length) || length > 128 || Reflect.ownKeys(descriptors).length !== length + 1) return invalid();
    return Object.freeze(Array.from({ length }, (_, i) => {
      const d = descriptors[String(i)];
      if (!d || !d.enumerable || !Object.hasOwn(d, "value")) return invalid();
      return data(d.value, depth + 1);
    }));
  }
  const result: Record<string, unknown> = Object.create(null);
  for (const key of Reflect.ownKeys(descriptors)) {
    const d = typeof key === "string" ? descriptors[key] : null;
    if (!d || !d.enumerable || !Object.hasOwn(d, "value")) return invalid();
    result[key as string] = data(d.value, depth + 1);
  }
  return Object.freeze(result);
}

function observation(value: unknown, selected: HostObservationSelection): RecordedHostObservation {
  const keys = ["schema", "platform", "observed_host_role", "observation_kind", "root_job_id", "job_id", "attempt_id", "claim_event_id", "begin_event_id", "claim_recorded_at_ms", "begin_recorded_at_ms", "capture_decision_at_ms", "read_at_ms", "age_ms", "oldest_observation_age_ms", "snapshot_sha256", "snapshot", "source", "capability", "admission_state", "can_place_work"];
  if (!object(value) || !exact(value, keys) || value.schema !== "mastermind.retained_host_observation.v1" || value.platform !== "darwin" || value.observed_host_role !== "PHYSICAL_RESOURCE_HOST" || value.observation_kind !== "RETAINED_PHYSICAL_BEGIN" || value.capability !== "OBSERVATION_ONLY" || value.admission_state !== "NOT_EVALUATED" || value.can_place_work !== false || ["root_job_id", "job_id", "attempt_id"].some(k => value[k] !== selected[k as keyof HostObservationSelection]) || !hash(value.snapshot_sha256)) return invalid();
  for (const key of ["claim_event_id", "begin_event_id", "claim_recorded_at_ms", "begin_recorded_at_ms", "capture_decision_at_ms", "read_at_ms"]) if (!safe(value[key], 1)) return invalid();
  const v = value as unknown as RecordedHostObservation, s = value.snapshot, source = value.source;
  if (!object(source) || !exact(source, ["commit_sha", "helper_sha256", "policy_revision", "host_qualification_revision"]) || !match(source.commit_sha, /^[0-9a-f]{40}$/) || !hash(source.helper_sha256) || [source.policy_revision, source.host_qualification_revision].some(x => !match(x, /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/))) return invalid();
  if (!object(s) || !exact(s, ["schema", "host_ref", "boot_ref", "capacity_pool_ref", "observed_at_ms", "sample_window_ms", "total_observation_window_ms", "hp0_sha256", "hp0_observed_at_ms", "hp0_sample_window_ms", "logical_cpu_count", "load1_milli", "load_ratio_milli", "hp0_telemetry_status", "telemetry_status", "unknown_fields", ...metrics]) || s.schema !== "mastermind.host_capacity_snapshot/v1" || !hash(s.hp0_sha256)) return invalid();
  for (const [key, prefix] of [["host_ref", "host-"], ["boot_ref", "boot-"], ["capacity_pool_ref", "capacity-pool-"]]) if (!match(s[key], new RegExp(`^${prefix}[0-9a-f]{64}$`))) return invalid();
  for (const key of ["observed_at_ms", "sample_window_ms", "total_observation_window_ms", "hp0_observed_at_ms", "hp0_sample_window_ms", "logical_cpu_count"]) if (!safe(s[key], 1)) return invalid();
  const snapshot = s as unknown as RecordedHostSnapshot;
  if (snapshot.sample_window_ms > 10000 || snapshot.hp0_sample_window_ms > 5000 || snapshot.total_observation_window_ms > 3600000 || snapshot.total_observation_window_ms < snapshot.sample_window_ms || snapshot.hp0_observed_at_ms > snapshot.observed_at_ms || snapshot.hp0_observed_at_ms < snapshot.hp0_sample_window_ms || snapshot.total_observation_window_ms !== snapshot.observed_at_ms - snapshot.hp0_observed_at_ms + snapshot.hp0_sample_window_ms || snapshot.logical_cpu_count > 4096 || !safe(snapshot.load1_milli) || !safe(snapshot.load_ratio_milli) || snapshot.load_ratio_milli !== Math.floor(snapshot.load1_milli / snapshot.logical_cpu_count) || !["COMPLETE", "PARTIAL"].includes(snapshot.hp0_telemetry_status)) return invalid();
  const unknown = metrics.filter(k => s[k] === null).sort();
  if (!Array.isArray(s.unknown_fields) || s.unknown_fields.length !== unknown.length || s.unknown_fields.some((k, i) => k !== unknown[i]) || s.telemetry_status !== (unknown.length ? "PARTIAL" : "COMPLETE")) return invalid();
  for (const key of metrics) if (s[key] !== null && !safe(s[key], ["physical_memory_bytes", "vm_page_size_bytes"].includes(key) ? 1 : 0)) return invalid();
  for (const [lower, upper] of [["swap_used_bytes", "swap_total_bytes"], ["pool_free_bytes", "pool_total_bytes"]] as const) if (snapshot[lower] !== null && snapshot[upper] !== null && snapshot[lower]! > snapshot[upper]!) return invalid();
  if ([v.read_at_ms, v.claim_recorded_at_ms, v.begin_recorded_at_ms, v.capture_decision_at_ms].some(x => x > 8_640_000_000_000_000) || !safe(v.age_ms) || !safe(v.oldest_observation_age_ms) || snapshot.observed_at_ms < snapshot.total_observation_window_ms || !(v.begin_recorded_at_ms <= v.claim_recorded_at_ms && v.claim_recorded_at_ms <= v.read_at_ms && snapshot.observed_at_ms <= v.capture_decision_at_ms && v.capture_decision_at_ms <= v.read_at_ms && v.begin_recorded_at_ms <= v.capture_decision_at_ms && v.capture_decision_at_ms < v.begin_recorded_at_ms + 1000) || v.age_ms !== v.read_at_ms - snapshot.observed_at_ms || v.oldest_observation_age_ms !== v.age_ms + snapshot.total_observation_window_ms) return invalid();
  return v;
}

export function decodeRecordedHostObservation(raw: unknown, selected: HostObservationSelection): RecordedHostObservation {
  try { if (!validHostObservationSelection(selected)) return invalid(); return observation(data(raw), selected); } catch { return invalid(); }
}

export function decodeHostObservationRead(raw: unknown, selected: HostObservationSelection): HostObservationRead {
  try {
    if (!validHostObservationSelection(selected)) return invalid();
    const body = data(raw);
    if (new TextEncoder().encode(JSON.stringify({ ok: true, result: body })).byteLength + 1 > 16384 || !object(body) || !exact(body, ["schema", "selection", "availability", "reason_codes", "observation", "source_observation"]) || body.schema !== "mastermind.workspace_host_observation_result.v1" || !same(body.selection, selected) || !Array.isArray(body.reason_codes)) return invalid();
    if (body.availability === "UNAVAILABLE") {
      if (body.reason_codes.length !== 1 || !["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET", "RESPONSE_OVER_BUDGET"].includes(body.reason_codes[0] as string) || body.observation !== null || body.source_observation !== null) return invalid();
      return Object.freeze({ state: "UNAVAILABLE" });
    }
    const bracket = body.source_observation;
    if (body.availability !== "AVAILABLE" || body.reason_codes.length || !object(bracket) || !exact(bracket, ["schema", "state", "selection", "control_room", "runtime"]) || bracket.schema !== "mastermind.workspace_host_observation_source.v1" || bracket.state !== "SAME" || !same(bracket.selection, selected)) return invalid();
    const c = bracket.control_room, r = bracket.runtime;
    if (!object(c) || !exact(c, ["instance_before", "instance_after", "publication_before", "publication_after", "document_digest", "source_validity_digest", "cache_currentness_digest"]) || typeof c.instance_before !== "string" || c.instance_before.length < 1 || c.instance_before.length > 256 || c.instance_after !== c.instance_before || !safe(c.publication_before, 1) || c.publication_after !== c.publication_before || !hash(c.document_digest) || !hash(c.source_validity_digest) || !hash(c.cache_currentness_digest) || !object(r) || !exact(r, ["schema", "state", "source_identity", "before", "after"]) || r.schema !== "mastermind.runtime_read_observation.v1" || r.state !== "SAME" || !match(r.source_identity, /^[0-9a-f]{32}$/) || !safe(r.before) || r.after !== r.before) return invalid();
    return Object.freeze({ state: "AVAILABLE", document: observation(body.observation, selected) });
  } catch { return invalid(); }
}
