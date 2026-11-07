// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import fixture from "./fixtures/project-admission-owner.json";
import { OperationController, type OperationPointer } from "../orchestration/operation-controller";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import { createProjectAdmissionCommandPort, projectAdmissionReceipt, type ProjectAdmissionSnapshot, type ProjectAdmissionTransport } from "./project-admission-command-port";
const selection=fixture.open.selection;
const pause:OperationPointer={kind:"project_pause",targetKey:selection.work_ref,operationKey:"mmos-project-pause-"+"a".repeat(40)};
const resume:OperationPointer={kind:"project_resume",targetKey:selection.work_ref,operationKey:"mmos-project-resume-"+"b".repeat(40)};
function source(data:unknown=fixture.open):ProjectAdmissionSnapshot{return {selection:{...selection},data,dataGeneration:"1",generation:"1",canRead:true};}
function transport(){return {pause:vi.fn<ProjectAdmissionTransport["pause"]>(async()=>fixture.pause_result),resume:vi.fn<ProjectAdmissionTransport["resume"]>(async()=>fixture.resume_result),status:vi.fn<ProjectAdmissionTransport["status"]>(async()=>({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"OBSERVED",receipt:fixture.pause_result.receipt,reason_codes:[]}))};}
afterEach(()=>vi.restoreAllMocks());
describe("project admission finite command owner",()=>{
 it("requires an actual decoded capability, not methods/login alone",()=>{
  let current=source(null);const io=transport(),port=createProjectAdmissionCommandPort(()=>current,io);
  expect(port.context()).toBeNull();expect(()=>port.prepare({kind:"project_pause",targetKey:selection.work_ref,payload:{selection}})).toThrow();
  current=source();current.canRead=false;expect(port.context()).toBeNull();expect(io.pause).not.toHaveBeenCalled();
 });
 it("passes exact current Resume token, and refuses a stale or foreign draft before effect",async()=>{
  const current=source(fixture.paused),io=transport(),port=createProjectAdmissionCommandPort(()=>current,io);
  const intent={kind:"project_resume" as const,targetKey:selection.work_ref,payload:{selection,pause_token:fixture.paused.pause_token}};
  expect(await port.submit(resume,intent,new AbortController().signal)).toEqual({...resume,disposition:"accepted"});
  expect(io.resume.mock.calls[0]?.[0]).toMatchObject({selection,command_id:resume.operationKey,pause_token:fixture.paused.pause_token});
  const result=await port.submit(resume,{...intent,payload:{selection,pause_token:{...fixture.paused.pause_token,event_id:999}}},new AbortController().signal);
  expect(result.disposition).toBe("refused");expect(io.resume).toHaveBeenCalledTimes(1);
 });
 it("keeps original unknown pointer across process reopen and status NOT_OBSERVED; never sends a replacement",async()=>{
  vi.spyOn(globalThis.crypto,"getRandomValues").mockImplementation((array)=>{(array as Uint8Array).fill(0xaa);return array;});
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory),io=transport();
  io.pause.mockRejectedValue(new Error("transport lost"));
  const port=createProjectAdmissionCommandPort(()=>source(),io),controller=new OperationController(port,store);
  const intent={kind:"project_pause" as const,targetKey:selection.work_ref,payload:{selection}};
  expect((await controller.begin(intent)).status).toBe("unknown");
  const scope=fixture.open.owner_context.principal_scope;
  expect(await store.read(scope)).toEqual(pause);
  const reopened=createIndexedDbPendingPointerStore(factory),next=new OperationController(port,reopened);
  await next.begin(intent);expect(io.pause).toHaveBeenCalledTimes(1);
  io.status.mockResolvedValueOnce({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"NOT_OBSERVED",receipt:null,reason_codes:[]});
  expect((await next.recover()).status).toBe("unknown");expect(await reopened.read(scope)).toEqual(pause);
  expect((await next.recover()).status).toBe("accepted");expect(await reopened.read(scope)).toBeNull();
  expect(io.status.mock.calls.every(([request])=>request.command_id===pause.operationKey)).toBe(true);expect(io.pause).toHaveBeenCalledTimes(1);
 });
 it("observes the original key after current-state read becomes unavailable, without another mutation",async()=>{
  vi.spyOn(globalThis.crypto,"getRandomValues").mockImplementation((array)=>{(array as Uint8Array).fill(0xaa);return array;});
  let current=source();const io=transport();io.pause.mockRejectedValue(new Error("lost"));
  const store=createIndexedDbPendingPointerStore(new IDBFactory()),port=createProjectAdmissionCommandPort(()=>current,io),controller=new OperationController(port,store);
  await controller.begin({kind:"project_pause",targetKey:selection.work_ref,payload:{selection}});
  current={...current,data:{schema:fixture.open.schema,selection,availability:"UNAVAILABLE",state:null,permissions:null,owner_context:null,current_receipt:null,pause_token:null,reason_codes:["SOURCE_UNAVAILABLE"]}};
  expect((await controller.recover()).status).toBe("accepted");expect(io.status).toHaveBeenCalledTimes(1);expect(io.pause).toHaveBeenCalledTimes(1);expect(io.resume).not.toHaveBeenCalled();
 });
 it("withholds a late commit across generation ABA or selected-root change",async()=>{
  for(const change of ["generation","selection"]){
   let current=source();let release!:(value:unknown)=>void;
   const io=transport();io.pause.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
   const port=createProjectAdmissionCommandPort(()=>current,io),pending=port.submit(pause,{kind:"project_pause",targetKey:selection.work_ref,payload:{selection}},new AbortController().signal);
   if(change==="generation"){current={...current,generation:"2"};current={...current,generation:"3"};}
   else current={...current,selection:{...selection,root_job_id:"JOB-999"}};
   release(fixture.pause_result);expect((await pending).disposition).toBe("unknown");
  }
 });
 it("decodes full owner receipt and rejects foreign schema/body/getters without touching them",()=>{
  expect(projectAdmissionReceipt(fixture.pause_result,pause,selection).disposition).toBe("accepted");
  for(const value of [{...fixture.pause_result,extra:true},{...fixture.pause_result,receipt:{...fixture.pause_result.receipt,state:"RESUMED"}},{...fixture.resume_result}])expect(projectAdmissionReceipt(value,pause,selection).disposition).toBe("unknown");
  let invoked=false;const dangerous={...fixture.pause_result};Object.defineProperty(dangerous,"receipt",{get(){invoked=true;return fixture.pause_result.receipt;},enumerable:true});
  expect(projectAdmissionReceipt(dangerous,pause,selection).disposition).toBe("unknown");expect(invoked).toBe(false);
 });
 it("never upgrades method/status absence or unknown to a terminal refusal",async()=>{
  const io=transport(),port=createProjectAdmissionCommandPort(()=>source(),io);
  io.status.mockResolvedValueOnce({schema:"mastermind.workspace_project_admission_status_result.v1",selection:fixture.pause_result.selection,state:"NOT_OBSERVED",receipt:null,reason_codes:[]});
  expect((await port.readOperation(pause,new AbortController().signal)).disposition).toBe("unknown");
  expect(io.pause).not.toHaveBeenCalled();expect(io.resume).not.toHaveBeenCalled();
 });
});


it('holds the same pending pointer across auth departure when current gate data is unavailable',async()=>{
 vi.spyOn(globalThis.crypto,'getRandomValues').mockImplementation(array=>{(array as Uint8Array).fill(0xaa);return array;});
 let current=source();const io=transport();io.pause.mockRejectedValue(new Error('lost'));
 const store=createIndexedDbPendingPointerStore(new IDBFactory()),port=createProjectAdmissionCommandPort(()=>current,io),controller=new OperationController(port,store);
 await controller.begin({kind:'project_pause',targetKey:selection.work_ref,payload:{selection}});
 current={...current,generation:'2',dataGeneration:'1'};
 expect((await controller.recover()).status).toBe('idle');expect(io.status).not.toHaveBeenCalled();
 expect(await store.read(fixture.open.owner_context.principal_scope)).toEqual(pause);expect(io.pause).toHaveBeenCalledTimes(1);
});


it.each(['request_digest','command_id'])('rejects final-newline receipt identifier %s',(field)=>{
 const body=structuredClone(fixture.pause_result);const receipt=body.receipt as Record<string,unknown>;receipt[field]=String(receipt[field])+'\n';
 expect(projectAdmissionReceipt(body,pause,selection).disposition).toBe('unknown');
});
