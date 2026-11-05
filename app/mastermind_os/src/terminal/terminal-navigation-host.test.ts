import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient, type RawClient } from "../host";

const out = { status: "signed_out" as const, reason: null, acquisition: false, content: false };
const receipt = {
  schema: "mastermind.terminal_navigation.v1",
  destination: "TERMINAL_BRIEFS",
  outcome: "HANDOFF_REQUESTED",
};

function invokeFor(open: () => unknown) {
  return vi.fn(async (command: string, _args?: Record<string, unknown>) => {
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "auth_status") return out;
    if (command === "open_terminal_briefs") return open();
    throw new Error("unexpected command");
  });
}

describe("fixed Terminal host composition", () => {
  it("binds actual native client to zero-input navigation without borrowing a private grant", async () => {
    const invoke = invokeFor(() => receipt);
    const client = await createNativeClient(invoke as never, async () => () => {});
    const host = bindMissionHost(client);
    expect(host.auth!.getState()).toEqual(out);
    expect(await host.openTerminalBriefs!()).toEqual(receipt);
    expect(invoke.mock.calls).toEqual([
      ["executive_auth_status"], ["auth_status"], ["open_terminal_briefs"],
    ]);
  });

  it("keeps older and web clients without an actual port unavailable", () => {
    const client: RawClient = {
      getState: () => out, subscribe: () => () => {},
      signIn: async () => {}, signOut: async () => {},
      readPrograms: async () => ({}), readMission: async () => ({}),
      readWork: async () => ({}), readCurrentWindow: async () => ({}),
    };
    expect(bindMissionHost(client).openTerminalBriefs).toBeUndefined();
  });

  it.each(["rejected", "malformed"])("withholds %s native outcome and never replays navigation", async (mode) => {
    const invoke = invokeFor(() => {
      if (mode === "rejected") throw new Error("synthetic-private-native-error");
      return { ...receipt, access: "Shared" };
    });
    const client = await createNativeClient(invoke as never, async () => () => {});
    const host = bindMissionHost(client);
    await expect(host.openTerminalBriefs!()).rejects.toThrow(/^TERMINAL_HANDOFF_UNAVAILABLE$/);
    expect(invoke.mock.calls.filter(([command]) => command === "open_terminal_briefs"))
      .toEqual([["open_terminal_briefs"]]);
  });
});
