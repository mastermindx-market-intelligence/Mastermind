/** Exact direct-native correction DATA. Request acknowledgment is not settlement. */
import { canonicalJson, sha256Hex } from "./orchestration/operation-key";
import {
  normalizeDirectSelection,
  type DirectSelection,
  type DirectTerminalSelection,
} from "./direct-native-result";
export type DirectCorrection = {
  schema: "mastermind.direct_native_correction.v1";
  selection: DirectTerminalSelection;
  fence_generation: number;
  operation_key: string | null;
  status:
    | "RUNNING"
    | "CHECKPOINTED"
    | "CANCEL_REQUESTED"
    | "CANCELLED"
    | "COMPLETED"
    | "FAILED"
    | "LOST"
    | "RATE_LIMITED";
  parent_consumed: false;
};
const statuses = new Set([
  "RUNNING",
  "CHECKPOINTED",
  "CANCEL_REQUESTED",
  "CANCELLED",
  "COMPLETED",
  "FAILED",
  "LOST",
  "RATE_LIMITED",
]);
export function decodeDirectCorrection(
  value: unknown,
  expected: DirectSelection,
): DirectCorrection | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  if (
    Object.keys(v).sort().join(",") !==
      "fence_generation,operation_key,parent_consumed,schema,selection,status" ||
    v.schema !== "mastermind.direct_native_correction.v1" ||
    v.parent_consumed !== false
  )
    return null;
  const s = normalizeDirectSelection(v.selection);
  if (
    !s ||
    s.attempt_id === null ||
    s.work_ref !== expected.work_ref ||
    s.job_id !== expected.job_id ||
    (expected.attempt_id !== null && s.attempt_id !== expected.attempt_id) ||
    !Number.isSafeInteger(v.fence_generation) ||
    (v.fence_generation as number) < 1 ||
    typeof v.status !== "string" ||
    !statuses.has(v.status) ||
    !(
      v.operation_key === null ||
      (typeof v.operation_key === "string" &&
        /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(v.operation_key))
    )
  )
    return null;
  return { ...v, selection: s } as DirectCorrection;
}
export function correctionIdentity(
  scope: string,
  selection: DirectTerminalSelection,
  fence: number,
) {
  if (
    !/^[a-f0-9]{64}$/.test(scope) ||
    !normalizeDirectSelection(selection) ||
    selection.attempt_id === null ||
    !Number.isSafeInteger(fence) ||
    fence < 1
  )
    throw Error("DIRECT_CORRECTION_INVALID");
  const target = { ...selection, fence_generation: fence };
  return {
    kind: "stop" as const,
    targetKey: canonicalJson(target),
    operationKey: `mmos-correct-${sha256Hex(canonicalJson({ principal_scope: scope, ...target })).slice(0, 40)}`,
  };
}
export function parseCorrectionTarget(
  raw: string | null,
): (DirectTerminalSelection & { fence_generation: number }) | null {
  try {
    const v = JSON.parse(raw ?? "null");
    if (
      !v ||
      typeof v !== "object" ||
      Object.keys(v).sort().join(",") !==
        "attempt_id,fence_generation,job_id,work_ref"
    )
      return null;
    const { fence_generation, ...selected } = v,
      s = normalizeDirectSelection(selected);
    if (
      !s ||
      s.attempt_id === null ||
      !Number.isSafeInteger(fence_generation) ||
      fence_generation < 1
    )
      return null;
    return { ...s, attempt_id: s.attempt_id, fence_generation };
  } catch {
    return null;
  }
}
