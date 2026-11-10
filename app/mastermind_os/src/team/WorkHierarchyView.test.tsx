// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  WorkHierarchyView,
  type DelegatedWorkRow,
  type ParentWorkRow,
  type ScopedTaskDetail,
} from "./WorkHierarchyView";

afterEach(cleanup);

/** Fixtures are PROP DATA ONLY — every name below arrives through the real
 *  arrays; nothing is rendered from nowhere. */
const parentWork: ParentWorkRow[] = [
  { id: "w1", title: "Teamlink adapter", meta: "Mastermind OS · wave 4" },
  { id: "w2", title: "Fleet route hardening", meta: null },
];

const delegated: DelegatedWorkRow[] = [
  { id: "t1", title: "Repair launch refusal", state: "queued", owner: "Director C" },
  { id: "t2", title: "Verify route preview", state: "running", owner: "Engineering" },
  { id: "t3", title: "Archive old attempts", state: "terminal", owner: null },
];

const selectedTask: ScopedTaskDetail = {
  id: "t1",
  title: "Repair launch refusal",
  owner: "Director C",
  facts: [
    { label: "Complexity", value: "C2_COMPLEX_BOUNDED" },
    { label: "Runtime", value: "fabric-native" },
  ],
  timeline: [
    { step: "Handoff admitted", state: "done", at: "2026-11-08T09:00:00Z" },
    { step: "Runtime slot", state: "pending", at: null },
    { step: "Result returned", state: "unknown", at: null },
  ],
};

function taskButtons(): HTMLElement[] {
  return Array.from(document.querySelectorAll(".mm-work-task-row"));
}

describe("WorkHierarchyView", () => {
  it("renders parent work rows and the delegated section with the count from the real array", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={null}
        onOpenTask={() => {}}
      />,
    );
    expect(screen.getByText("Teamlink adapter")).toBeTruthy();
    expect(screen.getByText("Mastermind OS · wave 4")).toBeTruthy();
    expect(screen.getByText("Fleet route hardening")).toBeTruthy();
    // Delegated count from the REAL array.
    expect(screen.getByTestId("mm-work-count").textContent).toBe("3 tasks");
    expect(taskButtons()).toHaveLength(3);
    // State chips reuse the delegated-task vocabulary.
    expect(screen.getByText("Queued")).toBeTruthy();
    expect(screen.getByText("In progress")).toBeTruthy();
    expect(screen.getByText("Finished")).toBeTruthy();
    expect(screen.getByText("Director C")).toBeTruthy();
  });

  it("opens a task dialogue through onOpenTask with the exact id", () => {
    const onOpenTask = vi.fn();
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={null}
        onOpenTask={onOpenTask}
      />,
    );
    fireEvent.click(screen.getByText("Verify route preview"));
    expect(onOpenTask).toHaveBeenCalledTimes(1);
    expect(onOpenTask).toHaveBeenCalledWith("t2");
  });

  it("disables task rows with a visible reason when no open path exists", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={null}
      />,
    );
    for (const button of taskButtons()) {
      expect(button.hasAttribute("disabled")).toBe(true);
    }
    expect(
      screen.getByText(/Opening a task dialogue is not wired in this build/i),
    ).toBeTruthy();
  });

  it("moves focus through task rows with arrow keys (roving focus)", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={null}
        onOpenTask={() => {}}
      />,
    );
    const [first, second, third] = taskButtons();
    first!.focus();
    fireEvent.keyDown(first!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(second!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(third);
    fireEvent.keyDown(third!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(third);
    fireEvent.keyDown(third!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(second!, { key: "End" });
    expect(document.activeElement).toBe(third);
    expect(first!.tabIndex).toBe(0);
    expect(second!.tabIndex).toBe(-1);
  });

  it("renders independent honest not-projected states per section (parent / delegated)", () => {
    // Parent read missing, delegated read real.
    let mounted = render(
      <WorkHierarchyView
        locale="en"
        parentWork={null}
        delegated={delegated}
        selectedTask={null}
        onOpenTask={() => {}}
      />,
    );
    expect(screen.getByText("Parent work not projected in this build")).toBeTruthy();
    expect(screen.getByText(/No parent-work read exists/i)).toBeTruthy();
    // The delegated read still renders its real rows.
    expect(screen.getByText("Repair launch refusal")).toBeTruthy();
    expect(screen.getByTestId("mm-work-count").textContent).toBe("3 tasks");
    mounted.unmount();
    // Delegated read missing, parent read real — no count without a real array.
    mounted = render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={null}
        selectedTask={null}
      />,
    );
    expect(
      screen.getByText("Delegated work not projected in this build"),
    ).toBeTruthy();
    expect(screen.getByText("Teamlink adapter")).toBeTruthy();
    expect(screen.queryByTestId("mm-work-count")).toBeNull();
    expect(taskButtons()).toHaveLength(0);
    mounted.unmount();
    // Both missing: two independent honest cards, zero rows.
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={null}
        delegated={null}
        selectedTask={null}
      />,
    );
    expect(screen.getByText("Parent work not projected in this build")).toBeTruthy();
    expect(
      screen.getByText("Delegated work not projected in this build"),
    ).toBeTruthy();
  });

  it("renders honest zero states for real empty reads", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={[]}
        delegated={[]}
        selectedTask={null}
      />,
    );
    expect(screen.getByText(/No parent work is projected in this read/i)).toBeTruthy();
    expect(screen.getByText(/No delegated tasks are projected/i)).toBeTruthy();
    expect(screen.getByTestId("mm-work-count").textContent).toBe("0 tasks");
  });

  it("shows the selected task dialogue: header, owner, facts and timeline with state marks", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={selectedTask}
      />,
    );
    expect(
      document.querySelector(".mm-work-dialogue-head h3")?.textContent,
    ).toBe("Repair launch refusal");
    expect(screen.getByText("Owner Director C")).toBeTruthy();
    // Facts row from the real array.
    expect(screen.getByText("Complexity")).toBeTruthy();
    expect(screen.getByText("C2_COMPLEX_BOUNDED")).toBeTruthy();
    expect(screen.getByText("Runtime")).toBeTruthy();
    expect(screen.getByText("fabric-native")).toBeTruthy();
    // Timeline: done/pending/unknown marks; a null at is honestly unobserved.
    const steps = Array.from(document.querySelectorAll(".mm-work-step"));
    expect(steps.map((node) => node.getAttribute("data-state"))).toEqual([
      "done",
      "pending",
      "unknown",
    ]);
    expect(screen.getByText("Handoff admitted")).toBeTruthy();
    expect(screen.getAllByText("Not observed")).toHaveLength(2);
    // The selected row is marked in the hierarchy.
    const marked = document.querySelector(
      '.mm-work-task-row[data-selected="true"]',
    );
    expect(marked?.getAttribute("data-state")).toBe("queued");
  });

  it("says when the timeline is not projected or facts are empty — never invents steps", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={{
          ...selectedTask,
          facts: [],
          timeline: null,
        }}
      />,
    );
    expect(screen.getByText(/No task facts are projected/i)).toBeTruthy();
    expect(screen.getByText(/The timeline is not projected/i)).toBeTruthy();
    expect(document.querySelectorAll(".mm-work-step")).toHaveLength(0);
  });

  it("renders an honest empty-timeline state for a real empty timeline array", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={{ ...selectedTask, timeline: [] }}
      />,
    );
    expect(screen.getByText(/No timeline steps are recorded/i)).toBeTruthy();
  });

  it("disables the composer with a visible reason when no send path exists", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={selectedTask}
      />,
    );
    const textarea = screen.getByLabelText("Message this task");
    expect(textarea.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByRole("button", { name: "Send to task" }).hasAttribute(
        "disabled",
      ),
    ).toBe(true);
    expect(
      screen.getByText(/No send path exists in this build/i),
    ).toBeTruthy();
  });

  it("sends through onCompose with the draft text, then clears it", () => {
    const onCompose = vi.fn();
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={selectedTask}
        onCompose={onCompose}
      />,
    );
    const textarea = screen.getByLabelText("Message this task");
    expect(textarea.hasAttribute("disabled")).toBe(false);
    const send = screen.getByRole("button", { name: "Send to task" });
    // Empty draft never sends.
    expect(send.hasAttribute("disabled")).toBe(true);
    fireEvent.change(textarea, { target: { value: "  Start from the failing check  " } });
    expect(send.hasAttribute("disabled")).toBe(false);
    fireEvent.click(send);
    expect(onCompose).toHaveBeenCalledTimes(1);
    expect(onCompose).toHaveBeenCalledWith("Start from the failing check");
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("shows an honest placeholder when no task dialogue is selected", () => {
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={null}
        onOpenTask={() => {}}
      />,
    );
    expect(
      screen.getByText(/Select a delegated task to open its dialogue/i),
    ).toBeTruthy();
  });

  it("clears the selection on Escape when a handler exists; without one it is a no-op", () => {
    const onCloseSelection = vi.fn();
    const { unmount } = render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={selectedTask}
        onCloseSelection={onCloseSelection}
      />,
    );
    fireEvent.keyDown(document.querySelector(".mm-work-surface")!, {
      key: "Escape",
    });
    expect(onCloseSelection).toHaveBeenCalledTimes(1);
    unmount();
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={selectedTask}
      />,
    );
    fireEvent.keyDown(document.querySelector(".mm-work-surface")!, {
      key: "Escape",
    });
    expect(
      document.querySelector(".mm-work-dialogue-head h3")?.textContent,
    ).toBe("Repair launch refusal");
  });

  it("regression: never renders Paper sample data — no hardcoded counts, no sample people", () => {
    const { unmount } = render(
      <WorkHierarchyView
        locale="en"
        parentWork={null}
        delegated={null}
        selectedTask={null}
      />,
    );
    const text = document.body.textContent ?? "";
    expect(text).not.toContain("3 results");
    expect(text).not.toContain("Ryan");
    expect(text).not.toContain("Meta-CEO");
    expect(text).not.toContain("Secretary");
    expect(text).not.toContain("12 teammates");
    unmount();
    // Real empty reads carry only the real zero count.
    render(
      <WorkHierarchyView
        locale="en"
        parentWork={[]}
        delegated={[]}
        selectedTask={null}
      />,
    );
    expect(screen.getByTestId("mm-work-count").textContent).toBe("0 tasks");
  });

  it("renders the honest zh-CN copy", () => {
    const { unmount } = render(
      <WorkHierarchyView
        locale="zh-CN"
        parentWork={parentWork}
        delegated={delegated}
        selectedTask={selectedTask}
      />,
    );
    expect(screen.getByText("工作")).toBeTruthy();
    expect(screen.getByTestId("mm-work-count").textContent).toBe("3 个任务");
    expect(screen.getByText("排队中")).toBeTruthy();
    expect(screen.getByText("负责人 Director C")).toBeTruthy();
    // "已完成" appears on the terminal state chip AND the done timeline step.
    expect(screen.getAllByText("已完成")).toHaveLength(2);
    expect(
      screen.getByText(/此构建不存在发送路径——输入框已停用/),
    ).toBeTruthy();
    unmount();
    render(
      <WorkHierarchyView
        locale="zh-CN"
        parentWork={null}
        delegated={null}
        selectedTask={null}
      />,
    );
    expect(screen.getByText("此构建未投影父级工作")).toBeTruthy();
    expect(screen.getByText("此构建未投影受派工作")).toBeTruthy();
    expect(screen.getByText(/从层级中选择一个受派任务/)).toBeTruthy();
  });
});
