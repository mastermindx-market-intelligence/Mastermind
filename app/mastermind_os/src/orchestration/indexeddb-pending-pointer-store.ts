import { parseProjectSourceWriteTarget, projectSourceWriteKeyMatches } from "./project-source-write-target";
import { parseInstructionAdmissionTarget } from "./instruction-admission-target";
import type { OperationPointer } from "./operation-controller";
import { readNativePending } from "../hermes-native/pending-pointer";
import { parseDirectConsumeTarget } from "../direct-native-result";
import { canonicalJson, sha256Hex } from "./operation-key";
import {parseFreshConversationTarget} from './fresh-conversation-target';
import {parsePlanProposalTarget} from '../planning/project-plan-proposal';

export interface DurablePendingPointerStore {
  read(scope: string, signal?: AbortSignal): Promise<OperationPointer | null>;
  reserve(
    scope: string,
    pointer: OperationPointer,
    signal?: AbortSignal,
  ): Promise<
    { readonly reserved: true } | { readonly reserved: false; readonly pointer: OperationPointer }
  >;
  clearIfEqual(scope: string, pointer: OperationPointer, signal?: AbortSignal): Promise<boolean>;
}

export const PENDING_POINTER_DB_NAME = "mastermind-os-pending-v1";
export const PENDING_POINTER_DB_VERSION = 1;
export const PENDING_POINTER_STORE_NAME = "pointers";
export const PENDING_POINTER_OPEN_TIMEOUT_MS = 8000;
export const PENDING_POINTER_TX_TIMEOUT_MS = 8000;

export const PENDING_POINTER_ERRORS = {
  UNAVAILABLE: "PENDING_POINTER_STORE_UNAVAILABLE",
  INVALID_SCOPE: "PENDING_POINTER_INVALID_SCOPE",
  INVALID_POINTER: "PENDING_POINTER_INVALID_POINTER",
  CORRUPT_RECORD: "PENDING_POINTER_CORRUPT_RECORD",
  OPEN_FAILED: "PENDING_POINTER_OPEN_FAILED",
  BLOCKED: "PENDING_POINTER_STORE_BLOCKED",
  VERSION_CHANGE: "PENDING_POINTER_VERSION_CHANGE",
  TX_FAILED: "PENDING_POINTER_TRANSACTION_FAILED",
  TIMEOUT: "PENDING_POINTER_TIMEOUT",
  CANCELLED: "PENDING_POINTER_CANCELLED",
} as const;

type SourceOperationKind = "project_create" | "project_adopt" | "direction_accept";
type StoredKind = "launch" | "consume" | "project_pause" | "project_resume" | SourceOperationKind | "project_source_write" | "instruction_pause" | "conversation_create" | "conversation_consume" | "conversation_turn";
type ClosedRecord = {
  readonly v: 1; readonly operationKey: string; readonly kind: "launch" | "consume"; readonly targetKey: string;
} | {
  readonly v: 2; readonly operationKey: string; readonly kind: "project_pause"; readonly targetKey: string;
} | {
  readonly v: 3; readonly operationKey: string; readonly kind: "project_resume"; readonly targetKey: string;
} | {
  /** Source operations retain only a candidate/work lookup, never payload or authority. */
  readonly v: 4; readonly operationKey: string; readonly kind: SourceOperationKind; readonly targetKey: string;
} | {
  readonly v: 5; readonly operationKey: string; readonly kind: "project_source_write"; readonly targetKey: string;
} | {
  readonly v: 6; readonly operationKey: string; readonly kind: "instruction_pause"; readonly targetKey: string;
} | {
  /** Fresh-conversation original lookup only; no message, preview or authority. */
  readonly v: 7; readonly operationKey: string; readonly kind: "conversation_create"; readonly targetKey: string;
} | {
  /** Journey CREATE retains only the original request/work lookup, never a goal or payload. */
  readonly v: 8; readonly operationKey: string; readonly kind: "project_create"; readonly targetKey: string;
} | {
  /** Planning launch retains only the opaque status lookup; its key binding stays port-owned. */
  readonly v: 9; readonly operationKey: string; readonly kind: "launch"; readonly targetKey: string;
} | {
  readonly v: 10; readonly operationKey: string; readonly kind: "conversation_consume"; readonly targetKey: string;
} | {
  readonly v: 11; readonly operationKey: string; readonly kind: "conversation_turn"; readonly targetKey: string;
} | {
  /** Project execution keeps only the original opaque operation lookup. */
  readonly v: 12; readonly operationKey: string; readonly kind: "launch"; readonly targetKey: string;
} | {
  /** Same local native request only; no prompt, ticket or execution state. */
  readonly v: 13; readonly operationKey: string; readonly kind: "conversation_create"; readonly targetKey: string;
} | {
  readonly v: 14; readonly operationKey: string; readonly kind: "conversation_turn"; readonly targetKey: string;
} | {
  /** Original PLAN publication lookup only; no private body or preview witness. */
  readonly v: 15; readonly operationKey: string; readonly kind: "project_source_write"; readonly targetKey: string;
};

type DurableReservation =
  | { readonly reserved: true }
  | { readonly reserved: false; readonly pointer: OperationPointer };


const SCOPE_RE = /^[0-9a-f]{64}$/;
const LAUNCH_KEY_RE = /^mmos-launch-[0-9a-f]{40}$/;
const CONSUME_KEY_RE = /^mmos-consume-[0-9a-f]{40}$/;
export const PROJECT_PAUSE_KEY_PREFIX = "mmos-project-pause-";
export const CONVERSATION_CREATE_KEY_PREFIX = "mmos-conversation-create-";
const CONVERSATION_CREATE_KEY_RE = /^mmos-conversation-create-[0-9a-f]{40}$/;
const CONVERSATION_WORK_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/;
const PROJECT_PAUSE_KEY_RE = /^mmos-project-pause-[0-9a-f]{40}$/;
const TARGET_KEY_RE = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
// ── Exact issued pointer variants (key-shape discriminated, own record version) ──
const JOURNEY_CREATE_KEY_RE = /^mmos-journey-create-[0-9a-f]{40}$/;
/** Journey request ids keep the incumbent publish_project_proposal id grammar. */
const CREATE_REQUEST_ID_RE = /^mmos-project-create-[0-9a-f]{40}$/;
const CREATE_WORK_RE = /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const PLANNING_KEY_RE = /^mmos-project-planning-[0-9a-f]{40}$/;
const PLANNING_TARGET_PREFIX = "project-initial-planning.v1:";
const PLANNING_WORK_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const POINTER_INPUT_KEYS: ReadonlySet<string> = new Set(["operationKey", "kind", "targetKey"]);
const RECORD_KEYS: ReadonlyArray<string> = ["v", "operationKey", "kind", "targetKey"];

function fail(code: string): never {
  throw new Error(code);
}

function closeQuietly(db: IDBDatabase | null | undefined): void {
  if (!db) return;
  try {
    db.close();
  } catch {
    return;
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function assertScope(scope: string): void {
  if (typeof scope !== "string" || !SCOPE_RE.test(scope)) {
    fail(PENDING_POINTER_ERRORS.INVALID_SCOPE);
  }
}

const KIND_RECORDS = {
  launch: { v: 1, key: LAUNCH_KEY_RE, consume: false },
  consume: { v: 1, key: CONSUME_KEY_RE, consume: true },
  project_pause: { v: 2, key: PROJECT_PAUSE_KEY_RE, consume: false },
  project_resume: { v: 3, key: /^mmos-project-resume-[0-9a-f]{40}$/, consume: false },
  project_create: { v: 4, key: /^mmos-project-create-[0-9a-f]{40}$/, consume: false },
  project_adopt: { v: 4, key: /^mmos-project-adopt-[0-9a-f]{40}$/, consume: false },
  direction_accept: { v: 4, key: /^mmos-direction-accept-[0-9a-f]{40}$/, consume: false },
  project_source_write: { v: 5, key: /^mmos-project-(?:file-add|preference-set|discovery-correct)-[0-9a-f]{40}$/, consume: false },
  instruction_pause: { v: 6, key: /^mmos-instruction-pause-[0-9a-f]{40}$/, consume: false },
  conversation_create: { v: 7, key: CONVERSATION_CREATE_KEY_RE, consume: false },
  conversation_consume: { v: 10, key: /^mmos-conversation-consume-[0-9a-f]{40}$/, consume: false },
  conversation_turn: { v: 11, key: /^mmos-conversation-turn-[0-9a-f]{40}$/, consume: false },
} as const;
/**
 * Extra closed shapes of an EXISTING kind, discriminated by the exact issued
 * operation-key prefix. Each variant carries its own record version, so no
 * v1-v7 record can ever decode as (or be confused with) a variant and vice
 * versa; the prefix grammars are disjoint from every legacy key grammar.
 */
const KIND_VARIANTS = {
  conversation_create: [{ v: 13, key: /^mmos-hermes-create-[0-9a-f]{32}$/, consume: false }],
  conversation_turn: [{ v: 14, key: /^mmos-hermes-send-[0-9a-f]{32}$/, consume: false }],
  project_source_write: [{v:15,key:/^mmos-project-plan-proposal-[0-9a-f]{40}$/,consume:false}],
  project_create: [{ v: 8, key: JOURNEY_CREATE_KEY_RE, consume: false }],
  launch: [{ v: 9, key: PLANNING_KEY_RE, consume: false },
    { v: 12, key: /^mmos-project-execute-[0-9a-f]{40}$/, consume: false }],
} as const;
function recordSpec(kind: unknown, operationKey?: unknown) {
  if (typeof kind !== "string" || !Object.hasOwn(KIND_RECORDS, kind)) return null;
  const variants = KIND_VARIANTS[kind as keyof typeof KIND_VARIANTS];
  if (variants !== undefined && typeof operationKey === "string") {
    for (const variant of variants) if (variant.key.test(operationKey)) return variant;
  }
  return KIND_RECORDS[kind as StoredKind];
}
/** The exact journey CREATE target: canonical closed `{request_id, work_ref}` bytes. */
function createTargetRecord(targetKey: unknown): { request_id: string; work_ref: string | null } | null {
  // Bound parsing before JSON allocation; original request + canonical WS
  // identity fits this cap. The current status/URL owner bounds WS keys at64.
  if (typeof targetKey !== "string" || targetKey.length > 256) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(targetKey);
  } catch {
    return null;
  }
  if (!isPlainObject(parsed) || Object.keys(parsed).length !== 2
      || !Object.hasOwn(parsed, "request_id") || !Object.hasOwn(parsed, "work_ref")) return null;
  if (typeof parsed.request_id !== "string" || !CREATE_REQUEST_ID_RE.test(parsed.request_id)) return null;
  if (parsed.work_ref !== null && (typeof parsed.work_ref !== "string" || parsed.work_ref.length > 67
      || !CREATE_WORK_RE.test(parsed.work_ref))) {
    return null;
  }
  if (canonicalJson(parsed) !== targetKey) return null;
  return { request_id: parsed.request_id, work_ref: parsed.work_ref as string | null };
}
/** The journey key binds the actual scope, request id and work ref derivation. */
function journeyCreateKeyMatches(operationKey: string, scope: string,
    target: { request_id: string; work_ref: string | null }): boolean {
  return operationKey === `mmos-journey-create-${sha256Hex(
    canonicalJson({ v: 1, principalScope: scope, request_id: target.request_id, work_ref: target.work_ref }),
  ).slice(0, 40)}`;
}
/** Exact issued planning target grammar; no suffix wildcard is accepted. */
function planningTargetMatches(targetKey: unknown): boolean {
  if (typeof targetKey !== "string" || !targetKey.startsWith(PLANNING_TARGET_PREFIX)) return false;
  const workRef = targetKey.slice(PLANNING_TARGET_PREFIX.length);
  return PLANNING_WORK_RE.exec(workRef)?.[0] === workRef;
}
function validFields(raw: Record<string, unknown>, spec: NonNullable<ReturnType<typeof recordSpec>>, scope: string): boolean {
  if (typeof raw.operationKey !== "string" || !spec.key.test(raw.operationKey)
      || (spec.v !== 1 && spec.key.exec(raw.operationKey)?.[0] !== raw.operationKey)) return false;
  if (spec.v === 13 || spec.v === 14) {
    return readNativePending(raw as unknown as OperationPointer) !== null;
  }
  if (spec.v === 15) {
    const target=parsePlanProposalTarget(raw.targetKey);
    return target!==null && target.request_id===raw.operationKey && target.principal_scope===scope;
  }
  if (spec.v === 5) {
    if (typeof raw.targetKey !== "string") return false;
    const target = parseProjectSourceWriteTarget(raw.targetKey);
    return target !== null && projectSourceWriteKeyMatches(raw.operationKey, target);
  }
  if (spec.v === 6) return parseInstructionAdmissionTarget(raw.targetKey) !== null;
  if (spec.v === 7) return typeof raw.targetKey === "string" && CONVERSATION_WORK_RE.exec(raw.targetKey)?.[0] === raw.targetKey;
  if (spec.v === 8) {
    const target = createTargetRecord(raw.targetKey);
    return target !== null && journeyCreateKeyMatches(raw.operationKey, scope, target);
  }
  // The planning launch key commits the whole private request, so it cannot be
  // recomputed from the pointer alone; the issuing port's prepare owns that
  // binding and this store enforces only the exact issued key/target grammar.
  if (spec.v === 9) return planningTargetMatches(raw.targetKey);
  if (spec.v === 12) return typeof raw.targetKey === "string" && raw.targetKey.length >= 5 && raw.targetKey.length <= 67
    && CREATE_WORK_RE.exec(raw.targetKey)?.[0] === raw.targetKey;
  if (spec.v === 10 || spec.v === 11) return parseFreshConversationTarget(raw.targetKey)!==null;
  return typeof raw.targetKey === "string"
    && (spec.consume ? parseDirectConsumeTarget(raw.targetKey) !== null : TARGET_KEY_RE.test(raw.targetKey))
    && (spec.v === 1 || TARGET_KEY_RE.exec(raw.targetKey)?.[0] === raw.targetKey);
}
function parsePointer(pointer: unknown, scope: string): ClosedRecord {
  if (!isPlainObject(pointer)) fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  const keys = Object.keys(pointer), spec = recordSpec(pointer.kind, pointer.operationKey);
  if (keys.length !== POINTER_INPUT_KEYS.size || keys.some(key => !POINTER_INPUT_KEYS.has(key))
      || spec === null || !validFields(pointer, spec, scope)) fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  // The closed kind-to-version map above is the sole source of this version.
  return {v:spec.v,operationKey:pointer.operationKey,kind:pointer.kind,targetKey:pointer.targetKey} as ClosedRecord;
}
function decodeRecord(value: unknown, scope: string): OperationPointer {
  if (!isPlainObject(value)) fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  const keys = Object.keys(value), spec = recordSpec(value.kind, value.operationKey);
  if (keys.length !== RECORD_KEYS.length || RECORD_KEYS.some(key => !Object.hasOwn(value,key))
      || keys.some(key => !RECORD_KEYS.includes(key)) || spec === null || value.v !== spec.v
      || !validFields(value,spec,scope)) fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  return {operationKey:value.operationKey as string,kind:value.kind as StoredKind,targetKey:value.targetKey as string};
}

function canonicalFieldsEqual(a: ClosedRecord, b: OperationPointer): boolean {
  return (
    a.operationKey === b.operationKey && a.kind === b.kind && a.targetKey === b.targetKey
  );
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error(PENDING_POINTER_ERRORS.TX_FAILED));
  });
}

function openWriteTransaction(db: IDBDatabase, mode: IDBTransactionMode): IDBTransaction {
  const transaction = db.transaction(PENDING_POINTER_STORE_NAME, mode, { durability: "strict" });
  if (transaction.durability !== "strict") {
    try { transaction.abort(); } catch { /* no write was enqueued */ }
    fail(PENDING_POINTER_ERRORS.TX_FAILED);
  }
  return transaction;
}

function openTransaction(
  db: IDBDatabase,
  mode: IDBTransactionMode,
  write: boolean,
): IDBTransaction {
  return write
    ? openWriteTransaction(db, mode)
    : db.transaction(PENDING_POINTER_STORE_NAME, mode);
}

function openDatabase(factory: IDBFactory, signal?: AbortSignal): Promise<IDBDatabase> {
  return new Promise<IDBDatabase>((resolve, reject) => {
    let settled = false;
    let request: IDBOpenDBRequest;
    if (signal?.aborted) { reject(new Error(PENDING_POINTER_ERRORS.CANCELLED)); return; }
    try {
      request = factory.open(PENDING_POINTER_DB_NAME, PENDING_POINTER_DB_VERSION);
    } catch {
      reject(new Error(PENDING_POINTER_ERRORS.OPEN_FAILED));
      return;
    }
    if (!request) {
      reject(new Error(PENDING_POINTER_ERRORS.OPEN_FAILED));
      return;
    }

    const closeResult = () => {
      try { closeQuietly(request.result); } catch { /* result is unavailable before success */ }
    };
    const onAbort = () => settleError(PENDING_POINTER_ERRORS.CANCELLED);
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", onAbort);
      closeResult();
      reject(new Error(PENDING_POINTER_ERRORS.TIMEOUT));
    }, PENDING_POINTER_OPEN_TIMEOUT_MS);

    const settleError = (code: string, db?: IDBDatabase | null): void => {
      if (settled) {
        if (db) closeQuietly(db); else closeResult();
        return;
      }
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      if (db) closeQuietly(db); else closeResult();
      reject(new Error(code));
    };

    const settleOk = (db: IDBDatabase): void => {
      if (settled) {
        closeQuietly(db);
        return;
      }
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      resolve(db);
    };

    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) onAbort();

    request.onupgradeneeded = () => {
      if (settled) {
        try {
          request.transaction?.abort();
        } catch {
          return;
        }
        return;
      }
      const db = request.result;
      if (!db) return;
      try {
        if (!db.objectStoreNames.contains(PENDING_POINTER_STORE_NAME)) {
          db.createObjectStore(PENDING_POINTER_STORE_NAME);
        }
      } catch {
        settleError(PENDING_POINTER_ERRORS.OPEN_FAILED, db);
      }
    };

    request.onsuccess = () => {
      const db = request.result;
      if (!db) {
        settleError(PENDING_POINTER_ERRORS.OPEN_FAILED);
        return;
      }
      if (settled) {
        closeQuietly(db);
        return;
      }
      if (
        db.version !== PENDING_POINTER_DB_VERSION ||
        !db.objectStoreNames.contains(PENDING_POINTER_STORE_NAME)
      ) {
        settleError(PENDING_POINTER_ERRORS.OPEN_FAILED, db);
        return;
      }
      db.onversionchange = () => {
        closeQuietly(db);
      };
      settleOk(db);
    };

    request.onerror = () => {
      settleError(PENDING_POINTER_ERRORS.OPEN_FAILED);
    };

    request.onblocked = () => {
      settleError(PENDING_POINTER_ERRORS.BLOCKED);
    };
  });
}

function runTransaction<T>(
  db: IDBDatabase,
  mode: IDBTransactionMode,
  write: boolean,
  body: (store: IDBObjectStore) => Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    let result: T;
    let resultReady = false;
    if (signal?.aborted) { reject(new Error(PENDING_POINTER_ERRORS.CANCELLED)); return; }
    let transaction: IDBTransaction;
    let store: IDBObjectStore;
    try {
      transaction = openTransaction(db, mode, write);
      store = transaction.objectStore(PENDING_POINTER_STORE_NAME);
    } catch {
      reject(new Error(PENDING_POINTER_ERRORS.TX_FAILED));
      return;
    }

    const timer = setTimeout(() => refuse(PENDING_POINTER_ERRORS.TIMEOUT), PENDING_POINTER_TX_TIMEOUT_MS);
    const onAbort = () => refuse(PENDING_POINTER_ERRORS.CANCELLED);
    const refuse = (code: string) => {
      settle(() => {
        try { transaction.abort(); } catch { /* still reject */ }
        reject(new Error(code));
      });
    };

    const settle = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      fn();
    };

    transaction.oncomplete = () => {
      settle(() => { if (resultReady) resolve(result); else reject(new Error(PENDING_POINTER_ERRORS.TX_FAILED)); });
    };
    transaction.onerror = () => {
      settle(() => reject(new Error(PENDING_POINTER_ERRORS.TX_FAILED)));
    };
    transaction.onabort = () => {
      settle(() => reject(new Error(PENDING_POINTER_ERRORS.TX_FAILED)));
    };

    db.onversionchange = () => {
      refuse(PENDING_POINTER_ERRORS.VERSION_CHANGE);
      closeQuietly(db);
    };
    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) onAbort();

    Promise.resolve()
      .then(() => { if (settled) throw new Error(PENDING_POINTER_ERRORS.CANCELLED); return body(store); })
      .then((value) => {
        result = value;
        resultReady = true;
      })
      .catch((err: unknown) => {
        settle(() => {
          try {
            transaction.abort();
          } catch { /* still reject */ }
          reject(err instanceof Error ? err : new Error(PENDING_POINTER_ERRORS.TX_FAILED));
        });
      });
  });
}

async function readInStore(
  store: IDBObjectStore,
  scope: string,
): Promise<OperationPointer | null> {
  const value = await requestToPromise(store.get(scope) as IDBRequest<unknown>);
  if (value === undefined) return null;
  return decodeRecord(value, scope);
}

async function reserveInStore(
  store: IDBObjectStore,
  scope: string,
  record: ClosedRecord,
): Promise<DurableReservation> {
  const value = await requestToPromise(store.get(scope) as IDBRequest<unknown>);
  if (value !== undefined) {
    const existing = decodeRecord(value, scope);
    return { reserved: false, pointer: existing };
  }
  await requestToPromise(store.add(record, scope) as IDBRequest<IDBValidKey>);
  return { reserved: true };
}

async function clearIfEqualInStore(
  store: IDBObjectStore,
  scope: string,
  record: ClosedRecord,
): Promise<boolean> {
  const value = await requestToPromise(store.get(scope) as IDBRequest<unknown>);
  if (value === undefined) return false;
  const existing = decodeRecord(value, scope);
  if (!canonicalFieldsEqual(record, existing)) return false;
  await requestToPromise(store.delete(scope) as IDBRequest<undefined>);
  return true;
}

export function createIndexedDbPendingPointerStore(
  factory: IDBFactory | undefined,
): DurablePendingPointerStore {
  const requireFactory = (): IDBFactory => {
    if (factory === undefined || factory === null) {
      fail(PENDING_POINTER_ERRORS.UNAVAILABLE);
    }
    return factory;
  };

  return {
    async read(scope: string, signal?: AbortSignal): Promise<OperationPointer | null> {
      assertScope(scope);
      const idb = requireFactory();
      const db = await openDatabase(idb, signal);
      try {
        return await runTransaction(db, "readonly", false, (store) => readInStore(store, scope), signal);
      } finally {
        closeQuietly(db);
      }
    },

    async reserve(scope: string, pointer: OperationPointer, signal?: AbortSignal): Promise<DurableReservation> {
      assertScope(scope);
      const record = parsePointer(pointer, scope);
      const idb = requireFactory();
      const db = await openDatabase(idb, signal);
      try {
        return await runTransaction(db, "readwrite", true, (store) => reserveInStore(store, scope, record), signal);
      } finally {
        closeQuietly(db);
      }
    },

    async clearIfEqual(scope: string, pointer: OperationPointer, signal?: AbortSignal): Promise<boolean> {
      assertScope(scope);
      const record = parsePointer(pointer, scope);
      const idb = requireFactory();
      const db = await openDatabase(idb, signal);
      try {
        return await runTransaction(db, "readwrite", true, (store) => clearIfEqualInStore(store, scope, record), signal);
      } finally {
        closeQuietly(db);
      }
    },
  };
}
