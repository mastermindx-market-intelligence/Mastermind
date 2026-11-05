import { describe, expect, it, vi } from "vitest";
import {
  decodeSupervisionRead,
  type SupervisionRead,
  type SupervisionRow,
} from "./supervision-read";
import controlRoomFixture from "../fixtures/control-room-b5-c20a3cf8.json";

type Mutable = Record<string, any>;

const clone = (): Mutable => structuredClone(controlRoomFixture) as Mutable;
const unavailable = (reason: "SOURCE_UNAVAILABLE" | "SOURCE_INVALID") => ({
  state: "UNAVAILABLE",
  reason,
});

it("never invokes a getter before the incumbent identity parser", () => {
  const source = clone();
  const getter = vi.fn(() => "private");
  Object.defineProperty(source, "generated_at", {enumerable:true,get:getter});
  expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  expect(getter).not.toHaveBeenCalled();
});

it("rejects cyclic and over-budget source graphs before projection", () => {
  const source = clone();
  source.sources.loop = source;
  expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  const oversized = clone();
  oversized.sources.extra = "x".repeat(2_000_001);
  expect(decodeSupervisionRead(oversized)).toEqual(unavailable("SOURCE_INVALID"));
});

it.each(["target", "terminal"])("retains a reported unresolved %s companion effect", kind => {
  const source = clone();
  const row = source.autonomy.responsibilities[0];
  if (kind === "target") row.current_sol_target = {effect_state:"effect_unknown"};
  else row.dispatch.w3c.state = "EFFECT_UNKNOWN";
  expect(firstRow(decodeSupervisionRead(source)).unresolvedEffect).toBe(true);
});

function firstRow(read: SupervisionRead): SupervisionRow {
  if (read.state !== "AVAILABLE") throw new Error(`expected AVAILABLE, got ${read.state}`);
  return read.rows[0];
}

describe("decodeSupervisionRead", () => {
  it("decodes the canonical bounded fixture into detached rows", () => {
    const read = decodeSupervisionRead(controlRoomFixture);
    expect(read.state).toBe("AVAILABLE");
    expect(read).toEqual({
      state: "AVAILABLE",
      generatedAt: "2026-09-05T00:00:00Z",
      rows: [firstRow(read)],
      sourceFailureCount: 0,
      issueCount: 1,
    });
    const row = firstRow(read);
    // ProgramCard facts come straight from the existing parser output.
    expect(row.workRef).toBe("WS:B5");
    expect(row.title).toBe("Bounded fixture");
    expect(row.state).toBe("active");
    expect(row.rootJobId).toBe("JOB-B5");
    expect(row.rootState).toBe("RESOLVED");
    expect(row.rootCandidates).toEqual(["JOB-B5"]);
    expect(row.nextAction).toBeNull();
    expect(row.nextActionWithheld).toBe(false);
    // Consumed autonomy facts.
    expect(row.accountableSeat).toBe("ceo");
    expect(row.owedSeat).toBe("ceo");
    expect(row.owedReason).toBe("attention_targets_seat");
    expect(row.freshness).toBe("current");
    expect(row.queryStatus).toBe("ok");
    expect(row.dispatchState).toBe("RETURNED");
    expect(row.dispatchHistorical).toBe(false);
    // A null current_worker stays unknown and never becomes "none".
    expect(row.workerEffect).toBeNull();
    expect(row.sources).toEqual([
      {
        owner: "agent_os",
        ref: "agent_os_state.workstreams:B5",
        observedAt: "2026-09-03T00:00:01Z",
        freshness: "current",
      },
      {
        owner: "executive_inbox",
        ref: "ATTENTION-B5",
        observedAt: "2026-09-05T00:00:00Z",
        freshness: "current",
      },
    ]);
  });

  it("detaches the output from later source mutations and deep-freezes it", () => {
    const source = clone();
    const read = decodeSupervisionRead(source);
    if (read.state !== "AVAILABLE") throw new Error("expected AVAILABLE");
    const row = firstRow(read);
    expect(read.state).toBe("AVAILABLE");
    // Mutate the source document deeply after decoding.
    source.work[0].agent_os.title = "mutated title";
    source.work[0].agent_os.status = "held";
    source.work[0].agent_os.next_action = "do something else";
    source.autonomy.responsibilities[0].root_job_candidates.push("JOB-OTHER");
    source.autonomy.responsibilities[0].source_receipts[0].ref = "mutated";
    source.autonomy.issues.push({ code: "extra" });
    // The already decoded read keeps its detached values.
    expect(row.title).toBe("Bounded fixture");
    expect(row.state).toBe("active");
    expect(row.nextAction).toBeNull();
    expect(row.rootCandidates).toEqual(["JOB-B5"]);
    expect(row.sources[0].ref).toBe("agent_os_state.workstreams:B5");
    expect(read.issueCount).toBe(1);
    // No output array aliases the source document.
    expect(row.rootCandidates).not.toBe(
      controlRoomFixture.autonomy.responsibilities[0].root_job_candidates,
    );
    expect(row.sources[0]).not.toBe(
      controlRoomFixture.autonomy.responsibilities[0].source_receipts[0],
    );
    // Every level of the output is frozen.
    expect(Object.isFrozen(read)).toBe(true);
    if (read.state === "AVAILABLE") expect(Object.isFrozen(read.rows)).toBe(true);
    expect(Object.isFrozen(row)).toBe(true);
    expect(Object.isFrozen(row.rootCandidates)).toBe(true);
    expect(Object.isFrozen(row.sources)).toBe(true);
    expect(Object.isFrozen(row.sources[0])).toBe(true);
    expect(Object.isFrozen(decodeSupervisionRead(null))).toBe(true);
    // Attempts to mutate the frozen output throw.
    expect(() => (read.rows as unknown as { push: (v: unknown) => unknown }).push({})).toThrow();
    expect(() => {
      (row as unknown as Mutable).workRef = "WS:OTHER";
    }).toThrow();
  });

  it("stays unavailable for missing or non-object sources", () => {
    expect(decodeSupervisionRead(null)).toEqual(unavailable("SOURCE_UNAVAILABLE"));
    expect(decodeSupervisionRead(undefined)).toEqual(unavailable("SOURCE_UNAVAILABLE"));
    expect(decodeSupervisionRead(42)).toEqual(unavailable("SOURCE_INVALID"));
    expect(decodeSupervisionRead("control room")).toEqual(unavailable("SOURCE_INVALID"));
    expect(decodeSupervisionRead({})).toEqual(unavailable("SOURCE_INVALID"));
  });

  it("fails closed on duplicate responsibility rows", () => {
    const source = clone();
    source.autonomy.responsibilities = [
      ...source.autonomy.responsibilities,
      structuredClone(source.autonomy.responsibilities[0]),
    ];
    expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  });

  it("fails closed on an orphan responsibility row", () => {
    const source = clone();
    const orphan = structuredClone(source.autonomy.responsibilities[0]);
    orphan.responsibility_ref = "WS:GHOST";
    source.autonomy.responsibilities = [...source.autonomy.responsibilities, orphan];
    expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  });

  it("fails closed when a projected program has no responsibility row", () => {
    const source = clone();
    source.autonomy.responsibilities = [];
    expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  });

  const malformed: Array<[string, (source: Mutable) => void]> = [
    ["unknown freshness token", (s) => { s.autonomy.responsibilities[0].freshness = "live"; }],
    ["non-enum query_status", (s) => { s.autonomy.responsibilities[0].query_status = 7; }],
    ["unknown accountable seat", (s) => { s.autonomy.responsibilities[0].accountable_seat = "intern"; }],
    ["non-enum owed seat", (s) => { s.autonomy.responsibilities[0].owed_turn.seat = 42; }],
    ["multiline owed reason", (s) => { s.autonomy.responsibilities[0].owed_turn.reason = "line1\nline2"; }],
    ["owed_turn not an object", (s) => { s.autonomy.responsibilities[0].owed_turn = "ceo"; }],
    ["dispatch not an object", (s) => { s.autonomy.responsibilities[0].dispatch = 3; }],
    ["non-boolean dispatch historical", (s) => { s.autonomy.responsibilities[0].dispatch.historical = "no"; }],
    ["over-long dispatch state", (s) => { s.autonomy.responsibilities[0].dispatch.dispatch_state = "x".repeat(129); }],
    ["current_worker not an object", (s) => { s.autonomy.responsibilities[0].current_worker = "running"; }],
    ["unknown worker effect", (s) => { s.autonomy.responsibilities[0].current_worker = { effect_state: "applied_twice" }; }],
    ["over-long source ref", (s) => { s.autonomy.responsibilities[0].source_receipts[0].ref = "x".repeat(129); }],
    ["non-ISO observed_at", (s) => { s.autonomy.responsibilities[0].source_receipts[0].observed_at = "2026-09-05"; }],
    ["impossible observed_at", (s) => { s.autonomy.responsibilities[0].source_receipts[0].observed_at = "2026-02-30T00:00:00Z"; }],
    ["over-long receipt freshness", (s) => { s.autonomy.responsibilities[0].source_receipts[0].freshness = "x".repeat(65); }],
    ["receipts not a list", (s) => { s.autonomy.responsibilities[0].source_receipts = { owner: "agent_os" }; }],
    ["receipt entry not an object", (s) => { s.autonomy.responsibilities[0].source_receipts[0] = "agent_os"; }],
    ["issue array over bound", (s) => { s.autonomy.issues = Array.from({ length: 501 }, () => ({ code: "x" })); }],
    ["failure array over bound", (s) => { s.autonomy.source_failures = Array.from({ length: 501 }, () => ({ owner: "x" })); }],
    ["receipt array over bound", (s) => {
      s.autonomy.responsibilities[0].source_receipts = Array.from({ length: 501 }, () => ({
        owner: "agent_os",
        ref: "r",
        observed_at: "2026-09-05T00:00:00Z",
        freshness: "current",
      }));
    }],
  ];
  it.each(malformed)("fails the whole projection closed on %s", (_name, mutate) => {
    const source = clone();
    mutate(source);
    expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  });

  it("keeps the exact reference bound inclusive at 128 characters", () => {
    const ok = clone();
    ok.autonomy.responsibilities[0].source_receipts[0].ref = "x".repeat(128);
    expect(decodeSupervisionRead(ok)).not.toEqual(unavailable("SOURCE_INVALID"));
    const over = clone();
    over.autonomy.responsibilities[0].source_receipts[0].ref = "x".repeat(129);
    expect(decodeSupervisionRead(over)).toEqual(unavailable("SOURCE_INVALID"));
  });

  it("fails closed on accessor-bearing rows without reading them", () => {
    const source = clone();
    const row: Mutable = { ...source.autonomy.responsibilities[0] };
    delete row.freshness;
    let reads = 0;
    Object.defineProperty(row, "freshness", {
      enumerable: true,
      get: () => {
        reads += 1;
        return "current";
      },
    });
    source.autonomy.responsibilities = [row];
    expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
    expect(reads).toBe(0);
  });

  it("fails closed when the source root itself carries an accessor", () => {
    const source = clone();
    Object.defineProperty(source, "generated_at", {
      enumerable: true,
      get: () => "2026-09-05T00:00:00Z",
    });
    expect(decodeSupervisionRead(source)).toEqual(unavailable("SOURCE_INVALID"));
  });

  it("keeps an explicit worker effect distinct from an unreported one", () => {
    const withWorker = (currentWorker: unknown): SupervisionRead => {
      const source = clone();
      source.autonomy.responsibilities[0].current_worker = currentWorker;
      return decodeSupervisionRead(source);
    };
    expect(firstRow(withWorker({ effect_state: "none" })).workerEffect).toBe("none");
    expect(firstRow(withWorker({ effect_state: "applied" })).workerEffect).toBe("applied");
    expect(firstRow(withWorker({ effect_state: "effect_unknown" })).workerEffect).toBe(
      "effect_unknown",
    );
    // Null current_worker and a missing effect_state both stay unknown.
    expect(firstRow(withWorker(null)).workerEffect).toBeNull();
    expect(firstRow(withWorker({})).workerEffect).toBeNull();
    expect(firstRow(withWorker(null)).workerEffect).not.toBe(
      firstRow(withWorker({ effect_state: "none" })).workerEffect,
    );
  });

  it("preserves null unknowns for owed turn and dispatch", () => {
    const source = clone();
    source.autonomy.responsibilities[0].owed_turn = null;
    source.autonomy.responsibilities[0].dispatch = null;
    const row = firstRow(decodeSupervisionRead(source));
    expect(row.owedSeat).toBeNull();
    expect(row.owedReason).toBeNull();
    expect(row.dispatchState).toBeNull();
    expect(row.dispatchHistorical).toBeNull();
    expect(row.workerEffect).toBeNull();
  });

  it("keeps reported freshness as verbatim evidence with no authority field", () => {
    const stale = clone();
    stale.autonomy.responsibilities[0].freshness = "stale";
    expect(firstRow(decodeSupervisionRead(stale)).freshness).toBe("stale");
    const unknown = clone();
    unknown.autonomy.responsibilities[0].freshness = "unknown";
    expect(firstRow(decodeSupervisionRead(unknown)).freshness).toBe("unknown");
    const read = decodeSupervisionRead(controlRoomFixture);
    // No projection-wide liveness or readiness field is invented anywhere.
    expect(Object.keys(read).sort()).toEqual([
      "generatedAt",
      "issueCount",
      "rows",
      "sourceFailureCount",
      "state",
    ]);
    expect(Object.keys(firstRow(read)).sort()).toEqual([
      "accountableSeat",
      "dispatchHistorical",
      "dispatchState",
      "freshness",
      "nextAction",
      "nextActionWithheld",
      "owedReason",
      "owedSeat",
      "queryStatus",
      "rootCandidates",
      "rootJobId",
      "rootState",
      "sources",
      "state",
      "title",
      "workRef",
      "workerEffect",
    ]);
  });

  it("preserves the owner generation timestamp verbatim", () => {
    const source = clone();
    source.generated_at = "2025-01-02T03:04:05Z";
    source.autonomy.generated_at = "2025-01-02T03:04:05Z";
    const read = decodeSupervisionRead(source);
    if (read.state !== "AVAILABLE") throw new Error("expected AVAILABLE");
    expect(read.generatedAt).toBe("2025-01-02T03:04:05Z");
    const mismatched = clone();
    mismatched.autonomy.generated_at = "2025-01-02T03:04:05Z";
    expect(decodeSupervisionRead(mismatched)).toEqual(unavailable("SOURCE_INVALID"));
  });
});
