// @vitest-environment node
import { expect, it } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { createIndexedDbPendingPointerStore, PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME, PENDING_POINTER_ERRORS } from "./indexeddb-pending-pointer-store";
import { nativePendingPointer } from "../hermes-native/pending-pointer";
import { planProposalTarget } from "../planning/project-plan-proposal";
import type { OperationPointer } from "./operation-controller";

const scope = "a".repeat(64);
const original = nativePendingPointer({ kind: "send", requestId: "b".repeat(32), sessionId: "original-session" });
const stopped = nativePendingPointer({ kind: "send", requestId: "b".repeat(32), sessionId: "original-session", stopReserved: true });
function plan(principal = scope): OperationPointer {
  const operationKey = "mmos-project-plan-proposal-" + "c".repeat(40);
  return { kind: "project_source_write", operationKey, targetKey: planProposalTarget({
    schema: "mastermind.project_plan_publication_lookup.v1", action: "publish_project_plan_proposal",
    request_id: operationKey, work_ref: "WS:ONE", principal_scope: principal,
    request_sha256: "d".repeat(64), recipe_fingerprint_sha256: "e".repeat(64),
  }) };
}
async function record(factory: IDBFactory, value?: unknown): Promise<unknown> {
  const db = await new Promise<any>((resolve, reject) => {
    const request = factory.open(PENDING_POINTER_DB_NAME, 1);
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
  });
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(PENDING_POINTER_STORE_NAME, value === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore(PENDING_POINTER_STORE_NAME);
      const request = value === undefined ? store.get(scope) : store.put(value, scope);
      let result: unknown;
      request.onsuccess = () => { result = request.result; };
      tx.oncomplete = () => resolve(result); tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}
it("reopens both published v15 formats while Stop reserves only its original native send", async () => {
  const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
  await store.reserve(scope, original);
  expect(await store.reserveNativeStop!(scope, original)).toBe(true);
  expect(await record(factory)).toEqual({ v: 15, ...stopped });
  expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(stopped);
  expect(await store.clearIfEqual(scope, original)).toBe(false);
  expect(await store.clearIfEqual(scope, stopped)).toBe(true);
  const proposal = plan();
  expect(await store.reserve(scope, proposal)).toEqual({ reserved: true });
  expect(await record(factory)).toEqual({ v: 15, ...proposal });
  expect(await createIndexedDbPendingPointerStore(factory).read(scope)).toEqual(proposal);
  await expect(store.reserveNativeStop!(scope, proposal)).rejects.toThrow(PENDING_POINTER_ERRORS.INVALID_POINTER);
  expect(await store.read(scope)).toEqual(proposal);
});
it("refuses cross-kind and foreign-scope records without clearing or reinterpreting them", async () => {
  for (const pointer of [stopped, plan()]) {
    const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
    await store.reserve(scope, pointer);
    const crossed = { v: 15, ...pointer, kind: pointer.kind === "conversation_turn" ? "project_source_write" : "conversation_turn" };
    await record(factory, crossed);
    await expect(store.read(scope)).rejects.toThrow(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
    expect(await record(factory)).toEqual(crossed);
  }
  await expect(createIndexedDbPendingPointerStore(new IDBFactory()).reserve(scope, plan("f".repeat(64))))
    .rejects.toThrow(PENDING_POINTER_ERRORS.INVALID_POINTER);
});
