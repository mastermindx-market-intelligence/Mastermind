// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { decodeControlRoomRead } from "./control-room";
import { controlRoomFixture } from "./test-fixtures";
import type { AuthState } from "./host";
import { ControlRoomActionTransportError } from "./control-room";

const firstHandle = "55555555-5555-4555-8555-555555555555";
function signed() {
  let value: AuthState = { status: "signed_in", acquisition: true, content: true, reason: null };
  let notify = (_next: AuthState) => {};
  return {
    auth: {
      getState: () => value,
      subscribe: (listener: (next: AuthState) => void) => {
        notify = listener; return () => { notify = () => {}; };
      },
      signIn: vi.fn(async () => {}), signOut: vi.fn(async () => {}),
    },
    leave() {
      value = { ...value, status: "signed_out", acquisition: false, content: false };
      notify(value);
    },
  };
}
function source() {
  const room = controlRoomFixture();
  // Each attached binding is a separate incumbent source handle.
  room.work[1].bindings[0].binding_id = "66666666-6666-4666-8666-666666666666";
  return decodeControlRoomRead({
    control_room: room, capabilities: {},
    composed_at: "2026-10-19T00:00:00Z", refresh_in_flight: false,
    live_builds_active: false, state_refresh_error: null, source_validity: {},
  });
}
beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as any).__TAURI_INTERNALS__;
});
afterEach(() => {
  cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks();
});
describe("mounted Control Room actions use the existing authenticated Host", () => {
  it("sends one deliberate exact binding Open without changing the mission navigation", async () => {
    const owner = signed(), user = userEvent.setup();
    const open = vi.fn(async () => ({
      schema: "mastermind.workspace_control_room_action_result.v1" as const,
      operation: "open" as const, status: 200,
      disposition: "OWNER_RETURNED" as const,
      outcome: { ok: true, verified: false },
    }));
    window.MastermindMissionHost = {
      auth: owner.auth, readControlRoomState: vi.fn(async () => source()),
      openControlRoomSurface: open,
    };
    render(<App />);
    await user.click(within(screen.getByRole("navigation", { name: "Company operations" }))
      .getByRole("button", { name: "Control Room" }));
    const operator = await screen.findByRole("region", { name: "Workspace surfaces" });
    const openButton = await within(operator).findByRole("button",
      { name: `Open Cursor agent binding ${firstHandle}` });
    expect(open).not.toHaveBeenCalled();
    await user.click(openButton);
    expect(open).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith({
      payload: { binding_id: firstHandle },
      signal: expect.any(AbortSignal),
    });
    const status = within(operator).getByText("Owner reported success").closest('[role="status"]');
    expect(status?.textContent).toContain("Verification that the surface is open was not confirmed.");
    expect(screen.getByRole("heading", { name: "Company overview" })).toBeTruthy();
  });
  it("keeps an unknown original effect held while read refresh remains a separate operation", async () => {
    const owner = signed(), user = userEvent.setup();
    const open = vi.fn(async () => { throw new ControlRoomActionTransportError("open", "EFFECT_UNKNOWN"); });
    const read = vi.fn(async () => source());
    window.MastermindMissionHost = {
      auth: owner.auth, readControlRoomState: read,
      openControlRoomSurface: open, refreshControlRoomBuilds: vi.fn(async () => ({
        schema: "mastermind.workspace_control_room_action_result.v1" as const, operation: "refresh-builds" as const,
        status: 200, disposition: "OWNER_RETURNED" as const, outcome: { ok: true },
      })),
    };
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Control Room" }));
    const operator = await screen.findByRole("region", { name: "Workspace surfaces" });
    await user.click(await within(operator).findByRole("button", { name: `Open Cursor agent binding ${firstHandle}` }));
    const status = within(operator).getByText("Action outcome unknown").closest('[role="status"]');
    expect(status?.textContent).toContain("No retry is sent automatically.");
    const overview = screen.getByRole("region", { name: "Control Room workspace" });
    await user.click(within(overview).getByRole("button", { name: "Refresh Control Room" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(within(operator).getByText("Action outcome unknown")).toBeTruthy();
    expect(window.MastermindMissionHost.refreshControlRoomBuilds).not.toHaveBeenCalled();
    expect(open).toHaveBeenCalledTimes(1);
    expect((within(operator).getByRole("button", { name: "Refresh builds" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("removes the old principal's binding and action methods from the screen on logout", async () => {
    const owner = signed(), user = userEvent.setup();
    window.MastermindMissionHost = {
      auth: owner.auth, readControlRoomState: vi.fn(async () => source()),
      openControlRoomSurface: vi.fn(async () => {
        throw new Error("should not run");
      }),
    };
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Control Room" }));
    expect(await screen.findByRole("button", { name: `Open Cursor agent binding ${firstHandle}` })).toBeTruthy();
    await act(async () => owner.leave());
    await waitFor(() => expect(screen.queryByRole("button", { name: `Open Cursor agent binding ${firstHandle}` })).toBeNull());
  });
});
