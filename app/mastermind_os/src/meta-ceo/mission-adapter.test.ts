// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { bindMissionHost, type RawClient } from "../host";
import { decodeMission, type MissionDocument, type Missionv3Document } from "../mission";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";
import { decodeMissionResultBytes } from "../mission-result";
import { normalizeResultSelection, type ResultEnvelopeDigestShape, type ResultSelection } from "../result";
import { captureMissionOfficeRead, completeMissionOfficeRead, completeMissionResultOfficeRead, captureMissionResultOfficeRead } from "./mission-adapter";
import { projectOffice, type ProjectionContext } from "./projection";
import { useOfficeProjection } from "./useOfficeProjection";

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

describe("compound Mission/Result presentation", () => {
  const acquiredAt = "2026-10-24T21:40:00Z";
  let selection: ResultSelection;
  let mission: Missionv3Document;
  let result: ResultEnvelopeDigestShape;
  const load = async () => {
    if (mission) return;
    const cwd = (globalThis as { process?: { cwd?: () => string } }).process?.cwd?.();
    if (!cwd) throw new Error("producer fixture path requires the vitest worker cwd");
    // @ts-expect-error node:fs/promises is resolved by the vitest worker.
    const fs = (await import("node:fs/promises")) as { readFile(path: string): Promise<Uint8Array> };
    const bytes = new Uint8Array(await fs.readFile(
      `${cwd}/src/meta-ceo/fixtures/mission-result-producer/actual-pair.json`,
    ));
    const wire = (JSON.parse(new TextDecoder().decode(bytes)) as { selection: Record<string, string> }).selection;
    const normalized = normalizeResultSelection({
      workRef: wire.work_ref, rootJobId: wire.root_job_id, jobId: wire.job_id,
      attemptId: wire.attempt_id, resultEnvelopeDigest: wire.result_envelope_digest,
    });
    if (!normalized) throw new Error("producer selection missing");
    const decoded = decodeMissionResultBytes(bytes, normalized);
    if (!decoded.ok || decoded.document.availability !== "AVAILABLE")
      throw new Error("producer bytes did not yield a pair");
    selection = normalized;
    mission = decoded.document.mission;
    result = decoded.document.roleResult;
  };

  it("publishes both revisions from the unchanged producer bytes and discards a late pair", async () => {
    await load();
    const base: ProjectionContext = {
      authGeneration: 1,
      selection: { workRef: selection.workRef, rootJobId: selection.rootJobId },
      sessionRef: null, bindingGeneration: null,
      revisions: { mission: null, programs: "programs:kept", result: null, conversation: null },
    };
    const pending = captureMissionResultOfficeRead(base, 1);
    const observed = completeMissionResultOfficeRead(pending, base, mission, result, acquiredAt);
    expect(observed.kind).toBe("observed");
    if (observed.kind !== "observed") return;
    expect(observed.context.revisions.programs).toBe("programs:kept");
    expect(observed.context.revisions.mission).toBe(observed.mission.source.revision);
    expect(observed.context.revisions.result).toBe(observed.result.source.revision);
    expect(observed.mission.source.observed_at_kind).toBe("LOCAL_ACQUISITION");
    expect(observed.result.source.observed_at_kind).toBe("LOCAL_ACQUISITION");
    expect(observed.context.sessionRef).toBeNull();
    expect(observed.context.bindingGeneration).toBeNull();
    const projection = projectOffice(
      { mission: observed.mission, programs: null, result: observed.result, conversation: null },
      observed.context,
    );
    expect(projection.result.value?.result?.review?.verdict).toBe("reject");
    expect(projection.result.value?.result?.acceptance).toBe("NOT_PROJECTED");
    expect(projection.result.value?.result?.execution_status).toBe("COMPLETED");
    expect(projection.receipts.review).not.toBe("reject");
    expect(projection.receipts.acceptance).toBe("NOT_PROJECTED");
    expect(projection.receipts.return).toBe("RETURNED");
    const late = completeMissionResultOfficeRead(pending, observed.context, mission, result, acquiredAt);
    expect(late).toEqual({ kind: "discarded", state: "STALE", reason: "READ_SUPERSEDED" });
    expect(projectOffice(
      { mission: observed.mission, programs: null, result: observed.result, conversation: null },
      observed.context,
    ).result.value).not.toBeNull();
  });

  it("refuses a synthetic crossed tuple through projectOffice instead of relaxing the join", async () => {
    await load();
    const base: ProjectionContext = {
      authGeneration: 1,
      selection: { workRef: selection.workRef, rootJobId: selection.rootJobId },
      sessionRef: null, bindingGeneration: null,
      revisions: { mission: null, programs: null, result: null, conversation: null },
    };
    const crossed = structuredClone(result);
    crossed.selection.result_envelope_digest = "f".repeat(64);
    const outcome = completeMissionResultOfficeRead(
      captureMissionResultOfficeRead(base, 1), base, mission, crossed, acquiredAt,
    );
    expect(outcome).toMatchObject({ kind: "discarded", reason: "RESULT_TUPLE_NOT_ASSOCIATED" });
  });

  it("keeps a synthetic nested content-budget result associated and incomplete", async () => {
    await load();
    const fallback = structuredClone(result);
    if (!fallback.result) throw new Error("producer result has no role view");
    fallback.availability = "CONTENT_OVER_BUDGET";
    fallback.reason_codes = ["CONTENT_OVER_BUDGET"];
    fallback.result.availability = "CONTENT_OVER_BUDGET";
    fallback.result.content = null;
    fallback.result.content_complete = false;
    fallback.result.omitted = ["role_result", "summary", "next_actions"];
    const base: ProjectionContext = {
      authGeneration: 1,
      selection: { workRef: selection.workRef, rootJobId: selection.rootJobId },
      sessionRef: null, bindingGeneration: null,
      revisions: { mission: null, programs: null, result: null, conversation: null },
    };
    const observed = completeMissionResultOfficeRead(
      captureMissionResultOfficeRead(base, 4), base, mission, fallback, acquiredAt,
    );
    expect(observed.kind).toBe("observed");
    if (observed.kind !== "observed") return;
    const projection = projectOffice(
      { mission: observed.mission, programs: null, result: observed.result, conversation: null },
      observed.context,
    );
    expect(projection.result.reason).toBe("CONTENT_OVER_BUDGET");
    expect(projection.result.source.coverage).toBe("INCOMPLETE");
    expect(projection.result.value?.result?.content).toBeNull();
    expect(projection.result.value?.result?.review?.verdict).toBe("reject");
  });

  it("commits and fences the pair through the hook refs without a programs reset", async () => {
    await load();
    const hook = renderHook(() => useOfficeProjection(1, { workRef: selection.workRef, rootJobId: selection.rootJobId }));
    let first!: ReturnType<typeof hook.result.current.beginMissionResult>;
    act(() => { first = hook.result.current.beginMissionResult(); });
    act(() => { hook.result.current.acceptMissionResult(first, mission, result, acquiredAt); });
    expect(hook.result.current.projection.result.value?.selection.job_id).toBe(selection.jobId);
    expect(hook.result.current.projection.mission.value?.schema).toBe("mastermind.mission_workspace.v3");
    const programsBefore = hook.result.current.projection.programs;
    act(() => { hook.result.current.beginPrograms(); });
    expect(hook.result.current.projection.result.value?.selection.job_id).toBe(selection.jobId);
    expect(hook.result.current.projection.programs.source.state).toBe(programsBefore.source.state);
    let second!: ReturnType<typeof hook.result.current.beginMissionResult>;
    act(() => { second = hook.result.current.beginMissionResult(); });
    act(() => { hook.result.current.acceptMissionResult(first, mission, result, acquiredAt); });
    expect(hook.result.current.projection.result.value).toBeNull();
    act(() => { hook.result.current.acceptMissionResult(second, mission, result, acquiredAt); });
    expect(hook.result.current.projection.result.value?.selection.job_id).toBe(selection.jobId);
    const visible = hook.result.current.projection.result.value?.result?.content?.summary;
    act(() => { hook.result.current.supersedePair(); });
    expect(hook.result.current.projection.result.value).toBeNull();
    expect(hook.result.current.projection.mission.value).toBeNull();
    expect(visible).toBe("bounded typed fixture result");
  });
});
