import type { MissionHost } from "../host";

/** Actual App/native owner observation. A capture is neither a read grant nor
 * a replacement for the backend's authorization. It only fences navigation. */
export interface ConversationListOwnerInput {
  readonly host: MissionHost | undefined;
  readonly authGeneration: number;
  readonly selectionSequence: number;
  readonly currentHost: () => MissionHost | undefined;
  readonly currentAuthGeneration: () => number;
  readonly currentSelectionSequence: () => number;
}

export interface ConversationListOwnerCapture {
  readonly input: ConversationListOwnerInput;
  readonly auth: NonNullable<MissionHost["auth"]>;
  readonly getState: NonNullable<MissionHost["auth"]>["getState"];
  readonly getGeneration: NonNullable<MissionHost["invalidationGeneration"]>;
  readonly hostGeneration: number;
}

export function captureConversationListOwner(input: ConversationListOwnerInput): ConversationListOwnerCapture | null {
  try {
    const { host } = input, auth = host?.auth;
    if (!host || !auth || typeof auth.getState !== "function" ||
        typeof host.invalidationGeneration !== "function" ||
        !Number.isSafeInteger(input.authGeneration) || input.authGeneration < 0 ||
        !Number.isSafeInteger(input.selectionSequence) || input.selectionSequence < 0) return null;
    const getState = auth.getState, getGeneration = host.invalidationGeneration;
    const generation = getGeneration.call(host);
    if (!Number.isSafeInteger(generation) || generation < 0) return null;
    const capture = Object.freeze({ input: Object.freeze({ ...input }),
      auth, getState, getGeneration, hostGeneration: generation });
    return conversationListOwnerCurrent(capture, false) ? capture : null;
  } catch { return null; }
}

/** Re-read real public auth/generation and exact receivers at gesture time.
 * Missing, replaced or throwing methods fail closed without exposing errors. */
export function conversationListOwnerCurrent(capture: ConversationListOwnerCapture | null,
  requireContent: boolean): boolean {
  if (!capture) return false;
  const { input, auth, getState, getGeneration, hostGeneration } = capture;
  const host = input.host;
  const sameOwner = () => Boolean(host && input.currentHost() === host && host.auth === auth &&
    auth.getState === getState && host.invalidationGeneration === getGeneration &&
    input.currentAuthGeneration() === input.authGeneration &&
    input.currentSelectionSequence() === input.selectionSequence);
  try {
    if (!host || !sameOwner()) return false;
    const state = getState.call(auth), generation = getGeneration.call(host);
    return sameOwner() && generation === hostGeneration && state.status === "signed_in" &&
      state.acquisition === true && (!requireContent || state.content === true);
  } catch { return false; }
}
