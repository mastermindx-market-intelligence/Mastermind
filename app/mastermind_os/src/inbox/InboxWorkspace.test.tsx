// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InboxWorkspace } from "./InboxWorkspace";
import { decodeMission } from "../mission";
import { projectOffice, type OfficeInput, type ProjectionContext } from "../meta-ceo/projection";
import {
  createLazyTerminalSharingHost,
  createTerminalSharingHost,
  type TerminalSharingHost,
  type TerminalSharingInvoke,
  type TerminalSharingListen,
} from "../terminal/terminal-sharing-host";
import missionFixture from "../fixtures/mission-v2-current-128c46f6.json";
import feedFixture from "./fixtures/terminal-sharing-request-feed.json";

afterEach(cleanup);

// Seam: only the native Terminal invoke/listen ports are inert test doubles at
// the host boundary. The host, the sharing hook, BriefSharingInbox,
// TerminalSharingInbox and InboxWorkspace under test are the real accepted
// implementations, and the feed body is the supplied accepted fixture.
const NATIVE_COMMANDS = [
  "terminal_session_status",
  "terminal_sign_in",
  "terminal_disconnect",
  "read_terminal_sharing_requests",
  "open_terminal_sharing_request",
];

const feedRequest = feedFixture.requests[0]!;
const REQUEST_REF = feedRequest.request_ref;
const DELIVERY_ID = feedRequest.delivery.delivery_id;
const CONTENT = feedRequest.delivery.content_sha256;
const FEED_TITLE = feedRequest.delivery.title;
const PRINCIPAL = feedFixture.viewer.principal_scope;
const SESSION = feedFixture.viewer.session_scope;
const ALT_PRINCIPAL = "8a".repeat(32);
const ALT_SESSION = "9b".repeat(32);

const context: ProjectionContext = {
  authGeneration: 3, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: "session:one", bindingGeneration: 4,
  revisions: { mission: "mission:1", programs: null, result: null, conversation: null },
};

function input(): OfficeInput {
  const raw = structuredClone(missionFixture);
  raw.read_state = { ...raw.read_state, state: "CURRENT", reason_codes: [] };
  const value = decodeMission(raw, context.selection!)!;
  value.principal.owed_turn = { seat: "chairman", reason: "Decide the exact release scope.",
    source_refs: [{ owner: "EXECUTIVE_OS", ref: "private:attention-one", observed_at: "2026-10-04T07:00:00Z", freshness: "current" }] };
  return { programs: null, result: null, conversation: null, mission: { context,
    source: { owner: "EXECUTIVE_OS", ref: "private:mission-one", revision: "mission:1", observed_at: "2026-10-04T07:00:01Z", state: "CURRENT", coverage: "COMPLETE" }, value } };
}

function nextContext(change: "auth" | "target" | "revision" | "session"): ProjectionContext {
  const next = structuredClone(context);
  if (change === "auth") next.authGeneration += 1;
  if (change === "target") next.selection = { workRef: "WS:TWO", rootJobId: "JOB-2" };
  if (change === "revision") next.revisions = { ...next.revisions, mission: "mission:2" };
  if (change === "session") next.sessionRef = "session:two";
  return next;
}

function signedInStatus(generation = 5): Record<string, unknown> {
  return {
    state: "SIGNED_IN", generation, reason: null, available: true,
    principal_scope: PRINCIPAL, session_scope: SESSION,
  };
}

function altSignedInStatus(generation = 5): Record<string, unknown> {
  return { ...signedInStatus(generation), principal_scope: ALT_PRINCIPAL, session_scope: ALT_SESSION };
}

function signedOutStatus(): Record<string, unknown> {
  return {
    state: "SIGNED_OUT", generation: 7, reason: null, available: false,
    principal_scope: null, session_scope: null,
  };
}

/** The supplied accepted feed with only the viewer scope and title shifted. */
function scopedFeed(principalScope: string, sessionScope: string, title: string): Record<string, unknown> {
  const feed = structuredClone(feedFixture) as Record<string, unknown>;
  const viewer = structuredClone(feedFixture.viewer) as Record<string, unknown>;
  viewer.principal_scope = principalScope;
  viewer.session_scope = sessionScope;
  feed.viewer = viewer;
  const requests = structuredClone(feedFixture.requests) as Array<Record<string, unknown>>;
  const delivery = structuredClone(feedRequest.delivery) as Record<string, unknown>;
  delivery.title = title;
  requests[0]!["delivery"] = delivery;
  feed.requests = requests;
  return feed;
}

function handoffReceipt(): Record<string, unknown> {
  return {
    schema: "mastermind.terminal_sharing_handoff.v1",
    request_ref: REQUEST_REF, revision: 1,
    delivery_id: DELIVERY_ID, outcome: "HANDOFF_REQUESTED",
  };
}

type Responder = (args?: Record<string, unknown>) => unknown;

function byCommand(map: Record<string, Responder>): (command: string, args?: Record<string, unknown>) => unknown {
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
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const flush = async (): Promise<void> => {
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const settle = async (): Promise<void> => {
  for (let turns = 0; turns < 6; turns++) await flush();
};

async function createHost(
  respond: (command: string, args?: Record<string, unknown>) => unknown,
): Promise<{ host: TerminalSharingHost; native: ReturnType<typeof fakeNative> }> {
  const native = fakeNative(respond);
  const host = await createTerminalSharingHost(native.invoke, native.listen);
  return { host, native };
}

function readCalls(native: ReturnType<typeof fakeNative>): number {
  return native.invoke.mock.calls.filter(([command]) => command === "read_terminal_sharing_requests").length;
}

function openCalls(native: ReturnType<typeof fakeNative>) {
  return native.invoke.mock.calls.filter(([command]) => command === "open_terminal_sharing_request");
}

describe("InboxWorkspace", () => {
  it("does not carry a prior host's handoff message into a replacement capability with identical public identity", async () => {
    const responder = byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => structuredClone(feedFixture),
      open_terminal_sharing_request: () => handoffReceipt(),
    });
    const a = await createHost(responder), b = await createHost(responder);
    try {
      const view = render(<InboxWorkspace projection={projectOffice(input(), context)} locale="en" terminalHost={a.host}/>);
      await act(settle);
      fireEvent.click(screen.getByRole("button", {name:"Continue in Terminal"}));
      await act(settle);
      expect(screen.getByText("Continue in Terminal to review this request.")).toBeTruthy();
      view.rerender(<InboxWorkspace projection={projectOffice(input(), context)} locale="en" terminalHost={b.host}/>);
      await act(settle);
      expect(screen.queryByText("Continue in Terminal to review this request.")).toBeNull();
      expect((screen.getByRole("button", {name:"Continue in Terminal"}) as HTMLButtonElement).disabled).toBe(false);
      expect(openCalls(a.native)).toHaveLength(1);
      expect(openCalls(b.native)).toHaveLength(0);
    } finally {a.host.dispose(); b.host.dispose();}
  });
  it("mounts the Office Inbox beside a stable Terminal sibling and hands off the exact issued tuple once", async () => {
    let reads = 0;
    const native = fakeNative(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => { reads += 1; return structuredClone(feedFixture); },
      open_terminal_sharing_request: () => handoffReceipt(),
    }));
    const lazy = createLazyTerminalSharingHost(native.invoke, native.listen);
    try {
      const navigate = vi.fn();
      render(<InboxWorkspace projection={projectOffice(input(), context)}
        onNavigateMission={navigate} locale="en" terminalHost={lazy} />);
      // The Office Inbox renders unchanged, independent of Terminal availability.
      fireEvent.click(screen.getByText("Mission owner context", {exact:true}));
      expect(screen.getByRole("region", { name: "Needs you" }).textContent)
        .toContain("Decide the exact release scope.");
      expect(screen.getByRole("region", { name: "Terminal brief requests" })).toBeTruthy();

      await act(settle);
      expect(reads).toBe(1);
      expect(screen.getByText(FEED_TITLE)).toBeTruthy();

      // Review resolves the rendered view to the host's own issued tuple.
      fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
      await act(settle);
      const open = openCalls(native);
      expect(open).toHaveLength(1);
      expect(open[0]![1]).toEqual({ selection: {
        request_ref: REQUEST_REF, revision: 1,
        delivery_id: DELIVERY_ID, content_sha256: CONTENT,
      } });
      // The closed receipt is the whole outcome: a requested handoff, never a share claim.
      expect(screen.getByText("Continue in Terminal to review this request.")).toBeTruthy();
      expect(screen.getByText("Sharing has not changed.")).toBeTruthy();
      expect(document.body.textContent).not.toContain("Shared");
      expect((screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement).disabled).toBe(true);
      expect(reads).toBe(1);
      expect(native.invoke.mock.calls.every(([command]) => NATIVE_COMMANDS.includes(command))).toBe(true);
      expect(native.unlisten).not.toHaveBeenCalled();

      // The Office side keeps its own navigation semantics.
      fireEvent.click(screen.getByRole("button", { name: "Open project" }));
      expect(navigate).toHaveBeenCalledExactlyOnceWith(context.selection, "current");
    } finally {
      lazy.dispose();
    }
  });

  it("never re-reads or resets a pending Terminal attempt on unrelated Mission changes", async () => {
    let reads = 0;
    const officeInput = input();
    const pendingOpen = deferred<Record<string, unknown>>();
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => { reads += 1; return structuredClone(feedFixture); },
      open_terminal_sharing_request: () => pendingOpen.promise,
    }));
    const view = render(<InboxWorkspace projection={projectOffice(officeInput, context)}
      locale="en" terminalHost={host} />);
    await act(settle);
    expect(reads).toBe(1);

    // An in-flight review attempt stays pending.
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    await act(flush);
    expect(screen.getByText("Opening Terminal…")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Continue in Terminal" }) as HTMLButtonElement).disabled).toBe(true);

    // Office-side private evidence is open when the unrelated Mission changes arrive.
    fireEvent.click(screen.getByText("Mission owner context", {exact:true}));
    fireEvent.click(screen.getByRole("button", { name: "View evidence" }));
    expect(screen.getByRole("region", { name: "Attention evidence" })).toBeTruthy();

    for (const change of ["auth", "target", "revision", "session"] as const) {
      view.rerender(<InboxWorkspace projection={projectOffice(officeInput, nextContext(change))}
        locale="en" terminalHost={host} />);
      // Existing Office keyed semantics still clear private inspection synchronously…
      expect(screen.queryByRole("region", { name: "Attention evidence" })).toBeNull();
      // …while the stable Terminal sibling keeps its rows, its pending attempt and its read.
      expect(screen.getByText(FEED_TITLE)).toBeTruthy();
      expect(screen.getByText("Opening Terminal…")).toBeTruthy();
      await act(flush);
      expect(reads).toBe(1);
      expect(openCalls(native)).toHaveLength(1);
    }

    // The surviving attempt still resolves against the original issued tuple.
    await act(async () => {
      pendingOpen.resolve(handoffReceipt());
      await settle();
    });
    expect(screen.getByText("Continue in Terminal to review this request.")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Shared");
    expect(reads).toBe(1);
    expect(openCalls(native)).toHaveLength(1);
  });

  it("withdraws Terminal rows in the same render when the Terminal epoch is replaced, before the late read resolves", async () => {
    let reads = 0;
    const pendingSix = deferred<Record<string, unknown>>();
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => {
        reads += 1;
        return reads === 1 ? structuredClone(feedFixture) : pendingSix.promise;
      },
    }));
    render(<InboxWorkspace projection={projectOffice(input(), context)}
      locale="en" terminalHost={host} />);
    await act(settle);
    expect(screen.getByText(FEED_TITLE)).toBeTruthy();
    expect(reads).toBe(1);

    // The host's own distinct-epoch status event arrives.
    act(() => { native.emit(signedInStatus(6)); });
    // Withdrawn in the same render that observed the replacement epoch: the old
    // epoch's rows are gone before the replacement read has resolved.
    expect(screen.queryByText(FEED_TITLE)).toBeNull();
    expect(screen.queryByText("Replacement epoch brief")).toBeNull();
    await act(settle);
    expect(reads).toBe(2);
    expect(screen.getByText("Loading brief-sharing requests…")).toBeTruthy();

    await act(async () => {
      pendingSix.resolve(scopedFeed(PRINCIPAL, SESSION, "Replacement epoch brief"));
      await settle();
    });
    expect(screen.getByText("Replacement epoch brief")).toBeTruthy();
    expect(screen.queryByText(FEED_TITLE)).toBeNull();
    expect(reads).toBe(2);
  });

  it("withdraws prior-host rows in the same render when the host is replaced while reusing the same numeric epoch", async () => {
    const officeInput = input();
    const pendingB = deferred<Record<string, unknown>>();
    const a = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => structuredClone(feedFixture),
    }));
    let bReads = 0;
    const b = await createHost(byCommand({
      terminal_session_status: () => altSignedInStatus(5), // same epoch, different own viewer
      read_terminal_sharing_requests: () => { bReads += 1; return pendingB.promise; },
    }));
    const view = render(<InboxWorkspace projection={projectOffice(officeInput, context)}
      locale="en" terminalHost={a.host} />);
    await act(settle);
    expect(screen.getByText(FEED_TITLE)).toBeTruthy();
    expect(readCalls(a.native)).toBe(1);

    // Replace the workspace host with one reporting the SAME numeric epoch.
    view.rerender(<InboxWorkspace projection={projectOffice(officeInput, context)}
      locale="en" terminalHost={b.host} />);
    // Prior-host rows are withdrawn in that same render, before host B's late
    // promise resolves, and host A is never consulted again.
    expect(screen.queryByText(FEED_TITLE)).toBeNull();
    expect(readCalls(a.native)).toBe(1);
    expect(bReads).toBeLessThanOrEqual(1);

    await act(settle);
    expect(bReads).toBe(1);
    await act(async () => {
      pendingB.resolve(scopedFeed(ALT_PRINCIPAL, ALT_SESSION, "Replacement owner brief"));
      await settle();
    });
    expect(screen.getByText("Replacement owner brief")).toBeTruthy();
    expect(screen.queryByText(FEED_TITLE)).toBeNull();
    expect(readCalls(a.native)).toBe(1);
  });

  it("keeps a signed-out Terminal empty and unavailable without borrowing workspace auth", async () => {
    let reads = 0;
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedOutStatus(),
      terminal_sign_in: () => signedInStatus(8),
      read_terminal_sharing_requests: () => { reads += 1; return structuredClone(feedFixture); },
    }));
    render(<InboxWorkspace projection={projectOffice(input(), context)}
      locale="en" terminalHost={host} />);
    await act(settle);
    // Signed out: explicit unavailable state, no rows, no read, no borrow.
    expect(screen.getByText("Requests are unavailable.")).toBeTruthy();
    expect(screen.queryByText(FEED_TITLE)).toBeNull();
    expect(reads).toBe(0);

    // The only connection affordance belongs to the distinct Terminal owner.
    fireEvent.click(screen.getByRole("button", { name: "Connect Terminal" }));
    await act(settle);
    // The Terminal's own sign-in produced its own epoch; only then does the feed activate.
    expect(screen.getByText(FEED_TITLE)).toBeTruthy();
    expect(reads).toBe(1);
    expect(native.invoke.mock.calls.every(([command]) => NATIVE_COMMANDS.includes(command))).toBe(true);
    expect(screen.getByText(
      "Terminal uses a separate connection. Workspace sign-in does not establish brief access.",
    )).toBeTruthy();
  });

  it("renders the Terminal sibling unavailable without a host and never fakes a connection", () => {
    render(<InboxWorkspace projection={projectOffice(input(), context)} locale="zh-CN" />);
    fireEvent.click(screen.getByText("任务负责人上下文", {exact:true}));
    expect(screen.getByRole("region", { name: "Needs you" }).textContent)
      .toContain("Decide the exact release scope.");
    expect(screen.getByRole("region", { name: "Terminal 简报请求" })).toBeTruthy();
    expect(screen.getByText("暂时无法加载请求。")).toBeTruthy();
    expect(screen.getByText("Terminal 使用独立的账户连接。工作区登录不代表已获得简报访问权限。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "连接 Terminal" })).toBeNull();
    expect(screen.queryByText(FEED_TITLE)).toBeNull();
  });

  it("refuses an outcome other than HANDOFF_REQUESTED without ever claiming a share", async () => {
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => structuredClone(feedFixture),
      open_terminal_sharing_request: () => ({
        schema: "mastermind.terminal_sharing_handoff.v1",
        request_ref: REQUEST_REF, revision: 1,
        delivery_id: DELIVERY_ID,
        outcome: "SHARED", // a closed Shared claim is refused outright
      }),
    }));
    render(<InboxWorkspace projection={projectOffice(input(), context)}
      locale="en" terminalHost={host} />);
    await act(settle);
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    await act(settle);
    expect(screen.getByText("Terminal could not be confirmed open.")).toBeTruthy();
    expect(screen.getByText("Check the original Terminal page.")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Shared");
    expect(openCalls(native)).toHaveLength(1);
    // The retained refusal is never replayed; the per-attempt latch holds.
    fireEvent.click(screen.getByRole("button", { name: "Continue in Terminal" }));
    await act(flush);
    expect(openCalls(native)).toHaveLength(1);
    expect(screen.getByText("Terminal could not be confirmed open.")).toBeTruthy();
  });

  it("invalidates an in-flight read on unmount and re-activates the current owner on return", async () => {
    let reads = 0;
    const pending = deferred<Record<string, unknown>>();
    const { host, native } = await createHost(byCommand({
      terminal_session_status: () => signedInStatus(5),
      read_terminal_sharing_requests: () => {
        reads += 1;
        return reads === 1 ? pending.promise
          : scopedFeed(PRINCIPAL, SESSION, "Returned owner brief");
      },
    }));
    const view = render(<InboxWorkspace projection={projectOffice(input(), context)}
      locale="en" terminalHost={host} />);
    await act(settle);
    expect(reads).toBe(1);

    // Departure: the Inbox unmounts while the read is still in flight.
    view.unmount();
    const callsAtDeparture = native.invoke.mock.calls.length;
    await act(async () => {
      pending.resolve(structuredClone(feedFixture)); // late completion
      await settle();
    });
    // The late completion starts nothing and re-opens nothing.
    expect(native.invoke.mock.calls.length).toBe(callsAtDeparture);
    expect(reads).toBe(1);

    // Return: the current owner host is activated again under its own fresh read.
    render(<InboxWorkspace projection={projectOffice(input(), context)}
      locale="en" terminalHost={host} />);
    await act(settle);
    expect(reads).toBe(2);
    expect(screen.getByText("Returned owner brief")).toBeTruthy();
  });
});
