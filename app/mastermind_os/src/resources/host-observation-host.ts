/** Fixed selected-work port. Method presence/login is never source authority. */
import type { AuthState } from "../host";
import { decodeHostObservationRead, validHostObservationSelection, type HostObservationSelection, type HostObservationRead } from "./recorded-host-observation";
export interface HostObservationRequest { selection: HostObservationSelection; signal: AbortSignal }
export interface HostObservationRawMethods { readHostObservation(request: HostObservationRequest): Promise<unknown> }
export interface HostObservationHostMethods { readHostObservation(request: HostObservationRequest): Promise<HostObservationRead> }
export function hostObservationPublicSelection(request: unknown): HostObservationSelection | null {
  try {
    if (!request || typeof request !== "object" || Array.isArray(request) || ![Object.prototype, null].includes(Object.getPrototypeOf(request))) return null;
    const d = Object.getOwnPropertyDescriptors(request);
    if (Reflect.ownKeys(d).length !== 2 || ["selection", "signal"].some(k => !Object.hasOwn(d, k) || !d[k].enumerable || !Object.hasOwn(d[k], "value")) || !(d.signal.value instanceof AbortSignal)) return null;
    const s = d.selection.value;
    if (!s || typeof s !== "object" || Array.isArray(s) || ![Object.prototype, null].includes(Object.getPrototypeOf(s))) return null;
    const v = Object.getOwnPropertyDescriptors(s), keys = ["work_ref", "root_job_id", "job_id", "attempt_id"];
    if (Reflect.ownKeys(v).length !== 4 || keys.some(k => !Object.hasOwn(v, k) || !v[k].enumerable || !Object.hasOwn(v[k], "value"))) return null;
    const selection = Object.fromEntries(keys.map(k => [k, v[k].value]));
    return validHostObservationSelection(selection) ? selection : null;
  } catch { return null; }
}
type Client = Partial<HostObservationRawMethods> & { getState(): AuthState; invalidationGeneration?(): number };
export function hostObservationHostMethods(client: Client, hostEpoch: () => number): Partial<HostObservationHostMethods> {
  const read = client.readHostObservation, generation = client.invalidationGeneration, getState = client.getState;
  if (typeof read !== "function" || typeof generation !== "function") return {};
  return { async readHostObservation(request) {
    const selection = hostObservationPublicSelection(request);
    if (!selection) throw Error("HOST_OBSERVATION_REQUEST_INVALID");
    const epoch = hostEpoch(), ticket = generation.call(client), signal = request.signal;
    const qualified = () => {
      try {
        const auth = getState.call(client);
        return !signal.aborted && Number.isSafeInteger(ticket) && ticket >= 0 && epoch === hostEpoch() && generation.call(client) === ticket && client.invalidationGeneration === generation && client.getState === getState && client.readHostObservation === read && auth.status === "signed_in" && auth.acquisition;
      } catch { return false; }
    };
    if (!qualified()) throw Error("HOST_OBSERVATION_UNAUTHORIZED");
    const raw = await read.call(client, { selection, signal });
    if (!qualified()) throw Error("HOST_OBSERVATION_AUTH_CHANGED");
    return decodeHostObservationRead(raw, selection);
  } };
}
