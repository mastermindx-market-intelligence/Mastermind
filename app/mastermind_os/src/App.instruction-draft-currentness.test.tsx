// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { openObservedConversation } from "./test-operational-navigation";
const gesture = {click: async (element: HTMLElement) => {fireEvent.click(element);}};
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
    await openObservedConversation(gesture);
    await screen.findByText(destination.window.view.items.find(item => item.text)!.text!);
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Unsent notes" }), { target: { value: originalDraft } });
  }
  fireEvent.click(screen.getByRole("button", { name: "Projects" }));
  fireEvent.click(await screen.findByRole("button", { name: "Open project Qualified instruction project" }));
  fireEvent.click(await screen.findByRole("button", { name: "Project details" }));
  // The details navigator hides each owner until its overview button chooses
  // it; choosing Standing instructions is presentation-only and reads nothing.
  fireEvent.click(screen.getByRole("button", { name: "Standing instructions" }));
  fireEvent.click(screen.getByRole("button", { name: "Read instructions" }));
  fireEvent.click(await screen.findByRole("button", { name: /Review instruction:/ }));
  const change = screen.getByRole("button", { name: "Change in conversation" });
  return { host, invoke, change };
}
async function draftText() {
  await openObservedConversation(gesture);
  if (!screen.queryByRole("textbox", { name: "Unsent notes" }))
    fireEvent.click(screen.getByRole("button", { name: "Unsent notes" }));
  return (screen.getByRole("textbox", { name: "Unsent notes" }) as HTMLTextAreaElement).value;
}
function noPublication(invoke: ReturnType<typeof vi.fn>) {
  // This fixed context command is a READ, independently of the source writer.
  // Every prepare/submit/send or other source-operation call remains forbidden.
  expect(invoke.mock.calls.filter(([name]) => name !== "read_source_operation_context" &&
    /submit|prepare|send|create|source_operation|pause|resume/.test(String(name))).map(([name])=>name)).toEqual([]);
}
it("adds only to the genuine current owner/work draft through the existing revision witness", async () => {
  const e = await prepare(); expect((e.change as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(e.change);
  const text = await draftText();
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
  expect(await draftText()).toBe(originalDraft); noPublication(e.invoke);
});
it("refuses same-host generation drift without a notification or replacement destination", async () => {
  const e = await prepare(), previous = e.host.invalidationGeneration!();
  const generation = vi.spyOn(e.host, "invalidationGeneration").mockReturnValue(previous + 1);
  fireEvent.click(e.change);
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  generation.mockRestore();
  expect(await draftText()).toBe(originalDraft); noPublication(e.invoke);
});
it("refuses an unwitnessed host-owner replacement even with identical public auth flags and generation", async () => {
  const e = await prepare();
  const replacement = { ...e.host, auth: e.host.auth };
  window.MastermindMissionHost = replacement;
  fireEvent.click(e.change);
  expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
  window.MastermindMissionHost = e.host;
  expect(await draftText()).toBe(originalDraft); noPublication(e.invoke);
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
