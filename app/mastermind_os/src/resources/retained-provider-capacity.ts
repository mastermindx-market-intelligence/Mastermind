/** Safe historical claim projection; this is neither a provider snapshot nor admission. */
export type ResourceCapacitySelection = Readonly<{ workRef: string; rootJobId: string; jobId: string; attemptId: string }>;
export type RetainedProviderCapacity = Readonly<{
  schema: "mastermind.retained_provider_capacity.v1";
  root_job_id: string; job_id: string; attempt_id: string;
  claim_event_id: number; begin_event_id: number; claim_recorded_at_ms: number;
  observed_at_ms: number; age_ms: number;
  source_snapshot_sha256: string; source_release_commit: string;
  host_ref: string; boot_ref: string; provider: "minimax"; provider_enabled: boolean | null;
  realm_auth: Readonly<{ state: "unknown" | "authenticated" | "unauthenticated"; source_quality: "unknown" | "native_provider" }>;
  provider_health: Readonly<{ state: "unknown" | "healthy" | "unhealthy"; error_class: null | "auth" | "quota" | "transport" | "provider" }>;
  cooling: Readonly<{ active: boolean | null; kind: null | "rate_limit" | "provider" | "account"; reset_at: string | null }>;
  quota_horizons: readonly Readonly<{ name: string; remaining: number; limit: number; reset_at: string }>[];
  current_eligibility: "NOT_EVALUATED"; can_place_work: false; observation_kind: "RETAINED_CLAIM";
}>;
export type RetainedProviderCapacityState = { state: "PENDING" } | { state: "UNAVAILABLE" } | { state: "AVAILABLE"; document: RetainedProviderCapacity };
const fields = ["schema", "root_job_id", "job_id", "attempt_id", "claim_event_id", "begin_event_id", "claim_recorded_at_ms", "observed_at_ms", "age_ms", "source_snapshot_sha256", "source_release_commit", "host_ref", "boot_ref", "provider", "provider_enabled", "realm_auth", "provider_health", "cooling", "quota_horizons", "current_eligibility", "can_place_work", "observation_kind"];
const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: readonly string[]) => Object.keys(v).length === keys.length && keys.every(key => Object.hasOwn(v, key));
const id = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(v);
const natural = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0;
const time = (v: unknown): v is string => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) && Number.isFinite(Date.parse(v));
const hash = (v: unknown, length: number): v is string => typeof v === "string" && v.length === length && /^[0-9a-f]+$/.test(v);
function invalid(): never { throw new Error("RETAINED_CAPACITY_INVALID"); }

/** Selection narrows a server-authorized owner read; matching IDs never authorize it. */
export function decodeRetainedProviderCapacity(raw: unknown, selection: ResourceCapacitySelection): RetainedProviderCapacity {
  if (!record(raw) || !exact(raw, fields) || raw.schema !== "mastermind.retained_provider_capacity.v1" ||
      raw.root_job_id !== selection.rootJobId || raw.job_id !== selection.jobId || raw.attempt_id !== selection.attemptId ||
      !id(raw.root_job_id) || !id(raw.job_id) || !id(raw.attempt_id) ||
      !natural(raw.claim_event_id) || raw.claim_event_id < 1 || !natural(raw.begin_event_id) || raw.begin_event_id < 1 ||
      !natural(raw.claim_recorded_at_ms) || !natural(raw.observed_at_ms) || raw.observed_at_ms > 8_640_000_000_000_000 ||
      !natural(raw.age_ms) || !Number.isSafeInteger(raw.observed_at_ms + raw.age_ms) ||
      raw.claim_recorded_at_ms > raw.observed_at_ms + raw.age_ms ||
      !hash(raw.source_snapshot_sha256, 64) || !hash(raw.source_release_commit, 40) ||
      typeof raw.host_ref !== "string" || !raw.host_ref.startsWith("host-") || !hash(raw.host_ref.slice(5), 64) ||
      typeof raw.boot_ref !== "string" || !raw.boot_ref.startsWith("boot-") || !hash(raw.boot_ref.slice(5), 64) ||
      raw.provider !== "minimax" || !(raw.provider_enabled === null || typeof raw.provider_enabled === "boolean") ||
      raw.current_eligibility !== "NOT_EVALUATED" || raw.can_place_work !== false || raw.observation_kind !== "RETAINED_CLAIM") return invalid();
  const auth = raw.realm_auth, health = raw.provider_health, cooling = raw.cooling;
  if (!record(auth) || !exact(auth, ["state", "source_quality"]) || !["unknown", "authenticated", "unauthenticated"].includes(auth.state as string) || !["unknown", "native_provider"].includes(auth.source_quality as string) ||
      !record(health) || !exact(health, ["state", "error_class"]) || !["unknown", "healthy", "unhealthy"].includes(health.state as string) || ![null, "auth", "quota", "transport", "provider"].includes(health.error_class as string | null) ||
      !record(cooling) || !exact(cooling, ["active", "kind", "reset_at"]) || !(cooling.active === null || typeof cooling.active === "boolean") || ![null, "rate_limit", "provider", "account"].includes(cooling.kind as string | null) || !(cooling.reset_at === null || time(cooling.reset_at)) ||
      !Array.isArray(raw.quota_horizons) || raw.quota_horizons.length > 8) return invalid();
  const names = new Set<string>();
  const horizons = raw.quota_horizons.map(row => {
    if (!record(row) || !exact(row, ["name", "remaining", "limit", "reset_at"]) || !id(row.name) || names.has(row.name) || !natural(row.remaining) || !natural(row.limit) || row.limit < 1 || row.remaining > row.limit || !time(row.reset_at)) return invalid();
    names.add(row.name);
    return Object.freeze({ name: row.name, remaining: row.remaining, limit: row.limit, reset_at: row.reset_at });
  });
  return Object.freeze({ ...raw, realm_auth: Object.freeze({ ...auth }), provider_health: Object.freeze({ ...health }), cooling: Object.freeze({ ...cooling }), quota_horizons: Object.freeze(horizons) }) as RetainedProviderCapacity;
}
