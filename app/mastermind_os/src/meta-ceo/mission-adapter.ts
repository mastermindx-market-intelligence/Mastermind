/** Presentation adapter only: the existing MissionHost owns acquisition and decoding. */
import type { MissionDocument, Missionv3Document } from "../mission";
import { decodeOwnerObservation } from "../workspace-contract";
import { sameTarget, type ProjectionContext, type ReadSnapshot, type SourceClaim } from "./projection";

type Document = MissionDocument | Missionv3Document;
export interface PendingMissionOfficeRead { readonly context: ProjectionContext }
export type MissionOfficeObservation =
  | { kind: "observed"; context: ProjectionContext; snapshot: ReadSnapshot<Document> }
  | { kind: "discarded"; state: "WITHHELD" | "UNASSOCIATED" | "STALE"; reason: string };

/** Call before acquisition, with the actual MissionHost invalidation generation. */
export function captureMissionOfficeRead(current: ProjectionContext): PendingMissionOfficeRead {
  const context = structuredClone(current);
  if (context.selection) Object.freeze(context.selection);
  Object.freeze(context.revisions);
  Object.freeze(context);
  return Object.freeze({ context });
}

function ownerRevision(document: Document | null): string | null {
  if (!document?.mission.root_job_id) return null;
  // Reuse the owner decoder at the presentation boundary. The DTO types also
  // represent incomplete observations; a caller-held object is not a grant.
  const observation = decodeOwnerObservation(document.source.owner_observation, {
    work_ref: document.program.work_ref, root_job_id: document.mission.root_job_id,
  });
  const control = observation?.control_room, runtime = observation?.runtime;
  if (observation?.state !== "SAME" || !observation.selection || !control || runtime?.state !== "SAME") return null;
  // This tagged tuple is a presentation identity for decoded owner receipts.
  // It is not a new owner revision, local sequence, session or authority.
  return "mission-owner-observation:v1:" + JSON.stringify([
    observation.schema, observation.selection.work_ref, observation.selection.root_job_id,
    control.instance_before, control.instance_after,
    control.publication_before, control.publication_after,
    control.document_digest, control.source_validity_digest, control.cache_currentness_digest,
    runtime.schema, runtime.source_identity, runtime.before, runtime.after, runtime.snapshot_digest,
  ]);
}

/**
 * Call with freshly observed host/selection context after the decoded read completes.
 * Commit an observed snapshot and its context together; discard replies never replace
 * the current view. The local completion time is labelled acquisition, not owner time.
 */
export function completeMissionOfficeRead(
  pending: PendingMissionOfficeRead,
  current: ProjectionContext,
  document: Document | null,
  localAcquiredAt: string,
): MissionOfficeObservation {
  if (pending.context.authGeneration !== current.authGeneration)
    return { kind: "discarded", state: "WITHHELD", reason: "AUTH_GENERATION_CHANGED" };
  if (!sameTarget(pending.context, current))
    return { kind: "discarded", state: "UNASSOCIATED", reason: "TARGET_CHANGED" };
  const observation = document?.source.owner_observation;
  if (document && (!current.selection || document.program.work_ref !== current.selection.workRef ||
      document.mission.root_job_id !== current.selection.rootJobId ||
      observation?.selection && (observation.selection.work_ref !== current.selection.workRef ||
        observation.selection.root_job_id !== current.selection.rootJobId)))
    return { kind: "discarded", state: "UNASSOCIATED", reason: "OWNER_TARGET_CHANGED" };

  const revision = ownerRevision(document);
  // A later read already won this source. Even an agreeing digest cannot let an
  // older partial/historical response replace the winner's complete observation.
  if (current.revisions.mission !== pending.context.revisions.mission)
    return { kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" };

  const validTime = /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(localAcquiredAt) && Number.isFinite(Date.parse(localAcquiredAt));
  const qualified = revision !== null && validTime;
  const source: SourceClaim = {
    owner: "EXECUTIVE_OS",
    ref: qualified ? observation!.control_room!.document_digest : null,
    ref_kind: "CONTROL_ROOM_DOCUMENT_DIGEST",
    revision: qualified ? revision : null,
    observed_at: validTime ? localAcquiredAt : null,
    observed_at_kind: "LOCAL_ACQUISITION",
    state: !document || document.read_state.state === "UNAVAILABLE" ? "UNAVAILABLE" :
      !qualified ? "UNKNOWN" : document.read_state.state === "HISTORICAL" ? "STALE" : "CURRENT",
    coverage: document?.read_state.state === "CURRENT" ? "COMPLETE" : "INCOMPLETE",
  };
  const context = structuredClone(current);
  context.revisions.mission = source.revision;
  return {
    kind: "observed", context,
    snapshot: {
      context: structuredClone(context), source,
      value: qualified && source.state !== "UNAVAILABLE" ? structuredClone(document) : null,
    },
  };
}
