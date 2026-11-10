import { decodeSourceObservation, normalizeResultSelection, type ResultSelection,
  type ResultSourceObservation } from "./result";
import { canonicalJson, parseExecutionReturn, parseExecutionReturnDelivery,
  type ExecutionReturnRecord, type ExecutionReturnDeliveryReceipt } from "./hermes-native/execution-return-contract";

export const EXECUTION_RETURN_READ_SCHEMA = "mastermind.workspace_execution_return.v1";
export const EXECUTION_RETURN_READ_BYTES = 32_768;
const reasons = new Set(["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "OVER_BUDGET", "RESPONSE_OVER_BUDGET"]);

export interface ExecutionReturnReadDocument {
  schema: typeof EXECUTION_RETURN_READ_SCHEMA;
  selection: ResultSourceObservation["selection"];
  availability: "AVAILABLE" | "UNAVAILABLE";
  reason_codes: string[];
  source_observation: ResultSourceObservation;
  execution_return: ExecutionReturnRecord | null;
  delivery_receipt: ExecutionReturnDeliveryReceipt | null;
}

export type ExecutionReturnRead = (request: ResultSelection & { signal: AbortSignal }) => Promise<unknown>;

const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const keys = (value: Record<string, unknown>, expected: string[]) =>
  Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));

/** One same-read snapshot. It does not send, reconcile, consume or accept a return. */
export async function decodeExecutionReturnRead(value: unknown, expected: ResultSelection): Promise<ExecutionReturnReadDocument | null> {
  try {
    const selected = normalizeResultSelection(expected);
    if (!selected || !object(value) || !keys(value, ["schema", "selection", "availability", "reason_codes",
      "source_observation", "execution_return", "delivery_receipt"]) || value.schema !== EXECUTION_RETURN_READ_SCHEMA ||
      new TextEncoder().encode(canonicalJson({ ok: true, result: value })).byteLength + 1 > EXECUTION_RETURN_READ_BYTES) return null;
    const wire = { work_ref: selected.workRef, root_job_id: selected.rootJobId, job_id: selected.jobId,
      attempt_id: selected.attemptId, result_envelope_digest: selected.resultEnvelopeDigest };
    if (!object(value.selection) || !keys(value.selection, Object.keys(wire)) ||
      Object.entries(wire).some(([key, item]) => (value.selection as Record<string, unknown>)[key] !== item) ||
      !Array.isArray(value.reason_codes)) return null;
    if (value.availability !== "AVAILABLE" && value.availability !== "UNAVAILABLE") return null;
    if (value.availability === "UNAVAILABLE") {
      if (value.reason_codes.length !== 1 || !reasons.has(value.reason_codes[0]) ||
        value.execution_return !== null || value.delivery_receipt !== null) return null;
    } else if (value.reason_codes.length !== 0) return null;
    const observation = decodeSourceObservation(value.source_observation, selected, value.availability, value.reason_codes);
    if (!observation) return null;
    const record = value.execution_return === null ? null : await parseExecutionReturn(value.execution_return);
    const receipt = value.delivery_receipt === null ? null : await parseExecutionReturnDelivery(value.delivery_receipt);
    if (record === null ? receipt !== null :
      record.attempt.root_id !== selected.rootJobId || record.attempt.attempt_id !== selected.attemptId ||
      (receipt !== null && (receipt.return_id !== record.return_id || receipt.return_digest !== record.digest ||
        receipt.conversation_id !== record.original_requester.conversation_id))) return null;
    return JSON.parse(canonicalJson({ ...value, source_observation: observation,
      execution_return: record, delivery_receipt: receipt })) as ExecutionReturnReadDocument;
  } catch {
    return null;
  }
}
