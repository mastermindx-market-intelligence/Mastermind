// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory, IDBDatabase, IDBObjectStore } from "fake-indexeddb";
import {
  createIndexedDbPendingPointerStore, PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME,
  PENDING_POINTER_ERRORS as ERR,
} from "./indexeddb-pending-pointer-store";
import { canonicalJson, sha256Hex } from "./operation-key";
import type { OperationPointer } from "./operation-controller";
import { makePlanningIntent, ProjectPlanningCommandPort } from "../planning/project-planning-command-port";

const scope = "c".repeat(64), otherScope = "d".repeat(64);
const legacy: OperationPointer = { operationKey: "mmos-launch-" + "1".repeat(40), kind: "launch", targetKey: "WS:ORIGINAL.WORK-1" };
const requestId = "mmos-project-create-" + "a".repeat(40);
const PLANNING_TARGET_PREFIX = "project-initial-planning.v1:";
// v7 exists only in the mounted controller's kind union; the record stays byte-closed here.
const conversation = { kind: "conversation_create", operationKey: "mmos-conversation-create-" + "e".repeat(40), targetKey: "WS:TEAM.ONE" } as unknown as OperationPointer;
afterEach(() => { vi.restoreAllMocks(); });

/** Exact journey CREATE port derivation: canonical target bytes and the scope-bound key. */
function createTarget(workRef: string | null): string {
  return canonicalJson({ request_id: requestId, work_ref: workRef });
}
function createKey(createScope: string, workRef: string | null): string {
  return "mmos-journey-create-" + sha256Hex(
    canonicalJson({ v: 1, principalScope: createScope, request_id: requestId, work_ref: workRef }),
  ).slice(0, 40);
}
function createPointer(workRef: string | null, createScope: string = scope): OperationPointer {
  return { kind: "project_create", operationKey: createKey(createScope, workRef), targetKey: createTarget(workRef) };
}
/** Exact planning port shape; the key commits the private request, so only the port re-derives it. */
const planningPointer: OperationPointer = {
  kind: "launch",
  operationKey: "mmos-project-planning-" + "b".repeat(40),
  targetKey: PLANNING_TARGET_PREFIX + "WS:PROJECT.ONE-2",
};

function database(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(PENDING_POINTER_DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(PENDING_POINTER_STORE_NAME);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
  });
}
async function raw(factory: IDBFactory, value?: unknown, key: string = scope): Promise<unknown> {
  const db = await database(factory);
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(PENDING_POINTER_STORE_NAME, value === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore(PENDING_POINTER_STORE_NAME);
      let observed: unknown;
      const request = value === undefined ? store.get(key) : store.put(value, key);
      request.onsuccess = () => { observed = request.result; };
      tx.oncomplete = () => resolve(observed);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

describe("v8 journey CREATE durable variant", () => {
  it("retains the current64-character canonical work-key boundary", async () => {
    const store = createIndexedDbPendingPointerStore(new IDBFactory());
    const pointer = createPointer("WS:"+"A".repeat(64));
    expect(await store.reserve(scope,pointer)).toEqual({reserved:true});
    expect(await store.read(scope)).toEqual(pointer);
  });
  it.each([
    {request_id:requestId+"\n",work_ref:null},
    {request_id:requestId,work_ref:"WS:JOURNEY\n"},
    {request_id:requestId,work_ref:"WS:"+"A".repeat(65)},
  ])("parent bounded CREATE parser refuses malformed even with matching key %j", async (target) => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const pointer:OperationPointer = {kind:"project_create",targetKey:canonicalJson(target),
      operationKey:"mmos-journey-create-"+sha256Hex(canonicalJson({v:1,principalScope:scope,...target})).slice(0,40)};
    await expect(store.reserve(scope,pointer)).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await raw(factory)).toBeUndefined();
  });
  it("parent bounded CREATE parser refuses oversized bytes before parsing", async () => {
    const store = createIndexedDbPendingPointerStore(new IDBFactory());
    const target = " ".repeat(257); const original = JSON.parse; let parsed = 0;
    vi.spyOn(JSON,"parse").mockImplementation((...args) => {
      if (args[0] === target) parsed++;
      return original(...args);
    });
    await expect(store.reserve(scope,{...createPointer(null),targetKey:target})).rejects.toThrow(ERR.INVALID_POINTER);
    expect(parsed).toBe(0);
  });
  it("reserves the exact port-issued pointer, reopens it and clears only itself", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.read(scope)).toBeNull();
    expect(await store.reserve(scope, createPointer(null))).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 8, ...createPointer(null) });
    const reopened = createIndexedDbPendingPointerStore(factory);
    expect(await reopened.read(scope)).toEqual(createPointer(null));
    expect(await reopened.reserve(scope, createPointer("WS:JOURNEY-ONE"))).toEqual({ reserved: false, pointer: createPointer(null) });
    expect(await reopened.clearIfEqual(scope, createPointer("WS:JOURNEY-ONE"))).toBe(false);
    expect(await reopened.clearIfEqual(scope, createPointer(null))).toBe(true);
    expect(await reopened.read(scope)).toBeNull();
  });
  it("keeps the bound work-ref variant and the null-work reservation apart", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope, createPointer("WS:JOURNEY-ONE"))).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 8, ...createPointer("WS:JOURNEY-ONE") });
    expect(await store.reserve(scope, createPointer(null))).toEqual({ reserved: false, pointer: createPointer("WS:JOURNEY-ONE") });
    expect(await store.read(scope)).toEqual(createPointer("WS:JOURNEY-ONE"));
  });
  it("refuses a key not derived from the actual scope/request/work bytes", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await expect(store.reserve(scope, createPointer(null, otherScope))).rejects.toThrow(ERR.INVALID_POINTER);
    await expect(store.reserve(scope, { ...createPointer(null), operationKey: "mmos-journey-create-" + "f".repeat(40) })).rejects.toThrow(ERR.INVALID_POINTER);
    await expect(store.reserve(scope, { ...createPointer(null), targetKey: createTarget("WS:JOURNEY-ONE") })).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await raw(factory)).toBeUndefined();
  });
  const badTargets = [
    ["trailing byte", createTarget(null) + " "],
    ["spacing", '{"request_id": "' + requestId + '", "work_ref": null}'],
    ["unsorted keys", '{"work_ref":null,"request_id":"' + requestId + '"}'],
    ["private extra field", canonicalJson({ request_id: requestId, work_ref: null, goal: "draft-goal-text" })],
    ["wrong request prefix", canonicalJson({ request_id: "mmos-journey-create-" + "a".repeat(40), work_ref: null })],
    ["uppercase request hash", canonicalJson({ request_id: "mmos-project-create-" + "A".repeat(40), work_ref: null })],
    ["short request hash", canonicalJson({ request_id: "mmos-project-create-" + "a".repeat(39), work_ref: null })],
    ["lowercase work", canonicalJson({ request_id: requestId, work_ref: "WS:journey-one" })],
    ["dotted work", canonicalJson({ request_id: requestId, work_ref: "WS:JOURNEY.ONE" })],
    ["foreign work prefix", canonicalJson({ request_id: requestId, work_ref: "JOB-1" })],
    ["empty work", canonicalJson({ request_id: requestId, work_ref: "" })],
    ["request final newline", canonicalJson({ request_id: requestId+"\n", work_ref: null })],
    ["work final newline", canonicalJson({ request_id: requestId, work_ref: "WS:JOURNEY\n" })],
    ["overlong work", canonicalJson({ request_id: requestId, work_ref: "WS:"+"A".repeat(65) })],
    ["over-budget JSON", " ".repeat(257)],
  ] as const;
  it.each(badTargets)("refuses a %s CREATE target before any write", async (_name, target) => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await expect(store.reserve(scope, { ...createPointer(null), targetKey: target })).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await raw(factory)).toBeUndefined();
  });
  it("refuses extra pointer fields and incumbent kind/key grammar confusion", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await expect(store.reserve(scope, { ...createPointer(null), payload: {} } as OperationPointer)).rejects.toThrow(ERR.INVALID_POINTER);
    await expect(store.reserve(scope, { ...createPointer(null), kind: "launch" })).rejects.toThrow(ERR.INVALID_POINTER);
    await expect(store.reserve(scope, { kind: "project_create", operationKey: requestId, targetKey: createTarget(null) })).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await raw(factory)).toBeUndefined();
  });
  it.each([
    { v: 4, ...createPointer(null) },
    { v: 9, ...createPointer(null) },
    { v: 8, kind: "project_create", operationKey: requestId, targetKey: createTarget(null) },
    { v: 8, ...createPointer(null), goal: "draft-goal-text" },
  ] as unknown[])("withholds a confused journey record %j without replacing it", async (record) => {
    const factory = new IDBFactory();
    await raw(factory, record);
    const store = createIndexedDbPendingPointerStore(factory);
    await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
    await expect(store.reserve(scope, createPointer(null))).rejects.toThrow(ERR.CORRUPT_RECORD);
    expect(await raw(factory)).toEqual(record);
  });
  it("refuses a stored journey record whose key was derived for a different scope", async () => {
    const factory = new IDBFactory();
    const foreign = { v: 8, ...createPointer(null, otherScope) };
    await raw(factory, foreign, scope);
    const store = createIndexedDbPendingPointerStore(factory);
    await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
    expect(await raw(factory, undefined, scope)).toEqual(foreign);
  });
  it("aborts an uncommitted CREATE reservation without retaining the write", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const abort = new AbortController(), original = IDBObjectStore.prototype.add;
    vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args);
      request.addEventListener("success", () => abort.abort());
      return request;
    });
    await expect(store.reserve(scope, createPointer(null), abort.signal)).rejects.toThrow(ERR.CANCELLED);
    expect(await store.read(scope)).toBeNull();
  });
  it("cannot replace an unresolved legacy pointer and preserves the incumbent v4 grammar", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope, legacy)).toEqual({ reserved: true });
    expect(await store.reserve(scope, createPointer(null))).toEqual({ reserved: false, pointer: legacy });
    expect(await store.clearIfEqual(scope, createPointer(null))).toBe(false);
    await store.clearIfEqual(scope, legacy);
    const incumbent: OperationPointer = { kind: "project_create", operationKey: requestId, targetKey: "WS:CANDIDATE.ONE" };
    expect(await store.reserve(scope, incumbent)).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 4, ...incumbent });
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(incumbent);
    expect(await store.reserve(scope, createPointer(null))).toEqual({ reserved: false, pointer: incumbent });
  });
});

describe("v9 planning launch durable variant", () => {
  it("reserves a real port-issued payload-bound pointer without a transport shim", async () => {
    const owner = { principalScope: scope, generation: "1" };
    const input = { stage:"plan",work_ref:"WS:REAL-PORT",
      project_source:{repository:"macro",commit:"a".repeat(40),path:"agentos/workstreams/WS-REAL-PORT.md",
        content_sha256:"b".repeat(64),request_sha256:"c".repeat(64)},
      publication:{request_id:requestId,principal_scope:otherScope,event_id:1,receipt_sha256:"d".repeat(64)},
      grounding:{mastermind_sha:"e".repeat(40),macro_sha:"a".repeat(40)},private_request:"Original private planning request" };
    const port = new ProjectPlanningCommandPort({request:async()=>{throw new Error("NO_TRANSPORT_ALLOWED");}},()=>owner);
    const intent = makePlanningIntent(owner,input)!;
    const pointer = port.prepare(intent);
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope,pointer)).toEqual({reserved:true});
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(pointer);
    expect(() => port.prepare({...intent,payload:{...(intent.payload as object),operation_key:"mmos-project-planning-"+"f".repeat(40)}})).toThrow("INVALID_PAYLOAD");
    expect(() => port.prepare({...intent,payload:{...(intent.payload as object),private_request:"Substituted input"}})).toThrow("INVALID_PAYLOAD");
    expect(await store.read(scope)).toEqual(pointer);
  });
  it("reserves the exact issued planning pointer, reopens it and clears only itself", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.read(scope)).toBeNull();
    expect(await store.reserve(scope, planningPointer)).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 9, ...planningPointer });
    const reopened = createIndexedDbPendingPointerStore(factory);
    expect(await reopened.read(scope)).toEqual(planningPointer);
    expect(await reopened.reserve(scope, planningPointer)).toEqual({ reserved: false, pointer: planningPointer });
    expect(await reopened.clearIfEqual(scope, planningPointer)).toBe(true);
    expect(await reopened.read(scope)).toBeNull();
  });
  it("accepts the exact grammar boundary and nothing past it", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    const boundary: OperationPointer = { kind: "launch", operationKey: "mmos-project-planning-" + "c".repeat(40), targetKey: PLANNING_TARGET_PREFIX + "WS:" + "A".repeat(128) };
    expect(await store.reserve(scope, boundary)).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 9, ...boundary });
    await expect(store.reserve(scope, { ...boundary, operationKey: "mmos-project-planning-" + "d".repeat(40), targetKey: PLANNING_TARGET_PREFIX + "WS:" + "A".repeat(129) })).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await store.read(scope)).toEqual(boundary);
  });
  it.each([
    ["legacy key keeps the incumbent launch grammar", { ...planningPointer, operationKey: "mmos-launch-" + "b".repeat(40) }],
    ["uppercase key hash", { ...planningPointer, operationKey: "mmos-project-planning-" + "B".repeat(40) }],
    ["short key hash", { ...planningPointer, operationKey: "mmos-project-planning-" + "b".repeat(39) }],
    ["bare work ref without the opaque prefix", { ...planningPointer, targetKey: "WS:PROJECT.ONE-2" }],
    ["wrong opaque prefix", { ...planningPointer, targetKey: "project-initial-planning.v2:WS:PROJECT.ONE-2" }],
    ["lowercase work ref", { ...planningPointer, targetKey: PLANNING_TARGET_PREFIX + "ws:project-one" }],
    ["empty suffix wildcard", { ...planningPointer, targetKey: PLANNING_TARGET_PREFIX }],
    ["trailing byte", { ...planningPointer, targetKey: planningPointer.targetKey + "\n" }],
    ["extra pointer field", { ...planningPointer, payload: {} }],
  ] as [string, OperationPointer][])("refuses %s before any write", async (_name, bad) => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await expect(store.reserve(scope, bad)).rejects.toThrow(ERR.INVALID_POINTER);
    expect(await raw(factory)).toBeUndefined();
  });
  it.each([
    { v: 1, ...planningPointer },
    { v: 8, ...planningPointer },
    { v: 9, operationKey: legacy.operationKey, kind: "launch", targetKey: legacy.targetKey },
  ] as unknown[])("withholds a confused planning record %j without replacing it", async (record) => {
    const factory = new IDBFactory();
    await raw(factory, record);
    const store = createIndexedDbPendingPointerStore(factory);
    await expect(store.read(scope)).rejects.toThrow(ERR.CORRUPT_RECORD);
    await expect(store.reserve(scope, planningPointer)).rejects.toThrow(ERR.CORRUPT_RECORD);
    expect(await raw(factory)).toEqual(record);
  });
  it("cannot replace an unresolved journey CREATE and vice versa", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope, createPointer(null))).toEqual({ reserved: true });
    expect(await store.reserve(scope, planningPointer)).toEqual({ reserved: false, pointer: createPointer(null) });
    expect(await store.clearIfEqual(scope, planningPointer)).toBe(false);
    expect(await store.clearIfEqual(scope, createPointer(null))).toBe(true);
    expect(await store.reserve(scope, planningPointer)).toEqual({ reserved: true });
    expect(await store.reserve(scope, createPointer(null))).toEqual({ reserved: false, pointer: planningPointer });
    expect(await raw(factory)).toEqual({ v: 9, ...planningPointer });
  });
});

describe("incumbent v1-v7 records stay exactly closed", () => {
  it("still reserves and reopens the incumbent v1 launch record", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope, legacy)).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 1, ...legacy });
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(legacy);
    expect(await store.reserve(scope, planningPointer)).toEqual({ reserved: false, pointer: legacy });
  });
  it("still reserves, reopens and clears the incumbent v7 conversation record", async () => {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    expect(await store.reserve(scope, conversation)).toEqual({ reserved: true });
    expect(await raw(factory)).toEqual({ v: 7, ...conversation });
    expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(conversation);
    expect(await store.clearIfEqual(scope, conversation)).toBe(true);
    expect(await store.read(scope)).toBeNull();
  });
});
