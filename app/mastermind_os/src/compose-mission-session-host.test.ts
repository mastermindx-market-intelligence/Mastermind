import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { composeMissionHost } from "./compose-mission-host";
import type { RawClient } from "./host";
import {
  completeExecutiveSessionBinding,
  readSessionOwnerContext,
} from "./orchestration/os-executive-session-host";
import type { ExecutiveSessionTransport } from "./orchestration/executive-session-command-port";

const WS = "WS:ALPHA";
const ROOT = "JOB-1";
const REF = `fabric_attempt:${"a".repeat(64)}`;
const OPKEY = `session-continue-${"b".repeat(64)}`;
const SCOPE = "c".repeat(64);

function sessionEnvelope(state: "RESOLVED" | "UNAVAILABLE" = "RESOLVED") {
  return {
    schema: "mastermind.os.executive.session_result.v1",
    operation: "context",
    ok: true,
    effect: "NONE",
    operation_key: null,
    data: {
      schema: "mastermind.os.executive.session_context.v1",
      principal_scope: SCOPE,
      verified_expiry: Math.floor(Date.now() / 1000) + 60,
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
  };
}

function fixture(session: boolean) {
  let generation = 0;
  const listeners = new Set<() => void>();
  const transport: ExecutiveSessionTransport | undefined = session
    ? {
        authGeneration: () => generation,
        available: () => generation > 0,
        subscribe(fn) {
          listeners.add(fn);
          return () => {
            listeners.delete(fn);
          };
        },
        context: vi.fn(async () => sessionEnvelope()),
        send: vi.fn(async () => {
          throw new Error("unused");
        }),
        reply: vi.fn(async () => {
          throw new Error("unused");
        }),
      }
    : undefined;
  const client: RawClient = {
    ...(transport ? { executiveSession: transport } : {}),
    getState: () => ({
      status: generation > 0 ? "signed_in" : "signed_out",
      reason: null,
      acquisition: generation > 0,
      content: generation > 0,
    }),
    subscribe: () => () => {},
    signIn: async () => {},
    signOut: async () => {},
    readPrograms: async () => ({}),
    readWork: async () => ({}),
    readMission: async () => ({}),
    readCurrentWindow: async () => ({}),
  };
  return {
    client,
    context: (transport ? transport.context : undefined) as unknown as ReturnType<typeof vi.fn>,
    signIn() {
      generation = 1;
      for (const listener of listeners) listener();
    },
    listenerCount: () => listeners.size,
  };
}

const disposals: Array<() => void> = [];
afterEach(() => {
  disposals.splice(0).forEach((d) => d());
});

describe("session capability composition", () => {
  it("mounts the separate session binding without any Launch catalog", async () => {
    const f = fixture(true);
    const composed = composeMissionHost(f.client, null, new IDBFactory());
    disposals.push(composed.dispose);
    const binding = completeExecutiveSessionBinding(composed.host.sessionCommandBinding);
    expect(binding).not.toBeNull();
    expect(composed.host.commandBinding).toBeUndefined();
    // Signed out: the capability exists but is unavailable and sends nothing.
    expect(readSessionOwnerContext(binding!)).toBeNull();
    expect(f.context).not.toHaveBeenCalled();
    await composed.host.session!.refresh({ workRef: WS, rootJobId: ROOT });
    expect(f.context).not.toHaveBeenCalled();
    // Sign-in qualifies the exact selected Mission through the pushed selection.
    f.signIn();
    await composed.host.session!.refresh({ workRef: WS, rootJobId: ROOT });
    await composed.sessionReady;
    expect(f.context).toHaveBeenCalledTimes(2);
    expect(binding!.port.currentTargetRef()).toBe(REF);
    expect(readSessionOwnerContext(binding!)?.principalScope).toBe(SCOPE);
    expect(
      binding!.makeSessionMessageIntent(REF, "Continue", "CI green"),
    ).not.toBeNull();
  });

  it("mounts no session capability when the client exposes no session transport", () => {
    const f = fixture(false);
    const composed = composeMissionHost(f.client, null, new IDBFactory());
    disposals.push(composed.dispose);
    expect(composed.host.sessionCommandBinding).toBeUndefined();
    expect(composed.host.session).toBeUndefined();
  });

  it("dispose unsubscribes the session transport", async () => {
    const f = fixture(true);
    const composed = composeMissionHost(f.client, null, new IDBFactory());
    await composed.sessionReady;
    expect(f.listenerCount()).toBe(1);
    composed.dispose();
    expect(f.listenerCount()).toBe(0);
  });
});
