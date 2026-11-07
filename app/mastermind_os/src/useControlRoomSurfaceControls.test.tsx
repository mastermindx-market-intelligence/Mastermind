// @vitest-environment jsdom
// In-memory hook fixtures only. No provider, socket, browser manager or host effect.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthState, MissionHost } from "./host";
import {
  CONTROL_ROOM_UNKNOWN_OUTCOME,
  ControlRoomActionTransportError,
  type ControlRoomActionResult,
  type ControlRoomDisposition,
  type ControlRoomOperation,
} from "./control-room-actions";
import { useControlRoomSurfaceControls } from "./useControlRoomSurfaceControls";

type HookProps = Parameters<typeof useControlRoomSurfaceControls>[0];
type ActionArgs = { payload?: Readonly<Record<string, unknown>>; signal: AbortSignal };
const SIGNED: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
const OPEN = { binding_id: "00000000-0000-0000-0000-000000000001" };
const BIND = {
  work_ref: "WS:FABRIC", role: "worker", provider: "codex",
  locator: { session_id: "fixture-session" },
};

function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function envelope(
  operation: ControlRoomOperation,
  outcome: Readonly<Record<string, unknown>> = { ok: true },
  disposition: ControlRoomDisposition = "OWNER_RETURNED",
  status = 200,
): ControlRoomActionResult {
  return {
    schema: "mastermind.workspace_control_room_action_result.v1",
    operation, status, disposition, outcome,
  };
}

function discoveryDocument(label = "fixture-session") {
  return {
    chatgpt_environments: { multilogin: [], gologin: [] },
    claude_code_sessions: [],
    codex_sessions: [{ session_id: label, date: "2026-10-19" }],
    cursor: { supported: false, note: "Fixture observation only." },
  };
}

function fixture() {
  let state: AuthState = { ...SIGNED };
  let generation = 7;
  const getState = vi.fn(() => state);
  const getGeneration = vi.fn(() => generation);
  const auth = {
    getState,
    subscribe: vi.fn((_listener: (value: AuthState) => void) => () => {}),
    signIn: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
  };
  const open = vi.fn(async (_args: ActionArgs): Promise<unknown> => envelope("open"));
  const bind = vi.fn(async (_args: ActionArgs): Promise<unknown> => envelope("bind"));
  const unbind = vi.fn(async (_args: ActionArgs): Promise<unknown> => envelope("unbind"));
  const refresh = vi.fn(async (_args: ActionArgs): Promise<unknown> => envelope("refresh-builds"));
  const discover = vi.fn(async (_args: { signal: AbortSignal }): Promise<unknown> => discoveryDocument());
  // Deliberately permit malformed fixture returns to test the hook's boundary.
  const host = {
    auth, invalidationGeneration: getGeneration,
    openControlRoomSurface: open, bindControlRoomSurface: bind,
    unbindControlRoomSurface: unbind, refreshControlRoomBuilds: refresh,
    readControlRoomDiscovery: discover,
  } as unknown as MissionHost;
  return {
    host, auth, getState, getGeneration, open, bind, unbind, refresh, discover,
    setState(next: AuthState) { state = next; },
    advanceGeneration() { generation += 1; },
  };
}

function mount(e = fixture()) {
  window.MastermindMissionHost = e.host;
  const authEpoch = { current: 0 };
  const selectionSeq = { current: 0 };
  let props: HookProps = {
    selection: { workRef: "WS:FABRIC", rootJobId: "JOB-001" },
    authEpoch, selectionSeq, authRevision: 0, active: true,
  };
  const hook = renderHook((input: HookProps) => useControlRoomSurfaceControls(input), { initialProps: props });
  return {
    e, authEpoch, selectionSeq, result: hook.result,
    update(next: Partial<HookProps> = {}) { props = { ...props, ...next }; hook.rerender(props); },
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
});

describe("render-owned Control Room action admission", () => {
  it.each(["host", "method", "auth", "getState", "generation callback", "generation"] as const)(
    "an old callback cannot adopt a replacement %s with otherwise identical auth",
    async (replacement) => {
      const h = mount();
      const activate = h.result.current.onOpenSurface!;
      const next = fixture();
      if (replacement === "host") window.MastermindMissionHost = next.host;
      else if (replacement === "method") h.e.host.openControlRoomSurface = next.host.openControlRoomSurface;
      else if (replacement === "auth") h.e.host.auth = next.auth;
      else if (replacement === "getState") h.e.auth.getState = next.getState;
      else if (replacement === "generation callback") h.e.host.invalidationGeneration = next.getGeneration;
      else h.e.advanceGeneration();

      await act(async () => { activate(OPEN); });
      expect(h.e.open).not.toHaveBeenCalled();
      expect(next.open).not.toHaveBeenCalled();
      expect(h.result.current.held).toBe(false);
      // The rejected stale scope has no result to expose under its replacement.
      expect(h.result.current.action).toEqual({ state: "WITHHELD", held: false });

      h.update();
      await act(async () => { h.result.current.onOpenSurface!(OPEN); });
      const currentOpen = replacement === "host" || replacement === "method" ? next.open : h.e.open;
      expect(currentOpen).toHaveBeenCalledTimes(1);
      expect(h.result.current.action).toEqual({ state: "RESULT", result: envelope("open") });
    },
  );

  it.each(["auth", "selection"] as const)("rejects a retained callback across a %s ABA before rerender", async (boundary) => {
    const h = mount();
    const activate = h.result.current.onOpenSurface!;
    // The externally owned epoch records both transitions, even though the
    // public auth values / selected tuple are back to their original values.
    const epoch = boundary === "auth" ? h.authEpoch : h.selectionSeq;
    epoch.current += 2;
    await act(async () => { activate(OPEN); });
    expect(h.e.open).not.toHaveBeenCalled();
    expect(h.result.current.held).toBe(false);
  });

  it("reserves the slot before same-render double activation and a reentrant auth callback", async () => {
    const h = mount();
    const pending = deferred();
    h.e.open.mockReturnValueOnce(pending.promise);
    const activate = h.result.current.onOpenSurface!;
    h.e.getState.mockImplementationOnce(() => { activate(OPEN); return SIGNED; });
    await act(async () => { activate(OPEN); activate(OPEN); });
    expect(h.e.open).toHaveBeenCalledTimes(1);
    expect(h.result.current.held).toBe(true);
    await act(async () => { pending.resolve(envelope("open")); });
    expect(h.result.current.held).toBe(false);
  });

  it.each(["open", "bind", "unbind", "refresh-builds"] as const)("invokes only the fixed %s method once", async (operation) => {
    const h = mount();
    await act(async () => {
      if (operation === "open") h.result.current.onOpenSurface!(OPEN);
      else if (operation === "bind") h.result.current.onBindSurface!(BIND);
      else if (operation === "unbind") h.result.current.onUnbindSurface!(OPEN);
      else h.result.current.onRefreshBuilds!();
    });
    const calls = [h.e.open, h.e.bind, h.e.unbind, h.e.refresh];
    const selected = { open: h.e.open, bind: h.e.bind, unbind: h.e.unbind, "refresh-builds": h.e.refresh }[operation];
    for (const method of calls) expect(method).toHaveBeenCalledTimes(method === selected ? 1 : 0);
    const args = selected.mock.calls[0]![0];
    expect(args.signal.aborted).toBe(false);
    if (operation === "refresh-builds") expect(Object.keys(args)).toEqual(["signal"]);
    else {
      const request = operation === "bind" ? BIND : OPEN;
      expect(args.payload).toEqual(request);
      expect(args.payload).not.toBe(request);
    }
  });
});

describe("App-lifetime action custody", () => {
  it("retains one action across navigation and preserves an owner-returned false outcome", async () => {
    const h = mount();
    const pending = deferred();
    h.e.open.mockReturnValueOnce(pending.promise);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    const signal = h.e.open.mock.calls[0]![0].signal;
    h.update({ active: false });
    h.update({ active: true });
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(signal.aborted).toBe(false);
    expect(h.e.open).toHaveBeenCalledTimes(1);
    const returned = envelope("open", { ok: false, failure_kind: "unsupported", detail: "Fixture owner refused." });
    await act(async () => { pending.resolve(returned); });
    expect(h.result.current.action).toEqual({ state: "RESULT", result: returned });
    expect(h.result.current.held).toBe(false);
  });

  it("withholds an old auth scope's result without erasing its eventual qualified settlement", async () => {
    const h = mount();
    const pending = deferred();
    h.e.open.mockReturnValueOnce(pending.promise);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    h.authEpoch.current += 1;
    h.e.advanceGeneration();
    h.update({ authRevision: 1 });
    expect(h.result.current.action).toEqual({ state: "WITHHELD", held: true });
    await act(async () => { h.result.current.onUnbindSurface!(OPEN); });
    expect(h.e.unbind).not.toHaveBeenCalled();
    await act(async () => { pending.resolve(envelope("open", { ok: false, detail: "Old owner outcome" })); });
    expect(h.result.current.action).toEqual({ state: "WITHHELD", held: false });
    expect(h.e.open.mock.calls[0]![0].signal.aborted).toBe(false);
    await act(async () => { h.result.current.onUnbindSurface!(OPEN); });
    expect(h.e.unbind).toHaveBeenCalledTimes(1);
    expect(h.result.current.action).toEqual({ state: "RESULT", result: envelope("unbind") });
  });

  it("keeps an unknown hold across auth, selection, navigation and an independent Discovery read", async () => {
    const h = mount();
    h.e.open.mockRejectedValueOnce(new Error("Fixture response lost"));
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.result.current.action).toEqual({ state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" });
    h.authEpoch.current += 1;
    h.selectionSeq.current += 1;
    h.update({ authRevision: 1, active: false, selection: { workRef: "WS:OTHER", rootJobId: "JOB-002" } });
    h.update({ active: true });
    await act(async () => {
      h.result.current.onOpenSurface!(OPEN);
      h.result.current.onBindSurface!(BIND);
      h.result.current.onUnbindSurface!(OPEN);
      h.result.current.onRefreshBuilds!();
      h.result.current.onDiscover!();
    });
    expect(h.e.open).toHaveBeenCalledTimes(1);
    for (const method of [h.e.bind, h.e.unbind, h.e.refresh]) expect(method).not.toHaveBeenCalled();
    expect(h.result.current.discovery.state).toBe("AVAILABLE");
    expect(h.result.current.action).toEqual({ state: "WITHHELD", held: true });
    expect(h.result.current.held).toBe(true);
  });

  it.each([
    envelope("open", CONTROL_ROOM_UNKNOWN_OUTCOME, "EFFECT_UNKNOWN", 503),
    envelope("open", { ok: false, failure_kind: "effect_unknown", detail: "Original owner cannot qualify its effect." }),
  ])("retains a qualified uncertain $disposition result and keeps its hold", async (returned) => {
    const h = mount();
    h.e.open.mockResolvedValueOnce(returned);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.result.current.action).toEqual({ state: "RESULT", result: returned });
    expect(h.result.current.held).toBe(true);
    await act(async () => { h.result.current.onRefreshBuilds!(); });
    expect(h.e.refresh).not.toHaveBeenCalled();
  });
});

describe("phase-specific action outcome qualification", () => {
  it("classifies a request-inspection exception as NOT_DISPATCHED even if it is a typed unknown error", async () => {
    const h = mount();
    const request = new Proxy({ ...OPEN }, {
      getPrototypeOf() { throw new ControlRoomActionTransportError("open", "EFFECT_UNKNOWN"); },
    });
    await act(async () => { h.result.current.onOpenSurface!(request); });
    expect(h.e.open).not.toHaveBeenCalled();
    expect(h.result.current.action).toEqual({ state: "FAILURE", operation: "open", disposition: "NOT_DISPATCHED" });
    expect(h.result.current.held).toBe(false);
  });

  it("preserves matching NOT_DISPATCHED only from the invoked original method", async () => {
    const h = mount();
    h.e.open.mockRejectedValueOnce(new ControlRoomActionTransportError("open", "NOT_DISPATCHED"));
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.e.open).toHaveBeenCalledTimes(1);
    expect(h.result.current.action).toEqual({ state: "FAILURE", operation: "open", disposition: "NOT_DISPATCHED" });
    expect(h.result.current.held).toBe(false);
  });

  it.each([
    { label: "a foreign-operation typed refusal", error: new ControlRoomActionTransportError("bind", "NOT_DISPATCHED") },
    { label: "an ordinary transport error", error: new Error("Fixture transport failure") },
  ])("does not accept $label as proof of no dispatch", async ({ error }) => {
    const h = mount();
    h.e.open.mockRejectedValueOnce(error);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.result.current.action).toEqual({ state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" });
    expect(h.result.current.held).toBe(true);
  });

  it("never promotes a result-inspection NOT_DISPATCHED exception into an original-owner refusal", async () => {
    const h = mount();
    const value = new Proxy(envelope("open"), {
      get(target, key, receiver) {
        if (key === "status") throw new ControlRoomActionTransportError("open", "NOT_DISPATCHED");
        return Reflect.get(target, key, receiver);
      },
    });
    h.e.open.mockResolvedValueOnce(value);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.result.current.action).toEqual({ state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" });
    expect(h.result.current.held).toBe(true);
  });

  it("holds a returned envelope for a foreign operation as unknown", async () => {
    const h = mount();
    h.e.open.mockResolvedValueOnce(envelope("bind"));
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.result.current.action).toEqual({ state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" });
    expect(h.result.current.held).toBe(true);
  });

  it("preserves a qualified NOT_DISPATCHED envelope, including its actual 409 status", async () => {
    const h = mount();
    const returned = envelope("open", { ok: false, detail: "Original owner's no-provider precondition." }, "NOT_DISPATCHED", 409);
    h.e.open.mockResolvedValueOnce(returned);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); });
    expect(h.result.current.action).toEqual({ state: "RESULT", result: returned });
    expect(h.result.current.held).toBe(false);
  });
});

describe("Discovery READ custody stays separate from actions", () => {
  it("removes an old Discovery document when the next attempt fails before creating a flight", async () => {
    const h = mount();
    await act(async () => { h.result.current.onDiscover!(); });
    expect(h.result.current.discovery.state).toBe("AVAILABLE");
    const discover = h.result.current.onDiscover!;
    delete h.e.host.readControlRoomDiscovery;
    await act(async () => { discover(); });
    expect(h.e.discover).toHaveBeenCalledTimes(1);
    expect(h.result.current.discovery).toEqual({ state: "IDLE" });
  });

  it.each(["resolve", "reject"] as const)("ignores a superseded READ's late %s without aborting an action or clearing a newer READ", async (late) => {
    const h = mount();
    const action = deferred(), oldRead = deferred(), newRead = deferred();
    h.e.open.mockReturnValueOnce(action.promise);
    h.e.discover.mockReturnValueOnce(oldRead.promise).mockReturnValueOnce(newRead.promise);
    await act(async () => { h.result.current.onOpenSurface!(OPEN); h.result.current.onDiscover!(); });
    const actionSignal = h.e.open.mock.calls[0]![0].signal;
    const oldSignal = h.e.discover.mock.calls[0]![0].signal;
    h.update({ active: false });
    expect(oldSignal.aborted).toBe(true);
    expect(actionSignal.aborted).toBe(false);
    h.update({ active: true });
    await act(async () => { h.result.current.onDiscover!(); });
    await act(async () => {
      if (late === "resolve") oldRead.resolve(discoveryDocument("old-private-candidate"));
      else oldRead.reject(new Error("Old fixture read failed"));
    });
    expect(h.result.current.discovery).toEqual({ state: "PENDING" });
    expect(h.e.discover.mock.calls[1]![0].signal.aborted).toBe(false);
    expect(h.result.current.held).toBe(true);
    await act(async () => { newRead.resolve(discoveryDocument("current-candidate")); });
    expect(h.result.current.discovery).toMatchObject({
      state: "AVAILABLE", document: { codex_sessions: [{ session_id: "current-candidate", date: "2026-10-19" }] },
    });
    await act(async () => { action.resolve(envelope("open")); });
    expect(h.result.current.action).toEqual({ state: "RESULT", result: envelope("open") });
    expect(actionSignal.aborted).toBe(false);
  });
});
