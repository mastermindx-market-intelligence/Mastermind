// @vitest-environment jsdom
import { StrictMode, type ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  createTerminalSharingHost,
  type TerminalSharingHost,
  type TerminalSharingInvoke,
  type TerminalSharingListen,
} from "../terminal/terminal-sharing-host";
import { TERMINAL_SHARING_UNAVAILABLE } from "../terminal/terminal-sharing-contract";
import { useTerminalSharing } from "./use-terminal-sharing";

const PRINCIPAL = "1a".repeat(32);
const SESSION = "2b".repeat(32);
const CONTENT = "3a".repeat(32);
const REQUEST_REF = "0193f2c4-7a1b-7c2d-8e3f-4a5b6c7d8e9f";
const OTHER_REQUEST_REF = "0193f2c4-7a1b-7c2d-8e3f-4a5b6c7d8e90";
const DELIVERY_ID = "0f8e7d6c-5b4a-6c3d-9e2f-1a2b3c4d5e6f";
const TEAM_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
const ISSUED_AT = "2026-11-04T10:15:30.123456Z";
const OBSERVED_AT = "2026-11-04T10:15:30.654321Z";
const SLOT = "2026-11-04";

const CLOSED = new RegExp(`^${TERMINAL_SHARING_UNAVAILABLE}$`);
const NATIVE_COMMANDS = [
  "terminal_session_status",
  "terminal_sign_in",
  "terminal_disconnect",
  "read_terminal_sharing_requests",
  "open_terminal_sharing_request",
];

function signedInStatus(generation = 5): Record<string, unknown> {
  return {
    state: "SIGNED_IN",
    generation,
    reason: null,
    available: true,
    principal_scope: PRINCIPAL,
    session_scope: SESSION,
  };
}

function signedOutStatus(): Record<string, unknown> {
  return {
    state: "SIGNED_OUT",
    generation: 7,
    reason: null,
    available: false,
    principal_scope: null,
    session_scope: null,
  };
}

function feedFor(
  title: string,
  requestRef = REQUEST_REF,
  deliveryId = DELIVERY_ID,
): Record<string, unknown> {
  return {
    schema: "mastermind.terminal_sharing_request_feed.v1",
    viewer: { principal_scope: PRINCIPAL, session_scope: SESSION },
    source: {
      owner: "TERMINAL_BRIEF_DELIVERY",
      scope: "OWNED_EXPLICIT_SHARING_REQUESTS",
      observed_at: OBSERVED_AT,
    },
    coverage: { state: "COMPLETE_WITHIN_SCOPE", reason_codes: [] },
    requests: [
      {
        request_ref: requestRef,
        revision: 1,
        issued_at: ISSUED_AT,
        delivery: {
          delivery_id: deliveryId,
          content_sha256: CONTENT,
          title,
          slot_asof: SLOT,
          artifact_asof: null,
        },
        audience: {
          team_id: TEAM_ID,
          name: "Boundary owners",
          member_count: 3,
          membership_policy: "DYNAMIC_TEAM_MEMBERSHIP",
        },
        review: { request_ref: requestRef, revision: 1, delivery_id: deliveryId },
      },
    ],
  };
}

type Responder = (args?: Record<string, unknown>) => unknown;

function byCommand(
  map: Record<string, Responder>,
): (command: string, args?: Record<string, unknown>) => unknown {
  return (command, args) => {
    const respond = map[command];
    if (respond === undefined) throw new Error(`unexpected command ${command}`);
    return respond(args);
  };
}

function fakeNative(respond: (command: string, args?: Record<string, unknown>) => unknown) {
  const handlers: Array<(payload: unknown) => void> = [];
  const unlisten = vi.fn();
  const invoke = vi.fn<TerminalSharingInvoke>(async (command, args) => respond(command, args));
  const listen = vi.fn<TerminalSharingListen>(async (event, handler) => {
    if (event !== "terminal-session-changed") throw new Error(`unexpected event ${event}`);
    handlers.push(handler);
    return unlisten;
  });
  return {
    invoke,
    listen,
    unlisten,
    emit: (payload: unknown = null) => {
      for (const handler of [...handlers]) handler(payload);
    },
  };
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const flush = async (): Promise<void> => {
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
};

async function createHost(
  respond: (command: string, args?: Record<string, unknown>) => unknown,
): Promise<{ host: TerminalSharingHost; native: ReturnType<typeof fakeNative> }> {
  const native = fakeNative(respond);
  const host = await createTerminalSharingHost(native.invoke, native.listen);
  return { host, native };
}

describe("useTerminalSharing", () => {
  it("renders nothing while disabled, then reads exactly once when enabled", async () => {
    const reads: Array<Record<string, unknown>> = [];
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => {
        const copy = feedFor("Boundary review brief");
        reads.push(copy);
        return copy;
      },
    }));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host, enabled),
      { initialProps: { enabled: false } },
    );
    await act(async () => {
      await flush();
    });
    expect(result.current.state).toBe("unavailable");
    expect(result.current.requests).toEqual([]);
    expect(result.current.session).toEqual(signedInStatus(5));
    expect(reads).toHaveLength(0);

    await act(async () => {
      rerender({ enabled: true });
      await flush();
    });
    expect(result.current.state).toBe("ready");
    expect(reads).toHaveLength(1);
    expect(result.current.requests).toEqual([
      {
        requestRef: REQUEST_REF,
        requestRevision: "1",
        deliveryId: DELIVERY_ID,
        contentSha256: CONTENT,
        title: "Boundary review brief",
        version: null,
        audienceName: "Boundary owners",
        audienceMemberCount: 3,
        access: "VIEW_ONLY",
      },
    ]);
    expect(result.current.coverage).toEqual({ state: "COMPLETE_WITHIN_SCOPE", reasonCodes: [] });
    expect(native.unlisten).not.toHaveBeenCalled();

    // Rerenders without an activation or epoch change never re-read.
    await act(async () => {
      rerender({ enabled: true });
      rerender({ enabled: true });
      await flush();
    });
    expect(reads).toHaveLength(1);
    expect(native.invoke.mock.calls.every(([command]) => NATIVE_COMMANDS.includes(command))).toBe(true);
  });

  it("keeps a missing capability unavailable without any auth action", async () => {
    const { result } = renderHook(() => useTerminalSharing(null, true));
    await act(async () => {
      await flush();
    });
    expect(result.current.state).toBe("unavailable");
    expect(result.current.requests).toEqual([]);
    expect(result.current.session).toBeNull();
    expect(result.current.coverage).toBeNull();
    await act(async () => {
      await result.current.onConnect();
      await result.current.onDisconnect();
      await result.current.onReview(result.current.requests[0] ?? {
        requestRef: REQUEST_REF,
        requestRevision: "1",
        deliveryId: DELIVERY_ID,
        contentSha256: CONTENT,
        title: "Boundary review brief",
        version: null,
        audienceName: "Boundary owners",
        audienceMemberCount: 3,
        access: "VIEW_ONLY",
      });
    });
    // No command at all: no sign-in, no read, no review navigation.
  });

  it("withdraws the feed in the same render and ignores the stale in-flight completion", async () => {
    const pendings: Array<{ promise: Promise<Record<string, unknown>>; resolve: (value: Record<string, unknown>) => void }> = [];
    const statuses = [signedInStatus(5), signedOutStatus()];
    let statusCursor = 0;
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => statuses[Math.min(statusCursor++, statuses.length - 1)],
      read_terminal_sharing_requests: () => {
        const pending = deferred<Record<string, unknown>>();
        pendings.push(pending);
        return pending.promise;
      },
    }));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host, enabled),
      { initialProps: { enabled: false } },
    );
    await act(async () => {
      rerender({ enabled: true });
      await flush();
    });
    expect(result.current.state).toBe("loading");
    expect(pendings).toHaveLength(1);

    await act(async () => {
      native.emit();
      await flush();
    });
    expect(result.current.state).toBe("unavailable");
    expect(result.current.requests).toEqual([]);

    await act(async () => {
      pendings[0].resolve(feedFor("Late completion"));
      await flush();
    });
    expect(result.current.state).toBe("unavailable");
    expect(result.current.requests).toEqual([]);
    // Signed out: the withdrawn feed is not re-read behind the hook's back.
    expect(native.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"))
      .toHaveLength(1);

    await act(async () => {
      rerender({ enabled: false });
      await flush();
    });
    expect(result.current.state).toBe("unavailable");
  });

  it("re-reads only for a new distinct epoch and binds rows to it", async () => {
    const pendings: Array<{ promise: Promise<Record<string, unknown>>; resolve: (value: Record<string, unknown>) => void }> = [];
    const statuses = [signedInStatus(5), signedInStatus(6)];
    let statusCursor = 0;
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => statuses[Math.min(statusCursor++, statuses.length - 1)],
      read_terminal_sharing_requests: () => {
        const pending = deferred<Record<string, unknown>>();
        pendings.push(pending);
        return pending.promise;
      },
    }));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host, enabled),
      { initialProps: { enabled: false } },
    );
    await act(async () => {
      rerender({ enabled: true });
      await flush();
    });
    expect(result.current.state).toBe("loading");
    await act(async () => {
      pendings[0].resolve(feedFor("Epoch five feed"));
      await flush();
    });
    expect(result.current.state).toBe("ready");
    expect(result.current.requests[0].title).toBe("Epoch five feed");

    await act(async () => {
      native.emit();
      await flush();
    });
    // Old rows withdrawn immediately, before the replacement read resolves.
    expect(result.current.state).toBe("loading");
    expect(result.current.requests).toEqual([]);

    await act(async () => {
      pendings[1].resolve(feedFor("Epoch six feed", OTHER_REQUEST_REF));
      await flush();
    });
    expect(result.current.state).toBe("ready");
    expect(result.current.requests[0].title).toBe("Epoch six feed");
    expect(result.current.requests[0].requestRef).toBe(OTHER_REQUEST_REF);
    expect(native.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"))
      .toHaveLength(2);
  });

  it("withdraws prior-host rows in the same render when a different viewer reuses the numeric epoch", async () => {
    const a = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => feedFor("Private A title"),
    }));
    const pendingB = deferred<Record<string, unknown>>();
    const principalB = "8a".repeat(32);
    const sessionB = "9b".repeat(32);
    const b = await createHost(byCommand({
      terminal_session_status: () => ({ ...signedInStatus(5), principal_scope: principalB, session_scope: sessionB }),
      read_terminal_sharing_requests: () => pendingB.promise,
    }));
    const bRenders: Array<readonly string[]> = [];
    const { result, rerender } = renderHook(({ host }: { host: TerminalSharingHost }) => {
      const current = useTerminalSharing(host, true);
      if (host === b.host) bRenders.push(current.requests.map(row => row.title));
      return current;
    }, { initialProps: { host: a.host } });
    await act(flush);
    expect(result.current.requests[0].title).toBe("Private A title");
    const oldView = result.current.requests[0];
    await act(async () => { rerender({ host: b.host }); await flush(); });
    expect(bRenders.length).toBeGreaterThan(0);
    expect(bRenders.every(titles => titles.length === 0)).toBe(true);
    expect(result.current.requests).toEqual([]);
    expect(result.current.coverage).toBeNull();
    expect(result.current.session?.principal_scope).toBe(principalB);
    await act(async () => { await result.current.onReview(oldView); });
    expect(b.native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request")).toHaveLength(0);
    await act(async () => {
      pendingB.resolve({ ...feedFor("Private B title", OTHER_REQUEST_REF), viewer: { principal_scope: principalB, session_scope: sessionB } });
      await flush();
    });
    expect(result.current.requests.map(row => row.title)).toEqual(["Private B title"]);
  });

  it("never retries a failed read automatically, and re-enabling may read again", async () => {
    let readCalls = 0;
    let succeed = false;
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => {
        readCalls += 1;
        if (!succeed) throw new Error("synthetic-private-native-error");
        return feedFor("Recovered feed");
      },
    }));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host, enabled),
      { initialProps: { enabled: true } },
    );
    await act(async () => {
      await flush();
    });
    expect(result.current.state).toBe("unavailable");
    expect(result.current.requests).toEqual([]);
    expect(readCalls).toBe(1);

    await act(async () => {
      rerender({ enabled: true });
      await flush();
      native.emit();
      await flush();
    });
    expect(readCalls).toBe(1);

    await act(async () => {
      rerender({ enabled: false });
      await flush();
    });
    await act(async () => {
      succeed = true;
      rerender({ enabled: true });
      await flush();
    });
    expect(result.current.state).toBe("ready");
    expect(result.current.requests[0].title).toBe("Recovered feed");
    expect(readCalls).toBe(2);
    expect(native.invoke.mock.calls.every(([command]) => NATIVE_COMMANDS.includes(command))).toBe(true);
  });

  it("reads once under StrictMode double-effect", async () => {
    let readCalls = 0;
    const { host } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => {
        readCalls += 1;
        return feedFor("Strict feed");
      },
    }));
    const { result } = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host, enabled),
      {
        initialProps: { enabled: true },
        wrapper: ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>,
      },
    );
    await act(async () => {
      await flush();
    });
    expect(result.current.state).toBe("ready");
    expect(result.current.requests[0].title).toBe("Strict feed");
    expect(readCalls).toBe(1);
  });

  it("forwards only issued tuples for review, exactly once", async () => {
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => feedFor("Boundary review brief"),
      open_terminal_sharing_request: () => ({
        schema: "mastermind.terminal_sharing_handoff.v1",
        request_ref: REQUEST_REF,
        revision: 1,
        delivery_id: DELIVERY_ID,
        outcome: "HANDOFF_REQUESTED",
      }),
    }));
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host, enabled),
      { initialProps: { enabled: false } },
    );
    await act(async () => {
      rerender({ enabled: true });
      await flush();
    });
    const view = result.current.requests[0];
    await act(async () => {
      await expect(result.current.onReview(view)).resolves.toBeUndefined();
    });
    const openCalls = native.invoke.mock.calls.filter(
      ([command]) => command === "open_terminal_sharing_request",
    );
    expect(openCalls).toHaveLength(1);
    expect(openCalls[0]?.[1]).toEqual({ selection: {
      request_ref: REQUEST_REF,
      revision: 1,
      delivery_id: DELIVERY_ID,
      content_sha256: CONTENT,
    } });

    // Unknown tuples never mint a request; the issued tuple cannot replay.
    await act(async () => {
      await result.current.onReview({ ...view, requestRef: OTHER_REQUEST_REF });
      await expect(result.current.onReview(view)).rejects.toThrow(CLOSED);
    });
    expect(
      native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"),
    ).toHaveLength(1);

    // After withdrawal the same view no longer resolves to anything.
    const statuses = [signedInStatus(5), signedOutStatus()];
    let statusCursor = 0;
    const { host: host2, native: native2 } = await createHost(byCommand({
      terminal_session_status: () => statuses[Math.min(statusCursor++, statuses.length - 1)],
      read_terminal_sharing_requests: () => feedFor("Boundary review brief"),
    }));
    const second = renderHook(
      ({ enabled }: { enabled: boolean }) => useTerminalSharing(host2, enabled),
      { initialProps: { enabled: false } },
    );
    await act(async () => {
      second.rerender({ enabled: true });
      await flush();
    });
    await act(async () => {
      native2.emit();
      await flush();
    });
    expect(second.result.current.state).toBe("unavailable");
    await act(async () => {
      await second.result.current.onReview(view);
    });
    expect(
      native2.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"),
    ).toHaveLength(0);
  });
});
