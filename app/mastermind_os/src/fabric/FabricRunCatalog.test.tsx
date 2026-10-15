// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { bindMissionHost, type AuthState, type RawClient } from "../host";
import { FabricRunCatalog } from "./FabricRunCatalog";
import { AttendedFabricWorkspace } from "./AttendedFabricWorkspace";
import ownerNested from "../fixtures/fabric-catalog-m2-nested-observation-20261015.json";
import { CATALOG_LIMIT, decodeFabricCatalog, type CatalogRow, type FabricCatalog } from "./catalog-contract";

afterEach(cleanup);
function row(id = "run-one"): CatalogRow {
  return { run_id: id, controller_modified_at: "2026-10-13T20:00:00Z", reason_code: null,
    status: { schema: "mastermind.fabric_task_status.v1", run_id: id, root_id: "original-root", parent_run_id: "immediate-parent",
      state: "TERMINAL", rc: 0, signal: "ok", result_available: true, result_bytes: 120, accepted: false, accepted_by: null,
      acceptance_state: "NOT_ACCEPTED", acceptance_reason: "NO_OUTCOME" } };
}
function catalog(items = [row()]): FabricCatalog {
  return { schema: "mastermind.attended_fabric_catalog.v1", availability: "AVAILABLE", observed_at: "2026-10-13T20:01:00Z",
    source: { owner: "ATTENDED_FABRIC", observation_kind: "CONTROLLER_STATUS_SNAPSHOT", revision: "a".repeat(64),
      scope: "EXACT_RUN_SET", atomic: false, time_basis: "LOCAL_READ" },
    coverage: { returned_count: items.length, candidate_count: items.length, omitted_count: 0, scan_complete: true, status_complete: true },
    items, reason_codes: [] };
}
function client(read: (request: { signal: AbortSignal }) => Promise<unknown> = async () => catalog()) {
  let auth: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null }, generation = 1;
  const listeners = new Set<(s: AuthState) => void>();
  const statusRead = vi.fn(async () => row().status);
  const raw: RawClient = { getState: () => auth, invalidationGeneration: () => generation,
    subscribe: fn => { listeners.add(fn); return () => { listeners.delete(fn); }; },
    signIn: async () => {}, signOut: async () => {}, readPrograms: async () => null, readWork: async () => null,
    readMission: async () => null, readCurrentWindow: async () => null, readAttendedFabricCatalog: vi.fn(read), readAttendedFabric: statusRead };
  return { raw, statusRead, listeners, change: (next = auth) => { auth = next; generation++; listeners.forEach(fn => fn(auth)); } };
}
const load = async () => { fireEvent.click(screen.getByRole("button", { name: "Load runs" })); await screen.findByRole("button", { name: /^run-one ·/ }); };
const select = (id = "run-one") => fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${id} ·`) }));

describe("catalog metadata contract", () => {
  it("keeps a valid owner-shaped observation and strips unsanctioned content", () => {
    const d = catalog(); const projected = decodeFabricCatalog({ ...d, prompts: "PRIVATE", items: [{ ...d.items[0], raw_log: "PRIVATE", status: { ...d.items[0].status, bearer: "PRIVATE" } }] });
    expect(projected).toEqual(d); expect(JSON.stringify(projected)).not.toContain("PRIVATE");
  });
  it("preserves null lineage rather than converting the run label into a root", () => {
    const r = row(); r.status!.root_id = null; r.status!.parent_run_id = null;
    expect(decodeFabricCatalog(catalog([r])).items[0].status!.root_id).toBeNull();
  });
  it("rejects mismatched run IDs, duplicates and oversized row collections", () => {
    const r = row(); r.status!.run_id = "another-run";
    expect(() => decodeFabricCatalog(catalog([r]))).toThrow();
    expect(() => decodeFabricCatalog(catalog([row(), row()]))).toThrow();
    expect(() => decodeFabricCatalog(catalog(Array.from({ length: CATALOG_LIMIT + 1 }, (_, n) => row(`run-${n}`))))).toThrow();
  });
  it("refuses contradictory counts, unknown schema and fake atomic snapshots", () => {
    for (const mutate of [
      (d: FabricCatalog) => { d.coverage.returned_count = 2; },
      (d: FabricCatalog) => { d.coverage.candidate_count = 0; },
      (d: FabricCatalog) => { d.coverage.omitted_count = 2; },
      (d: FabricCatalog) => { d.coverage.candidate_count = null; },
      (d: FabricCatalog) => { d.source.revision = null; },
    ]) { const d = catalog(); mutate(d); expect(() => decodeFabricCatalog(d)).toThrow(); }
    expect(() => decodeFabricCatalog({ ...catalog(), schema: "future" })).toThrow();
    expect(() => decodeFabricCatalog({ ...catalog(), source: { ...catalog().source, atomic: true } })).toThrow();
  });
  it("allows bounded complete scans with omitted rows, without claiming the full fleet", () => {
    const d = catalog(); d.coverage.candidate_count = 100; d.coverage.omitted_count = 99; d.reason_codes = ["ROWS_OMITTED"];
    expect(decodeFabricCatalog(d).coverage.omitted_count).toBe(99);
  });
  it("preserves partial and unavailable sources instead of manufacturing empty success", () => {
    const d = catalog([{ run_id: "run-one", controller_modified_at: null, status: null, reason_code: "STATUS_UNAVAILABLE" }]);
    d.availability = "PARTIAL"; d.coverage.status_complete = false; d.reason_codes = ["STATUS_PARTIAL"];
    expect(decodeFabricCatalog(d).items[0].status).toBeNull();
    d.coverage.status_complete = true; expect(() => decodeFabricCatalog(d)).toThrow();
    const absent = catalog([]); absent.availability = "UNAVAILABLE"; absent.source.revision = null;
    absent.coverage = { returned_count: 0, candidate_count: null, omitted_count: null, scan_complete: false, status_complete: false };
    expect(decodeFabricCatalog(absent).availability).toBe("UNAVAILABLE");
  });
  it("rejects raw reason text, malformed time and incoherent row failure/status pairs", () => {
    const r = row(); r.reason_code = "SOURCE_CHANGED";
    expect(() => decodeFabricCatalog(catalog([r]))).toThrow();
    expect(() => decodeFabricCatalog({ ...catalog(), reason_codes: ["PRIVATE ERROR"] })).toThrow();
    expect(() => decodeFabricCatalog({ ...catalog(), observed_at: "yesterday" })).toThrow();
  });
});

describe("owner-authorized catalog host and view", () => {
  it("does not mount optional readers or subscriptions when the source is absent", () => {
    const c = client(); delete c.raw.readAttendedFabricCatalog;
    const host = bindMissionHost(c.raw); expect(host.readAttendedFabricCatalog).toBeUndefined();
    const before = c.listeners.size; render(<FabricRunCatalog host={host} />);
    expect(c.listeners.size).toBe(before); expect(screen.getByRole("status").textContent).toContain("does not mean the fleet is idle");
  });
  it("withholds the port without owner invalidation and refuses signed-out reads", async () => {
    const c = client(); delete c.raw.invalidationGeneration; expect(bindMissionHost(c.raw).readAttendedFabricCatalog).toBeUndefined();
    const second = client(), host = bindMissionHost(second.raw);
    second.change({ status: "signed_out", acquisition: false, content: false, reason: null });
    await expect(host.readAttendedFabricCatalog!({ signal: new AbortController().signal })).rejects.toThrow("FABRIC_READ_UNAUTHORIZED");
    expect(second.raw.readAttendedFabricCatalog).not.toHaveBeenCalled();
  });
  it("loads only on explicit demand and separates observed controller states from acceptance", async () => {
    const c = client(); render(<FabricRunCatalog host={bindMissionHost(c.raw)} />);
    expect(c.raw.readAttendedFabricCatalog).not.toHaveBeenCalled(); await load();
    expect(screen.getByText("1 awaiting acceptance")).toBeTruthy(); expect(screen.getByText("0 active or waiting in these rows")).toBeTruthy();
    expect(screen.getByText(/Sequential observation/)).toBeTruthy(); expect(screen.getByRole("button", { name: "Refresh runs" })).toBeTruthy();
  });
  it("locally searches identifiers and filters only loaded rows", async () => {
    const running = row("run-two"); running.status!.state = "ACTIVE_OR_WAITING"; running.status!.root_id = null;
    running.status!.accepted = null; running.status!.acceptance_state = "UNVERIFIED";
    const c = client(async () => catalog([row(), running])); render(<FabricRunCatalog host={bindMissionHost(c.raw)} />); await load();
    fireEvent.click(screen.getByRole("button", { name: "Active or waiting" }));
    expect(screen.queryByRole("button", { name: /^run-one ·/ })).toBeNull(); expect(screen.getByRole("button", { name: /^run-two ·/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByLabelText("Search loaded run, root or parent"), { target: { value: "immediate-parent" } });
    expect(c.raw.readAttendedFabricCatalog).toHaveBeenCalledTimes(1);
  });
  it("shows only actual source-declared nested chains, not invented missing parents", async () => {
    const direct = row(); direct.status!.parent_run_id = "original-root";
    const nested = row("run-two"); nested.status!.parent_run_id = "run-one";
    const outside = row("run-three"); outside.status!.parent_run_id = "outside-parent";
    const c = client(async () => catalog([direct, nested, outside]));
    render(<FabricRunCatalog host={bindMissionHost(c.raw)} />); await load();
    expect(screen.getByText("2 declared nested parents in these rows")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Nested parents" }));
    expect(screen.queryByRole("button", { name: /^run-one ·/ })).toBeNull();
    expect(screen.getByRole("button", { name: /^run-two ·/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^run-three ·/ })).toBeTruthy();
    select("run-two");
    const exact = screen.getByRole("group", { name: "Observed run ancestry" });
    expect(exact.textContent).toContain("original-root → run-one → run-two");
    expect(exact.textContent).toContain("Declared depth 2");
    expect(exact.textContent).toContain("not authority or verified worker START");
    select("run-three");
    const partial = screen.getByRole("group", { name: "Observed run ancestry" });
    expect(partial.textContent).toContain("outside-parent → run-three");
    expect(partial.textContent).toContain("Parent not supplied in these records");
    expect(partial.textContent).toContain("Full depth unknown");
    expect(c.statusRead).not.toHaveBeenCalled();
    expect(c.raw.readAttendedFabricCatalog).toHaveBeenCalledTimes(1);
  });
  it("inspects an actual M2 nested operator/leaf snapshot with no implicit read", async () => {
    const c = client(async () => ownerNested);
    render(<FabricRunCatalog host={bindMissionHost(c.raw)} />);
    fireEvent.click(screen.getByRole("button", { name: "Load runs" }));
    await screen.findByRole("button", { name: /^fabric-grok-operator-onboarding-leaf/ });
    expect(screen.getByText("3 declared nested parents in these rows")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Nested parents" }));
    expect(screen.queryByRole("button", { name: /^fabric-grok-operator-return/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^fabric-grok-operator-onboarding-leaf/ }));
    const ancestry = screen.getByRole("group", { name: "Observed run ancestry" });
    expect(ancestry.textContent).toContain("fabric-grok-operator-return-01a11e90-v1 → fabric-grok-operator-onboarding-leaf-01a11e90-v1");
    expect(ancestry.textContent).toContain("Declared depth 2");
    expect(c.statusRead).not.toHaveBeenCalled();
    expect(c.raw.readAttendedFabricCatalog).toHaveBeenCalledTimes(1);
  });
  it("supports localized lineage while preserving exact source labels", async () => {
    const direct = row(); direct.status!.parent_run_id = "original-root";
    const c = client(async () => catalog([direct]));
    render(<FabricRunCatalog host={bindMissionHost(c.raw)} locale="zh-CN" />);
    fireEvent.click(screen.getByRole("button", { name: "加载运行" }));
    await screen.findByRole("button", { name: /^run-one ·/ });
    select();
    const relation = screen.getByRole("group", { name: "观测运行层级" });
    expect(relation.textContent).toContain("original-root → run-one");
    expect(relation.textContent).toContain("上级为原始根标签");
    expect(relation.textContent).toContain("声明深度 1");
    expect(c.statusRead).not.toHaveBeenCalled();
  });
  it("selects an exact root/run without reading it automatically", async () => {
    const c = client(), inspect = vi.fn(); render(<FabricRunCatalog host={bindMissionHost(c.raw)} onInspect={inspect} />); await load(); select();
    fireEvent.click(screen.getByRole("button", { name: "Use in run inspector" }));
    expect(inspect).toHaveBeenCalledWith({ runId: "run-one", rootId: "original-root" }); expect(c.statusRead).not.toHaveBeenCalled();
  });
  it("keeps null-root records visible but non-navigable", async () => {
    const r = row(); r.status!.root_id = null; const c = client(async () => catalog([r]));
    render(<FabricRunCatalog host={bindMissionHost(c.raw)} onInspect={vi.fn()} />); await load(); select();
    expect((screen.getByRole("button", { name: "Use in run inspector" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/No root has been invented/)).toBeTruthy();
  });
  it("suppresses late results after same-display auth generation changes", async () => {
    let resolve!: (value: unknown) => void;
    const c = client(() => new Promise(r => { resolve = r; })); render(<FabricRunCatalog host={bindMissionHost(c.raw)} />);
    fireEvent.click(screen.getByRole("button", { name: "Load runs" }));
    await act(async () => { c.change(); resolve(catalog()); });
    expect(screen.queryByRole("button", { name: /^run-one ·/ })).toBeNull();
  });
  it("clears old host observations without briefly attributing them to the replacement", async () => {
    const c = client(), host = bindMissionHost(c.raw); const view = render(<FabricRunCatalog host={host} />); await load();
    view.rerender(<FabricRunCatalog host={bindMissionHost(client().raw)} />);
    expect(screen.queryByRole("button", { name: /^run-one ·/ })).toBeNull();
  });
  it("redacts upstream error messages", async () => {
    const c = client(async () => { throw new Error("PRIVATE token=secret /private/path"); });
    render(<FabricRunCatalog host={bindMissionHost(c.raw)} />); fireEvent.click(screen.getByRole("button", { name: "Load runs" }));
    expect((await screen.findByRole("alert")).textContent).toBe("FABRIC_SOURCE_UNAVAILABLE"); expect(document.body.textContent).not.toContain("PRIVATE");
  });
  it("shows unknown denominator and source limits in partial responses", async () => {
    const d = catalog(); d.availability = "PARTIAL"; d.coverage.scan_complete = false; d.coverage.candidate_count = null; d.coverage.omitted_count = null;
    d.reason_codes = ["SCAN_LIMIT"]; const c = client(async () => d); render(<FabricRunCatalog host={bindMissionHost(c.raw)} />); await load();
    expect(screen.getByText(/Source candidates Unknown/)).toBeTruthy(); expect(screen.getByText("Omitted Unknown")).toBeTruthy();
    expect(screen.getByText("SCAN_LIMIT")).toBeTruthy();
  });
  it("connects catalog selection to the existing inspector without automatic status reads", async () => {
    const c = client(); render(<AttendedFabricWorkspace host={bindMissionHost(c.raw)} />); await load(); select();
    fireEvent.click(screen.getByRole("button", { name: "Use in run inspector" }));
    await waitFor(() => expect((screen.getByLabelText("Original root") as HTMLInputElement).value).toBe("original-root"));
    expect((screen.getByLabelText("Existing run ID") as HTMLInputElement).value).toBe("run-one");
    expect(c.statusRead).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "Inspect run" }));
    await waitFor(() => expect(c.statusRead).toHaveBeenCalledTimes(1));
    expect(c.statusRead).toHaveBeenCalledWith(expect.objectContaining({ runId: "run-one", rootId: "original-root" }));
  });
  it("clears copied run selectors on an authentication generation change", async () => {
    const c = client(); render(<AttendedFabricWorkspace host={bindMissionHost(c.raw)} />); await load(); select();
    fireEvent.click(screen.getByRole("button", { name: "Use in run inspector" }));
    await waitFor(() => expect((screen.getByLabelText("Existing run ID") as HTMLInputElement).value).toBe("run-one"));
    act(() => c.change());
    expect((screen.getByLabelText("Existing run ID") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Original root") as HTMLInputElement).value).toBe("");
    expect(screen.queryByRole("button", { name: /^run-one ·/ })).toBeNull();
  });
  it("renders the new copy in the selected locale", () => {
    render(<FabricRunCatalog locale="zh-CN" />); expect(screen.getByRole("heading", { name: "近期 Fabric 运行" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("不代表代理池空闲");
  });
});
