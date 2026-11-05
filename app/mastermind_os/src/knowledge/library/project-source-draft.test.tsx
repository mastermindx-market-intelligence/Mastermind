// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
import type { ProjectionContext } from '../../meta-ceo/projection';
import type { SavedConversationReference } from '../../discovery/saved-conversations';
import type { KnowledgeRepository, KnowledgeSourceResult } from './knowledge-library-contract';
import {
  captureProjectSourceDraftRead,
  checkProjectSourceDraftProof,
  completeProjectSourceDraftRead,
  retireProjectSourceDraftRead,
  type ProjectSourceDraftPort,
  type ProjectSourceDraftProof,
  type ProjectSourceDraftSource,
  type ProjectSourceDraftWitness,
} from './project-source-draft';
import { ProjectSourceDraftCompanion } from './ProjectSourceDraftCompanion';
import fixtureJson from '../../fixtures/project-knowledge-owner.json';
import {KnowledgeLibrary} from './KnowledgeLibrary';
import {buildProjectFileRequest} from './project-knowledge-requests';
import type {KnowledgeLibrarySourceOwner} from './knowledge-library-contract';

afterEach(cleanup);

/* ------------------------------------------------------------------ */
/* Fixture decode (strict, typed, over the supplied Python JSON)        */
/* ------------------------------------------------------------------ */

interface FixtureSourceEntry {
  schema: string;
  availability: string;
  selection: { source_ref: string; work_ref: string };
  source: {
    repository: string; commit: string; path: string; revision: string;
    content_sha256: string; committed_at: string;
  };
  document: { title: string; media_type: string; content_utf8: string; content_sha256: string };
  reason_codes: string[];
}

const FIXTURE = fixtureJson as unknown as { work_ref: string; sources: Record<string, FixtureSourceEntry> };

const UPLOADED_FILE_REF = 'project-file.v1.cd0abe0c380ff2adffeb5ac03833342cfaa5e0fefb0a88e1b4b336db8177e37d';

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

/** Typed strict decode of one fixture source entry into the
 * KnowledgeSourceResult DTO shape this leaf consumes. */
function decodeFixtureSource(sourceRef: string): { result: KnowledgeSourceResult; raw: FixtureSourceEntry } {
  const raw = FIXTURE.sources[sourceRef];
  expect(raw).toBeTruthy();
  expect(raw.schema).toBe('mastermind.workspace_project_source.v1');
  expect(raw.availability).toBe('AVAILABLE');
  expect(raw.selection).toEqual({ source_ref: sourceRef, work_ref: FIXTURE.work_ref });
  expect(raw.reason_codes).toEqual([]);
  expect(raw.source.repository).toBe('mastermindx-market-intelligence/macro');
  expect(raw.source.commit).toMatch(/^[0-9a-f]{40}$/);
  expect(raw.source.revision).toMatch(/^[0-9a-f]{40}$/);
  expect(raw.document.content_sha256).toBe(raw.source.content_sha256);
  expect(raw.document.media_type).toBe('text/markdown');
  const repository = raw.source.repository as KnowledgeRepository;
  const result: KnowledgeSourceResult = Object.freeze({
    availability: 'AVAILABLE',
    source: Object.freeze({
      repository,
      commit: raw.source.commit,
      path: raw.source.path,
      revision: raw.source.revision,
      contentSha256: raw.source.content_sha256,
      committedAt: raw.source.committed_at,
    }),
    document: Object.freeze({
      title: raw.document.title,
      mediaType: 'text/markdown' as const,
      contentUtf8: raw.document.content_utf8,
      contentSha256: raw.document.content_sha256,
    }),
    reasonCodes: Object.freeze([] as string[]),
  });
  return { result, raw };
}

/* ------------------------------------------------------------------ */
/* Synthetic genuine-witness destination over the real drafts functions */
/* ------------------------------------------------------------------ */

interface DestinationOptions {
  append?: (source: DraftSource, expectedRevision: number) => boolean;
  undo?: (identity: string, expectedRevision: number) => boolean;
  readWitness?: () => ProjectSourceDraftWitness | null;
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
      };
    },
  };
}

/* ------------------------------------------------------------------ */
/* Synthetic sources                                                    */
/* ------------------------------------------------------------------ */

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
    reason:null,
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

/** Plain mutable deep copy with one mutation applied (negative shapes keep
 * own plain data properties; only the module's closed validation may reject). */
function mutatedCopy(value: unknown, patch: (root: Record<string, unknown>) => void): ProjectSourceDraftSource {
  const root = JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
  patch(root);
  return root as unknown as ProjectSourceDraftSource;
}

/** Walk a plain JSON round-trip object by path (own string keys only). */
function node(root: Record<string, unknown>, path: readonly string[]): Record<string, unknown> {
  let cursor = root;
  for (const key of path) cursor = cursor[key] as Record<string, unknown>;
  return cursor;
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
/* Proof composition                                                    */
/* ------------------------------------------------------------------ */

describe('project-source-draft proof composition', () => {
  it('issues a proof for a fixture project file and preserves its exact provenance', async () => {
    const dest = createDestination();
    const { result, raw } = decodeFixtureSource(UPLOADED_FILE_REF);
    const proof = await issueProof(dest, { kind: 'PROJECT_FILE', sourceRef: UPLOADED_FILE_REF, result });
    expect(proof).toBeTruthy();
    expect(proof!.sourceKind).toBe('PROJECT_FILE');
    expect(proof!.workRef).toBe('WS:ALPHA');
    // Exact source bytes, CJK included, no trim or summary:
    expect(proof!.draftSource.excerpt).toBe(raw.document.content_utf8);
    expect(proof!.draftSource.excerpt).toContain('中文 body line.');
    expect(proof!.draftSource.label)
      .toBe(`${raw.source.repository} · ${raw.source.path} · ${raw.source.commit} · ${raw.source.revision}`);
    expect(proof!.draftSource.identity).toMatch(/^[0-9a-f]{64}$/);
    expect(Object.isFrozen(proof!.draftSource)).toBe(true);
    expect(Object.isFrozen(proof)).toBe(true);
  });

  it('derives a deterministic identity from kind, work, pointer and text SHA', async () => {
    const dest = createDestination();
    const first = await issueProof(dest, (await projectRecordSource()).source);
    const second = await issueProof(dest, (await projectRecordSource()).source);
    expect(first!.draftSource.identity).toBe(second!.draftSource.identity);
    const changed = await issueProof(dest, (await projectRecordSource('决策记录：修订后的中文决定。')).source);
    expect(changed!.draftSource.identity).not.toBe(first!.draftSource.identity);
    expect(changed!.draftSource.label).toBe(first!.draftSource.label);
    // Record and saved-reply identities never collide with the same text:
    const saved = await savedReplySource('决策记录：中文决定。\r\n记录正文  \n');
    const savedProof = await issueProof(dest, saved.source);
    expect(savedProof!.draftSource.identity).not.toBe(first!.draftSource.identity);
    expect(savedProof!.sourceKind).toBe('SAVED_REPLY');
  });

  it('keeps exact CRLF, CJK, emoji and boundary excerpt bytes', async () => {
    const dest = createDestination();
    const crlf = await issueProof(dest, (await projectRecordSource('决策一\r\n决策二  \n')).source);
    expect(crlf!.draftSource.excerpt).toBe('决策一\r\n决策二  \n');
    // 478 ASCII bytes; the next CJK code point would cross the 480-byte budget:
    const cjkCut = await issueProof(dest, (await projectRecordSource('x'.repeat(478) + '中中🎉')).source);
    expect(cjkCut!.draftSource.excerpt).toBe('x'.repeat(478));
    // 477 ASCII bytes; the next 4-byte emoji would cross the budget intact:
    const emojiCut = await issueProof(dest, (await projectRecordSource('a'.repeat(477) + '🎉\r\n后文')).source);
    expect(emojiCut!.draftSource.excerpt).toBe('a'.repeat(477));
    // Exact ASCII budget boundary still succeeds at 32768 UTF-8 bytes:
    const atBudget = await issueProof(dest, (await projectRecordSource('a'.repeat(32768))).source);
    expect(atBudget!.draftSource.excerpt).toBe('a'.repeat(480));
  });

  it('binds the exact saved-reply reference provenance and appends genuinely unsent', async () => {
    const dest = createDestination();
    const saved = await savedReplySource();
    const proof = await issueProof(dest, saved.source);
    expect(proof).toBeTruthy();
    expect(proof!.draftSource.label)
      .toBe(`${saved.readRef} · WS:ALPHA · ${saved.rootJobId} · ${saved.requestedAt}`);
    expect(proof!.draftSource.excerpt).toBe(saved.text);
    // One explicit append through the port lands in the REAL drafts state:
    expect(dest.port.append(proof!.draftSource, dest.port.revision)).toBe(true);
    const drafts = dest.drafts();
    expect(readDraft(drafts, dest.context))
      .toBe(`“${saved.text}”\nSource: ${proof!.draftSource.label}`);
    expect(readDraftRevision(drafts, dest.context)).toBe(1);
    expect(readDraftInsertion(drafts, dest.context)?.revision).toBe(1);
    expect(readDraftInsertion(drafts, dest.context)?.before).toBe('');
  });

  it('refuses malformed, unavailable, relabelled, out-of-namespace or oversize sources', async () => {
    const dest = createDestination();
    const record = await projectRecordSource();
    const saved = await savedReplySource();
    const oversizeSha = await sha256Hex('a'.repeat(32769));
    const savedOversizeSha = await sha256Hex('a'.repeat(16385));
    const otherBodySha = await sha256Hex('other body');
    const getterText = mutatedCopy(record.source, root => {
      Object.defineProperty(node(root, ['result', 'document']), 'contentUtf8',
        { enumerable: true, get: () => 'getter body' });
    });
    const cases: Array<[string, ProjectSourceDraftSource]> = [
      ['unavailable result', mutatedCopy(record.source, root => {
        node(root, ['result']).availability = 'UNAVAILABLE';
      })],
      ['unempty reason codes', mutatedCopy(record.source, root => {
        node(root, ['result']).reasonCodes = ['SOURCE_CHANGED'];
      })],
      ['wrong repository namespace', mutatedCopy(record.source, root => {
        node(root, ['result', 'source']).repository = 'other/macro';
      })],
      ['kind and sourceRef mismatch', {
        kind: 'PROJECT_FILE', sourceRef: RECORD_REF, result: record.source.result,
      } as unknown as ProjectSourceDraftSource],
      ['relabelled document sha', mutatedCopy(record.source, root => {
        node(root, ['result', 'document']).contentSha256 = otherBodySha;
      })],
      ['relabelled raw result bytes', mutatedCopy(record.source, root => {
        node(root, ['result', 'document']).contentUtf8 = 'other body';
      })],
      ['non-canonical blob path', mutatedCopy(record.source, root => {
        node(root, ['result', 'source']).path = 'agentos/../secrets/notes.md';
      })],
      ['oversize project text', mutatedCopy(record.source, root => {
        const result = node(root, ['result']);
        node(result, ['document']).contentUtf8 = 'a'.repeat(32769);
        node(result, ['document']).contentSha256 = oversizeSha;
        node(result, ['source']).contentSha256 = oversizeSha;
      })],
      ['oversize saved text', mutatedCopy(saved.source, root => {
        const result = node(root, ['result']);
        result.text = 'a'.repeat(16385);
        result.sourceTextSha256 = savedOversizeSha;
      })],
      ['saved work mismatch', (await savedReplySource('答复', 'WS:BETA')).source],
      ['retained-result extra key on the union', Object.assign(
        JSON.parse(JSON.stringify(record.source)) as object, { retainedMarker: true },
      ) as unknown as ProjectSourceDraftSource],
      ['retained-result extra key on the result', mutatedCopy(record.source, root => {
        node(root, ['result']).retained = true;
      })],
      ['getter-backed source text', getterText],
      ['saved reply not reference-only', mutatedCopy(saved.source, root => {
        node(root, ['result', 'reference']).reference_only = false;
      })],
      ['malformed saved operation',mutatedCopy(saved.source,root=>{node(root,['result','reference']).operation_key='session-continue-invalid';})],
      ['malformed saved event',mutatedCopy(saved.source,root=>{node(root,['result','reference']).request_event_id=0;})],
      ['malformed saved target',mutatedCopy(saved.source,root=>{node(root,['result','reference']).target_ref='unqualified';})],
      ['missing source pointer', mutatedCopy(record.source, root => {
        node(root, ['result']).source = null;
      })],
      ['saved read without text sha', mutatedCopy(saved.source, root => {
        delete node(root, ['result']).sourceTextSha256;
      })],
    ];
    for (const [label, candidate] of cases) {
      const ticket = captureProjectSourceDraftRead(dest.port, 'WS:ALPHA', () => true);
      expect(ticket, label).toBeTruthy();
      expect(await completeProjectSourceDraftRead(ticket!, candidate, dest.port), label).toBeNull();
    }
  });

  it('consumes each ticket exactly once and honors retirement', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const retired = captureProjectSourceDraftRead(dest.port, 'WS:ALPHA', () => true);
    expect(retired).toBeTruthy();
    retireProjectSourceDraftRead(retired!);
    expect(await completeProjectSourceDraftRead(retired!, source, dest.port)).toBeNull();
    const good = captureProjectSourceDraftRead(dest.port, 'WS:ALPHA', () => true);
    const proof = await completeProjectSourceDraftRead(good!, source, dest.port);
    expect(proof).toBeTruthy();
    expect(await completeProjectSourceDraftRead(good!, source, dest.port)).toBeNull();
    const spent = captureProjectSourceDraftRead(dest.port, 'WS:ALPHA', () => true)!;
    expect(await completeProjectSourceDraftRead(spent, { kind: 'PROJECT_FILE', sourceRef: 'x' } as unknown as ProjectSourceDraftSource, dest.port)).toBeNull();
    expect(await completeProjectSourceDraftRead(spent, source, dest.port)).toBeNull();
    expect(captureProjectSourceDraftRead(dest.port, 'WS:BETA', () => true)).toBeNull();
  });

  it('refuses witness movement between capture, before-hash and after-hash', async () => {
    const { source } = await projectRecordSource();
    const base = { workRef: 'WS:ALPHA', binding: 'principal:queued-binding', revision: 0 };
    const movedAfterHash = [base, base, { ...base, revision: 1 }];
    const movedBeforeHash = [base, { ...base, revision: 1 }, base];
    const rebound = [base, base, { ...base, binding: 'principal:other-binding' }];
    for (const [label, queue] of [['after', movedAfterHash], ['before', movedBeforeHash], ['binding', rebound]] as const) {
      const dest = createDestination({ readWitness: () => queue.shift() ?? null });
      const ticket = captureProjectSourceDraftRead(dest.port, 'WS:ALPHA', () => true);
      expect(ticket, label).toBeTruthy();
      expect(await completeProjectSourceDraftRead(ticket!, source, dest.port), label).toBeNull();
    }
  });

  it('refuses replaced port method identities', async () => {
    const destA = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(destA, source);
    expect(proof).toBeTruthy();
    const destB = createDestination();
    expect(checkProjectSourceDraftProof(proof, destB.port)).toBe('STALE');
    const ticket = captureProjectSourceDraftRead(destA.port, 'WS:ALPHA', () => true);
    expect(await completeProjectSourceDraftRead(ticket!, source, destB.port)).toBeNull();
    const getterPort = { ...destA.port };
    Object.defineProperty(getterPort, 'text', { enumerable: true, get: () => '' });
    const ticket2 = captureProjectSourceDraftRead(destA.port, 'WS:ALPHA', () => true);
    expect(await completeProjectSourceDraftRead(ticket2!, source, getterPort as ProjectSourceDraftPort)).toBeNull();
    expect(captureProjectSourceDraftRead(getterPort as ProjectSourceDraftPort, 'WS:ALPHA', () => true)).toBeNull();
    expect(captureProjectSourceDraftRead({ ...destA.port, revision: -1 }, 'WS:ALPHA', () => true)).toBeNull();
  });

  it('gates append on the original revision and undo on the matching insertion', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    expect(checkProjectSourceDraftProof(proof, dest.port)).toBe('APPENDABLE');
    expect(dest.port.append(proof!.draftSource, dest.port.revision)).toBe(true);
    // After our own append only the matching undo is possible, never a new append:
    expect(checkProjectSourceDraftProof(proof, dest.port)).toBe('UNDOABLE');
    expect(dest.port.append(proof!.draftSource, dest.port.revision)).toBe(false);
    expect(dest.port.undo('other-source-identity', dest.port.revision)).toBe(false);
    expect(dest.port.undo(proof!.draftSource.identity, dest.port.revision)).toBe(true);
    // Undo advanced the revision again; the proof is stale for both actions:
    expect(checkProjectSourceDraftProof(proof, dest.port)).toBe('STALE');
    dest.writeText('用户手改');
    expect(checkProjectSourceDraftProof(proof, dest.port)).toBe('STALE');
  });

  it('marks spoofed proofs and unavailable witnesses STALE', async () => {
    const dest = createDestination();
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    expect(checkProjectSourceDraftProof(proof, dest.port)).toBe('APPENDABLE');
    const spoof = {
      sourceKind: 'PROJECT_RECORD', workRef: 'WS:ALPHA', draftSource: proof!.draftSource,
    } as unknown as ProjectSourceDraftProof;
    expect(checkProjectSourceDraftProof(spoof, dest.port)).toBe('STALE');
    expect(checkProjectSourceDraftProof(null, dest.port)).toBe('STALE');
    expect(checkProjectSourceDraftProof(proof, undefined)).toBe('STALE');
    let witness: ProjectSourceDraftWitness | null = {
      workRef: 'WS:ALPHA', binding: dest.binding, revision: readDraftRevision(dest.drafts(), dest.context),
    };
    const vanishing = createDestination({ readWitness: () => witness });
    const ticket = captureProjectSourceDraftRead(vanishing.port, 'WS:ALPHA', () => true);
    const vanishingProof = await completeProjectSourceDraftRead(ticket!, source, vanishing.port);
    expect(vanishingProof).toBeTruthy();
    witness = null;
    expect(checkProjectSourceDraftProof(vanishingProof, vanishing.port)).toBe('STALE');
  });
});

/* ------------------------------------------------------------------ */
/* Companion                                                            */
/* ------------------------------------------------------------------ */

describe('ProjectSourceDraftCompanion', () => {
  it('shows the original draft, exact excerpt and one explicit add action', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    expect(document.activeElement).toBe(document.body);
    expect(document.querySelector('[autofocus]')).toBeNull();
    const panel = rendered.container.querySelector('aside.knowledge-library-aside-panel');
    expect(panel).toBeTruthy();
    const excerpt = panel!.querySelector('blockquote.knowledge-library-plaintext');
    expect(excerpt!.textContent).toBe(text);
    expect(panel!.textContent).toContain('Original unsent draft');
    expect(panel!.textContent).toContain('The draft is empty.');
    expect(panel!.textContent).toContain(`${proof!.draftSource.label}`);
    expect(panel!.textContent).toContain('Nothing is sent, stored or re-read');
    expect(rendered.container.querySelectorAll('button')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Add excerpt to draft' })).toBeTruthy();
  });

  it('appends once unsent, then permits only the matching undo', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    rendered.rerender(view());
    expect(screen.getByText('Excerpt added to the draft. Not sent.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Add excerpt to draft' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Remove added excerpt' })).toBeTruthy();
    expect(readDraft(dest.drafts(), dest.context)).toBe(`“${text}”\nSource: ${proof!.draftSource.label}`);
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: 'Remove added excerpt' }));
    rendered.rerender(view());
    // Undo advanced the revision; the proof is stale and the excerpt hides:
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.body.textContent).not.toContain(text);
    expect(readDraft(dest.drafts(), dest.context)).toBe('');
    expect(readDraftRevision(dest.drafts(), dest.context)).toBe(2);
  });

  it('hides the private excerpt when the destination changes under the proof', async () => {
    const undo = vi.fn(() => false);
    const append = vi.fn(() => false);
    const dest = createDestination({ append, undo });
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} />;
    const rendered = render(view());
    expect(rendered.container.querySelector('blockquote')!.textContent).toBe(text);
    dest.writeText('用户手改草稿');
    rendered.rerender(view());
    expect(screen.queryByText('Source excerpt')).toBeNull();
    expect(document.body.textContent).not.toContain(text);
    expect(append).not.toHaveBeenCalled();
    expect(undo).not.toHaveBeenCalled();
    rendered.rerender(<ProjectSourceDraftCompanion proof={proof} locale="en" />);
    expect(document.body.textContent).not.toContain(text);
    rendered.rerender(<ProjectSourceDraftCompanion proof={null} port={dest.port} />);
    expect(document.body.textContent).not.toContain(text);
  });

  it('blocks IME composition Enter and appends only on the explicit click', async () => {
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

  it('renders zh-CN copy with the same single explicit action', async () => {
    const dest = createDestination();
    const { source, text } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const view = () => <ProjectSourceDraftCompanion proof={proof} port={dest.port} locale="zh-CN" />;
    const rendered = render(view());
    expect(rendered.container.querySelectorAll('button')).toHaveLength(1);
    expect(document.activeElement).toBe(document.body);
    fireEvent.click(screen.getByRole('button', { name: '将摘录添加到草稿' }));
    rendered.rerender(view());
    expect(screen.getByText('摘录已添加到草稿，尚未发送。')).toBeTruthy();
    expect(screen.getByRole('button', { name: '移除已添加摘录' })).toBeTruthy();
    expect(readDraft(dest.drafts(), dest.context)).toBe(`“${text}”\nSource: ${proof!.draftSource.label}`);
    expect(rendered.container.querySelector('aside')!.textContent).toContain('原始未发送草稿');
  });

  it('never fakes success when the owner refuses or has not synced', async () => {
    const append = vi.fn(() => false);
    const dest = createDestination({ append });
    const { source } = await projectRecordSource();
    const proof = await issueProof(dest, source);
    const refused = render(<ProjectSourceDraftCompanion proof={proof} port={dest.port} />);
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    expect(screen.queryByText('Excerpt added to the draft. Not sent.')).toBeNull();
    expect(readDraft(dest.drafts(), dest.context)).toBe('');
    refused.unmount();
    const unsynced = createDestination({ append: vi.fn(() => true) });
    const unsyncedProof = await issueProof(unsynced, source);
    render(<ProjectSourceDraftCompanion proof={unsyncedProof} port={unsynced.port} />);
    fireEvent.click(screen.getByRole('button', { name: 'Add excerpt to draft' }));
    expect(screen.getByText('Excerpt added to the draft. Not sent.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Add excerpt to draft' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Remove added excerpt' })).toBeNull();
    expect(readDraft(unsynced.drafts(), unsynced.context)).toBe('');
  });
});


describe('actual reader and project source proof join',()=>{
  function sourceOwner() {
    let generation='source-1';
    const owner={context:()=>({generation}),authGeneration:()=>7,
      readCatalogue:async()=>fixtureJson.catalogue as never,
      readSource:async({sourceRef}:{sourceRef:string})=>fixtureJson.sources[sourceRef as keyof typeof fixtureJson.sources] as never};
    return {owner,revoke:()=>{generation='source-2';}};
  }
  it('captures before actual Library Open, appends exact qualified file unsent, and undoes',async()=>{
    const dest=createDestination();dest.writeText('Original draft');
    const f=sourceOwner();
    const props={workRef:'WS:ALPHA',authGeneration:7,hostGeneration:1,fileSearchOwner:f.owner,
      readCatalogue:async()=>fixtureJson.catalogue as never,
      readSource:async({sourceRef}:{sourceRef:string})=>f.owner.readSource({sourceRef})};
    const view=render(<KnowledgeLibrary {...props} draftPort={dest.port}/>);
    const row=(await screen.findByText('Uploaded file')).closest('.knowledge-library-row')!;
    fireEvent.click(within(row as HTMLElement).getByRole('button',{name:'Open'}));
    fireEvent.click(await screen.findByRole('button',{name:'Add excerpt to draft'}));
    view.rerender(<KnowledgeLibrary {...props} draftPort={dest.port}/>);
    expect(readDraft(dest.drafts(),dest.context)).toContain('Original draft');
    const expected=decodeFixtureSource(UPLOADED_FILE_REF).raw.document.content_utf8;
    expect(readDraft(dest.drafts(),dest.context)).toContain(expected);
    fireEvent.click(await screen.findByRole('button',{name:'Remove added excerpt'}));
    expect(readDraft(dest.drafts(),dest.context)).toBe('Original draft');
  });
  it('refuses append if the actual source owner revokes without a React render',async()=>{
    const dest=createDestination(),f=sourceOwner();
    render(<KnowledgeLibrary workRef="WS:ALPHA" authGeneration={7} hostGeneration={1} draftPort={dest.port}
      fileSearchOwner={f.owner} readCatalogue={async()=>fixtureJson.catalogue}
      readSource={async({sourceRef})=>f.owner.readSource({sourceRef})}/>);
    const row=(await screen.findByText('Uploaded file')).closest('.knowledge-library-row')!;
    fireEvent.click(within(row as HTMLElement).getByRole('button',{name:'Open'}));
    const append=await screen.findByRole('button',{name:'Add excerpt to draft'});
    f.revoke();fireEvent.click(append);
    expect(readDraftRevision(dest.drafts(),dest.context)).toBe(0);
    expect(readDraft(dest.drafts(),dest.context)).toBe('');
  });
  it('binds file and record opaque references to the exact work rather than a Runtime root',async()=>{
    const dest=createDestination({readWitness:()=>({workRef:'WS:BETA',binding:'genuine-other-work',revision:0})});
    const ticket=captureProjectSourceDraftRead(dest.port,'WS:BETA',()=>true)!;
    const file=decodeFixtureSource(UPLOADED_FILE_REF).result;
    expect(await completeProjectSourceDraftRead(ticket,{kind:'PROJECT_FILE',sourceRef:UPLOADED_FILE_REF,result:file},dest.port)).toBeNull();
    const recordTicket=captureProjectSourceDraftRead(dest.port,'WS:BETA',()=>true)!;
    expect(await completeProjectSourceDraftRead(recordTicket,(await projectRecordSource()).source,dest.port)).toBeNull();
  });
  it('accepts the actual bounded JSON destination binding and rechecks source currentness at completion',async()=>{
    const binding=JSON.stringify({authGeneration:7,selection:{workRef:'WS:ALPHA',rootJobId:'JOB-'+ 'r'.repeat(110)},
      sessionRef:'session-'+ 's'.repeat(100),bindingGeneration:'generation-'+ 'b'.repeat(80),revisions:{mission:null,result:null}});
    expect(binding.length).toBeGreaterThan(256);
    const dest=createDestination({readWitness:()=>({workRef:'WS:ALPHA',binding,revision:0})});
    const source=(await projectRecordSource()).source;
    let current=true;
    const ticket=captureProjectSourceDraftRead(dest.port,'WS:ALPHA',()=>current)!;
    expect(await completeProjectSourceDraftRead(ticket,source,dest.port)).toBeTruthy();
    const second=captureProjectSourceDraftRead(dest.port,'WS:ALPHA',()=>current)!;
    current=false;expect(await completeProjectSourceDraftRead(second,source,dest.port)).toBeNull();
    expect(captureProjectSourceDraftRead(dest.port,'WS:ALPHA',()=>false)).toBeNull();
  });
});


it('the real Library source getter expires during an async selected-file read and on unmount',async()=>{
 let registered:KnowledgeLibrarySourceOwner|null=null;
 let generation='catalogue-current';
 const owner={context:()=>({generation}),authGeneration:()=>7,readCatalogue:async()=>fixtureJson.catalogue as never,
  readSource:async()=>fixtureJson.sources[UPLOADED_FILE_REF as keyof typeof fixtureJson.sources] as never};
 const view=render(<KnowledgeLibrary workRef="WS:ALPHA" authGeneration={7} hostGeneration={1}
   readCatalogue={async()=>fixtureJson.catalogue} fileSearchOwner={owner} onCurrentSourceOwner={value=>{registered=value;}}/>);
 await screen.findByText('Uploaded file');expect(registered).not.toBeNull();
 const actual=registered! as KnowledgeLibrarySourceOwner;
 const snapshot={workRef:'WS:ALPHA',sourceCommit:fixtureJson.catalogue.source.commit,baseRevision:fixtureJson.catalogue.source.workstream_sha256};
 expect(actual.current(snapshot)).toEqual(snapshot);
 expect(()=>actual.current({...snapshot,baseRevision:'0'.repeat(64)})).toThrow('SOURCE_CHANGED');
 let finish!:(buffer:ArrayBuffer)=>void;
 const bytes=new TextEncoder().encode('Literal file');
 const file=new File([bytes],'计划.MD',{type:'text/markdown'});
 Object.defineProperty(file,'arrayBuffer',{value:()=>new Promise<ArrayBuffer>(resolve=>{finish=resolve;})});
 const request=buildProjectFileRequest(snapshot,'mmos-project-file-add-'+'a'.repeat(40),file,new AbortController().signal,actual.current);
 generation='catalogue-revoked';finish(bytes.buffer as ArrayBuffer);
 await expect(request).rejects.toMatchObject({code:'SOURCE_CHANGED'});
 view.unmount();expect(registered).toBeNull();expect(()=>actual.current(snapshot)).toThrow('SOURCE_CHANGED');
});
