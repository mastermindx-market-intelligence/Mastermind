/** Read-only presentation of the existing authenticated service's collection receipt. */
import { programsFromControlRoom } from "../mission";
import type { ProgramsObservation } from "../programs-observation";
import { decodeOwnerObservation } from "../workspace-contract";
import { sameTarget, type ProjectionContext, type ReadSnapshot, type SourceClaim, type SourceState } from "./projection";

export interface PendingProgramsOfficeRead { readonly context: ProjectionContext }
export type ProgramsOfficeObservation =
  | { kind: "observed"; context: ProjectionContext; snapshot: ReadSnapshot<ReturnType<typeof programsFromControlRoom>>; reasonCodes: readonly string[] }
  | { kind: "discarded"; state: "WITHHELD" | "UNASSOCIATED" | "STALE"; reason: string };

/** Capture the actual host generation before its single fixed Programs acquisition. */
export function captureProgramsOfficeRead(current: ProjectionContext): PendingProgramsOfficeRead {
  const context = structuredClone(current);
  if (context.selection) Object.freeze(context.selection);
  Object.freeze(context.revisions);
  Object.freeze(context);
  return Object.freeze({ context });
}

/**
 * Commit context and snapshot together; a discarded read cannot replace a winner.
 * The host must preserve the full fixed-service receipt with its original response.
 * A bare legacy Control Room, Mission receipt or UI epoch cannot qualify Programs.
 */
export function completeProgramsOfficeRead(
  pending: PendingProgramsOfficeRead,
  current: ProjectionContext,
  document: ProgramsObservation | null,
  localAcquiredAt: string,
): ProgramsOfficeObservation {
  if (pending.context.authGeneration !== current.authGeneration)
    return { kind: "discarded", state: "WITHHELD", reason: "AUTH_GENERATION_CHANGED" };
  if (!sameTarget(pending.context, current))
    return { kind: "discarded", state: "UNASSOCIATED", reason: "TARGET_CHANGED" };
  if (pending.context.revisions.programs !== current.revisions.programs)
    return { kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" };

  const observation = decodeOwnerObservation(document?.observation, null);
  const control = observation?.control_room;
  const validTime = /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(localAcquiredAt) && Number.isFinite(Date.parse(localAcquiredAt));
  let state: SourceState = "UNAVAILABLE";
  let reasonCodes: readonly string[] = document?.reasonCodes ?? ["PROGRAM_SOURCE_UNAVAILABLE"];
  let value: ReturnType<typeof programsFromControlRoom> | null = null;
  let revision: string | null = null;
  if (document?.availability === "AVAILABLE") {
    if (observation?.state !== "SAME" || !control) {
      state = "UNKNOWN";
      reasonCodes = [...reasonCodes, "PROGRAM_OWNER_OBSERVATION_UNQUALIFIED"];
    } else {
      const programs = programsFromControlRoom(document.controlRoom);
      if (programs.state !== "AVAILABLE") {
        reasonCodes = [...reasonCodes, programs.reason];
      } else if (!validTime) {
        state = "UNKNOWN";
        reasonCodes = [...reasonCodes, "LOCAL_ACQUISITION_TIME_INVALID"];
      } else {
        state = "CURRENT";
        value = programs;
        // A presentation identity for the collection receipt; not a new owner revision.
        revision = "programs-owner-observation:v1:" + JSON.stringify([
          observation.schema, observation.selection,
          control.instance_before, control.instance_after,
          control.publication_before, control.publication_after,
          control.document_digest, control.source_validity_digest, control.cache_currentness_digest,
        ]);
      }
    }
  }
  const source: SourceClaim = {
    owner: "AGENT_OS", // Program orientation owner; the fixed service attests the receipt.
    ref: state === "CURRENT" ? control!.document_digest : null,
    ref_kind: "CONTROL_ROOM_DOCUMENT_DIGEST",
    revision,
    observed_at: validTime ? localAcquiredAt : null,
    observed_at_kind: "LOCAL_ACQUISITION",
    state,
    coverage: state === "CURRENT" ? "SUPPLIED_COLLECTION" : "NOT_PROJECTED",
  };
  const context = structuredClone(current);
  context.revisions.programs = revision;
  return {
    kind: "observed", context, reasonCodes: [...reasonCodes],
    snapshot: { context: structuredClone(context), source, value: structuredClone(value) },
  };
}
