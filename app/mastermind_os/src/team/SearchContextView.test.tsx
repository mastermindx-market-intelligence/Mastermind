// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SearchContextView,
  type SearchMessageResult,
} from "./SearchContextView";

afterEach(cleanup);

/** Fixtures are PROP DATA ONLY — every author/title below is passed in
 *  through the real results array; nothing is rendered from nowhere. */
const results: SearchMessageResult[] = [
  {
    id: "m1",
    conversationId: "c-alpha",
    conversationTitle: "Alpha room",
    author: "Engineering",
    text: "The route review landed",
    at: "2026-11-08T09:00:00Z",
    surrounding: {
      before: [
        {
          author: "Director C",
          text: "Morning check starts now",
          at: "2026-11-08T08:59:00Z",
        },
      ],
      after: [],
    },
  },
  {
    id: "m2",
    conversationId: "c-alpha",
    conversationTitle: "Alpha room",
    author: "Director C",
    text: "route review follow-up",
    at: "2026-11-08T10:00:00Z",
    surrounding: null,
  },
  {
    id: "m3",
    conversationId: "c-beta",
    conversationTitle: "Beta room",
    author: "Ops",
    text: "route review from ops",
    at: "2026-11-08T11:00:00Z",
    surrounding: {
      before: [],
      after: [
        {
          author: "Engineering",
          text: "Received, thank you",
          at: "2026-11-08T11:05:00Z",
        },
      ],
    },
  },
];

function resultRows(): HTMLElement[] {
  return Array.from(document.querySelectorAll(".mm-search-row"));
}

describe("SearchContextView", () => {
  it("groups results by conversation and computes the footer count from the real array", () => {
    render(
      <SearchContextView
        locale="en"
        query="route review"
        results={results}
        selectedId={null}
        onSelectResult={() => {}}
      />,
    );
    // One conversation header per distinct conversation, in array order.
    const headers = Array.from(
      document.querySelectorAll(".mm-search-conversation"),
    );
    expect(headers.map((node) => node.textContent)).toEqual([
      "Alpha room",
      "Beta room",
    ]);
    // Three message rows, all from the provided array.
    expect(resultRows()).toHaveLength(3);
    expect(screen.getByText("The route review landed")).toBeTruthy();
    expect(screen.getByText("route review from ops")).toBeTruthy();
    // The query display row shows the actual query.
    expect(
      document.querySelector(".mm-search-query-label")?.textContent,
    ).toBe("Query");
    expect(
      document.querySelector(".mm-search-query-text")?.textContent,
    ).toContain("route review");
    // Count computed from the REAL array (3 items), not a Paper sample.
    expect(screen.getByTestId("mm-search-count").textContent).toBe(
      "3 results in available history",
    );
  });

  it("marks the selected match and renders the surrounding window around it", () => {
    render(
      <SearchContextView
        locale="en"
        query="route review"
        results={results}
        selectedId="m1"
        onSelectResult={() => {}}
      />,
    );
    // The selected row is marked in the list.
    const marked = document.querySelector(
      '.mm-search-row[data-selected="true"]',
    );
    expect(marked?.textContent).toContain("The route review landed");
    // Context pane: conversation header + window with before/match/after.
    expect(
      document.querySelector(".mm-search-context-head h3")?.textContent,
    ).toBe("Alpha room");
    const match = document.querySelector('.mm-search-msg[data-match="true"]');
    expect(match?.textContent).toContain("The route review landed");
    expect(match?.textContent).toContain("Exact match");
    expect(match?.textContent).toContain("Engineering");
    // The before neighbor renders; the match is the only marked message.
    expect(screen.getByText("Morning check starts now")).toBeTruthy();
    expect(
      document.querySelectorAll('.mm-search-msg[data-match="true"]'),
    ).toHaveLength(1);
  });

  it("says when the surrounding window is not projected instead of faking neighbors", () => {
    render(
      <SearchContextView
        locale="en"
        query="q"
        results={[results[1]!]}
        selectedId="m2"
        onSelectResult={() => {}}
      />,
    );
    expect(
      screen.getByText(/only the exact match is shown/i),
    ).toBeTruthy();
    expect(
      document.querySelectorAll(".mm-search-msg"),
    ).toHaveLength(1);
  });

  it("moves focus through result rows with arrow keys (roving focus)", () => {
    render(
      <SearchContextView
        locale="en"
        query="route review"
        results={results}
        selectedId={null}
        onSelectResult={() => {}}
      />,
    );
    const [first, second, third] = resultRows();
    first!.focus();
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(second!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(third);
    // The last row does not wrap.
    fireEvent.keyDown(third!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(third);
    fireEvent.keyDown(third!, { key: "ArrowUp" });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(second!, { key: "Home" });
    expect(document.activeElement).toBe(first);
    // Only the roving anchor is tab-reachable.
    expect(first!.tabIndex).toBe(0);
    expect(second!.tabIndex).toBe(-1);
  });

  it("selects a result through onSelectResult", () => {
    const onSelectResult = vi.fn();
    render(
      <SearchContextView
        locale="en"
        query="route review"
        results={results}
        selectedId={null}
        onSelectResult={onSelectResult}
      />,
    );
    fireEvent.click(screen.getByText("route review follow-up"));
    expect(onSelectResult).toHaveBeenCalledTimes(1);
    expect(onSelectResult).toHaveBeenCalledWith("m2");
  });

  it("renders the honest not-projected state when no search read exists (null), never sample rows", () => {
    render(
      <SearchContextView
        locale="en"
        query="anything"
        results={null}
        selectedId={null}
        onSelectResult={() => {}}
      />,
    );
    expect(
      screen.getByText("Search source not projected in this build"),
    ).toBeTruthy();
    expect(
      screen.getByText(/No conversation-search read exists in this build/i),
    ).toBeTruthy();
    // No rows, and no count text at all (a count needs a real array).
    expect(resultRows()).toHaveLength(0);
    expect(screen.queryByTestId("mm-search-count")).toBeNull();
    expect(screen.queryByText(/results in available history/i)).toBeNull();
  });

  it("renders an honest zero-results state for a real empty read", () => {
    render(
      <SearchContextView
        locale="en"
        query="nothing matches"
        results={[]}
        selectedId={null}
        onSelectResult={() => {}}
      />,
    );
    expect(screen.getByText("No results")).toBeTruthy();
    expect(
      screen.getByText(/Nothing in the available history matches/i),
    ).toBeTruthy();
    expect(resultRows()).toHaveLength(0);
    // The count is the REAL zero, never the Paper sample "3".
    expect(screen.getByTestId("mm-search-count").textContent).toBe(
      "0 results in available history",
    );
  });

  it("regression: never renders Paper sample data — no hardcoded counts, no sample people", () => {
    for (const empty of [null, []] as (SearchMessageResult[] | null)[]) {
      const { unmount } = render(
        <SearchContextView
          locale="en"
          query=""
          results={empty}
          selectedId={null}
          onSelectResult={() => {}}
        />,
      );
      const text = document.body.textContent ?? "";
      expect(text).not.toContain("3 results");
      expect(text).not.toContain("Ryan");
      expect(text).not.toContain("Meta-CEO");
      expect(text).not.toContain("Secretary");
      expect(text).not.toContain("12 teammates");
      unmount();
    }
  });

  it("disables the open-conversation action with a reason when no open path exists", () => {
    render(
      <SearchContextView
        locale="en"
        query="q"
        results={results}
        selectedId="m1"
        onSelectResult={() => {}}
      />,
    );
    const open = screen.getByRole("button", { name: "Open conversation →" });
    expect(open.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/Opening a conversation is not wired in this build/i),
    ).toBeTruthy();
  });

  it("opens the conversation through the provided action with the exact conversation id", () => {
    const onOpenConversation = vi.fn();
    render(
      <SearchContextView
        locale="en"
        query="q"
        results={results}
        selectedId="m3"
        onSelectResult={() => {}}
        onOpenConversation={onOpenConversation}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Open conversation →" }),
    );
    expect(onOpenConversation).toHaveBeenCalledTimes(1);
    expect(onOpenConversation).toHaveBeenCalledWith("c-beta");
  });

  it("clears the selection on Escape only when a handler exists; without one it is a no-op, not a trap", () => {
    const onCloseSelection = vi.fn();
    const { unmount } = render(
      <SearchContextView
        locale="en"
        query="q"
        results={results}
        selectedId="m1"
        onSelectResult={() => {}}
        onCloseSelection={onCloseSelection}
      />,
    );
    fireEvent.keyDown(document.querySelector(".mm-search-surface")!, {
      key: "Escape",
    });
    expect(onCloseSelection).toHaveBeenCalledTimes(1);
    unmount();
    // No handler: Escape renders and does nothing (no crash, no trap).
    render(
      <SearchContextView
        locale="en"
        query="q"
        results={results}
        selectedId="m1"
        onSelectResult={() => {}}
      />,
    );
    fireEvent.keyDown(document.querySelector(".mm-search-surface")!, {
      key: "Escape",
    });
    // The selection pane is still rendered (no crash, nothing trapped).
    expect(
      document.querySelector(".mm-search-context-head h3")?.textContent,
    ).toBe("Alpha room");
  });

  it("renders the honest zh-CN copy", () => {
    const { unmount } = render(
      <SearchContextView
        locale="zh-CN"
        query="路由评审"
        results={results}
        selectedId="m1"
        onSelectResult={() => {}}
      />,
    );
    expect(screen.getByText("搜索")).toBeTruthy();
    expect(screen.getByText("搜索词")).toBeTruthy();
    expect(screen.getByTestId("mm-search-count").textContent).toBe(
      "可用历史中 3 条结果",
    );
    expect(screen.getByText("确切匹配")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "打开对话 →" }).hasAttribute(
        "disabled",
      ),
    ).toBe(true);
    unmount();
    render(
      <SearchContextView
        locale="zh-CN"
        query=""
        results={null}
        selectedId={null}
        onSelectResult={() => {}}
      />,
    );
    expect(screen.getByText("此构建未投影搜索来源")).toBeTruthy();
    // null ≠ empty: the zero-results copy belongs to a real empty read only.
    expect(screen.queryByText("无结果")).toBeNull();
  });
});
