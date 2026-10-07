import { useEffect, useId, useRef, useState } from "react";
import { allEvidence, type EvidenceRef } from "../mission";
import type { OfficeProjection, SourceState } from "../meta-ceo/projection";
import "./knowledge.css";

export interface SourceNavigation {
  owner: EvidenceRef["owner"]; ref: string; revision: string; mode: "current" | "history";
}
export interface KnowledgeProps {
  projection: OfficeProjection;
  /** Existing source-navigation owner only. This component never resolves a ref
   * into a guessed URL, reads another source, or mutates the original record. */
  onOpenSource?: (source: SourceNavigation) => void;
}

function referenceState(ref: EvidenceRef, parent: SourceState): SourceState {
  if (ref.freshness_state === "UNAVAILABLE") return "UNAVAILABLE";
  if (ref.freshness_state === "PARTIAL" || !ref.owner || !ref.ref || !ref.source_revision || !ref.observed_at) return "UNKNOWN";
  return parent === "STALE" || ref.freshness_state === "HISTORICAL" ? "STALE" : "CURRENT";
}

function KnowledgeBody({ projection, onOpenSource }: KnowledgeProps) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const searchId = useId(), search = useRef<HTMLInputElement>(null);
  const detail = useRef<HTMLElement>(null), trigger = useRef<HTMLButtonElement | null>(null);
  const source = projection.mission.source;
  const retained = source.state === "CURRENT" || source.state === "STALE";
  const mission = retained ? projection.mission.value : null;
  // v3 adds a Result index; these are the unchanged canonical v2 evidence fields.
  const refs = mission ? allEvidence({ ...mission, schema: "mastermind.mission_workspace.v2" }) : [];
  const selected = selectedId === null ? null : refs[selectedId] ?? null;
  const term = query.trim().toLocaleLowerCase();
  const visible = refs.map((row, index) => ({ ...row, index })).filter(({ facet, evidence: e }) =>
    !term || `${facet}\n${e.owner}\n${e.ref}\n${e.field}\n${e.source_revision ?? ""}`.toLocaleLowerCase().includes(term));
  const selectedState = selected ? referenceState(selected.evidence, source.state) : null;
  const canOpen = selected && onOpenSource && (selectedState === "CURRENT" || selectedState === "STALE");
  useEffect(() => { if (selectedId !== null) detail.current?.focus(); }, [selectedId]);
  const close = () => {
    setSelectedId(null);
    (trigger.current?.isConnected ? trigger.current : search.current)?.focus();
  };

  return <section className="atelier-knowledge" aria-label="Knowledge">
    <header className="knowledge-heading"><p className="knowledge-eyebrow">A library that grows with you</p>
      <h1>Keep what matters.<br />Build on what you know.</h1>
      <p>Useful work, with its sources and qualification intact.</p>
      <div className="knowledge-search"><label htmlFor={searchId}>Search supplied knowledge</label>
        <input ref={search} id={searchId} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Find an owner, reference or field" /></div>
    </header>
    <section className="knowledge-source" aria-label="Knowledge source"><span data-state={source.state}>{source.state}</span>
      <p>Selected Mission scope · {source.coverage}. Company-wide coverage is not established.</p></section>
    <div className="knowledge-collections">
      <section><p className="knowledge-eyebrow">01 · Decisions</p><h2>The choices shaping the company.</h2><p>Owner index unavailable</p></section>
      <section><p className="knowledge-eyebrow">02 · Discoveries</p><h2>Findings worth returning to.</h2><p>Owner index unavailable</p></section>
      <section><p className="knowledge-eyebrow">03 · Evidence</p><h2>Follow the supplied references.</h2><p>{mission ? `${refs.length} references supplied` : "Source unavailable"}</p></section>
    </div>
    <p className="knowledge-muted">Decision, discovery, handoff and contract indexes are unavailable. Evidence references do not supply their record content.</p>
    <div className="knowledge-layout">
      <section className="knowledge-list" aria-label="Supplied knowledge references">
        <div className="knowledge-section-title"><h2>Supplied references</h2><p>Owner order retained</p></div>
        {source.state === "STALE" && <p className="knowledge-history">Retained history. Currentness has not been established.</p>}
        {!mission ? <div className="knowledge-empty"><h3>A qualified source is not available.</h3>
          <p>{projection.mission.reason ?? "No source reference collection was supplied."}</p>
          <p>Missing or private knowledge is never reconstructed from conversation history.</p></div>
          : visible.length ? <ul>{visible.map(({ facet, evidence, index }) => <li key={`${facet}:${index}`}>
            <div><p className="knowledge-eyebrow">Evidence reference · {evidence.owner}</p>
              <h3>{facet} · {evidence.field}</h3><p className="knowledge-ref">{evidence.ref}</p></div>
            <div className="knowledge-row-action"><span data-state={referenceState(evidence, source.state)}>{referenceState(evidence, source.state)}</span>
              <button type="button" aria-label={`Inspect ${facet} · ${evidence.field}`} onClick={event => { trigger.current = event.currentTarget; setSelectedId(index); }}>Inspect</button></div>
          </li>)}</ul> : <p className="knowledge-empty">{term ? "No supplied references match this search." : "No references were supplied. This does not establish zero knowledge."}</p>}
      </section>
      <aside className="knowledge-companion">
        {selected ? <section ref={detail} tabIndex={-1} aria-label="Selected source reference" onKeyDown={event => { if (event.key === "Escape") close(); }}>
          <div className="knowledge-section-title"><p className="knowledge-eyebrow">Exact source reference</p><button type="button" onClick={close}>Close source context</button></div>
          <h2>{selected.facet} · {selected.evidence.field}</h2>
          <p data-state={selectedState ?? "UNKNOWN"}>{selectedState}</p>
          <dl><dt>Canonical owner</dt><dd>{selected.evidence.owner}</dd>
            <dt>Type</dt><dd>Evidence reference</dd><dt>Exact ref</dt><dd>{selected.evidence.ref}</dd>
            <dt>Revision</dt><dd>{selected.evidence.source_revision ?? "Not supplied"}</dd>
            <dt>Source time</dt><dd>{selected.evidence.source_time ?? "Not supplied"}</dd>
            <dt>Observed</dt><dd>{selected.evidence.observed_at ?? "Not supplied"}</dd>
            <dt>Referenced by selected Mission</dt><dd>{projection.context.selection?.workRef} · {projection.context.selection?.rootJobId}</dd>
            <dt>Coverage</dt><dd>Supplied Mission evidence references</dd>
            <dt>Derived from</dt><dd>{source.owner} · {source.ref} · {source.revision}</dd></dl>
          <p>Original record content has not been supplied. This derived reference view is not a canonical record or proof of a direct project relationship.</p>
          <button type="button" disabled={!canOpen} onClick={() => {
            if (canOpen) onOpenSource!({ owner: selected.evidence.owner, ref: selected.evidence.ref,
              revision: selected.evidence.source_revision!, mode: selectedState === "STALE" ? "history" : "current" });
          }}>Open original source</button>
          {!canOpen && <p className="knowledge-muted">A qualified source and its existing navigation owner are required to open the original.</p>}
        </section> : <section><p className="knowledge-eyebrow">Follow the source</p><h2>Useful knowledge.<br />Visible provenance.</h2>
          <p>Inspect a supplied reference to see its owner, revision, observed time and exact source context.</p>
          <p>Source clocks remain separate. A return remains separate from acceptance.</p></section>}
        <p className="knowledge-boundary">Knowledge is not model memory. Search and inspection change presentation only; durable changes return to the canonical owner.</p>
      </aside>
    </div>
  </section>;
}

export function Knowledge(props: KnowledgeProps) {
  const { context, mission } = props.projection;
  return <KnowledgeBody key={JSON.stringify([context.authGeneration, context.selection, context.sessionRef,
    context.bindingGeneration, context.revisions.mission, mission.source.state])} {...props} />;
}
