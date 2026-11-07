import {afterEach,expect,it,vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import {createNativeClient} from "./host";
import {composeMissionHost} from "./compose-mission-host";
import fixture from "./fixtures/project-conversation-history-owner.json";
const dispose:Array<()=>void>=[];afterEach(()=>dispose.splice(0).forEach(fn=>fn()));
async function setup(held=false){
 const events=new Map<string,(event:{payload:unknown})=>void>();let finish!:(value:unknown)=>void;
 const response=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string)=>{
  if(command==="auth_status")return {status:"signed_in",reason:null,acquisition:true,content:false};
  if(command==="executive_auth_status")return {generation:1,available:true};
  if(command==="executive_project_history_context")return held?response:structuredClone(fixture.context);
  throw Error("No fixture mutation or unlisted read");
 });
 const raw=await createNativeClient(invoke as never,async(name,listener)=>{events.set(name,listener);return()=>{};});
 const composed=composeMissionHost(raw,null,new IDBFactory());dispose.push(composed.dispose);
 await composed.sessionReady;
 return {raw,host:composed.host,invoke,events,finish};
}
it("forwards the real native fixed READ through all host seams with no constructor read or target",async()=>{
 const e=await setup();
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_project_history_context")).toHaveLength(0);
 const factory=e.host.session?.createProjectHistoryReader;expect(factory).toBeTypeOf("function");
 const reader=factory!({workRef:fixture.work_ref,currentWorkRef:()=>fixture.work_ref,selectionGeneration:()=>"project-epoch-1"});
 dispose.push(reader.dispose);
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_project_history_context")).toHaveLength(0);
 await reader.refresh();expect(reader.owner.context()).not.toBeNull();
 expect(e.invoke.mock.calls.find(([name])=>name==="executive_project_history_context")).toEqual([
  "executive_project_history_context",{workRef:fixture.work_ref}]);
 expect(e.invoke.mock.calls.filter(([name])=>/send|submit|create|targets/.test(name))).toHaveLength(0);
});
it("closes selector descriptors and extra/root/cursor inputs before native invocation",async()=>{
 const e=await setup(),read=e.raw.executiveSession!.historyContext!,signal=new AbortController().signal;
 const getter=vi.fn(()=>fixture.work_ref);
 const values:unknown[]=[{workRef:fixture.work_ref,rootJobId:"JOB-1"},{workRef:fixture.work_ref,cursor:"cursor"},
  {workRef:fixture.work_ref+"\n"},[fixture.work_ref],Object.defineProperty({},"workRef",{get:getter}),
  {[Symbol("hidden")]:1,workRef:fixture.work_ref}];
 for(const value of values)await expect(read(value as {workRef:string},signal)).rejects.toThrow("SESSION_HISTORY_SELECTION_INVALID");
 expect(getter).not.toHaveBeenCalled();
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_project_history_context")).toHaveLength(0);
});
it("drops a late project READ on the real Executive epoch without a second invocation",async()=>{
 const e=await setup(true),factory=e.host.session!.createProjectHistoryReader!;
 const reader=factory({workRef:fixture.work_ref,currentWorkRef:()=>fixture.work_ref,selectionGeneration:()=>"project-epoch-1"});dispose.push(reader.dispose);
 const pending=reader.refresh();await vi.waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==="executive_project_history_context")).toHaveLength(1));
 e.events.get("mastermind-executive-auth-state")!({payload:{generation:2,available:false}});
 e.finish(structuredClone(fixture.context));await pending;
 expect(reader.owner.context()).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==="executive_project_history_context")).toHaveLength(1);
});
