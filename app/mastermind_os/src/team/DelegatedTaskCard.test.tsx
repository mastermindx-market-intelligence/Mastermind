// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DelegatedTaskCard } from "./DelegatedTaskCard";
import { delegatedTaskValid, type DelegatedTask } from "./delegated-task";
afterEach(cleanup);

function task(extra: Partial<DelegatedTask> = {}): DelegatedTask {
  return {
    taskId: "task-1",
    title: "Repair launch refusal",
    summary: "Fix the fleet remote launch path",
    state: "queued",
    stateReason: null,
    owner: "Director C",
    route: ["Executive", "capacity_fabric"],
    authority: "preview",
    lastActivity: "2026-11-09T00:00:00Z",
    result: null,
    ...extra,
  };
}

describe("delegatedTaskValid presentation contract", () => {
  it("accepts a well-formed task and enforces honest-state rules", () => {
    expect(delegatedTaskValid(task())).toBe(true);
    expect(delegatedTaskValid(task({ state: "unknown" }))).toBe(false);
    expect(
      delegatedTaskValid(
        task({ state: "unknown", stateReason: "send returned no outcome" }),
      ),
    ).toBe(true);
    expect(delegatedTaskValid(task({ state: "declined" }))).toBe(false);
    expect(
      delegatedTaskValid(
        task({ state: "declined", stateReason: "no admission" }),
      ),
    ).toBe(true);
    expect(
      delegatedTaskValid(
        task({ result: { title: "Patch", deliveredTo: "Project X" } }),
      ),
    ).toBe(false);
    expect(
      delegatedTaskValid(
        task({
          state: "terminal",
          result: { title: "Patch", deliveredTo: "Project X" },
        }),
      ),
    ).toBe(true);
    expect(delegatedTaskValid(task({ taskId: "" }))).toBe(false);
    expect(
      delegatedTaskValid(task({ route: ["a", "b", "c", "d", "e", "f", "g"] })),
    ).toBe(false);
  });
});

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
          task={task({
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
    render(<DelegatedTaskCard task={task()} />);
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
  it("keeps dispatch disabled with the refusal reason on a declined handoff and the carrier reason while running", () => {
    const declined = task({ state: "declined", stateReason: "no admission" });
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
    render(<DelegatedTaskCard task={task({ state: "running" })} />);
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
        task={task({ state: "unknown", stateReason: "no outcome returned" })}
      />,
    );
    expect(
      screen.getByText(
        /result has not returned\. Check the original request before sending more work/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Outcome unknown")).toBeTruthy();
  });
  it("shows a terminal result as delivered, never accepted, and allows dispatch only with real authority", () => {
    const finished = task({
      state: "terminal",
      stateReason: "rc 0",
      authority: "preview",
      result: { title: "Repair patch + tests", deliveredTo: "Project Hermes" },
    });
    render(<DelegatedTaskCard task={finished} />);
    expect(screen.getByText("Result delivered")).toBeTruthy();
    expect(screen.getByText("Repair patch + tests")).toBeTruthy();
    expect(screen.getByText("Delivered to Project Hermes")).toBeTruthy();
    expect(
      screen.getByText(
        /Delivered is not acceptance\. The owner still reviews the result/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy(); // preview authority still carries no effect
    expect(screen.getByText("Finished")).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "Dispatch coding task" })
        .hasAttribute("disabled"),
    ).toBe(true);
  });
  it("enables dispatch only when a real dispatch authority exists and the state permits it", () => {
    render(<DelegatedTaskCard task={task({ authority: "dispatch" })} />);
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
    render(<DelegatedTaskCard task={task()} onOpenCode={onOpenCode} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Open coding session →" }),
    );
    expect(onOpenCode).toHaveBeenCalledTimes(1);
  });
  it("renders the honest zh-CN copy", () => {
    render(
      <DelegatedTaskCard
        task={task({ state: "unknown", stateReason: "结果未返回" })}
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
  });
});
