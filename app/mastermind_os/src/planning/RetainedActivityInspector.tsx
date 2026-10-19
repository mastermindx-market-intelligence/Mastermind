import { useEffect, useRef, useState } from "react";
import { validActivitySelection, type ActivityRead, type ActivitySelection } from "./retained-activity";
import "./retained-activity.css";

export type RetainedActivityReader =
  (request: ActivitySelection & { signal: AbortSignal }) => Promise<ActivityRead>;

export interface RetainedActivityInspectorProps {
  selection: ActivitySelection | null;
  read?: RetainedActivityReader;
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  locale?: "en" | "zh-CN";
}

/** Explicit, bounded post-candidate evidence. No live tool stream or hidden reasoning. */
export function RetainedActivityInspector({
  selection, read, sourceGeneration, canRead, locale = "en",
}: RetainedActivityInspectorProps) {
  const [body, setBody] = useState<ActivityRead | null>(null);
  const [bodyGeneration, setBodyGeneration] = useState<number | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable">("idle");
  const abort = useRef<AbortController | null>(null);
  const seq = useRef(0);
  const work = selection?.work_ref, root = selection?.root_job_id;
  const job = selection?.job_id, attempt = selection?.attempt_id;
  useEffect(() => {
    seq.current++;
    abort.current?.abort();
    abort.current = null;
    setBody(null);
    setBodyGeneration(null);
    setState("idle");
    return () => { seq.current++; abort.current?.abort(); };
  }, [work, root, job, attempt, read, sourceGeneration, canRead]);
  const chinese = locale === "zh-CN";
  const ready = validActivitySelection(selection) && !!read && !!sourceGeneration &&
    !!canRead && canRead();
  // A prior user's rendered candidate evidence must never survive a viewer
  // revocation, source-generation change or selected Attempt switch, even in
  // the commit before React's effect clears cached state.
  const display = ready && bodyGeneration !== null &&
    sourceGeneration?.() === bodyGeneration && body && selection &&
    body.selection.work_ref === selection.work_ref &&
    body.selection.root_job_id === selection.root_job_id &&
    body.selection.job_id === selection.job_id &&
    body.selection.attempt_id === selection.attempt_id ? body : null;
  const open = async () => {
    if (!ready || !selection || !read || !sourceGeneration || !canRead || state === "loading") return;
    const current = new AbortController();
    abort.current?.abort();
    abort.current = current;
    const ticket = ++seq.current, generation = sourceGeneration();
    const authorized = () => !current.signal.aborted && seq.current === ticket &&
      canRead() && sourceGeneration() === generation;
    setBody(null);
    setBodyGeneration(null);
    setState("loading");
    try {
      const result = await read({ ...selection, signal: current.signal });
      if (!authorized()) return;
      setBody(result);
      setBodyGeneration(generation);
      setState("ready");
    } catch {
      if (authorized()) setState("unavailable");
    }
  };
  return <section className="mm-retained" aria-label={chinese ? "代理保留活动记录" : "Retained operator activity"}>
    <button type="button" disabled={!ready || state === "loading"} onClick={open}>
      {state === "loading" ? (chinese ? "读取中…" : "Reading…") :
        (chinese ? "查看已保留的代理活动" : "Inspect retained activity")}
    </button>
    {ready && state === "unavailable" && <span role="status">{chinese ?
      "原始来源或权限不可用；未推断执行状态。" : "Original source or permission unavailable; execution state unknown."}</span>}
    {display?.availability === "UNAVAILABLE" && <span role="status">{chinese ?
      "没有可展示的已授权活动。" : "No authorized activity available."} ({display.reasons.join(", ")})</span>}
    {display?.availability === "AVAILABLE" && <div className="mm-retained__details">
      <strong>{chinese ? "候选证据元数据" : "Candidate evidence metadata"}</strong>
      <p>{chinese ? "仅包含已经记录的候选事件；不是实时工具流或模型内部推理。" :
        "Recorded candidate events only; not live tool streaming or private model reasoning."}</p>
      <p>{chinese ? "来源覆盖" : "Source coverage"}: {display.coverage}
        {display.sourceTruncated || display.omittedInSample ? " · PARTIAL" : ""}
        {display.omittedInSample ? ` · ${display.omittedInSample} omitted in sample` : ""}
      </p>
      {display.rows.length === 0 && <p>{chinese ? "未观察到候选记录；不能据此推断代理空闲。" :
        "No retained candidates in this sample; this does not establish an idle worker."}</p>}
      {display.rows.length > 0 && <ol>{display.rows.map(row =>
        <li key={row.candidate_event_id + ":" + row.ordinal_in_candidate}>
          <span>{row.category.replaceAll("_", " ").toLowerCase()}</span>
          <small> · {chinese ? "候选保存时间" : "candidate recorded"}: {row.candidate_recorded_at}</small>
        </li>)}</ol>}
      <p className="mm-retained__footnote">{chinese ?
        "执行、审查、验收仍需独立的原始证据。" :
        "Completion, review and acceptance require separate original evidence."}</p>
    </div>}
  </section>;
}
