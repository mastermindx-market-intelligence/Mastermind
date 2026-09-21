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
} from "./workspace-contract";

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
