import { useRef, useState } from "react";
import { createDirectionPreview, previewIsCurrent, type DirectionPreview } from "./preview";
import { sameTarget, type OfficeProjection, type ProjectionContext, type SourceClaim } from "./projection";
import "./office.css";

/** Draft storage belongs to the existing shell. Inspection never rewrites or sends it. */
export interface OfficeDraft { text: string; context: ProjectionContext }
export interface MetaCeoOfficeProps {
  projection: OfficeProjection;
  draft: OfficeDraft;
  onDraftChange: (text: string) => void;
}

function SourceBadge({ source }: { source: SourceClaim }) {
  return <span className="office-state" data-state={source.state}>{source.state}</span>;
}

export function MetaCeoOffice({ projection, draft, onDraftChange }: MetaCeoOfficeProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [preview, setPreview] = useState<DirectionPreview | null>(null);
  const previewButton = useRef<HTMLButtonElement>(null);
  const sourcesButton = useRef<HTMLButtonElement>(null);
  const mission = projection.mission.value;
  const current = projection.mission.source.state === "CURRENT";
  const needsChairman = current && mission?.principal.owed_turn?.seat === "chairman" &&
    mission.principal.owed_turn.source_refs.length > 0 &&
    mission.principal.owed_turn.source_refs.every(ref =>
      !!ref.owner && !!ref.ref && !!ref.observed_at && ref.freshness === "current");
  const title = mission?.program.title ?? mission?.program.work_ref;
  const unknownEffect = projection.receipts.effect === "EFFECT_UNKNOWN";
  const draftAssociated = draft.context.authGeneration === projection.context.authGeneration && sameTarget(draft.context, projection.context);
  const visiblePreview = preview && previewIsCurrent(preview, projection.context) ? preview : null;
  const sources = [
    ["Mission", projection.mission], ["Projects", projection.programs],
    ["Return", projection.result], ["Conversation", projection.conversation],
  ] as const;
  const closePreview = () => { setPreview(null); previewButton.current?.focus(); };

  return <section className="meta-ceo-office" aria-label="Meta-CEO office">
    <header className="office-heading">
      <div><p className="office-eyebrow">One company. One office.</p>
        <h1>Keep the whole company <br />moving with intention.</h1>
        <p>A clear view of direction, movement and the next accountable action.</p></div>
      <div className="office-heading-aside"><div className="office-art" aria-hidden="true" />
        <span className="office-state" data-state="UNKNOWN">Read + preview only</span></div>
    </header>

    <section className="office-direction" aria-label="Current direction">
      <div><p className="office-eyebrow">Current direction</p><span className="office-muted">Source unavailable</span></div>
      <p>The adopted direction has not been supplied by its owner.</p>
    </section>

    {unknownEffect && <div className="office-effect-alert" role="alert">
      <strong>EFFECT_UNKNOWN</strong><p>Reconcile the original operation. Resend, failover and target change remain held.</p>
    </div>}

    <div className="office-top-grid">
      <section className="office-panel office-answer" aria-label="Meta-CEO answer">
        <div className="office-section-label"><p className="office-eyebrow">The next accountable move</p><SourceBadge source={projection.mission.source} /></div>
        <h2>{mission ? `${title}: ${mission.execution.state ?? "execution state unknown"}.` : "The current operating answer is not yet available."}</h2>
        <p>{mission?.program.next_action ?? "A qualified owner read is needed before an accountable next action can be stated."}</p>
        <p className="office-muted">{current ? "Source-backed summary of the selected project." : "Currentness is not established. Retained facts keep their source qualification."}</p>
        <section className="office-movement" aria-labelledby="office-moving-title">
        <div className="office-section-label"><h2 id="office-moving-title">Moving with Meta-CEO</h2><span className="office-muted">Supplied mission view</span></div>
        <p>Work details are unavailable. Mission coverage and accountable owners are reported below.</p>
        {mission ? <>
          <p className="office-muted">Coverage · {mission.children.coverage} · total {mission.children.total_count ?? "not established"}</p>
          <ul className="office-lanes">{mission.children.items.map(child => <li key={child.job_id}>
            <div><strong>{child.job_id}</strong><p>{child.orchestration_role ?? "Role unknown"} · Owner {child.worker_id ?? "not supplied"}</p></div>
            <span>{child.status ?? "UNKNOWN"}</span>
          </li>)}</ul>
          {mission.children.items.length === 0 && <p>No mission lanes were supplied. This is not a company-wide zero.</p>}
        </> : <p className="office-empty">Mission lanes are unavailable.</p>}
        <p className="office-muted">Company total is not established.</p>
        </section>
      </section>
      <section className={`office-panel office-attention${needsChairman ? " has-attention" : ""}`} aria-labelledby="office-attention-title">
        <p className="office-eyebrow">Needs you</p>
        <h2 id="office-attention-title">{needsChairman ? "The owner has requested Chairman attention." : "Chairman attention is not established."}</h2>
        <p>{needsChairman ? mission!.principal.owed_turn!.reason : "Missing attention data does not mean there are no decisions. Routine work remains with its accountable owner."}</p>
        {needsChairman && <p className="office-ref">{mission!.principal.owed_turn!.source_refs.map(ref => `${ref.owner} · ${ref.ref} · ${ref.observed_at}`).join("; ")}</p>}
      </section>
    </div>

    <details className="office-context">
      <summary>Returns, critical path and journal</summary>
      <div className="office-main-grid">
      <section className="office-panel" aria-labelledby="office-returns-title">
        <div className="office-section-label"><h2 id="office-returns-title">Returns to review</h2><SourceBadge source={projection.result.source} /></div>
        <p>A return is not acceptance.</p>
        {projection.result.value?.result ? <>
          <h3>{projection.result.value.selection.job_id}</h3>
          <p>{projection.result.value.result.content?.summary ?? "Content is withheld or outside the bounded response."}</p>
          <p className="office-ref">{projection.result.value.selection.attempt_id} · {projection.result.value.selection.result_envelope_digest}</p>
          <p>Acceptance · {projection.result.value.result.acceptance}</p>
        </> : <p className="office-empty">No exactly associated return has been qualified for this view.</p>}
      </section>
      <section className="office-panel" aria-labelledby="office-path-title">
        <h2 id="office-path-title">Critical path</h2>
        <p>The critical path is unavailable. The owner’s next action remains visible.</p>
        <dl className="office-next"><dt>Next accountable owner</dt><dd>{mission?.principal.accountable_seat ?? "Not supplied"}</dd>
          <dt>Next action</dt><dd>{mission?.program.next_action ?? "Not supplied"}</dd>
          <dt>Return condition</dt><dd>Not supplied by the current owner read</dd></dl>
      </section>
      <section className="office-panel" aria-labelledby="office-journal-title">
        <h2 id="office-journal-title">What changed — and why</h2>
        <p>The durable journal is unavailable. A current snapshot does not establish a change history.</p>
        <p className="office-ref">{projection.context.selection?.workRef ?? "Project not selected"} · {projection.context.selection?.rootJobId ?? "Root not selected"}</p>
        <p className="office-muted">Agent OS retains decisions, discoveries and handoffs.</p>
      </section>
      </div>
    </details>

    <details className="office-context">
      <summary>Delivery, effect and acceptance receipts</summary>
      <section className="office-receipts" aria-label="Independent receipts">
      {Object.entries(projection.receipts).map(([name, value]) => <div key={name}><p className="office-eyebrow">{name}</p><strong>{value ?? "NOT_PROJECTED"}</strong></div>)}
      </section>
    </details>
    <section className="office-sources" aria-label="Source qualification">
      {sources.map(([name, read]) => <div key={name}><span>{name}</span><SourceBadge source={read.source} /><span className="office-muted">{read.source.coverage}</span></div>)}
      <button ref={sourcesButton} type="button" aria-expanded={sourcesOpen} onClick={() => setSourcesOpen(!sourcesOpen)}>Review sources</button>
    </section>
    {sourcesOpen && <aside className="office-panel office-evidence" aria-label="Source evidence" onKeyDown={event => { if (event.key === "Escape") { setSourcesOpen(false); sourcesButton.current?.focus(); } }}>
      <h2>Exact source provenance</h2>
      {sources.map(([name, read]) => <div key={name}><h3>{name} · {read.source.owner}</h3>
        <p className="office-ref">{read.source.ref_kind === "CONTROL_ROOM_DOCUMENT_DIGEST" ? "Control Room document digest · " : ""}{read.source.ref ?? "Ref unavailable"} · revision {read.source.revision ?? "unknown"}</p>
        <p>{read.source.observed_at_kind === "LOCAL_ACQUISITION" ? "Locally acquired " : "Observed "}{read.source.observed_at ?? "time unknown"} · {read.reason ?? "Owner read supplied"}</p></div>)}
      {mission && <details><summary>Owner evidence and missingness</summary><pre>{JSON.stringify({
        program: mission.program.evidence, principal: mission.principal.evidence,
        execution: mission.execution.evidence, transport: mission.transport.evidence,
        review: mission.review.evidence, acceptance: mission.acceptance.evidence,
        missingness: mission.missingness, degraded: mission.degraded,
      }, null, 2)}</pre></details>}
      <button type="button" onClick={() => { setSourcesOpen(false); sourcesButton.current?.focus(); }}>Close sources</button>
    </aside>}

    <section className="office-composer" aria-label="Direction intake">
      <div><label className="office-eyebrow" htmlFor="office-direction">Direction to Meta-CEO</label>
        <textarea id="office-direction" rows={2} value={draftAssociated ? draft.text : ""}
          disabled={!draftAssociated} onChange={event => onDraftChange(event.target.value)}
          placeholder="Keep the highest-value safe next step moving." />
        <p className="office-muted">{draftAssociated ? "Preview only · no message, Job, session, acceptance or deployment." : "A draft is retained for another identity or session. Return to that exact context to continue it."}</p>
      </div>
      <button ref={previewButton} className="office-primary" type="button" disabled={!draftAssociated || !draft.text.trim()}
        onClick={() => setPreview(createDirectionPreview(projection, draft.text))}>Review direction preview</button>
    </section>
    {visiblePreview && <section className="office-panel office-preview" aria-label="Direction preview" onKeyDown={event => { if (event.key === "Escape") closePreview(); }}>
      <div className="office-section-label"><h2>Frozen direction preview</h2><span className="office-state">EFFECT_NONE</span></div>
      <p>{visiblePreview.draft}</p>
      <p className="office-ref">{visiblePreview.context.selection?.workRef ?? "Project unavailable"} · {visiblePreview.context.selection?.rootJobId ?? "Root unavailable"} · {visiblePreview.context.sessionRef ?? "Session unavailable"}</p>
      <p>Binding generation · {String(visiblePreview.context.bindingGeneration ?? "unknown")}</p>
      <p>Content permission · NOT_PROJECTED. Command permission · NOT_PROJECTED.</p>
      <p>Inspecting this preview supplies no authorization. Submission requires the canonical command owner.</p>
      <button type="button" onClick={closePreview}>Close preview</button>
    </section>}
  </section>;
}
