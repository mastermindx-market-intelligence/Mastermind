import { describe, expect, it } from "vitest";
import producer from "../fixtures/window-mission-association-producer.json";
import { projectDiscovery } from "./projection";
import type { DiscoveryInputs } from "./contract";
import type {
  OfficeProjection,
  ProjectedRead,
  ProjectionContext,
  SourceClaim,
  SourceState,
} from "../meta-ceo/projection";
import type { ControlRoomState } from "../control-room";
import type { Missionv3Document } from "../mission";
import type { WindowDocumentV2, WindowItem } from "../workspace-contract";

const WORK_REF = "WS:PROPHET";
const ROOT_JOB = "JOB-1";
const CHILD_JOB = "JOB-2";
const ATTEMPT_ID = "ATT-" + "a".repeat(32);
const DIGEST = "c".repeat(64);

function claim(state: SourceState, over: Partial<SourceClaim> = {}): SourceClaim {
  return {
    owner: "CONTROL_ROOM_CACHE",
    ref: "cr-doc-digest-1",
    ref_kind: "CONTROL_ROOM_DOCUMENT_DIGEST",
    revision: "rev-1",
    observed_at: "2026-11-03T08:00:00Z",
    observed_at_kind: "LOCAL_ACQUISITION",
    state,
    coverage: "COMPLETE",
    ...over,
  };
}

function read<T>(
  value: T,
  state: SourceState = "CURRENT",
  over: Partial<SourceClaim> = {},
  reason: string | null = null,
): ProjectedRead<T> {
  return { source: claim(state, over), value, reason };
}

function unqualifiedRead(state: SourceState): ProjectedRead<null> {
  return read(null, state, { ref: null, revision: null, observed_at: null }, "NOT_SUPPLIED");
}

function context(over: Partial<ProjectionContext> = {}): ProjectionContext {
  return {
    authGeneration: 7,
    selection: { workRef: WORK_REF, rootJobId: ROOT_JOB },
    sessionRef: "session-1",
    bindingGeneration: "binding-1",
    revisions: { mission: "rev-1", programs: "rev-1", result: null, conversation: null },
    ...over,
  };
}

function card(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    workRef: WORK_REF,
    title: "Prophet nav repair",
    state: "RUNNING",
    nextAction: "Ship the nav footprint fix",
    nextActionWithheld: false,
    rootJobId: ROOT_JOB,
    rootState: "RESOLVED",
    rootCandidates: [ROOT_JOB],
    ...over,
  };
}

function attemptRow(attemptId: string, status: "RUNNING" | "CHECKPOINTED") {
  return { attempt_id: attemptId, status };
}

function childRow() {
  return {
    job_id: CHILD_JOB,
    orchestration_role: "plan",
    parent_job_id: ROOT_JOB,
    depth: 1,
    status: "RUNNING",
    current_attempt_id: ATTEMPT_ID,
    latest_attempt: attemptRow(ATTEMPT_ID, "RUNNING"),
  };
}

function resultRef(role: "work" | "review", jobId: string) {
  return {
    root_job_id: ROOT_JOB,
    job_id: jobId,
    attempt_id: ATTEMPT_ID,
    result_envelope_digest: DIGEST,
    orchestration_role: role,
    validation: "UNVALIDATED" as const,
  };
}

function refsIndex(over: Record<string, unknown> = {}) {
  return {
    schema: "mastermind.fabric_result_reference_index.v1",
    root_job_id: ROOT_JOB,
    snapshot_digest: null,
    generation: {
      schema: "mastermind.runtime_read_observation.v1",
      state: "SAME",
      source_identity: "runtime-1",
      before: 7,
      after: 7,
    },
    availability: "AVAILABLE",
    refs: [resultRef("work", CHILD_JOB), resultRef("review", "JOB-3")],
    absent_job_ids: [],
    omitted_job_ids: [],
    truncated: false,
    ...over,
  };
}

/** v3 mission fixture satisfying the real observedMissionAssociation contract. */
function missionV3(over: Record<string, unknown> = {}): Missionv3Document {
  const base = structuredClone(producer.mission);
  return {
    ...base,
    schema: "mastermind.mission_workspace.v3",
    program: { ...base.program, work_ref: WORK_REF },
    mission: { ...base.mission, root_job_id: ROOT_JOB, runtime_root_state: "RESOLVED", root_job_ambiguous: false },
    read_state: { state: "CURRENT" },
    generated_at: "2026-11-03T10:00:00Z",
    source: { owner_observation: { state: "SAME", runtime: { state: "SAME" } } },
    children: { state: "AVAILABLE", coverage: "COMPLETE", items: [childRow()] },
    result_refs: refsIndex(),
    ...over,
  } as unknown as Missionv3Document;
}

function windowItem(over: Partial<WindowItem> & { id: string; text: string | null }): WindowItem {
  return {
    source_sequence: 1,
    publication_sequence: 1,
    state: "completed",
    kind: "visible-response",
    representation: "VISIBLE_TEXT",
    display_sha256: null,
    ...over,
  };
}

function windowDoc(items: WindowItem[], over: Record<string, unknown> = {}): WindowDocumentV2 {
  return {
    schema: "mastermind.workspace.window_read_candidate.v2",
    selection_ref: WORK_REF,
    mode: "observed-turn-window",
    observation_binding: { job_id: CHILD_JOB, attempt_id: ATTEMPT_ID },
    view: {
      schema: "mastermind.workspace.visible_window_candidate.v1",
      source_ref: "window-ref-1",
      scope: "one-managed-turn-window",
      observed_at: "2026-11-03T10:05:00Z",
      epoch: "epoch-1",
      terminal: false,
      coverage: "OBSERVED_WINDOW",
      history: "NOT_PROVEN",
      acceptance: "NOT_PROJECTED",
      capabilities: { send: false, provider_control: false, history: false },
      items,
      gaps: [],
      ...over,
    },
  };
}

function emptyRead(state: SourceState = "UNAVAILABLE"): ProjectedRead<null> {
  return unqualifiedRead(state);
}

function projectionFixture(over: Record<string, unknown> = {}): OfficeProjection {
  return {
    schema: "mastermind.product_projection.v1",
    context: context(),
    mission: read(missionV3()),
    programs: read({ state: "AVAILABLE", programs: [card()] }),
    result: emptyRead(),
    conversation: emptyRead(),
    companyTotal: null,
    receipts: {
      delivery: null, pickup: null, start: null,
      effect: null, return: null, review: null, acceptance: null,
    },
    work: { state: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" },
    direction: { state: "UNAVAILABLE", reason: "MISSING_PRODUCER" },
    ...over,
  } as unknown as OfficeProjection;
}

function conversationFixture(
  window: WindowDocumentV2,
  contextOver: Partial<ProjectionContext> = {},
): OfficeProjection {
  return {
    schema: "mastermind.product_projection.v1",
    context: context(contextOver),
    mission: emptyRead(),
    programs: emptyRead(),
    result: emptyRead(),
    conversation: read(window),
    companyTotal: null,
    receipts: {
      delivery: null, pickup: null, start: null,
      effect: null, return: null, review: null, acceptance: null,
    },
    work: { state: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" },
    direction: { state: "UNAVAILABLE", reason: "MISSING_PRODUCER" },
  } as unknown as OfficeProjection;
}

function controlRoomFixture(ownerRevision: number): ControlRoomState {
  return {
    state: "AVAILABLE",
    programs: [],
    navigation: {
      state: "AVAILABLE",
      bindings: [],
      unboundBindingIds: [],
      conflicts: [],
      capabilities: {
        chatgpt: { installed: true, version: "1.2.3", state: "PARTIAL", detail: "bounded" },
        aionui: { installed: false, version: null, state: "NOT_INSTALLED", detail: "absent" },
      },
      bindingsPathPresent: true,
    },
    observedAt: "2026-11-03T09:00:00Z",
    liveBuildsActive: false,
    refreshInFlight: false,
    freshness: "OWNER_QUALIFIED",
    publicationSeq: 4,
    crossPlane: {},
    ownerRevision,
  } as unknown as ControlRoomState;
}

function baseInputs(over: Record<string, unknown> = {}): DiscoveryInputs {
  return {
    projection: projectionFixture(over.projection as Record<string, unknown> | undefined),
    ...Object.fromEntries(Object.entries(over).filter(([key]) => key !== "projection")),
  } as DiscoveryInputs;
}

const GOOD_TEXT = "Visible assistant text about the prophet nav repair.";
const SECRET_TEXT = "withheld-secret-representation-text";

function conversationItems(inputs: DiscoveryInputs) {
  return projectDiscovery(inputs).items.filter((item) => item.kind === "conversation");
}

function capability(
  view: { readonly capabilities: readonly { id: string; state: string; target: string | null }[] },
  id: string,
) {
  const row = view.capabilities.find((entry) => entry.id === id);
  if (!row) throw new Error(`missing capability ${id}`);
  return row;
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
  }
  return value;
}

describe("projectDiscovery", () => {
  it("projects qualified program cards in supplied owner order with exact next actions", () => {
    const inputs = baseInputs({
      projection: {
        programs: read({ state: "AVAILABLE", programs: [card(), card({ title: null, nextAction: null })] }),
      },
    });
    const view = projectDiscovery(inputs);
    const projects = view.items.filter((item) => item.kind === "project");
    expect(projects.map((item) => item.title)).toEqual(["Prophet nav repair", "WS:PROPHET"]);
    expect(projects[0]!.summary).toBe("Ship the nav footprint fix");
    const target = projects[0]!.target;
    expect(target.kind === "project" && target.selection).toEqual({
      workRef: WORK_REF,
      rootJobId: ROOT_JOB,
    });
    expect(projects[1]!.summary).toBeNull();
    expect(projects[1]!.searchText).toBe("WS:PROPHET");
    expect(view.items[0]!.id).toBe(`discovery:project:${WORK_REF}:0`);
    expect(view.scope).toBe("SUPPLIED_WORKSPACE");
    expect(view.context).toEqual(inputs.projection.context);
    expect(view.context).not.toBe(inputs.projection.context);
  });

  it("never guesses a project root for unresolved or ambiguous cards", () => {
    const inputs = baseInputs({
      projection: {
        programs: read({
          state: "AVAILABLE",
          programs: [
            card({ rootState: "CONFLICT", rootCandidates: [ROOT_JOB, "JOB-9"] }),
            card({ rootState: "RESOLVED", rootCandidates: [ROOT_JOB, "JOB-9"] }),
            card({ rootState: "RESOLVED", rootCandidates: ["JOB-9"] }),
          ],
        }),
      },
    });
    const view = projectDiscovery(inputs);
    const projects = view.items.filter((item) => item.kind === "project");
    for (const item of projects) {
      const target = item.target;
      expect(target.kind === "project" && target.selection).toBeNull();
    }
    expect(projects).toHaveLength(3);
  });

  it("withholds rejected next-action text and keeps title-only search text", () => {
    const inputs = baseInputs({
      projection: {
        programs: read({
          state: "AVAILABLE",
          programs: [card({ nextActionWithheld: true, nextAction: "rejected source text" })],
        }),
      },
    });
    const view = projectDiscovery(inputs);
    expect(view.items[0]!.summary).toBeNull();
    expect(view.items[0]!.searchText).toBe("Prophet nav repair");
    expect(JSON.stringify(view)).not.toContain("rejected source text");
  });

  it("exposes missing provenance as source state with redacted refs, never records", () => {
    const inputs = baseInputs({
      projection: {
        programs: read(
          { state: "AVAILABLE", programs: [card()] },
          "CURRENT",
          { ref: null, revision: null, observed_at: null },
        ),
        mission: unqualifiedRead("WITHHELD"),
      },
    });
    const view = projectDiscovery(inputs);
    expect(view.items).toHaveLength(0);
    expect(view.capabilities.find((row) => row.id === "search")).toEqual({
      id: "search", state: "UNAVAILABLE", target: null,
    });
    const programsRow = view.sources.find((row) => row.id === "discovery-source:programs");
    expect(programsRow).toMatchObject({ state: "CURRENT", reference: null, revision: null, observedAt: null });
    const missionRow = view.sources.find((row) => row.id === "discovery-source:mission");
    expect(missionRow).toMatchObject({ state: "WITHHELD", reference: null, revision: null, observedAt: null });
    expect(missionRow!.owner).toBe("CONTROL_ROOM_CACHE");
    expect(JSON.stringify(view)).not.toContain("cr-doc-digest-1");
    expect(view.limitations).toContain("CONTROL_ROOM_NOT_SUPPLIED");
  });

  it("keeps exact provenance on qualified stale reads and preserves coverage", () => {
    const inputs = baseInputs({
      projection: {
        programs: read({ state: "AVAILABLE", programs: [card()] }, "STALE", { coverage: "HISTORICAL_ONLY" }),
      },
    });
    const view = projectDiscovery(inputs);
    expect(view.items.filter((item) => item.kind === "project")).toHaveLength(1);
    const row = view.sources.find((entry) => entry.id === "discovery-source:programs")!;
    expect(row.state).toBe("STALE");
    expect(row).toMatchObject({
      reference: "cr-doc-digest-1", revision: "rev-1",
      observedAt: "2026-11-03T08:00:00Z", observedKind: "LOCAL_ACQUISITION", coverage: "HISTORICAL_ONLY",
    });
    expect(row.sourceTime).toBeNull();
    expect(row.content).toBe("OBSERVED");
  });

  it("projects the paired observed window only when auth, target and association all match", () => {
    const window = windowDoc([windowItem({ id: "w1", text: GOOD_TEXT })]);
    const happyView = projectDiscovery(baseInputs({ conversation: conversationFixture(window) }));
    const items = happyView.items.filter((item) => item.kind === "conversation");
    expect(items).toHaveLength(1);
    expect(items[0]!.summary).toBe(GOOD_TEXT);
    expect(items[0]!.searchText).toBe(GOOD_TEXT);
    expect(items[0]!.title).toBe("Observed response");
    const target = items[0]!.target;
    expect(target.kind === "conversation" && target.reference).toBe("window-ref-1");
    expect(items[0]!.source).toMatchObject({
      state: "CURRENT", ref: "cr-doc-digest-1", revision: "rev-1",
    });

    const ambiguous = missionV3({
      mission: { ...missionV3().mission, root_job_id: ROOT_JOB, runtime_root_state: "RESOLVED", root_job_ambiguous: true },
    });
    const blocked: DiscoveryInputs[] = [
      baseInputs({ conversation: conversationFixture(window, { sessionRef: "session-other" }) }),
      baseInputs({ conversation: conversationFixture(window, { bindingGeneration: 99 }) }),
      baseInputs({ conversation: conversationFixture(window, { authGeneration: 8 }) }),
      baseInputs({
        conversation: conversationFixture(window),
        projection: projectionFixture({ mission: read(ambiguous) }),
      }),
    ];
    for (const inputs of blocked) {
      const view = projectDiscovery(inputs);
      expect(view.items.filter((item) => item.kind === "conversation")).toHaveLength(0);
      const source = view.sources.find((row) => row.id === "discovery-source:window");
      expect(source).not.toBeUndefined();
      if (inputs.conversation!.context.authGeneration !== inputs.projection.context.authGeneration ||
          inputs.conversation!.context.sessionRef !== inputs.projection.context.sessionRef ||
          inputs.conversation!.context.bindingGeneration !== inputs.projection.context.bindingGeneration) {
        expect(source).toMatchObject({ reference: null, revision: null, observedAt: null, content: "UNAVAILABLE" });
      }
    }
  });

  it("excludes withheld kind, withheld representation and null text from the window", () => {
    const window = windowDoc([
      windowItem({ id: "w1", text: GOOD_TEXT }),
      windowItem({ id: "w2", kind: "withheld", representation: "WITHHELD", text: SECRET_TEXT }),
      windowItem({ id: "w3", representation: "WITHHELD", text: SECRET_TEXT }),
      windowItem({ id: "w4", text: null }),
    ]);
    const view = projectDiscovery(baseInputs({ conversation: conversationFixture(window) }));
    const items = view.items.filter((item) => item.kind === "conversation");
    expect(items).toHaveLength(1);
    expect(JSON.stringify(view)).not.toContain(SECRET_TEXT);
  });

  it("bounds conversation summaries to the exact first 240 characters", () => {
    const long = "x".repeat(300);
    const window = windowDoc([windowItem({ id: "w1", text: long })]);
    const view = projectDiscovery(baseInputs({ conversation: conversationFixture(window) }));
    const items = view.items.filter((item) => item.kind === "conversation");
    expect(items).toHaveLength(1);
    expect(items[0]!.summary).toBe(long.slice(0, 240));
    expect(items[0]!.searchText).toBe(long);
    expect(items[0]!.searchText.length).toBe(300);
  });

  it("emits explicit result tuples only for SAME generation on the exact root", () => {
    const happy = projectDiscovery(baseInputs({}));
    const results = happy.items.filter((item) => item.kind === "result");
    expect(results.map((item) => item.title)).toEqual([
      `work result ${CHILD_JOB}`, "review result JOB-3",
    ]);
    for (const item of results) {
      expect(item.summary).toBeNull();
      expect(item.searchText).toContain(DIGEST);
      expect(item.target.kind === "result").toBe(true);
    }
    expect(capability(happy, "return_review")).toEqual({
      id: "return_review", state: "READ_ONLY", target: "knowledge",
    });

    const blocked = [
      refsIndex({ root_job_id: "JOB-9" }),
      refsIndex({ generation: { schema: "mastermind.runtime_read_observation.v1", state: "UNKNOWN", source_identity: null, before: null, after: null } }),
      refsIndex({ availability: "UNAVAILABLE", refs: [] }),
    ];
    for (const refs of blocked) {
      const view = projectDiscovery(baseInputs({ projection: projectionFixture({ mission: read(missionV3({ result_refs: refs })) }) }));
      expect(view.items.filter((item) => item.kind === "result")).toHaveLength(0);
      expect(capability(view, "return_review")).toEqual({
        id: "return_review", state: "UNAVAILABLE", target: null,
      });
    }
  });

  it("gates capabilities as local view hints and never grants placement or release", () => {
    const view = projectDiscovery(baseInputs({}));
    expect(capability(view, "direction_preview")).toEqual({
      id: "direction_preview", state: "PREVIEW_ONLY", target: "meta_ceo",
    });
    expect(capability(view, "search")).toEqual({ id: "search", state: "READ_ONLY", target: "search" });
    expect(capability(view, "source_context")).toEqual({
      id: "source_context", state: "READ_ONLY", target: "sources",
    });
    expect(capability(view, "placement")).toEqual({ id: "placement", state: "UNAVAILABLE", target: null });
    expect(capability(view, "release")).toEqual({ id: "release", state: "UNAVAILABLE", target: null });

    const staleMissionView = projectDiscovery(baseInputs({
      projection: projectionFixture({ mission: read(missionV3(), "STALE") }),
    }));
    expect(capability(staleMissionView, "direction_preview")).toEqual({
      id: "direction_preview", state: "UNAVAILABLE", target: null,
    });
    expect(staleMissionView.items.length).toBeGreaterThan(0);
  });

  it("maps qualified Control Room navigation verbatim and redacts stale owner revisions", () => {
    const qualified = projectDiscovery(baseInputs({ controlRoom: controlRoomFixture(7) }));
    expect(qualified.limitations).not.toContain("CONTROL_ROOM_NOT_SUPPLIED");
    expect(qualified.systems.map((row) => row.provider)).toEqual(["chatgpt", "aionui"]);
    expect(qualified.systems[0]).toEqual({
      provider: "chatgpt", installed: true, state: "PARTIAL",
      version: "1.2.3", detail: "bounded", observedAt: "2026-11-03T09:00:00Z",
    });
    for (const row of qualified.systems) {
      expect(Object.keys(row).sort()).toEqual([
        "detail", "installed", "observedAt", "provider", "state", "version",
      ]);
    }
    const cacheRow = qualified.sources.find((row) => row.id === "discovery-source:control-room");
    expect(cacheRow).toMatchObject({ owner: "CONTROL_ROOM_CACHE", state: "UNKNOWN", content: "OBSERVED" });

    const staleRevision = projectDiscovery(baseInputs({ controlRoom: controlRoomFixture(6) }));
    expect(staleRevision.systems).toEqual([]);
    expect(staleRevision.limitations).toContain("CONTROL_ROOM_NOT_SUPPLIED");
    expect(staleRevision.sources.find((row) => row.id === "discovery-source:control-room")).toBeUndefined();
  });

  it("keeps evidence citations reference-only with reduced per-ref freshness", () => {
    const mission = missionV3();
    mission.program.evidence = (["CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"] as const).map(freshness_state => ({
      owner: "GITHUB", ref: "source:bounded-citation", field: "body", source_revision: "supplied-revision",
      source_time: "2026-11-01T00:00:00Z", observed_at: "2026-11-03T00:00:00Z", freshness_state,
    }));
    const view = projectDiscovery(baseInputs({ projection: projectionFixture({ mission: read(mission) }) }));
    const evidenceItems = view.items.filter((item) => item.kind === "evidence");
    expect(evidenceItems).toHaveLength(4);
    expect(evidenceItems.map(item => item.source.state)).toEqual(["CURRENT", "UNKNOWN", "STALE", "UNAVAILABLE"]);
    expect(evidenceItems.every((item) => item.summary === null)).toBe(true);
    evidenceItems.forEach((item, index) => {
      if (item.target.kind !== "evidence") return;
      const evidence = item.target.evidence;
      expect(typeof item.target.facet).toBe("string");
      expect(item.searchText).toBe(`${evidence.owner} ${evidence.field}`);
      const row = view.sources.find((entry) => entry.id === `discovery-source:evidence:${index}`);
      expect(row).not.toBeUndefined();
      expect(row!.content).toBe("REFERENCE_ONLY");
      const expected = evidence.freshness_state === "UNAVAILABLE" ? "UNAVAILABLE"
        : evidence.freshness_state === "HISTORICAL" ? "STALE"
        : evidence.freshness_state === "PARTIAL" || !evidence.ref ||
          evidence.source_revision === null || evidence.observed_at === null
        ? "UNKNOWN" : "CURRENT";
      expect(row!.state).toBe(expected);
      if (expected === "UNAVAILABLE") {
        expect(row!.reference).toBeNull();
        expect(row!.sourceTime).toBeNull();
      }
    });
  });

  it("orders sources as programs, mission, window, result, evidence, control room", () => {
    const view = projectDiscovery(baseInputs({
      projection: projectionFixture({ result: read(null) }),
      conversation: conversationFixture(windowDoc([windowItem({ id: "w1", text: GOOD_TEXT })])),
      controlRoom: controlRoomFixture(7),
    }));
    const ids = view.sources.map((row) => row.id);
    expect(ids[0]).toBe("discovery-source:programs");
    expect(ids[1]).toBe("discovery-source:mission");
    expect(ids[2]).toBe("discovery-source:window");
    expect(ids[3]).toBe("discovery-source:result");
    expect(ids[ids.length - 1]).toBe("discovery-source:control-room");
    expect(ids.filter((id) => id.startsWith("discovery-source:evidence"))).toHaveLength(ids.length - 5);
  });

  it("does not mutate frozen inputs", () => {
    const inputs = baseInputs({
      conversation: conversationFixture(windowDoc([windowItem({ id: "w1", text: GOOD_TEXT })])),
      controlRoom: controlRoomFixture(7),
    });
    deepFreeze(inputs);
    const view = projectDiscovery(inputs);
    expect(view.scope).toBe("SUPPLIED_WORKSPACE");
    expect(() => projectDiscovery(inputs)).not.toThrow();
    expect(Object.isFrozen(inputs.projection.programs.source)).toBe(true);
  });
});
