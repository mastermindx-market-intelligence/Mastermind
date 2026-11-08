/** Read-only Office association using the existing Executive session owner.

A model transcript, DSH session, Slack thread, title, operation pointer or
Fabric target string alone is NOT company authority. The mounted native host
must expose one atomically qualified owner+selection+target observation.
This module creates no session, identity, cache, store, URL or sending route.
*/
import { normalizeSelection, type MissionSelection } from "../mission";
import {
  sessionTargetKind,
  type ExecutiveSessionTargetKind,
} from "../orchestration/executive-session-command-port";
import { readSessionOwnerContext, type MountedExecutiveSessionBinding } from "../orchestration/os-executive-session-host";

/** The closed canonical target-prefix union of the qualified session surface. */
export const SESSION_TARGET_REF = /^(?:fabric_attempt|hermes_secretary|hermes_meta):[0-9a-f]{64}$/;

export interface OfficeSessionContext {
  readonly sessionRef: string | null;
  readonly bindingGeneration: string | null;
}
const UNBOUND: OfficeSessionContext = Object.freeze({
  sessionRef: null,
  bindingGeneration: null,
});

/**
 * The exact observed selection. The legacy pair and the explicit three-key
 * variant are the only accepted shapes; any extra or unknown key is refused
 * rather than ignored.
 */
function decodeObservedSelection(value: unknown): {
  workRef: string; rootJobId: string; targetKind?: ExecutiveSessionTargetKind;
} | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const keys = Object.keys(value);
  const hasKind = keys.includes("targetKind");
  if (keys.length !== (hasKind ? 3 : 2)) return null;
  if (!keys.every((key) =>
    key === "workRef" || key === "rootJobId" || key === "targetKind")) {
    return null;
  }
  const workRef = (value as { workRef?: unknown }).workRef;
  const rootJobId = (value as { rootJobId?: unknown }).rootJobId;
  if (typeof workRef !== "string" || typeof rootJobId !== "string") return null;
  const kind = sessionTargetKind(value as { targetKind?: unknown });
  if (kind === null) return null;
  return { workRef, rootJobId, targetKind: kind };
}

export function qualifyExecutiveOfficeSession(
  signedIn: boolean,
  selected: MissionSelection | null,
  binding: MountedExecutiveSessionBinding | null,
): OfficeSessionContext {
  const wanted = normalizeSelection(selected);
  if (!signedIn || !binding || !wanted) return UNBOUND;
  try {
    // Older host mounts do not advertise an owner-qualified atomic
    // observation. Absence is UNBOUND, not a license to guess from a title.
    const observation = binding.port.currentObservation?.();
    const owner = readSessionOwnerContext(binding);
    if (!observation || !owner ||
        typeof observation !== "object" ||
        Array.isArray(observation) ||
        Object.keys(observation).sort().join("|") !==
          "generation|principalScope|selection|targetRef") return UNBOUND;
    // The observation carries the session selection, which may also carry the
    // closed target kind; only the work/root pair joins to the mission.
    const observed = decodeObservedSelection(observation.selection);
    if (!observed) return UNBOUND;
    if (observed.workRef !== wanted.workRef ||
        observed.rootJobId !== wanted.rootJobId) return UNBOUND;
    // The qualified target kind is part of the association identity: a kind
    // change must not reuse a previous observation.
    const observedKind = sessionTargetKind(observed);
    if (observedKind === null) return UNBOUND;
    if (typeof observation.targetRef !== "string" ||
        !SESSION_TARGET_REF.test(observation.targetRef) ||
        !observation.targetRef.startsWith(
          observedKind + ":",
        ) ||
        binding.port.currentTargetRef() !== observation.targetRef) return UNBOUND;
    if (observation.principalScope !== owner.principalScope ||
        observation.generation !== owner.generation) return UNBOUND;
    if (owner.principalScope.length > 256 || owner.generation.length > 256 ||
        /[\x00-\x1f\x7f]/.test(owner.principalScope + owner.generation)) return UNBOUND;
    // Distinguishes the owner principal and epoch without minting a fresh
    // session ID or treating a Fabric Attempt as a DSH chat identifier.
    return {
      sessionRef: observation.targetRef,
      bindingGeneration: JSON.stringify([
        "executive-native-session", owner.principalScope, owner.generation,
      ]),
    };
  } catch {
    return UNBOUND;
  }
}
