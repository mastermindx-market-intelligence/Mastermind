import { useId, useRef, useState } from "react";
import { useComposerKeyboard } from "./useComposerKeyboard";
import {
  SESSION_TEXT_MAX_CODEPOINTS as MAX_CONDITION_CODEPOINTS,
  codePointLength,
} from "../session-text-contract";
export {
  SESSION_TEXT_MAX_CODEPOINTS as MAX_CONDITION_CODEPOINTS,
  codePointLength,
} from "../session-text-contract";
import "./session-continuation.css";
import type {
  OperationPointer,
  OperationState,
} from "../operation-controller";

/**
 * Selected-session continuation panel.
 *
 * Presentation only: it shows the host-projected fabric_attempt target and
 * the closed receipt outcome of the dedicated session controller, and it
 * captures the explicit user-entered instruction and completion/stop
 * condition once per submit through the accepted synchronous provider. It
 * never renders transcript, reply text, worker execution, attention delivery
 * or parent consumption — an effect receipt is not proof of any of those —
 * and it offers no Stop control: stop_condition is content, not cancel.
 * Recovery is status-only and always uses the original operation key.
 */

export type SessionContinuationOutcome =
  | { status: "accepted" }
  | { status: "refused" };

type SessionLocale = "en" | "zh-CN";
const STATIC_ZH: Record<string, string> = {
  "Session continuation": "会话继续",
  "Retained continuation": "保留的继续请求",
  "Original message reference": "原消息引用",
  "Its outcome is unresolved here; status recovery reads that exact original key only and never sends again.": "此处尚未确认结果；状态查询仅使用原操作键，不会再次发送。",
  "Check status": "查看状态",
  "Checking…": "正在查询…",
  "Checking for a retained continuation…": "正在查找保留的继续请求…",
  "Session continuation is unavailable for the exact selected mission.": "此项目暂时无法发送。",
  "Technical details": "技术详情",
  "Refresh session capability": "重新核验会话能力",
  "Continuation target": "继续请求目标",
  "Send capability": "发送能力",
  "Exactly one verified target": "仅一个已核验目标",
  "No verified target; nothing is guessed": "没有已核验目标；不会猜测",
  "Stop control": "停止控制",
  "Not offered — the completion condition is content, not cancel.": "不提供停止控制；完成条件是请求内容，不是取消命令。",
  "Message committed.": "消息已提交。",
  "Further activity has not been established by this receipt.": "此回执尚未证明后续活动。",
  "This invocation was refused before any effect:": "本次请求在产生效果前被拒绝：",
  "What would you like done?": "你希望完成什么？",
  "How will we know it is done?": "达到什么条件才算完成？",
  "Describe the change and its completion condition.": "请说明要做的事及完成条件。",
  "Use 1–700 characters.": "请输入 1–700 个字符。",
  "Sending…": "正在发送…",
  "Send": "发送",
  "The completion condition is captured once; it is not evaluated here and authorizes no stop.": "完成条件仅捕获一次；此处不判断是否达成，也不授权停止。",
  "Continue this project’s verified session.": "继续此项目已验证的会话。",
  "Outcome not yet established.": "结果尚未确认。"
};
function ui(locale: SessionLocale, text: string) { return locale === "zh-CN" ? STATIC_ZH[text] ?? text : text; }

export interface SelectedSessionContinuationProps {
  locale?: SessionLocale;
  /** Host-projected target ref when send is exactly capable; otherwise null. */
  sessionKey: string | null;
  unavailableReason?: string;
  /** Last closed controller state; null before any dispatch this epoch. */
  status: OperationState | null;
  /** Durable retained pointer for this scope, when discovery/hold found one. */
  retainedPointer: OperationPointer | null;
  reading: boolean;
  recoveryRequired?: boolean;
  recovering: boolean;
  /** Owner-side dispatch in flight; never releases the local guard. */
  sending: boolean;
  refusalReason?: string;
  onContinue: (
    instruction: string,
    stopCondition: string,
    onComplete: (outcome: SessionContinuationOutcome) => void,
  ) => void;
  onRecover: () => void;
  /** Explicit context qualification; separate from original-key recovery. */
  onRequalify?: () => void;
}

function isTerminal(outcome: unknown): outcome is SessionContinuationOutcome {
  try {
    if (typeof outcome !== "object" || outcome === null || Array.isArray(outcome)) return false;
    const status = Reflect.get(outcome, "status");
    return status === "accepted" || status === "refused";
  } catch {
    return false;
  }
}

export function SelectedSessionContinuation({
  locale = "en",
  sessionKey,
  unavailableReason,
  status,
  retainedPointer,
  reading,
  recoveryRequired = false,
  recovering,
  sending,
  refusalReason,
  onContinue,
  onRecover,
  onRequalify,
}: SelectedSessionContinuationProps) {
  const formId = useId();
  const instructionId = `${formId}-instruction`;
  const conditionId = `${formId}-condition`;
  const [instruction, setInstruction] = useState("");
  const [condition, setCondition] = useState("");
  const instructionRef = useRef("");
  const conditionRef = useRef("");
  const sentInstructionRef = useRef("");
  const sentConditionRef = useRef("");
  const tokenRef = useRef<number | null>(null);
  const tokenSeq = useRef(0);
  const [inFlight, setInFlight] = useState(false);

  const setField = (which: "instruction" | "condition", value: string) => {
    if (which === "instruction") {
      instructionRef.current = value;
      setInstruction(value);
    } else {
      conditionRef.current = value;
      setCondition(value);
    }
  };

  const complete = (token: number, outcome: unknown) => {
    if (!isTerminal(outcome)) return;
    if (tokenRef.current !== token) return;
    tokenRef.current = null;
    setInFlight(false);
    if (outcome.status === "accepted" &&
        instructionRef.current === sentInstructionRef.current &&
        conditionRef.current === sentConditionRef.current) {
      // Success clears only the exact submitted pair; anything retyped is kept.
      instructionRef.current = "";
      conditionRef.current = "";
      setInstruction("");
      setCondition("");
    }
  };

  const dispatchBusy = sending || inFlight || recovering;
  const instructionPoints = codePointLength(instruction);
  const conditionPoints = codePointLength(condition);
  const instructionValid = instructionPoints >= 1 && instructionPoints <= MAX_CONDITION_CODEPOINTS && instruction.trim().length > 0;
  const conditionValid =
    conditionPoints >= 1 &&
    conditionPoints <= MAX_CONDITION_CODEPOINTS &&
    condition.trim().length > 0;
  const canContinue =
    sessionKey !== null && !unavailableReason && !dispatchBusy && !reading && !retainedPointer && !recoveryRequired && instructionValid && conditionValid;

  const composerKeyDown = useComposerKeyboard(canContinue);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canContinue || tokenRef.current !== null) return;
    const token = ++tokenSeq.current;
    tokenRef.current = token;
    sentInstructionRef.current = instruction;
    sentConditionRef.current = condition;
    setInFlight(true);
    try {
      onContinue(instruction, condition, (outcome) => {
        try {
          complete(token, outcome);
        } catch {
          /* not terminal: stays in flight */
        }
      });
    } catch {
      /* a thrown host callback is not an outcome; the dispatch stays in flight */
    }
  };

  const retained = retainedPointer !== null;
  const outcomeState = status?.status ?? null;
  return (
    <section className="card session-continuation" aria-label={ui(locale, "Session continuation")}>
      <div className="section-title">
        <div>
          <h2>{ui(locale, "Session continuation")}</h2>
          <p className="muted">
            {ui(locale, "Continue this project’s verified session.")}
          </p>
        </div>

      </div>
          {retained || recoveryRequired ? (
            <div className="unjoined" role="note">
              <b>{ui(locale, "Retained continuation")}</b>
              <p>
                {ui(locale, "Original message reference")}: <code>{retainedPointer?.operationKey ?? "POINTER_READ_UNAVAILABLE"}</code>. {ui(locale, "Its outcome is unresolved here; status recovery reads that exact original key only and never sends again.")}
              </p>
              <div className="form-actions">
                <button className="primary" type="button" onClick={onRecover} disabled={recovering || reading}>
                  {recovering ? ui(locale, "Checking\u2026") : ui(locale, "Check status")}
                </button>
              </div>
            </div>
          ) : reading ? (
            <p className="muted">{ui(locale, "Checking for a retained continuation…")}</p>
          ) : null}
      {unavailableReason ? (
        <>
          <p className="muted">
            {ui(locale, "Session continuation is unavailable for the exact selected mission.")}
          </p>
          <details className="reason-details">
            <summary>{ui(locale, "Technical details")}</summary>
            <code>{unavailableReason}</code>
          </details>
          {onRequalify ? (
            <button type="button" onClick={onRequalify}>
              Refresh session capability
            </button>
          ) : null}
        </>
      ) : (
        <>
          <details className="session-technical"><summary>{ui(locale, "Technical details")}</summary>        <span
          className={`state state-${sessionKey && !unavailableReason ? "available" : "unavailable"}`}
        >
          {sessionKey && !unavailableReason ? "AVAILABLE" : "UNAVAILABLE"}
        </span><dl>
            <dt>{ui(locale, "Continuation target")}</dt>
            <dd>{sessionKey ? <code>{sessionKey}</code> : <code>SESSION_UNAVAILABLE</code>}</dd>
            <dt>{ui(locale, "Send capability")}</dt>
            <dd>{sessionKey ? ui(locale, "Exactly one verified target") : ui(locale, "No verified target; nothing is guessed")}</dd>
            <dt>{ui(locale, "Stop control")}</dt>
            <dd>{ui(locale, "Not offered — the completion condition is content, not cancel.")}</dd>
          </dl></details>
          {outcomeState === "accepted" && !retained ? (
            <div className="session-receipt" role="status">
              <p>{ui(locale, "Message committed.")}</p>
              <p className="muted">{ui(locale, "Further activity has not been established by this receipt.")}</p>
            </div>
          ) : null}
          {outcomeState === "refused" && !retained ? (
            <p className="muted">
              {ui(locale, "This invocation was refused before any effect:")}{" "}
              <code>{status?.reason}</code>
            </p>
          ) : null}
          {refusalReason ? (
            <div className="form-error" role="alert">
              {refusalReason}
            </div>
          ) : null}
          <form onSubmit={submit} noValidate className="session-send-form">
            <div className="form-field">
              <label htmlFor={instructionId}>
                <span>{ui(locale, "What would you like done?")}</span>
                {instructionPoints > MAX_CONDITION_CODEPOINTS && (
                  <span className="field-error">
                    {" "}
                    ({instructionPoints}/{MAX_CONDITION_CODEPOINTS})
                  </span>
                )}
              </label>
              <textarea
                id={instructionId}
                value={instruction}
                onChange={(e) => setField("instruction", e.target.value)}
                onKeyDown={(event) => composerKeyDown(event)}
                rows={3}
                disabled={dispatchBusy}
                aria-invalid={instructionPoints > MAX_CONDITION_CODEPOINTS}
                aria-describedby={`${formId}-bounds`}
              />
            </div>
            <div className="form-field">
              <label htmlFor={conditionId}>
                <span>{ui(locale, "How will we know it is done?")}</span>
                {(conditionPoints > MAX_CONDITION_CODEPOINTS || (conditionPoints > 0 && !conditionValid)) && (
                  <span className="field-error">
                    {" "}
                    ({conditionPoints}/{MAX_CONDITION_CODEPOINTS})
                  </span>
                )}
              </label>
              <textarea
                id={conditionId}
                value={condition}
                onChange={(e) => setField("condition", e.target.value)}
                onKeyDown={(event) => composerKeyDown(event)}
                rows={2}
                placeholder={ui(locale, "Describe the change and its completion condition.")}
                disabled={dispatchBusy}
                aria-invalid={conditionPoints > MAX_CONDITION_CODEPOINTS || (conditionPoints > 0 && !conditionValid)}
                aria-describedby={`${formId}-bounds`}
              />
              <p className="muted">
                {ui(locale, "The completion condition is captured once; it is not evaluated here and authorizes no stop.")}
              </p>
            </div>
            <p id={`${formId}-bounds`} className="session-bounds">{ui(locale, "Use 1–700 characters.")} ({instructionPoints}/700 · {conditionPoints}/700)</p>
            <p className="session-keyboard-hint">{locale === "zh-CN"
              ? "准备就绪后按 Ctrl / Cmd + Enter 发送；Enter 或 Shift + Enter 换行。"
              : "Ctrl / Cmd + Enter to send when ready. Enter and Shift + Enter insert new lines."}</p>
            <div className="form-actions">
              <button type="submit" disabled={!canContinue} className="primary">
                {dispatchBusy ? ui(locale, "Sending\u2026") : ui(locale, "Send")}
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
