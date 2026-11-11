/**
 * Inert Vitest coverage for {@link ProjectPlanningCommandPort}, driven through
 * the real {@link OperationController}.
 *
 * DISCLOSED BOUNDARY: the only stub in this file is the
 * `ProjectPlanningTransport` — an in-memory stand-in for the accepted S19
 * transport, which is the port's single external boundary. The port, the
 * controller and the pointer-store semantics are the real implementations; no
 * port or controller is mocked and no network, filesystem or process effect is
 * performed.
 */

import { describe, expect, it, vi } from "vitest";
import { OperationController } from "../orchestration/operation-controller";
import type {
  CommandIntent,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "../orchestration/operation-controller";
import {
  ProjectPlanningCommandPort,
  makePlanningIntent,
  planningIntentId,
  planningOperationKey,
} from "./project-planning-command-port";
import type {
  PlanningOperation,
  ProjectPlanningTransport,
} from "./project-planning-transport";

// ── Fixtures ──────────────────────────────────────────────────────────────────

const fill = (pattern: string, count: number): string =>
  pattern.repeat(Math.ceil(count / pattern.length)).slice(0, count);
const hex40 = (pattern: string): string => fill(pattern, 40);
const hex64 = (pattern: string): string => fill(pattern, 64);

const OWNER: OwnerContext = { principalScope: "scope-A", generation: "generation-1" };
const WORK_REF = "WS:PROJ-1";
const TARGET_KEY = `project-initial-planning.v1:${WORK_REF}`;

/** One exact already-qualified published project (grounding matches source). */
const QUALIFIED = {
  stage: "clarify",
  work_ref: WORK_REF,
  project_source: {
    repository: "macro",
    commit: hex40("a1b2"),
    path: "agentos/workstreams/WS-PROJ-1.md",
    content_sha256: hex64("c3d4"),
    request_sha256: hex64("d5e6"),
  },
  publication: {
    request_id: `mmos-project-create-${hex40("e7f8")}`,
    principal_scope: hex64("f9a0"),
    event_id: 7,
    receipt_sha256: hex64("b1c2"),
  },
  grounding: { mastermind_sha: hex40("a1b2"), macro_sha: hex40("a1b2") },
  private_request: "Initial planning request text",
};

const expectedKey = (): string => planningOperationKey(OWNER, QUALIFIED);

/** Raw S19 direct native ceo receipt, exactly the closed factory shape. */
function directReceipt(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: "mastermind.ceo_direct_native_receipt.v1",
    intent_id: planningIntentId(expectedKey(), OWNER.principalScope),
    fingerprint: hex64("dd01"),
    job_id: "JOB-root-1",
    status: "QUEUED",
    accepted: true,
    duplicate: false,
    dispatched: false,
    authority: {
      requested: ["READ", "RESEARCH"],
      policy_sha256: hex64("ee02"),
      authority_level: "A0",
    },
    grounding: { mastermind_sha: hex40("a1b2"), macro_sha: hex40("a1b2") },
    created_at_ms: 1760000000000,
    work_ref: WORK_REF,
    ...overrides,
  };
}

/** Only external boundary stubbed: the S19 projectPlanning transport. */
function stubTransport(
  handler?: (operation: PlanningOperation, args: Readonly<Record<string, unknown>>) => unknown,
) {
  const calls: Array<{
    operation: PlanningOperation;
    args: Readonly<Record<string, unknown>>;
  }> = [];
  const transport: ProjectPlanningTransport = {
    request: vi.fn(async (operation, args) => {
      calls.push({ operation, args: { ...args } });
      return handler ? handler(operation, args) : directReceipt();
    }),
  };
  return { transport, calls };
}

/** In-memory PendingPointerStore, exact-match semantics as the real host store. */
function fixture(
  transport: ProjectPlanningTransport,
  owner: () => OwnerContext | null = () => ({ ...OWNER }),
) {
  const hints = new Map<string, OperationPointer>();
  const reserved: OperationPointer[] = [];
  const samePointer = (a: OperationPointer, b: OperationPointer): boolean =>
    a.operationKey === b.operationKey && a.kind === b.kind && a.targetKey === b.targetKey;
  const store: PendingPointerStore = {
    read: (scope) => hints.get(scope) ?? null,
    reserve: (scope, pointer) => {
      const existing = hints.get(scope);
      if (existing) return { reserved: false, pointer: existing };
      hints.set(scope, pointer);
      reserved.push({ ...pointer });
      return { reserved: true };
    },
    clearIfEqual: (scope, pointer) => {
      const existing = hints.get(scope);
      if (existing && samePointer(existing, pointer)) {
        hints.delete(scope);
        return true;
      }
      return false;
    },
  };
  const port = new ProjectPlanningCommandPort(transport, owner);
  const controller = new OperationController(port, store);
  return { controller, port, hints, reserved };
}

/** Drive the real port directly (no mock) for one submit. */
async function submitOnce(
  transport: ProjectPlanningTransport,
  owner: () => OwnerContext | null = () => ({ ...OWNER }),
) {
  const port = new ProjectPlanningCommandPort(transport, owner);
  const intent = port.makePlanningIntent(QUALIFIED)!;
  const pointer = port.prepare(intent);
  const receipt = await port.submit(pointer, intent, new AbortController().signal);
  return { port, intent, pointer, receipt };
}

// ── One submit ────────────────────────────────────────────────────────────────

describe("one submit", () => {
  it("submits exactly once and publishes the accepted selection", async () => {
    const { transport, calls } = stubTransport();
    const f = fixture(transport);
    const intent = f.port.makePlanningIntent(QUALIFIED);
    expect(intent).not.toBeNull();
    expect(intent!.kind).toBe("launch");
    expect(intent!.targetKey).toBe(TARGET_KEY);
    expect(intent!.payload.operation_key).toBe(expectedKey());
    expect(makePlanningIntent(OWNER, QUALIFIED)).toEqual(intent);

    const state = await f.controller.begin(intent!);
    expect(state.status).toBe("accepted");
    if (state.status !== "accepted") throw new Error("expected an accepted terminal state");
    expect(state.reason).toBe("ACCEPTED");
    expect(state.missionSelection).toEqual({ workRef: WORK_REF, rootJobId: "JOB-root-1" });
    expect(f.hints.size).toBe(0);

    expect(transport.request).toHaveBeenCalledTimes(1);
    expect(calls[0].operation).toBe("submit");
    expect(Object.keys(calls[0].args).sort()).toEqual(
      [
        "grounding",
        "operation_key",
        "private_request",
        "project_source",
        "publication",
        "stage",
        "work_ref",
      ].sort(),
    );
    expect(calls[0].args.operation_key).toBe(expectedKey());
    expect(calls[0].args.work_ref).toBe(WORK_REF);
    expect(calls[0].args.private_request).toBe(QUALIFIED.private_request);
  });

  it("persists only the safe status lookup pointer", async () => {
    const { transport } = stubTransport();
    const f = fixture(transport);
    const state = await f.controller.begin(f.port.makePlanningIntent(QUALIFIED)!);
    expect(state.status).toBe("accepted");
    expect(f.reserved).toHaveLength(1);
    const pointer = f.reserved[0];
    expect(Object.keys(pointer).sort()).toEqual(["kind", "operationKey", "targetKey"].sort());
    expect(pointer.kind).toBe("launch");
    expect(pointer.targetKey).toBe(TARGET_KEY);
    expect(pointer.operationKey).toBe(expectedKey());
    const serialized = JSON.stringify(pointer);
    expect(serialized).not.toContain(QUALIFIED.private_request);
    expect(serialized).not.toContain(QUALIFIED.project_source.request_sha256);
    expect(serialized).not.toContain("private_request");
  });
});

// ── Lost submit ───────────────────────────────────────────────────────────────

describe("lost submit", () => {
  it("re-reads the same key by status and never replaces the submission", async () => {
    let submits = 0;
    const { transport, calls } = stubTransport((operation) => {
      if (operation === "submit") {
        submits += 1;
        throw new Error("submit transport lost");
      }
      return directReceipt();
    });
    const f = fixture(transport);
    const first = await f.controller.begin(f.port.makePlanningIntent(QUALIFIED)!);
    expect(first.status).toBe("unknown");
    expect(f.hints.get(OWNER.principalScope)?.operationKey).toBe(expectedKey());
    expect(f.hints.get(OWNER.principalScope)?.kind).toBe("launch");

    // A new begin must join the pending hint, never submit a second effect.
    const again = await f.controller.begin(f.port.makePlanningIntent(QUALIFIED)!);
    expect(again.status).toBe("checking");
    expect(again.reason).toBe("PENDING_POINTER");
    expect(submits).toBe(1);

    const recovered = await f.controller.recover();
    expect(recovered.status).toBe("accepted");
    expect(submits).toBe(1);
    const statusCalls = calls.filter((c) => c.operation === "status");
    expect(statusCalls).toHaveLength(1);
    expect(statusCalls[0].args).toEqual({
      operation_key: expectedKey(),
      work_ref: WORK_REF,
    });
    expect(f.hints.size).toBe(0);
  });

  it("maps a throwing transport to a nonterminal unknown at the port", async () => {
    const { transport } = stubTransport(() => {
      throw new Error("submit transport lost");
    });
    const { receipt } = await submitOnce(transport);
    expect(receipt.disposition).toBe("unknown");
    expect(receipt.reason).toBe("TRANSPORT_ERROR");
    expect(receipt.missionSelection).toBeUndefined();
  });
});

// ── Foreign / malformed receipts ──────────────────────────────────────────────

const FOREIGN: Array<[string, Record<string, unknown>, string]> = [
  ["a foreign intent_id", { intent_id: `ceo-project-planning-${hex40("0000")}` }, "RECEIPT_MISMATCH"],
  ["a foreign work_ref", { work_ref: "WS:OTHER" }, "RECEIPT_MISMATCH"],
  ["a foreign digest", { fingerprint: "not-hex" }, "MALFORMED_RECEIPT"],
  ["a foreign job reference", { job_id: "JOB bad id" }, "UNKNOWN_RECEIPT"],
  ["an invented wrapper field", { wrapped: true }, "MALFORMED_RECEIPT"],
  ["a non-accepted receipt", { accepted: false }, "UNKNOWN_RECEIPT"],
];

describe("foreign or malformed receipts never publish", () => {
  it.each(FOREIGN)("%s is mapped to a specific unknown at the port", async (_name, override, expectedReason) => {
    const { transport } = stubTransport(() => ({ ...directReceipt(), ...override }));
    const { receipt } = await submitOnce(transport);
    expect(receipt.disposition).toBe("unknown");
    expect(receipt.reason).toBe(expectedReason);
    expect(receipt.missionSelection).toBeUndefined();
  });

  it.each(FOREIGN)("%s retains the pointer with no acceptance", async (_name, override) => {
    const { transport } = stubTransport(() => ({ ...directReceipt(), ...override }));
    const f = fixture(transport);
    const state = await f.controller.begin(f.port.makePlanningIntent(QUALIFIED)!);
    // The controller collapses every unknown receipt to UNKNOWN_RECEIPT and
    // keeps the pointer so a later recover can resolve the real outcome.
    expect(state.status).toBe("unknown");
    expect(state.reason).toBe("UNKNOWN_RECEIPT");
    expect(f.hints.get(OWNER.principalScope)?.operationKey).toBe(expectedKey());
    expect(transport.request).toHaveBeenCalledTimes(1);
  });

  it("resolves the retained pointer once a genuine receipt arrives", async () => {
    let foreign = true;
    const { transport, calls } = stubTransport(() =>
      foreign
        ? { ...directReceipt(), intent_id: `ceo-project-planning-${hex40("9999")}` }
        : directReceipt(),
    );
    const f = fixture(transport);
    const first = await f.controller.begin(f.port.makePlanningIntent(QUALIFIED)!);
    expect(first.status).toBe("unknown");
    foreign = false;
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(calls.filter((c) => c.operation === "submit")).toHaveLength(1);
    expect(f.hints.size).toBe(0);
  });
});

// ── Authentication epoch changes ──────────────────────────────────────────────

describe("authentication epoch changes are suppressed", () => {
  it("never publishes a receipt that arrives under a changed epoch", async () => {
    let generation = "generation-1";
    const { transport, calls } = stubTransport((operation) => {
      if (operation !== "submit") return directReceipt();
      generation = "generation-2"; // A -> B while the submit is in flight
      return directReceipt();
    });
    const f = fixture(transport, () => ({ principalScope: "scope-A", generation }));
    const state = await f.controller.begin(f.port.makePlanningIntent(QUALIFIED)!);
    expect(state.status).not.toBe("accepted");
    generation = "generation-3"; // A signs back in: a third epoch, not a repeat
    expect(f.hints.get(OWNER.principalScope)?.operationKey).toBe(expectedKey());
    expect((await f.controller.recover()).status).toBe("accepted");
    expect(calls.filter((c) => c.operation === "submit")).toHaveLength(1);
    expect(f.hints.size).toBe(0);
  });

  it("refuses to map a response when the owner generation moved during submit", async () => {
    let generation = "generation-1";
    const { transport } = stubTransport(() => {
      generation = "generation-2";
      return directReceipt();
    });
    const { receipt } = await submitOnce(transport, () => ({
      principalScope: "scope-A",
      generation,
    }));
    expect(receipt.disposition).toBe("unknown");
    expect(receipt.missionSelection).toBeUndefined();
  });

  it("reports an absent owner before any transport call", async () => {
    const { transport } = stubTransport();
    const composing = new ProjectPlanningCommandPort(transport, () => ({ ...OWNER }));
    const intent = composing.makePlanningIntent(QUALIFIED)!;
    const pointer = composing.prepare(intent);
    const absent = new ProjectPlanningCommandPort(transport, () => null);
    const receipt = await absent.submit(pointer, intent, new AbortController().signal);
    expect(receipt.disposition).toBe("unknown");
    expect(receipt.reason).toBe("OWNER_ABSENT");
    expect(transport.request).not.toHaveBeenCalled();
  });
});

// ── Status reads ──────────────────────────────────────────────────────────────

describe("status reads", () => {
  it("reopens the same pointer and never resubmits or guesses a root", async () => {
    let failing = true;
    const { transport, calls } = stubTransport((operation) => {
      if (operation === "status" && failing) throw new Error("status unavailable");
      return directReceipt();
    });
    const f = fixture(transport);
    f.hints.set(OWNER.principalScope, {
      operationKey: expectedKey(),
      kind: "launch",
      targetKey: TARGET_KEY,
    });
    // The port reports a failed status read as a nonterminal unknown receipt;
    // the controller retains the pointer either way.
    expect((await f.controller.recover()).reason).toBe("UNKNOWN_RECEIPT");
    failing = false;
    expect((await f.controller.recover()).status).toBe("accepted");
    const statusCalls = calls.filter((c) => c.operation === "status");
    expect(statusCalls).toHaveLength(2);
    expect(statusCalls[1].args).toEqual(statusCalls[0].args);
    expect(statusCalls[0].args).toEqual({
      operation_key: expectedKey(),
      work_ref: WORK_REF,
    });
    expect(calls.some((c) => c.operation === "submit")).toBe(false);
    expect(f.hints.size).toBe(0);
  });

  it("maps a throwing status read to a transport unknown at the port", async () => {
    const { transport } = stubTransport(() => {
      throw new Error("status unavailable");
    });
    const port = new ProjectPlanningCommandPort(transport, () => ({ ...OWNER }));
    const pointer: OperationPointer = {
      operationKey: expectedKey(),
      kind: "launch",
      targetKey: TARGET_KEY,
    };
    const receipt = await port.readOperation(pointer, new AbortController().signal);
    expect(receipt.disposition).toBe("unknown");
    expect(receipt.reason).toBe("TRANSPORT_ERROR");
    expect(receipt.missionSelection).toBeUndefined();
  });
});

// ── Key determinism ───────────────────────────────────────────────────────────

describe("operation keys", () => {
  it("are stable for an identical request and distinct under exact edits", () => {
    const port = new ProjectPlanningCommandPort(stubTransport().transport, () => ({ ...OWNER }));
    const first = port.makePlanningIntent(QUALIFIED)!;
    const repeat = port.makePlanningIntent(QUALIFIED)!;
    expect(first.payload.operation_key).toBe(repeat.payload.operation_key);

    const editedRequest = port.makePlanningIntent({
      ...QUALIFIED,
      private_request: "Edited initial planning request",
    })!;
    expect(editedRequest.payload.operation_key).not.toBe(first.payload.operation_key);
    expect(editedRequest.targetKey).toBe(first.targetKey);

    const editedStage = port.makePlanningIntent({ ...QUALIFIED, stage: "plan" })!;
    expect(editedStage.payload.operation_key).not.toBe(first.payload.operation_key);

    const otherOwner = makePlanningIntent({ ...OWNER, principalScope: "scope-B" }, QUALIFIED)!;
    expect(otherOwner.payload.operation_key).not.toBe(first.payload.operation_key);

    const key = String(first.payload.operation_key);
    expect(key.length).toBeLessThanOrEqual(128);
    expect(/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(key)).toBe(true);
  });

  it("derives the S19 intent id over {operation_key, principal_scope}", () => {
    const id = planningIntentId(expectedKey(), OWNER.principalScope);
    expect(id.startsWith("ceo-project-planning-")).toBe(true);
    expect(id).toHaveLength("ceo-project-planning-".length + 40);
    expect(planningIntentId(expectedKey(), "scope-B")).not.toBe(id);
    expect(planningIntentId("mmos-project-planning-other", OWNER.principalScope)).not.toBe(id);
  });
});

// ── Invalid input ─────────────────────────────────────────────────────────────

describe("invalid arguments never reach the transport", () => {
  it("composes no intent for out-of-contract input", () => {
    const { transport, calls } = stubTransport();
    const port = new ProjectPlanningCommandPort(transport, () => ({ ...OWNER }));
    expect(port.makePlanningIntent({ ...QUALIFIED, stage: "bogus" })).toBeNull();
    expect(port.makePlanningIntent({ ...QUALIFIED, private_request: "   " })).toBeNull();
    expect(
      port.makePlanningIntent({
        ...QUALIFIED,
        publication: { ...QUALIFIED.publication, event_id: 0 },
      }),
    ).toBeNull();
    expect(
      port.makePlanningIntent({
        ...QUALIFIED,
        grounding: { mastermind_sha: "not-hex", macro_sha: hex40("a1b2") },
      }),
    ).toBeNull();
    expect(
      port.makePlanningIntent({ ...QUALIFIED, extra: true } as unknown as typeof QUALIFIED),
    ).toBeNull();
    expect(makePlanningIntent(null, QUALIFIED)).toBeNull();
    expect(transport.request).not.toHaveBeenCalled();
    expect(calls).toHaveLength(0);
  });

  it("rejects a tampered intent or target before any call", async () => {
    const { transport, calls } = stubTransport();
    const f = fixture(transport);
    const intent = f.port.makePlanningIntent(QUALIFIED)!;
    const tamperedKey: CommandIntent = {
      kind: "launch",
      targetKey: intent.targetKey,
      payload: {
        ...intent.payload,
        operation_key: `mmos-project-planning-${hex40("abab")}`,
      },
    };
    expect((await f.controller.begin(tamperedKey)).reason).toBe("MALFORMED_POINTER");
    const tamperedTarget: CommandIntent = {
      kind: "launch",
      targetKey: "project-initial-planning.v1:WS:OTHER",
      payload: intent.payload,
    };
    expect((await f.controller.begin(tamperedTarget)).reason).toBe("MALFORMED_POINTER");
    expect(transport.request).not.toHaveBeenCalled();
    expect(calls).toHaveLength(0);
    expect(f.hints.size).toBe(0);
  });

  it("treats a fixed grounding as closed data, not as a grant", () => {
    const { transport } = stubTransport();
    const fixed = { mastermind_sha: hex40("a1b2"), macro_sha: hex40("a1b2") };
    const port = new ProjectPlanningCommandPort(transport, () => ({ ...OWNER }), fixed);
    expect(port.makePlanningIntent(QUALIFIED)).not.toBeNull();
    expect(
      port.makePlanningIntent({
        ...QUALIFIED,
        grounding: { mastermind_sha: hex40("a1b2"), macro_sha: hex40("0123") },
      }),
    ).toBeNull();
    const absent = new ProjectPlanningCommandPort(transport, () => null);
    expect(absent.makePlanningIntent(QUALIFIED)).toBeNull();
    expect(absent.context()).toBeNull();
    expect(transport.request).not.toHaveBeenCalled();
  });
});
