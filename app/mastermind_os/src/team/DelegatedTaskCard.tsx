import type { DelegatedTask } from "./delegated-task";

const STRINGS = {
  en: {
    stateQueued: "Queued",
    stateRunning: "In progress",
    stateUnknown: "Outcome unknown",
    stateDeclined: "Declined",
    stateTerminal: "Finished",
    stateUnknownBody:
      "The request was sent, but its result has not returned. Check the original request before sending more work.",
    stateQueuedBody:
      "The handoff is admitted and waiting for its runtime slot.",
    noReason: "No reason supplied by the source.",
    dispatch: "Dispatch coding task",
    dispatchPreviewReason:
      "Dispatch needs an admitted coding handoff on the Executive path. This surface can only preview.",
    dispatchDeclinedReason:
      "This handoff was declined. Start a new handoff; do not replay the refused one.",
    dispatchRunningReason:
      "This task is already running on its original carrier.",
    openCode: "Open coding session →",
    lastActivity: (value: string) => `Last activity ${value}`,
    chipsLabel: "Route",
    previewChip: "PREVIEW",
    effectNoneChip: "EFFECT·NONE",
    resultHeading: "Result delivered",
    deliveredTo: (value: string) => `Delivered to ${value}`,
    deliveredNotAccepted:
      "Delivered is not acceptance. The owner still reviews the result.",
  },
  "zh-CN": {
    stateQueued: "排队中",
    stateRunning: "进行中",
    stateUnknown: "结果未知",
    stateDeclined: "已拒绝",
    stateTerminal: "已完成",
    stateUnknownBody:
      "请求已发送，但结果尚未返回。发送更多工作之前，请先核对原始请求。",
    stateQueuedBody: "该交接已获受理，正在等待运行席位。",
    noReason: "来源未提供原因。",
    dispatch: "派发编码任务",
    dispatchPreviewReason:
      "派发需要经由 Executive 路径受理的编码交接。此界面仅可预览。",
    dispatchDeclinedReason:
      "该交接已被拒绝。请发起新的交接，不要重放被拒绝的请求。",
    dispatchRunningReason: "该任务已在原始载体上运行。",
    openCode: "打开编码会话 →",
    lastActivity: (value: string) => `最近活动 ${value}`,
    chipsLabel: "路径",
    previewChip: "预览",
    effectNoneChip: "无效果",
    resultHeading: "结果已交付",
    deliveredTo: (value: string) => `已交付给 ${value}`,
    deliveredNotAccepted: "交付不等于接受。负责人仍需审阅该结果。",
  },
};

function stateLabel(
  state: DelegatedTask["state"],
  t: typeof STRINGS.en,
): string {
  if (state === "queued") return t.stateQueued;
  if (state === "running") return t.stateRunning;
  if (state === "unknown") return t.stateUnknown;
  if (state === "declined") return t.stateDeclined;
  return t.stateTerminal;
}

export function DelegatedTaskCard({
  task,
  locale = "en",
  onOpenCode,
}: {
  task: DelegatedTask;
  locale?: "en" | "zh-CN";
  onOpenCode?: () => void;
}) {
  const t = STRINGS[locale];
  const preview = task.authority === "preview";
  const dispatchDisabledReason =
    task.state === "declined"
      ? t.dispatchDeclinedReason
      : task.state === "running"
        ? t.dispatchRunningReason
        : preview
          ? t.dispatchPreviewReason
          : null;
  return (
    <article
      className="mm-delegated-task"
      data-state={task.state}
      data-authority={task.authority}
    >
      <header className="mm-task-head">
        <h3 className="mm-task-title">{task.title}</h3>
        <span className="mm-chip mm-chip-state" data-state={task.state}>
          {stateLabel(task.state, t)}
        </span>
        {preview ? (
          <>
            <span className="mm-chip mm-chip-preview">{t.previewChip}</span>
            <span className="mm-chip mm-chip-effect-none">
              {t.effectNoneChip}
            </span>
          </>
        ) : null}
      </header>
      {task.summary ? <p className="mm-task-summary">{task.summary}</p> : null}
      {task.route.length > 0 ? (
        <p className="mm-task-route" aria-label={t.chipsLabel}>
          {task.route.map((chip) => (
            <span key={chip} className="mm-chip mm-chip-route">
              {chip}
            </span>
          ))}
        </p>
      ) : null}
      {task.owner ? <p className="mm-task-owner">{task.owner}</p> : null}
      {task.lastActivity ? (
        <p className="mm-task-activity">{t.lastActivity(task.lastActivity)}</p>
      ) : null}
      {task.state === "unknown" ? (
        <p className="mm-task-reason">{t.stateUnknownBody}</p>
      ) : null}
      {task.state === "queued" ? (
        <p className="mm-task-reason">{t.stateQueuedBody}</p>
      ) : null}
      {task.stateReason !== null &&
      task.state !== "unknown" &&
      task.state !== "queued" ? (
        <p className="mm-task-reason">
          {task.stateReason.length > 0 ? task.stateReason : t.noReason}
        </p>
      ) : null}
      {task.result ? (
        <div className="mm-task-result">
          <h4>{t.resultHeading}</h4>
          <p className="mm-task-result-title">{task.result.title}</p>
          <p>{t.deliveredTo(task.result.deliveredTo)}</p>
          <p className="mm-task-not-accepted">{t.deliveredNotAccepted}</p>
        </div>
      ) : null}
      <div className="mm-task-actions">
        {dispatchDisabledReason !== null ? (
          <button
            type="button"
            className="mm-task-dispatch"
            disabled
            aria-describedby="mm-task-dispatch-reason"
          >
            {t.dispatch}
          </button>
        ) : (
          <button
            type="button"
            className="mm-task-dispatch mm-task-dispatch-live"
          >
            {t.dispatch}
          </button>
        )}
        {onOpenCode ? (
          <button
            type="button"
            className="mm-task-open-code"
            onClick={onOpenCode}
          >
            {t.openCode}
          </button>
        ) : null}
      </div>
      {dispatchDisabledReason !== null ? (
        <p className="mm-task-dispatch-reason" id="mm-task-dispatch-reason">
          {dispatchDisabledReason}
        </p>
      ) : null}
    </article>
  );
}
