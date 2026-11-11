// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { createNativeClient } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import fixture from "./fixtures/project-conversation-history-owner.json";
import catalogue from "./fixtures/project-conversation-catalogue-owner.json";
import {composeMissionHost} from "./compose-mission-host";

const disposals:Array<()=>void>=[];
const signed = { status: "signed_in", reason: null, acquisition: true, content: true };
beforeEach(async () => {
  history.replaceState(null, "", `/os/?work_ref=${paired.selection.work_ref}&root_job_id=${paired.selection.root_job_id}`);
  delete window.MastermindMissionHost; delete (window as any).__TAURI_INTERNALS__;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => { cleanup(); disposals.splice(0).forEach(dispose=>dispose()); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost; });

async function prepare() {
  const room = controlRoomFixture(), row = structuredClone(room.work[0]);
  row.work_ref = fixture.work_ref; row.agent_os.workstream = fixture.work_ref.slice(3);
  row.agent_os.title = "Qualified conversation project"; room.work = [row];
  const responsibility = structuredClone(room.autonomy.responsibilities[0]);
  Object.assign(responsibility, { responsibility_ref: fixture.work_ref,
    root_job_id: paired.selection.root_job_id, root_job_candidates: [paired.selection.root_job_id],
    root_job_ambiguous: false, runtime_root_state: "RESOLVED" });
  room.autonomy.responsibilities = [responsibility];
  const invoke = vi.fn(async (name: string, _args?: Record<string,unknown>) => {
    if (name === "auth_status") return signed;
    if (name === "executive_auth_status") return { generation: 1, available: true };
    if (name === "executive_project_history_context")return structuredClone(fixture.context);
    if (name === "executive_project_conversations_read") {
      if(_args?.operation === "catalogue")return structuredClone(catalogue.catalogue);
      if(_args?.operation === "read")return structuredClone(catalogue.read);
      throw Error("Separate fresh population is unavailable in this original-native fixture");
    }
    if (name === "executive_project_session_references")return structuredClone(fixture.page);
    if (name === "executive_session_reply")return structuredClone(fixture.answer);
    if (name === "read_programs") return { ...structuredClone(programs), control_room: room };
    if (name === "read_mission_v3") return structuredClone(paired.mission);
    if (name === "read_current_window") return structuredClone(paired.window);
    throw new Error("Unexpected fixed fixture command");
  });
  const raw = await createNativeClient(invoke as never, async () => () => {});
  const composed=composeMissionHost(raw,null);disposals.push(composed.dispose);await composed.sessionReady;
  const host=composed.host;
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
  await screen.findByRole("button", { name: "Open project Qualified conversation project" });
  const list = within(document.querySelector(".conversations-list") as HTMLElement);
  fireEvent.click(list.getByRole("button", {name:"Open project Qualified conversation project"}));
  fireEvent.click(await screen.findByRole("button",{name:"Project details"}));
  fireEvent.click(screen.getByRole("button",{name:"History and sources",exact:true}));
  const disclosure=await screen.findByText("Project history and source evidence",{selector:"summary"});
  fireEvent.click(disclosure);
  const panel=within(await screen.findByRole("region",{name:"Project conversations"}));
  const read=panel.getByRole("button",{name:"Read project conversations"});
  await waitFor(()=>expect(read.hasAttribute("disabled")).toBe(false));
  return { invoke, host, raw, panel, read, driftGeneration: () => { generationDelta++; } };
}
function noWrite(invoke: ReturnType<typeof vi.fn>) {
  expect(invoke.mock.calls.filter(([name]) => /send|submit|create|launch|consume|pause|resume|adopt/.test(name))).toHaveLength(0);
}


it("mounts selected-project catalogue and explicitly reopens the exact original window, preserving Back query",async()=>{
 const e=await prepare();
 expect(e.invoke.mock.calls.filter(([name])=>/history|references|reply|conversations_read/.test(name))).toHaveLength(0);
 fireEvent.click(e.read);
 const open=await e.panel.findByRole("button",{name:"Open"});
 fireEvent.change(e.panel.getByRole("textbox",{name:"Find in these conversations"}),{target:{value:"Conversation"}});
 fireEvent.click(open);
 await e.panel.findByText(catalogue.read.turns[0].reply!.text);
 fireEvent.click(e.panel.getByRole("button",{name:"Back to conversations"}));
 expect(e.panel.getByRole("textbox",{name:"Find in these conversations"})).toHaveProperty("value","Conversation");
 fireEvent.click(e.panel.getByRole("button",{name:"Open"}));
 await e.panel.findByText(catalogue.read.turns[0].reply!.text);
 expect(e.invoke.mock.calls.filter(([name,args])=>name==="executive_project_conversations_read"&&(args as any).operation==="read")).toHaveLength(2);
 noWrite(e.invoke);
});
it("refuses captured catalogue Read and Open after no-render host generation withdrawal",async()=>{
 const e=await prepare();fireEvent.click(e.read);
 const open=await e.panel.findByRole("button",{name:"Open"});
 e.driftGeneration();fireEvent.click(open);
 expect(e.invoke.mock.calls.filter(([name,args])=>name==="executive_project_conversations_read"&&(args as any).operation==="read")).toHaveLength(0);
 expect(e.panel.queryByText(catalogue.read.turns[0].reply!.text)).toBeNull();
 fireEvent.click(e.panel.getByRole("button",{name:"Read project conversations"}));
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_project_history_context")).toHaveLength(1);
 noWrite(e.invoke);
});
