import { useEffect, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { decodeByokRolesRead, type ByokRolesRead } from "./byok-roles-read";

const MAX_AGE_MS = 30_000;
const MAX_FUTURE_MS = 5_000;
type State = "LOADING" | "SOURCE_UNBOUND" | "UNAVAILABLE" | "OBSERVED";
interface Input { active: boolean; acquisition: boolean; authRevision: number }
interface Binding {
  host: MissionHost;
  read: NonNullable<MissionHost["readByokRoles"]>;
  generation: NonNullable<MissionHost["invalidationGeneration"]>;
  epoch: number;
  auth: NonNullable<MissionHost["auth"]>;
  getState: NonNullable<MissionHost["auth"]>["getState"];
}
interface Slot {
  binding: Binding;
  authRevision: number;
  refreshRevision: number;
  pending: boolean;
  body: ByokRolesRead | null;
}

function current(binding: Binding): boolean {
  try {
    const { host, read, generation, epoch, auth, getState } = binding;
    if (window.MastermindMissionHost !== host || host.readByokRoles !== read ||
        host.invalidationGeneration !== generation || host.auth !== auth ||
        auth.getState !== getState || generation.call(host) !== epoch) return false;
    const state = getState.call(auth);
    return state.status === "signed_in" && state.acquisition;
  } catch { return false; }
}

function fresh(body: ByokRolesRead): boolean {
  if (body.state !== "OBSERVED") return true;
  const age = Date.now() - body.source_observation!.observed_at_ms;
  return age >= -MAX_FUTURE_MS && age <= MAX_AGE_MS;
}

/** One view-triggered read through the existing host. Expiry never initiates I/O. */
export function useByokRoleObservation(input: Input): {
  state: State;
  body: ByokRolesRead | null;
  canRefresh: boolean;
  refresh: () => void;
} {
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [slot, setSlot] = useState<Slot | null>(null);
  const inputRef = useRef({ ...input, refreshRevision });
  inputRef.current = { ...input, refreshRevision };
  const host = window.MastermindMissionHost;
  const read = host?.readByokRoles;
  const generation = host?.invalidationGeneration;
  const auth = host?.auth;
  const getState = auth?.getState;
  let epoch: number | null = null;
  let authorized = false;
  try {
    const value = generation?.call(host);
    if (Number.isSafeInteger(value) && Number(value) >= 0) epoch = value!;
    const state = getState?.call(auth);
    authorized = state?.status === "signed_in" && state.acquisition;
  } catch { /* The existing owner is currently unavailable. */ }
  const readable = input.active && input.acquisition && authorized &&
    !!host && typeof read === "function" && typeof generation === "function" &&
    !!auth && !!getState && epoch !== null;

  useEffect(() => {
    if (!readable || !host || !read || !generation || !auth || !getState || epoch === null) {
      setSlot(null);
      return;
    }
    const binding: Binding = { host, read, generation, epoch, auth, getState };
    const owner = { binding, authRevision: input.authRevision, refreshRevision };
    const abort = new AbortController();
    let attached = true;
    let expiry: ReturnType<typeof setTimeout> | undefined;
    const sameView = () => attached && !abort.signal.aborted && inputRef.current.active &&
      inputRef.current.acquisition && inputRef.current.authRevision === owner.authRevision &&
      inputRef.current.refreshRevision === owner.refreshRevision;
    setSlot({ ...owner, pending: true, body: null });
    void Promise.resolve().then(() => {
      if (!sameView() || !current(binding)) throw new Error("BYOK_READ_CANCELLED");
      return read.call(host, { signal: abort.signal });
    }).then(raw => {
      if (!sameView()) return;
      const body = decodeByokRolesRead(raw);
      if (!current(binding) || !fresh(body)) throw new Error("BYOK_SOURCE_UNAVAILABLE");
      setSlot({ ...owner, pending: false, body });
      if (body.state === "OBSERVED") {
        // Preserve the producer's timestamp. This timer only removes old evidence.
        const delay = Math.max(1, body.source_observation!.observed_at_ms + MAX_AGE_MS + 1 - Date.now());
        expiry = setTimeout(() => {
          if (sameView()) setSlot({ ...owner, pending: false, body: null });
        }, delay);
      }
    }).catch(() => {
      if (sameView()) setSlot({ ...owner, pending: false, body: null });
    });
    return () => { attached = false; abort.abort(); if (expiry !== undefined) clearTimeout(expiry); };
  }, [readable, host, read, generation, epoch, auth, getState, input.authRevision, refreshRevision]);

  let state: State = "UNAVAILABLE";
  let body: ByokRolesRead | null = null;
  if (!input.active || (input.acquisition && authorized && (!host || !read || !generation))) {
    state = "SOURCE_UNBOUND";
  } else if (readable) {
    if (!slot || slot.authRevision !== input.authRevision || slot.refreshRevision !== refreshRevision ||
        slot.binding.host !== host || slot.binding.read !== read || slot.binding.generation !== generation ||
        slot.binding.epoch !== epoch || slot.binding.auth !== auth || slot.binding.getState !== getState) {
      state = "LOADING";
    } else if (current(slot.binding)) {
      state = slot.pending ? "LOADING" : "UNAVAILABLE";
      if (slot.body && fresh(slot.body)) { body = slot.body; state = body.state; }
    }
  }
  const canRefresh = readable && state !== "LOADING";
  return { state, body, canRefresh, refresh: () => {
    if (canRefresh && slot && current(slot.binding)) setRefreshRevision(value => value + 1);
  } };
}
