import { describe, expect, it, vi } from "vitest";
import { createNativeExecutiveTransport } from "./native-executive-transport";
const deferred = () => { let resolve!: (x: unknown) => void; let reject!: (x: unknown) => void;
  const promise = new Promise<unknown>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
async function fixture() {
  let notify = (_raw: unknown) => {};
  const invoke = vi.fn(async (command: string, _args?: Record<string, unknown>): Promise<unknown> =>
    command === "executive_auth_status" ? { generation: 3, available: true } : { ok: true });
  const created = await createNativeExecutiveTransport(invoke as never, async (event, callback) => {
    expect(event).toBe("mastermind-executive-auth-state"); notify = (raw) => callback({ payload: raw }); return () => {};
  });
  await created.ready;
  return { ...created, invoke, notify: (raw: unknown) => notify(raw) };
}
describe("native fixed Executive bridge", () => {
  it("maps only fixed commands/arguments without passing a bearer or resource", async () => {
    const f = await fixture(), signal = new AbortController().signal;
    await f.transport.context(signal);
    await f.transport.submit({ goal: "fixture" }, signal);
    await f.transport.status({ intent_id: "auto-original" }, signal);
    expect(f.invoke.mock.calls).toEqual([
      ["executive_auth_status"], ["executive_context", undefined],
      ["executive_submit", { arguments: { goal: "fixture" } }],
      ["executive_status", { intentId: "auto-original" }],
    ]);
  });
  it.each(["context", "submit", "status"] as const)("sign-out settles a stalled %s locally and discards its late reply without retry", async (method) => {
    const f = await fixture(), late = deferred(), signal = new AbortController().signal;
    f.invoke.mockReturnValueOnce(late.promise);
    const pending = method === "context" ? f.transport.context(signal) : method === "submit"
      ? f.transport.submit({ operation_key: "original" }, signal) : f.transport.status({ intent_id: "auto-original" }, signal);
    const held = expect(pending).rejects.toThrow("EXECUTIVE_AUTH_CHANGED");
    f.invalidate(); await held; late.resolve({ ok: true, foreign: true }); await Promise.resolve();
    expect(f.invoke).toHaveBeenCalledTimes(2);
    expect(f.transport.available()).toBe(false);
    f.notify({ generation: 3, available: true }); expect(f.transport.available()).toBe(false);
    f.notify({ generation: 4, available: true }); expect(f.transport.available()).toBe(true);
  });
  it("rejects malformed/regressing status, propagates private generations, and never exposes token fields", async () => {
    const f = await fixture(), first = f.transport.authGeneration();
    f.notify({ generation: 4, available: true });
    expect(f.transport.authGeneration()).toBeGreaterThan(first);
    f.notify({ generation: 3, available: false }); expect(f.transport.available()).toBe(true);
    f.notify({ generation: 4, available: true, token: "private" }); expect(f.transport.available()).toBe(false);
    f.notify({ generation: 4, available: true }); expect(f.transport.available()).toBe(false);
    f.notify({ generation: 5, available: true }); expect(f.transport.available()).toBe(true);
  });
  it("an initially missing command leaves Executive unavailable", async () => {
    const invoke = vi.fn(async () => { throw new Error("native missing"); });
    const f = await createNativeExecutiveTransport(invoke as never, async () => () => {});
    expect(f.transport.available()).toBe(false);
    await expect(f.transport.context(new AbortController().signal)).rejects.toThrow("EXECUTIVE_UNAVAILABLE");
    expect(invoke).toHaveBeenCalledTimes(1);
  });
});
