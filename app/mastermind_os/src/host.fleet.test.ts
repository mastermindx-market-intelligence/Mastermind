import { describe, expect, it } from "vitest";
import { bindMissionHost, createNativeClient, type MissionHost } from "./host";
import type { FleetRead } from "./fleet";
import { fleetFixture } from "./fleet.test-fixture";

const transport = (read: (command: string, args?: Record<string, unknown>) => Promise<unknown>) =>
  <T,>(command: string, args?: Record<string, unknown>): Promise<T> => read(command, args) as Promise<T>;
const signed = {status: "signed_in", reason: null, acquisition: true, content: true};
const fleetRead = (host: MissionHost) => {
  const read = (host as MissionHost & {readFleet?: FleetRead}).readFleet;
  expect(read, "fixed Fleet host read absent").toBeTypeOf("function");
  return read!;
};

describe("fixed Fleet acquisition", () => {
  it("invokes one fixed native command with only the validated window", async () => {
    const calls: [string, unknown][] = [];
    const client = await createNativeClient(transport(async (command, args) => {
      calls.push([command, args]); return command === "auth_status" ? signed : fleetFixture();
    }), async () => () => {});
    const result = await fleetRead(bindMissionHost(client))({window: "24h", signal: new AbortController().signal});
    expect(calls.at(-1)).toEqual(["read_fleet", {selection: {window: "24h"}}]);
    expect(result.hosts[0].metrics.cpu_busy_pct).toBe(0);
    expect(result.hosts[0].metrics.fabric_active_lanes).toBe(0);
  });
  it("rejects wrong-window responses and malformed producer data", async () => {
    let response: unknown = {...fleetFixture(), window: "7d"};
    const client = await createNativeClient(transport(async command => command === "auth_status" ? signed : response), async () => () => {});
    const read = fleetRead(bindMissionHost(client));
    await expect(read({window: "24h", signal: new AbortController().signal})).rejects.toThrow();
    response = {...fleetFixture(), private_path: "/secret"};
    await expect(read({window: "24h", signal: new AbortController().signal})).rejects.toThrow();
  });
  it("cancels on auth invalidation and consumes late native outcomes", async () => {
    let notify!: (event: {payload: unknown}) => void, resolve!: (value: unknown) => void;
    const client = await createNativeClient(transport(async command => command === "auth_status" ? signed : new Promise(done => {resolve = done;})), async (_event, listener) => {notify = listener; return () => {};});
    let outcome = "PENDING";
    const done = fleetRead(bindMissionHost(client))({window: "24h", signal: new AbortController().signal})
      .then(() => {outcome = "RESOLVED";}, (error: Error) => {outcome = error.message;});
    notify({payload: signed});
    for (let n = 0; n < 12; n++) await Promise.resolve();
    expect(outcome).toBe("READ_CANCELLED");
    resolve(fleetFixture()); await done; expect(outcome).toBe("READ_CANCELLED");
  });
});
