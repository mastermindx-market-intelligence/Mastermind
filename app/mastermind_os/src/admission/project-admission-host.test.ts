// @vitest-environment node
import { describe, expect, it, vi } from 'vitest';
import fixture from './fixtures/project-admission-owner.json';
import { bindMissionHost, createNativeClient, type RawClient } from '../host';
import { projectAdmissionPublicRequest, projectAdmissionHostMethods } from './project-admission-host';
const selection=fixture.open.selection;
const command_id='mmos-project-pause-'+'a'.repeat(40);
const request=()=>({selection,signal:new AbortController().signal});
const auth={status:'signed_in' as const,reason:null,acquisition:true,content:false};
describe('fixed admission host boundary',()=>{
 it('requires actual source generation and signed-in acquisition before invoking any method',async()=>{
  const read=vi.fn(async()=>fixture.open);
  const partial={getState:()=>auth,readProjectAdmissionControl:read};
  expect(projectAdmissionHostMethods(partial,()=>0).readProjectAdmissionControl).toBeUndefined();
  const client={...partial,invalidationGeneration:()=>0,getState:()=>({...auth,status:'signed_out' as const})};
  await expect(projectAdmissionHostMethods(client,()=>0).readProjectAdmissionControl!(request())).rejects.toThrow();
  expect(read).not.toHaveBeenCalled();
 });
 it('decodes the full current document and rejects foreign state without an action',async()=>{
  const read=vi.fn(async()=>fixture.open as unknown),client={getState:()=>auth,invalidationGeneration:()=>0,readProjectAdmissionControl:read};
  const host=projectAdmissionHostMethods(client,()=>0);
  await expect(host.readProjectAdmissionControl!(request())).resolves.toEqual(fixture.open);
  read.mockResolvedValueOnce({...fixture.open,extra:true});await expect(host.readProjectAdmissionControl!(request())).rejects.toThrow('RESPONSE_INVALID');
  read.mockResolvedValueOnce({...fixture.open,selection:{...selection,work_ref:'WS:FOREIGN'}});await expect(host.readProjectAdmissionControl!(request())).rejects.toThrow('RESPONSE_INVALID');
 });
 it('withholds late bodies after host epoch, source generation, method replacement or abort',async()=>{
  for(const change of ['epoch','generation','method','abort']){
   let epoch=0,generation=0,finish!:(x:unknown)=>void;
   const client={getState:()=>auth,invalidationGeneration:()=>generation,readProjectAdmissionControl:vi.fn(()=>new Promise<unknown>(r=>{finish=r;}))};
   const signal=new AbortController(),pending=projectAdmissionHostMethods(client,()=>epoch).readProjectAdmissionControl!({selection,signal:signal.signal});
   if(change==='epoch')epoch++;else if(change==='generation')generation++;else if(change==='method')client.readProjectAdmissionControl=vi.fn(async()=>fixture.open);else signal.abort();
   finish(fixture.open);await expect(pending).rejects.toThrow('AUTH_CHANGED');
  }
 });
 it('observes an original status without requiring a fresh gate read',async()=>{
  const status=vi.fn(async()=>fixture.pause_result),client={getState:()=>auth,invalidationGeneration:()=>4,readProjectAdmissionOperation:status};
  await expect(projectAdmissionHostMethods(client,()=>2).readProjectAdmissionOperation!({...request(),kind:'project_pause',command_id})).resolves.toEqual(fixture.pause_result);
  expect(status).toHaveBeenCalledTimes(1);
 });
 it('rejects private fields, foreign command namespaces and noncanonical token before dispatch',()=>{
  expect(projectAdmissionPublicRequest('pause',{...request(),command_id,url:'https://example.invalid'})).toBeNull();
  expect(projectAdmissionPublicRequest('pause',{...request(),command_id:command_id+'\n'})).toBeNull();
  expect(projectAdmissionPublicRequest('status',{...request(),command_id,kind:'project_resume'})).toBeNull();
  expect(projectAdmissionPublicRequest('resume',{...request(),command_id:'mmos-project-resume-'+'b'.repeat(40),pause_token:{event_id:0,receipt_digest:'a'.repeat(64)}})).toBeNull();
 });
 it('uses only literal registered native commands with exact detached request arguments',async()=>{
  const invoke=vi.fn(async(command:string)=>command==='executive_auth_status'?{generation:0,available:false}:command==='auth_status'?auth:command==='read_project_admission_control'?fixture.open:fixture.pause_result);
  const client=await createNativeClient(invoke as never,async()=>()=>{}),host=bindMissionHost(client);
  await host.readProjectAdmissionControl!(request());
  await host.pauseProjectAdmission!({...request(),command_id});
  await host.readProjectAdmissionOperation!({...request(),command_id,kind:'project_pause'});
  expect(invoke.mock.calls.slice(2)).toEqual([
   ['read_project_admission_control',{selection}],['pause_project_admission',{request:{selection,command_id}}],
   ['read_project_admission_operation',{request:{selection,command_id,kind:'project_pause'}}]
  ]);
 });
});
