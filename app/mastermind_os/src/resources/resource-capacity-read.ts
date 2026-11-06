import { validActivitySelection, type ActivitySelection } from "../planning/retained-activity";
import { decodeRetainedProviderCapacity, type RetainedProviderCapacityState } from "./retained-provider-capacity";
export type ResourceCapacityReadSelection = ActivitySelection;
export type ResourceCapacityRead = Exclude<RetainedProviderCapacityState, { state: "PENDING" }>;
export const validResourceCapacitySelection = validActivitySelection;
const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: readonly string[]) => Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const natural = (v: unknown, minimum = 0): v is number => Number.isSafeInteger(v) && Number(v) >= minimum;
const sameSelection = (v: unknown, selected: ResourceCapacityReadSelection) => record(v) && exact(v, ["work_ref", "root_job_id", "job_id", "attempt_id"]) && Object.entries(selected).every(([k, value]) => v[k] === value);
const hash = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
function invalid(): never { throw new Error("RESOURCE_CAPACITY_INVALID"); }

export function decodeResourceCapacityRead(raw: unknown, selected: ResourceCapacityReadSelection): ResourceCapacityRead {
  if (!validResourceCapacitySelection(selected)) return invalid();
  try { if (new TextEncoder().encode(JSON.stringify({ ok: true, result: raw })).byteLength + 1 > 16_384) return invalid(); }
  catch { return invalid(); }
  if (!record(raw) || !exact(raw, ["schema", "selection", "availability", "reason_codes", "provider_capacity", "source_observation"]) ||
      raw.schema !== "mastermind.workspace_resource_capacity_result.v1" || !sameSelection(raw.selection, selected) || !Array.isArray(raw.reason_codes)) return invalid();
  if (raw.availability === "UNAVAILABLE") {
    if (raw.reason_codes.length !== 1 || !["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET", "RESPONSE_OVER_BUDGET"].includes(raw.reason_codes[0]) || raw.provider_capacity !== null || raw.source_observation !== null) return invalid();
    return Object.freeze({ state: "UNAVAILABLE" });
  }
  if (raw.availability !== "AVAILABLE" || raw.reason_codes.length !== 0) return invalid();
  const observed = raw.source_observation;
  if (!record(observed) || !exact(observed, ["schema", "state", "selection", "control_room", "runtime"]) ||
      observed.schema !== "mastermind.workspace_resource_capacity_observation.v1" || observed.state !== "SAME" || !sameSelection(observed.selection, selected)) return invalid();
  const ccr = observed.control_room, runtime = observed.runtime;
  if (!record(ccr) || !exact(ccr, ["instance_before", "instance_after", "publication_before", "publication_after", "document_digest", "source_validity_digest", "cache_currentness_digest"]) ||
      typeof ccr.instance_before !== "string" || !ccr.instance_before.length || ccr.instance_before.length > 256 || ccr.instance_after !== ccr.instance_before ||
      !natural(ccr.publication_before, 1) || ccr.publication_after !== ccr.publication_before ||
      !hash(ccr.document_digest) || !hash(ccr.source_validity_digest) || !hash(ccr.cache_currentness_digest) ||
      !record(runtime) || !exact(runtime, ["schema", "state", "source_identity", "before", "after"]) ||
      runtime.schema !== "mastermind.runtime_read_observation.v1" || runtime.state !== "SAME" || typeof runtime.source_identity !== "string" || !/^[0-9a-f]{32}$/.test(runtime.source_identity) ||
      !natural(runtime.before) || runtime.after !== runtime.before) return invalid();
  const document = decodeRetainedProviderCapacity(raw.provider_capacity, {
    workRef: selected.work_ref, rootJobId: selected.root_job_id, jobId: selected.job_id, attemptId: selected.attempt_id,
  });
  return Object.freeze({ state: "AVAILABLE", document });
}
