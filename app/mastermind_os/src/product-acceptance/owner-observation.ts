import { decodeMissionv4, normalizeWorkspaceSelection, type MissionSelection, type Missionv4Document } from "../mission";

/** An internal publication attachment. It is absent until a real owner is composed. */
export interface ProductAcceptanceOwner {
  getSnapshot(): unknown;
  /** Every owner/selection transition, including ABA, must notify synchronously. */
  subscribe(listener: () => void): () => void;
}
export interface MissionV4Selection extends MissionSelection {
  requestMessageKey: string;
}
export interface ProductAcceptanceObservation {
  selector: MissionV4Selection;
  principalScope: string;
  ownerGeneration: number;
  selectionGeneration: number;
}
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: string[]) =>
  Object.keys(value).length === keys.length && keys.every(k => Object.hasOwn(value, k));
export function missionV4Selection(value: unknown): MissionV4Selection | null {
  if (!record(value) || !exact(value, ["workRef", "rootJobId", "requestMessageKey"])) return null;
  const pair = normalizeWorkspaceSelection({ workRef: value.workRef, rootJobId: value.rootJobId });
  if (!pair || typeof value.requestMessageKey !== "string" || !/^asd-mcp-[0-9a-f]{32}$/.test(value.requestMessageKey)) return null;
  return { ...pair, requestMessageKey: value.requestMessageKey };
}
export function ownerObservation(owner: ProductAcceptanceOwner | undefined): ProductAcceptanceObservation | null {
  try {
    const value = owner?.getSnapshot();
    if (!record(value) || !exact(value, ["selector", "principalScope", "ownerGeneration", "selectionGeneration"])) return null;
    const selector = missionV4Selection(value.selector);
    const generation = (n: unknown): n is number => typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
    if (!selector || typeof value.principalScope !== "string" || value.principalScope.length === 0 || value.principalScope.length > 512 || /[\u0000-\u001f\u007f]/.test(value.principalScope)
      || !generation(value.ownerGeneration) || !generation(value.selectionGeneration)) return null;
    return { selector, principalScope: value.principalScope, ownerGeneration: value.ownerGeneration, selectionGeneration: value.selectionGeneration };
  } catch { return null; }
}
export function sameAcceptanceObservation(a: ProductAcceptanceObservation | null, b: ProductAcceptanceObservation | null): boolean {
  return !!a && !!b && a.principalScope === b.principalScope && a.ownerGeneration === b.ownerGeneration && a.selectionGeneration === b.selectionGeneration
    && a.selector.workRef === b.selector.workRef && a.selector.rootJobId === b.selector.rootJobId && a.selector.requestMessageKey === b.selector.requestMessageKey;
}
/** One read lifetime, not a selector store or an authority grant. */
export function guardAcceptanceRead(owner: ProductAcceptanceOwner | undefined, selection: MissionV4Selection, authorized: () => boolean) {
  let invalidated = false;
  const before = ownerObservation(owner);
  if (!owner || !before || !authorized() || !sameAcceptanceObservation(before, { ...before, selector: selection })) throw new Error("ACCEPTANCE_OWNER_UNAVAILABLE");
  const unsubscribe = owner.subscribe(() => { invalidated = true; });
  const check = () => {
    if (invalidated || !authorized() || !sameAcceptanceObservation(before, ownerObservation(owner))) throw new Error("READ_CANCELLED");
  };
  try { check(); } catch (error) { unsubscribe(); throw error; }
  let disposed = false;
  return { check, dispose: () => { if (!disposed) { disposed = true; invalidated = true; unsubscribe(); } } };
}

/** Decode the ONE authenticated original-owner body; never discover or reread a key. */
export function decodeOriginalAcceptanceBody(value: unknown, selection: MissionSelection): Missionv4Document | null {
  try {
    if (!normalizeWorkspaceSelection(selection) || !record(value) || !record(value.product_acceptance)
      || !record(value.product_acceptance.selection)) return null;
    const key = value.product_acceptance.selection.request_message_key;
    return typeof key === "string" ? decodeMissionv4(value, selection, key) : null;
  } catch { return null; }
}
