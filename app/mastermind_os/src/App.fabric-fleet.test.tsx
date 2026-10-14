// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, type RawClient } from "./host";
import { navigateCompanyOperation } from "./test-operational-navigation";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import type { MissionHost } from "./host";

function status(run_id = "fabric-selected-run") {
  return {
    schema: "mastermind.fabric_task_status.v1", run_id,
    root_id: "original-root", parent_run_id: "original-root",
    state: "TERMINAL", rc: 0, signal: "ok",
    result_available: true, result_bytes: 32,
    accepted: false, accepted_by: null,
    acceptance_state: "NOT_ACCEPTED", acceptance_reason: "NO_OUTCOME",
  };
}
function catalog() {
  return {
    schema: "mastermind.attended_fabric_catalog.v1",
    availability: "AVAILABLE", observed_at: "2026-10-13T21:10:00Z",
    source: {
      owner: "ATTENDED_FABRIC", observation_kind: "CONTROLLER_STATUS_SNAPSHOT",
      revision: "a".repeat(64), scope: "MACHINE_OWNER", atomic: false, time_basis: "LOCAL_READ",
    },
    coverage: { returned_count: 1, candidate_count: 1, omitted_count: 0, scan_complete: true, status_complete: true },
    items: [{ run_id: "fabric-selected-run", controller_modified_at: "2026-10-13T21:09:00Z", status: status(), reason_code: null }],
    reason_codes: [],
  };
}
function connectedHost(options: { catalog: boolean } = { catalog: true }): {
  host: MissionHost; catalogRead: ReturnType<typeof vi.fn>; statusRead: ReturnType<typeof vi.fn>;
  authChanged: () => void;
} {
  let generation = 1;
  let statusValue: RawClient["getState"] extends () => infer S ? S : never = {
    status: "signed_in", acquisition: true, content: false, reason: null
  };
  const listeners = new Set<(state: ReturnType<RawClient["getState"]>) => void>();
  const catalogRead = vi.fn(async () => catalog()), statusRead = vi.fn(async () => status());
  const raw: RawClient = {
    getState: () => statusValue, invalidationGeneration: () => generation,
    subscribe: fn => { listeners.add(fn); return () => { listeners.delete(fn); }; },
    signIn: async () => {}, signOut: async () => {},
    readPrograms: async () => controlRoomFixture(),
    readWork: async () => { throw new Error("NOT_AVAILABLE_IN_TEST"); },
    readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    readCurrentWindow: async () => { throw new Error("NOT_AVAILABLE_IN_TEST"); },
    readAttendedFabric: statusRead,
    ...(options.catalog ? { readAttendedFabricCatalog: catalogRead } : {}),
  };
  return {
    host: bindMissionHost(raw), catalogRead, statusRead,
    authChanged: () => {
      generation++;
      statusValue = { status: "signed_out", acquisition: false, content: false, reason: null };
      listeners.forEach(fn => fn(statusValue));
    }
  };
}
beforeEach(async () => {
  history.replaceState(null, "", "/os/?work_ref=WS%3AALPHA&root_job_id=JOB-A");
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  delete window.MastermindMissionHost;
});

describe("Fleet route — separate Fabric observation and Capacity truth", () => {
  it("keeps canonical Capacity unavailable and marks missing direct M2 source as disconnected", async () => {
    const owner = connectedHost({ catalog: false });
    window.MastermindMissionHost = owner.host;
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Fleet & Capacity");
    expect(screen.getByText("CAPACITY_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Recent Fabric runs" })).toBeTruthy();
    expect(screen.getByText(/No authorized catalog reader is connected/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Load runs" }).hasAttribute("disabled")).toBe(true);
    expect(owner.catalogRead).not.toHaveBeenCalled();
    expect(owner.statusRead).not.toHaveBeenCalled();
  });

  it("opens an authorized catalog only by request and routes selection without an implicit status read", async () => {
    const owner = connectedHost();
    window.MastermindMissionHost = owner.host;
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Fleet & Capacity");
    expect(screen.getByText("CAPACITY_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(owner.catalogRead).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Load runs" }));
    expect(await screen.findByRole("button", { name: /fabric-selected-run · TERMINAL/ })).toBeTruthy();
    expect(owner.catalogRead).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: /fabric-selected-run · TERMINAL/ }));
    await user.click(screen.getByRole("button", { name: "Use in run inspector" }));
    const runDetails = screen.getByText("Direct M2 Fabric · inspect an existing run").closest("details")!;
    const inspector = within(runDetails as HTMLElement);
    expect((inspector.getByRole("textbox", { name: "Original root" }) as HTMLInputElement).value).toBe("original-root");
    expect((inspector.getByRole("textbox", { name: "Existing run ID" }) as HTMLInputElement).value).toBe("fabric-selected-run");
    expect(owner.statusRead).not.toHaveBeenCalled();
    await user.click(inspector.getByRole("button", { name: "Inspect run" }));
    await waitFor(() => expect(owner.statusRead).toHaveBeenCalledTimes(1));
    expect(inspector.getByText("NOT_ACCEPTED")).toBeTruthy();
    expect(screen.getByText("CAPACITY_SOURCE_NOT_CONNECTED")).toBeTruthy();
  });

  it("invalidates selections and keeps source reads disabled after sign-out", async () => {
    const owner = connectedHost();
    window.MastermindMissionHost = owner.host;
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Fleet & Capacity");
    await user.click(screen.getByRole("button", { name: "Load runs" }));
    await screen.findByRole("button", { name: /fabric-selected-run · TERMINAL/ });
    owner.authChanged();
    await waitFor(() => expect(screen.queryByRole("button", { name: /fabric-selected-run · TERMINAL/ })).toBeNull());
    expect(screen.getByRole("button", { name: "Load runs" }).hasAttribute("disabled")).toBe(true);
    expect(owner.catalogRead).toHaveBeenCalledTimes(1);
    expect(owner.statusRead).not.toHaveBeenCalled();
  });
});
