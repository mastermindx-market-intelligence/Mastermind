import { useEffect, useRef, useState } from "react";
import { decodeAdmittedPlan, validPlanSelection, type PlanRead, type PlanSelection } from "./admitted-plan";
import "./admitted-plan.css";

/** The injected reader must be the existing authenticated Workspace acquisition owner. */
export type AdmittedPlanReader = (request: PlanSelection & { signal: AbortSignal }) => Promise<unknown>;
export interface AdmittedPlanInspectorProps {
  selection: PlanSelection | null;
  read?: AdmittedPlanReader;
  /** Existing auth/source generation, not a new identity or permission authority. */
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  locale?: "en" | "zh-CN";
}

export function AdmittedPlanInspector({
  selection, read, sourceGeneration, canRead, locale = "en",
}: AdmittedPlanInspectorProps) {
  const [document, setDocument] = useState<PlanRead | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable">("idle");
  const request = useRef<AbortController | null>(null);
  const requestSeq = useRef(0);
  const selectedWork = selection?.work_ref;
  const selectedRoot = selection?.root_job_id;
  useEffect(() => {
    requestSeq.current += 1;
    request.current?.abort();
    request.current = null;
    setDocument(null);
    setState("idle");
    return () => { requestSeq.current += 1; request.current?.abort(); };
  }, [selectedWork, selectedRoot, read, sourceGeneration, canRead]);

  const qualified = validPlanSelection(selection);
  const ready = qualified && !!read && !!sourceGeneration && !!canRead && canRead();
  const chinese = locale === "zh-CN";
  const open = async () => {
    if (!ready || !selection || !read || !sourceGeneration || !canRead || state === "loading") return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    const seq = ++requestSeq.current;
    const initialGeneration = sourceGeneration();
    const current = () => !controller.signal.aborted && requestSeq.current === seq &&
      canRead() && sourceGeneration() === initialGeneration;
    setDocument(null);
    setState("loading");
    try {
      const raw = await read({ ...selection, signal: controller.signal });
      if (!current()) return;
      const parsed = decodeAdmittedPlan(raw, selection);
      if (!current()) return;
      setDocument(parsed);
      setState("ready");
    } catch {
      if (current()) setState("unavailable");
    } finally {
      if (request.current === controller) request.current = null;
    }
  };

  return <section className="mm-admitted-plan" aria-label={chinese ? "已准入执行计划" : "Admitted execution plan"}>
    <div className="mm-admitted-plan__heading">
      <div>
        <h3>{chinese ? "已准入执行计划" : "Admitted execution plan"}</h3>
        <p>{chinese ? "源自执行系统的步骤与依赖；准入不代表已经执行。" :
          "Source-qualified steps and dependencies. Admission does not establish execution."}</p>
      </div>
      <button type="button" onClick={() => { void open(); }} disabled={!ready || state === "loading"}>
        {state === "loading" ? (chinese ? "正在读取…" : "Reading…") :
          (chinese ? "检查计划" : "Inspect plan")}
      </button>
    </div>
    {!ready && <p role="status">{chinese ? "当前身份未提供已授权的计划读取。" :
      "No authorized plan reader is available for the current identity."}</p>}
    {state === "unavailable" && <p role="status">{chinese ? "当前计划不可用；未推断进度。" :
      "Plan read unavailable; no progress inferred."}</p>}
    {document?.availability === "UNAVAILABLE" && <p role="status">
      {chinese ? "执行系统尚未提供可用的准入计划。" : "No available admitted plan was provided by the execution owner."}
      {" "}({document.reason_codes.join(", ")})
    </p>}
    {document?.availability === "AVAILABLE" && <div className="mm-admitted-plan__results">
      <div className="mm-admitted-plan__summary">
        <strong>{document.plan.steps.length} {chinese ? "个已准入步骤" : "admitted steps"}</strong>
        <span>{chinese ? "执行状态：未由此读取确认" : "Execution status: not asserted by this read"}</span>
      </div>
      <ol>
        {document.plan.steps.map(step => <li key={step.step_id}>
          <div className="mm-admitted-plan__step-title">
            <span aria-hidden="true" className="mm-admitted-plan__step-no">{step.ordinal + 1}</span>
            <span>{step.objective}</span>
          </div>
          <div className="mm-admitted-plan__meta">
            <code>{step.step_id}</code>
            <span>{step.business_impact}</span>
            {step.review_required && <span>{chinese ? "需独立审查" : "Review required"}</span>}
            {step.prerequisite_step_ids.length > 0 && <span>
              {chinese ? "依赖：" : "Depends on: "}{step.prerequisite_step_ids.join(", ")}
            </span>}
          </div>
        </li>)}
      </ol>
      <p className="mm-admitted-plan__footnote">{chinese ?
        "只有执行系统的真实 Job / Attempt / 审查证据才可以证明任务开始、完成或验收。" :
        "Only observed Jobs, Attempts, reviews and acceptance evidence can establish progress or completion."}</p>
    </div>}
  </section>;
}
