// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture } from "./test-fixtures";
import type { AuthState } from "./host";
import { decodeControlRoomRead } from "./control-room";

function owner() {
  let state: AuthState = {
    status: "signed_in",
    acquisition: true,
    content: true,
    reason: null,
  };
  let notify = (_next: AuthState) => {};
  const auth = {
    getState: () => state,
    subscribe: (fn: (next: AuthState) => void) => {
      notify = fn;
      return () => {
        notify = () => {};
      };
    },
    signIn: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
  };
  return {
    auth,
    replace(next: AuthState) {
      state = next;
      notify(next);
    },
  };
}
function payload() {
  return {
    control_room: controlRoomFixture(),
    capabilities: {},
    composed_at: "2026-10-17T00:00:00Z",
    refresh_in_flight: false,
    live_builds_active: false,
    state_refresh_error: null,
    source_validity: {},
  };
}
beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
});
afterEach(() => {
  cleanup();
  delete window.MastermindMissionHost;
  vi.restoreAllMocks();
});

describe("authenticated incumbent Control Room read presentation", () => {
  it("renders only decoded programs for an enrolled signed-in member", async () => {
    const a = owner();
    const read = vi.fn(async () => decodeControlRoomRead(payload()));
    window.MastermindMissionHost = { auth: a.auth, readControlRoomState: read };
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Company operations" });
    await userEvent
      .setup()
      .click(within(nav).getByRole("button", { name: "Control Room" }));
    expect(
      await screen.findByRole("heading", { name: "Company overview" }),
    ).toBeTruthy();
    await screen.findByText(/source-qualified Programs/);
    expect(screen.getByText(/READ/)).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
    expect(
      screen.queryByRole("button", {
        name: /^Bind$|^Open$|^Unbind$|^Refresh builds$/,
      }),
    ).toBeNull();
  });

  it("shows unavailable when the host has no signed Control Room read", async () => {
    const a = owner();
    window.MastermindMissionHost = { auth: a.auth };
    render(<App />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Control Room" }));
    expect(
      screen.getByText(/signed Control Room read is unavailable/i),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Refresh Control Room",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("withholds an old member's accepted card immediately after logout", async () => {
    const a = owner();
    let settle!: (value: ReturnType<typeof decodeControlRoomRead>) => void;
    const deferred = new Promise<ReturnType<typeof decodeControlRoomRead>>(
      (resolve) => {
        settle = resolve;
      },
    );
    const read = vi
      .fn()
      .mockReturnValueOnce(Promise.resolve(decodeControlRoomRead(payload())))
      .mockReturnValueOnce(deferred);
    window.MastermindMissionHost = { auth: a.auth, readControlRoomState: read };
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Control Room" }));
    await screen.findByText(/source-qualified Programs/);
    await user.click(
      screen.getByRole("button", { name: "Refresh Control Room" }),
    );
    expect(read).toHaveBeenCalledTimes(2);
    await act(async () =>
      a.replace({
        status: "signed_out",
        acquisition: false,
        content: false,
        reason: null,
      }),
    );
    await act(async () => settle(decodeControlRoomRead(payload())));
    expect(screen.queryByText(/source-qualified Programs/)).toBeNull();
    expect(
      screen.getByText(/signed Control Room read is unavailable/i),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Refresh Control Room",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});

describe("closed Control Room read decoder", () => {
  it("rejects extra fields, malformed source, and forged claim of source freshness", () => {
    const source = payload();
    expect(decodeControlRoomRead(source).state).toBe("AVAILABLE");
    expect(() =>
      decodeControlRoomRead({ ...source, admin: "admin@mastermind-x.com" }),
    ).toThrow();
    expect(() =>
      decodeControlRoomRead({ ...source, control_room: {} }),
    ).toThrow();
    expect(() =>
      decodeControlRoomRead({ ...source, refresh_in_flight: "false" }),
    ).toThrow();
  });
});
