// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, expect, it, vi} from "vitest";
import {App} from "./App";
import {bindMissionHost, createNativeClient} from "./host";
import {controlRoomFixture, missionFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import work from "./fixtures/work-service-available.json";
import producer from "./fixtures/project-session-association-producer.json";

// Real fixed native client -> authenticated host capability gate -> closed BODY decoder
// -> actual App/consumer. The invoke seam returns the immutable producer fixture;
// no consumer/host method is mocked into existence and no network is exercised.
let response: () => Promise<unknown>;

const signed = {status:"signed_in",reason:null,acquisition:true,content:true};
beforeEach(async () => {
  history.replaceState(null,"","/os/"); delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
  const {webcrypto} = await vi.importActual<{webcrypto:Crypto}>("node:crypto");
  vi.stubGlobal("crypto", webcrypto); response = async () => structuredClone(producer);
});
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); delete window.MastermindMissionHost;});

async function setup({conflict=false, rootless=false, noGeneration=false, noPort=false} = {}) {
  const base = controlRoomFixture();
  let room = JSON.parse(JSON.stringify(base).replaceAll("WS:ALPHA",producer.selection.work_ref).replaceAll("JOB-A",producer.selection.root_job_id));
  room.work = [room.work[0]]; room.work[0].agent_os.title = "Synthetic project";
  room.autonomy.responsibilities = rootless ? [] : [room.autonomy.responsibilities[0]];
  if (conflict) room.autonomy.responsibilities[0].root_job_candidates = [producer.selection.root_job_id,"JOB-OTHER"];
  let notify!:(event:{payload:unknown})=>void;
  const invoke = vi.fn(async (command:string, args?:unknown) => {
    if (command === "read_project_session") {
      expect(args).toEqual({selection:producer.selection});
      return response();
    }
    if (command === "auth_status") return signed;
    if (command === "read_programs") return {...structuredClone(programs),control_room:structuredClone(room)};
    if (command === "read_work") return structuredClone(work);
    if (command === "read_mission_v3" || command === "read_mission") return missionFixture(producer.selection.work_ref,producer.selection.root_job_id);
    throw new Error("Unexpected fixture command");
  });
  const client = await createNativeClient(invoke as never,async (_name,listener) => {notify=listener;return()=>{};});
  const host = bindMissionHost(noPort ? {...client,readProjectSessionAssociation:undefined} : client);
  const read = host.readProjectSessionAssociation ? vi.spyOn(host,"readProjectSessionAssociation") : undefined;
  if (noGeneration) host.invalidationGeneration = undefined;
  window.MastermindMissionHost = host;
  render(<App/>);
  fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Synthetic project"}));
  fireEvent.click(await screen.findByRole("button",{name:"Project details"}));
  return {invoke, host, read, notify, changeRoom:(next: typeof room) => {room=next;}, room};
}

it("mounts actual Project Details with explicit missing capability and no association read",async () => {
  const f = await setup({noPort:true});
  expect(screen.getByRole("heading",{name:"Session evidence"})).toBeTruthy();
  expect(screen.getByText("Session information is unavailable here.")).toBeTruthy();
  expect(screen.getByText("No association observation port is connected for this selection.")).toBeTruthy();
  expect(f.invoke.mock.calls.some(([name]) => /session|submit|prepare|launch/.test(name))).toBe(false);
});

it("joins the actual retained producer body to the catalogue pair without creating a conversation target",async () => {
  const f = await setup();
  const read=f.read!;
  expect(await screen.findByText("A managed session was observed.")).toBeTruthy();
  expect(read).toHaveBeenCalledExactlyOnceWith({...{workRef:producer.selection.work_ref,rootJobId:producer.selection.root_job_id},signal:expect.any(AbortSignal)});
  const evidence=screen.getByRole("heading",{name:"Session evidence"}).closest("section")!;
  expect(evidence.querySelectorAll("button")).toHaveLength(1); // Refresh observation only.
  expect(evidence.textContent).not.toMatch(/Working|Send message|Continue session/);
  expect(f.invoke.mock.calls.some(([name]) => /submit|prepare|launch/.test(name))).toBe(false);
  act(() => f.notify({payload:{status:"signed_out",reason:"AUTHENTICATION_REQUIRED",acquisition:false,content:false}}));
  expect(screen.queryByText("A managed session was observed.")).toBeNull();
  expect(read.mock.calls[0][0].signal.aborted).toBe(true);
});

it.each([{conflict:true},{rootless:true},{noGeneration:true}])("withholds association acquisition for an unqualified catalogue/host: %j",async options => {
  const f=await setup(options);
  expect(screen.getByText("Session information is unavailable here.")).toBeTruthy();
  expect(f.invoke.mock.calls.filter(([name])=>name==="read_project_session")).toHaveLength(0);
});

it("rejects a response for a different exact root through the real consumer decoder",async () => {
  response=async()=>({...structuredClone(producer),selection:{...producer.selection,root_job_id:"JOB-OTHER"}});
  await setup();
  expect(await screen.findByText("Session information could not be loaded.")).toBeTruthy();
  expect(screen.queryByText("A managed session was observed.")).toBeNull();
  expect(document.body.textContent).not.toContain(producer.materialization.recorded_at);
});

it("aborts a pending observation on catalogue refresh and withholds its late source body",async () => {
  let finish!:(value:unknown)=>void;
  response=()=>new Promise(resolve=>{finish=resolve;});
  const f=await setup();const read=f.read!;await waitFor(()=>expect(read).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button",{name:"Refresh Projects"}));
  expect(read.mock.calls[0][0].signal.aborted).toBe(true);
  await act(async()=>finish(structuredClone(producer)));
  expect(screen.queryByText("A managed session was observed.")).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});
