import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  decodeDirectNativeResult,
  type DirectResult,
  type DirectSelection,
  type DirectTerminalSelection,
} from "../../direct-native-result";
export interface DirectNativeResultPanelProps {
  selection: DirectSelection;
  locale?: "en" | "zh-CN";
  read?: (selection: DirectSelection, signal: AbortSignal) => Promise<unknown>;
  held: boolean;
  recovery?: ReactNode;
  onConsume: (
    selection: DirectTerminalSelection,
    digest: string,
    complete: (outcome: { status: "accepted" | "refused" }) => void,
  ) => void;
}
/** Selected direct result only. A read is never an acknowledgment or product acceptance. */
export function DirectNativeResultPanel({
  selection,
  locale = "en",
  read,
  held,
  recovery,
  onConsume,
}: DirectNativeResultPanelProps) {
  const [state, setState] = useState<DirectResult | null>(null),
    [reading, setReading] = useState(false),
    [failed, setFailed] = useState(false),
    [consuming, setConsuming] = useState(false);
  const request = useRef<AbortController | null>(null),
    seq = useRef(0),
    latch = useRef(false),
    mounted = useRef(true);
  const statusFocus = useRef<HTMLParagraphElement>(null),
    actionFocus = useRef(false);
  useEffect(() => {
    mounted.current = true;
    seq.current++;
    request.current?.abort();
    latch.current = false;
    actionFocus.current = false;
    setState(null);
    setFailed(false);
    setReading(false);
    setConsuming(false);
    return () => {
      mounted.current = false;
      seq.current++;
      request.current?.abort();
    };
  }, [selection.work_ref, selection.job_id, selection.attempt_id]);
  useEffect(() => {
    if (!actionFocus.current) return;
    statusFocus.current?.focus();
    if (!reading && !consuming && !held) actionFocus.current = false;
  }, [reading, consuming, held, failed, state]);
  const words =
    locale === "zh-CN"
      ? {
          title: "原生任务结果",
          read: "读取当前结果",
          reading: "正在读取…",
          unknown: "结果尚未得到验证。读取当前任务不会确认接收结果。",
          unavailable: "结果当前不可用。未推断任务为空或结果已被接收。",
          consume: "确认接收此结果",
          consuming: "正在确认接收…",
          consumed: "原发起方已确认接收此确切结果。",
          unconsumed: "结果已保留，尚未记录接收确认。",
          pending: "接收结果尚不确定。仅检查原操作状态；不要重新提交。",
          state: "当前状态",
          steps: "已完成事项",
          next: "后续事项",
          noneSteps: "未报告已完成事项。",
          noneNext: "未报告后续事项。",
          details: "结果身份与限制",
          limit: "这是明确的接收确认，不是独立审核或产品验收。",
        }
      : {
          title: "Native task result",
          read: "Read current result",
          reading: "Reading…",
          unknown:
            "The result is not verified yet. Reading this Job does not acknowledge it.",
          unavailable:
            "The result is unavailable. No empty result or acknowledgment is inferred.",
          consume: "Acknowledge this result",
          consuming: "Acknowledging…",
          consumed:
            "The original commissioning parent acknowledged this exact result.",
          unconsumed:
            "The result is retained; acknowledgment has not been recorded.",
          pending:
            "Acknowledgment is unresolved. Check the original operation only; do not submit again.",
          state: "Current state",
          steps: "Completed steps",
          next: "Next actions",
          noneSteps: "No completed steps were reported.",
          noneNext: "No next actions were reported.",
          details: "Result identity and limits",
          limit:
            "This is explicit receipt acknowledgment, not independent review or product acceptance.",
        };
  const load = async () => {
    if (!read || reading) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const ticket = ++seq.current;
    actionFocus.current = true;
    setReading(true);
    setFailed(false);
    setState(null);
    try {
      const raw = await read(selection, controller.signal);
      if (
        !mounted.current ||
        controller.signal.aborted ||
        ticket !== seq.current
      )
        return;
      const decoded = decodeDirectNativeResult(raw, selection);
      setState(decoded);
      setFailed(!decoded);
    } catch {
      if (
        mounted.current &&
        !controller.signal.aborted &&
        ticket === seq.current
      )
        setFailed(true);
    } finally {
      if (mounted.current && ticket === seq.current) setReading(false);
    }
  };
  const consume = () => {
    if (
      latch.current ||
      held ||
      !state?.result ||
      state.selection.attempt_id === null ||
      state.consumption?.state !== "UNCONSUMED"
    )
      return;
    latch.current = true;
    actionFocus.current = true;
    setConsuming(true);
    const ticket = seq.current;
    onConsume(
      { ...state.selection, attempt_id: state.selection.attempt_id },
      state.result.result_digest,
      () => {
        if (!mounted.current || ticket !== seq.current) return;
        latch.current = false;
        setConsuming(false);
        void load();
      },
    );
  };
  return (
    <section className="card" aria-busy={reading || consuming}>
      <div className="section-title">
        <h2>{words.title}</h2>
      </div>
      <p className="muted">{words.limit}</p>
      <button
        type="button"
        disabled={!read || reading || consuming}
        onClick={() => void load()}
      >
        {reading ? words.reading : words.read}
      </button>
      <p ref={statusFocus} tabIndex={-1} role="status" aria-live="polite">
        {reading
          ? words.reading
          : held || consuming
            ? words.pending
            : failed || state?.availability === "UNAVAILABLE" || !read
              ? words.unavailable
              : state?.consumption?.state === "CONSUMED"
                ? words.consumed
                : state?.availability === "AVAILABLE"
                  ? words.unconsumed
                  : words.unknown}
      </p>
      <div>
        {(held || consuming) &&
        (failed || state?.availability === "UNAVAILABLE") ? (
          <p>{words.unavailable}</p>
        ) : null}
        {state?.availability === "AVAILABLE" && state.result ? (
          <>
            <p className="visible-text">{state.result.summary}</p>
            <h3>{words.state}</h3>
            <p className="visible-text">{state.result.current_state}</p>
            <h3>{words.steps}</h3>
            {state.result.completed_steps.length ? (
              <ul>
                {state.result.completed_steps.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            ) : (
              <p>{words.noneSteps}</p>
            )}
            <h3>{words.next}</h3>
            {state.result.next_actions.length ? (
              <ul>
                {state.result.next_actions.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            ) : (
              <p>{words.noneNext}</p>
            )}
            {state.consumption?.state === "UNCONSUMED" ? (
              <button
                type="button"
                disabled={held || consuming || reading}
                onClick={consume}
              >
                {consuming ? words.consuming : words.consume}
              </button>
            ) : null}
          </>
        ) : null}
      </div>
      {recovery}
      <details className="reason-details">
        <summary>{words.details}</summary>
        <dl>
          <dt>Job</dt>
          <dd>
            <code>{selection.job_id}</code>
          </dd>
          <dt>Attempt</dt>
          <dd>
            <code>{state?.selection.attempt_id ?? "NOT_OBSERVED"}</code>
          </dd>
          <dt>Result digest</dt>
          <dd>
            <code>{state?.result?.result_digest ?? "NOT_OBSERVED"}</code>
          </dd>
        </dl>
        {state?.reason_codes.length ? (
          <ul>
            {state.reason_codes.map((x) => (
              <li key={x}>
                <code>{x}</code>
              </li>
            ))}
          </ul>
        ) : null}
      </details>
    </section>
  );
}
