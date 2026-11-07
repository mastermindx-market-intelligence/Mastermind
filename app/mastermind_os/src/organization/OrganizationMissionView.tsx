import { useId, useLayoutEffect, useRef, useState } from "react";
import type { ResultSelection } from "../result";
import { organizationWork, type OrganizationMission, type ObservedActivity } from "./organization-mission";

export interface OrganizationMissionViewProps {
  mission: OrganizationMission;
  observedAt: string;
  onOpenProject?: (selection: { workRef: string; rootJobId: string }) => void;
  onInspectWorkerResult?: (selection: ResultSelection) => void;
  hasPlanReader?: boolean;
  locale: "en" | "zh-CN";
}

const COPY = {
  "Selected project": "所选项目",
  "Current task": "当前任务",
  "Task description unavailable": "暂无任务说明",
  "Next step": "下一步",
  "No next step supplied. Open the project to inspect its current state.": "暂无下一步说明。打开项目可查看当前状态。",
  "An execution error was reported.": "执行过程中报告了错误。",
  "More next steps": "更多后续步骤",
  "Job details": "任务详情",
  "Back to work list": "返回工作列表",
  "Open project": "打开项目",
  "Operation progress": "任务进度",
  "Observed jobs": "已观测任务",
  "Observed running": "观测为执行中",
  "Finished jobs": "已完成任务",
  "Unknown": "未知",
  "Execution": "执行",
  "Review": "审查",
  "Acceptance": "验收",
  "Not started": "尚未开始",
  "In progress": "进行中",
  "Completed": "已完成",
  "Accepted": "已验收",
  "Cancelled": "已取消",
  "Failed": "失败",
  "Connection lost": "连接丢失",
  "Rate limited": "触及速率限制",
  "Approved": "已批准",
  "Rejected": "已拒绝",
  "Not observed": "尚未观测",
  "Required review pending": "待完成必要审查",
  "Review not required": "无需审查",
  "Selected work is no longer in this view. Choose a current job or change the search.": "所选工作已不在当前视图中。请选择现有任务或更改搜索条件。",
  "This operation only. Job completion does not establish parent or product acceptance.": "仅限此任务。子任务完成不代表父任务或产品已经验收。",
  "Some job activity is unknown. Activity totals are withheld.": "部分任务活动未知，活动总数暂不显示。",
  "Coverage is incomplete. Counts and overall progress remain unknown.": "来源覆盖不完整。总数和整体进度仍未知。",
  "Agents and work": "代理与工作",
  "Find agent or job": "查找代理或任务",
  "Work": "执行",
  "Planning": "规划",
  "Reviewing": "审查",
  "Repair": "修复",
  "Aggregation": "汇总",
  "Role unknown": "角色未知",
  "Working": "正在执行",
  "Queued": "已排队",
  "Finished": "已完成",
  "Needs attention": "需要处理",
  "Activity unknown": "活动未知",
  "Worker not observed": "尚未观测工作代理",
  "Worker": "工作代理",
  "Availability": "可用性",
  "Availability unknown": "可用性未知",
  "Job": "任务",
  "Attempt": "执行尝试",
  "Parent job": "父任务",
  "Selected operation": "所选任务",
  "Child jobs": "子任务",
  "No matching jobs": "无匹配任务",
  "Try another agent or job identifier.": "请尝试其他代理或任务标识。",
  "No child jobs in this observation.": "此观测中没有子任务。",
  "This does not establish that the organization has no agents.": "这不代表组织中没有代理。",
  "Child-job coverage is unavailable or incomplete.": "子任务来源不可用或不完整。",
  "The current source does not establish a complete job list.": "当前来源无法证明任务列表完整。",
  "This row cannot be associated with the selected operation.": "此行无法与所选任务建立关联。",
  "Job relationships describe execution lineage. They do not establish employee reporting lines or role availability.": "任务关系描述执行层级，并不证明人员汇报关系或角色可用性。",
  "Retained results": "已留存结果",
  "Open result": "打开结果",
  "No qualified result reference is available for this job.": "此任务尚无已核验的结果引用。",
  "No qualified completed results in this observation.": "此观测中没有已核验的完成结果。",
  "Result viewing is unavailable in this app context.": "当前应用上下文无法查看结果。",
  "Opening a result reads the retained attempt through the existing authenticated viewer.": "打开结果会通过现有的已认证查看器读取留存的执行尝试。",
  "Dependencies": "依赖",
  "An authorized plan read is needed to show step dependencies.": "显示步骤依赖需要已授权的计划读取。",
  "Source detail": "来源详情",
  "Mission acquired": "任务读取时间",
  "Source revision": "来源修订",
  "Plan step": "计划步骤",
  "More rows exist outside this view. Totals are unknown.": "此视图之外还有更多行，总数未知。",
} as const;
type CopyKey = keyof typeof COPY;

const ACTIVITY: Record<ObservedActivity, CopyKey> = {
  WORKING: "Working", QUEUED: "Queued", FINISHED: "Finished",
  NEEDS_ATTENTION: "Needs attention", UNKNOWN: "Activity unknown",
};
const ROLE: Record<string, CopyKey> = {
  work: "Work", plan: "Planning", review: "Reviewing", repair: "Repair", aggregation: "Aggregation",
};
const EXECUTION: Record<string, CopyKey> = {
  NOT_STARTED: "Not started", IN_PROGRESS: "In progress", COMPLETED: "Completed",
  ACCEPTED: "Accepted", CANCELLED: "Cancelled", FAILED: "Failed", LOST: "Connection lost",
  RATE_LIMITED: "Rate limited",
};

export function OrganizationMissionView({
  mission, observedAt, onOpenProject, onInspectWorkerResult, hasPlanReader, locale,
}: OrganizationMissionViewProps) {
  const t = (key: CopyKey) => locale === "zh-CN" ? COPY[key] : key;
  const model = organizationWork(mission);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const searchId = useId();
  const detailId = useId();
  const detailRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const missingSelectionRef = useRef<HTMLParagraphElement>(null);
  useLayoutEffect(() => { if (selectedKey !== null) detailRef.current?.focus(); }, [selectedKey]);
  const selectRow = (key: string) => {
    setSelectedKey(key);
    // Returning to the selected row and reopening it is still a navigation action.
    if (key === selectedKey) detailRef.current?.focus();
  };
  const returnToWork = () => {
    listRef.current?.querySelector<HTMLButtonElement>('button[aria-pressed="true"]')?.focus();
  };
  const nextSteps = mission.execution.next_actions;
  const nextStep = nextSteps[0] ?? mission.program.next_action;
  const normalized = query.trim().toLocaleLowerCase(locale);
  const visible = model.rows.filter(row => [row.child.job_id, row.child.worker_id,
    row.child.plan_step_id, t(ROLE[row.child.orchestration_role ?? ""] ?? "Role unknown")]
    .some(value => value?.toLocaleLowerCase(locale).includes(normalized)));
  // A refresh or filter must never silently substitute a different deliberate selection.
  const selected = selectedKey === null ? visible[0] ?? null
    : visible.find(row => row.key === selectedKey) ?? null;
  const selectionMissing = selectedKey !== null && selected === null;
  useLayoutEffect(() => {
    if (selectionMissing) (searchRef.current ?? missingSelectionRef.current)?.focus();
  }, [selectionMissing]);
  const finishedResults = model.rows.filter(row => row.activity === "FINISHED" && row.result);
  const rootId = mission.mission.root_job_id!;
  const role = (value: string | null) => t(ROLE[value ?? ""] ?? "Role unknown");
  const navigate = (jobId: string) => {
    const row = model.rows.find(item => item.child.job_id === jobId && item.association === "ASSOCIATED");
    if (row) { setQuery(""); selectRow(row.key); }
  };
  const parent = selected?.association === "ASSOCIATED"
    ? model.rows.find(row => row.child.job_id === selected.child.parent_job_id && row.association === "ASSOCIATED")
    : null;
  const children = selected?.association === "ASSOCIATED"
    ? model.rows.filter(row => row.child.parent_job_id === selected.child.job_id && row.association === "ASSOCIATED")
    : [];

  return <div className="organization-workspace__operation">
    <header className="organization-workspace__project">
      <div>
        <span className="organization-workspace__eyebrow">{t("Selected project")}</span>
        <h3>{mission.program.title ?? mission.program.work_ref}</h3>
        <p><span>{t("Current task")}: </span><span>{mission.mission.title ?? t("Task description unavailable")}</span></p>
      </div>
      {onOpenProject && <button type="button" className="organization-workspace__action"
        onClick={() => onOpenProject({ workRef: mission.program.work_ref, rootJobId: rootId })}>
        {t("Open project")} <span aria-hidden="true">↗</span>
      </button>}
    </header>

    <section className="organization-workspace__next-step" aria-label={t("Next step")}>
      <h3>{t("Next step")}</h3>
      {mission.execution.errors_present && <p className="organization-workspace__notice" role="status">{t("An execution error was reported.")}</p>}
      <p>{nextStep ?? t("No next step supplied. Open the project to inspect its current state.")}</p>
      {nextSteps.length > 1 && <details className="organization-workspace__source">
        <summary>{t("More next steps")}</summary>
        <ul>{nextSteps.slice(1).map((step, index) => <li key={index}>{step}</li>)}</ul>
      </details>}
    </section>

    <section className="organization-workspace__progress" aria-label={t("Operation progress")}>
      <h3>{t("Operation progress")}</h3>
      <dl className="organization-workspace__metrics">
        <div><dt>{t("Observed jobs")}</dt><dd>{model.observedJobs ?? t("Unknown")}</dd></div>
        <div><dt>{t("Observed running")}</dt><dd>{model.working ?? t("Unknown")}</dd></div>
        <div><dt>{t("Finished jobs")}</dt><dd>{model.finished ?? t("Unknown")}</dd></div>
      </dl>
      <dl className="organization-workspace__milestones">
        <div><dt>{t("Execution")}</dt><dd>{t(EXECUTION[mission.execution.state ?? ""] ?? "Unknown")}</dd></div>
        <div><dt>{t("Review")}</dt><dd>{t(mission.review.verdict === "approve" ? "Approved" :
          mission.review.verdict === "reject" ? "Rejected" : mission.review.required === true
            ? "Required review pending" : mission.review.required === false ? "Review not required" : "Not observed")}</dd></div>
        <div><dt>{t("Acceptance")}</dt><dd>{t(mission.acceptance.state === "ACCEPTED" ? "Accepted" : "Not observed")}</dd></div>
      </dl>
      {!model.coverageComplete && <p className="organization-workspace__notice" role="status">{t("Coverage is incomplete. Counts and overall progress remain unknown.")}</p>}
      {model.coverageComplete && !model.activityComplete && <p className="organization-workspace__notice" role="status">{t("Some job activity is unknown. Activity totals are withheld.")}</p>}
      <p className="organization-workspace__caption">{t("This operation only. Job completion does not establish parent or product acceptance.")}</p>
    </section>

    <section className="organization-workspace__work" aria-label={t("Agents and work")}>
      <div className="organization-workspace__section-heading">
        <h3>{t("Agents and work")}</h3>
        {model.rows.length > 0 && <div className="organization-workspace__search">
          <label htmlFor={searchId}>{t("Find agent or job")}</label>
          <input ref={searchRef} id={searchId} type="search" value={query} onChange={event => setQuery(event.target.value)} />
        </div>}
      </div>
      {selectionMissing && <p ref={missingSelectionRef} tabIndex={-1} className="organization-workspace__notice" role="status">
        {t("Selected work is no longer in this view. Choose a current job or change the search.")}
      </p>}
      {model.rows.length === 0 ? <div className="organization-workspace__empty">
        <strong>{t(model.coverageComplete ? "No child jobs in this observation." : "Child-job coverage is unavailable or incomplete.")}</strong>
        <p>{t(model.coverageComplete ? "This does not establish that the organization has no agents." :
          "The current source does not establish a complete job list.")}</p>
      </div> : visible.length === 0 ? <div className="organization-workspace__empty" role="status">
        <strong>{t("No matching jobs")}</strong><p>{t("Try another agent or job identifier.")}</p>
      </div> : <div className="organization-workspace__work-layout">
        <ul ref={listRef} className="organization-workspace__jobs" aria-label={t("Observed jobs")}>
          {visible.map(row => <li key={row.key}>
            <button type="button" aria-pressed={selected?.key === row.key} aria-controls={detailId}
              onClick={() => selectRow(row.key)}>
              <span className="organization-workspace__job-title">{role(row.child.orchestration_role)}
                <span className="organization-workspace__state" data-state={row.activity}>{t(ACTIVITY[row.activity])}</span>
              </span>
              <span className="organization-workspace__job-id">{row.child.job_id}</span>
              <span className="organization-workspace__worker">{row.child.worker_id ?? t("Worker not observed")}</span>
            </button>
          </li>)}
        </ul>
        {selected && <section id={detailId} ref={detailRef} tabIndex={-1} className="organization-workspace__job-detail"
          aria-label={t("Job") + " " + selected.child.job_id}
          onKeyDown={event => {
            if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); returnToWork(); }
          }}>
          <div className="organization-workspace__detail-title">
            <h4>{role(selected.child.orchestration_role)}</h4>
            <span className="organization-workspace__state" data-state={selected.activity}>{t(ACTIVITY[selected.activity])}</span>
          </div>
          <button type="button" className="organization-workspace__link" onClick={returnToWork} aria-keyshortcuts="Escape">{t("Back to work list")}</button>
          <details key={selected.key} className="organization-workspace__source">
            <summary>{t("Job details")}</summary>
          <dl>
            <div><dt>{t("Worker")}</dt><dd>{selected.child.worker_id ?? t("Worker not observed")}</dd></div>
            <div><dt>{t("Availability")}</dt><dd>{t("Availability unknown")}</dd></div>
            <div><dt>{t("Job")}</dt><dd>{selected.child.job_id}</dd></div>
            <div><dt>{t("Attempt")}</dt><dd>{selected.exactAttempt ? selected.child.current_attempt_id : t("Not observed")}</dd></div>
            {selected.child.plan_step_id && <div><dt>{t("Plan step")}</dt><dd>{selected.child.plan_step_id}</dd></div>}
            <div><dt>{t("Parent job")}</dt><dd>{selected.association !== "ASSOCIATED" ? t("Unknown") :
              parent ? <button type="button" className="organization-workspace__link" onClick={() => navigate(parent.child.job_id)}>{parent.child.job_id}</button> :
              selected.child.parent_job_id === rootId ? <>{t("Selected operation")} · {rootId}</> : t("Unknown")}</dd></div>
          </dl>
          </details>
          {selected.association !== "ASSOCIATED" && <p className="organization-workspace__notice">{t("This row cannot be associated with the selected operation.")}</p>}
          {children.length > 0 && <div className="organization-workspace__children">
            <h4>{t("Child jobs")}</h4>
            {children.map(row => <button type="button" className="organization-workspace__link" key={row.key}
              onClick={() => navigate(row.child.job_id)}>{role(row.child.orchestration_role)} · {row.child.job_id}</button>)}
          </div>}
          {selected.result ? onInspectWorkerResult
            ? <button type="button" className="organization-workspace__action" onClick={() => onInspectWorkerResult(selected.result!)}>{t("Open result")}</button>
            : <p>{t("Result viewing is unavailable in this app context.")}</p>
            : <p className="organization-workspace__caption">{t("No qualified result reference is available for this job.")}</p>}
        </section>}
      </div>}
      {model.locallyOmitted > 0 && <p className="organization-workspace__notice">{t("More rows exist outside this view. Totals are unknown.")}</p>}
      <p className="organization-workspace__caption">{t("Job relationships describe execution lineage. They do not establish employee reporting lines or role availability.")}</p>
    </section>

    <section className="organization-workspace__results" aria-label={t("Retained results")}>
      <h3>{t("Retained results")}</h3>
      {finishedResults.length === 0 ? <p className="organization-workspace__caption">{t("No qualified completed results in this observation.")}</p> :
        <ul>{finishedResults.map(row => <li key={row.key}>
          <div><strong>{role(row.child.orchestration_role)}</strong><span>{row.child.job_id}</span></div>
          {onInspectWorkerResult ? <button type="button" className="organization-workspace__action"
            aria-label={t("Open result") + " · " + row.child.job_id}
            onClick={() => onInspectWorkerResult(row.result!)}>{t("Open result")}</button>
            : <span>{t("Result viewing is unavailable in this app context.")}</span>}
        </li>)}</ul>}
      {finishedResults.length > 0 && <p className="organization-workspace__caption">{t("Opening a result reads the retained attempt through the existing authenticated viewer.")}</p>}
    </section>

    {!hasPlanReader && <section className="organization-workspace__dependencies" aria-label={t("Dependencies")}>
      <h3>{t("Dependencies")}</h3><p className="organization-workspace__caption">{t("An authorized plan read is needed to show step dependencies.")}</p>
    </section>}
    <details className="organization-workspace__source">
      <summary>{t("Source detail")}</summary>
      <dl>
        <div><dt>{t("Selected project")}</dt><dd>{mission.program.work_ref}</dd></div>
        <div><dt>{t("Selected operation")}</dt><dd>{rootId}</dd></div>
        <div><dt>{t("Mission acquired")}</dt><dd>{observedAt}</dd></div>
        <div><dt>{t("Source revision")}</dt><dd className="organization-workspace__fingerprint">{mission.source.owner_observation?.control_room?.document_digest}</dd></div>
      </dl>
    </details>
  </div>;
}
