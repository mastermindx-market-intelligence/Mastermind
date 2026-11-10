// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReplyThreadPanel } from "./ReplyThreadPanel";
afterEach(cleanup);

const origin = {
  author: "Engineering",
  text: "Reconnect handling changed; review the flow before tonight.",
  at: "2026-11-09T20:05:00Z",
};

const replies = [
  {
    id: "r1",
    author: "Research Desk",
    text: "The retry branch looks right to me.",
    at: "2026-11-09T20:11:00Z",
    taskLink: { label: "Reconnect handling", onOpen: vi.fn() },
  },
  {
    id: "r2",
    author: "Engineering",
    text: "Noted — I will hold the merge until you confirm.",
    at: "2026-11-09T20:14:00Z",
  },
];

describe("ReplyThreadPanel", () => {
  it("renders the origin, replies with task link, and the thread note", () => {
    render(<ReplyThreadPanel origin={origin} replies={replies} />);
    expect(screen.getByText("Thread")).toBeTruthy();
    expect(screen.getByText("2 replies")).toBeTruthy();
    expect(screen.getByText(origin.text)).toBeTruthy();
    expect(screen.getByText("20:05")).toBeTruthy();
    expect(screen.getByText("The retry branch looks right to me.")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Reconnect handling →" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Replies stay with this message. Mention a teammate to bring them in.",
      ),
    ).toBeTruthy();
  });

  it("opens the original, the task link, the preview and the mention picker through wired callbacks", () => {
    const onViewOriginal = vi.fn();
    const onOpenPreview = vi.fn();
    const onMention = vi.fn();
    render(
      <ReplyThreadPanel
        origin={{ ...origin, onViewOriginal }}
        replies={replies}
        attachment={{
          name: "reconnect-flow.png",
          kind: "Image",
          onOpenPreview,
        }}
        onReply={vi.fn()}
        onMention={onMention}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "View original message →" }),
    );
    expect(onViewOriginal).toHaveBeenCalledTimes(1);
    fireEvent.click(
      screen.getByRole("button", { name: "Reconnect handling →" }),
    );
    expect(replies[0].taskLink!.onOpen).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Open preview" }));
    expect(onOpenPreview).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "＋ @ Mention" }));
    expect(onMention).toHaveBeenCalledTimes(1);
    expect(screen.getByText("reconnect-flow.png")).toBeTruthy();
    expect(screen.getByText("Image")).toBeTruthy();
  });

  it("renders the honest not-projected state for null replies and a real empty state for none", () => {
    render(<ReplyThreadPanel origin={origin} replies={null} />);
    expect(screen.getByText("Thread")).toBeTruthy();
    expect(
      screen.getByText("Replies are not projected for this message."),
    ).toBeTruthy();
    cleanup();
    render(<ReplyThreadPanel origin={origin} replies={[]} />);
    expect(screen.getByText("No replies yet.")).toBeTruthy();
    expect(
      screen.queryByText("Replies are not projected for this message."),
    ).toBeNull();
  });

  it("keeps the composer disabled with its reason when no send path is wired", () => {
    render(<ReplyThreadPanel origin={origin} replies={replies} />);
    const textarea = screen.getByPlaceholderText("Reply to this thread…");
    expect(textarea.hasAttribute("disabled")).toBe(true);
    const reply = screen.getByRole("button", { name: "Reply" });
    expect(reply.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(
        /No send path is wired to this surface. Replies cannot be sent/i,
      ),
    ).toBeTruthy();
    // Mention and View original carry their own honest reasons.
    const mention = screen.getByRole("button", { name: "＋ @ Mention" });
    expect(mention.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Mention needs a wired people picker/i)).toBeTruthy();
    const viewOriginal = screen.getByRole("button", {
      name: "View original message →",
    });
    expect(viewOriginal.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/original message view is not wired/i),
    ).toBeTruthy();
  });

  it("sends a reply through the wired callback and clears only its own draft", () => {
    const onReply = vi.fn();
    render(
      <ReplyThreadPanel origin={origin} replies={[]} onReply={onReply} />,
    );
    const textarea = screen.getByPlaceholderText("Reply to this thread…");
    const reply = screen.getByRole("button", { name: "Reply" });
    expect(reply.hasAttribute("disabled")).toBe(true);
    fireEvent.change(textarea, { target: { value: "  Confirmed — merge it. " } });
    expect(reply.hasAttribute("disabled")).toBe(false);
    fireEvent.click(reply);
    expect(onReply).toHaveBeenCalledWith("Confirmed — merge it.");
    expect(textarea.value).toBe("");
    expect(reply.hasAttribute("disabled")).toBe(true);
  });

  it("closes on Escape through the wired onClose and offers a visible close button", () => {
    const onClose = vi.fn();
    render(
      <ReplyThreadPanel origin={origin} replies={null} onClose={onClose} />,
    );
    fireEvent.keyDown(document.querySelector(".mm-cv-thread")!, {
      key: "Escape",
    });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Close thread" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("does not invent a close path when onClose is absent", () => {
    const { container } = render(
      <ReplyThreadPanel origin={origin} replies={null} />,
    );
    expect(
      screen.queryByRole("button", { name: "Close thread" }),
    ).toBeNull();
    fireEvent.keyDown(container.querySelector(".mm-cv-thread")!, {
      key: "Escape",
    });
    expect(container.querySelector(".mm-cv-thread")).toBeTruthy();
  });

  it("disables attachment preview honestly when it is not wired", () => {
    render(
      <ReplyThreadPanel
        origin={origin}
        replies={[]}
        attachment={{ name: "handoff.txt", kind: "Text" }}
      />,
    );
    const preview = screen.getByRole("button", { name: "Open preview" });
    expect(preview.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Preview is not wired/i)).toBeTruthy();
  });

  it("renders the honest zh-CN copy", () => {
    render(
      <ReplyThreadPanel
        locale="zh-CN"
        origin={origin}
        replies={replies}
        attachment={{ name: "reconnect-flow.png", kind: "Image" }}
      />,
    );
    expect(screen.getByText("回复串")).toBeTruthy();
    expect(screen.getByText("2 条回复")).toBeTruthy();
    expect(screen.getByText("查看原始消息 →")).toBeTruthy();
    // replies are projected here, so the not-projected note stays absent
    expect(
      screen.queryByText("此消息未投影回复。"),
    ).toBeNull();
    expect(screen.getByText("回复此串…")).toBeTruthy();
    expect(screen.getByText("＋ @ 提及")).toBeTruthy();
    expect(
      screen.getByText(/回复保留在这条消息上。提及成员可将其带入。/),
    ).toBeTruthy();
    expect(screen.getByText("附件")).toBeTruthy();
  });

  it("renders the honest zh-CN not-projected and no-send-path states", () => {
    render(
      <ReplyThreadPanel locale="zh-CN" origin={origin} replies={null} />,
    );
    expect(screen.getByText("此消息未投影回复。")).toBeTruthy();
    expect(
      screen.getByText(/此界面未接通发送通道/i),
    ).toBeTruthy();
  });

  it("ships no sample data: forbidden board literals never appear in output", () => {
    for (const node of [
      <ReplyThreadPanel key="null" origin={origin} replies={null} />,
      <ReplyThreadPanel key="full" origin={origin} replies={replies} />,
    ]) {
      const { container } = render(node);
      expect(container.textContent).not.toMatch(/Ryan|Meta-CEO|Secretary/);
      expect(container.textContent).not.toMatch(/\b2 min\b/);
      cleanup();
    }
  });
});
