/** A presentation over the incumbent Mission read. No acquisition, identity, or task store. */
import { decodeMission, decodeMissionv3, type MissionDocument, type Missionv3Document } from "../mission";
import { captureMissionOfficeRead, completeMissionOfficeRead } from "../meta-ceo/mission-adapter";
import { sameTarget, type OfficeProjection, type ProjectionContext, type SourceState } from "../meta-ceo/projection";
import { missionInteriors } from "../fabric/mission-interiors";
import { qualifyWorkerResultRef } from "../fabric/mission-worker-result";

export type OrganizationMission = MissionDocument | Missionv3Document;

/** Reuse the actual owner decoder and receipt identity; a CURRENT label alone is insufficient. */
export function qualifyOrganizationMission(
  binding: ProjectionContext, missionState: SourceState, projection?: OfficeProjection,
): OrganizationMission | null {
  if (!projection || !projection.context || !projection.mission?.source || missionState !== "CURRENT" || !binding.selection ||
      projection.schema !== "mastermind.product_projection.v1" ||
      projection.context.authGeneration !== binding.authGeneration ||
      !sameTarget(binding, projection.context) ||
      projection.context.revisions.mission !== binding.revisions.mission ||
      !binding.revisions.mission) return null;
  const read = projection.mission;
  if (read.source.state !== "CURRENT" || read.source.owner !== "EXECUTIVE_OS" ||
      read.source.revision !== binding.revisions.mission || read.source.coverage !== "COMPLETE" ||
      read.source.ref_kind !== "CONTROL_ROOM_DOCUMENT_DIGEST" ||
      read.source.observed_at_kind !== "LOCAL_ACQUISITION" ||
      !read.source.observed_at || !read.source.ref || !read.value) return null;
  const decoded = read.value.schema === "mastermind.mission_workspace.v3"
    ? decodeMissionv3(read.value, binding.selection)
    : decodeMission(read.value, binding.selection);
  if (!decoded || decoded.read_state.state !== "CURRENT" ||
      decoded.mission.runtime_root_state !== "RESOLVED" || decoded.mission.root_job_ambiguous ||
      decoded.source.owner_observation?.state !== "SAME") return null;
  const checked = completeMissionOfficeRead(
    captureMissionOfficeRead(binding), binding, decoded, read.source.observed_at,
  );
  if (checked.kind !== "observed" || checked.snapshot.source.state !== "CURRENT" ||
      checked.snapshot.source.coverage !== "COMPLETE" ||
      checked.snapshot.source.revision !== read.source.revision ||
      checked.snapshot.source.ref !== read.source.ref) return null;
  // Return detached owner bytes, never caller-owned mutable objects.
  return structuredClone(decoded);
}

export type ObservedActivity = "WORKING" | "QUEUED" | "FINISHED" | "NEEDS_ATTENTION" | "UNKNOWN";

export function organizationWork(mission: OrganizationMission) {
  const current = mission.read_state.state === "CURRENT";
  const model = missionInteriors(mission);
  const rows = model.rows.map(row => {
    const child = row.child;
    const attempt = child.latest_attempt;
    const exactAttempt = !!child.current_attempt_id && attempt?.attempt_id === child.current_attempt_id;
    let activity: ObservedActivity = "UNKNOWN";
    if (current && row.association === "ASSOCIATED") {
      if (child.status === "QUEUED") activity = "QUEUED";
      else if (child.worker_id && exactAttempt && child.status === "RUNNING" && attempt?.status === "RUNNING")
        activity = "WORKING";
      else if (exactAttempt && child.status === "COMPLETED" && attempt?.status === "COMPLETED")
        activity = "FINISHED";
      else if (["FAILED", "LOST", "CANCELLED", "RATE_LIMITED"].includes(child.status ?? ""))
        activity = "NEEDS_ATTENTION";
    }
    return { ...row, activity, exactAttempt,
      result: row.association === "ASSOCIATED" ? qualifyWorkerResultRef(mission, child) : null };
  });
  const coverageComplete = current && mission.children.unjoined_job_ids.length === 0 && mission.children.coverage === "COMPLETE" &&
    (mission.children.state === "AVAILABLE" || mission.children.state === "EMPTY") &&
    mission.children.overflow_count === 0 && mission.children.unjoined_job_count === 0 &&
    mission.children.total_count === mission.children.items.length &&
    model.locallyOmitted === 0 && model.unassociated === 0;
  const activityComplete = coverageComplete && rows.every(row => row.activity !== "UNKNOWN");
  return {
    rows, coverageComplete, activityComplete, locallyOmitted: model.locallyOmitted,
    working: activityComplete ? rows.filter(row => row.activity === "WORKING").length : null,
    finished: activityComplete ? rows.filter(row => row.activity === "FINISHED").length : null,
    // All counts are this selected operation's observed jobs, never an organization/fleet census.
    observedJobs: current && (mission.children.state === "AVAILABLE" || mission.children.state === "EMPTY")
      ? rows.length : null,
  };
}
