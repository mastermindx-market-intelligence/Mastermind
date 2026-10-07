import { describe, expect, it } from "vitest";
import available from "./fixtures/programs-available-workspace-service.json";
import { decodeProgramsEnvelope } from "./workspace-contract";
import { decodeProgramsObservation } from "./programs-observation";

describe("Programs receipt-preserving companion decoder", () => {
  it("preserves one detached collection receipt and its Control Room from the same envelope", () => {
    const raw = structuredClone(available);
    const decoded = decodeProgramsObservation(raw);
    expect(decoded.availability).toBe("AVAILABLE");
    expect(decoded.controlRoom).toEqual(decodeProgramsEnvelope(raw));
    expect(decoded.observation).toEqual(raw.source_observation);
    expect(decoded.observation?.selection).toBeNull();
    expect(decoded.observation?.runtime).toBeNull();
    raw.source_observation.control_room.document_digest = "a".repeat(64);
    expect(decoded.observation?.control_room?.document_digest).not.toBe("a".repeat(64));
  });

  it("clears content and provenance for UNAVAILABLE even if a valid-looking receipt and content are supplied", () => {
    const raw = { ...structuredClone(available), availability: "UNAVAILABLE", reason_codes: ["CONTROL_ROOM_UNAVAILABLE"] };
    const decoded = decodeProgramsObservation(raw);
    expect(decoded).toEqual({ availability: "UNAVAILABLE", controlRoom: null, observation: null, reasonCodes: ["CONTROL_ROOM_UNAVAILABLE"] });
    expect(() => decodeProgramsEnvelope(raw)).toThrow("PROGRAM_SOURCE_UNAVAILABLE");
  });

  it.each(["UNKNOWN", "CONFLICT"])("preserves %s owner state without releasing content", state => {
    const raw = structuredClone(available);
    raw.source_observation.state = state;
    const decoded = decodeProgramsObservation(raw);
    expect(decoded.observation?.state).toBe(state);
    expect(decoded.controlRoom).toBeNull();
    expect(() => decodeProgramsEnvelope(raw)).toThrow("PROGRAM_SOURCE_UNQUALIFIED");
  });

  it.each(["extra", "digest", "selection", "runtime"])("retains the canonical refusal for malformed %s", field => {
    const raw: any = structuredClone(available);
    if (field === "extra") raw.borrowed_mission = {};
    if (field === "digest") raw.source_observation.control_room.document_digest = "not-a-digest";
    if (field === "selection") raw.source_observation.selection = { work_ref: "WS:ONE", root_job_id: "JOB-1" };
    if (field === "runtime") raw.source_observation.runtime = {};
    expect(() => decodeProgramsObservation(raw)).toThrow(/PROGRAM_(RESPONSE|OBSERVATION)_INVALID/);
  });
});
