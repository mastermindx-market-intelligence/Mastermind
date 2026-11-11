import { describe, expect, it, vi } from "vitest";
import { createNativeExecutiveTransport } from "./native-executive-transport";

const selected = { work_ref: "WS:NATIVE-H2", job_id: "JOB-original", attempt_id: "ATT-original" };
const consumed = { ...selected, result_digest: "a".repeat(64), operation_key: "mmos-consume-original" };
async function fixture() {
  let notify = (_raw: unknown) => {};
  const invoke = vi.fn(async (command: string, _args?: Record<string, unknown>): Promise<unknown> =>
    command === "executive_auth_status" ? { generation: 3, available: true } : { retained: true });
  const native = await createNativeExecutiveTransport(invoke as never, async (_event, callback) => {
    notify = (raw) => callback({ payload: raw });
    return () => {};
  });
  await native.ready;
  return { ...native, invoke, notify: (raw: unknown) => notify(raw) };
}

describe("native direct-result transport", () => {
  it("maps closed original selectors to two fixed commands without a bearer, URL, or source", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    expect(f.transport.directNative).toBeDefined();
    await f.transport.directNative!.read({ ...selected, attempt_id: null }, signal);
    await f.transport.directNative!.consume(consumed, signal);
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"],
      ["executive_direct_native_result", { arguments: { ...selected, attempt_id: null } }],
      ["executive_direct_native_consume", { arguments: consumed }],
    ]);
  });

  it.each([
    ["read", { ...selected, source_path: "/caller/selected" }],
    ["read", { ...selected, job_id: "JOB-original/another" }],
    ["read", { ...selected, work_ref: "WS:NATIVE-H2\n" }],
    ["read", { ...selected, attempt_id: undefined }],
    ["consume", { ...consumed, attempt_id: null }],
    ["consume", { ...consumed, result_digest: "A".repeat(64) }],
    ["consume", { ...consumed, operation_key: "caller/path" }],
    ["consume", { ...consumed, resource: "https://caller.invalid" }],
  ] as const)("refuses malformed %s before any native dispatch", async (method, input) => {
    const f = await fixture();
    expect(f.transport.directNative).toBeDefined();
    await expect(f.transport.directNative![method](input as never, new AbortController().signal))
      .rejects.toThrow("DIRECT_SELECTION_INVALID");
    expect(f.invoke.mock.calls).toEqual([["executive_auth_status"]]);
  });

  it.each(["read", "consume"] as const)("discards a stalled %s after an actual native auth generation change without replay", async (method) => {
    const f = await fixture();
    expect(f.transport.directNative).toBeDefined();
    let finish!: (value: unknown) => void;
    f.invoke.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const request = method === "read" ? selected : consumed;
    const pending = f.transport.directNative![method](request as never, new AbortController().signal);
    const rejected = expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.notify({ generation: 4, available: true });
    await rejected;
    finish({ retained: "late old generation" });
    await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
    expect(f.transport.available()).toBe(true);
  });
});
