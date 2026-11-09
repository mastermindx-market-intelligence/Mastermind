/** Fail-closed parser tests for the delegated-task projection. The binding
 *  block must satisfy the SAME fences the Python admission contract
 *  (control_plane/child_execution_contracts.py, ExecutionBinding v1/v1.1)
 *  enforces: bounded printable identity triple, hex64 request digest,
 *  canonical long-name complexity, open-but-normalized runtime kind, sparse
 *  v1.1 schema derivation — and it must REFUSE fields the Python side has
 *  not defined yet (the PENDING v1.2 requester block). */
import { describe, expect, it } from "vitest";
import {
  BINDING_SCHEMA_V1, BINDING_SCHEMA_V1_1, KNOWN_RUNTIME_KINDS,
  PENDING_REQUESTER_FIELDS, TASK_COMPLEXITIES, parseDelegatedTask,
} from "./delegated-task";

const binding = {
  root_run_ref: "root-wo19-coding-7",
  immediate_parent_run_ref: "run-41",
  logical_child_key: "fleet-launch-repair",
  request_digest: "a".repeat(64),
  effective_complexity: "C2_COMPLEX_BOUNDED",
  task_kind: "code",
  runtime_kind: "fabric-native",
  operation_key: "op-77",
  caller_namespace: "mastermind:fabric",
  lease_ref: "lease-9",
};

function task(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    binding: { ...binding },
    title: "Repair launch refusal",
    summary: null,
    state: "queued",
    stateReason: null,
    owner: null,
    route: [],
    authority: "preview",
    lastActivity: null,
    ...extra,
  };
}

function rejects(payload: unknown, detail: RegExp) {
  expect(() => parseDelegatedTask(payload)).toThrow(detail);
}

describe("parseDelegatedTask — contract-aligned binding", () => {
  it("parses a v1.1 binding and derives the schema tag from extension content", () => {
    const parsed = parseDelegatedTask(task());
    expect(parsed.binding.schema).toBe(BINDING_SCHEMA_V1_1);
    expect(parsed.binding.logical_child_key).toBe("fleet-launch-repair");
    expect(parsed.binding.caller_namespace).toBe("mastermind:fabric");
    expect(parsed.binding.operation_key).toBe("op-77");
    expect(parsed.binding.lease_ref).toBe("lease-9");
    expect(parsed.binding.runtime_kind).toBe("fabric-native");
    expect(parsed.state).toBe("queued");
  });

  it("normalizes a plain v1 binding (no extensions) to the v1 schema tag — sparse law", () => {
    const v1 = { ...binding, runtime_kind: "", operation_key: "", caller_namespace: "", lease_ref: "" };
    const fromWireTag = parseDelegatedTask(task({ binding: { ...v1, schema: "ExecutionBinding.v1.1" } }));
    expect(fromWireTag.binding.schema).toBe(BINDING_SCHEMA_V1); // v1.1 label without content IS v1
    const fromNoTag = parseDelegatedTask(task({ binding: v1 }));
    expect(fromNoTag.binding.schema).toBe(BINDING_SCHEMA_V1);
    expect(parseDelegatedTask(task()).binding.schema).toBe(BINDING_SCHEMA_V1_1);
  });

  it("normalizes complexity shorthand to canonical long names, like the shared boundary", () => {
    expect(parseDelegatedTask(task({ binding: { ...binding, effective_complexity: "c2" } })).binding.effective_complexity)
      .toBe("C2_COMPLEX_BOUNDED");
    expect(parseDelegatedTask(task({ binding: { ...binding, effective_complexity: "Reviewer" } })).binding.effective_complexity)
      .toBe("REVIEWER");
    expect([...TASK_COMPLEXITIES]).toEqual([
      "C0_MECHANICAL", "C1_ROUTINE_BOUNDED", "C2_COMPLEX_BOUNDED",
      "C3_FRONTIER_JUDGMENT", "REVIEWER",
    ]);
  });

  it("normalizes runtime kind strip+lower and keeps the vocabulary open", () => {
    expect(parseDelegatedTask(task({ binding: { ...binding, runtime_kind: "  T3-Native " } })).binding.runtime_kind)
      .toBe("t3-native");
    expect(parseDelegatedTask(task({ binding: { ...binding, runtime_kind: "some-future-harness" } })).binding.runtime_kind)
      .toBe("some-future-harness"); // open set: newer runtimes pass through
    expect(parseDelegatedTask(task({ binding: { ...binding, runtime_kind: "   " } })).binding.runtime_kind)
      .toBe(""); // whitespace-only reads as unset, exactly like the Python owner
    expect(KNOWN_RUNTIME_KINDS).toContain("t3-native");
    expect(KNOWN_RUNTIME_KINDS).toContain("fabric-native");
  });

  it("keeps the honest-state rules at the presentation layer", () => {
    expect(() => parseDelegatedTask(task({ state: "unknown" }))).toThrow(/stateReason/);
    expect(() => parseDelegatedTask(task({ state: "declined" }))).toThrow(/stateReason/);
    expect(parseDelegatedTask(task({ state: "unknown", stateReason: "send returned no outcome" })).state)
      .toBe("unknown");
    expect(() => parseDelegatedTask(task({ route: ["a", "b", "c", "d", "e", "f", "g"] }))).toThrow(/route/);
    expect(() => parseDelegatedTask(task({ authority: "admin" }))).toThrow(/authority/);
    expect(() => parseDelegatedTask(task({ title: "" }))).toThrow(/title/);
  });
});

describe("parseDelegatedTask — fail-closed on binding drift", () => {
  it("refuses a control character in the identity triple (the \\x1f command-id join law)", () => {
    rejects(task({ binding: { ...binding, root_run_ref: "root\u001fclone" } }), /root_run_ref/);
    rejects(task({ binding: { ...binding, logical_child_key: "a\u0000b" } }), /logical_child_key/);
  });
  it("refuses empty/oversized identity fields and bad digests", () => {
    rejects(task({ binding: { ...binding, logical_child_key: "" } }), /logical_child_key/);
    rejects(task({ binding: { ...binding, immediate_parent_run_ref: "r".repeat(257) } }), /immediate_parent_run_ref/);
    rejects(task({ binding: { ...binding, request_digest: "A".repeat(64) } }), /request_digest/);
    rejects(task({ binding: { ...binding, request_digest: "deadbeef" } }), /request_digest/);
  });
  it("refuses non-canonical complexity and unknown schema labels", () => {
    rejects(task({ binding: { ...binding, effective_complexity: "C4_FRONTIER" } }), /not a canonical class/);
    rejects(task({ binding: { ...binding, schema: "ExecutionBinding.v2" } }), /schema/);
  });
  it("refuses fields the Python contract does not define (unknown keys, missing keys)", () => {
    rejects(task({ binding: { ...binding, model_ref: "glm-5.3" } }), /does not define/);
    rejects(task({ extra: 1 }), /does not define/);
    const missing = { ...binding } as Record<string, unknown>;
    delete missing.lease_ref;
    rejects(task({ binding: missing }), /missing a contract field/);
  });
  it("refuses the PENDING v1.2 requester fields until the Python contract has them", () => {
    // LANE_RETURN_PATH_DIRECTOR_F.md gap #1: the requester block is being
    // added as ChildExecutionRequest/ExecutionBinding v1.2 (Director C2).
    // Until then these keys are drift, not contract fields.
    expect([...PENDING_REQUESTER_FIELDS]).toEqual(["teammate_id", "conversation_id", "project_id"]);
    for (const field of PENDING_REQUESTER_FIELDS) {
      rejects(task({ binding: { ...binding, [field]: "premature" } }), /does not define/);
    }
  });
});
