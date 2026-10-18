/** Closed, read-only consumer of the existing authenticated Workspace admitted-plan route.
 * Admission is NOT worker START, progress, review, publication or acceptance.
 * No request, source owner, event store or authorization decision is created here.
 */
export const PLAN_BODY_SCHEMA = "mastermind.workspace_admitted_execution_plan.v1";
export const PLAN_VIEW_SCHEMA = "mastermind.admitted_execution_plan_view.v1";
export const PLAN_OBSERVATION_SCHEMA = "mastermind.workspace_plan_observation.v1";
export interface PlanSelection { work_ref: string; root_job_id: string }
export interface AdmittedStep {
  ordinal: number;
  step_id: string;
  objective: string;
  business_impact: "routine" | "material" | "critical";
  review_required: boolean;
  prerequisite_step_ids: string[];
}
export interface AdmittedPlan {
  schema: typeof PLAN_VIEW_SCHEMA;
  root_job_id: string;
  plan_attempt_id: string;
  plan_digest: string;
  policy_sha: string;
  reservation_digest: string;
  plan_schema_version: string;
  admission_schema_version: string;
  admission_state: "ADMITTED";
  steps: AdmittedStep[];
}
export type PlanRead =
  | { availability: "AVAILABLE"; selection: PlanSelection; plan: AdmittedPlan; observation: "SAME"; reason_codes: [] }
  | { availability: "UNAVAILABLE"; selection: PlanSelection; plan: null; observation: "UNKNOWN" | "CONFLICT"; reason_codes: string[] };
const id = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const sha = /^[0-9a-f]{64}$/;
const knownReasons = new Set(["ADMISSION_NOT_ESTABLISHED", "ADMISSION_CONFLICT", "SOURCE_CHANGED",
  "SOURCE_UNAVAILABLE", "OVER_BUDGET", "CONTENT_WITHHELD", "CONTENT_OVER_BUDGET", "RESPONSE_OVER_BUDGET"]);
const keys = (v: Record<string, unknown>, expected: string[]) =>
  Object.keys(v).length === expected.length && expected.every(key => Object.hasOwn(v, key));
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isId = (v: unknown): v is string => typeof v === "string" && id.test(v);
const isDigest = (v: unknown): v is string => typeof v === "string" && sha.test(v);
const refuse = (): never => { throw new Error("ADMITTED_PLAN_INVALID"); };

export function validPlanSelection(value: unknown): value is PlanSelection {
  if (!record(value) || !keys(value, ["work_ref", "root_job_id"])) return false;
  return typeof value.work_ref === "string" && value.work_ref.length <= 128 &&
    /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(value.work_ref) &&
    typeof value.root_job_id === "string" && /^JOB-[0-9]{1,9}$/.test(value.root_job_id);
}

/** The caller already acquired an authorized owner document; never decode raw provider output. */
export function decodeAdmittedPlan(value: unknown, expected: PlanSelection): PlanRead {
  if (!validPlanSelection(expected) || !record(value) ||
      !keys(value, ["schema", "selection", "availability", "reason_codes", "source_observation", "plan"]) ||
      value.schema !== PLAN_BODY_SCHEMA || !validPlanSelection(value.selection) ||
      value.selection.work_ref !== expected.work_ref || value.selection.root_job_id !== expected.root_job_id ||
      !Array.isArray(value.reason_codes) || !record(value.source_observation)) return refuse();
  const obs = value.source_observation;
  if (obs.schema !== PLAN_OBSERVATION_SCHEMA || !validPlanSelection(obs.selection) ||
      obs.selection.work_ref !== expected.work_ref || obs.selection.root_job_id !== expected.root_job_id ||
      !["SAME", "UNKNOWN", "CONFLICT"].includes(String(obs.state))) return refuse();
  if (value.availability === "UNAVAILABLE") {
    if (value.plan !== null || value.reason_codes.length !== 1 ||
        !knownReasons.has(value.reason_codes[0]) ||
        obs.state === "SAME" ||
        (value.reason_codes[0] === "SOURCE_CHANGED") !== (obs.state === "CONFLICT")) return refuse();
    return { availability: "UNAVAILABLE", selection: { ...expected }, plan: null,
      observation: obs.state as "UNKNOWN" | "CONFLICT", reason_codes: [value.reason_codes[0]] };
  }
  if (value.availability !== "AVAILABLE" || value.reason_codes.length !== 0 ||
      obs.state !== "SAME" || !record(value.plan)) return refuse();
  const plan = value.plan;
  if (!keys(plan, ["schema", "plan_schema_version", "admission_schema_version",
      "root_job_id", "plan_attempt_id", "policy_sha", "plan_digest", "reservation_digest",
      "admission_state", "steps"]) ||
      plan.schema !== PLAN_VIEW_SCHEMA || plan.root_job_id !== expected.root_job_id ||
      !isId(plan.plan_attempt_id) || !isDigest(plan.policy_sha) ||
      !isDigest(plan.plan_digest) || !isDigest(plan.reservation_digest) ||
      plan.admission_state !== "ADMITTED" ||
      !["mastermind.execution_plan/v1", "mastermind.execution_plan/v2",
        "mastermind.execution_plan/v3", "mastermind.execution_plan/v4"].includes(String(plan.plan_schema_version)) ||
      !["mastermind.coo_plan_admission/v1", "mastermind.coo_plan_admission/v2"].includes(String(plan.admission_schema_version)) ||
      !Array.isArray(plan.steps) || plan.steps.length < 1 || plan.steps.length > 8) return refuse();
  const dependencyPlan = plan.plan_schema_version === "mastermind.execution_plan/v3" ||
    plan.plan_schema_version === "mastermind.execution_plan/v4";
  if (plan.admission_schema_version !== (dependencyPlan ? "mastermind.coo_plan_admission/v2" : "mastermind.coo_plan_admission/v1")) return refuse();
  const seen = new Set<string>();
  const steps: AdmittedStep[] = [];
  for (let i = 0; i < plan.steps.length; i++) {
    const step = plan.steps[i];
    if (!record(step) || !keys(step, ["ordinal", "step_id", "objective", "business_impact",
        "review_required", "prerequisite_step_ids"]) ||
        step.ordinal !== i || !isId(step.step_id) || seen.has(step.step_id) ||
        typeof step.objective !== "string" || !step.objective.length || step.objective.length > 4096 ||
        !["routine", "material", "critical"].includes(String(step.business_impact)) ||
        typeof step.review_required !== "boolean" ||
        !Array.isArray(step.prerequisite_step_ids) || step.prerequisite_step_ids.length > 8 ||
        !step.prerequisite_step_ids.every((d: unknown) => isId(d) && seen.has(d)) ||
        new Set(step.prerequisite_step_ids).size !== step.prerequisite_step_ids.length ||
        (!dependencyPlan && step.prerequisite_step_ids.length !== 0)) return refuse();
    steps.push({ ordinal: i, step_id: step.step_id, objective: step.objective,
      business_impact: step.business_impact as AdmittedStep["business_impact"],
      review_required: step.review_required, prerequisite_step_ids: [...step.prerequisite_step_ids] });
    seen.add(step.step_id);
  }
  return {
    availability: "AVAILABLE", selection: { ...expected }, observation: "SAME", reason_codes: [],
    plan: { schema: PLAN_VIEW_SCHEMA, root_job_id: expected.root_job_id,
      plan_attempt_id: plan.plan_attempt_id as string, plan_digest: plan.plan_digest as string,
      policy_sha: plan.policy_sha as string, reservation_digest: plan.reservation_digest as string,
      plan_schema_version: plan.plan_schema_version as string,
      admission_schema_version: plan.admission_schema_version as string,
      admission_state: "ADMITTED", steps },
  };
}
