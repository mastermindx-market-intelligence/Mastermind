// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TeamWorkspace, classifyGatewayState } from "./TeamWorkspace";
import type { TeamRosterRead } from "./team-roster";
// Fixtures are built through Director B's REAL fail-closed parser, so every
// rendered roster is contract-valid by construction (no second parser here).
import { parseTeamRoster } from "../hermes-native/team-roster-contract";
import type { DelegatedTask } from "./delegated-task";
afterEach(cleanup);

const observedGateway = (over: Record<string, unknown> = {}) => ({
  observed: true, source: "control_socket_identify", instanceId: "gw-1",
  authorityEpoch: 4, codeVersion: "0.23.0", pid: 1234, state: "ready", ...over,
});
const unobservedGateway = {
  observed: false, source: "none", instanceId: null, authorityEpoch: null,
  codeVersion: null, pid: null, state: null,
};
const botJson = (over: Record<string, unknown> = {}) => ({
  id: "bot-alpha", displayName: "Alpha Bot", role: "Research lead",
  profilePath: "/Users/operator/.hermes/profiles/alpha", managed: true,
  host: "m2studio", gateway: observedGateway(), readiness: "ready",
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
const task: DelegatedTask = {
  binding: {
    schema: "ExecutionBinding.v1",
    root_run_ref: "root-wo19-coding-7",
    immediate_parent_run_ref: "run-41",
    logical_child_key: "fleet-launch-repair",
    request_digest: "a".repeat(64),
    effective_complexity: "C2_COMPLEX_BOUNDED",
    task_kind: "code",
    runtime_kind: "",
    operation_key: "",
    caller_namespace: "",
    lease_ref: "",
  },
  title: "Repair launch refusal",
  summary: null,
  state: "queued",
  stateReason: null,
  owner: null,
  route: [],
  authority: "preview",
  lastActivity: null,
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

  it("NM-06: a stopped gateway is its own state — never busy or disconnected", () => {
    for (const code of ["NATIVE_GATEWAY_STOPPED", "NATIVE_GATEWAY_NOT_RUNNING"]) {
      expect(classifyGatewayState("UNAVAILABLE", code)).toBe("gateway-stopped");
    }
    expect(
      new Set([
        classifyGatewayState("UNAVAILABLE", "NATIVE_GATEWAY_STOPPED"),
        classifyGatewayState("UNAVAILABLE", "NATIVE_BUSY"),
        classifyGatewayState("UNAVAILABLE", "NATIVE_CLIENT_UNAVAILABLE"),
      ]),
    ).toEqual(new Set(["gateway-stopped", "gateway-busy", "viewer-disconnected"]));
  });
});

describe("TeamWorkspace roster (TD01/TS01) on Director B's contract", () => {
  it("renders honest ready/degraded/unknown rows with visible reason codes", () => {
    render(
      <TeamWorkspace
        roster={available([
          botJson(),
          botJson({
            id: "bot-beta",
            displayName: "Beta",
            role: "Ops",
            managed: false,
            gateway: { ...observedGateway({ source: "gateway_lock", state: "lock_only", instanceId: "gw-2" }) },
            readiness: "degraded",
            readinessReason: "GATEWAY_PID_NOT_RUNNING",
            lastActivity: null,
            activitySummary: null,
            activityReason: "NO_STATE_DB",
          }),
          botJson({
            id: "bot-gamma",
            displayName: "Gamma",
            role: "Review",
            host: "unknown",
            gateway: unobservedGateway,
            readiness: "unknown",
            readinessReason: "NO_GATEWAY_LOCK",
            lastActivity: null,
            activitySummary: null,
            activityReason: "NO_SESSIONS",
          }),
        ])}
      />,
    );
    expect(screen.getByRole("table", { name: "Team roster" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Alpha Bot" })).toBeTruthy();
    expect(screen.getByText("Ready")).toBeTruthy();
    const degraded = document.querySelector(
      ".mm-roster-state[data-readiness='degraded']",
    )!;
    expect(degraded.textContent).toContain("Degraded");
    // Human-readable phrase AND the closed reason code stay visible.
    expect(degraded.textContent).toContain("GATEWAY_PID_NOT_RUNNING");
    expect(degraded.textContent).toContain("Locked gateway process is not running");
    const unknown = document.querySelector(
      ".mm-roster-state[data-readiness='unknown']",
    )!;
    expect(unknown.textContent).toContain("Unknown");
    expect(unknown.textContent).toContain("NO_GATEWAY_LOCK");
    expect(unknown.textContent).not.toContain("Ready");
    // Unobserved activity carries its typed reason, never a fabricated summary.
    const rows = document.querySelectorAll(".mm-roster tbody tr");
    expect(rows[0]!.textContent).toContain("Last activity 2026-11-09T00:00:00Z");
    expect(rows[1]!.textContent).toContain("NO_STATE_DB");
    expect(rows[1]!.textContent).not.toContain("No activity observed");
    // host:"unknown" is a sentinel, never rendered as an observed hostname.
    expect(rows[0]!.querySelector(".mm-roster-host")!.textContent).toBe("m2studio");
    expect(rows[2]!.querySelector(".mm-roster-host")).toBeNull();
    expect(screen.queryByText(/Team needs a connection/i)).toBeNull();
  });

  it("keeps an unavailable source unverified — never an empty company (TS01)", () => {
    const onOpenConversations = vi.fn();
    render(
      <TeamWorkspace
        roster={{
          kind: "UNAVAILABLE",
          reason: "NATIVE_PLATFORM_UNAVAILABLE",
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
    // The port's closed reason code stays visible, never paraphrased away.
    expect(screen.getByText("NATIVE_PLATFORM_UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Open recent conversations" }),
    );
    expect(onOpenConversations).toHaveBeenCalledTimes(1);
  });

  it("says the source is unverifiable when data fails the contract", () => {
    render(
      <TeamWorkspace
        roster={{ kind: "UNAVAILABLE", reason: "NATIVE_RESPONSE_INVALID" }}
      />,
    );
    expect(
      screen.getByText(
        /returned data this surface could not verify\. Nothing is shown from it/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("NATIVE_RESPONSE_INVALID")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("renders an honest PENDING state — never an empty roster table", () => {
    render(<TeamWorkspace roster={{ kind: "PENDING" }} />);
    expect(screen.getByText("Reading the team roster…")).toBeTruthy();
    expect(
      screen.getByText(/read once from the local native runtime/i),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText(/Team needs a connection/i)).toBeNull();
  });

  it("opens a bot detail with B's richer facts, PREVIEW authority and the existing conversation panel", () => {
    const conversationPanel = <div data-testid="existing-hermes-panel" />;
    render(
      <TeamWorkspace
        roster={available([botJson()])}
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
    expect(facts).toContain("GATEWAY_IDENTIFY_READY");
    expect(facts).toContain("Last activity 2026-11-09T00:00:00Z");
    expect(facts).toContain("gw-1");
    expect(facts).toContain("ready"); // gateway.state when observed
    expect(facts).toContain("control_socket_identify"); // gateway.source stays visible
    expect(facts).toContain("Yes"); // managed: true
    expect(facts).toContain("/Users/operator/.hermes/profiles/alpha");
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

  it("keeps unobserved detail facts honest (unknown gateway, managed null, activity reason)", () => {
    render(
      <TeamWorkspace
        roster={available([
          botJson({
            id: "bot-gamma",
            displayName: "Gamma",
            host: "unknown",
            managed: null,
            gateway: unobservedGateway,
            readiness: "unknown",
            readinessReason: "NO_GATEWAY_LOCK",
            lastActivity: null,
            activitySummary: null,
            activityReason: "NO_STATE_DB",
          }),
        ])}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open Gamma" }));
    const facts = document.querySelector(".mm-team-bot-facts")!.textContent!;
    expect(facts).toContain("Unknown"); // readiness label + managed null
    expect(facts).toContain("NO_GATEWAY_LOCK");
    expect(facts).toContain("No activity observed");
    expect(facts).toContain("NO_STATE_DB");
    expect(facts).toContain("none"); // gateway.source
  });

  it("labels the five distinct non-live gateway states (HS01 + NM-06)", () => {
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
        gateway: { state: "UNAVAILABLE", code: "NATIVE_GATEWAY_STOPPED" },
        label: "Gateway stopped",
        note: /its owner starts it.*no automatic restart or reconnect/i,
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
        <TeamWorkspace roster={available([botJson()])} gateway={gateway} />,
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
          botJson(),
          botJson({ id: "bot-beta", displayName: "Beta Bot" }),
          botJson({ id: "bot-gamma", displayName: "Gamma Bot" }),
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
    render(<TeamWorkspace roster={available([botJson()])} delegatedTask={task} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Alpha Bot" }));
    expect(screen.getByText("Delegated coding work")).toBeTruthy();
    expect(screen.getByText("Repair launch refusal")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
  });

  it("renders the honest zh-CN roster, pending and unavailable copy", () => {
    const { unmount } = render(
      <TeamWorkspace roster={available([botJson()])} locale="zh-CN" />,
    );
    expect(screen.getByRole("table", { name: "团队名册" })).toBeTruthy();
    expect(screen.getByText("就绪")).toBeTruthy();
    expect(screen.getByRole("button", { name: "打开 Alpha Bot" })).toBeTruthy();
    expect(screen.getByText("GATEWAY_IDENTIFY_READY")).toBeTruthy();
    expect(screen.getByText("控制套接字 identify 已验证网关")).toBeTruthy();
    unmount();
    render(
      <TeamWorkspace
        roster={{ kind: "UNAVAILABLE", reason: "NATIVE_PLATFORM_UNAVAILABLE" }}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("团队需要连接")).toBeTruthy();
    expect(screen.getByText("名册未验证")).toBeTruthy();
    expect(screen.getByText("未验证")).toBeTruthy();
    expect(screen.getByText(/来源不可用时，绝不显示为空公司。/)).toBeTruthy();
    expect(screen.getByText("NATIVE_PLATFORM_UNAVAILABLE")).toBeTruthy();
    unmount();
    render(<TeamWorkspace roster={{ kind: "PENDING" }} locale="zh-CN" />);
    expect(screen.getByText("正在读取团队名册…")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
