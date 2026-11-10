/**
 * Strict pure decoder for `mastermind.native_draft_continuity.v1` — public
 * native draft continuity metadata. Syntax validation only: the decoder is
 * neither an issuer nor a grant, performs no clock, identity, retention or
 * permission inference, and a decoded record never by itself authorizes
 * showing a draft — native-facet ownership and original-scope checks remain
 * mandatory upstream. No IO, no mutation, no getters or `toJSON` invoked,
 * no external imports. Inputs must be plain canonical JSON (exact own
 * enumerable data keys, data properties only, no symbols, no foreign
 * prototypes, no arrays); anything else — including exceptions thrown by
 * hostile proxies — decodes to `null`.
 */
export interface NativeDraftContinuity {
  schema: 'mastermind.native_draft_continuity.v1';
  owner_instance: string;
  privacy_epoch: number;
  phase: 'UNQUALIFIED' | 'QUALIFIED' | 'EXPIRED' | 'REAUTHENTICATING' | 'WITHDRAWN';
  cause:
    | 'OWNER_UNQUALIFIED'
    | 'OWNER_QUALIFIED'
    | 'PRINCIPAL_CHANGED'
    | 'TOKEN_EXPIRED'
    | 'REAUTHENTICATION'
    | 'EXPLICIT_LOGOUT'
    | 'EPOCH_EXHAUSTED';
  principal_scope: string | null;
  valid_until_ms: number | null;
}

const CONTINUITY_SCHEMA = 'mastermind.native_draft_continuity.v1';
const FIELD_KEYS = [
  'schema', 'owner_instance', 'privacy_epoch', 'phase', 'cause', 'principal_scope', 'valid_until_ms',
] as const;
const PHASE_CAUSES: Readonly<Record<string, ReadonlySet<string>>> = {
  UNQUALIFIED: new Set(['OWNER_UNQUALIFIED']),
  QUALIFIED: new Set(['OWNER_QUALIFIED', 'PRINCIPAL_CHANGED']),
  EXPIRED: new Set(['TOKEN_EXPIRED']),
  REAUTHENTICATING: new Set(['REAUTHENTICATION']),
  WITHDRAWN: new Set(['EXPLICIT_LOGOUT', 'EPOCH_EXHAUSTED']),
};
const QUALIFIED_PHASE = 'QUALIFIED';
// Anchored patterns must consume the entire value, so a trailing newline is rejected.
const OWNER_INSTANCE_PATTERN = /^[0-9a-f]{32}$(?![\s\S])/;
const PRINCIPAL_SCOPE_PATTERN = /^[0-9a-f]{64}$(?![\s\S])/;
const MIN_PRIVACY_EPOCH_QUALIFIED = 1;
const MIN_VALID_UNTIL_MS = 1;
const MAX_VALID_UNTIL_MS = 8640000000000000;

/** Accepts only plain `Object.prototype` objects of enumerable data properties. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  if (Object.getPrototypeOf(value) !== Object.prototype) return false;
  if (Object.getOwnPropertySymbols(value).length !== 0) return false;
  const names = Object.getOwnPropertyNames(value);
  if (Object.keys(value).length !== names.length) return false;
  for (const name of names) {
    const descriptor = Object.getOwnPropertyDescriptor(value, name);
    if (descriptor === undefined || descriptor.get !== undefined || descriptor.set !== undefined) return false;
  }
  return true;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== keys.length) return false;
  for (const key of keys) if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  return true;
}

/**
 * Decodes public native draft continuity metadata into a detached, deeply
 * frozen plain object, or returns `null` for anything outside the closed
 * syntax contract. The result carries no authority to display a draft.
 */
export function decodeNativeDraftContinuity(raw: unknown): NativeDraftContinuity | null {
  try {
    if (!isPlainObject(raw) || !hasExactKeys(raw, FIELD_KEYS)) return null;
    if (raw.schema !== CONTINUITY_SCHEMA) return null;
    const ownerInstance = raw.owner_instance;
    if (typeof ownerInstance !== 'string' || !OWNER_INSTANCE_PATTERN.test(ownerInstance)) return null;
    const privacyEpoch = raw.privacy_epoch;
    if (typeof privacyEpoch !== 'number' || !Number.isSafeInteger(privacyEpoch) || privacyEpoch < 0) return null;
    const phase = raw.phase;
    if (typeof phase !== 'string' || !Object.prototype.hasOwnProperty.call(PHASE_CAUSES, phase)) return null;
    const allowedCauses = PHASE_CAUSES[phase];
    if (allowedCauses === undefined) return null;
    const cause = raw.cause;
    if (typeof cause !== 'string' || !allowedCauses.has(cause)) return null;
    const principalScope = raw.principal_scope;
    const validUntilMs = raw.valid_until_ms;
    if (phase === QUALIFIED_PHASE) {
      if (typeof principalScope !== 'string' || !PRINCIPAL_SCOPE_PATTERN.test(principalScope)) return null;
      if (
        typeof validUntilMs !== 'number'
        || !Number.isSafeInteger(validUntilMs)
        || validUntilMs < MIN_VALID_UNTIL_MS
        || validUntilMs > MAX_VALID_UNTIL_MS
      ) {
        return null;
      }
      if (privacyEpoch < MIN_PRIVACY_EPOCH_QUALIFIED) return null;
    } else if (principalScope !== null || validUntilMs !== null) {
      return null;
    }
    const decoded: NativeDraftContinuity = {
      schema: CONTINUITY_SCHEMA,
      owner_instance: ownerInstance,
      privacy_epoch: privacyEpoch,
      phase: phase as NativeDraftContinuity['phase'],
      cause: cause as NativeDraftContinuity['cause'],
      principal_scope: principalScope,
      valid_until_ms: validUntilMs,
    };
    return Object.freeze(decoded);
  } catch {
    return null;
  }
}
