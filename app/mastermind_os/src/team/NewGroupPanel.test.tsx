// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewGroupPanel } from "./NewGroupPanel";
import type { TeamRosterRead } from "./team-roster";
// Fixtures go through Director B's REAL fail-closed parser, so every rendered
// roster is contract-valid by construction (no second parser here).
import { parseTeamRoster } from "../hermes-native/team-roster-contract";
afterEach(cleanup);

const observedGateway = {
  observed: true, source: "gateway_lock" as const, instanceId: "gw-1",
  authorityEpoch: 4, codeVersion: "0.23.0", pid: 1234, state: "serving",
};
const botJson = (over: Record<string, unknown> = {}) => ({
  id: "bot-alpha", displayName: "Alpha Bot", role: "Research lead",
  profilePath: "/Users/operator/.hermes/profiles/alpha", managed: true,
  host: "m2studio", gateway: observedGateway, readiness: "ready",
  readinessReason: "GATEWAY_LOCK_PID_VERIFIED", lastActivity: "2026-11-09T00:00:00Z",
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
  botJson({ id: "bot-gamma", displayName: "Gamma Review", role: "Review" }),
]);

const PAPER_SAMPLES = /Ryan|Meta-CEO|Secretary|Engineering|GLM/i;

describe("NewGroupPanel (HC03) — members and room behavior", () => {
  it("renders group name, purpose and the member picker on the real roster", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    expect(screen.getByText("Give the right teammates a shared place to work.")).toBeTruthy();
    expect(screen.getByLabelText("Group name")).toBeTruthy();
    expect(screen.getByLabelText("Purpose")).toBeTruthy();
    expect(
      screen.getByText("Everyone in the room can use this shared direction."),
    ).toBeTruthy();
    expect(screen.getByText("Who responds?")).toBeTruthy();
    expect(screen.getByText("ROOM BEHAVIOR")).toBeTruthy();
    expect(screen.getByText("Shared context")).toBeTruthy();
  });

  it("derives the search count from the real roster — never a sample literal", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    const search = screen.getByRole("searchbox");
    expect(search.getAttribute("placeholder")).toBe("Search 3 teammates…");
    expect(document.body.textContent).not.toMatch(/12 teammates/i);
  });

  it("selects and deselects real teammates; the count follows the real selection", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    expect(screen.getByText("0 selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Alpha Bot/ }));
    fireEvent.click(screen.getByRole("button", { name: /Beta Ops/ }));
    expect(screen.getByText("2 selected")).toBeTruthy();
    // Selected rows render with a per-member remove control.
    fireEvent.click(screen.getByRole("button", { name: "Remove Alpha Bot" }));
    expect(screen.getByText("1 selected")).toBeTruthy();
  });

  it("filters the member list by the real roster text", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "ops" },
    });
    expect(screen.getByRole("button", { name: /Beta Ops/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Alpha Bot/ })).toBeNull();
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "nothing-matches" },
    });
    expect(screen.getByText("No teammates match this search.")).toBeTruthy();
  });

  it("never invents a member cap the roster contract does not carry", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    expect(document.body.textContent).not.toMatch(/up to \d+/i);
    expect(document.body.textContent).not.toMatch(/最多 \d+ (位|人)/);
  });

  it("offers the three room behaviors as radios and toggles always-on", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    const automatic = screen.getByRole("radio", { name: /Automatic/ }) as HTMLInputElement;
    const lead = screen.getByRole("radio", { name: /Lead/ }) as HTMLInputElement;
    const everyone = screen.getByRole("radio", { name: /Everyone/ }) as HTMLInputElement;
    expect(automatic.checked).toBe(true); // default
    fireEvent.click(lead);
    expect(lead.checked).toBe(true);
    expect(automatic.checked).toBe(false);
    expect(everyone.checked).toBe(false);
    const alwaysOn = screen.getByRole("checkbox", {
      name: /Always-on available/,
    }) as HTMLInputElement;
    expect(alwaysOn.checked).toBe(true);
    fireEvent.click(alwaysOn);
    expect(alwaysOn.checked).toBe(false);
  });

  it("states the honest gateway-unknown room availability when unverified", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    expect(
      screen.getByText(
        "Whether the room can continue depends on the team gateway, which is not verified on this connection.",
      ),
    ).toBeTruthy();
  });

  it("shows the live gateway note when the real gateway state is live", () => {
    render(
      <NewGroupPanel roster={roster} gatewayState="live" onClose={() => {}} />,
    );
    expect(
      screen.getByText("Team gateway is live on this connection."),
    ).toBeTruthy();
  });

  it("renders the honest roster-unavailable state with the read's reason code", () => {
    render(
      <NewGroupPanel
        roster={{ kind: "UNAVAILABLE", reason: "NATIVE_CLIENT_NOT_STARTED" }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("Member search unavailable")).toBeTruthy();
    expect(screen.getByText("NATIVE_CLIENT_NOT_STARTED")).toBeTruthy();
    expect(screen.queryByRole("searchbox")).toBeNull();
    // No teammates are listed while the roster is unverified.
    expect(screen.queryByRole("button", { name: /Alpha Bot/ })).toBeNull();
  });

  it("lands the primary action in the honest not-wired state, never a fake success", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Create group" }));
    expect(screen.getByText("Not wired on this connection")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
    expect(
      screen.getByText(
        "No create-group route exists on this connection. Nothing was sent and no group was created.",
      ),
    ).toBeTruthy();
  });

  it("closes on Escape and Cancel through the provided callbacks", () => {
    const onClose = vi.fn();
    render(<NewGroupPanel roster={roster} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("renders the zh-CN copy (TD10/HC15)", () => {
    render(<NewGroupPanel roster={roster} locale="zh-CN" onClose={() => {}} />);
    expect(screen.getByText("为合适的成员提供一个共享的工作空间。")).toBeTruthy();
    expect(screen.getByText("谁来响应？")).toBeTruthy();
    expect(screen.getByText("房间行为")).toBeTruthy();
    expect(screen.getByText("已选择 0 位")).toBeTruthy();
    expect(screen.getByPlaceholderText("搜索 3 位成员…")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "创建群组" }));
    expect(screen.getByText("此连接未接通")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });

  it("carries no Paper sample data in the rendered output", () => {
    render(<NewGroupPanel roster={roster} onClose={() => {}} />);
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });
});
