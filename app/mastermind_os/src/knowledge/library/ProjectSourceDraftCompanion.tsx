/**
 * Companion panel for one issued project-source draft proof.
 *
 * Renders the genuine original unsent draft text first, in a bounded,
 * keyboard-scrollable named region, then the proof's exact excerpt and its
 * closed source label, with exactly one explicit add-to-draft action. The
 * panel is a pure presentation leaf over the narrow `ProjectSourceDraftPort`
 * and never: sends, creates drafts, retargets, stores, reads, refetches or
 * polls; reads the excerpt back from the DOM (append always uses the private
 * proof's draft source); steals focus passively or on status change (the
 * keyed body below remounts instead; focus moves only from an explicit add
 * or undo gesture, resolved through the stable outer host); or lets an IME
 * composition Enter reach button activation.
 *
 * Currentness is re-proven on every render and again immediately before the
 * append: the proof must be privately issued, the port methods must be the
 * bound identities, the witness work/binding must still match, and the
 * revision must still be the original pre-append revision. After the owner
 * accepted our append, only the matching last insertion may be undone — the
 * excerpt is never appended twice, and any other text or revision change
 * hides the private excerpt entirely. When the destination is unavailable,
 * the witness is absent, or the proof is stale, nothing is rendered: there
 * is no invented recipient, draft, excerpt or navigation.
 *
 * When the destination's current last insertion is already exactly this
 * proof's source at the current revision — a reopened source whose append
 * the owner correctly refuses — the panel displays "Already in this draft.
 * Not sent." with no add action and no invented undo, plus, only when the
 * genuine port itself exposes an edit callback, one open-original-
 * conversation action that calls that existing callback alone.
 *
 * Explicit-gesture focus survives the keyed body remount through the stable
 * outer host: the intent holds only the proof's source identity, the
 * validated witness work/binding, the expected next revision and the target
 * — never private text — and is consumed exactly once on the next render. A
 * successful append may focus the existing Remove button once the owner
 * revision matches and the proof is undoable; a successful undo makes the
 * proof stale by design and may focus only the reader's existing Back
 * button, scoped through this host — never a global document search. A
 * refused gesture forces only a local presentation recheck and never
 * fabricates success or another action.
 *
 * Only the existing Knowledge Library stylesheet and its classes carry the
 * material; `project-source-draft-companion.css` adds layout, the bounded
 * region and the inherited focus outline, and no new palette, tokens or
 * surface.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import './knowledge-library.css';
import './project-source-draft-companion.css';
import type { KnowledgeLibraryLocale } from './knowledge-library-contract';
import {
  checkProjectSourceDraftProof,
  projectSourceDraftWitnessOf,
  type ProjectSourceDraftPort,
  type ProjectSourceDraftProof,
} from './project-source-draft';

interface CompanionCopy {
  readonly eyebrow: string;
  readonly draftLabel: string;
  readonly emptyDraft: string;
  readonly sourceLabel: string;
  readonly add: string;
  readonly added: string;
  readonly already: string;
  readonly open: string;
  readonly undo: string;
  readonly boundary: string;
}

const COPY: Record<KnowledgeLibraryLocale, CompanionCopy> = {
  en: {
    eyebrow: 'Source excerpt',
    draftLabel: 'Original unsent draft',
    emptyDraft: 'The draft is empty.',
    sourceLabel: 'Source',
    add: 'Add excerpt to draft',
    added: 'Excerpt added to the draft. Not sent.',
    already: 'Already in this draft. Not sent.',
    open: 'Open original conversation',
    undo: 'Remove added excerpt',
    boundary: 'Adds the excerpt and source label to this unsent draft. Nothing is sent.',
  },
  'zh-CN': {
    eyebrow: '来源摘录',
    draftLabel: '原始未发送草稿',
    emptyDraft: '草稿为空。',
    sourceLabel: '来源',
    add: '将摘录添加到草稿',
    added: '摘录已添加到草稿，尚未发送。',
    already: '已在此草稿中，尚未发送。',
    open: '打开原始对话',
    undo: '移除已添加摘录',
    boundary: '将摘录和来源标签添加到此未发送草稿，不会发送。',
  },
};

export interface ProjectSourceDraftCompanionProps {
  /** A proof issued by `completeProjectSourceDraftRead`, or null. */
  proof: ProjectSourceDraftProof | null;
  /** The genuine destination port adapted by the App; absent means unavailable. */
  port?: ProjectSourceDraftPort;
  locale?: KnowledgeLibraryLocale;
}

/** Explicit-gesture focus intent: provenance only, never private text. */
interface ProjectSourceDraftFocusIntent {
  readonly identity: string;
  readonly workRef: string;
  readonly binding: string;
  readonly revision: number;
  readonly target: 'remove' | 'back';
}

interface CompanionBodyProps extends ProjectSourceDraftCompanionProps {
  /** Stores one explicit-gesture focus intent on the stable outer host. */
  readonly onRequestFocus: (intent: ProjectSourceDraftFocusIntent) => void;
  /** Forces a local presentation recheck after a refused gesture. */
  readonly onGestureRecheck: () => void;
}

function CompanionBody({ proof, port, locale = 'en', onRequestFocus, onGestureRecheck }: CompanionBodyProps) {
  const copy = COPY[locale];
  const [added, setAdded] = useState<{ identity: string; revision: number } | null>(null);
  if (!proof || !port) return null;
  const state = checkProjectSourceDraftProof(proof, port);
  if (state !== 'APPENDABLE' && state !== 'UNDOABLE') return null;
  const identity = proof.draftSource.identity;
  const insertion = port.insertion;
  // Display-only: the reopened source the owner correctly refuses to append
  // twice. The proof classification itself is never rewritten.
  const alreadyInDraft =
    state === 'APPENDABLE' &&
    insertion !== null &&
    insertion.source.identity === identity &&
    insertion.revision === port.revision &&
    port.text === insertion.after;
  const showAdded = state === 'UNDOABLE' || (added !== null && added.identity === identity);
  const addExcerpt = () => {
    if (checkProjectSourceDraftProof(proof, port) !== 'APPENDABLE') {
      onGestureRecheck();
      return;
    }
    const witnessNow = projectSourceDraftWitnessOf(port);
    const expectedRevision = port.revision;
    if (!witnessNow || !port.append(proof.draftSource, expectedRevision)) {
      onGestureRecheck();
      return;
    }
    setAdded({ identity, revision: expectedRevision });
    onRequestFocus({
      identity,
      workRef: witnessNow.workRef,
      binding: witnessNow.binding,
      revision: expectedRevision + 1,
      target: 'remove',
    });
  };
  const undoExcerpt = () => {
    if (checkProjectSourceDraftProof(proof, port) !== 'UNDOABLE') {
      onGestureRecheck();
      return;
    }
    const witnessNow = projectSourceDraftWitnessOf(port);
    const expectedRevision = port.revision;
    if (!witnessNow || !port.undo(identity, expectedRevision)) {
      onGestureRecheck();
      return;
    }
    onRequestFocus({
      identity,
      workRef: witnessNow.workRef,
      binding: witnessNow.binding,
      revision: expectedRevision + 1,
      target: 'back',
    });
  };
  const openConversation = () => {
    const edit = port.edit;
    if (!edit) {
      onGestureRecheck();
      return;
    }
    if (checkProjectSourceDraftProof(proof, port) === 'STALE') {
      onGestureRecheck();
      return;
    }
    if (!projectSourceDraftWitnessOf(port)) {
      onGestureRecheck();
      return;
    }
    edit();
  };
  return (
    <aside
      className="knowledge-library-aside-panel project-source-draft-companion-panel"
      aria-label={copy.eyebrow}
      onKeyDown={event => {
        if (event.key === 'Enter' && event.nativeEvent.isComposing) {
          event.preventDefault();
          event.stopPropagation();
        }
      }}
    >
      <p className="knowledge-library-note">{copy.draftLabel}</p>
      <div
        className="knowledge-library-plaintext project-source-draft-companion-text"
        role="region"
        aria-label={copy.draftLabel}
        tabIndex={0}
      >
        {port.text || copy.emptyDraft}
      </div>
      <p className="knowledge-library-note">{copy.eyebrow}</p>
      <blockquote className="knowledge-library-plaintext">{proof.draftSource.excerpt}</blockquote>
      <details className="knowledge-library-details"><summary>{copy.sourceLabel}</summary><p className="knowledge-library-plaintext project-source-draft-companion-label">{proof.draftSource.label}</p></details>
      {showAdded && <p className="knowledge-library-note" role="status">{copy.added}</p>}
      {alreadyInDraft && <p className="knowledge-library-note" role="status">{copy.already}</p>}
      {state === 'APPENDABLE' && !alreadyInDraft && (
        <button type="button" className="knowledge-library-button" onClick={addExcerpt}>
          {copy.add}
        </button>
      )}
      {state === 'UNDOABLE' && (
        <button type="button" className="knowledge-library-button" data-project-source-draft-action="remove" onClick={undoExcerpt}>
          {copy.undo}
        </button>
      )}
      {alreadyInDraft && port.edit && (
        <button type="button" className="knowledge-library-button" onClick={openConversation}>
          {copy.open}
        </button>
      )}
      <p className="knowledge-library-note">{copy.boundary}</p>
    </aside>
  );
}

export function ProjectSourceDraftCompanion(props: ProjectSourceDraftCompanionProps) {
  const { proof, port } = props;
  const hostRef = useRef<HTMLDivElement | null>(null);
  const ownerToken = useMemo(() => ({}), [proof, port?.append, port?.undo, port?.readWitness]);
  const intentRef = useRef<(ProjectSourceDraftFocusIntent & { ownerToken: object }) | null>(null);
  const [recheck, setRecheck] = useState(0);
  // The keyed body remounts whenever the proof, the witnessed work/binding or
  // the observed revision changes, so no stale DOM text survives a destination
  // change and no status change ever steals focus.
  const witness = projectSourceDraftWitnessOf(port);

  useEffect(() => {
    const intent = intentRef.current;
    if (!intent) return;
    // Consume exactly once: this render either resolves the gesture or
    // discards it. A missing or changed source, proof, host, witness
    // work/binding or revision clears the intent without focus, and it is
    // never revived later.
    intentRef.current = null;
    const host = hostRef.current;
    if (!proof || !port || !host || intent.ownerToken !== ownerToken) return;
    if (proof.draftSource.identity !== intent.identity) return;
    const witnessNow = projectSourceDraftWitnessOf(port);
    if (!witnessNow) return;
    if (witnessNow.workRef !== intent.workRef || witnessNow.binding !== intent.binding) return;
    if (witnessNow.revision !== intent.revision) return;
    if (intent.target === 'remove') {
      if (checkProjectSourceDraftProof(proof, port) !== 'UNDOABLE') return;
      const remove = host.querySelector('[data-project-source-draft-action="remove"]');
      if (remove instanceof HTMLButtonElement) remove.focus();
      return;
    }
    // Undo advanced the revision on purpose: the proof is stale, the private
    // excerpt has withdrawn, and only the reader's own Back button — scoped
    // through this host — may receive focus.
    if (checkProjectSourceDraftProof(proof, port) !== 'STALE') return;
    const back = host.closest('.knowledge-library-reader')?.querySelector('.knowledge-library-document > button');
    if (back instanceof HTMLButtonElement) back.focus();
  }, [recheck, proof, port, ownerToken]);

  const body = proof && port && witness ? (
    <CompanionBody
      key={JSON.stringify([
        proof?.draftSource.identity ?? null,
        witness?.workRef ?? null,
        witness?.binding ?? null,
        witness?.revision ?? null,
      ])}
      proof={proof}
      port={port}
      locale={props.locale}
      onRequestFocus={intent => {
        intentRef.current = { ...intent, ownerToken };
      }}
      onGestureRecheck={() => setRecheck(count => count + 1)}
    />
  ) : null;

  return (
    <div ref={hostRef} className="project-source-draft-companion">
      {body}
    </div>
  );
}
