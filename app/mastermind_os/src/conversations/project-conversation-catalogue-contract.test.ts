import { describe, expect, it } from 'vitest';
import {
  decodeProjectConversationCatalogue,
  decodeProjectConversationRead,
  validateProjectConversationSelection,
  type ProjectConversationCatalogue,
  type ProjectConversationRead,
  type ProjectConversationRequest,
  type ProjectConversationSelection,
} from './project-conversation-catalogue-contract';

const WORK_REF = 'WS:MM-PROJ-1';
const CATALOGUE_SCHEMA = 'mastermind.project_conversation_catalogue.v1';
const READ_SCHEMA = 'mastermind.project_conversation_read.v1';
const UNAVAILABLE = /PROJECT_CONVERSATION_UNAVAILABLE/;

function must<T>(value: T | undefined | null): T {
  if (value === undefined || value === null) {
    throw new Error('test fixture missing value');
  }
  return value;
}

function hex64(seed: number): string {
  return seed.toString(16).padStart(64, '0');
}

function hex40(seed: number): string {
  return seed.toString(16).padStart(40, '0');
}

function conversationRef(seed: number): string {
  return `conversation-${hex64(seed)}`;
}

function readRef(seed: number): string {
  return `session-reply-${hex64(seed)}`;
}

function messageKey(seed: number): string {
  return `asd-native-reply-${hex40(seed)}`;
}

function fingerprint(seed: number): string {
  return hex64(900 + seed);
}

function request(seed: number): ProjectConversationRequest {
  return { read_ref: readRef(seed), request_revision: hex64(seed) };
}

function requestList(...seeds: number[]): ProjectConversationRequest[] {
  return seeds.map((seed) => request(seed));
}

interface CatalogueOverrides {
  workRef?: string;
  rows?: number[][];
  nextCursor?: string | null;
  highWater?: number;
  revision?: string;
  lastRequestAt?: string;
  title?: unknown;
}

function makeCatalogueRaw(
  overrides: CatalogueOverrides = {},
): Record<string, unknown> {
  const rowSeeds = overrides.rows ?? [[11, 12], [13], [14, 15, 16]];
  const conversations = rowSeeds.map((seeds, rowIndex) => ({
    conversation_ref: conversationRef(rowIndex + 1),
    revision: overrides.revision ?? hex64(rowIndex + 21),
    root_job_id: `JOB-7${rowIndex}00`,
    title: overrides.title ?? null,
    last_request_at: overrides.lastRequestAt ?? `2026-03-0${rowIndex + 1}T08:30:00Z`,
    requests: seeds.map((seed) => request(seed)),
  }));
  return {
    schema: CATALOGUE_SCHEMA,
    work_ref: overrides.workRef ?? WORK_REF,
    coverage: 'PARTIAL',
    conversations,
    next_cursor: overrides.nextCursor ?? null,
    high_water: overrides.highWater ?? 42,
    can_send: false,
  };
}

interface ReadOverrides {
  workRef?: string;
  conversationRef?: string;
  revision?: string;
  rootJobId?: string;
  requests?: ProjectConversationRequest[];
  turns?: unknown[];
  title?: unknown;
}

function defaultReadRequests(): ProjectConversationRequest[] {
  return requestList(31, 32, 33);
}

function availableTurn(
  entry: ProjectConversationRequest,
  index: number,
): Record<string, unknown> {
  return {
    read_ref: entry.read_ref,
    request_revision: entry.request_revision,
    requested_at: `2026-03-01T10:00:0${index % 10}Z`,
    instruction: 'Continue the native session grouping work now',
    stop_condition: 'Stop when the acceptance evidence is green',
    reply: {
      text: 'Reply text with unicode 中文 ✓ \t and  spacing preserved',
      next_step: 'Next step: run the focused suite',
      read_ref: entry.read_ref,
      message_key: messageKey(index + 1),
      fingerprint: fingerprint(index + 1),
      parent_consumed: false,
    },
    state: 'AVAILABLE',
  };
}

function unavailableTurn(
  entry: ProjectConversationRequest,
  index: number,
): Record<string, unknown> {
  return {
    read_ref: entry.read_ref,
    request_revision: entry.request_revision,
    requested_at: `2026-03-01T11:00:0${index % 10}Z`,
    instruction: null,
    stop_condition: null,
    reply: null,
    state: 'UNAVAILABLE',
  };
}

function makeReadRaw(
  overrides: ReadOverrides = {},
): Record<string, unknown> {
  const requests = overrides.requests ?? defaultReadRequests();
  const turns =
    overrides.turns ??
    requests.map((entry, index) =>
      index === 2 ? unavailableTurn(entry, index) : availableTurn(entry, index),
    );
  return {
    schema: READ_SCHEMA,
    work_ref: overrides.workRef ?? WORK_REF,
    conversation_ref: overrides.conversationRef ?? conversationRef(1),
    revision: overrides.revision ?? hex64(21),
    root_job_id: overrides.rootJobId ?? 'JOB-700',
    title: overrides.title ?? null,
    coverage: 'PARTIAL',
    can_send: false,
    turns,
  };
}

interface ExpectedOverrides {
  workRef?: string;
  conversationRef?: string;
  revision?: string;
  requests?: ProjectConversationRequest[];
}

function makeExpected(
  overrides: ExpectedOverrides = {},
): {
  workRef: string;
  conversationRef: string;
  revision: string;
  requests: ProjectConversationRequest[];
} {
  return {
    workRef: overrides.workRef ?? WORK_REF,
    conversationRef: overrides.conversationRef ?? conversationRef(1),
    revision: overrides.revision ?? hex64(21),
    requests: overrides.requests ?? defaultReadRequests(),
  };
}

interface SelectionOverrides {
  workRef?: string;
  conversationRef?: string;
  revision?: string;
  requests?: ProjectConversationRequest[];
}

function makeSelectionRaw(
  overrides: SelectionOverrides = {},
): Record<string, unknown> {
  return {
    work_ref: overrides.workRef ?? WORK_REF,
    conversation_ref: overrides.conversationRef ?? conversationRef(1),
    revision: overrides.revision ?? hex64(21),
    requests: overrides.requests ?? requestList(31, 32),
  };
}

describe('decodeProjectConversationCatalogue', () => {
  it('decodes a multi-session page with varied request counts', () => {
    const raw = makeCatalogueRaw({
      rows: [[11, 12], [13], [14, 15, 16]],
      nextCursor: 'aGVsbG8xMjM0NQ',
      highWater: 7,
    });
    const decoded: ProjectConversationCatalogue =
      decodeProjectConversationCatalogue(raw, WORK_REF);
    expect(decoded.schema).toBe(CATALOGUE_SCHEMA);
    expect(decoded.work_ref).toBe(WORK_REF);
    expect(decoded.coverage).toBe('PARTIAL');
    expect(decoded.can_send).toBe(false);
    expect(decoded.high_water).toBe(7);
    expect(decoded.next_cursor).toBe('aGVsbG8xMjM0NQ');
    expect(decoded.conversations.length).toBe(3);
    const firstRow = must(decoded.conversations[0]);
    expect(firstRow.conversation_ref).toBe(conversationRef(1));
    expect(firstRow.root_job_id).toBe('JOB-7000');
    expect(firstRow.title).toBeNull();
    expect(firstRow.last_request_at).toBe('2026-03-01T08:30:00Z');
    expect(firstRow.requests.length).toBe(2);
    expect(must(firstRow.requests[0]).read_ref).toBe(readRef(11));
    const thirdRow = must(decoded.conversations[2]);
    expect(thirdRow.requests.length).toBe(3);
  });

  it('keeps snake_case keys with exact closed key sets', () => {
    const decoded = decodeProjectConversationCatalogue(
      makeCatalogueRaw({ rows: [[11]] }),
      WORK_REF,
    );
    expect(Object.keys(decoded)).toEqual([
      'schema',
      'work_ref',
      'coverage',
      'conversations',
      'next_cursor',
      'high_water',
      'can_send',
    ]);
    const row = must(decoded.conversations[0]);
    expect(Object.keys(row)).toEqual([
      'conversation_ref',
      'revision',
      'root_job_id',
      'title',
      'last_request_at',
      'requests',
    ]);
    expect(Object.keys(must(row.requests[0]))).toEqual([
      'read_ref',
      'request_revision',
    ]);
  });

  it('returns detached deep-frozen output', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    const decoded = decodeProjectConversationCatalogue(raw, WORK_REF);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded.conversations)).toBe(true);
    expect(Object.isFrozen(must(decoded.conversations[0]))).toBe(true);
    expect(
      Object.isFrozen(must(must(decoded.conversations[0]).requests[0])),
    ).toBe(true);
    const mutableRow = must((raw.conversations as Record<string, unknown>[])[0]);
    mutableRow.revision = 'tampered';
    expect(must(decoded.conversations[0]).revision).not.toBe('tampered');
  });

  it('accepts null-prototype plain containers', () => {
    const row = Object.assign(Object.create(null), {
      conversation_ref: conversationRef(1),
      revision: hex64(21),
      root_job_id: 'JOB-700',
      title: null,
      last_request_at: '2026-03-01T08:30:00Z',
      requests: [
        Object.assign(Object.create(null), {
          read_ref: readRef(11),
          request_revision: hex64(11),
        }),
      ],
    });
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.conversations = [row];
    const decoded = decodeProjectConversationCatalogue(raw, WORK_REF);
    expect(decoded.conversations.length).toBe(1);
  });

  it('rejects a foreign work_ref scope', () => {
    expect(() =>
      decodeProjectConversationCatalogue(
        makeCatalogueRaw({ workRef: 'WS:OTHER-2' }),
        WORK_REF,
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a grammatically invalid expectedWorkRef', () => {
    expect(() =>
      decodeProjectConversationCatalogue(makeCatalogueRaw(), 'BADREF'),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a foreign schema', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.schema = 'mastermind.saved_reply_catalogue.v1';
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects extra fields at the root', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.model = 'claude-opus-5-5';
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects extra fields inside a row', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    const row = must((raw.conversations as Record<string, unknown>[])[0]);
    row.session_path = '/sessions/abc';
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects duplicate conversation_ref values', () => {
    const raw = makeCatalogueRaw({ rows: [[11], [12]] });
    const rows = raw.conversations as Record<string, unknown>[];
    must(rows[1]).conversation_ref = must(rows[0]).conversation_ref;
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects duplicate read_ref across the page', () => {
    const raw = makeCatalogueRaw({ rows: [[11], [11]] });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects duplicate read_ref inside one row', () => {
    const raw = makeCatalogueRaw({ rows: [[11, 11]] });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a faked can_send flag', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.can_send = true;
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a non-null row title', () => {
    const raw = makeCatalogueRaw({ rows: [[11]], title: 'Invented title' });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects coverage other than PARTIAL', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.coverage = 'FULL';
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects invalid high_water values', () => {
    for (const highWater of [-1, 1.5, '3', null]) {
      const raw = makeCatalogueRaw({ rows: [[11]] });
      raw.high_water = highWater as unknown;
      expect(() =>
        decodeProjectConversationCatalogue(raw, WORK_REF),
      ).toThrowError(UNAVAILABLE);
    }
  });

  it('rejects invalid cursor grammar and oversized cursors', () => {
    const slashCursor = makeCatalogueRaw({ rows: [[11]], nextCursor: 'abc/def+' });
    expect(() =>
      decodeProjectConversationCatalogue(slashCursor, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const emptyCursor = makeCatalogueRaw({ rows: [[11]], nextCursor: '' });
    expect(() =>
      decodeProjectConversationCatalogue(emptyCursor, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const oversized = makeCatalogueRaw({
      rows: [[11]],
      nextCursor: 'a'.repeat(2049),
    });
    expect(() =>
      decodeProjectConversationCatalogue(oversized, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('accepts a base64url cursor and preserves it', () => {
    const decoded = decodeProjectConversationCatalogue(
      makeCatalogueRaw({ rows: [[11]], nextCursor: 'Ab_-1=' }),
      WORK_REF,
    );
    expect(decoded.next_cursor).toBe('Ab_-1=');
  });

  it('rejects impossible calendar timestamps', () => {
    const invalidDay = makeCatalogueRaw({
      rows: [[11]],
      lastRequestAt: '2026-02-30T08:30:00Z',
    });
    expect(() =>
      decodeProjectConversationCatalogue(invalidDay, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const badMonth = makeCatalogueRaw({
      rows: [[11]],
      lastRequestAt: '2026-13-01T08:30:00Z',
    });
    expect(() =>
      decodeProjectConversationCatalogue(badMonth, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const badHour = makeCatalogueRaw({
      rows: [[11]],
      lastRequestAt: '2026-03-01T24:30:00Z',
    });
    expect(() =>
      decodeProjectConversationCatalogue(badHour, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const noZone = makeCatalogueRaw({
      rows: [[11]],
      lastRequestAt: '2026-03-01T08:30:00',
    });
    expect(() =>
      decodeProjectConversationCatalogue(noZone, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('accepts a leap day and fractional seconds', () => {
    const decoded = decodeProjectConversationCatalogue(
      makeCatalogueRaw({
        rows: [[11]],
        lastRequestAt: '2028-02-29T08:30:00.250Z',
      }),
      WORK_REF,
    );
    expect(must(decoded.conversations[0]).last_request_at).toBe(
      '2028-02-29T08:30:00.250Z',
    );
  });

  it('rejects non-lowercase or wrong-length revision hex', () => {
    const raw = makeCatalogueRaw({ rows: [[11]], revision: hex64(0xabcdef).toUpperCase() });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const short = makeCatalogueRaw({ rows: [[11]], revision: hex64(21).slice(1) });
    expect(() =>
      decodeProjectConversationCatalogue(short, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a page over 8 sessions and an empty page', () => {
    const tooMany = makeCatalogueRaw({
      rows: Array.from({ length: 9 }, (_, index) => [index + 1]),
    });
    expect(() =>
      decodeProjectConversationCatalogue(tooMany, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const empty = makeCatalogueRaw({ rows: [] });
    expect(() =>
      decodeProjectConversationCatalogue(empty, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects rows with zero or over-limit requests', () => {
    const none = makeCatalogueRaw({ rows: [[]] });
    expect(() =>
      decodeProjectConversationCatalogue(none, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    const five = makeCatalogueRaw({ rows: [[11, 12, 13, 14, 15]] });
    expect(() =>
      decodeProjectConversationCatalogue(five, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects hostile getters without invoking them', () => {
    let invocations = 0;
    const raw = makeCatalogueRaw({ rows: [[11]] });
    Object.defineProperty(raw, 'coverage', {
      enumerable: true,
      get() {
        invocations += 1;
        return 'PARTIAL';
      },
    });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    expect(invocations).toBe(0);
  });

  it('rejects hostile getters on nested rows without invoking them', () => {
    let invocations = 0;
    const raw = makeCatalogueRaw({ rows: [[11]] });
    const row = must((raw.conversations as Record<string, unknown>[])[0]);
    Object.defineProperty(row, 'title', {
      enumerable: true,
      get() {
        invocations += 1;
        return null;
      },
    });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
    expect(invocations).toBe(0);
  });

  it('rejects a hostile toJSON data property', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.toJSON = () => {
      throw new Error('toJSON must never run');
    };
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects symbol-keyed extras', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    Object.defineProperty(raw, Symbol('extra'), {
      value: 'x',
      enumerable: true,
      writable: true,
      configurable: true,
    });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects hidden non-enumerable properties', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    Object.defineProperty(raw, 'ghost', {
      value: 1,
      enumerable: false,
      writable: true,
      configurable: true,
    });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects cyclic array references without hanging', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    const requests = must(
      must((raw.conversations as Record<string, unknown>[])[0]).requests,
    ) as unknown[];
    requests.push(requests);
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects arrays with extra custom properties', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    const conversations = raw.conversations as unknown[];
    Object.defineProperty(conversations, 'meta', {
      value: 'extra',
      enumerable: true,
      writable: true,
      configurable: true,
    });
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects arrays with holes', () => {
    const raw = makeCatalogueRaw({ rows: [[11], [12]] });
    const conversations = raw.conversations as unknown[];
    delete conversations[0];
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects arrays with a replaced prototype', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    Object.setPrototypeOf(raw.conversations as unknown[], {});
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects non-plain object prototypes', () => {
    class Wrapper {}
    const fake = Object.assign(
      new Wrapper(),
      makeCatalogueRaw({ rows: [[11]] }),
    ) as unknown;
    expect(() =>
      decodeProjectConversationCatalogue(fake, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects lone surrogates in bounded strings', () => {
    const raw = makeCatalogueRaw({ rows: [[11]] });
    raw.work_ref = 'WS:A\ud800B';
    expect(() =>
      decodeProjectConversationCatalogue(raw, WORK_REF),
    ).toThrowError(UNAVAILABLE);
  });
});

describe('decodeProjectConversationRead', () => {
  it('decodes mixed AVAILABLE and UNAVAILABLE turns in expected order', () => {
    const requests = defaultReadRequests();
    const decoded: ProjectConversationRead = decodeProjectConversationRead(
      makeReadRaw({ requests }),
      makeExpected({ requests }),
    );
    expect(decoded.schema).toBe(READ_SCHEMA);
    expect(decoded.work_ref).toBe(WORK_REF);
    expect(decoded.conversation_ref).toBe(conversationRef(1));
    expect(decoded.revision).toBe(hex64(21));
    expect(decoded.root_job_id).toBe('JOB-700');
    expect(decoded.title).toBeNull();
    expect(decoded.coverage).toBe('PARTIAL');
    expect(decoded.can_send).toBe(false);
    expect(decoded.turns.length).toBe(3);
    const firstTurn = must(decoded.turns[0]);
    expect(firstTurn.state).toBe('AVAILABLE');
    expect(firstTurn.read_ref).toBe(readRef(31));
    expect(must(firstTurn.reply).parent_consumed).toBe(false);
    expect(must(firstTurn.reply).message_key).toBe(messageKey(1));
    expect(Object.keys(must(firstTurn.reply))).toEqual([
      'text',
      'next_step',
      'read_ref',
      'message_key',
      'fingerprint',
      'parent_consumed',
    ]);
    const unavailable = must(decoded.turns[2]);
    expect(unavailable.state).toBe('UNAVAILABLE');
    expect(unavailable.instruction).toBeNull();
    expect(unavailable.stop_condition).toBeNull();
    expect(unavailable.reply).toBeNull();
  });

  it('preserves literal unicode and whitespace byte-for-byte', () => {
    const literal =
      'Keep 中文 text ✓ \u{1F600} with \t tab, \n newline and  double space.';
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    turn.instruction = literal;
    turn.stop_condition = literal;
    const decoded = decodeProjectConversationRead(
      makeReadRaw({ requests, turns: [turn] }),
      makeExpected({ requests }),
    );
    const decodedTurn = must(decoded.turns[0]);
    expect(decodedTurn.instruction).toBe(literal);
    expect(decodedTurn.stop_condition).toBe(literal);
    expect(must(decodedTurn.reply).text).toContain('中文');
  });

  it('returns detached deep-frozen output including replies', () => {
    const requests = requestList(31);
    const decoded = decodeProjectConversationRead(
      makeReadRaw({ requests }),
      makeExpected({ requests }),
    );
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded.turns)).toBe(true);
    const turn = must(decoded.turns[0]);
    expect(Object.isFrozen(turn)).toBe(true);
    expect(Object.isFrozen(must(turn.reply))).toBe(true);
  });

  it('accepts null-prototype containers', () => {
    const requests = requestList(31);
    const turn = Object.assign(Object.create(null), availableTurn(must(requests[0]), 0));
    const raw = makeReadRaw({ requests });
    raw.turns = [turn];
    const decoded = decodeProjectConversationRead(
      raw,
      makeExpected({ requests }),
    );
    expect(decoded.turns.length).toBe(1);
  });

  it('rejects a foreign conversation_ref', () => {
    const requests = requestList(31);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({
          requests,
          conversationRef: conversationRef(9),
        }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a revision mismatch against the expectation', () => {
    const requests = requestList(31);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, revision: hex64(99) }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a foreign work_ref', () => {
    const requests = requestList(31);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, workRef: 'WS:OTHER-9' }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects reordered turns', () => {
    const requests = requestList(31, 32);
    const turns = [
      availableTurn(must(requests[1]), 1),
      availableTurn(must(requests[0]), 0),
    ];
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a turn read_ref outside the expected requests', () => {
    const requests = requestList(31);
    const turn = availableTurn(request(99), 0);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a turn request_revision mismatch', () => {
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    turn.request_revision = hex64(77);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects turn counts that differ from expected requests', () => {
    const requests = requestList(31, 32, 33);
    const turns = requests.slice(0, 2).map((entry, index) => availableTurn(entry, index));
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects more than four turns', () => {
    const requests = requestList(31, 32, 33, 34);
    const extra = requestList(31, 32, 33, 34, 35);
    const turns = extra.map((entry, index) => availableTurn(entry, index));
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns }),
        makeExpected({ requests: [...requests, request(35)] }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a faked can_send flag', () => {
    const requests = requestList(31);
    const raw = makeReadRaw({ requests });
    raw.can_send = true;
    expect(() =>
      decodeProjectConversationRead(raw, makeExpected({ requests })),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a faked parent_consumed flag', () => {
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    const reply = must(turn.reply) as Record<string, unknown>;
    reply.parent_consumed = true;
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a reply read_ref that differs from the turn', () => {
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    const reply = must(turn.reply) as Record<string, unknown>;
    reply.read_ref = readRef(98);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a wrong message_key prefix and bad fingerprint', () => {
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    const reply = must(turn.reply) as Record<string, unknown>;
    reply.message_key = 'saved-reply-' + hex40(1);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
    const turn2 = availableTurn(must(requests[0]), 0);
    const reply2 = must(turn2.reply) as Record<string, unknown>;
    reply2.fingerprint = fingerprint(0xabcdef).toUpperCase();
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn2] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects AVAILABLE turns with missing literal data', () => {
    const requests = requestList(31);
    const nullReply = availableTurn(must(requests[0]), 0);
    nullReply.reply = null;
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [nullReply] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
    const emptyInstruction = availableTurn(must(requests[0]), 0);
    emptyInstruction.instruction = '';
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [emptyInstruction] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
    const nullStop = availableTurn(must(requests[0]), 0);
    nullStop.stop_condition = null;
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [nullStop] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects UNAVAILABLE turns that carry guessed data', () => {
    const requests = requestList(31);
    const turn = unavailableTurn(must(requests[0]), 0);
    turn.instruction = 'guessed';
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
    const turn2 = unavailableTurn(must(requests[0]), 0);
    turn2.reply = availableTurn(must(requests[0]), 0).reply;
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn2] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects an unknown turn state', () => {
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    turn.state = 'PENDING';
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('enforces the 700-codepoint literal bound', () => {
    const requests = requestList(31);
    const over = availableTurn(must(requests[0]), 0);
    over.instruction = 'x'.repeat(701);
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [over] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
    const boundary = availableTurn(must(requests[0]), 0);
    boundary.instruction = '\u{1F600}'.repeat(700);
    const decoded = decodeProjectConversationRead(
      makeReadRaw({ requests, turns: [boundary] }),
      makeExpected({ requests }),
    );
    expect(must(decoded.turns[0]).instruction).toBe('\u{1F600}'.repeat(700));
  });

  it('enforces the 32768-byte wire budget after detach', () => {
    const big = '\u{1F600}'.repeat(700);
    const requests = requestList(31, 32, 33, 34);
    const turns = requests.map((entry, index) => {
      const turn = availableTurn(entry, index);
      turn.instruction = big;
      turn.stop_condition = big;
      const reply = must(turn.reply) as Record<string, unknown>;
      reply.text = big;
      reply.next_step = big;
      return turn;
    });
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a lone surrogate in a turn literal', () => {
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    turn.instruction = 'broken \ud800 pair';
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a hostile reply getter without invoking it', () => {
    let invocations = 0;
    const requests = requestList(31);
    const turn = availableTurn(must(requests[0]), 0);
    const reply = must(turn.reply) as Record<string, unknown>;
    Object.defineProperty(reply, 'text', {
      enumerable: true,
      get() {
        invocations += 1;
        return 'never read';
      },
    });
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests, turns: [turn] }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
    expect(invocations).toBe(0);
  });

  it('rejects duplicate read_ref in the expectation', () => {
    const requests = [request(31), request(31)];
    expect(() =>
      decodeProjectConversationRead(
        makeReadRaw({ requests: [...requests], turns: requests.map((entry, index) => availableTurn(entry, index)) }),
        makeExpected({ requests }),
      ),
    ).toThrowError(UNAVAILABLE);
  });

  it('rejects a non-null title', () => {
    const requests = requestList(31);
    const raw = makeReadRaw({ requests, title: 'Invented' });
    expect(() =>
      decodeProjectConversationRead(raw, makeExpected({ requests })),
    ).toThrowError(UNAVAILABLE);
  });
});

describe('validateProjectConversationSelection', () => {
  it('decodes a closed four-key selection and freezes it', () => {
    const selection: ProjectConversationSelection =
      validateProjectConversationSelection(makeSelectionRaw());
    expect(Object.keys(selection)).toEqual([
      'work_ref',
      'conversation_ref',
      'revision',
      'requests',
    ]);
    expect(selection.work_ref).toBe(WORK_REF);
    expect(selection.conversation_ref).toBe(conversationRef(1));
    expect(selection.revision).toBe(hex64(21));
    expect(selection.requests.length).toBe(2);
    expect(Object.isFrozen(selection)).toBe(true);
    expect(Object.isFrozen(selection.requests)).toBe(true);
  });

  it('feeds a decoded read as the exact expectation', () => {
    const selection = validateProjectConversationSelection(makeSelectionRaw());
    const requests = [...selection.requests];
    const decoded = decodeProjectConversationRead(
      makeReadRaw({
        conversationRef: selection.conversation_ref,
        revision: selection.revision,
        requests,
        turns: requests.map((entry, index) => availableTurn(entry, index)),
      }),
      {
        workRef: selection.work_ref,
        conversationRef: selection.conversation_ref,
        revision: selection.revision,
        requests: selection.requests,
      },
    );
    expect(decoded.turns.length).toBe(2);
  });

  it('rejects principal, path or session selector extras', () => {
    for (const key of ['principal', 'session_path', 'target_url', 'selector']) {
      const raw = makeSelectionRaw();
      raw[key] = 'injected';
      expect(() => validateProjectConversationSelection(raw)).toThrowError(
        UNAVAILABLE,
      );
    }
  });

  it('rejects a malformed conversation_ref grammar', () => {
    const raw = makeSelectionRaw({ conversationRef: 'conversation-' + 'A'.repeat(64) });
    expect(() => validateProjectConversationSelection(raw)).toThrowError(
      UNAVAILABLE,
    );
    const raw2 = makeSelectionRaw({ conversationRef: readRef(31) });
    expect(() => validateProjectConversationSelection(raw2)).toThrowError(
      UNAVAILABLE,
    );
  });

  it('rejects an invalid work_ref grammar', () => {
    const raw = makeSelectionRaw({ workRef: 'ws:mm-proj-1' });
    expect(() => validateProjectConversationSelection(raw)).toThrowError(
      UNAVAILABLE,
    );
    const raw2 = makeSelectionRaw({ workRef: `WS:${'A'.repeat(70)}` });
    expect(() => validateProjectConversationSelection(raw2)).toThrowError(
      UNAVAILABLE,
    );
  });

  it('rejects duplicate read_refs in the request list', () => {
    const raw = makeSelectionRaw({ requests: [request(31), request(31)] });
    expect(() => validateProjectConversationSelection(raw)).toThrowError(
      UNAVAILABLE,
    );
  });

  it('rejects an empty or oversized request list', () => {
    expect(() =>
      validateProjectConversationSelection(makeSelectionRaw({ requests: [] })),
    ).toThrowError(UNAVAILABLE);
    expect(() =>
      validateProjectConversationSelection(
        makeSelectionRaw({ requests: requestList(31, 32, 33, 34, 35) }),
      ),
    ).toThrowError(UNAVAILABLE);
  });
});
