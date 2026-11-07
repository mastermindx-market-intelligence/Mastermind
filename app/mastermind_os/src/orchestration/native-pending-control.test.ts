// @vitest-environment node
import {afterEach,describe,expect,it,vi} from 'vitest';
import {IDBFactory,IDBObjectStore} from 'fake-indexeddb';
import {createIndexedDbPendingPointerStore,PENDING_POINTER_DB_NAME,PENDING_POINTER_STORE_NAME} from './indexeddb-pending-pointer-store';
import {OperationController,type OperationPointer,type CommandIntent,type EffectReceipt,type FiniteCommandPort} from './operation-controller';
import {freshConversationTarget} from './fresh-conversation-target';
const scope='a'.repeat(64),work='WS:Original.Project';
const parent:OperationPointer={kind:'conversation_turn',operationKey:'mmos-native-turn-'+'b'.repeat(40),
 targetKey:freshConversationTarget({work_ref:work,operation_key:'mmos-native-create-'+'c'.repeat(40)})};
const control:OperationPointer={kind:'conversation_stop',operationKey:'mmos-native-stop-'+'d'.repeat(40),targetKey:parent.targetKey};
const stopIntent:CommandIntent={kind:'conversation_stop',targetKey:control.targetKey,payload:{private:'never persisted'}};
const intent:CommandIntent={kind:parent.kind,targetKey:parent.targetKey,payload:{}};
const receipt=(p:OperationPointer,disposition:EffectReceipt['disposition']='accepted'):EffectReceipt=>({...p,disposition});
const deferred=<T,>()=>{let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};};
afterEach(()=>vi.restoreAllMocks());
async function raw(factory:IDBFactory,value?:unknown):Promise<unknown>{
 const db=await new Promise<IDBDatabase>((resolve,reject)=>{const r=factory.open(PENDING_POINTER_DB_NAME,1);
  r.onupgradeneeded=()=>r.result.createObjectStore(PENDING_POINTER_STORE_NAME);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
 try{return await new Promise((resolve,reject)=>{const tx=db.transaction(PENDING_POINTER_STORE_NAME,value===undefined?'readonly':'readwrite');
  const r=value===undefined?tx.objectStore(PENDING_POINTER_STORE_NAME).get(scope):tx.objectStore(PENDING_POINTER_STORE_NAME).put(value,scope);
  let result:unknown;r.onsuccess=()=>{result=r.result;};tx.oncomplete=()=>resolve(result);tx.onabort=()=>reject(tx.error);});
 }finally{db.close();}
}
function setup(factory=new IDBFactory()){
 const store=createIndexedDbPendingPointerStore(factory);
 let generation='1',present=true;
 const port:FiniteCommandPort={
  context:()=>present?{principalScope:scope,generation}:null,
  prepare:vi.fn(()=>parent),submit:vi.fn(async p=>receipt(p,'unknown')),readOperation:vi.fn(async p=>receipt(p)),
  prepareControl:vi.fn(()=>control),submitControl:vi.fn(async(_parent,p)=>receipt(p)),
  readControlOperation:vi.fn(async(_parent,p)=>receipt(p)),
 };
 const controller=new OperationController(port,store);
 return {factory,store,port,controller,withdraw:()=>{generation='2';},logout:()=>{present=false;}};
}
describe('one durable parent with a subordinate original Stop lookup',()=>{
 it('stores only closed parent/child selectors and restores the exact parent after clearing Stop',async()=>{
  const e=setup();await e.store.reserve(scope,parent);
  expect(await e.store.attachControlIfEqual!(scope,parent,control)).toBe(true);
  const row=await raw(e.factory);
  expect(row).toEqual({v:21,parent:{v:18,...parent},control:{v:20,...control}});
  expect(await e.store.read(scope)).toEqual(parent);
  expect(await e.store.reserve(scope,parent)).toEqual({reserved:false,pointer:parent});
  expect(await e.store.clearIfEqual(scope,parent)).toBe(false);
  expect(await createIndexedDbPendingPointerStore(e.factory).readControl!(scope,parent)).toEqual({matched:true,control});
  expect(await e.store.clearControlIfEqual!(scope,parent,control)).toBe(true);
  expect(await raw(e.factory)).toEqual({v:18,...parent});
  expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control:null});
  expect(await e.store.clearIfEqual(scope,parent)).toBe(true);
 });
 it('serializes competing connections so an identical child attaches once',async()=>{
  const e=setup(),other=createIndexedDbPendingPointerStore(e.factory);await e.store.reserve(scope,parent);
  const results=await Promise.all([e.store.attachControlIfEqual!(scope,parent,control),other.attachControlIfEqual!(scope,parent,control)]);
  expect(results.sort()).toEqual([false,true]);
  expect(await other.clearIfEqual(scope,parent)).toBe(false);
  expect(await other.clearControlIfEqual!(scope,parent,{...control,operationKey:'mmos-native-stop-'+'e'.repeat(40)})).toBe(false);
  expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control});
 });
 it('handles both parent-clear/child-attach orderings without losing either durable lookup',async()=>{
  const e=setup();await e.store.reserve(scope,parent);expect(await e.store.clearIfEqual(scope,parent)).toBe(true);
  expect(await e.store.attachControlIfEqual!(scope,parent,control)).toBe(false);
  await e.store.reserve(scope,parent);await e.store.attachControlIfEqual!(scope,parent,control);
  expect(await e.store.clearIfEqual(scope,parent)).toBe(false);
  expect(await e.store.readControl!(scope,{...parent,operationKey:'mmos-native-turn-'+'f'.repeat(40)})).toEqual({matched:false});
 });
 it('keeps native and legacy key/record variants disjoint and refuses a foreign Stop target',async()=>{
  const e=setup(),legacyTarget=freshConversationTarget({work_ref:work,operation_key:'mmos-conversation-create-'+'a'.repeat(40)});
  for(const p of [
   {...parent,operationKey:'mmos-conversation-turn-'+'a'.repeat(40)},
   {...parent,targetKey:legacyTarget},
   {...control,targetKey:legacyTarget},
   {...control,kind:'stop'},
  ])await expect(e.store.reserve(scope,p as OperationPointer)).rejects.toThrow();
  await e.store.reserve(scope,parent);
  await expect(e.store.attachControlIfEqual!(scope,parent,{...control,targetKey:freshConversationTarget({work_ref:work,operation_key:'mmos-native-create-'+'f'.repeat(40)})})).rejects.toThrow();
  const create:OperationPointer={kind:'conversation_create',operationKey:'mmos-native-create-'+'c'.repeat(40),targetKey:work};
  const fresh=setup();await fresh.store.reserve(scope,create);
  expect(await fresh.store.attachControlIfEqual!(scope,create,control)).toBe(true);
 });
 it.each(['extra','nested','wrong-version','wrong-parent','wrong-child'])('refuses malformed %s wrapper on every destructive path',async fault=>{
  const e=setup();const row:any={v:21,parent:{v:18,...parent},control:{v:20,...control}};
  if(fault==='extra')row.message='do not persist';
  if(fault==='nested')row.parent={v:21,parent:row.parent,control:row.control};
  if(fault==='wrong-version')row.parent.v=11;
  if(fault==='wrong-parent')row.parent.operationKey='mmos-native-turn-'+'f'.repeat(40),row.parent.targetKey=freshConversationTarget({work_ref:work,operation_key:'mmos-native-create-'+'f'.repeat(40)});
  if(fault==='wrong-child')row.control.kind='conversation_resume',row.control.v=19,row.control.operationKey='mmos-native-resume-'+'d'.repeat(40);
  await raw(e.factory,row);
  await expect(e.store.read(scope)).rejects.toThrow();await expect(e.store.reserve(scope,parent)).rejects.toThrow();
  await expect(e.store.clearIfEqual(scope,parent)).rejects.toThrow();
  await expect(e.store.clearControlIfEqual!(scope,parent,control)).rejects.toThrow();
  expect(await raw(e.factory)).toEqual(row);
 });
 it('aborts an uncommitted attachment without deleting or replacing the parent',async()=>{
  const e=setup();await e.store.reserve(scope,parent);
  const abort=new AbortController(),put=IDBObjectStore.prototype.put;
  vi.spyOn(IDBObjectStore.prototype,'put').mockImplementation(function(this:IDBObjectStore,...args){
   const request=put.apply(this,args);request.addEventListener('success',()=>abort.abort());return request;
  });
  await expect(e.store.attachControlIfEqual!(scope,parent,control,abort.signal)).rejects.toThrow();
  expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control:null});
 });
 it('Stop never aborts/replaces pending Send; parent settlement waits for the child receipt',async()=>{
  const e=setup(),sent=deferred<EffectReceipt>(),stopped=deferred<EffectReceipt>();
  let parentSignal!:AbortSignal;
  e.port.submit=vi.fn(async(_p,_i,signal)=>{parentSignal=signal;return sent.promise;});
  e.port.submitControl=vi.fn(async()=>stopped.promise);
  const sending=e.controller.begin(intent);await vi.waitFor(()=>expect(e.port.submit).toHaveBeenCalledTimes(1));
  const stopping=e.controller.beginControl(parent,stopIntent);await vi.waitFor(()=>expect(e.port.submitControl).toHaveBeenCalledTimes(1));
  expect(parentSignal.aborted).toBe(false);expect(e.controller.getState().status).toBe('submitting');
  sent.resolve(receipt(parent));expect((await sending).status).toBe('unknown');
  expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control});
  stopped.resolve(receipt(control));expect((await stopping).status).toBe('accepted');
  expect(await e.store.read(scope)).toEqual(parent);
  expect((await e.controller.recover()).status).toBe('accepted');expect(await e.store.read(scope)).toBeNull();
  expect(e.port.submit).toHaveBeenCalledTimes(1);expect(e.port.submitControl).toHaveBeenCalledTimes(1);
 });
 it('remount recovers only the original control lookup with no prepare or resend',async()=>{
  const e=setup();await e.controller.begin(intent);
  e.port.submitControl=vi.fn(async()=>{throw Error('lost after original entry');});
  expect((await e.controller.beginControl(parent,stopIntent)).status).toBe('unknown');
  const next=new OperationController(e.port,createIndexedDbPendingPointerStore(e.factory));
  vi.mocked(e.port.prepareControl!).mockClear();vi.mocked(e.port.submitControl!).mockClear();
  expect((await next.recoverControl(parent)).status).toBe('accepted');
  expect(e.port.readControlOperation).toHaveBeenCalledWith(parent,control,expect.any(AbortSignal));
  expect(e.port.prepareControl).not.toHaveBeenCalled();expect(e.port.submitControl).not.toHaveBeenCalled();
  expect(await e.store.read(scope)).toEqual(parent);
 });
 it('parent clear winning before attachment produces zero Stop calls',async()=>{
  const e=setup();await e.store.reserve(scope,parent);const attach=e.store.attachControlIfEqual!;
  e.store.attachControlIfEqual=async(...args)=>{await e.store.clearIfEqual(scope,parent);return attach(...args);};
  expect((await e.controller.beginControl(parent,stopIntent)).status).toBe('refused');
  expect(e.port.submitControl).not.toHaveBeenCalled();expect(await e.store.read(scope)).toBeNull();
 });
 it.each(['attach','dispatch','clear'])('withdrawal during %s suppresses late control publication and preserves committed store truth',async phase=>{
  const e=setup();await e.store.reserve(scope,parent);
  if(phase==='attach'){const method=e.store.attachControlIfEqual!;e.store.attachControlIfEqual=async(...args)=>{const result=await method(...args);e.withdraw();return result;};}
  if(phase==='dispatch')e.port.submitControl=vi.fn(async(_p,p)=>{e.withdraw();return receipt(p);});
  if(phase==='clear'){const method=e.store.clearControlIfEqual!;e.store.clearControlIfEqual=async(...args)=>{const result=await method(...args);e.withdraw();return result;};}
  expect((await e.controller.beginControl(parent,stopIntent)).status).not.toBe('accepted');
  expect(await e.store.read(scope)).toEqual(parent);
  expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control:phase==='clear'?null:control});
  expect(e.port.submitControl).toHaveBeenCalledTimes(phase==='attach'?0:1);
 });
 it.each(['refused','unknown','foreign'])('retains original attachment for %s recovery without treating it as APPLIED',async disposition=>{
  const e=setup();await e.store.reserve(scope,parent);await e.store.attachControlIfEqual!(scope,parent,control);
  e.port.readControlOperation=vi.fn(async()=>disposition==='foreign'?receipt({...control,operationKey:'foreign'}):receipt(control,disposition as 'refused'|'unknown'));
  expect((await e.controller.recoverControl(parent)).status).toBe('unknown');
  expect(await e.store.readControl!(scope,parent)).toEqual({matched:true,control});expect(e.port.submitControl).not.toHaveBeenCalled();
 });
});
