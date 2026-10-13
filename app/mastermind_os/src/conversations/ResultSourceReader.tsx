import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MissionResultRead } from "../host";
import { observedMissionAssociation } from "../workspace-contract";
import { decodeResultEnvelope, normalizeResultSelection, type ResultSelection } from "../result";
import { projectOffice, type OfficeProjection, type ProjectedRead } from "../meta-ceo/projection";
import type { DraftInsertion, DraftSource } from "./drafts";

export interface ResultSourceReaderProps {
  projection: OfficeProjection;
  selection: ResultSelection;
  readResult: MissionResultRead;
  draftRevision: number;
  draftInsertion: DraftInsertion | null;
  appendAvailable: boolean;
  onAppend: (source: DraftSource, expectedRevision: number) => boolean;
  onUndo: (identity: string, expectedRevision: number) => boolean;
  onEditDraft: () => void;
  onClose: () => void;
}
type SourceRead = ProjectedRead<NonNullable<OfficeProjection["result"]["value"]>>;
type ReadState = { kind: "loading" } | { kind: "unavailable" } | { kind: "read"; source: SourceRead };

/** Existing fixed Result read only. The parent keys this view by its exact
 * auth/selection/paired-observation boundary. No generic source URL or cache. */
export function ResultSourceReader({ projection, selection, readResult, draftRevision,
  draftInsertion, appendAvailable, onAppend, onUndo, onEditDraft, onClose }: ResultSourceReaderProps) {
  const [read, setRead] = useState<ReadState>({ kind: "loading" });
  const [notice, setNotice] = useState("");
  const originalDraftRevision = useRef(draftRevision);
  const busy = useRef(false), abort = useRef<AbortController | null>(null);
  const region = useRef<HTMLElement>(null);
  const actionStatus = useRef<HTMLParagraphElement>(null);
  useLayoutEffect(() => { if (notice) actionStatus.current?.focus(); }, [notice]);
  const acquire = async () => {
    if (busy.current) return;
    busy.current = true;
    const controller = new AbortController(); abort.current = controller;
    setRead({ kind: "loading" }); setNotice("");
    try {
      const exact = normalizeResultSelection(selection);
      const context = structuredClone(projection.context);
      const association = projection.mission.source.state === "CURRENT" &&
        ["CURRENT", "STALE"].includes(projection.conversation.source.state) &&
        observedMissionAssociation(projection.conversation.value, projection.mission.value, context.selection);
      if (!exact || !association || exact.jobId !== association.job_id || exact.attemptId !== association.attempt_id ||
          exact.workRef !== context.selection?.workRef || exact.rootJobId !== context.selection?.rootJobId)
        throw new Error("RESULT_SELECTION_UNQUALIFIED");
      const raw = await readResult({ ...exact, signal: controller.signal });
      if (controller.signal.aborted || abort.current !== controller) return;
      const value = decodeResultEnvelope(raw, exact);
      if (!value) throw new Error("RESULT_RESPONSE_INVALID");
      context.revisions.result = exact.resultEnvelopeDigest;
      const qualified = projectOffice({
        mission: { context, source: projection.mission.source, value: projection.mission.value },
        conversation: { context, source: projection.conversation.source, value: projection.conversation.value },
        programs: null,
        result: { context, value, source: {
          owner: "EXECUTIVE_OS", ref: JSON.stringify(exact), revision: exact.resultEnvelopeDigest,
          observed_at: new Date().toISOString(), observed_at_kind: "LOCAL_ACQUISITION",
          state: "CURRENT", coverage: "BOUNDED_RESULT",
        } },
      }, context).result;
      setRead({ kind: "read", source: qualified });
    } catch {
      if (!controller.signal.aborted && abort.current === controller) setRead({ kind: "unavailable" });
    } finally {
      if (abort.current === controller) busy.current = false;
    }
  };
  useEffect(() => {
    region.current?.focus();
    void acquire();
    return () => { abort.current?.abort(); abort.current = null; busy.current = false; };
  }, []);
  const qualified = read.kind === "read" ? read.source : null;
  const value = qualified && ["CURRENT", "STALE"].includes(qualified.source.state) ? qualified.value : null;
  const result = value?.result;
  const summary = result?.availability === "AVAILABLE" ? result.content?.summary : null;
  const sourceLabel = qualified ? `Executive ${result?.role ?? "bounded"} result · ${selection.workRef} · ${selection.jobId} · Revision ${selection.resultEnvelopeDigest} · ${qualified.source.state} observation · Freshness unverified · Acceptance not projected` : "";
  const source: DraftSource | null = summary && result && qualified ? {
    identity: JSON.stringify([selection, result.role_result_digest, summary, sourceLabel, qualified.source.state, qualified.source.revision]),
    excerpt: summary,
    label: sourceLabel,
  } : null;
  const added = source && draftInsertion?.source.identity === source.identity ? draftInsertion : null;
  const unchanged = draftRevision === originalDraftRevision.current;
  const canUndo = !!added && draftRevision === added.revision;
  return <section ref={region} tabIndex={-1} className="conversation-companion conversation-result-reader"
    role="region" aria-label="Result source reader" onKeyDown={event => {
      if (event.key === "Escape" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) {
        event.stopPropagation(); onClose();
      }
    }}>
    <header><h2>Result source</h2><button type="button" onClick={onClose}>Back to evidence</button></header>
    <p>{selection.workRef} · {selection.jobId}</p>
    <p>A bounded Executive result. Review and acceptance remain separate.</p>
    {read.kind === "loading" ? <p role="status">Reading the exact result…</p> : <>
      {!summary ? <p role="status">Result content is unavailable. No excerpt can be added.</p> : <>
        <p>{qualified!.source.state} observation · Freshness unverified · Acceptance not projected</p>
        <h3>Exact summary excerpt</h3><blockquote className="conversation-source-excerpt">{summary}</blockquote>
        <details><summary>Source label for the draft</summary><p>{source!.label}</p></details>
        <button type="button" disabled={!appendAvailable || !!added || !unchanged} onKeyDown={event => {
          if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)) event.preventDefault();
        }} onClick={() => {
          if (!source || !appendAvailable || added || !unchanged) return;
          setNotice(onAppend(source, originalDraftRevision.current)
            ? "Added to draft · Not sent"
            : "The original draft changed or is unavailable. Return to review it before adding.");
        }}>Add result summary to draft</button>
        {!appendAvailable && <p>An eligible scoped draft is unavailable. Reading does not create one.</p>}
        {canUndo ? <button type="button" onClick={() => {
          setNotice(onUndo(added!.source.identity, draftRevision)
            ? "Source insertion removed. Your original draft is preserved."
            : "The draft changed. Edit the draft to preserve your newer text.");
        }}>Undo source insertion</button> : (added || !unchanged) && <>
          <p>The draft has changed. Automatic removal is unavailable.</p><button type="button" onClick={onEditDraft}>Edit draft</button>
        </>}
        {!added && !unchanged && <p>Return to evidence and reopen this result to review the current draft before adding.</p>}
      </>}
      {qualified?.reason && <details><summary>Read details</summary><p>{qualified.reason}</p></details>}
    </>}
    <details><summary>Exact source details</summary>
      <dl><dt>Work reference</dt><dd>{selection.workRef}</dd><dt>Root Job</dt><dd>{selection.rootJobId}</dd>
        <dt>Job</dt><dd>{selection.jobId}</dd><dt>Attempt</dt><dd>{selection.attemptId}</dd>
        <dt>Result envelope digest</dt><dd>{selection.resultEnvelopeDigest}</dd>
        {summary && <><dt>Owner</dt><dd>{qualified!.source.owner}</dd><dt>Role result digest</dt><dd>{result!.role_result_digest}</dd>
          <dt>Locally acquired</dt><dd>{qualified!.source.observed_at}</dd><dt>Source time</dt><dd>Not supplied</dd>
          <dt>Coverage</dt><dd>Bounded result · {result!.content_complete ? "Complete returned content" : "Partial returned content"}</dd></>}
      </dl>
    </details>
    {(notice || added) && <p ref={actionStatus} tabIndex={-1} role="status">{notice || "Added to draft · Not sent"}</p>}
    <button type="button" disabled={read.kind === "loading"} onClick={() => { void acquire(); }}>Recheck exact result</button>
    <p>Closing stops this display read. It does not stop work or resolve an original operation.</p>
  </section>;
}
