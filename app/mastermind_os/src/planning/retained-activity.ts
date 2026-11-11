/** Passive original Executive OHF retained-event metadata, never provider reasoning.
 * The original Workspace HTTP + COO + Runtime owners authorize and coarsen;
 * this strict client refuses any extra fields before presentation.
 */
export const ACTIVITY_BODY_SCHEMA = "mastermind.workspace_retained_activity.v1";
export const ACTIVITY_VIEW_SCHEMA = "mastermind.operator_retained_activity_metadata.v1";
export const ACTIVITY_OBSERVATION_SCHEMA = "mastermind.workspace_retained_activity_observation.v1";
export interface ActivitySelection {
  work_ref: string; root_job_id: string; job_id: string; attempt_id: string;
}
export interface ActivityRow {
  candidate_event_id: number; turn_id: string; ordinal_in_candidate: number;
  category: "TURN_COMPLETED" | "TURN_ACTIVITY" | "ITEM_ACTIVITY" | "TOOL_ACTIVITY" |
    "MODEL_ACTIVITY" | "OTHER_REDACTED_EVENT";
  candidate_recorded_at: string;
}
export type ActivityRead =
  | { availability: "AVAILABLE"; selection: ActivitySelection;
      sourceState: "SAME"; coverage: "RETAINED" | "PARTIAL" | "NO_RETAINED_CANDIDATES";
      sourceTruncated: boolean; omittedInSample: number; rows: ActivityRow[]; }
  | { availability: "UNAVAILABLE"; selection: ActivitySelection;
      sourceState: "UNKNOWN" | "CONFLICT"; coverage: null; sourceTruncated: null;
      omittedInSample: null; rows: []; reasons: string[]; };

const keys = (value: Record<string, unknown>, expected: string[]) =>
  Object.keys(value).length === expected.length && expected.every(k => Object.hasOwn(value, k));
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const id = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const sha = /^[0-9a-f]{64}$/;
const identity = /^[0-9a-f]{32}$/;
const stamp = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)$/;
const reason = new Set(["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET", "RESPONSE_OVER_BUDGET"]);
const category = new Set(["TURN_COMPLETED","TURN_ACTIVITY","ITEM_ACTIVITY","TOOL_ACTIVITY","MODEL_ACTIVITY","OTHER_REDACTED_EVENT"]);
const refuse = (): never => { throw new Error("RETAINED_ACTIVITY_INVALID"); };

export function validActivitySelection(value: unknown): value is ActivitySelection {
  if (!record(value) || !keys(value, ["work_ref","root_job_id","job_id","attempt_id"])) return false;
  return typeof value.work_ref === "string" && /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(value.work_ref) &&
    typeof value.root_job_id === "string" && /^JOB-[0-9]{1,9}$/.test(value.root_job_id) &&
    typeof value.job_id === "string" && /^JOB-[0-9]{1,9}$/.test(value.job_id) &&
    value.job_id !== value.root_job_id && typeof value.attempt_id === "string" &&
    /^ATT-[0-9a-f]{32}$/.test(value.attempt_id);
}

/** Detached 32-row allowlisted display only, not a new authority or transcript store. */
export function decodeRetainedActivity(raw: unknown, selected: ActivitySelection): ActivityRead {
  if (!validActivitySelection(selected) || !record(raw) ||
      !keys(raw, ["schema","selection","availability","reason_codes","activity","source_observation"]) ||
      raw.schema !== ACTIVITY_BODY_SCHEMA || !validActivitySelection(raw.selection) ||
      Object.keys(selected).some(k => (raw.selection as Record<string, string>)[k] !== (selected as unknown as Record<string, string>)[k]) ||
      !Array.isArray(raw.reason_codes) || !record(raw.source_observation)) return refuse();
  const obs = raw.source_observation;
  if (!keys(obs, ["schema","state","selection","control_room","runtime"]) ||
      obs.schema !== ACTIVITY_OBSERVATION_SCHEMA || !validActivitySelection(obs.selection) ||
      Object.keys(selected).some(k => (obs.selection as Record<string, string>)[k] !== (selected as unknown as Record<string, string>)[k])) return refuse();
  if (raw.availability === "UNAVAILABLE") {
    if (raw.activity !== null || raw.reason_codes.length !== 1 ||
        !reason.has(raw.reason_codes[0]) ||
        (obs.state !== "UNKNOWN" && obs.state !== "CONFLICT") ||
        (obs.state === "CONFLICT") !== (raw.reason_codes[0] === "SOURCE_CHANGED") ||
        obs.control_room !== null || obs.runtime !== null) return refuse();
    return { availability:"UNAVAILABLE", selection:{...selected}, sourceState:obs.state,
      coverage:null, sourceTruncated:null, omittedInSample:null, rows:[], reasons:[raw.reason_codes[0]] };
  }
  if (raw.availability !== "AVAILABLE" || raw.reason_codes.length !== 0 || !record(raw.activity) ||
      obs.state !== "SAME" || !record(obs.control_room) || !record(obs.runtime)) return refuse();
  const view = raw.activity, source = view.source;
  if (!keys(view, ["schema","selection","availability","source","candidate_receipts_in_sample",
                    "normalized_events_in_sample","omitted_in_sample","rows"]) ||
      view.schema !== ACTIVITY_VIEW_SCHEMA || !validActivitySelection(view.selection) ||
      Object.keys(selected).some(k => (view.selection as Record<string,string>)[k] !== (selected as unknown as Record<string,string>)[k]) ||
      !["RETAINED","PARTIAL","NO_RETAINED_CANDIDATES"].includes(String(view.availability)) ||
      !record(source) || !keys(source, ["state","scope","source_truncated","live_worker_count","global_event_total"]) ||
      source.state !== "SAME_AS_OF_READ" || source.scope !== "RETAINED_CANDIDATES_ONLY" ||
      typeof source.source_truncated !== "boolean" || source.live_worker_count !== null || source.global_event_total !== null ||
      !Array.isArray(view.rows) || view.rows.length > 32 ||
      !Number.isInteger(view.candidate_receipts_in_sample) || Number(view.candidate_receipts_in_sample) > 64 ||
      !Number.isInteger(view.normalized_events_in_sample) || !Number.isInteger(view.omitted_in_sample) ||
      Number(view.omitted_in_sample) < 0 ||
      Number(view.normalized_events_in_sample) !== view.rows.length + Number(view.omitted_in_sample)) return refuse();
  const runtime = obs.runtime, ccr = obs.control_room;
  if (!keys(runtime, ["schema","state","source_identity","before","after"]) ||
      runtime.schema !== "mastermind.runtime_read_observation.v1" || runtime.state !== "SAME" ||
      typeof runtime.source_identity !== "string" || !identity.test(runtime.source_identity) ||
      !Number.isInteger(runtime.before) || Number(runtime.before) < 0 || runtime.before !== runtime.after ||
      !keys(ccr, ["instance_before","instance_after","publication_before","publication_after",
                    "document_digest","source_validity_digest","cache_currentness_digest"]) ||
      !Number.isInteger(ccr.publication_before) || Number(ccr.publication_before) <= 0 ||
      ccr.publication_before !== ccr.publication_after ||
      ["document_digest","source_validity_digest","cache_currentness_digest"].some(k => typeof ccr[k] !== "string" || !sha.test(ccr[k] as string))) return refuse();
  const rows: ActivityRow[] = [];
  for (const value of view.rows) {
    if (!record(value) || !keys(value, ["candidate_event_id","turn_id","ordinal_in_candidate","category","candidate_recorded_at"]) ||
        !Number.isInteger(value.candidate_event_id) || Number(value.candidate_event_id) <= 0 ||
        typeof value.turn_id !== "string" || !id.test(value.turn_id) ||
        !Number.isInteger(value.ordinal_in_candidate) || Number(value.ordinal_in_candidate) < 0 ||
        Number(value.ordinal_in_candidate) > 255 || !category.has(value.category as string) ||
        typeof value.candidate_recorded_at !== "string" || !stamp.test(value.candidate_recorded_at)) return refuse();
    rows.push({ candidate_event_id:value.candidate_event_id as number, turn_id:value.turn_id,
      ordinal_in_candidate:value.ordinal_in_candidate as number, category:value.category as ActivityRow["category"],
      candidate_recorded_at:value.candidate_recorded_at });
  }
  if (view.availability === "NO_RETAINED_CANDIDATES" && rows.length > 0) return refuse();
  return { availability:"AVAILABLE", selection:{...selected}, sourceState:"SAME",
    coverage:view.availability as "RETAINED" | "PARTIAL" | "NO_RETAINED_CANDIDATES",
    sourceTruncated:source.source_truncated as boolean,
    omittedInSample:view.omitted_in_sample as number, rows };
}
