import { describe, expect, it } from "vitest";
import {
  decodeResultReferencesEnvelope,
  normalizeResultReferencesSelection,
  referenceSelection,
  RESULT_REFERENCES_SOCKET_ENVELOPE_BYTES,
} from "./result-references";
import { decodeResultEnvelope, normalizeResultSelection } from "./result";

const HEX = (ch: string) => ch.repeat(64);
const SEL = { workRef: "WS:ONE", rootJobId: "JOB-001" };

// The provided existing-owner reference index fixture, verbatim.
const INDEX = {
  schema: "mastermind.fabric_result_reference_index.v1",
  root_job_id: "JOB-001",
  snapshot_digest:
    "b025afa54ba7cb8ce68b287edbcd48023982a147252531b2c476b3de1937efeb",
  generation: {
    schema: "mastermind.runtime_read_observation.v1",
    state: "SAME",
    source_identity: "8f2ba172e5e975d5ab0f0965a4df9b53",
    before: 2,
    after: 2,
  },
  availability: "AVAILABLE",
  refs: [
    {
      root_job_id: "JOB-001",
      job_id: "JOB-002",
      attempt_id: "ATT-f762f805f4ab4567ab244aba0d106721",
      result_envelope_digest:
        "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a",
      orchestration_role: "plan" as const,
      validation: "UNVALIDATED" as const,
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-003",
      attempt_id: "ATT-0f7521645e5b462da6c3890da7575125",
      result_envelope_digest:
        "e3f365cc856fd9b205c16485cd148dd795baf794147f370530c384f3a66d3bbb",
      orchestration_role: "work" as const,
      validation: "UNVALIDATED" as const,
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-004",
      attempt_id: "ATT-c0ed7b3dea244d18a28e6677f04aefa0",
      result_envelope_digest:
        "867e1551abfcf92b1718b1fdd06ac37eed9f5d2783a8dc2332ec7d4936f9e1d1",
      orchestration_role: "review" as const,
      validation: "UNVALIDATED" as const,
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-005",
      attempt_id: "ATT-5d77c6ff01984f0bb0a1e83a40301cd1",
      result_envelope_digest:
        "6797ee07859494b54caad2832a8fefa600eb8b4e73dd568e0c4bc0d88cee9fde",
      orchestration_role: "repair" as const,
      validation: "UNVALIDATED" as const,
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-006",
      attempt_id: "ATT-a1e449e6e02e4eeb8271fcb11fdd836a",
      result_envelope_digest:
        "affb31703d0349accb4f7c7ecc932b7feb7ccdc13d375f24ffc37ce823d69de0",
      orchestration_role: "review" as const,
      validation: "UNVALIDATED" as const,
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-007",
      attempt_id: "ATT-f2dc8c0c163e47d1831128ee6f06a268",
      result_envelope_digest:
        "d7a82ffb86b6f8a3a2c3e194c60db869c15a3ed818e611368ccde6050725f48a",
      orchestration_role: "repair" as const,
      validation: "UNVALIDATED" as const,
    },
    {
      root_job_id: "JOB-001",
      job_id: "JOB-008",
      attempt_id: "ATT-ad068ac8f9744f6c9e9d38ee93006ce3",
      result_envelope_digest:
        "4db9efd82ed357ac8d3219a11df35642d0b0c58dcc597617c5e067a38bb2af1d",
      orchestration_role: "review" as const,
      validation: "UNVALIDATED" as const,
    },
  ],
  absent_job_ids: ["JOB-001"],
  omitted_job_ids: [],
  truncated: false,
};

const RUNTIME = {
  schema: "mastermind.runtime_read_observation.v1",
  state: "SAME",
  source_identity: "8f2ba172e5e975d5ab0f0965a4df9b53",
  before: 2,
  after: 2,
};

const CONTROL_ROOM = {
  instance_before: "control-room-instance",
  instance_after: "control-room-instance",
  publication_before: 11,
  publication_after: 11,
  document_digest: HEX("a"),
  source_validity_digest: HEX("b"),
  cache_currentness_digest: HEX("c"),
};

const base = (overrides: Record<string, unknown> = {}) => ({
  schema: "mastermind.workspace_result_references.v1",
  selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
  availability: "AVAILABLE",
  reason_codes: [],
  index: INDEX,
  source_observation: {
    schema: "mastermind.workspace_source_observation.v1",
    state: "SAME",
    selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
    control_room: CONTROL_ROOM,
    runtime: RUNTIME,
  },
  catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: "CURRENT" },
  ...overrides,
});

const decode = (overrides: Record<string, unknown> = {}) =>
  decodeResultReferencesEnvelope(base(overrides), SEL);

const withIndex = (indexOverrides: Record<string, unknown> = {}) =>
  decode({ index: { ...INDEX, ...indexOverrides } });

const withRef = (rowOverrides: Record<string, unknown>, at = 0) =>
  withIndex({
    refs: INDEX.refs.map((row, i) =>
      i === at ? { ...row, ...rowOverrides } : row,
    ),
  });

const omitKey = (body: Record<string, unknown>, key: string) => {
  const copy = { ...body };
  delete copy[key];
  return decodeResultReferencesEnvelope(copy, SEL);
};

const unavailable = (reason: string, state?: string) =>
  decodeResultReferencesEnvelope(
    base({
      availability: "UNAVAILABLE",
      reason_codes: [reason],
      index: null,
      source_observation: {
        schema: "mastermind.workspace_source_observation.v1",
        state: state ?? (reason === "SOURCE_CHANGED" ? "CONFLICT" : "UNKNOWN"),
        selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
        control_room: null,
        runtime: null,
      },
      catalogue: { generated_at: null, freshness: "UNKNOWN" },
    }),
    SEL,
  );

const framed = (value: unknown) =>
  new TextEncoder().encode(JSON.stringify({ ok: true, result: value }) + "\n")
    .byteLength;

const indexWithSlots = (count: number) => {
  const refs = [];
  for (let n = 2; n < 2 + count; n++) {
    refs.push({
      root_job_id: "JOB-001",
      job_id: "JOB-" + String(n).padStart(3, "0"),
      attempt_id: "ATT-" + "0".repeat(32),
      result_envelope_digest: HEX("1"),
      orchestration_role: "work" as const,
      validation: "UNVALIDATED" as const,
    });
  }
  return { ...INDEX, refs, absent_job_ids: [], omitted_job_ids: [] };
};

// Minimal valid exact-result body for the selector join cross-check. Its
// runtime receipt deliberately differs from the list receipt above, so a
// passing decode proves a list read never binds a later exact-result click.
const RESULT_RUNTIME = {
  schema: "mastermind.runtime_read_observation.v1",
  state: "SAME",
  source_identity: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  before: 7,
  after: 7,
};

const resultBody = (exact: {
  workRef: string;
  rootJobId: string;
  jobId: string;
  attemptId: string;
  resultEnvelopeDigest: string;
}) => ({
  schema: "mastermind.workspace_role_result.v1",
  selection: {
    work_ref: exact.workRef,
    root_job_id: exact.rootJobId,
    job_id: exact.jobId,
    attempt_id: exact.attemptId,
    result_envelope_digest: exact.resultEnvelopeDigest,
  },
  availability: "AVAILABLE",
  reason_codes: [],
  source_observation: {
    schema: "mastermind.workspace_result_observation.v1",
    state: "SAME",
    selection: {
      work_ref: exact.workRef,
      root_job_id: exact.rootJobId,
      job_id: exact.jobId,
      attempt_id: exact.attemptId,
      result_envelope_digest: exact.resultEnvelopeDigest,
    },
    control_room: {
      instance_before: "control-room-instance",
      instance_after: "control-room-instance",
      publication_before: 3,
      publication_after: 3,
      document_digest: HEX("d"),
      source_validity_digest: HEX("e"),
      cache_currentness_digest: HEX("f"),
    },
    runtime: RESULT_RUNTIME,
  },
  result: {
    schema: "mastermind.fabric_role_result_view.v1",
    selection: {
      root_job_id: exact.rootJobId,
      job_id: exact.jobId,
      attempt_id: exact.attemptId,
      result_envelope_digest: exact.resultEnvelopeDigest,
    },
    role: "work",
    execution_status: "COMPLETED",
    acceptance: "NOT_PROJECTED",
    role_result_digest: HEX("1"),
    generation: RESULT_RUNTIME,
    availability: "AVAILABLE",
    content_complete: true,
    review: null,
    counts: { findings: null, next_actions: 1 },
    content: {
      role_result: { outcome: "retained" },
      summary: "Retained work result.",
      next_actions: ["Inspect the retained result."],
    },
    omitted: [],
  },
});

describe("available list documents", () => {
  it("decodes the provided fixture index verbatim with a joined receipt", () => {
    const document = decode();
    expect(document).not.toBeNull();
    expect(document!.availability).toBe("AVAILABLE");
    expect(document!.reason_codes).toEqual([]);
    expect(document!.index!.root_job_id).toBe("JOB-001");
    expect(document!.index!.refs).toHaveLength(7);
    expect(document!.index!.absent_job_ids).toEqual(["JOB-001"]);
    expect(document!.index!.omitted_job_ids).toEqual([]);
    expect(document!.index!.truncated).toBe(false);
    expect(document!.catalogue.freshness).toBe("CURRENT");
    // Index generation equals the actual wrapper runtime receipt exactly.
    expect(document!.index!.generation).toEqual(RUNTIME);
    expect(document!.source_observation.runtime).toEqual(RUNTIME);
  });

  it("accepts a null snapshot digest as the owner emits it", () => {
    expect(withIndex({ snapshot_digest: null })).not.toBeNull();
  });

  it("accepts the legitimately emitted PARTIAL index availability", () => {
    const document = withIndex({ availability: "PARTIAL", truncated: true });
    expect(document).not.toBeNull();
    expect(document!.index!.availability).toBe("PARTIAL");
  });

  it("accepts an empty refs partition with absent jobs", () => {
    const document = withIndex({
      refs: [],
      absent_job_ids: ["JOB-001", "JOB-002"],
    });
    expect(document).not.toBeNull();
    expect(document!.index!.refs).toEqual([]);
  });

  it("accepts STALE orientation with a generated_at", () => {
    expect(
      decode({ catalogue: { generated_at: "2026-10-30T09:00:00Z", freshness: "STALE" } }),
    ).not.toBeNull();
  });

  it("accepts UNKNOWN freshness only without a generated_at", () => {
    expect(
      decode({ catalogue: { generated_at: null, freshness: "UNKNOWN" } }),
    ).not.toBeNull();
  });
});

describe("closed-key and schema rejections", () => {
  it("refuses non-objects", () => {
    for (const raw of [null, 42, "x", [], true]) {
      expect(decodeResultReferencesEnvelope(raw, SEL)).toBeNull();
    }
  });

  it("refuses any missing top-level key", () => {
    for (const key of [
      "schema",
      "selection",
      "availability",
      "reason_codes",
      "index",
      "source_observation",
      "catalogue",
    ]) {
      expect(omitKey(base(), key)).toBeNull();
    }
  });

  it("refuses extra keys, including any mission-currentness field", () => {
    expect(decode({ ...base(), mission_current: "CURRENT" })).toBeNull();
    expect(decode({ ...base(), extra: 1 })).toBeNull();
  });

  it("refuses a wrong schema", () => {
    expect(decode({ schema: "mastermind.workspace_result_references.v2" })).toBeNull();
    expect(decode({ schema: "mastermind.workspace_role_result.v1" })).toBeNull();
  });

  it("refuses wrapper selection mismatches and extra keys", () => {
    expect(
      decodeResultReferencesEnvelope(base(), { workRef: "WS:TWO", rootJobId: "JOB-001" }),
    ).toBeNull();
    expect(
      decodeResultReferencesEnvelope(base(), { workRef: "WS:ONE", rootJobId: "JOB-002" }),
    ).toBeNull();
    expect(
      decode({
        selection: { work_ref: "WS:ONE", root_job_id: "JOB-001", job_id: "JOB-002" },
      }),
    ).toBeNull();
    expect(
      decode({ selection: { work_ref: "WS:ONE" } }),
    ).toBeNull();
  });

  it("refuses invalid availability enums", () => {
    expect(decode({ availability: "PARTIAL" })).toBeNull();
    expect(decode({ availability: "AVAILABLE " })).toBeNull();
    expect(decode({ availability: 1 })).toBeNull();
  });
});

describe("reason-code consistency", () => {
  it("refuses reasons on an available document", () => {
    expect(decode({ reason_codes: ["SOURCE_UNAVAILABLE"] })).toBeNull();
    expect(decode({ reason_codes: ["SOURCE_UNAVAILABLE", "SOURCE_CHANGED"] })).toBeNull();
  });

  it("refuses unavailable documents without exactly one typed reason", () => {
    expect(
      decodeResultReferencesEnvelope(
        base({ availability: "UNAVAILABLE", reason_codes: [] }),
        SEL,
      ),
    ).toBeNull();
    expect(
      decodeResultReferencesEnvelope(
        base({
          availability: "UNAVAILABLE",
          reason_codes: ["SOURCE_UNAVAILABLE", "SOURCE_CHANGED"],
        }),
        SEL,
      ),
    ).toBeNull();
  });

  it("refuses unknown reason codes", () => {
    expect(
      decodeResultReferencesEnvelope(
        base({ availability: "UNAVAILABLE", reason_codes: ["SOMETHING_ELSE"] }),
        SEL,
      ),
    ).toBeNull();
    expect(
      decodeResultReferencesEnvelope(
        base({ availability: "UNAVAILABLE", reason_codes: [42] }),
        SEL,
      ),
    ).toBeNull();
  });
});

describe("typed unavailable shapes", () => {
  it("decodes SOURCE_CHANGED as CONFLICT without any receipt", () => {
    const document = unavailable("SOURCE_CHANGED");
    expect(document).not.toBeNull();
    expect(document!.availability).toBe("UNAVAILABLE");
    expect(document!.reason_codes).toEqual(["SOURCE_CHANGED"]);
    expect(document!.source_observation.state).toBe("CONFLICT");
    expect(document!.source_observation.control_room).toBeNull();
    expect(document!.source_observation.runtime).toBeNull();
    expect(document!.index).toBeNull();
    expect(document!.catalogue).toEqual({ generated_at: null, freshness: "UNKNOWN" });
  });

  it("decodes each other reason as UNKNOWN", () => {
    for (const reason of [
      "SOURCE_UNAVAILABLE",
      "OVER_BUDGET",
      "REFERENCE_INDEX_UNAVAILABLE",
    ]) {
      const document = unavailable(reason);
      expect(document).not.toBeNull();
      expect(document!.source_observation.state).toBe("UNKNOWN");
    }
  });

  it("pins the observation state to the reason", () => {
    expect(unavailable("SOURCE_CHANGED", "UNKNOWN")).toBeNull();
    expect(unavailable("SOURCE_UNAVAILABLE", "CONFLICT")).toBeNull();
    expect(unavailable("SOURCE_UNAVAILABLE", "SAME")).toBeNull();
  });

  it("refuses receipts, an index or a live catalogue on unavailable reads", () => {
    const carrying = (extra: Record<string, unknown>) =>
      decodeResultReferencesEnvelope(
        base({
          availability: "UNAVAILABLE",
          reason_codes: ["SOURCE_UNAVAILABLE"],
          index: null,
          source_observation: {
            schema: "mastermind.workspace_source_observation.v1",
            state: "UNKNOWN",
            selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
            control_room: extra.control_room ?? null,
            runtime: extra.runtime ?? null,
          },
          catalogue: { generated_at: null, freshness: "UNKNOWN" },
        }),
        SEL,
      );
    expect(carrying({ control_room: CONTROL_ROOM })).toBeNull();
    expect(carrying({ runtime: RUNTIME })).toBeNull();
    expect(unavailable("SOURCE_UNAVAILABLE", "UNKNOWN")!.index).toBeNull();
    expect(
      decodeResultReferencesEnvelope(
        base({
          availability: "UNAVAILABLE",
          reason_codes: ["SOURCE_UNAVAILABLE"],
          index: INDEX,
          source_observation: {
            schema: "mastermind.workspace_source_observation.v1",
            state: "UNKNOWN",
            selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
            control_room: null,
            runtime: null,
          },
          catalogue: { generated_at: null, freshness: "UNKNOWN" },
        }),
        SEL,
      ),
    ).toBeNull();
    expect(
      decodeResultReferencesEnvelope(
        base({
          availability: "UNAVAILABLE",
          reason_codes: ["SOURCE_UNAVAILABLE"],
          index: null,
          source_observation: {
            schema: "mastermind.workspace_source_observation.v1",
            state: "UNKNOWN",
            selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
            control_room: null,
            runtime: null,
          },
          catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: "UNKNOWN" },
        }),
        SEL,
      ),
    ).toBeNull();
  });
});

describe("index law rejections", () => {
  it("refuses a wrong index schema or key shape", () => {
    expect(withIndex({ schema: "mastermind.fabric_result_reference_index.v2" })).toBeNull();
    expect(withIndex({ extra: true })).toBeNull();
    expect(withIndex({ truncated: undefined })).toBeNull();
  });

  it("refuses a foreign or unparseable root", () => {
    expect(withIndex({ root_job_id: "JOB-002" })).toBeNull();
    expect(withIndex({ root_job_id: "not a root!" })).toBeNull();
    expect(withIndex({ root_job_id: 42 })).toBeNull();
  });

  it("refuses a malformed snapshot digest but accepts null", () => {
    expect(withIndex({ snapshot_digest: "NOT-HEX" })).toBeNull();
    expect(withIndex({ snapshot_digest: HEX("a").toUpperCase() })).toBeNull();
    expect(withIndex({ snapshot_digest: 42 })).toBeNull();
    expect(withIndex({ snapshot_digest: null })).not.toBeNull();
  });

  it("requires a finalized SAME generation", () => {
    expect(
      withIndex({
        generation: { ...INDEX.generation, state: "CONFLICT", before: 2, after: 3 },
      }),
    ).toBeNull();
    expect(
      withIndex({ generation: { ...INDEX.generation, state: "UNKNOWN", before: null, after: null, source_identity: null } }),
    ).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, before: 2, after: 3 } })).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, source_identity: null } })).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, source_identity: "bad identity" } })).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, before: -1, after: -1 } })).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, before: 2.5, after: 2.5 } })).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, before: null, after: null } })).toBeNull();
    expect(
      withIndex({
        generation: { ...INDEX.generation, schema: "mastermind.runtime_read_observation.v2" },
      }),
    ).toBeNull();
    expect(withIndex({ generation: { ...INDEX.generation, extra: 1 } })).toBeNull();
  });

  it("refuses an index availability outside the owner-emitted pair", () => {
    expect(withIndex({ availability: "UNAVAILABLE" })).toBeNull();
    expect(withIndex({ availability: "CURRENT" })).toBeNull();
  });

  it("refuses unsorted or duplicated partitions", () => {
    expect(withIndex({ refs: [...INDEX.refs].reverse() })).toBeNull();
    expect(withIndex({ refs: [INDEX.refs[0], INDEX.refs[0]] })).toBeNull();
    expect(withIndex({ absent_job_ids: ["JOB-009", "JOB-001"] })).toBeNull();
    expect(withIndex({ omitted_job_ids: ["JOB-002"] })).toBeNull();
    expect(withIndex({ absent_job_ids: ["JOB-009", 42] })).toBeNull();
  });

  it("refuses invalid ref rows", () => {
    expect(withRef({ root_job_id: "JOB-002" })).toBeNull();
    expect(withRef({ job_id: "JOB/002" })).toBeNull();
    expect(withRef({ job_id: "" })).toBeNull();
    expect(withRef({ attempt_id: "ATT short" })).toBeNull();
    expect(
      withRef({ result_envelope_digest: HEX("e").toUpperCase() }),
    ).toBeNull();
    expect(withRef({ result_envelope_digest: "abc" })).toBeNull();
    expect(withRef({ validation: "VALIDATED" })).toBeNull();
    expect(withRef({ orchestration_role: "manager" })).toBeNull();
    expect(withRef({ orchestration_role: "aggregation" })).not.toBeNull();
    expect(withRef({ extra: 1 })).toBeNull();
    expect(
      withRef({
        root_job_id: undefined as unknown as string,
        job_id: undefined as unknown as string,
        attempt_id: undefined as unknown as string,
        result_envelope_digest: undefined as unknown as string,
        orchestration_role: undefined as unknown as string,
        validation: undefined as unknown as string,
      }),
    ).toBeNull();
  });

  it("enforces at most 17 included Job slots", () => {
    expect(decode({ index: indexWithSlots(17) })).not.toBeNull();
    expect(decode({ index: indexWithSlots(18) })).toBeNull();
  });

  it("requires a boolean truncated flag", () => {
    expect(withIndex({ truncated: "false" })).toBeNull();
    expect(withIndex({ truncated: true })).not.toBeNull();
  });
});

describe("source observation and receipt rejections", () => {
  const observe = (overrides: Record<string, unknown>) =>
    decode({
      source_observation: {
        schema: "mastermind.workspace_source_observation.v1",
        state: "SAME",
        selection: { work_ref: "WS:ONE", root_job_id: "JOB-001" },
        control_room: CONTROL_ROOM,
        runtime: RUNTIME,
        ...overrides,
      },
    });

  it("refuses non-SAME observation on an available document", () => {
    expect(observe({ state: "UNKNOWN" })).toBeNull();
    expect(observe({ state: "CONFLICT" })).toBeNull();
  });

  it("refuses a missing or mismatched receipt half", () => {
    expect(observe({ control_room: null })).toBeNull();
    expect(observe({ runtime: null })).toBeNull();
    expect(
      observe({
        control_room: { ...CONTROL_ROOM, instance_after: "other-instance" },
      }),
    ).toBeNull();
    expect(
      observe({ control_room: { ...CONTROL_ROOM, publication_after: 12 } }),
    ).toBeNull();
    expect(
      observe({ control_room: { ...CONTROL_ROOM, document_digest: null } }),
    ).toBeNull();
    expect(
      observe({ control_room: { ...CONTROL_ROOM, instance_before: null } }),
    ).toBeNull();
    expect(
      observe({ control_room: { ...CONTROL_ROOM, publication_before: 0 } }),
    ).toBeNull();
    expect(observe({ control_room: { ...CONTROL_ROOM, extra: 1 } })).toBeNull();
  });

  it("refuses a runtime receipt that is not settled SAME", () => {
    expect(observe({ runtime: { ...RUNTIME, state: "CONFLICT" } })).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, before: 3, after: 3 } })).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, after: 3 } })).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, source_identity: "zz" } })).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, source_identity: null } })).toBeNull();
    expect(
      observe({ runtime: { ...RUNTIME, schema: "mastermind.runtime_read_observation.v2" } }),
    ).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, extra: 1 } })).toBeNull();
  });

  it("binds the index generation to the actual wrapper receipt", () => {
    expect(
      observe({ runtime: { ...RUNTIME, source_identity: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" } }),
    ).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, before: 3, after: 3 } })).toBeNull();
    expect(observe({ runtime: { ...RUNTIME, before: 2, after: 4 } })).toBeNull();
  });

  it("refuses an observation with the wrong schema or selection", () => {
    expect(observe({ schema: "mastermind.workspace_result_observation.v1" })).toBeNull();
    expect(
      observe({ selection: { work_ref: "WS:TWO", root_job_id: "JOB-001" } }),
    ).toBeNull();
    expect(
      observe({
        selection: { work_ref: "WS:ONE", root_job_id: "JOB-001", job_id: "JOB-002" },
      }),
    ).toBeNull();
    expect(observe({ extra: 1 })).toBeNull();
  });
});

describe("catalogue rejections", () => {
  it("refuses extra catalogue keys, including mission-currentness", () => {
    expect(
      decode({ catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: "CURRENT", mission_current: true } }),
    ).toBeNull();
  });

  it("refuses an untyped freshness or non-string timestamp", () => {
    expect(decode({ catalogue: { generated_at: null, freshness: "FRESH" } })).toBeNull();
    expect(decode({ catalogue: { generated_at: 42, freshness: "CURRENT" } })).toBeNull();
    expect(decode({ catalogue: { generated_at: "", freshness: "CURRENT" } })).toBeNull();
    expect(decode({ catalogue: { generated_at: null, freshness: "CURRENT" } })).toBeNull();
    expect(
      decode({ catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: "UNKNOWN" } }),
    ).toBeNull();
    expect(decode({ catalogue: { generated_at: "x", freshness: "CURRENT", extra: 1 } })).toBeNull();
  });
});

describe("byte budget", () => {
  it("refuses a whole body over the frozen framed budget", () => {
    const oversized = base({
      catalogue: { generated_at: "x".repeat(17000), freshness: "CURRENT" },
    });
    expect(framed(oversized)).toBeGreaterThan(RESULT_REFERENCES_SOCKET_ENVELOPE_BYTES);
    expect(decodeResultReferencesEnvelope(oversized, SEL)).toBeNull();
  });

  it("decodes the provided fixture well inside the budget", () => {
    expect(framed(base())).toBeLessThanOrEqual(RESULT_REFERENCES_SOCKET_ENVELOPE_BYTES);
    expect(decode()).not.toBeNull();
  });
});

describe("selection normalization and the exact-selector join", () => {
  it("normalizes only the closed two-field pair", () => {
    expect(normalizeResultReferencesSelection({ workRef: "WS:ONE", rootJobId: "JOB-001" })).toEqual(SEL);
    expect(normalizeResultReferencesSelection({ workRef: "WS:ONE", rootJobId: "JOB-001", extra: 1 })).toBeNull();
    expect(normalizeResultReferencesSelection({ workRef: "WS:ONE" })).toBeNull();
    expect(normalizeResultReferencesSelection({ workRef: "ws:one", rootJobId: "JOB-001" })).toBeNull();
    expect(normalizeResultReferencesSelection({ workRef: "WS:ONE", rootJobId: "JOB-x" })).toBeNull();
    expect(normalizeResultReferencesSelection(null)).toBeNull();
  });

  it("builds the exact selector from a returned row only", () => {
    const exact = normalizeResultSelection(
      referenceSelection(INDEX.refs[0], SEL),
    );
    expect(exact).not.toBeNull();
    expect(exact).toEqual({
      workRef: "WS:ONE",
      rootJobId: "JOB-001",
      jobId: "JOB-002",
      attemptId: "ATT-f762f805f4ab4567ab244aba0d106721",
      resultEnvelopeDigest:
        "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a",
    });
    const bogus = normalizeResultSelection(
      referenceSelection(
        { ...INDEX.refs[0], job_id: "JOB/002", attempt_id: "nope" },
        SEL,
      ),
    );
    expect(bogus).toBeNull();
  });

  it("a list read never binds a later exact-result click", () => {
    const exact = normalizeResultSelection(referenceSelection(INDEX.refs[1], SEL))!;
    // The list receipt is (8f2b…, 2); this result read observed (aaaa…, 7).
    expect(RESULT_RUNTIME.source_identity).not.toBe(RUNTIME.source_identity);
    const decoded = decodeResultEnvelope(resultBody(exact), exact);
    expect(decoded).not.toBeNull();
    expect(decoded!.result!.role).toBe("work");
    expect(decoded!.selection.job_id).toBe("JOB-003");
  });

  it("refuses an exact result whose selector disagrees with its body", () => {
    const exact = normalizeResultSelection(referenceSelection(INDEX.refs[0], SEL))!;
    const foreign = resultBody({
      ...exact,
      jobId: "JOB-003",
      attemptId: "ATT-0f7521645e5b462da6c3890da7575125",
      resultEnvelopeDigest:
        "e3f365cc856fd9b205c16485cd148dd795baf794147f370530c384f3a66d3bbb",
    });
    expect(decodeResultEnvelope(foreign, exact)).toBeNull();
  });
});
