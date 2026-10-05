// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { decodeProgramsObservation } from "./programs-observation";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";

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
    for (const route of ["Today", "Work", "Programs", "Fleet & Capacity", "Mission Workspace", "Conversation", "Activity", "Connections", "Evidence"])
      expect(screen.getByRole("button", { name: route })).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(2); // one original collection plus the new exact selection
  });
  it("keeps legacy Programs available without upgrading its missing receipt", async () => {
    window.MastermindMissionHost = { readPrograms: async () => controlRoomFixture() };
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    expect(await screen.findByText("Project facts cannot be displayed from this source.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Open project Beta/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Programs" }));
    expect(await screen.findByRole("button", { name: /Beta program/ })).toBeTruthy();
  });
});
