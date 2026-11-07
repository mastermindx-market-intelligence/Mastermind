/** Closed request/result wire for the incumbent fresh conversation composition.
 *
 * Pure TypeScript translation of the frozen Python wire at pin
 * 30a7400f6fe71b4a89e039451d4470fc41bf4608
 * (`mastermind.executive.fresh_conversation.v1`): request syntax, response DATA
 * shape, and the result digest check. Parsing/validation grants no admission,
 * permission, consumption or send authority — every decoded value stays data.
 * No operation key is minted here and nothing is transported or stored.
 */
import { canonicalJson, sha256Hex } from "../../orchestration/operation-key";

export type FreshConversationOperation = "preview" | "create" | "status" | "read";

const OPERATIONS: ReadonlySet<string> = new Set(["preview", "create", "status", "read"]);

export type FreshConversationRequest =
  | { readonly work_ref: string; readonly operation_key: string }
  | {
      readonly work_ref: string;
      readonly operation_key: string;
      readonly message: string;
    }
  | {
      readonly work_ref: string;
      readonly operation_key: string;
      readonly message: string;
      readonly preview_digest: string;
    };

export type FreshConversationState =
  | "PREVIEW_READY"
  | "ABSENT"
  | "ADMITTED"
  | "CREATED"
  | "SETTLED"
  | "RECONCILIATION_REQUIRED";

export type FreshConversationEffect = "NONE" | "ADMITTED" | "COMMITTED";

/** Plain JSON value; strings carry no unpaired surrogate, numbers are finite. */
export type FreshConversationJsonValue =
  | string
  | number
  | boolean
  | null
  | readonly FreshConversationJsonValue[]
  | { readonly [key: string]: FreshConversationJsonValue };

export interface FreshConversationPreview {
  readonly digest: string;
  readonly profile_digest: string;
  readonly source_digest: string;
  /** Opaque producer JSON. Never a permission source; never rendered as authority. */
  readonly grounding: FreshConversationJsonValue;
  readonly attempt_limit: 1;
  readonly worker_account: "REGISTERED_NOT_SESSION_ATTESTED";
}

export interface FreshConversationLocator {
  readonly work_ref: string;
  readonly root_job_id: string;
  readonly job_id: string | null;
  readonly attempt_id: string | null;
}

export interface FreshConversationSession {
  readonly attempt_id: string;
  readonly generation: string;
  readonly binding_digest: string;
}

/** Producer-sealed role result. Digest re-verified against the exact envelope. */
export interface FreshConversationPayload {
  readonly digest: string;
  readonly envelope: FreshConversationJsonValue;
}

export interface FreshConversationData {
  readonly schema: "mastermind.executive.fresh_conversation_data.v1";
  readonly operation_key: string;
  readonly work_ref: string;
  readonly state: FreshConversationState;
  readonly effect: FreshConversationEffect;
  readonly parent_consumed: false;
  readonly can_send: false;
  readonly preview: FreshConversationPreview | null;
  readonly locator: FreshConversationLocator | null;
  readonly session: FreshConversationSession | null;
  /** Producer-sealed result; non-null only for a read of CREATED/SETTLED. */
  readonly result: FreshConversationPayload | null;
}

export interface FreshConversationError {
  readonly code: string;
  readonly message: string;
}

/** Normalized decoded response AFTER validating the actual five-field wire
 * envelope, schema and operation. Never accepts a pre-normalized surrogate. */
export type FreshConversationResult =
  | { readonly ok: true; readonly data: FreshConversationData }
  | {
      readonly ok: false;
      readonly data: null;
      readonly error: FreshConversationError;
    };

const WORK_REF_RE = /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,68}$/;
const OPERATION_KEY_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;

const DATA_SCHEMA = "mastermind.executive.fresh_conversation_data.v1";
const DATA_KEYS = [
  "schema",
  "operation_key",
  "work_ref",
  "state",
  "effect",
  "parent_consumed",
  "preview",
  "locator",
  "session",
  "result",
  "can_send",
] as const;
const PREVIEW_KEYS = [
  "digest",
  "profile_digest",
  "source_digest",
  "grounding",
  "attempt_limit",
  "worker_account",
] as const;
const LOCATOR_KEYS = ["work_ref", "root_job_id", "job_id", "attempt_id"] as const;
const SESSION_KEYS = ["attempt_id", "generation", "binding_digest"] as const;
const ERROR_KEYS = ["code", "message"] as const;

const STATES: ReadonlySet<string> = new Set([
  "PREVIEW_READY",
  "ABSENT",
  "ADMITTED",
  "CREATED",
  "SETTLED",
  "RECONCILIATION_REQUIRED",
]);
const EFFECTS: ReadonlySet<string> = new Set(["NONE", "ADMITTED", "COMMITTED"]);

/** Literal caps carried by the Python wire. */
const MESSAGE_MAX_CODE_POINTS = 700;
const MESSAGE_MAX_UTF8_BYTES = 2800;
const GROUNDING_MAX_UTF8_BYTES = 8192;
const GROUNDING_MAX_DEPTH = 16;
const ENVELOPE_MAX_UTF8_BYTES = 16384;
const ENVELOPE_MAX_DEPTH = 24;
const ID_MAX_CODE_POINTS = 256;
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
function codePointsOk(
  value: string,
  accept: (cp: number) => boolean,
): boolean {
  for (const ch of value) {
    if (!accept(ch.codePointAt(0)!)) return false;
  }
  return true;
}

/** Exactly `dict`-like input: own enumerable keys only, no array/foreign proto. */
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

function exactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  const own = Object.keys(value);
  if (own.length !== keys.length) return false;
  return keys.every((key) => Object.hasOwn(value, key));
}

function isHex64(value: unknown): value is string {
  return typeof value === "string" && HEX64_RE.test(value);
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
 * TAB/LF/CR, nothing in U+007F–U+009F, no unpaired surrogate, not all
 * whitespace under `str.strip()`. The literal is never trimmed or normalized. */
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

/** Validate a value as plain JSON and return its canonical (sorted, compact)
 * encoding, or null when it is not plain JSON, too deep, or too large. */
function canonicalPlainJson(
  value: unknown,
  maxDepth: number,
  maxBytes: number,
): string | null {
  if (!plainObject(value)) return null;
  if (jsonDepth(value, 1, maxDepth) < 0) return null;
  const canonical = canonicalJson(value);
  if (utf8Length(canonical) > maxBytes) return null;
  return canonical;
}

/** Subtree container depth (flat object = 1, scalars are free) or -1 when the
 * value is not plain JSON. The depth cap is checked when entering a container,
 * so cyclic or absurdly nested hostile input terminates bounded instead of
 * overflowing the stack. */
function jsonDepth(value: unknown, depth: number, maxDepth: number): number {
  if (value === null) return 0;
  const kind = typeof value;
  if (kind === "string") {
    return codePointsOk(value as string, (cp) => cp < 0xd800 || cp > 0xdfff)
      ? 0
      : -1;
  }
  if (kind === "boolean") return 0;
  if (kind === "number") return Number.isFinite(value as number) ? 0 : -1;
  if (kind === "object") {
    if (depth > maxDepth) return -1;
    let childMax = 0;
    if (Array.isArray(value)) {
      if (Object.getPrototypeOf(value) !== Array.prototype) return -1;
      const keys = Reflect.ownKeys(value);
      if (keys.length !== value.length + 1) return -1;
      const descriptors = Object.getOwnPropertyDescriptors(value);
      for (let i = 0; i < value.length; i++) {
        const descriptor = descriptors[String(i)];
        if (!descriptor || !descriptor.enumerable || !Object.hasOwn(descriptor, "value")) return -1;
      }
      for (const item of value as unknown[]) {
        const child = jsonDepth(item, depth + 1, maxDepth);
        if (child < 0) return -1;
        if (child > childMax) childMax = child;
      }
      return childMax + 1;
    }
    if (
      plainObject(value)
    ) {
      const record = value as Record<string, unknown>;
      for (const key of Object.keys(record)) {
        if (!codePointsOk(key, cp => cp < 0xd800 || cp > 0xdfff)) return -1;
        const child = jsonDepth(record[key], depth + 1, maxDepth);
        if (child < 0) return -1;
        if (child > childMax) childMax = child;
      }
      return childMax + 1;
    }
    return -1; // Date, Map, class instance, …
  }
  return -1; // undefined, function, bigint, symbol
}

/** Fresh deep copy of already-validated plain JSON; never aliases the input. */
function detachJson(value: FreshConversationJsonValue): FreshConversationJsonValue {
  if (Array.isArray(value)) {
    return value.map((item) => detachJson(item as FreshConversationJsonValue));
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, FreshConversationJsonValue> = {};
    for (const key of Object.keys(value as Record<string, unknown>)) {
      Object.defineProperty(out, key, {enumerable:true, writable:true, configurable:true,
        value:detachJson((value as Record<string, unknown>)[key] as FreshConversationJsonValue)});
    }
    return out;
  }
  return value;
}

export function validateFreshConversationRequest(
  value: unknown,
  operation: FreshConversationOperation,
): FreshConversationRequest | null {
  try {
    if (typeof operation !== "string" || !OPERATIONS.has(operation)) return null;
    if (!plainObject(value)) return null;
    const keys: string[] = ["work_ref", "operation_key"];
    if (operation === "preview" || operation === "create") keys.push("message");
    if (operation === "create") keys.push("preview_digest");
    if (!exactKeys(value, keys)) return null;
    const workRef = value.work_ref;
    const operationKey = value.operation_key;
    if (
      typeof workRef !== "string" ||
      !WORK_REF_RE.test(workRef) ||
      typeof operationKey !== "string" ||
      !OPERATION_KEY_RE.test(operationKey)
    ) {
      return null;
    }
    let message: string | undefined;
    if (operation === "preview" || operation === "create") {
      if (!isMessage(value.message)) return null;
      message = value.message;
    }
    let previewDigest: string | undefined;
    if (operation === "create") {
      if (!isHex64(value.preview_digest)) return null;
      previewDigest = value.preview_digest;
    }
    // Detached copy: own fields only, originals untouched (message included).
    if (operation === "create") {
      return {
        work_ref: workRef,
        operation_key: operationKey,
        message: message!,
        preview_digest: previewDigest!,
      };
    }
    if (operation === "preview") {
      return {
        work_ref: workRef,
        operation_key: operationKey,
        message: message!,
      };
    }
    return { work_ref: workRef, operation_key: operationKey };
  } catch {
    return null;
  }
}

function decodePreview(value: unknown): FreshConversationPreview | null {
  if (!plainObject(value) || !exactKeys(value, PREVIEW_KEYS)) return null;
  if (
    !isHex64(value.digest) ||
    !isHex64(value.profile_digest) ||
    !isHex64(value.source_digest)
  ) {
    return null;
  }
  // Literal 1: rejects 2, "1", true, null and every other stand-in.
  if (value.attempt_limit !== 1) return null;
  if (value.worker_account !== "REGISTERED_NOT_SESSION_ATTESTED") return null;
  const grounding = canonicalPlainJson(
    value.grounding,
    GROUNDING_MAX_DEPTH,
    GROUNDING_MAX_UTF8_BYTES,
  );
  if (grounding === null) return null;
  return {
    digest: value.digest,
    profile_digest: value.profile_digest,
    source_digest: value.source_digest,
    grounding: detachJson(value.grounding as FreshConversationJsonValue),
    attempt_limit: 1,
    worker_account: "REGISTERED_NOT_SESSION_ATTESTED",
  };
}

function decodeLocator(
  value: unknown,
  workRef: string,
): FreshConversationLocator | null {
  if (!plainObject(value) || !exactKeys(value, LOCATOR_KEYS)) return null;
  if (value.work_ref !== workRef) return null;
  if (!isBoundedText(value.root_job_id, ID_MAX_CODE_POINTS)) return null;
  if (value.job_id !== null && !isBoundedText(value.job_id, ID_MAX_CODE_POINTS)) {
    return null;
  }
  if (
    value.attempt_id !== null &&
    !isBoundedText(value.attempt_id, ID_MAX_CODE_POINTS)
  ) {
    return null;
  }
  return {
    work_ref: value.work_ref as string,
    root_job_id: value.root_job_id as string,
    job_id: (value.job_id ?? null) as string | null,
    attempt_id: (value.attempt_id ?? null) as string | null,
  };
}

function decodeSession(
  value: unknown,
  attemptId: string,
): FreshConversationSession | null {
  if (!plainObject(value) || !exactKeys(value, SESSION_KEYS)) return null;
  if (!isBoundedText(value.attempt_id, ID_MAX_CODE_POINTS)) return null;
  // Actual attempt must equal the locator's; never invented or derived here.
  if (value.attempt_id !== attemptId) return null;
  if (!isBoundedText(value.generation, ID_MAX_CODE_POINTS)) return null;
  if (!isHex64(value.binding_digest)) return null;
  return {
    attempt_id: value.attempt_id as string,
    generation: value.generation as string,
    binding_digest: value.binding_digest as string,
  };
}

function decodePayload(value: unknown): FreshConversationPayload | null {
  if (!plainObject(value) || !exactKeys(value, ["digest", "envelope"])) {
    return null;
  }
  if (!isHex64(value.digest)) return null;
  const canonical = canonicalPlainJson(
    value.envelope,
    ENVELOPE_MAX_DEPTH,
    ENVELOPE_MAX_UTF8_BYTES,
  );
  if (canonical === null) return null;
  // Existing hash helper; no duplicated hashing, no digest invention.
  if (sha256Hex(canonical) !== value.digest) return null;
  return {
    digest: value.digest,
    envelope: detachJson(value.envelope as FreshConversationJsonValue),
  };
}

function decodeError(value: unknown): FreshConversationError | null {
  if (!plainObject(value) || !exactKeys(value, ERROR_KEYS)) return null;
  if (!isBoundedText(value.code, ERROR_CODE_MAX)) return null;
  if (!isBoundedText(value.message, ERROR_MESSAGE_MAX)) return null;
  return { code: value.code, message: value.message };
}

function decodeData(
  value: unknown,
  operation: FreshConversationOperation,
  expected: { work_ref: string; operation_key: string },
): FreshConversationData | null {
  if (!plainObject(value) || !exactKeys(value, DATA_KEYS)) return null;
  if (value.schema !== DATA_SCHEMA) return null;
  // Exact selector match on the supplied operation's expected pair.
  if (value.work_ref !== expected.work_ref) return null;
  if (value.operation_key !== expected.operation_key) return null;
  if (typeof value.state !== "string" || !STATES.has(value.state)) return null;
  if (typeof value.effect !== "string" || !EFFECTS.has(value.effect)) return null;
  if (value.parent_consumed !== false || value.can_send !== false) return null;
  const state = value.state as FreshConversationState;
  const effect = value.effect as FreshConversationEffect;

  // PREVIEW_READY belongs to the preview operation alone; nothing else may
  // carry it or a preview. Preview itself is NONE-effect and fully terminal.
  if (operation === "preview") {
    if (state !== "PREVIEW_READY" || effect !== "NONE") return null;
  } else if (state === "PREVIEW_READY") {
    return null;
  }
  if (operation === "status" || operation === "read") {
    if (effect !== "NONE") return null;
  }

  let preview: FreshConversationPreview | null = null;
  if (operation === "preview") {
    preview = decodePreview(value.preview);
    if (preview === null) return null;
  } else if (value.preview !== null) {
    return null;
  }

  let locator: FreshConversationLocator | null = null;
  if (state === "PREVIEW_READY" || state === "ABSENT") {
    if (value.locator !== null) return null;
  } else {
    locator = decodeLocator(value.locator, expected.work_ref);
    if (locator === null) return null;
  }

  let session: FreshConversationSession | null = null;
  if (state === "CREATED") {
    // Genuine CREATED carries a real session and a fully resolved locator;
    // ids are compared, never generated.
    if (locator === null || locator.job_id === null || locator.attempt_id === null) {
      return null;
    }
    session = decodeSession(value.session, locator.attempt_id);
    if (session === null) return null;
  } else if (value.session !== null) {
    return null;
  }

  let payload: FreshConversationPayload | null = null;
  if (value.result !== null) {
    // A result envelope is only meaningful for a read of CREATED/SETTLED;
    // decoding one never implies consumption or send authority.
    if (operation !== "read" || (state !== "CREATED" && state !== "SETTLED")) {
      return null;
    }
    payload = decodePayload(value.result);
    if (payload === null) return null;
  }

  return {
    schema: DATA_SCHEMA,
    operation_key: expected.operation_key,
    work_ref: expected.work_ref,
    state,
    effect,
    parent_consumed: false,
    can_send: false,
    preview,
    locator,
    session,
    result: payload,
  };
}

export function decodeFreshConversationResult(
  value: unknown,
  operation: FreshConversationOperation,
  expected: { work_ref: string; operation_key: string },
): FreshConversationResult | null {
  try {
    if (typeof operation !== "string" || !OPERATIONS.has(operation)) return null;
    if (!plainObject(expected)) return null;
    const workRef = expected.work_ref;
    const operationKey = expected.operation_key;
    if (typeof workRef !== "string" || typeof operationKey !== "string") {
      return null;
    }
    if (!validateFreshConversationRequest({work_ref:workRef,operation_key:operationKey},"status")) return null;
    if (!plainObject(value) || !exactKeys(value,["schema","operation","ok","data","error"]) ||
      value.schema !== "mastermind.executive.fresh_conversation_result.v1" || value.operation !== operation) return null;
    if (value.ok === true) {
      if (value.error !== null) return null;
      const data = decodeData(value.data, operation, { work_ref: workRef, operation_key: operationKey });
      if (data === null) return null;
      return { ok: true, data };
    }
    if (value.ok === false) {
      if (value.data !== null) return null;
      const error = decodeError(value.error);
      if (error === null) return null;
      // Preserved as data only: no UI, disposition or permission decision.
      return { ok: false, data: null, error };
    }
    return null;
  } catch {
    return null;
  }
}

/** Display guard for an existing source owner's initial_result + locator.
 * It verifies the sealed digest/budget, closed canonical outer envelope and
 * actual job/run association. Runtime still owns full role-body validation,
 * completion, consumption and continuation permission. No old create key or
 * synthetic create DTO is needed by a project reference reader. */
export function decodeFreshConversationInitialResult(value:unknown, locator:{job_id:string|null;attempt_id:string|null;root_job_id?:string}):FreshConversationPayload|null {
  try {
    if(!plainObject(locator))return null;
    const id=(v:unknown):v is string=>typeof v==="string"&&/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(v);
    if(!id(locator.job_id)||!id(locator.attempt_id))return null;
    if(locator.root_job_id!==undefined&&!id(locator.root_job_id))return null;
    const result=decodePayload(value);if(!result||!plainObject(result.envelope))return null;
    const e=result.envelope;
    if(!exactKeys(e,["schema_version","job_id","run_id","worker_id","role","status","role_result","summary","current_state","next_actions","errors","validations"])||
      e.schema_version!=="mastermind.executive_orchestration_result/v1"||e.job_id!==locator.job_id||e.run_id!==locator.attempt_id||
      !id(e.worker_id)||typeof e.role!=="string"||!["plan","work","review","repair","aggregation"].includes(e.role)||e.status!=="COMPLETED"||
      !Array.isArray(e.validations)||e.validations.length!==0||!plainObject(e.role_result))return null;
    const text=(v:unknown):v is string=>typeof v==="string"&&Array.from(v).length<=8192;
    const texts=(v:unknown)=>Array.isArray(v)&&v.length<=16&&v.every(text)&&new Set(v).size===v.length;
    if(!text(e.summary)||!text(e.current_state)||!texts(e.next_actions)||!texts(e.errors))return null;
    if(e.role==="plan"&&(e.role_result.plan_attempt_id!==locator.attempt_id||
      locator.root_job_id!==undefined&&e.role_result.root_job_id!==locator.root_job_id))return null;
    return result;
  }catch{return null;}
}
