import { describe, expect, it } from "vitest";
import {
  PROJECT_ASSOCIATION_BODY_BYTES,
  PROJECT_ASSOCIATION_SCHEMA,
  decodeProjectAssociation,
  normalizeProjectAssociationSelection,
  type ProjectAssociationSelection,
  type ProjectAssociationState,
} from "./project-association";

const SELECTION: ProjectAssociationSelection = { workRef: "WS:ALPHA01", rootJobId: "JOB-7" };

function hex64(seed: string): string {
  return (seed + "0".repeat(64)).slice(0, 64);
}

function projectSource(): Record<string, unknown> {
  return {
    repository: "macro",
    commit: "0123456789abcdef0123456789abcdef01234567",
    path: "agentos/workstreams/WS-ALPHA01.md",
    content_sha256: hex64("c1"),
    request_sha256: hex64("d2"),
  };
}

function runtimeCreation(): Record<string, unknown> {
  return {
    intent_id: "runtime-intent-1",
    fingerprint: hex64("f1"),
    creation_event_sha256: hex64("e1"),
  };
}

function materialization(): Record<string, unknown> {
  return {
    receipt_sha256: hex64("a3"),
    recorded_at: "2026-11-01T12:00:00.000Z",
    operation_kind: "start_session",
    epoch_sha256: hex64("b4"),
    process_generation_sha256: hex64("c5"),
    provider_session_sha256: hex64("d6"),
    generation_number: 1,
  };
}

function documentBody(
  state: ProjectAssociationState,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema: PROJECT_ASSOCIATION_SCHEMA,
    selection: { work_ref: "WS:ALPHA01", root_job_id: "JOB-7" },
    availability: "AVAILABLE",
    state,
    reason: null,
    observational_only: true,
    can_send: false,
    continuation_target: null,
    project_source: projectSource(),
    runtime_creation: runtimeCreation(),
    materialization: materialization(),
    ...extra,
  };
}

function ownerBody(state: ProjectAssociationState): Record<string, unknown> {
  switch (state) {
    case "RECORDED_MATERIALIZATION":
      return documentBody(state, { reason: "BROKER_RESTARTED" });
    case "PREPARING":
      return documentBody(state, { reason: "NOT_MATERIALIZED", materialization: null });
    case "UNAVAILABLE":
      return documentBody(state, {
        availability: "UNAVAILABLE",
        reason: "SOURCE_CHANGED",
        project_source: null,
        runtime_creation: null,
        materialization: null,
      });
    default:
      return documentBody(state);
  }
}

function expectNull(raw: unknown, expected: unknown = SELECTION): void {
  expect(decodeProjectAssociation(raw, expected as ProjectAssociationSelection)).toBeNull();
}

describe("decodeProjectAssociation owner states", () => {
  it("decodes a MATERIALIZED_OBSERVATION owner document with every source object", () => {
    const decoded = decodeProjectAssociation(ownerBody("MATERIALIZED_OBSERVATION"), SELECTION);
    expect(decoded).not.toBeNull();
    expect(decoded?.state).toBe("MATERIALIZED_OBSERVATION");
    expect(decoded?.availability).toBe("AVAILABLE");
    expect(decoded?.reason).toBeNull();
    expect(decoded?.observational_only).toBe(true);
    expect(decoded?.can_send).toBe(false);
    expect(decoded?.continuation_target).toBeNull();
    expect(decoded?.selection).toEqual({ work_ref: "WS:ALPHA01", root_job_id: "JOB-7" });
    expect(decoded?.project_source?.path).toBe("agentos/workstreams/WS-ALPHA01.md");
    expect(decoded?.runtime_creation?.intent_id).toBe("runtime-intent-1");
    expect(decoded?.materialization?.receipt_sha256).toBe(hex64("a3"));
    expect(decoded?.materialization?.recorded_at).toBe("2026-11-01T12:00:00.000Z");
    expect(decoded?.materialization?.generation_number).toBe(1);
  });

  it("decodes a RECORDED_MATERIALIZATION owner document with every source object", () => {
    const decoded = decodeProjectAssociation(ownerBody("RECORDED_MATERIALIZATION"), SELECTION);
    expect(decoded).not.toBeNull();
    expect(decoded?.state).toBe("RECORDED_MATERIALIZATION");
    expect(decoded?.availability).toBe("AVAILABLE");
    expect(decoded?.reason).toBe("BROKER_RESTARTED");
    expect(decoded?.project_source).not.toBeNull();
    expect(decoded?.runtime_creation).not.toBeNull();
    expect(decoded?.materialization).not.toBeNull();
  });

  it("decodes a PREPARING owner document with source and runtime root only", () => {
    const decoded = decodeProjectAssociation(ownerBody("PREPARING"), SELECTION);
    expect(decoded).not.toBeNull();
    expect(decoded?.state).toBe("PREPARING");
    expect(decoded?.availability).toBe("AVAILABLE");
    expect(decoded?.reason).toBe("NOT_MATERIALIZED");
    expect(decoded?.project_source).not.toBeNull();
    expect(decoded?.runtime_creation).not.toBeNull();
    expect(decoded?.materialization).toBeNull();
  });

  it("decodes an UNAVAILABLE owner document with the exact owner reason", () => {
    const decoded = decodeProjectAssociation(ownerBody("UNAVAILABLE"), SELECTION);
    expect(decoded).not.toBeNull();
    expect(decoded?.state).toBe("UNAVAILABLE");
    expect(decoded?.availability).toBe("UNAVAILABLE");
    expect(decoded?.reason).toBe("SOURCE_CHANGED");
    expect(decoded?.project_source).toBeNull();
    expect(decoded?.runtime_creation).toBeNull();
    expect(decoded?.materialization).toBeNull();
  });

  it("returns a copied and frozen document without mutating the owner input", () => {
    const raw = ownerBody("MATERIALIZED_OBSERVATION");
    const before = JSON.stringify(raw);
    const decoded = decodeProjectAssociation(raw, SELECTION);
    expect(decoded).not.toBeNull();
    expect(JSON.stringify(raw)).toBe(before);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded?.selection)).toBe(true);
    expect(Object.isFrozen(decoded?.project_source)).toBe(true);
    expect(Object.isFrozen(decoded?.runtime_creation)).toBe(true);
    expect(Object.isFrozen(decoded?.materialization)).toBe(true);
    expect(decoded?.selection).not.toBe(raw.selection);
  });

  it("accepts owner JSON text within the body budget and parsed objects alike", () => {
    const text = JSON.stringify(ownerBody("MATERIALIZED_OBSERVATION"));
    expect(text.length).toBeLessThan(PROJECT_ASSOCIATION_BODY_BYTES);
    expect(decodeProjectAssociation(text, SELECTION)).not.toBeNull();
    expect(decodeProjectAssociation(ownerBody("MATERIALIZED_OBSERVATION"), SELECTION)).not.toBeNull();
  });
});

describe("decodeProjectAssociation closed fields", () => {
  it("rejects extraneous owner fields, credentials and raw provider identities", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { credentials: { token: "t" } }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { account: "acct-1" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { authority: "send" }));
    const rawProvider = ownerBody("MATERIALIZED_OBSERVATION");
    (rawProvider.materialization as Record<string, unknown>).provider_session_id = "prov-123";
    expectNull(rawProvider);
    const rawEpoch = ownerBody("MATERIALIZED_OBSERVATION");
    (rawEpoch.materialization as Record<string, unknown>).epoch_id = "epoch-9";
    expectNull(rawEpoch);
    const privateSource = ownerBody("MATERIALIZED_OBSERVATION");
    (privateSource.project_source as Record<string, unknown>).repository_private_path = "/srv/x";
    expectNull(privateSource);
    const extraSession = ownerBody("MATERIALIZED_OBSERVATION");
    (extraSession.selection as Record<string, unknown>).session_id = "s1";
    expectNull(extraSession);
  });

  it("rejects symbol keys and accessor properties", () => {
    const symbolKeyed = ownerBody("MATERIALIZED_OBSERVATION");
    (symbolKeyed as Record<symbol, unknown>)[Symbol("extra")] = 1;
    expectNull(symbolKeyed);
    let getterCalls = 0;
    const accessor = ownerBody("MATERIALIZED_OBSERVATION");
    Object.defineProperty(accessor, "can_send", {
      enumerable: true,
      configurable: true,
      get: () => { getterCalls++; return false; },
    });
    expectNull(accessor);
    expect(getterCalls).toBe(0);
  });

  it("rejects arrays, classed objects, scalars and malformed JSON bodies", () => {
    expectNull(null);
    expectNull(42);
    expectNull(true);
    expectNull([]);
    expectNull(new Date());
    expectNull("not json");
    expectNull("42");
    expectNull(documentBody("MATERIALIZED_OBSERVATION").selection as unknown);
    expectNull([ownerBody("MATERIALIZED_OBSERVATION")]);
    expectNull("{");
  });
});

describe("decodeProjectAssociation state correspondence", () => {
  it("rejects reason and payload combinations outside the four owner states", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { reason: "BROKER_RESTARTED" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { reason: "MATERIALIZATION_CONFLICT" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { reason: "NOT_MATERIALIZED" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { materialization: null }));
    expectNull(documentBody("RECORDED_MATERIALIZATION", { reason: null }));
    expectNull(documentBody("RECORDED_MATERIALIZATION", { reason: "SOURCE_CHANGED" }));
    expectNull(documentBody("RECORDED_MATERIALIZATION", { runtime_creation: null }));
    expectNull(documentBody("PREPARING", { reason: "BROKER_RESTARTED" }));
    expectNull(documentBody("PREPARING", { project_source: null }));
    expectNull(documentBody("PREPARING", { runtime_creation: null }));
    expectNull(documentBody("PREPARING", { materialization: materialization() }));
    expectNull(documentBody("UNAVAILABLE", {
      availability: "UNAVAILABLE",
      reason: "SOURCE_CHANGED",
      project_source: projectSource(),
    }));
    expectNull(documentBody("UNAVAILABLE", { availability: "AVAILABLE", reason: "SOURCE_CHANGED" }));
    expectNull(documentBody("UNAVAILABLE", { availability: "UNAVAILABLE", reason: null }));
    expectNull(documentBody("UNAVAILABLE", { availability: "UNAVAILABLE", reason: "NOT_MATERIALIZED" }));
    expectNull(documentBody("UNAVAILABLE", { availability: "UNAVAILABLE", reason: "BROKER_RESTARTED" }));
  });

  it("rejects unknown enum values and payload mismatches", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { availability: "PENDING" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { state: "WORKING" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { reason: "SESSION_DENIED" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { can_send: true }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { observational_only: false }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { continuation_target: { job_id: "JOB-7" } }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", { continuation_target: "JOB-7" }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      schema: "mastermind.workspace_project_session_association.v2",
    }));
  });

  it("rejects malformed materialization payloads", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      materialization: { ...materialization(), generation_number: 3 },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      materialization: { ...materialization(), generation_number: "1" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      materialization: { ...materialization(), operation_kind: "restart_session" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      materialization: { ...materialization(), receipt_sha256: 7 },
    }));
  });
});

describe("decodeProjectAssociation selection and source binding", () => {
  it("rejects bodies for a different work, root or expected pair", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      selection: { work_ref: "WS:ALPHA01", root_job_id: "JOB-8" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      selection: { work_ref: "WS:BETA02", root_job_id: "JOB-7" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      selection: { work_ref: "ws:ALPHA01", root_job_id: "JOB-7" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      selection: { workRef: "WS:ALPHA01", rootJobId: "JOB-7" },
    }));
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), { workRef: "WS:ALPHA01", rootJobId: "JOB-9" });
  });

  it("rejects malformed expected selections", () => {
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), null);
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), { workRef: "ALPHA01", rootJobId: "JOB-7" });
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), { workRef: "WS:ALPHA01" });
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), { workRef: "WS:ALPHA01", rootJobId: "" });
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), {
      workRef: "WS:ALPHA01",
      rootJobId: "JOB-7",
      extra: 1,
    });
    expectNull(ownerBody("MATERIALIZED_OBSERVATION"), [SELECTION]);
  });

  it("rejects a project source path that does not match the selected work key", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), path: "agentos/workstreams/WS-BETA02.md" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), path: "agentos/workstreams/WS-ALPHA01.txt" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), path: "workstreams/WS-ALPHA01.md" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), repository: "other" },
    }));
  });

  it("rejects malformed digests", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), commit: "0123456789ABCDEF0123456789ABCDEF01234567" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), commit: "0123456789abcdef" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), content_sha256: hex64("c1").slice(1) },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      project_source: { ...projectSource(), request_sha256: "g".repeat(64) },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), fingerprint: hex64("f1") + "0" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), creation_event_sha256: "zz" },
    }));
  });

  it("rejects recorded_at values that are not owner UTC instants", () => {
    for (const recordedAt of [
      "2026-13-01T00:00:00Z",
      "2026-02-30T00:00:00Z",
      "2026-11-01T12:00:00+01:00",
      "2026-11-01 12:00:00Z",
      "2026-11-01T12:00:00",
      "not-a-clock",
      1730000000000,
      null,
    ]) {
      expectNull(documentBody("MATERIALIZED_OBSERVATION", {
        materialization: { ...materialization(), recorded_at: recordedAt },
      }));
    }
  });

  it("rejects intent ids with controls, lone surrogates or oversize text", () => {
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), intent_id: "" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), intent_id: "a".repeat(65) },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), intent_id: "intent\u0000id" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), intent_id: "intent\nid" },
    }));
    expectNull(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), intent_id: "\uD800intent" },
    }));
    expect(decodeProjectAssociation(documentBody("MATERIALIZED_OBSERVATION", {
      runtime_creation: { ...runtimeCreation(), intent_id: "运行时意图" },
    }), SELECTION)).toBeNull();
  });
});

describe("decodeProjectAssociation body budget", () => {
  it("exposes the frozen body budget and rejects oversized bodies", () => {
    expect(PROJECT_ASSOCIATION_BODY_BYTES).toBe(16384);
    const oversized = JSON.stringify(documentBody("MATERIALIZED_OBSERVATION", {
      padding: "x".repeat(PROJECT_ASSOCIATION_BODY_BYTES),
    }));
    expect(oversized.length).toBeGreaterThan(PROJECT_ASSOCIATION_BODY_BYTES);
    expectNull(oversized);
    const oversizedObject = documentBody("MATERIALIZED_OBSERVATION", {
      padding: "x".repeat(PROJECT_ASSOCIATION_BODY_BYTES),
    });
    expectNull(oversizedObject);
  });
});

describe("normalizeProjectAssociationSelection", () => {
  it("normalizes and freezes the exact model selection pair", () => {
    const normalized = normalizeProjectAssociationSelection({ workRef: "WS:ALPHA01", rootJobId: "JOB-7" });
    expect(normalized).toEqual({ workRef: "WS:ALPHA01", rootJobId: "JOB-7" });
    expect(Object.isFrozen(normalized)).toBe(true);
    expect(normalized?.workRef).toBe("WS:ALPHA01");
    expect(normalized?.rootJobId).toBe("JOB-7");
  });

  it("rejects selections outside the closed workspace pair", () => {
    expect(normalizeProjectAssociationSelection(null)).toBeNull();
    expect(normalizeProjectAssociationSelection("WS:ALPHA01")).toBeNull();
    expect(normalizeProjectAssociationSelection([])).toBeNull();
    expect(normalizeProjectAssociationSelection({ workRef: "WS:ALPHA01" })).toBeNull();
    expect(normalizeProjectAssociationSelection({ workRef: "WS:ALPHA01", rootJobId: "JOB-7", session: "s" })).toBeNull();
    expect(normalizeProjectAssociationSelection({ workRef: "ws:ALPHA01", rootJobId: "JOB-7" })).toBeNull();
    expect(normalizeProjectAssociationSelection({ workRef: "ALPHA01", rootJobId: "JOB-7" })).toBeNull();
    expect(normalizeProjectAssociationSelection({ workRef: "WS:ALPHA01", rootJobId: "job-7" })).toBeNull();
    expect(normalizeProjectAssociationSelection({ workRef: "WS:ALPHA01", rootJobId: "JOB-1234567890" })).toBeNull();
  });
});
