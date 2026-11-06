// @vitest-environment jsdom
import {afterEach,it,expect,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {IDBFactory} from "fake-indexeddb";
import owner from "./fixtures/instruction-owner.json";
import {useStandingInstructionsWorkspace,type StandingInstructionsWorkspaceProps} from "./useStandingInstructionsWorkspace";
import {createIndexedDbPendingPointerStore} from "../orchestration/indexeddb-pending-pointer-store";
import {serializeInstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const selected={work_ref:"WS:ONE",instruction_ref:"INS:DAILY-ONE"},original={kind:"instruction_pause" as const,operationKey:owner.status.selection.command_id,targetKey:serializeInstructionAdmissionTarget(selected)!};
function setup(){
 const readContent=vi.fn<NonNullable<StandingInstructionsWorkspaceProps["readContent"]>>(async()=>owner.project_current),readCurrent=vi.fn<NonNullable<StandingInstructionsWorkspaceProps["readCurrent"]>>(async()=>owner.current);
 const pause=vi.fn(async()=>owner.unknown),status=vi.fn(async()=>owner.status),store=createIndexedDbPendingPointerStore(new IDBFactory());
 const props:StandingInstructionsWorkspaceProps={selection:{work_ref:"WS:ONE"},authGeneration:1,sourceGeneration:()=>0,canRead:()=>true,readContent,readCurrent,transport:{pause,status},store,locale:"en"};
 return {props,readContent,readCurrent,pause,status,store};
}
function Workspace(props:StandingInstructionsWorkspaceProps){return useStandingInstructionsWorkspace(props);}
async function select(){fireEvent.click(screen.getByRole("button",{name:"Read instructions"}));await screen.findByRole("button",{name:/Review instruction:/});fireEvent.click(screen.getByRole("button",{name:/Review instruction:/}));}
it("does no mount I/O, reads real content/control explicitly and hydrates an empty DB without status or mutation",async()=>{
 const e=setup();render(<Workspace {...e.props}/>);expect(e.readContent).not.toHaveBeenCalled();expect(e.readCurrent).not.toHaveBeenCalled();expect(e.pause).not.toHaveBeenCalled();
 await select();expect(e.readCurrent).not.toHaveBeenCalled();fireEvent.click(screen.getByRole("button",{name:"Check instruction status"}));
 await waitFor(()=>expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(false));
 expect(e.readContent).toHaveBeenCalledTimes(1);expect(e.readCurrent).toHaveBeenCalledTimes(1);expect(e.status).not.toHaveBeenCalled();expect(e.pause).not.toHaveBeenCalled();
});
it("joins explicit Pause→unknown→readonly original status with exact App-held source withholding",async()=>{
 vi.spyOn(crypto,"getRandomValues").mockImplementation(array=>{(array as Uint8Array).fill(0x11);return array;});const e=setup();render(<Workspace {...e.props}/>);await select();fireEvent.click(screen.getByRole("button",{name:"Check instruction status"}));
 await waitFor(()=>expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(false));fireEvent.click(screen.getByRole("button",{name:"Pause this instruction"}));await screen.findByText(/original request outcome is unresolved/);
 expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(true);expect(await e.store.read(owner.current.owner_context.principal_scope)).toEqual(original);
 fireEvent.click(screen.getByRole("button",{name:"Check original instruction request"}));await screen.findByText("Pause request committed. Check current status to confirm the current setting.");expect(e.pause).toHaveBeenCalledTimes(1);expect(e.status).toHaveBeenCalledTimes(1);expect(await e.store.read(owner.current.owner_context.principal_scope)).toBeNull();
});
it("ordinary project-only reopen discovers a removed INS then requalifies its actual current grant before same-ID status",async()=>{
 const e=setup();await e.store.reserve(owner.current.owner_context.principal_scope,original);e.readContent.mockResolvedValue(owner.project_only_empty);e.readCurrent.mockResolvedValue(owner.removed);render(<Workspace {...e.props}/>);
 fireEvent.click(screen.getByRole("button",{name:"Read instructions"}));await screen.findByText("This project currently supplies an empty instruction list.");fireEvent.click(screen.getByRole("button",{name:"Check original instruction request"}));
 await screen.findByText("Pause request committed. Check current status to confirm the current setting.");expect(e.readCurrent).toHaveBeenCalledWith(expect.objectContaining({selection:selected}));expect(e.status).toHaveBeenCalledTimes(1);expect(e.pause).not.toHaveBeenCalled();expect(await e.store.read(owner.current.owner_context.principal_scope)).toBeNull();
});
it("does not borrow a mismatched control principal or expired content READ identity",async()=>{
 const e=setup();await e.store.reserve(owner.current.owner_context.principal_scope,original);e.readContent.mockResolvedValue(owner.project_only_empty);e.readCurrent.mockResolvedValue({...owner.removed,owner_context:{principal_scope:"f".repeat(64)}});
 const view=render(<Workspace {...e.props}/>);fireEvent.click(screen.getByRole("button",{name:"Read instructions"}));await screen.findByText("This project currently supplies an empty instruction list.");fireEvent.click(screen.getByRole("button",{name:"Check original instruction request"}));
 await waitFor(()=>expect(e.readCurrent).toHaveBeenCalledTimes(1));await waitFor(()=>expect((screen.getByRole("button",{name:"Check instruction status"}) as HTMLButtonElement).disabled).toBe(false));expect(e.status).not.toHaveBeenCalled();expect(e.pause).not.toHaveBeenCalled();expect(await e.store.read(owner.current.owner_context.principal_scope)).toEqual(original);
 view.rerender(<Workspace {...e.props} authGeneration={2} canRead={()=>false}/>);expect((screen.getByRole("button",{name:"Check original instruction request"}) as HTMLButtonElement).disabled).toBe(true);expect(screen.queryByText("WS:ONE")).toBeNull();expect(await e.store.read(owner.current.owner_context.principal_scope)).toEqual(original);
});
it("masks a late body on host-generation/source-owner change without mounting another controller/store",async()=>{
 const e=setup();let finish!:(body:unknown)=>void,generation=0;e.readContent.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));const props={...e.props,sourceGeneration:()=>generation};
 const view=render(<Workspace {...props}/>);fireEvent.click(screen.getByRole("button",{name:"Read instructions"}));generation++;view.rerender(<Workspace {...props}/>);finish(owner.project_current);
 await waitFor(()=>expect(screen.queryByText("Review the project carefully.")).toBeNull());expect(e.pause).not.toHaveBeenCalled();expect(e.status).not.toHaveBeenCalled();expect(e.readContent).toHaveBeenCalledTimes(1);
});
it("malformed content settles as unavailable rather than leaving an infinite reading state",async()=>{
 const e=setup();e.readContent.mockResolvedValue({...owner.project_current,extra:true});render(<Workspace {...e.props}/>);fireEvent.click(screen.getByRole("button",{name:"Read instructions"}));
 await waitFor(()=>expect((screen.getByRole("button",{name:"Read instructions"}) as HTMLButtonElement).disabled).toBe(false));expect(e.readCurrent).not.toHaveBeenCalled();expect(e.pause).not.toHaveBeenCalled();
});
it("does not resurrect a consumed project read after an A→B→A selection detour",async()=>{
 const e=setup(),view=render(<Workspace {...e.props}/>);fireEvent.click(screen.getByRole("button",{name:"Read instructions"}));await screen.findByRole("button",{name:/Review instruction:/});
 view.rerender(<Workspace {...e.props} selection={{work_ref:"WS:OTHER"}}/>);expect(screen.queryByText("Review the project carefully.")).toBeNull();
 view.rerender(<Workspace {...e.props}/>);expect(screen.queryByText("Review the project carefully.")).toBeNull();expect(e.readContent).toHaveBeenCalledTimes(1);expect(e.pause).not.toHaveBeenCalled();
});
it("rechecks the actual host generation before a stale DOM gesture can reserve or copy into another auth context",async()=>{
 const e=setup();let generation=0;const draft=vi.fn(),props={...e.props,sourceGeneration:()=>generation,onChangeInConversation:draft};render(<Workspace {...props}/>);await select();fireEvent.click(screen.getByRole("button",{name:"Check instruction status"}));
 await waitFor(()=>expect((screen.getByRole("button",{name:"Pause this instruction"}) as HTMLButtonElement).disabled).toBe(false));generation++;
 fireEvent.click(screen.getByRole("button",{name:"Change in conversation"}));expect(draft).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Pause this instruction"}));await waitFor(()=>expect(e.pause).not.toHaveBeenCalled());expect(await e.store.read(owner.current.owner_context.principal_scope)).toBeNull();
});
