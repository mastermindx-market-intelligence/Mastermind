/** A current read of supplied Workspace grants; never mutation authority. */
import type { AuthState } from "../host";
import {
  decodeCurrentProjectAccess,
  validProjectAccessSelection,
  type ProjectAccessCurrentRead,
  type ProjectAccessSelection,
} from "./project-access-current";
export interface ProjectAccessRequest {
  selection: ProjectAccessSelection;
  signal: AbortSignal;
}
export interface ProjectAccessRawMethods {
  readProjectAccess(request: ProjectAccessRequest): Promise<unknown>;
}
export interface ProjectAccessHostMethods {
  readProjectAccess(
    request: ProjectAccessRequest,
  ): Promise<ProjectAccessCurrentRead>;
}
export function projectAccessPublicSelection(
  input: unknown,
): ProjectAccessSelection | null {
  try {
    if (
      typeof input !== "object" ||
      input === null ||
      Array.isArray(input) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(input))
    )
      return null;
    const fields = Object.getOwnPropertyDescriptors(input);
    if (
      Reflect.ownKeys(fields).length !== 2 ||
      !["selection", "signal"].every(
        (key) =>
          Object.hasOwn(fields, key) &&
          fields[key].enumerable &&
          Object.hasOwn(fields[key], "value"),
      )
    )
      return null;
    const selection = fields.selection.value;
    if (
      !validProjectAccessSelection(selection) ||
      !(fields.signal.value instanceof AbortSignal)
    )
      return null;
    return { work_ref: selection.work_ref };
  } catch {
    return null;
  }
}
type Client = Partial<ProjectAccessRawMethods> & {
  getState(): AuthState;
  invalidationGeneration?(): number;
};
export function projectAccessHostMethods(
  client: Client,
  hostEpoch: () => number,
): Partial<ProjectAccessHostMethods> {
  const read = client.readProjectAccess,
    getState = client.getState,
    generation = client.invalidationGeneration;
  if (typeof read !== "function" || typeof generation !== "function") return {};
  return {
    async readProjectAccess(request) {
      const selection = projectAccessPublicSelection(request);
      if (!selection) throw Error("PROJECT_ACCESS_REQUEST_INVALID");
      const epoch = hostEpoch(),
        ticket = generation.call(client),
        signal = request.signal;
      const qualified = () => {
        try {
          const auth = getState.call(client);
          return (
            !signal.aborted &&
            epoch === hostEpoch() &&
            client.getState === getState &&
            client.invalidationGeneration === generation &&
            client.readProjectAccess === read &&
            ticket === generation.call(client) &&
            Number.isSafeInteger(ticket) &&
            ticket >= 0 &&
            auth.status === "signed_in" &&
            auth.acquisition
          );
        } catch {
          return false;
        }
      };
      if (!qualified()) throw Error("PROJECT_ACCESS_UNAUTHORIZED");
      const raw = await read.call(client, { selection, signal });
      if (!qualified()) throw Error("PROJECT_ACCESS_AUTH_CHANGED");
      const body = decodeCurrentProjectAccess(raw, selection);
      if (!body) throw Error("PROJECT_ACCESS_RESPONSE_INVALID");
      return body;
    },
  };
}
