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
 * A lookup hint only. The host implementation owns real persistence and
 * enrollment; this module never derives a storage backend from it and never
 * hands it a payload.
 */
export interface PendingPointerStore {
  read(principalScope: string): OperationPointer | null;
  write(principalScope: string, pointer: OperationPointer): void;
  clear(principalScope: string, pointer: OperationPointer): void;
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
  | "CLEARED"
  | "OWNER_ABSENT"
  | "INVALID_KIND"
  | "INVALID_TARGET"
  | "INVALID_PAYLOAD"
  | "MALFORMED_POINTER"
  | "KIND_MISMATCH"
  | "TARGET_MISMATCH"
  | "STORE_WRITE_FAILED"
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
  /** `OwnerContext.generation` captured at start. See dependency (1). */
  readonly generation: string;
  /** Controller-local epoch captured at start. */
  readonly epoch: number;
  readonly abort: AbortController | null;
}

type StoredRead =
  | { readonly ok: true; readonly pointer: OperationPointer | null }
  | { readonly ok: false };

export class OperationController {
  private _state: OperationState = {
    status: "idle",
    pointer: null,
    reason: "IDLE",
  };

  private _inflight: Promise<OperationState> | null = null;

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
   * Ordering matters: identity, then intent shape, then the in-flight join,
   * then the pending hint. A hint already held by the store for this scope
   * means an operation may already exist whose outcome is unknown, so no new
   * intent is submitted — the caller must `recover()` to resolve it.
   */
  async begin(intent: CommandIntent): Promise<OperationState> {
    const ctx = this._port.context();
    if (!ctx) return this._idle("OWNER_ABSENT");

    // Re-type as unknown so a rejected intent can still be inspected for the
    // most specific reason; the predicate above narrows `intent` to `never`.
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

    // Duplicate synchronous / racing begin joins the one in-flight operation.
    if (this._inflight) return this._inflight;

    const scope = ctx.principalScope;
    const stored = this._readStored(scope);
    if (!stored.ok) return this._idle("MALFORMED_POINTER");
    if (stored.pointer) {
      // Never submit over an unresolved operation. recover() resolves it.
      this._track(stored.pointer, scope, ctx.generation, this._epoch, null);
      const state: CheckingState = {
        status: "checking",
        pointer: stored.pointer,
        reason: "PENDING_POINTER",
      };
      this._state = state;
      return state;
    }

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

    // Store before submit: the hint exists before any effect can be requested.
    try {
      this._store.write(scope, pointer);
    } catch {
      return this._idle("STORE_WRITE_FAILED");
    }

    return this._submit(pointer, intent, scope, ctx.generation);
  }

  /**
   * Resolve the pending hint through `readOperation` only. Never submits.
   */
  async recover(): Promise<OperationState> {
    const ctx = this._port.context();
    if (!ctx) return this._idle("OWNER_ABSENT");

    if (this._inflight) return this._inflight;

    const scope = ctx.principalScope;
    const stored = this._readStored(scope);
    if (!stored.ok) return this._idle("MALFORMED_POINTER");
    if (!stored.pointer) return this._idle("RECOVER_NO_POINTER");

    const pointer = stored.pointer;
    const state: CheckingState = {
      status: "checking",
      pointer,
      reason: "CHECKING",
    };
    this._state = state;

    const abort = new AbortController();
    const op = this._track(pointer, scope, ctx.generation, this._epoch, abort);

    const run = async (): Promise<OperationState> => {
      try {
        const receipt = await this._port.readOperation(pointer, abort.signal);
        return this._applyReceipt(receipt, op);
      } catch {
        return this._applyFailure(op, "RECOVER_FAILED");
      } finally {
        this._releaseInflight(op.epoch);
      }
    };
    this._inflight = run();
    return this._inflight;
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
   * original-scope pointer stays so a later `begin()` cannot submit a second
   * effect — dropping the in-flight join is safe only because that hint remains.
   * Only `recover()` via `readOperation` may later clear the exact hint on a
   * terminal receipt. A sign-out that leaves `context()` null is the same:
   * the hint stays in its original scope.
   */
  invalidate(): void {
    const tracked = this._tracked;
    const hadVisibleOperation = this._state.status !== "idle" || tracked !== null;

    // Bump epoch before abort so a synchronous rejection cannot publish.
    this._epoch++;
    if (this._inflight) {
      tracked?.abort?.abort();
      this._inflight = null;
    }
    this._tracked = null;

    if (!hadVisibleOperation) return;

    this._state = { status: "idle", pointer: null, reason: "CLEARED" };
  }

  // ── internals ───────────────────────────────────────────────────────────────

  private _submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    scope: string,
    generation: string,
  ): Promise<OperationState> {
    const epoch = ++this._epoch;
    const abort = new AbortController();
    const op = this._track(pointer, scope, generation, epoch, abort);
    this._state = { status: "submitting", pointer, reason: "SUBMITTING" };

    const run = async (): Promise<OperationState> => {
      try {
        const receipt = await this._port.submit(pointer, intent, abort.signal);
        return this._applyReceipt(receipt, op);
      } catch {
        return this._applyFailure(op, "TRANSPORT_ERROR");
      } finally {
        this._releaseInflight(epoch);
      }
    };
    this._inflight = run();
    return this._inflight;
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

  private _releaseInflight(epoch: number): void {
    if (this._epoch === epoch) this._inflight = null;
  }

  /** A receipt arrived for `op`. Decide first whether it may be published. */
  private _applyReceipt(
    receipt: unknown,
    op: TrackedOperation,
  ): OperationState {
    const gated = this._gate(op);
    return gated ?? this._decide(receipt, op);
  }

  /**
   * The request failed rather than returning. Same gate as a receipt: a
   * request aborted by `invalidate()`, or one whose authentication epoch has
   * moved on, must not publish over whatever the UI is showing now.
   */
  private _applyFailure(op: TrackedOperation, reason: SafeReason): OperationState {
    const gated = this._gate(op);
    return gated ?? this._retain(op, reason);
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
  private _gate(op: TrackedOperation): OperationState | null {
    if (this._epoch !== op.epoch) return this._state;

    const ctx = this._port.context();
    if (
      !ctx ||
      ctx.principalScope !== op.scope ||
      ctx.generation !== op.generation
    ) {
      return this._suppressStale(op);
    }
    return null;
  }

  /**
   * Suppress a stale result and keep the hint in its original scope.
   *
   * An authentication epoch change does not cancel the operation and is never
   * reported as one: the pointer stays so a later `recover()` can still
   * resolve it under the new epoch.
   */
  private _suppressStale(op: TrackedOperation): OperationState {
    return this._retain(op, "EPOCH_CHANGED");
  }

  private _decide(receipt: unknown, op: TrackedOperation): OperationState {
    if (!isValidReceipt(receipt)) return this._retain(op, "MALFORMED_RECEIPT");

    // The receipt must describe exactly the operation this controller issued.
    if (receipt.operationKey !== op.pointer.operationKey) {
      return this._retain(op, "RECEIPT_MISMATCH");
    }
    if (receipt.kind !== op.pointer.kind) return this._retain(op, "KIND_MISMATCH");
    if (receipt.targetKey !== op.pointer.targetKey) {
      return this._retain(op, "TARGET_MISMATCH");
    }

    // Only an accepted launch receipt may carry a selection. A message or a
    // stop can never replace the selected root, and a refused or unknown
    // receipt never carries one. Such a receipt is not evidence of anything,
    // so hold the pointer rather than adopting the selection or declaring a
    // terminal state.
    if (receipt.missionSelection !== undefined) {
      if (receipt.kind !== "launch" || receipt.disposition !== "accepted") {
        return this._retain(op, "SELECTION_NOT_ALLOWED");
      }
      const decoded = normalizeSelection(receipt.missionSelection);
      if (!decoded) return this._retain(op, "SELECTION_INVALID");
      return this._clearAccepted(op, "ACCEPTED", decoded);
    }

    // An accepted launch is the effect that changes the selection, so it may
    // only be published as accepted when it carried a selection that decoded
    // above. With the selection absent, the outcome is not known to this
    // client: the producer may have accepted the launch even though the root
    // cannot be decoded here. That is never a refusal — hold the exact
    // pointer so a later recover() can re-read the operation.
    if (receipt.kind === "launch" && receipt.disposition === "accepted") {
      return this._retain(op, "SELECTION_INVALID");
    }

    switch (receipt.disposition) {
      case "accepted":
        return this._clearAccepted(op, "ACCEPTED");
      case "refused":
        return this._clearRefused(op, "REFUSED");
      default:
        // Explicit unknown: the outcome is not known, so the pointer stays.
        return this._retain(op, "UNKNOWN_RECEIPT");
    }
  }

  /** Terminal accept: publish and clear exactly this operation's hint. */
  private _clearAccepted(
    op: TrackedOperation,
    reason: SafeReason,
    selection?: MissionSelection,
  ): OperationState {
    this._clearHint(op);
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

  /** Terminal refuse: publish and clear exactly this operation's hint. */
  private _clearRefused(op: TrackedOperation, reason: SafeReason): OperationState {
    this._clearHint(op);
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

  private _clearHint(op: TrackedOperation): void {
    try {
      this._store.clear(op.scope, op.pointer);
    } catch {
      // Best effort; the hint may survive and be cleared by a later recover().
    }
  }

  private _readStored(scope: string): StoredRead {
    let stored: unknown;
    try {
      stored = this._store.read(scope);
    } catch {
      return { ok: false };
    }
    if (stored === null) return { ok: true, pointer: null };
    return isValidPointer(stored)
      ? { ok: true, pointer: stored }
      : { ok: false };
  }

  private _idle(reason: SafeReason): OperationState {
    const state: IdleState = { status: "idle", pointer: null, reason };
    this._state = state;
    return state;
  }
}
