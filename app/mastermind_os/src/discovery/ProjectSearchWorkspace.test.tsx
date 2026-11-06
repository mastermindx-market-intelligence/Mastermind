// @vitest-environment jsdom
/**
 * ProjectSearchWorkspace tests — Vitest + jsdom, synthetic fixtures.
 *
 * SCOPE LIMITATION (recorded honestly for the parent reviewer):
 *  - The imported composers `searchSavedConversations` / `searchProjectFiles`
 *    are replaced here with CONTRACT-FAITHFUL FIXTURES through vi.mock, only
 *    so UI state, focus, pagination and late-await behaviour can be checked in
 *    isolation. They are NOT the real producers, nothing here claims live
 *    auth, provider, source or file access, and no result is presented as a
 *    live read.
 *  - The parent's unmocked producer path joins separately, together with the
 *    parent's strict DTO decoders, the exact-match/source re-read validator,
 *    the real owner/App wiring and the rendered browser matrix. Passing here
 *    grants no business acceptance and creates no new authority.
 */

import { useLayoutEffect, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectSearchWorkspace } from './ProjectSearchWorkspace';
import type { SavedConversationMatch, SavedConversationSearchOwner, SavedConversationSearchResult } from './saved-conversations';
import type { ProjectFileMatch, ProjectFileSearchOwner, ProjectFileSearchResult } from './project-file-search';

/* -------------------------------------------------------------------------
 * Composer fixtures (mocked imports — see scope limitation above).
 * ---------------------------------------------------------------------- */

const harness = vi.hoisted(() => {
  type Impl = (request: any, owner: any) => Promise<any>;
  return {
    saved: null as Impl | null,
    files: null as Impl | null,
    savedCalls: [] as Array<{ request: any; owner: any }>,
    filesCalls: [] as Array<{ request: any; owner: any }>,
    reset() {
      this.saved = null;
      this.files = null;
      this.savedCalls = [];
      this.filesCalls = [];
    },
  };
});

vi.mock('./saved-conversations', () => ({
  searchSavedConversations: (request: unknown, owner: unknown) => {
    harness.savedCalls.push({ request, owner });
    if (!harness.saved) {
      return Promise.reject(new Error('saved composer fixture not installed'));
    }
    return harness.saved(request, owner);
  },
}));

vi.mock('./project-file-search', () => ({
  searchProjectFiles: (request: unknown, owner: unknown) => {
    harness.filesCalls.push({ request, owner });
    if (!harness.files) {
      return Promise.reject(new Error('file composer fixture not installed'));
    }
    return harness.files(request, owner);
  },
}));

/* -------------------------------------------------------------------------
 * Synthetic contract payloads.
 * ---------------------------------------------------------------------- */

function savedMatch(index: number, workRef = 'WS:ONE'): SavedConversationMatch {
  return {
    reference: {
      read_ref: `read-ref-${index}`,
      operation_key: `op-${index}`,
      request_ref: `request-ref-${index}`,
      request_event_id: 400 + index,
      request_revision: 'revision-7',
      requested_at: `2026-11-03T10:0${index}:00Z`,
      work_ref: workRef,
      root_job_id: `root-job-${index}`,
      target_ref: `target-${index}`,
      reference_only: true,
    },
    excerpt: `节选 ${index}: returned excerpt is rendered verbatim`,
    sourceTextSha256: `sha-${index}`,
  } as unknown as SavedConversationMatch;
}

function fileMatch(index: number): ProjectFileMatch {
  return {
    sourceRef: `source-${index}`,
    expectedRevision: 'revision-7',
    displayName: `report-${index}.md`,
    excerpt: `excerpt ${index}: exact body slice`,
    sourceTextSha256: `sha-${index}`,
    source: {
      repository: 'mastermindx-market-intelligence/macro',
      commit: 'commit-a',
      path: `docs/report-${index}.md`,
      revision: 'revision-7',
      content_sha256: `content-sha-${index}`,
      committed_at: '2026-11-01T00:00:00Z',
    },
  } as unknown as ProjectFileMatch;
}

type SavedCoverageOverride = Partial<{
  status: 'COMPLETE' | 'PARTIAL';
  scanned: number;
  matched: number;
  unavailable: number;
  nextCursor: string | null;
  highWater: number | null;
}>;

type FilesCoverageOverride = Partial<{
  status: 'COMPLETE' | 'PARTIAL';
  declared: number;
  listed: number;
  scanned: number;
  matched: number;
  unavailable: number;
  nextPageStart: number | null;
}>;

function savedResult(
  items: SavedConversationMatch[],
  coverage: SavedCoverageOverride = {},
  query = 'needle',
  workRef = 'WS:ONE',
): SavedConversationSearchResult {
  return {
    state: 'AVAILABLE',
    reason: null,
    workRef,
    query,
    scope: 'SAVED_CONVERSATIONS_IN_PROJECT',
    items,
    coverage: {
      status: 'COMPLETE',
      scanned: items.length,
      matched: items.length,
      unavailable: 0,
      nextCursor: null,
      highWater: 42,
      ...coverage,
    },
  } as unknown as SavedConversationSearchResult;
}

function fileResult(
  items: ProjectFileMatch[],
  coverage: FilesCoverageOverride = {},
  query = 'needle',
  sourceCommit: string | null = 'commit-a',
  workRef = 'WS:ONE',
): ProjectFileSearchResult {
  return {
    state: 'AVAILABLE',
    reason: null,
    workRef,
    query,
    scope: 'CANONICAL_PROJECT_FILES',
    sourceCommit,
    items,
    coverage: {
      status: 'COMPLETE',
      declared: items.length,
      listed: items.length,
      scanned: items.length,
      matched: items.length,
      unavailable: 0,
      nextPageStart: null,
      ...coverage,
    },
  } as unknown as ProjectFileSearchResult;
}

function savedOwnerFixture(
  context: { principalScope: string; generation: string } | null = { principalScope: 'scope-a', generation: 'gen-1' },
  auth = 11,
): SavedConversationSearchOwner {
  return {
    context: () => (context ? { ...context } : null),
    authGeneration: () => auth,
    readReferences: () => {
      throw new Error('not reachable from this UI');
    },
    readAnswer: () => {
      throw new Error('not reachable from this UI');
    },
  } as unknown as SavedConversationSearchOwner;
}

function filesOwnerFixture(
  context: { principalScope: string; generation: string } | null = { principalScope: 'scope-a', generation: 'gen-1' },
  auth = 11,
): ProjectFileSearchOwner {
  return {
    context: () => (context ? { ...context } : null),
    authGeneration: () => auth,
    readCatalogue: () => {
      throw new Error('not reachable from this UI');
    },
    readSource: () => {
      throw new Error('not reachable from this UI');
    },
  } as unknown as ProjectFileSearchOwner;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/* -------------------------------------------------------------------------
 * Render helpers.
 * ---------------------------------------------------------------------- */

interface RenderArgs {
  workRef?: string | null;
  authGeneration?: number;
  hostGeneration?: string | number | null;
  locale?: 'en' | 'zh-CN';
  theme?: 'dark' | 'light';
  sessionHistory?: SavedConversationSearchOwner;
  projectFiles?: ProjectFileSearchOwner;
  onOpenSaved?: (match: SavedConversationMatch) => void;
  onOpenFile?: (match: ProjectFileMatch) => void;
}

function renderWorkspace(args: RenderArgs = {}) {
  const view = render(
    <ProjectSearchWorkspace
      workRef={args.workRef === undefined ? 'WS:ONE' : args.workRef}
      authGeneration={args.authGeneration === undefined ? 11 : args.authGeneration}
      hostGeneration={args.hostGeneration === undefined ? 'host-1' : args.hostGeneration}
      locale={args.locale}
      theme={args.theme}
      sessionHistory={'sessionHistory' in args ? args.sessionHistory : savedOwnerFixture()}
      projectFiles={'projectFiles' in args ? args.projectFiles : filesOwnerFixture()}
      onOpenSaved={args.onOpenSaved}
      onOpenFile={args.onOpenFile}
    />,
  );
  const queryInput = () => document.getElementById('project-search-query') as HTMLInputElement;
  const form = () => view.container.querySelector('form') as HTMLFormElement;
  const submitSearch = () => fireEvent.submit(form());
  const typeQuery = (value: string) => fireEvent.change(queryInput(), { target: { value } });
  const filterButton = (label: string) => screen.getByRole('button', { name: label });
  return { view, queryInput, form, submitSearch, typeQuery, filterButton };
}

function flush() {
  return act(async () => {
    await Promise.resolve();
  });
}

/** Parent-side probe: reads the committed DOM inside a layout effect on every
 * commit, i.e. after commit but strictly BEFORE passive effects and paint. */
function DomProbe({ seen, children }: { seen: string[]; children: any }) {
  const host = useRef<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    seen.push(host.current ? (host.current.textContent ?? '') : '');
  });
  return <div ref={host}>{children}</div>;
}

beforeEach(() => {
  harness.reset();
});

afterEach(() => {
  cleanup();
});

/* -------------------------------------------------------------------------
 * Checks.
 * ---------------------------------------------------------------------- */

describe('ProjectSearchWorkspace', () => {
  it('performs no read on mount — search happens only on explicit submit', async () => {
    const filesResult = fileResult([fileMatch(0)]);
    harness.files = () => Promise.resolve(filesResult);
    const { submitSearch, typeQuery } = renderWorkspace();

    expect(harness.filesCalls).toHaveLength(0);
    expect(harness.savedCalls).toHaveLength(0);
    await flush();
    expect(harness.filesCalls).toHaveLength(0);
    expect(harness.savedCalls).toHaveLength(0);

    typeQuery('needle');
    await flush();
    expect(harness.filesCalls).toHaveLength(0);

    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(1);
    expect(harness.savedCalls).toHaveLength(0);
  });

  it('calls the chosen composer once with the exact bounded request and owner', async () => {
    const match = fileMatch(0);
    harness.files = () => Promise.resolve(fileResult([match]));
    const owner = filesOwnerFixture();
    const { submitSearch, typeQuery } = renderWorkspace({ projectFiles: owner });

    typeQuery('needle');
    submitSearch();
    await flush();

    expect(harness.filesCalls).toHaveLength(1);
    const call = harness.filesCalls[0];
    expect(call.request.workRef).toBe('WS:ONE');
    expect(call.request.query).toBe('needle');
    expect(call.request.signal).toBeInstanceOf(AbortSignal);
    expect(Object.prototype.hasOwnProperty.call(call.request, 'pageStart')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(call.request, 'expectedCommit')).toBe(false);
    expect(call.owner).toBe(owner);
    expect(screen.getByText('report-0.md')).toBeTruthy();
  });

  it('files: Next page sends the exact pageStart plus expectedCommit from the last result', async () => {
    harness.files = (request: any) =>
      Promise.resolve(
        request.pageStart === 4
          ? fileResult([fileMatch(4)], {
              declared: 8,
              listed: 8,
              scanned: 4,
              matched: 1,
              nextPageStart: null,
            })
          : fileResult([fileMatch(0), fileMatch(1)], {
              declared: 8,
              listed: 8,
              scanned: 4,
              matched: 2,
              nextPageStart: 4,
            }),
      );
    const { submitSearch, typeQuery, view } = renderWorkspace();
    typeQuery('needle');
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await flush();

    expect(harness.filesCalls).toHaveLength(2);
    const second = harness.filesCalls[1].request;
    expect(second.query).toBe('needle');
    expect(second.workRef).toBe('WS:ONE');
    expect(second.pageStart).toBe(4);
    expect(second.expectedCommit).toBe('commit-a');
    expect(view.container.textContent).toContain('report-4.md');
  });

  it('saved conversations: Next page sends the exact saved cursor plus expectedHighWater', async () => {
    harness.saved = (request: any) => {
      if (request.cursor === 'cursor-3') {
        return Promise.resolve(
          savedResult([savedMatch(5)], { scanned: 4, matched: 1, nextCursor: null, highWater: null }),
        );
      }
      if (request.cursor === 'cursor-2') {
        return Promise.resolve(
          savedResult([savedMatch(2), savedMatch(3)], {
            scanned: 4,
            matched: 2,
            nextCursor: 'cursor-3',
            highWater: null,
          }),
        );
      }
      return Promise.resolve(
        savedResult([savedMatch(0), savedMatch(1)], {
          scanned: 4,
          matched: 2,
          nextCursor: 'cursor-2',
          highWater: 42,
        }),
      );
    };
    const { submitSearch, typeQuery, filterButton } = renderWorkspace();
    fireEvent.click(filterButton('Saved conversations'));
    typeQuery('needle');
    submitSearch();
    await flush();

    const first = harness.savedCalls[0].request;
    expect(Object.prototype.hasOwnProperty.call(first, 'cursor')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(first, 'expectedHighWater')).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await flush();

    expect(harness.savedCalls).toHaveLength(2);
    const second = harness.savedCalls[1].request;
    expect(second.cursor).toBe('cursor-2');
    expect(second.expectedHighWater).toBe(42);
    expect(second.query).toBe('needle');

    // A page without a reported watermark must not invent one.
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await flush();
    expect(harness.savedCalls).toHaveLength(3);
    const third = harness.savedCalls[2].request;
    expect(third.cursor).toBe('cursor-3');
    expect(Object.prototype.hasOwnProperty.call(third, 'expectedHighWater')).toBe(false);
  });

  it('missing source owner: truthful local-unavailable, no enabled unsupported action, no read', async () => {
    const { filterButton, submitSearch, typeQuery, view } = renderWorkspace({ sessionHistory: undefined });
    fireEvent.click(filterButton('Saved conversations'));
    await flush();

    expect(view.container.textContent).toContain('Saved conversation search is unavailable in this view.');
    expect(screen.getByRole('button', { name: 'Search' }).hasAttribute('disabled')).toBe(true);
    typeQuery('needle');
    submitSearch();
    await flush();
    expect(harness.savedCalls).toHaveLength(0);
    expect(harness.filesCalls).toHaveLength(0);
  });

  it('missing work or host generation: truthful local-unavailable for both sources', async () => {
    const { view, submitSearch, typeQuery } = renderWorkspace({ workRef: null });
    expect(view.container.textContent).toContain('Search is unavailable in this view.');
    typeQuery('needle');
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(0);
    expect(harness.savedCalls).toHaveLength(0);

    cleanup();
    const other = renderWorkspace({ hostGeneration: null });
    expect(other.view.container.textContent).toContain('Search is unavailable in this view.');
  });

  it('renders exact returned excerpt, requested_at and the Saved reply label; raw ids only inside closed details', async () => {
    const match = savedMatch(1);
    harness.saved = () => Promise.resolve(savedResult([match]));
    const { submitSearch, typeQuery, filterButton, view } = renderWorkspace();

    fireEvent.click(filterButton('Saved conversations'));
    typeQuery('needle');
    submitSearch();
    await flush();

    expect(screen.getByText('Saved reply')).toBeTruthy();
    expect(view.container.textContent).toContain('2026-11-03T10:01:00Z');
    expect(view.container.textContent).toContain('节选 1: returned excerpt is rendered verbatim');
    const details = view.container.querySelector('details') as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    expect(details.textContent).toContain('root-job-1');
    expect(details.textContent).toContain('read-ref-1');
    const summaryText = details.querySelector('summary')?.textContent ?? '';
    expect(summaryText.includes('root-job-1')).toBe(false);
    // No invented title, author, created time or global claim.
    expect(view.container.textContent).not.toContain('匹配生成');
    expect(view.container.textContent).not.toContain('Generated title');
  });

  it('mobile/narrow behaviour: full preview appears only after explicit Inspect, once', async () => {
    const match = fileMatch(0);
    harness.files = () => Promise.resolve(fileResult([match]));
    const { submitSearch, typeQuery, view } = renderWorkspace();
    typeQuery('needle');
    submitSearch();
    await flush();

    const preview = view.container.querySelector('.project-search__preview') as HTMLElement;
    expect(preview).toBeTruthy();
    expect(preview.hasAttribute('hidden')).toBe(true);
    expect(view.container.querySelectorAll('.project-search__preview')).toHaveLength(1);
    // One content-owned h1, preview heading is a separate h2.
    expect(view.container.querySelectorAll('h1')).toHaveLength(1);
    expect(view.container.querySelector('h1')?.textContent).toBe('Search');
    expect(view.container.querySelector('.project-search__previewTitle')?.textContent).toBe('Selected match');

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }));
    await flush();

    expect(preview.hasAttribute('hidden')).toBe(false);
    expect(view.container.querySelectorAll('.project-search__previewBody')).toHaveLength(1);
    expect(preview.textContent).toContain('excerpt 0: exact body slice');
    // No per-row stacked preview: the only preview is the single quiet panel.
    expect(view.container.querySelectorAll('.project-search__row .project-search__preview')).toHaveLength(0);
  });

  it('Open forwards the exact owned match object from the current displayed result', async () => {
    const match = savedMatch(2);
    const openSaved = vi.fn();
    harness.saved = () => Promise.resolve(savedResult([match], {}, 'needle'));
    const { submitSearch, typeQuery, filterButton } = renderWorkspace({ onOpenSaved: openSaved });

    fireEvent.click(filterButton('Saved conversations'));
    typeQuery('needle');
    submitSearch();
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    expect(openSaved).toHaveBeenCalledTimes(1);
    expect(openSaved.mock.calls[0][0]).toBe(match);
    expect(openSaved.mock.calls[0][1]).toEqual({expectedHighWater:42});
    // No route, path or id guessing: the exact object identity is handed over.
    expect(openSaved.mock.calls[0][0].reference.read_ref).toBe('read-ref-2');
  });

  it('A-B-A over auth generation, host 1 vs "1" and owner context: private DOM is cleared before passive effects and late results never render', async () => {
    const first = savedResult([savedMatch(0)]);
    const late = savedResult([savedMatch(9)]);
    const firstGate = deferred<SavedConversationSearchResult>();
    let call = 0;
    harness.saved = () => {
      call += 1;
      return call === 1 ? Promise.resolve(first) : firstGate.promise;
    };
    const owner = savedOwnerFixture({ principalScope: 'scope-a', generation: 'gen-1' }, 11);
    const seen: string[] = [];

    const probe = render(
      <DomProbe seen={seen}>
        <ProjectSearchWorkspace
          workRef="WS:ONE"
          authGeneration={11}
          hostGeneration={1}
          sessionHistory={owner}
          projectFiles={filesOwnerFixture()}
        />
      </DomProbe>,
    );

    fireEvent.change(document.getElementById('project-search-query') as HTMLInputElement, {
      target: { value: 'needle' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Saved conversations' }));
    fireEvent.submit(probe.container.querySelector('form') as HTMLFormElement);
    await flush();
    // The probe records only on its own commits; the result commit is checked
    // directly, and each identity change below adds one probe entry.
    expect(probe.container.textContent.includes('节选 0')).toBe(true);
    expect(seen).toHaveLength(1);

    // A -> B: same work ref and owner object, different auth generation.
    probe.rerender(
      <DomProbe seen={seen}>
        <ProjectSearchWorkspace
          workRef="WS:ONE"
          authGeneration={12}
          hostGeneration={1}
          sessionHistory={owner}
          projectFiles={filesOwnerFixture()}
        />
      </DomProbe>,
    );
    // Observed during the commit, before passive effects: old private content gone.
    expect(seen).toHaveLength(2);
    expect(seen[seen.length - 1].includes('节选 0')).toBe(false);

    // B -> A (back to the original identity): still cleared, no stale revival.
    probe.rerender(
      <DomProbe seen={seen}>
        <ProjectSearchWorkspace
          workRef="WS:ONE"
          authGeneration={11}
          hostGeneration={1}
          sessionHistory={owner}
          projectFiles={filesOwnerFixture()}
        />
      </DomProbe>,
    );
    expect(seen).toHaveLength(3);
    expect(seen[seen.length - 1].includes('节选 0')).toBe(false);

    // Host generation 1 vs '1' is a distinct identity, not a silent match.
    probe.rerender(
      <DomProbe seen={seen}>
        <ProjectSearchWorkspace
          workRef="WS:ONE"
          authGeneration={11}
          hostGeneration={'1'}
          sessionHistory={owner}
          projectFiles={filesOwnerFixture()}
        />
      </DomProbe>,
    );
    expect(seen).toHaveLength(4);
    expect(seen[seen.length - 1].includes('节选 0')).toBe(false);
    expect(probe.container.textContent.includes('节选 0')).toBe(false);

    // A fresh read under the current identity, held open by the fixture gate.
    fireEvent.change(document.getElementById('project-search-query') as HTMLInputElement, {
      target: { value: 'needle' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Saved conversations' }));
    fireEvent.submit(probe.container.querySelector('form') as HTMLFormElement);
    await flush();
    expect(harness.savedCalls).toHaveLength(2);
    expect(probe.container.textContent.includes('节选 9')).toBe(false);

    // Late auth change while that read is in flight.
    probe.rerender(
      <DomProbe seen={seen}>
        <ProjectSearchWorkspace
          workRef="WS:ONE"
          authGeneration={12}
          hostGeneration={1}
          sessionHistory={owner}
          projectFiles={filesOwnerFixture()}
        />
      </DomProbe>,
    );
    expect(seen).toHaveLength(5);

    // The read resolves after the identity change: it may not render anywhere,
    // even though the fixture ignores the abort signal.
    await act(async () => {
      firstGate.resolve(late);
      await firstGate.promise;
    });
    expect(probe.container.textContent.includes('节选 9')).toBe(false);
    expect(probe.container.textContent.includes('节选 0')).toBe(false);
    expect(harness.savedCalls).toHaveLength(2);
  });

  it('editing the query aborts the pending read and clears the slate; the late result never renders', async () => {
    const gate = deferred<ProjectFileSearchResult>();
    harness.files = () => gate.promise;
    const { submitSearch, typeQuery, view } = renderWorkspace();

    typeQuery('needle');
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(1);

    typeQuery('needle two');
    expect(view.container.textContent).not.toContain('report-0.md');

    await act(async () => {
      gate.resolve(fileResult([fileMatch(0)]));
      await gate.promise;
    });
    expect(view.container.textContent).not.toContain('report-0.md');
    expect(view.container.textContent).not.toContain('excerpt 0');
    expect(harness.filesCalls).toHaveLength(1);
  });

  it('switching the source filter clears the slate content without any new read', async () => {
    harness.files = () => Promise.resolve(fileResult([fileMatch(0)]));
    const { submitSearch, typeQuery, filterButton, view } = renderWorkspace();

    typeQuery('needle');
    submitSearch();
    await flush();
    expect(view.container.textContent).toContain('report-0.md');

    fireEvent.click(filterButton('Saved conversations'));
    expect(view.container.textContent).not.toContain('report-0.md');
    expect(view.container.textContent).not.toContain('excerpt 0');
    await flush();
    expect(harness.savedCalls).toHaveLength(0);
    expect(harness.filesCalls).toHaveLength(1);
  });

  it('does not steal focus and announces loading through the polite status region', async () => {
    const gate = deferred<ProjectFileSearchResult>();
    harness.files = () => gate.promise;
    const { submitSearch, typeQuery, queryInput } = renderWorkspace();

    typeQuery('needle');
    const input = queryInput();
    input.focus();
    submitSearch();
    await flush();
    const status = document.querySelector('.project-search__status');
    expect(status?.getAttribute('aria-live')).toBe('polite');
    expect(status?.textContent).toContain('Searching');

    await act(async () => {
      gate.resolve(fileResult([fileMatch(0)]));
      await gate.promise;
    });
    expect(document.activeElement).toBe(input);
    expect(document.querySelector('.project-search__preview')?.hasAttribute('hidden')).toBe(true);
  });

  it('ignores submit while an IME composition is active, then submits on the real submit', async () => {
    harness.files = () => Promise.resolve(fileResult([fileMatch(0)]));
    const { submitSearch, typeQuery, queryInput } = renderWorkspace();

    const input = queryInput();
    fireEvent.compositionStart(input);
    typeQuery('needle');
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(0);

    fireEvent.compositionEnd(input);
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(1);
  });

  it('preserves the literal query, filter and selection across locale and theme changes; source text stays verbatim', async () => {
    const match = savedMatch(3);
    harness.saved = () => Promise.resolve(savedResult([match], {}, '检索词'));
    const args: RenderArgs = {
      locale: 'en',
      theme: 'dark',
      sessionHistory: savedOwnerFixture(),
      projectFiles: filesOwnerFixture(),
    };
    const first = renderWorkspace(args);
    fireEvent.click(first.filterButton('Saved conversations'));
    first.typeQuery('检索词');
    first.submitSearch();
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Inspect' }));
    const excerpt = '节选 3: returned excerpt is rendered verbatim';
    expect(first.view.container.textContent).toContain(excerpt);
    expect(first.queryInput().value).toBe('检索词');

    first.view.rerender(
      <ProjectSearchWorkspace
        workRef="WS:ONE"
        authGeneration={11}
        hostGeneration="host-1"
        locale="zh-CN"
        theme="light"
        sessionHistory={args.sessionHistory}
        projectFiles={args.projectFiles}
      />,
    );
    expect(first.queryInput().value).toBe('检索词');
    expect(screen.getByRole('button', { name: '已保存的对话' }).getAttribute('aria-pressed')).toBe('true');
    expect(first.view.container.textContent).toContain(excerpt);
    expect(first.view.container.textContent).toContain('2026-11-03T10:03:00Z');
    expect(first.view.container.querySelector('h1')?.textContent).toBe('搜索');
    expect(first.view.container.querySelectorAll('.project-search__previewBody')).toHaveLength(1);
    await flush();
    expect(harness.savedCalls).toHaveLength(1);
  });

  it('reports honest partial coverage counts with a this-page scope and no global corpus claim', async () => {
    harness.files = () =>
      Promise.resolve(
        fileResult([fileMatch(0), fileMatch(1)], {
          status: 'PARTIAL',
          declared: 40,
          listed: 12,
          scanned: 4,
          matched: 2,
          unavailable: 1,
          nextPageStart: 4,
        }),
      );
    const { submitSearch, typeQuery, view } = renderWorkspace();

    typeQuery('needle');
    submitSearch();
    await flush();

    const status = document.querySelector('.project-search__status')?.textContent ?? '';
    expect(status).toContain('This page: scanned 4 · matched 2 · unavailable 1');
    expect(status).toContain('declared 40 · listed 12');
    expect(status).toContain('Coverage is partial');
    expect(status).not.toContain('no further page');
    expect(screen.getByRole('button', { name: 'Next page' }).hasAttribute('disabled')).toBe(false);
    expect(view.container.textContent).not.toContain('all files');
    expect(view.container.textContent).not.toContain('entire project');
  });

  it('surfaces composer UNAVAILABLE reasons truthfully without enabling paging or rows', async () => {
    harness.files = () => Promise.resolve({ ...fileResult([]), state: 'UNAVAILABLE', reason: 'SOURCE_CHANGED' } as unknown as ProjectFileSearchResult);
    const { submitSearch, typeQuery, view } = renderWorkspace();

    typeQuery('needle');
    submitSearch();
    await flush();

    expect(view.container.textContent).toContain('The source changed since this view loaded.');
    expect(view.container.querySelector('.project-search__row')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull();
    expect(harness.filesCalls).toHaveLength(1);
  });

  it('missing Open callback disables Open; a throwing callback is a fixed local-unavailable with no source text', async () => {
    const match = savedMatch(4);
    harness.saved = () => Promise.resolve(savedResult([match]));

    const withoutCallback = renderWorkspace({ sessionHistory: savedOwnerFixture(), projectFiles: undefined });
    fireEvent.click(withoutCallback.filterButton('Saved conversations'));
    withoutCallback.typeQuery('needle');
    withoutCallback.submitSearch();
    await flush();
    expect(screen.getByRole('button', { name: 'Open' }).hasAttribute('disabled')).toBe(true);

    cleanup();
    const throwing = vi.fn(() => {
      throw new Error('secret pipeline detail');
    });
    const withCallback = renderWorkspace({ onOpenSaved: throwing });
    fireEvent.click(withCallback.filterButton('Saved conversations'));
    withCallback.typeQuery('needle');
    withCallback.submitSearch();
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
    await flush();
    expect(throwing).toHaveBeenCalledTimes(1);
    const status = document.querySelector('.project-search__status')?.textContent ?? '';
    expect(status).toContain('Open is not available for this match.');
    expect(status.includes('secret pipeline detail')).toBe(false);
    expect(withCallback.view.container.textContent.includes('secret pipeline detail')).toBe(false);
  });

  it('caps the visible list at 8 matches and stops offering a further page at the cap', async () => {
    harness.files = (request: any) =>
      Promise.resolve(
        request.pageStart === 4
          ? fileResult([fileMatch(4), fileMatch(5), fileMatch(6), fileMatch(7)], { scanned: 4, matched: 4, nextPageStart: 8 })
          : fileResult([fileMatch(0), fileMatch(1), fileMatch(2), fileMatch(3)], { scanned: 4, matched: 4, nextPageStart: 4 }),
      );
    const { submitSearch, typeQuery, view } = renderWorkspace();
    typeQuery('needle');
    submitSearch();
    await flush();
    expect(view.container.querySelectorAll('li.project-search__row')).toHaveLength(4);

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    await flush();
    expect(view.container.querySelectorAll('li.project-search__row')).toHaveLength(8);
    expect(screen.queryByRole('button', { name: 'Next page' })).toBeNull();
  });

  it('rejects out-of-band queries without any read', async () => {
    const { submitSearch, typeQuery, queryInput, view } = renderWorkspace();

    typeQuery('x');
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(0);
    expect(view.container.textContent).toContain('Enter 2–128 characters');

    const lone = 'a\uD800b';
    typeQuery(lone);
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(0);
    expect(queryInput().value).toBe(lone);
    expect(harness.savedCalls).toHaveLength(0);
  });

  it('runs no background search after a completed result', async () => {
    harness.files = () => Promise.resolve(fileResult([fileMatch(0)]));
    const { submitSearch, typeQuery } = renderWorkspace();
    typeQuery('needle');
    submitSearch();
    await flush();
    expect(harness.filesCalls).toHaveLength(1);

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25));
    });
    expect(harness.filesCalls).toHaveLength(1);
    expect(harness.savedCalls).toHaveLength(0);
  });
  it('retains the original page cursor and high-water witness on every saved row',async()=>{
    const first=savedMatch(1),second=savedMatch(2),open=vi.fn();let call=0;
    harness.saved=()=>Promise.resolve(++call===1?savedResult([first],{nextCursor:'page-two',highWater:73}):savedResult([second],{highWater:73}));
    const view=renderWorkspace({onOpenSaved:open});fireEvent.click(view.filterButton('Saved conversations'));view.typeQuery('needle');view.submitSearch();await flush();
    fireEvent.click(screen.getByRole('button',{name:'Next page'}));await flush();
    fireEvent.click(screen.getAllByRole('button',{name:'Open'})[1]);expect(open.mock.calls[0]).toEqual([second,{pageCursor:'page-two',expectedHighWater:73}]);
    fireEvent.click(screen.getAllByRole('button',{name:'Open'})[0]);expect(open.mock.calls[1]).toEqual([first,{expectedHighWater:73}]);
  });
  it('never opens a saved match when its owner omitted the high-water witness',async()=>{
    const open=vi.fn();harness.saved=()=>Promise.resolve(savedResult([savedMatch(0)],{highWater:null}));
    const view=renderWorkspace({onOpenSaved:open});fireEvent.click(view.filterButton('Saved conversations'));view.typeQuery('needle');view.submitSearch();await flush();
    expect(screen.getByRole('button',{name:'Open'}).hasAttribute('disabled')).toBe(true);expect(open).not.toHaveBeenCalled();
  });
  it('clears private file matches on a context change of the SAME owner before passive effects',async()=>{
    let generation='one';const owner={...filesOwnerFixture(),context:()=>({generation})};const seen:string[]=[];
    harness.files=()=>Promise.resolve(fileResult([fileMatch(0)]));
    const element=()=> <DomProbe seen={seen}><ProjectSearchWorkspace workRef="WS:ONE" authGeneration={11} hostGeneration={1} projectFiles={owner}/></DomProbe>;
    const view=render(element());fireEvent.change(document.getElementById('project-search-query') as HTMLInputElement,{target:{value:'needle'}});fireEvent.submit(view.container.querySelector('form')!);await flush();
    expect(view.container.textContent).toContain('exact body slice');generation='two';view.rerender(element());
    expect(seen[seen.length-1]).not.toContain('exact body slice');
  });

  it('explicit Inspect focuses preview; Escape and Close return to its invoking result',async()=>{
    harness.saved=()=>Promise.resolve(savedResult([savedMatch(0)]));
    const view=renderWorkspace();fireEvent.click(view.filterButton('Saved conversations'));view.typeQuery('needle');view.submitSearch();await flush();
    const inspect=screen.getByRole('button',{name:'Inspect'});fireEvent.click(inspect);
    const heading=view.view.container.querySelector('.project-search__previewTitle');expect(document.activeElement).toBe(heading);
    const details=view.view.container.querySelector('.project-search__preview details') as HTMLDetailsElement;expect(details.open).toBe(false);expect(details.querySelector('dl')?.textContent).toContain('read_ref');
    expect(view.view.container.querySelector('.project-search__previewMeta')?.textContent).toContain('Request time');
    fireEvent.keyDown(heading!,{key:'Escape'});expect(document.activeElement).toBe(inspect);
    fireEvent.click(inspect);fireEvent.click(screen.getByRole('button',{name:'Close preview'}));expect(document.activeElement).toBe(inspect);
  });

});
