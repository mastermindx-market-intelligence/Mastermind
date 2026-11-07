// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import acceptedFixture from "../fixtures/mission-v4-owner-accepted.json";
import partialFixture from "../fixtures/mission-v3-owner-current-operator-harness.json";
import { decodeMissionv3 } from "../mission";
import { captureMissionOfficeRead, completeMissionOfficeRead } from "../meta-ceo/mission-adapter";
import { projectOffice, type ProjectionContext } from "../meta-ceo/projection";
import { OrganizationWorkspace } from "./OrganizationWorkspace";

afterEach(cleanup);

// Existing producer export through the actual decoder and Office qualifier.
// Explicit mutations below are consumer regressions, never live source evidence.
function observed(raw: unknown = structuredClone(acceptedFixture.mission), workRef = "WS:FIXTURE") {
  const context: ProjectionContext = {
    authGeneration: 3, selection: { workRef, rootJobId: "JOB-001" },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: null, programs: null, result: null, conversation: null },
  };
  const mission = decodeMissionv3(raw, context.selection!);
  if (!mission) throw new Error("Owner fixture failed the existing decoder");
  const read = completeMissionOfficeRead(captureMissionOfficeRead(context), context, mission, "2026-11-07T07:00:00Z");
  if (read.kind !== "observed") throw new Error("Expected an observed Mission");
  return {
    binding: read.context,
    missionProjection: projectOffice({ mission: read.snapshot, programs: null, result: null, conversation: null }, read.context),
    missionState: "CURRENT" as const,
  };
}

describe("Organization work navigation and actionable context", () => {
  it("keeps the selected work and search across a qualified same-target source refresh", () => {
    const view = render(<OrganizationWorkspace {...observed()} />);
    const jobs = screen.getByRole("list", { name: "Observed jobs" });
    fireEvent.click(within(jobs).getByRole("button", { name: /JOB-005/ }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "JOB-005" } });
    const next = structuredClone(acceptedFixture.mission);
    next.source.owner_observation.control_room.document_digest = "b".repeat(64);
    view.rerender(<OrganizationWorkspace {...observed(next)} />);
    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toBe("JOB-005");
    expect(screen.getByRole("region", { name: "Job JOB-005" })).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Observed jobs" })).getAllByRole("button")).toHaveLength(1);
  });

  it("returns keyboard focus to the chosen work and allows reopening the same detail", async () => {
    const user = userEvent.setup();
    render(<OrganizationWorkspace {...observed()} />);
    const row = within(screen.getByRole("list", { name: "Observed jobs" }))
      .getByRole("button", { name: /JOB-003/ });
    await user.click(row);
    const detail = screen.getByRole("region", { name: "Job JOB-003" });
    expect(document.activeElement).toBe(detail);
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(row);
    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(detail);
    await user.click(within(detail).getByRole("button", { name: "Back to work list" }));
    expect(document.activeElement).toBe(row);
  });

  it("shows the actual current task, reported problem and supplied next step", () => {
    const raw = structuredClone(acceptedFixture.mission);
    raw.mission.title = "Verify the retained operator result";
    raw.execution.errors_present = true;
    raw.execution.next_actions = ["Inspect the failed attempt before correcting.", "Keep the original request."];
    render(<OrganizationWorkspace {...observed(raw)} />);
    expect(screen.getByText("Verify the retained operator result")).toBeTruthy();
    const next = screen.getByRole("region", { name: "Next step" });
    expect(within(next).getByText("Inspect the failed attempt before correcting.")).toBeTruthy();
    expect(within(next).getByText("An execution error was reported.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /retry|restart/i })).toBeNull();
  });

  it("does not print a zero job count when the child observation is unavailable", () => {
    render(<OrganizationWorkspace {...observed(structuredClone(partialFixture) as typeof acceptedFixture.mission, "WS:ONE")} />);
    const metric = screen.getByText("Observed jobs").closest("div")!;
    expect(within(metric).getByText("Unknown")).toBeTruthy();
    expect(within(metric).queryByText("0")).toBeNull();
  });

  it("keeps source identities inside an explicit disclosure in job detail", () => {
    render(<OrganizationWorkspace {...observed()} />);
    const detail = screen.getByRole("region", { name: "Job JOB-002" });
    const disclosure = within(detail).getByText("Job details").closest("details")!;
    expect(disclosure.open).toBe(false);
    expect(within(disclosure).getByText("Attempt")).toBeTruthy();
    expect(within(disclosure).getByText("Job")).toBeTruthy();
  });

  it("provides the same next-step and return controls in Chinese", () => {
    render(<OrganizationWorkspace {...observed()} locale="zh-CN" />);
    expect(screen.getByRole("region", { name: "下一步" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回工作列表" })).toBeTruthy();
    expect(screen.getByText("任务详情")).toBeTruthy();
  });


  it("withholds the selected detail when that job disappears during a qualified refresh", () => {
    const view = render(<OrganizationWorkspace {...observed()} />);
    fireEvent.click(within(screen.getByRole("list", { name: "Observed jobs" }))
      .getByRole("button", { name: /JOB-005/ }));
    const next = structuredClone(acceptedFixture.mission);
    next.children.items = next.children.items.filter(row => row.job_id !== "JOB-005");
    next.children.total_count = next.children.items.length;
    next.source.owner_observation.control_room.document_digest = "c".repeat(64);
    view.rerender(<OrganizationWorkspace {...observed(next)} />);
    expect(screen.queryByRole("region", { name: /^Job JOB-/ })).toBeNull();
    expect(screen.getByText("Selected work is no longer in this view. Choose a current job or change the search.")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("searchbox"));
    expect(within(screen.getByRole("list", { name: "Observed jobs" })).getAllByRole("button")
      .every(row => row.getAttribute("aria-pressed") === "false")).toBe(true);
  });

  it("does not silently select another job when the chosen work is filtered out", () => {
    render(<OrganizationWorkspace {...observed()} />);
    fireEvent.click(within(screen.getByRole("list", { name: "Observed jobs" }))
      .getByRole("button", { name: /JOB-005/ }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "JOB-003" } });
    expect(screen.queryByRole("region", { name: "Job JOB-003" })).toBeNull();
    const row = within(screen.getByRole("list", { name: "Observed jobs" })).getByRole("button");
    expect(row.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(row);
    expect(screen.getByRole("region", { name: "Job JOB-003" })).toBeTruthy();
  });

  it.each([
    [true, "en", "Required review pending"],
    [true, "zh-CN", "待完成必要审查"],
    [false, "en", "Review not required"],
    [null, "en", "Not observed"],
  ] as const)("preserves the supplied review requirement (%s, %s)", (required, locale, label) => {
    const raw = { ...structuredClone(acceptedFixture.mission),
      review: { ...acceptedFixture.mission.review, required, verdict: "NOT_YET" } };
    render(<OrganizationWorkspace {...observed(raw)} locale={locale} />);
    const review = within(screen.getByRole("region", { name: locale === "zh-CN" ? "任务进度" : "Operation progress" }))
      .getByText(locale === "zh-CN" ? "审查" : "Review").closest("div")!;
    expect(within(review).getByText(label)).toBeTruthy();
  });

  it("still removes work and navigation immediately when the viewer authorization changes", () => {
    const props = observed();
    const inspect = vi.fn();
    const view = render(<OrganizationWorkspace {...props} onInspectWorkerResult={inspect} />);
    fireEvent.click(within(screen.getByRole("list", { name: "Observed jobs" })).getByRole("button", { name: /JOB-003/ }));
    view.rerender(<OrganizationWorkspace {...props} binding={{ ...props.binding, authGeneration: 4 }} onInspectWorkerResult={inspect} />);
    expect(screen.queryByRole("region", { name: "Agents and work" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open result" })).toBeNull();
    expect(inspect).not.toHaveBeenCalled();
  });
});
