import type { PlanSelection } from "./admitted-plan";

/** Synthetic complete receipt for plan consumer tests; no installed source proof. */
export function planObservationFixture(selection: PlanSelection) {
  const digest = "a".repeat(64);
  return {
    schema: "mastermind.workspace_plan_observation.v1", selection: { ...selection }, state: "SAME",
    runtime: { schema: "mastermind.runtime_read_observation.v1", state: "SAME",
      source_identity: "b".repeat(32), before: 7, after: 7 },
    control_room: { instance_before: "fixture-ccr-owner", instance_after: "fixture-ccr-owner",
      publication_before: 3, publication_after: 3,
      document_digest: digest, source_validity_digest: digest, cache_currentness_digest: digest },
  };
}
