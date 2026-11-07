import { decodeProjectPlan, type ProjectPlanSelection } from "./project-plan";
import { decodePlanAdoptionRequest, type PlanAdoptionRequest } from "./plan-adoption-request";

/** Compose request metadata from the actual bounded READ, never a grant or preview.
 * The owner supplies the original ID and must still capture/qualify the exact
 * source bytes, scope and private recipe before returning a real Review slot.
 * No Job, version inference, ID mint, storage or publication is introduced.
 */
export function planAdoptionRequestFromRead(raw: unknown, selection: ProjectPlanSelection,
    proposalId: string, requestId: string): PlanAdoptionRequest {
  try {
    const read = decodeProjectPlan(raw, selection);
    if (read.schema !== "mastermind.workspace_project_plan.v2" || read.availability !== "AVAILABLE") throw Error();
    const { adoption, proposals } = read.continuity;
    if (proposals.state !== "AVAILABLE") throw Error();
    const rows = proposals.items.filter(item => item.state === "RECORDED_PROPOSAL" && item.proposal_id === proposalId);
    if (rows.length !== 1 || rows[0].state !== "RECORDED_PROPOSAL") throw Error();
    const proposal = rows[0];
    // A proposal referenced by the current decision is retained history, not
    // an automatically eligible new adoption. The server independently checks
    // the proposal/current predecessor again against captured owner records.
    if (proposal.adoption_relation !== "UNASSOCIATED_WITH_CURRENT_DECISION" || proposal.comparison.state !== "AVAILABLE") throw Error();
    const expected = adoption.state === "AVAILABLE" ? adoption.decision_ref
      : adoption.reason === "NOT_DECLARED" ? null : undefined;
    if (expected === undefined || proposal.base_adoption !== expected) throw Error();
    return decodePlanAdoptionRequest({ schema: "agentos.plan_adoption_request.v1", request_id: requestId,
      work_ref: selection.work_ref, expected_commit: read.source.commit, expected_adoption: expected,
      proposal_source: proposal.proposal_source, base_source: proposal.base_source,
      candidate_sha256: proposal.candidate_sha256 }, selection.work_ref);
  } catch {
    throw new Error("PLAN_ADOPTION_PREPARATION_UNAVAILABLE");
  }
}
