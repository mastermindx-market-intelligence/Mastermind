import { normalizeResultSelection, type ResultSelection } from "../result";
import type { ChildCard } from "../mission";
import { missionInteriors, type FabricMission } from "./mission-interiors";

/**
 * Presentation-only selection of an existing Mission v3 result reference.
 * This never reads content or extends source/user permissions. The actual
 * Result owner must authorize and decode its exact tuple again.
 */
export function qualifyWorkerResultRef(mission: FabricMission | null, child: ChildCard | null): ResultSelection | null {
  if (!mission || !child || mission.schema !== "mastermind.mission_workspace.v3" ||
      mission.read_state.state !== "CURRENT" ||
      mission.children.state === "UNAVAILABLE" ||
      mission.mission.runtime_root_state !== "RESOLVED" ||
      mission.mission.root_job_ambiguous ||
      mission.source.owner_observation?.state !== "SAME")
    return null;
  const index = mission.result_refs;
  const root = mission.mission.root_job_id;
  if (!root || index.root_job_id !== root ||
      index.generation.state !== "SAME" ||
      index.availability === "UNAVAILABLE" ||
      child.latest_attempt?.has_result !== true ||
      !child.latest_attempt.attempt_id)
    return null;
  // Strictly select the same row object already associated by the bounded
  // Mission tree. An off-cap, duplicate or unjoined job cannot mint an action.
  const rows = missionInteriors(mission).rows;
  if (!rows.some(row => row.child === child && row.association === "ASSOCIATED"))
    return null;
  const exact = index.refs.filter(ref =>
    ref.root_job_id === root &&
    ref.job_id === child.job_id &&
    ref.attempt_id === child.latest_attempt?.attempt_id &&
    (!child.orchestration_role || child.orchestration_role === ref.orchestration_role));
  if (exact.length !== 1) return null;
  const ref = exact[0];
  return normalizeResultSelection({
    workRef: mission.program.work_ref, rootJobId: root,
    jobId: ref.job_id, attemptId: ref.attempt_id,
    resultEnvelopeDigest: ref.result_envelope_digest,
  });
}
