/**
 * Synthetic scratch tests for the bounded canonical project file search
 * composer (`searchProjectFiles`).
 *
 * These exercise the exported composer against in-memory canonical catalogue
 * and source fixtures only. They are NOT the parent's actual Python producer
 * fixture and NOT the actual App join, which remain the final acceptance
 * gates; as scratch tests they are synthetic by construction and say so.
 * No network, no filesystem, no persisted state, no timers.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  searchProjectFiles,
  type ProjectFileSearchOwner,
  type ProjectFileSearchRequest,
  type ProjectFileSearchResult,
} from './project-file-search';

const WORK_REF = 'WS:MARKETMACRO01';
const CANONICAL_REPO = 'mastermindx-market-intelligence/macro';
const COMMIT = hex40('commit-a');
const DEFAULT_COMMITTED_AT = '2026-01-01T00:00:00Z';
const encoder = new TextEncoder();

function hex40(seed: string, offset = 0): string {
  return hexOf(seed, 40, offset);
}

function hex64(seed: string, offset = 0): string {
  return hexOf(seed, 64, offset);
}

function hexOf(seed: string, length: number, offset: number): string {
  const digits = '0123456789abcdef';
  let out = '';
  for (let i = 0; i < length; i += 1) {
    const code = seed.length > 0 ? seed.charCodeAt(i % seed.length) : 7;
    out += digits[(code + i + offset) % 16];
  }
  return out;
}

function sourceRef(seed: string): string {
  return `project-file.v1.${hex64(seed)}`;
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(text));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

/** Scalar well-formedness check (no lone surrogates), ES2024-independent. */
function isWellFormed(text: string): boolean {
  for (let i = 0; i < text.length; i += 1) {
    const unit = text.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) return false;
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return false;
    }
  }
  return true;
}

interface RowSpec {
  seed: string;
  displayName: string;
  path: string;
  content?: string;
  contentSha256?: string | null;
  state?: string;
  repository?: string | null;
  revisionSeed?: string;
  mediaType?: string | null;
  committedAt?: string | null;
  rowOverride?: Record<string, unknown>;
  sourceOverride?: Record<string, unknown>;
}

function buildRow(spec: RowSpec): Record<string, unknown> {
  const state = spec.state === undefined ? 'READABLE' : spec.state;
  const row: Record<string, unknown> = {
    source_ref: sourceRef(spec.seed),
    repository: spec.repository === undefined ? 'macro' : spec.repository,
    path: spec.path,
    revision: spec.revisionSeed === undefined ? hex40(spec.seed) : hex40(spec.revisionSeed),
    display_name: spec.displayName,
    media_type: spec.mediaType === undefined ? 'text/markdown' : spec.mediaType,
    content_sha256: spec.contentSha256 === undefined ? null : spec.contentSha256,
    state,
    origin: { kind: 'DECLARED_ARTIFACT', actor_ref: 'actor:test', request_sha256: null },
    viewer_relation: 'CURRENT_PRINCIPAL',
  };
  return { ...row, ...(spec.rowOverride ?? {}) };
}

function buildSource(spec: RowSpec): Record<string, unknown> {
  const base: Record<string, unknown> = {
    schema: 'mastermind.workspace_project_source.v1',
    selection: { work_ref: WORK_REF, source_ref: sourceRef(spec.seed) },
    availability: 'AVAILABLE',
    reason_codes: [],
    source: {
      repository: CANONICAL_REPO,
      commit: COMMIT,
      path: spec.path,
      revision: spec.revisionSeed === undefined ? hex40(spec.seed) : hex40(spec.revisionSeed),
      content_sha256: spec.contentSha256 === undefined ? hex64('undeclared') : spec.contentSha256,
      committed_at: spec.committedAt === undefined ? DEFAULT_COMMITTED_AT : spec.committedAt,
    },
    document: {
      title: spec.displayName,
      media_type: spec.mediaType === undefined ? 'text/markdown' : spec.mediaType,
      content_utf8: spec.content === undefined ? '' : spec.content,
      content_sha256: spec.contentSha256 === undefined ? hex64('undeclared') : spec.contentSha256,
    },
  };
  return { ...base, ...(spec.sourceOverride ?? {}) };
}

async function buildFixtures(specs: RowSpec[]): Promise<{ rows: Record<string, unknown>[]; sources: Record<string, unknown> }> {
  const rows = specs.map(buildRow);
  const sources: Record<string, unknown> = {};
  for (const spec of specs) {
    const source = buildSource(spec);
    if (spec.content !== undefined) {
      const digest = await sha256(spec.content);
      (source.document as Record<string, unknown>).content_sha256 = digest;
      (source.source as Record<string, unknown>).content_sha256 = digest;
    }
    sources[sourceRef(spec.seed)] = source;
  }
  return { rows, sources };
}

function buildCatalogue(rows: unknown[], overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Record<string, unknown> = {
    schema: 'mastermind.workspace_project_knowledge.v1',
    selection: { work_ref: WORK_REF },
    availability: 'AVAILABLE',
    reason_codes: [],
    source: { repository: CANONICAL_REPO, commit: COMMIT, workstream_sha256: hex64('ws') },
    project: {
      title: 'Macro Intelligence Project',
      files: rows,
      records: [],
      memory: null,
      coverage: { files: { state: 'COMPLETE', declared: rows.length, listed: rows.length, omitted: 0 }, records: null },
    },
  };
  return { ...base, ...overrides };
}

interface OwnerOptions {
  catalogue: unknown;
  sources: Record<string, unknown>;
  onCatalogue?: () => void;
  onReadSource?: (args: { workRef: string; sourceRef: string; expectedRevision: string }, callIndex: number) => unknown;
  throwOnSourceRef?: string;
}

function makeOwner(options: OwnerOptions) {
  const calls = {
    catalogue: 0,
    source: 0,
    sourceRefs: [] as string[],
    sourceArgs: [] as Array<{ workRef: string; sourceRef: string; expectedRevision: string }>,
  };
  const owner = {
    context: () => ({ principalScope: 'principal:test', generation: 'gen-1' }),
    authGeneration: () => 7,
    readCatalogue: vi.fn(async (request: { workRef: string }) => {
      calls.catalogue += 1;
      options.onCatalogue?.();
      return options.catalogue;
    }),
    readSource: vi.fn(async (request: { workRef: string; sourceRef: string; expectedRevision: string }) => {
      calls.source += 1;
      calls.sourceRefs.push(request.sourceRef);
      calls.sourceArgs.push(request);
      if (options.throwOnSourceRef === request.sourceRef) throw new Error('owner read failed');
      const hooked = options.onReadSource?.(request, calls.source - 1);
      if (hooked !== undefined) return hooked;
      return options.sources[request.sourceRef];
    }),
  };
  return { owner: owner as unknown as ProjectFileSearchOwner, ownerRaw: owner, calls };
}

/**
 * Builds a conforming request; the cast keeps deliberate per-field overrides
 * (including malformed ones) writable in the table-driven invalid-input tests.
 */
function makeRequest(overrides: Record<string, unknown> = {}): ProjectFileSearchRequest {
  return { workRef: WORK_REF, query: 'macro', signal: new AbortController().signal, ...overrides } as unknown as ProjectFileSearchRequest;
}

function expectFailedCoverage(result: ProjectFileSearchResult): void {
  expect(result.items).toHaveLength(0);
  expect(result.sourceCommit).toBeNull();
  expect(result.coverage.nextPageStart).toBeNull();
  expect(result.coverage.scanned).toBe(0);
  expect(result.coverage.matched).toBe(0);
  expect(result.coverage.unavailable).toBe(0);
  expect(result.coverage.declared).toBe(0);
  expect(result.coverage.listed).toBe(0);
}

describe('searchProjectFiles', () => {
  it('reads one catalogue then every READABLE slice entry and returns exact matches', async () => {
    const contents = [
      '# Overview\n\nThe outlook is stable and pricing is quiet.\n',
      'The macro cycle improves while inflation cools through the year.\n',
      'Terminal revenue is unaffected by the pricing note.\n',
    ];
    const specs: RowSpec[] = [
      { seed: 'f1', displayName: 'Overview.md', path: 'docs/overview.md', content: contents[0] },
      { seed: 'f2', displayName: 'Macro note.md', path: 'docs/macro-note.md', content: contents[1] },
      { seed: 'f3', displayName: 'Terminal.md', path: 'docs/terminal.md', content: contents[2] },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.scope).toBe('CANONICAL_PROJECT_FILES');
    expect(result.workRef).toBe(WORK_REF);
    expect(result.sourceCommit).toBe(COMMIT);
    expect(result.items).toHaveLength(1);
    const item = result.items[0];
    const content = contents[1];
    expect(item.sourceRef).toBe(sourceRef('f2'));
    expect(item.expectedRevision).toBe(hex40('f2'));
    expect(item.displayName).toBe('Macro note.md');
    expect(content.includes(item.excerpt)).toBe(true);
    expect(item.excerpt.includes('inflation')).toBe(true);
    expect(item.sourceTextSha256).toBe(await sha256(content));
    expect(item.source.repository).toBe(CANONICAL_REPO);
    expect(item.source.commit).toBe(COMMIT);
    expect(item.source.path).toBe('docs/macro-note.md');
    expect(item.source.revision).toBe(hex40('f2'));
    expect(item.source.content_sha256).toBe(await sha256(content));
    expect(item.source.committed_at).toBe(DEFAULT_COMMITTED_AT);
    expect(result.coverage).toEqual({
      status: 'COMPLETE',
      declared: 3,
      listed: 3,
      scanned: 3,
      matched: 1,
      unavailable: 0,
      nextPageStart: null,
    });
    expect(calls.catalogue).toBe(1);
    expect(calls.source).toBe(3);
    for (const arg of calls.sourceArgs) {
      expect(Object.keys(arg).sort()).toEqual(['expectedRevision', 'signal', 'sourceRef', 'workRef']);
      expect(arg.workRef).toBe(WORK_REF);
    }
  });

  it('scans at most four entries, reports the explicit next page and never auto-advances', async () => {
    const specs: RowSpec[] = Array.from({ length: 6 }, (_, index) => ({
      seed: `p${index}`,
      displayName: `File ${index}.md`,
      path: `docs/file-${index}.md`,
      content: `body ${index} carries marker-${index} inside\n`,
    }));
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'marker-5' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.scanned).toBe(4);
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(0);
    expect(result.coverage.nextPageStart).toBe(4);
    expect(result.coverage.declared).toBe(6);
    expect(result.coverage.listed).toBe(6);
    expect(result.items).toHaveLength(0);
    expect(calls.catalogue).toBe(1);
    expect(calls.source).toBe(4);
  });

  it('honours one explicit page advance on the same commit with no hidden walk', async () => {
    const specs: RowSpec[] = Array.from({ length: 6 }, (_, index) => ({
      seed: `p${index}`,
      displayName: `File ${index}.md`,
      path: `docs/file-${index}.md`,
      content: `body ${index} carries marker-${index} inside\n`,
    }));
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(
      makeRequest({ query: 'marker-5', pageStart: 4, expectedCommit: COMMIT }),
      owner,
    );
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.sourceCommit).toBe(COMMIT);
    expect(result.coverage).toEqual({
      status: 'COMPLETE',
      declared: 6,
      listed: 6,
      scanned: 2,
      matched: 1,
      unavailable: 0,
      nextPageStart: null,
    });
    expect(result.items).toHaveLength(1);
    expect(result.items[0].sourceRef).toBe(sourceRef('p5'));
    expect(calls.catalogue).toBe(1);
    expect(calls.source).toBe(2);
    expect(calls.sourceRefs).toEqual([sourceRef('p4'), sourceRef('p5')]);
  });

  it('rejects a page advance without expectedCommit before any read', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'q1', displayName: 'A.md', path: 'docs/a.md', content: 'inflation text\n' },
    ]);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation', pageStart: 1 }), owner);
    expect(result.state).toBe('UNAVAILABLE');
    expect(result.reason).toBe('INVALID_INPUT');
    expectFailedCoverage(result);
    expect(calls.catalogue).toBe(0);
    expect(calls.source).toBe(0);
  });

  it('reports SOURCE_CHANGED without body reads when expectedCommit mismatches', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'r1', displayName: 'A.md', path: 'docs/a.md', content: 'inflation text\n' },
    ]);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(
      makeRequest({ query: 'inflation', expectedCommit: hex40('stale') }),
      owner,
    );
    expect(result.state).toBe('UNAVAILABLE');
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.catalogue).toBe(1);
    expect(calls.source).toBe(0);
  });
});

describe('searchProjectFiles candidate selection', () => {
  it('counts non-READABLE and cross-repository entries unavailable without body reads', async () => {
    const specs: RowSpec[] = [
      { seed: 'g1', displayName: 'Match.md', path: 'docs/match.md', content: 'inflation rises in the report\n' },
      { seed: 'g2', displayName: 'Missing.md', path: 'docs/missing.md', content: 'inflation elsewhere\n', state: 'SOURCE_MISSING' },
      { seed: 'g3', displayName: 'Over.md', path: 'docs/over.md', content: 'inflation elsewhere\n', state: 'CONTENT_OVER_BUDGET' },
      { seed: 'g4', displayName: 'Unsupported.md', path: 'docs/unsupported.md', content: 'inflation elsewhere\n', state: 'UNSUPPORTED_SOURCE' },
      { seed: 'g5', displayName: 'Terminal.md', path: 'docs/terminal.md', content: 'inflation elsewhere\n', repository: 'terminal' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.scanned).toBe(4);
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.unavailable).toBe(3);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].sourceRef).toBe(sourceRef('g1'));
    expect(calls.source).toBe(1);
    expect(calls.sourceRefs).toEqual([sourceRef('g1')]);
  });

  it('counts a duplicate opaque identity in the same page unavailable with a single read', async () => {
    const specs: RowSpec[] = [
      { seed: 'dup', displayName: 'First.md', path: 'docs/first.md', content: 'inflation note\n' },
      { seed: 'dup', displayName: 'Second.md', path: 'docs/first.md', content: 'inflation note again\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.scanned).toBe(2);
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.unavailable).toBe(1);
    expect(result.coverage.status).toBe('PARTIAL');
    expect(calls.source).toBe(1);
    expect(calls.sourceRefs).toEqual([sourceRef('dup')]);
  });

  it('counts a row that is READABLE without exact open metadata unavailable', async () => {
    const specs: RowSpec[] = [
      { seed: 'h1', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation note\n' },
      {
        seed: 'h2',
        displayName: 'BadRef.md',
        path: 'docs/badref.md',
        content: 'inflation note\n',
        rowOverride: { source_ref: 'project-file.v1.notahexref' },
      },
      {
        seed: 'h3',
        displayName: 'NoRevision.md',
        path: 'docs/norev.md',
        content: 'inflation note\n',
        rowOverride: { revision: null },
      },
      {
        seed: 'h4',
        displayName: 'NoPath.md',
        path: 'docs/nopath.md',
        content: 'inflation note\n',
        rowOverride: { path: null },
      },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.scanned).toBe(4);
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.unavailable).toBe(3);
    expect(calls.source).toBe(1);
    expect(calls.sourceRefs).toEqual([sourceRef('h1')]);
  });

  it('matches only against document content, never against filenames or generated text', async () => {
    const specs: RowSpec[] = [
      { seed: 'i1', displayName: 'inflation-only-in-filename.md', path: 'docs/x.md', content: 'nothing relevant here\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.coverage.matched).toBe(0);
    expect(result.items).toHaveLength(0);
  });
});

describe('searchProjectFiles drift and prefix leakage', () => {
  it('clears all items when a later source body answers the wrong source_ref', async () => {
    const specs: RowSpec[] = [
      { seed: 'k1', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      {
        seed: 'k2',
        displayName: 'Two.md',
        path: 'docs/two.md',
        content: 'inflation two\n',
        sourceOverride: { selection: { work_ref: WORK_REF, source_ref: sourceRef('k3') } },
      },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('UNAVAILABLE');
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.source).toBe(2);
    expect(calls.sourceRefs).toEqual([sourceRef('k1'), sourceRef('k2')]);
  });

  it('clears all items when a source body answers with the wrong revision', async () => {
    const specs: RowSpec[] = [
      { seed: 'l1', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      {
        seed: 'l2',
        displayName: 'Two.md',
        path: 'docs/two.md',
        content: 'inflation two\n',
        sourceOverride: {
          source: {
            repository: CANONICAL_REPO,
            commit: COMMIT,
            path: 'docs/two.md',
            revision: hex40('other-revision'),
            content_sha256: hex64('x'),
            committed_at: DEFAULT_COMMITTED_AT,
          },
        },
      },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.source).toBe(2);
  });

  it('clears all items when a source body answers from a different commit', async () => {
    const specs: RowSpec[] = [
      {
        seed: 'm1',
        displayName: 'One.md',
        path: 'docs/one.md',
        content: 'inflation one\n',
        sourceOverride: {
          source: {
            repository: CANONICAL_REPO,
            commit: hex40('other-commit'),
            path: 'docs/one.md',
            revision: hex40('m1'),
            content_sha256: hex64('y'),
            committed_at: DEFAULT_COMMITTED_AT,
          },
        },
      },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
  });

  it('clears all items when the owner context changes mid-scan', async () => {
    const specs: RowSpec[] = [
      { seed: 'n1', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 'n2', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    let drifted = false;
    const { owner, calls } = makeOwner({
      catalogue: buildCatalogue(rows),
      sources,
      onReadSource: (_args, callIndex) => {
        if (callIndex === 0) drifted = true;
        return undefined;
      },
    });
    const ownerWithDrift = owner as unknown as ProjectFileSearchOwner & {
      context: () => { generation: string } | null;
    };
    const baseContext = ownerWithDrift.context;
    ownerWithDrift.context = () => (drifted ? { principalScope: 'principal:test', generation: 'gen-2' } : baseContext());
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.source).toBe(1);
  });

  it('clears all items when the auth generation changes mid-scan', async () => {
    const specs: RowSpec[] = [
      { seed: 'o1', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 'o2', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    let drifted = false;
    const { owner, calls } = makeOwner({
      catalogue: buildCatalogue(rows),
      sources,
      onReadSource: (_args, callIndex) => {
        if (callIndex === 0) drifted = true;
        return undefined;
      },
    });
    const raw = owner as unknown as { authGeneration: () => number };
    const baseAuth = raw.authGeneration;
    raw.authGeneration = () => (drifted ? 8 : baseAuth());
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.source).toBe(1);
  });

  it('clears all items when the readSource method identity is swapped mid-scan', async () => {
    const specs: RowSpec[] = [
      { seed: 'p1a', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 'p2a', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, ownerRaw, calls } = makeOwner({
      catalogue: buildCatalogue(rows),
      sources,
      onReadSource: () => {
        ownerRaw.readSource = vi.fn(async () => sources[sourceRef('p2a')]);
        return undefined;
      },
    });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.source).toBe(1);
  });

  it('clears all items when the context becomes null mid-scan', async () => {
    const specs: RowSpec[] = [
      { seed: 'r1a', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 'r2a', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    let dropped = false;
    const { owner, calls } = makeOwner({
      catalogue: buildCatalogue(rows),
      sources,
      onReadSource: (_args, callIndex) => {
        if (callIndex === 0) dropped = true;
        return undefined;
      },
    });
    const raw = owner as unknown as { context: () => unknown };
    raw.context = () => (dropped ? null : { principalScope: 'principal:test', generation: 'gen-1' });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.source).toBe(1);
  });

  it('clears all items when the signal aborts mid-scan', async () => {
    const specs: RowSpec[] = [
      { seed: 's1a', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 's2a', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const controller = new AbortController();
    const { owner, calls } = makeOwner({
      catalogue: buildCatalogue(rows),
      sources,
      onReadSource: () => {
        controller.abort();
        return undefined;
      },
    });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation', signal: controller.signal }), owner);
    expect(result.state).toBe('UNAVAILABLE');
    expect(result.reason).toBe('OWNER_UNAVAILABLE');
    expectFailedCoverage(result);
    expect(result.items).toHaveLength(0);
    expect(calls.source).toBe(1);
  });

  it('aborts before any read when the signal is already aborted', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 't1a', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
    ]);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const controller = new AbortController();
    controller.abort();
    const result = await searchProjectFiles(makeRequest({ query: 'inflation', signal: controller.signal }), owner);
    expect(result.reason).toBe('OWNER_UNAVAILABLE');
    expectFailedCoverage(result);
    expect(calls.catalogue).toBe(0);
    expect(calls.source).toBe(0);
  });

  it('keeps using the snapshotted request after the request object is mutated mid-scan', async () => {
    const specs: RowSpec[] = [
      { seed: 'u1a', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 'u2a', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const request = makeRequest({ query: 'inflation' }) as unknown as Record<string, unknown>;
    const { owner, calls } = makeOwner({
      catalogue: buildCatalogue(rows),
      sources,
      onReadSource: () => {
        request.query = 'completely-other-query';
        request.workRef = 'WS:OTHERWORK01';
        return undefined;
      },
    });
    const result = await searchProjectFiles(request as unknown as ProjectFileSearchRequest, owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.query).toBe('inflation');
    expect(result.workRef).toBe(WORK_REF);
    expect(result.coverage.matched).toBe(2);
    expect(calls.source).toBe(2);
    for (const arg of calls.sourceArgs) expect(arg.workRef).toBe(WORK_REF);
  });

  it('cannot be retargeted by mutating the catalogue after the catalogue read', async () => {
    const specs: RowSpec[] = [
      { seed: 'v1a', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
      { seed: 'v2a', displayName: 'Two.md', path: 'docs/two.md', content: 'inflation two\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const catalogue = buildCatalogue(rows);
    const { owner, calls } = makeOwner({
      catalogue,
      sources,
      onReadSource: () => {
        const files = (catalogue.project as { files: Array<Record<string, unknown>> }).files;
        files[1].source_ref = sourceRef('retargeted');
        files[1].revision = hex40('retargeted');
        files.reverse();
        return undefined;
      },
    });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.coverage.matched).toBe(2);
    expect(calls.source).toBe(2);
    expect(calls.sourceArgs[1].sourceRef).toBe(sourceRef('v2a'));
    expect(calls.sourceArgs[1].expectedRevision).toBe(hex40('v2a'));
  });
});

describe('searchProjectFiles content integrity', () => {
  it('counts a tampered document digest unavailable without an excerpt', async () => {
    const specs: RowSpec[] = [
      {
        seed: 'w1',
        displayName: 'Tampered.md',
        path: 'docs/tampered.md',
        content: 'inflation report with tampered digest\n',
        sourceOverride: {},
      },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const target = sources[sourceRef('w1')] as { document: { content_sha256: string }; source: { content_sha256: string } };
    target.document.content_sha256 = hex64('tampered');
    target.source.content_sha256 = hex64('tampered');
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(1);
    expect(result.items).toHaveLength(0);
  });

  it('counts a declared uploaded digest mismatch unavailable', async () => {
    const specs: RowSpec[] = [
      {
        seed: 'w2',
        displayName: 'Declared.md',
        path: 'docs/declared.md',
        content: 'inflation report with declared digest\n',
        contentSha256: hex64('declared-wrong'),
      },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(1);
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.items).toHaveLength(0);
  });

  it('counts oversize content unavailable and never reads rows already marked over budget', async () => {
    const oversize = 'inflation '.repeat(4000);
    const specs: RowSpec[] = [
      { seed: 'w3', displayName: 'Big.md', path: 'docs/big.md', content: oversize },
      { seed: 'w4', displayName: 'Marked.md', path: 'docs/marked.md', content: 'inflation marked\n', state: 'CONTENT_OVER_BUDGET' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.scanned).toBe(2);
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(2);
    expect(result.items).toHaveLength(0);
    expect(calls.source).toBe(1);
  });

  it('counts forbidden control characters unavailable without an excerpt', async () => {
    const specs: RowSpec[] = [
      { seed: 'w5', displayName: 'Control.md', path: 'docs/control.md', content: 'before\u0000after inflation tail\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.unavailable).toBe(1);
    expect(result.coverage.matched).toBe(0);
    expect(result.items).toHaveLength(0);
  });

  it('counts a source body that is unavailable without claiming it was denied', async () => {
    const specs: RowSpec[] = [
      { seed: 'w6', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation here\n' },
      { seed: 'w7', displayName: 'Blocked.md', path: 'docs/blocked.md', content: 'inflation there\n', sourceOverride: { availability: 'UNAVAILABLE', reason_codes: ['source_unavailable'] } },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.scanned).toBe(2);
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.unavailable).toBe(1);
    expect(result.items[0].sourceRef).toBe(sourceRef('w6'));
    expect(calls.source).toBe(2);
  });

  it('counts a source body that throws as unavailable and keeps the rest of the page', async () => {
    const specs: RowSpec[] = [
      { seed: 'w8', displayName: 'First.md', path: 'docs/first.md', content: 'inflation first\n' },
      { seed: 'w9', displayName: 'Broken.md', path: 'docs/broken.md', content: 'inflation second\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources, throwOnSourceRef: sourceRef('w9') });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.unavailable).toBe(1);
    expect(result.items[0].sourceRef).toBe(sourceRef('w8'));
  });
});

describe('searchProjectFiles UTF-8 exactness', () => {
  it('preserves BOM, CRLF and Chinese text and digests the exact full text', async () => {
    const content = '﻿# 宏观周报\r\n\r\n本周市场情报：通胀降温，需求平稳。\r\n';
    const specs: RowSpec[] = [
      { seed: 'x1', displayName: '周报.md', path: 'docs/weekly.md', content },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: '市场情报' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.coverage.matched).toBe(1);
    const item = result.items[0];
    expect(item.excerpt.includes('市场情报')).toBe(true);
    expect(content.includes(item.excerpt)).toBe(true);
    expect(item.excerpt.includes('\r\n')).toBe(true);
    expect(encoder.encode(item.excerpt).length).toBeLessThanOrEqual(480);
    expect(isWellFormed(item.excerpt)).toBe(true);
    expect(item.sourceTextSha256).toBe(await sha256(content));
    expect(content.charCodeAt(0)).toBe(0xfeff);
    expect(item.excerpt.charCodeAt(0)).toBe(0xfeff);
  });

  it('matches literally and case-insensitively without regex interpretation', async () => {
    const content = 'Use macro data. Raw a.b plus [note] tags. MACRO again.\n';
    const specs: RowSpec[] = [
      { seed: 'x2', displayName: 'Regex.md', path: 'docs/regex.md', content },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const dotted = await searchProjectFiles(makeRequest({ query: 'A.B' }), owner);
    expect(dotted.coverage.matched).toBe(1);
    expect(dotted.items[0].excerpt.includes('a.b')).toBe(true);
    expect(dotted.items[0].excerpt.includes('plus')).toBe(true);
    const bracket = await searchProjectFiles(makeRequest({ query: '[note]' }), owner);
    expect(bracket.coverage.matched).toBe(1);
    expect(bracket.items[0].excerpt.includes('[note]')).toBe(true);
    const folded = await searchProjectFiles(makeRequest({ query: 'MACRO' }), owner);
    expect(folded.coverage.matched).toBe(1);
    expect(folded.items[0].excerpt.includes('macro data')).toBe(true);
  });

  it('bounds the excerpt to 480 UTF-8 bytes at scalar boundaries', async () => {
    const content = '前'.repeat(2000) + 'MARK' + '前'.repeat(2000) + '\n';
    const specs: RowSpec[] = [
      { seed: 'x3', displayName: 'Wide.md', path: 'docs/wide.md', content },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'mark' }), owner);
    expect(result.coverage.matched).toBe(1);
    const item = result.items[0];
    expect(item.excerpt.includes('MARK')).toBe(true);
    expect(content.includes(item.excerpt)).toBe(true);
    expect(encoder.encode(item.excerpt).length).toBeLessThanOrEqual(480);
    expect(isWellFormed(item.excerpt)).toBe(true);
  });

  it('bounds an emoji-heavy excerpt and keeps surrogate pairs intact', async () => {
    const content = '🎯'.repeat(5) + 'NEEDLE' + '🎯'.repeat(5) + '\n';
    const specs: RowSpec[] = [
      { seed: 'x4', displayName: 'Emoji.md', path: 'docs/emoji.md', content },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'needle' }), owner);
    expect(result.coverage.matched).toBe(1);
    const item = result.items[0];
    expect(item.excerpt.includes('NEEDLE')).toBe(true);
    expect(content.includes(item.excerpt)).toBe(true);
    expect(encoder.encode(item.excerpt).length).toBeLessThanOrEqual(480);
    expect(isWellFormed(item.excerpt)).toBe(true);
  });
});

describe('searchProjectFiles malformed DTOs and getters', () => {
  it('fails closed without invoking accessors on malformed DTO data', async () => {
    const specs: RowSpec[] = [
      { seed: 'y1', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);

    // Row with an accessor-backed field: the getter must never run.
    const getterRow = { ...rows[0] } as Record<string, unknown>;
    let rowGetterRuns = 0;
    Object.defineProperty(getterRow, 'display_name', {
      get() {
        rowGetterRuns += 1;
        throw new Error('row getter');
      },
      configurable: true,
    });

    // Catalogue with an accessor-backed schema field.
    const getterCatalogue = buildCatalogue([getterRow]);
    let schemaGetterRuns = 0;
    Object.defineProperty(getterCatalogue, 'schema', {
      get() {
        schemaGetterRuns += 1;
        throw new Error('schema getter');
      },
      configurable: true,
    });
    const { owner: catalogueOwner, calls: catalogueCalls } = makeOwner({ catalogue: getterCatalogue, sources });
    const catalogueResult = await searchProjectFiles(makeRequest({ query: 'inflation' }), catalogueOwner);
    expect(catalogueResult.reason).toBe('INVALID_SOURCE');
    expectFailedCoverage(catalogueResult);
    expect(schemaGetterRuns).toBe(0);
    expect(catalogueCalls.source).toBe(0);

    // Source with an accessor-backed document field.
    const getterSource = { ...(sources[sourceRef('y1')] as Record<string, unknown>) };
    let documentGetterRuns = 0;
    Object.defineProperty(getterSource, 'document', {
      get() {
        documentGetterRuns += 1;
        throw new Error('document getter');
      },
      configurable: true,
    });
    const sourceOverrides: Record<string, unknown> = { [sourceRef('y1')]: getterSource };
    const { owner: sourceOwner, calls: sourceCalls } = makeOwner({ catalogue: buildCatalogue(rows), sources: sourceOverrides });
    const sourceResult = await searchProjectFiles(makeRequest({ query: 'inflation' }), sourceOwner);
    expect(sourceResult.state).toBe('AVAILABLE');
    expect(sourceResult.coverage.unavailable).toBe(1);
    expect(sourceResult.items).toHaveLength(0);
    expect(documentGetterRuns).toBe(0);
    expect(sourceCalls.source).toBe(1);
  });

  it('reports INVALID_SOURCE for structurally malformed catalogues', async () => {
    const good: RowSpec[] = [{ seed: 'z1', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' }];
    const { rows, sources } = await buildFixtures(good);
    const variants: Array<[string, Record<string, unknown>]> = [
      ['wrong schema', buildCatalogue(rows, { schema: 'mastermind.other.v9' })],
      ['files not an array', buildCatalogue(rows, { project: { title: 't', files: 'nope', records: [], memory: null, coverage: { files: { state: 'COMPLETE', declared: 0, listed: 0, omitted: 0 }, records: null } } })],
      ['too many listed files', buildCatalogue(Array.from({ length: 33 }, (_, i) => rows[0]), {})],
      ['bad catalogue commit', buildCatalogue(rows, { source: { repository: CANONICAL_REPO, commit: 'not-hex', workstream_sha256: hex64('ws') } })],
      ['missing coverage counters', buildCatalogue(rows, { project: { title: 't', files: rows, records: [], memory: null, coverage: { files: { state: 'COMPLETE', declared: 1, listed: 1 }, records: null } } })],
    ];
    for (const [label, catalogue] of variants) {
      const { owner, calls } = makeOwner({ catalogue, sources });
      const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
      expect(result.reason).toBe('INVALID_SOURCE');
      expectFailedCoverage(result);
      expect(calls.source).toBe(0);
      expect(label).toBeTruthy();
    }
  });

  it('counts a row with an unknown state unavailable without any read', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'z1b', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ]);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue([{ ...rows[0], state: 'WEIRD' }]), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.scanned).toBe(1);
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(1);
    expect(calls.source).toBe(0);
  });

  it('reports SOURCE_CHANGED when the catalogue answers for a different workspace', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'z2', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ]);
    const catalogue = buildCatalogue(rows, { selection: { work_ref: 'WS:OTHERWORK01' } });
    const { owner, calls } = makeOwner({ catalogue, sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.reason).toBe('SOURCE_CHANGED');
    expectFailedCoverage(result);
    expect(calls.catalogue).toBe(1);
    expect(calls.source).toBe(0);
  });

  it('reports plain unavailability for canonical knowledge that is absent', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'z3', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ]);
    const unavailable = buildCatalogue(rows, { availability: 'UNAVAILABLE', reason_codes: ['project_knowledge_absent'] });
    const noProject = buildCatalogue(rows, { project: null });
    const noSource = buildCatalogue(rows, { source: null });
    for (const catalogue of [unavailable, noProject, noSource]) {
      const { owner, calls } = makeOwner({ catalogue, sources });
      const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
      expect(result.state).toBe('UNAVAILABLE');
      expect(result.reason).toBeNull();
      expectFailedCoverage(result);
      expect(calls.source).toBe(0);
    }
  });

  it('treats an empty file list as a complete empty search', async () => {
    const { sources } = await buildFixtures([]);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue([]), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.reason).toBeNull();
    expect(result.sourceCommit).toBe(COMMIT);
    expect(result.coverage).toEqual({
      status: 'COMPLETE',
      declared: 0,
      listed: 0,
      scanned: 0,
      matched: 0,
      unavailable: 0,
      nextPageStart: null,
    });
    expect(result.items).toHaveLength(0);
    expect(calls.source).toBe(0);
  });

  it('reports PARTIAL coverage when the owner itself declares omitted files', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'z4', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ]);
    const catalogue = buildCatalogue(rows, {
      project: {
        title: 'Partial project',
        files: rows,
        records: [],
        memory: null,
        coverage: { files: { state: 'PARTIAL', declared: 5, listed: 1, omitted: 4 }, records: null },
      },
    });
    const { owner } = makeOwner({ catalogue, sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.state).toBe('AVAILABLE');
    expect(result.coverage.status).toBe('PARTIAL');
    expect(result.coverage.declared).toBe(5);
    expect(result.coverage.listed).toBe(1);
    expect(result.coverage.scanned).toBe(1);
    expect(result.coverage.unavailable).toBe(0);
    expect(result.coverage.nextPageStart).toBeNull();
  });
});

describe('searchProjectFiles inputs and owner availability', () => {
  it('performs zero reads for malformed requests', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'z5', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ]);
    const { owner, calls } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const badRequests: Array<[string, unknown]> = [
      ['lowercase first workRef char', makeRequest({ workRef: 'WS:abc', query: 'inflation' })],
      ['too short workRef', makeRequest({ workRef: 'WS:A', query: 'inflation' })],
      ['lowercase prefix', makeRequest({ workRef: 'ws:AB', query: 'inflation' })],
      ['overlong workRef', makeRequest({ workRef: `WS:${'a'.repeat(64)}`, query: 'inflation' })],
      ['wrong prefix', makeRequest({ workRef: 'PRJ:ABC', query: 'inflation' })],
      ['missing workRef', { query: 'inflation', signal: new AbortController().signal }],
      ['too short query', makeRequest({ query: 'a' })],
      ['overlong query', makeRequest({ query: 'a'.repeat(129) })],
      ['query with newline', makeRequest({ query: 'infla\ntion' })],
      ['query with NUL', makeRequest({ query: 'a\u0000b' })],
      ['query with lone surrogate', makeRequest({ query: 'a\ud800b' })],
      ['missing query', { workRef: WORK_REF, signal: new AbortController().signal }],
      ['negative pageStart', makeRequest({ query: 'inflation', pageStart: -1 })],
      ['pageStart beyond 31', makeRequest({ query: 'inflation', pageStart: 32 })],
      ['fractional pageStart', makeRequest({ query: 'inflation', pageStart: 1.5 })],
      ['string pageStart', makeRequest({ query: 'inflation', pageStart: '0' })],
      ['bad expectedCommit', makeRequest({ query: 'inflation', expectedCommit: 'ZZZ' })],
      ['missing signal', { workRef: WORK_REF, query: 'inflation' }],
    ];
    for (const [label, request] of badRequests) {
      const result = await searchProjectFiles(request as unknown as ProjectFileSearchRequest, owner);
      expect(result.reason).toBe('INVALID_INPUT');
      expectFailedCoverage(result);
      expect(calls.catalogue).toBe(0);
      expect(calls.source).toBe(0);
      expect(label).toBeTruthy();
    }
    // Unbounded invalid values are never echoed back: the valid, bounded
    // workRef stays, the invalid query is dropped.
    const echoed = await searchProjectFiles(makeRequest({ query: 'a'.repeat(129) }), owner);
    expect(echoed.query).toBe('');
    expect(echoed.workRef).toBe(WORK_REF);
    const badRef = await searchProjectFiles(makeRequest({ workRef: 'PRJ:ABC', query: 'inflation' }), owner);
    expect(badRef.workRef).toBe('');
    expect(badRef.query).toBe('inflation');
  });

  it('returns OWNER_UNAVAILABLE with zero reads when the owner cannot be engaged', async () => {
    const { rows, sources } = await buildFixtures([
      { seed: 'z6', displayName: 'Ok.md', path: 'docs/ok.md', content: 'inflation ok\n' },
    ]);
    const catalogue = buildCatalogue(rows);
    const variants: Array<[string, ProjectFileSearchOwner]> = [
      ['owner without methods', {} as unknown as ProjectFileSearchOwner],
      ['context null', patchOwner(catalogue, sources, (raw) => { raw.context = () => null; })],
      ['context throws', patchOwner(catalogue, sources, (raw) => { raw.context = () => { throw new Error('context'); }; })],
      ['context missing generation', patchOwner(catalogue, sources, (raw) => { raw.context = () => ({ principalScope: 'p' }); })],
      ['auth NaN', patchOwner(catalogue, sources, (raw) => { raw.authGeneration = () => Number.NaN; })],
      ['auth non-number', patchOwner(catalogue, sources, (raw) => { raw.authGeneration = () => '7' as unknown as number; })],
      ['auth throws', patchOwner(catalogue, sources, (raw) => { raw.authGeneration = () => { throw new Error('auth'); }; })],
      ['readCatalogue throws', patchOwner(catalogue, sources, (raw) => { raw.readCatalogue = vi.fn(async () => { throw new Error('catalogue read'); }); })],
    ];
    for (const [label, owner] of variants) {
      const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
      expect(result.state).toBe('UNAVAILABLE');
      expect(result.reason).toBe('OWNER_UNAVAILABLE');
      expectFailedCoverage(result);
      expect(label).toBeTruthy();
    }
    const reading = patchOwner(catalogue, sources, () => undefined);
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), reading);
    expect(result.state).toBe('AVAILABLE');
  });
});

describe('searchProjectFiles closed result', () => {
  it('returns frozen detached data with no live DTO references', async () => {
    const specs: RowSpec[] = [
      { seed: 'd1', displayName: 'One.md', path: 'docs/one.md', content: 'inflation one\n' },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.items)).toBe(true);
    expect(Object.isFrozen(result.coverage)).toBe(true);
    expect(Object.isFrozen(result.items[0])).toBe(true);
    expect(Object.isFrozen(result.items[0].source)).toBe(true);
    const fixtureSource = sources[sourceRef('d1')] as { source: unknown };
    expect(result.items[0].source).not.toBe(fixtureSource.source);
    expect(() => { (result as { state: string }).state = 'X'; }).toThrow();
    expect(() => { (result.items as unknown[]).push({}); }).toThrow();
  });

  it('never returns the full source body', async () => {
    const content = 'inflation starts here\n' + 'x'.repeat(2000) + '\nSECRET-TAIL-98765\n';
    const specs: RowSpec[] = [
      { seed: 'd2', displayName: 'Long.md', path: 'docs/long.md', content },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.matched).toBe(1);
    const encoded = JSON.stringify(result);
    expect(encoded.includes('SECRET-TAIL-98765')).toBe(false);
    expect(result.items[0].excerpt.includes('inflation')).toBe(true);
    expect(content.includes(result.items[0].excerpt)).toBe(true);
    expect(encoder.encode(encoded).length).toBeLessThanOrEqual(65536);
  });

  it('echoes committed_at exactly and never invents metadata', async () => {
    const specs: RowSpec[] = [
      { seed: 'd3', displayName: 'Undated.md', path: 'docs/undated.md', content: 'inflation undated\n', committedAt: null },
    ];
    const { rows, sources } = await buildFixtures(specs);
    const { owner } = makeOwner({ catalogue: buildCatalogue(rows), sources });
    const result = await searchProjectFiles(makeRequest({ query: 'inflation' }), owner);
    expect(result.coverage.matched).toBe(1);
    expect(result.items[0].source.committed_at).toBeNull();
    expect(result.items[0].displayName).toBe('Undated.md');
  });
});

type RawOwner = {
  context: () => unknown;
  authGeneration: () => number;
  readCatalogue: (request: { workRef: string }) => Promise<unknown>;
  readSource: (request: { workRef: string; sourceRef: string; expectedRevision: string }) => Promise<unknown>;
};

function patchOwner(
  catalogue: unknown,
  sources: Record<string, unknown>,
  patch: (raw: RawOwner) => void,
): ProjectFileSearchOwner {
  const { owner } = makeOwner({ catalogue, sources });
  patch(owner as unknown as RawOwner);
  return owner;
}
