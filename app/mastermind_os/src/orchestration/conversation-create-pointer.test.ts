// @vitest-environment node
import { expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { OperationController, type FiniteCommandPort, type OperationPointer } from "./operation-controller";
import { createIndexedDbPendingPointerStore, CONVERSATION_CREATE_KEY_PREFIX,
  PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME } from "./indexeddb-pending-pointer-store";
const scope = "a".repeat(64);
const pointer: OperationPointer = {kind:"conversation_create",
  operationKey:CONVERSATION_CREATE_KEY_PREFIX+"1".repeat(40),targetKey:"WS:Original.Project"};
async function raw(factory: IDBFactory, value?: unknown) {
  const db = await new Promise<IDBDatabase>((resolve,reject) => {
    const request=factory.open(PENDING_POINTER_DB_NAME,1);
    request.onupgradeneeded=()=>request.result.createObjectStore(PENDING_POINTER_STORE_NAME);
    request.onsuccess=()=>resolve(request.result as unknown as IDBDatabase);
    request.onerror=()=>reject(request.error);
  });
  try { return await new Promise<unknown>((resolve,reject)=>{
    const tx=db.transaction(PENDING_POINTER_STORE_NAME,value===undefined?"readonly":"readwrite");
    const store=tx.objectStore(PENDING_POINTER_STORE_NAME);
    const request=value===undefined?store.get(scope):store.put(value,scope);let observed:unknown;
    request.onsuccess=()=>{observed=request.result;};tx.oncomplete=()=>resolve(observed);tx.onabort=()=>reject(tx.error);
  }); } finally { db.close(); }
}
it("reopens only the closed v7 original lookup in the incumbent store and preserves CAS",async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  expect(await store.reserve(scope,pointer)).toEqual({reserved:true});
  expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(pointer);
  expect(await raw(factory)).toEqual({v:7,...pointer});
  expect(await store.read("b".repeat(64))).toBeNull();
  expect(await store.reserve(scope,{...pointer,operationKey:CONVERSATION_CREATE_KEY_PREFIX+"2".repeat(40)})).toEqual({reserved:false,pointer});
  expect(await store.clearIfEqual(scope,{...pointer,targetKey:"WS:Other"})).toBe(false);
  expect(await store.read(scope)).toEqual(pointer);
});
it.each([
  {...pointer,operationKey:"fresh-original-one"},
  {...pointer,operationKey:pointer.operationKey+"\n"},
  {...pointer,operationKey:CONVERSATION_CREATE_KEY_PREFIX+"A".repeat(40)},
  {...pointer,operationKey:"mmos-launch-"+"1".repeat(40)},
  {...pointer,targetKey:"WS:"},
  {...pointer,targetKey:"WS:Original\n"},
  {...pointer,targetKey:"WS:Original/JOB-1"},
  {...pointer,payload:{message:"inert private first message"}},
  {...pointer,kind:"launch"},
])("refuses mismatched fresh lookup metadata without reserving or widening older kinds",async invalid=>{
  const store=createIndexedDbPendingPointerStore(new IDBFactory());
  await expect(store.reserve(scope,invalid as OperationPointer)).rejects.toThrow("PENDING_POINTER_INVALID_POINTER");
  expect(await store.read(scope)).toBeNull();
});
it("keeps a lost create outcome and original status key, with no source reconciliation or second submit",async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  let terminal=false;
  const port:FiniteCommandPort={context:()=>({principalScope:scope,generation:"executive-owner-1"}),
    prepare:vi.fn(()=>pointer),submit:vi.fn(async()=>{throw Error("inert lost reply");}),
    readOperation:vi.fn(async()=>({...pointer,disposition:terminal?"accepted" as const:"unknown" as const})),
    reconcileOperation:vi.fn(async()=>{throw Error("not a source reconciliation kind");})};
  const first=new OperationController(port,store);
  await first.begin({kind:"conversation_create",payload:{message:"only ephemeral"},targetKey:pointer.targetKey});
  expect(await store.read(scope)).toEqual(pointer);
  const reopened=new OperationController(port,createIndexedDbPendingPointerStore(factory));
  await reopened.recover({reconcileSource:true});
  expect(port.prepare).toHaveBeenCalledTimes(1);expect(port.submit).toHaveBeenCalledTimes(1);
  expect(port.readOperation).toHaveBeenCalledWith(pointer,expect.any(AbortSignal));
  expect(port.reconcileOperation).not.toHaveBeenCalled();expect(await store.read(scope)).toEqual(pointer);
  terminal=true;await reopened.recover();expect(await store.read(scope)).toBeNull();
});
it("does not let the new record version adopt a legacy kind",async()=>{
  const factory=new IDBFactory();await raw(factory,{v:7,...pointer,kind:"launch",operationKey:"mmos-launch-"+"1".repeat(40)});
  const store=createIndexedDbPendingPointerStore(factory);
  await expect(store.read(scope)).rejects.toThrow("PENDING_POINTER_CORRUPT_RECORD");
  await expect(store.reserve(scope,pointer)).rejects.toThrow("PENDING_POINTER_CORRUPT_RECORD");
});
