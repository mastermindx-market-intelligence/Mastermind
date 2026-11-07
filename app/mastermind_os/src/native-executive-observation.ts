/**
 * Closed decoder for the native executive status observation payload.
 *
 * Pure and total: no I/O, no storage, no clock, no global mutable state. The
 * decoder accepts unknown input and returns a deeply frozen, detached,
 * normalized observation or null. Accessors are never evaluated: object,
 * key-set and property-descriptor checks all run before any value is read,
 * and the whole decode is guarded so no hostile input can throw out of the
 * function. Input is never echoed, stringified or retained on any path.
 */

export type NativeExecutiveReason =
  | 'UNCONFIGURED'
  | 'NOT_ESTABLISHED'
  | 'AUTHORIZING'
  | 'EXCHANGING'
  | 'AVAILABLE'
  | 'EXPIRED'
  | 'AUTHORIZATION_REFUSED'
  | 'TOKEN_EXCHANGE_FAILED'
  | 'TOKEN_RESPONSE_INVALID'
  | 'AUTH_BROWSER_UNAVAILABLE'
  | 'AUTH_TRANSACTION_EXPIRED'
  | 'GENERATION_EXHAUSTED';

export type NativeProgramsReadPhase =
  | 'NOT_OBSERVED'
  | 'PENDING'
  | 'READY'
  | 'AUTH_UNAVAILABLE'
  | 'HTTP_FAILURE'
  | 'NETWORK_FAILURE'
  | 'TIMEOUT'
  | 'BODY_FAILURE'
  | 'INVALID_RESPONSE';

export type NativeProgramsRead = Readonly<{
  phase: NativeProgramsReadPhase;
  httpStatus: number | null;
}>;

export type NativeExecutiveObservation =
  | Readonly<{
      wire: 'legacy';
      generation: number;
      available: boolean;
      configured: null;
      reason: null;
      programsRead: null;
    }>
  | Readonly<{
      wire: 'v1';
      generation: number;
      available: boolean;
      configured: boolean;
      reason: NativeExecutiveReason;
      programsRead: NativeProgramsRead;
    }>;

export const NATIVE_EXECUTIVE_STATUS_SCHEMA = 'mastermind.native_executive_status.v1';

export const NATIVE_EXECUTIVE_REASON_VALUES: readonly NativeExecutiveReason[] = [
  'UNCONFIGURED',
  'NOT_ESTABLISHED',
  'AUTHORIZING',
  'EXCHANGING',
  'AVAILABLE',
  'EXPIRED',
  'AUTHORIZATION_REFUSED',
  'TOKEN_EXCHANGE_FAILED',
  'TOKEN_RESPONSE_INVALID',
  'AUTH_BROWSER_UNAVAILABLE',
  'AUTH_TRANSACTION_EXPIRED',
  'GENERATION_EXHAUSTED',
];

export const NATIVE_PROGRAMS_READ_PHASE_VALUES: readonly NativeProgramsReadPhase[] = [
  'NOT_OBSERVED',
  'PENDING',
  'READY',
  'AUTH_UNAVAILABLE',
  'HTTP_FAILURE',
  'NETWORK_FAILURE',
  'TIMEOUT',
  'BODY_FAILURE',
  'INVALID_RESPONSE',
];

const REASON_MEMBERS: ReadonlySet<string> = new Set<string>(NATIVE_EXECUTIVE_REASON_VALUES);
const PHASE_MEMBERS: ReadonlySet<string> = new Set<string>(NATIVE_PROGRAMS_READ_PHASE_VALUES);
const UNCONFIGURED_REASON_MEMBERS: ReadonlySet<string> = new Set<string>([
  'UNCONFIGURED',
  'GENERATION_EXHAUSTED',
]);

const LEGACY_KEYS: readonly string[] = ['generation', 'available'];
const EXTENDED_KEYS: readonly string[] = [
  'schema',
  'generation',
  'available',
  'configured',
  'reason',
  'programs_read',
];
const PROGRAMS_KEYS: readonly string[] = ['phase', 'http_status'];

function deepFreeze<T>(value: T): T {
  if (value === null || typeof value !== 'object') {
    return value;
  }
  const source = value as Record<PropertyKey, unknown>;
  for (const key of Reflect.ownKeys(source)) {
    deepFreeze(source[key]);
  }
  Object.freeze(source);
  return value;
}

function isCandidateObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

/**
 * Verifies the own-key set equals `expected` exactly and that every own
 * property is a plain data property. Accessors are detected from descriptors
 * and rejected without ever being invoked; throwing proxies are caught.
 */
function hasExactDataShape(value: object, expected: readonly string[]): boolean {
  let ownKeys: readonly (string | symbol)[];
  try {
    ownKeys = Reflect.ownKeys(value);
  } catch {
    return false;
  }
  if (ownKeys.length !== expected.length) {
    return false;
  }
  for (const key of ownKeys) {
    if (typeof key !== 'string' || expected.indexOf(key) === -1) {
      return false;
    }
  }
  for (const key of expected) {
    let descriptor: PropertyDescriptor | undefined;
    try {
      descriptor = Object.getOwnPropertyDescriptor(value, key);
    } catch {
      return false;
    }
    if (descriptor === undefined) {
      return false;
    }
    if (typeof descriptor.get === 'function' || typeof descriptor.set === 'function') {
      return false;
    }
    if (!('value' in descriptor)) {
      return false;
    }
  }
  return true;
}

function decodeGeneration(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    return null;
  }
  return value === 0 ? 0 : value;
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === 'boolean';
}

function decodeReason(value: unknown): NativeExecutiveReason | null {
  if (typeof value !== 'string' || !REASON_MEMBERS.has(value)) {
    return null;
  }
  return value as NativeExecutiveReason;
}

/** Returns undefined to signal a malformed status, null for an absent one. */
function decodeProgramsStatus(value: unknown): number | null | undefined {
  if (value === null) {
    return null;
  }
  if (typeof value === 'number' && Number.isInteger(value)) {
    return value;
  }
  return undefined;
}

function phaseAllowsStatus(phase: NativeProgramsReadPhase, httpStatus: number | null): boolean {
  switch (phase) {
    case 'READY':
    case 'BODY_FAILURE':
    case 'INVALID_RESPONSE':
      return httpStatus !== null && httpStatus >= 200 && httpStatus <= 299;
    case 'HTTP_FAILURE':
      return (
        httpStatus !== null &&
        httpStatus >= 100 &&
        httpStatus <= 599 &&
        (httpStatus < 200 || httpStatus > 299)
      );
    case 'NOT_OBSERVED':
    case 'PENDING':
    case 'AUTH_UNAVAILABLE':
    case 'NETWORK_FAILURE':
    case 'TIMEOUT':
      return httpStatus === null;
    default:
      return false;
  }
}

function decodeProgramsRead(value: unknown): NativeProgramsRead | null {
  if (!isCandidateObject(value) || !hasExactDataShape(value, PROGRAMS_KEYS)) {
    return null;
  }
  const rawPhase: unknown = value['phase'];
  if (typeof rawPhase !== 'string' || !PHASE_MEMBERS.has(rawPhase)) {
    return null;
  }
  const phase = rawPhase as NativeProgramsReadPhase;
  const httpStatus = decodeProgramsStatus(value['http_status']);
  if (httpStatus === undefined || !phaseAllowsStatus(phase, httpStatus)) {
    return null;
  }
  const programsRead: NativeProgramsRead = { phase, httpStatus };
  return deepFreeze(programsRead);
}

function isCrossFieldValid(
  available: boolean,
  configured: boolean,
  reason: NativeExecutiveReason,
): boolean {
  if (available) {
    return reason === 'AVAILABLE' && configured;
  }
  if (reason === 'AVAILABLE') {
    return false;
  }
  if (!configured) {
    return UNCONFIGURED_REASON_MEMBERS.has(reason);
  }
  return !UNCONFIGURED_REASON_MEMBERS.has(reason);
}

function decodeLegacyObservation(raw: Record<string, unknown>): NativeExecutiveObservation | null {
  if (!hasExactDataShape(raw, LEGACY_KEYS)) {
    return null;
  }
  const generation = decodeGeneration(raw['generation']);
  const available = raw['available'];
  if (generation === null || !isBoolean(available)) {
    return null;
  }
  const observation: NativeExecutiveObservation = {
    wire: 'legacy',
    generation,
    available,
    configured: null,
    reason: null,
    programsRead: null,
  };
  return deepFreeze(observation);
}

function decodeExtendedObservation(raw: Record<string, unknown>): NativeExecutiveObservation | null {
  if (!hasExactDataShape(raw, EXTENDED_KEYS)) {
    return null;
  }
  if (raw['schema'] !== NATIVE_EXECUTIVE_STATUS_SCHEMA) {
    return null;
  }
  const generation = decodeGeneration(raw['generation']);
  const available = raw['available'];
  const configured = raw['configured'];
  const reason = decodeReason(raw['reason']);
  const programsRead = decodeProgramsRead(raw['programs_read']);
  if (
    generation === null ||
    !isBoolean(available) ||
    !isBoolean(configured) ||
    reason === null ||
    programsRead === null ||
    !isCrossFieldValid(available, configured, reason)
  ) {
    return null;
  }
  const observation: NativeExecutiveObservation = {
    wire: 'v1',
    generation,
    available,
    configured,
    reason,
    programsRead,
  };
  return deepFreeze(observation);
}

function decodeObservation(raw: unknown): NativeExecutiveObservation | null {
  if (!isCandidateObject(raw)) {
    return null;
  }
  if (hasExactDataShape(raw, LEGACY_KEYS)) {
    return decodeLegacyObservation(raw);
  }
  if (hasExactDataShape(raw, EXTENDED_KEYS)) {
    return decodeExtendedObservation(raw);
  }
  return null;
}

export function decodeNativeExecutiveObservation(raw: unknown): NativeExecutiveObservation | null {
  try {
    return decodeObservation(raw);
  } catch {
    return null;
  }
}
