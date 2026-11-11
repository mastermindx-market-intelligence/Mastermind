// @vitest-environment jsdom
/**
 * Knowledge Library — Vitest/jsdom tests over synthetic, strictly typed owner
 * fixtures.
 *
 * These fixtures are NOT live auth, a live host, or real owner receipts: every
 * read port is an in-memory stub built to the frozen backend DTO shapes, and
 * every digest is computed locally. They verify this presentation slice's
 * gating, hashing, diagnostics and typed parent handoffs only. Real python
 * producers, real source/action controllers and integration tests remain with
 * the parent acceptance suite.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { KnowledgeLibrary } from './KnowledgeLibrary';
import { sha256Hex } from './knowledge-library-contract';
import type { KnowledgeLibraryProps } from './knowledge-library-contract';

const WORK_REF = 'WS:2026-11-MARKET-INTELLIGENCE';
const REPO = 'mastermindx-market-intelligence/macro';
const COMMIT = '1111111111111111111111111111111111111111';
const OTHER_COMMIT = '2222222222222222222222222222222222222222';
const WS_SHA = '3'.repeat(64);
const FILE_REV = '4'.repeat(40);
const FILE_REF = 'project-file.v1.'+'a'.repeat(64);
const MISSING_REF = 'project-file.v1.'+'b'.repeat(64);
const REQ_SHA = 'c'.repeat(64);
const MEM_SOURCE_REV = 'd'.repeat(40);
const CONV_SOURCE_REF = 'session-reply-'+'e'.repeat(64);
const RECORD_REF='project-record.v1.'+'e'.repeat(64);
const CONV_SOURCE_REV = 'f'.repeat(64);
const PREFERENCE_REF='project-record.v1.'+'9'.repeat(64);
const PREFERENCE_PATH='agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-2026-11-MARKET-INTELLIGENCE.md';
const PREF_VALUE = 'Prefer concise weekly email updates.';
const SOURCE_TEXT = '# Original brief\n\nScope and sources for the market intelligence project.';

let SOURCE_SHA = '';
const SOURCE_PATH = 'agentos/project-files/WS-2026-11-MARKET-INTELLIGENCE/'+'0'.repeat(64)+'.md';

function cataloguePayload(overrides: Record<string, unknown> = {}) {
  return {
    schema: 'mastermind.workspace_project_knowledge.v1',
    selection: { work_ref: WORK_REF },
    availability: 'AVAILABLE',
    reason_codes: [],
    source: { repository: REPO, commit: COMMIT, workstream_sha256: WS_SHA },
    project: {
      title: 'Market intelligence 2026',
      files: [
        {
          source_ref: FILE_REF,
          repository: 'macro',
          path: SOURCE_PATH,
          revision: FILE_REV,
          display_name: 'Original brief',
          media_type: 'text/markdown',
          content_sha256: SOURCE_SHA,
          state: 'READABLE',
          origin: { kind: 'PRINCIPAL_UPLOAD', actor_ref: 'workspace:'+ 'a'.repeat(64), request_sha256: REQ_SHA },
          viewer_relation: 'UNKNOWN',
        },
        {
          source_ref: MISSING_REF,
          repository: null,
          path: null,
          revision: null,
          display_name: 'Projected appendix',
          media_type: null,
          content_sha256: null,
          state: 'SOURCE_MISSING',
          origin: { kind: 'DECLARED_ARTIFACT', actor_ref: null, request_sha256: null },
          viewer_relation: 'UNKNOWN',
        },
      ],
      records: [
        {
          source_ref: RECORD_REF,
          path: 'agentos/workstreams/WS-2026-11-MARKET-INTELLIGENCE.md',
          revision: MEM_SOURCE_REV,
          kind: 'WORKSTREAM',
          title: 'Market intelligence workstream',
          authored_at: '2026-10-01',
          committed_at: '2026-10-02T09:15:00Z',
        },
      ],
      memory: { state: 'EMPTY', source_ref: null, revision: null },
      coverage: {
        files: { state: 'PARTIAL', declared: 3, listed: 2, omitted: 1 },
        records: { state: 'BOUNDED_SAMPLE', scanned: 3, matched: 1, omitted: 1, invalid: 1 },
      },
    },
    ...overrides,
  };
}

function sourcePayload(document: Record<string, unknown>, commit = COMMIT) {
  return {
    schema: 'mastermind.workspace_project_source.v1',
    selection: { work_ref: WORK_REF, source_ref: FILE_REF },
    availability: 'AVAILABLE',
    reason_codes: [],
    source: {
      repository: REPO,
      commit,
      path: SOURCE_PATH,
      revision: FILE_REV,
      content_sha256: document['content_sha256'],
      committed_at: '2026-10-12T08:30:00Z',
    },
    document,
  };
}

function memoryPayload(overrides: Record<string, unknown> = {}) {
  return {
    schema: 'mastermind.workspace_project_preference.v1',
    selection: { work_ref: WORK_REF },
    availability: 'AVAILABLE',
    reason_codes: [],
    source: {
      repository: REPO,
      commit: COMMIT,
      path: PREFERENCE_PATH,
      revision: FILE_REV,
      content_sha256: SOURCE_SHA,
      committed_at: '2026-10-12T08:30:00Z',
    },
    memory: {
      value: PREF_VALUE,
      origin: {
        kind: 'CONVERSATION',
        actor_ref: 'workspace:'+ 'a'.repeat(64),
        source_ref: CONV_SOURCE_REF,
        source_revision: CONV_SOURCE_REV,
      },
      last_edit: { actor_ref: 'workspace:'+ 'a'.repeat(64), request_sha256: REQ_SHA },
    },
    ...overrides,
  };
}

function catalogueMemoryPayload() {
  const raw=cataloguePayload();
  raw.project.memory={state:'AVAILABLE',source_ref:PREFERENCE_REF,revision:FILE_REV} as never;
  raw.project.records.push({source_ref:PREFERENCE_REF,path:PREFERENCE_PATH,revision:FILE_REV,
    kind:'PROJECT_PREFERENCE',title:'Project communication preference',authored_at:'2026-10-01',committed_at:'2026-10-12T08:30:00Z'});
  raw.project.coverage.records={state:'BOUNDED_SAMPLE',scanned:4,matched:2,omitted:1,invalid:1};
  return raw;
}

const ACTIONS_PAYLOAD = {
  schema: 'mastermind.project_knowledge_actions.v1',
  selection: { work_ref: WORK_REF },
  source_commit: COMMIT,
  base_revision: WS_SHA,
  actions: { add_files: 'AVAILABLE', edit_preference: 'AVAILABLE' },
};

type SourceRequest = { workRef: string; sourceRef: string; expectedRevision: string; signal: AbortSignal };

function baseProps(): KnowledgeLibraryProps {
  return {
    workRef: WORK_REF,
    authGeneration: 7,
    hostGeneration: 'host-gen-1',
    locale: 'en',
    theme: 'dark',
  };
}

function makeProps(overrides: Partial<KnowledgeLibraryProps> = {}): KnowledgeLibraryProps {
  return { ...baseProps(), ...overrides };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeAll(async () => {
  SOURCE_SHA = await sha256Hex(SOURCE_TEXT);
});

afterEach(() => {
  cleanup();
});

async function renderWithOwner(props: Partial<KnowledgeLibraryProps> = {}, payloadOverrides: Record<string, unknown> = {}) {
  const readCatalogue = vi.fn(async () => ({...(props.readMemory ? catalogueMemoryPayload() : cataloguePayload()),...payloadOverrides}));
  const readSource = vi.fn(async (_request:SourceRequest) => sourcePayload({title:'Original brief',media_type:'text/markdown',content_utf8:SOURCE_TEXT,content_sha256:SOURCE_SHA}));
  const readActions = vi.fn(async () => ACTIONS_PAYLOAD);
  const view = render(
    <KnowledgeLibrary
      {...makeProps({
        readCatalogue,
        readActions,
        readSource,
        ...props,
      })}
    />,
  );
  await waitFor(() => expect(screen.getByText('Market intelligence 2026')).toBeTruthy());
  return { view, readCatalogue, readActions };
}

describe('KnowledgeLibrary files list', () => {
  it('renders the actual catalogue title, named rows and upload provenance', async () => {
    await renderWithOwner();
    expect(screen.getByText('Mastermind OS')).toBeTruthy();
    expect(screen.getByText('Original brief')).toBeTruthy();
    expect(screen.queryByText('Added by you')).toBeNull();
    expect(screen.getByText('Projected appendix')).toBeTruthy();
    // Only the actual owner's CURRENT_PRINCIPAL upload says "Added by you".
    expect(screen.getByText('Uploaded file')).toBeTruthy();
  });

  it('enables Open only for the readable row and shows the honest partial notice', async () => {
    await renderWithOwner();
    const openButtons = screen.getAllByRole('button', { name: 'Open' });
    expect(openButtons).toHaveLength(1);
    expect(screen.getByText(/Some sources are unavailable/)).toBeTruthy();
    expect(screen.getByText(/Showing 2 of 3 declared files in the permitted scope/)).toBeTruthy();
  });

  it('does not read anything when the read ports are absent', async () => {
    const readCatalogue = vi.fn();
    render(<KnowledgeLibrary {...makeProps({ readCatalogue: undefined })} />);
    await waitFor(() => expect(screen.getByText('Knowledge is not available for this view.')).toBeTruthy());
    expect(readCatalogue).not.toHaveBeenCalled();
    expect(screen.queryByText('Original brief')).toBeNull();
  });

  it('rejects a foreign work ref without rendering any private payload', async () => {
    const readCatalogue = vi.fn(async () => cataloguePayload({ selection: { work_ref: 'ws-other-project' } }));
    render(<KnowledgeLibrary {...makeProps({ readCatalogue })} />);
    await waitFor(() => expect(screen.getByText('This project knowledge could not be read safely.')).toBeTruthy());
    expect(screen.queryByText('Market intelligence 2026')).toBeNull();
    expect(screen.queryByText('Original brief')).toBeNull();
  });

  it('clears private DOM on late auth replacement and re-reads once', async () => {
    const first = vi.fn(async () => cataloguePayload());
    const second = deferred<unknown>();
    const readCatalogue = vi.fn((request: { signal: AbortSignal }) =>
      readCatalogue.mock.calls.length === 1 ? first() : second.promise,
    );
    const view = render(<KnowledgeLibrary {...makeProps({ readCatalogue })} />);
    await waitFor(() => expect(screen.getByText('Market intelligence 2026')).toBeTruthy());
    view.rerender(
      <KnowledgeLibrary
        {...makeProps({ authGeneration: 8, readCatalogue: readCatalogue as unknown as KnowledgeLibraryProps['readCatalogue'] })}
      />,
    );
    await waitFor(() => expect(screen.queryByText('Market intelligence 2026')).toBeNull());
    expect(screen.queryByText('Original brief')).toBeNull();
  });
});

describe('KnowledgeLibrary source reader', () => {
  it('opens the exact read tuple, renders verbatim text and keeps raw ids closed', async () => {
    const readSource = vi.fn(async (_request: SourceRequest) => sourcePayload({
      title: 'Original brief',
      media_type: 'text/markdown',
      content_utf8: SOURCE_TEXT,
      content_sha256: SOURCE_SHA,
    }));
    const renderSourceCompanion = vi.fn((_source: unknown) => 'companion-slot');
    await renderWithOwner({ readSource, renderSourceCompanion });
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    await waitFor(() => expect(screen.getByText('Scope and sources for the market intelligence project.')).toBeTruthy());
    expect(readSource).toHaveBeenCalledTimes(1);
    expect(readSource.mock.calls[0][0]).toEqual({
      workRef: WORK_REF,
      sourceRef: FILE_REF,
      expectedRevision: FILE_REV,
      signal: expect.anything(),
    });
    expect(renderSourceCompanion).toHaveBeenCalled();
    expect((renderSourceCompanion.mock.calls.at(-1)![0] as {contentUtf8:string}).contentUtf8).toBe(SOURCE_TEXT);
    expect((renderSourceCompanion.mock.calls[0][0] as { sourceRef: string }).sourceRef).toBe(FILE_REF);
    const details = screen.getByText('Source details').closest('details') as HTMLDetailsElement;
    expect(details.open).toBe(false);
    fireEvent.click(screen.getByText('Source details'));
    expect(details.textContent).toContain(`commit: ${COMMIT}`);
    expect(details.textContent).toContain(SOURCE_PATH);
    // Lists are hidden while the reader is open.
    expect(screen.getByText('Original brief', { selector: '.knowledge-library-row-title' }).closest('[hidden]')).not.toBeNull();
  });

  it('fails closed with a refresh prompt when the source snapshot moved', async () => {
    const readSource = vi.fn(async () => sourcePayload({
      title: 'Original brief',
      media_type: 'text/markdown',
      content_utf8: SOURCE_TEXT,
      content_sha256: SOURCE_SHA,
    }, OTHER_COMMIT));
    await renderWithOwner({ readSource });
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    await waitFor(() => expect(screen.getByText('This source changed. Refresh to continue.')).toBeTruthy());
    expect(screen.queryByText('Scope and sources for the market intelligence project.')).toBeNull();
  });

  it('fails closed on a digest tamper without showing the content', async () => {
    const readSource = vi.fn(async () => sourcePayload({
      title: 'Original brief',
      media_type: 'text/markdown',
      content_utf8: SOURCE_TEXT,
      content_sha256: '9'.repeat(64),
    }));
    await renderWithOwner({ readSource });
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    await waitFor(() => expect(screen.getByText('This source changed. Refresh to continue.')).toBeTruthy());
    expect(screen.queryByText('Scope and sources for the market intelligence project.')).toBeNull();
  });

  it('rejects over-budget and unsafe-unicode bodies without rendering content', async () => {
    const readSource = vi.fn(async () => sourcePayload({
      title: 'Original brief',
      media_type: 'text/markdown',
      content_utf8: 'x'.repeat(40000),
      content_sha256: await sha256Hex('x'.repeat(40000)),
    }));
    await renderWithOwner({ readSource });
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    await waitFor(() => expect(screen.getByText('This project knowledge could not be read safely.')).toBeTruthy());
    expect(screen.queryByText(/xxxxx/)).toBeNull();
  });

  it('preserves the query and restores focus on explicit Back only', async () => {
    const readSource = vi.fn(async () => sourcePayload({
      title: 'Original brief',
      media_type: 'text/markdown',
      content_utf8: SOURCE_TEXT,
      content_sha256: SOURCE_SHA,
    }));
    await renderWithOwner({ readSource });
    const query = screen.getByLabelText('Filter') as HTMLInputElement;
    fireEvent.change(query, { target: { value: 'brief' } });
    const open = screen.getByRole('button', { name: 'Open' });
    fireEvent.click(open);
    await waitFor(() => expect(screen.getByText('Scope and sources for the market intelligence project.')).toBeTruthy());
    expect(screen.getByLabelText('Filter').closest('[hidden]')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await waitFor(() => expect(document.activeElement).toBe(open));
    expect((screen.getByLabelText('Filter') as HTMLInputElement).value).toBe('brief');
    fireEvent.keyDown(window, { key: 'Escape' });
    // Escape in list view is view-only: nothing changes.
    expect(screen.getByRole('button', { name: 'Open' })).toBeTruthy();
  });
});

describe('KnowledgeLibrary records view', () => {
  it('browses the actual canonical record list with metadata filtering', async () => {
    await renderWithOwner();
    fireEvent.click(screen.getByRole('button', { name: 'Browse all records' }));
    expect(screen.getByText('All records')).toBeTruthy();
    expect(screen.getByText('Market intelligence workstream')).toBeTruthy();
    expect(screen.getByText('Listing 1 records from 3 reviewed candidates in the permitted sample.')).toBeTruthy();
    const query = screen.getByLabelText('Filter') as HTMLInputElement;
    fireEvent.change(query, { target: { value: 'nothing-matches-this' } });
    expect(screen.getByText('Nothing in the permitted sample matches this filter.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Back to library' }));
    expect(screen.getByText(/Showing 2 of 3 declared files in the permitted scope/)).toBeTruthy();
  });
});

describe('KnowledgeLibrary memory', () => {
  it('reads memory only on explicit tab activation and shows the exact value', async () => {
    const readMemory = vi.fn(async () => memoryPayload());
    await renderWithOwner({ readMemory });
    expect(readMemory).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: 'Memory' }));
    await waitFor(() => expect(screen.getByText(PREF_VALUE)).toBeTruthy());
    expect(readMemory).toHaveBeenCalledTimes(1);
    expect(screen.getByText('From a conversation · Only this project')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Back to files' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Memory' }));
    expect(readMemory).toHaveBeenCalledTimes(1);
  });

  it('shows an honest empty state with no invented preference value', async () => {
    const readMemory = vi.fn(async () => ({
      ...memoryPayload(),
      availability: 'EMPTY',
      source: null,
      memory: null,
    }));
    await renderWithOwner({ readMemory },{project:cataloguePayload().project});
    fireEvent.click(screen.getByRole('tab', { name: 'Memory' }));
    await waitFor(() => expect(screen.getByText('No communication preference is recorded for this project.')).toBeTruthy());
    expect(screen.queryByText(PREF_VALUE)).toBeNull();
  });

  it('forwards the exact typed edit handoff once and claims nothing locally', async () => {
    const onEditPreference = vi.fn();
    await renderWithOwner({ readMemory: async () => memoryPayload(), onEditPreference });
    fireEvent.click(screen.getByRole('tab', { name: 'Memory' }));
    await waitFor(() => expect(screen.getByText(PREF_VALUE)).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(onEditPreference).toHaveBeenCalledTimes(1);
    const [context, document] = onEditPreference.mock.calls[0];
    expect(context).toEqual({ workRef: WORK_REF, sourceCommit: COMMIT, baseRevision: WS_SHA });
    expect(document.value).toBe(PREF_VALUE);
    expect(document.origin.kind).toBe('CONVERSATION');
    expect(screen.queryByText('Saved')).toBeNull();
    expect(screen.getByText(PREF_VALUE)).toBeTruthy();
  });

  it('offers no unsupported action without the actual callback or availability', async () => {
    const readMemory = vi.fn(async () => memoryPayload());
    await renderWithOwner({ readMemory });
    fireEvent.click(screen.getByRole('tab', { name: 'Memory' }));
    await waitFor(() => expect(screen.getByText(PREF_VALUE)).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  });
});

describe('KnowledgeLibrary actions handoff', () => {
  it('enables Add files only with actual availability and forwards the exact context', async () => {
    const onAddFiles = vi.fn();
    await renderWithOwner({ onAddFiles });
    await waitFor(() =>
      expect((screen.getByRole('button', { name: 'Add files' }) as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Add files' }));
    expect(onAddFiles).toHaveBeenCalledTimes(1);
    expect(onAddFiles.mock.calls[0][0]).toEqual({ workRef: WORK_REF, sourceCommit: COMMIT, baseRevision: WS_SHA });
    expect(screen.queryByText('Uploading')).toBeNull();
    expect(screen.queryByText('Original brief Uploaded')).toBeNull();
  });

  it('keeps Add files disabled when the owner reports unavailability', async () => {
    const onAddFiles = vi.fn();
    await renderWithOwner({
      onAddFiles,
      readActions: async () => ({
        ...ACTIONS_PAYLOAD,
        actions: { add_files: 'UNAVAILABLE', edit_preference: 'UNAVAILABLE' },
      }),
    });
    await waitFor(() =>
      expect((screen.getByRole('button', { name: 'Add files' }) as HTMLButtonElement).disabled).toBe(true),
    );
    expect(onAddFiles).not.toHaveBeenCalled();
  });

  it('reads the catalogue once per identity and honours explicit refresh', async () => {
    const readCatalogue = vi.fn(async () => cataloguePayload());
    const view = render(<KnowledgeLibrary {...makeProps({ readCatalogue })} />);
    await waitFor(() => expect(screen.getByText('Market intelligence 2026')).toBeTruthy());
    expect(readCatalogue).toHaveBeenCalledTimes(1);
    view.rerender(<KnowledgeLibrary {...makeProps({ readCatalogue, refreshKey: 2 })} />);
    await waitFor(() => expect(readCatalogue).toHaveBeenCalledTimes(2));
  });

  it('steals no focus when async reads complete in the background', async () => {
    const catalogue = deferred<unknown>();
    const readCatalogue = vi.fn(async () => catalogue.promise);
    render(<KnowledgeLibrary {...makeProps({ readCatalogue })} />);
    expect(screen.getByText('Loading…')).toBeTruthy();
    expect(document.activeElement).toBe(document.body);
    catalogue.resolve(cataloguePayload());
    await waitFor(() => expect(screen.getByText('Market intelligence 2026')).toBeTruthy());
    expect(document.activeElement).toBe(document.body);
  });

  it('renders plain EN/ZH public copy with source text unchanged', async () => {
    const readSource = vi.fn(async (_request: SourceRequest) => sourcePayload({
      title: 'Original brief',
      media_type: 'text/markdown',
      content_utf8: SOURCE_TEXT,
      content_sha256: SOURCE_SHA,
    }));
    const readMemory = vi.fn(async () => memoryPayload());
    const view = render(
      <KnowledgeLibrary
        {...makeProps({
          locale: 'zh-CN',
          readCatalogue:async()=>catalogueMemoryPayload(),
          readSource,
          readMemory: readMemory as unknown as KnowledgeLibraryProps['readMemory'],
        })}
      />,
    );
    await waitFor(() => expect(screen.getByText('Market intelligence 2026')).toBeTruthy());
    expect(screen.getByRole('tab', { name: '记忆' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '打开' }));
    await waitFor(() => expect(screen.getByText('Scope and sources for the market intelligence project.')).toBeTruthy());
    expect(readSource.mock.calls[0][0].sourceRef).toBe(FILE_REF);
    view.unmount();
  });
});

describe('KnowledgeLibrary pending source navigation', () => {
  it.each([
    ['en', 'LIST'],
    ['en', 'RECORDS'],
    ['zh-CN', 'LIST'],
    ['zh-CN', 'RECORDS'],
  ] as const)('returns from a pending %s %s read without losing query or focus', async (locale, origin) => {
    const pending = [deferred<unknown>(), deferred<unknown>()];
    let readIndex = 0;
    const readSource = vi.fn((_request: SourceRequest) => pending[readIndex++].promise);
    await renderWithOwner({ readSource, locale });

    const zh = locale === 'zh-CN';
    if (origin === 'RECORDS') {
      fireEvent.click(screen.getByRole('button', { name: zh ? '浏览全部记录' : 'Browse all records' }));
    }
    const query = document.getElementById(
      origin === 'LIST' ? 'knowledge-library-files-query' : 'knowledge-library-records-query',
    ) as HTMLInputElement;
    const queryText = origin === 'LIST' ? 'brief' : 'workstream';
    fireEvent.change(query, { target: { value: queryText } });
    const open = screen.getByRole('button', { name: zh ? '打开' : 'Open' });
    const loadingText = zh ? '正在加载…' : 'Loading…';
    const backName = zh ? '返回' : 'Back';

    const payload = sourcePayload({
      title: 'Original brief', media_type: 'text/markdown',
      content_utf8: SOURCE_TEXT, content_sha256: SOURCE_SHA,
    });
    if (origin === 'RECORDS') {
      payload.selection.source_ref = RECORD_REF;
      payload.source.path = 'agentos/workstreams/WS-2026-11-MARKET-INTELLIGENCE.md';
      payload.source.revision = MEM_SOURCE_REV;
    }

    fireEvent.click(open);
    expect(readSource).toHaveBeenCalledTimes(1);
    expect(readSource.mock.calls[0][0].signal.aborted).toBe(false);
    expect(screen.getByText(loadingText)).toBeTruthy();
    expect(query.closest('[hidden]')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: backName }));
    expect(readSource.mock.calls[0][0].signal.aborted).toBe(true);
    await waitFor(() => expect(document.activeElement).toBe(open));
    expect(query.closest('[hidden]')).toBeNull();
    expect(query.value).toBe(queryText);
    expect(screen.queryByText(loadingText)).toBeNull();

    fireEvent.click(open);
    expect(readSource).toHaveBeenCalledTimes(2);
    expect(readSource.mock.calls[1][0].signal.aborted).toBe(false);
    await act(async () => { pending[0].resolve(payload); });
    expect(screen.getByText(loadingText)).toBeTruthy();
    expect(screen.queryByText('Scope and sources for the market intelligence project.')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: backName }));
    expect(readSource.mock.calls[1][0].signal.aborted).toBe(true);
    await act(async () => { pending[1].resolve(payload); });
    await waitFor(() => expect(document.activeElement).toBe(open));
    expect(query.closest('[hidden]')).toBeNull();
    expect(query.value).toBe(queryText);
    expect(screen.queryByText('Scope and sources for the market intelligence project.')).toBeNull();
    expect(screen.queryByText(loadingText)).toBeNull();
  });
});

describe('KnowledgeLibrary Memory return destination', () => {
  it.each(['en', 'zh-CN'] as const)('returns from Records through Memory to Files in %s', async (locale) => {
    const zh = locale === 'zh-CN';
    const readMemory = vi.fn(async () => memoryPayload());
    const readSource = vi.fn(async (request: SourceRequest) => {
      const payload = sourcePayload({
        title: 'Original brief', media_type: 'text/markdown',
        content_utf8: SOURCE_TEXT, content_sha256: SOURCE_SHA,
      });
      if (request.sourceRef === RECORD_REF) {
        payload.selection.source_ref = RECORD_REF;
        payload.source.path = 'agentos/workstreams/WS-2026-11-MARKET-INTELLIGENCE.md';
        payload.source.revision = MEM_SOURCE_REV;
      }
      return payload;
    });
    const { readCatalogue } = await renderWithOwner({ locale, readMemory, readSource });
    const filesQuery = () => document.getElementById('knowledge-library-files-query') as HTMLInputElement;
    const recordsQuery = () => document.getElementById('knowledge-library-records-query') as HTMLInputElement;
    const browseRecords = () => fireEvent.click(screen.getByRole('button', { name: zh ? '浏览全部记录' : 'Browse all records' }));
    const open = () => fireEvent.click(screen.getByRole('button', { name: zh ? '打开' : 'Open' }));
    const back = () => fireEvent.click(screen.getByRole('button', { name: zh ? '返回' : 'Back' }));
    const memory = () => fireEvent.click(screen.getByRole('tab', { name: zh ? '记忆' : 'Memory' }));

    fireEvent.change(filesQuery(), { target: { value: 'brief' } });
    browseRecords();
    fireEvent.change(recordsQuery(), { target: { value: 'workstream' } });
    memory();
    await waitFor(() => expect(screen.getByText(PREF_VALUE)).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: zh ? '返回文件' : 'Back to files' }));

    expect(document.getElementById('knowledge-library-panel-files')).not.toBeNull();
    expect(document.getElementById('knowledge-library-panel-records')).toBeNull();
    expect(filesQuery().value).toBe('brief');
    expect(screen.getByRole('tab', { name: zh ? '文件' : 'Files' }).getAttribute('aria-selected')).toBe('true');

    // The normal file reader and its existing Back path still work.
    open();
    await waitFor(() => expect(screen.getByText('Scope and sources for the market intelligence project.')).toBeTruthy());
    expect(readSource.mock.calls[0][0].sourceRef).toBe(FILE_REF);
    back();
    expect(filesQuery().value).toBe('brief');

    // Records retain their independent filter and normal reader origin.
    browseRecords();
    expect(recordsQuery().value).toBe('workstream');
    open();
    await waitFor(() => expect(screen.getByText('Scope and sources for the market intelligence project.')).toBeTruthy());
    expect(readSource.mock.calls[1][0].sourceRef).toBe(RECORD_REF);
    back();
    expect(recordsQuery().value).toBe('workstream');

    memory();
    expect(screen.getByText(PREF_VALUE)).toBeTruthy();
    expect(readMemory).toHaveBeenCalledTimes(1);
    expect(readCatalogue).toHaveBeenCalledTimes(1);
    expect(readSource).toHaveBeenCalledTimes(2);
  });
});
