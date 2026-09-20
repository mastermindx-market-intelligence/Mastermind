import { describe, expect, it } from "vitest";
import {
  allEvidence,
  decodeMission,
  programsFromControlRoom,
  relationshipsForMission,
  selectionFromLocation,
  unavailableMission,
  validateMission,
} from "./mission";
import {
  controlRoomFixture,
  fabricUnavailableMissionFixture,
  missionFixture,
  nullRoleMissionFixture,
  realControlRoomFixture,
  realMissionFixture,
  retainedPartialMissionFixture,
} from "./test-fixtures";

const clone = <T>(value: T): T => structuredClone(value);
const selection = { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" };

describe("closed mission selection", () => {
  it("requires exactly one occurrence of both keys", () =>
    expect(
      selectionFromLocation("?work_ref=WS%3AALPHA&root_job_id=JOB-ROOT"),
    ).toEqual(selection));
  it.each([
    "",
    "?work_ref=WS:ALPHA",
    "?root_job_id=JOB-ROOT",
    "?work_ref=WS:ALPHA&root_job_id=",
    "?work_ref=WS:ALPHA&root_job_id=JOB-ROOT&x=1",
    "?work_ref=WS:ALPHA&work_ref=WS:BETA&root_job_id=JOB-ROOT",
    "?work_ref=WS%ZZALPHA&root_job_id=JOB-ROOT",
    "?work_ref=https%3A%2F%2Felsewhere&root_job_id=JOB-ROOT",
    `?work_ref=WS:ALPHA&root_job_id=JOB-${"x".repeat(300)}`,
  ])("rejects %s", (query) => expect(selectionFromLocation(query)).toBeNull());
});

describe("closed mission decoder", () => {
  it("accepts the full exact document and keeps producer clocks stable", () => {
    const raw = missionFixture();
    const decoded = decodeMission(raw, selection);
    expect(decoded?.source.control_room_generated_at).toBe(
      "2026-09-05T00:00:00Z",
    );
    expect(decoded?.source.fabric_view_generated_at).toBe(
      "2026-09-20T00:00:00Z",
    );
    expect(decoded?.generated_at).toBe("2026-09-05T00:00:00Z");
    expect(decoded?.mission.evidence[0]).toMatchObject({
      source_time: "2026-09-20T10:00:00Z",
      observed_at: "2026-09-20T10:01:00Z",
    });
    expect(validateMission(raw, "WS:ALPHA", "JOB-ROOT")).toBe(true);
  });
  it.each([
    [
      "top extra",
      (d: any) => {
        d.extra = true;
      },
    ],
    [
      "nested extra",
      (d: any) => {
        d.transport.raw_error = "secret";
      },
    ],
    [
      "program nested extra",
      (d: any) => {
        d.program.github_prs.push({
          repo: null,
          number: null,
          url: null,
          title: null,
          branch: null,
          draft: null,
          merge_state: null,
          private_host: "hidden",
        });
      },
    ],
    [
      "child nested extra",
      (d: any) => {
        d.children.items[0].latest_attempt.raw_error = "withheld by contract";
      },
    ],
    [
      "bad enum",
      (d: any) => {
        d.read_state.state = "BANANA";
      },
    ],
    [
      "string reasons",
      (d: any) => {
        d.read_state.reason_codes = "bad";
      },
    ],
    [
      "null child",
      (d: any) => {
        d.children.items = [null];
      },
    ],
    [
      "bad complete cardinality",
      (d: any) => {
        d.children.total_count = 0;
      },
    ],
    [
      "incomplete with count",
      (d: any) => {
        d.children.coverage = "INCOMPLETE";
        d.children.total_count = 1;
      },
    ],
    [
      "foreign pair",
      (d: any) => {
        d.program.work_ref = "WS:BETA";
      },
    ],
    [
      "foreign root",
      (d: any) => {
        d.mission.root_job_id = "JOB-OTHER";
      },
    ],
    [
      "missing generated_at",
      (d: any) => {
        delete d.generated_at;
      },
    ],
    [
      "missing budget",
      (d: any) => {
        delete d.budget;
      },
    ],
    [
      "missing source generation",
      (d: any) => {
        delete d.source.source_generation;
      },
    ],
    [
      "extra source generation key",
      (d: any) => {
        d.source.source_generation.qualification_generation = 3;
      },
    ],
  ])("rejects %s", (_name, mutate) => {
    const raw: any = clone(missionFixture());
    mutate(raw);
    expect(decodeMission(raw, selection)).toBeNull();
  });
  it("preserves a qualified conflict without treating it as a selected root", () => {
    const raw: any = clone(missionFixture());
    raw.mission.root_job_id = null;
    raw.mission.root_job_candidates = ["JOB-A", "JOB-B"];
    raw.mission.root_job_ambiguous = true;
    raw.mission.runtime_root_state = "CONFLICT";
    raw.children = {
      state: "UNAVAILABLE",
      coverage: "INCOMPLETE",
      reason_codes: ["ROOT_CONFLICT"],
      total_count: null,
      items: [],
      overflow_count: null,
      unjoined_job_count: 0,
      unjoined_job_ids: [],
    };
    expect(decodeMission(raw, selection)?.mission.runtime_root_state).toBe(
      "CONFLICT",
    );
  });
  it("preserves a qualified unknown when the former exact join disappeared", () => {
    const raw: any = clone(missionFixture());
    raw.mission.root_job_id = null;
    raw.mission.root_job_candidates = ["JOB-OTHER"];
    raw.mission.root_job_ambiguous = false;
    raw.mission.runtime_root_state = "UNKNOWN";
    raw.children.items = [];
    raw.children.state = "UNAVAILABLE";
    raw.children.coverage = "INCOMPLETE";
    raw.children.reason_codes = ["ROOT_NOT_JOINED"];
    raw.children.total_count = null;
    raw.children.overflow_count = null;
    expect(decodeMission(raw, selection)?.mission.runtime_root_state).toBe(
      "UNKNOWN",
    );
  });
  it("accepts the actual reducer output when the Fabric owner is unavailable", () => {
    const decoded = decodeMission(fabricUnavailableMissionFixture(), {
      workRef: "WS:B5",
      rootJobId: "JOB-B5",
    });
    expect(decoded).not.toBeNull();
    expect(decoded?.mission).toMatchObject({
      root_job_id: null,
      root_job_candidates: ["JOB-B5"],
      root_job_ambiguous: false,
      runtime_root_state: "UNKNOWN",
      capability: {
        state: null,
        installed: null,
        version: null,
        detail: null,
      },
    });
    expect(decoded?.execution.state).toBeNull();
    expect(decoded?.children).toMatchObject({
      state: "UNAVAILABLE",
      coverage: "INCOMPLETE",
      items: [],
    });
  });
  it("accepts actual owner-nullable and guarded known-subset child projections", () => {
    const nullRole = decodeMission(nullRoleMissionFixture(), {
      workRef: "WS:B5",
      rootJobId: "JOB-001",
    });
    expect(nullRole?.children).toMatchObject({
      state: "AVAILABLE",
      coverage: "COMPLETE",
    });
    expect(nullRole?.children.items[0].orchestration_role).toBeNull();

    const retained = decodeMission(retainedPartialMissionFixture(), {
      workRef: "WS:B5",
      rootJobId: "JOB-B5",
    });
    expect(retained?.children).toMatchObject({
      state: "PARTIAL",
      coverage: "INCOMPLETE",
      reason_codes: ["CHILD_ROWS_INVALID"],
    });
    expect(retained?.children.items[0]).toMatchObject({
      job_id: "JOB-CHILD",
      status: null,
      latest_attempt: { has_result: null },
    });
    expect(relationshipsForMission(retained!)).toEqual([
      {
        id: "JOB-B5->JOB-CHILD",
        from: "JOB-B5",
        to: "JOB-CHILD",
        kind: "Execution containment",
      },
    ]);

    const unguarded: any = retainedPartialMissionFixture();
    unguarded.missingness = unguarded.missingness.filter(
      (row: any) => row.target_field !== "children",
    );
    expect(
      decodeMission(unguarded, { workRef: "WS:B5", rootJobId: "JOB-B5" }),
    ).toBeNull();
  });
  it("keeps local unavailable state outside the producer contract", () => {
    const local = unavailableMission(selection, "SOURCE_UNAVAILABLE");
    expect(local.kind).toBe("LOCAL_UNAVAILABLE");
    expect(validateMission(local, "WS:ALPHA", "JOB-ROOT")).toBe(false);
  });
  it("admits a withheld execution state only with matching degraded missingness", () => {
    const raw: any = clone(missionFixture());
    raw.execution.state = null;
    expect(decodeMission(raw, selection)).toBeNull();
    raw.missingness.push({
      missingness_class: "DEGRADED",
      target_field: "execution",
      producer_owner: "executive_os",
      reason: "source detail withheld",
    });
    expect(decodeMission(raw, selection)?.execution.state).toBeNull();
  });
  it("accepts the frozen real producer-to-reducer output without adaptation", () => {
    const decoded = decodeMission(realMissionFixture(), {
      workRef: "WS:B5",
      rootJobId: "JOB-B5",
    });
    expect(decoded).not.toBeNull();
    expect(decoded?.principal.owed_turn?.seat).toBe("ceo");
    expect(decoded?.children.items[0].latest_attempt?.error_class).toBe(
      "WITHHELD",
    );
    expect(decoded?.transport.carrier?.state).toBe("OWNER_HELD");
    expect(decoded?.transport.w3c?.source_receipt?.freshness).toBe(
      "SOURCE_EVIDENCE_TIME",
    );
    expect(decoded?.read_state.state).toBe("PARTIAL");
    expect(decoded?.source.source_generation).toEqual({
      state: "UNKNOWN",
      version: null,
      generation: null,
    });
    expect(decoded?.posture).toMatchObject({
      value: "CONSUMPTION_UNKNOWN",
      rule: "E3",
    });
  });
  it.each([
    ["unknown state", { state: "BANANA", version: null, generation: null }],
    ["boolean version", { state: "UNKNOWN", version: true, generation: null }],
    ["zero generation", { state: "STALE", version: 1, generation: 0 }],
    ["fractional version", { state: "CONFLICT", version: 1.5, generation: 2 }],
  ])("rejects an invalid source generation %s", (_name, sourceGeneration) => {
    const raw: any = clone(missionFixture());
    raw.source.source_generation = sourceGeneration;
    expect(decodeMission(raw, selection)).toBeNull();
  });
  it("treats CURRENT generation as diagnostic and refuses a CURRENT read claim", () => {
    const raw: any = clone(missionFixture());
    raw.source.source_generation = {
      state: "CURRENT",
      version: 1,
      generation: 2,
    };
    expect(decodeMission(raw, selection)?.read_state.state).toBe("PARTIAL");
    raw.read_state.state = "CURRENT";
    expect(decodeMission(raw, selection)).toBeNull();
  });
  it.each([
    "2026-13-01T00:00:00Z",
    "2026-02-30T00:00:00Z",
    "2026-01-01T24:00:00Z",
    "2026-01-01T00:60:00Z",
    "2026-01-01T00:00:60Z",
  ])("rejects impossible UTC timestamp %s", (timestamp) => {
    const raw: any = clone(missionFixture());
    raw.generated_at = timestamp;
    expect(decodeMission(raw, selection)).toBeNull();
  });
  it("accepts a descendant tree and preserves each producer parent edge", () => {
    const raw: any = clone(missionFixture());
    const grandchild = clone(raw.children.items[0]);
    grandchild.job_id = "JOB-GRANDCHILD";
    grandchild.parent_job_id = "JOB-ROOT-CHILD";
    grandchild.depth = 2;
    raw.children.items.push(grandchild);
    raw.children.total_count = 2;
    const decoded = decodeMission(raw, selection)!;
    expect(relationshipsForMission(decoded)).toEqual([
      {
        id: "JOB-ROOT->JOB-ROOT-CHILD",
        from: "JOB-ROOT",
        to: "JOB-ROOT-CHILD",
        kind: "Execution containment",
      },
      {
        id: "JOB-ROOT-CHILD->JOB-GRANDCHILD",
        from: "JOB-ROOT-CHILD",
        to: "JOB-GRANDCHILD",
        kind: "Execution containment",
      },
    ]);
  });
  it.each([
    [
      "null child identity",
      (d: any) => {
        d.children.items[0].job_id = null;
      },
    ],
    [
      "duplicate child identity",
      (d: any) => {
        d.children.items.push(clone(d.children.items[0]));
        d.children.total_count = 2;
      },
    ],
    [
      "missing parent",
      (d: any) => {
        d.children.items[0].parent_job_id = "JOB-MISSING";
      },
    ],
    [
      "self parent",
      (d: any) => {
        d.children.items[0].parent_job_id = d.children.items[0].job_id;
      },
    ],
    [
      "cycle",
      (d: any) => {
        const second = clone(d.children.items[0]);
        second.job_id = "JOB-SECOND";
        second.parent_job_id = d.children.items[0].job_id;
        second.depth = 2;
        d.children.items[0].parent_job_id = "JOB-SECOND";
        d.children.items.push(second);
        d.children.total_count = 2;
      },
    ],
  ])("rejects %s topology", (_name, mutate) => {
    const raw: any = clone(missionFixture());
    mutate(raw);
    expect(decodeMission(raw, selection)).toBeNull();
  });
  it.each([
    "/Users/person/private.json",
    "/tmp/private.json",
    "C:\\Users\\person\\private.json",
    "http://127.0.0.1:8123/admin",
    "https://unapproved.example/report",
    "service.internal.local",
    "service.internal",
    "operator@example.com",
    "X-CCR-Token: abc",
    "authorization: bearer abc",
    "ghp_privatecredential",
    "session_id=abc123",
    "Traceback: raw model failure",
    "unsafe\u0000control",
  ])("rejects private or raw material %s", (value) => {
    const raw: any = clone(missionFixture());
    raw.execution.artifacts = [value];
    expect(decodeMission(raw, selection)).toBeNull();
  });
  it("accepts hostile markup only as inert bounded text", () => {
    const raw: any = clone(missionFixture());
    raw.execution.artifacts = ["<img src=x onerror=alert(1)>\u2028@channel"];
    expect(decodeMission(raw, selection)?.execution.artifacts[0]).toContain(
      "<img",
    );
  });
  it("rejects oversized fields", () => {
    const raw: any = clone(missionFixture());
    raw.execution.artifacts = ["x".repeat(1025)];
    expect(decodeMission(raw, selection)).toBeNull();
  });
});

describe("actual Control Room shape", () => {
  it("decodes the frozen real compose_control_room fixture", () => {
    const result = programsFromControlRoom(realControlRoomFixture());
    expect(result).toMatchObject({
      state: "AVAILABLE",
      programs: [
        {
          workRef: "WS:B5",
          title: "Bounded fixture",
          rootJobId: "JOB-B5",
          rootState: "RESOLVED",
        },
      ],
    });
  });
  it("distinguishes absent and malformed Control Room inputs", () => {
    expect(programsFromControlRoom(undefined).reason).toBe(
      "SOURCE_UNAVAILABLE",
    );
    expect(programsFromControlRoom({ invalid: true }).reason).toBe(
      "SCHEMA_INVALID",
    );
  });
  it("orients from work.agent_os and joins exactly one responsibility", () => {
    const result = programsFromControlRoom(controlRoomFixture());
    expect(result.programs[0]).toMatchObject({
      workRef: "WS:ALPHA",
      title: "Alpha program",
      rootJobId: "JOB-A",
      rootState: "RESOLVED",
    });
  });
  it("does not guess a root for zero or multiple responsibility joins", () => {
    const raw: any = controlRoomFixture();
    raw.autonomy.responsibilities.push({ ...raw.autonomy.responsibilities[0] });
    raw.autonomy.responsibilities = raw.autonomy.responsibilities.filter(
      (x: any) => x.responsibility_ref !== "WS:BETA",
    );
    const result = programsFromControlRoom(raw);
    expect(
      result.programs.find((p) => p.workRef === "WS:ALPHA")?.rootState,
    ).toBe("CONFLICT");
    expect(
      result.programs.find((p) => p.workRef === "WS:BETA")?.rootState,
    ).toBe("UNKNOWN");
  });
  it("rejects extra nested keys in the consumed Control Room shape", () => {
    const raw: any = realControlRoomFixture();
    raw.autonomy.responsibilities[0].qualification_generation = 3;
    expect(programsFromControlRoom(raw)).toMatchObject({
      state: "UNAVAILABLE",
      reason: "SCHEMA_INVALID",
    });
  });
  it("does not call mismatched producer clocks current or available", () => {
    const raw: any = realControlRoomFixture();
    raw.autonomy.generated_at = "2026-09-05T00:00:01Z";
    expect(programsFromControlRoom(raw)).toMatchObject({
      state: "UNAVAILABLE",
      reason: "GENERATION_MISMATCH",
    });
  });
  it("never selects an ambiguous RESOLVED root", () => {
    const raw: any = realControlRoomFixture();
    raw.autonomy.responsibilities[0].root_job_ambiguous = true;
    expect(programsFromControlRoom(raw).programs[0]).toMatchObject({
      rootJobId: null,
      rootState: "CONFLICT",
    });
  });
  it("classifies two distinct candidates as a conflict even if the row says RESOLVED", () => {
    const raw: any = realControlRoomFixture();
    raw.autonomy.responsibilities[0].root_job_candidates.push("JOB-OTHER");
    raw.autonomy.responsibilities[0].root_job_ambiguous = false;
    raw.autonomy.responsibilities[0].runtime_root_state = "RESOLVED";
    expect(programsFromControlRoom(raw).programs[0]).toMatchObject({
      rootJobId: null,
      rootState: "CONFLICT",
      rootCandidates: ["JOB-B5", "JOB-OTHER"],
    });
  });
  it("rejects duplicate work references", () => {
    const raw: any = realControlRoomFixture();
    raw.work.push(clone(raw.work[0]));
    expect(programsFromControlRoom(raw)).toMatchObject({
      state: "UNAVAILABLE",
      reason: "DUPLICATE_WORK_REF",
    });
  });
  it("rejects the invented legacy card shape", () =>
    expect(
      programsFromControlRoom({
        schema: "mastermind.chairman_control_room.v1",
        generated_at: "2026-09-20T10:00:00Z",
        work: [{ work_ref: "WS:X", title: "invented" }],
      }).state,
    ).toBe("UNAVAILABLE"));
});

describe("relationships and evidence", () => {
  it("uses one identity model for graph and list consumers", () => {
    const decoded = decodeMission(missionFixture(), selection)!;
    const rel = relationshipsForMission(decoded);
    expect(rel).toEqual([
      {
        id: "JOB-ROOT->JOB-ROOT-CHILD",
        from: "JOB-ROOT",
        to: "JOB-ROOT-CHILD",
        kind: "Execution containment",
      },
    ]);
    expect(new Set(rel.map((x) => x.id)).size).toBe(rel.length);
  });
  it("returns actual facet-qualified evidence and artifacts remain typed strings", () => {
    const decoded = decodeMission(missionFixture(), selection)!;
    expect(allEvidence(decoded).map((x) => x.facet)).toEqual(
      expect.arrayContaining([
        "Program",
        "Mission",
        "Principal",
        "Execution",
        "Review",
        "Transport",
        "Posture",
      ]),
    );
    expect(decoded.execution.artifacts).toEqual([
      "artifact:result/report.json",
    ]);
  });
});
