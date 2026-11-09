import type {
  ExecutionReturnDeliveryReceipt,
  ExecutionReturnRecord,
  ExecutionReturnStage,
} from "../hermes-native/execution-return-contract";

/** HC08 — a settled attempt's execution return. Consumes ONLY Director F's
 *  authoritative contract (`mastermind.execution_return/v1` +
 *  `mastermind.execution_return_delivery/v1`, parsed fail-closed by
 *  `src/hermes-native/execution-return-contract.ts`). There is no UI-side
 *  return type anymore, and no "accepted" rendering exists anywhere: in v1
 *  acceptance is closed to exactly `not_accepted` and no producer of
 *  `accepted` exists, so this card structurally cannot show one. Delivery is
 *  an observation, never acceptance — the two are always rendered as
 *  separate states. Stages come from the parsed record, whose parser already
 *  refuses a stage that outruns its own evidence; unknown GitHub evidence is
 *  rendered as unknown, never green. */

type StageLabelKey = Record<ExecutionReturnStage, string>;

interface Strings {
  heading: string;
  emptyBody: string;
  emptyNote: string;
  stageLabel: string;
  stage: StageLabelKey;
  evidenceHeading: string;
  branch: string;
  pullRequest: string;
  checks: string;
  merge: string;
  installation: string;
  checksGreen: string;
  checksFailed: string;
  checksUnknown: string;
  merged: string;
  notMerged: string;
  mergeUnknown: string;
  installClaimed: string;
  installNone: string;
  notObserved: string;
  checksListLabel: string;
  acceptanceLabel: string;
  acceptanceNotAccepted: string;
  acceptanceNote: string;
  acceptanceClaimRefused: string;
  deliveryLabel: string;
  deliveryDelivered: string;
  deliveryUnknown: string;
  deliveryRefused: string;
  deliveryNotObserved: string;
  deliveryNoReceipt: string;
  deliveryMismatch: string;
  deliveredNotAccepted: string;
  transportRef: (value: string) => string;
  submissionId: (value: string) => string;
  refusalCode: (value: string) => string;
  resultHeading: string;
  resultEmpty: string;
  artifactsHeading: string;
  artifactsEmpty: string;
  identityHeading: string;
  returnId: string;
  rootId: string;
  attemptId: string;
  idempotencyKey: string;
  requester: string;
  conversation: string;
  project: string;
  openOrigin: string;
}

const STRINGS: Record<"en" | "zh-CN", Strings> = {
  en: {
    heading: "Execution return",
    emptyBody: "No execution return is projected yet.",
    emptyNote:
      "When a delegated attempt settles, its mastermind.execution_return/v1 record appears here — with delivery and acceptance kept separate.",
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
    evidenceHeading: "GitHub evidence",
    branch: "Branch",
    pullRequest: "Pull request",
    checks: "Checks",
    merge: "Merge",
    installation: "Installation",
    checksGreen: "Green",
    checksFailed: "Failed",
    checksUnknown: "Unknown",
    merged: "Merged",
    notMerged: "Not merged",
    mergeUnknown: "Unknown",
    installClaimed: "Claimed, unproven",
    installNone: "None claimed",
    notObserved: "Not observed",
    checksListLabel: "Individual checks",
    acceptanceLabel: "Acceptance",
    acceptanceNotAccepted: "Not accepted",
    acceptanceNote:
      "Delivery is not acceptance. In execution_return/v1 acceptance is closed to not_accepted — no accepted state exists yet.",
    acceptanceClaimRefused:
      "The incoming record claimed acceptance; the contract refused the claim.",
    deliveryLabel: "Delivery",
    deliveryDelivered: "Delivered",
    deliveryUnknown: "Delivery unknown",
    deliveryRefused: "Refused",
    deliveryNotObserved: "Not observed",
    deliveryNoReceipt: "No delivery receipt is projected for this return.",
    deliveryMismatch: "Receipt does not match this return",
    deliveredNotAccepted:
      "Delivered ≠ accepted — delivery is an observation; acceptance is a separate act.",
    transportRef: (value: string) => `Transport ref ${value}`,
    submissionId: (value: string) => `Submission ${value}`,
    refusalCode: (value: string) => `Refusal code ${value}`,
    resultHeading: "Result",
    resultEmpty: "No result text.",
    artifactsHeading: "Artifact refs",
    artifactsEmpty: "No artifact refs.",
    identityHeading: "Return identity",
    returnId: "Return ID",
    rootId: "Root",
    attemptId: "Attempt",
    idempotencyKey: "Idempotency key",
    requester: "Requester",
    conversation: "Conversation",
    project: "Project",
    openOrigin: "Open origin →",
  },
  "zh-CN": {
    heading: "执行返回",
    emptyBody: "尚无执行返回被投影。",
    emptyNote:
      "当受派的尝试落定后，其 mastermind.execution_return/v1 记录会显示在此——交付与接受始终分开显示。",
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
    evidenceHeading: "GitHub 证据",
    branch: "分支",
    pullRequest: "拉取请求",
    checks: "检查",
    merge: "合并",
    installation: "安装",
    checksGreen: "通过",
    checksFailed: "失败",
    checksUnknown: "未知",
    merged: "已合并",
    notMerged: "未合并",
    mergeUnknown: "未知",
    installClaimed: "已声明，未证实",
    installNone: "未声明",
    notObserved: "未观测",
    checksListLabel: "单项检查",
    acceptanceLabel: "接受",
    acceptanceNotAccepted: "未接受",
    acceptanceNote:
      "交付不等于接受。在 execution_return/v1 中，接受被封闭为 not_accepted——目前不存在“已接受”状态。",
    acceptanceClaimRefused: "传入记录声称已被接受；契约拒绝了该声明。",
    deliveryLabel: "交付",
    deliveryDelivered: "已交付",
    deliveryUnknown: "交付未知",
    deliveryRefused: "已拒绝",
    deliveryNotObserved: "未观测",
    deliveryNoReceipt: "该返回尚无已投影的交付回执。",
    deliveryMismatch: "回执与该返回不匹配",
    deliveredNotAccepted: "已交付 ≠ 已接受——交付是观测；接受是另一个行为。",
    transportRef: (value: string) => `传输引用 ${value}`,
    submissionId: (value: string) => `提交 ${value}`,
    refusalCode: (value: string) => `拒绝码 ${value}`,
    resultHeading: "结果",
    resultEmpty: "无结果文本。",
    artifactsHeading: "产物引用",
    artifactsEmpty: "无产物引用。",
    identityHeading: "返回标识",
    returnId: "返回 ID",
    rootId: "根",
    attemptId: "尝试",
    idempotencyKey: "幂等键",
    requester: "请求方",
    conversation: "会话",
    project: "项目",
    openOrigin: "打开来源 →",
  },
};

function checksLabel(
  state: ExecutionReturnRecord["github"]["checks_state"],
  t: Strings,
): string {
  if (state === "green") return t.checksGreen;
  if (state === "failed") return t.checksFailed;
  return t.checksUnknown;
}

function mergeLabel(
  state: ExecutionReturnRecord["github"]["merge_state"],
  t: Strings,
): string {
  if (state === "merged") return t.merged;
  if (state === "not_merged") return t.notMerged;
  return t.mergeUnknown;
}

export function ResultReturnCard({
  executionReturn,
  deliveryReceipt = null,
  locale = "en",
  onOpenOrigin,
}: {
  /** Director F's parsed mastermind.execution_return/v1 record; null = no
   *  return projected yet (the honest empty state — never fixture data). */
  executionReturn: ExecutionReturnRecord | null;
  /** Optional parsed delivery receipt for the same return. */
  deliveryReceipt?: ExecutionReturnDeliveryReceipt | null;
  locale?: "en" | "zh-CN";
  onOpenOrigin?: () => void;
}) {
  const t = STRINGS[locale];

  if (executionReturn === null) {
    return (
      <article
        className="mm-result-return mm-result-return-empty"
        aria-labelledby="mm-result-return-heading"
      >
        <h3 id="mm-result-return-heading">{t.heading}</h3>
        <p className="mm-result-empty-body">{t.emptyBody}</p>
        <p className="muted">{t.emptyNote}</p>
        {onOpenOrigin ? (
          <button
            type="button"
            className="mm-result-open-origin"
            onClick={onOpenOrigin}
          >
            {t.openOrigin}
          </button>
        ) : null}
      </article>
    );
  }

  const record = executionReturn;
  const receiptMatches =
    deliveryReceipt !== null &&
    deliveryReceipt.return_id === record.return_id;
  const receiptMismatch =
    deliveryReceipt !== null && !receiptMatches;

  const deliveryLabel = !deliveryReceipt
    ? t.deliveryNotObserved
    : receiptMismatch
      ? t.deliveryMismatch
      : deliveryReceipt.state === "delivered"
        ? t.deliveryDelivered
        : deliveryReceipt.state === "unknown"
          ? t.deliveryUnknown
          : t.deliveryRefused;
  const deliveryData = !deliveryReceipt
    ? "none"
    : receiptMismatch
      ? "mismatch"
      : deliveryReceipt.state;

  return (
    <article
      className="mm-result-return"
      aria-labelledby="mm-result-return-heading"
    >
      <h3 id="mm-result-return-heading">{t.heading}</h3>
      <p className="mm-result-status-line">
        <span className="mm-chip mm-chip-state" data-stage={record.stage}>
          {t.stageLabel}: {t.stage[record.stage]}
        </span>
      </p>
      <dl className="mm-result-status">
        <div>
          <dt>{t.acceptanceLabel}</dt>
          <dd>
            {/* v1 closes acceptance to exactly not_accepted; there is no
                accepted producer, so no accepted branch exists here. */}
            <span data-acceptance={record.acceptance}>
              {t.acceptanceNotAccepted}
            </span>
            <small>{t.acceptanceNote}</small>
            {record.acceptance_claim_refused ? (
              <small>{t.acceptanceClaimRefused}</small>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>{t.deliveryLabel}</dt>
          <dd>
            <span data-delivery={deliveryData}>{deliveryLabel}</span>
            {receiptMatches && deliveryReceipt.state === "delivered" ? (
              <small>{t.transportRef(deliveryReceipt.transport_ref ?? "")}</small>
            ) : null}
            {receiptMatches && deliveryReceipt.state === "refused" ? (
              <small>{t.refusalCode(deliveryReceipt.refusal_code ?? "")}</small>
            ) : null}
            {receiptMatches ? (
              <small>{t.submissionId(deliveryReceipt.submission_id)}</small>
            ) : null}
            {!deliveryReceipt ? <small>{t.deliveryNoReceipt}</small> : null}
            <small>{t.deliveredNotAccepted}</small>
          </dd>
        </div>
      </dl>
      <div className="mm-result-evidence">
        <h4>{t.evidenceHeading}</h4>
        <dl>
          <div>
            <dt>{t.branch}</dt>
            <dd>{record.github.branch ?? t.notObserved}</dd>
          </div>
          <div>
            <dt>{t.pullRequest}</dt>
            <dd>
              {record.github.pr_url ? (
                <a href={record.github.pr_url} target="_blank" rel="noreferrer">
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
            <dt>{t.checks}</dt>
            {/* Unknown evidence renders as unknown — never green. */}
            <dd data-checks={record.github.checks_state}>
              {checksLabel(record.github.checks_state, t)}
            </dd>
          </div>
          <div>
            <dt>{t.merge}</dt>
            <dd data-merge={record.github.merge_state}>
              {mergeLabel(record.github.merge_state, t)}
            </dd>
          </div>
          <div>
            <dt>{t.installation}</dt>
            <dd>
              {record.github.installation === "claimed_unproven"
                ? t.installClaimed
                : t.installNone}
            </dd>
          </div>
        </dl>
        {record.github.checks !== null && record.github.checks.length > 0 ? (
          <p className="mm-result-checks" aria-label={t.checksListLabel}>
            {record.github.checks.map((check) => (
              <span key={check.name} className="mm-chip" data-conclusion={check.conclusion}>
                {check.name}: {check.conclusion}
              </span>
            ))}
          </p>
        ) : null}
      </div>
      <div className="mm-result-outcome">
        <h4>{t.resultHeading}</h4>
        <p className="mm-result-text">{record.result.text ?? t.resultEmpty}</p>
        <h4>{t.artifactsHeading}</h4>
        {record.result.artifact_refs.length === 0 ? (
          <p className="muted">{t.artifactsEmpty}</p>
        ) : (
          <ul className="mm-result-artifacts">
            {record.result.artifact_refs.map((ref) => (
              <li key={ref}>
                <code>{ref}</code>
              </li>
            ))}
          </ul>
        )}
      </div>
      <details className="mm-result-identity">
        <summary>{t.identityHeading}</summary>
        <dl>
          <div>
            <dt>{t.returnId}</dt>
            <dd>
              <code>{record.return_id}</code>
            </dd>
          </div>
          <div>
            <dt>{t.rootId}</dt>
            <dd>
              <code>{record.attempt.root_id}</code>
            </dd>
          </div>
          <div>
            <dt>{t.attemptId}</dt>
            <dd>
              <code>{record.attempt.attempt_id}</code>
            </dd>
          </div>
          <div>
            <dt>{t.idempotencyKey}</dt>
            <dd>
              <code>{record.attempt.idempotency_key}</code>
            </dd>
          </div>
          <div>
            <dt>{t.requester}</dt>
            <dd>
              <code>{record.original_requester.teammate_id}</code>
            </dd>
          </div>
          <div>
            <dt>{t.conversation}</dt>
            <dd>
              <code>{record.original_requester.conversation_id}</code>
            </dd>
          </div>
          <div>
            <dt>{t.project}</dt>
            <dd>
              <code>{record.original_requester.project_id}</code>
            </dd>
          </div>
        </dl>
      </details>
      {onOpenOrigin ? (
        <button
          type="button"
          className="mm-result-open-origin"
          onClick={onOpenOrigin}
        >
          {t.openOrigin}
        </button>
      ) : null}
    </article>
  );
}
