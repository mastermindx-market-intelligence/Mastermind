import { useEffect, useId, useRef, useState } from "react";
import { observedMissionAssociation } from "../workspace-contract";
import type { OfficeProjection, SourceClaim } from "../meta-ceo/projection";
import "./conversation.css";

export interface ConversationWindowProps {
  projection: OfficeProjection;
  /** Shell-controlled, unsent text. Scope and auth isolation live in drafts.ts. */
  draft: string;
  onDraftChange: (text: string) => void;
}
function Provenance({ source }: { source: SourceClaim }) {
  return <dl><dt>Owner</dt><dd>{source.owner}</dd><dt>Reference</dt><dd>{source.ref ?? "Not supplied"}</dd>
    <dt>Revision</dt><dd>{source.revision ?? "Not supplied"}</dd>
    <dt>{source.observed_at_kind === "LOCAL_ACQUISITION" ? "Locally acquired" : "Observed"}</dt><dd>{source.observed_at ?? "Not supplied"}</dd>
    <dt>State</dt><dd>{source.state}</dd><dt>Coverage</dt><dd>{source.coverage}</dd></dl>;
}
function ConversationBody({ projection, draft, onDraftChange }: ConversationWindowProps) {
  const [panel, setPanel] = useState<"evidence" | "context" | null>(null);
  const evidenceTrigger = useRef<HTMLButtonElement>(null), contextTrigger = useRef<HTMLButtonElement>(null);
  const companion = useRef<HTMLElement>(null), panelId = useId();
  const { conversation: read, mission, result, context } = projection;
  const retained = read.source.state === "CURRENT" || read.source.state === "STALE";
  // Defensive reduction: neither a context.sessionRef nor a runtime card can
  // promote this window's Job/Attempt observation into exact session identity.
  const association = mission.source.state === "CURRENT"
    ? observedMissionAssociation(read.value, mission.value, context.selection) : null;
  const document = retained && association ? read.value : null;
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
  const close = () => {
    const trigger = panel === "evidence" ? evidenceTrigger : contextTrigger;
    setPanel(null); trigger.current?.focus();
  };
  return <section className="atelier-conversation" aria-label="Conversations">
    <header className="conversation-header"><div className="conversation-mark" aria-hidden="true">✧</div>
      <div><h1>{title || "Conversations"}</h1><p>Observed managed turn window</p></div>
      <button ref={contextTrigger} type="button" disabled={!document} aria-expanded={panel === "context" && showPanel}
        aria-controls={panelId} onClick={() => setPanel(panel === "context" ? null : "context")}>Context</button></header>
    <div className="conversation-layout" data-companion={showPanel}>
      <div className="conversation-reading">
        <div className="conversation-source"><span data-state={state} className="conversation-state">{state}</span>
          <p>{read.source.coverage} · History is not proven.</p></div>
        {effectUnknown && <div className="conversation-alert" role="alert"><strong>EFFECT_UNKNOWN</strong>
          <p>Keep the original operation. Reconcile its outcome before resend, failover or target change.</p></div>}
        {document ? <>
          <div className="conversation-association"><p className="conversation-eyebrow">Observed Job/Attempt association</p>
            <p>{association!.job_id} · {association!.attempt_id}</p>
            <p>Session identity has not been supplied for this window.</p></div>
          {state === "STALE" && <p className="conversation-history">Retained window; current conversation state is not established.</p>}
          <section className="conversation-transcript" aria-label="Observed responses">
            {document.view.items.map(item => <article key={item.id} className="conversation-response">
              <p className="conversation-eyebrow">{item.kind === "withheld" ? "Content withheld" : "Owner-visible response"} · {item.state}</p>
              {item.kind === "withheld" ? <p>Content withheld by its owner.</p> : <p className="conversation-answer">{item.text}</p>}
            </article>)}
            {!document.view.items.length && <p>No visible response was supplied in this observed window.</p>}
            {!!document.view.gaps.length && <p className="conversation-history">The owner reported gaps in this window.</p>}
          </section>
          <section className="conversation-result" aria-label="Returned evidence">
            <div><p className="conversation-eyebrow">Returned evidence</p><h2>{resultSummary ? "A source-backed result is available." : "Inspect the supplied sources."}</h2>
              {resultSummary && <p>{resultSummary}</p>}
              <p>Result source · {resultState}. Review and acceptance remain separate.</p></div>
            <button type="button" ref={evidenceTrigger} aria-expanded={panel === "evidence" && showPanel} aria-controls={panelId}
              onClick={() => setPanel(panel === "evidence" ? null : "evidence")}>Review evidence</button>
          </section>
          <details className="conversation-receipts"><summary>Delivery, review and acceptance</summary>
            <section aria-label="Independent receipts">{Object.entries(projection.receipts).map(([name, value]) =>
              <div key={name}><span>{name}</span><strong>{value ?? "NOT_PROJECTED"}</strong></div>)}</section>
          </details>
        </> : <div className="conversation-empty"><p className="conversation-eyebrow">Conversation source</p>
          <h2>{privateHidden ? "Content is withheld." : "A qualified window is not available."}</h2>
          <p>{read.reason || "The current owner source does not establish this conversation."}</p>
          <p>No transcript or session relationship is reconstructed from neighboring records.</p></div>}
        {!privateHidden && <div className="conversation-composer">
          <label htmlFor={`${panelId}-draft`}>Unsent draft</label>
          <textarea id={`${panelId}-draft`} value={draft} rows={3} onChange={event => onDraftChange(event.target.value)}
            placeholder="Keep a thought here…" aria-describedby={`${panelId}-draft-reason`} />
          <div className="conversation-composer-actions"><p id={`${panelId}-draft-reason`}>No recipient is qualified by this window. Send is unavailable.</p>
            <button type="button" disabled aria-label="Send message" title="Send message is unavailable">↑</button></div>
          <p className="conversation-draft-note">Draft only · Opening evidence or context never sends.</p>
        </div>}
      </div>
      {showPanel && <aside id={panelId} ref={companion} tabIndex={-1} role="region"
        aria-label={panel === "evidence" ? "Conversation evidence" : "Conversation context"}
        className="conversation-companion" onKeyDown={event => { if (event.key === "Escape") close(); }}>
        <header><h2>{panel === "evidence" ? "Evidence" : "Context"}</h2><button type="button" onClick={close}>Close {panel}</button></header>
        {panel === "evidence" ? <><h3>Observed window</h3><Provenance source={read.source} />
          {resultVisible && result.value && <><h3>Result source</h3><Provenance source={result.source} /></>}
          <p>Window observations do not prove action/result correspondence or acceptance.</p></>
          : <><h3>Selected project context</h3><p>{context.selection?.workRef} · {context.selection?.rootJobId}</p>
            <Provenance source={mission.source} /><p>This window supplies no provider conversation, session binding or model selection.</p>
            <p>A Meta-CEO recommendation has not been supplied by its owner.</p></>}
      </aside>}
    </div>
  </section>;
}

/** Read-only owner projection. Exact managed sessions use the separate canonical
 * command binding; this component cannot promote a window to that capability. */
export function ConversationWindow(props: ConversationWindowProps) {
  const { context, conversation, mission, result } = props.projection;
  return <ConversationBody key={JSON.stringify([context.authGeneration, context.selection, context.sessionRef,
    context.bindingGeneration, context.revisions.conversation, context.revisions.mission, context.revisions.result,
    conversation.source.state, mission.source.state, result.source.state])} {...props} />;
}
