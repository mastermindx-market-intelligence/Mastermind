import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { observedMissionAssociation } from "../workspace-contract";
import type { OfficeProjection, SourceClaim } from "../meta-ceo/projection";
import type { MissionResultRead } from "../host";
import { normalizeResultSelection, type ResultSelection } from "../result";
import type { DraftInsertion, DraftSource } from "./drafts";
import { ResultSourceReader } from "./ResultSourceReader";
import "./conversation.css";

type ConversationLocale = "en" | "zh-CN";
const STATIC_ZH: Record<string, string> = {
  "Conversations": "对话",
  "Owner": "所有者",
  "Reference": "引用",
  "Revision": "修订",
  "Not supplied": "未提供",
  "Locally acquired": "本地获取",
  "Observed": "已观察",
  "State": "状态",
  "Coverage": "覆盖范围",
  "Observed managed turn window": "已观察的托管对话窗口",
  "Context": "上下文",
  "History is not proven.": "历史记录尚未得到证明。",
  "Keep the original operation. Reconcile its outcome before resend, failover or target change.": "请保留原操作。在再次发送、切换或更改目标前，先确认原操作的结果。",
  "Observed Job/Attempt association": "已观察的作业与尝试关联",
  "Session identity has not been supplied for this window.": "此窗口尚未提供会话身份。",
  "Retained window; current conversation state is not established.": "保留的视图；当前对话状态尚未确认。",
  "Observed responses": "已观察的回复",
  "Content withheld": "内容已隐藏",
  "Owner-visible response": "所有者提供的回复",
  "Content withheld by its owner.": "内容已被所有者隐藏。",
  "No visible response was supplied in this observed window.": "此窗口尚未提供可见回复。",
  "The owner reported gaps in this window.": "所有者报告此窗口存在缺漏。",
  "Returned evidence": "返回的证据",
  "A source-backed result is available.": "有可查看的来源结果。",
  "Inspect the supplied sources.": "查看已提供的来源。",
  "The exact result source is open below. Review and acceptance remain separate.": "下方已打开精确结果来源。审阅与接受仍相互独立。",
  "Result source": "结果来源",
  "Review and acceptance remain separate.": "审阅与接受仍相互独立。",
  "Review evidence": "审阅证据",
  "View evidence": "查看证据",
  "Delivery, review and acceptance": "交付、审阅与接受",
  "Independent receipts": "独立回执",
  "Conversation source": "对话来源",
  "Content is withheld.": "内容已隐藏。",
  "A qualified window is not available.": "暂无已核验的窗口。",
  "The current owner source does not establish this conversation.": "当前所有者来源尚未证明此对话。",
  "No transcript or session relationship is reconstructed from neighboring records.": "不会从相邻记录重建对话或会话关系。",
  "Unsent draft": "未发送草稿",
  "Unsent notes": "未发送的笔记",
  "Keep a thought here…": "在此记下想法…",
  "No recipient is qualified by this window. Send is unavailable.": "此窗口未核验收件方。无法发送。",
  "Send message": "发送消息",
  "Send message is unavailable": "暂时无法发送消息",
  "Draft only · Opening evidence or context never sends.": "仅为草稿 · 打开证据或上下文不会发送。",
  "Conversation evidence": "对话证据",
  "Conversation context": "对话上下文",
  "Evidence": "证据",
  "Close evidence": "关闭证据",
  "Close context": "关闭上下文",
  "Observed window": "已观察的窗口",
  "Read exact result source": "阅读精确结果来源",
  "An exact result and its fixed read capability are required. No source is guessed.": "需要精确结果及其固定读取能力。不会猜测来源。",
  "Window observations do not prove action/result correspondence or acceptance.": "窗口观察不能证明行动与结果对应或已被接受。",
  "Selected project context": "所选项目上下文",
  "This window supplies no provider conversation, session binding or model selection.": "此窗口不提供供应方对话、会话绑定或模型选择。",
  "A Meta-CEO recommendation has not been supplied by its owner.": "所有者尚未提供 Meta-CEO 建议。"
};
function ui(locale: ConversationLocale, text: string) { return locale === "zh-CN" ? STATIC_ZH[text] ?? text : text; }

export interface ConversationWindowProps {
  locale?: ConversationLocale;
  /** Exact parent-created owner-keyed element; this window supplies no command identity. */
  continuation?: ReactNode;
  notesPresentation?: "inline" | "collapsed";
  projection: OfficeProjection;
  /** Shell-controlled, unsent text. Scope and auth isolation live in drafts.ts. */
  draft: string;
  onDraftChange: (text: string) => void;
  readResult?: MissionResultRead;
  draftRevision?: number;
  draftInsertion?: DraftInsertion | null;
  onAppendSource?: (source: DraftSource, expectedRevision: number) => boolean;
  onUndoSource?: (identity: string, expectedRevision: number) => boolean;
}
function Provenance({ source, locale }: { source: SourceClaim; locale: ConversationLocale }) {
  return <dl><dt>{ui(locale, "Owner")}</dt><dd>{source.owner}</dd><dt>{ui(locale, "Reference")}</dt><dd>{source.ref ?? ui(locale, "Not supplied")}</dd>
    <dt>{ui(locale, "Revision")}</dt><dd>{source.revision ?? ui(locale, "Not supplied")}</dd>
    <dt>{source.observed_at_kind === "LOCAL_ACQUISITION" ? ui(locale, "Locally acquired") : ui(locale, "Observed")}</dt><dd>{source.observed_at ?? ui(locale, "Not supplied")}</dd>
    <dt>{ui(locale, "State")}</dt><dd>{source.state}</dd><dt>{ui(locale, "Coverage")}</dt><dd>{source.coverage}</dd></dl>;
}
function observationKey(projection: OfficeProjection) {
  const { context, conversation, mission, result } = projection;
  return JSON.stringify([context.authGeneration, context.selection, context.sessionRef,
    context.bindingGeneration, context.revisions.conversation, context.revisions.mission, context.revisions.result,
    conversation.source.state, mission.source.state, result.source.state]);
}
function ConversationBody({ projection, draft, onDraftChange, readResult, draftRevision,
  draftInsertion, onAppendSource, onUndoSource, locale = "en", notesPresentation = "inline", continuation }: ConversationWindowProps) {
  const [notesOpen, setNotesOpen] = useState(notesPresentation !== "collapsed");
  const notesTrigger = useRef<HTMLButtonElement>(null);
  const pendingNotesFocus = useRef(false);
  const [panel, setPanel] = useState<"evidence" | "context" | null>(null);
  const [readerSelection, setReaderSelection] = useState<ResultSelection | null>(null);
  const evidenceTrigger = useRef<HTMLButtonElement>(null), contextTrigger = useRef<HTMLButtonElement>(null);
  const sourceTrigger = useRef<HTMLButtonElement>(null), draftInput = useRef<HTMLTextAreaElement>(null);
  const returningFromReader = useRef(false);
  const companion = useRef<HTMLElement>(null), panelId = useId();
  const { conversation: read, mission, result, context } = projection;
  const currentObservation = observationKey(projection);
  const [inspectedObservation, setInspectedObservation] = useState(currentObservation);
  if (inspectedObservation !== currentObservation) {
    // Discard inspection state before committing changed evidence, including A-B-A.
    // Notes are parent-scoped and survive a passive observation refresh.
    setInspectedObservation(currentObservation);
    setPanel(null);
    setReaderSelection(null);
    returningFromReader.current = false;
    pendingNotesFocus.current = false;
  }
  useLayoutEffect(() => { if (notesOpen && pendingNotesFocus.current && draftInput.current) { pendingNotesFocus.current = false; draftInput.current.focus(); } }, [notesOpen, readerSelection]);
  const retained = read.source.state === "CURRENT" || read.source.state === "STALE";
  // Defensive reduction: neither a context.sessionRef nor a runtime card can
  // promote this window's Job/Attempt observation into exact session identity.
  const association = mission.source.state === "CURRENT"
    ? observedMissionAssociation(read.value, mission.value, context.selection) : null;
  const document = retained && association ? read.value : null;
  const refs = mission.value?.schema === "mastermind.mission_workspace.v3" ? mission.value.result_refs.refs : [];
  const candidates = association ? refs.filter(ref => ref.root_job_id === context.selection?.rootJobId &&
    ref.job_id === association.job_id && ref.attempt_id === association.attempt_id) : [];
  const exactResult = candidates.length === 1 ? normalizeResultSelection({
    workRef: context.selection?.workRef, rootJobId: candidates[0].root_job_id,
    jobId: candidates[0].job_id, attemptId: candidates[0].attempt_id, resultEnvelopeDigest: candidates[0].result_envelope_digest,
  }) : null;
  const state = retained && read.value && !association ? "UNASSOCIATED" : read.source.state;
  const privateHidden = state === "WITHHELD";
  const title = mission.source.state === "CURRENT" ? mission.value?.program.title : null;
  const effectUnknown = mission.source.state === "CURRENT" && projection.receipts.effect === "EFFECT_UNKNOWN";
  const resultRetained = result.source.state === "CURRENT" || result.source.state === "STALE";
  // A result qualified for this Project may belong to another child/attempt.
  // Keep it out of this window's evidence until its observed tuple also matches.
  const resultVisible = resultRetained && !!association && !!result.value &&
    result.value.selection.job_id === association.job_id && result.value.selection.attempt_id === association.attempt_id;
  const resultState = resultRetained && result.value && !resultVisible ? "UNASSOCIATED for this window" : result.source.state;
  const resultSummary = resultVisible ? result.value?.result?.content?.summary : null;
  const showPanel = !!panel && !!document;
  useEffect(() => { if (showPanel) companion.current?.focus(); }, [showPanel, panel]);
  useLayoutEffect(() => {
    if (!readerSelection && returningFromReader.current) {
      returningFromReader.current = false; sourceTrigger.current?.focus();
    }
  }, [readerSelection]);
  const close = () => {
    const trigger = panel === "evidence" ? evidenceTrigger : contextTrigger;
    setPanel(null); trigger.current?.focus();
  };
  return <section className="atelier-conversation" aria-label={ui(locale, "Conversations")}>
    <header className="conversation-header"><div className="conversation-mark" aria-hidden="true">✧</div>
      <div><h1>{title || ui(locale, "Conversations")}</h1><p>{ui(locale, "Observed managed turn window")}</p></div>
      <button ref={contextTrigger} type="button" disabled={!document} aria-expanded={panel === "context" && showPanel}
        aria-controls={panelId} onClick={() => { setReaderSelection(null); setPanel(panel === "context" ? null : "context"); }}>{ui(locale, "Context")}</button></header>
    <div className="conversation-layout" data-companion={showPanel}>
      <div className="conversation-reading">
        <div className="conversation-source"><span data-state={state} className="conversation-state">{state}</span>
          <p>{read.source.coverage} · {ui(locale, "History is not proven.")}</p></div>
        {effectUnknown && <div className="conversation-alert" role="alert"><strong>EFFECT_UNKNOWN</strong>
          <p>{ui(locale, "Keep the original operation. Reconcile its outcome before resend, failover or target change.")}</p></div>}
        {document ? <>
          <details className="conversation-association"><summary>{ui(locale, "Observed Job/Attempt association")}</summary>
            <p>{association!.job_id} · {association!.attempt_id}</p>
            <p>{ui(locale, "Session identity has not been supplied for this window.")}</p></details>
          {state === "STALE" && <p className="conversation-history">{ui(locale, "Retained window; current conversation state is not established.")}</p>}
          <section className="conversation-transcript" aria-label={ui(locale, "Observed responses")}>
            {document.view.items.map(item => <article key={item.id} className="conversation-response">
              <p className="conversation-eyebrow">{item.kind === "withheld" ? ui(locale, "Content withheld") : ui(locale, "Owner-visible response")} · {item.state}</p>
              {item.kind === "withheld" ? <p>{ui(locale, "Content withheld by its owner.")}</p> : <p className="conversation-answer">{item.text}</p>}
            </article>)}
            {!document.view.items.length && <p>{ui(locale, "No visible response was supplied in this observed window.")}</p>}
            {!!document.view.gaps.length && <p className="conversation-history">{ui(locale, "The owner reported gaps in this window.")}</p>}
          </section>
          <section className="conversation-result" aria-label={ui(locale, "Returned evidence")}>
            <div><p className="conversation-eyebrow">{ui(locale, "Returned evidence")}</p><h2>{resultSummary ? ui(locale, "A source-backed result is available.") : ui(locale, "Inspect the supplied sources.")}</h2>
              {resultSummary && <p>{resultSummary}</p>}
              <p>{readerSelection ? ui(locale, "The exact result source is open below. Review and acceptance remain separate.") : `${ui(locale, "Result source")} · ${resultState}. ${ui(locale, "Review and acceptance remain separate.")}`}</p></div>
            <button type="button" ref={evidenceTrigger} aria-expanded={panel === "evidence" && showPanel} aria-controls={panelId}
              onClick={() => { setReaderSelection(null); setPanel(panel === "evidence" ? null : "evidence"); }}>{ui(locale, continuation != null ? "View evidence" : "Review evidence")}</button>
          </section>
          <details className="conversation-receipts"><summary>{ui(locale, "Delivery, review and acceptance")}</summary>
            <section aria-label={ui(locale, "Independent receipts")}>{Object.entries(projection.receipts).map(([name, value]) =>
              <div key={name}><span>{name}</span><strong>{value ?? "NOT_PROJECTED"}</strong></div>)}</section>
          </details>
        </> : <div className="conversation-empty"><p className="conversation-eyebrow">{ui(locale, "Conversation source")}</p>
          <h2>{privateHidden ? ui(locale, "Content is withheld.") : ui(locale, "A qualified window is not available.")}</h2>
          <p>{read.reason || ui(locale, "The current owner source does not establish this conversation.")}</p>
          <p>{ui(locale, "No transcript or session relationship is reconstructed from neighboring records.")}</p></div>}
        {!privateHidden && <div className="conversation-notes" onKeyDown={event => {
          if (notesPresentation === "collapsed" && event.key === "Escape" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) { setNotesOpen(false); notesTrigger.current?.focus(); }
        }}>
          {notesPresentation === "collapsed" && <button ref={notesTrigger} type="button" className="conversation-notes-trigger" aria-expanded={notesOpen} aria-controls={`${panelId}-notes`} onClick={() => setNotesOpen(open => !open)}>{ui(locale, "Unsent notes")}</button>}
          {notesOpen && <div id={`${panelId}-notes`} className="conversation-composer">
          <label htmlFor={`${panelId}-draft`}>{ui(locale, notesPresentation === "collapsed" ? "Unsent notes" : "Unsent draft")}</label>
          <textarea ref={draftInput} id={`${panelId}-draft`} value={draft} rows={3} onChange={event => onDraftChange(event.target.value)}
            placeholder={ui(locale, "Keep a thought here…")} aria-describedby={`${panelId}-draft-reason`} />
          <div className="conversation-composer-actions"><p id={`${panelId}-draft-reason`}>{ui(locale, "No recipient is qualified by this window. Send is unavailable.")}</p>
            {notesPresentation === "inline" && <button type="button" disabled aria-label={ui(locale, "Send message")} title={ui(locale, "Send message is unavailable")}>↑</button>}</div>
          <p className="conversation-draft-note">{ui(locale, "Draft only · Opening evidence or context never sends.")}</p>
          </div>}
        </div>}
      </div>
      {showPanel && readerSelection && readResult ? <ResultSourceReader locale={locale} projection={projection} selection={readerSelection}
        readResult={readResult} draftRevision={draftRevision ?? 0} draftInsertion={draftInsertion ?? null}
        appendAvailable={!!onAppendSource && !!onUndoSource && draftRevision !== undefined && !!context.selection && !privateHidden}
        onAppend={(source, revision) => onAppendSource?.(source, revision) ?? false}
        onUndo={(identity, revision) => onUndoSource?.(identity, revision) ?? false}
        onEditDraft={() => { pendingNotesFocus.current = true; setNotesOpen(true); setReaderSelection(null); setPanel(null); }}
        onClose={() => { returningFromReader.current = true; setReaderSelection(null); }} />
        : showPanel && <aside id={panelId} ref={companion} tabIndex={-1} role="region"
        aria-label={ui(locale, panel === "evidence" ? "Conversation evidence" : "Conversation context")}
        className="conversation-companion" onKeyDown={event => {
          if (event.key === "Escape" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) close();
        }}>
        <header><h2>{ui(locale, panel === "evidence" ? "Evidence" : "Context")}</h2><button type="button" onClick={close}>{ui(locale, panel === "evidence" ? "Close evidence" : "Close context")}</button></header>
        {panel === "evidence" ? <><h3>{ui(locale, "Observed window")}</h3><Provenance source={read.source} locale={locale} />
          {resultVisible && result.value && <><h3>{ui(locale, "Result source")}</h3><Provenance source={result.source} locale={locale} /></>}
          <button ref={sourceTrigger} type="button" disabled={!exactResult || !readResult} onClick={() => {
            if (exactResult && readResult) setReaderSelection(exactResult);
          }}>{ui(locale, "Read exact result source")}</button>
          {(!exactResult || !readResult) && <p>{ui(locale, "An exact result and its fixed read capability are required. No source is guessed.")}</p>}
          <p>{ui(locale, "Window observations do not prove action/result correspondence or acceptance.")}</p></>
          : <><h3>{ui(locale, "Selected project context")}</h3><p>{context.selection?.workRef} · {context.selection?.rootJobId}</p>
            <Provenance source={mission.source} locale={locale} /><p>{ui(locale, "This window supplies no provider conversation, session binding or model selection.")}</p>
            <p>{ui(locale, "A Meta-CEO recommendation has not been supplied by its owner.")}</p></>}
      </aside>}
    </div>
  </section>;
}

/** Read-only owner projection. Exact managed sessions use the separate canonical
 * command binding; this component cannot promote a window to that capability. */
export function ConversationWindow(props: ConversationWindowProps) {
  const { context, conversation, mission, result } = props.projection;
  // Privacy/target changes still replace the body. Passive evidence refreshes
  // only withdraw inspection state, preserving the actual notes textarea.
  // Keep the owner's Session command slot outside both lifetimes.
  return <div className="conversation-window">
    <ConversationBody key={JSON.stringify([context.authGeneration, context.selection, context.sessionRef,
    context.bindingGeneration, conversation.source.state === "WITHHELD",
    mission.source.state === "WITHHELD", result.source.state === "WITHHELD"])} {...props} />
    {props.continuation != null && <div className="conversation-continuation-slot">{props.continuation}</div>}
  </div>;
}
