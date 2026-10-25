// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture } from "./test-fixtures";
import { decodeControlRoomRead } from "./control-room";
import type { AuthState } from "./host";

function payload() {
  return {
    control_room: controlRoomFixture(),
    capabilities: {},
    composed_at: "2026-10-17T15:00:00Z",
    refresh_in_flight: false,
    live_builds_active: false,
    state_refresh_error: null,
    source_validity: {},
  };
}
function mount() {
  let state: AuthState = {
    status: "signed_in",
    acquisition: true,
    content: true,
    reason: null,
  };
  let subscriber = (_s: AuthState) => {};
  const read = vi.fn(async () => decodeControlRoomRead(payload()));
  window.MastermindMissionHost = {
    readControlRoomState: read,
    auth: {
      getState: () => state,
      subscribe: (fn) => {
        subscriber = fn;
        return () => {};
      },
      signIn: vi.fn(async () => {}),
      signOut: vi.fn(async () => {}),
    },
  };
  render(<App />);
  return {
    read,
    signOut() {
      state = {
        status: "signed_out",
        acquisition: false,
        content: false,
        reason: null,
      };
      subscriber(state);
    },
  };
}
async function enter() {
  const user = userEvent.setup();
  const navigation = screen.getByRole("navigation", {
    name: "Company operations",
  });
  await user.click(
    within(navigation).getByRole("button", { name: "Control Room" }),
  );
  return user;
}
beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
});
afterEach(() => {
  cleanup();
  delete window.MastermindMissionHost;
  vi.restoreAllMocks();
});

describe("Control Room decision-first experience", () => {
  it("provides a local programme search without repeating source requests", async () => {
    const { read } = mount();
    const user = await enter();
    await screen.findByRole("searchbox", { name: "Find a programme" });
    const region = screen.getByRole("region", { name: "Programme overview" });
    expect(within(region).getByText("Alpha program")).toBeTruthy();
    expect(within(region).getByText("Beta program")).toBeTruthy();
    await user.type(
      screen.getByRole("searchbox", { name: "Find a programme" }),
      "alpha",
    );
    expect(within(region).getByText("Alpha program")).toBeTruthy();
    expect(within(region).queryByText("Beta program")).toBeNull();
    expect(read).toHaveBeenCalledTimes(1);
  });
  it("makes a zero search result distinct from no company work and allows recovery", async () => {
    mount();
    const user = await enter();
    await user.type(
      await screen.findByRole("searchbox", { name: "Find a programme" }),
      "no-such-program",
    );
    expect(screen.getByText("No programmes match your search.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(
      screen
        .getByRole("searchbox", { name: "Find a programme" })
        .getAttribute("value"),
    ).toBe("");
    expect(
      screen.getByRole("region", { name: "Programme overview" }).textContent,
    ).toContain("Alpha program");
  });
  it("retains explicit source uncertainty without presenting registry links as live workers", async () => {
    mount();
    await enter();
    expect(await screen.findByText("Freshness not supplied")).toBeTruthy();
    expect(
      screen.queryByText(/2 workers running|all systems operational/i),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "Refresh Control Room" }),
    ).toBeTruthy();
    expect(screen.getByText("Workspace access and controls")).toBeTruthy();
    expect(
      screen.queryByText(/Choose a Program with one resolved mission/),
    ).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: /^Bind$|^Unbind$|^Refresh builds$/,
      }),
    ).toBeNull();
  });
  it("removes old-member content and search on an authentication change", async () => {
    const h = mount();
    const user = await enter();
    await user.type(
      await screen.findByRole("searchbox", { name: "Find a programme" }),
      "alpha",
    );
    await act(async () => h.signOut());
    expect(
      screen.queryByRole("searchbox", { name: "Find a programme" }),
    ).toBeNull();
    expect(screen.queryByText("Alpha program")).toBeNull();
  });
});

describe("Control Room truthful source boundary", () => {
  it("refuses a stale refresh error instead of presenting an AVAILABLE state", () => {
    expect(() =>
      decodeControlRoomRead({
        ...payload(),
        state_refresh_error: "private/path/failed",
      }),
    ).toThrow("CONTROL_ROOM_REFRESH_FAILED");
  });
  it.each(["not-a-date", "2026-99-99T00:00:00Z", "<script>alert(1)</script>"])(
    "refuses malformed observation timestamps: %s",
    (observed) => {
      expect(() =>
        decodeControlRoomRead({ ...payload(), composed_at: observed }),
      ).toThrow("CONTROL_ROOM_RESPONSE_INVALID");
    },
  );
  it("does not let a display annotation mint freshness", () => {
    const result = decodeControlRoomRead({
      ...payload(),
      source_validity: { status: "LIVE" },
    });
    expect((result as any).freshness).toBe("UNKNOWN");
  });
  it("detaches and freezes the public programme projection", () => {
    const result = decodeControlRoomRead(payload());
    expect(Object.isFrozen(result.programs)).toBe(true);
    expect(result.programs.every(Object.isFrozen)).toBe(true);
  });
});
