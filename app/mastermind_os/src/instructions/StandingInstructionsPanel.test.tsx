// @vitest-environment jsdom
import {useState} from "react";
import {afterEach,it,expect,vi} from "vitest";
import {cleanup,fireEvent,render,screen} from "@testing-library/react";
import {IDBFactory} from "fake-indexeddb";
import owner from "./fixtures/instruction-owner.json";
import {StandingInstructionsPanel,type StandingInstructionsPanelProps} from "./StandingInstructionsPanel";
import {createInstructionAdmissionCommandPort,type InstructionAdmissionSnapshot,type InstructionAdmissionTransport} from "./instruction-command-port";
import {OperationController} from "../orchestration/operation-controller";
import {createIndexedDbPendingPointerStore} from "../orchestration/indexeddb-pending-pointer-store";
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const selection={work_ref:"WS:ONE",instruction_ref:"INS:DAILY-ONE"};
function bound(){
 const ref:{current:InstructionAdmissionSnapshot}={current:{selection,data:owner.current,dataGeneration:"1",generation:"1",canRead:true}};
 const io={pause:vi.fn<InstructionAdmissionTransport["pause"]>(async()=>owner.unknown),status:vi.fn<InstructionAdmissionTransport["status"]>(async()=>owner.status)};
 const store=createIndexedDbPendingPointerStore(new IDBFactory()),controller=new OperationController(createInstructionAdmissionCommandPort(()=>ref.current,io),store);
 return {ref,io,store,controller};
}
function props(value=bound()):StandingInstructionsPanelProps{return {selection:{work_ref:"WS:ONE"},selectedInstructionRef:selection.instruction_ref,canRead:true,sourceGeneration:"1",content:{data:owner.project_current,generation:"1",readVersion:1},control:{selection,data:owner.current,generation:"1",readVersion:1},controller:value.controller,onControlConsumed:vi.fn(),onReadInstructions:vi.fn(),onReadCurrent:vi.fn(),onFindOriginal:vi.fn(),onSelectInstruction:vi.fn(),onChangeInConversation:vi.fn()};}
function random(){vi.spyOn(crypto,"getRandomValues").mockImplementation(array=>{(array as Uint8Array).fill(0x11);return array;});}
it("shows actual content and stable instruction caveat without a mount read or mutation",()=>{
 const binding=bound(),p=props(binding);render(<StandingInstructionsPanel {...p}/>);
 expect(screen.getAllByText("Review the project carefully.")).toHaveLength(2);
 expect(screen.getByText("Stops new work from this instruction. Other project work and work already running may continue.")).toBeTruthy();
 expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(false);
 expect(binding.io.pause).not.toHaveBeenCalled();expect(binding.io.status).not.toHaveBeenCalled();expect(p.onReadInstructions).not.toHaveBeenCalled();
 expect(screen.queryByRole("button",{name:/Resume/})).toBeNull();
});
it("keeps absent, explicitly empty and unavailable content distinct",()=>{
 const p=props(),view=render(<StandingInstructionsPanel {...p} content={{data:owner.project_only_empty,generation:"1",readVersion:1}}/>);
 expect(screen.getByText("This project currently supplies an empty instruction list.")).toBeTruthy();
 view.rerender(<StandingInstructionsPanel {...p} content={{data:{...owner.project_only_empty,declaration:"NOT_DECLARED"},generation:"1",readVersion:2}}/>);expect(screen.getByText("No standing instructions were declared for this project.")).toBeTruthy();
 view.rerender(<StandingInstructionsPanel {...p} content={{data:{...owner.project_only_empty,availability:"UNAVAILABLE",source:null,declaration:null,instructions:null,recovery_identity:null,reason_codes:["SOURCE_UNAVAILABLE"]},generation:"1",readVersion:3}}/>);
 expect(screen.getAllByText("Standing instructions are unavailable.").length).toBeGreaterThan(0);expect(screen.queryByText("The selected instruction is not supplied in the current project content.")).toBeNull();
});
it("quotes only the exact current instruction into the existing unsent draft callback",()=>{
 const p=props();render(<StandingInstructionsPanel {...p}/>);fireEvent.click(screen.getByRole("button",{name:"Change in conversation"}));
 expect(p.onChangeInConversation).toHaveBeenCalledWith(expect.objectContaining({excerpt:"Review the project carefully.",label:expect.stringContaining("INS:DAILY-ONE")}));
 expect(p.onControlConsumed).not.toHaveBeenCalled();expect(screen.getByText("Adds this instruction to the existing unsent draft. Nothing is sent or published.")).toBeTruthy();
});
it("unknown then failed fresh read still reaches same-original status with no duplicate Pause",async()=>{
 random();const binding=bound(),p=props(binding),view=render(<StandingInstructionsPanel {...p}/>);
 fireEvent.click(screen.getByRole("button",{name:"Pause this instruction"}));await screen.findByText(/original request outcome is unresolved/);
 expect(p.onControlConsumed).toHaveBeenCalledWith(selection,"1",1);binding.ref.current={...binding.ref.current,data:null,dataGeneration:null};
 view.rerender(<StandingInstructionsPanel {...p} content={null} control={null}/>);
 const recover=screen.getByRole("button",{name:"Check original instruction request"}) as HTMLButtonElement;expect(recover.disabled).toBe(false);fireEvent.click(recover);
 await screen.findByText("Pause request committed. Check current status to confirm the current setting.");
 expect(binding.io.pause).toHaveBeenCalledTimes(1);expect(binding.io.status).toHaveBeenCalledTimes(1);expect(binding.io.status.mock.calls[0]?.[0].command_id).toBe(owner.status.selection.command_id);
 expect(await binding.store.read(owner.current.owner_context.principal_scope)).toBeNull();expect(screen.queryByText("New work from this instruction is paused.")).toBeNull();
});
it("parent exact-read consumption prevents a remount from resurrecting pre-Pause controls",async()=>{
 random();const binding=bound(),p=props(binding);
 function Harness(){const[show,setShow]=useState(true),[control,setControl]=useState(p.control);return <><button onClick={()=>setShow(value=>!value)}>Toggle details</button>{show&&<StandingInstructionsPanel {...p} control={control} onControlConsumed={()=>setControl(null)}/>}</>;}
 render(<Harness/>);fireEvent.click(screen.getByRole("button",{name:"Pause this instruction"}));await screen.findByText(/original request outcome is unresolved/);
 fireEvent.click(screen.getByRole("button",{name:"Toggle details"}));fireEvent.click(screen.getByRole("button",{name:"Toggle details"}));
 expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(true);expect(binding.io.pause).toHaveBeenCalledTimes(1);
});
it("auth/generation departure masks source facts and actions on the same render",()=>{
 const p=props(),view=render(<StandingInstructionsPanel {...p}/>);view.rerender(<StandingInstructionsPanel {...p} canRead={false} sourceGeneration="2"/>);
 expect(screen.queryByText("Review the project carefully.")).toBeNull();expect(screen.queryByText("WS:ONE")).toBeNull();expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(true);
 expect((screen.getByRole("button",{name:"Check original instruction request"}) as HTMLButtonElement).disabled).toBe(true);
});
it("keeps recorded pause source/clock separate from changed current text and real current gate",()=>{
 const p=props(),changed=structuredClone(owner.project_current),gate=structuredClone(owner.paused);changed.instructions[0].revision="f".repeat(64);gate.instruction_revision="f".repeat(64);
 render(<StandingInstructionsPanel {...p} content={{data:changed,generation:"1",readVersion:2}} control={{data:gate,selection,generation:"1",readVersion:2}}/>);
 expect(screen.getByText("The instruction text changed after this pause was recorded. It is still paused.")).toBeTruthy();expect(screen.getByText("Current instruction")).toBeTruthy();expect(screen.getByText("Recorded pause request")).toBeTruthy();expect(screen.getByText("Pause recorded at")).toBeTruthy();
 expect(screen.getByText(owner.paused.current_receipt.command_id)).toBeTruthy();
});
it("Chinese copy preserves instruction-only semantics and language",()=>{
 render(<StandingInstructionsPanel {...props()} locale="zh-CN"/>);expect(screen.getByRole("region").getAttribute("lang")).toBe("zh-CN");expect(screen.getByText("停止由此指令产生的新工作；其他项目工作及已在运行的工作可能继续。")).toBeTruthy();
});
