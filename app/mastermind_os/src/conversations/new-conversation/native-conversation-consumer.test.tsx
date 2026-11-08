// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {useState} from 'react';
import {IDBFactory} from 'fake-indexeddb';
import fixture from '../../fixtures/native-fresh-action-owner.json';
import historyFixture from '../../fixtures/native-fresh-conversation-owner.json';
import {decodeFreshConversationHistoryCatalogue,decodeFreshConversationHistoryWindow} from '../fresh-conversation-reference';
import {createProjectConversationCatalogueOwner} from '../project-conversation-catalogue-owner';
import {createFreshConversationAttendedBinding,type FreshConversationOriginalRead} from './fresh-conversation-attended-binding';
import {createFreshConversationBinding} from './fresh-conversation-command-binding';
import {NativeConversationActions} from './NativeConversationActions';
import {NativeJourneyContinuation,NativeReferenceContinuation} from './NativeConversationContinuation';
import type {NativeFreshConversationObservation} from './useFreshConversationJourney';
import {decodeNativeFreshResult,type NativeFreshData} from './native-fresh-result';
import type {NativeFreshRequest,NativeFreshOperation} from './native-fresh-request';
import type {NativeConversationObservation} from './native-conversation-controls';
import {freshConversationTarget} from '../../orchestration/fresh-conversation-target';
import {createIndexedDbPendingPointerStore} from '../../orchestration/indexeddb-pending-pointer-store';
const s=fixture.samples,scope='f'.repeat(64),owner={principalScope:scope,generation:'native-actions-ui'},host={};
const selected={work_ref:'WS:ONE',operation_key:'mmos-native-create-'+'a'.repeat(40)};
function data(index:number):NativeFreshData{
 const row=s[index],decoded=decodeNativeFreshResult(row.response,row.operation as NativeFreshOperation,row.arguments);
 if(!decoded?.ok||decoded.data.schema!=='mastermind.executive.fresh_conversation_data.v2')throw Error('actual base missing');
 return decoded.data;
}
function mint(key:string){vi.stubGlobal('crypto',{getRandomValues:(bytes:Uint8Array)=>{
 const hex=key.slice(-40);for(let i=0;i<20;i++)bytes[i]=parseInt(hex.slice(i*2,i*2+2),16);return bytes;}});}
function setup(){
 const store=createIndexedDbPendingPointerStore(new IDBFactory()),initial=data(12);
 const read:FreshConversationOriginalRead={contract:'native-v2',selection:selected,result:initial.result!,
  locator:{...initial.locator!,job_id:initial.locator!.job_id!,attempt_id:initial.locator!.attempt_id!},current:()=>true};
 let resumeApplied=false;
 const nativeTransport={request:vi.fn(async(op:NativeFreshOperation)=>{
  if(op==='resume')resumeApplied=true;
  if(op==='read'&&resumeApplied)throw Error('new writer observation unavailable');
  return op==='read'?{...s[18].response,operation:'read'}:s[({stop:16,stop_status:19,resume_preview:20,resume:21,resume_status:22} as Record<string,number>)[op]].response;
 })};
 const transport={consume:vi.fn(async()=>s[13].response),consumeStatus:vi.fn(),turnPreview:vi.fn(async()=>s[14].response),
  turn:vi.fn(async()=>s[17].response),turnStatus:vi.fn(),turnRead:vi.fn()};
 const options={owner:()=>owner,canModify:()=>true,store,transport,nativeTransport,readInitial:async()=>read};
 const binding=createFreshConversationAttendedBinding(options);
 const create=createFreshConversationBinding({owner:()=>owner,canPreviewCreate:()=>true,newContract:'native-v2',store,nativeTransport,
  transport:{preview:vi.fn(),create:vi.fn(),status:vi.fn(),read:vi.fn()}});
 return {binding,create,store,transport,nativeTransport,read};
}
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});
it('the user can Stop while Send awaits, then preview Resume only after the parent settles',async()=>{
 const e=setup();mint((s[14].arguments as NativeFreshRequest).turn_key!);
 const req=e.binding.makeTurnRequest(e.read,(s[14].arguments as NativeFreshRequest).message!)!;
 const prepared=await e.binding.previewTurn(e.read,req,new AbortController().signal);
 let finish!:(v:unknown)=>void,entered!:()=>void,signal:AbortSignal|undefined;
 const started=new Promise<void>(r=>{entered=r;});
 e.transport.turn=vi.fn((_req:any,seen:AbortSignal)=>{signal=seen;entered();return new Promise(r=>{finish=r;});}) as typeof e.transport.turn;
 const sending=e.binding.controller.begin(e.binding.makeTurnIntent(prepared!)!);await started;
 const settled=vi.fn(),held=vi.fn();
 function Harness(){
  const [observed,setObserved]=useState<NativeConversationObservation>({selection:selected,data:data(15),current:()=>true});
  async function refresh(){const value=await e.binding.native!.readCurrent(selected,new AbortController().signal);
   if(value)setObserved({selection:selected,data:value,current:()=>true});}
  return <NativeConversationActions locale="en" active host={host} authGeneration={0} selection={selected} binding={e.binding}
    observation={observed} refresh={refresh} onControlSettled={settled} onUnresolvedChange={held}/>;
 }
 render(<Harness/>);mint((s[16].arguments as NativeFreshRequest).stop_key!);
 const stop=screen.getByRole('button',{name:'Stop response'});
 expect(stop).toHaveProperty('disabled',true);
 await waitFor(()=>{expect(stop).toHaveProperty('disabled',false);fireEvent.click(stop);});
 await waitFor(()=>expect(settled).toHaveBeenCalledTimes(1));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Review resume'})).toBeTruthy());
 expect((screen.getByRole('button',{name:'Review resume'}) as HTMLButtonElement).disabled).toBe(true);
 expect(signal?.aborted).toBe(false);expect(await e.store.read(scope)).not.toBeNull();
 await act(async()=>{finish(s[17].response);expect((await sending).status).toBe('accepted');});
 fireEvent.click(screen.getByRole('button',{name:'Check conversation status'}));
 await waitFor(()=>expect((screen.getByRole('button',{name:'Review resume'}) as HTMLButtonElement).disabled).toBe(false));
 mint((s[20].arguments as NativeFreshRequest).resume_key!);
 fireEvent.click(screen.getByRole('button',{name:'Review resume'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Resume conversation'})).toBeTruthy());
 fireEvent.click(screen.getByRole('button',{name:'Resume conversation'}));
 await waitFor(()=>expect(settled).toHaveBeenCalledTimes(2));
 await waitFor(()=>expect(screen.getByText('The current conversation could not be checked. Keep the original request and check again.')).toBeTruthy());
 // APPLIED still carries G1; failed current read cannot re-enable another Resume.
 expect(screen.queryByRole('button',{name:'Review resume'})).toBeNull();
 expect(screen.queryByRole('button',{name:'Resume conversation'})).toBeNull();
 expect(e.nativeTransport.request.mock.calls.filter(([op])=>op==='resume')).toHaveLength(1);
 expect(e.transport.turn).toHaveBeenCalledTimes(1);expect(await e.store.read(scope)).toBeNull();
});
it('native progress retains the same initial witness and never invalidates the parent controller',async()=>{
 const e=setup(),reported=vi.fn(),held=vi.fn();
 const original=(index:number):NativeFreshConversationObservation=>({selection:selected,data:data(index),binding:e.create,
  pendingParent:null,creating:false,observing:false,current:()=>true,initialCurrent:()=>true,refresh:async()=>{}});
 const common={locale:'en' as const,active:true,host,authGeneration:0,binding:e.binding,historyOwner:undefined,
  message:'Draft remains original',draftOwner:owner,onMessageChange:vi.fn(),onReadCurrent:reported,onUnresolvedChange:held};
 const mounted=render(<NativeJourneyContinuation {...common} observation={original(12)}/>);
 await waitFor(()=>expect(reported.mock.calls.some(([value])=>value?.contract==='native-v2'&&value.current())).toBe(true));
 const witness=reported.mock.calls.filter(([value])=>value?.contract==='native-v2').at(-1)![0] as FreshConversationOriginalRead;
 const invalidated=vi.spyOn(e.binding.controller,'invalidate');
 mounted.rerender(<NativeJourneyContinuation {...common} observation={original(15)}/>);
 await act(async()=>{});
 expect(witness.current()).toBe(true);
 mounted.rerender(<NativeJourneyContinuation {...common} observation={original(18)}/>);
 await act(async()=>{});
 expect(witness.current()).toBe(true);expect(invalidated).not.toHaveBeenCalled();
 expect(reported.mock.calls.filter(([value])=>value!==null).every(([value])=>value===witness)).toBe(true);
});
it('native intent preparation rejects missing locators and a cross-contract original key before dispatch',()=>{
 const e=setup();mint('a'.repeat(40));
 for(const locator of [{...e.read.locator,job_id:null},{...e.read.locator,attempt_id:''},{...e.read.locator,root_job_id:'bad\nroot'}]){
  const read={...e.read,locator} as FreshConversationOriginalRead;
  expect(e.binding.makeConsumeIntent(read)).toBeNull();expect(e.binding.makeTurnRequest(read,'hello')).toBeNull();
 }
 const cross={...e.read,selection:{...selected,operation_key:'mmos-conversation-create-'+'a'.repeat(40)}};
 expect(e.binding.makeConsumeIntent(cross)).toBeNull();expect(e.binding.makeTurnRequest(cross,'hello')).toBeNull();
 expect(e.transport.consume).not.toHaveBeenCalled();expect(e.transport.turn).not.toHaveBeenCalled();
});

function nativeWindow(){
 const page=decodeFreshConversationHistoryCatalogue(historyFixture.catalogue,historyFixture.catalogue.work_ref);
 const value=decodeFreshConversationHistoryWindow(historyFixture.window,page.entries[0]!.reference);
 if(value.schema!=='mastermind.fresh_conversation_window.v3')throw Error('expected native history');
 return value;
}
async function referenceCase(){
 const e=setup(),window=nativeWindow(),reported=vi.fn(),observed:NativeConversationObservation[]=[];
 vi.spyOn(e.binding.native!,'readCurrent').mockResolvedValue(data(18));
 vi.spyOn(e.binding.native!,'makeResumeRequest').mockImplementation(value=>{observed.push(value);return null;});
 const props={locale:'en' as const,active:true,host,authGeneration:0,binding:e.binding,window,current:()=>true,
  message:'Original reference draft',draftOwner:owner,onMessageChange:vi.fn(),onReadCurrent:reported,onUnresolvedChange:vi.fn()};
 const mounted=render(<NativeReferenceContinuation {...props}/>);
 await waitFor(()=>expect(reported.mock.calls.some(([v])=>v?.contract==='native-v2')).toBe(true));
 async function capture(){
  await waitFor(()=>{const check=screen.getByRole('button',{name:'Check conversation status'});
   expect(check).toHaveProperty('disabled',false);fireEvent.click(check);});
  await waitFor(()=>expect((screen.getByRole('button',{name:'Review resume'}) as HTMLButtonElement).disabled).toBe(false));
  const count=observed.length;fireEvent.click(screen.getByRole('button',{name:'Review resume'}));
  await waitFor(()=>expect(observed).toHaveLength(count+1));
  return observed.at(-1)!;
 }
 return {e,props,mounted,reported,capture};
}
it('replaced reference status withdraws the old control witness while the original answer stays current',async()=>{
 const e=await referenceCase(),initial=e.reported.mock.calls.filter(([v])=>v!==null).at(-1)![0] as FreshConversationOriginalRead;
 const a=await e.capture(),b=await e.capture();
 expect(a).not.toBe(b);expect(a.current()).toBe(false);expect(b.current()).toBe(true);
 expect(initial.current()).toBe(true);
 expect(e.reported.mock.calls.filter(([v])=>v!==null).every(([v])=>v===initial)).toBe(true);
 expect(await e.e.store.read(scope)).toBeNull();expect(e.e.nativeTransport.request).not.toHaveBeenCalled();
});
it.each(['host','authGeneration','binding'] as const)('reference progress withdraws at the %s boundary',async boundary=>{
 const e=await referenceCase(),a=await e.capture();
 const replacement=boundary==='host'?{host:{}}:boundary==='authGeneration'?{authGeneration:1}:{binding:{...e.e.binding}};
 e.mounted.rerender(<NativeReferenceContinuation {...e.props} {...replacement}/>);
 expect(a.current()).toBe(false);expect(await e.e.store.read(scope)).toBeNull();
});
it('a control hold during original history acquisition releases only that read activity',async()=>{
 const e=setup(),reported=vi.fn();let resolve!:()=>void;
 const refreshContext=vi.fn(()=>new Promise<void>(r=>{resolve=r;}));
 const forbidden=vi.fn(async()=>{throw Error('held history must not advance');});
 const historyOwner=createProjectConversationCatalogueOwner({
  transport:{context:()=>({workRef:selected.work_ref,...owner}),authGeneration:()=>0,available:()=>true,
   subscribe:()=>()=>{},refreshContext,catalogue:forbidden,read:forbidden,freshReferences:forbidden,readFreshReference:forbidden},
  workRef:()=>selected.work_ref,selectionGeneration:()=> 'same-native-project'});
 const observation:NativeFreshConversationObservation={selection:selected,data:data(12),binding:e.create,
  pendingParent:null,creating:false,observing:false,current:()=>true,initialCurrent:()=>true,refresh:async()=>{}};
 const props={locale:'en' as const,active:true,host,authGeneration:0,binding:e.binding,historyOwner,
  message:'Same draft',draftOwner:owner,onMessageChange:vi.fn(),onReadCurrent:reported,onUnresolvedChange:vi.fn()};
 const mounted=render(<NativeJourneyContinuation {...props} observation={observation}/>);
 await waitFor(()=>expect((screen.getByRole('button',{name:'Read recorded conversation'}) as HTMLButtonElement).disabled).toBe(false));
 const initial=reported.mock.calls.filter(([v])=>v!==null).at(-1)![0] as FreshConversationOriginalRead;
 fireEvent.click(screen.getByRole('button',{name:'Read recorded conversation'}));
 await waitFor(()=>expect(refreshContext).toHaveBeenCalledTimes(1));
 expect(screen.getByRole('button',{name:'Reading conversation…'})).toBeTruthy();
 mounted.rerender(<NativeJourneyContinuation {...props} observation={{...observation,creating:true}}/>);
 await act(async()=>{resolve();});
 mounted.rerender(<NativeJourneyContinuation {...props} observation={observation}/>);
 await waitFor(()=>expect((screen.getByRole('button',{name:'Read recorded conversation'}) as HTMLButtonElement).disabled).toBe(false));
 expect(screen.queryByRole('button',{name:'Reading conversation…'})).toBeNull();
 expect(forbidden).not.toHaveBeenCalled();expect(initial.current()).toBe(true);
 expect(reported.mock.calls.filter(([v])=>v!==null).every(([v])=>v===initial)).toBe(true);
 historyOwner.dispose();
});
it('native controls reject a legacy creation selector before any status read or preparation',async()=>{
 const e=setup(),selection={...selected,operation_key:'mmos-conversation-create-'+'a'.repeat(40)};
 const idle={selection,data:{...data(18),operation_key:selection.operation_key},current:()=>true};
 const active={selection,data:{...data(15),operation_key:selection.operation_key},current:()=>true};
 expect(e.binding.native!.makeStopIntent(active)).toBeNull();
 expect(e.binding.native!.makeResumeRequest(idle)).toBeNull();
 await expect(e.binding.native!.readCurrent(selection,new AbortController().signal)).rejects.toThrow();
 expect(e.nativeTransport.request).not.toHaveBeenCalled();expect(await e.store.read(scope)).toBeNull();
});

function controls(e:ReturnType<typeof setup>,held:ReturnType<typeof vi.fn>,observation:NativeConversationObservation){
 return {locale:'en' as const,active:true,host,authGeneration:0,selection:selected,binding:e.binding,
  observation,refresh:async()=>{},onUnresolvedChange:held};
}
it('holds a failed local inspection and lets one explicit check qualify the existing empty store',async()=>{
 const e=setup(),held=vi.fn();
 vi.spyOn(e.store,'read').mockRejectedValueOnce(Error('local read unavailable'));
 render(<NativeConversationActions {...controls(e,held,{selection:selected,data:data(18),current:()=>true})}/>);
 expect(screen.getByRole('button',{name:'Review resume'})).toHaveProperty('disabled',true);
 expect(held.mock.calls.at(-1)?.[0]).toBe(true);
 await screen.findByText('The current conversation could not be checked. Keep the original request and check again.');
 const check=screen.getByRole('button',{name:'Check conversation status'});
 expect(check).toHaveProperty('disabled',false);expect(held.mock.calls.at(-1)?.[0]).toBe(true);
 fireEvent.click(check);
 await waitFor(()=>expect(held.mock.calls.at(-1)?.[0]).toBe(false));
 expect(screen.getByRole('button',{name:'Review resume'})).toHaveProperty('disabled',false);
 expect(e.nativeTransport.request).not.toHaveBeenCalled();
 expect(e.transport.turn).not.toHaveBeenCalled();expect(await e.store.read(scope)).toBeNull();
});
it('a pending native Resume remains held after its original deferred inspection',async()=>{
 const e=setup(),held=vi.fn(),pointer={kind:'conversation_resume' as const,
  operationKey:(s[20].arguments as NativeFreshRequest).resume_key!,targetKey:freshConversationTarget(selected)!};
 expect(await e.store.reserve(scope,pointer)).toEqual({reserved:true});
 const sourceRead=e.store.read.bind(e.store);let finish!:(value:typeof pointer|null)=>void;
 vi.spyOn(e.store,'read').mockImplementationOnce(()=>new Promise(r=>{finish=r;}));
 render(<NativeConversationActions {...controls(e,held,{selection:selected,data:data(18),current:()=>true})}/>);
 expect(held.mock.calls.at(-1)?.[0]).toBe(true);
 expect(screen.getByRole('button',{name:'Review resume'})).toHaveProperty('disabled',true);
 await act(async()=>{finish(await sourceRead(scope) as typeof pointer);});
 expect(screen.getByRole('button',{name:'Check original control'})).toHaveProperty('disabled',false);
 expect(held.mock.calls.at(-1)?.[0]).toBe(true);expect(await sourceRead(scope)).toEqual(pointer);
 expect(e.nativeTransport.request).not.toHaveBeenCalled();expect(e.transport.turn).not.toHaveBeenCalled();
});
it('an older failed inspection cannot overwrite a newer qualified control observation',async()=>{
 const e=setup(),held=vi.fn();let reject!:(reason:unknown)=>void;
 vi.spyOn(e.store,'read').mockImplementationOnce(()=>new Promise((_resolve,r)=>{reject=r;}));
 const first=controls(e,held,{selection:selected,data:data(18),current:()=>true});
 const mounted=render(<NativeConversationActions {...first}/>);
 expect(held.mock.calls.at(-1)?.[0]).toBe(true);
 mounted.rerender(<NativeConversationActions {...first} observation={{selection:selected,data:data(18),current:()=>true}}/>);
 await waitFor(()=>expect(held.mock.calls.at(-1)?.[0]).toBe(false));
 await act(async()=>{reject(Error('retired inspection failed'));});
 expect(held.mock.calls.at(-1)?.[0]).toBe(false);
 expect(screen.queryByText('The current conversation could not be checked. Keep the original request and check again.')).toBeNull();
 expect(screen.getByRole('button',{name:'Review resume'})).toHaveProperty('disabled',false);
 expect(e.nativeTransport.request).not.toHaveBeenCalled();expect(await e.store.read(scope)).toBeNull();
});
