// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {App} from "./App";
import {bindMissionHost,createNativeClient} from "./host";
import {controlRoomFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import plan from "./fixtures/project-plan-canonical-owner.json";
import journal from "./fixtures/project-journal-canonical-owner.json";
import work from "./fixtures/work-service-available.json";
const signed={status:"signed_in",reason:null,acquisition:true,content:true};
beforeEach(async()=>{
  history.replaceState(null,"","/os/"); delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(holdPlan=false){
  const room=controlRoomFixture();room.work=[room.work[0]];room.work[0].work_ref="WS:ONE";
  room.autonomy.responsibilities=[]; // A genuine catalogue row without a Runtime root.
  let notify!:(event:{payload:unknown})=>void,finish!:()=>void;
  const pending=new Promise(resolve=>{finish=()=>resolve(structuredClone(plan));});
  const invoke=vi.fn(async(command:string)=>{
    if(command==="auth_status")return signed;
    if(command==="read_programs")return {...structuredClone(programs),control_room:room};
    if(command==="read_work")return structuredClone(work);
    if(command==="read_project_plan")return holdPlan?pending:structuredClone(plan);
    if(command==="read_project_journal")return structuredClone(journal);
    throw new Error("Unexpected fixture command");
  });
  const client=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
  const host=bindMissionHost(client);window.MastermindMissionHost=host;
  const planRead=vi.spyOn(host,"readProjectPlan"),journalRead=vi.spyOn(host,"readProjectJournal");
  render(<App/>);fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Alpha program"}));
  return {host,invoke,planRead,journalRead,notify,finish};
}
it("opens rootless canonical Plan/Journal through actual host decoders under Project Details",async()=>{
  const f=await setup();
  expect(screen.getByRole("heading",{name:"Alpha program",level:1})).toBeTruthy();
  expect(screen.getAllByRole("heading",{level:1})).toHaveLength(1);
  expect(screen.getByRole("heading",{name:"Project team conversation"})).toBeTruthy();
  expect((screen.getByRole("button",{name:"Read project runs"}) as HTMLButtonElement).disabled).toBe(true);
  expect(await screen.findByText("Deliver the real owner content.")).toBeTruthy();
  expect(f.journalRead).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  fireEvent.click(screen.getByRole("button",{name:"Plan",exact:true}));
  const visiblePlan=within(screen.getByRole("region",{name:"Inspect Plan",exact:true}));
  expect(visiblePlan.getByText("Deliver the real owner content.")).toBeTruthy();
  expect(f.planRead).toHaveBeenCalledExactlyOnceWith({work_ref:"WS:ONE",signal:expect.any(AbortSignal)});
  expect(f.journalRead).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:/Back to project details/}));
  fireEvent.click(screen.getByRole("button",{name:"History and sources",exact:true}));
  fireEvent.click(screen.getByText("Project history and source evidence",{selector:"summary"}));
  fireEvent.click(screen.getByRole("button",{name:"Read project journal"}));
  await waitFor(()=>expect(f.journalRead).toHaveBeenCalledTimes(1));
  expect(f.journalRead).toHaveBeenCalledWith({work_ref:"WS:ONE",signal:expect.any(AbortSignal)});
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  expect(screen.getByText("Deliver the real owner content.")).toBeTruthy();
  expect(f.planRead).toHaveBeenCalledTimes(1);
  expect(f.invoke.mock.calls.some(([name])=>["read_mission","read_mission_v3","read_current_window","submit_command"].includes(name))).toBe(false);
  expect(screen.queryByRole("button",{name:/^Send$|^Launch$|^Pause$/})).toBeNull();
});
it("withdraws the pending rootless plan when the actual auth owner changes",async()=>{
  const f=await setup(true);fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  await waitFor(()=>expect(f.planRead).toHaveBeenCalledTimes(1));
  const signal=f.planRead.mock.calls[0][0].signal;
  act(()=>f.notify({payload:{status:"signed_out",reason:"AUTHENTICATION_REQUIRED",acquisition:false,content:false}}));
  expect(signal.aborted).toBe(true);
  await act(async()=>f.finish());
  expect(screen.queryByText("Deliver the real owner content.")).toBeNull();
  expect(f.journalRead).not.toHaveBeenCalled();
});

it("expires a rootless read selection on catalogue refresh without borrowing the previous Mission",async()=>{
  const f=await setup(true);fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  await waitFor(()=>expect(f.planRead).toHaveBeenCalledTimes(1));
  const signal=f.planRead.mock.calls[0][0].signal;
  fireEvent.click(screen.getByRole("button",{name:"Refresh Projects"}));
  expect(signal.aborted).toBe(true);
  await act(async()=>f.finish());
  expect(screen.queryByText("Deliver the real owner content.")).toBeNull();
  expect(await screen.findByRole("button",{name:"Open project Alpha program"})).toBeTruthy();
  expect(f.planRead).toHaveBeenCalledTimes(1);
});
