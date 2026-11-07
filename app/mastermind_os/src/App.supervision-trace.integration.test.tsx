// @vitest-environment jsdom
// Real App -> NativeClient/Host -> existing exact canonical source fixture.
// Only native invoke/listen is inert. No provider, account, Runtime write or
// operation is invoked. Reuse the complete SAME-run discovery fixture without edits.
import {webcrypto} from "node:crypto";
import actual from "./fixtures/project-discovery-app-source.json";
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import {App} from "./App";
import {decodeMissionv3} from "./mission";
import {createNativeClient} from "./host";
import {composeMissionHost} from "./compose-mission-host";
import {decodeLaunchBindingConfig} from "./launch-config";
const pair={workRef:actual.programs.canonical_projects[0].work_ref,rootJobId:actual.mission.mission.root_job_id!};
const disposals:Array<()=>void>=[];
beforeEach(()=>{
 vi.stubGlobal("crypto",webcrypto);
 history.replaceState(null,"","/os/?"+new URLSearchParams({work_ref:pair.workRef,root_job_id:pair.rootJobId}));
 delete window.MastermindMissionHost;
});
afterEach(()=>{cleanup();disposals.splice(0).forEach(dispose=>dispose());vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(locale: "en" | "zh-CN" = "en"){
 expect(decodeMissionv3(actual.mission,pair)).not.toBeNull();
 const events=new Map<string,Set<(event:{payload:unknown})=>void>>();
 let nextMission:Promise<unknown>|null=null;
 const invoke=vi.fn(async(name:string,input?:Record<string,unknown>):Promise<unknown>=>{
  if(name==="auth_status")return {status:"signed_in",reason:null,acquisition:true,content:true};
  if(name==="executive_auth_status")return {generation:1,available:true};
  if(name==="executive_context")return {schema:"mastermind.os.executive.owner_context.v1",principal_scope:"c".repeat(64),verified_expiry:Math.floor(Date.now()/1000)+600,profile:{name:"web_ceo_v3",server_version:"1.5.0"}};
  if(name==="read_programs")return structuredClone(actual.programs);
  if(name==="read_control_room_state")return structuredClone(actual.programs.control_room);
  if(name==="read_mission_v3"){
   expect(input).toEqual({selection:{work_ref:pair.workRef,root_job_id:pair.rootJobId}});
   return nextMission??structuredClone(actual.mission);
  }
  if(name==="read_work"||name==="executive_session_context")throw Error("INERT_READ_UNAVAILABLE");
  throw Error("UNRECORDED_NATIVE_EFFECT:"+name);
 });
 const raw=await createNativeClient(invoke as never,async(name,listener)=>{
  const handlers=events.get(name)??new Set();handlers.add(listener);events.set(name,handlers);return()=>handlers.delete(listener);
 });
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:pair.workRef,priority:0,attemptLimit:1,
  projects:[{ref:"executive-infrastructure",label:"Infrastructure"}],profiles:[{ref:"research_only",label:"Research"},{ref:"native_research_only",label:"Native research"}]}))!;
 const composed=composeMissionHost(raw,config,new IDBFactory(),"native");disposals.push(composed.dispose);
 await composed.ready;await composed.sessionReady;window.MastermindMissionHost=composed.host;
 render(<App locale={locale}/>);
 await waitFor(()=>expect(invoke.mock.calls.some(([name])=>name==="read_mission_v3")).toBe(true));
 const advanced=document.querySelector<HTMLDetailsElement>("details.nav-advanced")!;
 if(!advanced.open)fireEvent.click(advanced.querySelector("summary")!);
 fireEvent.click(screen.getByRole("button",{name:locale === "zh-CN" ? "会话工作区" : "Session Estate"}));
 const trace=await screen.findByRole("region",{name:locale === "zh-CN" ? "监督与追踪" : "Supervision and trace"});
 await within(trace).findByRole("heading",{name:locale === "zh-CN" ? "编排追踪" : "Orchestration trace"});
 return {trace,invoke,host:composed.host,store:composed.host.commandBinding!.store,hold(){let resolve!:(value:unknown)=>void;nextMission=new Promise(r=>{resolve=r;});return(value:unknown=actual.mission)=>resolve(structuredClone(value));},
  withdraw(){events.get("mastermind-auth-state")?.forEach(fn=>fn({payload:{status:"signed_out",reason:"NATIVE_TOKEN_EXPIRED",acquisition:false,content:false}}));}};
}
function reads(e:Awaited<ReturnType<typeof setup>>){return e.invoke.mock.calls.filter(([name])=>name==="read_mission_v3").length;}
function noCommands(e:Awaited<ReturnType<typeof setup>>){expect(e.invoke.mock.calls.every(([name])=>["auth_status","executive_auth_status","executive_context","read_programs","read_control_room_state","read_mission_v3","read_work","executive_session_context"].includes(name)), e.invoke.mock.calls.map(([name])=>name).join(",")).toBe(true);}
it("explicit trace read reuses exact selected source; disclosure inspection and return/reopen preserve scope with no command",async()=>{
 const e=await setup();const original=reads(e);const query=location.search;
 const button=within(e.trace).getByRole("button",{name:"Read current mission"});
 fireEvent.click(button);
 await waitFor(()=>expect(reads(e)).toBe(original+1));
 await within(e.trace).findByRole("heading",{name:"Orchestration trace"});
 const details=within(e.trace).getByRole("heading",{name:"Orchestration trace"}).closest("details")!;
 fireEvent.click(details.querySelector("summary")!);expect(details.open).toBe(true);
 expect(within(details).getByText("Dispatch state")).toBeTruthy();
 fireEvent.click(details.querySelector("summary")!);expect(details.open).toBe(false);
 fireEvent.click(screen.getByRole("button",{name:"Today"}));
 fireEvent.click(screen.getByRole("button",{name:"Session Estate"}));
 const returned=screen.getByRole("region",{name:"Supervision and trace"});
 expect(within(returned).getByRole("heading",{name:"Orchestration trace"})).toBeTruthy();
 expect(returned.textContent).toContain(pair.workRef);expect(returned.textContent).toContain(pair.rootJobId);
 expect(location.search).toBe(query);expect(reads(e)).toBe(original+1);
 expect(await e.store.read("c".repeat(64))).toBeNull();noCommands(e);
});
it("withdraws late trace read on actual native auth expiry and cannot reuse detached read control",async()=>{
 const e=await setup();const finish=e.hold();const button=within(e.trace).getByRole("button",{name:"Read current mission"});
 const before=reads(e);fireEvent.click(button);await waitFor(()=>expect(reads(e)).toBe(before+1));
 await act(async()=>{e.withdraw();});await act(async()=>{finish();});
 expect(screen.queryByRole("region",{name:"Supervision and trace"})).toBeNull();
 fireEvent.click(button);expect(reads(e)).toBe(before+1);noCommands(e);
});
it("refuses detached Host control and withholds a late response after Host replacement",async()=>{
 const e=await setup();const finish=e.hold();const button=within(e.trace).getByRole("button",{name:"Read current mission"});
 const before=reads(e);fireEvent.click(button);await waitFor(()=>expect(reads(e)).toBe(before+1));
 window.MastermindMissionHost={...e.host};
 await act(async()=>{finish();});
 expect(within(e.trace).queryByRole("heading",{name:"Orchestration trace"})).toBeNull();
 fireEvent.click(button);expect(reads(e)).toBe(before+1);noCommands(e);
});

it("rejects a foreign selected-source response without guessing or issuing another read",async()=>{
 const e=await setup();const finish=e.hold();const before=reads(e);
 fireEvent.click(within(e.trace).getByRole("button",{name:"Read current mission"}));
 await waitFor(()=>expect(reads(e)).toBe(before+1));
 const foreign=structuredClone(actual.mission);foreign.program.work_ref="WS:FOREIGN";
 await act(async()=>{finish(foreign);});
 expect(within(e.trace).queryByRole("heading",{name:"Orchestration trace"})).toBeNull();
 expect(e.trace.textContent).not.toContain("WS:FOREIGN");expect(reads(e)).toBe(before+1);
 expect(await e.store.read("c".repeat(64))).toBeNull();noCommands(e);
});

it("localizes the ZH trace read notice and unavailable chip through read and return without changing source scope",async()=>{
 const e=await setup("zh-CN"),before=reads(e),query=location.search;
 const notice="来源时间和观测时间按已有记录显示；本次显示未刷新这些时间。";
 const localized=()=>{
  expect(screen.getByText(notice)).toBeTruthy();
  expect(screen.queryByText("Source and observation clocks are displayed as projected; this render did not refresh them.")).toBeNull();
  const state=document.querySelector(".workspace-header .facts .state")!;
  expect(state.textContent).toBe("暂不可用");expect(state.classList.contains("state-unavailable")).toBe(true);
 };
 await waitFor(localized);
 fireEvent.click(within(e.trace).getByRole("button",{name:"读取当前任务"}));
 await waitFor(()=>expect(reads(e)).toBe(before+1));
 await within(e.trace).findByRole("heading",{name:"编排追踪"});await waitFor(localized);
 expect(e.trace.textContent).toContain(actual.mission.generated_at);
 fireEvent.click(screen.getByRole("button",{name:"今天"}));
 fireEvent.click(screen.getByRole("button",{name:"会话工作区"}));
 const returned=screen.getByRole("region",{name:"监督与追踪"});await waitFor(localized);
 expect(returned.textContent).toContain(pair.workRef);expect(returned.textContent).toContain(pair.rootJobId);
 expect(location.search).toBe(query);expect(reads(e)).toBe(before+1);
 expect(await e.store.read("c".repeat(64))).toBeNull();noCommands(e);
});
