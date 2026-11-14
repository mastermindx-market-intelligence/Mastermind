// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DelegatedTaskCard } from "./DelegatedTaskCard";
import { parseDelegatedTask, type DelegatedTask } from "./delegated-task";
afterEach(cleanup);

const task: DelegatedTask = {
  binding: {
    schema: "ExecutionBinding.v1.1",
    root_run_ref: "root-wo19-coding-7",
    immediate_parent_run_ref: "run-41",
    logical_child_key: "fleet-launch-repair",
    request_digest: "a".repeat(64),
    effective_complexity: "C2_COMPLEX_BOUNDED",
    task_kind: "code",
    runtime_kind: "fabric-native",
    operation_key: "op-77",
    caller_namespace: "mastermind:fabric",
    lease_ref: "lease-9",
  },
  title: "Repair launch refusal",
  summary: "Fix the fleet remote launch path",
  state: "queued",
  stateReason: null,
  owner: "Director C",
  route: ["Executive", "capacity_fabric"],
  authority: "preview",
  lastActivity: "2026-11-09T00:00:00Z",
};

function variant(extra: Partial<DelegatedTask>): DelegatedTask {
  return { ...task, ...extra };
}

describe("DelegatedTaskCard", () => {
  it("renders all five states with distinct honest labels", () => {
    const states: [DelegatedTask["state"], string][] = [
      ["queued", "Queued"],
      ["running", "In progress"],
      ["unknown", "Outcome unknown"],
      ["declined", "Declined"],
      ["terminal", "Finished"],
    ];
    for (const [state, label] of states) {
      const { unmount } = render(
        <DelegatedTaskCard
          task={variant({
            state,
            stateReason:
              state === "unknown" || state === "declined" ? "a reason" : null,
          })}
        />,
      );
      const chip = document.querySelector(
        `.mm-chip-state[data-state="${state}"]`,
      );
      expect(chip?.textContent).toBe(label);
      unmount();
    }
  });
  it("shows PREVIEW and EFFECT·NONE chips and a disabled dispatch with its reason while preview-only", () => {
    render(<DelegatedTaskCard task={task} />);
    expect(screen.getByText("PREVIEW")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
    const dispatch = screen.getByRole("button", {
      name: "Dispatch coding task",
    });
    expect(dispatch.hasAttribute("disabled")).toBe(true);
    expect(dispatch.getAttribute("aria-describedby")).toBe(
      "mm-task-dispatch-reason",
    );
    expect(
      screen.getByText(
        /Dispatch needs an admitted coding handoff on the Executive path/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Queued")).toBeTruthy();
    expect(
      screen.getByText(/admitted and waiting for its runtime slot/i),
    ).toBeTruthy();
    expect(screen.getByText("Last activity 2026-11-09T00:00:00Z")).toBeTruthy();
    expect(screen.getByText("Director C")).toBeTruthy();
    expect(screen.getByText("Executive")).toBeTruthy();
    expect(screen.getByText("capacity_fabric")).toBeTruthy();
  });
  it("surfaces the real admission-binding identity (contract field names)", () => {
    render(<DelegatedTaskCard task={task} />);
    expect(screen.getByText("Admission binding")).toBeTruthy();
    const facts = document.querySelector(".mm-task-binding")!.textContent!;
    expect(facts).toContain("ExecutionBinding.v1.1");
    expect(facts).toContain("root-wo19-coding-7");
    expect(facts).toContain("run-41");
    expect(facts).toContain("fleet-launch-repair");
    expect(facts).toContain("a".repeat(64));
    expect(facts).toContain("C2_COMPLEX_BOUNDED");
    expect(facts).toContain("op-77");
    expect(facts).toContain("mastermind:fabric");
    expect(facts).toContain("lease-9");
    // The runtime kind rides the header as an honest chip.
    expect(document.querySelector(".mm-task-head")?.textContent).toContain("fabric-native");
  });
  it("marks unset v1.1 binding fields as not set, never invented", () => {
    render(
      <DelegatedTaskCard
        task={variant({
          binding: {
            ...task.binding, schema: "ExecutionBinding.v1",
            runtime_kind: "", operation_key: "", caller_namespace: "",
            lease_ref: "",
          },
        })}
      />,
    );
    const facts = document.querySelector(".mm-task-binding")!.textContent!;
    expect(facts).toContain("ExecutionBinding.v1");
    expect(screen.getAllByText("Not set").length).toBe(4);
    expect(document.querySelector(".mm-task-head")?.textContent).not.toContain("fabric-native");
  });
  it("keeps dispatch disabled with the refusal reason on a declined handoff and the carrier reason while running", () => {
    const declined = variant({ state: "declined", stateReason: "no admission" });
    const { unmount } = render(<DelegatedTaskCard task={declined} />);
    expect(
      screen
        .getByRole("button", { name: "Dispatch coding task" })
        .hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen.getByText(/declined\. Start a new handoff; do not replay/i),
    ).toBeTruthy();
    unmount();
    render(<DelegatedTaskCard task={variant({ state: "running" })} />);
    expect(
      screen
        .getByRole("button", { name: "Dispatch coding task" })
        .hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen.getByText(/already running on its original carrier/i),
    ).toBeTruthy();
  });
  it("explains an unknown outcome without inviting a replay", () => {
    render(
      <DelegatedTaskCard
        task={variant({ state: "unknown", stateReason: "no outcome returned" })}
      />,
    );
    expect(
      screen.getByText(
        /result has not returned\. Check the original request before sending more work/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Outcome unknown")).toBeTruthy();
  });
  it("renders a terminal task without a return block — returns belong to the execution_return card (HC08)", () => {
    render(
      <DelegatedTaskCard
        task={variant({ state: "terminal", stateReason: "rc 0" })}
      />,
    );
    expect(screen.getByText("Finished")).toBeTruthy();
    expect(screen.getByText("rc 0")).toBeTruthy();
    expect(screen.queryByText(/Delivered to /i)).toBeNull();
    expect(screen.queryByText(/Delivered is not acceptance/i)).toBeNull();
  });
  it("enables dispatch only when a real dispatch authority exists and the state permits it", () => {
    render(<DelegatedTaskCard task={variant({ authority: "dispatch" })} />);
    const dispatch = screen.getByRole("button", {
      name: "Dispatch coding task",
    });
    expect(dispatch.hasAttribute("disabled")).toBe(false);
    expect(screen.queryByText("PREVIEW")).toBeNull();
    expect(
      screen.queryByText(/Dispatch needs an admitted coding handoff/i),
    ).toBeNull();
  });
  it("opens the coding session through the provided action", () => {
    const onOpenCode = vi.fn();
    render(<DelegatedTaskCard task={task} onOpenCode={onOpenCode} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Open coding session →" }),
    );
    expect(onOpenCode).toHaveBeenCalledTimes(1);
  });
  it("renders the honest zh-CN copy including the binding block", () => {
    render(
      <DelegatedTaskCard
        task={variant({ state: "unknown", stateReason: "结果未返回" })}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("结果未知")).toBeTruthy();
    expect(screen.getByText("预览")).toBeTruthy();
    expect(screen.getByText("无效果")).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "派发编码任务" })
        .hasAttribute("disabled"),
    ).toBe(true);
    expect(screen.getByText(/此界面仅可预览/i)).toBeTruthy();
    expect(screen.getByText(/结果尚未返回/i)).toBeTruthy();
    expect(screen.getByText("受理绑定")).toBeTruthy();
    expect(screen.getByText("逻辑子键")).toBeTruthy();
    expect(screen.getByText("租约")).toBeTruthy(); // v1.1 lease_ref stays visible
  });
  it("only ever receives tasks that passed the fail-closed parser contract", () => {
    // The projection type and the parser share one law: a card can never be
    // fed a record the admission contract would refuse.
    expect(() =>
      parseDelegatedTask({ ...task, binding: { ...task.binding, logical_child_key: "" } }),
    ).toThrow(/DELEGATED_TASK_INVALID/);
    expect(parseDelegatedTask(task).binding.schema).toBe("ExecutionBinding.v1.1");
  });
});
