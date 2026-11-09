// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectDeliveryPanel, type DeliveryTrailStep } from "./ProjectDeliveryPanel";
import type { DelegatedTask } from "../team/delegated-task";
afterEach(cleanup);

const task: DelegatedTask = {
  taskId: "task-1", title: "Repair launch refusal", summary: null, state: "running",
  stateReason: null, owner: "Director C", route: ["Executive"], authority: "preview",
  lastActivity: "2026-11-09T00:00:00Z", result: null,
};
const unknownTrail: DeliveryTrailStep[] = [
  { key: "plan", step: "1", label: "Plan", state: "unknown" },
  { key: "build", step: "2", label: "Build", state: "unknown" },
  { key: "verify", step: "3", label: "Verify", state: "unknown" },
];

describe("ProjectDeliveryPanel (TD03/HC05)", () => {
  it("says the next outcome is not read rather than inventing one", () => {
    render(<ProjectDeliveryPanel objective={null} owner={null} delegatedTask={null} trail={unknownTrail} />);
    expect(screen.getByText("NEXT OUTCOME")).toBeTruthy();
    expect(screen.getByText(/has not been read from the project source/i)).toBeTruthy();
    expect(screen.getByText(/No delegated coding task is projected for this project yet/i)).toBeTruthy();
    expect(screen.getAllByText("Not projected")).toHaveLength(3);
    expect(screen.getByText(/Code results return to this project for review and release/i)).toBeTruthy();
  });

  it("shows the projected outcome, owner and a delegated task with honest states", () => {
    render(<ProjectDeliveryPanel objective="Ship the Team/Code/Fleet experience" owner="Director D" delegatedTask={task} trail={unknownTrail} />);
    expect(screen.getByText("Ship the Team/Code/Fleet experience")).toBeTruthy();
    expect(screen.getByText("Director D owns delivery")).toBeTruthy();
    expect(screen.getByText("Repair launch refusal")).toBeTruthy();
    expect(screen.getByText("In progress")).toBeTruthy();
    expect(screen.getByText("PREVIEW")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
    // Running preview work cannot be dispatched from here.
    expect(screen.getByRole("button", { name: "Dispatch coding task" }).hasAttribute("disabled")).toBe(true);
  });

  it("marks projected trail steps done while unknown ones stay not-projected", () => {
    const trail: DeliveryTrailStep[] = [
      { key: "plan", step: "1", label: "Plan accepted", state: "done" },
      { key: "build", step: "2", label: "Build", state: "active" },
      { key: "verify", step: "3", label: "Verify", state: "unknown" },
    ];
    render(<ProjectDeliveryPanel objective="O" owner={null} delegatedTask={null} trail={trail} />);
    expect(screen.getByText("Plan accepted")).toBeTruthy();
    expect(screen.getByText("Build")).toBeTruthy();
    expect(screen.getByText("Not projected")).toBeTruthy();
  });

  it("opens the code surface and the plan through the provided actions", () => {
    const onOpenCode = vi.fn(), onOpenPlan = vi.fn();
    render(<ProjectDeliveryPanel objective="O" owner={null} delegatedTask={task} trail={unknownTrail} onOpenCode={onOpenCode} onOpenPlan={onOpenPlan} />);
    fireEvent.click(screen.getByRole("button", { name: "Open coding session →" }));
    expect(onOpenCode).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Open plan →" }));
    expect(onOpenPlan).toHaveBeenCalledTimes(1);
  });

  it("renders the honest zh-CN copy", () => {
    render(<ProjectDeliveryPanel objective={null} owner={null} delegatedTask={null} trail={unknownTrail} locale="zh-CN" />);
    // The panel itself carries no view heading — the App renders it in the section summary.
    expect(screen.getByText("下一个成果")).toBeTruthy();
    expect(screen.getByText(/尚未从项目来源读取下一个成果。/)).toBeTruthy();
    expect(screen.getByText(/尚未为该项目投影受派的编码任务。/)).toBeTruthy();
    expect(screen.getAllByText("未投影")).toHaveLength(3);
  });
});
