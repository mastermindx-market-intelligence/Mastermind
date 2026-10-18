// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { MissionDocument } from "../mission";
import { AdmittedPlanInspector } from "./AdmittedPlanInspector";
import { observePlanWorkers } from "./plan-mission-observation";
import { decodeAdmittedPlan, type PlanSelection } from "./admitted-plan";

afterEach(cleanup);
const selection: PlanSelection = { work_ref: "WS:PLAN-INSPECT", root_job_id: "JOB-333" };
const hash = "a".repeat(64);
const admitted = () => decodeAdmittedPlan({
  schema: "mastermind.workspace_admitted_execution_plan.v1",
  selection, availability: "AVAILABLE", reason_codes: [],
  source_observation: { schema: "mastermind.workspace_plan_observation.v1",
    selection, state: "SAME", control_room: {}, runtime: {} },
  plan: { schema: "mastermind.admitted_execution_plan_view.v1",
    plan_schema_version: "mastermind.execution_plan/v3",
    admission_schema_version: "mastermind.coo_plan_admission/v2",
    root_job_id: selection.root_job_id, plan_attempt_id: "ATT-333",
    policy_sha: hash, plan_digest: hash, reservation_digest: hash,
    admission_state: "ADMITTED",
    steps: [
      { ordinal: 0, step_id: "step-one", objective: "Read source requirements",
        business_impact: "routine", review_required: false, prerequisite_step_ids: [] },
      { ordinal: 1, step_id: "step-two", objective: "Verify exact source behavior",
        business_impact: "material", review_required: true, prerequisite_step_ids: ["step-one"] },
    ],
  },
}, selection);
function mission(jobs: Array<{ job_id: string; plan_step_id: string | null; status?: string }> = [
  { job_id: "JOB-340", plan_step_id: "step-two", status: "RUNNING" },
  { job_id: "JOB-341", plan_step_id: "step-two", status: "COMPLETED" },
]): MissionDocument {
  return {
    program: { work_ref: selection.work_ref },
    mission: { root_job_id: selection.root_job_id, root_job_ambiguous: false, runtime_root_state: "RESOLVED" },
    read_state: { state: "CURRENT" },
    source: { owner_observation: { state: "SAME" } },
    children: { state: "AVAILABLE", coverage: "INCOMPLETE", items: jobs.map(j => ({
      ...j, current_attempt_id: "ATT-" + j.job_id.slice(4), worker_id: "worker-" + j.job_id.slice(4),
    })) },
  } as unknown as MissionDocument;
}
const plan = () => {
  const p = admitted();
  if (p.availability !== "AVAILABLE") throw Error("fixture not admitted");
  return p.plan;
};
describe("independent plan vs Mission worker observations", () => {
  it("associates exact plan_step_id rows but does not promote Job states to plan completion", () => {
    const observations = observePlanWorkers(selection, plan(), mission(), "CURRENT", "2026-10-18T07:00:00Z");
    expect(observations.get("step-one")).toMatchObject({ state: "NO_MATCH_IN_SAMPLE", coverage: "INCOMPLETE", workers: [] });
    expect(observations.get("step-two")).toMatchObject({ state: "OBSERVED", coverage: "INCOMPLETE", omitted: false,
      observed_at: "2026-10-18T07:00:00Z" });
    expect(observations.get("step-two")?.workers.map(x => [x.job_id, x.status])).toEqual([
      ["JOB-340", "RUNNING"], ["JOB-341", "COMPLETED"],
    ]);
    expect(JSON.stringify(observations.get("step-two"))).not.toMatch(/accepted|reviewed|plan_complete/i);
  });
  it("refuses stale, foreign, unqualified and conflicting mission observations without leaking rows", () => {
    const valid = mission();
    const cases: Array<[MissionDocument, string]> = [
      [valid, "STALE"],
      [{ ...valid, mission: { ...valid.mission, root_job_id: "JOB-999" } }, "CURRENT"],
      [{ ...valid, read_state: { ...valid.read_state, state: "HISTORICAL" } }, "CURRENT"],
      [{ ...valid, mission: { ...valid.mission, root_job_ambiguous: true } }, "CURRENT"],
      [{ ...valid, source: { ...valid.source, owner_observation: { ...valid.source.owner_observation!, state: "CONFLICT" } } }, "CURRENT"],
    ];
    for (const [sample, sourceState] of cases) {
      const observations = observePlanWorkers(selection, plan(), sample, sourceState, null);
      expect([...observations.values()].every(x => x.state === "UNAVAILABLE" && x.workers.length === 0)).toBe(true);
    }
  });
  it("keeps source truncation visible instead of inventing global worker coverage", () => {
    const jobs = Array.from({ length: 10 }, (_, index) => ({
      job_id: "JOB-" + (440 + index), plan_step_id: "step-two", status: "RUNNING",
    }));
    const readings = observePlanWorkers(selection, plan(), mission(jobs), "CURRENT", null);
    const assoc = readings.get("step-two");
    expect(assoc).toMatchObject({ state: "OBSERVED", coverage: "INCOMPLETE", omitted: true });
    expect(assoc!.workers).toHaveLength(6);
  });
  it("renders only job observations, separately attributed from admitted-plan steps", async () => {
    const read = vi.fn(async () => admitted());
    render(<AdmittedPlanInspector selection={selection} read={read}
      sourceGeneration={() => 1} canRead={() => true}
      mission={mission()} missionSourceState="CURRENT" missionObservedAt="2026-10-18T07:00:00Z" />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect plan" }));
    expect(await screen.findByText("Verify exact source behavior")).toBeTruthy();
    expect(screen.getAllByText(/Mission jobs \(separate observation\)/)).toHaveLength(1);
    expect(screen.getByText(/Source coverage: INCOMPLETE/)).toBeTruthy();
    expect(screen.getByText(/observed at 2026-10-18T07:00:00Z/)).toBeTruthy();
    expect(screen.getByText(/non-atomic with plan/)).toBeTruthy();
    expect(screen.getByText(/JOB-340/)).toBeTruthy();
    expect(screen.getByText(/JOB-341/)).toBeTruthy();
    expect(screen.getByText(/No associated job in the supplied Mission sample/)).toBeTruthy();
    expect(screen.getByText(/Execution status: not asserted/)).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
  });
  it("withholds worker attribution when Mission is stale despite a valid admitted plan", async () => {
    render(<AdmittedPlanInspector selection={selection} read={async () => admitted()}
      sourceGeneration={() => 1} canRead={() => true}
      mission={mission()} missionSourceState="STALE" />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect plan" }));
    expect(await screen.findByText("Verify exact source behavior")).toBeTruthy();
    expect(screen.queryByText(/JOB-340/)).toBeNull();
  });
});
