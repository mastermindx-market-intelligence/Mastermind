// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HermesNativePanel } from "./HermesNativePanel";
import { parseNativeView, type NativeHermesPort, type NativeOperation } from "./contract";

function view(extra: Record<string, unknown> = {}) {
  return parseNativeView({ schema: "mastermind.hermes_native_view.v1", state: "READY", authGeneration: 2,
    capabilities: ["native_chat", "native_history", "admission_recovery"], delegation: "NOT_ENABLED", retryAllowed: false,
    runtime: { protocol: 1, instanceId: "native-one", authorityEpoch: 1, version: "0.23.0", sourceRevision: "a".repeat(40) }, ...extra });
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
    expect(screen.getByText(/configured-model/)).toBeTruthy();
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
    await waitFor(() => expect(p.request.mock.calls.some(([r]) => r.operation === "read")).toBe(true));
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
});
