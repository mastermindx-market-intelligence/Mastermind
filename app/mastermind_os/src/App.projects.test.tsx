// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { navigateCompanyOperation } from "./test-operational-navigation";
import { decodeProgramsObservation } from "./programs-observation";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const qualifiedPrograms = () => decodeProgramsObservation({
  ...structuredClone(programs), control_room: controlRoomFixture(),
});
const ownerState = () => screen.getByText("OWNER STATE").parentElement!;

beforeEach(() => { history.replaceState(null, "", "/os/"); delete window.MastermindMissionHost; delete (window as any).__TAURI_INTERNALS__; });
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete window.MastermindMissionHost; });
describe("Projects in the actual App", () => {
  it("uses the existing collection, opens its exact root and preserves all legacy destinations", async () => {
    const read = vi.fn(async () => decodeProgramsObservation({ ...structuredClone(programs), control_room: controlRoomFixture() }));
    const mission = vi.fn(async ({ workRef, rootJobId }: { workRef: string; rootJobId: string }) => missionFixture(workRef, rootJobId));
    window.MastermindMissionHost = { readProgramsObservation: read, readMission: mission };
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    expect(await screen.findByRole("heading", { name: "Your projects, in perspective." })).toBeTruthy();
    await user.click(await screen.findByRole("button", { name: "Open project Beta program" }));
    await waitFor(() => expect(mission).toHaveBeenCalledTimes(1));
    expect(mission.mock.calls[0][0]).toMatchObject({ workRef: "WS:BETA", rootJobId: "JOB-B" });
    expect(new URLSearchParams(location.search).get("work_ref")).toBe("WS:BETA");
    expect(new URLSearchParams(location.search).get("root_job_id")).toBe("JOB-B");
    await user.click(screen.getByRole("button", { name: "Projects" }));
    expect(await screen.findByRole("region", { name: "Selected project" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Today" }));
    for (const route of ["Today", "Work", "Open Programs", "Fleet & Capacity", "Mission Workspace", "Conversation", "Activity", "Connections", "Evidence"])
      expect(screen.getByRole("button", { name: route })).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(2); // one original collection plus the new exact selection
  });
  it("keeps legacy Programs available without upgrading its missing receipt", async () => {
    window.MastermindMissionHost = { readPrograms: async () => controlRoomFixture() };
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    expect(await screen.findByText("Project facts cannot be displayed from this source.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Open project Beta/ })).toBeNull();
    await navigateCompanyOperation(user, "Programs");
    expect(await screen.findByRole("button", { name: /Beta program/ })).toBeTruthy();
  });
  it("moves keyboard focus from a removed project card to the heading, including same-pair reopen", async () => {
    const alpha = deferred<unknown>(), beta = deferred<unknown>(), retry = deferred<unknown>();
    const read = vi.fn(async () => qualifiedPrograms());
    const mission = vi.fn().mockReturnValueOnce(alpha.promise).mockReturnValueOnce(beta.promise).mockReturnValueOnce(retry.promise);
    window.MastermindMissionHost = { readProgramsObservation: read, readMission: mission };
    const user = userEvent.setup(); render(<App />);
    const projects = screen.getByRole("button", { name: "Projects" });
    await user.click(projects);
    const openAlpha = await screen.findByRole("button", { name: "Open project Alpha program" });
    openAlpha.focus(); await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Projects", level: 1 }));
    await act(async () => alpha.resolve(missionFixture("WS:ALPHA", "JOB-A")));
    await user.click(projects);
    expect(document.activeElement).toBe(projects);
    const openBeta = await screen.findByRole("button", { name: "Open project Beta program" });
    openBeta.focus(); await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Projects", level: 1 }));
    await act(async () => beta.reject(new Error("private host detail")));
    expect(location.search).toContain("root_job_id=JOB-B");
    expect(screen.queryByRole("heading", { name: "Alpha program" })).toBeNull();
    await user.click(projects);
    const reopen = await screen.findByRole("button", { name: "Open project Beta program" });
    reopen.focus(); await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Projects", level: 1 }));
    const plan = screen.getByRole("tab", { name: "Plan" });
    await user.click(plan); expect(document.activeElement).toBe(plan);
    projects.focus();
    await act(async () => retry.resolve(missionFixture("WS:BETA", "JOB-B")));
    expect(document.activeElement).toBe(projects);
    expect(read).toHaveBeenCalledTimes(3);
    expect(mission).toHaveBeenCalledTimes(3);
    expect(mission.mock.calls.map(([pair]) => [pair.workRef, pair.rootJobId])).toEqual([
      ["WS:ALPHA", "JOB-A"], ["WS:BETA", "JOB-B"], ["WS:BETA", "JOB-B"],
    ]);
  });
  it("ends the pending owner state after read failure on every project tab and retries only on reopen", async () => {
    const first = deferred<unknown>(), retry = deferred<unknown>();
    const read = vi.fn(async () => qualifiedPrograms());
    const mission = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(retry.promise);
    window.MastermindMissionHost = { readProgramsObservation: read, readMission: mission };
    const user = userEvent.setup(); render(<App />);
    const projects = screen.getByRole("button", { name: "Projects" });
    await user.click(projects);
    await user.click(await screen.findByRole("button", { name: "Open project Beta program" }));
    expect(ownerState().textContent).toContain("SOURCE READ PENDING");
    await user.click(screen.getByRole("tab", { name: "Plan" }));
    await act(async () => first.reject(new Error("private host detail")));
    for (const name of ["Overview", "Plan", "Work", "Evidence", "More"]) {
      await user.click(screen.getByRole("tab", { name }));
      expect(ownerState().textContent).toContain("UNAVAILABLE");
      expect(ownerState().textContent).not.toContain("PENDING");
      expect(screen.getByText("MISSION ROOT").parentElement?.textContent).toContain("JOB-B");
      expect(screen.queryByText("private host detail")).toBeNull();
    }
    expect(mission).toHaveBeenCalledTimes(1);
    await user.click(projects);
    await user.click(await screen.findByRole("button", { name: "Open project Beta program" }));
    expect(ownerState().textContent).toContain("SOURCE READ PENDING");
    await act(async () => retry.resolve(missionFixture("WS:BETA", "JOB-B")));
    expect(ownerState().textContent).toContain("PARTIAL");
    expect(ownerState().textContent).not.toContain("PENDING");
    expect(read).toHaveBeenCalledTimes(2);
    expect(mission).toHaveBeenCalledTimes(2);
    expect(location.search).toContain("work_ref=WS%3ABETA");
    expect(location.search).toContain("root_job_id=JOB-B");
  });

  it("preserves an unavailable owner document and never calls an absent reader pending", async () => {
    const unavailable = missionFixture("WS:BETA", "JOB-B");
    unavailable.read_state.state = "UNAVAILABLE";
    window.MastermindMissionHost = {
      readProgramsObservation: async () => qualifiedPrograms(),
      readMission: async () => unavailable,
    };
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    await user.click(await screen.findByRole("button", { name: "Open project Beta program" }));
    await waitFor(() => expect(ownerState().textContent).toContain("UNAVAILABLE"));
    expect(ownerState().closest("section")?.textContent).toContain("Beta program");
    cleanup(); history.replaceState(null, "", "/os/");
    window.MastermindMissionHost = { readProgramsObservation: async () => qualifiedPrograms() };
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    await user.click(await screen.findByRole("button", { name: "Open project Beta program" }));
    await waitFor(() => expect(ownerState().textContent).toContain("UNAVAILABLE"));
    expect(screen.getByText("QUALIFIED_HOST_READ_UNAVAILABLE")).toBeTruthy();
    expect(ownerState().textContent).not.toContain("PENDING");
  });

});
