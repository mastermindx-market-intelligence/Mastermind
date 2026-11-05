import { useLayoutEffect, useRef, useState } from "react";
import { validDirectionSelection, type AcceptedDirectionRead, type DirectionRevision, type DirectionSelection } from "./accepted-direction";
import "./accepted-direction.css";

export interface AcceptedDirectionPanelProps {
  selection: DirectionSelection | null;
  read?: (request: DirectionSelection & { signal: AbortSignal }) => Promise<AcceptedDirectionRead>;
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  /** Existing qualified conversation navigation. This panel performs no SEND. */
  onChangeDirection?: (workRef: string) => void;
  locale?: "en" | "zh-CN";
}

const REASONS = {
  NOT_DECLARED: ["No accepted Direction is declared for this programme.", "此项目尚未声明已接受的方向。"],
  SOURCE_UNAVAILABLE: ["The Direction source could not be read.", "无法读取方向来源。"],
  SOURCE_CHANGED: ["The source changed during this read. Read again for current content.", "读取期间来源已更改。请重新读取当前内容。"],
  RECORD_NOT_FOUND: ["A required source record was not found.", "未找到所需的来源记录。"],
  RECORD_INVALID: ["The source record could not be validated.", "无法验证来源记录。"],
  LINEAGE_CONFLICT: ["The Direction history has conflicting links.", "方向历史的关联存在冲突。"],
  LINEAGE_INCOMPLETE: ["The declared Direction history is incomplete.", "已声明的方向历史不完整。"],
  CONTENT_OVER_BUDGET: ["The source exceeds this read's size limit.", "来源内容超过此次读取的大小限制。"],
} as const;

function RevisionDetails({ revision, zh }: { revision: DirectionRevision; zh: boolean }) {
  return <details className="accepted-direction__sources">
    <summary>{zh ? "修订与来源详情" : "Revision and source details"}</summary>
    <dl>
      <dt>{zh ? "决定记录" : "Decision record"}</dt><dd><code>{revision.decision_ref}</code></dd>
      <dt>{zh ? "决定者" : "Decided by"}</dt><dd>{revision.decided_by}</dd>
      <dt>{zh ? "决定日期（精确到日）" : "Decision date (day precision)"}</dt><dd><time dateTime={revision.decided_at}>{revision.decided_at}</time></dd>
      <dt>{zh ? "仓库" : "Repository"}</dt><dd><code>{revision.source.repository}</code></dd>
      <dt>{zh ? "提交" : "Commit"}</dt><dd><code>{revision.source.commit}</code></dd>
      <dt>{zh ? "路径" : "Path"}</dt><dd><code>{revision.source.path}</code></dd>
      <dt>{zh ? "内容摘要" : "Content digest"}</dt><dd><code>{revision.source.content_sha256}</code></dd>
    </dl>
  </details>;
}

/** AT27: owner-declared accepted Direction and its explicit predecessor chain.
 * Inspecting a previous revision changes only local selection, never currency.
 */
export function AcceptedDirectionPanel({ selection, read, sourceGeneration, canRead, onChangeDirection, locale = "en" }: AcceptedDirectionPanelProps) {
  const zh = locale === "zh-CN";
  const workRef = selection && validDirectionSelection(selection) ? selection.work_ref : null;
  let generation = NaN, permitted = false;
  try {
    generation = sourceGeneration?.() ?? NaN;
    permitted = !!workRef && !!read && typeof canRead === "function" && canRead() === true && Number.isSafeInteger(generation) && generation >= 0;
  } catch { permitted = false; }
  type Held = { reader: typeof read; workRef: string; generation: number; status: "loading" | "ok" | "failed"; value: AcceptedDirectionRead | null };
  const [held, setHeld] = useState<Held | null>(null);
  const [inspected, setInspected] = useState<string | null>(null);
  const seq = useRef(0), abort = useRef<AbortController | null>(null);
  const current = useRef({ read, sourceGeneration, canRead, workRef, generation, permitted });
  current.current = { read, sourceGeneration, canRead, workRef, generation, permitted };
  useLayoutEffect(() => {
    seq.current += 1; abort.current?.abort(); setHeld(null); setInspected(null);
    return () => { seq.current += 1; abort.current?.abort(); };
  }, [read, sourceGeneration, canRead, workRef, generation, permitted]);
  const visible = permitted && held !== null && held.reader === read && held.workRef === workRef && held.generation === generation ? held : null;
  const load = async () => {
    if (!permitted || !read || !workRef) return;
    try {
      if (canRead?.() !== true || sourceGeneration?.() !== generation) return;
    } catch { return; }
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const own = ++seq.current, reader = read, epochReader = sourceGeneration, permissionReader = canRead;
    const state: Held = { reader, workRef, generation, status: "loading", value: null };
    setInspected(null); setHeld(state);
    const owns = () => {
      const live = current.current;
      try {
        return !controller.signal.aborted && seq.current === own && live.read === reader && live.workRef === workRef &&
          live.sourceGeneration === epochReader && live.canRead === permissionReader &&
          epochReader?.() === generation && permissionReader?.() === true;
      } catch { return false; }
    };
    try {
      const value = await reader({ work_ref: workRef, signal: controller.signal });
      if (owns()) setHeld({ ...state, status: "ok", value });
    } catch {
      if (owns()) setHeld({ ...state, status: "failed" });
    }
  };
  const value = visible?.status === "ok" ? visible.value : null;
  const direction = value?.availability === "AVAILABLE" ? value.direction : null;
  const previous = direction?.history.revisions.find(row => row.decision_ref === inspected);
  const selectedRevision = previous ?? direction?.current;
  const reason = value?.availability === "UNAVAILABLE" ? value.reason_codes[0] : null;
  const reasonCopy = reason && Object.hasOwn(REASONS, reason) ? REASONS[reason as keyof typeof REASONS][zh ? 1 : 0] : zh ? "方向证据不可用。" : "Direction evidence is unavailable.";
  const openConversation = () => {
    try {
      if (permitted && workRef && canRead?.() === true && sourceGeneration?.() === generation) onChangeDirection?.(workRef);
    } catch { /* The existing navigation owner remains authoritative. */ }
  };
  return <section className="accepted-direction" lang={locale} aria-label={zh ? "已接受的方向与历史" : "Accepted Direction and history"}>
    <header className="accepted-direction__heading">
      <div><h2>{zh ? "变化了什么，为什么" : "What changed, and why"}</h2><p>{zh ? "当前方向与明确声明的历史。" : "Current Direction and its declared history."}</p></div>
      <button type="button" disabled={!permitted || visible?.status === "loading"} onClick={() => void load()}>
        {visible?.status === "loading" ? zh ? "正在读取…" : "Reading…" : zh ? "读取方向" : "Read Direction"}
      </button>
    </header>
    {!permitted && <p role="status">{zh ? "请在已授权的项目上下文中打开方向。" : "Open Direction in an authorized programme context."}</p>}
    {permitted && !visible && <p role="status">{zh ? "读取以查看此项目的方向。" : "Read to inspect this programme's Direction."}</p>}
    {visible?.status === "failed" && <p role="status">{zh ? "无法读取方向。请重新读取。" : "Direction could not be read. Read again to retry."}</p>}
    {reason && <p role="status">{reasonCopy}</p>}
    {direction && <>
      <article className="accepted-direction__current" aria-label={zh ? "当前已接受的方向" : "Current accepted Direction"}>
        <h3>{zh ? "当前方向" : "Current Direction"}</h3><p className="accepted-direction__answer">{direction.current.answer}</p>
        <h4>{zh ? "为什么" : "Why"}</h4><p>{direction.current.rationale}</p>
      </article>
      <div className="accepted-direction__history">
        <h3>{zh ? "方向历史" : "Direction history"}</h3>
        <p>{direction.history.has_more
          ? zh ? `显示 ${direction.history.revisions.length} 条历史修订；总数未知。` : `${direction.history.revisions.length} previous revisions shown; total unknown.`
          : direction.history.revisions.length === 0
            ? zh ? "此关联尚未声明更早的方向。" : "No earlier Direction is declared by this association."
            : zh ? `${direction.history.revisions.length} 条历史修订。` : `${direction.history.revisions.length} previous revisions.`}</p>
        <div className="accepted-direction__history-body">
          <ol>{[direction.current, ...direction.history.revisions].map(row => <li key={row.decision_ref}>
            <button type="button" aria-pressed={selectedRevision?.decision_ref === row.decision_ref}
              onClick={() => setInspected(row.decision_ref === direction.current.decision_ref ? null : row.decision_ref)}>
              <span>{row.decision_ref === direction.current.decision_ref && <strong>{zh ? "当前 · " : "Current · "}</strong>}{row.answer}</span>
              <time dateTime={row.decided_at}>{row.decided_at}</time>
            </button>
          </li>)}</ol>
          {selectedRevision && <article className="accepted-direction__previous" aria-label={previous
            ? zh ? "历史方向，只读" : "Previous Direction, read only"
            : zh ? "所选当前方向，只读" : "Selected current Direction, read only"}>
            <h4>{previous ? zh ? "历史修订 · 只读" : "Previous revision · Read only" : zh ? "当前修订 · 只读" : "Current revision · Read only"}</h4>
            <p>{selectedRevision.answer}</p><p>{selectedRevision.rationale}</p>
            <RevisionDetails revision={selectedRevision} zh={zh} />
            {previous && <button type="button" onClick={() => setInspected(null)}>{zh ? "查看当前方向" : "View current Direction"}</button>}
          </article>}
        </div>
      </div>
    </>}
    {permitted && workRef && (onChangeDirection ? <button type="button" className="accepted-direction__conversation" onClick={openConversation}>
      {zh ? "在对话中更改方向" : "Change direction in conversation"}
    </button> : <p role="status">{zh ? "此处尚未连接此项目的当前对话。" : "This project's current conversation is not connected here."}</p>)}
  </section>;
}
