import { afterEach, describe, expect, it, vi } from "vitest";
import { closedReadFailurePhase, decodeMissionDiagnostics } from "./diagnostic-state";
import { createOsExecutiveHost, type OsExecutiveTransport } from "./orchestration/os-executive-host";

const disposals: Array<() => void> = [];
afterEach(() => { disposals.splice(0).forEach((dispose) => dispose()); vi.useRealTimers(); });
const snapshot = () => ({ hostKind: "native", launchConfigured: true,
  frontendResourceConfigured: true, nativeResourceConfigured: null,
  acquisitionAvailable: true, contentAvailable: false, executiveAvailable: null,
  executiveContextPhase: "not_requested" });
function fixture(expiry: number, available = true, diagnostics?: OsExecutiveTransport["diagnostics"]) {
  let now = 1_000_000, generation = 1;
  const context = vi.fn(async () => ({ schema: "mastermind.os.executive.owner_context.v1",
    principal_scope: "a".repeat(64), verified_expiry: expiry,
    profile: { name: "web_ceo_v3", server_version: "1.5.0" } }));
  const transport: OsExecutiveTransport = { available: () => available,
    authGeneration: () => generation, context,
    subscribe: () => () => {}, submit: vi.fn(), status: vi.fn(), ...(diagnostics ? { diagnostics } : {}) };
  const host = createOsExecutiveHost({ workstream: "WS:DIAGNOSTIC-ONLY", priority: 0,
    projects: [{ ref: "fixture", label: "Fixture" }], profiles: [{ ref: "research_only", label: "Fixture" }] },
    transport, { read: async () => null, reserve: async () => ({ reserved: true as const }), clearIfEqual: async () => true }, () => now);
  disposals.push(host.dispose);
  return { host, transport, context, advanceClock(ms: number) { now += ms; }, drift() { generation++; } };
}

describe("diagnostic boundaries preserve existing authority and unknowns", () => {
  it("does not evaluate accessor fields or Error message getters", () => {
    let reads = 0;
    const raw = snapshot();
    Object.defineProperty(raw, "executiveAvailable", { enumerable: true,
      get() { reads++; throw new Error("PRIVATE-CREDENTIAL-CONTENT"); } });
    expect(decodeMissionDiagnostics(raw)).toBeNull();
    const reason = new Error("untrusted");
    Object.defineProperty(reason, "message", { get() { reads++; throw new Error("PRIVATE-CREDENTIAL-CONTENT"); } });
    expect(closedReadFailurePhase(reason)).toBe("unknown");
    expect(reads).toBe(0);
  });
  it("recognizes the actual closed Programs decoder failures without copying messages", () => {
    expect(closedReadFailurePhase("PROGRAM_RESPONSE_INVALID")).toBe("invalid_response");
    expect(closedReadFailurePhase(new Error("PROGRAM_OBSERVATION_INVALID"))).toBe("invalid_response");
    expect(closedReadFailurePhase(new Error("PROGRAM_RESPONSE_INVALID PRIVATE"))).toBe("unknown");
  });
  it("does not let a throwing diagnostic hook affect a blocked existing refresh", async () => {
    const f = fixture(2000, false, () => { throw new Error("PRIVATE-DIAGNOSTIC"); });
    await expect(f.host.ready).resolves.toBeUndefined();
    expect(() => f.host.diagnostics()).not.toThrow();
    expect(f.context).not.toHaveBeenCalled();
  });
  it("does not call a clamped future timer actual expiry", async () => {
    vi.useFakeTimers();
    const clamp = 2_147_483_647;
    const f = fixture(Math.ceil((1_000_000 + clamp + 100_000) / 1000));
    await f.host.ready;
    f.advanceClock(clamp);
    await vi.advanceTimersByTimeAsync(clamp);
    expect(f.host.binding.port.context()).toBeNull(); // existing invalidation unchanged
    expect(f.host.diagnostics().contextPhase).toBe("unknown");
    expect(f.context).toHaveBeenCalledTimes(1);
  });
  it("observes actual expiry even if the timer has not yet fired, without a request", async () => {
    vi.useFakeTimers(); const f = fixture(1001); await f.host.ready;
    f.advanceClock(1001);
    expect(f.host.binding.port.context()).toBeNull();
    expect(f.host.diagnostics().contextPhase).toBe("expired");
    expect(f.context).toHaveBeenCalledTimes(1);
  });
  it("does not report ready after an auth-generation drift without an event", async () => {
    const f = fixture(2000); await f.host.ready; f.drift();
    expect(f.host.binding.port.context()).toBeNull();
    expect(f.host.diagnostics().contextPhase).toBe("unknown");
    expect(f.context).toHaveBeenCalledTimes(1);
  });
});
