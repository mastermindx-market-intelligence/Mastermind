// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ProjectionContext } from '../../meta-ceo/projection';
import type { SavedConversationReference } from '../../discovery/saved-conversations';
import {
  appendDraftSource,
  emptyDrafts,
  readDraft,
  readDraftInsertion,
  readDraftRevision,
  undoDraftSource,
  writeDraft,
  type ConversationDrafts,
  type DraftSource,
} from '../../conversations/drafts';
import type { KnowledgeLibraryLocale, KnowledgeSourceResult } from './knowledge-library-contract';
import {
  captureProjectSourceDraftRead,
  checkProjectSourceDraftProof,
  completeProjectSourceDraftRead,
  type ProjectSourceDraftPort,
  type ProjectSourceDraftProof,
  type ProjectSourceDraftSource,
  type ProjectSourceDraftWitness,
} from './project-source-draft';
import { ProjectSourceDraftCompanion } from './ProjectSourceDraftCompanion';

afterEach(cleanup);

/* ------------------------------------------------------------------ */
/* Genuine helper kit (local copies; the module never re-exports it)    */
/* ------------------------------------------------------------------ */

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

interface DestinationOptions {
  append?: (source: DraftSource, expectedRevision: number) => boolean;
  undo?: (identity: string, expectedRevision: number) => boolean;
  readWitness?: () => ProjectSourceDraftWitness | null;
  /** The port's own genuine edit callback, when the App adapter exposes one. */
  edit?: () => void;
}

/** Clearly synthetic (not live auth) destination port whose append/undo/
 * write semantics are the REAL `conversations/drafts.ts` functions. Method
 * identities stay stable across snapshots, mirroring the App adapter. */
function createDestination(options: DestinationOptions = {}) {
  const context: ProjectionContext = {
    authGeneration: 7,
    selection: { workRef: 'WS:ALPHA', rootJobId: 'JOB-42' },
    sessionRef: 'session-alpha',
    bindingGeneration: 'binding-9',
    revisions: { mission: null, programs: null, result: null, conversation: null },
  };
  const cell = { drafts: emptyDrafts(7) };
  const binding = 'principal:root-workspace:session-alpha:binding-9:mission-association';
  const append = options.append ?? ((source: DraftSource, expectedRevision: number): boolean => {
    if (readDraftRevision(cell.drafts, context) !== expectedRevision) return false;
    cell.drafts = appendDraftSource(cell.drafts, context, expectedRevision, source);
    return readDraftRevision(cell.drafts, context) === expectedRevision + 1
      && readDraftInsertion(cell.drafts, context)?.source.identity === source.identity;
  });
  const undo = options.undo ?? ((identity: string, expectedRevision: number): boolean => {
    if (readDraftRevision(cell.drafts, context) !== expectedRevision) return false;
    cell.drafts = undoDraftSource(cell.drafts, context, expectedRevision, identity);
    return readDraftRevision(cell.drafts, context) === expectedRevision + 1;
  });
  const readWitness = options.readWitness ?? ((): ProjectSourceDraftWitness | null =>
    ({ workRef: 'WS:ALPHA', binding, revision: readDraftRevision(cell.drafts, context) }));
  return {
    context,
    binding,
    drafts: (): ConversationDrafts => cell.drafts,
    writeText: (text: string): void => { cell.drafts = writeDraft(cell.drafts, context, text); },
    get port(): ProjectSourceDraftPort {
      return {
        text: readDraft(cell.drafts, context),
        revision: readDraftRevision(cell.drafts, context),
        insertion: readDraftInsertion(cell.drafts, context),
        append, undo, readWitness,
        ...(options.edit ? { edit: options.edit } : {}),
      };
    },
  };
}

const COMMIT = '579ef67e8b387a1c40c6393e93eeaeafe98bec45';
const RECORD_REF = 'project-record.v1.bc983b58d00776459fc98402d26da229822756c30d7461f81e6ca785a37c4ec1';
const RECORD_PATH = 'agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-ALPHA.md';
const RECORD_REVISION = 'b11a2cd5e404875fae98fb6c12b76c4f899eb74b';
const REPOSITORY = 'mastermindx-market-intelligence/macro';

async function projectRecordSource(text = '决策记录：中文决定。\r\n记录正文  \n'): Promise<{
  source: ProjectSourceDraftSource; text: string; contentSha256: string;
}> {
  const contentSha256 = await sha256Hex(text);
  const result: KnowledgeSourceResult = Object.freeze({
    availability: 'AVAILABLE',
    source: Object.freeze({
      repository: REPOSITORY,
      commit: COMMIT,
      path: RECORD_PATH,
      revision: RECORD_REVISION,
      contentSha256,
      committedAt: '2026-02-01T06:30:00Z',
    }),
    document: Object.freeze({
      title: 'How should this project communicate with its owner?',
      mediaType: 'text/markdown' as const,
      contentUtf8: text,
      contentSha256,
    }),
    reasonCodes: Object.freeze([] as string[]),
  });
  return { source: { kind: 'PROJECT_RECORD', sourceRef: RECORD_REF, result }, text, contentSha256 };
}

async function savedReplySource(text = '答复一\r\n答复二 🚀  \n', workRef = 'WS:ALPHA'): Promise<{
  source: ProjectSourceDraftSource; text: string; readRef: string; requestedAt: string; rootJobId: string;
}> {
  const reference: SavedConversationReference = Object.freeze({
    read_ref: `session-reply-${await sha256Hex(`read-ref:${workRef}`)}`,
    operation_key: `session-continue-${await sha256Hex('operation-key')}`,
    request_ref: 'request-1',
    request_event_id: 12,
    request_revision: '1'.repeat(64),
    requested_at: '2026-02-01T09:15:00Z',
    work_ref: workRef,
    root_job_id: 'JOB-42',
    target_ref: `fabric_attempt:${await sha256Hex('target')}`,
    reference_only: true,
  });
  const result = Object.freeze({
    state: 'AVAILABLE' as const,
    reason: null,
    reference,
    text,
    sourceTextSha256: await sha256Hex(text),
  });
  return {
    source: { kind: 'SAVED_REPLY' as const, result },
    text,
    readRef: reference.read_ref,
    requestedAt: reference.requested_at,
    rootJobId: reference.root_job_id,
  };
}

async function issueProof(
  dest: ReturnType<typeof createDestination>,
  source: ProjectSourceDraftSource,
): Promise<ProjectSourceDraftProof | null> {
  const ticket = captureProjectSourceDraftRead(dest.port, 'WS:ALPHA', () => true);
  expect(ticket).toBeTruthy();
  return completeProjectSourceDraftRead(ticket as NonNullable<typeof ticket>, source, dest.port);
}

/* ------------------------------------------------------------------ */
/* Presentation                                                         */
/* ------------------------------------------------------------------ */

describe('ProjectSourceDraftCompanion presentation', () => {
  it('shows the current draft first, focuses Remove once the owner revision matches', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    expect(document.activeElement).toBe(document.body);
    expect(document.querySelector('[autofocus]')).toBeNull();
    const aside = rendered.container.querySelector('aside')!;
    // Draft section first, then the source excerpt section:
    expect(aside.children[0].textContent).toBe('Original unsent draft');
    expect(aside.children[1].getAttribute('role')).toBe('region');
    expect(aside.children[2].textContent).toBe('Source excerpt');
    expect(aside.querySelector('blockquote')).toBe(aside.children[3]);
    expect(aside.querySelector('blockquote')!.textContent).toBe(text);
    expect(aside.textContent).toContain('The draft is empty.');
    expect(aside.textContent).toContain('Adds the excerpt and source label to this unsent draft. Nothing is sent.');
    expect(rendered.container.querySelectorAll('button')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    expect(screen.getByText('Excerpt added to the draft. Not sent.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add excerpt to draft' })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Remove added excerpt' }));
    expect(readDraft(dest.drafts(), dest.context)).toBe(`“${text}”\nSource: ${proof!.draftSource.label}`);
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(1);
  });

  it('moves focus to the reader Back button when Undo withdraws the stale proof', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => (
      <div className="knowledge-library-reader">
        <div className="knowledge-library-document">
          <button type="button">Back</button>
          <ProjectSourceDraftCompanion proof={proof} port={dest.port} />
        </div>
      </div>
    );
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    fireEvent.click(screen.getByRole('button', { name: 'Remove added excerpt' }));
    rendered.rerender(view());
    // Undo made the proof stale by design; the private excerpt withdraws:
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.body.textContent).not.toContain(text);
    expect(readDraft(dest.drafts(), dest.context)).toBe('');
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(2);
    expect(document.activeElement).toBe(rendered.container.querySelector('.knowledge-library-document > button'));
    expect(rendered.container.querySelector('.knowledge-library-document > button')!.textContent).toBe('Back');
  });

  it('never searches outside the stable host for the Back button', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => (
      <div>
        <div className="knowledge-library-reader">
          <div className="knowledge-library-document">
            <button type="button">Decoy Back</button>
          </div>
        </div>
        <div className="knowledge-library-reader">
          <div className="knowledge-library-document">
            <button type="button">Own Back</button>
            <ProjectSourceDraftCompanion proof={proof} port={dest.port} />
          </div>
        </div>
      </div>
    );
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    fireEvent.click(screen.getByRole('button', { name: 'Remove added excerpt' }));
    rendered.rerender(view());
    expect(screen.queryByText('Source excerpt')).toBeNull();
    const readers = rendered.container.querySelectorAll('.knowledge-library-reader');
    const ownBack = readers[1].querySelector('.knowledge-library-document > button')!;
    expect(ownBack.textContent).toBe('Own Back');
    expect(document.activeElement).toBe(ownBack);
    expect(document.activeElement!.textContent).not.toBe('Decoy Back');
  });

  it('withdraws without focus when no reader host exists around the companion', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    fireEvent.click(screen.getByRole('button', { name: 'Remove added excerpt' }));
    rendered.rerender(view());
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.body.textContent).not.toContain(text);
    // No reader ancestor: no Back button is searched globally, none is focused.
    expect(document.activeElement).toBe(document.body);
    expect(document.body.textContent).not.toContain('Back');
  });

  it('shows Already for a reopened proof over the same insertion without add or invented undo', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const first = await issueProof(dest, source);
    const view = (p: ProjectSourceDraftProof | null) => <ProjectSourceDraftCompanion proof={p} port={dest.port} />;
    const rendered = render(view(first));
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view(first));
    const reopened = await issueProof(dest, source);
    rendered.rerender(view(reopened));
    expect(screen.getByText('Already in this draft. Not sent.')).toBeTruthy();
    expect(rendered.container.querySelector('blockquote')!.textContent).toBe(text);
    expect(screen.queryByRole('button', { name: 'Add excerpt to draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Remove added excerpt' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Open original conversation' })).toBeNull();
    expect(rendered.container.querySelectorAll('button')).toHaveLength(0);
    expect(readDraft(dest.drafts(), dest.context)).toBe(`“${text}”\nSource: ${first!.draftSource.label}`);
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(1);
  });

  it('offers exactly the genuine port edit callback once in the Already state', async () => {
    const edit = vi.fn();
    const dest = createDestination({ edit });
    const { source, text } = await projectRecordSource();
    const first = await issueProof(dest, source);
    const view = (p: ProjectSourceDraftProof | null) => <ProjectSourceDraftCompanion proof={p} port={dest.port} />;
    const rendered = render(view(first));
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view(first));
    const reopened = await issueProof(dest, source);
    rendered.rerender(view(reopened));
    expect(screen.getByText('Already in this draft. Not sent.')).toBeTruthy();
    expect(screen.getAllByRole('button')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Open original conversation' }));
    expect(edit).toHaveBeenCalledTimes(1);
    expect(edit).toHaveBeenCalledWith();
    // The existing callback alone acted; the draft and its revision are unchanged:
    expect(readDraft(dest.drafts(), dest.context)).toBe(`“${text}”\nSource: ${first!.draftSource.label}`);
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(1);
  });

  it('does not show Already when the last insertion is a different source', async () => {
    const dest = createDestination();
    const record = await projectRecordSource();
    const reply = await savedReplySource();
    const recordProof = await issueProof(dest, record.source);
    const view = (p: ProjectSourceDraftProof | null) => <ProjectSourceDraftCompanion proof={p} port={dest.port} />;
    const rendered = render(view(recordProof));
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view(recordProof));
    const replyProof = await issueProof(dest, reply.source);
    rendered.rerender(view(replyProof));
    expect(screen.queryByText('Already in this draft. Not sent.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Add excerpt to draft' })).toBeTruthy();
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(1);
  });

  it('does not show Already when the insertion revision does not match', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const first = await issueProof(dest, source);
    const view = (
      p: ProjectSourceDraftProof | null,
      port: ProjectSourceDraftPort = dest.port,
    ) => <ProjectSourceDraftCompanion proof={p} port={port} />;
    const rendered = render(view(first));
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view(first));
    const reopened = await issueProof(dest, source);
    rendered.rerender(view(reopened));
    expect(screen.getByText('Already in this draft. Not sent.')).toBeTruthy();
    const insertion = dest.port.insertion;
    expect(insertion).toBeTruthy();
    rendered.rerender(view(reopened, {
      ...dest.port,
      insertion: { ...insertion!, revision: dest.port.revision + 5 },
    }));
    expect(screen.queryByText('Already in this draft. Not sent.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Add excerpt to draft' })).toBeTruthy();
    expect(readDraft(dest.drafts(), dest.context)).toBe(`“${text}”\nSource: ${first!.draftSource.label}`);
  });

  it('keeps passive rerenders and locale changes from moving focus', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = (locale?: KnowledgeLibraryLocale) =>
      <ProjectSourceDraftCompanion proof={proof} port={dest.port} locale={locale} />;
    const rendered = render(view());
    expect(document.activeElement).toBe(document.body);
    expect(document.querySelector('[autofocus]')).toBeNull();
    const region = screen.getByRole('region', { name: 'Original unsent draft' });
    region.focus();
    expect(document.activeElement).toBe(region);
    rendered.rerender(view());
    expect(document.activeElement).toBe(region);
    rendered.rerender(view('zh-CN'));
    expect(document.activeElement).toBe(region);
    expect(screen.getByRole('region', { name: '原始未发送草稿' })).toBeTruthy();
    expect(document.activeElement).toBe(region);
  });

  it('withdraws and refuses effects when the witness is absent or the proof went stale', async () => {
    const append = vi.fn((_source: DraftSource, _expectedRevision: number) => false);
    const undo = vi.fn((_identity: string, _expectedRevision: number) => false);
    const dest = createDestination({ append, undo });
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = (port: ProjectSourceDraftPort = dest.port) =>
      <ProjectSourceDraftCompanion proof={proof} port={port} />;
    const rendered = render(view());
    expect(rendered.container.querySelector('blockquote')!.textContent).toBe(text);
    // No-notification witness callback: the companion withdraws entirely.
    const witnessless: ProjectSourceDraftPort = { ...dest.port, readWitness: () => null };
    rendered.rerender(view(witnessless));
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.body.textContent).not.toContain(text);
    expect(rendered.container.querySelectorAll('button')).toHaveLength(0);
    rendered.rerender(view());
    expect(rendered.container.querySelector('blockquote')!.textContent).toBe(text);
    // Stale destination: the companion withdraws and no effect is offered.
    dest.writeText('用户手改草稿');
    rendered.rerender(view());
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.body.textContent).not.toContain(text);
    expect(append).not.toHaveBeenCalled();
    expect(undo).not.toHaveBeenCalled();
  });

  it('never fakes success or focus when the owner refuses the append', async () => {
    const append = vi.fn((_source: DraftSource, _expectedRevision: number) => false);
    const dest = createDestination({ append });
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    expect(screen.queryByText('Excerpt added to the draft. Not sent.')).toBeNull();
    expect(screen.queryByText('Already in this draft. Not sent.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Add excerpt to draft' })).toBeTruthy();
    expect(readDraft(dest.drafts(), dest.context)).toBe('');
    expect(append).toHaveBeenCalledTimes(1);
    expect(append.mock.calls[0][0]).toBe(proof!.draftSource);
    expect(append.mock.calls[0][1]).toBe(0);
    expect(document.activeElement).toBe(document.body);
  });

  it('still blocks IME composition Enter and appends only on the explicit click', async () => {
    const append = vi.fn((_source: DraftSource, _expectedRevision: number) => false);
    const dest = createDestination({ append });
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    render(<ProjectSourceDraftCompanion proof={proof} port={dest.port} />);
    const button = screen.getByRole('button', { name: 'Add excerpt to draft' });
    expect(fireEvent.keyDown(button, { key: 'Enter', isComposing: true })).toBe(false);
    expect(append).not.toHaveBeenCalled();
    fireEvent.keyDown(button, { key: 'Enter' });
    expect(append).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(append).toHaveBeenCalledTimes(1);
    expect(append.mock.calls[0][0]).toBe(proof!.draftSource);
    expect(append.mock.calls[0][1]).toBe(0);
  });

  it('renders the zh-CN draft first with exact linebreak text through the append', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} locale="zh-CN" />;
    const rendered = render(view());
    const aside = rendered.container.querySelector('aside')!;
    expect(aside.children[0].textContent).toBe('原始未发送草稿');
    const region = aside.children[1] as HTMLElement;
    expect(region.getAttribute('role')).toBe('region');
    expect(region.getAttribute('tabindex')).toBe('0');
    expect(aside.children[2].textContent).toBe('来源摘录');
    const blockquote = aside.querySelector('blockquote')!;
    expect(blockquote).toBe(aside.children[3]);
    expect(blockquote.textContent).toBe(text);
    expect(screen.getByText('将摘录和来源标签添加到此未发送草稿，不会发送。')).toBeTruthy();
    expect(aside.textContent).toContain('草稿为空。');
    fireEvent.click(screen.getByRole('button', { name: '将摘录添加到草稿' }));
    rendered.rerender(view());
    // The keyed body remounted at the new owner revision; re-read its region:
    const regionAfter = rendered.container.querySelector('aside')!.children[1] as HTMLElement;
    expect(regionAfter).not.toBe(region);
    // The exact current text — including \r\n and trailing spaces — is preserved:
    expect(regionAfter.textContent).toBe(`“${text}”\nSource: ${proof!.draftSource.label}`);
    expect(screen.getByText('摘录已添加到草稿，尚未发送。')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '移除已添加摘录' }));
  });

  it('checks proof classification through the existing helper on every render', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    expect(checkProjectSourceDraftProof(proof!, dest.port)).toBe('APPENDABLE');
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    expect(checkProjectSourceDraftProof(proof!, dest.port)).toBe('UNDOABLE');
    fireEvent.click(screen.getByRole('button', { name: 'Remove added excerpt' }));
    rendered.rerender(view());
    expect(checkProjectSourceDraftProof(proof!, dest.port)).toBe('STALE');
    expect(screen.queryByText('Source excerpt')).toBeNull();
  });
  it('discards Undo focus when the owner methods change despite matching witness fields', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = (port = dest.port) => <>
      <input aria-label="Outside focus" />
      <div className="knowledge-library-reader">
        <article className="knowledge-library-document"><button type="button">Back</button></article>
        <ProjectSourceDraftCompanion proof={proof} port={port} />
      </div>
    </>;
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    fireEvent.click(screen.getByRole('button', { name: 'Remove added excerpt' }));
    const outside = screen.getByRole('textbox', { name: 'Outside focus' });
    outside.focus();
    const current = dest.port;
    rendered.rerender(view({ ...current, append: (source, revision) => current.append(source, revision) }));
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.activeElement).toBe(outside);
    rendered.rerender(view());
    expect(document.activeElement).toBe(outside);
  });

});
