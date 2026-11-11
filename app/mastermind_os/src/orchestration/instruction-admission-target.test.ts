// @vitest-environment node
import { describe,it,expect,vi } from "vitest";
import {IDBFactory} from "fake-indexeddb";
import {parseInstructionAdmissionTarget as parse,serializeInstructionAdmissionTarget as serialize} from "./instruction-admission-target";
import {createIndexedDbPendingPointerStore,PENDING_POINTER_DB_NAME,PENDING_POINTER_DB_VERSION,PENDING_POINTER_STORE_NAME,PENDING_POINTER_ERRORS as ERR} from "./indexeddb-pending-pointer-store";
import {OperationController,type OperationPointer,type FiniteCommandPort,type EffectReceipt} from "./operation-controller";
const selection={work_ref:"WS:PROJECT-ONE",instruction_ref:"INS:DAILY-ONE"};
const target=serialize(selection)!;
const original:OperationPointer={kind:"instruction_pause",operationKey:"mmos-instruction-pause-"+"a".repeat(40),targetKey:target};
const scope="b".repeat(64);
async function raw(factory:IDBFactory,value?:unknown):Promise<unknown>{
 const db=await new Promise<IDBDatabase>((resolve,reject)=>{const request=factory.open(PENDING_POINTER_DB_NAME,1);request.onupgradeneeded=()=>request.result.createObjectStore(PENDING_POINTER_STORE_NAME);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
 try{return await new Promise((resolve,reject)=>{const tx=db.transaction(PENDING_POINTER_STORE_NAME,value===undefined?"readonly":"readwrite");const store=tx.objectStore(PENDING_POINTER_STORE_NAME);let observed:unknown;const request=value===undefined?store.get(scope):store.put(value,scope);request.onsuccess=()=>{observed=request.result;};tx.oncomplete=()=>resolve(observed);tx.onabort=()=>reject(tx.error);});}finally{db.close();}
}
describe("stable instruction lookup",()=>{
 it("stores only canonical stable identity and accepts numeric upper-kebab refs",()=>{
  expect(parse(target)).toEqual(selection);expect(serialize({work_ref:"WS:12",instruction_ref:"INS:34"})).not.toBeNull();
  expect(parse(target)?.work_ref).toBe(selection.work_ref);
 });
 it.each([target+"\n",target.replace("PROJECT-ONE","PROJECT--ONE"),target.replace("DAILY-ONE","DAILY-ONE-"),target.replace("WS:PROJECT-ONE","WS:lower"),target.replace('"instruction_ref":"INS:DAILY-ONE","work_ref":"WS:PROJECT-ONE"','"work_ref":"WS:PROJECT-ONE","instruction_ref":"INS:DAILY-ONE"'),"instruction-admission.v1:"+JSON.stringify({...selection,revision:"a".repeat(64)})])("rejects noncanonical or unsupported target bytes: %s",value=>expect(parse(value)).toBeNull());
 it("does not evaluate an instruction getter or permit hidden/foreign fields",()=>{
  const getter=vi.fn(()=>"INS:OTHER");expect(serialize(Object.defineProperty({work_ref:selection.work_ref},"instruction_ref",{enumerable:true,get:getter}) as typeof selection)).toBeNull();expect(getter).not.toHaveBeenCalled();
  expect(serialize(Object.create(selection))).toBeNull();expect(serialize({...selection,source:"private"} as typeof selection)).toBeNull();
 });
 it("reopens a v6 lookup without changing DB1 or overwriting an original command",async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);expect(PENDING_POINTER_DB_VERSION).toBe(1);
  await store.reserve(scope,original);expect(await raw(factory)).toEqual({v:6,...original});
  const reopen=createIndexedDbPendingPointerStore(factory);expect(await reopen.read(scope)).toEqual(original);
  const other={...original,operationKey:"mmos-instruction-pause-"+"c".repeat(40)};
  expect(await reopen.reserve(scope,other)).toEqual({reserved:false,pointer:original});expect(await reopen.clearIfEqual(scope,other)).toBe(false);
  expect(await reopen.clearIfEqual(scope,original)).toBe(true);
 });
 it.each([{...original,operationKey:"mmos-project-pause-"+"a".repeat(40)},{...original,operationKey:original.operationKey+"\n"},{...original,targetKey:"WS:PROJECT-ONE"}])("rejects kind/key/target mismatch before storage",async bad=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);await expect(store.reserve(scope,bad)).rejects.toThrow(ERR.INVALID_POINTER);expect(await raw(factory)).toBeUndefined();
 });
 it("holds unknown versions and preserves all original lookup bytes",async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory),future={v:7,...original};await raw(factory,future);
  await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);await expect(store.reserve(scope,original)).rejects.toThrow(ERR.CORRUPT_RECORD);await expect(store.clearIfEqual(scope,original)).rejects.toThrow(ERR.CORRUPT_RECORD);expect(await raw(factory)).toEqual(future);
 });
 it("retains original instruction unknown across reopen and uses readonly status even on explicit source-reconcile option",async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  const submit=vi.fn(async()=>({...original,disposition:"unknown" as const})),read=vi.fn(async():Promise<EffectReceipt>=>({...original,disposition:"unknown"})),observe=vi.fn(async()=>({...original,disposition:"accepted" as const}));
  const port:FiniteCommandPort={context:()=>({principalScope:scope,generation:"1"}),prepare:()=>original,submit,readOperation:read,reconcileOperation:observe};
  const intent={kind:original.kind,targetKey:target,payload:{source:"not persisted",revision:"not persisted"}};
  expect((await new OperationController(port,store).begin(intent)).status).toBe("unknown");
  const reopened=new OperationController(port,createIndexedDbPendingPointerStore(factory));expect((await reopened.begin(intent)).status).toBe("checking");
  expect((await reopened.recover({reconcileSource:true})).status).toBe("unknown");expect(read).toHaveBeenCalledTimes(1);expect(observe).not.toHaveBeenCalled();expect(submit).toHaveBeenCalledTimes(1);expect(await raw(factory)).toEqual({v:6,...original});
  read.mockResolvedValue({...original,disposition:"accepted"});expect((await reopened.recover()).status).toBe("accepted");expect(await store.read(scope)).toBeNull();expect(submit).toHaveBeenCalledTimes(1);
 });
 it("cannot replace a retained v1 launch with an instruction operation",async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);const old:OperationPointer={kind:"launch",operationKey:"mmos-launch-"+"c".repeat(40),targetKey:"WS:Original.Work-1"};
  await store.reserve(scope,old);expect(await store.reserve(scope,original)).toEqual({reserved:false,pointer:old});expect(await raw(factory)).toEqual({v:1,...old});
 });
});
