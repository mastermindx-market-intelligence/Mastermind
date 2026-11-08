import { describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { createNativeHermesPort } from "./native-port";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { nativePendingPointer } from "./pending-pointer";
import type { NativeLiveFrame } from "./live-stream";

const scope = "a".repeat(64);
const target = { sessionId: "logical-session", admissionId: "original", authorityEpoch: 2, executionGeneration: 3 };
const frame = (extra: Partial<NativeLiveFrame> = {}): NativeLiveFrame => ({ ...target,
  schema: "mastermind.hermes_native_stream.v1", authGeneration: 7, replayEpoch: "epoch", sequence: 1,
  state: "live", text: "Actual native text", activity: "responding", code: null, ...extra });
async function fixture() {
  let generation = 7;
  let channel: { onmessage: (value: unknown) => void };
  const store = createIndexedDbPendingPointerStore(new IDBFactory());
  const invoke = vi.fn(async (command: string, args: Record<string, unknown>) => {
    if (command === "hermes_native_observe") return new Promise(() => {});
    if (command === "hermes_native_unobserve") return;
    const operation = (args.request as { operation: string }).operation;
    return { schema: "mastermind.hermes_native_view.v1", state: "READY", operation,
      authGeneration: generation, capabilities: [], delegation: "NOT_ENABLED", retryAllowed: false,
      runtime: { protocol: 1, instanceId: "instance", authorityEpoch: 2, version: "0.23.0", sourceRevision: "a".repeat(40), localScope: scope },
      ...(operation === "list" ? { sessions: [] } : {}) };
  });
  const port = createNativeHermesPort({ invoke, available: () => true, store,
    channel: receive => channel = { onmessage: receive } });
  await port.request({ operation: "status" });
  return { port, store, invoke, emit: (value: unknown) => channel.onmessage(value), changeAuth: () => { generation++; } };
}

describe("native foreground stream port", () => {
  it("observes without occupying send/read serialization and disposes only its view", async () => {
    const f = await fixture(), receive = vi.fn(), fail = vi.fn();
    const dispose = f.port.observe!(target, receive, fail);
    await expect(f.port.request({ operation: "list" })).resolves.toMatchObject({ state: "READY" });
    f.emit(frame()); expect(receive).toHaveBeenCalledTimes(1);
    dispose(); f.emit(frame({ sequence: 2 }));
    expect(receive).toHaveBeenCalledTimes(1);
    expect(f.invoke.mock.calls.filter(([command]) => command === "hermes_native_unobserve")).toHaveLength(1);
    expect(f.invoke.mock.calls.some(([, args]) => ["send", "stop", "stop_send"].includes((args.request as {operation?: string} | undefined)?.operation ?? ""))).toBe(false);
  });
  it("drops foreign admission text and closes that view before rendering", async () => {
    const f = await fixture(), receive = vi.fn(), fail = vi.fn();
    f.port.observe!(target, receive, fail); f.emit(frame({ admissionId: "foreign" }));
    expect(receive).not.toHaveBeenCalled(); expect(fail).toHaveBeenCalledWith("NATIVE_STREAM_INVALID");
    expect(f.invoke.mock.calls.at(-1)?.[0]).toBe("hermes_native_unobserve");
  });
  it("does not settle a durable request from a stream completion", async () => {
    const f = await fixture(), receive = vi.fn();
    const pointer = nativePendingPointer({ kind: "send", sessionId: target.sessionId, requestId: "a".repeat(32) });
    await f.store.reserve(scope, pointer);
    f.port.observe!(target, receive, vi.fn()); f.emit(frame({ state: "complete" }));
    expect(receive).toHaveBeenCalledTimes(1);
    expect(await f.store.read(scope)).toEqual(pointer);
  });
  it("drops private text after a changed sign-in", async () => {
    const f = await fixture(), receive = vi.fn(), fail = vi.fn();
    f.port.observe!(target, receive, fail);
    f.changeAuth(); await f.port.request({ operation: "status" }); f.emit(frame());
    expect(receive).not.toHaveBeenCalled(); expect(fail).toHaveBeenCalledWith("AUTHENTICATION_CHANGED");
  });
});
