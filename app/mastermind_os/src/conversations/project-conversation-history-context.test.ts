import { describe, expect, it } from 'vitest';
import {
  decodeProjectConversationHistoryContext,
  type ProjectConversationHistoryContext,
} from './project-conversation-history-context';

type AnyRec = Record<string, any>;

const WORK_REF = 'WS:AB12cd';
const NOW_MS = 1_700_000_000_123;
const PRINCIPAL = 'a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5061728394a5b6c7d8e9f0';
const EXPIRY_SECONDS = 1_700_000_004; // -> 1_700_000_004_000 ms, strictly after NOW_MS

function freshFrame(): Record<string, unknown> {
  return {
    schema: 'mastermind.os.executive.session_result.v1',
    operation: 'history_context',
    ok: true,
    effect: 'NONE',
    operation_key: null,
    error: null,
    data: {
      schema: 'mastermind.os.executive.project_history_context.v1',
      principal_scope: PRINCIPAL,
      verified_expiry: EXPIRY_SECONDS,
      selection: { work_ref: WORK_REF },
      capabilities: { references_read: true, reply_read: true },
    },
  };
}

function mutatedFrame(mutate: (raw: AnyRec) => void): Record<string, unknown> {
  const raw = freshFrame() as AnyRec;
  mutate(raw);
  return raw;
}

function decode(
  frameValue: unknown,
  workRef: string = WORK_REF,
  nowMs: number = NOW_MS,
): ProjectConversationHistoryContext | null {
  return decodeProjectConversationHistoryContext(frameValue, workRef, nowMs);
}

function expectDecoded(
  frameValue: unknown,
  workRef: string = WORK_REF,
  nowMs: number = NOW_MS,
): ProjectConversationHistoryContext {
  const result = decode(frameValue, workRef, nowMs);
  if (result === null) {
    throw new Error('expected a successful decode');
  }
  return result;
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const key of Object.getOwnPropertyNames(value)) {
      deepFreeze((value as AnyRec)[key]);
    }
  }
  return value;
}

describe('decodeProjectConversationHistoryContext', () => {
  it('decodes a valid rootless read-only (effect NONE) frame into a frozen context', () => {
    const result = expectDecoded(freshFrame());
    expect(result).toEqual({
      workRef: WORK_REF,
      principalScope: PRINCIPAL,
      expiresAtMs: EXPIRY_SECONDS * 1000,
    });
    expect(Object.isFrozen(result)).toBe(true);
    expect(result.workRef).toBe(WORK_REF);
    expect(result.principalScope).toBe(PRINCIPAL);
    expect(result.expiresAtMs).toBe(EXPIRY_SECONDS * 1000);
  });

  it('decodes a null-prototype frame (closed plain object)', () => {
    const raw = Object.assign(Object.create(null), freshFrame()) as AnyRec;
    expect(expectDecoded(raw).principalScope).toBe(PRINCIPAL);
  });

  it('does not mutate its input (a deeply frozen frame still decodes)', () => {
    const raw = deepFreeze(freshFrame() as AnyRec);
    expect(expectDecoded(raw).workRef).toBe(WORK_REF);
  });

  it('returns a detached value that survives later mutation of the raw frame', () => {
    const raw = freshFrame() as AnyRec;
    const result = expectDecoded(raw);
    (raw.data as AnyRec).principal_scope = 'f'.repeat(64);
    (raw.data as AnyRec).selection = { work_ref: 'WS:zz99' };
    (raw.data as AnyRec).verified_expiry = 1;
    raw.schema = 'mastermind.os.executive.other.v1';
    delete raw.operation;
    expect(result).toEqual({
      workRef: WORK_REF,
      principalScope: PRINCIPAL,
      expiresAtMs: EXPIRY_SECONDS * 1000,
    });
  });

  it('exposes an immutable context (frozen; assignment cannot change values)', () => {
    const result = expectDecoded(freshFrame());
    expect(Object.isFrozen(result)).toBe(true);
    let threw = false;
    try {
      (result as { workRef: string }).workRef = 'WS:mutate0';
    } catch {
      threw = true;
    }
    expect(result.workRef).toBe(WORK_REF);
    expect(threw || Object.isFrozen(result)).toBe(true);
  });

  it('rejects non-object and array raw frames', () => {
    const bad: unknown[] = [null, undefined, 7, 'frame', true, [], Symbol('x')];
    for (const candidate of bad) {
      expect(decode(candidate)).toBeNull();
    }
  });

  it('rejects foreign prototypes (class instance, inherited-only fields) without touching them', () => {
    let executed = 0;
    class SpoofFrame {}
    const spoof = Object.assign(new SpoofFrame(), freshFrame()) as unknown as AnyRec;
    expect(decode(spoof)).toBeNull();

    const inherited = Object.create({
      get effect() {
        executed += 1;
        return 'NONE';
      },
      schema: 'mastermind.os.executive.session_result.v1',
    }) as AnyRec;
    Object.assign(inherited, {
      operation: 'history_context',
      ok: true,
      operation_key: null,
      error: null,
      data: (freshFrame() as AnyRec).data,
    });
    expect(decode(inherited)).toBeNull();
    expect(executed).toBe(0);
  });

  it('rejects symbol-keyed own properties anywhere in the frame', () => {
    const symbol = Symbol('extra');
    const envelope = mutatedFrame(() => {}) as AnyRec;
    Reflect.set(envelope, symbol, 1);
    expect(decode(envelope)).toBeNull();

    const data = mutatedFrame((raw) => {
      Reflect.set(raw.data as object, symbol, 1);
    }) as AnyRec;
    expect(decode(data)).toBeNull();

    const capabilities = mutatedFrame((raw) => {
      Reflect.set((raw.data as AnyRec).capabilities as object, symbol, true);
    }) as AnyRec;
    expect(decode(capabilities)).toBeNull();
  });

  it('rejects accessor descriptors without executing any getter (JSON round-trip safe)', () => {
    let executed = 0;
    const spy = () => {
      executed += 1;
      return 'NONE';
    };

    // Accessor on a required envelope key, even returning the correct value.
    const accessorEnvelope = freshFrame() as AnyRec;
    delete accessorEnvelope.effect;
    Object.defineProperty(accessorEnvelope, 'effect', {
      enumerable: true,
      configurable: true,
      get: spy,
    });
    expect(decode(accessorEnvelope)).toBeNull();
    expect(executed).toBe(0);

    // Accessor on data.principal_scope returning the correct value.
    const accessorData = freshFrame() as AnyRec;
    const dataObject = accessorData.data as AnyRec;
    delete dataObject.principal_scope;
    Object.defineProperty(dataObject, 'principal_scope', {
      enumerable: true,
      configurable: true,
      get: () => PRINCIPAL,
    });
    expect(decode(accessorData)).toBeNull();
    expect(executed).toBe(0);

    // toJSON trap: an extra accessor that a JSON round-trip would execute.
    const jsonTrap = freshFrame() as AnyRec;
    Object.defineProperty(jsonTrap, 'toJSON', {
      enumerable: true,
      configurable: true,
      get: spy,
    });
    expect(decode(jsonTrap)).toBeNull();
    expect(executed).toBe(0);
  });

  it('rejects ok:false, non-null operation_key and non-null error', () => {
    expect(decode(mutatedFrame((raw) => { raw.ok = false; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.ok = 'true'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.operation_key = 'op_123'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.error = 'boom'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.error = false; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.operation_key = 0; }))).toBeNull();
  });

  it('rejects wrong envelope schema, operation, effect and unexpected status key', () => {
    expect(
      decode(mutatedFrame((raw) => {
        raw.schema = 'mastermind.os.executive.session_result.v2';
      })),
    ).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.operation = 'history_write'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.operation = 1; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.effect = 'READ'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.effect = 'NONE\n'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.effect = null; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.status = 'ok'; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.root_job_id = 'r1'; }))).toBeNull();
  });

  it('rejects missing, renamed or extra envelope keys', () => {
    for (const key of ['schema', 'operation', 'ok', 'effect', 'operation_key', 'error', 'data']) {
      expect(decode(mutatedFrame((raw) => { delete raw[key]; }))).toBeNull();
    }
    for (const extra of ['status', 'root_job_id', 'job_id', 'principal_scope', 'session_id', 'data2']) {
      expect(decode(mutatedFrame((raw) => { raw[extra] = 'x'; }))).toBeNull();
    }
  });

  it('rejects missing, extra or non-plain data keys (root_job_id included)', () => {
    for (const key of ['schema', 'principal_scope', 'verified_expiry', 'selection', 'capabilities']) {
      expect(
        decode(mutatedFrame((raw) => { delete (raw.data as AnyRec)[key]; })),
      ).toBeNull();
    }
    for (const extra of ['root_job_id', 'send', 'target', 'stop', 'create', 'expires_at', 'ok']) {
      expect(
        decode(mutatedFrame((raw) => { (raw.data as AnyRec)[extra] = true; })),
      ).toBeNull();
    }
    expect(decode(mutatedFrame((raw) => { raw.data = null; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.data = []; }))).toBeNull();
    expect(decode(mutatedFrame((raw) => { raw.data = 'data'; }))).toBeNull();
    expect(
      decode(mutatedFrame((raw) => {
        raw.data = Object.assign(Object.create({ inherited: true }), (freshFrame() as AnyRec).data);
      })),
    ).toBeNull();
  });

  it('rejects wrong data schema', () => {
    expect(
      decode(mutatedFrame((raw) => {
        (raw.data as AnyRec).schema = 'mastermind.os.executive.project_history_context.v2';
      })),
    ).toBeNull();
    expect(
      decode(mutatedFrame((raw) => { (raw.data as AnyRec).schema = 7; })),
    ).toBeNull();
  });

  it('rejects malformed principal_scope values', () => {
    const bad: unknown[] = [
      '',
      'a'.repeat(63),
      'a'.repeat(65),
      PRINCIPAL.toUpperCase(),
      PRINCIPAL.slice(0, 32) + 'g'.repeat(32),
      `${PRINCIPAL}\n`,
      123,
      null,
    ];
    for (const candidate of bad) {
      expect(
        decode(mutatedFrame((raw) => { (raw.data as AnyRec).principal_scope = candidate; })),
      ).toBeNull();
    }
  });

  describe('verified_expiry and nowMs', () => {
    const BASE_SECONDS = 1_700_000_000;

    function withExpiry(seconds: unknown): Record<string, unknown> {
      return mutatedFrame((raw) => { (raw.data as AnyRec).verified_expiry = seconds; });
    }

    it('accepts only a strictly future verified_expiry', () => {
      expect(decode(withExpiry(BASE_SECONDS), WORK_REF, BASE_SECONDS * 1000)).toBeNull();
      expect(decode(withExpiry(BASE_SECONDS), WORK_REF, BASE_SECONDS * 1000 - 1)).not.toBeNull();
      expect(decode(withExpiry(BASE_SECONDS), WORK_REF, BASE_SECONDS * 1000 + 1)).toBeNull();
      expect(
        decode(withExpiry(BASE_SECONDS - 1), WORK_REF, BASE_SECONDS * 1000 - 1000),
      ).toBeNull();
    });

    it('requires verified_expiry seconds to convert to a safe millisecond value', () => {
      const maxSeconds = Math.floor(Number.MAX_SAFE_INTEGER / 1000);
      expect(decode(withExpiry(maxSeconds), WORK_REF, 0)).not.toBeNull();
      expect(decode(withExpiry(maxSeconds + 1), WORK_REF, 0)).toBeNull();
      expect(decode(withExpiry(Number.MAX_SAFE_INTEGER), WORK_REF, 0)).toBeNull();
    });

    it('rejects malformed verified_expiry values', () => {
      const bad: unknown[] = [
        0, -5, 1.5, Number.NaN, Number.POSITIVE_INFINITY, '1700000004', null, true,
      ];
      for (const candidate of bad) {
        expect(decode(withExpiry(candidate))).toBeNull();
      }
    });

    it('requires a finite nonnegative safe-integer nowMs', () => {
      const badNow: unknown[] = [
        Number.NaN,
        Number.POSITIVE_INFINITY,
        Number.NEGATIVE_INFINITY,
        -1,
        1.5,
        90_071_992_547_409_93,
        '1700000000123',
        null,
      ];
      for (const candidate of badNow) {
        expect(decode(freshFrame(), WORK_REF, candidate as number)).toBeNull();
      }
    });
  });

  describe('workRef canonicalization and selection binding', () => {
    it('rejects non-canonical requested workRef values (full match, trailing newline)', () => {
      const bad: string[] = [
        '',
        'ws:AB12cd',
        'WS:',
        'WS:ab12cd',
        'WS: AB12cd',
        'WS:AB12cd\n',
        'WS:AB12cd\r',
        ' WS:AB12cd',
        'WS:AB12cd ',
        'WS:AB12cd\nmore',
        'WS:AB12cd!',
        `WS:${'A'.repeat(65)}`,
      ];
      for (const candidate of bad) {
        expect(decode(freshFrame(), candidate)).toBeNull();
      }
      expect(decode(freshFrame(), 123 as unknown as string)).toBeNull();
    });

    it('rejects cross-work selections (frame bound to a different work ref)', () => {
      expect(decode(freshFrame(), 'WS:Zz99')).toBeNull();
      expect(decode(freshFrame(), 'WS:other99')).toBeNull();
    });

    it('accepts a different but internally consistent canonical pair', () => {
      const raw = mutatedFrame((inner) => {
        inner.data.selection = { work_ref: 'WS:Zz99' };
      });
      expect(expectDecoded(raw, 'WS:Zz99').workRef).toBe('WS:Zz99');
    });

    it('rejects a non-canonical requested workRef even when selection repeats it', () => {
      const newlineRef = 'WS:AB12cd\n';
      const raw = mutatedFrame((inner) => {
        inner.data.selection = { work_ref: newlineRef };
      });
      expect(decode(raw, newlineRef)).toBeNull();
    });

    it('rejects selections that are not exactly {work_ref} bound to the requested ref', () => {
      const bad: unknown[] = [
        {},
        { work_ref: WORK_REF, root_job_id: 'r1' },
        { work_ref: WORK_REF, send: true },
        { ref: WORK_REF },
        { work_ref: 5 },
        { work_ref: null },
        [WORK_REF],
        'WS:AB12cd',
      ];
      for (const candidate of bad) {
        expect(
          decode(mutatedFrame((raw) => { (raw.data as AnyRec).selection = candidate; })),
        ).toBeNull();
      }
    });
  });

  it('rejects capability sets granting anything beyond read-only reference/reply reads', () => {
    const bad: unknown[] = [
      {},
      { references_read: true },
      { reply_read: true },
      { references_read: false, reply_read: true },
      { references_read: true, reply_read: false },
      { references_read: 'yes', reply_read: true },
      { references_read: true, reply_read: 1 },
      { references_read: null, reply_read: true },
      { send: true, reply_read: true },
      { references_read: true, send: true },
      { references_read: true, reply_read: true, send: true },
      { references_read: true, reply_read: true, target: 'x' },
      { references_read: true, reply_read: true, root: true },
      { references_read: true, reply_read: true, stop: true },
      { references_read: true, reply_read: true, create: true },
      { references_read: true, reply_read: true, root_job_id: 'r1' },
      { references_read: true, reply_read: true, extra: null },
    ];
    for (const candidate of bad) {
      expect(
        decode(mutatedFrame((raw) => { (raw.data as AnyRec).capabilities = candidate; })),
      ).toBeNull();
    }
  });
});
