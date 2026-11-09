/** Public, bounded observation. This is never permission to place or start work. */
export const CAPACITY_FABRIC_SCHEMA = "mastermind.workspace_capacity_fabric.v1";
export type Pressure = "UNKNOWN" | "HEADROOM_RECORDED" | "LOW_ALLOWANCE" | "LIMIT_REACHED" | "COOLDOWN" | "SLOTS_OCCUPIED" | "UNAVAILABLE";
export type QuotaWindow = { window: string; required: boolean; remaining_pct: number | null; observed_at: string | null; reset_at: string | null; state: "CURRENT" | "EXHAUSTED" | "UNKNOWN" | "STALE" | "UNQUALIFIED"; reason: string };
export type CapacityResource = {
  resource_ref: string; provider: string; pool: string; allowance_scope: string | null; identity_qualified: boolean;
  readiness: string; configured_concurrency: number | null; configured_cap_basis: "ACCOUNT" | "POOL" | "UNKNOWN"; active: number | null; queued: number | null;
  cooldown_until: string | null; pressure: Pressure; reason_codes: string[]; windows: QuotaWindow[];
  preview_eligible: boolean | null; single_window_remaining_pct: number | null;
  single_window_observed_at: string | null; single_window_source: "RECORDED_OBSERVATION" | "LOCAL_ESTIMATE" | "UNKNOWN";
};
export type CapacityConsumer = { consumer: "hermes" | "deepseek" | "t3_code" | "website"; source_state: "BUILT" | "SPEC_ONLY"; runtime_state: "NOT_OBSERVED" | "ENROLLED" | "RUNNING" | "RESULT_PROVEN"; observed_at: string | null; evidence_ref: string | null };
export type CapacityAdvice = "UPDATE_USAGE" | "CONSERVE_ALLOWANCE" | "WAIT_FOR_RESET" | "REVIEW_QUEUE" | "REVIEW_ROUTING" | "MEASURE_DEMAND";
export type CapacityFabricDocument = { schema: string; availability: "AVAILABLE"; reason_codes: []; observed_at: string; expires_at: string; source_revision: string; resources: CapacityResource[]; consumers: CapacityConsumer[]; recommendations: CapacityAdvice[]; admission_authorized: false };
export type CapacityFabricRead = { state: "AVAILABLE"; document: CapacityFabricDocument } | { state: "UNAVAILABLE"; reason: string };
type Obj = Record<string, unknown>;
const object = (x: unknown): x is Obj => !!x && typeof x === "object" && !Array.isArray(x);
const exact = (x: Obj, keys: string) => Object.keys(x).length === keys.split(" ").length && keys.split(" ").every(k => Object.hasOwn(x, k));
const token = (x: unknown): x is string => typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9._:+-]{0,159}$/.test(x) && !/xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,}|bearer/i.test(x);
const time = (x: unknown): x is string => typeof x === "string" && x.length <= 40 && /(Z|\+00:00)$/.test(x) && Number.isFinite(Date.parse(x));
const count = (x: unknown) => x === null || (Number.isSafeInteger(x) && (x as number) >= 0 && (x as number) <= 1_000_000);
const pct = (x: unknown) => x === null || typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 100;
const pressures: Pressure[] = ["UNKNOWN", "HEADROOM_RECORDED", "LOW_ALLOWANCE", "LIMIT_REACHED", "COOLDOWN", "SLOTS_OCCUPIED", "UNAVAILABLE"];
const advice: CapacityAdvice[] = ["UPDATE_USAGE", "CONSERVE_ALLOWANCE", "WAIT_FOR_RESET", "REVIEW_QUEUE", "REVIEW_ROUTING", "MEASURE_DEMAND"];
const consumers = ["hermes", "deepseek", "t3_code", "website"];
const invalid = (): CapacityFabricRead => ({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });

export function decodeCapacityFabric(value: unknown, now = Date.now()): CapacityFabricRead {
  try {
    if (!Number.isFinite(now) || now <= 0) return invalid();
    const encoded = JSON.stringify(value);
    if (!encoded || new TextEncoder().encode(encoded).length >= 262_144 || !object(value)
      || !exact(value, "schema availability reason_codes observed_at expires_at source_revision resources consumers recommendations admission_authorized")
      || value.schema !== CAPACITY_FABRIC_SCHEMA || value.admission_authorized !== false) return invalid();
    if (value.availability === "UNAVAILABLE") {
      if (value.observed_at !== null || value.expires_at !== null || value.source_revision !== null
        || ![value.resources, value.consumers, value.recommendations].every(x => Array.isArray(x) && !x.length)
        || !Array.isArray(value.reason_codes) || value.reason_codes.length !== 1
        || !["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_EXPIRED", "RESPONSE_OVER_BUDGET"].includes(value.reason_codes[0])) return invalid();
      return { state: "UNAVAILABLE", reason: value.reason_codes[0] };
    }
    if (value.availability !== "AVAILABLE" || !Array.isArray(value.reason_codes) || value.reason_codes.length
      || !time(value.observed_at) || !time(value.expires_at) || !token(value.source_revision)
      || Date.parse(value.observed_at) > now || Date.parse(value.expires_at) <= Date.parse(value.observed_at)
      || Date.parse(value.expires_at) - Date.parse(value.observed_at) > 900_000) return invalid();
    if (Date.parse(value.expires_at) <= now) return { state: "UNAVAILABLE", reason: "SOURCE_EXPIRED" };
    if (!Array.isArray(value.resources) || value.resources.length > 256) return invalid();
    const refs = new Set<string>();
    for (const row of value.resources) {
      if (!object(row) || !exact(row, "resource_ref provider pool allowance_scope identity_qualified readiness configured_concurrency configured_cap_basis active queued cooldown_until pressure reason_codes windows preview_eligible single_window_remaining_pct single_window_observed_at single_window_source")
        || !token(row.resource_ref) || !token(row.provider) || !token(row.pool) || !token(row.readiness) || refs.has(row.resource_ref)
        || !(row.allowance_scope === null || token(row.allowance_scope)) || typeof row.identity_qualified !== "boolean"
        || row.identity_qualified !== (row.allowance_scope !== null) || ![row.configured_concurrency, row.active, row.queued].every(count)
        || !["ACCOUNT", "POOL", "UNKNOWN"].includes(row.configured_cap_basis as string)
        || !(row.cooldown_until === null || time(row.cooldown_until)) || !pressures.includes(row.pressure as Pressure)
        || !(row.preview_eligible === null || typeof row.preview_eligible === "boolean") || !pct(row.single_window_remaining_pct)
        || !["RECORDED_OBSERVATION", "LOCAL_ESTIMATE", "UNKNOWN"].includes(row.single_window_source as string)
        || !Array.isArray(row.reason_codes) || row.reason_codes.length > 20 || !row.reason_codes.every(token)
        || !Array.isArray(row.windows) || !row.windows.length || row.windows.length > 16) return invalid();
      if (row.single_window_remaining_pct === null ? row.single_window_observed_at !== null
        : !time(row.single_window_observed_at) || row.single_window_source === "UNKNOWN"
          || Date.parse(row.single_window_observed_at) > now || now - Date.parse(row.single_window_observed_at) >= 600_000
          || Date.parse(value.expires_at) - Date.parse(row.single_window_observed_at) > 600_000) return invalid();
      refs.add(row.resource_ref);
      const names = new Set<string>();
      for (const w of row.windows) {
        if (!object(w) || !exact(w, "window required remaining_pct observed_at reset_at state reason") || !token(w.window) || names.has(w.window)
          || typeof w.required !== "boolean" || !pct(w.remaining_pct) || !token(w.reason)
          || !(w.observed_at === null || time(w.observed_at)) || !(w.reset_at === null || time(w.reset_at))
          || !["CURRENT", "EXHAUSTED", "UNKNOWN", "STALE", "UNQUALIFIED"].includes(w.state as string)) return invalid();
        names.add(w.window);
        if (w.state === "CURRENT" || w.state === "EXHAUSTED") {
          if (w.remaining_pct === null || !time(w.observed_at) || (w.state === "EXHAUSTED") !== (w.remaining_pct === 0)
            || Date.parse(w.observed_at) > now || now - Date.parse(w.observed_at) >= 600_000
            || Date.parse(value.expires_at) - Date.parse(w.observed_at) > 600_000
            || w.reset_at !== null && Date.parse(value.expires_at) > Date.parse(w.reset_at as string)
            || w.reset_at !== null && Date.parse(w.reset_at as string) <= now) return invalid();
        } else if (w.remaining_pct !== null) return invalid();
      }
    }
    if (!Array.isArray(value.consumers) || value.consumers.length !== consumers.length) return invalid();
    for (const [i, row] of value.consumers.entries()) {
      if (!object(row) || !exact(row, "consumer source_state runtime_state observed_at evidence_ref") || row.consumer !== consumers[i]
        || !["BUILT", "SPEC_ONLY"].includes(row.source_state as string)
        || !["NOT_OBSERVED", "ENROLLED", "RUNNING", "RESULT_PROVEN"].includes(row.runtime_state as string)) return invalid();
      if (row.runtime_state === "NOT_OBSERVED") {
        if (row.observed_at !== null || row.evidence_ref !== null) return invalid();
      } else if (!time(row.observed_at) || Date.parse(row.observed_at) > now || !token(row.evidence_ref)
        || Date.parse(value.expires_at) - Date.parse(row.observed_at) > 900_000) return invalid();
    }
    if (!Array.isArray(value.recommendations) || value.recommendations.length > 6 || new Set(value.recommendations).size !== value.recommendations.length
      || !value.recommendations.every(x => advice.includes(x))) return invalid();
    // Detach the validated observation from a mutable transport object.
    return { state: "AVAILABLE", document: JSON.parse(encoded) as CapacityFabricDocument };
  } catch { return invalid(); }
}

export function capacitySummary(document: CapacityFabricDocument) {
  const constrained = document.resources.filter(row => ["LIMIT_REACHED", "COOLDOWN", "SLOTS_OCCUPIED", "LOW_ALLOWANCE"].includes(row.pressure)).length;
  const unknown = document.resources.filter(row => row.pressure === "UNKNOWN").length;
  const shared = new Set(document.resources.filter(row => row.identity_qualified).map(row => row.allowance_scope));
  return { constrained, unknown, qualifiedAllowances: shared.size };
}
