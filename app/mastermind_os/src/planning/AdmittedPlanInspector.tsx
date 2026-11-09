import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { validPlanSelection, type PlanRead, type PlanSelection } from "./admitted-plan";
import { RetainedActivityInspector, type RetainedActivityReader } from "./RetainedActivityInspector";
import { validActivitySelection } from "./retained-activity";
import type { MissionDocument, Missionv3Document } from "../mission";
import { observePlanWorkers } from "./plan-mission-observation";
import "./admitted-plan.css";

/** The existing authenticated MissionHost performs the sole raw-owner decode. */
export type AdmittedPlanReader = (request: PlanSelection & { signal: AbortSignal }) => Promise<PlanRead>;
export interface AdmittedPlanInspectorProps {
  selection: PlanSelection | null;
  read?: AdmittedPlanReader;
  readActivity?: RetainedActivityReader;
  /** Existing auth/source generation, not a new identity or permission authority. */
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  locale?: "en" | "zh-CN";
  /** Independently authorized Mission source; never proof of the plan snapshot. */
  mission?: MissionDocument | Missionv3Document | null;
  missionSourceState?: string;
  missionObservedAt?: string | null;
}

export function AdmittedPlanInspector({
  selection, read, readActivity, sourceGeneration, canRead, locale = "en",
  mission = null, missionSourceState = "UNAVAILABLE", missionObservedAt = null,
}: AdmittedPlanInspectorProps) {
  const [document, setDocument] = useState<PlanRead | null>(null);
  const [documentGeneration, setDocumentGeneration] = useState<number | null>(null);
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
    setDocumentGeneration(null);
    setState("idle");
    return () => { requestSeq.current += 1; request.current?.abort(); };
  }, [selectedWork, selectedRoot, read, sourceGeneration, canRead]);

  const qualified = validPlanSelection(selection);
  const ready = qualified && !!read && !!sourceGeneration && !!canRead && canRead();
  useLayoutEffect(() => {
    if (!ready) {
      // Revocation is irreversible for the old acquisition. A future
      // regrant—even if the host reuses the numeric source generation—
      // must make a fresh authorized read before any old content reappears.
      requestSeq.current += 1;
      request.current?.abort();
      request.current = null;
      setDocument(null);
      setDocumentGeneration(null);
      setState("idle");
    }
  }, [ready]);
  // Cached plan objectives and their nested Mission/Attempt observations must
  // disappear on the *same render* as viewer revocation, source-generation
  // rotation, or root selection change; a later useEffect cleanup is too late.
  const displayedPlan = ready && documentGeneration !== null &&
    sourceGeneration?.() === documentGeneration && document && selection &&
    document.selection.work_ref === selection.work_ref &&
    document.selection.root_job_id === selection.root_job_id ? document : null;
  const chinese = locale === "zh-CN";
  const observedWorkers = displayedPlan?.availability === "AVAILABLE" && selection
    ? observePlanWorkers(selection, displayedPlan.plan, mission, missionSourceState, missionObservedAt)
    : null;
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
    setDocumentGeneration(null);
    setState("loading");
    try {
      const qualifiedPlan = await read({ ...selection, signal: controller.signal });
      if (!current()) return;
      setDocument(qualifiedPlan);
      setDocumentGeneration(initialGeneration);
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
    {ready && state === "unavailable" && <p role="status">{chinese ? "当前计划不可用；未推断进度。" :
      "Plan read unavailable; no progress inferred."}</p>}
    {displayedPlan?.availability === "UNAVAILABLE" && <p role="status">
      {chinese ? "执行系统尚未提供可用的准入计划。" : "No available admitted plan was provided by the execution owner."}
      {" "}({displayedPlan.reason_codes.join(", ")})
    </p>}
    {displayedPlan?.availability === "AVAILABLE" && <div className="mm-admitted-plan__results">
      <div className="mm-admitted-plan__summary">
        <strong>{displayedPlan.plan.steps.length} {chinese ? "个已准入步骤" : "admitted steps"}</strong>
        <span>{chinese ? "执行状态：未由此读取确认" : "Execution status: not asserted by this read"}</span>
      </div>
      <ol>
        {displayedPlan.plan.steps.map(step => <li key={step.step_id}>
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
          {observedWorkers?.get(step.step_id)?.state === "OBSERVED" && <div className="mm-admitted-plan__observed">
            <strong>{chinese ? "任务观测（独立快照）" : "Mission jobs (separate observation)"}</strong>
            <p className="mm-admitted-plan__observed-source">
              {chinese ? "来源覆盖" : "Source coverage"}: {observedWorkers.get(step.step_id)!.coverage}
              {observedWorkers.get(step.step_id)!.observed_at && <> · {chinese ? "观测时间" : "observed at"} {observedWorkers.get(step.step_id)!.observed_at}</>}
              {" · "}{chinese ? "非原子联合，不能推断计划完成" : "non-atomic with plan; no completion inferred"}
            </p>
            <ul>{observedWorkers.get(step.step_id)!.workers.map(worker => <li key={worker.job_id}>
              <code>{worker.job_id}</code> · {chinese ? "观测状态" : "observed job state"}: {worker.status ?? (chinese ? "未知" : "unknown")}
              {worker.worker_id && <span> · {chinese ? "工作代理" : "worker"}: {worker.worker_id}</span>}
              {readActivity && selection && worker.current_attempt_id &&
                validActivitySelection({ ...selection, job_id: worker.job_id,
                  attempt_id: worker.current_attempt_id }) &&
                <RetainedActivityInspector
                  key={worker.job_id + ":" + worker.current_attempt_id}
                  selection={{ ...selection, job_id: worker.job_id,
                    attempt_id: worker.current_attempt_id }}
                  read={readActivity} sourceGeneration={sourceGeneration}
                  canRead={canRead} locale={locale} />}
            </li>)}</ul>
            {observedWorkers.get(step.step_id)!.omitted && <p>{chinese ? "部分关联任务未显示。" : "Some associated jobs exceed this display bound."}</p>}
          </div>}
          {observedWorkers?.get(step.step_id)?.state === "NO_MATCH_IN_SAMPLE" && <p className="mm-admitted-plan__observed-note">
            {chinese ? "所提供的任务观测未列出此步骤的关联任务；这不代表没有执行。" : "No associated job in the supplied Mission sample; absence of execution is not established."}
          </p>}
        </li>)}
      </ol>
      <p className="mm-admitted-plan__footnote">{chinese ?
        "只有执行系统的真实 Job / Attempt / 审查证据才可以证明任务开始、完成或验收。" :
        "Only observed Jobs, Attempts, reviews and acceptance evidence can establish progress or completion."}</p>
    </div>}
  </section>;
}
