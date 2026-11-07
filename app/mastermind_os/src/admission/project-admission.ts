/**
 * Pure strict TypeScript decoder for the closed Workspace project admission
 * control read body (`mastermind.workspace_project_admission_control.v1`).
 *
 * This mirrors only the body-shape math of the Python owner
 * (`common/workspace_project_admission_control_contract.py::validate_body`):
 *
 * - The input is the BODY alone; the `{"ok": ..., "result": ...}` envelope is
 *   never decoded here and is never echoed back. Only parsed closed output is
 *   returned; any rejected input decodes to `null`.
 * - A decoded control grants nothing. Permissions are qualified owner facts
 *   at this read, never reusable grants: action permission is granted only at
 *   server re-check with exactly these independently supplied booleans (at
 *   least one true). `owner_context.principal_scope` is an opaque 64-hex
 *   scope label, not a login, grant or capability.
 * - A historical receipt is never current state by itself.
 *   `NOT_SUSPENDED` and `RESUMED` mean the admission gate is open only; they
 *   never imply readiness, start authority or continuous supervision.
 * - The pause token is validated as the CURRENT pause event id plus a
 *   SHAPE-CHECKED `receipt_digest` only. The frontend cannot recompute the
 *   full receipt SHA-256 without async crypto, so the Python owner verifies
 *   digest equality; this decoder checks shape and event-id currency and
 *   never claims independent digest verification. A hash is CAS input, not
 *   authority.
 * - An UNAVAILABLE body withholds every fact: state, permissions, owner
 *   context, current receipt and pause token are all absent, and a body that
 *   carries stale facts alongside `UNAVAILABLE` is rejected.
 *
 * Selection key shapes (per the supplied owners): `work_ref` is `WS:` plus a
 * 2..64 character key of `[A-Z0-9]` segments joined by single hyphens;
 * `root_job_id` uses the frozen Workspace v2 JOB-[0-9]{1,9} grammar.
 * Historical leading zero identifiers are valid; no Job is inferred.
 * Receipt `command_id` values match
 * `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`.
 *
 * No I/O, transport, store, controller, getter, timer or effect is used or
 * created; inputs are never mutated; every returned value is a detached new
 * object.
 */

export const PROJECT_ADMISSION_CONTROL_BODY_SCHEMA =
  'mastermind.workspace_project_admission_control.v1';
export const WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA =
  'mastermind.workstream_admission_suspension_receipt.v1';
export const WORKSTREAM_ADMISSION_RESUMPTION_RECEIPT_SCHEMA =
  'mastermind.workstream_admission_resumption_receipt.v1';
export const PROJECT_ADMISSION_MAX_RESPONSE_BYTES = 32768;

/** Closed reason-code enum carried by UNAVAILABLE bodies. */
export const PROJECT_ADMISSION_REASON_CODES = [
  'INVALID_INPUT',
  'ACCESS_DENIED',
  'SOURCE_UNAVAILABLE',
  'SOURCE_CHANGED',
  'ROOT_MISMATCH',
  'OWNER_NOT_READY',
] as const;

export type ProjectAdmissionReasonCode = (typeof PROJECT_ADMISSION_REASON_CODES)[number];

/** Closed availability enum of the admission control read body. */
export type ProjectAdmissionAvailability = 'AVAILABLE' | 'UNAVAILABLE';

/** Closed workstream gate state; open-gate facts only, never readiness. */
export type ProjectAdmissionState = 'NOT_SUSPENDED' | 'PAUSED' | 'RESUMED';

/** Operation-specific project selection with an optional explicit root. */
export interface ProjectAdmissionSelection {
  readonly work_ref: string;
  readonly root_job_id?: string;
}

/** Qualified owner permission facts at this read; never reusable grants. */
export interface ProjectAdmissionPermissions {
  readonly pause: boolean;
  readonly resume: boolean;
}

/** Opaque owner scope context; not a login, grant or capability. */
export interface ProjectAdmissionOwnerContext {
  readonly principal_scope: string;
}

/** Public PAUSED suspension receipt shape; digest format-checked only. */
export interface ProjectAdmissionPauseReceipt {
  readonly schema: typeof WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA;
  readonly work_ref: string;
  readonly state: 'PAUSED';
  readonly event_id: number;
  readonly command_id: string;
  readonly request_digest: string;
  readonly committed_at_ms: number;
}

/**
 * Current-pause pointer. `receipt_digest` is shape-checked only; digest
 * equality is verified by the Python owner, never by this decoder.
 */
export interface ProjectAdmissionPauseToken {
  readonly event_id: number;
  readonly receipt_digest: string;
}

/** Public RESUMED resumption receipt shape; digest format-checked only. */
export interface ProjectAdmissionResumptionReceipt {
  readonly schema: typeof WORKSTREAM_ADMISSION_RESUMPTION_RECEIPT_SCHEMA;
  readonly work_ref: string;
  readonly state: 'RESUMED';
  readonly event_id: number;
  readonly command_id: string;
  readonly request_digest: string;
  readonly committed_at_ms: number;
  readonly pause_event_id: number;
  readonly pause_receipt_digest: string;
}

/** AVAILABLE body: gate facts present, no reason codes, at least one flag. */
export interface ProjectAdmissionAvailableControl {
  readonly availability: 'AVAILABLE';
  readonly schema: typeof PROJECT_ADMISSION_CONTROL_BODY_SCHEMA;
  readonly selection: ProjectAdmissionSelection;
  readonly state: ProjectAdmissionState;
  readonly permissions: ProjectAdmissionPermissions;
  readonly owner_context: ProjectAdmissionOwnerContext;
  readonly current_receipt: ProjectAdmissionPauseReceipt | ProjectAdmissionResumptionReceipt | null;
  readonly pause_token: ProjectAdmissionPauseToken | null;
  readonly reason_codes: readonly [];
}

/** UNAVAILABLE body: every fact withheld, exactly one reason code kept. */
export interface ProjectAdmissionUnavailableControl {
  readonly availability: 'UNAVAILABLE';
  readonly schema: typeof PROJECT_ADMISSION_CONTROL_BODY_SCHEMA;
  readonly selection: ProjectAdmissionSelection;
  readonly state: null;
  readonly permissions: null;
  readonly owner_context: null;
  readonly current_receipt: null;
  readonly pause_token: null;
  readonly reason_codes: readonly [ProjectAdmissionReasonCode];
}

/** Closed union over the AVAILABLE / UNAVAILABLE read-body schema. */
export type ProjectAdmissionControl =
  | ProjectAdmissionAvailableControl
  | ProjectAdmissionUnavailableControl;

const BODY_KEYS: readonly string[] = [
  'schema',
  'selection',
  'availability',
  'state',
  'permissions',
  'owner_context',
  'current_receipt',
  'pause_token',
  'reason_codes',
];
const FACT_KEYS: readonly string[] = [
  'state',
  'permissions',
  'owner_context',
  'current_receipt',
  'pause_token',
];
const PERMISSIONS_KEYS: readonly string[] = ['pause', 'resume'];
const OWNER_CONTEXT_KEYS: readonly string[] = ['principal_scope'];
const PAUSE_RECEIPT_KEYS: readonly string[] = [
  'schema',
  'work_ref',
  'state',
  'event_id',
  'command_id',
  'request_digest',
  'committed_at_ms',
];
const PAUSE_TOKEN_KEYS: readonly string[] = ['event_id', 'receipt_digest'];
const RESUMPTION_RECEIPT_KEYS: readonly string[] = [
  'schema',
  'work_ref',
  'state',
  'event_id',
  'command_id',
  'request_digest',
  'committed_at_ms',
  'pause_event_id',
  'pause_receipt_digest',
];

const WORK_REF_PATTERN = /^WS:([A-Z0-9]+(?:-[A-Z0-9]+)*)$/;
const WORK_REF_KEY_MIN = 2;
const WORK_REF_KEY_MAX = 64;
const ROOT_JOB_ID_PATTERN = /^JOB-[0-9]{1,9}$/;
const COMMAND_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const HEX64_PATTERN = /^[0-9a-f]{64}$/;

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if(typeof value !== 'object' || value===null || Array.isArray(value))return false;
  if(Object.getPrototypeOf(value)!==Object.prototype && Object.getPrototypeOf(value)!==null)return false;
  return Reflect.ownKeys(Object.getOwnPropertyDescriptors(value)).every(key=>typeof key==='string' && Object.hasOwn(Object.getOwnPropertyDescriptor(value,key)!, 'value'));
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  if (actual.length !== keys.length) {
    return false;
  }
  const expected = new Set(keys);
  for (const key of actual) {
    if (!expected.has(key)) {
      return false;
    }
  }
  return true;
}

function isWorkRef(value: unknown): value is string {
  if (typeof value !== 'string') {
    return false;
  }
  const match = WORK_REF_PATTERN.exec(value);
  if (match === null || match[0]!==value) {
    return false;
  }
  const key = match[1];
  return key !== undefined && key.length >= WORK_REF_KEY_MIN && key.length <= WORK_REF_KEY_MAX;
}

function isRootJobId(value: unknown): value is string {
  return typeof value === 'string' && ROOT_JOB_ID_PATTERN.exec(value)?.[0]===value;
}

function isCommandId(value: unknown): value is string {
  return typeof value === 'string' && COMMAND_ID_PATTERN.exec(value)?.[0]===value;
}

function isHex64(value: unknown): value is string {
  return typeof value === 'string' && HEX64_PATTERN.exec(value)?.[0]===value;
}

/** Exact finite integer with no boolean coercion; rejects NaN/Infinity. */
function isPositiveInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1;
}

function isNonNegativeInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

/**
 * Validate the rootless or rooted project selection shape. `work_ref` and an
 * optional explicit `root_job_id` are the only accepted keys; no shape here
 * grants an action or creates a root.
 */
export function validProjectAdmissionSelection(value: unknown): value is ProjectAdmissionSelection {
  if (!isPlainRecord(value)) {
    return false;
  }
  const keys = Object.keys(value);
  if(!hasExactKeys(value,keys.length===1 ? ['work_ref'] : ['work_ref','root_job_id']))return false;
  if (!isWorkRef(value['work_ref'])) {
    return false;
  }
  if (keys.length === 2) {
    if (!('root_job_id' in value) || !isRootJobId(value['root_job_id'])) {
      return false;
    }
  }
  return true;
}

/** Detached copy of a validated selection; shares no state with the input. */
function readSelection(value: unknown): ProjectAdmissionSelection | null {
  if (!validProjectAdmissionSelection(value)) {
    return null;
  }
  const selection: { work_ref: string; root_job_id?: string } = { work_ref: value.work_ref };
  const rootJobId = value.root_job_id;
  if (typeof rootJobId === 'string') {
    selection.root_job_id = rootJobId;
  }
  return selection;
}

/** Exact selection equality: same key set, same work_ref, same root proof. */
function sameSelection(a: ProjectAdmissionSelection, b: ProjectAdmissionSelection): boolean {
  if (a.work_ref !== b.work_ref) {
    return false;
  }
  const aRoot = 'root_job_id' in a;
  const bRoot = 'root_job_id' in b;
  if (aRoot !== bRoot) {
    return false;
  }
  return !aRoot || a.root_job_id === b.root_job_id;
}

function isReasonCode(value: unknown): value is ProjectAdmissionReasonCode {
  if (typeof value !== 'string') {
    return false;
  }
  return (PROJECT_ADMISSION_REASON_CODES as readonly string[]).includes(value);
}

function readSingleReasonCode(value: unknown): ProjectAdmissionReasonCode | null {
  if (!Array.isArray(value) || value.length !== 1) {
    return null;
  }
  const code = value[0];
  return isReasonCode(code) ? code : null;
}

/**
 * Validate a PAUSED suspension receipt shape against the selected work_ref.
 * `request_digest` is format-checked only (64 lowercase hex): recomputation
 * belongs to the verified owner with the actual server actor, and
 * `root_job_id` is intentionally absent from receipts.
 */
function parsePauseReceipt(value: unknown, workRef: string): ProjectAdmissionPauseReceipt | null {
  if (!isPlainRecord(value) || !hasExactKeys(value, PAUSE_RECEIPT_KEYS)) {
    return null;
  }
  const schema = value['schema'];
  if (
    typeof schema !== 'string' ||
    schema !== WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA
  ) {
    return null;
  }
  if (value['state'] !== 'PAUSED') {
    return null;
  }
  const receiptWorkRef = value['work_ref'];
  if (!isWorkRef(receiptWorkRef) || receiptWorkRef !== workRef) {
    return null;
  }
  const commandId = value['command_id'];
  if (!isCommandId(commandId)) {
    return null;
  }
  const eventId = value['event_id'];
  if (!isPositiveInt(eventId)) {
    return null;
  }
  const committedAtMs = value['committed_at_ms'];
  if (!isNonNegativeInt(committedAtMs)) {
    return null;
  }
  const requestDigest = value['request_digest'];
  if (!isHex64(requestDigest)) {
    return null;
  }
  return {
    schema,
    work_ref: receiptWorkRef,
    state: 'PAUSED',
    event_id: eventId,
    command_id: commandId,
    request_digest: requestDigest,
    committed_at_ms: committedAtMs,
  };
}

/**
 * Validate the pause token as the CURRENT pause event id plus a digest
 * SHAPE. Equality of the digest with the receipt's canonical form is
 * verified by the Python owner; this check never claims it.
 */
function parsePauseToken(value: unknown, currentEventId: number): ProjectAdmissionPauseToken | null {
  if (!isPlainRecord(value) || !hasExactKeys(value, PAUSE_TOKEN_KEYS)) {
    return null;
  }
  const eventId = value['event_id'];
  if (!isPositiveInt(eventId) || eventId !== currentEventId) {
    return null;
  }
  const receiptDigest = value['receipt_digest'];
  if (!isHex64(receiptDigest)) {
    return null;
  }
  return { event_id: eventId, receipt_digest: receiptDigest };
}

/**
 * Validate a RESUMED resumption receipt shape against the selected
 * work_ref. Ordering is judged by event-id monotonicity only; wall-clock
 * values are never compared to each other, and digest equality stays with
 * the owner.
 */
function parseResumptionReceipt(
  value: unknown,
  workRef: string,
): ProjectAdmissionResumptionReceipt | null {
  if (!isPlainRecord(value) || !hasExactKeys(value, RESUMPTION_RECEIPT_KEYS)) {
    return null;
  }
  const schema = value['schema'];
  if (
    typeof schema !== 'string' ||
    schema !== WORKSTREAM_ADMISSION_RESUMPTION_RECEIPT_SCHEMA
  ) {
    return null;
  }
  if (value['state'] !== 'RESUMED') {
    return null;
  }
  const receiptWorkRef = value['work_ref'];
  if (!isWorkRef(receiptWorkRef) || receiptWorkRef !== workRef) {
    return null;
  }
  const commandId = value['command_id'];
  if (!isCommandId(commandId)) {
    return null;
  }
  const eventId = value['event_id'];
  if (!isPositiveInt(eventId)) {
    return null;
  }
  const pauseEventId = value['pause_event_id'];
  if (!isPositiveInt(pauseEventId)) {
    return null;
  }
  if (eventId <= pauseEventId) {
    return null;
  }
  const committedAtMs = value['committed_at_ms'];
  if (!isNonNegativeInt(committedAtMs)) {
    return null;
  }
  const requestDigest = value['request_digest'];
  if (!isHex64(requestDigest)) {
    return null;
  }
  const pauseReceiptDigest = value['pause_receipt_digest'];
  if (!isHex64(pauseReceiptDigest)) {
    return null;
  }
  return {
    schema,
    work_ref: receiptWorkRef,
    state: 'RESUMED',
    event_id: eventId,
    command_id: commandId,
    request_digest: requestDigest,
    committed_at_ms: committedAtMs,
    pause_event_id: pauseEventId,
    pause_receipt_digest: pauseReceiptDigest,
  };
}

function parsePermissions(value: unknown): ProjectAdmissionPermissions | null {
  if (!isPlainRecord(value) || !hasExactKeys(value, PERMISSIONS_KEYS)) {
    return null;
  }
  const pause = value['pause'];
  const resume = value['resume'];
  if (typeof pause !== 'boolean' || typeof resume !== 'boolean') {
    return null;
  }
  if (!pause && !resume) {
    return null;
  }
  return { pause, resume };
}

function parseOwnerContext(value: unknown): ProjectAdmissionOwnerContext | null {
  if (!isPlainRecord(value) || !hasExactKeys(value, OWNER_CONTEXT_KEYS)) {
    return null;
  }
  const principalScope = value['principal_scope'];
  if (!isHex64(principalScope)) {
    return null;
  }
  return { principal_scope: principalScope };
}

/**
 * Canonical JSON text (sorted keys, compact, UTF-8) or `null` when the value
 * cannot be produced at all: non-JSON constants (`undefined`, functions,
 * symbols, bigints) and non-finite numbers are rejected, matching the
 * Python owner's `allow_nan=False` serialization.
 */
function safeJSON(value: unknown, seen=new Set<object>(), depth=0, budget={left:512}): boolean {
  if(--budget.left<0 || depth>20)return false;
  if(value===null || typeof value==='boolean')return true;
  if(typeof value==='string') {
    for(let i=0;i<value.length;i++) {
      const code=value.charCodeAt(i);
      if(code>=0xd800 && code<=0xdbff) {const next=value.charCodeAt(++i);if(!(next>=0xdc00 && next<=0xdfff))return false;}
      else if(code>=0xdc00 && code<=0xdfff)return false;
    }
    return true;
  }
  if(typeof value==='number')return Number.isFinite(value);
  if(typeof value!=='object' || value===null || seen.has(value))return false;
  if(!Array.isArray(value) && !isPlainRecord(value))return false;
  seen.add(value);
  const fields=Object.getOwnPropertyDescriptors(value);
  for(const key of Reflect.ownKeys(fields)) {
    if(typeof key!=='string' || !Object.hasOwn(fields[key],'value') || !safeJSON(fields[key].value,seen,depth+1,budget))return false;
  }
  seen.delete(value);return true;
}

function canonicalJsonText(value: unknown): string | null {
  if (typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? JSON.stringify(value) : null;
  }
  if (value === null) {
    return 'null';
  }
  if (Array.isArray(value)) {
    const parts: string[] = [];
    for (const item of value) {
      const text = canonicalJsonText(item);
      if (text === null) {
        return null;
      }
      parts.push(text);
    }
    return `[${parts.join(',')}]`;
  }
  if (isPlainRecord(value)) {
    const parts: string[] = [];
    for (const key of Object.keys(value).sort()) {
      const text = canonicalJsonText(value[key]);
      if (text === null) {
        return null;
      }
      parts.push(`${JSON.stringify(key)}:${text}`);
    }
    return `{${parts.join(',')}}`;
  }
  return null;
}

function utf8ByteLength(text: string): number {
  let bytes = 0;
  for (const char of text) {
    const codePoint = char.codePointAt(0);
    if (codePoint === undefined) {
      return Number.NaN;
    }
    if (codePoint < 0x80) {
      bytes += 1;
    } else if (codePoint < 0x800) {
      bytes += 2;
    } else if (codePoint < 0x10000) {
      bytes += 3;
    } else {
      bytes += 4;
    }
  }
  return bytes;
}

/**
 * UTF-8 byte length of the canonical `{"ok":true,"result":<value>}` read
 * envelope, or `null` when the envelope cannot be produced. The size counted
 * by the caller adds one trailing newline, mirroring the Python owner.
 */
export function projectAdmissionEnvelopeUtf8Bytes(value: unknown): number | null {
  if(!safeJSON(value))return null;
  const text = canonicalJsonText(value);
  if (text === null) {
    return null;
  }
  return utf8ByteLength(`{"ok":true,"result":${text}}`);
}

/**
 * Decode one closed project admission control read BODY for `expected`.
 *
 * Returns the parsed closed control, or `null` when the body is not an
 * object of the exact body schema, carries unknown or missing fields, uses
 * an unknown enum, mismatches `expected`, carries a malformed receipt or
 * token, uses booleans-as-numbers or non-finite numbers, or its canonical
 * envelope plus trailing newline would exceed
 * `PROJECT_ADMISSION_MAX_RESPONSE_BYTES`. An invalid `expected` selection is
 * itself rejected. Decoding grants no action, readiness or authority.
 */
export function decodeProjectAdmissionControl(
  value: unknown,
  expected: ProjectAdmissionSelection,
): ProjectAdmissionControl | null {
  if (!safeJSON(value) || !validProjectAdmissionSelection(expected)) {
    return null;
  }
  if (!isPlainRecord(value) || !hasExactKeys(value, BODY_KEYS)) {
    return null;
  }
  const schema = value['schema'];
  if (typeof schema !== 'string' || schema !== PROJECT_ADMISSION_CONTROL_BODY_SCHEMA) {
    return null;
  }
  const selection = readSelection(value['selection']);
  if (selection === null || !sameSelection(selection, expected)) {
    return null;
  }
  const availability = value['availability'];
  if (availability === 'UNAVAILABLE') {
    for (const key of FACT_KEYS) {
      if (value[key] !== null) {
        return null;
      }
    }
    const reasonCode = readSingleReasonCode(value['reason_codes']);
    if (reasonCode === null) {
      return null;
    }
    if (!envelopeWithinResponseCap(value)) {
      return null;
    }
    const control: ProjectAdmissionUnavailableControl = {
      availability: 'UNAVAILABLE',
      schema: PROJECT_ADMISSION_CONTROL_BODY_SCHEMA,
      selection,
      state: null,
      permissions: null,
      owner_context: null,
      current_receipt: null,
      pause_token: null,
      reason_codes: [reasonCode],
    };
    return control;
  }
  if (availability !== 'AVAILABLE') {
    return null;
  }
  const reasonCodes = value['reason_codes'];
  if (!Array.isArray(reasonCodes) || reasonCodes.length !== 0) {
    return null;
  }
  const permissions = parsePermissions(value['permissions']);
  if (permissions === null) {
    return null;
  }
  const ownerContext = parseOwnerContext(value['owner_context']);
  if (ownerContext === null) {
    return null;
  }
  const state = value['state'];
  if (state !== 'NOT_SUSPENDED' && state !== 'PAUSED' && state !== 'RESUMED') {
    return null;
  }
  let currentReceipt: ProjectAdmissionPauseReceipt | ProjectAdmissionResumptionReceipt | null =
    null;
  let pauseToken: ProjectAdmissionPauseToken | null = null;
  if (state === 'NOT_SUSPENDED') {
    if (value['current_receipt'] !== null || value['pause_token'] !== null) {
      return null;
    }
  } else if (state === 'PAUSED') {
    const receipt = parsePauseReceipt(value['current_receipt'], selection.work_ref);
    if (receipt === null) {
      return null;
    }
    pauseToken = parsePauseToken(value['pause_token'], receipt.event_id);
    if (pauseToken === null) {
      return null;
    }
    currentReceipt = receipt;
  } else {
    const receipt = parseResumptionReceipt(value['current_receipt'], selection.work_ref);
    if (receipt === null) {
      return null;
    }
    if (value['pause_token'] !== null) {
      return null;
    }
    currentReceipt = receipt;
  }
  if (!envelopeWithinResponseCap(value)) {
    return null;
  }
  const control: ProjectAdmissionAvailableControl = {
    availability: 'AVAILABLE',
    schema: PROJECT_ADMISSION_CONTROL_BODY_SCHEMA,
    selection,
    state,
    permissions,
    owner_context: ownerContext,
    current_receipt: currentReceipt,
    pause_token: pauseToken,
    reason_codes: [],
  };
  return control;
}

function envelopeWithinResponseCap(value: Record<string, unknown>): boolean {
  const bytes = projectAdmissionEnvelopeUtf8Bytes(value);
  return bytes !== null && bytes + 1 <= PROJECT_ADMISSION_MAX_RESPONSE_BYTES;
}
