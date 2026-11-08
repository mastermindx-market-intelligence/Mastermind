/** Native-issued draft privacy witnesses. These never grant READ/Send/action
 * authority and never hold draft text, tokens, pending operations or storage. */
import { decodeNativeDraftContinuity, type NativeDraftContinuity } from "./native-draft-continuity";
export interface NativeDraftOrigin { readonly scopeKey: string; readonly principalScope: string; readonly ownerInstance: string; readonly privacyEpoch: number }
export type NativeDraftCheck = "QUARANTINED" | "RETURNABLE" | "CLEARED";
export interface NativeDraftRecoveryOwner {
  capture(scopeKey: string): Promise<NativeDraftOrigin | null>;
  quarantine(origin: NativeDraftOrigin): boolean;
  check(origin: NativeDraftOrigin): Promise<NativeDraftCheck>;
  canReturn(origin: NativeDraftOrigin, currentScopeKey: string): boolean;
  discard(origin: NativeDraftOrigin): void;
  invalidate(): void;
  clear(): void;
}
const returnGuards = new WeakMap<object, (origin: NativeDraftOrigin, scopeKey: string) => boolean>();
/** Existing draft owners use this nominal check, never a caller's canReturn
 * boolean or an auth DTO. Only this module's native-host facet is registered. */
export function nativeDraftReturnQualified(owner: unknown, origin: NativeDraftOrigin, scopeKey: string): boolean {
  try { return !!owner && typeof owner === "object" && returnGuards.get(owner)?.(origin, scopeKey) === true; }
  catch { return false; }
}

/** Construct only inside createNativeClient with the literal zero-input Tauri
 * command. A public auth event or JSON DTO cannot mint one of these origins.
 * The caller's current scope predicate belongs to its existing draft owner. */
export function createNativeDraftRecoveryOwner(input: {
  inspect: () => Promise<unknown>;
  sourceGeneration: () => number;
  signedIn: () => boolean;
  now?: () => number;
}): NativeDraftRecoveryOwner {
  const inspect = input.inspect, generation = input.sourceGeneration, signedIn = input.signedIn, now = input.now ?? Date.now;
  let boundary = 0, known = new WeakSet<object>();
  let returns = new WeakMap<object, { document: NativeDraftContinuity; generation: number; boundary: number }>();
  const safeGeneration = () => { const value = generation(); return Number.isSafeInteger(value) && value >= 0 ? value : null; };
  const methodsCurrent = () => input.inspect === inspect && input.sourceGeneration === generation && input.signedIn === signedIn;
  const alive = (document: NativeDraftContinuity) => {
    const instant = now();
    return document.phase === "QUALIFIED" && document.principal_scope !== null && document.valid_until_ms !== null &&
      Number.isSafeInteger(instant) && instant >= 0 && instant < document.valid_until_ms;
  };
  const validScope = (key: unknown): key is string => typeof key === "string" && key.length > 0 && key.length <= 4096;
  async function read() {
    const epoch = boundary, source = safeGeneration();
    if (source === null || !methodsCurrent()) return null;
    const raw = await inspect();
    if (epoch !== boundary || source !== safeGeneration() || !methodsCurrent()) return null;
    const document = decodeNativeDraftContinuity(raw);
    return document ? { document, source, epoch } : null;
  }
  const owner: NativeDraftRecoveryOwner = Object.freeze({
    async capture(scopeKey: string) {
      if (!validScope(scopeKey)) return null;
      try {
        const value = await read();
        if (!value || !alive(value.document) || !signedIn()) return null;
        const origin = Object.freeze({ scopeKey, principalScope: value.document.principal_scope!,
          ownerInstance: value.document.owner_instance, privacyEpoch: value.document.privacy_epoch });
        known.add(origin); return origin;
      } catch { return null; }
    },
    quarantine(origin: NativeDraftOrigin) {
      if (!known.has(origin)) return false;
      returns.delete(origin); return true;
    },
    async check(origin: NativeDraftOrigin): Promise<NativeDraftCheck> {
      if (!known.has(origin)) return "CLEARED";
      returns.delete(origin);
      try {
        const value = await read();
        if (!known.has(origin)) return "CLEARED";
        if (!value) return "QUARANTINED";
        const document = value.document;
        if (document.phase === "WITHDRAWN" || document.owner_instance !== origin.ownerInstance || document.privacy_epoch !== origin.privacyEpoch ||
            document.phase === "QUALIFIED" && document.principal_scope !== origin.principalScope) {
          known.delete(origin); return "CLEARED";
        }
        if (!alive(document) || !signedIn()) return "QUARANTINED";
        returns.set(origin, { document, generation: value.source, boundary: value.epoch });
        return "RETURNABLE";
      } catch { return "QUARANTINED"; }
    },
    canReturn(origin: NativeDraftOrigin, currentScopeKey: string) {
      try {
        const value = returns.get(origin);
        return known.has(origin) && !!value && methodsCurrent() && validScope(currentScopeKey) && currentScopeKey === origin.scopeKey &&
          value.boundary === boundary && value.generation === safeGeneration() && signedIn() && alive(value.document) &&
          value.document.owner_instance === origin.ownerInstance && value.document.privacy_epoch === origin.privacyEpoch &&
          value.document.principal_scope === origin.principalScope;
      } catch { return false; }
    },
    discard(origin: NativeDraftOrigin) { known.delete(origin); returns.delete(origin); },
    invalidate() { boundary++; returns = new WeakMap(); },
    clear() { boundary++; known = new WeakSet(); returns = new WeakMap(); },
  });
  returnGuards.set(owner, owner.canReturn);
  return owner;
}
