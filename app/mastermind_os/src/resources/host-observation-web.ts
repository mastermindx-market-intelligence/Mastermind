/** The existing Web Acquisition read closure supplies tokens/currentness. */
import { ORIGIN } from "../public-config";
import { hostObservationPublicSelection, type HostObservationRequest, type HostObservationRawMethods } from "./host-observation-host";
type Read = (resource: "acquisition", url: string, signal: AbortSignal,
  options: { cap: number; typedUnavailableSchema: string }) => Promise<unknown>;
export function hostObservationWebMethods(read: Read): HostObservationRawMethods {
  return { readHostObservation(request: HostObservationRequest) {
    const selection = hostObservationPublicSelection(request);
    if (!selection) return Promise.reject(Error("HOST_OBSERVATION_REQUEST_INVALID"));
    return read("acquisition", `${ORIGIN}/workspace/resources/host-observation/current?${new URLSearchParams({ ...selection })}`,
      request.signal, { cap: 16384, typedUnavailableSchema: "mastermind.workspace_host_observation_result.v1" });
  } };
}
