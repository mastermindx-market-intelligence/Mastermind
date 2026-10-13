/** Closed diagnostics presentation; never placement or agent-lifecycle authority. */
export const FLEET_WINDOWS = { "1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000 } as const;
export type FleetWindow = keyof typeof FLEET_WINDOWS;
export const HISTORY_METRICS = ["cpu_temp_c", "cpu_busy_pct", "load1", "memory_used_pct", "fabric_active_lanes"] as const;
export type HistoryMetric = typeof HISTORY_METRICS[number];
const METRICS = ["cpu_busy_pct", "load1", "load5", "logical_cpus", "memory_available_bytes",
  "memory_total_bytes", "memory_used_pct", "swap_used_bytes", "cpu_temp_c", "nvme_temp_c",
  "fan_rpm", "disk_free_bytes", "fabric_active_lanes", "process_lane_candidates", "thermal_advisory_c"] as const;
export type FleetMetrics = Record<typeof METRICS[number], number | null>;
export type FleetHistoryPoint = Record<HistoryMetric, number | null> & { timestamp: number; gaps: HistoryMetric[] };
export interface FleetFinding {
  code: string; severity: "info" | "warning" | "critical"; category: "coverage" | "performance" | "hardware";
  summary: string; detail: string; duration_seconds: number | null;
}
export interface FleetHost {
  id: string; label: string; platform: "macos" | "linux" | "unknown";
  state: "CURRENT" | "STALE" | "OFFLINE" | "UNKNOWN"; observed_at: number | null;
  metrics: FleetMetrics; history: FleetHistoryPoint[]; findings: FleetFinding[]; coverage: string[];
}
export interface FleetHealthDocument {
  schema: "mastermind.fleet_health.v1"; availability: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE";
  generated_at: number; window: FleetWindow; history_truncated: boolean;
  admission_authoritative: false; source: "fabric_host_observer"; hosts: FleetHost[]; reason_codes: string[];
}
export type FleetRead = (request: { window: FleetWindow; signal: AbortSignal }) => Promise<FleetHealthDocument>;

function object(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("shape");
  const result = value as Record<string, unknown>;
  if (Object.keys(result).length !== keys.length || keys.some(key => !Object.hasOwn(result, key))) throw Error("keys");
  return result;
}
function array(value: unknown, max: number): unknown[] {
  if (!Array.isArray(value) || value.length > max) throw Error("array");
  return value;
}
function number(value: unknown, low = 0, high = Number.MAX_SAFE_INTEGER): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < low || value > high) throw Error("number");
  return value;
}
function text(value: unknown, max: number): string {
  if (typeof value !== "string" || !value.length || value.length > max) throw Error("text");
  return value;
}
function choice<T extends string>(value: unknown, values: readonly T[]): T {
  if (typeof value !== "string" || !values.includes(value as T)) throw Error("enum");
  return value as T; // Only a member of this literal set reaches the return.
}
function codes(value: unknown, max = 16): string[] {
  const result = array(value, max).map(value => text(value, 80));
  if (result.some(code => !/^[A-Z][A-Z0-9_]{0,79}$/.test(code)) || new Set(result).size !== result.length) throw Error("codes");
  return result;
}
function metric(key: typeof METRICS[number], value: unknown): number | null {
  if (value === null) return null;
  const high = ["cpu_busy_pct", "memory_used_pct"].includes(key) ? 100 :
    ["cpu_temp_c", "nvme_temp_c", "thermal_advisory_c"].includes(key) ? 150 : Number.MAX_SAFE_INTEGER;
  const result = number(value, key === "logical_cpus" ? 1 : 0, high);
  if (["logical_cpus", "fabric_active_lanes", "process_lane_candidates"].includes(key) && !Number.isSafeInteger(result)) throw Error("integer");
  return result;
}
function measurements(value: unknown): FleetMetrics {
  const m = object(value, METRICS);
  const result: FleetMetrics = {
    cpu_busy_pct: metric("cpu_busy_pct", m.cpu_busy_pct), load1: metric("load1", m.load1), load5: metric("load5", m.load5),
    logical_cpus: metric("logical_cpus", m.logical_cpus), memory_available_bytes: metric("memory_available_bytes", m.memory_available_bytes),
    memory_total_bytes: metric("memory_total_bytes", m.memory_total_bytes), memory_used_pct: metric("memory_used_pct", m.memory_used_pct),
    swap_used_bytes: metric("swap_used_bytes", m.swap_used_bytes), cpu_temp_c: metric("cpu_temp_c", m.cpu_temp_c),
    nvme_temp_c: metric("nvme_temp_c", m.nvme_temp_c), fan_rpm: metric("fan_rpm", m.fan_rpm),
    disk_free_bytes: metric("disk_free_bytes", m.disk_free_bytes), fabric_active_lanes: metric("fabric_active_lanes", m.fabric_active_lanes),
    process_lane_candidates: metric("process_lane_candidates", m.process_lane_candidates), thermal_advisory_c: metric("thermal_advisory_c", m.thermal_advisory_c),
  };
  const { memory_total_bytes: total, memory_available_bytes: available, memory_used_pct: used } = result;
  if (total !== null && available !== null && (total <= 0 || available > total ||
      (used !== null && Math.abs(used - 100 * (1 - available / total)) > 0.1))) throw Error("memory");
  return result;
}
function finding(value: unknown): FleetFinding {
  const f = object(value, ["code", "severity", "category", "summary", "detail", "duration_seconds"]);
  return { code: codes([f.code], 1)[0], severity: choice(f.severity, ["info", "warning", "critical"]),
    category: choice(f.category, ["coverage", "performance", "hardware"]), summary: text(f.summary, 160), detail: text(f.detail, 800),
    duration_seconds: f.duration_seconds === null ? null : number(f.duration_seconds) };
}
function host(value: unknown, now: number, window: FleetWindow): FleetHost {
  const h = object(value, ["id", "label", "platform", "state", "observed_at", "metrics", "history", "findings", "coverage"]);
  const id = text(h.id, 64);
  if (!/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/.test(id)) throw Error("id");
  const state = choice(h.state, ["CURRENT", "STALE", "OFFLINE", "UNKNOWN"]);
  const stamp = h.observed_at === null ? null : number(h.observed_at, 1, now);
  if (state !== "UNKNOWN" && stamp === null) throw Error("observation");
  if (stamp !== null && ((state === "CURRENT" && now - stamp > 180) || (state === "STALE" && now - stamp <= 180))) throw Error("freshness");
  const m = measurements(h.metrics);
  if (["OFFLINE", "UNKNOWN"].includes(state) && Object.values(m).some(v => v !== null)) throw Error("unknown");
  let previous = 0;
  const history = array(h.history, 360).map(value => {
    const p = object(value, ["timestamp", ...HISTORY_METRICS, "gaps"]);
    const timestamp = number(p.timestamp, Math.max(1, now - FLEET_WINDOWS[window]), now);
    if (timestamp <= previous) throw Error("order");
    previous = timestamp;
    const gaps = array(p.gaps, 5).map(k => choice(k, HISTORY_METRICS));
    if (new Set(gaps).size !== gaps.length) throw Error("gaps");
    return { timestamp, cpu_temp_c: metric("cpu_temp_c", p.cpu_temp_c), cpu_busy_pct: metric("cpu_busy_pct", p.cpu_busy_pct),
      load1: metric("load1", p.load1), memory_used_pct: metric("memory_used_pct", p.memory_used_pct),
      fabric_active_lanes: metric("fabric_active_lanes", p.fabric_active_lanes), gaps };
  });
  return { id, label: text(h.label, 100), platform: choice(h.platform, ["macos", "linux", "unknown"]), state,
    observed_at: stamp, metrics: m, history, findings: array(h.findings, 12).map(finding), coverage: codes(h.coverage) };
}

export function decodeFleetHealth(value: unknown, expectedWindow?: FleetWindow): FleetHealthDocument | null {
  try {
    const d = object(value, ["schema", "availability", "generated_at", "window", "history_truncated", "admission_authoritative", "source", "hosts", "reason_codes"]);
    if (d.schema !== "mastermind.fleet_health.v1" || d.source !== "fabric_host_observer" ||
        d.admission_authoritative !== false || typeof d.history_truncated !== "boolean") return null;
    const window = choice(d.window, ["1h", "24h", "7d", "30d"]);
    if (expectedWindow !== undefined && window !== expectedWindow) return null;
    const now = number(d.generated_at, 1);
    const availability = choice(d.availability, ["AVAILABLE", "PARTIAL", "UNAVAILABLE"]);
    const hosts = array(d.hosts, 32).map(value => host(value, now, window));
    const reason_codes = codes(d.reason_codes);
    if (new Set(hosts.map(h => h.id)).size !== hosts.length) return null;
    if (availability === "UNAVAILABLE" ? hosts.length > 0 || reason_codes.length === 0 : hosts.length === 0 || reason_codes.length > 0) return null;
    if (hosts.length && (availability === "AVAILABLE") !== hosts.every(h => h.state === "CURRENT")) return null;
    const result: FleetHealthDocument = { schema: "mastermind.fleet_health.v1", availability, generated_at: now, window,
      history_truncated: d.history_truncated, admission_authoritative: false, source: "fabric_host_observer", hosts, reason_codes };
    if (new TextEncoder().encode(JSON.stringify(result)).byteLength > 1_500_000) return null;
    return result;
  } catch { return null; }
}
