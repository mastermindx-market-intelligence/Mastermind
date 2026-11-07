import type { MissionHost } from "../host";

/** Caller-currentness only. No read, grant, owner issuance or source promotion.
 * The actual fixed Host method independently authorizes every acquisition. */
export function captureOfficeReadFrame(
  host: MissionHost | undefined,
  authRevision: number,
  currentAuthRevision: () => number,
  source: "readWork" | "readProjectJournal",
): Readonly<{ current(): boolean }> {
  const reader = host?.[source],
    auth = host?.auth,
    getState = auth?.getState;
  const generation = host?.invalidationGeneration;
  let epoch: number | null = null;
  try {
    const value = typeof generation === "function" ? generation.call(host) : null;
    if (Number.isSafeInteger(value) && Number(value) >= 0) epoch = value!;
  } catch {
    /* withhold */
  }
  return Object.freeze({
    current: () => {
      try {
        if (
          !host ||
          typeof reader !== "function" ||
          !auth ||
          typeof getState !== "function" ||
          typeof generation !== "function" ||
          epoch === null ||
          window.MastermindMissionHost !== host ||
          currentAuthRevision() !== authRevision ||
          host[source] !== reader ||
          host.auth !== auth ||
          auth.getState !== getState ||
          host.invalidationGeneration !== generation ||
          generation.call(host) !== epoch
        )
          return false;
        const state = getState.call(auth);
        return state.status === "signed_in" && state.acquisition === true;
      } catch {
        return false;
      }
    },
  });
}
