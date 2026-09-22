import availablePrograms from "./fixtures/programs-available-workspace-service.json";
import unavailablePrograms from "./fixtures/programs-unavailable-workspace-service.json";
import current from "./fixtures/mission-v2-current-128c46f6.json";
import conflict from "./fixtures/mission-v2-conflict-128c46f6.json";
import unknown from "./fixtures/mission-v2-unknown-128c46f6.json";
import { describe, expect, it } from "vitest";
import baseline from "./fixtures/mission-v2-baseline-80518e41.json";
import controlRoom from "./fixtures/control-room-b5-c20a3cf8.json";
import { decodeMission } from "./mission";
import {
  decodeOwnerObservation,
  decodeProgramsEnvelope,
  decodeWindow,
  observedMissionAssociation,
} from "./workspace-contract";
import v3Current17 from "./fixtures/mission-v3-design-current-17-slots.json";

const pair = { work_ref: "WS:ONE", root_job_id: "JOB-1" };
const selection = { workRef: pair.work_ref, rootJobId: pair.root_job_id };
const h = "a".repeat(64);
// Structural consumer fixtures only: owner provenance is tested by the service.
const receipt = (mission = true) => ({
  schema: "mastermind.workspace_source_observation.v1",
  state: "SAME",
  selection: mission ? pair : null,
  control_room: {
    instance_before: "owner",
    instance_after: "owner",
    publication_before: 1,
    publication_after: 1,
    document_digest: h,
    source_validity_digest: h,
    cache_currentness_digest: h,
  },
  runtime: mission
    ? {
        schema: "mastermind.runtime_read_observation.v1",
        state: "SAME",
        source_identity: "request-owner",
        before: 1,
        after: 1,
        snapshot_digest: h,
      }
    : null,
});
function mission(current = false) {
  const v = structuredClone(baseline) as typeof baseline & {
    source: typeof baseline.source & {
      owner_observation: ReturnType<typeof receipt>;
    };
  };
  v.source.owner_observation = receipt();
  if (current) {
    v.read_state.state = "CURRENT";
    v.read_state.reason_codes = [];
    v.missingness = v.missingness.filter(
      (x) => x.target_field !== "source.generation_vector",
    );
  } else v.source.owner_observation.state = "UNKNOWN";
  return v;
}
describe("exact Mission v2 consumer", () => {
  it("decodes real composer baseline plus explicit unknown receipt without promoting completion", () => {
    const decoded = decodeMission(mission(), selection);
    expect(decoded?.execution.state).toBe("COMPLETED");
    expect(decoded?.acceptance.state).toBe("NOT_PROJECTED");
    expect(decoded?.read_state.state).toBe("PARTIAL");
    expect(decodeMission(baseline, selection)).toBeNull();
  });
  it("requires a coherent SAME observation for as-of CURRENT", () => {
    expect(decodeMission(mission(true), selection)?.read_state.state).toBe(
      "CURRENT",
    );
    for (const mutate of [
      (v: ReturnType<typeof mission>) => {
        v.source.owner_observation.state = "UNKNOWN";
      },
      (v: ReturnType<typeof mission>) => {
        v.source.owner_observation.control_room.instance_after = "other";
      },
      (v: ReturnType<typeof mission>) => {
        v.source.owner_observation.control_room.publication_after = 2;
      },
      (v: ReturnType<typeof mission>) => {
        v.source.owner_observation.runtime!.after = 2;
      },
      (v: ReturnType<typeof mission>) => {
        v.source.owner_observation.control_room.document_digest =
          "not-a-digest";
      },
      (v: ReturnType<typeof mission>) => {
        v.source.owner_observation.selection = {
          work_ref: "WS:OTHER",
          root_job_id: "JOB-1",
        };
      },
      (v: ReturnType<typeof mission>) => {
        v.execution.state = "ACCEPTED";
      },
      (v: ReturnType<typeof mission>) => {
        v.acceptance.state = "ACCEPTED";
      },
    ]) {
      const v = mission(true);
      mutate(v);
      expect(decodeMission(v, selection)).toBeNull();
    }
    expect(
      decodeMission(mission(true), { ...selection, rootJobId: "JOB-other" }),
    ).toBeNull();
  });
  it("rejects unknown receipt keys even when values look consistent", () => {
    expect(
      decodeOwnerObservation({ ...receipt(), trusted: true }, pair),
    ).toBeNull();
    const r = receipt();
    r.state = "UNKNOWN";
    expect(decodeOwnerObservation(r, pair)?.state).toBe("UNKNOWN");
  });
});
describe("Programs transport envelope", () => {
  const envelope = () => ({
    schema: "mastermind.workspace_programs.v1",
    availability: "AVAILABLE",
    control_room: controlRoom,
    source_observation: receipt(false),
    reason_codes: [],
  });
  it("unwraps only the qualified closed envelope", () => {
    expect(decodeProgramsEnvelope(envelope())).toEqual(controlRoom);
    expect(() =>
      decodeProgramsEnvelope({ ...envelope(), extra: true }),
    ).toThrow();
    expect(() =>
      decodeProgramsEnvelope({
        ...envelope(),
        availability: "UNAVAILABLE",
        control_room: null,
      }),
    ).toThrow("PROGRAM_SOURCE_UNAVAILABLE");
    const v = envelope();
    v.source_observation.state = "UNKNOWN";
    expect(() => decodeProgramsEnvelope(v)).toThrow(
      "PROGRAM_SOURCE_UNQUALIFIED",
    );
  });
});
const windowFixture = () => ({
  schema: "mastermind.workspace.window_read_candidate.v1",
  selection_ref: "managed-window:one",
  mode: "observed-turn-window",
  view: {
    schema: "mastermind.workspace.visible_window_candidate.v1",
    source_ref: "managed-window:one",
    scope: "one-managed-turn-window",
    observed_at: "2026-09-21T07:00:00Z",
    epoch: h,
    terminal: false,
    coverage: "OBSERVED_WINDOW",
    history: "NOT_PROVEN",
    acceptance: "NOT_PROJECTED",
    capabilities: { send: false, provider_control: false, history: false },
    items: [
      {
        id: `visible:${h}`,
        source_sequence: 0,
        publication_sequence: 1,
        state: "completed",
        kind: "visible-response",
        text: "hello",
        representation: "VISIBLE_TEXT",
        display_sha256:
          "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
      },
    ],
    gaps: [],
  },
});
describe("current permitted window", () => {
  it("validates display hash and refuses authority/history upgrades", async () => {
    expect((await decodeWindow(windowFixture()))?.view.items[0].text).toBe(
      "hello",
    );
    const v = windowFixture();
    v.view.items[0].text = "changed";
    expect(await decodeWindow(v)).toBeNull();
    for (const field of ["send", "provider_control", "history"] as const) {
      const v = windowFixture();
      v.view.capabilities[field] = true;
      expect(await decodeWindow(v)).toBeNull();
    }
    const accepted = windowFixture();
    accepted.view.acceptance = "ACCEPTED";
    expect(await decodeWindow(accepted)).toBeNull();
  });
  it("retains withheld missingness without text or digest", async () => {
    const v = windowFixture() as unknown as {
      view: { items: Array<Record<string, unknown>> };
    };
    Object.assign(v.view.items[0], {
      kind: "withheld",
      text: null,
      display_sha256: null,
      representation: "WITHHELD",
    });
    expect((await decodeWindow(v))?.view.items[0].text).toBeNull();
    v.view.items[0].text = "hidden";
    expect(await decodeWindow(v)).toBeNull();
  });
  it("rejects duplicated items, bad time, and mismatched source", async () => {
    const v = windowFixture();
    v.view.items.push(v.view.items[0]);
    expect(await decodeWindow(v)).toBeNull();
    const time = windowFixture();
    time.view.observed_at = "2026-09-21";
    expect(await decodeWindow(time)).toBeNull();
    const source = windowFixture();
    source.view.source_ref = "managed-window:other";
    expect(await decodeWindow(source)).toBeNull();
  });
});

const ATT = "ATT-" + "ab".repeat(16);
const planChild = {
  job_id: "JOB-101",
  status: "RUNNING",
  parent_job_id: "JOB-100",
  depth: 1,
  orchestration_role: "plan",
  plan_step_id: null,
  attempt_count: 1,
  attempt_limit: 2,
  current_attempt_id: ATT,
  latest_attempt: {
    attempt_id: ATT,
    attempt_number: 1,
    status: "RUNNING",
    started_at: "2026-09-20T00:00:00Z",
    finished_at: null,
    exit_code: null,
    has_result: false,
    error_present: false,
    error_class: null,
  },
  worker_id: null,
};
function v2Window() {
  const v = windowFixture();
  return {
    ...v,
    schema: "mastermind.workspace.window_read_candidate.v2" as const,
    observation_binding: { job_id: "JOB-101", attempt_id: ATT },
  };
}
function qualifyingMission() {
  const mission = structuredClone(v3Current17) as any;
  mission.children = {
    ...mission.children,
    state: "AVAILABLE",
    coverage: "COMPLETE",
    items: [planChild],
    total_count: 1,
    overflow_count: 0,
    unjoined_job_count: 0,
    unjoined_job_ids: [],
  };
  return mission;
}

describe("window v2 tagged union and observed association", () => {
  it("accepts exact v2 and refuses extra, missing, or coerced tuple members", async () => {
    const decoded = await decodeWindow(v2Window());
    expect(decoded?.schema).toBe(
      "mastermind.workspace.window_read_candidate.v2",
    );
    expect(
      decoded && "observation_binding" in decoded
        ? decoded.observation_binding
        : null,
    ).toEqual({ job_id: "JOB-101", attempt_id: ATT });
    expect(await decodeWindow(windowFixture())).toMatchObject({
      schema: "mastermind.workspace.window_read_candidate.v1",
    });
    const extra = v2Window() as Record<string, unknown>;
    extra.root = "JOB-100";
    expect(await decodeWindow(extra)).toBeNull();
    const missing = { ...v2Window() } as Record<string, unknown>;
    delete missing.observation_binding;
    expect(await decodeWindow(missing)).toBeNull();
    const badJob = v2Window();
    badJob.observation_binding.job_id = "JOB-CHILD";
    expect(await decodeWindow(badJob)).toBeNull();
    const trimmed = v2Window();
    trimmed.observation_binding.job_id = " JOB-101";
    expect(await decodeWindow(trimmed)).toBeNull();
    const extraTuple = v2Window() as any;
    extraTuple.observation_binding.root = "JOB-100";
    expect(await decodeWindow(extraTuple)).toBeNull();
  });
  it("v1 can display content but never associates; v2 associates only the conservative plan child", async () => {
    const selection = { workRef: "WS:B5", rootJobId: "JOB-100" };
    const v1 = await decodeWindow(windowFixture());
    const mission = qualifyingMission();
    expect(observedMissionAssociation(v1, mission, selection)).toBeNull();
    const v2 = await decodeWindow(v2Window());
    const observed = observedMissionAssociation(v2, mission, selection);
    expect(observed?.state).toBe("OBSERVED_MISSION_ASSOCIATION");
    expect(observed?.job_id).toBe("JOB-101");
    expect(observed?.attempt_id).toBe(ATT);
    expect(observed?.window_observed_at).toBe("2026-09-21T07:00:00Z");
    expect(observed?.mission_generated_at).toBe(mission.generated_at);
    const foreign = structuredClone(mission);
    foreign.children.items[0].current_attempt_id =
      "ATT-" + "cd".repeat(16);
    foreign.children.items[0].latest_attempt.attempt_id =
      "ATT-" + "cd".repeat(16);
    expect(observedMissionAssociation(v2, foreign, selection)).toBeNull();
    const work = structuredClone(mission);
    work.children.items[0].orchestration_role = "work";
    expect(observedMissionAssociation(v2, work, selection)).toBeNull();
    const terminal = structuredClone(v2Window());
    terminal.view.terminal = true;
    expect(
      observedMissionAssociation(
        await decodeWindow(terminal),
        mission,
        selection,
      ),
    ).toBeNull();
    const unjoined = structuredClone(mission);
    unjoined.children.coverage = "INCOMPLETE";
    unjoined.children.unjoined_job_ids = ["JOB-102"];
    unjoined.children.unjoined_job_count = 1;
    expect(observedMissionAssociation(v2, unjoined, selection)).toBeNull();
  });
});

it("consumes actual 128c46f6 compositor CURRENT, CONFLICT and UNKNOWN fixtures", () => {
  expect(decodeMission(current, selection)?.read_state.state).toBe("CURRENT");
  expect(decodeMission(conflict, selection)?.read_state.state).toBe("PARTIAL");
  expect(decodeMission(unknown, selection)?.read_state.state).toBe("PARTIAL");
});

it("does not call a historical transport CURRENT even with a SAME receipt", () => {
  const value = structuredClone(current);
  value.transport.historical = true;
  expect(decodeMission(value, selection)).toBeNull();
});

it("consumes actual service Programs envelopes without turning unavailability into empty success", () => {
  expect(decodeProgramsEnvelope(availablePrograms)).toEqual(
    availablePrograms.control_room,
  );
  expect(() => decodeProgramsEnvelope(unavailablePrograms)).toThrow(
    "PROGRAM_SOURCE_UNAVAILABLE",
  );
});
