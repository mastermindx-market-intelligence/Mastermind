// @vitest-environment jsdom
import userEvent from "@testing-library/user-event";
import { App } from "../App";
import { decodeProgramsObservation } from "../programs-observation";
import programsFixture from "../fixtures/programs-available-workspace-service.json";
import { controlRoomFixture } from "../test-fixtures";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthState, MissionHost } from "../host";
import fixture from "../fixtures/mission-v4-owner-accepted.json";
import { ProductAcceptancePanel } from "./ProductAcceptancePanel";
const selected={workRef:fixture.product_acceptance.selection.work_ref,rootJobId:fixture.product_acceptance.selection.root_job_id,requestMessageKey:fixture.product_acceptance.selection.request_message_key};
const snapshot=()=>({selector:{...selected},principalScope:"fixture-owner",ownerGeneration:1,selectionGeneration:1});
const deferred=()=>{let resolve!:(v:unknown)=>void;const promise=new Promise<unknown>(r=>resolve=r);return{promise,resolve};};
function setup(){
 let value:unknown=snapshot(),generation=1,selectionGeneration=1;
 let auth:AuthState={status:"signed_in",acquisition:true,content:true,reason:null};
 const observers=new Set<()=>void>(),authObservers=new Set<(s:AuthState)=>void>();
 const owner={getSnapshot:()=>value,subscribe:(fn:()=>void)=>{observers.add(fn);return()=>{observers.delete(fn);};}};
 const read=vi.fn(async():Promise<unknown>=>structuredClone(fixture));
 const host:MissionHost={productAcceptanceOwner:owner,readMissionV4:read,invalidationGeneration:()=>generation,
  auth:{getState:()=>auth,subscribe:fn=>{authObservers.add(fn);return()=>{authObservers.delete(fn);};},signIn:async()=>{},signOut:async()=>{}}};
 let currentHost:MissionHost|undefined=host;
 const props=()=>({host,selection:selected,selectionGeneration,currentSelectionGeneration:()=>selectionGeneration,currentHost:()=>currentHost,authRevision:generation,enabled:true,locale:"en"});
 return{host,owner,read,props,set:(next:unknown)=>{value=next;for(const fn of [...observers])fn();},
  revoke:()=>{auth={...auth,status:"signed_out",acquisition:false};generation++;for(const fn of [...authObservers])fn(auth);},
  selectionABA:()=>{selectionGeneration+=2;},replaceHost:()=>{currentHost={...host};},listenerCount:()=>observers.size+authObservers.size};
}
afterEach(()=>{cleanup();vi.restoreAllMocks();});
describe("read-only product acceptance presentation",()=>{
 it("shows a qualified exact receipt and has no effect controls",async()=>{const e=setup();render(<ProductAcceptancePanel {...e.props()}/>);await screen.findByText("PRODUCT_ACCEPTED");expect(screen.getByText(fixture.product_acceptance.receipt.parent_result_envelope_digest)).toBeTruthy();expect(screen.queryAllByRole("button")).toHaveLength(0);expect(e.read).toHaveBeenCalledTimes(1);});
 it("shows unavailable and performs zero reads without an owner",()=>{const e=setup();delete (e.host as any).productAcceptanceOwner;render(<ProductAcceptancePanel {...e.props()}/>);expect(screen.getByText("UNAVAILABLE")).toBeTruthy();expect(e.read).not.toHaveBeenCalled();});
 it("withholds a malformed accepted response",async()=>{const e=setup();e.read.mockResolvedValue({schema:"mastermind.mission_workspace.v4",product_acceptance:{state:"ACCEPTED"}});render(<ProductAcceptancePanel {...e.props()}/>);await waitFor(()=>expect(e.read).toHaveBeenCalledTimes(1));await screen.findByText("UNAVAILABLE");expect(screen.queryByText("PRODUCT_ACCEPTED")).toBeNull();});
 it("keeps a closed unavailable source truthful in both locale treatments",async()=>{const e=setup();const f:any=structuredClone(fixture);f.product_acceptance={...f.product_acceptance,state:"UNAVAILABLE",receipt:null,reason_codes:["PARENT_CONSUMPTION_UNPROVEN"]};e.read.mockResolvedValue(f);render(<ProductAcceptancePanel {...e.props()} locale="zh"/>);await screen.findByText("PARENT_CONSUMPTION_UNPROVEN");expect(screen.getByText("产品验收")).toBeTruthy();expect(screen.queryByText("PRODUCT_ACCEPTED")).toBeNull();});
 it.each(["ownerABA","selectionABA","authWithdrawal","hostReplacement","unmount"])("withholds an old promise after %s",async event=>{
  const e=setup(),p=deferred();e.read.mockImplementation(()=>new Promise(()=>{})).mockImplementationOnce(()=>p.promise);
  const ui=render(<ProductAcceptancePanel {...e.props()}/>);await waitFor(()=>expect(e.read).toHaveBeenCalledTimes(1));
  act(()=>{if(event==="ownerABA"){e.set(null);e.set(snapshot());}if(event==="selectionABA")e.selectionABA();if(event==="authWithdrawal")e.revoke();if(event==="hostReplacement")e.replaceHost();if(event==="unmount")ui.unmount();});
  await act(async()=>{p.resolve(structuredClone(fixture));await p.promise;});
  expect(screen.queryByText("PRODUCT_ACCEPTED")).toBeNull();if(event==="unmount")expect(e.listenerCount()).toBe(0);
 });
 it("clears an already displayed receipt on owner withdrawal",async()=>{const e=setup();render(<ProductAcceptancePanel {...e.props()}/>);await screen.findByText("PRODUCT_ACCEPTED");act(()=>e.set(null));expect(screen.queryByText("PRODUCT_ACCEPTED")).toBeNull();expect(screen.getByText("UNAVAILABLE")).toBeTruthy();});
 it("does not reacquire on an unchanged passive rerender",async()=>{const e=setup();const ui=render(<ProductAcceptancePanel {...e.props()}/>);await screen.findByText("PRODUCT_ACCEPTED");ui.rerender(<ProductAcceptancePanel {...e.props()}/>);await act(async()=>{});expect(e.read).toHaveBeenCalledTimes(1);});
 it("reads a legitimate new owner generation separately",async()=>{const e=setup();render(<ProductAcceptancePanel {...e.props()}/>);await screen.findByText("PRODUCT_ACCEPTED");act(()=>e.set({...snapshot(),ownerGeneration:2}));await waitFor(()=>expect(e.read).toHaveBeenCalledTimes(2));await screen.findByText("PRODUCT_ACCEPTED");});
 it("fails closed when subscription cannot establish an owner lifetime",async()=>{const e=setup();e.owner.subscribe=()=>{throw Error("unavailable");};render(<ProductAcceptancePanel {...e.props()}/>);await act(async()=>{});expect(e.read).not.toHaveBeenCalled();expect(screen.queryByText("PRODUCT_ACCEPTED")).toBeNull();});
});

describe("actual App Evidence composition",()=>{
 it.each([true,false])("mounts the read-only receipt with owner attachment=%s",async attached=>{
  const e=setup();
  const room=controlRoomFixture();room.work=[room.work[0]];room.autonomy.responsibilities=[room.autonomy.responsibilities[0]];
  room.work[0].work_ref=selected.workRef;room.work[0].agent_os.workstream="FIXTURE";room.work[0].agent_os.title="Acceptance project";
  Object.assign(room.autonomy.responsibilities[0],{responsibility_ref:selected.workRef,root_job_id:selected.rootJobId,root_job_candidates:[selected.rootJobId],root_job_ambiguous:false,runtime_root_state:"RESOLVED"});
  e.host.readProgramsObservation=async()=>decodeProgramsObservation({...structuredClone(programsFixture),control_room:room});e.host.readMissionV3=async()=>structuredClone(fixture.mission);
  if(!attached)delete (e.host as any).productAcceptanceOwner;
  window.MastermindMissionHost=e.host;
  history.replaceState(null,"","/os/?work_ref=WS%3AFIXTURE&root_job_id=JOB-001&request_message_key="+selected.requestMessageKey);
  const ui=render(<App/>),user=userEvent.setup();
  try {
   await user.click(screen.getByRole("button",{name:"Projects"}));
   await user.click(await screen.findByRole("button",{name:"Open project Acceptance project"}));
   const tab=await screen.findByRole("tab",{name:"Evidence"});
   await user.click(tab);
   const panel=await screen.findByRole("region",{name:"Product acceptance receipt"});
   if(attached)await within(panel).findByText("PRODUCT_ACCEPTED");
   else{expect(within(panel).getByText("UNAVAILABLE")).toBeTruthy();expect(e.read).not.toHaveBeenCalled();}
   expect(screen.getAllByRole("tab").map(n=>n.textContent)).toEqual(["Overview","Plan","Work","Evidence","More"]);
  } finally {ui.unmount();delete window.MastermindMissionHost;history.replaceState(null,"","/os/");}
 });
});
