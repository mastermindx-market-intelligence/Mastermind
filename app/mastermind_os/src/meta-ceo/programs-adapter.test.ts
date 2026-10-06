import { describe, expect, it } from "vitest";
import fixture from "../fixtures/programs-available-workspace-service.json";
import { controlRoomFixture } from "../test-fixtures";
import { decodeProgramsObservation } from "../programs-observation";
import { captureProgramsOfficeRead, completeProgramsOfficeRead } from "./programs-adapter";
import { projectOffice, type ProjectionContext } from "./projection";

const context: ProjectionContext = {
  authGeneration: 3, selection: null, sessionRef: null, bindingGeneration: null,
  revisions: { mission: "mission:unchanged", programs: null, result: null, conversation: null },
};
const acquiredAt = "2026-10-04T06:45:00Z";
// The service fixture alone is an intentionally minimal structural envelope.
// Inject the existing full consumer fixture for strict ProgramCard qualification.
const envelope = () => ({ ...structuredClone(fixture), control_room: controlRoomFixture() });
const document = () => decodeProgramsObservation(envelope());
function complete(doc = document(), current = context, pending = captureProgramsOfficeRead(context), at = acquiredAt) {
  return completeProgramsOfficeRead(pending, current, doc, at);
}
function observed(result: ReturnType<typeof complete>) {
  expect(result.kind).toBe("observed");
  if (result.kind !== "observed") throw new Error("Expected current-context observation");
  return result;
}

describe("Programs collection owner receipt to Office", () => {
  it("qualifies only the supplied collection, keeping Mission revision and target unchanged", () => {
    const doc = document(), result = observed(complete(doc));
    const source = result.snapshot.source;
    expect(source.state).toBe("CURRENT");
    expect(source.ref).toBe(doc.observation!.control_room!.document_digest);
    expect(source.ref_kind).toBe("CONTROL_ROOM_DOCUMENT_DIGEST");
    expect(source.observed_at).toBe(acquiredAt);
    expect(source.observed_at_kind).toBe("LOCAL_ACQUISITION");
    expect(source.coverage).toBe("SUPPLIED_COLLECTION");
    expect(result.context.revisions.mission).toBe("mission:unchanged");
    expect(result.context.selection).toBeNull();
    const view = projectOffice({ mission: null, programs: result.snapshot, result: null, conversation: null }, result.context);
    expect(view.programs.source.state).toBe("CURRENT");
    expect(view.programs.value?.state).toBe("AVAILABLE");
    expect(view.companyTotal).toBeNull();
  });

  it("uses the existing service-attested receipt boundary without claiming frontend digest recomputation", () => {
    const raw = envelope();
    raw.source_observation.control_room.document_digest = "a".repeat(64);
    const result = observed(complete(decodeProgramsObservation(raw)));
    expect(result.snapshot.source.state).toBe("CURRENT");
    expect(result.snapshot.source.ref).toBe("a".repeat(64));
  });

  it("captures context independently and freezes its selection and revisions", () => {
    const mutable = structuredClone(context);
    mutable.selection = { workRef: "WS:ONE", rootJobId: "JOB-1" };
    const pending = captureProgramsOfficeRead(mutable);
    mutable.selection.workRef = "WS:OTHER";
    mutable.revisions.programs = "later";
    expect(pending.context.selection?.workRef).toBe("WS:ONE");
    expect(pending.context.revisions.programs).toBeNull();
    expect(Object.isFrozen(pending.context.selection)).toBe(true);
    expect(Object.isFrozen(pending.context.revisions)).toBe(true);
  });

  it("discards old-principal data before looking at its content", () => {
    expect(complete(document(), { ...context, authGeneration: 4 })).toEqual({ kind: "discarded", state: "WITHHELD", reason: "AUTH_GENERATION_CHANGED" });
  });
  it.each([
    { selection: { workRef: "WS:OTHER", rootJobId: "JOB-2" } },
    { sessionRef: "session:other" }, { bindingGeneration: 2 },
  ])("does not carry the collection across a changed target %j", change => {
    expect(complete(document(), { ...context, ...change })).toEqual({ kind: "discarded", state: "UNASSOCIATED", reason: "TARGET_CHANGED" });
  });
  it("discards even an agreeing receipt after a later read won the Programs revision", () => {
    const winner = observed(complete());
    expect(complete(document(), winner.context)).toEqual({ kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" });
  });

  it.each(["UNKNOWN", "CONFLICT"] as const)("does not promote %s collection observations", state => {
    const doc = document();
    doc.observation!.state = state;
    const result = observed(complete(doc));
    expect(result.snapshot.source.state).toBe("UNKNOWN");
    expect(result.snapshot.value).toBeNull();
    expect(result.snapshot.source.ref).toBeNull();
    expect(result.context.revisions.programs).toBeNull();
  });
  it.each(["digest", "publication", "selection", "runtime"])("revalidates caller-held %s receipt fields", field => {
    const doc = document();
    if (field === "digest") doc.observation!.control_room!.document_digest = null;
    if (field === "publication") doc.observation!.control_room!.publication_after!++;
    if (field === "selection") doc.observation!.selection = { work_ref: "WS:ONE", root_job_id: "JOB-1" };
    if (field === "runtime") doc.observation!.runtime = {} as never;
    const result = observed(complete(doc));
    expect(result.snapshot.source.state).toBe("UNKNOWN");
    expect(result.snapshot.value).toBeNull();
    expect(result.snapshot.source.revision).toBeNull();
  });

  it("retains unavailable owner reasons and clears any caller-held content or provenance", () => {
    const doc = document();
    doc.availability = "UNAVAILABLE";
    doc.reasonCodes = ["OWNER_OFFLINE"];
    const result = observed(complete(doc));
    expect(result.snapshot.source.state).toBe("UNAVAILABLE");
    expect(result.snapshot.value).toBeNull();
    expect(result.snapshot.source.ref).toBeNull();
    expect(result.reasonCodes).toEqual(["OWNER_OFFLINE"]);
  });
  it.each(["duplicate", "generation"])("refuses qualified receipt with invalid %s collection content", defect => {
    const doc = document(), room = doc.controlRoom as ReturnType<typeof controlRoomFixture>;
    if (defect === "duplicate") room.work.push(structuredClone(room.work[0]!));
    else room.autonomy.generated_at = "2026-10-01T00:00:00Z";
    const result = observed(complete(doc));
    expect(result.snapshot.source.state).toBe("UNAVAILABLE");
    expect(result.snapshot.value).toBeNull();
    expect(result.reasonCodes).toContain(defect === "duplicate" ? "DUPLICATE_WORK_REF" : "GENERATION_MISMATCH");
  });
  it("does not turn failed acquisition into a healthy empty list", () => {
    const result = observed(completeProgramsOfficeRead(captureProgramsOfficeRead(context), context, null, acquiredAt));
    expect(result.snapshot.source.state).toBe("UNAVAILABLE");
    expect(result.snapshot.value).toBeNull();
  });
  it("keeps a qualified empty supplied collection distinct from unavailable", () => {
    const doc = document(), room = doc.controlRoom as ReturnType<typeof controlRoomFixture>;
    room.work = []; room.autonomy.responsibilities = [];
    const result = observed(complete(doc));
    expect(result.snapshot.source.state).toBe("CURRENT");
    expect(result.snapshot.value?.programs).toEqual([]);
  });
  it("requires a valid local acquisition time without borrowing a producer clock", () => {
    const result = observed(complete(document(), context, captureProgramsOfficeRead(context), "not-a-date"));
    expect(result.snapshot.source.state).toBe("UNKNOWN");
    expect(result.snapshot.source.observed_at).toBeNull();
    expect(result.snapshot.value).toBeNull();
  });
  it("derives revisions from the service receipt rather than labels or local clocks", () => {
    const first = observed(complete()), doc = document();
    const room = doc.controlRoom as ReturnType<typeof controlRoomFixture>;
    room.generated_at = room.autonomy.generated_at = "2026-10-03T01:00:00Z";
    const relabeled = observed(complete(doc, context, captureProgramsOfficeRead(context), "2026-10-04T06:46:00Z"));
    expect(relabeled.snapshot.source.revision).toBe(first.snapshot.source.revision);
    doc.observation!.control_room!.document_digest = "b".repeat(64);
    expect(observed(complete(doc)).snapshot.source.revision).not.toBe(first.snapshot.source.revision);
  });
});
