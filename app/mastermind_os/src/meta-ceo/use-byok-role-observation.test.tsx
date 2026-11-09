// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthState, MissionHost } from "../host";
import { BYOK_ROLES_SCHEMA, type ByokRolesRead } from "./byok-roles-read";
import { useByokRoleObservation } from "./use-byok-role-observation";

let authState: AuthState;
let generation: number;
let host: MissionHost;
const active = { active: true, acquisition: true, authRevision: 1 };
function observed(timestamp = Date.now()): ByokRolesRead {
  return {
    schema: BYOK_ROLES_SCHEMA, state: "OBSERVED", reason_code: "OBSERVED",
    roles: [
      { role: "mmmeta", state: "CONFIGURATION_OBSERVED", requested_provider: "zai", requested_model: "glm-5.3" },
      { role: "mmsecretary", state: "ABSENT", requested_provider: null, requested_model: null },
    ],
    source_observation: { host_binding_sha256: "a".repeat(64), host_boot_id: "12345678-1234-1234-1234-123456789abc",
      implementation_sha: "b".repeat(40), metadata_sha256: "c".repeat(64), observed_at_ms: timestamp },
    proof: { credentials_read: false, provider_called: false, service_observed: false,
      served_model_verified: false, credential_enrollment: "UNVERIFIED" },
  };
}
function deferred() {
  let resolve!: (value: ByokRolesRead) => void;
  const promise = new Promise<ByokRolesRead>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => {
  authState = { status: "signed_in", reason: null, acquisition: true, content: true };
  generation = 1;
  host = {
    readByokRoles: vi.fn(async () => observed()),
    invalidationGeneration: () => generation,
    auth: { getState: () => authState, subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {} },
  };
  window.MastermindMissionHost = host;
});
afterEach(() => { cleanup(); vi.useRealTimers(); delete window.MastermindMissionHost; });

describe("Office BYOK observation", () => {
  it("reads the fixed role pair once on Office entry, through the existing host", async () => {
    const view = renderHook(props => useByokRoleObservation(props), { initialProps: { ...active, active: false } });
    expect(view.result.current.state).toBe("SOURCE_UNBOUND");
    expect(host.readByokRoles).not.toHaveBeenCalled();
    view.rerender(active);
    await waitFor(() => expect(view.result.current.state).toBe("OBSERVED"));
    expect(host.readByokRoles).toHaveBeenCalledTimes(1);
    expect(view.result.current.body?.roles[0]?.requested_model).toBe("glm-5.3");
    expect(Object.isFrozen(view.result.current.body)).toBe(true);
    view.rerender({ ...active });
    expect(host.readByokRoles).toHaveBeenCalledTimes(1);
  });

  it("does not acquire while signed out and clears visible metadata on authorization change", async () => {
    const view = renderHook(props => useByokRoleObservation(props), { initialProps: active });
    await waitFor(() => expect(view.result.current.state).toBe("OBSERVED"));
    authState = { ...authState, status: "signed_out", acquisition: false };
    view.rerender({ ...active, acquisition: false, authRevision: 2 });
    expect(view.result.current.state).toBe("UNAVAILABLE");
    expect(view.result.current.body).toBeNull();
    act(() => view.result.current.refresh());
    expect(host.readByokRoles).toHaveBeenCalledTimes(1);
  });

  it("keeps missing source distinct from an observed absent configuration", async () => {
    delete host.readByokRoles;
    const view = renderHook(() => useByokRoleObservation(active));
    expect(view.result.current.state).toBe("SOURCE_UNBOUND");
    expect(view.result.current.body).toBeNull();
    expect(view.result.current.canRefresh).toBe(false);
  });

  it("passes a validated SOURCE_UNBOUND response without inventing role rows", async () => {
    host.readByokRoles = vi.fn(async (): Promise<ByokRolesRead> => ({ ...observed(), state: "SOURCE_UNBOUND", reason_code: "SOURCE_UNBOUND",
      roles: [], source_observation: null }));
    const view = renderHook(() => useByokRoleObservation(active));
    await waitFor(() => expect(view.result.current.state).toBe("SOURCE_UNBOUND"));
    expect(view.result.current.body?.roles).toEqual([]);
  });

  it.each([30_001, -5_001])("refuses a publication outside its original freshness window: %s", async age => {
    vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-05T13:00:00Z"));
    host.readByokRoles = vi.fn(async () => observed(Date.now() - age));
    const view = renderHook(() => useByokRoleObservation(active));
    await act(async () => {});
    expect(view.result.current.state).toBe("UNAVAILABLE");
    expect(view.result.current.body).toBeNull();
  });

  it("expires visible evidence without polling, then permits one explicit refresh", async () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-05T13:00:00Z"));
    const view = renderHook(() => useByokRoleObservation(active));
    await act(async () => {});
    expect(view.result.current.state).toBe("OBSERVED");
    act(() => vi.advanceTimersByTime(30_001));
    expect(view.result.current.state).toBe("UNAVAILABLE");
    expect(view.result.current.body).toBeNull();
    expect(host.readByokRoles).toHaveBeenCalledTimes(1);
    act(() => view.result.current.refresh());
    await act(async () => {});
    expect(view.result.current.state).toBe("OBSERVED");
    expect(host.readByokRoles).toHaveBeenCalledTimes(2);
  });

  it("discards a late response from an earlier auth generation", async () => {
    const old = deferred(), next = deferred();
    const read = vi.fn().mockReturnValueOnce(old.promise).mockReturnValueOnce(next.promise);
    host.readByokRoles = read;
    const view = renderHook(props => useByokRoleObservation(props), { initialProps: active });
    await act(async () => {});
    const firstSignal = read.mock.calls[0][0].signal as AbortSignal;
    generation = 2;
    view.rerender({ ...active, authRevision: 2 });
    await act(async () => { old.resolve(observed()); });
    expect(firstSignal.aborted).toBe(true);
    expect(view.result.current.state).toBe("LOADING");
    expect(view.result.current.body).toBeNull();
    await act(async () => { next.resolve(observed()); });
    expect(view.result.current.state).toBe("OBSERVED");
  });

  it.each(["host", "method", "generation", "auth"])('discards source replacement during acquisition: %s', async change => {
    const pending = deferred(), next = deferred();
    host.readByokRoles = vi.fn().mockReturnValueOnce(pending.promise).mockReturnValue(next.promise);
    const view = renderHook(() => useByokRoleObservation(active));
    await act(async () => {});
    if (change === "host") window.MastermindMissionHost = { ...host, readByokRoles: () => next.promise };
    if (change === "method") host.readByokRoles = vi.fn(() => next.promise);
    if (change === "generation") generation = 2;
    if (change === "auth") authState = { ...authState, status: "signed_out", acquisition: false };
    await act(async () => { pending.resolve(observed()); });
    expect(view.result.current.body).toBeNull();
  });

  it("aborts on view exit and never lets a late result repopulate the Office", async () => {
    const pending = deferred();
    const read = vi.fn(() => pending.promise); host.readByokRoles = read;
    const view = renderHook(props => useByokRoleObservation(props), { initialProps: active });
    await act(async () => {});
    const signal = (read.mock.calls[0] as unknown as [{signal: AbortSignal}])[0].signal;
    view.rerender({ ...active, active: false });
    expect(signal.aborted).toBe(true);
    await act(async () => { pending.resolve(observed()); });
    expect(view.result.current.state).toBe("SOURCE_UNBOUND");
    expect(view.result.current.body).toBeNull();
  });
});
