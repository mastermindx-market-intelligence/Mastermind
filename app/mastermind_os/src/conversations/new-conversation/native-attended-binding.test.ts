// @vitest-environment node
/** Actual native owner envelopes; synthetic frontend identities and deferred transport only. */
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import fixture from '../../fixtures/native-fresh-action-owner.json';
import {createFreshConversationAttendedBinding,type FreshConversationOriginalRead,type FreshConversationAttendedTransport} from './fresh-conversation-attended-binding';
import {createFreshConversationBinding} from './fresh-conversation-command-binding';
import {createIndexedDbPendingPointerStore} from '../../orchestration/indexeddb-pending-pointer-store';
import {decodeNativeFreshResult,type NativeFreshData} from './native-fresh-result';
import type {NativeConversationObservation,NativeControlTransport} from './native-conversation-controls';
import type {NativeFreshOperation,NativeFreshRequest} from './native-fresh-request';
import type {OwnerContext,OperationPointer} from '../../orchestration/operation-controller';
import {freshConversationTarget} from '../../orchestration/fresh-conversation-target';
const samples=fixture.samples;
const item=(index:number)=>samples[index];
const scope='c'.repeat(64),selection={work_ref:'WS:ONE',operation_key:'mmos-native-create-'+'a'.repeat(40)};
function mint(key:string){vi.stubGlobal('crypto',{getRandomValues:(bytes:Uint8Array)=>{
 const hex=key.slice(-40);for(let i=0;i<20;i++)bytes[i]=parseInt(hex.slice(i*2,i*2+2),16);return bytes;
}});}
function data(index:number):NativeFreshData{
 const sample=item(index),value=decodeNativeFreshResult(sample.response,sample.operation as NativeFreshOperation,sample.arguments);
 if(!value?.ok||value.data.schema!=='mastermind.executive.fresh_conversation_data.v2')throw Error('actual base fixture unavailable');
 return value.data;
}
function observation(index:number):NativeConversationObservation{return {selection,data:data(index),current:()=>true};}
function initial(index=12):FreshConversationOriginalRead{
 const value=data(index);if(!value.result||!value.locator?.job_id||!value.locator.attempt_id)throw Error('missing actual seal');
 return {contract:'native-v2',selection,result:value.result,locator:{...value.locator,job_id:value.locator.job_id,attempt_id:value.locator.attempt_id},current:()=>true};
}
function setup(index=12){
 let owner:OwnerContext|null={principalScope:scope,generation:'synthetic-native-ui-owner'};
 let canModify=true;const store=createIndexedDbPendingPointerStore(new IDBFactory()),read=initial(index);
 const choose=(op:string)=>item(index===2?({consume:3,consume_status:8,turn_preview:4,turn:5,turn_status:6,turn_read:7} as Record<string,number>)[op]:
  ({consume:13,consume_status:8,turn_preview:14,turn:17,turn_status:6,turn_read:7} as Record<string,number>)[op]).response;
 const transport:FreshConversationAttendedTransport={consume:vi.fn(async()=>choose('consume')),consumeStatus:vi.fn(async()=>choose('consume_status')),
  turnPreview:vi.fn(async()=>choose('turn_preview')),turn:vi.fn(async()=>choose('turn')),turnStatus:vi.fn(async()=>choose('turn_status')),turnRead:vi.fn(async()=>choose('turn_read'))};
 const nativeTransport:NativeControlTransport={request:vi.fn(async(op)=>item(({read:18,stop:16,stop_status:19,resume_preview:20,resume:21,resume_status:22} as Record<string,number>)[op]).response)};
 const readInitial=vi.fn(async()=>read),options={owner:()=>owner,canModify:()=>canModify,store,transport,nativeTransport,readInitial};
 const binding=createFreshConversationAttendedBinding(options);
 return {binding,store,read,transport,nativeTransport,options,readInitial,withdraw:()=>{owner=null;},unavailable:()=>{canModify=false;}};
}
async function prepared(e:ReturnType<typeof setup>,index=14){
 const args=item(index).arguments as unknown as NativeFreshRequest;mint(args.turn_key!);
 const request=e.binding.makeTurnRequest(e.read,args.message!);expect(request).toEqual(args);
 return (await e.binding.previewTurn(e.read,request!,new AbortController().signal))!;
}
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});
it('consumes the original native seal through the incumbent controller and explicit transport contract',async()=>{
 const e=setup(2);mint('d'.repeat(40));
 const intent=e.binding.makeConsumeIntent(e.read);expect(intent).not.toBeNull();
 expect((await e.binding.controller.begin(intent!)).status).toBe('accepted');
 expect(e.transport.consume).toHaveBeenCalledWith(item(3).arguments,expect.any(AbortSignal),'native-v2');
 expect(await e.store.read(scope)).toBeNull();
});
it('keeps the one native turn key across actual unknown submit, remount status and original read',async()=>{
 const e=setup(2),preview=await prepared(e,4);expect(preview).not.toBeNull();
 const intent=e.binding.makeTurnIntent(preview)!;
 expect((await e.binding.controller.begin(intent)).status).toBe('unknown');
 expect(e.transport.turn).toHaveBeenCalledWith(item(5).arguments,expect.any(AbortSignal),'native-v2');
 const pending=await e.store.read(scope),remount=createFreshConversationAttendedBinding(e.options);
 expect((await remount.controller.recover()).status).toBe('accepted');
 expect(e.transport.turnStatus).toHaveBeenCalledWith(item(6).arguments,expect.any(AbortSignal),'native-v2');
 expect(await remount.readOriginalTurn(selection,pending!.operationKey,new AbortController().signal)).toEqual(item(7).response);
 expect(e.transport.turn).toHaveBeenCalledTimes(1);expect(await e.store.read(scope)).toBeNull();
});
it('attaches Stop to the same running turn without aborting or clearing its parent',async()=>{
 const e=setup(),preview=await prepared(e);let finish!:(v:unknown)=>void,entered!:()=>void;
 const began=new Promise<void>(r=>{entered=r;});let parentSignal:AbortSignal|undefined;
 e.transport.turn=vi.fn((_request,signal)=>{parentSignal=signal;entered();return new Promise(r=>{finish=r;});});
 const sending=e.binding.controller.begin(e.binding.makeTurnIntent(preview)!);await began;
 const parent=(await e.store.read(scope))!;
 mint((item(16).arguments as NativeFreshRequest).stop_key!);
 const intent=e.binding.native!.makeStopIntent(observation(15))!;expect(intent).not.toBeNull();
 expect((await e.binding.controller.beginControl(parent,intent)).status).toBe('accepted');
 expect(e.nativeTransport.request).toHaveBeenCalledWith('stop',item(16).arguments,expect.any(AbortSignal));
 expect(parentSignal?.aborted).toBe(false);expect(await e.store.read(scope)).toEqual(parent);
 expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control:null});
 finish(item(17).response);expect((await sending).status).toBe('accepted');
 expect(await e.store.read(scope)).toBeNull();expect(e.transport.turn).toHaveBeenCalledTimes(1);
});
it('lost Stop response retains the child and remount recovers only the original Stop',async()=>{
 const e=setup();const parent:OperationPointer={kind:'conversation_turn',operationKey:(item(14).arguments as NativeFreshRequest).turn_key!,targetKey:freshConversationTarget(selection)};
 await e.store.reserve(scope,parent);
 mint((item(16).arguments as NativeFreshRequest).stop_key!);
 e.nativeTransport.request=vi.fn(async(op)=>{if(op==='stop')throw Error('lost response after entry');return item(19).response;});
 const intent=e.binding.native!.makeStopIntent(observation(15))!;
 expect((await e.binding.controller.beginControl(parent,intent)).status).toBe('unknown');
 const child=await e.store.readControl!(scope,parent);expect(child.matched&&child.control).not.toBeNull();
 expect(await e.store.clearIfEqual(scope,parent)).toBe(false);
 const remount=createFreshConversationAttendedBinding(e.options);
 expect((await remount.controller.recoverControl(parent)).status).toBe('accepted');
 expect(e.nativeTransport.request).toHaveBeenCalledTimes(2);
 expect(e.nativeTransport.request).toHaveBeenLastCalledWith('stop_status',item(19).arguments,expect.any(AbortSignal));
 expect(await e.store.read(scope)).toEqual(parent);
});
it('previews and resumes the original Session using head digest and the exact closed wire',async()=>{
 const e=setup();mint((item(20).arguments as NativeFreshRequest).resume_key!);
 const witness=observation(18),args=e.binding.native!.makeResumeRequest(witness);expect(args).toEqual(item(20).arguments);
 expect(args).not.toHaveProperty('binding_digest');
 const preview=await e.binding.native!.previewResume(witness,args!,new AbortController().signal);expect(preview).not.toBeNull();
 const intent=e.binding.native!.makeResumeIntent(preview!);expect(intent).not.toBeNull();
 expect((await e.binding.controller.begin(intent!)).status).toBe('accepted');
 expect(e.nativeTransport.request).toHaveBeenLastCalledWith('resume',item(21).arguments,expect.any(AbortSignal));
 expect(await e.store.read(scope)).toBeNull();
 // APPLIED control reply is not a replacement initial seal/current G2 writer.
 expect(e.read.result.digest).toBe(data(12).result!.digest);
 expect(args!.expected_result_digest).toBe(data(18).head_result!.digest);
});
it('two controllers competing for one subordinate Stop dispatch exactly once',async()=>{
 const e=setup(),other=createFreshConversationAttendedBinding(e.options);
 const parent:OperationPointer={kind:'conversation_create',operationKey:selection.operation_key,targetKey:selection.work_ref};
 await e.store.reserve(scope,parent);mint((item(16).arguments as NativeFreshRequest).stop_key!);
 let finish!:(v:unknown)=>void;e.nativeTransport.request=vi.fn(()=>new Promise(r=>{finish=r;}));
 const intent=e.binding.native!.makeStopIntent(observation(15))!;
 const a=e.binding.controller.beginControl(parent,intent),b=other.controller.beginControl(parent,intent);
 await vi.waitFor(()=>expect(e.nativeTransport.request).toHaveBeenCalledTimes(1));
 finish(item(16).response);const results=await Promise.all([a,b]);
 expect(results.filter(x=>x.status==='accepted')).toHaveLength(1);
 expect(await e.store.read(scope)).toEqual(parent);
});
it('creation controller shares the exact subordinate Stop port without another controller',async()=>{
 const e=setup(),create=createFreshConversationBinding({newContract:'native-v2',owner:e.options.owner,canPreviewCreate:()=>true,
  store:e.store,nativeTransport:e.nativeTransport,transport:{preview:vi.fn(),create:vi.fn(),read:vi.fn(),status:vi.fn()}});
 const parent:OperationPointer={kind:'conversation_create',operationKey:selection.operation_key,targetKey:selection.work_ref};
 await e.store.reserve(scope,parent);mint((item(16).arguments as NativeFreshRequest).stop_key!);
 expect((await create.controller.beginControl(parent,create.native!.makeStopIntent(observation(15))!)).status).toBe('accepted');
 expect(await e.store.read(scope)).toEqual(parent);
});
it('malformed APPLIED and owner withdrawal retain the original control lookup',async()=>{
 for(const withdraw of [false,true]){
  const e=setup();mint((item(16).arguments as NativeFreshRequest).stop_key!);
  e.nativeTransport.request=vi.fn(async()=>{if(withdraw)e.withdraw();
   const raw:any=structuredClone(item(16).response);if(!withdraw)raw.data.receipt.event_id=0;return raw;});
  const state=await e.binding.controller.begin(e.binding.native!.makeStopIntent(observation(15))!);
  expect(state.status).not.toBe('accepted');expect(await e.store.read(scope)).not.toBeNull();
 }
});
it('native consume recovery explicitly reuses the native initial reader and does not repeat Keep',async()=>{
 const e=setup(2),key='mmos-native-consume-'+'b'.repeat(40);
 await e.store.reserve(scope,{kind:'conversation_consume',operationKey:key,targetKey:freshConversationTarget(selection)});
 e.unavailable();expect((await e.binding.controller.recover()).status).toBe('accepted');
 expect(e.readInitial).toHaveBeenCalledWith(selection,expect.any(AbortSignal),'native-v2');
 expect(e.transport.consume).not.toHaveBeenCalled();expect(e.transport.consumeStatus).toHaveBeenCalledTimes(1);
});

it('explicit native recovery joins the original turn pointer without another send',async()=>{
 const e=setup(2),preview=await prepared(e,4);
 expect((await e.binding.controller.begin(e.binding.makeTurnIntent(preview)!)).status).toBe('unknown');
 const pending=(await e.store.read(scope))!;
 e.nativeTransport.request=vi.fn(async(op)=>{
  expect(op).toBe('turn_recover');return {...structuredClone(item(7).response),operation:op};
 });
 e.unavailable();
 const remount=createFreshConversationAttendedBinding(e.options);
 expect((await remount.controller.recover({reconcileNative:true})).status).toBe('accepted');
 expect(e.nativeTransport.request).toHaveBeenCalledWith('turn_recover',
  {...selection,turn_key:pending.operationKey},expect.any(AbortSignal));
 expect(e.transport.turnStatus).not.toHaveBeenCalled();
 expect(e.transport.turn).toHaveBeenCalledTimes(1);expect(await e.store.read(scope)).toBeNull();
});
it('unresolved native acknowledgement and refusal retain the exact original pointer',async()=>{
 for(const refused of [false,true]){
  const e=setup(2),preview=await prepared(e,4);
  await e.binding.controller.begin(e.binding.makeTurnIntent(preview)!);
  const pending=(await e.store.read(scope))!;
  e.nativeTransport.request=vi.fn(async(op)=>{
   if(refused)return {schema:'mastermind.executive.fresh_conversation_result.v2',operation:op,ok:false,data:null,
    error:{code:'access_denied',message:'Original request remains unresolved.'}};
   const raw:any=structuredClone(item(7).response);raw.operation=op;raw.data.state='RECONCILIATION_REQUIRED';raw.data.result=null;
   return raw;
  });
  expect((await e.binding.controller.recover({reconcileNative:true})).status).toBe('unknown');
  expect(await e.store.read(scope)).toEqual(pending);expect(e.transport.turn).toHaveBeenCalledTimes(1);
 }
});
it('a changed owner or native transport withholds the late recovery receipt',async()=>{
 for(const change of ['owner','transport']){
  const e=setup(2),preview=await prepared(e,4);
  await e.binding.controller.begin(e.binding.makeTurnIntent(preview)!);
  const pending=(await e.store.read(scope))!;
  e.nativeTransport.request=vi.fn(async(op)=>{
   if(change==='owner')e.withdraw();
   else e.options.nativeTransport={request:vi.fn()};
   return {...structuredClone(item(7).response),operation:op};
  });
  expect((await e.binding.controller.recover({reconcileNative:true})).status).not.toBe('accepted');
  expect(await e.store.read(scope)).toEqual(pending);expect(e.transport.turn).toHaveBeenCalledTimes(1);
 }
});
it('original create recovery uses its existing pointer despite new-create unavailability',async()=>{
 const e=setup(),parent:OperationPointer={kind:'conversation_create',operationKey:selection.operation_key,targetKey:selection.work_ref};
 await e.store.reserve(scope,parent);
 e.nativeTransport.request=vi.fn(async(op)=>({...structuredClone(item(2).response),operation:op}));
 const transport={preview:vi.fn(),create:vi.fn(),read:vi.fn(),status:vi.fn()};
 const create=createFreshConversationBinding({newContract:'native-v2',owner:e.options.owner,canPreviewCreate:()=>false,
  store:e.store,nativeTransport:e.nativeTransport,transport});
 expect((await create.controller.recover({reconcileNative:true})).status).toBe('accepted');
 expect(e.nativeTransport.request).toHaveBeenCalledWith('recover',selection,expect.any(AbortSignal));
 expect(transport.create).not.toHaveBeenCalled();expect(await e.store.read(scope)).toBeNull();
});
it('recovered answer cannot clear an unresolved subordinate Stop',async()=>{
 const e=setup(),parent:OperationPointer={kind:'conversation_turn',
  operationKey:(item(14).arguments as NativeFreshRequest).turn_key!,targetKey:freshConversationTarget(selection)};
 await e.store.reserve(scope,parent);mint((item(16).arguments as NativeFreshRequest).stop_key!);
 e.nativeTransport.request=vi.fn(async(op)=>{
  if(op==='stop')throw Error('original Stop return lost');
  return {...structuredClone(item(17).response),operation:op};
 });
 expect((await e.binding.controller.beginControl(parent,e.binding.native!.makeStopIntent(observation(15))!)).status).toBe('unknown');
 const child=await e.store.readControl!(scope,parent);
 expect(child.matched&&child.control).not.toBeNull();
 expect((await e.binding.controller.recover({reconcileNative:true})).status).not.toBe('accepted');
 expect(await e.store.read(scope)).toEqual(parent);expect(await e.store.readControl!(scope,parent)).toEqual(child);
 expect(e.transport.turn).not.toHaveBeenCalled();
});

it('an explicit recovery gesture cannot recover a replacement pending pointer',async()=>{
 for(const field of ['operationKey','kind','targetKey'] as const){
  const e=setup(2),preview=await prepared(e,4);
  await e.binding.controller.begin(e.binding.makeTurnIntent(preview)!);
  const original=(await e.store.read(scope))!;
  const replacement:OperationPointer={...original,
   ...(field==='operationKey'?{operationKey:'mmos-native-turn-'+'f'.repeat(40)}:
      field==='kind'?{kind:'conversation_create',operationKey:'mmos-native-create-'+'f'.repeat(40),targetKey:selection.work_ref}:
      {targetKey:freshConversationTarget({...selection,work_ref:'WS:OTHER'})})};
  expect(await e.store.clearIfEqual(scope,original)).toBe(true);
  expect(await e.store.reserve(scope,replacement)).toEqual({reserved:true});
  const result=await e.binding.controller.recover({reconcileNative:true,expectedPointer:original});
  expect(result.status).toBe('unknown');expect(result.pointer).toEqual(replacement);
  expect(await e.store.read(scope)).toEqual(replacement);
  expect(e.nativeTransport.request).not.toHaveBeenCalled();
  expect(e.transport.turnStatus).not.toHaveBeenCalled();
  expect(e.transport.turn).toHaveBeenCalledTimes(1);
 }
});
