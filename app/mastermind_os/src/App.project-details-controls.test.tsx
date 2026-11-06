// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { App } from "./App";
import { bindMissionHost, createNativeClient } from "./host";
import { createIndexedDbPendingPointerStore } from "./orchestration/indexeddb-pending-pointer-store";
import { serializeInstructionAdmissionTarget } from "./orchestration/instruction-admission-target";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import { controlRoomFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import instruction from "./instructions/fixtures/instruction-owner.json";
import access from "./access/fixtures/current-grants.json";

const selection = { work_ref: "WS:ONE" };
const scope = instruction.current.owner_context.principal_scope;
const launchScope = "e".repeat(64);
const original = { kind: "instruction_pause" as const,
  operationKey: instruction.status.selection.command_id,
  targetKey: serializeInstructionAdmissionTarget(instruction.current.selection)! };
beforeEach(async () => {
  history.replaceState(null, "", "/os/"); delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost; });

async function setup({ permitted = true, pending = false } = {}) {
  const room = controlRoomFixture(); room.work = [room.work[0]];
  room.work[0].work_ref = selection.work_ref;
  room.work[0].agent_os.title = "Controls test project"; room.autonomy.responsibilities = [];
  let notify!: (event: { payload: unknown }) => void;
  let finish!: (value: unknown) => void;
  const waiting = new Promise(resolve => { finish = resolve; });
  const invoke = vi.fn(async (name: string, args?: unknown) => {
    if (name === "auth_status") return { status: "signed_in", reason: null, acquisition: true, content: true };
    if (name === "executive_auth_status") return { generation: 0, available: false };
    if (name === "read_programs") return { ...structuredClone(programs), control_room: room };
    if (name === "read_project_instructions") { expect(args).toEqual({ selection }); return instruction.project_current; }
    if (name === "read_project_access") { expect(args).toEqual({ selection }); return access; }
    if (name === "read_instruction_admission_control") {
      expect(args).toEqual({ selection: instruction.current.selection });
      return { ...instruction.current, permission: { pause: permitted } };
    }
    if (name === "pause_instruction_admission") {
      expect(args).toEqual({ request: { selection: instruction.current.selection,
        command_id: original.operationKey, expected_revision: instruction.current.instruction_revision,
        expected_source: instruction.current.source } });
      return pending ? waiting : instruction.unknown;
    }
    if (name === "read_instruction_admission_operation") {
      expect(args).toEqual({ request: { selection: instruction.current.selection, command_id: original.operationKey } });
      return instruction.status;
    }
    throw new Error("Unexpected fixture command");
  });
  const raw = await createNativeClient(invoke as never, async (_name, listener) => { notify = listener; return () => {}; });
  const store = createIndexedDbPendingPointerStore(new IDBFactory());
  const launch = { prepare: vi.fn(() => { throw new Error("Unexpected launch prepare"); }),
    submit: vi.fn(async () => { throw new Error("Unexpected launch submit"); }),
    readOperation: vi.fn(async () => { throw new Error("Unexpected launch status"); }) };
  const binding: OrchestratorCommandBinding = { store,
    port: { context: () => ({ principalScope: launchScope, generation: "executive-1" }), ...launch },
    getView: () => ({ projects: [], profiles: [], session: null }), subscribe: () => () => {},
    makeLaunchIntent: () => null, makeMessageIntent: () => null, makeStopIntent: () => null };
  window.MastermindMissionHost = bindMissionHost(raw, binding);
  function mount() { return render(<App />); }
  async function open() {
    fireEvent.click(screen.getByRole("button", { name: "Projects" }));
    fireEvent.click(await screen.findByRole("button", { name: "Open project Controls test project" }));
    fireEvent.click(screen.getByRole("button", { name: "Project details" }));
  }
  const view = mount(); await open();
  return { invoke, store, launch, view, mount, open, notify, finish };
}
/** The Project details navigator keeps every owner mounted but hidden until
 * its overview button is chosen; switching owners first returns through
 * "Back to project details". Choosing a section reads nothing by itself. */
function chooseSection(name: string) {
  const back = screen.queryByRole("button", { name: /Back to project details/ });
  if (back) fireEvent.click(back);
  fireEvent.click(screen.getByRole("button", { name }));
}
async function readInstruction() {
  chooseSection("Standing instructions");
  fireEvent.click(screen.getByRole("button", { name: "Read instructions" }));
  fireEvent.click(await screen.findByRole("button", { name: /Review instruction:/ }));
  fireEvent.click(screen.getByRole("button", { name: "Check instruction status" }));
}
async function enablePause() {
  await readInstruction();
  await waitFor(() => expect((screen.getByRole("button", { name: "Pause this instruction" }) as HTMLButtonElement).disabled).toBe(false));
  vi.spyOn(crypto, "getRandomValues").mockImplementation(value => { (value as Uint8Array).fill(0x11); return value; });
}
it("mounts both accepted controls visibly with zero automatic I/O and independent rootless reads", async () => {
  const e = await setup();
  chooseSection("Standing instructions");
  expect(screen.getByRole("region", { name: "Standing instructions" })).toBeTruthy();
  chooseSection("Project permissions");
  expect(screen.getByRole("region", { name: "Project permissions" })).toBeTruthy();
  chooseSection("Work controls");
  expect(screen.getByRole("region", { name: "New work" })).toBeTruthy();
  expect(e.invoke.mock.calls.filter(([name]) => /instruction|access|admission/.test(name))).toHaveLength(0);
  chooseSection("Project permissions");
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_project_access")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name]) => /instruction|admission/.test(name))).toHaveLength(0);
  chooseSection("Standing instructions");
  fireEvent.click(screen.getByRole("button", { name: "Read instructions" }));
  await screen.findByRole("button", { name: /Review instruction:/ });
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_project_instructions")).toHaveLength(1);
  const controls = screen.getByRole("region", { name: "Standing instructions" });
  expect(controls.closest("details")?.open ?? true).toBe(true);
});
it("keeps effective permissions view-only and never borrows a project grant for instruction Pause", async () => {
  const e = await setup({ permitted: false });
  chooseSection("Project permissions");
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  expect(within(screen.getByRole("region", { name: "Project permissions" })).queryByRole("button", { name: /edit|grant|pause|resume/i })).toBeNull();
  await readInstruction();
  await waitFor(() => expect(e.invoke.mock.calls.filter(([name]) => name === "read_instruction_admission_control")).toHaveLength(1));
  expect((screen.getByRole("button", { name: "Pause this instruction" }) as HTMLButtonElement).disabled).toBe(true);
  expect(e.invoke.mock.calls.some(([name]) => /^(pause|resume)_/.test(name))).toBe(false);
  expect(e.launch.prepare).not.toHaveBeenCalled();
});
it("reopens the actual App with its exact instruction pointer and recovers only the original request", async () => {
  const e = await setup(); await enablePause();
  fireEvent.click(screen.getByRole("button", { name: "Pause this instruction" }));
  await screen.findByText(/original request outcome is unresolved/);
  expect(await e.store.read(scope)).toEqual(original); expect(await e.store.read(launchScope)).toBeNull();
  e.view.unmount(); e.mount(); await e.open();
  expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1);
  await readInstruction();
  await screen.findByText("Pause request committed. Check current status to confirm the current setting.");
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_instruction_admission_operation")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1);
  expect(e.invoke.mock.calls.some(([name]) => name === "pause_project_admission" || name === "resume_project_admission")).toBe(false);
  expect(await e.store.read(scope)).toBeNull(); expect(e.launch.readOperation).not.toHaveBeenCalled();
});
it("withdraws a late instruction action on actual native auth loss and retains its original hint", async () => {
  const e = await setup({ pending: true }); await enablePause();
  fireEvent.click(screen.getByRole("button", { name: "Pause this instruction" }));
  await waitFor(() => expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1));
  act(() => e.notify({ payload: { status: "signed_out", reason: "AUTHENTICATION_REQUIRED", acquisition: false, content: false } }));
  await act(async () => e.finish(instruction.status));
  expect(screen.queryByText("Pause request committed. Check current status to confirm the current setting.")).toBeNull();
  expect(screen.queryByText("Review the project carefully.")).toBeNull();
  expect(await e.store.read(scope)).toEqual(original);
  expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_instruction_admission_operation")).toHaveLength(0);
});
