import { describe, expect, it } from "vitest";
import { decodeAdmittedPlan, type PlanSelection } from "./admitted-plan";
import { planObservationFixture } from "./plan-observation.fixture";

const selection: PlanSelection = { work_ref: "WS:RECEIPT-PROOF", root_job_id: "JOB-123" };
const hash = "a".repeat(64);
function fixture() {
  return {
    schema: "mastermind.workspace_admitted_execution_plan.v1",
    selection: { ...selection }, availability: "AVAILABLE", reason_codes: [] as string[],
    source_observation: planObservationFixture(selection),
    plan: { schema: "mastermind.admitted_execution_plan_view.v1",
      plan_schema_version: "mastermind.execution_plan/v3", admission_schema_version: "mastermind.coo_plan_admission/v2",
      root_job_id: selection.root_job_id, plan_attempt_id: "ATT-123",
      policy_sha: hash, plan_digest: hash, reservation_digest: hash, admission_state: "ADMITTED",
      steps: [{ ordinal: 0, step_id: "step-1", objective: "Verify the source receipt",
        business_impact: "routine", review_required: true, prerequisite_step_ids: [] as string[] }],
    },
  };
}
type Change = (value: ReturnType<typeof fixture>) => void;
describe("admitted plan public receipt discriminator", () => {
  it("accepts a complete qualified canonical receipt", () => {
    expect(decodeAdmittedPlan(fixture(), selection).availability).toBe("AVAILABLE");
  });
  it.each([
    ["empty receipts", x => { Object.assign(x.source_observation, { runtime: {}, control_room: {} }); }],
    ["missing receipt", x => { Reflect.deleteProperty(x.source_observation, "runtime"); }],
    ["nested Runtime conflict", x => { x.source_observation.runtime.state = "CONFLICT"; }],
    ["nested Runtime unknown", x => { x.source_observation.runtime.state = "UNKNOWN"; }],
    ["wrong Runtime schema", x => { x.source_observation.runtime.schema = "wrong"; }],
    ["missing Runtime identity", x => { Reflect.deleteProperty(x.source_observation.runtime, "source_identity"); }],
    ["malformed Runtime identity", x => { x.source_observation.runtime.source_identity = "arbitrary"; }],
    ["unequal Runtime samples", x => { x.source_observation.runtime.after = 8; }],
    ["negative Runtime samples", x => { x.source_observation.runtime.before = -1; x.source_observation.runtime.after = -1; }],
    ["boolean Runtime samples", x => { Object.assign(x.source_observation.runtime, { before: true, after: true }); }],
    ["missing Control Room instance", x => { Reflect.deleteProperty(x.source_observation.control_room, "instance_before"); }],
    ["different Control Room instances", x => { x.source_observation.control_room.instance_after = "other-owner"; }],
    ["empty Control Room instances", x => { Object.assign(x.source_observation.control_room, { instance_before: "", instance_after: "" }); }],
    ["unequal publications", x => { x.source_observation.control_room.publication_after = 4; }],
    ["zero publications", x => { Object.assign(x.source_observation.control_room, { publication_before: 0, publication_after: 0 }); }],
    ["boolean publications", x => { Object.assign(x.source_observation.control_room, { publication_before: true, publication_after: true }); }],
    ["malformed source digest", x => { x.source_observation.control_room.document_digest = "invalid"; }],
    ["extra observation field", x => { Object.assign(x.source_observation, { private_payload: "forbidden" }); }],
    ["extra Runtime field", x => { Object.assign(x.source_observation.runtime, { snapshot: "forbidden" }); }],
    ["extra Control Room field", x => { Object.assign(x.source_observation.control_room, { path: "forbidden" }); }],
  ] as Array<[string, Change]>)("refuses %s", (_label, change) => {
    const value = fixture(); change(value);
    expect(() => decodeAdmittedPlan(value, selection)).toThrow("ADMITTED_PLAN_INVALID");
  });
  it.each(["ADMISSION_NOT_ESTABLISHED", "ADMISSION_CONFLICT", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED",
    "OVER_BUDGET", "CONTENT_WITHHELD", "CONTENT_OVER_BUDGET", "RESPONSE_OVER_BUDGET"])(
    "preserves canonical unavailable %s", reason => {
      const value = fixture();
      const unavailable = { ...value, availability: "UNAVAILABLE", reason_codes: [reason], plan: null,
        source_observation: { ...value.source_observation,
          state: reason === "SOURCE_CHANGED" ? "CONFLICT" : "UNKNOWN", runtime: null, control_room: null } };
      expect(decodeAdmittedPlan(unavailable, selection).availability).toBe("UNAVAILABLE");
    });
  it("refuses an unavailable response retaining successful nested receipts", () => {
    const value = fixture();
    const unavailable = { ...value, availability: "UNAVAILABLE", reason_codes: ["ADMISSION_NOT_ESTABLISHED"], plan: null,
      source_observation: { ...value.source_observation, state: "UNKNOWN" } };
    expect(() => decodeAdmittedPlan(unavailable, selection)).toThrow("ADMITTED_PLAN_INVALID");
  });
});
