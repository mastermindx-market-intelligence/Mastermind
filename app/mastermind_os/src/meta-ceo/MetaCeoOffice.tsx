import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createDirectionPreview, previewIsCurrent, type DirectionPreview } from "./preview";
import { sameTarget, type OfficeProjection, type ProjectionContext, type SourceClaim } from "./projection";
import "./office.css";
import { FabricMissionInspector } from "../fabric/FabricMissionInspector";
import { AttendedFabricInspector } from "../fabric/AttendedFabricInspector";
import { AdmittedPlanInspector } from "../planning/AdmittedPlanInspector";
import type { PlanSelection } from "../planning/admitted-plan";
import type { ActivitySelection } from "../planning/retained-activity";

// Stable presentation callbacks: parent render churn cannot invalidate an acquired plan.
// Each call resolves the *current* installed host; neither reference conveys authorization.
const readOfficePlan = (request: PlanSelection & { signal: AbortSignal }) =>
  window.MastermindMissionHost!.readAdmittedPlan!(request);
const readOfficeActivity = (request: ActivitySelection & { signal: AbortSignal }) =>
  window.MastermindMissionHost!.readRetainedActivity!(request);
const officePlanGeneration = () => window.MastermindMissionHost!.invalidationGeneration!();
const officePlanPermission = () => {
  const state = window.MastermindMissionHost!.auth!.getState();
  return state.status === "signed_in" && state.acquisition;
};

/** Draft storage belongs to the existing shell. Inspection never rewrites or sends it. */
export interface OfficeDraft { text: string; context: ProjectionContext }
export interface MetaCeoOfficeProps {
  projection: OfficeProjection;
  draft: OfficeDraft;
  onDraftChange: (text: string) => void;
  /** Only the existing signed-in Executive owner may supply a continuation. */
  nativeContinuation?: ReactNode;
  locale?: "en" | "zh-CN";
}

const OFFICE_ZH = {
  "Meta-CEO office": "Meta-CEO 办公室",
  "One company. One office.": "一家公司，一个办公室。",
  "Keep the whole company moving with intention.": "让整个公司有方向地前进。",
  "A clear view of direction, movement and the next accountable action.": "看清方向、进展，以及下一步由谁负责。",
  "Read + preview only": "仅供阅读和预览",
  "Owner-qualified session": "经负责人验证的会话",
  "Continue the exact selected Executive session": "继续当前已验证的 Executive 会话",
  "Native continuation uses the existing Executive owner. Sending confirms only the original operation receipt, not a worker result or acceptance.": "原有 Executive 负责人处理会话继续。发送回执只证明原操作已提交，不代表工作结果或验收。",
  "Current direction": "当前方向",
  "Source unavailable": "来源不可用",
  "The adopted direction has not been supplied by its owner.": "负责人尚未提供已采纳的方向。",
  "Reconcile the original operation. Resend, failover and target change remain held.": "请核对原操作。重新发送、切换通道和更改目标仍暂停。",
  "Meta-CEO answer": "Meta-CEO 答复",
  "The next accountable move": "下一步负责行动",
  "Moving with Meta-CEO": "与 Meta-CEO 一同推进",
  "Supplied mission view": "已提供的任务视图",
  "Work details are unavailable. Mission coverage and accountable owners are reported below.": "工作明细不可用。下方列出任务覆盖范围和负责人。",
  "No mission lanes were supplied. This is not a company-wide zero.": "尚未提供任务分支。这不代表全公司没有工作。",
  "Company total is not established.": "全公司总量尚未确认。",
  "Needs you": "需要你处理",
  "Returns, critical path and journal": "返回结果、关键路径和日志",
  "Returns to review": "待查看的返回结果",
  "A return is not acceptance.": "返回结果不等于验收通过。",
  "Critical path": "关键路径",
  "The critical path is unavailable. The owner’s next action remains visible.": "关键路径不可用。仍可查看负责人给出的下一步。",
  "Next accountable owner": "下一步负责人",
  "Next action": "下一步",
  "Return condition": "返回条件",
  "Not supplied by the current owner read": "当前负责人读取结果未提供",
  "What changed — and why": "变化与原因",
  "The durable journal is unavailable. A current snapshot does not establish a change history.": "持久日志不可用。当前快照不能证明变化历史。",
  "Agent OS retains decisions, discoveries and handoffs.": "Agent OS 保留决策、发现和交接记录。",
  "Delivery, effect and acceptance receipts": "交付、效果与验收回执",
  "Independent receipts": "独立回执",
  "Source qualification": "来源资格",
  "Review sources": "查看来源",
  "Source evidence": "来源证据",
  "Exact source provenance": "确切的来源信息",
  "Owner evidence and missingness": "负责人证据与缺失项",
  "Close sources": "关闭来源",
  "Direction intake": "方向草稿",
  "Direction to Meta-CEO": "给 Meta-CEO 的方向",
  "Keep the highest-value safe next step moving.": "推进价值最高且安全的下一步。",
  "Review direction preview": "查看方向预览",
  "Direction preview": "方向预览",
  "Frozen direction preview": "已固定的方向预览",
  "Content permission · NOT_PROJECTED. Command permission · NOT_PROJECTED.": "内容权限 · NOT_PROJECTED。命令权限 · NOT_PROJECTED。",
  "Inspecting this preview supplies no authorization. Submission requires the canonical command owner.": "查看预览不会授予权限。提交仍须通过原有命令负责人。",
  "Close preview": "关闭预览",
  "execution state unknown": "执行状态未知",
  "The current operating answer is not yet available.": "当前运行答复尚不可用。",
  "A qualified owner read is needed before an accountable next action can be stated.": "需取得合格的负责人读取结果，才能给出下一步负责行动。",
  "Source-backed summary of the selected project.": "基于来源的所选项目摘要。",
  "Currentness is not established. Retained facts keep their source qualification.": "当前性尚未确认。保留事实仍遵循各自的来源资格。",
  "not established": "尚未确认",
  "Role unknown": "角色未知",
  "not supplied": "未提供",
  "Mission lanes are unavailable.": "任务分支不可用。",
  "The owner has requested Chairman attention.": "负责人已请求主席关注。",
  "Chairman attention is not established.": "尚未确认需要主席关注。",
  "Missing attention data does not mean there are no decisions. Routine work remains with its accountable owner.": "缺少关注数据不代表没有待决事项。日常工作仍由相应负责人处理。",
  "Content is withheld or outside the bounded response.": "内容已隐藏或超出受限响应范围。",
  "No exactly associated return has been qualified for this view.": "此视图尚无通过资格验证且精确关联的返回结果。",
  "Not supplied": "未提供",
  "Project not selected": "未选择项目",
  "Root not selected": "未选择根任务",
  "Ref unavailable": "引用不可用",
  "unknown": "未知",
  "time unknown": "时间未知",
  "Owner read supplied": "负责人读取结果已提供",
  "Preview only · no message, Job, session, acceptance or deployment.": "仅为预览 · 不产生消息、Job、会话、验收或部署。",
  "A draft is retained for another identity or session. Return to that exact context to continue it.": "草稿属于另一个身份或会话。请回到该确切上下文继续。",
  "Project unavailable": "项目不可用",
  "Root unavailable": "根任务不可用",
  "Session unavailable": "会话不可用",
  "Coverage": "覆盖范围",
  "total": "总量",
  "Owner": "负责人",
  "Acceptance": "验收",
  "revision": "版本",
  "Control Room document digest · ": "Control Room 文档摘要 · ",
  "Locally acquired ": "本地获取于 ",
  "Observed ": "观察于 ",
  "Binding generation": "绑定代次",
  "Mission": "任务",
  "Projects": "项目",
  "Return": "返回结果",
  "Conversation": "对话"
} as const;

function SourceBadge({ source }: { source: SourceClaim }) {
  return <span className="office-state" data-state={source.state}>{source.state}</span>;
}

export function MetaCeoOffice({
  projection, draft, onDraftChange, nativeContinuation, locale = "en",
}: MetaCeoOfficeProps) {
  const t = (en: keyof typeof OFFICE_ZH): string => locale === "zh-CN" ? OFFICE_ZH[en] : en;
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [preview, setPreview] = useState<DirectionPreview | null>(null);
  const previewButton = useRef<HTMLButtonElement>(null);
  const sourcesButton = useRef<HTMLButtonElement>(null);
  const previewPanel = useRef<HTMLElement>(null);
  const sourcesPanel = useRef<HTMLElement>(null);
  const previewPanelId = useId();
  const sourcesPanelId = useId();
  const mission = projection.mission.value;
  const current = projection.mission.source.state === "CURRENT";
  const needsChairman = current && mission?.principal.owed_turn?.seat === "chairman" &&
    mission.principal.owed_turn.source_refs.length > 0 &&
    mission.principal.owed_turn.source_refs.every(ref =>
      !!ref.owner && !!ref.ref && !!ref.observed_at && ref.freshness === "current");
  const title = mission?.program.title ?? mission?.program.work_ref;
  const unknownEffect = projection.receipts.effect === "EFFECT_UNKNOWN";
  const draftAssociated = draft.context.authGeneration === projection.context.authGeneration && sameTarget(draft.context, projection.context);
  const visiblePreview = preview && previewIsCurrent(preview, projection.context) ? preview : null;
  useEffect(() => {
    if (sourcesOpen) sourcesPanel.current?.focus();
  }, [sourcesOpen]);
  useEffect(() => {
    // Only a Review action creates a new preview; revalidation must not steal focus.
    if (preview) previewPanel.current?.focus();
  }, [preview]);
  const sources = [
    ["Mission", projection.mission], ["Projects", projection.programs],
    ["Return", projection.result], ["Conversation", projection.conversation],
  ] as const;
  const closePreview = () => {
    setPreview(null);
    if (previewButton.current?.isConnected) previewButton.current.focus();
  };
  const closeSources = () => {
    setSourcesOpen(false);
    if (sourcesButton.current?.isConnected) sourcesButton.current.focus();
  };

  const nativeSessionQualified = nativeContinuation != null &&
    projection.mission.source.state === "CURRENT" &&
    projection.context.sessionRef !== null &&
    projection.context.bindingGeneration !== null;
  return <section className="meta-ceo-office" aria-label={t("Meta-CEO office")}>
    <header className="office-heading">
      <div><p className="office-eyebrow">{t("One company. One office.")}</p>
        <h1>{t("Keep the whole company moving with intention.")}</h1>
        <p>{t("A clear view of direction, movement and the next accountable action.")}</p></div>
      <div className="office-heading-aside"><div className="office-art" aria-hidden="true" />
        <span className="office-state" data-state={nativeSessionQualified ? "CURRENT" : "UNKNOWN"}>
          {t(nativeSessionQualified ? "Owner-qualified session" : "Read + preview only")}
        </span></div>
    </header>

    <section className="office-direction" aria-label={t("Current direction")}>
      <div><p className="office-eyebrow">{t("Current direction")}</p><span className="office-muted">{t("Source unavailable")}</span></div>
      <p>{t("The adopted direction has not been supplied by its owner.")}</p>
    </section>

    {unknownEffect && <div className="office-effect-alert" role="alert">
      <strong>EFFECT_UNKNOWN</strong><p>{t("Reconcile the original operation. Resend, failover and target change remain held.")}</p>
    </div>}
    {nativeSessionQualified && <section className="office-panel office-native-session"
      aria-label={t("Continue the exact selected Executive session")}>
      <h2>{t("Continue the exact selected Executive session")}</h2>
      <p className="office-muted">
        {t("Native continuation uses the existing Executive owner. Sending confirms only the original operation receipt, not a worker result or acceptance.")}
      </p>
      {nativeContinuation}
    </section>}

    <details className="fi-disclosure">
      <summary>{locale === "zh-CN" ? "子代理 Fabric · 查看执行内部状态" : "Subagent Fabric · inspect execution"}</summary>
    <AdmittedPlanInspector
      key={`plan:${projection.context.authGeneration}`}
      selection={mission?.program?.work_ref && mission?.mission?.root_job_id
        ? { work_ref: mission.program.work_ref, root_job_id: mission.mission.root_job_id } : null}
      read={typeof window !== "undefined" && window.MastermindMissionHost?.readAdmittedPlan
        ? readOfficePlan : undefined}
      readActivity={typeof window !== "undefined" && window.MastermindMissionHost?.readRetainedActivity
        ? readOfficeActivity : undefined}
      sourceGeneration={typeof window !== "undefined" && window.MastermindMissionHost?.invalidationGeneration
        ? officePlanGeneration : undefined}
      canRead={typeof window !== "undefined" && window.MastermindMissionHost?.auth
        ? officePlanPermission : undefined}
      locale={locale}
      mission={mission}
      missionSourceState={projection.mission.source.state}
      missionObservedAt={projection.mission.source.observed_at}
    />
    <FabricMissionInspector
      key={JSON.stringify([projection.context.authGeneration, projection.context.selection])}
      mission={mission} locale={locale}
    />
    <AttendedFabricInspector
      key={`attended:${projection.context.authGeneration}`}
      host={typeof window === "undefined" ? undefined : window.MastermindMissionHost}
      locale={locale}
    />
    </details>

    <div className="office-top-grid">
      <section className="office-panel office-answer" aria-label={t("Meta-CEO answer")}>
        <div className="office-section-label"><p className="office-eyebrow">{t("The next accountable move")}</p><SourceBadge source={projection.mission.source} /></div>
        <h2>{mission ? `${title}: ${mission.execution.state ?? t("execution state unknown")}.` : t("The current operating answer is not yet available.")}</h2>
        <p>{mission?.program.next_action ?? t("A qualified owner read is needed before an accountable next action can be stated.")}</p>
        <p className="office-muted">{current ? t("Source-backed summary of the selected project.") : t("Currentness is not established. Retained facts keep their source qualification.")}</p>
        <section className="office-movement" aria-labelledby="office-moving-title">
        <div className="office-section-label"><h2 id="office-moving-title">{t("Moving with Meta-CEO")}</h2><span className="office-muted">{t("Supplied mission view")}</span></div>
        <p>{t("Work details are unavailable. Mission coverage and accountable owners are reported below.")}</p>
        {mission ? <>
          <p className="office-muted">{t("Coverage")} · {mission.children.coverage} · {t("total")} {mission.children.total_count ?? t("not established")}</p>
          <ul className="office-lanes">{mission.children.items.map(child => <li key={child.job_id}>
            <div><strong>{child.job_id}</strong><p>{child.orchestration_role ?? t("Role unknown")} · {t("Owner")} {child.worker_id ?? t("not supplied")}</p></div>
            <span>{child.status ?? "UNKNOWN"}</span>
          </li>)}</ul>
          {mission.children.items.length === 0 && <p>{t("No mission lanes were supplied. This is not a company-wide zero.")}</p>}
        </> : <p className="office-empty">{t("Mission lanes are unavailable.")}</p>}
        <p className="office-muted">{t("Company total is not established.")}</p>
        </section>
      </section>
      <section className={`office-panel office-attention${needsChairman ? " has-attention" : ""}`} aria-labelledby="office-attention-title">
        <p className="office-eyebrow">{t("Needs you")}</p>
        <h2 id="office-attention-title">{needsChairman ? t("The owner has requested Chairman attention.") : t("Chairman attention is not established.")}</h2>
        <p>{needsChairman ? mission!.principal.owed_turn!.reason : t("Missing attention data does not mean there are no decisions. Routine work remains with its accountable owner.")}</p>
        {needsChairman && <p className="office-ref">{mission!.principal.owed_turn!.source_refs.map(ref => `${ref.owner} · ${ref.ref} · ${ref.observed_at}`).join("; ")}</p>}
      </section>
    </div>

    <details className="office-context">
      <summary>{t("Returns, critical path and journal")}</summary>
      <div className="office-main-grid">
      <section className="office-panel" aria-labelledby="office-returns-title">
        <div className="office-section-label"><h2 id="office-returns-title">{t("Returns to review")}</h2><SourceBadge source={projection.result.source} /></div>
        <p>{t("A return is not acceptance.")}</p>
        {projection.result.value?.result ? <>
          <h3>{projection.result.value.selection.job_id}</h3>
          <p>{projection.result.value.result.content?.summary ?? t("Content is withheld or outside the bounded response.")}</p>
          <p className="office-ref">{projection.result.value.selection.attempt_id} · {projection.result.value.selection.result_envelope_digest}</p>
          <p>{t("Acceptance")} · {projection.result.value.result.acceptance}</p>
        </> : <p className="office-empty">{t("No exactly associated return has been qualified for this view.")}</p>}
      </section>
      <section className="office-panel" aria-labelledby="office-path-title">
        <h2 id="office-path-title">{t("Critical path")}</h2>
        <p>{t("The critical path is unavailable. The owner’s next action remains visible.")}</p>
        <dl className="office-next"><dt>{t("Next accountable owner")}</dt><dd>{mission?.principal.accountable_seat ?? t("Not supplied")}</dd>
          <dt>{t("Next action")}</dt><dd>{mission?.program.next_action ?? t("Not supplied")}</dd>
          <dt>{t("Return condition")}</dt><dd>{t("Not supplied by the current owner read")}</dd></dl>
      </section>
      <section className="office-panel" aria-labelledby="office-journal-title">
        <h2 id="office-journal-title">{t("What changed — and why")}</h2>
        <p>{t("The durable journal is unavailable. A current snapshot does not establish a change history.")}</p>
        <p className="office-ref">{projection.context.selection?.workRef ?? t("Project not selected")} · {projection.context.selection?.rootJobId ?? t("Root not selected")}</p>
        <p className="office-muted">{t("Agent OS retains decisions, discoveries and handoffs.")}</p>
      </section>
      </div>
    </details>

    <details className="office-context">
      <summary>{t("Delivery, effect and acceptance receipts")}</summary>
      <section className="office-receipts" aria-label={t("Independent receipts")}>
      {Object.entries(projection.receipts).map(([name, value]) => <div key={name}><p className="office-eyebrow">{name}</p><strong>{value ?? "NOT_PROJECTED"}</strong></div>)}
      </section>
    </details>
    <section className="office-sources" aria-label={t("Source qualification")}>
      {sources.map(([name, read]) => <div key={name}><span>{t(name)}</span><SourceBadge source={read.source} /><span className="office-muted">{read.source.coverage}</span></div>)}
      <button ref={sourcesButton} type="button" aria-controls={sourcesPanelId} aria-expanded={sourcesOpen} onClick={() => sourcesOpen ? closeSources() : setSourcesOpen(true)}>{t("Review sources")}</button>
    </section>
    {sourcesOpen && <aside ref={sourcesPanel} id={sourcesPanelId} tabIndex={-1} className="office-panel office-evidence" aria-label={t("Source evidence")} onKeyDown={event => { if (event.key === "Escape") closeSources(); }}>
      <h2>{t("Exact source provenance")}</h2>
      {sources.map(([name, read]) => <div key={name}><h3>{t(name)} · {read.source.owner}</h3>
        <p className="office-ref">{read.source.ref_kind === "CONTROL_ROOM_DOCUMENT_DIGEST" ? t("Control Room document digest · ") : ""}{read.source.ref ?? t("Ref unavailable")} · {t("revision")} {read.source.revision ?? t("unknown")}</p>
        <p>{read.source.observed_at_kind === "LOCAL_ACQUISITION" ? t("Locally acquired ") : t("Observed ")}{read.source.observed_at ?? t("time unknown")} · {read.reason ?? t("Owner read supplied")}</p></div>)}
      {mission && <details><summary>{t("Owner evidence and missingness")}</summary><pre>{JSON.stringify({
        program: mission.program.evidence, principal: mission.principal.evidence,
        execution: mission.execution.evidence, transport: mission.transport.evidence,
        review: mission.review.evidence, acceptance: mission.acceptance.evidence,
        missingness: mission.missingness, degraded: mission.degraded,
      }, null, 2)}</pre></details>}
      <button type="button" onClick={closeSources}>{t("Close sources")}</button>
    </aside>}

    <section className="office-composer" aria-label={t("Direction intake")}>
      <div><label className="office-eyebrow" htmlFor="office-direction">{t("Direction to Meta-CEO")}</label>
        <textarea id="office-direction" rows={2} value={draftAssociated ? draft.text : ""}
          disabled={!draftAssociated} onChange={event => onDraftChange(event.target.value)}
          placeholder={t("Keep the highest-value safe next step moving.")} />
        <p className="office-muted">{draftAssociated ? t("Preview only · no message, Job, session, acceptance or deployment.") : t("A draft is retained for another identity or session. Return to that exact context to continue it.")}</p>
      </div>
      <button ref={previewButton} className="office-primary" type="button" disabled={!draftAssociated || !draft.text.trim()}
        aria-controls={previewPanelId} aria-expanded={!!visiblePreview}
        onClick={() => setPreview(createDirectionPreview(projection, draft.text))}>{t("Review direction preview")}</button>
    </section>
    {visiblePreview && <section ref={previewPanel} id={previewPanelId} tabIndex={-1} className="office-panel office-preview" aria-label={t("Direction preview")} onKeyDown={event => { if (event.key === "Escape") closePreview(); }}>
      <div className="office-section-label"><h2>{t("Frozen direction preview")}</h2><span className="office-state">EFFECT_NONE</span></div>
      <p>{visiblePreview.draft}</p>
      <p className="office-ref">{visiblePreview.context.selection?.workRef ?? t("Project unavailable")} · {visiblePreview.context.selection?.rootJobId ?? t("Root unavailable")} · {visiblePreview.context.sessionRef ?? t("Session unavailable")}</p>
      <p>{t("Binding generation")} · {String(visiblePreview.context.bindingGeneration ?? t("unknown"))}</p>
      <p>{t("Content permission · NOT_PROJECTED. Command permission · NOT_PROJECTED.")}</p>
      <p>{t("Inspecting this preview supplies no authorization. Submission requires the canonical command owner.")}</p>
      <button type="button" onClick={closePreview}>{t("Close preview")}</button>
    </section>}
  </section>;
}
