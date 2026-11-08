import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  createDirectionPreview, previewIsCurrent, type DirectionPreview, type OfficeLaunchOutcome,
} from "./preview";
import { ProgrammeDirection, type ProgrammeDirectionProps } from "../direction/ProgrammeDirection";
import { OfficeWorkRead, type OfficeWorkReadState } from "./OfficeWorkRead";
import { sameTarget, type OfficeProjection, type ProjectionContext, type SourceClaim } from "./projection";
import "./office.css";
import { ByokRolesPanel } from "./ByokRolesPanel";
import type { ByokRoleView } from "./byok-role-view";
import { registerUnsavedNavigationHold } from "../auth-navigation-guard";
import { FabricMissionInspector } from "../fabric/FabricMissionInspector";
import type { ResultSelection } from "../result";
import { AttendedFabricWorkspace } from "../fabric/AttendedFabricWorkspace";
import { AdmittedPlanInspector } from "../planning/AdmittedPlanInspector";
import type { PlanSelection } from "../planning/admitted-plan";
import type { ActivitySelection } from "../planning/retained-activity";
import { OrganizationWorkspace, type OrganizationObservation } from "../organization/OrganizationWorkspace";

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
  /** Current presentation from the existing authenticated BYOK read owner. */
  byokObservation?: ByokRoleView;
  /** Optional owner-qualified Hermes read; no browser-side team lookup or enrollment. */
  organizationObservation?: OrganizationObservation;
  canRefreshByok?: boolean;
  onRefreshByok?: () => void;
  /** Existing canonical Agent OS reader; authored objectives never confer adoption. */
  programmeDirection?: Omit<ProgrammeDirectionProps, "locale">;
  /** Existing independently qualified project catalogue; navigation DATA only. */
  selectedProject?: { title: string; nextAction: string | null; onOpen: () => void } | null;
  onOpenProjects?: () => void;
  /** Existing accepted Direction owner node; no authority is derived here. */
  acceptedDirection?: ReactNode;
  /** Already acquired fixed Work read; never a company-total inference. */
  workRead?: OfficeWorkReadState;
  onInspectWork?: () => void;
  /** Existing explicit selected-project journal reader, not company history. */
  projectJournal?: ReactNode;
  companyPriorities?: ReactNode;
  draft: OfficeDraft;
  onDraftChange: (text: string) => void;
  /** Only the existing signed-in Executive owner may supply a continuation. */
  nativeContinuation?: ReactNode;
  /** Reuse App's exact Result owner reader; this component never acquires content. */
  onInspectWorkerResult?: (selection: ResultSelection) => void;
  /**
   * Optional navigation handoff for the actually selected project. Selection
   * data is navigation input only: the explicit View project gesture is the
   * sole caller, and the control is enabled only while the selection matches
   * the actual mission program and root. It never sends or prepares anything.
   */
  onOpenProject?: (selection: { workRef: string; rootJobId: string }) => void;
  /**
   * The existing launch owner. Supplied only when the actual launch binding
   * can offer a handoff. The request is effect-free: it neither prepares nor
   * submits, and this component keeps the Office draft either way.
   */
  onStartNewWork?: (preview: DirectionPreview) => OfficeLaunchOutcome;
  locale?: "en" | "zh-CN";
}

const OFFICE_ZH = {
  "Meta-CEO office": "Meta-CEO 办公室",
  "Company context": "公司上下文",
  "Draft preview": "草稿预览",
  "This is a review of your unsent draft. No request has been sent from this preview.": "这是未发送草稿的预览。此预览尚未发送任何请求。",
  "This view does not establish whether a decision needs you. You can inspect the project’s source records.": "此视图尚无法确认是否有决策需要您处理。您可以查看项目来源记录。",
  "Choose project": "选择项目",
  "Select a project to view its direction and next step.": "选择项目，查看其方向与下一步。",
  "Project information is available. Work and conversation context have not been supplied here.": "可查看项目信息。此视图尚未提供工作与对话上下文。",
  "This direction is an unsent draft.": "这段方向仍是未发送的草稿。",
  "Authored project objective": "编写的项目目标",
  "Accepted direction and history": "已接受方向与历史",
  "Read the accepted direction for this project. Its authored objective is a separate source record.": "读取此项目已接受的方向。编写的项目目标是另一份来源记录。",
  "The original result needs checking.": "需要核对原操作的结果。",

  "Meta-CEO": "Meta-CEO",
  "Give direction or ask a question.": "给出方向，或提出问题。",
  "Decisions not yet known.": "决策情况尚未确认。",
  "Send unavailable": "发送不可用",
  "Sending is unavailable in this context. You can keep and review this draft.": "此处暂时无法发送。您仍可保留并预览草稿。",
  "View project": "查看项目",
  "Open project": "打开项目",
  "Project objective · authored": "项目目标 · 已编写",
  "This is the authored objective of the selected project from the existing Agent OS reader. It is project source, not accepted company direction. Reading it adopts nothing.": "这是所选项目在现有 Agent OS 读取器中的已编写目标。它是项目来源，不是已采纳的公司方向。阅读不会采纳任何内容。",
  "Authored objective not supplied.": "尚未提供已编写目标。",
  "Configuration": "配置",
  "Technical and source details": "技术与来源详情",
  "Execution state": "执行状态",
  "Movement and mission lanes": "进展与任务分支",
  "One company. One office.": "一家公司，一个办公室。",
  "Keep the whole company moving with intention.": "让整个公司有方向地前进。",
  "A clear view of direction, movement and the next accountable action.": "看清方向、进展，以及下一步由谁负责。",
  "Read + preview only": "仅供阅读和预览",
  "Owner-qualified session": "经负责人验证的会话",
  "Continue the exact selected Executive session": "继续当前已验证的 Executive 会话",
  "Native continuation uses the existing Executive owner. Sending confirms only the original operation receipt, not a worker result or acceptance.": "原有 Executive 负责人处理会话继续。发送回执只证明原操作已提交，不代表工作结果或验收。",
  "Current direction": "当前方向",
  "Refresh configuration": "刷新配置",
  "Source unavailable": "来源不可用",
  "The adopted direction has not been supplied by its owner.": "负责人尚未提供已采纳的方向。",
  "Reconcile the original operation. Resend, failover and target change remain held.": "请核对原操作。重新发送、切换通道和更改目标仍暂停。",
  "Meta-CEO answer": "Meta-CEO 答复",
  "The next accountable move": "下一步负责行动",
  "Moving with Meta-CEO": "与 Meta-CEO 一同推进",
  "Supplied mission view": "已提供的任务视图",
  "Work details are unavailable. Mission coverage and accountable owners are reported below.": "工作明细不可用。下方列出任务覆盖范围和负责人。",
  "Separate Work and selected Mission sources": "工作与所选任务的独立来源",
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
  "Conversation": "对话",
  "Start new work": "开始新工作",
  "This opens the existing launch form with this exact direction. Nothing is prepared or sent until you launch it there.": "这会用这段确切方向打开已有的启动表单。在那里启动之前，不会准备或发送任何内容。",
  "The existing launch form now holds this exact direction. Review the project and profile there, then launch.": "已有的启动表单现已填入这段确切方向。请在那里核对项目与执行方式，然后启动。",
  "This preview is no longer current. Review the direction again before starting new work.": "此预览已不再有效。请重新查看方向预览后再开始新工作。",
  "The existing launch owner cannot offer a handoff here. Your direction is kept.": "已有的启动负责人此处无法提供交接。您的方向已保留。",
  "This direction names another workstream than the configured launch. The handoff is refused so no other workstream is targeted.": "此方向指向的工作流与已配置的启动不同。为避免指向其他工作流，已拒绝交接。",
  "An unsent launch goal already exists. It is kept as it is; resolve it before starting new work.": "已存在未发送的启动目标。该目标原样保留；请先处理它再开始新工作。",
  "An original launch command is still held on its own pointer. Reconcile it before starting new work.": "原有启动命令仍在自己的指针上保持。请先完成核对再开始新工作。"
} as const;

function SourceBadge({ source }: { source: SourceClaim }) {
  return <span className="office-state" data-state={source.state}>{source.state}</span>;
}

export function MetaCeoOffice({
  projection, draft, onDraftChange, nativeContinuation, onInspectWorkerResult, programmeDirection,
  selectedProject, onOpenProjects, acceptedDirection, organizationObservation, workRead, onInspectWork, projectJournal, companyPriorities,
  onOpenProject, onStartNewWork, byokObservation = { state: "SOURCE_UNBOUND" },
  canRefreshByok = false, onRefreshByok, locale = "en",
}: MetaCeoOfficeProps) {
  const t = (en: keyof typeof OFFICE_ZH): string => locale === "zh-CN" ? OFFICE_ZH[en] : en;
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const [preview, setPreview] = useState<DirectionPreview | null>(null);
  const [launchOutcome, setLaunchOutcome] = useState<OfficeLaunchOutcome | null>(null);
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
  useEffect(() => registerUnsavedNavigationHold(() => draftAssociated && draft.text.length > 0),
    [draftAssociated, draft.text]);
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
    setLaunchOutcome(null);
    if (previewButton.current?.isConnected) previewButton.current.focus();
  };
  const closeSources = () => {
    setSourcesOpen(false);
    if (sourcesButton.current?.isConnected) sourcesButton.current.focus();
  };
  // The handoff request is effect-free: it asks the existing launch owner to
  // take this exact frozen direction. It prepares and submits nothing here,
  // and the Office draft is never cleared by it.
  const startNewWork = () => {
    if (!visiblePreview || !onStartNewWork) return;
    setLaunchOutcome(onStartNewWork(visiblePreview));
  };

  const nativeSessionQualified = nativeContinuation != null &&
    projection.mission.source.state === "CURRENT" &&
    projection.context.sessionRef !== null &&
    projection.context.bindingGeneration !== null;
  // Navigation data only: the explicit View project gesture below is the sole
  // caller of onOpenProject, and only while the selection matches the actual
  // mission program and root.
  const selection = projection.context.selection;
  const missionAligned = !!selection && !!mission &&
    mission.program.work_ref === selection.workRef &&
    mission.mission.root_job_id === selection.rootJobId;
  return <section className="meta-ceo-office" lang={locale} aria-label={t("Meta-CEO office")}>
    <header className="office-heading">
      <div><p className="office-eyebrow">{t("Company context")}</p>
        <h1>{t("Meta-CEO")}</h1>
        <p>{t("Give direction or ask a question.")}</p></div>
      {nativeSessionQualified && <div className="office-heading-aside">
        <span className="office-state" data-state={nativeSessionQualified ? "CURRENT" : "UNKNOWN"}>
          {t(nativeSessionQualified ? "Owner-qualified session" : "Read + preview only")}
        </span></div>}
    </header>

    {unknownEffect && <div className="office-effect-alert" role="alert">
      <strong>{t("The original result needs checking.")}</strong><p>{t("Reconcile the original operation. Resend, failover and target change remain held.")}</p>
    </div>}

    <div className="office-shell">
      <div className="office-main">
        <section className="office-panel office-answer" aria-label={t("Meta-CEO answer")}>
          <p className="office-eyebrow">{t("The next accountable move")}</p>
          {mission || selectedProject ? <>
            <h2>{title ?? selectedProject?.title ?? t("Project unavailable")}</h2>
            <p className="office-next-action">{(mission ? mission.program.next_action : selectedProject?.nextAction) ??
              t("A qualified owner read is needed before an accountable next action can be stated.")}</p>
          </> : <h2>{t("The current operating answer is not yet available.")}</h2>}
          {!mission && !selectedProject && <p>{t("Select a project to view its direction and next step.")}</p>}
          <p className="office-muted">{current
            ? t("Source-backed summary of the selected project.")
            : selectedProject && !mission ? t("Project information is available. Work and conversation context have not been supplied here.")
            : t("Currentness is not established. Retained facts keep their source qualification.")}</p>
          {selectedProject ? <div className="office-answer-actions"><button type="button" onClick={selectedProject.onOpen}>{t("View project")}</button></div> : !mission && onOpenProjects ? <div className="office-answer-actions"><button type="button" onClick={onOpenProjects}>{t("Choose project")}</button></div> : onOpenProject && <div className="office-answer-actions">
            <button type="button" disabled={!missionAligned}
              onClick={() => onOpenProject({ workRef: selection!.workRef, rootJobId: selection!.rootJobId })}>
              {t("View project")}
            </button>
          </div>}
        </section>

        <section className="office-composer" aria-label={t("Direction intake")}>
          <div><label className="office-eyebrow" htmlFor="office-direction">{t("Direction to Meta-CEO")}</label>
            <textarea id="office-direction" rows={2} value={draftAssociated ? draft.text : ""}
              disabled={!draftAssociated} onChange={event => onDraftChange(event.target.value)}
              placeholder={t("Keep the highest-value safe next step moving.")} />
            <p className="office-muted">{draftAssociated ? t("This direction is an unsent draft.") : t("A draft is retained for another identity or session. Return to that exact context to continue it.")}</p>
          </div>
          <div className="office-composer-actions"><button ref={previewButton} className="office-primary" type="button" disabled={!draftAssociated || !draft.text.trim()}
            aria-controls={previewPanelId} aria-expanded={!!visiblePreview}
            onClick={() => { setLaunchOutcome(null); setPreview(createDirectionPreview(projection, draft.text)); }}>{t("Review direction preview")}</button>
          {!nativeSessionQualified && <button type="button" disabled>{t("Send unavailable")}</button>}</div>
          {!nativeSessionQualified && <p className="office-muted">{t("Sending is unavailable in this context. You can keep and review this draft.")}</p>}
        </section>
        {visiblePreview && <section ref={previewPanel} id={previewPanelId} tabIndex={-1} className="office-panel office-preview" aria-label={t("Direction preview")} onKeyDown={event => { if (event.key === "Escape") closePreview(); }}>
          <div className="office-section-label"><h2>{t("Draft preview")}</h2></div>
          <p className="office-preview-draft">{visiblePreview.draft}</p>
          <p>{t("This is a review of your unsent draft. No request has been sent from this preview.")}</p>
          {onStartNewWork ? <>
            <p className="office-muted">{t("This opens the existing launch form with this exact direction. Nothing is prepared or sent until you launch it there.")}</p>
            <button type="button" className="office-primary" disabled={launchOutcome?.status === "OPENED"} onClick={startNewWork}>
              {t("Start new work")}
            </button>
          </> : null}
          {launchOutcome?.status === "OPENED" ? <p role="status" className="office-muted">
            {t("The existing launch form now holds this exact direction. Review the project and profile there, then launch.")}
          </p> : null}
          {launchOutcome?.status === "REFUSED" ? <p role="alert" className="office-muted">
            {launchOutcome.reason === "PREVIEW_NOT_CURRENT"
              ? t("This preview is no longer current. Review the direction again before starting new work.")
              : launchOutcome.reason === "LAUNCH_OWNER_UNAVAILABLE"
                ? t("The existing launch owner cannot offer a handoff here. Your direction is kept.")
                : launchOutcome.reason === "WORKSTREAM_MISMATCH"
                  ? t("This direction names another workstream than the configured launch. The handoff is refused so no other workstream is targeted.")
                  : launchOutcome.reason === "LAUNCH_GOAL_PRESERVED"
                    ? t("An unsent launch goal already exists. It is kept as it is; resolve it before starting new work.")
                    : t("An original launch command is still held on its own pointer. Reconcile it before starting new work.")}
          </p> : null}
          <details className="office-raw">
            <summary>{t("Technical and source details")}</summary>
            <p><span className="office-state">EFFECT_NONE</span></p>
            <p>{t("Inspecting this preview supplies no authorization. Submission requires the canonical command owner.")}</p>
            <p className="office-ref">{visiblePreview.context.selection?.workRef ?? t("Project unavailable")} · {visiblePreview.context.selection?.rootJobId ?? t("Root unavailable")} · {visiblePreview.context.sessionRef ?? t("Session unavailable")}</p>
            <p>{t("Binding generation")} · {String(visiblePreview.context.bindingGeneration ?? t("unknown"))}</p>
            <p>{t("Content permission · NOT_PROJECTED. Command permission · NOT_PROJECTED.")}</p>
          </details>
          <button type="button" onClick={closePreview}>{t("Close preview")}</button>
        </section>}
        {nativeSessionQualified ? <section className="office-panel office-native-session"
          aria-label={t("Continue the exact selected Executive session")}>
          <h2>{t("Continue the exact selected Executive session")}</h2>
          <p className="office-muted">
            {t("Native continuation uses the existing Executive owner. Sending confirms only the original operation receipt, not a worker result or acceptance.")}
          </p>
          {nativeContinuation}
        </section> : null}
      </div>

      <aside role="region" aria-labelledby="office-attention-title"
        className={`office-panel office-attention${needsChairman ? " has-attention" : ""}`}>
        <p className="office-eyebrow">{t("Needs you")}</p>
        <h2 id="office-attention-title">{needsChairman ? t("The owner has requested Chairman attention.") : t("Decisions not yet known.")}</h2>
        {needsChairman ? <p>{mission!.principal.owed_turn!.reason}</p>
          : <p className="office-muted">{t("This view does not establish whether a decision needs you. You can inspect the project’s source records.")}</p>}
        {needsChairman && <p className="office-ref">{mission!.principal.owed_turn!.source_refs.map(ref => `${ref.owner} · ${ref.ref} · ${ref.observed_at}`).join("; ")}</p>}
      </aside>
    </div>

    {companyPriorities}
    {acceptedDirection ? <details className="office-disclosure office-accepted-direction">
      <summary>{t("Accepted direction and history")}</summary>
      <p className="office-muted">{t("Read the accepted direction for this project. Its authored objective is a separate source record.")}</p>
      {acceptedDirection}
    </details> : null}
    <details className="office-disclosure office-organization">
      <summary>{locale === "zh-CN" ? "组织架构与目标关联" : "Organization and goal lineage"}</summary>
      <OrganizationWorkspace binding={projection.context} missionState={projection.mission.source.state}
        observation={organizationObservation} locale={locale} />
    </details>
    <details className="office-disclosure office-objective">
      <summary>{t("Authored project objective")}</summary>
      <p className="office-muted">{t("This is the authored objective of the selected project from the existing Agent OS reader. It is project source, not accepted company direction. Reading it adopts nothing.")}</p>
      {programmeDirection ? <ProgrammeDirection
        key={`objective:${projection.context.authGeneration}`}
        {...programmeDirection}
        locale={locale} /> : <p>{t("Source unavailable")} · {t("Authored objective not supplied.")}</p>}
    </details>


    <details className="office-disclosure office-config">
      <summary>{t("Configuration")}</summary>
      <ByokRolesPanel locale={locale} observation={byokObservation} />
      <div className="office-byok-refresh">
        <button type="button" disabled={!canRefreshByok || !onRefreshByok} onClick={onRefreshByok}>
          {t("Refresh configuration")}
        </button>
      </div>
    </details>

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
      onInspectResult={projection.mission.source.state === "CURRENT" ? onInspectWorkerResult : undefined}
    />
    <AttendedFabricWorkspace
      key={`attended:${projection.context.authGeneration}`}
      host={typeof window === "undefined" ? undefined : window.MastermindMissionHost}
      locale={locale}
    />
    </details>

    <details className="office-disclosure office-movement-d">
      <summary>{t("Movement and mission lanes")}</summary>
      <section className="office-movement" aria-labelledby="office-moving-title">
        <div className="office-section-label"><h2 id="office-moving-title">{t("Moving with Meta-CEO")}</h2><span className="office-muted">{workRead ? t("Separate Work and selected Mission sources") : t("Supplied mission view")}</span></div>
        {workRead ? <OfficeWorkRead state={workRead} locale={locale} onInspect={onInspectWork}/>
          : <p>{t("Work details are unavailable. Mission coverage and accountable owners are reported below.")}</p>}
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
    </details>

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
        {projectJournal ? <><p>{locale === "zh-CN" ? "所选项目日志；有界记录样本，不是全公司历史。" : "Selected-project journal: a bounded record sample, not company-wide history."}</p>{projectJournal}</>
          : <p>{t("The durable journal is unavailable. A current snapshot does not establish a change history.")}</p>}
        {!projectJournal && <p className="office-ref">{projection.context.selection?.workRef ?? t("Project not selected")} · {projection.context.selection?.rootJobId ?? t("Root not selected")}</p>}
        <p className="office-muted">{t("Agent OS retains decisions, discoveries and handoffs.")}</p>
      </section>
      </div>
    </details>

        <button ref={sourcesButton} type="button" aria-controls={sourcesPanelId} aria-expanded={sourcesOpen}
          onClick={() => { setTechnicalOpen(true); sourcesOpen ? closeSources() : setSourcesOpen(true); }}>{t("Review sources")}</button>

    <details className="office-disclosure office-technical" open={technicalOpen}
      onToggle={event => setTechnicalOpen((event.target as HTMLDetailsElement).open)}>
      <summary>{t("Technical and source details")}</summary>
      <p className="office-muted">{t("Execution state")} · {mission?.execution.state ?? t("execution state unknown")}</p>
      <details className="office-context">
        <summary>{t("Delivery, effect and acceptance receipts")}</summary>
        <section className="office-receipts" aria-label={t("Independent receipts")}>
        {Object.entries(projection.receipts).map(([name, value]) => <div key={name}><p className="office-eyebrow">{name}</p><strong>{value ?? "NOT_PROJECTED"}</strong></div>)}
        </section>
      </details>
      <section className="office-sources" aria-label={t("Source qualification")}>
        {sources.map(([name, read]) => <div key={name}><span>{t(name)}</span><SourceBadge source={read.source} /><span className="office-muted">{read.source.coverage}</span></div>)}

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
    </details>
  </section>;
}
