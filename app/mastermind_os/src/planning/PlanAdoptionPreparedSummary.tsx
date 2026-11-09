import type {
  PlanAdoptionPreview,
  PreparedPlanAdoption,
} from "./plan-adoption-port";
import type { PlanAdoptionPrepared } from "./PlanAdoptionReview";
import { canonicalJson } from "../orchestration/operation-key";
import { planAdoptionRequestFromRead } from "./plan-adoption-from-read";
import { decodeProjectPlan, type ProjectPlanSelection } from "./project-plan";
import { ProjectPlanContinuity } from "./ProjectPlanContinuity";

/** Only a closed, qualified owner summary; no private recipe/body/actor is rendered. */
export function PlanAdoptionPreparedSummary({
  preview,
  locale = "en",
}: {
  preview: PlanAdoptionPreview;
  locale?: "en" | "zh-CN";
}) {
  const zh = locale === "zh-CN";
  return (
    <div lang={locale}>
      <p>
        {zh
          ? `此提案将更改 ${preview.changed_frontmatter_fields.length} 个记录字段。`
          : `This proposal changes ${preview.changed_frontmatter_fields.length} recorded ${preview.changed_frontmatter_fields.length === 1 ? "field" : "fields"}.`}
      </p>
      <p>
        {preview.record_body_changed
          ? zh
            ? "计划正文将更改。"
            : "The plan’s recorded text changes."
          : zh
            ? "计划正文保持不变。"
            : "The plan’s recorded text stays the same."}
      </p>
      <details className="mm-plan-adoption__ids">
        <summary>{zh ? "更改的记录字段" : "Changed record fields"}</summary>
        {preview.changed_frontmatter_fields.length > 0 ? (
          <ul>
            {preview.changed_frontmatter_fields.map((field) => (
              <li key={field}>
                <code>{field}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p>{zh ? "没有记录字段更改。" : "No recorded fields change."}</p>
        )}
      </details>
    </div>
  );
}

/** Bridges an actual qualified prepare result into the incumbent Review slot.
 * isCurrent must fence the selected READ/source and authentication epoch; it is
 * evaluated by Review before initial adoption, never used to replace recovery.
 */
export function planAdoptionPreparedReview(
  prepared: PreparedPlanAdoption,
  input: {
    read: unknown;
    selection: ProjectPlanSelection;
    proposalId: string;
    isCurrent: () => boolean;
    canReadComparison: () => boolean;
    locale?: "en" | "zh-CN";
  },
): PlanAdoptionPrepared {
  const locale = input.locale ?? "en";
  let read;
  try {
    if (!input.canReadComparison() || !input.isCurrent()) throw Error();
    const request = planAdoptionRequestFromRead(
      input.read,
      input.selection,
      input.proposalId,
      prepared.request.request_id,
    );
    if (canonicalJson(request) !== canonicalJson(prepared.request))
      throw Error();
    read = decodeProjectPlan(input.read, input.selection);
    if (
      read.schema !== "mastermind.workspace_project_plan.v2" ||
      read.availability !== "AVAILABLE" ||
      read.continuity.proposals.state !== "AVAILABLE"
    )
      throw Error();
  } catch {
    throw new Error("PLAN_ADOPTION_REVIEW_UNAVAILABLE");
  }
  const data = {
    ...read.continuity,
    proposals: {
      ...read.continuity.proposals,
      items: read.continuity.proposals.items.filter(
        (row) =>
          row.state === "RECORDED_PROPOSAL" &&
          row.proposal_id === input.proposalId,
      ),
    },
  };
  return {
    request: prepared.request,
    preview: (
      <>
        <PlanAdoptionPreparedSummary
          preview={prepared.preview}
          locale={locale}
        />
        <ProjectPlanContinuity data={data} locale={locale} />
      </>
    ),
    isCurrent: () => input.canReadComparison() && input.isCurrent(),
  };
}
