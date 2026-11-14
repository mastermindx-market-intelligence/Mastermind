// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SplitConversationsWorkspace,
  type SplitConversationPane,
} from "./SplitConversationsWorkspace";
afterEach(cleanup);

const panes: SplitConversationPane[] = [
  {
    id: "eng",
    header: { title: "Engineering", subtitle: "Reconnect handling review" },
    excerpt: [
      { author: "Engineering", text: "Draft is ready for review.", at: "2026-11-09T20:05:00Z" },
    ],
  },
  {
    id: "research",
    header: { title: "Research Desk", subtitle: "Sector study follow-up" },
    excerpt: null,
  },
];

describe("SplitConversationsWorkspace", () => {
  it("renders exactly two side-by-side panes with header, timeline and footer", () => {
    render(<SplitConversationsWorkspace panes={panes} />);
    expect(screen.getByText("Two conversations")).toBeTruthy();
    expect(
      screen.getByText(/drafts stay independent per conversation/i),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Engineering" }),
    ).toBeTruthy();
    expect(screen.getByText("Reconnect handling review")).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Research Desk" }),
    ).toBeTruthy();
    expect(screen.getByText("Draft is ready for review.")).toBeTruthy();
    expect(screen.getByText("20:05")).toBeTruthy();
    // A third pane is not rendered: the workspace holds exactly two.
    expect(
      screen.queryByText("Third Conversation"),
    ).toBeNull();
    // Both composers exist (disabled without onCompose — still textboxes),
    // and neither carries a custom tabindex: tab order is the pane order.
    const composers = screen.getAllByRole("textbox");
    expect(composers.length).toBe(2);
    for (const composer of composers) {
      expect(composer.hasAttribute("tabindex")).toBe(false);
    }
  });

  it("renders the honest not-projected state for a pane without an excerpt", () => {
    render(<SplitConversationsWorkspace panes={panes} />);
    expect(
      screen.getByText("This conversation is not projected yet."),
    ).toBeTruthy();
  });

  it("keeps independent drafts: typing in one pane never changes the other", () => {
    render(
      <SplitConversationsWorkspace panes={panes} onCompose={vi.fn()} />,
    );
    const composers = screen.getAllByRole("textbox");
    expect(composers.length).toBe(2);
    const [first, second] = composers;
    expect(
      first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    fireEvent.change(first, { target: { value: "draft for engineering" } });
    expect(first.value).toBe("draft for engineering");
    expect(second.value).toBe("");
    fireEvent.change(second, { target: { value: "draft for research" } });
    expect(first.value).toBe("draft for engineering");
    expect(second.value).toBe("draft for research");
  });

  it("sends through onCompose with the pane id and clears only that pane's draft", () => {
    const onCompose = vi.fn();
    render(
      <SplitConversationsWorkspace panes={panes} onCompose={onCompose} />,
    );
    const [first, second] = screen.getAllByRole("textbox");
    const [sendFirst, sendSecond] = screen.getAllByRole("button", {
      name: "Send",
    });
    expect(sendFirst.hasAttribute("disabled")).toBe(true);
    fireEvent.change(first, { target: { value: "engineering note" } });
    fireEvent.change(second, { target: { value: "research note" } });
    expect(sendFirst.hasAttribute("disabled")).toBe(false);
    fireEvent.click(sendFirst);
    expect(onCompose).toHaveBeenCalledWith("eng", "engineering note");
    expect(first.value).toBe("");
    expect(second.value).toBe("research note");
    expect(sendSecond.hasAttribute("disabled")).toBe(false);
  });

  it("disables both composers with their honest reason when no send path is wired", () => {
    render(<SplitConversationsWorkspace panes={panes} />);
    const textareas = screen.getAllByPlaceholderText(
      "No send path is wired. Composing is unavailable.",
    );
    expect(textareas.length).toBe(2);
    for (const textarea of textareas) {
      expect(textarea.hasAttribute("disabled")).toBe(true);
    }
    for (const send of screen.getAllByRole("button", { name: "Send" })) {
      expect(send.hasAttribute("disabled")).toBe(true);
    }
    expect(
      screen.getAllByText(/No send path is wired to this workspace/i).length,
    ).toBe(2);
    expect(screen.getAllByText("Draft stays with this conversation.").length).toBe(2);
  });

  it("renders an empty excerpt as a real empty state, distinct from not projected", () => {
    render(
      <SplitConversationsWorkspace
        panes={[
          { ...panes[0], excerpt: [] },
          panes[1],
        ]}
      />,
    );
    expect(screen.getByText("No messages yet.")).toBeTruthy();
    expect(
      screen.getByText("This conversation is not projected yet."),
    ).toBeTruthy();
  });

  it("states honestly when the workspace has no conversations", () => {
    render(<SplitConversationsWorkspace panes={[]} />);
    expect(
      screen.getByText("This workspace needs two conversations."),
    ).toBeTruthy();
  });

  it("renders the honest zh-CN copy", () => {
    render(
      <SplitConversationsWorkspace
        locale="zh-CN"
        panes={panes}
        onCompose={vi.fn()}
      />,
    );
    expect(screen.getByText("两个对话")).toBeTruthy();
    expect(screen.getByText("分屏视图 · 各对话草稿相互独立")).toBeTruthy();
    expect(screen.getByText("此对话尚未投影。")).toBeTruthy();
    expect(screen.getAllByPlaceholderText("写入此对话…").length).toBe(2);
    expect(screen.getAllByText("草稿保留在此对话中。").length).toBe(2);
    expect(screen.getAllByRole("button", { name: "发送" }).length).toBe(2);
  });

  it("ships no sample data: forbidden board literals never appear in output", () => {
    for (const node of [
      <SplitConversationsWorkspace key="empty" panes={[]} />,
      <SplitConversationsWorkspace key="full" panes={panes} />,
    ]) {
      const { container } = render(node);
      expect(container.textContent).not.toMatch(/Ryan|Meta-CEO|Secretary/);
      expect(container.textContent).not.toMatch(/\b2 min\b/);
      cleanup();
    }
  });
});
