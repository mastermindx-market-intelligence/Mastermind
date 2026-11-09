// @vitest-environment jsdom
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CodeWorkspace } from "./CodeWorkspace";
import type { T3ProjectionRead, T3ThreadProjection } from "./t3-thread-projection";
afterEach(cleanup);

function thread(extra: Partial<T3ThreadProjection> = {}): T3ThreadProjection {
  return {
    schema: "mastermind.t3_thread_projection.v1", threadId: "abc123", environment: "m2studio",
    title: "Fix fabric launch refusal", runState: "running",
    lastActivity: "2026-11-09T00:00:00Z", prLink: "https://github.com/acme/repo/pull/12",
    repository: "acme/repo", companyManaged: true,
    ...extra,
  };
}
const available = (threads: T3ThreadProjection[]): T3ProjectionRead => ({
  kind: "AVAILABLE", list: { schema: "mastermind.t3_thread_projection_list.v1", threads },
});

describe("CodeWorkspace (TD04)", () => {
  it("deep-links the exact native T3 thread with id, environment and run state — never an embedded editor", () => {
    render(<CodeWorkspace projection={available([
      thread(),
      thread({ threadId: "idle-9", environment: "chatgpt1", title: null, runState: "idle", lastActivity: null, prLink: null, repository: null, companyManaged: false }),
    ])} />);
    const open = screen.getAllByRole("link", { name: "Open in T3 Code ↗" });
    expect(open[0]!.getAttribute("href")).toBe("https://app.t3.codes/threads/m2studio/abc123");
    expect(open[1]!.getAttribute("href")).toBe("https://app.t3.codes/threads/chatgpt1/idle-9");
    expect(open.every(node => node.getAttribute("target") === "_blank")).toBe(true);
    const first = document.querySelector(".mm-code-thread")!;
    expect(first.textContent).toContain("m2studio");
    expect(first.textContent).toContain("abc123");
    expect(first.textContent).toContain("Running");
    expect(first.textContent).toContain("Last activity");
    expect(first.textContent).toContain("2026-11-09T00:00:00Z");
    expect(first.textContent).toContain("acme/repo");
    const pr = screen.getByRole("link", { name: "https://github.com/acme/repo/pull/12" });
    expect(pr.getAttribute("href")).toBe("https://github.com/acme/repo/pull/12");
    const second = document.querySelectorAll(".mm-code-thread")[1]!;
    expect(second.textContent).toContain("T3 thread idle-9"); // no title → honest id label
    expect(second.textContent).toContain("Not observed"); // no last activity
    expect(second.textContent).toContain("Not company managed");
    expect(screen.queryByRole("textbox")).toBeNull(); // no editor, no terminal, ever
    expect(screen.getByText(/No provider keys live in this app/i)).toBeTruthy();
  });

  it("marks each observed run state without inventing one", () => {
    render(<CodeWorkspace projection={available([
      thread({ threadId: "a", runState: "running" }),
      thread({ threadId: "b", runState: "idle" }),
      thread({ threadId: "c", runState: "blocked" }),
      thread({ threadId: "d", runState: "unknown" }),
    ])} />);
    for (const label of ["Running", "Idle", "Blocked", "Unknown"]) {
      // Each state renders in the chip and the facts list — both must agree.
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(2);
    }
  });

  it("shows the honest not-projected state with its source reason while no projection is connected", () => {
    render(<CodeWorkspace projection={{ kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_NOT_CONNECTED" }} />);
    expect(screen.getByText("Code threads are not projected yet")).toBeTruthy();
    expect(screen.getByText(/projection source is not connected, so no thread state is shown or inferred/i)).toBeTruthy();
    expect(screen.getByText("T3_PROJECTION_SOURCE_NOT_CONNECTED")).toBeTruthy();
    expect(screen.getByText(/Open T3 Code directly/i)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Open in T3 Code ↗" })).toBeNull();
  });

  it("reads from the provided host facade when no projection is supplied", () => {
    render(<CodeWorkspace host={{ t3ThreadProjection: { read: () => ({ schema: "mastermind.t3_thread_projection_list.v1", threads: [] }) } }} />);
    expect(screen.getByRole("list", { name: "T3 coding threads" })).toBeTruthy();
    expect(screen.queryByText(/not projected yet/i)).toBeNull();
  });

  it("renders the honest zh-CN copy with the same deep links", () => {
    render(<CodeWorkspace projection={available([thread()])} locale="zh-CN" />);
    expect(screen.getByRole("heading", { name: "T3 Code" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "在 T3 Code 中打开 ↗" }).getAttribute("href")).toBe("https://app.t3.codes/threads/m2studio/abc123");
    expect(screen.getAllByText("运行中").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("拉取请求")).toBeTruthy();
  });
});
