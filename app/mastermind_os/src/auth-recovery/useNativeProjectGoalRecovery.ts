import { useRef, useState } from "react";
import type { ProjectJourneyStateApi } from "../projects/useProjectJourneyState";
import type { NativeDraftOrigin, NativeDraftRecoveryOwner } from "./native-draft-owner";

/** Metadata only. Exact goal text stays in the incumbent ProjectJourney slot.
 * App calls beforeEdit on goal focus or an explicit scope transfer, before
 * recoverable authoring, and onAuthChange BEFORE normal owner invalidation.
 * No inspection, return or send on mount. Focus itself grants no authority;
 * unavailable identity leaves ordinary editing explicitly UNBOUND. */
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
  const editMode = useRef<"UNQUALIFIED" | "CHECKING" | "BOUND" | "UNBOUND">("UNQUALIFIED");
  const editingOwner = useRef(input.owner);
  const [, setEditRevision] = useState(0);
  const setEditMode = (mode: typeof editMode.current) => {
    if (mode === "UNBOUND") editingOwner.current = live.current.owner;
    editMode.current = mode; setEditRevision(value => value + 1);
  };
  const sameOwner = (origin.current === null || origin.current.owner === input.owner) &&
    !(editMode.current === "UNBOUND" && input.journey.hasUnsentDraft() && editingOwner.current !== input.owner);
  const quarantine = input.native && (held.current || !sameOwner || origin.current !== null && boundAuth.current !== input.authGeneration);
  async function beforeEdit() {
    const current = live.current, owner = current.owner;
    if (!current.native) return;
    // A known local/nominal owner change withdraws old text BEFORE a failed
    // replacement lookup could turn it into ordinary unbound authoring.
    if (origin.current && origin.current.owner !== owner ||
        editMode.current === "UNBOUND" && current.journey.hasUnsentDraft() && editingOwner.current !== owner) {
      origin.current?.owner.discard(origin.current.value); origin.current = null;
      held.current = false; boundAuth.current = current.authGeneration;
      current.journey.invalidateAuth(false); setPhase("ACTIVE"); setEditMode("UNQUALIFIED"); return;
    }
    if (held.current || !current.journey.isHostCurrent()) return;
    const key = current.journey.currentGoalScope();
    if (!key) return;
    // Legacy/unavailable identity never freezes ordinary draft authoring. Such
    // text is UNBOUND and must never later acquire a recovery principal.
    if (!owner) { setEditMode("UNBOUND"); return; }
    if (origin.current?.owner === owner && origin.current.value.scopeKey === key && editMode.current === "BOUND") return;
    if (!origin.current && current.journey.hasUnsentDraft()) { setEditMode("UNBOUND"); return; }
    if (flight.current) return flight.current;
    const previous = origin.current, ticket = ++serial.current, generation = current.authGeneration;
    setEditMode("CHECKING");
    const task = (async () => {
      const value = await owner.capture(key);
      if (ticket !== serial.current || live.current.owner !== owner || live.current.authGeneration !== generation ||
          !live.current.journey.isHostCurrent() || live.current.journey.currentGoalScope() !== key || held.current || origin.current !== previous) {
        if (value) owner.discard(value); return;
      }
      // A capture started before an unbound edit cannot retroactively own it.
      if (!previous && live.current.journey.hasUnsentDraft()) {
        if (value) owner.discard(value); setEditMode("UNBOUND"); return;
      }
      if (!value) {
        previous?.owner.discard(previous.value); origin.current = null;
        setEditMode("UNBOUND"); return;
      }
      // Moving the same unsent slot to another safe selection preserves its
      // original native principal/instance/privacy epoch, not a later actor.
      if (previous && (previous.owner !== owner || previous.value.principalScope !== value.principalScope ||
          previous.value.ownerInstance !== value.ownerInstance || previous.value.privacyEpoch !== value.privacyEpoch)) {
        owner.discard(value); previous.owner.discard(previous.value); origin.current = null;
        current.journey.invalidateAuth(false); setEditMode("UNQUALIFIED"); return;
      }
      previous?.owner.discard(previous.value);
      origin.current = { owner, value }; boundAuth.current = generation; setEditMode("BOUND");
    })();
    flight.current = task;
    try { await task; } catch {
      if (ticket === serial.current) {
        previous?.owner.discard(previous.value); origin.current = null; setEditMode("UNBOUND");
      }
    } finally { if (flight.current === task) flight.current = null; }
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
      setEditMode("UNQUALIFIED"); current.journey.invalidateAuth(false); return false;
    }
    const unsent = current.journey.hasUnsentDraft();
    // Notification has already withdrawn the old live actor. Its guarded
    // scope reader is intentionally unavailable now; the bound origin stays
    // private, and the incumbent retained-slot scope is re-proved on return.
    if (!held.current && (!unsent || !origin.current || editMode.current !== "BOUND")) {
      origin.current?.owner.discard(origin.current.value); origin.current = null;
      boundAuth.current = current.authGeneration; setPhase("ACTIVE"); setEditMode("UNQUALIFIED");
      current.journey.invalidateAuth(false); return false;
    }
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
      boundAuth.current = live.current.authGeneration; setEditMode("UNQUALIFIED"); setPhase("ACTIVE"); return false;
    }
    if (result === "RETURNABLE" && live.current.journey.returnToNativeRetainedGoal(captured.value, captured.owner)) {
      // The SAME nominal origin owns unchanged returned text until discard,
      // logout or a qualified scope transfer. Never recapture it as a new actor.
      held.current = false; setEditMode("BOUND");
      boundAuth.current = live.current.authGeneration; setPhase("ACTIVE"); return true;
    }
    setPhase("QUARANTINED"); return false;
  }
  function discard() {
    serial.current++; flight.current = null;
    origin.current?.owner.discard(origin.current.value); origin.current = null;
    live.current.journey.invalidateAuth(false); held.current = false;
    boundAuth.current = live.current.authGeneration; setEditMode("UNQUALIFIED"); setPhase("ACTIVE");
  }
  const canEdit = !input.native || (!held.current && sameOwner && input.journey.isHostCurrent() &&
    (!input.owner || editMode.current === "UNBOUND" && editingOwner.current === input.owner || editMode.current === "BOUND" &&
      origin.current?.owner === input.owner && boundAuth.current === input.authGeneration &&
      origin.current.value.scopeKey === input.journey.currentGoalScope()));
  return { beforeEdit, onAuthChange, recover, discard, canEdit,
    quarantine, phase, hasHeld: input.native && held.current,
    canRecover: input.native && held.current && !!origin.current && sameOwner && input.journey.isHostCurrent() };
}
