import { describe, expect, it } from "vitest";
import { programsFromControlRoom } from "./mission";
import { controlRoomFixture, realControlRoomFixture } from "./test-fixtures";
import { resolveWorkMissionLink } from "./work-mission-link";

const input = () => ({
  rootJobId: "JOB-A",
  programs: programsFromControlRoom(controlRoomFixture()),
  acquisitionAllowed: true,
  workObservationAvailable: true,
});

describe("Work-to-Mission navigation boundary", () => {
  it("consumes the untouched recorded Control Room through the shipping Programs mapper", () => {
    const programs = programsFromControlRoom(realControlRoomFixture());
    expect(programs.state).toBe("AVAILABLE");
    const row = programs.programs.find((p) => p.rootState === "RESOLVED");
    expect(row).toBeDefined();
    const result = resolveWorkMissionLink({
      ...input(),
      programs,
      rootJobId: row!.rootJobId!,
    });
    expect(result).toMatchObject({
      state: "RESOLVED",
      selection: { workRef: row!.workRef, rootJobId: row!.rootJobId },
    });
  });
  it("uses the exact normalized pair and the title only as presentation", () => {
    const x = input();
    x.programs.programs[0].title = "Same name as another mission";
    x.programs.programs[1].title = "Same name as another mission";
    expect(resolveWorkMissionLink(x)).toEqual({
      state: "RESOLVED",
      rootJobId: "JOB-A",
      selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
      title: "Same name as another mission",
    });
  });
  it.each(["acquisitionAllowed", "workObservationAvailable"] as const)(
    "fails closed after %s is withdrawn",
    (key) => {
      expect(resolveWorkMissionLink({ ...input(), [key]: false }).state).toBe(
        "UNAVAILABLE",
      );
    },
  );
  it("distinguishes an unavailable source from a missing root", () => {
    expect(
      resolveWorkMissionLink({ ...input(), programs: null }),
    ).toMatchObject({ state: "UNAVAILABLE", reason: "PROGRAMS_UNAVAILABLE" });
    expect(
      resolveWorkMissionLink({
        ...input(),
        programs: programsFromControlRoom(null),
      }),
    ).toMatchObject({ reason: "PROGRAMS_UNAVAILABLE" });
    expect(
      resolveWorkMissionLink({ ...input(), rootJobId: "JOB-OTHER" }),
    ).toMatchObject({ reason: "ROOT_UNJOINED" });
  });
  it("rejects two resolved Programs for the same root", () => {
    const x = input();
    x.programs.programs[1].rootJobId = "JOB-A";
    x.programs.programs[1].rootCandidates = ["JOB-A"];
    expect(resolveWorkMissionLink(x)).toMatchObject({
      state: "UNAVAILABLE",
      reason: "ROOT_CONFLICT",
    });
  });
  it.each(["UNKNOWN", "CONFLICT"] as const)(
    "rejects a competing %s candidate without hiding the root",
    (state) => {
      const x = input();
      x.programs.programs[1].rootState = state;
      x.programs.programs[1].rootJobId = null;
      x.programs.programs[1].rootCandidates = ["JOB-A", "JOB-B"];
      expect(resolveWorkMissionLink(x)).toMatchObject({
        state: "UNAVAILABLE",
        rootJobId: "JOB-A",
        reason: "ROOT_CONFLICT",
      });
    },
  );
  it.each([
    { candidates: ["JOB-B"] },
    { candidates: ["JOB-A", "JOB-B"] },
    { candidates: ["JOB-A", "JOB-A"] },
    { candidates: [] },
  ])(
    "rejects non-singleton or mismatched candidates $candidates",
    ({ candidates }) => {
      const x = input();
      x.programs.programs[0].rootCandidates = candidates;
      expect(resolveWorkMissionLink(x).state).toBe("UNAVAILABLE");
    },
  );
  it.each(["UNKNOWN", "CONFLICT"] as const)(
    "never upgrades a selected %s row",
    (state) => {
      const x = input();
      x.programs.programs[0].rootState = state;
      expect(resolveWorkMissionLink(x).state).toBe("UNAVAILABLE");
    },
  );
  it("uses the existing selector validator instead of creating an arbitrary pair", () => {
    const x = input();
    x.programs.programs[0].workRef = "https://untrusted.invalid/mission";
    expect(resolveWorkMissionLink(x)).toMatchObject({
      state: "UNAVAILABLE",
      reason: "PROGRAMS_INVALID",
    });
  });
  it("refuses duplicate work refs rather than guessing which copy is current", () => {
    const x = input();
    x.programs.programs[1].workRef = x.programs.programs[0].workRef;
    expect(resolveWorkMissionLink(x)).toMatchObject({
      reason: "PROGRAMS_INVALID",
    });
  });
  it("does not mutate its source projection or return a borrowed selector", () => {
    const x = input(),
      before = JSON.stringify(x);
    const a = resolveWorkMissionLink(x),
      b = resolveWorkMissionLink(x);
    expect(JSON.stringify(x)).toBe(before);
    expect(a).toEqual(b);
    if (a.state === "RESOLVED" && b.state === "RESOLVED")
      expect(a.selection).not.toBe(b.selection);
  });
  it("accepts a qualified pair without inventing a missing title", () => {
    const x = input();
    x.programs.programs[0].title = null;
    expect(resolveWorkMissionLink(x)).toMatchObject({
      state: "RESOLVED",
      title: null,
    });
  });
  it("refuses a source index beyond the existing 500-row bound", () => {
    const x = input(),
      row = x.programs.programs[1];
    x.programs.programs = [
      x.programs.programs[0],
      ...Array.from({ length: 500 }, (_, i) => ({
        ...row,
        workRef: `WS:EXTRA-${i}`,
      })),
    ];
    expect(resolveWorkMissionLink(x)).toMatchObject({
      reason: "PROGRAMS_INVALID",
    });
  });
  it("refuses more than 50 candidate identifiers", () => {
    const x = input();
    x.programs.programs[1].rootCandidates = Array.from(
      { length: 51 },
      (_, i) => `JOB-X-${i}`,
    );
    expect(resolveWorkMissionLink(x)).toMatchObject({
      reason: "PROGRAMS_INVALID",
    });
  });
  it("refuses a malformed in-process row without throwing or selecting a partial index", () => {
    const x = input();
    (x.programs.programs as unknown[])[1] = null;
    expect(resolveWorkMissionLink(x)).toMatchObject({
      reason: "PROGRAMS_INVALID",
    });
  });
  it("distinguishes a valid empty Programs result from unavailable Programs", () => {
    const x = input();
    x.programs.programs = [];
    expect(resolveWorkMissionLink(x)).toMatchObject({
      reason: "ROOT_UNJOINED",
    });
  });
  it("allows unrelated unresolved Programs without inventing their relationships", () => {
    const x = input();
    x.programs.programs[1].rootJobId = null;
    x.programs.programs[1].rootState = "UNKNOWN";
    x.programs.programs[1].rootCandidates = [];
    expect(resolveWorkMissionLink(x).state).toBe("RESOLVED");
  });
});
