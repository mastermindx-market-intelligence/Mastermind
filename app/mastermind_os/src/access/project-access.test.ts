import { describe, expect, it } from 'vitest';
import {
  decodeProjectAccess,
  validProjectAccessSelection,
  type ProjectAccessGrantRow,
  type ProjectAccessRead,
  type ProjectAccessSelection,
} from './project-access';

const SCHEMA = 'mastermind.workspace_project_access.v1';
const SELECTED = { work_ref: 'WS:ALPHA' } as const;
const COMMIT = '1234567890abcdef1234567890abcdef12345678';
const CONTENT_SHA = '0123456789abcdef'.repeat(4);
const INSTRUCTION_REF = 'INS:BRIEF-01';

type Row = Record<string, unknown>;
type Body = Record<string, unknown>;

function source(): Row {
  return {
    repository: 'mastermindx-market-intelligence/macro',
    commit: COMMIT,
    content_sha256: CONTENT_SHA,
    path: 'agentos/workstreams/WS-ALPHA.md',
  };
}

function grantRow(action: string, scope: string, overrides: Row = {}): Row {
  return {
    action,
    scope,
    work_ref: scope === 'WORKSPACE' ? null : SELECTED.work_ref,
    instruction_ref: scope === 'INSTRUCTION' ? INSTRUCTION_REF : null,
    supply: 'SUPPLIED',
    ...overrides,
  };
}

function grants(instructionSupplied = true): Row[] {
  return [
    grantRow('publish_project_proposal', 'WORKSPACE'),
    grantRow('pause_workstream_admission', 'PROJECT'),
    grantRow('resume_workstream_admission', 'PROJECT'),
    grantRow('ADOPT_PLAN', 'PROJECT'),
    grantRow('ACCEPT_DIRECTION', 'PROJECT'),
    grantRow('add_project_file', 'PROJECT'),
    grantRow('set_project_communication_preference', 'PROJECT'),
    grantRow(
      'pause_instruction_admission',
      'INSTRUCTION',
      instructionSupplied ? {} : { instruction_ref: null, supply: 'NOT_SUPPLIED' },
    ),
  ];
}

function availableBody(overrides: Row = {}): Body {
  return {
    schema: SCHEMA,
    selection: { work_ref: SELECTED.work_ref },
    availability: 'AVAILABLE',
    source: source(),
    membership: { workspace_read: 'QUALIFIED' },
    declaration: 'SUPPLIED',
    grants: grants(),
    reason_codes: [],
    ...overrides,
  };
}

function unavailableBody(overrides: Row = {}): Body {
  return {
    schema: SCHEMA,
    selection: { work_ref: SELECTED.work_ref },
    availability: 'UNAVAILABLE',
    source: null,
    membership: null,
    declaration: null,
    grants: null,
    reason_codes: ['SOURCE_UNAVAILABLE'],
    ...overrides,
  };
}

/** Builds a fresh body, applies `patch` to grant row `index`. */
function patchedGrant(index: number, patch: Row): Body {
  const body = availableBody();
  const rows = body.grants as Row[];
  rows[index] = { ...rows[index], ...patch };
  return body;
}

function declines(body: unknown, expected: ProjectAccessSelection = SELECTED): void {
  expect(decodeProjectAccess(body, expected)).toBeNull();
}

/** Swaps two grant rows to exercise closed positional action order. */
function swapRows(rows: Row[], first: number, second: number): void {
  const left = rows[first];
  const right = rows[second];
  if (left === undefined || right === undefined) throw new Error('fixture rows missing');
  rows[first] = right;
  rows[second] = left;
}

const EXPECTED_SUPPLIED_GRANTS = grants().map((row) => ({ ...row }));

describe('validProjectAccessSelection', () => {
  it('accepts canonical WS references and keeps the exact shape', () => {
    for (const ref of [
      'WS:AB',
      'WS:A-B',
      'WS:ALPHA',
      'WS:90210',
      'WS:ALPHA-BETA-GAMMA',
      `WS:${'A'.repeat(64)}`,
    ]) {
      expect(validProjectAccessSelection({ work_ref: ref })).toBe(true);
    }
  });

  it('rejects malformed WS references', () => {
    for (const ref of [
      'ws:alpha',
      'WS:alpha',
      'WS:',
      'WS:A',
      'WS:-ALPHA',
      'WS:ALPHA-',
      'WS:AL--PHA',
      'WS:ALPHA\n',
      'WS:AL PHA',
      'WS:ALPHA\nWS:BETA',
      `WS:${'A'.repeat(65)}`,
      'INS:ALPHA',
      'ALPHA',
      '',
    ]) {
      expect(validProjectAccessSelection({ work_ref: ref })).toBe(false);
    }
  });

  it('rejects non-selection shapes', () => {
    for (const value of [
      null,
      undefined,
      'WS:ALPHA',
      42,
      [],
      ['WS:ALPHA'],
      {},
      { work_ref: 7 },
      { work_ref: 'WS:ALPHA', extra: true },
      Object.create({ work_ref: 'WS:ALPHA' }),
    ]) {
      expect(validProjectAccessSelection(value)).toBe(false);
    }
  });
});

describe('decodeProjectAccess — canonical available body', () => {
  it('decodes a fully supplied body exactly', () => {
    const decoded = decodeProjectAccess(availableBody(), SELECTED);
    expect(decoded).not.toBeNull();
    expect(decoded).toEqual({
      schema: SCHEMA,
      selection: { work_ref: 'WS:ALPHA' },
      availability: 'AVAILABLE',
      source: source(),
      membership: { workspace_read: 'QUALIFIED' },
      declaration: 'SUPPLIED',
      grants: EXPECTED_SUPPLIED_GRANTS,
      reason_codes: [],
    });
  });

  it('exposes the discriminated SUPPLIED variant with closed row scopes', () => {
    const decoded: ProjectAccessRead | null = decodeProjectAccess(availableBody(), SELECTED);
    if (decoded === null || decoded.availability !== 'AVAILABLE' || decoded.declaration !== 'SUPPLIED') {
      throw new Error('expected the AVAILABLE/SUPPLIED variant');
    }
    expect(decoded.grants).toHaveLength(8);
    const first: ProjectAccessGrantRow = decoded.grants[0];
    expect(first).toEqual({
      action: 'publish_project_proposal',
      scope: 'WORKSPACE',
      work_ref: null,
      instruction_ref: null,
      supply: 'SUPPLIED',
    });
    expect(decoded.grants[7]).toEqual({
      action: 'pause_instruction_admission',
      scope: 'INSTRUCTION',
      work_ref: 'WS:ALPHA',
      instruction_ref: INSTRUCTION_REF,
      supply: 'SUPPLIED',
    });
  });

  it('accepts numeric and single-hyphen INS refs, and NOT_SUPPLIED instruction rows', () => {
    const numeric = availableBody();
    (numeric.grants as Row[])[7] = grantRow('pause_instruction_admission', 'INSTRUCTION', {
      instruction_ref: 'INS:0091',
    });
    expect(decodeProjectAccess(numeric, SELECTED)).not.toBeNull();

    const withheld = availableBody({ declaration: 'SUPPLIED' });
    (withheld.grants as Row[])[7] = grantRow('pause_instruction_admission', 'INSTRUCTION', {
      instruction_ref: null,
      supply: 'NOT_SUPPLIED',
    });
    const decoded = decodeProjectAccess(withheld, SELECTED);
    expect(decoded).not.toBeNull();
    if (decoded !== null && decoded.availability === 'AVAILABLE' && decoded.declaration === 'SUPPLIED') {
      expect(decoded.grants[7]).toEqual({
        action: 'pause_instruction_admission',
        scope: 'INSTRUCTION',
        work_ref: 'WS:ALPHA',
        instruction_ref: null,
        supply: 'NOT_SUPPLIED',
      });
    }
  });

  it('returns fresh decoded values and does not mutate the input', () => {
    const body = availableBody();
    const snapshot = JSON.stringify(body);
    const decoded = decodeProjectAccess(body, SELECTED);
    expect(decoded).not.toBeNull();
    if (decoded !== null && decoded.availability === 'AVAILABLE' && decoded.declaration === 'SUPPLIED') {
      expect(decoded.source).not.toBe(body.source);
      expect(decoded.grants).not.toBe(body.grants);
    }
    expect(JSON.stringify(body)).toBe(snapshot);
  });
});

describe('decodeProjectAccess — legacy not-declared body', () => {
  it('decodes AVAILABLE with NOT_DECLARED and null grants', () => {
    const body = availableBody({ declaration: 'NOT_DECLARED', grants: null });
    expect(decodeProjectAccess(body, SELECTED)).toEqual({
      schema: SCHEMA,
      selection: { work_ref: 'WS:ALPHA' },
      availability: 'AVAILABLE',
      source: source(),
      membership: { workspace_read: 'QUALIFIED' },
      declaration: 'NOT_DECLARED',
      grants: null,
      reason_codes: [],
    });
  });

  it('rejects NOT_DECLARED with any grants payload', () => {
    declines(availableBody({ declaration: 'NOT_DECLARED', grants: [] }));
    declines(availableBody({ declaration: 'NOT_DECLARED', grants: grants() }));
  });
});

describe('decodeProjectAccess — unavailable bodies', () => {
  it('decodes each closed reason code exactly', () => {
    for (const reason of ['ACCESS_DENIED', 'SOURCE_UNAVAILABLE', 'SOURCE_CHANGED', 'OWNER_NOT_READY']) {
      const decoded = decodeProjectAccess(unavailableBody({ reason_codes: [reason] }), SELECTED);
      expect(decoded).toEqual({
        schema: SCHEMA,
        selection: { work_ref: 'WS:ALPHA' },
        availability: 'UNAVAILABLE',
        source: null,
        membership: null,
        declaration: null,
        grants: null,
        reason_codes: [reason],
      });
    }
  });

  it('rejects unknown, duplicated, empty, non-array and non-string reasons', () => {
    declines(unavailableBody({ reason_codes: ['SOURCE_LOST'] }));
    declines(unavailableBody({ reason_codes: ['SOURCE_UNAVAILABLE', 'ACCESS_DENIED'] }));
    declines(unavailableBody({ reason_codes: [] }));
    declines(unavailableBody({ reason_codes: 'SOURCE_UNAVAILABLE' }));
    declines(unavailableBody({ reason_codes: [7] }));
    declines(unavailableBody({ reason_codes: null }));
  });

  it('rejects unavailable bodies with any non-null observation field', () => {
    declines(unavailableBody({ source: source() }));
    declines(unavailableBody({ membership: { workspace_read: 'QUALIFIED' } }));
    declines(unavailableBody({ declaration: 'SUPPLIED' }));
    declines(unavailableBody({ grants: grants() }));
  });
});

describe('decodeProjectAccess — foreign selection or source', () => {
  it('rejects a body whose selection differs from the expected selection', () => {
    declines(availableBody({ selection: { work_ref: 'WS:BETA' } }), SELECTED);
    declines(availableBody(), { work_ref: 'WS:BETA' });
  });

  it('strictly validates the expected selection itself', () => {
    declines(availableBody(), { work_ref: 'WS:BAD-' });
    declines(availableBody(), { work_ref: 'WS:BAD-REF' });
    declines(availableBody(), { work_ref: 'WS:ALPHA', extra: 1 } as unknown as ProjectAccessSelection);
    declines(availableBody(), {} as unknown as ProjectAccessSelection);
    declines(availableBody(), null as unknown as ProjectAccessSelection);
  });

  it('rejects foreign or malformed sources', () => {
    declines(availableBody({ source: { ...source(), repository: 'mastermindx-market-intelligence/other' } }));
    declines(availableBody({ source: { ...source(), commit: COMMIT.toUpperCase() } }));
    declines(availableBody({ source: { ...source(), commit: COMMIT.slice(1) } }));
    declines(availableBody({ source: { ...source(), content_sha256: CONTENT_SHA.toUpperCase() } }));
    declines(availableBody({ source: { ...source(), path: 'agentos/workstreams/WS-BETA.md' } }));
    declines(availableBody({ source: { ...source(), path: 'agentos/workstreams/WS-ALPHA.md\n' } }));
    declines(availableBody({ source: { ...source(), path: 'agentos/project-files/WS-ALPHA.md' } }));
    const extra = source();
    extra.committed_at = '2026-01-01T00:00:00Z';
    declines(availableBody({ source: extra }));
    const missing = source();
    delete missing.content_sha256;
    declines(availableBody({ source: missing }));
    declines(availableBody({ source: null }));
    declines(availableBody({ source: 'agentos/workstreams/WS-ALPHA.md' }));
  });

  it('rejects malformed or foreign membership', () => {
    declines(availableBody({ membership: { workspace_read: 'PENDING' } }));
    declines(availableBody({ membership: { workspace_read: 'QUALIFIED', extra: 1 } }));
    declines(availableBody({ membership: {} }));
    declines(availableBody({ membership: null }));
  });
});

describe('decodeProjectAccess — closed order, scopes and refs', () => {
  it('rejects rows in altered action order', () => {
    const body = availableBody();
    swapRows(body.grants as Row[], 0, 1);
    declines(body);
  });

  it('rejects duplicated actions that keep the length', () => {
    const body = availableBody();
    const rows = body.grants as Row[];
    rows[4] = grantRow('ADOPT_PLAN', 'PROJECT');
    declines(body);
  });

  it('rejects wrong scope and wrong work_ref bindings', () => {
    declines(patchedGrant(0, { scope: 'PROJECT' }));
    declines(patchedGrant(0, { scope: 'INSTRUCTION' }));
    declines(patchedGrant(0, { work_ref: SELECTED.work_ref }));
    declines(patchedGrant(2, { scope: 'WORKSPACE' }));
    declines(patchedGrant(2, { work_ref: null }));
    declines(patchedGrant(2, { work_ref: 'WS:BETA' }));
  });

  it('enforces the INSTRUCTION instruction_ref contract', () => {
    declines(patchedGrant(7, { instruction_ref: null }));
    declines(patchedGrant(7, { instruction_ref: 'WS:ALPHA' }));
    declines(patchedGrant(7, { instruction_ref: 'ins:BRIEF-01' }));
    declines(patchedGrant(7, { instruction_ref: 'INS:BRIEF--01' }));
    declines(patchedGrant(7, { instruction_ref: 'INS:B' }));
    declines(patchedGrant(7, { instruction_ref: 'INS:BRIEF-01\n' }));
    declines(patchedGrant(7, { instruction_ref: 42 }));
  });

  it('requires null instruction_ref outside the supplied INSTRUCTION row', () => {
    declines(patchedGrant(1, { instruction_ref: INSTRUCTION_REF }));
    declines(patchedGrant(0, { instruction_ref: INSTRUCTION_REF }));
    declines(patchedGrant(7, { supply: 'NOT_SUPPLIED', instruction_ref: INSTRUCTION_REF }));
  });

  it('rejects wrong row counts and malformed supplies', () => {
    const short = availableBody();
    (short.grants as Row[]).pop();
    declines(short);
    const long = availableBody();
    (long.grants as Row[]).push(grantRow('publish_project_proposal', 'WORKSPACE'));
    declines(long);
    declines(patchedGrant(1, { supply: 'supplied' }));
    declines(patchedGrant(1, { supply: 'SUPPLIED ' }));
    declines(patchedGrant(1, { supply: null }));
  });

  it('rejects row-level key surprises', () => {
    const extra = patchedGrant(3, { extra: 1 });
    declines(extra);
    const missing = availableBody();
    const dropped = (missing.grants as Row[])[3];
    if (dropped === undefined) throw new Error('fixture row missing');
    delete dropped.scope;
    declines(missing);
    declines(availableBody({ grants: null }));
    declines(availableBody({ grants: {} }));
    const sparse = availableBody();
    delete (sparse.grants as Row[])[3];
    declines(sparse);
  });
});

describe('decodeProjectAccess — strict structural rejection', () => {
  it('rejects null and malformed inputs', () => {
    for (const value of [null, undefined, 42, 'body', true, [], ['x'], () => 1]) {
      declines(value);
    }
    declines({});
  });

  it('rejects closed-body key surprises', () => {
    const extra = availableBody();
    extra.extra = 1;
    declines(extra);
    const missing = availableBody();
    delete missing.declaration;
    declines(missing);
    const symbolKey = availableBody();
    Reflect.set(symbolKey, Symbol('extra'), 1);
    declines(symbolKey);
    declines(availableBody({ schema: 42 }));
    declines(availableBody({ schema: 'mastermind.workspace_project_access.v0' }));
  });

  it('rejects accessors, non-enumerable keys and prototype surprises', () => {
    const getter = availableBody();
    Object.defineProperty(getter, 'source', { enumerable: true, get: () => source() });
    declines(getter);
    const hidden = availableBody();
    Object.defineProperty(hidden, 'schema', { value: SCHEMA, enumerable: false });
    declines(hidden);
    const foreignProto = Object.assign(Object.create({ inherited: 1 }), availableBody());
    declines(foreignProto);
    const nullProto: Row = Object.assign(Object.create(null), availableBody());
    declines(nullProto);
    const protoValue = availableBody();
    (protoValue.membership as Row) = Object.create({ workspace_read: 'QUALIFIED' });
    declines(protoValue);
  });

  it('rejects cyclic, over-deep, non-JSON and oversized inputs', () => {
    const cyclic: unknown[] = [];
    cyclic.push(cyclic);
    declines(unavailableBody({ reason_codes: cyclic }));
    const cyclicRow = availableBody();
    (cyclicRow.grants as Row[])[0] = { ...grantRow('publish_project_proposal', 'WORKSPACE'), self: undefined };
    declines(cyclicRow);
    let deep: unknown = 'SOURCE_UNAVAILABLE';
    for (let index = 0; index < 30; index += 1) deep = [deep];
    declines(unavailableBody({ reason_codes: deep }));
    declines(unavailableBody({ source: undefined }));
    declines(availableBody({ reason_codes: [undefined] }));
    declines(availableBody({ source: { ...source(), commit: Number.NaN } }));
    declines(availableBody({ schema: 'x'.repeat(20000) }));
    declines(availableBody({ source: { ...source(), path: `agentos/workstreams/WS-${'A'.repeat(20000)}.md` } }));
  });

  it('rejects unknown availability and unknown declaration values', () => {
    declines(availableBody({ availability: 'unavailable' }));
    declines(availableBody({ availability: 'PENDING' }));
    declines(availableBody({ declaration: 'DECLARED' }));
    declines(availableBody({ declaration: null }));
    declines(unavailableBody({ availability: 'AVAILABLE' }));
  });

  it('rejects non-empty reason_codes on available bodies', () => {
    declines(availableBody({ reason_codes: ['ACCESS_DENIED'] }));
  });
});
