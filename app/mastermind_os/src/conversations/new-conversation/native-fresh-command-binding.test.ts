// @vitest-environment node
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import actions from '../../fixtures/native-fresh-action-owner.json';
import legacy from './fixtures/fresh-conversation-owner.json';
import {createFreshConversationBinding,type FreshConversationTransport} from './fresh-conversation-command-binding';
import {decodeConversationResult} from './fresh-conversation-contract';
import {createIndexedDbPendingPointerStore} from '../../orchestration/indexeddb-pending-pointer-store';
import type {OperationPointer} from '../../orchestration/operation-controller';
const scope='b'.repeat(64),owner={principalScope:scope,generation:'1'};
const sample=(operation:string)=>actions.samples.find(s=>s.operation===operation)!;
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});
function setup(){
 const store=createIndexedDbPendingPointerStore(new IDBFactory());
 const transport:FreshConversationTransport={
  preview:vi.fn(async()=>sample('preview').response),create:vi.fn(async()=>sample('create').response),
  read:vi.fn(async()=>sample('read').response),status:vi.fn(async()=>sample('status').response),
 };
 vi.stubGlobal('crypto',{getRandomValues:(bytes:Uint8Array)=>{bytes.fill(0xaa);return bytes;}});
 const binding=createFreshConversationBinding({newContract:'native-v2',owner:()=>owner,canPreviewCreate:()=>true,transport,store});
 return {binding,store,transport};
}
it('uses the incumbent controller/store for native preview/create and full actual-owner request decoding',async()=>{
 const e=setup(),input=sample('preview').arguments;
 const request=e.binding.makePreviewRequest(input.work_ref,input.message!);expect(request).toEqual(input);
 const signal=new AbortController().signal;
 const raw=await e.binding.preview(request!,signal);
 const decoded=decodeConversationResult(raw,'preview',request!);expect(decoded?.ok).toBe(true);
 if(!decoded?.ok)throw Error('fixture missing preview');
 const intent=e.binding.makeCreateIntent(request!,decoded.data);expect(intent).not.toBeNull();
 expect((await e.binding.controller.begin(intent!)).status).toBe('accepted');
 expect(e.transport.create).toHaveBeenCalledWith(sample('create').arguments,expect.any(AbortSignal),'native-v2');
 expect(e.transport.preview).toHaveBeenCalledWith(input,signal,'native-v2');
 expect(await e.store.read(scope)).toBeNull();
 const selected={work_ref:input.work_ref,operation_key:input.operation_key};
 expect(await e.binding.readOriginal(selected,signal)).toEqual(sample('read').response);
 expect(e.transport.read).toHaveBeenCalledWith(selected,signal,'native-v2');
});
it('a legacy original pending key retains v1 recovery under a native default',async()=>{
 const e=setup(),selected={work_ref:legacy.request.work_ref,operation_key:legacy.request.operation_key};
 const pointer:OperationPointer={kind:'conversation_create',operationKey:selected.operation_key,targetKey:selected.work_ref};
 await e.store.reserve(scope,pointer);
 // Unit status projection: v1 status carries NONE and omits the read-only result body.
 e.transport.status=vi.fn(async()=>({...legacy.read,operation:'status',data:{...legacy.read.data,result:null}}));
 expect((await e.binding.controller.recover()).status).toBe('accepted');
 expect(e.transport.status).toHaveBeenCalledWith(selected,expect.any(AbortSignal));
 expect(e.transport.create).not.toHaveBeenCalled();expect(e.transport.preview).not.toHaveBeenCalled();
 expect(await e.store.read(scope)).toBeNull();
});
it('native unknown creation remount performs only status against the same durable key',async()=>{
 const e=setup(),req=sample('preview').arguments;
 const request=e.binding.makePreviewRequest(req.work_ref,req.message!)!;
 const result=decodeConversationResult(await e.binding.preview(request,new AbortController().signal),'preview',request)!;
 if(!result.ok)throw Error('preview unavailable');
 e.transport.create=vi.fn(async()=>{throw Error('lost after entry');});
 expect((await e.binding.controller.begin(e.binding.makeCreateIntent(request,result.data)!)).status).toBe('unknown');
 const pointer=await e.store.read(scope);expect(pointer?.operationKey).toBe(req.operation_key);
 const remount=createFreshConversationBinding({newContract:'legacy-v1',owner:()=>owner,canPreviewCreate:()=>false,
  transport:e.transport,store:e.store});
 expect((await remount.controller.recover()).status).toBe('accepted');
 expect(e.transport.status).toHaveBeenCalledWith({work_ref:req.work_ref,operation_key:req.operation_key},expect.any(AbortSignal),'native-v2');
 expect(e.transport.create).toHaveBeenCalledTimes(1);
});
it('ACTIVE and incomplete SETTLED replies keep the creation lookup occupied',async()=>{
 for(const state of ['ACTIVE','SETTLED']){
  const e=setup(),preview=sample('preview'),request=e.binding.makePreviewRequest(preview.arguments.work_ref,preview.arguments.message!)!;
  const decoded=decodeConversationResult(preview.response,'preview',request)!;if(!decoded.ok)throw Error('preview unavailable');
  const active=actions.samples.find(s=>s.operation==='status'&&s.response.data?.state==='ACTIVE')!;
  const raw:any=structuredClone(active.response);raw.operation='create';
  if(state==='SETTLED'){raw.data.state='SETTLED';raw.data.active_turn=null;raw.data.result=null;raw.data.head_result=null;raw.data.can_stop=false;}
  e.transport.create=vi.fn(async()=>raw);
  expect((await e.binding.controller.begin(e.binding.makeCreateIntent(request,decoded.data)!)).status).toBe('unknown');
  expect((await e.store.read(scope))?.operationKey).toBe(request.operation_key);
 }
});
it('cross-contract preview data and malformed native input never create or fall back',()=>{
 const e=setup(),request=e.binding.makePreviewRequest(sample('preview').arguments.work_ref,'x'.repeat(800))!;
 expect(request).not.toBeNull();
 expect(e.binding.makeCreateIntent(request,legacy.preview.data as never)).toBeNull();
 expect(e.binding.makePreviewRequest(request.work_ref,'x'.repeat(131073))).toBeNull();
 expect(e.transport.create).not.toHaveBeenCalled();expect(e.transport.preview).not.toHaveBeenCalled();
});
