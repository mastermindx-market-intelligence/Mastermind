import { describe, expect, it } from 'vitest';
import {
  PROJECT_ADMISSION_CONTROL_BODY_SCHEMA,
  PROJECT_ADMISSION_MAX_RESPONSE_BYTES,
  PROJECT_ADMISSION_REASON_CODES,
  WORKSTREAM_ADMISSION_RESUMPTION_RECEIPT_SCHEMA,
  WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA,
  decodeProjectAdmissionControl,
  projectAdmissionEnvelopeUtf8Bytes,
  validProjectAdmissionSelection,
  type ProjectAdmissionControl,
} from './project-admission';

const WORK_REF = 'WS:PROPHET-US';
const OTHER_WORK_REF = 'WS:ATLAS-CORE';
const ROOT_JOB_ID = 'JOB-42';
const SELECTION = { work_ref: WORK_REF };
const ROOTED_SELECTION = { work_ref: WORK_REF, root_job_id: ROOT_JOB_ID };
const REQUEST_DIGEST = 'ab'.repeat(32);
const PAUSE_TOKEN_DIGEST = 'cd'.repeat(32);
const PRINCIPAL_SCOPE = 'ef'.repeat(32);
const COMMITTED_AT_MS = 1735689600000;

function pauseReceipt(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA,
    work_ref: WORK_REF,
    state: 'PAUSED',
    event_id: 18,
    command_id: 'pause-admission-1',
    request_digest: REQUEST_DIGEST,
    committed_at_ms: COMMITTED_AT_MS,
    ...overrides,
  };
}

function pauseToken(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { event_id: 18, receipt_digest: PAUSE_TOKEN_DIGEST, ...overrides };
}

function resumptionReceipt(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: WORKSTREAM_ADMISSION_RESUMPTION_RECEIPT_SCHEMA,
    work_ref: WORK_REF,
    state: 'RESUMED',
    event_id: 19,
    command_id: 'resume-admission-1',
    request_digest: REQUEST_DIGEST,
    committed_at_ms: COMMITTED_AT_MS,
    pause_event_id: 18,
    pause_receipt_digest: PAUSE_TOKEN_DIGEST,
    ...overrides,
  };
}

function body(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: PROJECT_ADMISSION_CONTROL_BODY_SCHEMA,
    selection: { work_ref: WORK_REF },
    availability: 'AVAILABLE',
    state: 'PAUSED',
    permissions: { pause: true, resume: false },
    owner_context: { principal_scope: PRINCIPAL_SCOPE },
    current_receipt: pauseReceipt(),
    pause_token: pauseToken(),
    reason_codes: [],
    ...overrides,
  };
}

describe('validProjectAdmissionSelection', () => {
  it('accepts the rootless selection shape', () => {
    expect(validProjectAdmissionSelection(SELECTION)).toBe(true);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:R2D2' })).toBe(true);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:A-B' })).toBe(true);
  });

  it('accepts the optional explicit root proof', () => {
    expect(validProjectAdmissionSelection(ROOTED_SELECTION)).toBe(true);
    expect(validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 'JOB-1' })).toBe(
      true,
    );
  });

  it('rejects non-object and malformed shapes', () => {
    expect(validProjectAdmissionSelection(null)).toBe(false);
    expect(validProjectAdmissionSelection(undefined)).toBe(false);
    expect(validProjectAdmissionSelection('WS:PROPHET-US')).toBe(false);
    expect(validProjectAdmissionSelection(42)).toBe(false);
    expect(validProjectAdmissionSelection(true)).toBe(false);
    expect(validProjectAdmissionSelection([])).toBe(false);
    expect(validProjectAdmissionSelection({})).toBe(false);
    expect(validProjectAdmissionSelection({ root_job_id: 'JOB-1' })).toBe(false);
    expect(
      validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 'JOB-1', extra: 1 }),
    ).toBe(false);
  });

  it('enforces the selector key pattern and 2..64 key length', () => {
    expect(validProjectAdmissionSelection({ work_ref: 'WS:AB' })).toBe(true);
    expect(validProjectAdmissionSelection({ work_ref: `WS:${'A'.repeat(64)}` })).toBe(true);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:A' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: `WS:${'A'.repeat(65)}` })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: '' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'ws:PROPHET-US' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:Ab' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:-PROPHET' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:PROPHET-' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:PRO--PHET' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:PROPHET.US' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:PROPHET_US' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'WS:PROPHET US' })).toBe(false);
    expect(validProjectAdmissionSelection({ work_ref: 'PROPHET-US' })).toBe(false);
  });

  it('accepts frozen leading-zero identifiers and rejects malformed roots', () => {
    expect(validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 'JOB-0' })).toBe(
      true,
    );
    expect(validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 'JOB-007' })).toBe(
      true,
    );
    expect(validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 'JOB-' })).toBe(
      false,
    );
    expect(validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 'job-42' })).toBe(
      false,
    );
    expect(validProjectAdmissionSelection({ work_ref: WORK_REF, root_job_id: 42 })).toBe(false);
  });
});

describe('decodeProjectAdmissionControl — AVAILABLE positives', () => {
  it('decodes a current PAUSED body with receipt and matching pause token', () => {
    const control = decodeProjectAdmissionControl(body(), SELECTION);
    expect(control).not.toBeNull();
    expect(control?.availability).toBe('AVAILABLE');
    expect(control?.schema).toBe(PROJECT_ADMISSION_CONTROL_BODY_SCHEMA);
    expect(control?.selection).toEqual(SELECTION);
    expect(control?.state).toBe('PAUSED');
    if (control?.availability !== 'AVAILABLE') {
      throw new Error('expected AVAILABLE control');
    }
    expect(control.permissions).toEqual({ pause: true, resume: false });
    expect(control.owner_context).toEqual({ principal_scope: PRINCIPAL_SCOPE });
    expect(control.reason_codes).toEqual([]);
    expect(control.current_receipt).toEqual({
      schema: WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA,
      work_ref: WORK_REF,
      state: 'PAUSED',
      event_id: 18,
      command_id: 'pause-admission-1',
      request_digest: REQUEST_DIGEST,
      committed_at_ms: COMMITTED_AT_MS,
    });
    expect(control.pause_token).toEqual({ event_id: 18, receipt_digest: PAUSE_TOKEN_DIGEST });
  });

  it('decodes a NOT_SUSPENDED gate-open body with no receipt and no token', () => {
    const control = decodeProjectAdmissionControl(
      body({ state: 'NOT_SUSPENDED', current_receipt: null, pause_token: null }),
      SELECTION,
    );
    expect(control).not.toBeNull();
    expect(control?.state).toBe('NOT_SUSPENDED');
    if (control?.availability !== 'AVAILABLE') {
      throw new Error('expected AVAILABLE control');
    }
    expect(control.current_receipt).toBeNull();
    expect(control.pause_token).toBeNull();
    expect(control.permissions).toEqual({ pause: true, resume: false });
  });

  it('decodes a RESUMED body with the resumption receipt and no pause token', () => {
    const control = decodeProjectAdmissionControl(
      body({ state: 'RESUMED', current_receipt: resumptionReceipt(), pause_token: null }),
      SELECTION,
    );
    expect(control).not.toBeNull();
    expect(control?.state).toBe('RESUMED');
    if (control?.availability !== 'AVAILABLE') {
      throw new Error('expected AVAILABLE control');
    }
    expect(control.pause_token).toBeNull();
    expect(control.current_receipt).toEqual(resumptionReceipt());
  });

  it('accepts resume-only permission facts (at least one flag true)', () => {
    const control = decodeProjectAdmissionControl(
      body({ permissions: { pause: false, resume: true } }),
      SELECTION,
    );
    expect(control).not.toBeNull();
    if (control?.availability !== 'AVAILABLE') {
      throw new Error('expected AVAILABLE control');
    }
    expect(control.permissions).toEqual({ pause: false, resume: true });
  });

  it('decodes a rooted selection match exactly', () => {
    const control = decodeProjectAdmissionControl(
      body({ selection: { work_ref: WORK_REF, root_job_id: ROOT_JOB_ID } }),
      ROOTED_SELECTION,
    );
    expect(control).not.toBeNull();
    expect(control?.selection).toEqual(ROOTED_SELECTION);
  });

  it('shape-checks the pause digest without claiming independent verification', () => {
    // The frontend cannot recompute the receipt SHA-256; any well-shaped
    // digest decodes and the Python owner alone verifies digest equality.
    const control = decodeProjectAdmissionControl(
      body({ pause_token: pauseToken({ receipt_digest: '09'.repeat(32) }) }),
      SELECTION,
    );
    expect(control).not.toBeNull();
    if (control?.availability !== 'AVAILABLE') {
      throw new Error('expected AVAILABLE control');
    }
    expect(control.pause_token?.receipt_digest).toBe('09'.repeat(32));
  });

  it('returns detached output that no longer tracks the input', () => {
    const input = body();
    const control = decodeProjectAdmissionControl(input, SELECTION);
    expect(control).not.toBeNull();
    const receipt = input['current_receipt'] as Record<string, unknown>;
    receipt['event_id'] = 999;
    (input['pause_token'] as Record<string, unknown>)['receipt_digest'] = 'zz'.repeat(32);
    if (control?.availability !== 'AVAILABLE') {
      throw new Error('expected AVAILABLE control');
    }
    expect(control.current_receipt?.event_id).toBe(18);
    expect(control.pause_token?.receipt_digest).toBe(PAUSE_TOKEN_DIGEST);
    expect(control.selection).not.toBe(input['selection']);
  });
});

describe('decodeProjectAdmissionControl — UNAVAILABLE withholds facts', () => {
  for (const code of PROJECT_ADMISSION_REASON_CODES) {
    it(`decodes UNAVAILABLE with reason ${code} and exposes no facts`, () => {
      const control = decodeProjectAdmissionControl(
        body({
          availability: 'UNAVAILABLE',
          state: null,
          permissions: null,
          owner_context: null,
          current_receipt: null,
          pause_token: null,
          reason_codes: [code],
        }),
        SELECTION,
      );
      expect(control).not.toBeNull();
      if (control?.availability !== 'UNAVAILABLE') {
        throw new Error('expected UNAVAILABLE control');
      }
      expect(control.state).toBeNull();
      expect(control.permissions).toBeNull();
      expect(control.owner_context).toBeNull();
      expect(control.current_receipt).toBeNull();
      expect(control.pause_token).toBeNull();
      expect(control.reason_codes).toEqual([code]);
    });
  }

  it('rejects a stale fact-bearing UNAVAILABLE body (withheld means withheld)', () => {
    expect(
      decodeProjectAdmissionControl(
        body({
          availability: 'UNAVAILABLE',
          state: null,
          permissions: null,
          owner_context: null,
          current_receipt: pauseReceipt(),
          pause_token: null,
          reason_codes: ['SOURCE_CHANGED'],
        }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({
          availability: 'UNAVAILABLE',
          state: 'PAUSED',
          permissions: null,
          owner_context: null,
          current_receipt: null,
          pause_token: null,
          reason_codes: ['SOURCE_CHANGED'],
        }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({
          availability: 'UNAVAILABLE',
          state: null,
          permissions: { pause: true, resume: false },
          owner_context: null,
          current_receipt: null,
          pause_token: null,
          reason_codes: ['SOURCE_CHANGED'],
        }),
        SELECTION,
      ),
    ).toBeNull();
  });

  it('rejects malformed UNAVAILABLE reason code lists', () => {
    const unavailable = (reasonCodes: unknown): Record<string, unknown> =>
      body({
        availability: 'UNAVAILABLE',
        state: null,
        permissions: null,
        owner_context: null,
        current_receipt: null,
        pause_token: null,
        reason_codes: reasonCodes,
      });
    expect(decodeProjectAdmissionControl(unavailable([]), SELECTION)).toBeNull();
    expect(
      decodeProjectAdmissionControl(unavailable(['ACCESS_DENIED', 'ROOT_MISMATCH']), SELECTION),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(unavailable(['NOT_A_REASON']), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(unavailable([7]), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(unavailable('ACCESS_DENIED'), SELECTION)).toBeNull();
  });
});

describe('decodeProjectAdmissionControl — envelope and schema rejections', () => {
  it('rejects a foreign schema string', () => {
    expect(
      decodeProjectAdmissionControl(
        body({ schema: 'mastermind.workspace_project_admission_control_read.v1' }),
        SELECTION,
      ),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(body({ schema: 7 }), SELECTION)).toBeNull();
  });

  it('rejects unknown availability and state enums', () => {
    expect(decodeProjectAdmissionControl(body({ availability: 'unavailable' }), SELECTION)).toBe(
      null,
    );
    expect(decodeProjectAdmissionControl(body({ availability: 'PARTIAL' }), SELECTION)).toBe(
      null,
    );
    expect(decodeProjectAdmissionControl(body({ availability: 1 }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(body({ state: 'SUSPENDED' }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(body({ state: 'PAUSED ' }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(body({ state: null }), SELECTION)).toBeNull();
  });

  it('rejects unknown and missing top-level fields', () => {
    expect(
      decodeProjectAdmissionControl(body({ extra_field: 'x' }), SELECTION),
    ).toBeNull();
    const keys = [
      'schema',
      'selection',
      'availability',
      'state',
      'permissions',
      'owner_context',
      'current_receipt',
      'pause_token',
      'reason_codes',
    ] as const;
    for (const key of keys) {
      const partial = { ...body() };
      delete partial[key];
      expect(decodeProjectAdmissionControl(partial, SELECTION)).toBeNull();
    }
  });

  it('rejects nested unknown fields in permissions, owner context, receipt, token and selection', () => {
    expect(
      decodeProjectAdmissionControl(
        body({ permissions: { pause: true, resume: false, admin: true } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ owner_context: { principal_scope: PRINCIPAL_SCOPE, login: 'op' } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: { ...pauseReceipt(), root_job_id: 'JOB-1' } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ pause_token: { ...pauseToken(), verified: true } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ selection: { work_ref: WORK_REF, command_id: 'pause-admission-1' } }),
        SELECTION,
      ),
    ).toBeNull();
  });

  it('rejects non-empty reason_codes on an AVAILABLE body', () => {
    expect(decodeProjectAdmissionControl(body({ reason_codes: ['ACCESS_DENIED'] }), SELECTION)).toBeNull();
  });
});

describe('decodeProjectAdmissionControl — expected selection handling', () => {
  it('rejects an invalid expected selection outright', () => {
    expect(decodeProjectAdmissionControl(body(), { work_ref: 'WS:A' })).toBeNull();
    expect(decodeProjectAdmissionControl(body(), { work_ref: '' })).toBeNull();
    expect(decodeProjectAdmissionControl(body(), { work_ref: WORK_REF, root_job_id: 'JOB-0' })).toBeNull();
    expect(
      decodeProjectAdmissionControl(body(), { work_ref: WORK_REF, root_job_id: 'JOB-007' }),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body(), { ...SELECTION, extra: 1 } as unknown as {
        work_ref: string;
      }),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(body(), null as unknown as { work_ref: string })).toBeNull();
    expect(
      decodeProjectAdmissionControl(body(), 'WS:PROPHET-US' as unknown as { work_ref: string }),
    ).toBeNull();
  });

  it('rejects exact selection mismatch including optional root shape', () => {
    expect(decodeProjectAdmissionControl(body(), { work_ref: OTHER_WORK_REF })).toBeNull();
    expect(decodeProjectAdmissionControl(body(), ROOTED_SELECTION)).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ selection: { work_ref: WORK_REF, root_job_id: 'JOB-41' } }),
        ROOTED_SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ selection: { work_ref: WORK_REF, root_job_id: 'JOB-41' } }),
        { work_ref: WORK_REF, root_job_id: ROOT_JOB_ID },
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ selection: { work_ref: WORK_REF, root_job_id: ROOT_JOB_ID } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ selection: ROOTED_SELECTION }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ selection: { work_ref: OTHER_WORK_REF } }), SELECTION),
    ).toBeNull();
  });
});

describe('decodeProjectAdmissionControl — receipt, command, work_ref and token matching', () => {
  it('rejects receipts whose work_ref differs from the selection', () => {
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ work_ref: OTHER_WORK_REF }) }),
        SELECTION,
      ),
    ).toBeNull();
  });

  it('rejects malformed receipt command identifiers', () => {
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: pauseReceipt({ command_id: '' }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ command_id: '-pause-1' }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ command_id: `p${'a'.repeat(128)}` }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ command_id: 'pause 1' }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ command_id: 12 }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({
          current_receipt: pauseReceipt({ command_id: `${'a'.repeat(127)}x` }),
        }),
        SELECTION,
      ),
    ).not.toBeNull();
  });

  it('rejects wrong receipt schema, state, digest shape and field types', () => {
    expect(
      decodeProjectAdmissionControl(
        body({
          current_receipt: pauseReceipt({
            schema: WORKSTREAM_ADMISSION_RESUMPTION_RECEIPT_SCHEMA,
          }),
        }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: pauseReceipt({ state: 'RESUMED' }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ request_digest: 'ZZ'.repeat(32) }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ request_digest: 'ab'.repeat(31) }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ event_id: 0 }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ event_id: 1.5 }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ committed_at_ms: -1 }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: null }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: pauseReceipt({ work_ref: 'WS:A' }) }), SELECTION),
    ).toBeNull();
  });

  it('rejects pause tokens that are not the current pause event id', () => {
    // A historical receipt is never current state by itself: the token must
    // point at exactly the current PAUSE event id.
    expect(
      decodeProjectAdmissionControl(body({ pause_token: pauseToken({ event_id: 17 }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ pause_token: pauseToken({ event_id: 19 }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ pause_token: pauseToken({ event_id: '18' }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(body({ pause_token: null }), SELECTION)).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ pause_token: pauseToken({ receipt_digest: 'CD'.repeat(32) }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ pause_token: pauseToken({ receipt_digest: 'cd'.repeat(63) }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ pause_token: 'cd'.repeat(32) }), SELECTION),
    ).toBeNull();
  });
});

describe('decodeProjectAdmissionControl — resumption receipt shape', () => {
  const resumed = (overrides: Record<string, unknown> = {}): Record<string, unknown> =>
    body({ state: 'RESUMED', current_receipt: resumptionReceipt(overrides), pause_token: null });

  it('rejects wrong resumption schema, state and cross-field work_ref', () => {
    expect(
      decodeProjectAdmissionControl(
        resumed({ schema: WORKSTREAM_ADMISSION_SUSPENSION_RECEIPT_SCHEMA }),
        SELECTION,
      ),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(resumed({ state: 'PAUSED' }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(resumed({ work_ref: OTHER_WORK_REF }), SELECTION)).toBeNull();
  });

  it('enforces event-id monotonicity over the pause event', () => {
    expect(decodeProjectAdmissionControl(resumed({ event_id: 18 }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(resumed({ pause_event_id: 19 }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(resumed({ event_id: 20 }), SELECTION)).not.toBeNull();
  });

  it('rejects a RESUMED body that still carries a pause token or malformed digests', () => {
    expect(decodeProjectAdmissionControl(resumed(), { work_ref: WORK_REF })).not.toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ state: 'RESUMED', current_receipt: resumptionReceipt(), pause_token: pauseToken() }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        resumed({ pause_receipt_digest: '0987' }),
        SELECTION,
      ),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(resumed({ pause_event_id: 0 }), SELECTION)).toBeNull();
  });
});

describe('decodeProjectAdmissionControl — permission fact quality', () => {
  it('rejects false/false permissions (no action implied)', () => {
    expect(
      decodeProjectAdmissionControl(body({ permissions: { pause: false, resume: false } }), SELECTION),
    ).toBeNull();
  });

  it('rejects booleans-as-numbers and string flags', () => {
    expect(
      decodeProjectAdmissionControl(body({ permissions: { pause: 1, resume: false } }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ permissions: { pause: true, resume: 0 } }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ permissions: { pause: 'true', resume: false } }),
        SELECTION,
      ),
    ).toBeNull();
  });

  it('rejects a foreign or malformed owner context scope', () => {
    expect(
      decodeProjectAdmissionControl(
        body({ owner_context: { principal_scope: 'EF'.repeat(32) } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ owner_context: { principal_scope: 'operator-login' } }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ owner_context: { principal_scope: 123 } }), SELECTION),
    ).toBeNull();
    expect(decodeProjectAdmissionControl(body({ owner_context: null }), SELECTION)).toBeNull();
    expect(decodeProjectAdmissionControl(body({ permissions: null }), SELECTION)).toBeNull();
  });
});

describe('decodeProjectAdmissionControl — numbers, booleans and non-finites', () => {
  it('rejects NaN and Infinity in receipt integers', () => {
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: pauseReceipt({ event_id: Number.NaN }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ committed_at_ms: Number.POSITIVE_INFINITY }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ committed_at_ms: Number.NEGATIVE_INFINITY }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ state: 'RESUMED', current_receipt: resumptionReceipt({ event_id: Number.NaN }), pause_token: null }),
        SELECTION,
      ),
    ).toBeNull();
  });

  it('rejects boolean values in integer positions', () => {
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: pauseReceipt({ event_id: true }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ current_receipt: pauseReceipt({ committed_at_ms: false }) }),
        SELECTION,
      ),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(
        body({ state: 'RESUMED', current_receipt: resumptionReceipt({ pause_event_id: true }), pause_token: null }),
        SELECTION,
      ),
    ).toBeNull();
  });

  it('rejects non-integer and string-typed event ids and tokens', () => {
    expect(
      decodeProjectAdmissionControl(body({ pause_token: pauseToken({ event_id: 18.5 }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ pause_token: pauseToken({ event_id: NaN }) }), SELECTION),
    ).toBeNull();
    expect(
      decodeProjectAdmissionControl(body({ current_receipt: pauseReceipt({ state: 7 }) }), SELECTION),
    ).toBeNull();
  });
});

describe('response envelope byte cap', () => {
  it('matches the owner cap constant', () => {
    expect(PROJECT_ADMISSION_MAX_RESPONSE_BYTES).toBe(32768);
  });

  it('counts the canonical envelope plus trailing newline against the cap', () => {
    const within = { pad: 'a'.repeat(32736) };
    const over = { pad: 'a'.repeat(32737) };
    const withinBytes = projectAdmissionEnvelopeUtf8Bytes(within);
    const overBytes = projectAdmissionEnvelopeUtf8Bytes(over);
    expect(withinBytes).toBe(32767);
    expect(overBytes).toBe(32768);
    expect((withinBytes as number) + 1).toBeLessThanOrEqual(PROJECT_ADMISSION_MAX_RESPONSE_BYTES);
    expect((overBytes as number) + 1).toBeGreaterThan(PROJECT_ADMISSION_MAX_RESPONSE_BYTES);
  });

  it('rejects non-serializable envelope payloads instead of guessing', () => {
    expect(projectAdmissionEnvelopeUtf8Bytes({ pad: Number.NaN })).toBeNull();
    expect(projectAdmissionEnvelopeUtf8Bytes({ pad: Infinity })).toBeNull();
    expect(projectAdmissionEnvelopeUtf8Bytes({ pad: undefined })).toBeNull();
    expect(projectAdmissionEnvelopeUtf8Bytes({ pad: () => 'x' })).toBeNull();
  });

  it('never trips the cap on a fully shaped valid body (defense in depth)', () => {
    const paused = body();
    const resumedBody = body({
      state: 'RESUMED',
      current_receipt: resumptionReceipt(),
      pause_token: null,
    });
    const unavailable = body({
      availability: 'UNAVAILABLE',
      state: null,
      permissions: null,
      owner_context: null,
      current_receipt: null,
      pause_token: null,
      reason_codes: ['SOURCE_UNAVAILABLE'],
    });
    for (const input of [paused, resumedBody, unavailable]) {
      const bytes = projectAdmissionEnvelopeUtf8Bytes(input);
      expect(bytes).not.toBeNull();
      expect((bytes as number) + 1).toBeLessThanOrEqual(PROJECT_ADMISSION_MAX_RESPONSE_BYTES);
      expect(decodeProjectAdmissionControl(input, SELECTION)).not.toBeNull();
    }
  });
});

describe('decoder type narrowing', () => {
  it('discriminates the closed union on availability', () => {
    const available = decodeProjectAdmissionControl(body(), SELECTION) as ProjectAdmissionControl;
    const unavailable = decodeProjectAdmissionControl(
      body({
        availability: 'UNAVAILABLE',
        state: null,
        permissions: null,
        owner_context: null,
        current_receipt: null,
        pause_token: null,
        reason_codes: ['OWNER_NOT_READY'],
      }),
      SELECTION,
    ) as ProjectAdmissionControl;
    const states: (string | null)[] = [];
    if (available.availability === 'AVAILABLE') {
      states.push(available.state);
      expect(available.reason_codes).toEqual([]);
    }
    if (unavailable.availability === 'UNAVAILABLE') {
      states.push(unavailable.state);
      expect(unavailable.reason_codes[0]).toBe('OWNER_NOT_READY');
      expect(unavailable.current_receipt).toBeNull();
    }
    expect(states).toEqual(['PAUSED', null]);
  });
});


describe('actual producer and parent protocol corrections',()=>{
  it('decodes actual Runtime/Workspace source fixtures with leading-zero root identity',async()=>{
    const source=await import('./fixtures/project-admission-owner.json');
    for(const value of [source.open,source.paused,source.resumed])expect(decodeProjectAdmissionControl(value,value.selection)).toEqual(value);
  });
  it('uses frozen root grammar and exact full string matches',()=>{
    for(const root of ['JOB-0','JOB-001','JOB-123456789'])expect(validProjectAdmissionSelection({work_ref:'WS:ONE',root_job_id:root})).toBe(true);
    for(const root of ['JOB-1234567890','JOB-1\n','JOB-'])expect(validProjectAdmissionSelection({work_ref:'WS:ONE',root_job_id:root})).toBe(false);
    expect(validProjectAdmissionSelection({work_ref:'WS:ONE\n'})).toBe(false);
  });
  it('does not invoke getters or serialize custom objects',()=>{
    let touched=false;const input=body();Object.defineProperty(input,'permissions',{get(){touched=true;return {pause:true,resume:true};},enumerable:true});
    expect(decodeProjectAdmissionControl(input,{work_ref:WORK_REF})).toBeNull();expect(touched).toBe(false);
    const inherited=Object.assign(Object.create({root_job_id:'JOB-1'}),{work_ref:WORK_REF,extra:true});expect(validProjectAdmissionSelection(inherited)).toBe(false);
    const symbol=Symbol('hidden');const selected={work_ref:WORK_REF,[symbol]:true};expect(validProjectAdmissionSelection(selected)).toBe(false);
  });
});
