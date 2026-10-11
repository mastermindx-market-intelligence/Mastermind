import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { composeMissionHost } from "./compose-mission-host";
import type { RawClient } from "./host";
import { OperationController } from "./orchestration/operation-controller";
import { intentIdForOperationKey } from "./orchestration/operation-key";
import type { OsExecutiveTransport } from "./orchestration/os-executive-host";

const config = { workstream: "WS:APP-FIXTURE", priority: 0,
  projects: [{ ref: "research", label: "Research" }], profiles: [{ ref: "research_only", label: "Research only" }] };
const disposals: Array<() => void> = [];
afterEach(() => { disposals.splice(0).forEach((d) => d()); });
function fixture() {
  let signed = false, generation = 0;
  const listeners = new Set<() => void>();
  const transport: OsExecutiveTransport = {
    authGeneration: () => generation, available: () => signed,
    subscribe(fn) { listeners.add(fn); return () => { listeners.delete(fn); }; },
    context: vi.fn(async () => ({ schema: "mastermind.os.executive.owner_context.v1", principal_scope: "a".repeat(64),
      verified_expiry: Math.floor(Date.now() / 1000) + 60, profile: { name: "web_ceo_v3", server_version: "1.4.0" } })),
    submit: vi.fn(async () => { throw new Error("lost response after backend acceptance"); }),
    status: vi.fn(async ({ intent_id }) => ({
      schema: "mastermind.executive_mcp_result.v1", tool: "ceo_intent_status", ok: true,
      server_version: "1.4.0", mode: "readonly", generated_at: "2026-10-05T00:00:00Z",
      grounding: {}, degraded: [], bounded: [], error: null,
      data: { schema: "mastermind.ceo_intent_receipt.v1", intent_id, fingerprint: "f".repeat(64),
        job_id: "JOB-731", work_ref: config.workstream, status: "QUEUED", accepted: true, duplicate: false,
        dispatched: false, authority: { requested: [], policy_sha256: "a".repeat(64), authority_level: "A0" },
        grounding: {}, created_at_ms: 0 },
    })),
  };
  const client: RawClient = { executive: transport,
    getState: () => ({ status: signed ? "signed_in" : "signed_out", reason: null, acquisition: signed, content: signed }),
    subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {},
    readPrograms: async () => ({}), readWork: async () => ({}), readMission: async () => ({}), readCurrentWindow: async () => ({}) };
  return { client, transport, listeners, signIn() { signed = true; generation++; listeners.forEach((l) => l()); } };
}
function mount(client: RawClient, factory: IDBFactory, configured = true) {
  const c = composeMissionHost(client, configured ? config : null, factory); disposals.push(c.dispose); return c;
}
describe("actual app host composition", () => {
  it("does not invent a launch manifest or absent Executive transport", () => {
    const f = fixture(), factory = new IDBFactory();
    expect(mount(f.client, factory, false).host.commandBinding).toBeUndefined();
    const { executive: _, ...readOnly } = f.client;
    expect(mount(readOnly, factory).host.commandBinding).toBeUndefined();
    expect(f.transport.context).not.toHaveBeenCalled();
  });
  it("mounts signed out, qualifies on real owner context, then reopens and recovers the exact original operation without resubmit", async () => {
    const f = fixture(), factory = new IDBFactory(), c = mount(f.client, factory);
    await c.ready; const binding = c.host.commandBinding!;
    expect(binding.port.context()).toBeNull();
    f.signIn(); await vi.waitFor(() => expect(binding.port.context()).not.toBeNull());
    const form = { goal: "Fixture authorized launch", projectRef: "research", profileRef: "research_only" };
    const intent = binding.makeLaunchIntent(form)!;
    expect(binding.getView().projects).toEqual(config.projects);
    const controller = new OperationController(binding.port, binding.store);
    const lost = await controller.begin(intent); expect(lost.status).toBe("unknown");
    const pointer = lost.pointer!; expect(pointer.targetKey).toBe(config.workstream);
    c.dispose(); expect(f.listeners.size).toBe(0);
    const reopened = mount(f.client, factory); await reopened.ready;
    const next = reopened.host.commandBinding!;
    const recovered = await new OperationController(next.port, next.store).recover();
    expect(recovered).toMatchObject({ status: "accepted", pointer: null,
      missionSelection: { workRef: config.workstream, rootJobId: "JOB-731" } });
    expect(f.transport.submit).toHaveBeenCalledTimes(1);
    expect(f.transport.status).toHaveBeenCalledExactlyOnceWith(
      { intent_id: intentIdForOperationKey(pointer.operationKey) }, expect.any(AbortSignal));
    expect(await next.store.read("a".repeat(64))).toBeNull();
  });
});
