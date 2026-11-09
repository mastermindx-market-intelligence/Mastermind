// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeamWorkspace, classifyGatewayState } from "./TeamWorkspace";
import type { TeamRosterEntry, TeamRosterRead } from "./team-roster-contract";
import type { DelegatedTask } from "./delegated-task";
afterEach(cleanup);

function bot(extra: Partial<TeamRosterEntry> = {}): TeamRosterEntry {
  return {
    botId: "bot-alpha",
    displayName: "Alpha Bot",
    role: "Research lead",
    profile: null,
    gatewayInstance: "gw-1",
    host: "m2studio",
    readiness: "ready",
    readinessReason: null,
    lastActivity: "2026-11-09T00:00:00Z",
    activitySummary: "Reading regime data",
    ...extra,
  };
}
const available = (bots: TeamRosterEntry[]): TeamRosterRead => ({
  kind: "AVAILABLE",
  roster: { schema: "mastermind.team_roster.v1", bots },
});
const task: DelegatedTask = {
  taskId: "task-1",
  title: "Repair launch refusal",
  summary: null,
  state: "queued",
  stateReason: null,
  owner: null,
  route: [],
  authority: "preview",
  lastActivity: null,
  result: null,
};

describe("classifyGatewayState — distinct conversation states per HS01", () => {
  it("maps observed gateway states and codes without inventing health", () => {
    expect(classifyGatewayState("OPENED", null)).toBe("live");
    expect(classifyGatewayState("ADMITTED", null)).toBe("live");
    expect(classifyGatewayState(null, null)).toBe("unknown");
    expect(classifyGatewayState("REFUSED", null)).toBe("unknown");
    expect(
      classifyGatewayState("UNAVAILABLE", "NATIVE_PLATFORM_UNAVAILABLE"),
    ).toBe("viewer-disconnected");
    expect(
      classifyGatewayState("UNAVAILABLE", "NATIVE_CLIENT_NOT_STARTED"),
    ).toBe("viewer-disconnected");
    expect(classifyGatewayState("UNAVAILABLE", "NATIVE_BUSY")).toBe(
      "gateway-busy",
    );
    expect(classifyGatewayState("UNAVAILABLE", "NATIVE_QUOTA_EXCEEDED")).toBe(
      "quota",
    );
    expect(classifyGatewayState("EFFECT_UNKNOWN", "SOMETHING_ELSE")).toBe(
      "unknown",
    );
    expect(
      classifyGatewayState("EFFECT_UNKNOWN", "NATIVE_INSTALL_UNAVAILABLE"),
    ).toBe("viewer-disconnected");
  });
});

describe("TeamWorkspace roster (TD01/TS01)", () => {
  it("renders the roster table with honest unknowns, never an invented company", () => {
    render(
      <TeamWorkspace
        roster={available([
          bot(),
          bot({
            botId: "bot-beta",
            displayName: "Beta",
            role: "Ops",
            readiness: "degraded",
            readinessReason: "gateway reconnecting",
            lastActivity: null,
            activitySummary: null,
            host: null,
          }),
          bot({
            botId: "bot-gamma",
            displayName: "Gamma",
            role: "Review",
            readiness: "unknown",
            readinessReason: "no reading in 48h",
            gatewayInstance: null,
          }),
        ])}
      />,
    );
    expect(screen.getByRole("table", { name: "Team roster" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Alpha Bot" })).toBeTruthy();
    expect(screen.getByText("Alpha Bot")).toBeTruthy();
    expect(screen.getByText("Ready")).toBeTruthy();
    expect(
      document.querySelector(".mm-roster-state[data-readiness='degraded']")
        ?.textContent,
    ).toContain("Degraded");
    expect(
      document.querySelector(".mm-roster-state[data-readiness='degraded']")
        ?.textContent,
    ).toContain("gateway reconnecting");
    expect(
      document.querySelector(".mm-roster-state[data-readiness='unknown']")
        ?.textContent,
    ).toContain("Unknown");
    expect(
      document.querySelector(".mm-roster-state[data-readiness='unknown']")
        ?.textContent,
    ).toContain("no reading in 48h");
    // A teammate with no observed focus shows unknown, and never a fabricated summary.
    const rows = document.querySelectorAll(".mm-roster tbody tr");
    expect(rows[1]!.textContent).toContain("Unknown"); // Beta has no activity summary
    expect(rows[1]!.textContent).not.toContain("No activity observed"); // detail-view fact only
    expect(rows[2]!.textContent).toContain(
      "Last activity 2026-11-09T00:00:00Z",
    );
    expect(screen.queryByText(/Team needs a connection/i)).toBeNull();
  });

  it("keeps an unavailable source unverified — never an empty company (TS01)", () => {
    const onOpenConversations = vi.fn();
    render(
      <TeamWorkspace
        roster={{
          kind: "UNAVAILABLE",
          reason: "TEAM_ROSTER_SOURCE_NOT_CONNECTED",
        }}
        onOpenConversations={onOpenConversations}
      />,
    );
    expect(screen.getByText("Team needs a connection")).toBeTruthy();
    expect(screen.getByText("Roster not verified")).toBeTruthy();
    expect(screen.getByText("Current team size")).toBeTruthy();
    expect(screen.getByText("Not verified")).toBeTruthy();
    expect(screen.getByText("Presence")).toBeTruthy();
    expect(screen.getByText("Not observed")).toBeTruthy();
    expect(
      screen.getByText(
        /An unavailable source is never shown as an empty company/i,
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Open recent conversations" }),
    );
    expect(onOpenConversations).toHaveBeenCalledTimes(1);
  });

  it("says the source is unverifiable when data fails the contract", () => {
    render(
      <TeamWorkspace
        roster={{ kind: "UNAVAILABLE", reason: "TEAM_ROSTER_SOURCE_INVALID" }}
      />,
    );
    expect(
      screen.getByText(
        /returned data this surface could not verify\. Nothing is shown from it/i,
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("opens a bot detail with honest facts, PREVIEW authority and the existing conversation panel", () => {
    const conversationPanel = <div data-testid="existing-hermes-panel" />;
    render(
      <TeamWorkspace
        roster={available([bot()])}
        conversationPanel={conversationPanel}
        gateway={{ state: "UNAVAILABLE", code: "NATIVE_BUSY" }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open Alpha Bot" }));
    expect(screen.getByText(/Research lead · m2studio/)).toBeTruthy();
    expect(screen.getByText("PREVIEW")).toBeTruthy();
    expect(screen.getByTestId("existing-hermes-panel")).toBeTruthy();
    // The section note yields to the App-owned panel — this view adds no second transport.
    expect(screen.queryByText(/never creates a second transport/i)).toBeNull();
    const facts = document.querySelector(".mm-team-bot-facts")!.textContent!;
    expect(facts).toContain("Ready");
    expect(facts).toContain("Last activity 2026-11-09T00:00:00Z");
    expect(facts).toContain("gw-1");
    expect(screen.getByRole("status").textContent).toBe("Gateway busy");
    expect(
      screen.getByText(/team gateway is handling one operation/i),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /No delegated coding task is projected for this teammate yet/i,
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "← Team" }));
    expect(screen.getByRole("table", { name: "Team roster" })).toBeTruthy();
  });

  it("labels the four distinct non-live gateway states (HS01)", () => {
    const cases: {
      gateway: { state: string | null; code: string | null };
      label: string;
      note: RegExp | null;
    }[] = [
      { gateway: { state: "OPENED", code: null }, label: "Live", note: null },
      {
        gateway: { state: "UNAVAILABLE", code: "NATIVE_PLATFORM_UNAVAILABLE" },
        label: "Viewer disconnected",
        note: /cannot reach the team gateway/i,
      },
      {
        gateway: { state: "UNAVAILABLE", code: "NATIVE_BUSY" },
        label: "Gateway busy",
        note: /handling one operation/i,
      },
      {
        gateway: { state: "UNAVAILABLE", code: "NATIVE_QUOTA_LIMIT" },
        label: "Quota limited",
        note: /reports a quota limit/i,
      },
      {
        gateway: { state: null, code: null },
        label: "Connection unknown",
        note: /not confirmed/i,
      },
    ];
    for (const { gateway, label, note } of cases) {
      const { unmount } = render(
        <TeamWorkspace roster={available([bot()])} gateway={gateway} />,
      );
      fireEvent.click(screen.getByRole("button", { name: "Open Alpha Bot" }));
      expect(screen.getByRole("status").textContent).toBe(label);
      if (note === null) {
        expect(screen.queryByText(/Controls stay limited until/i)).toBeNull();
      } else {
        expect(screen.getByText(note)).toBeTruthy();
      }
      unmount();
    }
  });

  it("navigates the roster by keyboard ArrowUp/ArrowDown/Home/End (TD01)", () => {
    render(
      <TeamWorkspace
        roster={available([
          bot(),
          bot({ botId: "bot-beta", displayName: "Beta Bot" }),
          bot({ botId: "bot-gamma", displayName: "Gamma Bot" }),
        ])}
      />,
    );
    const rows = screen.getAllByRole("button", { name: /^Open / });
    expect(rows).toHaveLength(3);
    rows[0]!.focus();
    expect(document.activeElement).toBe(rows[0]);
    fireEvent.keyDown(rows[0]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(rows[1]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[2]);
    fireEvent.keyDown(rows[2]!, { key: "ArrowDown" }); // clamped at the end
    expect(document.activeElement).toBe(rows[2]);
    fireEvent.keyDown(rows[2]!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(rows[1]!, { key: "Home" });
    expect(document.activeElement).toBe(rows[0]);
    fireEvent.keyDown(rows[0]!, { key: "End" });
    expect(document.activeElement).toBe(rows[2]);
  });

  it("shows the delegated coding task on the bot detail when one is projected", () => {
    render(<TeamWorkspace roster={available([bot()])} delegatedTask={task} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Alpha Bot" }));
    expect(screen.getByText("Delegated coding work")).toBeTruthy();
    expect(screen.getByText("Repair launch refusal")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
  });

  it("renders the honest zh-CN roster and unavailable copy", () => {
    const { unmount } = render(
      <TeamWorkspace roster={available([bot()])} locale="zh-CN" />,
    );
    expect(screen.getByRole("table", { name: "团队名册" })).toBeTruthy();
    expect(screen.getByText("就绪")).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开 Alpha Bot" })).toBeTruthy();
    unmount();
    render(
      <TeamWorkspace
        roster={{
          kind: "UNAVAILABLE",
          reason: "TEAM_ROSTER_SOURCE_NOT_CONNECTED",
        }}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("团队需要连接")).toBeTruthy();
    expect(screen.getByText("名册未验证")).toBeTruthy();
    expect(screen.getByText("未验证")).toBeTruthy();
    expect(screen.getByText(/来源不可用时，绝不显示为空公司。/)).toBeTruthy();
  });
});
