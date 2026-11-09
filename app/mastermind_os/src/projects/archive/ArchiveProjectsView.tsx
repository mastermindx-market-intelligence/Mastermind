import { useId, useLayoutEffect, useRef, useState, type ReactNode, type Ref } from "react";
import type { ArchivedProject } from "./project-archive";
import "./archive-projects.css";

export interface ArchiveProjectCard {
  workRef: string;
  title: string | null;
  nextAction: string | null;
  state: string | null;
  archiveStatus: "NOT_DECLARED" | "UNKNOWN";
  /** Actual parent-owned read-navigation capability for this exact row. */
  openable?: boolean;
}

export interface ArchiveProjectsViewProps {
  scopeKey: string;
  locale: "en" | "zh-CN";
  mode: "projects" | "archived";
  status: "unread" | "loading" | "ready" | "unavailable";
  projects: readonly ArchiveProjectCard[];
  /** Separate current catalogue outcome. Archive permission is not catalogue authority. */
  currentProjectsState?: "pending" | "ready" | "unavailable";
  archived: readonly ArchivedProject[];
  coverage: { checked: number; supplied: number; companyTotal: null } | null;
  inspectedWorkRef: string | null;
  canRead: boolean;
  onRead: () => void;
  onChangeMode: (mode: "projects" | "archived") => void;
  onInspectArchive: (workRef: string | null) => void;
  onOpenProject?: (workRef: string) => void;
  /** Existing caller-owned action, including its own command/grant guards. */
  newProjectControl?: ReactNode;
}

// Presentation copy only. Titles, objectives, actors, reasons, authored archive
// dates, work refs, commits, paths and digests stay verbatim from the qualified
// projection. No row, count or company total is invented in this view.
const COPY_ZH: Record<string, string> = {
  "Projects": "项目",
  "Choose a project to view its plan, sources and conversations.": "选择项目，查看计划、来源和对话。",
  "All projects": "全部项目",
  "Current projects": "当前项目",
  "Project": "项目",
  "Owner": "负责人",
  "Recorded state": "记录状态",
  "Clear search": "清除搜索",
  "Show fewer projects": "收起项目",
  "Source details": "来源详情",
  "About this list": "关于此列表",
  "Names, next steps and recorded states come from the current project read. An owner is not supplied by this source.": "名称、下一步和记录状态来自当前项目读取；此来源未提供负责人。",
  "Refresh Projects to try the current list again. Archived projects uses a separate read.": "请刷新项目后重试当前列表。归档项目使用独立的读取权限。",
  "The list is still being read. No project count is confirmed yet.": "正在读取列表，项目数量尚未确认。",
  "Reading projects…": "正在读取项目…",
  "Projects are unavailable right now. The current project list could not be confirmed.": "项目暂不可用；当前项目列表尚未确认。",
  "No projects were supplied by the current read.": "当前读取未提供项目。",
  "Archived": "已归档",
  "Find a project": "查找项目",
  "No supplied projects match this search.": "没有已提供的项目匹配此搜索。",
  "The remaining supplied records have not been checked.": "其余已提供记录尚未检查。",
  "Date precision": "日期精度",
  "Day": "日",
  "Refresh archived projects": "刷新归档项目",
  "Archived projects": "归档项目",
  "Back to projects": "返回项目",
  "Back to archived list": "返回归档列表",
  "Find an archived project": "查找归档项目",
  "Open project": "打开项目",
  "Open read-only": "只读打开",
  "Next step": "下一步",
  "State": "状态",
  "Unknown": "未知",
  "No next action projected": "暂无下一步",
  "Not supplied": "未提供",
  "Archive status": "归档状态",
  "Not declared": "未声明",
  "Archive unknown": "归档未知",
  "Archive status comes only from checked source records. It does not indicate whether work is running.":
    "归档状态仅来自已检查的来源记录，并不表示工作是否正在运行。",
  "No project records are shown in this view.": "此视图未显示项目记录。",
  "Archive evidence has not been read yet.": "尚未读取归档证据。",
  "Reading archive evidence…": "正在读取归档证据…",
  "The archive source is unavailable.": "归档来源不可用。",
  "Open archive records in an authorized current project context.":
    "请在已授权且最新的项目上下文中打开归档记录。",
  "No archived projects are declared in the checked sample.": "检查样本中未声明任何归档项目。",
  "No supplied archived projects match this search.": "没有已提供的归档项目匹配此搜索。",
  "Search filters the loaded view only.": "搜索仅筛选已加载的视图。",
  "The selected archived record is not in the loaded view.": "所选归档记录不在已加载的视图中。",
  "Archived record (read-only)": "归档记录（只读）",
  "Objective": "目标",
  "Archived on": "归档日期",
  "Archived by": "归档人",
  "Reason": "原因",
  "Source": "来源",
  "Repository": "仓库",
  "Commit": "提交",
  "Path": "路径",
  "Content SHA-256": "内容 SHA-256",
  "company total unknown": "公司总数未知",
};

type Coverage = ArchiveProjectsViewProps["coverage"];
type Translate = (value: string) => string;

function loadedLine(zh: boolean, count: number): string {
  return zh ? `已返回 ${count} 个归档项目` : `${count} archived projects returned`;
}

function coverageClause(zh: boolean, coverage: NonNullable<Coverage>): string {
  return zh
    ? `已检查 ${coverage.checked} 条，共提供 ${coverage.supplied} 条记录`
    : `${coverage.checked} checked of ${coverage.supplied} supplied records`;
}

function ProjectRow({ card, t, onOpenProject }: {
  card: ArchiveProjectCard; t: Translate; onOpenProject?: (workRef: string) => void;
}) {
  const label = card.title || card.workRef;
  return <tr>
    <th scope="row" className="projects-list-identity">
      <h2>{label}</h2>
      <p className="archive-ref">{card.workRef}</p>
      <details className="projects-row-source">
        <summary>{t("Source details")}</summary>
        <p>{t("Archive status")}: <span>{card.archiveStatus === "UNKNOWN" ? t("Archive unknown") : t("Not declared")}</span></p>
      </details>
    </th>
    <td data-label={t("Next step")}>{card.nextAction || t("No next action projected")}</td>
    <td data-label={t("Owner")} className="projects-owner">{t("Not supplied")}</td>
    <td data-label={t("Recorded state")}><span className="projects-recorded-state">{card.state || t("Unknown")}</span></td>
    <td className="projects-open">
      {onOpenProject && card.openable !== false && <button type="button" aria-label={`${t("Open project")} ${label}`}
        onClick={() => onOpenProject(card.workRef)}>{t("Open project")}<span aria-hidden="true"> →</span></button>}
    </td>
  </tr>;
}

function ArchiveRow({ row, t, onInspect, openRef }: {
  row: ArchivedProject; t: Translate; onInspect: () => void; openRef: Ref<HTMLButtonElement>;
}) {
  const label = row.title || row.work_ref;
  return <li className="archive-row">
    <div className="archive-identity">
      <h2>{label}</h2>
      <p className="archive-ref">{row.work_ref}</p>
    </div>
    <p className="archive-field"><span>{t("Archived on")}</span><time dateTime={row.archive.archived_on}>{row.archive.archived_on}</time></p>
    <p className="archive-field"><span>{t("Archived by")}</span>{row.archive.archived_by}</p>
    <p className="archive-field"><span>{t("Reason")}</span><span className="archive-reason-preview">{row.archive.reason}</span></p>
    <div className="archive-actions">
      <button ref={openRef} type="button" aria-label={`${t("Open read-only")} ${label}`} onClick={onInspect}>
        {t("Open read-only")}
      </button>
    </div>
  </li>;
}

/** Read-only record: actual authored fields only, source provenance folded shut. */
function Inspector({ found, workRef, t, onBack, headingRef }: {
  found: ArchivedProject | null; workRef: string; t: Translate; onBack: () => void; headingRef: Ref<HTMLHeadingElement>;
}) {
  return <article className="archive-inspector" aria-label={t("Archived record (read-only)")}>
    <div className="archive-actions">
      <button type="button" onClick={onBack}>{t("Back to archived list")}</button>
    </div>
    {found ? <>
      <div className="archive-identity">
        <h2 ref={headingRef} tabIndex={-1}>{found.title || found.work_ref}</h2>
        <p className="archive-ref">{found.work_ref}</p>
      </div>
      <p className="archive-field"><span>{t("Objective")}</span>{found.objective || t("Not supplied")}</p>
      <dl className="archive-facts">
        <dt>{t("State")}</dt><dd>{t("Archived")}</dd>
        <dt>{t("Archived on")}</dt><dd><time dateTime={found.archive.archived_on}>{found.archive.archived_on}</time></dd>
        <dt>{t("Archived by")}</dt><dd>{found.archive.archived_by}</dd>
        <dt>{t("Reason")}</dt><dd>{found.archive.reason}</dd>
      </dl>
      <details className="archive-source">
        <summary>{t("Source")}</summary>
        <dl>
          <dt>{t("Date precision")}</dt><dd>{t("Day")}</dd>
          <dt>{t("Repository")}</dt><dd>{found.source.repository}</dd>
          <dt>{t("Commit")}</dt><dd>{found.source.commit}</dd>
          <dt>{t("Path")}</dt><dd>{found.source.path}</dd>
          <dt>{t("Content SHA-256")}</dt><dd>{found.source.content_sha256}</dd>
        </dl>
      </details>
    </> : <>
      <h2 ref={headingRef} tabIndex={-1}>{t("Archived record (read-only)")}</h2>
      <p className="archive-ref">{workRef}</p>
      <p className="archive-empty">{t("The selected archived record is not in the loaded view.")}</p>
    </>}
  </article>;
}

function ArchiveProjectsScoped({
  locale, mode, status, projects, currentProjectsState, archived, coverage, inspectedWorkRef,
  canRead, onRead, onChangeMode, onInspectArchive, onOpenProject, newProjectControl,
}: ArchiveProjectsViewProps) {
  const zh = locale === "zh-CN";
  const t: Translate = value => (zh ? COPY_ZH[value] ?? value : value);
  const [query, setQuery] = useState("");
  const [projectQuery, setProjectQuery] = useState("");
  const [showAllProjects, setShowAllProjects] = useState(false);
  const projectSearch = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const inspectorHeading = useRef<HTMLHeadingElement>(null);
  const rowButtons = useRef(new Map<string, HTMLButtonElement>());
  type FocusIntent = { kind: "mode"; mode: "projects" | "archived" } | { kind: "inspector" | "row"; workRef: string };
  const [focusIntent, setFocusIntent] = useState<FocusIntent | null>(null);
  // Only an explicit navigation handler creates an intent. Resolve or discard
  // it in that render; a later asynchronous source update cannot revive it.
  useLayoutEffect(() => {
    if (!focusIntent) return;
    let target: HTMLElement | null = null;
    if (focusIntent.kind === "mode" && mode === focusIntent.mode) target = heading.current;
    if (focusIntent.kind === "inspector" && mode === "archived" && canRead && inspectedWorkRef === focusIntent.workRef)
      target = inspectorHeading.current;
    if (focusIntent.kind === "row" && mode === "archived" && canRead && inspectedWorkRef === null)
      target = rowButtons.current.get(focusIntent.workRef) ?? heading.current;
    target?.focus();
    setFocusIntent(null);
  }, [focusIntent, mode, inspectedWorkRef, canRead]);
  const changeMode = (next: "projects" | "archived") => {
    setFocusIntent({ kind: "mode", mode: next }); onChangeMode(next);
  };
  const inspectArchive = (workRef: string) => {
    setFocusIntent({ kind: "inspector", workRef }); onInspectArchive(workRef);
  };
  const backToList = () => {
    if (inspectedWorkRef !== null) setFocusIntent({ kind: "row", workRef: inspectedWorkRef });
    onInspectArchive(null);
  };
  const searchId = useId(), projectSearchId = useId();
  const projectTerm = projectQuery.trim().toLocaleLowerCase();
  const visibleProjects = projects.filter(row => !projectTerm || `${row.title ?? ""}\n${row.workRef}`.toLocaleLowerCase().includes(projectTerm));
  const listedProjects = showAllProjects ? visibleProjects : visibleProjects.slice(0, 8);
  const projectCount = projectTerm
    ? zh ? `匹配 ${visibleProjects.length} 个项目，共 ${projects.length} 个` : `${visibleProjects.length} of ${projects.length} projects match this search`
    : zh ? `此视图中有 ${projects.length} 个项目` : `${projects.length} ${projects.length === 1 ? "project" : "projects"} in this view`;
  const term = query.trim().toLocaleLowerCase();
  const matches = archived.filter(row =>
    !term || `${row.title ?? ""}\n${row.work_ref}`.toLocaleLowerCase().includes(term));
  const inspected = inspectedWorkRef === null
    ? null
    : archived.find(row => row.work_ref === inspectedWorkRef) ?? null;
  const projectsReady = currentProjectsState === undefined ? canRead : currentProjectsState === "ready";
  const statusLine = mode === "projects"
    ? currentProjectsState === "pending" ? t("Reading projects…")
      : currentProjectsState === "unavailable" ? t("Projects are unavailable right now. The current project list could not be confirmed.") : null
    : !canRead
    ? t("Open archive records in an authorized current project context.")
    : status === "unread" ? t("Archive evidence has not been read yet.")
    : status === "loading" ? t("Reading archive evidence…")
    : status === "unavailable" ? t("The archive source is unavailable.")
    : null;
  return <section className="archive-projects" data-view={mode} lang={locale}
    aria-label={mode === "archived" ? t("Archived projects") : t("Projects")}>
    {mode === "archived"
      ? <header className="archive-head">
        <h1 ref={heading} tabIndex={-1}>{t("Archived projects")}</h1>
        <div className="archive-header-actions"><button type="button" onClick={() => changeMode("projects")}>{t("Back to projects")}</button>
          <button type="button" disabled={!canRead || status === "loading"} onClick={onRead}>{t("Refresh archived projects")}</button></div>
      </header>
      : <header className="archive-head projects-head">
        <div className="projects-heading"><h1 ref={heading} tabIndex={-1}>{t("Projects")}</h1>
          <p>{t("Choose a project to view its plan, sources and conversations.")}</p></div>
        <div className="archive-header-actions">{newProjectControl}</div>
      </header>}
    {statusLine && <p className="archive-status" role="status">{statusLine}</p>}
    {mode === "projects" ? <>
      <div className="projects-toolbar">
        <nav aria-label={t("Projects")} className="projects-list-modes">
          <span className="projects-current-mode" aria-current="page">{t("All projects")}</span>
          <button type="button" onClick={() => changeMode("archived")}>{t("Archived projects")}</button>
        </nav>
        {projectsReady && <div className="archive-search projects-search">
          <label className="projects-visually-hidden" htmlFor={projectSearchId}>{t("Find a project")}</label>
          <input ref={projectSearch} id={projectSearchId} type="search" value={projectQuery} placeholder={t("Find a project")}
            onChange={event => {setProjectQuery(event.target.value);setShowAllProjects(false);}} />
          {projectQuery && <button type="button" onClick={() => {setProjectQuery("");setShowAllProjects(false);projectSearch.current?.focus();}}>{t("Clear search")}</button>}
        </div>}
      </div>
      {!projectsReady ? <div className="projects-list-state">
        {currentProjectsState === "pending" ? <>
          <p className="archive-note">{t("The list is still being read. No project count is confirmed yet.")}</p>
          <div className="projects-skeleton" aria-hidden="true">{[0,1,2].map(i=><div key={i}><span/><span/><span/></div>)}</div>
        </> : <p className="archive-note">{t("Refresh Projects to try the current list again. Archived projects uses a separate read.")}</p>}
      </div> : <>
        <p className="projects-list-count" role="status" aria-live="polite">{projectCount}</p>
        {projects.length === 0
          ? <p className="archive-empty">{t(currentProjectsState === "ready"
            ? "No projects were supplied by the current read." : "No project records are shown in this view.")}</p>
          : visibleProjects.length === 0 ? <p className="archive-empty">{t("No supplied projects match this search.")}</p>
          : <table className="projects-table" aria-label={t("Current projects")}>
            <thead><tr><th scope="col">{t("Project")}</th><th scope="col">{t("Next step")}</th>
              <th scope="col">{t("Owner")}</th><th scope="col">{t("Recorded state")}</th>
              <th scope="col"><span className="projects-visually-hidden">{t("Open project")}</span></th></tr></thead>
            <tbody>{listedProjects.map(card => <ProjectRow key={card.workRef} card={card} t={t} onOpenProject={onOpenProject} />)}</tbody>
          </table>}
        {visibleProjects.length > 8 && <div className="projects-list-more"><button type="button" onClick={() => setShowAllProjects(!showAllProjects)}>
          {showAllProjects ? t("Show fewer projects") : zh ? `查看全部 ${visibleProjects.length} 个项目` : `See all ${visibleProjects.length} projects`}
        </button></div>}
        <details className="projects-list-source"><summary>{t("About this list")}</summary>
          <p>{t("Names, next steps and recorded states come from the current project read. An owner is not supplied by this source.")}</p>
          <p>{t("Archive status comes only from checked source records. It does not indicate whether work is running.")}</p>
        </details>
      </>}
    </> : <>
      {!canRead ? null : <>
        <div className="archive-search">
          <label htmlFor={searchId}>{t("Find an archived project")}</label>
          <input id={searchId} type="search" value={query} placeholder={t("Find an archived project")}
            onChange={event => setQuery(event.target.value)} />
        </div>
        {status === "ready" && <p className="archive-count">
          {loadedLine(zh, archived.length)}
          {coverage ? ` · ${coverageClause(zh, coverage)}` : ""}
          {" · "}{t("company total unknown")}
        </p>}
        {status === "ready" && coverage && coverage.checked < coverage.supplied && <p className="archive-note">{t("The remaining supplied records have not been checked.")}</p>}
        {inspectedWorkRef !== null
          ? <Inspector found={inspected} workRef={inspectedWorkRef} t={t} headingRef={inspectorHeading}
            onBack={backToList} />
          : status === "ready" ? (
            archived.length === 0
              ? <p className="archive-empty">{t("No archived projects are declared in the checked sample.")}</p>
              : matches.length === 0
                ? <>
                  <p className="archive-empty">{t("No supplied archived projects match this search.")}</p>
                  <p className="archive-note">{t("Search filters the loaded view only.")}</p>
                </>
                : <ul className="archive-list">
                  {matches.map(row =>
                    <ArchiveRow key={row.work_ref} row={row} t={t}
                      openRef={node => { if (node) rowButtons.current.set(row.work_ref, node); else rowButtons.current.delete(row.work_ref); }}
                      onInspect={() => inspectArchive(row.work_ref)} />)}
                </ul>
          ) : null}
      </>}
    </>}
  </section>;
}

/** Pure read-only presentation over qualified props. The parent owns data
 * acquisition, auth, scope epochs and navigation; a scopeKey change remounts
 * this view and resets its local search state, while passive prop updates
 * never move focus. */
export function ArchiveProjectsView(props: ArchiveProjectsViewProps) {
  return <ArchiveProjectsScoped key={props.scopeKey} {...props} />;
}
