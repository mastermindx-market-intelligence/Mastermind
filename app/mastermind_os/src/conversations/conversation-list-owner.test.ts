// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "../host";
import { captureConversationListOwner, conversationListOwnerCurrent } from "./conversation-list-owner";

afterEach(() => { vi.restoreAllMocks(); delete window.MastermindMissionHost; });
async function owner() {
  const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: true };
  const invoke = vi.fn(async (name: string) => name === "auth_status" ? signed : { generation: 0, available: false });
  const client = await createNativeClient(invoke as never, async () => () => {}), host = bindMissionHost(client);
  window.MastermindMissionHost = host;
  // Stable fixture owner observations let predicates be tested independently
  // from method-replacement detection; no notification or render is involved.
  let liveState = signed, liveGeneration = host.invalidationGeneration!(), authGeneration = 4, sequence = 9;
  let reenter: (() => void) | null = null;
  vi.spyOn(host.auth!, "getState").mockImplementation(() => { reenter?.(); return liveState; });
  vi.spyOn(host, "invalidationGeneration").mockImplementation(() => liveGeneration);
  const input = { host, authGeneration, selectionSequence: sequence,
    currentHost: () => window.MastermindMissionHost,
    currentAuthGeneration: () => authGeneration, currentSelectionSequence: () => sequence };
  const capture = captureConversationListOwner(input);
  expect(capture).not.toBeNull();
  return { host, input, capture, invoke,
    revokeContent: () => { liveState = { ...liveState, content: false }; },
    expire: () => { liveState = { ...liveState, acquisition: false, content: false }; },
    invalidate: () => { liveGeneration++; }, changeAuth: () => { authGeneration++; },
    changeSelection: () => { sequence++; }, reenter: (fn: () => void) => { reenter = fn; } };
}
describe("actual conversation-list navigation owner", () => {
  it("uses the actual host's live Content and Acquisition without acquiring data or borrowing send rights", async () => {
    const e = await owner();
    expect(conversationListOwnerCurrent(e.capture, true)).toBe(true);
    e.revokeContent();
    expect(conversationListOwnerCurrent(e.capture, true)).toBe(false);
    expect(conversationListOwnerCurrent(e.capture, false)).toBe(true);
    e.expire(); expect(conversationListOwnerCurrent(e.capture, false)).toBe(false);
    expect(e.invoke.mock.calls.some(([name]) => name.startsWith("read_") || /send|submit|prepare/.test(name))).toBe(false);
  });
  it.each(["generation", "auth", "selection", "host", "method"])("refuses no-render %s drift", async kind => {
    const e = await owner();
    if (kind === "generation") e.invalidate();
    if (kind === "auth") e.changeAuth();
    if (kind === "selection") e.changeSelection();
    if (kind === "host") window.MastermindMissionHost = { ...e.host };
    if (kind === "method") Object.defineProperty(e.host.auth!, "getState", { configurable: true, value: () => ({ status: "signed_in", acquisition: true, content: true, reason: null }) });
    expect(conversationListOwnerCurrent(e.capture, false)).toBe(false);
  });
  it("rechecks receiver identity after a getter reenters and cannot retarget the original capture", async () => {
    const e = await owner();
    e.reenter(() => { window.MastermindMissionHost = { ...e.host }; });
    expect(conversationListOwnerCurrent(e.capture, true)).toBe(false);
    expect(Object.isFrozen(e.capture!.input)).toBe(true);
    e.input.authGeneration = 5;
    expect(e.capture!.input.authGeneration).toBe(4);
  });
});
