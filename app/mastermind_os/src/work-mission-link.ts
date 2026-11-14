import {
  normalizeSelection,
  type MissionSelection,
  type programsFromControlRoom,
} from "./mission";

/** Input must come from the existing admitted Programs mapper, never raw JSON. */
export interface WorkMissionLinkInput {
  rootJobId: string;
  programs: ReturnType<typeof programsFromControlRoom> | null;
  /** Existing host auth policy, not a new authorization or token. */
  acquisitionAllowed: boolean;
  /** Clear when the selected Work observation is replaced/refused/invalidated. */
  workObservationAvailable: boolean;
}
export type WorkMissionLinkReason =
  | "ACQUISITION_UNAVAILABLE"
  | "WORK_UNAVAILABLE"
  | "PROGRAMS_UNAVAILABLE"
  | "PROGRAMS_INVALID"
  | "ROOT_UNJOINED"
  | "ROOT_CONFLICT";
export type WorkMissionLinkResolution =
  | {
      state: "RESOLVED";
      rootJobId: string;
      selection: MissionSelection;
      title: string | null;
    }
  | { state: "UNAVAILABLE"; rootJobId: string; reason: WorkMissionLinkReason };

/**
 * Navigation-only join inside the returned bounded Programs view.
 * Work and Programs are independent observations, not a common snapshot.
 * Resolution neither proves current liveness nor authorizes the Mission read.
 * No cached selection: callers resolve again after every relevant invalidation.
 */
export function resolveWorkMissionLink(
  input: WorkMissionLinkInput,
): WorkMissionLinkResolution {
  const { rootJobId, programs } = input;
  const refuse = (
    reason: WorkMissionLinkReason,
  ): WorkMissionLinkResolution => ({ state: "UNAVAILABLE", rootJobId, reason });
  if (input.acquisitionAllowed !== true)
    return refuse("ACQUISITION_UNAVAILABLE");
  if (input.workObservationAvailable !== true)
    return refuse("WORK_UNAVAILABLE");
  if (!programs || programs.state !== "AVAILABLE")
    return refuse("PROGRAMS_UNAVAILABLE");
  // The existing Programs mapper bounds the index at 500 and candidates at 50.
  // Reject malformed in-process inputs rather than granting a partial join.
  if (!Array.isArray(programs.programs) || programs.programs.length > 500)
    return refuse("PROGRAMS_INVALID");
  const seen = new Set<string>();
  const mentions: typeof programs.programs = [];
  for (const row of programs.programs) {
    if (
      !row ||
      typeof row !== "object" ||
      typeof row.workRef !== "string" ||
      seen.has(row.workRef) ||
      !Array.isArray(row.rootCandidates) ||
      row.rootCandidates.length > 50 ||
      !row.rootCandidates.every((r) => typeof r === "string") ||
      !(row.rootJobId === null || typeof row.rootJobId === "string") ||
      !["RESOLVED", "UNKNOWN", "CONFLICT"].includes(row.rootState) ||
      !(row.title === null || typeof row.title === "string")
    )
      return refuse("PROGRAMS_INVALID");
    seen.add(row.workRef);
    if (row.rootJobId === rootJobId || row.rootCandidates.includes(rootJobId))
      mentions.push(row);
  }
  if (!mentions.length) return refuse("ROOT_UNJOINED");
  if (mentions.length !== 1) return refuse("ROOT_CONFLICT");
  const row = mentions[0];
  if (row.rootState === "CONFLICT") return refuse("ROOT_CONFLICT");
  if (row.rootState !== "RESOLVED" || row.rootJobId !== rootJobId)
    return refuse("ROOT_UNJOINED");
  if (row.rootCandidates.length !== 1 || row.rootCandidates[0] !== rootJobId)
    return refuse("ROOT_CONFLICT");
  const selection = normalizeSelection({ workRef: row.workRef, rootJobId });
  if (!selection) return refuse("PROGRAMS_INVALID");
  return { state: "RESOLVED", rootJobId, selection, title: row.title };
}
