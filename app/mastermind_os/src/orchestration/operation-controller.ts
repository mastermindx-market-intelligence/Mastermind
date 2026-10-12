/**
 * OperationController — UI-local command reconciliation
 *
 * A finite state machine over a typed injected port. There is no backend, no
 * wire adapter, no runtime/provider selection and no execution store here: the
 * controller owns only *which receipt the UI is currently allowed to show*.
 * The injected {@link FiniteCommandPort} is the sole authority for what actually
 * happened, and the injected {@link PendingPointerStore} is the sole authority
 * for persisting the pending-operation hint.
 *
 * HOST DEPENDENCIES this module cannot enforce on its own:
 *
 *  1. `OwnerContext.generation` MUST be monotonic per principal scope and MUST
 *     change on every authentication epoch change — including A→B→A (user A
 *     signs out, B signs in, A signs back in must produce a *third* generation,
 *     not a repeat of the first). The controller compares the generation it
 *     captured when an operation started against the generation the port
 *     reports when the receipt arrives; a generation that is not monotonic
 *     makes A→B→A indistinguishable from the original session. The controller
 *     never mints, signs, parses or validates generations — it compares them.
 *
 *  2. The host MUST call {@link OperationController.invalidate} when the user's
 *     selected mission root changes. `targetKey` is an opaque owner target
 *     reference: the controller never parses it, never derives a root from it,
 *     and never compares it against an "expected" root. Selection identity is
 *     only ever observed on a receipt that carries one.
 *
 *  3. Persistence, enrollment and operation-key minting live in the host's
 *     port and store implementations, not here.
 *
 * DURABILITY. The pending-pointer store is durable: `read`, `reserve`, and
 * `clearIfEqual` are atomic operations whose commitment cannot be claimed
 * cancelled by a later signal. The controller awaits each of them in turn,
 * fences after every await, and refuses to publish anything — pointer,
 * selection, or terminal state — into a controller epoch that no longer owns
 * the visible UI. Only a full terminal receipt (accepted/refused) followed by
 * a successful `clearIfEqual` may erase the exact hint; a false or rejected
 * clear leaves the pointer in place and the UI holds unknown so a later
 * recover can resolve it.
 *
 * Privacy: `CommandIntent.payload` is never persisted, never handed to the
 * store, and never surfaced in state. Producer `reason` text and thrown
 * exception text are never forwarded, even when they happen to match a
 * fixed code. Receipt outcomes publish only disposition-derived codes
 * (`ACCEPTED` / `REFUSED` / `UNKNOWN_RECEIPT`) plus the local decode/hold
 * codes this module itself assigns.
 */

import {
  type MissionSelection,
  normalizeSelection,
} from "../mission";

// ── Frozen UI-local contract types ────────────────────────────────────────────

export type OperationKind = "launch" | "message" | "stop";

export interface CommandIntent {
  readonly kind: OperationKind;
  /** Never persisted, never leaves this module. */
  readonly payload: Readonly<Record<string, unknown>>;
  /** Opaque owner target reference. Never parsed, never compared to a root. */
  readonly targetKey: string | null;
}

export interface OwnerContext {
  readonly principalScope: string;
  /** Host-supplied, monotonic per scope. See module doc, dependency (1). */
  readonly generation: string;
}

export interface OperationPointer {
  readonly operationKey: string;
  readonly kind: OperationKind;
  readonly targetKey: string | null;
}

export interface EffectReceipt {
  readonly operationKey: string;
  readonly kind: OperationKind;
  readonly targetKey: string | null;
  readonly disposition: "accepted" | "refused" | "unknown";
  /** Meaningful only on an accepted launch receipt. See `_decide`. */
  readonly missionSelection?: MissionSelection;
  /** Opaque producer text; never surfaced verbatim to the UI. */
  readonly reason?: string;
}

/** Allow in-memory test stores to return values directly; controllers always await. */
export type MaybePromise<T> = T | Promise<T>;

// ── Port / store interfaces ───────────────────────────────────────────────────

export interface FiniteCommandPort {
  context(): OwnerContext | null;
  /** Synchronous and effect-free; must not mint or select runtime/provider IDs. */
  prepare(intent: CommandIntent): OperationPointer;
  submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ): Promise<EffectReceipt>;
  readOperation(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt>;
}

/**
 * Durable pending-pointer store. Three atomic operations:
 *
 *  - {@link PendingPointerStore.read} returns the current pending pointer for a
 *    scope, or `null` when none exists. A read failure (host store blocked /
 *    aborted) is reported by rejecting the returned promise.
 *
 *  - {@link PendingPointerStore.reserve} atomically claims the scope for a
 *    specific pointer. It NEVER overwrites, even when the incoming pointer is
 *    exactly equal to the existing one: a concurrent begin that races for the
 *    same scope and pointer loses the reservation and receives the existing
 *    pointer back, so the loser can join the in-flight observation rather
 *    than submit a second effect.
 *
 *  - {@link PendingPointerStore.clearIfEqual} deletes the hint at the scope
 *    iff it exactly matches the provided pointer (operationKey, kind,
 *    targetKey). A `false` return or rejection means the caller's commit is
 *    unknown and the pointer remains in the store; the controller treats that
 *    as an explicit non-terminal hold, not a terminal settlement.
 *
 * All three operations accept an optional `AbortSignal`. The host store may
 * abort an uncommitted transaction when the controller invalidates the
 * visible epoch; a transaction that has already committed durably ignores the
 * signal, so the controller never claims cancellation of a durable effect.
 *
 * The production shape has NO `write` or `clear` alias. Controllers cannot
 * compose `write` + `clear` to fake atomic durability, and the shape check
 * in {@link completeOrchestratorCommandBinding} rejects bindings that
 * expose those aliases.
 */
export interface PendingPointerStore {
  read(
    principalScope: string,
    signal?: AbortSignal,
  ): MaybePromise<OperationPointer | null>;
  reserve(
    principalScope: string,
    pointer: OperationPointer,
    signal?: AbortSignal,
  ): MaybePromise<
    | { readonly reserved: true }
    | { readonly reserved: false; readonly pointer: OperationPointer }
  >;
  clearIfEqual(
    principalScope: string,
    pointer: OperationPointer,
    signal?: AbortSignal,
  ): MaybePromise<boolean>;
}

// ── Safe reasons ──────────────────────────────────────────────────────────────

/**
 * Fixed vocabulary for every user-visible reason. The controller assigns these
 * itself. Producer receipt `reason` strings never become UI reasons, even if
 * they happen to equal one of the codes.
 */
type SafeReason =
  | "IDLE"
  | "SUBMITTING"
  | "OPERATION_BUSY"
  | "CLEARED"
  | "OWNER_ABSENT"
  | "INVALID_KIND"
  | "INVALID_TARGET"
  | "INVALID_PAYLOAD"
  | "MALFORMED_POINTER"
  | "KIND_MISMATCH"
  | "TARGET_MISMATCH"
  | "STORE_WRITE_FAILED"
  | "LOCAL_UNAVAILABLE"
  | "PENDING_POINTER"
  | "CHECKING"
  | "RECOVER_NO_POINTER"
  | "RECOVER_FAILED"
  | "MALFORMED_RECEIPT"
  | "RECEIPT_MISMATCH"
  | "SELECTION_INVALID"
  | "SELECTION_NOT_ALLOWED"
  | "EPOCH_CHANGED"
  | "TRANSPORT_ERROR"
  | "UNKNOWN_RECEIPT"
  | "ACCEPTED"
  | "REFUSED";

// ── Operation state ───────────────────────────────────────────────────────────

export type OperationState =
  | IdleState
  | SubmittingState
  | CheckingState
  | AcceptedState
  | RefusedState
  | UnknownState;

export interface IdleState {
  readonly status: "idle";
  readonly pointer: null;
  readonly reason: SafeReason;
}

export interface SubmittingState {
  readonly status: "submitting";
  readonly pointer: OperationPointer;
  readonly reason: SafeReason;
}

export interface CheckingState {
  readonly status: "checking";
  readonly pointer: OperationPointer;
  readonly reason: SafeReason;
}

/** Terminal. `missionSelection` is present only when the producer supplied one. */
export interface AcceptedState {
  readonly status: "accepted";
  readonly pointer: null;
  readonly reason: SafeReason;
  readonly missionSelection?: MissionSelection;
}

export interface RefusedState {
  readonly status: "refused";
  readonly pointer: null;
  readonly reason: SafeReason;
}

/** Not terminal. The pointer is retained so `recover()` can still resolve it. */
export interface UnknownState {
  readonly status: "unknown";
  readonly pointer: OperationPointer;
  readonly reason: SafeReason;
}

// ── Validation helpers ────────────────────────────────────────────────────────

const VALID_KINDS: ReadonlySet<string> = new Set(["launch", "message", "stop"]);

const POINTER_KEYS: ReadonlySet<string> = new Set([
  "operationKey",
  "kind",
  "targetKey",
]);

const RECEIPT_KEYS: ReadonlySet<string> = new Set([
  "operationKey",
  "kind",
  "targetKey",
  "disposition",
  "missionSelection",
  "reason",
]);

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function hasOnlyKeys(v: object, allowed: ReadonlySet<string>): boolean {
  return Object.keys(v).every((k) => allowed.has(k));
}

function isValidKind(kind: unknown): kind is OperationKind {
  return typeof kind === "string" && VALID_KINDS.has(kind);
}

function nonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.length > 0;
}

function isValidPointer(p: unknown): p is OperationPointer {
  if (!isPlainObject(p) || !hasOnlyKeys(p, POINTER_KEYS)) return false;
  return (
    nonEmptyString(p.operationKey) &&
    isValidKind(p.kind) &&
    (p.targetKey === null || typeof p.targetKey === "string")
  );
}

/**
 * Structural check only. `missionSelection` is deliberately *not* decoded here:
 * an absent or undecodable selection on an accepted launch is one outcome
 * (`unknown` / `SELECTION_INVALID`, pointer held for recovery), and a selection
 * on any other receipt is a different outcome (pointer retained /
 * `SELECTION_NOT_ALLOWED`). Decoding here would collapse the two into one
 * indistinguishable bucket.
 */
function isValidReceipt(r: unknown): r is EffectReceipt {
  if (!isPlainObject(r) || !hasOnlyKeys(r, RECEIPT_KEYS)) return false;
  return (
    typeof r.operationKey === "string" &&
    isValidKind(r.kind) &&
    (r.targetKey === null || typeof r.targetKey === "string") &&
    (r.disposition === "accepted" ||
      r.disposition === "refused" ||
      r.disposition === "unknown") &&
    (r.missionSelection === undefined || isPlainObject(r.missionSelection)) &&
    (r.reason === undefined || typeof r.reason === "string")
  );
}

function isValidIntent(i: unknown): i is CommandIntent {
  return (
    isPlainObject(i) &&
    isValidKind(i.kind) &&
    isPlainObject(i.payload) &&
    (i.targetKey === null || typeof i.targetKey === "string")
  );
}

// ── Controller ────────────────────────────────────────────────────────────────

/** Identity of the operation the UI is currently tracking. */
interface TrackedOperation {
  readonly pointer: OperationPointer;
  /** Scope the hint was written under — never re-derived from live context. */
  readonly scope: string;
  /** `OwnerContext.generation` captured at start. See module doc, dependency (1). */
  readonly generation: string;
  /** Controller-local epoch captured at start. */
  readonly epoch: number;
  readonly abort: AbortController | null;
}

type StoredRead =
  | { readonly ok: true; readonly pointer: OperationPointer | null }
  | { readonly ok: false; readonly reason: "MALFORMED_POINTER" | "LOCAL_UNAVAILABLE" };

type ReserveOutcome =
  | { readonly ok: true; readonly reserved: true }
  | { readonly ok: false; readonly reason: "STORE_WRITE_FAILED" }
  | {
      readonly ok: true;
      readonly reserved: false;
      readonly pointer: OperationPointer;
    };

export class OperationController {
  private _state: OperationState = {
    status: "idle",
    pointer: null,
    reason: "IDLE",
  };

  private _inflight: Promise<OperationState> | null = null;
  private _activeAbort: AbortController | null = null;

  /**
   * Controller-local monotonic counter. Bumped when a new operation starts and
   * by `invalidate()`. A receipt whose epoch no longer matches belongs to a
   * superserved operation and is dropped without publishing or clearing.
   */
  private _epoch = 0;

  private _tracked: TrackedOperation | null = null;

  constructor(
    private readonly _port: FiniteCommandPort,
    private readonly _store: PendingPointerStore,
  ) {}

  getState(): OperationState {
    return this._state;
  }

  /**
   * Begin a new operation.
   *
   * Ordering matters:
   *  1. owner context, identity, intent shape, and the in-flight busy gate are
   *     all resolved synchronously;
   *  2. the in-flight slot is then installed BEFORE the first async store read,
   *     so a reentrant begin is refused locally (`OPERATION_BUSY`) until the
   *     run releases the slot;
   *  3. after every await the controller re-fences against the captured scope,
   *     generation, and epoch; an invalidated or superseded run can publish
   *     nothing;
   *  4. `store.read` returning a pointer routes to checking/PENDING_POINTER
   *     (recover-only), null is the only "empty" sentinel — read unavailable
   *     or corrupt returns `LOCAL_UNAVAILABLE` or `MALFORMED_POINTER` and
   *     zeros effects;
   *  5. `store.reserve` is awaited BEFORE `port.submit`; a reservation
   *     already held by an exact or different pointer keeps the caller in
   *     checking/PENDING_POINTER with no second submit;
   *  6. only the run that holds the reservation may publish or clear — a
   *     reentrant host callback that arrives after `reserve` resolved cannot
   *     create a duplicate submission because the run is already executing
   *     and the in-flight slot is held until the clear attempt resolves.
   */
  async begin(intent: CommandIntent): Promise<OperationState> {
    const ctx = this._port.context();
    if (!ctx) return this._idle("OWNER_ABSENT");

    const raw: unknown = intent;
    if (!isValidIntent(raw)) {
      if (!isPlainObject(raw) || !isValidKind(raw.kind)) {
        return this._idle("INVALID_KIND");
      }
      if (!isPlainObject(raw.payload)) return this._idle("INVALID_PAYLOAD");
      return this._idle("INVALID_TARGET");
    }
    if (intent.targetKey !== null && intent.targetKey.length === 0) {
      return this._idle("INVALID_TARGET");
    }

    // Sync in-flight check: the slot may already be held by a prior begin/recover.
    if (this._inflight) return this._busy();

    const scope = ctx.principalScope;
    const generation = ctx.generation;
    const epoch = ++this._epoch;
    const abort = new AbortController();

    return this._startInflight(async (): Promise<OperationState> => {
      // 1. Async read. Awaiting here is safe because _inflight was installed
      //    synchronously by _startInflight before this run started.
      const read = await this._readStoredAsync(scope, abort.signal);
      if (this._stale(epoch, scope, generation)) return this._state;
      if (!read.ok) {
        return this._idle(read.reason);
      }
      if (read.pointer) {
        // Already a pending pointer in the store: never submit over it.
        this._track(read.pointer, scope, generation, epoch, abort);
        const state: CheckingState = {
          status: "checking",
          pointer: read.pointer,
          reason: "PENDING_POINTER",
        };
        this._state = state;
        return state;
      }

      // 2. Prepare pointer (sync; effect-free). A throwing prepare is the
      //    caller's contract failure, not the store's, so we do not abort it.
      let pointer: OperationPointer;
      try {
        pointer = this._port.prepare(intent);
      } catch {
        return this._idle("MALFORMED_POINTER");
      }
      if (!isValidPointer(pointer)) return this._idle("MALFORMED_POINTER");
      if (pointer.kind !== intent.kind) return this._idle("KIND_MISMATCH");
      if (pointer.targetKey !== intent.targetKey) {
        return this._idle("TARGET_MISMATCH");
      }

      // 3. Fence again — prepare can re-enter host callbacks.
      if (this._stale(epoch, scope, generation)) return this._state;

      // 4. Durable reserve. Awaiting commit BEFORE submit is the contract.
      const reserved = await this._reserveAsync(scope, pointer, abort.signal);
      if (this._stale(epoch, scope, generation)) return this._state;
      if (!reserved.ok) return this._idle(reserved.reason);
      if (!reserved.reserved) {
        // Lost the reservation race to another controller; track what is in
        // the store and route to checking — never submit.
        this._track(reserved.pointer, scope, generation, epoch, abort);
        const state: CheckingState = {
          status: "checking",
          pointer: reserved.pointer,
          reason: "PENDING_POINTER",
        };
        this._state = state;
        return state;
      }

      // 5. Reservation committed. We own the slot; track and submit.
      const op = this._track(pointer, scope, generation, epoch, abort);
      this._state = { status: "submitting", pointer, reason: "SUBMITTING" };

      let receipt: unknown;
      try {
        receipt = await this._port.submit(pointer, intent, abort.signal);
      } catch {
        if (this._stale(epoch, scope, generation)) return this._state;
        return await this._applyFailure(op, "TRANSPORT_ERROR");
      }
      if (this._stale(epoch, scope, generation)) return this._state;
      return await this._applyReceipt(receipt, op);
    }, abort);
  }

  /**
   * Resolve the pending hint through `readOperation` only. Never submits.
   *
   * Recover is observation only. It may join an in-flight promise only when
   * the live principal and generation match the captured tracked context.
   * A foreign or changed context is refused locally (`OPERATION_BUSY`)
   * without leaking the original pointer or selection, without publishing,
   * and without clearing the original-scope hint.
   */
  async recover(): Promise<OperationState> {
    const ctx = this._port.context();
    if (!ctx) return this._idle("OWNER_ABSENT");

    if (this._inflight) {
      const tracked = this._tracked;
      if (
        tracked &&
        ctx.principalScope === tracked.scope &&
        ctx.generation === tracked.generation
      ) {
        return this._inflight;
      }
      return this._busy();
    }

    const scope = ctx.principalScope;
    const generation = ctx.generation;
    const epoch = ++this._epoch;
    const abort = new AbortController();

    return this._startInflight(async (): Promise<OperationState> => {
      const read = await this._readStoredAsync(scope, abort.signal);
      if (this._stale(epoch, scope, generation)) return this._state;
      if (!read.ok) return this._idle(read.reason);
      if (!read.pointer) return this._idle("RECOVER_NO_POINTER");

      const pointer = read.pointer;
      this._state = { status: "checking", pointer, reason: "CHECKING" };
      const op = this._track(pointer, scope, generation, epoch, abort);

      let receipt: unknown;
      try {
        receipt = await this._port.readOperation(pointer, abort.signal);
      } catch {
        if (this._stale(epoch, scope, generation)) return this._state;
        return await this._applyFailure(op, "RECOVER_FAILED");
      }
      if (this._stale(epoch, scope, generation)) return this._state;
      return await this._applyReceipt(receipt, op);
    }, abort);
  }

  /**
   * Void the currently visible operation epoch.
   *
   * This is the hook the host calls when the user's selected mission root
   * changes (module doc, dependency 2). It drops the visible state and aborts
   * the in-flight request so a stale receipt can no longer be rendered.
   *
   * Aborting suppresses rendering only. It does not assert that the underlying
   * operation was cancelled, and it must not erase the pending hint. The
   * store-original signal is cleared by `clearIfEqual` on a terminal receipt.
   * A sign-out that leaves `context()` null is the same: the hint stays in
   * its original scope.
   */
  invalidate(): void {
    const tracked = this._tracked;
    const hadVisibleOperation = this._state.status !== "idle" || tracked !== null || this._inflight !== null;

    // Bump epoch before abort so a synchronous rejection cannot publish.
    this._epoch++;
    if (this._inflight) {
      this._activeAbort?.abort();
      // _inflight stays set until the run settles; clearing here would let a
      // racing begin submit a second effect into the same scope.
    }
    this._tracked = null;

    if (!hadVisibleOperation) return;

    this._state = { status: "idle", pointer: null, reason: "CLEARED" };
  }

  // ── internals ───────────────────────────────────────────────────────────────

  private _startInflight(
    run: () => Promise<OperationState>,
    abort: AbortController,
  ): Promise<OperationState> {
    let resolve!: (state: OperationState) => void;
    let reject!: (reason: unknown) => void;
    const inflight = new Promise<OperationState>((done, failed) => {
      resolve = done;
      reject = failed;
    });
    // Install the slot synchronously so reentrant begin/recover sees it
    // before the first await inside `run` yields to the event loop.
    this._inflight = inflight;
    this._activeAbort = abort;
    void run().then(
      (state) => {
        this._releaseInflight(inflight);
        resolve(state);
      },
      (err) => {
        this._releaseInflight(inflight);
        reject(err);
      },
    );
    return inflight;
  }

  private _track(
    pointer: OperationPointer,
    scope: string,
    generation: string,
    epoch: number,
    abort: AbortController | null,
  ): TrackedOperation {
    const op: TrackedOperation = { pointer, scope, generation, epoch, abort };
    this._tracked = op;
    return op;
  }

  private _releaseInflight(inflight: Promise<OperationState>): void {
    // Invalidation fences publication, but the settled run must release its slot.
    if (this._inflight === inflight) {
      this._inflight = null;
      this._activeAbort = null;
    }
  }

  /**
   * Is `op` still the operation this UI is showing? Returns the state to
   * short-circuit with, or `null` when the result may be considered.
   *
   * Two independent reasons to short-circuit:
   *
   *  - a newer controller epoch took over (a new `begin`, or `invalidate()`).
   *    The newer epoch owns both the visible state and the hint, so publish
   *    nothing and clear nothing;
   *
   *  - the authentication epoch moved on since `op` started — sign-out,
   *    generation bump, or a different principal. The result belongs to a
   *    session the UI is no longer showing. See module doc, dependency (1).
   */
  private _stale(
    epoch: number,
    scope: string,
    generation: string,
  ): boolean {
    if (this._epoch !== epoch) return true;
    const ctx = this._port.context();
    if (
      !ctx ||
      ctx.principalScope !== scope ||
      ctx.generation !== generation
    ) {
      this._epoch++;
      this._activeAbort?.abort();
      this._tracked = null;
      this._idle("EPOCH_CHANGED");
      return true;
    }
    return false;
  }

  /**
   * Suppress a stale result and keep the hint in its original scope.
   *
   * An authentication epoch change does not cancel the operation and is never
   * reported as one: the pointer stays so a later `recover()` can still
   * resolve it under the new epoch.
   */
  private _applyFailure(
    op: TrackedOperation,
    reason: SafeReason,
  ): Promise<OperationState> {
    if (this._stale(op.epoch, op.scope, op.generation)) return Promise.resolve(this._state);
    return Promise.resolve(this._retain(op, reason));
  }

  /**
   * A receipt arrived for `op`. Decide first whether it may be published.
   * Returns a promise so the caller can await the atomic `clearIfEqual`
   * before publishing a terminal state.
   */
  private _applyReceipt(
    receipt: unknown,
    op: TrackedOperation,
  ): Promise<OperationState> {
    if (this._stale(op.epoch, op.scope, op.generation)) return Promise.resolve(this._state);
    if (!isValidReceipt(receipt)) {
      return Promise.resolve(this._retain(op, "MALFORMED_RECEIPT"));
    }

    // The receipt must describe exactly the operation this controller issued.
    if (receipt.operationKey !== op.pointer.operationKey) {
      return Promise.resolve(this._retain(op, "RECEIPT_MISMATCH"));
    }
    if (receipt.kind !== op.pointer.kind) {
      return Promise.resolve(this._retain(op, "KIND_MISMATCH"));
    }
    if (receipt.targetKey !== op.pointer.targetKey) {
      return Promise.resolve(this._retain(op, "TARGET_MISMATCH"));
    }

    // Only an accepted launch receipt may carry a selection. A message or a
    // stop can never replace the selected root, and a refused or unknown
    // receipt never carries one. Such a receipt is not evidence of anything,
    // so hold the pointer rather than adopting the selection or declaring a
    // terminal state.
    if (receipt.missionSelection !== undefined) {
      if (receipt.kind !== "launch" || receipt.disposition !== "accepted") {
        return Promise.resolve(this._retain(op, "SELECTION_NOT_ALLOWED"));
      }
      const decoded = normalizeSelection(receipt.missionSelection);
      if (!decoded) return Promise.resolve(this._retain(op, "SELECTION_INVALID"));
      return this._clearAccepted(op, "ACCEPTED", decoded);
    }

    // An accepted launch is the effect that changes the selection, so it may
    // only be published as accepted when it carried a selection that decoded
    // above. With the selection absent, the outcome is not known to this
    // client: the producer may have accepted the launch even though the root
    // cannot be decoded here. That is never a refusal — hold the exact
    // pointer so a later recover() can re-read the operation.
    if (receipt.kind === "launch" && receipt.disposition === "accepted") {
      return Promise.resolve(this._retain(op, "SELECTION_INVALID"));
    }

    switch (receipt.disposition) {
      case "accepted":
        return this._clearAccepted(op, "ACCEPTED");
      case "refused":
        return this._clearRefused(op, "REFUSED");
      default:
        // Explicit unknown: the outcome is not known, so the pointer stays.
        return Promise.resolve(this._retain(op, "UNKNOWN_RECEIPT"));
    }
  }

  /** Terminal accept: clear exactly this operation's hint, then publish. */
  private async _clearAccepted(
    op: TrackedOperation,
    reason: SafeReason,
    selection?: MissionSelection,
  ): Promise<OperationState> {
    const cleared = await this._clearHint(op);
    if (this._stale(op.epoch, op.scope, op.generation)) return this._state;
    if (!cleared) {
      // compareclear false / rejected: hold unknown, pointer remains.
      return this._retain(op, "UNKNOWN_RECEIPT");
    }
    const state: AcceptedState = {
      status: "accepted",
      pointer: null,
      reason,
      ...(selection ? { missionSelection: selection } : {}),
    };
    this._state = state;
    this._tracked = null;
    return state;
  }

  /** Terminal refuse: clear exactly this operation's hint, then publish. */
  private async _clearRefused(
    op: TrackedOperation,
    reason: SafeReason,
  ): Promise<OperationState> {
    const cleared = await this._clearHint(op);
    if (this._stale(op.epoch, op.scope, op.generation)) return this._state;
    if (!cleared) {
      return this._retain(op, "UNKNOWN_RECEIPT");
    }
    const state: RefusedState = { status: "refused", pointer: null, reason };
    this._state = state;
    this._tracked = null;
    return state;
  }

  /** Non-terminal: publish an unknown and keep the pointer for recovery. */
  private _retain(op: TrackedOperation, reason: SafeReason): OperationState {
    const state: UnknownState = { status: "unknown", pointer: op.pointer, reason };
    this._state = state;
    this._tracked = null;
    return state;
  }

  /**
   * Atomic compareclear. A `false` return or rejection means the caller's
   * commit is unknown and the pointer remains in the store; the caller must
   * NOT publish a terminal state. Awaiting the store's commit before deciding
   * is what makes the in-flight slot stay joined through the clear attempt.
   */
  private async _clearHint(op: TrackedOperation): Promise<boolean> {
    if (this._stale(op.epoch, op.scope, op.generation)) return false;
    try {
      return (await this._store.clearIfEqual(
        op.scope,
        op.pointer,
        op.abort?.signal ?? undefined,
      )) === true;
    } catch {
      return false;
    }
  }

  private async _readStoredAsync(
    scope: string,
    signal?: AbortSignal,
  ): Promise<StoredRead> {
    let stored: unknown;
    try {
      stored = await this._store.read(scope, signal);
    } catch {
      // read unavailable / blocked / aborted / failed
      return { ok: false, reason: "LOCAL_UNAVAILABLE" };
    }
    if (stored === null) return { ok: true, pointer: null };
    return isValidPointer(stored)
      ? { ok: true, pointer: stored }
      : { ok: false, reason: "MALFORMED_POINTER" };
  }

  private async _reserveAsync(
    scope: string,
    pointer: OperationPointer,
    signal?: AbortSignal,
  ): Promise<ReserveOutcome> {
    let result: unknown;
    try {
      result = await this._store.reserve(scope, pointer, signal);
    } catch {
      return { ok: false, reason: "STORE_WRITE_FAILED" };
    }
    if (isPlainObject(result)) {
      const keys = Object.keys(result);
      if (result.reserved === true && keys.length === 1) return { ok: true, reserved: true };
      if (result.reserved === false && keys.length === 2 && isValidPointer(result.pointer)) {
        return { ok: true, reserved: false, pointer: result.pointer };
      }
    }
    return { ok: false, reason: "STORE_WRITE_FAILED" };
  }

  private _idle(reason: SafeReason): OperationState {
    const state: IdleState = { status: "idle", pointer: null, reason };
    this._state = state;
    return state;
  }

  /**
   * Before-effect local refusal for a caller that is not the in-flight
   * operation. Does not publish, does not mutate epoch/tracked/store/abort,
   * and does not expose the original pointer or selection.
   */
  private _busy(): RefusedState {
    return { status: "refused", pointer: null, reason: "OPERATION_BUSY" };
  }
}