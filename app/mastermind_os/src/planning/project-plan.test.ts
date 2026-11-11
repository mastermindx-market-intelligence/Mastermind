import { describe, expect, it } from "vitest";
import {
  ADOPTION_REASON_NOT_DECLARED,
  ADOPTION_STATE_UNAVAILABLE,
  BODY_SCHEMA,
  CANONICAL_REPOSITORY,
  MAX_RESPONSE_BYTES,
  VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER,
  VERSION_HISTORY_REASON_SOURCE_UNAVAILABLE,
  canonicalRecordPath,
  decodeProjectPlan,
  validProjectPlanSelection,
} from "./project-plan";

const KEY = "READER";
const WORK_REF = `WS:${KEY}`;
const SELECTION = { work_ref: WORK_REF };

/** 40-char lowercase hex commit ids. */
const COMMIT_A = "5aae3c5e97dcdcf85d0745062fe9424f1ed7c0c7";
const COMMIT_B = "3f7a1c9e2b64d8051a2c4e6f8b0d9a3c5e7f9b11";
/** 64-char lowercase hex content digests. */
const CONTENT_A = "11".repeat(32);
const CONTENT_B = "ab".repeat(32);
const PATH = canonicalRecordPath(KEY);

const byteLength = (value: string): number => new TextEncoder().encode(value).length;

type Body = Record<string, any>;

function makeSource(overrides: Body = {}): Body {
  return {
    repository: CANONICAL_REPOSITORY,
    commit: COMMIT_A,
    path: PATH,
    content_sha256: CONTENT_A,
    ...overrides,
  };
}

function makeWave(id: string, overrides: Body = {}): Body {
  return {
    id,
    title: `Wave ${id}`,
    status: "active",
    depends_on: [],
    next_action: null,
    prs: [],
    ...overrides,
  };
}

function makePlan(overrides: Body = {}): Body {
  return {
    title: "Market intelligence macro read lane",
    objective: "Keep the authored macro read lane addressable end to end.",
    status: "done",
    owner: "workspace-planner",
    next_action: null,
    waves: [
      makeWave("w1", { status: "done", prs: [5593] }),
      makeWave("w2", {
        status: "awaiting_review",
        depends_on: ["w3"],
        next_action: "Land the focused tests.",
        prs: [5594, 5595],
      }),
      makeWave("w3", { status: "parked" }),
      makeWave("w4", { status: "killed", depends_on: ["w1", "w3"] }),
    ],
    adoption: { state: ADOPTION_STATE_UNAVAILABLE, reason: ADOPTION_REASON_NOT_DECLARED },
    version_history: {
      state: "AVAILABLE",
      kind: "GIT_RECORD_REVISIONS",
      revisions: [
        { commit: COMMIT_A, committed_at: "2026-10-30T10:22:31+02:00", content_sha256: CONTENT_A },
        { commit: COMMIT_B, committed_at: "2026-10-28T08:00:00Z", content_sha256: CONTENT_B },
      ],
    },
    ...overrides,
  };
}

function makeBody(overrides: Body = {}): Body {
  return {
    schema: BODY_SCHEMA,
    selection: { work_ref: WORK_REF },
    availability: "AVAILABLE",
    source: makeSource(),
    plan: makePlan(),
    reason_codes: [],
    ...overrides,
  };
}

function makeUnavailableBody(reason: string, overrides: Body = {}): Body {
  return {
    schema: BODY_SCHEMA,
    selection: { work_ref: WORK_REF },
    availability: "UNAVAILABLE",
    source: null,
    plan: null,
    reason_codes: [reason],
    ...overrides,
  };
}

/** The whole wire frame: canonical envelope plus exactly one delimiter. */
const wire = (body: unknown): string => `${JSON.stringify({ ok: true, result: body })}\n`;

const decode = (body: unknown): unknown => decodeProjectPlan(body, SELECTION);

/** Asserts the exact value-free constant, never a fragment of the input. */
function expectInvalid(input: unknown, selection: { work_ref: string } = SELECTION): void {
  let thrown: unknown;
  try {
    decodeProjectPlan(input, selection);
  } catch (error) {
    thrown = error;
  }
  expect(thrown).toBeInstanceOf(Error);
  expect((thrown as Error).message).toBe("PROJECT_PLAN_INVALID");
}

/** An available body padded with ASCII next_action text to an exact byte size. */
function boundaryBody(totalBytes: number): Body {
  const waves = Array.from({ length: 8 }, (_, index) => makeWave(`w${index}`));
  const body = makeBody({ plan: makePlan({ waves }) });
  const base = byteLength(wire(body));
  // Each `null` next_action (4 bytes) becomes quotes plus content (len + 2
  // bytes), so the content lengths must sum to totalBytes - base + 2 per wave.
  const deficit = totalBytes - base + 2 * waves.length;
  expect(deficit).toBeGreaterThan(0);
  const per = Math.floor(deficit / waves.length);
  const remainder = deficit - per * waves.length;
  expect(per).toBeLessThanOrEqual(16384);
  body.plan.waves = waves.map((wave: Body, index: number) => ({
    ...wave,
    next_action: "x".repeat(per + (index === 0 ? remainder : 0)),
  }));
  expect(byteLength(wire(body))).toBe(totalBytes);
  return body;
}

describe("validProjectPlanSelection", () => {
  it("accepts strict WS: UPPER-KEBAB selectors", () => {
    expect(validProjectPlanSelection({ work_ref: WORK_REF })).toBe(true);
    expect(validProjectPlanSelection({ work_ref: "WS:READER-1" })).toBe(true);
    expect(validProjectPlanSelection({ work_ref: `WS:${"A".repeat(64)}` })).toBe(true);
  });

  it("rejects non-strict selectors and shapes", () => {
    expect(validProjectPlanSelection({ work_ref: "WS:A" })).toBe(false); // key too short
    expect(validProjectPlanSelection({ work_ref: `WS:${"A".repeat(65)}` })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: "WS:reader" })).toBe(false); // lowercase
    expect(validProjectPlanSelection({ work_ref: "WS:A--B" })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: "WS:-A" })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: "WS:A-" })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: "WS:READER\n" })).toBe(false); // $ keeps the newline out
    expect(validProjectPlanSelection({ work_ref: "JOB:READER" })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: "agentos/workstreams/WS-READER.md" })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: 7 })).toBe(false);
    expect(validProjectPlanSelection({ work_ref: WORK_REF, path: "extra" })).toBe(false);
    expect(validProjectPlanSelection([WORK_REF])).toBe(false);
    expect(validProjectPlanSelection(null)).toBe(false);
    expect(validProjectPlanSelection("WS:READER")).toBe(false);
  });
});

describe("decodeProjectPlan: public available body", () => {
  it("decodes the full body with real fields", () => {
    expect(decode(makeBody())).toEqual({
      schema: BODY_SCHEMA,
      selection: { work_ref: WORK_REF },
      availability: "AVAILABLE",
      source: {
        repository: CANONICAL_REPOSITORY,
        commit: COMMIT_A,
        path: "agentos/workstreams/WS-READER.md",
        content_sha256: CONTENT_A,
      },
      plan: {
        title: "Market intelligence macro read lane",
        objective: "Keep the authored macro read lane addressable end to end.",
        status: "done",
        owner: "workspace-planner",
        next_action: null,
        waves: [
          { id: "w1", title: "Wave w1", status: "done", depends_on: [], next_action: null, prs: [5593] },
          {
            id: "w2",
            title: "Wave w2",
            status: "awaiting_review",
            depends_on: ["w3"],
            next_action: "Land the focused tests.",
            prs: [5594, 5595],
          },
          { id: "w3", title: "Wave w3", status: "parked", depends_on: [], next_action: null, prs: [] },
          { id: "w4", title: "Wave w4", status: "killed", depends_on: ["w1", "w3"], next_action: null, prs: [] },
        ],
        adoption: { state: "UNAVAILABLE", reason: "NOT_DECLARED" },
        version_history: {
          state: "AVAILABLE",
          kind: "GIT_RECORD_REVISIONS",
          revisions: [
            { commit: COMMIT_A, committed_at: "2026-10-30T10:22:31+02:00", content_sha256: CONTENT_A },
            { commit: COMMIT_B, committed_at: "2026-10-28T08:00:00Z", content_sha256: CONTENT_B },
          ],
        },
      },
      reason_codes: [],
    });
  });

  it("keeps authored statuses verbatim, including parked and killed", () => {
    const decoded = decode(makeBody()) as { plan: { waves: Array<{ status: string }> } };
    expect(decoded.plan.waves.map((wave) => wave.status)).toEqual([
      "done",
      "awaiting_review",
      "parked",
      "killed",
    ]);
  });

  it("treats authored done as record state, never adoption", () => {
    const decoded = decode(makeBody()) as { plan: { adoption: Record<string, string> } };
    expect(decoded.plan.adoption).toEqual({ state: "UNAVAILABLE", reason: "NOT_DECLARED" });
  });

  it("supports forward dependencies in authored order", () => {
    const decoded = decode(makeBody()) as { plan: { waves: Array<{ id: string; depends_on: string[] }> } };
    expect(decoded.plan.waves.map((wave) => wave.id)).toEqual(["w1", "w2", "w3", "w4"]);
    expect(decoded.plan.waves[1].depends_on).toEqual(["w3"]);
  });

  it("decodes the typed unavailable body", () => {
    expect(decode(makeUnavailableBody("RECORD_NOT_FOUND"))).toEqual({
      schema: BODY_SCHEMA,
      selection: { work_ref: WORK_REF },
      availability: "UNAVAILABLE",
      source: null,
      plan: null,
      reason_codes: ["RECORD_NOT_FOUND"],
    });
    expect(decode(makeUnavailableBody("CONTENT_OVER_BUDGET"))).toEqual({
      schema: BODY_SCHEMA,
      selection: { work_ref: WORK_REF },
      availability: "UNAVAILABLE",
      source: null,
      plan: null,
      reason_codes: ["CONTENT_OVER_BUDGET"],
    });
  });

  it("decodes owner-unavailable and source-unavailable version history", () => {
    const owner = makeBody({
      plan: makePlan({
        version_history: { state: "UNAVAILABLE", reason: VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER },
      }),
    });
    expect(decode(owner)).toEqual(owner);
    const source = makeBody({
      plan: makePlan({
        version_history: { state: "UNAVAILABLE", reason: VERSION_HISTORY_REASON_SOURCE_UNAVAILABLE },
      }),
    });
    expect(decode(source)).toEqual(source);
    expect((decode(source) as { plan: Body }).plan.version_history).toEqual({
      state: "UNAVAILABLE",
      reason: "SOURCE_UNAVAILABLE",
    });
  });

  it("accepts Unicode content within the byte budget", () => {
    const body = makeBody({
      plan: makePlan({
        title: "宏观 reads — méqué 📈 lane",
        waves: [makeWave("w1", { title: "中文 wave 🚀", status: "parked", prs: [1, 2, 3] })],
      }),
    });
    expect(byteLength(wire(body))).toBeLessThan(MAX_RESPONSE_BYTES);
    const decoded = decode(body) as { plan: { title: string } };
    expect(decoded.plan.title).toBe("宏观 reads — méqué 📈 lane");
  });

  it("accepts Git-record history at the 8-revision bound with ISO forms", () => {
    const stamps = [
      "2026-10-30T10:22:31+02:00",
      "2026-10-28T08:00:00Z",
      "2026-10-27T08:00:00.123456+00:00",
      "2026-10-26 08:00:00+00:00",
      "2026-10-25T08:00+00:00",
      "20261024T080000+0000",
      "2026-10-23T08:00:00-05:00",
      "2026-10-22T08:00:00+23:59",
    ];
    const revisions = stamps.map((committed_at, index) => ({
      commit: `${String(index).padStart(2, "0")}${COMMIT_A.slice(2)}`,
      committed_at,
      content_sha256: index === 0 ? CONTENT_A : CONTENT_B,
    }));
    const body = makeBody({
      plan: makePlan({
        version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions },
      }),
    });
    const decoded = decode(body) as { plan: { version_history: { revisions: unknown[] } } };
    expect(decoded.plan.version_history.revisions).toHaveLength(8);
  });

  it("accepts an empty wave list", () => {
    const decoded = decode(makeBody({ plan: makePlan({ waves: [] }) }));
    expect(decoded).toEqual(makeBody({ plan: makePlan({ waves: [] }) }));
  });

  it("consumes the actual already-parsed public body", () => {
    expect(decodeProjectPlan(makeBody(), SELECTION)).toEqual(makeBody());
  });

  it("returns detached results", () => {
    const first = decode(makeBody()) as Body;
    const second = decode(makeBody()) as Body;
    expect(first).not.toBe(second);
    expect(first.plan).not.toBe(second.plan);
    expect(first).toEqual(second);
    first.plan.title = "mutated";
    first.plan.waves[0].prs.push(999999);
    first.plan.waves[0].depends_on.push("w9");
    first.source.commit = "z".repeat(40);
    const third = decode(makeBody());
    expect(third).toEqual(second);
    expect(third).not.toBe(second);
  });

  it("fails closed for a malformed expected selection", () => {
    expectInvalid(makeBody(), { work_ref: "WS:reader" });
    expectInvalid(makeBody(), { work_ref: "WS:A" });
    expectInvalid(makeBody(), { work_ref: "WS:READER\n" });
    expectInvalid(makeBody(), { work_ref: "WS:OTHER", path: "x" } as unknown as { work_ref: string });
  });
});

describe("decodeProjectPlan: public transport boundary", () => {
  it("rejects internal envelopes, serialized JSON and byte buffers", () => {
    expectInvalid({ ok: true, result: makeBody() });
    expectInvalid(wire(makeBody()));
    expectInvalid(JSON.stringify(makeBody()));
    expectInvalid(new TextEncoder().encode(wire(makeBody())));
    expectInvalid(new Uint8Array([0xff, 0xfe, 0x0a]));
    expectInvalid(null); expectInvalid([]); expectInvalid(42); expectInvalid(true); expectInvalid(undefined);
  });

  it("enforces the response byte budget", () => {
    const exact = boundaryBody(MAX_RESPONSE_BYTES);
    expect(decode(exact)).toEqual(decode(exact));
    expect((decode(exact) as Body).plan).toBeDefined();

    const over = boundaryBody(MAX_RESPONSE_BYTES);
    over.plan.waves[7].next_action += "x";
    expectInvalid(over);
  });

  it("rejects Unicode bodies whose UTF-8 bytes exceed the budget", () => {
    const waves = Array.from({ length: 8 }, (_, index) =>
      makeWave(`w${index}`, { next_action: "é".repeat(16384) }),
    );
    const body = makeBody({ plan: makePlan({ waves }) });
    // Every field bound holds on a code-point count; only the byte budget trips.
    expectInvalid(body);
  });
});

describe("decodeProjectPlan: closed body shape", () => {
  it("rejects raw-body sentinel metadata", () => {
    const body = makeBody();
    body.secret_sentinel = "CLASSIFIED-123";
    expectInvalid(body);
  });

  it("rejects a missing or extra top-level key", () => {
    const missing = makeBody();
    delete missing.reason_codes;
    expectInvalid(missing);
    const extra = makeBody();
    extra.wait = { until: "ci" };
    expectInvalid(extra);
  });

  it("rejects a wrong schema", () => {
    expectInvalid(makeBody({ schema: "mastermind.workspace_project_plan.v2" }));
    expectInvalid(makeBody({ schema: 1 }));
  });

  it("rejects non-object bodies", () => {
    expectInvalid(null);
    expectInvalid([]);
  });
});

describe("decodeProjectPlan: selection", () => {
  it("rejects selector companions on the body selection", () => {
    expectInvalid(makeBody({ selection: { work_ref: WORK_REF, path: PATH } }));
    expectInvalid(makeBody({ selection: { work_ref: WORK_REF, commit: COMMIT_A } }));
    expectInvalid(makeBody({ selection: {} }));
    expectInvalid(makeBody({ selection: null }));
  });

  it("requires the selection to match the selected work_ref", () => {
    expectInvalid(makeBody({ selection: { work_ref: "WS:OTHER" } }));
    expectInvalid(makeBody({ selection: { work_ref: "WS:reader" } }));
    expectInvalid(makeBody({ selection: { work_ref: `WS:${KEY}\n` } }));
  });
});

describe("decodeProjectPlan: source identity", () => {
  it("rejects a foreign repository", () => {
    expectInvalid(makeBody({ source: makeSource({ repository: "other/macro" }) }));
  });

  it("rejects malformed commits and digests", () => {
    expectInvalid(makeBody({ source: makeSource({ commit: COMMIT_A.toUpperCase() }) }));
    expectInvalid(makeBody({ source: makeSource({ commit: COMMIT_A.slice(1) }) }));
    expectInvalid(makeBody({ source: makeSource({ commit: `${COMMIT_A}\n` }) }));
    expectInvalid(makeBody({ source: makeSource({ content_sha256: CONTENT_A.slice(1) }) }));
    expectInvalid(makeBody({ source: makeSource({ content_sha256: "AB".repeat(32) }) }));
    expectInvalid(makeBody({ source: makeSource({ commit: 42 }) }));
  });

  it("rejects a path that is not the canonical Store path of the selection", () => {
    expectInvalid(makeBody({ source: makeSource({ path: "agentos/workstreams/WS-OTHER.md" }) }));
    expectInvalid(makeBody({ source: makeSource({ path: "agentos/workstreams/WS-READER.MD" }) }));
    expectInvalid(makeBody({ source: makeSource({ path: `${PATH}\n` }) }));
    expectInvalid(makeBody({ source: makeSource({ path: `${PATH} ` }) }));
    expectInvalid(makeBody({ source: makeSource({ path: 42 }) }));
  });

  it("rejects extra or missing source keys on an available body", () => {
    expectInvalid(makeBody({ source: { ...makeSource(), key: KEY } }));
    const missing = makeSource();
    delete missing.content_sha256;
    expectInvalid(makeBody({ source: missing }));
    expectInvalid(makeBody({ source: null }));
  });
});

describe("decodeProjectPlan: plan projection", () => {
  it("rejects a missing or extra plan key", () => {
    const extra = makeBody();
    extra.plan.adopted_version = "v9";
    expectInvalid(extra);
    const missing = makeBody();
    delete missing.plan.adoption;
    expectInvalid(missing);
  });

  it("rejects overlong text fields", () => {
    const plan = makePlan();
    plan.title = "x".repeat(513);
    expectInvalid(makeBody({ plan }));
    plan.title = "x".repeat(512);
    plan.objective = "x".repeat(16385);
    expectInvalid(makeBody({ plan }));
    plan.objective = "x".repeat(16384);
    plan.owner = "x".repeat(257);
    expectInvalid(makeBody({ plan }));
    plan.owner = "workspace-planner";
    plan.status = "x".repeat(65);
    expectInvalid(makeBody({ plan }));
  });

  it("rejects blank required text and blank-but-present next_action", () => {
    for (const field of ["title", "objective", "status", "owner"]) {
      const blank = makePlan({ [field]: "   " });
      expectInvalid(makeBody({ plan: blank }));
      const empty = makePlan({ [field]: "" });
      expectInvalid(makeBody({ plan: empty }));
    }
    expectInvalid(makeBody({ plan: makePlan({ next_action: "" }) }));
    expectInvalid(makeBody({ plan: makePlan({ next_action: "   " }) }));
    expectInvalid(
      makeBody({ plan: makePlan({ waves: [makeWave("w1", { next_action: "" })] }) }),
    );
    expectInvalid(makeBody({ plan: makePlan({ next_action: "x".repeat(16385) }) }));
    expectInvalid(
      makeBody({ plan: makePlan({ waves: [makeWave("w1", { next_action: "x".repeat(16385) })] }) }),
    );
  });

  it("rejects non-text required fields", () => {
    expectInvalid(makeBody({ plan: makePlan({ title: 7 }) }));
    expectInvalid(makeBody({ plan: makePlan({ status: null }) }));
    expectInvalid(makeBody({ plan: makePlan({ owner: ["a"] }) }));
  });

  it("rejects wave shape violations", () => {
    const extra = makeWave("w1");
    extra.wait = { until: "ci" };
    expectInvalid(makeBody({ plan: makePlan({ waves: [extra] }) }));
    const missing = makeWave("w1");
    delete missing.prs;
    expectInvalid(makeBody({ plan: makePlan({ waves: [missing] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: "w1" }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [42] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1"), makeWave("w1")] }) })); // duplicate ids
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1 ")] }) })); // trailing space id
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave(" w1")] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("x".repeat(129))] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { title: "" })] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { title: "x".repeat(1025) })] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { status: "x".repeat(33) })] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { status: "" })] }) }));
  });

  it("rejects more than 64 waves", () => {
    const waves = Array.from({ length: 65 }, (_, index) => makeWave(`w${index}`));
    expectInvalid(makeBody({ plan: makePlan({ waves }) }));
  });
});

describe("decodeProjectPlan: dependencies", () => {
  it("rejects unknown dependencies", () => {
    expectInvalid(
      makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: ["w9"] })] }) }),
    );
  });

  it("rejects duplicate dependencies within one wave", () => {
    expectInvalid(
      makeBody({ plan: makePlan({ waves: [makeWave("w1"), makeWave("w2", { depends_on: ["w1", "w1"] })] }) }),
    );
  });

  it("rejects dependency cycles including self-dependency", () => {
    expectInvalid(
      makeBody({
        plan: makePlan({
          waves: [
            makeWave("w1", { depends_on: ["w2"] }),
            makeWave("w2", { depends_on: ["w1"] }),
          ],
        }),
      }),
    );
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: ["w1"] })] }) }));
  });

  it("rejects malformed dependency lists", () => {
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: null })] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: "w1" })] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: [42] })] }) }));
    expectInvalid(
      makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: ["w1\n"] })] }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: ["x".repeat(129)] })] }) }),
    );
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { depends_on: [""] })] }) }));
  });
});

describe("decodeProjectPlan: prs", () => {
  it("accepts positive safe-integer references verbatim", () => {
    const decoded = decode(makeBody()) as { plan: { waves: Array<{ prs: number[] }> } };
    expect(decoded.plan.waves[1].prs).toEqual([5594, 5595]);
  });

  it("rejects non-positive, fractional, unsafe and non-integer references", () => {
    for (const prs of [[0], [-1], [1.5], [9007199254740992], [true], ["5593"], [null], [[]]]) {
      expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { prs })] }) }));
    }
    expectInvalid(
      makeBody({
        plan: makePlan({ waves: [makeWave("w1", { prs: Array.from({ length: 33 }, () => 1) })] }),
      }),
    );
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { prs: null })] }) }));
    expectInvalid(makeBody({ plan: makePlan({ waves: [makeWave("w1", { prs: 5593 })] }) }));
  });

  it("handles integer values from the public transport's JSON parser", () => {
    const body = JSON.parse(JSON.stringify(makeBody()).replace('"prs":[5593]', '"prs":[5593.0]'));
    expect(decode(body)).toEqual(makeBody());
  });
});

describe("decodeProjectPlan: version history", () => {
  it("rejects a first revision whose content digest differs from the source", () => {
    const body = makeBody();
    body.plan.version_history.revisions[0].content_sha256 = CONTENT_B;
    expectInvalid(body);
  });

  it("rejects unavailable-history shapes outside the closed vocabulary", () => {
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "UNAVAILABLE", reason: "INVENTED" } }) }),
    );
    expectInvalid(makeBody({ plan: makePlan({ version_history: { state: "UNAVAILABLE" } }) }));
    expectInvalid(makeBody({ plan: makePlan({ version_history: { state: "PARTIAL", kind: "GIT_RECORD_REVISIONS", revisions: [] } }) }));
    expectInvalid(makeBody({ plan: makePlan({ version_history: null }) }));
  });

  it("rejects available-history shape violations", () => {
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "EXECUTION_HISTORY", revisions: [{ commit: COMMIT_A, committed_at: "2026-10-30T10:22:31+02:00", content_sha256: CONTENT_A }] } }) }),
    );
    expectInvalid(makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", revisions: [] } }) }));
    expectInvalid(makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [] } }) }));
    expectInvalid(
      makeBody({
        plan: makePlan({
          version_history: {
            state: "AVAILABLE",
            kind: "GIT_RECORD_REVISIONS",
            revisions: Array.from({ length: 9 }, (_, index) => ({
              commit: `${String(index % 10).repeat(2)}${COMMIT_A.slice(2)}`,
              committed_at: "2026-10-30T10:22:31+02:00",
              content_sha256: index === 0 ? CONTENT_A : CONTENT_B,
            })),
          },
        }),
      }),
    );
    const revision = { commit: COMMIT_A, committed_at: "2026-10-30T10:22:31+02:00", content_sha256: CONTENT_A };
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ ...revision, derived: true }] } }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ ...revision, commit: COMMIT_A.toUpperCase() }] } }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ ...revision, commit: "g".repeat(40) }] } }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ ...revision, content_sha256: "zz".repeat(32) }] } }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ ...revision, committed_at: 42 }] } }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ ...revision, committed_at: "2".repeat(41) }] } }) }),
    );
    expectInvalid(
      makeBody({ plan: makePlan({ version_history: { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: [{ commit: COMMIT_A, committed_at: "2026-10-30T10:22:31+02:00", content_sha256: CONTENT_A }, { ...revision, content_sha256: 42 }] } }) }),
    );
  });

  it("rejects duplicate commit ids in history", () => {
    const body = makeBody();
    body.plan.version_history.revisions[1].commit = COMMIT_A;
    expectInvalid(body);
  });

  it("rejects invalid committed_at dates", () => {
    for (const committed_at of [
      "2026-13-01T00:00:00Z",
      "2026-10-32T00:00:00Z",
      "2026-02-30T00:00:00Z",
      "2025-02-29T00:00:00Z",
      "2024-02-30T00:00:00Z",
      "0000-01-01T00:00:00Z",
      "2026-10-30T24:00:00Z",
      "2026-10-30T10:60:00Z",
      "2026-10-30T10:22:60Z",
      "266-10-30T10:22:31Z",
      "not-a-date",
      "",
    ]) {
      const body = makeBody();
      body.plan.version_history.revisions[0].committed_at = committed_at;
      expectInvalid(body);
    }
  });

  it("rejects committed_at without a timezone", () => {
    for (const committed_at of [
      "2026-10-30T10:22:31",
      "2026-10-30",
      "2026-10-30Z",
      "2026-10-30T10:22:31z",
      "2026-10-30T10:22:31+24:00",
      "2026-10-30T10:22:31+99:00",
      "2026-10-30T10:22:31+23:99",
      "2026-10-30T10:22:31+00:00x",
      "2026-10-30T10:22:31+00:00 ",
    ]) {
      const body = makeBody();
      body.plan.version_history.revisions[0].committed_at = committed_at;
      expectInvalid(body);
    }
  });

  it("accepts timezone-aware committed_at forms Python accepts", () => {
    for (const committed_at of [
      "2026-10-30T10:22:31+02:00",
      "2026-10-30T10:22:31Z",
      "2026-10-30 10:22:31+00:00",
      "2026-10-30T10:22+00:00",
      "2026-10-30T10+00:00",
      "2026-10-30T10:22:31.123456+00:00",
      "2026-10-30T10:22:31.+00:00",
      "20261030T102231+0000",
      "2026-10-30T102231.5+0000",
      "2026-10-30T10:22:31+23:59",
      "2026-10-30T10:22:31-00:99",
      "2026-10-30T10:22:31+00:00:30",
    ]) {
      const body = makeBody();
      body.plan.version_history.revisions = [
        { commit: COMMIT_A, committed_at, content_sha256: CONTENT_A },
      ];
      expect(decode(body)).toEqual(body);
    }
  });

  it("rejects history inferred from execution rather than supplied", () => {
    const body = makeBody();
    body.plan.version_history = { state: "AVAILABLE", kind: "EXECUTION_LOG", revisions: [] };
    expectInvalid(body);
  });
});

describe("decodeProjectPlan: unavailable bodies", () => {
  it("rejects reason_codes that are not exactly one closed code", () => {
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { reason_codes: [] }));
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { reason_codes: ["RECORD_NOT_FOUND", "SOURCE_CHANGED"] }));
    expectInvalid(makeUnavailableBody("INVENTED"));
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { reason_codes: [42] }));
    expectInvalid(makeUnavailableBody("record_not_found"));
    expectInvalid(makeBody({ reason_codes: ["RECORD_NOT_FOUND"] }));
  });

  it("rejects non-null source or plan on an unavailable body", () => {
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { source: makeSource() }));
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { plan: makePlan() }));
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { source: {} }));
    expectInvalid(makeUnavailableBody("RECORD_NOT_FOUND", { reason_codes: ["SOURCE_UNAVAILABLE", "RECORD_NOT_FOUND"] }));
  });

  it("rejects an unknown availability value", () => {
    expectInvalid(makeBody({ availability: "PARTIAL" }));
    expectInvalid(makeBody({ availability: null }));
    expectInvalid(makeBody({ availability: "available" }));
  });
});

describe("decodeProjectPlan: failure hygiene", () => {
  it("throws the value-free constant without echoing input", () => {
    const body = makeBody();
    body.secret_sentinel = "CLASSIFIED-123";
    try {
      decode(body);
      expect.unreachable("expected PROJECT_PLAN_INVALID");
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).toBe("PROJECT_PLAN_INVALID");
      expect((error as Error).message).not.toContain("CLASSIFIED");
    }
  });
});
