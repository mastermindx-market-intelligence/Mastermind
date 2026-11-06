import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { validProjectPlanSelection, type ProjectPlanRead, type ProjectPlanSelection } from "./project-plan";
import "./project-plan-panel.css";
import { ProjectPlanContinuity, selectedRecordedPlanProposal } from "./ProjectPlanContinuity";
import type { PlanAdoptionInspection } from "./plan-adoption-workspace";
import type { ProjectPlanLaunchInspection } from "./ProjectStartWork";

/**
 * Task-tab content for one canonical Agent OS project-plan read. The
 * integrating parent supplies the already-decoded, detached wire body through
 * `read`; this panel owns acquisition fencing and closed presentation only.
 * A canonical project plan is NOT an admitted execution plan: nothing here
 * requires a Job, asserts execution, or relabels authored record state as
 * adoption, acceptance or approval.
 */

/** The authenticated parent performs the sole raw-owner decode. */
export type ProjectPlanReader = (request: ProjectPlanSelection & { signal: AbortSignal }) => Promise<ProjectPlanRead>;
export interface ProjectPlanPanelProps {
  selection: ProjectPlanSelection | null;
  read?: ProjectPlanReader;
  /** Existing auth/source generation, not a new identity or permission authority. */
  sourceGeneration?: () => number;
  canRead?: () => boolean;
  locale?: "en" | "zh-CN";
  /** DATA hint only; chooses an actually captured proposal. */
  initialProposalId?: string|null;
  /** Compose a workspace from this same qualified read, without another cache or read. */
  renderWorkspace?: (view: {
    objective: string | null; panel: ReactNode; inspection: PlanAdoptionInspection | null;
    launchInspection: ProjectPlanLaunchInspection | null;
  }) => ReactNode;
}

// PR links may only derive from the fixed canonical repository and a positive
// PR number; anything else stays an inert reference.
const CANONICAL_REPOSITORY = "mastermindx-market-intelligence/macro";
const INITIAL_VISIBLE_WAVES = 8;

interface CopyEntry { en: string; zh: string }
const text = (entry: CopyEntry, chinese: boolean) => (chinese ? entry.zh : entry.en);

const COPY = {
  ariaLabel: { en: "Project plan", zh: "项目计划" },
  heading: { en: "Plan", zh: "计划" },
  subtitle: { en: "Recorded objective and delivery plan.",
    zh: "已记录的目标与推进计划。" },
  refresh: { en: "Refresh", zh: "刷新" },
  reading: { en: "Reading…", zh: "正在读取…" },
  noReader: { en: "This project’s recorded plan is unavailable here.",
    zh: "此处无法获取此项目已记录的计划。" },
  idle: { en: "Refresh to view this project’s recorded plan.",
    zh: "刷新以查看此项目已记录的计划。" },
  loading: { en: "Reading the project plan…", zh: "正在读取项目计划…" },
  failed: { en: "The project-plan read failed or was refused; nothing was inferred.",
    zh: "项目计划读取失败或被拒绝；未推断任何内容。" },
  unavailableLead: { en: "The project-plan source is unavailable for this read.",
    zh: "此次读取的项目计划来源不可用。" },
  statusLabel: { en: "Record status", zh: "记录状态" },
  ownerLabel: { en: "Owner", zh: "所有者" },
  nextActionLabel: { en: "Next action", zh: "下一步" },
  wavesLabel: { en: "Waves", zh: "波次" },
  emptyWaves: { en: "This record declares no waves. The record itself is available; that is not evidence that work is complete or that no work exists.",
    zh: "该记录未写明任何波次。记录本身可用；这不代表工作已完成或不存在工作。" },
  seeAll: { en: "See all", zh: "显示全部" },
  showFirst: { en: "Show first", zh: "仅显示前" },
  wavesSuffix: { en: "waves", zh: "个波次" },
  adoptionLabel: { en: "Adoption", zh: "采用状态" },
  adoptionUnavailable: { en: "This source does not declare plan adoption. Adoption and proposal history are unavailable in this read.",
    zh: "此来源未声明计划采用状态。此次读取无法提供采用或提案历史。" },
  adoptionRecorded: { en: "An adoption decision is recorded. The planning details below identify its exact baseline.",
    zh: "已记录采纳决定。下方规划详情列明其准确基线。" },
  authoredMatches: { en: "This recorded plan matches the adopted baseline content.",
    zh: "此记录的计划与已采纳基线内容一致。" },
  authoredDiffers: { en: "The recorded programme and adopted baseline contain different content. Review both before choosing a change.",
    zh: "已记录方案与已采纳基线的内容不同。选择变更前请查看两者。" },
  adoptionReadUnavailable: { en: "Adoption information is unavailable in this read. Recorded programme content remains available.",
    zh: "此次读取无法提供采纳信息，已记录的方案内容仍可查看。" },
  noAdoptedBaseline: { en: "No adopted baseline is recorded in the captured planning sources. Recorded proposals can be reviewed below.",
    zh: "已捕获的规划来源未记录已采纳基线，可在下方查看已记录的提案。" },
  historyLabel: { en: "Record revision history", zh: "记录修订历史" },
  historyNote: { en: "Recent changes to the source record. Adoption status is shown separately.",
    zh: "来源记录的近期修订。采用状态另行显示。" },
  currentRevision: { en: "displayed record content", zh: "当前显示的记录内容" },
  commitLabel: { en: "Commit", zh: "提交" },
  digestLabel: { en: "Content SHA-256", zh: "内容 SHA-256" },
  recordDigestLabel: { en: "Record content SHA-256", zh: "记录内容 SHA-256" },
  committedAtLabel: { en: "Recorded at", zh: "记录时间" },
  sourceLabel: { en: "Source details", zh: "来源详情" },
  sourceNote: { en: "The record and revision used for this view.",
    zh: "此视图使用的记录及其修订。" },
  repositoryLabel: { en: "Repository", zh: "仓库" },
  pathLabel: { en: "Path", zh: "路径" },
  footnote: { en: "Planning records describe plans and source decisions. Execution and product acceptance are reported separately.",
    zh: "规划记录说明计划与来源决定，执行情况及产品验收另行报告。" },
} satisfies Record<string, CopyEntry>;

const REASON_COPY: Record<string, CopyEntry> = {
  SOURCE_UNAVAILABLE: { en: "The source record is currently unreadable.", zh: "源记录当前不可读取。" },
  SOURCE_CHANGED: { en: "The source changed during this read. Refresh to read the current record.", zh: "读取期间来源已更改。请刷新以读取当前记录。" },
  RECORD_NOT_FOUND: { en: "The selected workstream record was not found.", zh: "所选工作流记录不存在。" },
  RECORD_INVALID: { en: "The source record is structurally invalid; nothing was projected.", zh: "源记录结构无效；未投影任何内容。" },
  CONTENT_OVER_BUDGET: { en: "The record exceeds the response budget and is not truncated here.", zh: "记录超出响应预算；此处不进行截断。" },
};

const HISTORY_UNAVAILABLE_COPY: Record<string, CopyEntry> = {
  NOT_SUPPLIED_BY_OWNER: { en: "The record owner did not supply revision history, so no record revisions are shown.",
    zh: "记录所有者未提供修订历史，因此不显示任何记录修订。" },
  SOURCE_UNAVAILABLE: { en: "The pinned source was unreadable, so record revision history could not be enumerated.",
    zh: "钉住的源不可读取，因此无法枚举记录修订历史。" },
};

interface WaveView { id: string; title: string; status: string; depends_on: string[]; next_action: string | null; prs: number[] }
interface RevisionView { commit: string; committed_at: string; content_sha256: string }
type PlanDetail = NonNullable<ProjectPlanRead["plan"]>;
type PlanSource = NonNullable<ProjectPlanRead["source"]>;

const validSelection = validProjectPlanSelection;

const prHref = (pr: number, repository: string): string | null =>
  repository === CANONICAL_REPOSITORY && Number.isSafeInteger(pr) && pr > 0
    ? `https://github.com/${CANONICAL_REPOSITORY}/pull/${pr}`
    : null;

function WaveItem({ wave, chinese, repository }: { wave: WaveView; chinese: boolean; repository: string }) {
  return <li className="mm-project-plan__wave">
    <div className="mm-project-plan__wave-head">
      <code>{wave.id}</code>
      <span className="mm-project-plan__wave-title">{wave.title}</span>
      <span className="mm-project-plan__wave-status">{wave.status}</span>
    </div>
    {wave.depends_on.length > 0 && <p className="mm-project-plan__wave-line">
      {chinese ? "依赖：" : "Depends on: "}{wave.depends_on.join(", ")}
    </p>}
    {wave.next_action !== null && <p className="mm-project-plan__wave-line">
      {chinese ? "下一步：" : "Next action: "}{wave.next_action}
    </p>}
    {wave.prs.length > 0 && <ul className="mm-project-plan__prs">
      {wave.prs.map((pr, index) => {
        const href = prHref(pr, repository);
        return <li key={`${pr}:${index}`}>{href !== null
          ? <a href={href} target="_blank" rel="noreferrer">#{pr}</a>
          : <code>#{pr}</code>}</li>;
      })}
    </ul>}
  </li>;
}

function RevisionHistory({ history, chinese }: { history: PlanDetail["version_history"]; chinese: boolean }) {
  if (history.state !== "AVAILABLE") {
    const reason = history.reason;
    const copy = HISTORY_UNAVAILABLE_COPY[reason];
    return <div className="mm-project-plan__history">
      <h3 className="mm-project-plan__section-title">{text(COPY.historyLabel, chinese)}</h3>
      <p className="mm-project-plan__note" role="status">
        {copy ? text(copy, chinese) : <code>{reason}</code>}
      </p>
    </div>;
  }
  if (history.kind !== "GIT_RECORD_REVISIONS") {
    // A typed deviation from the closed history contract is never relabelled
    // into invented version content.
    return <div className="mm-project-plan__history">
      <h3 className="mm-project-plan__section-title">{text(COPY.historyLabel, chinese)}</h3>
      <p className="mm-project-plan__note"><code>{history.kind}</code></p>
    </div>;
  }
  return <div className="mm-project-plan__history">
    <h3 className="mm-project-plan__section-title">{text(COPY.historyLabel, chinese)}</h3>
    <ol className="mm-project-plan__revisions">
      {history.revisions.map((revision: RevisionView, index) => <li key={revision.commit}>
        <details className="mm-project-plan__revision-details">
          <summary>
            <code>{revision.commit.slice(0, 10)}</code>
            <span className="mm-project-plan__revision-at">{revision.committed_at}</span>
            {index === 0 && <span className="mm-project-plan__revision-current">
              {text(COPY.currentRevision, chinese)}</span>}
          </summary>
          <dl className="mm-project-plan__detail-list">
            <div><dt>{text(COPY.commitLabel, chinese)}</dt><dd><code>{revision.commit}</code></dd></div>
            <div><dt>{text(COPY.recordDigestLabel, chinese)}</dt><dd><code>{revision.content_sha256}</code></dd></div>
            <div><dt>{text(COPY.committedAtLabel, chinese)}</dt><dd>{revision.committed_at}</dd></div>
          </dl>
        </details>
      </li>)}
    </ol>
    <p className="mm-project-plan__note">{text(COPY.historyNote, chinese)}</p>
  </div>;
}

function AvailablePlanBody({ plan, source, chinese, hasContinuity, continuity }: {
  plan: PlanDetail; source: PlanSource | null; chinese: boolean; hasContinuity: boolean; continuity?: ReactNode;
}) {
  const waves: WaveView[] = plan.waves;
  const [showAllWaves, setShowAllWaves] = useState(false);
  const repository = source?.repository ?? "";
  const visibleWaves = showAllWaves ? waves : waves.slice(0, INITIAL_VISIBLE_WAVES);
  return <>
    <div className="mm-project-plan__record">
      <h3 className="mm-project-plan__title">{plan.title}</h3>
      <p className="mm-project-plan__objective">{plan.objective}</p>
    <div className="mm-project-plan__adoption">
      <h3 className="mm-project-plan__section-title">{text(COPY.adoptionLabel, chinese)}</h3>
      {plan.adoption.state === "UNAVAILABLE"
        ? <p className="mm-project-plan__note" role="status">{text(plan.adoption.reason === "NOT_DECLARED"
          ? hasContinuity ? COPY.noAdoptedBaseline : COPY.adoptionUnavailable : COPY.adoptionReadUnavailable, chinese)}</p>
        : <><p className="mm-project-plan__note">{text(COPY.adoptionRecorded, chinese)}</p>
          <p className="mm-project-plan__note">{text(plan.adoption.matches_authored_record
            ? COPY.authoredMatches : COPY.authoredDiffers, chinese)}</p></>}
    </div>
      <dl className="mm-project-plan__facts">
        <div><dt>{text(COPY.statusLabel, chinese)}</dt><dd>{plan.status}</dd></div>
        <div><dt>{text(COPY.ownerLabel, chinese)}</dt><dd>{plan.owner}</dd></div>
        {plan.next_action !== null && <div>
          <dt>{text(COPY.nextActionLabel, chinese)}</dt><dd>{plan.next_action}</dd>
        </div>}
      </dl>
    </div>
    {continuity}
    <div className="mm-project-plan__waves-section">
      <h3 className="mm-project-plan__section-title">{text(COPY.wavesLabel, chinese)}</h3>
      {waves.length === 0
        ? <p className="mm-project-plan__note" role="status">{text(COPY.emptyWaves, chinese)}</p>
        : <ol className="mm-project-plan__waves">
            {visibleWaves.map(wave => <WaveItem key={wave.id} wave={wave} chinese={chinese} repository={repository} />)}
          </ol>}
      {waves.length > INITIAL_VISIBLE_WAVES && <button type="button" className="mm-project-plan__disclose"
        aria-expanded={showAllWaves} onClick={() => setShowAllWaves(value => !value)}>
        {showAllWaves
          ? `${text(COPY.showFirst, chinese)} ${INITIAL_VISIBLE_WAVES} ${text(COPY.wavesSuffix, chinese)}`
          : `${text(COPY.seeAll, chinese)} ${waves.length} ${text(COPY.wavesSuffix, chinese)}`}
      </button>}
    </div>
    <RevisionHistory history={plan.version_history} chinese={chinese} />
    {source !== null && <details className="mm-project-plan__source">
      <summary>{text(COPY.sourceLabel, chinese)}</summary>
      <p className="mm-project-plan__note">{text(COPY.sourceNote, chinese)}</p>
      <dl className="mm-project-plan__detail-list">
        <div><dt>{text(COPY.repositoryLabel, chinese)}</dt><dd><code>{source.repository}</code></dd></div>
        <div><dt>{text(COPY.commitLabel, chinese)}</dt><dd><code>{source.commit}</code></dd></div>
        <div><dt>{text(COPY.pathLabel, chinese)}</dt><dd><code>{source.path}</code></dd></div>
        <div><dt>{text(COPY.digestLabel, chinese)}</dt><dd><code>{source.content_sha256}</code></dd></div>
      </dl>
    </details>}
    <p className="mm-project-plan__footnote">{text(COPY.footnote, chinese)}</p>
  </>;
}

export function ProjectPlanPanel({
  selection, read, sourceGeneration, canRead, locale = "en", renderWorkspace, initialProposalId,
}: ProjectPlanPanelProps) {
  const chinese = locale === "zh-CN";
  const [document, setDocument] = useState<ProjectPlanRead | null>(null);
  const [documentGeneration, setDocumentGeneration] = useState<number | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "unavailable">("idle");
  const request = useRef<AbortController | null>(null);
  const requestSeq = useRef(0);
  const phase = useRef<"idle" | "loading" | "ready" | "unavailable">("idle");
  // Identity captured at publish time: content survives only while the very
  // same reader/generation/canRead facts and selection still hold.
  const fence = useRef<{ read: ProjectPlanReader | undefined;
    sourceGeneration: (() => number) | undefined; canRead: (() => boolean) | undefined;
    workRef: string } | null>(null);
  const autoWindow = useRef<{ ready: boolean; work: string | null } | null>(null);
  const selectedWork = selection?.work_ref ?? null;
  const [proposalHint,setProposalHint]=useState<string|null>(initialProposalId??null);
  useLayoutEffect(()=>setProposalHint(initialProposalId??null),[selectedWork,initialProposalId]);
  const currentOwner=useRef({read,sourceGeneration,canRead,selectedWork});
  currentOwner.current={read,sourceGeneration,canRead,selectedWork};
  const currentProposal=useRef<string|null>(null);
  const setPhase = (next: "idle" | "loading" | "ready" | "unavailable") => {
    phase.current = next;
    setState(next);
  };

  const acquire = (target: ProjectPlanSelection, reader: ProjectPlanReader,
      generation: () => number, granted: () => boolean) => {
    if (!granted()) { setPhase("idle"); return; }
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    const seq = ++requestSeq.current;
    const initialGeneration = generation();
    const windowLive = () => requestSeq.current === seq && !controller.signal.aborted;
    const current = () => windowLive() && granted() && generation() === initialGeneration;
    setDocument(null);
    setDocumentGeneration(null);
    fence.current = null;
    setPhase("loading");
    let pending: Promise<ProjectPlanRead>;
    try {
      pending = reader({ ...target, signal: controller.signal });
    } catch {
      if (current()) setPhase("unavailable");
      else if (windowLive()) setPhase("idle");
      request.current = null;
      return;
    }
    pending.then(body => {
      if (!current()) {
        // A stale response can never publish. Fall back to the idle prompt
        // instead of a stranded spinner when only the generation moved.
        if (windowLive()) setPhase("idle");
        return;
      }
      setDocument(body);
      setDocumentGeneration(initialGeneration);
      fence.current = { read: reader, sourceGeneration: generation, canRead: granted,
        workRef: target.work_ref };
      setPhase("ready");
    }).catch(() => {
      if (current()) setPhase("unavailable");
      else if (windowLive()) setPhase("idle");
    }).finally(() => {
      if (request.current === controller) request.current = null;
    });
  };

  const open = () => {
    if (phase.current === "loading") return;
    if (!validSelection(selection) || read === undefined ||
        sourceGeneration === undefined || canRead === undefined || !canRead()) {
      requestSeq.current += 1;
      request.current?.abort(); request.current = null;
      fence.current = null;
      setDocument(null); setDocumentGeneration(null); setPhase("idle");
      return;
    }
    acquire(selection, read, sourceGeneration, canRead);
  };

  const ready = validSelection(selection) && read !== undefined &&
    sourceGeneration !== undefined && canRead !== undefined && canRead();

  // Fencing: clear and abort on selection or reader change. A layout effect so
  // the clear lands before the auto-acquire effect in the same commit.
  useLayoutEffect(() => {
    requestSeq.current += 1;
    request.current?.abort();
    request.current = null;
    fence.current = null;
    setDocument(null);
    setDocumentGeneration(null);
    setPhase("idle");
    return () => {
      requestSeq.current += 1;
      request.current?.abort();
      request.current = null;
    };
  }, [selectedWork, read, sourceGeneration, canRead]);

  useLayoutEffect(() => {
    if (!ready) {
      // Revocation is irreversible for the old acquisition. A regrant — even
      // with the same numeric generation — must acquire freshly before any
      // old content reappears.
      requestSeq.current += 1;
      request.current?.abort();
      request.current = null;
      fence.current = null;
      setDocument(null);
      setDocumentGeneration(null);
      setPhase("idle");
    }
  }, [ready]);

  // One automatic acquisition per authorized mount/selection/regrant window.
  // Churn inside a settled window never refires: a refused read stays refused
  // until explicit Refresh, so no fetch loop can self-sustain.
  useLayoutEffect(() => {
    const work = ready && selection !== null ? selection.work_ref : null;
    const previous = autoWindow.current;
    autoWindow.current = { ready, work };
    if (!ready || work === null || selection === null || read === undefined ||
        sourceGeneration === undefined || canRead === undefined) return;
    const windowContinues = previous !== null && previous.ready && previous.work === work;
    if (windowContinues && (request.current !== null ||
        phase.current === "ready" || phase.current === "unavailable")) return;
    acquire(selection, read, sourceGeneration, canRead);
  }, [ready, selectedWork, read, sourceGeneration, canRead]);

  // Cached record content must disappear on the *same render* as viewer
  // revocation, reader replacement, generation rotation or selection change.
  let displayedPlan: ProjectPlanRead | null = null;
  if (ready && selection !== null && document !== null && documentGeneration !== null &&
      fence.current !== null && fence.current.read === read &&
      fence.current.sourceGeneration === sourceGeneration &&
      fence.current.canRead === canRead && fence.current.workRef === selectedWork &&
      document.selection.work_ref === selectedWork &&
      canRead() && sourceGeneration() === documentGeneration) {
    displayedPlan = document;
  }

  const originalMissing=!!initialProposalId&&displayedPlan?.availability==='AVAILABLE'&&
    (displayedPlan.schema!=='mastermind.workspace_project_plan.v2'||displayedPlan.continuity.proposals.state!=='AVAILABLE'||
      !displayedPlan.continuity.proposals.items.some(item=>'proposal_id' in item&&item.proposal_id===initialProposalId));
  const proposal=originalMissing?null:displayedPlan?.schema==='mastermind.workspace_project_plan.v2'&&displayedPlan.availability==='AVAILABLE'
    ?selectedRecordedPlanProposal(displayedPlan.continuity,proposalHint):null;
  currentProposal.current=proposal?.proposal_id??null;
  const capturedFence=fence.current;
  const proposalId=proposal?.proposal_id??null;
  const capturedRequest = requestSeq.current;
  // Project launch uses the same qualified read even when no proposal is selected.
  // Request identity also invalidates a captured inspection after unmount/refresh.
  const planInspectionCurrent = () => {
    const owner = currentOwner.current;
    return displayedPlan !== null && capturedFence !== null && fence.current === capturedFence &&
      requestSeq.current === capturedRequest && phase.current === "ready" &&
      owner.read === read && owner.sourceGeneration === sourceGeneration &&
      owner.canRead === canRead && owner.selectedWork === selectedWork &&
      canRead?.() === true && sourceGeneration?.() === documentGeneration;
  };
  const inspectionCurrent = () => planInspectionCurrent() && currentProposal.current === proposalId;
  const launchInspection: ProjectPlanLaunchInspection | null =
    displayedPlan?.availability === "AVAILABLE" && selection !== null
      ? { read: displayedPlan, selection: { work_ref: selection.work_ref }, isCurrent: planInspectionCurrent }
      : null;
  const inspection:PlanAdoptionInspection|null=displayedPlan!==null&&proposalId!==null&&selection!==null
    ?{read:displayedPlan,selection:{work_ref:selection.work_ref},proposalId,isCurrent:inspectionCurrent,canRead:inspectionCurrent}:null;
  const panel = <section className="mm-project-plan" aria-label={text(COPY.ariaLabel, chinese)}
    aria-busy={state === "loading"}>
    <div className="mm-project-plan__heading">
      <div>
        <h2>{text(COPY.heading, chinese)}</h2>
        <p className="mm-project-plan__subtitle">{text(COPY.subtitle, chinese)}</p>
      </div>
      <button type="button" className="mm-project-plan__refresh"
        onClick={() => { open(); }} disabled={!ready || state === "loading"}>
        {state === "loading" ? text(COPY.reading, chinese) : text(COPY.refresh, chinese)}
      </button>
    </div>
    {!ready && <p className="mm-project-plan__status" role="status">{text(COPY.noReader, chinese)}</p>}
    {ready && (state === "idle" || state === "ready" && displayedPlan === null) && <p className="mm-project-plan__status" role="status">{text(COPY.idle, chinese)}</p>}
    {ready && state === "loading" && <p className="mm-project-plan__status" role="status">{text(COPY.loading, chinese)}</p>}
    {ready && state === "unavailable" && <p className="mm-project-plan__status" role="status">{text(COPY.failed, chinese)}</p>}
    {displayedPlan !== null && displayedPlan.availability === "UNAVAILABLE" &&
      <div className="mm-project-plan__unavailable" role="status">
        <p>{text(COPY.unavailableLead, chinese)}</p>
        <ul className="mm-project-plan__reasons">
          {displayedPlan.reason_codes.map(code => REASON_COPY[code] !== undefined
            ? <li key={code}>{text(REASON_COPY[code], chinese)}</li> : null)}
        </ul>
        <details className="mm-project-plan__source">
          <summary>{text(COPY.sourceLabel, chinese)}</summary>
          <ul className="mm-project-plan__reasons">
            {displayedPlan.reason_codes.map(code => <li key={code}><code>{code}</code></li>)}
          </ul>
        </details>
      </div>}
    {displayedPlan !== null && displayedPlan.availability === "AVAILABLE" &&
      displayedPlan.plan !== null &&
      <div className="mm-project-plan__results"
        key={`${displayedPlan.selection.work_ref}:${documentGeneration}`}>
        <AvailablePlanBody plan={displayedPlan.plan} source={displayedPlan.source} chinese={chinese}
          hasContinuity={displayedPlan.schema === "mastermind.workspace_project_plan.v2"}
          continuity={displayedPlan.schema === "mastermind.workspace_project_plan.v2"
            ? originalMissing ? <p role="status">{chinese?"此次当前计划读取未提供此原始提案；未选择替代提案。":"This original proposal is not supplied by the current Plan read; no replacement was selected."}</p> : <ProjectPlanContinuity data={displayedPlan.continuity} locale={locale}
                selectedProposalId={proposalHint} onSelectedProposal={setProposalHint}/> : undefined} />
      </div>}
  </section>;
  return renderWorkspace ? renderWorkspace({
    objective: displayedPlan?.availability === "AVAILABLE" ? displayedPlan.plan?.objective ?? null : null,
    panel,
    inspection,
    launchInspection,
  }) : panel;
}
