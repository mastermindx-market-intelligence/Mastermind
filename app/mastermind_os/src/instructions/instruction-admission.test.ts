import { describe, expect, it } from 'vitest';

import {
  INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA,
  INSTRUCTION_ADMISSION_CONTROL_SCHEMA,
  INSTRUCTION_ADMISSION_INVALID,
  INSTRUCTION_ADMISSION_MAX_RESPONSE_UTF8_BYTES,
  INSTRUCTION_ADMISSION_REASON_CODES,
  INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA,
  INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA,
  OWNER_OUTCOME_UNCONFIRMED,
  decodeInstructionAdmissionControl,
  decodeInstructionAdmissionReceipt,
  decodeInstructionAdmissionResult,
  unavailableInstructionAdmissionControl,
  validInstructionAdmissionSelection,
} from './instruction-admission';

import type { InstructionAdmissionReasonCode } from './instruction-admission';

/** Test-only union-arm guard: a decoded body landed in the wrong arm. */
function fail(message: string): never {
  throw new Error(message);
}

/* ------------------------------------------------------------------ *
 * fixtures
 * ------------------------------------------------------------------ */

const HEX64 = '0123456789abcdef'.repeat(4);
const HEX40 = HEX64.slice(0, 40);
const OTHER_HEX64 = 'a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8';
const WS = 'WS:CAP-C1';
const OTHER_WS = 'WS:DELTA-2';
const INS = 'INS:PAUSE-MAIN';
const COMMAND = `mmos-instruction-pause-${HEX40}`;
const SCOPE = OTHER_HEX64;

type Body = Record<string, unknown>;

function sourceRef(workRef: string = WS): Body {
  return {
    repository: 'mastermindx-market-intelligence/macro',
    commit: HEX40,
    path: `agentos/workstreams/${workRef.replace(':', '-')}.md`,
    content_sha256: HEX64,
  };
}

let receiptSeq = 0;
function receipt(overrides: Body = {}): Body {
  receiptSeq += 1;
  return {
    schema: INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA,
    work_ref: WS,
    instruction_ref: INS,
    revision: HEX64,
    source: sourceRef(),
    command_id: `pause-receipt-${receiptSeq.toString(16).padStart(8, '0')}-${HEX40.slice(0, 8)}`,
    state: 'PAUSED',
    event_id: 4200 + receiptSeq,
    request_digest: OTHER_HEX64,
    committed_at_ms: 1_700_000_000_000,
    ...overrides,
  };
}

function controlBody(overrides: Body = {}): Body {
  const state = overrides.state === undefined ? 'PAUSED' : overrides.state;
  const withReceipt =
    overrides.current_receipt === undefined && state === 'PAUSED' ? receipt() : {};
  return {
    schema: INSTRUCTION_ADMISSION_CONTROL_SCHEMA,
    selection: { work_ref: WS, instruction_ref: INS },
    availability: 'AVAILABLE',
    state,
    source: sourceRef(),
    instruction_revision: HEX64,
    permission: { pause: true },
    owner_context: { principal_scope: SCOPE },
    current_receipt: state === 'PAUSED' ? { ...(withReceipt as Body) } : null,
    reason_codes: [],
    ...overrides,
  };
}

function unavailableBody(reason: string): Body {
  return {
    schema: INSTRUCTION_ADMISSION_CONTROL_SCHEMA,
    selection: { work_ref: WS, instruction_ref: INS },
    availability: 'UNAVAILABLE',
    state: null,
    source: null,
    instruction_revision: null,
    permission: null,
    owner_context: null,
    current_receipt: null,
    reason_codes: [reason],
  };
}

function actionBody(overrides: Body = {}): Body {
  const disposition = overrides.disposition === undefined ? 'COMMITTED' : overrides.disposition;
  return {
    schema: INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA,
    selection: { work_ref: WS, instruction_ref: INS, command_id: COMMAND },
    disposition,
    receipt: disposition === 'COMMITTED' ? receipt() : null,
    reason_codes: [],
    ...overrides,
  };
}

function statusBody(overrides: Body = {}): Body {
  const state = overrides.state === undefined ? 'OBSERVED' : overrides.state;
  return {
    schema: INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA,
    selection: { work_ref: WS, instruction_ref: INS, command_id: COMMAND },
    state,
    receipt: state === 'OBSERVED' ? receipt() : null,
    reason_codes: [],
    ...overrides,
  };
}

const SELECTED = { work_ref: WS, instruction_ref: INS };
const SELECTED_COMMAND = { work_ref: WS, instruction_ref: INS, command_id: COMMAND };

/** Control decode against the selected pair. */
function decodeControl(value: unknown): ReturnType<typeof decodeInstructionAdmissionControl> {
  return decodeInstructionAdmissionControl(value, { ...SELECTED });
}

/** Result decode against the selected command selection, in a given mode. */
function decodeResult(
  value: unknown,
  mode: 'pause' | 'status',
): ReturnType<typeof decodeInstructionAdmissionResult> {
  return decodeInstructionAdmissionResult(value, { ...SELECTED_COMMAND }, mode);
}

/** Sorted-key compact JSON, the producer's canonical shape (ASCII bodies only). */
function canonical(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  const keys = Object.keys(value as Body).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonical((value as Body)[k])}`).join(',')}}`;
}

function getterBody(keys: readonly string[], counter: { hits: number }): Body {
  const out = {};
  for (const key of keys) {
    Object.defineProperty(out, key, {
      enumerable: true,
      get() {
        counter.hits += 1;
        return null;
      },
    });
  }
  return out as Body;
}

/* ------------------------------------------------------------------ *
 * selection grammar
 * ------------------------------------------------------------------ */

describe('validInstructionAdmissionSelection', () => {
  it('accepts the exact two-field selection and nothing else', () => {
    expect(validInstructionAdmissionSelection({ ...SELECTED })).toBe(true);
    expect(validInstructionAdmissionSelection({ work_ref: OTHER_WS, instruction_ref: 'INS:A-B' })).toBe(true);
    expect(validInstructionAdmissionSelection({ ...SELECTED_COMMAND })).toBe(false);
    expect(validInstructionAdmissionSelection({ work_ref: WS })).toBe(false);
    expect(validInstructionAdmissionSelection({ ...SELECTED, extra: 1 })).toBe(false);
  });

  it('rejects malformed work and instruction refs', () => {
    const badRefs = [
      'WS:A',
      'ws:CAP-C1',
      'WS:cap-c1',
      'WS:-CAP',
      'WS:CAP C1',
      'WS:CAP--C1',
      'WS:CAP-C1-',
      'WS:CAP-C1\n',
      `WS:${'A'.repeat(65)}`,
      'WS-CAP-C1',
      'WS:',
      'INS:A',
      'ins:PAUSE',
      'IN:PAUSE',
      'INS:PAUSE_MAIN',
      `INS:${'A'.repeat(65)}`,
      7,
      null,
    ];
    for (const work_ref of badRefs) {
      expect(validInstructionAdmissionSelection({ work_ref, instruction_ref: INS })).toBe(false);
    }
    for (const instruction_ref of badRefs) {
      expect(validInstructionAdmissionSelection({ work_ref: WS, instruction_ref })).toBe(false);
    }
    // Boundary of the key grammar: 1 + 63 = 64 key characters is accepted.
    expect(validInstructionAdmissionSelection({ work_ref: `WS:${'A'}${'B'.repeat(63)}`, instruction_ref: INS })).toBe(true);
  });

  it('rejects non-plain objects without invoking accessors', () => {
    expect(validInstructionAdmissionSelection(null)).toBe(false);
    expect(validInstructionAdmissionSelection([WS, INS])).toBe(false);
    expect(validInstructionAdmissionSelection('WS:X')).toBe(false);
    expect(validInstructionAdmissionSelection(42)).toBe(false);

    const counter = { hits: 0 };
    const hostile = getterBody(['work_ref', 'instruction_ref'], counter);
    expect(validInstructionAdmissionSelection(hostile)).toBe(false);
    expect(counter.hits).toBe(0);

    class Candidate {}
    expect(validInstructionAdmissionSelection(new Candidate())).toBe(false);

    const symbols = { ...SELECTED };
    (symbols as unknown as { [k: symbol]: unknown })[Symbol('x')] = 1;
    expect(validInstructionAdmissionSelection(symbols)).toBe(false);
  });

  it('accepts null-prototype records as plain data', () => {
    const bare = Object.create(null);
    bare.work_ref = WS;
    bare.instruction_ref = INS;
    expect(validInstructionAdmissionSelection(bare)).toBe(true);
  });
});

/* ------------------------------------------------------------------ *
 * receipt grammar
 * ------------------------------------------------------------------ */

describe('decodeInstructionAdmissionReceipt', () => {
  it('accepts a valid receipt against a two-field selection with a generic token', () => {
    const decoded = decodeInstructionAdmissionReceipt(receipt(), { ...SELECTED });
    expect(decoded).not.toBeNull();
    expect(decoded?.state).toBe('PAUSED');
    expect(decoded?.schema).toBe(INSTRUCTION_ADMISSION_SUSPENSION_RECEIPT_SCHEMA);
    // Detached: not the wire object.
    const wire = receipt();
    expect(decodeInstructionAdmissionReceipt(wire, { ...SELECTED })).not.toBe(wire);
  });

  it('accepts a null-prototype receipt', () => {
    const raw = Object.create(null);
    for (const [k, v] of Object.entries(receipt())) raw[k] = v;
    expect(decodeInstructionAdmissionReceipt(raw, { ...SELECTED })).not.toBeNull();
  });

  it('rejects any key-set, schema or state deviation', () => {
    expect(decodeInstructionAdmissionReceipt({ ...receipt(), extra: 1 }, { ...SELECTED })).toBeNull();
    const trimmed = receipt();
    delete trimmed.event_id;
    expect(decodeInstructionAdmissionReceipt(trimmed, { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ schema: 'mastermind.other.v1' }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ state: 'RESUMED' }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ state: 'PAUSED ' }), { ...SELECTED })).toBeNull();
  });

  it('rejects a receipt pointed at another workstream or instruction', () => {
    expect(decodeInstructionAdmissionReceipt(receipt({ work_ref: OTHER_WS }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ instruction_ref: 'INS:OTHER' }), { ...SELECTED })).toBeNull();
    // The source must still describe the selected workstream.
    const sibling = receipt();
    (sibling.source as Body).path = `agentos/workstreams/${OTHER_WS.replace(':', '-')}.md`;
    expect(decodeInstructionAdmissionReceipt(sibling, { ...SELECTED })).toBeNull();
  });

  it('enforces the digest and source grammar', () => {
    expect(decodeInstructionAdmissionReceipt(receipt({ revision: HEX64.slice(1) + 'g' }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ revision: HEX64.slice(0, 63) }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ revision: HEX64.toUpperCase() }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ request_digest: 5 }), { ...SELECTED })).toBeNull();
    const repo = receipt();
    (repo.source as Body).repository = 'other-macro';
    expect(decodeInstructionAdmissionReceipt(repo, { ...SELECTED })).toBeNull();
    const commit = receipt();
    (commit.source as Body).commit = HEX40.toUpperCase();
    expect(decodeInstructionAdmissionReceipt(commit, { ...SELECTED })).toBeNull();
    const sha = receipt();
    (sha.source as Body).content_sha256 = HEX64.slice(0, 64).replace('0', 'z');
    expect(decodeInstructionAdmissionReceipt(sha, { ...SELECTED })).toBeNull();
    const extraSource = receipt();
    (extraSource.source as Body).blob = 'x';
    expect(decodeInstructionAdmissionReceipt(extraSource, { ...SELECTED })).toBeNull();
  });

  it('bounds the event and commit timestamps to safe integers', () => {
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: 1 }), { ...SELECTED })).not.toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: 9007199254740991 }), { ...SELECTED })).not.toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ committed_at_ms: 0 }), { ...SELECTED })).not.toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ committed_at_ms: 9007199254740991 }), { ...SELECTED })).not.toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: 0 }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: -1 }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: 1.5 }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: true }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: Number.NaN }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ event_id: 9007199254740992 }), { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ committed_at_ms: -1 }), { ...SELECTED })).toBeNull();
  });

  it('accepts any generic bounded command token without a selected command', () => {
    const generic128 = `A${'-'.repeat(127)}`;
    expect(generic128.length).toBe(128);
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: generic128 }), { ...SELECTED })).not.toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: COMMAND }), { ...SELECTED })).not.toBeNull();
    const tooLong = `A${'-'.repeat(128)}`;
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: tooLong }), { ...SELECTED })).toBeNull();
    for (const bad of ['', '.', '-', ':', '!x', 'a b', `${HEX40} `]) {
      expect(decodeInstructionAdmissionReceipt(receipt({ command_id: bad }), { ...SELECTED })).toBeNull();
    }
    // A lone surrogate never reaches the token grammar: the string is
    // rejected as not well-formed UTF-16 first.
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: `x\uD800` }), { ...SELECTED })).toBeNull();
  });

  it('requires the exact selected command token when one is selected', () => {
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: COMMAND }), { ...SELECTED_COMMAND })).not.toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: 'pause-receipt-other' }), { ...SELECTED_COMMAND })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt({ command_id: 'A-'.repeat(10) }), { ...SELECTED_COMMAND })).toBeNull();
  });

  it('rejects hostile containers without running user code', () => {
    const counter = { hits: 0 };
    expect(decodeInstructionAdmissionReceipt(getterBody(Object.keys(receipt()), counter), { ...SELECTED })).toBeNull();
    expect(counter.hits).toBe(0);
    expect(decodeInstructionAdmissionReceipt(['receipt'], { ...SELECTED })).toBeNull();
    expect(decodeInstructionAdmissionReceipt('PAUSED', { ...SELECTED })).toBeNull();
    const hidden = receipt();
    Object.defineProperty(hidden, 'shadow', { enumerable: false, value: 1 });
    expect(decodeInstructionAdmissionReceipt(hidden, { ...SELECTED })).toBeNull();
    const expectedGetter = getterBody(['work_ref', 'instruction_ref'], counter);
    expect(decodeInstructionAdmissionReceipt(receipt(), expectedGetter)).toBeNull();
    expect(counter.hits).toBe(0);
    expect(decodeInstructionAdmissionReceipt(receipt(), { ...SELECTED, extra: 1 })).toBeNull();
    expect(decodeInstructionAdmissionReceipt(receipt(), { work_ref: WS })).toBeNull();
  });
});

/* ------------------------------------------------------------------ *
 * control body
 * ------------------------------------------------------------------ */

describe('decodeInstructionAdmissionControl — AVAILABLE', () => {
  it('decodes a paused body with its receipt', () => {
    const decoded = decodeControl(controlBody());
    expect(decoded).not.toBeNull();
    if (!decoded || decoded.availability !== 'AVAILABLE') return fail('wrong branch');
    expect(decoded.availability).toBe('AVAILABLE');
    expect(decoded.state).toBe('PAUSED');
    expect(decoded.permission).toEqual({ pause: true });
    expect(decoded.reason_codes).toEqual([]);
    expect(decoded.current_receipt?.command_id).toBeTypeOf('string');
    expect(decoded.selection).toEqual(SELECTED);
    // The embedded receipt is a fresh object, never the wire value.
    expect(Object.is(decoded.current_receipt, controlBody().current_receipt)).toBe(false);
  });

  it('decodes a not-suspended body with no receipt', () => {
    const decoded = decodeControl(controlBody({ state: 'NOT_SUSPENDED', current_receipt: null }));
    expect(decoded).not.toBeNull();
    if (!decoded || decoded.availability !== 'AVAILABLE') return fail('wrong branch');
    expect(decoded.state).toBe('NOT_SUSPENDED');
    expect(decoded.current_receipt).toBeNull();
  });

  it('accepts an old receipt revision and source that differ from current content', () => {
    // A stable instruction pause survives workstream edits: no cross-check.
    const body = controlBody({
      instruction_revision: OTHER_HEX64,
      source: { ...sourceRef(), content_sha256: OTHER_HEX64 },
      current_receipt: receipt({ revision: OTHER_HEX64, source: { ...sourceRef(), commit: HEX40 } }),
    });
    (body.source as Body).content_sha256 = OTHER_HEX64;
    const decoded = decodeControl(body);
    expect(decoded).not.toBeNull();
    if (!decoded || decoded.availability !== 'AVAILABLE') return fail('wrong branch');
    expect(decoded.instruction_revision).toBe(OTHER_HEX64);
    expect(decoded.source.content_sha256).toBe(OTHER_HEX64);
    expect(decoded.current_receipt?.revision).toBe(OTHER_HEX64);
  });

  it('rejects key-set, schema, availability and selection deviations', () => {
    expect(decodeControl({ ...controlBody(), extra: 1 })).toBeNull();
    const trimmed = controlBody();
    delete trimmed.owner_context;
    expect(decodeControl(trimmed)).toBeNull();
    expect(decodeControl(controlBody({ schema: INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA }))).toBeNull();
    expect(decodeControl(controlBody({ availability: 'PARTIAL' }))).toBeNull();
    expect(decodeControl(controlBody({ availability: 'available' }))).toBeNull();
    expect(decodeControl(controlBody({ selection: { work_ref: WS } }))).toBeNull();
    expect(decodeControl(controlBody({ selection: { work_ref: OTHER_WS, instruction_ref: INS } }))).toBeNull();
    expect(decodeControl(controlBody({ selection: { ...SELECTED, command_id: COMMAND } }))).toBeNull();
    // A different selected pair changes the expected source path too.
    expect(
      decodeInstructionAdmissionControl(controlBody(), { work_ref: OTHER_WS, instruction_ref: INS }),
    ).toBeNull();
  });

  it('rejects malformed current facts', () => {
    expect(decodeControl(controlBody({ source: { ...sourceRef(), path: 'agentos/workstreams/WS-OTHER.md' } }))).toBeNull();
    expect(decodeControl(controlBody({ source: { ...sourceRef(), commit: 'z'.repeat(40) } }))).toBeNull();
    expect(decodeControl(controlBody({ source: null }))).toBeNull();
    expect(decodeControl(controlBody({ instruction_revision: HEX64.slice(0, 63) }))).toBeNull();
    expect(decodeControl(controlBody({ instruction_revision: 'X'.repeat(64) }))).toBeNull();
    expect(decodeControl(controlBody({ reason_codes: ['SOURCE_UNAVAILABLE'] }))).toBeNull();
    expect(decodeControl(controlBody({ owner_context: { principal_scope: 'not-hex' } }))).toBeNull();
    expect(decodeControl(controlBody({ owner_context: { principal_scope: HEX40 } }))).toBeNull();
    expect(decodeControl(controlBody({ owner_context: { ...SELECTED } }))).toBeNull();
  });

  it('treats permission.pause strictly as the boolean fact true', () => {
    expect(decodeControl(controlBody({ permission: { pause: false } }))).toBeNull();
    expect(decodeControl(controlBody({ permission: { pause: 1 } }))).toBeNull();
    expect(decodeControl(controlBody({ permission: { pause: 'true' } }))).toBeNull();
    expect(decodeControl(controlBody({ permission: { pause: null } }))).toBeNull();
    expect(decodeControl(controlBody({ permission: {} }))).toBeNull();
    expect(decodeControl(controlBody({ permission: { pause: true, resume: true } }))).toBeNull();
    expect(decodeControl(controlBody({ permission: null }))).toBeNull();
  });

  it('pairs state and current receipt exactly', () => {
    expect(decodeControl(controlBody({ state: 'SUSPENDED' }))).toBeNull();
    expect(decodeControl(controlBody({ state: 'paused' }))).toBeNull();
    expect(decodeControl(controlBody({ state: 'PAUSED', current_receipt: null }))).toBeNull();
    expect(decodeControl(controlBody({ state: 'NOT_SUSPENDED', current_receipt: receipt() }))).toBeNull();
    expect(decodeControl(controlBody({ state: 'PAUSED', current_receipt: 'PAUSED' }))).toBeNull();
    const broken = controlBody({ current_receipt: receipt({ event_id: 0 }) });
    expect(decodeControl(broken)).toBeNull();
  });
});

describe('decodeInstructionAdmissionControl — UNAVAILABLE', () => {
  it('decodes each closed reason with every fact null', () => {
    for (const reason of INSTRUCTION_ADMISSION_REASON_CODES) {
      const decoded = decodeControl(unavailableBody(reason));
      expect(decoded).not.toBeNull();
      if (!decoded || decoded.availability !== 'UNAVAILABLE') return fail('wrong branch');
      expect(decoded.availability).toBe('UNAVAILABLE');
      expect(decoded.state).toBeNull();
      expect(decoded.source).toBeNull();
      expect(decoded.instruction_revision).toBeNull();
      expect(decoded.permission).toBeNull();
      expect(decoded.owner_context).toBeNull();
      expect(decoded.current_receipt).toBeNull();
      expect(decoded.reason_codes).toEqual([reason]);
    }
  });

  it('rejects reason-code payload deviations', () => {
    expect(decodeControl(unavailableBody('CONFLICT'))).toBeNull();
    expect(decodeControl(unavailableBody('SOURCE_UNAVAILABLE '))).toBeNull();
    const empty = unavailableBody('SOURCE_UNAVAILABLE');
    empty.reason_codes = [];
    expect(decodeControl(empty)).toBeNull();
    const two = unavailableBody('SOURCE_UNAVAILABLE');
    two.reason_codes = ['SOURCE_UNAVAILABLE', 'ACCESS_DENIED'];
    expect(decodeControl(two)).toBeNull();
    const notList = unavailableBody('SOURCE_UNAVAILABLE');
    notList.reason_codes = 'SOURCE_UNAVAILABLE';
    expect(decodeControl(notList)).toBeNull();
    const unknownFirst = unavailableBody('OWNER_OUTCOME_UNCONFIRMED');
    expect(decodeControl(unknownFirst)).toBeNull();
  });

  it('rejects any surviving fact on an unreachable-owner body', () => {
    for (const [key, value] of [
      ['state', 'PAUSED'],
      ['source', sourceRef()],
      ['instruction_revision', HEX64],
      ['permission', { pause: true }],
      ['owner_context', { principal_scope: SCOPE }],
      ['current_receipt', receipt()],
    ] as const) {
      const body = unavailableBody('SOURCE_UNAVAILABLE');
      body[key] = value;
      expect(decodeControl(body)).toBeNull();
    }
    const nulled = unavailableBody('SOURCE_UNAVAILABLE');
    nulled.state = undefined;
    expect(decodeControl(nulled)).toBeNull();
  });
});

describe('decodeInstructionAdmissionControl — hostile input', () => {
  it('returns null for non-body values', () => {
    for (const junk of [null, undefined, 0, 'body', [], true, new Date(0)]) {
      expect(decodeControl(junk)).toBeNull();
    }
  });

  it('rejects accessor properties without invoking them', () => {
    const counter = { hits: 0 };
    const keys = Object.keys(controlBody());
    expect(decodeControl(getterBody(keys, counter))).toBeNull();
    expect(counter.hits).toBe(0);

    // A single accessor among data properties is still rejected, and still
    // never invoked.
    const body = controlBody();
    let hits = 0;
    Object.defineProperty(body, 'permission', {
      enumerable: true,
      get() {
        hits += 1;
        return { pause: true };
      },
    });
    expect(decodeControl(body)).toBeNull();
    expect(hits).toBe(0);
  });

  it('rejects class instances, arrays and symbol keys', () => {
    class Body {}
    expect(decodeControl(new Body())).toBeNull();
    expect(decodeControl([controlBody()])).toBeNull();
    const symbols = controlBody();
    (symbols as unknown as { [k: symbol]: unknown })[Symbol('x')] = 1;
    expect(decodeControl(symbols)).toBeNull();
    const hidden = controlBody();
    Object.defineProperty(hidden, 'shadow', { enumerable: false, value: 1 });
    expect(decodeControl(hidden)).toBeNull();
  });

  it('keeps the whole envelope within the response budget', () => {
    const decoded = decodeControl(controlBody());
    expect(decoded).not.toBeNull();
    const envelope = canonical({ ok: true, result: decoded });
    expect(envelope.startsWith('{"ok":true,"result":')).toBe(true);
    expect(envelope.length + 1).toBeLessThanOrEqual(INSTRUCTION_ADMISSION_MAX_RESPONSE_UTF8_BYTES);
    // The bounded receipt command token stays inside the grammar at 128.
    const wide = controlBody({ current_receipt: receipt({ command_id: `A${'-'.repeat(127)}` }) });
    expect(decodeControl(wide)).not.toBeNull();
    const oversized = controlBody({
      current_receipt: receipt({ command_id: `A${'-'.repeat(128)}` }),
    });
    expect(decodeControl(oversized)).toBeNull();
  });
});

/* ------------------------------------------------------------------ *
 * result bodies
 * ------------------------------------------------------------------ */

describe('decodeInstructionAdmissionResult — pause mode', () => {
  it('decodes a committed action with the exact command receipt', () => {
    const decoded = decodeResult(actionBody({ receipt: receipt({ command_id: COMMAND }) }), 'pause');
    expect(decoded).not.toBeNull();
    if (!decoded || decoded.schema !== INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA) return fail('wrong branch');
    expect(decoded.disposition).toBe('COMMITTED');
    expect(decoded.selection).toEqual(SELECTED_COMMAND);
    expect(decoded.receipt?.command_id).toBe(COMMAND);
    expect(decoded.reason_codes).toEqual([]);
  });

  it('decodes the unknown and not-dispatched outcomes without a receipt', () => {
    const unknown = decodeResult(actionBody({ disposition: 'EFFECT_UNKNOWN', receipt: null, reason_codes: [OWNER_OUTCOME_UNCONFIRMED] }), 'pause');
    expect(unknown).not.toBeNull();
    if (!unknown || unknown.schema !== INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA) return fail('wrong branch');
    expect(unknown.disposition).toBe('EFFECT_UNKNOWN');
    expect(unknown.receipt).toBeNull();
    expect(unknown.reason_codes).toEqual([OWNER_OUTCOME_UNCONFIRMED]);

    for (const reason of INSTRUCTION_ADMISSION_REASON_CODES) {
      const notDispatched = decodeResult(
        actionBody({ disposition: 'NOT_DISPATCHED', receipt: null, reason_codes: [reason] }),
        'pause',
      );
      expect(notDispatched).not.toBeNull();
      if (!notDispatched || notDispatched.schema !== INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA) return fail('wrong branch');
      expect(notDispatched.disposition).toBe('NOT_DISPATCHED');
      expect(notDispatched.reason_codes).toEqual([reason]);
    }
  });

  it('rejects reason payloads that do not match the exact disposition', () => {
    expect(decodeResult(actionBody({ disposition: 'EFFECT_UNKNOWN', reason_codes: [] }), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ disposition: 'EFFECT_UNKNOWN', reason_codes: ['ACCESS_DENIED'] }), 'pause')).toBeNull();
    expect(
      decodeResult(actionBody({ disposition: 'EFFECT_UNKNOWN', reason_codes: [OWNER_OUTCOME_UNCONFIRMED, OWNER_OUTCOME_UNCONFIRMED] }), 'pause'),
    ).toBeNull();
    expect(decodeResult(actionBody({ disposition: 'NOT_DISPATCHED', reason_codes: [] }), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ disposition: 'NOT_DISPATCHED', reason_codes: [OWNER_OUTCOME_UNCONFIRMED] }), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ disposition: 'NOT_DISPATCHED', reason_codes: ['CONFLICT'] }), 'pause')).toBeNull();
    const two = actionBody({ disposition: 'NOT_DISPATCHED', reason_codes: ['ACCESS_DENIED', 'SOURCE_CHANGED'] });
    expect(decodeResult(two, 'pause')).toBeNull();
    const notList = actionBody({ disposition: 'NOT_DISPATCHED' });
    notList.reason_codes = 'ACCESS_DENIED';
    expect(decodeResult(notList, 'pause')).toBeNull();
    // A status vocabulary word on an action body is not a disposition.
    expect(decodeResult(actionBody({ disposition: 'OBSERVED' }), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ disposition: 'NOT_OBSERVED', receipt: null, reason_codes: [] }), 'pause')).toBeNull();
  });

  it('requires a receipt exactly when committed', () => {
    expect(decodeResult(actionBody({ receipt: null }), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ receipt: receipt({ command_id: 'pause-receipt-other' }) }), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ receipt: receipt({ command_id: COMMAND }), reason_codes: ['SOURCE_CHANGED'] }), 'pause')).toBeNull();
    const noReceipt = actionBody({ disposition: 'EFFECT_UNKNOWN' });
    expect(decodeResult(noReceipt, 'pause')).toBeNull();
    const observed = actionBody({ disposition: 'NOT_DISPATCHED', receipt: receipt({ command_id: COMMAND }) });
    expect(decodeResult(observed, 'pause')).toBeNull();
  });

  it('rejects cross-mode schemas and key spellings', () => {
    expect(decodeResult(statusBody(), 'pause')).toBeNull();
    expect(decodeResult(actionBody({ schema: INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA }), 'pause')).toBeNull();
    const stateSpelled = actionBody();
    delete stateSpelled.disposition;
    stateSpelled.state = 'COMMITTED';
    expect(decodeResult(stateSpelled, 'pause')).toBeNull();
    expect(decodeResult(actionBody({ schema: 'mastermind.other.v1' }), 'pause')).toBeNull();
  });

  it('validates the expected command selection strictly', () => {
    expect(decodeInstructionAdmissionResult(actionBody(), { work_ref: WS, instruction_ref: INS }, 'pause')).toBeNull();
    expect(
      decodeInstructionAdmissionResult(actionBody(), { ...SELECTED_COMMAND, extra: 1 }, 'pause'),
    ).toBeNull();
    expect(
      decodeInstructionAdmissionResult(actionBody(), { work_ref: WS, instruction_ref: INS, command_id: 'mmos-instruction-pause-zz' }, 'pause'),
    ).toBeNull();
    const short = `mmos-instruction-pause-${HEX40.slice(0, 39)}`;
    const long = `mmos-instruction-pause-${HEX40}0`;
    const upper = `mmos-instruction-pause-${HEX40.toUpperCase()}`;
    const other = `mmos-other-command-${HEX40}`;
    for (const command_id of [short, long, upper, other]) {
      expect(
        decodeInstructionAdmissionResult(actionBody(), { work_ref: WS, instruction_ref: INS, command_id }, 'pause'),
      ).toBeNull();
    }
    // The body's own selection must equal the selected command selection.
    expect(
      decodeResult(actionBody({ selection: { work_ref: WS, instruction_ref: INS, command_id: `mmos-instruction-pause-${'f'.repeat(40)}` } }), 'pause'),
    ).toBeNull();
    expect(decodeResult(actionBody({ selection: { work_ref: WS, instruction_ref: INS } }), 'pause')).toBeNull();
  });
});

describe('decodeInstructionAdmissionResult — status mode', () => {
  it('decodes an observed status with the exact command receipt', () => {
    const decoded = decodeResult(statusBody({ receipt: receipt({ command_id: COMMAND }) }), 'status');
    expect(decoded).not.toBeNull();
    if (!decoded || decoded.schema !== INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA) return fail('wrong branch');
    expect(decoded.state).toBe('OBSERVED');
    expect(decoded.receipt?.command_id).toBe(COMMAND);
    expect(decoded.reason_codes).toEqual([]);
  });

  it('decodes not-observed with an empty reason list only', () => {
    const decoded = decodeResult(statusBody({ state: 'NOT_OBSERVED', receipt: null, reason_codes: [] }), 'status');
    expect(decoded).not.toBeNull();
    if (!decoded || decoded.schema !== INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA) return fail('wrong branch');
    expect(decoded.state).toBe('NOT_OBSERVED');
    expect(decoded.receipt).toBeNull();
    // NOT_OBSERVED never proves that no effect occurred; the payload stays empty.
    expect(decodeResult(statusBody({ state: 'NOT_OBSERVED', reason_codes: ['ACCESS_DENIED'] }), 'status')).toBeNull();
    expect(decodeResult(statusBody({ state: 'NOT_OBSERVED', reason_codes: [OWNER_OUTCOME_UNCONFIRMED] }), 'status')).toBeNull();
    // A plain not-observed body is exactly valid.
    expect(decodeResult(statusBody({ state: 'NOT_OBSERVED' }), 'status')).not.toBeNull();
  });

  it('decodes unavailable statuses for every closed reason', () => {
    for (const reason of INSTRUCTION_ADMISSION_REASON_CODES) {
      const decoded = decodeResult(statusBody({ state: 'UNAVAILABLE', receipt: null, reason_codes: [reason] }), 'status');
      expect(decoded).not.toBeNull();
      if (!decoded || decoded.schema !== INSTRUCTION_ADMISSION_STATUS_RESULT_SCHEMA) return fail('wrong branch');
      expect(decoded.state).toBe('UNAVAILABLE');
      expect(decoded.reason_codes).toEqual([reason]);
    }
    expect(decodeResult(statusBody({ state: 'UNAVAILABLE', reason_codes: [] }), 'status')).toBeNull();
    expect(decodeResult(statusBody({ state: 'UNAVAILABLE', reason_codes: [OWNER_OUTCOME_UNCONFIRMED] }), 'status')).toBeNull();
  });

  it('rejects action vocabulary and cross-mode bodies', () => {
    expect(decodeResult(actionBody(), 'status')).toBeNull();
    expect(decodeResult(statusBody({ state: 'COMMITTED' }), 'status')).toBeNull();
    expect(decodeResult(statusBody({ state: 'EFFECT_UNKNOWN', reason_codes: [OWNER_OUTCOME_UNCONFIRMED] }), 'status')).toBeNull();
    expect(decodeResult(statusBody({ state: 'NOT_DISPATCHED', reason_codes: ['ACCESS_DENIED'] }), 'status')).toBeNull();
    const dispositionSpelled = statusBody();
    delete dispositionSpelled.state;
    dispositionSpelled.disposition = 'OBSERVED';
    expect(decodeResult(dispositionSpelled, 'status')).toBeNull();
    const wrongSchema = statusBody({ schema: INSTRUCTION_ADMISSION_ACTION_RESULT_SCHEMA });
    expect(decodeResult(wrongSchema, 'status')).toBeNull();
  });

  it('pairs the receipt with the observed state only', () => {
    expect(decodeResult(statusBody({ receipt: null }), 'status')).toBeNull();
    expect(decodeResult(statusBody({ receipt: receipt({ command_id: 'pause-receipt-generic' }) }), 'status')).toBeNull();
    const unobserved = statusBody({ state: 'UNAVAILABLE', receipt: receipt({ command_id: COMMAND }) });
    expect(decodeResult(unobserved, 'status')).toBeNull();
    expect(decodeResult(statusBody({ receipt: receipt({ command_id: COMMAND }), reason_codes: ['OWNER_NOT_READY'] }), 'status')).toBeNull();
  });
});

describe('decodeInstructionAdmissionResult — hostile input', () => {
  it('returns null for non-body values and accessor traps', () => {
    for (const junk of [null, undefined, 'result', 1, [], new Map()]) {
      expect(decodeResult(junk, 'pause')).toBeNull();
      expect(decodeResult(junk, 'status')).toBeNull();
    }
    const counter = { hits: 0 };
    const hostile = getterBody(Object.keys(actionBody()), counter);
    expect(decodeResult(hostile, 'pause')).toBeNull();
    expect(counter.hits).toBe(0);
    const symbols = actionBody();
    (symbols as unknown as { [k: symbol]: unknown })[Symbol('x')] = 1;
    expect(decodeResult(symbols, 'pause')).toBeNull();
  });

  it('stays inside the response budget', () => {
    const decoded = decodeResult(actionBody({ receipt: receipt({ command_id: COMMAND }) }), 'pause');
    expect(decoded).not.toBeNull();
    const envelope = canonical({ ok: true, result: decoded });
    expect(envelope.length + 1).toBeLessThanOrEqual(INSTRUCTION_ADMISSION_MAX_RESPONSE_UTF8_BYTES);
    const statusDecoded = decodeResult(statusBody({ receipt: receipt({ command_id: COMMAND }) }), 'status');
    expect(statusDecoded).not.toBeNull();
    expect(canonical({ ok: true, result: statusDecoded }).length + 1).toBeLessThanOrEqual(
      INSTRUCTION_ADMISSION_MAX_RESPONSE_UTF8_BYTES,
    );
  });
});

/* ------------------------------------------------------------------ *
 * unavailable builder
 * ------------------------------------------------------------------ */

describe('unavailableInstructionAdmissionControl', () => {
  it('builds the exact unavailable body, SOURCE_UNAVAILABLE by default', () => {
    const built = unavailableInstructionAdmissionControl({ ...SELECTED });
    expect(built.availability).toBe('UNAVAILABLE');
    if (built.availability !== 'UNAVAILABLE') return fail('wrong branch');
    expect(built.reason_codes).toEqual(['SOURCE_UNAVAILABLE']);
    // The built body re-decodes through the public decoder.
    expect(decodeControl(structuredClone(built) as unknown)).toEqual(built);
    // And matches the producer-shaped handcrafted body exactly.
    expect(built).toEqual(decodeControl(unavailableBody('SOURCE_UNAVAILABLE')));
  });

  it('builds each closed reason and rejects everything else', () => {
    for (const reason of INSTRUCTION_ADMISSION_REASON_CODES) {
      const built = unavailableInstructionAdmissionControl({ ...SELECTED }, reason);
      expect(built.availability === 'UNAVAILABLE' && built.reason_codes).toEqual([reason]);
    }
    expect(() =>
      unavailableInstructionAdmissionControl({ ...SELECTED }, 'CONFLICT' as InstructionAdmissionReasonCode),
    ).toThrowError(INSTRUCTION_ADMISSION_INVALID);
    expect(() => unavailableInstructionAdmissionControl({ work_ref: WS })).toThrowError(
      INSTRUCTION_ADMISSION_INVALID,
    );
    expect(() => unavailableInstructionAdmissionControl(null)).toThrowError(INSTRUCTION_ADMISSION_INVALID);
  });
});
