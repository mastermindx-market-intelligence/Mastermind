// @vitest-environment node
import {describe,it,expect,vi} from "vitest";
import owner from "./fixtures/instruction-owner.json";
import {bindMissionHost,createNativeClient} from "../host";
import {instructionHostMethods,instructionPublicRequest} from "./instruction-host";
const selection={work_ref:"WS:ONE",instruction_ref:"INS:DAILY-ONE"},command_id=owner.status.selection.command_id;
const request=()=>({selection,signal:new AbortController().signal});
const pause=()=>({...request(),command_id,expected_revision:owner.current.instruction_revision,expected_source:{...owner.current.source,repository:"mastermindx-market-intelligence/macro" as const}});
const auth={status:"signed_in" as const,reason:null,acquisition:true,content:false};
describe("fixed instruction host boundary",()=>{
 it("requires real source generation and current Acquisition identity before any invocation",async()=>{
  const read=vi.fn(async()=>owner.current),partial={getState:()=>auth,readInstructionAdmissionControl:read};
  expect(instructionHostMethods(partial,()=>0).readInstructionAdmissionControl).toBeUndefined();
  const client={...partial,invalidationGeneration:()=>0,getState:()=>({...auth,status:"signed_out" as const})};
  await expect(instructionHostMethods(client,()=>0).readInstructionAdmissionControl!(request())).rejects.toThrow("UNAUTHORIZED");expect(read).not.toHaveBeenCalled();
 });
 it("fully decodes content, current control and original status; method presence grants no pause",async()=>{
  const current=vi.fn(async():Promise<unknown>=>owner.current),status=vi.fn(async():Promise<unknown>=>owner.status);
  const client={getState:()=>auth,invalidationGeneration:()=>0,readProjectInstructions:vi.fn(async()=>owner.project_only_empty),readInstructionAdmissionControl:current,readInstructionAdmissionOperation:status};
  const host=instructionHostMethods(client,()=>0);
  await expect(host.readProjectInstructions!({selection:{work_ref:"WS:ONE"},signal:request().signal})).resolves.toEqual(owner.project_only_empty);
  await expect(host.readInstructionAdmissionControl!(request())).resolves.toEqual(owner.current);
  await expect(host.readInstructionAdmissionOperation!({...request(),command_id})).resolves.toEqual(owner.status);
  current.mockResolvedValueOnce({...owner.current,permission:{pause:true,resume:true}});await expect(host.readInstructionAdmissionControl!(request())).rejects.toThrow("RESPONSE_INVALID");
  status.mockResolvedValueOnce({...owner.status,selection:{...owner.status.selection,instruction_ref:"INS:OTHER"}});await expect(host.readInstructionAdmissionOperation!({...request(),command_id})).rejects.toThrow("RESPONSE_INVALID");
 });
 it.each(["epoch","generation","method","abort"])("withholds a late body after %s departure",async change=>{
  let epoch=0,generation=0,finish!:(value:unknown)=>void;
  const client={getState:()=>auth,invalidationGeneration:()=>generation,readInstructionAdmissionControl:vi.fn(()=>new Promise<unknown>(resolve=>{finish=resolve;}))};
  const abort=new AbortController(),pending=instructionHostMethods(client,()=>epoch).readInstructionAdmissionControl!({selection,signal:abort.signal});
  if(change==="epoch")epoch++;else if(change==="generation")generation++;else if(change==="method")client.readInstructionAdmissionControl=vi.fn(async()=>owner.current);else abort.abort();
  finish(owner.current);await expect(pending).rejects.toThrow("AUTH_CHANGED");
 });
 it("closes request fields, source path and command namespaces without evaluating getters",()=>{
  expect(instructionPublicRequest("pause",{...pause(),url:"https://foreign.example"})).toBeNull();
  expect(instructionPublicRequest("pause",{...pause(),command_id:command_id+"\n"})).toBeNull();
  expect(instructionPublicRequest("pause",{...pause(),expected_source:{...pause().expected_source,path:"/private/input"}})).toBeNull();
  let reads=0;const hostile={...pause()};Object.defineProperty(hostile,"selection",{enumerable:true,get(){reads++;return selection;}});expect(instructionPublicRequest("pause",hostile)).toBeNull();expect(reads).toBe(0);
 });
 it("invokes only the four literal native methods with closed detached arguments",async()=>{
  const invoke=vi.fn(async(command:string)=>command==="executive_auth_status"?{generation:0,available:false}:command==="auth_status"?auth:command==="read_project_instructions"?owner.project_only_empty:command==="read_instruction_admission_control"?owner.current:command==="pause_instruction_admission"?owner.unknown:owner.status);
  const client=await createNativeClient(invoke as never,async()=>()=>{}),host=bindMissionHost(client);
  await host.readProjectInstructions!({selection:{work_ref:"WS:ONE"},signal:request().signal});await host.readInstructionAdmissionControl!(request());
  await host.pauseInstructionAdmission!(pause());await host.readInstructionAdmissionOperation!({...request(),command_id});
  expect(invoke.mock.calls.slice(2)).toEqual([["read_project_instructions",{selection:{work_ref:"WS:ONE"}}],["read_instruction_admission_control",{selection}],["pause_instruction_admission",{request:{selection,command_id,expected_revision:owner.current.instruction_revision,expected_source:owner.current.source}}],["read_instruction_admission_operation",{request:{selection,command_id}}]]);
 });
});
