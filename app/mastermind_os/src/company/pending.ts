import { canonicalJson } from "../orchestration/operation-key";
import type { OperationPointer } from "../orchestration/operation-controller";

const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/;
const scope = /^[0-9a-f]{64}$/;
export interface CompanyPendingTarget {
  readonly company_id: string;
  readonly principal_scope: string;
  readonly request_id: string;
}
/** An original-source lookup in the existing pointer store; never a payload or grant. */
export function readCompanyPending(
  pointer: OperationPointer,
  expectedScope?: string,
): CompanyPendingTarget | null {
  if (
    pointer.kind !== "project_source_write" ||
    typeof pointer.targetKey !== "string" ||
    pointer.targetKey.length > 300
  )
    return null;
  try {
    const target = JSON.parse(pointer.targetKey) as CompanyPendingTarget;
    if (
      target === null ||
      typeof target !== "object" ||
      Array.isArray(target) ||
      Object.keys(target).length !== 3 ||
      typeof target.company_id !== "string" ||
      !uuid.test(target.company_id) ||
      typeof target.principal_scope !== "string" ||
      !scope.test(target.principal_scope) ||
      typeof target.request_id !== "string" ||
      !uuid.test(target.request_id) ||
      (expectedScope !== undefined &&
        target.principal_scope !== expectedScope) ||
      pointer.operationKey !==
        `mmos-paperclip-backlog-${target.request_id.replaceAll("-", "")}` ||
      canonicalJson(target) !== pointer.targetKey
    )
      return null;
    return Object.freeze(target);
  } catch {
    return null;
  }
}
export function companyPendingPointer(
  companyId: string,
  principalScope: string,
  requestId: string,
): OperationPointer {
  const result: OperationPointer = Object.freeze({
    kind: "project_source_write",
    operationKey: `mmos-paperclip-backlog-${requestId.replaceAll("-", "")}`,
    targetKey: canonicalJson({
      company_id: companyId,
      principal_scope: principalScope,
      request_id: requestId,
    }),
  });
  if (!readCompanyPending(result, principalScope))
    throw new Error("COMPANY_PENDING_INVALID");
  return result;
}
