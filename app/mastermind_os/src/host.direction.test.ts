import { expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "./host";
import fixture from "./direction/fixtures/accepted-direction-owner.json";

const selected = fixture.selection;
const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
const request = () => ({ ...selected, signal: new AbortController().signal });
async function environment(read = async (): Promise<unknown> => fixture) {
  let notify = (_: unknown) => {};
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "read_project_direction") return read();
    throw new Error("unexpected command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => { notify = payload => listener({ payload }); return () => {}; });
  return { raw, host: bindMissionHost(raw), invoke, notify };
}

it("reads the actual Root owner fixture through only the fixed native Direction command", async () => {
  const env = await environment();
  const value = await env.host.readProjectDirection!(request());
  expect(value.availability).toBe("AVAILABLE");
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_direction")).toEqual([["read_project_direction", { selection: selected }]]);
});

it("rejects caller paths/Root IDs before native invocation", async () => {
  const env = await environment();
  for (const extra of [{ path: "private" }, { root_job_id: "JOB-1" }, { commit: "a".repeat(40) }]) {
    await expect(env.host.readProjectDirection!({ ...request(), ...extra } as never)).rejects.toThrow("DIRECTION_SELECTION_INVALID");
  }
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_direction")).toEqual([]);
});

it("withholds replies across signout and source-reader replacement", async () => {
  for (const kind of ["signout", "reader"] as const) {
    let finish!: (body: unknown) => void;
    const env = await environment(() => new Promise(resolve => { finish = resolve; }));
    const pending = env.host.readProjectDirection!(request());
    if (kind === "signout") env.notify({ status: "signed_out", reason: null, acquisition: false, content: false });
    else env.raw.readProjectDirection = async () => fixture;
    finish(fixture);
    await expect(pending).rejects.toThrow("READ_CANCELLED");
  }
});
