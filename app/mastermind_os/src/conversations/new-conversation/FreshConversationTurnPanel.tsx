import { useId, type ReactNode } from "react";
import type { OperationState } from "../../orchestration/operation-controller";
import type { FreshConversationTurnData, FreshConversationTurnConsumption } from "./fresh-conversation-turn";
import { FreshConversationInitialResponse } from "./NewConversationOutcome";
import type {FreshAttendedData} from "./fresh-conversation-attended-contract";
import "./fresh-conversation-turn-panel.css";

export interface FreshConversationTurnPanelProps {
  locale: "en" | "zh-CN";
  /** Parent-decoded follow-up window; null until a confirmed read exists. */
  data: FreshAttendedData | null;
  /** Actual current reader's receipt; no synthetic turn DATA is constructed. */
  initialConsumption?: FreshConversationTurnConsumption | null;
  /** A submitted turn remains held until its exact original read settles. */
  responsePending?: boolean;
  /** Only the caller's verified original read releases the next draft. */
  allowNextMessage?:boolean;
  /** Only an owner-confirmed absence before any submission can offer initial Keep. */
  allowInitialKeep?:boolean;
  /** Previously verified local reads, retained for this open conversation. */
  recordedTurns?:readonly {data:FreshAttendedData;message:string|null}[];
  /** Complete older entries were omitted from the bounded local presentation. */
  historyLimited?:boolean;
  /** Live controller observation; null when the controller holds no state here. */
  operationState: OperationState | null;
  /** Actual caller-side await activity; never a provider state. */
  activity: "keeping" | "sending" | "checking" | null;
  /** Controlled draft text; the parent owns every transition. */
  message: string;
  /** Exact owner-prepared review replaces the editable field; no duplicate draft. */
  messagePreview?:ReactNode;
  /** Exact owner-captured sent text or actual recorded-window message, never the current draft. */
  originalTurnMessage?:string|null;
  onMessageChange: (value: string) => void;
  /** Parent hold on the draft input; this view never grants itself permission. */
  readOnly: boolean;
  /** Native before-edit lookup hold: readonly but still focusable. */
  messageReadOnly?:boolean;
  onMessageFocus?:()=>void;
  /** Real guarded action nodes from the owner; this view never synthesizes one. */
  keepControl?: ReactNode;
  sendControl?: ReactNode;
  checkControl?: ReactNode;
  feedback?: ReactNode;
}

type TurnKey = "keeping" | "sending" | "checking" | "unresolved" | "recorded" | "absent" | "refused";

/** Priority-ordered continuation sentence: a live controller or any
 * unresolved/effect-unknown signal dominates every green or success heading. */
function turnStatus(zh: boolean, activity: FreshConversationTurnPanelProps["activity"],
  operationState: OperationState | null, data: FreshAttendedData | null):
  { key: TurnKey; title: string } | null {
  const text = (en: string, cn: string) => zh ? cn : en;
  if (activity === "keeping") return { key: "keeping", title: text("Keeping response…", "正在保留回复…") };
  if (activity === "sending") return { key: "sending", title: text("Sending message…", "正在发送消息…") };
  if (activity === "checking") return { key: "checking", title: text("Checking original request…", "正在查询原请求…") };
  const controller = operationState?.status ?? null;
  if (controller === "submitting") return { key: "sending", title: text("Sending message…", "正在发送消息…") };
  if (controller === "checking") return { key: "checking", title: text("Checking original request…", "正在查询原请求…") };
  if (controller === "unknown" || data?.state === "RECONCILIATION_REQUIRED" || data?.effect === "UNKNOWN") {
    return {
      key: "unresolved",
      title: text("The original request needs a status check. Don’t send it again.",
        "原请求需要查询状态。请勿再次发送。"),
    };
  }
  if (data?.state === "RECORDED") {
    return { key: "recorded", title: text("Follow-up response recorded", "已记录后续回复") };
  }
  if (data?.state === "ABSENT") {
    return {
      key: "absent",
      title: data.turn_key===null&&data.initial_consumption===null
        ? text("First response not kept yet", "首条回复尚未保留")
        : text("No follow-up is recorded for this original request yet.", "此原请求尚未记录后续回复。"),
    };
  }
  if (controller === "refused") {
    return {
      key: "refused",
      title: text("The request was refused. Your message remains a draft.", "请求被拒绝。消息仍保留为草稿。"),
    };
  }
  return null;
}

/** Bounded source rows; raw codes live only inside the closed disclosure. */
function sourceRows(zh: boolean, operationState: OperationState | null,
  data: FreshAttendedData | null, initialConsumption: FreshConversationTurnConsumption | null): { label: string; value: string }[] {
  const text = (en: string, cn: string) => zh ? cn : en;
  const notSupplied = text("Not supplied", "未提供");
  const flag = (value: boolean | undefined) => value === undefined ? notSupplied : String(value);
  const join = (parts: (string | null)[]) => parts.filter(part => part != null).join(" · ");
  const locator = data?.locator ?? null;
  const reference = data?.reference ?? null;
  const receipt = data?.initial_consumption ?? initialConsumption;
  return [
    { label: text("Server schema", "服务端结构标识"), value: data?.schema ?? notSupplied },
    { label: text("Turn state", "回合状态"), value: data?.state ?? notSupplied },
    { label: text("Effect", "效果"), value: data?.effect ?? notSupplied },
    { label: text("Work reference", "工作引用"), value: data?.work_ref ?? notSupplied },
    { label: text("Operation key", "操作键"), value: data?.operation_key ?? notSupplied },
    { label: text("Turn key", "回合键"), value: data?.turn_key ?? notSupplied },
    {
      label: text("Locator", "定位记录"),
      value: locator == null ? notSupplied
        : join([`root ${locator.root_job_id}`,
          locator.job_id == null ? null : `job ${locator.job_id}`,
          locator.attempt_id == null ? null : `attempt ${locator.attempt_id}`]),
    },
    {
      label: text("Reference root", "引用根"),
      value: reference == null ? notSupplied
        : join([`root ${reference.root_job_id}`, `event ${reference.root_event_id}`]),
    },
    { label: text("Reference event hash", "引用事件摘要"), value: reference?.root_event_sha256 ?? notSupplied },
    { label: text("Principal scope", "主体范围"), value: reference?.principal_scope_sha256 ?? notSupplied },
    {
      label: text("First-response receipt", "首条回复回执"),
      value: receipt == null ? notSupplied : `event ${receipt.event_id} · ${receipt.event_sha256}`,
    },
    { label: text("First-response digest", "首条回复摘要"), value: receipt?.initial_digest ?? notSupplied },
    { label: text("Follow-up digest", "后续回复摘要"), value: data?.result?.digest ?? notSupplied },
    { label: text("Continuation (can_send)", "继续发送 (can_send)"), value: flag(data?.can_send) },
    { label: text("Parent consumed", "父级已接收"), value: flag(data?.parent_consumed) },
    { label: text("Controller state", "控制器状态"), value: operationState?.status ?? notSupplied },
    { label: text("Controller reason", "控制器原因"), value: operationState?.reason ?? notSupplied },
  ];
}

/** Controlled follow-up continuation view. The parent owns the controller, the
 * decoded window and every guarded action; this component renders the handed
 * state, forwards exact draft text and never mints or infers a permission. */
export function FreshConversationTurnPanel({ locale, data, operationState, activity, message,
  onMessageChange, readOnly, keepControl, sendControl, checkControl, feedback, originalTurnMessage, initialConsumption = null, responsePending = false, allowNextMessage = false, allowInitialKeep = false, recordedTurns = [], historyLimited = false, messageReadOnly = false, onMessageFocus, messagePreview }: FreshConversationTurnPanelProps) {
  const inputId=useId();
  const zh = locale === "zh-CN";
  const text = (en: string, cn: string) => zh ? cn : en;
  const status = turnStatus(zh, activity, operationState, data);
  const busy = activity != null || status?.key === "sending" || status?.key === "checking";
  const unresolved = status?.key === "unresolved";
  const recorded = status?.key === "recorded";
  const absent = status?.key === "absent";
  const receipt = data?.initial_consumption ?? initialConsumption;
  const result = data?.result ?? null;
  /** Absent submitted turns stay held; the owner alone may qualify an initial Keep. */
  const unsubmittedInitial=allowInitialKeep&&absent&&data?.turn_key===null&&receipt==null;
  const holdActions = busy || unresolved || recorded && !allowNextMessage || absent && !unsubmittedInitial || responsePending || status?.key === "refused";
  const keepVisible = keepControl != null && receipt == null && !holdActions;
  const sendVisible = sendControl != null && receipt != null && !holdActions;
  const inputHeld = readOnly || busy || unresolved || recorded && !allowNextMessage || responsePending;
  const showUnavailable = !busy && !unresolved && !recorded && !responsePending && !keepVisible && !sendVisible;
  return <section className="mm-fresh-conversation-turn" lang={zh ? "zh-CN" : "en"}>
    <h2 className="mm-fresh-conversation-turn-heading">{text("Continue this conversation", "继续此对话")}</h2>
    {status != null && <p role="status" className="mm-fresh-conversation-turn-status">{status.title}</p>}
    {responsePending && !recorded && !busy && !unresolved && <p role="status" className="mm-fresh-conversation-turn-status">
      {text("Check the original request to read its response. Don’t send another message here.", "请查看原请求以读取回复。请勿在此再次发送消息。")}
    </p>}
    <p className="mm-fresh-conversation-turn-receipt">
      {receipt != null ? text("First response kept", "已保留第一条回复")
        : text("Keep the first response to continue.", "保留第一条回复后继续。")}
    </p>
    {historyLimited && <p>{text("Earlier replies remain available in project conversation history.", "更早的回复仍可在项目对话历史中查看。")}</p>}
    {recordedTurns.map(turn=><section className="mm-fresh-conversation-turn-followup" key={turn.data.turn_key}>
      {turn.data.result&&!("envelope"in turn.data.result)?<NativeTurnNotice locale={locale} message={turn.message}/>:
       <FreshConversationInitialResponse locale={locale} result={turn.data.result&&"envelope"in turn.data.result?turn.data.result:null} originalMessage={turn.message}
        responseKind="followup" headingLevel={3}/>}
    </section>)}
    {recorded && result != null && !recordedTurns.some(turn=>turn.data.turn_key===data?.turn_key) && <section className="mm-fresh-conversation-turn-followup">
      {!("envelope"in result)?<NativeTurnNotice locale={locale} message={originalTurnMessage??null}/>:
       <FreshConversationInitialResponse locale={locale} result={result} originalMessage={originalTurnMessage??null} responseKind="followup" headingLevel={3}
        caption={data?.parent_consumed === false
          ? text("Reading this result does not acknowledge it.", "查看此结果并不表示已确认接收。") : null} />}
    </section>}
    {receipt != null && (!recorded || allowNextMessage) && (messagePreview ?? <div className="mm-fresh-conversation-turn-field">
      <label className="mm-fresh-conversation-turn-label" htmlFor={inputId}>
        {text("Your next message", "下一条消息")}
      </label>
      <textarea id={inputId} className="mm-fresh-conversation-turn-input"
        value={message} disabled={inputHeld} readOnly={messageReadOnly} onFocus={onMessageFocus} rows={4}
        onChange={event => onMessageChange(event.target.value)} />
      <p className="mm-fresh-conversation-turn-hint">
        {text("Your messages stay in this conversation.", "消息将保留在此对话中。")}
      </p>
    </div>)}
    {(keepVisible || sendVisible || checkControl != null) &&
      <div className="mm-fresh-conversation-turn-actions">
        {keepVisible ? keepControl : null}
        {sendVisible ? sendControl : null}
        {checkControl != null ? checkControl : null}
      </div>}
    {showUnavailable && <p className="mm-fresh-conversation-turn-note">
      {text("Continuing is unavailable here right now. Your message remains a draft.",
        "此处暂时无法继续对话。消息仍是草稿。")}
    </p>}
    {feedback}
    <details className="mm-fresh-conversation-turn-sources">
      <summary>{text("Sources and request", "来源与请求")}</summary>
      <div className="mm-fresh-conversation-turn-source-list">
        {sourceRows(zh, operationState, data, initialConsumption).map(row =>
          <div key={row.label} className="mm-fresh-conversation-turn-source">
            <span>{row.label}</span>
            <code>{row.value}</code>
          </div>)}
      </div>
    </details>
  </section>;
}


function NativeTurnNotice({locale,message}:{locale:"en"|"zh-CN";message:string|null}){
 const zh=locale==="zh-CN";
 return <>
  <h3>{zh?"已记录后续回复":"Follow-up response recorded"}</h3>
  {message!==null?<p style={{whiteSpace:"pre-wrap"}}>{message}</p>:null}
  <p>{zh?"打开“已记录对话”以读取原始回复。":"Open Recorded conversation to read the original answer."}</p>
 </>;
}
