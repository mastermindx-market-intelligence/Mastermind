import { describe, expect, it } from "vitest";
import { bindMissionHost, createNativeClient } from "./host";
import fixture from "./fixtures/programs-available-workspace-service.json";

// Native invoke is generic; the test transport supplies untrusted owner JSON.
const transport = (read: (command: string) => Promise<unknown>) =>
  <T,>(command: string): Promise<T> => read(command) as Promise<T>;

describe("fixed Programs receipt companion", () => {
  it("retains the same acquired response's receipt without a second source request", async () => {
    const commands: string[] = [];
    const raw = structuredClone(fixture);
    const client = await createNativeClient(transport(async command => {
      commands.push(command);
      return command === "auth_status" ? { status: "signed_in", reason: null, acquisition: true, content: true } : raw;
    }), async () => () => {});
    const observation = await bindMissionHost(client).readProgramsObservation!({ signal: new AbortController().signal });
    expect(commands).toEqual(["executive_auth_status", "auth_status", "read_programs"]);
    expect(observation.observation).toEqual(fixture.source_observation);
    expect(observation.controlRoom).toEqual(fixture.control_room);
    raw.source_observation.state = "UNKNOWN";
    expect(observation.observation!.state).toBe("SAME");
  });
  it("preserves unavailable as a source-negative observation and malformed as refusal", async () => {
    let response: unknown = { ...structuredClone(fixture), availability: "UNAVAILABLE", control_room: null };
    const client = await createNativeClient(transport(async command => command === "auth_status"
      ? { status: "signed_in", reason: null, acquisition: true, content: true } : response), async () => () => {});
    const host = bindMissionHost(client);
    const observation = await host.readProgramsObservation!({ signal: new AbortController().signal });
    expect(observation).toMatchObject({ availability: "UNAVAILABLE", observation: null, controlRoom: null });
    response = { ...fixture, source_observation: undefined };
    await expect(host.readProgramsObservation!({ signal: new AbortController().signal })).rejects.toThrow();
  });
  it("settles the receipt read at auth invalidation and consumes a late response", async () => {
    let notify!: (event: { payload: unknown }) => void, resolve!: (value: unknown) => void;
    const signed = { status: "signed_in", reason: null, acquisition: true, content: true };
    const client = await createNativeClient(transport(async command => command === "auth_status" ? signed
      : new Promise(value => { resolve = value; })), async (_event, listener) => { notify = listener; return () => {}; });
    let outcome = "PENDING";
    const done = bindMissionHost(client).readProgramsObservation!({ signal: new AbortController().signal })
      .then(() => { outcome = "RESOLVED"; }, (error: Error) => { outcome = error.message; });
    notify({ payload: signed });
    for (let n = 0; n < 12; n++) await Promise.resolve();
    expect(outcome).toBe("READ_CANCELLED");
    resolve(fixture); await done;
    expect(outcome).toBe("READ_CANCELLED");
  });
});
