import { describe, expect, it } from "vitest";
import { decodeMission, decodeMissionv3, type MissionDocument } from "../mission";
import { decodeResultEnvelope } from "../result";
import currentV3 from "../fixtures/mission-v3-design-current-17-slots.json";
import availableResult from "../fixtures/result-design-available-reject-unicode.json";
import currentMission from "../fixtures/mission-v2-current-128c46f6.json";
import {
  projectOffice,
  type OfficeInput,
  type ProjectionContext,
  type SourceState,
} from "./projection";

const context: ProjectionContext = {
  authGeneration: 7,
  selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: "session:exact-a",
  bindingGeneration: "generation:1",
  revisions: { mission: "revision:1", programs: "programs:1", result: null, conversation: null },
};
function input(): OfficeInput {
  const raw = structuredClone(currentMission);
  raw.read_state = { state: "CURRENT", reason_codes: [], usable_sections: raw.read_state.usable_sections };
  return {
    mission: {
      context: structuredClone(context),
      source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "revision:1", observed_at: "2026-10-03T10:00:00Z", state: "CURRENT", coverage: "COMPLETE" },
      value: decodeMission(raw, context.selection!)!,
    },
    programs: null,
    result: null,
    conversation: null,
  };
}

function withResult() {
  const selection = { workRef: availableResult.selection.work_ref, rootJobId: availableResult.selection.root_job_id };
  const current: ProjectionContext = { ...context, selection, revisions: { ...context.revisions, result: "result:1" } };
  const mission = decodeMissionv3(structuredClone(currentV3), { workRef: "WS:B5", rootJobId: "JOB-100" })!;
  mission.program.work_ref = selection.workRef;
  mission.mission.root_job_id = selection.rootJobId;
  mission.mission.root_job_candidates = [selection.rootJobId];
  mission.result_refs.root_job_id = selection.rootJobId;
  mission.source.owner_observation!.selection = { work_ref: selection.workRef, root_job_id: selection.rootJobId };
  const result = decodeResultEnvelope(structuredClone(availableResult), {
    ...selection, jobId: availableResult.selection.job_id,
    attemptId: availableResult.selection.attempt_id, resultEnvelopeDigest: availableResult.selection.result_envelope_digest,
  })!;
  mission.result_refs.refs = [{ ...result.result!.selection, orchestration_role: result.result!.role, validation: "UNVALIDATED" }];
  mission.source.owner_observation!.control_room = structuredClone(result.source_observation.control_room);
  const source = input();
  source.mission = { context: current, source: { ...source.mission!.source }, value: mission };
  source.result = { context: current, source: { ...source.mission.source, ref: "result:exact", revision: "result:1" }, value: result };
  return { source, current };
}

describe("owner-fed office projection", () => {
  it("retains exact provenance and owner facts without interpreting return as acceptance", () => {
    const source = input();
    const mission = source.mission!.value!;
    mission.execution.state = "COMPLETED";
    mission.review.verdict = "approve";
    mission.acceptance.state = "NOT_PROJECTED";
    const projected = projectOffice(source, context);
    expect(projected.schema).toBe("mastermind.product_projection.v1");
    expect(projected.mission.value?.program.work_ref).toBe("WS:ONE");
    expect(projected.mission.source).toEqual(source.mission!.source);
    expect(projected.mission.value?.program.evidence).toEqual(mission.program.evidence);
    expect(projected.receipts.review).toBe("approve");
    expect(projected.receipts.acceptance).toBe("NOT_PROJECTED");
    expect(projected.companyTotal).toBeNull();
    expect(projected.work.reason).toBe("WORK_PENDING_CUSTODY");
    expect(projected.direction.reason).toBe("MISSING_PRODUCER");
  });

  it.each<SourceState>(["CURRENT", "STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])("keeps %s distinct", (state) => {
    const source = input();
    source.mission!.source.state = state;
    const projected = projectOffice(source, context);
    expect(projected.mission.source.state).toBe(state);
    if (!["CURRENT", "STALE"].includes(state)) expect(projected.mission.value).toBeNull();
  });

  it("clears private data synchronously on auth change, including unrelated source inputs", () => {
    const projected = projectOffice(input(), { ...context, authGeneration: 8 });
    expect(projected.mission.source.state).toBe("WITHHELD");
    expect(projected.mission.value).toBeNull();
    expect(JSON.stringify(projected)).not.toContain("One");
  });

  it.each([
    { selection: { workRef: "WS:BETA", rootJobId: "JOB-1" } },
    { selection: { workRef: "WS:ONE", rootJobId: "JOB-2" } },
    { sessionRef: "session:exact-b" },
    { bindingGeneration: "generation:2" },
  ])("does not reuse a projection after a target or binding changes: %j", (change) => {
    const projected = projectOffice(input(), { ...context, ...change });
    expect(projected.mission.source.state).toBe("UNASSOCIATED");
    expect(projected.mission.value).toBeNull();
  });

  it("invalidates only the source whose revision changed", () => {
    const source = input();
    source.programs = {
      context: structuredClone(context),
      source: { ...source.mission!.source, owner: "AGENT_OS", ref: "programs:supplied", revision: "programs:1" },
      value: { programs: [], state: "AVAILABLE", reason: "" },
    };
    const projected = projectOffice(source, { ...context, revisions: { ...context.revisions, mission: "revision:2" } });
    expect(projected.mission.source.state).toBe("STALE");
    expect(projected.mission.value).toBeNull();
    expect(projected.programs.source.state).toBe("CURRENT");
    expect(projected.programs.value?.programs).toEqual([]);
    expect(projected.companyTotal).toBeNull();
  });

  it("refuses a same-title mission with a different owner identity", () => {
    const source = input();
    source.mission!.value!.program.work_ref = "WS:BETA";
    expect(projectOffice(source, context).mission.source.state).toBe("UNASSOCIATED");
  });

  it("preserves useful partial facts and their incomplete coverage without a healthy aggregate", () => {
    const source = input();
    source.mission!.value!.read_state.state = "PARTIAL";
    source.mission!.value!.children.coverage = "INCOMPLETE";
    source.mission!.value!.children.total_count = null;
    const projected = projectOffice(source, context);
    expect(projected.mission.source.state).toBe("UNKNOWN");
    expect(projected.mission.source.coverage).toBe("INCOMPLETE");
    expect(projected.mission.value?.children.total_count).toBeNull();
    expect(projected).not.toHaveProperty("healthy");
  });

  it("does not infer delivery and pickup from a START receipt", () => {
    const source = input();
    source.mission!.value!.transport.dispatch_state = "STARTED";
    const { receipts } = projectOffice(source, context);
    expect(receipts.start).toBe("STARTED");
    expect(receipts.delivery).toBeNull();
    expect(receipts.pickup).toBeNull();
  });

  it("does not carry collection context into a preview for another session", () => {
    const source = input();
    source.programs = {
      context: structuredClone(context),
      source: { ...source.mission!.source, owner: "AGENT_OS", ref: "programs:supplied", revision: "programs:1" },
      value: { programs: [], state: "AVAILABLE", reason: "" },
    };
    const projected = projectOffice(source, { ...context, sessionRef: "session:another" });
    expect(projected.programs.source.state).toBe("UNASSOCIATED");
    expect(projected.programs.value).toBeNull();
  });

  it("keeps a completed exact result separate from a transport return", () => {
    const { source, current } = withResult();
    source.mission!.value!.transport.dispatch_state = "STARTED";
    const projected = projectOffice(source, current);
    expect(projected.result.value?.result?.execution_status).toBe("COMPLETED");
    expect(projected.receipts.return).toBeNull();
    expect(projected.receipts.acceptance).toBe("NOT_PROJECTED");
  });

  it("refuses a result from another digest even when title and root match", () => {
    const { source, current } = withResult();
    source.result!.value!.selection.result_envelope_digest = "0".repeat(64);
    expect(projectOffice(source, current).result.source.state).toBe("UNASSOCIATED");
  });

  it("invalidates a result if the Control Room observation changed during detail acquisition", () => {
    const { source, current } = withResult();
    source.result!.value!.source_observation.control_room!.document_digest = "0".repeat(64);
    const projected = projectOffice(source, current);
    expect(projected.result.source.state).toBe("UNKNOWN");
    expect(projected.result.value).toBeNull();
  });

  it("retains unknown effect even if execution and review look complete", () => {
    const source = input();
    source.mission!.value!.transport.dispatch_state = "EFFECT_UNKNOWN";
    source.mission!.value!.execution.state = "COMPLETED";
    source.mission!.value!.review.verdict = "approve";
    expect(projectOffice(source, context).receipts.effect).toBe("EFFECT_UNKNOWN");
  });

  it("does not mutate decoded input or alias it into the presentation", () => {
    const source = input(), original = structuredClone(source);
    const projected = projectOffice(source, context);
    projected.mission.value!.program.title = "changed display";
    expect(source).toEqual(original);
  });

  it.each(["HISTORICAL", "UNAVAILABLE"] as MissionDocument["read_state"]["state"][])("does not promote owner read state %s", (state) => {
    const source = input();
    source.mission!.value!.read_state.state = state;
    const projected = projectOffice(source, context);
    expect(projected.mission.source.state).toBe(state === "HISTORICAL" ? "STALE" : "UNAVAILABLE");
    if (state === "UNAVAILABLE") expect(projected.mission.value).toBeNull();
  });

  it("represents missing reads as unavailable, never a healthy zero", () => {
    const projected = projectOffice({ mission: null, programs: null, result: null, conversation: null }, context);
    expect(projected.mission.source.state).toBe("UNAVAILABLE");
    expect(projected.programs.value).toBeNull();
    expect(projected.companyTotal).toBeNull();
    expect(projected.receipts.acceptance).toBeNull();
  });
});
