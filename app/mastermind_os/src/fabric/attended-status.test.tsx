// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { bindMissionHost, type AuthState, type RawClient } from "../host";
import { attendedSelection, decodeAttendedStatus } from "./attended-status";
import { AttendedFabricInspector } from "./AttendedFabricInspector";

afterEach(cleanup);
const selected = { rootId: "source-root", runId: "source-run" };
const raw = () => ({ schema: "mastermind.fabric_task_status.v1", run_id: "source-run", root_id: "source-root", parent_run_id: "source-root",
  state: "TERMINAL", rc: 0, signal: "ok", result_available: true, result_bytes: 3672, accepted: false, accepted_by: null,
  acceptance_state: "NOT_ACCEPTED", acceptance_reason: "NO_OUTCOME" });
function client(read = vi.fn(async () => raw())) {
  let state: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null }, gen = 0;
  const listeners: Array<(s: AuthState) => void> = [];
  const c: RawClient = { getState: () => state, invalidationGeneration: () => gen,
    subscribe: fn => { listeners.push(fn); return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); }; },
    signIn: async () => {}, signOut: async () => {}, readPrograms: async () => null, readWork: async () => null,
    readMission: async () => null, readCurrentWindow: async () => null, readAttendedFabric: read };
  return { c, read, change: (next = state) => { state = next; gen++; listeners.forEach(fn => fn(state)); } };
}
const enter = () => {
  fireEvent.click(screen.getByText("Direct M2 Fabric · inspect an existing run"));
  fireEvent.change(screen.getByLabelText("Original root"), { target: { value: "source-root" } });
  fireEvent.change(screen.getByLabelText("Existing run ID"), { target: { value: "source-run" } });
};

describe("direct Fabric status-only boundary", () => {
  it("uses selectors, not paths, commands or guessed Executive IDs", () => {
    expect(attendedSelection(selected)).toEqual(selected);
    for (const bad of ["../root", "run;whoami", "a\n", "a".repeat(129), ""]) expect(attendedSelection({ rootId: "ok", runId: bad })).toBeNull();
  });
  it("strips controller output, prompts, credentials and arbitrary extra fields", () => {
    const projected = decodeAttendedStatus({ ...raw(), prompt: "PRIVATE", controller_observation: { path: "/private" }, token: "SECRET" }, selected);
    expect(JSON.stringify(projected)).not.toContain("PRIVATE"); expect(projected).not.toHaveProperty("controller_observation");
    expect(projected).not.toHaveProperty("token");
  });
  it("does not translate terminal success into acceptance", () => {
    expect(decodeAttendedStatus(raw(), selected).accepted).toBe(false);
    expect(() => decodeAttendedStatus({ ...raw(), accepted: true }, selected)).toThrow("FABRIC_ACCEPTANCE_CONFLICT");
    expect(() => decodeAttendedStatus({ ...raw(), accepted: true, accepted_by: "none", acceptance_state: "ACCEPTED" }, selected)).toThrow();
    expect(decodeAttendedStatus({ ...raw(), accepted: true, accepted_by: "reviewer", acceptance_state: "ACCEPTED" }, selected).accepted).toBe(true);
  });
  it("preserves explicit rejected outcome and unknown lineage", () => {
    expect(decodeAttendedStatus({ ...raw(), accepted_by: "none", acceptance_reason: "OUTCOME_NOT_ACCEPTED" }, selected).accepted_by).toBe("none");
    const d = decodeAttendedStatus({ ...raw(), state: "ACTIVE_OR_WAITING", root_id: null, parent_run_id: null, rc: null, signal: null,
      accepted: null, acceptance_state: "UNVERIFIED", result_available: false, result_bytes: null }, selected);
    expect(d.state).toBe("ACTIVE_OR_WAITING"); expect(d.root_id).toBeNull();
  });
  it("refuses mismatched run/root and malformed numerical values", () => {
    expect(() => decodeAttendedStatus({ ...raw(), root_id: "another-root" }, selected)).toThrow("FABRIC_ROOT_MISMATCH");
    for (const extra of [{ run_id: "other-run" }, { rc: NaN }, { result_bytes: -1 }, { result_bytes: 1.5 }, { result_available: false, result_bytes: 100 }, { accepted_by: "CEO" }])
      expect(() => decodeAttendedStatus({ ...raw(), ...extra }, selected)).toThrow();
  });
  it("does not expose a reader on unconfigured clients", () => {
    const a = client(); delete a.c.readAttendedFabric;
    expect(bindMissionHost(a.c).readAttendedFabric).toBeUndefined();
    const host = bindMissionHost(a.c);
    const subscribe = vi.spyOn(host.auth!, "subscribe");
    render(<AttendedFabricInspector host={host} />);
    expect(screen.getByText(/No authorized direct Fabric reader/)).toBeTruthy(); expect(a.read).not.toHaveBeenCalled();
    expect(subscribe).not.toHaveBeenCalled();
  });
  it("withholds the port when source identity invalidation is not available", () => {
    const a = client(); delete a.c.invalidationGeneration;
    expect(bindMissionHost(a.c).readAttendedFabric).toBeUndefined();
  });
  it("requires existing acquisition permission before any source read", async () => {
    const a = client(); a.change({ status: "signed_out", acquisition: false, content: false, reason: null });
    await expect(bindMissionHost(a.c).readAttendedFabric!({ ...selected, signal: new AbortController().signal })).rejects.toThrow("FABRIC_READ_UNAUTHORIZED");
    expect(a.read).not.toHaveBeenCalled();
  });
  it("rejects a reply after same-display-state identity generation changes", async () => {
    let resolve!: (value: ReturnType<typeof raw>) => void;
    const a = client(vi.fn(() => new Promise(r => { resolve = r; }))); const host = bindMissionHost(a.c);
    const promise = host.readAttendedFabric!({ ...selected, signal: new AbortController().signal }); a.change(); resolve(raw());
    await expect(promise).rejects.toThrow("READ_CANCELLED");
  });
  it("rejects an aborted read before acquiring source", async () => {
    const a = client(), abort = new AbortController(); abort.abort();
    await expect(bindMissionHost(a.c).readAttendedFabric!({ ...selected, signal: abort.signal })).rejects.toThrow("READ_CANCELLED");
    expect(a.read).not.toHaveBeenCalled();
  });
  it("reads only on explicit inspection and renders same-run metadata", async () => {
    const a = client(); render(<AttendedFabricInspector host={bindMissionHost(a.c)} />); enter();
    expect(a.read).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "Inspect run" }));
    await waitFor(() => expect(screen.getByText("NOT_ACCEPTED")).toBeTruthy());
    expect(a.read).toHaveBeenCalledTimes(1); expect(screen.getByText("3672")).toBeTruthy();
    expect(screen.getByText(/not proof of worker START/)).toBeTruthy();
  });
  it("discards delayed replies after selection changes", async () => {
    let resolve!: (value: ReturnType<typeof raw>) => void;
    const a = client(vi.fn(() => new Promise(r => { resolve = r; }))); render(<AttendedFabricInspector host={bindMissionHost(a.c)} />); enter();
    fireEvent.click(screen.getByRole("button", { name: "Inspect run" }));
    fireEvent.change(screen.getByLabelText("Existing run ID"), { target: { value: "other-run" } }); resolve(raw());
    await waitFor(() => expect(screen.getByRole("button", { name: "Inspect run" })).toBeTruthy());
    expect(screen.queryByText("3672")).toBeNull();
  });
});
