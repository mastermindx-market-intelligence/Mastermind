import { describe, expect, it, vi } from "vitest";
import { activationFacts } from "./activation-facts";
import {
  OperationController,
  type FiniteCommandPort,
  type PendingPointerStore,
  type OperationPointer,
  type OriginalOperationObservation,
} from "../orchestration/operation-controller";
import { decodeMission, decodeMissionv3, type MissionDocument } from "../mission";
import raw from "../fixtures/mission-v3-design-current-17-slots.json";
const selection = { workRef: "WS:B5", rootJobId: "JOB-100" };
const pointer: OperationPointer = {
  operationKey: "original-request-1",
  kind: "launch",
  targetKey: "opaque-not-a-root",
};
const original: OriginalOperationObservation = {
  pointer,
  owner: { principalScope: "owner-a", generation: "g1" },
  status: "accepted",
  missionSelection: selection,
};
function document(): MissionDocument {
  const d = decodeMissionv3(structuredClone(raw), selection);
  expect(d).not.toBeNull();
  return d as unknown as MissionDocument;
}
// Explicit inert lifecycle variations over the genuine decoded read. These are
// consumer join discriminators, not claims that this retained producer ran them.
function complete() {
  const d = document();
  const e = {
    owner: "EXECUTIVE_OS" as const,
    ref: "job:JOB-100",
    field: "transport",
    source_revision: "revision-1",
    source_time: null,
    observed_at: "2026-09-20T00:00:00Z",
    freshness_state: "CURRENT" as const,
  };
  d.transport.dispatch_state = "PICKUP_ACKNOWLEDGED";
  d.transport.historical = false;
  d.transport.evidence = [e];
  const worker = {
    continuation_state: null, capacity_state: null, previous_attempt_id: null, movement_reason_code: null,
    worker_id: "JOB-CHILD",
    attempt_id: "ATT-1",
    runtime_binding_id: "binding-1",
    binding_generation: 4,
    status: "COMPLETED" as const,
    effect_state: "applied" as const,
  };
  d.principal.current_worker = worker;
  d.children.items = [
    {
      status: "COMPLETED", depth: 1, orchestration_role: "work", plan_step_id: null, attempt_count: 1, attempt_limit: 1,
      job_id: "JOB-CHILD",
      parent_job_id: "JOB-100",
      worker_id: "JOB-CHILD",
      current_attempt_id: "ATT-1",
      latest_attempt: {
        attempt_id: "ATT-1",
        status: "COMPLETED" as const,
        started_at: "2026-09-20T00:01:00Z",
        attempt_number: 1, finished_at: null, exit_code: null, has_result: true, error_present: false, error_class: null,
      },
    },
  ];
  d.children.state = "AVAILABLE"; d.children.total_count = 1;
  const input: Record<string, unknown> = {...d, schema: "mastermind.mission_workspace.v2"};
  delete input.result_refs;
  const validated = decodeMission(input, selection);
  expect(validated).not.toBeNull();
  return validated!;
}
const facts = (d: MissionDocument | null, o = original) =>
  activationFacts(o, d)!.facts;
describe("six independent activation facts", () => {
  it("uses a genuine decoder output without inventing missing lifecycle facts", () => {
    const d = document();
    expect(
      facts(d)
        .slice(1)
        .every((f) => f.state === "unavailable"),
    ).toBe(true);
    expect(activationFacts(original, d)?.targetKey).toBe("opaque-not-a-root");
  });
  it("keeps pickup START and effect independent from return and acceptance", () => {
    const d = complete();
    expect(activationFacts(original, d)?.runtime).toEqual({
      jobId: "JOB-CHILD",
      workerId: "JOB-CHILD",
      attemptId: "ATT-1",
      bindingId: "binding-1",
      bindingGeneration: 4,
    });
    const rows = facts(d);
    expect(rows.map((x) => x.state)).toEqual([
      "reported",
      "reported",
      "reported",
      "reported",
      "unavailable",
      "unavailable",
    ]);
    d.transport.dispatch_state = "RETURNED";
    expect(facts(d)[1].state).toBe("unavailable");
    expect(facts(d)[4].state).toBe("reported");
  });
  it.each([
    "work",
    "root",
    "ambiguous",
    "historical",
    "source",
    "observation",
  ] as const)("refuses unrelated or stale %s Mission facts", (kind) => {
    const d = complete();
    if (kind === "work") d.program.work_ref = "WS:FOREIGN";
    if (kind === "root") d.mission.root_job_id = "JOB-FOREIGN";
    if (kind === "ambiguous") d.mission.root_job_ambiguous = true;
    if (kind === "historical") d.read_state.state = "HISTORICAL";
    if (kind === "source") d.source.owner_observation!.state = "CONFLICT";
    if (kind === "observation")
      d.source.owner_observation!.selection!.root_job_id = "JOB-FOREIGN";
    expect(
      facts(d)
        .slice(1)
        .every((x) => x.state === "unavailable"),
    ).toBe(true);
  });
  it("does not join wrong Attempt or infer START from completed status", () => {
    const d = complete();
    d.children.items[0].current_attempt_id = "ATT-FOREIGN";
    expect(facts(d)[2].state).toBe("unavailable");
    expect(facts(d)[3].state).toBe("unavailable");
    d.children.items[0].current_attempt_id = "ATT-1";
    d.children.items[0].latest_attempt!.started_at = null;
    expect(facts(d)[2].state).toBe("unavailable");
  });
  it("does not turn review approval or completion into acceptance", () => {
    const d = complete();
    d.acceptance.state = "NOT_PROJECTED";
    expect(facts(d)[5].state).toBe("unavailable");
    d.acceptance.state = "ACCEPTED";
    d.acceptance.evidence = [];
    expect(facts(d)[5].state).toBe("unavailable");
  });
  it("keeps unknown on the original recovery route, no inferred selection", () => {
    const o = {
      ...original,
      status: "unknown" as const,
      missionSelection: null,
    };
    const m = activationFacts(o, complete())!;
    expect(m.routes).toEqual(["original_status"]);
    expect(m.facts[0].state).toBe("held");
    expect(m.facts.slice(1).every((f) => f.state === "unavailable")).toBe(true);
  });
  it("holds explicit unknown effect and never aggregates a green outcome", () => {
    const d = complete();
    d.principal.current_worker!.effect_state = "effect_unknown";
    const m = activationFacts(original, d)!;
    expect(m.routes).toEqual(["work", "sessions"]);
    expect(m.facts[3].state).toBe("held");
    expect(m.facts[5].state).toBe("unavailable");
    expect(Object.isFrozen(m.facts[0].evidence[0])).toBe(true);
  });
});
function controller(accepted = true) {
  let ctx: ReturnType<FiniteCommandPort["context"]> = {
    principalScope: "owner-a",
    generation: "g1",
  };
  let saved: OperationPointer | null = null;
  const store: PendingPointerStore = {
    read: vi.fn(() => saved),
    reserve: vi.fn((_s, p) => {
      saved = p;
      return { reserved: true as const };
    }),
    clearIfEqual: vi.fn(() => {
      saved = null;
      return true;
    }),
  };
  const port: FiniteCommandPort = {
    context: vi.fn(() => ctx),
    prepare: vi.fn(() => pointer),
    submit: vi.fn(async () => ({
      ...pointer,
      disposition: accepted ? ("accepted" as const) : ("unknown" as const),
      ...(accepted ? { missionSelection: selection } : {}),
    })),
    readOperation: vi.fn(async () => ({
      ...pointer,
      disposition: "unknown" as const,
    })),
  };
  return {
    c: new OperationController(port, store),
    port,
    store,
    change: (v: typeof ctx) => {
      ctx = v;
    },
    saved: () => saved,
  };
}
describe("original controller receipt observation", () => {
  it("retains exact terminal tuple after pointer clearance without reads or effects", async () => {
    const f = controller();
    await f.c.begin({
      kind: "launch",
      targetKey: pointer.targetKey,
      payload: { private: "never observed" },
    });
    vi.mocked(f.store.read).mockClear();
    const o = f.c.observeOriginalOperation()!;
    expect(o.pointer).toEqual(pointer);
    expect(o.status).toBe("accepted");
    expect(f.c.getState().pointer).toBeNull();
    expect(JSON.stringify(o)).not.toContain("private");
    expect(f.store.read).not.toHaveBeenCalled();
    expect(f.port.readOperation).not.toHaveBeenCalled();
    expect(f.port.submit).toHaveBeenCalledTimes(1);
    expect(Object.isFrozen(o.pointer)).toBe(true);
  });
  it.each(["principal", "generation", "null", "throw"] as const)(
    "withholds on no-render %s withdrawal without clearing original",
    async (kind) => {
      const f = controller(false);
      await f.c.begin({
        kind: "launch",
        targetKey: pointer.targetKey,
        payload: {},
      });
      if (kind === "principal")
        f.change({ principalScope: "foreign", generation: "g1" });
      if (kind === "generation")
        f.change({ principalScope: "owner-a", generation: "g2" });
      if (kind === "null") f.change(null);
      if (kind === "throw")
        vi.mocked(f.port.context).mockImplementation(() => {
          throw Error("private");
        });
      expect(f.c.observeOriginalOperation()).toBeNull();
      expect(f.saved()).toEqual(pointer);
      expect(f.store.clearIfEqual).not.toHaveBeenCalled();
      expect(f.c.getState().status).toBe("unknown");
    },
  );
  it("invalidate removes terminal provenance without new store effects", async () => {
    const f = controller();
    await f.c.begin({
      kind: "launch",
      targetKey: pointer.targetKey,
      payload: {},
    });
    f.c.invalidate();
    expect(f.c.observeOriginalOperation()).toBeNull();
    expect(f.port.submit).toHaveBeenCalledTimes(1);
  });
});

it("a foreign receipt cannot lend its Mission selection to the original request", async () => {
  const f = controller();
  vi.mocked(f.port.submit).mockResolvedValue({
    ...pointer,
    operationKey: "foreign-request",
    disposition: "accepted",
    missionSelection: selection,
  });
  await f.c.begin({
    kind: "launch",
    targetKey: pointer.targetKey,
    payload: {},
  });
  const observed = f.c.observeOriginalOperation()!;
  expect(observed.pointer).toEqual(pointer);
  expect(observed.status).toBe("unknown");
  expect(observed.missionSelection).toBeNull();
  expect(
    activationFacts(observed, complete())!
      .facts.slice(1)
      .every((x) => x.state === "unavailable"),
  ).toBe(true);
  expect(f.saved()).toEqual(pointer);
});
