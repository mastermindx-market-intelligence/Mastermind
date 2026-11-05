import { useCallback, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { nativeDraftReturnQualified, type NativeDraftOrigin, type NativeDraftRecoveryOwner } from "../auth-recovery/native-draft-owner";
import { projectGoalDraftScope } from "../auth-recovery/project-goal-scope";
import type { ProjectJourneySelection } from "./ProjectPlanningJourney";
import {
  PROJECT_JOURNEY_FLAG_KEY,
  PROJECT_JOURNEY_FLAG_VALUE,
  commitProjectJourneySelection,
  readProjectJourneyLocation,
  type ProjectJourneyReadResult,
} from "./project-journey-location";

/** The mounted host surface this presentation reads; never a new authority. */
export type ProjectJourneyHost = Pick<MissionHost, "auth" | "invalidationGeneration" | "nativeDraftRecovery">;

export interface ProjectJourneyRetainedGoal {
  readonly text: string;
  readonly selection: ProjectJourneySelection | null;
  readonly passivelyHeld: boolean;
}

export interface ProjectJourneyStateProps {
  /** The App's existing mounted host; live identity is re-proved per gesture. */
  host: ProjectJourneyHost | null;
  /** The App auth epoch captured at render; drift refuses every mutation. */
  authRevision: number;
  /** Live epoch reader (the parent's revision ref); part of every proof. */
  currentAuthRevision: () => number;
}

export interface ProjectJourneyStateApi {
  shown: boolean;
  invalidLink: boolean;
  selection: ProjectJourneySelection | null;
  goal: string;
  goalBelongsToSelection: boolean;
  retainedGoal: ProjectJourneyRetainedGoal | null;
  isHostCurrent: () => boolean;
  hasUnsentDraft: () => boolean;
  /** Current safe draft lookup after an explicit selection gesture; no authority. */
  currentGoalScope: () => string | null;
  open: () => boolean;
  hide: () => void;
  onSelection: (value: ProjectJourneySelection) => void;
  onGoalChange: (text: string) => void;
  invalidateAuth: (preserve: boolean) => void;
  restoreLocation: () => void;
  returnToRetainedGoal: () => boolean;
  /** Explicit same-principal native privacy recovery; never a source/action grant. */
  returnToNativeRetainedGoal: (origin: NativeDraftOrigin, owner: NativeDraftRecoveryOwner) => boolean;
  editRetainedGoal: (text: string) => void;
  discardRetainedGoal: () => void;
}

/** One render-captured host/epoch/generation triple. Any later drift makes
 * owned text foreign: no latest-props rewrite ever re-authorizes a callback. */
interface JourneyActor {
  readonly host: ProjectJourneyHost;
  readonly epoch: number;
  readonly generation: number;
}

interface OwnedGoal {
  readonly text: string;
  readonly actor: JourneyActor;
  /** CREATE identity the text belongs to; null on the blank journey. */
  readonly createRequestId: string | null;
}

interface RetainedGoalState extends ProjectJourneyRetainedGoal {
  /** The actor and host instance that owned or preserved the text. */
  readonly actor: JourneyActor;
  readonly host: ProjectJourneyHost;
}

interface JourneyState {
  readonly shown: boolean;
  readonly invalidLink: boolean;
  /** Detached, reader-validated selection DATA; never evidence of a grant. */
  readonly selection: ProjectJourneySelection | null;
  readonly goal: OwnedGoal | null;
  readonly retained: RetainedGoalState | null;
}

function actorEquals(left: JourneyActor | null, right: JourneyActor | null): boolean {
  return left !== null && right !== null &&
    left.host === right.host && left.epoch === right.epoch && left.generation === right.generation;
}

/** The draft is visible only while its authoring context is still the
 * rendering context and it still belongs to the shown CREATE identity. */
function goalVisible(state: JourneyState, actor: JourneyActor | null): boolean {
  const goal = state.goal;
  if (goal === null || !actorEquals(goal.actor, actor)) return false;
  return goal.createRequestId === (state.selection?.createRequestId ?? null);
}

function retainedExposed(retained: RetainedGoalState | null, actor: JourneyActor | null): boolean {
  if (retained === null) return false;
  return actorEquals(retained.actor, actor) ||
    (retained.passivelyHeld && actor !== null && retained.host === actor.host);
}

function readJourneyLocation(): ProjectJourneyReadResult {
  try {
    return readProjectJourneyLocation(window.location.href);
  } catch {
    return { valid: false, open: false, selection: null };
  }
}

function captureActor(host: ProjectJourneyHost | null, authRevision: number): JourneyActor | null {
  if (host === null || !Number.isSafeInteger(authRevision)) return null;
  let generation: number | undefined;
  try {
    generation = host.invalidationGeneration?.();
  } catch {
    return null;
  }
  if (generation === undefined || !Number.isSafeInteger(generation) || generation < 0) return null;
  return { host, epoch: authRevision, generation };
}

/** The exact currency proof of every mutation handler and of isHostCurrent:
 * live global host identity, live epoch, live source generation and a real
 * signed-in acquisition. Any throw refuses without mutation. */
function journeyActorCurrent(actor: JourneyActor | null, currentAuthRevision: () => number): boolean {
  if (actor === null || typeof window === "undefined") return false;
  try {
    if (window.MastermindMissionHost !== actor.host) return false;
    if (currentAuthRevision() !== actor.epoch) return false;
    if (actor.host.invalidationGeneration?.() !== actor.generation) return false;
    const auth = actor.host.auth?.getState();
    return auth?.status === "signed_in" && auth.acquisition === true;
  } catch {
    return false;
  }
}

function initialJourneyState(): JourneyState {
  const read = readJourneyLocation();
  if (!read.valid) {
    return { shown: false, invalidLink: true, selection: null, goal: null, retained: null };
  }
  if (!read.open) {
    return { shown: false, invalidLink: false, selection: null, goal: null, retained: null };
  }
  return { shown: true, invalidLink: false, selection: read.selection, goal: null, retained: null };
}

/** Close the pane. Visible owned text parks in the single retained slot
 * instead of being silently dropped; foreign text just becomes invisible. */
function closeJourney(state: JourneyState, actor: JourneyActor, invalid: boolean): JourneyState {
  const goal = state.goal;
  const parked = goal !== null && goalVisible(state, actor);
  return {
    ...state,
    shown: false,
    invalidLink: invalid,
    selection: null,
    goal: null,
    retained: parked
      ? { text: goal.text, selection: state.selection, passivelyHeld: false, actor, host: actor.host }
      : state.retained,
  };
}

function parkOwnedGoal(state: JourneyState, actor: JourneyActor): JourneyState {
  const goal = state.goal;
  if (goal === null || !goalVisible(state, actor)) return { ...state, goal: null };
  return {
    ...state,
    goal: null,
    retained: { text: goal.text, selection: state.selection, passivelyHeld: false, actor, host: actor.host },
  };
}

/** Move the journey to `next`. The same CREATE identity (or the hook's own
 * blank -> minted gesture) keeps the draft; any other identity refuses the
 * silent overwrite by parking the visible draft first. */
function adoptSelection(
  state: JourneyState,
  actor: JourneyActor,
  next: ProjectJourneySelection | null,
  markShown: boolean,
  ownBlankMint: boolean,
): JourneyState {
  const currentId = state.selection?.createRequestId ?? null;
  const nextId = next?.createRequestId ?? null;
  const sameJourney = currentId === nextId || (ownBlankMint && state.selection === null && next !== null);
  if (sameJourney) {
    return {
      ...state,
      shown: markShown ? true : state.shown,
      invalidLink: false,
      selection: next,
      goal: state.goal === null ? null : { ...state.goal, createRequestId: nextId },
    };
  }
  const parked = parkOwnedGoal(state, actor);
  return { ...parked, shown: markShown ? true : parked.shown, invalidLink: false, selection: next };
}

/** Commit the armed blank journey URL: origin and path preserved, prior
 * search (including any private or credential-bearing part) and hash never
 * carried over, exactly the flag key written. One guarded replaceState runs
 * before adoption; a rejected write suppresses the state update and
 * propagates unchanged, mirroring the URL adapter's own contract. The
 * adapter's writer only emits selection URLs, so the flag-only URL is
 * composed here from its exported key/value constants under the same rules. */
function writeBlankJourneyUrl(onCommitted: () => void): void {
  const url = new URL(window.location.href);
  const href = `${url.protocol}//${url.host}${url.pathname}` +
    `?${PROJECT_JOURNEY_FLAG_KEY}=${PROJECT_JOURNEY_FLAG_VALUE}`;
  window.history.replaceState(null, "", href);
  onCommitted();
}

/**
 * useProjectJourneyState — App-owned presentation state of the one
 * New-project -> initial planning journey.
 *
 * OWNERSHIP. Only local React state/refs and the safe URL projection through
 * the existing URL adapter. No request, port, pending-pointer persistence,
 * id mint, session/config/draft registry, permission grant, DOM focus or
 * auth subscription; no lifecycle handlers are installed here. Selection
 * DATA is read from the URL on mount and on restoreLocation; the goal is
 * user-authored local text and is never carried in the URL, storage or any
 * host field. Host.selection/Mission/catalogue are never consulted.
 *
 * CURRENCY. Every draft/navigation mutation closes over the render-captured
 * host, epoch and source generation and re-proves all of them live, plus
 * signed-in acquisition, before acting. Callbacks from an earlier render
 * stay refused after the global host, the epoch or the generation moves;
 * only hasUnsentDraft and invalidateAuth are stable (for the parent's
 * mount-once navigation hold and auth subscription) and they only read the
 * hook's own state.
 *
 * RETENTION. Cross-actor (host/epoch/generation) text is never returned as
 * current. A same-actor draft refused by a different CREATE restore, and the
 * current owned text at a passive auth expiry, park in the single retained
 * slot for the parent's existing return/discard and passive-expiry hold
 * policies. Retained DATA is presentation only, never a credential, grant
 * or source effect.
 */
export function useProjectJourneyState(props: ProjectJourneyStateProps): ProjectJourneyStateApi {
  const { host, authRevision, currentAuthRevision } = props;
  const actor = captureActor(host, authRevision);
  const isCurrent = () => journeyActorCurrent(actor, currentAuthRevision);
  const ensureCurrent = (): JourneyActor | null =>
    actor !== null && journeyActorCurrent(actor, currentAuthRevision) ? actor : null;

  const [state, setState] = useState(initialJourneyState);
  const stateRef = useRef(state);
  const apply = useCallback((next: JourneyState) => {
    stateRef.current = next;
    setState(next);
  }, []);
  // Read-side currency for the stable probes and the auth notification only.
  // No mutation handler consults it, so late callbacks can never be
  // re-authorized by a newer render.
  const latestActor = useRef<JourneyActor | null>(actor);
  latestActor.current = actor;

  const open = (): boolean => {
    const live = ensureCurrent();
    if (live === null) return false;
    const current = stateRef.current;
    if (current.selection !== null) {
      // Resume the known original operation; never reset it to a fresh blank.
      commitProjectJourneySelection(window.location.href, current.selection, window.history, (committed) => {
        apply({ ...current, shown: true, invalidLink: false, selection: committed });
      });
      return true;
    }
    const retained = current.retained;
    // With no current selection, an explicitly parked same-actor goal resumes
    // its own journey. Passively held cross-actor text never becomes current
    // here; the parent's passive-expiry policy owns that decision.
    if (retained !== null && !retained.passivelyHeld && actorEquals(retained.actor, live) &&
        !goalVisible(current, live)) {
      const goal: OwnedGoal = {
        text: retained.text,
        actor: live,
        createRequestId: retained.selection?.createRequestId ?? null,
      };
      const resumed = (selection: ProjectJourneySelection | null) =>
        apply({ ...current, shown: true, invalidLink: false, selection, goal, retained: null });
      if (retained.selection === null) writeBlankJourneyUrl(() => resumed(null));
      else commitProjectJourneySelection(window.location.href, retained.selection, window.history, resumed);
      return true;
    }
    writeBlankJourneyUrl(() => apply({ ...current, shown: true, invalidLink: false, selection: null }));
    return true;
  };

  const hide = (): void => {
    if (ensureCurrent() === null) return;
    const current = stateRef.current;
    // Local pane visibility only: the safe URL ids stay for reopen, and an
    // off-view owned draft stays held.
    if (current.shown || current.invalidLink) apply({ ...current, shown: false, invalidLink: false });
  };

  const onGoalChange = (text: string): void => {
    const live = ensureCurrent();
    if (live === null) return;
    const current = stateRef.current;
    if (!current.shown) return;
    apply({
      ...current,
      goal: text === ""
        ? null
        : { text, actor: live, createRequestId: current.selection?.createRequestId ?? null },
    });
  };

  const onSelection = (value: ProjectJourneySelection): void => {
    const live = ensureCurrent();
    if (live === null) return;
    // Safe URL synchronously BEFORE any adoption; the adapter returns a
    // detached validated copy, and a rejected write suppresses the update.
    commitProjectJourneySelection(window.location.href, value, window.history, (committed) => {
      apply(adoptSelection(stateRef.current, live, committed, false, true));
    });
  };

  const restoreLocation = (): void => {
    const live = ensureCurrent();
    if (live === null) return;
    const read = readJourneyLocation();
    const current = stateRef.current;
    if (!read.valid) {
      apply(closeJourney(current, live, true));
      return;
    }
    if (!read.open) {
      apply(closeJourney(current, live, false));
      return;
    }
    apply(adoptSelection(current, live, read.selection, true, false));
  };

  const returnToRetainedGoal = (): boolean => {
    const live = ensureCurrent();
    if (live === null) return false;
    const current = stateRef.current;
    const retained = current.retained;
    if (retained === null || retained.passivelyHeld || !actorEquals(retained.actor, live)) return false;
    const goal: OwnedGoal = {
      text: retained.text,
      actor: live,
      createRequestId: retained.selection?.createRequestId ?? null,
    };
    // A currently visible draft swaps into the retained slot instead of
    // being silently overwritten by the explicit return.
    const swap: RetainedGoalState | null =
      current.goal !== null && goalVisible(current, live) && current.goal.text !== retained.text
        ? { text: current.goal.text, selection: current.selection, passivelyHeld: false, actor: live, host: live.host }
        : null;
    const restore = (selection: ProjectJourneySelection | null) =>
      apply({ ...current, shown: true, invalidLink: false, selection, goal, retained: swap });
    if (retained.selection === null) writeBlankJourneyUrl(() => restore(null));
    else commitProjectJourneySelection(window.location.href, retained.selection, window.history, restore);
    return true;
  };

  const returnToNativeRetainedGoal = (origin: NativeDraftOrigin, owner: NativeDraftRecoveryOwner): boolean => {
    const actor = ensureCurrent(), current = stateRef.current, retained = current.retained;
    if (!actor || actor.host.nativeDraftRecovery !== owner || !retained || !retained.passivelyHeld || retained.host !== actor.host) return false;
    const scope = projectGoalDraftScope(retained.selection);
    if (!scope || !nativeDraftReturnQualified(owner, origin, scope)) return false;
    const swap = current.goal && goalVisible(current, actor) && current.goal.text !== retained.text
      ? { text: current.goal.text, selection: current.selection, passivelyHeld: false, actor, host: actor.host } : null;
    let restored = false;
    const restore = (selection: ProjectJourneySelection | null) => {
      // History callbacks and stale click closures cannot restore text after
      // an intervening auth/host/selection change. Tokens/operations stay out.
      if (stateRef.current !== current || !actorEquals(ensureCurrent(), actor) || actor.host.nativeDraftRecovery !== owner || !nativeDraftReturnQualified(owner, origin, scope)) return;
      apply({ ...current, shown: true, invalidLink: false, selection,
        goal: { text: retained.text, actor, createRequestId: retained.selection?.createRequestId ?? null }, retained: swap });
      restored = true;
    };
    if (retained.selection === null) writeBlankJourneyUrl(() => restore(null));
    else commitProjectJourneySelection(window.location.href, retained.selection, window.history, restore);
    return restored;
  };

  // Currency proof for retained-slot-only edits (never draft or navigation):
  // the full live proof, or — only for an exactly held passive same-host
  // text whose credential is already gone — bare live host identity at the
  // current render. Only currently exposed retained text is editable, and a
  // callback from an earlier render is never the current render's editor.
  const ensureRetainedEditor = (retained: RetainedGoalState): JourneyActor | null => {
    if (actor === null || latestActor.current !== actor || !retainedExposed(retained, actor)) {
      return null;
    }
    if (journeyActorCurrent(actor, currentAuthRevision)) return actor;
    try {
      if (retained.passivelyHeld && retained.host === actor.host &&
          typeof window !== "undefined" && window.MastermindMissionHost === actor.host) {
        return actor;
      }
    } catch {
      return null;
    }
    return null;
  };

  const editRetainedGoal = (text: string): void => {
    const retained = stateRef.current.retained;
    if (retained === null || ensureRetainedEditor(retained) === null) return;
    // Local-only editing by the owning actor, or of an exactly held passive
    // same-host text; never a source call.
    const current = stateRef.current;
    apply({ ...current, retained: text === "" ? null : { ...retained, text } });
  };

  const discardRetainedGoal = (): void => {
    const retained = stateRef.current.retained;
    if (retained === null || ensureRetainedEditor(retained) === null) return;
    // Clears only the retained goal text; never the original selection or URL pointer.
    apply({ ...stateRef.current, retained: null });
  };

  // Stable for the parent's mount-once auth subscription. This IS the
  // notification, so it is not gated by the currency proof it reports.
  const invalidateAuth = useCallback((preserve: boolean) => {
    const current = stateRef.current;
    if (!preserve) {
      // Explicit sign-in/logout: private text and the retained ref are
      // cleared. The URL selection pointer is DATA the parent still owns.
      apply({ ...current, goal: null, retained: null });
      return;
    }
    // Passive expiry preserves ONLY the visible same-host owned text, for the
    // parent's existing passive-expiry hold. Never a new credential.
    if (current.goal === null || !goalVisible(current, latestActor.current)) {
      const retained = current.retained;
      // An off-view goal already parked by this actor is still unsent work.
      // Keep it in the SAME slot; native callers separately quarantine its
      // body until genuine same-principal/original-scope recovery qualifies.
      const owned = retained !== null && actorEquals(retained.actor, latestActor.current);
      apply({ ...current, goal: null, retained: owned ? { ...retained, passivelyHeld: true } : retained });
      return;
    }
    const goal = current.goal;
    apply({
      ...current,
      goal: null,
      retained: {
        text: goal.text,
        selection: current.selection,
        passivelyHeld: true,
        actor: goal.actor,
        host: goal.actor.host,
      },
    });
  }, [apply]);

  // Stable for the parent's mount-once unsaved-navigation hold.
  const hasUnsentDraft = useCallback(() => {
    const current = stateRef.current;
    if (goalVisible(current, latestActor.current)) return true;
    const retained = current.retained;
    return retained !== null && retainedExposed(retained, latestActor.current) && retained.text !== "";
  }, []);

  const visible = goalVisible(state, actor);
  const retained = state.retained;
  const retainedGoal: ProjectJourneyRetainedGoal | null =
    retained !== null && retainedExposed(retained, actor)
      ? { text: retained.text, selection: retained.selection, passivelyHeld: retained.passivelyHeld }
      : null;

  return {
    shown: state.shown,
    invalidLink: state.invalidLink,
    selection: state.selection,
    goal: visible && state.goal !== null ? state.goal.text : "",
    goalBelongsToSelection: visible,
    retainedGoal,
    isHostCurrent: isCurrent,
    hasUnsentDraft,
    currentGoalScope: () => ensureCurrent() ? projectGoalDraftScope(stateRef.current.selection) : null,
    open,
    hide,
    onSelection,
    onGoalChange,
    invalidateAuth,
    restoreLocation,
    returnToRetainedGoal,
    returnToNativeRetainedGoal,
    editRetainedGoal,
    discardRetainedGoal,
  };
}
