import { describe, expect, it } from "vitest";
import {
  RESULT_HTTP_BODY_BYTES,
  RESULT_SOCKET_ENVELOPE_BYTES,
  decodeResultBytes,
  decodeResultEnvelope,
  decodeResultSocketEnvelope,
  normalizeResultSelection,
  unavailableResult,
} from "./result";

// DESIGN ONLY. The parent contract authorizes consumer work against synthetic
// design-only fixtures. Each fixture was frozen in input/design-only-fixtures
// at parent commit 9c85527d and is JSON-equivalent (the copied files add a newline) to the copy under
// src/fixtures/result-design-*.json. These fixtures do not represent a real
// Runtime or shared projector emission.
import availableAt16384 from "./fixtures/result-design-available-at-16384-socket-bytes.json";
import availableRejectUnicode from "./fixtures/result-design-available-reject-unicode.json";
import contentOverBudget from "./fixtures/result-design-content-over-budget-preserves-reject.json";
import unavailableOverBudget from "./fixtures/result-design-unavailable-over_budget.json";
import unavailableResponseOverBudget from "./fixtures/result-design-unavailable-response_over_budget.json";
import unavailableSourceChanged from "./fixtures/result-design-unavailable-source_changed.json";
import unavailableSourceUnavailable from "./fixtures/result-design-unavailable-source_unavailable.json";
import v3Current17 from "./fixtures/mission-v3-design-current-17-slots.json";
import v3Partial from "./fixtures/mission-v3-design-partial-truncated.json";
import v3Unavailable from "./fixtures/mission-v3-design-unavailable.json";

const SELECTION = {
  workRef: "WS:DESIGN",
  rootJobId: "JOB-001",
  jobId: "JOB-004",
  attemptId: "ATT-44444444444444444444444444444444",
  resultEnvelopeDigest:
    "390cfeea0f8476caa22dd263a243acf66216ea14d560ad6c908f668f59052a3a",
};

const clone = <T>(value: T): T => structuredClone(value);

describe("result selection normalization", () => {
  it("accepts the canonical five-field object", () => {
    expect(normalizeResultSelection(SELECTION)).toEqual(SELECTION);
  });
  it.each([
    ["missing field", { ...SELECTION, workRef: undefined }],
    ["bad work_ref", { ...SELECTION, workRef: "WS:bad.ws_lower" }],
    ["bad root_job_id", { ...SELECTION, rootJobId: "JOB-X" }],
    ["bad job_id", { ...SELECTION, jobId: "X-1" }],
    ["bad attempt_id", { ...SELECTION, attemptId: "ATT-short" }],
    [
      "uppercase digest",
      { ...SELECTION, resultEnvelopeDigest: "A".repeat(64) },
    ],
  ])("rejects %s", (_name, mutation) => {
    expect(normalizeResultSelection(mutation)).toBeNull();
  });
});

describe("frozen design-only fixture byte budgets", () => {
  it("at-limit fixture HTTP body is exactly 16362 and socket envelope is exactly 16384", () => {
    expect(
      new TextEncoder().encode(JSON.stringify(availableAt16384)).length,
    ).toBe(16362);
    const envelope =
      '{"ok":true,"result":' + JSON.stringify(availableAt16384) + "}\n";
    expect(new TextEncoder().encode(envelope).length).toBe(16384);
    expect(RESULT_HTTP_BODY_BYTES).toBe(16_384);
    expect(RESULT_SOCKET_ENVELOPE_BYTES).toBe(16_384);
  });
  it("never accepts a 16385-byte wrapper even if its body fits", () => {
    const padding = " ".repeat(2);
    const envelope =
      '{"ok":true,"result":' +
      JSON.stringify(availableAt16384) +
      "}" +
      padding +
      "\n";
    expect(new TextEncoder().encode(envelope).length).toBe(16386);
    const bytes = new TextEncoder().encode(envelope);
    expect(decodeResultSocketEnvelope(bytes, SELECTION)).toBeNull();
  });
});

describe("decodeResultEnvelope - happy path", () => {
  it("accepts the at-limit AVAILABLE fixture and binds the receipt", () => {
    const decoded = decodeResultEnvelope(clone(availableAt16384), SELECTION);
    expect(decoded?.availability).toBe("AVAILABLE");
    expect(decoded?.reason_codes).toEqual([]);
    expect(decoded?.source_observation.state).toBe("SAME");
    expect(decoded?.source_observation.runtime?.source_identity).toBe(
      "a".repeat(32),
    );
    expect(decoded?.result?.review?.verdict).toBe("reject");
    expect(decoded?.result?.counts.findings?.blocking).toBe(1);
  });
  it("accepts a rejecting review verdict exactly and preserves UNPROVEN", () => {
    const decoded = decodeResultEnvelope(clone(availableAt16384), SELECTION);
    expect(decoded?.result?.review?.latest_revision_currentness).toBe(
      "UNPROVEN",
    );
    expect(decoded?.result?.review?.verdict).toBe("reject");
  });
});

describe("decodeResultEnvelope - rejection", () => {
  it.each([
    [
      "different source identity",
      (d: any) => {
        d.source_observation.runtime.source_identity = "f".repeat(32);
      },
    ],
    [
      "different job id",
      (d: any) => {
        d.selection.job_id = "JOB-999";
      },
    ],
    [
      "mismatched attempt id",
      (d: any) => {
        d.selection.attempt_id = "ATT-" + "0".repeat(32);
      },
    ],
    [
      "root/job/attempt/digest mismatch",
      (d: any) => {
        d.selection.root_job_id = "JOB-099";
      },
    ],
    [
      "overbudget finding counts",
      (d: any) => {
        d.result.counts.findings.total = 99;
        d.result.counts.findings.blocking = 50;
      },
    ],
    [
      "non-review with findings",
      (d: any) => {
        d.result.role = "work";
        d.result.counts.findings = {
          total: 0,
          blocking: 0,
          warning: 0,
          info: 0,
        };
      },
    ],
    [
      "non-CURRENT state still AVAILABLE",
      (d: any) => {
        d.availability = "AVAILABLE";
        d.source_observation.state = "CONFLICT";
      },
    ],
    [
      "review approve still rejecting review verdict",
      (d: any) => {
        d.result.review.verdict = "approve";
        d.result.availability = "AVAILABLE";
        d.reason_codes = [];
      },
    ],
  ])("rejects %s", (_name, mutate) => {
    const raw = clone(availableAt16384) as any;
    mutate(raw);
    expect(decodeResultEnvelope(raw, SELECTION)).toBeNull();
  });
});

describe("decodeResultEnvelope - availability consistency", () => {
  it("accepts CONTENT_OVER_BUDGET with the preserved reject review", () => {
    const decoded = decodeResultEnvelope(clone(contentOverBudget), {
      ...SELECTION,
      resultEnvelopeDigest:
        "128e3a3eb18b714dab98b625865cf10468d9680d756ef99d027c2652a82a50e9",
    });
    expect(decoded?.availability).toBe("CONTENT_OVER_BUDGET");
    expect(decoded?.reason_codes).toEqual(["CONTENT_OVER_BUDGET"]);
    expect(decoded?.result?.content).toBeNull();
    expect(decoded?.result?.omitted).toEqual([
      "role_result",
      "summary",
      "next_actions",
    ]);
  });
  it("accepts UNAVAILABLE SOURCE_CHANGED with CONFLICT observation", () => {
    const decoded = decodeResultEnvelope(clone(unavailableSourceChanged), {
      ...SELECTION,
      resultEnvelopeDigest:
        "d2b2ded46fb64f965e5f7f83bb9fd6652b11fc80b6d9387d6bb2b1831f93643c",
    });
    expect(decoded?.availability).toBe("UNAVAILABLE");
    expect(decoded?.reason_codes).toEqual(["SOURCE_CHANGED"]);
    expect(decoded?.source_observation.state).toBe("CONFLICT");
    expect(decoded?.source_observation.control_room).toBeNull();
    expect(decoded?.source_observation.runtime).toBeNull();
  });
  it("accepts UNAVAILABLE SOURCE_UNAVAILABLE with UNKNOWN observation", () => {
    const decoded = decodeResultEnvelope(clone(unavailableSourceUnavailable), {
      ...SELECTION,
      resultEnvelopeDigest:
        "d2b2ded46fb64f965e5f7f83bb9fd6652b11fc80b6d9387d6bb2b1831f93643c",
    });
    expect(decoded?.availability).toBe("UNAVAILABLE");
    expect(decoded?.reason_codes).toEqual(["SOURCE_UNAVAILABLE"]);
    expect(decoded?.source_observation.state).toBe("UNKNOWN");
  });
  it("accepts UNAVAILABLE OVER_BUDGET and preserves no findings", () => {
    const decoded = decodeResultEnvelope(clone(unavailableOverBudget), {
      ...SELECTION,
      resultEnvelopeDigest:
        "d2b2ded46fb64f965e5f7f83bb9fd6652b11fc80b6d9387d6bb2b1831f93643c",
    });
    expect(decoded?.availability).toBe("UNAVAILABLE");
    expect(decoded?.reason_codes).toEqual(["OVER_BUDGET"]);
    expect(decoded?.result).toBeNull();
  });
  it("accepts UNAVAILABLE RESPONSE_OVER_BUDGET", () => {
    const decoded = decodeResultEnvelope(clone(unavailableResponseOverBudget), {
      ...SELECTION,
      resultEnvelopeDigest:
        "d2b2ded46fb64f965e5f7f83bb9fd6652b11fc80b6d9387d6bb2b1831f93643c",
    });
    expect(decoded?.availability).toBe("UNAVAILABLE");
    expect(decoded?.reason_codes).toEqual(["RESPONSE_OVER_BUDGET"]);
  });
});

describe("decodeResultBytes - byte budget enforcement", () => {
  it("accepts the at-limit fixture HTTP body when fed as raw bytes", () => {
    const body = JSON.stringify(availableAt16384);
    const bytes = new TextEncoder().encode(body);
    expect(bytes.length).toBe(16362);
    const decoded = decodeResultBytes(bytes, 16_384, SELECTION);
    expect(decoded?.availability).toBe("AVAILABLE");
  });
  it("rejects a 16385-byte body even when its first 16384 bytes match a valid fixture", () => {
    const body = JSON.stringify(availableAt16384) + " ".repeat(23);
    const bytes = new TextEncoder().encode(body);
    expect(bytes.length).toBe(16385);
    expect(decodeResultBytes(bytes, 16_384, SELECTION)).toBeNull();
  });
  it("rejects malformed JSON and UTF-8 garbage", () => {
    const bad1 = new TextEncoder().encode("{not json");
    expect(decodeResultBytes(bad1, 1024, SELECTION)).toBeNull();
    const bad2 = new Uint8Array([0xff, 0xfe, 0xfd, 0xfc]);
    expect(decodeResultBytes(bad2, 1024, SELECTION)).toBeNull();
  });
});

describe("decodeResultSocketEnvelope - canonical compact wrapper", () => {
  it("accepts the canonical envelope at exactly 16384 bytes", () => {
    const envelope =
      '{"ok":true,"result":' + JSON.stringify(availableAt16384) + "}\n";
    const bytes = new TextEncoder().encode(envelope);
    expect(bytes.length).toBe(16384);
    const decoded = decodeResultSocketEnvelope(bytes, SELECTION);
    expect(decoded?.ok).toBe(true);
  });
  it("rejects when the LF terminator is missing", () => {
    const envelope =
      '{"ok":true,"result":' + JSON.stringify(availableAt16384) + "}";
    const bytes = new TextEncoder().encode(envelope);
    expect(decodeResultSocketEnvelope(bytes, SELECTION)).toEqual({
      ok: false,
      reason: "INVALID_SHAPE",
    });
  });
  it("rejects when ok is not true", () => {
    const envelope =
      '{"ok":false,"result":' + JSON.stringify(availableAt16384) + "}\n";
    const bytes = new TextEncoder().encode(envelope);
    // false adds one byte to this exactly-at-limit envelope; budget refusal wins.
    expect(decodeResultSocketEnvelope(bytes, SELECTION)).toBeNull();
  });
});

describe("unavailableResult consumer surface", () => {
  it("preserves the typed reason code, never coercing into a generic exception", () => {
    const u = unavailableResult(SELECTION, "SOURCE_CHANGED");
    expect(u.kind).toBe("LOCAL_UNAVAILABLE");
    expect(u.reason).toBe("SOURCE_CHANGED");
    expect(u.selection).toEqual(SELECTION);
  });
});

describe("decodeMissionv3 fixtures and decoder", () => {
  it("accepts the at-cap 17-slot AVAILABLE design fixture", () => {
    const decoded = decodeMissionv3Envelope();
    expect(decoded?.result_refs.refs.length).toBe(11);
    expect(decoded?.result_refs.absent_job_ids.length).toBe(6);
    expect(decoded?.result_refs.omitted_job_ids.length).toBe(0);
    expect(decoded?.result_refs.availability).toBe("AVAILABLE");
    expect(decoded?.result_refs.truncated).toBe(false);
  });
  it("accepts the PARTIAL/truncated fixture with refs, absent, and omitted", () => {
    const decoded = decodeMissionv3Partial();
    expect(decoded?.result_refs.availability).toBe("PARTIAL");
    expect(decoded?.result_refs.refs.length).toBe(3);
    expect(decoded?.result_refs.absent_job_ids).toEqual(["JOB-005", "JOB-006"]);
    expect(decoded?.result_refs.omitted_job_ids).toEqual(["JOB-007"]);
    expect(decoded?.result_refs.truncated).toBe(true);
  });
  it("accepts the UNAVAILABLE design fixture with empty refs", () => {
    const decoded = decodeMissionv3Unavailable();
    expect(decoded?.result_refs.availability).toBe("UNAVAILABLE");
    expect(decoded?.result_refs.refs).toEqual([]);
    expect(decoded?.result_refs.absent_job_ids).toEqual([]);
    expect(decoded?.result_refs.omitted_job_ids).toEqual([]);
  });
  it.each([
    [
      "extra index key",
      (d: any) => {
        d.result_refs.injected = true;
      },
    ],
    [
      "out-of-order absent ids",
      (d: any) => {
        const a = d.result_refs.absent_job_ids.slice();
        a.reverse();
        d.result_refs.absent_job_ids = a;
      },
    ],
    [
      "duplicate ref job_id",
      (d: any) => {
        d.result_refs.refs.push({ ...d.result_refs.refs[0] });
      },
    ],
    [
      "17 refs + 1 absent = 18 slots",
      (d: any) => {
        const extra = Array.from({ length: 7 }, (_, i) => ({
          ...d.result_refs.refs[i],
          job_id: "JOB-9" + String(i).padStart(2, "0"),
        }));
        d.result_refs.refs = d.result_refs.refs.concat(extra);
      },
    ],
    [
      "non-CURRENT Mission with AVAILABLE index",
      (d: any) => {
        d.source.owner_observation.state = "CONFLICT";
      },
    ],
    [
      "overlapping absent and omitted",
      (d: any) => {
        d.result_refs.absent_job_ids = ["JOB-999"];
        d.result_refs.omitted_job_ids = ["JOB-999"];
      },
    ],
    [
      "same digest with different source identity",
      (d: any) => {
        // The Mission v3 contract requires index generation.identity
        // equals the Fabricv2 receipt identity. A non-matching source
        // identity here is a strict refusal.
        d.result_refs.generation.source_identity = "f".repeat(32);
        d.source.owner_observation.runtime.source_identity = "a".repeat(32);
      },
    ],
  ])("rejects %s", (_name, mutate) => {
    const raw = clone(v3Current17) as any;
    mutate(raw);
    expect(decodeMissionv3Re(raw)).toBeNull();
  });
});

import { decodeMission, decodeMissionv3 } from "./mission";
import { realMissionFixture } from "./test-fixtures";

function decodeMissionv3Envelope() {
  return decodeMissionv3(clone(v3Current17), {
    workRef: "WS:B5",
    rootJobId: (v3Current17 as any).mission.root_job_id,
  });
}
function decodeMissionv3Partial() {
  return decodeMissionv3(clone(v3Partial), {
    workRef: "WS:ALPHA",
    rootJobId: (v3Partial as any).mission.root_job_id,
  });
}
function decodeMissionv3Unavailable() {
  return decodeMissionv3(clone(v3Unavailable), {
    workRef: "WS:B5",
    rootJobId: "JOB-100",
  });
}
function decodeMissionv3Re(raw: unknown) {
  return decodeMissionv3(raw, {
    workRef: "WS:B5",
    rootJobId: (raw as any).mission.root_job_id,
  });
}

// Re-export fixtures for tooling that imports result.test
export {
  availableAt16384,
  availableRejectUnicode,
  contentOverBudget,
  unavailableOverBudget,
  unavailableResponseOverBudget,
  unavailableSourceChanged,
  unavailableSourceUnavailable,
};

// Discriminating residual closure checks against the actual public contract.
describe("result closure boundaries", () => {
  it("allows a fresh detail observation whose two bound identities agree", () => {
    const value = clone(availableAt16384);
    value.source_observation.runtime.source_identity = "f".repeat(32);
    value.result.generation.source_identity = "f".repeat(32);
    expect(decodeResultEnvelope(value, SELECTION)).not.toBeNull();
  });
  it("refuses a complete DTO whose canonical socket wrapper exceeds the cap", () => {
    const value = clone(availableAt16384);
    value.result.content.summary += "x";
    expect(decodeResultEnvelope(value, SELECTION)).toBeNull();
  });
  it("requires SOURCE_CHANGED to carry a CONFLICT observation", () => {
    const value = clone(unavailableSourceChanged);
    value.source_observation.state = "UNKNOWN";
    const selection = {
      ...SELECTION,
      resultEnvelopeDigest: value.selection.result_envelope_digest,
    };
    expect(decodeResultEnvelope(value, selection)).toBeNull();
  });
  it("does not coerce array selectors into strings", () => {
    expect(
      normalizeResultSelection({ ...SELECTION, jobId: [SELECTION.jobId] }),
    ).toBeNull();
  });
  it("requires the fixed ATT hexadecimal grammar in navigation", () => {
    const value = clone(v3Current17);
    value.result_refs.refs[0].attempt_id = "ATT-not-a-canonical-attempt";
    expect(decodeMissionv3Re(value)).toBeNull();
  });
  it("allows an unavailable index diagnostic with null unobserved samples", () => {
    const value = clone(v3Unavailable) as any;
    value.result_refs.generation.before = null;
    value.result_refs.generation.after = null;
    expect(
      decodeMissionv3(value, { workRef: "WS:B5", rootJobId: "JOB-100" }),
    ).not.toBeNull();
  });
});

it("refuses selectable refs when only the main Mission read state becomes PARTIAL", () => {
  const value = {
    ...clone(v3Current17),
    read_state: {
      ...v3Current17.read_state,
      state: "PARTIAL",
      reason_codes: ["SOURCE_OR_VALIDITY_INCOMPLETE"],
    },
  };
  expect(decodeMissionv3Re(value)).toBeNull();
});

describe("review successor: canonical next actions and complete receipt equality", () => {
  const expected = {
    workRef: availableRejectUnicode.selection.work_ref,
    rootJobId: availableRejectUnicode.selection.root_job_id,
    jobId: availableRejectUnicode.selection.job_id,
    attemptId: availableRejectUnicode.selection.attempt_id,
    resultEnvelopeDigest:
      availableRejectUnicode.selection.result_envelope_digest,
  };
  it.each(["UNKNOWN", "CONFLICT"])(
    "refuses %s Runtime state inside outer SAME",
    (state) => {
      const value = clone(availableRejectUnicode);
      value.source_observation.runtime.state = state;
      expect(decodeResultEnvelope(value, expected)).toBeNull();
    },
  );
  it.each([
    "",
    "Read https://example.com/review",
    "x".repeat(1025),
    "x".repeat(8192),
    "🔎" + "x".repeat(8191),
    "\u0001 retained control text",
  ])("preserves canonical inert action %#", (action) => {
    const value = clone(availableRejectUnicode);
    value.result.content.next_actions = [action];
    value.result.counts.next_actions = 1;
    expect(
      decodeResultEnvelope(value, expected)?.result?.content?.next_actions,
    ).toEqual([action]);
  });
  it.each(["x".repeat(8193), "\u0000", "\ud800", "\udc00"])(
    "refuses owner-invalid action %#",
    (action) => {
      const value = clone(availableRejectUnicode);
      value.result.content.next_actions = [action];
      value.result.counts.next_actions = 1;
      expect(decodeResultEnvelope(value, expected)).toBeNull();
    },
  );
  it.each([["same", "same"], Array.from({ length: 17 }, (_, i) => String(i))])(
    "refuses owner-invalid action list %#",
    (...actions) => {
      const value = clone(availableRejectUnicode);
      value.result.content.next_actions = actions;
      value.result.counts.next_actions = actions.length;
      expect(decodeResultEnvelope(value, expected)).toBeNull();
    },
  );
});

// Unchanged accepted actual SQLite producer output (M8fdf4296, manifestd020).
// Test namespace custody is not installed service custody.
import actualOwnerMission from "./fixtures/mission-v3-owner-current-operator-harness.json";
describe("actual owner global unjoined scope", () => {
  it("accepts the unchanged CURRENT owner document with root globally unjoined", () => {
    expect(actualOwnerMission.children.unjoined_job_ids).toContain("JOB-001");
    expect(
      decodeMissionv3(actualOwnerMission, {
        workRef: "WS:ONE",
        rootJobId: "JOB-001",
      }),
    ).not.toBeNull();
  });
  it("still refuses a joined child duplicated into global unjoined IDs", () => {
    const value: any = realMissionFixture();
    const selection = {
      workRef: value.program.work_ref,
      rootJobId: value.mission.root_job_id,
    };
    expect(decodeMission(value, selection)).not.toBeNull();
    const child = value.children.items[0];
    expect(child).toBeTruthy();
    value.children.unjoined_job_ids = [child.job_id];
    value.children.unjoined_job_count = 1;
    value.children.coverage = "INCOMPLETE";
    value.children.state = "PARTIAL";
    expect(decodeMission(value, selection)).toBeNull();
  });
});

describe("Mission opaque receipt and detail identity remain separate contracts", () => {
  it("admits equal opaque Mission receipts but never uses them for detail identity", () => {
    const value = clone(actualOwnerMission);
    value.source.owner_observation.runtime.source_identity =
      "rt_owner_1234567890";
    value.result_refs.generation.source_identity = "rt_owner_1234567890";
    expect(
      decodeMissionv3(value, { workRef: "WS:ONE", rootJobId: "JOB-001" }),
    ).not.toBeNull();
    value.result_refs.generation.source_identity = "rt_owner_other_1234";
    expect(
      decodeMissionv3(value, { workRef: "WS:ONE", rootJobId: "JOB-001" }),
    ).toBeNull();
    const detail = clone(availableRejectUnicode);
    detail.result.generation.source_identity = "rt_owner_1234567890";
    detail.source_observation.runtime.source_identity = "rt_owner_1234567890";
    expect(
      decodeResultEnvelope(detail, {
        workRef: detail.selection.work_ref,
        rootJobId: detail.selection.root_job_id,
        jobId: detail.selection.job_id,
        attemptId: detail.selection.attempt_id,
        resultEnvelopeDigest: detail.selection.result_envelope_digest,
      }),
    ).toBeNull();
  });
});
