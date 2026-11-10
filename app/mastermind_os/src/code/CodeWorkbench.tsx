/** HC07 — "Code · Thread, changes and host tools". The per-attempt workbench:
 *  attempt facts from the `mastermind.t3_attempt_fleet/v1` read, work panels
 *  from a typed `mastermind.execution_return/v1` record, an activity trail
 *  from the retained-activity read, and a return footer. Every panel degrades
 *  to an HONEST state naming its missing source; nothing here is ever
 *  fabricated. Read-only surface: no send, launch or interrupt transport
 *  exists anywhere in this file. */
import { useId, useState } from "react";
import type { ActivitySelection } from "../planning/retained-activity";
import type {
  ExecutionReturnDeliveryReceipt,
  ExecutionReturnRecord,
  ExecutionReturnStage,
} from "../hermes-native/execution-return-contract";
import {
  t3ThreadUrl,
  type T3ProjectionRead,
  type T3ThreadProjection,
} from "./t3-thread-projection";
import {
  useRetainedActivityRead,
  useT3AttemptFleetRead,
} from "./attempt-fleet-read";
import type {
  DuplicateKind,
  InvariantVerdict,
  T3Attempt,
} from "../resources/t3-attempt-fleet-contract";
import "./code.css";

interface Strings {
  heading: string;
  rail: string;
  project: string;
  projectNone: string;
  newThread: string;
  newThreadNote: string;
  searchLabel: string;
  searchPlaceholder: string;
  thisAttempt: string;
  working: string;
  settled: (count: number) => string;
  noThreads: string;
  noMatch: string;
  threadsUnder: (count: number) => string;
  environments: string;
  environmentNone: string;
  manageEnvironments: string;
  manageNote: string;
  railToggle: (open: boolean) => string;
  openSession: string;
  environmentUnknown: string;
  attemptLabel: string;
  evaluated: string;
  harnessUnknown: string;
  notObserved: string;
  unknownReason: (reason: string) => string;
  threadLabel: (threadId: string) => string;
  attemptTitle: (attemptId: string) => string;
  pid: (value: number) => string;
  started: string;
  factsHeading: string;
  exactlyOneThread: string;
  exactlyOneHarness: string;
  proven: string;
  violated: string;
  unknown: string;
  t3Thread: string;
  run: string;
  harness: string;
  duplicates: string;
  duplicatesKinds: Record<DuplicateKind, string>;
  duplicatesNone: string;
  duplicatesObserved: string;
  threadsForKey: string;
  methodHeading: string;
  fresh: Record<string, string>;
  evidenceRefs: string;
  refusalTitle: string;
  refusalBody: string;
  unavailableTitle: string;
  pending: string;
  notConnected: string;
  signIn: string;
  invalidId: string;
  activityHeading: string;
  activityFootnote: string;
  activityNotRetained: string;
  activitySelectionMissing: string;
  activityNotConnected: string;
  activityReading: string;
  activityZero: string;
  activityPartial: string;
  activityOmitted: (count: number) => string;
  activityCategory: Record<string, string>;
  returnTextHeading: string;
  relatedHeading: string;
  relatedNotProjected: string;
  composerLabel: string;
  composerNote: string;
  composerNotConnected: string;
  composerQueue: string;
  panelsLabel: string;
  changesTab: string;
  changesTabCount: (count: number) => string;
  browserTab: string;
  terminalTab: string;
  browserTitle: string;
  browserBody: string;
  branch: string;
  noBranch: string;
  filesHeading: string;
  noFiles: string;
  diffHeading: string;
  changesMissing: string;
  changesSource: string;
  prHeading: string;
  prNumber: (value: number) => string;
  prNone: string;
  merge: string;
  installation: string;
  mergeMerged: string;
  mergeNotMerged: string;
  mergeUnknown: string;
  installClaimed: string;
  installNone: string;
  terminalMissing: string;
  terminalSource: string;
  checksHeading: string;
  noChecks: string;
  checksStateLabel: string;
  checksState: Record<string, string>;
  checkMark: Record<string, string>;
  returnHeading: string;
  returnPending: string;
  returnStage: string;
  stage: Record<ExecutionReturnStage, string>;
  returnedTo: (conversation: string) => string;
  deliveryUnknown: string;
  deliveryRefused: (code: string) => string;
  deliveryNoReceipt: string;
  deliveryMismatch: string;
  transportRef: (value: string) => string;
  deliveredNotAccepted: string;
  securityNote: string;
}

const STRINGS: Record<"en" | "zh-CN", Strings> = {
  en: {
    heading: "T3 Code",
    rail: "Threads",
    project: "Project",
    projectNone: "Not projected",
    newThread: "＋ New thread",
    newThreadNote:
      "Creating a thread is not permitted from this surface — no launch authority here.",
    searchLabel: "Search threads",
    searchPlaceholder: "Search threads",
    thisAttempt: "THIS ATTEMPT",
    working: "WORKING",
    settled: (count) => `SETTLED · ${count}`,
    noThreads: "No code threads are projected here.",
    noMatch: "No threads match.",
    threadsUnder: (count) => `${count} thread${count === 1 ? "" : "s"}`,
    environments: "Environments",
    environmentNone: "No environment projected.",
    manageEnvironments: "Manage environments →",
    manageNote: "Environment management is not connected.",
    railToggle: (open) => (open ? "Hide threads" : "Show threads"),
    openSession: "Open coding session →",
    environmentUnknown:
      "The environment for this thread is not known, so no deep link is shown.",
    attemptLabel: "Attempt",
    evaluated: "Evaluated",
    harnessUnknown: "Harness not observed",
    notObserved: "Not observed",
    unknownReason: (reason) => `Unknown · ${reason}`,
    threadLabel: (threadId) => `T3 thread ${threadId}`,
    attemptTitle: (attemptId) => `Attempt ${attemptId}`,
    pid: (value) => `pid ${value}`,
    started: "started",
    factsHeading: "Thread facts",
    exactlyOneThread: "Exactly one thread",
    exactlyOneHarness: "Exactly one harness",
    proven: "PROVEN",
    violated: "VIOLATED",
    unknown: "UNKNOWN",
    t3Thread: "T3 thread",
    run: "Run",
    harness: "Harness",
    duplicates: "Duplicate launchers",
    duplicatesKinds: {
      dsh_direct: "direct DSH process",
      codex_cli: "Codex CLI process",
      second_t3_thread: "second T3 thread",
      other: "other launcher",
    },
    duplicatesNone: "None observed",
    duplicatesObserved: "Observed",
    threadsForKey: "Threads under this key",
    methodHeading: "Freshness & evidence",
    fresh: { fresh: "fresh", stale: "stale", absent: "absent", unknown: "unknown" },
    evidenceRefs: "Evidence references",
    refusalTitle: "Attempt evidence refused",
    refusalBody:
      "The Fleet per-attempt read returned a typed refusal; no attempt facts are shown.",
    unavailableTitle: "Attempt observation unavailable",
    pending: "Reading the attempt observation…",
    notConnected: "The T3 attempt reader is not connected to this workspace.",
    signIn: "Sign in with Workspace access to read attempt observations.",
    invalidId: "This run id is not a readable attempt id; nothing was fetched.",
    activityHeading: "Recorded activity",
    activityFootnote:
      "Recorded candidate events only — not a live tool stream or model reasoning.",
    activityNotRetained: "Activity is not retained for this attempt yet.",
    activitySelectionMissing:
      "Activity selection (work, job, attempt) is not projected for this thread.",
    activityNotConnected: "Retained activity is not connected on this host.",
    activityReading: "Reading retained activity…",
    activityZero:
      "No retained activity in this sample; this does not establish an idle worker.",
    activityPartial: "This sample is partial.",
    activityOmitted: (count) =>
      `${count} additional event${count === 1 ? "" : "s"} omitted from this sample.`,
    activityCategory: {
      TURN_COMPLETED: "Turn completion recorded",
      TURN_ACTIVITY: "Turn activity",
      ITEM_ACTIVITY: "Item activity",
      TOOL_ACTIVITY: "Tool activity",
      MODEL_ACTIVITY: "Model activity",
      OTHER_REDACTED_EVENT: "Other activity (content withheld)",
    },
    returnTextHeading: "Return text",
    relatedHeading: "Related tasks",
    relatedNotProjected: "Related tasks are not projected yet.",
    composerLabel: "Direction for the next turn",
    composerNote: "New direction queues for the next turn. Current work continues.",
    composerNotConnected:
      "Not connected — this surface never sends to or interrupts the thread.",
    composerQueue: "Queue direction",
    panelsLabel: "Work panels",
    changesTab: "Changes",
    changesTabCount: (count) => `Changes · ${count}`,
    browserTab: "Browser",
    terminalTab: "Terminal",
    browserTitle: "Browser is not connected",
    browserBody:
      "No browser session is projected on this surface; it never drives a live page from here.",
    branch: "Branch",
    noBranch: "No branch recorded",
    filesHeading: "Changed files",
    noFiles: "No file refs recorded",
    diffHeading: "Working diff",
    changesMissing: "Working changes are not projected yet",
    changesSource:
      "Source: a mastermind.execution_return/v1 record for this attempt — none is connected yet.",
    prHeading: "Pull request",
    prNumber: (value) => `#${value}`,
    prNone: "Not observed",
    merge: "Merge",
    installation: "Installation",
    mergeMerged: "Merged",
    mergeNotMerged: "Not merged",
    mergeUnknown: "Unknown",
    installClaimed: "Claimed, unproven",
    installNone: "None claimed",
    terminalMissing: "Terminal output is not projected yet",
    terminalSource:
      "Source: the mastermind.execution_return/v1 check rows for this attempt — no record is connected.",
    checksHeading: "Recorded checks",
    noChecks: "No checks recorded in this return.",
    checksStateLabel: "Checks",
    checksState: { green: "Green", failed: "Failed", unknown: "Unknown" },
    checkMark: { success: "✓", failure: "✗", skipped: "–", unknown: "?" },
    returnHeading: "Result returns to OS launch team",
    returnPending: "Return pending · Engineering receives the result here.",
    returnStage: "Stage",
    stage: {
      result_only: "Result only",
      branch_pushed: "Branch pushed",
      pr_open: "Pull request open",
      checks_green: "Checks green",
      checks_failed: "Checks failed",
      merged: "Merged",
      installed_unknown: "Merged — install claim unproven",
    },
    returnedTo: (conversation) => `Returned to ${conversation}`,
    deliveryUnknown:
      "Delivery unknown — the send was ambiguous; it is never auto-retried.",
    deliveryRefused: (code) => `Refused · ${code}`,
    deliveryNoReceipt: "No delivery receipt yet — return pending.",
    deliveryMismatch: "Receipt does not match this return.",
    transportRef: (value) => `Transport ref ${value}`,
    deliveredNotAccepted:
      "Delivered ≠ accepted — delivery is an observation; acceptance is a separate act.",
    securityNote:
      "No provider keys live in this app; the deep link opens the native client with its own authentication.",
  },
  "zh-CN": {
    heading: "T3 Code",
    rail: "线程",
    project: "项目",
    projectNone: "未投影",
    newThread: "＋ 新建线程",
    newThreadNote: "此界面无启动权限，不允许在此创建线程。",
    searchLabel: "搜索线程",
    searchPlaceholder: "搜索线程",
    thisAttempt: "本次尝试",
    working: "进行中",
    settled: (count) => `已落定 · ${count}`,
    noThreads: "此处尚未投影任何编码线程。",
    noMatch: "没有匹配的线程。",
    threadsUnder: (count) => `${count} 个线程`,
    environments: "环境",
    environmentNone: "未投影环境。",
    manageEnvironments: "管理环境 →",
    manageNote: "环境管理尚未连接。",
    railToggle: (open) => (open ? "收起线程" : "展开线程"),
    openSession: "打开编码会话 →",
    environmentUnknown: "此线程的环境未知，因此不显示深层链接。",
    attemptLabel: "尝试",
    evaluated: "评估于",
    harnessUnknown: "执行器未观测",
    notObserved: "未观测",
    unknownReason: (reason) => `未知 · ${reason}`,
    threadLabel: (threadId) => `T3 线程 ${threadId}`,
    attemptTitle: (attemptId) => `尝试 ${attemptId}`,
    pid: (value) => `进程号 ${value}`,
    started: "启动于",
    factsHeading: "线程事实",
    exactlyOneThread: "唯一线程",
    exactlyOneHarness: "唯一执行器",
    proven: "已证实",
    violated: "已违反",
    unknown: "未知",
    t3Thread: "T3 线程",
    run: "运行",
    harness: "执行器",
    duplicates: "重复启动器",
    duplicatesKinds: {
      dsh_direct: "DSH 直启进程",
      codex_cli: "Codex CLI 进程",
      second_t3_thread: "第二个 T3 线程",
      other: "其他启动器",
    },
    duplicatesNone: "未观测到",
    duplicatesObserved: "已观测",
    threadsForKey: "此键下线程数",
    methodHeading: "新鲜度与证据",
    fresh: { fresh: "新鲜", stale: "过期", absent: "缺失", unknown: "未知" },
    evidenceRefs: "证据引用",
    refusalTitle: "尝试证据被拒绝",
    refusalBody: "Fleet 逐次尝试读取返回了类型化拒绝；不展示任何尝试事实。",
    unavailableTitle: "尝试观测不可用",
    pending: "正在读取尝试观测…",
    notConnected: "此工作区尚未连接 T3 尝试读取器。",
    signIn: "登录具有 Workspace 权限的账号后查看尝试观测。",
    invalidId: "此运行编号不是可读取的尝试编号，未进行任何读取。",
    activityHeading: "已记录活动",
    activityFootnote: "仅包含已记录的候选事件——不是实时工具流或模型内部推理。",
    activityNotRetained: "此尝试的活动尚未留存。",
    activitySelectionMissing: "此线程未投影活动选择（工作、任务、尝试）。",
    activityNotConnected: "此主机尚未连接已留存活动读取。",
    activityReading: "正在读取已留存活动…",
    activityZero: "此样本中没有已留存活动；不能据此推断代理空闲。",
    activityPartial: "此样本不完整。",
    activityOmitted: (count) => `样本中另有 ${count} 条记录未显示。`,
    activityCategory: {
      TURN_COMPLETED: "回合完成记录",
      TURN_ACTIVITY: "回合活动",
      ITEM_ACTIVITY: "工作项活动",
      TOOL_ACTIVITY: "工具活动",
      MODEL_ACTIVITY: "模型活动",
      OTHER_REDACTED_EVENT: "其他活动（内容已隐去）",
    },
    returnTextHeading: "返回文本",
    relatedHeading: "相关任务",
    relatedNotProjected: "相关任务尚未投影。",
    composerLabel: "下一回合的方向",
    composerNote: "新方向排队到下一回合。当前工作继续。",
    composerNotConnected: "未连接——此界面绝不向线程发送消息或中断线程。",
    composerQueue: "排队方向",
    panelsLabel: "工作面板",
    changesTab: "变更",
    changesTabCount: (count) => `变更 · ${count}`,
    browserTab: "浏览器",
    terminalTab: "终端",
    browserTitle: "浏览器未连接",
    browserBody: "此界面未投影任何浏览器会话；绝不在此驱动实时页面。",
    branch: "分支",
    noBranch: "未记录分支",
    filesHeading: "已变更文件",
    noFiles: "未记录文件引用",
    diffHeading: "工作差异",
    changesMissing: "工作变更尚未投影",
    changesSource: "来源：此尝试的 mastermind.execution_return/v1 记录——尚未连接。",
    prHeading: "拉取请求",
    prNumber: (value) => `#${value}`,
    prNone: "未观测",
    merge: "合并",
    installation: "安装",
    mergeMerged: "已合并",
    mergeNotMerged: "未合并",
    mergeUnknown: "未知",
    installClaimed: "已声明，未证实",
    installNone: "未声明",
    terminalMissing: "终端输出尚未投影",
    terminalSource: "来源：此尝试的 mastermind.execution_return/v1 检查行——尚未连接记录。",
    checksHeading: "已记录检查",
    noChecks: "此返回中未记录检查。",
    checksStateLabel: "检查",
    checksState: { green: "通过", failed: "失败", unknown: "未知" },
    checkMark: { success: "✓", failure: "✗", skipped: "–", unknown: "?" },
    returnHeading: "结果返回 OS 启动团队",
    returnPending: "返回待定 · 工程团队在此接收结果。",
    returnStage: "阶段",
    stage: {
      result_only: "仅结果",
      branch_pushed: "分支已推送",
      pr_open: "拉取请求已打开",
      checks_green: "检查通过",
      checks_failed: "检查失败",
      merged: "已合并",
      installed_unknown: "已合并——安装声明未证实",
    },
    returnedTo: (conversation) => `已返回到 ${conversation}`,
    deliveryUnknown: "交付未知——发送结果不明确；绝不自动重试。",
    deliveryRefused: (code) => `已拒绝 · ${code}`,
    deliveryNoReceipt: "尚无交付回执——返回待定。",
    deliveryMismatch: "回执与该返回不匹配。",
    transportRef: (value) => `传输引用 ${value}`,
    deliveredNotAccepted: "已交付 ≠ 已接受——交付是观测；接受是另一个行为。",
    securityNote: "此应用不保存任何提供商密钥；深层链接使用原生客户端自身的身份验证。",
  },
};

/** A diff block renders ONLY when the record carries real diff-shaped text;
 *  prose results never masquerade as diffs. */
function diffText(text: string | null): string | null {
  if (!text) return null;
  const head = text.slice(0, 400);
  if (head.startsWith("diff --git ")) return text;
  if (head.startsWith("--- ") && head.includes("\n@@")) return text;
  return null;
}

/** Environment for the attempt thread's deep link: an exact projected thread
 *  match, else a single shared environment. Unknown stays unknown — the link
 *  is simply not rendered. */
function resolveEnvironment(
  threads: readonly T3ThreadProjection[],
  threadId: string | null,
): string | null {
  if (threadId) {
    const envs = new Set(
      threads.filter((x) => x.threadId === threadId).map((x) => x.environment),
    );
    if (envs.size === 1) return [...envs][0] ?? null;
  }
  if (threads.length > 0) {
    const envs = new Set(threads.map((x) => x.environment));
    if (envs.size === 1) return [...envs][0] ?? null;
  }
  return null;
}

export interface CodeWorkbenchProps {
  locale?: "en" | "zh-CN";
  host?: unknown;
  attemptId: string;
  projection?: T3ProjectionRead;
  /** Director F's parsed mastermind.execution_return/v1 record; null = none
   *  projected (honest states downstream — never fixture data). */
  executionReturn?: ExecutionReturnRecord | null;
  deliveryReceipt?: ExecutionReturnDeliveryReceipt | null;
  /** Selection ids for the retained-activity read; absent → honest note. */
  activitySelection?: ActivitySelection | null;
}

export function CodeWorkbench({
  locale = "en",
  host,
  attemptId,
  projection,
  executionReturn = null,
  deliveryReceipt = null,
  activitySelection = null,
}: CodeWorkbenchProps) {
  const t = STRINGS[locale];
  const uid = useId().replace(/[^a-zA-Z0-9-]/g, "");
  const fleet = useT3AttemptFleetRead(host, attemptId);
  const activity = useRetainedActivityRead(host, activitySelection);
  const [needle, setNeedle] = useState("");
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [panel, setPanel] = useState<"changes" | "browser" | "terminal">("changes");

  const fleetDoc = fleet.read.state === "AVAILABLE" ? fleet.read.document : null;
  const attemptDoc = fleetDoc?.kind === "attempt" ? fleetDoc : null;
  const attempt = attemptDoc?.attempt ?? null;
  const attemptThreadId = attempt?.t3_thread.thread_id ?? null;
  const projectionThreads =
    projection?.kind === "AVAILABLE" ? projection.list.threads : [];
  const environment = resolveEnvironment(projectionThreads, attemptThreadId);
  const matched = attemptThreadId
    ? projectionThreads.find((x) => x.threadId === attemptThreadId)
    : undefined;
  const when = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value))
      : t.notObserved;

  const matches = (label: string, id: string) =>
    !needle ||
    label.toLowerCase().includes(needle.toLowerCase()) ||
    id.toLowerCase().includes(needle.toLowerCase());
  const workingRows = projectionThreads
    .filter((x) => x.runState !== "idle")
    .filter((x) => matches(x.title ?? t.threadLabel(x.threadId), x.threadId));
  const settledRows = projectionThreads
    .filter((x) => x.runState === "idle")
    .filter((x) => matches(x.title ?? t.threadLabel(x.threadId), x.threadId));
  const repositories = [...new Set(projectionThreads.map((x) => x.repository).filter((x): x is string => !!x))];
  const environments = [...new Set(projectionThreads.map((x) => x.environment))];
  const attemptRowLabel = attemptThreadId
    ? matched?.title ?? t.threadLabel(attemptThreadId)
    : null;
  const attemptRowVisible =
    !!attemptRowLabel && matches(attemptRowLabel, attemptThreadId ?? "");

  const activityRead = activity.state === "READ" ? activity.read : null;
  const activityRows =
    activityRead?.availability === "AVAILABLE" ? activityRead.rows : null;

  const title = matched?.title ?? (attemptThreadId ? t.threadLabel(attemptThreadId) : t.attemptTitle(attemptId));
  const harness = attempt?.harness_process;
  const subtitle = !attempt
    ? null
    : harness && harness.pid !== null
      ? [harness.provider, harness.model, t.pid(harness.pid)].filter(Boolean).join(" · ")
      : `${t.harnessUnknown} · ${harness?.unknown_reason ?? t.notObserved}`;
  const record = executionReturn;
  const recordDiff = diffText(record?.result.text ?? null);

  const tabOrder = ["changes", "browser", "terminal"] as const;
  const onTabsKeyDown = (event: React.KeyboardEvent) => {
    const index = tabOrder.indexOf(panel);
    let next: number | null = null;
    if (event.key === "ArrowRight") next = (index + 1) % tabOrder.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabOrder.length) % tabOrder.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabOrder.length - 1;
    if (next === null) return;
    event.preventDefault();
    const target = tabOrder[next]!;
    setPanel(target);
    document.getElementById(`${uid}-tab-${target}`)?.focus();
  };

  return (
    <section className="mm-code mm-workbench" aria-labelledby={`${uid}-heading`} data-testid="mm-code-workbench">
      <h2 id={`${uid}-heading`} tabIndex={-1} className="mm-visually-hidden">{t.heading}</h2>
      <button
        type="button"
        className="mm-rail-toggle"
        aria-expanded={!railCollapsed}
        aria-controls={`${uid}-rail`}
        onClick={() => setRailCollapsed((value) => !value)}
      >
        {t.railToggle(!railCollapsed)}
      </button>
      <div className="mm-workbench-grid">
        {/* ── Column 1 · thread rail (248px) ─────────────────────────── */}
        <aside className="mm-code-rail" id={`${uid}-rail`} data-testid="mm-code-rail" data-collapsed={railCollapsed} aria-label={t.rail}>
          <label className="mm-code-rail-project">
            <span>{t.project}</span>
            <select disabled aria-label={t.project}>
              {repositories.length > 0 ? (
                repositories.map((repo) => <option key={repo} value={repo}>{repo}</option>)
              ) : (
                <option value="">{t.projectNone}</option>
              )}
            </select>
          </label>
          <button type="button" className="mm-code-new-thread" disabled title={t.newThreadNote}>
            {t.newThread}
          </button>
          <input
            type="search"
            className="mm-code-search"
            aria-label={t.searchLabel}
            placeholder={t.searchPlaceholder}
            value={needle}
            onChange={(event) => setNeedle(event.target.value)}
            disabled={projectionThreads.length === 0 && !attemptThreadId}
          />
          <div className="mm-code-rail-groups">
            {attemptRowVisible && attemptRowLabel && attemptThreadId ? (
              <section className="mm-code-rail-group" aria-label={t.thisAttempt}>
                <h3>{t.thisAttempt}</h3>
                <p className="mm-code-thread-row" data-run-state={matched?.runState ?? "unknown"}>
                  <span className="mm-code-thread-row-title">{attemptRowLabel}</span>
                  <span className="mm-chip mm-chip-state" data-state="attempt">{attempt?.t3_thread.state ?? t.unknown}</span>
                  {attempt?.harness_process.model ? (
                    <small>{[attempt.harness_process.provider, attempt.harness_process.model].filter(Boolean).join(" · ")}</small>
                  ) : null}
                </p>
              </section>
            ) : null}
            {projectionThreads.length === 0 && !attemptRowVisible ? (
              <p className="mm-code-rail-empty">{t.noThreads}</p>
            ) : needle && workingRows.length === 0 && settledRows.length === 0 && !attemptRowVisible ? (
              <p className="mm-code-rail-empty">{t.noMatch}</p>
            ) : (
              <>
                {workingRows.length > 0 ? (
                  <section className="mm-code-rail-group" aria-label={t.working}>
                    <h3>{t.working}</h3>
                    {workingRows.map((x) => (
                      <p key={`${x.environment}/${x.threadId}`} className="mm-code-thread-row" data-run-state={x.runState}>
                        <span className="mm-code-thread-row-title">{x.title ?? t.threadLabel(x.threadId)}</span>
                        <span className="mm-chip mm-chip-state" data-state={x.runState === "running" ? "running" : x.runState === "blocked" ? "declined" : "unknown"}>{x.runState}</span>
                        <small><code>{x.environment}</code></small>
                      </p>
                    ))}
                  </section>
                ) : null}
                {settledRows.length > 0 ? (
                  <details className="mm-code-rail-group mm-code-rail-settled">
                    <summary>{t.settled(settledRows.length)} ›</summary>
                    {settledRows.map((x) => (
                      <p key={`${x.environment}/${x.threadId}`} className="mm-code-thread-row" data-run-state="idle">
                        <span className="mm-code-thread-row-title">{x.title ?? t.threadLabel(x.threadId)}</span>
                        <span className="mm-chip mm-chip-state" data-state="terminal">{x.runState}</span>
                        <small><code>{x.environment}</code></small>
                      </p>
                    ))}
                  </details>
                ) : null}
              </>
            )}
          </div>
          <div className="mm-code-rail-env">
            <h3>{t.environments}</h3>
            {environments.length === 0 ? (
              <p className="mm-code-rail-empty">{t.environmentNone}</p>
            ) : (
              <ul>
                {environments.map((env) => (
                  <li key={env}>
                    <code>{env}</code>
                    {" · "}
                    {t.threadsUnder(projectionThreads.filter((x) => x.environment === env).length)}
                  </li>
                ))}
              </ul>
            )}
            <button type="button" disabled title={t.manageNote}>{t.manageEnvironments}</button>
          </div>
        </aside>

        {/* ── Column 2 · code conversation (640px) ───────────────────── */}
        <div className="mm-code-conversation">
          <header className="mm-code-thread-header">
            <div>
              <p className="mm-eyebrow">{t.attemptLabel}</p>
              <h3 className="mm-code-thread-title" tabIndex={-1}>{title}</h3>
              {subtitle ? <p className="mm-code-thread-subtitle">{subtitle}</p> : null}
              <p className="mm-code-thread-meta">
                <code>{attemptId}</code>
                {attemptDoc ? <small> · {t.evaluated} {when(attemptDoc.evaluated_at_utc)}</small> : null}
              </p>
            </div>
            {attemptThreadId && environment ? (
              <a className="mm-code-open" href={t3ThreadUrl(environment, attemptThreadId)} target="_blank" rel="noreferrer">
                {t.openSession}
              </a>
            ) : attemptThreadId ? (
              <p className="muted mm-code-env-unknown">{t.environmentUnknown}</p>
            ) : null}
          </header>

          <AttemptFacts
            fleet={fleet.read}
            permitted={fleet.permitted}
            selectable={fleet.selectable}
            attempt={attempt}
            when={when}
            t={t}
          />

          <ActivityTrail state={activity} selectionProvided={!!activitySelection} t={t} />

          {record?.result.text && !recordDiff ? (
            <article className="mm-code-card" aria-label={t.returnTextHeading}>
              <h4 tabIndex={-1}>{t.returnTextHeading}</h4>
              <p className="mm-code-return-text">{record.result.text}</p>
            </article>
          ) : null}

          <p className="mm-code-related">{t.relatedHeading} · {t.relatedNotProjected}</p>

          <div className="mm-code-composer" data-testid="mm-code-composer">
            <label htmlFor={`${uid}-composer`}>{t.composerLabel}</label>
            <textarea
              id={`${uid}-composer`}
              disabled
              placeholder={t.composerNotConnected}
              aria-describedby={`${uid}-composer-note`}
            />
            <button type="button" disabled>{t.composerQueue}</button>
            <p className="muted" id={`${uid}-composer-note`}>{t.composerNote}</p>
          </div>
          <p className="muted mm-code-security">{t.securityNote}</p>
        </div>

        {/* ── Column 3 · work panels (480px) ─────────────────────────── */}
        <div className="mm-code-panels" data-testid="mm-code-panels">
          <div className="mm-code-tabs" role="tablist" aria-label={t.panelsLabel} onKeyDown={onTabsKeyDown}>
            {tabOrder.map((id) => (
              <button
                key={id}
                id={`${uid}-tab-${id}`}
                role="tab"
                type="button"
                aria-selected={panel === id}
                aria-controls={`${uid}-panel-${id}`}
                tabIndex={panel === id ? 0 : -1}
                onClick={() => setPanel(id)}
              >
                {id === "changes"
                  ? record && record.result.artifact_refs.length > 0
                    ? t.changesTabCount(record.result.artifact_refs.length)
                    : t.changesTab
                  : id === "browser" ? t.browserTab : t.terminalTab}
              </button>
            ))}
          </div>
          <div
            id={`${uid}-panel-changes`}
            role="tabpanel"
            aria-labelledby={`${uid}-tab-changes`}
            tabIndex={0}
            className="mm-code-tabpanel"
            hidden={panel !== "changes"}
            data-testid="mm-code-changes"
          >
            <ChangesPanel record={record} diff={recordDiff} t={t} />
          </div>
          <div
            id={`${uid}-panel-browser`}
            role="tabpanel"
            aria-labelledby={`${uid}-tab-browser`}
            tabIndex={0}
            className="mm-code-tabpanel"
            hidden={panel !== "browser"}
          >
            <div className="mm-code-honest" role="status">
              <p className="mm-eyebrow">{t.browserTitle}</p>
              <p>{t.browserBody}</p>
            </div>
          </div>
          <div
            id={`${uid}-panel-terminal`}
            role="tabpanel"
            aria-labelledby={`${uid}-tab-terminal`}
            tabIndex={0}
            className="mm-code-tabpanel"
            hidden={panel !== "terminal"}
            data-testid="mm-code-terminal"
          >
            <TerminalPanel record={record} t={t} />
          </div>
          <ReturnFooter record={record} receipt={deliveryReceipt} t={t} />
        </div>
      </div>
    </section>
  );
}

/** VERDICT chip — same vocabulary as the Fleet block (PROVEN/VIOLATED/UNKNOWN). */
function VerdictChip({ verdict, label, reason, t }: {
  verdict: InvariantVerdict; label: string; reason: string | null; t: Strings;
}) {
  return (
    <span className={`mm-chip mm-verdict-${verdict.toLowerCase()}`}>
      <b>{label}</b>{" "}
      {verdict === "PROVEN" ? t.proven : verdict === "VIOLATED" ? t.violated : t.unknown}
      {verdict === "UNKNOWN" && reason ? <small> · {reason}</small> : null}
    </span>
  );
}

function AttemptFacts({ fleet, permitted, selectable, attempt, when, t }: {
  fleet: ReturnType<typeof useT3AttemptFleetRead>["read"];
  permitted: boolean;
  selectable: boolean;
  attempt: T3Attempt | null;
  when: (value: string | null) => string;
  t: Strings;
}) {
  if (!selectable) {
    return (
      <article className="mm-code-card mm-code-honest" data-testid="mm-code-attempt-facts" role="status">
        <p>{t.invalidId}</p>
      </article>
    );
  }
  if (fleet.state === "NOT_STARTED") {
    return (
      <article className="mm-code-card mm-code-honest" data-testid="mm-code-attempt-facts" role="status">
        <p>{permitted ? t.notConnected : t.signIn}</p>
      </article>
    );
  }
  if (fleet.state === "PENDING") {
    return (
      <article className="mm-code-card mm-code-honest" data-testid="mm-code-attempt-facts" aria-busy="true" role="status">
        <p>{t.pending}</p>
      </article>
    );
  }
  if (fleet.state === "UNAVAILABLE") {
    return (
      <article className="mm-code-card mm-code-honest" data-testid="mm-code-attempt-facts" role="status">
        <p className="mm-eyebrow">{t.unavailableTitle}</p>
        <p><code>{fleet.reason}</code></p>
      </article>
    );
  }
  if (fleet.document.kind === "refusal") {
    return (
      <article className="mm-code-card mm-code-honest" data-testid="mm-code-attempt-refusal" role="status">
        <p className="mm-eyebrow">{t.refusalTitle}</p>
        <p>{t.refusalBody}</p>
        <p><code>{fleet.document.refusal}</code></p>
      </article>
    );
  }
  if (!attempt) return null;
  const thread = attempt.t3_thread, harness = attempt.harness_process, duplicate = attempt.duplicate_launcher;
  return (
    <article className="mm-code-card" data-testid="mm-code-attempt-facts" aria-label={t.factsHeading}>
      <h4 tabIndex={-1}>{t.factsHeading}</h4>
      <p className="mm-code-verdicts">
        <VerdictChip verdict={attempt.invariant.exactly_one_thread} label={t.exactlyOneThread}
          reason={thread.unknown_reason ?? attempt.thread_count_reason} t={t} />
        <VerdictChip verdict={attempt.invariant.exactly_one_harness} label={t.exactlyOneHarness}
          reason={harness.unknown_reason ?? attempt.harness_count_reason} t={t} />
      </p>
      <dl className="mm-code-facts">
        <div>
          <dt>{t.t3Thread}</dt>
          <dd>
            {thread.thread_id ? (
              <><code>{thread.thread_id}</code>{thread.state ? <small> · {thread.state}</small> : null}</>
            ) : (
              <span className="mm-code-unknown">{t.unknownReason(thread.unknown_reason ?? t.notObserved)}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>{t.run}</dt>
          <dd>{thread.run_id ? <code>{thread.run_id}</code> : <span className="mm-code-unknown">{t.notObserved}</span>}</dd>
        </div>
        <div>
          <dt>{t.harness}</dt>
          <dd>
            {harness.pid !== null ? (
              <>
                <code>{t.pid(harness.pid)}</code>
                {harness.provider || harness.model ? <small> · {[harness.provider, harness.model].filter(Boolean).join(" · ")}</small> : null}
                {harness.start_time ? <small> · {t.started} {when(harness.start_time)}</small> : null}
              </>
            ) : (
              <span className="mm-code-unknown">{t.unknownReason(harness.unknown_reason ?? t.notObserved)}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>{t.duplicates}</dt>
          <dd>
            {duplicate.observed === true ? (
              <span className="mm-code-violated">
                {t.duplicatesObserved} · {duplicate.kinds.map((kind) => t.duplicatesKinds[kind]).join(" · ")}
              </span>
            ) : duplicate.observed === false ? (
              t.duplicatesNone
            ) : (
              <span className="mm-code-unknown">{t.unknownReason(duplicate.unknown_reason ?? t.notObserved)}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>{t.threadsForKey}</dt>
          <dd>
            {attempt.thread_count_for_key !== null ? (
              String(attempt.thread_count_for_key)
            ) : (
              <span className="mm-code-unknown">{t.unknownReason(attempt.thread_count_reason ?? t.notObserved)}</span>
            )}
          </dd>
        </div>
      </dl>
      <details className="mm-code-evidence">
        <summary>{t.methodHeading}</summary>
        <p>
          <code>{attempt.freshness.adapter_state}</code> · <code>{attempt.freshness.census}</code> · <code>{attempt.freshness.thread_read}</code>
        </p>
        {attempt.evidence_refs.length > 0 ? (
          <ul aria-label={t.evidenceRefs}>
            {attempt.evidence_refs.map((ref) => <li key={ref}><code>{ref}</code></li>)}
          </ul>
        ) : null}
      </details>
    </article>
  );
}

function ActivityTrail({ state, selectionProvided, t }: {
  state: ReturnType<typeof useRetainedActivityRead>;
  selectionProvided: boolean;
  t: Strings;
}) {
  const body = () => {
    if (!selectionProvided) return <p className="mm-code-honest-line">{t.activitySelectionMissing}</p>;
    if (state.state === "NOT_STARTED") return <p className="mm-code-honest-line">{t.activityNotConnected}</p>;
    if (state.state === "PENDING") return <p className="mm-code-honest-line" aria-busy="true">{t.activityReading}</p>;
    if (state.state === "FAILED") return <p className="mm-code-honest-line">{t.activityNotRetained}</p>;
    const read = state.read;
    if (read.availability === "UNAVAILABLE") {
      return (
        <>
          <p className="mm-code-honest-line">{t.activityNotRetained}</p>
          <details className="mm-code-evidence">
            <summary>{read.reasons.join(", ")}</summary>
          </details>
        </>
      );
    }
    if (read.rows.length === 0) return <p className="mm-code-honest-line">{t.activityZero}</p>;
    return (
      <>
        <ol className="mm-code-activity-rows">
          {read.rows.map((row) => (
            <li key={`${row.candidate_event_id}:${row.ordinal_in_candidate}`}>
              <span>{t.activityCategory[row.category] ?? row.category}</span>
              <small> · {row.candidate_recorded_at}</small>
            </li>
          ))}
        </ol>
        {read.coverage === "PARTIAL" || read.sourceTruncated || read.omittedInSample > 0 ? (
          <p className="mm-code-honest-line">
            {read.coverage === "PARTIAL" || read.sourceTruncated ? `${t.activityPartial} ` : ""}
            {read.omittedInSample > 0 ? t.activityOmitted(read.omittedInSample) : ""}
          </p>
        ) : null}
      </>
    );
  };
  return (
    <article className="mm-code-card" data-testid="mm-code-activity" aria-label={t.activityHeading}>
      <h4 tabIndex={-1}>{t.activityHeading}</h4>
      {body()}
      <p className="muted mm-code-activity-footnote">{t.activityFootnote}</p>
    </article>
  );
}

function ChangesPanel({ record, diff, t }: {
  record: ExecutionReturnRecord | null;
  diff: string | null;
  t: Strings;
}) {
  if (!record) {
    return (
      <div className="mm-code-honest" role="status" data-testid="mm-code-changes-missing">
        <p className="mm-eyebrow">{t.changesMissing}</p>
        <p>{t.changesSource}</p>
      </div>
    );
  }
  const github = record.github;
  return (
    <div className="mm-code-changes">
      <dl className="mm-code-facts">
        <div>
          <dt>{t.branch}</dt>
          <dd>{github.branch ? <code>{github.branch}</code> : <span className="mm-code-unknown">{t.noBranch}</span>}</dd>
        </div>
      </dl>
      <h4>{t.prHeading}</h4>
      <dl className="mm-code-facts">
        <div>
          <dt>{t.prHeading}</dt>
          <dd>
            {github.pr_url ? (
              <a href={github.pr_url} target="_blank" rel="noreferrer">{github.pr_url}</a>
            ) : github.pr_number !== null ? (
              t.prNumber(github.pr_number)
            ) : (
              <span className="mm-code-unknown">{t.prNone}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>{t.merge}</dt>
          <dd data-merge={github.merge_state}>
            {github.merge_state === "merged" ? t.mergeMerged : github.merge_state === "not_merged" ? t.mergeNotMerged : t.mergeUnknown}
          </dd>
        </div>
        <div>
          <dt>{t.installation}</dt>
          <dd>{github.installation === "claimed_unproven" ? t.installClaimed : t.installNone}</dd>
        </div>
      </dl>
      <h4>{t.filesHeading}</h4>
      {record.result.artifact_refs.length === 0 ? (
        <p className="mm-code-honest-line">{t.noFiles}</p>
      ) : (
        <ul className="mm-code-files">
          {record.result.artifact_refs.map((ref) => (
            <li key={ref}><code>{ref}</code></li>
          ))}
        </ul>
      )}
      <h4>{t.diffHeading}</h4>
      {diff ? (
        <pre className="mm-code-diff"><code>{diff}</code></pre>
      ) : (
        <p className="mm-code-honest-line">
          {t.changesMissing} · <code>mastermind.execution_return/v1</code>
        </p>
      )}
    </div>
  );
}

function TerminalPanel({ record, t }: { record: ExecutionReturnRecord | null; t: Strings }) {
  if (!record) {
    return (
      <div className="mm-code-honest" role="status" data-testid="mm-code-terminal-missing">
        <p className="mm-eyebrow">{t.terminalMissing}</p>
        <p>{t.terminalSource}</p>
      </div>
    );
  }
  const checks = record.github.checks;
  return (
    <div className="mm-code-terminal">
      <p className="mm-code-terminal-state">
        {t.checksStateLabel}: <b data-checks={record.github.checks_state}>{t.checksState[record.github.checks_state] ?? record.github.checks_state}</b>
      </p>
      <h4>{t.checksHeading}</h4>
      {checks === null || checks.length === 0 ? (
        <p className="mm-code-honest-line">{t.noChecks}</p>
      ) : (
        <ul className="mm-code-checks" aria-label={t.checksHeading}>
          {checks.map((check) => (
            <li key={check.name} data-conclusion={check.conclusion}>
              <span aria-hidden="true">{t.checkMark[check.conclusion]}</span>{" "}
              <code>{check.name}</code>{" "}
              <small>{check.conclusion}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReturnFooter({ record, receipt, t }: {
  record: ExecutionReturnRecord | null;
  receipt: ExecutionReturnDeliveryReceipt | null;
  t: Strings;
}) {
  const receiptMatches = !!receipt && !!record && receipt.return_id === record.return_id;
  const receiptMismatch = !!receipt && !!record && !receiptMatches;
  return (
    <footer className="mm-code-return" data-testid="mm-code-return-footer" aria-label={t.returnHeading}>
      <h4 tabIndex={-1}>{t.returnHeading}</h4>
      {!record ? (
        <p className="mm-code-return-line" data-return="pending">{t.returnPending}</p>
      ) : (
        <>
          <p className="mm-code-return-line">
            <span className="mm-chip mm-chip-state" data-stage={record.stage}>
              {t.returnStage}: {t.stage[record.stage]}
            </span>
          </p>
          <p className="mm-code-return-line" data-return={receiptMatches ? receipt!.state : "none"}>
            {!receipt
              ? t.deliveryNoReceipt
              : receiptMismatch
                ? t.deliveryMismatch
                : receipt.state === "delivered"
                  ? t.returnedTo(receipt.conversation_id)
                  : receipt.state === "unknown"
                    ? t.deliveryUnknown
                    : t.deliveryRefused(receipt.refusal_code ?? "")}
            {receiptMatches && receipt.state === "delivered" ? (
              <small> · {t.transportRef(receipt.transport_ref ?? "")}</small>
            ) : null}
          </p>
        </>
      )}
      <p className="muted">{t.deliveredNotAccepted}</p>
    </footer>
  );
}
