// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ProjectDeliveryPanel, type DeliveryTrailStep } from "./ProjectDeliveryPanel";
import type { DelegatedTask } from "../team/delegated-task";
import { parseExecutionReturn } from "../hermes-native/execution-return-contract";
afterEach(cleanup);

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.resolve(here, "../../../../integrations/mmos/fixtures/execution_return_v1");
const sampleRecord: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_record.json"), "utf8"));

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
  title: "Repair launch refusal", summary: null, state: "running",
  stateReason: null, owner: "Director C", route: ["Executive"], authority: "preview",
  lastActivity: "2026-11-09T00:00:00Z",
};
const unknownTrail: DeliveryTrailStep[] = [
  { key: "plan", step: "1", label: "Plan", state: "unknown" },
  { key: "build", step: "2", label: "Build", state: "unknown" },
  { key: "verify", step: "3", label: "Verify", state: "unknown" },
];

describe("ProjectDeliveryPanel (TD03/HC05)", () => {
  it("says the next outcome is not read rather than inventing one", () => {
    render(<ProjectDeliveryPanel objective={null} owner={null} delegatedTask={null} executionReturn={null} trail={unknownTrail} />);
    expect(screen.getByText("NEXT OUTCOME")).toBeTruthy();
    expect(screen.getByText(/has not been read from the project source/i)).toBeTruthy();
    expect(screen.getByText(/No delegated coding task is projected for this project yet/i)).toBeTruthy();
    expect(screen.getAllByText("Not projected")).toHaveLength(3);
    expect(screen.getByText(/Code results return to this project for review and release/i)).toBeTruthy();
  });

  it("shows the projected outcome, owner and a delegated task with honest states", () => {
    render(<ProjectDeliveryPanel objective="Ship the Team/Code/Fleet experience" owner="Director D" delegatedTask={task} executionReturn={null} trail={unknownTrail} />);
    expect(screen.getByText("Ship the Team/Code/Fleet experience")).toBeTruthy();
    expect(screen.getByText("Director D owns delivery")).toBeTruthy();
    expect(screen.getByText("Repair launch refusal")).toBeTruthy();
    expect(screen.getByText("In progress")).toBeTruthy();
    expect(screen.getByText("PREVIEW")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
    // Running preview work cannot be dispatched from here.
    expect(screen.getByRole("button", { name: "Dispatch coding task" }).hasAttribute("disabled")).toBe(true);
  });

  it("mounts the HC08 return card fed by execution_return/v1 (null today = honest empty)", () => {
    render(<ProjectDeliveryPanel objective={null} owner={null} delegatedTask={null} executionReturn={null} trail={unknownTrail} />);
    expect(screen.getByText("Result return")).toBeTruthy();
    expect(screen.getByText("No execution return is projected yet.")).toBeTruthy();
    expect(screen.queryByText(/Delivered to /i)).toBeNull(); // nothing invented
  });

  it("renders a parsed execution_return/v1 record through the same mount", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    render(<ProjectDeliveryPanel objective="O" owner={null} delegatedTask={null} executionReturn={record} trail={unknownTrail} />);
    expect(
      document.querySelector(".mm-chip-state[data-stage='installed_unknown']"),
    ).not.toBeNull();
    expect(screen.getByText(/Delivered ≠ accepted/i)).toBeTruthy();
    expect(screen.getByText("Not accepted")).toBeTruthy();
  });

  it("marks projected trail steps done while unknown ones stay not-projected", () => {
    const trail: DeliveryTrailStep[] = [
      { key: "plan", step: "1", label: "Plan accepted", state: "done" },
      { key: "build", step: "2", label: "Build", state: "active" },
      { key: "verify", step: "3", label: "Verify", state: "unknown" },
    ];
    render(<ProjectDeliveryPanel objective="O" owner={null} delegatedTask={null} executionReturn={null} trail={trail} />);
    expect(screen.getByText("Plan accepted")).toBeTruthy();
    expect(screen.getByText("Build")).toBeTruthy();
    expect(screen.getByText("Not projected")).toBeTruthy();
  });

  it("opens the code surface and the plan through the provided actions", () => {
    const onOpenCode = vi.fn(), onOpenPlan = vi.fn();
    render(<ProjectDeliveryPanel objective="O" owner={null} delegatedTask={task} executionReturn={null} trail={unknownTrail} onOpenCode={onOpenCode} onOpenPlan={onOpenPlan} />);
    fireEvent.click(screen.getByRole("button", { name: "Open coding session →" }));
    expect(onOpenCode).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Open plan →" }));
    expect(onOpenPlan).toHaveBeenCalledTimes(1);
  });

  it("renders the honest zh-CN copy", () => {
    render(<ProjectDeliveryPanel objective={null} owner={null} delegatedTask={null} executionReturn={null} trail={unknownTrail} locale="zh-CN" />);
    // The panel itself carries no view heading — the App renders it in the section summary.
    expect(screen.getByText("下一个成果")).toBeTruthy();
    expect(screen.getByText(/尚未从项目来源读取下一个成果。/)).toBeTruthy();
    expect(screen.getByText(/尚未为该项目投影受派的编码任务。/)).toBeTruthy();
    expect(screen.getAllByText("未投影")).toHaveLength(3);
    expect(screen.getByText("结果返回")).toBeTruthy();
    expect(screen.getByText("尚无执行返回被投影。")).toBeTruthy();
  });
});
