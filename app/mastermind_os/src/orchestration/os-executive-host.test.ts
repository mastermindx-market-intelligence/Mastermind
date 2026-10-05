import { afterEach, describe, expect, it, vi } from "vitest";
import { createOsExecutiveHost, decodeExecutiveContext, type OsExecutiveTransport } from "./os-executive-host";
import type { PendingPointerStore } from "./operation-controller";

const scopeA = "a".repeat(64), scopeB = "b".repeat(64);
const dto = (scope = scopeA, expiry = 2000) => ({
  schema: "mastermind.os.executive.owner_context.v1", principal_scope: scope,
  verified_expiry: expiry, profile: { name: "web_ceo_v3", server_version: "1.4.0" },
});
const config = { workstream: "WS:TEST-ONLY", priority: 0,
  projects: [{ ref: "executive-infrastructure", label: "Fixture" }],
  profiles: [{ ref: "research_only", label: "Research" }] };
const deferred = <T,>() => { let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; }); return { promise, resolve }; };
function fixture() {
  let generation = 1, available = true;
  const listeners = new Set<() => void>();
  const transport: OsExecutiveTransport = {
    authGeneration: () => generation, available: () => available,
    subscribe: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    context: vi.fn(async () => dto()),
    submit: vi.fn(async () => ({ ok: false, error: { code: "backend_unavailable" } })),
    status: vi.fn(async () => ({ ok: false, error: { code: "not_found" } })),
  };
  return { transport, change(value = true) { generation++; available = value; for (const l of listeners) l(); },
    driftWithoutEvent() { generation++; }, listenerCount: () => listeners.size };
}
const disposals: Array<() => void> = [];
const mount = (f: ReturnType<typeof fixture>) => {
  // This unit exercises only the host boundary; the controller/store have their own suite.
  const host = createOsExecutiveHost(config, f.transport, {} as PendingPointerStore, () => 1_000_000);
  disposals.push(host.dispose); return host;
};
afterEach(() => { for (const dispose of disposals.splice(0)) dispose(); vi.useRealTimers(); });
const tick = async () => { await Promise.resolve(); await Promise.resolve(); };

describe("verified Executive host", () => {
  it("accepts only the exact current authenticated context DTO", () => {
    expect(decodeExecutiveContext(dto(), 1_000_000)?.principalScope).toBe(scopeA);
    for (const invalid of [null, { ...dto(), token: "secret" }, { ...dto(), principal_scope: "subject" },
      { ...dto(), verified_expiry: 1000 }, { ...dto(), verified_expiry: NaN },
      { ...dto(), profile: { name: "web_ceo_v3", server_version: "1.3.1" } },
      { ...dto(), profile: { ...dto().profile, scopes: [] } }])
      expect(decodeExecutiveContext(invalid, 1_000_000)).toBeNull();
  });
  it("mounts an unavailable binding then qualifies after the existing auth owner signs in", async () => {
    const f = fixture(); f.change(false); const h = mount(f); await h.ready;
    expect(h.binding.port.context()).toBeNull(); expect(f.transport.context).not.toHaveBeenCalled();
    f.change(true); await tick();
    expect(h.binding.port.context()?.principalScope).toBe(scopeA);
  });
  it("invalidates immediately and withholds late context across A to B to A", async () => {
    const f = fixture(); const first = deferred<unknown>();
    vi.mocked(f.transport.context).mockReturnValueOnce(first.promise);
    const h = mount(f); expect(h.binding.port.context()).toBeNull();
    vi.mocked(f.transport.context).mockResolvedValueOnce(dto(scopeB)); f.change(); await tick();
    const b = h.binding.port.context(); expect(b?.principalScope).toBe(scopeB);
    vi.mocked(f.transport.context).mockResolvedValueOnce(dto(scopeA)); f.change(); await tick();
    const a = h.binding.port.context(); expect(a?.principalScope).toBe(scopeA);
    expect(a?.generation).not.toBe(b?.generation);
    first.resolve(dto(scopeB)); await h.ready;
    expect(h.binding.port.context()).toEqual(a);
  });
  it("aborts and withholds a late submit while retaining operation identity for the controller", async () => {
    const f = fixture(), late = deferred<unknown>();
    vi.mocked(f.transport.submit).mockReturnValue(late.promise);
    const h = mount(f); await h.ready;
    const intent = h.binding.makeLaunchIntent({ goal: "Read fixture", projectRef: "executive-infrastructure", profileRef: "research_only" })!;
    const pointer = h.binding.port.prepare(intent);
    const result = h.binding.port.submit(pointer, intent, new AbortController().signal);
    const submittedSignal = vi.mocked(f.transport.submit).mock.calls[0][1];
    f.change(false); expect(submittedSignal.aborted).toBe(true); expect(h.binding.port.context()).toBeNull();
    late.resolve({ ok: true, status: "accepted" });
    expect(await result).toMatchObject({ operationKey: pointer.operationKey, disposition: "unknown" });
    expect(f.transport.submit).toHaveBeenCalledTimes(1);
  });
  it("checks the private auth generation even if the display state never changes", async () => {
    const f = fixture(), late = deferred<unknown>(); vi.mocked(f.transport.context).mockReturnValue(late.promise);
    const h = mount(f); f.driftWithoutEvent(); late.resolve(dto()); await h.ready;
    expect(h.binding.port.context()).toBeNull();
  });
  it("expires the verified context and releases subscriptions on disposal", async () => {
    vi.useFakeTimers(); const f = fixture();
    vi.mocked(f.transport.context).mockResolvedValue(dto(scopeA, 1001)); const h = mount(f); await h.ready;
    const listener = vi.fn(); h.binding.subscribe(listener);
    await vi.advanceTimersByTimeAsync(1000); expect(h.binding.port.context()).toBeNull(); expect(listener).toHaveBeenCalled();
    h.dispose(); expect(f.listenerCount()).toBe(0);
  });
  it("withholds late recovery status after sign-out and never submits", async () => {
    const f = fixture(), late = deferred<unknown>();
    vi.mocked(f.transport.status).mockReturnValue(late.promise);
    const h = mount(f); await h.ready;
    const intent = h.binding.makeLaunchIntent({ goal: "Read fixture", projectRef: "executive-infrastructure", profileRef: "research_only" })!;
    const pointer = h.binding.port.prepare(intent);
    const result = h.binding.port.readOperation(pointer, new AbortController().signal);
    const requested = vi.mocked(f.transport.status).mock.calls[0];
    f.change(false);
    expect(requested[1].aborted).toBe(true);
    late.resolve({ ok: true, data: { intent_id: requested[0].intent_id } });
    expect(await result).toMatchObject({ operationKey: pointer.operationKey, disposition: "unknown" });
    expect(f.transport.status).toHaveBeenCalledTimes(1);
    expect(f.transport.submit).not.toHaveBeenCalled();
  });

});
