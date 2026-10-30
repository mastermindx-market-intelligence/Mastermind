/** Read-only Office association using the existing Executive session owner.

A model transcript, DSH session, Slack thread, title, operation pointer or
Fabric target string alone is NOT company authority. The mounted native host
must expose one atomically qualified owner+selection+target observation.
This module creates no session, identity, cache, store, URL or sending route.
*/
import { normalizeSelection, type MissionSelection } from "../mission";
import { readSessionOwnerContext, type MountedExecutiveSessionBinding } from "../orchestration/os-executive-session-host";

export const SESSION_TARGET_REF = /^fabric_attempt:[0-9a-f]{64}$/;

export interface OfficeSessionContext {
  readonly sessionRef: string | null;
  readonly bindingGeneration: string | null;
}
const UNBOUND: OfficeSessionContext = Object.freeze({
  sessionRef: null,
  bindingGeneration: null,
});

export function qualifyExecutiveOfficeSession(
  signedIn: boolean,
  selected: MissionSelection | null,
  binding: MountedExecutiveSessionBinding | null,
): OfficeSessionContext {
  if (!signedIn || !binding || !normalizeSelection(selected)) return UNBOUND;
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
    const match = normalizeSelection(observation.selection);
    if (!match || match.workRef !== selected!.workRef ||
        match.rootJobId !== selected!.rootJobId) return UNBOUND;
    if (typeof observation.targetRef !== "string" ||
        !SESSION_TARGET_REF.test(observation.targetRef) ||
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
