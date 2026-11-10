// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import type { DurablePendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { createNativeHermesPort } from "./native-port";
import { nativePendingPointer } from "./pending-pointer";

const scope = "e".repeat(64);
const original = { kind: "send" as const, sessionId: "original-session", requestId: "a".repeat(32) };
const rosterPayload = {
  schema: "mastermind.team_roster/v1", generatedAt: "2026-11-09T12:00:00Z", host: "m2studio",
  bots: [{
    id: "engineering", displayName: "Engineering", role: "operator",
    profilePath: "/Users/operator/.hermes/profiles/engineering", managed: true, host: "m2studio",
    gateway: { observed: true, source: "gateway_lock", instanceId: "gw-1", authorityEpoch: 4,
      codeVersion: "0.23.0", pid: 1234, state: "serving" },
    readiness: "ready", readinessReason: "GATEWAY_LOCK_VERIFIED",
    lastActivity: "2026-11-09T10:00:00Z", activitySummary: "ran the WO-19 dry-run",
  }],
};
function baseView(extra: Record<string, unknown> = {}) {
  return {
    schema: "mastermind.hermes_native_view.v1", state: "READY", operation: "status",
    authGeneration: 7, capabilities: ["native_chat", "native_history", "admission_recovery"],
    delegation: "NOT_ENABLED", retryAllowed: false,
    runtime: { protocol: 1, instanceId: "native", authorityEpoch: 1, version: "0.23.0",
      sourceRevision: "b".repeat(40), localScope: scope }, ...extra,
  };
}
function memoryStore(held: unknown = null): DurablePendingPointerStore & { writes: number } {
  let pointer = held;
  return {
    writes: 0,
    async read() { return pointer; },
    async reserve(_scope: string, next: unknown) {
      if (pointer !== null) return { reserved: false, pointer };
      pointer = next; this.writes += 1;
      return { reserved: true, pointer: next };
    },
    async clearIfEqual(_scope: string, candidate: unknown) {
      if (pointer !== candidate) return false;
      pointer = null; this.writes += 1;
      return true;
    },
  } as unknown as DurablePendingPointerStore & { writes: number };
}

describe("team_roster through the native port", () => {
  it("flows as a read-only operation after one status, with the roster parsed", async () => {
    const store = memoryStore();
    const invoke = vi.fn(async (_command: string, args: Record<string, unknown>) => {
      const request = args.request as { operation: string };
      if (request.operation === "team_roster") return baseView({ operation: "team_roster", roster: rosterPayload });
      return baseView();
    });
    const port = createNativeHermesPort({ invoke, available: () => true, store });
    await port.request({ operation: "status" });
    const result = await port.request({ operation: "team_roster" });
    expect(invoke).toHaveBeenLastCalledWith("hermes_native",
      { request: { operation: "team_roster" }, expectedAuthGeneration: 7 });
    expect(result.state).toBe("READY");
    expect(result.roster?.schema).toBe("mastermind.team_roster/v1");
    expect(result.roster?.bots[0].id).toBe("engineering");
    expect(result.pendingOperation).toBeNull();
    expect(store.writes).toBe(0); // read-only: no reservation, no settlement
  });
  it("never dispatches team_roster before a status established the runtime scope", async () => {
    const port = createNativeHermesPort({
      invoke: async () => baseView(), available: () => true, store: memoryStore() });
    await expect(port.request({ operation: "team_roster" })).rejects.toThrow("NATIVE_RECOVERY_UNAVAILABLE");
  });
  it("a roster response that does not echo the team_roster operation is invalid", async () => {
    for (const bad of [
      baseView({ operation: "status", roster: rosterPayload }), // roster off-operation
      baseView({ operation: "list" }), // wrong echo
    ]) {
      const port = createNativeHermesPort({
        invoke: async (_c: string, args: Record<string, unknown>) =>
          (args.request as { operation: string }).operation === "team_roster" ? bad : baseView(),
        available: () => true, store: memoryStore() });
      await port.request({ operation: "status" });
      await expect(port.request({ operation: "team_roster" })).rejects.toThrow("NATIVE_RESPONSE_INVALID");
    }
  });
  it("a malformed roster payload is rejected fail-closed, not rendered", async () => {
    const port = createNativeHermesPort({
      invoke: async (_c: string, args: Record<string, unknown>) =>
        (args.request as { operation: string }).operation === "team_roster"
          ? baseView({ operation: "team_roster", roster: { ...rosterPayload, host: "" } })
          : baseView(),
      available: () => true, store: memoryStore() });
    await port.request({ operation: "status" });
    await expect(port.request({ operation: "team_roster" })).rejects.toThrow("NATIVE_RESPONSE_INVALID");
  });
  it("a live recovery hold does not block the read-only roster, and the view carries the pending pointer", async () => {
    const held = nativePendingPointer(original);
    const store = memoryStore(held);
    const port = createNativeHermesPort({
      invoke: async (_c: string, args: Record<string, unknown>) =>
        (args.request as { operation: string }).operation === "team_roster"
          ? baseView({ operation: "team_roster", roster: rosterPayload })
          : baseView(),
      available: () => true, store });
    await port.request({ operation: "status" });
    const result = await port.request({ operation: "team_roster" });
    expect(result.roster?.bots).toHaveLength(1);
    expect(result.pendingOperation).toEqual(original);
    expect(store.writes).toBe(0); // the hold is untouched by a roster read
  });
  it("an auth-generation change on the roster response flips auth_changed and clears the session", async () => {
    const port = createNativeHermesPort({
      invoke: async (_c: string, args: Record<string, unknown>) =>
        (args.request as { operation: string }).operation === "team_roster"
          ? baseView({ operation: "team_roster", roster: rosterPayload, authGeneration: 8 })
          : baseView(),
      available: () => true, store: memoryStore() });
    await port.request({ operation: "status" });
    await expect(port.request({ operation: "team_roster" })).rejects.toThrow("AUTHENTICATION_CHANGED");
  });
});
