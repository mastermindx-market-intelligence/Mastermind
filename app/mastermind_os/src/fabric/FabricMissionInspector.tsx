import { useEffect, useId, useState } from "react";
import { matchesFilter, missionInteriors, type FabricFilter, type FabricMission } from "./mission-interiors";
import "./fabric-inspector.css";

const ZH = {
  "Subagent Fabric": "子代理 Fabric", "Inside this mission": "任务内部状态", "Read only": "只读",
  "Inspect the workers, attempts and returns behind this mission.": "查看此任务中的工作代理、执行尝试和返回结果。",
  "Mission source unavailable. This is not a zero-worker reading.": "任务来源不可用，不代表没有工作代理。",
  "Supplied mission only. Direct M2 Fabric workers and other missions are not included.": "仅含所提供的任务，不包括直接启动的 M2 Fabric 工作代理或其他任务。",
  "Source": "来源", "Coverage": "覆盖范围", "Shown": "已显示", "Owner total": "来源总量", "Omitted by owner": "来源省略数",
  "Unjoined by owner": "来源未关联数", "Unknown": "未知", "Observed running": "观测到的运行中任务", "With results": "包含结果", "Needs inspection": "需要检查",
  "All": "全部", "Running": "运行中", "Problems": "问题", "Filter workers": "筛选工作代理",
  "No matching workers in this observation.": "本次观测没有匹配的工作代理。",
  "Worker list unavailable.": "工作代理列表不可用。", "No children supplied by this observation.": "本次观测未提供子任务。",
  "Selected worker": "所选工作代理", "Select a worker to inspect its exact attempt and lineage.": "选择工作代理以查看具体执行尝试和父子关系。",
  "Role unknown": "角色未知", "No worker identity supplied": "未提供工作代理身份", "Unassociated": "未关联",
  "Job": "任务", "Parent": "父任务", "Lineage": "父子关系", "Step": "步骤", "Worker": "工作代理", "Job state": "任务状态",
  "Current attempt": "当前执行尝试", "Latest attempt": "最近执行尝试", "Attempt number": "尝试序号", "Attempt state": "尝试状态",
  "Started": "开始时间", "Finished": "结束时间", "Exit code": "退出码", "Result present": "存在结果", "Error present": "存在错误",
  "Yes": "是", "No": "否", "Latest attempt is not the current attempt. Its result is not attributed to the current attempt.": "最近执行尝试不等于当前执行尝试，其结果不归于当前尝试。",
  "Execution": "执行", "Review": "审查", "Acceptance": "验收", "Mission-level receipts": "任务级回执",
  "These receipts describe the mission, not acceptance of each child. A completed attempt or present result is not product acceptance.": "这些回执属于任务，不代表逐个子任务已通过验收。执行完成或存在结果不等于产品验收。",
  "Source observed": "来源观测时间", "Association needs reconciliation": "需要核对关联关系",
  "More supplied rows exceed this inspector’s display bound.": "另有来源记录超出此检查器的显示上限。",
  "Attempt count": "执行尝试数", "Attempt limit": "执行尝试上限", "Owner coverage is incomplete; observed counts are not fleet totals.": "来源覆盖不完整，观测计数不代表工作代理池总量。"
} as const;

export function FabricMissionInspector({ mission, locale = "en" }: {
  mission: FabricMission | null; locale?: "en" | "zh-CN";
}) {
  const t = (en: keyof typeof ZH): string => locale === "zh-CN" ? ZH[en] : en;
  const id = useId();
  const model = missionInteriors(mission);
  const identity = JSON.stringify([mission?.program.work_ref, mission?.mission.root_job_id]);
  const [filter, setFilter] = useState<FabricFilter>("all");
  const [selected, setSelected] = useState<{ identity: string; key: string } | null>(null);
  useEffect(() => { setSelected(null); }, [identity]);
  const visible = model.rows.filter(row => matchesFilter(row, filter));
  // Render qualification prevents a stale detail flash before an effect can run.
  const row = selected?.identity === identity ? visible.find(item => item.key === selected.key) : undefined;
  const child = row?.child;
  const attempt = child?.latest_attempt;
  const value = (v: string | number | boolean | null | undefined): string =>
    v === null || v === undefined ? t("Unknown") : typeof v === "boolean" ? t(v ? "Yes" : "No") : String(v);
  const count = (v: number | null | undefined) => value(v);
  const filters: Array<[FabricFilter, keyof typeof ZH]> = [["all", "All"], ["running", "Running"], ["results", "With results"], ["problems", "Problems"]];
  const available = !!mission && mission.read_state.state !== "UNAVAILABLE" && mission.children.state !== "UNAVAILABLE";
  const detailFields: Array<[keyof typeof ZH, string | number | boolean | null | undefined]> = child ? [
    ["Job", child.job_id], ["Parent", child.parent_job_id], ["Job state", child.status],
    ["Worker", child.worker_id], ["Step", child.plan_step_id], ["Current attempt", child.current_attempt_id],
    ["Attempt count", child.attempt_count], ["Attempt limit", child.attempt_limit],
    ["Latest attempt", attempt?.attempt_id], ["Attempt number", attempt?.attempt_number], ["Attempt state", attempt?.status],
    ["Started", attempt?.started_at], ["Finished", attempt?.finished_at], ["Exit code", attempt?.exit_code],
    ["Result present", attempt?.has_result], ["Error present", attempt?.error_present]
  ] : [];

  return <section className="fi-workspace" aria-labelledby={`${id}-title`}>
    <header className="fi-heading"><div><p className="fi-eyebrow">{t("Subagent Fabric")}</p>
      <h2 id={`${id}-title`}>{t("Inside this mission")}</h2>
      <p>{t("Inspect the workers, attempts and returns behind this mission.")}</p></div>
      <span className="fi-badge">{t("Read only")}</span></header>
    {!mission ? <p className="fi-notice" role="status">{t("Mission source unavailable. This is not a zero-worker reading.")}</p> : <>
      <div className="fi-source"><div className="fi-source-tags">
        <span className="fi-badge" data-state={mission.read_state.state}>{t("Source")} · {mission.read_state.state}</span>
        <span className="fi-badge">{t("Coverage")} · {mission.children.coverage}</span>
        <span>{t("Shown")} {model.rows.length} / {t("Owner total")} {count(mission.children.total_count)}</span>
        <span>{t("Omitted by owner")} {count(mission.children.overflow_count)}</span>
        <span>{t("Unjoined by owner")} {count(mission.children.unjoined_job_count)}</span>
      </div><p>{t("Supplied mission only. Direct M2 Fabric workers and other missions are not included.")}</p>
        {mission.children.coverage !== "COMPLETE" && <p className="fi-warning">{t("Owner coverage is incomplete; observed counts are not fleet totals.")}</p>}
        {model.locallyOmitted > 0 && <p className="fi-warning">{model.locallyOmitted} · {t("More supplied rows exceed this inspector’s display bound.")}</p>}
        <small>{t("Source observed")} · {value(mission.source.fabric_view_generated_at)}</small>
      </div>
      <div className="fi-counts" aria-label={t("Subagent Fabric")}>
        <span><strong>{available ? model.running : t("Unknown")}</strong>{t("Observed running")}</span>
        <span><strong>{available ? model.results : t("Unknown")}</strong>{t("With results")}</span>
        <span><strong>{available ? model.problems : t("Unknown")}</strong>{t("Needs inspection")}</span>
      </div>
      <div className="fi-layout"><div className="fi-list-panel">
        <div className="fi-filters" role="group" aria-label={t("Filter workers")}>{filters.map(([key, label]) =>
          <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>{t(label)}</button>)}</div>
        <div className="fi-list">{!available ? <p className="fi-notice">{t("Worker list unavailable.")}</p> : visible.length === 0 ?
          <p className="fi-notice">{t(model.rows.length ? "No matching workers in this observation." : "No children supplied by this observation.")}</p> :
          visible.map(item => <button className="fi-row" type="button" key={item.key} aria-pressed={row?.key === item.key}
            aria-label={`${item.child.job_id} · ${value(item.child.status)} · ${item.child.orchestration_role ?? t("Role unknown")}`}
            onClick={() => setSelected({ identity, key: item.key })}>
            <span className="fi-row-title"><strong>{item.child.job_id}</strong><span className="fi-badge" data-state={item.child.status}>{value(item.child.status)}</span></span>
            <span>{item.child.orchestration_role ?? t("Role unknown")} · {item.child.worker_id ?? t("No worker identity supplied")}</span>
            <small>{t("Parent")} · {item.child.parent_job_id}</small>
            {item.association !== "ASSOCIATED" && <span className="fi-warning">{t("Unassociated")} · {item.problem}</span>}
          </button>)}</div>
      </div><aside className="fi-detail" aria-label={t("Selected worker")} aria-live="polite">
        <h3>{t("Selected worker")}</h3>
        {!child || !available ? <p>{t("Select a worker to inspect its exact attempt and lineage.")}</p> : <>
          {row?.association === "ASSOCIATED" ? <p className="fi-lineage"><span>{t("Lineage")}</span>{row.lineage.join(" → ")}</p> :
            <p className="fi-warning">{t("Association needs reconciliation")} · {row?.problem}</p>}
          {attempt?.attempt_id && attempt.attempt_id !== child.current_attempt_id &&
            <p className="fi-notice">{t("Latest attempt is not the current attempt. Its result is not attributed to the current attempt.")}</p>}
          <dl>{detailFields.map(([label, v]) => <div key={label}><dt>{t(label)}</dt><dd>{value(v)}</dd></div>)}</dl>
        </>}
      </aside></div>
      <footer className="fi-receipts"><h3>{t("Mission-level receipts")}</h3><div className="fi-source-tags">
        <span>{t("Execution")} · <strong>{value(mission.execution.state)}</strong></span>
        <span>{t("Review")} · <strong>{value(mission.review.verdict)}</strong></span>
        <span>{t("Acceptance")} · <strong>{value(mission.acceptance.state)}</strong></span>
      </div><p>{t("These receipts describe the mission, not acceptance of each child. A completed attempt or present result is not product acceptance.")}</p></footer>
    </>}
  </section>;
}
