/** Consumer of executive_host_capacity.project_native_host_capacity only.
 * Authentication, source custody, expected binding and freshness policy belong
 * to the fixed server reader. Decoding grants no origin or placement authority.
 */
export const capacityBindingFields = ["host_ref", "boot_ref", "capacity_pool_ref", "source_generation_sha256", "execution_scope_sha256", "namespace_sha256", "ancestry_sha256"] as const;
export type HostCapacityBinding = Readonly<Record<typeof capacityBindingFields[number], string>>;
const baseUnits = {
  host_usable_memory_bytes: "bytes_usable", host_available_memory_estimate_bytes: "bytes_estimate",
  host_swap_total_bytes: "bytes", host_swap_used_bytes: "bytes", host_cpu_busy_milli_pct: "milli_percent",
  host_logical_cpu_count: "logical_cpus", effective_cpu_capacity_millicores: "millicores_ceiling",
  effective_memory_headroom_estimate_bytes: "bytes_estimate", disk_usable_bytes: "bytes_unprivileged",
  pool_total_bytes: "bytes", darwin_vm_counters: "not_applicable", darwin_fseventsd: "not_applicable",
  host_cpu_full_pressure: "not_applicable", pswpin_pages_delta: "pages_delta", pswpout_pages_delta: "pages_delta",
} as const;
type PressureMetric = `${"cpu_some" | "memory_some" | "memory_full" | "io_some" | "io_full"}_${"avg10" | "avg60" | "avg300" | "total"}`;
export type CapacityMetricName = keyof typeof baseUnits | PressureMetric;
const units: Readonly<Record<CapacityMetricName, string>> = Object.freeze({ ...baseUnits,
  ...Object.fromEntries(["cpu_some", "memory_some", "memory_full", "io_some", "io_full"].flatMap(prefix =>
    ["avg10", "avg60", "avg300", "total"].map(metric => [`${prefix}_${metric}`, metric === "total" ? "microseconds" : "milli_percent"])))
}) as Readonly<Record<CapacityMetricName, string>>;
const reasons = new Set(["MISSING", "PERMISSION_DENIED", "TIMEOUT", "MALFORMED", "OVERFLOW", "SOURCE_MOVED", "BOOT_DRIFT", "STALE", "FUTURE", "WINDOW_INVALID", "COUNTER_REGRESSION", "NO_COUNTER_DELTA", "NOT_SUPPORTED", "SCOPE_UNQUALIFIED", "MOUNT_MISMATCH"]);
export type CapacityMetric = Readonly<{ value: number | null; null_reason: string | null; unit: string }>;
export type HostCapacityRead = HostCapacityBinding & Readonly<{
  schema: "mastermind.native_host_capacity_read/v1";
  platform: "linux";
  observation_profile: "linux-native-observation/v1";
  observed_at_ms: number;
  sample_window_ms: number;
  total_observation_window_ms: number;
  snapshot_sha256: string;
  metrics: Readonly<Record<CapacityMetricName, CapacityMetric>>;
  telemetry_status: "COMPLETE" | "PARTIAL";
  unknown_fields: readonly CapacityMetricName[];
  capability: "OBSERVATION_ONLY";
  admission_state: "NOT_EVALUATED";
  can_place_work: false;
}>;
export type HostCapacityState = { state: "PENDING" } | { state: "UNAVAILABLE" } | { state: "AVAILABLE"; document: HostCapacityRead };
const fields = ["schema", ...capacityBindingFields, "platform", "observation_profile", "observed_at_ms", "sample_window_ms", "total_observation_window_ms", "snapshot_sha256", "metrics", "telemetry_status", "unknown_fields", "capability", "admission_state", "can_place_work"];
const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: readonly string[]) => Object.keys(v).length === keys.length && keys.every(key => Object.hasOwn(v, key));
const natural = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const digest = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
function invalid(): never { throw new Error("RESOURCE_CAPACITY_INVALID"); }

export function decodeHostCapacityRead(raw: unknown): HostCapacityRead {
  if (!record(raw) || !exact(raw, fields) || raw.schema !== "mastermind.native_host_capacity_read/v1" ||
      raw.platform !== "linux" || raw.observation_profile !== "linux-native-observation/v1" ||
      raw.capability !== "OBSERVATION_ONLY" || raw.admission_state !== "NOT_EVALUATED" || raw.can_place_work !== false ||
      !natural(raw.observed_at_ms) || raw.observed_at_ms > 8_640_000_000_000_000 ||
      !natural(raw.sample_window_ms) || raw.sample_window_ms < 1 || raw.sample_window_ms > 5000 ||
      !natural(raw.total_observation_window_ms) || raw.total_observation_window_ms < raw.sample_window_ms || raw.total_observation_window_ms > 5000 ||
      raw.observed_at_ms < raw.total_observation_window_ms || !digest(raw.snapshot_sha256) || !record(raw.metrics) || !exact(raw.metrics, Object.keys(units)) ||
      !["COMPLETE", "PARTIAL"].includes(raw.telemetry_status as string) || !Array.isArray(raw.unknown_fields)) return invalid();
  for (const field of capacityBindingFields) {
    const value = raw[field];
    if (field === "host_ref" || field === "boot_ref" || field === "capacity_pool_ref") {
      const prefix = field === "host_ref" ? "host-" : field === "boot_ref" ? "boot-" : "capacity-pool-";
      if (typeof value !== "string" || !value.startsWith(prefix) || !digest(value.slice(prefix.length))) return invalid();
    } else if (!digest(value)) return invalid();
  }
  const metrics: Partial<Record<CapacityMetricName, CapacityMetric>> = {};
  const unknown: string[] = [];
  for (const name of Object.keys(units) as CapacityMetricName[]) {
    const metric = raw.metrics[name];
    if (!record(metric) || !exact(metric, ["value", "null_reason", "unit"]) || metric.unit !== units[name]) return invalid();
    if (metric.unit === "not_applicable") {
      if (metric.value !== null || metric.null_reason !== "NOT_APPLICABLE") return invalid();
    } else if (metric.value === null) {
      if (typeof metric.null_reason !== "string" || !reasons.has(metric.null_reason)) return invalid();
      unknown.push(name);
    } else {
      if (!natural(metric.value) || metric.null_reason !== null ||
          metric.unit === "milli_percent" && metric.value > 100_000 ||
          name === "host_logical_cpu_count" && (metric.value < 1 || metric.value > 4096) ||
          name === "host_usable_memory_bytes" && metric.value < 1) return invalid();
    }
    metrics[name] = Object.freeze({ value: metric.value as number | null, null_reason: metric.null_reason as string | null, unit: metric.unit });
  }
  unknown.sort();
  if (raw.unknown_fields.length !== unknown.length || raw.unknown_fields.some((name, i) => name !== unknown[i]) ||
      raw.telemetry_status !== (unknown.length ? "PARTIAL" : "COMPLETE")) return invalid();
  for (const [lower, upper, factor] of [
    ["host_available_memory_estimate_bytes", "host_usable_memory_bytes", 1],
    ["effective_memory_headroom_estimate_bytes", "host_available_memory_estimate_bytes", 1],
    ["effective_cpu_capacity_millicores", "host_logical_cpu_count", 1000],
    ["host_swap_used_bytes", "host_swap_total_bytes", 1], ["disk_usable_bytes", "pool_total_bytes", 1],
  ] as const) {
    const a = metrics[lower]!.value, b = metrics[upper]!.value;
    if (a !== null && b !== null && a > b * factor) return invalid();
  }
  return Object.freeze({ ...raw, metrics: Object.freeze(metrics), unknown_fields: Object.freeze([...unknown]) }) as HostCapacityRead;
}

/** Fixed reader supplies these independently of the received body. Browser
 * selection and a matching digest alone are never a source grant. */
export function qualifyHostCapacityRead(raw: unknown, expected: HostCapacityBinding, nowMs: number, maxAgeMs: number): HostCapacityRead {
  const document = decodeHostCapacityRead(raw);
  if (capacityBindingFields.some(field => document[field] !== expected[field])) throw new Error("RESOURCE_CAPACITY_BINDING_MISMATCH");
  if (!natural(nowMs) || !natural(maxAgeMs) || maxAgeMs < 1 || document.observed_at_ms > nowMs ||
      nowMs - (document.observed_at_ms - document.total_observation_window_ms) > maxAgeMs) throw new Error("RESOURCE_CAPACITY_STALE");
  return document;
}
