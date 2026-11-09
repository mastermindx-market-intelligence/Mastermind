import type {AuthState, RawClient} from "./host";
export interface NativePrimaryAccountOwner { signIn(): Promise<void>; }
export const primaryAccountEntry = (state: AuthState): boolean =>
  state.status !== "unconfigured" && state.status !== "signing_in" && !state.acquisition && !state.content;
/** Optional fixed action. Missing support never falls back to full Sign in. */
export function bindNativePrimaryAccount(client: RawClient, begin: () => void): NativePrimaryAccountOwner | undefined {
  const command = client.signInPrimary, state = client.getState, generation = client.invalidationGeneration;
  if (!command || !generation) return undefined;
  let busy = false, uncertain = false;
  return {async signIn() {
    if (busy || uncertain || client.signInPrimary !== command || client.getState !== state ||
        client.invalidationGeneration !== generation || !Number.isSafeInteger(generation.call(client)) ||
        !primaryAccountEntry(state.call(client))) throw Error("PRIMARY_AUTH_UNAVAILABLE");
    busy = true;
    try {begin(); await command.call(client);}
    catch (error) {uncertain = true; throw error;}
    finally {busy = false;}
  }};
}
