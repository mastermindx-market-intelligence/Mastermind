/**
 * Fixed frontend finite-command binding for the fresh conversation port.
 *
 * A thin host adapter over the incumbent {@link OperationController} and its
 * durable {@link PendingPointerStore}. This module owns no controller state
 * machine, no store, no global map, no subscription, no cache and no
 * lifecycle: the injected controller alone reads, reserves and clears the
 * pending pointer, and the port below alone decides which receipt the UI may
 * see. There are no timers, retries, mount effects, mission selection, source
 * reconciliation or child creation here.
 *
 * Wires:
 *  - `preview` is an observation. One ordinary client key is minted per
 *    explicit {@link FreshConversationBinding.makePreviewRequest} call; no
 *    pointer is reserved and no effect is submitted.
 *  - `create` is the only effect. It reaches the transport exclusively through
 *    `controller.begin(makeCreateIntent(...))`, which durably reserves the
 *    scope before submitting and clears the exact pointer only on a terminal
 *    receipt.
 *  - `status`/`read` are observations of the ORIGINAL operation. Recovery
 *    always belongs to the controller and its retained pointer; no new key is
 *    ever minted for a status, read or recovery.
 *
 * Privacy and authority:
 *  - `CommandIntent.payload.owner` is UI metadata captured through the host's
 *    `owner()` seam. It is never transmitted, never persisted, and never
 *    rendered as authority; the transport receives only the closed wire.
 *  - {@link FreshConversationBindingOptions.canPreviewCreate} is a host
 *    availability/precondition check only, never a grant: the backend enforces
 *    the real dual-resource authorization.
 *  - Raw five-field responses are returned verbatim; decoding belongs to the
 *    parent decoder. Producer messages and thrown text are never surfaced.
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
import { CONVERSATION_CREATE_KEY_PREFIX } from "../../orchestration/indexeddb-pending-pointer-store";
import {validateConversationRequest,decodeConversationResult,conversationContractForKey,
  conversationCreateSettled,NATIVE_CREATE_PREFIX,type FreshConversationObservedData} from "./fresh-conversation-contract";
import type {FreshConversationContract} from "../../orchestration/fresh-conversation-transport";
import {createNativeControlAdapter,type NativeControlTransport,type NativeControlBinding} from "./native-conversation-controls";

/** Exact wire selectors; ordinary client keys are never Runtime/session IDs. */
export interface ConversationRequestSelection {
  readonly work_ref: string;
  readonly operation_key: string;
}

export interface ConversationPreviewRequest extends ConversationRequestSelection {
  readonly message: string;
}

/** Closed four-field create wire; exactly what the transport may receive. */
export interface ConversationCreateRequest extends ConversationRequestSelection {
  readonly message: string;
  readonly preview_digest: string;
}

/** External transport seam. Every response stays an opaque raw envelope. */
export interface FreshConversationTransport {
  preview(request: ConversationPreviewRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  create(request: ConversationCreateRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  status(selection: ConversationRequestSelection, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  read(selection: ConversationRequestSelection, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
}

export interface FreshConversationBindingOptions {
  readonly nativeTransport?:NativeControlTransport;
  /** New drafts only; original stored keys always determine recovery syntax. */
  readonly newContract?:FreshConversationContract;
  /** Live UI owner snapshot seam; snapshots are taken through this only. */
  readonly owner: () => OwnerContext | null;
  /**
   * Current host availability/precondition for a NEW create. Never a grant,
   * never derived from Workspace/catalogue/source title, and never consulted
   * for status or read of an original operation.
   */
  readonly canPreviewCreate: () => boolean;
  readonly transport: FreshConversationTransport;
  /** The incumbent durable store; only the controller writes through it. */
  readonly store: PendingPointerStore;
}

/**
 * Fixed host adapter over the incumbent controller/store. Preview is an
 * observation; only controller.begin(makeCreateIntent(...)) can submit create.
 * Original recovery always belongs to that controller and its retained pointer.
 * The shared Host/native/App implementation is owned by the Release integrator.
 */
export interface FreshConversationBinding {
  readonly native?:NativeControlBinding;
  readonly newContract?:FreshConversationContract;
  readonly controller: OperationController;
  readonly store: PendingPointerStore;
  context(): OwnerContext | null;
  /** Synchronous, effect-free. Mint once for an explicit new draft, not recovery. */
  makePreviewRequest(workRef: string, message: string): ConversationPreviewRequest | null;
  preview(request: ConversationPreviewRequest, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
  /** Must preserve the request key and actual preview digest, distinct kind conversation_create. */
  makeCreateIntent(request: ConversationPreviewRequest, preview: FreshConversationObservedData): CommandIntent | null;
  readOriginal(selection: ConversationRequestSelection, signal: AbortSignal, contract?:FreshConversationContract): Promise<unknown>;
}

export interface ConversationProjectChoice {
  readonly workRef: string;
  readonly title: string | null;
}

/** A view identity comparison, never authentication or a derived permission. */
export function sameConversationOwner(
  a: OwnerContext | null,
  b: OwnerContext | null,
): boolean {
  return (
    a !== null &&
    b !== null &&
    a.principalScope === b.principalScope &&
    a.generation === b.generation
  );
}

/** Fixed marker thrown for every closed local refusal. No detail, ever. */
export const FRESH_CONVERSATION_BINDING_CLOSED = "FRESH_CONVERSATION_BINDING_CLOSED";

const CONVERSATION_KIND: OperationKind = "conversation_create";

/** Ordinary client keys only: the store's own conversation-create prefix. */
const OPERATION_KEY_RE = /^mmos-(?:conversation|native)-create-[0-9a-f]{40}$/;

const WORK_REF_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;

/**
 * Known public pre-effect producer codes that may close a create as refused.
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

const UNKNOWN_REASON = "UNKNOWN_RECEIPT";
const ACCEPTED_REASON = "ACCEPTED";

function closedError(): Error {
  return new Error(FRESH_CONVERSATION_BINDING_CLOSED);
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

/** Closed four-field create wire with the ordinary conversation-create key. */
function isCreateRequest(value: unknown): value is ConversationCreateRequest {
  if (validateConversationRequest(value, "create") === null) return false;
  const operationKey = (value as { operation_key?: unknown }).operation_key;
  return typeof operationKey === "string" && OPERATION_KEY_RE.test(operationKey);
}

function requestOriginal(options:FreshConversationBindingOptions,operation:"preview"|"create"|"status"|"read",
  request:ConversationPreviewRequest|ConversationCreateRequest|ConversationRequestSelection,signal:AbortSignal):Promise<unknown>{
  const contract=conversationContractForKey(request.operation_key);
  if(!contract)throw closedError();
  const method=options.transport[operation] as (request:ConversationPreviewRequest|ConversationCreateRequest|ConversationRequestSelection,signal:AbortSignal,contract?:FreshConversationContract)=>Promise<unknown>;
  return contract==="native-v2"?method.call(options.transport,request,signal,contract):method.call(options.transport,request,signal);
}

interface CapturedCreatePayload {
  readonly request: ConversationCreateRequest;
  /** UI metadata only; never transmitted and never persisted. */
  readonly owner: OwnerContext;
}

function isCreatePayload(value: unknown): value is CapturedCreatePayload {
  if (!isPlainObject(value) || Object.keys(value).length !== 2) return false;
  if (!Object.hasOwn(value, "request") || !Object.hasOwn(value, "owner")) {
    return false;
  }
  return isCreateRequest(value.request) && isOwnerContext(value.owner);
}

/**
 * Mint one ordinary client key: 20 random bytes as 40 lowercase hex digits
 * behind the store's conversation-create prefix. Fail closed when the
 * platform boundary is unavailable or misbehaves — no Math, time, default or
 * fixed-key fallback exists.
 */
function mintOperationKey(contract:FreshConversationContract): string | null {
  if(contract!=="legacy-v1"&&contract!=="native-v2")return null;
  const source: Crypto | undefined = globalThis.crypto;
  const getRandomValues = source?.getRandomValues;
  if (typeof getRandomValues !== "function") return null;
  const bytes = new Uint8Array(20);
  try {
    const filled = getRandomValues.call(source, bytes);
    if (!(filled instanceof Uint8Array) || filled.length !== bytes.length) {
      return null;
    }
  } catch {
    return null;
  }
  let hex = "";
  for (const byte of bytes) {
    if (!Number.isInteger(byte) || byte < 0 || byte > 0xff) return null;
    hex += byte.toString(16).padStart(2, "0");
  }
  const operationKey = `${contract==="native-v2"?NATIVE_CREATE_PREFIX:CONVERSATION_CREATE_KEY_PREFIX}${hex}`;
  return OPERATION_KEY_RE.test(operationKey) ? operationKey : null;
}

/**
 * The injected port. `prepare`/`submit`/`readOperation` re-derive everything
 * from the intent and the pointer alone; nothing is cached between calls and
 * the owner is re-read through the host seam on every fence.
 */
class FreshConversationCommandPort implements FiniteCommandPort {
  constructor(private readonly _options: FreshConversationBindingOptions) {}

  context(): OwnerContext | null {
    return this._options.owner();
  }

  /**
   * Synchronous and effect-free. Validates kind, target, payload wire grammar,
   * ordinary key prefix and owner currency; a contract failure throws and the
   * controller reports it as a malformed pointer.
   */
  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind !== CONVERSATION_KIND) throw closedError();
    if (typeof intent.targetKey !== "string") throw closedError();
    if (!isCreatePayload(intent.payload)) throw closedError();
    const request = intent.payload.request;
    if (request.work_ref !== intent.targetKey) throw closedError();
    const live = this._options.owner();
    if (live === null || !sameConversationOwner(live, intent.payload.owner)) {
      throw closedError();
    }
    return {
      operationKey: request.operation_key,
      kind: CONVERSATION_KIND,
      targetKey: intent.targetKey,
    };
  }

  /**
   * The single create path. Fences the captured owner and the create
   * availability before and after the await, calls the transport exactly once
   * with the closed wire, and classifies only the decoded outcome.
   */
  async submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (intent.kind !== CONVERSATION_KIND || !isCreatePayload(intent.payload)) {
      throw closedError();
    }
    const request = intent.payload.request;
    const capturedOwner = intent.payload.owner;
    if (
      pointer.kind !== CONVERSATION_KIND ||
      pointer.operationKey !== request.operation_key ||
      pointer.targetKey !== request.work_ref
    ) {
      return unknownReceipt(pointer);
    }
    const available = this._options.canPreviewCreate() === true;
    const liveBefore = this._options.owner();
    if (
      liveBefore === null ||
      !sameConversationOwner(liveBefore, capturedOwner) ||
      !available
    ) {
      return unknownReceipt(pointer);
    }
    let raw: unknown;
    try {
      raw = await requestOriginal(this._options,"create",
        {
          work_ref: request.work_ref,
          operation_key: request.operation_key,
          message: request.message,
          preview_digest: request.preview_digest,
        },
        signal,
      );
    } catch {
      // Thrown transport: the effect is unknown, never refused.
      return unknownReceipt(pointer);
    }
    const liveAfter = this._options.owner();
    if (
      liveAfter === null ||
      !sameConversationOwner(liveAfter, capturedOwner) ||
      this._options.canPreviewCreate() !== true
    ) {
      // Owner or availability moved across the await: this receipt may not be
      // published as private knowledge; unknown retains the pointer.
      return unknownReceipt(pointer);
    }
    return this._classifyCreate(raw, request, pointer);
  }

  /**
   * Observation of the ORIGINAL operation only. Validates the pointer,
   * requires the current executive owner, and reads `status` with the stored
   * key — never create, prepare, resubmit or source reconciliation. Create
   * availability is deliberately not consulted here.
   */
  async readOperation(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    if (pointer.kind !== CONVERSATION_KIND) return unknownReceipt(pointer);
    if (
      typeof pointer.operationKey !== "string" ||
      !OPERATION_KEY_RE.test(pointer.operationKey) ||
      typeof pointer.targetKey !== "string" ||
      !WORK_REF_RE.test(pointer.targetKey)
    ) {
      return unknownReceipt(pointer);
    }
    const before = this._options.owner();
    if (before === null) return unknownReceipt(pointer);
    let raw: unknown;
    try {
      raw = await requestOriginal(this._options,"status",
        { work_ref: pointer.targetKey, operation_key: pointer.operationKey },
        signal,
      );
    } catch {
      return unknownReceipt(pointer);
    }
    const after = this._options.owner();
    if (after === null || !sameConversationOwner(after, before)) {
      return unknownReceipt(pointer);
    }
    const decoded = decodeConversationResult(raw, "status", {
      work_ref: pointer.targetKey,
      operation_key: pointer.operationKey,
    });
    if (decoded === null || !decoded.ok) {
      // ABSENT and every producer error are holds, never pre-effect clearance.
      return unknownReceipt(pointer);
    }
    if (conversationCreateSettled(decoded.data)) {
      return receipt(pointer, "accepted", ACCEPTED_REASON);
    }
    return unknownReceipt(pointer);
  }

  /** CREATED (with session + resolved locator) or SETTLED; all else unknown. */
  private _classifyCreate(
    raw: unknown,
    request: ConversationCreateRequest,
    pointer: OperationPointer,
  ): EffectReceipt {
    const decoded = decodeConversationResult(raw, "create", request);
    if (decoded === null) return unknownReceipt(pointer);
    if (!decoded.ok) {
      return REFUSAL_CODES.has(decoded.error.code)
        ? receipt(pointer, "refused", decoded.error.code)
        : unknownReceipt(pointer);
    }
    if (conversationCreateSettled(decoded.data)) {
      return receipt(pointer, "accepted", ACCEPTED_REASON);
    }
    return unknownReceipt(pointer);
  }
}

/**
 * Build the binding over the incumbent controller and store. No other module
 * state is created; every call below re-reads the host seams.
 */
export function createFreshConversationBinding(
  options: FreshConversationBindingOptions,
): FreshConversationBinding {
  const port = new FreshConversationCommandPort(options);
  const native=options.nativeTransport?createNativeControlAdapter({owner:options.owner,canModify:options.canPreviewCreate,get transport(){if(!options.nativeTransport)throw closedError();return options.nativeTransport;}}):null;
  if(native)Object.assign(port,{reconcileNativeOperation:native.reconcileNativeOperation,prepareControl:native.prepareControl,submitControl:native.submitControl,readControlOperation:native.readControlOperation});
  const controller = new OperationController(port, options.store);

  function makePreviewRequest(
    workRef: string,
    message: string,
  ): ConversationPreviewRequest | null {
    if (typeof workRef !== "string" || !WORK_REF_RE.test(workRef)) return null;
    if (typeof message !== "string") return null;
    const operationKey = mintOperationKey(options.newContract??"legacy-v1");
    if (operationKey === null) return null;
    const candidate = { work_ref: workRef, operation_key: operationKey, message };
    // Full wire validation of the exact request that will be sent.
    const validated = validateConversationRequest(candidate, "preview");
    if (validated === null || !("message" in validated)) return null;
    return validated;
  }

  async function preview(
    request: ConversationPreviewRequest,
    signal: AbortSignal,
  ): Promise<unknown> {
    const validated = validateConversationRequest(request, "preview");
    if (validated === null || !("message" in validated)) throw closedError();
    const before = options.owner();
    if (before === null || options.canPreviewCreate() !== true) {
      throw closedError();
    }
    let raw: unknown;
    try {
      raw = await requestOriginal(options,"preview",validated, signal);
    } catch {
      throw closedError();
    }
    const after = options.owner();
    if (
      after === null ||
      !sameConversationOwner(after, before) ||
      options.canPreviewCreate() !== true
    ) {
      throw closedError();
    }
    // Original five-field envelope, verbatim; the parent decoder consumes it.
    return raw;
  }

  function makeCreateIntent(
    request: ConversationPreviewRequest,
    previewData: FreshConversationObservedData,
  ): CommandIntent | null {
    const validated = validateConversationRequest(request, "preview");
    if (validated === null || !("message" in validated)) return null;
    if (!OPERATION_KEY_RE.test(validated.operation_key)) return null;
    if (!isPlainObject(previewData)) return null;
    if (previewData.state !== "PREVIEW_READY" || previewData.schema!==(conversationContractForKey(validated.operation_key)==="native-v2"
      ?"mastermind.executive.fresh_conversation_data.v2":"mastermind.executive.fresh_conversation_data.v1")) return null;
    if (
      previewData.work_ref !== validated.work_ref ||
      previewData.operation_key !== validated.operation_key
    ) {
      return null;
    }
    const preview = previewData.preview;
    if (preview === null || !HEX64_RE.test(preview.digest)) return null;
    const owner = options.owner();
    if (owner === null || options.canPreviewCreate() !== true) return null;
    return {
      kind: CONVERSATION_KIND,
      targetKey: validated.work_ref,
      payload: {
        request: {
          work_ref: validated.work_ref,
          operation_key: validated.operation_key,
          message: validated.message,
          preview_digest: preview.digest,
        },
        owner: { principalScope: owner.principalScope, generation: owner.generation },
      },
    };
  }

  async function readOriginal(
    selection: ConversationRequestSelection,
    signal: AbortSignal,
  ): Promise<unknown> {
    const validated = validateConversationRequest(selection, "read");
    if (validated === null) throw closedError();
    const before = options.owner();
    if (before === null) throw closedError();
    let raw: unknown;
    try {
      raw = await requestOriginal(options,"read",
        { work_ref: validated.work_ref, operation_key: validated.operation_key },
        signal,
      );
    } catch {
      throw closedError();
    }
    const after = options.owner();
    if (after === null || !sameConversationOwner(after, before)) {
      throw closedError();
    }
    // Original five-field envelope, verbatim; availability is irrelevant here.
    return raw;
  }

  return {
    ...(native?{native:native.binding}:{}),
    newContract:options.newContract??"legacy-v1",
    controller,
    store: options.store,
    context: () => options.owner(),
    makePreviewRequest,
    preview,
    makeCreateIntent,
    readOriginal,
  };
}
