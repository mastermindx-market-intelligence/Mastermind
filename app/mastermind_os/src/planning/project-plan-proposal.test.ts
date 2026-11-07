import { describe, it, expect, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import currentSupplier from "../fixtures/project-plan-proposal-source-issued-4fa354.json";
import { planProposalOriginalFromRead } from "./project-plan-proposal";
import fixture from "../fixtures/project-journey-source-issued-388205.json";
import {
  decodePlanProposalOriginal,
  planProposalTarget,
  parsePlanProposalTarget,
  serializePlanProposalOriginal,
} from "./project-plan-proposal";
import {
  preparePlanProposal,
  proposalPointer,
  createPlanProposalPort,
  qualifyPlanProposalStatus,
  type PreparedPlanProposal,
} from "./project-plan-proposal-port";
import { createIndexedDbPendingPointerStore, PENDING_POINTER_DB_NAME, PENDING_POINTER_STORE_NAME } from "../orchestration/indexeddb-pending-pointer-store";
import { OperationController } from "../orchestration/operation-controller";
import {
  projectJourneyUrl,
  readProjectJourneyLocation,
  PROJECT_JOURNEY_PLAN_PROPOSAL_KEY,
} from "../projects/project-journey-location";
const sample = (i: number) =>
  fixture.samples[i] as unknown as {
    request: { arguments: unknown };
    response: unknown;
  };
const original = decodePlanProposalOriginal(sample(12).request.arguments);
const preview = sample(12).response;
const pending = sample(14).response,
  accepted = sample(15).response;
const W = fixture.identities.workspace_scope,
  E = fixture.identities.executive_context.principal_scope;
function harness() {
  let generation = "1",
    allowed = true,
    current = true;
  let prepared: PreparedPlanProposal | null = null;
  const owner = {
    context: () => (allowed ? { principalScope: W, generation } : null),
    canInspect: () => allowed,
    canPublish: () => allowed,
  };
  const planning = { request: vi.fn(async () => preview) };
  const source = {
    prepareSourceOperation: vi.fn(),
    submitSourceOperation: vi.fn(async () => pending),
    readSourceOperation: vi.fn(async () => accepted),
    reconcileSourceOperation: vi.fn(async () => accepted),
    advanceSourceOperation: vi.fn(),
  };
  return {
    owner,
    planning,
    source,
    change: () => {
      generation = "2";
    },
    revoke: () => {
      allowed = false;
    },
    withdraw: () => {
      current = false;
    },
    async prepare() {
      return (prepared = await preparePlanProposal(
        {
          original,
          planning,
          owner,
          executiveOwner: () => ({ principalScope: E, generation }),
          isCurrent: () => current,
        },
        new AbortController().signal,
      ));
    },
    port() {
      return createPlanProposalPort({
        workRef: original.work_ref,
        source,
        owner,
        original: () => original,
        prepared: () => prepared,
        isPreparedCurrent: () => current,
      });
    },
  };
}
describe("closed S24 original and actual unchanged supplier operands", () => {
  it("keeps distinct scopes, exact issued original and canonical URL metadata", () => {
    expect(W).not.toBe(E);
    expect(serializePlanProposalOriginal(original)).toBe(
      JSON.stringify(JSON.parse(serializePlanProposalOriginal(original))),
    );
    const selection = {
      createRequestId: fixture.identities.creation_request_id,
      workRef: original.work_ref,
      planningOperationKey: original.operation_key,
      jobId: original.proposal_request.selection.job_id,
    };
    const href = projectJourneyUrl(
      "https://os.example/os/?secret=removed",
      selection,
      null,
      original,
    );
    expect(readProjectJourneyLocation(href).proposalOriginal).toEqual(original);
    expect(href).not.toContain("secret");
    expect(href).not.toContain("Private first request");
    for (const raw of [
      { ...original, body: "private" },
      { ...original, work_ref: "WS:FOREIGN" },
      {
        ...original,
        proposal_request: {
          ...original.proposal_request,
          selection: {
            ...original.proposal_request.selection,
            attempt_id: null,
          },
        },
      },
    ])
      expect(() => decodePlanProposalOriginal(raw)).toThrow();
    const u = new URL(href);
    u.searchParams.append(
      PROJECT_JOURNEY_PLAN_PROPOSAL_KEY,
      serializePlanProposalOriginal(original),
    );
    expect(readProjectJourneyLocation(u).valid).toBe(false);
    expect(() =>
      projectJourneyUrl(
        href,
        { ...selection, jobId: "JOB-foreign" },
        null,
        original,
      ),
    ).toThrow();
  });
  it("qualifies actual preview and only exact PLAN publication receipt", async () => {
    const h = harness(),
      p = await h.prepare();
    expect(p.original).toEqual(original);
    expect(h.planning.request.mock.calls[0]?.[0]).toBe("prepare_proposal");
    expect(qualifyPlanProposalStatus(accepted, original, W).disposition).toBe(
      "accepted",
    );
    for (const mutate of [
      (x: any) => (x.selection.work_ref = "WS:FOREIGN"),
      (x: any) => (x.owner_context.principal_scope = E),
      (x: any) => x.receipt.sources.pop(),
      (x: any) => (x.request_sha256 = "f".repeat(64)),
      (x: any) => (x.receipt.sources[0].commit = "f".repeat(40)),
    ]) {
      const raw = structuredClone(accepted);
      mutate(raw);
      expect(() => qualifyPlanProposalStatus(raw, original, W)).toThrow();
    }
    expect(() => proposalPointer({ ...p })).toThrow();
  });
  it.each(["revoke", "change", "withdraw"] as const)(
    "discards late preview after %s",
    async (kind) => {
      const h = harness();
      h.planning.request.mockImplementation(async () => {
        h[kind]();
        return preview;
      });
      await expect(h.prepare()).rejects.toThrow();
      expect(h.source.submitSourceOperation).not.toHaveBeenCalled();
    },
  );
  it("refuses mismatched preview and foreign prepared intent before source effects", async () => {
    const h = harness();
    const raw: any = structuredClone(preview);
    raw.data.owner_context.principal_scope = E;
    h.planning.request.mockResolvedValue(raw);
    await expect(h.prepare()).rejects.toThrow();
    h.planning.request.mockResolvedValue(preview);
    const p = await h.prepare();
    const pointer = proposalPointer(p);
    expect(() =>
      h
        .port()
        .prepare(
          {
            kind: pointer.kind,
            targetKey: pointer.targetKey,
            payload: {
              action: "publish_project_plan_proposal",
              original: {
                ...original,
                operation_key: "mmos-project-planning-" + "f".repeat(40),
              },
            },
          },
          new AbortController().signal,
        ),
    ).toThrow();
    expect(h.source.submitSourceOperation).not.toHaveBeenCalled();
  });
});
describe("incumbent v15 IDB original-operation recovery", () => {
  it("retains UNKNOWN, reopens only the original read/reconcile, never submits twice", async () => {
    const h = harness(),
      p = await h.prepare(),
      pointer = proposalPointer(p),
      factory = new IDBFactory();
    const store = createIndexedDbPendingPointerStore(factory),
      machine = new OperationController(h.port(), store);
    const intent = {
      kind: pointer.kind,
      targetKey: pointer.targetKey,
      payload: { action: "publish_project_plan_proposal", original },
    };
    expect((await machine.begin(intent)).status).toBe("unknown");
    expect(await store.read(W)).toEqual(pointer);
    const reopened = new OperationController(
      h.port(),
      createIndexedDbPendingPointerStore(factory),
    );
    expect((await reopened.recover({ reconcileSource: true })).status).toBe(
      "accepted",
    );
    expect(h.source.submitSourceOperation).toHaveBeenCalledTimes(1);
    expect(h.source.reconcileSourceOperation).toHaveBeenCalledTimes(1);
    expect(await store.read(W)).toBeNull();
  });
  it("closed metadata contains no witness/body and rejects key/scope/extra substitutions", async () => {
    const h = harness(),
      pointer = proposalPointer(await h.prepare()),
      target = parsePlanProposalTarget(pointer.targetKey)!;
    const store = createIndexedDbPendingPointerStore(new IDBFactory());
    expect(await store.reserve(W, pointer)).toEqual({ reserved: true });
    for (const bad of [
      {
        ...pointer,
        operationKey: "mmos-project-plan-proposal-" + "f".repeat(40),
      },
      {
        ...pointer,
        targetKey: planProposalTarget({ ...target, principal_scope: E }),
      },
      { ...pointer, targetKey: pointer.targetKey + " " },
      { ...pointer, payload: "private" },
    ])
      await expect(
        createIndexedDbPendingPointerStore(new IDBFactory()).reserve(W, bad),
      ).rejects.toThrow();
    expect(
      parsePlanProposalTarget(
        pointer.targetKey.replace('"action":', '"body":"private","action":'),
      ),
    ).toBeNull();
    expect(pointer.targetKey).not.toContain("terminal-input:");
    expect(pointer.targetKey).not.toContain("Private first request");
  });
});

it("actual current supplier initial Plan READ compiles the exact same original request before publication", () => {
  const args = (currentSupplier.samples[14].request as { arguments: any })
    .arguments;
  const material = planProposalOriginalFromRead({
    read: currentSupplier.samples[2].response,
    workRef: args.work_ref,
    planningOperationKey: args.operation_key,
    requestId: args.proposal_request.request_id,
    jobId: args.proposal_request.selection.job_id,
    attemptId: args.proposal_request.selection.attempt_id,
    resultDigest: args.proposal_request.result_digest,
  });
  expect(material).toEqual(args);
});

it.each(["request_id", "expected_commit", "result_digest"] as const)(
  "refuses final-linebreak proposal metadata in %s",
  (key) => {
    const raw = structuredClone(original);
    raw.proposal_request[key] += "\n";
    expect(() => decodePlanProposalOriginal(raw)).toThrow();
  },
);


// Released native13/14 and historical execution12 retain their original lookup.
async function durableRecord(factory: IDBFactory, scope: string, value?: unknown): Promise<unknown> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const open = factory.open(PENDING_POINTER_DB_NAME, 1);
    open.onsuccess = () => resolve(open.result); open.onerror = () => reject(open.error);
  });
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(PENDING_POINTER_STORE_NAME, value === undefined ? "readonly" : "readwrite");
      const records = tx.objectStore(PENDING_POINTER_STORE_NAME);
      const request = value === undefined ? records.get(scope) : records.put(value, scope);
      let result: unknown;
      request.onsuccess = () => { result = request.result; };
      tx.oncomplete = () => resolve(result); tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

it.each([
  { v: 12, kind: "launch" as const, operationKey: "mmos-project-execute-" + "1".repeat(40), targetKey: "WS:ORIGINAL" },
  { v: 13, kind: "conversation_create" as const, operationKey: "mmos-hermes-create-" + "2".repeat(32), targetKey: "hermes-native-local.v1" },
  { v: 14, kind: "conversation_turn" as const, operationKey: "mmos-hermes-send-" + "3".repeat(32), targetKey: "original-session" },
])("retains original v$v bytes and reservation while new PLAN15 reopens separately", async record => {
  const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
  const { v, ...originalPointer } = record;
  const plan = proposalPointer(await harness().prepare());
  await store.reserve(E, originalPointer);
  expect(await durableRecord(factory, E)).toEqual(record);
  await store.reserve(W, plan);
  expect(await durableRecord(factory, W)).toEqual({ v: 15, ...plan });
  const reopened = createIndexedDbPendingPointerStore(factory);
  expect(await reopened.read(E)).toEqual(originalPointer);
  expect(await reopened.read(W)).toEqual(plan);
  await expect(reopened.reserve(E, plan)).rejects.toThrow("PENDING_POINTER_INVALID_POINTER");
  await expect(reopened.clearIfEqual(E, plan)).rejects.toThrow("PENDING_POINTER_INVALID_POINTER");
  expect(await durableRecord(factory, E)).toEqual(record);
  const occupiedFactory = new IDBFactory();
  const occupied = createIndexedDbPendingPointerStore(occupiedFactory);
  await occupied.reserve(W, originalPointer);
  expect(await occupied.reserve(W, plan)).toEqual({ reserved: false, pointer: originalPointer });
  expect(await occupied.clearIfEqual(W, plan)).toBe(false);
  expect(await durableRecord(occupiedFactory, W)).toEqual(record);
});

it.each([12, 13, 14, 16])("refuses PLAN metadata mislabeled v%i without rewriting it", async v => {
  const factory = new IDBFactory(), store = createIndexedDbPendingPointerStore(factory);
  const plan = proposalPointer(await harness().prepare());
  await store.reserve(W, plan);
  const malformed = { v, ...plan };
  await durableRecord(factory, W, malformed);
  await expect(store.read(W)).rejects.toThrow("PENDING_POINTER_CORRUPT_RECORD");
  await expect(store.reserve(W, plan)).rejects.toThrow("PENDING_POINTER_CORRUPT_RECORD");
  await expect(store.clearIfEqual(W, plan)).rejects.toThrow("PENDING_POINTER_CORRUPT_RECORD");
  expect(await durableRecord(factory, W)).toEqual(malformed);
});
