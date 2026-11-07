// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { bindMissionHost, createNativeClient } from "../host";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { serializeInstructionAdmissionTarget } from "../orchestration/instruction-admission-target";
import instruction from "../instructions/fixtures/instruction-owner.json";
import access from "../access/fixtures/current-grants.json";
import { useProjectDetailsControls, type ProjectDetailsControlsProps } from "./useProjectDetailsControls";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function Details(props: ProjectDetailsControlsProps) {
  const panels = useProjectDetailsControls(props);
  return <>{panels.instructions}{panels.access}</>;
}
async function setup({ permission = true } = {}) {
  let notify!: (event: { payload: unknown }) => void;
  let content: unknown = instruction.project_current;
  let pauseResult: unknown = instruction.unknown;
  const invoke = vi.fn(async (name: string) => {
    if (name === "auth_status") return { status: "signed_in", reason: null, acquisition: true, content: false };
    if (name === "executive_auth_status") return { generation: 0, available: false };
    if (name === "read_project_instructions") return content;
    if (name === "read_instruction_admission_control")
      return { ...instruction.current, permission: { pause: permission } };
    if (name === "pause_instruction_admission") return pauseResult;
    if (name === "read_instruction_admission_operation") return instruction.status;
    if (name === "read_project_access") return access;
    throw new Error("Unexpected fixture command");
  });
  const client = await createNativeClient(invoke as never, async (_name, listener) => {
    notify = listener; return () => {};
  });
  const host = bindMissionHost(client);
  const store = createIndexedDbPendingPointerStore(new IDBFactory());
  const draft = vi.fn();
  const props: ProjectDetailsControlsProps = {
    host, selection: { work_ref: "WS:ONE" }, authGeneration: 1,
    sourceGeneration: () => host.invalidationGeneration!(),
    canRead: () => host.auth!.getState().status === "signed_in" && host.auth!.getState().acquisition,
    store, locale: "en", onChangeInConversation: draft,
  };
  invoke.mockClear();
  return { host, store, props, invoke, draft, notify,
    holdContent: (value: Promise<unknown>) => { content = value; },
    holdPause: (value: Promise<unknown>) => { pauseResult = value; } };
}
async function selectInstruction() {
  fireEvent.click(screen.getByRole("button", { name: "Read instructions" }));
  fireEvent.click(await screen.findByRole("button", { name: /Review instruction:/ }));
}
async function readInstructionControl() {
  await selectInstruction();
  fireEvent.click(screen.getByRole("button", { name: "Check instruction status" }));
  await waitFor(() => expect((screen.getByRole("button", { name: "Pause this instruction" }) as HTMLButtonElement).disabled).toBe(false));
}
it("joins actual native/host readers rootlessly without mount I/O or cross-panel reads", async () => {
  const e = await setup(), view = render(<Details {...e.props} />);
  expect(e.invoke).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  expect(e.invoke.mock.calls).toEqual([["read_project_access", { selection: { work_ref: "WS:ONE" } }]]);
  await selectInstruction();
  expect(e.invoke.mock.calls.map(([name]) => name)).toEqual(["read_project_access", "read_project_instructions"]);
  view.rerender(<Details {...e.props} />);
  expect(screen.getAllByText("Review the project carefully.").length).toBeGreaterThan(0);
  expect(screen.getByText("You can read this project’s information.")).toBeTruthy();
  expect(e.invoke).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", { name: "Change in conversation" }));
  expect(e.draft).toHaveBeenCalledTimes(1);
  expect(e.draft.mock.calls[0][0].excerpt).toBe("Review the project carefully.");
  expect(e.invoke).toHaveBeenCalledTimes(2);
});
it("keeps effective access view-only and requires the distinct current instruction permission", async () => {
  const e = await setup({ permission: false }); render(<Details {...e.props} />);
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  const panel = screen.getByRole("region", { name: "Project permissions" });
  expect(within(panel).queryByRole("button", { name: /edit|grant|pause|resume|adopt/i })).toBeNull();
  await selectInstruction();
  fireEvent.click(screen.getByRole("button", { name: "Check instruction status" }));
  await waitFor(() => expect(e.invoke.mock.calls.filter(([name]) => name === "read_instruction_admission_control")).toHaveLength(1));
  expect((screen.getByRole("button", { name: "Pause this instruction" }) as HTMLButtonElement).disabled).toBe(true);
  expect(e.invoke.mock.calls.some(([name]) => /^(pause|resume)_/.test(name))).toBe(false);
});
it("uses the incumbent instruction pointer and same-ID status without invoking project Pause or Resume", async () => {
  const e = await setup(); render(<Details {...e.props} />);
  vi.spyOn(crypto, "getRandomValues").mockImplementation(value => { (value as Uint8Array).fill(0x11); return value; });
  await readInstructionControl();
  fireEvent.click(screen.getByRole("button", { name: "Pause this instruction" }));
  await screen.findByText(/original request outcome is unresolved/);
  expect(await e.store.read(instruction.current.owner_context.principal_scope)).toEqual({
    kind: "instruction_pause", operationKey: instruction.status.selection.command_id,
    targetKey: serializeInstructionAdmissionTarget(instruction.current.selection)!,
  });
  fireEvent.click(screen.getByRole("button", { name: "Check original instruction request" }));
  await screen.findByText("Pause request committed. Check current status to confirm the current setting.");
  expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_instruction_admission_operation")).toHaveLength(1);
  expect(e.invoke.mock.calls.some(([name]) => name === "pause_project_admission" || name === "resume_project_admission")).toBe(false);
  expect(await e.store.read(instruction.current.owner_context.principal_scope)).toBeNull();
});
it("fences an in-place method replacement before a stale gesture can reserve or dispatch", async () => {
  const e = await setup(); render(<Details {...e.props} />); await readInstructionControl();
  const replacement = vi.fn(async () => instruction.unknown);
  e.host.pauseInstructionAdmission = replacement;
  fireEvent.click(screen.getByRole("button", { name: "Pause this instruction" }));
  await act(async () => {});
  expect(replacement).not.toHaveBeenCalled();
  expect(e.invoke.mock.calls.some(([name]) => name === "pause_instruction_admission")).toBe(false);
  expect(await e.store.read(instruction.current.owner_context.principal_scope)).toBeNull();
  // An unrelated instruction capability departure does not disable Access.
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
});
it("withholds late source content on actual auth invalidation and never resurrects A after B", async () => {
  const e = await setup(); let finish!: (value: unknown) => void;
  e.holdContent(new Promise(resolve => { finish = resolve; }));
  const view = render(<Details {...e.props} />);
  fireEvent.click(screen.getByRole("button", { name: "Read instructions" }));
  act(() => e.notify({ payload: { status: "signed_out", reason: "AUTHENTICATION_REQUIRED", acquisition: false, content: false } }));
  view.rerender(<Details {...e.props} authGeneration={2} />);
  await act(async () => finish(instruction.project_current));
  expect(screen.queryByText("Review the project carefully.")).toBeNull();
  expect(e.draft).not.toHaveBeenCalled();
  expect(e.invoke.mock.calls).toHaveLength(1);
  view.rerender(<Details {...e.props} selection={{ work_ref: "WS:OTHER" }} authGeneration={2} />);
  view.rerender(<Details {...e.props} authGeneration={2} />);
  expect(screen.queryByText("Review the project carefully.")).toBeNull();
  expect(e.invoke.mock.calls).toHaveLength(1);
});
it("retains the original instruction pause across action-time auth revocation", async () => {
  const e = await setup(); let finish!: (value: unknown) => void;
  e.holdPause(new Promise(resolve => { finish = resolve; }));
  const view = render(<Details {...e.props} />);
  vi.spyOn(crypto, "getRandomValues").mockImplementation(value => { (value as Uint8Array).fill(0x11); return value; });
  await readInstructionControl();
  fireEvent.click(screen.getByRole("button", { name: "Pause this instruction" }));
  await waitFor(() => expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1));
  act(() => e.notify({ payload: { status: "signed_out", reason: "AUTHENTICATION_REQUIRED", acquisition: false, content: false } }));
  view.rerender(<Details {...e.props} authGeneration={2} />);
  await act(async () => finish(instruction.status));
  expect(screen.queryByText("Pause request committed. Check current status to confirm the current setting.")).toBeNull();
  expect(await e.store.read(instruction.current.owner_context.principal_scope)).toEqual({
    kind: "instruction_pause", operationKey: instruction.status.selection.command_id,
    targetKey: serializeInstructionAdmissionTarget(instruction.current.selection)!,
  });
  expect(e.invoke.mock.calls.filter(([name]) => name === "pause_instruction_admission")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name]) => name === "read_instruction_admission_operation")).toHaveLength(0);
});
it("renders the accepted Chinese panels with no methods or inferred permission", async () => {
  const e = await setup(); render(<Details {...e.props} host={null} locale="zh-CN" />);
  expect(document.querySelectorAll('section[lang="zh-CN"]')).toHaveLength(2);
  expect(e.invoke).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /暂停|恢复|授予|编辑/ })).toBeNull();
});
