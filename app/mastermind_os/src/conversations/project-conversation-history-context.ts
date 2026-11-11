/**
 * Pure decoder for a validated Executive OS session result frame carrying a
 * project conversation-history context.
 *
 * Scope and guarantees:
 * - Accepts ONLY a rootless, READ-only, same-existing-OS-session result
 *   envelope: `effect: "NONE"`, `ok: true`, `operation_key: null`,
 *   `error: null`, and the exact envelope/data key sets below. No
 *   `root_job_id` (or any other key) is accepted at any level.
 * - This function validates a server-produced frame and extracts a detached,
 *   frozen value. It does NOT authenticate any principal, does NOT issue or
 *   renew any capability, and grants no authority by itself. Callers must have
 *   already obtained the frame through the authenticated OS session channel;
 *   this decoder consumes such a validated frame, nothing more.
 * - Fail-closed: every invalid input returns `null`; nothing is thrown,
 *   logged, or surfaced to the caller.
 * - No timers, dates, globals, network, auth, or grant access: the current
 *   time is a required `nowMs` parameter; nothing here reads a clock.
 * - Closed structure: only own, plain data properties on objects whose
 *   prototype is `Object.prototype` or `null` are read. Accessor descriptors
 *   are rejected without executing any getter, and no JSON round-trip (which
 *   could invoke getters or `toJSON`) is performed. Keys and strings are
 *   bounded by the closed shallow field structure below; no generic recursive
 *   parser is used.
 */

export interface ProjectConversationHistoryContext {
  readonly workRef: string;
  readonly principalScope: string;
  readonly expiresAtMs: number;
}

const ENVELOPE_SCHEMA = 'mastermind.os.executive.session_result.v1';
const ENVELOPE_OPERATION = 'history_context';
const ENVELOPE_EFFECT = 'NONE';
const ENVELOPE_KEYS: readonly string[] = [
  'schema',
  'operation',
  'ok',
  'effect',
  'operation_key',
  'error',
  'data',
];
const DATA_SCHEMA = 'mastermind.os.executive.project_history_context.v1';
const DATA_KEYS: readonly string[] = [
  'schema',
  'principal_scope',
  'verified_expiry',
  'selection',
  'capabilities',
];
const SELECTION_KEYS: readonly string[] = ['work_ref'];
const CAPABILITY_KEYS: readonly string[] = ['references_read', 'reply_read'];
const WORK_REF_PATTERN = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const PRINCIPAL_SCOPE_PATTERN = /^[0-9a-f]{64}$/;
const MS_PER_SECOND = 1000;
const MAX_SAFE_EXPIRY_SECONDS = Math.floor(Number.MAX_SAFE_INTEGER / MS_PER_SECOND);

function isClosedPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const proto: unknown = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Returns the own data-property values of `value` when its own key set is
 * exactly `keys` and every descriptor is a plain data descriptor. Accessor
 * descriptors are rejected without invoking their getters.
 */
function readOwnDataFields(
  value: object,
  keys: readonly string[],
): Record<string, unknown> | null {
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== keys.length) {
    return null;
  }
  const expected = new Set<string>(keys);
  for (const name of names) {
    if (!expected.has(name)) {
      return null;
    }
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) {
    return null;
  }
  const fields: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor === undefined) {
      return null;
    }
    if (descriptor.get !== undefined || descriptor.set !== undefined) {
      return null;
    }
    fields[key] = descriptor.value;
  }
  return fields;
}

/**
 * Decode a validated rootless READ-only session result frame into a detached,
 * frozen project conversation-history context. Returns `null` on any invalid
 * frame, non-canonical `workRef`, invalid `nowMs`, or expired/not-yet-valid
 * context. This validates the frame only; it does not authenticate a
 * principal or issue any capability.
 */
export function decodeProjectConversationHistoryContext(
  raw: unknown,
  workRef: string,
  nowMs: number,
): ProjectConversationHistoryContext | null {
  try {
    if (typeof nowMs !== 'number' || !Number.isSafeInteger(nowMs) || nowMs < 0) {
      return null;
    }
    if (typeof workRef !== 'string' || !WORK_REF_PATTERN.test(workRef)) {
      return null;
    }
    if (workRef.includes('\n') || workRef.includes('\r')) {
      return null;
    }

    if (!isClosedPlainObject(raw)) {
      return null;
    }
    const envelope = readOwnDataFields(raw, ENVELOPE_KEYS);
    if (envelope === null) {
      return null;
    }
    if (envelope.schema !== ENVELOPE_SCHEMA) {
      return null;
    }
    if (envelope.operation !== ENVELOPE_OPERATION) {
      return null;
    }
    if (envelope.ok !== true) {
      return null;
    }
    if (envelope.effect !== ENVELOPE_EFFECT) {
      return null;
    }
    if (envelope.operation_key !== null) {
      return null;
    }
    if (envelope.error !== null) {
      return null;
    }

    const dataValue = envelope.data;
    if (!isClosedPlainObject(dataValue)) {
      return null;
    }
    const data = readOwnDataFields(dataValue, DATA_KEYS);
    if (data === null) {
      return null;
    }
    if (data.schema !== DATA_SCHEMA) {
      return null;
    }

    const principalScope = data.principal_scope;
    if (
      typeof principalScope !== 'string' ||
      !PRINCIPAL_SCOPE_PATTERN.test(principalScope)
    ) {
      return null;
    }

    const expirySeconds = data.verified_expiry;
    if (
      typeof expirySeconds !== 'number' ||
      !Number.isSafeInteger(expirySeconds) ||
      expirySeconds <= 0
    ) {
      return null;
    }
    if (expirySeconds > MAX_SAFE_EXPIRY_SECONDS) {
      return null;
    }
    const expiresAtMs = expirySeconds * MS_PER_SECOND;
    if (!Number.isSafeInteger(expiresAtMs)) {
      return null;
    }
    if (expiresAtMs <= nowMs) {
      return null;
    }

    const selectionValue = data.selection;
    if (!isClosedPlainObject(selectionValue)) {
      return null;
    }
    const selection = readOwnDataFields(selectionValue, SELECTION_KEYS);
    if (selection === null) {
      return null;
    }
    if (selection.work_ref !== workRef) {
      return null;
    }

    const capabilitiesValue = data.capabilities;
    if (!isClosedPlainObject(capabilitiesValue)) {
      return null;
    }
    const capabilities = readOwnDataFields(capabilitiesValue, CAPABILITY_KEYS);
    if (capabilities === null) {
      return null;
    }
    if (capabilities.references_read !== true) {
      return null;
    }
    if (capabilities.reply_read !== true) {
      return null;
    }

    return Object.freeze({
      workRef,
      principalScope,
      expiresAtMs,
    });
  } catch {
    return null;
  }
}
