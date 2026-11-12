import { describe, expect, it } from 'vitest';
import { decodeAcceptedDirection, validDirectionSelection } from './accepted-direction';
import type {
  DirectionRevision,
  DirectionSelection,
  DirectionSource,
} from './accepted-direction';

const SCHEMA = 'mastermind.workspace_project_direction.v1';
const REPO = 'mastermindx-market-intelligence/macro';
const COMMIT = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7b8c9d0';
const WS_SHA = 'aa'.repeat(32);
const DEC_SHA = 'bb'.repeat(32);
const SELECTED: DirectionSelection = { work_ref: 'WS:ALPHA' };
const ALL_REASONS = [
  'NOT_DECLARED',
  'SOURCE_UNAVAILABLE',
  'SOURCE_CHANGED',
  'RECORD_NOT_FOUND',
  'RECORD_INVALID',
  'LINEAGE_CONFLICT',
  'LINEAGE_INCOMPLETE',
  'CONTENT_OVER_BUDGET',
];

function wsSource(overrides: Partial<DirectionSource> = {}): DirectionSource {
  return {
    repository: REPO,
    commit: COMMIT,
    path: 'agentos/workstreams/WS-ALPHA.md',
    content_sha256: WS_SHA,
    ...overrides,
  };
}

function decisionSource(ref: string, overrides: Partial<DirectionSource> = {}): DirectionSource {
  return {
    repository: REPO,
    commit: COMMIT,
    path: `agentos/decisions/${ref.replace('DEC:', 'DEC-')}.md`,
    content_sha256: DEC_SHA,
    ...overrides,
  };
}

function revision(ref: string, overrides: Record<string, unknown> = {}): DirectionRevision {
  return {
    decision_ref: ref,
    answer: `answer-${ref}`,
    rationale: `rationale-${ref}`,
    decided_by: 'macro-owner',
    decided_at: '2026-01-05',
    date_precision: 'DAY',
    predecessor: null,
    source: decisionSource(ref),
    ...overrides,
  };
}

type Chain = {
  current: DirectionRevision;
  revisions: DirectionRevision[];
  has_more: boolean;
  total_count: number | null;
};

function linkedChain(
  currentRef: string,
  historyRefs: string[],
  options: Record<string, unknown> = {},
): Chain {
  const hasMore = 'has_more' in options ? (options.has_more as boolean) : false;
  const rows: DirectionRevision[] = [revision(currentRef)];
  for (const ref of historyRefs) rows.push(revision(ref));
  for (let index = 0; index < rows.length - 1; index += 1) {
    rows[index].predecessor = rows[index + 1].decision_ref;
  }
  const last = rows[rows.length - 1];
  const defaultTail = hasMore ? 'DEC:ALPHA-UNKNOWN-TAIL' : null;
  last.predecessor = 'tail' in options ? (options.tail as string | null) : defaultTail;
  const defaultTotal = hasMore ? null : rows.length;
  const totalCount = 'total_count' in options ? options.total_count : defaultTotal;
  return {
    current: rows[0],
    revisions: rows.slice(1),
    has_more: hasMore,
    total_count: totalCount as number | null,
  };
}

function rawAvailable(
  chain: Chain,
  bodyOverrides: Record<string, unknown> = {},
  directionOverrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema: SCHEMA,
    selection: { work_ref: 'WS:ALPHA' },
    availability: 'AVAILABLE',
    source: wsSource(),
    direction: {
      work_ref: 'WS:ALPHA',
      workstream_source: wsSource(),
      current: chain.current,
      history: {
        revisions: chain.revisions,
        has_more: chain.has_more,
        total_count: chain.total_count,
      },
      ...directionOverrides,
    },
    reason_codes: [],
    ...bodyOverrides,
  };
}

function rawUnavailable(reasonCodes: unknown): Record<string, unknown> {
  return {
    schema: SCHEMA,
    selection: { work_ref: 'WS:ALPHA' },
    availability: 'UNAVAILABLE',
    source: null,
    direction: null,
    reason_codes: reasonCodes,
  };
}

function expectInvalid(raw: unknown, selected: DirectionSelection = SELECTED): void {
  let message = '';
  try {
    decodeAcceptedDirection(raw, selected);
  } catch (error) {
    message = error instanceof Error ? error.message : '';
  }
  expect(message).toBe('DIRECTION_INVALID');
}

function wireLength(body: unknown): number {
  return new TextEncoder().encode(JSON.stringify({ ok: true, result: body }) + '\n').byteLength;
}

describe('validDirectionSelection', () => {
  it('accepts well-formed selections', () => {
    expect(validDirectionSelection({ work_ref: 'WS:ALPHA' })).toBe(true);
    expect(validDirectionSelection({ work_ref: 'WS:MACRO-DIRECTION-01' })).toBe(true);
    expect(validDirectionSelection({ work_ref: 'WS:AB' })).toBe(true);
    expect(validDirectionSelection({ work_ref: 'WS:' + 'A'.repeat(64) })).toBe(true);
  });

  it('rejects malformed selectors', () => {
    const bad: unknown[] = [
      null,
      undefined,
      42,
      'WS:ALPHA',
      [],
      {},
      { work_ref: 'WS:' },
      { work_ref: 'WS:A' },
      { work_ref: 'WS:' + 'A'.repeat(65) },
      { work_ref: 'ws:alpha' },
      { work_ref: 'WS:alpha' },
      { work_ref: 'WS:ALPHA-BETA-' },
      { work_ref: 'WS:-ALPHA' },
      { work_ref: 'WS:AL--PHA' },
      { work_ref: 'WS:ALPHA/BETA' },
      { work_ref: 'WS:ALPHA BETA' },
      { work_ref: 'DEC:ALPHA' },
      { work_ref: 7 },
      { work_ref: 'WS:ALPHA', root: 'x' },
      { work_ref: 'WS:ALPHA', commit: 'x' },
      { work_ref: 'WS:ALPHA', path: 'x' },
    ];
    for (const value of bad) expect(validDirectionSelection(value)).toBe(false);
  });
});

describe('decodeAcceptedDirection available reads', () => {
  it('decodes a valid current revision with a historical chain', () => {
    const raw = rawAvailable(linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12', 'DEC:ALPHA-2025-11']));
    const read = decodeAcceptedDirection(raw, SELECTED);
    expect(read.schema).toBe(SCHEMA);
    expect(read.availability).toBe('AVAILABLE');
    expect(read.selection).toEqual({ work_ref: 'WS:ALPHA' });
    expect(read.reason_codes).toEqual([]);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.source).toEqual(wsSource());
    expect(read.direction.work_ref).toBe('WS:ALPHA');
    expect(read.direction.workstream_source).toEqual(wsSource());
    expect(read.direction.current.decision_ref).toBe('DEC:ALPHA-2026-01');
    expect(read.direction.current.source).toEqual(decisionSource('DEC:ALPHA-2026-01'));
    expect(
      read.direction.history.revisions.map((row) => row.decision_ref),
    ).toEqual(['DEC:ALPHA-2025-12', 'DEC:ALPHA-2025-11']);
    expect(read.direction.history.has_more).toBe(false);
    expect(read.direction.history.total_count).toBe(3);
  });

  it('decodes the maximum seven-row history', () => {
    const refs = [
      'DEC:ALPHA-2026-01',
      'DEC:ALPHA-2025-12',
      'DEC:ALPHA-2025-11',
      'DEC:ALPHA-2025-10',
      'DEC:ALPHA-2025-09',
      'DEC:ALPHA-2025-08',
      'DEC:ALPHA-2025-07',
      'DEC:ALPHA-2025-06',
    ];
    const raw = rawAvailable(linkedChain(refs[0], refs.slice(1)));
    const read = decodeAcceptedDirection(raw, SELECTED);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.direction.history.revisions.length).toBe(7);
    expect(read.direction.history.total_count).toBe(8);
  });

  it('decodes 8 visible rows of a longer lineage with an unknown total', () => {
    const refs = [
      'DEC:ALPHA-2026-01',
      'DEC:ALPHA-2025-12',
      'DEC:ALPHA-2025-11',
      'DEC:ALPHA-2025-10',
      'DEC:ALPHA-2025-09',
      'DEC:ALPHA-2025-08',
      'DEC:ALPHA-2025-07',
      'DEC:ALPHA-2025-06',
    ];
    const raw = rawAvailable(
      linkedChain(refs[0], refs.slice(1), {
        has_more: true,
        total_count: null,
        tail: 'DEC:ALPHA-2025-05',
      }),
    );
    const read = decodeAcceptedDirection(raw, SELECTED);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.direction.history.has_more).toBe(true);
    expect(read.direction.history.total_count).toBe(null);
    expect(read.direction.history.revisions.length).toBe(7);
    const last = read.direction.history.revisions[6];
    expect(last.predecessor).toBe('DEC:ALPHA-2025-05');
  });

  it('decodes a single-row lineage', () => {
    const read = decodeAcceptedDirection(
      rawAvailable(linkedChain('DEC:ALPHA-2026-01', [], { total_count: 1 })),
      SELECTED,
    );
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.direction.history.revisions).toEqual([]);
    expect(read.direction.history.total_count).toBe(1);
    expect(read.direction.current.predecessor).toBe(null);
  });

  it('decodes a truncated single-row lineage with an unseen tail', () => {
    const raw = rawAvailable(
      linkedChain('DEC:ALPHA-2026-01', [], {
        has_more: true,
        total_count: null,
        tail: 'DEC:ALPHA-UNKNOWN',
      }),
    );
    expect(decodeAcceptedDirection(raw, SELECTED).availability).toBe('AVAILABLE');
  });

  it('keeps the literal owner pointer instead of electing by date', () => {
    const current = revision('DEC:ALPHA-2026-01', {
      decided_at: '2026-01-05',
      predecessor: 'DEC:ALPHA-2025-12',
    });
    const laterDated = revision('DEC:ALPHA-2025-12', { decided_at: '2027-06-06', predecessor: null });
    const raw = rawAvailable(linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']), {}, {
      current,
      history: { revisions: [laterDated], has_more: false, total_count: 2 },
    });
    const read = decodeAcceptedDirection(raw, SELECTED);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.direction.current.decision_ref).toBe('DEC:ALPHA-2026-01');
    expect(read.direction.current.decided_at).toBe('2026-01-05');
    expect(read.direction.history.revisions[0].decided_at).toBe('2027-06-06');
  });

  it('binds paths and refs to the selected work key', () => {
    const selected: DirectionSelection = { work_ref: 'WS:BETA-01' };
    const betaSource = wsSource({ path: 'agentos/workstreams/WS-BETA-01.md' });
    const raw: Record<string, unknown> = {
      schema: SCHEMA,
      selection: { work_ref: 'WS:BETA-01' },
      availability: 'AVAILABLE',
      source: betaSource,
      direction: {
        work_ref: 'WS:BETA-01',
        workstream_source: betaSource,
        current: revision('DEC:BETA-01-R1'),
        history: { revisions: [], has_more: false, total_count: 1 },
      },
      reason_codes: [],
    };
    const read = decodeAcceptedDirection(raw, selected);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.source.path).toBe('agentos/workstreams/WS-BETA-01.md');
    expect(read.direction.workstream_source.path).toBe('agentos/workstreams/WS-BETA-01.md');
    expect(read.direction.current.source.path).toBe('agentos/decisions/DEC-BETA-01-R1.md');
  });
});

describe('decodeAcceptedDirection rejections', () => {
  it('rejects unknown read states', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    for (const availability of ['UNKNOWN', 'AVAILABLE ', 'available', 'PARTIAL', 1, null, true]) {
      expectInvalid(rawAvailable(chain, { availability }));
    }
    const missing = rawAvailable(chain);
    delete missing.availability;
    expectInvalid(missing);
  });

  it('rejects bodies with extra or private keys', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    for (const key of ['raw_body', 'current', 'acceptance', 'runtime_grants', 'private', 'debug', 'ok', 'result']) {
      expectInvalid(rawAvailable(chain, { [key]: 'x' }));
    }
    expectInvalid(rawAvailable(chain, {}, { extra: 1 }));
    expectInvalid(rawAvailable(chain, { selection: { work_ref: 'WS:ALPHA', job: 'J1' } }));
    expectInvalid(
      rawAvailable(chain, { source: { ...wsSource(), root: 'x' } }),
    );
    expectInvalid(
      rawAvailable(chain, {}, {
        current: { ...revision('DEC:ALPHA-2026-01', { predecessor: 'DEC:ALPHA-2025-12' }), note: 'x' },
      }),
    );
    const read = decodeAcceptedDirection(rawAvailable(chain), SELECTED);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expectInvalid(
      rawAvailable(chain, {}, {
        history: {
          revisions: read.direction.history.revisions,
          has_more: false,
          total_count: 3,
          cursor: 'x',
        },
      }),
    );
    expectInvalid(rawUnavailable(['RECORD_NOT_FOUND', { tag: 'x' }]));
  });

  it('rejects wrong schema and envelope-shaped payloads', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    expectInvalid(rawAvailable(chain, { schema: 'mastermind.workspace_project_direction.v2' }));
    expectInvalid(rawAvailable(chain, { schema: 1 }));
    const missing = rawAvailable(chain);
    delete missing.schema;
    expectInvalid(missing);
    expectInvalid({ ok: true, result: rawAvailable(chain) });
    expectInvalid(null);
    expectInvalid('body');
    expectInvalid([]);
    expectInvalid(rawAvailable(chain, { selection: 5 }));
    expectInvalid(rawAvailable(chain, { selection: { work_ref: 'WS:ALPHA', extra: 1 } }));
    const noSelection = rawAvailable(chain);
    delete noSelection.selection;
    expectInvalid(noSelection);
  });

  it('rejects a body selection that differs from the requested selection', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    expectInvalid(rawAvailable(chain), { work_ref: 'WS:BETA' });
    expectInvalid(rawAvailable(chain, { selection: { work_ref: 'WS:BETA' } }));
    expectInvalid(rawAvailable(chain, { selection: { work_ref: 'ws:alpha' } }));
  });

  it('rejects malformed selectors passed to the decoder', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    expectInvalid(rawAvailable(chain), 'WS:ALPHA' as unknown as DirectionSelection);
    expectInvalid(rawAvailable(chain), null as unknown as DirectionSelection);
    expectInvalid(
      rawAvailable(chain),
      { work_ref: 'WS:ALPHA', root: 'x' } as unknown as DirectionSelection,
    );
  });

  it('enforces source identity, commit and digest formats', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    expectInvalid(rawAvailable(chain, { source: wsSource({ repository: 'other/repo' }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ commit: COMMIT.slice(1) }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ commit: COMMIT + 'a' }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ commit: COMMIT.toUpperCase() }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ commit: 'g'.repeat(40) }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ content_sha256: WS_SHA.slice(1) }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ content_sha256: WS_SHA.toUpperCase() }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ path: 'agentos/workstreams/WS-BETA.md' }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ path: '/agentos/workstreams/WS-ALPHA.md' }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ path: 'agentos/jobs/WS-ALPHA.md' }) }));
    expectInvalid(rawAvailable(chain, { source: wsSource({ path: 'agentos/workstreams/WS-ALPHA.md.txt' }) }));
    expectInvalid(
      rawAvailable(chain, {}, {
        workstream_source: wsSource({ content_sha256: 'cc'.repeat(32) }),
      }),
    );
    expectInvalid(rawAvailable(chain, {}, { work_ref: 'WS:BETA' }));
    expectInvalid(rawAvailable(chain, {}, { workstream_source: null }));
    expectInvalid(rawAvailable(chain, {}, { current: null }));
    expectInvalid(rawAvailable(chain, {}, { history: null }));
  });

  it('cross-binds each revision row source to its own decision record', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    expectInvalid(
      rawAvailable(chain, {}, {
        current: revision('DEC:ALPHA-2026-01', {
          predecessor: 'DEC:ALPHA-2025-12',
          source: decisionSource('DEC:ALPHA-2026-01', { path: 'agentos/decisions/DEC-ALPHA-2025-12.md' }),
        }),
      }),
    );
    expectInvalid(
      rawAvailable(chain, {}, {
        current: revision('DEC:ALPHA-2026-01', {
          predecessor: 'DEC:ALPHA-2025-12',
          source: decisionSource('DEC:ALPHA-2026-01', { commit: 'b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2' }),
        }),
      }),
    );
    expectInvalid(
      rawAvailable(chain, {}, {
        current: revision('DEC:ALPHA-2026-01', {
          predecessor: 'DEC:ALPHA-2025-12',
          source: decisionSource('DEC:ALPHA-2026-01', { repository: 'other/repo' }),
        }),
      }),
    );
    expectInvalid(
      rawAvailable(chain, {}, {
        current: revision('DEC:ALPHA-2026-01', {
          predecessor: 'DEC:ALPHA-2025-12',
          source: decisionSource('DEC:ALPHA-2026-01', { content_sha256: 'dd'.repeat(31) + 'g' }),
        }),
      }),
    );
    const raw = rawAvailable(chain);
    const read = decodeAcceptedDirection(raw, SELECTED);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.direction.history.revisions[0].source.path).toBe(
      'agentos/decisions/DEC-ALPHA-2025-12.md',
    );
  });

  it('enforces DAY date precision and real calendar dates', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    const dated = (decidedAt: unknown, precision: unknown = 'DAY'): Record<string, unknown> =>
      rawAvailable(chain, {}, {
        current: revision('DEC:ALPHA-2026-01', {
          decided_at: decidedAt as string,
          date_precision: precision as 'DAY',
          predecessor: 'DEC:ALPHA-2025-12',
        }),
      });
    expect(decodeAcceptedDirection(
      rawAvailable(chain, {}, {
        current: revision('DEC:ALPHA-2026-01', {
          decided_at: '2024-02-29',
          predecessor: 'DEC:ALPHA-2025-12',
        }),
      }),
      SELECTED,
    ).availability).toBe('AVAILABLE');
    expectInvalid(dated('2023-02-29'));
    expectInvalid(dated('2026-02-30'));
    expectInvalid(dated('2026-04-31'));
    expectInvalid(dated('2026-13-01'));
    expectInvalid(dated('2026-00-10'));
    expectInvalid(dated('2026-01-00'));
    expectInvalid(dated('2026-01-32'));
    expectInvalid(dated('2026-1-05'));
    expectInvalid(dated('2026-01-05T00:00:00Z'));
    expectInvalid(dated('20260105'));
    expectInvalid(dated(1767225600000));
    expectInvalid(dated('2026-01-05', 'HOUR'));
    expectInvalid(dated('2026-01-05', 'DAY '.trim() + ' '));
    expectInvalid(dated('2026-01-05', 2));
    expectInvalid(dated('2026-01-05', null));
  });

  it('enforces text and owner bounds', () => {
    const chain = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    const withCurrent = (current: DirectionRevision): Record<string, unknown> =>
      rawAvailable(chain, {}, { current });
    expect(
      decodeAcceptedDirection(
        withCurrent(revision('DEC:ALPHA-2026-01', {
          answer: 'x'.repeat(4096),
          rationale: 'y'.repeat(4096),
          decided_by: 'z'.repeat(256),
          predecessor: 'DEC:ALPHA-2025-12',
        })),
        SELECTED,
      ).availability,
    ).toBe('AVAILABLE');
    expectInvalid(withCurrent(revision('DEC:ALPHA-2026-01', { answer: '', predecessor: 'DEC:ALPHA-2025-12' })));
    expectInvalid(withCurrent(revision('DEC:ALPHA-2026-01', { answer: 'x'.repeat(4097), predecessor: 'DEC:ALPHA-2025-12' })));
    expectInvalid(withCurrent(revision('DEC:ALPHA-2026-01', { rationale: '', predecessor: 'DEC:ALPHA-2025-12' })));
    expectInvalid(withCurrent(revision('DEC:ALPHA-2026-01', { rationale: 'y'.repeat(4097), predecessor: 'DEC:ALPHA-2025-12' })));
    expectInvalid(withCurrent(revision('DEC:ALPHA-2026-01', { decided_by: 'z'.repeat(257), predecessor: 'DEC:ALPHA-2025-12' })));
    expectInvalid(withCurrent(revision('DEC:ALPHA-2026-01', { answer: 5, predecessor: 'DEC:ALPHA-2025-12' })));
  });

  it('rejects broken, cyclic and duplicated history', () => {
    const broken = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']);
    broken.revisions[0].predecessor = 'DEC:ALPHA-WRONG';
    expectInvalid(rawAvailable(broken));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']), {}, {
      current: revision('DEC:ALPHA-2026-01', { predecessor: 'DEC:ALPHA-2026-01' }),
    }));
    const cyclic = linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B', 'DEC:ALPHA-C'], {
      has_more: true,
      total_count: null,
      tail: 'DEC:ALPHA-A',
    });
    expectInvalid(rawAvailable(cyclic));
    const cycleClosed = linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B']);
    cycleClosed.revisions[0].predecessor = 'DEC:ALPHA-A';
    expectInvalid(rawAvailable(cycleClosed));
    const duplicated = linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B', 'DEC:ALPHA-B']);
    expectInvalid(rawAvailable(duplicated));
    const shadowsCurrent = linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-A']);
    expectInvalid(rawAvailable(shadowsCurrent));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:X'])));
  });

  it('rejects dangling visible chains and has_more/total_count contradictions', () => {
    const danglingVisible = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12'], { tail: 'DEC:ALPHA-2025-11' });
    expectInvalid(rawAvailable(danglingVisible));
    const closedTailClaim = linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12'], {
      has_more: true,
      total_count: null,
      tail: null,
    });
    expectInvalid(rawAvailable(closedTailClaim));
    const tailInsideView = linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B', 'DEC:ALPHA-C'], {
      has_more: true,
      total_count: null,
      tail: 'DEC:ALPHA-B',
    });
    expectInvalid(rawAvailable(tailInsideView));
    const tailEqualsSelf = linkedChain('DEC:ALPHA-A', [], {
      has_more: true,
      total_count: null,
      tail: 'DEC:ALPHA-A',
    });
    expectInvalid(rawAvailable(tailEqualsSelf));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { has_more: true, total_count: 9, tail: 'DEC:ALPHA-Z' })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { total_count: 4 })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { total_count: null })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { total_count: 2.5 })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { total_count: '2' })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { has_more: 1 })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { has_more: 'false' })));
    expectInvalid(rawAvailable(linkedChain('DEC:ALPHA-A', ['DEC:ALPHA-B'], { has_more: null })));
    const eightRows = linkedChain('DEC:ALPHA-ROOT', [
      'DEC:ALPHA-R1',
      'DEC:ALPHA-R2',
      'DEC:ALPHA-R3',
      'DEC:ALPHA-R4',
      'DEC:ALPHA-R5',
      'DEC:ALPHA-R6',
      'DEC:ALPHA-R7',
      'DEC:ALPHA-R8',
    ]);
    expectInvalid(rawAvailable(eightRows));
  });
});

describe('decodeAcceptedDirection unavailable reads', () => {
  it('decodes every declared unavailability reason', () => {
    for (const reason of ALL_REASONS) {
      const read = decodeAcceptedDirection(rawUnavailable([reason]), SELECTED);
      expect(read.availability).toBe('UNAVAILABLE');
      if (read.availability !== 'UNAVAILABLE') throw new Error('unreachable');
      expect(read.schema).toBe(SCHEMA);
      expect(read.selection).toEqual({ work_ref: 'WS:ALPHA' });
      expect(read.source).toBe(null);
      expect(read.direction).toBe(null);
      expect(read.reason_codes).toEqual([reason]);
    }
  });

  it('rejects unknown or malformed reason codes and leaked state', () => {
    for (const reason of ALL_REASONS) expectInvalid(rawUnavailable([reason, reason]));
    expectInvalid(rawUnavailable([]));
    expectInvalid(rawUnavailable(['SOURCE_TIMEOUT']));
    expectInvalid(rawUnavailable(['record_not_found']));
    expectInvalid(rawUnavailable([7]));
    expectInvalid(rawUnavailable([null]));
    expectInvalid(rawUnavailable('RECORD_NOT_FOUND'));
    expectInvalid(rawUnavailable({ code: 'RECORD_NOT_FOUND' }));
    expectInvalid({
      schema: SCHEMA,
      selection: { work_ref: 'WS:ALPHA' },
      availability: 'UNAVAILABLE',
      source: wsSource(),
      direction: null,
      reason_codes: ['SOURCE_UNAVAILABLE'],
    });
    expectInvalid({
      schema: SCHEMA,
      selection: { work_ref: 'WS:ALPHA' },
      availability: 'UNAVAILABLE',
      source: null,
      direction: { work_ref: 'WS:ALPHA' },
      reason_codes: ['SOURCE_UNAVAILABLE'],
    });
    expectInvalid({
      schema: SCHEMA,
      selection: { work_ref: 'WS:BETA' },
      availability: 'UNAVAILABLE',
      source: null,
      direction: null,
      reason_codes: ['SOURCE_UNAVAILABLE'],
    });
  });
});

describe('wire budget', () => {
  it('rejects bodies whose serialized envelope exceeds the byte cap', () => {
    const row = (ref: string, predecessor: string | null): DirectionRevision =>
      revision(ref, { answer: 'あ'.repeat(4096), rationale: 'あ'.repeat(4096), predecessor });
    const rows = [row('DEC:ALPHA-2026-03', 'DEC:ALPHA-2026-02'), row('DEC:ALPHA-2026-02', 'DEC:ALPHA-2026-01'), row('DEC:ALPHA-2026-01', null)];
    const raw: Record<string, unknown> = {
      schema: SCHEMA,
      selection: { work_ref: 'WS:ALPHA' },
      availability: 'AVAILABLE',
      source: wsSource(),
      direction: {
        work_ref: 'WS:ALPHA',
        workstream_source: wsSource(),
        current: rows[0],
        history: { revisions: rows.slice(1), has_more: false, total_count: 3 },
      },
      reason_codes: [],
    };
    expect(wireLength(raw)).toBeGreaterThan(65536);
    expectInvalid(raw);
  });

  it('accepts a fully loaded ascii body within the byte cap', () => {
    const row = (ref: string, predecessor: string | null): DirectionRevision =>
      revision(ref, { answer: 'x'.repeat(4096), rationale: 'x'.repeat(4096), predecessor });
    const rows = [
      row('DEC:ALPHA-2026-04', 'DEC:ALPHA-2026-03'),
      row('DEC:ALPHA-2026-03', 'DEC:ALPHA-2026-02'),
      row('DEC:ALPHA-2026-02', 'DEC:ALPHA-2026-01'),
      row('DEC:ALPHA-2026-01', null),
    ];
    const raw: Record<string, unknown> = {
      schema: SCHEMA,
      selection: { work_ref: 'WS:ALPHA' },
      availability: 'AVAILABLE',
      source: wsSource(),
      direction: {
        work_ref: 'WS:ALPHA',
        workstream_source: wsSource(),
        current: rows[0],
        history: { revisions: rows.slice(1), has_more: false, total_count: 4 },
      },
      reason_codes: [],
    };
    expect(wireLength(raw)).toBeLessThanOrEqual(65536);
    expect(decodeAcceptedDirection(raw, SELECTED).availability).toBe('AVAILABLE');
  });
});

describe('detachment and freezing', () => {
  it('returns a deeply detached read', () => {
    const raw = rawAvailable(linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12']));
    const read = decodeAcceptedDirection(raw, SELECTED);
    const before = JSON.stringify(read);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(read.direction).not.toBe(raw.direction);
    expect(read.source).not.toBe(raw.source);
    (raw.direction as Record<string, unknown>).current = 'tampered';
    raw.source = 'tampered';
    const history = (raw.direction as Record<string, unknown>).history as Record<string, unknown>;
    (history.revisions as unknown[]).push('tampered');
    history.has_more = true;
    raw.selection = { work_ref: 'WS:TAMPERED' };
    const selected: DirectionSelection = { work_ref: 'WS:ALPHA' };
    selected.work_ref = 'WS:TAMPERED';
    expect(JSON.stringify(read)).toBe(before);
  });

  it('freezes the decoded read', () => {
    const read = decodeAcceptedDirection(
      rawAvailable(linkedChain('DEC:ALPHA-2026-01', ['DEC:ALPHA-2025-12'])),
      SELECTED,
    );
    expect(Object.isFrozen(read)).toBe(true);
    if (read.availability !== 'AVAILABLE') throw new Error('unreachable');
    expect(Object.isFrozen(read.direction.current.source)).toBe(true);
    expect(Object.isFrozen(read.direction.history.revisions)).toBe(true);
    const unavailable = decodeAcceptedDirection(rawUnavailable(['NOT_DECLARED']), SELECTED);
    expect(Object.isFrozen(unavailable.reason_codes)).toBe(true);
  });
});

describe('error shape', () => {
  it('throws a value-free DIRECTION_INVALID error', () => {
    let thrown: unknown;
    try {
      decodeAcceptedDirection({ nonsense: true }, SELECTED);
    } catch (error) {
      thrown = error;
    }
    expect(thrown instanceof Error).toBe(true);
    const err = thrown as Error;
    expect(err.message).toBe('DIRECTION_INVALID');
    expect(err.name).toBe('Error');
    expect(Object.keys(err).length).toBe(0);
    expect(String(err)).toBe('Error: DIRECTION_INVALID');
  });
});


describe('native owner UTF-8 and calendar parity', () => {
  it('bounds fields by UTF-8 bytes and rejects blank actors and unpaired surrogates', () => {
    const chain = linkedChain('DEC:ALPHA-CURRENT', []);
    for (const overrides of [{ answer: '中'.repeat(1366) }, { decided_by: '中'.repeat(86) },
      { answer: ' ' }, { decided_by: '' }, { rationale: '\ud800' }]) {
      expectInvalid(rawAvailable({ ...chain, current: revision('DEC:ALPHA-CURRENT', overrides) }));
    }
    const raw = rawAvailable({ ...chain, current: revision('DEC:ALPHA-CURRENT', { answer: '中'.repeat(1365) + 'a', decided_by: '中'.repeat(85) + 'a' }) });
    expect(decodeAcceptedDirection(raw, SELECTED).availability).toBe('AVAILABLE');
  });
  it('rejects year zero and retains value-free errors for exceptional raw objects', () => {
    const chain = linkedChain('DEC:ALPHA-CURRENT', []);
    expectInvalid(rawAvailable({ ...chain, current: revision('DEC:ALPHA-CURRENT', { decided_at: '0000-01-01' }) }));
    const raw = rawAvailable(chain);
    Object.defineProperty(raw, 'schema', { enumerable: true, get: () => { throw new Error('private source diagnostic'); } });
    expectInvalid(raw);
  });
  it('rejects a wire-over-budget body whose every individual field remains valid', () => {
    const chain = linkedChain('DEC:ALPHA-CURRENT', Array.from({ length: 7 }, (_, n) => `DEC:ALPHA-REV-${n}`));
    for (const row of [chain.current, ...chain.revisions]) { row.answer = 'x'.repeat(4096); row.rationale = 'y'.repeat(4096); }
    const raw = rawAvailable(chain);
    expect(wireLength(raw)).toBeGreaterThan(65536);
    expectInvalid(raw);
  });
});
