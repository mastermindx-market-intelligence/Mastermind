import { useEffect, useId, useRef, useState } from "react";
import type { MissionSelection } from "../mission";
import type { OfficeProjection } from "../meta-ceo/projection";
import "./inbox.css";

export interface InboxProps {
  projection: OfficeProjection;
  /** Read navigation, owned by the existing shell; never starts or retargets work. */
  onNavigateMission?: (selection: MissionSelection, mode: "current" | "history") => void;
}

function InboxBody({ projection, onNavigateMission }: InboxProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const evidenceButton = useRef<HTMLButtonElement>(null);
  const evidencePanel = useRef<HTMLElement>(null);
  const evidenceId = useId();
  const read = projection.mission;
  const source = read.source;
  const retained = source.state === "CURRENT" || source.state === "STALE";
  const mission = retained ? read.value : null;
  const current = source.state === "CURRENT" && !!mission;
  const turn = mission?.principal.owed_turn;
  // The owner uses executive_steward.Freshness's lower-case receipt values.
  // A current Mission alone cannot promote an old or missing attention receipt.
  const referenced = !!turn?.source_refs.length && turn.source_refs.every(ref =>
    !!ref.owner && !!ref.ref && !!ref.observed_at && ref.freshness === "current");
  const knownSeat = turn?.seat && ["chairman", "ceo", "coo", "worker"].includes(turn.seat);
  const owed = current && referenced && knownSeat ? turn : null;
  const needsChairman = owed?.seat === "chairman";
  const teamTurn = owed && !needsChairman ? owed : null;
  const history = source.state === "STALE" && mission && turn?.source_refs.length && knownSeat ? turn : null;
  const visibleTurn = owed || history;
  const selection = projection.context.selection;
  const exactSelection = mission && selection && mission.program.work_ref === selection.workRef &&
    mission.mission.root_job_id === selection.rootJobId && !mission.mission.root_job_ambiguous &&
    mission.mission.runtime_root_state === "RESOLVED" ? selection : null;
  const unknownEffect = current && projection.receipts.effect === "EFFECT_UNKNOWN";
  const title = mission?.program.title || mission?.program.work_ref;
  const showEvidence = evidenceOpen && !!visibleTurn;
  useEffect(() => { if (showEvidence) evidencePanel.current?.focus(); }, [showEvidence]);
  const closeEvidence = () => { setEvidenceOpen(false); evidenceButton.current?.focus(); };

  return <section className="atelier-inbox" aria-label="Inbox">
    <header className="inbox-heading">
      <p className="inbox-eyebrow">Your attention, well spent</p>
      <h1>A little attention.<br />A meaningful difference.</h1>
      <p>Owner-defined requests and exceptions, with their context intact.</p>
    </header>
    <div className="inbox-source-state"><span className="inbox-state" data-state={source.state}>{source.state}</span>
      <p>Supplied Mission scope · {source.coverage}</p></div>
    {unknownEffect && <div className="inbox-exception" role="alert"><strong>EFFECT_UNKNOWN</strong>
      <p>Reconcile the original operation. Resend, failover and target change remain held.</p></div>}
    <div className="inbox-columns">
      <div className="inbox-attention-list">
        <section aria-label="Needs you" className="inbox-attention">
          <h2>Needs you</h2>
          {needsChairman ? <article className="inbox-selected">
            <p className="inbox-eyebrow">Chairman request · {title}</p>
            <h3>{owed.reason || "The owner has requested your attention."}</h3>
            <p className="inbox-muted">Selected Mission · {exactSelection?.workRef || "Association unavailable"}</p>
          </article> : <p className="inbox-empty">No Chairman request is qualified in the supplied scope.</p>}
        </section>
        {teamTurn && <section aria-label="With the team" className="inbox-team">
          <p className="inbox-eyebrow">With the team · {teamTurn.seat!.toUpperCase()}</p>
          <h2>{title}</h2><p>{teamTurn.reason || "The next turn remains with its owner."}</p>
          <p className="inbox-muted">This request is assigned to its team owner.</p>
        </section>}
        <div className="inbox-coverage"><p>Company-wide attention coverage is not established.</p>
          <p>An unavailable source is never an all-clear.</p></div>
      </div>
      <section className="inbox-detail" aria-label="Owner request context">
        {visibleTurn ? <>
          <div className="inbox-detail-heading"><p className="inbox-eyebrow">{history ? "Retained context" : needsChairman ? "Why this needs you" : "Next accountable owner"}</p>
            <h2>{title}</h2>
            {history && <p className="inbox-history">Retained owner request; current attention is not established.</p>}
            <p>{visibleTurn.reason || "No reason was supplied by the owner."}</p>
          </div>
          <div className="inbox-recommendation"><p className="inbox-eyebrow">Recommendation</p>
            <p>A decision recommendation has not been supplied by its owner.</p>
            <p className="inbox-muted">A next-action note does not establish decision options or approval authority.</p>
          </div>
          <div className="inbox-evidence-row"><div><p>{visibleTurn.source_refs.length} linked {visibleTurn.source_refs.length === 1 ? "reference" : "references"}</p>
            <p className="inbox-muted">Exact owner evidence</p></div>
            <button type="button" ref={evidenceButton} aria-expanded={showEvidence} aria-controls={evidenceId}
              onClick={() => setEvidenceOpen(value => !value)}>View evidence</button></div>
          <p className="inbox-muted">Decision preview is unavailable until an owner supplies the decision contract.</p>
          {exactSelection && onNavigateMission && <button className="inbox-open-project" type="button"
            onClick={() => onNavigateMission(exactSelection, history ? "history" : "current")}>
            {history ? "Inspect retained project history" : "Open project"}</button>}
        </> : <><p className="inbox-eyebrow">Owner context</p><h2>Attention is not established.</h2>
          <p>A qualified request needs an exact Mission, an accountable recipient and current owner references.</p>
          <p className="inbox-muted">{read.reason || "No qualified owner request was supplied."}</p></>}
      </section>
    </div>
    {showEvidence && <section ref={evidencePanel} id={evidenceId} tabIndex={-1} className="inbox-evidence" aria-label="Attention evidence"
      onKeyDown={event => { if (event.key === "Escape") closeEvidence(); }}>
      <h2>Attention evidence</h2>
      <dl><dt>Mission owner</dt><dd>{source.owner}</dd><dt>Reference</dt><dd>{source.ref || "Not supplied"}</dd>
        <dt>Revision</dt><dd>{source.revision || "Not supplied"}</dd>
        <dt>{source.observed_at_kind === "LOCAL_ACQUISITION" ? "Locally acquired" : "Observed"}</dt><dd>{source.observed_at || "Not supplied"}</dd>
        <dt>Coverage</dt><dd>{source.coverage}</dd></dl>
      <ul>{visibleTurn!.source_refs.map((ref, index) => <li key={index}><p>{ref.owner}</p><p>{ref.ref}</p>
        <p>Observed {ref.observed_at} · freshness {ref.freshness}</p></li>)}</ul>
      <button type="button" onClick={closeEvidence}>Close evidence</button>
    </section>}
    {mission && <details className="inbox-receipt-details"><summary>{history ? "Retained receipts" : "Delivery, review and acceptance receipts"}</summary>
      <section className="inbox-receipts" aria-label="Independent receipts">
        {Object.entries(projection.receipts).map(([name, value]) => <div key={name}><p>{name}</p><strong>{value ?? "NOT_PROJECTED"}</strong></div>)}
      </section><p>Delivery, pickup, start, effect, return, review and acceptance remain separate.</p>
    </details>}
    <footer className="inbox-footer"><p className="inbox-eyebrow">Accountable ownership</p>
      <p>Routine work remains with its current owners.</p></footer>
  </section>;
}

/** Pure presentation of the existing product projection; no queue, read or action port. */
export function Inbox(props: InboxProps) {
  // A new identity/revision unmounts inspection state before any old protected panel renders.
  const { context, mission } = props.projection;
  return <InboxBody key={JSON.stringify([context.authGeneration, context.selection, context.sessionRef,
    context.bindingGeneration, context.revisions.mission, mission.source.state])} {...props} />;
}
