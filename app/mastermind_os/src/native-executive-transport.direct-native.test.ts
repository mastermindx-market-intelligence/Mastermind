import { describe, expect, it, vi } from "vitest";
import { createNativeExecutiveTransport } from "./native-executive-transport";
import { createNativeClient } from "./host";

const selection = { work_ref: "WS:H2", job_id: "JOB-1", attempt_id: "ATTEMPT-1" };
const consumption = { ...selection, result_digest: "a".repeat(64), operation_key: "ack-original" };
async function fixture() {
  let notify = (_payload: unknown) => {};
  const invoke = vi.fn(async (command: string): Promise<unknown> =>
    command === "executive_auth_status" ? { generation: 3, available: true } : { retained: true });
  const client = await createNativeExecutiveTransport(invoke as never, async (_event, listener) => {
    notify = (payload) => listener({ payload }); return () => {};
  });
  await client.ready;
  return { ...client, invoke, notify: (value: unknown) => notify(value) };
}

describe("native existing direct result and explicit consumption", () => {
  it("maps only fixed native commands with exact arguments and never consumes a read", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    await expect(f.transport.directNative!.read(selection, signal)).resolves.toEqual({ retained: true });
    expect(f.invoke.mock.calls).toEqual([["executive_auth_status"],
      ["executive_direct_native_result", { arguments: selection }]]);
    await f.transport.directNative!.consume(consumption, signal);
    expect(f.invoke.mock.calls[2]).toEqual(["executive_direct_native_consume", { arguments: consumption }]);
  });
  it("rejects unknown selectors and incomplete consumption before invoking native code", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    for (const value of [{ ...selection, operation: "consume" }, { ...selection, job_id: "../foreign" }])
      await expect(f.transport.directNative!.read(value, signal)).rejects.toThrow("DIRECT_SELECTION_INVALID");
    for (const value of [{ ...consumption, attempt_id: null }, { ...consumption, result_digest: "A".repeat(64) },
      { ...consumption, operation_key: "bad/key" }, { ...consumption, principal_scope: "foreign" }])
      await expect(f.transport.directNative!.consume(value as never, signal)).rejects.toThrow("DIRECT_SELECTION_INVALID");
    expect(f.invoke.mock.calls).toEqual([["executive_auth_status"]]);
  });
  it.each(["read", "consume"] as const)("fences a pending %s on logout and observes its late result without retry", async (method) => {
    const f = await fixture(); let resolve!: (value: unknown) => void;
    f.invoke.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const pending = method === "read" ? f.transport.directNative!.read(selection, new AbortController().signal)
      : f.transport.directNative!.consume(consumption, new AbortController().signal);
    const rejected = expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.invalidate(); await rejected; resolve({ late: true }); await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
    f.notify({ generation: 3, available: true });
    expect(f.transport.available()).toBe(false);
  });
  it.each(["read", "consume"] as const)("honors caller abort of %s without dispatch replay or fabricated cancellation", async (method) => {
    const f = await fixture(), controller = new AbortController();
    let resolve!: (value: unknown) => void;
    f.invoke.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const pending = method === "read" ? f.transport.directNative!.read(selection, controller.signal)
      : f.transport.directNative!.consume(consumption, controller.signal);
    const rejected = expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    controller.abort(); await rejected; resolve({ late: true }); await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
  });
  it("uses the same private epoch through the real native client composition", async () => {
    const invoke = vi.fn(async (command: string) => command === "executive_auth_status"
      ? { generation: 1, available: true } : command === "auth_status"
        ? { status: "signed_in", reason: null, acquisition: true, content: true } : { retained: true });
    const client = await createNativeClient(invoke as never, async () => () => {});
    await Promise.resolve();
    await client.executive!.directNative!.read(selection, new AbortController().signal);
    expect(invoke).toHaveBeenCalledWith("executive_direct_native_result", { arguments: selection });
    expect(invoke.mock.calls.map(([command]) => command)).not.toContain("executive_direct_native_consume");
  });
  it("maps correction inspect and exact fenced request without inventing terminal consumption", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    const inspect = { operation: "inspect", ...selection };
    const request = { operation: "request", ...selection, fence_generation: 2, operation_key: "cancel-original" };
    await f.transport.directNative.correction(inspect, signal);
    f.invoke.mockResolvedValueOnce({ error: { code: "effect_unknown" } });
    await expect(f.transport.directNative.correction(request, signal)).resolves.toEqual({ error: { code: "effect_unknown" } });
    expect(f.invoke.mock.calls.slice(1)).toEqual([
      ["executive_direct_correction", { arguments: inspect }],
      ["executive_direct_correction", { arguments: request }],
    ]);
    expect(f.invoke.mock.calls.map(([command]) => command)).not.toContain("executive_direct_native_consume");
  });
  it("refuses correction mutation fields in inspect and invalid fences before native dispatch", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    const request = { operation: "request", ...selection, fence_generation: 1, operation_key: "cancel-original" };
    for (const value of [{ operation: "inspect", ...selection, fence_generation: 1 },
      { ...request, fence_generation: 0 }, { ...request, fence_generation: 1.5 },
      { ...request, attempt_id: null }, { ...request, operation_key: "bad/key" },
      { ...request, operation: "consume" }, { ...request, principal_scope: "foreign" }])
      await expect(f.transport.directNative.correction(value, signal)).rejects.toThrow("DIRECT_SELECTION_INVALID");
    expect(f.invoke.mock.calls).toEqual([["executive_auth_status"]]);
  });
});
