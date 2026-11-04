import { describe, expect, it } from "vitest";
import producer from "../fixtures/project-session-association-producer.json";
import { decodeProjectAssociation, normalizeProjectAssociationSelection } from "./project-association";

// The fixture was emitted by the actual Runtime-backed pure producer tests at
// 65832f7da. It is synthetic test evidence, never a live broker observation.
const selected = { workRef: producer.selection.work_ref, rootJobId: producer.selection.root_job_id };
describe("managed-session producer consumer agreement", () => {
  it("consumes the exact producer body without granting continuation", () => {
    expect(normalizeProjectAssociationSelection(selected)).toEqual(selected);
    const decoded = decodeProjectAssociation(producer, selected);
    expect(decoded).toEqual(producer);
    expect(decoded?.can_send).toBe(false);
    expect(decoded?.continuation_target).toBeNull();
    expect(Object.isFrozen(decoded)).toBe(true);
  });
  it("preserves the producer's start/resume generation relationship", () => {
    const resumed = structuredClone(producer);
    resumed.materialization.operation_kind = "resume_session";
    resumed.materialization.generation_number = 2;
    expect(decodeProjectAssociation(resumed, selected)).not.toBeNull();
    resumed.materialization.generation_number = 1;
    expect(decodeProjectAssociation(resumed, selected)).toBeNull();
    const invalidStart = structuredClone(producer);
    invalidStart.materialization.generation_number = 2;
    expect(decodeProjectAssociation(invalidStart, selected)).toBeNull();
  });
  it("rejects an impossible UTC calendar timestamp accepted by permissive Date parsing", () => {
    const invalid = structuredClone(producer);
    invalid.materialization.recorded_at = "2026-02-31T00:00:00+00:00";
    expect(decodeProjectAssociation(invalid, selected)).toBeNull();
  });
  it("requires the actual producer selector and canonical workstream path", () => {
    for (const workRef of ["WS:lowercase", "WS:A--B", "WS:A.B", "WS:A_"]) {
      expect(normalizeProjectAssociationSelection({ ...selected, workRef })).toBeNull();
    }
    expect(decodeProjectAssociation(producer, { ...selected, rootJobId: "JOB-002" })).toBeNull();
    const wrongPath = structuredClone(producer);
    wrongPath.project_source.path = "agentos/workstreams/WS-OTHER.md";
    expect(decodeProjectAssociation(wrongPath, selected)).toBeNull();
  });
});
