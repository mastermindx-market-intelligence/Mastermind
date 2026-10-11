// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { navigateCompanyOperation } from "./test-operational-navigation";
import { bindMissionHost, createNativeClient } from "./host";
import { decodeProgramsObservation } from "./programs-observation";
import programsAvailable from "./fixtures/programs-available-workspace-service.json";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import type { AuthState } from "./host";
import workUnavailable from "./fixtures/work-service-unavailable.json";
import workAvailable from "./fixtures/work-service-available.json";

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete window.MastermindMissionHost; });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

describe("Work read recovery in the actual App", () => {
  it("lets the user recover a transient Work failure without signing out or reloading", async () => {
    const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary"))
      .mockResolvedValue(structuredClone(workAvailable));
    window.MastermindMissionHost = {
      readPrograms: async () => controlRoomFixture(), readWork,
    };
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Work");
    expect(await screen.findByText("SOURCE_UNAVAILABLE")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Today" }));
    await navigateCompanyOperation(user, "Work");
    expect(readWork).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Refresh Work" }));
    expect(await screen.findByText("JOB-2")).toBeTruthy();
    expect(screen.queryByText("SOURCE_UNAVAILABLE")).toBeNull();
    expect(readWork).toHaveBeenCalledTimes(2);
  });
  it("recovers a typed owner refusal with a focusable, guarded pending control", async () => {
    const retry = deferred<unknown>();
    const readPrograms = vi.fn(async () => controlRoomFixture());
    const readWork = vi.fn().mockResolvedValueOnce(structuredClone(workUnavailable)).mockReturnValueOnce(retry.promise);
    window.MastermindMissionHost = { readPrograms, readWork };
    const user = userEvent.setup(); render(<App />);
    await navigateCompanyOperation(user, "Work");
    expect(await screen.findByText("projection_refused")).toBeTruthy();
    const button = screen.getByRole<HTMLButtonElement>("button", { name: "Refresh Work" });
    button.focus(); await user.keyboard("{Enter}");
    // jsdom does not reproduce native-disabled browser blur. Assert the DOM
    // contract explicitly; real-browser Enter/Tab/focus proof is separate.
    expect(button.disabled).toBe(false);
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(screen.queryByText("projection_refused")).toBeNull();
    expect(screen.getByText("Reading the bounded Work projection…")).toBeTruthy();
    await user.keyboard("{Enter}");
    expect(readWork).toHaveBeenCalledTimes(2);
    expect(readPrograms).toHaveBeenCalledTimes(1);
    await act(async () => retry.resolve(structuredClone(workAvailable)));
    expect(await screen.findByText("JOB-2")).toBeTruthy();
    expect(document.activeElement).toBe(button);
    expect(button.disabled).toBe(false);
    expect(button.getAttribute("aria-disabled")).toBe("false");
  });

  it("leaves repeated failures retryable without automatically polling", async () => {
    const retry = deferred<unknown>();
    const readWork = vi.fn().mockRejectedValueOnce(new Error("initial")).mockReturnValueOnce(retry.promise)
      .mockResolvedValue(structuredClone(workAvailable));
    window.MastermindMissionHost = { readPrograms: async () => controlRoomFixture(), readWork };
    const user = userEvent.setup(); render(<App />);
    await navigateCompanyOperation(user, "Work");
    await screen.findByText("SOURCE_UNAVAILABLE");
    await user.dblClick(screen.getByRole("button", { name: "Refresh Work" }));
    expect(readWork).toHaveBeenCalledTimes(2);
    await act(async () => retry.reject(new Error("still unavailable")));
    await screen.findByText("SOURCE_UNAVAILABLE");
    expect(screen.queryByText("JOB-2")).toBeNull();
    expect(readWork).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("button", { name: "Refresh Work" }));
    expect(await screen.findByText("JOB-2")).toBeTruthy();
    expect(readWork).toHaveBeenCalledTimes(3);
  });

  it("aborts the retried read on sign-out and ignores its late result", async () => {
    const retry = deferred<unknown>();
    let state: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
    let notify!: (state: AuthState) => void;
    const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary")).mockReturnValueOnce(retry.promise);
    window.MastermindMissionHost = {
      readPrograms: async () => controlRoomFixture(), readWork,
      auth: { getState: () => state, subscribe: listener => { notify = listener; return () => {}; },
        signIn: async () => {}, signOut: async () => {} },
    };
    const user = userEvent.setup(); render(<App />);
    await navigateCompanyOperation(user, "Work");
    await screen.findByText("SOURCE_UNAVAILABLE");
    await user.click(screen.getByRole("button", { name: "Refresh Work" }));
    const signal = readWork.mock.calls[1][0].signal as AbortSignal;
    await act(async () => {
      state = { status: "signed_out", reason: null, acquisition: false, content: false }; notify(state);
    });
    expect(signal.aborted).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Refresh Work" }).disabled).toBe(true);
    await act(async () => retry.resolve(structuredClone(workAvailable)));
    expect(screen.queryByText("JOB-2")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Refresh Work" }));
    expect(readWork).toHaveBeenCalledTimes(2);
  });

  it("does not offer an enabled refresh when the host has no Work reader", async () => {
    window.MastermindMissionHost = { readPrograms: async () => controlRoomFixture() };
    const user = userEvent.setup(); render(<App />);
    await navigateCompanyOperation(user, "Work");
    expect(await screen.findByText("QUALIFIED_WORK_READ_UNAVAILABLE")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Refresh Work" }).disabled).toBe(true);
  });

  it("retains selected project, exact Work filtering and the Office draft on refresh", async () => {
    const data = structuredClone(workAvailable);
    const readWork = vi.fn().mockRejectedValueOnce(new Error("temporary")).mockResolvedValue(data);
    const readProgramsObservation = vi.fn(async () => decodeProgramsObservation({
      ...structuredClone(programsAvailable), control_room: JSON.parse(JSON.stringify(controlRoomFixture()).replaceAll("JOB-A", "JOB-2")),
    }));
    const readMission = vi.fn(async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) => missionFixture(workRef, rootJobId));
    window.MastermindMissionHost = { readProgramsObservation, readMission, readWork };
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    await user.click(await screen.findByRole("button", { name: "Open project Alpha program" }));
    await screen.findByRole("heading", { name: "Mission" });
    await user.click(screen.getByRole("button", { name: "Today" }));
    await user.type(screen.getByRole("textbox", { name: "Direction to Meta-CEO" }), "Keep this direction");
    await user.click(screen.getByRole("button", { name: "Projects" }));
    await user.click(screen.getByRole("button", { name: "Open project Alpha program" }));
    await user.click(screen.getByRole("tab", { name: "Work" }));
    await screen.findByText("SOURCE_UNAVAILABLE");
    const locationBefore = location.href;
    const missionCalls = readMission.mock.calls.length, programCalls = readProgramsObservation.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh Work" }));
    expect(await screen.findByText("Exact project root JOB-2; other roots remain outside this project view.")).toBeTruthy();
    expect(screen.getByText("CHECKPOINTED")).toBeTruthy();
    expect(screen.queryByText("JOB-1")).toBeNull();
    expect(location.href).toBe(locationBefore);
    expect(readWork).toHaveBeenCalledTimes(2);
    expect(readMission).toHaveBeenCalledTimes(missionCalls);
    expect(readProgramsObservation).toHaveBeenCalledTimes(programCalls);
    expect(screen.getByRole("tab", { name: "Work" }).getAttribute("aria-selected")).toBe("true");
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value).toBe("Keep this direction");
  });

  it("uses the actual native read adapter and rejects a retry result from an older same-label auth epoch", async () => {
    const retry = deferred<unknown>(), replacement = deferred<unknown>();
    const signed: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
    let authEvent!: (event: { payload: unknown }) => void;
    let workCalls = 0;
    const invoke = vi.fn(async (command: string) => {
      if (command === "auth_status") return signed;
      if (command === "read_programs") return { ...structuredClone(programsAvailable), control_room: controlRoomFixture() };
      if (command === "read_work") {
        workCalls++;
        if (workCalls === 1) throw new Error("temporary");
        return workCalls === 2 ? retry.promise : replacement.promise;
      }
      throw new Error("No other host command is permitted in this fixture: " + command);
    });
    const client = await createNativeClient(invoke as never, async (event, listener) => {
      if (event === "mastermind-auth-state") authEvent = listener;
      return () => {};
    });
    window.MastermindMissionHost = bindMissionHost(client);
    const user = userEvent.setup(); render(<App />);
    await navigateCompanyOperation(user, "Work");
    await screen.findByText("SOURCE_UNAVAILABLE");
    await user.click(screen.getByRole("button", { name: "Refresh Work" }));
    expect(workCalls).toBe(2);
    await act(async () => authEvent({ payload: signed }));
    await waitFor(() => expect(workCalls).toBe(3));
    await act(async () => retry.resolve(structuredClone(workAvailable)));
    expect(screen.queryByText("JOB-2")).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Refresh Work" }).disabled).toBe(false);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Refresh Work" }).getAttribute("aria-disabled")).toBe("true");
    await act(async () => replacement.resolve(structuredClone(workUnavailable)));
    expect(await screen.findByText("projection_refused")).toBeTruthy();
    expect(screen.queryByText("JOB-2")).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Refresh Work" }).disabled).toBe(false);
    expect(new Set(invoke.mock.calls.map(([command]) => command))).toEqual(new Set(["auth_status", "read_programs", "read_work", "executive_auth_status"]));
  });

});

