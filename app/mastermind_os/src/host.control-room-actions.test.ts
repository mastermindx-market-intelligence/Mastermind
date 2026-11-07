import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, type RawClient, type AuthState } from "./host";
import {
  CONTROL_ROOM_UNKNOWN_OUTCOME,
  ControlRoomActionTransportError,
} from "./control-room";

const signed: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
function fixture() {
  let state = signed, generation = 0;
  const listeners = new Set<(value: AuthState) => void>();
  const client: RawClient = {
    getState: () => state, invalidationGeneration: () => generation,
    subscribe(fn) { listeners.add(fn); return () => { listeners.delete(fn); }; },
    signIn: async () => {}, signOut: async () => {},
    readPrograms: async () => ({}), readWork: async () => ({}),
    readMission: async () => ({}), readCurrentWindow: async () => ({}),
  };
  return { client, change(next = signed) {
    state = next; generation++; for (const fn of listeners) fn(state);
  } };
}
const response = (operation = "open", disposition = "OWNER_RETURNED", status = 200,
  outcome: unknown = { ok: true }) => ({
  schema: "mastermind.workspace_control_room_action_result.v1",
  operation, disposition, status, outcome,
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
};

describe("optional Control Room methods on the existing MissionHost", () => {
  it("does not manufacture action or discovery capabilities for an uncomposed client", () => {
    const { client } = fixture();
    const host = bindMissionHost(client);
    for (const key of ["readControlRoomDiscovery", "openControlRoomSurface",
      "bindControlRoomSurface", "unbindControlRoomSurface", "refreshControlRoomBuilds"]) {
      expect(Object.hasOwn(host, key)).toBe(false);
    }
  });
  it("detaches an Open payload and preserves its explicit owed-context presence", async () => {
    const e = fixture();
    const original = response();
    e.client.openControlRoomSurface = vi.fn(async request => {
      expect(Object.isFrozen(request.payload)).toBe(true);
      expect(Object.hasOwn(request.payload, "owed_context")).toBe(true);
      return original;
    });
    const host = bindMissionHost(e.client);
    const payload = { binding_id: "original", owed_context: null };
    const decoded = await host.openControlRoomSurface!({
      payload, signal: new AbortController().signal,
    });
    expect(decoded).toEqual(original);
    expect(e.client.openControlRoomSurface).toHaveBeenCalledTimes(1);
    expect(vi.mocked(e.client.openControlRoomSurface!).mock.calls[0]![0].payload).not.toBe(payload);
  });
  it.each(["aborted", "signed_out", "malformed"])("refuses %s before invoking a raw action", async defect => {
    const e = fixture();
    e.client.openControlRoomSurface = vi.fn(async () => response());
    const host = bindMissionHost(e.client);
    const controller = new AbortController();
    if (defect === "aborted") controller.abort();
    if (defect === "signed_out") e.change({ ...signed, status: "signed_out", acquisition: false });
    await expect(host.openControlRoomSurface!({
      payload: { binding_id: defect === "malformed" ? "" : "original" },
      signal: controller.signal,
    })).rejects.toMatchObject({ operation: "open", disposition: "NOT_DISPATCHED" });
    expect(e.client.openControlRoomSurface).not.toHaveBeenCalled();
  });
  it("preserves the captured request's qualified outcome across later epoch and abort", async () => {
    const e = fixture(), delayed = deferred<unknown>();
    e.client.openControlRoomSurface = vi.fn(() => delayed.promise);
    const host = bindMissionHost(e.client), controller = new AbortController();
    const pending = host.openControlRoomSurface!({ payload: { binding_id: "original" }, signal: controller.signal });
    e.change();
    controller.abort();
    const original = response("open", "OWNER_RETURNED", 200, { ok: true, verified: false });
    delayed.resolve(original);
    expect(await pending).toEqual(original);
    expect(e.client.openControlRoomSurface).toHaveBeenCalledTimes(1);
  });
  it("retains typed preflight failure from the fixed client and qualifies other call failures conservatively", async () => {
    const e = fixture();
    e.client.openControlRoomSurface = vi.fn(async () => {
      throw new ControlRoomActionTransportError("open", "NOT_DISPATCHED");
    });
    const host = bindMissionHost(e.client);
    await expect(host.openControlRoomSurface!({ payload: { binding_id: "original" },
      signal: new AbortController().signal })).rejects.toMatchObject({ disposition: "NOT_DISPATCHED" });
    e.client.openControlRoomSurface = vi.fn(async () => { throw new Error("response lost"); });
    // A replaced raw method invalidates this host capability before invocation.
    await expect(host.openControlRoomSurface!({ payload: { binding_id: "original" },
      signal: new AbortController().signal })).rejects.toMatchObject({ disposition: "NOT_DISPATCHED" });
    const rebound = bindMissionHost(e.client);
    await expect(rebound.openControlRoomSurface!({ payload: { binding_id: "original" },
      signal: new AbortController().signal })).rejects.toMatchObject({ disposition: "EFFECT_UNKNOWN" });
  });
  it("withholds a malformed or differently named return after one call as uncertain", async () => {
    const e = fixture();
    e.client.openControlRoomSurface = vi.fn(async () => response("bind"));
    const host = bindMissionHost(e.client);
    await expect(host.openControlRoomSurface!({ payload: { binding_id: "original" },
      signal: new AbortController().signal })).rejects.toMatchObject({ disposition: "EFFECT_UNKNOWN" });
    expect(e.client.openControlRoomSurface).toHaveBeenCalledTimes(1);
  });
  it("preserves a qualified explicit unknown owner receipt", async () => {
    const e = fixture();
    const unknown = response("open", "EFFECT_UNKNOWN", 503, CONTROL_ROOM_UNKNOWN_OUTCOME);
    e.client.openControlRoomSurface = vi.fn(async () => unknown);
    expect(await bindMissionHost(e.client).openControlRoomSurface!({
      payload: { binding_id: "original" }, signal: new AbortController().signal,
    })).toEqual(unknown);
  });

  it("refuses an authority transition during payload preflight", async () => {
    const e = fixture(), action = vi.fn(async () => response());
    e.client.openControlRoomSurface = action;
    const host = bindMissionHost(e.client);
    let changed = false;
    const payload = new Proxy({ binding_id: "original" }, {
      ownKeys(target) {
        if (!changed) { changed = true; e.change(); }
        return Reflect.ownKeys(target);
      },
    });
    await expect(host.openControlRoomSurface!({ payload,
      signal: new AbortController().signal })).rejects.toMatchObject({
      operation: "open", disposition: "NOT_DISPATCHED",
    });
    expect(action).not.toHaveBeenCalled();
  });
  it("refuses an authority transition during the state callback", async () => {
    const e = fixture(), action = vi.fn(async () => response());
    e.client.openControlRoomSurface = action;
    const host = bindMissionHost(e.client);
    e.client.getState = () => { e.change(); return signed; };
    await expect(host.openControlRoomSurface!({ payload: { binding_id: "original" },
      signal: new AbortController().signal })).rejects.toMatchObject({
      operation: "open", disposition: "NOT_DISPATCHED",
    });
    expect(action).not.toHaveBeenCalled();
  });
  it.each(["epoch", "method", "generation_callback"])(
    "rechecks %s after the final generation callback returns", async transition => {
      const e = fixture(), action = vi.fn(async () => response());
      const replacement = vi.fn(async () => response());
      e.client.openControlRoomSurface = action;
      let armed = false, calls = 0;
      e.client.invalidationGeneration = () => {
        if (armed && ++calls === 2) {
          if (transition === "epoch") e.change({ ...signed, reason: "new authority" });
          if (transition === "method") e.client.openControlRoomSurface = replacement;
          if (transition === "generation_callback") e.client.invalidationGeneration = () => 0;
        }
        return 0;
      };
      const host = bindMissionHost(e.client);
      armed = true;
      await expect(host.openControlRoomSurface!({ payload: { binding_id: "original" },
        signal: new AbortController().signal })).rejects.toMatchObject({
        operation: "open", disposition: "NOT_DISPATCHED",
      });
      expect(action).not.toHaveBeenCalled();
      expect(replacement).not.toHaveBeenCalled();
    },
  );
  it("rechecks the state callback identity after payload preflight", async () => {
    const e = fixture(), action = vi.fn(async () => response());
    e.client.openControlRoomSurface = action;
    const host = bindMissionHost(e.client);
    const payload = new Proxy({ binding_id: "original" }, {
      ownKeys(target) {
        e.client.getState = () => signed;
        return Reflect.ownKeys(target);
      },
    });
    await expect(host.openControlRoomSurface!({ payload,
      signal: new AbortController().signal })).rejects.toMatchObject({
      operation: "open", disposition: "NOT_DISPATCHED",
    });
    expect(action).not.toHaveBeenCalled();
  });
  it("classifies a foreign typed preflight exception under this operation", async () => {
    const e = fixture(), action = vi.fn(async () => response());
    e.client.openControlRoomSurface = action;
    const host = bindMissionHost(e.client);
    const payload = new Proxy({ binding_id: "original" }, {
      ownKeys() { throw new ControlRoomActionTransportError("bind", "EFFECT_UNKNOWN"); },
    });
    await expect(host.openControlRoomSurface!({ payload,
      signal: new AbortController().signal })).rejects.toMatchObject({
      operation: "open", disposition: "NOT_DISPATCHED",
    });
    expect(action).not.toHaveBeenCalled();
  });
  it("does not adopt a different operation's typed no-dispatch claim", async () => {
    const e = fixture(), action = vi.fn(async () => {
      throw new ControlRoomActionTransportError("bind", "NOT_DISPATCHED");
    });
    e.client.openControlRoomSurface = action;
    await expect(bindMissionHost(e.client).openControlRoomSurface!({
      payload: { binding_id: "original" }, signal: new AbortController().signal,
    })).rejects.toMatchObject({ operation: "open", disposition: "EFFECT_UNKNOWN" });
    expect(action).toHaveBeenCalledTimes(1);
  });
  it("does not turn a post-return status exception into a no-dispatch claim", async () => {
    const e = fixture(), returned = response();
    Object.defineProperty(returned, "status", { enumerable: true, get() {
      throw new ControlRoomActionTransportError("open", "NOT_DISPATCHED");
    } });
    const action = vi.fn(async () => returned);
    e.client.openControlRoomSurface = action;
    await expect(bindMissionHost(e.client).openControlRoomSurface!({
      payload: { binding_id: "original" }, signal: new AbortController().signal,
    })).rejects.toMatchObject({ operation: "open", disposition: "EFFECT_UNKNOWN" });
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("maps Bind, Unbind and Refresh builds to their one fixed raw method", async () => {
    const e = fixture();
    e.client.bindControlRoomSurface = vi.fn(async () => response("bind"));
    e.client.unbindControlRoomSurface = vi.fn(async () => response("unbind"));
    e.client.refreshControlRoomBuilds = vi.fn(async () => response("refresh-builds"));
    const host = bindMissionHost(e.client), signal = new AbortController().signal;
    const bind = { work_ref: "WS:ONE", role: "worker", provider: "codex", locator: { session_id: "existing" } };
    await host.bindControlRoomSurface!({ payload: bind, signal });
    await host.unbindControlRoomSurface!({ payload: { binding_id: "original" }, signal });
    await host.refreshControlRoomBuilds!({ signal });
    expect(e.client.bindControlRoomSurface).toHaveBeenCalledExactlyOnceWith({ payload: bind, signal });
    expect(e.client.unbindControlRoomSurface).toHaveBeenCalledExactlyOnceWith({ payload: { binding_id: "original" }, signal });
    expect(e.client.refreshControlRoomBuilds).toHaveBeenCalledExactlyOnceWith({ signal });
  });
});

describe("independent Control Room Discovery observation on MissionHost", () => {
  const document = () => ({
    chatgpt_environments: { multilogin: [], gologin: [] },
    claude_code_sessions: [], codex_sessions: [],
    cursor: { supported: false, note: "Existing candidates only" },
  });
  it("decodes and detaches one original read without manufacturing action methods", async () => {
    const e = fixture(), raw = document();
    const read = vi.fn(async () => raw);
    e.client.readControlRoomDiscovery = read;
    const host = bindMissionHost(e.client), signal = new AbortController().signal;
    const result = await host.readControlRoomDiscovery!({ signal });
    expect(result).toEqual(raw);
    expect(result).not.toBe(raw);
    expect(Object.isFrozen(result.cursor)).toBe(true);
    expect(read).toHaveBeenCalledExactlyOnceWith({ signal });
    expect(Object.hasOwn(host, "openControlRoomSurface")).toBe(false);
  });
  it("withholds malformed Discovery through the fixed unavailable error", async () => {
    const e = fixture(), read = vi.fn(async () => ({ private_note: "not display data" }));
    e.client.readControlRoomDiscovery = read;
    await expect(bindMissionHost(e.client).readControlRoomDiscovery!({
      signal: new AbortController().signal,
    })).rejects.toThrow("CONTROL_ROOM_DISCOVERY_UNAVAILABLE");
    expect(read).toHaveBeenCalledTimes(1);
  });
  it.each(["auth", "abort"] as const)("discards a late read after %s changes", async transition => {
    const e = fixture(), delayed = deferred<unknown>();
    e.client.readControlRoomDiscovery = vi.fn(() => delayed.promise);
    const host = bindMissionHost(e.client), controller = new AbortController();
    const pending = host.readControlRoomDiscovery!({ signal: controller.signal });
    if (transition === "auth") e.change(); else controller.abort();
    delayed.resolve(document());
    await expect(pending).rejects.toThrow("READ_CANCELLED");
  });
  it("checks currentness after the returned observation is decoded", async () => {
    const e = fixture();
    const raw = new Proxy(document(), {
      ownKeys(target) { e.change(); return Reflect.ownKeys(target); },
    });
    e.client.readControlRoomDiscovery = vi.fn(async () => raw);
    await expect(bindMissionHost(e.client).readControlRoomDiscovery!({
      signal: new AbortController().signal,
    })).rejects.toThrow("READ_CANCELLED");
  });
  it("requires acquisition before calling the original read", async () => {
    const e = fixture(), read = vi.fn(async () => document());
    e.client.readControlRoomDiscovery = read;
    const host = bindMissionHost(e.client);
    e.change({ ...signed, acquisition: false });
    await expect(host.readControlRoomDiscovery!({
      signal: new AbortController().signal,
    })).rejects.toThrow("DISCOVERY_READ_UNAUTHORIZED");
    expect(read).not.toHaveBeenCalled();
  });
});
