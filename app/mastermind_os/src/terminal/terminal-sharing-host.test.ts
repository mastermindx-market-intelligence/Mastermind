import { describe, expect, it, vi } from "vitest";
import {
  createTerminalSharingHost,
  type TerminalSharingInvoke,
  type TerminalSharingListen,
} from "./terminal-sharing-host";
import { TERMINAL_SHARING_UNAVAILABLE } from "./terminal-sharing-contract";

const PRINCIPAL = "1a".repeat(32);
const SESSION = "2b".repeat(32);
const OTHER_PRINCIPAL = "55".repeat(32);
const CONTENT = "3a".repeat(32);
const REQUEST_REF = "0193f2c4-7a1b-7c2d-8e3f-4a5b6c7d8e9f";
const DELIVERY_ID = "0f8e7d6c-5b4a-6c3d-9e2f-1a2b3c4d5e6f";
const TEAM_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
const ISSUED_AT = "2026-11-04T10:15:30.123456Z";
const OBSERVED_AT = "2026-11-04T10:15:30.654321Z";
const SLOT = "2026-11-04";

const CLOSED = new RegExp(`^${TERMINAL_SHARING_UNAVAILABLE}$`);
const HANDOFF_RECEIPT = {
  schema: "mastermind.terminal_sharing_handoff.v1",
  request_ref: REQUEST_REF,
  revision: 1,
  delivery_id: DELIVERY_ID,
  outcome: "HANDOFF_REQUESTED",
};

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

function validRequest(): Record<string, unknown> {
  return {
    request_ref: REQUEST_REF,
    revision: 1,
    issued_at: ISSUED_AT,
    delivery: {
      delivery_id: DELIVERY_ID,
      content_sha256: CONTENT,
      title: "Boundary review brief",
      slot_asof: SLOT,
      artifact_asof: null,
    },
    audience: {
      team_id: TEAM_ID,
      name: "Boundary owners",
      member_count: 3,
      membership_policy: "DYNAMIC_TEAM_MEMBERSHIP",
    },
    review: { request_ref: REQUEST_REF, revision: 1, delivery_id: DELIVERY_ID },
  };
}

function validFeed(
  viewer: Record<string, unknown> = { principal_scope: PRINCIPAL, session_scope: SESSION },
): Record<string, unknown> {
  return {
    schema: "mastermind.terminal_sharing_request_feed.v1",
    viewer,
    source: {
      owner: "TERMINAL_BRIEF_DELIVERY",
      scope: "OWNED_EXPLICIT_SHARING_REQUESTS",
      observed_at: OBSERVED_AT,
    },
    coverage: { state: "COMPLETE_WITHIN_SCOPE", reason_codes: [] },
    requests: [validRequest()],
  };
}

function cloneIssued(issued: Record<string, unknown>): Record<string, unknown> {
  const source = issued as {
    delivery: Record<string, unknown>;
    audience: Record<string, unknown>;
    review: Record<string, unknown>;
  };
  return {
    ...issued,
    delivery: { ...source.delivery },
    audience: { ...source.audience },
    review: { ...source.review },
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

const tick = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

function sequencedStatuses(statuses: Array<Record<string, unknown>>) {
  let cursor = 0;
  return () => statuses[Math.min(cursor++, statuses.length - 1)];
}

describe("terminal sharing host composition", () => {
  it("subscribes to the session event before reading status, with a race guard", async () => {
    const statuses = [signedInStatus(5), signedInStatus(5), signedInStatus(6), signedOutStatus()];
    const native = fakeNative(byCommand({
      terminal_session_status: sequencedStatuses(statuses),
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    expect(native.listen.mock.calls).toEqual([["terminal-session-changed", expect.any(Function)]]);
    expect(native.invoke.mock.calls).toEqual([["terminal_session_status"]]);
    expect(host.getState()).toEqual(signedInStatus(5));

    const listener = vi.fn();
    host.subscribe(listener);

    // Event landing while the status stays identical: no notification.
    native.emit();
    await tick();
    expect(listener).not.toHaveBeenCalled();
    expect(host.getState()).toEqual(signedInStatus(5));

    // A stopped listener stays silent through a real change.
    const stoppedListener = vi.fn();
    const stop = host.subscribe(stoppedListener);
    stop();

    // New epoch: republished once, never the raw event payload.
    native.emit();
    await tick();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenNthCalledWith(1, signedInStatus(6));
    expect(stoppedListener).not.toHaveBeenCalled();
    expect(host.getState()).toEqual(signedInStatus(6));

    // Sign-out event: republished, opaque scopes withheld.
    native.emit();
    await tick();
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenNthCalledWith(2, signedOutStatus());
    expect(host.getState()).toEqual(signedOutStatus());
  });

  it("connects and disconnects through explicit commands only, without returning grants", async () => {
    const native = fakeNative(byCommand({
      terminal_session_status: () => signedOutStatus(),
      terminal_sign_in: () => ({...signedOutStatus(),state:"SIGNING_IN",generation:8,reason:"SIGN_IN_STARTED"}),
      terminal_disconnect: () => ({...signedOutStatus(),generation:9,reason:"SIGNED_OUT_LOCAL"}),
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    expect(await host.connect()).toBeUndefined();
    expect(await host.disconnect()).toBeUndefined();
    expect(native.invoke.mock.calls.filter(([command]) => command === "terminal_sign_in"))
      .toEqual([["terminal_sign_in"]]);
    expect(native.invoke.mock.calls.filter(([command]) => command === "terminal_disconnect"))
      .toEqual([["terminal_disconnect"]]);
  });

  it("surfaces connect and construction failures as the closed code only", async () => {
    const native = fakeNative(byCommand({
      terminal_session_status: () => signedOutStatus(),
      terminal_sign_in: () => {
        throw new Error("synthetic-private-native-error");
      },
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    await expect(host.connect()).rejects.toThrow(CLOSED);

    await expect(
      createTerminalSharingHost(
        native.invoke,
        async () => {
          throw new Error("synthetic-private-listen-error");
        },
      ),
    ).rejects.toThrow(CLOSED);

    const failingStatus = fakeNative(
      byCommand({
        terminal_session_status: () => {
          throw new Error("synthetic-private-status-error");
        },
      }),
    );
    await expect(
      createTerminalSharingHost(failingStatus.invoke, failingStatus.listen),
    ).rejects.toThrow(CLOSED);
    expect(failingStatus.unlisten).toHaveBeenCalledTimes(1);
  });

  it("reads the bounded feed only under the current own signed-in snapshot", async () => {
    const native = fakeNative(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => validFeed(),
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    const result = await host.readRequests({ signal: new AbortController().signal });
    expect(result).not.toBeNull();
    expect(result?.generation).toBe(5);
    expect(result?.feed.viewer).toEqual({ principal_scope: PRINCIPAL, session_scope: SESSION });
    expect(result?.feed.requests[0]?.request_ref).toBe(REQUEST_REF);
    expect(Object.isFrozen(result?.feed)).toBe(true);
    expect(Object.isFrozen(result?.feed.requests[0])).toBe(true);
    expect(native.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"))
      .toEqual([["read_terminal_sharing_requests"]]);

    const wrongViewer = validFeed({ principal_scope: OTHER_PRINCIPAL, session_scope: SESSION });
    const wrongNative = fakeNative(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => wrongViewer,
    }));
    const wrongHost = await createTerminalSharingHost(wrongNative.invoke, wrongNative.listen);
    await expect(
      wrongHost.readRequests({ signal: new AbortController().signal }),
    ).rejects.toThrow(CLOSED);
    expect(
      wrongNative.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"),
    ).toHaveLength(1);
  });

  it("never borrows auth for a read while signed out and never retries invalid responses", async () => {
    const native = fakeNative(byCommand({
      terminal_session_status: () => signedOutStatus(),
      read_terminal_sharing_requests: () => validFeed(),
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    await expect(host.readRequests({ signal: new AbortController().signal })).rejects.toThrow(CLOSED);
    expect(
      native.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"),
    ).toHaveLength(0);

    // A pre-aborted read under a signed-in snapshot drops without a native call.
    const signedInNative = fakeNative(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => validFeed(),
    }));
    const signedInHost = await createTerminalSharingHost(signedInNative.invoke, signedInNative.listen);
    const controller = new AbortController();
    controller.abort();
    await expect(signedInHost.readRequests({ signal: controller.signal })).resolves.toBeNull();
    expect(
      signedInNative.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"),
    ).toHaveLength(0);

    let readCalls = 0;
    const statuses = [signedInStatus(5), { malformed: true }, signedInStatus(5)];
    const invalidNative = fakeNative(byCommand({
      terminal_session_status: sequencedStatuses(statuses),
      read_terminal_sharing_requests: () => {
        readCalls += 1;
        return readCalls === 1 ? { malformed: true } : { ...validFeed(), requests: [] };
      },
    }));
    const invalidHost = await createTerminalSharingHost(invalidNative.invoke, invalidNative.listen);
    await expect(
      invalidHost.readRequests({ signal: new AbortController().signal }),
    ).rejects.toThrow(CLOSED);
    expect(
      invalidNative.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"),
    ).toHaveLength(1);
    // A later explicit read is a new caller decision, never an internal retry.
    invalidNative.emit();
    await tick();
    const result = await invalidHost.readRequests({ signal: new AbortController().signal });
    expect(result?.feed.requests).toHaveLength(0);
    expect(
      invalidNative.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"),
    ).toHaveLength(2);
  });

  it("drops aborted, post-logout and cross-generation reads", async () => {
    const pendings: Array<{ promise: Promise<Record<string, unknown>>; resolve: (value: Record<string, unknown>) => void }> = [];
    const statuses = [
      signedInStatus(5),
      {...signedOutStatus(),generation:6},
      signedInStatus(7),
      signedInStatus(8),
    ];
    const native = fakeNative(byCommand({
      terminal_session_status: sequencedStatuses(statuses),
      read_terminal_sharing_requests: () => {
        const pending = deferred<Record<string, unknown>>();
        pendings.push(pending);
        return pending.promise;
      },
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    expect(pendings).toHaveLength(0);

    const abortedController = new AbortController();
    const abortedRead = host.readRequests({ signal: abortedController.signal });
    abortedController.abort();
    pendings[0].resolve(validFeed());
    await expect(abortedRead).resolves.toBeNull();

    const logoutRead = host.readRequests({ signal: new AbortController().signal });
    await tick();
    native.emit();
    await tick();
    pendings[1].resolve(validFeed());
    await expect(logoutRead).resolves.toBeNull();

    // Return to a signed-in snapshot under a new epoch, then move the epoch
    // again while the read is in flight: the result drops, never replays.
    native.emit();
    await tick();
    const epochRead = host.readRequests({ signal: new AbortController().signal });
    await tick();
    native.emit();
    await tick();
    pendings[2].resolve(validFeed());
    await expect(epochRead).resolves.toBeNull();
    expect(
      native.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests"),
    ).toHaveLength(3);
  });

  it("dispose unsubscribes, fences pending work and refuses later calls", async () => {
    const pending = deferred<Record<string, unknown>>();
    const native = fakeNative(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => pending.promise,
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    const inFlight = host.readRequests({ signal: new AbortController().signal });
    host.dispose();
    expect(native.unlisten).toHaveBeenCalledTimes(1);
    pending.resolve(validFeed());
    await expect(inFlight).resolves.toBeNull();
    await expect(host.readRequests({ signal: new AbortController().signal })).rejects.toThrow(CLOSED);
    await expect(host.connect()).rejects.toThrow(CLOSED);
    await expect(host.disconnect()).rejects.toThrow(CLOSED);
    host.dispose();
    expect(native.unlisten).toHaveBeenCalledTimes(1);
    expect(
      native.invoke.mock.calls.filter(([command]) =>
        ["terminal_session_status", "read_terminal_sharing_requests"].includes(command),
      ),
    ).toHaveLength(2);
  });
});

describe("terminal sharing host review", () => {
  async function hostWithFeed(options: {
    open?: Responder;
    statuses?: Array<Record<string, unknown>>;
  } = {}) {
    const native = fakeNative(byCommand({
      terminal_session_status: sequencedStatuses(options.statuses ?? [signedInStatus(5)]),
      read_terminal_sharing_requests: () => validFeed(),
      open_terminal_sharing_request: options.open ?? (() => HANDOFF_RECEIPT),
    }));
    const host = await createTerminalSharingHost(native.invoke, native.listen);
    const read = await host.readRequests({ signal: new AbortController().signal });
    if (read === null) throw new Error("fixture read was dropped");
    return { host, native, issued: read.feed.requests[0] };
  }

  it("forwards the exact tuple once and decodes the matching receipt", async () => {
    const { host, native, issued } = await hostWithFeed();
    expect(await host.reviewRequest(issued)).toEqual(HANDOFF_RECEIPT);
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
    await expect(host.reviewRequest(issued)).rejects.toThrow(CLOSED);
    expect(native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request")).toHaveLength(1);
  });

  it("refuses forged clones and foreign objects without a native call", async () => {
    const { host, native, issued } = await hostWithFeed();
    await expect(host.reviewRequest(cloneIssued(issued as unknown as Record<string, unknown>) as never)).rejects.toThrow(CLOSED);
    await expect(
      host.reviewRequest({
        request_ref: REQUEST_REF,
        revision: 1,
        issued_at: ISSUED_AT,
        delivery: {
          delivery_id: DELIVERY_ID,
          content_sha256: CONTENT,
          title: "Boundary review brief",
          slot_asof: SLOT,
          artifact_asof: null,
        },
        audience: {
          team_id: TEAM_ID,
          name: "Boundary owners",
          member_count: 3,
          membership_policy: "DYNAMIC_TEAM_MEMBERSHIP",
        },
        review: { request_ref: REQUEST_REF, revision: 1, delivery_id: DELIVERY_ID },
      } as never),
    ).rejects.toThrow(CLOSED);
    await expect(host.reviewRequest(null as never)).rejects.toThrow(CLOSED);
    expect(native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"))
      .toHaveLength(0);
    // The genuinely issued request still reviews exactly once.
    await expect(host.reviewRequest(issued)).resolves.toEqual(HANDOFF_RECEIPT);
    expect(native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"))
      .toHaveLength(1);
  });

  it("retains rejected and malformed outcomes without replaying them", async () => {
    const outcomes: Array<Responder> = [
      () => {
        throw new Error("synthetic-private-native-error");
      },
      () => ({ ...HANDOFF_RECEIPT, outcome: "Shared" }),
      () => ({ ...HANDOFF_RECEIPT, schema: "mastermind.terminal_navigation.v1" }),
      () => ({ ...HANDOFF_RECEIPT, request_ref: DELIVERY_ID }),
      () => ({ ...HANDOFF_RECEIPT, delivery_id: REQUEST_REF }),
      () => ({ ...HANDOFF_RECEIPT, revision: 2 }),
      () => ({ ...HANDOFF_RECEIPT, grant: "borrowed" }),
      () => ({
        schema: "mastermind.terminal_sharing_handoff.v1",
        request_ref: REQUEST_REF,
        revision: 1,
        delivery_id: DELIVERY_ID,
      }),
    ];
    for (const outcome of outcomes) {
      const { host, native, issued } = await hostWithFeed({ open: outcome });
      await expect(host.reviewRequest(issued)).rejects.toThrow(CLOSED);
      await expect(host.reviewRequest(issued)).rejects.toThrow(CLOSED);
      expect(
        native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"),
      ).toHaveLength(1);
    }
  });

  it("guards review by the current epoch and signed-in snapshot", async () => {
    const moved = await hostWithFeed({ statuses: [signedInStatus(5), signedInStatus(6)] });
    moved.native.emit();
    await tick();
    await expect(moved.host.reviewRequest(moved.issued)).rejects.toThrow(CLOSED);
    expect(
      moved.native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"),
    ).toHaveLength(0);

    const logout = await hostWithFeed({ statuses: [signedInStatus(5), signedOutStatus()] });
    logout.native.emit();
    await tick();
    await expect(logout.host.reviewRequest(logout.issued)).rejects.toThrow(CLOSED);
    expect(
      logout.native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request"),
    ).toHaveLength(0);
  });
});
