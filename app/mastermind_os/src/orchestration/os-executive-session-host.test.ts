// Focused coverage for the separately mounted session host lifecycle.
// Every fixture is in-memory: no backend, route, credential or producer.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  completeExecutiveSessionBinding,
  createOsExecutiveSessionHost,
  readSessionOwnerContext,
} from "./os-executive-session-host";
import type {
  ExecutiveSessionTransport,
  SessionSendArguments,
} from "./executive-session-command-port";
import { OperationController } from "./operation-controller";
import type { PendingPointerStore } from "./operation-controller";

const WS = "WS:ALPHA";
const ROOT = "JOB-1";
const REF = `fabric_attempt:${"a".repeat(64)}`;
const OPKEY = `session-continue-${"b".repeat(64)}`;
const SCOPE = "c".repeat(64);

function memStore(): PendingPointerStore {
  const hints = new Map<string, { operationKey: string; kind: "message"; targetKey: string }>();
  return {
    read: (scope) => hints.get(scope) ?? null,
    reserve: (scope, pointer) => {
      const existing = hints.get(scope);
      if (existing) return { reserved: false, pointer: existing };
      hints.set(scope, { operationKey: pointer.operationKey, kind: "message", targetKey: pointer.targetKey as string });
      return { reserved: true };
    },
    clearIfEqual: (scope, pointer) => {
      const existing = hints.get(scope);
      if (existing && existing.operationKey === pointer.operationKey) {
        hints.delete(scope);
        return true;
      }
      return false;
    },
  };
}

function fixture() {
  let authGen = 1;
  let available = true;
  const listeners = new Set<() => void>();
  const contextSelections: Array<{ workRef: string; rootJobId: string }> = [];
  const envelope = (state: "RESOLVED" | "UNAVAILABLE" | "AMBIGUOUS" = "RESOLVED") => ({
    schema: "mastermind.os.executive.session_result.v1",
    operation: "context",
    ok: true,
    effect: "NONE",
    operation_key: null,
    data: {
      schema: "mastermind.os.executive.session_context.v1",
      principal_scope: SCOPE,
      verified_expiry: 4102444800,
      selection: { work_ref: WS, root_job_id: ROOT },
      selection_state: state,
      target: state === "RESOLVED"
        ? {
            target_ref: REF,
            generation: "a".repeat(24),
            addressable: true,
            kind: "fabric_attempt",
            continuation_operation_key: OPKEY,
            work_ref: WS,
            root_job_id: ROOT,
          }
        : null,
      capabilities: { send: state === "RESOLVED", reply_read: true, stop: false },
    },
    error: null,
  });
  let contextResponse: unknown = envelope();
  const transport: ExecutiveSessionTransport = {
    authGeneration: () => authGen,
    available: () => available,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    context: vi.fn(async (selected: { workRef: string; rootJobId: string }) => {
      contextSelections.push(selected);
      return contextResponse;
    }),
    send: vi.fn(async (_args: SessionSendArguments) => {
      throw new Error("not used here");
    }),
    reply: vi.fn(async () => {
      throw new Error("not used here");
    }),
  };
  return {
    transport,
    contextSelections,
    contextCalls: () => (transport.context as ReturnType<typeof vi.fn>).mock.calls.length,
    setContext: (value: unknown) => {
      contextResponse = value;
    },
    setAvailable: (value: boolean) => {
      available = value;
    },
    bumpAuth: () => {
      authGen++;
      for (const listener of listeners) listener();
    },
  };
}

const disposables: Array<() => void> = [];
afterEach(() => {
  for (const dispose of disposables.splice(0)) dispose();
});

function mount(f: ReturnType<typeof fixture>) {
  const host = createOsExecutiveSessionHost(f.transport, memStore());
  disposables.push(host.dispose);
  return { ...host, ready: host.refresh({ workRef: WS, rootJobId: ROOT }) };
}

describe("selected-session host lifecycle", () => {
  it("does not advertise SEND for a resolved read-only target", async () => {
    const f = fixture();
    const raw = await f.transport.context({ workRef: WS, rootJobId: ROOT }, new AbortController().signal) as { data: { capabilities: { send: boolean } } };
    raw.data.capabilities.send = false;
    f.setContext(raw);
    const host = mount(f); await host.ready;
    expect(readSessionOwnerContext(host.binding)?.principalScope).toBe(SCOPE);
    expect(host.binding.port.currentTargetRef()).toBeNull();
    expect(host.binding.makeSessionMessageIntent(REF, "Continue", "done")).toBeNull();
  });
  it("refreshes on EVERY pushed selection transition, including same-value and A→B→A", async () => {
    const f = fixture();
    const host = mount(f);
    await host.ready;
    expect(f.contextCalls()).toBe(1);
    expect(f.contextSelections[0]).toEqual({ workRef: WS, rootJobId: ROOT });
    const firstGeneration = host.binding.port.context()?.generation;
    // Same-value transition: still an event, still invalidated and re-read.
    await host.refresh({ workRef: WS, rootJobId: ROOT });
    expect(f.contextCalls()).toBe(2);
    // A→B→A: each leg pushes and invalidates; the final generation is new.
    await host.refresh({ workRef: "WS:OTHER", rootJobId: ROOT });
    expect(f.contextCalls()).toBe(3);
    expect(f.contextSelections[2]).toEqual({ workRef: "WS:OTHER", rootJobId: ROOT });
    expect(host.binding.port.context()).toBeNull();
    await host.refresh({ workRef: WS, rootJobId: ROOT });
    expect(f.contextCalls()).toBe(4);
    const generations = new Set([
      firstGeneration,
      host.binding.port.context()?.generation,
    ]);
    expect(generations.size).toBe(2);
    expect(host.binding.port.currentTargetRef()).toBe(REF);
  });

  it("clears a null push and sends nothing while the transport is unavailable", async () => {
    const f = fixture();
    const host = mount(f);
    await host.ready;
    await host.refresh(null);
    expect(host.binding.port.context()).toBeNull();
    f.setAvailable(false);
    await host.refresh({ workRef: WS, rootJobId: ROOT });
    expect(f.contextCalls()).toBe(1); // unavailable transport reads nothing more
    expect(host.binding.port.context()).toBeNull();
  });

  it("re-reads on auth change and fences a stale context reply", async () => {
    const f = fixture();
    const host = mount(f);
    await host.ready;
    const generation = host.binding.port.context()?.generation;
    const initial = await vi.mocked(f.transport.context).mock.results[0].value as { data: Record<string, unknown> };
    let resolve!: (value: unknown) => void;
    const delayed = new Promise<unknown>(done => { resolve = done; });
    vi.mocked(f.transport.context).mockImplementationOnce(() => delayed);
    f.bumpAuth();
    expect(host.binding.port.context()).toBeNull();
    expect(f.contextCalls()).toBe(2);
    f.bumpAuth();
    await Promise.resolve();
    await Promise.resolve();
    expect(f.contextCalls()).toBe(3);
    const current = host.binding.port.context();
    expect(current?.principalScope).toBe(SCOPE);
    expect(current?.generation).not.toBe(generation);
    resolve({ ...initial, data: { ...initial.data, principal_scope: "d".repeat(64) } });
    await delayed;
    await Promise.resolve();
    expect(host.binding.port.context()).toEqual(current);
    expect(host.binding.port.currentTargetRef()).toBe(REF);
  });

  it("carries the explicit synchronous condition provider and no default", async () => {
    const f = fixture();
    const host = mount(f);
    await host.ready;
    // No provider registered: the two-argument helper refuses outright.
    expect(host.binding.makeMessageIntent(REF, "Continue")).toBeNull();
    host.setStopCondition(() => "CI green");
    const explicit = host.binding.makeMessageIntent(REF, "Continue");
    expect(explicit?.payload).toMatchObject({ stop_condition: "CI green" });
    expect(host.binding.makeLaunchIntent({ goal: "g", projectRef: "p", profileRef: "r" })).toBeNull();
    expect(host.binding.makeStopIntent(REF)).toBeNull();
  });

  it("dispose stops subscription, drops the session and clears the provider", async () => {
    const f = fixture();
    const host = mount(f);
    await host.ready;
    host.setStopCondition(() => "owned");
    expect(host.binding.makeMessageIntent(REF, "Continue")).not.toBeNull();
    host.dispose();
    expect(readSessionOwnerContext(host.binding)).toBeNull();
    expect(host.binding.makeMessageIntent(REF, "Continue")).toBeNull();
    f.bumpAuth();
    await Promise.resolve();
    await Promise.resolve();
    expect(f.contextCalls()).toBe(1);
  });
});

describe("completeExecutiveSessionBinding shape gate", () => {
  it("accepts the mounted binding and refuses launch-shaped or aliased substitutes", async () => {
    const f = fixture();
    const host = mount(f);
    await host.ready;
    expect(completeExecutiveSessionBinding(host.binding)).toBe(host.binding);
    expect(completeExecutiveSessionBinding(null)).toBeNull();
    expect(completeExecutiveSessionBinding({})).toBeNull();
    const aliased = {
      ...host.binding,
      store: { ...host.binding.store, write: () => undefined },
    };
    expect(completeExecutiveSessionBinding(aliased)).toBeNull();
    const cleared = {
      ...host.binding,
      store: { ...host.binding.store, clear: () => undefined },
    };
    expect(completeExecutiveSessionBinding(cleared)).toBeNull();
    const withoutSessionEntry = { ...host.binding };
    delete (withoutSessionEntry as Record<string, unknown>).makeSessionMessageIntent;
    expect(completeExecutiveSessionBinding(withoutSessionEntry)).toBeNull();
  });

  it("drives a real controller against the mounted binding", async () => {
    const f = fixture();
    const store = memStore();
    const host = createOsExecutiveSessionHost(f.transport, store);
    disposables.push(host.dispose);
    await host.refresh({ workRef: WS, rootJobId: ROOT });
    const controller = new OperationController(host.binding.port, store);
    const intent = host.binding.makeSessionMessageIntent(REF, "Continue", "CI green");
    expect(intent).not.toBeNull();
    // The send transport is not wired to succeed here; a lost response must
    // retain the exact original pointer for status-only recovery.
    const state = await controller.begin(intent!);
    expect(state.status).toBe("unknown");
    expect(state.pointer?.operationKey).toBe(OPKEY);
    expect(state.pointer?.kind).toBe("message");
    const recovered = await controller.recover();
    expect(recovered.status).toBe("unknown"); // reply fixture refuses; pointer retained
    expect((await store.read(SCOPE))?.operationKey).toBe(OPKEY);
  });
});
