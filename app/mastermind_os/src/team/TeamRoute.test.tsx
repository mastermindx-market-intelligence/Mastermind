// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { NativeHermesPort, NativeOperation, NativeView } from "../hermes-native/contract";
import { parseNativeView } from "../hermes-native/contract";
import { TeamRoute } from "./TeamRoute";
afterEach(cleanup);

const rosterPayload = {
  schema: "mastermind.team_roster/v1", generatedAt: "2026-11-09T12:00:00Z",
  host: "m2studio",
  bots: [{
    id: "engineering", displayName: "Engineering", role: "operator",
    profilePath: "/Users/operator/.hermes/profiles/engineering", managed: true,
    host: "m2studio",
    gateway: { observed: true, source: "gateway_lock", instanceId: "gw-1",
      authorityEpoch: 4, codeVersion: "0.23.0", pid: 1234, state: "serving" },
    readiness: "ready", readinessReason: "GATEWAY_LOCK_PID_VERIFIED",
    lastActivity: "2026-11-09T10:00:00Z", activitySummary: "ran the WO-19 dry-run",
  }],
};
function view(operation: NativeOperation["operation"], extra: Record<string, unknown> = {}): NativeView {
  return parseNativeView({
    schema: "mastermind.hermes_native_view.v1", state: "READY", operation,
    authGeneration: 7, capabilities: ["native_chat", "native_history", "admission_recovery"],
    delegation: "NOT_ENABLED", retryAllowed: false,
    runtime: { protocol: 1, instanceId: "native", authorityEpoch: 1, version: "0.23.0",
      sourceRevision: "b".repeat(40), localScope: "e".repeat(64) }, ...extra,
  });
}
/** The same port-injection seam HermesNativePanel.test.tsx uses. */
function port(behaviour?: (request: NativeOperation) => Promise<NativeView>) {
  return {
    available: () => true,
    request: vi.fn(behaviour ?? (async (request: NativeOperation) =>
      request.operation === "team_roster"
        ? view("team_roster", { roster: rosterPayload })
        : view("status"))),
  } satisfies NativeHermesPort;
}

describe("TeamRoute — one bounded native-port read of the roster", () => {
  it("never dispatches when the native host is absent; the honest code is shown", () => {
    const p = port();
    p.available = () => false;
    render(<TeamRoute port={p} />);
    expect(screen.getByText("Team needs a connection")).toBeTruthy();
    expect(screen.getByText("NATIVE_PLATFORM_UNAVAILABLE")).toBeTruthy();
    expect(p.request).not.toHaveBeenCalled();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("reads status then the read-only team_roster operation exactly once, then renders the roster", async () => {
    const p = port();
    render(<TeamRoute port={p} />);
    const table = await screen.findByRole("table", { name: "Team roster" });
    expect(screen.getByRole("button", { name: "Open Engineering" })).toBeTruthy();
    expect(screen.getByText("GATEWAY_LOCK_PID_VERIFIED")).toBeTruthy();
    expect(table).toBeTruthy();
    const calls = p.request.mock.calls.map(([request]) => request.operation);
    expect(calls).toEqual(["status", "team_roster"]); // no polling, no retry, no second transport
  });

  it("maps a port error to UNAVAILABLE with the closed code, never an empty company", async () => {
    const p = port(async (request) => {
      if (request.operation === "team_roster") throw new Error("NATIVE_BUSY");
      return view("status");
    });
    render(<TeamRoute port={p} />);
    await screen.findByText("Team needs a connection");
    expect(screen.getByText("NATIVE_BUSY")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("reports an unknown error as NATIVE_CLIENT_UNAVAILABLE without inventing a code", async () => {
    const p = port(async () => {
      throw new Error("something odd");
    });
    render(<TeamRoute port={p} />);
    await screen.findByText("Team needs a connection");
    expect(screen.getByText("NATIVE_CLIENT_UNAVAILABLE")).toBeTruthy();
  });

  it("treats a team_roster response without a roster as unverifiable", async () => {
    const p = port(async (request) =>
      request.operation === "team_roster" ? view("team_roster") : view("status"));
    render(<TeamRoute port={p} />);
    await screen.findByText("Team needs a connection");
    expect(screen.getByText("NATIVE_RESPONSE_INVALID")).toBeTruthy();
    expect(
      screen.getByText(/returned data this surface could not verify/i),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
