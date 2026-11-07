// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, beforeEach, expect, it, vi} from "vitest";
import {App} from "./App";
import {bindMissionHost, createNativeClient} from "./host";
import {controlRoomFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import producer from "./direction/fixtures/accepted-direction-owner.json";
const signed={status:"signed_in",reason:null,acquisition:true,content:true};
beforeEach(async()=>{
  history.replaceState(null,"","/os/");delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(hold=false) {
  const room=controlRoomFixture();room.work=[room.work[0]];
  room.work[0].work_ref=producer.selection.work_ref;room.work[0].agent_os.title="Direction test programme";
  room.autonomy.responsibilities=[];
  let notify!:(event:{payload:unknown})=>void,finish!:(body:unknown)=>void;
  const pending=new Promise(resolve=>{finish=resolve;});
  const invoke=vi.fn(async(command:string,args?:unknown)=>{
    if(command==="auth_status")return signed;
    if(command==="read_programs")return {...structuredClone(programs),control_room:room};
    if(command==="read_project_direction") {
      expect(args).toEqual({selection:producer.selection});return hold?pending:structuredClone(producer);
    }
    throw new Error("Unexpected fixture command");
  });
  const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
  const host=bindMissionHost(raw);window.MastermindMissionHost=host;
  const read=vi.spyOn(host,"readProjectDirection");
  render(<App/>);fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Direction test programme"}));
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  return {invoke,read,notify,finish};
}
it("reads the actual Direction owner body explicitly through the real host for a rootless project",async()=>{
  const e=await setup();expect(e.read).not.toHaveBeenCalled();
  expect(document.querySelector("div.notice[role=status]")?.textContent).toBe("Choose a project to view its work.");
  expect(screen.queryByRole("button",{name:"Change direction in conversation"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Read Direction"}));
  expect(await screen.findByRole("article",{name:"Current accepted Direction"})).toHaveProperty("textContent",expect.stringContaining(producer.direction.current.answer));
  expect(e.read).toHaveBeenCalledExactlyOnceWith({...producer.selection,signal:expect.any(AbortSignal)});
  expect(e.invoke.mock.calls.filter(([name])=>/mission|current_window|submit|prepare|launch/.test(name))).toHaveLength(0);
  act(()=>e.notify({payload:{status:"signed_out",reason:"AUTHENTICATION_REQUIRED",acquisition:false,content:false}}));
  expect(screen.queryByRole("article",{name:"Current accepted Direction"})).toBeNull();
  expect(document.body.textContent).not.toContain(producer.direction.current.answer);
});
it("withdraws a pending Direction read and ignores its late result after catalogue refresh",async()=>{
  const e=await setup(true);fireEvent.click(screen.getByRole("button",{name:"Read Direction"}));
  await waitFor(()=>expect(e.read).toHaveBeenCalledTimes(1));const signal=e.read.mock.calls[0][0].signal;
  fireEvent.click(screen.getByRole("button",{name:"Refresh Projects"}));expect(signal.aborted).toBe(true);
  await act(async()=>e.finish(structuredClone(producer)));
  expect(screen.queryByRole("article",{name:"Current accepted Direction"})).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(1);
});
