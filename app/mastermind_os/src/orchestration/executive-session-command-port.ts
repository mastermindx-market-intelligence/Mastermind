/**
 * Executive session command port — selected fabric_attempt session continuation.
 *
 * A UI-local {@link FiniteCommandPort} over the injected private session
 * transport, plus the explicit {@link createExecutiveSessionBinding} factory
 * that matches the existing {@link OrchestratorCommandBinding} shape. There is
 * no backend, no route/URL/tool/token selection, no registry and no producer
 * here: the injected transport is the sole authority for the fixed private
 * session context/send/reply calls, and the host-projected target row is the
 * sole authority for target, generation and continuation identity.
 *
 * AUTH AND SELECTION FENCING. The host captures the owner principal scope, the
 * owner generation, the private authGeneration, the selected Mission and the
 * target generation before every await and re-checks the exact same values
 * after it. A→B→A is covered because the owner generation supplied by the host
 * is monotonic across auth epochs. The host MUST call refresh on each selected
 * Mission transition (including A→B→A); no snapshot getter can detect an
 * unobserved ABA. The port never mints, signs or parses
 * generations — it compares them. Any drift after the send call has been
 * entered yields an `unknown` receipt that retains the ORIGINAL pointer; drift
 * before the send call is a pre-send refusal (this invocation only).
 *
 * EFFECT DISCIPLINE. Only a validated exact canonical send receipt or native
 * reply receipt is an accepted commit (`CONTINUATION_COMMITTED`). Attention
 * (`UNAVAILABLE` / reconciliation `EFFECT_UNKNOWN`) is retained as data only —
 * it never proves or disproves Worker execution or parent consumption. Every
 * malformed, foreign, lost-response, epoch-drift or reply-failure outcome is
 * `unknown` on the original pointer; a reply failure NEVER clears it. A
 * refusal is only ever a pre-send outcome for THIS invocation and says nothing
 * about any historical invocation. Recovery is observation only: it uses the
 * exact original operation key, never sends, never looks up targets, and never
 * mints a key.
 *
 * STOP. There is no stop factory here. `stop_condition` is an explicit
 * caller-provided string carried verbatim; it is never a cancellation, and
 * abort/invalidate only suppress rendering while retaining the pointer.
 */

import type {
  CommandIntent,
  EffectReceipt,
  FiniteCommandPort,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "./operation-controller";
import type { OrchestratorCommandBinding } from "./host-command-bindings";
import type { MissionSelection } from "../mission";
import {
  SESSION_TEXT_MAX_CODEPOINTS as MAX_TEXT_CODEPOINTS,
  codePointLength,
} from "./session-text-contract";
export { codePointLength } from "./session-text-contract";

// ── Frozen wire vocabulary ────────────────────────────────────────────────────

const RESULT_SCHEMA = "mastermind.os.executive.session_result.v1";
const CONTEXT_SCHEMA = "mastermind.os.executive.session_context.v1";
const NATIVE_REPLY_SCHEMA = "mastermind.native_reply_read.v1";

const ENVELOPE_KEYS = [
  "schema", "operation", "ok", "effect", "operation_key", "data", "error",
] as const;
const CONTEXT_KEYS = [
  "schema", "principal_scope", "verified_expiry", "selection",
  "selection_state", "target", "capabilities",
] as const;
const SELECTION_KEYS = ["work_ref", "root_job_id"] as const;
const CAPABILITY_KEYS = ["send", "reply_read", "stop"] as const;
/** Exactly the seven host-projected canonical target fields. */
const TARGET_KEYS = [
  "target_ref", "generation", "addressable", "kind",
  "continuation_operation_key", "work_ref", "root_job_id",
] as const;
const SEND_DATA_KEYS = [
  "target_ref", "reply_committed", "carrier", "attention", "read_ref",
] as const;
const CARRIER_KEYS = [
  "reply_committed", "action", "message_key", "fingerprint", "thread_ts",
] as const;
const REPLY_KEYS = [
  "schema", "read_ref", "request_ref", "in_reply_to", "message_key",
  "fingerprint", "text", "next_step", "primary_ts", "reply_committed",
  "parent_consumed", "operation_key",
] as const;
const ERROR_KEYS = ["code", "message"] as const;

const EFFECTS = new Set(["NONE", "CONTINUATION_COMMITTED", "UNKNOWN"]);
const OPERATIONS = new Set(["context", "send", "reply"]);
const SELECTION_STATES = new Set(["RESOLVED", "UNAVAILABLE", "AMBIGUOUS"]);
const ERROR_CODES = new Set([
  "invalid_input",
  "authentication_required",
  "transport_refused",
  "session_unavailable",
  "effect_unknown",
]);
/** Committed carrier actions from the existing dialogue CONTINUE writer. */
const COMMITTED_ACTIONS = new Set(["POSTED", "RECOVERED", "DUPLICATE"]);
/** Closed installed attention state; it is not worker/result evidence. */
const ATTENTION_VALUES = new Set(["UNAVAILABLE", "EFFECT_UNKNOWN"]);

const TARGET_REF_RE = /^fabric_attempt:[0-9a-f]{64}$/;
const GENERATION_RE = /^[0-9a-f]{24}$/;
const OPERATION_KEY_RE = /^session-continue-[0-9a-f]{64}$/;
/** Protected os_transport.principal_scope returns SHA-256.hexdigest(); opaque to this consumer. */
const SCOPE_RE = /^[0-9a-f]{64}$/;
const FINGERPRINT_RE = /^[0-9a-f]{64}$/;
const THREAD_TS_RE = /^[0-9]{10,16}\.[0-9]{6}$/;
const BOUNDED_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;
const CONTINUE_MESSAGE_KEY_RE = /^asd-dot-continue-[0-9a-f]{40}$/;
const WORK_REF_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ROOT_JOB_RE = /^JOB-[A-Za-z0-9][A-Za-z0-9._:-]{0,250}$/;

const REPLY_TEXT_BOUND = 8192;

const PAYLOAD_KEYS = new Set([
  "instruction", "stop_condition", "work_ref", "root_job_id",
]);

// ── Small validation helpers ──────────────────────────────────────────────────

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function exactKeys(v: Record<string, unknown>, keys: readonly string[]): boolean {
  const own = Object.keys(v);
  if (own.length !== keys.length) return false;
  return keys.every((k) => Object.prototype.hasOwnProperty.call(v, k));
}

function isString(v: unknown): v is string {
  return typeof v === "string";
}

function boundedText(v: unknown, max: number): v is string {
  return isString(v) && codePointLength(v) >= 1 && codePointLength(v) <= max;
}

function validWorkRef(v: unknown): v is string {
  return isString(v) && WORK_REF_RE.test(v);
}

function validRootJobId(v: unknown): v is string {
  return isString(v) && ROOT_JOB_RE.test(v);
}

function validSelection(v: unknown): v is { work_ref: string; root_job_id: string } {
  return (
    isPlainObject(v) &&
    exactKeys(v, SELECTION_KEYS) &&
    validWorkRef(v.work_ref) &&
    validRootJobId(v.root_job_id)
  );
}

function validPointerShape(p: OperationPointer): boolean {
  return (
    OPERATION_KEY_RE.test(p.operationKey) &&
    p.kind === "message" &&
    typeof p.targetKey === "string" &&
    TARGET_REF_RE.test(p.targetKey)
  );
}

function validErrorShape(v: unknown): v is { code: string; message: string } {
  return (
    isPlainObject(v) &&
    exactKeys(v, ERROR_KEYS) &&
    isString(v.code) &&
    ERROR_CODES.has(v.code) &&
    isString(v.message)
  );
}

/**
 * Strict closed envelope. Unknown or unrecognized envelopes return null and
 * are treated as UNKNOWN by the caller — never as absence or refusal.
 */
function decodeEnvelope(
  raw: unknown,
  operation: "context" | "send" | "reply",
): {
  readonly ok: boolean;
  readonly effect: string;
  readonly operationKey: unknown;
  readonly data: unknown;
  readonly error: unknown;
} | null {
  if (!isPlainObject(raw) || !exactKeys(raw, ENVELOPE_KEYS)) return null;
  if (raw.schema !== RESULT_SCHEMA || !OPERATIONS.has(raw.operation as string)) {
    return null;
  }
  if (raw.operation !== operation) return null;
  if (typeof raw.ok !== "boolean" || !EFFECTS.has(raw.effect as string)) {
    return null;
  }
  if (raw.operation_key !== null && !isString(raw.operation_key)) return null;
  if (raw.data !== null && !isPlainObject(raw.data)) return null;
  if (raw.error !== null && !isPlainObject(raw.error)) return null;
  return {
    ok: raw.ok,
    effect: raw.effect as string,
    operationKey: raw.operation_key,
    data: raw.data,
    error: raw.error,
  };
}

/**
 * Canonical CONTINUE message key binding: `asd-dot-continue-` + the first 40
 * hex chars of SHA-256("mastermind.session_bridge.continue.v1\n"+key). This
 * only validates receipt binding of the host-projected key; it never mints an
 * operation or target. Unavailable WebCrypto refuses validation.
 */
async function continueMessageKeyBound(
  operationKey: string,
  messageKey: string,
  native = false,
): Promise<boolean> {
  const prefix = native ? "asd-native-reply-" : "asd-dot-continue-";
  const grammar = native ? /^asd-native-reply-[0-9a-f]{40}$/ : CONTINUE_MESSAGE_KEY_RE;
  if (!grammar.test(messageKey)) return false;
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return false;
  try {
    const encoded = new TextEncoder().encode(
      (native ? "mastermind.session_bridge.native_reply.v1\n" : "mastermind.session_bridge.continue.v1\n") + operationKey,
    );
    const digest = await subtle.digest("SHA-256", encoded);
    const hex = [...new Uint8Array(digest)]
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    return hex.slice(0, 40) === messageKey.slice(prefix.length);
  } catch {
    return false;
  }
}

// ── Validated projections ─────────────────────────────────────────────────────

/** Exact seven-field canonical fabric_attempt target row. */
export interface SessionTargetRow {
  readonly target_ref: string;
  readonly generation: string;
  readonly addressable: true;
  readonly kind: "fabric_attempt";
  readonly continuation_operation_key: string;
  readonly work_ref: string;
  readonly root_job_id: string;
}

export interface SessionCapabilities {
  readonly send: boolean;
  readonly reply_read: boolean;
  readonly stop: false;
}

export type SessionSelectionState = "RESOLVED" | "UNAVAILABLE" | "AMBIGUOUS";

/** Fenced verified session state the host projects to the port. */
export interface VerifiedSessionState {
  readonly principalScope: string;
  readonly expiresAtMs: number;
  readonly selection: MissionSelection;
  readonly selectionState: SessionSelectionState;
  readonly target: SessionTargetRow | null;
  readonly capabilities: SessionCapabilities;
}

function validTargetRow(v: unknown): v is SessionTargetRow {
  if (!isPlainObject(v) || !exactKeys(v, TARGET_KEYS)) return false;
  return (
    isString(v.target_ref) &&
    TARGET_REF_RE.test(v.target_ref) &&
    isString(v.generation) &&
    GENERATION_RE.test(v.generation) &&
    v.generation === v.target_ref.slice("fabric_attempt:".length, "fabric_attempt:".length + 24) &&
    v.addressable === true &&
    v.kind === "fabric_attempt" &&
    isString(v.continuation_operation_key) &&
    OPERATION_KEY_RE.test(v.continuation_operation_key) &&
    validWorkRef(v.work_ref) &&
    validRootJobId(v.root_job_id)
  );
}

function validCapabilities(v: unknown): v is SessionCapabilities {
  if (!isPlainObject(v) || !exactKeys(v, CAPABILITY_KEYS)) return false;
  return (
    typeof v.send === "boolean" &&
    v.reply_read === true &&
    v.stop === false
  );
}

/**
 * Decode the context envelope against the exact requested selection. The
 * canonical work/root join is enforced here too: RESOLVED carries exactly one
 * intact row whose selection equals the request; UNAVAILABLE and AMBIGUOUS
 * carry no target and never send. Any malformed or disagreeing row fails
 * closed as unavailable — an empty projection is never durable absence.
 */
export function decodeSessionContext(
  raw: unknown,
  selection: MissionSelection,
): VerifiedSessionState | null {
  const envelope = decodeEnvelope(raw, "context");
  if (!envelope || envelope.ok !== true) return null;
  if (envelope.effect !== "NONE") return null;
  if (envelope.operationKey !== null || envelope.error !== null) return null;
  const data = envelope.data as Record<string, unknown> | null;
  if (!isPlainObject(data) || !exactKeys(data, CONTEXT_KEYS)) return null;
  if (data.schema !== CONTEXT_SCHEMA) return null;
  if (!isString(data.principal_scope) || !SCOPE_RE.test(data.principal_scope)) {
    return null;
  }
  if (
    typeof data.verified_expiry !== "number" ||
    !Number.isSafeInteger(data.verified_expiry) || data.verified_expiry <= 0 ||
    !Number.isSafeInteger(data.verified_expiry * 1000)
  ) {
    return null;
  }
  if (!validSelection(data.selection)) return null;
  if (
    data.selection.work_ref !== selection.workRef ||
    data.selection.root_job_id !== selection.rootJobId
  ) {
    return null;
  }
  if (!isString(data.selection_state) || !SELECTION_STATES.has(data.selection_state)) {
    return null;
  }
  if (!validCapabilities(data.capabilities)) return null;
  const state = data.selection_state as SessionSelectionState;
  if (state === "RESOLVED") {
    if (!validTargetRow(data.target)) return null;
    if (
      data.target.work_ref !== selection.workRef ||
      data.target.root_job_id !== selection.rootJobId
    ) {
      return null;
    }
  } else if (data.target !== null || data.capabilities.send) {
    return null;
  }
  return Object.freeze({
    principalScope: data.principal_scope,
    expiresAtMs: data.verified_expiry * 1000,
    selection: Object.freeze({ ...selection }),
    selectionState: state,
    target: state === "RESOLVED" ? Object.freeze({ ...data.target }) as SessionTargetRow : null,
    capabilities: Object.freeze({ ...data.capabilities }),
  });
}

// ── Private transport (fixed calls; no URL/tool/token selection) ─────────────

export interface SessionSendArguments {
  readonly target_ref: string;
  readonly instruction: string;
  readonly stop_condition: string;
  readonly operation_key: string;
}

export interface SessionReplyArguments {
  readonly operation_key: string;
}

/** Bounded fields from an already cryptographically validated native READ.
 * No new authority, reply fetch or parent-consumed writer is introduced. */
export interface QualifiedSessionAnswer {
  readonly text: string;
  readonly nextStep: string;
  readonly readRef: string;
  readonly parentConsumed: false;
}
export interface QualifiedSessionAnswerRead {
  readonly receipt: EffectReceipt;
  readonly answer: QualifiedSessionAnswer | null;
}

export interface ExecutiveSessionTransport {
  /** Current private auth generation; monotonic across auth epochs. */
  authGeneration(): number;
  available(): boolean;
  subscribe(listener: () => void): () => void;
  context(selection: MissionSelection, signal: AbortSignal): Promise<unknown>;
  send(args: SessionSendArguments, signal: AbortSignal): Promise<unknown>;
  reply(args: SessionReplyArguments, signal: AbortSignal): Promise<unknown>;
  /** Canonical historical original-request references; no SEND or ACK. */
  references?(args: { work_ref: string; root_job_id: string; page_size?: number; cursor?: string },
              signal: AbortSignal): Promise<unknown>;
}

// ── Port ──────────────────────────────────────────────────────────────────────

type PortReason =
  | "ACCEPTED"
  | "REFUSED"
  | "INVALID_PAYLOAD"
  | "INVALID_KIND"
  | "MALFORMED_POINTER"
  | "MALFORMED_RECEIPT"
  | "RECEIPT_MISMATCH"
  | "UNKNOWN_RECEIPT"
  | "TRANSPORT_ERROR"
  | "EPOCH_CHANGED"
  | "SESSION_UNAVAILABLE";

export class ExecutiveSessionCommandPort implements FiniteCommandPort {
  private readonly _transport: ExecutiveSessionTransport;
  private readonly _session: () => VerifiedSessionState | null;
  private readonly _owner: () => OwnerContext | null;
  private readonly _captured = new WeakMap<CommandIntent["payload"], { scope: string; generation: string; auth: number }>();

  constructor(
    transport: ExecutiveSessionTransport,
    session: () => VerifiedSessionState | null,
    owner: () => OwnerContext | null,
  ) {
    this._transport = transport;
    this._session = session;
    this._owner = owner;
  }

  context(): OwnerContext | null {
    return this._owner();
  }

  currentTargetRef(): string | null {
    const session = this._session();
    return session?.target?.target_ref ?? null;
  }

  /**
   * Build an explicit message intent. The binding supplies its synchronous owner
   * stop-condition provider for the two-argument UI form; neither prepare nor
   * submit calls that provider again. Both strings are carried verbatim, 1..700 code points.
   */
  makeMessageIntent(
    sessionKey: string,
    text: string,
    stopCondition?: string,
  ): CommandIntent | null {
    if (stopCondition === undefined) return null;
    return this.makeSessionMessageIntent(sessionKey, text, stopCondition);
  }

  makeSessionMessageIntent(
    sessionKey: string,
    instruction: string,
    stopCondition: string,
  ): CommandIntent | null {
    const session = this._session();
    if (!session || session.selectionState !== "RESOLVED") return null;
    if (!session.capabilities.send || !session.target) return null;
    if (!boundedText(instruction, MAX_TEXT_CODEPOINTS)) return null;
    if (!boundedText(stopCondition, MAX_TEXT_CODEPOINTS) || !stopCondition.trim()) return null;
    if (!isString(sessionKey) || sessionKey !== session.target.target_ref) {
      return null;
    }
    const owner = this._owner();
    if (!owner) return null;
    const intent: CommandIntent = Object.freeze({
      kind: "message",
      targetKey: session.target.target_ref,
      payload: Object.freeze({
        instruction,
        stop_condition: stopCondition,
        work_ref: session.selection.workRef,
        root_job_id: session.selection.rootJobId,
      }),
    });
    this._captured.set(intent.payload, { scope: owner.principalScope, generation: owner.generation, auth: this._transport.authGeneration() });
    return intent;
  }

  private _intentDrifted(intent: CommandIntent): boolean {
    const captured = this._captured.get(intent.payload);
    if (!captured) return true;
    const owner = this._owner();
    return !owner || owner.principalScope !== captured.scope || owner.generation !== captured.generation ||
      this._transport.authGeneration() !== captured.auth;
  }

  makeStopIntent(_sessionKey?: string): CommandIntent | null {
    // Stop is unavailable in this binding; stop_condition is never cancel.
    return null;
  }

  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind !== "message") throw new Error("INVALID_KIND");
    if (this._intentDrifted(intent)) throw new Error("EPOCH_CHANGED");
    // The existing UI helper rewraps the outer intent, retaining this exact frozen
    // payload. Seal that wrapper before the controller awaits atomic reservation.
    Object.freeze(intent);
    const decoded = this._decodePayload(intent.payload);
    if (!decoded) throw new Error("INVALID_PAYLOAD");
    const session = this._session();
    if (
      !session ||
      session.selectionState !== "RESOLVED" ||
      !session.capabilities.send ||
      !session.target
    ) {
      throw new Error("INVALID_PAYLOAD");
    }
    if (
      decoded.workRef !== session.selection.workRef ||
      decoded.rootJobId !== session.selection.rootJobId
    ) {
      throw new Error("INVALID_PAYLOAD");
    }
    if (intent.targetKey !== session.target.target_ref) {
      throw new Error("INVALID_PAYLOAD");
    }
    // The host-projected continuation key is the sole source of the key.
    return {
      operationKey: session.target.continuation_operation_key,
      kind: "message",
      targetKey: intent.targetKey,
    };
  }

  async submit(
    pointer: OperationPointer,
    intent: CommandIntent,
    signal: AbortSignal,
  ): Promise<EffectReceipt> {
    // Pre-send validation: every refusal below happens before the send call
    // and is scoped to this invocation only.
    if (!validPointerShape(pointer)) {
      return this._receipt(pointer, "refused", "MALFORMED_POINTER");
    }
    const decoded = this._decodePayload(intent.payload);
    if (
      this._intentDrifted(intent) || !decoded ||
      intent.kind !== "message" ||
      !isString(intent.targetKey) ||
      intent.targetKey !== pointer.targetKey
    ) {
      return this._receipt(pointer, "refused", "INVALID_PAYLOAD");
    }
    const session = this._session();
    const owner = this._owner();
    if (
      !owner ||
      !session ||
      session.selectionState !== "RESOLVED" ||
      !session.capabilities.send ||
      !session.target ||
      decoded.workRef !== session.selection.workRef ||
      decoded.rootJobId !== session.selection.rootJobId ||
      pointer.targetKey !== session.target.target_ref ||
      pointer.operationKey !== session.target.continuation_operation_key
    ) {
      return this._receipt(pointer, "refused", "SESSION_UNAVAILABLE");
    }
    if (signal.aborted) {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }

    // Fence snapshot: exact owner, auth generation, selection and target
    // generation. Any change after the send is entered is UNKNOWN, never NONE.
    const scope = owner.principalScope;
    const generation = owner.generation;
    const authGeneration = this._transport.authGeneration();
    const selection = session.selection;
    const targetRef = session.target.target_ref;
    const targetGeneration = session.target.generation;
    const args: SessionSendArguments = {
      target_ref: pointer.targetKey,
      instruction: decoded.instruction,
      stop_condition: decoded.stopCondition,
      operation_key: pointer.operationKey,
    };

    let raw: unknown;
    try {
      raw = await this._transport.send(args, signal);
    } catch {
      return this._receipt(pointer, "unknown", "TRANSPORT_ERROR");
    }
    if (this._drifted(scope, generation, authGeneration, selection, targetRef, targetGeneration) ||
        signal.aborted) {
      return this._receipt(pointer, "unknown", "EPOCH_CHANGED");
    }
    const receipt = await this._mapSend(pointer, raw);
    if (signal.aborted || this._drifted(scope, generation, authGeneration, selection, targetRef, targetGeneration)) {
      return this._receipt(pointer, "unknown", "EPOCH_CHANGED");
    }
    return receipt;
  }

  /** Legacy command-port observation retains its exact receipt-only shape. */
  async readOperation(pointer: OperationPointer, signal: AbortSignal): Promise<EffectReceipt> {
    return (await this.readQualifiedAnswer(pointer, signal)).receipt;
  }

  /** Same fixed READ, original operation and security checks, now exposing
   * the already validated bounded body to the existing Office answer port.
   * Local acceptance cannot mark canonical parent consumption. */
  async readQualifiedAnswer(
    pointer: OperationPointer,
    signal: AbortSignal,
  ): Promise<QualifiedSessionAnswerRead> {
    const withhold = (reason: PortReason): QualifiedSessionAnswerRead =>
      ({ receipt: this._receipt(pointer, "unknown", reason), answer: null });
    if (!validPointerShape(pointer)) {
      return withhold("MALFORMED_POINTER");
    }
    if (signal.aborted) {
      return withhold("TRANSPORT_ERROR");
    }
    const owner = this._owner();
    if (!owner) {
      // Recovery is observation only; without an owner nothing is published
      // and the original pointer is retained untouched.
      return withhold("EPOCH_CHANGED");
    }
    // Recovery uses ONLY the exact original operation key. It never sends,
    // never consults targets and never mints or re-derives a key — the
    // original committed reply stays recoverable after the target disappears.
    const scope = owner.principalScope;
    const generation = owner.generation;
    const authGeneration = this._transport.authGeneration();

    let raw: unknown;
    try {
      raw = await this._transport.reply(
        { operation_key: pointer.operationKey },
        signal,
      );
    } catch {
      return withhold("TRANSPORT_ERROR");
    }
    if (signal.aborted) {
      return withhold("EPOCH_CHANGED");
    }
    const current = this._owner();
    if (
      !current ||
      current.principalScope !== scope ||
      current.generation !== generation ||
      this._transport.authGeneration() !== authGeneration
    ) {
      return withhold("EPOCH_CHANGED");
    }
    // The strict native correlation check awaits WebCrypto. Pin the exact
    // already-bounded frame before that await so a mutable transport object
    // cannot swap text or provenance between validation and local publication.
    let frameBefore: string;
    try {
      frameBefore = JSON.stringify(raw);
    } catch {
      return withhold("MALFORMED_RECEIPT");
    }
    if (typeof frameBefore !== "string") return withhold("MALFORMED_RECEIPT");
    const receipt = await this._mapReply(pointer, raw);
    const finalOwner = this._owner();
    if (signal.aborted || !finalOwner || finalOwner.principalScope !== scope ||
        finalOwner.generation !== generation || this._transport.authGeneration() !== authGeneration) {
      return withhold("EPOCH_CHANGED");
    }
    try {
      if (JSON.stringify(raw) !== frameBefore) return withhold("MALFORMED_RECEIPT");
    } catch {
      return withhold("MALFORMED_RECEIPT");
    }
    // Strict native correlation and bounded text were already proven by
    // _mapReply on THIS one fixed reply frame. Never publish any reply
    // fields on an unknown, foreign or malformed receipt.
    if (receipt.disposition !== "accepted") {
      return { receipt, answer: null };
    }
    const data = decodeEnvelope(raw, "reply")?.data;
    if (!isPlainObject(data) ||
        !boundedText(data.text, REPLY_TEXT_BOUND) ||
        !boundedText(data.next_step, REPLY_TEXT_BOUND) ||
        !isString(data.read_ref) || data.parent_consumed !== false) {
      return withhold("MALFORMED_RECEIPT");
    }
    return {
      receipt,
      answer: Object.freeze({
        text: data.text, nextStep: data.next_step,
        readRef: data.read_ref, parentConsumed: false as const,
      }),
    };
  }

  // ── internals ───────────────────────────────────────────────────────────────

  private _decodePayload(
    payload: Readonly<Record<string, unknown>>,
  ): {
    instruction: string;
    stopCondition: string;
    workRef: string;
    rootJobId: string;
  } | null {
    if (!isPlainObject(payload) || !exactKeys(payload, [...PAYLOAD_KEYS])) {
      return null;
    }
    if (!boundedText(payload.instruction, MAX_TEXT_CODEPOINTS)) return null;
    if (!boundedText(payload.stop_condition, MAX_TEXT_CODEPOINTS) || !payload.stop_condition.trim()) return null;
    if (!validWorkRef(payload.work_ref) || !validRootJobId(payload.root_job_id)) {
      return null;
    }
    return {
      instruction: payload.instruction,
      stopCondition: payload.stop_condition,
      workRef: payload.work_ref,
      rootJobId: payload.root_job_id,
    };
  }

  private _drifted(
    scope: string,
    generation: string,
    authGeneration: number,
    selection: MissionSelection,
    targetRef: string,
    targetGeneration: string,
  ): boolean {
    const owner = this._owner();
    if (
      !owner ||
      owner.principalScope !== scope ||
      owner.generation !== generation
    ) {
      return true;
    }
    if (this._transport.authGeneration() !== authGeneration) return true;
    const session = this._session();
    if (!session) return true;
    if (
      session.selection.workRef !== selection.workRef ||
      session.selection.rootJobId !== selection.rootJobId
    ) {
      return true;
    }
    if (
      session.target?.target_ref !== targetRef ||
      session.target?.generation !== targetGeneration
    ) {
      return true;
    }
    return false;
  }

  private async _mapSend(
    pointer: OperationPointer,
    raw: unknown,
  ): Promise<EffectReceipt> {
    const envelope = decodeEnvelope(raw, "send");
    if (!envelope) return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    if (envelope.ok !== true) {
      // effect NONE is the exact pre-send refusal of THIS invocation; every
      // other failure outcome (including UNKNOWN) retains the pointer.
      if (envelope.effect === "NONE" && validErrorShape(envelope.error) &&
          envelope.data === null &&
          (envelope.operationKey === null || envelope.operationKey === pointer.operationKey)) {
        return this._receipt(
          pointer,
          "refused",
          envelope.error.code === "invalid_input" ? "INVALID_PAYLOAD" : "REFUSED",
        );
      }
      if (envelope.effect === "UNKNOWN") {
        return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
      }
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (envelope.effect !== "CONTINUATION_COMMITTED") {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (envelope.operationKey !== pointer.operationKey) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    if (envelope.error !== null) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    const data = envelope.data as Record<string, unknown>;
    if (!isPlainObject(data) || !exactKeys(data, SEND_DATA_KEYS)) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (data.target_ref !== pointer.targetKey || data.reply_committed !== true) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    const attentionOk =
      isPlainObject(data.attention) && exactKeys(data.attention, ["state"]) &&
      isString(data.attention.state) && ATTENTION_VALUES.has(data.attention.state);
    if (
      !isString(data.read_ref) ||
      !BOUNDED_ID_RE.test(data.read_ref) ||
      !attentionOk
    ) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    const carrier = data.carrier;
    if (!isPlainObject(carrier) || !exactKeys(carrier, CARRIER_KEYS)) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (
      carrier.reply_committed !== true ||
      !isString(carrier.action) ||
      !COMMITTED_ACTIONS.has(carrier.action) ||
      !isString(carrier.message_key) ||
      !isString(carrier.fingerprint) ||
      !FINGERPRINT_RE.test(carrier.fingerprint) ||
      !isString(carrier.thread_ts) ||
      !THREAD_TS_RE.test(carrier.thread_ts)
    ) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (!(await continueMessageKeyBound(pointer.operationKey, carrier.message_key))) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    // Commit proves only the canonical continuation effect. Attention data is
    // retained verbatim and never upgrades or downgrades the receipt.
    return this._receipt(pointer, "accepted", "ACCEPTED");
  }

  private async _mapReply(
    pointer: OperationPointer,
    raw: unknown,
  ): Promise<EffectReceipt> {
    const envelope = decodeEnvelope(raw, "reply");
    if (!envelope) return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    // Every reply failure remains UNKNOWN on the original pointer; it is
    // NEVER cleared, whatever effect label the envelope carries.
    if (envelope.ok !== true) {
      return this._receipt(pointer, "unknown", "UNKNOWN_RECEIPT");
    }
    if (envelope.effect !== "CONTINUATION_COMMITTED") {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (envelope.operationKey !== pointer.operationKey) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    if (envelope.error !== null) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    const data = envelope.data as Record<string, unknown>;
    if (!isPlainObject(data) || !exactKeys(data, REPLY_KEYS)) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (
      data.schema !== NATIVE_REPLY_SCHEMA ||
      data.reply_committed !== true ||
      // No client read ever marks parent consumption.
      data.parent_consumed !== false ||
      data.operation_key !== pointer.operationKey
    ) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    if (
      !isString(data.read_ref) || !BOUNDED_ID_RE.test(data.read_ref) ||
      !isString(data.request_ref) || !BOUNDED_ID_RE.test(data.request_ref) ||
      !isString(data.in_reply_to) || !BOUNDED_ID_RE.test(data.in_reply_to) ||
      !isString(data.message_key) || !/^asd-native-reply-[0-9a-f]{40}$/.test(data.message_key) ||
      !isString(data.fingerprint) || !FINGERPRINT_RE.test(data.fingerprint) ||
      !isString(data.primary_ts) || !THREAD_TS_RE.test(data.primary_ts) ||
      !boundedText(data.text, REPLY_TEXT_BOUND) ||
      !boundedText(data.next_step, REPLY_TEXT_BOUND) ||
      JSON.stringify(data).replace(/[\u007f-\uffff]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")).length > 16384
    ) {
      return this._receipt(pointer, "unknown", "MALFORMED_RECEIPT");
    }
    if (!(await continueMessageKeyBound(pointer.operationKey, data.in_reply_to)) ||
        !(await continueMessageKeyBound(pointer.operationKey, data.message_key, true))) {
      return this._receipt(pointer, "unknown", "RECEIPT_MISMATCH");
    }
    return this._receipt(pointer, "accepted", "ACCEPTED");
  }

  private _receipt(
    pointer: OperationPointer,
    disposition: EffectReceipt["disposition"],
    reason: PortReason,
  ): EffectReceipt {
    return {
      operationKey: pointer.operationKey,
      kind: pointer.kind,
      targetKey: pointer.targetKey,
      disposition,
      reason,
    };
  }
}

// ── Explicit binding factory ──────────────────────────────────────────────────

/**
 * The session binding is the existing OrchestratorCommandBinding shape plus
 * the explicit three-argument message entry; launch and stop mappers are
 * present but always return null in this binding.
 */
export interface ExecutiveSessionBinding extends OrchestratorCommandBinding {
  /** This specific factory installs the actual qualified reply reader, not a generic port. */
  readonly port: ExecutiveSessionCommandPort;
  makeSessionMessageIntent(
    sessionKey: string,
    text: string,
    stopCondition: string,
  ): CommandIntent | null;
}

export interface ExecutiveSessionBindingHandle {
  readonly binding: ExecutiveSessionBinding;
  readonly ready: Promise<void>;
  refresh(): Promise<void>;
  dispose(): void;
  sessionState(): VerifiedSessionState | null;
}

export interface ExecutiveSessionBindingDependencies {
  readonly transport: ExecutiveSessionTransport;
  readonly store: PendingPointerStore;
  /** Currently selected Mission, owned by the host; never parsed here. */
  readonly selection: () => MissionSelection | null;
  /** Explicit synchronous owner condition; captured once when the UI creates an intent. */
  readonly stopCondition: () => unknown;
  clock?: () => number;
}

const EMPTY_BINDING_VIEW = {
  projects: [],
  profiles: [],
  session: null,
} as const;

/**
 * Compose the verified session host, the session port and the injected atomic
 * pending-pointer store into the existing OrchestratorCommandBinding shape.
 * No route registration, runtime, listener, provider or credential is created
 * here. Launch and stop intents are null in this binding; the explicit
 * `makeSessionMessageIntent` entry carries the caller-provided stop_condition.
 */
export function createExecutiveSessionBinding(
  deps: ExecutiveSessionBindingDependencies,
): ExecutiveSessionBindingHandle {
  const now = deps.clock ?? Date.now;
  const transport = deps.transport;
  let epoch = 0;
  let verified: VerifiedSessionState | null = null;
  let verifiedAuthGeneration: number | null = null;
  let disposed = false;
  let expiryTimer: ReturnType<typeof setTimeout> | undefined;
  let boundary = new AbortController();
  const listeners = new Set<() => void>();
  const notify = () => {
    for (const listener of listeners) listener();
  };

  function invalidate(): void {
    epoch++;
    verified = null;
    verifiedAuthGeneration = null;
    boundary.abort();
    boundary = new AbortController();
    clearTimeout(expiryTimer);
    expiryTimer = undefined;
    notify();
  }

  const sessionState = (): VerifiedSessionState | null => {
    const current = deps.selection();
    return !disposed && verified !== null && now() < verified.expiresAtMs &&
      verifiedAuthGeneration === transport.authGeneration() && transport.available() &&
      current?.workRef === verified.selection.workRef && current?.rootJobId === verified.selection.rootJobId
      ? verified : null;
  };

  const ownerContext = (): OwnerContext | null =>
    sessionState() === null
      ? null
      : { principalScope: verified!.principalScope, generation: String(epoch) };

  const port = new ExecutiveSessionCommandPort(transport, sessionState, ownerContext);

  async function refresh(): Promise<void> {
    invalidate();
    if (disposed || !transport.available()) return;
    const selected = deps.selection();
    if (!selected) return;
    const selection = Object.freeze({ ...selected });
    const capturedEpoch = epoch;
    const authGeneration = transport.authGeneration();
    const signal = boundary.signal;
    try {
      const raw = await transport.context(selection, signal);
      if (
        disposed ||
        signal.aborted ||
        capturedEpoch !== epoch ||
        authGeneration !== transport.authGeneration()
      ) {
        return;
      }
      const current = deps.selection();
      if (
        !current ||
        current.workRef !== selection.workRef ||
        current.rootJobId !== selection.rootJobId
      ) {
        return;
      }
      // The authenticated envelope is the sole source of the principal scope;
      // a first refresh has no prior verified state to fence it against.
      const decoded = decodeSessionContext(raw, selection);
      if (!decoded || decoded.expiresAtMs <= now()) return;
      verified = decoded;
      verifiedAuthGeneration = authGeneration;
      const delay = decoded.expiresAtMs - now();
      expiryTimer = setTimeout(() => {
        if (capturedEpoch === epoch) invalidate();
      }, Math.min(Math.max(delay, 0), 2_147_483_647));
      notify();
    } catch {
      // No transport or auth error text is exposed; the session stays
      // unavailable and any pending pointer keeps its original scope.
    }
  }

  const binding: ExecutiveSessionBinding = {
    port,
    store: deps.store,
    getView: () => EMPTY_BINDING_VIEW,
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    makeLaunchIntent: () => null,
    makeMessageIntent: (sessionKey, text) => {
      if (!sessionState() || !deps.stopCondition) return null;
      try {
        const condition = deps.stopCondition();
        return typeof condition === "string"
          ? port.makeSessionMessageIntent(sessionKey, text, condition) : null;
      } catch { return null; }
    },
    makeStopIntent: () => null,
    makeSessionMessageIntent: (sessionKey, text, stopCondition) =>
      port.makeSessionMessageIntent(sessionKey, text, stopCondition),
  };

  const unsubscribe = transport.subscribe(() => {
    void refresh();
  });
  const ready = refresh();
  return {
    binding,
    ready,
    refresh,
    sessionState,
    dispose() {
      if (disposed) return;
      disposed = true;
      unsubscribe();
      invalidate();
      listeners.clear();
    },
  };
}
