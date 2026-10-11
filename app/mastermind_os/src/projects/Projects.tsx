import { useId, useState } from "react";
import { normalizeSelection } from "../mission";
import type { MissionSelection, ProgramCard } from "../mission";
import type { OfficeProjection, SourceClaim } from "../meta-ceo/projection";
import "./projects.css";

export interface ProjectsProps {
  programs: OfficeProjection["programs"];
  /** Supplied by the existing selection owner; no first-row or recency inference. */
  selectedProject?: MissionSelection | null;
  /** Read navigation only. The parent must preserve current/history semantics. */
  onNavigateMission?: (selection: MissionSelection, mode: "current" | "history") => void;
}

function resolvedSelection(card: ProgramCard): MissionSelection | null {
  if (card.rootState !== "RESOLVED" || card.rootCandidates.length !== 1 || card.rootCandidates[0] !== card.rootJobId) return null;
  return normalizeSelection({ workRef: card.workRef, rootJobId: card.rootJobId });
}

function rootLabel(card: ProgramCard): string {
  if (resolvedSelection(card)) return `Mission ${card.rootJobId}`;
  if (card.rootState === "UNKNOWN" || !card.rootJobId && card.rootState !== "CONFLICT")
    return "Root unknown; no mission was guessed";
  return `Root conflict: ${card.rootCandidates.join(", ") || "multiple responsibility rows"}`;
}

function ProjectCard({ card, history, featured, onNavigateMission }: {
  card: ProgramCard; history: boolean; featured?: boolean;
  onNavigateMission?: ProjectsProps["onNavigateMission"];
}) {
  const title = card.title || card.workRef;
  const selection = resolvedSelection(card);
  const action = history ? `Inspect retained history for ${title}` : `Open project ${title}`;
  return <article className={featured ? "projects-featured" : "projects-row"}>
    <div className="projects-identity">
      {featured && <p className="projects-eyebrow">Selected project</p>}
      <h2>{title}</h2>
      <p className="projects-ref">{card.workRef}</p>
      <p className="projects-root">{rootLabel(card)}</p>
    </div>
    <p className="projects-next"><span>Next step</span>{card.nextAction || "No next action projected"}</p>
    <p className="projects-owner"><span>Owner</span>Not supplied</p>
    <div className="projects-status"><span>{history ? "Retained state" : "Owner state"}</span><p>{card.state || "Unknown"}</p></div>
    <div className="projects-open">
      {selection && onNavigateMission && <button type="button" aria-label={action}
        onClick={() => onNavigateMission(selection, history ? "history" : "current")}>
        {history ? "Inspect retained history" : "Open project"}<span aria-hidden="true"> →</span>
      </button>}
    </div>
    {featured && <div className="projects-art" aria-hidden="true" />}
  </article>;
}

function Collection({ cards, history, selectedProject, onNavigateMission }: {
  cards: ProgramCard[]; history: boolean;
  selectedProject: ProjectsProps["selectedProject"];
  onNavigateMission: ProjectsProps["onNavigateMission"];
}) {
  const [query, setQuery] = useState("");
  const inputId = useId();
  const term = query.trim().toLocaleLowerCase();
  const visible = cards.filter(card => !term || `${card.title ?? ""}\n${card.workRef}`.toLocaleLowerCase().includes(term));
  const featured = visible.find(card => resolvedSelection(card) && card.workRef === selectedProject?.workRef && card.rootJobId === selectedProject.rootJobId);
  const rows = visible.filter(card => card !== featured);
  return <>
    <div className="projects-tools">
      <p className="projects-count">{cards.length} {cards.length === 1 ? "project" : "projects"} supplied</p>
      <div className="projects-search"><label htmlFor={inputId}>Find a supplied project</label>
        <input id={inputId} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find a project" />
      </div>
    </div>
    {history && <p className="projects-history">Retained history. These facts do not establish current project state.</p>}
    {term && <p className="projects-matches" role="status">{visible.length} {visible.length === 1 ? "match" : "matches"} in {cards.length} supplied projects</p>}
    {cards.length === 0 ? <p className="projects-empty">No projects were supplied. This does not establish zero company work.</p> :
      visible.length === 0 ? <p className="projects-empty">No supplied projects match this search.</p> : <>
        {featured && <section aria-label="Selected project"><ProjectCard card={featured} featured history={history} onNavigateMission={onNavigateMission} /></section>}
        {rows.length > 0 && <section aria-label={featured ? "More supplied projects" : "Supplied projects"} className="projects-list">
          {featured && <h2 className="projects-list-heading">More projects</h2>}
          {rows.map(card => <ProjectCard key={card.workRef} card={card} history={history} onNavigateMission={onNavigateMission} />)}
        </section>}
      </>}
  </>;
}

function Provenance({ source }: { source: SourceClaim }) {
  if (source.state === "WITHHELD") return null;
  return <details className="projects-provenance"><summary>Project source</summary>
    <dl><dt>Owner</dt><dd>{source.owner}</dd><dt>Reference</dt><dd>{source.ref || "Not supplied"}</dd>
      <dt>Revision</dt><dd>{source.revision || "Not supplied"}</dd>
      <dt>{source.observed_at_kind === "LOCAL_ACQUISITION" ? "Locally acquired" : "Observed"}</dt><dd>{source.observed_at || "Not supplied"}</dd>
      <dt>Coverage</dt><dd>{source.coverage}</dd></dl>
  </details>;
}

/** Pure view over the qualified projection. The existing host owns all reads. */
export function Projects({ programs, selectedProject, onNavigateMission }: ProjectsProps) {
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
  return <section className="atelier-projects" aria-label="Projects">
    <header className="projects-heading"><h1>Your projects, in perspective.</h1>
      <p>Direction, conversations and delivery, together.</p></header>
    <div className="projects-source-state"><span className="projects-state" data-state={source.state}>{source.state}</span>
      <p>Only the supplied scope is represented.</p></div>
    {cards ? <Collection key={JSON.stringify([source.owner, source.ref, source.revision])} cards={cards} history={source.state === "STALE"}
      selectedProject={selectedProject} onNavigateMission={onNavigateMission} /> :
      <div className="projects-empty"><p>Project facts cannot be displayed from this source.</p><p>{reason || `SOURCE_${source.state}`}</p></div>}
    <Provenance source={source} />
  </section>;
}
