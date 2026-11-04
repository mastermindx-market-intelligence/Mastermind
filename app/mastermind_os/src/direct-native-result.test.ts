import { describe, it, expect, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import {
  decodeDirectNativeResult,
  parseDirectNativeJson,
  directConsumeIdentity,
  parseDirectConsumeTarget,
  DIRECT_RESULT_BYTES,
} from "./direct-native-result";
import { DirectNativeCommandPort } from "./orchestration/direct-native-command-port";
import { OperationController } from "./orchestration/operation-controller";
import { createIndexedDbPendingPointerStore } from "./orchestration/indexeddb-pending-pointer-store";
import { directLocationInput } from "./direct-native-location";
import { selectionFromLocation } from "./mission";
export const selected = {
  work_ref: "WS:H2-FIXTURE",
  job_id: "JOB-123",
  attempt_id: "ATT-456",
};
export function result(consumed = false) {
  return {
    schema: "mastermind.direct_native_result_response.v1",
    selection: { ...selected },
    availability: "AVAILABLE",
    reason_codes: [],
    result: {
      result_digest: "d".repeat(64),
      summary: "Retained native analysis.",
      current_state: "Completed",
      completed_steps: ["Read supplied evidence"],
      next_actions: [],
    },
    consumption: consumed
      ? { state: "CONSUMED", receipt_digest: "c".repeat(64) }
      : { state: "UNCONSUMED", receipt_digest: null },
  };
}
describe("closed direct-result view", () => {
  it("adds a closed reopen hint without relaxing the original mission decoder", () => {
    const base = "?work_ref=WS%3AH2-FIXTURE&root_job_id=JOB-123";
    expect(directLocationInput(base).direct).toBe(false);
    const direct = base + "&direct_native_job=JOB-123";
    expect(selectionFromLocation(direct)).toBeNull();
    expect(directLocationInput(direct)).toEqual({
      hasIdentity: true,
      direct: true,
      selection: { workRef: "WS:H2-FIXTURE", rootJobId: "JOB-123" },
    });
    for (const raw of [
      base + "&direct_native_job=JOB-other",
      direct + "&direct_native_job=JOB-123",
      direct + "&worker=codex-01",
      base + "&direct_native_job=%GG",
    ])
      expect(directLocationInput(raw).selection).toBeNull();
  });
  it("discovers only the exact selected Job's actual Attempt without role inference", () => {
    const decoded = decodeDirectNativeResult(result(), {
      ...selected,
      attempt_id: null,
    });
    expect(decoded?.selection.attempt_id).toBe(selected.attempt_id);
    expect(decoded?.consumption?.state).toBe("UNCONSUMED");
    expect(
      decodeDirectNativeResult(result(), { ...selected, job_id: "JOB-other" }),
    ).toBeNull();
    expect(
      decodeDirectNativeResult(result(), {
        ...selected,
        attempt_id: "ATT-other",
      }),
    ).toBeNull();
  });
  it.each([
    "extra",
    "schema",
    "null-attempt",
    "boolean-id",
    "digest",
    "control",
    "surrogate",
    "long",
    "list",
    "consumption",
  ])("refuses %s", (fault) => {
    const v: Record<string, any> = structuredClone(result());
    if (fault === "extra") v.acceptance = "PRODUCT_ACCEPTED";
    if (fault === "schema") v.schema = "mastermind.workspace_role_result.v1";
    if (fault === "null-attempt") v.selection.attempt_id = null;
    if (fault === "boolean-id") v.selection.job_id = true;
    if (fault === "digest") v.result.result_digest = "not-a-digest";
    if (fault === "control") v.result.summary = "secret\u0000";
    if (fault === "surrogate") v.result.summary = "\ud800";
    if (fault === "long") v.result.summary = "a".repeat(4097);
    if (fault === "list") v.result.next_actions = Array(33).fill("a");
    if (fault === "consumption")
      v.consumption = {
        state: "PRODUCT_ACCEPTED",
        receipt_digest: "c".repeat(64),
      };
    expect(decodeDirectNativeResult(v)).toBeNull();
  });
  it("keeps unavailable consumption unknown and accepts only the closed reason set", () => {
    const v = {
      schema: "mastermind.direct_native_result_response.v1",
      selection: { ...selected, attempt_id: null },
      availability: "UNAVAILABLE",
      reason_codes: ["NOT_TERMINAL"],
      result: null,
      consumption: null,
    };
    expect(decodeDirectNativeResult(v)?.consumption).toBeNull();
    expect(
      decodeDirectNativeResult({
        ...v,
        consumption: { state: "UNCONSUMED", receipt_digest: null },
      }),
    ).toBeNull();
    expect(
      decodeDirectNativeResult({
        ...v,
        reason_codes: ["NOT_TERMINAL", "NOT_TERMINAL"],
      }),
    ).toBeNull();
    expect(
      decodeDirectNativeResult({ ...v, reason_codes: ["unknown"] }),
    ).toBeNull();
  });
  it("uses Unicode codepoints for text ceilings and UTF8 bytes for total response", () => {
    const v = result();
    v.result.summary = "😀".repeat(4096);
    expect(decodeDirectNativeResult(v)).not.toBeNull();
    v.result.current_state = "😀".repeat(4096);
    expect(decodeDirectNativeResult(v)).toBeNull();
  });
  it.each([
    '{"a":1,"a":2}',
    '{"a":{"x":1,"\\u0078":2}}',
    '{"a":NaN}',
    '{"a":1e999}',
    '{"a":1,}',
    "[1,]",
    "{} trailing",
  ])("rejects malformed/duplicate JSON %s", (raw) => {
    expect(() => parseDirectNativeJson(raw)).toThrow();
  });
  it("bounds byte count and nesting before display", () => {
    expect(() =>
      parseDirectNativeJson(" ".repeat(DIRECT_RESULT_BYTES + 1)),
    ).toThrow();
    expect(() =>
      parseDirectNativeJson("[".repeat(34) + "0" + "]".repeat(34)),
    ).toThrow();
    expect(
      decodeDirectNativeResult(parseDirectNativeJson(JSON.stringify(result()))),
    ).toEqual(result());
  });
});
describe("explicit consume through the existing durable pointer owner", () => {
  const scope = "a".repeat(64),
    owner = () => ({ principalScope: scope, generation: "1" });
  it("binds identity to original parent scope, exact Attempt and terminal digest", () => {
    const p = directConsumeIdentity(scope, selected, "d".repeat(64));
    expect(parseDirectConsumeTarget(p.targetKey)).toEqual({
      ...selected,
      result_digest: "d".repeat(64),
    });
    expect(
      directConsumeIdentity("b".repeat(64), selected, "d".repeat(64))
        .operationKey,
    ).not.toBe(p.operationKey);
    expect(
      directConsumeIdentity(
        scope,
        { ...selected, attempt_id: "ATT-other" },
        "d".repeat(64),
      ).operationKey,
    ).not.toBe(p.operationKey);
    expect(
      directConsumeIdentity(scope, selected, "e".repeat(64)).operationKey,
    ).not.toBe(p.operationKey);
  });
  it("retains unknown across reopen; recover only reads and clears after actual consumption", async () => {
    const factory = new IDBFactory(),
      store = createIndexedDbPendingPointerStore(factory);
    const transport = {
      consume: vi.fn().mockRejectedValue(new Error("lost reply")),
      read: vi.fn().mockResolvedValue(result()),
    };
    const port = new DirectNativeCommandPort(transport, owner),
      intent = port.makeConsumeIntent(selected, "d".repeat(64))!;
    const controller = new OperationController(port, store);
    expect((await controller.begin(intent)).status).toBe("unknown");
    const original = await store.read(scope);
    expect(original?.kind).toBe("consume");
    const reopened = new OperationController(
      port,
      createIndexedDbPendingPointerStore(factory),
    );
    expect((await reopened.recover()).status).toBe("unknown");
    expect(await store.read(scope)).toEqual(original);
    expect(transport.consume).toHaveBeenCalledTimes(1);
    transport.read.mockResolvedValue(result(true));
    expect((await reopened.recover()).status).toBe("accepted");
    expect(await store.read(scope)).toBeNull();
    expect(transport.consume).toHaveBeenCalledTimes(1);
  });
  it("cannot adopt a different terminal or a late auth generation", async () => {
    let generation = "1";
    let resolve!: (v: unknown) => void;
    const transport = {
      consume: vi.fn(() => new Promise<unknown>((r) => (resolve = r))),
      read: vi.fn(),
    };
    const port = new DirectNativeCommandPort(transport, () => ({
      principalScope: scope,
      generation,
    }));
    const intent = port.makeConsumeIntent(selected, "d".repeat(64))!,
      pointer = port.prepare(intent);
    const pending = port.submit(pointer, intent, new AbortController().signal);
    generation = "2";
    resolve(result(true));
    expect((await pending).disposition).toBe("unknown");
    transport.consume.mockImplementationOnce(async () => ({
      ...result(true),
      result: { ...result().result, result_digest: "e".repeat(64) },
    }));
    const next = port.makeConsumeIntent(selected, "d".repeat(64))!;
    expect(
      (
        await port.submit(
          port.prepare(next),
          next,
          new AbortController().signal,
        )
      ).disposition,
    ).toBe("unknown");
  });
});
