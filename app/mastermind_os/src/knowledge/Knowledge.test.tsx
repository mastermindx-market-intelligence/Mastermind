// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Knowledge } from "./Knowledge";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceState } from "../meta-ceo/projection";
import { decodeMission } from "../mission";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(cleanup);
const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: null, bindingGeneration: null, revisions: { mission: "rev:1", programs: null, result: null, conversation: null } };
function input(state: SourceState = "CURRENT"): OfficeInput {
  const raw = structuredClone(fixture);
  raw.read_state.state = "CURRENT";
  const mission = decodeMission(raw, context.selection!)!;
  for (const section of [mission.program, mission.mission, mission.principal, mission.execution, mission.review, mission.transport, mission.acceptance, mission.posture]) section.evidence = [];
  mission.program.evidence = [{ owner: "GITHUB", ref: "https://github.com/example/repo/pull/42", field: "review", source_revision: "exact:42",
    source_time: "2026-10-01T10:00:00Z", observed_at: "2026-10-04T08:00:00Z", freshness_state: "CURRENT" }];
  return { programs: null, result: null, conversation: null, mission: { context, value: mission,
    source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "rev:1", observed_at: "2026-10-04T08:00:00Z", state, coverage: "COMPLETE" } } };
}
describe("Knowledge owner-reference view", () => {
  it("shows exact owner provenance without inventing canonical record content", () => {
    const open = vi.fn(); render(<Knowledge projection={projectOffice(input(), context)} onOpenSource={open} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    const detail = screen.getByRole("region", { name: "Selected source reference" });
    expect(detail.textContent).toContain("exact:42"); expect(detail.textContent).toContain("2026-10-01T10:00:00Z");
    expect(detail.textContent).toContain("2026-10-04T08:00:00Z");
    expect(detail.textContent).toContain("Original record content has not been supplied");
    fireEvent.click(screen.getByRole("button", { name: "Open original source" }));
    expect(open).toHaveBeenCalledExactlyOnceWith({ owner: "GITHUB", ref: "https://github.com/example/repo/pull/42", revision: "exact:42", mode: "current" });
    expect(screen.getByText(/Decision, discovery, handoff and contract indexes are unavailable/)).toBeTruthy();
  });
  it.each<SourceState>(["CURRENT", "STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])("preserves %s without reconstructing private references", state => {
    render(<Knowledge projection={projectOffice(input(state), context)} />);
    expect(screen.getByRole("region", { name: "Knowledge source" }).textContent).toContain(state);
    expect(!!screen.queryByRole("button", { name: "Inspect Program · review" })).toBe(["CURRENT", "STALE"].includes(state));
    if (!["CURRENT", "STALE"].includes(state)) expect(document.body.textContent).not.toContain("example/repo");
    expect(screen.getByText(/Company-wide coverage is not established/)).toBeTruthy();
  });
  it("keeps partial or missing reference provenance UNKNOWN even with a current Mission", () => {
    const i = input(); i.mission!.value!.program.evidence[0].source_revision = null;
    render(<Knowledge projection={projectOffice(i, context)} onOpenSource={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    expect(screen.getByRole("region", { name: "Selected source reference" }).textContent).toContain("UNKNOWN");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Open original source" }).disabled).toBe(true);
  });
  it("opens retained sources only as history and restores keyboard focus", () => {
    const open = vi.fn(); render(<Knowledge projection={projectOffice(input("STALE"), context)} onOpenSource={open} />);
    const trigger = screen.getByRole("button", { name: "Inspect Program · review" });
    fireEvent.click(trigger);
    const detail = screen.getByRole("region", { name: "Selected source reference" });
    expect(document.activeElement).toBe(detail);
    fireEvent.click(screen.getByRole("button", { name: "Open original source" }));
    expect(open.mock.calls[0][0].mode).toBe("history");
    fireEvent.keyDown(detail, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it.each([
    { state: "CURRENT" as const, key: "{Enter}" }, { state: "CURRENT" as const, key: " " },
    { state: "STALE" as const, key: "{Enter}" }, { state: "STALE" as const, key: " " },
  ])("refocuses the same $state reference on keyboard reactivation with $key", async ({ state, key }) => {
    const user = userEvent.setup(); render(<Knowledge projection={projectOffice(input(state), context)} />);
    const trigger = screen.getByRole("button", { name: "Inspect Program · review" });
    await user.click(trigger);
    const detail = screen.getByRole("region", { name: "Selected source reference" });
    expect(document.activeElement).toBe(detail);
    trigger.focus(); expect(document.activeElement).toBe(trigger);
    await user.keyboard(key);
    expect(document.activeElement).toBe(detail);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("focuses a different reference and restores its own invoking trigger", async () => {
    const user = userEvent.setup(), i = input();
    i.mission!.value!.mission.evidence = [{ ...i.mission!.value!.program.evidence[0],
      ref: "https://github.com/example/repo/pull/43", source_revision: "exact:43" }];
    render(<Knowledge projection={projectOffice(i, context)} />);
    await user.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    const trigger = screen.getByRole("button", { name: "Inspect Mission · review" });
    trigger.focus(); await user.keyboard("{Enter}");
    const detail = screen.getByRole("region", { name: "Selected source reference" });
    expect(document.activeElement).toBe(detail); expect(detail.textContent).toContain("exact:43");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
  it("preserves outside focus through passive rerenders and unrelated revision round trips", () => {
    const i = input(), r = render(<Knowledge projection={projectOffice(i, context)} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    const detail = screen.getByRole("region", { name: "Selected source reference" });
    const search = screen.getByRole("searchbox", { name: "Search supplied knowledge" });
    search.focus();
    for (const next of [context, { ...context, revisions: { ...context.revisions, programs: "rev:2" } }, context]) {
      r.rerender(<Knowledge projection={projectOffice(i, next)} />);
      expect(document.activeElement).toBe(search);
      expect(screen.getByRole("region", { name: "Selected source reference" })).toBe(detail);
    }
  });
  it("does not autofocus when source invalidation and restoration clear the selection", () => {
    const view = (state: SourceState) => <><button type="button">Outside knowledge</button><Knowledge projection={projectOffice(input(state), context)} /></>;
    const r = render(view("CURRENT"));
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    const outside = screen.getByRole("button", { name: "Outside knowledge" }); outside.focus();
    for (const state of ["UNKNOWN", "CURRENT"] as const) {
      r.rerender(view(state));
      expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
      expect(document.activeElement).toBe(outside);
    }
  });
  it("clears selection on a passive Mission revision without autofocus", () => {
    const i = input(), view = (c: ProjectionContext) => <><button type="button">Outside knowledge</button><Knowledge projection={projectOffice(i, c)} /></>;
    const r = render(view(context));
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    const outside = screen.getByRole("button", { name: "Outside knowledge" }); outside.focus();
    r.rerender(view({ ...context, revisions: { ...context.revisions, mission: "rev:2" } }));
    expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
    expect(document.activeElement).toBe(outside);
  });
  it("returns Escape focus to search when its invoking trigger was filtered out", async () => {
    const user = userEvent.setup(); render(<Knowledge projection={projectOffice(input(), context)} />);
    const trigger = screen.getByRole("button", { name: "Inspect Program · review" });
    await user.click(trigger);
    const search = screen.getByRole("searchbox", { name: "Search supplied knowledge" });
    await user.type(search, "absent"); expect(trigger.isConnected).toBe(false);
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close source context" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
    expect(document.activeElement).toBe(search);
  });
  it("does not treat a PARTIAL reference as current inside a current Mission", () => {
    const i = input(); i.mission!.value!.program.evidence[0].freshness_state = "PARTIAL";
    render(<Knowledge projection={projectOffice(i, context)} onOpenSource={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    expect(screen.getByRole("region", { name: "Selected source reference" }).textContent).toContain("UNKNOWN");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Open original source" }).disabled).toBe(true);
  });
  it("searches only supplied references and never infers that a missing match means zero knowledge", () => {
    render(<Knowledge projection={projectOffice(input(), context)} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search supplied knowledge" }), { target: { value: "absent" } });
    expect(screen.getByText("No supplied references match this search.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Inspect Program · review" })).toBeNull();
  });
  it("clears open source context and search text on the first auth-change render", () => {
    const i = input(), r = render(<Knowledge projection={projectOffice(i, context)} />);
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search supplied knowledge" }), { target: { value: "private search" } });
    r.rerender(<Knowledge projection={projectOffice(i, { ...context, authGeneration: 2 })} />);
    expect(screen.queryByRole("region", { name: "Selected source reference" })).toBeNull();
    expect(document.body.textContent).not.toContain("example/repo");
    expect(screen.getByRole<HTMLInputElement>("searchbox", { name: "Search supplied knowledge" }).value).toBe("");
  });
});
