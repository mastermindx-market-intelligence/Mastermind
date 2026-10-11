// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AuthState } from "./host";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import { navigateCompanyOperation } from "./test-operational-navigation";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import type { EffectReceipt, OperationPointer, OwnerContext, PendingPointerStore } from "./orchestration/operation-controller";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue({ version: "0.1.0", source_revision: "a".repeat(40), build_identity: "test", transport: "UNCONFIGURED", state: "BUILT_NOT_PROVEN" }) }));
const original: OperationPointer = { operationKey: "retained-original-operation", kind: "launch", targetKey: "opaque-original-target" };
const signedIn: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
const signedOut: AuthState = { status: "signed_out", reason: null, acquisition: false, content: false };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(yes => { resolve = yes; });
  return { promise, resolve };
};
function fixture(pointer: OperationPointer | null = original, emptyCatalog = false) {
  let ctx: OwnerContext | null = { principalScope: "owner-a", generation: "gen-1" };
  let auth = signedIn;
  let authListener = (_state: AuthState) => {};
  const data = new Map<string, OperationPointer>(pointer ? [["owner-a", pointer]] : []);
  const store: PendingPointerStore = {
    read: scope => data.get(scope) ?? null,
    reserve: (scope, value) => {
      const saved = data.get(scope);
      if (saved) return { reserved: false, pointer: saved };
      data.set(scope, value);
      return { reserved: true };
    },
    clearIfEqual: vi.fn((scope, value) => {
      const saved = data.get(scope);
      if (!saved || saved.operationKey !== value.operationKey || saved.kind !== value.kind || saved.targetKey !== value.targetKey) return false;
      data.delete(scope);
      return true;
    }),
  };
  const prepare = vi.fn((intent): OperationPointer => ({ operationKey: "new-operation", kind: intent.kind, targetKey: intent.targetKey }));
  const publication = vi.fn();
  const submit = vi.fn(async (value): Promise<EffectReceipt> => {
    publication(value);
    return { ...value, disposition: "accepted", missionSelection: { workRef: "WS:NEW", rootJobId: "JOB-NEW" } };
  });
  const readOperation = vi.fn(async (value: OperationPointer): Promise<EffectReceipt> => ({ ...value, disposition: "accepted", ...(value.kind === "launch" ? { missionSelection: { workRef: "WS:ORIGINAL", rootJobId: "JOB-ORIGINAL" } } : {}) }));
  const binding: OrchestratorCommandBinding = {
    port: { context: () => ctx, prepare, submit, readOperation }, store,
    getView: () => ({ projects: emptyCatalog ? [] : [{ ref: "project", label: "Project" }], profiles: emptyCatalog ? [] : [{ ref: "profile", label: "Profile" }], session: null }),
    subscribe: () => () => {},
    makeLaunchIntent: form => ({ kind: "launch", targetKey: "new-target", payload: { ...form } }),
    makeMessageIntent: () => null, makeStopIntent: () => null,
  };
  window.MastermindMissionHost = {
    commandBinding: binding, readPrograms: async () => controlRoomFixture(),
    readMission: async ({ workRef, rootJobId }) => missionFixture(workRef, rootJobId),
    auth: { getState: () => auth, subscribe: fn => { authListener = fn; return () => {}; }, signIn: async () => {}, signOut: async () => {} },
  };
  return { binding, store, data, prepare, submit, publication, readOperation,
    setCtx: (value: OwnerContext | null) => { ctx = value; },
    notify: (value: AuthState) => { auth = value; authListener(value); },
  };
}
beforeEach(() => { history.replaceState(null, "", "/os/"); delete window.MastermindMissionHost; });
afterEach(() => { cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks(); });

describe("status-only operation reopen", () => {
  it("fresh App mount discovers the original launch and explicit status opens its exact accepted mission without publication", async () => {
    const made = fixture(); render(<App />);
    const check = await screen.findByRole("button", { name: "Check status" });
    expect(screen.getByText(original.operationKey)).toBeTruthy();
    expect(made.readOperation).not.toHaveBeenCalled();
    await userEvent.setup().click(check);
    await waitFor(() => expect(window.location.search).toBe("?work_ref=WS%3AORIGINAL&root_job_id=JOB-ORIGINAL"));
    expect(made.readOperation).toHaveBeenCalledWith(original, expect.any(AbortSignal));
    expect(made.data.has("owner-a")).toBe(false);
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    expect(made.publication).not.toHaveBeenCalled();
  });
  it("recovers a launch even when its catalogs are unavailable", async () => {
    const made = fixture(original, true); render(<App />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(window.location.search).toContain("root_job_id=JOB-ORIGINAL"));
    expect(made.submit).not.toHaveBeenCalled();
  });
  it("unknown and not-found status preserve the exact pointer and permit another status check", async () => {
    const made = fixture();
    made.readOperation.mockResolvedValueOnce({ ...original, disposition: "unknown" })
      .mockResolvedValueOnce({ ...original, disposition: "unknown", reason: "not_found" });
    render(<App />);
    for (let i = 0; i < 2; i++) {
      await userEvent.setup().click(await screen.findByRole("button", { name: "Check status" }));
      await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(i + 1));
      await waitFor(() => expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false));
      expect(made.data.get("owner-a")).toEqual(original);
      expect(window.location.search).toBe("");
    }
    expect(screen.queryByText("not_found")).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(window.location.search).toContain("root_job_id=JOB-ORIGINAL"));
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.publication).not.toHaveBeenCalled();
  });
  it("an empty successful discovery leaves ordinary launch available", async () => {
    const made = fixture(null); render(<App />);
    const user = userEvent.setup();
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "A new ordinary launch");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(window.location.search).toContain("root_job_id=JOB-NEW"));
    expect(screen.queryByRole("button", { name: "Check status" })).toBeNull();
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.publication).toHaveBeenCalledTimes(1);
    expect(made.readOperation).not.toHaveBeenCalled();
  });
  it("failed discovery holds commands until a read-only retry proves the store empty", async () => {
    const made = fixture(null);
    const read = vi.fn().mockRejectedValueOnce(new Error("private-store-error")).mockResolvedValue(null);
    made.store.read = read;
    render(<App />);
    await screen.findByRole("button", { name: "Check status" });
    const user = userEvent.setup();
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Only after recovery");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    expect(made.submit).not.toHaveBeenCalled();
    expect(screen.queryByText("private-store-error")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Check status" })).toBeNull());
    expect(made.readOperation).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
  });
  it("a failed discovery followed by qualified accepted launch status opens the original mission", async () => {
    const made = fixture();
    made.store.read = vi.fn().mockRejectedValueOnce(new Error("store-temporarily-unavailable")).mockImplementation(scope => made.data.get(scope) ?? null);
    render(<App />);
    await screen.findByText("LOCAL_UNAVAILABLE");
    await userEvent.setup().click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(window.location.search).toBe("?work_ref=WS%3AORIGINAL&root_job_id=JOB-ORIGINAL"));
    expect(made.data.has("owner-a")).toBe(false);
    expect(made.readOperation).toHaveBeenCalledWith(original, expect.any(AbortSignal));
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });
  it("local busy after selection invalidation preserves recovery and blocks Launch until the retained operation is resolved", async () => {
    const made = fixture(); const oldResult = deferred<EffectReceipt>();
    made.readOperation.mockImplementationOnce(() => oldResult.promise);
    render(<App />); const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(1));
    act(() => { history.pushState(null, "", "/os/?work_ref=WS%3AALPHA&root_job_id=JOB-A"); window.dispatchEvent(new PopStateEvent("popstate")); });
    await screen.findByText(original.operationKey);
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Do not replace the unresolved operation");
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(screen.queryByText("OPERATION_BUSY")).toBeTruthy());
    expect(screen.getByText(original.operationKey)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false);
    expect(made.data.get("owner-a")).toEqual(original);
    expect(made.store.clearIfEqual).not.toHaveBeenCalled();
    await act(async () => oldResult.resolve({ ...original, disposition: "unknown" }));
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(window.location.search).toContain("JOB-ORIGINAL"));
    expect(made.submit).not.toHaveBeenCalled();
  });
  it.each(["/os/", "/os/?work_ref=WS%3AALPHA&root_job_id=JOB-A"])("same-tuple navigation at %s preserves recovery and blocks a filled Launch", async location => {
    history.replaceState(null, "", location);
    const made = fixture(); render(<App />); const user = userEvent.setup();
    await screen.findByText(original.operationKey);
    act(() => { history.pushState(null, "", location); window.dispatchEvent(new PopStateEvent("popstate")); });
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Retain the original operation");
    expect(await screen.findByRole("button", { name: "Check status" })).toBeTruthy();
    expect(screen.getByText(original.operationKey)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled")).toBe(true);
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.readOperation).not.toHaveBeenCalled();
    expect(made.data.get("owner-a")).toEqual(original);
  });
  it("a retained pointer blocks Launch while leaving the unsent draft editable and status usable", async () => {
    const made = fixture(); render(<App />);
    await screen.findByText(original.operationKey);
    const user = userEvent.setup();
    await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Keep this unsent draft");
    expect(screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled")).toBe(true);
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Keep this unsent draft");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    expect(made.prepare).not.toHaveBeenCalled();
    made.readOperation.mockResolvedValueOnce({ ...original, disposition: "refused" });
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled")).toBe(false));
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Keep this unsent draft");
    expect(made.submit).not.toHaveBeenCalled();
  });
  it("malformed storage remains failclosed without revealing extra stored content", async () => {
    const made = fixture();
    made.store.read = () => ({ ...original, payload: "private-persisted-payload" } as OperationPointer);
    render(<App />);
    await screen.findByText("MALFORMED_POINTER");
    expect(screen.queryByText(original.operationKey)).toBeNull();
    expect(screen.queryByText("private-persisted-payload")).toBeNull();
    const user = userEvent.setup(); await navigateCompanyOperation(user, "Work");
    await user.type(screen.getByLabelText("Goal"), "Do not launch over malformed storage");
    expect(screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(false));
    expect(made.readOperation).not.toHaveBeenCalled();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.data.get("owner-a")).toEqual(original);
  });
  it.each(["message", "stop"] as const)("restores a %s using its original kind and never opens a launch mission", async kind => {
    const pointer = { ...original, kind };
    const made = fixture(pointer); render(<App />);
    await screen.findByText(original.operationKey);
    expect(screen.getByText(new RegExp(`Original ${kind} reference`))).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.data.has("owner-a")).toBe(false));
    expect(window.location.search).toBe("");
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });
  it.each(["signout", "owner", "generation", "binding"])("ignores a late discovery after %s changes", async change => {
    const made = fixture();
    const read = deferred<OperationPointer | null>();
    made.store.read = scope => scope === "owner-a" ? read.promise : null;
    const page = render(<App />);
    if (change === "signout") act(() => made.notify(signedOut));
    if (change === "owner") { made.setCtx({ principalScope: "owner-b", generation: "gen-2" }); page.rerender(<App />); }
    if (change === "generation") { made.setCtx({ principalScope: "owner-a", generation: "gen-2" }); made.store.read = () => null; page.rerender(<App />); }
    if (change === "binding") { window.MastermindMissionHost!.commandBinding = { ...made.binding, store: { ...made.store, read: () => null } }; page.rerender(<App />); }
    await act(async () => read.resolve(original));
    expect(screen.queryByText(original.operationKey)).toBeNull();
    expect(made.readOperation).not.toHaveBeenCalled();
    expect(made.data.get("owner-a")).toEqual(original);
  });
  it.each(["signout", "owner", "generation", "binding", "selection", "unmount"])("a late status receipt cannot navigate or clear retained owner state after %s", async change => {
    const made = fixture(); const result = deferred<EffectReceipt>();
    made.readOperation.mockImplementation(() => result.promise);
    const page = render(<App />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(1));
    if (change === "signout") act(() => made.notify(signedOut));
    if (change === "owner") { made.setCtx({ principalScope: "owner-b", generation: "gen-2" }); page.rerender(<App />); }
    if (change === "generation") { made.setCtx({ principalScope: "owner-a", generation: "gen-2" }); page.rerender(<App />); }
    if (change === "binding") { window.MastermindMissionHost!.commandBinding = { ...made.binding, store: { ...made.store, read: () => null } }; page.rerender(<App />); }
    if (change === "selection") act(() => { history.pushState(null, "", "/os/?work_ref=WS%3AALPHA&root_job_id=JOB-A"); window.dispatchEvent(new PopStateEvent("popstate")); });
    if (change === "unmount") page.unmount();
    await act(async () => result.resolve({ ...original, disposition: "accepted", missionSelection: { workRef: "WS:ORIGINAL", rootJobId: "JOB-ORIGINAL" } }));
    expect(window.location.search).not.toContain("JOB-ORIGINAL");
    expect(made.data.get("owner-a")).toEqual(original);
    expect(made.store.clearIfEqual).not.toHaveBeenCalled();
    expect(made.publication).not.toHaveBeenCalled();
  });
  it("reauthentication rediscovers the same principal's original pointer without replay", async () => {
    const made = fixture(); render(<App />);
    await screen.findByText(original.operationKey);
    act(() => { made.setCtx(null); made.notify(signedOut); });
    expect(screen.queryByText(original.operationKey)).toBeNull();
    act(() => { made.setCtx({ principalScope: "owner-a", generation: "gen-2" }); made.notify(signedIn); });
    await userEvent.setup().click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(window.location.search).toContain("JOB-ORIGINAL"));
    expect(made.submit).not.toHaveBeenCalled();
  });
  it("an old binding's completed status cannot clear the replacement pointer or release its in-flight control", async () => {
    const made = fixture(); const oldResult = deferred<EffectReceipt>();
    made.readOperation.mockImplementation(() => oldResult.promise);
    const page = render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Check status" }));
    await waitFor(() => expect(made.readOperation).toHaveBeenCalledTimes(1));
    const replacementPointer: OperationPointer = { operationKey: "replacement-operation", kind: "launch", targetKey: "replacement-target" };
    const replacementResult = deferred<EffectReceipt>();
    const replacementRead = vi.fn(() => replacementResult.promise);
    const replacementData = new Map([["owner-a", replacementPointer]]);
    const replacementClear = vi.fn(() => { replacementData.delete("owner-a"); return true; });
    window.MastermindMissionHost!.commandBinding = { ...made.binding,
      port: { ...made.binding.port, readOperation: replacementRead },
      store: { ...made.store, read: scope => replacementData.get(scope) ?? null, clearIfEqual: replacementClear },
    };
    page.rerender(<App />);
    await screen.findByText(replacementPointer.operationKey);
    await user.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(replacementRead).toHaveBeenCalledTimes(1));
    await act(async () => oldResult.resolve({ ...original, disposition: "accepted", missionSelection: { workRef: "WS:ORIGINAL", rootJobId: "JOB-ORIGINAL" } }));
    expect(screen.getByRole("button", { name: "Check status" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(replacementPointer.operationKey)).toBeTruthy();
    expect(replacementData.get("owner-a")).toEqual(replacementPointer);
    expect(replacementClear).not.toHaveBeenCalled();
    expect(made.data.get("owner-a")).toEqual(original);
    expect(window.location.search).toBe("");
    await act(async () => replacementResult.resolve({ ...replacementPointer, disposition: "accepted", missionSelection: { workRef: "WS:REPLACEMENT", rootJobId: "JOB-REPLACEMENT" } }));
    await waitFor(() => expect(window.location.search).toContain("JOB-REPLACEMENT"));
    expect(made.submit).not.toHaveBeenCalled();
  });
});
