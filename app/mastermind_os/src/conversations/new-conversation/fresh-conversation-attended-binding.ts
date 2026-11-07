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

import {attendedContractForKey,validateAttendedRequest,decodeAttendedResult,decodeAttendedPreview} from "./fresh-conversation-attended-contract";
import {decodeFreshNativeResult,type FreshNativeResult} from "../fresh-conversation-reference";
import type {NativeFreshTurnPreview} from "./native-fresh-result";
import {nativeExact,nativeId,nativeWork} from "./native-fresh-request";
import {conversationContractForKey} from "./fresh-conversation-contract";
import type {FreshConversationContract} from "../../orchestration/fresh-conversation-transport";
import {createNativeControlAdapter,type NativeControlTransport,type NativeControlBinding,type NativeControlAdapter} from "./native-conversation-controls";

// ── Public contract ──────────────────────────────────────────────────────────

/** Host-issued witness for the current sealed initial read of an original. */
export interface FreshConversationOriginalRead {
  readonly selection: FreshConversationOriginalSelector;
  /** Producer-sealed initial result, re-verified against the actual locator. */
  readonly result: FreshConversationPayload|FreshNativeResult;
  readonly contract?: "native-v2";
  readonly locator: FreshConversationTurnLocator;
  /** Issued current witness; a false answer withholds new actions. */
  current(): boolean;
}

/** External transport seam. Every response stays an opaque raw envelope. */
export interface FreshConversationAttendedTransport {
  consume(request: FreshConversationTurnRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  consumeStatus(request: FreshConversationTurnRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  turnPreview(request: FreshConversationTurnRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  turn(request: FreshConversationTurnRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  turnStatus(request: FreshConversationTurnRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  turnRead(request: FreshConversationTurnRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
}

export interface FreshConversationAttendedBindingOptions {
  readonly nativeTransport?:NativeControlTransport;
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
    contract?:FreshConversationContract,
  ) => Promise<FreshConversationOriginalRead | null>;
}

/** Captured, privilege-free preflight result for one attended turn. */
export interface PreparedFreshConversationTurn {
  /** Exactly the once-minted request; the intent never remints. */
  readonly request: FreshConversationTurnRequest;
  /** Actually decoded TURN_READY preview of the separate pure branch. */
  readonly preview: FreshConversationTurnPreviewData|NativeFreshTurnPreview;
  /** Owner snapshot captured at preflight; compared, never an authority. */
  readonly owner: OwnerContext;
  /** Actual host read witness the request was minted against. */
  readonly witness: FreshConversationOriginalRead;
}

export interface FreshConversationAttendedBinding {
  readonly native?:NativeControlBinding;
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
    contract?:FreshConversationContract,
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
const CONSUME_KEY_PATTERN = /^mmos-(?:conversation|native)-consume-[0-9a-f]{40}$/;
const TURN_KEY_PATTERN = /^mmos-(?:conversation|native)-turn-[0-9a-f]{40}$/;

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
  if (!isPlainObject(value) || Object.keys(value).length !== (value.contract==="native-v2"?5:4) ||
    Object.hasOwn(value,"contract")&&value.contract!=="native-v2") return false;
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
  if (!isPlainObject(read.result) || Object.keys(read.result).length !== (read.contract==="native-v2"?3:2)) return false;
  return true;
}

/**
 * Strict shared sealed-result/locator proof bound to the same original
 * selector and the actual work/root. Returns the verified initial digest.
 */
function witnessDigest(read: FreshConversationOriginalRead): string | null {
  const selector = freshConversationOriginalSelector(read.selection);
  if (selector === null || selector.work_ref !== read.locator.work_ref||
    "operation_key"in selector&&conversationContractForKey(selector.operation_key)!==contractOf(read)) return null;
  if ("reference" in selector && selector.reference.root_job_id !== read.locator.root_job_id) {
    return null;
  }
  if(read.contract==="native-v2"){
    try{
      const locator=nativeExact(read.locator,["work_ref","root_job_id","job_id","attempt_id"]);
      if(nativeWork(locator.work_ref)!==selector.work_ref)return null;
      nativeId(locator.root_job_id);nativeId(locator.job_id);nativeId(locator.attempt_id);
      return decodeFreshNativeResult(read.result).digest;
    }catch{return null;}
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
  contract:FreshConversationContract="legacy-v1",
): FreshConversationTurnRequest | null {
  const base = selectorRequestBase(selector);
  if (base === null) return null;
  return validateAttendedRequest({ ...base, initial_digest: digest }, "consume_status",contract);
}

function turnKeyRequest(
  selector: FreshConversationOriginalSelector,
  turnKey: string,
  operation: "turn_status" | "turn_read",
): FreshConversationTurnRequest | null {
  const base = selectorRequestBase(selector);
  if (base === null) return null;
  const contract=attendedContractForKey(turnKey);
  return contract?validateAttendedRequest({ ...base, turn_key: turnKey }, operation,contract):null;
}

function contractOf(read:FreshConversationOriginalRead):FreshConversationContract{
  return read.contract==="native-v2"?"native-v2":"legacy-v1";
}
function requestTransport(options:FreshConversationAttendedBindingOptions,method:keyof FreshConversationAttendedTransport,
 request:FreshConversationTurnRequest,signal:AbortSignal,contract:FreshConversationContract):Promise<unknown>{
 const call=options.transport[method];
 return contract==="native-v2"?call.call(options.transport,request,signal,contract):call.call(options.transport,request,signal);
}
function readInitial(options:FreshConversationAttendedBindingOptions,selection:FreshConversationOriginalSelector,
 signal:AbortSignal,contract:FreshConversationContract):Promise<FreshConversationOriginalRead|null>{
 return contract==="native-v2"?options.readInitial(selection,signal,contract):options.readInitial(selection,signal);
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
  if(attendedContractForKey(key)!==contractOf(witness))return null;
  const request = validateAttendedRequest(
    payload.request,
    intent.kind === CONSUME_KIND ? "consume" : "turn",contractOf(witness),
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
  constructor(private readonly _options: FreshConversationAttendedBindingOptions,private readonly _native:NativeControlAdapter|null) {}

  context(): OwnerContext | null {
    return this._options.owner();
  }

  /** Synchronous and effect-free; a contract failure throws. */
  prepare(intent: CommandIntent): OperationPointer {
    if(intent.kind==="conversation_stop"||intent.kind==="conversation_resume"){if(!this._native)throw closedError();return this._native.prepare(intent);}
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
    if(intent.kind==="conversation_stop"||intent.kind==="conversation_resume")return this._native?this._native.submit(pointer,intent,signal):unknownReceipt(pointer);
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
        ? await requestTransport(this._options,"consume",payload.request,signal,contractOf(payload.witness))
        : await requestTransport(this._options,"turn",payload.request,signal,contractOf(payload.witness));
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
    return classifyEffect(raw, isConsume ? "consume" : "turn", payload.request, pointer,contractOf(payload.witness));
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
    if(pointer.kind==="conversation_stop"||pointer.kind==="conversation_resume")return this._native?this._native.readOperation(pointer,signal):unknownReceipt(pointer);
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
      read = await readInitial(this._options,selector,signal,attendedContractForKey(pointer.operationKey)!);
    } catch {
      return unknownReceipt(pointer);
    }
    if (read === null || read.current() !== true ||
        freshConversationTarget(read.selection) !== pointer.targetKey) return unknownReceipt(pointer);
    const contract=attendedContractForKey(pointer.operationKey);
    if(!contract||contract!==contractOf(read))return unknownReceipt(pointer);
    const digest = witnessDigest(read);
    if (digest === null) return unknownReceipt(pointer);
    const ownerAfter = this._options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) {
      return unknownReceipt(pointer);
    }
    const request = consumeStatusRequest(selector, digest,contract);
    if (request === null) return unknownReceipt(pointer);
    let raw: unknown;
    try {
      raw = await requestTransport(this._options,"consumeStatus",request,signal,contract);
    } catch {
      return unknownReceipt(pointer);
    }
    const ownerFinal = this._options.owner();
    if (ownerFinal === null || !sameOwner(ownerFinal, ownerBefore)) {
      return unknownReceipt(pointer);
    }
    const decoded = decodeAttendedResult(raw, "consume_status", request,contract);
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
      raw = await requestTransport(this._options,"turnStatus",request,signal,attendedContractForKey(pointer.operationKey)!);
    } catch {
      return unknownReceipt(pointer);
    }
    const ownerAfter = this._options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) {
      return unknownReceipt(pointer);
    }
    const decoded = decodeAttendedResult(raw, "turn_status", request,attendedContractForKey(pointer.operationKey)!);
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
  contract:FreshConversationContract,
): EffectReceipt {
  const decoded = decodeAttendedResult(raw, operation, request,contract);
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
  const native=options.nativeTransport?createNativeControlAdapter({owner:options.owner,canModify:options.canModify,get transport(){if(!options.nativeTransport)throw closedError();return options.nativeTransport;}}):null;
  const port = new FreshConversationAttendedCommandPort(options,native);
  if(native)Object.assign(port,{reconcileNativeOperation:native.reconcileNativeOperation,prepareControl:native.prepareControl,submitControl:native.submitControl,readControlOperation:native.readControlOperation});
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
    const key = mintFreshConversationCommandKey("conversation_consume",contractOf(read));
    if (key === null || !CONSUME_KEY_PATTERN.test(key)) return null;
    const request = validateAttendedRequest(
      { ...base, initial_digest: digest },
      "consume",contractOf(read),
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
    const key = mintFreshConversationCommandKey("conversation_turn",contractOf(read));
    if (key === null || !TURN_KEY_PATTERN.test(key)) return null;
    // Exact message, actual digest, minted key; no preview digest yet.
    const request = validateAttendedRequest(
      { ...base, initial_digest: digest, message, turn_key: key },
      contractOf(read)==="native-v2"?"turn_preview":"turn",contractOf(read),
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
    const validated = validateAttendedRequest(request, "turn_preview",contractOf(read));
    if (validated === null) return null;
    const validatedTurnKey = requestTurnKey(validated);
    if (validatedTurnKey === null || !TURN_KEY_PATTERN.test(validatedTurnKey)||attendedContractForKey(validatedTurnKey)!==contractOf(read)) return null;
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
      raw = await requestTransport(options,"turnPreview",detachRequest(validated),signal,contractOf(read));
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
    const decoded = decodeAttendedPreview(raw, validated,contractOf(read));
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
    const contract=contractOf(prepared.witness);
    const base = validateAttendedRequest(prepared.request, contract==="native-v2"?"turn_preview":"turn",contract);
    if (base === null) return null;
    const baseTurnKey = requestTurnKey(base);
    if (baseTurnKey === null || !TURN_KEY_PATTERN.test(baseTurnKey)||attendedContractForKey(baseTurnKey)!==contract||
      preview.schema!==(contract==="native-v2"?"mastermind.executive.fresh_conversation_turn_preview.v2":"mastermind.executive.fresh_conversation_turn_preview.v1")) return null;
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
    const request = validateAttendedRequest(
      { ...base, preview_digest: preview.preview_digest },
      "turn",contract,
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
    contract:FreshConversationContract="legacy-v1",
  ): Promise<unknown> {
    const selector = freshConversationOriginalSelector(selection);
    if (selector === null || freshConversationTarget(selector) === null) throw closedError();
    const ownerBefore = options.owner();
    if (ownerBefore === null) throw closedError();
    let read: FreshConversationOriginalRead | null;
    try {
      read = await readInitial(options,selector,signal,contract);
    } catch {
      throw closedError();
    }
    if (read === null || read.current() !== true ||
        freshConversationTarget(read.selection) !== freshConversationTarget(selector)) throw closedError();
    if(contract!==contractOf(read))throw closedError();
    const digest = witnessDigest(read);
    if (digest === null) throw closedError();
    const ownerAfter = options.owner();
    if (ownerAfter === null || !sameOwner(ownerAfter, ownerBefore)) throw closedError();
    const request = consumeStatusRequest(selector, digest,contract);
    if (request === null) throw closedError();
    let raw: unknown;
    try {
      raw = await requestTransport(options,"consumeStatus",request,signal,contract);
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
      raw = await requestTransport(options,"turnRead",request,signal,attendedContractForKey(turnKey)!);
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
    ...(native?{native:native.binding}:{}),
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
