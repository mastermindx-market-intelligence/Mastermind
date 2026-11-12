import { useId, useState } from "react";
import { normalizeSelection } from "../mission";
import { validProjectPlanSelection } from "../planning/project-plan";
import type { MissionSelection, ProgramCard } from "../mission";
import type { OfficeProjection, SourceClaim } from "../meta-ceo/projection";
import "./projects.css";

type Locale = "en" | "zh-CN";
const copy = (locale: Locale) => (en: string, zh: string) => locale === "zh-CN" ? zh : en;

export interface ProjectsProps {
  locale?: Locale;
  programs: OfficeProjection["programs"];
  /** Supplied by the existing selection owner; no first-row or recency inference. */
  selectedProject?: MissionSelection | null;
  /** Read navigation only. The parent must preserve current/history semantics. */
  /** Current catalogue read navigation; no Mission root or command is implied. */
  onOpenProject?: (workRef: string) => void;
  onNavigateMission?: (selection: MissionSelection, mode: "current" | "history") => void;
}

function resolvedSelection(card: ProgramCard): MissionSelection | null {
  if (card.rootState !== "RESOLVED" || card.rootCandidates.length !== 1 || card.rootCandidates[0] !== card.rootJobId) return null;
  return normalizeSelection({ workRef: card.workRef, rootJobId: card.rootJobId });
}

function rootLabel(card: ProgramCard, locale: Locale): string {
  const t = copy(locale);
  if (resolvedSelection(card)) return t(`Mission ${card.rootJobId}`, `任务 ${card.rootJobId}`);
  if (card.rootState === "UNKNOWN" || !card.rootJobId && card.rootState !== "CONFLICT")
    return t("Root unknown; no mission was guessed", "根任务未知；未推断任何任务");
  return t(`Root conflict: ${card.rootCandidates.join(", ") || "multiple responsibility rows"}`, `根任务冲突：${card.rootCandidates.join("、") || "多个职责记录"}`);
}

function ProjectCard({ card, history, featured, onNavigateMission, onOpenProject, locale }: {
  card: ProgramCard; history: boolean; featured?: boolean; locale: Locale;
  onNavigateMission?: ProjectsProps["onNavigateMission"];
  onOpenProject?: ProjectsProps["onOpenProject"];
}) {
  const t = copy(locale);
  const title = card.title || card.workRef;
  const selection = resolvedSelection(card);
  const action = history ? t(`Inspect retained history for ${title}`, `查看${title}的保留记录`) : t(`Open project ${title}`, `打开项目${title}`);
  return <article className={featured ? "projects-featured" : "projects-row"}>
    <div className="projects-identity">
      {featured && <p className="projects-eyebrow">{t("Selected project", "所选项目")}</p>}
      <h2>{title}</h2>
      <p className="projects-ref">{card.workRef}</p>
      <p className="projects-root">{rootLabel(card, locale)}</p>
    </div>
    <p className="projects-next"><span>{t("Next step", "下一步")}</span>{card.nextActionWithheld ? t("Next action withheld", "下一步内容未显示") : card.nextAction || t("No next action projected", "尚未提供下一步")}</p>
    <p className="projects-owner"><span>{t("Owner", "负责人")}</span>{t("Not supplied", "未提供")}</p>
    <div className="projects-status"><span>{history ? t("Retained state", "保留状态") : t("Owner state", "来源状态")}</span><p>{card.state || t("Unknown", "未知")}</p></div>
    <div className="projects-open">
      {!history && onOpenProject && !selection && validProjectPlanSelection({work_ref: card.workRef}) ? <button type="button" aria-label={action}
        onClick={() => onOpenProject(card.workRef)}>{t("Open project", "打开项目")}<span aria-hidden="true"> →</span></button> : null}
      {selection && onNavigateMission && <button type="button" aria-label={action}
        onClick={() => onNavigateMission(selection, history ? "history" : "current")}>
        {history ? t("Inspect retained history", "查看保留记录") : t("Open project", "打开项目")}<span aria-hidden="true"> →</span>
      </button>}
    </div>
    {featured && <div className="projects-art" aria-hidden="true" />}
  </article>;
}

function Collection({ cards, history, selectedProject, onNavigateMission, onOpenProject, locale }: {
  cards: ProgramCard[]; history: boolean; locale: Locale;
  selectedProject: ProjectsProps["selectedProject"];
  onNavigateMission: ProjectsProps["onNavigateMission"];
  onOpenProject: ProjectsProps["onOpenProject"];
}) {
  const t = copy(locale);
  const [query, setQuery] = useState("");
  const inputId = useId();
  const term = query.trim().toLocaleLowerCase();
  // Search the displayed root label, never hidden identity fields.
  const visible = cards.filter(card => !term || `${card.title ?? ""}\n${card.workRef}\n${rootLabel(card, locale)}`.toLocaleLowerCase().includes(term));
  const featured = visible.find(card => resolvedSelection(card) && card.workRef === selectedProject?.workRef && card.rootJobId === selectedProject.rootJobId);
  const rows = visible.filter(card => card !== featured);
  return <>
    <div className="projects-tools">
      <p className="projects-count">{t(`${cards.length} ${cards.length === 1 ? "project" : "projects"} supplied`, `已提供 ${cards.length} 个项目`)}</p>
      <div className="projects-search"><label htmlFor={inputId}>{t("Find a supplied project", "查找已提供的项目")}</label>
        <input id={inputId} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={t("Find a project", "查找项目")} />
      </div>
    </div>
    {history && <p className="projects-history">{t("Retained history. These facts do not establish current project state.", "保留记录。这些事实不代表项目当前状态。")}</p>}
    {term && <p className="projects-matches" role="status">{t(`${visible.length} ${visible.length === 1 ? "match" : "matches"} in ${cards.length} supplied projects`, `在 ${cards.length} 个已提供的项目中找到 ${visible.length} 个匹配`)}</p>}
    {cards.length === 0 ? <p className="projects-empty">{t("No projects were supplied. This does not establish zero company work.", "尚未提供项目。这不代表公司没有工作。")}</p> :
      visible.length === 0 ? <p className="projects-empty">{t("No supplied projects match this search.", "没有已提供的项目符合此搜索。")}</p> : <>
        {featured && <section aria-label={t("Selected project", "所选项目")}><ProjectCard card={featured} featured history={history} onNavigateMission={onNavigateMission} onOpenProject={onOpenProject} locale={locale} /></section>}
        {rows.length > 0 && <section aria-label={featured ? t("More supplied projects", "其他已提供的项目") : t("Supplied projects", "已提供的项目")} className="projects-list">
          {featured && <h2 className="projects-list-heading">{t("More projects", "更多项目")}</h2>}
          {rows.map(card => <ProjectCard key={card.workRef} card={card} history={history} onNavigateMission={onNavigateMission} onOpenProject={onOpenProject} locale={locale} />)}
        </section>}
      </>}
  </>;
}

function Provenance({ source, locale }: { source: SourceClaim; locale: Locale }) {
  const t = copy(locale);
  if (source.state === "WITHHELD") return null;
  return <details className="projects-provenance"><summary>{t("Project source", "项目来源")}</summary>
    <dl><dt>{t("Owner", "所有者")}</dt><dd>{source.owner}</dd><dt>{t("Reference", "引用")}</dt><dd>{source.ref || t("Not supplied", "未提供")}</dd>
      <dt>{t("Revision", "修订")}</dt><dd>{source.revision || t("Not supplied", "未提供")}</dd>
      <dt>{source.observed_at_kind === "LOCAL_ACQUISITION" ? t("Locally acquired", "本地获取时间") : t("Observed", "观测时间")}</dt><dd>{source.observed_at || t("Not supplied", "未提供")}</dd>
      <dt>{t("Coverage", "覆盖范围")}</dt><dd>{source.coverage}</dd></dl>
  </details>;
}

/** Pure view over the qualified projection. The existing host owns all reads. */
export function Projects({ programs, selectedProject, onNavigateMission, onOpenProject, locale = "en" }: ProjectsProps) {
  const t = copy(locale);
  let source = programs.source, reason = programs.reason;
  let cards = programs.value?.programs ?? null;
  if (source.state === "CURRENT" || source.state === "STALE") {
    if (!programs.value || programs.value.state === "UNAVAILABLE") {
      source = { ...source, state: "UNAVAILABLE" };
      reason = programs.value?.reason || "SOURCE_VALUE_MISSING";
    } else if (source.state === "CURRENT" && (!source.ref || !source.revision || !source.observed_at)) {
      source = { ...source, state: "UNKNOWN" }; reason = "PROVENANCE_INCOMPLETE";
    } else if (new Set(cards!.map(card => card.workRef)).size !== cards!.length) {
      source = { ...source, state: "UNKNOWN" }; reason = "DUPLICATE_WORK_REF";
    }
  }
  if (source.state !== "CURRENT" && source.state !== "STALE") cards = null;
  return <section className="atelier-projects" aria-label={t("Projects", "项目")}>
    <header className="projects-heading"><h1>{t("Your projects, in perspective.", "纵览你的项目。")}</h1>
      <p>{t("Direction, conversations and delivery, together.", "目标、对话与交付，汇集于此。")}</p></header>
    <div className="projects-source-state"><span className="projects-state" data-state={source.state}>{source.state}</span>
      <p>{t("Only the supplied scope is represented.", "仅显示来源提供的范围。")}</p></div>
    {cards ? <Collection key={JSON.stringify([source.owner, source.ref, source.revision])} cards={cards} history={source.state === "STALE"}
      selectedProject={selectedProject} onNavigateMission={onNavigateMission} onOpenProject={source.state === "CURRENT" ? onOpenProject : undefined} locale={locale} /> :
      <div className="projects-empty"><p>{t("Project facts cannot be displayed from this source.", "此来源暂时无法提供项目详情。")}</p><p>{reason || `SOURCE_${source.state}`}</p></div>}
    <Provenance source={source} locale={locale} />
  </section>;
}
