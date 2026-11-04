import type { ChildCard, MissionDocument, Missionv3Document } from "../mission";

export type FabricMission = MissionDocument | Missionv3Document;
export type FabricFilter = "all" | "running" | "results" | "problems";
export interface FabricRow {
  key: string;
  child: ChildCard;
  association: "ASSOCIATED" | "UNASSOCIATED";
  lineage: string[];
  problem: string | null;
}
export const MAX_INSPECTED_CHILDREN = 256;
const FAILURE_STATES = new Set(["FAILED", "LOST", "CANCELLED", "RATE_LIMITED"]);

/** Bounded presentation over already-decoded owner data. No new lifecycle or acquisition. */
export function missionInteriors(mission: FabricMission | null) {
  const children = mission?.children.items ?? [];
  const slice = children.slice(0, MAX_INSPECTED_CHILDREN);
  const byId = new Map<string, ChildCard>();
  const duplicates = new Set<string>();
  // Include the complete decoded set for duplicate detection, never silently pick a winner.
  for (const child of children) {
    if (byId.has(child.job_id)) duplicates.add(child.job_id);
    byId.set(child.job_id, child);
  }
  const root = mission?.mission.root_job_id;
  const usable = !!root && mission?.mission.runtime_root_state === "RESOLVED" &&
    !mission.mission.root_job_ambiguous && mission.read_state.state !== "UNAVAILABLE" &&
    mission.children.state !== "UNAVAILABLE";
  // The decoder bounds the complete source to 500 children. The display cap
  // limits rendered rows and counts, not which supplied ancestors can prove
  // lineage. Missing, duplicate and cyclic parents still fail below.
  const rows: FabricRow[] = slice.map((child, index) => {
    const lineage: string[] = [];
    const seen = new Set<string>();
    let cursor: ChildCard | undefined = child;
    let problem: string | null = usable ? null : "ROOT_NOT_QUALIFIED";
    while (!problem && cursor) {
      if (seen.has(cursor.job_id)) { problem = "PARENT_CYCLE"; break; }
      if (duplicates.has(cursor.job_id) || cursor.job_id === root) { problem = "IDENTITY_CONFLICT"; break; }
      seen.add(cursor.job_id);
      lineage.unshift(cursor.job_id);
      if (cursor.parent_job_id === root) { lineage.unshift(root!); break; }
      cursor = byId.get(cursor.parent_job_id);
      if (!cursor) problem = "PARENT_NOT_OBSERVED";
    }
    return { key: duplicates.has(child.job_id) ? `${child.job_id}:conflict:${index}` : child.job_id,
      child, association: problem ? "UNASSOCIATED" : "ASSOCIATED", lineage, problem };
  });
  const associated = rows.filter(row => row.association === "ASSOCIATED");
  return {
    rows,
    running: associated.filter(row => row.child.status === "RUNNING").length,
    results: associated.filter(row => row.child.latest_attempt?.has_result === true).length,
    problems: rows.filter(isProblem).length,
    unassociated: rows.filter(row => row.association === "UNASSOCIATED").length,
    locallyOmitted: Math.max(0, children.length - MAX_INSPECTED_CHILDREN),
  };
}
export function isProblem(row: FabricRow): boolean {
  return row.association !== "ASSOCIATED" || FAILURE_STATES.has(row.child.status ?? "") ||
    FAILURE_STATES.has(row.child.latest_attempt?.status ?? "") || row.child.latest_attempt?.error_present === true;
}
export function matchesFilter(row: FabricRow, filter: FabricFilter): boolean {
  if (filter === "running") return row.association === "ASSOCIATED" && row.child.status === "RUNNING";
  if (filter === "results") return row.association === "ASSOCIATED" && row.child.latest_attempt?.has_result === true;
  if (filter === "problems") return isProblem(row);
  return true;
}
