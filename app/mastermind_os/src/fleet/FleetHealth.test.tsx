// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentType } from "react";
import { decodeFleetHealth, type FleetRead } from "../fleet";
import { fleetFixture } from "../fleet.test-fixture";

const module = import.meta.glob<{ FleetHealth: ComponentType<{read?: FleetRead; generation?: number}> }>("./FleetHealth.tsx", { eager: true })["./FleetHealth.tsx"];
function component() {
  expect(module?.FleetHealth, "Fleet screen is not implemented").toBeTypeOf("function");
  return module.FleetHealth;
}
const valid = () => decodeFleetHealth(fleetFixture(), "24h")!;
beforeEach(() => Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" }));
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("Fleet hardware screen", () => {
  it("shows an honest disconnected state without issuing a request", () => {
    const FleetHealth = component(); render(<FleetHealth />);
    expect(screen.getByText(/source not connected/i)).toBeTruthy();
    expect(screen.queryByText(/all systems healthy/i)).toBeNull();
  });
  it("renders measured zero, source scope, missing history and actual time coverage", async () => {
    const FleetHealth = component(); render(<FleetHealth read={async () => valid()} />);
    await screen.findByRole("button", { name: /inspect Ubuntu 2/i });
    expect(screen.getAllByText(/^0%$/).length).toBeGreaterThan(0);
    expect(screen.getByText(/not a complete subagent count/i)).toBeTruthy();
    expect(screen.getByText(/RAM history is incomplete/i)).toBeTruthy();
    expect(screen.getByText(/recorded coverage/i)).toBeTruthy();
    expect(screen.queryByText(/24 hours of history/i)).toBeNull();
  });
  it("requests exactly the selected window and aborts the old read", async () => {
    const requests: {window: string; signal: AbortSignal}[] = [];
    const read: FleetRead = async request => {
      requests.push(request); const d = valid(); d.window = request.window; return d;
    };
    const FleetHealth = component(); const view = render(<FleetHealth read={read} />);
    await screen.findByRole("button", { name: /inspect Ubuntu 2/i });
    fireEvent.click(screen.getByRole("button", {name: "7d"}));
    await waitFor(() => expect(requests.length).toBe(2));
    expect(requests[1].window).toBe("7d"); expect(requests[0].signal.aborted).toBe(true);
    view.unmount(); expect(requests[1].signal.aborted).toBe(true);
  });
  it("discards an older auth generation and late responses", async () => {
    let resolve!: (value: ReturnType<typeof valid>) => void;
    const read: FleetRead = () => new Promise(done => { resolve = done; });
    const FleetHealth = component(); const view = render(<FleetHealth read={read} generation={1} />);
    const old = resolve;
    view.rerender(<FleetHealth generation={2} />);
    await act(async () => old(valid()));
    expect(screen.queryByRole("button", {name: /inspect Ubuntu 2/i})).toBeNull();
    expect(screen.getByText(/source not connected/i)).toBeTruthy();
  });
  it("never refreshes while hidden and aborts a request on hiding", async () => {
    const requests: AbortSignal[] = [];
    const read: FleetRead = async ({signal}) => { requests.push(signal); return valid(); };
    const FleetHealth = component(); render(<FleetHealth read={read} />);
    await screen.findByRole("button", {name: /inspect Ubuntu 2/i});
    vi.useFakeTimers();
    Object.defineProperty(document, "visibilityState", {configurable: true, value: "hidden"});
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { await vi.advanceTimersByTimeAsync(180_000); });
    expect(requests).toHaveLength(1); expect(requests[0].aborted).toBe(true);
    Object.defineProperty(document, "visibilityState", {configurable: true, value: "visible"});
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { await Promise.resolve(); });
    expect(requests).toHaveLength(2);
  });
  it("marks a retained observation as last known after a refresh failure", async () => {
    let fail = false;
    const read: FleetRead = async () => { if (fail) throw Error("private transport detail"); return valid(); };
    const FleetHealth = component(); render(<FleetHealth read={read} />);
    await screen.findByRole("button", {name: /inspect Ubuntu 2/i});
    fail = true; fireEvent.click(screen.getByRole("button", {name: "Refresh fleet"}));
    await screen.findByText(/refresh failed/i);
    expect(screen.getAllByText(/last known/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/private transport detail/i)).toBeNull();
  });
  it("keeps recorded gaps in chart geometry even with retained distant points", async () => {
    const d = valid(); d.hosts[0].history[1].gaps = ["cpu_temp_c", "memory_used_pct"];
    const FleetHealth = component(); render(<FleetHealth read={async () => d} />);
    const plot = await screen.findByRole("img", { name: /CPU temperature history/i });
    const path = plot.querySelector("path[data-series]")!;
    expect(path.getAttribute("d")?.match(/M/g)).toHaveLength(2);
    expect(path.getAttribute("d")?.includes("L")).toBe(false);
  });
});
