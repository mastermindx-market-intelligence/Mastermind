import { useId, useState } from "react";
import type { ControlRoomState } from "../control-room";
import type { ControlRoomCapabilityProvider } from "../control-room-navigation";
import { WORK_GROUP_ORDER, type WorkDocument } from "../work";
import type { HostCapacityState } from "./host-capacity";
import { HostTelemetryPanel } from "./HostTelemetryPanel";
import { RetainedProviderCapacityPanel } from "./RetainedProviderCapacityPanel";
import type { RetainedProviderCapacityState } from "./retained-provider-capacity";
import "./resources.css";

export type ResourcesWorkState =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "DOCUMENT"; document: WorkDocument };
type Props = {
  controlRoom: ControlRoomState;
  work: ResourcesWorkState;
  locale?: "en" | "zh-CN";
  onReviewSources?: () => void;
  onOpenWork?: (rootJobId: string) => void;
  /** Fixed authenticated retained owner only; no default probe/read is implied. */
  capacity?: HostCapacityState;
  providerCapacity?: RetainedProviderCapacityState;
};
const names: Record<ControlRoomCapabilityProvider, string> = {
  chatgpt: "ChatGPT", claude_code: "Claude Code", claude_desktop: "Claude Desktop",
  cursor_agent: "Cursor", codex: "Codex", aionui: "AionUI",
};
const providers = Object.keys(names) as ControlRoomCapabilityProvider[];

/** Inspect existing authenticated observations only. System installation, host
 * admission, per-task serviceability and queue pressure remain distinct facts.
 * No source read, placement, admission, reservation or provider effect occurs here.
 */
export function ResourcesSystemsPanel({ controlRoom, work, locale = "en", onReviewSources, onOpenWork, capacity, providerCapacity }: Props) {
  const zh = locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  const labelId = useId();
  const [selected, setSelected] = useState<ControlRoomCapabilityProvider | null>(null);
  const [showAllWork, setShowAllWork] = useState(false);
  const navigation = controlRoom.state === "AVAILABLE" && controlRoom.navigation.state === "AVAILABLE"
    ? controlRoom.navigation : null;
  const rows = providers.flatMap(provider => {
    const capability = navigation?.capabilities[provider];
    return capability ? [{ provider, capability }] : [];
  });
  const current = rows.find(row => row.provider === selected) ?? rows[0];
  const bindings = current && navigation
    ? navigation.bindings.filter(binding => binding.provider === current.provider) : [];
  const document = work.kind === "DOCUMENT" && work.document.availability === "AVAILABLE" ? work.document : null;
  const workRows = document ? WORK_GROUP_ORDER.flatMap(group => document.groups[group]) : [];
  const visibleWork = showAllWork ? workRows : workRows.slice(0, 8);
  const unknown = t("Not supplied", "未提供");
  const capacityLabel = (value: string) => ({
    WAITING_CAPACITY: t("Waiting for capacity", "等待可用容量"),
    NOT_APPLICABLE: t("Not applicable to this work state", "不适用于此工作状态"),
    UNKNOWN: unknown, NOT_PROJECTED: unknown,
  } as Record<string, string>)[value] ?? unknown;
  return <section className="resources-workspace" aria-labelledby={labelId} aria-busy={controlRoom.state === "PENDING"}>
    <header className="resources-header">
      <div><p className="eyebrow">{t("RESOURCES & SYSTEMS", "资源与系统")}</p>
        <h2 id={labelId}>{t("Check readiness before placing work", "安排工作前，先检查就绪情况")}</h2>
        <p className="muted">{t("Inspect connected systems and the evidence available for each work item.", "查看已连接系统，以及每项工作的现有证据。")}</p>
      </div>
      {onReviewSources && <button type="button" onClick={() => onReviewSources?.()}>{t("Review sources", "查看来源")}</button>}
    </header>
    <div className="resources-columns">
      <section className="card resources-inventory" aria-label={t("Execution resources", "执行资源")}>
        <h3>{t("Execution resources", "执行资源")}</h3>
        <p className="muted">{t("Observed system inventory. Installation does not establish readiness for a task.", "系统清单的观测结果。已安装不代表能够执行具体任务。")}</p>
        {rows.length ? <>
          <div className="resources-table-heading" aria-hidden="true"><span>{t("RESOURCE / ROLE", "资源 / 角色")}</span><span>{t("READINESS", "就绪情况")}</span><span>{t("WORK / PRESSURE", "工作 / 压力")}</span></div>
          <ul className="resources-list">{rows.map(({ provider, capability }) => <li key={provider}>
            <button type="button" aria-pressed={current?.provider === provider} onClick={() => setSelected(provider)} className="resources-row">
              <span><strong>{names[provider]}</strong><small>{t("Execution system", "执行系统")}</small></span>
              <span><b>{capability.installed ? t("Installed", "已安装") : t("Not installed", "未安装")}</b><small>{t("Task preflight not supplied", "未提供任务预检")}</small></span>
              <span><b>{unknown}</b><small>{t("Inspect source evidence", "查看来源证据")}</small></span>
            </button>
          </li>)}</ul>
        </> : <p role="status">{controlRoom.state === "PENDING"
          ? t("Reading connected systems…", "正在读取已连接系统…")
          : t("System inventory is unavailable in this observation. This does not mean no resources exist.", "本次观测无法提供系统清单。这不代表没有资源。")}</p>}
      </section>
      <section className="card resources-inspector" aria-label={t("Selected resource", "所选资源")}>
        <h3>{current ? names[current.provider] : t("Resource details", "资源详情")}</h3>
        <dl>
          <div><dt>{t("Host readiness", "主机就绪情况")}</dt><dd>{unknown}</dd></div>
          <div><dt>{t("Serviceability / task preflight", "服务能力 / 任务预检")}</dt><dd>{unknown}</dd></div>
          <div><dt>{t("Assigned / protected work", "已分配 / 受保护工作")}</dt><dd>{t("No resource-to-work assignment supplied", "未提供资源与工作的分配关系")}</dd></div>
          <div><dt>{t("Queue pressure", "队列压力")}</dt><dd>{unknown}</dd></div>
        </dl>
        {current && <details><summary>{t("Source details", "来源详情")}</summary>
          <dl><div><dt>{t("System version", "系统版本")}</dt><dd>{current.capability.version ?? unknown}</dd></div>
            <div><dt>{t("Owner capability state", "来源能力状态")}</dt><dd><code>{current.capability.state}</code></dd></div>
            <div><dt>{t("Observed session bindings", "已观测会话绑定")}</dt><dd>{bindings.length}</dd></div>
            <div><dt>{t("Observation time", "观测时间")}</dt><dd>{controlRoom.state === "AVAILABLE" && controlRoom.observedAt ? <time dateTime={controlRoom.observedAt}>{controlRoom.observedAt}</time> : unknown}</dd></div>
          </dl>
          <p>{t("Session bindings are navigation records. They do not establish active work, host health or placement permission.", "会话绑定属于导航记录，不能证明工作正在运行、主机健康或已有调度权限。")}</p>
        </details>}
      </section>
    </div>
    <section className="card resources-work" aria-label={t("Work capacity evidence", "工作容量证据")}>
      <h3>{t("Work capacity evidence", "工作容量证据")}</h3>
      <p className="muted">{t("These observations belong to exact work items. They are not free slots or a fleet utilisation total.", "这些观测对应具体工作，不代表空闲槽位或集群总利用率。")}</p>
      {document ? <>
        <p>{t("Generated at", "生成时间")} <time dateTime={document.generated_at}>{document.generated_at}</time> · {document.coverage.completeness === "COMPLETE" ? t("Complete returned view", "返回视图完整") : t("Partial returned view", "返回视图不完整")}</p>
        {workRows.length ? <ul className="resources-work-list">{visibleWork.map(row => <li key={row.root_job_id}>
          <div><strong>{row.root_job_id}</strong><p>{capacityLabel(row.capacity.value)}</p></div>
          {onOpenWork && <button type="button" onClick={() => onOpenWork(row.root_job_id)}>{t("Assigned work", "查看工作")}</button>}
          <details><summary>{t("Capacity source", "容量来源")}</summary><dl>
            <div><dt>{t("Source state", "来源状态")}</dt><dd><code>{row.capacity.value}</code></dd></div>
            <div><dt>{t("Owner", "来源")}</dt><dd>{row.capacity.source ?? unknown}</dd></div>
            <div><dt>{t("Evidence", "证据")}</dt><dd>{row.capacity.evidence_ref ?? unknown}</dd></div>
            <div><dt>{t("Observed", "观测时间")}</dt><dd>{row.capacity.observed_at ?? unknown}</dd></div>
          </dl></details>
        </li>)}</ul> : <p role="status">{t("No work items were returned in this bounded view. Fleet capacity remains unknown.", "此有限视图未返回工作项。集群容量仍然未知。")}</p>}
        {!showAllWork && workRows.length > 8 && <button type="button" onClick={() => setShowAllWork(true)}>{t(`See all ${workRows.length} returned work items`, `查看全部 ${workRows.length} 项已返回工作`)}</button>}
        {document.coverage.truncated && <p role="status">{t("The source omitted work items. This view does not describe the full queue.", "来源省略了部分工作项。此视图不能代表完整队列。")}</p>}
      </> : <p role="status">{work.kind === "PENDING" ? t("Reading work capacity evidence…", "正在读取工作容量证据…") : t("Work capacity evidence is unavailable. No idle or busy state is inferred.", "无法获取工作容量证据，不能推断为空闲或繁忙。")}</p>}
    </section>
    <HostTelemetryPanel state={capacity ?? { state: "UNAVAILABLE" }} locale={locale} />
    {providerCapacity && <RetainedProviderCapacityPanel state={providerCapacity} locale={locale} />}
    <aside className="card resources-missing" aria-label={t("Missing evidence", "缺失证据")}>
      <h3>{t("Provider capacity is not supplied", "未提供供应商容量")}</h3>
      <p>{t("Host admission, task serviceability, protected assignments and provider queue pressure need separate owner observations before placement can be assessed.", "评估工作安排前，需要分别获取主机准入、任务服务能力、受保护分配和供应商队列压力的来源观测。")}</p>
      {onReviewSources && <button type="button" onClick={() => onReviewSources?.()}>{t("Sources & access", "来源与访问")}</button>}
    </aside>
  </section>;
}
