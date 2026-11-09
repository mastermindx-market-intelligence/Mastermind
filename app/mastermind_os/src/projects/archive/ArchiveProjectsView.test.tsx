// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import type { ArchivedProject } from "./project-archive";
import { ArchiveProjectsView } from "./ArchiveProjectsView";
import type { ArchiveProjectCard, ArchiveProjectsViewProps } from "./ArchiveProjectsView";

afterEach(cleanup);

const row: ArchivedProject = {
  work_ref: "WS:ARCH-1",
  title: "Legacy billing",
  objective: "Close out the legacy billing workspace",
  archive: {
    schema: "agentos.workstream_archive.v1",
    state: "ARCHIVED",
    archived_on: "2026-09-14",
    archived_by: "ops-owner",
    reason: "Superseded by the new billing program",
  },
  source: {
    repository: "macro",
    commit: "a".repeat(40),
    path: "agentos/workstreams/WS-ARCH-1.md",
    content_sha256: "b".repeat(64),
  },
};
const second: ArchivedProject = { ...row, work_ref: "WS:ARCH-2", title: "Old onboarding" };

const live: ArchiveProjectCard = {
  workRef: "WS:LIVE-1",
  title: "Live program",
  nextAction: "Collect review evidence",
  state: "In review",
  archiveStatus: "NOT_DECLARED",
};
const unknownCard: ArchiveProjectCard = {
  workRef: "WS:LIVE-2", title: null, nextAction: null, state: null, archiveStatus: "UNKNOWN",
};

function props(overrides: Partial<ArchiveProjectsViewProps> = {}): ArchiveProjectsViewProps {
  return {
    scopeKey: "scope-1",
    locale: "en",
    mode: "projects",
    status: "ready",
    projects: [live],
    archived: [row],
    coverage: { checked: 1, supplied: 2, companyTotal: null },
    inspectedWorkRef: null,
    canRead: true,
    onRead: vi.fn(),
    onChangeMode: vi.fn(),
    onInspectArchive: vi.fn(),
    ...overrides,
  };
}

describe("ArchiveProjectsView", () => {
  it("renders a supplied project row with actual identity, unknown defaults and explicit archive status", () => {
    render(<ArchiveProjectsView {...props({ projects: [live, unknownCard] })} />);
    expect(screen.getByRole("heading", { name: "Projects" })).toBeTruthy();
    expect(screen.getByText("Live program")).toBeTruthy();
    expect(screen.getByText("WS:LIVE-1")).toBeTruthy();
    expect(screen.getByText("Collect review evidence")).toBeTruthy();
    expect(screen.getByText("In review")).toBeTruthy();
    expect(screen.getAllByText("WS:LIVE-2")).toHaveLength(2);
    expect(screen.getByText("Not declared")).toBeTruthy();
    expect(screen.getByText("Archive unknown")).toBeTruthy();
    expect(screen.getByText("No next action projected")).toBeTruthy();
    expect(screen.getByText("Unknown")).toBeTruthy();
    expect(document.body.textContent).toContain("does not indicate whether work is running");
    expect(document.body.textContent?.match(/Running/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Open project Live program" })).toBeNull();
  });

  it("switches to archived mode and passes the exact workRef to the parent's project navigation", () => {
    const onChangeMode = vi.fn();
    const onOpenProject = vi.fn();
    render(<ArchiveProjectsView {...props({ onChangeMode, onOpenProject })} />);
    fireEvent.click(screen.getByRole("button", { name: "Archived projects" }));
    expect(onChangeMode).toHaveBeenCalledWith("archived");
    expect(onChangeMode).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Open project Live program" }));
    expect(onOpenProject).toHaveBeenCalledWith("WS:LIVE-1");
    expect(onOpenProject).toHaveBeenCalledTimes(1);
  });

  it("reads archive evidence from the header action only when enabled", () => {
    const onRead = vi.fn();
    const view = render(<ArchiveProjectsView {...props({ onRead, status: "unread", mode: "archived" })} />);
    const read = screen.getByRole("button", { name: "Refresh archived projects" }) as HTMLButtonElement;
    expect(read.disabled).toBe(false);
    fireEvent.click(read);
    expect(onRead).toHaveBeenCalledTimes(1);
    view.rerender(<ArchiveProjectsView {...props({ onRead, status: "loading", mode: "archived" })} />);
    expect((screen.getByRole("button", { name: "Refresh archived projects" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Reading archive evidence…")).toBeTruthy();
  });

  it("shows the loaded count, coverage and company-total unknown without disabling the empty archived entry", () => {
    const onChangeMode = vi.fn();
    const view = render(<ArchiveProjectsView {...props({ onChangeMode })} />);
    const entry = screen.getByRole("button", { name: "Archived projects" }) as HTMLButtonElement;
    expect(entry.disabled).toBe(false);
    fireEvent.click(entry);
    expect(onChangeMode).toHaveBeenCalledWith("archived");
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", archived: [], coverage: null })} />);
    expect(screen.getByRole("heading", { name: "Archived projects" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back to projects" })).toBeTruthy();
    expect(screen.getByText("No archived projects are declared in the checked sample.")).toBeTruthy();
    expect(screen.getByText("0 archived projects returned · company total unknown")).toBeTruthy();
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", archived: [], coverage: null, status: "unread" })} />);
    expect(screen.getByText("Archive evidence has not been read yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Archived projects" })).toBeNull();
  });

  it("opens the exact archived record read-only and returns to the list with the search retained", () => {
    const onInspectArchive = vi.fn();
    const view = render(<ArchiveProjectsView {...props({ mode: "archived", archived: [row, second], onInspectArchive })} />);
    expect(screen.getByText("2 archived projects returned · 1 checked of 2 supplied records · company total unknown")).toBeTruthy();
    expect(screen.getByText("Legacy billing")).toBeTruthy();
    expect(screen.getByText("Old onboarding")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Find an archived project"), { target: { value: "legacy" } });
    expect(screen.queryByText("Old onboarding")).toBeNull();
    expect(screen.getByText("2026-09-14")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open read-only Legacy billing" }));
    expect(onInspectArchive).toHaveBeenCalledWith("WS:ARCH-1");
    expect(onInspectArchive).toHaveBeenCalledTimes(1);
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", archived: [row, second], onInspectArchive, inspectedWorkRef: "WS:ARCH-1" })} />);
    expect(screen.getByText("Close out the legacy billing workspace")).toBeTruthy();
    expect(screen.getByText("Archived")).toBeTruthy();
    expect(screen.getByText("ops-owner")).toBeTruthy();
    expect(screen.getByText("Superseded by the new billing program")).toBeTruthy();
    const source = screen.getByText("Repository").closest("details") as HTMLDetailsElement;
    expect(source.open).toBe(false);
    expect(source.textContent).toContain("macro");
    expect(source.textContent).toContain("a".repeat(40));
    expect(source.textContent).toContain("agentos/workstreams/WS-ARCH-1.md");
    expect(source.textContent).toContain("b".repeat(64));
    fireEvent.click(screen.getByRole("button", { name: "Back to archived list" }));
    expect(onInspectArchive).toHaveBeenCalledWith(null);
    expect(onInspectArchive).toHaveBeenCalledTimes(2);
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", archived: [row, second], onInspectArchive })} />);
    expect((screen.getByLabelText("Find an archived project") as HTMLInputElement).value).toBe("legacy");
    expect(screen.getByText("Legacy billing")).toBeTruthy();
    expect(screen.queryByText("Old onboarding")).toBeNull();
  });

  it("scopes search to the supplied loaded view and reports no-match truthfully", () => {
    render(<ArchiveProjectsView {...props({ mode: "archived" })} />);
    fireEvent.change(screen.getByLabelText("Find an archived project"), { target: { value: "nomatch" } });
    expect(screen.queryByText("Legacy billing")).toBeNull();
    expect(screen.getByText("No supplied archived projects match this search.")).toBeTruthy();
    expect(screen.getByText("Search filters the loaded view only.")).toBeTruthy();
    expect(screen.getByText("1 archived projects returned · 1 checked of 2 supplied records · company total unknown")).toBeTruthy();
  });

  it("hides supplied data and disables the read action without a grant", () => {
    render(<ArchiveProjectsView {...props({ canRead: false })} />);
    expect(document.body.textContent).not.toContain("Live program");
    expect(document.body.textContent).not.toContain("WS:LIVE-1");
    expect(screen.queryByRole("button", { name: "Refresh archived projects" })).toBeNull();
    expect(screen.getByRole("button", {name:"Archived projects"})).toBeTruthy();
    cleanup();
    render(<ArchiveProjectsView {...props({ canRead: false, mode: "archived" })} />);
    expect(document.body.textContent).not.toContain("Legacy billing");
    expect(document.body.textContent).not.toContain("WS:ARCH-1");
    expect(screen.getByText("Open archive records in an authorized current project context.")).toBeTruthy();
    expect((screen.getByRole("button",{name:"Refresh archived projects"}) as HTMLButtonElement).disabled).toBe(true);
  });

  it("reports unread and unavailable archive states truthfully", () => {
    const view = render(<ArchiveProjectsView {...props({ mode: "archived", status: "unread" })} />);
    expect(screen.getByText("Archive evidence has not been read yet.")).toBeTruthy();
    expect(screen.queryByText("Legacy billing")).toBeNull();
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", status: "unavailable" })} />);
    expect(screen.getByText("The archive source is unavailable.")).toBeTruthy();
    expect(screen.queryByText("Legacy billing")).toBeNull();
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", status: "ready", inspectedWorkRef: "WS:GONE" })} />);
    expect(screen.getByText("The selected archived record is not in the loaded view.")).toBeTruthy();
  });

  it("passes the bounded back callback with null for a missing inspected record", () => {
    const onInspectArchive = vi.fn();
    render(<ArchiveProjectsView {...props({ mode: "archived", inspectedWorkRef: "WS:GONE", onInspectArchive })} />);
    fireEvent.click(screen.getByRole("button", { name: "Back to archived list" }));
    expect(onInspectArchive).toHaveBeenCalledWith(null);
    expect(onInspectArchive).toHaveBeenCalledTimes(1);
  });

  it("resets local search state when the parent changes the scope epoch", () => {
    const view = render(<ArchiveProjectsView {...props({ mode: "archived", archived: [row, second] })} />);
    fireEvent.change(screen.getByLabelText("Find an archived project"), { target: { value: "legacy" } });
    expect(screen.queryByText("Old onboarding")).toBeNull();
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived", archived: [row, second], scopeKey: "scope-2" })} />);
    expect((screen.getByLabelText("Find an archived project") as HTMLInputElement).value).toBe("");
    expect(screen.getByText("Old onboarding")).toBeTruthy();
  });

  it("localizes all copy in zh-CN and keeps the authored archive date", () => {
    const view = render(<ArchiveProjectsView {...props({ locale: "zh-CN", mode: "archived" })} />);
    expect(document.querySelector(".archive-projects")?.getAttribute("lang")).toBe("zh-CN");
    expect(screen.getByRole("heading", { name: "归档项目" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "返回项目" })).toBeTruthy();
    expect(screen.getByLabelText("查找归档项目")).toBeTruthy();
    expect(screen.getByText("已返回 1 个归档项目 · 已检查 1 条，共提供 2 条记录 · 公司总数未知")).toBeTruthy();
    expect(screen.getByText("归档日期")).toBeTruthy();
    expect(screen.getByText("2026-09-14")).toBeTruthy();
    expect(screen.getByText("归档人")).toBeTruthy();
    expect(screen.getByText("原因")).toBeTruthy();
    expect(screen.getByText("只读打开")).toBeTruthy();
    view.rerender(<ArchiveProjectsView {...props({ mode: "archived" })} />);
    expect(document.querySelector(".archive-projects")?.getAttribute("lang")).toBe("en");
    expect(screen.getByRole("heading", { name: "Archived projects" })).toBeTruthy();
    expect(screen.queryByText("归档项目")).toBeNull();
  });
});


function NavigableArchive({ status = "ready", rows = [row, { ...second, title: row.title }] }: {
  status?: ArchiveProjectsViewProps["status"]; rows?: ArchivedProject[];
}) {
  const [mode, setMode] = useState<"projects" | "archived">("projects");
  const [inspected, setInspected] = useState<string | null>(null);
  return <ArchiveProjectsView {...props({ mode, status, archived: rows, inspectedWorkRef: inspected,
    onChangeMode: setMode, onInspectArchive: setInspected })} />;
}

it("preserves the caller-owned New project control only in the normal Projects header", () => {
  const create = vi.fn(), read = vi.fn();
  const shared = props({ newProjectControl: <button type="button" onClick={create}>New project</button>, onRead: read });
  const view = render(<ArchiveProjectsView {...shared} />);
  fireEvent.click(screen.getByRole("button", { name: "New project" }));
  expect(create).toHaveBeenCalledTimes(1); expect(read).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Refresh archived projects" })).toBeNull();
  expect(screen.getByRole("button", { name: "Archived projects" })).toBeTruthy();
  view.rerender(<ArchiveProjectsView {...shared} mode="archived" locale="zh-CN" />);
  expect(screen.queryByRole("button", { name: "New project" })).toBeNull();
  expect(screen.getByRole("button", { name: "刷新归档项目" })).toBeTruthy();
});

it("hands focus to explicit mode/inspector headings and restores the exact row Open button on Back", () => {
  render(<NavigableArchive />);
  const entry = screen.getByRole("button", { name: "Archived projects" });
  entry.focus(); fireEvent.click(entry);
  expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Archived projects", level: 1 }));
  const search = screen.getByRole("searchbox", { name: "Find an archived project" });
  fireEvent.change(search, { target: { value: "Legacy" } });
  const original = screen.getAllByRole("button", { name: "Open read-only Legacy billing" })[1]!;
  original.focus(); fireEvent.click(original);
  expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Legacy billing", level: 2 }));
  const back = screen.getByRole("button", { name: "Back to archived list" });
  back.focus(); fireEvent.click(back);
  expect(document.activeElement).toBe(screen.getAllByRole("button", { name: "Open read-only Legacy billing" })[1]);
  expect((screen.getByRole("searchbox", { name: "Find an archived project" }) as HTMLInputElement).value).toBe("Legacy");
  const projects = screen.getByRole("button", { name: "Back to projects" });
  projects.focus(); fireEvent.click(projects);
  expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Projects", level: 1 }));
});

it("does not move focus on passive loading or fresh source props", () => {
  const view = render(<NavigableArchive />);
  fireEvent.click(screen.getByRole("button", { name: "Archived projects" }));
  const search = screen.getByRole("searchbox", { name: "Find an archived project" });
  search.focus(); fireEvent.change(search, { target: { value: "Legacy" } });
  view.rerender(<NavigableArchive status="loading" />);
  expect(document.activeElement).toBe(search);
  view.rerender(<NavigableArchive status="ready" rows={[structuredClone(row)]} />);
  expect(document.activeElement).toBe(search);
  expect((search as HTMLInputElement).value).toBe("Legacy");
});

it("uses a visual reason preview while preserving the full exact reason in the inspector", () => {
  const reason = "Exact long archive explanation. ".repeat(60);
  const long = { ...row, archive: { ...row.archive, reason } };
  render(<NavigableArchive rows={[long]} />);
  fireEvent.click(screen.getByRole("button", { name: "Archived projects" }));
  const preview = document.querySelector(".archive-reason-preview");
  expect(preview?.textContent).toBe(reason);
  fireEvent.click(screen.getByRole("button", { name: "Open read-only Legacy billing" }));
  expect(document.querySelector(".archive-facts dd:last-child")?.textContent).toBe(reason);
  expect(document.querySelector(".archive-reason-preview")).toBeNull();
});

it.each(["en","zh-CN"] as const)("distinguishes current catalogue pending/unavailable from qualified empty independently of archive permission: %s",locale=>{
 const messages={pending:locale==="en"?"Reading projects…":"正在读取项目…",unavailable:locale==="en"?"Projects are unavailable right now. The current project list could not be confirmed.":"项目暂不可用；当前项目列表尚未确认。",ready:locale==="en"?"No projects were supplied by the current read.":"当前读取未提供项目。"};
 for(const state of ["pending","unavailable","ready"] as const){
  const read=vi.fn();const v=render(<ArchiveProjectsView {...props({locale,currentProjectsState:state,projects:[],canRead:false,onRead:read})}/>);
  expect(screen.getByText(messages[state])).toBeTruthy();
  if(state!=="ready")expect(screen.queryByText(messages.ready)).toBeNull();
  if(state!=="ready")expect(document.body.textContent).not.toMatch(/0 projects|公司.*0/);
  else expect(screen.getByRole("status").textContent).toBe(locale==="en"?"0 projects in this view":"此视图中有 0 个项目");
  expect(read).not.toHaveBeenCalled();v.unmount();
 }
});
it("shows a qualified current row without granting an archive read",()=>{
 const read=vi.fn(),open=vi.fn();render(<ArchiveProjectsView {...props({currentProjectsState:"ready",canRead:false,onRead:read,onOpenProject:open})}/>);
 expect(screen.getByText("Live program")).toBeTruthy();expect(screen.queryByRole("button",{name:"Refresh archived projects"})).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:"Open project Live program"}));expect(open).toHaveBeenCalledWith("WS:LIVE-1");expect(read).not.toHaveBeenCalled();
});


it("composes the current catalogue as a counted table with honest owner and recorded state", () => {
 render(<ArchiveProjectsView {...props({currentProjectsState:"ready",projects:[live,unknownCard],canRead:false,onOpenProject:vi.fn()})}/>);
 expect(screen.getByRole('heading',{level:1,name:'Projects'})).toBeTruthy();
 expect(screen.getByText('Choose a project to view its plan, sources and conversations.')).toBeTruthy();
 expect(screen.getByRole('status').textContent).toBe('2 projects in this view');
 const table=within(screen.getByRole('table',{name:'Current projects'}));
 expect(table.getAllByRole('columnheader').map(n=>n.textContent)).toEqual(['Project','Next step','Owner','Recorded state','Open project']);
 expect(table.getAllByText('Not supplied')).toHaveLength(2);
 expect(table.getByText('In review')).toBeTruthy();
 expect(table.getByText('Unknown')).toBeTruthy();
 expect(screen.queryByText('Continue working')).toBeNull();
 expect(screen.queryByRole('button',{name:'Refresh archived projects'})).toBeNull();
 expect(screen.getByRole('button',{name:'Archived projects'}).hasAttribute('disabled')).toBe(false);
 expect((screen.getByText('Archive status comes only from checked source records. It does not indicate whether work is running.').closest('details') as HTMLDetailsElement).open).toBe(false);
});
it("reports filtered loaded counts, clears the filter, and keeps the exact explicit project target", () => {
 const open=vi.fn();render(<ArchiveProjectsView {...props({currentProjectsState:'ready',projects:[live,unknownCard],onOpenProject:open})}/>);
 fireEvent.change(screen.getByRole('searchbox',{name:'Find a project'}),{target:{value:'LIVE-2'}});
 expect(screen.getByRole('status').textContent).toBe('1 of 2 projects match this search');
 fireEvent.click(screen.getByRole('button',{name:'Open project WS:LIVE-2'}));expect(open).toHaveBeenCalledExactlyOnceWith('WS:LIVE-2');
 fireEvent.change(screen.getByRole('searchbox'),{target:{value:'absent'}});
 expect(screen.getByRole('status').textContent).toBe('0 of 2 projects match this search');
 expect(screen.getByText('No supplied projects match this search.')).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Clear search'}));
 expect(screen.getByRole('searchbox')).toHaveProperty('value','');
 expect(document.activeElement).toBe(screen.getByRole('searchbox'));
 expect(screen.getByRole('status').textContent).toBe('2 projects in this view');
});
it("withholds stale rows and counts while pending or unavailable, then distinguishes qualified empty", () => {
 const v=render(<ArchiveProjectsView {...props({currentProjectsState:'pending',projects:[live]})}/>);
 expect(screen.queryByText(live.title!)).toBeNull();expect(screen.queryByRole('table')).toBeNull();
 expect(screen.queryByText(/0 projects/)).toBeNull();expect(screen.getByText('Reading projects…')).toBeTruthy();
 v.rerender(<ArchiveProjectsView {...props({currentProjectsState:'unavailable',projects:[live]})}/>);
 expect(screen.queryByText(live.title!)).toBeNull();expect(screen.queryByRole('table')).toBeNull();
 expect(screen.getByText('Projects are unavailable right now. The current project list could not be confirmed.')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Archived projects'})).toBeTruthy();
 v.rerender(<ArchiveProjectsView {...props({currentProjectsState:'ready',projects:[]})}/>);
 expect(screen.getByRole('status').textContent).toBe('0 projects in this view');
 expect(screen.getByText('No projects were supplied by the current read.')).toBeTruthy();
});
it("uses a bounded initial list and reveals only the actual remaining supplied rows", () => {
 const cards=Array.from({length:11},(_,i)=>({...live,workRef:`WS:REAL-${i}`,title:`Supplied ${i}`}));
 render(<ArchiveProjectsView {...props({currentProjectsState:'ready',projects:cards})}/>);
 expect(screen.getAllByRole('row')).toHaveLength(9);
 fireEvent.click(screen.getByRole('button',{name:'See all 11 projects'}));
 expect(screen.getAllByRole('row')).toHaveLength(12);
 fireEvent.click(screen.getByRole('button',{name:'Show fewer projects'}));expect(screen.getAllByRole('row')).toHaveLength(9);
});
it("localizes current-list hierarchy and filter feedback without rewriting authored source content", () => {
 render(<ArchiveProjectsView {...props({locale:'zh-CN',currentProjectsState:'ready',projects:[live],onOpenProject:vi.fn()})}/>);
 expect(screen.getByText('选择项目，查看计划、来源和对话。')).toBeTruthy();
 expect(screen.getByRole('table',{name:'当前项目'})).toBeTruthy();
 expect(screen.getByRole('columnheader',{name:'负责人'})).toBeTruthy();expect(screen.getByText('未提供')).toBeTruthy();
 expect(screen.getByRole('columnheader',{name:'记录状态'})).toBeTruthy();expect(screen.getByText('In review')).toBeTruthy();
 fireEvent.change(screen.getByRole('searchbox',{name:'查找项目'}),{target:{value:'unmatched'}});
 expect(screen.getByRole('status').textContent).toBe('匹配 0 个项目，共 1 个');
 expect(screen.getByRole('button',{name:'清除搜索'})).toBeTruthy();
 expect(screen.queryByText('Owner')).toBeNull();expect(screen.queryByText('Recorded state')).toBeNull();
});
