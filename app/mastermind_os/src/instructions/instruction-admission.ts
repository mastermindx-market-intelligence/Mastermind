// Parent integration: canonical common contracts supersede request shorthand;
// owner-qualified missing-row identity is recovery only, never permission.
/**
 * Pure TypeScript mirror of the Mastermind instruction-admission PUBLIC BODY
 * contracts:
 *
 *   - mastermind.instruction_admission_suspension_receipt.v1
 *   - mastermind.workspace_instruction_admission_control.v1
 *   - mastermind.workspace_instruction_admission_action_result.v1
 *   - mastermind.workspace_instruction_admission_status_result.v1
 *
 * This is the decode-side consumer mirror of the Python producer validator
 * (`instruction-admission` admission contract). It implements no producer
 * logic, opens no request frame, and edits no Python file. Request frames
 * (`workspace_instruction_admission_control_read` / `..._action` /
 * `..._status`) are producer-side transport and are intentionally out of
 * scope here; only public bodies decode.
 *
 * Purity:
 *   - no network, clock, storage, DOM, auth, worker/controller, repository or
 *     publication effect of any kind; the module imports nothing, performs no
 *     I/O, and never computes or verifies a digest for meaning.
 *   - a well-formed hash is a wire-grammar fact only. It never proves receipt
 *     authenticity, grant, ownership, source authenticity, or that an effect
 *     happened or did not happen.
 *   - `permission.pause === true` is an owner-supplied FACT carried on the
 *     wire. It is not a grant: decoding it authorises nothing and mints no
 *     admission.
 *   - `NOT_OBSERVED` never proves that no effect occurred, and
 *     `OWNER_OUTCOME_UNCONFIRMED` is the only honest reading of an unseen
 *     dispatch outcome.
 *   - a receipt's `revision`/`source` may differ from the control body's
 *     current `instruction_revision`/`source`: a stable instruction pause
 *     survives workstream edits, so no such cross-check is performed (the
 *     producer does not perform one either).
 *
 * Strictness (mirroring the Python "exact builtin types" producer rules):
 *   - objects must be plain records: `Object.getPrototypeOf` is exactly
 *     `Object.prototype` or `null`. Class instances, arrays, functions and
 *     primitives are rejected; so are symbol-keyed objects.
 *   - exact closed key sets: no missing key, no extra key, hidden or not.
 *   - field values are read from the own property DESCRIPTOR, so accessor
 *     (getter/setter) properties are rejected and a hostile getter is never
 *     invoked; no user code runs during decoding.
 *   - strings must be well-formed UTF-16 (no lone surrogates). Every string
 *     grammar in this contract is ASCII, so every accepted value has a
 *     well-defined UTF-8 encoding.
 *   - integers must be safe integers; booleans are rejected where an integer
 *     is required. (A JS number cannot distinguish a JSON `1` from a `1.0`
 *     wire token; the producer rejects the float spelling, the mirror cannot
 *     observe it after parsing.)
 *
 * Canonical budget: the whole accepted body, serialised inside the response
 * envelope `{"ok":true,"result":BODY}` as sorted-key compact JSON, must stay
 * within 32767 UTF-8 bytes so that envelope plus one trailing LF is at most
 * 32768 (`MAX_RESPONSE_UTF8_BYTES`).
 *
 * Reconstruction notes (inputs not supplied to this port, frozen here from
 * the contract constraints and the established host grammar):
 *   - workstream ref: `WS:` + key, key = uppercase letter then 1..63 further
 *     uppercase letters/digits/hyphens (`WS:[A-Z][A-Z0-9-]{1,63}`).
 *   - instruction ref: `INS:` + the same key grammar.
 *   - source ref: `{repository, commit, path, content_sha256}` with the
 *     repository `mastermindx-market-intelligence/macro`, a 40-lowercase-hex commit, a 64-lowercase-hex
 *     content digest, and `path` exactly
 *     `agentos/workstreams/WS-<key>.md` for the selected workstream key.
 *
 * Every decoder returns `null` on any invalid input; it never echoes input
 * text, keys or reasons. Decoding grants no authority and dispatches nothing.
 */

/** Brand marker for a validated workstream ref (`WS:<key>`). */
export type WorkRef = string & { readonly __instructionAdmissionWorkRef: unique symbol };
/** Brand marker for a validated instruction ref (`INS:<key>`). */
export type InstructionRef = string & { readonly __instructionAdmissionInstructionRef: unique symbol };
/** Generic 64 lowercase hex digest field (opaque wire token, no meaning). */
export type LowerHex64 = string & { readonly __instructionAdmissionLowerHex64: unique symbol };
/** 40 lowercase hex commit digest field (opaque wire token, no meaning). */
export type LowerHex40 = string & { readonly __instructionAdmissionLowerHex40: unique symbol };
/** Owner principal scope: 64 lowercase hex (opaque wire token, no meaning). */
export type PrincipalScope = string & { readonly __instructionAdmissionPrincipalScope: unique symbol };
/**
 * Receipt command token: 1..128 chars of `[A-Za-z0-9._:-]` with an
 * alphanumeric first character. A current control receipt may carry ANY such
 * generic bounded token; only when an exact command is selected (action /
 * status results) must the receipt token equal it.
 */
export type ReceiptCommandId = string & { readonly __instructionAdmissionReceiptCommandId: unique symbol };
/** Request pause command id: `mmos-instruction-pause-` + 40 lowercase hex. */
export type PauseCommandId = string & { readonly __instructionAdmissionPauseCommandId: unique symbol };

/* ------------------------------------------------------------------ *
 * closed vocabularies and schema constants
 * ------------------------------------------------------------------ */

/** Exact schema discriminator of the suspension receipt. */
export const INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA =
  'mastermind.instruction_admission_suspension_receipt.v1' as const;

/** Exact schema discriminator of the current admission control body. */
export const INSTRUCTION_ADMISSION_CONTROL_SCHEMA =
  'mastermind.workspace_instruction_admission_control.v1' as const;

/** Exact schema discriminator of the pause action result body. */
export const INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA =
  'mastermind.workspace_instruction_admission_action_result.v1' as const;

/** Exact schema discriminator of the pause status result body. */
export const INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA =
  'mastermind.workspace_instruction_admission_status_result.v1' as const;

/** Request pause command prefix; the full id adds 40 lowercase hex. Ids are never minted here. */
export const INSTRUCTION_ADMISSION_PAUSE_COMMAND_PREFIX = 'mmos-instruction-pause-' as const;

/** The unknown-outcome marker: an unseen dispatch outcome, not a no-effect claim. */
export const OWNER_OUTCOME_UNCONFIRMED = 'OWNER_OUTCOME_UNCONFIRMED' as const;

/** Source repository macro accepted by the project source contract. */
export const INSTRUCTION_ADMISSION_SOURCE_REPOSITORY = 'mastermindx-market-intelligence/macro' as const;

/** Whole response envelope cap, trailing LF included. */
export const INSTRUCTION_ADMISSION_MAX_RESPONSE_UTF8_BYTES = 32768;

/** Single constant rejection marker (never carries input text). */
export const INSTRUCTION_ADMISSION_INVALID = 'instruction_admission_invalid' as const;

/** Closed reason vocabulary shared by control unavailability and failed results. */
export const INSTRUCTION_ADMISSION_REASON_CODES = [
  'ACCESS_DENIED',
  'SOURCE_UNAVAILABLE',
  'SOURCE_CHANGED',
  'OWNER_NOT_READY',
  'INSTRUCTION_NOT_SUPPLIED',
] as const;

export type InstructionAdmissionReasonCode = (typeof INSTRUCTION_ADMISSION_REASON_CODES)[number];

export type InstructionAdmissionAvailability = 'AVAILABLE' | 'UNAVAILABLE';

/** Control body state. `PAUSED` carries a receipt; `NOT_SUSPENDED` never does. */
export type InstructionAdmissionControlState = 'PAUSED' | 'NOT_SUSPENDED';

/** Pause action result disposition: committed, unknown, or never dispatched. */
export type InstructionAdmissionActionDisposition = 'COMMITTED' | 'EFFECT_UNKNOWN' | 'NOT_DISPATCHED';

/** Pause status result state: observed, not observed, or unavailable. */
export type InstructionAdmissionStatusState = 'OBSERVED' | 'NOT_OBSERVED' | 'UNAVAILABLE';

/** Mode selector of {@link decodeInstructionAdmissionResult}. */
export type InstructionAdmissionResultMode = 'pause' | 'status';

/* ------------------------------------------------------------------ *
 * decoded body types
 * ------------------------------------------------------------------ */

/** Exact selection of an instruction-admission body. */
export interface InstructionAdmissionSelection {
  readonly work_ref: string;
  readonly instruction_ref: string;
}

/** Selection of an action/status body: the selection plus the exact request command id. */
export interface InstructionAdmissionCommandSelection extends InstructionAdmissionSelection {
  readonly command_id: PauseCommandId;
}

/** Source reference of an available control body or a suspension receipt. */
export interface InstructionAdmissionSourceRef {
  readonly repository: typeof INSTRUCTION_ADMISSION_SOURCE_REPOSITORY;
  readonly commit: LowerHex40;
  readonly path: string;
  readonly content_sha256: LowerHex64;
}

/** Owner context of an available control body. A scope token is not a grant. */
export interface InstructionAdmissionOwnerContext {
  readonly principal_scope: PrincipalScope;
}

/**
 * Permission FACT of an available control body. `pause: true` is what the
 * owner currently reports; it is owner-supplied data, not authority.
 */
export interface InstructionAdmissionPermission {
  readonly pause: true;
}

/**
 * Observed suspension receipt embedded in a control or result body. Its
 * `revision`/`source` may legitimately differ from the current workstream
 * content: a stable pause survives edits.
 */
export interface InstructionAdmissionSuspensionReceipt {
  readonly schema: typeof INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA;
  readonly work_ref: WorkRef;
  readonly instruction_ref: InstructionRef;
  readonly revision: LowerHex64;
  readonly source: InstructionAdmissionSourceRef;
  readonly command_id: ReceiptCommandId;
  readonly state: 'PAUSED';
  readonly event_id: number;
  readonly request_digest: LowerHex64;
  readonly committed_at_ms: number;
}

/** Current admission control: the owner is unreachable (exactly one reason). */
export interface InstructionAdmissionControlUnavailable {
  readonly schema: typeof INSTRUCTION_ADMISSION_CONTROL_SCHEMA;
  readonly selection: InstructionAdmissionSelection;
  readonly availability: 'UNAVAILABLE';
  readonly state: null;
  readonly source: null;
  readonly instruction_revision: null;
  readonly permission: null;
  readonly owner_context: InstructionAdmissionOwnerContext | null;
  readonly current_receipt: null;
  readonly reason_codes: readonly [InstructionAdmissionReasonCode];
}

/** Current admission control: the owner answered, and reports one of two states. */
export interface InstructionAdmissionControlAvailable {
  readonly schema: typeof INSTRUCTION_ADMISSION_CONTROL_SCHEMA;
  readonly selection: InstructionAdmissionSelection;
  readonly availability: 'AVAILABLE';
  readonly state: InstructionAdmissionControlState;
  readonly source: InstructionAdmissionSourceRef;
  readonly instruction_revision: LowerHex64;
  readonly permission: InstructionAdmissionPermission;
  readonly owner_context: InstructionAdmissionOwnerContext;
  readonly current_receipt: InstructionAdmissionSuspensionReceipt | null;
  readonly reason_codes: readonly [];
}

/** Discriminated current-admission control body. */
export type InstructionAdmissionControl =
  | InstructionAdmissionControlAvailable
  | InstructionAdmissionControlUnavailable;

/** Reason-code payload of a failed result, fully determined by its state. */
export type InstructionAdmissionResultReasonCodes =
  | readonly []
  | readonly [typeof OWNER_OUTCOME_UNCONFIRMED]
  | readonly [InstructionAdmissionReasonCode];

/** Pause action result (mode `pause`). */
export interface InstructionAdmissionActionResult {
  readonly schema: typeof INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA;
  readonly selection: InstructionAdmissionCommandSelection;
  readonly disposition: InstructionAdmissionActionDisposition;
  readonly receipt: InstructionAdmissionSuspensionReceipt | null;
  readonly reason_codes: InstructionAdmissionResultReasonCodes;
}

/** Pause status result (mode `status`). */
export interface InstructionAdmissionStatusResult {
  readonly schema: typeof INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA;
  readonly selection: InstructionAdmissionCommandSelection;
  readonly state: InstructionAdmissionStatusState;
  readonly receipt: InstructionAdmissionSuspensionReceipt | null;
  readonly reason_codes: InstructionAdmissionResultReasonCodes;
}

/** Discriminated action/status result body; the schema is the discriminator. */
export type InstructionAdmissionResult =
  | InstructionAdmissionActionResult
  | InstructionAdmissionStatusResult;

/* ------------------------------------------------------------------ *
 * rejection + scalar helpers
 * ------------------------------------------------------------------ */

function fail(): never {
  throw new Error(INSTRUCTION_ADMISSION_INVALID);
}

function req(condition: unknown): void {
  if (condition !== true) fail();
}

const LOWER_HEX_64 = /^[0-9a-f]{64}$/;
const LOWER_HEX_40 = /^[0-9a-f]{40}$/;
const WORK_REF_PATTERN = /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const INSTRUCTION_REF_PATTERN = /^INS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const PAUSE_COMMAND_ID_PATTERN = /^mmos-instruction-pause-[0-9a-f]{40}$/;
const RECEIPT_COMMAND_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

const EVENT_ID_MAX = 9007199254740991; // 2^53 - 1

const SOURCE_PATH_PREFIX = 'agentos/workstreams/WS-';
const SOURCE_PATH_SUFFIX = '.md';

/** True when the string has no unpaired surrogate, i.e. encodes to UTF-8. */
function wellFormed(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      if (i + 1 >= s.length) return false;
      const d = s.charCodeAt(i + 1);
      if (d < 0xdc00 || d > 0xdfff) return false;
      i++;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return false;
    }
  }
  return true;
}

/** UTF-8 byte length of a well-formed string, without allocating. */
function utf8ByteLength(s: string): number {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
      const d = s.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) {
        n += 4;
        i++;
        continue;
      }
    }
    if (c < 0x80) n += 1;
    else if (c < 0x800) n += 2;
    else if (c < 0x10000) n += 3;
    else n += 4;
  }
  return n;
}

function reqString(value: unknown): string {
  req(typeof value === 'string');
  const s = value as string;
  req(s.length <= 8192 && wellFormed(s));
  return s;
}

function reqLowerHex64(value: unknown): LowerHex64 {
  const s = reqString(value);
  req(LOWER_HEX_64.exec(s)?.[0] === s);
  return s as LowerHex64;
}

function reqLowerHex40(value: unknown): LowerHex40 {
  const s = reqString(value);
  req(LOWER_HEX_40.exec(s)?.[0] === s);
  return s as LowerHex40;
}

function reqPrincipalScope(value: unknown): PrincipalScope {
  const s = reqString(value);
  req(LOWER_HEX_64.exec(s)?.[0] === s);
  return s as PrincipalScope;
}

/**
 * Safe integer scalar. Booleans are rejected explicitly: in this position a
 * boolean is a type confusion, not a truthy integer.
 */
function reqSafeInt(value: unknown, min: number, max: number): number {
  if (typeof value === 'boolean') fail();
  req(typeof value === 'number');
  req(Number.isSafeInteger(value as number));
  const n = value as number;
  req(n >= min && n <= max);
  return n;
}

function reqWorkRef(value: unknown): WorkRef {
  const s = reqString(value);
  req(s.length >= 5 && s.length <= 67 && WORK_REF_PATTERN.exec(s)?.[0] === s);
  return s as WorkRef;
}

function reqInstructionRef(value: unknown): InstructionRef {
  const s = reqString(value);
  req(s.length >= 6 && s.length <= 68 && INSTRUCTION_REF_PATTERN.exec(s)?.[0] === s);
  return s as InstructionRef;
}

function reqPauseCommandId(value: unknown): PauseCommandId {
  const s = reqString(value);
  req(PAUSE_COMMAND_ID_PATTERN.exec(s)?.[0] === s);
  return s as PauseCommandId;
}

function reqReceiptCommandId(value: unknown): ReceiptCommandId {
  const s = reqString(value);
  req(RECEIPT_COMMAND_ID_PATTERN.exec(s)?.[0] === s);
  return s as ReceiptCommandId;
}

function reqClosedReason(value: unknown): InstructionAdmissionReasonCode {
  const s = reqString(value);
  for (const reason of INSTRUCTION_ADMISSION_REASON_CODES) {
    if (reason === s) return s as InstructionAdmissionReasonCode;
  }
  fail();
}

/* ------------------------------------------------------------------ *
 * plain-object access (never invokes user code)
 * ------------------------------------------------------------------ */

/**
 * Rejects anything that is not a plain record: prototypes other than
 * `Object.prototype`/`null` (class instances), arrays, primitives, functions
 * and symbol-keyed objects. No property is read here, so no getter runs.
 */
function reqPlainObject(value: unknown): asserts value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) fail();
  const proto = Object.getPrototypeOf(value as object);
  if (proto !== Object.prototype && proto !== null) fail();
  if (Object.getOwnPropertySymbols(value as object).length !== 0) fail();
}

/**
 * Rejects anything that is not a builtin array, mirroring the producer's
 * exact `list` check: array subclasses and arrays with a replaced prototype
 * are rejected. Reads no element and no property.
 */
function reqArray(value: unknown): asserts value is readonly unknown[] {
  if (!Array.isArray(value)) fail();
  const proto = Object.getPrototypeOf(value as object);
  if (proto !== Array.prototype) fail();
  const fields = Object.getOwnPropertyDescriptors(value);
  const length = Object.getOwnPropertyDescriptor(value,'length')?.value;
  if (typeof length !== 'number' || !Number.isSafeInteger(length) || length < 0 || length > 1
      || Reflect.ownKeys(fields).length !== length + 1) fail();
  for (let i=0;i<length;i++) {
    const item=fields[String(i)];
    if (!item?.enumerable || !Object.hasOwn(item,'value')) fail();
  }
}

/** Exact closed key set: no missing key, no extra key, hidden or not. */
function reqExactKeys(value: Record<string, unknown>, keys: readonly string[]): void {
  const own = Object.getOwnPropertyNames(value);
  if (own.length !== keys.length) fail();
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) fail();
  }
}

/**
 * Own data-property value only. Accessor descriptors are rejected instead of
 * being invoked, so a throwing or counting getter never executes.
 */
function field(value: Record<string, unknown>, key: string): unknown {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (descriptor === undefined) fail();
  if (!descriptor.enumerable || descriptor.get !== undefined || descriptor.set !== undefined) fail();
  return descriptor.value;
}

function hasValue<T extends string>(closed: readonly T[], candidate: string): boolean {
  for (let i = 0; i < closed.length; i++) {
    if (closed[i] === candidate) return true;
  }
  return false;
}

/* ------------------------------------------------------------------ *
 * canonical JSON + envelope budget
 * ------------------------------------------------------------------ */

/**
 * Sorted-key compact JSON, non-ASCII preserved: the exact shape of the
 * producer's `canonical`. Only plain records, arrays, strings, safe numbers
 * and booleans reach it (all wire strings accepted by this module are ASCII,
 * so the serialisation is byte-identical to the producer's).
 */
function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  const type = typeof value;
  if (type === 'boolean') return (value as boolean) ? 'true' : 'false';
  if (type === 'number') {
    req(Number.isSafeInteger(value as number));
    return String(value as number);
  }
  if (type === 'string') return JSON.stringify(value as string);
  if (Array.isArray(value)) {
    let out = '';
    for (let i = 0; i < value.length; i++) {
      if (i > 0) out += ',';
      out += canonicalJson(value[i]);
    }
    return '[' + out + ']';
  }
  if (type === 'object') {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort(compareCodeUnits);
    let out = '{';
    let first = true;
    for (const key of keys) {
      if (!first) out += ',';
      first = false;
      out += JSON.stringify(key) + ':' + canonicalJson(record[key]);
    }
    return out + '}';
  }
  fail();
}

function compareCodeUnits(a: string, b: string): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

const ENVELOPE_BUDGET_UTF8_BYTES = INSTRUCTION_ADMISSION_MAX_RESPONSE_UTF8_BYTES - 1;

/**
 * Envelope budget: the canonical `{"ok":true,"result":BODY}` serialisation
 * must stay within 32767 UTF-8 bytes so envelope + one trailing LF is at most
 * 32768.
 */
function reqEnvelopeBudget(body: unknown): void {
  const envelope = canonicalJson({ ok: true, result: body });
  req(utf8ByteLength(envelope) <= ENVELOPE_BUDGET_UTF8_BYTES);
}

/* ------------------------------------------------------------------ *
 * closed key sets
 * ------------------------------------------------------------------ */

const SELECTION_KEYS = ['instruction_ref', 'work_ref'] as const;
const SELECTION_COMMAND_KEYS = ['command_id', 'instruction_ref', 'work_ref'] as const;
const SOURCE_KEYS = ['commit', 'content_sha256', 'path', 'repository'] as const;
const PERMISSION_KEYS = ['pause'] as const;
const OWNER_CONTEXT_KEYS = ['principal_scope'] as const;
const RECEIPT_KEYS = [
  'command_id',
  'committed_at_ms',
  'event_id',
  'instruction_ref',
  'request_digest',
  'revision',
  'schema',
  'source',
  'state',
  'work_ref',
] as const;
const CONTROL_KEYS = [
  'availability',
  'current_receipt',
  'instruction_revision',
  'owner_context',
  'permission',
  'reason_codes',
  'schema',
  'selection',
  'source',
  'state',
] as const;
const ACTION_RESULT_KEYS = ['disposition', 'reason_codes', 'receipt', 'schema', 'selection'] as const;
const STATUS_RESULT_KEYS = ['reason_codes', 'receipt', 'schema', 'selection', 'state'] as const;

/** Control facts that must all be exactly null on an UNAVAILABLE body. */
const CONTROL_FACT_KEYS = [
  'state',
  'source',
  'instruction_revision',
  'permission',
  'current_receipt',
] as const;

/* ------------------------------------------------------------------ *
 * selection / source / receipt validators
 * ------------------------------------------------------------------ */

interface InternalSelection {
  readonly work_ref: WorkRef;
  readonly instruction_ref: InstructionRef;
  readonly command_id?: PauseCommandId;
}

function reqSelection(value: unknown, command: boolean): InternalSelection {
  reqPlainObject(value);
  reqExactKeys(value, command ? SELECTION_COMMAND_KEYS : SELECTION_KEYS);
  const work_ref = reqWorkRef(field(value, 'work_ref'));
  const instruction_ref = reqInstructionRef(field(value, 'instruction_ref'));
  if (!command) return { work_ref, instruction_ref };
  return { work_ref, instruction_ref, command_id: reqPauseCommandId(field(value, 'command_id')) };
}

/** A wire selection equals the selected one exactly (canonical comparison). */
function reqSameSelection(value: unknown, expected: InternalSelection): void {
  req(canonicalJson(reqSelection(value, expected.command_id !== undefined)) === canonicalJson(expected));
}

/** Accepts a receipt expected-set with either two or three keys, like the producer. */
function reqReceiptExpectedSelection(value: unknown): InternalSelection {
  reqPlainObject(value);
  const command = Object.prototype.hasOwnProperty.call(value, 'command_id');
  return reqSelection(value, command);
}

/**
 * The exact source path of a workstream: `agentos/workstreams/WS-<key>.md`,
 * derived from the selected work_ref so a sibling workstream's file is always
 * rejected.
 */
function expectedSourcePath(workRef: WorkRef): string {
  return SOURCE_PATH_PREFIX + workRef.slice(3) + SOURCE_PATH_SUFFIX;
}

function reqSourceRef(value: unknown, workRef: WorkRef): InstructionAdmissionSourceRef {
  reqPlainObject(value);
  reqExactKeys(value, SOURCE_KEYS);
  req(field(value, 'repository') === INSTRUCTION_ADMISSION_SOURCE_REPOSITORY);
  const path = reqString(field(value, 'path'));
  req(path === expectedSourcePath(workRef));
  return {
    repository: INSTRUCTION_ADMISSION_SOURCE_REPOSITORY,
    commit: reqLowerHex40(field(value, 'commit')),
    path,
    content_sha256: reqLowerHex64(field(value, 'content_sha256')),
  };
}

function reqReceipt(
  value: unknown,
  expected: InternalSelection,
): InstructionAdmissionSuspensionReceipt {
  reqPlainObject(value);
  reqExactKeys(value, RECEIPT_KEYS);

  const schema = reqString(field(value, 'schema'));
  req(schema === INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA);

  const state = reqString(field(value, 'state'));
  req(state === 'PAUSED');

  // Exact selected-workstream and selected-instruction match; the selected
  // refs are already grammar-validated, so string equality is the whole check.
  const work_ref = field(value, 'work_ref');
  req(work_ref === expected.work_ref);
  const instruction_ref = field(value, 'instruction_ref');
  req(instruction_ref === expected.instruction_ref);

  const revision = reqLowerHex64(field(value, 'revision'));
  const request_digest = reqLowerHex64(field(value, 'request_digest'));

  // A current control receipt may carry any generic bounded token; when an
  // exact command is selected (action / status results) it must equal it.
  const command_id = reqReceiptCommandId(field(value, 'command_id'));
  if (expected.command_id !== undefined) {
    req((command_id as string) === (expected.command_id as string));
  }

  const source = reqSourceRef(field(value, 'source'), expected.work_ref);

  const event_id = reqSafeInt(field(value, 'event_id'), 1, EVENT_ID_MAX);
  const committed_at_ms = reqSafeInt(field(value, 'committed_at_ms'), 0, EVENT_ID_MAX);

  return {
    schema: INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA,
    work_ref: work_ref as WorkRef,
    instruction_ref: instruction_ref as InstructionRef,
    revision,
    source,
    command_id,
    state: 'PAUSED',
    event_id,
    request_digest,
    committed_at_ms,
  };
}

/* ------------------------------------------------------------------ *
 * control body decoder
 * ------------------------------------------------------------------ */

function decodeControl(
  value: unknown,
  expected: InternalSelection,
): InstructionAdmissionControl {
  reqPlainObject(value);
  reqExactKeys(value, CONTROL_KEYS);

  const schema = reqString(field(value, 'schema'));
  req(schema === INSTRUCTION_ADMISSION_CONTROL_SCHEMA);

  reqSameSelection(field(value, 'selection'), expected);

  const availability = reqString(field(value, 'availability'));

  if (availability === 'UNAVAILABLE') {
    // Unreachable owner: every fact is exactly null and exactly one closed
    // reason explains why. No fact here ever proves a pause exists or not.
    for (const factKey of CONTROL_FACT_KEYS) {
      req(field(value, factKey) === null);
    }
    const rawReasons = field(value, 'reason_codes');
    reqArray(rawReasons);
    req(rawReasons.length === 1);
    const reason = reqClosedReason(rawReasons[0]);
    const rawIdentity=field(value,'owner_context');
    let owner_context:InstructionAdmissionOwnerContext|null=null;
    if(rawIdentity!==null){
      req(reason==='INSTRUCTION_NOT_SUPPLIED');reqPlainObject(rawIdentity);reqExactKeys(rawIdentity,OWNER_CONTEXT_KEYS);
      owner_context={principal_scope:reqPrincipalScope(field(rawIdentity,'principal_scope'))};
    }
    const control: InstructionAdmissionControlUnavailable = {
      schema: INSTRUCTION_ADMISSION_CONTROL_SCHEMA,
      selection: { work_ref: expected.work_ref, instruction_ref: expected.instruction_ref },
      availability: 'UNAVAILABLE',
      state: null,
      source: null,
      instruction_revision: null,
      permission: null,
      owner_context,
      current_receipt: null,
      reason_codes: [reason],
    };
    reqEnvelopeBudget(control);
    return control;
  }

  if (availability !== 'AVAILABLE') fail();

  // Reachable owner: the current source must be the selected workstream's
  // file, no reason may accompany an available body, and the reported
  // permission is a fact, never a grant.
  const source = reqSourceRef(field(value, 'source'), expected.work_ref);
  const rawReasons = field(value, 'reason_codes');
  reqArray(rawReasons);
  req(rawReasons.length === 0);

  const instruction_revision = reqLowerHex64(field(value, 'instruction_revision'));

  const rawPermission = field(value, 'permission');
  reqPlainObject(rawPermission);
  reqExactKeys(rawPermission, PERMISSION_KEYS);
  req(field(rawPermission, 'pause') === true);

  const rawOwnerContext = field(value, 'owner_context');
  reqPlainObject(rawOwnerContext);
  reqExactKeys(rawOwnerContext, OWNER_CONTEXT_KEYS);
  const principal_scope = reqPrincipalScope(field(rawOwnerContext, 'principal_scope'));

  const state = reqString(field(value, 'state'));
  let current_receipt: InstructionAdmissionSuspensionReceipt | null = null;
  if (state === 'PAUSED') {
    current_receipt = reqReceipt(field(value, 'current_receipt'), expected);
  } else if (state === 'NOT_SUSPENDED') {
    req(field(value, 'current_receipt') === null);
  } else {
    fail();
  }

  const control: InstructionAdmissionControlAvailable = {
    schema: INSTRUCTION_ADMISSION_CONTROL_SCHEMA,
    selection: { work_ref: expected.work_ref, instruction_ref: expected.instruction_ref },
    availability: 'AVAILABLE',
    state: state as InstructionAdmissionControlState,
    source,
    instruction_revision,
    permission: { pause: true },
    owner_context: { principal_scope },
    current_receipt,
    reason_codes: [],
  };
  reqEnvelopeBudget(control);
  return control;
}

/* ------------------------------------------------------------------ *
 * result body decoder (pause action / pause status)
 * ------------------------------------------------------------------ */

function decodeResult(
  value: unknown,
  expected: InternalSelection,
  status: boolean,
): InstructionAdmissionResult {
  reqPlainObject(value);
  reqExactKeys(value, status ? STATUS_RESULT_KEYS : ACTION_RESULT_KEYS);

  const schema = reqString(field(value, 'schema'));
  req(schema === (status ? INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA : INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA));

  reqSameSelection(field(value, 'selection'), expected);

  // The state field is spelled `state` on status results and `disposition` on
  // action results; the exact key set above already picked the right one.
  const state = reqString(field(value, status ? 'state' : 'disposition'));
  const found = state === (status ? 'OBSERVED' : 'COMMITTED');

  let receipt: InstructionAdmissionSuspensionReceipt | null = null;
  let reason_codes: InstructionAdmissionResultReasonCodes;
  if (found) {
    // The outcome was observed: the receipt must exist and match the exact
    // selected command, and no reason may accompany it.
    receipt = reqReceipt(field(value, 'receipt'), expected);
    const rawReasons = field(value, 'reason_codes');
    reqArray(rawReasons);
    req(rawReasons.length === 0);
    reason_codes = [];
  } else {
    // No observation: no receipt may exist, and the reason payload is
    // determined by the exact failed state.
    req(field(value, 'receipt') === null);
    const rawReasons = field(value, 'reason_codes');
    reqArray(rawReasons);
    if (status && state === 'NOT_OBSERVED') {
      req(rawReasons.length === 0);
      reason_codes = [];
    } else if (!status && state === 'EFFECT_UNKNOWN') {
      // Exactly `[OWNER_OUTCOME_UNCONFIRMED]` — the unknown marker is its own
      // constant and is deliberately NOT a member of the closed reason set.
      const first = rawReasons[0];
      req(
        rawReasons.length === 1 &&
          typeof first === 'string' &&
          (first as string) === OWNER_OUTCOME_UNCONFIRMED,
      );
      reason_codes = [OWNER_OUTCOME_UNCONFIRMED];
    } else if (state === (status ? 'UNAVAILABLE' : 'NOT_DISPATCHED')) {
      req(rawReasons.length === 1);
      reason_codes = [reqClosedReason(rawReasons[0])];
    } else {
      fail();
    }
  }

  if (status) {
    const result: InstructionAdmissionStatusResult = {
      schema: INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA,
      selection: {
        work_ref: expected.work_ref,
        instruction_ref: expected.instruction_ref,
        command_id: expected.command_id as PauseCommandId,
      },
      state: state as InstructionAdmissionStatusState,
      receipt,
      reason_codes,
    };
    reqEnvelopeBudget(result);
    return result;
  }
  const result: InstructionAdmissionActionResult = {
    schema: INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA,
    selection: {
      work_ref: expected.work_ref,
      instruction_ref: expected.instruction_ref,
      command_id: expected.command_id as PauseCommandId,
    },
    disposition: state as InstructionAdmissionActionDisposition,
    receipt,
    reason_codes,
  };
  reqEnvelopeBudget(result);
  return result;
}

/* ------------------------------------------------------------------ *
 * public API
 * ------------------------------------------------------------------ */

/**
 * Validates an instruction-admission selection of unknown provenance against
 * the closed grammar. Pure predicate: it throws nothing and reads no accessor
 * property. True means the exact `{work_ref, instruction_ref}` shape held;
 * it never means the instruction exists or is pauseable.
 */
export function validInstructionAdmissionSelection(
  value: unknown,
): value is InstructionAdmissionSelection {
  try {
    reqSelection(value, false);
    return true;
  } catch {
    return false;
  }
}

/**
 * Decodes a current instruction-admission control body of unknown provenance
 * into a deeply detached, closed-shape result, or returns `null` on any
 * invalid input.
 *
 * `expected` must be the exact selected `{work_ref, instruction_ref}`; the
 * body's own selection must equal it. This is a shape/grammar decoder only:
 * an `AVAILABLE` body's `permission.pause === true` is an owner-supplied
 * fact and confers no authority, an `UNAVAILABLE` body never proves the
 * absence of a pause, and every digest is an opaque wire token.
 */
export function decodeInstructionAdmissionControl(
  value: unknown,
  expected: unknown,
): InstructionAdmissionControl | null {
  try {
    return decodeControl(value, reqSelection(expected, false));
  } catch {
    return null;
  }
}

/**
 * Decodes a pause action result (mode `pause`) or pause status result (mode
 * `status`) of unknown provenance, or returns `null` on any invalid input.
 *
 * `expected` must be the exact selected `{work_ref, instruction_ref,
 * command_id}` with the request pause command id
 * `mmos-instruction-pause-` + 40 lowercase hex. On a found outcome the
 * receipt's command token must equal the selected command; on any other
 * outcome no receipt may exist. `EFFECT_UNKNOWN` reports an unseen dispatch
 * outcome — never a claim that nothing happened — and `NOT_OBSERVED` never
 * proves the absence of an effect.
 */
export function decodeInstructionAdmissionResult(
  value: unknown,
  expected: unknown,
  mode: InstructionAdmissionResultMode,
): InstructionAdmissionResult | null {
  try {
    if(mode!=='pause'&&mode!=='status')return null;
    return decodeResult(value, reqSelection(expected, true), mode === 'status');
  } catch {
    return null;
  }
}

/**
 * Decodes an observed suspension receipt of unknown provenance against a
 * selected `{work_ref, instruction_ref}` pair, optionally with a `command_id`
 * that the receipt token must then equal exactly, or returns `null` on any
 * invalid input. Without a selected command, any generic bounded receipt
 * token is accepted — exactly like the producer. The receipt is a wire fact
 * about a past owner report; it grants nothing.
 */
export function decodeInstructionAdmissionReceipt(
  value: unknown,
  expected: unknown,
): InstructionAdmissionSuspensionReceipt | null {
  try {
    return reqReceipt(value, reqReceiptExpectedSelection(expected));
  } catch {
    return null;
  }
}

/**
 * Builds the exact typed unavailable control body for a valid selection:
 * every fact null, exactly one closed reason (`SOURCE_UNAVAILABLE` by
 * default). Mirrors the producer's `unavailable` helper: invalid input throws
 * {@link INSTRUCTION_ADMISSION_INVALID} instead of wrapping a plausible body.
 * The result reports that the owner was not reachable; it never asserts that
 * no pause exists and it authorises nothing.
 */
export function unavailableInstructionAdmissionControl(
  selected: unknown,
  reason: InstructionAdmissionReasonCode = 'SOURCE_UNAVAILABLE',
): InstructionAdmissionControl {
  const expected = reqSelection(selected, false);
  return decodeControl(
    {
      schema: INSTRUCTION_ADMISSION_CONTROL_SCHEMA,
      selection: { work_ref: expected.work_ref, instruction_ref: expected.instruction_ref },
      availability: 'UNAVAILABLE',
      state: null,
      source: null,
      instruction_revision: null,
      permission: null,
      owner_context: null,
      current_receipt: null,
      reason_codes: [reason],
    },
    expected,
  );
}
