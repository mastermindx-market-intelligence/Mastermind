import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
afterEach(() => cleanup());
import { AdmittedPlanInspector } from "./AdmittedPlanInspector";
import { decodeAdmittedPlan, type PlanSelection } from "./admitted-plan";

const selection: PlanSelection = { work_ref: "WS:PLAN-VISIBILITY", root_job_id: "JOB-123" };
const digest = "a".repeat(64);
function fixture() {
  return {
    schema: "mastermind.workspace_admitted_execution_plan.v1",
    selection: { ...selection },
    availability: "AVAILABLE", reason_codes: [],
    source_observation: { schema: "mastermind.workspace_plan_observation.v1",
      selection: { ...selection }, state: "SAME", control_room: {}, runtime: {} },
    plan: {
      schema: "mastermind.admitted_execution_plan_view.v1",
      plan_schema_version: "mastermind.execution_plan/v3",
      admission_schema_version: "mastermind.coo_plan_admission/v2",
      root_job_id: selection.root_job_id, plan_attempt_id: "ATT-123",
      policy_sha: digest, plan_digest: digest, reservation_digest: digest,
      admission_state: "ADMITTED",
      steps: [
        { ordinal: 0, step_id: "step-1", objective: "Investigate the original parent route",
          business_impact: "material", review_required: false, prerequisite_step_ids: [] },
        { ordinal: 1, step_id: "step-2", objective: "Verify the authenticated route",
          business_impact: "critical", review_required: true, prerequisite_step_ids: ["step-1"] },
      ],
    },
  };
}
const unavailable = () => {
  const x = fixture();
  return { ...x, availability: "UNAVAILABLE", reason_codes: ["ADMISSION_NOT_ESTABLISHED"],
    source_observation: { ...x.source_observation, state: "UNKNOWN" }, plan: null };
};

describe("authenticated admitted-plan contract", () => {
  it("projects only approved fields with ordered prerequisites and no fabricated progress", () => {
    const original = fixture();
    const decoded = decodeAdmittedPlan(original, selection);
    expect(decoded.availability).toBe("AVAILABLE");
    if (decoded.availability !== "AVAILABLE") throw Error("expected admitted plan");
    expect(decoded.plan.steps[1].prerequisite_step_ids).toEqual(["step-1"]);
    expect(Object.keys(decoded.plan)).toHaveLength(10);
    decoded.plan.steps[0].objective = "local presentation mutation";
    expect(original.plan.steps[0].objective).toMatch(/Investigate/);
    expect(JSON.stringify(decoded)).not.toMatch(/private-quota|credential|tool-payload/);
  });
  it("does not turn unavailable or absent admission into an empty successful plan", () => {
    const decoded = decodeAdmittedPlan(unavailable(), selection);
    expect(decoded.availability).toBe("UNAVAILABLE");
    expect(decoded.plan).toBeNull();
    expect(decoded.reason_codes).toEqual(["ADMISSION_NOT_ESTABLISHED"]);
  });
  it.each([
    ["wrong root", x => { x.selection.root_job_id = "JOB-9"; }],
    ["unobserved source", x => { x.source_observation.state = "UNKNOWN"; }],
    ["unknown plan field", x => { (x.plan as object & { prompt?: string }).prompt = "secret"; }],
    ["unknown step field", x => { (x.plan.steps[0] as object & { provider?: string }).provider = "private"; }],
    ["duplicate id", x => { x.plan.steps[1].step_id = "step-1"; }],
    ["forward prerequisite", x => { x.plan.steps[0].prerequisite_step_ids = ["step-2"]; }],
    ["unknown prerequisite", x => { x.plan.steps[1].prerequisite_step_ids = ["missing"]; }],
    ["duplicate prerequisite", x => { x.plan.steps[1].prerequisite_step_ids = ["step-1", "step-1"]; }],
    ["unadmitted plan", x => { x.plan.admission_state = "PENDING"; }],
    ["wrong policy digest", x => { x.plan.policy_sha = "not-a-digest"; }],
    ["wrong admission version", x => { x.plan.admission_schema_version = "mastermind.coo_plan_admission/v1"; }],
    ["false completion", x => { (x.plan.steps[0] as object & { completed?: boolean }).completed = true; }],
    ["too many steps", x => { x.plan.steps = Array.from({ length: 9 }, (_, index) => ({ ...x.plan.steps[0], step_id: "n" + index, ordinal: index })); }],
  ] as Array<[string, (x: ReturnType<typeof fixture>) => void]>)("refuses %s", (_label, change) => {
    const x = fixture(); change(x);
    expect(() => decodeAdmittedPlan(x, selection)).toThrow("ADMITTED_PLAN_INVALID");
  });
  it("does not promote source changes to unavailable-without-conflict", () => {
    const x = unavailable();
    x.reason_codes[0] = "SOURCE_CHANGED";
    expect(() => decodeAdmittedPlan(x, selection)).toThrow("ADMITTED_PLAN_INVALID");
    x.source_observation.state = "CONFLICT";
    expect(decodeAdmittedPlan(x, selection).observation).toBe("CONFLICT");
  });
});

describe("admitted plan inspector", () => {
  it("starts no read automatically; selection opens only through explicit interaction", async () => {
    const read = vi.fn(async () => fixture());
    render(<AdmittedPlanInspector selection={selection} read={read}
      sourceGeneration={() => 7} canRead={() => true} />);
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect plan" }));
    expect(await screen.findByText("Investigate the original parent route")).toBeTruthy();
    expect(screen.getByText("Verify the authenticated route")).toBeTruthy();
    expect(screen.getByText(/Execution status: not asserted/)).toBeTruthy();
    expect(screen.getByText(/Only observed Jobs, Attempts/)).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledWith(expect.objectContaining(selection));
  });
  it("has no read action without the source and permission owner", () => {
    const read = vi.fn(async () => fixture());
    render(<AdmittedPlanInspector selection={selection} read={read}
      sourceGeneration={() => 1} canRead={() => false} />);
    expect(screen.getByRole("button", { name: "Inspect plan" })).toHaveProperty("disabled", true);
    expect(read).not.toHaveBeenCalled();
  });
  it("drops obsolete responses on identity change and source-generation revocation", async () => {
    let release!: (value: unknown) => void;
    let epoch = 4;
    const read = vi.fn(() => new Promise<unknown>(resolve => { release = resolve; }));
    const props = { read, sourceGeneration: () => epoch, canRead: () => true };
    const view = render(<AdmittedPlanInspector selection={selection} {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect plan" }));
    epoch = 5;
    release(fixture());
    await waitFor(() => expect(screen.queryByText("Investigate the original parent route")).toBeNull());
    view.rerender(<AdmittedPlanInspector selection={{ ...selection, root_job_id: "JOB-124" }} {...props} />);
    expect(screen.queryByText("Investigate the original parent route")).toBeNull();
  });
  it("preserves unavailable vs admitted and localizes the surface", async () => {
    const read = vi.fn(async () => unavailable());
    render(<AdmittedPlanInspector selection={selection} read={read}
      sourceGeneration={() => 0} canRead={() => true} locale="zh-CN" />);
    fireEvent.click(screen.getByRole("button", { name: "检查计划" }));
    expect(await screen.findByText(/ADMISSION_NOT_ESTABLISHED/)).toBeTruthy();
    expect(screen.queryByText("Investigate the original parent route")).toBeNull();
  });
});

describe("existing MissionHost authenticated plan acquisition", () => {
  it("omits the port when the source owner is unmounted", async () => {
    const { bindMissionHost } = await import("../host");
    const client: any = {
      getState: () => ({ status: "signed_in", acquisition: true, content: false, reason: null }),
      invalidationGeneration: () => 1, subscribe: () => () => {},
      signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => null, readWork: async () => null,
      readMission: async () => null, readCurrentWindow: async () => null,
    };
    expect(bindMissionHost(client).readAdmittedPlan).toBeUndefined();
  });
  it("revalidates selection and authentication after the owner acquisition", async () => {
    const { bindMissionHost } = await import("../host");
    let epoch = 1;
    let allowed = true;
    let resolve!: (value: unknown) => void;
    const read = vi.fn(() => new Promise<unknown>(r => { resolve = r; }));
    const client: any = {
      getState: () => ({ status: allowed ? "signed_in" : "signed_out", acquisition: allowed, content: false, reason: null }),
      invalidationGeneration: () => epoch, subscribe: () => () => {},
      signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => null, readWork: async () => null,
      readMission: async () => null, readCurrentWindow: async () => null,
      readAdmittedPlan: read,
    };
    const host = bindMissionHost(client);
    await expect(host.readAdmittedPlan!({ ...selection, root_job_id: "NOT-A-JOB",
      signal: new AbortController().signal })).rejects.toThrow("PLAN_SELECTION_INVALID");
    expect(read).not.toHaveBeenCalled();
    const pending = host.readAdmittedPlan!({ ...selection, signal: new AbortController().signal });
    epoch += 1;
    allowed = false;
    resolve(fixture());
    await expect(pending).rejects.toThrow("READ_CANCELLED");
    expect(read).toHaveBeenCalledTimes(1);
  });
});
