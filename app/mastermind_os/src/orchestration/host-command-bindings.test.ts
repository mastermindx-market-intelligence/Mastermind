import { describe, expect, it, vi } from "vitest";
import type { CommandIntent } from "./operation-controller";
import {
  COMMAND_ROUTE_UNAVAILABLE,
  completeOrchestratorCommandBinding,
  intentMatchingKind,
  launchIntentFromBinding,
  messageIntentFromBinding,
  readCommandView,
  readOwnerContext,
  sessionMatchesSelection,
  stopIntentFromBinding,
  subscribeCommandView,
} from "./host-command-bindings";

const port = {
  context: () => ({ principalScope: "owner-a", generation: "gen-1" }),
  prepare: () => ({
    operationKey: "op-1",
    kind: "launch" as const,
    targetKey: "t",
  }),
  submit: async () => ({
    operationKey: "op-1",
    kind: "launch" as const,
    targetKey: "t",
    disposition: "accepted" as const,
  }),
  readOperation: async () => ({
    operationKey: "op-1",
    kind: "launch" as const,
    targetKey: "t",
    disposition: "accepted" as const,
  }),
};

const store = {
  read: async () => null,
  reserve: async () => ({ reserved: true as const }),
  clearIfEqual: async () => true,
};

const session = {
  sessionKey: "sess-1",
  title: "Session",
  messages: [{ id: "m1", role: "user" as const, text: "hi" }],
  observedAt: null,
  connection: "connected" as const,
  coverage: "COMPLETE",
  turnBusy: false,
  selection: { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
};

function completeBinding(overrides: Record<string, unknown> = {}) {
  return {
    port,
    store,
    getView: () => ({
      projects: [{ ref: "p1", label: "P1" }],
      profiles: [{ ref: "r1", label: "R1" }],
      session,
    }),
    subscribe: () => () => {},
    makeLaunchIntent: () =>
      ({
        kind: "launch",
        targetKey: "opaque-launch",
        payload: { goal: "g" },
      }) satisfies CommandIntent,
    makeMessageIntent: () =>
      ({
        kind: "message",
        targetKey: "opaque-session",
        payload: { text: "t" },
      }) satisfies CommandIntent,
    makeStopIntent: () =>
      ({
        kind: "stop",
        targetKey: "opaque-session",
        payload: {},
      }) satisfies CommandIntent,
    ...overrides,
  };
}

describe("completeOrchestratorCommandBinding", () => {
  it("accepts only the closed complete shape", () => {
    expect(completeOrchestratorCommandBinding(completeBinding())).not.toBeNull();
    expect(completeOrchestratorCommandBinding(undefined)).toBeNull();
    expect(completeOrchestratorCommandBinding(null)).toBeNull();
    expect(completeOrchestratorCommandBinding({})).toBeNull();
    expect(
      completeOrchestratorCommandBinding(
        completeBinding({ makeStopIntent: undefined }),
      ),
    ).toBeNull();
    expect(
      completeOrchestratorCommandBinding(
        completeBinding({
          port: { context: port.context, prepare: port.prepare },
        }),
      ),
    ).toBeNull();
    // Missing the atomic durability operations on the store is rejected.
    expect(
      completeOrchestratorCommandBinding(
        completeBinding({ store: { read: store.read } }),
      ),
    ).toBeNull();
    expect(
      completeOrchestratorCommandBinding(
        completeBinding({
          store: { read: store.read, reserve: store.reserve },
        }),
      ),
    ).toBeNull();
    expect(
      completeOrchestratorCommandBinding(
        completeBinding({
          store: {
            read: store.read,
            reserve: store.reserve,
            clearIfEqual: store.clearIfEqual,
            write: () => {},
          },
        }),
      ),
    ).toBeNull();
    expect(
      completeOrchestratorCommandBinding(
        completeBinding({
          store: {
            read: store.read,
            reserve: store.reserve,
            clearIfEqual: store.clearIfEqual,
            clear: () => {},
          },
        }),
      ),
    ).toBeNull();
  });

  it("does not invoke port or mappers while checking shape", () => {
    const prepare = vi.fn();
    const makeLaunchIntent = vi.fn();
    completeOrchestratorCommandBinding(
      completeBinding({
        port: { ...port, prepare },
        makeLaunchIntent,
      }),
    );
    expect(prepare).not.toHaveBeenCalled();
    expect(makeLaunchIntent).not.toHaveBeenCalled();
  });
});

describe("readOwnerContext", () => {
  it("requires both principalScope and generation from the owner", () => {
    expect(readOwnerContext(port)).toEqual({
      principalScope: "owner-a",
      generation: "gen-1",
    });
    expect(readOwnerContext({ context: () => null })).toBeNull();
    expect(
      readOwnerContext({
        context: () => ({ principalScope: "owner-a", generation: "" }),
      }),
    ).toBeNull();
    expect(
      readOwnerContext({
        context: () => {
          throw new Error("secret");
        },
      }),
    ).toBeNull();
  });
});

describe("readCommandView", () => {
  it("returns empty view on throw or malformed payload", () => {
    const empty = { projects: [], profiles: [], session: null };
    expect(
      readCommandView(
        completeBinding({
          getView: () => {
            throw new Error("producer secret");
          },
        }) as never,
      ),
    ).toEqual(empty);
    expect(
      readCommandView(completeBinding({ getView: () => ({}) }) as never),
    ).toEqual(empty);
    expect(
      readCommandView(
        completeBinding({
          getView: () => ({
            projects: [{ ref: "p1" }],
            profiles: [{ ref: "r1", label: "R1" }],
            session: null,
          }),
        }) as never,
      ),
    ).toEqual(empty);
  });

  it("keeps a normalized session selection and drops callback flags", () => {
    const view = readCommandView(
      completeBinding({
        getView: () => ({
          projects: [{ ref: "p1", label: "P1" }],
          profiles: [{ ref: "r1", label: "R1" }],
          session: {
            ...session,
            sending: true,
            submitting: true,
            checking: true,
          },
        }),
      }) as never,
    );
    expect(view.session?.selection).toEqual({
      workRef: "WS:ALPHA",
      rootJobId: "JOB-A",
    });
    expect(view.session).not.toHaveProperty("sending");
    expect(view.session).not.toHaveProperty("submitting");
  });
});

describe("sessionMatchesSelection", () => {
  it("matches only the exact selected workRef/rootJobId pair", () => {
    const view = readCommandView(completeBinding() as never);
    expect(
      sessionMatchesSelection(view.session, {
        workRef: "WS:ALPHA",
        rootJobId: "JOB-A",
      }),
    ).toBe(true);
    expect(
      sessionMatchesSelection(view.session, {
        workRef: "WS:BETA",
        rootJobId: "JOB-A",
      }),
    ).toBe(false);
    expect(sessionMatchesSelection(view.session, null)).toBe(false);
  });
});

describe("intent mappers", () => {
  it("fails locally on kind mismatch, null, and thrown mapper text", () => {
    expect(intentMatchingKind(null, "launch")).toBeNull();
    expect(
      intentMatchingKind(
        { kind: "message", payload: {}, targetKey: "x" },
        "launch",
      ),
    ).toBeNull();
    const binding = completeBinding({
      makeLaunchIntent: () => ({
        kind: "stop",
        payload: {},
        targetKey: "x",
      }),
      makeMessageIntent: () => {
        throw new Error("mapper secret");
      },
      makeStopIntent: () => null,
    });
    expect(
      launchIntentFromBinding(binding as never, {
        goal: "g",
        projectRef: "p",
        profileRef: "r",
      }),
    ).toBeNull();
    expect(messageIntentFromBinding(binding as never, "sess-1", "hi")).toBeNull();
    expect(stopIntentFromBinding(binding as never, "sess-1")).toBeNull();
  });
});

describe("subscribeCommandView", () => {
  it("is rerender-only and swallows producer throws", () => {
    const listener = vi.fn();
    expect(
      subscribeCommandView(
        completeBinding({
          subscribe: () => {
            throw new Error("subscribe secret");
          },
        }) as never,
        listener,
      ),
    ).toBeTypeOf("function");
    expect(COMMAND_ROUTE_UNAVAILABLE).toBe("COMMAND_ROUTE_UNAVAILABLE");
  });
});