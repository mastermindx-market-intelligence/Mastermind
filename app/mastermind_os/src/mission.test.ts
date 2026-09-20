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
  missionFixture,
  realControlRoomFixture,
  realMissionFixture,
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
  it("keeps local unavailable state outside the producer contract", () => {
    const local = unavailableMission(selection, "SOURCE_UNAVAILABLE");
    expect(local.kind).toBe("LOCAL_UNAVAILABLE");
    expect(validateMission(local, "WS:ALPHA", "JOB-ROOT")).toBe(false);
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
  });
  it.each([
    "/Users/person/private.json",
    "http://127.0.0.1:8123/admin",
    "service.internal.local",
    "operator@example.com",
    "X-CCR-Token: abc",
    "session_id=abc123",
    "Traceback: raw model failure",
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
      reason: "AUTONOMY_PROJECTION_UNAVAILABLE",
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
