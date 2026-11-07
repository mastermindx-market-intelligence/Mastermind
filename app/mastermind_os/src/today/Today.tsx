import type { ReactNode } from "react";
import { normalizeSelection } from "../mission";
import type { MissionSelection, ProgramCard } from "../mission";
import type { OfficeProjection, SourceClaim } from "../meta-ceo/projection";
import type { WorkDocument } from "../work";
import "./today.css";

export type TodayWorkState =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "DOCUMENT"; document: WorkDocument };

interface TodayProps {
  locale?: "en" | "zh-CN";
  projection: OfficeProjection;
  work: TodayWorkState;
  /** The existing qualified LaunchOrchestrator/controller slot; Today never sends. */
  composer: ReactNode;
  authenticationCue?: ReactNode;
  retainComposerWithAuth?: boolean;
  onOpenInbox: () => void;
  onOpenProjects: () => void;
  onOpenMission?: (selection: MissionSelection) => void;
}

const STRINGS = {
  en: {
    heroTitle: "What would you like done?",
    heroSubtitle:
      "Start something new, or continue an existing project.",
    composerLabel: "Direction",
    attentionEyebrow: "Selected task",
    attentionTitle: "Needs your decision",
    attentionRegion: "Decisions",
    teamTitle: "Your team owns the next step",
    nextOwner: "Next turn",
    teamNext: "The next step remains with its current owner.",
    attentionWhy: "Why this needs you",
    chairmanEyebrow: "Chairman request",
    attentionContext: "Selected task",
    associationUnavailable: "Association unavailable",
    nothingTitle: "Nothing needs your decision",
    nothingBody: "This applies to this task only. Other project decisions may still be open.",
    uncertaintyTitle: "Decisions",
    uncertaintyBody: "Decision information is unavailable right now.",
    uncertaintyNotClear: "Missing information doesn’t mean there are no decisions.",
    openInbox: "Open inbox",
    openProject: "Open project",
    attentionNote: "Open your inbox to review this request.",
    projectsEyebrow: "Programs",
    projectsTitle: "Your projects",
    viewAll: "View all",
    selectedProject: "Selected project",
    suppliedCount: (count: number) => `${count} ${count === 1 ? "project" : "projects"} supplied`,
    rootLabel: (root: string) => `Mission ${root}`,
    projectsUnavailable: "Projects are unavailable right now.",
    stateLabel: "Source",
    coverageLabel: "Coverage",
    provenance: "Source details",
    owner: "Owner",
    reference: "Reference",
    revision: "Revision",
    observed: "Observed",
    locallyAcquired: "Locally acquired",
    notSupplied: "Not supplied",
    workEyebrow: "Runtime work",
    workTitle: "Work",
    workDetails: "Work and source details",
    generatedAt: "Generated at",
    workExceptionScope: "Work source exception",
    selectedEffectScope: "Selected task effect",
    firstProjects: "Showing the first three supplied projects. View all for the full supplied list.",
    workPending: "Work details are not available yet.",
    workUnavailable: "Work details are unavailable for this task.",
    workRoot: "Selected mission root",
    lifecycleLabel: "Lifecycle",
    workQueueSupplied: (count: number) => `${count} work ${count === 1 ? "root" : "roots"} supplied`,
    workCompleteScope: "This is the full list supplied for this view. It is not a company-wide total.",
    workPartialScope: "Some work may be missing from this list. Missing items are unknown, not zero.",
    workRootAbsentComplete: "The selected mission's root is not present in the supplied work queue.",
    workRootAbsentPartial: "The selected mission's root is not attributed in the supplied scope.",
    workNoRoot: "Work status is unavailable until a task can be identified.",
    workEffectUnknown: "An action’s outcome is still unknown. Don’t send it again, send it elsewhere, or start a replacement.",
    receiptsSummary: "Delivery, pickup, start, effect, return, review and acceptance receipts",
    receiptsNote: "Delivery, pickup, start, effect, return, review and acceptance remain separate.",
    notProjected: "NOT_PROJECTED",
    retainedNote: "Saved information does not confirm the current state.",
    withheldNext: "Next step unavailable here",
    withheldNote: "This task’s details are not available in this view.",
  },
  "zh-CN": {
    heroTitle: "您想完成什么？",
    heroSubtitle: "开始一项新工作，或继续已有项目。",
    composerLabel: "方向",
    attentionEyebrow: "所选任务",
    attentionTitle: "需要您决策",
    attentionRegion: "决策",
    teamTitle: "团队负责下一步",
    nextOwner: "下一回合",
    teamNext: "下一步仍由当前负责人推进。",
    attentionWhy: "为何需要您",
    chairmanEyebrow: "董事长请求",
    attentionContext: "所选任务",
    associationUnavailable: "关联不可用",
    nothingTitle: "目前没有需要您决策的事项",
    nothingBody: "此结论仅适用于当前任务。其他项目事项仍可能需要决策。",
    uncertaintyTitle: "待决策事项",
    uncertaintyBody: "暂时无法获取待决策事项。",
    uncertaintyNotClear: "信息缺失不代表没有待决策事项。",
    openInbox: "打开收件箱",
    openProject: "打开项目",
    attentionNote: "在收件箱中查看这项请求。",
    projectsEyebrow: "项目群",
    projectsTitle: "你的项目",
    viewAll: "查看全部",
    selectedProject: "所选项目",
    suppliedCount: (count: number) => `${count} 个已提供项目`,
    rootLabel: (root: string) => `任务 ${root}`,
    projectsUnavailable: "暂时无法获取项目。",
    stateLabel: "来源",
    coverageLabel: "覆盖",
    provenance: "来源详情",
    owner: "所有者",
    reference: "引用",
    revision: "修订",
    observed: "观测时间",
    locallyAcquired: "本地获取时间",
    notSupplied: "未提供",
    workEyebrow: "运行时工作",
    workTitle: "工作",
    workDetails: "工作与来源详情",
    generatedAt: "生成时间",
    workExceptionScope: "工作来源异常",
    selectedEffectScope: "所选任务操作状态",
    firstProjects: "显示前三个已提供项目。查看全部以浏览完整的已提供列表。",
    workPending: "工作详情暂不可用。",
    workUnavailable: "此任务的工作详情不可用。",
    workRoot: "所选任务根",
    lifecycleLabel: "生命周期",
    workQueueSupplied: (count: number) => `已提供 ${count} 个工作根`,
    workCompleteScope: "这是此视图已提供的完整列表，并非全公司总量。",
    workPartialScope: "此列表可能缺少部分工作。未列出的工作数量未知，不代表为零。",
    workRootAbsentComplete: "所选任务的根不在提供的工作队列中。",
    workRootAbsentPartial: "所选任务的根未在提供的范围内归属。",
    workNoRoot: "尚未确定具体任务，暂时无法显示工作状态。",
    workEffectUnknown: "某项操作的结果仍不确定。请勿重发、改发到其他目标或创建替代操作。",
    receiptsSummary: "交付、拾取、开始、效果、返回、评审与验收回执",
    receiptsNote: "交付、拾取、开始、效果、返回、评审与验收保持独立。",
    notProjected: "NOT_PROJECTED",
    retainedNote: "已保存的信息不能确认当前状态。",
    withheldNext: "此处无法提供下一步",
    withheldNote: "此视图无法提供该任务的详情。",
  },
} as const;

type Strings = {
  [K in keyof typeof STRINGS.en]: typeof STRINGS.en[K] extends (...args: infer A) => string
    ? (...args: A) => string : string;
};

interface QualifiedPrograms {
  source: SourceClaim;
  cards: ProgramCard[];
}

function resolvedSelection(card: ProgramCard): MissionSelection | null {
  if (card.rootState !== "RESOLVED" || card.rootCandidates.length !== 1 || card.rootCandidates[0] !== card.rootJobId) return null;
  return normalizeSelection({ workRef: card.workRef, rootJobId: card.rootJobId });
}

/**
 * Programs are actionable on Today only from a CURRENT claim with provenance,
 * a single supplied collection and distinct work references — the same
 * qualification Projects applies. STALE stays retained history, never current.
 */
function qualifyPrograms(read: OfficeProjection["programs"]): QualifiedPrograms | null {
  const source = read.source;
  if (source.state !== "CURRENT") return null;
  const cards = read.value?.programs ?? null;
  if (!read.value || read.value.state === "UNAVAILABLE") return null;
  if (!source.ref || !source.revision || !source.observed_at) return null;
  if (!cards || new Set(cards.map(card => card.workRef)).size !== cards.length) return null;
  return { source, cards };
}

function Provenance({ source, summary, strings, reason }: {
  source: SourceClaim;
  summary: string;
  strings: Strings;
  reason?: string | null;
}) {
  if (source.state === "WITHHELD") return null;
  return <details className="today-provenance"><summary>{summary}</summary>
    <dl><dt>{strings.stateLabel}</dt><dd>{source.state}</dd>
      {reason && <><dt>{strings.reference}</dt><dd>{reason}</dd></>}
      <dt>{strings.owner}</dt><dd>{source.owner}</dd>
      <dt>{strings.reference}</dt><dd>{source.ref || strings.notSupplied}</dd>
      <dt>{strings.revision}</dt><dd>{source.revision || strings.notSupplied}</dd>
      <dt>{source.observed_at_kind === "LOCAL_ACQUISITION" ? strings.locallyAcquired : strings.observed}</dt>
      <dd>{source.observed_at || strings.notSupplied}</dd>
      <dt>{strings.coverageLabel}</dt><dd>{source.coverage}</dd></dl>
  </details>;
}

function StateChip({ source, strings }: { source: SourceClaim; strings: Strings }) {
  return <span className="today-state" data-state={source.state}>{strings.stateLabel} · {source.state}</span>;
}

/** The exact Inbox predicate: CURRENT mission, chairman owed turn, current owner receipts. */
function chairmanTurn(projection: OfficeProjection) {
  const read = projection.mission;
  const source = read.source;
  const mission = source.state === "CURRENT" ? read.value : null;
  const turn = mission?.principal.owed_turn ?? null;
  const referenced = !!turn?.source_refs.length && turn.source_refs.every(ref =>
    !!ref.owner && !!ref.ref && !!ref.observed_at && ref.freshness === "current");
  const knownSeat = turn?.seat && ["chairman", "ceo", "coo", "worker"].includes(turn.seat);
  const qualifiedTurn = source.state === "CURRENT" && mission && referenced && knownSeat ? turn : null;
  const owed = qualifiedTurn?.seat === "chairman" ? qualifiedTurn : null;
  // A turn that is present but not qualifiable (stale/missing receipts, unknown
  // seat) leaves attention unknown; it must never become an all-clear.
  const unqualifiedTurn = !!turn && !qualifiedTurn;
  const selection = projection.context.selection;
  const exactSelection = mission && selection &&
    mission.program.work_ref === selection.workRef &&
    mission.mission.root_job_id === selection.rootJobId &&
    !mission.mission.root_job_ambiguous &&
    mission.mission.runtime_root_state === "RESOLVED" ? selection : null;
  return { source, mission, owed, teamTurn: qualifiedTurn && !owed ? qualifiedTurn : null, unqualifiedTurn, exactSelection, reason: read.reason };
}

function Attention({ projection, strings, onOpenInbox, onOpenMission }: {
  projection: OfficeProjection;
  strings: Strings;
  onOpenInbox: TodayProps["onOpenInbox"];
  onOpenMission: TodayProps["onOpenMission"];
}) {
  const { source, mission, owed, teamTurn, unqualifiedTurn, exactSelection } = chairmanTurn(projection);
  const title = mission?.program.title || mission?.program.work_ref;
  const effectUnknown = projection.receipts.effect === "EFFECT_UNKNOWN";
  const complete = source.state === "CURRENT" && mission !== null &&
    mission.read_state.state === "CURRENT" && !unqualifiedTurn &&
    source.coverage === "COMPLETE" && exactSelection !== null;
  let body: ReactNode;
  if (owed) {
    body = <article className="today-attention-item">
      <p className="today-eyebrow">{strings.chairmanEyebrow} · {title}</p>
      <p className="today-attention-reason">{owed.reason || strings.attentionWhy}</p>
      <p className="today-muted">{strings.attentionContext} · {exactSelection?.workRef || strings.associationUnavailable}</p>
      <div className="today-attention-actions">
        {exactSelection && onOpenMission && <button type="button" className="today-primary"
          onClick={() => onOpenMission(exactSelection)}>{strings.openProject}</button>}
        <button type="button" onClick={onOpenInbox}>{strings.openInbox}</button>
      </div>
      <p className="today-faint">{strings.attentionNote}</p>
    </article>;
  } else if (teamTurn) {
    body = <article className="today-attention-item">
      <p className="today-eyebrow">{title}</p>
      <p>{teamTurn.reason || strings.teamNext}</p>
      <p className="today-muted">{strings.nextOwner} · {teamTurn.seat}</p>
      <button type="button" onClick={onOpenInbox}>{strings.openInbox}</button>
    </article>;
  } else if (complete && !effectUnknown) {
    body = <article className="today-attention-item">
      <p className="today-muted">{strings.nothingBody}</p>
    </article>;
  } else {
    body = <article className="today-attention-item">
      <p>{strings.uncertaintyBody}</p>

      <div className="today-attention-actions">
        <button type="button" onClick={onOpenInbox}>{strings.openInbox}</button>
      </div>
    </article>;
  }
  const heading = owed ? strings.attentionTitle : teamTurn ? strings.teamTitle : complete && !effectUnknown ? strings.nothingTitle : strings.uncertaintyTitle;
  return <section className="today-attention" aria-label={strings.attentionRegion}>
    <h2 className="today-module-title">{heading}</h2>
    {(owed || teamTurn || complete) && <StateChip source={source} strings={strings} />}
    {effectUnknown && <p className="today-exception" role="alert">{strings.workEffectUnknown}</p>}
    {body}
    <Provenance source={source} summary={strings.provenance} strings={strings} reason={projection.mission.reason} />
  </section>;
}

function Programs({ projection, strings, selection, onOpenProjects, onOpenMission }: {
  projection: OfficeProjection;
  strings: Strings;
  selection: OfficeProjection["context"]["selection"];
  onOpenProjects: TodayProps["onOpenProjects"];
  onOpenMission: TodayProps["onOpenMission"];
}) {
  const qualified = qualifyPrograms(projection.programs);
  const source = projection.programs.source;
  return <section className="today-programs" aria-label={strings.projectsTitle}>
    <div className="today-programs-head">
      <h2 className="today-module-title">{strings.projectsTitle}</h2>
      <button type="button" className="today-view-all" onClick={onOpenProjects}>{strings.viewAll}</button>
    </div>
    {qualified ? <>
      <p className="today-faint">{strings.suppliedCount(qualified.cards.length)}</p>
      <ul className="today-project-list">
        {qualified.cards.slice(0, 3).map(card => {
          const open = resolvedSelection(card);
          const title = card.title || card.workRef;
          const selected = !!selection && selection.workRef === card.workRef && selection.rootJobId === card.rootJobId;
          return <li key={card.workRef} className="today-project-row" aria-current={selected || undefined}>
            <div>
              {selected && <p className="today-eyebrow">{strings.selectedProject}</p>}
              <p className="today-project-name">{title}</p>
              <p className="today-faint">{card.workRef}{open ? ` · ${strings.rootLabel(open.rootJobId)}` : ""}</p>
            </div>
            <p className="today-project-state">
              {card.nextActionWithheld ? strings.withheldNext : card.nextAction || ""}
              <span data-state={card.state ? "KNOWN" : "UNKNOWN"}>{card.state || strings.notSupplied}</span>
            </p>
            {open && onOpenMission && <button type="button" aria-label={`${strings.openProject} ${title}`}
              onClick={() => onOpenMission(open)}>{strings.openProject}</button>}
          </li>;
        })}
      </ul>
      {qualified.cards.length > 3 && <p className="today-faint">{strings.firstProjects}</p>}
      <Provenance source={qualified.source} summary={strings.provenance} strings={strings} />
    </> : <div className="today-unavailable">
      <p>{strings.projectsUnavailable}</p>
      <Provenance source={source} summary={strings.provenance} strings={strings} reason={projection.programs.reason} />
    </div>}
  </section>;
}

/** Work summary speaks only from a decoded AVAILABLE document observed SAME. */
function workView(work: TodayWorkState, strings: Strings) {
  if (work.kind === "PENDING") return { ok: false as const, line: strings.workPending, detail: null };
  if (work.kind === "UNAVAILABLE") return { ok: false as const, line: strings.workUnavailable, detail: work.reason };
  const document = work.document;
  if (document.availability !== "AVAILABLE" || document.source_observation.state !== "SAME")
    return { ok: false as const, line: strings.workUnavailable, detail: document.reason_codes.join(" · ") || document.availability };
  return { ok: true as const, document };
}

function Work({ work, projection, strings }: {
  work: TodayWorkState;
  projection: OfficeProjection;
  strings: Strings;
}) {
  const view = workView(work, strings);
  const { exactSelection } = chairmanTurn(projection);
  const root = exactSelection ? exactSelection.rootJobId : null;
  const row = view.ok && root ? view.document.groups.RUNNING.concat(
    view.document.groups.QUEUED, view.document.groups.NEEDS_SOL, view.document.groups.NEEDS_WORKER,
    view.document.groups.WAITING_CAPACITY, view.document.groups.COMPLETED_NOT_ACCEPTED,
    view.document.groups.TERMINAL, view.document.groups.EFFECT_EXCEPTION, view.document.groups.UNKNOWN
  ).find(candidate => candidate.root_job_id === root) : null;
  const coverage = view.ok ? view.document.coverage : null;
  const lifecycleSource = view.ok ? view.document.lifecycle_source : null;
  return <section className="today-work" aria-label={strings.workTitle}>
    <h2 className="today-module-title">{strings.workTitle}</h2>
    {!view.ok ? <div className="today-unavailable">
      <p>{view.line}</p>
      {view.detail && <p className="today-faint">{view.detail}</p>}
    </div> : <>
      <span className="today-state" data-state="CURRENT">{strings.stateLabel} · EXECUTIVE_RUNTIME · SAME</span>
      {coverage!.count > 0 && <p className="today-faint">{strings.workQueueSupplied(coverage!.count)}</p>}
      <p className="today-muted">{coverage!.completeness === "COMPLETE" ? strings.workCompleteScope : strings.workPartialScope}</p>
      <div className="today-work-root">
        <p className="today-eyebrow">{strings.workRoot}</p>
        {root === null ? <p className="today-muted">{strings.workNoRoot}</p> : row ? <>
          <p className="today-project-name">{root}</p>
          <p><span>{strings.lifecycleLabel}</span>{row.lifecycle.status}</p>
          {row.effect.value === "EFFECT_UNKNOWN" && <p className="today-exception" role="alert">{strings.workEffectUnknown}</p>}
        </> : <p className="today-muted">{coverage!.completeness === "COMPLETE" ? strings.workRootAbsentComplete : strings.workRootAbsentPartial}</p>}
      </div>
      {view.document.effect_exception.value === "EFFECT_UNKNOWN" &&
        <p className="today-exception" role="alert">{strings.workEffectUnknown}</p>}
      <Provenance source={{
        owner: lifecycleSource?.runtime.acquisition.owner ?? "EXECUTIVE_RUNTIME",
        ref: lifecycleSource?.runtime.root ?? null,
        revision: view.document.source_observation.runtime?.snapshot_digest ?? null,
        observed_at: null,
        state: "CURRENT",
        coverage: coverage!.completeness,
      }} summary={strings.provenance} strings={strings} />
      <dl className="today-work-clock">
        <dt>{strings.workExceptionScope}</dt><dd><code>{view.document.effect_exception.value}</code></dd>
        <dt>{strings.selectedEffectScope}</dt><dd><code>{row?.effect.value ?? strings.notSupplied}</code></dd>
      </dl>
      <dl className="today-work-clock"><dt>{strings.generatedAt}</dt><dd>{view.document.generated_at || strings.notSupplied}</dd></dl>
    </>}
    {work.kind === "DOCUMENT" && <details className="today-provenance"><summary>{strings.receiptsSummary}</summary>
      <section className="today-receipts">
        {Object.entries(projection.receipts).map(([name, value]) =>
          <div key={name}><p>{name}</p><strong>{value ?? strings.notProjected}</strong></div>)}
      </section>
      <p className="today-faint">{strings.receiptsNote}</p>
    </details>}
  </section>;
}

function TodayBody({ locale, projection, work, composer, authenticationCue, retainComposerWithAuth, onOpenInbox, onOpenProjects, onOpenMission }: TodayProps) {
  const strings = STRINGS[locale ?? "en"];
  const selection = projection.context.selection;
  return <section className="atelier-today" aria-label={strings.heroTitle}>
    <header className="today-hero">
      <h1>{strings.heroTitle}</h1>
      <p>{strings.heroSubtitle}</p>
    </header>
    <section className="today-composer" aria-label={strings.composerLabel}><div hidden={!!authenticationCue && !retainComposerWithAuth}>{composer}</div>{authenticationCue}</section>
    <div className="today-lower">
      {!authenticationCue && <Attention projection={projection} strings={strings} onOpenInbox={onOpenInbox} onOpenMission={onOpenMission} />}
      {authenticationCue && projection.receipts.effect === "EFFECT_UNKNOWN" && <p className="today-exception" role="alert">{strings.workEffectUnknown}</p>}
      <div className="today-side">
        {!authenticationCue && <Programs projection={projection} strings={strings} selection={selection}
          onOpenProjects={onOpenProjects} onOpenMission={onOpenMission} />}
        {work.kind === "DOCUMENT" && work.document.availability === "AVAILABLE" &&
          work.document.source_observation.state === "SAME" &&
          (work.document.effect_exception.value === "EFFECT_UNKNOWN" ||
            Object.values(work.document.groups).some(rows => rows.some(row =>
              row.root_job_id === selection?.rootJobId && row.effect.value === "EFFECT_UNKNOWN"))) &&
          <p className="today-exception" role="alert">{strings.workEffectUnknown}</p>}
        {!authenticationCue && <details className="today-work-details"><summary>{strings.workDetails}</summary>
          <Work work={work} projection={projection} strings={strings} />
        </details>}
      </div>
    </div>
  </section>;
}

/** Pure owner-fed view. The parent composer owns its auth/selection lifecycle;
 * source refresh, locale and work-summary transitions must not remount it. */
export function Today(props: TodayProps) {
  return <TodayBody {...props} />;
}
