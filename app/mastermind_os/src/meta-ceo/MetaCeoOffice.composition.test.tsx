// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetaCeoOffice } from "./MetaCeoOffice";
import { projectOffice, type OfficeInput, type ProjectionContext } from "./projection";
import { decodeMission } from "../mission";
import currentMission from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(cleanup);

const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" }, sessionRef: null, bindingGeneration: null, revisions: { mission: "rev:1", programs: null, result: null, conversation: null } };

function input(): OfficeInput {
  const raw = structuredClone(currentMission);
  raw.read_state = { state: "CURRENT", reason_codes: [], usable_sections: raw.read_state.usable_sections };
  return { programs: null, result: null, conversation: null, mission: {
    context,
    source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "rev:1", observed_at: "2026-10-03T10:00:00Z", state: "CURRENT", coverage: "COMPLETE" },
    value: decodeMission(raw, context.selection!)!,
  } };
}

const office = (text: string, props: Partial<Parameters<typeof MetaCeoOffice>[0]> = {}) => (
  <MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text, context }} onDraftChange={() => {}} {...props} />
);

describe("Meta-CEO Office composition", () => {
  it("localizes the calm headline and marks the section language", () => {
    render(office("", { locale: "zh-CN" }));
    expect(screen.getByRole("heading", { level: 1, name: "Meta-CEO" })).toBeTruthy();
    expect(screen.getByText("给出方向，或提出问题。")).toBeTruthy();
    expect(document.querySelector("section.meta-ceo-office")!.getAttribute("lang")).toBe("zh-CN");
  });

  it("leads with the project title and next action, never a raw execution enum", () => {
    const mission = input().mission!.value!;
    render(office(""));
    const answer = screen.getByRole("region", { name: "Meta-CEO answer" });
    const headline = within(answer).getByRole("heading", { level: 2 });
    expect(headline.textContent).toContain(mission.program.title ?? mission.program.work_ref ?? "");
    const state = mission.execution.state;
    if (state) expect(answer.textContent).not.toContain(String(state));
    const action = mission.program.next_action;
    if (action) expect(within(answer).getByText(action)).toBeTruthy();
    const technical = document.querySelector("details.office-technical")!;
    expect(technical.open).toBe(false);
    if (state) expect(technical.textContent).toContain(String(state));
  });

  it("keeps missing or stale reads plainly scoped without inventing an answer", () => {
    const values = input();
    values.mission!.source.state = "STALE";
    const view = render(<MetaCeoOffice projection={projectOffice(values, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent)
      .toContain("Currentness is not established.");
    (values.mission as unknown as { value: null }).value = null;
    view.rerender(<MetaCeoOffice projection={projectOffice(values, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.getByRole("heading", { name: "The current operating answer is not yet available." })).toBeTruthy();
    expect(screen.getByText("Select a project to view its direction and next step.")).toBeTruthy();
  });

  it("keeps the native continuation gate and offers no fake send when unqualified", () => {
    const view = render(office(""));
    expect(screen.queryByRole("region", { name: "Continue the exact selected Executive session" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send unavailable" }).disabled).toBe(true);
    expect(screen.getByText("Sending is unavailable in this context. You can keep and review this draft.")).toBeTruthy();
    const qualified: ProjectionContext = { ...context, sessionRef: "session:exec-1", bindingGeneration: 7 };
    const qualifiedInput = input(); qualifiedInput.mission!.context = qualified;
    view.rerender(<MetaCeoOffice projection={projectOffice(qualifiedInput, qualified)} draft={{ text: "", context: qualified }}
      onDraftChange={() => {}} nativeContinuation={<button type="button">Continue on the Executive session</button>} />);
    expect(screen.getByRole("region", { name: "Continue the exact selected Executive session" }).textContent)
      .toContain("Continue on the Executive session");
    expect(screen.queryByRole("button", { name: "Send unavailable" })).toBeNull();
  });

  it("opens the actual selected project only from the explicit View project gesture", () => {
    const onOpenProject = vi.fn();
    const mission = input().mission!.value!;
    const view = render(office("", { onOpenProject }));
    expect(onOpenProject).not.toHaveBeenCalled();
    const expected = { workRef: context.selection!.workRef, rootJobId: context.selection!.rootJobId };
    const aligned = mission.program.work_ref === expected.workRef && mission.mission.root_job_id === expected.rootJobId;
    const button = screen.getByRole("button", { name: "View project" });
    expect(button.disabled).toBe(!aligned);
    if (aligned) {
      fireEvent.click(button);
      expect(onOpenProject).toHaveBeenCalledTimes(1);
      expect(onOpenProject).toHaveBeenCalledWith(expected);
    }
    onOpenProject.mockClear();
    view.rerender(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.queryByRole("button", { name: "View project" })).toBeNull();
    expect(onOpenProject).not.toHaveBeenCalled();
  });

  it("does not turn missing attention data into a decision verdict or action", () => {
    const values = input();
    (values.mission!.value!.principal as { owed_turn?: unknown }).owed_turn = undefined;
    const view = render(<MetaCeoOffice projection={projectOffice(values, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    const aside = screen.getByRole("region", { name: "Decisions not yet known." });
    expect(aside.textContent).toContain("This view does not establish whether a decision needs you.");
    expect(within(aside).queryAllByRole("button")).toHaveLength(0);
    values.mission!.value!.principal.owed_turn = { seat: "chairman", reason: "Reserved decision from owner.",
      source_refs: [{ owner: "EXECUTIVE_OS", ref: "decision:one", observed_at: "2026-10-04T08:00:00Z", freshness: "current" }] };
    view.rerender(<MetaCeoOffice projection={projectOffice(values, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.getByRole("region", { name: "The owner has requested Chairman attention." }).textContent)
      .toContain("Reserved decision from owner.");
  });

  it("keeps authored objective, configuration, fabric and receipts closed but reachable", () => {
    const opened = vi.fn();
    render(office("", { onInspectWorkerResult: opened }));
    const objective = document.querySelector("details.office-objective")!;
    expect(objective.open).toBe(false);
    expect(objective.textContent).toContain("not accepted company direction");
    const config = document.querySelector("details.office-config")!;
    expect(config.open).toBe(false);
    fireEvent.click(config.querySelector("summary")!);
    expect(config.open).toBe(true);
    expect(within(config).getByRole("button", { name: "Refresh configuration" })).toBeTruthy();
    const fabric = screen.getByText("Subagent Fabric · inspect execution").closest("details")!;
    expect(fabric.open).toBe(false);
    const technical = document.querySelector("details.office-technical")!;
    expect(technical.open).toBe(false);
    expect(technical.textContent).toContain("Delivery, effect and acceptance receipts");
    expect(technical.querySelector('[aria-label="Independent receipts"]')).toBeTruthy();
    fireEvent.click(technical.querySelector("summary")!);
    const review = screen.getByRole("button", { name: "Review sources" });
    fireEvent.click(review);
    expect(screen.getByText("Exact source provenance")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close sources" }));
    expect(screen.queryByText("Exact source provenance")).toBeNull();
  });

  it("keeps the exact draft through preview inspection and returns focus on close", () => {
    const view = render(office("Hold this exact draft line."));
    const textarea = screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement;
    expect(textarea.value).toBe("Hold this exact draft line.");
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    const preview = screen.getByRole("region", { name: "Direction preview" });
    expect(preview.textContent).toContain("Hold this exact draft line.");
    expect(textarea.value).toBe("Hold this exact draft line.");
    fireEvent.click(within(preview).getByRole("button", { name: "Close preview" }));
    expect(screen.queryByRole("region", { name: "Direction preview" })).toBeNull();
    expect(textarea.value).toBe("Hold this exact draft line.");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review direction preview" }));
  });
});
