// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import fixture from "../fixtures/project-plan-v2-owner.json";
import { ProjectPlanPanel, type ProjectPlanPanelProps, type ProjectPlanReader } from "./ProjectPlanPanel";
import { decodeProjectPlan } from "./project-plan";

afterEach(cleanup);
const selection = { work_ref: "WS:PLAN-TEST" };
const body = () => decodeProjectPlan(fixture.cases.no_captured_proposal, selection);
type WorkspaceView = Parameters<NonNullable<ProjectPlanPanelProps["renderWorkspace"]>>[0];

function mount(read: ProjectPlanReader, generation = () => 7, canRead = () => true) {
  const captured: { view: WorkspaceView | null } = { view: null };
  const props: ProjectPlanPanelProps = {
    selection, read, sourceGeneration: generation, canRead,
    renderWorkspace: view => { captured.view = view; return view.panel; },
  };
  const rendered = render(<ProjectPlanPanel {...props}/>);
  const launch = () => {
    const value = captured.view?.launchInspection;
    if (!value) throw new Error("A current launch inspection is required");
    return value;
  };
  return { ...rendered, props, captured, launch };
}

describe("project launch uses the panel's qualified acquisition", () => {
  it("offers the current plan without requiring a selected proposal or a second read", async () => {
    const value = body();
    const read = vi.fn<ProjectPlanReader>(async () => value);
    const view = mount(read);
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    expect(view.captured.view?.inspection).toBeNull();
    expect(view.launch().read).toBe(value);
    expect(view.launch().selection).toEqual(selection);
    expect(view.launch().isCurrent()).toBe(true);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("detects source generation changes at click time without needing another render", async () => {
    let generation = 7;
    const view = mount(async () => body(), () => generation);
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    const captured = view.launch();
    generation += 1;
    expect(captured.isCurrent()).toBe(false);
  });

  it("invalidates the captured source when the project panel unmounts", async () => {
    const view = mount(async () => body());
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    const captured = view.launch();
    view.unmount();
    expect(captured.isCurrent()).toBe(false);
  });

  it("invalidates the old acquisition immediately when the user refreshes", async () => {
    let resolve: ((value: ReturnType<typeof body>) => void) | undefined;
    const read = vi.fn<ProjectPlanReader>()
      .mockResolvedValueOnce(body())
      .mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    const view = mount(read);
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    const captured = view.launch();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    expect(captured.isCurrent()).toBe(false);
    expect(view.captured.view?.launchInspection).toBeNull();
    resolve!(body());
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    expect(view.launch().isCurrent()).toBe(true);
    expect(captured.isCurrent()).toBe(false);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("never revives an old capture after observed permission revocation and regrant", async () => {
    let allowed = true;
    const canRead = () => allowed;
    const read = vi.fn<ProjectPlanReader>(async () => body());
    const view = mount(read, () => 7, canRead);
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    const captured = view.launch();
    allowed = false;
    view.rerender(<ProjectPlanPanel {...view.props}/>);
    expect(captured.isCurrent()).toBe(false);
    expect(view.captured.view?.launchInspection).toBeNull();
    allowed = true;
    view.rerender(<ProjectPlanPanel {...view.props}/>);
    await waitFor(() => expect(view.captured.view?.launchInspection).toBeTruthy());
    expect(view.launch().isCurrent()).toBe(true);
    expect(captured.isCurrent()).toBe(false);
  });

  it("does not offer an unavailable plan as launch context", async () => {
    const unavailable = decodeProjectPlan({
      schema: "mastermind.workspace_project_plan.v1", selection,
      availability: "UNAVAILABLE", source: null, plan: null, reason_codes: ["SOURCE_UNAVAILABLE"],
    }, selection);
    const view = mount(async () => unavailable);
    await screen.findByText(/source record is currently unreadable/);
    expect(view.captured.view?.launchInspection).toBeNull();
  });
});
