import { expect, it, vi } from "vitest";
import { ORIGIN } from "../public-config";
import { hostObservationWebMethods } from "./host-observation-web";
import fixture from "./fixtures/recorded-host-observation-owner.json";
it("uses only the fixed Acquisition GET closure, selected work and 16KiB cap", async () => {
  const read = vi.fn(async () => fixture), port = hostObservationWebMethods(read), signal = new AbortController().signal;
  expect(await port.readHostObservation({ selection: fixture.selection, signal })).toBe(fixture);
  const [resource, address, actualSignal, options] = read.mock.calls[0] as unknown as [string, string, AbortSignal, object];
  const url = new URL(address);
  expect(resource).toBe("acquisition"); expect(url.origin).toBe(ORIGIN); expect(url.pathname).toBe("/workspace/resources/host-observation/current");
  expect(Object.fromEntries(url.searchParams)).toEqual(fixture.selection); expect(actualSignal).toBe(signal);
  expect(options).toEqual({ cap: 16384, typedUnavailableSchema: "mastermind.workspace_host_observation_result.v1" });
});
it("does not forward caller host/clock/path/binding selectors", async () => {
  const read = vi.fn(async () => fixture), port = hostObservationWebMethods(read);
  for (const field of ["host_ref", "clock", "path", "snapshot"]) {
    await expect(port.readHostObservation({ selection: { ...fixture.selection, [field]: "supplied" }, signal: new AbortController().signal } as any)).rejects.toThrow("REQUEST_INVALID");
  }
  expect(read).not.toHaveBeenCalled();
});
