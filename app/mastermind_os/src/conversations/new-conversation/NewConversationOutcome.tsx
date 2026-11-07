import type { ReactNode } from "react";
import type { OperationState } from "../../orchestration/operation-controller";
import type { FreshConversationPayload } from "./fresh-conversation";
import type {FreshConversationObservedData} from "./fresh-conversation-contract";
import "./new-conversation-outcome.css";

export interface NewConversationOutcomeProps {
  locale: "en" | "zh-CN";
  /** Parent-coupled fresh server data; null until a confirmed read exists. */
  data: FreshConversationObservedData | null;
  /** Live controller observation; null when the controller holds no state here. */
  operationState: OperationState | null;
  originalMessage: string | null;
  projectTitle: string | null;
  /** Parent-explicit read gesture; this view never opens or refreshes itself. */
  opened: boolean;
  busy: boolean;
  contract?: "legacy-v1"|"native-v2";
  observing?: boolean;
  canObserveWhileCreating?: boolean;
  /** Actual caller-side await activity; never a provider state. */
  activity?: "creating" | "checking" | null;
  /** Parent permission gate: server data alone never enables the open control. */
  canOpen: boolean;
  /** A selected lookup has not yet been read; no availability conclusion. */
  awaitingCheck?: boolean;
  onCheck: () => void;
  onOpen: () => void;
  onBack: () => void;
  /** Independently qualified attended controls; absent keeps this view read-only. */
  continuation?: ReactNode;
}

type OutcomeKey = "submitting" | "checking" | "unconfirmed" | "admitted" | "absent"
  | "created" | "settled" | "refused" | "unavailable" | "awaiting" | "active" | "idle";

/** A created claim needs a real session binding AND a real locator, never either alone. */
function createdConfirmed(data: FreshConversationObservedData | null): boolean {
  return data != null && (data.state === "CREATED"||data.schema==="mastermind.executive.fresh_conversation_data.v2"&&data.state==="IDLE") && data.session != null && data.locator != null;
}

function settledWithLocator(data: FreshConversationObservedData | null): boolean {
  return data != null && data.state === "SETTLED" && data.locator != null;
}

/** Only a plain string summary is reply text; other envelope members are never content. */
function envelopeSummary(result: FreshConversationPayload | null): string | null {
  if (result == null) return null;
  const envelope: unknown = result.envelope;
  if (typeof envelope !== "object" || envelope === null) return null;
  const summary: unknown = (envelope as Record<string, unknown>)["summary"];
  return typeof summary === "string" ? summary : null;
}

/** Priority-ordered outcome sentence: live controller truth outranks stale data. */
function outcomeStatus(zh: boolean, operationState: OperationState | null,
  data: FreshConversationObservedData | null): { key: OutcomeKey; title: string } {
  const text = (en: string, cn: string) => zh ? cn : en;
  const controller = operationState?.status ?? null;
  if(data?.schema==="mastermind.executive.fresh_conversation_data.v2"){
    if(data.state==="ACTIVE")return {key:"active",title:text("The response is running.","正在生成回复。")};
    if(data.state==="IDLE")return {key:"idle",title:text("The conversation is stopped. Check its recorded response before resuming.","对话已停止。请查看已记录的回复后再继续。")};
    if(data.state==="SETTLED"&&data.result)return {key:"settled",title:text("Conversation completed","对话已完成")};
  }
  if (controller === "submitting") {
    return { key: "submitting", title: text("Creating conversation…", "正在创建对话…") };
  }
  if (controller === "checking") {
    return { key: "checking", title: text("Checking original request…", "正在查看原请求…") };
  }
  if (controller === "unknown" || data?.state === "RECONCILIATION_REQUIRED") {
    return {
      key: "unconfirmed",
      title: text("The outcome is not confirmed. Check the original request; do not create it again.",
        "结果尚未确认。请查看原请求状态，不要再次创建。"),
    };
  }
  if (data?.state === "ADMITTED") {
    return {
      key: "admitted",
      title: text("Conversation request accepted. The conversation is not confirmed yet.",
        "对话请求已接收，尚未确认对话已创建。"),
    };
  }
  if (data?.state === "ABSENT") {
    return {
      key: "absent",
      title: text("No outcome can be confirmed for this original request yet.", "尚未确认此原请求的结果。"),
    };
  }
  if (createdConfirmed(data)) {
    return { key: "created", title: text("Conversation created", "对话已创建") };
  }
  if (data?.state === "SETTLED") {
    return { key: "settled", title: text("Original request completed", "原请求已完成") };
  }
  if (controller === "refused") {
    return {
      key: "refused",
      title: text("The request was refused. Your message remains a draft.", "请求被拒绝。消息仍保留为草稿。"),
    };
  }
  return { key: "unavailable", title: text("Conversation status is unavailable here.", "此处暂时无法查看对话状态。") };
}

/** Bounded source rows; raw codes appear only inside the closed disclosure. */
function sourceRows(zh: boolean, operationState: OperationState | null,
  data: FreshConversationObservedData | null): { label: string; value: string }[] {
  const text = (en: string, cn: string) => zh ? cn : en;
  const notSupplied = text("Not supplied", "未提供");
  const locator = data?.locator ?? null;
  const session = data?.session ?? null;
  const flag = (value: boolean | undefined) => value === undefined ? notSupplied : String(value);
  return [
    { label: text("Server schema", "服务端结构标识"), value: data?.schema ?? notSupplied },
    { label: text("Server state", "服务端状态"), value: data?.state ?? notSupplied },
    { label: text("Operation key", "操作键"), value: data?.operation_key ?? notSupplied },
    { label: text("Work reference", "工作引用"), value: data?.work_ref ?? notSupplied },
    {
      label: text("Locator", "定位记录"),
      value: locator == null ? notSupplied
        : `root ${locator.root_job_id} · job ${locator.job_id} · attempt ${locator.attempt_id}`,
    },
    {
      label: text("Session binding", "会话绑定"),
      value: session == null ? notSupplied
        : "session_epoch_id"in session
          ? `attempt ${session.attempt_id} · epoch ${session.session_epoch_id} · process ${session.process_generation_id} · binding ${session.binding_digest}`
          : `attempt ${session.attempt_id} · generation ${session.generation} · binding ${session.binding_digest}`,
    },
    { label: text("Result digest", "结果摘要"), value: data?.result?.digest ?? notSupplied },
    { label: text("Parent consumed", "父级已接收"), value: flag(data?.parent_consumed) },
    { label: text("Continuation (can_send)", "继续发送 (can_send)"), value: flag(data?.can_send) },
    { label: text("Controller state", "控制器状态"), value: operationState?.status ?? notSupplied },
    { label: text("Controller reason", "控制器原因"), value: operationState?.reason ?? notSupplied },
  ];
}

/** Controlled request-status/initial-result view. The parent owns the controller,
 * binding and currentness; this component only renders what it is handed. */
export function NewConversationOutcome({ locale, data, operationState, originalMessage,
  projectTitle, opened, busy, contract="legacy-v1", observing=false, canObserveWhileCreating=false, activity = null, canOpen, awaitingCheck = false, onCheck, onOpen, onBack, continuation }: NewConversationOutcomeProps) {
  const zh = locale === "zh-CN";
  const text = (en: string, cn: string) => zh ? cn : en;
  const native=contract==="native-v2"||data?.schema==="mastermind.executive.fresh_conversation_data.v2";
  const nativeActive=data?.schema==="mastermind.executive.fresh_conversation_data.v2"&&data.state==="ACTIVE";
  const status = activity === "creating"&&!nativeActive ? {key:"submitting" as const,title:text("Creating conversation…","正在创建对话…")}
    : activity === "checking" ? {key:"checking" as const,title:text("Checking original request…","正在查看原请求…")}
    : awaitingCheck && data == null && operationState == null
      ? {key:"awaiting" as const,title:text("Check the original request to view its status.", "请查看原请求以了解其状态。")}
      : outcomeStatus(zh, operationState, data);
  const result = data?.result ?? null;
  const responseOpenable = canOpen && (createdConfirmed(data) || settledWithLocator(data));
  const backAnnotated = status.key === "submitting" || status.key === "checking"
    || status.key === "unconfirmed" || status.key === "admitted" || status.key === "absent" || status.key==="active";
  return <section className="mm-new-conversation-outcome" lang={zh ? "zh-CN" : "en"}>
    <header className="mm-new-conversation-outcome-heading">
      {opened ? <>
        <h1>{text("Conversation", "对话")}</h1>
        {projectTitle != null && <p className="mm-new-conversation-outcome-subtitle">{projectTitle}</p>}
        <p className="mm-new-conversation-outcome-scope">
          {continuation==null?text("Only the initial response is shown here.", "此处仅显示首条回复。")
            :text("The first response and any recorded follow-up are shown here.", "此处显示首条回复及已记录的后续回复。")}
        </p>
      </> : <>
        <h1>{text("New conversation", "新建对话")}</h1>
        <p className="mm-new-conversation-outcome-status">{status.title}</p>
      </>}
    </header>
    {opened && backAnnotated && <p role="status" className="mm-new-conversation-outcome-status">{status.title}</p>}
    {opened && !native && <FreshConversationInitialResponse locale={locale} result={result&&"envelope"in result?result:null} originalMessage={originalMessage}
      caption={result != null && data?.parent_consumed === false
        ? text("Reading this result does not acknowledge it.", "查看此结果并不表示已确认接收。") : null}
      continuation={continuation==null?<p className="mm-new-conversation-outcome-caption">{text("Further messages are not available in this view yet.", "此视图暂不支持继续发送消息。")}</p>:undefined}/>}
    {native&&operationState?.status==="unknown"&&data?.state!=="RECONCILIATION_REQUIRED"&&
      <p role="status">{text("The original request is still being reconciled. Do not send it again.","原请求仍在核对中。请勿再次发送。")}</p>}
    {(opened||native)&&continuation!=null?continuation:null}
    <footer className="mm-new-conversation-outcome-footer">
      <div className="mm-new-conversation-outcome-actions">
        <button type="button" disabled={observing||busy&&!canObserveWhileCreating} onClick={onCheck}>
          {continuation==null?text("Check original request", "查看原请求状态"):text("Check initial request", "查看首次请求状态")}
        </button>
        {!opened && responseOpenable && <button type="button" className="primary" disabled={busy} onClick={onOpen}>
          {text("Open initial response", "查看首条回复")}
        </button>}
        <button type="button" onClick={onBack}>{text("Back to conversations", "返回对话")}</button>
      </div>
      {!opened && backAnnotated &&
        <p className="mm-new-conversation-outcome-caption">
          {text("Going back does not cancel the original request.", "返回不会取消原请求。")}
        </p>}
    </footer>
    <details className="mm-new-conversation-outcome-sources">
      <summary>{text("Sources and access", "来源与访问")}</summary>
      <div className="mm-new-conversation-outcome-source-list">
        {sourceRows(zh, operationState, data).map(row =>
          <div key={row.label} className="mm-new-conversation-outcome-source">
            <span>{row.label}</span>
            <code>{row.value}</code>
          </div>)}
      </div>
    </details>
  </section>;
}


/** Reusable initial-result body. The source/reference reader owns exact
 * result+locator validation, its own heading/provenance, and actual action
 * slots; it never needs to manufacture an old operation-key DTO. */
export interface FreshConversationInitialResponseProps {
  locale: "en" | "zh-CN";
  result: FreshConversationPayload | null;
  originalMessage: string | null;
  caption?: ReactNode;
  continuation?: ReactNode;
  /** A recorded follow-up stays distinct from the original first response. */
  responseKind?: "initial" | "followup";
  headingLevel?: 2 | 3;
}
export function FreshConversationInitialResponse({locale,result,originalMessage,caption,continuation,responseKind="initial",headingLevel=2}:FreshConversationInitialResponseProps){
  const text=(en:string,cn:string)=>locale==="zh-CN"?cn:en;
  const summary=envelopeSummary(result);
  const Heading=headingLevel===3?"h3":"h2";
  const followup=responseKind==="followup";
  return <div className="mm-new-conversation-outcome-panel" lang={locale}>
    {originalMessage!==null&&<div className="mm-new-conversation-outcome-field">
      <p className="mm-new-conversation-outcome-label">{followup?text("Your message","你的消息"):text("Your first message","你的首条消息")}</p>
      <p className="mm-new-conversation-outcome-pre">{originalMessage}</p></div>}
    <section className="mm-new-conversation-outcome-field"><Heading>{followup?text("Follow-up response","后续回复"):text("Initial response","首条回复")}</Heading>
      {summary!==null?<p className="mm-new-conversation-outcome-pre">{summary}</p>:<p className="mm-new-conversation-outcome-missing">{followup?text("The follow-up response is not available yet.","暂时还没有可查看的后续回复。"):text("The initial response is not available yet.","暂时还没有可查看的首条回复。")}</p>}
      {caption!=null&&<p className="mm-new-conversation-outcome-caption">{caption}</p>}
    </section>{continuation}
  </div>;
}
