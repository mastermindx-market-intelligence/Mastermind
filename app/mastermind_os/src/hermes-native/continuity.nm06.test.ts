/** NM-06 — a stopped gateway is its own continuity state, not busy and not
 *  viewer-disconnected. Mirror of `tests/test_mmos_nm06_gateway_stopped.py`:
 *  the gateway code table classifies both stopped codes into `gateway_stopped`,
 *  the state offers only observation (its owner starts the gateway — this port
 *  never restarts, reconnects or remakes it), and it is never effect-unknown
 *  even with a pending pointer. */
import { describe, expect, it } from "vitest";
import { classifyContinuity, freshSendAllowed, permittedContinuations } from "./continuity";

const pending = { kind: "send" as const, sessionId: "original-session", requestId: "b".repeat(32) };
const stoppedOps = new Set(["read", "status"]);
const mutationOps = new Set(["send", "recover", "restart", "reconnect", "remake"]);

describe("NM-06 gateway stopped vs disconnected", () => {
  it("stopped code classifies gateway_stopped with reason", () => {
    const stopped = classifyContinuity({ error: { message: "NATIVE_GATEWAY_STOPPED" } });
    expect(stopped).toEqual({ kind: "gateway_stopped", reason: "gateway_not_running" });
    // The alias code in the closed table maps to the same typed state.
    const alias = classifyContinuity({ error: { message: "NATIVE_GATEWAY_NOT_RUNNING" } });
    expect(alias).toEqual({ kind: "gateway_stopped", reason: "gateway_not_running" });
  });

  it("stopped, busy and viewer codes yield three distinct states", () => {
    const stopped = classifyContinuity({ error: { message: "NATIVE_GATEWAY_STOPPED" } }).kind;
    const busy = classifyContinuity({ error: { message: "NATIVE_SESSION_BUSY" } }).kind;
    const disconnected = classifyContinuity({ error: { message: "NATIVE_CLIENT_UNAVAILABLE" } }).kind;
    expect(new Set([stopped, busy, disconnected]).size).toBe(3);
    expect([stopped, busy, disconnected]).toEqual(["gateway_stopped", "gateway_busy", "viewer_disconnected"]);
  });

  it("stopped permits only read/status operations and never a fresh send", () => {
    const stopped = classifyContinuity({ error: { message: "NATIVE_GATEWAY_STOPPED" } });
    const continuations = permittedContinuations(stopped);
    expect(continuations.length).toBeGreaterThan(0); // a stopped gateway still offers observation
    for (const row of continuations) {
      expect(stoppedOps.has(row.operation.operation)).toBe(true);
      expect(mutationOps.has(row.operation.operation)).toBe(false);
    }
    expect(freshSendAllowed(stopped)).toBe(false);
  });

  it("stopped code beats the pending fallback and is never effect_unknown", () => {
    // A pending pointer must not turn a stopped gateway into effect-unknown:
    // there is nothing in flight to reconcile while the gateway is down.
    expect(classifyContinuity({ error: { message: "NATIVE_GATEWAY_STOPPED" }, pending }))
      .toEqual({ kind: "gateway_stopped", reason: "gateway_not_running" });
    expect(classifyContinuity({ error: { message: "NATIVE_GATEWAY_NOT_RUNNING" }, pending }))
      .toEqual({ kind: "gateway_stopped", reason: "gateway_not_running" });
  });

  it("a REFUSED view carrying a stopped code is gateway_stopped, not unclassified", () => {
    for (const code of ["NATIVE_GATEWAY_STOPPED", "NATIVE_GATEWAY_NOT_RUNNING"]) {
      expect(classifyContinuity({
        view: { schema: "mastermind.hermes_native_view.v1", state: "REFUSED", operation: "send",
          authGeneration: 7, capabilities: [], delegation: "NOT_ENABLED", retryAllowed: false, code },
      })).toEqual({ kind: "gateway_stopped", reason: "gateway_not_running" });
    }
  });

  it("existing code table rows are unchanged", () => {
    // Regression pins: the NM-06 fix adds a state without reclassifying any
    // previously-mapped code.
    const pins: [string, string][] = [
      ["NATIVE_SESSION_BUSY", "gateway_busy"],
      ["NATIVE_PROMPT_PENDING", "gateway_busy"],
      ["NATIVE_BUSY", "gateway_busy"],
      ["NATIVE_CLIENT_INTERRUPTED", "viewer_disconnected"],
      ["NATIVE_CLIENT_UNAVAILABLE", "viewer_disconnected"],
      ["NATIVE_PIPE_UNAVAILABLE", "viewer_disconnected"],
      ["NATIVE_PLATFORM_UNAVAILABLE", "viewer_disconnected"],
      ["AUTHENTICATION_CHANGED", "auth_changed"],
      ["NATIVE_AUTH_NOT_DISPATCHED", "auth_changed"],
      ["SOMETHING_ELSE", "unclassified"],
    ];
    for (const [code, expected] of pins) {
      expect(classifyContinuity({ error: { message: code } }).kind).toBe(expected);
    }
    // Unknown codes with a pending pointer stay effect-unknown (unchanged).
    expect(classifyContinuity({ error: { message: "SOMETHING_ELSE" }, pending }))
      .toEqual({ kind: "effect_unknown", pending });
  });
});
