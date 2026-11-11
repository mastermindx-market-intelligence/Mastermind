import type {AuthState, RawClient} from "./host";
import {decodeNativeAuthorizationContinuation, type NativeAuthorizationContinuation} from "./native-authorization-continuation";
export interface NativeAuthorizationContinuationOwner {
  read(request: {signal: AbortSignal}): Promise<NativeAuthorizationContinuation>;
  continue(): Promise<void>;
}
export function incompleteAuthorization(state: AuthState): boolean {
  return state.status === "error" && state.reason === "AUTH_TRANSACTION_EXPIRED" && state.acquisition && !state.content;
}
const unavailable = (): NativeAuthorizationContinuation => ({schema: "mastermind.native_authorization_continuation.v1", state: "INELIGIBLE", resource: null, reason: "NOT_ELIGIBLE"});
/** Binds presentation to the same methods/owner/epoch; the native command rechecks its private witness. */
export function bindNativeAuthorizationContinuation(client: RawClient, hostEpoch: () => number): NativeAuthorizationContinuationOwner | undefined {
  const reader = client.readAuthorizationContinuation, command = client.continueAuthorization;
  const generation = client.invalidationGeneration, stateReader = client.getState;
  if (!reader || !command || !generation) return undefined;
  let qualified: (() => boolean) | null = null;
  let busy = false;
  return {
    async read({signal}) {
      qualified = null;
      const state = stateReader.call(client), epoch = hostEpoch(), source = generation.call(client);
      const current = () => {try {return !signal.aborted && !busy && hostEpoch() === epoch &&
        Number.isSafeInteger(source) && source >= 0 && client.invalidationGeneration === generation &&
        generation.call(client) === source && client.getState === stateReader &&
        client.readAuthorizationContinuation === reader && client.continueAuthorization === command &&
        (() => {const now = stateReader.call(client); return now.status === state.status && now.reason === state.reason &&
          now.acquisition === state.acquisition && now.content === state.content;})();} catch {return false;}};
      if (!current()) throw new Error("AUTHENTICATION_CHANGED");
      if (!incompleteAuthorization(state)) return unavailable();
      const raw = await reader.call(client, {signal});
      if (!current()) throw new Error("AUTHENTICATION_CHANGED");
      const value = decodeNativeAuthorizationContinuation(raw);
      if (!value) throw new Error("AUTH_CONTINUATION_RESPONSE_INVALID");
      if (value.state === "ELIGIBLE") qualified = current;
      return value;
    },
    async continue() {
      const current = qualified;
      qualified = null;
      if (!current || !current() || busy) throw new Error("AUTH_CONTINUATION_INELIGIBLE");
      busy = true;
      try {await command.call(client);} finally {busy = false;}
    },
  };
}
