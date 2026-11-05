// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import fixture from "./admission/fixtures/project-admission-owner.json";
import {useProjectAdmissionWorkspace, type ProjectAdmissionWorkspaceProps} from "./useProjectAdmissionWorkspace";
import {createIndexedDbPendingPointerStore} from "./orchestration/indexeddb-pending-pointer-store";
import type {ProjectAdmissionTransport} from "./admission/project-admission-command-port";

afterEach(() => {cleanup();vi.restoreAllMocks();});
const selection=fixture.open.selection, scope=fixture.open.owner_context.principal_scope;
const pointer={kind:"project_pause" as const,targetKey:selection.work_ref,operationKey:fixture.pause_result.selection.command_id};
const unavailable={schema:fixture.open.schema,selection,availability:"UNAVAILABLE",state:null,permissions:null,owner_context:null,current_receipt:null,pause_token:null,reason_codes:["SOURCE_UNAVAILABLE"]};
function environment() {
  let data:unknown=fixture.open;
  const read=vi.fn(async()=>data);
  const transport={
    pause:vi.fn<ProjectAdmissionTransport["pause"]>(async()=>fixture.pause_result),
    resume:vi.fn<ProjectAdmissionTransport["resume"]>(async()=>fixture.resume_result),
    status:vi.fn<ProjectAdmissionTransport["status"]>(async()=>({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"OBSERVED",receipt:fixture.pause_result.receipt,reason_codes:[]})),
  };
  const store=createIndexedDbPendingPointerStore(new IDBFactory());
  const props:ProjectAdmissionWorkspaceProps={selection,authGeneration:1,sourceGeneration:()=>1,canRead:()=>true,readCurrent:read,transport,store,locale:"en"};
  return {props,read,transport,store,setData:(value:unknown)=>{data=value;}};
}
function Driver({show=true,...props}:ProjectAdmissionWorkspaceProps&{show?:boolean}) {
  const panel=useProjectAdmissionWorkspace(props);
  return show ? panel : <p>Another App route</p>;
}
function random(value=0xaa) {
  vi.spyOn(globalThis.crypto,"getRandomValues").mockImplementation(array=>{(array as Uint8Array).fill(value);return array;});
}
async function readCurrent() {
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  await screen.findByText("New work is not paused here. Other limits and permissions still apply.");
  await waitFor(()=>expect((screen.getByRole("button",{name:"Pause new work"}) as HTMLButtonElement).disabled).toBe(false));
}

it("has no mount effect, reads explicitly and uses only the supplied incumbent store",async()=>{
  const e=environment();render(<Driver {...e.props}/>);
  expect(e.read).not.toHaveBeenCalled();expect(e.transport.status).not.toHaveBeenCalled();
  await readCurrent();
  expect(e.read).toHaveBeenCalledExactlyOnceWith({selection,signal:expect.any(AbortSignal)});
  expect(e.transport.status).not.toHaveBeenCalled();expect(e.transport.pause).not.toHaveBeenCalled();
  expect(await e.store.read(scope)).toBeNull();
});

it("keeps controls disconnected without the actual store rather than creating a fallback",async()=>{
  const e=environment();render(<Driver {...e.props} store={undefined}/>);
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  expect(await screen.findByText("Project controls are not connected here.")).toBeTruthy();
  expect((screen.getByRole("button",{name:"Pause new work"}) as HTMLButtonElement).disabled).toBe(true);
  expect(e.transport.pause).not.toHaveBeenCalled();
});

it("commits one explicit Pause and requires a fresh owner read before a token-bound Resume",async()=>{
  random();const e=environment();render(<Driver {...e.props}/>);await readCurrent();
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
  expect(await screen.findByText(/Request committed/)).toBeTruthy();
  expect(e.transport.pause).toHaveBeenCalledExactlyOnceWith({selection,command_id:pointer.operationKey,signal:expect.any(AbortSignal)});
  expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(1);expect(e.transport.status).not.toHaveBeenCalled();
  e.setData(fixture.paused);
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  const resume=await screen.findByRole("button",{name:"Resume new work"});
  await waitFor(()=>expect((resume as HTMLButtonElement).disabled).toBe(false));
  vi.mocked(globalThis.crypto.getRandomValues).mockImplementation(array=>{(array as Uint8Array).fill(0xbb);return array;});
  fireEvent.click(resume);await screen.findByText(/Request committed/);
  expect(e.transport.resume).toHaveBeenCalledExactlyOnceWith({selection,command_id:fixture.resume_result.selection.command_id,pause_token:fixture.paused.pause_token,signal:expect.any(AbortSignal)});
  expect(e.transport.pause).toHaveBeenCalledTimes(1);
});

it("preserves UNKNOWN across route hiding and an unavailable current gate, then checks only the original key",async()=>{
  random();const e=environment();e.transport.pause.mockRejectedValue(new Error("private transport failure"));
  const view=render(<Driver {...e.props}/>);await readCurrent();
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
  await screen.findByText(/original request outcome is unresolved/);
  expect(await e.store.read(scope)).toEqual(pointer);
  view.rerender(<Driver {...e.props} show={false}/>);view.rerender(<Driver {...e.props}/>);
  expect(screen.getByText(/original request outcome is unresolved/)).toBeTruthy();
  e.setData(unavailable);fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  await waitFor(()=>expect(e.read).toHaveBeenCalledTimes(2));
  await waitFor(()=>expect((screen.getByRole("button",{name:"Check original project request"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Check original project request"}));
  await screen.findByText(/Request committed/);
  expect(e.transport.status).toHaveBeenCalledExactlyOnceWith({kind:"project_pause",selection,command_id:pointer.operationKey,signal:expect.any(AbortSignal)});
  expect(e.transport.pause).toHaveBeenCalledTimes(1);expect(e.transport.resume).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain("private transport failure");
});

it("reopens the exact durable pointer only after explicit current-state read and never mints a replacement",async()=>{
  const e=environment();await e.store.reserve(scope,pointer);
  e.transport.status.mockResolvedValueOnce({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"NOT_OBSERVED",receipt:null,reason_codes:[]});
  const mint=vi.spyOn(globalThis.crypto,"getRandomValues");
  render(<Driver {...e.props}/>);expect(e.transport.status).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  await screen.findByText(/original request outcome is unresolved/);
  expect(await e.store.read(scope)).toEqual(pointer);
  expect((screen.getByRole("button",{name:"Pause new work"}) as HTMLButtonElement).disabled).toBe(true);
  expect(e.transport.status).toHaveBeenCalledTimes(1);expect(mint).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Check original project request"}));
  await screen.findByText(/Request committed/);
  expect(e.transport.status.mock.calls.map(([request])=>request.command_id)).toEqual([pointer.operationKey,pointer.operationKey]);
  expect(e.transport.pause).not.toHaveBeenCalled();expect(e.transport.resume).not.toHaveBeenCalled();
});

it("holds new actions visibly when the original pending state cannot be read, even without an exposed pointer",async()=>{
  const e=environment();vi.spyOn(e.store,"read").mockRejectedValue(new Error("private store failure"));
  render(<Driver {...e.props}/>);fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  expect(await screen.findByText(/pending request state could not be read/)).toBeTruthy();
  expect((screen.getByRole("button",{name:"Pause new work"}) as HTMLButtonElement).disabled).toBe(true);
  expect(e.transport.pause).not.toHaveBeenCalled();expect(e.transport.status).not.toHaveBeenCalled();
  expect(document.body.textContent).not.toContain("private store failure");
});

it("invalidates a pending action on actual auth/source generation change without erasing its durable hint",async()=>{
  random();const e=environment();let finish!:(value:unknown)=>void;
  e.transport.pause.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
  const view=render(<Driver {...e.props}/>);await readCurrent();
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
  await waitFor(()=>expect(e.transport.pause).toHaveBeenCalledTimes(1));
  const signal=e.transport.pause.mock.calls[0][0].signal;
  view.rerender(<Driver {...e.props} authGeneration={2} sourceGeneration={()=>2} canRead={()=>false}/>);
  expect(signal.aborted).toBe(true);
  expect(screen.queryByText("New work is not paused here. Other limits and permissions still apply.")).toBeNull();
  await act(async()=>finish(fixture.pause_result));
  expect(screen.queryByText(/Request committed/)).toBeNull();
  expect(await e.store.read(scope)).toEqual(pointer);
  expect(e.transport.status).not.toHaveBeenCalled();expect(e.transport.pause).toHaveBeenCalledTimes(1);
});

it.each([undefined,-1,NaN,1.5])("does not read or qualify controls from invalid actual host generation %s",async generation=>{
  const e=environment();render(<Driver {...e.props} sourceGeneration={generation===undefined?undefined:()=>generation}/>);
  expect((screen.getByRole("button",{name:"Check pause status"}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  expect(e.read).not.toHaveBeenCalled();expect(e.transport.pause).not.toHaveBeenCalled();
});

it("retains a legitimate observed host generation zero without substituting a fallback",async()=>{
  const e=environment();render(<Driver {...e.props} sourceGeneration={()=>0}/>);await readCurrent();
  expect(e.read).toHaveBeenCalledTimes(1);expect(e.transport.pause).not.toHaveBeenCalled();
});

it("does not resurrect the pre-Pause gate when Details remounts after acceptance",async()=>{
  random();const e=environment();const view=render(<Driver {...e.props}/>);await readCurrent();
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));await screen.findByText(/Request committed/);
  view.rerender(<Driver {...e.props} show={false}/>);view.rerender(<Driver {...e.props}/>);
  expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();
  expect(screen.queryByText("New work is not paused here. Other limits and permissions still apply.")).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(1);expect(e.transport.pause).toHaveBeenCalledTimes(1);
});


it("withdraws the old controller when its actual store disappears and restores only original recovery with that same store",async()=>{
  const e=environment();const view=render(<Driver {...e.props}/>);await readCurrent();
  await e.store.reserve(scope,pointer);
  e.transport.status.mockResolvedValue({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"NOT_OBSERVED",receipt:null,reason_codes:[]});
  view.rerender(<Driver {...e.props} store={undefined}/>);
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  await screen.findByText("Project controls are not connected here.");
  expect((screen.getByRole("button",{name:"Pause new work"}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
  expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();
  expect(e.transport.status).not.toHaveBeenCalled();
  expect(e.transport.pause).not.toHaveBeenCalled();expect(e.transport.resume).not.toHaveBeenCalled();
  expect(await e.store.read(scope)).toEqual(pointer);
  view.rerender(<Driver {...e.props}/>);
  fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));
  await screen.findByText(/original request outcome is unresolved/);
  expect(e.transport.status).toHaveBeenCalledExactlyOnceWith({kind:"project_pause",selection,command_id:pointer.operationKey,signal:expect.any(AbortSignal)});
  expect(await e.store.read(scope)).toEqual(pointer);
  expect(e.transport.pause).not.toHaveBeenCalled();expect(e.transport.resume).not.toHaveBeenCalled();
});
