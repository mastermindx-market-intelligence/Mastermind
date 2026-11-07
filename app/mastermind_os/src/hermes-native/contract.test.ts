import { describe, expect, it } from "vitest";
import { parseNativeView } from "./contract";

export const ready = () => ({
  schema: "mastermind.hermes_native_view.v1", state: "READY", operation: "status",
  authGeneration: 7, capabilities: ["native_chat", "native_history", "admission_recovery"],
  delegation: "NOT_ENABLED", retryAllowed: false,
  runtime: { protocol: 1, instanceId: "native-one", authorityEpoch: 2, version: "0.23.0", sourceRevision: "a".repeat(40) },
});
export const session = () => ({
  id: "native-session-one", storedId: "native-session-one", title: "Meta-CEO conversation",
  requestedModel: "configured-only", canSend: true, toolAccess: "CAPACITY_READ_ONLY",
  running: false, executionGeneration: 0, messageCount: 2, historyTruncated: false,
  messages: [{ role: "user", text: "  original\n 中文\t" }, { role: "assistant", text: "<script>not HTML</script>" }],
  pending: [], promptsPending: false,
});

describe("native Hermes presentation contract", () => {
  it("accepts a bounded runtime observation without turning it into company admission", () => {
    const view = parseNativeView(ready());
    expect(view.state).toBe("READY");
    expect(view.delegation).toBe("NOT_ENABLED");
    expect(view.runtime?.sourceRevision).toBe("a".repeat(40));
  });
  it("preserves original Unicode and whitespace as text, not HTML", () => {
    const view = parseNativeView({ ...ready(), operation: "read", session: session() });
    expect(view.session?.messages[0].text).toBe("  original\n 中文\t");
    expect(view.session?.messages[1].text).toBe("<script>not HTML</script>");
    expect(view.session?.requestedModel).toBe("configured-only");
  });
  it("accepts the qualified advisory scope while rejecting unbounded OMH execution", () => {
    const result = parseNativeView({ ...ready(), operation: "read",
      session: { ...session(), toolAccess: "ADVISORY_READ_ONLY" } });
    expect(result.session?.canSend).toBe(true);
    expect(result.delegation).toBe("NOT_ENABLED");
    expect(() => parseNativeView({ ...ready(), session: { ...session(), toolAccess: "FULL_OMH" } })).toThrow();
  });
  it("keeps queued, started, unknown and terminal receipts distinct", () => {
    for (const status of ["queued", "started", "unknown", "terminal"]) {
      const view = parseNativeView({ ...ready(), state: "ADMITTED", operation: "send", receipt: {
        id: "admission-one", sessionId: "native-session-one", sequence: 1,
        status, outcome: null, executionGeneration: null,
      } });
      expect(view.receipt?.status).toBe(status);
    }
  });
  it("rejects authority, credential and arbitrary native transport material", () => {
    for (const key of ["token", "apiOrigin", "profile", "accepted", "jobId"]) {
      expect(() => parseNativeView({ ...ready(), [key]: "not allowed" })).toThrow();
    }
    expect(() => parseNativeView({ ...ready(), delegation: "ENABLED" })).toThrow();
    expect(() => parseNativeView({ ...ready(), retryAllowed: true })).toThrow();
  });
  it("rejects malformed scope, history, generation and policy projections", () => {
    for (const change of [{ schema: "other" }, { authGeneration: -1 }, { authGeneration: NaN },
      { state: "ACCEPTED" }, { capabilities: ["company_admission"] }, { runtime: { ...ready().runtime, protocol: 2 } }]) {
      expect(() => parseNativeView({ ...ready(), ...change })).toThrow();
    }
    for (const change of [{ id: "../other" }, { toolAccess: "UNQUALIFIED", canSend: true },
      { messages: [{ role: "system", text: "private" }] }, { messages: Array.from({ length: 101 }, () => ({ role: "user", text: "x" })) }]) {
      expect(() => parseNativeView({ ...ready(), session: { ...session(), ...change } })).toThrow();
    }
  });
  it("does not erase uncertainty or manufacture a retry permission", () => {
    const view = parseNativeView({ ...ready(), state: "EFFECT_UNKNOWN", operation: "send", code: "NATIVE_OUTCOME_UNKNOWN" });
    expect(view.state).toBe("EFFECT_UNKNOWN");
    expect(view.retryAllowed).toBe(false);
  });
});

describe("stored native history eligibility", () => {
  const stored = () => ({ ...session(), canSend: false, toolAccess: "UNQUALIFIED",
    sendCheckRequired: true, running: null, promptsPending: null });
  it("accepts owned stored history without claiming live send scope", () => {
    const observed = parseNativeView({ ...ready(), operation: "read", session: stored() }).session!;
    expect(observed.sendCheckRequired).toBe(true);
    expect(observed.canSend).toBe(false);
    expect(observed.running).toBeNull();
    expect(observed.promptsPending).toBeNull();
    expect(observed.messages).toEqual(session().messages);
    expect(parseNativeView({ ...ready(), operation: "list",
      sessions: [{ id: "original", title: "Saved", running: null, messageCount: 2 }] }).sessions?.[0].running).toBeNull();
  });
  it("rejects mixing an unobserved snapshot with a claimed live permission", () => {
    for (const change of [{ canSend: true }, { toolAccess: "NONE" }, { running: false },
      { promptsPending: false }, { sendCheckRequired: false }]) {
      expect(() => parseNativeView({ ...ready(), session: { ...stored(), ...change } })).toThrow();
    }
    expect(() => parseNativeView({ ...ready(), session: { ...session(), running: null } })).toThrow();
    expect(() => parseNativeView({ ...ready(), session: { ...session(), promptsPending: null } })).toThrow();
  });
});
