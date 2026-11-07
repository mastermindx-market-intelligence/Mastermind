/** Fixed authenticated transport contract. Values carry no admission authority. */
export const planningOperations = ["submit", "status", "result", "consume", "prepare_proposal"] as const;
export type PlanningOperation = typeof planningOperations[number];
export interface ProjectPlanningTransport {
  request(operation: PlanningOperation, arguments_: Readonly<Record<string, unknown>>, signal: AbortSignal): Promise<unknown>;
}
const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" &&
  !Array.isArray(v) && [Object.prototype, null].includes(Object.getPrototypeOf(v));
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v,k));
const text = (v: unknown, pattern: RegExp) => typeof v === "string" && pattern.test(v);
const hex = (v: unknown, count = 64) => typeof v === "string" && new RegExp(`^[0-9a-f]{${count}}$`).test(v);
const id = (v: unknown) => text(v,/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/);

export function planningArguments(operation: PlanningOperation, value: unknown): Readonly<Record<string, unknown>> {
  const fail = (): never => { throw new Error("PROJECT_PLANNING_INPUT_INVALID"); };
  if (!planningOperations.includes(operation) || !record(value)) return fail();
  const keys = ["operation_key","work_ref", ...(operation === "submit" ?
    ["stage","project_source","publication","private_request","grounding"] : operation === "prepare_proposal" ? ["proposal_request"] : operation === "consume" ?
      ["attempt_id","result_digest","consumption_operation_key"] : [])];
  if (!exact(value,keys) || !id(value.operation_key) || !text(value.work_ref,/^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/)) return fail();
  if (operation === "submit") {
    const source=value.project_source, publication=value.publication, grounding=value.grounding;
    if (!["clarify","plan"].includes(String(value.stage)) || typeof value.stage !== "string" ||
      typeof value.private_request !== "string" || !value.private_request.trim() || new TextEncoder().encode(value.private_request).length > 32768 ||
      !record(source) || !exact(source,["repository","commit","path","content_sha256","request_sha256"]) || source.repository !== "macro" ||
      !hex(source.commit,40) || source.path !== `agentos/workstreams/WS-${String(value.work_ref).slice(3)}.md` || !hex(source.content_sha256) || !hex(source.request_sha256) ||
      !record(publication) || !exact(publication,["request_id","principal_scope","event_id","receipt_sha256"]) ||
      !text(publication.request_id,/^mmos-project-create-[0-9a-f]{40}$/) || !hex(publication.principal_scope) || !hex(publication.receipt_sha256) ||
      !Number.isSafeInteger(publication.event_id) || Number(publication.event_id)<=0 ||
      !record(grounding) || !exact(grounding,["mastermind_sha","macro_sha"]) || !hex(grounding.mastermind_sha,40) || !hex(grounding.macro_sha,40)) return fail();
  }
  if(operation === "prepare_proposal") {
    const p=value.proposal_request;
    if(!record(p)||!exact(p,["schema","request_id","work_ref","expected_commit","expected_adoption","base_source","selection","result_digest"])||
      p.schema!=="mastermind.project_plan_proposal_request.v1"||p.work_ref!==value.work_ref||!text(p.request_id,/^mmos-project-plan-proposal-[a-f0-9]{40}$/)||
      !hex(p.expected_commit,40)||!hex(p.result_digest)||!(p.expected_adoption===null||text(p.expected_adoption,/^DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*$/))||
      !record(p.selection)||!exact(p.selection,["work_ref","job_id","attempt_id"])||p.selection.work_ref!==value.work_ref||!id(p.selection.job_id)||!id(p.selection.attempt_id)||
      !record(p.base_source)||!exact(p.base_source,["repository","commit","path","content_sha256"])||p.base_source.repository!=="mastermindx-market-intelligence/macro"||
      !hex(p.base_source.commit,40)||!hex(p.base_source.content_sha256)||!text(p.base_source.path,/^(?:agentos\/workstreams\/WS-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md|research\/project-plans\/[A-Za-z0-9._-]+\.md)$/))return fail();
  }
  if (operation === "consume" && (!id(value.attempt_id) || !hex(value.result_digest) || !id(value.consumption_operation_key))) return fail();
  // Freeze exact input before any asynchronous auth/transport boundary.
  const bytes=JSON.stringify(value);
  if (new TextEncoder().encode(bytes).length > 57344) return fail();
  return JSON.parse(bytes) as Record<string,unknown>;
}
