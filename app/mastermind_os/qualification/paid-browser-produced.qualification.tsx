import { readFileSync } from "node:fs";
import { cleanup, render, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { bindMissionHost, type RawClient } from "../src/host";
import { navigateCompanyOperation } from "../src/test-operational-navigation";
import { controlRoomFixture, realControlRoomFixture, missionFixture } from "../src/test-fixtures";
import { decodeBrowserScopedFabricCatalog } from "../src/fabric/catalog-contract";
import { decodeAttendedStatus, type AttendedSelection } from "../src/fabric/attended-status";

const path = process.env.MMOS_PAID_BROWSER_PRODUCED_JSON;
if (!path) throw new Error("Run tests/test_workspace_fabric_produced_boundary.py to produce actual native bodies");
const produced = JSON.parse(readFileSync(path, "utf8")) as {
  case: string; selection: AttendedSelection; catalog: unknown; status: unknown;
};

function connectedHost() {
  let generation = 1;
  let state: ReturnType<RawClient["getState"]> = {
    status: "signed_in", acquisition: true, content: false, reason: null,
  };
  const listeners = new Set<(state: ReturnType<RawClient["getState"]>) => void>();
  const catalogRead = vi.fn(async () => structuredClone(produced.catalog));
  const statusRead = vi.fn(async (selected: AttendedSelection) => {
    expect({ rootId: selected.rootId, runId: selected.runId }).toEqual(produced.selection);
    return structuredClone(produced.status);
  });
  // A separate, explicit offline Control Room observation supplies only an
  // inventory row. It is not the Programs read or evidence of host capacity.
  const controlRead = vi.fn(async () => ({
    control_room: realControlRoomFixture(),
    capabilities: { codex: { installed: false, version: null, state: "NOT_INSTALLED", detail: "" } },
    composed_at: null, refresh_in_flight: false, live_builds_active: false,
    state_refresh_error: null, source_validity: {},
  }));
  const raw: RawClient = {
    getState: () => state, invalidationGeneration: () => generation,
    subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    signIn: async () => {}, signOut: async () => {},
    readPrograms: async () => controlRoomFixture(),
    readControlRoomState: controlRead,
    readWork: async () => { throw new Error("UNUSED_FIXTURE_ROUTE"); },
    readMission: async () => missionFixture("WS:ALPHA", "JOB-A"),
    readCurrentWindow: async () => { throw new Error("UNUSED_FIXTURE_ROUTE"); },
    readAttendedFabric: statusRead, readAttendedFabricCatalog: catalogRead,
  };
  return { host: bindMissionHost(raw), catalogRead, statusRead, controlRead,
    revoke: () => {
      generation++;
      state = { status: "signed_out", acquisition: false, content: false, reason: null };
      listeners.forEach(listener => listener(state));
    },
  };
}

function expectCapacityUnknown() {
  const resource = within(screen.getByRole("region", { name: "Selected resource" }));
  for (const label of ["Host readiness", "Serviceability / task preflight", "Queue pressure"])
    expect(resource.getByText(label).nextElementSibling?.textContent).toBe("Not supplied");
  const telemetry = within(screen.getByRole("region", { name: "Host telemetry observation" }));
  expect(telemetry.getByText("No qualified retained host observation is connected. CPU, memory and disk readings remain unknown.")).toBeTruthy();
  expect(telemetry.queryByText("Not evaluated; cannot place work")).toBeNull();
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

describe(`actual native producer → browser/App (${produced.case})`, () => {
  it("passes both existing closed decoders without adapting the emitted bodies", () => {
    const catalog = decodeBrowserScopedFabricCatalog(produced.catalog);
    const status = decodeAttendedStatus(produced.status, produced.selection);
    expect(catalog).toEqual(produced.catalog);
    expect(status).toEqual(produced.status);
    expect(catalog.items).toHaveLength(1);
    expect(catalog.items[0].status).toEqual(status);
    expect(catalog.source.scope).toBe("EXACT_RUN_SET");
    expect(catalog.availability).toBe("PARTIAL");
    expect(catalog.coverage).toEqual({ returned_count: 1, candidate_count: null,
      omitted_count: null, scan_complete: false, status_complete: true });
    expect(catalog.reason_codes).toEqual(["ROWS_OMITTED"]);
    expect(status.acceptance_state).toBe(produced.case === "accepted" ? "ACCEPTED"
      : ["unaccepted", "rejected"].includes(produced.case) ? "NOT_ACCEPTED" : "UNVERIFIED");
  });

  it("loads the produced row, preserves lineage and acceptance, and clears it on auth change", async () => {
    const expected = decodeAttendedStatus(produced.status, produced.selection);
    const owner = connectedHost();
    window.MastermindMissionHost = owner.host;
    const user = userEvent.setup();
    render(<App />);
    await navigateCompanyOperation(user, "Fleet & Capacity");
    // Follow the current resource drilldown and evidence disclosures. These
    // presentation actions must not read the Fabric catalog or a run status.
    const resourceRow = await screen.findByRole("button", { name: /Codex/ });
    await user.click(resourceRow);
    expect(owner.controlRead).toHaveBeenCalledTimes(1);
    await user.click(screen.getByText("Additional resource evidence", { selector: "summary" }));
    await user.click(screen.getByText("Original capacity receipts and run records", { selector: "summary" }));
    expectCapacityUnknown();
    expect(owner.catalogRead).not.toHaveBeenCalled();
    expect(owner.statusRead).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Load runs" }));
    const rowName = `${produced.selection.runId} · ${expected.state}`;
    const row = await screen.findByRole("button", { name: rowName });
    expect(screen.getByText("PARTIAL")).toBeTruthy();
    expect(screen.getByText("Shown 1 / Source candidates Unknown")).toBeTruthy();
    expect(screen.getByText("Omitted Unknown")).toBeTruthy();
    expect(screen.getByText("ROWS_OMITTED")).toBeTruthy();
    expect(owner.catalogRead).toHaveBeenCalledTimes(1);
    await user.click(row);
    const details = screen.getByText("Direct M2 Fabric · inspect an existing run").closest("details")!;
    const inspector = within(details as HTMLElement);
    const use = screen.getByRole("button", { name: "Use in run inspector" });
    if (expected.root_id === null) {
      expect(use.hasAttribute("disabled")).toBe(true);
      expect(screen.getByText("Root lineage is not established. No root has been invented for this record.")).toBeTruthy();
      expect((inspector.getByRole("textbox", { name: "Original root" }) as HTMLInputElement).value).toBe("");
      // The original Runtime selector is explicit test input. A missing native
      // root never turns into invented catalog lineage or an automatic read.
      await user.click(screen.getByText("Direct M2 Fabric · inspect an existing run"));
      await user.type(inspector.getByRole("textbox", { name: "Original root" }), produced.selection.rootId);
      await user.type(inspector.getByRole("textbox", { name: "Existing run ID" }), produced.selection.runId);
    } else {
      expect(use.hasAttribute("disabled")).toBe(false);
      await user.click(use);
      expect((inspector.getByRole("textbox", { name: "Original root" }) as HTMLInputElement).value).toBe(produced.selection.rootId);
      expect((inspector.getByRole("textbox", { name: "Existing run ID" }) as HTMLInputElement).value).toBe(produced.selection.runId);
    }
    expect(owner.statusRead).not.toHaveBeenCalled();
    await user.click(inspector.getByRole("button", { name: "Inspect run" }));
    await waitFor(() => expect(owner.statusRead).toHaveBeenCalledTimes(1));
    expect(await inspector.findByText(expected.acceptance_state)).toBeTruthy();
    expect(inspector.getByText(expected.acceptance_reason)).toBeTruthy();
    expect(inspector.getByText(expected.state)).toBeTruthy();
    if (expected.root_id === null)
      expect(inspector.getByText("The source did not establish root or parent lineage.")).toBeTruthy();
    if (produced.case === "effect_unknown")
      expect(inspector.getByText(/Effects are unresolved/)).toBeTruthy();
    if (["unaccepted", "rejected", "unverified_ledger"].includes(produced.case))
      expect(inspector.getByText(/Exit 0: result not accepted/)).toBeTruthy();
    if (produced.case === "accepted")
      expect(inspector.queryByText(/Exit 0: result not accepted/)).toBeNull();
    expectCapacityUnknown();
    expect(document.body.textContent).not.toContain("Private retained answer");
    act(() => owner.revoke());
    await waitFor(() => expect(screen.queryByRole("button", { name: rowName })).toBeNull());
    expect(screen.getByText("Sign in to your workspace.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load runs" })).toBeNull();
    // Auth invalidation can unmount this entire App branch. Query the live
    // document rather than the detached pre-revocation inspector element.
    expect(screen.queryByText(expected.acceptance_reason)).toBeNull();
    expect(owner.catalogRead).toHaveBeenCalledTimes(1);
    expect(owner.statusRead).toHaveBeenCalledTimes(1);
  });
});
