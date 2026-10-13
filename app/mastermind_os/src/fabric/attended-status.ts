/** Read-only consumer of the installed fabric_task.py status DTO, not an Executive Job. */
export interface AttendedSelection { rootId: string; runId: string }
export const ATTENDED_STATES = ["NOT_FOUND", "STATUS_UNREADABLE", "ACTIVE_OR_WAITING", "EFFECT_UNKNOWN", "RESULT_UNAVAILABLE", "TERMINAL_FAILURE", "TERMINAL", "SETTLING"] as const;
export interface AttendedStatus {
  schema: "mastermind.fabric_task_status.v1";
  run_id: string;
  root_id: string | null;
  parent_run_id: string | null;
  state: typeof ATTENDED_STATES[number];
  rc: number | null;
  signal: string | null;
  result_available: boolean;
  result_bytes: number | null;
  accepted: boolean | null;
  accepted_by: "deterministic" | "reviewer" | "none" | null;
  acceptance_state: "UNVERIFIED" | "NOT_ACCEPTED" | "ACCEPTED";
  acceptance_reason: string;
}
const idPattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const codePattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
export function attendedSelection(value: unknown): AttendedSelection | null {
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  return typeof v.rootId === "string" && idPattern.test(v.rootId) && typeof v.runId === "string" && idPattern.test(v.runId)
    ? { rootId: v.rootId, runId: v.runId } : null;
}
/** Drops optional controller payloads and all unapproved fields, including source content. */
export function decodeAttendedStatus(value: unknown, selected: AttendedSelection): AttendedStatus {
  const refuse = (): never => { throw new Error("FABRIC_STATUS_INVALID"); };
  if (!attendedSelection(selected) || !value || typeof value !== "object" || Array.isArray(value)) return refuse();
  const v = value as Record<string, unknown>;
  const nullableId = (x: unknown) => x === null || typeof x === "string" && idPattern.test(x);
  const nullableCode = (x: unknown) => x === null || typeof x === "string" && codePattern.test(x);
  const nullableBool = (x: unknown) => x === null || typeof x === "boolean";
  if (v.schema !== "mastermind.fabric_task_status.v1" || v.run_id !== selected.runId ||
      !nullableId(v.root_id) || !nullableId(v.parent_run_id) ||
      !ATTENDED_STATES.includes(v.state as AttendedStatus["state"]) ||
      !(v.rc === null || Number.isSafeInteger(v.rc) && Number(v.rc) >= 0 && Number(v.rc) <= 255) || !nullableCode(v.signal) ||
      typeof v.result_available !== "boolean" || (!v.result_available && v.result_bytes !== null) ||
      !(v.result_bytes === null || Number.isSafeInteger(v.result_bytes) && Number(v.result_bytes) >= 0) ||
      !nullableBool(v.accepted) || ![null, "deterministic", "reviewer", "none"].includes(v.accepted_by as never) ||
      !["UNVERIFIED", "NOT_ACCEPTED", "ACCEPTED"].includes(v.acceptance_state as string) ||
      typeof v.acceptance_reason !== "string" || !codePattern.test(v.acceptance_reason)) return refuse();
  if (v.root_id !== null && v.root_id !== selected.rootId) throw new Error("FABRIC_ROOT_MISMATCH");
  const acceptanceState = v.accepted === true ? "ACCEPTED" : v.accepted === false ? "NOT_ACCEPTED" : "UNVERIFIED";
  if (v.acceptance_state !== acceptanceState || v.accepted === null && v.accepted_by !== null ||
      v.accepted === true && (v.state !== "TERMINAL" || v.rc !== 0 || v.signal !== "ok" || !v.result_available || !["deterministic", "reviewer"].includes(v.accepted_by as string) || !v.root_id))
    throw new Error("FABRIC_ACCEPTANCE_CONFLICT");
  return {
    schema: "mastermind.fabric_task_status.v1", run_id: selected.runId,
    root_id: v.root_id as string | null, parent_run_id: v.parent_run_id as string | null,
    state: v.state as AttendedStatus["state"], rc: v.rc as number | null, signal: v.signal as string | null,
    result_available: v.result_available, result_bytes: v.result_bytes as number | null,
    accepted: v.accepted as boolean | null, accepted_by: v.accepted_by as AttendedStatus["accepted_by"],
    acceptance_state: v.acceptance_state as AttendedStatus["acceptance_state"], acceptance_reason: v.acceptance_reason,
  };
}
