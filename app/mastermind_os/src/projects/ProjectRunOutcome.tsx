import type { ExecutionReturnStage } from "../hermes-native/execution-return-contract";
import type { DelegatedRunOutcome } from "./delivery-route-run";
import "./project-route-run.css";

/** TD07 — "Run · Result and return path" (node 11GQ-0): the run/result step
 *  AFTER dispatch. The stage vocabulary is the execution-return contract's own
 *  (`EXECUTION_RETURN_STAGES`); when a run exists but its return record is
 *  still null the surface shows the honest "Preparing the result" state — the
 *  coding turn ended, the result is still being assembled — never a guessed
 *  stage. Delivery stays an observation (delivered|unknown|refused) and
 *  acceptance stays closed to not_accepted, exactly like ResultReturnCard. */

type StageLabelKey = Record<ExecutionReturnStage, string>;

interface RunStrings {
  heading: string;
  openCode: string;
  emptyRunBody: string;
  emptyRunNote: string;
  preparing: string;
  preparingBody: string;
  preparingNote: string;
  stageLabel: string;
  stage: StageLabelKey;
  acceptanceChip: string;
  checksGreen: string;
  checksFailed: string;
  checksUnknown: string;
  deliveryDelivered: string;
  deliveryUnknown: string;
  deliveryRefused: string;
  deliveryNotObserved: string;
  deliveryNoReceipt: string;
  deliveredNotAccepted: string;
  refusalCode: (code: string) => string;
  trailColumn: string;
  trailNotProjected: string;
  trailNote: string;
  trailEmpty: string;
  evidenceColumn: string;
  sessionCard: string;
  sessionNote: string;
  attemptId: string;
  rootId: string;
  idempotencyKey: string;
  namespace: string;
  t3Thread: string;
  t3Run: string;
  unknownValue: string;
  notObserved: string;
  artifactsCard: string;
  artifactsNote: string;
  notProjected: string;
  artifactRefs: string;
  checksSummary: string;
  branch: string;
  pullRequest: string;
  resultRow: string;
  resultEmpty: string;
  artifactCount: (count: number) => string;
  checksSummaryLine: (state: string, count: number) => string;
}

const STRINGS: Record<"en" | "zh-CN", RunStrings> = {
  en: {
    heading: "Run and result",
    openCode: "Open coding session →",
    emptyRunBody: "No run is projected for this project yet.",
    emptyRunNote:
      "When a dispatched attempt settles, its execution return, delivery receipt and retained-activity trail appear here.",
    preparing: "Preparing the result",
    preparingBody: "The coding turn has ended. Its result is still being assembled.",
    preparingNote:
      "Engineering will receive the verified files, checks, and source for review here.",
    stageLabel: "Stage",
    stage: {
      result_only: "Result only",
      branch_pushed: "Branch pushed",
      pr_open: "Pull request open",
      checks_green: "Checks green",
      checks_failed: "Checks failed",
      merged: "Merged",
      installed_unknown: "Merged — install claim unproven",
    },
    acceptanceChip: "Not accepted",
    checksGreen: "Green",
    checksFailed: "Failed",
    checksUnknown: "Unknown",
    deliveryDelivered: "Delivered",
    deliveryUnknown: "Delivery unknown",
    deliveryRefused: "Refused",
    deliveryNotObserved: "Not observed",
    deliveryNoReceipt: "No delivery receipt is projected for this return.",
    deliveredNotAccepted:
      "Delivered ≠ accepted — delivery is an observation; acceptance is a separate act.",
    refusalCode: (code) => `Refusal code ${code}`,
    trailColumn: "Execution trail",
    trailNotProjected: "The execution trail is not projected yet.",
    trailNote:
      "The trail is fed by the retained-activity read, which is not wired to this surface yet.",
    trailEmpty: "No trail steps are recorded.",
    evidenceColumn: "Run evidence",
    sessionCard: "Bound session",
    sessionNote: "The bound-session facts arrive with the execution return record.",
    attemptId: "Attempt",
    rootId: "Root",
    idempotencyKey: "Idempotency key",
    namespace: "Authenticated namespace",
    t3Thread: "T3 thread",
    t3Run: "T3 run",
    unknownValue: "Unknown",
    notObserved: "Not observed",
    artifactsCard: "Result artifacts",
    artifactsNote: "Result artifacts arrive with the execution return record.",
    notProjected: "Not projected",
    artifactRefs: "Artifact refs",
    checksSummary: "Checks summary",
    branch: "Branch",
    pullRequest: "Pull request",
    resultRow: "Result",
    resultEmpty: "No result text.",
    artifactCount: (count) => `${count} refs`,
    checksSummaryLine: (state, count) => `${state} · ${count} checks`,
  },
  "zh-CN": {
    heading: "运行与结果",
    openCode: "打开编码会话 →",
    emptyRunBody: "尚无为该项目投影的运行。",
    emptyRunNote:
      "当受派的尝试落定后，其执行返回、交付回执与保留活动轨迹会显示在此。",
    preparing: "正在准备结果",
    preparingBody: "编码回合已结束。其结果仍在组装中。",
    preparingNote: "工程将在此收到经验证的文件、检查与源代码，供审阅。",
    stageLabel: "阶段",
    stage: {
      result_only: "仅结果",
      branch_pushed: "分支已推送",
      pr_open: "拉取请求已打开",
      checks_green: "检查通过",
      checks_failed: "检查失败",
      merged: "已合并",
      installed_unknown: "已合并——安装声明未证实",
    },
    acceptanceChip: "未接受",
    checksGreen: "通过",
    checksFailed: "失败",
    checksUnknown: "未知",
    deliveryDelivered: "已交付",
    deliveryUnknown: "交付未知",
    deliveryRefused: "已拒绝",
    deliveryNotObserved: "未观测",
    deliveryNoReceipt: "该返回尚无已投影的交付回执。",
    deliveredNotAccepted: "已交付 ≠ 已接受——交付是观测；接受是另一个行为。",
    refusalCode: (code) => `拒绝码 ${code}`,
    trailColumn: "执行轨迹",
    trailNotProjected: "执行轨迹尚未投影。",
    trailNote: "轨迹由保留活动读取供给，目前尚未接入此界面。",
    trailEmpty: "未记录任何轨迹步骤。",
    evidenceColumn: "运行证据",
    sessionCard: "绑定会话",
    sessionNote: "绑定会话事实随执行返回记录一同到来。",
    attemptId: "尝试",
    rootId: "根",
    idempotencyKey: "幂等键",
    namespace: "认证命名空间",
    t3Thread: "T3 线程",
    t3Run: "T3 运行",
    unknownValue: "未知",
    notObserved: "未观测",
    artifactsCard: "结果产物",
    artifactsNote: "结果产物随执行返回记录一同到来。",
    notProjected: "未投影",
    artifactRefs: "产物引用",
    checksSummary: "检查摘要",
    branch: "分支",
    pullRequest: "拉取请求",
    resultRow: "结果",
    resultEmpty: "无结果文本。",
    artifactCount: (count) => `${count} 个引用`,
    checksSummaryLine: (state, count) => `${state} · ${count} 项检查`,
  },
};

function checksStateLabel(
  state: "green" | "failed" | "unknown",
  t: RunStrings,
): string {
  if (state === "green") return t.checksGreen;
  if (state === "failed") return t.checksFailed;
  return t.checksUnknown;
}

export function ProjectRunOutcome({
  run,
  locale = "en",
  breadcrumb = null,
  subject = null,
  onOpenCode,
}: {
  /** The settled/settling run's projected outcome; null/undefined = no run
   *  projected yet (the step still renders, naming its missing sources). */
  run: DelegatedRunOutcome | null;
  locale?: "en" | "zh-CN";
  /** Journey breadcrumb ending at this step (e.g. ["Code", "Connect the team
   *  roster", "Run"]); null = omitted — wayfinding chrome, not a fact. */
  breadcrumb?: readonly string[] | null;
  /** Where the run happened (e.g. "Engineering · Mastermind OS"); null = the
   *  heading falls back to the state alone. Never invented here. */
  subject?: string | null;
  onOpenCode?: () => void;
}) {
  const t = STRINGS[locale];
  const record = run?.executionReturn ?? null;
  const receipt = run?.deliveryReceipt ?? null;
  const trail = run?.trail ?? null;
  const hasRun = run !== null && run !== undefined;

  const stateLabel = record ? t.stage[record.stage] : t.preparing;
  const heading = subject ? `${subject} / ${stateLabel}` : stateLabel;

  const receiptMatches =
    receipt !== null && record !== null && receipt.return_id === record.return_id;
  const deliveryChip = !receipt
    ? t.deliveryNotObserved
    : !receiptMatches
      ? t.deliveryNotObserved
      : receipt.state === "delivered"
        ? t.deliveryDelivered
        : receipt.state === "unknown"
          ? t.deliveryUnknown
          : t.deliveryRefused;
  const deliveryData = !receipt || !receiptMatches ? "none" : receipt.state;

  const sessionRows: readonly (readonly [string, string | null])[] = [
    [t.attemptId, record?.attempt.attempt_id ?? null],
    [t.rootId, record?.attempt.root_id ?? null],
    [t.idempotencyKey, record?.attempt.idempotency_key ?? null],
    [t.namespace, record?.attempt.authenticated_namespace ?? null],
    [t.t3Thread, record?.attempt.t3_thread_id ?? null],
    [t.t3Run, record?.attempt.t3_run_id ?? null],
  ];

  return (
    <article
      className="mm-run-outcome"
      aria-labelledby="mm-run-outcome-heading"
      data-run={hasRun ? "projected" : "not-projected"}
    >
      {breadcrumb !== null && breadcrumb.length > 0 ? (
        <p className="mm-run-breadcrumb">{breadcrumb.join(" / ")}</p>
      ) : null}
      <header className="mm-run-head">
        <h4 id="mm-run-outcome-heading" tabIndex={-1}>
          {hasRun ? heading : t.heading}
        </h4>
        {onOpenCode ? (
          <button
            type="button"
            className="mm-run-open-code"
            onClick={onOpenCode}
          >
            {t.openCode}
          </button>
        ) : null}
      </header>
      {!hasRun ? (
        <>
          <p className="mm-run-status-body">{t.emptyRunBody}</p>
          <p className="muted">{t.emptyRunNote}</p>
        </>
      ) : (
        <>
          <p className="mm-run-status">
            {record === null ? (
              <span className="mm-chip" data-run-state="preparing">
                {t.preparing}
              </span>
            ) : (
              <>
                <span className="mm-chip mm-chip-state" data-stage={record.stage}>
                  {t.stageLabel}: {t.stage[record.stage]}
                </span>
                {/* v1 closes acceptance to not_accepted; no accepted branch
                    exists here, same as ResultReturnCard. */}
                <span className="mm-chip" data-acceptance="not_accepted">
                  {t.acceptanceChip}
                </span>
                <span className="mm-chip" data-delivery={deliveryData}>
                  {deliveryChip}
                </span>
              </>
            )}
          </p>
          {record === null ? (
            <>
              <p className="mm-run-status-body">{t.preparingBody}</p>
              <p className="muted">{t.preparingNote}</p>
            </>
          ) : receiptMatches && receipt?.state === "delivered" ? (
            <p className="mm-run-receipt-note">{t.deliveredNotAccepted}</p>
          ) : receiptMatches && receipt?.state === "refused" ? (
            <p className="mm-run-receipt-note">
              {t.refusalCode(receipt.refusal_code ?? "")}
            </p>
          ) : (
            <p className="mm-run-receipt-note">{t.deliveryNoReceipt}</p>
          )}
        </>
      )}
      <div className="mm-run-grid">
        <section className="mm-run-col" aria-label={t.trailColumn}>
          <h5>{t.trailColumn}</h5>
          {trail === null ? (
            <>
              <p className="mm-run-status-body">{t.trailNotProjected}</p>
              <p className="muted">{t.trailNote}</p>
            </>
          ) : trail.length === 0 ? (
            <p className="muted">{t.trailEmpty}</p>
          ) : (
            <ol className="mm-run-trail">
              {trail.map((step, index) => (
                <li key={`${index}-${step.title}`}>
                  <span className="mm-run-trail-title">{step.title}</span>
                  {step.detail !== null ? (
                    <span className="mm-run-trail-detail">{step.detail}</span>
                  ) : null}
                  {step.timestamp !== null ? (
                    <span className="mm-run-trail-time">{step.timestamp}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </section>
        <section className="mm-run-col" aria-label={t.evidenceColumn}>
          <h5>{t.evidenceColumn}</h5>
          <div className="card mm-route-card">
            <h6>{t.sessionCard}</h6>
            <dl className="mm-route-facts">
              {sessionRows.map(([row, value]) =>
                record === null ? (
                  <div key={row}>
                    <dt>{row}</dt>
                    <dd data-readiness="unknown">
                      {t.unknownValue}
                      <small>{t.sessionNote}</small>
                    </dd>
                  </div>
                ) : (
                  <div key={row}>
                    <dt>{row}</dt>
                    <dd data-projected={value !== null ? "true" : "false"}>
                      {value ?? t.notObserved}
                    </dd>
                  </div>
                ),
              )}
            </dl>
          </div>
          <div className="card mm-route-card">
            <h6>{t.artifactsCard}</h6>
            {record === null ? (
              <>
                <dl className="mm-route-facts">
                  {(
                    [
                      [t.artifactRefs],
                      [t.checksSummary],
                      [t.branch],
                      [t.pullRequest],
                      [t.resultRow],
                    ] as const
                  ).map(([row]) => (
                    <div key={row}>
                      <dt>{row}</dt>
                      <dd data-projected="false">{t.notProjected}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mm-route-card-note">{t.artifactsNote}</p>
              </>
            ) : (
              <>
                <dl className="mm-route-facts">
                  <div>
                    <dt>{t.artifactRefs}</dt>
                    <dd>{t.artifactCount(record.result.artifact_refs.length)}</dd>
                  </div>
                  <div>
                    <dt>{t.checksSummary}</dt>
                    <dd>
                      {record.github.checks === null
                        ? checksStateLabel(record.github.checks_state, t)
                        : t.checksSummaryLine(
                            checksStateLabel(record.github.checks_state, t),
                            record.github.checks.length,
                          )}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.branch}</dt>
                    <dd>{record.github.branch ?? t.notObserved}</dd>
                  </div>
                  <div>
                    <dt>{t.pullRequest}</dt>
                    <dd>
                      {record.github.pr_url ? (
                        <a
                          href={record.github.pr_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {record.github.pr_url}
                        </a>
                      ) : record.github.pr_number !== null ? (
                        `#${record.github.pr_number}`
                      ) : (
                        t.notObserved
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.resultRow}</dt>
                    <dd>{record.result.text ?? t.resultEmpty}</dd>
                  </div>
                </dl>
                {record.result.artifact_refs.length > 0 ? (
                  <ul className="mm-run-artifacts">
                    {record.result.artifact_refs.map((ref) => (
                      <li key={ref}>
                        <code>{ref}</code>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
          </div>
        </section>
      </div>
    </article>
  );
}
