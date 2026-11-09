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
    readPrograms: vi.fn(async () => ({})), readWork: async () => ({}), readMission: async () => ({}), readCurrentWindow: async () => ({}) };
  return { client, transport, listeners, signIn() { signed = true; generation++; listeners.forEach((l) => l()); } };
}
function mount(client: RawClient, factory: IDBFactory, configured = true,
  hostKind: "native" | "web" | "unknown" = "unknown") {
  const c = composeMissionHost(client, configured ? config : null, factory, hostKind); disposals.push(c.dispose); return c;
}
/** Sets the build-time Executive resource input for one synchronous read. */
function withExecutiveResource<T>(value: string, run: () => T): T {
  vi.stubEnv("VITE_MM_EXECUTIVE_RESOURCE", value);
  try { return run(); }
  finally { vi.unstubAllEnvs(); }
}
describe("actual app host composition", () => {
  it("mounts the Executive owner without inventing a legacy manifest or absent transport", () => {
    const f = fixture(), factory = new IDBFactory();
    const unconfigured = mount(f.client, factory, false).host.commandBinding!;
    expect(unconfigured).toBeDefined();
    expect(unconfigured.port.context()).toBeNull();
    expect(unconfigured.getView()).toEqual({ projects: [], profiles: [], session: null });
    expect(unconfigured.makeLaunchIntent({ goal: "No static enrollment", projectRef: "research", profileRef: "research_only" })).toBeNull();
    const { executive: _, ...readOnly } = f.client;
    expect(mount(readOnly, factory).host.commandBinding).toBeUndefined();
    expect(f.transport.context).not.toHaveBeenCalled();
  });
  it("qualifies signed-out composition then recovers the same original after the legacy manifest is withdrawn", async () => {
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
    const reopened = mount(f.client, factory, false); await reopened.ready;
    const next = reopened.host.commandBinding!;
    expect(next.getView()).toEqual({ projects: [], profiles: [], session: null });
    expect(next.makeLaunchIntent(form)).toBeNull();
    const recovered = await new OperationController(next.port, next.store).recover();
    expect(recovered).toMatchObject({ status: "accepted", pointer: null,
      missionSelection: { workRef: config.workstream, rootJobId: "JOB-731" } });
    expect(f.transport.submit).toHaveBeenCalledTimes(1);
    expect(f.transport.status).toHaveBeenCalledExactlyOnceWith(
      { intent_id: intentIdForOperationKey(pointer.operationKey) }, expect.any(AbortSignal));
    expect(await next.store.read("a".repeat(64))).toBeNull();
  });
});

describe("composition diagnostics", () => {
  it("reports only zero-effect composition facts without any extra context, invoke or read call", async () => {
    const f = fixture(), factory = new IDBFactory(), c = mount(f.client, factory);
    await c.ready;
    const listenersBefore = f.listeners.size;
    const contextBefore = vi.mocked(f.transport.context).mock.calls.length;
    const statusBefore = vi.mocked(f.transport.status).mock.calls.length;
    const submitBefore = vi.mocked(f.transport.submit).mock.calls.length;
    const first = c.host.diagnostics!();
    expect(first.hostKind).toBe("unknown");
    expect(first.launchConfigured).toBe(true);
    expect(first.nativeResourceConfigured).toBeNull();
    expect(first.executiveAvailable).toBeNull();
    expect(["unknown", "not_requested", "pending", "auth_unavailable",
      "transport_failure", "invalid_response", "expired", "ready",
    ]).toContain(first.executiveContextPhase);
    expect(withExecutiveResource("https://executive.example/os/executive",
      () => c.host.diagnostics!().frontendResourceConfigured)).toBe(true);
    expect(withExecutiveResource("http://executive.example",
      () => c.host.diagnostics!().frontendResourceConfigured)).toBe(false);
    expect(withExecutiveResource("",
      () => c.host.diagnostics!().frontendResourceConfigured)).toBe(false);
    expect(vi.mocked(f.transport.context).mock.calls.length).toBe(contextBefore);
    f.signIn();
    const contextAfterSignIn = vi.mocked(f.transport.context).mock.calls.length;
    expect(contextAfterSignIn).toBe(contextBefore + 1); // original refresh, not a diagnostic read
    const second = c.host.diagnostics!();
    expect(second.acquisitionAvailable).toBe(true);
    expect(second.contentAvailable).toBe(true);
    // Signed-in workspace state never implies an Executive grant.
    expect(second.executiveAvailable).toBeNull();
    expect(c.host.diagnostics!()).toEqual(second);
    expect(f.listeners.size).toBe(listenersBefore);
    expect(vi.mocked(f.transport.context).mock.calls.length).toBe(contextAfterSignIn);
    expect(vi.mocked(f.transport.status).mock.calls.length).toBe(statusBefore);
    expect(vi.mocked(f.transport.submit).mock.calls.length).toBe(submitBefore);
    expect(f.client.readPrograms).not.toHaveBeenCalled();
  });

  it("reads Executive availability only from the transport diagnostics, even while signed in", async () => {
    const f = fixture(), factory = new IDBFactory(), c = mount(f.client, factory);
    await c.ready; f.signIn();
    expect(c.host.diagnostics!().executiveAvailable).toBeNull();
    f.transport.diagnostics = () => ({ kind: "native", authAvailable: false, phase: "auth_unavailable" });
    expect(c.host.diagnostics!().executiveAvailable).toBe(false);
    expect(c.host.diagnostics!().executiveTransportPhase).toBe("auth_unavailable");
    f.transport.diagnostics = () => ({ kind: "web", authAvailable: null, phase: "ready" });
    expect(c.host.diagnostics!().executiveAvailable).toBeNull();
    f.transport.diagnostics = () => ({ kind: "web", authAvailable: true, phase: "ready" });
    expect(c.host.diagnostics!().executiveAvailable).toBe(true);
  });

  it("distinguishes the actual mount surface and never infers native resource configuration", () => {
    const f = fixture(), factory = new IDBFactory();
    const native = mount(f.client, factory, true, "native");
    expect(native.host.diagnostics!().hostKind).toBe("native");
    expect(native.host.diagnostics!().nativeResourceConfigured).toBeNull();
    native.dispose();
    const web = mount(f.client, factory, true, "web");
    expect(web.host.diagnostics!().hostKind).toBe("web");
    expect(web.host.diagnostics!().nativeResourceConfigured).toBeNull();
    web.dispose();
    const unconfigured = mount(f.client, factory, false);
    const unconfiguredSnapshot = unconfigured.host.diagnostics!();
    expect(unconfiguredSnapshot.launchConfigured).toBe(false);
    expect(unconfiguredSnapshot.executiveContextPhase).toBe("not_requested");
    unconfigured.dispose();
  });
});
