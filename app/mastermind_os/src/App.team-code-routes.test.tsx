// @vitest-environment jsdom
import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

// The Team route reads the roster through the EXISTING native port. The mock
// below replaces the singleton with a REAL createNativeHermesPort over a fake
// transport (invoke/available) and a real IndexedDB pointer store — the same
// seam Director B's suites mock — so the closed echo check and the fail-closed
// roster parse still run in this App-level test.
const nativeTransport = vi.hoisted(() => ({
  invoke: vi.fn(),
  available: vi.fn(() => false),
}));
vi.mock("./hermes-native/native-port", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("./hermes-native/native-port")>();
  const store = await import("./orchestration/indexeddb-pending-pointer-store");
  const idb = await import("fake-indexeddb");
  return {
    ...actual,
    nativeHermesPort: actual.createNativeHermesPort({
      invoke: nativeTransport.invoke,
      available: nativeTransport.available,
      store: store.createIndexedDbPendingPointerStore(new idb.IDBFactory()),
    }),
  };
});

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__;
  nativeTransport.invoke.mockReset();
  nativeTransport.available.mockReset().mockReturnValue(false);
});
afterEach(cleanup);

const companyNav = (locale: "en" | "zh-CN" = "en") => {
  const pane = document.getElementById("workspace-navigation")!;
  return within(pane as HTMLElement).getByRole("navigation", {
    name: locale === "zh-CN" ? "公司导航" : "Company navigation",
  });
};
const activeRoute = () =>
  document.querySelector(".shell")?.getAttribute("data-active-route");

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
const statusView = () => ({
  schema: "mastermind.hermes_native_view.v1", state: "READY", operation: "status",
  authGeneration: 7, capabilities: ["native_chat", "native_history", "admission_recovery"],
  delegation: "NOT_ENABLED", retryAllowed: false,
  runtime: { protocol: 1, instanceId: "native", authorityEpoch: 1, version: "0.23.0",
    sourceRevision: "b".repeat(40), localScope: "e".repeat(64) },
});

describe("Team and Code company routes", () => {
  it("registers Team and Code beside the incumbent Company destinations", () => {
    render(<App />);
    const company = companyNav();
    for (const name of [
      "Today",
      "Team",
      "Projects",
      "Code",
      "Inbox",
      "Conversations",
      "Knowledge",
    ])
      expect(within(company).getByRole("button", { name })).toBeTruthy();
  });

  it("shows the honest unverified roster while the native host is absent (TS01)", () => {
    render(<App />);
    fireEvent.click(within(companyNav()).getByRole("button", { name: "Team" }));
    expect(activeRoute()).toBe("Team");
    expect(screen.getByRole("tab", { name: "Company" }).getAttribute("aria-selected")).toBe("true");
    expect(nativeTransport.invoke).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("tab", { name: "Runtime profiles" }));
    expect(screen.getByRole("heading", { name: "Runtime profiles" })).toBeTruthy();
    expect(screen.getByText("Runtime profiles could not be read")).toBeTruthy();
    expect(screen.getByText("Roster not verified")).toBeTruthy();
    expect(screen.getByText("Current team size")).toBeTruthy();
    expect(screen.getByText("Not verified")).toBeTruthy();
    expect(screen.getByText("Presence")).toBeTruthy();
    expect(screen.getByText("Not observed")).toBeTruthy();
    // The native port's closed unavailable code stays visible.
    expect(screen.getByText("NATIVE_PLATFORM_UNAVAILABLE")).toBeTruthy();
    expect(nativeTransport.invoke).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        /Current profile availability is not verified/i,
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    // The escape hatch reuses the existing Conversations surface, not a new transport.
    fireEvent.click(
      screen.getByRole("button", { name: "Open recent conversations" }),
    );
    expect(activeRoute()).toBe("Conversations");
  });

  it("renders the live roster from the native team_roster operation through the real port", async () => {
    nativeTransport.available.mockReturnValue(true);
    nativeTransport.invoke.mockImplementation(
      async (_command: string, args: Record<string, unknown>) => {
        const request = args.request as { operation: string };
        return request.operation === "team_roster"
          ? { ...statusView(), operation: "team_roster", roster: rosterPayload }
          : statusView();
      },
    );
    render(<App />);
    fireEvent.click(within(companyNav()).getByRole("button", { name: "Team" }));
    expect(nativeTransport.invoke).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("tab", { name: "Runtime profiles" }));
    const table = await screen.findByRole("table", { name: "Runtime profiles" });
    expect(table).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Open Engineering" }),
    ).toBeTruthy();
    // Director B's closed reason code is rendered, code and phrase both visible.
    expect(screen.getByText("GATEWAY_LOCK_PID_VERIFIED")).toBeTruthy();
    expect(
      screen.getByText(/Gateway verified by lock file and running process/i),
    ).toBeTruthy();
    // The dispatch followed the port's read-only shape: status binds the
    // runtime scope, then team_roster echoes with the bound auth generation.
    const teamRosterCall = nativeTransport.invoke.mock.calls.find(
      ([, args]) =>
        (args as { request?: { operation?: string } }).request?.operation ===
        "team_roster",
    );
    expect(teamRosterCall?.[0]).toBe("hermes_native");
    expect(teamRosterCall?.[1]).toEqual({
      request: { operation: "team_roster" },
      expectedAuthGeneration: 7,
    });
    fireEvent.click(screen.getByRole("button", { name: "Open Engineering" }));
    const runtime = screen.getByRole("region", { name: "Runtime profiles" });
    expect(within(runtime).getByRole("heading", { name: "Engineering" })).toBeTruthy();
    expect(within(runtime).getByText("No conversation is bound to this runtime profile in this view.")).toBeTruthy();
    expect(within(runtime).queryByRole("combobox")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Native conversations" }));
    expect(screen.getByRole("tabpanel", { name: "Native conversations" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Engineering" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Runtime profiles" }));
    expect(screen.getByRole("heading", { name: "Engineering" })).toBeTruthy();
    const operations = nativeTransport.invoke.mock.calls.map(([, args]) => args.request.operation);
    expect(operations.filter(operation => operation === "team_roster")).toHaveLength(1);
    expect(operations.every(operation => ["status", "team_roster"].includes(operation))).toBe(true);
  });

  it("shows the honest not-projected T3 threads while no projection source is connected (TD04)", () => {
    render(<App />);
    fireEvent.click(within(companyNav()).getByRole("button", { name: "Code" }));
    expect(activeRoute()).toBe("Code");
    expect(screen.getByRole("heading", { name: "T3 Code" })).toBeTruthy();
    expect(screen.getByText("Code threads are not projected yet")).toBeTruthy();
    expect(
      screen.getByText(/no thread state is shown or inferred/i),
    ).toBeTruthy();
    expect(screen.getByText("T3_PROJECTION_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.getByText(/No provider keys live in this app/i)).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Open in T3 Code ↗" }),
    ).toBeNull();
  });

  it("keeps the zh-CN route labels and honest states", () => {
    render(<App locale="zh-CN" />);
    const company = companyNav("zh-CN");
    fireEvent.click(within(company).getByRole("button", { name: "团队" }));
    expect(activeRoute()).toBe("Team");
    fireEvent.click(screen.getByRole("tab", { name: "运行配置" }));
    expect(screen.getByRole("heading", { name: "运行配置" })).toBeTruthy();
    expect(screen.getByText("运行配置来源不可用")).toBeTruthy();
    expect(screen.getByText("名册未验证")).toBeTruthy();
    expect(screen.getByText(/运行配置的当前可用性尚未核验。/)).toBeTruthy();
    expect(screen.getByText("NATIVE_PLATFORM_UNAVAILABLE")).toBeTruthy();
    fireEvent.click(within(company).getByRole("button", { name: "代码" }));
    expect(activeRoute()).toBe("Code");
    expect(screen.getByText("编码线程尚未投影")).toBeTruthy();
    expect(screen.getByText("T3_PROJECTION_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.getByText(/此应用不保存任何提供商密钥/i)).toBeTruthy();
  });
});
