// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ControlRoomState } from "../control-room";
import { WORK_GROUP_ORDER, type WorkDocument, type WorkRow } from "../work";
import { ResourcesSystemsPanel } from "./ResourcesSystemsPanel";

afterEach(cleanup);
const control = (): ControlRoomState => ({ state: "AVAILABLE", ownerRevision: 1,
  programs: [], observedAt: "2026-11-04T05:00:00Z", liveBuildsActive: false,
  refreshInFlight: false, freshness: "UNKNOWN", publicationSeq: null,
  crossPlane: { state: "UNAVAILABLE", reason: "NOT_INSTALLED" },
  navigation: { state: "AVAILABLE", bindings: [], unboundBindingIds: [], conflicts: [], bindingsPathPresent: true,
    capabilities: {
      codex: { installed: true, version: "1.2.3", state: "PARTIAL", detail: "UNTRUSTED_PRIVATE_DETAIL" },
      cursor_agent: { installed: false, version: null, state: "NOT_INSTALLED", detail: "missing" },
    } },
});
const work = (count = 1): WorkDocument => ({ schema: "mastermind.workspace_work_queue.v1",
  generated_at: "2026-11-04T05:00:00Z", availability: "AVAILABLE", lifecycle_source: null,
  effect_exception: { value: "UNKNOWN", scope: "RUNTIME_CURRENT_WORKER", observable: false, reason: "read_refused" },
  coverage: { count, total: null, truncated: true, completeness: "PARTIAL" },
  groups: Object.fromEntries(WORK_GROUP_ORDER.map(group => [group, group === "WAITING_CAPACITY" ? Array.from({ length: count }, (_, i): WorkRow => ({
    root_job_id: `root-${i}`, lifecycle: { status: "QUEUED", source: "EXECUTIVE_RUNTIME", orchestration_role: null, depth: 0 },
    next_actor: { value: "UNKNOWN", source: null, reason: "unknown", evidence_ref: null, observed_at: null },
    capacity: { value: "WAITING_CAPACITY", source: "Capacity owner", reason: "UNTRUSTED_REASON", evidence_ref: "capacity-receipt", observed_at: null },
    effect: { value: "UNKNOWN", source: null, reason: "unknown", evidence_ref: null, observed_at: null },
    acceptance: { state: "NOT_PROJECTED", producer_owner: null, reason: "product acceptance has no producer in this projection" }, group,
  })) : []])) as WorkDocument["groups"],
  source_observation: { schema: "mastermind.workspace_source_observation.v1", state: "UNKNOWN", selection: null, control_room: null, runtime: null }, reason_codes: [],
});

it("keeps pending and missing inventories unknown without invented hosts or zero slots", () => {
  render(<ResourcesSystemsPanel controlRoom={{ state: "PENDING", ownerRevision: 1 }} work={{ kind: "PENDING" }} />);
  expect(screen.getByText("Reading connected systems…")).toBeTruthy();
  expect(screen.getByText("Provider capacity is not supplied")).toBeTruthy();
  expect(screen.queryByText(/0 slots|StudioUltra|Mac Studio/)).toBeNull();
});
it("inspects installed systems without promoting installation or bindings to readiness", () => {
  const c = control();
  render(<ResourcesSystemsPanel controlRoom={c} work={{ kind: "UNAVAILABLE", reason: "RAW_ERROR_PRIVATE" }} />);
  fireEvent.click(screen.getByRole("button", { name: /Codex/ }));
  const selected = screen.getByRole("region", { name: "Selected resource" });
  expect(within(selected).getByText("Codex")).toBeTruthy();
  expect(within(selected).getByText("No resource-to-work assignment supplied")).toBeTruthy();
  expect(within(selected).getAllByText("Not supplied").length).toBeGreaterThanOrEqual(3);
  fireEvent.click(screen.getByRole("button", { name: /Cursor/ }));
  expect(within(selected).getByText("Cursor")).toBeTruthy();
  expect(screen.queryByText("UNTRUSTED_PRIVATE_DETAIL")).toBeNull();
  expect(screen.queryByText("RAW_ERROR_PRIVATE")).toBeNull();
});
it("shows exact-work evidence and retains partial/truncated scope and safe navigation", () => {
  const open = vi.fn();
  render(<ResourcesSystemsPanel controlRoom={control()} work={{ kind: "DOCUMENT", document: work() }} onOpenWork={open} />);
  expect(screen.getByText("Waiting for capacity")).toBeTruthy();
  expect(screen.getByText(/Partial returned view/)).toBeTruthy();
  expect(screen.getByText(/source omitted work items/)).toBeTruthy();
  expect(screen.getByText("capacity-receipt")).toBeTruthy();
  expect(screen.getByText(/Generated at/)).toBeTruthy();
  expect(screen.queryByText("UNTRUSTED_REASON")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Assigned work" }));
  expect(open).toHaveBeenCalledExactlyOnceWith("root-0");
});
it("limits the first level to eight rows then reveals only returned work", () => {
  render(<ResourcesSystemsPanel controlRoom={control()} work={{ kind: "DOCUMENT", document: work(10) }} />);
  expect(screen.queryByText("root-8")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "See all 10 returned work items" }));
  expect(screen.getByText("root-9")).toBeTruthy();
});
it("removes selected source details when the auth owner clears observations", () => {
  const { rerender } = render(<ResourcesSystemsPanel controlRoom={control()} work={{ kind: "DOCUMENT", document: work() }} />);
  fireEvent.click(screen.getByRole("button", { name: /Codex/ }));
  expect(screen.getByText("1.2.3")).toBeTruthy();
  rerender(<ResourcesSystemsPanel controlRoom={{ state: "UNAVAILABLE", ownerRevision: 2, reason: "SIGNED_OUT" }} work={{ kind: "UNAVAILABLE", reason: "SIGNED_OUT" }} />);
  expect(screen.queryByText("1.2.3")).toBeNull();
  expect(screen.queryByText("root-0")).toBeNull();
});
it("preserves Chinese evidence semantics and routes source inspection through its caller", () => {
  const sources = vi.fn();
  render(<ResourcesSystemsPanel controlRoom={control()} work={{ kind: "UNAVAILABLE", reason: "absent" }} locale="zh-CN" onReviewSources={sources} />);
  expect(screen.getByText("未提供供应商容量")).toBeTruthy();
  expect(screen.getAllByText("未提供").length).toBeGreaterThanOrEqual(3);
  fireEvent.click(screen.getByRole("button", { name: "来源与访问" }));
  expect(sources).toHaveBeenCalledExactlyOnceWith();
});
