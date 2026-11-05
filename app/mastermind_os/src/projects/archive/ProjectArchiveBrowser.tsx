import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { normalizeSelection, type MissionSelection } from "../../mission";
import type { OfficeProjection } from "../../meta-ceo/projection";
import type { ProjectArchiveRead } from "./project-archive";
import { acceptArchivePage, nextArchiveCursor, type ArchiveCursor, type AvailableArchive } from "./project-archive-continuation";
import { ArchiveProjectsView } from "./ArchiveProjectsView";
import "./archive-browser.css";

export interface ProjectArchiveBrowserProps {
  /** Actual existing workspace/auth identity. A reset key, never a grant. */
  scopeKey: string;
  programs: OfficeProjection["programs"];
  read?: (request: { signal: AbortSignal }) => Promise<ProjectArchiveRead>;
  readPage?: (request: ArchiveCursor & { signal: AbortSignal }) => Promise<ProjectArchiveRead>;
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  /** Existing qualified catalogue read navigation; no Mission root is inferred. */
  onOpenProject?: (workRef: string) => void;
  onNavigateMission?: (selection: MissionSelection, mode: "current") => void;
  /** Caller retains the existing New project command and permission owner. */
  newProjectControl?: ReactNode;
  locale?: "en" | "zh-CN";
}

/** Read-only catalogue join. Archive inspection never enters Mission/current. */
export function ProjectArchiveBrowser({ scopeKey, programs, read, readPage, sourceGeneration, canRead, onOpenProject, onNavigateMission, newProjectControl, locale = "en" }: ProjectArchiveBrowserProps) {
  const zh = locale === "zh-CN";
  const cards = programs.value?.state === "AVAILABLE" ? programs.value.programs : null;
  const qualified = programs.source.state === "CURRENT" && programs.source.ref && programs.source.revision && programs.source.observed_at &&
    cards && cards.length <= 500 && new Set(cards.map(row => row.workRef)).size === cards.length;
  const catalogueDigest = qualified ? programs.source.ref : null;
  const catalogueRevision = qualified ? programs.source.revision : null;
  let generation = NaN, permitted = false;
  try {
    generation = sourceGeneration?.() ?? NaN;
    permitted = !!catalogueDigest && !!read && !!scopeKey && canRead?.() === true && Number.isSafeInteger(generation) && generation >= 0;
  } catch { permitted = false; }
  type Held = { scope: string; digest: string; revision: string; generation: number; reader: typeof read; pager: typeof readPage;
    status: "loading" | "ready" | "unavailable"; pages: AvailableArchive[] };
  const [held, setHeld] = useState<Held | null>(null);
  const [mode, setMode] = useState<"projects" | "archived">("projects");
  const [inspected, setInspected] = useState<string | null>(null);
  const sequence = useRef(0), abort = useRef<AbortController | null>(null);
  const current = useRef({ scopeKey, catalogueDigest, catalogueRevision, generation, permitted, read, readPage, sourceGeneration, canRead });
  current.current = { scopeKey, catalogueDigest, catalogueRevision, generation, permitted, read, readPage, sourceGeneration, canRead };
  useLayoutEffect(() => {
    sequence.current += 1; abort.current?.abort(); setHeld(null); setInspected(null);
    return () => { sequence.current += 1; abort.current?.abort(); };
  }, [scopeKey, catalogueDigest, catalogueRevision, generation, permitted, read, readPage, sourceGeneration, canRead]);
  useLayoutEffect(() => { setMode("projects"); }, [scopeKey]);
  const visible = permitted && held?.scope === scopeKey && held.digest === catalogueDigest && held.revision === catalogueRevision &&
    held.generation === generation && held.reader === read && held.pager === readPage ? held : null;
  const pages = visible?.pages ?? [];
  const archived = pages.flatMap(page => page.sample.items);
  const checkedRefs = pages.flatMap(page => page.catalogue.work_refs);
  const cursor = nextArchiveCursor(pages);
  const busy = visible?.status === "loading";
  const isCurrent = () => {
    const now = current.current;
    try {
      return now.permitted && now.scopeKey === scopeKey && now.catalogueDigest === catalogueDigest && now.catalogueRevision === catalogueRevision &&
        now.read === read && now.readPage === readPage && now.sourceGeneration === sourceGeneration && now.canRead === canRead &&
        sourceGeneration?.() === generation && canRead?.() === true;
    } catch { return false; }
  };
  const load = async (more = false) => {
    if (!isCurrent() || !read || !catalogueDigest || !catalogueRevision || !cards) return;
    if (more && (busy || !cursor || !readPage)) return;
    const previous = more ? pages : [];
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const own = ++sequence.current;
    const state: Held = { scope: scopeKey, digest: catalogueDigest, revision: catalogueRevision, generation,
      reader: read, pager: readPage, status: "loading", pages: previous };
    if (!more) setInspected(null);
    setHeld(state);
    try {
      const raw = more && cursor && readPage
        ? await readPage({ ...cursor, signal: controller.signal }) : await read({ signal: controller.signal });
      const combined = acceptArchivePage(previous, raw, { documentDigest: catalogueDigest, workRefs: cards.map(row => row.workRef) });
      if (!controller.signal.aborted && sequence.current === own && isCurrent()) setHeld({ ...state, status: "ready", pages: combined });
    } catch {
      if (!controller.signal.aborted && sequence.current === own && isCurrent()) {
        setHeld({ ...state, status: "unavailable", pages: [] }); setInspected(null);
      }
    }
  };
  const archiveRefs = new Set(archived.map(row => row.work_ref));
  const checked = new Set(checkedRefs);
  const projectRows = permitted && cards ? cards.filter(row => !archiveRefs.has(row.workRef)).map(row => ({
    workRef: row.workRef, title: row.title, nextAction: row.nextActionWithheld ? null : row.nextAction, state: row.state,
    archiveStatus: checked.has(row.workRef) ? "NOT_DECLARED" as const : "UNKNOWN" as const,
    openable: !!onOpenProject || (checked.has(row.workRef) && row.rootState === "RESOLVED" && row.rootCandidates.length === 1 && row.rootCandidates[0] === row.rootJobId && !!onNavigateMission),
  })) : [];
  const inspect = (ref: string | null) => {
    if (isCurrent() && (ref === null || archived.some(row => row.work_ref === ref))) setInspected(ref);
  };
  const openProject = (ref: string) => {
    if (!isCurrent() || archiveRefs.has(ref)) return;
    const row = cards?.find(card => card.workRef === ref);
    if (row && onOpenProject) { onOpenProject(ref); return; }
    if (!checked.has(ref) || !row || row.rootState !== "RESOLVED" || row.rootCandidates.length !== 1 || row.rootCandidates[0] !== row.rootJobId) return;
    const selected = normalizeSelection({ workRef: row.workRef, rootJobId: row.rootJobId });
    if (selected) onNavigateMission?.(selected, "current");
  };
  return <section className="project-archive-browser" lang={locale}>
    <ArchiveProjectsView key={scopeKey} scopeKey={scopeKey} locale={locale} mode={mode} newProjectControl={newProjectControl}
      status={pages.length ? "ready" : visible?.status ?? "unread"} projects={projectRows} archived={archived}
      coverage={pages[0] ? { checked: checkedRefs.length, supplied: pages[0].catalogue.qualified_catalogue_count, companyTotal: null } : null}
      inspectedWorkRef={visible ? inspected : null} canRead={permitted} onRead={() => void load()}
      onChangeMode={next => { setMode(next); setInspected(null); if (next === "archived" && !pages.length && !busy) void load(); }}
      onInspectArchive={inspect} onOpenProject={onOpenProject || onNavigateMission ? openProject : undefined} />
    {mode === "archived" && cursor && <div className="project-archive-browser__continuation" aria-busy={busy}>
      {readPage ? <button type="button" disabled={!permitted || busy} onClick={() => void load(true)}>
        {busy ? zh ? "正在检查…" : "Checking…" : zh ? "检查更多已提供的项目" : "Check more supplied projects"}
      </button> : <p>{zh ? "当前读取接口尚未提供后续记录。" : "This reader has not supplied a continuation for the remaining records."}</p>}
    </div>}
  </section>;
}
