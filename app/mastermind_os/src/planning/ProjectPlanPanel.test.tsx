// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
afterEach(() => cleanup());
import { ProjectPlanPanel, type ProjectPlanReader } from "./ProjectPlanPanel";
import { decodeProjectPlan, type ProjectPlanRead, type ProjectPlanSelection } from "./project-plan";
import v2Fixture from "../fixtures/project-plan-v2-owner.json";

const selection: ProjectPlanSelection = { work_ref: "WS:PLAN-VISIBILITY" };
const commit0 = "a".repeat(40);
const commit1 = "c".repeat(40);
const digest0 = "b".repeat(64);
const digest1 = "d".repeat(64);
const CANONICAL = "mastermindx-market-intelligence/macro";

function availableBody(title = "Work visibility baseline",
    workRef = selection.work_ref): ProjectPlanRead {
  return {
    schema: "mastermind.workspace_project_plan.v1",
    selection: { work_ref: workRef },
    availability: "AVAILABLE",
    source: {
      repository: CANONICAL, commit: commit0,
      path: `agentos/workstreams/WS-${workRef.slice(3)}.md`, content_sha256: digest0,
    },
    plan: {
      title, objective: "Finish current work, then confirm the session can resume.",
      status: "active", owner: "Project continuity",
      next_action: "Show workspace updates and preview the direction draft.",
      waves: [
        { id: "W1", title: "Read model", status: "in_progress", depends_on: [],
          next_action: "Install the read model behind the existing host.", prs: [5593] },
        { id: "W2", title: "Session continuity", status: "proposed", depends_on: ["W1"],
          next_action: null, prs: [] },
      ],
      adoption: { state: "UNAVAILABLE", reason: "NOT_DECLARED" },
      version_history: {
        state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS",
        revisions: [
          { commit: commit0, committed_at: "2026-11-03T12:00:00Z", content_sha256: digest0 },
          { commit: commit1, committed_at: "2026-10-29T09:30:00Z", content_sha256: digest1 },
        ],
      },
    },
    reason_codes: [],
  };
}

function unavailableBody(reasonCode: string): ProjectPlanRead {
  return {
    schema: "mastermind.workspace_project_plan.v1",
    selection: { ...selection },
    availability: "UNAVAILABLE", source: null, plan: null, reason_codes: [reasonCode],
  } as ProjectPlanRead;
}

const mount = (read: ProjectPlanReader, props: {
  selection?: ProjectPlanSelection | null; sourceGeneration?: () => number;
  canRead?: () => boolean; locale?: "en" | "zh-CN";
} = {}) => render(<ProjectPlanPanel
  selection={props.selection !== undefined ? props.selection : selection} read={read}
  sourceGeneration={props.sourceGeneration ?? (() => 7)}
  canRead={props.canRead ?? (() => true)} locale={props.locale} />);

describe("project plan panel", () => {
  it("reads once on authorized mount and shows the authored record with real history", async () => {
    const read = vi.fn<ProjectPlanReader>(async () => availableBody());
    mount(read);
    expect(await screen.findByRole("heading", { name: "Work visibility baseline", level: 3 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Plan", level: 2 })).toBeTruthy();
    expect(screen.getByText("Finish current work, then confirm the session can resume.")).toBeTruthy();
    expect(screen.getByText("active")).toBeTruthy();
    expect(screen.getByText("Project continuity")).toBeTruthy();
    expect(screen.getByText("Depends on: W1")).toBeTruthy();
    expect(screen.getByText("Next action: Install the read model behind the existing host.")).toBeTruthy();
    const pr = screen.getByRole("link", { name: "#5593" });
    expect(pr).toHaveProperty("href", `https://github.com/${CANONICAL}/pull/5593`);
    expect(screen.getByText("Record revision history")).toBeTruthy();
    expect(screen.getByText("aaaaaaaaaa")).toBeTruthy();
    // Authored timestamps surface both collapsed and expanded, never truncated.
    expect(screen.getAllByText("2026-11-03T12:00:00Z")).toHaveLength(2);
    expect(screen.getByText(/does not declare plan adoption/)).toBeTruthy();
    expect(screen.queryByText("Adopted versions")).toBeNull();
    const adoption = screen.getByText(/does not declare plan adoption/);
    const facts = screen.getByText("Record status");
    expect(adoption.compareDocumentPosition(facts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledWith(expect.objectContaining({
      work_ref: selection.work_ref, signal: expect.any(AbortSignal) }));
  });

  it("shows at most eight waves initially with a disclosure for the remainder", async () => {
    const body = availableBody();
    body.plan!.waves = Array.from({ length: 10 }, (_, index) => ({
      id: "W" + (index + 1), title: "Wave " + (index + 1), status: "todo",
      depends_on: [], next_action: null, prs: [] }));
    mount(vi.fn(async () => body));
    expect(await screen.findByText("Wave 8")).toBeTruthy();
    expect(screen.queryByText("Wave 9")).toBeNull();
    const disclose = screen.getByRole("button", { name: "See all 10 waves" });
    expect(disclose.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(disclose);
    expect(screen.getByText("Wave 9")).toBeTruthy();
    expect(screen.getByText("Wave 10")).toBeTruthy();
    expect(disclose.getAttribute("aria-expanded")).toBe("true");
  });

  it("explains an empty wave list without inferring zero work", async () => {
    const body = availableBody();
    body.plan!.waves = [];
    mount(vi.fn(async () => body));
    expect(await screen.findByText(/declares no waves/)).toBeTruthy();
    expect(screen.getByText(/not evidence that work is complete/)).toBeTruthy();
  });

  it("renders typed unavailability without any plan content", async () => {
    mount(vi.fn(async () => unavailableBody("RECORD_NOT_FOUND")));
    expect(await screen.findByText(/RECORD_NOT_FOUND/)).toBeTruthy();
    expect(screen.getByText(/project-plan source is unavailable/)).toBeTruthy();
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
  });

  it("reports a refused read and re-acquires exactly once per Refresh", async () => {
    const read = vi.fn<ProjectPlanReader>()
      .mockRejectedValueOnce(new Error("transport refused"))
      .mockResolvedValueOnce(availableBody());
    mount(read);
    expect(await screen.findByText(/failed or was refused/)).toBeTruthy();
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText("Work visibility baseline")).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("does not read without the authorization and source owners", () => {
    const read = vi.fn<ProjectPlanReader>(async () => availableBody());
    mount(read, { canRead: () => false });
    expect(screen.getByText(/This project’s recorded plan is unavailable here/)).toBeTruthy();
    expect(read).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Refresh" })).toHaveProperty("disabled", true);
  });

  it("does not read a malformed selector or a missing selection", () => {
    const read = vi.fn<ProjectPlanReader>(async () => availableBody());
    render(<ProjectPlanPanel selection={{ work_ref: "JOB-9" } as unknown as ProjectPlanSelection}
      read={read} sourceGeneration={() => 1} canRead={() => true} />);
    expect(read).not.toHaveBeenCalled();
    mount(read, { selection: null });
    expect(read).not.toHaveBeenCalled();
    expect(screen.getAllByText(/This project’s recorded plan is unavailable here/)).toHaveLength(2);
  });

  it("masks published content on the same render as generation rotation", async () => {
    let generation = 3;
    const read = vi.fn<ProjectPlanReader>(async () => availableBody());
    const props = { selection, read, sourceGeneration: () => generation, canRead: () => true };
    const view = render(<ProjectPlanPanel {...props} />);
    expect(await screen.findByText("Work visibility baseline")).toBeTruthy();
    generation = 4;
    view.rerender(<ProjectPlanPanel {...props} />);
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("requires a fresh acquisition after sign-out and regrant", async () => {
    let granted = true;
    let calls = 0;
    const read = vi.fn<ProjectPlanReader>(async () => {
      calls += 1;
      return availableBody(calls === 1 ? "Work visibility baseline" : "Fresh baseline");
    });
    const props = { selection, read, sourceGeneration: () => 5, canRead: () => granted };
    const view = render(<ProjectPlanPanel {...props} />);
    expect(await screen.findByText("Work visibility baseline")).toBeTruthy();

    granted = false;
    view.rerender(<ProjectPlanPanel {...props} />);
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(screen.getByRole("button", { name: "Refresh" })).toHaveProperty("disabled", true);

    granted = true;
    view.rerender(<ProjectPlanPanel {...props} />);
    // Content returns only through a new acquisition carrying the new body.
    expect(await screen.findByText("Fresh baseline")).toBeTruthy();
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("never publishes a response that arrives after revocation", async () => {
    let granted = true;
    let release!: (value: ProjectPlanRead) => void;
    const read = vi.fn<ProjectPlanReader>(() =>
      new Promise<ProjectPlanRead>(resolve => { release = resolve; }));
    const props = { selection, read, sourceGeneration: () => 11, canRead: () => granted };
    const view = render(<ProjectPlanPanel {...props} />);
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    granted = false;
    view.rerender(<ProjectPlanPanel {...props} />);
    await act(async () => { release(availableBody()); });
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(screen.getByText(/This project’s recorded plan is unavailable here/)).toBeTruthy();
  });

  it("never publishes a response that arrives after a generation change", async () => {
    let generation = 7;
    let release!: (value: ProjectPlanRead) => void;
    const read = vi.fn<ProjectPlanReader>(() =>
      new Promise<ProjectPlanRead>(resolve => { release = resolve; }));
    const props = { selection, read, sourceGeneration: () => generation, canRead: () => true };
    const view = render(<ProjectPlanPanel {...props} />);
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    generation = 8;
    view.rerender(<ProjectPlanPanel {...props} />);
    await act(async () => { release(availableBody()); });
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(screen.getByText(/Refresh to view this project’s recorded plan/)).toBeTruthy();
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("aborts the previous acquisition and reads once for a new selection", async () => {
    const requests: Array<ProjectPlanSelection & { signal: AbortSignal }> = [];
    const pending = new Promise<ProjectPlanRead>(() => {});
    const read = vi.fn<ProjectPlanReader>(request => {
      requests.push(request);
      return request.work_ref === selection.work_ref
        ? pending
        : Promise.resolve(availableBody("Fresh baseline", "WS:OTHER-PLAN"));
    });
    const props = { read, sourceGeneration: () => 2, canRead: () => true };
    const view = render(<ProjectPlanPanel selection={selection} {...props} />);
    await waitFor(() => expect(requests).toHaveLength(1));
    view.rerender(<ProjectPlanPanel selection={{ work_ref: "WS:OTHER-PLAN" }} {...props} />);
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(requests[0].signal.aborted).toBe(true);
    expect(await screen.findByText("Fresh baseline")).toBeTruthy();
    expect(requests).toHaveLength(2);
    expect(requests[1].work_ref).toBe("WS:OTHER-PLAN");
    expect(requests[1].signal.aborted).toBe(false);
  });

  it("aborts the in-flight read on unmount", async () => {
    const requests: Array<ProjectPlanSelection & { signal: AbortSignal }> = [];
    const read = vi.fn<ProjectPlanReader>(request => {
      requests.push(request);
      return new Promise<ProjectPlanRead>(() => {});
    });
    const view = mount(read);
    await waitFor(() => expect(requests).toHaveLength(1));
    view.unmount();
    expect(requests[0].signal.aborted).toBe(true);
  });

  it("re-acquires freshly when the reader is replaced and masks the old body meanwhile", async () => {
    const readA = vi.fn<ProjectPlanReader>(async () => availableBody("Work visibility baseline"));
    const view = render(<ProjectPlanPanel selection={selection} read={readA}
      sourceGeneration={() => 9} canRead={() => true} />);
    expect(await screen.findByText("Work visibility baseline")).toBeTruthy();
    const readB = vi.fn<ProjectPlanReader>(async () => availableBody("Fresh baseline"));
    view.rerender(<ProjectPlanPanel selection={selection} read={readB}
      sourceGeneration={() => 9} canRead={() => true} />);
    expect(screen.queryByText("Work visibility baseline")).toBeNull();
    expect(await screen.findByText("Fresh baseline")).toBeTruthy();
    expect(readA).toHaveBeenCalledTimes(1);
    expect(readB).toHaveBeenCalledTimes(1);
  });

  it("does not refetch on stable re-renders", async () => {
    const read = vi.fn<ProjectPlanReader>(async () => availableBody());
    const props = { selection, read, sourceGeneration: () => 5, canRead: () => true };
    const view = render(<ProjectPlanPanel {...props} />);
    expect(await screen.findByText("Work visibility baseline")).toBeTruthy();
    view.rerender(<ProjectPlanPanel {...props} />);
    view.rerender(<ProjectPlanPanel {...props} />);
    expect(read).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Work visibility baseline")).toBeTruthy();
  });

  it("marks the surface busy and disables Refresh while reading", async () => {
    const read = vi.fn<ProjectPlanReader>(() => new Promise<ProjectPlanRead>(() => {}));
    mount(read);
    await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Reading…" })).toHaveProperty("disabled", true);
    expect(screen.getByText(/Reading the project plan/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Project plan" }).getAttribute("aria-busy")).toBe("true");
  });

  it("keeps the source identity behind an accessible disclosure", async () => {
    mount(vi.fn(async () => availableBody()));
    expect(await screen.findByText("Work visibility baseline")).toBeTruthy();
    const summary = screen.getByText("Source details");
    const details = summary.closest("details");
    expect(details).toHaveProperty("open", false);
    fireEvent.click(summary);
    expect(details).toHaveProperty("open", true);
    expect(screen.getByText("agentos/workstreams/WS-PLAN-VISIBILITY.md")).toBeTruthy();
    // The pinned digest matches the current revision's digest, by contract.
    expect(screen.getAllByText(digest0)).toHaveLength(2);
    expect(screen.getByText(/record and revision used for this view/)).toBeTruthy();
  });

  it("shows typed record-revision unavailability without inventing adopted versions", async () => {
    const body = availableBody();
    body.plan!.version_history = { state: "UNAVAILABLE", reason: "NOT_SUPPLIED_BY_OWNER" };
    mount(vi.fn(async () => body));
    expect(await screen.findByText(/did not supply revision history/)).toBeTruthy();
    expect(screen.getByText("Record revision history")).toBeTruthy();
    expect(screen.getByText("Work visibility baseline")).toBeTruthy();
    expect(screen.queryByText("Adopted versions")).toBeNull();
    const adoption = screen.getByText(/does not declare plan adoption/);
    const facts = screen.getByText("Record status");
    expect(adoption.compareDocumentPosition(facts) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("localizes the surface for zh-CN", async () => {
    mount(vi.fn(async () => availableBody()), { locale: "zh-CN" });
    expect(await screen.findByRole("heading", { name: "计划", level: 2 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Work visibility baseline", level: 3 })).toBeTruthy();
    expect(screen.getByRole("button", { name: "刷新" })).toBeTruthy();
    expect(screen.getByText(/未声明计划采用状态/)).toBeTruthy();
    expect(screen.getByText("记录修订历史")).toBeTruthy();
    expect(screen.getByText(/采用状态另行显示/)).toBeTruthy();
    expect(screen.queryByText("Record revision history")).toBeNull();
    expect(screen.queryByText(/does not declare plan adoption/)).toBeNull();
  });
});


it("does not call a retained reader if permission changes before a Refresh click", async () => {
  let granted = true;
  const read = vi.fn<ProjectPlanReader>(async () => availableBody());
  const props = { selection, read, sourceGeneration: () => 7, canRead: () => granted };
  render(<ProjectPlanPanel {...props} />);
  expect(await screen.findByText("Work visibility baseline")).toBeTruthy();
  granted = false;
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  expect(read).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("Work visibility baseline")).toBeNull();
});

it("rejects a trailing-newline selector through the sole authoritative selector validator", () => {
  const read = vi.fn<ProjectPlanReader>(async () => availableBody());
  mount(read, { selection: { work_ref: "WS:PLAN-VISIBILITY\n" } });
  expect(read).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Refresh" })).toHaveProperty("disabled", true);
});


it("composes the objective from the same fenced reader without a second read or stale header",async()=>{
  const read=vi.fn(async()=>availableBody()), generation=()=>1;
  let allowed=true;const canRead=()=>allowed;
  const renderWorkspace=({objective,panel}:{objective:string|null;panel:React.ReactNode})=><><h1>{objective??"Objective unavailable"}</h1>{panel}</>;
  const view=render(<ProjectPlanPanel selection={selection} read={read} canRead={canRead} sourceGeneration={generation} renderWorkspace={renderWorkspace}/>);
  expect(await screen.findByRole("heading",{level:1,name:"Finish current work, then confirm the session can resume."})).toBeTruthy();
  expect(read).toHaveBeenCalledTimes(1);
  allowed=false;
  view.rerender(<ProjectPlanPanel selection={selection} read={read} canRead={canRead} sourceGeneration={generation} renderWorkspace={renderWorkspace}/>);
  expect(screen.getByRole("heading",{level:1,name:"Objective unavailable"})).toBeTruthy();
  expect(screen.queryByText("Work visibility baseline")).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});

it("renders v2 comparison and header from one fenced real-decoder result and masks both on revocation", async () => {
  const current = { work_ref: "WS:PLAN-TEST" };
  const body = decodeProjectPlan(v2Fixture.cases.available_pending, current);
  let granted = true;
  const read = vi.fn<ProjectPlanReader>(async () => body);
  const props = { selection: current, read, canRead: () => granted, sourceGeneration: () => 8,
    renderWorkspace: ({objective,panel}: {objective: string|null;panel: React.ReactNode}) => <><h1>{objective ?? "No objective"}</h1>{panel}</> };
  const view = render(<ProjectPlanPanel {...props} />);
  expect(await screen.findByRole("heading", { level: 1, name: "Real available objective." })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Plan comparison", level: 3 })).toBeTruthy();
  const comparison = screen.getByRole("heading", { name: "Plan comparison" });
  for (const title of ["Waves", "Record revision history"])
    expect(comparison.compareDocumentPosition(screen.getByRole("heading", {name:title})) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getAllByText("PLAN-PROPOSAL").length).toBeGreaterThan(0);
  expect(screen.queryByText(/does not declare plan adoption/)).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
  granted = false; view.rerender(<ProjectPlanPanel {...props} />);
  expect(screen.queryByRole("heading", { name: "Plan comparison" })).toBeNull();
  expect(screen.queryAllByText("PLAN-PROPOSAL")).toHaveLength(0);
  expect(screen.getByRole("heading", { level: 1, name: "No objective" })).toBeTruthy();
  expect(read).toHaveBeenCalledTimes(1);
});
