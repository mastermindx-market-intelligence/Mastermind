import { useId, useState } from "react";
import type { ChangeEvent } from "react";
import type {
  EvidenceRef,
  MissionDocument,
  MissionSelection,
  ReadState,
} from "../mission";
import "./web-session-preview.css";

// ---------------------------------------------------------------------------
// Canonical Paper AT23 — "New Web session preview"
//
// An intentionally inert draft + review stage for the selected mission. It
// shows the exact selected source's bounded receipts and a purely local
// draft; nothing here fetches, stores, maps commands, selects a browser,
// profile or account, dispatches, or creates any session. The workspace's
// existing session bridge admits fabric_attempt, codex and claude targets
// only (SessionBridge TARGET_KINDS), so no qualified Web session launch
// capability exists here and none is invented: "Launch unavailable" is a
// fixed disabled state with no callback.
// ---------------------------------------------------------------------------

export interface WebSessionPreviewProps {
  /** The exact selected mission document; null when none is available. */
  document: MissionDocument | null;
  /** The exact current selection; supplied by the parent, never inferred. */
  selection: MissionSelection | null;
  locale?: string;
}

type MissingReason =
  | "NO_DOCUMENT"
  | "NO_SELECTION"
  | "WORK_MISMATCH"
  | "ROOT_MISMATCH"
  | "ROOT_UNRESOLVED"
  | "ROOT_AMBIGUOUS"
  | "SOURCE_UNAVAILABLE";

interface Bilingual {
  en: string;
  zh: string;
}

interface PreviewCopy {
  heading: string;
  status: string;
  brief: string;
  sessionBrief: string;
  role: string;
  objective: string;
  attachedSources: string;
  guardrails: string;
  whenFinished: string;
  taskDetails: string;
  whyNew: string;
  reason: string;
  required: string;
  optional: string;
  reviewLaunch: string;
  launchUnavailable: string;
  capabilityNote: string;
  reviewTitle: string;
  reviewCaption: string;
  work: string;
  rootJob: string;
  readState: string;
  reasonCodes: string;
  generatedAt: string;
  owner: string;
  ref: string;
  revision: string;
  sourceTime: string;
  observedAt: string;
  freshness: string;
  notReported: string;
  noSources: string;
  showAll: string;
  none: string;
  roleRequired: string;
  objectiveRequired: string;
  whenFinishedRequired: string;
  whyRequired: string;
  shownCount: (shown: number, total: number) => string;
}

const COPY: Record<"en" | "zh", PreviewCopy> = {
  en: {
    heading: "Review a new session",
    status: "Preview — not launched",
    brief: "A new conversation does not create a new mission.",
    sessionBrief: "Session brief",
    role: "Role",
    objective: "Objective",
    attachedSources: "Attached sources",
    guardrails: "Guardrails",
    whenFinished: "When finished",
    taskDetails: "Task details",
    whyNew: "Why a new session",
    reason: "Reason",
    required: "Required",
    optional: "Optional",
    reviewLaunch: "Review launch",
    launchUnavailable: "Launch unavailable",
    capabilityNote: "This workspace has no qualified Web session launch capability.",
    reviewTitle: "Draft preview",
    reviewCaption:
      "Local snapshot of this draft for the current selection and source. Nothing was launched.",
    work: "Work",
    rootJob: "Root job",
    readState: "Read state",
    reasonCodes: "Reason codes",
    generatedAt: "Generated at",
    owner: "Owner",
    ref: "Ref",
    revision: "Revision",
    sourceTime: "Source time",
    observedAt: "Observed at",
    freshness: "Freshness",
    notReported: "Not reported",
    noSources: "No attached sources.",
    showAll: "Show all",
    none: "None",
    roleRequired: "Role is required.",
    objectiveRequired: "Objective is required.",
    whenFinishedRequired: "When finished is required.",
    whyRequired: "Why a new session is required.",
    shownCount: (shown, total) => `Showing ${shown} of ${total} attached sources.`,
  },
  zh: {
    heading: "审核新会话",
    status: "预览 — 未启动",
    brief: "新对话不会创建新任务。",
    sessionBrief: "会话简报",
    role: "角色",
    objective: "目标",
    attachedSources: "附带来源",
    guardrails: "护栏",
    whenFinished: "完成条件",
    taskDetails: "任务详情",
    whyNew: "为何需要新会话",
    reason: "理由",
    required: "必填",
    optional: "可选",
    reviewLaunch: "审核启动",
    launchUnavailable: "启动不可用",
    capabilityNote: "此工作区没有已认证的 Web 会话启动能力。",
    reviewTitle: "草稿预览",
    reviewCaption: "针对当前选择与来源的草稿本地快照。未启动任何操作。",
    work: "工作",
    rootJob: "根任务",
    readState: "读取状态",
    reasonCodes: "原因代码",
    generatedAt: "生成时间",
    owner: "所有者",
    ref: "引用",
    revision: "修订",
    sourceTime: "来源时间",
    observedAt: "观察时间",
    freshness: "新鲜度",
    notReported: "未报告",
    noSources: "没有附带来源。",
    showAll: "显示全部",
    none: "未填写",
    roleRequired: "角色必填。",
    objectiveRequired: "目标必填。",
    whenFinishedRequired: "完成条件必填。",
    whyRequired: "为何需要新会话必填。",
    shownCount: (shown, total) => `显示 ${total} 个附带来源中的 ${shown} 个。`,
  },
};

const MISSING_REASON_COPY: Record<MissingReason, Bilingual> = {
  NO_DOCUMENT: { en: "No selected mission document is available.", zh: "没有可用的已选任务文档。" },
  NO_SELECTION: { en: "No mission selection is active.", zh: "当前没有已选的任务。" },
  WORK_MISMATCH: { en: "The selected source does not match the selected work.", zh: "所选来源与所选工作不匹配。" },
  ROOT_MISMATCH: { en: "The selected source does not match the selected root job.", zh: "所选来源与所选根任务不匹配。" },
  ROOT_UNRESOLVED: { en: "The root job of the selected source is not resolved.", zh: "所选来源的根任务未解析。" },
  ROOT_AMBIGUOUS: { en: "The root job of the selected source is ambiguous.", zh: "所选来源的根任务存在歧义。" },
  SOURCE_UNAVAILABLE: { en: "The selected source is unavailable.", zh: "所选来源不可用。" },
};

const READ_STATE_COPY: Record<ReadState, Bilingual> = {
  CURRENT: { en: "Current source.", zh: "当前来源。" },
  PARTIAL: { en: "Partial source — some source sections are unavailable.", zh: "部分来源 — 部分来源分区不可用。" },
  HISTORICAL: { en: "Historical source — not the current source generation.", zh: "历史来源 — 不是当前来源生成。" },
  UNAVAILABLE: { en: "Source unavailable.", zh: "来源不可用。" },
};

/** Resolved selected source: hidden unless everything matches exactly. */
type PreviewSource =
  | {
      kind: "MATCHED";
      document: MissionDocument;
      selection: MissionSelection;
      /** Key of the exact selection plus the source generation. */
      key: string;
      /** Stamp of the exact source revision content behind any review. */
      stamp: string;
    }
  | { kind: "MISSING"; reason: MissingReason };

function sourceStamp(document: MissionDocument, key: string): string {
  const rows = document.program.evidence.map((item: EvidenceRef) =>
    [
      item.owner,
      item.ref,
      item.source_revision,
      item.source_time,
      item.observed_at,
      item.freshness_state,
    ].join("\u0000"),
  );
  return [key, document.read_state.state, ...rows].join("\u0001");
}

/** Attached sources only exist for the exact work, exact resolved root and readable source. */
function resolveSource(
  document: MissionDocument | null,
  selection: MissionSelection | null,
): PreviewSource {
  if (!document) return { kind: "MISSING", reason: "NO_DOCUMENT" };
  if (!selection) return { kind: "MISSING", reason: "NO_SELECTION" };
  if (document.program.work_ref !== selection.workRef) {
    return { kind: "MISSING", reason: "WORK_MISMATCH" };
  }
  if (document.mission.root_job_id !== selection.rootJobId) {
    return { kind: "MISSING", reason: "ROOT_MISMATCH" };
  }
  if (document.mission.runtime_root_state !== "RESOLVED") {
    return { kind: "MISSING", reason: "ROOT_UNRESOLVED" };
  }
  const candidates = document.mission.root_job_candidates;
  if (
    document.mission.root_job_ambiguous ||
    candidates.length !== 1 ||
    candidates[0] !== selection.rootJobId
  ) {
    return { kind: "MISSING", reason: "ROOT_AMBIGUOUS" };
  }
  if (document.read_state.state === "UNAVAILABLE") {
    return { kind: "MISSING", reason: "SOURCE_UNAVAILABLE" };
  }
  const key = [
    selection.workRef,
    selection.rootJobId,
    document.generated_at ?? "",
  ].join("\u0000");
  return {
    kind: "MATCHED",
    document,
    selection,
    key,
    stamp: sourceStamp(document, key),
  };
}

interface DraftState {
  role: string;
  objective: string;
  guardrails: string;
  completionCondition: string;
  whyNew: string;
}

const EMPTY_DRAFT: DraftState = {
  role: "",
  objective: "",
  guardrails: "",
  completionCondition: "",
  whyNew: "",
};

/** Snapshot of the exact reviewed draft bound to its exact source stamp. */
interface ReviewedDraft extends DraftState {
  workRef: string;
  rootJobId: string;
  generatedAt: string | null;
  stamp: string;
}

/** Bounded receipts: owner, ref, revision, source time, observed at, freshness. */
function SourceReceipts({ evidence, copy }: { evidence: EvidenceRef[]; copy: PreviewCopy }) {
  const [showAll, setShowAll] = useState(false);
  if (evidence.length === 0) {
    return <p className="wsp-empty">{copy.noSources}</p>;
  }
  const visible = showAll ? evidence : evidence.slice(0, 8);
  return (
    <div className="wsp-sources">
      <ul className="wsp-source-list">
        {visible.map((item, index) => (
          <li key={index} className="wsp-source">
            <dl className="wsp-receipt">
              <dt>{copy.owner}</dt>
              <dd><code>{item.owner}</code></dd>
              <dt>{copy.ref}</dt>
              <dd><code>{item.ref}</code></dd>
              <dt>{copy.revision}</dt>
              <dd><code>{item.source_revision ?? copy.notReported}</code></dd>
              <dt>{copy.sourceTime}</dt>
              <dd><code>{item.source_time ?? copy.notReported}</code></dd>
              <dt>{copy.observedAt}</dt>
              <dd><code>{item.observed_at ?? copy.notReported}</code></dd>
              <dt>{copy.freshness}</dt>
              <dd><code>{item.freshness_state}</code></dd>
            </dl>
          </li>
        ))}
      </ul>
      {!showAll && evidence.length > visible.length ? (
        <div className="wsp-count">
          <span>{copy.shownCount(visible.length, evidence.length)}</span>
          <button type="button" onClick={() => setShowAll(true)}>
            {copy.showAll}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function SessionDraftForm({
  document,
  selection,
  stamp,
  copy,
  localeIsZh,
}: {
  document: MissionDocument;
  selection: MissionSelection;
  stamp: string;
  copy: PreviewCopy;
  localeIsZh: boolean;
}) {
  const ids = useId();
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [reviewed, setReviewed] = useState<ReviewedDraft | null>(null);
  const [attempted, setAttempted] = useState(false);

  // A reviewed snapshot survives only while its exact source stamp is current.
  const liveReview = reviewed !== null && reviewed.stamp === stamp ? reviewed : null;

  const setField =
    (field: keyof DraftState) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value = event.target.value;
      setDraft((previous) => ({ ...previous, [field]: value }));
      // Any draft change invalidates the reviewed snapshot immediately.
      setReviewed(null);
    };

  const missingReasons: string[] = [];
  if (draft.role.trim() === "") missingReasons.push(copy.roleRequired);
  if (draft.objective.trim() === "") missingReasons.push(copy.objectiveRequired);
  if (draft.completionCondition.trim() === "") missingReasons.push(copy.whenFinishedRequired);
  if (draft.whyNew.trim() === "") missingReasons.push(copy.whyRequired);
  const complete = missingReasons.length === 0;

  const onReview = () => {
    if (!complete) {
      setAttempted(true);
      return;
    }
    setReviewed({
      ...draft,
      workRef: selection.workRef,
      rootJobId: selection.rootJobId,
      generatedAt: document.generated_at,
      stamp,
    });
  };

  const readState = document.read_state.state;

  return (
    <>
      <div className="wsp-columns">
        <section className="wsp-col" aria-label={copy.sessionBrief}>
          <h3>{copy.sessionBrief}</h3>
          <div className="wsp-field">
            <label htmlFor={`${ids}-role`}>{copy.role}</label>
            <span className="wsp-hint">{copy.required}</span>
            <input id={`${ids}-role`} value={draft.role} onChange={setField("role")} />
          </div>
          <div className="wsp-field">
            <label htmlFor={`${ids}-objective`}>{copy.objective}</label>
            <span className="wsp-hint">{copy.required}</span>
            <textarea
              id={`${ids}-objective`}
              value={draft.objective}
              onChange={setField("objective")}
              rows={3}
            />
          </div>
          <section className="wsp-sources-block" aria-label={copy.attachedSources}>
            <h4>{copy.attachedSources}</h4>
            <p className="wsp-generated">
              <span>{copy.generatedAt}</span> <code>{document.generated_at ?? copy.notReported}</code>
            </p>
            <SourceReceipts evidence={document.program.evidence} copy={copy} />
          </section>
          <div className="wsp-field">
            <label htmlFor={`${ids}-guardrails`}>{copy.guardrails}</label>
            <span className="wsp-hint">{copy.optional}</span>
            <textarea
              id={`${ids}-guardrails`}
              value={draft.guardrails}
              onChange={setField("guardrails")}
              rows={3}
            />
          </div>
          <div className="wsp-field">
            <label htmlFor={`${ids}-finished`}>{copy.whenFinished}</label>
            <span className="wsp-hint">{copy.required}</span>
            <textarea
              id={`${ids}-finished`}
              value={draft.completionCondition}
              onChange={setField("completionCondition")}
              rows={2}
            />
          </div>
          <details className="wsp-details">
            <summary>{copy.taskDetails}</summary>
            <dl className="wsp-detail-list">
              <dt>{copy.work}</dt>
              <dd><code>{document.program.work_ref}</code></dd>
              <dt>{copy.rootJob}</dt>
              <dd><code>{document.mission.root_job_id}</code></dd>
              <dt>{copy.readState}</dt>
              <dd><code>{readState}</code> {READ_STATE_COPY[readState][localeIsZh ? "zh" : "en"]}</dd>
              {document.read_state.reason_codes.length > 0 ? (
                <>
                  <dt>{copy.reasonCodes}</dt>
                  <dd><code>{document.read_state.reason_codes.join(" · ")}</code></dd>
                </>
              ) : null}
            </dl>
          </details>
          {attempted && !complete ? (
            <ul className="wsp-required-list">
              {missingReasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          <div className="wsp-actions">
            <button type="button" className="wsp-primary" onClick={onReview}>
              {copy.reviewLaunch}
            </button>
          </div>
        </section>
        <aside className="wsp-col" aria-label={copy.whyNew}>
          <h3>{copy.whyNew}</h3>
          <div className="wsp-field">
            <label htmlFor={`${ids}-why`}>{copy.reason}</label>
            <span className="wsp-hint">{copy.required}</span>
            <textarea
              id={`${ids}-why`}
              value={draft.whyNew}
              onChange={setField("whyNew")}
              rows={4}
            />
          </div>
          <p id={`${ids}-capability`} className="wsp-note">{copy.capabilityNote}</p>
          <div className="wsp-actions">
            <button type="button" disabled aria-describedby={`${ids}-capability`}>
              {copy.launchUnavailable}
            </button>
          </div>
        </aside>
      </div>
      {liveReview ? (
        <section className="wsp-review" aria-label={copy.reviewTitle}>
          <h3>{copy.reviewTitle}</h3>
          <p className="wsp-muted">{copy.reviewCaption}</p>
          <dl className="wsp-review-list">
            <dt>{copy.work}</dt>
            <dd><code>{liveReview.workRef}</code></dd>
            <dt>{copy.rootJob}</dt>
            <dd><code>{liveReview.rootJobId}</code></dd>
            <dt>{copy.generatedAt}</dt>
            <dd><code>{liveReview.generatedAt ?? copy.notReported}</code></dd>
            <dt>{copy.role}</dt>
            <dd className="wsp-value">{liveReview.role}</dd>
            <dt>{copy.objective}</dt>
            <dd className="wsp-value">{liveReview.objective}</dd>
            <dt>{copy.guardrails}</dt>
            <dd className="wsp-value">{liveReview.guardrails === "" ? copy.none : liveReview.guardrails}</dd>
            <dt>{copy.whenFinished}</dt>
            <dd className="wsp-value">{liveReview.completionCondition}</dd>
            <dt>{copy.whyNew}</dt>
            <dd className="wsp-value">{liveReview.whyNew}</dd>
          </dl>
          <SourceReceipts evidence={document.program.evidence} copy={copy} />
        </section>
      ) : null}
    </>
  );
}

/** Inert preview stage: local draft and review only, never a launch. */
export function WebSessionPreview({
  document,
  selection,
  locale = "en",
}: WebSessionPreviewProps) {
  const ids = useId();
  const localeIsZh = locale.startsWith("zh");
  const copy = COPY[localeIsZh ? "zh" : "en"];
  const source = resolveSource(document, selection);
  const header = (
    <header className="wsp-header">
      <div className="wsp-heading">
        <h2>{copy.heading}</h2>
        <span className="wsp-status">{copy.status}</span>
      </div>
      <p className="wsp-muted">{copy.brief}</p>
    </header>
  );
  if (source.kind === "MISSING") {
    return (
      <section className="wsp" aria-label={copy.heading}>
        {header}
        <div className="wsp-columns">
          <section className="wsp-col" aria-label={copy.sessionBrief}>
            <h3>{copy.sessionBrief}</h3>
            <p id={`${ids}-missing`} className="wsp-missing" role="note">
              {MISSING_REASON_COPY[source.reason][localeIsZh ? "zh" : "en"]}
            </p>
            <div className="wsp-actions">
              <button type="button" disabled aria-describedby={`${ids}-missing`}>
                {copy.reviewLaunch}
              </button>
            </div>
          </section>
          <aside className="wsp-col" aria-label={copy.whyNew}>
            <h3>{copy.whyNew}</h3>
            <p id={`${ids}-capability`} className="wsp-note">{copy.capabilityNote}</p>
            <div className="wsp-actions">
              <button type="button" disabled aria-describedby={`${ids}-capability`}>
                {copy.launchUnavailable}
              </button>
            </div>
          </aside>
        </div>
      </section>
    );
  }
  return (
    <section className="wsp" aria-label={copy.heading}>
      {header}
      <p className="wsp-scope">
        <span>{copy.work}</span> <code>{source.document.program.work_ref}</code>
        <span aria-hidden="true">·</span>
        <span>{copy.rootJob}</span> <code>{source.document.mission.root_job_id}</code>
      </p>
      {/* Keyed by the exact selection plus source generation: a change remounts
          the form, so no draft or receipt from another context is retained. */}
      <SessionDraftForm
        key={source.key}
        document={source.document}
        selection={source.selection}
        stamp={source.stamp}
        copy={copy}
        localeIsZh={localeIsZh}
      />
    </section>
  );
}
