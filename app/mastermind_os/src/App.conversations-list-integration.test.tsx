// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, createNativeClient } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";

const signed = { status: "signed_in", reason: null, acquisition: true, content: true };
beforeEach(async () => {
  history.replaceState(null, "", `/os/?work_ref=${paired.selection.work_ref}&root_job_id=${paired.selection.root_job_id}`);
  delete window.MastermindMissionHost; delete (window as any).__TAURI_INTERNALS__;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost; });

async function prepare() {
  const room = controlRoomFixture(), row = structuredClone(room.work[0]);
  row.work_ref = paired.selection.work_ref; row.agent_os.workstream = paired.selection.work_ref.slice(3);
  row.agent_os.title = "Qualified conversation project"; room.work = [row];
  const responsibility = structuredClone(room.autonomy.responsibilities[0]);
  Object.assign(responsibility, { responsibility_ref: paired.selection.work_ref,
    root_job_id: paired.selection.root_job_id, root_job_candidates: [paired.selection.root_job_id],
    root_job_ambiguous: false, runtime_root_state: "RESOLVED" });
  room.autonomy.responsibilities = [responsibility];
  const invoke = vi.fn(async (name: string) => {
    if (name === "auth_status") return signed;
    if (name === "executive_auth_status") return { generation: 0, available: false };
    if (name === "read_programs") return { ...structuredClone(programs), control_room: room };
    if (name === "read_mission_v3") return structuredClone(paired.mission);
    if (name === "read_current_window") return structuredClone(paired.window);
    throw new Error("Unexpected fixed fixture command");
  });
  const raw = await createNativeClient(invoke as never, async () => () => {}), host = bindMissionHost(raw);
  delete host.readProjectArchive; delete host.readProjectArchivePage;
  let content: boolean | null = null, generationDelta = 0;
  const state = host.auth!.getState, generation = host.invalidationGeneration!;
  // Stable public receivers are installed before acquisition. Changing a
  // returned value later tests revocation, rather than method replacement.
  vi.spyOn(host.auth!, "getState").mockImplementation(() => {
    const current = state.call(host.auth); return content === null ? current : { ...current, content };
  });
  vi.spyOn(host, "invalidationGeneration").mockImplementation(() => generation.call(host) + generationDelta);
  window.MastermindMissionHost = host;
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Conversations" }));
  const open = await screen.findByRole("button", { name: "Open conversation: Current conversation" });
  await screen.findByRole("button", { name: "Open project Qualified conversation project" });
  const list = within(document.querySelector(".conversations-list") as HTMLElement);
  return { invoke, host, raw, list, open, revokeContent: () => { content = false; }, driftGeneration: () => { generationDelta++; } };
}
function noWrite(invoke: ReturnType<typeof vi.fn>) {
  expect(invoke.mock.calls.filter(([name]) => /send|submit|create|launch|consume|pause|resume|adopt/.test(name))).toHaveLength(0);
}

it("joins global index→exact current detail→Back preserving local query, unsent draft and row focus", async () => {
  const e = await prepare();
  expect(e.list.getByRole("heading", { level: 1 }).textContent).toBe("Conversations");
  expect(screen.queryByText(paired.window.view.items.find(item => item.text)!.text!)).toBeNull();
  fireEvent.change(e.list.getByRole("searchbox"), { target: { value: paired.selection.work_ref } });
  fireEvent.click(e.open);
  await screen.findByText(paired.window.view.items.find(item => item.text)!.text!);
  expect(document.querySelector(".conversations-list")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Unsent notes" }), { target: { value: "Original unsent note" } });
  fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
  expect(screen.getByRole("searchbox")).toHaveProperty("value", paired.selection.work_ref);
  expect(screen.getByText("Unsent draft")).toBeTruthy();
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open conversation: Current conversation" }));
  noWrite(e.invoke);
});

it("opens a project through the real rootless catalogue route and restores list query/focus without changing the selected Runtime root", async () => {
  const e = await prepare(), before = location.href;
  fireEvent.change(e.list.getByRole("searchbox"), { target: { value: "Qualified" } });
  fireEvent.click(e.list.getByRole("button", { name: "Open project Qualified conversation project" }));
  await screen.findByRole("button", { name: "Back to conversations" });
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  expect(location.href).toBe(before);
  fireEvent.click(screen.getByRole("button", { name: "Back to conversations" }));
  expect(screen.getByRole("searchbox")).toHaveProperty("value", "Qualified");
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open project Qualified conversation project" }));
  expect(e.invoke.mock.calls.filter(([name]) => /references|history/.test(name))).toHaveLength(0);
  noWrite(e.invoke);
});

it("refuses a current row after no-render Content withdrawal while keeping project Acquisition distinct", async () => {
  const e = await prepare();
  e.revokeContent();
  fireEvent.click(e.open); // no notification or render between revoke and click
  expect(document.querySelector(".conversations-list")).not.toBeNull();
  expect(screen.queryByText(paired.window.view.items.find(item => item.text)!.text!)).toBeNull();
  expect(screen.getByText("This source is no longer current. Refresh this view before opening it.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Open project Qualified conversation project" }));
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  noWrite(e.invoke);
});

it("does not requalify cached catalogue/window metadata after no-notify host generation drift and an unrelated render", async () => {
  const e = await prepare();
  e.driftGeneration();
  fireEvent.click(e.open); // stale captured handler cannot navigate
  expect(document.querySelector(".conversations-list")).not.toBeNull();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Qualified" } });
  await waitFor(() => expect(screen.queryByRole("button", { name: "Open project Qualified conversation project" })).toBeNull());
  expect(screen.queryByRole("button", { name: "Open conversation: Current conversation" })).toBeNull();
  noWrite(e.invoke);
});
