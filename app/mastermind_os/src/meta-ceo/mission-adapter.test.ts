import { describe, expect, it } from "vitest";
import { bindMissionHost, type RawClient } from "../host";
import { decodeMission, type MissionDocument } from "../mission";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";
import { captureMissionOfficeRead, completeMissionOfficeRead } from "./mission-adapter";
import { projectOffice, type ProjectionContext } from "./projection";

const context: ProjectionContext = {
  authGeneration: 3, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: null, bindingGeneration: null,
  revisions: { mission: null, programs: "programs:unchanged", result: null, conversation: null },
};
const acquiredAt = "2026-10-04T05:00:00Z";
const decoded = () => decodeMission(structuredClone(fixture), context.selection!)!;
function complete(document: MissionDocument | null = decoded(), current = context, pending = captureMissionOfficeRead(context)) {
  return completeMissionOfficeRead(pending, current, document, acquiredAt);
}
function accepted(result: ReturnType<typeof complete>) {
  expect(result.kind).toBe("observed");
  if (result.kind !== "observed") throw new Error("Expected a current-context observation");
  return result;
}
function projected(result: ReturnType<typeof accepted>) {
  return projectOffice({ mission: result.snapshot, programs: null, result: null, conversation: null }, result.context);
}

describe("Mission owner receipt to Office adapter", () => {
  it("qualifies an unmodified decoded owner fixture without inventing project or session provenance", () => {
    const document = decoded();
    const result = accepted(complete(document));
    const observation = document.source.owner_observation!;
    expect(result.snapshot.source.ref).toBe(observation.control_room!.document_digest);
    expect(result.snapshot.source.ref_kind).toBe("CONTROL_ROOM_DOCUMENT_DIGEST");
    expect(result.snapshot.source.observed_at).toBe(acquiredAt);
    expect(result.snapshot.source.observed_at_kind).toBe("LOCAL_ACQUISITION");
    expect(result.context.sessionRef).toBeNull();
    expect(result.context.bindingGeneration).toBeNull();
    expect(result.context.revisions.programs).toBe("programs:unchanged");
    expect(result.snapshot.context.revisions.mission).toBe(result.context.revisions.mission);
    expect(projected(result).mission.source.state).toBe("CURRENT");
    expect(projected(result).mission.value).toEqual(document);
    expect(projected(result).programs.source.state).toBe("UNAVAILABLE");
  });

  it("captures an immutable original context before a caller changes selection", () => {
    const mutable = structuredClone(context);
    const pending = captureMissionOfficeRead(mutable);
    mutable.selection!.workRef = "WS:CHANGED";
    mutable.revisions.mission = "changed";
    expect(pending.context).toEqual(context);
    expect(Object.isFrozen(pending.context.selection)).toBe(true);
    expect(Object.isFrozen(pending.context.revisions)).toBe(true);
  });

  it("discards all old-principal data on an actual host epoch change", async () => {
    let notify!: Parameters<RawClient["subscribe"]>[0];
    const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: true };
    const client: RawClient = {
      getState: () => signed, subscribe: listener => { notify = listener; return () => {}; },
      signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => ({}), readCurrentWindow: async () => ({}),
      readWork: async () => ({}),
      readMission: async () => structuredClone(fixture),
    };
    const host = bindMissionHost(client);
    const before = { ...context, authGeneration: host.invalidationGeneration!() };
    const pending = captureMissionOfficeRead(before);
    const document = decodeMission(await host.readMission!({ ...context.selection!, signal: new AbortController().signal }), context.selection!)!;
    notify({ ...signed, content: false });
    const result = completeMissionOfficeRead(pending, { ...before, authGeneration: host.invalidationGeneration!() }, document, acquiredAt);
    expect(result).toEqual({ kind: "discarded", state: "WITHHELD", reason: "AUTH_GENERATION_CHANGED" });
    expect(JSON.stringify(result)).not.toContain(fixture.program.title);
  });

  it.each([
    { selection: { workRef: "WS:OTHER", rootJobId: "JOB-1" } },
    { selection: { workRef: "WS:ONE", rootJobId: "JOB-2" } },
    { sessionRef: "session:other" }, { bindingGeneration: 2 },
  ])("discards a reply for changed target %j", change => {
    expect(complete(decoded(), { ...context, ...change })).toEqual({ kind: "discarded", state: "UNASSOCIATED", reason: "TARGET_CHANGED" });
  });

  it("does not accept an owner observation for a neighboring target", () => {
    const document = decoded();
    document.source.owner_observation!.selection!.work_ref = "WS:OTHER";
    expect(complete(document)).toEqual({ kind: "discarded", state: "UNASSOCIATED", reason: "OWNER_TARGET_CHANGED" });
  });

  it.each(["missing", "UNKNOWN", "CONFLICT"])("clears facts and the current revision for an unqualified %s observation", state => {
    const document = decoded();
    if (state === "missing") delete document.source.owner_observation;
    else document.source.owner_observation!.state = state as "UNKNOWN" | "CONFLICT";
    const current = { ...context, revisions: { ...context.revisions, mission: "previous" } };
    const result = accepted(complete(document, current, captureMissionOfficeRead(current)));
    expect(result.context.revisions.mission).toBeNull();
    expect(result.snapshot.source.ref).toBeNull();
    expect(result.snapshot.value).toBeNull();
    expect(projected(result).mission.source.state).toBe("UNKNOWN");
  });

  it("does not turn an unavailable acquisition into a healthy empty view", () => {
    const result = accepted(complete(null));
    expect(projected(result).mission.source.state).toBe("UNAVAILABLE");
    expect(projected(result).mission.value).toBeNull();
  });

  it.each(["selection", "document_digest", "source_identity", "generation"])("refuses incomplete or changed %s inside an asserted SAME receipt", field => {
    const document = decoded();
    const observation = document.source.owner_observation!;
    if (field === "selection") observation.selection = null;
    if (field === "document_digest") observation.control_room!.document_digest = null;
    if (field === "source_identity") observation.runtime!.source_identity = null;
    if (field === "generation") observation.runtime!.after = 99;
    const result = accepted(complete(document));
    expect(result.snapshot.source.state).toBe("UNKNOWN");
    expect(result.snapshot.source.ref).toBeNull();
    expect(result.snapshot.source.revision).toBeNull();
    expect(result.snapshot.value).toBeNull();
  });

  it("advances only the Mission revision and invalidates the old snapshot", () => {
    const old = accepted(complete());
    const document = decoded();
    document.source.owner_observation!.runtime!.snapshot_digest = "d".repeat(64);
    const next = accepted(complete(document, old.context, captureMissionOfficeRead(old.context)));
    expect(next.context.revisions.mission).not.toBe(old.context.revisions.mission);
    expect(next.context.revisions.programs).toBe(old.context.revisions.programs);
    const stale = projectOffice({ mission: old.snapshot, programs: null, result: null, conversation: null }, next.context);
    expect(stale.mission.reason).toBe("SOURCE_REVISION_CHANGED");
    expect(stale.mission.value).toBeNull();
    expect(projected(next).mission.source.state).toBe("CURRENT");
  });

  it("rejects a late same-target response after a different owner revision won", () => {
    const pending = captureMissionOfficeRead(context);
    const newer = decoded();
    newer.source.owner_observation!.runtime!.snapshot_digest = "d".repeat(64);
    const current = accepted(complete(newer)).context;
    expect(complete(decoded(), current, pending)).toEqual({ kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" });
    expect(complete(null, current, pending)).toEqual({ kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" });
  });

  it("does not let an older request replace a newer complete result even when its late partial reply names the winning revision", () => {
    const pending = captureMissionOfficeRead(context);
    const newer = decoded();
    newer.source.owner_observation!.runtime!.snapshot_digest = "d".repeat(64);
    const winner = accepted(complete(newer));
    const late = structuredClone(newer);
    late.read_state.state = "PARTIAL";
    expect(complete(late, winner.context, pending)).toEqual({ kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" });
    expect(projected(winner).mission.source.state).toBe("CURRENT");
  });

  it("never uses title or local acquisition time as a source revision", () => {
    const first = accepted(complete());
    const document = decoded();
    document.program.title = "A presentation title is not a revision";
    const second = accepted(completeMissionOfficeRead(captureMissionOfficeRead(context), context, document, "2026-10-05T05:00:00Z"));
    expect(second.snapshot.source.revision).toBe(first.snapshot.source.revision);
    expect(second.snapshot.source.observed_at).not.toBe(first.snapshot.source.observed_at);
  });

  it("retains partial sections without claiming complete owner coverage", () => {
    const document = decoded();
    document.read_state.state = "PARTIAL";
    const result = projected(accepted(complete(document)));
    expect(result.mission.value).not.toBeNull();
    expect(result.mission.source.state).toBe("UNKNOWN");
    expect(result.mission.source.coverage).toBe("INCOMPLETE");
  });

  it("cannot qualify provenance with an invalid local acquisition timestamp", () => {
    const result = accepted(completeMissionOfficeRead(captureMissionOfficeRead(context), context, decoded(), "not a timestamp"));
    expect(projected(result).mission.source.state).toBe("UNKNOWN");
    expect(result.snapshot.source.observed_at).toBeNull();
    expect(result.snapshot.value).toBeNull();
  });
});
