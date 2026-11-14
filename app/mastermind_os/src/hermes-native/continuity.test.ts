import { describe, expect, it } from "vitest";
import {
  classifyContinuity, freshSendAllowed, interventions, permittedContinuations,
} from "./continuity";

const pending = { kind: "send" as const, sessionId: "original-session", requestId: "a".repeat(32) };
const session = (over: Record<string, unknown> = {}) => ({
  id: "original-session", storedId: "original-session", title: "Original", requestedModel: "configured",
  canSend: true, toolAccess: "NONE" as const, running: false, executionGeneration: 1,
  messageCount: 0, messages: [], historyTruncated: false, pending: [], promptsPending: false, ...over,
});
const view = (over: Record<string, unknown> = {}) => ({
  schema: "mastermind.hermes_native_view.v1", state: "READY", operation: "read",
  authGeneration: 7, capabilities: ["native_chat", "native_history", "admission_recovery"],
  delegation: "NOT_ENABLED", retryAllowed: false, session: session(), ...over,
});
const receipt = (over: Record<string, unknown> = {}) => ({
  id: "admission-1", sessionId: "original-session", status: "terminal", sequence: 1,
  outcome: "completed", executionGeneration: 1, ...over,
});

describe("continuity classification", () => {
  it("keeps the five distinguished failure families apart (error-code inputs)", () => {
    expect(classifyContinuity({ error: { message: "NATIVE_SESSION_BUSY" } }))
      .toEqual({ kind: "gateway_busy", sessionId: null, reason: "session_busy" });
    expect(classifyContinuity({ error: { message: "NATIVE_PROMPT_PENDING" } }).reason).toBe("prompt_pending");
    expect(classifyContinuity({ error: { message: "NATIVE_BUSY" } }).reason).toBe("port_busy");
    expect(classifyContinuity({ error: { message: "NATIVE_CLIENT_UNAVAILABLE" } }))
      .toEqual({ kind: "viewer_disconnected", sessionId: null, detail: "client_unavailable" });
    expect(classifyContinuity({ error: { message: "NATIVE_PLATFORM_UNAVAILABLE" } }).detail)
      .toBe("platform_unavailable");
    expect(classifyContinuity({ error: { message: "AUTHENTICATION_CHANGED" } }))
      .toEqual({ kind: "auth_changed" });
  });
  it("an unknown error with a pending mutation is effect-unknown; without one it is unclassified", () => {
    expect(classifyContinuity({ error: { message: "SOMETHING_ELSE" }, pending }))
      .toEqual({ kind: "effect_unknown", pending });
    expect(classifyContinuity({ error: { message: "SOMETHING_ELSE" } }))
      .toEqual({ kind: "unclassified", code: "SOMETHING_ELSE" });
    expect(classifyContinuity({ error: { message: "SOMETHING_ELSE" }, pending, view: view() }))
      .toEqual({ kind: "effect_unknown", pending });
  });
  it("terminal failed + provider 429/quota is model_limited and never auto-retries", () => {
    for (const failureReason of ["provider_rate_limit", "provider_quota_limit"] as const) {
      const state = classifyContinuity({ view: view({ state: "ADMITTED", operation: "send",
        receipt: receipt({ status: "terminal", outcome: "failed", failureReason }) }) });
      expect(state).toEqual({ kind: "model_limited", sessionId: "original-session",
        admissionId: "admission-1", failureReason, retryPolicy: "never_auto" });
      expect(permittedContinuations(state).map(c => c.operation)).toEqual([{ operation: "read", sessionId: "original-session" }]);
      expect(freshSendAllowed(state)).toBe(false);
    }
  });
  it("other terminal failures stay native_terminal, carrying the typed reason", () => {
    const state = classifyContinuity({ view: view({ state: "ADMITTED", operation: "send",
      receipt: receipt({ outcome: "failed", failureReason: "provider_auth_or_access" }) }) });
    expect(state).toEqual({ kind: "native_terminal", sessionId: "original-session",
      admissionId: "admission-1", outcome: "failed", failureReason: "provider_auth_or_access" });
    const quiet = classifyContinuity({ view: view({ state: "ADMITTED", operation: "send",
      receipt: receipt() }) });
    expect(quiet).toEqual({ kind: "native_terminal", sessionId: "original-session",
      admissionId: "admission-1", outcome: "completed" });
  });
  it("running admissions and busy sessions are turn_running / gateway_busy, never idle", () => {
    for (const status of ["queued", "started", "unknown"] as const) {
      expect(classifyContinuity({ view: view({ state: "ADMITTED", operation: "send",
        receipt: receipt({ status, outcome: null }) }) }))
        .toEqual({ kind: "turn_running", sessionId: "original-session", admissionId: "admission-1", status });
    }
    expect(classifyContinuity({ view: view({ session: session({ running: true }) }) }).kind)
      .toBe("turn_running");
    expect(classifyContinuity({ view: view({ session: session({ pending: [{ id: "adm-9", status: "started" }] }) }) }))
      .toMatchObject({ kind: "turn_running", admissionId: "adm-9" });
    expect(classifyContinuity({ view: view({ session: session({ promptsPending: true }) }) }))
      .toEqual({ kind: "gateway_busy", sessionId: "original-session", reason: "prompt_pending" });
  });
  it("a quiet session is the only idle state — unobserved facts are unclassified", () => {
    expect(classifyContinuity({ view: view() })).toEqual({ kind: "idle", sessionId: "original-session" });
    expect(classifyContinuity({ view: view({ session: { ...session(), running: null, promptsPending: null } }) }))
      .toEqual({ kind: "unclassified", code: "NO_OBSERVATION" });
    expect(classifyContinuity({})).toEqual({ kind: "unclassified", code: "NO_OBSERVATION" });
  });
  it("viewer disconnect and effect-unknown states from view observations", () => {
    expect(classifyContinuity({ view: view({ state: "NOT_SENT", session: undefined }) }))
      .toEqual({ kind: "viewer_disconnected", sessionId: null, detail: "client_unavailable" });
    expect(classifyContinuity({ view: view({ state: "NOT_SENT", code: "NATIVE_CLIENT_INTERRUPTED", session: undefined }) }))
      .toEqual({ kind: "viewer_disconnected", sessionId: null, detail: "host_interrupted" });
    expect(classifyContinuity({ view: view({ state: "EFFECT_UNKNOWN", pendingOperation: pending }) }))
      .toEqual({ kind: "effect_unknown", pending });
    expect(classifyContinuity({ view: view({ state: "EFFECT_UNKNOWN" }) }))
      .toEqual({ kind: "unclassified", code: "EFFECT_UNKNOWN_WITHOUT_POINTER" });
  });
});

describe("permitted continuations", () => {
  it("effect-unknown recovers ONLY by the original operation key — never a resend", () => {
    const state = classifyContinuity({ view: view({ state: "EFFECT_UNKNOWN", pendingOperation: pending }) });
    const continuations = permittedContinuations(state);
    expect(continuations).toHaveLength(1);
    expect(continuations[0].operation).toEqual({ operation: "recover" });
    // the port expands recover with the ORIGINAL requestId+sessionId:
    expect(freshSendAllowed(state)).toBe(false);
    expect(permittedContinuations(state).some(c => c.operation.operation === "send")).toBe(false);
  });
  it("only idle permits a fresh send", () => {
    const idle = classifyContinuity({ view: view() });
    expect(freshSendAllowed(idle)).toBe(true);
    expect(permittedContinuations(idle)).toHaveLength(1); // the read; a send mints a fresh request id
    for (const state of [
      classifyContinuity({ error: { message: "NATIVE_SESSION_BUSY" } }),
      classifyContinuity({ error: { message: "NATIVE_CLIENT_UNAVAILABLE" } }),
      classifyContinuity({ view: view({ state: "ADMITTED", operation: "send", receipt: receipt({ status: "queued", outcome: null }) }) }),
      classifyContinuity({ view: view({ state: "ADMITTED", operation: "send", receipt: receipt() }) }),
      classifyContinuity({ error: { message: "AUTHENTICATION_CHANGED" } }),
      classifyContinuity({ error: { message: "WHATEVER" }, pending }),
      classifyContinuity({}),
    ]) {
      expect(freshSendAllowed(state)).toBe(false);
      expect(permittedContinuations(state).some(c => c.operation.operation === "send")).toBe(false);
    }
  });
  it("auth_changed and unclassified offer no continuation at all", () => {
    expect(permittedContinuations({ kind: "auth_changed" })).toEqual([]);
    expect(permittedContinuations({ kind: "unclassified", code: "X" })).toEqual([]);
  });
  it("stop and steer are honestly not exposed by the native port", () => {
    expect(interventions).toEqual({ stop: "not_exposed_by_native_port", steer: "not_exposed_by_native_port" });
  });
});
