// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { IDBFactory } from "fake-indexeddb";
import fixture from "./fixtures/project-admission-owner.json";
import { ProjectAdmissionPanel, type ProjectAdmissionPanelProps } from "./ProjectAdmissionPanel";
import { createProjectAdmissionCommandPort, type ProjectAdmissionSnapshot, type ProjectAdmissionTransport } from "./project-admission-command-port";
import { OperationController } from "../orchestration/operation-controller";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
afterEach(()=>{cleanup();vi.restoreAllMocks();});
const selection=fixture.open.selection;
const unavailable={schema:fixture.open.schema,selection,availability:"UNAVAILABLE",state:null,permissions:null,owner_context:null,current_receipt:null,pause_token:null,reason_codes:["SOURCE_UNAVAILABLE"]};
function binding(data:unknown=fixture.open){
 const ref:{current:ProjectAdmissionSnapshot}={current:{selection,data,dataGeneration:"1",generation:"1",canRead:true}};
 const io={pause:vi.fn<ProjectAdmissionTransport["pause"]>(async()=>fixture.pause_result),resume:vi.fn<ProjectAdmissionTransport["resume"]>(async()=>fixture.resume_result),status:vi.fn<ProjectAdmissionTransport["status"]>(async()=>({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"OBSERVED",receipt:fixture.pause_result.receipt,reason_codes:[]}))};
 const store=createIndexedDbPendingPointerStore(new IDBFactory()),controller=new OperationController(createProjectAdmissionCommandPort(()=>ref.current,io),store);
 return {ref,io,store,controller};
}
function props(value= binding(),data:unknown=fixture.open):ProjectAdmissionPanelProps{
 return {selection,canRead:true,sourceGeneration:"1",source:{data,generation:"1",readVersion:1},controller:value.controller,onReadCurrent:vi.fn()};
}
function random(value=0xaa){vi.spyOn(globalThis.crypto,"getRandomValues").mockImplementation(array=>{(array as Uint8Array).fill(value);return array;});}
it("shows only supplied current gate/actions, with the in-flight caveat and no mount effect",()=>{
 const bound=binding(),p=props(bound);render(<ProjectAdmissionPanel {...p}/>);
 expect(screen.getByText("New work is not paused here. Other limits and permissions still apply.")).toBeTruthy();
 expect(screen.getByText("Stops new work for this project. Work already running may continue.")).toBeTruthy();
 expect(screen.getByRole("button",{name:"Pause new work"})).toBeTruthy();expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();
 expect(bound.io.pause).not.toHaveBeenCalled();expect(bound.io.status).not.toHaveBeenCalled();expect(p.onReadCurrent).not.toHaveBeenCalled();
});
it("one explicit Pause uses existing controller and requires a fresh read before another action/current-state claim",async()=>{
 random();const bound=binding(),p=props(bound);render(<ProjectAdmissionPanel {...p}/>);
 fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));
 await screen.findByText(/Request committed/);
 expect(bound.io.pause).toHaveBeenCalledTimes(1);expect(screen.getByText("Check pause status to see the current setting.")).toBeTruthy();
 expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();expect(screen.queryByText("New work paused")).toBeNull();
 expect(p.onReadCurrent).not.toHaveBeenCalled();fireEvent.click(screen.getByRole("button",{name:"Check pause status"}));expect(p.onReadCurrent).toHaveBeenCalledTimes(1);
});
it("UNKNOWN with a failed current read still reaches original status and never duplicates Pause/Resume",async()=>{
 random();const bound=binding();bound.io.pause.mockRejectedValue(new Error("lost after dispatch"));
 const p=props(bound),view=render(<ProjectAdmissionPanel {...p}/>);
 fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));await screen.findByText(/original request outcome is unresolved/);
 bound.ref.current={...bound.ref.current,data:unavailable};
 view.rerender(<ProjectAdmissionPanel {...p} source={{data:unavailable,generation:"1",readVersion:2}}/>);
 const recover=screen.getByRole("button",{name:"Check original project request"}) as HTMLButtonElement;
 expect(recover.disabled).toBe(false);fireEvent.click(recover);await screen.findByText(/Request committed/);
 expect(bound.io.status).toHaveBeenCalledTimes(1);expect(bound.io.status.mock.calls[0]?.[0].command_id).toBe("mmos-project-pause-"+"a".repeat(40));
 expect(bound.io.pause).toHaveBeenCalledTimes(1);expect(bound.io.resume).not.toHaveBeenCalled();
 expect(await bound.store.read(fixture.open.owner_context.principal_scope)).toBeNull();
});
it("auth departure masks current facts and disables original-status observation without clearing its pointer",async()=>{
 random();const bound=binding();bound.io.pause.mockRejectedValue(new Error("lost"));const p=props(bound),view=render(<ProjectAdmissionPanel {...p}/>);
 fireEvent.click(screen.getByRole("button",{name:"Pause new work"}));await screen.findByText(/original request outcome is unresolved/);
 bound.ref.current={...bound.ref.current,canRead:false,generation:"2"};
 view.rerender(<ProjectAdmissionPanel {...p} canRead={false} sourceGeneration="2"/>);
 expect((screen.getByRole("button",{name:"Check original project request"}) as HTMLButtonElement).disabled).toBe(true);
 expect(screen.queryByText(selection.work_ref)).toBeNull();expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();
 expect(bound.io.status).not.toHaveBeenCalled();expect(await bound.store.read(fixture.open.owner_context.principal_scope)).not.toBeNull();
});
it("Resume is explicit and uses the exact current owner pause token",async()=>{
 random(0xbb);const bound=binding(fixture.paused);render(<ProjectAdmissionPanel {...props(bound,fixture.paused)}/>);
 expect(screen.getByText("New work paused")).toBeTruthy();fireEvent.click(screen.getByRole("button",{name:"Resume new work"}));
 await screen.findByText(/Request committed/);expect(bound.io.resume.mock.calls[0]?.[0].pause_token).toEqual(fixture.paused.pause_token);expect(bound.io.pause).not.toHaveBeenCalled();
});
it("an absent action grant or controller explains its actual missing capability",()=>{
 const noResume={...fixture.paused,permissions:{pause:true,resume:false}},bound=binding(noResume),p=props(bound,noResume);
 const view=render(<ProjectAdmissionPanel {...p}/>);expect(screen.queryByRole("button",{name:"Resume new work"})).toBeNull();expect(screen.getByText("This read does not supply current permission for this action.")).toBeTruthy();
 view.rerender(<ProjectAdmissionPanel {...p} controller={undefined}/>);expect(screen.getByText("Project controls are not connected here.")).toBeTruthy();
});
it("selection/generation mismatch withholds previous identity and gate on the same render",()=>{
 const bound=binding(),p=props(bound),view=render(<ProjectAdmissionPanel {...p}/>);
 view.rerender(<ProjectAdmissionPanel {...p} selection={{work_ref:"WS:OTHER"}}/>);
 expect(screen.queryByText(selection.work_ref)).toBeNull();expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();
 view.rerender(<ProjectAdmissionPanel {...p} sourceGeneration="2"/>);expect(screen.queryByRole("button",{name:"Pause new work"})).toBeNull();
});
it("Chinese copy preserves stop-new-work semantics and declares language",()=>{
 render(<ProjectAdmissionPanel {...props()} locale="zh-CN"/>);
 expect(screen.getByText("停止此项目的新工作；已在运行的工作可能继续。")).toBeTruthy();
 expect(screen.getByRole("region").getAttribute("lang")).toBe("zh-CN");
});


it("composes Pause → explicit fresh gate read → Resume → explicit resumed gate read without optimistic state",async()=>{
 random();const bound=binding(),p=props(bound),view=render(<ProjectAdmissionPanel {...p}/>);
 fireEvent.click(screen.getByRole('button',{name:'Pause new work'}));await screen.findByText(/Request committed/);
 expect(screen.queryByText('New work paused')).toBeNull();
 bound.ref.current={...bound.ref.current,data:fixture.paused};
 view.rerender(<ProjectAdmissionPanel {...p} source={{data:fixture.paused,generation:'1',readVersion:2}}/>);
 expect(screen.getByText('New work paused')).toBeTruthy();random(0xbb);
 fireEvent.click(screen.getByRole('button',{name:'Resume new work'}));
 await screen.findByText('Check pause status to see the current setting.');
 bound.ref.current={...bound.ref.current,data:fixture.resumed};
 view.rerender(<ProjectAdmissionPanel {...p} source={{data:fixture.resumed,generation:'1',readVersion:3}}/>);
 expect(screen.getByText('New work is not paused here. Other limits and permissions still apply.')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Pause new work'})).toBeTruthy();expect(bound.io.pause).toHaveBeenCalledTimes(1);expect(bound.io.resume).toHaveBeenCalledTimes(1);expect(bound.io.status).not.toHaveBeenCalled();
});
