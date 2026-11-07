// @vitest-environment node
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {freshConversationTarget,parseFreshConversationTarget,mintFreshConversationCommandKey} from './fresh-conversation-target';
import {canonicalJson} from './operation-key';
import {OperationController,type OperationPointer,type FiniteCommandPort} from './operation-controller';
import {createIndexedDbPendingPointerStore,PENDING_POINTER_DB_NAME,PENDING_POINTER_STORE_NAME} from './indexeddb-pending-pointer-store';
import fixture from '../conversations/new-conversation/fixtures/fresh-conversation-recovery-owner.json';
const scope='a'.repeat(64),key='mmos-conversation-create-'+'1'.repeat(40);
const original={work_ref:'WS:EXAMPLE',operation_key:key};
const referenced={work_ref:fixture.initial_read.reference.work_ref,reference:fixture.initial_read.reference};
afterEach(()=>vi.unstubAllGlobals());
it('mints only the canonical twenty-byte client key and fails closed without the genuine random boundary',()=>{
  vi.stubGlobal('crypto',undefined);expect(mintFreshConversationCommandKey('conversation_turn')).toBeNull();
  const random=vi.fn((bytes:Uint8Array)=>{bytes.forEach((_,i)=>{bytes[i]=i+21;});return bytes;});
  vi.stubGlobal('crypto',{getRandomValues:random});
  expect(mintFreshConversationCommandKey('conversation_turn')).toBe('mmos-conversation-turn-15161718191a1b1c1d1e1f202122232425262728');
  expect(random).toHaveBeenCalledTimes(1);
  vi.stubGlobal('crypto',{getRandomValues:()=>new Uint8Array(20)});
  expect(mintFreshConversationCommandKey('conversation_consume')).toBeNull();
});
it('retains only canonical original selector DATA and rejects message/digest/grant/mixed authority fields',()=>{
  for(const selector of [original,referenced]){
    const target=freshConversationTarget(selector);expect(target).toBe(canonicalJson(selector));
    expect(parseFreshConversationTarget(target)).toEqual(selector);
    expect(parseFreshConversationTarget(JSON.stringify(selector,null,2))).toBeNull();
    for(const field of ['message','initial_digest','preview_digest','can_send','turn_key'])
      expect(freshConversationTarget({...selector,[field]:'private'})).toBeNull();
  }
  expect(freshConversationTarget({...original,reference:referenced.reference})).toBeNull();
  expect(freshConversationTarget({...original,operation_key:key+'\n'})).toBeNull();
  expect(freshConversationTarget({...original,work_ref:original.work_ref+'\n'})).toBeNull();
  expect(freshConversationTarget({...referenced,work_ref:'WS:OTHER'})).toBeNull();
  const getter=vi.fn(()=>key);expect(freshConversationTarget(Object.defineProperty({work_ref:original.work_ref},'operation_key',{get:getter}))).toBeNull();
  expect(getter).not.toHaveBeenCalled();
  expect(parseFreshConversationTarget('{"operation_key":"bad","operation_key":"'+key+'","work_ref":"WS:EXAMPLE"}')).toBeNull();
});
it.each(['conversation_consume','conversation_turn'] as const)('reopens %s in its own closed version, preserving original pointer CAS and unrelated scopes',async kind=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  for(const selector of [original,referenced]){
    const pointer:OperationPointer={kind,operationKey:`mmos-${kind.replace('_','-')}-`+'2'.repeat(40),targetKey:freshConversationTarget(selector)!};
    expect(await store.reserve(scope,pointer)).toEqual({reserved:true});
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(pointer);
    expect(await store.reserve(scope,{...pointer,operationKey:pointer.operationKey.replace(/2/g,'3')})).toEqual({reserved:false,pointer});
    expect(await store.read('b'.repeat(64))).toBeNull();
    expect(await store.clearIfEqual(scope,{...pointer,targetKey:freshConversationTarget({...original,work_ref:'WS:OTHER'})!})).toBe(false);
    expect(await store.clearIfEqual(scope,pointer)).toBe(true);
  }
});
it.each(['conversation_consume','conversation_turn'] as const)('holds unknown %s through reload and status-only recovery without source reconcile or replay',async kind=>{
  const store=createIndexedDbPendingPointerStore(new IDBFactory());
  const pointer:OperationPointer={kind,operationKey:`mmos-${kind.replace('_','-')}-`+'2'.repeat(40),targetKey:freshConversationTarget(original)!};
  let terminal=false;const submit=vi.fn(async()=>{throw Error('lost reply');}),reconcileOperation=vi.fn(async()=>{throw Error('not source reconciliation');});
  const owner={principalScope:scope,generation:'original-epoch'};
  const port:FiniteCommandPort={context:()=>owner,prepare:()=>pointer,submit,reconcileOperation,
    readOperation:async()=>({...pointer,disposition:terminal?'accepted':'unknown'})};
  const first=new OperationController(port,store);await first.begin({kind,targetKey:pointer.targetKey,payload:{}});
  expect(await store.read(scope)).toEqual(pointer);
  const reopened=new OperationController(port,store);await reopened.recover({reconcileSource:true});
  expect(await store.read(scope)).toEqual(pointer);expect(submit).toHaveBeenCalledTimes(1);expect(reconcileOperation).not.toHaveBeenCalled();
  terminal=true;await reopened.recover();expect(await store.read(scope)).toBeNull();
});
it('refuses key/kind aliasing and version downgrade without adopting a corrupt record',async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  const pointer:OperationPointer={kind:'conversation_turn',operationKey:'mmos-conversation-turn-'+'2'.repeat(40),targetKey:freshConversationTarget(original)!};
  await expect(store.reserve(scope,{...pointer,kind:'conversation_consume'})).rejects.toThrow('PENDING_POINTER_INVALID_POINTER');
  await expect(store.reserve(scope,{...pointer,operationKey:'mmos-conversation-turn-'+'A'.repeat(40)})).rejects.toThrow('PENDING_POINTER_INVALID_POINTER');
  await store.reserve(scope,pointer);
  const db=await new Promise<IDBDatabase>((resolve,reject)=>{const r=factory.open(PENDING_POINTER_DB_NAME,1);r.onsuccess=()=>resolve(r.result as unknown as IDBDatabase);r.onerror=()=>reject(r.error);});
  await new Promise<void>((resolve,reject)=>{const tx=db.transaction(PENDING_POINTER_STORE_NAME,'readwrite');tx.objectStore(PENDING_POINTER_STORE_NAME).put({v:7,...pointer},scope);tx.oncomplete=()=>resolve();tx.onabort=()=>reject(tx.error);});db.close();
  await expect(store.read(scope)).rejects.toThrow('PENDING_POINTER_CORRUPT_RECORD');
});
