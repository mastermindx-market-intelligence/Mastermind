// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  InboxNeedsYouPanel,
  type InboxRequest,
} from "./InboxNeedsYouPanel";
import type { TeamRosterRead } from "./team-roster";
afterEach(cleanup);

const roster: TeamRosterRead = {
  kind: "AVAILABLE",
  roster: {
    schema: "mastermind.team_roster/v1",
    generatedAt: "2026-11-09T20:00:00Z",
    host: "m2studio",
    bots: [
      {
        id: "engineering",
        displayName: "Engineering",
        role: "Always-on teammate",
        managed: true,
        host: "m2studio",
        gateway: {
          observed: false,
          source: "none",
          instanceId: null,
          authorityEpoch: null,
          codeVersion: null,
          pid: null,
          state: null,
        },
        readiness: "ready",
        readinessReason: "GATEWAY_IDENTIFY_READY",
        lastActivity: "2026-11-09T19:55:00Z",
        activitySummary: null,
      },
      {
        id: "research",
        displayName: "Research Desk",
        role: "",
        managed: null,
        host: "unknown",
        gateway: {
          observed: false,
          source: "none",
          instanceId: null,
          authorityEpoch: null,
          codeVersion: null,
          pid: null,
          state: null,
        },
        readiness: "unknown",
        readinessReason: "NO_GATEWAY_LOCK",
        lastActivity: null,
        activitySummary: null,
        activityReason: "ACTIVITY_TIMESTAMP_INVALID",
      },
    ],
  },
};

const minutesAgo = (minutes: number) =>
  new Date(Date.now() - minutes * 60_000).toISOString();

function fixtureRequests(): InboxRequest[] {
  return [
    {
      id: "req-1",
      teammateId: "engineering",
      kind: "question",
      summary: "Where should the daily briefing go?",
      waitingSince: minutesAgo(2),
      options: ["Morning digest", "Research channel"],
      conversationExcerpt: [
        { author: "Engineering", text: "The briefing draft is ready.", at: "2026-11-09T20:05:00Z" },
      ],
    },
    {
      id: "req-2",
      teammateId: "research",
      kind: "result_review",
      summary: "Sector study results returned",
      waitingSince: minutesAgo(8),
      conversationExcerpt: null,
    },
  ];
}

describe("InboxNeedsYouPanel", () => {
  it("moves roving focus through the waiting list with arrow keys", () => {
    render(
      <InboxNeedsYouPanel roster={roster} requests={fixtureRequests()} />,
    );
    const first = screen.getByRole("button", {
      name: "Open request from Engineering",
    });
    const second = screen.getByRole("button", {
      name: "Open request from Research Desk",
    });
    first.focus();
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(document.activeElement!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: "End" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(first);
  });

  it("computes the kind · age chip from waitingSince and identity from the roster", () => {
    render(
      <InboxNeedsYouPanel roster={roster} requests={fixtureRequests()} />,
    );
    expect(
      document.querySelector('.mm-cv-kind-chip[data-kind="question"]')
        ?.textContent,
    ).toBe("Question · 2 min");
    expect(
      document.querySelector('.mm-cv-kind-chip[data-kind="result_review"]')
        ?.textContent,
    ).toBe("Result to review · 8 min");
    // Names come from the roster, never a sample.
    expect(screen.getByText("Engineering")).toBeTruthy();
    expect(screen.getByText("Research Desk")).toBeTruthy();
  });

  it("selects a request, renders the exact ask from roster identity, and reports the selection", () => {
    const onSelectRequest = vi.fn();
    const { rerender } = render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        onSelectRequest={onSelectRequest}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Open request from Engineering" }),
    );
    expect(onSelectRequest).toHaveBeenCalledWith("req-1");
    // Controlled selection renders the detail pane.
    rerender(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-1"
        onSelectRequest={onSelectRequest}
      />,
    );
    expect(screen.getByText("Waiting for your answer")).toBeTruthy();
    expect(screen.getByText("Always-on teammate")).toBeTruthy();
    // The summary appears in the rail card and as the exact-request title.
    expect(
      screen.getAllByText("Where should the daily briefing go?").length,
    ).toBe(2);
    expect(screen.getByText("The briefing draft is ready.")).toBeTruthy();
    expect(screen.getByText("20:05")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Morning digest" })).toBeTruthy();
    expect(screen.getByText("Reading keeps requests open.")).toBeTruthy();
  });

  it("keeps option buttons disabled with a visible reason until an answer path is wired", () => {
    render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-1"
      />,
    );
    const option = screen.getByRole("button", { name: "Morning digest" });
    expect(option.hasAttribute("disabled")).toBe(true);
    expect(option.getAttribute("aria-describedby")).toMatch(/-answer-reason$/);
    expect(
      screen.getByText(/Answering needs a wired answer path/i),
    ).toBeTruthy();
  });

  it("answers through the wired callback", () => {
    const onAnswer = vi.fn();
    render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-1"
        onAnswer={onAnswer}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Research channel" }));
    expect(onAnswer).toHaveBeenCalledWith("Research channel");
  });

  it("disables Open beside and Details with their reason when the callbacks are absent", () => {
    render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-2"
      />,
    );
    for (const name of ["Open beside", "Details"]) {
      const button = screen.getByRole("button", { name });
      expect(button.hasAttribute("disabled")).toBe(true);
      expect(button.getAttribute("aria-describedby")).toMatch(
        /-action-reason$/,
      );
    }
    expect(
      screen.getByText(/This action is not wired to a live surface yet/i),
    ).toBeTruthy();
  });

  it("opens the conversation through the provided action and shows no exact options honestly", () => {
    const onOpenConversation = vi.fn();
    render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-2"
        onOpenConversation={onOpenConversation}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open beside" }));
    expect(onOpenConversation).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText(/No exact options are projected/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/No conversation excerpt is projected/i),
    ).toBeTruthy();
  });

  it("renders the not-connected composer with no send path", () => {
    render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-1"
      />,
    );
    const composer = screen.getByLabelText(/To Engineering · Private conversation/);
    expect(composer.hasAttribute("disabled")).toBe(true);
    const send = screen.getByRole("button", { name: "Send" });
    expect(send.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/No send path exists on this surface/i),
    ).toBeTruthy();
  });

  it("filters the real list from the search input", () => {
    render(
      <InboxNeedsYouPanel roster={roster} requests={fixtureRequests()} />,
    );
    const search = screen.getByLabelText("Search messages and people");
    fireEvent.change(search, { target: { value: "sector" } });
    expect(
      screen.queryByRole("button", { name: "Open request from Engineering" }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: "Open request from Research Desk" }),
    ).toBeTruthy();
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText(/No matches for “zzz”/i)).toBeTruthy();
  });

  it("renders nothing for pinned/archived when absent and rows when provided", () => {
    const { container, rerender } = render(
      <InboxNeedsYouPanel roster={roster} requests={fixtureRequests()} />,
    );
    expect(container.textContent).not.toContain("PINNED");
    expect(container.textContent).not.toContain("ARCHIVED");
    rerender(
      <InboxNeedsYouPanel
        roster={roster}
        requests={fixtureRequests()}
        pinned={[{ id: "p1", label: "Engineering room" }]}
        archived={[{ id: "a1", label: "Old planning room" }]}
      />,
    );
    expect(container.textContent).toContain("PINNED · 1");
    expect(container.textContent).toContain("Engineering room");
    expect(container.textContent).toContain("Old planning room");
    expect(container.textContent).toContain("View →");
  });

  it("renders the honest unavailable state when no request projection is wired", () => {
    const { container } = render(
      <InboxNeedsYouPanel roster={roster} requests={null} />,
    );
    expect(screen.getByText("No request projection is wired")).toBeTruthy();
    expect(
      screen.getByText(/nothing is shown or invented/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/never shown as an empty inbox/i),
    ).toBeTruthy();
    // No fabricated cards, no search over an unwired source.
    expect(container.querySelectorAll(".mm-cv-request-card").length).toBe(0);
    expect(
      screen.queryByLabelText("Search messages and people"),
    ).toBeNull();
  });

  it("treats an empty request list as a real empty state, distinct from unwired", () => {
    render(<InboxNeedsYouPanel roster={roster} requests={[]} />);
    expect(
      screen.getByText(/No requests are waiting for your response/i),
    ).toBeTruthy();
    expect(screen.queryByText("No request projection is wired")).toBeNull();
  });

  it("shows an unresolvable teammate as its own key, never an invented name", () => {
    render(
      <InboxNeedsYouPanel
        roster={roster}
        requests={[
          {
            id: "req-x",
            teammateId: "unlisted",
            kind: "action_needed",
            summary: "Unlisted teammate ask",
            waitingSince: minutesAgo(47),
            conversationExcerpt: null,
          },
        ]}
        selectedId="req-x"
      />,
    );
    expect(screen.getAllByText("#unlisted").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Teammate identity not verified against the roster/i),
    ).toBeTruthy();
    expect(
      document.querySelector('.mm-cv-kind-chip[data-kind="action_needed"]')
        ?.textContent,
    ).toBe("Action needed · 47 min");
  });

  it("renders the honest zh-CN copy", () => {
    render(
      <InboxNeedsYouPanel
        locale="zh-CN"
        roster={roster}
        requests={fixtureRequests()}
        selectedId="req-1"
      />,
    );
    expect(screen.getByText("需要你")).toBeTruthy();
    expect(screen.getByLabelText("搜索消息与成员")).toBeTruthy();
    expect(screen.getByText("等待你的回复")).toBeTruthy();
    expect(
      document.querySelector('.mm-cv-kind-chip[data-kind="question"]')
        ?.textContent,
    ).toBe("问题 · 2 分钟");
    expect(screen.getByText("等待你的回答")).toBeTruthy();
    expect(screen.getByText("确切请求")).toBeTruthy();
    expect(
      screen.getByText(/此界面没有发送通道/i),
    ).toBeTruthy();
  });

  it("ships no sample data: forbidden board literals never appear in output", () => {
    const states: React.ReactNode[] = [
      <InboxNeedsYouPanel key="null" roster={roster} requests={null} />,
      <InboxNeedsYouPanel key="empty" roster={roster} requests={[]} />,
      <InboxNeedsYouPanel
        key="filled"
        roster={roster}
        requests={[
          {
            id: "req-9",
            teammateId: "engineering",
            kind: "question",
            summary: "A real projected ask",
            waitingSince: minutesAgo(47),
            conversationExcerpt: null,
          },
        ]}
        selectedId="req-9"
      />,
    ];
    for (const node of states) {
      const { container } = render(node);
      expect(container.textContent).not.toMatch(/Ryan|Meta-CEO|Secretary/);
      expect(container.textContent).not.toContain("2 min");
      cleanup();
    }
  });
});
