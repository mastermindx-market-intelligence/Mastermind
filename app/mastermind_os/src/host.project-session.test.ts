import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient, type RawClient } from "./host";
import fixture from "./fixtures/project-session-association-producer.json";
const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
const out = { status: "signed_out" as const, reason: null, acquisition: false, content: false };
const selection = { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id };
const request = () => ({ ...selection, signal: new AbortController().signal });
const deferred = () => {
  let resolve!: (value: unknown) => void;
  return { promise: new Promise<unknown>(yes => { resolve = yes; }), resolve: (value: unknown) => resolve(value) };
};
async function native(read = async () => fixture as unknown) {
  let notify = (_: unknown) => {};
  const invoke = vi.fn(async (command: string, _args?: Record<string, unknown>) => {
    if (command === "auth_status") return signed;
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "read_project_session") return read();
    throw Error("unexpected native command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => {
    notify = payload => listener({ payload }); return () => {};
  });
  return { raw, invoke, notify };
}
describe("project-session fixed native host composition", () => {
  it("decodes the actual owner fixture and invokes only one fixed paired read", async () => {
    const env = await native();
    const value = await bindMissionHost(env.raw).readProjectSessionAssociation!(request());
    expect(value).toEqual(fixture);
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_session")).toEqual([
      ["read_project_session", { selection: { work_ref: selection.workRef, root_job_id: selection.rootJobId } }],
    ]);
  });
  it("optional capability leaves older clients compatible", async () => {
    const env = await native();
    const old: RawClient = { ...env.raw, readProjectSessionAssociation: undefined };
    expect(bindMissionHost(old).readProjectSessionAssociation).toBeUndefined();
  });
  it("revocation fences an already-running native read and does not retry", async () => {
    const late = deferred(); const env = await native(() => late.promise);
    const host = bindMissionHost(env.raw);
    const pending = host.readProjectSessionAssociation!(request());
    const rejected = expect(pending).rejects.toThrow("READ_CANCELLED");
    env.notify(out); late.resolve(fixture); await rejected;
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_session")).toHaveLength(1);
  });
  it("rejects a foreign selection before native transport", async () => {
    const env = await native();
    await expect(bindMissionHost(env.raw).readProjectSessionAssociation!({ ...request(), workRef: "WS:ONE\n" })).rejects.toThrow("PROJECT_SESSION_SELECTION_INVALID");
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_session")).toHaveLength(0);
  });
  it("aborted read makes no native command and wrong source selection never displays", async () => {
    const env = await native(async () => ({ ...fixture, selection: { ...fixture.selection, root_job_id: "JOB-999999" } }));
    const controller = new AbortController(); controller.abort();
    await expect(bindMissionHost(env.raw).readProjectSessionAssociation!({ ...selection, signal: controller.signal })).rejects.toThrow();
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_session")).toHaveLength(0);
    await expect(bindMissionHost(env.raw).readProjectSessionAssociation!(request())).rejects.toThrow("PROJECT_SESSION_RESPONSE_INVALID");
  });
});

