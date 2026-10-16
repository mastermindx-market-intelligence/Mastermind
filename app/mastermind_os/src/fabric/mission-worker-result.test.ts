import { describe, expect, it } from "vitest";
import fixture from "../fixtures/mission-v3-owner-current-operator-harness.json";
import type { Missionv3Document, ChildCard } from "../mission";
import { qualifyWorkerResultRef } from "./mission-worker-result";

const source = () => structuredClone(fixture) as unknown as Missionv3Document;
const indexed = () => {
  const mission = source();
  const ref = mission.result_refs.refs[0];
  const child: ChildCard = {
    job_id: ref.job_id, parent_job_id: ref.root_job_id, status: "COMPLETED", depth: 1,
    orchestration_role: ref.orchestration_role, plan_step_id: "plan-1", attempt_count: 1,
    attempt_limit: 2, current_attempt_id: ref.attempt_id, worker_id: "observed-worker",
    latest_attempt: { attempt_id: ref.attempt_id, attempt_number: 1, status: "COMPLETED",
      started_at: "2026-10-15T10:00:00Z", finished_at: "2026-10-15T10:10:00Z",
      exit_code: 0, has_result: true, error_present: false, error_class: null },
  };
  mission.children.items = [child];
  return { mission, child, ref };
};
describe("exact source-backed worker return reference", () => {
  it("constructs only the fixed 5-field tuple from the owner result index", () => {
    const { mission, child, ref } = indexed();
    expect(qualifyWorkerResultRef(mission, child)).toEqual({
      workRef: mission.program.work_ref, rootJobId: ref.root_job_id,
      jobId: ref.job_id, attemptId: ref.attempt_id,
      resultEnvelopeDigest: ref.result_envelope_digest,
    });
  });
  it("allows a returned latest attempt but never conflates it with a different current attempt", () => {
    const { mission, child, ref } = indexed();
    child.current_attempt_id = "ATT-" + "f".repeat(32);
    expect(qualifyWorkerResultRef(mission, child)?.attemptId).toBe(ref.attempt_id);
  });
  it("never invents a result from has_result or a matching job alone", () => {
    const { mission, child } = indexed();
    const changed = { ...child, latest_attempt: { ...child.latest_attempt!, attempt_id: "ATT-" + "a".repeat(32) } };
    expect(qualifyWorkerResultRef(mission, changed)).toBeNull();
    expect(qualifyWorkerResultRef(mission, { ...child, latest_attempt: { ...child.latest_attempt!, has_result: null } })).toBeNull();
    mission.result_refs.refs = [];
    expect(qualifyWorkerResultRef(mission, child)).toBeNull();
  });
  it("refuses an unqualified root, stale source and unavailable references", () => {
    for (const mutate of [
      (m: Missionv3Document) => { m.mission.root_job_ambiguous = true; },
      (m: Missionv3Document) => { m.mission.runtime_root_state = "CONFLICT"; },
      (m: Missionv3Document) => { m.read_state.state = "HISTORICAL"; },
      (m: Missionv3Document) => { m.result_refs.generation.state = "UNKNOWN"; },
      (m: Missionv3Document) => { m.result_refs.availability = "UNAVAILABLE"; },
      (m: Missionv3Document) => { m.result_refs.root_job_id = "JOB-999"; },
      (m: Missionv3Document) => { m.source.owner_observation!.state = "UNKNOWN"; },
      (m: Missionv3Document) => { m.children.state = "UNAVAILABLE"; },
    ]) {
      const { mission, child } = indexed(); mutate(mission);
      expect(qualifyWorkerResultRef(mission, child)).toBeNull();
    }
  });
  it("refuses a wrong role, another root or multiple references even with a result bit", () => {
    const { mission, child } = indexed();
    expect(qualifyWorkerResultRef(mission, { ...child, orchestration_role: "review" })).toBeNull();
    expect(qualifyWorkerResultRef(mission, { ...child, parent_job_id: "JOB-999" })).toBeNull();
    const { mission: duplicate, child: exact } = indexed();
    duplicate.result_refs.refs.push({ ...duplicate.result_refs.refs[0] });
    expect(qualifyWorkerResultRef(duplicate, exact)).toBeNull();
  });
});
