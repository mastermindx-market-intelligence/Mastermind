import { useCallback, useRef, useState } from "react";
import type { AuthState, MissionHost } from "../../host";
import type { OwnerContext } from "../../orchestration/operation-controller";
import {
  readFreshConversationLocation,
  writeFreshConversationLocation,
  type FreshConversationLocation,
} from "../fresh-conversation-location";
import {
  sameConversationOwner,
  type ConversationRequestSelection,
} from "./fresh-conversation-binding";

/** The mounted host surface this presentation reads; never a new authority. */
export type FreshConversationDraftHost = Pick<
  MissionHost,
  "auth" | "invalidationGeneration" | "freshConversation"
>;

export interface FreshConversationOriginalLookup {
  /** Detached, reader-validated lookup DATA; never a grant or dispatch. */
  readonly selection: ConversationRequestSelection;
  /** The Executive owner the lookup was read under; never derived credentials. */
  readonly owner: OwnerContext;
}

export interface FreshConversationRetainedDraft {
  readonly text: string;
  readonly workRef: string | null;
  readonly selection: ConversationRequestSelection | null;
  readonly passivelyHeld: boolean;
}

export interface FreshConversationDraftStateProps {
  /** The App's existing mounted host; live identity is re-proved per gesture. */
  host: FreshConversationDraftHost | null;
  /** The App auth epoch captured at render; drift refuses every mutation. */
  authRevision: number;
  /** Live epoch reader (the parent's revision ref); part of every proof. */
  currentAuthRevision: () => number;
  /** The parent's existing Executive owner getter; snapshotted and re-proved live. */
  getExecutiveOwner: () => OwnerContext | null;
}

export interface FreshConversationDraftStateApi {
  shown: boolean;
  invalidLink: boolean;
  /** The ephemeral chosen work while blank; the full lookup's work once written. */
  workRef: string | null;
  /** Exact authored text, exposed only while its authoring context renders. */
  message: string;
  /** Owner of the currently visible draft; null when no draft is exposed. */
  draftOwner: OwnerContext | null;
  /** URL lookup DATA bound to the owner that read it; never a grant. */
  originalLookup: FreshConversationOriginalLookup | null;
  retainedDraft: FreshConversationRetainedDraft | null;
  /** Presentation epoch; bumped by explicit new-presentation and foreign restores. */
  navigationEpoch: number;
  isHostCurrent: () => boolean;
  /** Stable local probe for the parent's existing unsaved-navigation hold. */
  hasUnsentDraft: () => boolean;
  open: (mode?: "resume" | "new") => boolean;
  hide: () => void;
  restoreLocation: () => void;
  onWorkRefChange: (value: string | null) => void;
  onMessageChange: (value: string) => void;
  onOriginalKeySelected: (value: ConversationRequestSelection) => void;
  /** Stable notification for the parent's existing central auth owner. */
  invalidateAuth: (preserve: boolean) => void;
  returnToRetainedDraft: () => boolean;
  editRetainedDraft: (text: string) => void;
  discardRetainedDraft: () => void;
}

/** One render-captured host/epoch/generation/owner quadruple plus the exact
 * method identities read. Any later drift makes owned text foreign: no
 * latest-props rewrite ever re-authorizes a callback. */
interface DraftActor {
  readonly host: FreshConversationDraftHost;
  readonly epoch: number;
  readonly generation: number;
  /** Detached copy; the input owner object is never retained or mutated. */
  readonly owner: OwnerContext;
  readonly authIdentity: unknown;
  readonly getStateIdentity: unknown;
  readonly transportIdentity: unknown;
  readonly requestIdentity: unknown;
  readonly getterIdentity: unknown;
}

interface OwnedMessage {
  readonly text: string;
  readonly actor: DraftActor;
  /** Original identity the text belongs to; null on the blank pane. */
  readonly selection: ConversationRequestSelection | null;
}

interface RetainedDraftState extends FreshConversationRetainedDraft {
  /** The actor and host instance that owned or preserved the text. */
  readonly actor: DraftActor;
  readonly host: FreshConversationDraftHost;
}

interface FreshDraftState {
  readonly shown: boolean;
  readonly invalidLink: boolean;
  /** Detached lookup DATA the URL carried; never evidence of a grant. */
  readonly selection: ConversationRequestSelection | null;
  /** Owner binding of `selection`; exposure requires a matching render owner. */
  readonly lookupOwner: OwnerContext | null;
  /** Ephemeral chosen work while blank; mirrored from the lookup once written. */
  readonly workRef: string | null;
  readonly message: OwnedMessage | null;
  readonly retained: RetainedDraftState | null;
  readonly navigationEpoch: number;
}

function ownerOf(value: OwnerContext): OwnerContext {
  // A detached copy with only the incumbent identity fields; no derived
  // credentials, tokens or capabilities ever leave the getter's object.
  return { principalScope: value.principalScope, generation: value.generation };
}

function selectionOf(value: ConversationRequestSelection): ConversationRequestSelection {
  return Object.freeze({ work_ref: value.work_ref, operation_key: value.operation_key });
}

function sameOriginal(
  left: ConversationRequestSelection | null,
  right: ConversationRequestSelection | null,
): boolean {
  if (left === null || right === null) return left === right;
  return left.work_ref === right.work_ref && left.operation_key === right.operation_key;
}

function actorEquals(left: DraftActor | null, right: DraftActor | null): boolean {
  return left !== null && right !== null &&
    left.host === right.host && left.epoch === right.epoch &&
    left.generation === right.generation && sameConversationOwner(left.owner, right.owner) &&
    left.authIdentity === right.authIdentity && left.getStateIdentity === right.getStateIdentity &&
    left.transportIdentity === right.transportIdentity && left.requestIdentity === right.requestIdentity &&
    left.getterIdentity === right.getterIdentity;
}

/** The draft is visible only while its authoring context is still the
 * rendering context and it still belongs to the shown original identity. */
function messageVisible(state: FreshDraftState, actor: DraftActor | null): boolean {
  const message = state.message;
  if (message === null || !actorEquals(message.actor, actor)) return false;
  return sameOriginal(message.selection, state.selection);
}

function retainedExposed(retained: RetainedDraftState, actor: DraftActor | null): boolean {
  if (actor === null) return false;
  if (actorEquals(retained.actor, actor)) return true;
  // Passive recovery view: exactly the last-owned same-host text, and never
  // for a different known principal than the one that authored it.
  return retained.passivelyHeld && retained.host === actor.host &&
    retained.actor.owner.principalScope === actor.owner.principalScope;
}

function readFreshLocation(): FreshConversationLocation {
  try {
    return readFreshConversationLocation(window.location.href);
  } catch {
    return { valid: false, open: false, selection: null };
  }
}

function captureActor(
  host: FreshConversationDraftHost | null,
  authRevision: number,
  getExecutiveOwner: () => OwnerContext | null,
): DraftActor | null {
  if (host === null || !Number.isSafeInteger(authRevision)) return null;
  if (typeof getExecutiveOwner !== "function") return null;
  let generation: number | undefined;
  try {
    generation = host.invalidationGeneration?.();
  } catch {
    return null;
  }
  if (generation === undefined || !Number.isSafeInteger(generation) || generation < 0) return null;
  const auth = host.auth;
  if (auth === undefined || auth === null || typeof auth.getState !== "function") return null;
  let transport: unknown;
  let requestIdentity: unknown;
  try {
    const present = host.freshConversation;
    if (present !== undefined && present !== null) {
      transport = present;
      const candidate = (transport as { request?: unknown }).request;
      if (typeof candidate === "function") requestIdentity = candidate;
    } else {
      transport = undefined;
    }
  } catch {
    return null;
  }
  let owner: OwnerContext;
  try {
    const live = getExecutiveOwner();
    if (live === null || typeof live.principalScope !== "string" || live.principalScope === "" ||
        typeof live.generation !== "string" || live.generation === "") {
      return null;
    }
    owner = ownerOf(live);
  } catch {
    return null;
  }
  return {
    host,
    epoch: authRevision,
    generation,
    owner,
    authIdentity: auth,
    getStateIdentity: auth.getState,
    transportIdentity: transport,
    requestIdentity,
    getterIdentity: getExecutiveOwner,
  };
}

/** The exact currency proof of every mutation handler and of isHostCurrent:
 * live global host identity, live epoch, live source generation, the exact
 * auth/transport/request/getter method identities captured at render, a real
 * signed-in state and the exact current Executive principalScope/generation.
 * Any throw refuses without mutation and without surfacing raw details. */
function freshActorCurrent(
  actor: DraftActor | null,
  currentAuthRevision: () => number,
  getExecutiveOwner: () => OwnerContext | null,
): boolean {
  if (actor === null || typeof window === "undefined") return false;
  try {
    if (window.MastermindMissionHost !== actor.host) return false;
    if (currentAuthRevision() !== actor.epoch) return false;
    if (actor.host.invalidationGeneration?.() !== actor.generation) return false;
    const auth = actor.host.auth;
    if (auth === undefined || auth === null) return false;
    if (auth !== actor.authIdentity || auth.getState !== actor.getStateIdentity) return false;
    const transport = actor.host.freshConversation === undefined ? undefined : actor.host.freshConversation;
    if (transport !== actor.transportIdentity) return false;
    if (transport !== undefined &&
        (transport as { request?: unknown }).request !== actor.requestIdentity) {
      return false;
    }
    if (getExecutiveOwner !== actor.getterIdentity) return false;
    const state: AuthState = auth.getState();
    if (state.status !== "signed_in") return false;
    if (!sameConversationOwner(getExecutiveOwner(), actor.owner)) return false;
    return true;
  } catch {
    return false;
  }
}

function initialFreshState(actor: DraftActor | null): FreshDraftState {
  const read = readFreshLocation();
  if (!read.valid) {
    return {
      shown: false, invalidLink: true, selection: null,
      lookupOwner: null,
      workRef: null, message: null, retained: null, navigationEpoch: 0,
    };
  }
  if (!read.open) {
    return {
      shown: false, invalidLink: false, selection: null,
      lookupOwner: null,
      workRef: null, message: null, retained: null, navigationEpoch: 0,
    };
  }
  return {
    shown: true, invalidLink: false, selection: read.selection,
    // The URL lookup is DATA bound to the owner that first rendered it; a
    // different principal never sees it until that owner restores it again.
    lookupOwner: actor === null ? null : actor.owner,
    workRef: read.selection === null ? null : read.selection.work_ref,
    message: null, retained: null, navigationEpoch: 0,
  };
}

/** Commit the safe presentation URL through the existing location adapter:
 * origin and path preserved (native custom schemes included), prior search
 * (including any private or credential-bearing part) and hash never carried
 * over, exactly the adapter's three safe keys written. The synchronous
 * replaceState runs BEFORE any state adoption; a rejected write suppresses
 * the update and propagates the adapter's own fixed error, never raw URL
 * or host details. */
function writeFreshUrl(original: ConversationRequestSelection | null): void {
  try {
    const href = writeFreshConversationLocation(window.location.href, original, true);
    window.history.replaceState(null, "", href);
  } catch {
    // The fixed adapter error only: raw URL, host or transport details of a
    // refused write are never surfaced, and no state was adopted above.
    throw Error("FRESH_CONVERSATION_LOCATION_INVALID");
  }
}

/** Park the currently visible owned text into the single retained slot;
 * foreign or stale text is dropped without transplant and any existing
 * retained draft is kept. */
function parkVisibleDraft(
  state: FreshDraftState,
  actor: DraftActor,
): FreshDraftState {
  const message = state.message;
  if (message === null || !messageVisible(state, actor)) {
    return { ...state, message: null };
  }
  return {
    ...state,
    message: null,
    retained: {
      text: message.text,
      workRef: message.selection === null ? state.workRef : message.selection.work_ref,
      selection: message.selection,
      passivelyHeld: false,
      actor: message.actor,
      host: message.actor.host,
    },
  };
}

/**
 * useFreshConversationDraftState — App-owned presentation state of the one
 * New-conversation first-message pane.
 *
 * OWNERSHIP. Only local React state/refs and the safe URL projection through
 * the existing location adapter. No request, port, preview, id mint,
 * pending-pointer read/write, session/config/draft registry, permission
 * grant, DOM focus, auth subscription or lifecycle handler lives here. The
 * Journey state, the pending-pointer store and the operation controller are
 * never read; the parent prefers their unresolved state before calling
 * open. Lookup DATA read from the URL is presentation only: it never grants
 * create/send, and the ephemeral work choice alone never grants anything.
 *
 * CURRENCY. Every draft/navigation mutation closes over the render-captured
 * host, epoch, source generation, Executive owner snapshot and the exact
 * method identities (auth group and getState; freshConversation group and
 * request when present; the owner getter) and re-proves all of them live,
 * plus signed-in state and the exact current Executive principalScope and
 * generation, before acting. Callbacks from an earlier render stay refused
 * after the global host, an identity, the epoch, the generation or the owner
 * moves; only hasUnsentDraft and invalidateAuth are stable (for the parent's
 * mount-once navigation hold and auth subscription) and they only read the
 * hook's own local state. Workspace acquisition/content is never required
 * for writing own draft text or adopting lookup DATA.
 *
 * RETENTION. Cross-actor (host/epoch/generation/owner) text is never exposed
 * as current. A draft refused by a different original identity, a work
 * change away from an owned draft, an explicit new presentation, and the
 * current owned text at a passive auth expiry park in the single retained
 * slot for the parent's existing return/discard and passive-expiry policies.
 * Return and the recovery view are same-host and same-principal only, never
 * crossidentity or new-host, and stay explicit gestures. Retained DATA is
 * presentation only, never a credential, grant or source effect.
 */
export function useFreshConversationDraftState(
  props: FreshConversationDraftStateProps,
): FreshConversationDraftStateApi {
  const { host, authRevision, currentAuthRevision, getExecutiveOwner } = props;
  const actor = captureActor(host, authRevision, getExecutiveOwner);
  const isCurrent = () => freshActorCurrent(actor, currentAuthRevision, getExecutiveOwner);
  const ensureCurrent = (): DraftActor | null =>
    actor !== null && freshActorCurrent(actor, currentAuthRevision, getExecutiveOwner)
      ? actor
      : null;

  const [state, setState] = useState(() => initialFreshState(actor));
  const stateRef = useRef(state);
  const apply = useCallback((next: FreshDraftState) => {
    stateRef.current = next;
    setState(next);
  }, []);
  // Read-side currency for the stable probes and the auth notification only.
  // No mutation handler consults it, so late callbacks can never be
  // re-authorized by a newer render.
  const latestActor = useRef<DraftActor | null>(actor);
  latestActor.current = actor;

  const writeCurrentUrl = (selection: ConversationRequestSelection | null): void => {
    writeFreshUrl(selection);
    if (ensureCurrent() === null) throw Error("FRESH_CONVERSATION_CONTEXT_CHANGED");
  };

  // A passive signed-out view may expose only already-held text. This
  // frame is never returned as draftOwner and cannot authorize a command.
  let recoveryFrame: DraftActor | null = actor;
  if (recoveryFrame === null && state.retained?.passivelyHeld && host === state.retained.host) {
    try {
      if (host?.auth?.getState().status === "signed_out" && getExecutiveOwner() === null) {
        recoveryFrame = captureActor(host, authRevision, () => state.retained!.actor.owner);
      }
    } catch { recoveryFrame = null; }
  }
  const latestRecoveryFrame = useRef<DraftActor | null>(recoveryFrame);
  latestRecoveryFrame.current = recoveryFrame;
  const signedOutFrameCurrent = (frame: DraftActor): boolean => {
    try {
      return window.MastermindMissionHost === frame.host &&
        currentAuthRevision() === frame.epoch && frame.host.invalidationGeneration?.() === frame.generation &&
        frame.host.auth === frame.authIdentity && frame.host.auth?.getState === frame.getStateIdentity &&
        frame.host.freshConversation === frame.transportIdentity &&
        frame.host.freshConversation?.request === frame.requestIdentity &&
        frame.host.auth?.getState().status === "signed_out" &&
        (getExecutiveOwner() === null || getExecutiveOwner()?.principalScope === frame.owner.principalScope);
    } catch { return false; }
  };

  const open = (mode: "resume" | "new" = "resume"): boolean => {
    const live = ensureCurrent();
    if (live === null) return false;
    const current = stateRef.current;
    if (mode === "new") {
      // Explicit new presentation: park any unsent owned text, write the
      // blank safe URL and advance the presentation epoch. Runtime identity
      // (host/epoch/generation/owner) is untouched by the epoch bump.
      const parked = parkVisibleDraft(current, live);
      writeCurrentUrl(null);
      apply({
        ...parked,
        shown: true,
        invalidLink: false,
        selection: null,
        lookupOwner: live.owner,
        workRef: null,
        message: null,
        navigationEpoch: current.navigationEpoch + 1,
      });
      return true;
    }
    const selection = current.selection;
    if (selection !== null && current.lookupOwner !== null &&
        current.lookupOwner.principalScope === live.owner.principalScope) {
      // Resume the known original lookup; never reset it to a fresh blank.
      writeCurrentUrl(selection);
      apply({
        ...current,
        shown: true,
        invalidLink: false,
        lookupOwner: live.owner,
      });
      return true;
    }
    const retained = current.retained;
    // With no current lookup, an explicitly parked same-actor draft resumes
    // its own presentation. Passively held text never becomes current by
    // itself here; returnToRetainedDraft owns that explicit decision.
    if (retained !== null && !retained.passivelyHeld && actorEquals(retained.actor, live) &&
        !messageVisible(current, live)) {
      writeCurrentUrl(retained.selection);
      apply({
        ...current,
        shown: true,
        invalidLink: false,
        selection: retained.selection,
        lookupOwner: live.owner,
        workRef: retained.selection === null ? retained.workRef : retained.selection.work_ref,
        message: { text: retained.text, actor: live, selection: retained.selection },
        retained: null,
      });
      return true;
    }
    writeCurrentUrl(null);
    apply({
      ...current,
      shown: true,
      invalidLink: false,
      selection: null,
      lookupOwner: live.owner,
    });
    return true;
  };

  const hide = (): void => {
    if (ensureCurrent() === null) return;
    const current = stateRef.current;
    // Local pane visibility only: the safe URL ids stay for reopen, and an
    // off-view owned draft stays held. Nothing is cancelled or cleared.
    if (current.shown || current.invalidLink) {
      apply({ ...current, shown: false, invalidLink: false });
    }
  };

  const onMessageChange = (text: string): void => {
    const live = ensureCurrent();
    if (live === null) return;
    const current = stateRef.current;
    // Text mutation happens only while the pane is shown, under the exact
    // current actor, and the exact authored string (whitespace, non-BMP
    // included) is kept verbatim: never trimmed, truncated or translated.
    if (!current.shown) return;
    apply({
      ...current,
      message: text === ""
        ? null
        : { text, actor: live, selection: current.selection },
    });
  };

  const onWorkRefChange = (value: string | null): void => {
    const live = ensureCurrent();
    if (live === null) return;
    const current = stateRef.current;
    const next = value ?? null;
    if (next === (current.workRef ?? null)) return;
    // Changing the chosen work away from an original-bound or owned draft
    // parks the text without transplant and writes the blank safe URL
    // synchronously BEFORE the new choice is adopted.
    const parked = parkVisibleDraft(current, live);
    writeCurrentUrl(null);
    apply({
      ...parked,
      invalidLink: false,
      selection: null,
      lookupOwner: live.owner,
      workRef: next,
      message: null,
    });
  };

  const onOriginalKeySelected = (value: ConversationRequestSelection): void => {
    const live = ensureCurrent();
    if (live === null) return;
    // A detached validated copy: the caller's object is never retained or
    // mutated, and the lookup stays DATA — never a grant or dispatch.
    const next = selectionOf(value);
    // Safe URL synchronously BEFORE any adoption; a rejected write suppresses
    // the update and propagates the adapter's fixed error.
    writeCurrentUrl(next);
    const current = stateRef.current;
    if (current.selection !== null && sameOriginal(current.selection, next)) {
      // Same original: no reset, the bound draft stays exactly as authored.
      apply({
        ...current,
        invalidLink: false,
        selection: next,
        lookupOwner: live.owner,
        workRef: next.work_ref,
      });
      return;
    }
    if (current.selection === null && next.work_ref === (current.workRef ?? null)) {
      // The hook's own blank -> minted gesture for the same chosen work: the
      // exact draft text is preserved and the presentation epoch never moves.
      const message = current.message;
      const preserved = message !== null && messageVisible(current, live) && message.selection === null
        ? { ...message, selection: next }
        : message;
      apply({
        ...current,
        invalidLink: false,
        selection: next,
        lookupOwner: live.owner,
        workRef: next.work_ref,
        message: preserved,
      });
      return;
    }
    // Any other original (for example a recovered pending key): the owned
    // text parks without transplant and no presentation epoch is self-induced.
    const parked = parkVisibleDraft(current, live);
    apply({
      ...parked,
      invalidLink: false,
      selection: next,
      lookupOwner: live.owner,
      workRef: next.work_ref,
      message: null,
    });
  };

  const restoreLocation = (): void => {
    const live = ensureCurrent();
    if (live === null) return;
    const read = readFreshLocation();
    const current = stateRef.current;
    if (!read.valid || !read.open) {
      // The URL no longer carries a usable original: the owned text parks for
      // the parent's existing hold policies and the presentation moves on.
      const parked = parkVisibleDraft(current, live);
      apply({
        ...parked,
        shown: false,
        invalidLink: !read.valid,
        selection: null,
        lookupOwner: null,
        workRef: null,
        message: null,
        navigationEpoch: current.navigationEpoch + 1,
      });
      return;
    }
    const next = read.selection;
    // Same original restore (including blank -> blank): no reset, no epoch
    // bump, and the bound draft stays exactly as authored.
    if (sameOriginal(current.selection, next)) {
      // Same original restore: no reset and no epoch bump; the draft stays.
      apply({
        ...current,
        shown: true,
        invalidLink: false,
        lookupOwner: live.owner,
      });
      return;
    }
    // A changed external original increments the presentation epoch so the
    // App can recreate its existing binding/discovery; owned text parks
    // without transplant and no request or mint ever happens here.
    const parked = parkVisibleDraft(current, live);
    apply({
      ...parked,
      shown: true,
      invalidLink: false,
      selection: next,
      lookupOwner: live.owner,
      workRef: next === null ? null : next.work_ref,
      message: null,
      navigationEpoch: current.navigationEpoch + 1,
    });
  };

  const returnToRetainedDraft = (): boolean => {
    const live = ensureCurrent();
    if (live === null) return false;
    const current = stateRef.current;
    const retained = current.retained;
    if (retained === null) return false;
    // Explicit gesture only, on the same host instance and the same
    // principal: an owned passive draft may rebind after same-principal
    // reauthentication (a newer generation of the same scope), never a
    // crossidentity or new-host draft.
    if (retained.host !== live.host) return false;
    if (retained.actor.owner.principalScope !== live.owner.principalScope) return false;
    const swapVisible = messageVisible(current, live) && current.message !== null &&
      current.message.text !== retained.text;
    const swap: RetainedDraftState | null = swapVisible && current.message !== null
      ? {
          text: current.message.text,
          workRef: current.message.selection === null
            ? current.workRef
            : current.message.selection.work_ref,
          selection: current.message.selection,
          passivelyHeld: false,
          actor: current.message.actor,
          host: current.message.actor.host,
        }
      : null;
    writeCurrentUrl(retained.selection);
    apply({
      ...current,
      shown: true,
      invalidLink: false,
      selection: retained.selection,
      lookupOwner: live.owner,
      workRef: retained.selection === null ? retained.workRef : retained.selection.work_ref,
      message: { text: retained.text, actor: live, selection: retained.selection },
      retained: swap,
    });
    return true;
  };

  // Currency proof for retained-slot-only edits (never draft or navigation):
  // the full live proof, or — only for an exactly held passive same-host text
  // whose credential is already gone — bare live host identity at the current
  // render. Only currently exposed retained text is editable, and a callback
  // from an earlier render is never the current render's editor.
  const ensureRetainedEditor = (retained: RetainedDraftState): DraftActor | null => {
    const frame = actor ?? recoveryFrame;
    if (frame === null || latestRecoveryFrame.current !== frame || !retainedExposed(retained, frame)) {
      return null;
    }
    if (actor !== null && freshActorCurrent(actor, currentAuthRevision, getExecutiveOwner)) return actor;
    try {
      if (retained.passivelyHeld && retained.host === frame.host && signedOutFrameCurrent(frame)) {
        return frame;
      }
    } catch {
      return null;
    }
    return null;
  };

  const editRetainedDraft = (text: string): void => {
    const retained = stateRef.current.retained;
    if (retained === null || ensureRetainedEditor(retained) === null) return;
    // Local-only editing by the owning actor, or of an exactly held passive
    // same-host text; never a source call and never re-authored text.
    apply({ ...stateRef.current, retained: text === "" ? null : { ...retained, text } });
  };

  const discardRetainedDraft = (): void => {
    const retained = stateRef.current.retained;
    if (retained === null || ensureRetainedEditor(retained) === null) return;
    // Clears only the retained draft text; never the original lookup or URL pointer.
    apply({ ...stateRef.current, retained: null });
  };

  // Stable for the parent's mount-once auth subscription. This IS the
  // notification, so it is not gated by the currency proof it reports.
  const invalidateAuth = useCallback((preserve: boolean) => {
    const current = stateRef.current;
    if (!preserve) {
      // Explicit sign-in/logout or crossidentity change: private current and
      // retained text and the ephemeral chosen work are cleared. The URL
      // lookup DATA is presentation the parent still owns and stays.
      apply({ ...current, message: null, retained: null, workRef: null, selection: null, lookupOwner: null });
      return;
    }
    // Passive expiry preserves ONLY the visible same-host owned text, for the
    // parent's existing passive-expiry hold. Never a new credential.
    const message = current.message;
    let samePassiveOwner = false;
    try {
      const known = getExecutiveOwner();
      samePassiveOwner = message !== null && window.MastermindMissionHost === message.actor.host &&
        (known === null || known.principalScope === message.actor.owner.principalScope);
    } catch { samePassiveOwner = false; }
    if (message === null || !samePassiveOwner || !sameOriginal(message.selection, current.selection)) {
      apply({ ...current, message: null });
      return;
    }
    apply({
      ...current,
      message: null,
      retained: {
        text: message.text,
        workRef: message.selection === null ? current.workRef : message.selection.work_ref,
        selection: message.selection,
        passivelyHeld: true,
        actor: message.actor,
        host: message.actor.host,
      },
    });
  }, [apply]);

  // Stable for the parent's mount-once unsaved-navigation hold.
  const hasUnsentDraft = useCallback(() => {
    const current = stateRef.current;
    if (messageVisible(current, latestActor.current) &&
        freshActorCurrent(latestActor.current, currentAuthRevision, getExecutiveOwner)) return true;
    const retained = current.retained;
    const frame = latestRecoveryFrame.current;
    return retained !== null && frame !== null && retainedExposed(retained, frame) &&
      (freshActorCurrent(frame, currentAuthRevision, getExecutiveOwner) ||
        (retained.passivelyHeld && signedOutFrameCurrent(frame))) && retained.text !== "";
  }, []);

  const visible = messageVisible(state, actor) && isCurrent();
  const retained = state.retained;
  const retainedDraft: FreshConversationRetainedDraft | null =
    retained !== null && recoveryFrame !== null && retainedExposed(retained, recoveryFrame) &&
      (freshActorCurrent(recoveryFrame, currentAuthRevision, getExecutiveOwner) ||
        (retained.passivelyHeld && signedOutFrameCurrent(recoveryFrame)))
      ? {
          text: retained.text,
          workRef: retained.workRef,
          selection: retained.selection === null ? null : selectionOf(retained.selection),
          passivelyHeld: retained.passivelyHeld,
        }
      : null;
  const lookup = state.selection !== null && actor !== null &&
      state.lookupOwner !== null && sameConversationOwner(state.lookupOwner, actor.owner)
    ? { selection: selectionOf(state.selection), owner: ownerOf(actor.owner) }
    : null;

  return {
    shown: state.shown,
    invalidLink: state.invalidLink,
    workRef: state.workRef ?? state.selection?.work_ref ?? null,
    message: visible && state.message !== null ? state.message.text : "",
    draftOwner: visible && state.message !== null ? ownerOf(state.message.actor.owner) : null,
    originalLookup: lookup,
    retainedDraft,
    navigationEpoch: state.navigationEpoch,
    isHostCurrent: isCurrent,
    hasUnsentDraft,
    open,
    hide,
    restoreLocation,
    onWorkRefChange,
    onMessageChange,
    onOriginalKeySelected,
    invalidateAuth,
    returnToRetainedDraft,
    editRetainedDraft,
    discardRetainedDraft,
  };
}
