// @vitest-environment jsdom
import React from "react";
import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RoutinesPanel,
  type RoutineRecord,
} from "./RoutinesPanel";
import type { TeamBot, TeamRoster } from "./team-roster";

afterEach(cleanup);

/** Read the stylesheet from disk — the vitest CSS pipeline in this app only
 *  processes styles.css?raw, so a ?raw import of routines.css is empty.
 *  Vitest runs with cwd at the app root. */
const routinesCss = readFileSync("src/team/routines.css", "utf8");

/** Fixtures only — none of the Paper sample values ("Engineering check-in",
 *  "20:30", "America / Vancouver"…) ship in the component or its copy. */
function makeBot(id: string, displayName: string): TeamBot {
  return {
    id,
    displayName,
    role: "Teammate",
    managed: true,
    host: "m2studio",
    gateway: {
      observed: true,
      source: "control_socket_identify",
      instanceId: "gw-1",
      authorityEpoch: 3,
      codeVersion: "1.0.0",
      pid: 4242,
      state: "OPENED",
    },
    readiness: "ready",
    readinessReason: "GATEWAY_IDENTIFY_READY",
    lastActivity: "2026-11-09T00:00:00Z",
    activitySummary: "Answering",
  };
}

const roster: TeamRoster = {
  schema: "mastermind.team_roster/v1",
  generatedAt: "2026-11-09T00:00:00Z",
  host: "m2studio",
  bots: [makeBot("scrum", "Daily Scrum Bot"), makeBot("quiet", "Quiet Analyst")],
};

const routine: RoutineRecord = {
  name: "Morning portfolio sweep",
  status: "scheduled",
  instruction: "Summarize overnight moves for the sleeve owners.",
  repeatRule: "Weekdays at launch",
  timezone: "Asia/Shanghai",
  deliveryTargetId: "scrum",
  latestRun: {
    finishedAt: "2026-11-08T01:00:00Z",
    executionState: "finished",
    deliveryState: "delivered",
  },
  recentRuns: [
    {
      finishedAt: "2026-11-08T01:00:00Z",
      executionState: "finished",
      deliveryState: "delivered",
    },
    {
      finishedAt: "2026-11-07T01:00:00Z",
      executionState: "failed",
      deliveryState: "pending",
    },
  ],
};

const SAMPLES = [
  "Engineering check-in",
  "Ubuntu 2",
  "DeepSeek Harness",
  "20:30",
  "America / Vancouver",
];

describe("RoutinesPanel (HC10)", () => {
  it("renders the routine editor from a real record", () => {
    render(
      <RoutinesPanel roster={roster} routine={routine} onBack={() => {}} />,
    );
    expect(screen.getByText("Routines")).toBeTruthy();
    expect(screen.getByRole("button", { name: "← Team" })).toBeTruthy();
    expect(screen.getByText("Morning portfolio sweep")).toBeTruthy();
    expect(screen.getByText("Scheduled")).toBeTruthy();
    const textarea = screen.getByLabelText(
      "What should happen?",
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe("Summarize overnight moves for the sleeve owners.");
    expect(screen.getByText("Weekdays at launch")).toBeTruthy();
    expect(screen.getByText("Asia/Shanghai")).toBeTruthy();
    expect(
      screen.getByText("The run and its delivery are tracked separately."),
    ).toBeTruthy();
    // Run behavior rows.
    expect(screen.getByText("If a run is still active")).toBeTruthy();
    expect(screen.getByText("Gateway policy")).toBeTruthy();
    // The execution target resolves from the roster (also an option label).
    expect(screen.getAllByText("Daily Scrum Bot").length).toBe(2);
    // Right rail.
    expect(screen.getByText("SCHEDULE & HISTORY")).toBeTruthy();
    expect(screen.getByText("2026-11-08T01:00:00Z — Finished · Delivered")).toBeTruthy();
    expect(screen.getByText("2026-11-07T01:00:00Z — Failed · Pending")).toBeTruthy();
  });

  it("renders the explicit not-projected state when the record is null", () => {
    render(<RoutinesPanel roster={roster} routine={null} />);
    expect(
      screen.getByText("Routines are not projected in this build"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /no schedule, run or delivery state is shown or inferred/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Routines")).toBeTruthy();
    // No editor fabrications leak into the unavailable state.
    expect(screen.queryByText("Scheduled")).toBeNull();
    expect(screen.queryByLabelText("What should happen?")).toBeNull();
  });

  it("renders unknown-with-reason rows for null subfields, never finished/delivered fabrications", () => {
    render(
      <RoutinesPanel
        roster={roster}
        routine={{ ...routine, latestRun: null, recentRuns: null }}
      />,
    );
    expect(
      screen.getByText("No run is projected for this routine yet."),
    ).toBeTruthy();
    expect(
      screen.getByText("Run history is not projected in this build."),
    ).toBeTruthy();
    expect(
      screen.getByText(/no scheduler projection is wired, so no time or zone/i),
    ).toBeTruthy();
    // Unknown stays unknown — no observed-state labels are invented.
    expect(screen.queryByText("Finished")).toBeNull();
    expect(screen.queryByText("Delivered")).toBeNull();
    expect(screen.queryByText("Pending")).toBeNull();
  });

  it("feeds the delivery select from the real roster and follows the draft target", () => {
    render(<RoutinesPanel roster={roster} routine={routine} />);
    const select = screen.getByLabelText("Deliver the result to");
    const options = Array.from(select.querySelectorAll("option"));
    expect(options.map((option) => option.textContent)).toEqual([
      "No delivery target set",
      "Daily Scrum Bot",
      "Quiet Analyst",
    ]);
    expect((select as HTMLSelectElement).value).toBe("scrum");
    // Changing the draft target moves the Execution row; nothing is saved.
    fireEvent.change(select, { target: { value: "quiet" } });
    expect(screen.getAllByText("Quiet Analyst").length).toBe(2);
  });

  it("keeps the Execution row honest when no roster target resolves", () => {
    render(
      <RoutinesPanel
        roster={roster}
        routine={{ ...routine, deliveryTargetId: null }}
      />,
    );
    expect(
      screen.getByText(/no delivery target is selected on this roster/i),
    ).toBeTruthy();
  });

  it("pause and resume call through, and render disabled with a reason when unwired", () => {
    const onPause = vi.fn();
    const onResume = vi.fn();
    const { unmount } = render(
      <RoutinesPanel
        roster={roster}
        routine={routine}
        onPause={onPause}
        onResume={onResume}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Pause routine" }));
    expect(onPause).toHaveBeenCalledTimes(1);
    unmount();
    render(
      <RoutinesPanel
        roster={roster}
        routine={{ ...routine, status: "paused" }}
        onResume={onResume}
      />,
    );
    expect(screen.getByText("Paused")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Resume routine" }));
    expect(onResume).toHaveBeenCalledTimes(1);
    unmount();
    render(<RoutinesPanel roster={roster} routine={routine} />);
    const action = screen.getByRole("button", { name: "Pause routine" });
    expect(action.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/this action stays disabled/i),
    ).toBeTruthy();
  });

  it("opens the latest run result through the provided action, disabled with a reason otherwise", () => {
    const onOpenResult = vi.fn();
    const { unmount } = render(
      <RoutinesPanel
        roster={roster}
        routine={routine}
        onOpenResult={onOpenResult}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open result in room →" }));
    expect(onOpenResult).toHaveBeenCalledTimes(1);
    unmount();
    render(<RoutinesPanel roster={roster} routine={routine} />);
    const open = screen.getByRole("button", { name: "Open result in room →" });
    expect(open.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/no room result path is wired in this build/i),
    ).toBeTruthy();
  });

  it("returns via Escape and the back link", () => {
    const onBack = vi.fn();
    render(<RoutinesPanel roster={roster} routine={routine} onBack={onBack} />);
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(onBack).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "← Team" }));
    expect(onBack).toHaveBeenCalledTimes(2);
  });

  it("keeps focus reachable and visible on interactive controls", () => {
    render(<RoutinesPanel roster={roster} routine={routine} />);
    const textarea = screen.getByLabelText("What should happen?");
    textarea.focus();
    expect(document.activeElement).toBe(textarea);
    const select = screen.getByLabelText("Deliver the result to");
    select.focus();
    expect(document.activeElement).toBe(select);
    // The stylesheet keeps a visible focus ring on every interactive control.
    expect(routinesCss).toContain(".mm-routines :is(button, select, textarea):focus-visible");
    expect(routinesCss).toContain("outline: 2px solid var(--noir-champagne)");
  });

  it("renders the zh-CN copy for record and unavailable states", () => {
    const { unmount } = render(
      <RoutinesPanel roster={roster} routine={routine} locale="zh-CN" />,
    );
    expect(screen.getByText("例行任务")).toBeTruthy();
    expect(screen.getByText("已排程")).toBeTruthy();
    expect(screen.getByText("应该发生什么？")).toBeTruthy();
    expect(screen.getByText("运行与其送达是分开跟踪的。")).toBeTruthy();
    expect(screen.getByText("暂停例行任务")).toBeTruthy();
    expect(screen.getByText("2026-11-08T01:00:00Z — 已完成 · 已送达")).toBeTruthy();
    unmount();
    render(<RoutinesPanel roster={roster} routine={null} locale="zh-CN" />);
    expect(screen.getByText("此版本尚未投影例行任务")).toBeTruthy();
    expect(screen.getByText(/不显示也不推断任何排程、运行或送达状态/)).toBeTruthy();
  });

  it("ships no Paper sample data in any rendered state", () => {
    const record = render(<RoutinesPanel roster={roster} routine={routine} />);
    for (const sample of SAMPLES) {
      expect(record.container.textContent).not.toContain(sample);
    }
    record.unmount();
    const empty = render(<RoutinesPanel roster={roster} routine={null} />);
    for (const sample of SAMPLES) {
      expect(empty.container.textContent).not.toContain(sample);
    }
    // The rendered values come from the record/roster, not from copy.
    expect(empty.container.textContent).not.toContain("Morning portfolio sweep");
  });

  it("renders an empty recent-runs list honestly and follows the record for rows", () => {
    const { unmount } = render(
      <RoutinesPanel roster={roster} routine={{ ...routine, recentRuns: [] }} />,
    );
    expect(screen.getByText("No runs recorded yet.")).toBeTruthy();
    unmount();
    render(<RoutinesPanel roster={roster} routine={routine} />);
    expect(screen.queryByText("No runs recorded yet.")).toBeNull();
    expect(screen.getAllByText(/— Finished · Delivered/).length).toBe(1);
  });
});
