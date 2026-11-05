/**
 * Companion panel for one issued project-source draft proof.
 *
 * Renders the genuine original unsent draft text next to the proof's exact
 * excerpt and its closed source label, with exactly one explicit
 * add-to-draft action. The panel is a pure presentation leaf over the narrow
 * `ProjectSourceDraftPort` and never: sends, creates drafts, retargets,
 * stores, reads, refetches or polls; reads the excerpt back from the DOM
 * (append always uses the private proof's draft source); steals focus
 * passively or on status change (the keyed body below remounts instead);
 * or lets an IME composition Enter reach button activation.
 *
 * Currentness is re-proven on every render and again immediately before the
 * append: the proof must be privately issued, the port methods must be the
 * bound identities, the witness work/binding must still match, and the
 * revision must still be the original pre-append revision. After the owner
 * accepted our append, only the matching last insertion may be undone — the
 * excerpt is never appended twice, and any other text or revision change
 * hides the private excerpt entirely. When the destination is unavailable
 * there is no invented recipient, draft or excerpt.
 *
 * Only the existing Knowledge Library stylesheet and its classes are used;
 * this component introduces no new CSS and no material system.
 */

import { useState } from 'react';
import './knowledge-library.css';
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
    undo: 'Remove added excerpt',
    boundary: 'The excerpt is appended to this unsent draft only. Nothing is sent, stored or re-read.',
  },
  'zh-CN': {
    eyebrow: '来源摘录',
    draftLabel: '原始未发送草稿',
    emptyDraft: '草稿为空。',
    sourceLabel: '来源',
    add: '将摘录添加到草稿',
    added: '摘录已添加到草稿，尚未发送。',
    undo: '移除已添加摘录',
    boundary: '摘录仅追加到当前未发送草稿。不发送、不存储、不重新读取。',
  },
};

export interface ProjectSourceDraftCompanionProps {
  /** A proof issued by `completeProjectSourceDraftRead`, or null. */
  proof: ProjectSourceDraftProof | null;
  /** The genuine destination port adapted by the App; absent means unavailable. */
  port?: ProjectSourceDraftPort;
  locale?: KnowledgeLibraryLocale;
}

function CompanionBody({ proof, port, locale = 'en' }: ProjectSourceDraftCompanionProps) {
  const copy = COPY[locale];
  const [added, setAdded] = useState<{ identity: string; revision: number } | null>(null);
  if (!proof || !port) return null;
  const state = checkProjectSourceDraftProof(proof, port);
  if (state === 'STALE') return null;
  const identity = proof.draftSource.identity;
  const showAdded = state === 'UNDOABLE' || (added !== null && added.identity === identity);
  const addExcerpt = () => {
    if (checkProjectSourceDraftProof(proof, port) !== 'APPENDABLE') return;
    const expectedRevision = port.revision;
    if (port.append(proof.draftSource, expectedRevision)) {
      setAdded({ identity, revision: expectedRevision });
    }
  };
  const undoExcerpt = () => {
    if (checkProjectSourceDraftProof(proof, port) !== 'UNDOABLE') return;
    port.undo(identity, port.revision);
  };
  return (
    <aside
      className="knowledge-library-aside-panel"
      aria-label={copy.eyebrow}
      onKeyDown={event => {
        if (event.key === 'Enter' && event.nativeEvent.isComposing) {
          event.preventDefault();
          event.stopPropagation();
        }
      }}
    >
      <p className="knowledge-library-note">{copy.eyebrow}</p>
      <blockquote className="knowledge-library-plaintext">{proof.draftSource.excerpt}</blockquote>
      <details className="knowledge-library-details"><summary>{copy.sourceLabel}</summary><p>{proof.draftSource.label}</p></details>
      <p className="knowledge-library-note">
        {copy.draftLabel}: <span className="knowledge-library-plaintext">{port.text || copy.emptyDraft}</span>
      </p>
      {showAdded && <p className="knowledge-library-note" role="status">{copy.added}</p>}
      {state === 'APPENDABLE' && (
        <button type="button" className="knowledge-library-button" onClick={addExcerpt}>
          {copy.add}
        </button>
      )}
      {state === 'UNDOABLE' && (
        <button type="button" className="knowledge-library-button" onClick={undoExcerpt}>
          {copy.undo}
        </button>
      )}
      <p className="knowledge-library-note">{copy.boundary}</p>
    </aside>
  );
}

export function ProjectSourceDraftCompanion(props: ProjectSourceDraftCompanionProps) {
  const { proof, port } = props;
  // The keyed body remounts whenever the proof, the witnessed work/binding or
  // the observed revision changes, so no stale DOM text survives a destination
  // change and no status change ever steals focus.
  const witness = projectSourceDraftWitnessOf(port);
  return (
    <CompanionBody
      key={JSON.stringify([
        proof?.draftSource.identity ?? null,
        witness?.workRef ?? null,
        witness?.binding ?? null,
        witness?.revision ?? null,
      ])}
      {...props}
    />
  );
}
