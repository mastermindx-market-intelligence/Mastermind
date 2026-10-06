/** Companion to the existing fixed-response decoder; no acquisition or new owner schema. */
import { decodeOwnerObservation, decodeProgramsEnvelope, type OwnerObservation } from "./workspace-contract";

export interface ProgramsObservation {
  availability: "AVAILABLE" | "UNAVAILABLE";
  controlRoom: unknown | null;
  observation: OwnerObservation | null;
  reasonCodes: readonly string[];
}

/**
 * Retain the receipt from the SAME raw response validated by the canonical decoder.
 * Only its two known source-negative refusals become data. Structural refusals still
 * throw, and legacy decodeProgramsEnvelope/readPrograms behavior is unchanged.
 * Digests are service-attested references, not frontend-recomputed content hashes.
 */
export function decodeProgramsObservation(value: unknown): ProgramsObservation {
  const copy: unknown = structuredClone(value);
  let controlRoom: unknown | null = null;
  try {
    controlRoom = decodeProgramsEnvelope(copy);
  } catch (error) {
    if (!(error instanceof Error) ||
        !["PROGRAM_SOURCE_UNAVAILABLE", "PROGRAM_SOURCE_UNQUALIFIED"].includes(error.message)) throw error;
  }
  // All successful and source-negative paths above validated the closed envelope,
  // reason codes and collection observation before returning/throwing these results.
  const envelope = copy as {
    availability: "AVAILABLE" | "UNAVAILABLE";
    source_observation: unknown;
    reason_codes: string[];
  };
  const unavailable = envelope.availability === "UNAVAILABLE";
  return {
    availability: envelope.availability,
    controlRoom: unavailable ? null : controlRoom,
    observation: unavailable ? null : decodeOwnerObservation(envelope.source_observation, null),
    reasonCodes: [...envelope.reason_codes],
  };
}
