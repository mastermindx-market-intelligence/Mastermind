import { expect, it, vi } from "vitest";
import fixture from "./fixtures/recorded-host-observation-owner.json";
import { hostObservationHostMethods } from "./host-observation-host";
import type { AuthState } from "../host";
function setup() {
  let generation = 1, epoch = 1;
  let state = { status: "signed_in", acquisition: true } as AuthState;
  const read = vi.fn(async () => fixture);
  const client = { readHostObservation: read, getState: () => state, invalidationGeneration: () => generation };
  return { client, read, port: hostObservationHostMethods(client, () => epoch), rotate: () => generation++, changeEpoch: () => epoch++, depart: () => { state = { status: "signed_out" } as AuthState; } };
}
it("requires exact selected tuple and makes one fixed qualified read", async () => {
  const s = setup();
  const result = await s.port.readHostObservation!({ selection: fixture.selection, signal: new AbortController().signal });
  expect(result.state).toBe("AVAILABLE"); expect(s.read).toHaveBeenCalledTimes(1);
  await expect(s.port.readHostObservation!({ selection: { ...fixture.selection, host_ref: "supplied" }, signal: new AbortController().signal } as any)).rejects.toThrow("REQUEST_INVALID");
  expect(s.read).toHaveBeenCalledTimes(1);
});
it.each(["rotate", "changeEpoch", "depart", "reader", "abort"])("withholds late result after %s", async fault => {
  const s = setup(), abort = new AbortController();
  s.read.mockImplementationOnce(async () => {
    if (fault === "reader") s.client.readHostObservation = vi.fn(async () => fixture);
    else if (fault === "abort") abort.abort();
    else s[fault as "rotate" | "changeEpoch" | "depart"]();
    return fixture;
  });
  await expect(s.port.readHostObservation!({ selection: fixture.selection, signal: abort.signal })).rejects.toThrow("AUTH_CHANGED");
  expect(s.read).toHaveBeenCalledTimes(1);
});
it("has no port without actual source-generation owner", () => {
  expect(hostObservationHostMethods({ getState: () => ({ status: "signed_out" }) as AuthState }, () => 0)).toEqual({});
});
