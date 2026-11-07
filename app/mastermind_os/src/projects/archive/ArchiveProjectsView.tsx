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
  return <li className="archive-row">
    <div className="archive-identity">
      <h2>{label}</h2>
      <p className="archive-ref">{card.workRef}</p>
    </div>
    <p className="archive-field"><span>{t("Next step")}</span>{card.nextAction || t("No next action projected")}</p>
    <p className="archive-field"><span>{t("State")}</span>{card.state || t("Unknown")}</p>
    <p className="archive-chip" data-archive={card.archiveStatus}>
      <span>{t("Archive status")}</span>
      {card.archiveStatus === "UNKNOWN" ? t("Archive unknown") : t("Not declared")}
    </p>
    <div className="archive-actions">
      {onOpenProject && card.openable !== false && <button type="button" aria-label={`${t("Open project")} ${label}`}
        onClick={() => onOpenProject(card.workRef)}>{t("Open project")}</button>}
    </div>
  </li>;
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
  locale, mode, status, projects, archived, coverage, inspectedWorkRef,
  canRead, onRead, onChangeMode, onInspectArchive, onOpenProject, newProjectControl,
}: ArchiveProjectsViewProps) {
  const zh = locale === "zh-CN";
  const t: Translate = value => (zh ? COPY_ZH[value] ?? value : value);
  const [query, setQuery] = useState("");
  const [projectQuery, setProjectQuery] = useState("");
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
  const term = query.trim().toLocaleLowerCase();
  const matches = archived.filter(row =>
    !term || `${row.title ?? ""}\n${row.work_ref}`.toLocaleLowerCase().includes(term));
  const inspected = inspectedWorkRef === null
    ? null
    : archived.find(row => row.work_ref === inspectedWorkRef) ?? null;
  const statusLine = !canRead
    ? t("Open archive records in an authorized current project context.")
    : status === "unread" ? t("Archive evidence has not been read yet.")
    : status === "loading" ? t("Reading archive evidence…")
    : status === "unavailable" ? t("The archive source is unavailable.")
    : null;
  return <section className="archive-projects" lang={locale}
    aria-label={mode === "archived" ? t("Archived projects") : t("Projects")}>
    {mode === "archived"
      ? <header className="archive-head">
        <h1 ref={heading} tabIndex={-1}>{t("Archived projects")}</h1>
        <div className="archive-header-actions"><button type="button" onClick={() => changeMode("projects")}>{t("Back to projects")}</button>
          <button type="button" disabled={!canRead || status === "loading"} onClick={onRead}>{t("Refresh archived projects")}</button></div>
      </header>
      : <header className="archive-head">
        <h1 ref={heading} tabIndex={-1}>{t("Projects")}</h1>
        <div className="archive-header-actions">{newProjectControl}
          <button type="button" disabled={!canRead || status === "loading"} onClick={onRead}>
            {t("Refresh archived projects")}
          </button>
        </div>
      </header>}
    {mode === "projects" && <p className="archive-note">
      {t("Archive status comes only from checked source records. It does not indicate whether work is running.")}
    </p>}
    {statusLine && <p className="archive-status" role="status">{statusLine}</p>}
    {mode === "projects" ? <>
      {canRead && <div className="archive-search"><label htmlFor={projectSearchId}>{t("Find a project")}</label>
        <input id={projectSearchId} type="search" value={projectQuery} placeholder={t("Find a project")} onChange={event => setProjectQuery(event.target.value)} /></div>}
      {!canRead ? null
        : projects.length === 0
          ? <p className="archive-empty">{t("No project records are shown in this view.")}</p>
          : visibleProjects.length === 0 ? <p className="archive-empty">{t("No supplied projects match this search.")}</p>
          : <ul className="archive-list">
            {visibleProjects.map(card =>
              <ProjectRow key={card.workRef} card={card} t={t} onOpenProject={onOpenProject} />)}
          </ul>}
      {/* Navigation only: the entry never claims data and stays enabled even
          when the checked sample declares no archived projects. */}
      <div className="archive-footer">
        <button type="button" onClick={() => changeMode("archived")}>{t("Archived projects")}</button>
      </div>
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
