// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TeamWorkspace } from "./TeamWorkspace";
import type { TeamRosterRead } from "./team-roster";
// Fixtures go through Director B's REAL fail-closed parser, so every rendered
// roster is contract-valid by construction (no second parser here).
import { parseTeamRoster } from "../hermes-native/team-roster-contract";
afterEach(cleanup);

const observedGateway = {
  observed: true, source: "control_socket_identify" as const, instanceId: "gw-1",
  authorityEpoch: 4, codeVersion: "0.23.0", pid: 1234, state: "ready",
};
const botJson = (over: Record<string, unknown> = {}) => ({
  id: "bot-alpha", displayName: "Alpha Bot", role: "Research lead",
  profilePath: "/Users/operator/.hermes/profiles/alpha", managed: true,
  host: "m2studio", gateway: observedGateway, readiness: "ready",
  readinessReason: "GATEWAY_IDENTIFY_READY", lastActivity: "2026-11-09T00:00:00Z",
  activitySummary: "Reading regime data", ...over,
});
const roster: TeamRosterRead = {
  kind: "AVAILABLE",
  roster: parseTeamRoster({
    schema: "mastermind.team_roster/v1", generatedAt: "2026-11-09T12:00:00Z",
    host: "m2studio",
    bots: [
      botJson(),
      botJson({ id: "bot-beta", displayName: "Beta Ops", role: "Operations" }),
    ],
  }),
};

const PAPER_SAMPLES = /Ryan|Meta-CEO|Secretary|GLM/i;

describe("TeamWorkspace — hosting the HC02/HC03/HC09 conversation surfaces", () => {
  it("carries the toolbar actions above the roster (HC02 toolbar)", () => {
    render(<TeamWorkspace roster={roster} />);
    const toolbar = screen.getByRole("toolbar", { name: "Team actions" });
    expect(toolbar.textContent).toContain("New group");
    expect(toolbar.textContent).toContain("＋ New bot");
    // The roster itself is untouched.
    expect(screen.getByRole("table", { name: "Team roster" })).toBeTruthy();
  });

  it("opens the New teammate surface from the toolbar on the real roster", () => {
    render(<TeamWorkspace roster={roster} />);
    fireEvent.click(screen.getByRole("button", { name: "＋ New bot" }));
    const dialog = screen.getByRole("dialog", { name: "New teammate" });
    expect(dialog).toBeTruthy();
    const select = screen.getByLabelText("Start from") as HTMLSelectElement;
    expect(
      Array.from(select.options).map((option) => option.textContent),
    ).toEqual(["Start fresh", "Alpha Bot", "Beta Ops"]);
  });

  it("closes the New teammate surface on Escape and returns focus to its trigger", () => {
    render(<TeamWorkspace roster={roster} />);
    const trigger = screen.getByRole("button", { name: "＋ New bot" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "New teammate" })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("opens the New group surface from the toolbar and closes on Escape", () => {
    render(<TeamWorkspace roster={roster} />);
    fireEvent.click(screen.getByRole("button", { name: "New group" }));
    expect(screen.getByRole("dialog", { name: "New group" })).toBeTruthy();
    expect(screen.getByPlaceholderText("Search 2 teammates…")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens Bot settings from the bot detail with the real selected bot", () => {
    render(<TeamWorkspace roster={roster} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Beta Ops" }));
    fireEvent.click(screen.getByRole("button", { name: "Bot settings" }));
    const dialog = screen.getByRole("dialog", { name: "Bot settings" });
    expect(dialog.textContent).toContain("Beta Ops"); // scope panel, real bot
    // No host is wired in tests: the Models tab stays honestly unavailable.
    expect(dialog.textContent).toContain("Model policy not verified");
    expect(dialog.textContent).toContain("READ_NOT_EXPOSED");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    // The bot detail itself is untouched.
    expect(screen.getByText("Beta Ops")).toBeTruthy();
  });

  it("carries no Paper sample data anywhere in the workspace output", () => {
    const { container } = render(
      <TeamWorkspace roster={roster} locale="zh-CN" />,
    );
    fireEvent.click(screen.getByRole("button", { name: "＋ 新机器人" }));
    expect(container.textContent).not.toMatch(PAPER_SAMPLES);
    expect(container.textContent).not.toMatch(/12 teammates/i);
  });
});

describe("TeamWorkspace — hosting the HC10/HC18/HC19/HC20/HC21 board modes", () => {
  it("toggles a board mode in place of the roster and back, with aria-pressed", () => {
    render(<TeamWorkspace roster={roster} />);
    const needsYou = screen.getByRole("button", { name: "Needs you" });
    expect(needsYou.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(needsYou);
    expect(needsYou.getAttribute("aria-pressed")).toBe("true");
    // HC18 replaces the roster table with the inbox, honestly null-fed.
    expect(screen.queryByRole("table", { name: "Team roster" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Needs you" })).toBeTruthy();
    expect(screen.getByText("No request projection is wired")).toBeTruthy();
    fireEvent.click(needsYou);
    expect(needsYou.getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("table", { name: "Team roster" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Needs you" })).toBeNull();
  });

  it("hosts HC10 Routines on the real roster with its honest not-projected card and back", () => {
    render(<TeamWorkspace roster={roster} />);
    fireEvent.click(screen.getByRole("button", { name: "Routines" }));
    expect(screen.getByRole("heading", { name: "Routines" })).toBeTruthy();
    expect(screen.getByText("Routines are not projected in this build")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "← Team" }));
    expect(screen.getByRole("table", { name: "Team roster" })).toBeTruthy();
  });

  it("hosts HC19 split, HC20 search and HC21 work modes with honest empty states", () => {
    render(<TeamWorkspace roster={roster} />);
    fireEvent.click(screen.getByRole("button", { name: "Split view" }));
    expect(screen.getByRole("heading", { name: "Two conversations" })).toBeTruthy();
    expect(screen.getByText("This workspace needs two conversations.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "/ Search" }));
    expect(screen.getByRole("heading", { name: "Search" })).toBeTruthy();
    expect(screen.getByText("Search source not projected in this build")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "/ Work" }));
    expect(screen.getByRole("heading", { name: "Work" })).toBeTruthy();
    expect(screen.getByText("Parent work not projected in this build")).toBeTruthy();
  });
});
