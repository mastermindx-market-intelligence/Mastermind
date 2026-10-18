/** Render-only join across TWO independently sampled, authorized Workspace reads.
 * Admitted plan describes allowed work, Mission describes observed Jobs/Attempts.
 * Neither proves per-step completion, current liveness, review or product acceptance.
 */
import type { MissionDocument, Missionv3Document } from "../mission";
import type { AdmittedPlan, PlanSelection } from "./admitted-plan";

export interface ObservedPlanWorker {
  job_id: string;
  status: string | null;
  current_attempt_id: string | null;
  worker_id: string | null;
}
export interface PlanWorkerObservation {
  state: "OBSERVED" | "NO_MATCH_IN_SAMPLE" | "UNAVAILABLE";
  /** Explicitly source-limited, never a global or authoritative plan-step total. */
  coverage: "COMPLETE" | "INCOMPLETE" | "HISTORICAL_ONLY" | "NOT_PROJECTED" | "NOT_APPLICABLE" | "UNKNOWN";
  workers: ObservedPlanWorker[];
  omitted: boolean;
  observed_at: string | null;
}
const blank = (): PlanWorkerObservation => ({
  state: "UNAVAILABLE", coverage: "UNKNOWN", workers: [], omitted: false, observed_at: null,
});
const MAX_WORKER_DISPLAY = 6;

/**
 * The office supplies an already-qualified Mission; the caller must additionally
 * pass its existing source state. No independent runtime read or entitlement
 * is inferred from plan-step strings or shared machine credentials.
 */
export function observePlanWorkers(
  selection: PlanSelection,
  plan: AdmittedPlan,
  mission: MissionDocument | Missionv3Document | null,
  missionSourceState: string,
  missionObservedAt: string | null,
): ReadonlyMap<string, PlanWorkerObservation> {
  const result = new Map<string, PlanWorkerObservation>();
  const current = missionSourceState === "CURRENT" &&
    mission?.read_state.state === "CURRENT" &&
    mission.program.work_ref === selection.work_ref &&
    mission.mission.root_job_id === selection.root_job_id &&
    mission.mission.root_job_ambiguous === false &&
    mission.mission.runtime_root_state === "RESOLVED" &&
    mission.children.state !== "UNAVAILABLE" &&
    mission.children.state !== "HISTORICAL" &&
    (mission.source.owner_observation == null || mission.source.owner_observation.state === "SAME");
  if (!current || !mission) {
    for (const step of plan.steps) result.set(step.step_id, blank());
    return result;
  }
  for (const step of plan.steps) {
    // Mission DTO may be PARTIAL/truncated, so even no matches is NOT proof
    // that an admitted plan step has no workers.
    const matching = mission.children.items.filter(child => child.plan_step_id === step.step_id);
    const workers = matching.slice(0, MAX_WORKER_DISPLAY).map(child => ({
      job_id: child.job_id,
      status: child.status,
      current_attempt_id: child.current_attempt_id,
      worker_id: child.worker_id,
    }));
    result.set(step.step_id, {
      state: matching.length ? "OBSERVED" : "NO_MATCH_IN_SAMPLE",
      coverage: mission.children.coverage, workers,
      omitted: matching.length > MAX_WORKER_DISPLAY,
      observed_at: missionObservedAt,
    });
  }
  return result;
}
