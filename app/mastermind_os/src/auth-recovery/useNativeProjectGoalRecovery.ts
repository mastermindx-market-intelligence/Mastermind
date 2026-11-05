import { useRef, useState } from "react";
import type { ProjectJourneyStateApi } from "../projects/useProjectJourneyState";
import type { NativeDraftOrigin, NativeDraftRecoveryOwner } from "./native-draft-owner";

/** Metadata only. Exact goal text stays in the incumbent ProjectJourney slot.
 * App calls beforeEdit on an explicit edit and onAuthChange BEFORE its normal
 * source/controller invalidation. No work/source reads, return or send on mount. */
export function useNativeProjectGoalRecovery(input: {
  native: boolean;
  owner?: NativeDraftRecoveryOwner;
  journey: ProjectJourneyStateApi;
  authGeneration: number;
}) {
  const live = useRef(input); live.current = input;
  const origin = useRef<{ owner: NativeDraftRecoveryOwner; value: NativeDraftOrigin } | null>(null);
  const flight = useRef<Promise<void> | null>(null), serial = useRef(0);
  const [phase, setPhase] = useState<"ACTIVE" | "QUARANTINED" | "CHECKING">("ACTIVE");
  const held = useRef(false), boundAuth = useRef(input.authGeneration);
  const sameOwner = origin.current === null || origin.current.owner === input.owner;
  const quarantine = input.native && (held.current || !sameOwner || origin.current !== null && boundAuth.current !== input.authGeneration);
  async function beforeEdit() {
    const current = live.current, owner = current.owner;
    if (!current.native || !owner || held.current || !current.journey.isHostCurrent()) return;
    const key = current.journey.currentGoalScope();
    if (!key) return;
    if (origin.current?.owner === owner && origin.current.value.scopeKey === key) return;
    if (flight.current) return flight.current;
    const ticket = ++serial.current, generation = current.authGeneration;
    const task = (async () => {
      const value = await owner.capture(key);
      if (ticket !== serial.current || live.current.owner !== owner || live.current.authGeneration !== generation ||
          !live.current.journey.isHostCurrent() || live.current.journey.currentGoalScope() !== key || held.current) return;
      if (value) { origin.current = { owner, value }; boundAuth.current = generation; }
    })();
    flight.current = task;
    try { await task; } catch { /* unqualified identity stays unbound */ }
    finally { if (flight.current === task) flight.current = null; }
  }
  /** A public event may quarantine, never qualify identity or show held text.
   * Explicit logout is destructive; preserve flag never touches action pointers. */
  function onAuthChange(explicitLogout = false): boolean {
    const current = live.current;
    serial.current++; flight.current = null;
    if (!current.native) return false;
    if (explicitLogout) {
      origin.current?.owner.discard(origin.current.value); origin.current = null;
      held.current = false; boundAuth.current = current.authGeneration; setPhase("ACTIVE");
      current.journey.invalidateAuth(false); return false;
    }
    const unsent = current.journey.hasUnsentDraft();
    if (unsent || held.current) {
      if (origin.current && !origin.current.owner.quarantine(origin.current.value)) {
        origin.current = null; held.current = false; boundAuth.current = current.authGeneration;
        setPhase("ACTIVE"); current.journey.invalidateAuth(false); return false;
      }
      held.current = true; origin.current?.owner.quarantine(origin.current.value);
      setPhase("QUARANTINED"); current.journey.invalidateAuth(true); return true;
    }
    return false;
  }
  async function recover() {
    const current = live.current, captured = origin.current;
    if (!current.native || !held.current || !captured || current.owner !== captured.owner) return false;
    const ticket = ++serial.current;
    setPhase("CHECKING");
    const result = await captured.owner.check(captured.value);
    if (ticket !== serial.current || live.current.owner !== captured.owner || origin.current !== captured) return false;
    if (result === "CLEARED") {
      live.current.journey.invalidateAuth(false); origin.current = null; held.current = false;
      boundAuth.current = live.current.authGeneration; setPhase("ACTIVE"); return false;
    }
    if (result === "RETURNABLE" && live.current.journey.returnToNativeRetainedGoal(captured.value, captured.owner)) {
      captured.owner.discard(captured.value); origin.current = null; held.current = false;
      boundAuth.current = live.current.authGeneration; setPhase("ACTIVE"); return true;
    }
    setPhase("QUARANTINED"); return false;
  }
  function discard() {
    serial.current++; flight.current = null;
    origin.current?.owner.discard(origin.current.value); origin.current = null;
    live.current.journey.invalidateAuth(false); held.current = false;
    boundAuth.current = live.current.authGeneration; setPhase("ACTIVE");
  }
  return { beforeEdit, onAuthChange, recover, discard,
    quarantine, phase, hasHeld: input.native && held.current,
    canRecover: input.native && held.current && !!origin.current && sameOwner && input.journey.isHostCurrent() };
}
