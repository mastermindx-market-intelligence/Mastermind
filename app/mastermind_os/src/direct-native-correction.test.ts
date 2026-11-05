import { describe, it, expect, vi } from "vitest";
import { DirectNativeCommandPort } from "./orchestration/direct-native-command-port";
import {
  decodeDirectCorrection,
  correctionIdentity,
} from "./direct-native-correction";
import { decodeDirectNativeResult } from "./direct-native-result";
const selection = { work_ref: "WS:H7", job_id: "JOB-1", attempt_id: "ATT-1" };
const owner = () => ({ principalScope: "a".repeat(64), generation: "1" });
const response = (
  key: string | null,
  status = "CANCEL_REQUESTED",
  fence = 7,
) => ({
  schema: "mastermind.direct_native_correction.v1",
  selection,
  fence_generation: fence,
  operation_key: key,
  status,
  parent_consumed: false,
});
describe("same original direct Job correction", () => {
  it("one correction request; unknown response reconciles by inspect without resending", async () => {
    let calls = 0;
    const correction = vi.fn(async (request: Record<string, unknown>) => {
      calls++;
      if (request.operation === "request")
        throw Error("response lost after actual commit");
      return response(null);
    });
    const port = new DirectNativeCommandPort(
      { read: vi.fn(), consume: vi.fn(), correction },
      owner,
    );
    const intent = port.makeCorrectionIntent(selection, 7)!,
      pointer = port.prepare(intent),
      signal = new AbortController().signal;
    expect((await port.submit(pointer, intent, signal)).disposition).toBe(
      "unknown",
    );
    expect((await port.readOperation(pointer, signal)).disposition).toBe(
      "accepted",
    );
    expect(calls).toBe(2);
    expect(correction.mock.calls.map(([request]) => request.operation)).toEqual(
      ["request", "inspect"],
    );
  });
  it("different current Attempt/fence and still-running inspection cannot clear pending operation", async () => {
    for (const value of [
      response(null, "RUNNING"),
      response(null, "CANCEL_REQUESTED", 8),
      { ...response(null), selection: { ...selection, attempt_id: "ATT-2" } },
    ]) {
      const port = new DirectNativeCommandPort(
        {
          read: vi.fn(),
          consume: vi.fn(),
          correction: vi.fn(async () => value),
        },
        owner,
      );
      const pointer = port.prepare(port.makeCorrectionIntent(selection, 7)!);
      expect(
        (await port.readOperation(pointer, new AbortController().signal))
          .disposition,
      ).toBe("unknown");
    }
  });
  it("exact pointer captures principal and rejects changed payload", () => {
    const port = new DirectNativeCommandPort(
      { read: vi.fn(), consume: vi.fn(), correction: vi.fn() },
      owner,
    );
    const intent = port.makeCorrectionIntent(selection, 7)!;
    expect(port.prepare(intent)).toEqual(
      correctionIdentity(owner().principalScope, selection, 7),
    );
    expect(() =>
      port.prepare({
        ...intent,
        payload: { ...intent.payload, fence_generation: 8 },
      }),
    ).toThrow();
    expect(
      decodeDirectCorrection(
        { ...response(null), parent_consumed: true },
        selection,
      ),
    ).toBeNull();
  });
  it("typed CANCELLED is separate from successful v1 and remains unconsumed", () => {
    const value = {
      schema: "mastermind.direct_native_result_response.cancelled.v1",
      selection,
      availability: "AVAILABLE",
      reason_codes: [],
      result: {
        terminal_status: "CANCELLED",
        result_digest: "b".repeat(64),
        summary: "Cancelled",
        current_state: "CANCELLED",
        completed_steps: [],
        next_actions: [],
      },
      consumption: { state: "UNCONSUMED", receipt_digest: null },
    };
    expect(
      decodeDirectNativeResult(value, selection)?.result?.terminal_status,
    ).toBe("CANCELLED");
    expect(
      decodeDirectNativeResult(
        { ...value, schema: "mastermind.direct_native_result_response.v1" },
        selection,
      ),
    ).toBeNull();
    expect(
      decodeDirectNativeResult(
        { ...value, result: { ...value.result, terminal_status: "COMPLETED" } },
        selection,
      ),
    ).toBeNull();
  });
});

it.each(["COMPLETED", "FAILED", "LOST", "RATE_LIMITED"])(
  "resolves same-attempt %s by observation without asserting cancellation or sending again",
  async (status) => {
    const correction = vi.fn(async (_request: Record<string, unknown>) =>
      response(null, status),
    );
    const port = new DirectNativeCommandPort(
      { read: vi.fn(), consume: vi.fn(), correction },
      owner,
    );
    const pointer = port.prepare(port.makeCorrectionIntent(selection, 7)!);
    expect(
      (await port.readOperation(pointer, new AbortController().signal))
        .disposition,
    ).toBe("accepted");
    expect(correction.mock.calls).toHaveLength(1);
    expect(correction.mock.calls[0][0].operation).toBe("inspect");
    expect(
      decodeDirectCorrection(response(null, status), selection)?.status,
    ).toBe(status);
  },
);
