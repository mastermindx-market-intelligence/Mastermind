// @vitest-environment jsdom
// One actual Runtime/canonical compiler/HTTP operand; inert Auth/kernel transport.
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {act,cleanup,render,screen,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {IDBFactory} from "fake-indexeddb";
import {App} from "./App";
import {bindMissionHost,type RawClient,type AuthState} from "./host";
import source from "./fixtures/project-activity-whole-source.json";
beforeEach(()=>{
  history.replaceState(null,"",`/os/?work_ref=${encodeURIComponent(source.selection.work_ref)}&root_job_id=${source.selection.root_job_id}`);
  Object.defineProperty(globalThis,"indexedDB",{value:new IDBFactory(),configurable:true});
  delete window.MastermindMissionHost;delete(window as any).__TAURI_INTERNALS__;
  vi.useFakeTimers({toFake:["Date"]});
  vi.setSystemTime(new Date(source.final.programs.body.control_room.generated_at));
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();delete window.MastermindMissionHost;});
function fixtureClient(){
  let final=false,generation=1;
  let state:AuthState={status:"signed_in",reason:null,acquisition:true,content:true};
  const listeners=new Set<(state:AuthState)=>void>();
  const exact=(request:{workRef:string;rootJobId:string})=>{
    expect(request.workRef).toBe(source.selection.work_ref);expect(request.rootJobId).toBe(source.selection.root_job_id);
  };
  const activity=vi.fn(async(request:Parameters<NonNullable<RawClient["readRetainedActivity"]>>[0])=>{
    expect(request).toMatchObject(source.activity_selection);
    return final?source.final.activity.body:source.active.activity.result;
  });
  const result=vi.fn(async(request:Parameters<NonNullable<RawClient["readResult"]>>[0])=>{
    exact(request);expect(final).toBe(true);
    expect(request).toMatchObject({jobId:source.result_selection.job_id,attemptId:source.result_selection.attempt_id,
      resultEnvelopeDigest:source.result_selection.result_envelope_digest});
    return source.final.result.body;
  });
  const references=vi.fn(async(request:Parameters<NonNullable<RawClient["readResultReferences"]>>[0])=>{
    exact(request);return final?source.final.result_references.body:source.active.result_references.result;
  });
  const raw:RawClient={getState:()=>state,invalidationGeneration:()=>generation,
    subscribe:callback=>{listeners.add(callback);return()=>listeners.delete(callback);},signIn:async()=>{},signOut:async()=>{},
    readPrograms:async()=>final?source.final.programs.body:source.active.programs.result,
    readWork:async()=>final?source.final.work.body:source.active.work.result,
    readMission:async()=>final?source.final.mission.body:source.active.mission.result,
    readMissionV3:async request=>{exact(request);return final?source.final.mission.body:source.active.mission.result;},
    readAdmittedPlan:async()=>final?source.final.plan.body:source.active.plan.result,
    readRetainedActivity:activity,readResultReferences:references,readResult:result,
    readCurrentWindow:async()=>{throw new Error("No session window operand or SEND authority in this fixture");},
  };
  const host=bindMissionHost(raw);window.MastermindMissionHost=host;
  return{raw,host,activity,result,references,complete:()=>{final=true;generation++;for(const callback of listeners)callback(state);},
    revoke:()=>{state={status:"signed_out",reason:"fixture-withdrawal",acquisition:false,content:false};generation++;for(const callback of listeners)callback(state);}};
}
it("shows actual running Mission and recorded metadata, then original retained result and Back",async()=>{
  const user=userEvent.setup();const f=fixtureClient();render(<App/>);
  await user.click(screen.getByRole("button",{name:"Activity"}));
  const row=await screen.findByText(source.activity_selection.job_id,{selector:"code"});
  const item=row.closest("li")!;
  expect(item.textContent).toContain("Running");
  expect(f.activity).not.toHaveBeenCalled();expect(f.result).not.toHaveBeenCalled();
  await user.click(within(item).getByRole("button",{name:"Inspect retained activity"}));
  expect(await within(item).findByText("Recorded activity")).toBeTruthy();
  expect(within(item).getAllByText(/candidate recorded:/)).toHaveLength(source.active.activity.result.activity.rows.length);
  expect(item.textContent).toContain("not live tool streaming");
  expect(item.textContent).not.toContain("PRIVATE-COLLECTOR");
  await act(async()=>f.complete());
  await user.click(screen.getByRole("button",{name:"Projects"}));
  const title=source.final.programs.body.control_room.work[0].agent_os.title;
  await user.click(await screen.findByRole("button",{name:new RegExp(title)}));
  await user.click(await screen.findByRole("button",{name:"Project details"}));
  await user.click(await screen.findByRole("button",{name:"Work controls"}));
  await user.click(await screen.findByText("More work details",{selector:"summary"}));
  const work=await screen.findByRole("tab",{name:"Work"});await user.click(work);
  const liveWork=screen.getByRole("heading",{name:"Recorded work"}).closest("section")!;
  const originalRow=within(liveWork).getByText(source.activity_selection.job_id,{selector:"code"}).closest("li")!;
  await user.click(within(originalRow).getByRole("button",{name:"Inspect retained activity"}));
  expect(await within(originalRow).findByText("Recorded activity")).toBeTruthy();
  expect(f.activity).toHaveBeenCalledTimes(2);
  await user.click(await screen.findByRole("button",{name:"Show retained results"}));
  await user.click(await screen.findByRole("button",{name:new RegExp(source.result_selection.job_id)}));
  expect(await screen.findByRole("heading",{name:"Result detail"})).toBeTruthy();
  expect(f.result).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("heading",{name:"Retained result list"})).toBeNull();
  const summary=screen.getByText(source.final.result.body.result.content.summary,{exact:true});
  expect(summary.closest("details")).toBeNull();
  expect(summary.closest("article")!.querySelector("details")!.open).toBe(false);
  await user.click(screen.getByRole("button",{name:"Back to retained results"}));
  expect(await screen.findByRole("heading",{name:"Retained result list"})).toBeTruthy();
  expect(screen.getByRole("tab",{name:"Work"}).getAttribute("aria-selected")).toBe("true");
  expect(f.result).toHaveBeenCalledTimes(1);
});


it.each(["withdrawal","host-replacement"])("withholds a real late candidate reply after %s",async(boundary)=>{
  const user=userEvent.setup();const f=fixtureClient();let release!:()=>void;
  f.activity.mockImplementationOnce(()=>new Promise(resolve=>{release=()=>resolve(source.active.activity.result);}));
  render(<App/>);await user.click(screen.getByRole("button",{name:"Activity"}));
  const row=(await screen.findByText(source.activity_selection.job_id,{selector:"code"})).closest("li")!;
  await user.click(within(row).getByRole("button",{name:"Inspect retained activity"}));
  await act(async()=>{
    if(boundary==="withdrawal")f.revoke();
    else window.MastermindMissionHost=bindMissionHost({...f.raw});
    release();
  });
  expect(screen.queryByText("Recorded activity")).toBeNull();
  expect(f.result).not.toHaveBeenCalled();expect(f.activity).toHaveBeenCalledTimes(1);
});

it("does not expose an Activity selector from a foreign Mission root",async()=>{
  const user=userEvent.setup();const f=fixtureClient();
  const foreign=structuredClone(source.active.mission.result);foreign.mission.root_job_id="JOB-999";
  f.raw.readMissionV3=async()=>foreign;f.raw.readMission=async()=>foreign;
  render(<App/>);await user.click(screen.getByRole("button",{name:"Activity"}));
  await act(async()=>{for(let i=0;i<12;i++)await Promise.resolve();});
  expect(screen.queryByRole("button",{name:"Inspect retained activity"})).toBeNull();
  expect(f.activity).not.toHaveBeenCalled();expect(f.result).not.toHaveBeenCalled();
});
