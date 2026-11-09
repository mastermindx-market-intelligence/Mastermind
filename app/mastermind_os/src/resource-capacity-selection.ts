import { qualifyWorkerResultRef } from "./fabric/mission-worker-result";
import type { OfficeProjection } from "./meta-ceo/projection";
import type { MissionSelection } from "./mission";
import { normalizeResultSelection, type ResultSelection } from "./result";
import type { ResourceCapacityReadSelection } from "./resources/resource-capacity-read";

/** Reuse an explicitly selected return only while the current Mission owner
 * independently indexes that exact tuple and names its Attempt as the child's
 * latest. This is a READ selector, never a placement/readiness conclusion. */
export function selectedCurrentCapacityAttempt(
  projection: OfficeProjection,
  selection: MissionSelection | null,
  requested: ResultSelection | null,
  authGeneration: number,
): ResourceCapacityReadSelection | null {
  const read = projection.mission;
  const mission = read.value;
  const tuple = requested && normalizeResultSelection(requested);
  if (projection.context.authGeneration !== authGeneration || !selection || !tuple ||
      projection.context.selection?.workRef !== selection.workRef ||
      projection.context.selection?.rootJobId !== selection.rootJobId ||
      read.source.state !== "CURRENT" || !mission || mission.schema !== "mastermind.mission_workspace.v3" ||
      mission.program.work_ref !== selection.workRef || mission.mission.root_job_id !== selection.rootJobId ||
      mission.mission.runtime_root_state !== "RESOLVED" || mission.mission.root_job_ambiguous ||
      mission.mission.root_job_candidates.length !== 1 || mission.mission.root_job_candidates[0] !== selection.rootJobId ||
      tuple.workRef !== selection.workRef || tuple.rootJobId !== selection.rootJobId) return null;
  const children = mission.children.items.filter(child => child.job_id === tuple.jobId);
  if (children.length !== 1 || children[0].latest_attempt?.attempt_id !== tuple.attemptId) return null;
  const indexed = qualifyWorkerResultRef(mission, children[0]);
  if (!indexed || children[0].current_attempt_id !== tuple.attemptId ||
      indexed.workRef !== tuple.workRef || indexed.rootJobId !== tuple.rootJobId ||
      indexed.jobId !== tuple.jobId || indexed.attemptId !== tuple.attemptId ||
      indexed.resultEnvelopeDigest !== tuple.resultEnvelopeDigest) return null;
  return {work_ref: tuple.workRef, root_job_id: tuple.rootJobId, job_id: tuple.jobId, attempt_id: tuple.attemptId};
}
