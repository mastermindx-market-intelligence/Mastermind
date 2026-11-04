import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient, type RawClient } from "./host";
import fixture from "./fixtures/project-plan-canonical-owner.json";
const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
const out = { status: "signed_out" as const, reason: null, acquisition: false, content: false };
const selection = { work_ref: "WS:ONE" };
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
    if (command === "read_project_plan") return read();
    throw Error("unexpected native command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => {
    notify = payload => listener({ payload }); return () => {};
  });
  return { raw, invoke, notify };
}
describe("canonical project-plan native host composition", () => {
  it("decodes the actual owner fixture and invokes only one fixed rootless read", async () => {
    const env = await native();
    const value = await bindMissionHost(env.raw).readProjectPlan!(request());
    expect(value).toEqual(fixture);
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_plan")).toEqual([
      ["read_project_plan", { selection }],
    ]);
  });
  it("optional capability leaves older clients compatible", async () => {
    const env = await native();
    const old: RawClient = { ...env.raw, readProjectPlan: undefined };
    expect(bindMissionHost(old).readProjectPlan).toBeUndefined();
  });
  it("revocation fences an already-running native read and does not retry", async () => {
    const late = deferred(); const env = await native(() => late.promise);
    const host = bindMissionHost(env.raw);
    const pending = host.readProjectPlan!(request());
    const rejected = expect(pending).rejects.toThrow("READ_CANCELLED");
    env.notify(out); late.resolve(fixture); await rejected;
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_plan")).toHaveLength(1);
  });
  it("rejects a foreign selection before native transport", async () => {
    const env = await native();
    await expect(bindMissionHost(env.raw).readProjectPlan!({ ...request(), work_ref: "WS:ONE\n" })).rejects.toThrow("PROJECT_PLAN_SELECTION_INVALID");
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_plan")).toHaveLength(0);
  });
  it("aborted read makes no native command and wrong source selection never displays", async () => {
    const env = await native(async () => ({ ...fixture, selection: { work_ref: "WS:OTHER" } }));
    const controller = new AbortController(); controller.abort();
    await expect(bindMissionHost(env.raw).readProjectPlan!({ ...selection, signal: controller.signal })).rejects.toThrow();
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_plan")).toHaveLength(0);
    await expect(bindMissionHost(env.raw).readProjectPlan!(request())).rejects.toThrow("PROJECT_PLAN_INVALID");
  });
});

import planV2Fixture from "./fixtures/project-plan-v2-owner.json";
describe("project plan v2 through incumbent native read", () => {
  const selection = { work_ref: "WS:PLAN-TEST" };
  it("decodes actual Python v2 with the same sole fixed command", async () => {
    const body = planV2Fixture.cases.available_pending;
    const env = await native(async () => body);
    const value = await bindMissionHost(env.raw).readProjectPlan!({ ...selection, signal: new AbortController().signal });
    expect(value).toEqual(body);
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_plan")).toEqual([["read_project_plan", { selection }]]);
  });
  it("discards v2 continuity on the same existing revocation fence", async () => {
    const late = deferred(); const env = await native(() => late.promise);
    const pending = bindMissionHost(env.raw).readProjectPlan!({ ...selection, signal: new AbortController().signal });
    const rejected = expect(pending).rejects.toThrow("READ_CANCELLED");
    env.notify(out); late.resolve(planV2Fixture.cases.available_pending); await rejected;
    expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_plan")).toHaveLength(1);
  });
});
