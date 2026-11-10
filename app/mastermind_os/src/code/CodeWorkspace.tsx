import {
  readT3ThreadProjection,
  t3ThreadUrl,
  type T3ProjectionRead,
  type T3ThreadProjection,
} from "./t3-thread-projection";
import type { ActivitySelection } from "../planning/retained-activity";
import type {
  ExecutionReturnDeliveryReceipt,
  ExecutionReturnRecord,
} from "../hermes-native/execution-return-contract";
import { CodeWorkbench } from "./CodeWorkbench";
import "./code.css";

/** TD04/HC07 — Code surface. Without an attempt id this stays the projected
 *  thread list with documented deep links. With a valid attempt id it becomes
 *  the per-attempt workbench (CodeWorkbench): attempt facts from the Fleet
 *  read, work panels from a typed execution_return/v1 record, a retained
 *  activity trail and a return footer. Either way it never embeds an editor
 *  or terminal, and never launches, steers or interrupts a thread. */
const STRINGS = {
  en: {
    heading: "T3 Code",
    headingSummary:
      "Company coding threads on T3 Code. This surface opens the exact native thread; it never embeds an editor or terminal.",
    threadsLabel: "T3 coding threads",
    threadLabel: (threadId: string) => `T3 thread ${threadId}`,
    openThread: "Open in T3 Code ↗",
    environment: "Environment",
    runState: "Run state",
    lastActivity: "Last activity",
    prLink: "Pull request",
    repository: "Repository",
    companyManaged: "Company managed",
    notCompanyManaged: "Not company managed",
    runRunning: "Running",
    runIdle: "Idle",
    runBlocked: "Blocked",
    runUnknown: "Unknown",
    noActivity: "Not observed",
    unavailableTitle: "Code threads are not projected yet",
    unavailableBody:
      "This surface reads the typed T3 thread projection from MastermindMissionHost.t3ThreadProjection. That projection source is not connected on this host — no host implements it yet — so no thread state is shown or inferred.",
    unavailableNote:
      "The source of truth for per-attempt T3 facts is the Fleet per-attempt read (Fleet & Capacity), not this list.",
    unavailableFallback:
      "Open T3 Code directly to inspect threads on the machine that runs them.",
    evidenceHeading: "Projection source",
    securityNote:
      "No provider keys live in this app; the deep link opens the native client with its own authentication.",
  },
  "zh-CN": {
    heading: "T3 Code",
    headingSummary:
      "T3 Code 上的公司编码线程。此界面打开确切的原生线程；绝不内嵌编辑器或终端。",
    threadsLabel: "T3 编码线程",
    threadLabel: (threadId: string) => `T3 线程 ${threadId}`,
    openThread: "在 T3 Code 中打开 ↗",
    environment: "环境",
    runState: "运行状态",
    lastActivity: "最近活动",
    prLink: "拉取请求",
    repository: "代码库",
    companyManaged: "公司托管",
    notCompanyManaged: "非公司托管",
    runRunning: "运行中",
    runIdle: "空闲",
    runBlocked: "受阻",
    runUnknown: "未知",
    noActivity: "未观测",
    unavailableTitle: "编码线程尚未投影",
    unavailableBody:
      "此界面通过 MastermindMissionHost.t3ThreadProjection 读取类型化的 T3 线程投影。该投影来源未连接此主机——目前尚无主机实现它——因此不显示也不推断任何线程状态。",
    unavailableNote:
      "每次尝试的 T3 事实以 Fleet 的逐次尝试读取为准（Fleet 与容量），而非此列表。",
    unavailableFallback: "请直接打开 T3 Code，在运行线程的机器上查看。",
    evidenceHeading: "投影来源",
    securityNote:
      "此应用不保存任何提供商密钥；深层链接使用原生客户端自身的身份验证。",
  },
};

function runStateLabel(
  state: T3ThreadProjection["runState"],
  t: typeof STRINGS.en,
): string {
  if (state === "running") return t.runRunning;
  if (state === "idle") return t.runIdle;
  if (state === "blocked") return t.runBlocked;
  return t.runUnknown;
}

export function CodeWorkspace({
  locale = "en",
  projection,
  host,
  attemptId = null,
  executionReturn = null,
  deliveryReceipt = null,
  activitySelection = null,
}: {
  locale?: "en" | "zh-CN";
  /** Pre-read projection (tests); omitted → read from the host facade. */
  projection?: T3ProjectionRead;
  host?: unknown;
  /** Attempt id from the run/fleet context; when set (and grammar-valid) the
   *  per-attempt workbench reads the attempt facts once through
   *  host.readT3AttemptFleet. Default null = the projected thread list. */
  attemptId?: string | null;
  /** Parsed mastermind.execution_return/v1 record for the attempt; null =
   *  no return projected yet (honest states downstream). */
  executionReturn?: ExecutionReturnRecord | null;
  /** Optional parsed delivery receipt for the same return. */
  deliveryReceipt?: ExecutionReturnDeliveryReceipt | null;
  /** Selection ids for the retained-activity read; absent → honest note. */
  activitySelection?: ActivitySelection | null;
}) {
  const t = STRINGS[locale];
  const read =
    projection ??
    readT3ThreadProjection(
      host ??
        (typeof window !== "undefined"
          ? (window as { MastermindMissionHost?: unknown })
              .MastermindMissionHost
          : undefined),
    );

  if (attemptId != null) {
    return (
      <CodeWorkbench
        locale={locale}
        host={host}
        attemptId={attemptId}
        projection={read}
        executionReturn={executionReturn}
        deliveryReceipt={deliveryReceipt}
        activitySelection={activitySelection}
      />
    );
  }

  if (read.kind !== "AVAILABLE") {
    return (
      <section className="mm-code" aria-labelledby="mm-code-heading">
        <h1 id="mm-code-heading" tabIndex={-1}>
          {t.heading}
        </h1>
        <div className="card mm-code-unavailable">
          <p className="mm-eyebrow">{t.unavailableTitle}</p>
          <p>{t.unavailableBody}</p>
          <p className="muted">{t.unavailableNote}</p>
          <p className="muted">{t.unavailableFallback}</p>
          <details className="mm-code-evidence">
            <summary>{t.evidenceHeading}</summary>
            <p>
              <code>
                {read.kind === "UNAVAILABLE"
                  ? read.reason
                  : "SOURCE_READ_PENDING"}
              </code>
            </p>
          </details>
        </div>
        <p className="muted mm-code-security">{t.securityNote}</p>
      </section>
    );
  }

  const threads = read.list.threads;
  return (
    <section className="mm-code" aria-labelledby="mm-code-heading">
      <h1 id="mm-code-heading" tabIndex={-1}>
        {t.heading}
      </h1>
      <p className="muted">{t.headingSummary}</p>
      <ul className="mm-code-threads" aria-label={t.threadsLabel}>
        {threads.map((thread) => {
          const url = t3ThreadUrl(thread.environment, thread.threadId);
          return (
            <li
              key={`${thread.environment}/${thread.threadId}`}
              className="mm-code-thread"
              data-run-state={thread.runState}
            >
              <div className="mm-code-thread-head">
                <h2>{thread.title ?? t.threadLabel(thread.threadId)}</h2>
                <span
                  className="mm-chip mm-chip-state"
                  data-state={
                    thread.runState === "running"
                      ? "running"
                      : thread.runState === "blocked"
                        ? "declined"
                        : thread.runState === "idle"
                          ? "terminal"
                          : "unknown"
                  }
                >
                  {runStateLabel(thread.runState, t)}
                </span>
                <span className="mm-chip">
                  {thread.companyManaged
                    ? t.companyManaged
                    : t.notCompanyManaged}
                </span>
              </div>
              <dl>
                <div>
                  <dt>{t.environment}</dt>
                  <dd>
                    <code>{thread.environment}</code>
                  </dd>
                </div>
                <div>
                  <dt>ID</dt>
                  <dd>
                    <code>{thread.threadId}</code>
                  </dd>
                </div>
                {thread.repository ? (
                  <div>
                    <dt>{t.repository}</dt>
                    <dd>{thread.repository}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>{t.runState}</dt>
                  <dd>{runStateLabel(thread.runState, t)}</dd>
                </div>
                <div>
                  <dt>{t.lastActivity}</dt>
                  <dd>{thread.lastActivity ?? t.noActivity}</dd>
                </div>
                {thread.prLink ? (
                  <div>
                    <dt>{t.prLink}</dt>
                    <dd>
                      <a href={thread.prLink} target="_blank" rel="noreferrer">
                        {thread.prLink}
                      </a>
                    </dd>
                  </div>
                ) : null}
              </dl>
              <a
                className="mm-code-open"
                href={url}
                target="_blank"
                rel="noreferrer"
              >
                {t.openThread}
              </a>
            </li>
          );
        })}
      </ul>
      <p className="muted mm-code-security">{t.securityNote}</p>
    </section>
  );
}
