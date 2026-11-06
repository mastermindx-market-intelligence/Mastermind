import { describe, expect, it, vi } from 'vitest';
import { bindMissionHost, createNativeClient } from './host';
const raw = () => ({schema:'mastermind.native_executive_status.v1',generation:7,available:true,configured:true,reason:'AVAILABLE',programs_read:{phase:'HTTP_FAILURE',http_status:503}});
async function fixture() {
 const handlers=new Map<string,(event:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string,args?:unknown):Promise<unknown>=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:true};
  if(command==='executive_auth_status')return args?raw():{generation:7,available:false};
  throw new Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(event,handler)=>{handlers.set(event,handler);return ()=>{};});
 await Promise.resolve();return {client,invoke,handlers};
}
describe('explicit native Executive observation',()=>{
 it('uses only the fixed local command and never changes the authoritative transport or notifies auth',async()=>{
  const {client,invoke}=await fixture();const notify=vi.fn();client.subscribe(notify);
  const host=bindMissionHost(client);invoke.mockClear();
  expect(client.executive!.available()).toBe(false);
  const observed=await host.readNativeExecutiveDiagnostics!({signal:new AbortController().signal});
  expect(observed).toMatchObject({wire:'v1',configured:true,available:true,reason:'AVAILABLE',programsRead:{phase:'HTTP_FAILURE',httpStatus:503}});
  expect(invoke.mock.calls).toEqual([['executive_auth_status',{diagnostics:true}]]);
  expect(client.executive!.available()).toBe(false);expect(notify).not.toHaveBeenCalled();
 });
 it('retains old exact-two-key status compatibility without inventing config or a Programs outcome',async()=>{
  const {client,invoke}=await fixture();invoke.mockResolvedValueOnce({generation:7,available:false});
  const result=await bindMissionHost(client).readNativeExecutiveDiagnostics!({signal:new AbortController().signal});
  expect(result).toEqual({wire:'legacy',generation:7,available:false,configured:null,reason:null,programsRead:null});
 });
 it('refuses malformed metadata rather than echoing raw details',async()=>{
  const {client,invoke}=await fixture();invoke.mockResolvedValueOnce({...raw(),private:'secret-origin-token'});
  await expect(bindMissionHost(client).readNativeExecutiveDiagnostics!({signal:new AbortController().signal})).rejects.toThrow('RESPONSE_INVALID');
 });
 it('refuses late metadata after real native auth withdrawal without replaying the native read',async()=>{
  const {client,invoke,handlers}=await fixture();let resolve!:(v:unknown)=>void;
  invoke.mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));
  const host=bindMissionHost(client);invoke.mockClear();
  const read=host.readNativeExecutiveDiagnostics!({signal:new AbortController().signal});
  const rejected=expect(read).rejects.toThrow('READ_CANCELLED');
  handlers.get('mastermind-auth-state')!({payload:{status:'signed_out',reason:null,acquisition:false,content:false}});
  await rejected;resolve(raw());await Promise.resolve();
  expect(invoke.mock.calls).toEqual([['executive_auth_status',{diagnostics:true}]]);
 });
 it('checks the actual source method before and after the local observation',async()=>{
  const {client}=await fixture();const host=bindMissionHost(client);
  const current=client.readNativeExecutiveDiagnostics!;
  client.readNativeExecutiveDiagnostics=async()=>{client.readNativeExecutiveDiagnostics=current;return raw();};
  await expect(host.readNativeExecutiveDiagnostics!({signal:new AbortController().signal})).rejects.toThrow('READ_CANCELLED');
 });
});
