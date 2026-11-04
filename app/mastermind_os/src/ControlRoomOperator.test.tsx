// @vitest-environment jsdom
// Original #1515 operator cases, composed through the actual App and fixed host.
// Inert Runtime-shaped fixtures only; no browser/host/provider acceptance claim.
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { flushSync } from "react-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, type AuthState, type RawClient } from "./host";
import {
  CONTROL_ROOM_UNKNOWN_OUTCOME, ControlRoomActionTransportError,
  type ControlRoomActionResult, type ControlRoomOperation,
} from "./control-room";
import { controlRoomFixture, missionFixture } from "./test-fixtures";

const bindingId = (n: number) => `${String(n).padStart(8, "0")}-1111-4111-8111-111111111111`;
function payload() {
  const room = controlRoomFixture();
  // The shared two-programme fixture clones one actual binding. Give each
  // explicitly separate fixture row its own handle, preserving closed navigation.
  room.work.forEach((work: { bindings: Array<{ binding_id: string }> }, i: number) => {
    work.bindings[0].binding_id = bindingId(i + 1);
  });
  return {
    control_room: room, capabilities: {}, composed_at: "2026-10-19T11:00:00Z",
    refresh_in_flight: false, live_builds_active: false,
    state_refresh_error: null, source_validity: {},
  };
}
const discoveryDocument = () => ({
  chatgpt_environments: { multilogin: [], gologin: [] }, claude_code_sessions: [],
  codex_sessions: [{ session_id: "fixture-candidate", date: "2026-10-19" }],
  cursor: { supported: false as const, note: "Fixture Cursor discovery is unsupported." },
});
function result(operation: ControlRoomOperation, disposition: ControlRoomActionResult["disposition"] = "OWNER_RETURNED",
                outcome: Record<string, unknown> = { ok: true, detail: "fixture-owner-result" }): ControlRoomActionResult {
  return {
    schema: "mastermind.workspace_control_room_action_result.v1", operation,
    status: disposition === "OWNER_RETURNED" ? 200 : disposition === "NOT_DISPATCHED" ? 403 : 503,
    disposition, outcome: disposition === "EFFECT_UNKNOWN" ? { ...CONTROL_ROOM_UNKNOWN_OUTCOME } : outcome,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture({ signedIn = true, methods = true } = {}) {
  let state: AuthState = { status: signedIn ? "signed_in" : "signed_out", acquisition: signedIn, content: signedIn, reason: null };
  let generation = 0;
  const listeners = new Set<(state: AuthState) => void>();
  const unavailable = vi.fn(async () => { throw new Error("FIXTURE_SOURCE_UNAVAILABLE"); });
  const raw: RawClient = {
    getState: () => state,
    invalidationGeneration: () => generation,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    signIn: vi.fn(async () => {}), signOut: vi.fn(async () => {}),
    readPrograms: unavailable, readWork: unavailable, readCurrentWindow: unavailable,
    readMission: vi.fn(async request => missionFixture(request.work_ref, request.root_job_id)),
    readControlRoomState: vi.fn(async () => payload()),
    ...(methods ? {
      readControlRoomDiscovery: vi.fn(async () => discoveryDocument()),
      openControlRoomSurface: vi.fn(async () => result("open")),
      unbindControlRoomSurface: vi.fn(async () => result("unbind")),
      bindControlRoomSurface: vi.fn(async () => result("bind")),
      refreshControlRoomBuilds: vi.fn(async () => result("refresh-builds")),
    } : {}),
  };
  const host = bindMissionHost(raw);
  window.MastermindMissionHost = host;
  return {
    raw, host,
    advance(next: AuthState = state) {
      generation++;
      state = next;
      for (const listener of listeners) listener(state);
    },
  };
}
function openButton(n = 1) {
  return screen.getByRole("button", { name: `Open Cursor agent binding ${bindingId(n)}` }) as HTMLButtonElement;
}
async function enter(user = userEvent.setup()) {
  if (!screen.queryByRole("navigation", { name: "Company operations" })) {
    await user.click(within(screen.getByRole("navigation", { name: "Company navigation" }))
      .getByRole("button", { name: "Today" }));
  }
  await user.click(within(screen.getByRole("navigation", { name: "Company operations" }))
    .getByRole("button", { name: "Control Room" }));
  await screen.findByRole("heading", { name: "Company overview" });
  return user;
}
async function observed() {
  await screen.findByText(/source-qualified Programs/);
  expect(screen.getByRole("list", { name: "Observed surface bindings" })).toBeTruthy();
}
beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
});
afterEach(() => { cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks(); });

describe("Control Room original operator intent in App", () => {
  it("preserves READ and View mission when optional action methods are absent", async () => {
    const { raw } = fixture({ methods: false });
    render(<App />);
    const user = await enter();
    await observed();
    expect(raw.readControlRoomState).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: /^Open |^Unbind |^Confirm Unbind|^Refresh builds$/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "View qualified Mission for Alpha program" }));
    expect(new URL(location.href).searchParams.get("work_ref")).toBe("WS:ALPHA");
    expect(new URL(location.href).searchParams.get("root_job_id")).toBe("JOB-A");
  });

  it("routes only explicit Open through the captured original host and exact handle", async () => {
    const { raw } = fixture();
    render(<App />);
    const user = await enter();
    await observed();
    expect(raw.openControlRoomSurface).not.toHaveBeenCalled();
    expect(raw.readControlRoomDiscovery).not.toHaveBeenCalled();
    await user.click(openButton());
    expect(raw.openControlRoomSurface).toHaveBeenCalledExactlyOnceWith({ payload: { binding_id: bindingId(1) }, signal: expect.any(AbortSignal) });
    expect(screen.getByText("Owner reported success")).toBeTruthy();
    expect(screen.getByText("Verification that the surface is open was not confirmed.")).toBeTruthy();
    expect(raw.bindControlRoomSurface).not.toHaveBeenCalled();
    expect(raw.refreshControlRoomBuilds).not.toHaveBeenCalled();
  });

  it("retains the original affirmative Unbind confirmation before its one host call", async () => {
    const { raw } = fixture();
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(screen.getByRole("button", { name: `Unbind Cursor agent binding ${bindingId(1)}` }));
    expect(raw.unbindControlRoomSurface).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Confirm Unbind/ }));
    expect(raw.unbindControlRoomSurface).toHaveBeenCalledExactlyOnceWith({ payload: { binding_id: bindingId(1) }, signal: expect.any(AbortSignal) });
    expect(raw.openControlRoomSurface).not.toHaveBeenCalled();
  });

  it("retains unknown custody through State READ, Discovery READ and route remount", async () => {
    const { raw } = fixture();
    vi.mocked(raw.openControlRoomSurface!).mockRejectedValueOnce(new ControlRoomActionTransportError("open", "EFFECT_UNKNOWN"));
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(openButton());
    expect(screen.getByText("Action outcome unknown")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Refresh Control Room" }));
    await observed();
    await user.click(screen.getByRole("button", { name: "Discover surfaces" }));
    expect(raw.readControlRoomDiscovery).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Today" }));
    await enter(user);
    await observed();
    expect(screen.getByText("Action outcome unknown")).toBeTruthy();
    expect(openButton().disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Refresh builds" }) as HTMLButtonElement).disabled).toBe(true);
    expect(raw.openControlRoomSurface).toHaveBeenCalledOnce();
    expect(raw.readControlRoomState).toHaveBeenCalledTimes(3);
    expect(raw.refreshControlRoomBuilds).not.toHaveBeenCalled();
  });

  it("preserves OWNER_RETURNED false, with State refresh separate from build mutation", async () => {
    const { raw } = fixture();
    vi.mocked(raw.openControlRoomSurface!).mockResolvedValueOnce(result("open", "OWNER_RETURNED", { ok: false, detail: "fixture returned failure" }));
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(openButton());
    expect(screen.getByText("Success was not reported")).toBeTruthy();
    expect(screen.getByText("The owner returned. This does not confirm that no change occurred.")).toBeTruthy();
    expect(screen.queryByText("Action not dispatched")).toBeNull();
    expect(raw.readControlRoomState).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Refresh Control Room" }));
    await observed();
    expect(raw.refreshControlRoomBuilds).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Refresh builds" }));
    expect(raw.refreshControlRoomBuilds).toHaveBeenCalledExactlyOnceWith({ signal: expect.any(AbortSignal) });
  });

  it("binds explicit Codex coordinates without deriving them from Discovery", async () => {
    const { raw } = fixture();
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(screen.getByRole("button", { name: "Discover surfaces" }));
    expect(raw.readControlRoomDiscovery).toHaveBeenCalledOnce();
    expect(raw.bindControlRoomSurface).not.toHaveBeenCalled();
    await user.click(screen.getByText("Bind a surface"));
    const form = within(screen.getByRole("form", { name: "Bind a workspace surface" }));
    expect((form.getByLabelText("Work reference") as HTMLInputElement).value).toBe("");
    await user.type(form.getByLabelText("Work reference"), "WS:TEST");
    await user.selectOptions(form.getByLabelText("Role"), "ceo");
    await user.selectOptions(form.getByLabelText("Provider"), "codex");
    await user.type(form.getByLabelText("Codex session ID"), "existing-session");
    await user.click(form.getByRole("button", { name: "Bind" }));
    expect(raw.bindControlRoomSurface).toHaveBeenCalledExactlyOnceWith({ payload: {
      work_ref: "WS:TEST", role: "ceo", provider: "codex", locator: { session_id: "existing-session" },
    }, signal: expect.any(AbortSignal) });
    expect(raw.openControlRoomSurface).not.toHaveBeenCalled();
  });

  it("discloses no binding or Discovery rows and dispatches nothing without acquisition", async () => {
    const { raw } = fixture({ signedIn: false });
    render(<App />);
    const user = await enter();
    expect(screen.queryByText(bindingId(1))).toBeNull();
    expect(screen.queryByText("fixture-candidate")).toBeNull();
    expect(screen.queryByLabelText("Work reference")).toBeNull();
    const builds = screen.getByRole("button", { name: "Refresh builds" }) as HTMLButtonElement;
    expect(builds.disabled).toBe(true);
    await user.click(builds);
    expect(raw.readControlRoomState).not.toHaveBeenCalled();
    expect(raw.refreshControlRoomBuilds).not.toHaveBeenCalled();
  });

  it("preserves one pending action above the unmounted panel and keeps its late result", async () => {
    const { raw } = fixture();
    const reply = deferred<ControlRoomActionResult>();
    vi.mocked(raw.openControlRoomSurface!).mockReturnValueOnce(reply.promise);
    render(<App />);
    const user = await enter();
    await observed();
    const button = openButton();
    act(() => { button.click(); button.click(); });
    expect(raw.openControlRoomSurface).toHaveBeenCalledOnce();
    const signal = vi.mocked(raw.openControlRoomSurface!).mock.calls[0][0].signal;
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(signal.aborted).toBe(false);
    await enter(user);
    await observed();
    expect(screen.getByText("Awaiting action result")).toBeTruthy();
    expect(openButton().disabled).toBe(true);
    await act(async () => reply.resolve(result("open")));
    expect(screen.getByText("Owner reported success")).toBeTruthy();
    expect(openButton().disabled).toBe(false);
    expect(signal.aborted).toBe(false);
    expect(raw.openControlRoomSurface).toHaveBeenCalledOnce();
  });

  it("withholds old details immediately on equal-public-state auth generation change, retaining custody", async () => {
    const owner = fixture();
    const reply = deferred<ControlRoomActionResult>();
    const replacementState = deferred<ReturnType<typeof payload>>();
    vi.mocked(owner.raw.openControlRoomSurface!).mockReturnValueOnce(reply.promise);
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(screen.getByRole("button", { name: "Discover surfaces" }));
    await user.click(screen.getByText("Codex sessions"));
    expect(screen.getByText("fixture-candidate")).toBeTruthy();
    await user.click(openButton());
    const signal = vi.mocked(owner.raw.openControlRoomSurface!).mock.calls[0][0].signal;
    vi.mocked(owner.raw.readControlRoomState!).mockReturnValueOnce(replacementState.promise);
    act(() => flushSync(() => owner.advance()));
    expect(screen.queryByText("fixture-candidate")).toBeNull();
    expect(screen.queryByText("Awaiting action result")).toBeNull();
    expect(screen.getByText("Earlier action details withheld")).toBeTruthy();
    expect(signal.aborted).toBe(false);
    await act(async () => reply.resolve(result("open", "EFFECT_UNKNOWN")));
    await act(async () => replacementState.resolve(payload()));
    await observed();
    expect(screen.getByText("Earlier action details withheld")).toBeTruthy();
    expect(screen.queryByText("Action receipt")).toBeNull();
    expect(openButton().disabled).toBe(true);
    expect(owner.raw.openControlRoomSurface).toHaveBeenCalledOnce();
  });

  it("does not restore old action details after selected mission A-B-A", async () => {
    history.replaceState(null, "", "/os/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
    const { raw } = fixture();
    const reply = deferred<ControlRoomActionResult>();
    vi.mocked(raw.openControlRoomSurface!).mockReturnValueOnce(reply.promise);
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(openButton());
    for (const name of ["Beta", "Alpha"]) {
      await user.click(screen.getByRole("button", { name: `View qualified Mission for ${name} program` }));
      await enter(user);
      await observed();
    }
    expect(new URL(location.href).searchParams.get("work_ref")).toBe("WS:ALPHA");
    await act(async () => reply.resolve(result("open", "EFFECT_UNKNOWN")));
    expect(screen.getByText("Earlier action details withheld")).toBeTruthy();
    expect(screen.queryByText("Requested action:")).toBeNull();
    expect(openButton().disabled).toBe(true);
    expect(raw.openControlRoomSurface).toHaveBeenCalledOnce();
  });

  it("releases only a qualified NOT_DISPATCHED hold for a later explicit choice", async () => {
    const { raw } = fixture();
    vi.mocked(raw.openControlRoomSurface!).mockRejectedValueOnce(new ControlRoomActionTransportError("open", "NOT_DISPATCHED"));
    render(<App />);
    const user = await enter();
    await observed();
    await user.click(openButton());
    expect(screen.getByText("Action not dispatched")).toBeTruthy();
    expect(openButton().disabled).toBe(false);
    expect(raw.openControlRoomSurface).toHaveBeenCalledOnce();
    await user.click(openButton());
    expect(raw.openControlRoomSurface).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Owner reported success")).toBeTruthy();
  });
});
