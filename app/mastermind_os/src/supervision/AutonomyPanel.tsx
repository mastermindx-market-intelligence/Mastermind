import { useEffect, useRef, useState } from "react";
import "./supervision-trace.css";
import type { MissionSelection } from "../mission";
import {
  isAutonomySelection,
  decodeAutonomyPolicy,
  type AutonomyRead,
  type AutonomySelection,
} from "./autonomy-policy";

export interface AutonomyReadRequest {
  work_ref: string;
  root_job_id: string;
  signal: AbortSignal;
}
export type AutonomyReadCallback = (request: AutonomyReadRequest) => Promise<unknown>;
export type AutonomyPanelLocale = "en" | "zh-CN";
export interface AutonomyPanelProps {
  /** Exact selected mission from the existing host; the host stays the selection and auth authority. */
  selection: MissionSelection | null;
  canRead: boolean;
  /** Actual host source generation; never inferred here and never shown as a clock. */
  sourceGeneration: string | number;
  /** Injected fixed autonomy read; no fetch, URL or default transport in this panel. */
  read?: AutonomyReadCallback;
  locale?: AutonomyPanelLocale;
}

const STRINGS = {
  en: {
    heading: "Autonomy",
    intent: "Review how work follows this selected mission.",
    readButton: "Read existing limits",
    readingButton: "Reading…",
    limitsHeading: "Existing plan limits",
    ceilingsNote: "Policy ceilings, not remaining budget or permission for new work.",
    standingInstructions: "Standing instructions are not supplied by this read.",
    pauseNote: "Project pause is not available from this read.",
    sourceSummary: "Source details",
    unavailable: "Existing execution limits are unavailable.",
    readFailed: "The autonomy read did not complete.",
    readInvalid: "The autonomy read returned a response this panel cannot decode.",
    noSelection: "Select a mission to review its autonomy policy.",
    invalidSelection: "This selection does not match the autonomy read selection format.",
    denied: "Reading is unavailable: the existing host has not confirmed current read permission.",
    noReader: "No autonomy read is connected to this panel.",
    workRef: "Work ref",
    rootJobId: "Root job",
    policySha: "Policy digest",
    sourceSha: "Source digest",
    planDigest: "Plan digest",
    reservationDigest: "Reservation digest",
    sourceProof: "Source proof",
    sourceIdentity: "Source identity",
    receiptCounter: "Receipt counter (before = after)",
    instance: "Instance",
    publicationCounter: "Publication counter",
    documentDigest: "Document digest",
    sourceValidityDigest: "Source validity digest",
    cacheCurrentnessDigest: "Cache currentness digest",
    limits: {
      max_children_total: "Max children total",
      max_fan_out_per_parent: "Max fan-out per parent",
      max_depth: "Max depth",
      max_attempts_per_orchestration_job: "Max attempts per orchestration job",
      max_repair_rounds: "Max repair rounds",
      max_review_attempts_per_job: "Max review attempts per job",
      review_job_attempt_limit: "Review job attempt limit",
      allowed_child_cost_classes: "Allowed child cost classes",
    },
  },
  "zh-CN": {
    heading: "自主工作",
    intent: "查看工作如何遵循当前选定的任务。",
    readButton: "读取现有上限",
    readingButton: "读取中…",
    limitsHeading: "现有计划上限",
    ceilingsNote: "这些是策略上限，不是剩余预算，也不是新工作的许可。",
    standingInstructions: "此读取不提供常设指令。",
    pauseNote: "此读取不提供项目暂停。",
    sourceSummary: "来源详情",
    unavailable: "暂时无法获取现有执行上限。",
    readFailed: "自主读取未完成。",
    readInvalid: "自主读取返回了无法解读的结果。",
    noSelection: "请先选定一个任务，再查看其自主策略。",
    invalidSelection: "当前选定不符合自主读取的格式要求。",
    denied: "无法读取：现有主机尚未确认当前的读取权限。",
    noReader: "此面板未接入自主读取。",
    workRef: "工作引用",
    rootJobId: "根任务",
    policySha: "策略摘要",
    sourceSha: "来源摘要",
    planDigest: "计划摘要",
    reservationDigest: "预留摘要",
    sourceProof: "来源凭证",
    sourceIdentity: "来源标识",
    receiptCounter: "读取计数（前后一致）",
    instance: "实例",
    publicationCounter: "发布计数",
    documentDigest: "文档摘要",
    sourceValidityDigest: "来源有效性摘要",
    cacheCurrentnessDigest: "缓存当前性摘要",
    limits: {
      max_children_total: "子工作总数上限",
      max_fan_out_per_parent: "每个父工作的扇出上限",
      max_depth: "最大深度",
      max_attempts_per_orchestration_job: "每个编排任务的最大尝试次数",
      max_repair_rounds: "最大修复轮数",
      max_review_attempts_per_job: "每个任务的审阅尝试上限",
      review_job_attempt_limit: "审阅任务尝试上限",
      allowed_child_cost_classes: "允许的子工作成本类别",
    },
  },
} as const;

interface PanelState {
  scopeKey: string | null;
  read: AutonomyRead | null;
  errorText: string | null;
  pending: boolean;
}
const EMPTY_STATE: PanelState = { scopeKey: null, read: null, errorText: null, pending: false };

const READER_IDS = new WeakMap<AutonomyReadCallback, number>();
let NEXT_READER_ID = 0;
function readerIdentity(read: AutonomyReadCallback): number {
  let id = READER_IDS.get(read);
  if (id === undefined) {
    id = NEXT_READER_ID;
    NEXT_READER_ID += 1;
    READER_IDS.set(read, id);
  }
  return id;
}

/** Read-only autonomy policy consumer: one explicit click reads; ceilings are never grants. */
export function AutonomyPanel(props: AutonomyPanelProps) {
  const { selection, canRead, sourceGeneration, read, locale = "en" } = props;
  const t = locale === "zh-CN" ? STRINGS["zh-CN"] : STRINGS.en;
  const eligible: AutonomySelection | null = selection !== null
    && isAutonomySelection({work_ref: selection.workRef, root_job_id: selection.rootJobId})
    ? { work_ref: selection.workRef, root_job_id: selection.rootJobId }
    : null;
  // Owner source key: exact selection + host generation + reader identity + current permission.
  const scopeKey = eligible && canRead && read
    ? JSON.stringify([eligible.work_ref, eligible.root_job_id, sourceGeneration, readerIdentity(read)])
    : null;
  const [state, setState] = useState<PanelState>(EMPTY_STATE);
  const controllerRef = useRef<AbortController | null>(null);
  const latestScopeKey = useRef<string | null>(null);
  latestScopeKey.current = scopeKey;
  const liveRef = useRef(true);
  // Same-render mask: stored content from another scope is never rendered, not even once.
  const visible = state.scopeKey !== null && state.scopeKey === scopeKey ? state : EMPTY_STATE;

  useEffect(() => {
    // Scope change: abort only the in-flight read and drop the local request.
    // This effect never starts a read; the existing host stays the read provider.
    controllerRef.current?.abort();
    controllerRef.current = null;
    setState((prev) => prev.scopeKey === null && prev.read === null && prev.errorText === null && !prev.pending
      ? prev
      : EMPTY_STATE);
  }, [scopeKey]);
  useEffect(() => {
    liveRef.current = true;
    return () => {
      liveRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const onReadClick = () => {
    const key = scopeKey;
    if (!read || !canRead || key === null || eligible === null || controllerRef.current !== null) return;
    const captured = eligible;
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({ scopeKey: key, read: null, errorText: null, pending: true });
    let response: Promise<unknown>;
    try {
      response = read({ work_ref: captured.work_ref, root_job_id: captured.root_job_id, signal: controller.signal });
    } catch {
      controllerRef.current = null;
      setState({ scopeKey: key, read: null, errorText: t.readFailed, pending: false });
      return;
    }
    Promise.resolve(response).then(
      (raw) => {
        // Every branch rechecks liveness, current scope and the captured key before publishing.
        if (!liveRef.current || controller.signal.aborted || controllerRef.current !== controller) return;
        if (latestScopeKey.current !== key) return;
        let decoded: AutonomyRead | null = null;
        try {
          decoded = decodeAutonomyPolicy(raw, captured);
        } catch {
          decoded = null;
        }
        controllerRef.current = null;
        setState((prev) => {
          if (prev.scopeKey !== key || !prev.pending) return prev;
          return decoded === null
            ? { scopeKey: key, read: null, errorText: t.readInvalid, pending: false }
            : { scopeKey: key, read: decoded, errorText: null, pending: false };
        });
      },
      () => {
        if (!liveRef.current || controller.signal.aborted || controllerRef.current !== controller) return;
        if (latestScopeKey.current !== key) return;
        controllerRef.current = null;
        setState((prev) => prev.scopeKey !== key || !prev.pending
          ? prev
          : { scopeKey: key, read: null, errorText: t.readFailed, pending: false });
      },
    );
  };

  const pendingRead = visible.pending;
  const disabledReason = pendingRead ? null
    : selection === null ? t.noSelection
    : eligible === null ? t.invalidSelection
    : !canRead ? t.denied
    : !read ? t.noReader
    : null;
  const decodedRead = visible.read;
  const limitRows = decodedRead !== null && decodedRead.availability === "AVAILABLE"
    ? [
      [t.limits.max_children_total, "max_children_total", String(decodedRead.policy.limits.max_children_total)],
      [t.limits.max_fan_out_per_parent, "max_fan_out_per_parent", String(decodedRead.policy.limits.max_fan_out_per_parent)],
      [t.limits.max_depth, "max_depth", String(decodedRead.policy.limits.max_depth)],
      [t.limits.max_attempts_per_orchestration_job, "max_attempts_per_orchestration_job", String(decodedRead.policy.limits.max_attempts_per_orchestration_job)],
      [t.limits.max_repair_rounds, "max_repair_rounds", String(decodedRead.policy.limits.max_repair_rounds)],
      [t.limits.max_review_attempts_per_job, "max_review_attempts_per_job", String(decodedRead.policy.limits.max_review_attempts_per_job)],
      [t.limits.review_job_attempt_limit, "review_job_attempt_limit", String(decodedRead.policy.limits.review_job_attempt_limit)],
      [t.limits.allowed_child_cost_classes, "allowed_child_cost_classes", decodedRead.policy.limits.allowed_child_cost_classes.join(" · ")],
    ]
    : [];
  return <section className="card" aria-label={t.heading}>
    <div className="section-title"><h2>{t.heading}</h2></div>
    <p className="muted">{t.intent}</p>
    <div className="form-field">
      <button type="button" onClick={onReadClick} disabled={pendingRead || disabledReason !== null}>
        {pendingRead ? t.readingButton : t.readButton}
      </button>
      {disabledReason !== null ? <p className="muted">{disabledReason}</p> : null}
      {visible.errorText !== null ? <p className="muted">{visible.errorText}</p> : null}
    </div>
    {decodedRead !== null && decodedRead.availability === "UNAVAILABLE" ? <p className="muted">
      {t.unavailable}
    </p> : null}
    {decodedRead !== null && decodedRead.availability === "UNAVAILABLE" ? <details className="reason-details mm-supervision-trace__expand">
      <summary>{t.sourceSummary}</summary><code>{decodedRead.reason_codes[0]}</code>
    </details> : null}
    {decodedRead !== null && decodedRead.availability === "AVAILABLE" ? <>
      <h3>{t.limitsHeading}</h3>
      <p className="muted">{t.ceilingsNote}</p>
      <dl className="mm-supervision-trace__facts" aria-label={t.limitsHeading}>
        {limitRows.map(([label, field, value]) => (
          <div className="mm-supervision-trace__fact" key={field}>
            <dt className="mm-supervision-trace__fact-label">{label}</dt>
            <dd className="mm-supervision-trace__fact-value">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="muted">{t.standingInstructions}</p>
      <p className="muted">{t.pauseNote}</p>
      <details className="reason-details mm-supervision-trace__expand">
        <summary>{t.sourceSummary}</summary>
        <dl>
          {limitRows.map(([label, field]) => <div key={field}><dt>{label}</dt><dd><code>{field}</code></dd></div>)}
          <dt>{t.workRef}</dt><dd>{decodedRead.selection.work_ref}</dd>
          <dt>{t.rootJobId}</dt><dd>{decodedRead.selection.root_job_id}</dd>
          <dt>{t.policySha}</dt><dd><code>{decodedRead.policy.policy_sha}</code></dd>
          <dt>{t.sourceSha}</dt><dd><code>{decodedRead.policy.source_sha256}</code></dd>
          <dt>{t.planDigest}</dt><dd><code>{decodedRead.policy.plan_digest}</code></dd>
          <dt>{t.reservationDigest}</dt><dd><code>{decodedRead.policy.reservation_digest}</code></dd>
          <dt>{t.sourceProof}</dt><dd>{decodedRead.source_observation.state}</dd>
          <dt>{t.sourceIdentity}</dt><dd><code>{decodedRead.source_observation.runtime.source_identity}</code></dd>
          <dt>{t.receiptCounter}</dt><dd>{decodedRead.source_observation.runtime.before}</dd>
          <dt>{t.instance}</dt><dd>{decodedRead.source_observation.control_room.instance_before}</dd>
          <dt>{t.publicationCounter}</dt><dd>{decodedRead.source_observation.control_room.publication_before}</dd>
          <dt>{t.documentDigest}</dt><dd><code>{decodedRead.source_observation.control_room.document_digest}</code></dd>
          <dt>{t.sourceValidityDigest}</dt><dd><code>{decodedRead.source_observation.control_room.source_validity_digest}</code></dd>
          <dt>{t.cacheCurrentnessDigest}</dt><dd><code>{decodedRead.source_observation.control_room.cache_currentness_digest}</code></dd>
        </dl>
      </details>
    </> : null}
  </section>;
}
