// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { flushSync } from "react-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, createNativeClient } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import programsFixture from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import work from "./fixtures/work-service-available.json";

const signed = { status: "signed_in", reason: null, acquisition: true, content: true };
async function ownerFixture() {
  const envelope = structuredClone(programsFixture), room = controlRoomFixture();
  room.work = [room.work[0]]; room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = paired.selection.work_ref;
  room.work[0].agent_os.workstream = "FABRIC"; room.work[0].agent_os.title = "Current project source";
  Object.assign(room.autonomy.responsibilities[0], { responsibility_ref: paired.selection.work_ref,
    root_job_id: paired.selection.root_job_id, root_job_candidates: [paired.selection.root_job_id],
    root_job_ambiguous: false, runtime_root_state: "RESOLVED" });
  const mission = structuredClone(paired.mission); mission.program.title = "Private owner project";
  mission.program.next_action = "Read the exact owner return.";
  let notify!: (event: { payload: unknown }) => void, hold = false;
  const held: Array<() => void> = [];
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    const response = command === "read_programs" ? { ...envelope, control_room: room }
      : command === "read_mission_v3" ? mission : command === "read_work" ? work : paired.window;
    return hold ? new Promise(resolve => held.push(() => resolve(structuredClone(response)))) : structuredClone(response);
  });
  const client = await createNativeClient(invoke as never, async (_event, listener) => { notify = listener; return () => {}; });
  return { host: bindMissionHost(client), invoke, notify, hold: () => { hold = true; }, settle: () => held.forEach(resolve => resolve()) };
}
beforeEach(async () => {
  history.replaceState(null, "", "/os/?work_ref=WS%3AFABRIC&root_job_id=JOB-001");
  delete (window as any).__TAURI_INTERNALS__; delete window.MastermindMissionHost;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto"); vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost; });

describe("actual Today owner projection", () => {
  it("waits for the native companion's collection before reading the Mission", async () => {
    const e = await ownerFixture(), read = e.host.readProgramsObservation!;
    let release!: () => void;
    e.host.readProgramsObservation = request => new Promise((resolve, reject) => {
      release = () => { read(request).then(resolve, reject); };
    });
    delete e.host.readPrograms;
    window.MastermindMissionHost = e.host;
    (window as any).__TAURI_INTERNALS__ = { invoke: vi.fn(async () => ({})) };
    render(<App />);
    await waitFor(() => expect(release).toBeTypeOf("function"));
    expect(e.invoke.mock.calls.filter(([command]) => command === "read_mission_v3")).toHaveLength(0);
    await act(async () => release());
    await waitFor(() => expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent).toContain("Private owner project"));
    expect(e.invoke.mock.calls.filter(([command]) => command === "read_mission_v3")).toHaveLength(1);
  });
  it("accepts a native host with only the qualified Programs companion", async () => {
    const e = await ownerFixture();
    delete e.host.readPrograms;
    window.MastermindMissionHost = e.host;
    (window as any).__TAURI_INTERNALS__ = { invoke: vi.fn(async () => ({})) };
    render(<App />);
    await waitFor(() => expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent).toContain("Private owner project"));
    expect(e.invoke.mock.calls.filter(([command]) => command === "read_programs")).toHaveLength(1);
    await userEvent.setup().click(screen.getByRole("button", { name: "Review sources" }));
    expect(screen.getByRole("complementary", { name: "Source evidence" }).textContent).toContain("programs-owner-observation:v1:");
  });
  it("renders Atelier from the existing owner reads and preserves every legacy route", async () => {
    const e = await ownerFixture(); window.MastermindMissionHost = e.host; render(<App />);
    const answer = await screen.findByRole("region", { name: "Meta-CEO answer" });
    await waitFor(() => expect(answer.textContent).toContain("Read the exact owner return."));
    expect(answer.textContent).toContain("Private owner project");
    expect(e.invoke.mock.calls.filter(([command]) => command === "read_programs")).toHaveLength(1);
    await userEvent.setup().click(screen.getByRole("button", { name: "Review sources" }));
    expect(screen.getByRole("complementary", { name: "Source evidence" }).textContent).toContain("programs-owner-observation:v1:");
    for (const route of ["Today", "Work", "Programs", "Fleet & Capacity", "Mission Workspace", "Conversation", "Activity", "Connections", "Evidence"])
      expect(screen.getByRole("button", { name: route })).toBeTruthy();
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });
  it("withdraws the real Office answer, sources and draft in the first auth commit", async () => {
    const e = await ownerFixture(); window.MastermindMissionHost = e.host; render(<App />);
    await waitFor(() => expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent).toContain("Private owner project"));
    await userEvent.setup().type(screen.getByRole("textbox", { name: "Direction to Meta-CEO" }), "Private unsent direction");
    await userEvent.setup().click(screen.getByRole("button", { name: "Review sources" }));
    e.hold();
    try {
      flushSync(() => e.notify({ payload: signed }));
      expect(document.body.textContent).not.toContain("Private owner project");
      expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value).toBe("");
      expect(screen.queryByRole("complementary", { name: "Source evidence" })).toBeNull();
    } finally { await act(async () => { e.settle(); for (let n = 0; n < 20; n++) await Promise.resolve(); }); }
  });
  it("keeps an unsent direction through legacy navigation without a second read", async () => {
    const e = await ownerFixture(); window.MastermindMissionHost = e.host; render(<App />);
    await waitFor(() => expect(within(screen.getByRole("region", { name: "Meta-CEO answer" })).getByText("Read the exact owner return.")).toBeTruthy());
    const user = userEvent.setup(); await user.type(screen.getByRole("textbox", { name: "Direction to Meta-CEO" }), "Keep this thought");
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value).toBe("Keep this thought");
    expect(e.invoke.mock.calls.filter(([command]) => command === "read_programs")).toHaveLength(1);
  });
  it("keeps the Programs receipt and draft when reopening the same exact project", async () => {
    const e = await ownerFixture(); window.MastermindMissionHost = e.host; render(<App />);
    await waitFor(() => expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent).toContain("Private owner project"));
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Direction to Meta-CEO" }), "Same project thought");
    await user.click(screen.getByRole("button", { name: "Programs" }));
    await user.click(await screen.findByRole("button", { name: /Current project source/ }));
    await user.click(screen.getByRole("button", { name: "Today" }));
    await user.click(screen.getByRole("button", { name: "Review sources" }));
    expect(screen.getByRole("complementary", { name: "Source evidence" }).textContent).toContain("programs-owner-observation:v1:");
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value).toBe("Same project thought");
    expect(e.invoke.mock.calls.filter(([command]) => command === "read_programs")).toHaveLength(1);
  });
});
