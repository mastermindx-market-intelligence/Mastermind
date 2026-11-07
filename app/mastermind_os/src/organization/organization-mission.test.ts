/**
 * Organization consumer over the incumbent Mission read.
 *
 * Evidence base: exactly one owner-produced committed regression fixture,
 * ../fixtures/mission-v2-current-128c46f6.json (schema v2, selection WS:ONE /
 * JOB-1, CURRENT read, owner observation SAME, empty complete children). It is
 * a real owner receipt, not production acceptance.
 *
 * Every case that adds children, breaks the tree or withholds a count is a
 * controlled mutation of a decoded copy of that fixture. Those are test inputs
 * for the presentation rules, never new owner evidence.
 */
import { describe, expect, it } from "vitest";
import { decodeMission, type ChildCard, type MissionDocument } from "../mission";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";
import { captureMissionOfficeRead, completeMissionOfficeRead } from "../meta-ceo/mission-adapter";
import {
  projectOffice,
  type ProjectionContext,
  type SourceClaim,
} from "../meta-ceo/projection";
import { organizationWork, qualifyOrganizationMission } from "./organization-mission";

const context: ProjectionContext = {
  authGeneration: 3,
  selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: null,
  bindingGeneration: null,
  revisions: { mission: null, programs: null, result: null, conversation: null },
};
/** Local acquisition label for the read, not an owner observation time. */
const acquiredAt = "2026-11-07T05:00:00Z";

/** The owner fixture exactly as the canonical owner decoder admits it. */
function ownerDocument(): MissionDocument {
  const decoded = decodeMission(structuredClone(fixture), context.selection!);
  expect(decoded, "the owner fixture must decode").not.toBeNull();
  return decoded!;
}

/** One owner read, committed exactly as the Mission adapter commits it. */
function ownerRead(document: MissionDocument = ownerDocument()) {
  const pending = captureMissionOfficeRead(context);
  const result = completeMissionOfficeRead(pending, context, document, acquiredAt);
  expect(result.kind, "the owner read must be observed").toBe("observed");
  if (result.kind !== "observed") throw new Error("expected an observed mission read");
  return result;
}

/** The presentation the office renders for that read. */
function officeProjection(document: MissionDocument = ownerDocument()) {
  const read = ownerRead(document);
  const projection = projectOffice(
    { mission: read.snapshot, programs: null, result: null, conversation: null },
    read.context,
  );
  return { read, projection };
}

describe("Organization mission qualification", () => {
  it("qualifies the owner fixture and hands back detached owner bytes", () => {
    const document = ownerDocument();
    const { read, projection } = officeProjection(document);
    expect(projection.mission.source.state).toBe("CURRENT");
    expect(projection.mission.source.owner).toBe("EXECUTIVE_OS");
    expect(projection.mission.source.coverage).toBe("COMPLETE");

    const qualified = qualifyOrganizationMission(read.context, "CURRENT", projection);
    expect(qualified).toEqual(document);
    expect(qualified).not.toBe(document);
    if (!qualified) throw new Error("expected a qualified organization mission");
    (qualified as MissionDocument).mission.status = "CANCELLED";
    expect(document.mission.status).toBe("COMPLETED");
    expect(projection.mission.value!.mission.status).toBe("COMPLETED");
  });

  it("presents nothing without a current mission read", () => {
    const { read, projection } = officeProjection();
    expect(qualifyOrganizationMission(read.context, "STALE", projection)).toBeNull();
    expect(qualifyOrganizationMission(read.context, "CURRENT", undefined)).toBeNull();
  });

  it("refuses a CURRENT label that carries no owner provenance", () => {
    const { read, projection } = officeProjection();
    const withoutRef = structuredClone(projection);
    withoutRef.mission.source.ref = null;
    expect(qualifyOrganizationMission(read.context, "CURRENT", withoutRef)).toBeNull();

    const withoutObservation = structuredClone(projection);
    withoutObservation.mission.source.observed_at = null;
    expect(qualifyOrganizationMission(read.context, "CURRENT", withoutObservation)).toBeNull();

    const withoutRevision = structuredClone(projection);
    withoutRevision.mission.source.revision = null;
    expect(qualifyOrganizationMission(read.context, "CURRENT", withoutRevision)).toBeNull();
  });

  it.each<[string, Partial<ProjectionContext>]>([
    ["auth epoch", { authGeneration: 4 }],
    ["session", { sessionRef: "session:other" }],
    ["binding generation", { bindingGeneration: 2 }],
    ["work", { selection: { workRef: "WS:OTHER", rootJobId: "JOB-1" } }],
    ["root job", { selection: { workRef: "WS:ONE", rootJobId: "JOB-2" } }],
    [
      "mission revision",
      {
        revisions: {
          mission: "mission-owner-observation:v1:other",
          programs: null,
          result: null,
          conversation: null,
        },
      },
    ],
  ])("invalidates a render bound to another %s", (_label, change) => {
    const { read, projection } = officeProjection();
    const binding: ProjectionContext = { ...read.context, ...change };
    expect(qualifyOrganizationMission(binding, "CURRENT", projection)).toBeNull();
  });

  it.each<[string, Partial<SourceClaim>]>([
    ["stale", { state: "STALE" }],
    ["withheld", { state: "WITHHELD" }],
    ["unknown", { state: "UNKNOWN" }],
    ["incomplete", { coverage: "INCOMPLETE" }],
    ["unattributed", { owner: "UNKNOWN" }],
    ["claimed by another owner", { owner: "AGENT_OS" }],
  ])("refuses a mission read the office reports as %s", (_label, change) => {
    const { read, projection } = officeProjection();
    const altered = structuredClone(projection);
    Object.assign(altered.mission.source, change);
    expect(qualifyOrganizationMission(read.context, "CURRENT", altered)).toBeNull();
  });

  it.each<[string, Partial<SourceClaim>]>([
    ["ref", { ref: "0".repeat(64) }],
    ["revision", { revision: "mission-owner-observation:v1:other" }],
    ["observed_at", { observed_at: "2026-11-07T05:00:00" }],
  ])("refuses a mission read whose %s was altered", (_label, change) => {
    const { read, projection } = officeProjection();
    const altered = structuredClone(projection);
    Object.assign(altered.mission.source, change);
    expect(qualifyOrganizationMission(read.context, "CURRENT", altered)).toBeNull();
  });

  it.each(["UNKNOWN", "CONFLICT"] as const)(
    "refuses a read whose own owner receipt reports %s",
    state => {
      const { read, projection } = officeProjection();
      const altered = structuredClone(projection);
      altered.mission.value!.source.owner_observation!.state = state;
      expect(qualifyOrganizationMission(read.context, "CURRENT", altered)).toBeNull();
    },
  );
});

/** A child row in the wire shape the owner decoder accepts. */
function child(overrides: Partial<ChildCard> = {}): ChildCard {
  return {
    job_id: "JOB-2",
    parent_job_id: "JOB-1",
    depth: 1,
    orchestration_role: "work",
    plan_step_id: null,
    status: "QUEUED",
    worker_id: null,
    attempt_count: 0,
    attempt_limit: 2,
    current_attempt_id: null,
    latest_attempt: null,
    ...overrides,
  };
}

function attempt(status: "RUNNING" | "COMPLETED" | "FAILED" = "RUNNING", attemptId = "ATT-1") {
  return {
    attempt_id: attemptId,
    attempt_number: 1,
    status,
    started_at: "2026-11-07T04:00:00Z",
    finished_at: status === "RUNNING" ? null : "2026-11-07T04:30:00Z",
    exit_code: null,
    has_result: false,
    error_present: false,
    error_class: null,
  };
}

function workingChild(overrides: Partial<ChildCard> = {}): ChildCard {
  return child({
    status: "RUNNING",
    worker_id: "worker-a",
    attempt_count: 1,
    attempt_limit: 2,
    current_attempt_id: "ATT-1",
    latest_attempt: attempt("RUNNING", "ATT-1"),
    ...overrides,
  });
}

/**
 * Controlled mutation of the owner fixture: the children section is replaced
 * with the given rows, and the canonical decoder must still admit the source.
 */
function missionWith(children: ChildCard[], section: Record<string, unknown> = {}) {
  const raw = structuredClone(fixture) as unknown as Record<string, unknown>;
  const existing = raw.children as Record<string, unknown>;
  raw.children = {
    ...existing,
    state: children.length ? "AVAILABLE" : "EMPTY",
    coverage: "COMPLETE",
    reason_codes: [],
    items: children,
    total_count: children.length,
    overflow_count: 0,
    unjoined_job_count: 0,
    unjoined_job_ids: [],
    ...section,
  };
  const decoded = decodeMission(raw, context.selection!);
  expect(decoded, "the canonical decoder must admit this source").not.toBeNull();
  return decoded!;
}

describe("Organization work view", () => {
  it("counts only the jobs this selection observed", () => {
    const mission = missionWith([
      workingChild(),
      child({
        job_id: "JOB-3",
        status: "COMPLETED",
        attempt_count: 1,
        current_attempt_id: "ATT-2",
        latest_attempt: attempt("COMPLETED", "ATT-2"),
      }),
    ]);
    const view = organizationWork(mission);
    expect(view.coverageComplete).toBe(true);
    expect(view.observedJobs).toBe(view.rows.length);
    expect(view.observedJobs).toBe(2);
    expect(view.working).toBe(1);
    expect(view.finished).toBe(1);
    expect(view.rows.map(row => row.activity)).toEqual(["WORKING", "FINISHED"]);
  });

  it.each<[ChildCard["status"], string]>([
    ["QUEUED", "QUEUED"],
    ["FAILED", "NEEDS_ATTENTION"],
    ["LOST", "NEEDS_ATTENTION"],
  ])("reports a %s child as %s without counting it as work", (status, activity) => {
    const mission = missionWith([child({ job_id: "JOB-2", status })]);
    const view = organizationWork(mission);
    expect(view.rows[0].activity).toBe(activity);
    expect(view.working).toBe(0);
    expect(view.finished).toBe(0);
  });

  it.each<[string, Partial<ChildCard>]>([
    ["no assigned worker", { worker_id: null }],
    ["no current attempt", { current_attempt_id: null }],
    ["a different observed attempt", { current_attempt_id: "ATT-OTHER" }],
    ["an attempt that is not running", { latest_attempt: attempt("FAILED", "ATT-1") }],
  ])("does not count a running child with %s as working", (_label, override) => {
    const mission = missionWith([workingChild({ ...override })]);
    const view = organizationWork(mission);
    expect(view.rows[0].activity).not.toBe("WORKING");
    expect(view.working).toBeNull();
    expect(view.finished).toBeNull();
    expect(view.activityComplete).toBe(false);
  });

  it("counts a completed child from its attempt, not from worker availability", () => {
    const mission = missionWith([
      child({
        job_id: "JOB-2",
        status: "COMPLETED",
        worker_id: null,
        orchestration_role: null,
        attempt_count: 1,
        attempt_limit: 2,
        current_attempt_id: "ATT-1",
        latest_attempt: attempt("COMPLETED", "ATT-1"),
      }),
    ]);
    const view = organizationWork(mission);
    expect(view.rows[0].activity).toBe("FINISHED");
    expect(view.finished).toBe(1);
    expect(view.working).toBe(0);
  });

  it.each<[string, (mission: MissionDocument) => void]>([
    [
      "parent that was never observed",
      mission => {
        mission.children.items[0].parent_job_id = "JOB-ABSENT";
      },
    ],
    [
      "sibling rows that form a cycle",
      mission => {
        mission.children.items[0].parent_job_id = "JOB-3";
        mission.children.items[1].parent_job_id = "JOB-2";
      },
    ],
  ])("keeps a child whose %s stays unknown and withholds the totals", (_label, mutate) => {
    const mission = missionWith([
      workingChild(),
      child({
        job_id: "JOB-3",
        status: "RUNNING",
        worker_id: "worker-b",
        attempt_count: 1,
        attempt_limit: 2,
        current_attempt_id: "ATT-3",
        latest_attempt: attempt("RUNNING", "ATT-3"),
      }),
    ]);
    mutate(mission);
    const view = organizationWork(mission);
    expect(view.rows[0].association).toBe("UNASSOCIATED");
    expect(view.rows[0].activity).toBe("UNKNOWN");
    expect(
      view.rows.filter(row => row.association === "UNASSOCIATED").every(row => row.activity === "UNKNOWN"),
    ).toBe(true);
    expect(view.coverageComplete).toBe(false);
    expect(view.working).toBeNull();
    expect(view.finished).toBeNull();
  });

  it.each<[string, Record<string, unknown>, (mission: MissionDocument) => void]>([
    [
      "incomplete coverage",
      {
        coverage: "INCOMPLETE",
        total_count: null,
        overflow_count: null,
        state: "PARTIAL",
        reason_codes: ["CHILDREN_PARTIAL"],
      },
      () => {},
    ],
    ["an overflowed job", { total_count: 2, overflow_count: 1 }, () => {}],
    [
      "an unjoined job",
      {},
      mission => {
        mission.children.unjoined_job_count = 2;
        mission.children.unjoined_job_ids = ["JOB-9"];
      },
    ],
  ])(
    "withholds the totals when the children section reports %s",
    (_label, section, mutate) => {
      const mission = missionWith([workingChild()], section);
      mutate(mission);
      const view = organizationWork(mission);
      expect(view.coverageComplete).toBe(false);
      expect(view.working).toBeNull();
      expect(view.finished).toBeNull();
      expect(view.rows).toHaveLength(1);
    },
  );

  it("offers no worker result for a v2 mission", () => {
    const mission = missionWith([
      child({
        job_id: "JOB-2",
        status: "COMPLETED",
        worker_id: "worker-a",
        attempt_count: 1,
        attempt_limit: 2,
        current_attempt_id: "ATT-1",
        latest_attempt: { ...attempt("COMPLETED", "ATT-1"), has_result: true },
      }),
    ]);
    const view = organizationWork(mission);
    expect(view.rows[0].activity).toBe("FINISHED");
    expect(view.rows[0].result).toBeNull();
  });
});
// Parent-added regression for the worker's valid exported-helper finding.
describe("historical activity is never current work", () => {
  it.each(["HISTORICAL", "PARTIAL", "UNAVAILABLE"] as const)("withholds current activity for %s", state => {
    const mission = missionWith([workingChild()]);
    mission.read_state.state = state;
    const view = organizationWork(mission);
    expect(view.rows.every(row => row.activity === "UNKNOWN")).toBe(true);
    expect(view.working).toBeNull();
    expect(view.finished).toBeNull();
    expect(view.coverageComplete).toBe(false);
  });
});
