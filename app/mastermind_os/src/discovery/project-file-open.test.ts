/**
 * Synthetic scratch tests for the bounded single-match open composer
 * (`readProjectFileMatchSource`).
 *
 * These exercise the exported composer against in-memory canonical catalogue
 * and source fixtures that the parent's actual strict validators
 * (`validate_catalogue` / `validate_source`) accept. They are NOT the
 * parent's actual Python producer fixture and NOT the actual App open flow,
 * which remain the final acceptance gates; as scratch tests they are
 * synthetic by construction and say so.
 * No network, no filesystem, no persisted state, no timers.
 */
import { describe, expect, it } from 'vitest';
import {
  readProjectFileMatchSource,
  type ProjectFileOpenFailureReason,
  type ProjectFileOpenRead,
} from './project-file-open';
import type { ProjectFileMatch, ProjectFileSearchOwner } from './project-file-search';
import { sha256Hex, validate_catalogue, validate_source } from '../knowledge/library/knowledge-library-contract';
import type { KnowledgeSourceResult } from '../knowledge/library/knowledge-library-contract';

const WORK_REF = 'WS:MARKETMACRO01';
const OTHER_WORK_REF = 'WS:OTHERPROJECT';
const CANONICAL_REPO = 'mastermindx-market-intelligence/macro' as const;
const COMMIT = hex40('commit-one');
const DEFAULT_COMMITTED_AT = '2026-01-02T03:04:05Z';

function hexOf(seed: string, length: number, offset = 0): string {
  const digits = '0123456789abcdef';
  let out = '';
  for (let i = 0; i < length; i += 1) {
    const code = seed.length > 0 ? seed.charCodeAt(i % seed.length) : 7;
    out += digits[(code + i + offset) % 16];
  }
  return out;
}

function hex40(seed: string, offset = 0): string {
  return hexOf(seed, 40, offset);
}

function hex64(seed: string, offset = 0): string {
  return hexOf(seed, 64, offset);
}

function sourceRef(seed: string): string {
  return `project-file.v1.${hex64(seed)}`;
}

/* ------------------------------------------------------------------ */
/* Labeled assertion helpers (runner-independent diagnostics)           */
/* ------------------------------------------------------------------ */

function assertUnavailable(
  read: ProjectFileOpenRead,
  reason: ProjectFileOpenFailureReason | null,
  label: string,
): void {
  if (read.state !== 'UNAVAILABLE') throw new Error(`${label}: expected UNAVAILABLE, got ${read.state}`);
  if (read.reason !== reason) throw new Error(`${label}: expected reason ${reason}, got ${read.reason}`);
  if (read.reference !== null || read.document !== null) {
    throw new Error(`${label}: unavailable result must carry null reference/document`);
  }
}

function assertAvailable(
  read: ProjectFileOpenRead,
  label: string,
): {
  reference: ProjectFileMatch;
  document: KnowledgeSourceResult;
  pointer: NonNullable<KnowledgeSourceResult['source']>;
  body: NonNullable<KnowledgeSourceResult['document']>;
} {
  if (read.state !== 'AVAILABLE' || read.reason !== null) {
    throw new Error(`${label}: expected AVAILABLE/null reason, got ${read.state}/${read.reason}`);
  }
  if (read.reference === null || read.document === null) {
    throw new Error(`${label}: AVAILABLE result must carry reference and document`);
  }
  if (read.document.source === null || read.document.document === null) {
    throw new Error(`${label}: AVAILABLE document must carry the source pointer and body`);
  }
  return {
    reference: read.reference,
    document: read.document,
    pointer: read.document.source,
    body: read.document.document,
  };
}

/* ------------------------------------------------------------------ */
/* Fixture builders (snake_case backend DTO shapes)                     */
/* ------------------------------------------------------------------ */

interface RowSpec {
  seed: string;
  path: string;
  displayName: string;
  revisionSeed?: string;
  mediaType?: string | null;
  state?: string;
  repository?: string | null;
  contentSha256?: string | null;
}

function fileRow(spec: RowSpec): Record<string, unknown> {
  return {
    source_ref: sourceRef(spec.seed),
    repository: spec.repository === undefined ? 'macro' : spec.repository,
    path: spec.path,
    revision: hex40(spec.revisionSeed ?? spec.seed),
    display_name: spec.displayName,
    media_type: spec.mediaType === undefined ? 'text/markdown' : spec.mediaType,
    content_sha256: spec.contentSha256 === undefined ? null : spec.contentSha256,
    state: spec.state === undefined ? 'READABLE' : spec.state,
    origin: { kind: 'DECLARED_ARTIFACT', actor_ref: null, request_sha256: null },
    viewer_relation: 'UNKNOWN',
  };
}

interface CatalogueSpec {
  workRef?: string;
  commit?: string;
  rows?: Array<Record<string, unknown>>;
  availability?: string;
  extraKey?: boolean;
  getterSchema?: boolean;
}

function catalogueBody(spec: CatalogueSpec = {}): Record<string, unknown> {
  const rows = spec.rows ?? [];
  const body: Record<string, unknown> = {
    schema: 'mastermind.workspace_project_knowledge.v1',
    selection: { work_ref: spec.workRef ?? WORK_REF },
    availability: spec.availability ?? 'AVAILABLE',
    reason_codes: [] as string[],
    source: {
      repository: CANONICAL_REPO,
      commit: spec.commit ?? COMMIT,
      workstream_sha256: hex64('workstream'),
    },
    project: {
      title: 'Macro project',
      files: rows,
      records: [] as Array<Record<string, unknown>>,
      memory: { state: 'EMPTY', source_ref: null, revision: null },
      coverage: {
        files: { state: 'COMPLETE', declared: rows.length, listed: rows.length, omitted: 0 },
        records: { state: 'BOUNDED_SAMPLE', scanned: 0, matched: 0, omitted: 0, invalid: 0 },
      },
    },
  };
  if (spec.availability === 'UNAVAILABLE') {
    body.source = null;
    body.project = null;
    body.reason_codes = ['SOURCE_UNAVAILABLE'];
  }
  if (spec.extraKey === true) body.extra = true;
  if (spec.getterSchema === true) {
    Object.defineProperty(body, 'schema', {
      enumerable: true,
      configurable: true,
      get: () => 'mastermind.workspace_project_knowledge.v1',
    });
  }
  return body;
}

interface SourceSpec {
  sourceRef?: string;
  sourceRefSeed?: string;
  workRef?: string;
  commit?: string;
  path: string;
  revisionSeed?: string;
  revision?: string;
  mediaType?: string;
  content: string;
  digest: string;
  committedAt?: string | null;
  title?: string;
  extraDocumentKey?: boolean;
  getterSchema?: boolean;
}

function sourceBody(spec: SourceSpec): Record<string, unknown> {
  const body: Record<string, unknown> = {
    schema: 'mastermind.workspace_project_source.v1',
    selection: {
      work_ref: spec.workRef ?? WORK_REF,
      source_ref: spec.sourceRef ?? sourceRef(spec.sourceRefSeed ?? 'file-one'),
    },
    availability: 'AVAILABLE',
    reason_codes: [] as string[],
    source: {
      repository: CANONICAL_REPO,
      commit: spec.commit ?? COMMIT,
      path: spec.path,
      revision: spec.revision ?? hex40(spec.revisionSeed ?? 'rev-one'),
      content_sha256: spec.digest,
      committed_at: spec.committedAt === undefined ? DEFAULT_COMMITTED_AT : spec.committedAt,
    },
    document: {
      title: spec.title ?? 'Macro overview',
      media_type: spec.mediaType ?? 'text/markdown',
      content_utf8: spec.content,
      content_sha256: spec.digest,
    },
  };
  if (spec.extraDocumentKey === true) {
    (body.document as Record<string, unknown>).extra = true;
  }
  if (spec.getterSchema === true) {
    Object.defineProperty(body, 'schema', {
      enumerable: true,
      configurable: true,
      get: () => 'mastermind.workspace_project_source.v1',
    });
  }
  return body;
}

interface MatchSpec {
  ref: string;
  revision: string;
  displayName: string;
  excerpt: string;
  digest: string;
  path: string;
  commit?: string;
  committedAt?: string | null;
}

function buildMatch(spec: MatchSpec): ProjectFileMatch {
  return {
    sourceRef: spec.ref,
    expectedRevision: spec.revision,
    displayName: spec.displayName,
    excerpt: spec.excerpt,
    sourceTextSha256: spec.digest,
    source: {
      repository: CANONICAL_REPO,
      commit: spec.commit ?? COMMIT,
      path: spec.path,
      revision: spec.revision,
      content_sha256: spec.digest,
      committed_at: spec.committedAt === undefined ? DEFAULT_COMMITTED_AT : spec.committedAt,
    },
  };
}

/* ------------------------------------------------------------------ */
/* Happy-path fixture and owner harness                                 */
/* ------------------------------------------------------------------ */

interface Fixture {
  workRef: string;
  commit: string;
  revision: string;
  ref: string;
  path: string;
  displayName: string;
  content: string;
  digest: string;
  excerpt: string;
  match: ProjectFileMatch;
  catalogue: Record<string, unknown>;
  source: Record<string, unknown>;
}

async function happyFixture(
  overrides: {
    content?: string;
    excerpt?: string;
    mediaType?: string;
    path?: string;
    displayName?: string;
    committedAt?: string | null;
  } = {},
): Promise<Fixture> {
  const content = overrides.content ?? '# Macro market overview\n\nRevenue grew in Q3.\n';
  const excerpt = overrides.excerpt ?? 'Revenue grew';
  const digest = await sha256Hex(content);
  const mediaType = overrides.mediaType ?? 'text/markdown';
  const path = overrides.path ?? 'research/macro-overview.md';
  const displayName = overrides.displayName ?? 'Macro overview';
  const revision = hex40('rev-one');
  const ref = sourceRef('file-one');
  const committedAt = overrides.committedAt === undefined ? DEFAULT_COMMITTED_AT : overrides.committedAt;
  const match = buildMatch({ ref, revision, displayName, excerpt, digest, path, committedAt });
  const catalogue = catalogueBody({
    rows: [
      fileRow({
        seed: 'file-one',
        path,
        displayName,
        revisionSeed: 'rev-one',
        contentSha256: digest,
        mediaType,
      }),
    ],
  });
  const source = sourceBody({
    sourceRef: ref,
    path,
    revisionSeed: 'rev-one',
    mediaType,
    content,
    digest,
    committedAt,
  });
  return { workRef: WORK_REF, commit: COMMIT, revision, ref, path, displayName, content, digest, excerpt, match, catalogue, source };
}

/** The caller-side open request built from a fixture (fresh signal each call). */
function openRequest(fixture: Fixture, signal: AbortSignal, match?: ProjectFileMatch): {
  workRef: string;
  match: ProjectFileMatch;
  signal: AbortSignal;
} {
  return { workRef: fixture.workRef, match: match ?? fixture.match, signal };
}

interface OwnerCalls {
  context: number;
  auth: number;
  readCatalogue: number;
  readSource: number;
}

interface Harness {
  owner: ProjectFileSearchOwner;
  calls: OwnerCalls;
  captured: { catalogueRequest: unknown; sourceRequest: unknown };
}

interface OwnerOptions {
  generation?: string | (() => string);
  auth?: number | (() => number);
  contextImpl?: () => unknown;
  catalogue?: unknown;
  source?: unknown;
  onCatalogue?: (request: { workRef: string; signal: AbortSignal }) => unknown;
  onSource?: (request: {
    workRef: string;
    sourceRef: string;
    expectedRevision: string;
    signal: AbortSignal;
  }) => unknown;
}

function makeOwner(options: OwnerOptions = {}): Harness {
  const calls: OwnerCalls = { context: 0, auth: 0, readCatalogue: 0, readSource: 0 };
  const captured: { catalogueRequest: unknown; sourceRequest: unknown } = {
    catalogueRequest: null,
    sourceRequest: null,
  };
  const generationOption = options.generation;
  const generation =
    typeof generationOption === 'function' ? generationOption : () => generationOption ?? 'gen-1';
  const authOption = options.auth;
  const auth = typeof authOption === 'function' ? authOption : () => authOption ?? 3;
  const owner = {
    context: (): unknown => {
      calls.context += 1;
      if (options.contextImpl) return options.contextImpl();
      return { generation: generation() };
    },
    authGeneration: (): number => {
      calls.auth += 1;
      return auth();
    },
    readCatalogue: async (request: { workRef: string; signal: AbortSignal }): Promise<unknown> => {
      calls.readCatalogue += 1;
      captured.catalogueRequest = { ...request };
      if (options.onCatalogue) return options.onCatalogue(request);
      return options.catalogue;
    },
    readSource: async (request: {
      workRef: string;
      sourceRef: string;
      expectedRevision: string;
      signal: AbortSignal;
    }): Promise<unknown> => {
      calls.readSource += 1;
      captured.sourceRequest = { ...request };
      if (options.onSource) return options.onSource(request);
      return options.source;
    },
  } as unknown as ProjectFileSearchOwner;
  return { owner, calls, captured };
}

/** Returns `stable` for calls 1..driftAtCall-1 and `drifted` from then on. */
function driftSequence<T>(stable: T, drifted: T, driftAtCall: number): () => T {
  let calls = 0;
  return () => {
    calls += 1;
    return calls >= driftAtCall ? drifted : stable;
  };
}

/* ------------------------------------------------------------------ */
/* Suites                                                               */
/* ------------------------------------------------------------------ */

describe('fixtures satisfy the actual parent validators', () => {
  it('catalogue and source fixtures validate strictly', async () => {
    const fixture = await happyFixture();
    const catalogue = validate_catalogue(fixture.catalogue, fixture.workRef);
    expect(catalogue.availability).toBe('AVAILABLE');
    const source = validate_source(fixture.source, fixture.workRef, fixture.ref);
    expect(source.availability).toBe('AVAILABLE');
  });
});

describe('positive single-match open', () => {
  it('opens through exactly one catalogue read and one detail read', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const signal = new AbortController().signal;
    const read = await readProjectFileMatchSource(openRequest(fixture, signal), harness.owner);
    const { reference, document } = assertAvailable(read, 'happy path');
    expect(harness.calls.readCatalogue).toBe(1);
    expect(harness.calls.readSource).toBe(1);
    // The detail request carries ONLY workRef/sourceRef/expectedRevision/signal.
    const detailRequest = harness.captured.sourceRequest as Record<string, unknown>;
    expect(Object.keys(detailRequest).sort()).toEqual(['expectedRevision', 'signal', 'sourceRef', 'workRef']);
    expect(detailRequest['workRef']).toBe(fixture.workRef);
    expect(detailRequest['sourceRef']).toBe(fixture.ref);
    expect(detailRequest['expectedRevision']).toBe(fixture.revision);
    expect(detailRequest['signal']).toBe(signal);
    const catalogueRequest = harness.captured.catalogueRequest as Record<string, unknown>;
    expect(Object.keys(catalogueRequest).sort()).toEqual(['signal', 'workRef']);
    expect(catalogueRequest['workRef']).toBe(fixture.workRef);
    // The document is exactly the parent's strict decoded KnowledgeSourceResult.
    const expected = await validate_source(fixture.source, fixture.workRef, fixture.ref);
    expect(document).toEqual(expected);
    expect(document.reasonCodes).toEqual([]);
    // The reference echoes the caller's validated match verbatim.
    expect(reference.sourceRef).toBe(fixture.match.sourceRef);
    expect(reference.expectedRevision).toBe(fixture.match.expectedRevision);
    expect(reference.displayName).toBe(fixture.match.displayName);
    expect(reference.excerpt).toBe(fixture.match.excerpt);
    expect(reference.sourceTextSha256).toBe(fixture.digest);
    expect(reference.source.repository).toBe(CANONICAL_REPO);
    expect(reference.source.commit).toBe(fixture.commit);
    expect(reference.source.path).toBe(fixture.path);
    expect(reference.source.revision).toBe(fixture.revision);
    expect(reference.source.content_sha256).toBe(fixture.digest);
    expect(reference.source.committed_at).toBe(DEFAULT_COMMITTED_AT);
  });

  it('preserves BOM, CRLF, CJK and emoji byte-exactly in text/plain', async () => {
    const content = '\uFEFF# 市场概览\r\n\r\n营收增长 🚀 于第三季度。\r\nascii tail\n末端 👍🏽';
    const excerpt = '营收增长 🚀 于第三季度。';
    const fixture = await happyFixture({
      content,
      excerpt,
      mediaType: 'text/plain',
      path: 'docs/cjk.txt',
      displayName: 'CJK notes',
    });
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    const { reference, pointer, body } = assertAvailable(read, 'unicode');
    expect(body.contentUtf8).toBe(content);
    expect(body.mediaType).toBe('text/plain');
    expect(body.title).toBe('Macro overview');
    expect(pointer.path).toBe('docs/cjk.txt');
    expect(pointer.revision).toBe(fixture.revision);
    expect(reference.excerpt).toBe(excerpt);
    const digest = await sha256Hex(content);
    expect(body.contentSha256).toBe(digest);
    expect(reference.sourceTextSha256).toBe(digest);
  });

  it('a caller mutating the request mid-flight cannot retarget the open', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const mutableMatch = { ...fixture.match, source: { ...fixture.match.source } } as unknown as ProjectFileMatch;
    const request = { workRef: fixture.workRef, match: mutableMatch, signal: new AbortController().signal };
    const pending = readProjectFileMatchSource(request, harness.owner);
    // Runs after the synchronous snapshot, before any read resolves.
    (request as { workRef: string }).workRef = OTHER_WORK_REF;
    const writable = mutableMatch as unknown as Record<string, unknown>;
    writable['sourceRef'] = sourceRef('retarget');
    writable['expectedRevision'] = hex40('retarget-rev');
    (writable['source'] as Record<string, unknown>)['commit'] = hex40('retarget-commit');
    const read = await pending;
    const { reference } = assertAvailable(read, 'mid-flight mutation');
    expect(harness.calls.readCatalogue).toBe(1);
    expect(harness.calls.readSource).toBe(1);
    expect(reference.sourceRef).toBe(fixture.ref);
    expect(reference.expectedRevision).toBe(fixture.revision);
    expect(reference.source.commit).toBe(fixture.commit);
    const detailRequest = harness.captured.sourceRequest as Record<string, unknown>;
    expect(detailRequest['sourceRef']).toBe(fixture.ref);
  });

  it('the returned reference is detached from later caller mutation', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    const { reference } = assertAvailable(read, 'detached');
    const beforeExcerpt = reference.excerpt;
    const beforeDigest = reference.sourceTextSha256;
    const writable = fixture.match as unknown as Record<string, unknown>;
    writable['excerpt'] = 'mutated afterwards';
    writable['sourceTextSha256'] = hex64('mutated');
    expect(reference.excerpt).toBe(beforeExcerpt);
    expect(reference.sourceTextSha256).toBe(beforeDigest);
    expect(reference).not.toBe(fixture.match);
    expect(read.document).not.toBe(fixture.source);
  });

  it('a plain forwarding proxy over a valid match opens safely', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const proxied = new Proxy({ ...fixture.match }, {}) as unknown as ProjectFileMatch;
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal, proxied),
      harness.owner,
    );
    const { reference } = assertAvailable(read, 'forwarding proxy');
    expect(reference.sourceRef).toBe(fixture.ref);
    expect(harness.calls.readSource).toBe(1);
  });

  it('accepts the canonical work_ref upper bound like the parent composer', async () => {
    const longRef = 'WS:' + 'A'.repeat(64);
    const fixture = await happyFixture();
    const catalogue = catalogueBody({
      workRef: longRef,
      commit: fixture.commit,
      rows: [
        fileRow({
          seed: 'file-one',
          path: fixture.path,
          displayName: fixture.displayName,
          revisionSeed: 'rev-one',
          contentSha256: fixture.digest,
        }),
      ],
    });
    const source = {
      ...fixture.source,
      selection: { work_ref: longRef, source_ref: fixture.ref },
    };
    const harness = makeOwner({ catalogue, source });
    const read = await readProjectFileMatchSource(
      { workRef: longRef, match: fixture.match, signal: new AbortController().signal },
      harness.owner,
    );
    const { body } = assertAvailable(read, 'long work_ref');
    expect(body.contentUtf8).toBe(fixture.content);
  });
});

describe('catalogue gate fails closed with zero detail reads', () => {
  interface CatalogueCase {
    name: string;
    reason: ProjectFileOpenFailureReason | null;
    build: (fixture: Fixture) => { catalogue?: unknown; match?: ProjectFileMatch };
  }

  const fixtureRowOf = (fixture: Fixture): Record<string, unknown> =>
    fileRow({
      seed: 'file-one',
      path: fixture.path,
      displayName: fixture.displayName,
      revisionSeed: 'rev-one',
      contentSha256: fixture.digest,
    });

  const CASES: CatalogueCase[] = [
    {
      name: 'catalogue unavailable',
      reason: null,
      build: () => ({ catalogue: catalogueBody({ availability: 'UNAVAILABLE' }) }),
    },
    {
      name: 'missing membership with another readable row present (no fallback)',
      reason: 'SOURCE_CHANGED',
      build: () => ({
        catalogue: catalogueBody({
          rows: [fileRow({ seed: 'file-two', path: 'docs/other-notes.md', displayName: 'Other notes' })],
        }),
      }),
    },
    {
      name: 'duplicate source_ref rows',
      reason: 'INVALID_SOURCE',
      build: (fixture) => {
        const row = fixtureRowOf(fixture);
        return { catalogue: catalogueBody({ rows: [row, { ...row, path: 'research/other.md' }] }) };
      },
    },
    {
      name: 'row no longer READABLE',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({
          rows: [{ ...fixtureRowOf(fixture), state: 'SOURCE_MISSING' }],
        }),
      }),
    },
    {
      name: 'row repository not macro',
      reason: 'INVALID_SOURCE',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [{ ...fixtureRowOf(fixture), repository: 'terminal' }] }),
      }),
    },
    {
      name: 'catalogue commit drift',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({ commit: hex40('other-commit'), rows: [fixtureRowOf(fixture)] }),
      }),
    },
    {
      name: 'row path drift',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [{ ...fixtureRowOf(fixture), path: 'docs/other-path.md' }] }),
      }),
    },
    {
      name: 'row revision drift',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [{ ...fixtureRowOf(fixture), revision: hex40('rev-two') }] }),
      }),
    },
    {
      name: 'row display name drift',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [{ ...fixtureRowOf(fixture), display_name: 'Renamed' }] }),
      }),
    },
    {
      name: 'catalogue work_ref drift',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({ workRef: OTHER_WORK_REF, rows: [fixtureRowOf(fixture)] }),
      }),
    },
    {
      name: 'row declared digest drift',
      reason: 'SOURCE_CHANGED',
      build: (fixture) => ({
        catalogue: catalogueBody({
          rows: [{ ...fixtureRowOf(fixture), content_sha256: hex64('other-content') }],
        }),
      }),
    },
    {
      name: 'READABLE row without media type',
      reason: 'INVALID_SOURCE',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [{ ...fixtureRowOf(fixture), media_type: null }] }),
      }),
    },
    {
      name: 'malformed catalogue schema',
      reason: 'INVALID_SOURCE',
      build: (fixture) => ({
        catalogue: { ...catalogueBody({ rows: [fixtureRowOf(fixture)] }), schema: 'other.schema.v1' },
      }),
    },
    {
      name: 'extra top-level catalogue key',
      reason: 'INVALID_SOURCE',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [fixtureRowOf(fixture)], extraKey: true }),
      }),
    },
    {
      name: 'getter-backed catalogue schema',
      reason: 'INVALID_SOURCE',
      build: (fixture) => ({
        catalogue: catalogueBody({ rows: [fixtureRowOf(fixture)], getterSchema: true }),
      }),
    },
  ];

  for (const testCase of CASES) {
    it(`catalogue gate: ${testCase.name} → zero detail reads`, async () => {
      const fixture = await happyFixture();
      const built = testCase.build(fixture);
      const harness = makeOwner({
        catalogue: built.catalogue ?? fixture.catalogue,
        source: fixture.source,
      });
      const read = await readProjectFileMatchSource(
        openRequest(fixture, new AbortController().signal, built.match),
        harness.owner,
      );
      assertUnavailable(read, testCase.reason, testCase.name);
      expect(harness.calls.readCatalogue).toBe(1);
      expect(harness.calls.readSource).toBe(0);
    });
  }

  it('a rejecting readCatalogue is OWNER_UNAVAILABLE with zero detail reads', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      onCatalogue: () => Promise.reject(new Error('catalogue read failed')),
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'catalogue reject');
    expect(harness.calls.readCatalogue).toBe(1);
    expect(harness.calls.readSource).toBe(0);
  });
});

describe('source gate fails closed', () => {
  interface SourceCase {
    name: string;
    reason: ProjectFileOpenFailureReason | null;
    mutateBody?: (raw: Record<string, unknown>) => void | Promise<void>;
    mutateMatch?: (writable: Record<string, unknown>) => void;
    /** Detail reads expected; defaults to 1 (mismatches caught pre-read read 0). */
    detailReads?: number;
  }

  const CASES: SourceCase[] = [
    {
      name: 'selection work_ref drift',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['selection'] as Record<string, unknown>)['work_ref'] = OTHER_WORK_REF;
      },
    },
    {
      name: 'selection source_ref drift',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['selection'] as Record<string, unknown>)['source_ref'] = sourceRef('other');
      },
    },
    {
      name: 'pointer commit drift',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['source'] as Record<string, unknown>)['commit'] = hex40('other-commit');
      },
    },
    {
      name: 'pointer path drift vs row',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['source'] as Record<string, unknown>)['path'] = 'docs/other-path.md';
      },
    },
    {
      name: 'pointer blob revision drift',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['source'] as Record<string, unknown>)['revision'] = hex40('other-rev');
      },
    },
    {
      name: 'document media drift vs row',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['document'] as Record<string, unknown>)['media_type'] = 'text/plain';
      },
    },
    {
      name: 'content replaced under the declared digest',
      reason: 'SOURCE_CHANGED',
      mutateBody: (raw) => {
        (raw['document'] as Record<string, unknown>)['content_utf8'] = '# replaced content\n';
      },
    },
    {
      name: 'declared digest tampered but self-consistent',
      reason: 'SOURCE_CHANGED',
      mutateBody: async (raw) => {
        const tampered = await sha256Hex('# unrelated text\n');
        (raw['document'] as Record<string, unknown>)['content_sha256'] = tampered;
        (raw['source'] as Record<string, unknown>)['content_sha256'] = tampered;
      },
    },
    {
      name: 'match digest differs from actual text',
      reason: 'SOURCE_CHANGED',
      // The row's declared digest disagrees with the match's claimed digest,
      // so the gate fails before any detail read.
      detailReads: 0,
      mutateMatch: (writable) => {
        writable['sourceTextSha256'] = hex64('wrong-digest');
        (writable['source'] as Record<string, unknown>)['content_sha256'] = hex64('wrong-digest');
      },
    },
    {
      name: 'excerpt not contiguous in actual text',
      reason: 'SOURCE_CHANGED',
      mutateMatch: (writable) => {
        writable['excerpt'] = 'never appears in this document';
      },
    },
    {
      name: 'source body unavailable',
      reason: null,
      mutateBody: (raw) => {
        raw['availability'] = 'UNAVAILABLE';
        raw['source'] = null;
        raw['document'] = null;
        raw['reason_codes'] = ['SOURCE_UNAVAILABLE'];
      },
    },
    {
      name: 'document extra key rejected by validator',
      reason: 'INVALID_SOURCE',
      mutateBody: (raw) => {
        (raw['document'] as Record<string, unknown>)['extra'] = true;
      },
    },
    {
      name: 'getter-backed source schema rejected by validator',
      reason: 'INVALID_SOURCE',
      mutateBody: (raw) => {
        Object.defineProperty(raw, 'schema', {
          enumerable: true,
          configurable: true,
          get: () => 'mastermind.workspace_project_source.v1',
        });
      },
    },
  ];

  for (const testCase of CASES) {
    it(`source gate: ${testCase.name}`, async () => {
      const fixture = await happyFixture();
      if (testCase.mutateBody) await testCase.mutateBody(fixture.source);
      let match = fixture.match;
      if (testCase.mutateMatch) {
        const writable = { ...fixture.match, source: { ...fixture.match.source } } as unknown as Record<string, unknown>;
        testCase.mutateMatch(writable);
        match = writable as unknown as ProjectFileMatch;
      }
      const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
      const read = await readProjectFileMatchSource(
        openRequest(fixture, new AbortController().signal, match),
        harness.owner,
      );
      assertUnavailable(read, testCase.reason, testCase.name);
      expect(harness.calls.readCatalogue).toBe(1);
      expect(harness.calls.readSource).toBe(testCase.detailReads ?? 1);
    });
  }

  it('a rejecting readSource is OWNER_UNAVAILABLE with no document', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      onSource: () => Promise.reject(new Error('source read failed')),
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'source reject');
    expect(harness.calls.readSource).toBe(1);
  });
});

describe('owner identity, currentness and abort drift', () => {
  it('null context is OWNER_UNAVAILABLE with zero reads', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      contextImpl: () => null,
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'null context');
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('a throwing context() is OWNER_UNAVAILABLE with zero reads', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      contextImpl: () => {
        throw new Error('hostile context');
      },
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'throwing context');
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('a context without a generation own data property is OWNER_UNAVAILABLE', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      contextImpl: () => ({ other: 'x' }),
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'missing generation');
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('an accessor-backed context generation is OWNER_UNAVAILABLE without executing it', async () => {
    const fixture = await happyFixture();
    let getterRuns = 0;
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      contextImpl: () => {
        const holder: Record<string, unknown> = {};
        Object.defineProperty(holder, 'generation', {
          enumerable: true,
          configurable: true,
          get: () => {
            getterRuns += 1;
            return 'gen-1';
          },
        });
        return holder;
      },
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'accessor generation');
    expect(getterRuns).toBe(0);
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('missing owner methods are OWNER_UNAVAILABLE with zero reads', async () => {
    const fixture = await happyFixture();
    const owner = { context: () => ({ generation: 'gen-1' }) } as unknown as ProjectFileSearchOwner;
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      owner,
    );
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'missing methods');
  });

  const INVALID_AUTH_VALUES: Array<{ name: string; value: number }> = [
    { name: 'negative', value: -1 },
    { name: 'NaN', value: Number.NaN },
    { name: 'Infinity', value: Number.POSITIVE_INFINITY },
    { name: 'fractional', value: 1.5 },
    { name: 'unsafe 2^53', value: 2 ** 53 },
    { name: 'MAX_SAFE_INTEGER + 1', value: Number.MAX_SAFE_INTEGER + 1 },
  ];
  for (const invalid of INVALID_AUTH_VALUES) {
    it(`authGeneration ${invalid.name} is OWNER_UNAVAILABLE with zero reads`, async () => {
      const fixture = await happyFixture();
      const harness = makeOwner({
        catalogue: fixture.catalogue,
        source: fixture.source,
        auth: invalid.value,
      });
      const read = await readProjectFileMatchSource(
        openRequest(fixture, new AbortController().signal),
        harness.owner,
      );
      assertUnavailable(read, 'OWNER_UNAVAILABLE', `auth ${invalid.name}`);
      expect(harness.calls.readCatalogue).toBe(0);
      expect(harness.calls.readSource).toBe(0);
    });
  }

  // Checkpoint call order: capture(1) → post-catalogue(2) → pre-detail(3) →
  // post-detail(4) → post-digest(5) → immediately-before-return(6).
  const CHECKPOINTS = [
    { name: 'after the catalogue', driftAtCall: 2, detailReads: 0 },
    { name: 'after the detail read', driftAtCall: 4, detailReads: 1 },
    { name: 'after the digest', driftAtCall: 5, detailReads: 1 },
    { name: 'immediately before return', driftAtCall: 6, detailReads: 1 },
  ];
  for (const checkpoint of CHECKPOINTS) {
    it(`auth generation drift ${checkpoint.name} clears the open`, async () => {
      const fixture = await happyFixture();
      const harness = makeOwner({
        catalogue: fixture.catalogue,
        source: fixture.source,
        auth: driftSequence(3, 9, checkpoint.driftAtCall),
      });
      const read = await readProjectFileMatchSource(
        openRequest(fixture, new AbortController().signal),
        harness.owner,
      );
      assertUnavailable(read, 'SOURCE_CHANGED', `auth drift ${checkpoint.name}`);
      expect(harness.calls.readSource).toBe(checkpoint.detailReads);
    });

    it(`owner generation drift ${checkpoint.name} clears the open`, async () => {
      const fixture = await happyFixture();
      const harness = makeOwner({
        catalogue: fixture.catalogue,
        source: fixture.source,
        generation: driftSequence('gen-1', 'gen-2', checkpoint.driftAtCall),
      });
      const read = await readProjectFileMatchSource(
        openRequest(fixture, new AbortController().signal),
        harness.owner,
      );
      assertUnavailable(read, 'SOURCE_CHANGED', `generation drift ${checkpoint.name}`);
      expect(harness.calls.readSource).toBe(checkpoint.detailReads);
    });
  }

  it('readSource method drift after the catalogue clears the open with zero detail reads', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    (harness.owner as unknown as { readCatalogue: unknown }).readCatalogue = async () => {
      (harness.owner as unknown as { readSource: unknown }).readSource = async () => fixture.source;
      return fixture.catalogue;
    };

    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'SOURCE_CHANGED', 'readSource method drift');
    expect(harness.calls.readSource).toBe(0);
  });

  it('readCatalogue method drift after the catalogue clears the open', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      onCatalogue: () => {
        (harness.owner as unknown as { readCatalogue: unknown }).readCatalogue = async () => fixture.catalogue;
        return fixture.catalogue;
      },
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'SOURCE_CHANGED', 'readCatalogue method drift');
    expect(harness.calls.readSource).toBe(0);
  });

  it('a pre-aborted signal performs zero reads', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const controller = new AbortController();
    controller.abort();
    const read = await readProjectFileMatchSource(openRequest(fixture, controller.signal), harness.owner);
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'pre-aborted');
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('abort during the catalogue read discards the body with zero detail reads', async () => {
    const fixture = await happyFixture();
    const controller = new AbortController();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      onCatalogue: () => {
        controller.abort();
        return fixture.catalogue;
      },
    });
    const read = await readProjectFileMatchSource(openRequest(fixture, controller.signal), harness.owner);
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'abort after catalogue');
    expect(harness.calls.readSource).toBe(0);
  });

  it('abort during the detail read discards a fully valid body', async () => {
    const fixture = await happyFixture();
    const controller = new AbortController();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      onSource: () => {
        controller.abort();
        return fixture.source;
      },
    });
    const read = await readProjectFileMatchSource(openRequest(fixture, controller.signal), harness.owner);
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'abort after detail');
    expect(harness.calls.readSource).toBe(1);
  });

  it('abort during the digest window discards the open document', async () => {
    const fixture = await happyFixture();
    const controller = new AbortController();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: fixture.source,
      onSource: () => {
        // Land the abort inside the digest await window.
        queueMicrotask(() => {
          queueMicrotask(() => controller.abort());
        });
        return fixture.source;
      },
    });
    const read = await readProjectFileMatchSource(openRequest(fixture, controller.signal), harness.owner);
    assertUnavailable(read, 'OWNER_UNAVAILABLE', 'abort during digest');
    expect(harness.calls.readSource).toBe(1);
  });
});

describe('malformed caller data is rejected before any owner interaction', () => {
  interface MatchCase {
    name: string;
    mutate: (writable: Record<string, unknown>) => void;
  }

  const CASES: MatchCase[] = [
    { name: 'missing excerpt', mutate: (m) => {
        delete m['excerpt'];
      } },
    { name: 'extra match key', mutate: (m) => {
        m['extra'] = 'x';
      } },
    { name: 'bad source_ref prefix', mutate: (m) => {
        m['sourceRef'] = 'project-other.v1.' + hex64('x');
      } },
    { name: 'uppercase expected revision', mutate: (m) => {
        m['expectedRevision'] = hex40('rev-one').toUpperCase();
      } },
    { name: 'short source text digest', mutate: (m) => {
        m['sourceTextSha256'] = 'ab'.repeat(31);
      } },
    { name: 'empty display name', mutate: (m) => {
        m['displayName'] = '';
      } },
    { name: 'excerpt over 480 bytes', mutate: (m) => {
        m['excerpt'] = 'a'.repeat(481);
      } },
    { name: 'excerpt with control char', mutate: (m) => {
        m['excerpt'] = 'bad\u0001excerpt';
      } },
    { name: 'excerpt with lone surrogate', mutate: (m) => {
        m['excerpt'] = 'bad\uD800trail';
      } },
    { name: 'wrong repository', mutate: (m) => {
        (m['source'] as Record<string, unknown>)['repository'] = 'other/repo';
      } },
    { name: 'source revision differs from expectedRevision', mutate: (m) => {
        (m['source'] as Record<string, unknown>)['revision'] = hex40('other-rev');
      } },
    { name: 'declared digest differs from source text digest', mutate: (m) => {
        (m['source'] as Record<string, unknown>)['content_sha256'] = hex64('other');
      } },
    { name: 'numeric committed_at', mutate: (m) => {
        (m['source'] as Record<string, unknown>)['committed_at'] = 42;
      } },
    { name: 'source missing path', mutate: (m) => {
        delete (m['source'] as Record<string, unknown>)['path'];
      } },
    { name: 'source extra key', mutate: (m) => {
        (m['source'] as Record<string, unknown>)['extra'] = true;
      } },
  ];

  for (const testCase of CASES) {
    it(`match rejected: ${testCase.name} (zero owner reads)`, async () => {
      const fixture = await happyFixture();
      const writable = { ...fixture.match, source: { ...fixture.match.source } } as unknown as Record<string, unknown>;
      testCase.mutate(writable);
      const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
      const read = await readProjectFileMatchSource(
        openRequest(fixture, new AbortController().signal, writable as unknown as ProjectFileMatch),
        harness.owner,
      );
      assertUnavailable(read, 'INVALID_INPUT', testCase.name);
      expect(harness.calls.context).toBe(0);
      expect(harness.calls.auth).toBe(0);
      expect(harness.calls.readCatalogue).toBe(0);
      expect(harness.calls.readSource).toBe(0);
    });
  }

  const BAD_WORK_REFS = ['ws:lower', 'WS:', 'WS:A B', 'WS:' + 'A'.repeat(65), '', 'WS:ok'];
  for (const bad of BAD_WORK_REFS) {
    it(`workRef rejected: ${JSON.stringify(bad)} (zero owner reads)`, async () => {
      const fixture = await happyFixture();
      const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
      const read = await readProjectFileMatchSource(
        { workRef: bad, match: fixture.match, signal: new AbortController().signal },
        harness.owner,
      );
      assertUnavailable(read, 'INVALID_INPUT', `workRef ${bad}`);
      expect(harness.calls.context).toBe(0);
      expect(harness.calls.readCatalogue).toBe(0);
    });
  }

  it('an accessor-backed match field rejects without executing the getter', async () => {
    const fixture = await happyFixture();
    let getterRuns = 0;
    const hostile: Record<string, unknown> = { ...fixture.match };
    Object.defineProperty(hostile, 'excerpt', {
      enumerable: true,
      configurable: true,
      get: () => {
        getterRuns += 1;
        return fixture.match.excerpt;
      },
    });
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal, hostile as unknown as ProjectFileMatch),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_INPUT', 'accessor excerpt');
    expect(getterRuns).toBe(0);
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('an accessor-backed source.commit rejects without executing the getter', async () => {
    const fixture = await happyFixture();
    let getterRuns = 0;
    const source: Record<string, unknown> = { ...fixture.match.source };
    Object.defineProperty(source, 'commit', {
      enumerable: true,
      configurable: true,
      get: () => {
        getterRuns += 1;
        return fixture.match.source.commit;
      },
    });
    const hostile = { ...fixture.match, source } as unknown as ProjectFileMatch;
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal, hostile),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_INPUT', 'accessor commit');
    expect(getterRuns).toBe(0);
    expect(harness.calls.readCatalogue).toBe(0);
  });

  it('a proxy with accessor descriptors rejects without invoking getters or the owner', async () => {
    const fixture = await happyFixture();
    const hostile = new Proxy({ ...fixture.match } as Record<string, unknown>, {
      getOwnPropertyDescriptor() {
        return {
          enumerable: true,
          configurable: true,
          get: () => {
            throw new Error('getter must never run');
          },
        };
      },
    });
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal, hostile as unknown as ProjectFileMatch),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_INPUT', 'accessor proxy');
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('a proxy whose descriptor trap throws rejects safely', async () => {
    const fixture = await happyFixture();
    const bomb = new Proxy({ ...fixture.match }, {
      getOwnPropertyDescriptor(): PropertyDescriptor {
        throw new Error('boom');
      },
    });
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal, bomb as unknown as ProjectFileMatch),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_INPUT', 'throwing proxy');
    expect(harness.calls.readCatalogue).toBe(0);
    expect(harness.calls.readSource).toBe(0);
  });

  it('a throwing toJSON on an extra key never executes', async () => {
    const fixture = await happyFixture();
    let toJSONRuns = 0;
    const hostile = {
      ...fixture.match,
      toJSON: () => {
        toJSONRuns += 1;
        return '{}';
      },
    } as unknown as ProjectFileMatch;
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal, hostile),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_INPUT', 'throwing toJSON');
    expect(toJSONRuns).toBe(0);
    expect(harness.calls.readCatalogue).toBe(0);
  });

  it('a non-object request is INVALID_INPUT', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      null as unknown as { workRef: string; match: ProjectFileMatch; signal: AbortSignal },
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_INPUT', 'null request');
    expect(harness.calls.readCatalogue).toBe(0);
  });
});

describe('no fallback, no retry, no cached state', () => {
  it('a failed open leaves no state: a corrected open succeeds afterwards', async () => {
    const fixture = await happyFixture();
    const stale = catalogueBody({
      rows: [
        fileRow({
          seed: 'file-one',
          path: fixture.path,
          displayName: fixture.displayName,
          revisionSeed: 'rev-two',
          contentSha256: fixture.digest,
        }),
      ],
    });
    const firstHarness = makeOwner({ catalogue: stale, source: fixture.source });
    const first = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      firstHarness.owner,
    );
    assertUnavailable(first, 'SOURCE_CHANGED', 'stale revision');
    const secondHarness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const second = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      secondHarness.owner,
    );
    assertAvailable(second, 'open after correction');
    expect(secondHarness.calls.readCatalogue).toBe(1);
    expect(secondHarness.calls.readSource).toBe(1);
  });

  it('a validator-failing catalogue is read exactly once (no retry)', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: { ...catalogueBody({ rows: [fileRow({ seed: 'x', path: 'p', displayName: 'd' })] }), schema: 'other' },
      source: fixture.source,
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_SOURCE', 'no retry');
    expect(harness.calls.readCatalogue).toBe(1);
    expect(harness.calls.readSource).toBe(0);
  });

  it('a failing detail read happens at most once (no retry)', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({
      catalogue: fixture.catalogue,
      source: { ...fixture.source, schema: 'other.schema' },
    });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'INVALID_SOURCE', 'single detail read');
    expect(harness.calls.readSource).toBe(1);
  });
});

describe('result budget', () => {
  it('a maximum-content document over the encoded budget is OVER_BUDGET with nulls', async () => {
    const content = '\n'.repeat(32768);
    const fixture = await happyFixture({ content, excerpt: '\n' });
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    assertUnavailable(read, 'OVER_BUDGET', 'over budget');
  });

  it('a large but in-budget document opens completely', async () => {
    const content = 'line\n'.repeat(6000);
    const fixture = await happyFixture({ content, excerpt: 'line' });
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    const { body } = assertAvailable(read, 'in budget');
    expect(body.contentUtf8).toBe(content);
  });
});

describe('frozen detached result shape', () => {
  it('result, reference, source and document are deeply frozen', async () => {
    const fixture = await happyFixture();
    const harness = makeOwner({ catalogue: fixture.catalogue, source: fixture.source });
    const read = await readProjectFileMatchSource(
      openRequest(fixture, new AbortController().signal),
      harness.owner,
    );
    const { reference, document, pointer, body } = assertAvailable(read, 'frozen');
    expect(Object.isFrozen(read)).toBe(true);
    expect(Object.isFrozen(reference)).toBe(true);
    expect(Object.isFrozen(reference.source)).toBe(true);
    expect(Object.isFrozen(document)).toBe(true);
    expect(Object.isFrozen(body)).toBe(true);
    expect(Object.isFrozen(pointer)).toBe(true);
  });
});
