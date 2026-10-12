import type { OperationPointer } from "./operation-controller";

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

interface ClosedRecord {
  readonly v: 1;
  readonly operationKey: string;
  readonly kind: "launch";
  readonly targetKey: string;
}

type DurableReservation =
  | { readonly reserved: true }
  | { readonly reserved: false; readonly pointer: OperationPointer };


const SCOPE_RE = /^[0-9a-f]{64}$/;
const LAUNCH_KEY_RE = /^mmos-launch-[0-9a-f]{40}$/;
const TARGET_KEY_RE = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
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

function parsePointer(pointer: unknown): ClosedRecord {
  if (!isPlainObject(pointer)) fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  const raw = pointer;
  const keys = Object.keys(raw);
  if (keys.length !== POINTER_INPUT_KEYS.size) fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  for (const key of keys) {
    if (!POINTER_INPUT_KEYS.has(key)) fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  }
  if (raw.kind !== "launch") fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  if (typeof raw.operationKey !== "string" || !LAUNCH_KEY_RE.test(raw.operationKey)) {
    fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  }
  if (typeof raw.targetKey !== "string" || !TARGET_KEY_RE.test(raw.targetKey)) {
    fail(PENDING_POINTER_ERRORS.INVALID_POINTER);
  }
  return {
    v: 1,
    operationKey: raw.operationKey,
    kind: "launch",
    targetKey: raw.targetKey,
  };
}

function decodeRecord(value: unknown): OperationPointer {
  if (!isPlainObject(value)) fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  const raw = value;
  const keys = Object.keys(raw);
  if (keys.length !== RECORD_KEYS.length) fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  for (const key of RECORD_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(raw, key)) {
      fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
    }
  }
  for (const key of keys) {
    if (!RECORD_KEYS.includes(key)) fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  }
  if (raw.v !== 1) fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  if (raw.kind !== "launch") fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  if (typeof raw.operationKey !== "string" || !LAUNCH_KEY_RE.test(raw.operationKey)) {
    fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  }
  if (typeof raw.targetKey !== "string" || !TARGET_KEY_RE.test(raw.targetKey)) {
    fail(PENDING_POINTER_ERRORS.CORRUPT_RECORD);
  }
  return {
    operationKey: raw.operationKey,
    kind: "launch",
    targetKey: raw.targetKey,
  };
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
  return decodeRecord(value);
}

async function reserveInStore(
  store: IDBObjectStore,
  scope: string,
  record: ClosedRecord,
): Promise<DurableReservation> {
  const value = await requestToPromise(store.get(scope) as IDBRequest<unknown>);
  if (value !== undefined) {
    const existing = decodeRecord(value);
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
  const existing = decodeRecord(value);
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
      const record = parsePointer(pointer);
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
      const record = parsePointer(pointer);
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
