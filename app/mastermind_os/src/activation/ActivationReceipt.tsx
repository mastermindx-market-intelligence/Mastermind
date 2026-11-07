import type { OperationState } from "../orchestration/operation-controller";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ActivationReceiptProps {
  /**
   * The controller's actual current state — owner-typed input, not untrusted
   * wire data. `null` means no controller state is attached right now; the
   * receipt shows unavailable and fabricates nothing.
   */
  state: OperationState | null;
  locale?: "en" | "zh-CN";
  /**
   * Explicit owner action for resolving the retained original operation.
   * Rendered only while the current state is `unknown`; nothing on this
   * component ever reads, replays, resubmits, cancels, or recovers by itself,
   * on mount or otherwise.
   */
  onReadOriginalStatus?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const WORDS = {
  en: {
    title: "Request status",
    unavailable: "Request status unavailable",
    idle: "No current request receipt",
    submitting: "Awaiting the original request result.",
    checking: "Checking the original result.",
    unknown: "Request outcome unknown",
    hold: "This request is unresolved. Do not send it again, choose another destination, or create a replacement.",
    readOriginal: "Read original status",
    accepted: "Request accepted",
    acceptedCaption:
      "This receipt does not confirm that work started, a result returned, or the result was accepted.",
    refused: "Request declined",
    details: "Details",
    operation: "Operation",
    kind: "Kind",
    target: "Target",
    notReported: "Not reported",
    work: "Work",
    rootJob: "Root job",
  },
  "zh-CN": {
    title: "请求状态",
    unavailable: "请求状态不可用",
    idle: "当前没有请求回执",
    submitting: "正在等待原始请求结果。",
    checking: "正在检查原始结果。",
    unknown: "请求结果未知",
    hold: "此请求尚未确认结果。请勿再次发送、改换目标或创建替代请求。",
    readOriginal: "读取原始状态",
    accepted: "请求已接受",
    acceptedCaption:
      "此回执不能确认工作已开始、结果已返回或结果已被接受。",
    refused: "请求已拒绝",
    details: "详情",
    operation: "操作",
    kind: "类型",
    target: "目标",
    notReported: "未报告",
    work: "工作",
    rootJob: "根任务",
  },
} as const;

/**
 * Current-state command receipt. Exactly one receipt for the controller's
 * present state — no history, list, or event is fabricated. Accepted is not
 * labelled as a completed activation, and no operation ID is invented for a
 * terminal state whose pointer is already null.
 */
export function ActivationReceipt({
  state,
  locale = "en",
  onReadOriginalStatus,
}: ActivationReceiptProps) {
  const words = WORDS[locale === "zh-CN" ? "zh-CN" : "en"];

  if (state === null) {
    return (
      <section className="card">
        <div className="section-title">
          <h2>{words.title}</h2>
        </div>
        <p className="empty">{words.unavailable}</p>
      </section>
    );
  }

  const readOriginal = onReadOriginalStatus;

  const headline =
    state.status === "idle"
      ? words.idle
      : state.status === "submitting"
        ? words.submitting
        : state.status === "checking"
          ? words.checking
          : state.status === "unknown"
            ? words.unknown
            : state.status === "accepted"
              ? words.accepted
              : words.refused;

  return (
    <section
      className="card"
      aria-busy={state.status === "submitting" || state.status === "checking"}
    >
      <div className="section-title">
        <h2>{words.title}</h2>
      </div>
      <p role="status" aria-live="polite">
        {headline}
      </p>
      {state.status === "unknown" ? (
        <>
          <p className="muted">{words.hold}</p>
          <dl>
            <dt>{words.operation}</dt>
            <dd>
              <code>{state.pointer.operationKey}</code>
            </dd>
            <dt>{words.kind}</dt>
            <dd>
              <code>{state.pointer.kind}</code>
            </dd>
            <dt>{words.target}</dt>
            <dd>
              {state.pointer.targetKey === null ? (
                words.notReported
              ) : (
                <code>{state.pointer.targetKey}</code>
              )}
            </dd>
          </dl>
          {readOriginal ? (
            <button type="button" onClick={() => readOriginal()}>
              {words.readOriginal}
            </button>
          ) : null}
        </>
      ) : null}
      {state.status === "accepted" ? (
        <>
          {state.missionSelection ? (
            <dl>
              <dt>{words.work}</dt>
              <dd>
                <code>{state.missionSelection.workRef}</code>
              </dd>
              <dt>{words.rootJob}</dt>
              <dd>
                <code>{state.missionSelection.rootJobId}</code>
              </dd>
            </dl>
          ) : null}
          <p className="muted">{words.acceptedCaption}</p>
        </>
      ) : null}
      <details className="reason-details">
        <summary>{words.details}</summary>
        <p>
          <code>{state.reason}</code>
        </p>
      </details>
    </section>
  );
}
