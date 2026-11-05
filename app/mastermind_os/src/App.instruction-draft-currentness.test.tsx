// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, createNativeClient } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import instruction from "./instructions/fixtures/instruction-owner.json";
import { decodeWindow, observedMissionAssociation } from "./workspace-contract";
import { decodeMissionv3 } from "./mission";

const workRef = "WS:ONE", originalDraft = "Original current instruction draft";
const signed = { status: "signed_in", reason: null, acquisition: true, content: true };
beforeEach(async () => {
  delete window.MastermindMissionHost; delete (window as any).__TAURI_INTERNALS__;
  history.replaceState(null, "", "/os/");
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost; });

async function prepare({ foreignConversation = false } = {}) {
  const room = controlRoomFixture(), row = structuredClone(room.work[0]);
  row.work_ref = workRef; row.agent_os.workstream = workRef.slice(3);
  row.agent_os.title = "Qualified instruction project"; room.work = [row];
  const responsibility = structuredClone(room.autonomy.responsibilities[0]);
  Object.assign(responsibility, { responsibility_ref: workRef, root_job_id: paired.selection.root_job_id,
    root_job_candidates: [paired.selection.root_job_id], root_job_ambiguous: false, runtime_root_state: "RESOLVED" });
  room.autonomy.responsibilities = [responsibility];
  history.replaceState(null, "", `/os/?work_ref=${workRef}&root_job_id=${paired.selection.root_job_id}`);
  const destination = foreignConversation ? structuredClone(paired)
    : JSON.parse(JSON.stringify(paired).replaceAll(paired.selection.work_ref, workRef)) as typeof paired;
  const selection = { workRef, rootJobId: paired.selection.root_job_id };
  const association = observedMissionAssociation(await decodeWindow(destination.window),
    decodeMissionv3(destination.mission, selection), selection);
  expect(association === null).toBe(foreignConversation);
  const invoke = vi.fn(async (name: string, args?: unknown) => {
    if (name === "auth_status") return signed;
    if (name === "executive_auth_status") return { generation: 0, available: false };
    if (name === "read_programs") return { ...structuredClone(programs), control_room: room };
    if (name === "read_mission_v3") return structuredClone(destination.mission);
    if (name === "read_current_window") return structuredClone(destination.window);
    if (name === "read_project_instructions") {
      expect(args).toEqual({ selection: { work_ref: workRef } }); return structuredClone(instruction.project_current);
    }
    throw new Error("Unexpected fixed fixture command");
  });
  const client = await createNativeClient(invoke as never, async () => () => {});
  const host = bindMissionHost(client);
  delete host.readProjectArchive; delete host.readProjectArchivePage;
  window.MastermindMissionHost = host;
  render(<App />);
  if (!foreignConversation) {
    fireEvent.click(screen.getByRole("button", { name: "Conversations" }));
    await screen.findByText(destination.window.view.items.find(item => item.text)!.text!);
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Unsent notes" }), { target: { value: originalDraft } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Projects" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open project Qualified instruction project" }));
  fireEvent.click(await screen.findByRole("button", { name: "Project details" }));
  fireEvent.click(screen.getByRole("button", { name: "Read instructions" }));
  fireEvent.click(await screen.findByRole("button", { name: /Review instruction:/ }));
  const change = screen.getByRole("button", { name: "Change in conversation" });
  return { host, invoke, change };
}
function draftText() {
  fireEvent.click(screen.getByRole("button", { name: "Conversations" }));
  if (!screen.queryByRole("textbox", { name: "Unsent notes" }))
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
  return (screen.getByRole("textbox", { name: "Unsent notes" }) as HTMLTextAreaElement).value;
}
function noPublication(invoke: ReturnType<typeof vi.fn>) {
  expect(invoke.mock.calls.some(([name]) => /submit|prepare|send|create|source_operation|pause|resume/.test(String(name)))).toBe(false);
}
it("adds only to the genuine current owner/work draft through the existing revision witness", async () => {
  const e = await prepare(); expect((e.change as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(e.change);
  const text = draftText();
  expect(text.startsWith(originalDraft + "\n\n")).toBe(true);
  expect(text).toContain("“Review the project carefully.”");
  expect(text).toContain("INS:DAILY-ONE");
  noPublication(e.invoke);
});
it("refuses no-render CONTENT revocation while Acquisition and the rendered instruction remain current", async () => {
  const e = await prepare(); expect((e.change as HTMLButtonElement).disabled).toBe(false);
  const state = vi.spyOn(e.host.auth!, "getState").mockReturnValue({ ...signed, content: false } as never);
  // No notify(), rerender(), helper substitution, or route change precedes the gesture.
  fireEvent.click(e.change);
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  state.mockRestore();
  expect(draftText()).toBe(originalDraft); noPublication(e.invoke);
});
it("refuses same-host generation drift without a notification or replacement destination", async () => {
  const e = await prepare(), previous = e.host.invalidationGeneration!();
  const generation = vi.spyOn(e.host, "invalidationGeneration").mockReturnValue(previous + 1);
  fireEvent.click(e.change);
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  generation.mockRestore();
  expect(draftText()).toBe(originalDraft); noPublication(e.invoke);
});
it("refuses an unwitnessed host-owner replacement even with identical public auth flags and generation", async () => {
  const e = await prepare();
  const replacement = { ...e.host, auth: e.host.auth };
  window.MastermindMissionHost = replacement;
  fireEvent.click(e.change);
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  window.MastermindMissionHost = e.host;
  expect(draftText()).toBe(originalDraft); noPublication(e.invoke);
});
it("keeps instruction reading independent but never supplies a draft callback for a foreign Mission/window tuple", async () => {
  const e = await prepare({ foreignConversation: true });
  expect(screen.getAllByText("Review the project carefully.").length).toBeGreaterThan(0);
  expect((e.change as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(e.change);
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_project_instructions")).toHaveLength(1);
  noPublication(e.invoke);
});
