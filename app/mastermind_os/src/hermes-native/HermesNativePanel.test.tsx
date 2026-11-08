// @vitest-environment jsdom
import React from "react";
import { IDBFactory } from "fake-indexeddb";
import { createNativeHermesPort } from "./native-port";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HermesNativePanel } from "./HermesNativePanel";
import { nativePendingPointer } from "./pending-pointer";
import { parseNativeView, type NativeHermesPort, type NativeOperation } from "./contract";

function view(extra: Record<string, unknown> = {}) {
  return parseNativeView({ schema: "mastermind.hermes_native_view.v1", state: "READY", authGeneration: 2,
    capabilities: ["native_chat", "native_history", "admission_recovery"], delegation: "NOT_ENABLED", retryAllowed: false,
    runtime: { protocol: 1, instanceId: "native-one", authorityEpoch: 1, version: "0.23.0", sourceRevision: "a".repeat(40), localScope: "e".repeat(64) }, ...extra });
}
function nativeSession() { return { id: "session-one", storedId: "session-one", title: "Office conversation", requestedModel: "configured-model",
  canSend: true, toolAccess: "CAPACITY_READ_ONLY", running: false, executionGeneration: 0, messageCount: 0,
  messages: [], historyTruncated: false, pending: [], promptsPending: false }; }
function port() {
  return { available: () => true, request: vi.fn(async (request: NativeOperation) => {
    if (request.operation === "create") return view({ operation: "create", state: "OPENED", session: nativeSession() });
    if (request.operation === "read") return view({ operation: "read", session: nativeSession() });
    if (request.operation === "list") return view({ operation: "list", sessions: [] });
    if (request.operation === "send") return view({ operation: "send", state: "ADMITTED", receipt: {
      id: "admission-one", sessionId: "session-one", status: "terminal", sequence: 1, outcome: "completed", executionGeneration: 1 } });
    return view({ operation: "status" });
  }) } satisfies NativeHermesPort;
}
async function openChat(p = port()) {
  render(<HermesNativePanel port={p} locale="en" />);
  fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
  await screen.findByRole("textbox", { name: "Message Hermes" });
  return p;
}
afterEach(cleanup);

describe("thin native Hermes Office", () => {
  it("never contacts loopback or invokes the native host in a web-only client", () => {
    const p = port(); p.available = () => false;
    render(<HermesNativePanel port={p} locale="en" />);
    expect(screen.getByText(/desktop app on the Mac running Hermes/i)).toBeTruthy();
    expect(p.request).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Connect local Hermes" })).toBeNull();
  });
  it("opens an actual native conversation and labels the limited tool scope", async () => {
    const p = await openChat();
    expect(p.request.mock.calls.some(([r]) => r.operation === "create" && r.role === "meta-ceo" && /^[a-f0-9]{32}$/.test(r.requestId))).toBe(true);
    expect(screen.getByText(/Capacity catalog and route preview only/i)).toBeTruthy();
    expect(screen.getAllByText(/configured-model/).length).toBeGreaterThan(0);
  });
  it("labels qualified OMH advice without claiming execution or capacity-only scope", async () => {
    const p = port(); const base = p.request.getMockImplementation()!;
    p.request.mockImplementation(async r => r.operation === "create"
      ? view({ state: "OPENED", session: { ...nativeSession(), toolAccess: "ADVISORY_READ_ONLY" } }) : base(r));
    await openChat(p);
    expect(screen.getByText(/Local planning advice and capacity previews/)).toBeTruthy();
    expect(screen.queryByText(/Capacity catalog and route preview only/)).toBeNull();
    expect(screen.getByText(/Worker dispatch is not enabled/)).toBeTruthy();
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(0);
  });
  it("sends original text once even under a rapid second click", async () => {
    const p = await openChat();
    const original = "  Original\n 中文\t";
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: original } });
    const send = screen.getByRole("button", { name: "Send message" });
    fireEvent.click(send); fireEvent.click(send);
    await waitFor(() => expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1));
    expect(p.request.mock.calls.find(([r]) => r.operation === "send")?.[0]).toMatchObject({ text: original, sessionId: "session-one" });
  });
  it("keeps an unknown send held after read-only recovery without replaying", async () => {
    const p = port(); const base = p.request.getMockImplementation()!;
    p.request.mockImplementation(async r => r.operation === "send" ? view({ state: "EFFECT_UNKNOWN", operation: "send", code: "NATIVE_OUTCOME_UNKNOWN" }) : base(r));
    await openChat(p);
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Outcome unknown/);
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await waitFor(() => expect(p.request.mock.calls.some(([r]) => r.operation === "recover")).toBe(true));
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(true);
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);
  });
  it("does not render model content as HTML", async () => {
    const p = port(); const base = p.request.getMockImplementation()!;
    p.request.mockImplementation(async r => r.operation === "create" ? view({ state: "OPENED", session: { ...nativeSession(), messageCount: 1,
      messages: [{ role: "assistant", text: "<img src=x onerror=alert(1)>" }] } }) : base(r));
    await openChat(p);
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(document.querySelector(".hermes-native-panel img")).toBeNull();
  });
  it("clears private conversation state when authentication changes", async () => {
    const p = await openChat();
    p.request.mockResolvedValue(view({ authGeneration: 3, session: nativeSession() }));
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText(/Sign-in changed/);
    expect(screen.queryByRole("textbox", { name: "Message Hermes" })).toBeNull();
  });

  it("reconnects after a proven before-dispatch auth change without inventing an uncertain send", async () => {
    const p = await openChat();
    p.request.mockRejectedValueOnce(new Error("NATIVE_AUTH_NOT_DISPATCHED"));
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Sign-in changed/);
    expect(screen.queryByRole("textbox", { name: "Message Hermes" })).toBeNull();
    expect(screen.queryByText(/Outcome unknown/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(false));
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);
  });

  it("preserves an unsent draft and explains a proven preflight failure without automatic resend", async () => {
    const p = await openChat();
    p.request.mockResolvedValueOnce({ ...view({ operation: "send", state: "NOT_SENT", code: "NATIVE_NOT_SENT" }), pendingOperation: null });
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "  original draft\n 中文" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/The request was not sent/);
    expect((screen.getByRole("textbox", { name: "Message Hermes" }) as HTMLTextAreaElement).value).toBe("  original draft\n 中文");
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(false);
    expect(screen.queryByRole("button", { name: "Check previous request" })).toBeNull();
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);
  });

  it("reopens a lost in-flight send with no automatic replay and settles only its original receipt", async () => {
    const factory = new IDBFactory();
    let loseReply: ((reason: Error) => void) | undefined;
    const invoke = vi.fn(async (_command: string, args: Record<string, unknown>) => {
      const request = args.request as { operation: string; requestId?: string; sessionId?: string };
      if (request.operation === "create") return view({ state: "OPENED", operation: "create", requestId: request.requestId, session: nativeSession() });
      if (request.operation === "send") return await new Promise((_resolve, reject) => { loseReply = reject; });
      if (request.operation === "read") return view({ operation: "read", session: nativeSession() });
      if (request.operation === "recover_send") return view({ state: "ADMITTED", operation: "recover",
        requestId: request.requestId, requestSessionId: request.sessionId,
        receipt: { id: "original-admission", sessionId: "session-one", status: "terminal", sequence: 1,
          outcome: "completed", executionGeneration: 1 } });
      return view({ operation: "status" });
    });
    const makePort = () => createNativeHermesPort({ available: () => true, invoke,
      store: createIndexedDbPendingPointerStore(factory) });
    const first = render(<HermesNativePanel port={makePort()} locale="en" />);
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Message Hermes" }), { target: { value: "original private text" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(loseReply).toBeDefined());
    const originalRequest = invoke.mock.calls.find(([, args]) => (args.request as { operation: string }).operation === "send")![1].request as { requestId: string };
    first.unmount();
    loseReply!(new Error("transport interrupted"));
    render(<HermesNativePanel port={makePort()} locale="en" />);
    expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(true);
    expect(screen.queryByText("original private text")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await screen.findByText(/Outcome unknown/);
    expect(screen.getByText(originalRequest.requestId)).toBeTruthy();
    expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(true);
    expect(invoke.mock.calls.filter(([, args]) => (args.request as { operation: string }).operation === "send")).toHaveLength(1);
    expect(invoke.mock.calls.some(([, args]) => (args.request as { operation: string }).operation === "recover_send")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Check previous request" }));
    await screen.findByText(/original-admission/);
    expect(invoke.mock.calls.find(([, args]) => (args.request as { operation: string }).operation === "recover_send")?.[1].request).toEqual({ operation: "recover_send", sessionId: "session-one", requestId: originalRequest.requestId });
    expect(screen.queryByRole("button", { name: "Check previous request" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(false));
    expect(invoke.mock.calls.filter(([, args]) => (args.request as { operation: string }).operation === "send")).toHaveLength(1);
  });
  it("keeps sending paused if a durable-store failure occurs after invocation", async () => {
    const p = await openChat();
    p.request.mockRejectedValueOnce(new Error("NATIVE_RECOVERY_UNAVAILABLE"));
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Outcome unknown/);
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Check previous request" })).toBeTruthy();
  });
  it("does not enable a new send when the original settles but another native admission is running", async () => {
    const p = await openChat();
    p.request.mockResolvedValueOnce({ ...view({ state: "ADMITTED", session: { ...nativeSession(), running: true,
      pending: [{ id: "other-admission", status: "started" }] }, receipt: { id: "original-admission", sessionId: "session-one",
      status: "terminal", sequence: 1, outcome: "completed", executionGeneration: 1 } }), pendingOperation: null });
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText(/original-admission/);
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "next" } });
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(true);
  });

  it("bounds foreground original-admission reads even when every recovery remains admitted", async () => {
    const p = await openChat();
    const base = p.request.getMockImplementation()!;
    p.request.mockImplementation(async request => request.operation === "send" || request.operation === "recover"
      ? { ...view({ state: "ADMITTED", session: nativeSession(), receipt: { id: "original-admission", sessionId: "session-one",
          status: "queued", sequence: 1, outcome: null, executionGeneration: null } }),
          pendingOperation: { kind: "send", sessionId: "session-one", requestId: "a".repeat(32) } }
      : base(request));
    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
        fireEvent.click(screen.getByRole("button", { name: "Send message" }));
      });
      for (let i = 0; i < 35; i++) await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
      expect(p.request.mock.calls.filter(([request]) => request.operation === "recover")).toHaveLength(30);
      expect(p.request.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(1);
      expect(screen.queryByRole("button", { name: "Send message" })).toBeNull();
      expect(screen.getByRole("button", { name: "Stop generation" })).toBeTruthy();
    } finally { vi.useRealTimers(); }
  });

  it("keeps a settled receipt visible when history times out and requires a fresh read before another send", async () => {
    const p = await openChat();
    p.request.mockResolvedValueOnce(view({ state: "EFFECT_UNKNOWN", operation: "send" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Outcome unknown/);
    p.request.mockResolvedValueOnce({ ...view({ state: "ADMITTED", operation: "recover", receipt: {
      id: "settled-original", sessionId: "session-one", status: "terminal", sequence: 1,
      outcome: "completed", executionGeneration: 1 } }), pendingOperation: null });
    p.request.mockRejectedValueOnce(new Error("NATIVE_CLIENT_UNAVAILABLE"));
    fireEvent.click(screen.getByRole("button", { name: "Check previous request" }));
    await screen.findByText(/NATIVE_CLIENT_UNAVAILABLE/);
    expect(screen.getByText("settled-original")).toBeTruthy();
    expect(screen.getByText(/terminal · completed/)).toBeTruthy();
    expect(screen.queryByText(/Outcome unknown/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Check previous request" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(true);
    expect((screen.getByRole("textbox", { name: "Message Hermes" }) as HTMLTextAreaElement).value).toBe("");
    p.request.mockResolvedValueOnce(view({ operation: "read", session: nativeSession() }));
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message Hermes" }).hasAttribute("disabled")).toBe(false));
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "next question" } });
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(false);
    expect(p.request.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(1);
  });
});

describe("existing stored native conversations", () => {
  const savedSession = () => ({ ...nativeSession(), canSend: false, toolAccess: "UNQUALIFIED",
    sendCheckRequired: true, running: null, promptsPending: null, messageCount: 1,
    messages: [{ role: "assistant", text: "The original retained answer." }] });
  async function openSaved(p = port()) {
    const base = p.request.getMockImplementation()!;
    p.request.mockImplementation(async r => r.operation === "list"
      ? view({ operation: "list", sessions: [{ id: "session-one", title: "Original conversation", running: null, messageCount: 1 }] })
      : r.operation === "read" ? view({ operation: "read", session: savedSession() }) : base(r));
    render(<HermesNativePanel port={p} locale="en" />);
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Local history" }).hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Local history" }));
    fireEvent.click(await screen.findByRole("button", { name: /Original conversation/ }));
    await screen.findByText("The original retained answer.");
    return p;
  }
  it("opens the original answer without creation and checks only an explicit send", async () => {
    const p = await openSaved();
    expect(p.request.mock.calls.filter(([r]) => r.operation === "create" || r.operation === "send")).toHaveLength(0);
    expect(screen.getByText(/current send access is checked when you send/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "  original follow-up\n 中文" } });
    p.request.mockResolvedValueOnce({ ...view({ operation: "send", state: "NOT_SENT", code: "NATIVE_NOT_SENT" }), pendingOperation: null });
    fireEvent.click(screen.getByRole("button", { name: "Check and send message" }));
    await screen.findByText(/The request was not sent/);
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);
    expect(p.request.mock.calls.find(([r]) => r.operation === "send")?.[0]).toMatchObject({ sessionId: "session-one", text: "  original follow-up\n 中文" });
    expect((screen.getByRole("textbox", { name: "Message Hermes" }) as HTMLTextAreaElement).value).toBe("  original follow-up\n 中文");
  });
  it("refreshes the logical conversation after its physical transcript rotates", async () => {
    const p = await openSaved();
    p.request.mockResolvedValueOnce(view({ operation: "read", session: {
      ...savedSession(), storedId: "physical-old", messages: [{ role: "assistant", text: "Before rotation." }] } }));
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText("Before rotation.");
    p.request.mockImplementation(async request => {
      if (request.operation !== "read" || request.sessionId !== "session-one") throw new Error("NATIVE_RESPONSE_INVALID");
      return view({ operation: "read", session: { ...savedSession(), storedId: "physical-new",
        messages: [{ role: "assistant", text: "The same conversation after rotation." }] } });
    });
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText("The same conversation after rotation.");
    expect(p.request).toHaveBeenLastCalledWith({ operation: "read", sessionId: "session-one" });
    expect(p.request.mock.calls.filter(([r]) => r.operation === "create" || r.operation === "send")).toHaveLength(0);
  });
  it("keeps a durable unknown admission held when live state is unobserved", async () => {
    const p = await openSaved();
    p.request.mockResolvedValueOnce(view({ operation: "read", session: { ...savedSession(),
      pending: [{ id: "original-admission", status: "unknown" }] } }));
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText(/original native admission is unknown/);
    expect(screen.getByRole("button", { name: "Check and send message" }).hasAttribute("disabled")).toBe(true);
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(0);
  });
  it("holds conditional sending until history refresh succeeds after recovery", async () => {
    const p = await openSaved();
    const pendingOperation = { kind: "send" as const, sessionId: "session-one", requestId: "a".repeat(32) };
    const started = () => ({ ...view({ operation: "recover", state: "ADMITTED", receipt: {
      id: "original-admission", sessionId: "session-one", status: "started", sequence: 1,
      outcome: null, executionGeneration: 1 } }), pendingOperation });
    p.request.mockResolvedValueOnce({ ...started(), operation: "send" });
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and send message" }));
    await screen.findByText(/Sending is paused until the original request’s outcome is confirmed/);
    expect(screen.queryByText(/Tool scope not qualified for sending/)).toBeNull();

    // The started original is still held after recovery clears stale send eligibility.
    p.request.mockResolvedValueOnce(started());
    p.request.mockRejectedValueOnce(new Error("NATIVE_CLIENT_UNAVAILABLE"));
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText(/NATIVE_CLIENT_UNAVAILABLE/);
    expect(screen.getByText(/Sending is paused until the original request’s outcome is confirmed/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send message" })).toBeNull();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message Hermes" }), { key: "Enter", code: "Enter" });
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);

    p.request.mockResolvedValueOnce({ ...view({ operation: "recover", state: "EFFECT_UNKNOWN" }), pendingOperation });
    fireEvent.click(screen.getByRole("button", { name: "Check previous request" }));
    await screen.findByText(/Outcome unknown/);
    expect(screen.getByText(/Sending is paused until the original request’s outcome is confirmed/)).toBeTruthy();
    expect(screen.queryByText(/Tool scope not qualified for sending/)).toBeNull();
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);

    p.request.mockResolvedValueOnce({ ...view({ operation: "recover", state: "ADMITTED", receipt: {
      id: "original-admission", sessionId: "session-one", status: "terminal", sequence: 2,
      outcome: "completed", executionGeneration: 1 } }), pendingOperation: null });
    p.request.mockRejectedValueOnce(new Error("NATIVE_CLIENT_UNAVAILABLE"));
    fireEvent.click(screen.getByRole("button", { name: "Check previous request" }));
    await screen.findByText(/NATIVE_CLIENT_UNAVAILABLE/);
    expect(screen.queryByRole("button", { name: "Check and send message" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Refresh the original conversation before sending again/)).toBeTruthy();
    expect(screen.queryByText(/Sending is paused until/)).toBeNull();
    expect(screen.queryByText(/Tool scope not qualified for sending/)).toBeNull();
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText(/current send access is checked when you send/);
    expect(screen.getByText("The original retained answer.")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "next question" } });
    expect(screen.getByRole("button", { name: "Check and send message" }).hasAttribute("disabled")).toBe(false);
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(1);
  });
  it("retains the scope refusal when no original effect or send check applies", async () => {
    const p = await openSaved();
    p.request.mockResolvedValueOnce(view({ operation: "read", session: { ...nativeSession(), canSend: false, toolAccess: "UNQUALIFIED" } }));
    fireEvent.click(screen.getByRole("button", { name: "Read original conversation" }));
    await screen.findByText(/Tool scope not qualified for sending/);
    expect(screen.queryByText(/Sending is paused until/)).toBeNull();
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(true);
    expect(p.request.mock.calls.filter(([r]) => r.operation === "send")).toHaveLength(0);
  });
});



describe("Hermes Stop interaction", () => {
  const original = { kind: "send" as const, sessionId: "session-one", requestId: "a".repeat(32) };
  const admitted = (operation: string, status = "started") => view({ operation, state: "ADMITTED",
    requestId: original.requestId, requestSessionId: original.sessionId, receipt: {
      id: "original-admission", sessionId: original.sessionId, status, sequence: 2,
      outcome: status === "terminal" ? "cancelled" : null, executionGeneration: 1 } });
  it("offers Stop for its running original and a rapid second click cannot dispatch twice", async () => {
    const p = await openChat(), base = p.request.getMockImplementation()!;
    let finish!: () => void;
    p.request.mockImplementation(async request => {
      if (request.operation === "send") return { ...admitted("send"), pendingOperation: original };
      if (request.operation === "stop") return new Promise(resolve => {
        finish = () => resolve({ ...admitted("stop", "terminal"), pendingOperation: null });
      });
      return base(request);
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    const stop = await screen.findByRole("button", { name: "Stop generation" });
    fireEvent.click(stop); fireEvent.click(stop);
    expect(p.request.mock.calls.filter(([request]) => request.operation === "stop")).toHaveLength(1);
    await act(async () => { finish(); });
    await screen.findByText(/terminal · cancelled/);
    await waitFor(() => expect(p.request.mock.calls.some(([request]) => request.operation === "read")).toBe(true));
    expect(screen.queryByRole("button", { name: "Stop generation" })).toBeNull();
    expect(p.request.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(1);
    expect((screen.getByRole("textbox", { name: "Message Hermes" }) as HTMLTextAreaElement).value).toBe("");
  });
  it("reopens a lost cancellation with Stop and new sends disabled and only reads the original", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const scope = "e".repeat(64);
    await store.reserve(scope, nativePendingPointer(original));
    const invoke = vi.fn(async (_command: string, args: Record<string, unknown>) => {
      const request = args.request as { operation: string };
      if (request.operation === "stop_send") throw new Error("lost cancellation response");
      if (request.operation === "recover_send") return admitted("recover");
      if (request.operation === "read") return view({ operation: "read", session: nativeSession() });
      return view({ operation: "status" });
    });
    const makePort = () => createNativeHermesPort({ invoke, available: () => true,
      store: createIndexedDbPendingPointerStore(factory) });
    const first = render(<HermesNativePanel port={makePort()} locale="en" />);
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await screen.findByRole("button", { name: "Check previous request" });
    fireEvent.click(screen.getByRole("button", { name: "Check previous request" }));
    const stop = await screen.findByRole("button", { name: "Stop generation" });
    await waitFor(() => expect(stop.hasAttribute("disabled")).toBe(false));
    fireEvent.click(stop);
    await screen.findByText(/NATIVE_CLIENT_UNAVAILABLE/);
    expect(screen.getByRole("button", { name: "Stop generation" }).hasAttribute("disabled")).toBe(true);
    first.unmount();
    render(<HermesNativePanel port={makePort()} locale="en" />);
    expect(invoke.mock.calls.filter(([, args]) => (args.request as { operation: string }).operation === "stop_send")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await screen.findByText(/Stop outcome is not confirmed/);
    fireEvent.click(screen.getByRole("button", { name: "Check previous request" }));
    const reopenedStop = await screen.findByRole("button", { name: "Stop generation" });
    await waitFor(() => expect(screen.getByRole("region", { name: "Native Hermes" }).getAttribute("aria-busy")).toBe("false"));
    expect(reopenedStop.hasAttribute("disabled")).toBe(true);
    fireEvent.click(reopenedStop);
    expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(true);
    expect(invoke.mock.calls.filter(([, args]) => (args.request as { operation: string }).operation === "stop_send")).toHaveLength(1);
    expect(invoke.mock.calls.some(([, args]) => ["send", "create"].includes((args.request as { operation: string }).operation))).toBe(false);
  });
  it("clears private state when auth changes during Stop and never retries cancellation", async () => {
    const p = await openChat(), base = p.request.getMockImplementation()!;
    p.request.mockImplementation(async request => {
      if (request.operation === "send") return { ...admitted("send"), pendingOperation: original };
      if (request.operation === "stop") throw new Error("AUTHENTICATION_CHANGED");
      return base(request);
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Message Hermes" }), { target: { value: "private message" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    fireEvent.click(await screen.findByRole("button", { name: "Stop generation" }));
    await screen.findByText(/Sign-in changed\. The previous conversation is hidden/);
    expect(screen.queryByRole("textbox", { name: "Message Hermes" })).toBeNull();
    expect(screen.queryByText("original-admission")).toBeNull();
    expect(screen.queryByRole("button", { name: "Stop generation" })).toBeNull();
    expect(p.request.mock.calls.filter(([request]) => request.operation === "stop")).toHaveLength(1);
  });
});

describe("live native chat interaction", () => {
  it("keeps the next draft editable while real partial text arrives and reconciles only the original receipt", async () => {
    const p = port(), base = p.request.getMockImplementation()!;
    let receive: ((frame: import("./live-stream").NativeLiveFrame) => void) | undefined;
    const dispose = vi.fn();
    const observed: NativeHermesPort = { ...p, observe: vi.fn((_target, onFrame) => { receive = onFrame; return dispose; }) };
    let acceptSend: ((value: NativeView) => void) | undefined;
    const original = { kind: "send" as const, sessionId: "session-one", requestId: "a".repeat(32) };
    const receipt = { id: "stream-original", sessionId: "session-one", status: "started" as const, sequence: 1, outcome: null, executionGeneration: 1 };
    p.request.mockImplementation(async request => {
      if (request.operation === "send") return new Promise<NativeView>(resolve => { acceptSend = resolve; });
      if (request.operation === "recover") return { ...view({ operation: "recover", state: "ADMITTED", receipt: { ...receipt, status: "terminal", outcome: "completed" } }), pendingOperation: null };
      if (request.operation === "read") return { ...view({ operation: "read", session: { ...nativeSession(), messageCount: 2, messages: [{ role: "user", text: "Original message" }, { role: "assistant", text: "Canonical completed answer" }] } }), pendingOperation: null };
      return base(request);
    });
    render(<HermesNativePanel locale="en" port={observed} />);
    fireEvent.click(screen.getByRole("button", { name: "Connect local Hermes" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "New conversation" }).hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "New conversation" }));
    const input = await screen.findByRole("textbox", { name: "Message Hermes" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "Original message" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(acceptSend).toBeDefined());
    expect(input.disabled).toBe(false);
    fireEvent.change(input, { target: { value: "My next question" } });
    await act(async () => acceptSend!({ ...view({ operation: "send", state: "ADMITTED", receipt }), pendingOperation: original }));
    await waitFor(() => expect(receive).toBeDefined());
    const update = { schema: "mastermind.hermes_native_stream.v1" as const, authGeneration: 2,
      sessionId: "session-one", admissionId: receipt.id, authorityEpoch: 1, executionGeneration: 1,
      replayEpoch: "native-epoch", sequence: 2, text: "A real partial answer", state: "live" as const, activity: "responding" as const, code: null };
    await act(async () => receive!(update));
    await screen.findByText("A real partial answer");
    expect(input.value).toBe("My next question");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(p.request.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Stop generation" })).toBeTruthy();
    await act(async () => receive!({ ...update, state: "complete" }));
    await screen.findByText("Canonical completed answer");
    expect(screen.queryByText("A real partial answer")).toBeNull();
    expect(document.querySelector("[data-pending-message]")).toBeNull();
    expect(input.value).toBe("My next question");
    expect(screen.getByRole("button", { name: "Send message" }).hasAttribute("disabled")).toBe(false);
    expect(p.request.mock.calls.filter(([request]) => request.operation === "recover")).toHaveLength(1);
    expect(p.request).toHaveBeenLastCalledWith({ operation: "read", sessionId: "session-one" });
    expect(dispose).toHaveBeenCalledTimes(1);
  });

  it("does not submit an IME confirmation or Shift+Enter as a new message", async () => {
    const p = await openChat();
    const input = screen.getByRole("textbox", { name: "Message Hermes" });
    fireEvent.change(input, { target: { value: "中文" } });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter", isComposing: true, keyCode: 229 });
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyUp(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(p.request.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(0);
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(p.request.mock.calls.filter(([request]) => request.operation === "send")).toHaveLength(1));
  });
});
