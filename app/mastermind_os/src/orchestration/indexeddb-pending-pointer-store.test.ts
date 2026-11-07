// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory, IDBDatabase, IDBObjectStore, IDBVersionChangeEvent } from "fake-indexeddb";
import {
  createIndexedDbPendingPointerStore, PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME,
  PENDING_POINTER_OPEN_TIMEOUT_MS, PENDING_POINTER_ERRORS as ERR,
} from "./indexeddb-pending-pointer-store";
import { OperationController, type OperationPointer, type FiniteCommandPort } from "./operation-controller";

const scope = "a".repeat(64), otherScope = "b".repeat(64);
const pointer: OperationPointer = { operationKey: "mmos-launch-" + "1".repeat(40), kind: "launch", targetKey: "WS:Original.Work-1" };
const replacement: OperationPointer = { ...pointer, operationKey: "mmos-launch-" + "2".repeat(40) };
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

function database(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(PENDING_POINTER_DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(PENDING_POINTER_STORE_NAME);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}
async function raw(factory: IDBFactory, value?: unknown): Promise<unknown> {
  const db = await database(factory);
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(PENDING_POINTER_STORE_NAME, value === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore(PENDING_POINTER_STORE_NAME);
      let observed: unknown;
      const request = value === undefined ? store.get(scope) : store.put(value, scope);
      request.onsuccess = () => { observed = request.result; };
      tx.oncomplete = () => resolve(observed);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

describe("durable IndexedDB pointer transactions", () => {
  it("reopens the original pointer and stores only the closed lookup record", async () => {
    const factory = new IDBFactory();
    const first = createIndexedDbPendingPointerStore(factory);
    expect(await first.read(scope)).toBeNull();
    expect(await first.reserve(scope, pointer)).toEqual({ reserved: true });
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(pointer);
    expect(await raw(factory)).toEqual({ v: 1, ...pointer });
    expect(await first.read(otherScope)).toBeNull();
  });
  it("serializes two connections so only one reservation succeeds, even for an equal pointer", async () => {
    const factory = new IDBFactory();
    const one = createIndexedDbPendingPointerStore(factory), two = createIndexedDbPendingPointerStore(factory);
    const results = await Promise.all([one.reserve(scope, pointer), two.reserve(scope, pointer)]);
    expect(results.filter((r) => r.reserved)).toHaveLength(1);
    expect(results.filter((r) => !r.reserved)).toEqual([{ reserved: false, pointer }]);
  });
  it("never overwrites an occupied pointer and stale clears cannot remove a replacement", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.reserve(scope, pointer);
    expect(await store.reserve(scope, replacement)).toEqual({ reserved: false, pointer });
    expect(await store.clearIfEqual(scope, replacement)).toBe(false);
    expect(await store.clearIfEqual(scope, pointer)).toBe(true);
    await store.reserve(scope, replacement);
    expect(await store.clearIfEqual(scope, pointer)).toBe(false);
    expect(await store.read(scope)).toEqual(replacement);
  });
  it.each([null, { v: 2, ...pointer }, { v: 1, ...pointer, token: "not-persisted" }, { v: 1, ...pointer, kind: "message" }])(
    "refuses corrupt records on read/reserve/clear instead of treating them as absent", async (record) => {
      const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
      await raw(factory, record);
      await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
      await expect(store.reserve(scope, pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
      await expect(store.clearIfEqual(scope, pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
      expect(await raw(factory)).toEqual(record);
    });
  it("refuses missing storage, invalid namespaces, nonlaunch and extra input fields", async () => {
    await expect(createIndexedDbPendingPointerStore(undefined).read(scope)).rejects.toThrow(ERR.UNAVAILABLE);
    const store = createIndexedDbPendingPointerStore(new IDBFactory());
    await expect(store.read("unverified-subject")).rejects.toThrow(ERR.INVALID_SCOPE);
    for (const invalid of [{ ...pointer, kind: "stop" }, { ...pointer, payload: {} }, { ...pointer, targetKey: "WS:X" }])
      await expect(store.reserve(scope, invalid as OperationPointer)).rejects.toThrow(ERR.INVALID_POINTER);
  });
  it("does not resolve until the durable transaction completes", async () => {
    const completed: boolean[] = [];
    const original = IDBDatabase.prototype.transaction;
    vi.spyOn(IDBDatabase.prototype, "transaction").mockImplementation(function (this: IDBDatabase, ...args) {
      const tx = original.apply(this, args);
      if (args[1] === "readwrite") tx.addEventListener("complete", () => completed.push(true));
      return tx;
    });
    await createIndexedDbPendingPointerStore(new IDBFactory()).reserve(scope, pointer);
    expect(completed).toEqual([true]);
  });
  it("refuses unsupported strict durability before enqueuing a write", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.read(scope);
    const original = IDBDatabase.prototype.transaction;
    vi.spyOn(IDBDatabase.prototype, "transaction").mockImplementation(function (this: IDBDatabase, ...args) {
      if (args[2]?.durability === "strict") throw new TypeError("unsupported");
      return original.apply(this, args);
    });
    await expect(store.reserve(scope, pointer)).rejects.toThrow(ERR.TX_FAILED);
    expect(await raw(factory)).toBeUndefined();
  });
  it("aborts an uncommitted reservation without retaining the write", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const abort = new AbortController(), original = IDBObjectStore.prototype.add;
    vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args);
      request.addEventListener("success", () => abort.abort());
      return request;
    });
    await expect(store.reserve(scope, pointer, abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(await store.read(scope)).toBeNull();
  });
  it("aborts an uncommitted clear and preserves the original pointer", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.reserve(scope, pointer);
    const abort = new AbortController(), original = IDBObjectStore.prototype.delete;
    vi.spyOn(IDBObjectStore.prototype, "delete").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args);
      request.addEventListener("success", () => abort.abort());
      return request;
    });
    await expect(store.clearIfEqual(scope, pointer, abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(await store.read(scope)).toEqual(pointer);
  });
  it("withholds a transaction interrupted by database version change", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const original = IDBObjectStore.prototype.get;
    vi.spyOn(IDBObjectStore.prototype, "get").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args), db = this.transaction.db;
      request.addEventListener("success", () => db.dispatchEvent(new IDBVersionChangeEvent("versionchange")));
      return request;
    });
    await expect(store.read(scope)).rejects.toThrow(ERR.VERSION_CHANGE);
  });
  it("rejects an already cancelled operation without opening storage", async () => {
    const factory = new IDBFactory(), spy = vi.spyOn(factory, "open"), abort = new AbortController();
    abort.abort();
    await expect(createIndexedDbPendingPointerStore(factory).reserve(scope, pointer, abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(spy).not.toHaveBeenCalled();
  });
  it("rejects a blocked open whose result getter is still unavailable", async () => {
    const request = { get result() { throw new Error("InvalidStateError"); }, onblocked: null as (() => void) | null };
    const factory = { open() { queueMicrotask(() => request.onblocked?.()); return request; } } as unknown as IDBFactory;
    await expect(createIndexedDbPendingPointerStore(factory).read(scope)).rejects.toThrow(ERR.BLOCKED);
  });
  it("rejects an open timeout and closes a late success without starting a transaction", async () => {
    vi.useFakeTimers();
    const db = { close: vi.fn() };
    let ready = false;
    const request = { get result() { if (!ready) throw new Error("InvalidStateError"); return db; },
      onsuccess: null as (() => void) | null };
    const factory = { open: () => request } as unknown as IDBFactory;
    const result = createIndexedDbPendingPointerStore(factory).read(scope).catch((error: Error) => error.message);
    await vi.advanceTimersByTimeAsync(PENDING_POINTER_OPEN_TIMEOUT_MS + 1);
    expect(await result).toBe(ERR.TIMEOUT);
    ready = true; request.onsuccess?.();
    expect(db.close).toHaveBeenCalledTimes(1);
  });
});

describe("project pause closed record compatibility", () => {
  const pause: OperationPointer = {kind:"project_pause",operationKey:"mmos-project-pause-"+"a".repeat(40),targetKey:"WS:ONE"};
  it("reopens a v2 pause lookup without changing v1 launch grammar or database version", async () => {
    const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope,pause)).toEqual({reserved:true});
    expect(await raw(factory)).toEqual({v:2,...pause});
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(pause);
    expect(await store.clearIfEqual(scope,pause)).toBe(true);
    expect(await store.reserve(scope,pointer)).toEqual({reserved:true});
    expect(await raw(factory)).toEqual({v:1,...pointer});
  });
  it("cannot replace an unresolved launch with a new pause or vice versa", async () => {
    const factory=new IDBFactory(),first=createIndexedDbPendingPointerStore(factory),second=createIndexedDbPendingPointerStore(factory);
    expect(await first.reserve(scope,pointer)).toEqual({reserved:true});
    expect(await second.reserve(scope,pause)).toEqual({reserved:false,pointer});
    expect(await raw(factory)).toEqual({v:1,...pointer});
    expect(await second.clearIfEqual(scope,pause)).toBe(false);
    expect(await first.clearIfEqual(scope,pointer)).toBe(true);
    expect(await second.reserve(scope,pause)).toEqual({reserved:true});
    expect(await first.reserve(scope,pointer)).toEqual({reserved:false,pointer:pause});
  });
  it.each([{v:1,...pause},{v:2,...pointer},{v:3,...pause}])("withholds an unsupported version/kind without replacing its stored hint", async record => {
    const factory=new IDBFactory();await raw(factory,record);const store=createIndexedDbPendingPointerStore(factory);
    await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
    await expect(store.reserve(scope,pause)).rejects.toThrow(ERR.CORRUPT_RECORD);
    expect(await raw(factory)).toEqual(record);
  });
  it.each([{...pause,operationKey:pause.operationKey+"\n"},{...pause,targetKey:"WS:ONE\n"},{...pause,targetKey:"JOB-1"},{...pause,operationKey:"mmos-launch-"+"a".repeat(40)}])("rejects malformed pause scope/key before any write", async bad => {
    const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
    await expect(store.reserve(scope,bad)).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await raw(factory)).toBeUndefined();
  });
});


describe("closed Resume and source operation lookup versions", () => {
 const cases = [
  {kind:"project_resume",v:3,prefix:"mmos-project-resume-"},
  {kind:"project_create",v:4,prefix:"mmos-project-create-"},
  {kind:"project_adopt",v:4,prefix:"mmos-project-adopt-"},
  {kind:"direction_accept",v:4,prefix:"mmos-direction-accept-"},
 ] as const;
 it.each(cases)("$kind reopens its exact closed record and retains candidate/work identity only", async item => {
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  const value:OperationPointer={kind:item.kind,operationKey:item.prefix+"c".repeat(40),targetKey:"WS:SOURCE-CANDIDATE"};
  expect(await store.reserve(scope,value)).toEqual({reserved:true});
  expect(await raw(factory)).toEqual({v:item.v,...value});
  expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(value);
  expect(await store.reserve(scope,pointer)).toEqual({reserved:false,pointer:value});
  expect(await store.clearIfEqual(scope,pointer)).toBe(false);
 });
 it.each(cases)("$kind cannot overwrite an unresolved older pointer", async item => {
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  await store.reserve(scope,pointer);
  const value:OperationPointer={kind:item.kind,operationKey:item.prefix+"d".repeat(40),targetKey:"WS:SOURCE-CANDIDATE"};
  expect(await store.reserve(scope,value)).toEqual({reserved:false,pointer});
  expect(await raw(factory)).toEqual({v:1,...pointer});
 });
 it.each(cases)("$kind refuses prefix/version confusion without deleting a retained record", async item => {
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  const value:OperationPointer={kind:item.kind,operationKey:item.prefix+"e".repeat(40),targetKey:"WS:SOURCE-CANDIDATE"};
  const record={v:item.v===4?3:4,...value};await raw(factory,record);
  await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
  await expect(store.reserve(scope,value)).rejects.toThrow(ERR.CORRUPT_RECORD);
  expect(await raw(factory)).toEqual(record);
 });
});

describe('v5 source-write lookup compatibility',()=>{
 const target='project-source-write.v1:'+JSON.stringify({action:'add_project_file',base_revision:'b'.repeat(64),expected_preference_revision:null,request_sha256:'c'.repeat(64),source_commit:'a'.repeat(40),work_ref:'WS:PROJECT-ONE'});
 const write={kind:'project_source_write' as const,operationKey:'mmos-project-file-add-'+'d'.repeat(40),targetKey:target};
 it('reopens exactly the same v5 lookup and compares every original target byte',async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  await store.reserve(scope,write);expect(await raw(factory)).toEqual({v:5,...write});
  const reopened=createIndexedDbPendingPointerStore(factory);expect(await reopened.read(scope)).toEqual(write);
  expect(await reopened.clearIfEqual(scope,{...write,targetKey:target.replace('b'.repeat(64),'f'.repeat(64))})).toBe(false);
  expect(await reopened.clearIfEqual(scope,write)).toBe(true);
 });
 it('rejects action/key mismatch, malformed lookup and other record versions without overwrite',async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
  for(const bad of [{...write,operationKey:'mmos-project-preference-set-'+'d'.repeat(40)},{...write,targetKey:'WS:PROJECT-ONE'},{...write,targetKey:target+'\n'}])await expect(store.reserve(scope,bad)).rejects.toThrow(ERR.INVALID_POINTER);
  const record={v:4,...write};await raw(factory,record);await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
  await expect(store.reserve(scope,pointer)).rejects.toThrow(ERR.CORRUPT_RECORD);expect(await raw(factory)).toEqual(record);
 });
 it('cannot replace any existing original kind and preserves future records',async()=>{
  const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);await store.reserve(scope,pointer);
  expect(await store.reserve(scope,write)).toEqual({reserved:false,pointer});expect(await store.read(scope)).toEqual(pointer);
  await store.clearIfEqual(scope,pointer);const future={v:6,...write};await raw(factory,future);
  await expect(store.clearIfEqual(scope,write)).rejects.toThrow(ERR.CORRUPT_RECORD);expect(await raw(factory)).toEqual(future);
 });
});

it('retains v5 original source-write through unknown and app reopen without another submit',async()=>{
 const target='project-source-write.v1:'+JSON.stringify({action:'set_project_communication_preference',base_revision:'b'.repeat(64),expected_preference_revision:'e'.repeat(64),request_sha256:'c'.repeat(64),source_commit:'a'.repeat(40),work_ref:'WS:PROJECT-ONE'});
 const original={kind:'project_source_write' as const,operationKey:'mmos-project-preference-set-'+'d'.repeat(40),targetKey:target};
 const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);
 const submit=vi.fn(async()=>({...original,disposition:'unknown' as const})),status=vi.fn(async()=>({...original,disposition:'unknown' as const}));
 const port:FiniteCommandPort={context:()=>({principalScope:scope,generation:'1'}),prepare:()=>original,submit,readOperation:status};
 const intent={kind:original.kind,targetKey:target,payload:{notPersisted:'draft'}};
 expect((await new OperationController(port,store).begin(intent)).status).toBe('unknown');
 const reopened=new OperationController(port,createIndexedDbPendingPointerStore(factory));
 expect((await reopened.begin(intent)).status).toBe('checking');
 expect((await reopened.recover()).status).toBe('unknown');expect(submit).toHaveBeenCalledTimes(1);
 expect(status.mock.calls).toHaveLength(1);expect(await store.read(scope)).toEqual(original);
 expect(await raw(factory)).toEqual({v:5,...original});
});

it('keeps the real v5 durable pointer after a refused observational POST and permits later readonly settlement',async()=>{
 const target='project-source-write.v1:'+JSON.stringify({action:'add_project_file',base_revision:'b'.repeat(64),expected_preference_revision:null,request_sha256:'c'.repeat(64),source_commit:'a'.repeat(40),work_ref:'WS:PROJECT-ONE'});
 const original={kind:'project_source_write' as const,operationKey:'mmos-project-file-add-'+'d'.repeat(40),targetKey:target};
 const factory=new IDBFactory(),store=createIndexedDbPendingPointerStore(factory);await store.reserve(scope,original);
 const observer=vi.fn(async()=>({...original,disposition:'refused' as const,reason:'owner preflight refused'}));
 const read=vi.fn(async()=>({...original,disposition:'accepted' as const}));
 const prepare=vi.fn(()=>{throw Error('recovery must never prepare');}),submit=vi.fn(async()=>{throw Error('recovery must never submit');});
 const port:FiniteCommandPort={context:()=>({principalScope:scope,generation:'1'}),prepare,submit,readOperation:read,reconcileOperation:observer};
 expect((await new OperationController(port,store).recover({reconcileSource:true})).status).toBe('unknown');
 expect(await raw(factory)).toEqual({v:5,...original});expect(observer).toHaveBeenCalledTimes(1);expect(read).not.toHaveBeenCalled();
 const reopened=createIndexedDbPendingPointerStore(factory);
 expect((await new OperationController(port,reopened).recover()).status).toBe('accepted');
 expect(await reopened.read(scope)).toBeNull();expect(observer).toHaveBeenCalledTimes(1);expect(read).toHaveBeenCalledTimes(1);
 expect(prepare).not.toHaveBeenCalled();expect(submit).not.toHaveBeenCalled();
});
