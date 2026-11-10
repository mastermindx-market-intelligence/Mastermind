// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewBotPanel } from "./NewBotPanel";
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
const available = (bots: unknown[]): TeamRosterRead => ({
  kind: "AVAILABLE",
  roster: parseTeamRoster({
    schema: "mastermind.team_roster/v1", generatedAt: "2026-11-09T12:00:00Z",
    host: "m2studio", bots,
  }),
});
const roster = available([
  botJson(),
  botJson({ id: "bot-beta", displayName: "Beta Ops", role: "Operations" }),
  botJson({ id: "bot-gamma", displayName: "Gamma Review", role: "Review",
    host: "unknown", gateway: { observed: false, source: "none", instanceId: null,
      authorityEpoch: null, codeVersion: null, pid: null, state: null },
    readiness: "unknown", readinessReason: "NO_GATEWAY_LOCK", lastActivity: null,
    activitySummary: null, activityReason: "NO_SESSIONS" }),
]);

const PAPER_SAMPLES = /Ryan|Meta-CEO|Secretary|Engineering|GLM/i;

describe("NewBotPanel (HC02) — role and launch on the real roster", () => {
  it("renders the board structure: fields, access card, launch card, preview steps", () => {
    render(<NewBotPanel roster={roster} onClose={() => {}} />);
    expect(screen.getByText("Give your bot a role and a place on the team.")).toBeTruthy();
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect(screen.getByLabelText("What should this bot do?")).toBeTruthy();
    expect(screen.getByText("You can change this later.")).toBeTruthy();
    expect(screen.getByText("Access & capabilities")).toBeTruthy();
    expect(screen.getByText("Fresh personal memory. Credentials stay with the connection.")).toBeTruthy();
    expect(screen.getByText("Team default")).toBeTruthy();
    expect(screen.getByText("Model and placement follow your team's policy.")).toBeTruthy();
    expect(screen.getByText("PREVIEW")).toBeTruthy();
    expect(screen.getByText("Not created yet")).toBeTruthy();
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.getByText("Create a profile")).toBeTruthy();
    expect(screen.getByText("Start the bot")).toBeTruthy();
    expect(screen.getByText("Open its conversation")).toBeTruthy();
    expect(screen.getByText("You'll see Ready when the bot can respond.")).toBeTruthy();
  });

  it("builds Start-from options from the REAL roster read, never sample names", () => {
    render(<NewBotPanel roster={roster} onClose={() => {}} />);
    const select = screen.getByLabelText("Start from") as HTMLSelectElement;
    const options = Array.from(select.options).map((option) => option.textContent);
    expect(options).toContain("Start fresh");
    expect(options).toContain("Alpha Bot");
    expect(options).toContain("Beta Ops");
    expect(options).toContain("Gamma Review");
    expect(options.length).toBe(4);
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });

  it("shows the honest roster-unavailable state with the read's reason code", () => {
    render(
      <NewBotPanel
        roster={{ kind: "UNAVAILABLE", reason: "NATIVE_PLATFORM_UNAVAILABLE" }}
        onClose={() => {}}
      />,
    );
    const select = screen.getByLabelText("Start from") as HTMLSelectElement;
    expect(select.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText("Roster not verified on this connection"),
    ).toBeTruthy();
    expect(screen.getByText("NATIVE_PLATFORM_UNAVAILABLE")).toBeTruthy();
    // No teammate is invented while the roster is unverified.
    expect(select.options.length).toBe(1);
  });

  it("previews the typed name and role live; no name yet stays honest", () => {
    render(<NewBotPanel roster={roster} onClose={() => {}} />);
    expect(screen.getByText("Unnamed teammate")).toBeTruthy();
    expect(screen.getByText("No role described yet")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Delta Scout" } });
    expect(
      document.querySelector(".mm-preview-name")?.textContent,
    ).toBe("Delta Scout");
    fireEvent.change(screen.getByLabelText("What should this bot do?"), {
      target: { value: "Watch the launch checklist" },
    });
    expect(
      document.querySelector(".mm-preview-role")?.textContent,
    ).toBe("Watch the launch checklist");
  });

  it("lands the primary action in the honest not-wired state, never a fake success", () => {
    render(<NewBotPanel roster={roster} onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Delta Scout" } });
    fireEvent.click(screen.getByRole("button", { name: "Create teammate" }));
    expect(screen.getByText("Not wired on this connection")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
    expect(
      screen.getByText(
        "No create-teammate route exists on this connection. Nothing was sent and no teammate was created.",
      ),
    ).toBeTruthy();
    // The preview still says not created — success is never implied.
    expect(screen.getByText("Not created yet")).toBeTruthy();
  });

  it("closes on Escape and Cancel through the provided callbacks", () => {
    const onClose = vi.fn();
    render(<NewBotPanel roster={roster} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("keeps the launch route honest when the policy is unknown", () => {
    render(<NewBotPanel roster={roster} onClose={() => {}} />);
    const change = screen.getByRole("button", { name: "Change" });
    expect(change.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/no specific model or provider is claimed/i),
    ).toBeTruthy();
  });

  it("renders the zh-CN copy (TD10/HC15)", () => {
    render(<NewBotPanel roster={roster} locale="zh-CN" onClose={() => {}} />);
    expect(screen.getByText("为你的机器人设定角色与团队位置。")).toBeTruthy();
    expect(screen.getByText("以后可以更改。")).toBeTruthy();
    expect(screen.getByText("此构建尚未投影。")).toBeTruthy();
    expect(screen.getByText("尚未创建")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "创建队友" }));
    expect(screen.getByText("此连接未接通")).toBeTruthy();
    expect(
      screen.getByText(/未发送任何请求，也未创建任何队友/),
    ).toBeTruthy();
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });

  it("carries no Paper sample data in the rendered output", () => {
    render(<NewBotPanel roster={roster} onClose={() => {}} />);
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
    expect(document.body.textContent).not.toMatch(/12 teammates/i);
  });
});
