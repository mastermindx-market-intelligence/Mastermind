/** Closed request/result wire for the incumbent fresh-conversation consume and
 * turn composition (P16.T1.S34.S1).
 *
 * Pure TypeScript translation of the frozen Python turn wire at source pin
 * d4bcad271f1a95dd730b18ea56f9d468bad9658c: the five-field outer envelope
 * (`mastermind.executive.fresh_conversation_result.v1`), the turn DATA shape
 * (`mastermind.executive.fresh_conversation_turn_data.v1`), the conversation
 * reference selector (`mastermind.fresh_conversation_reference.v1`), and the
 * request syntax for consume / turn / turn_status / turn_read and the
 * successor readonly consume_status / pure turn_preview branches. The producer-sealed RECORDED result is validated
 * through the existing strict initial-result reader bound to the actual
 * locator — not merely its summary/digest. Parsing/validation grants no
 * admission, permission, consumption or send authority: every decoded value
 * stays data, `can_send`/`effect` remain producer claims, and nothing here is
 * transported, stored, rendered or acted on. No window, lifecycle, store or
 * runtime effect lives in this module.
 * f3574ad06 adds readonly consume_status, pure turn_preview and optional
 * turn preview_digest; actual successor-fixture acceptance is separate.
 */
import { decodeFreshConversationInitialResult } from "./fresh-conversation";
import type { FreshConversationPayload } from "./fresh-conversation";

/** The reference-mode operations of the frozen wire. */
export type FreshConversationTurnOperation =
  | "consume"
  | "turn"
  | "turn_status"
  | "turn_read"
  | "consume_status"
  | "turn_preview";

/** Closed conversation reference selector. Scalar fields only; validated
 * whole-string against the frozen Python laws. */
export interface FreshConversationReference {
  readonly schema: "mastermind.fresh_conversation_reference.v1";
  readonly work_ref: string;
  readonly root_job_id: string;
  readonly root_event_id: number;
  readonly root_event_sha256: string;
  readonly principal_scope_sha256: string;
}

/** Closed request union for the turn wire. Exactly one selector — a genuine
 * reference or a genuine operation key — never both, and never a surrogate. */
export type FreshConversationTurnRequest =
  | {
      readonly work_ref: string;
      readonly reference: FreshConversationReference;
      readonly initial_digest: string;
    }
  | {
      readonly work_ref: string;
      readonly reference: FreshConversationReference;
      readonly initial_digest: string;
      readonly message: string;
      readonly turn_key: string;
      readonly preview_digest?: string;
    }
  | {
      readonly work_ref: string;
      readonly reference: FreshConversationReference;
      readonly turn_key: string;
    }
  | {
      readonly work_ref: string;
      readonly operation_key: string;
      readonly initial_digest: string;
    }
  | {
      readonly work_ref: string;
      readonly operation_key: string;
      readonly initial_digest: string;
      readonly message: string;
      readonly turn_key: string;
      readonly preview_digest?: string;
    }
  | {
      readonly work_ref: string;
      readonly operation_key: string;
      readonly turn_key: string;
    };

export type FreshConversationTurnState =
  | "CONSUMED"
  | "ABSENT"
  | "RECONCILIATION_REQUIRED"
  | "RECORDED";

export type FreshConversationTurnEffect = "NONE" | "COMMITTED" | "UNKNOWN";

export interface FreshConversationTurnConsumption {
  readonly state: "CONSUMED";
  readonly event_id: number;
  readonly event_sha256: string;
  readonly initial_digest: string;
}

export interface FreshConversationTurnLocator {
  readonly work_ref: string;
  readonly root_job_id: string;
  readonly job_id: string | null;
  readonly attempt_id: string | null;
}

export interface FreshConversationTurnData {
  readonly schema: "mastermind.executive.fresh_conversation_turn_data.v1";
  readonly work_ref: string;
  readonly operation_key: string | null;
  readonly reference: FreshConversationReference | null;
  readonly turn_key: string | null;
  readonly state: FreshConversationTurnState;
  readonly effect: FreshConversationTurnEffect;
  readonly initial_consumption: FreshConversationTurnConsumption | null;
  readonly locator: FreshConversationTurnLocator;
  /** Producer-sealed result; non-null only for RECORDED, and re-verified
   * against the exact locator envelope, not merely its summary/digest. */
  readonly result: FreshConversationPayload | null;
  /** Always false on this wire: a false flag is never an initial receipt. */
  readonly parent_consumed: false;
  /** Producer claim. True is only wire-consistent with state CONSUMED. */
  readonly can_send: boolean;
}

export interface FreshConversationTurnError {
  readonly code: string;
  readonly message: string;
}

/** Normalized decoded response AFTER validating the actual five-field wire
 * envelope, schema and operation. Never accepts a pre-normalized surrogate. */
export type FreshConversationTurnResult =
  | { readonly ok: true; readonly data: FreshConversationTurnData }
  | { readonly ok: false; readonly data: null; readonly error: FreshConversationTurnError };

const TURN_OPERATIONS: ReadonlySet<string> = new Set([
  "consume",
  "turn",
  "turn_status",
  "turn_read",
  "consume_status",
  "turn_preview",
]);

// Python `re.fullmatch` semantics: a leading anchor only, and the whole string
// must be consumed — so a trailing newline can never sneak past `$`-style
// end-of-string (or end-before-final-newline) allowances.
const WORK_REF_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}/;
const OPERATION_KEY_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}/;
const HEX64_RE = /^[0-9a-f]{64}/;
const ROOT_JOB_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}/;

const TURN_RESULT_SCHEMA = "mastermind.executive.fresh_conversation_result.v1";
const TURN_DATA_SCHEMA = "mastermind.executive.fresh_conversation_turn_data.v1";
const REFERENCE_SCHEMA = "mastermind.fresh_conversation_reference.v1";

const OUTER_KEYS = ["schema", "operation", "ok", "data", "error"] as const;
const TURN_DATA_KEYS = [
  "schema",
  "work_ref",
  "operation_key",
  "reference",
  "turn_key",
  "state",
  "effect",
  "initial_consumption",
  "locator",
  "result",
  "parent_consumed",
  "can_send",
] as const;
const CONSUMPTION_KEYS = ["state", "event_id", "event_sha256", "initial_digest"] as const;
const LOCATOR_KEYS = ["work_ref", "root_job_id", "job_id", "attempt_id"] as const;
const REFERENCE_KEYS = [
  "schema",
  "work_ref",
  "root_job_id",
  "root_event_id",
  "root_event_sha256",
  "principal_scope_sha256",
] as const;
const ERROR_KEYS = ["code", "message"] as const;

const TURN_STATES: ReadonlySet<string> = new Set([
  "CONSUMED",
  "ABSENT",
  "RECONCILIATION_REQUIRED",
  "RECORDED",
]);
const TURN_EFFECTS: ReadonlySet<string> = new Set(["NONE", "COMMITTED", "UNKNOWN"]);

const MESSAGE_MAX_CODE_POINTS = 700;
const MESSAGE_MAX_UTF8_BYTES = 2800;
const ERROR_CODE_MAX = 96;
const ERROR_MESSAGE_MAX = 512;

const encoder = new TextEncoder();

function utf8Length(value: string): number {
  return encoder.encode(value).length;
}

/** Python `str.strip()` whitespace: Unicode White_Space plus U+001C–U+001F.
 * U+FEFF is deliberately excluded (Python does not strip a BOM). */
function isStripWhitespace(cp: number): boolean {
  return (
    (cp >= 0x09 && cp <= 0x0d) ||
    (cp >= 0x1c && cp <= 0x1f) ||
    cp === 0x20 ||
    cp === 0x85 ||
    cp === 0xa0 ||
    cp === 0x1680 ||
    (cp >= 0x2000 && cp <= 0x200a) ||
    cp === 0x2028 ||
    cp === 0x2029 ||
    cp === 0x202f ||
    cp === 0x205f ||
    cp === 0x3000
  );
}

function isControlFree(cp: number): boolean {
  return !(cp < 0x20 || cp === 0x7f || (cp >= 0x80 && cp <= 0x9f));
}

/** Iterate code points; a `for..of` step yields a lone surrogate only when
 * the string really contains one, so any 0xD800–0xDFFF here is unpaired. */
function codePointsOk(value: string, accept: (cp: number) => boolean): boolean {
  for (const ch of value) {
    if (!accept(ch.codePointAt(0)!)) return false;
  }
  return true;
}

/** Exactly `dict`-like input: own enumerable value keys only, no array or
 * foreign prototype, no accessor stands-ins. `__proto__` can only ever be an
 * own data key here, and it is never assigned or invoked. */
function plainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(key => typeof key === "string" &&
    descriptors[key]?.enumerable === true && Object.hasOwn(descriptors[key], "value"));
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const own = Object.keys(value);
  if (own.length !== keys.length) return false;
  return keys.every((key) => Object.hasOwn(value, key));
}

/** Python `re.fullmatch`: the regex consumes the entire string. Implemented
 * as longest-prefix match plus exact length, so "…\n" (which `$` would
 * wrongly accept before a final newline) is rejected like Python's `\Z`. */
function fullMatch(regex: RegExp, value: string): boolean {
  const match = regex.exec(value);
  return match !== null && match[0].length === value.length;
}

function isHex64(value: unknown): value is string {
  return typeof value === "string" && fullMatch(HEX64_RE, value);
}

/** Python `type(x) is int`: no bool, no float stand-in. */
function isWireInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

/** Non-empty, control-free, no unpaired surrogate, bounded in code points. */
function isBoundedText(value: unknown, maxCodePoints: number): value is string {
  if (typeof value !== "string" || value.length === 0) return false;
  let count = 0;
  return (
    codePointsOk(value, (cp) => {
      if (!isControlFree(cp) || (cp >= 0xd800 && cp <= 0xdfff)) return false;
      count += 1;
      return count <= maxCodePoints;
    }) && count > 0
  );
}

/** Python message rule: 1–700 code points, ≤2800 UTF-8 bytes, no C0 except
 * TAB/LF/CR, nothing in U+007F–U+009F, no unpaired surrogate (Python's strict
 * UTF-8 encode rejects those), not all whitespace under `str.strip()`. The
 * literal is never trimmed or normalized. */
function isMessage(value: unknown): value is string {
  if (typeof value !== "string") return false;
  let allWhitespace = true;
  let codePointCount = 0;
  const shapeOk = codePointsOk(value, (cp) => {
    if (!isStripWhitespace(cp)) allWhitespace = false;
    if (cp < 0x20 && cp !== 0x09 && cp !== 0x0a && cp !== 0x0d) return false;
    if (cp >= 0x7f && cp <= 0x9f) return false;
    if (cp >= 0xd800 && cp <= 0xdfff) return false;
    codePointCount += 1;
    return codePointCount <= MESSAGE_MAX_CODE_POINTS;
  });
  if (!shapeOk || allWhitespace) return false;
  return utf8Length(value) <= MESSAGE_MAX_UTF8_BYTES;
}

function isTurnOperation(value: unknown): value is FreshConversationTurnOperation {
  return typeof value === "string" && TURN_OPERATIONS.has(value);
}

/** Validate and detach the closed conversation reference. Returns null for
 * anything that is not exactly the frozen six-field scalar shape. */
export function validateFreshConversationReference(
  value: unknown,
): FreshConversationReference | null {
  try {
    if (!plainObject(value) || !exactKeys(value, REFERENCE_KEYS)) return null;
    if (value.schema !== REFERENCE_SCHEMA) return null;
    const workRef = value.work_ref;
    if (typeof workRef !== "string" || !fullMatch(WORK_REF_RE, workRef)) return null;
    const rootJobId = value.root_job_id;
    if (typeof rootJobId !== "string" || !fullMatch(ROOT_JOB_ID_RE, rootJobId)) {
      return null;
    }
    const rootEventId = value.root_event_id;
    if (!isWireInt(rootEventId) || rootEventId < 1) return null;
    const rootEventSha = value.root_event_sha256;
    if (!isHex64(rootEventSha)) return null;
    const principalScopeSha = value.principal_scope_sha256;
    if (!isHex64(principalScopeSha)) return null;
    return {
      schema: REFERENCE_SCHEMA,
      work_ref: workRef,
      root_job_id: rootJobId,
      root_event_id: rootEventId,
      root_event_sha256: rootEventSha,
      principal_scope_sha256: principalScopeSha,
    };
  } catch {
    return null;
  }
}

/** Field-wise closed equality between a decoded data reference and the
 * expected reference (or absence). Deep-equal of the validated scalar shape. */
function sameReference(value: unknown, expected: FreshConversationReference | null): boolean {
  if (expected === null) return value === null;
  if (!plainObject(value)||!exactKeys(value,REFERENCE_KEYS)) return false;
  return (
    value.schema === expected.schema &&
    value.work_ref === expected.work_ref &&
    value.root_job_id === expected.root_job_id &&
    value.root_event_id === expected.root_event_id &&
    value.root_event_sha256 === expected.root_event_sha256 &&
    value.principal_scope_sha256 === expected.principal_scope_sha256
  );
}

/** Closed request syntax for consume/turn/turn_status/turn_read, translated
 * from the frozen Python `validate_request` (reference-mode branch included).
 * Returns a detached closed-union request, or null for malformed input. */
export function validateFreshConversationTurnRequest(
  value: unknown,
  operation: FreshConversationTurnOperation,
): FreshConversationTurnRequest | null {
  try {
    if (!isTurnOperation(operation) || !plainObject(value)) return null;
    const referenceMode = Object.hasOwn(value,"reference");
    const consumeLike=operation==="consume"||operation==="consume_status";
    const messageLike=operation==="turn"||operation==="turn_preview";
    const hasPreview=operation==="turn"&&Object.hasOwn(value,"preview_digest");
    const keys=["work_ref",referenceMode?"reference":"operation_key"];
    if(consumeLike)keys.push("initial_digest");
    if(messageLike)keys.push("message","initial_digest","turn_key");
    if(operation==="turn_status"||operation==="turn_read")keys.push("turn_key");
    if(hasPreview)keys.push("preview_digest");
    if(!exactKeys(value,keys))return null;
    const workRef=value.work_ref;
    if(typeof workRef!=="string"||!fullMatch(WORK_REF_RE,workRef))return null;
    const reference=referenceMode?validateFreshConversationReference(value.reference):null;
    if(referenceMode&&(!reference||reference.work_ref!==workRef))return null;
    const operationKey=value.operation_key;
    if(!referenceMode&&(typeof operationKey!=="string"||!fullMatch(OPERATION_KEY_RE,operationKey)))return null;
    const selected=reference?{work_ref:workRef,reference}:{work_ref:workRef,operation_key:operationKey as string};
    if(consumeLike){
      if(!isHex64(value.initial_digest))return null;
      return {...selected,initial_digest:value.initial_digest};
    }
    const turnKey=value.turn_key;
    if(typeof turnKey!=="string"||!fullMatch(OPERATION_KEY_RE,turnKey))return null;
    if(!messageLike)return {...selected,turn_key:turnKey};
    if(!isHex64(value.initial_digest)||!isMessage(value.message))return null;
    if(hasPreview&&!isHex64(value.preview_digest))return null;
    return {...selected,turn_key:turnKey,initial_digest:value.initial_digest,message:value.message,
      ...(hasPreview?{preview_digest:value.preview_digest as string}:{})};
  }catch{return null;}
}

function decodeTurnConsumption(
  value: unknown,
): FreshConversationTurnConsumption | null {
  if (!plainObject(value) || !exactKeys(value, CONSUMPTION_KEYS)) return null;
  if (value.state !== "CONSUMED") return null;
  const eventId = value.event_id;
  if (!isWireInt(eventId) || eventId < 1) return null;
  if (!isHex64(value.event_sha256)) return null;
  if (!isHex64(value.initial_digest)) return null;
  return {
    state: "CONSUMED",
    event_id: eventId,
    event_sha256: value.event_sha256,
    initial_digest: value.initial_digest,
  };
}

/** Original locator: always present on turn DATA; job/attempt ids are real
 * non-empty strings except in the ABSENT state, where only null is allowed. */
function decodeTurnLocator(
  value: unknown,
  workRef: string,
  state: FreshConversationTurnState,
): FreshConversationTurnLocator | null {
  if (!plainObject(value) || !exactKeys(value, LOCATOR_KEYS)) return null;
  const locatorWorkRef = value.work_ref;
  if (typeof locatorWorkRef !== "string" || locatorWorkRef !== workRef) return null;
  const rootJobId = value.root_job_id;
  if (typeof rootJobId !== "string" || rootJobId.length === 0) return null;
  const jobId = value.job_id;
  if (jobId === null) {
    if (state !== "ABSENT") return null;
  } else if (typeof jobId !== "string" || jobId.length === 0) {
    return null;
  }
  const attemptId = value.attempt_id;
  if (attemptId === null) {
    if (state !== "ABSENT") return null;
  } else if (typeof attemptId !== "string" || attemptId.length === 0) {
    return null;
  }
  return {
    work_ref: locatorWorkRef,
    root_job_id: rootJobId,
    job_id: jobId,
    attempt_id: attemptId,
  };
}

function decodeTurnError(value: unknown): FreshConversationTurnError | null {
  if (!plainObject(value) || !exactKeys(value, ERROR_KEYS)) return null;
  if (!isBoundedText(value.code, ERROR_CODE_MAX)) return null;
  if (!isBoundedText(value.message, ERROR_MESSAGE_MAX)) return null;
  return { code: value.code, message: value.message };
}

/** Closed turn DATA, translated from the frozen Python `validate_turn_data`,
 * plus the two wire-agreement duties of this composition: the reference's
 * root job must agree with the returned original locator, and a supplied
 * request initial_digest must agree with the consumption's initial_digest.
 * RECORDED additionally requires consumption plus the actual sealed result
 * re-verified against the exact locator. */
function decodeTurnData(
  value: unknown,
  request: FreshConversationTurnRequest,
): FreshConversationTurnData | null {
  if (!plainObject(value) || !exactKeys(value, TURN_DATA_KEYS)) return null;
  if (value.schema !== TURN_DATA_SCHEMA) return null;
  if (value.work_ref !== request.work_ref) return null;
  const expectedOperationKey =
    "operation_key" in request ? request.operation_key : null;
  if (value.operation_key !== expectedOperationKey) return null;
  const expectedTurnKey = "turn_key" in request ? request.turn_key : null;
  if (value.turn_key !== expectedTurnKey) return null;
  const expectedReference = "reference" in request ? request.reference : null;
  if (!sameReference(value.reference, expectedReference)) return null;
  const requestInitialDigest =
    "initial_digest" in request ? request.initial_digest : undefined;
  if (typeof value.state !== "string" || !TURN_STATES.has(value.state)) return null;
  if (typeof value.effect !== "string" || !TURN_EFFECTS.has(value.effect)) return null;
  // A known-false parent_consumed is data, never an initial receipt.
  if (value.parent_consumed !== false) return null;
  const canSend = value.can_send;
  if (typeof canSend !== "boolean") return null;
  const state = value.state as FreshConversationTurnState;
  const effect = value.effect as FreshConversationTurnEffect;
  // No send claim outside CONSUMED; the claim itself stays producer data.
  if (canSend === true && state !== "CONSUMED") return null;

  let consumption: FreshConversationTurnConsumption | null = null;
  if (value.initial_consumption !== null) {
    consumption = decodeTurnConsumption(value.initial_consumption);
    if (consumption === null) return null;
  }
  if (
    consumption !== null &&
    requestInitialDigest !== undefined &&
    consumption.initial_digest !== requestInitialDigest
  ) {
    return null;
  }

  const locator = decodeTurnLocator(value.locator, request.work_ref, state);
  if (locator === null) return null;
  // The reference's root job must agree with the returned original locator.
  if (
    expectedReference !== null &&
    expectedReference.root_job_id !== locator.root_job_id
  ) {
    return null;
  }

  if (state === "CONSUMED" && consumption === null) return null;

  let payload: FreshConversationPayload | null = null;
  if (state === "RECORDED") {
    if (consumption === null) return null;
    // Strict sealed validation bound to the actual locator — envelope ids,
    // role/status and digest/budget, not merely summary/digest agreement.
    const sealed = decodeFreshConversationInitialResult(value.result, {
      job_id: locator.job_id,
      attempt_id: locator.attempt_id,
      root_job_id: locator.root_job_id,
    });
    if (sealed === null) return null;
    payload = sealed;
  } else if (value.result !== null) {
    return null;
  }

  return {
    schema: TURN_DATA_SCHEMA,
    work_ref: request.work_ref,
    operation_key: expectedOperationKey,
    reference: expectedReference,
    turn_key: expectedTurnKey,
    state,
    effect,
    initial_consumption: consumption,
    locator,
    result: payload,
    parent_consumed: false,
    can_send: canSend,
  };
}

/** Decode the five-field turn wire envelope against an expected request.
 * The expected request itself is re-validated (no surrogate, no foreign
 * selector), the outer schema/operation must match exactly, and the
 * normalized ok/data/error union is produced only after full wire
 * validation. Null for malformed input. */
export function decodeFreshConversationTurnResult(
  value: unknown,
  operation: FreshConversationTurnOperation,
  expectedRequest: unknown,
): FreshConversationTurnResult | null {
  try {
    if (!isTurnOperation(operation)||operation==="turn_preview") return null;
    const request = validateFreshConversationTurnRequest(expectedRequest, operation);
    if (request === null) return null;
    if (
      !plainObject(value) ||
      !exactKeys(value, OUTER_KEYS) ||
      value.schema !== TURN_RESULT_SCHEMA ||
      value.operation !== operation
    ) {
      return null;
    }
    if (value.ok === true) {
      if (value.error !== null) return null;
      const data = decodeTurnData(value.data, request);
      if (data === null) return null;
      if(operation==="consume_status"&&(
        data.can_send!==false||
        !(data.state==="CONSUMED"&&data.effect==="COMMITTED"&&data.initial_consumption!==null||
          data.state==="ABSENT"&&data.effect==="NONE"&&data.initial_consumption===null)))return null;
      return { ok: true, data };
    }
    if (value.ok === false) {
      if (value.data !== null) return null;
      const error = decodeTurnError(value.error);
      if (error === null) return null;
      // Preserved as data only: no UI, disposition or permission decision.
      return { ok: false, data: null, error };
    }
    return null;
  } catch {
    return null;
  }
}


/** Pure f357 preview DATA. Readiness is never permission or an effect receipt. */
export interface FreshConversationTurnPreviewData {
 readonly schema:"mastermind.executive.fresh_conversation_turn_preview.v1";
 readonly work_ref:string;
 readonly operation_key:string|null;
 readonly reference:FreshConversationReference|null;
 readonly turn_key:string;
 readonly state:"TURN_READY";
 readonly effect:"NONE";
 readonly initial_consumption:FreshConversationTurnConsumption;
 readonly locator:FreshConversationTurnLocator;
 readonly preview_digest:string;
 readonly parent_consumed:false;
 readonly can_send:true;
}
export type FreshConversationTurnPreviewResult=
 |{readonly ok:true;readonly data:FreshConversationTurnPreviewData}
 |{readonly ok:false;readonly data:null;readonly error:FreshConversationTurnError};
const TURN_PREVIEW_SCHEMA="mastermind.executive.fresh_conversation_turn_preview.v1";
const TURN_PREVIEW_KEYS=["schema","work_ref","operation_key","reference","turn_key","state","effect",
 "initial_consumption","locator","preview_digest","parent_consumed","can_send"] as const;

/** Separate preview reader: a TURN_READY frame can never become an accepted
 * Keep/turn receipt merely by passing through the ordinary result decoder. */
export function decodeFreshConversationTurnPreviewResult(value:unknown,expectedRequest:unknown):FreshConversationTurnPreviewResult|null{
 try{
  const request=validateFreshConversationTurnRequest(expectedRequest,"turn_preview");
  if(!request||!("turn_key" in request)||!plainObject(value)||!exactKeys(value,OUTER_KEYS)||
    value.schema!==TURN_RESULT_SCHEMA||value.operation!=="turn_preview")return null;
  if(value.ok===false){
   if(value.data!==null)return null;const error=decodeTurnError(value.error);
   return error?{ok:false,data:null,error}:null;
  }
  if(value.ok!==true||value.error!==null||!plainObject(value.data)||!exactKeys(value.data,TURN_PREVIEW_KEYS))return null;
  const raw=value.data;
  if(raw.schema!==TURN_PREVIEW_SCHEMA||raw.state!=="TURN_READY"||raw.effect!=="NONE"||
    raw.parent_consumed!==false||raw.can_send!==true||!isHex64(raw.preview_digest))return null;
  // The frozen Python owner reuses the same receipt/selector/locator checks.
  // This internal parse projection is not a producer frame or an effect.
  const {preview_digest:previewDigest,...fields}=raw;
  const data=decodeTurnData({...fields,schema:TURN_DATA_SCHEMA,state:"CONSUMED",result:null},request);
  if(!data||!data.initial_consumption)return null;
  return {ok:true,data:{schema:TURN_PREVIEW_SCHEMA,work_ref:data.work_ref,operation_key:data.operation_key,
    reference:data.reference,turn_key:request.turn_key,state:"TURN_READY",effect:"NONE",
    initial_consumption:data.initial_consumption,locator:data.locator,preview_digest:previewDigest as string,
    parent_consumed:false,can_send:true}};
 }catch{return null;}
}
