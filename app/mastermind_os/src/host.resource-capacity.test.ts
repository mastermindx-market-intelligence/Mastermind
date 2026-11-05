import { expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "./host";
import fixture from "./resources/fixtures/resource-capacity-owner-read.json";
import { decodeResourceCapacityRead } from "./resources/resource-capacity-read";
const selected = fixture.selection;
const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
const request = () => ({ ...selected, signal: new AbortController().signal });
export async function capacityHost(read = async (): Promise<unknown> => fixture) {
  let notify = (_: unknown) => {};
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "read_resource_capacity") return read();
    throw Error("unexpected native command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => { notify = payload => listener({ payload }); return () => {}; });
  return { raw, host: bindMissionHost(raw), invoke, notify };
}
it("uses only the fixed native original-claim read and actual bounded owner response", async () => {
  const env = await capacityHost();
  const result = await env.host.readResourceCapacity!(request());
  expect(result.state).toBe("AVAILABLE");
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_resource_capacity")).toEqual([["read_resource_capacity", { selection: selected }]]);
});
it("refuses unsafe selectors before invocation and clears a reply after authentication changes", async () => {
  let finish!: (v: unknown) => void;
  const env = await capacityHost(() => new Promise(resolve => { finish = resolve; }));
  await expect(env.host.readResourceCapacity!({ ...request(), host_ref: "supplied" } as never)).rejects.toThrow("RESOURCE_CAPACITY_SELECTION_INVALID");
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_resource_capacity")).toEqual([]);
  const pending = env.host.readResourceCapacity!(request());
  env.notify({ ...signed, status: "signed_out", acquisition: false });
  finish(fixture);
  await expect(pending).rejects.toThrow("READ_CANCELLED");
});
it("refuses a source reader replacement while its original read is pending", async () => {
  let finish!: (v: unknown) => void;
  const env = await capacityHost(() => new Promise(resolve => { finish = resolve; }));
  const pending = env.host.readResourceCapacity!(request());
  env.raw.readResourceCapacity = async () => fixture;
  finish(fixture);
  await expect(pending).rejects.toThrow("READ_CANCELLED");
});
it("rejects foreign selections, forged observation, raw secrets and placement promotion", () => {
  expect(() => decodeResourceCapacityRead(fixture, { ...selected, job_id: "JOB-999" })).toThrow();
  const changed = structuredClone(fixture); changed.source_observation.runtime.after++;
  expect(() => decodeResourceCapacityRead(changed, selected)).toThrow();
  const raw = { ...fixture, secret: "PRIVATE" };
  expect(() => decodeResourceCapacityRead(raw, selected)).toThrow();
  const grant = structuredClone(fixture); grant.provider_capacity.can_place_work = true;
  expect(() => decodeResourceCapacityRead(grant, selected)).toThrow();
});
