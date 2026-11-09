/**
 * Attended fresh-conversation binding over the incumbent controller/store.
 *
 * Fixed finite command port for the two attended conversation effect kinds
 * (`conversation_consume`, `conversation_turn`) of P16.T1.S34.S1, composed
 * over the actual incumbent {@link OperationController} and its durable
 * {@link PendingPointerStore}. This module owns no state machine, no store,
 * no cache, no registry, no Host/App/runtime surface and no native effect:
 * the injected controller alone reads, reserves and clears the pending
 * pointer, and the port below alone decides which receipt the UI may see.
 * The parent caller owns the mounted hook, acceptance and the UI gesture
 * latch; it captures the once-minted turn request across the pure preflight.
 *
 * Wires:
 *  - `consume` is an effect. It reaches the transport exclusively through
 *    `controller.begin(makeConsumeIntent(read))`, which durably reserves the
 *    scope before submitting and clears the exact pointer only on a terminal
 *    receipt. The local `mmos-conversation-consume-…` key is ordinary client
 *    correlation only — never a wire field and never the wire consume key.
 *  - `turn` is an effect. {@link FreshConversationAttendedBinding.makeTurnRequest}
 *    mints the turn key once for the exact message/digest/selector (no
 *    preview yet); {@link FreshConversationAttendedBinding.previewTurn} calls
 *    ONLY the pure `turnPreview` with that same key (zero store writes, zero
 *    turn calls) and decodes the separate TURN_READY preview;
 *    {@link FreshConversationAttendedBinding.makeTurnIntent} binds the actual
 *    preview digest to the same key/message/digest/read witness without
 *    reminting. Only `controller.begin(makeTurnIntent(prepared))` may call
 *    the transport `turn`.
 *  - `consume_status`/`turn_status`/`turn_read` are observations of the
 *    ORIGINAL operation. Recovery always belongs to the controller's retained
 *    pointer via `readOperation`; no new key is minted, nothing is prepared,
 *    reserved, submitted or source-reconciled on a read.
 *
 * Privacy and authority:
 *  - `CommandIntent.payload` carries the ephemeral owner snapshot, the local
 *    key, the detached wire request and the host read witness. It is never
 *    transmitted and never persisted; the transport receives only the closed
 *    wire request. `read.current()`, the sealed result and the locator are
 *    witnesses and DATA, never authority: the backend remains the authorizer.
 *  - Issued requests, owner snapshots and preview scalars are captured and
 *    detached when minted, so later caller mutation cannot alter an original.
 *  - Raw five-field responses are returned verbatim; decoding belongs to the
 *    parent. Producer messages and thrown text are never surfaced.
 */

import {
  OperationController,
  type CommandIntent,
  type EffectReceipt,
  type FiniteCommandPort,
  type OperationKind,
  type OperationPointer,
  type OwnerContext,
  type PendingPointerStore,
} from "../../orchestration/operation-controller";
import {
  freshConversationOriginalSelector,
  freshConversationTarget,
  mintFreshConversationCommandKey,
  parseFreshConversationTarget,
  type FreshConversationOriginalSelector,
} from "../../orchestration/fresh-conversation-target";
import {
  decodeFreshConversationTurnPreviewResult,
  decodeFreshConversationTurnResult,
  validateFreshConversationReference,
  validateFreshConversationTurnRequest,
  type FreshConversationReference as FreshConversationTurnReference,
  type FreshConversationTurnLocator,
  type FreshConversationTurnPreviewData,
  type FreshConversationTurnRequest,
} from "./fresh-conversation-turn";
import {
  decodeFreshConversationInitialResult,
  type FreshConversationPayload,
} from "./fresh-conversation";

// ── Public contract ──────────────────────────────────────────────────────────

/** Host-issued witness for the current sealed initial read of an original. */
export interface FreshConversationOriginalRead {
  readonly selection: FreshConversationOriginalSelector;
  /** Producer-sealed initial result, re-verified against the actual locator. */
  readonly result: FreshConversationPayload;
  readonly locator: FreshConversationTurnLocator;
  /** Issued current witness; a false answer withholds new actions. */
  current(): boolean;
}

/** External transport seam. Every response stays an opaque raw envelope. */
export interface FreshConversationAttendedTransport {
  consume(request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown>;
  consumeStatus(request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown>;
  turnPreview(request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown>;
  turn(request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown>;
  turnStatus(request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown>;
  turnRead(request: FreshConversationTurnRequest, signal: AbortSignal): Promise<unknown>;
}

export interface FreshConversationAttendedBindingOptions {
  /** Live UI owner snapshot seam; snapshots are taken through this only. */
  readonly owner: () => OwnerContext | null;
  /**
   * Current Workspace availability/precondition for a NEW consume or turn.
   * Never a grant, never consulted for an original status/read.
   */
  readonly canModify: () => boolean;
  readonly transport: FreshConversationAttendedTransport;
  /** The incumbent durable store; only the controller writes through it. */
  readonly store: PendingPointerStore;
  /**
   * Existing original-initial reader. Recovery and readbacks reacquire the
   * sealed initial response and its issued current witness through this only;
   * this binding never manufactures a context or a digest.
   */
  readonly readInitial: (
    selection: FreshConversationOriginalSelector,
    signal: AbortSignal,
  ) => Promise<FreshConversationOriginalRead | null>;
}

/** Captured, privilege-free preflight result for one attended turn. */
export interface PreparedFreshConversationTurn {
  /** Exactly the once-minted request; the intent never remints. */
  readonly request: FreshConversationTurnRequest;
  /** Actually decoded TURN_READY preview of the separate pure branch. */
  readonly preview: FreshConversationTurnPreviewData;
  /** Owner snapshot captured at preflight; compared, never an authority. */
  readonly owner: OwnerContext;
  /** Actual host read witness the request was minted against. */
  readonly witness: FreshConversationOriginalRead;
}

export interface FreshConversationAttendedBinding {
  readonly controller: OperationController;
  readonly store: PendingPointerStore;
  context(): OwnerContext | null;
  /** Synchronous, effect-free. Mints the local key ONCE and binds digest/selector. */
  makeConsumeIntent(read: FreshConversationOriginalRead): CommandIntent | null;
  /** Mints the turn key ONCE for the exact message + digest + selector. */
  makeTurnRequest(read: FreshConversationOriginalRead, message: string): FreshConversationTurnRequest | null;
  /** Pure turnPreview only: zero store writes, zero turn calls, no minting. */
  previewTurn(
    read: FreshConversationOriginalRead,
    request: FreshConversationTurnRequest,
    signal: AbortSignal,
  ): Promise<PreparedFreshConversationTurn | null>;
  /** Binds the actual preview digest; no remint, no second key. */
  makeTurnIntent(prepared: PreparedFreshConversationTurn): CommandIntent | null;
  /** Readonly current-initial-read + consumeStatus; returns the raw frame. */
  readOriginalConsume(
    selection: FreshConversationOriginalSelector,
    signal: AbortSignal,
  ): Promise<unknown>;
  /** Readonly turnRead of the exact original turn key; returns the raw frame. */
  readOriginalTurn(
    selection: FreshConversationOriginalSelector,
    turnKey: string,
    signal: AbortSignal,
  ): Promise<unknown>;
}

// ── Fixed local vocabulary ───────────────────────────────────────────────────

const CONSUME_KIND: OperationKind = "conversation_consume";
const TURN_KIND: OperationKind = "conversation_turn";

/** Ordinary client correlation keys only; minted by the shared 11af helper. */
const CONSUME_KEY_PATTERN = /^mmos-conversation-consume-[0-9a-f]{40}$/;
const TURN_KEY_PATTERN = /^mmos-conversation-turn-[0-9a-f]{40}$/;

/**
 * Known public pre-effect producer codes that may close a submit as refused.
 * Everything else — effect_unknown, any unknown future code, a malformed
 * error frame, a foreign or undecodable envelope, or a thrown transport — is
 * unknown and retains the pointer. Classification never reads message text.
 */
const REFUSAL_CODES: ReadonlySet<string> = new Set([
  "refused",
  "invalid_input",
  "authentication_required",
  "conversation_unavailable",
]);

const ACCEPTED_REASON = "ACCEPTED";
const UNKNOWN_REASON = "UNKNOWN_RECEIPT";

/** Fixed marker thrown for every closed local refusal. No detail, ever. */
export const FRESH_CONVERSATION_ATTENDED_CLOSED = "FRESH_CONVERSATION_ATTENDED_CLOSED";

function closedError(): Error {
  return new Error(FRESH_CONVERSATION_ATTENDED_CLOSED);
}

function receipt(
  pointer: OperationPointer,
  disposition: EffectReceipt["disposition"],
  reason: string,
): EffectReceipt {
  // Always the verbatim original pointer: same key, same kind, same target.
  return {
    operationKey: pointer.operationKey,
    kind: pointer.kind,
    targetKey: pointer.targetKey,
    disposition,
    reason,
  };
}

function unknownReceipt(pointer: OperationPointer): EffectReceipt {
  return receipt(pointer, "unknown", UNKNOWN_REASON);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isOwnerContext(value: unknown): value is OwnerContext {
  if (!isPlainObject(value) || Object.keys(value).length !== 2) return false;
  return (
    typeof value.principalScope === "string" &&
    value.principalScope.length > 0 &&
    typeof value.generation === "string" &&
    value.generation.length > 0
  );
}

/** Detached two-field owner snapshot; never aliased to a live seam result. */
function captureOwner(owner: OwnerContext): OwnerContext {
  return Object.freeze({
    principalScope: owner.principalScope,
    generation: owner.generation,
  });
}

/** A view identity comparison, never authentication or a derived permission. */
function sameOwner(a: OwnerContext | null, b: OwnerContext | null): boolean {
  return (
    a !== null &&
    b !== null &&
    a.principalScope === b.principalScope &&
    a.generation === b.generation
  );
}

function isOriginalRead(value: unknown): value is FreshConversationOriginalRead {
  if (!isPlainObject(value) || Object.keys(value).length !== 4) return false;
  if (
    !Object.hasOwn(value, "selection") ||
    !Object.hasOwn(value, "result") ||
    !Object.hasOwn(value, "locator") ||
    !Object.hasOwn(value, "current")
  ) {
    return false;
  }
  const read = value as unknown as FreshConversationOriginalRead;
  if (typeof read.current !== "function") return false;
  if (freshConversationOriginalSelector(read.selection) === null) return false;
  if (!isPlainObject(read.locator) || Object.keys(read.locator).length !== 4) return false;
  if (!isPlainObject(read.result) || Object.keys(read.result).length !== 2) return false;
  return true;
}

/**
 * Strict shared sealed-result/locator proof bound to the same original
 * selector and the actual work/root. Returns the verified initial digest.
 */
function witnessDigest(read: FreshConversationOriginalRead): string | null {
  const selector = freshConversationOriginalSelector(read.selection);
  if (selector === null || selector.work_ref !== read.locator.work_ref) return null;
  if ("reference" in selector && selector.reference.root_job_id !== read.locator.root_job_id) {
    return null;
  }
  const sealed = decodeFreshConversationInitialResult(read.result, {
    job_id: read.locator.job_id,
    attempt_id: read.locator.attempt_id,
    root_job_id: read.locator.root_job_id,
  });
  if (sealed === null || sealed.digest !== read.result.digest) return null;
  return sealed.digest;
}

/** Detached selector base for a wire request, or null when foreign. */
function selectorRequestBase(
  selector: FreshConversationOriginalSelector,
):
  | { readonly work_ref: string; readonly reference: FreshConversationTurnReference }
  | { readonly work_ref: string; readonly operation_key: string }
  | null {
  if ("reference" in selector) {
    const reference = validateFreshConversationReference(selector.reference);
    if (reference === null || reference.work_ref !== selector.work_ref) return null;
    return { work_ref: selector.work_ref, reference };
  }
  return { work_ref: selector.work_ref, operation_key: selector.operation_key };
}

/** The exact original selector a wire request was built from, or null. */
function selectorFromRequest(
  request: FreshConversationTurnRequest,
): FreshConversationOriginalSelector | null {
  if ("reference" in request) {
    return freshConversationOriginalSelector({
      work_ref: request.work_ref,
      reference: request.reference,
    });
  }
  if ("operation_key" in request) {
    return freshConversationOriginalSelector({
      work_ref: request.work_ref,
      operation_key: request.operation_key,
    });
  }
  return null;
}

function detachReference(
  reference: FreshConversationTurnReference,
): FreshConversationTurnReference {
  return Object.freeze({
    schema: reference.schema,
    work_ref: reference.work_ref,
    root_job_id: reference.root_job_id,
    root_event_id: reference.root_event_id,
    root_event_sha256: reference.root_event_sha256,
    principal_scope_sha256: reference.principal_scope_sha256,
  });
}

/** Fresh detached closed-union copy; later caller mutation cannot alter it. */
function detachRequest(request: FreshConversationTurnRequest): FreshConversationTurnRequest {
  const workRef = request.work_ref;
  if ("reference" in request) {
    const reference = detachReference(request.reference);
    if ("message" in request) {
      const base = {
        work_ref: workRef,
        reference,
        initial_digest: request.initial_digest,
        message: request.message,
        turn_key: request.turn_key,
      };
      return Object.freeze(
        "preview_digest" in request ? { ...base, preview_digest: request.preview_digest } : base,
      );
    }
    if ("initial_digest" in request) {
      return Object.freeze({ work_ref: workRef, reference, initial_digest: request.initial_digest });
    }
    return Object.freeze({ work_ref: workRef, reference, turn_key: request.turn_key });
  }
  const operationKey = request.operation_key;
  if ("message" in request) {
    const base = {
      work_ref: workRef,
      operation_key: operationKey,
      initial_digest: request.initial_digest,
      message: request.message,
      turn_key: request.turn_key,
    };
    return Object.freeze(
      "preview_digest" in request ? { ...base, preview_digest: request.preview_digest } : base,
    );
  }
  if ("initial_digest" in request) {
    return Object.freeze({
      work_ref: workRef,
      operation_key: operationKey,
      initial_digest: request.initial_digest,
    });
  }
  return Object.freeze({ work_ref: workRef, operation_key: operationKey, turn_key: request.turn_key });
}

function consumeStatusRequest(
  selector: FreshConversationOriginalSelector,
  digest: string,
): FreshConversationTurnRequest | null {
  const base = selectorRequestBase(selector);
  if (base === null) return null;
  return validateFreshConversationTurnRequest({ ...base, initial_digest: digest }, "consume_status");
}

function turnKeyRequest(
  selector: FreshConversationOriginalSelector,
  turnKey: string,
  operation: "turn_status" | "turn_read",
): FreshConversationTurnRequest | null {
  const base = selectorRequestBase(selector);
  if (base === null) return null;
  return validateFreshConversationTurnRequest({ ...base, turn_key: turnKey }, operation);
}

// ── Intent payload (ephemeral; never transmitted, never persisted) ───────────

interface AttendedPayload {
  /** Detached frozen closed wire request. */
  readonly request: FreshConversationTurnRequest;
  /** Detached owner snapshot captured at mint. */
  readonly owner: OwnerContext;
  /** Local correlation key; for turn it is also the wire turn_key. */
  readonly key: string;
  /** Actual host read witness the action was minted against. */
  readonly witness: FreshConversationOriginalRead;
}

/**
 * Re-derive everything from the intent alone. Validates kind, payload shape,
 * owner snapshot, the per-kind local key prefix, the exact wire request
 * grammar, the canonical selector-only targetKey and the witness binding.
 */
function intentPayload(intent: CommandIntent): AttendedPayload | null {
  if (intent.kind !== CONSUME_KIND && intent.kind !== TURN_KIND) return null;
  if (typeof intent.targetKey !== "string" || intent.targetKey.length === 0) return null;
  const payload: unknown = intent.payload;
  if (!isPlainObject(payload) || Object.keys(payload).length !== 4) return null;
  if (
    !Object.hasOwn(payload, "request") ||
    !Object.hasOwn(payload, "owner") ||
    !Object.hasOwn(payload, "key") ||
    !Object.hasOwn(payload, "witness")
  ) {
    return null;
  }
  const owner = payload.owner;
  if (!isOwnerContext(owner)) return null;
  const key = payload.key;
  if (typeof key !== "string") return null;
  if (intent.kind === CONSUME_KIND ? !CONSUME_KEY_PATTERN.test(key) : !TURN_KEY_PATTERN.test(key)) {
    return null;
  }
  const witness: unknown = payload.witness;
  if (!isOriginalRead(witness)) return null;
  const request = validateFreshConversationTurnRequest(
    payload.request,
    intent.kind === CONSUME_KIND ? "consume" : "turn",
  );
  if (request === null) return null;
  if (requestTurnKey(request) !== null && requestTurnKey(request) !== key) return null;
  const selector = selectorFromRequest(request);
  if (selector === null || freshConversationTarget(selector) !== intent.targetKey) return null;
  if (freshConversationTarget(witness.selection) !== intent.targetKey) return null;
  return {
    request: detachRequest(request),
    owner: captureOwner(owner),
    key,
    witness,
  };
}

// ── The injected port ────────────────────────────────────────────────────────

/**
 * The finite command port over the two attended conversation kinds.
 * `prepare`/`submit`/`readOperation` re-derive everything from the intent and
 * the pointer alone; nothing is cached between calls and the owner is re-read
 * through the host seam on every fence. No `reconcileOperation` and no
 * `advanceOperation` exist here: source reconciliation never applies to these
 * kinds, and default recovery always stays on {@link readOperation}.
 */
class FreshConversationAttendedCommandPort implements FiniteCommandPort {
  constructor(private readonly _options: FreshConversationAttendedBindingOptions) {}

  context(): OwnerContext | null {
    return this._options.owner();
  }

  /** Synchronous and effect-free; a contract failure throws. */
  prepare(intent: CommandIntent): OperationPointer {
    const payload = intentPayload(intent);
    if (payload === null) throw closedError();
    const live = this._options.owner();
    if (live === null || !sameOwner(live, payload.owner)) throw closedError();
    return {
      operationKey: payload.key,
      kind: intent.kind,
      targetKey: intent.targetKey,
    };
  }

  /**
   * The single effect path for both kinds. Fences the captured owner, the
   * Workspace availability and the read witness before and after the await,
   * calls the transport exactly once with the closed wire, and classifies
   * only the decoded outcome. A loss across the await stays conservatively
   * unknown: it withholds the private view and retains the pointer.
   */
  async submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    const payload = intentPayload(intent);
    if (
      payload === null ||
      pointer.kind !== intent.kind ||
      pointer.operationKey !== payload.key ||
      pointer.targetKey !== intent.targetKey
    ) {
      return unknownReceipt(pointer);
    }
    const isConsume = intent.kind === CONSUME_KIND;
    const before = this._options.owner();
    const witnessCurrent = payload.witness.current() === true;
    const witnessBound = witnessDigest(payload.witness) === requestDigest(payload.request);
    if (
      before === null ||
      !sameOwner(before, payload.owner) ||
      this._options.canModify() !== true ||
      !witnessCurrent ||
      !witnessBound
    ) {
      return unknownReceipt(pointer);
    }
    const transport = this._options.transport;
    let raw: unknown;
    try {
      raw = isConsume
        ? await transport.consume(payload.request, signal)
        : await transport.turn(payload.request, signal);
    } catch {
      // Thrown transport: the effect is unknown, never refused, never cleared.
      return unknownReceipt(pointer);
    }
    const after = this._options.owner();
    if (
      after === null ||
      !sameOwner(after, before) ||
      this._options.canModify() !== true ||
      payload.witness.current() !== true
    ) {
      return unknownReceipt(pointer);
    }
    return classifyEffect(raw, isConsume ? "consume" : "turn", payload.request, pointer);
  }

  /**
   * Observation of the ORIGINAL operation only. Recovery never calls consume,
   * turn, preview, mint, prepare or source reconciliation, and never consults
   * the Workspace availability: a withdrawn Workspace still reads the
   * original status. Consume reacquires the actual sealed initial response
   * and its issued current witness through the existing reader first; turn
   * needs no initial digest — the stored key IS the turn key.
   */
  async readOperation(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (pointer.kind === CONSUME_KIND) return this._readConsume(pointer, signal);
    if (pointer.kind === TURN_KIND) return this._readTurn(pointer, signal);
    return unknownReceipt(pointer);
  }

  private async _readConsume(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (
      typeof pointer.operationKey !== "string" ||
      !CONSUME_KEY_PATTERN.test(pointer.operationKey)
    ) {
      return unknownReceipt(pointer);
    }
    const selector =
      typeof pointer.targetKey === "string"
        ? parseFreshConversationTarget(pointer.targetKey)
        : null;
    if (selector === null) return unknownReceipt(pointer);
    const ownerBefore = this._options.owner();
    if (ownerBefore === null) return unknownReceipt(pointer);
    let read: FreshConversationOriginalRead | null;
    try {
      read = await this._options.readInitial(selector, signal);
    } catch {
      return unknownReceipt(pointer);
    }
    if (read === null || read.current() !== true ||
        freshConversationTarget(read.selection) !== pointer.targetKey) return unknownReceipt(pointer);
    const digest = witnessDigest(read);
    if (digest === null) return unknownReceipt(pointer);
    const ownerAfter = this._options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) {
      return unknownReceipt(pointer);
    }
    const request = consumeStatusRequest(selector, digest);
    if (request === null) return unknownReceipt(pointer);
    let raw: unknown;
    try {
      raw = await this._options.transport.consumeStatus(request, signal);
    } catch {
      return unknownReceipt(pointer);
    }
    const ownerFinal = this._options.owner();
    if (ownerFinal === null || !sameOwner(ownerFinal, ownerBefore)) {
      return unknownReceipt(pointer);
    }
    const decoded = decodeFreshConversationTurnResult(raw, "consume_status", request);
    if (decoded === null || !decoded.ok) {
      // ABSENT and every producer error are holds, never pre-effect clearance.
      return unknownReceipt(pointer);
    }
    if (
      decoded.data.state === "CONSUMED" &&
      decoded.data.effect !== "UNKNOWN" &&
      decoded.data.initial_consumption !== null
    ) {
      return receipt(pointer, "accepted", ACCEPTED_REASON);
    }
    return unknownReceipt(pointer);
  }

  private async _readTurn(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (typeof pointer.operationKey !== "string" || !TURN_KEY_PATTERN.test(pointer.operationKey)) {
      return unknownReceipt(pointer);
    }
    const selector =
      typeof pointer.targetKey === "string"
        ? parseFreshConversationTarget(pointer.targetKey)
        : null;
    if (selector === null) return unknownReceipt(pointer);
    const request = turnKeyRequest(selector, pointer.operationKey, "turn_status");
    if (request === null) return unknownReceipt(pointer);
    const ownerBefore = this._options.owner();
    if (ownerBefore === null) return unknownReceipt(pointer);
    let raw: unknown;
    try {
      raw = await this._options.transport.turnStatus(request, signal);
    } catch {
      return unknownReceipt(pointer);
    }
    const ownerAfter = this._options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) {
      return unknownReceipt(pointer);
    }
    const decoded = decodeFreshConversationTurnResult(raw, "turn_status", request);
    if (decoded === null || !decoded.ok) {
      return unknownReceipt(pointer);
    }
    if (
      decoded.data.state === "RECORDED" &&
      decoded.data.effect !== "UNKNOWN" &&
      decoded.data.initial_consumption !== null
    ) {
      return receipt(pointer, "accepted", ACCEPTED_REASON);
    }
    return unknownReceipt(pointer);
  }
}

/** The request's initial digest; consume/turn requests always carry one. */
function requestDigest(request: FreshConversationTurnRequest): string | null {
  return "initial_digest" in request ? request.initial_digest : null;
}

/** The wire turn_key, when this closed request carries one (turn-shaped only). */
function requestTurnKey(request: FreshConversationTurnRequest): string | null {
  return "turn_key" in request ? request.turn_key : null;
}

/** Receipt mapping for the two effect kinds; shared by the submit path. */
function classifyEffect(
  raw: unknown,
  operation: "consume" | "turn",
  request: FreshConversationTurnRequest,
  pointer: OperationPointer,
): EffectReceipt {
  const decoded = decodeFreshConversationTurnResult(raw, operation, request);
  if (decoded === null) return unknownReceipt(pointer);
  if (!decoded.ok) {
    return REFUSAL_CODES.has(decoded.error.code)
      ? receipt(pointer, "refused", decoded.error.code)
      : unknownReceipt(pointer);
  }
  const data = decoded.data;
  const consumed = operation === "consume" ? data.state === "CONSUMED" : data.state === "RECORDED";
  if (consumed && data.effect !== "UNKNOWN" && data.initial_consumption !== null) {
    return receipt(pointer, "accepted", ACCEPTED_REASON);
  }
  return unknownReceipt(pointer);
}

// ── The binding ──────────────────────────────────────────────────────────────

/**
 * Build the binding over the incumbent controller and store. No other module
 * state is created; every call below re-reads the host seams.
 */
export function createFreshConversationAttendedBinding(
  options: FreshConversationAttendedBindingOptions,
): FreshConversationAttendedBinding {
  const port = new FreshConversationAttendedCommandPort(options);
  const controller = new OperationController(port, options.store);

  /** New-action gate: issued current witness + live owner + Workspace. */
  function actionGate(read: FreshConversationOriginalRead): OwnerContext | null {
    if (!isOriginalRead(read) || read.current() !== true) return null;
    if (freshConversationTarget(read.selection) === null) return null;
    const owner = options.owner();
    if (owner === null || options.canModify() !== true) return null;
    return owner;
  }

  function makeConsumeIntent(read: FreshConversationOriginalRead): CommandIntent | null {
    const owner = actionGate(read);
    if (owner === null) return null;
    const digest = witnessDigest(read);
    if (digest === null) return null;
    const base = selectorRequestBase(read.selection);
    if (base === null) return null;
    const key = mintFreshConversationCommandKey("conversation_consume");
    if (key === null || !CONSUME_KEY_PATTERN.test(key)) return null;
    const request = validateFreshConversationTurnRequest(
      { ...base, initial_digest: digest },
      "consume",
    );
    if (request === null) return null;
    return {
      kind: CONSUME_KIND,
      targetKey: freshConversationTarget(read.selection),
      payload: {
        request: detachRequest(request),
        owner: captureOwner(owner),
        key,
        witness: read,
      },
    };
  }

  function makeTurnRequest(
    read: FreshConversationOriginalRead,
    message: string,
  ): FreshConversationTurnRequest | null {
    const owner = actionGate(read);
    if (owner === null) return null;
    const digest = witnessDigest(read);
    if (digest === null) return null;
    const base = selectorRequestBase(read.selection);
    if (base === null) return null;
    const key = mintFreshConversationCommandKey("conversation_turn");
    if (key === null || !TURN_KEY_PATTERN.test(key)) return null;
    // Exact message, actual digest, minted key; no preview digest yet.
    const request = validateFreshConversationTurnRequest(
      { ...base, initial_digest: digest, message, turn_key: key },
      "turn",
    );
    if (request === null || requestTurnKey(request) !== key) return null;
    return detachRequest(request);
  }

  async function previewTurn(
    read: FreshConversationOriginalRead,
    request: FreshConversationTurnRequest,
    signal: AbortSignal,
  ): Promise<PreparedFreshConversationTurn | null> {
    if (!isOriginalRead(read)) return null;
    const targetKey = freshConversationTarget(read.selection);
    if (targetKey === null) return null;
    // The separate pure branch validates the turn-shaped request with its
    // own operation; the request is never submitted through it.
    const validated = validateFreshConversationTurnRequest(request, "turn_preview");
    if (validated === null) return null;
    const validatedTurnKey = requestTurnKey(validated);
    if (validatedTurnKey === null || !TURN_KEY_PATTERN.test(validatedTurnKey)) return null;
    const requestSelector = selectorFromRequest(validated);
    if (requestSelector === null || freshConversationTarget(requestSelector) !== targetKey) {
      return null;
    }
    const digest = witnessDigest(read);
    if (digest === null || requestDigest(validated) !== digest) return null;
    if (read.current() !== true) return null;
    const owner = options.owner();
    if (owner === null || options.canModify() !== true) return null;
    let raw: unknown;
    try {
      raw = await options.transport.turnPreview(detachRequest(validated), signal);
    } catch {
      return null;
    }
    const after = options.owner();
    if (
      after === null ||
      !sameOwner(after, owner) ||
      options.canModify() !== true ||
      read.current() !== true
    ) {
      return null;
    }
    const decoded = decodeFreshConversationTurnPreviewResult(raw, validated);
    if (decoded === null || !decoded.ok) return null;
    const preview = decoded.data;
    if (
      preview.state !== "TURN_READY" ||
      preview.effect !== "NONE" ||
      preview.turn_key !== validatedTurnKey
    ) {
      return null;
    }
    return {
      request: detachRequest(validated),
      preview,
      owner: captureOwner(owner),
      witness: read,
    };
  }

  function makeTurnIntent(prepared: PreparedFreshConversationTurn): CommandIntent | null {
    if (!isPlainObject(prepared) || Object.keys(prepared).length !== 4) return null;
    if (
      !Object.hasOwn(prepared, "request") ||
      !Object.hasOwn(prepared, "preview") ||
      !Object.hasOwn(prepared, "owner") ||
      !Object.hasOwn(prepared, "witness")
    ) {
      return null;
    }
    if (!isOwnerContext(prepared.owner) || !isOriginalRead(prepared.witness)) return null;
    const preview: unknown = prepared.preview;
    if (!isPlainObject(preview)) return null;
    const base = validateFreshConversationTurnRequest(prepared.request, "turn");
    if (base === null) return null;
    const baseTurnKey = requestTurnKey(base);
    if (baseTurnKey === null || !TURN_KEY_PATTERN.test(baseTurnKey)) return null;
    if (
      preview.state !== "TURN_READY" ||
      preview.effect !== "NONE" ||
      preview.turn_key !== baseTurnKey ||
      preview.work_ref !== base.work_ref
    ) {
      return null;
    }
    // The preview must bind the same exact selector/message/digest/key.
    if (
      (typeof preview.operation_key === "string") !== ("operation_key" in base) ||
      (typeof preview.operation_key === "string" &&
        ("operation_key" in base ? preview.operation_key !== base.operation_key : true))
    ) {
      return null;
    }
    if (!isPlainObject(preview.initial_consumption)) return null;
    if (preview.initial_consumption.initial_digest !== requestDigest(base)) return null;
    if ("reference" in base) {
      const wire = validateFreshConversationReference(preview.reference);
      if (
        wire === null ||
        wire.work_ref !== base.reference.work_ref ||
        wire.root_job_id !== base.reference.root_job_id ||
        wire.root_event_id !== base.reference.root_event_id ||
        wire.root_event_sha256 !== base.reference.root_event_sha256 ||
        wire.principal_scope_sha256 !== base.reference.principal_scope_sha256
      ) {
        return null;
      }
    }
    // Same original witness: current, bound to this selector and digest.
    const witness = prepared.witness;
    if (witness.current() !== true) return null;
    const digest = witnessDigest(witness);
    if (digest === null || digest !== requestDigest(base)) return null;
    const targetKey = freshConversationTarget(witness.selection);
    const requestSelector = selectorFromRequest(base);
    if (targetKey === null || requestSelector === null || freshConversationTarget(requestSelector) !== targetKey) {
      return null;
    }
    // The live owner must still be the captured one and Workspace available.
    const owner = options.owner();
    if (owner === null || options.canModify() !== true) return null;
    if (!sameOwner(owner, prepared.owner)) return null;
    // Same exact original key and actual preview digest; never a remint.
    const request = validateFreshConversationTurnRequest(
      { ...base, preview_digest: preview.preview_digest },
      "turn",
    );
    if (request === null || requestTurnKey(request) !== baseTurnKey) return null;
    return {
      kind: TURN_KIND,
      targetKey,
      payload: {
        request: detachRequest(request),
        owner: captureOwner(owner),
        key: baseTurnKey,
        witness,
      },
    };
  }

  async function readOriginalConsume(
    selection: FreshConversationOriginalSelector,
    signal: AbortSignal,
  ): Promise<unknown> {
    const selector = freshConversationOriginalSelector(selection);
    if (selector === null || freshConversationTarget(selector) === null) throw closedError();
    const ownerBefore = options.owner();
    if (ownerBefore === null) throw closedError();
    let read: FreshConversationOriginalRead | null;
    try {
      read = await options.readInitial(selector, signal);
    } catch {
      throw closedError();
    }
    if (read === null || read.current() !== true ||
        freshConversationTarget(read.selection) !== freshConversationTarget(selector)) throw closedError();
    const digest = witnessDigest(read);
    if (digest === null) throw closedError();
    const ownerAfter = options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) throw closedError();
    const request = consumeStatusRequest(selector, digest);
    if (request === null) throw closedError();
    let raw: unknown;
    try {
      raw = await options.transport.consumeStatus(request, signal);
    } catch {
      throw closedError();
    }
    const ownerFinal = options.owner();
    if (ownerFinal === null || !sameOwner(ownerFinal, ownerBefore)) throw closedError();
    // Original five-field envelope, verbatim; the parent decoder consumes it.
    return raw;
  }

  async function readOriginalTurn(
    selection: FreshConversationOriginalSelector,
    turnKey: string,
    signal: AbortSignal,
  ): Promise<unknown> {
    const selector = freshConversationOriginalSelector(selection);
    if (selector === null) throw closedError();
    if (typeof turnKey !== "string" || !TURN_KEY_PATTERN.test(turnKey)) throw closedError();
    const request = turnKeyRequest(selector, turnKey, "turn_read");
    if (request === null) throw closedError();
    const ownerBefore = options.owner();
    if (ownerBefore === null) throw closedError();
    let raw: unknown;
    try {
      raw = await options.transport.turnRead(request, signal);
    } catch {
      throw closedError();
    }
    const ownerAfter = options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) throw closedError();
    // Original five-field envelope, verbatim; no initial digest is needed and
    // the Workspace availability is deliberately not consulted here.
    return raw;
  }

  return {
    controller,
    store: options.store,
    context: () => options.owner(),
    makeConsumeIntent,
    makeTurnRequest,
    previewTurn,
    makeTurnIntent,
    readOriginalConsume,
    readOriginalTurn,
  };
}
