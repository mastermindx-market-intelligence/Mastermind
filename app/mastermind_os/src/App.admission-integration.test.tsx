// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import {App} from "./App";
import {bindMissionHost,createNativeClient} from "./host";
import {createIndexedDbPendingPointerStore} from "./orchestration/indexeddb-pending-pointer-store";
import type {OrchestratorCommandBinding} from "./orchestration/host-command-bindings";
import {controlRoomFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import fixture from "./admission/fixtures/project-admission-owner.json";

// Synthetic rootless variants of the actual Runtime/Workspace owner fixture.
// The server's rootless canonical-source/grant checks have their own backend
// tests; this proves the real client/host/controller/store/App composition.
function rootless<T extends {selection:unknown}>(body:T) {
  const copy=structuredClone(body) as T & {selection:Record<string,unknown>};
  delete copy.selection.root_job_id;return copy;
}
const selection={work_ref:fixture.open.selection.work_ref};
const workspaceScope=fixture.open.owner_context.principal_scope, launchScope="e".repeat(64);
const command=fixture.pause_result.selection.command_id;
const signed={status:"signed_in",reason:null,acquisition:true,content:true};
beforeEach(async()=>{
  history.replaceState(null,"","/os/");delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup({lost=false,pending=false,noPermission=false}={}) {
  const room=controlRoomFixture();room.work=[room.work[0]];room.work[0].work_ref=selection.work_ref;
  room.work[0].agent_os.title="Admission test programme";room.autonomy.responsibilities=[];
  let notify!:(event:{payload:unknown})=>void,finish!:(value:unknown)=>void,statusObserved=false;
  const waiting=new Promise(resolve=>{finish=resolve;});
  const invoke=vi.fn(async(name:string,args?:unknown)=>{
    if(name==="auth_status")return signed;
    if(name==="read_programs")return {...structuredClone(programs),control_room:room};
    if(name==="read_project_admission_control") {
      expect(args).toEqual({selection});const body=rootless(fixture.open);
      if(noPermission)body.permissions.pause=false;return body;
    }
    if(name==="pause_project_admission") {
      expect(args).toEqual({request:{selection,command_id:command}});
      if(pending)return waiting;if(lost)throw new Error("private connection failure");return rootless(fixture.pause_result);
    }
    if(name==="read_project_admission_operation") {
      expect(args).toEqual({request:{selection,command_id:command,kind:"project_pause"}});
      return {schema:"mastermind.workspace_project_admission_status_result.v1",
        selection:{...selection,command_id:command},state:statusObserved?"OBSERVED":"NOT_OBSERVED",
        receipt:statusObserved?fixture.pause_result.receipt:null,reason_codes:[]};
    }
    throw new Error("Unexpected fixture command");
  });
  const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
  const store=createIndexedDbPendingPointerStore(new IDBFactory());
  const launch={prepare:vi.fn(()=>{throw new Error("Unexpected launch prepare");}),submit:vi.fn(async()=>{throw new Error("Unexpected launch submit");}),readOperation:vi.fn(async()=>{throw new Error("Unexpected launch status");})};
  const binding:OrchestratorCommandBinding={store,port:{context:()=>({principalScope:launchScope,generation:"executive-1"}),...launch},
    getView:()=>({projects:[],profiles:[],session:null}),subscribe:()=>()=>{},makeLaunchIntent:()=>null,makeMessageIntent:()=>null,makeStopIntent:()=>null};
  window.MastermindMissionHost=bindMissionHost(raw,binding);
  function mount(){return render(<App/>);}
  async function open(){
    fireEvent.click(screen.getByRole("button",{name:"Projects"}));
    fireEvent.click(await screen.findByRole("button",{name:"Open project Admission test programme"}));
    fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  }
  const view=mount();await open();
  return {invoke,store,binding,launch,view,mount,open,notify,finish,observe:()=>{statusObserved=true;}};
}
async function readCurrent(){
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  await waitFor(()=>expect((screen.getByRole("button",{name:"Pause new work"}) as HTMLButtonElement).disabled).toBe(false));
}
function fixedKey(){vi.spyOn(globalThis.crypto,"getRandomValues").mockImplementation(array=>{(array as Uint8Array).fill(0xaa);return array;});}
it("mounts actual fixed controls without automatic reads/effects, then submits one explicit Pause through the real host",async()=>{
  const e=await setup();
  expect(e.invoke.mock.calls.filter(([name])=>name.includes("admission"))).toHaveLength(0);
  await readCurrent();fixedKey();fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
  await screen.findByText(/Request committed/);
  expect(e.invoke.mock.calls.filter(([name])=>name==="pause_project_admission")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name])=>name==="read_project_admission_operation")).toHaveLength(0);
  expect(e.launch.prepare).not.toHaveBeenCalled();expect(e.launch.submit).not.toHaveBeenCalled();
  expect(await e.store.read(workspaceScope)).toBeNull();expect(await e.store.read(launchScope)).toBeNull();
  expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();
  expect(screen.queryByText("New work is not paused here. Other limits and permissions still apply.")).toBeNull();
});
it("keeps a lost Pause in the Workspace scope and recovers the same command on actual App reopen",async()=>{
  const e=await setup({lost:true});await readCurrent();fixedKey();
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));await screen.findByText(/original request outcome is unresolved/);
  const pointer={kind:"project_pause",targetKey:selection.work_ref,operationKey:command};
  expect(await e.store.read(workspaceScope)).toEqual(pointer);expect(await e.store.read(launchScope)).toBeNull();
  e.view.unmount();e.mount();await e.open();
  expect(e.invoke.mock.calls.filter(([name])=>name==="read_project_admission_operation")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));await screen.findByText(/original request outcome is unresolved/);
  expect(await e.store.read(workspaceScope)).toEqual(pointer);
  e.observe();fireEvent.click(within(screen.getByRole("region",{name:"New work"})).getByRole("button",{name:"Check original project request"}));await screen.findByText(/Request committed/);
  expect(e.invoke.mock.calls.filter(([name])=>name==="pause_project_admission")).toHaveLength(1);
  expect(e.invoke.mock.calls.filter(([name])=>name==="read_project_admission_operation")).toHaveLength(2);
  expect(e.launch.readOperation).not.toHaveBeenCalled();expect(e.launch.prepare).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain("private connection failure");
});
it("treats typed owner permission as decisive despite registered methods and a durable store",async()=>{
  const e=await setup({noPermission:true});fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  expect(await screen.findByText("This read does not supply current permission for this action.")).toBeTruthy();
  expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();
  expect(e.invoke.mock.calls.filter(([name])=>name==="pause_project_admission" || name==="resume_project_admission")).toHaveLength(0);
});
it("withdraws a pending action on actual host auth invalidation and retains its original durable hint",async()=>{
  const e=await setup({pending:true});await readCurrent();fixedKey();
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
  await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==="pause_project_admission")).toHaveLength(1));
  act(()=>e.notify({payload:{status:"signed_out",reason:"AUTHENTICATION_REQUIRED",acquisition:false,content:false}}));
  await act(async()=>e.finish(rootless(fixture.pause_result)));
  expect(screen.queryByText(/Request committed/)).toBeNull();
  expect(await e.store.read(workspaceScope)).toEqual({kind:"project_pause",targetKey:selection.work_ref,operationKey:command});
  expect(e.invoke.mock.calls.filter(([name])=>name==="resume_project_admission")).toHaveLength(0);
});
