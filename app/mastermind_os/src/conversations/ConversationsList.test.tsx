// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationsList } from "./ConversationsList";
import type { ConversationListModel, ConversationListProps } from "./conversation-list-contract";

afterEach(cleanup);
function model(): ConversationListModel {
  return { schema: "mastermind.conversations_list_projection.v1", authGeneration: 2,
    recentState: "CURRENT", projectsState: "CURRENT", historyCoverage: "NOT_ENUMERATED",
    recent: [{ key: "current-one", title: "Original topic", projectTitle: "Original project", observedAt: "2026-11-05T12:00:00Z", unsentDraft: true,
      locator: { kind: "current", workRef: "WS:ONE", rootJobId: "JOB-001", jobId: "JOB-001", attemptId: "ATT-001", selectionRef: "selection", sourceRef: "window", sourceRevision: "revision", epoch: "epoch", authGeneration: 2 } }],
    projects: Array.from({ length: 10 }, (_, i) => ({ key: `project-${i}`, title: `Project ${i}`, nextAction: i === 9 ? "Exact authored topic" : null,
      locator: { kind: "project", workRef: `WS:P${i}`, sourceRef: "catalogue", sourceRevision: "revision", authGeneration: 2 } })),
    sources: [{ owner: "CURRENT_WINDOW", state: "CURRENT", observedAt: "2026-11-05T12:00:00Z", revision: "private-current-revision" },
      { owner: "PROJECT_CATALOGUE", state: "CURRENT", observedAt: null, revision: "private-project-revision" }] };
}
function props(): ConversationListProps {
  return { model: model(), query: "", showAllProjects: false, onQueryChange: vi.fn(), onShowAllProjects: vi.fn(),
    onOpenCurrent: vi.fn(() => true), onOpenProject: vi.fn(() => true), onOpenMetaCeo: vi.fn(), onSourcesAndAccess: vi.fn() };
}
it("keeps a genuine conversation distinct from eight source-ordered project shortcuts, with no automatic owner calls", () => {
  const p = props(); render(<ConversationsList {...p} />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Conversations");
  expect(screen.getAllByRole("article")).toHaveLength(9);
  expect(screen.queryByText("Project 8")).toBeNull();
  expect(screen.getByText("Unsent draft")).toBeTruthy(); expect(screen.queryByText(/Draft saved/)).toBeNull();
  expect(screen.queryByRole("button", { name: "New conversation" })).toBeNull();
  expect(screen.getByRole("heading", { level: 2, name: "Current conversation" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Recent" })).toBeNull();
  const projectRow = screen.getByRole("button", { name: "Open project Project 0" }).closest("article")!;
  expect(projectRow.textContent).not.toContain("WS:P0");
  expect(screen.getByText("WS:P0").closest("details")).toBeTruthy();
  expect(p.onOpenCurrent).not.toHaveBeenCalled(); expect(p.onOpenProject).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Open conversation: Original topic" }));
  expect(p.onOpenCurrent).toHaveBeenCalledWith(p.model.recent[0].locator);
  fireEvent.click(screen.getByRole("button", { name: "Open project Project 0" }));
  expect(p.onOpenProject).toHaveBeenCalledWith(p.model.projects[0].locator);
  fireEvent.click(screen.getByRole("button", { name: "Show all 10 matching projects" })); expect(p.onShowAllProjects).toHaveBeenCalledOnce();
});
it("keeps titleless project rows distinguishable using their exact source reference", () => {
  const p = props(), first = { ...p.model.projects[0], title: null };
  render(<ConversationsList {...p} model={{ ...p.model, projects: [first] }} />);
  expect(screen.getByRole("heading", { level: 3, name: "WS:P0" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Open project WS:P0" })).toBeTruthy();
});
it("filters only supplied metadata and preserves the controlled query and source order", () => {
  const p = props(); const view = render(<ConversationsList {...p} query="exact authored" />);
  expect(screen.getAllByRole("article")).toHaveLength(1); expect(screen.getByText("Project 9")).toBeTruthy();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "new query" } }); expect(p.onQueryChange).toHaveBeenCalledWith("new query");
  view.rerender(<ConversationsList {...p} query="no supplied match" />);
  expect(screen.getByRole("status").textContent).toBe("No matches in the available records.");
});
it("masks inconsistent retained rows and private revisions after access withdrawal instead of claiming empty history", () => {
  const p = props(); render(<ConversationsList {...p} model={{ ...p.model, recentState: "WITHHELD", projectsState: "WITHHELD" }} />);
  expect(screen.queryAllByRole("article")).toHaveLength(0);
  expect(screen.queryByText("Original topic")).toBeNull(); expect(screen.queryByText("private-current-revision")).toBeNull();
  expect(screen.queryByText("private-project-revision")).toBeNull();
  expect(screen.getByText("Conversation access is unavailable here.")).toBeTruthy();
  expect(screen.queryByText("No current conversation is listed here.")).toBeNull();
});
it.each(["STALE", "PENDING", "UNAVAILABLE", "UNASSOCIATED"] as const)("keeps %s source distinct from a qualified empty catalogue", state => {
  const p = props(); const view = render(<ConversationsList {...p} model={{ ...p.model, recentState: state, projectsState: state }} />);
  expect(screen.queryAllByRole("article")).toHaveLength(0); expect(screen.queryByText("No projects are listed in this view.")).toBeNull();
  view.rerender(<ConversationsList {...p} model={{ ...p.model, recent: [], projects: [] }} />);
  expect(screen.getByText("No projects are listed in this view.")).toBeTruthy();
});
it("refuses changed locators and actual owner refusal without presenting an Open as success", () => {
  const p = { ...props(), onOpenCurrent: vi.fn(() => false) }; render(<ConversationsList {...p} />);
  fireEvent.click(screen.getByRole("button", { name: "Open conversation: Original topic" }));
  expect(screen.getByRole("status").textContent).toContain("no longer current");
});
it("restores explicit Back focus to the real row, falling back to search when its source is gone", () => {
  const p = props(); const view = render(<ConversationsList {...p} restoreFocus={{ key: "project-1", request: 1 }} />);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open project Project 1" }));
  view.rerender(<ConversationsList {...p} query="Original topic" restoreFocus={{ key: "project-1", request: 2 }} />);
  expect(document.activeElement).toBe(screen.getByRole("searchbox"));
});
it('restores explicit new-entry Back to its real trigger without automatic entry or query loss',()=>{
  const p={...props(),query:'Original topic',onNewConversation:vi.fn()};
  const view=render(<ConversationsList {...p}/>);
  expect(p.onNewConversation).not.toHaveBeenCalled();
  view.rerender(<ConversationsList {...p} restoreFocus={{key:'new-conversation',request:1}}/>);
  expect(document.activeElement).toBe(screen.getByRole('button',{name:'New conversation'}));
  expect(screen.getByRole('searchbox')).toHaveProperty('value','Original topic');
  expect(p.onNewConversation).not.toHaveBeenCalled();
});
it.each(["dark", "light"] as const)("preserves Chinese actions, clock meaning, and partial-source scope in %s", theme => {
  const p = props(); render(<ConversationsList {...p} locale="zh-CN" theme={theme} />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("对话");
  expect(screen.getByText("未发送草稿")).toBeTruthy(); expect(screen.getByText("此列表不完整。项目中可能还有其他对话。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "打开项目 Project 0" })); expect(p.onOpenProject).toHaveBeenCalledOnce();
  const source = screen.getByText("列表来源").parentElement!;
  expect(within(source).getByText(/尚未枚举/)).toBeTruthy();
});
